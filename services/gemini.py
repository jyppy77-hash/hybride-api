import logging
import random
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

# F08 V83: 0.6 = balance factualité/naturel pour chatbot data-grounded
_GEMINI_CHAT_TEMPERATURE = 0.6

# V143 — Timeouts streaming distincts (audits NoChunks 11/06/2026) :
# 1er token : Vertex sous tension DSQ peut mettre >8s à démarrer (8 cas/24h tués
# à tort par le timeout unique 8s V131.F — le wait_for de start ne couvre que
# l'obtention du stream, pas le 1er token). 15s couvre le slow-start observé
# (durées NoChunks jusqu'à ~15s en prod) sans hang infini.
# Inter-chunk : inchangé V131.F (latence normale ~50-200ms, 8s = >40×).
_FIRST_TOKEN_TIMEOUT = 15.0
_INTER_CHUNK_TIMEOUT = 8.0

# V143 — Retry 429 pattern V129.1 porté au stream chat. DSQ Vertex : 429 régional
# incompressible (aucun quota RPM par projet sur gemini-2.5-flash — audit Service
# Usage 11/06), réponse documentée Google = retry client avec backoff. Cap 12s
# (≠ 14s pitch) : un 429 stream est borné par le start-timeout 10s (wait_for)
# → 12s laisse passer 2 retries dans le cas typique 429 rapide (<1s), et évite
# le piège pitch "no budget left at attempt=1" (timeout 45s pitch vs cap 14s).
_V143_RETRY_BACKOFF_BASE = 2.0   # seconds (V129.1)
_V143_RETRY_CAP_TOTAL = 12.0     # seconds (calibré chat)
_V143_RETRY_JITTER_MAX = 1.0     # seconds (V129.1 equal jitter)


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
                             call_type="", lang="", temperature=None,
                             max_retries=0, failure_box=None):
    """
    Async generator — stream text chunks from Gemini Vertex AI (google-genai SDK).

    V131.A — Migration AI Studio httpx → google-genai SDK.
    Les paramètres `http_client` et `gem_api_key` sont conservés pour rétrocompat
    signature (appelants `chat_pipeline.py:262`, `chat_pipeline_em.py:252`, tests)
    mais IGNORÉS côté implémentation. Cleanup V131.D.

    V129.1 : default timeout 15.0 → 10.0s (strict user-facing).
    Yields str chunks. Manages circuit breaker state manually.
    Tracks Gemini usage (tokens, duration) via gcp_monitoring.

    V131.F — Per-chunk inter-chunk timeout 8s (was: start-only timeout
    laissait hang infini si Vertex bloquait entre 2 chunks après démarrage).
    Cf audit READ-ONLY 2026-05-05 : 50/58 erreurs `NoChunks` + cas terrain
    Cloud Run /api/hybride-chat duration=17379ms (4 mai). 8s = >40× la latence
    inter-chunk normale (~50-200ms), couvre les ralentissements ponctuels
    sans laisser hang infini.

    V143 — (audits NoChunks 11/06/2026 : 52% requêtes = 429 DSQ régional Vertex)
      - `max_retries` (opt-in, défaut 0) : retry 429 pattern V129.1 — backoff
        2·2^n + jitter [0,1s], cap total 12s, UNIQUEMENT si zéro chunk émis
        (garde `_yielded_any` anti-double-émission SSE), check breaker OPEN à
        chaque itération, retries silencieux pour le breaker (max 1
        `_record_failure` par requête utilisateur, à la sortie terminale).
      - `failure_box` (opt-in) : out-param dict où la cause terminale zéro-chunk
        est écrite ("Vertex429" / "InterChunkTimeout" / "VertexError") — lue par
        stream_and_respond pour différencier `error_detail` (ex-fourre-tout
        NoChunks). Additif strict : sémantique exceptions/breaker inchangée.
      - Timeout 1er-token 15s distinct de l'inter-chunk 8s (slow-start DSQ).
    """
    _ = http_client, gem_api_key  # noqa: F841  # V131.A DEPRECATED — paramètres ignorés

    _box = failure_box if failure_box is not None else {}

    _t0 = time.monotonic()
    _usage_tin = 0
    _usage_tout = 0
    _timeout_retries_left = 1  # V71 F06 préservé : 1 retry transient start-timeout
    _attempt_429 = 0           # V143 : compteur retries 429 (exponent backoff)
    _yielded_any = False       # V143 : garde anti-double-émission SSE

    _temperature = temperature if temperature is not None else _GEMINI_CHAT_TEMPERATURE
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=_temperature,
        max_output_tokens=1500,  # V131.F : 300→1500 (élimine MAX_TOKENS chat sur prompts ~12-15k tokens input observés en prod 4-5 mai)
        # V131.E HOTFIX — safety_settings BLOCK_ONLY_HIGH (réduit faux positifs SAFETY)
        # Cf. docs/DIAGNOSTIC_CHATBOT_STREAMING_TRONQUE.md
        safety_settings=_V131_E_SAFETY_SETTINGS_RELAX,
        # V131.E HOTFIX — thinking_budget=0 désactive le raisonnement interne de gemini-2.5-flash
        # qui consommait ~293 tokens sur 300 dispos, laissant ~7 tokens visibles → MAX_TOKENS.
        # Root cause confirmée empiriquement 24/04 (logs [STREAM] finish_reason=MAX_TOKENS tout=7).
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    while True:
        # V143 — check breaker à CHAQUE itération (pattern V129.1) : respecte un
        # OPEN posé par des failures concurrentes pendant un backoff. Atteignable
        # uniquement avant toute émission SSE (les retries sont gated par
        # `_yielded_any`) → CircuitOpenError safe côté caller (1 seul fallback).
        if gemini_breaker.state == gemini_breaker.OPEN:
            raise CircuitOpenError("Circuit ouvert — fallback immediat")

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

            # V131.F + V143 — Per-chunk timeout : 1er token 15s (slow-start DSQ),
            # inter-chunk 8s (latence normale ~50-200ms, >40×). Résout le hang
            # inter-chunk Vertex (ex-LIMITATION V131.A) sans tuer les démarrages lents.
            _stream_iter = stream.__aiter__()
            _first_chunk = True
            while True:
                _tmo = _FIRST_TOKEN_TIMEOUT if _first_chunk else _INTER_CHUNK_TIMEOUT
                try:
                    chunk = await asyncio.wait_for(_stream_iter.__anext__(), timeout=_tmo)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    logger.warning(
                        "[STREAM] V131.F %s timeout (%.0fs) — closing stream "
                        "(call_type=%s lang=%s tout=%d)",
                        "first-token" if _first_chunk else "inter-chunk",
                        _tmo, call_type, lang, _usage_tout,
                    )
                    if not _yielded_any:
                        _box["cause"] = "InterChunkTimeout"  # V143 #3
                    break
                _first_chunk = False

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
                    _yielded_any = True
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

            # ⚠️ Bug connu #4 (hors scope V143, signalé audits 11/06) : un timeout
            # 1er-token/inter-chunk aboutit ici → record_success — sémantique
            # V131.F préservée à l'identique, à arbitrer dans un lot dédié.
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
            # Hard API failure (429/5xx/4xx) — record and return.
            # V143 : retry 429 pattern V129.1, UNIQUEMENT si zéro chunk émis
            # (un retry après émission = texte en double côté SSE, interdit).
            if _is_rate_limit_error(e):
                if not _yielded_any and _attempt_429 < max_retries:
                    _remaining = _V143_RETRY_CAP_TOTAL - (time.monotonic() - _t0)
                    if _remaining > 0:
                        backoff = (
                            _V143_RETRY_BACKOFF_BASE * (2 ** _attempt_429)
                            + random.uniform(0, _V143_RETRY_JITTER_MAX)
                        )
                        backoff = min(backoff, _remaining)
                        logger.info(
                            "[STREAM] [V129_1_RETRY] attempt=%d/%d 429, backoff=%.1fs",
                            _attempt_429 + 1, max_retries, backoff,
                        )
                        _attempt_429 += 1
                        await asyncio.sleep(backoff)
                        continue  # retry silencieux — pas de _record_failure
                    logger.info(
                        "[STREAM] [V129_1_RETRY] no budget left at attempt=%d",
                        _attempt_429,
                    )
                # V143 #3 — corps de l'exception loggé (le message brut DSQ vs
                # quota était irrécupérable avec la chaîne fixe — audit 11/06)
                logger.warning("[STREAM] Gemini 429 ResourceExhausted — fallback: %s", e)
                _box["cause"] = "Vertex429"
            else:
                logger.warning("[STREAM] Gemini SDK error %s: %s", type(e).__name__, e)
                if not _yielded_any:
                    _box["cause"] = "VertexError"  # V143 D2 — 4xx/5xx zéro-chunk
            gemini_breaker._record_failure()  # terminal : max 1 failure/requête
            _dur_ms = (time.monotonic() - _t0) * 1000
            try:
                from services.gcp_monitoring import track_gemini_call
                _track_task(asyncio.ensure_future(track_gemini_call(
                    _dur_ms, error=True, call_type=call_type, lang=lang)))
            except Exception:
                pass
            return

        except (asyncio.TimeoutError, OSError):
            # Transient start-timeout — retry 1× avec backoff 2s (V71 F06 préservé)
            if _timeout_retries_left > 0:
                _timeout_retries_left -= 1
                logger.warning("[STREAM] Gemini timeout, retry 1/2 (backoff 2s)")
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
