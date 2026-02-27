"""
Module i18n central pour LotoIA.
Utilise gettext + Babel pour la gestion des traductions.
Langues supportées : fr, en, pt, es, de, nl
Seul EuroMillions est multilingue. Le Loto reste FR uniquement.
"""
import gettext
import os
import logging
from contextvars import ContextVar
from functools import lru_cache
from typing import Callable

logger = logging.getLogger("i18n")

# Répertoire des traductions
TRANSLATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "translations")

# Langues supportées pour l'i18n EM
SUPPORTED_LANGS = ["fr", "en", "pt", "es", "de", "nl"]

# Langue par défaut
DEFAULT_LANG = "fr"

# ContextVar pour la langue de la requête en cours (async-safe)
ctx_lang: ContextVar[str] = ContextVar("ctx_lang", default=DEFAULT_LANG)


@lru_cache(maxsize=10)
def get_translations(lang: str) -> gettext.GNUTranslations:
    """
    Charge et cache les traductions pour une langue donnée.
    Fallback sur FR si la langue n'existe pas.
    """
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG

    try:
        return gettext.translation(
            domain="messages",
            localedir=TRANSLATIONS_DIR,
            languages=[lang],
            fallback=False,
        )
    except FileNotFoundError:
        logger.warning("Failed to load translations for '%s': .mo file not found", lang)
        try:
            return gettext.translation(
                domain="messages",
                localedir=TRANSLATIONS_DIR,
                languages=[DEFAULT_LANG],
                fallback=True,
            )
        except Exception as e:
            logger.warning("Failed to load FR fallback translations: %s", e)
            return gettext.NullTranslations()
    except Exception as e:
        logger.warning("Failed to load translations for '%s': %s", lang, e)
        return gettext.NullTranslations()


def gettext_func(lang: str = DEFAULT_LANG) -> Callable[[str], str]:
    """
    Retourne la fonction _() pour une langue donnée.
    Usage : _ = gettext_func("en")
             label = _("Numéros chauds")  → "Hot Numbers"
    """
    trans = get_translations(lang)
    return trans.gettext


def ngettext_func(lang: str = DEFAULT_LANG):
    """
    Retourne la fonction ngettext() pour les pluriels.
    Usage : ng = ngettext_func("en")
             label = ng("1 tirage", "{count} tirages", count)
    """
    trans = get_translations(lang)
    return trans.ngettext


def _global(msg: str) -> str:
    """
    Fonction _() globale qui récupère la langue depuis le ContextVar.
    Utilisable PARTOUT sans passer request.
    Usage : from config.i18n import _global as _
            label = _("Numéros chauds")
    """
    lang = ctx_lang.get()
    trans = get_translations(lang)
    return trans.gettext(msg)


def get_translator(request) -> Callable[[str], str]:
    """
    Helper pour les routes FastAPI.
    Usage dans une route :
        _ = get_translator(request)
        return {"label": _("Numéros chauds")}
    """
    lang = getattr(request.state, "lang", DEFAULT_LANG)
    return gettext_func(lang)


# ═══════════════════════════════════════════════
# Badge translations (P11 compat — will migrate to gettext in Phase 2+)
# ═══════════════════════════════════════════════

def _badges(lang: str = "fr") -> dict:
    """Return badge labels for the given language."""
    if lang == "en":
        return {
            "hot": "Hot Numbers",
            "overdue": "Overdue Mix",
            "balanced": "Balanced",
            "wide_spectrum": "Wide Spectrum",
            "even_odd": "Even/Odd OK",
            "hybride_em": "Hybride V1 EM",
            "custom_em": "Custom Analysis EM",
            "custom": "Custom Analysis",
        }
    return {
        "hot": "Numéros chauds",
        "overdue": "Mix de retards",
        "balanced": "Équilibre",
        "wide_spectrum": "Large spectre",
        "even_odd": "Pair/Impair OK",
        "hybride_em": "Hybride V1 EM",
        "custom_em": "Analyse personnalisée EM",
        "custom": "Analyse personnalisée",
    }
