"""
Service Gemini — EuroMillions META ANALYSE
Enrichit le texte d'analyse local via Gemini avec prompts EM dedies.
Equivalent EM de services/gemini.py (ZERO modification au fichier Loto).
"""

import os
import logging
import httpx

from services.prompt_loader import load_prompt_em
from services.circuit_breaker import gemini_breaker, CircuitOpenError

logger = logging.getLogger(__name__)

GEMINI_MODEL_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


async def enrich_analysis_em(analysis_local: str, window: str = "GLOBAL", *, http_client: httpx.AsyncClient) -> dict:
    """
    Enrichit le texte d'analyse local EuroMillions via Gemini.
    Utilise un prompt dynamique EM adapte a la fenetre d'analyse.
    Timeout 20 secondes, fallback vers texte local si erreur.

    Returns:
        dict avec 'analysis_enriched' et 'source'
    """
    window_key = window or "GLOBAL"

    logger.info(f"[META TEXTE EM] Fenetre={window_key}")

    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if not gem_api_key:
        logger.warning("[META TEXTE EM] GEM_API_KEY non configuree - fallback local")
        return {"analysis_enriched": analysis_local, "source": "hybride_local"}

    # Charger le prompt dynamique contextuel EM
    prompt_template = load_prompt_em(window_key)

    if prompt_template:
        prompt = prompt_template + "\n" + analysis_local
    else:
        prompt = f"""Tu es un expert en statistiques de loterie specialise dans l'EuroMillions.
Reformule ce texte d'analyse de maniere pedagogique et accessible.
Regles strictes :
- Ne promets JAMAIS de gain
- Reste neutre et informatif
- Garde un ton professionnel
- Maximum 4 phrases fluides
- Ne modifie pas les chiffres
- Mets en valeur les boules et les etoiles

Texte a reformuler :
{analysis_local}"""

    logger.debug(f"[META TEXTE EM] Prompt construit ({len(prompt)} chars), appel Gemini...")

    try:
        response = await gemini_breaker.call(
            http_client,
            GEMINI_MODEL_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": gem_api_key
            },
            json={
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 250
                }
            }
        )

        if response.status_code == 200:
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    enriched_text = parts[0].get("text", "").strip()
                    if enriched_text:
                        logger.info(f"[META TEXTE EM] Gemini OK (window={window_key})")
                        return {"analysis_enriched": enriched_text, "source": "gemini_enriched"}

        logger.warning(f"[META TEXTE EM] Reponse Gemini incomplete — fallback local")
        return {"analysis_enriched": analysis_local, "source": "hybride_local"}

    except CircuitOpenError:
        logger.warning("[META TEXTE EM] Circuit breaker ouvert — fallback local")
        return {"analysis_enriched": analysis_local, "source": "fallback_circuit"}
    except httpx.TimeoutException:
        logger.warning("[META TEXTE EM] Timeout Gemini (20s) - fallback local")
        return {"analysis_enriched": analysis_local, "source": "hybride_local"}
    except Exception as e:
        logger.error(f"[META TEXTE EM] Erreur Gemini: {e}", exc_info=True)
        return {"analysis_enriched": analysis_local, "source": "fallback"}
