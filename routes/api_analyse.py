"""
Backward compat — routes Loto analyse.
Thin wrappers delegating to unified routes.
Keeps /ask (Loto-only, no EM equivalent).
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from typing import Optional
import logging

from engine.hybride import generate
from schemas import AskPayload
from rate_limit import limiter
from config.games import ValidGame
from routes.api_analyse_unified import (
    unified_generate,
    unified_meta_analyse_local,
    unified_analyze_custom_grid,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_LOTO = ValidGame.loto


# ── /ask — Loto-only, stays here ──

@router.post("/ask")
@limiter.limit("60/minute")
async def ask(request: Request, payload: AskPayload):
    """Endpoint principal du moteur HYBRIDE."""
    try:
        result = await generate(payload.prompt)
        return {"success": True, "response": result}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal engine error")


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
