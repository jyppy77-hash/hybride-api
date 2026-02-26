"""
Routes unifiees /api/{game}/... — Donnees (tirages, stats, frequences)
Phase 10 — remplace la duplication api_data.py / em_data.py
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from typing import Optional
import logging

import db_cloudsql
from rate_limit import limiter
from config.games import ValidGame, get_config, get_stats_service, get_engine_stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/{game}", tags=["Unified - Data"])


# =========================
# Tirages count / latest / list
# =========================

@router.get("/tirages/count")
@limiter.limit("60/minute")
async def unified_tirages_count(request: Request, game: ValidGame):
    cfg = get_config(game)
    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(f"SELECT COUNT(*) as total FROM {cfg.table}")
            total = (await cursor.fetchone())['total']
        return {"success": True, "data": {"total": total}, "error": None}
    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/tirages/count: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur interne du serveur"
        })


@router.get("/tirages/latest")
@limiter.limit("60/minute")
async def unified_tirages_latest(request: Request, game: ValidGame):
    cfg = get_config(game)
    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(f"""
                SELECT * FROM {cfg.table}
                ORDER BY date_de_tirage DESC LIMIT 1
            """)
            tirage = await cursor.fetchone()
            if tirage and tirage.get("date_de_tirage"):
                tirage["date_de_tirage"] = str(tirage["date_de_tirage"])
        if tirage:
            return {"success": True, "data": tirage, "error": None}
        else:
            return JSONResponse(status_code=404, content={
                "success": False, "data": None, "error": "Aucun tirage trouve"
            })
    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/tirages/latest: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur interne du serveur"
        })


@router.get("/tirages/list")
@limiter.limit("60/minute")
async def unified_tirages_list(
    request: Request, game: ValidGame,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    cfg = get_config(game)
    try:
        lim = min(max(1, limit), 100)
        off = max(0, offset)
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(f"""
                SELECT * FROM {cfg.table}
                ORDER BY date_de_tirage DESC
                LIMIT %s OFFSET %s
            """, (lim, off))
            tirages = await cursor.fetchall()
            for row in tirages:
                if row.get("date_de_tirage"):
                    row["date_de_tirage"] = str(row["date_de_tirage"])
        return {
            "success": True,
            "data": {"items": tirages, "count": len(tirages), "limit": limit, "offset": offset},
            "error": None,
        }
    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/tirages/list: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur interne du serveur"
        })


# =========================
# Database info
# =========================

@router.get("/database-info")
@limiter.limit("60/minute")
async def unified_database_info(request: Request, game: ValidGame):
    cfg = get_config(game)
    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(f"""
                SELECT COUNT(*) as total,
                       MIN(date_de_tirage) as date_min,
                       MAX(date_de_tirage) as date_max
                FROM {cfg.table}
            """)
            row = await cursor.fetchone()
        return {
            "total_draws": row["total"],
            "first_draw": str(row["date_min"]) if row["date_min"] else None,
            "last_draw": str(row["date_max"]) if row["date_max"] else None,
        }
    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/database-info: {e}")
        return JSONResponse(status_code=500, content={
            "total_draws": None, "first_draw": None, "last_draw": None
        })


# =========================
# META Windows Info (slider)
# =========================

@router.get("/meta-windows-info")
@limiter.limit("60/minute")
async def unified_meta_windows_info(request: Request, game: ValidGame):
    from datetime import timedelta

    cfg = get_config(game)
    # Loto uses window sizes up to 800, EM up to 700
    window_sizes = [100, 200, 300, 400, 500, 600, 700, 800] if game == ValidGame.loto else [100, 200, 300, 400, 500, 600, 700]

    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(f"""
                SELECT date_de_tirage FROM {cfg.table}
                ORDER BY date_de_tirage DESC
            """)
            all_dates = [row["date_de_tirage"] for row in await cursor.fetchall()]

        total = len(all_dates)
        last_draw = all_dates[0] if all_dates else None
        first_draw = all_dates[-1] if all_dates else None

        tirages_windows = {}
        for size in window_sizes:
            if size <= total:
                tirages_windows[size] = {"draws": size, "start": str(all_dates[size - 1]), "end": str(last_draw)}
            else:
                tirages_windows[size] = {"draws": total, "start": str(first_draw), "end": str(last_draw)}
        tirages_windows["GLOBAL"] = {"draws": total, "start": str(first_draw), "end": str(last_draw)}

        annees_windows = {}
        for y in [1, 2, 3, 4, 5, 6]:
            date_limit = last_draw - timedelta(days=365 * y)
            draws_in_range = [d for d in all_dates if d >= date_limit]
            annees_windows[y] = {
                "draws": len(draws_in_range),
                "start": str(draws_in_range[-1]) if draws_in_range else str(first_draw),
                "end": str(last_draw),
            }
        annees_windows["GLOBAL"] = {"draws": total, "start": str(first_draw), "end": str(last_draw)}

        return {
            "tirages": tirages_windows,
            "annees": annees_windows,
            "total_draws": total,
            "last_draw": str(last_draw),
            "first_draw": str(first_draw),
        }

    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/meta-windows-info: {e}")
        return JSONResponse(status_code=500, content={"tirages": None, "annees": None})


# =========================
# Stats completes
# =========================

@router.get("/stats")
@limiter.limit("60/minute")
async def unified_stats(request: Request, game: ValidGame):
    cfg = get_config(game)
    svc = get_stats_service(cfg)
    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()

            await cursor.execute(f"""
                SELECT COUNT(*) as total,
                       MIN(date_de_tirage) as date_min,
                       MAX(date_de_tirage) as date_max
                FROM {cfg.table}
            """)
            info = await cursor.fetchone()
            total_tirages = info['total']
            date_min = str(info['date_min']) if info['date_min'] else None
            date_max = str(info['date_max']) if info['date_max'] else None

            # Frequences & retards boules principales
            type_principal = "principal" if game == ValidGame.loto else "boule"
            freq_map = await svc._get_all_frequencies(cursor, type_principal)
            num_max = cfg.num_range[1] + 1
            frequences = {str(num): freq_map.get(num, 0) for num in range(1, num_max)}

            ecart_map = await svc._get_all_ecarts(cursor, type_principal)
            retards = {str(num): ecart_map.get(num, total_tirages) for num in range(1, num_max)}

            # Top/Flop boules
            sorted_by_freq = sorted(
                [(int(k), v) for k, v in frequences.items()],
                key=lambda x: x[1], reverse=True,
            )
            top_chauds = [{"numero": n, "freq": f} for n, f in sorted_by_freq[:5]]
            top_froids = [{"numero": n, "freq": f} for n, f in sorted_by_freq[-5:]]

            if game == ValidGame.loto:
                return {
                    "success": True,
                    "data": {
                        "total_tirages": total_tirages,
                        "periode": {"debut": date_min, "fin": date_max},
                        "frequences": frequences,
                        "retards": retards,
                        "top_chauds": top_chauds,
                        "top_froids": top_froids,
                    },
                    "error": None,
                }
            else:
                # EM: also compute etoiles
                freq_etoiles = await svc._get_all_frequencies(cursor, "etoile")
                frequences_etoiles = {str(num): freq_etoiles.get(num, 0) for num in range(1, 13)}
                ecart_etoiles = await svc._get_all_ecarts(cursor, "etoile")
                retards_etoiles = {str(num): ecart_etoiles.get(num, total_tirages) for num in range(1, 13)}

                sorted_etoiles = sorted(
                    [(int(k), v) for k, v in frequences_etoiles.items()],
                    key=lambda x: x[1], reverse=True,
                )
                top_chauds_etoiles = [{"numero": n, "freq": f} for n, f in sorted_etoiles[:3]]
                top_froids_etoiles = [{"numero": n, "freq": f} for n, f in sorted_etoiles[-3:]]

                return {
                    "success": True,
                    "data": {
                        "total_tirages": total_tirages,
                        "periode": {"debut": date_min, "fin": date_max},
                        "frequences_boules": frequences,
                        "retards_boules": retards,
                        "frequences_etoiles": frequences_etoiles,
                        "retards_etoiles": retards_etoiles,
                        "top_chauds_boules": top_chauds,
                        "top_froids_boules": top_froids,
                        "top_chauds_etoiles": top_chauds_etoiles,
                        "top_froids_etoiles": top_froids_etoiles,
                    },
                    "error": None,
                }

    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/stats: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur interne du serveur"
        })


# =========================
# Numbers Heat
# =========================

@router.get("/numbers-heat")
@limiter.limit("60/minute")
async def unified_numbers_heat(request: Request, game: ValidGame):
    cfg = get_config(game)
    svc = get_stats_service(cfg)
    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()

            await cursor.execute(f"SELECT COUNT(*) as total FROM {cfg.table}")
            total = (await cursor.fetchone())['total']

            # --- Boules ---
            type_principal = "principal" if game == ValidGame.loto else "boule"
            freq_boules = await svc._get_all_frequencies(cursor, type_principal)
            num_max = cfg.num_range[1] + 1

            await cursor.execute(f"""
                SELECT num, MAX(date_de_tirage) as last_date FROM (
                    SELECT boule_1 as num, date_de_tirage FROM {cfg.table}
                    UNION ALL SELECT boule_2, date_de_tirage FROM {cfg.table}
                    UNION ALL SELECT boule_3, date_de_tirage FROM {cfg.table}
                    UNION ALL SELECT boule_4, date_de_tirage FROM {cfg.table}
                    UNION ALL SELECT boule_5, date_de_tirage FROM {cfg.table}
                ) t GROUP BY num
            """)
            last_dates_boules = {row['num']: row['last_date'] for row in await cursor.fetchall()}

            boules_data = {}
            boules_freqs = []
            for num in range(1, num_max):
                freq = freq_boules.get(num, 0)
                last_d = last_dates_boules.get(num)
                boules_data[num] = {"frequency": freq, "last_draw": str(last_d) if last_d else None}
                boules_freqs.append(freq)

            boules_freqs.sort(reverse=True)
            seuil_chaud_b = boules_freqs[len(boules_freqs) // 3]
            seuil_froid_b = boules_freqs[2 * len(boules_freqs) // 3]
            for num in range(1, num_max):
                freq = boules_data[num]["frequency"]
                if freq >= seuil_chaud_b:
                    boules_data[num]["category"] = "hot"
                elif freq <= seuil_froid_b:
                    boules_data[num]["category"] = "cold"
                else:
                    boules_data[num]["category"] = "neutral"

            if game == ValidGame.loto:
                return {
                    "success": True,
                    "numbers": boules_data,
                    "total_tirages": total,
                    "seuils": {"chaud": seuil_chaud_b, "froid": seuil_froid_b},
                }

            # --- Etoiles (EM only) ---
            freq_etoiles = await svc._get_all_frequencies(cursor, "etoile")
            await cursor.execute(f"""
                SELECT num, MAX(date_de_tirage) as last_date FROM (
                    SELECT etoile_1 as num, date_de_tirage FROM {cfg.table}
                    UNION ALL SELECT etoile_2, date_de_tirage FROM {cfg.table}
                ) t GROUP BY num
            """)
            last_dates_etoiles = {row['num']: row['last_date'] for row in await cursor.fetchall()}

            etoiles_data = {}
            etoiles_freqs = []
            for num in range(1, 13):
                freq = freq_etoiles.get(num, 0)
                last_d = last_dates_etoiles.get(num)
                etoiles_data[num] = {"frequency": freq, "last_draw": str(last_d) if last_d else None}
                etoiles_freqs.append(freq)

            etoiles_freqs.sort(reverse=True)
            seuil_chaud_e = etoiles_freqs[len(etoiles_freqs) // 3]
            seuil_froid_e = etoiles_freqs[2 * len(etoiles_freqs) // 3]
            for num in range(1, 13):
                freq = etoiles_data[num]["frequency"]
                if freq >= seuil_chaud_e:
                    etoiles_data[num]["category"] = "hot"
                elif freq <= seuil_froid_e:
                    etoiles_data[num]["category"] = "cold"
                else:
                    etoiles_data[num]["category"] = "neutral"

            return {
                "success": True,
                "boules": boules_data,
                "etoiles": etoiles_data,
                "total_tirages": total,
                "seuils_boules": {"chaud": seuil_chaud_b, "froid": seuil_froid_b},
                "seuils_etoiles": {"chaud": seuil_chaud_e, "froid": seuil_froid_e},
            }

    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/numbers-heat: {e}")
        if game == ValidGame.loto:
            return JSONResponse(status_code=500, content={
                "success": False, "numbers": {}, "error": "Erreur interne du serveur"
            })
        return JSONResponse(status_code=500, content={
            "success": False, "boules": {}, "etoiles": {}, "error": "Erreur interne du serveur"
        })


# =========================
# Draw by date
# =========================

@router.get("/draw/{date}")
@limiter.limit("60/minute")
async def unified_draw_by_date(request: Request, game: ValidGame, date: str):
    cfg = get_config(game)
    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()
            if game == ValidGame.loto:
                await cursor.execute("""
                    SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance
                    FROM tirages WHERE date_de_tirage = %s
                """, (date,))
            else:
                await cursor.execute(f"""
                    SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                           etoile_1, etoile_2, jackpot_euros, nb_joueurs, nb_gagnants_rang1
                    FROM {cfg.table} WHERE date_de_tirage = %s
                """, (date,))
            result = await cursor.fetchone()

        if result:
            draw = {
                "date": str(result['date_de_tirage']),
                "n1": result['boule_1'], "n2": result['boule_2'],
                "n3": result['boule_3'], "n4": result['boule_4'],
                "n5": result['boule_5'],
            }
            if game == ValidGame.loto:
                draw["chance"] = result['numero_chance']
            else:
                draw["etoile_1"] = result['etoile_1']
                draw["etoile_2"] = result['etoile_2']
                draw["jackpot_euros"] = result['jackpot_euros']
                draw["nb_joueurs"] = result['nb_joueurs']
                draw["nb_gagnants_rang1"] = result['nb_gagnants_rang1']
            return {"success": True, "found": True, "draw": draw}
        else:
            game_label = "Loto" if game == ValidGame.loto else "EuroMillions"
            return JSONResponse(status_code=404, content={
                "success": True, "found": False,
                "message": f"Aucun tirage {game_label} pour la date {date}",
            })

    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/draw/{date}: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "found": False, "message": "Erreur interne du serveur"
        })


# =========================
# Stats number
# =========================

@router.get("/stats/number/{number}")
@limiter.limit("60/minute")
async def unified_stats_number(request: Request, game: ValidGame, number: int):
    cfg = get_config(game)
    try:
        if not (cfg.num_range[0] <= number <= cfg.num_range[1]):
            return JSONResponse(status_code=400, content={
                "success": False,
                "message": f"Numéro doit être entre {cfg.num_range[0]} et {cfg.num_range[1]}",
            })

        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(f"""
                SELECT date_de_tirage FROM {cfg.table}
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
                ORDER BY date_de_tirage ASC
            """, (number, number, number, number, number))
            results = await cursor.fetchall()
            appearance_dates = [str(r['date_de_tirage']) for r in results]
            total_appearances = len(appearance_dates)
            first_appearance = appearance_dates[0] if appearance_dates else None
            last_appearance = appearance_dates[-1] if appearance_dates else None

            current_gap = 0
            if last_appearance:
                await cursor.execute(f"""
                    SELECT COUNT(*) as gap FROM {cfg.table}
                    WHERE date_de_tirage > %s
                """, (last_appearance,))
                gap_result = await cursor.fetchone()
                current_gap = gap_result['gap'] if gap_result else 0

        resp = {
            "success": True,
            "number": number,
            "total_appearances": total_appearances,
            "first_appearance": first_appearance,
            "last_appearance": last_appearance,
            "current_gap": current_gap,
            "appearance_dates": appearance_dates,
        }
        if game == ValidGame.euromillions:
            resp["type"] = "boule"
        return resp

    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/stats/number/{number}: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "message": "Erreur interne du serveur"
        })


# =========================
# Stats etoile (EM only)
# =========================

@router.get("/stats/etoile/{number}")
@limiter.limit("60/minute")
async def unified_stats_etoile(request: Request, game: ValidGame, number: int):
    if game != ValidGame.euromillions:
        raise HTTPException(status_code=404, detail="Route disponible uniquement pour EuroMillions")

    cfg = get_config(game)
    try:
        if not (1 <= number <= 12):
            return JSONResponse(status_code=400, content={
                "success": False, "message": "Etoile doit etre entre 1 et 12"
            })

        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(f"""
                SELECT date_de_tirage FROM {cfg.table}
                WHERE etoile_1 = %s OR etoile_2 = %s
                ORDER BY date_de_tirage ASC
            """, (number, number))
            results = await cursor.fetchall()
            appearance_dates = [str(r['date_de_tirage']) for r in results]
            total_appearances = len(appearance_dates)
            first_appearance = appearance_dates[0] if appearance_dates else None
            last_appearance = appearance_dates[-1] if appearance_dates else None

            current_gap = 0
            if last_appearance:
                await cursor.execute(f"""
                    SELECT COUNT(*) as gap FROM {cfg.table}
                    WHERE date_de_tirage > %s
                """, (last_appearance,))
                gap_result = await cursor.fetchone()
                current_gap = gap_result['gap'] if gap_result else 0

        return {
            "success": True,
            "number": number,
            "type": "etoile",
            "total_appearances": total_appearances,
            "first_appearance": first_appearance,
            "last_appearance": last_appearance,
            "current_gap": current_gap,
            "appearance_dates": appearance_dates,
        }

    except Exception as e:
        logger.error(f"Erreur /api/euromillions/stats/etoile/{number}: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "message": "Erreur interne du serveur"
        })


# =========================
# Top / Flop
# =========================

@router.get("/stats/top-flop")
@limiter.limit("60/minute")
async def unified_stats_top_flop(request: Request, game: ValidGame):
    cfg = get_config(game)
    svc = get_stats_service(cfg)
    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()
            type_principal = "principal" if game == ValidGame.loto else "boule"
            num_max = cfg.num_range[1] + 1

            freq_map = await svc._get_all_frequencies(cursor, type_principal)
            numbers_freq = [{"number": num, "count": freq_map.get(num, 0)} for num in range(1, num_max)]

            top = sorted(numbers_freq, key=lambda x: (-x['count'], x['number']))
            flop = sorted(numbers_freq, key=lambda x: (x['count'], x['number']))

            if game == ValidGame.loto:
                return {"success": True, "top": top, "flop": flop}

            # EM: also compute etoiles
            freq_etoiles = await svc._get_all_frequencies(cursor, "etoile")
            etoiles_freq = [{"number": num, "count": freq_etoiles.get(num, 0)} for num in range(1, 13)]
            top_etoiles = sorted(etoiles_freq, key=lambda x: (-x['count'], x['number']))
            flop_etoiles = sorted(etoiles_freq, key=lambda x: (x['count'], x['number']))

            return {
                "success": True,
                "top_boules": top, "flop_boules": flop,
                "top_etoiles": top_etoiles, "flop_etoiles": flop_etoiles,
            }

    except Exception as e:
        logger.error(f"Erreur /api/{cfg.slug}/stats/top-flop: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "message": "Erreur interne du serveur"
        })


# =========================
# Hybride Stats (chatbot BDD)
# =========================

@router.get("/hybride-stats")
@limiter.limit("60/minute")
async def unified_hybride_stats(
    request: Request, game: ValidGame,
    numero: int = Query(..., description="Numero a analyser"),
    type: str = Query(default=None, description="Type de numero"),
):
    cfg = get_config(game)
    svc = get_stats_service(cfg)

    # Default type depends on game
    if type is None:
        type = "principal" if game == ValidGame.loto else "boule"

    valid_types = ("principal", "chance") if game == ValidGame.loto else ("boule", "etoile")
    if type not in valid_types:
        return JSONResponse(status_code=400, content={
            "success": False, "data": None,
            "error": f"type doit etre parmi {valid_types}",
        })

    stats = await svc.get_numero_stats(numero, type)
    if stats is None:
        return JSONResponse(status_code=404, content={
            "success": False, "data": None,
            "error": f"Numéro {numero} invalide pour type {type}",
        })

    return {"success": True, "data": stats, "error": None}
