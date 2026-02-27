"""
Routes unifiees /api/{game}/... — Chat (hybride-chat, pitch-grilles)
Phase 10 — remplace la duplication api_chat.py / api_chat_em.py
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from rate_limit import limiter
from config.games import ValidGame, get_config, get_chat_pipeline
from schemas import HybrideChatRequest, HybrideChatResponse, PitchGrillesRequest
from em_schemas import EMChatRequest, EMChatResponse, EMPitchGrillesRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/{game}", tags=["Unified - Chat"])


@router.post("/hybride-chat")
@limiter.limit("10/minute")
async def unified_hybride_chat(request: Request, game: ValidGame):
    cfg = get_config(game)
    pipeline = get_chat_pipeline(cfg)

    body = await request.json()

    if game == ValidGame.loto:
        payload = HybrideChatRequest(**body)
        result = await pipeline.handle_chat(
            payload.message,
            payload.history,
            payload.page,
            request.app.state.httpx_client,
        )
        return HybrideChatResponse(**result)
    else:
        payload = EMChatRequest(**body)
        result = await pipeline.handle_chat_em(
            payload.message,
            payload.history,
            payload.page,
            request.app.state.httpx_client,
            lang=payload.lang,
        )
        return EMChatResponse(**result)


@router.post("/pitch-grilles")
@limiter.limit("10/minute")
async def unified_pitch_grilles(request: Request, game: ValidGame):
    cfg = get_config(game)
    pipeline = get_chat_pipeline(cfg)

    body = await request.json()

    if game == ValidGame.loto:
        payload = PitchGrillesRequest(**body)
        result = await pipeline.handle_pitch(
            payload.grilles,
            request.app.state.httpx_client,
        )
    else:
        payload = EMPitchGrillesRequest(**body)
        result = await pipeline.handle_pitch_em(
            payload.grilles,
            request.app.state.httpx_client,
            lang=payload.lang if hasattr(payload, "lang") else "fr",
        )

    status = result.pop("status_code", 200)
    if status != 200:
        return JSONResponse(status_code=status, content=result)
    return JSONResponse(content=result)
