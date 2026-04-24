import logging
import time
import asyncio
import httpx  # V131.A: conservé pour rétrocompat signature publique (http_client param)

from google.genai import errors as genai_errors, types

from services.prompt_loader import load_prompt
from services.circuit_breaker import gemini_breaker, CircuitOpenError
from services.gemini_shared import (
    _get_client,
    _is_rate_limit_error,
    _track_task,
    _VERTEX_MODEL_NAME,
    _V131_E_SAFETY_SETTINGS_RELAX,
    enrich_analysis_base,
    ENRICHMENT_INSTRUCTIONS,
)

logger = logging.getLogger(__name__)

# V131.A — DEPRECATED : URLs AI Studio historiques. Usage legacy par chat_sql.py
# et chat_sql_em.py (HORS SCOPE V131.A, migration prévue V131.D). Ne plus utiliser
# dans tout nouveau code. Suppression définitive V131.D.
GEMINI_MODEL_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GEMINI_STREAM_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:streamGenerateContent?alt=sse"
)

# F08 V83: 0.6 = balance factualité/naturel pour chatbot data-grounded
_GEMINI_CHAT_TEMPERATURE = 0.6


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
        # F10 V82: minimal fallback with ERROR log (replaces 16-line hardcoded prompt).
        # In production, prompt files always exist. This triggers monitoring alerts.
        logger.error("[META TEXTE] CRITICAL: prompt file missing for window=%s — using minimal fallback", window_key)
        prompt = (
            "Tu es un assistant statistique pour le Loto français. "
            "Reformule ce texte de manière concise et factuelle. "
            "Ne promets jamais de gain. Maximum 4 phrases.\n\n"
            + analysis_local
        )

    return await enrich_analysis_base(
        analysis_local, prompt, http_client=http_client, lang=lang,
        call_type="enrichment_loto", log_prefix="[META TEXTE]",
        breaker=gemini_breaker,
    )


async def stream_gemini_chat(http_client, gem_api_key, system_prompt, contents, timeout=10.0,
                             call_type="", lang="", temperature=None):
    """
    Async generator — stream text chunks from Gemini Vertex AI (google-genai SDK).

    V131.A — Migration AI Studio httpx → google-genai SDK.
    Les paramètres `http_client` et `gem_api_key` sont conservés pour rétrocompat
    signature (appelants `chat_pipeline.py:262`, `chat_pipeline_em.py:252`, tests)
    mais IGNORÉS côté implémentation. Cleanup V131.D.

    V129.1 : default timeout 15.0 → 10.0s (strict user-facing).
    Yields str chunks. Manages circuit breaker state manually.
    Tracks Gemini usage (tokens, duration) via gcp_monitoring.

    ⚠️ V131.A LIMITATION : asyncio.wait_for ne timeout que le démarrage du
    stream (await client.aio.models.generate_content_stream(...)), PAS
    l'itération inter-chunk via `async for chunk in stream`. Si Vertex bloque
    entre 2 chunks après démarrage, stream hang indéfiniment côté consommateur.
    À surveiller en prod (Cloud Run logs duration > 30s sur /chat streaming).
    Hotfix V131.C ou V132 si observé : wrapper per-chunk
    via asyncio.wait_for(iterator.__anext__(), timeout=N).
    """
    _ = http_client, gem_api_key  # noqa: F841  # V131.A DEPRECATED — paramètres ignorés

    current = gemini_breaker.state
    if current == gemini_breaker.OPEN:
        raise CircuitOpenError("Circuit ouvert — fallback immediat")

    _t0 = time.monotonic()
    _usage_tin = 0
    _usage_tout = 0
    _max_attempts = 2  # 1 try + 1 retry on transient timeout

    _temperature = temperature if temperature is not None else _GEMINI_CHAT_TEMPERATURE
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=_temperature,
        max_output_tokens=300,
        # V131.E HOTFIX — safety_settings BLOCK_ONLY_HIGH (réduit faux positifs SAFETY)
        # Cf. docs/DIAGNOSTIC_CHATBOT_STREAMING_TRONQUE.md
        safety_settings=_V131_E_SAFETY_SETTINGS_RELAX,
        # V131.E HOTFIX — thinking_budget=0 désactive le raisonnement interne de gemini-2.5-flash
        # qui consommait ~293 tokens sur 300 dispos, laissant ~7 tokens visibles → MAX_TOKENS.
        # Root cause confirmée empiriquement 24/04 (logs [STREAM] finish_reason=MAX_TOKENS tout=7).
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    for _attempt in range(_max_attempts):
        try:
            client = _get_client()
            # V131.A — SDK B streaming : client.aio.models.generate_content_stream
            # retourne un AsyncIterable[GenerateContentResponse]. Chaque chunk a .text
            # (peut être vide) et .usage_metadata (présent sur dernier chunk).
            # Timeout strict via asyncio.wait_for sur le get du stream (start only).
            stream = await asyncio.wait_for(
                client.aio.models.generate_content_stream(
                    model=_VERTEX_MODEL_NAME,
                    contents=contents,
                    config=config,
                ),
                timeout=timeout,
            )

            # V131.E HOTFIX — Inspect finish_reason pour détecter SAFETY/RECITATION/MAX_TOKENS
            # Cf. docs/DIAGNOSTIC_CHATBOT_STREAMING_TRONQUE.md (50% users tronqués pré-fix)
            _last_finish_reason = None

            async for chunk in stream:
                # V131.E — Capture finish_reason du chunk final
                _cands = getattr(chunk, "candidates", None) or []
                if _cands:
                    _fr = getattr(_cands[0], "finish_reason", None)
                    if _fr is not None:
                        _last_finish_reason = _fr
                # Capture usage_metadata — présent sur dernier chunk
                _um = getattr(chunk, "usage_metadata", None)
                if _um:
                    _usage_tin = getattr(_um, "prompt_token_count", _usage_tin)
                    _usage_tout = getattr(_um, "candidates_token_count", _usage_tout)
                # .text peut lever ValueError si chunk SAFETY-blocked (finish_reason non-STOP)
                try:
                    text = chunk.text or ""
                except (ValueError, AttributeError):
                    continue
                if text:
                    yield text

            # V131.E HOTFIX — Détection arrêt prématuré du stream (SAFETY/RECITATION/MAX_TOKENS)
            _fr_name = str(_last_finish_reason) if _last_finish_reason is not None else "STOP"
            _fr_ok = any(ok in _fr_name for ok in ("STOP", "FinishReason.STOP"))
            if not _fr_ok:
                _lang_safe = lang or "fr"
                logger.warning(
                    "[STREAM] Gemini finish_reason=%s tout=%d tin=%d lang=%s (SAFETY/RECITATION/MAX_TOKENS suspected)",
                    _fr_name, _usage_tout, _usage_tin, _lang_safe,
                )
                # Yield fallback suffix user-facing i18n 6 langues
                _FALLBACK_SUFFIX = {
                    "fr": "\n\n— Réponse interrompue, peux-tu reformuler ta question ? 🙏",
                    "en": "\n\n— Response interrupted, could you rephrase your question? 🙏",
                    "es": "\n\n— Respuesta interrumpida, ¿puedes reformular tu pregunta? 🙏",
                    "pt": "\n\n— Resposta interrompida, podes reformular a tua pergunta? 🙏",
                    "de": "\n\n— Antwort unterbrochen, kannst du bitte neu formulieren? 🙏",
                    "nl": "\n\n— Antwoord onderbroken, kun je je vraag herformuleren? 🙏",
                }
                yield _FALLBACK_SUFFIX.get(_lang_safe, _FALLBACK_SUFFIX["fr"])

            gemini_breaker._record_success()

            # Track usage after stream completes
            _dur_ms = (time.monotonic() - _t0) * 1000
            try:
                from services.gcp_monitoring import track_gemini_call
                _track_task(asyncio.ensure_future(track_gemini_call(
                    _dur_ms, _usage_tin, _usage_tout, call_type=call_type, lang=lang)))
            except Exception:
                pass
            return  # success — exit retry loop

        except (genai_errors.ClientError, genai_errors.ServerError) as e:
            # Hard API failure (429/5xx/4xx) — record and return. Pas de retry ici :
            # retry backoff V129.1 est dans handle_pitch_common uniquement (stream
            # user-facing conserve son pattern V71 F06 : 1 retry transient timeout).
            if _is_rate_limit_error(e):
                logger.warning("[STREAM] Gemini 429 ResourceExhausted — fallback")
            else:
                logger.warning("[STREAM] Gemini SDK error %s: %s", type(e).__name__, e)
            gemini_breaker._record_failure()
            _dur_ms = (time.monotonic() - _t0) * 1000
            try:
                from services.gcp_monitoring import track_gemini_call
                _track_task(asyncio.ensure_future(track_gemini_call(
                    _dur_ms, error=True, call_type=call_type, lang=lang)))
            except Exception:
                pass
            return

        except (asyncio.TimeoutError, OSError):
            # Transient timeout — retry 1× avec backoff 2s (V71 F06 préservé)
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
                _track_task(asyncio.ensure_future(track_gemini_call(
                    _dur_ms, error=True, call_type=call_type, lang=lang)))
            except Exception:
                pass
            raise
