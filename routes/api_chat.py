import os
import logging
import httpx

from fastapi import APIRouter

from schemas import HybrideChatRequest, HybrideChatResponse
from services.prompt_loader import load_prompt
from services.gemini import GEMINI_MODEL_URL

logger = logging.getLogger(__name__)

router = APIRouter()

FALLBACK_RESPONSE = (
    "\U0001f916 Je suis momentan\u00e9ment indisponible. "
    "R\u00e9essaie dans quelques secondes ou consulte la FAQ !"
)

META_KEYWORDS = ["meta", "algorithme", "moteur", "pond\u00e9ration", "ponderation"]


def _detect_mode(message: str, page: str) -> str:
    lower = message.lower()
    for kw in META_KEYWORDS:
        if kw in lower:
            return "meta"
    if page in ("simulateur", "loto", "statistiques"):
        return "analyse"
    return "decouverte"


# =========================
# HYBRIDE Chatbot — Gemini 2.0 Flash
# =========================

@router.post("/api/hybride-chat")
async def api_hybride_chat(payload: HybrideChatRequest):
    """Endpoint chatbot HYBRIDE — conversation via Gemini 2.0 Flash."""

    mode = _detect_mode(payload.message, payload.page)

    # Charger le prompt systeme
    system_prompt = load_prompt("CHATBOT")
    if not system_prompt:
        logger.error("[HYBRIDE CHAT] Prompt systeme introuvable")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )

    # Cle API
    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        logger.warning("[HYBRIDE CHAT] GEM_API_KEY non configuree — fallback")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )

    # Construire les contents (historique + message actuel)
    contents = []

    # Historique (max 20 derniers messages) + garde anti-doublon
    history = (payload.history or [])[-20:]
    if history and history[-1].role == "user" and history[-1].content == payload.message:
        history = history[:-1]

    for msg in history:
        role = "user" if msg.role == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg.content}]})

    # Message utilisateur avec contexte de page
    user_text = f"[Page: {payload.page}] {payload.message}"
    contents.append({"role": "user", "parts": [{"text": user_text}]})

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                GEMINI_MODEL_URL,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": gem_api_key,
                },
                json={
                    "system_instruction": {
                        "parts": [{"text": system_prompt}]
                    },
                    "contents": contents,
                    "generationConfig": {
                        "temperature": 0.8,
                        "maxOutputTokens": 300,
                    },
                },
            )

            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "").strip()
                        if text:
                            logger.info(
                                f"[HYBRIDE CHAT] OK (page={payload.page}, mode={mode})"
                            )
                            return HybrideChatResponse(
                                response=text, source="gemini", mode=mode
                            )

            logger.warning(
                f"[HYBRIDE CHAT] Reponse Gemini invalide: {response.status_code}"
            )
            return HybrideChatResponse(
                response=FALLBACK_RESPONSE, source="fallback", mode=mode
            )

    except httpx.TimeoutException:
        logger.warning("[HYBRIDE CHAT] Timeout Gemini (15s) — fallback")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )
    except Exception as e:
        logger.error(f"[HYBRIDE CHAT] Erreur Gemini: {e}")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )
