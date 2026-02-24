"""
Routes API EuroMillions — Donnees (tirages, stats, frequences)
Equivalent EM de routes/api_data.py
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
import asyncio
import logging

import db_cloudsql
from rate_limit import limiter
from services.em_stats_service import (
    _get_all_frequencies, _get_all_ecarts,
    get_numero_stats,
)

logger = logging.getLogger(__name__)

TABLE = "tirages_euromillions"

router = APIRouter(prefix="/api/euromillions", tags=["EuroMillions - Donnees"])


# =========================
# API Tirages EM
# =========================

@router.get("/tirages/count")
@limiter.limit("60/minute")
async def em_tirages_count(request: Request):
    """Retourne le nombre total de tirages EuroMillions en base."""
    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) as total FROM {TABLE}")
                return cursor.fetchone()['total']
            finally:
                conn.close()

        total = await asyncio.to_thread(_fetch)
        return {"success": True, "data": {"total": total}, "error": None}
    except Exception as e:
        logger.error(f"Erreur /api/euromillions/tirages/count: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur interne du serveur"
        })


@router.get("/tirages/latest")
@limiter.limit("60/minute")
async def em_tirages_latest(request: Request):
    """Retourne le tirage EuroMillions le plus recent."""
    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT * FROM {TABLE}
                    ORDER BY date_de_tirage DESC
                    LIMIT 1
                """)
                result = cursor.fetchone()
                if result and result.get("date_de_tirage"):
                    result["date_de_tirage"] = str(result["date_de_tirage"])
                return result
            finally:
                conn.close()

        tirage = await asyncio.to_thread(_fetch)
        if tirage:
            return {"success": True, "data": tirage, "error": None}
        else:
            return JSONResponse(status_code=404, content={
                "success": False, "data": None, "error": "Aucun tirage trouve"
            })
    except Exception as e:
        logger.error(f"Erreur /api/euromillions/tirages/latest: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur interne du serveur"
        })


@router.get("/tirages/list")
@limiter.limit("60/minute")
async def em_tirages_list(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100, description="Nombre de tirages"),
    offset: int = Query(default=0, ge=0, description="Offset pour pagination")
):
    """Retourne une liste de tirages EuroMillions (du plus recent au plus ancien)."""
    try:
        def _fetch():
            lim = min(max(1, limit), 100)
            off = max(0, offset)
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT * FROM {TABLE}
                    ORDER BY date_de_tirage DESC
                    LIMIT %s OFFSET %s
                """, (lim, off))
                results = cursor.fetchall()
                for row in results:
                    if row.get("date_de_tirage"):
                        row["date_de_tirage"] = str(row["date_de_tirage"])
                return results
            finally:
                conn.close()

        tirages = await asyncio.to_thread(_fetch)
        return {
            "success": True,
            "data": {
                "items": tirages,
                "count": len(tirages),
                "limit": limit,
                "offset": offset
            },
            "error": None
        }
    except Exception as e:
        logger.error(f"Erreur /api/euromillions/tirages/list: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur interne du serveur"
        })


# =========================
# API Database Info EM
# =========================

@router.get("/database-info")
@limiter.limit("60/minute")
async def em_database_info(request: Request):
    """Retourne les informations sur les tirages EuroMillions en base."""
    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT COUNT(*) as total,
                           MIN(date_de_tirage) as date_min,
                           MAX(date_de_tirage) as date_max
                    FROM {TABLE}
                """)
                row = cursor.fetchone()
            finally:
                conn.close()
            return {
                "total_draws": row["total"],
                "first_draw": str(row["date_min"]) if row["date_min"] else None,
                "last_draw": str(row["date_max"]) if row["date_max"] else None
            }

        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.error(f"Erreur /api/euromillions/database-info: {e}")
        return JSONResponse(status_code=500, content={
            "total_draws": None, "first_draw": None, "last_draw": None
        })


# =========================
# API META Windows Info EM
# =========================

@router.get("/meta-windows-info")
@limiter.limit("60/minute")
async def em_meta_windows_info(request: Request):
    """
    Retourne les plages de dates et le nombre de tirages
    pour chaque fenetre d'analyse EuroMillions.
    """
    from datetime import timedelta

    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT date_de_tirage FROM {TABLE}
                    ORDER BY date_de_tirage DESC
                """)
                all_dates = [row["date_de_tirage"] for row in cursor.fetchall()]
            finally:
                conn.close()

            total = len(all_dates)
            last_draw = all_dates[0] if all_dates else None
            first_draw = all_dates[-1] if all_dates else None

            tirages_windows = {}
            for size in [100, 200, 300, 400, 500, 600, 700]:
                if size <= total:
                    tirages_windows[size] = {
                        "draws": size,
                        "start": str(all_dates[size - 1]),
                        "end": str(last_draw)
                    }
                else:
                    tirages_windows[size] = {
                        "draws": total,
                        "start": str(first_draw),
                        "end": str(last_draw)
                    }
            tirages_windows["GLOBAL"] = {
                "draws": total,
                "start": str(first_draw),
                "end": str(last_draw)
            }

            annees_windows = {}
            for y in [1, 2, 3, 4, 5, 6]:
                date_limit = last_draw - timedelta(days=365 * y)
                draws_in_range = [d for d in all_dates if d >= date_limit]
                annees_windows[y] = {
                    "draws": len(draws_in_range),
                    "start": str(draws_in_range[-1]) if draws_in_range else str(first_draw),
                    "end": str(last_draw)
                }
            annees_windows["GLOBAL"] = {
                "draws": total,
                "start": str(first_draw),
                "end": str(last_draw)
            }

            return {
                "tirages": tirages_windows,
                "annees": annees_windows,
                "total_draws": total,
                "last_draw": str(last_draw),
                "first_draw": str(first_draw)
            }

        return await asyncio.to_thread(_fetch)

    except Exception as e:
        logger.error(f"Erreur /api/euromillions/meta-windows-info: {e}")
        return JSONResponse(status_code=500, content={"tirages": None, "annees": None})


# =========================
# API Stats Completes EM
# =========================

@router.get("/stats")
@limiter.limit("60/minute")
async def em_stats(request: Request):
    """
    Retourne les statistiques completes EuroMillions.
    Frequences et retards pour boules (1-50) et etoiles (1-12).
    """
    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()

                cursor.execute(f"""
                    SELECT COUNT(*) as total,
                           MIN(date_de_tirage) as date_min,
                           MAX(date_de_tirage) as date_max
                    FROM {TABLE}
                """)
                info = cursor.fetchone()
                total_tirages = info['total']
                date_min = str(info['date_min']) if info['date_min'] else None
                date_max = str(info['date_max']) if info['date_max'] else None

                # Frequences boules (1-50)
                freq_boules = _get_all_frequencies(cursor, "boule")
                frequences_boules = {str(num): freq_boules.get(num, 0) for num in range(1, 51)}

                # Retards boules
                ecart_boules = _get_all_ecarts(cursor, "boule")
                retards_boules = {str(num): ecart_boules.get(num, total_tirages) for num in range(1, 51)}

                # Frequences etoiles (1-12)
                freq_etoiles = _get_all_frequencies(cursor, "etoile")
                frequences_etoiles = {str(num): freq_etoiles.get(num, 0) for num in range(1, 13)}

                # Retards etoiles
                ecart_etoiles = _get_all_ecarts(cursor, "etoile")
                retards_etoiles = {str(num): ecart_etoiles.get(num, total_tirages) for num in range(1, 13)}
            finally:
                conn.close()

            # Top/Flop boules
            sorted_boules = sorted(
                [(int(k), v) for k, v in frequences_boules.items()],
                key=lambda x: x[1], reverse=True
            )
            top_chauds_boules = [{"numero": n, "freq": f} for n, f in sorted_boules[:5]]
            top_froids_boules = [{"numero": n, "freq": f} for n, f in sorted_boules[-5:]]

            # Top/Flop etoiles
            sorted_etoiles = sorted(
                [(int(k), v) for k, v in frequences_etoiles.items()],
                key=lambda x: x[1], reverse=True
            )
            top_chauds_etoiles = [{"numero": n, "freq": f} for n, f in sorted_etoiles[:3]]
            top_froids_etoiles = [{"numero": n, "freq": f} for n, f in sorted_etoiles[-3:]]

            return {
                "success": True,
                "data": {
                    "total_tirages": total_tirages,
                    "periode": {"debut": date_min, "fin": date_max},
                    "frequences_boules": frequences_boules,
                    "retards_boules": retards_boules,
                    "frequences_etoiles": frequences_etoiles,
                    "retards_etoiles": retards_etoiles,
                    "top_chauds_boules": top_chauds_boules,
                    "top_froids_boules": top_froids_boules,
                    "top_chauds_etoiles": top_chauds_etoiles,
                    "top_froids_etoiles": top_froids_etoiles,
                },
                "error": None
            }

        return await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=30.0)

    except asyncio.TimeoutError:
        logger.error("Timeout 30s /api/euromillions/stats")
        return JSONResponse(status_code=503, content={
            "success": False, "data": None, "error": "Service temporairement indisponible"
        })
    except Exception as e:
        logger.error(f"Erreur /api/euromillions/stats: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur interne du serveur"
        })


# =========================
# API Numbers Heat EM
# =========================

@router.get("/numbers-heat")
@limiter.limit("60/minute")
async def em_numbers_heat(request: Request):
    """
    Retourne la classification chaud/neutre/froid pour boules (1-50) et etoiles (1-12).
    """
    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()

                cursor.execute(f"SELECT COUNT(*) as total FROM {TABLE}")
                total = cursor.fetchone()['total']

                # --- Boules ---
                freq_boules = _get_all_frequencies(cursor, "boule")

                cursor.execute(f"""
                    SELECT num, MAX(date_de_tirage) as last_date FROM (
                        SELECT boule_1 as num, date_de_tirage FROM {TABLE}
                        UNION ALL SELECT boule_2, date_de_tirage FROM {TABLE}
                        UNION ALL SELECT boule_3, date_de_tirage FROM {TABLE}
                        UNION ALL SELECT boule_4, date_de_tirage FROM {TABLE}
                        UNION ALL SELECT boule_5, date_de_tirage FROM {TABLE}
                    ) t
                    GROUP BY num
                """)
                last_dates_boules = {row['num']: row['last_date'] for row in cursor.fetchall()}

                boules_data = {}
                boules_freqs = []
                for num in range(1, 51):
                    freq = freq_boules.get(num, 0)
                    last_d = last_dates_boules.get(num)
                    boules_data[num] = {
                        "frequency": freq,
                        "last_draw": str(last_d) if last_d else None
                    }
                    boules_freqs.append(freq)

                boules_freqs.sort(reverse=True)
                seuil_chaud_b = boules_freqs[len(boules_freqs) // 3]
                seuil_froid_b = boules_freqs[2 * len(boules_freqs) // 3]

                for num in range(1, 51):
                    freq = boules_data[num]["frequency"]
                    if freq >= seuil_chaud_b:
                        boules_data[num]["category"] = "hot"
                    elif freq <= seuil_froid_b:
                        boules_data[num]["category"] = "cold"
                    else:
                        boules_data[num]["category"] = "neutral"

                # --- Etoiles ---
                freq_etoiles = _get_all_frequencies(cursor, "etoile")

                cursor.execute(f"""
                    SELECT num, MAX(date_de_tirage) as last_date FROM (
                        SELECT etoile_1 as num, date_de_tirage FROM {TABLE}
                        UNION ALL SELECT etoile_2, date_de_tirage FROM {TABLE}
                    ) t
                    GROUP BY num
                """)
                last_dates_etoiles = {row['num']: row['last_date'] for row in cursor.fetchall()}

                etoiles_data = {}
                etoiles_freqs = []
                for num in range(1, 13):
                    freq = freq_etoiles.get(num, 0)
                    last_d = last_dates_etoiles.get(num)
                    etoiles_data[num] = {
                        "frequency": freq,
                        "last_draw": str(last_d) if last_d else None
                    }
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
            finally:
                conn.close()

            return {
                "success": True,
                "boules": boules_data,
                "etoiles": etoiles_data,
                "total_tirages": total,
                "seuils_boules": {"chaud": seuil_chaud_b, "froid": seuil_froid_b},
                "seuils_etoiles": {"chaud": seuil_chaud_e, "froid": seuil_froid_e}
            }

        return await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=30.0)

    except asyncio.TimeoutError:
        logger.error("Timeout 30s /api/euromillions/numbers-heat")
        return JSONResponse(status_code=503, content={
            "success": False, "boules": {}, "etoiles": {},
            "error": "Service temporairement indisponible"
        })
    except Exception as e:
        logger.error(f"Erreur /api/euromillions/numbers-heat: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "boules": {}, "etoiles": {},
            "error": "Erreur interne du serveur"
        })


# =========================
# API Draw by Date EM
# =========================

@router.get("/draw/{date}")
@limiter.limit("60/minute")
async def em_get_draw_by_date(request: Request, date: str):
    """Recherche un tirage EuroMillions par date (format YYYY-MM-DD)."""
    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                           etoile_1, etoile_2, jackpot_euros, nb_joueurs, nb_gagnants_rang1
                    FROM {TABLE}
                    WHERE date_de_tirage = %s
                """, (date,))
                return cursor.fetchone()
            finally:
                conn.close()

        result = await asyncio.to_thread(_fetch)

        if result:
            return {
                "success": True,
                "found": True,
                "draw": {
                    "date": str(result['date_de_tirage']),
                    "n1": result['boule_1'],
                    "n2": result['boule_2'],
                    "n3": result['boule_3'],
                    "n4": result['boule_4'],
                    "n5": result['boule_5'],
                    "etoile_1": result['etoile_1'],
                    "etoile_2": result['etoile_2'],
                    "jackpot_euros": result['jackpot_euros'],
                    "nb_joueurs": result['nb_joueurs'],
                    "nb_gagnants_rang1": result['nb_gagnants_rang1']
                }
            }
        else:
            return JSONResponse(status_code=404, content={
                "success": True, "found": False,
                "message": f"Aucun tirage EuroMillions pour la date {date}"
            })

    except Exception as e:
        logger.error(f"Erreur /api/euromillions/draw/{date}: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "found": False, "message": "Erreur interne du serveur"
        })


# =========================
# API Stats Number EM
# =========================

@router.get("/stats/number/{number}")
@limiter.limit("60/minute")
async def em_stats_number(request: Request, number: int):
    """Analyse complete d'une boule specifique (1-50)."""
    try:
        if not 1 <= number <= 50:
            return JSONResponse(status_code=400, content={
                "success": False, "message": "Numéro doit être entre 1 et 50"
            })

        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()

                cursor.execute(f"""
                    SELECT date_de_tirage
                    FROM {TABLE}
                    WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                       OR boule_4 = %s OR boule_5 = %s
                    ORDER BY date_de_tirage ASC
                """, (number, number, number, number, number))

                results = cursor.fetchall()
                appearance_dates = [str(r['date_de_tirage']) for r in results]

                total_appearances = len(appearance_dates)
                first_appearance = appearance_dates[0] if appearance_dates else None
                last_appearance = appearance_dates[-1] if appearance_dates else None

                current_gap = 0
                if last_appearance:
                    cursor.execute(f"""
                        SELECT COUNT(*) as gap FROM {TABLE}
                        WHERE date_de_tirage > %s
                    """, (last_appearance,))
                    gap_result = cursor.fetchone()
                    current_gap = gap_result['gap'] if gap_result else 0
            finally:
                conn.close()

            return {
                "success": True,
                "number": number,
                "type": "boule",
                "total_appearances": total_appearances,
                "first_appearance": first_appearance,
                "last_appearance": last_appearance,
                "current_gap": current_gap,
                "appearance_dates": appearance_dates
            }

        return await asyncio.to_thread(_fetch)

    except Exception as e:
        logger.error(f"Erreur /api/euromillions/stats/number/{number}: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "message": "Erreur interne du serveur"
        })


# =========================
# API Stats Etoile EM
# =========================

@router.get("/stats/etoile/{number}")
@limiter.limit("60/minute")
async def em_stats_etoile(request: Request, number: int):
    """Analyse complete d'une etoile specifique (1-12)."""
    try:
        if not 1 <= number <= 12:
            return JSONResponse(status_code=400, content={
                "success": False, "message": "Etoile doit etre entre 1 et 12"
            })

        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()

                cursor.execute(f"""
                    SELECT date_de_tirage
                    FROM {TABLE}
                    WHERE etoile_1 = %s OR etoile_2 = %s
                    ORDER BY date_de_tirage ASC
                """, (number, number))

                results = cursor.fetchall()
                appearance_dates = [str(r['date_de_tirage']) for r in results]

                total_appearances = len(appearance_dates)
                first_appearance = appearance_dates[0] if appearance_dates else None
                last_appearance = appearance_dates[-1] if appearance_dates else None

                current_gap = 0
                if last_appearance:
                    cursor.execute(f"""
                        SELECT COUNT(*) as gap FROM {TABLE}
                        WHERE date_de_tirage > %s
                    """, (last_appearance,))
                    gap_result = cursor.fetchone()
                    current_gap = gap_result['gap'] if gap_result else 0
            finally:
                conn.close()

            return {
                "success": True,
                "number": number,
                "type": "etoile",
                "total_appearances": total_appearances,
                "first_appearance": first_appearance,
                "last_appearance": last_appearance,
                "current_gap": current_gap,
                "appearance_dates": appearance_dates
            }

        return await asyncio.to_thread(_fetch)

    except Exception as e:
        logger.error(f"Erreur /api/euromillions/stats/etoile/{number}: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "message": "Erreur interne du serveur"
        })


# =========================
# API Top/Flop EM
# =========================

@router.get("/stats/top-flop")
@limiter.limit("60/minute")
async def em_stats_top_flop(request: Request):
    """Retourne le classement des boules et etoiles par frequence."""
    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()

                freq_boules = _get_all_frequencies(cursor, "boule")
                boules_freq = [{"number": num, "count": freq_boules.get(num, 0)} for num in range(1, 51)]

                freq_etoiles = _get_all_frequencies(cursor, "etoile")
                etoiles_freq = [{"number": num, "count": freq_etoiles.get(num, 0)} for num in range(1, 13)]
            finally:
                conn.close()

            top_boules = sorted(boules_freq, key=lambda x: (-x['count'], x['number']))
            flop_boules = sorted(boules_freq, key=lambda x: (x['count'], x['number']))
            top_etoiles = sorted(etoiles_freq, key=lambda x: (-x['count'], x['number']))
            flop_etoiles = sorted(etoiles_freq, key=lambda x: (x['count'], x['number']))

            return {
                "success": True,
                "top_boules": top_boules,
                "flop_boules": flop_boules,
                "top_etoiles": top_etoiles,
                "flop_etoiles": flop_etoiles
            }

        return await asyncio.to_thread(_fetch)

    except Exception as e:
        logger.error(f"Erreur /api/euromillions/stats/top-flop: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "message": "Erreur interne du serveur"
        })


# =========================
# API Hybride Stats EM
# =========================

@router.get("/hybride-stats")
@limiter.limit("60/minute")
async def em_hybride_stats(
    request: Request,
    numero: int = Query(..., description="Numero a analyser"),
    type: str = Query(default="boule", description="boule ou etoile")
):
    """Retourne les statistiques completes d'un numero EM."""
    if type not in ("boule", "etoile"):
        return JSONResponse(status_code=400, content={
            "success": False, "data": None, "error": "type doit être 'boule' ou 'étoile'"
        })

    stats = await asyncio.to_thread(get_numero_stats, numero, type)
    if stats is None:
        return JSONResponse(status_code=404, content={
            "success": False, "data": None,
            "error": f"Numéro {numero} invalide pour type {type}"
        })

    return {"success": True, "data": stats, "error": None}
