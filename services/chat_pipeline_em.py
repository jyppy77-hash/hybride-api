"""
Service metier — pipeline chatbot EuroMillions.
Orchestre les 12 phases du chatbot EM (detection → enrichissement → Gemini).
Meme pattern que chat_pipeline.py (Loto) avec detecteurs/formatage EM.
"""

import logging

from services.prompt_loader import load_prompt_em
from services.gemini import stream_gemini_chat
from services.circuit_breaker import gemini_breaker, gemini_breaker_pitch
from services.em_stats_service import (
    get_numero_stats, analyze_grille_for_chat,
    get_classement_numeros, get_comparaison_numeros, get_comparaison_with_period,
    get_numeros_par_categorie,
    prepare_grilles_pitch_context, get_pair_correlations, get_triplet_correlations,
    get_star_pair_correlations,
)

from services.chat_detectors import (
    _detect_insulte, _count_insult_streak,
    _detect_compliment, _count_compliment_streak,
    _is_short_continuation, _detect_tirage, _has_temporal_filter, _extract_temporal_date,
    _detect_generation, _detect_generation_mode, _extract_forced_numbers, _extract_grid_count,
    _extract_exclusions,
    _detect_cooccurrence_high_n, _get_cooccurrence_high_n_response,
    _detect_site_rating, get_site_rating_response,
    _is_affirmation_simple, _detect_game_keyword_alone,  # V51
    _detect_salutation, _get_salutation_response,  # V65
    _has_data_signal,  # V65
    _detect_grid_evaluation,  # V70
    _is_refusal, _get_refusal_response,  # V98c
    _sql_continuation_reroute,  # V125 Sous-phase 2 Volet B
    _is_user_sql_request,  # V126 L13 Volet B'
)
from services.chat_detectors_em import (
    _detect_mode_em, _detect_prochain_tirage_em,
    _detect_numero_em, _detect_grille_em,
    _detect_requete_complexe_em, _detect_paires_em, _detect_triplets_em,
    _detect_out_of_range_em, _count_oor_streak_em,
    _detect_argent_em, _get_argent_response_em,
    _detect_country_em, _get_country_context_em,
    _wants_both_boules_and_stars,
)
from services.chat_responses_em_multilang import (
    get_insult_response, get_insult_short, get_menace_response,
    get_compliment_response, get_oor_response, get_fallback,
    _AFFIRMATION_INVITATION_EM, _GAME_KEYWORD_INVITATION_EM,  # V70 F05
)
from services.chat_sql_em import (
    _get_prochain_tirage_em, _get_tirage_data_em, _generate_sql_em,
    _validate_sql, _ensure_limit, _execute_safe_sql, _format_sql_result,
    _MAX_SQL_PER_SESSION, ALLOWED_TABLES_EM,
)
from services.chat_utils import (
    _enrich_with_context,
)
from services.chat_utils_em import (
    _format_tirage_context_em, _format_stats_context_em,
    _format_grille_context_em, _format_complex_context_em,
    _format_pairs_context_em, _format_triplets_context_em,
    _format_star_pairs_context_em,
    _build_session_context_em,
    _format_generation_context_em,
)
from services.chat_pipeline_shared import (
    sse_event as _sse_event_shared,
    log_from_meta as _log_from_meta_shared,
    call_gemini_and_respond,  # noqa: F401 — re-exported for test patches
    stream_and_respond,  # noqa: F401 — re-exported for test patches
    handle_pitch_common,
    handle_chat_common, handle_stream_common,  # F07 V98
    _prepare_chat_context_base,
    _build_config_base,  # F03 V74
    _TIRAGE_NOT_FOUND_EM,
)

logger = logging.getLogger(__name__)


# =========================
# HYBRIDE EuroMillions Chatbot — Pipeline 12 phases
# =========================

def _build_em_config():
    """Build EM game config at call time so test patches on module-level bindings are picked up.

    F03 V74: game-agnostic detectors provided by _build_config_base(); only EM-specific
    overrides are listed here.
    """
    return _build_config_base({
        # Identity
        "game": "em",
        "log_prefix": "[EM CHAT]",
        "debug_prefix": "[EM DEBUG]",
        # Prompt
        "load_system_prompt": lambda lang: load_prompt_em("prompt_hybride_em", lang=lang),
        "draw_count_game": "euromillions",
        # Fallback
        "get_fallback": get_fallback,
        # Mode
        "detect_mode": _detect_mode_em,
        # Shared detectors — must reference this module's bindings for test patch compat
        "detect_insulte": _detect_insulte,
        "count_insult_streak": _count_insult_streak,
        "detect_compliment": _detect_compliment,
        "count_compliment_streak": _count_compliment_streak,
        "detect_site_rating": _detect_site_rating,
        "get_site_rating_response": lambda lang: get_site_rating_response(lang),
        "is_short_continuation": _is_short_continuation,
        "detect_tirage": _detect_tirage,
        "has_temporal_filter": _has_temporal_filter,
        "extract_temporal_date": _extract_temporal_date,
        "detect_generation": _detect_generation,
        "detect_generation_mode": _detect_generation_mode,
        "extract_forced_numbers": _extract_forced_numbers,
        "extract_grid_count": _extract_grid_count,
        "extract_exclusions": lambda msg: _extract_exclusions(msg, max_num=50),
        "detect_cooccurrence_high_n": _detect_cooccurrence_high_n,
        "get_cooccurrence_high_n_response": _get_cooccurrence_high_n_response,
        "is_affirmation_simple": _is_affirmation_simple,
        "is_refusal": _is_refusal,  # V98c
        "get_refusal_response": _get_refusal_response,  # V98c
        "sql_continuation_reroute": _sql_continuation_reroute,  # V125 Sous-phase 2 Volet B
        "is_user_sql_request": _is_user_sql_request,  # V126 L13 Volet B'
        "detect_game_keyword_alone": _detect_game_keyword_alone,
        "detect_salutation": _detect_salutation,
        "get_salutation_response": _get_salutation_response,
        "has_data_signal": _has_data_signal,
        "detect_grid_evaluation": _detect_grid_evaluation,
        "enrich_with_context": _enrich_with_context,
        # Phase I
        "get_insult_short": get_insult_short,
        "get_menace_response": get_menace_response,
        "get_insult_response": get_insult_response,
        # Phase C
        "get_compliment_response": get_compliment_response,
        # Phase SALUTATION
        "salutation_game": "em",
        # Phase G
        "gen_engine_module": "engine.hybride_em",
        "forced_secondary_key": "forced_etoiles",
        "gen_secondary_param": "forced_etoiles",
        "store_exclusions": True,
        "format_generation_context": _format_generation_context_em,
        # Phase A
        "detect_argent": _detect_argent_em,
        "get_argent_response": lambda msg, lang: _get_argent_response_em(msg, lang),
        # Phase GEO
        "detect_country": _detect_country_em,
        "get_country_context": _get_country_context_em,
        # Phase AFFIRMATION
        "affirmation_invitation": _AFFIRMATION_INVITATION_EM,
        "game_keyword_invitation": _GAME_KEYWORD_INVITATION_EM,
        # Phase EVAL
        "eval_game": "em",
        "secondary_field": "etoiles",
        "format_grille_context": _format_grille_context_em,
        "analyze_grille_for_chat": analyze_grille_for_chat,
        "analyze_passes_lang": True,
        # Phase 0-bis
        "detect_prochain_tirage": _detect_prochain_tirage_em,
        "get_prochain_tirage": _get_prochain_tirage_em,
        # Phase T
        "get_tirage_data": _get_tirage_data_em,
        "format_tirage_context": _format_tirage_context_em,
        "tirage_not_found": _TIRAGE_NOT_FOUND_EM,
        # Phase 2
        "detect_grille": _detect_grille_em,
        # Phase 3
        "detect_requete_complexe": _detect_requete_complexe_em,
        "format_complex_context": _format_complex_context_em,
        "get_classement": get_classement_numeros,
        "get_comparaison": get_comparaison_numeros,
        "get_categorie": get_numeros_par_categorie,
        "get_comparaison_with_period": get_comparaison_with_period,
        "wants_both_fn": _wants_both_boules_and_stars,
        # Phase P
        "detect_triplets": _detect_triplets_em,
        "format_triplets_context": _format_triplets_context_em,
        "get_triplet_correlations": get_triplet_correlations,
        "detect_paires": _detect_paires_em,
        "format_pairs_context": _format_pairs_context_em,
        "get_pair_correlations": get_pair_correlations,
        "get_star_pair_correlations": get_star_pair_correlations,
        "format_star_pairs_context": _format_star_pairs_context_em,
        # Phase OOR
        "detect_oor": _detect_out_of_range_em,
        "count_oor_streak": _count_oor_streak_em,
        "get_oor_response": get_oor_response,
        # Phase 1
        "detect_numero": _detect_numero_em,
        "get_numero_stats": get_numero_stats,
        "format_stats_context": _format_stats_context_em,
        # Phase SQL
        "generate_sql": _generate_sql_em,
        "validate_sql": lambda sql: _validate_sql(sql, allowed_tables=ALLOWED_TABLES_EM),
        "ensure_limit": _ensure_limit,
        "execute_safe_sql": lambda sql: _execute_safe_sql(sql, allowed_tables=ALLOWED_TABLES_EM),
        "format_sql_result": _format_sql_result,
        "max_sql_per_session": _MAX_SQL_PER_SESSION,
        "sql_log_prefix": "[EM TEXT2SQL]",
        "sql_gen_kwargs": lambda lang: {"lang": lang},
        # Final
        "build_session_context": _build_session_context_em,
    })


async def _prepare_chat_context_em(message: str, history: list, page: str, http_client, lang: str = "fr"):
    """
    Phases I-SQL EM : prepare le contexte pour l'appel Gemini.
    Retourne (early_return_or_None, ctx_dict_or_None).
    Delegates to _prepare_chat_context_base with EM config.
    """
    return await _prepare_chat_context_base(
        message, history, page, http_client, lang, _build_em_config(),
    )


def _log_from_meta_em(meta, message, response_preview="",
                      is_error=False, error_detail=None):
    """Helper: call log_chat_exchange from _chat_meta dict (EM, delegates to shared)."""
    _log_from_meta_shared(meta, "em", meta.get("lang", "fr") if meta else "fr",
                          message, response_preview, is_error=is_error, error_detail=error_detail)


async def handle_chat_em(message: str, history: list, page: str, http_client, lang: str = "fr") -> dict:
    """Pipeline 12 phases du chatbot HYBRIDE EuroMillions. Retourne dict(response, source, mode)."""
    return await handle_chat_common(
        message, history, page, http_client, lang,
        prepare_context_fn=_prepare_chat_context_em,
        default_fallback="",  # EM uses ctx["fallback"] set by _build_em_config
        log_prefix="[EM CHAT]", module="em",
        breaker=gemini_breaker,
        sponsor_kwargs={"lang": lang, "module": "em"},
    )


def _sse_event_em(data):
    """Format dict as SSE event line (delegates to shared)."""
    return _sse_event_shared(data)


async def handle_chat_stream_em(message: str, history: list, page: str, http_client, lang: str = "fr"):
    """Async generator — SSE streaming du chatbot HYBRIDE EuroMillions. Yields SSE event strings."""
    async for event in handle_stream_common(
        message, history, page, http_client, lang,
        prepare_context_fn=_prepare_chat_context_em,
        default_fallback="",  # EM uses ctx["fallback"] set by _build_em_config
        log_prefix="[EM CHAT]", module="em",
        call_type="chat_em",
        stream_fn=stream_gemini_chat, breaker=gemini_breaker,
        sponsor_kwargs={"lang": lang, "module": "em"},
    ):
        yield event


# =========================
# PITCH GRILLES EM — Gemini
# =========================

async def handle_pitch_em(grilles: list, http_client, lang: str = "fr") -> dict:
    """Genere des pitchs HYBRIDE personnalises pour chaque grille EM via Gemini."""
    # Validation EM
    if not grilles or len(grilles) > 5:
        return {"success": False, "data": None, "error": "Entre 1 et 5 grilles requises", "status_code": 400}
    for i, g in enumerate(grilles):
        if len(g.numeros) != 5:
            return {"success": False, "data": None, "error": f"Grille {i+1}: 5 numéros requis", "status_code": 400}
        if len(set(g.numeros)) != 5:
            return {"success": False, "data": None, "error": f"Grille {i+1}: numéros doivent être uniques", "status_code": 400}
        if not all(1 <= n <= 50 for n in g.numeros):
            return {"success": False, "data": None, "error": f"Grille {i+1}: numéros entre 1 et 50", "status_code": 400}
        if g.etoiles is not None:
            if len(g.etoiles) > 2:
                return {"success": False, "data": None, "error": f"Grille {i+1}: maximum 2 étoiles", "status_code": 400}
            if len(g.etoiles) != len(set(g.etoiles)):
                return {"success": False, "data": None, "error": f"Grille {i+1}: étoiles doivent être uniques", "status_code": 400}
            if not all(1 <= e <= 12 for e in g.etoiles):
                return {"success": False, "data": None, "error": f"Grille {i+1}: étoiles entre 1 et 12", "status_code": 400}

    grilles_data = [{"numeros": g.numeros, "etoiles": g.etoiles, "score_conformite": g.score_conformite, "severity": g.severity} for g in grilles]
    return await handle_pitch_common(
        grilles_data, http_client, lang,
        context_coro=prepare_grilles_pitch_context(grilles_data, lang=lang),
        load_prompt_fn=lambda name: load_prompt_em(name, lang=lang),
        prompt_name="prompt_pitch_grille_em",
        log_prefix="[EM PITCH]", breaker=gemini_breaker_pitch,
    )
