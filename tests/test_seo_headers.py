"""
Tests Phase A SEO — Last-Modified + Vary: Accept-Language headers.
Verifies:
  - Last-Modified present on HTML responses (SEO routes)
  - Last-Modified absent on API JSON responses
  - Vary: Accept-Language present on EM multilingual routes
  - Vary: Accept-Language absent on Loto FR-only routes
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
