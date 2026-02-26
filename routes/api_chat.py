"""
Backward compat — routes Loto chat.
Thin wrappers delegating to unified chat + re-exports for tests.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from schemas import HybrideChatRequest, HybrideChatResponse, PitchGrillesRequest
from rate_limit import limiter
from services.chat_pipeline import handle_chat, handle_pitch

# Re-exports pour api_chat_em.py et les tests
# (preserve la surface publique existante)
from services.chat_detectors import (  # noqa: F401
    CONTINUATION_PATTERNS, _is_short_continuation,
    _detect_insulte, _insult_targets_bot, _count_insult_streak,
    _get_insult_response, _get_insult_short, _get_menace_response,
    _detect_compliment, _compliment_targets_bot, _count_compliment_streak,
    _get_compliment_response, _detect_out_of_range, _count_oor_streak,
    _get_oor_response, _detect_tirage, _detect_mode,
    _detect_prochain_tirage, _detect_numero, _detect_grille,
    _detect_requete_complexe, _has_temporal_filter,
    META_KEYWORDS,
    _INSULTE_MOTS, _INSULTE_PHRASES, _MENACE_PATTERNS,
    _INSULT_L1, _INSULT_L2, _INSULT_L3, _INSULT_L4,
    _INSULT_SHORT, _MENACE_RESPONSES,
    _COMPLIMENT_PHRASES, _COMPLIMENT_LOVE_PHRASES, _COMPLIMENT_SOLO_WORDS,
    _COMPLIMENT_L1, _COMPLIMENT_L2, _COMPLIMENT_L3,
    _COMPLIMENT_LOVE, _COMPLIMENT_MERCI,
    _OOR_L1, _OOR_L2, _OOR_L3, _OOR_CLOSE, _OOR_ZERO_NEG, _OOR_CHANCE,
    _JOURS_TIRAGE, _JOURS_FR, _JOURS_SEMAINE,
    _TIRAGE_KW, _MOIS_TO_NUM, _MOIS_NOM_RE, _MOIS_RE,
    _TEMPORAL_PATTERNS,
)
from services.chat_sql import (  # noqa: F401
    _validate_sql, _ensure_limit, _execute_safe_sql, _format_sql_result,
    _generate_sql, _get_tirage_data, _get_prochain_tirage,
    _MAX_SQL_PER_SESSION, _SQL_FORBIDDEN,
)
from services.chat_utils import (  # noqa: F401
    FALLBACK_RESPONSE, _enrich_with_context, _clean_response,
    _get_sponsor_if_due, _strip_sponsor_from_text, _format_date_fr,
    _format_tirage_context, _format_stats_context, _format_periode_fr,
    _format_grille_context, _format_complex_context,
    _build_session_context, _MOIS_FR,
    _load_sponsors_config,
)
from services.prompt_loader import load_prompt  # noqa: F401

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/hybride-chat")
@limiter.limit("10/minute")
async def api_hybride_chat(request: Request, payload: HybrideChatRequest):
    """Endpoint chatbot HYBRIDE — conversation via Gemini 2.0 Flash."""
    result = await handle_chat(
        payload.message,
        payload.history,
        payload.page,
        request.app.state.httpx_client,
    )
    return HybrideChatResponse(**result)


@router.post("/api/pitch-grilles")
@limiter.limit("10/minute")
async def api_pitch_grilles(request: Request, payload: PitchGrillesRequest):
    """Genere des pitchs HYBRIDE personnalises pour chaque grille via Gemini."""
    result = await handle_pitch(
        payload.grilles,
        request.app.state.httpx_client,
    )
    status = result.pop("status_code", 200)
    if status != 200:
        return JSONResponse(status_code=status, content=result)
    return JSONResponse(content=result)
