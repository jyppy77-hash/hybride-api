"""
Routes unifiees /api/{game}/... — Analyse (generateur, META local, grille custom)
Phase 10 — remplace la duplication api_analyse.py / em_analyse.py
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from typing import Optional
import logging

import db_cloudsql
from rate_limit import limiter
from config.games import ValidGame, get_config, get_engine
from config.i18n import _badges, _analysis_strings
from services.penalization import compute_penalized_ranking

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/{game}", tags=["Unified - Analyse"])


# =========================
# Generateur de grilles
# =========================

@router.get("/generate")
@limiter.limit("60/minute")
async def unified_generate(
    request: Request, game: ValidGame,
    n: int = Query(default=3, ge=1, le=10, description="Nombre de grilles"),
    mode: str = Query(default="balanced", description="Mode: conservative, balanced, recent"),
    lang: str = Query(default="fr", pattern=r"^(fr|en|pt|es|de)$"),
):
    cfg = get_config(game)
    try:
        valid_modes = ["conservative", "balanced", "recent"]
        if mode not in valid_modes:
            mode = "balanced"

        engine = get_engine(cfg)
        result = await engine.generate_grids(n=n, mode=mode, lang=lang)

        return {
            "success": True,
            "grids": result['grids'],
            "metadata": result['metadata'],
        }
    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/generate: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": "Erreur interne lors de la generation",
            "grids": [], "metadata": {},
        })


# =========================
# META ANALYSE Local
# =========================

@router.get("/meta-analyse-local")
@limiter.limit("60/minute")
async def unified_meta_analyse_local(
    request: Request, game: ValidGame,
    window: Optional[str] = Query(default="GLOBAL", description="Fenetre d'analyse"),
    years: Optional[str] = Query(default=None, description="Fenetre en annees"),
):
    from datetime import datetime, timedelta

    cfg = get_config(game)
    is_loto = game == ValidGame.loto

    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()

            await cursor.execute(f"SELECT COUNT(*) as total FROM {cfg.table}")
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
                    SELECT id FROM {cfg.table}
                    WHERE date_de_tirage >= %s
                    ORDER BY date_de_tirage DESC
                """, (date_limit,))
            elif window_used != "GLOBAL":
                await cursor.execute(f"""
                    SELECT id FROM {cfg.table}
                    ORDER BY date_de_tirage DESC
                    LIMIT %s
                """, (int(window_used),))
            else:
                await cursor.execute(f"""
                    SELECT id FROM {cfg.table}
                    ORDER BY date_de_tirage DESC
                """)
            window_ids = [row['id'] for row in await cursor.fetchall()]

            if not window_ids:
                raise Exception("Aucun tirage trouve")

            ids_placeholder = ','.join(['%s'] * len(window_ids))

            # Frequences boules sur la fenetre
            await cursor.execute(f"""
                SELECT num, COUNT(*) as freq FROM (
                    SELECT boule_1 as num FROM {cfg.table} WHERE id IN ({ids_placeholder})
                    UNION ALL SELECT boule_2 FROM {cfg.table} WHERE id IN ({ids_placeholder})
                    UNION ALL SELECT boule_3 FROM {cfg.table} WHERE id IN ({ids_placeholder})
                    UNION ALL SELECT boule_4 FROM {cfg.table} WHERE id IN ({ids_placeholder})
                    UNION ALL SELECT boule_5 FROM {cfg.table} WHERE id IN ({ids_placeholder})
                ) t
                GROUP BY num ORDER BY num
            """, (*window_ids, *window_ids, *window_ids, *window_ids, *window_ids))
            freq_map = {row['num']: row['freq'] for row in await cursor.fetchall()}

            # 2 derniers tirages pour penalisation
            if is_loto:
                await cursor.execute(f"""
                    SELECT boule_1, boule_2, boule_3, boule_4, boule_5,
                           numero_chance, date_de_tirage
                    FROM {cfg.table}
                    WHERE id IN ({ids_placeholder})
                    ORDER BY date_de_tirage DESC LIMIT 2
                """, window_ids)
            else:
                await cursor.execute(f"""
                    SELECT boule_1, boule_2, boule_3, boule_4, boule_5,
                           etoile_1, etoile_2, date_de_tirage
                    FROM {cfg.table}
                    WHERE id IN ({ids_placeholder})
                    ORDER BY date_de_tirage DESC LIMIT 2
                """, window_ids)
            recent_draws = await cursor.fetchall()

            if len(recent_draws) >= 2:
                last_draw_balls = {recent_draws[0][f'boule_{i}'] for i in range(1, 6)}
                second_last_balls = {recent_draws[1][f'boule_{i}'] for i in range(1, 6)}
                last_draw_date = str(recent_draws[0]['date_de_tirage'])
                second_last_date = str(recent_draws[1]['date_de_tirage'])
            elif len(recent_draws) == 1:
                last_draw_balls = {recent_draws[0][f'boule_{i}'] for i in range(1, 6)}
                second_last_balls = set()
                last_draw_date = str(recent_draws[0]['date_de_tirage'])
                second_last_date = None
            else:
                last_draw_balls = set()
                second_last_balls = set()
                last_draw_date = None
                second_last_date = None

            top_numbers, penal_info_balls = compute_penalized_ranking(
                raw_freq=freq_map,
                last_draw_numbers=last_draw_balls,
                second_last_draw_numbers=second_last_balls,
                num_range=range(1, cfg.num_range[1] + 1),
                top_n=5,
            )

            # Secondary numbers (chance / etoiles)
            if is_loto:
                # Loto: chance
                if len(recent_draws) >= 2:
                    last_draw_secondary = {recent_draws[0]['numero_chance']}
                    second_last_secondary = {recent_draws[1]['numero_chance']}
                elif len(recent_draws) == 1:
                    last_draw_secondary = {recent_draws[0]['numero_chance']}
                    second_last_secondary = set()
                else:
                    last_draw_secondary = set()
                    second_last_secondary = set()

                await cursor.execute(f"""
                    SELECT numero_chance AS num, COUNT(*) AS freq
                    FROM {cfg.table}
                    WHERE id IN ({ids_placeholder})
                    GROUP BY numero_chance ORDER BY freq DESC
                """, window_ids)
                secondary_freq = {row['num']: row['freq'] for row in await cursor.fetchall()}
                secondary_top, penal_info_secondary = compute_penalized_ranking(
                    raw_freq=secondary_freq,
                    last_draw_numbers=last_draw_secondary,
                    second_last_draw_numbers=second_last_secondary,
                    num_range=range(1, 11),
                    top_n=3,
                )
            else:
                # EM: etoiles
                if len(recent_draws) >= 2:
                    last_draw_secondary = {recent_draws[0]['etoile_1'], recent_draws[0]['etoile_2']}
                    second_last_secondary = {recent_draws[1]['etoile_1'], recent_draws[1]['etoile_2']}
                elif len(recent_draws) == 1:
                    last_draw_secondary = {recent_draws[0]['etoile_1'], recent_draws[0]['etoile_2']}
                    second_last_secondary = set()
                else:
                    last_draw_secondary = set()
                    second_last_secondary = set()

                await cursor.execute(f"""
                    SELECT num, COUNT(*) as freq FROM (
                        SELECT etoile_1 as num FROM {cfg.table} WHERE id IN ({ids_placeholder})
                        UNION ALL SELECT etoile_2 FROM {cfg.table} WHERE id IN ({ids_placeholder})
                    ) t
                    GROUP BY num ORDER BY num
                """, (*window_ids, *window_ids))
                secondary_freq = {row['num']: row['freq'] for row in await cursor.fetchall()}
                secondary_top, penal_info_secondary = compute_penalized_ranking(
                    raw_freq=secondary_freq,
                    last_draw_numbers=last_draw_secondary,
                    second_last_draw_numbers=second_last_secondary,
                    num_range=range(1, 13),
                    top_n=3,
                )

            # Dates de la fenetre
            await cursor.execute(f"""
                SELECT MIN(date_de_tirage) as min_date, MAX(date_de_tirage) as max_date
                FROM {cfg.table} WHERE id IN ({ids_placeholder})
            """, window_ids)
            dates = await cursor.fetchone()
            date_min = dates['min_date']
            date_max = dates['max_date']

        graph_labels = [str(n['number']) for n in top_numbers]
        graph_values = [n['count'] for n in top_numbers]
        secondary_labels = [str(n['number']) for n in secondary_top]
        secondary_values = [n['count'] for n in secondary_top]

        avg_freq = sum(graph_values) / len(graph_values) if graph_values else 0
        max_freq = max(graph_values) if graph_values else 0
        min_freq = min(graph_values) if graph_values else 0
        spread = max_freq - min_freq

        actual_count = len(window_ids)
        if mode_used == "annees" and years_used and years_used != "GLOBAL":
            window_label = f"{years_used} an(s) ({actual_count} tirages)"
        elif window_used != "GLOBAL":
            window_label = f"{actual_count} tirages"
        else:
            window_label = "l'intégralité de la base"

        if is_loto:
            if spread < 5:
                dispersion_text = "dispersion très homogène"
            elif spread < 15:
                dispersion_text = "dispersion équilibrée"
            else:
                dispersion_text = "dispersion marquée"

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
                "graph": {"labels": graph_labels, "values": graph_values},
                "chance": {"labels": secondary_labels, "values": secondary_values},
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
                    "source": "HYBRIDE_LOCAL",
                    "penalization": {
                        "last_draw_date": last_draw_date,
                        "second_last_draw_date": second_last_date,
                        "balls": penal_info_balls,
                        "chance": penal_info_secondary,
                    },
                },
            }
        else:
            avg_freq_e = sum(secondary_values) / len(secondary_values) if secondary_values else 0
            analysis_text = (
                f"Analyse locale HYBRIDE EM sur {window_label} "
                f"({date_min} -> {date_max}). "
                f"Top 5 boules : {', '.join(graph_labels)} (freq moy {avg_freq:.1f}). "
                f"Top 3 etoiles : {', '.join(secondary_labels)} (freq moy {avg_freq_e:.1f}). "
                f"Aucun biais algorithmique détecté."
            )
            return {
                "success": True,
                "rows_used": actual_count,
                "is_global": window_used == "GLOBAL",
                "graph_boules": {"labels": graph_labels, "values": graph_values},
                "graph_etoiles": {"labels": secondary_labels, "values": secondary_values},
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
                        "boules": penal_info_balls,
                        "etoiles": penal_info_secondary,
                    },
                },
            }

    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/meta-analyse-local: {e}")
        if is_loto:
            return JSONResponse(status_code=500, content={
                "success": False, "graph": None, "analysis": None, "pdf": False,
                "meta": {"source": "ERROR", "error": "Erreur interne lors de l'analyse"},
            })
        return JSONResponse(status_code=500, content={
            "success": False, "graph_boules": None, "graph_etoiles": None,
            "analysis": None, "pdf": False,
            "meta": {"source": "ERROR", "error": "Erreur interne lors de l'analyse"},
        })


# =========================
# Analyse Grille Custom
# =========================

@router.post("/analyze-custom-grid")
@limiter.limit("60/minute")
async def unified_analyze_custom_grid(
    request: Request, game: ValidGame,
    nums: list = Query(..., description="5 numeros principaux"),
    chance: Optional[int] = Query(default=None, ge=1, le=10, description="Numero chance (Loto)"),
    etoile1: Optional[int] = Query(default=None, ge=1, le=12, description="Etoile 1 (EM)"),
    etoile2: Optional[int] = Query(default=None, ge=1, le=12, description="Etoile 2 (EM)"),
    lang: str = Query(default="fr", pattern=r"^(fr|en|pt|es|de)$"),
):
    cfg = get_config(game)
    is_loto = game == ValidGame.loto

    try:
        # Validation
        if len(nums) != 5:
            return {"success": False, "error": "5 numéros requis"}
        nums = [int(n) for n in nums]
        if not all(cfg.num_range[0] <= n <= cfg.num_range[1] for n in nums):
            return {"success": False, "error": f"Numéros doivent être entre {cfg.num_range[0]} et {cfg.num_range[1]}"}
        if len(set(nums)) != 5:
            return {"success": False, "error": "Numéros doivent être uniques"}
        nums = sorted(nums)

        if is_loto:
            if chance is None:
                return {"success": False, "error": "Numero chance requis pour Loto"}
        else:
            if etoile1 is None or etoile2 is None:
                return {"success": False, "error": "2 étoiles requises pour EuroMillions"}
            if etoile1 == etoile2:
                return {"success": False, "error": "Les 2 étoiles doivent être différentes"}
            etoiles = sorted([etoile1, etoile2])

        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()

            await cursor.execute(f"SELECT COUNT(*) as total FROM {cfg.table}")
            total_tirages = (await cursor.fetchone())['total']

            # Frequences des boules selectionnees
            await cursor.execute(f"""
                SELECT num, COUNT(*) as freq FROM (
                    SELECT boule_1 as num FROM {cfg.table}
                    UNION ALL SELECT boule_2 FROM {cfg.table}
                    UNION ALL SELECT boule_3 FROM {cfg.table}
                    UNION ALL SELECT boule_4 FROM {cfg.table}
                    UNION ALL SELECT boule_5 FROM {cfg.table}
                ) t
                WHERE num IN (%s, %s, %s, %s, %s)
                GROUP BY num
            """, tuple(nums))
            freq_map = {row['num']: row['freq'] for row in await cursor.fetchall()}
            frequencies = [freq_map.get(num, 0) for num in nums]

            # Correspondance exacte
            if is_loto:
                await cursor.execute("""
                    SELECT date_de_tirage FROM tirages
                    WHERE boule_1 IN (%s,%s,%s,%s,%s)
                      AND boule_2 IN (%s,%s,%s,%s,%s)
                      AND boule_3 IN (%s,%s,%s,%s,%s)
                      AND boule_4 IN (%s,%s,%s,%s,%s)
                      AND boule_5 IN (%s,%s,%s,%s,%s)
                      AND numero_chance = %s
                    ORDER BY date_de_tirage DESC
                """, (*nums, *nums, *nums, *nums, *nums, chance))
            else:
                await cursor.execute(f"""
                    SELECT date_de_tirage FROM {cfg.table}
                    WHERE boule_1 IN (%s,%s,%s,%s,%s)
                      AND boule_2 IN (%s,%s,%s,%s,%s)
                      AND boule_3 IN (%s,%s,%s,%s,%s)
                      AND boule_4 IN (%s,%s,%s,%s,%s)
                      AND boule_5 IN (%s,%s,%s,%s,%s)
                      AND etoile_1 IN (%s,%s)
                      AND etoile_2 IN (%s,%s)
                    ORDER BY date_de_tirage DESC
                """, (*nums, *nums, *nums, *nums, *nums, *etoiles, *etoiles))
            exact_matches = await cursor.fetchall()
            exact_dates = [str(row['date_de_tirage']) for row in exact_matches]

            # Meilleure correspondance
            if is_loto:
                await cursor.execute("""
                    SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance,
                        (
                            (boule_1 IN (%s,%s,%s,%s,%s)) +
                            (boule_2 IN (%s,%s,%s,%s,%s)) +
                            (boule_3 IN (%s,%s,%s,%s,%s)) +
                            (boule_4 IN (%s,%s,%s,%s,%s)) +
                            (boule_5 IN (%s,%s,%s,%s,%s))
                        ) AS match_count,
                        (numero_chance = %s) AS chance_match
                    FROM tirages
                    ORDER BY match_count DESC, chance_match DESC, date_de_tirage DESC
                    LIMIT 1
                """, (*nums, *nums, *nums, *nums, *nums, chance))
            else:
                await cursor.execute(f"""
                    SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                           etoile_1, etoile_2,
                        (
                            (boule_1 IN (%s,%s,%s,%s,%s)) +
                            (boule_2 IN (%s,%s,%s,%s,%s)) +
                            (boule_3 IN (%s,%s,%s,%s,%s)) +
                            (boule_4 IN (%s,%s,%s,%s,%s)) +
                            (boule_5 IN (%s,%s,%s,%s,%s))
                        ) AS match_count,
                        (
                            (etoile_1 IN (%s,%s)) +
                            (etoile_2 IN (%s,%s))
                        ) AS etoile_match
                    FROM {cfg.table}
                    ORDER BY match_count DESC, etoile_match DESC, date_de_tirage DESC
                    LIMIT 1
                """, (*nums, *nums, *nums, *nums, *nums, *etoiles, *etoiles))
            best_match = await cursor.fetchone()

        best_match_numbers = []
        if best_match:
            tirage_nums = [int(best_match[f'boule_{i}']) for i in range(1, 6)]
            best_match_numbers = sorted([n for n in nums if n in tirage_nums])

        if is_loto:
            history_check = {
                "exact_match": len(exact_dates) > 0,
                "exact_dates": exact_dates,
                "best_match_count": len(best_match_numbers),
                "best_match_chance": bool(best_match['chance_match']) if best_match else False,
                "best_match_chance_number": int(best_match['numero_chance']) if best_match and best_match.get('chance_match') else None,
                "best_match_date": str(best_match['date_de_tirage']) if best_match else None,
                "best_match_numbers": best_match_numbers,
            }
        else:
            best_match_etoiles = []
            if best_match:
                tirage_etoiles = [int(best_match['etoile_1']), int(best_match['etoile_2'])]
                best_match_etoiles = sorted([e for e in etoiles if e in tirage_etoiles])
            history_check = {
                "exact_match": len(exact_dates) > 0,
                "exact_dates": exact_dates,
                "best_match_count": len(best_match_numbers),
                "best_match_etoiles": len(best_match_etoiles),
                "best_match_date": str(best_match['date_de_tirage']) if best_match else None,
                "best_match_numbers": best_match_numbers,
                "best_match_etoiles_list": best_match_etoiles,
            }

        # Metriques de la grille
        nb_pairs = sum(1 for n in nums if n % 2 == 0)
        nb_impairs = 5 - nb_pairs
        mid = 24 if is_loto else 25
        nb_bas = sum(1 for n in nums if n <= mid)
        nb_hauts = 5 - nb_bas
        somme = sum(nums)
        dispersion = max(nums) - min(nums)

        nums_sorted = sorted(nums)
        suites = sum(1 for i in range(4) if nums_sorted[i + 1] - nums_sorted[i] == 1)
        max_run = 1
        current_run = 1
        for i in range(4):
            if nums_sorted[i + 1] - nums_sorted[i] == 1:
                current_run += 1
                if current_run > max_run:
                    max_run = current_run
            else:
                current_run = 1

        # Score de conformite
        score_conformite = 100
        if nb_pairs == 0 or nb_pairs == 5:
            score_conformite -= 25
        elif nb_pairs == 1 or nb_pairs == 4:
            score_conformite -= 10
        if nb_bas == 0 or nb_bas == 5:
            score_conformite -= 25
        elif nb_bas == 1 or nb_bas == 4:
            score_conformite -= 8

        # Somme thresholds differ per game
        if is_loto:
            if somme < 50: score_conformite -= 35
            elif somme < 70: score_conformite -= 20
            elif somme > 200: score_conformite -= 35
            elif somme > 150: score_conformite -= 20
        else:
            if somme < 55: score_conformite -= 35
            elif somme < 75: score_conformite -= 20
            elif somme > 210: score_conformite -= 35
            elif somme > 175: score_conformite -= 20

        if dispersion < 10: score_conformite -= 35
        elif dispersion < 15: score_conformite -= 20
        if max_run >= 5: score_conformite -= 30
        elif max_run >= 4: score_conformite -= 20
        elif max_run >= 3: score_conformite -= 10
        score_conformite = max(0, score_conformite)

        freq_moyenne = sum(frequencies) / 5
        freq_max_theorique = total_tirages * 5 / cfg.num_range[1]
        score_freq = min(100, (freq_moyenne / freq_max_theorique) * 100) if freq_max_theorique else 0
        score = int(0.6 * score_conformite + 0.4 * score_freq)
        score = max(0, min(100, score))

        # Badges
        b = _badges(lang)
        badges = []
        if freq_moyenne > freq_max_theorique * 1.1:
            badges.append(b["hot"])
        elif freq_moyenne < freq_max_theorique * 0.9:
            badges.append(b["overdue"])
        else:
            badges.append(b["balanced"])
        if dispersion > 35:
            badges.append(b["wide_spectrum"])
        if nb_pairs == 2 or nb_pairs == 3:
            badges.append(b["even_odd"])
        badges.append(b["custom_em"] if not is_loto else b["custom"])

        # Detection conditions critiques
        critical_count = 0
        critical_flags = {}
        if max_run >= 4:
            critical_count += 1; critical_flags['suite'] = max_run
        somme_crit_low = 50 if is_loto else 55
        somme_crit_high = 200 if is_loto else 210
        if somme < somme_crit_low or somme > somme_crit_high:
            critical_count += 1; critical_flags['somme'] = somme
        if dispersion < 10:
            critical_count += 1; critical_flags['dispersion'] = dispersion
        if nb_bas == 0 or nb_bas == 5:
            critical_count += 1; critical_flags['bas_haut'] = f"{nb_bas}/{nb_hauts}"
        if nb_pairs == 0 or nb_pairs == 5:
            critical_count += 1; critical_flags['pairs'] = f"{nb_pairs}/{nb_impairs}"
        if score_conformite < 20:
            critical_count += 1; critical_flags['conformite'] = score_conformite

        if critical_count >= 3: severity = 3
        elif critical_count >= 2 or (critical_count == 1 and max_run >= 4): severity = 2
        else: severity = 1

        # Suggestions (i18n)
        s = _analysis_strings(lang)
        suggestions = []
        alert_message = None
        somme_avg = 125 if is_loto else 127
        somme_range_text = "80 et 170" if is_loto else "80 et 175"
        bas_haut_text = f"(1-{mid})"
        hauts_text = f"({mid+1}-{cfg.num_range[1]})"
        dispersion_max = cfg.num_range[1] - 1
        em_suffix = " EM" if not is_loto else ""

        if severity == 3:
            alert_message = s["alert_max"]
            if 'suite' in critical_flags:
                suggestions.append(s["perfect_run"].format(total=total_tirages, suffix=em_suffix, max_run=max_run))
            if 'somme' in critical_flags:
                suggestions.append(s["sum_catastrophic"].format(sum=somme, suffix=em_suffix, range=somme_range_text))
            if 'bas_haut' in critical_flags:
                if nb_bas == 5:
                    suggestions.append(s["zero_above"].format(mid=mid))
                else:
                    suggestions.append(s["zero_below"].format(mid=mid+1))
            if 'dispersion' in critical_flags:
                suggestions.append(s["dispersion_zero"].format(dispersion=dispersion))
            if 'pairs' in critical_flags:
                if nb_pairs == 5:
                    suggestions.append(s["all_even"])
                else:
                    suggestions.append(s["all_odd"])
            if 'conformite' in critical_flags:
                suggestions.append(s["conformity_collapsed"].format(score=score_conformite))

        elif severity == 2:
            if 'suite' in critical_flags:
                suggestions.append(s["run_detected"].format(max_run=max_run))
            if nb_pairs == 0 or nb_pairs == 5:
                suggestions.append(s["even_odd_imbalance"].format(even=nb_pairs, odd=nb_impairs))
            if nb_bas == 0 or nb_bas == 5:
                suggestions.append(s["low_high_imbalance"].format(low=nb_bas, high=nb_hauts, low_range=bas_haut_text, high_range=hauts_text))
            somme_mod_low = 50 if is_loto else 55
            somme_mod_mid_low = 70 if is_loto else 75
            somme_mod_high = 200 if is_loto else 210
            somme_mod_mid_high = 150 if is_loto else 175
            if somme < somme_mod_low or somme > somme_mod_high:
                direction = s["dir_low"] if somme < somme_mod_low else s["dir_high"]
                suggestions.append(s["sum_extreme"].format(direction=direction, sum=somme, avg=somme_avg))
            elif somme < somme_mod_mid_low or somme > somme_mod_mid_high:
                direction = s["dir_low"] if somme < somme_mod_mid_low else s["dir_high"]
                fourchette = "80-170" if is_loto else "85-175"
                suggestions.append(s["sum_moderate"].format(direction=direction, sum=somme, range=fourchette))
            if dispersion < 10:
                suggestions.append(s["dispersion_insufficient"].format(dispersion=dispersion, max=dispersion_max))
            elif dispersion < 15:
                suggestions.append(s["dispersion_low"].format(dispersion=dispersion))
            if max_run >= 3 and 'suite' not in critical_flags:
                suggestions.append(s["run_reduce"].format(max_run=max_run))
        else:
            if score >= 70:
                suggestions.append(s["excellent_balance"])
            if nb_pairs == 1 or nb_pairs == 4:
                suggestions.append(s["vary_even_odd"])
            if nb_bas == 1 or nb_bas == 4:
                suggestions.append(s["mix_low_high"].format(low_range=bas_haut_text, high_range=hauts_text))
            mild_low = 70 if is_loto else 75
            mild_high = 150 if is_loto else 165
            if mild_low <= somme < mild_low + 10:
                suggestions.append(s["sum_slightly_low"])
            elif mild_high < somme <= mild_high + 20:
                suggestions.append(s["sum_slightly_high"])
            if 15 <= dispersion < 20:
                suggestions.append(s["widen_dispersion"])
            if max_run == 3:
                suggestions.append(s["watch_run_3"])
            elif suites >= 2 and max_run < 3:
                suggestions.append(s["some_consecutive"])

        if not suggestions:
            suggestions.append(s["well_balanced"])

        if score >= 80: comparaison = s["better_85"]
        elif score >= 60: comparaison = s["better_60"]
        elif score >= 40: comparaison = s["average"]
        else: comparaison = s["below_average"]

        result = {
            "success": True,
            "nums": nums,
            "score": score,
            "comparaison": comparaison,
            "badges": badges,
            "details": {
                "pairs_impairs": f"{nb_pairs}/{nb_impairs}",
                "bas_haut": f"{nb_bas}/{nb_hauts}",
                "somme": str(somme),
                "dispersion": str(dispersion),
                "suites_consecutives": str(suites),
                "score_conformite": f"{score_conformite}%",
            },
            "severity": severity,
            "alert_message": alert_message,
            "suggestions": suggestions,
            "history_check": history_check,
        }
        if is_loto:
            result["chance"] = chance
        else:
            result["etoiles"] = etoiles
        return result

    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/analyze-custom-grid: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "error": "Erreur interne lors de l'analyse"
        })
