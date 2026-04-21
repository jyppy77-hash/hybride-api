"""
Shared Gemini enrichment logic — V71 R3c / V73 F03.

Extracts the common Gemini call → parse → track → fallback flow
from gemini.py and em_gemini.py. Both files delegate to
_enrich_analysis_base() with game-specific parameters.

F03: _gemini_call_with_fallback() extracts the shared try/except skeleton
(CircuitOpen/Timeout/Exception → fallback) used by 3 call sites.
"""

import os
import logging
import time
import httpx

from services.circuit_breaker import gemini_breaker, CircuitOpenError

logger = logging.getLogger(__name__)

# F12: track fire-and-forget tasks for graceful shutdown
_PENDING_TASKS: set = set()


def _track_task(task):
    """Add a task to _PENDING_TASKS with auto-discard on completion."""
    _PENDING_TASKS.add(task)
    task.add_done_callback(_PENDING_TASKS.discard)


async def await_pending_tasks(timeout: float = 5.0):
    """Await all pending fire-and-forget tasks (for graceful shutdown)."""
    import asyncio
    if _PENDING_TASKS:
        await asyncio.wait(_PENDING_TASKS, timeout=timeout)

GEMINI_MODEL_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# Shared i18n system instructions for enrichment (6 languages).
# Used by both Loto and EM — identical content.
ENRICHMENT_INSTRUCTIONS = {
    "fr": (
        "OBLIGATION ABSOLUE : Tu écris TOUJOURS en français correct "
        "avec TOUS les accents (é, è, ê, ë, à, â, ç, ù, û, ô, î, ï). "
        "Exemples : \"numéro\" (jamais \"numero\"), \"fréquence\" (jamais \"frequence\"), "
        "\"régularité\" (jamais \"regularite\"), \"dernière\" (jamais \"derniere\"), "
        "\"élevé\" (jamais \"eleve\"), \"intéressant\" (jamais \"interessant\"), "
        "\"présente\" (jamais \"presente\"), \"conformité\" (jamais \"conformite\"), "
        "\"équilibre\" (jamais \"equilibre\"), \"mérite\" (jamais \"merite\"), "
        "\"sélection\" (jamais \"selection\"), \"mélange\" (jamais \"melange\"), "
        "\"répartition\" (jamais \"repartition\"). "
        "Un texte sans accents est considéré comme un BUG CRITIQUE."
    ),
    "en": (
        "MANDATORY: You ALWAYS write in correct English. "
        "Keep a professional, educational tone suitable for a PDF report. "
        "Never promise winnings. Stay neutral and factual."
    ),
    "es": (
        "OBLIGATORIO: Escribes SIEMPRE en español correcto. "
        "Mantén un tono profesional y pedagógico adecuado para un informe PDF. "
        "Nunca prometas ganancias. Mantente neutro y factual."
    ),
    "pt": (
        "OBRIGATÓRIO: Escreves SEMPRE em português correto de Portugal "
        "com TODOS os acentos (á, à, â, ã, é, ê, í, ó, ô, õ, ú, ç). "
        "Mantém um tom profissional e pedagógico adequado a um relatório PDF. "
        "Nunca prometas ganhos. Mantém-te neutro e factual."
    ),
    "de": (
        "PFLICHT: Du schreibst IMMER in korrektem Deutsch "
        "mit allen Umlauten (ä, ö, ü, ß). "
        "Halte einen professionellen, pädagogischen Ton, der für einen PDF-Bericht geeignet ist. "
        "Verspreche niemals Gewinne. Bleibe neutral und sachlich."
    ),
    "nl": (
        "VERPLICHT: Je schrijft ALTIJD in correct Nederlands. "
        "Houd een professionele, educatieve toon aan die geschikt is voor een PDF-rapport. "
        "Beloof nooit winsten. Blijf neutraal en feitelijk."
    ),
}


async def _gemini_call_with_fallback(
    coro,
    *,
    fallback_fn,
    log_prefix: str = "[GEMINI]",
    breaker=None,
):
    """
    F03: shared try/except skeleton for Gemini calls.

    Wraps a coroutine (the Gemini HTTP call) with CircuitOpen/Timeout/Exception
    handling, returning a fallback on failure.

    Args:
        coro: awaitable — the Gemini breaker.call() coroutine
        fallback_fn: callable(error_type: str) → fallback value
            error_type is one of: "circuit_open", "timeout", "error"
        log_prefix: for logging
        breaker: unused (kept for API symmetry, caller passes breaker to coro)

    Returns:
        httpx.Response on success, or the result of fallback_fn(error_type) on failure.
    """
    try:
        return await coro
    except CircuitOpenError:
        logger.warning(f"{log_prefix} Circuit breaker ouvert — fallback")
        return fallback_fn("circuit_open")
    except httpx.TimeoutException:
        logger.warning(f"{log_prefix} Timeout Gemini — fallback")
        return fallback_fn("timeout")
    except Exception as e:
        logger.error(f"{log_prefix} Erreur Gemini: {e}")
        return fallback_fn("error")


async def enrich_analysis_base(
    analysis_local: str,
    prompt: str,
    *,
    http_client: httpx.AsyncClient,
    lang: str = "fr",
    instructions: dict | None = None,
    call_type: str = "enrichment",
    log_prefix: str = "[META TEXTE]",
    breaker=None,
) -> dict:
    """
    Shared Gemini enrichment: call → parse → track → fallback.

    Args:
        analysis_local: raw analysis text (fallback value)
        prompt: full prompt to send to Gemini (template + analysis)
        http_client: httpx async client
        lang: language code for system instruction
        instructions: i18n dict (defaults to ENRICHMENT_INSTRUCTIONS)
        call_type: tracking call type label
        log_prefix: log prefix string
        breaker: circuit breaker instance (defaults to global gemini_breaker)

    Returns:
        dict with 'analysis_enriched' and 'source'
    """
    _instructions = instructions or ENRICHMENT_INSTRUCTIONS
    _breaker = breaker or gemini_breaker

    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        logger.warning(f"{log_prefix} GEM_API_KEY non configuree - fallback local")
        return {"analysis_enriched": analysis_local, "source": "hybride_local"}

    system_instruction_text = _instructions.get(lang, _instructions["fr"])

    logger.debug(f"{log_prefix} Prompt construit ({len(prompt)} chars), appel Gemini...")

    _fallback_local = {"analysis_enriched": analysis_local, "source": "hybride_local"}

    def _fallback(error_type):
        if error_type == "circuit_open":
            return {"analysis_enriched": analysis_local, "source": "fallback_circuit"}
        return _fallback_local

    _t0 = time.monotonic()
    result = await _gemini_call_with_fallback(
        _breaker.call(
            http_client,
            GEMINI_MODEL_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": gem_api_key,
            },
            json={
                "systemInstruction": {
                    "parts": [{"text": system_instruction_text}]
                },
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 250,
                },
            },
            timeout=10.0,  # V129.1: strict 10s explicit (fix hang 15s observed
                           # in half_open — was falling back to AsyncClient default 20s).
        ),
        fallback_fn=_fallback,
        log_prefix=log_prefix,
    )

    # If fallback was returned (dict, not httpx.Response)
    if isinstance(result, dict):
        return result

    response = result
    _dur_ms = (time.monotonic() - _t0) * 1000
    if response.status_code == 200:
        data = response.json()
        _usage = data.get("usageMetadata", {})
        _tin = _usage.get("promptTokenCount", 0)
        _tout = _usage.get("candidatesTokenCount", 0)
        try:
            from services.gcp_monitoring import track_gemini_call
            import asyncio
            _track_task(asyncio.ensure_future(track_gemini_call(
                _dur_ms, _tin, _tout, call_type=call_type, lang=lang)))
        except Exception:
            pass
        candidates = data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts:
                enriched_text = parts[0].get("text", "").strip()
                if enriched_text:
                    logger.info(f"{log_prefix} Gemini OK")
                    return {"analysis_enriched": enriched_text, "source": "gemini_enriched"}

        logger.warning(f"{log_prefix} Reponse Gemini incomplete — fallback local")
    else:
        logger.warning(f"{log_prefix} Reponse Gemini HTTP {response.status_code}")
        try:
            from services.gcp_monitoring import track_gemini_call
            import asyncio
            _track_task(asyncio.ensure_future(track_gemini_call(
                _dur_ms, error=True, call_type=call_type, lang=lang)))
        except Exception:
            pass

    return _fallback_local
