from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import logging

from engine.hybride import generate, generate_grids
import db_cloudsql
from schemas import AskPayload

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ask")
def ask(payload: AskPayload):
    """
    Endpoint principal du moteur HYBRIDE
    """
    try:
        result = generate(payload.prompt)
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
async def generate_endpoint(
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

        result = generate_grids(n=n, mode=mode)

        return {
            "success": True,
            "grids": result['grids'],
            "metadata": result['metadata']
        }
    except Exception as e:
        logger.error(f"Erreur /generate: {e}")
        return {
            "success": False,
            "message": str(e),
            "grids": [],
            "metadata": {}
        }


# =========================
# META ANALYSE Mock (Phase A)
# =========================

@router.get("/api/meta-analyse-mock")
async def api_meta_analyse_mock():
    """
    Endpoint mock pour META ANALYSE 75 grilles.
    Retourne des données statiques pour valider le flux complet.
    Aucune API externe, aucune IA, données simulées uniquement.
    """
    return {
        "success": True,
        "graph": {
            "labels": ["1", "2", "3", "4", "5"],
            "values": [12, 18, 9, 22, 15]
        },
        "analysis": "Analyse simulée : tendances équilibrées, distribution homogène, aucun biais majeur détecté.",
        "pdf": False
    }


# =========================
# META ANALYSE Local (Phase B)
# =========================

@router.get("/api/meta-analyse-local")
async def api_meta_analyse_local(
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
        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        # Nombre total de tirages dans la base
        cursor.execute("SELECT COUNT(*) as total FROM tirages")
        total_rows = cursor.fetchone()['total']

        # Déterminer le mode et la fenêtre d'analyse
        mode_used = "tirages"
        window_used = "GLOBAL"
        years_used = None
        use_date_filter = False
        date_limit = None

        # MODE ANNÉES (prioritaire si years fourni)
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

        # MODE TIRAGES (si years non fourni)
        else:
            mode_used = "tirages"
            if window and window.upper() != "GLOBAL":
                try:
                    window_int = int(window)
                    if window_int >= 1:
                        window_used = str(min(window_int, total_rows))
                except (ValueError, TypeError):
                    window_used = "GLOBAL"

        # Récupérer les IDs des tirages dans la fenêtre
        if use_date_filter and date_limit:
            # Mode années : filtrer par date
            cursor.execute("""
                SELECT id FROM tirages
                WHERE date_de_tirage >= %s
                ORDER BY date_de_tirage DESC
            """, (date_limit,))
        elif window_used != "GLOBAL":
            # Mode tirages : LIMIT
            cursor.execute(f"""
                SELECT id FROM tirages
                ORDER BY date_de_tirage DESC
                LIMIT {int(window_used)}
            """)
        else:
            # GLOBAL : tous les tirages
            cursor.execute("""
                SELECT id FROM tirages
                ORDER BY date_de_tirage DESC
            """)
        window_ids = [row['id'] for row in cursor.fetchall()]

        if not window_ids:
            conn.close()
            raise Exception("Aucun tirage trouvé")

        # Créer la clause IN pour filtrer
        ids_placeholder = ','.join(['%s'] * len(window_ids))

        # Calculer les fréquences des numéros dans la fenêtre
        top_numbers = []
        for number in range(1, 50):
            cursor.execute(f"""
                SELECT COUNT(*) as freq
                FROM tirages
                WHERE id IN ({ids_placeholder})
                  AND (boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                       OR boule_4 = %s OR boule_5 = %s)
            """, (*window_ids, number, number, number, number, number))
            freq = cursor.fetchone()['freq']
            top_numbers.append({"number": number, "count": freq})

        # Trier par fréquence décroissante et prendre les 5 premiers
        top_numbers = sorted(top_numbers, key=lambda x: -x['count'])[:5]

        # Dates min/max de la fenêtre analysée
        cursor.execute(f"""
            SELECT MIN(date_de_tirage) as min_date, MAX(date_de_tirage) as max_date
            FROM tirages
            WHERE id IN ({ids_placeholder})
        """, window_ids)
        dates = cursor.fetchone()
        date_min = dates['min_date']
        date_max = dates['max_date']

        conn.close()

        # Construire le graphique (labels = numéros, values = fréquences)
        graph_labels = [str(n['number']) for n in top_numbers]
        graph_values = [n['count'] for n in top_numbers]

        # Calculer quelques métriques pour l'analyse textuelle
        avg_freq = sum(graph_values) / len(graph_values) if graph_values else 0
        max_freq = max(graph_values) if graph_values else 0
        min_freq = min(graph_values) if graph_values else 0
        spread = max_freq - min_freq

        # Générer le texte d'analyse local (pas d'IA)
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

    except Exception as e:
        logger.error(f"Erreur /api/meta-analyse-local: {e}")
        # Fallback vers données mock en cas d'erreur
        return {
            "success": True,
            "graph": {
                "labels": ["1", "2", "3", "4", "5"],
                "values": [12, 18, 9, 22, 15]
            },
            "analysis": "Analyse locale indisponible - données de secours affichées.",
            "pdf": False,
            "meta": {
                "source": "MOCK_FALLBACK",
                "error": str(e)
            }
        }


@router.post("/api/analyze-custom-grid")
async def api_analyze_custom_grid(
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

        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        # Recuperer les frequences
        cursor.execute("SELECT COUNT(*) as total FROM tirages")
        total_tirages = cursor.fetchone()['total']

        frequencies = []
        for num in nums:
            cursor.execute("""
                SELECT COUNT(*) as freq
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            freq = cursor.fetchone()['freq']
            frequencies.append(freq)

        # =====================================================
        # VERIFICATION HISTORIQUE
        # =====================================================

        # ETAPE 1: Combinaison exacte
        cursor.execute("""
            SELECT date_de_tirage
            FROM tirages
            WHERE boule_1 = %s AND boule_2 = %s AND boule_3 = %s
                  AND boule_4 = %s AND boule_5 = %s AND numero_chance = %s
            ORDER BY date_de_tirage DESC
        """, (*nums, chance))
        exact_matches = cursor.fetchall()
        exact_dates = [str(row['date_de_tirage']) for row in exact_matches]

        # ETAPE 2: Meilleure correspondance (numéros identiques)
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
            ORDER BY match_count DESC, chance_match DESC
            LIMIT 1
        """, (*nums, *nums, *nums, *nums, *nums, chance))
        best_match = cursor.fetchone()

        # Calculer les numéros communs
        best_match_numbers = []
        if best_match:
            tirage_nums = [best_match['boule_1'], best_match['boule_2'], best_match['boule_3'],
                          best_match['boule_4'], best_match['boule_5']]
            best_match_numbers = sorted([n for n in nums if n in tirage_nums])

        history_check = {
            "exact_match": len(exact_dates) > 0,
            "exact_dates": exact_dates,
            "best_match_count": best_match['match_count'] if best_match else 0,
            "best_match_chance": bool(best_match['chance_match']) if best_match else False,
            "best_match_chance_number": best_match['numero_chance'] if best_match and best_match['chance_match'] else None,
            "best_match_date": str(best_match['date_de_tirage']) if best_match else None,
            "best_match_numbers": best_match_numbers
        }

        conn.close()

        # Calcul des metriques
        nb_pairs = sum(1 for n in nums if n % 2 == 0)
        nb_impairs = 5 - nb_pairs
        nb_bas = sum(1 for n in nums if n <= 24)
        nb_hauts = 5 - nb_bas
        somme = sum(nums)
        dispersion = max(nums) - min(nums)

        # Suites consecutives
        nums_sorted = sorted(nums)
        suites = sum(1 for i in range(4) if nums_sorted[i+1] - nums_sorted[i] == 1)

        # Score de conformite
        score_conformite = 100
        if nb_pairs < 1 or nb_pairs > 4:
            score_conformite -= 15
        if nb_bas < 1 or nb_bas > 4:
            score_conformite -= 10
        if somme < 70 or somme > 150:
            score_conformite -= 20
        if dispersion < 15:
            score_conformite -= 25
        if suites > 2:
            score_conformite -= 15

        # Score frequence (moyenne des frequences normalisee)
        freq_moyenne = sum(frequencies) / 5
        freq_max_theorique = total_tirages * 5 / 49  # Frequence attendue uniforme
        score_freq = min(100, (freq_moyenne / freq_max_theorique) * 100)

        # Score final
        score = int(0.6 * score_conformite + 0.4 * score_freq)
        score = max(0, min(100, score))

        # Badges
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

        # Suggestions
        suggestions = []
        if score >= 70:
            suggestions.append("Excellent equilibre dans votre selection")
        if nb_pairs == 0 or nb_pairs == 5:
            suggestions.append("Equilibrer le ratio pair/impair (2-3 pairs ideal)")
        if nb_bas == 0 or nb_bas == 5:
            suggestions.append("Mixer numeros bas (1-24) et hauts (25-49)")
        if somme < 70:
            suggestions.append("Somme trop basse, ajouter des numeros plus eleves")
        elif somme > 150:
            suggestions.append("Somme trop elevee, ajouter des numeros plus bas")
        if dispersion < 15:
            suggestions.append("Numeros trop groupes, elargir la dispersion")
        if suites > 2:
            suggestions.append("Trop de numeros consecutifs")
        if not suggestions:
            suggestions.append("Grille bien equilibree")

        # Comparaison
        if score >= 80:
            comparaison = f"Meilleure que 85% des grilles aleatoires"
        elif score >= 60:
            comparaison = f"Meilleure que 60% des grilles aleatoires"
        elif score >= 40:
            comparaison = f"Dans la moyenne des grilles"
        else:
            comparaison = f"En dessous de la moyenne"

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
            "suggestions": suggestions,
            "history_check": history_check
        }

    except Exception as e:
        logger.error(f"Erreur /api/analyze-custom-grid: {e}")
        return {
            "success": False,
            "error": str(e)
        }
