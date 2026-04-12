"""
Gemini interaction helpers for chat pipelines — F15 V83.

Extracted from chat_pipeline_shared.py to reduce cognitive complexity.
Contains: SSE formatting, chat logging, Gemini contents building,
non-streaming and streaming Gemini calls, pitch pipeline, JSON parsing.

Direction: chat_pipeline_shared.py imports FROM this module (not the reverse).
"""

import os
import re
import json
import asyncio
import logging
import time

import httpx

from services.circuit_breaker import gemini_breaker, CircuitOpenError
from services.gemini import GEMINI_MODEL_URL, stream_gemini_chat, _GEMINI_CHAT_TEMPERATURE
from services.gemini_shared import _gemini_call_with_fallback
from services.chat_utils import (
    _clean_response, _strip_non_latin, _get_sponsor_if_due,
    _strip_sponsor_from_text, StreamBuffer,
)
from services.chat_logger import log_chat_exchange

logger = logging.getLogger(__name__)

_MAX_HISTORY_MESSAGES = 20

# Timeout constants are defined in chat_pipeline_shared.py and passed as parameters.

# V99 F05: Factual data tags — when present, lower temperature to reduce hallucination
_FACTUAL_TAGS = ("[RÉSULTAT SQL", "[RÉSULTAT TIRAGE", "[DONNÉES TEMPS RÉEL")
_TEMPERATURE_FACTUAL = 0.2
_TEMPERATURE_CONVERSATIONAL = _GEMINI_CHAT_TEMPERATURE  # 0.6


def _get_temperature(ctx: dict) -> float:
    """Adaptive temperature: low for factual data responses, normal otherwise."""
    meta = ctx.get("_chat_meta") or {}
    enrichment = meta.get("enrichment_context", "")
    if any(tag in enrichment for tag in _FACTUAL_TAGS):
        return _TEMPERATURE_FACTUAL
    return _TEMPERATURE_CONVERSATIONAL

# V96+V99: Anti-hallucination — extract numbers from context and verify Gemini response
# V99 F03: broadened to match [RÉSULTAT TIRAGE] and [DONNÉES TEMPS RÉEL] in addition to [RÉSULTAT SQL]
_DATA_TAG_RE = re.compile(
    r'\[(?:RÉSULTAT SQL|RÉSULTAT TIRAGE|DONNÉES TEMPS RÉEL)[^\]]*\](.*?)(?:\[/(?:RÉSULTAT SQL|RÉSULTAT TIRAGE)\]|$)',
    re.DOTALL,
)

# V99 F08: detect draw-like number sequences in Gemini response (e.g. "12 - 14 - 22 - 31 - 44")
_DRAW_SEQUENCE_RE = re.compile(
    r'(\d{1,2})\s*[-–—,]\s*(\d{1,2})\s*[-–—,]\s*(\d{1,2})\s*[-–—,]\s*(\d{1,2})\s*[-–—,]\s*(\d{1,2})',
)


def _check_sql_number_hallucination(
    enrichment_context: str, gemini_response: str, phase: str, log_prefix: str,
) -> None:
    """Log a warning when draw numbers from context are missing in Gemini response,
    or when Gemini invents numbers absent from context.

    V99 F03: checks Phase 1 (single number stats + tirage enrichment),
    Phase T (specific draw), and Phase SQL (text-to-SQL results).

    V99 F08: also detects *invented* numbers — draw-like sequences in the
    response that contain numbers absent from the enrichment context.
    """
    if phase not in ("1", "T", "SQL"):
        return
    m = _DATA_TAG_RE.search(enrichment_context or "")
    if not m:
        return
    data_body = m.group(1)
    if "aucun résultat" in data_body.lower():
        return
    context_numbers = set(re.findall(r'\b(\d{1,2})\b', data_body))
    if not context_numbers:
        return
    response_numbers = set(re.findall(r'\b(\d{1,2})\b', gemini_response))
    # Check 1: numbers from context missing in response
    missing = context_numbers - response_numbers
    if missing:
        logger.warning(
            "HALLUCINATION_RISK: %s context numbers %s missing from Gemini response. "
            "Phase=%s | data_excerpt=%.200s",
            log_prefix, sorted(missing, key=int), phase, data_body.strip(),
        )
    # V99 F08: Check 2 — invented numbers in draw-like sequences
    seq_match = _DRAW_SEQUENCE_RE.search(gemini_response)
    if seq_match:
        seq_nums = set(seq_match.groups())
        invented = seq_nums - context_numbers
        if invented:
            logger.warning(
                "HALLUCINATION_INVENTED: %s numbers %s in response draw sequence "
                "but ABSENT from context. Phase=%s | sequence=%s",
                log_prefix, sorted(invented, key=int), phase,
                seq_match.group(0),
            )
# This module does NOT import from shared (avoids circular dependency).


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
    history = history or []
    if len(history) > _MAX_HISTORY_MESSAGES:
        logger.info("Gemini history truncated: %d → %d messages", len(history), _MAX_HISTORY_MESSAGES)
        history = history[-_MAX_HISTORY_MESSAGES:]
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
                "generationConfig": {"temperature": _get_temperature(ctx), "maxOutputTokens": 300},
            },
            timeout=ctx.get("_timeout_gemini_chat", 15),
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
            ctx["contents"], timeout=ctx.get("_timeout_gemini_stream", 15),
            call_type=call_type, lang=lang,
            temperature=_get_temperature(ctx),
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
        _full_response = "".join(_stream_chunks)
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, _full_response)
        # V96: Anti-hallucination check — warn if SQL numbers missing from response
        _meta = ctx.get("_chat_meta") or {}
        _check_sql_number_hallucination(
            _meta.get("enrichment_context", ""), _full_response,
            _meta.get("phase", ""), log_prefix,
        )
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
                              log_prefix, breaker=None,
                              timeout_context=30, timeout_gemini=15):
    """
    Common pitch pipeline after validation.
    context_coro: awaitable that returns the stats context string.
    Calls context_coro → load_prompt → Gemini → parse JSON.
    Returns result dict.
    """
    try:
        context = await asyncio.wait_for(context_coro, timeout=timeout_context)
    except asyncio.TimeoutError:
        logger.error(f"{log_prefix} Timeout {timeout_context}s contexte stats")
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
            timeout=timeout_gemini,
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
