"""
Shared helpers for Loto and EM chat pipelines — V71 R3a.

Extracts mechanically identical blocks from chat_pipeline.py and chat_pipeline_em.py.
Callables are passed as parameters so that test patches on module-level bindings
in the pipeline files continue to work.

Extracted blocks:
- sse_event: SSE event formatter (was duplicated as _sse_event / _sse_event_em)
- log_from_meta: chat_logger wrapper (was _log_from_meta / _log_from_meta_em)
- build_gemini_contents: history processing loop (insult-stripping, role mapping)
- run_text_to_sql: Phase SQL block (~80 lines)
- call_gemini_and_respond: handle_chat Gemini call + response extraction + fallback
- stream_and_respond: handle_chat_stream SSE streaming loop + fallback
- handle_pitch_common: pitch validation + Gemini call + JSON parsing
- parse_pitch_json: backtick cleaning + JSON parse + sanitize

Shared constants (V72):
- _QUESTION_KEYWORDS_INSULT: Phase I keyword detection (6 langs)
- _QUESTION_KEYWORDS_COMPLIMENT: Phase C keyword detection (6 langs)
- ANTI_REINTRO_BLOCK: anti-re-introduction system prompt block
- _TIRAGE_NOT_FOUND_LOTO / _TIRAGE_NOT_FOUND_EM: tirage introuvable i18n messages
"""

import os
import re
import json
import asyncio
import logging
import time
import importlib
import httpx

from services.circuit_breaker import gemini_breaker, CircuitOpenError, GeminiCircuitBreaker
from services.gemini import GEMINI_MODEL_URL, stream_gemini_chat
from services.gemini_shared import _gemini_call_with_fallback
from services.chat_utils import (
    _clean_response, _strip_non_latin, _get_sponsor_if_due,
    _strip_sponsor_from_text, _enrich_with_context, _format_date_fr, StreamBuffer,
)
from services.chat_detectors import (
    _detect_insulte, _count_insult_streak,
    _detect_compliment, _count_compliment_streak,
    _detect_site_rating, get_site_rating_response,
    _is_short_continuation, _detect_tirage, _has_temporal_filter, _extract_temporal_date,
    _detect_generation, _detect_generation_mode, _extract_forced_numbers, _extract_grid_count,
    _extract_exclusions,
    _detect_cooccurrence_high_n, _get_cooccurrence_high_n_response,
    _is_affirmation_simple, _detect_game_keyword_alone,
    _detect_salutation, _get_salutation_response,
    _has_data_signal,
    _detect_grid_evaluation,
)
from services.stats_analysis import should_inject_pedagogical_context, PEDAGOGICAL_CONTEXT
from services.chat_logger import log_chat_exchange
from services.decay_state import get_decay_state, update_decay_after_generation

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# Shared constants — V72 F01/F03/F04/F07
# ═══════════════════════════════════════════════════════

# F01 V74: language names for system prompt injection when lang != "fr"
_LANG_NAMES = {
    "en": "anglais",
    "es": "espagnol",
    "pt": "portugais",
    "de": "allemand",
    "nl": "néerlandais",
}

# F03: _has_question keywords — shared across Phase I (Loto+EM)
# Used to detect if an insult/compliment message also contains a real question.
_QUESTION_KEYWORDS_INSULT = (
    # FR
    "numéro", "numero", "tirage", "grille", "fréquence", "frequence",
    "classement", "statistique", "stat", "analyse", "prochain",
    "étoile", "etoile",
    # EN
    "number", "draw", "grid", "frequency", "ranking", "statistic",
    "analysis", "next", "star",
    # ES (F01: was missing in EM)
    "número", "sorteo", "resultado", "cuadrícula", "combinación", "estrella",
    # PT
    "sorteio", "grelha",
    # DE
    "ziehung", "zahlen", "ergebnis", "kombination", "stern",
    # NL
    "trekking", "nummers", "resultaat", "combinatie", "ster",
)

# F03: _has_question_c keywords — shared across Phase C (Loto+EM)
_QUESTION_KEYWORDS_COMPLIMENT = (
    # FR
    "numéro", "numero", "tirage", "grille", "fréquence", "frequence",
    "combien", "c'est quoi", "quel", "quelle", "comment", "pourquoi",
    "classement", "statistique", "stat", "analyse",
    "étoile", "etoile",
    # EN
    "number", "draw", "grid", "frequency", "ranking", "how",
    "what", "which", "why", "star",
    # ES
    "número", "sorteo", "estrella", "cuánto", "cuál",
    # PT
    "sorteio", "estrela", "quanto", "qual",
    # DE
    "ziehung", "zahlen", "stern", "wie", "welche",
    # NL
    "trekking", "nummers", "ster", "hoeveel", "welke",
)

# F04: Anti-re-introduction block — injected into system prompt (both pipelines)
ANTI_REINTRO_BLOCK = (
    "\n\n[RAPPEL CRITIQUE — ANTI-RE-PRÉSENTATION]\n"
    "Le message de bienvenue affiché côté interface a DÉJÀ présenté HYBRIDE à l'utilisateur. "
    "Tu t'es DÉJÀ présenté. NE TE RE-PRÉSENTE PAS. "
    "Ne dis PAS 'Je suis HYBRIDE', 'I'm HYBRIDE', 'Soy HYBRIDE', 'Eu sou HYBRIDE', "
    "'Ich bin HYBRIDE', 'Ik ben HYBRIDE', etc. "
    "Ne dis PAS 'Salut !', 'Hello !', 'Hi !', 'Hola !', 'Olá !', 'Hallo !' en début de réponse "
    "s'il ne t'a pas salué. "
    "Va DIRECTEMENT à la réponse à sa question."
)

# F07: Tirage not found messages — i18n 6 langs
_TIRAGE_NOT_FOUND_LOTO = {
    "fr": (
        "[RÉSULTAT TIRAGE — INTROUVABLE]\n"
        "Aucun tirage trouvé en base de données pour la date du {date}.\n"
        "IMPORTANT : Ne PAS inventer de numéros. Indique simplement que "
        "ce tirage n'est pas disponible dans la base.\n"
        "Les tirages du Loto ont lieu les lundi, mercredi et samedi."
    ),
    "en": (
        "[DRAW RESULT — NOT FOUND]\n"
        "No draw found in the database for the date {date}.\n"
        "IMPORTANT: Do NOT invent numbers. Simply state that "
        "this draw is not available in the database.\n"
        "Loto draws take place on Monday, Wednesday and Saturday."
    ),
    "es": (
        "[RESULTADO SORTEO — NO ENCONTRADO]\n"
        "No se ha encontrado ningún sorteo en la base de datos para la fecha {date}.\n"
        "IMPORTANTE: NO inventes números. Indica simplemente que "
        "este sorteo no está disponible en la base de datos.\n"
        "Los sorteos del Loto tienen lugar los lunes, miércoles y sábados."
    ),
    "pt": (
        "[RESULTADO SORTEIO — NÃO ENCONTRADO]\n"
        "Nenhum sorteio encontrado na base de dados para a data {date}.\n"
        "IMPORTANTE: NÃO inventes números. Indica simplesmente que "
        "este sorteio não está disponível na base de dados.\n"
        "Os sorteios do Loto realizam-se às segundas, quartas e sábados."
    ),
    "de": (
        "[ZIEHUNGSERGEBNIS — NICHT GEFUNDEN]\n"
        "Keine Ziehung in der Datenbank für das Datum {date} gefunden.\n"
        "WICHTIG: Erfinde KEINE Zahlen. Gib einfach an, dass "
        "diese Ziehung nicht in der Datenbank verfügbar ist.\n"
        "Die Loto-Ziehungen finden montags, mittwochs und samstags statt."
    ),
    "nl": (
        "[TREKKINGSRESULTAAT — NIET GEVONDEN]\n"
        "Geen trekking gevonden in de database voor de datum {date}.\n"
        "BELANGRIJK: Verzin GEEN nummers. Geef gewoon aan dat "
        "deze trekking niet beschikbaar is in de database.\n"
        "De Loto-trekkingen vinden plaats op maandag, woensdag en zaterdag."
    ),
}

_TIRAGE_NOT_FOUND_EM = {
    "fr": (
        "[RÉSULTAT TIRAGE — INTROUVABLE]\n"
        "Aucun tirage trouvé en base de données pour la date du {date}.\n"
        "IMPORTANT : Ne PAS inventer de numéros. Indique simplement que "
        "ce tirage n'est pas disponible dans la base.\n"
        "Les tirages EuroMillions ont lieu les mardi et vendredi."
    ),
    "en": (
        "[DRAW RESULT — NOT FOUND]\n"
        "No draw found in the database for the date {date}.\n"
        "IMPORTANT: Do NOT invent numbers. Simply state that "
        "this draw is not available in the database.\n"
        "EuroMillions draws take place on Tuesday and Friday."
    ),
    "es": (
        "[RESULTADO SORTEO — NO ENCONTRADO]\n"
        "No se ha encontrado ningún sorteo en la base de datos para la fecha {date}.\n"
        "IMPORTANTE: NO inventes números. Indica simplemente que "
        "este sorteo no está disponible en la base de datos.\n"
        "Los sorteos de EuroMillions tienen lugar los martes y viernes."
    ),
    "pt": (
        "[RESULTADO SORTEIO — NÃO ENCONTRADO]\n"
        "Nenhum sorteio encontrado na base de dados para a data {date}.\n"
        "IMPORTANTE: NÃO inventes números. Indica simplesmente que "
        "este sorteio não está disponível na base de dados.\n"
        "Os sorteios do EuroMillions realizam-se às terças e sextas."
    ),
    "de": (
        "[ZIEHUNGSERGEBNIS — NICHT GEFUNDEN]\n"
        "Keine Ziehung in der Datenbank für das Datum {date} gefunden.\n"
        "WICHTIG: Erfinde KEINE Zahlen. Gib einfach an, dass "
        "diese Ziehung nicht in der Datenbank verfügbar ist.\n"
        "Die EuroMillions-Ziehungen finden dienstags und freitags statt."
    ),
    "nl": (
        "[TREKKINGSRESULTAAT — NIET GEVONDEN]\n"
        "Geen trekking gevonden in de database voor de datum {date}.\n"
        "BELANGRIJK: Verzin GEEN nummers. Geef gewoon aan dat "
        "deze trekking niet beschikbaar is in de database.\n"
        "De EuroMillions-trekkingen vinden plaats op dinsdag en vrijdag."
    ),
}


# ═══════════════════════════════════════════════════════
# F05: Centralized timeout constants (seconds)
# ═══════════════════════════════════════════════════════

_TIMEOUTS = {
    "sql_generate": 10,
    "sql_execute": 5,
    "gemini_chat": 15,
    "gemini_stream": 15,
    "pitch_context": 30,
    "pitch_gemini": 15,
    "stats_analysis": 30,
    "enrichment": 20,
}


# ═══════════════════════════════════════════════════════
# F03 V74: shared config base — DRY for _build_loto_config / _build_em_config
# ═══════════════════════════════════════════════════════

def _build_config_base(overrides: dict) -> dict:
    """Build config from game-specific overrides.

    Game-agnostic detectors (24 functions: _detect_insulte, _detect_compliment, etc.)
    are intentionally listed in each pipeline's overrides — NOT in this base dict —
    because existing tests patch them on the pipeline module (e.g.
    ``patch("services.chat_pipeline._detect_insulte")``).  Those patches only work
    when the config dict holds a reference to the pipeline-module binding, not
    to chat_pipeline_shared's copy.

    This function centralises the construction pattern and can hold truly shared
    non-callable defaults in the future.
    """
    return dict(overrides)


# ═══════════════════════════════════════════════════════
# SSE event formatter
# ═══════════════════════════════════════════════════════

def sse_event(data: dict) -> str:
    """Format dict as SSE event line: data: {...}\\n\\n"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ═══════════════════════════════════════════════════════
# Chat logger wrapper
# ═══════════════════════════════════════════════════════

def log_from_meta(meta, module, lang, message, response_preview="",
                  is_error=False, error_detail=None):
    """Call log_chat_exchange from _chat_meta dict."""
    if not meta:
        return
    log_chat_exchange(
        module=module, lang=meta.get("lang", lang), question=message,
        response_preview=response_preview,
        phase_detected=meta.get("phase", "unknown"),
        sql_generated=meta.get("sql_query"),
        sql_status=meta.get("sql_status", "N/A"),
        duration_ms=int((time.monotonic() - meta["t0"]) * 1000),
        grid_count=meta.get("grid_count", 0),
        has_exclusions=meta.get("has_exclusions", False),
        is_error=is_error, error_detail=error_detail,
    )


# ═══════════════════════════════════════════════════════
# History processing — build Gemini contents array
# ═══════════════════════════════════════════════════════

def build_gemini_contents(history, message, detect_insulte_fn):
    """
    Process chat history into Gemini contents array.
    Strips insult exchanges, maps roles, deduplicates consecutive same-role messages.
    Returns the processed contents list and the (possibly trimmed) history.
    """
    history = (history or [])[-20:]
    if history and history[-1].role == "user" and history[-1].content == message:
        history = history[:-1]

    contents = []
    _skip_insult_response = False
    for msg in history:
        if msg.role == "user" and detect_insulte_fn(msg.content):
            _skip_insult_response = True
            continue
        if msg.role == "assistant" and _skip_insult_response:
            _skip_insult_response = False
            continue
        _skip_insult_response = False

        role = "user" if msg.role == "user" else "model"
        content = _strip_sponsor_from_text(msg.content) if role == "model" else msg.content
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n" + content
        else:
            contents.append({"role": role, "parts": [{"text": content}]})

    while contents and contents[0]["role"] == "model":
        contents.pop(0)

    return contents, history


# ═══════════════════════════════════════════════════════
# Phase SQL — Text-to-SQL block
# ═══════════════════════════════════════════════════════

async def run_text_to_sql(message, http_client, gem_api_key, history,
                          generate_sql_fn, validate_sql_fn, ensure_limit_fn,
                          execute_sql_fn, format_result_fn, max_per_session,
                          log_prefix, force_sql, has_data_signal_fn,
                          continuation_mode, enrichment_context,
                          sql_gen_kwargs=None):
    """
    Phase SQL block. Returns (enrichment_context, sql_query, sql_status).
    sql_gen_kwargs: extra kwargs for generate_sql_fn (e.g. lang for EM).
    """
    _sql_query = None
    _sql_status = "N/A"

    _skip_sql = not force_sql and not has_data_signal_fn(message)
    if _skip_sql:
        logger.info(f'{log_prefix} Skip Phase SQL — no data signal | question="{message[:60]}"')
    if continuation_mode or enrichment_context or _skip_sql:
        return enrichment_context, _sql_query, _sql_status

    _sql_count = sum(1 for m in (history or []) if m.role == "user")
    if _sql_count >= max_per_session:
        logger.info(f"{log_prefix} Rate-limit session ({_sql_count} echanges)")
        return enrichment_context, _sql_query, _sql_status

    t0 = time.monotonic()
    try:
        kwargs = {"history": history}
        if sql_gen_kwargs:
            kwargs.update(sql_gen_kwargs)
        sql = await asyncio.wait_for(
            generate_sql_fn(message, http_client, gem_api_key, **kwargs),
            timeout=_TIMEOUTS["sql_generate"],
        )
        if sql and sql.strip().upper() != "NO_SQL" and validate_sql_fn(sql):
            _sql_query = sql
            sql = ensure_limit_fn(sql)
            rows = await asyncio.wait_for(execute_sql_fn(sql), timeout=_TIMEOUTS["sql_execute"])
            t_total = int((time.monotonic() - t0) * 1000)
            if rows is not None and len(rows) > 0:
                _sql_status = "OK"
                enrichment_context = format_result_fn(rows)
                logger.info(
                    f'{log_prefix} question="{message[:80]}" | '
                    f'sql="{sql[:120]}" | status=OK | '
                    f'rows={len(rows)} | time={t_total}ms'
                )
            elif rows is not None:
                _sql_status = "EMPTY"
                enrichment_context = "[RÉSULTAT SQL]\nAucun résultat trouvé pour cette requête."
                logger.info(
                    f'{log_prefix} question="{message[:80]}" | '
                    f'sql="{sql[:120]}" | status=EMPTY | '
                    f'rows=0 | time={t_total}ms'
                )
            else:
                _sql_status = "ERROR"
                enrichment_context = "[RÉSULTAT SQL]\nAucun résultat trouvé pour cette requête."
                logger.warning(
                    f'{log_prefix} question="{message[:80]}" | '
                    f'sql="{sql[:120]}" | status=EXEC_ERROR | '
                    f'time={t_total}ms'
                )
        elif sql and sql.strip().upper() == "NO_SQL":
            _sql_status = "NO_SQL"
            logger.info(
                f'{log_prefix} question="{message[:80]}" | '
                f'sql=NO_SQL | status=NO_SQL | '
                f'time={int((time.monotonic() - t0) * 1000)}ms'
            )
        elif sql:
            _sql_query = sql
            _sql_status = "REJECTED"
            logger.warning(
                f'{log_prefix} question="{message[:80]}" | '
                f'sql="{sql[:120]}" | status=REJECTED | '
                f'time={int((time.monotonic() - t0) * 1000)}ms'
            )
        else:
            _sql_status = "ERROR"
            logger.warning(
                f'{log_prefix} question="{message[:80]}" | '
                f'status=GEN_ERROR | '
                f'time={int((time.monotonic() - t0) * 1000)}ms'
            )
    except asyncio.TimeoutError:
        _sql_status = "ERROR"
        logger.warning(
            f'{log_prefix} question="{message[:80]}" | '
            f'status=TIMEOUT | '
            f'time={int((time.monotonic() - t0) * 1000)}ms'
        )
    except Exception as e:
        _sql_status = "ERROR"
        logger.warning(
            f'{log_prefix} question="{message[:80]}" | '
            f'status=ERROR | error="{e}" | '
            f'time={int((time.monotonic() - t0) * 1000)}ms'
        )

    return enrichment_context, _sql_query, _sql_status


# ═══════════════════════════════════════════════════════
# handle_chat — Gemini call + response extraction
# ═══════════════════════════════════════════════════════

async def call_gemini_and_respond(ctx, fallback, log_prefix, module, lang,
                                  message, page, sponsor_kwargs=None,
                                  breaker=None):
    """
    Gemini non-streaming call: send contents, extract text, handle errors.
    breaker: circuit breaker instance (pass module-level ref for test compat).
    Returns response dict.
    """
    mode = ctx["mode"]
    _breaker = breaker or gemini_breaker

    def _fallback(error_type):
        detail = {"circuit_open": "CircuitOpen", "timeout": "Timeout"}.get(error_type, error_type)
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail=detail)
        source = "fallback_circuit" if error_type == "circuit_open" else "fallback"
        return {"response": fallback, "source": source, "mode": mode}

    result = await _gemini_call_with_fallback(
        _breaker.call(
            ctx["_http_client"],
            GEMINI_MODEL_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": ctx["gem_api_key"],
            },
            json={
                "system_instruction": {"parts": [{"text": ctx["system_prompt"]}]},
                "contents": ctx["contents"],
                "generationConfig": {"temperature": 0.8, "maxOutputTokens": 300},
            },
            timeout=_TIMEOUTS["gemini_chat"],
        ),
        fallback_fn=_fallback,
        log_prefix=log_prefix,
    )

    # If fallback was returned (dict with "response" key, not httpx.Response)
    if isinstance(result, dict):
        return result

    response = result
    if response.status_code == 200:
        data = response.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                text = parts[0].get("text", "").strip()
                if text:
                    text = _clean_response(text)
                    if ctx["insult_prefix"]:
                        text = ctx["insult_prefix"] + "\n\n" + text
                    s_kwargs = sponsor_kwargs or {}
                    sponsor_line = _get_sponsor_if_due(ctx["history"], **s_kwargs)
                    if sponsor_line:
                        text += "\n\n" + sponsor_line
                    logger.info(f"{log_prefix} OK (page={page}, mode={mode})")
                    log_from_meta(ctx.get("_chat_meta"), module, lang, message, text)
                    return {"response": text, "source": "gemini", "mode": mode}

    logger.warning(f"{log_prefix} Reponse Gemini invalide: {response.status_code}")
    log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail=f"HTTP {response.status_code}")
    return {"response": fallback, "source": "fallback", "mode": mode}


# ═══════════════════════════════════════════════════════
# handle_chat_stream — SSE streaming loop
# ═══════════════════════════════════════════════════════

async def stream_and_respond(ctx, fallback, log_prefix, module, lang,
                             message, page, call_type, sponsor_kwargs=None,
                             stream_fn=None):
    """
    Async generator — SSE streaming loop with fallback handling.
    stream_fn: streaming function (pass module-level ref for test compat).
    Yields SSE event strings.
    """
    mode = ctx["mode"]
    _stream_chunks = []
    _stream = stream_fn or stream_gemini_chat

    try:
        if ctx["insult_prefix"]:
            yield sse_event({
                "chunk": ctx["insult_prefix"] + "\n\n",
                "source": "gemini", "mode": mode, "is_done": False,
            })

        has_chunks = False
        _buf = StreamBuffer()
        async for chunk in _stream(
            ctx["_http_client"], ctx["gem_api_key"], ctx["system_prompt"],
            ctx["contents"], timeout=_TIMEOUTS["gemini_stream"],
            call_type=call_type, lang=lang,
        ):
            safe = _buf.add_chunk(chunk)
            if not safe:
                continue
            has_chunks = True
            _stream_chunks.append(safe)
            yield sse_event({
                "chunk": safe, "source": "gemini", "mode": mode, "is_done": False,
            })

        _remaining = _buf.flush()
        if _remaining:
            has_chunks = True
            _stream_chunks.append(_remaining)
            yield sse_event({
                "chunk": _remaining, "source": "gemini", "mode": mode, "is_done": False,
            })

        if not has_chunks:
            log_from_meta(ctx.get("_chat_meta"), module, lang, message, fallback, is_error=True, error_detail="NoChunks")
            yield sse_event({
                "chunk": fallback,
                "source": "fallback", "mode": mode, "is_done": True,
            })
            return

        s_kwargs = sponsor_kwargs or {}
        sponsor_line = _get_sponsor_if_due(ctx["history"], **s_kwargs)
        if sponsor_line:
            yield sse_event({
                "chunk": "\n\n" + sponsor_line,
                "source": "gemini", "mode": mode, "is_done": False,
            })

        yield sse_event({
            "chunk": "", "source": "gemini", "mode": mode, "is_done": True,
        })
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, "".join(_stream_chunks))
        logger.info(f"{log_prefix} Stream OK (page={page}, mode={mode})")

    except CircuitOpenError:
        logger.warning(f"{log_prefix} Circuit breaker ouvert — fallback")
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail="CircuitOpen")
        yield sse_event({
            "chunk": fallback,
            "source": "fallback_circuit", "mode": mode, "is_done": True,
        })
    except httpx.TimeoutException:
        logger.warning(f"{log_prefix} Timeout Gemini (15s) — fallback")
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail="Timeout")
        yield sse_event({
            "chunk": fallback,
            "source": "fallback", "mode": mode, "is_done": True,
        })
    except Exception as e:
        logger.error(f"{log_prefix} Erreur streaming: {e}")
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail=str(e)[:255])
        yield sse_event({
            "chunk": fallback,
            "source": "fallback", "mode": mode, "is_done": True,
        })


# ═══════════════════════════════════════════════════════
# Pitch JSON parsing
# ═══════════════════════════════════════════════════════

def parse_pitch_json(text):
    """
    Clean backticks and parse pitch JSON from Gemini.
    Returns (pitchs_list, error_dict_or_None).
    """
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

    try:
        result = json.loads(clean)
        pitchs = result.get("pitchs", [])
    except (json.JSONDecodeError, AttributeError):
        return None, {
            "success": False, "data": None,
            "error": "Gemini: JSON mal formé",
            "status_code": 502,
        }

    pitchs = [_strip_non_latin(p) if isinstance(p, str) else p for p in pitchs]
    return pitchs, None


# ═══════════════════════════════════════════════════════
# handle_pitch — common pipeline
# ═══════════════════════════════════════════════════════

async def handle_pitch_common(grilles_data, http_client, lang,
                              context_coro,
                              load_prompt_fn, prompt_name,
                              log_prefix, breaker=None):
    """
    Common pitch pipeline after validation.
    context_coro: awaitable that returns the stats context string.
    Calls context_coro → load_prompt → Gemini → parse JSON.
    Returns result dict.
    """
    try:
        context = await asyncio.wait_for(context_coro, timeout=_TIMEOUTS["pitch_context"])
    except asyncio.TimeoutError:
        logger.error(f"{log_prefix} Timeout {_TIMEOUTS['pitch_context']}s contexte stats")
        return {"success": False, "data": None, "error": "Service temporairement indisponible", "status_code": 503}
    except Exception as e:
        logger.warning(f"{log_prefix} Erreur contexte stats: {e}")
        return {"success": False, "data": None, "error": "Erreur données statistiques", "status_code": 500}

    if not context:
        return {"success": False, "data": None, "error": "Impossible de préparer le contexte", "status_code": 500}

    system_prompt = load_prompt_fn(prompt_name)
    if not system_prompt:
        logger.error(f"{log_prefix} Prompt pitch introuvable")
        return {"success": False, "data": None, "error": "Prompt pitch introuvable", "status_code": 500}

    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        return {"success": False, "data": None, "error": "API Gemini non configurée", "status_code": 500}

    _breaker = breaker or gemini_breaker

    def _fallback(error_type):
        if error_type == "circuit_open":
            return {"success": False, "data": None, "error": "Service Gemini temporairement indisponible", "status_code": 503}
        if error_type == "timeout":
            return {"success": False, "data": None, "error": "Timeout Gemini", "status_code": 503}
        return {"success": False, "data": None, "error": "Erreur interne du serveur", "status_code": 500}

    result = await _gemini_call_with_fallback(
        _breaker.call(
            http_client,
            GEMINI_MODEL_URL,
            headers={"Content-Type": "application/json", "x-goog-api-key": gem_api_key},
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": context}]}],
                "generationConfig": {"temperature": 0.9, "maxOutputTokens": 600},
            },
            timeout=_TIMEOUTS["pitch_gemini"],
        ),
        fallback_fn=_fallback,
        log_prefix=log_prefix,
    )

    if isinstance(result, dict):
        return result

    response = result
    if response.status_code != 200:
        logger.warning(f"{log_prefix} Gemini HTTP {response.status_code}")
        return {"success": False, "data": None, "error": f"Gemini erreur HTTP {response.status_code}", "status_code": 502}

    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        return {"success": False, "data": None, "error": "Gemini: aucune réponse", "status_code": 502}

    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
    if not text:
        return {"success": False, "data": None, "error": "Gemini: réponse vide", "status_code": 502}

    pitchs, error = parse_pitch_json(text)
    if error:
        logger.warning(f"{log_prefix} JSON invalide: {text[:200]}")
        return error

    logger.info(f"{log_prefix} OK — {len(pitchs)} pitchs générés")
    return {"success": True, "data": {"pitchs": pitchs}, "error": None, "status_code": 200}


# ═══════════════════════════════════════════════════════
# Parametric pipeline orchestration — V72 F02
# ═══════════════════════════════════════════════════════

async def _prepare_chat_context_base(
    message: str, history: list, page: str, http_client, lang: str, cfg: dict,
):
    """
    Orchestration paramétrique des 19+ phases chatbot.

    cfg dict keys (all required unless noted):
      Identity: game, log_prefix, debug_prefix
      Prompt: load_system_prompt(lang) -> str|None, draw_count_game
      Fallback: get_fallback(lang) -> str
      Mode: detect_mode(message, page) -> str
      Phase I: get_insult_short(lang), get_menace_response(lang),
               get_insult_response(lang, streak, history)
      Phase C: get_compliment_response(lang, type, streak, history)
      Phase SALUTATION: salutation_game ("loto"|"em")
      Phase G: gen_engine_module (str), forced_secondary_key,
               gen_secondary_param, store_exclusions, format_generation_context(grid)
      Phase A: detect_argent(msg, lang), get_argent_response(msg, lang)
      Phase GEO (optional): detect_country(msg), get_country_context(lang)
      Phase AFFIRMATION: affirmation_invitation (dict), game_keyword_invitation (dict)
      Phase EVAL: eval_game, secondary_field, format_grille_context(data),
                  analyze_grille_for_chat(nums, secondary, **kw), analyze_passes_lang
      Phase 0-bis: detect_prochain_tirage(msg), get_prochain_tirage() async
      Phase T: get_tirage_data(target) async, format_tirage_context(data),
               tirage_not_found (dict)
      Phase 2: detect_grille(msg), (reuses analyze_grille_for_chat + format_grille_context)
      Phase 3: detect_requete_complexe(msg), format_complex_context(intent, data),
               get_classement(type, tri, limit) async, get_comparaison(n1, n2, type) async,
               get_categorie(cat, type) async, get_comparaison_with_period(n1,n2,type,date) async,
               wants_both_fn(msg) (optional, EM only)
      Phase P: detect_triplets(msg), format_triplets_context(data),
               get_triplet_correlations(top_n) async,
               detect_paires(msg), format_pairs_context(data),
               get_pair_correlations(top_n) async,
               get_star_pair_correlations(top_n) async (optional),
               format_star_pairs_context(data) (optional)
      Phase OOR: detect_oor(msg), count_oor_streak(history),
                 get_oor_response(lang, num, type, streak)
      Phase 1: detect_numero(msg), get_numero_stats(num, type) async,
               format_stats_context(stats)
      Phase SQL: generate_sql, sql_log_prefix, sql_gen_kwargs(lang) (optional),
                 validate_sql, ensure_limit, execute_safe_sql, format_sql_result,
                 max_sql_per_session
      Final: build_session_context(history, message)
    """
    _t0 = time.monotonic()
    _lp = cfg["log_prefix"]
    _fallback = cfg["get_fallback"](lang)
    mode = cfg["detect_mode"](message, page)

    # ── Chat Monitor: phase tracking ──
    _phase = "Gemini"
    _sql_query = None
    _sql_status = "N/A"
    _grid_count = 0
    _has_exclusions = False

    system_prompt = cfg["load_system_prompt"](lang)
    if not system_prompt:
        logger.error(f"{_lp} Prompt systeme introuvable")
        return {"response": _fallback, "source": "fallback", "mode": mode}, None

    # F02: inject dynamic draw count
    from services.chat_pipeline import _get_draw_count
    draw_count = await _get_draw_count(cfg["draw_count_game"])
    if draw_count and "{DRAW_COUNT}" in system_prompt:
        system_prompt = system_prompt.replace("{DRAW_COUNT}", str(draw_count))

    # ── F01 V74: Force language when lang != "fr" (Loto prompt is FR-only) ──
    if lang != "fr" and lang in _LANG_NAMES:
        system_prompt += (
            f"\n\n[LANGUE — RÈGLE OBLIGATOIRE]\n"
            f"Tu DOIS répondre UNIQUEMENT en {_LANG_NAMES[lang]}. "
            f"L'utilisateur parle {_LANG_NAMES[lang]}. "
            f"Ne réponds JAMAIS dans une autre langue."
        )

    # ── Anti-re-introduction ──
    system_prompt += ANTI_REINTRO_BLOCK

    # ── Contexte pédagogique ──
    if should_inject_pedagogical_context(message):
        system_prompt += PEDAGOGICAL_CONTEXT

    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        logger.warning(f"{_lp} GEM_API_KEY non configuree — fallback")
        return {"response": _fallback, "source": "fallback", "mode": mode}, None

    contents, history = build_gemini_contents(history, message, cfg["detect_insulte"])

    def _meta(**extra):
        return {"phase": _phase, "t0": _t0, "lang": lang, **extra}

    def _early(response, source, **extra_meta):
        return {"response": response, "source": source, "mode": mode,
                "_chat_meta": _meta(**extra_meta)}, None

    # ── Phase I : Détection d'insultes / agressivité ──
    _insult_prefix = ""
    _insult_type = cfg["detect_insulte"](message)
    if _insult_type:
        _insult_streak = cfg["count_insult_streak"](history)
        _has_question = (
            '?' in message
            or bool(re.search(r'\b\d{1,2}\b', message))
            or any(kw in message.lower() for kw in _QUESTION_KEYWORDS_INSULT)
        )
        if _has_question:
            _insult_prefix = cfg["get_insult_short"](lang)
            logger.info(f"{_lp} Insulte + question (type={_insult_type}, streak={_insult_streak})")
        else:
            _phase = "I"
            if _insult_type == "menace":
                _insult_resp = cfg["get_menace_response"](lang)
            else:
                _insult_resp = cfg["get_insult_response"](lang, _insult_streak, history)
            logger.info(f"{_lp} Insulte detectee (type={_insult_type}, streak={_insult_streak})")
            return _early(_insult_resp, "hybride_insult")

    # ── Phase C : Détection de compliments ──
    if not _insult_prefix:
        _compliment_type = cfg["detect_compliment"](message)
        if _compliment_type:
            _has_question_c = (
                '?' in message
                or bool(re.search(r'\b\d{1,2}\b', message))
                or any(kw in message.lower() for kw in _QUESTION_KEYWORDS_COMPLIMENT)
            )
            if not _has_question_c:
                _phase = "C"
                _comp_streak = cfg["count_compliment_streak"](history)
                _comp_resp = cfg["get_compliment_response"](lang, _compliment_type, _comp_streak, history)
                logger.info(f"{_lp} Compliment detecte (type={_compliment_type}, streak={_comp_streak})")
                return _early(_comp_resp, "hybride_compliment")
            else:
                logger.info(f"{_lp} Compliment + question (type={_compliment_type}), passage au flow normal")

    # ── Phase R : Détection intention de noter le site ──
    if cfg["detect_site_rating"](message):
        _phase = "R"
        logger.info(f"{_lp} Site rating intent detected (lang={lang})")
        return _early(cfg["get_site_rating_response"](lang), "hybride_rating_invite")

    # ── Phase SALUTATION : Salutation initiale sans historique ──
    if not history or len(history) <= 1:
        if cfg["detect_salutation"](message):
            _phase = "SALUTATION"
            _sal_resp = cfg["get_salutation_response"](cfg["salutation_game"], lang)
            logger.info(f"{_lp} Salutation detectee — court-circuit Phase SALUTATION (lang={lang})")
            return _early(_sal_resp, "hybride_salutation")

    # ── Phase G : Détection génération de grille ──
    _generation_context = ""
    if cfg["detect_generation"](message):
        _phase = "G"
        try:
            _gen_mod = importlib.import_module(cfg["gen_engine_module"])
            _gen_fn = _gen_mod.generate_grids
            _gen_mode = cfg["detect_generation_mode"](message)
            _grid_count = cfg["extract_grid_count"](message)
            _forced = cfg["extract_forced_numbers"](message, game=cfg["game"])
            _exclusions = cfg["extract_exclusions"](message)
            _has_exclusions = bool(_exclusions and any(_exclusions.values()))
            if _forced.get("error"):
                _generation_context = f"[ERREUR GÉNÉRATION] {_forced['error']}"
                logger.info(f"{_lp} Phase G — erreur contrainte: {_forced['error']}")
            else:
                # Decay state: load before generation (best-effort)
                _decay = None
                _game_name = "euromillions" if cfg.get("game") == "euromillions" else "loto"
                try:
                    import db_cloudsql as _db
                    async with _db.get_connection() as _dconn:
                        _decay = await get_decay_state(_dconn, _game_name, "ball")
                except Exception:
                    pass  # graceful — generate without decay

                _gen_kwargs = {
                    "n": _grid_count, "mode": _gen_mode, "lang": lang,
                    "forced_nums": _forced["forced_nums"] or None,
                    cfg["gen_secondary_param"]: _forced[cfg["forced_secondary_key"]] or None,
                    # DESIGN DECISION: anti_collision=True hardcode pour le chatbot.
                    # Le chatbot optimise l'UX (eviter les numeros superstitieux partages).
                    # L'API laisse le choix a l'utilisateur (default=False, opt-in via query param).
                    # Voir audit 360° Engine HYBRIDE F03 — 01/04/2026.
                    "anti_collision": True,
                    "decay_state": _decay,
                }
                if any((_exclusions or {}).values()):
                    _gen_kwargs["exclusions"] = _exclusions
                _gen_result = await asyncio.wait_for(_gen_fn(**_gen_kwargs), timeout=_TIMEOUTS["stats_analysis"])
                if _gen_result and _gen_result.get("grids"):
                    _grids = _gen_result["grids"][:_grid_count]
                    _active_excl = _exclusions if any((_exclusions or {}).values()) else None
                    if len(_grids) == 1:
                        _grids[0]["mode"] = _gen_mode
                        if cfg.get("store_exclusions") and _active_excl:
                            _grids[0]["exclusions"] = _active_excl
                        _generation_context = cfg["format_generation_context"](_grids[0])
                    else:
                        _parts = []
                        for idx, _grid in enumerate(_grids, 1):
                            _grid["mode"] = _gen_mode
                            if cfg.get("store_exclusions") and _active_excl:
                                _grid["exclusions"] = _active_excl
                            _parts.append(f"--- Grille {idx}/{len(_grids)} ---\n" + cfg["format_generation_context"](_grid))
                        _generation_context = "\n\n".join(_parts)
                    _sec_val = _forced[cfg["forced_secondary_key"]]
                    logger.info(
                        f"{_lp} Phase G — {len(_grids)} grille(s) generee(s) mode={_gen_mode} "
                        f"forced={_forced['forced_nums']} {cfg['forced_secondary_key']}={_sec_val}"
                    )
                    # Update decay after generation (best-effort)
                    try:
                        _all_b = [n for g in _grids for n in g.get("nums", [])]
                        _all_s = []
                        for g in _grids:
                            sec = g.get("etoiles") or g.get("chance")
                            if isinstance(sec, list):
                                _all_s.extend(sec)
                            elif sec is not None:
                                _all_s.append(sec)
                        if _all_b:
                            async with _db.get_connection() as _dconn:
                                await update_decay_after_generation(
                                    _dconn, _game_name, _all_b, _all_s or None,
                                )
                    except Exception:
                        pass  # non-blocking
        except Exception as e:
            logger.warning(f"{_lp} Phase G erreur: {e}")

    # ── Phase A : Détection argent / gains / paris ──
    if cfg["detect_argent"](message, lang):
        _phase = "A"
        _argent_resp = cfg["get_argent_response"](message, lang)
        if _insult_prefix:
            _argent_resp = _insult_prefix + "\n\n" + _argent_resp
        logger.info(f"{_lp} Argent detecte — court-circuit Phase A (lang={lang})")
        return _early(_argent_resp, "hybride_argent")

    # ── Phase GEO : Détection pays (EM only) ──
    _country_context = ""
    _detect_country_fn = cfg.get("detect_country")
    if _detect_country_fn and _detect_country_fn(message):
        _phase = "GEO"
        _country_context = cfg["get_country_context"](lang)
        logger.info(f"{_lp} Phase GEO — pays detecte, contexte injecte (lang={lang})")

    # ── Phase 0 : Continuation contextuelle ──
    _continuation_mode = False
    _enriched_message = None

    if cfg["is_short_continuation"](message) and history:
        _enriched_message = cfg["enrich_with_context"](message, history)
        if _enriched_message != message:
            _continuation_mode = True
            _phase = "0"
            logger.info(
                f"{_lp} Reponse courte detectee: \"{message}\" → enrichissement contextuel"
            )

    # ── Phase AFFIRMATION : affirmation simple ──
    if not _continuation_mode and cfg["is_affirmation_simple"](message):
        if history and len(history) >= 2:
            _enriched_message = cfg["enrich_with_context"](message, history)
            if _enriched_message != message:
                _continuation_mode = True
                _phase = "AFFIRMATION"
                logger.info(
                    f"{_lp} Affirmation simple avec contexte: \"{message}\" "
                    f"→ enrichissement contextuel (lang={lang})"
                )
        if not _continuation_mode:
            _phase = "AFFIRMATION_SANS_CONTEXTE"
            _resp = cfg["affirmation_invitation"].get(lang, cfg["affirmation_invitation"]["fr"])
            if _insult_prefix:
                _resp = _insult_prefix + "\n\n" + _resp
            logger.info(f"{_lp} AFFIRMATION_SANS_CONTEXTE \"{message}\" (lang={lang})")
            return _early(_resp, "hybride_affirmation")

    # ── Phase GAME_KEYWORD : mot-clé jeu seul ──
    if not _continuation_mode and cfg["detect_game_keyword_alone"](message):
        _phase = "GAME_KEYWORD"
        _resp = cfg["game_keyword_invitation"].get(lang, cfg["game_keyword_invitation"]["fr"])
        if _insult_prefix:
            _resp = _insult_prefix + "\n\n" + _resp
        logger.info(f"{_lp} GAME_KEYWORD Mot-cle jeu seul: \"{message}\" (lang={lang})")
        return _early(_resp, "hybride_game_keyword")

    enrichment_context = ""

    # ── Phase EVAL : Évaluation grille soumise ──
    if not _generation_context:
        _eval_result = cfg["detect_grid_evaluation"](message, game=cfg["eval_game"])
        if _eval_result:
            _phase = "EVAL"
            try:
                _eval_nums = _eval_result["numeros"]
                _eval_secondary = _eval_result.get(cfg["secondary_field"])
                _analyze_kw = {}
                if cfg.get("analyze_passes_lang"):
                    _analyze_kw["lang"] = lang
                grille_analysis = await asyncio.wait_for(
                    cfg["analyze_grille_for_chat"](_eval_nums, _eval_secondary, **_analyze_kw),
                    timeout=_TIMEOUTS["stats_analysis"],
                )
                if grille_analysis:
                    enrichment_context = cfg["format_grille_context"](grille_analysis)
                    enrichment_context = enrichment_context.replace(
                        "[ANALYSE DE GRILLE",
                        "[ÉVALUATION GRILLE UTILISATEUR",
                    )
                    logger.info(
                        f"{_lp} Phase EVAL — grille utilisateur evaluee: "
                        f"{_eval_nums} {cfg['secondary_field']}={_eval_secondary}"
                    )
            except Exception as e:
                logger.warning(f"{_lp} Phase EVAL erreur: {e}")

    # Phase 0-bis : prochain tirage
    if not _continuation_mode and cfg["detect_prochain_tirage"](message):
        _phase = "0-bis"
        try:
            tirage_ctx = await asyncio.wait_for(cfg["get_prochain_tirage"](), timeout=_TIMEOUTS["stats_analysis"])
            if tirage_ctx:
                enrichment_context = tirage_ctx
                logger.info(f"{_lp} Prochain tirage injecte")
        except Exception as e:
            logger.warning(f"{_lp} Erreur prochain tirage: {e}")

    # Phase T — Tirage spécifique / requête temporelle complexe
    if not _continuation_mode and not enrichment_context:
        tirage_target = cfg["detect_tirage"](message)
        if tirage_target is not None:
            _phase = "T"
            try:
                tirage_data = await asyncio.wait_for(
                    cfg["get_tirage_data"](tirage_target), timeout=_TIMEOUTS["stats_analysis"]
                )
                if tirage_data:
                    enrichment_context = cfg["format_tirage_context"](tirage_data)
                    logger.info(f"{_lp} Tirage injecte: {tirage_data['date']}")
                elif tirage_target != "latest":
                    date_fr = _format_date_fr(str(tirage_target))
                    _tpl = cfg["tirage_not_found"].get(lang, cfg["tirage_not_found"]["fr"])
                    enrichment_context = _tpl.format(date=date_fr)
                    logger.info(f"{_lp} Tirage introuvable pour: {tirage_target}")
            except Exception as e:
                logger.warning(f"{_lp} Erreur tirage: {e}")

    force_sql = not _continuation_mode and not enrichment_context and cfg["has_temporal_filter"](message)
    if force_sql:
        logger.info(f"{_lp} Filtre temporel detecte, force Phase SQL")

    # Phase 2 : detection de grille
    grille_nums, grille_secondary = (None, None) if _continuation_mode else cfg["detect_grille"](message)
    if not force_sql and not enrichment_context and grille_nums is not None:
        _phase = "2"
        try:
            _analyze_kw = {}
            if cfg.get("analyze_passes_lang"):
                _analyze_kw["lang"] = lang
            grille_result = await asyncio.wait_for(
                cfg["analyze_grille_for_chat"](grille_nums, grille_secondary, **_analyze_kw),
                timeout=_TIMEOUTS["stats_analysis"],
            )
            if grille_result:
                enrichment_context = cfg["format_grille_context"](grille_result)
                logger.info(f"{_lp} Grille analysee: {grille_nums} {cfg['secondary_field']}={grille_secondary}")
        except Exception as e:
            logger.warning(f"{_lp} Erreur analyse grille: {e}")

    # Phase 3 : requete complexe
    if not _continuation_mode and not force_sql and not enrichment_context:
        intent = cfg["detect_requete_complexe"](message)
        if intent:
            _phase = "3"
            try:
                data = None
                if intent["type"] == "classement":
                    data = await asyncio.wait_for(
                        cfg["get_classement"](intent["num_type"], intent["tri"], intent["limit"]),
                        timeout=_TIMEOUTS["stats_analysis"],
                    )
                    # EM: if user asks for both boules AND étoiles
                    _wants_both = cfg.get("wants_both_fn")
                    if data and _wants_both and intent["num_type"] == "boule" and _wants_both(message):
                        try:
                            star_data = await asyncio.wait_for(
                                cfg["get_classement"]("etoile", intent["tri"], intent["limit"]),
                                timeout=_TIMEOUTS["stats_analysis"],
                            )
                            if star_data:
                                star_intent = {**intent, "num_type": "etoile"}
                                enrichment_context = (
                                    cfg["format_complex_context"](intent, data)
                                    + "\n\n"
                                    + cfg["format_complex_context"](star_intent, star_data)
                                )
                                logger.info(f"{_lp} Requete complexe: classement boules + étoiles")
                                data = None
                        except Exception:
                            pass
                elif intent["type"] == "comparaison":
                    data = await asyncio.wait_for(
                        cfg["get_comparaison"](intent["num1"], intent["num2"], intent["num_type"]),
                        timeout=_TIMEOUTS["stats_analysis"],
                    )
                elif intent["type"] == "categorie":
                    data = await asyncio.wait_for(
                        cfg["get_categorie"](intent["categorie"], intent["num_type"]),
                        timeout=_TIMEOUTS["stats_analysis"],
                    )

                if data:
                    enrichment_context = cfg["format_complex_context"](intent, data)
                    logger.info(f"{_lp} Requete complexe: {intent['type']}")
            except Exception as e:
                logger.warning(f"{_lp} Erreur requete complexe: {e}")

    # Phase 3-bis : comparaison avec filtre temporel
    if not _continuation_mode and force_sql and not enrichment_context:
        intent = cfg["detect_requete_complexe"](message)
        if intent and intent["type"] == "comparaison":
            _phase = "3-bis"
            try:
                _date_from = cfg["extract_temporal_date"](message)
                data = await asyncio.wait_for(
                    cfg["get_comparaison_with_period"](
                        intent["num1"], intent["num2"], intent["num_type"], _date_from
                    ),
                    timeout=_TIMEOUTS["stats_analysis"],
                )
                if data:
                    enrichment_context = cfg["format_complex_context"](intent, data)
                    force_sql = False
                    logger.info(
                        f"{_lp} Phase 3-bis — comparaison temporelle "
                        f"{intent['num1']} vs {intent['num2']} (date_from={_date_from})"
                    )
            except Exception as e:
                logger.warning(f"{_lp} Erreur comparaison temporelle: {e}")

    # Phase P+ : co-occurrences N>3
    if not _continuation_mode and not enrichment_context:
        if cfg["detect_cooccurrence_high_n"](message):
            _phase = "P+"
            _high_n_resp = cfg["get_cooccurrence_high_n_response"](message, lang=lang)
            if _insult_prefix:
                _high_n_resp = _insult_prefix + "\n\n" + _high_n_resp
            logger.info(f"{_lp} Co-occurrence N>3 — redirection paires/triplets (lang={lang})")
            return _early(_high_n_resp, "hybride_cooccurrence")

    # Phase P : triplets
    if not _continuation_mode and not enrichment_context:
        if cfg["detect_triplets"](message):
            _phase = "P"
            try:
                triplets_data = await asyncio.wait_for(
                    cfg["get_triplet_correlations"](top_n=5), timeout=_TIMEOUTS["stats_analysis"]
                )
                if triplets_data:
                    enrichment_context = cfg["format_triplets_context"](triplets_data)
                    logger.info(f"{_lp} Triplets injectes")
            except Exception as e:
                logger.warning(f"{_lp} Erreur triplets: {e}")

    # Phase P : paires
    if not _continuation_mode and not enrichment_context:
        if cfg["detect_paires"](message):
            _phase = "P"
            try:
                pairs_data = await asyncio.wait_for(
                    cfg["get_pair_correlations"](top_n=5), timeout=_TIMEOUTS["stats_analysis"]
                )
                if pairs_data:
                    enrichment_context = cfg["format_pairs_context"](pairs_data)
                    # EM: star pairs
                    _get_star_pairs = cfg.get("get_star_pair_correlations")
                    if _get_star_pairs:
                        star_data = await asyncio.wait_for(_get_star_pairs(top_n=5), timeout=_TIMEOUTS["stats_analysis"])
                        if star_data:
                            enrichment_context += "\n\n" + cfg["format_star_pairs_context"](star_data)
                    logger.info(f"{_lp} Paires injectees")
            except Exception as e:
                logger.warning(f"{_lp} Erreur paires: {e}")

    # ── Phase OOR : Détection numéro hors range ──
    if not _continuation_mode and not force_sql and not enrichment_context:
        _oor_num, _oor_type = cfg["detect_oor"](message)
        if _oor_num is not None:
            _phase = "OOR"
            _oor_streak = cfg["count_oor_streak"](history)
            _oor_resp = cfg["get_oor_response"](lang, _oor_num, _oor_type, _oor_streak)
            if _insult_prefix:
                _oor_resp = _insult_prefix + "\n\n" + _oor_resp
            logger.info(
                f"{_lp} Numero hors range: {_oor_num} "
                f"(type={_oor_type}, streak={_oor_streak})"
            )
            return _early(_oor_resp, "hybride_oor")

    # Phase 1 : detection de numero simple
    if not _continuation_mode and not force_sql and not enrichment_context:
        numero, type_num = cfg["detect_numero"](message)
        if numero is not None:
            _phase = "1"
            try:
                stats = await asyncio.wait_for(
                    cfg["get_numero_stats"](numero, type_num), timeout=_TIMEOUTS["stats_analysis"]
                )
                if stats:
                    enrichment_context = cfg["format_stats_context"](stats)
                    logger.info(f"{_lp} Stats BDD injectees: numero={numero}, type={type_num}")
            except Exception as e:
                logger.warning(f"{_lp} Erreur stats BDD (numero={numero}): {e}")

    # Phase SQL : Text-to-SQL fallback
    _sql_gen_kwargs_fn = cfg.get("sql_gen_kwargs")
    _sql_kw = {}
    if _sql_gen_kwargs_fn:
        _sql_kw["sql_gen_kwargs"] = _sql_gen_kwargs_fn(lang)
    enrichment_context, _sql_query, _sql_status = await run_text_to_sql(
        message, http_client, gem_api_key, history,
        generate_sql_fn=cfg["generate_sql"], validate_sql_fn=cfg["validate_sql"],
        ensure_limit_fn=cfg["ensure_limit"], execute_sql_fn=cfg["execute_safe_sql"],
        format_result_fn=cfg["format_sql_result"], max_per_session=cfg["max_sql_per_session"],
        log_prefix=cfg["sql_log_prefix"], force_sql=force_sql,
        has_data_signal_fn=cfg["has_data_signal"],
        continuation_mode=_continuation_mode, enrichment_context=enrichment_context,
        **_sql_kw,
    )
    if _sql_query or _sql_status != "N/A":
        _phase = "SQL"

    if force_sql and not enrichment_context:
        logger.warning(
            f"{_lp} Phase SQL echouee avec filtre temporel, "
            f"PAS de fallback Phase 3 (evite stats all-time incorrectes) | "
            f'question="{message[:80]}"'
        )

    # ── Combine generation context + stats context ──
    if _generation_context and enrichment_context:
        enrichment_context = f"{enrichment_context}\n\n{_generation_context}"
        logger.info(f"{_lp} Multi-action: stats + generation combines")
    elif _generation_context:
        enrichment_context = _generation_context

    logger.info(
        f"{cfg['debug_prefix']} force_sql={force_sql} | continuation={_continuation_mode} | "
        f"enrichment={bool(enrichment_context)} | generation={bool(_generation_context)} | "
        f"question=\"{message[:60]}\" | history_len={len(history or [])}"
    )

    _session_ctx = cfg["build_session_context"](history, message)

    # Prepend country context (Phase GEO) if detected
    if _country_context:
        if enrichment_context:
            enrichment_context = _country_context + "\n\n" + enrichment_context
        else:
            enrichment_context = _country_context

    if _continuation_mode and _enriched_message:
        user_text = f"[Page: {page}]\n\n{_enriched_message}"
    elif enrichment_context:
        user_text = f"[Page: {page}]\n\n{enrichment_context}\n\n[Question utilisateur] {message}"
    else:
        user_text = f"[Page: {page}] {message}"

    if _session_ctx:
        user_text = f"{_session_ctx}\n\n{user_text}"

    contents.append({"role": "user", "parts": [{"text": user_text}]})

    return None, {
        "system_prompt": system_prompt,
        "gem_api_key": gem_api_key,
        "contents": contents,
        "mode": mode,
        "insult_prefix": _insult_prefix,
        "history": history,
        "lang": lang,
        "fallback": _fallback,
        "_chat_meta": {
            "phase": _phase, "t0": _t0, "lang": lang,
            "sql_query": _sql_query, "sql_status": _sql_status,
            "grid_count": _grid_count, "has_exclusions": _has_exclusions,
        },
    }
