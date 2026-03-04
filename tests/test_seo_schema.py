"""
Tests Phase B SEO — Schema Organization + legal.css conditionnel.
Verifies:
  - Organization schema: founder Person, foundingDate 2025, disambiguatingDescription
  - seo.py and a-propos.html alignment
  - legal.css loaded on legal pages, absent on non-legal EM pages
"""

import json
import os
from contextlib import asynccontextmanager
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ── Patches (same pattern as test_en_routes.py) ─────────────────────────

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})


def _async_cm_conn(cursor):
    @asynccontextmanager
    async def _cm():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn
    return _cm


def _get_client():
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _make_request():
    r = MagicMock()
    r.url.path = "/euromillions/a-propos"
    r.query_params = {}
    r.cookies = {}
    r.headers = {}
    return r


# ═══════════════════════════════════════════════
# 1. Schema Organization in seo.py
# ═══════════════════════════════════════════════

class TestSeoOrganizationSchema:
    """seo.py generate_jsonld_organization() output."""

    def test_founder_is_person(self):
        """founder must be a Person (not Organization)."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert '"@type": "Person"' in html

    def test_founder_name(self):
        """founder name must be Jean-Philippe Godard."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert "Jean-Philippe Godard" in html
        assert "JyppY" in html  # alternateName

    def test_founding_date_2025(self):
        """foundingDate must be 2025."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert '"foundingDate": "2025"' in html

    def test_disambiguating_description(self):
        """disambiguatingDescription must be present."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert "disambiguatingDescription" in html
        assert "literie" in html

    def test_parent_organization(self):
        """parentOrganization EmovisIA must be present."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert "EmovisIA" in html
        assert "parentOrganization" in html

    def test_same_as(self):
        """sameAs must contain emovisia.fr."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert "emovisia.fr" in html


# ═══════════════════════════════════════════════
# 2. Schema Organization in EM a-propos template
# ═══════════════════════════════════════════════

class TestEmAboutOrganizationSchema:
    """EM a-propos.html rendered Organization schema alignment."""

    def test_about_fr_has_disambiguating(self):
        """GET /euromillions/a-propos contains disambiguatingDescription."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/euromillions/a-propos")

        assert resp.status_code == 200
        assert "disambiguatingDescription" in resp.text

    def test_about_fr_founder_person(self):
        """GET /euromillions/a-propos has founder Person."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/euromillions/a-propos")

        assert "Jean-Philippe Godard" in resp.text


# ═══════════════════════════════════════════════
# 3. legal.css conditionnel
# ═══════════════════════════════════════════════

class TestLegalCssConditional:
    """legal.css only on legal pages, not on regular EM pages."""

    @pytest.mark.parametrize("path", [
        "/euromillions/mentions-legales",
        "/euromillions/confidentialite",
        "/euromillions/cookies",
        "/euromillions/avertissement",
    ])
    def test_legal_pages_have_legal_css(self, path):
        """Legal pages must load legal.css."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get(path)

        assert resp.status_code == 200
        assert "legal.css" in resp.text

    @pytest.mark.parametrize("path", [
        "/euromillions",
        "/euromillions/statistiques",
        "/euromillions/faq",
        "/euromillions/hybride",
    ])
    def test_non_legal_pages_no_legal_css(self, path):
        """Non-legal EM pages must NOT load legal.css."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get(path)

        assert resp.status_code == 200
        assert "legal.css" not in resp.text
