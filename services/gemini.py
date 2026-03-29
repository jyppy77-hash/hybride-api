import os
import json
import logging
import time
import asyncio
import httpx

from services.prompt_loader import load_prompt
from services.circuit_breaker import gemini_breaker, CircuitOpenError
from services.gemini_shared import enrich_analysis_base, ENRICHMENT_INSTRUCTIONS

logger = logging.getLogger(__name__)

GEMINI_MODEL_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GEMINI_STREAM_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:streamGenerateContent?alt=sse"
)


# V70 F04: i18n system instructions — now shared in gemini_shared.py
_ENRICHMENT_INSTRUCTIONS = ENRICHMENT_INSTRUCTIONS  # backward compat alias


async def enrich_analysis(analysis_local: str, window: str = "GLOBAL", *, http_client: httpx.AsyncClient, lang: str = "fr") -> dict:
    """Enrichit le texte d'analyse Loto via Gemini (delegates to shared base)."""
    window_key = window or "GLOBAL"
    logger.info(f"[META TEXTE] Fenetre={window_key}")

    # Build prompt (game-specific: Loto prompt loader)
    prompt_template = load_prompt(window_key)
    if prompt_template:
        prompt = prompt_template + "\n" + analysis_local
    else:
        # Safety fallback: used only if prompt file is missing from disk.
        # In production, prompt files always exist. This is defense-in-depth.
        prompt = f"""[LANGUE ET ORTHOGRAPHE — RÈGLE ABSOLUE]
Tu réponds TOUJOURS en français correct avec TOUS les accents : é, è, ê, ë, à, â, ç, ù, û, ô, î, ï.
Exemples obligatoires : "numéro" (jamais "numero"), "fréquence" (jamais "frequence"), "régularité" (jamais "regularite"), "dernière" (jamais "derniere"), "élevé" (jamais "eleve"), "intéressant" (jamais "interessant"), "présente" (jamais "presente"), "conformité" (jamais "conformite"), "éloigne" (jamais "eloigne"), "équilibre" (jamais "equilibre"), "mérite" (jamais "merite"), "peut-être" (jamais "peut-etre"), "sélection" (jamais "selection"), "mélange" (jamais "melange"), "répartition" (jamais "repartition").
C'est une règle NON NÉGOCIABLE. Un texte sans accents est considéré comme un BUG.

Tu es un expert en statistiques de loterie.
Reformule ce texte d'analyse de manière pédagogique et accessible.
Règles strictes :
- Ne promets JAMAIS de gain
- Reste neutre et informatif
- Garde un ton professionnel
- Maximum 4 phrases fluides
- Ne modifie pas les chiffres

Texte a reformuler :
{analysis_local}"""

    return await enrich_analysis_base(
        analysis_local, prompt, http_client=http_client, lang=lang,
        call_type="enrichment_loto", log_prefix="[META TEXTE]",
        breaker=gemini_breaker,
    )


async def stream_gemini_chat(http_client, gem_api_key, system_prompt, contents, timeout=15.0,
                             call_type="", lang=""):
    """
    Async generator — stream text chunks from Gemini streaming API.
    Yields str chunks. Manages circuit breaker state manually.
    Tracks Gemini usage (tokens, duration) via gcp_monitoring.
    """
    current = gemini_breaker.state
    if current == gemini_breaker.OPEN:
        raise CircuitOpenError("Circuit ouvert — fallback immediat")

    _t0 = time.monotonic()
    _usage_tin = 0
    _usage_tout = 0
    _max_attempts = 2  # 1 try + 1 retry on transient timeout

    for _attempt in range(_max_attempts):
        try:
            async with http_client.stream(
                "POST",
                GEMINI_STREAM_URL,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": gem_api_key,
                },
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": contents,
                    "generationConfig": {
                        "temperature": 0.8,
                        "maxOutputTokens": 300,
                    },
                },
                timeout=timeout,
            ) as response:
                if response.status_code >= 500 or response.status_code == 429:
                    gemini_breaker._record_failure()
                    return

                if response.status_code != 200:
                    logger.warning(f"[STREAM] Gemini HTTP {response.status_code}")
                    return

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                        # Capture usage_metadata from last chunk
                        _um = data.get("usageMetadata")
                        if _um:
                            _usage_tin = _um.get("promptTokenCount", _usage_tin)
                            _usage_tout = _um.get("candidatesTokenCount", _usage_tout)
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                text = parts[0].get("text", "")
                                if text:
                                    yield text
                    except json.JSONDecodeError:
                        continue

                gemini_breaker._record_success()

                # Track usage after stream completes
                _dur_ms = (time.monotonic() - _t0) * 1000
                try:
                    from services.gcp_monitoring import track_gemini_call
                    asyncio.ensure_future(track_gemini_call(
                        _dur_ms, _usage_tin, _usage_tout, call_type=call_type, lang=lang))
                except Exception:
                    pass
                return  # success — exit retry loop

        except (httpx.TimeoutException, httpx.ConnectError, OSError):
            if _attempt < _max_attempts - 1:
                logger.warning("[STREAM] Gemini timeout, retry %d/%d (backoff 2s)",
                               _attempt + 1, _max_attempts)
                await asyncio.sleep(2)
                continue
            # Final attempt failed — record failure and raise
            gemini_breaker._record_failure()
            _dur_ms = (time.monotonic() - _t0) * 1000
            try:
                from services.gcp_monitoring import track_gemini_call
                asyncio.ensure_future(track_gemini_call(
                    _dur_ms, error=True, call_type=call_type, lang=lang))
            except Exception:
                pass
            raise
