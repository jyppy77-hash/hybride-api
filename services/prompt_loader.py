import os
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

# =========================
# PROMPT MAP — Loto ONLY (EuroMillions uses file-based load_prompt_em)
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
    # Chatbot HYBRIDE — Loto
    "CHATBOT": "prompts/chatbot/prompt_hybride.txt",
    "PITCH_GRILLE": "prompts/chatbot/prompt_pitch_grille.txt",
    "SQL_GENERATOR": "prompts/chatbot/prompt_sql_generator.txt",
}

FALLBACK_PROMPT_PATH = "prompts/tirages/prompt_global.txt"


def load_prompt(window: str) -> str:
    """
    Charge le prompt contextuel correspondant a la fenetre d'analyse (Loto).
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


# =========================
# EuroMillions — file-based prompt loading with lang fallback
# =========================

@lru_cache(maxsize=128)
def load_prompt_em(name: str, lang: str = "fr") -> str:
    """
    Charge un prompt EM dans la langue demandee.
    Fallback : lang demandee -> en -> fr.

    Args:
        name: prompt file name without .txt extension
              (e.g. "prompt_hybride_em", "tirages/prompt_100")
        lang: language code (fr, en, pt, es, de, nl)

    Returns:
        Prompt text, or empty string if not found for any language.
    """
    for try_lang in _fallback_chain(lang):
        path = os.path.join(PROMPTS_DIR, "em", try_lang, f"{name}.txt")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

    logger.error(f"[PROMPT_EM] Prompt '{name}' not found for any language")
    return ""


def get_em_prompt(name: str, lang: str = "fr", **kwargs) -> str:
    """
    Charge un prompt EM et remplace les variables de maniere securisee.
    Utilise .replace() PAS .format() (danger JSON dans les prompts).

    Args:
        name: prompt file name (e.g. "prompt_sql_generator_em")
        lang: language code
        **kwargs: variables to replace (e.g. TODAY="2026-02-27")
    """
    template = load_prompt_em(name, lang)
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template


def _fallback_chain(lang: str) -> list[str]:
    """Return the language fallback chain: [lang, 'en', 'fr'] deduplicated."""
    chain = []
    for lc in [lang, "en", "fr"]:
        if lc not in chain:
            chain.append(lc)
    return chain


def em_window_to_prompt(window: str) -> str:
    """
    Convert a META analysis window key to a prompt file path (relative).

    Examples:
        "100"      -> "tirages/prompt_100"
        "GLOBAL"   -> "tirages/prompt_global"
        "1A"       -> "annees/prompt_1a"
        "GLOBAL_A" -> "annees/prompt_global"
    """
    w = (window or "GLOBAL").upper().strip()
    # Strip legacy prefixes/suffixes
    if w.startswith("EM_"):
        w = w[3:]
    if w.endswith("_EN"):
        w = w[:-3]

    # Year windows: "1A", "2A", ..., "6A"
    if len(w) >= 2 and w.endswith("A") and w[:-1].isdigit():
        return f"annees/prompt_{w.lower()}"
    # Global year window
    if w == "GLOBAL_A":
        return "annees/prompt_global"
    # Draw count windows: "100", "200", ..., "700"
    if w.isdigit():
        return f"tirages/prompt_{w}"
    # GLOBAL draws
    if w == "GLOBAL":
        return "tirages/prompt_global"
    # Unknown -> try tirages
    return f"tirages/prompt_{w.lower()}"
