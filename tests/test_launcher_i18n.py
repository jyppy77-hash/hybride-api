"""
Tests — Launcher i18n translations (V53 Phase 2/3).
Verifies that all 5 non-FR languages have proper translations,
no FR residue in titles/H1/SEO accordion, and correct localized keywords.
"""
import os
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ── Patches ─────────────────────────────────────────────────────────────

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


def _get_title(html):
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return m.group(1).strip() if m else ""


def _get_accordion(html):
    """Extract text inside seo-accordion-content div."""
    m = re.search(r'class="seo-accordion-content">(.*?)</div>', html, re.S)
    return m.group(1).strip() if m else ""


# =========================================================================
# Title NOT in French for non-FR pages
# =========================================================================

class TestTitleNotFR:
    """Non-FR titles must not contain 'Analyse Loto et EuroMillions par IA'."""

    _FR_TITLE_FRAGMENT = "Analyse Loto et EuroMillions par IA"

    @pytest.mark.parametrize("lang", ["en", "es", "pt", "de", "nl"])
    def test_title_not_french(self, client, lang):
        resp = client.get(f"/{lang}")
        title = _get_title(resp.text)
        assert self._FR_TITLE_FRAGMENT not in title, f"/{lang} title still in French: {title}"


# =========================================================================
# Title contains expected localized keywords
# =========================================================================

class TestTitleLocalized:
    """Each language title has the right keyword."""

    @pytest.mark.parametrize("lang,keyword", [
        ("en", "Free"),
        ("es", "Gratuito"),
        ("pt", "Gratuito"),
        ("de", "Kostenlos"),
        ("nl", "Gratis"),
    ])
    def test_title_keyword(self, client, lang, keyword):
        resp = client.get(f"/{lang}")
        title = _get_title(resp.text)
        assert keyword in title, f"/{lang} title missing '{keyword}': {title}"


# =========================================================================
# H1 NOT in French for non-FR pages
# =========================================================================

class TestH1NotFR:
    """Non-FR H1 must not contain 'Analyse statistique' (the FR phrase)."""

    _FR_H1 = "Analyse statistique"

    @pytest.mark.parametrize("lang", ["en", "es", "pt", "de", "nl"])
    def test_h1_not_french(self, client, lang):
        resp = client.get(f"/{lang}")
        h1 = re.search(r"<h1.*?>(.*?)</h1>", resp.text, re.S)
        h1_text = h1.group(1) if h1 else ""
        assert self._FR_H1 not in h1_text, f"/{lang} H1 still FR"


# =========================================================================
# SEO accordion has localized content
# =========================================================================

class TestAccordionLocalized:
    """SEO accordion must contain language-specific keywords, not FR."""

    @pytest.mark.parametrize("lang,keyword", [
        ("en", "statistics"),
        ("es", "estad"),       # estadístico / estadísticas (HTML entity)
        ("pt", "estat"),       # estatística / estatísticas (HTML entity)
        ("de", "Statistik"),   # Statistiken
        ("nl", "statistiek"),  # statistieken
    ])
    def test_accordion_keyword(self, client, lang, keyword):
        resp = client.get(f"/{lang}")
        accordion = _get_accordion(resp.text)
        assert keyword.lower() in accordion.lower(), (
            f"/{lang} accordion missing '{keyword}'"
        )


# =========================================================================
# No FR residue on non-FR pages (specific FR-only phrases)
# =========================================================================

class TestNoFRResidue:
    """Non-FR pages must not contain specific FR-only phrases."""

    _FR_ONLY_PHRASES = [
        "Analyse statistique du Loto",    # FR SEO paragraph
        "tirages officiels FDJ",           # FR SEO paragraph
        "jouez avec mod",                  # FR disclaimer
    ]

    @pytest.mark.parametrize("lang", ["en", "es", "pt", "de", "nl"])
    def test_no_fr_residue(self, client, lang):
        resp = client.get(f"/{lang}")
        for phrase in self._FR_ONLY_PHRASES:
            assert phrase not in resp.text, (
                f"/{lang} contains FR phrase: '{phrase}'"
            )


# =========================================================================
# FR page still works correctly
# =========================================================================

class TestFRStillWorks:
    """Sanity: /fr still renders in French."""

    def test_fr_title(self, client):
        resp = client.get("/fr")
        title = _get_title(resp.text)
        assert "Gratuit" in title

    def test_fr_accordion(self, client):
        resp = client.get("/fr")
        accordion = _get_accordion(resp.text)
        assert "statistique" in accordion.lower()
