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
"""

import os
import json
import asyncio
import logging
import time
import httpx

from services.circuit_breaker import gemini_breaker, CircuitOpenError, GeminiCircuitBreaker
from services.gemini import GEMINI_MODEL_URL, stream_gemini_chat
from services.chat_utils import (
    _clean_response, _strip_non_latin, _get_sponsor_if_due,
    _strip_sponsor_from_text, StreamBuffer,
)
from services.chat_logger import log_chat_exchange

logger = logging.getLogger(__name__)


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
            timeout=10.0,
        )
        if sql and sql.strip().upper() != "NO_SQL" and validate_sql_fn(sql):
            _sql_query = sql
            sql = ensure_limit_fn(sql)
            rows = await asyncio.wait_for(execute_sql_fn(sql), timeout=5.0)
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

    try:
        response = await _breaker.call(
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
            timeout=15.0,
        )

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

    except CircuitOpenError:
        logger.warning(f"{log_prefix} Circuit breaker ouvert — fallback")
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail="CircuitOpen")
        return {"response": fallback, "source": "fallback_circuit", "mode": mode}
    except httpx.TimeoutException:
        logger.warning(f"{log_prefix} Timeout Gemini (15s) — fallback")
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail="Timeout")
        return {"response": fallback, "source": "fallback", "mode": mode}
    except Exception as e:
        logger.error(f"{log_prefix} Erreur Gemini: {e}")
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail=str(e)[:255])
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
            ctx["contents"], timeout=15.0,
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
        context = await asyncio.wait_for(context_coro, timeout=30.0)
    except asyncio.TimeoutError:
        logger.error(f"{log_prefix} Timeout 30s contexte stats")
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
    try:
        response = await _breaker.call(
            http_client,
            GEMINI_MODEL_URL,
            headers={"Content-Type": "application/json", "x-goog-api-key": gem_api_key},
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": context}]}],
                "generationConfig": {"temperature": 0.9, "maxOutputTokens": 600},
            },
            timeout=15.0,
        )

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

    except CircuitOpenError:
        logger.warning(f"{log_prefix} Circuit breaker ouvert — fallback")
        return {"success": False, "data": None, "error": "Service Gemini temporairement indisponible", "status_code": 503}
    except httpx.TimeoutException:
        logger.warning(f"{log_prefix} Timeout Gemini (15s)")
        return {"success": False, "data": None, "error": "Timeout Gemini", "status_code": 503}
    except Exception as e:
        logger.error(f"{log_prefix} Erreur: {e}")
        return {"success": False, "data": None, "error": "Erreur interne du serveur", "status_code": 500}
