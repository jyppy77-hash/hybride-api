"""
Backward compat — routes EuroMillions chat.
Thin wrappers + re-exports for tests.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from em_schemas import EMChatRequest, EMChatResponse, EMPitchGrillesRequest
from rate_limit import limiter
from services.chat_pipeline_em import handle_chat_em, handle_pitch_em

# Re-exports pour compatibilite (tests et imports existants)
from services.chat_detectors_em import (  # noqa: F401
    _detect_mode_em, _detect_prochain_tirage_em,
    _detect_numero_em, _detect_grille_em,
    _detect_requete_complexe_em, _detect_out_of_range_em,
    _count_oor_streak_em, _get_oor_response_em,
    _get_insult_response_em, _get_insult_short_em, _get_menace_response_em,
    _get_compliment_response_em,
    META_KEYWORDS,
    _INSULT_L1_EM, _INSULT_L2_EM, _INSULT_L3_EM, _INSULT_L4_EM,
    _INSULT_SHORT_EM, _MENACE_RESPONSES_EM,
    _COMPLIMENT_L1_EM, _COMPLIMENT_L2_EM, _COMPLIMENT_L3_EM,
    _COMPLIMENT_LOVE_EM, _COMPLIMENT_MERCI_EM,
    _OOR_L1_EM, _OOR_L2_EM, _OOR_L3_EM,
    _OOR_CLOSE_EM, _OOR_ZERO_NEG_EM, _OOR_ETOILE_EM,
)
from services.chat_sql_em import (  # noqa: F401
    _get_prochain_tirage_em, _get_tirage_data_em, _generate_sql_em,
    _JOURS_TIRAGE_EM, _JOURS_FR,
    _validate_sql, _ensure_limit, _execute_safe_sql, _format_sql_result,
    _MAX_SQL_PER_SESSION, _SQL_FORBIDDEN,
)
from services.chat_utils_em import (  # noqa: F401
    FALLBACK_RESPONSE_EM,
    _format_tirage_context_em, _format_stats_context_em,
    _format_grille_context_em, _format_complex_context_em,
    _build_session_context_em,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/euromillions/hybride-chat")
@limiter.limit("10/minute")
async def api_hybride_chat_em(request: Request, payload: EMChatRequest):
    """Endpoint chatbot HYBRIDE EuroMillions — conversation via Gemini 2.0 Flash."""
    result = await handle_chat_em(
        payload.message,
        payload.history,
        payload.page,
        request.app.state.httpx_client,
    )
    return EMChatResponse(**result)


@router.post("/api/euromillions/pitch-grilles")
@limiter.limit("10/minute")
async def api_pitch_grilles_em(request: Request, payload: EMPitchGrillesRequest):
    """Genere des pitchs HYBRIDE personnalises pour chaque grille EM via Gemini."""
    result = await handle_pitch_em(
        payload.grilles,
        request.app.state.httpx_client,
    )
    status = result.pop("status_code", 200)
    if status != 200:
        return JSONResponse(status_code=status, content=result)
    return JSONResponse(content=result)
