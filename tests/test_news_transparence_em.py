"""
Tests — News transparence + lexique EM 6 langues (Release 1.6.046).

Couvre :
  - Mapping _LEXIQUE_PDF (6 langues, fichiers présents sur disque dans ui/static/)
  - Traductions gettext des chaînes clés (titre, sections, lien PDF, disclaimer)
    dans les 5 langues — pas de fallback FR (règle ZÉRO string FR visible)
  - Rendu de la page news EM par langue : bon PDF lié + titre traduit + titre FR absent
"""
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ── Patches (same pattern as test_launcher_seo.py) ──────────────────────

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})


def _get_client():
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def client():
    return _get_client()


UI_STATIC = Path(__file__).resolve().parent.parent / "ui" / "static"

_TITLE_FR = (
    "LotoIA renforce sa transparence : nouveaux outils d'analyse "
    "et lexique pédagogique"
)
# Fragment sans apostrophe pour les assertions sur le HTML rendu : Jinja2
# autoescape transforme ' en &#39;, donc _TITLE_FR ne matche jamais tel quel.
_TITLE_FR_MARKER = "renforce sa transparence"

_TITLE_BY_LANG = {
    "en": "LotoIA strengthens its transparency: new analysis tools and an educational glossary",
    "es": "LotoIA refuerza su transparencia: nuevas herramientas de análisis y glosario pedagógico",
    "pt": "A LotoIA reforça a sua transparência: novas ferramentas de análise e glossário pedagógico",
    "de": "LotoIA stärkt seine Transparenz: neue Analysewerkzeuge und ein pädagogisches Glossar",
    "nl": "LotoIA versterkt zijn transparantie: nieuwe analysetools en een educatief glossarium",
}

_LINK_LABEL_FR = "Consulter le lexique LotoIA (PDF)"
_LINK_LABEL_BY_LANG = {
    "en": "Consult the LotoIA glossary (PDF)",
    "es": "Consultar el glosario LotoIA (PDF)",
    "pt": "Consultar o glossário LotoIA (PDF)",
    "de": "Das LotoIA-Glossar einsehen (PDF)",
    "nl": "Raadpleeg het LotoIA-glossarium (PDF)",
}

_H3_STRINGS = {
    "Comprendre, pas prédire": {
        "en": "Understanding, not predicting",
        "es": "Comprender, no predecir",
        "pt": "Compreender, não prever",
        "de": "Verstehen, nicht vorhersagen",
        "nl": "Begrijpen, niet voorspellen",
    },
    "Un lexique pour tout comprendre": {
        "en": "A glossary to understand it all",
        "es": "Un glosario para entenderlo todo",
        "pt": "Um glossário para compreender tudo",
        "de": "Ein Glossar, um alles zu verstehen",
        "nl": "Een glossarium om alles te begrijpen",
    },
    "Des outils d'analyse renforcés": {
        "en": "Strengthened analysis tools",
        "es": "Herramientas de análisis reforzadas",
        "pt": "Ferramentas de análise reforçadas",
        "de": "Verstärkte Analysewerkzeuge",
        "nl": "Versterkte analysetools",
    },
    "Rappel — jeu responsable": {
        "en": "Reminder — responsible gambling",
        "es": "Recordatorio — juego responsable",
        "pt": "Lembrete — jogo responsável",
        "de": "Erinnerung — verantwortungsvolles Spielen",
        "nl": "Herinnering — verantwoord spelen",
    },
}

_DISCLAIMER_FR = (
    "LotoIA est un outil d'analyse statistique à vocation pédagogique. "
    "Il ne constitue en aucun cas une prédiction, une probabilité de gain "
    "ou un avantage sur le tirage. Le hasard d'un tirage de loterie est "
    "irréductible."
)


# =========================================================================
# 1. Mapping _LEXIQUE_PDF
# =========================================================================

class TestLexiquePdfMapping:
    """Mapping langue → fichier PDF lexique/glossaire."""

    def test_mapping_covers_all_supported_langs(self):
        from config.i18n import SUPPORTED_LANGS
        from config.templates import _LEXIQUE_PDF
        assert sorted(_LEXIQUE_PDF) == sorted(SUPPORTED_LANGS)

    def test_mapped_files_exist_in_ui_static(self):
        from config.templates import _LEXIQUE_PDF
        for lang, filename in _LEXIQUE_PDF.items():
            path = UI_STATIC / filename
            assert path.is_file(), f"{lang}: {path} manquant"
            assert path.stat().st_size > 10_000, f"{lang}: {path} suspect (taille)"

    def test_filenames_are_language_specific(self):
        """Noms localisés distincts (pas un f-string lexique-{lang})."""
        from config.templates import _LEXIQUE_PDF
        assert _LEXIQUE_PDF["fr"] == "lexique-lotoia-fr.pdf"
        assert _LEXIQUE_PDF["en"] == "glossary-lotoia-en.pdf"
        assert _LEXIQUE_PDF["nl"] == "glossarium-lotoia-nl.pdf"
        assert len(set(_LEXIQUE_PDF.values())) == 6


# =========================================================================
# 2. Traductions gettext — ZÉRO fallback FR
# =========================================================================

class TestTranslationsNotFrench:
    """Les chaînes clés de l'article sont traduites (pas de fallback msgid FR)."""

    @pytest.mark.parametrize("lang", ["en", "es", "pt", "de", "nl"])
    def test_title_translated(self, lang):
        from config.i18n import gettext_func
        _ = gettext_func(lang)
        assert _(_TITLE_FR) == _TITLE_BY_LANG[lang]

    @pytest.mark.parametrize("lang", ["en", "es", "pt", "de", "nl"])
    def test_link_label_translated(self, lang):
        from config.i18n import gettext_func
        _ = gettext_func(lang)
        assert _(_LINK_LABEL_FR) == _LINK_LABEL_BY_LANG[lang]

    @pytest.mark.parametrize("msgid,expected", list(_H3_STRINGS.items()))
    def test_section_headings_translated(self, msgid, expected):
        from config.i18n import gettext_func
        for lang, expected_str in expected.items():
            _ = gettext_func(lang)
            assert _(msgid) == expected_str, f"{lang}: '{msgid}' non traduit"

    @pytest.mark.parametrize("lang", ["en", "es", "pt", "de", "nl"])
    def test_disclaimer_translated(self, lang):
        from config.i18n import gettext_func
        _ = gettext_func(lang)
        result = _(_DISCLAIMER_FR)
        assert result != _DISCLAIMER_FR, f"{lang}: disclaimer en fallback FR"
        assert "LotoIA" in result


# =========================================================================
# 3. Rendu page news EM par langue
# =========================================================================

class TestNewsRenderPerLang:
    """La page news EM lie le PDF de SA langue et n'affiche pas le titre FR."""

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_news_page_links_own_pdf(self, client, lang):
        from config.templates import EM_URLS, _LEXIQUE_PDF
        resp = client.get(EM_URLS[lang]["news"])
        assert resp.status_code == 200
        assert f"/ui/static/{_LEXIQUE_PDF[lang]}" in resp.text
        # Aucun PDF d'une autre langue ne doit fuiter
        others = {f for lc, f in _LEXIQUE_PDF.items() if lc != lang}
        for other in others:
            assert other not in resp.text, f"{lang}: lien PDF {other} inattendu"

    @pytest.mark.parametrize("lang", ["en", "es", "pt", "de", "nl"])
    def test_news_page_title_not_french(self, client, lang):
        from config.templates import EM_URLS
        resp = client.get(EM_URLS[lang]["news"])
        assert resp.status_code == 200
        assert _TITLE_FR_MARKER not in resp.text, f"{lang}: titre FR visible"
        assert _TITLE_BY_LANG[lang] in resp.text

    def test_news_page_fr_shows_french_title(self, client):
        from config.templates import EM_URLS
        resp = client.get(EM_URLS["fr"]["news"])
        assert resp.status_code == 200
        assert _TITLE_FR_MARKER in resp.text

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_news_page_single_featured(self, client, lang):
        from config.templates import EM_URLS
        resp = client.get(EM_URLS[lang]["news"])
        assert resp.text.count("news-post featured") == 1
