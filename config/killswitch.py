"""
Kill switch multilingue — controle les langues EM activees.
Par defaut : fr + en uniquement. PT/ES/DE/NL = OFF (squelettes prets).
Pour activer une langue : ajouter son code a ENABLED_LANGS.
"""

ENABLED_LANGS: list[str] = ["fr", "en", "es", "pt"]
