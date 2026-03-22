"""
Tests — Launcher multilingue (V53 Phase 1/3).
24 tests: redirect CF-IPCountry + pages /{lang} + contenu + drapeaux.
"""
import os
import re
from unittest.mock import patch, AsyncMock
from contextlib import asynccontextmanager

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


# =========================================================================
# Redirect GET / → 302 based on CF-IPCountry
# =========================================================================

class TestLauncherRedirect:
    """GET / redirects to /{lang} based on CF-IPCountry header."""

    @pytest.mark.parametrize("country,expected_lang", [
        ("FR", "fr"),
        ("ES", "es"),
        ("BR", "pt"),
        ("DE", "de"),
        ("NL", "nl"),
        ("US", "en"),
        ("GB", "en"),
        ("JP", "en"),   # non-mapped → fallback EN
        ("AT", "de"),
        ("AR", "es"),
        ("BE", "fr"),
        ("CH", "fr"),
    ])
    def test_redirect_country(self, client, country, expected_lang):
        resp = client.get("/", headers={"cf-ipcountry": country}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == f"/{expected_lang}"

    def test_redirect_no_header(self, client):
        """No CF-IPCountry header → fallback to /en."""
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/en"


# =========================================================================
# Pages GET /{lang} → 200 + Content-Language + html lang
# =========================================================================

class TestLauncherPages:
    """GET /{lang} serves launcher in fixed language."""

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_page_status_and_headers(self, client, lang):
        resp = client.get(f"/{lang}")
        assert resp.status_code == 200
        assert resp.headers.get("content-language") == lang
        assert f'lang="{lang}"' in resp.text


# =========================================================================
# Content order: Loto/EM position
# =========================================================================

class TestLauncherContentOrder:
    """FR = Loto first, others = EuroMillions first (within engine cards)."""

    _LOTO_MARKER = 'class="engine-name">Loto France'
    _EM_MARKER = 'class="engine-name">EuroMillions'

    def test_fr_loto_before_em(self, client):
        resp = client.get("/fr")
        loto_pos = resp.text.index(self._LOTO_MARKER)
        em_pos = resp.text.index(self._EM_MARKER)
        assert loto_pos < em_pos

    def test_en_em_before_loto(self, client):
        resp = client.get("/en")
        loto_pos = resp.text.index(self._LOTO_MARKER)
        em_pos = resp.text.index(self._EM_MARKER)
        assert em_pos < loto_pos

    def test_es_em_before_loto(self, client):
        resp = client.get("/es")
        loto_pos = resp.text.index(self._LOTO_MARKER)
        em_pos = resp.text.index(self._EM_MARKER)
        assert em_pos < loto_pos


# =========================================================================
# Flags (language selector)
# =========================================================================

class TestLauncherFlags:
    """6 language flags present with active state."""

    def test_all_flags_present(self, client):
        resp = client.get("/fr")
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            assert f'href="/{lang}"' in resp.text

    def test_active_flag_fr(self, client):
        resp = client.get("/fr")
        assert re.search(r'href="/fr"\s+class="flag-link active"', resp.text)

    def test_active_flag_en(self, client):
        resp = client.get("/en")
        assert re.search(r'href="/en"\s+class="flag-link active"', resp.text)


# =========================================================================
# Links (Loto → /accueil, EM → localized)
# =========================================================================

class TestLauncherLinks:
    """Loto always links to /accueil, EM links to localized URL."""

    def test_loto_link(self, client):
        resp = client.get("/en")
        assert 'href="/accueil"' in resp.text

    def test_em_link_fr(self, client):
        resp = client.get("/fr")
        assert 'href="/euromillions"' in resp.text

    def test_em_link_en(self, client):
        resp = client.get("/en")
        assert 'href="/en/euromillions"' in resp.text

    def test_em_link_es(self, client):
        resp = client.get("/es")
        assert 'href="/es/euromillions"' in resp.text


# =========================================================================
# Accept-Language fallback (no CF-IPCountry)
# =========================================================================

class TestAcceptLanguageFallback:
    """When CF-IPCountry is absent, Accept-Language determines the redirect."""

    @pytest.mark.parametrize("accept_lang,expected", [
        ("fr-FR,fr;q=0.9,en;q=0.8", "fr"),
        ("de-DE,de;q=0.9,en;q=0.8", "de"),
        ("es-AR,es;q=0.9,en;q=0.8", "es"),
        ("pt-BR,pt;q=0.9", "pt"),
        ("nl-NL,nl;q=0.9", "nl"),
        ("zh-CN,zh;q=0.9,en;q=0.8", "en"),  # zh unsupported, fallback to en
        ("ja", "en"),                          # ja unsupported, no en → fallback
        ("", "en"),                            # empty → fallback
    ])
    def test_accept_language_redirect(self, client, accept_lang, expected):
        resp = client.get("/", headers={"accept-language": accept_lang}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == f"/{expected}"

    def test_no_headers_at_all(self, client):
        """No CF-IPCountry, no Accept-Language → fallback /en."""
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/en"


# =========================================================================
# CF-IPCountry takes priority over Accept-Language
# =========================================================================

class TestCFPriorityOverAcceptLang:
    """CF-IPCountry wins when both headers are present."""

    def test_cf_de_beats_accept_fr(self, client):
        resp = client.get("/", headers={
            "cf-ipcountry": "DE",
            "accept-language": "fr-FR,fr;q=0.9",
        }, follow_redirects=False)
        assert resp.headers["location"] == "/de"

    def test_cf_es_beats_accept_en(self, client):
        resp = client.get("/", headers={
            "cf-ipcountry": "ES",
            "accept-language": "en-US,en;q=0.9",
        }, follow_redirects=False)
        assert resp.headers["location"] == "/es"
