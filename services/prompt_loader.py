import os
import logging

logger = logging.getLogger(__name__)


# =========================
# PROMPT MAP — Prompts dynamiques META ANALYSE
# =========================

PROMPT_MAP = {
    "100": "prompts/tirages/prompt_100.txt",
    "200": "prompts/tirages/prompt_200.txt",
    "300": "prompts/tirages/prompt_300.txt",
    "400": "prompts/tirages/prompt_400.txt",
    "500": "prompts/tirages/prompt_500.txt",
    "600": "prompts/tirages/prompt_600.txt",
    "700": "prompts/tirages/prompt_700.txt",
    "800": "prompts/tirages/prompt_800.txt",
    "GLOBAL": "prompts/tirages/prompt_global.txt",
    "1A": "prompts/annees/prompt_1a.txt",
    "2A": "prompts/annees/prompt_2a.txt",
    "3A": "prompts/annees/prompt_3a.txt",
    "4A": "prompts/annees/prompt_4a.txt",
    "5A": "prompts/annees/prompt_5a.txt",
    "6A": "prompts/annees/prompt_6a.txt",
    # Chatbot HYBRIDE
    "CHATBOT": "prompts/chatbot/prompt_hybride.txt",
    "PITCH_GRILLE": "prompts/chatbot/prompt_pitch_grille.txt",
    "SQL_GENERATOR": "prompts/chatbot/prompt_sql_generator.txt",
    # Chatbot HYBRIDE — EuroMillions
    "CHATBOT_EM": "prompts/chatbot/prompt_hybride_em.txt",
    "PITCH_GRILLE_EM": "prompts/chatbot/prompt_pitch_grille_em.txt",
    "SQL_GENERATOR_EM": "prompts/chatbot/prompt_sql_generator_em.txt",
}

FALLBACK_PROMPT_PATH = "prompts/tirages/prompt_global.txt"


def load_prompt(window: str) -> str:
    """
    Charge le prompt contextuel correspondant a la fenetre d'analyse.
    Fallback vers prompt_global.txt si fichier absent.
    """
    key = (window or "GLOBAL").upper().strip()
    path = PROMPT_MAP.get(key, FALLBACK_PROMPT_PATH)

    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    # Fallback ultime si fichier introuvable
    if os.path.isfile(FALLBACK_PROMPT_PATH):
        logger.warning(f"[PROMPT] Fichier {path} introuvable, fallback global")
        with open(FALLBACK_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()

    logger.error("[PROMPT] Aucun fichier prompt disponible")
    return ""
