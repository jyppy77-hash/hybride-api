"""
Backward compat — routes EuroMillions data.
Thin wrappers delegating to unified routes.
"""

from fastapi import APIRouter, Query, Request
from rate_limit import limiter
from config.games import ValidGame
from routes.api_data_unified import (
    unified_tirages_count, unified_tirages_latest, unified_tirages_list,
    unified_database_info, unified_meta_windows_info,
    unified_stats, unified_numbers_heat,
    unified_draw_by_date, unified_stats_number, unified_stats_etoile,
    unified_stats_top_flop, unified_hybride_stats,
)

router = APIRouter(prefix="/api/euromillions", tags=["EuroMillions - Donnees"])

_EM = ValidGame.euromillions


@router.get("/tirages/count")
@limiter.limit("60/minute")
async def em_tirages_count(request: Request):
    return await unified_tirages_count(request=request, game=_EM)


@router.get("/tirages/latest")
@limiter.limit("60/minute")
async def em_tirages_latest(request: Request):
    return await unified_tirages_latest(request=request, game=_EM)


@router.get("/tirages/list")
@limiter.limit("60/minute")
async def em_tirages_list(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await unified_tirages_list(request=request, game=_EM, limit=limit, offset=offset)


@router.get("/database-info")
@limiter.limit("60/minute")
async def em_database_info(request: Request):
    return await unified_database_info(request=request, game=_EM)


@router.get("/meta-windows-info")
@limiter.limit("60/minute")
async def em_meta_windows_info(request: Request):
    return await unified_meta_windows_info(request=request, game=_EM)


@router.get("/stats")
@limiter.limit("60/minute")
async def em_stats(request: Request):
    return await unified_stats(request=request, game=_EM)


@router.get("/numbers-heat")
@limiter.limit("60/minute")
async def em_numbers_heat(request: Request):
    return await unified_numbers_heat(request=request, game=_EM)


@router.get("/draw/{date}")
@limiter.limit("60/minute")
async def em_get_draw_by_date(request: Request, date: str):
    return await unified_draw_by_date(request=request, game=_EM, date=date)


@router.get("/stats/number/{number}")
@limiter.limit("60/minute")
async def em_stats_number(request: Request, number: int):
    return await unified_stats_number(request=request, game=_EM, number=number)


@router.get("/stats/etoile/{number}")
@limiter.limit("60/minute")
async def em_stats_etoile(request: Request, number: int):
    return await unified_stats_etoile(request=request, game=_EM, number=number)


@router.get("/stats/top-flop")
@limiter.limit("60/minute")
async def em_stats_top_flop(request: Request):
    return await unified_stats_top_flop(request=request, game=_EM)


@router.get("/hybride-stats")
@limiter.limit("60/minute")
async def em_hybride_stats(
    request: Request,
    numero: int = Query(..., description="Numero a analyser"),
    type: str = Query(default="boule", description="boule ou etoile"),
):
    return await unified_hybride_stats(request=request, game=_EM, numero=numero, type=type)
