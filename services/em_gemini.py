"""
Service Gemini — EuroMillions META ANALYSE
Enrichit le texte d'analyse local via Gemini avec prompts EM dedies.
Equivalent EM de services/gemini.py (ZERO modification au fichier Loto).
"""

import os
import logging
import httpx

from services.prompt_loader import load_prompt_em, em_window_to_prompt
from services.circuit_breaker import gemini_breaker, CircuitOpenError

logger = logging.getLogger(__name__)

GEMINI_MODEL_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


async def enrich_analysis_em(analysis_local: str, window: str = "GLOBAL", *, http_client: httpx.AsyncClient, lang: str = "fr") -> dict:
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

    # Charger le prompt dynamique contextuel EM (lang-aware fallback)
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

    # System instruction: language-appropriate
    if lang == "en":
        system_instruction_text = (
            "MANDATORY: You ALWAYS write in correct English. "
            "Keep a professional, educational tone suitable for a PDF report. "
            "Never promise winnings. Stay neutral and factual."
        )
    elif lang == "pt":
        system_instruction_text = (
            "OBRIGATÓRIO: Escreves SEMPRE em português correto de Portugal "
            "com TODOS os acentos (á, à, â, ã, é, ê, í, ó, ô, õ, ú, ç). "
            "Mantém um tom profissional e pedagógico adequado a um relatório PDF. "
            "Nunca prometas ganhos. Mantém-te neutro e factual."
        )
    elif lang == "es":
        system_instruction_text = (
            "OBLIGATORIO: Escribes SIEMPRE en español correcto. "
            "Mantén un tono profesional y pedagógico adecuado para un informe PDF. "
            "Nunca prometas ganancias. Mantente neutro y factual."
        )
    elif lang == "de":
        system_instruction_text = (
            "PFLICHT: Du schreibst IMMER in korrektem Deutsch "
            "mit allen Umlauten (ä, ö, ü, ß). "
            "Halte einen professionellen, pädagogischen Ton, der für einen PDF-Bericht geeignet ist. "
            "Verspreche niemals Gewinne. Bleibe neutral und sachlich."
        )
    else:
        system_instruction_text = (
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
        )

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
                "systemInstruction": {
                    "parts": [{
                        "text": system_instruction_text
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
