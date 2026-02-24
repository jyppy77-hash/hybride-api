from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
import asyncio
import logging

import db_cloudsql
from engine.stats import get_global_stats
from rate_limit import limiter
from services.stats_service import (
    _get_all_frequencies, _get_all_ecarts,
    get_numero_stats,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =========================
# API Tirages (Cloud SQL)
# =========================

@router.get("/api/tirages/count")
@limiter.limit("60/minute")
async def api_tirages_count(request: Request):
    """
    Retourne le nombre total de tirages en base.

    Returns:
        JSON {success: bool, data: {total: int}, error: str|null}
    """
    try:
        total = await asyncio.to_thread(db_cloudsql.get_tirages_count)
        return {
            "success": True,
            "data": {"total": total},
            "error": None
        }
    except Exception as e:
        logger.error(f"Erreur /api/tirages/count: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "data": None,
            "error": "Erreur interne du serveur"
        })


@router.get("/api/tirages/latest")
@limiter.limit("60/minute")
async def api_tirages_latest(request: Request):
    """
    Retourne le tirage le plus recent.

    Returns:
        JSON {success: bool, data: {...tirage}, error: str|null}
    """
    try:
        tirage = await asyncio.to_thread(db_cloudsql.get_latest_tirage)
        if tirage:
            return {
                "success": True,
                "data": tirage,
                "error": None
            }
        else:
            return JSONResponse(status_code=404, content={
                "success": False,
                "data": None,
                "error": "Aucun tirage trouve"
            })
    except Exception as e:
        logger.error(f"Erreur /api/tirages/latest: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "data": None,
            "error": "Erreur interne du serveur"
        })


@router.get("/api/tirages/list")
@limiter.limit("60/minute")
async def api_tirages_list(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100, description="Nombre de tirages"),
    offset: int = Query(default=0, ge=0, description="Offset pour pagination")
):
    """
    Retourne une liste de tirages (du plus recent au plus ancien).

    Args:
        limit: Nombre max de tirages (1-100, defaut: 10)
        offset: Decalage pour pagination (defaut: 0)

    Returns:
        JSON {success: bool, data: {items: [...], count: int, limit: int}, error: str|null}
    """
    try:
        tirages = await asyncio.to_thread(db_cloudsql.get_tirages_list, limit, offset)
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
        logger.error(f"Erreur /api/tirages/list: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "data": None,
            "error": "Erreur interne du serveur"
        })


# =========================
# API Database Info
# =========================

@router.get("/database-info")
@limiter.limit("60/minute")
async def database_info(request: Request):
    """
    Retourne les informations sur la base de donnees.
    Utilise par le frontend pour afficher le statut.
    """
    try:
        result = await asyncio.to_thread(db_cloudsql.test_connection)

        if result['status'] == 'ok':
            return {
                "status": "success",
                "exists": True,
                "is_ready": result['total_tirages'] > 0,
                "total_rows": result['total_tirages'],
                "total_draws": result['total_tirages'],
                "date_min": result['date_min'],
                "date_max": result['date_max'],
                "first_draw": result['date_min'],
                "last_draw": result['date_max'],
                "file_size_mb": 0  # N/A pour Cloud SQL
            }
        else:
            return JSONResponse(status_code=503, content={
                "status": "error",
                "exists": False,
                "is_ready": False,
                "error": result.get('error', 'Connexion echouee')
            })
    except Exception as e:
        logger.error(f"Erreur /database-info: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "exists": False,
            "is_ready": False,
            "error": "Erreur interne du serveur"
        })


# =========================
# API Database Info (light)
# =========================

@router.get("/api/database-info")
@limiter.limit("60/minute")
async def api_database_info(request: Request):
    """
    Retourne total_draws, first_draw, last_draw.
    Endpoint léger utilisé par la FAQ pour affichage dynamique.
    """
    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) as total,
                           MIN(date_de_tirage) as date_min,
                           MAX(date_de_tirage) as date_max
                    FROM tirages
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
        logger.error(f"Erreur /api/database-info: {e}")
        return JSONResponse(status_code=500, content={
            "total_draws": None,
            "first_draw": None,
            "last_draw": None
        })


# =========================
# API META Windows Info (slider)
# =========================

@router.get("/api/meta-windows-info")
@limiter.limit("60/minute")
async def api_meta_windows_info(request: Request):
    """
    Retourne les plages de dates et le nombre de tirages
    pour chaque fenêtre d'analyse (slider META).
    Un seul appel, toutes les fenêtres.
    """
    from datetime import timedelta

    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT date_de_tirage FROM tirages
                    ORDER BY date_de_tirage DESC
                """)
                all_dates = [row["date_de_tirage"] for row in cursor.fetchall()]
            finally:
                conn.close()

            total = len(all_dates)
            last_draw = all_dates[0] if all_dates else None
            first_draw = all_dates[-1] if all_dates else None

            tirages_windows = {}
            for size in [100, 200, 300, 400, 500, 600, 700, 800]:
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
        logger.error(f"Erreur /api/meta-windows-info: {e}")
        return JSONResponse(status_code=500, content={"tirages": None, "annees": None})


@router.get("/stats")
@limiter.limit("60/minute")
async def stats(request: Request):
    """
    Retourne les statistiques globales.
    """
    try:
        global_stats = await asyncio.to_thread(get_global_stats)
        return {
            "success": True,
            "stats": global_stats
        }
    except Exception as e:
        logger.error(f"Erreur /stats: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": "Erreur interne du serveur"
        })


# =========================
# API Stats Completes
# =========================

@router.get("/api/stats")
@limiter.limit("60/minute")
async def api_stats(request: Request):
    """
    Retourne les statistiques completes pour le simulateur et la page stats.
    Base sur les tirages reels de Cloud SQL.

    Returns:
        - total_tirages
        - periode (debut, fin)
        - frequences de chaque numero (1-49)
        - retards (tirages depuis derniere apparition)
        - top_chauds (5 numeros les plus frequents)
        - top_froids (5 numeros les moins frequents)
    """
    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        MIN(date_de_tirage) as date_min,
                        MAX(date_de_tirage) as date_max
                    FROM tirages
                """)
                info = cursor.fetchone()
                total_tirages = info['total']
                date_min = str(info['date_min']) if info['date_min'] else None
                date_max = str(info['date_max']) if info['date_max'] else None

                freq_map = _get_all_frequencies(cursor, "principal")
                frequences = {str(num): freq_map.get(num, 0) for num in range(1, 50)}

                ecart_map = _get_all_ecarts(cursor, "principal")
                retards = {str(num): ecart_map.get(num, total_tirages) for num in range(1, 50)}
            finally:
                conn.close()

            sorted_by_freq = sorted(
                [(int(k), v) for k, v in frequences.items()],
                key=lambda x: x[1],
                reverse=True
            )

            top_chauds = [{"numero": n, "freq": f} for n, f in sorted_by_freq[:5]]
            top_froids = [{"numero": n, "freq": f} for n, f in sorted_by_freq[-5:]]

            return {
                "success": True,
                "data": {
                    "total_tirages": total_tirages,
                    "periode": {
                        "debut": date_min,
                        "fin": date_max
                    },
                    "frequences": frequences,
                    "retards": retards,
                    "top_chauds": top_chauds,
                    "top_froids": top_froids
                },
                "error": None
            }

        return await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=30.0)

    except asyncio.TimeoutError:
        logger.error("Timeout 30s /api/stats")
        return JSONResponse(status_code=503, content={
            "success": False,
            "data": None,
            "error": "Service temporairement indisponible"
        })
    except Exception as e:
        logger.error(f"Erreur /api/stats: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "data": None,
            "error": "Erreur interne du serveur"
        })


@router.get("/api/numbers-heat")
@limiter.limit("60/minute")
async def api_numbers_heat(request: Request):
    """
    Retourne la classification chaud/neutre/froid pour chaque numero (1-49).
    Utilise par le simulateur pour colorer les boutons.
    """
    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) as total FROM tirages")
                total = cursor.fetchone()['total']

                freq_map = _get_all_frequencies(cursor, "principal")

                cursor.execute("""
                    SELECT num, MAX(date_de_tirage) as last_date FROM (
                        SELECT boule_1 as num, date_de_tirage FROM tirages
                        UNION ALL SELECT boule_2, date_de_tirage FROM tirages
                        UNION ALL SELECT boule_3, date_de_tirage FROM tirages
                        UNION ALL SELECT boule_4, date_de_tirage FROM tirages
                        UNION ALL SELECT boule_5, date_de_tirage FROM tirages
                    ) t
                    GROUP BY num
                """)
                last_dates = {row['num']: row['last_date'] for row in cursor.fetchall()}

                numbers_data = {}
                frequencies = []
                for num in range(1, 50):
                    freq = freq_map.get(num, 0)
                    last_d = last_dates.get(num)
                    numbers_data[num] = {
                        "frequency": freq,
                        "last_draw": str(last_d) if last_d else None
                    }
                    frequencies.append(freq)
            finally:
                conn.close()

            frequencies.sort(reverse=True)
            seuil_chaud = frequencies[len(frequencies) // 3]
            seuil_froid = frequencies[2 * len(frequencies) // 3]

            for num in range(1, 50):
                freq = numbers_data[num]["frequency"]
                if freq >= seuil_chaud:
                    numbers_data[num]["category"] = "hot"
                elif freq <= seuil_froid:
                    numbers_data[num]["category"] = "cold"
                else:
                    numbers_data[num]["category"] = "neutral"

            return {
                "success": True,
                "numbers": numbers_data,
                "total_tirages": total,
                "seuils": {
                    "chaud": seuil_chaud,
                    "froid": seuil_froid
                }
            }

        return await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=30.0)

    except asyncio.TimeoutError:
        logger.error("Timeout 30s /api/numbers-heat")
        return JSONResponse(status_code=503, content={
            "success": False,
            "numbers": {},
            "error": "Service temporairement indisponible"
        })
    except Exception as e:
        logger.error(f"Erreur /api/numbers-heat: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "numbers": {},
            "error": "Erreur interne du serveur"
        })


@router.get("/draw/{date}")
@limiter.limit("60/minute")
async def get_draw_by_date(request: Request, date: str):
    """
    Recherche un tirage par date (format YYYY-MM-DD).
    """
    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance
                    FROM tirages
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
                    "chance": result['numero_chance']
                }
            }
        else:
            return JSONResponse(status_code=404, content={
                "success": True,
                "found": False,
                "message": f"Aucun tirage pour la date {date}"
            })

    except Exception as e:
        logger.error(f"Erreur /draw/{date}: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "found": False,
            "message": "Erreur interne du serveur"
        })


@router.get("/api/stats/number/{number}")
@limiter.limit("60/minute")
async def api_stats_number(request: Request, number: int):
    """
    Analyse complete d'un numero specifique (1-49).
    """
    try:
        if not 1 <= number <= 49:
            return JSONResponse(status_code=400, content={
                "success": False, "message": "Numéro doit être entre 1 et 49"
            })

        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT date_de_tirage
                    FROM tirages
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
                    cursor.execute("""
                        SELECT COUNT(*) as gap
                        FROM tirages
                        WHERE date_de_tirage > %s
                    """, (last_appearance,))
                    gap_result = cursor.fetchone()
                    current_gap = gap_result['gap'] if gap_result else 0
            finally:
                conn.close()

            return {
                "success": True,
                "number": number,
                "total_appearances": total_appearances,
                "first_appearance": first_appearance,
                "last_appearance": last_appearance,
                "current_gap": current_gap,
                "appearance_dates": appearance_dates
            }

        return await asyncio.to_thread(_fetch)

    except Exception as e:
        logger.error(f"Erreur /api/stats/number/{number}: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": "Erreur interne du serveur"
        })


@router.get("/api/stats/top-flop")
@limiter.limit("60/minute")
async def api_stats_top_flop(request: Request):
    """
    Retourne le classement des numeros par frequence (Top et Flop).
    """
    try:
        def _fetch():
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                freq_map = _get_all_frequencies(cursor, "principal")
                numbers_freq = [{"number": num, "count": freq_map.get(num, 0)} for num in range(1, 50)]
            finally:
                conn.close()

            top = sorted(numbers_freq, key=lambda x: (-x['count'], x['number']))
            flop = sorted(numbers_freq, key=lambda x: (x['count'], x['number']))

            return {
                "success": True,
                "top": top,
                "flop": flop
            }

        return await asyncio.to_thread(_fetch)

    except Exception as e:
        logger.error(f"Erreur /api/stats/top-flop: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": "Erreur interne du serveur"
        })


# =========================
# API Hybride Stats (chatbot BDD)
# =========================

@router.get("/api/hybride-stats")
@limiter.limit("60/minute")
async def api_hybride_stats(
    request: Request,
    numero: int = Query(..., description="Numero a analyser"),
    type: str = Query(default="principal", description="principal ou chance")
):
    """
    Retourne les statistiques completes d'un numero pour le chatbot HYBRIDE.
    """
    if type not in ("principal", "chance"):
        return JSONResponse(status_code=400, content={
            "success": False, "data": None, "error": "type doit etre 'principal' ou 'chance'"
        })

    stats = await asyncio.to_thread(get_numero_stats, numero, type)
    if stats is None:
        return JSONResponse(status_code=404, content={
            "success": False, "data": None, "error": f"Numéro {numero} invalide pour type {type}"
        })

    return {"success": True, "data": stats, "error": None}


