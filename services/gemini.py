import os
import json
import logging
import time
import asyncio
import httpx

from services.prompt_loader import load_prompt
from services.circuit_breaker import gemini_breaker, CircuitOpenError

logger = logging.getLogger(__name__)

GEMINI_MODEL_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GEMINI_STREAM_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:streamGenerateContent?alt=sse"
)


# V70 F04: i18n system instructions for enrichment (mirrors em_gemini.py pattern)
_ENRICHMENT_INSTRUCTIONS = {
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


async def enrich_analysis(analysis_local: str, window: str = "GLOBAL", *, http_client: httpx.AsyncClient, lang: str = "fr") -> dict:
    """
    Enrichit le texte d'analyse local via Gemini.
    Utilise un prompt dynamique adapte a la fenetre d'analyse.
    Timeout 20 secondes, fallback vers texte local si erreur.

    Returns:
        dict avec 'analysis_enriched' et 'source'
    """
    window_key = window or "GLOBAL"

    logger.info(f"[META TEXTE] Fenetre={window_key}")

    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")

    logger.debug(f"[META TEXTE] GEM_API_KEY presente: {bool(gem_api_key)}")
    logger.debug(f"[META TEXTE] Vars dispo: GEM_API_KEY={bool(os.environ.get('GEM_API_KEY'))}, GEMINI_API_KEY={bool(os.environ.get('GEMINI_API_KEY'))}")

    if not gem_api_key:
        logger.warning("[META TEXTE] GEM_API_KEY non configuree - fallback local")
        return {"analysis_enriched": analysis_local, "source": "hybride_local"}

    # Charger le prompt dynamique contextuel
    prompt_template = load_prompt(window_key)

    if prompt_template:
        prompt = prompt_template + "\n" + analysis_local
    else:
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

    logger.debug(f"[META TEXTE] Prompt construit ({len(prompt)} chars), appel Gemini...")

    try:
        logger.debug("[META TEXTE] POST vers Gemini en cours...")
        _t0 = time.monotonic()
        response = await gemini_breaker.call(
            http_client,
            GEMINI_MODEL_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": gem_api_key
            },
            json={
                "systemInstruction": {
                    "parts": [{
                        "text": _ENRICHMENT_INSTRUCTIONS.get(lang, _ENRICHMENT_INSTRUCTIONS["fr"])
                    }]
                },
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 250
                }
            }
        )

        logger.debug(f"[META TEXTE] Gemini HTTP status: {response.status_code}")

        _dur_ms = (time.monotonic() - _t0) * 1000
        if response.status_code == 200:
            data = response.json()
            # Track Gemini usage (tokens from usage_metadata)
            _usage = data.get("usageMetadata", {})
            _tin = _usage.get("promptTokenCount", 0)
            _tout = _usage.get("candidatesTokenCount", 0)
            try:
                from services.gcp_monitoring import track_gemini_call
                import asyncio
                asyncio.ensure_future(track_gemini_call(
                    _dur_ms, _tin, _tout, call_type="enrichment_loto", lang=lang))
            except Exception:
                pass
            candidates = data.get("candidates", [])
            logger.debug(f"[META TEXTE] candidates count: {len(candidates)}")
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    enriched_text = parts[0].get("text", "").strip()
                    logger.debug(f"[META TEXTE] enriched_text length: {len(enriched_text)}")
                    if enriched_text:
                        logger.info(f"[META TEXTE] Gemini OK (window={window_key})")
                        return {"analysis_enriched": enriched_text, "source": "gemini_enriched"}
                    else:
                        logger.warning("[META TEXTE] enriched_text vide apres strip")
                else:
                    logger.warning("[META TEXTE] parts vide dans la reponse Gemini")
            else:
                logger.warning("[META TEXTE] candidates vide dans la reponse Gemini")
        else:
            logger.warning(f"[META TEXTE] Reponse Gemini HTTP {response.status_code}: {response.text[:500]}")
            try:
                from services.gcp_monitoring import track_gemini_call
                import asyncio
                asyncio.ensure_future(track_gemini_call(
                    _dur_ms, error=True, call_type="enrichment_loto", lang=lang))
            except Exception:
                pass

        return {"analysis_enriched": analysis_local, "source": "hybride_local"}

    except CircuitOpenError:
        logger.warning("[META TEXTE] Circuit breaker ouvert — fallback local")
        return {"analysis_enriched": analysis_local, "source": "fallback_circuit"}
    except httpx.TimeoutException:
        logger.warning("[META TEXTE] Timeout Gemini (20s) - fallback local")
        return {"analysis_enriched": analysis_local, "source": "hybride_local"}
    except Exception as e:
        logger.error(f"[META TEXTE] Erreur Gemini: {e}", exc_info=True)
        return {"analysis_enriched": analysis_local, "source": "fallback"}


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
