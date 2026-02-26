"""
Routes API EuroMillions — Analyse (generateur, META, grilles custom)
Equivalent EM de routes/api_analyse.py
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Optional
import logging

from engine.hybride_em import generate_grids
from em_schemas import EMMetaAnalyseTextePayload, EMMetaPdfPayload
import db_cloudsql
from rate_limit import limiter
from services.penalization import compute_penalized_ranking

logger = logging.getLogger(__name__)

TABLE = "tirages_euromillions"

router = APIRouter(prefix="/api/euromillions", tags=["EuroMillions - Analyse"])


# =========================
# Generateur de grilles EM
# =========================

@router.get("/generate")
@limiter.limit("60/minute")
async def em_generate(
    request: Request,
    n: int = Query(default=3, ge=1, le=10, description="Nombre de grilles"),
    mode: str = Query(default="balanced", description="Mode: conservative, balanced, recent")
):
    """
    Genere N grilles EuroMillions optimisees.
    Chaque grille contient 5 boules [1-50] + 2 etoiles [1-12].
    """
    try:
        valid_modes = ["conservative", "balanced", "recent"]
        if mode not in valid_modes:
            mode = "balanced"

        result = await generate_grids(n=n, mode=mode)

        return {
            "success": True,
            "grids": result['grids'],
            "metadata": result['metadata']
        }
    except Exception as e:
        logger.error(f"Erreur /api/euromillions/generate: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": "Erreur interne lors de la generation",
            "grids": [],
            "metadata": {}
        })


# =========================
# META ANALYSE Local EM
# =========================

@router.get("/meta-analyse-local")
@limiter.limit("60/minute")
async def em_meta_analyse_local(
    request: Request,
    window: Optional[str] = Query(default="GLOBAL", description="Fenêtre: 25, 50, 75, 100, 200, 500, ou GLOBAL"),
    years: Optional[str] = Query(default=None, description="Fenêtre en années: 1, 2, 3, 4, 5, 6, ou GLOBAL")
):
    """
    META ANALYSE locale EuroMillions.
    Analyse les frequences des boules et etoiles sur une fenetre configurable.
    """
    from datetime import datetime, timedelta
    from services.em_stats_service import _get_all_frequencies

    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()

            await cursor.execute(f"SELECT COUNT(*) as total FROM {TABLE}")
            total_rows = (await cursor.fetchone())['total']

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

            # Recuperer les IDs de la fenetre
            if use_date_filter and date_limit:
                await cursor.execute(f"""
                    SELECT id FROM {TABLE}
                    WHERE date_de_tirage >= %s
                    ORDER BY date_de_tirage DESC
                """, (date_limit,))
            elif window_used != "GLOBAL":
                await cursor.execute(f"""
                    SELECT id FROM {TABLE}
                    ORDER BY date_de_tirage DESC
                    LIMIT %s
                """, (int(window_used),))
            else:
                await cursor.execute(f"""
                    SELECT id FROM {TABLE}
                    ORDER BY date_de_tirage DESC
                """)
            window_ids = [row['id'] for row in await cursor.fetchall()]

            if not window_ids:
                raise Exception("Aucun tirage trouve")

            ids_placeholder = ','.join(['%s'] * len(window_ids))

            # Frequences boules sur la fenetre
            await cursor.execute(f"""
                SELECT num, COUNT(*) as freq FROM (
                    SELECT boule_1 as num FROM {TABLE} WHERE id IN ({ids_placeholder})
                    UNION ALL SELECT boule_2 FROM {TABLE} WHERE id IN ({ids_placeholder})
                    UNION ALL SELECT boule_3 FROM {TABLE} WHERE id IN ({ids_placeholder})
                    UNION ALL SELECT boule_4 FROM {TABLE} WHERE id IN ({ids_placeholder})
                    UNION ALL SELECT boule_5 FROM {TABLE} WHERE id IN ({ids_placeholder})
                ) t
                GROUP BY num
                ORDER BY num
            """, (*window_ids, *window_ids, *window_ids, *window_ids, *window_ids))
            freq_boules = {row['num']: row['freq'] for row in await cursor.fetchall()}

            # ── 2 derniers tirages pour penalisation ──
            await cursor.execute(f"""
                SELECT boule_1, boule_2, boule_3, boule_4, boule_5,
                       etoile_1, etoile_2, date_de_tirage
                FROM {TABLE}
                WHERE id IN ({ids_placeholder})
                ORDER BY date_de_tirage DESC
                LIMIT 2
            """, window_ids)
            recent_draws = await cursor.fetchall()

            if len(recent_draws) >= 2:
                last_draw_balls = {recent_draws[0][f'boule_{i}'] for i in range(1, 6)}
                second_last_balls = {recent_draws[1][f'boule_{i}'] for i in range(1, 6)}
                last_draw_stars = {recent_draws[0]['etoile_1'], recent_draws[0]['etoile_2']}
                second_last_stars = {recent_draws[1]['etoile_1'], recent_draws[1]['etoile_2']}
                last_draw_date = str(recent_draws[0]['date_de_tirage'])
                second_last_date = str(recent_draws[1]['date_de_tirage'])
            elif len(recent_draws) == 1:
                last_draw_balls = {recent_draws[0][f'boule_{i}'] for i in range(1, 6)}
                second_last_balls = set()
                last_draw_stars = {recent_draws[0]['etoile_1'], recent_draws[0]['etoile_2']}
                second_last_stars = set()
                last_draw_date = str(recent_draws[0]['date_de_tirage'])
                second_last_date = None
            else:
                last_draw_balls = set()
                second_last_balls = set()
                last_draw_stars = set()
                second_last_stars = set()
                last_draw_date = None
                second_last_date = None

            top_boules, penal_info_boules = compute_penalized_ranking(
                raw_freq=freq_boules,
                last_draw_numbers=last_draw_balls,
                second_last_draw_numbers=second_last_balls,
                num_range=range(1, 51),
                top_n=5,
            )

            # Frequences etoiles sur la fenetre
            await cursor.execute(f"""
                SELECT num, COUNT(*) as freq FROM (
                    SELECT etoile_1 as num FROM {TABLE} WHERE id IN ({ids_placeholder})
                    UNION ALL SELECT etoile_2 FROM {TABLE} WHERE id IN ({ids_placeholder})
                ) t
                GROUP BY num
                ORDER BY num
            """, (*window_ids, *window_ids))
            freq_etoiles = {row['num']: row['freq'] for row in await cursor.fetchall()}
            top_etoiles, penal_info_etoiles = compute_penalized_ranking(
                raw_freq=freq_etoiles,
                last_draw_numbers=last_draw_stars,
                second_last_draw_numbers=second_last_stars,
                num_range=range(1, 13),
                top_n=3,
            )

            # Dates de la fenetre
            await cursor.execute(f"""
                SELECT MIN(date_de_tirage) as min_date, MAX(date_de_tirage) as max_date
                FROM {TABLE}
                WHERE id IN ({ids_placeholder})
            """, window_ids)
            dates = await cursor.fetchone()
            date_min = dates['min_date']
            date_max = dates['max_date']

        # Texte d'analyse
        graph_labels_b = [str(n['number']) for n in top_boules]
        graph_values_b = [n['count'] for n in top_boules]
        graph_labels_e = [str(n['number']) for n in top_etoiles]
        graph_values_e = [n['count'] for n in top_etoiles]

        avg_freq_b = sum(graph_values_b) / len(graph_values_b) if graph_values_b else 0
        avg_freq_e = sum(graph_values_e) / len(graph_values_e) if graph_values_e else 0

        actual_count = len(window_ids)
        if mode_used == "annees" and years_used and years_used != "GLOBAL":
            window_label = f"{years_used} an(s) ({actual_count} tirages)"
        elif window_used != "GLOBAL":
            window_label = f"{actual_count} tirages"
        else:
            window_label = "l'intégralité de la base"

        analysis_text = (
            f"Analyse locale HYBRIDE EM sur {window_label} "
            f"({date_min} -> {date_max}). "
            f"Top 5 boules : {', '.join(graph_labels_b)} (freq moy {avg_freq_b:.1f}). "
            f"Top 3 etoiles : {', '.join(graph_labels_e)} (freq moy {avg_freq_e:.1f}). "
            f"Aucun biais algorithmique détecté."
        )

        return {
            "success": True,
            "rows_used": actual_count,
            "is_global": window_used == "GLOBAL",
            "graph_boules": {
                "labels": graph_labels_b,
                "values": graph_values_b
            },
            "graph_etoiles": {
                "labels": graph_labels_e,
                "values": graph_values_e
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
                "source": "HYBRIDE_LOCAL_EM",
                "penalization": {
                    "last_draw_date": last_draw_date,
                    "second_last_draw_date": second_last_date,
                    "boules": penal_info_boules,
                    "etoiles": penal_info_etoiles,
                }
            }
        }

    except Exception as e:
        logger.error(f"Erreur /api/euromillions/meta-analyse-local: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "graph_boules": None,
            "graph_etoiles": None,
            "analysis": None,
            "pdf": False,
            "meta": {"source": "ERROR", "error": "Erreur interne lors de l'analyse"}
        })


# =========================
# META ANALYSE Texte Gemini EM
# =========================

@router.post("/meta-analyse-texte")
@limiter.limit("10/minute")
async def em_meta_analyse_texte(request: Request, payload: EMMetaAnalyseTextePayload):
    """Enrichit le texte d'analyse local EuroMillions via Gemini."""
    from services.em_gemini import enrich_analysis_em
    return await enrich_analysis_em(
        analysis_local=payload.analysis_local,
        window=payload.window or "GLOBAL",
        http_client=request.app.state.httpx_client
    )


# =========================
# META PDF EM
# =========================

@router.post("/meta-pdf")
@limiter.limit("10/minute")
async def em_meta_pdf(request: Request, payload: EMMetaPdfPayload):
    """Genere le PDF officiel META75 EuroMillions via ReportLab."""
    from services.em_pdf_generator import generate_em_meta_pdf

    try:
        logger.info(f"[META-PDF-EM ROUTE] graph_data_boules: {type(payload.graph_data_boules).__name__}, "
                     f"graph_data_etoiles: {type(payload.graph_data_etoiles).__name__}")

        buf = generate_em_meta_pdf(
            analysis=payload.analysis,
            window=payload.window,
            engine=payload.engine,
            graph=payload.graph,
            graph_data_boules=payload.graph_data_boules,
            graph_data_etoiles=payload.graph_data_etoiles,
            sponsor=payload.sponsor
        )
        return StreamingResponse(
            buf,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline; filename=meta75_em_report.pdf"}
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab non installe")
    except Exception as e:
        logger.error(f"[META-PDF-EM] Erreur generation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur generation PDF EM")


# =========================
# Analyse Grille Custom EM
# =========================

@router.post("/analyze-custom-grid")
@limiter.limit("60/minute")
async def em_analyze_custom_grid(
    request: Request,
    nums: list = Query(..., description="5 numeros principaux (1-50)"),
    etoile1: int = Query(..., ge=1, le=12, description="Etoile 1"),
    etoile2: int = Query(..., ge=1, le=12, description="Etoile 2")
):
    """
    Analyse une grille EuroMillions personnalisee.
    Retourne un score, des badges et des suggestions.
    """
    try:
        # Validation
        if len(nums) != 5:
            return {"success": False, "error": "5 numéros requis"}

        nums = [int(n) for n in nums]
        if not all(1 <= n <= 50 for n in nums):
            return {"success": False, "error": "Numéros doivent être entre 1 et 50"}
        if len(set(nums)) != 5:
            return {"success": False, "error": "Numéros doivent être uniques"}

        if etoile1 == etoile2:
            return {"success": False, "error": "Les 2 étoiles doivent être différentes"}

        nums = sorted(nums)
        etoiles = sorted([etoile1, etoile2])

        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()

            await cursor.execute(f"SELECT COUNT(*) as total FROM {TABLE}")
            total_tirages = (await cursor.fetchone())['total']

            # Frequences des boules selectionnees
            await cursor.execute(f"""
                SELECT num, COUNT(*) as freq FROM (
                    SELECT boule_1 as num FROM {TABLE}
                    UNION ALL SELECT boule_2 FROM {TABLE}
                    UNION ALL SELECT boule_3 FROM {TABLE}
                    UNION ALL SELECT boule_4 FROM {TABLE}
                    UNION ALL SELECT boule_5 FROM {TABLE}
                ) t
                WHERE num IN (%s, %s, %s, %s, %s)
                GROUP BY num
            """, tuple(nums))
            freq_map = {row['num']: row['freq'] for row in await cursor.fetchall()}
            frequencies = [freq_map.get(num, 0) for num in nums]

            # Correspondance exacte (5 boules + 2 etoiles)
            # Utilise IN pour etre independant de l'ordre de stockage en BDD
            await cursor.execute(f"""
                SELECT date_de_tirage
                FROM {TABLE}
                WHERE boule_1 IN (%s, %s, %s, %s, %s)
                  AND boule_2 IN (%s, %s, %s, %s, %s)
                  AND boule_3 IN (%s, %s, %s, %s, %s)
                  AND boule_4 IN (%s, %s, %s, %s, %s)
                  AND boule_5 IN (%s, %s, %s, %s, %s)
                  AND etoile_1 IN (%s, %s)
                  AND etoile_2 IN (%s, %s)
                ORDER BY date_de_tirage DESC
            """, (*nums, *nums, *nums, *nums, *nums, *etoiles, *etoiles))
            exact_matches = await cursor.fetchall()
            exact_dates = [str(row['date_de_tirage']) for row in exact_matches]

            # Meilleure correspondance boules
            await cursor.execute(f"""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                       etoile_1, etoile_2,
                    (
                        (boule_1 IN (%s, %s, %s, %s, %s)) +
                        (boule_2 IN (%s, %s, %s, %s, %s)) +
                        (boule_3 IN (%s, %s, %s, %s, %s)) +
                        (boule_4 IN (%s, %s, %s, %s, %s)) +
                        (boule_5 IN (%s, %s, %s, %s, %s))
                    ) AS match_count,
                    (
                        (etoile_1 IN (%s, %s)) +
                        (etoile_2 IN (%s, %s))
                    ) AS etoile_match
                FROM {TABLE}
                ORDER BY match_count DESC, etoile_match DESC, date_de_tirage DESC
                LIMIT 1
            """, (*nums, *nums, *nums, *nums, *nums, *etoiles, *etoiles))
            best_match = await cursor.fetchone()

        best_match_numbers = []
        best_match_etoiles = []
        if best_match:
            # Cast int() pour garantir la coherence de type (BDD peut renvoyer str/Decimal)
            tirage_nums = [int(best_match['boule_1']), int(best_match['boule_2']),
                           int(best_match['boule_3']), int(best_match['boule_4']),
                           int(best_match['boule_5'])]
            best_match_numbers = sorted([n for n in nums if n in tirage_nums])
            tirage_etoiles = [int(best_match['etoile_1']), int(best_match['etoile_2'])]
            best_match_etoiles = sorted([e for e in etoiles if e in tirage_etoiles])

        # Source unique de verite : intersection Python (pas le match_count SQL)
        history_check = {
            "exact_match": len(exact_dates) > 0,
            "exact_dates": exact_dates,
            "best_match_count": len(best_match_numbers),
            "best_match_etoiles": len(best_match_etoiles),
            "best_match_date": str(best_match['date_de_tirage']) if best_match else None,
            "best_match_numbers": best_match_numbers,
            "best_match_etoiles_list": best_match_etoiles
        }

        # Metriques de la grille
        nb_pairs = sum(1 for n in nums if n % 2 == 0)
        nb_impairs = 5 - nb_pairs
        nb_bas = sum(1 for n in nums if n <= 25)
        nb_hauts = 5 - nb_bas
        somme = sum(nums)
        dispersion = max(nums) - min(nums)

        nums_sorted = sorted(nums)
        suites = sum(1 for i in range(4) if nums_sorted[i + 1] - nums_sorted[i] == 1)

        # Plus long run consecutif
        max_run = 1
        current_run = 1
        for i in range(4):
            if nums_sorted[i + 1] - nums_sorted[i] == 1:
                current_run += 1
                if current_run > max_run:
                    max_run = current_run
            else:
                current_run = 1

        # Score de conformite avec penalites graduelles
        score_conformite = 100

        if nb_pairs == 0 or nb_pairs == 5:
            score_conformite -= 25
        elif nb_pairs == 1 or nb_pairs == 4:
            score_conformite -= 10

        if nb_bas == 0 or nb_bas == 5:
            score_conformite -= 25
        elif nb_bas == 1 or nb_bas == 4:
            score_conformite -= 8

        if somme < 55:
            score_conformite -= 35
        elif somme < 75:
            score_conformite -= 20
        elif somme > 210:
            score_conformite -= 35
        elif somme > 175:
            score_conformite -= 20

        if dispersion < 10:
            score_conformite -= 35
        elif dispersion < 15:
            score_conformite -= 20

        if max_run >= 5:
            score_conformite -= 30
        elif max_run >= 4:
            score_conformite -= 20
        elif max_run >= 3:
            score_conformite -= 10

        score_conformite = max(0, score_conformite)

        freq_moyenne = sum(frequencies) / 5
        freq_max_theorique = total_tirages * 5 / 50
        score_freq = min(100, (freq_moyenne / freq_max_theorique) * 100)

        score = int(0.6 * score_conformite + 0.4 * score_freq)
        score = max(0, min(100, score))

        # Badges
        badges = []
        if freq_moyenne > freq_max_theorique * 1.1:
            badges.append("Numéros chauds")
        elif freq_moyenne < freq_max_theorique * 0.9:
            badges.append("Mix de retards")
        else:
            badges.append("Équilibre")
        if dispersion > 35:
            badges.append("Large spectre")
        if nb_pairs == 2 or nb_pairs == 3:
            badges.append("Pair/Impair OK")
        badges.append("Analyse personnalisée EM")

        # Detection conditions critiques
        critical_count = 0
        critical_flags = {}

        if max_run >= 4:
            critical_count += 1
            critical_flags['suite'] = max_run
        if somme < 55 or somme > 210:
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

        if critical_count >= 3:
            severity = 3
        elif critical_count >= 2 or (critical_count == 1 and max_run >= 4):
            severity = 2
        else:
            severity = 1

        # Suggestions
        suggestions = []
        alert_message = None

        if severity == 3:
            alert_message = "Alerte maximale : cette grille cumule TOUS les défauts statistiques !"
            if 'suite' in critical_flags:
                suggestions.append(f"Suite parfaite détectée ! En {total_tirages} tirages EM, aucune suite de {max_run} consécutifs n'est jamais sortie")
            if 'somme' in critical_flags:
                suggestions.append(f"Somme catastrophique ({somme}) — les tirages EM oscillent entre 80 et 175")
            if 'bas_haut' in critical_flags:
                if nb_bas == 5:
                    suggestions.append("ZERO numéro au-dessus de 25 — statistiquement aberrant")
                else:
                    suggestions.append("ZERO numéro en dessous de 26 — statistiquement aberrant")
            if 'dispersion' in critical_flags:
                suggestions.append(f"Dispersion quasi nulle ({dispersion}) — la moyenne historique est autour de 30+")
            if 'pairs' in critical_flags:
                if nb_pairs == 5:
                    suggestions.append("100% de numéros pairs — aucun tirage historique n'a cette configuration")
                else:
                    suggestions.append("100% de numéros impairs — aucun tirage historique n'a cette configuration")
            if 'conformite' in critical_flags:
                suggestions.append(f"Score de conformité effondré ({score_conformite}%) — cette grille défie toutes les statistiques")

        elif severity == 2:
            if 'suite' in critical_flags:
                suggestions.append(f"Suite de {max_run} numéros consécutifs détectée — très rare dans les tirages réels")
            if nb_pairs == 0 or nb_pairs == 5:
                suggestions.append(f"Déséquilibre pair/impair ({nb_pairs}/{nb_impairs}) — viser 2-3 pairs")
            if nb_bas == 0 or nb_bas == 5:
                suggestions.append(f"Déséquilibre bas/haut ({nb_bas}/{nb_hauts}) — mixer numéros bas (1-25) et hauts (26-50)")
            if somme < 55 or somme > 210:
                suggestions.append(f"Somme trop {'basse' if somme < 55 else 'élevée'} ({somme}) — la moyenne historique est autour de 127")
            elif somme < 75 or somme > 175:
                suggestions.append(f"Somme {'basse' if somme < 75 else 'élevée'} ({somme}) — viser la fourchette 85-175")
            if dispersion < 10:
                suggestions.append(f"Dispersion insuffisante ({dispersion}) — vos numéros couvrent seulement {dispersion} unités sur 49 possibles")
            elif dispersion < 15:
                suggestions.append(f"Dispersion faible ({dispersion}) — élargir l'écart entre vos numéros")
            if max_run >= 3 and 'suite' not in critical_flags:
                suggestions.append(f"Suite de {max_run} consécutifs — réduire les numéros qui se suivent")

        else:
            if score >= 70:
                suggestions.append("Excellent équilibre dans votre sélection")
            if nb_pairs == 1 or nb_pairs == 4:
                suggestions.append("Pensez à varier pairs et impairs (2-3 pairs idéal)")
            if nb_bas == 1 or nb_bas == 4:
                suggestions.append("Mixer numéros bas (1-25) et hauts (26-50)")
            if 75 <= somme < 85:
                suggestions.append("Somme un peu basse, ajouter un numéro plus élevé")
            elif 165 < somme <= 175:
                suggestions.append("Somme un peu élevée, ajouter un numéro plus bas")
            if 15 <= dispersion < 20:
                suggestions.append("Élargir légèrement la dispersion de vos numéros")
            if max_run == 3:
                suggestions.append("Attention à la suite de 3 consécutifs")
            elif suites >= 2 and max_run < 3:
                suggestions.append("Quelques numéros consécutifs — pensez à les espacer")

        if not suggestions:
            suggestions.append("Grille bien équilibrée")

        if score >= 80:
            comparaison = "Meilleure que 85% des grilles aléatoires"
        elif score >= 60:
            comparaison = "Meilleure que 60% des grilles aléatoires"
        elif score >= 40:
            comparaison = "Dans la moyenne des grilles"
        else:
            comparaison = "En dessous de la moyenne"

        return {
            "success": True,
            "nums": nums,
            "etoiles": etoiles,
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

    except Exception as e:
        logger.error(f"Erreur /api/euromillions/analyze-custom-grid: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "error": "Erreur interne lors de l'analyse"
        })
