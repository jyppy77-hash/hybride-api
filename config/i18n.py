"""
i18n — Badge and label translations for multilingual support.
Used by engine, services, and routes for EM badge generation.
"""


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
        "hot": "Num\u00e9ros chauds",
        "overdue": "Mix de retards",
        "balanced": "\u00c9quilibre",
        "wide_spectrum": "Large spectre",
        "even_odd": "Pair/Impair OK",
        "hybride_em": "Hybride V1 EM",
        "custom_em": "Analyse personnalis\u00e9e EM",
        "custom": "Analyse personnalis\u00e9e",
    }
