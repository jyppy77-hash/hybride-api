"""
Language configuration — Phase 11+ Multilingual
================================================
ValidLang enum + helpers for i18n support.
Active: fr (default), en (EuroMillions GB).
Registered (pages pending Phase 2+): pt, es, de, nl.
"""

from enum import Enum


class ValidLang(str, Enum):
    fr = "fr"
    en = "en"
    pt = "pt"
    es = "es"
    de = "de"
    nl = "nl"


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
    ValidLang.pt: {
        "home": "home-em-pt",
        "generator": "generator-em-pt",
        "simulator": "simulator-em-pt",
        "statistics": "statistics-em-pt",
        "history": "history-em-pt",
        "faq": "faq-em-pt",
        "news": "news-em-pt",
    },
    ValidLang.es: {
        "home": "home-em-es",
        "generator": "generator-em-es",
        "simulator": "simulator-em-es",
        "statistics": "statistics-em-es",
        "history": "history-em-es",
        "faq": "faq-em-es",
        "news": "news-em-es",
    },
    ValidLang.de: {
        "home": "home-em-de",
        "generator": "generator-em-de",
        "simulator": "simulator-em-de",
        "statistics": "statistics-em-de",
        "history": "history-em-de",
        "faq": "faq-em-de",
        "news": "news-em-de",
    },
    ValidLang.nl: {
        "home": "home-em-nl",
        "generator": "generator-em-nl",
        "simulator": "simulator-em-nl",
        "statistics": "statistics-em-nl",
        "history": "history-em-nl",
        "faq": "faq-em-nl",
        "news": "news-em-nl",
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
