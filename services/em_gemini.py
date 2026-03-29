"""
Service Gemini — EuroMillions META ANALYSE
Enrichit le texte d'analyse local via Gemini avec prompts EM dedies.
Delegates to gemini_shared.enrich_analysis_base() (V71 R3c).
"""

import logging
import httpx

from services.prompt_loader import load_prompt_em, em_window_to_prompt
from services.circuit_breaker import gemini_breaker
from services.gemini_shared import enrich_analysis_base

logger = logging.getLogger(__name__)

GEMINI_MODEL_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


async def enrich_analysis_em(analysis_local: str, window: str = "GLOBAL", *, http_client: httpx.AsyncClient, lang: str = "fr") -> dict:
    """Enrichit le texte d'analyse EM via Gemini (delegates to shared base)."""
    window_key = window or "GLOBAL"
    logger.info(f"[META TEXTE EM] Fenetre={window_key}")

    # Build prompt (game-specific: EM prompt loader with lang-aware fallback)
    prompt_name = em_window_to_prompt(window_key)
    prompt_template = load_prompt_em(prompt_name, lang=lang)

    if prompt_template:
        prompt = prompt_template + "\n" + analysis_local
    elif lang == "en":
        prompt = f"""You are an expert in lottery statistics specialising in EuroMillions.
Rephrase the analysis below in a pedagogical and accessible way.
Strict rules:
- NEVER promise any winnings
- Stay neutral and informative
- Keep a professional tone
- Maximum 4 fluent sentences
- Do not alter the numbers
- Highlight balls and stars

Text to rephrase:
{analysis_local}"""
    else:
        prompt = f"""[LANGUE ET ORTHOGRAPHE — RÈGLE ABSOLUE]
Tu réponds TOUJOURS en français correct avec TOUS les accents : é, è, ê, ë, à, â, ç, ù, û, ô, î, ï.
Exemples obligatoires : "numéro" (jamais "numero"), "fréquence" (jamais "frequence"), "régularité" (jamais "regularite"), "dernière" (jamais "derniere"), "élevé" (jamais "eleve"), "intéressant" (jamais "interessant"), "présente" (jamais "presente"), "conformité" (jamais "conformite"), "éloigne" (jamais "eloigne"), "équilibre" (jamais "equilibre"), "mérite" (jamais "merite"), "peut-être" (jamais "peut-etre"), "sélection" (jamais "selection"), "mélange" (jamais "melange"), "répartition" (jamais "repartition").
C'est une règle NON NÉGOCIABLE. Un texte sans accents est considéré comme un BUG.

Tu es un expert en statistiques de loterie spécialisé dans l'EuroMillions.
Reformule ce texte d'analyse de manière pédagogique et accessible.
Règles strictes :
- Ne promets JAMAIS de gain
- Reste neutre et informatif
- Garde un ton professionnel
- Maximum 4 phrases fluides
- Ne modifie pas les chiffres
- Mets en valeur les boules et les étoiles

Texte a reformuler :
{analysis_local}"""

    return await enrich_analysis_base(
        analysis_local, prompt, http_client=http_client, lang=lang,
        call_type="enrichment_em", log_prefix="[META TEXTE EM]",
        breaker=gemini_breaker,
    )
