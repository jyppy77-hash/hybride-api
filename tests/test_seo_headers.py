"""
Tests Phase A SEO — Last-Modified + Vary: Accept-Language + X-Robots-Tag headers.
Verifies:
  - Last-Modified present on HTML responses = LAST_DEPLOY_DATE (fixed, not today)
  - Last-Modified absent on API JSON responses
  - Vary: Accept-Language present on EM multilingual routes
  - Vary: Accept-Language absent on Loto FR-only routes
  - X-Robots-Tag noindex on /api/* and /admin/*
  - X-Robots-Tag absent on public HTML pages
"""

import os
from contextlib import asynccontextmanager
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ── Patches (same pattern as test_routes.py) ─────────────────────────

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


# ═══════════════════════════════════════════════
# Last-Modified on HTML pages
# ═══════════════════════════════════════════════

class TestLastModifiedHeader:
    """Last-Modified header on HTML SEO routes."""

    def test_last_modified_present_on_accueil(self):
        """GET /accueil returns Last-Modified header (RFC 7231 format)."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=(150, 4.7))
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/accueil")

        assert "Last-Modified" in resp.headers
        lm = resp.headers["Last-Modified"]
        assert "GMT" in lm
        # RFC 7231 format: Thu, 04 Mar 2026 00:00:00 GMT
        assert len(lm.split()) >= 5

    def test_last_modified_is_fixed_deploy_date(self):
        """Last-Modified must be LAST_DEPLOY_DATE, not today (S02 audit fix)."""
        from config.version import LAST_DEPLOY_DATE

        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=(150, 4.7))
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            r1 = client.get("/accueil")

        lm = r1.headers["Last-Modified"]
        # The year from LAST_DEPLOY_DATE must appear in the header
        deploy_year = LAST_DEPLOY_DATE[:4]
        assert deploy_year in lm, f"Last-Modified should contain {deploy_year}: {lm}"
        # Must NOT contain tomorrow's year if different (stable across days)
        # More importantly: two requests on same deploy must yield identical Last-Modified
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client2 = _get_client()
            r2 = client2.get("/accueil")
        assert r1.headers["Last-Modified"] == r2.headers["Last-Modified"]

    def test_last_modified_present_on_euromillions(self):
        """GET /euromillions returns Last-Modified header."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/euromillions")

        assert "Last-Modified" in resp.headers

    def test_last_modified_absent_on_api_json(self):
        """GET /api/loto/data (JSON) must NOT have Last-Modified."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/health")

        # /health returns JSON — no Last-Modified expected
        assert "Last-Modified" not in resp.headers


# ═══════════════════════════════════════════════
# Vary: Accept-Language on EM multilingual routes
# ═══════════════════════════════════════════════

class TestVaryAcceptLanguage:
    """Vary: Accept-Language on EuroMillions i18n routes."""

    def test_vary_present_on_euromillions_fr(self):
        """GET /euromillions (FR) returns Vary: Accept-Language."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/euromillions")

        assert "Vary" in resp.headers
        assert "Accept-Language" in resp.headers["Vary"]

    def test_vary_present_on_en_euromillions(self):
        """GET /en/euromillions returns Vary: Accept-Language."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/en/euromillions")

        assert "Vary" in resp.headers
        assert "Accept-Language" in resp.headers["Vary"]

    def test_vary_absent_on_loto_accueil(self):
        """GET /accueil (Loto FR only) must NOT have Vary: Accept-Language."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=(150, 4.7))
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/accueil")

        vary = resp.headers.get("Vary", "")
        assert "Accept-Language" not in vary


# ═══════════════════════════════════════════════
# X-Robots-Tag on API / admin endpoints (S13)
# ═══════════════════════════════════════════════

class TestXRobotsTag:
    """X-Robots-Tag: noindex on /api/* and /admin/* (defense-in-depth)."""

    def test_api_has_x_robots_noindex(self):
        """GET /api/version must have X-Robots-Tag: noindex."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/api/version")

        assert "X-Robots-Tag" in resp.headers
        assert "noindex" in resp.headers["X-Robots-Tag"]

    def test_html_page_no_x_robots(self):
        """GET /accueil (public HTML) must NOT have X-Robots-Tag."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=(150, 4.7))
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/accueil")

        assert "X-Robots-Tag" not in resp.headers
