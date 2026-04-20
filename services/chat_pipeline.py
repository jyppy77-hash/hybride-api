import logging
import time

from services.prompt_loader import load_prompt
from services.gemini import stream_gemini_chat
from services.circuit_breaker import gemini_breaker
from services.stats_service import (
    get_numero_stats, analyze_grille_for_chat,
    get_classement_numeros, get_comparaison_numeros, get_comparaison_with_period,
    get_numeros_par_categorie,
    prepare_grilles_pitch_context, get_pair_correlations, get_triplet_correlations,
)

from services.chat_detectors import (
    _detect_mode, _is_short_continuation, _detect_prochain_tirage,
    _detect_tirage, _has_temporal_filter, _extract_temporal_date,
    _detect_numero, _detect_grille,
    _detect_requete_complexe, _detect_paires, _detect_triplets, _detect_insulte,
    _count_insult_streak, _get_insult_response, _get_insult_short,
    _get_menace_response, _detect_compliment, _count_compliment_streak,
    _get_compliment_response, _detect_out_of_range, _count_oor_streak,
    _get_oor_response, _detect_argent, _get_argent_response,
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
from services.chat_sql import (
    _get_prochain_tirage, _get_tirage_data, _generate_sql, _validate_sql,
    _ensure_limit, _execute_safe_sql, _format_sql_result, _MAX_SQL_PER_SESSION,
    ALLOWED_TABLES_LOTO,
)
from services.chat_utils import (
    FALLBACK_RESPONSE, _enrich_with_context,
    _format_tirage_context, _format_stats_context, _format_grille_context,
    _format_complex_context, _format_pairs_context, _format_triplets_context,
    _build_session_context, _format_generation_context,
)
from services.chat_responses_loto import (
    _AFFIRMATION_INVITATION_LOTO, _GAME_KEYWORD_INVITATION_LOTO,
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
    _TIRAGE_NOT_FOUND_LOTO,
)
import db_cloudsql

logger = logging.getLogger(__name__)

# F02: cached draw count for {DRAW_COUNT} placeholder injection
_draw_count_cache: dict[str, tuple[float, int]] = {}  # game -> (timestamp, count)
_DRAW_COUNT_TTL = 3600  # 1h


async def _get_draw_count(game: str = "loto") -> int:
    """Return draw count from DB with 1h cache. Returns 0 on error.

    TTL 1h: after a new draw, count may be stale by 1 for up to 60min.
    This is intentional — cosmetic impact only ("~980 tirages" vs "~981").
    """
    now = time.monotonic()
    cached = _draw_count_cache.get(game)
    if cached and (now - cached[0]) < _DRAW_COUNT_TTL:
        return cached[1]
    table = "tirages" if game == "loto" else "tirages_euromillions"
    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            row = await cursor.fetchone()
            count = row["cnt"] if row else 0
            _draw_count_cache[game] = (now, count)
            return count
    except Exception as e:
        logger.warning("[DRAW_COUNT] Error fetching count for %s: %s", game, e)
        return cached[1] if cached else 0


# =========================
# HYBRIDE Chatbot — Pipeline 12 phases
# =========================

def _build_loto_config():
    """Build Loto game config at call time so test patches on module-level bindings are picked up.

    F03 V74: game-agnostic detectors provided by _build_config_base(); only Loto-specific
    overrides are listed here.
    """
    return _build_config_base({
        # Identity
        "game": "loto",
        "log_prefix": "[HYBRIDE CHAT]",
        "debug_prefix": "[DEBUG]",
        # Prompt
        "load_system_prompt": lambda lang: load_prompt("CHATBOT"),
        "draw_count_game": "loto",
        # Fallback
        "get_fallback": lambda lang: FALLBACK_RESPONSE,
        # Mode
        "detect_mode": _detect_mode,
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
        "extract_exclusions": lambda msg: _extract_exclusions(msg, max_num=49),
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
        "get_insult_short": lambda lang: _get_insult_short(),
        "get_menace_response": lambda lang: _get_menace_response(),
        "get_insult_response": lambda lang, streak, hist: _get_insult_response(streak, hist),
        # Phase C
        "get_compliment_response": lambda lang, ctype, streak, hist: _get_compliment_response(ctype, streak, hist),
        # Phase SALUTATION
        "salutation_game": "loto",
        # Phase G
        "gen_engine_module": "engine.hybride",
        "forced_secondary_key": "forced_chance",
        "gen_secondary_param": "forced_chance",
        "store_exclusions": False,
        "format_generation_context": _format_generation_context,
        # Phase A
        "detect_argent": _detect_argent,
        "get_argent_response": lambda msg, lang: _get_argent_response(msg, lang),
        # Phase GEO — intentionnellement absente côté Loto.
        # Le Loto est géré par la FDJ et disponible uniquement en France métropolitaine + DOM-TOM.
        # Contrairement à EuroMillions (9 pays × 6 langues), aucune détection géographique nécessaire.
        # Ref: Audit 360° Chatbot HYBRIDE V81, faille F07.
        # Phase AFFIRMATION
        "affirmation_invitation": _AFFIRMATION_INVITATION_LOTO,
        "game_keyword_invitation": _GAME_KEYWORD_INVITATION_LOTO,
        # Phase EVAL
        "eval_game": "loto",
        "secondary_field": "chance",
        "format_grille_context": _format_grille_context,
        "analyze_grille_for_chat": analyze_grille_for_chat,
        "analyze_passes_lang": False,
        # Phase 0-bis
        "detect_prochain_tirage": _detect_prochain_tirage,
        "get_prochain_tirage": _get_prochain_tirage,
        # Phase T
        "get_tirage_data": _get_tirage_data,
        "format_tirage_context": _format_tirage_context,
        "tirage_not_found": _TIRAGE_NOT_FOUND_LOTO,
        # Phase 2
        "detect_grille": _detect_grille,
        # Phase 3
        "detect_requete_complexe": _detect_requete_complexe,
        "format_complex_context": _format_complex_context,
        "get_classement": get_classement_numeros,
        "get_comparaison": get_comparaison_numeros,
        "get_categorie": get_numeros_par_categorie,
        "get_comparaison_with_period": get_comparaison_with_period,
        # Phase P
        "detect_triplets": _detect_triplets,
        "format_triplets_context": _format_triplets_context,
        "get_triplet_correlations": get_triplet_correlations,
        "detect_paires": _detect_paires,
        "format_pairs_context": _format_pairs_context,
        "get_pair_correlations": get_pair_correlations,
        # Phase OOR
        "detect_oor": _detect_out_of_range,
        "count_oor_streak": _count_oor_streak,
        "get_oor_response": lambda lang, num, oor_type, streak: _get_oor_response(num, oor_type, streak),
        # Phase 1
        "detect_numero": _detect_numero,
        "get_numero_stats": get_numero_stats,
        "format_stats_context": _format_stats_context,
        # Phase SQL
        "generate_sql": _generate_sql,
        "validate_sql": lambda sql: _validate_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO),
        "ensure_limit": _ensure_limit,
        "execute_safe_sql": lambda sql: _execute_safe_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO),
        "format_sql_result": _format_sql_result,
        "max_sql_per_session": _MAX_SQL_PER_SESSION,
        "sql_log_prefix": "[TEXT2SQL]",
        # Final
        "build_session_context": _build_session_context,
    })


async def _prepare_chat_context(message: str, history: list, page: str, http_client, lang: str = "fr"):
    """
    Phases I-SQL : prepare le contexte pour l'appel Gemini.
    Retourne (early_return_or_None, ctx_dict_or_None).
    Si early_return n'est pas None, c'est une reponse complete (insult/compliment/OOR).
    Sinon, ctx_dict contient les cles pour l'appel Gemini.
    Delegates to _prepare_chat_context_base with Loto config.
    """
    return await _prepare_chat_context_base(
        message, history, page, http_client, lang, _build_loto_config(),
    )


def _log_from_meta(meta, module, lang, message, response_preview="",
                    is_error=False, error_detail=None):
    """Helper: call log_chat_exchange from _chat_meta dict (delegates to shared)."""
    _log_from_meta_shared(meta, module, lang, message, response_preview,
                          is_error=is_error, error_detail=error_detail)


async def handle_chat(message: str, history: list, page: str, http_client, lang: str = "fr") -> dict:
    """Pipeline 12 phases du chatbot HYBRIDE. Retourne dict(response, source, mode)."""
    return await handle_chat_common(
        message, history, page, http_client, lang,
        prepare_context_fn=_prepare_chat_context,
        default_fallback=FALLBACK_RESPONSE,
        log_prefix="[HYBRIDE CHAT]", module="loto",
        breaker=gemini_breaker,
    )


def _sse_event(data):
    """Format dict as SSE event line (delegates to shared)."""
    return _sse_event_shared(data)


async def handle_chat_stream(message: str, history: list, page: str, http_client, lang: str = "fr"):
    """Async generator — SSE streaming du chatbot HYBRIDE. Yields SSE event strings."""
    async for event in handle_stream_common(
        message, history, page, http_client, lang,
        prepare_context_fn=_prepare_chat_context,
        default_fallback=FALLBACK_RESPONSE,
        log_prefix="[HYBRIDE CHAT]", module="loto",
        call_type="chat_loto",
        stream_fn=stream_gemini_chat, breaker=gemini_breaker,
    ):
        yield event


# =========================
# PITCH GRILLES — Gemini
# =========================

async def handle_pitch(grilles: list, http_client, lang: str = "fr") -> dict:
    """Genere des pitchs HYBRIDE personnalises pour chaque grille via Gemini."""
    # Validation Loto
    if not grilles or len(grilles) > 5:
        return {"success": False, "data": None, "error": "Entre 1 et 5 grilles requises", "status_code": 400}
    for i, g in enumerate(grilles):
        if len(g.numeros) != 5:
            return {"success": False, "data": None, "error": f"Grille {i+1}: 5 numéros requis", "status_code": 400}
        if len(set(g.numeros)) != 5:
            return {"success": False, "data": None, "error": f"Grille {i+1}: numéros doivent être uniques", "status_code": 400}
        if not all(1 <= n <= 49 for n in g.numeros):
            return {"success": False, "data": None, "error": f"Grille {i+1}: numéros entre 1 et 49", "status_code": 400}
        if g.chance is not None and not 1 <= g.chance <= 10:
            return {"success": False, "data": None, "error": f"Grille {i+1}: chance entre 1 et 10", "status_code": 400}

    grilles_data = [{"numeros": g.numeros, "chance": g.chance, "score_conformite": g.score_conformite, "severity": g.severity} for g in grilles]
    return await handle_pitch_common(
        grilles_data, http_client, lang,
        context_coro=prepare_grilles_pitch_context(grilles_data),
        load_prompt_fn=load_prompt, prompt_name="PITCH_GRILLE",
        log_prefix="[PITCH]", breaker=gemini_breaker,
    )
