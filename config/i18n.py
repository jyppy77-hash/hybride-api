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


# ═══════════════════════════════════════════════
# Analysis suggestion / comparison translations
# ═══════════════════════════════════════════════

def _analysis_strings(lang: str = "fr") -> dict:
    """Return analysis suggestion and comparison strings for the given language."""
    if lang == "en":
        return {
            # --- Severity 3 (critical) ---
            "alert_max": "Maximum alert: this grid combines ALL statistical flaws!",
            "perfect_run": "Perfect run detected! In {total} draws{suffix}, no run of {max_run} consecutive numbers has ever been drawn",
            "sum_catastrophic": "Catastrophic sum ({sum}) — real{suffix} draws range between {range}",
            "zero_above": "ZERO numbers above {mid} — statistically aberrant",
            "zero_below": "ZERO numbers below {mid} — statistically aberrant",
            "dispersion_zero": "Near-zero spread ({dispersion}) — historical average is around 30+",
            "all_even": "100% even numbers — no historical draw has this configuration",
            "all_odd": "100% odd numbers — no historical draw has this configuration",
            "conformity_collapsed": "Conformity score collapsed ({score}%) — this grid defies all statistics",
            # --- Severity 2 (warning) ---
            "run_detected": "Run of {max_run} consecutive numbers detected — very rare in real draws",
            "even_odd_imbalance": "Even/odd imbalance ({even}/{odd}) — aim for 2-3 even to match statistics",
            "low_high_imbalance": "Low/high imbalance ({low}/{high}) — mix low {low_range} and high {high_range} numbers",
            "sum_extreme": "Sum too {direction} ({sum}) — historical average is around {avg}",
            "sum_moderate": "Sum {direction} ({sum}) — aim for the {range} range",
            "dispersion_insufficient": "Insufficient spread ({dispersion}) — your numbers cover only {dispersion} out of {max} possible units",
            "dispersion_low": "Low spread ({dispersion}) — widen the gap between your numbers",
            "run_reduce": "Run of {max_run} consecutive — reduce sequential numbers",
            # --- Severity 0/1 (mild) ---
            "excellent_balance": "Excellent balance in your selection",
            "vary_even_odd": "Consider varying even and odd numbers (2-3 even is ideal)",
            "mix_low_high": "Mix low {low_range} and high {high_range} numbers",
            "sum_slightly_low": "Sum slightly low, add a higher number",
            "sum_slightly_high": "Sum slightly high, add a lower number",
            "widen_dispersion": "Slightly widen the spread of your numbers",
            "watch_run_3": "Watch out for the run of 3 consecutive numbers",
            "some_consecutive": "Some consecutive numbers — consider spacing them out",
            # --- Default ---
            "well_balanced": "Well-balanced grid",
            # --- Comparison ---
            "better_85": "Better than 85% of random grids",
            "better_60": "Better than 60% of random grids",
            "average": "Average among grids",
            "below_average": "Below average",
            # --- Direction words ---
            "dir_low": "low",
            "dir_high": "high",
        }
    return {
        # --- Severity 3 (critical) ---
        "alert_max": "Alerte maximale : cette grille cumule TOUS les défauts statistiques !",
        "perfect_run": "Suite parfaite détectée ! En {total} tirages{suffix}, aucune suite de {max_run} consécutifs n'est jamais sortie",
        "sum_catastrophic": "Somme catastrophique ({sum}) — les tirages{suffix} réels oscillent entre {range}",
        "zero_above": "ZERO numéro au-dessus de {mid} — statistiquement aberrant",
        "zero_below": "ZERO numéro en dessous de {mid} — statistiquement aberrant",
        "dispersion_zero": "Dispersion quasi nulle ({dispersion}) — la moyenne historique est autour de 30+",
        "all_even": "100% de numéros pairs — aucun tirage historique n'a cette configuration",
        "all_odd": "100% de numéros impairs — aucun tirage historique n'a cette configuration",
        "conformity_collapsed": "Score de conformité effondré ({score}%) — cette grille défie toutes les statistiques",
        # --- Severity 2 (warning) ---
        "run_detected": "Suite de {max_run} numéros consécutifs détectée — très rare dans les tirages réels",
        "even_odd_imbalance": "Déséquilibre pair/impair ({even}/{odd}) — viser 2-3 pairs pour coller aux statistiques",
        "low_high_imbalance": "Déséquilibre bas/haut ({low}/{high}) — mixer numéros bas {low_range} et hauts {high_range}",
        "sum_extreme": "Somme trop {direction} ({sum}) — la moyenne historique est autour de {avg}",
        "sum_moderate": "Somme {direction} ({sum}) — viser la fourchette {range}",
        "dispersion_insufficient": "Dispersion insuffisante ({dispersion}) — vos numéros couvrent seulement {dispersion} unités sur {max} possibles",
        "dispersion_low": "Dispersion faible ({dispersion}) — élargir l'écart entre vos numéros",
        "run_reduce": "Suite de {max_run} consécutifs — réduire les numéros qui se suivent",
        # --- Severity 0/1 (mild) ---
        "excellent_balance": "Excellent équilibre dans votre sélection",
        "vary_even_odd": "Pensez à varier pairs et impairs (2-3 pairs idéal)",
        "mix_low_high": "Mixer numéros bas {low_range} et hauts {high_range}",
        "sum_slightly_low": "Somme un peu basse, ajouter un numéro plus élevé",
        "sum_slightly_high": "Somme un peu élevée, ajouter un numéro plus bas",
        "widen_dispersion": "Élargir légèrement la dispersion de vos numéros",
        "watch_run_3": "Attention à la suite de 3 consécutifs",
        "some_consecutive": "Quelques numéros consécutifs — pensez à les espacer",
        # --- Default ---
        "well_balanced": "Grille bien équilibrée",
        # --- Comparison ---
        "better_85": "Meilleure que 85% des grilles aléatoires",
        "better_60": "Meilleure que 60% des grilles aléatoires",
        "average": "Dans la moyenne des grilles",
        "below_average": "En dessous de la moyenne",
        # --- Direction words ---
        "dir_low": "basse",
        "dir_high": "élevée",
    }
