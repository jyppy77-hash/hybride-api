"""
Shared Gemini enrichment logic — V71 R3c / V73 F03 / V131.A google-genai SDK.

Extracts the common Gemini call → parse → track → fallback flow
from gemini.py and em_gemini.py. Both files delegate to
_enrich_analysis_base() with game-specific parameters.

V131.A — Migration AI Studio httpx → Google Gen AI SDK (`google-genai`) targeting
Vertex AI. Authentication via ADC (Application Default Credentials) : SA Cloud Run
en prod (`roles/aiplatform.user` attached), `gcloud auth application-default login`
en local. `genai.Client(vertexai=True, project, location)` détecte automatiquement
les credentials ambiants — aucune divergence code local/prod.

Modèle cible : `gemini-2.5-flash` (région `europe-west1`). Le SDK A
`vertexai.generative_models` est DEPRECATED par Google au 24/06/2026 — ce module
utilise le SDK B `google-genai` qui est le successeur supporté.
"""

import asyncio
import logging
import time

import httpx  # V131.A: conservé pour rétrocompat signatures publiques (http_client param)

from google import genai
from google.genai import errors as genai_errors, types

from services.circuit_breaker import gemini_breaker, CircuitOpenError

logger = logging.getLogger(__name__)

# V131.A — Config Vertex AI figée (projet unique LotoIA + modèle unique)
_VERTEX_PROJECT = "gen-lang-client-0680927607"
_VERTEX_LOCATION = "europe-west1"
_VERTEX_MODEL_NAME = "gemini-2.5-flash"

# V131.A — Client SDK B singleton lazy. Pas au module-load pour préserver
# les tests offline (collect-only sans ADC). Pas de thread-safety stricte
# nécessaire : race bénigne (double assignment idempotent + `genai.Client(...)`
# stateless côté config, pas d'I/O au constructeur).
_CLIENT: "genai.Client | None" = None


def _get_client() -> "genai.Client":
    """V131.A — Retourne le singleton `genai.Client` Vertex AI (lazy init).

    Utilise ADC :
      - Prod Cloud Run : Service Account attaché (810368514982-compute@...)
        avec rôle `roles/aiplatform.user` (binding posé 22/04/2026).
      - Local dev : `gcloud auth application-default login` + quota project
        = `gen-lang-client-0680927607`.

    Réutilisé par `gemini.py` (stream_gemini_chat) et `chat_pipeline_gemini.py`
    (call_gemini_and_respond, handle_pitch_common).
    """
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = genai.Client(
            vertexai=True,
            project=_VERTEX_PROJECT,
            location=_VERTEX_LOCATION,
        )
        logger.info(
            "[VERTEX] genai.Client init OK project=%s location=%s model=%s",
            _VERTEX_PROJECT, _VERTEX_LOCATION, _VERTEX_MODEL_NAME,
        )
    return _CLIENT


# F12: track fire-and-forget tasks for graceful shutdown
_PENDING_TASKS: set = set()


def _track_task(task):
    """Add a task to _PENDING_TASKS with auto-discard on completion."""
    _PENDING_TASKS.add(task)
    task.add_done_callback(_PENDING_TASKS.discard)


async def await_pending_tasks(timeout: float = 5.0):
    """Await all pending fire-and-forget tasks (for graceful shutdown)."""
    if _PENDING_TASKS:
        await asyncio.wait(_PENDING_TASKS, timeout=timeout)


# V131.A — DEPRECATED : URL AI Studio historique. Usage legacy par chat_sql*
# (HORS SCOPE V131.A, migration prévue V131.D). Suppression définitive V131.D.
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


# V131.E HOTFIX — safety_settings relaxés pour contenu LotoIA (stats factuelles).
# Réduit faux positifs SAFETY sur prompts lourds 10k-13k tokens (chat_loto/chat_em).
# BLOCK_ONLY_HIGH choisi (pas BLOCK_NONE qui nécessite CSA externe non activée projet).
# Appliqué sur les 4 call sites Gemini/Vertex : stream chat, non-stream chat, pitch,
# enrich_analysis. Cf. docs/DIAGNOSTIC_CHATBOT_STREAMING_TRONQUE.md
_V131_E_SAFETY_SETTINGS_RELAX = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
]


# V131.A — `_gemini_call_with_fallback` supprimé. Ses 3 callers (enrich_analysis_base
# dans ce fichier, call_gemini_and_respond + handle_pitch_common dans chat_pipeline_gemini.py)
# migrent vers Google Gen AI SDK avec try/except inline. Raison : le wrapper mélangeait
# la sémantique "appel Gemini httpx.post" avec un breaker state machine, alors qu'en SDK B
# chaque call site a une logique de gestion exceptions spécifique (streaming vs pitch-retry
# vs enrichment simple). Lisibilité > DRY sur 3 usages avec mapping exceptions simplifié
# (3 classes SDK B vs 6 classes SDK A).


def _is_rate_limit_error(e: Exception) -> bool:
    """V131.A — détection 429 hybride : .code int (primary) + .status string (fallback).

    `google.genai.errors.ClientError` expose `.code: int` (assigné dans APIError.__init__)
    et `.status: str` (canonical gRPC status, ex "RESOURCE_EXHAUSTED" pour 429).
    Stratégie défensive sur évolution future API.
    """
    if getattr(e, "code", None) == 429:
        return True
    status = getattr(e, "status", "")
    return status == "RESOURCE_EXHAUSTED" or "429" in str(e)


def _track_error(t0: float, call_type: str, lang: str) -> None:
    """V131.A — helper tracking d'erreur Vertex (fire-and-forget)."""
    _dur_ms = (time.monotonic() - t0) * 1000
    try:
        from services.gcp_monitoring import track_gemini_call
        _track_task(asyncio.ensure_future(track_gemini_call(
            _dur_ms, error=True, call_type=call_type, lang=lang)))
    except Exception:
        pass


async def enrich_analysis_base(
    analysis_local: str,
    prompt: str,
    *,
    http_client: httpx.AsyncClient | None = None,  # V131.A: DEPRECATED, ignoré. Cleanup V131.D.
    lang: str = "fr",
    instructions: dict | None = None,
    call_type: str = "enrichment",
    log_prefix: str = "[META TEXTE]",
    breaker=None,
) -> dict:
    """
    Shared Gemini enrichment: call → parse → track → fallback.

    V131.A — Migration AI Studio httpx → google-genai SDK (Vertex AI). Auth ADC
    (pas de clé). `http_client` param conservé rétrocompat mais ignoré.
    `contents=str` (single-turn simple) — SDK B accepte str direct pour prompts
    sans historique multi-turn.

    Args:
        analysis_local: raw analysis text (fallback value)
        prompt: full prompt to send to Gemini (template + analysis)
        http_client: DEPRECATED V131.A — argument ignoré, cleanup V131.D
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

    # V131.A — breaker state check manuel (ex-`_breaker.call` qui wrappait httpx.post)
    if _breaker.state == _breaker.OPEN:
        logger.warning(f"{log_prefix} Circuit breaker ouvert — fallback")
        return {"analysis_enriched": analysis_local, "source": "fallback_circuit"}

    system_instruction_text = _instructions.get(lang, _instructions["fr"])
    logger.debug(f"{log_prefix} Prompt construit ({len(prompt)} chars), appel Gemini Vertex...")

    _fallback_local = {"analysis_enriched": analysis_local, "source": "hybride_local"}
    _t0 = time.monotonic()

    try:
        client = _get_client()
        config = types.GenerateContentConfig(
            system_instruction=system_instruction_text,
            temperature=0.7,
            max_output_tokens=250,
            # V131.E HOTFIX — safety_settings BLOCK_ONLY_HIGH (réduit faux positifs SAFETY)
            # Cf. docs/DIAGNOSTIC_CHATBOT_STREAMING_TRONQUE.md
            safety_settings=_V131_E_SAFETY_SETTINGS_RELAX,
            # V131.E HOTFIX — thinking_budget=0 désactive le raisonnement interne gemini-2.5-flash
            # (enrichment PDF = reformulation factuelle, pas besoin de raisonnement)
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        # V131.A — timeout strict 10s (conservé V129.1) via asyncio.wait_for :
        # SDK B n'a pas de param timeout natif sur generate_content.
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=_VERTEX_MODEL_NAME,
                contents=prompt,
                config=config,
            ),
            timeout=10.0,
        )
    except CircuitOpenError:
        # Race : state flipped entre check et appel — traiter comme circuit
        logger.warning(f"{log_prefix} Circuit breaker ouvert (race) — fallback")
        return {"analysis_enriched": analysis_local, "source": "fallback_circuit"}
    except asyncio.TimeoutError:
        logger.warning(f"{log_prefix} Timeout Gemini Vertex (10s) — fallback")
        _breaker._record_failure()
        _track_error(_t0, call_type, lang)
        return _fallback_local
    except genai_errors.ClientError as e:
        if _is_rate_limit_error(e):
            logger.warning(f"{log_prefix} Vertex 429 ResourceExhausted — fallback")
        else:
            logger.warning(f"{log_prefix} Vertex ClientError {getattr(e, 'code', '?')}: {e}")
        _breaker._record_failure()
        _track_error(_t0, call_type, lang)
        return _fallback_local
    except genai_errors.ServerError as e:
        logger.warning(f"{log_prefix} Vertex ServerError {getattr(e, 'code', '?')}: {e}")
        _breaker._record_failure()
        _track_error(_t0, call_type, lang)
        return _fallback_local
    except genai_errors.APIError as e:
        logger.error(f"{log_prefix} Vertex APIError SDK: {type(e).__name__}: {e}")
        _breaker._record_failure()
        _track_error(_t0, call_type, lang)
        return _fallback_local
    except Exception as e:
        logger.error(f"{log_prefix} Exception inattendue Vertex: {type(e).__name__}: {e}")
        _track_error(_t0, call_type, lang)
        return _fallback_local

    # Parse réponse SDK B
    _dur_ms = (time.monotonic() - _t0) * 1000
    try:
        enriched_text = (response.text or "").strip()
    except (ValueError, AttributeError):
        # SAFETY/RECITATION block : .text lève ValueError
        # SAFETY = pas un vrai succès métier, PAS de record_success
        logger.warning(f"{log_prefix} Vertex response blocked (SAFETY/RECITATION) — fallback")
        _track_error(_t0, call_type, lang)
        return _fallback_local

    # V131.A FIX — record_success dès que round-trip OK (indépendant contenu).
    # Correction Jyppy CC Max : un round-trip réussi n'est pas une failure
    # infrastructure si le contenu est vide. Sémantique préservée vs AVANT.
    _breaker._record_success()

    # Tracking usage (attribute access SDK B vs dict AI Studio)
    _usage = getattr(response, "usage_metadata", None)
    _tin = getattr(_usage, "prompt_token_count", 0) if _usage else 0
    _tout = getattr(_usage, "candidates_token_count", 0) if _usage else 0
    try:
        from services.gcp_monitoring import track_gemini_call
        _track_task(asyncio.ensure_future(track_gemini_call(
            _dur_ms, _tin, _tout, call_type=call_type, lang=lang)))
    except Exception:
        pass

    if enriched_text:
        logger.info(f"{log_prefix} Gemini Vertex OK")
        return {"analysis_enriched": enriched_text, "source": "gemini_enriched"}

    logger.warning(f"{log_prefix} Reponse Gemini vide — fallback local")
    return _fallback_local
