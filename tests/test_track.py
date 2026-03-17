"""
Tests for universal event tracking — POST /api/track
"""

import json
import os
from unittest.mock import patch, AsyncMock

import pytest
from starlette.testclient import TestClient


_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
})

_test_ip_counter = 0


def _get_client():
    with _db_env, _static_patch, _static_call:
        import importlib
        import routes.api_track as track_mod
        importlib.reload(track_mod)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _unique_headers():
    """Return headers with unique IP to avoid rate limiting across tests."""
    global _test_ip_counter
    _test_ip_counter += 1
    return {"X-Forwarded-For": f"10.0.0.{_test_ip_counter}"}


class TestTrackEndpoint:
    """POST /api/track tests."""

    def test_valid_event_returns_204(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "chatbot-open",
                "page": "/loto",
                "module": "loto",
                "lang": "fr",
                "device": "desktop",
            }, headers=_unique_headers())
        assert resp.status_code == 204

    def test_missing_event_returns_204_no_insert(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={"page": "/loto"}, headers=_unique_headers())
        assert resp.status_code == 204
        mock_db.async_query.assert_not_called()

    def test_empty_event_returns_204_no_insert(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={"event": ""}, headers=_unique_headers())
        assert resp.status_code == 204
        mock_db.async_query.assert_not_called()

    def test_event_with_meta(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "rating-submitted",
                "meta": {"rating": 5, "module": "loto"},
            }, headers=_unique_headers())
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        assert "event_log" in call_args[0]
        assert call_args[1][0] == "rating-submitted"

    def test_owner_ip_filtered(self):
        with patch.dict(os.environ, {"OWNER_IP": "1.2.3.4"}):
            client = _get_client()
            with patch("routes.api_track.db_cloudsql") as mock_db:
                mock_db.async_query = AsyncMock(return_value=None)
                with patch("routes.api_track._is_owner_ip", return_value=True):
                    resp = client.post("/api/track", json={"event": "test"}, headers=_unique_headers())
            assert resp.status_code == 204
            mock_db.async_query.assert_not_called()

    def test_device_sanitized(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "test",
                "device": "invalid_device",
            }, headers=_unique_headers())
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        assert call_args[1][4] == "desktop"

    def test_db_error_still_returns_204(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(side_effect=Exception("db down"))
            resp = client.post("/api/track", json={"event": "test"}, headers=_unique_headers())
        assert resp.status_code == 204

    def test_session_hash_generated(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={"event": "test"}, headers=_unique_headers())
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        session_hash = call_args[1][6]
        assert len(session_hash) == 64

    def test_country_detected_from_accept_language(self):
        client = _get_client()
        h = _unique_headers()
        h["Accept-Language"] = "fr-FR,fr;q=0.9"
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={"event": "test"}, headers=h)
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        assert call_args[1][5] == "FR"

    def test_minimal_payload(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={"event": "page-view"}, headers=_unique_headers())
        assert resp.status_code == 204

    def test_event_too_long_returns_204_no_insert(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={"event": "x" * 81}, headers=_unique_headers())
        assert resp.status_code == 204
        mock_db.async_query.assert_not_called()

    def test_meta_json_stored(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "test",
                "meta": {"key": "value"},
            }, headers=_unique_headers())
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        meta = json.loads(call_args[1][7])
        assert meta["key"] == "value"

    def test_product_code_stored(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "meta75-launched",
                "module": "loto",
                "product_code": "LOTO_FR_A",
            }, headers=_unique_headers())
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        assert "product_code" in call_args[0]
        assert call_args[1][8] == "LOTO_FR_A"

    def test_product_code_none_when_missing(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "chatbot-open",
            }, headers=_unique_headers())
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        assert call_args[1][8] is None

    def test_product_code_truncated(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "test",
                "product_code": "X" * 50,
            }, headers=_unique_headers())
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        assert len(call_args[1][8]) == 20


# ═══════════════════════════════════════════════════════════════════════
# CF-IPCountry GeoIP detection (V42)
# ═══════════════════════════════════════════════════════════════════════

class TestDetectCountryCF:
    """_detect_country() with CF-IPCountry header (Cloudflare GeoIP)."""

    def test_cf_header_fr(self):
        """CF-IPCountry: FR → returns 'FR'."""
        client = _get_client()
        h = _unique_headers()
        h["CF-IPCountry"] = "FR"
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={"event": "test"}, headers=h)
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        assert call_args[1][5] == "FR"

    def test_cf_header_us(self):
        """CF-IPCountry: US → returns 'US'."""
        client = _get_client()
        h = _unique_headers()
        h["CF-IPCountry"] = "US"
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={"event": "test"}, headers=h)
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        assert call_args[1][5] == "US"

    def test_cf_xx_fallback_accept_language(self):
        """CF-IPCountry: XX (unknown) → fallback to Accept-Language."""
        client = _get_client()
        h = _unique_headers()
        h["CF-IPCountry"] = "XX"
        h["Accept-Language"] = "de-DE,de;q=0.9"
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={"event": "test"}, headers=h)
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        assert call_args[1][5] == "DE"

    def test_cf_t1_fallback_accept_language(self):
        """CF-IPCountry: T1 (Tor) → fallback to Accept-Language."""
        client = _get_client()
        h = _unique_headers()
        h["CF-IPCountry"] = "T1"
        h["Accept-Language"] = "en-GB,en;q=0.9"
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={"event": "test"}, headers=h)
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        assert call_args[1][5] == "GB"

    def test_no_cf_fallback_accept_language(self):
        """No CF-IPCountry → fallback to Accept-Language."""
        client = _get_client()
        h = _unique_headers()
        h["Accept-Language"] = "es-ES,es;q=0.9"
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={"event": "test"}, headers=h)
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        assert call_args[1][5] == "ES"

    def test_nothing_returns_unknown(self):
        """No CF-IPCountry, no Accept-Language → returns '??'."""
        client = _get_client()
        h = _unique_headers()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={"event": "test"}, headers=h)
        assert resp.status_code == 204
        call_args = mock_db.async_query.call_args[0]
        assert call_args[1][5] == "??"
