"""
Backward compat — routes Loto data.
Thin wrappers delegating to unified routes.
"""

from fastapi import APIRouter, Query, Request
from rate_limit import limiter
from config.games import ValidGame
from routes.api_data_unified import (
    unified_tirages_count, unified_tirages_latest, unified_tirages_list,
    unified_database_info, unified_meta_windows_info,
    unified_stats, unified_numbers_heat,
    unified_draw_by_date, unified_stats_number,
    unified_stats_top_flop, unified_hybride_stats,
)
from engine.stats import get_global_stats
from fastapi.responses import JSONResponse
import logging
import db_cloudsql

logger = logging.getLogger(__name__)

router = APIRouter()

_LOTO = ValidGame.loto


# ── Tirages ──

@router.get("/api/tirages/count")
@limiter.limit("60/minute")
async def api_tirages_count(request: Request):
    return await unified_tirages_count(request=request, game=_LOTO)


@router.get("/api/tirages/latest")
@limiter.limit("60/minute")
async def api_tirages_latest(request: Request):
    return await unified_tirages_latest(request=request, game=_LOTO)


@router.get("/api/tirages/list")
@limiter.limit("60/minute")
async def api_tirages_list(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await unified_tirages_list(request=request, game=_LOTO, limit=limit, offset=offset)


# ── Database info ──

@router.get("/database-info")
@limiter.limit("60/minute")
async def database_info(request: Request):
    """Legacy /database-info (full format with is_ready etc.)."""
    try:
        result = await db_cloudsql.test_connection()
        if result['status'] == 'ok':
            return {
                "status": "success", "exists": True,
                "is_ready": result['total_tirages'] > 0,
                "total_rows": result['total_tirages'],
                "total_draws": result['total_tirages'],
                "date_min": result['date_min'], "date_max": result['date_max'],
                "first_draw": result['date_min'], "last_draw": result['date_max'],
                "file_size_mb": 0,
            }
        else:
            return JSONResponse(status_code=503, content={
                "status": "error", "exists": False, "is_ready": False,
                "error": result.get('error', 'Connexion echouee'),
            })
    except Exception as e:
        logger.error(f"Erreur /database-info: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error", "exists": False, "is_ready": False,
            "error": "Erreur interne du serveur",
        })


@router.get("/api/database-info")
@limiter.limit("60/minute")
async def api_database_info(request: Request):
    return await unified_database_info(request=request, game=_LOTO)


@router.get("/api/meta-windows-info")
@limiter.limit("60/minute")
async def api_meta_windows_info(request: Request):
    return await unified_meta_windows_info(request=request, game=_LOTO)


# ── Stats ──

@router.get("/stats")
@limiter.limit("60/minute")
async def stats(request: Request):
    """Legacy /stats — uses engine.stats.get_global_stats."""
    try:
        global_stats = await get_global_stats()
        return {"success": True, "stats": global_stats}
    except Exception as e:
        logger.error(f"Erreur /stats: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "message": "Erreur interne du serveur"
        })


@router.get("/api/stats")
@limiter.limit("60/minute")
async def api_stats(request: Request):
    return await unified_stats(request=request, game=_LOTO)


@router.get("/api/numbers-heat")
@limiter.limit("60/minute")
async def api_numbers_heat(request: Request):
    return await unified_numbers_heat(request=request, game=_LOTO)


@router.get("/draw/{date}")
@limiter.limit("60/minute")
async def get_draw_by_date(request: Request, date: str):
    return await unified_draw_by_date(request=request, game=_LOTO, date=date)


@router.get("/api/stats/number/{number}")
@limiter.limit("60/minute")
async def api_stats_number(request: Request, number: int):
    return await unified_stats_number(request=request, game=_LOTO, number=number)


@router.get("/api/stats/top-flop")
@limiter.limit("60/minute")
async def api_stats_top_flop(request: Request):
    return await unified_stats_top_flop(request=request, game=_LOTO)


@router.get("/api/hybride-stats")
@limiter.limit("60/minute")
async def api_hybride_stats(
    request: Request,
    numero: int = Query(..., description="Numero a analyser"),
    type: str = Query(default="principal", description="principal ou chance"),
):
    return await unified_hybride_stats(request=request, game=_LOTO, numero=numero, type=type)
