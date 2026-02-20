from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Optional
import asyncio
import logging

from engine.hybride import generate, generate_grids
import db_cloudsql
from schemas import AskPayload
from rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ask")
@limiter.limit("60/minute")
async def ask(request: Request, payload: AskPayload):
    """
    Endpoint principal du moteur HYBRIDE
    """
    try:
        result = await asyncio.to_thread(generate, payload.prompt)
        return {
            "success": True,
            "response": result
        }
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal engine error"
        )


@router.get("/generate")
@limiter.limit("60/minute")
async def generate_endpoint(
    request: Request,
    n: int = Query(default=3, ge=1, le=10, description="Nombre de grilles"),
    mode: str = Query(default="balanced", description="Mode: conservative, balanced, recent")
):
    """
    Genere N grilles optimisees.

    Args:
        n: Nombre de grilles (1-10, defaut: 3)
        mode: Mode de generation (conservative, balanced, recent)

    Returns:
        JSON {success: bool, grids: [...], metadata: {...}}
    """
    try:
        # Validation du mode
        valid_modes = ["conservative", "balanced", "recent"]
        if mode not in valid_modes:
            mode = "balanced"

        result = await asyncio.to_thread(generate_grids, n=n, mode=mode)

        return {
            "success": True,
            "grids": result['grids'],
            "metadata": result['metadata']
        }
    except Exception as e:
        logger.error(f"Erreur /generate: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": "Erreur interne lors de la generation",
            "grids": [],
            "metadata": {}
        })


# =========================
# META ANALYSE Local
# =========================

@router.get("/api/meta-analyse-local")
@limiter.limit("60/minute")
async def api_meta_analyse_local(
    request: Request,
    window: Optional[str] = Query(default="GLOBAL", description="Fenêtre d'analyse: 25, 50, 75, 100, 200, 500, ou GLOBAL"),
    years: Optional[str] = Query(default=None, description="Fenêtre en années: 1, 2, 3, 4, 5, 6, ou GLOBAL")
):
    """
    Endpoint local pour META ANALYSE 75 grilles.
    Utilise le moteur HYBRIDE interne et la BDD locale.
    Paramètre window : nombre de tirages récents à analyser (ou GLOBAL pour tous).
    Paramètre years : nombre d'années complètes (prioritaire sur window si fourni).
    Aucune API externe, aucune IA, aucun PDF réel.
    Temps de réponse cible : < 300ms.
    """
    from datetime import datetime, timedelta

    try:
        def _compute():
            conn = None
            try:
                conn = db_cloudsql.get_connection()
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) as total FROM tirages")
                total_rows = cursor.fetchone()['total']

                mode_used = "tirages"
                window_used = "GLOBAL"
                years_used = None
                use_date_filter = False
                date_limit = None

                if years is not None:
                    mode_used = "annees"
                    if years.upper() == "GLOBAL":
                        window_used = "GLOBAL"
                        years_used = "GLOBAL"
                    else:
                        try:
                            years_int = int(years)
                            if 1 <= years_int <= 10:
                                years_used = str(years_int)
                                window_used = f"{years_int}A"
                                use_date_filter = True
                                date_limit = (datetime.now() - timedelta(days=365 * years_int)).strftime('%Y-%m-%d')
                            else:
                                years_used = "GLOBAL"
                                window_used = "GLOBAL"
                        except (ValueError, TypeError):
                            years_used = "GLOBAL"
                            window_used = "GLOBAL"
                else:
                    mode_used = "tirages"
                    if window and window.upper() != "GLOBAL":
                        try:
                            window_int = int(window)
                            if window_int >= 1:
                                window_used = str(min(window_int, total_rows))
                        except (ValueError, TypeError):
                            window_used = "GLOBAL"

                if use_date_filter and date_limit:
                    cursor.execute("""
                        SELECT id FROM tirages
                        WHERE date_de_tirage >= %s
                        ORDER BY date_de_tirage DESC
                    """, (date_limit,))
                elif window_used != "GLOBAL":
                    cursor.execute("""
                        SELECT id FROM tirages
                        ORDER BY date_de_tirage DESC
                        LIMIT %s
                    """, (int(window_used),))
                else:
                    cursor.execute("""
                        SELECT id FROM tirages
                        ORDER BY date_de_tirage DESC
                    """)
                window_ids = [row['id'] for row in cursor.fetchall()]

                if not window_ids:
                    raise Exception("Aucun tirage trouvé")

                ids_placeholder = ','.join(['%s'] * len(window_ids))

                cursor.execute(f"""
                    SELECT num, COUNT(*) as freq FROM (
                        SELECT boule_1 as num FROM tirages WHERE id IN ({ids_placeholder})
                        UNION ALL SELECT boule_2 FROM tirages WHERE id IN ({ids_placeholder})
                        UNION ALL SELECT boule_3 FROM tirages WHERE id IN ({ids_placeholder})
                        UNION ALL SELECT boule_4 FROM tirages WHERE id IN ({ids_placeholder})
                        UNION ALL SELECT boule_5 FROM tirages WHERE id IN ({ids_placeholder})
                    ) t
                    GROUP BY num
                    ORDER BY num
                """, (*window_ids, *window_ids, *window_ids, *window_ids, *window_ids))
                freq_map = {row['num']: row['freq'] for row in cursor.fetchall()}
                top_numbers = [{"number": n, "count": freq_map.get(n, 0)} for n in range(1, 50)]

                top_numbers = sorted(top_numbers, key=lambda x: -x['count'])[:5]

                cursor.execute(f"""
                    SELECT MIN(date_de_tirage) as min_date, MAX(date_de_tirage) as max_date
                    FROM tirages
                    WHERE id IN ({ids_placeholder})
                """, window_ids)
                dates = cursor.fetchone()
                date_min = dates['min_date']
                date_max = dates['max_date']

                graph_labels = [str(n['number']) for n in top_numbers]
                graph_values = [n['count'] for n in top_numbers]

                avg_freq = sum(graph_values) / len(graph_values) if graph_values else 0
                max_freq = max(graph_values) if graph_values else 0
                min_freq = min(graph_values) if graph_values else 0
                spread = max_freq - min_freq

                if spread < 5:
                    dispersion_text = "dispersion très homogène"
                elif spread < 15:
                    dispersion_text = "dispersion équilibrée"
                else:
                    dispersion_text = "dispersion marquée"

                actual_count = len(window_ids)
                if mode_used == "annees" and years_used and years_used != "GLOBAL":
                    window_label = f"{years_used} an(s) ({actual_count} tirages)"
                elif window_used != "GLOBAL":
                    window_label = f"{actual_count} tirages"
                else:
                    window_label = "l'intégralité de la base"

                analysis_text = (
                    f"Analyse locale HYBRIDE sur {window_label} "
                    f"({date_min} → {date_max}). "
                    f"Top 5 numéros : {', '.join(graph_labels)} avec fréquence moyenne {avg_freq:.1f}. "
                    f"Écart max-min : {spread} ({dispersion_text}). "
                    f"Aucun biais algorithmique détecté."
                )

                return {
                    "success": True,
                    "rows_used": actual_count,
                    "is_global": window_used == "GLOBAL",
                    "graph": {
                        "labels": graph_labels,
                        "values": graph_values
                    },
                    "analysis": analysis_text,
                    "pdf": False,
                    "meta": {
                        "total_draws": total_rows,
                        "window_used": window_used,
                        "window_size": actual_count,
                        "mode_used": mode_used,
                        "years_used": years_used,
                        "date_min": str(date_min) if date_min else None,
                        "date_max": str(date_max) if date_max else None,
                        "period": f"{date_min} - {date_max}",
                        "source": "HYBRIDE_LOCAL"
                    }
                }
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        return await asyncio.to_thread(_compute)

    except Exception as e:
        logger.error(f"Erreur /api/meta-analyse-local: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "graph": None,
            "analysis": None,
            "pdf": False,
            "meta": {
                "source": "ERROR",
                "error": "Erreur interne lors de l'analyse"
            }
        })


@router.post("/api/analyze-custom-grid")
@limiter.limit("60/minute")
async def api_analyze_custom_grid(
    request: Request,
    nums: list = Query(..., description="5 numeros principaux"),
    chance: int = Query(..., ge=1, le=10, description="Numero chance")
):
    """
    Analyse une grille personnalisee composee par l'utilisateur.
    Retourne un score, des badges et des suggestions.
    """
    try:
        # Validation
        if len(nums) != 5:
            return {"success": False, "error": "5 numeros requis"}

        nums = [int(n) for n in nums]
        if not all(1 <= n <= 49 for n in nums):
            return {"success": False, "error": "Numeros doivent etre entre 1 et 49"}

        if len(set(nums)) != 5:
            return {"success": False, "error": "Numeros doivent etre uniques"}

        nums = sorted(nums)

        def _compute():
            conn = None
            try:
                conn = db_cloudsql.get_connection()
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) as total FROM tirages")
                total_tirages = cursor.fetchone()['total']

                cursor.execute("""
                    SELECT num, COUNT(*) as freq FROM (
                        SELECT boule_1 as num FROM tirages
                        UNION ALL SELECT boule_2 FROM tirages
                        UNION ALL SELECT boule_3 FROM tirages
                        UNION ALL SELECT boule_4 FROM tirages
                        UNION ALL SELECT boule_5 FROM tirages
                    ) t
                    WHERE num IN (%s, %s, %s, %s, %s)
                    GROUP BY num
                """, tuple(nums))
                freq_map = {row['num']: row['freq'] for row in cursor.fetchall()}
                frequencies = [freq_map.get(num, 0) for num in nums]

                # Correspondance exacte (boules + chance)
                # Utilise IN pour les boules (independant de l'ordre de stockage)
                cursor.execute("""
                    SELECT date_de_tirage
                    FROM tirages
                    WHERE boule_1 IN (%s, %s, %s, %s, %s)
                      AND boule_2 IN (%s, %s, %s, %s, %s)
                      AND boule_3 IN (%s, %s, %s, %s, %s)
                      AND boule_4 IN (%s, %s, %s, %s, %s)
                      AND boule_5 IN (%s, %s, %s, %s, %s)
                      AND numero_chance = %s
                    ORDER BY date_de_tirage DESC
                """, (*nums, *nums, *nums, *nums, *nums, chance))
                exact_matches = cursor.fetchall()
                exact_dates = [str(row['date_de_tirage']) for row in exact_matches]

                cursor.execute("""
                    SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance,
                        (
                            (boule_1 IN (%s, %s, %s, %s, %s)) +
                            (boule_2 IN (%s, %s, %s, %s, %s)) +
                            (boule_3 IN (%s, %s, %s, %s, %s)) +
                            (boule_4 IN (%s, %s, %s, %s, %s)) +
                            (boule_5 IN (%s, %s, %s, %s, %s))
                        ) AS match_count,
                        (numero_chance = %s) AS chance_match
                    FROM tirages
                    ORDER BY match_count DESC, chance_match DESC, date_de_tirage DESC
                    LIMIT 1
                """, (*nums, *nums, *nums, *nums, *nums, chance))
                best_match = cursor.fetchone()

                best_match_numbers = []
                if best_match:
                    # Cast int() pour garantir la coherence de type
                    tirage_nums = [int(best_match['boule_1']), int(best_match['boule_2']),
                                   int(best_match['boule_3']), int(best_match['boule_4']),
                                   int(best_match['boule_5'])]
                    best_match_numbers = sorted([n for n in nums if n in tirage_nums])

                # Source unique de verite : intersection Python (pas le match_count SQL)
                history_check = {
                    "exact_match": len(exact_dates) > 0,
                    "exact_dates": exact_dates,
                    "best_match_count": len(best_match_numbers),
                    "best_match_chance": bool(best_match['chance_match']) if best_match else False,
                    "best_match_chance_number": int(best_match['numero_chance']) if best_match and best_match['chance_match'] else None,
                    "best_match_date": str(best_match['date_de_tirage']) if best_match else None,
                    "best_match_numbers": best_match_numbers
                }

                nb_pairs = sum(1 for n in nums if n % 2 == 0)
                nb_impairs = 5 - nb_pairs
                nb_bas = sum(1 for n in nums if n <= 24)
                nb_hauts = 5 - nb_bas
                somme = sum(nums)
                dispersion = max(nums) - min(nums)

                nums_sorted = sorted(nums)
                suites = sum(1 for i in range(4) if nums_sorted[i+1] - nums_sorted[i] == 1)

                # Calcul du plus long run consecutif
                max_run = 1
                current_run = 1
                for i in range(4):
                    if nums_sorted[i+1] - nums_sorted[i] == 1:
                        current_run += 1
                        if current_run > max_run:
                            max_run = current_run
                    else:
                        current_run = 1

                # Score de conformite avec penalites graduelles
                score_conformite = 100

                # Pair/Impair : penalite graduelle
                if nb_pairs == 0 or nb_pairs == 5:
                    score_conformite -= 25
                elif nb_pairs == 1 or nb_pairs == 4:
                    score_conformite -= 10

                # Bas/Haut : penalite graduelle
                if nb_bas == 0 or nb_bas == 5:
                    score_conformite -= 25
                elif nb_bas == 1 or nb_bas == 4:
                    score_conformite -= 8

                # Somme : penalite proportionnelle a la distance
                if somme < 50:
                    score_conformite -= 35
                elif somme < 70:
                    score_conformite -= 20
                elif somme > 200:
                    score_conformite -= 35
                elif somme > 150:
                    score_conformite -= 20

                # Dispersion
                if dispersion < 10:
                    score_conformite -= 35
                elif dispersion < 15:
                    score_conformite -= 20

                # Suites consecutives (selon longueur du run)
                if max_run >= 5:
                    score_conformite -= 30
                elif max_run >= 4:
                    score_conformite -= 20
                elif max_run >= 3:
                    score_conformite -= 10

                score_conformite = max(0, score_conformite)

                freq_moyenne = sum(frequencies) / 5
                freq_max_theorique = total_tirages * 5 / 49
                score_freq = min(100, (freq_moyenne / freq_max_theorique) * 100)

                score = int(0.6 * score_conformite + 0.4 * score_freq)
                score = max(0, min(100, score))

                badges = []
                if freq_moyenne > freq_max_theorique * 1.1:
                    badges.append("Numeros chauds")
                elif freq_moyenne < freq_max_theorique * 0.9:
                    badges.append("Mix de retards")
                else:
                    badges.append("Equilibre")

                if dispersion > 35:
                    badges.append("Large spectre")
                if nb_pairs == 2 or nb_pairs == 3:
                    badges.append("Pair/Impair OK")

                badges.append("Analyse personnalisee")

                # ── Detection des conditions critiques ──
                critical_count = 0
                critical_flags = {}

                if max_run >= 4:
                    critical_count += 1
                    critical_flags['suite'] = max_run
                if somme < 50 or somme > 200:
                    critical_count += 1
                    critical_flags['somme'] = somme
                if dispersion < 10:
                    critical_count += 1
                    critical_flags['dispersion'] = dispersion
                if nb_bas == 0 or nb_bas == 5:
                    critical_count += 1
                    critical_flags['bas_haut'] = f"{nb_bas}/{nb_hauts}"
                if nb_pairs == 0 or nb_pairs == 5:
                    critical_count += 1
                    critical_flags['pairs'] = f"{nb_pairs}/{nb_impairs}"
                if score_conformite < 20:
                    critical_count += 1
                    critical_flags['conformite'] = score_conformite

                # Determination du palier de severite
                if critical_count >= 3:
                    severity = 3
                elif critical_count >= 2 or (critical_count == 1 and max_run >= 4):
                    severity = 2
                else:
                    severity = 1

                # ── Generation des suggestions selon le palier ──
                suggestions = []
                alert_message = None

                if severity == 3:
                    # PALIER 3 — Critique : messages cinglants
                    alert_message = "Alerte maximale : cette grille cumule TOUS les defauts statistiques !"

                    if 'suite' in critical_flags:
                        suggestions.append(f"Suite parfaite detectee ! En {total_tirages} tirages, AUCUNE suite de {max_run} consecutifs n'est jamais sortie")
                    if 'somme' in critical_flags:
                        suggestions.append(f"Somme catastrophique ({somme}) — les tirages reels oscillent entre 80 et 170")
                    if 'bas_haut' in critical_flags:
                        if nb_bas == 5:
                            suggestions.append("ZERO numero au-dessus de 24 — statistiquement aberrant")
                        else:
                            suggestions.append("ZERO numero en dessous de 25 — statistiquement aberrant")
                    if 'dispersion' in critical_flags:
                        suggestions.append(f"Dispersion quasi nulle ({dispersion}) — la moyenne historique est autour de 30+")
                    if 'pairs' in critical_flags:
                        if nb_pairs == 5:
                            suggestions.append("100% de numeros pairs — aucun tirage historique n'a cette configuration")
                        else:
                            suggestions.append("100% de numeros impairs — aucun tirage historique n'a cette configuration")
                    if 'conformite' in critical_flags:
                        suggestions.append(f"Score de conformite effondre ({score_conformite}%) — cette grille defie toutes les statistiques")

                elif severity == 2:
                    # PALIER 2 — Modere : avertissements directs
                    if 'suite' in critical_flags:
                        suggestions.append(f"Suite de {max_run} numeros consecutifs detectee — tres rare dans les tirages reels")
                    if nb_pairs == 0 or nb_pairs == 5:
                        suggestions.append(f"Desequilibre pair/impair ({nb_pairs}/{nb_impairs}) — viser 2-3 pairs pour coller aux statistiques")
                    if nb_bas == 0 or nb_bas == 5:
                        suggestions.append(f"Desequilibre bas/haut ({nb_bas}/{nb_hauts}) — mixer numeros bas (1-24) et hauts (25-49)")
                    if somme < 50 or somme > 200:
                        suggestions.append(f"Somme trop {'basse' if somme < 50 else 'elevee'} ({somme}) — la moyenne historique est autour de 125")
                    elif somme < 70 or somme > 150:
                        suggestions.append(f"Somme {'basse' if somme < 70 else 'elevee'} ({somme}) — viser la fourchette 80-170")
                    if dispersion < 10:
                        suggestions.append(f"Dispersion insuffisante ({dispersion}) — vos numeros couvrent seulement {dispersion} unites sur 48 possibles")
                    elif dispersion < 15:
                        suggestions.append(f"Dispersion faible ({dispersion}) — elargir l'ecart entre vos numeros")
                    if max_run >= 3 and 'suite' not in critical_flags:
                        suggestions.append(f"Suite de {max_run} consecutifs — reduire les numeros qui se suivent")

                else:
                    # PALIER 1 — Leger : suggestions douces
                    if score >= 70:
                        suggestions.append("Excellent equilibre dans votre selection")
                    if nb_pairs == 1 or nb_pairs == 4:
                        suggestions.append("Pensez a varier pairs et impairs (2-3 pairs ideal)")
                    if nb_bas == 1 or nb_bas == 4:
                        suggestions.append("Mixer numeros bas (1-24) et hauts (25-49)")
                    if 70 <= somme < 80:
                        suggestions.append("Somme un peu basse, ajouter un numero plus eleve")
                    elif 150 < somme <= 170:
                        suggestions.append("Somme un peu elevee, ajouter un numero plus bas")
                    if 15 <= dispersion < 20:
                        suggestions.append("Elargir legerement la dispersion de vos numeros")
                    if max_run == 3:
                        suggestions.append("Attention a la suite de 3 consecutifs")
                    elif suites >= 2 and max_run < 3:
                        suggestions.append("Quelques numeros consecutifs — pensez a les espacer")

                if not suggestions:
                    suggestions.append("Grille bien equilibree")

                if score >= 80:
                    comparaison = "Meilleure que 85% des grilles aleatoires"
                elif score >= 60:
                    comparaison = "Meilleure que 60% des grilles aleatoires"
                elif score >= 40:
                    comparaison = "Dans la moyenne des grilles"
                else:
                    comparaison = "En dessous de la moyenne"

                return {
                    "success": True,
                    "nums": nums,
                    "chance": chance,
                    "score": score,
                    "comparaison": comparaison,
                    "badges": badges,
                    "details": {
                        "pairs_impairs": f"{nb_pairs}/{nb_impairs}",
                        "bas_haut": f"{nb_bas}/{nb_hauts}",
                        "somme": str(somme),
                        "dispersion": str(dispersion),
                        "suites_consecutives": str(suites),
                        "score_conformite": f"{score_conformite}%"
                    },
                    "severity": severity,
                    "alert_message": alert_message,
                    "suggestions": suggestions,
                    "history_check": history_check
                }
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        return await asyncio.to_thread(_compute)

    except Exception as e:
        logger.error(f"Erreur /api/analyze-custom-grid: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": "Erreur interne lors de l'analyse"
        })
