"""
Backward compat — routes Loto analyse.
Thin wrappers delegating to unified routes.
V93: /ask route removed (F01 audit — generate() DEPRECATED since V58).
"""

from fastapi import APIRouter, Query, Request
from typing import Optional

from rate_limit import limiter
from config.games import ValidGame
from routes.api_analyse_unified import (
    unified_generate,
    unified_meta_analyse_local,
    unified_analyze_custom_grid,
)

router = APIRouter()

_LOTO = ValidGame.loto


# ── Wrappers ──

@router.get("/generate")
@limiter.limit("60/minute")
async def generate_endpoint(
    request: Request,
    n: int = Query(default=3, ge=1, le=10),
    mode: str = Query(default="balanced"),
):
    return await unified_generate(request=request, game=_LOTO, n=n, mode=mode)


@router.get("/api/meta-analyse-local")
@limiter.limit("60/minute")
async def api_meta_analyse_local(
    request: Request,
    window: Optional[str] = Query(default="GLOBAL"),
    years: Optional[str] = Query(default=None),
):
    return await unified_meta_analyse_local(request=request, game=_LOTO, window=window, years=years)


@router.post("/api/analyze-custom-grid")
@limiter.limit("60/minute")
async def api_analyze_custom_grid(
    request: Request,
    nums: list = Query(..., description="5 numeros principaux"),
    chance: int = Query(..., ge=1, le=10, description="Numero chance"),
):
    return await unified_analyze_custom_grid(
        request=request, game=_LOTO, nums=nums, chance=chance,
    )
