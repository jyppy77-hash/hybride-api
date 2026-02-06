import os
import logging
import httpx

from services.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

GEMINI_MODEL_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


async def enrich_analysis(analysis_local: str, window: str = "GLOBAL") -> dict:
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

    print(f"[DEBUG META TEXTE] GEM_API_KEY presente: {bool(gem_api_key)}")
    print(f"[DEBUG META TEXTE] GEM_API_KEY prefix: {gem_api_key[:8] if gem_api_key else 'NONE'}...")
    print(f"[DEBUG META TEXTE] Vars dispo: GEM_API_KEY={bool(os.environ.get('GEM_API_KEY'))}, GEMINI_API_KEY={bool(os.environ.get('GEMINI_API_KEY'))}")

    if not gem_api_key:
        print("[DEBUG META TEXTE] >>> SORTIE: pas de cle API — fallback local")
        logger.warning("[META TEXTE] GEM_API_KEY non configuree - fallback local")
        return {"analysis_enriched": analysis_local, "source": "hybride_local"}

    # Charger le prompt dynamique contextuel
    prompt_template = load_prompt(window_key)

    if prompt_template:
        prompt = prompt_template + "\n" + analysis_local
    else:
        prompt = f"""Tu es un expert en statistiques de loterie.
Reformule ce texte d'analyse de maniere pedagogique et accessible.
Regles strictes :
- Ne promets JAMAIS de gain
- Reste neutre et informatif
- Garde un ton professionnel
- Maximum 4 phrases fluides
- Ne modifie pas les chiffres

Texte a reformuler :
{analysis_local}"""

    print(f"[DEBUG META TEXTE] Prompt construit ({len(prompt)} chars), appel Gemini...")

    try:
        print("[DEBUG META TEXTE] >>> Ouverture httpx.AsyncClient(timeout=20.0)")
        async with httpx.AsyncClient(timeout=20.0) as client:
            print("[DEBUG META TEXTE] >>> POST vers Gemini en cours...")
            response = await client.post(
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

            print(f"[DEBUG META TEXTE] >>> Gemini HTTP status: {response.status_code}")
            print(f"[DEBUG META TEXTE] >>> Gemini response headers: {dict(response.headers)}")

            if response.status_code == 200:
                data = response.json()
                print(f"[DEBUG META TEXTE] >>> Gemini JSON keys: {list(data.keys())}")
                candidates = data.get("candidates", [])
                print(f"[DEBUG META TEXTE] >>> candidates count: {len(candidates)}")
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    print(f"[DEBUG META TEXTE] >>> parts count: {len(parts)}")
                    if parts:
                        enriched_text = parts[0].get("text", "").strip()
                        print(f"[DEBUG META TEXTE] >>> enriched_text length: {len(enriched_text)}")
                        print(f"[DEBUG META TEXTE] >>> enriched_text preview: {enriched_text[:120]}")
                        if enriched_text:
                            print("[DEBUG META TEXTE] >>> SUCCES — return gemini_enriched")
                            logger.info(f"[META TEXTE] Gemini OK (window={window_key})")
                            return {"analysis_enriched": enriched_text, "source": "gemini_enriched"}
                        else:
                            print("[DEBUG META TEXTE] >>> ECHEC: enriched_text vide apres strip")
                    else:
                        print("[DEBUG META TEXTE] >>> ECHEC: parts vide")
                else:
                    print("[DEBUG META TEXTE] >>> ECHEC: candidates vide")
            else:
                print(f"[DEBUG META TEXTE] >>> ECHEC: HTTP {response.status_code}")
                print(f"[DEBUG META TEXTE] >>> Body: {response.text[:500]}")

            logger.warning(f"[META TEXTE] Reponse Gemini invalide: {response.status_code}")
            return {"analysis_enriched": analysis_local, "source": "hybride_local"}

    except httpx.TimeoutException as te:
        print(f"[DEBUG META TEXTE] >>> EXCEPTION TimeoutException: {te}")
        logger.warning("[META TEXTE] Timeout Gemini (20s) - fallback local")
        return {"analysis_enriched": analysis_local, "source": "hybride_local"}
    except Exception as e:
        print(f"[DEBUG META TEXTE] >>> EXCEPTION {type(e).__name__}: {e}")
        import traceback
        print(f"[DEBUG META TEXTE] >>> Traceback:\n{traceback.format_exc()}")
        logger.error(f"[META TEXTE] Erreur Gemini: {e}")
        return {"analysis_enriched": analysis_local, "source": "fallback"}
