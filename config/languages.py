"""
Language configuration — Phase 11 Multilingual
===============================================
ValidLang enum + helpers for i18n support.
Currently: fr (default), en (EuroMillions GB).
Extensible for pt/es/de/nl later.
"""

from enum import Enum


class ValidLang(str, Enum):
    fr = "fr"
    en = "en"


# Mapping lang → page slug adjustments (EN uses English slugs)
PAGE_SLUGS = {
    ValidLang.fr: {
        "home": "accueil-em",
        "generator": "euromillions",
        "simulator": "simulateur-em",
        "statistics": "statistiques-em",
        "history": "historique-em",
        "faq": "faq-em",
        "news": "news-em",
    },
    ValidLang.en: {
        "home": "home-em-en",
        "generator": "generator-em-en",
        "simulator": "simulator-em-en",
        "statistics": "statistics-em-en",
        "history": "history-em-en",
        "faq": "faq-em-en",
        "news": "news-em-en",
    },
}

# Prompt keys per language
PROMPT_KEYS = {
    ValidLang.fr: {
        "chatbot": "CHATBOT_EM",
        "pitch": "PITCH_GRILLE_EM",
        "sql": "SQL_GENERATOR_EM",
    },
    ValidLang.en: {
        "chatbot": "CHATBOT_EM_EN",
        "pitch": "PITCH_GRILLE_EM_EN",
        "sql": "SQL_GENERATOR_EM_EN",
    },
}


def get_prompt_key(lang: ValidLang, prompt_type: str) -> str:
    """Return the PROMPT_MAP key for the given lang and type."""
    return PROMPT_KEYS.get(lang, PROMPT_KEYS[ValidLang.fr])[prompt_type]
