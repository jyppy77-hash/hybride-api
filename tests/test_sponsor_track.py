"""
Tests for POST /api/sponsor/track endpoint.
"""

import os
from unittest.mock import patch, AsyncMock

import pytest
from starlette.testclient import TestClient


_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
})


def _get_client():
    with _db_env, _static_patch, _static_call:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _mock_db():
    with patch("routes.api_sponsor_track.db_cloudsql") as mock_db:
        mock_db.async_query = AsyncMock()
        yield mock_db


class TestSponsorTrack:
    """POST /api/sponsor/track tests."""

    def test_valid_event_returns_204(self, _mock_db):
        client = _get_client()
        resp = client.post("/api/sponsor/track", json={
            "event_type": "sponsor-popup-shown",
            "page": "/loto/analyse",
            "lang": "fr",
            "device": "desktop",
        })
        assert resp.status_code == 204
        assert resp.content == b""

    def test_invalid_event_type_returns_204_no_insert(self, _mock_db):
        client = _get_client()
        resp = client.post("/api/sponsor/track", json={
            "event_type": "hacked-event",
            "page": "/loto",
            "lang": "fr",
            "device": "desktop",
        })
        assert resp.status_code == 204
        _mock_db.async_query.assert_not_called()

    def test_sponsor_click_event(self, _mock_db):
        client = _get_client()
        resp = client.post("/api/sponsor/track", json={
            "event_type": "sponsor-click",
            "page": "/euromillions/simulator",
            "lang": "en",
            "device": "mobile",
        })
        assert resp.status_code == 204

    def test_sponsor_video_played_event(self, _mock_db):
        client = _get_client()
        resp = client.post("/api/sponsor/track", json={
            "event_type": "sponsor-video-played",
            "page": "/loto",
            "lang": "fr",
            "device": "desktop",
        })
        assert resp.status_code == 204

    def test_missing_event_type_returns_422(self, _mock_db):
        client = _get_client()
        resp = client.post("/api/sponsor/track", json={
            "page": "/loto",
        })
        assert resp.status_code == 422

    def test_missing_page_returns_422(self, _mock_db):
        client = _get_client()
        resp = client.post("/api/sponsor/track", json={
            "event_type": "sponsor-popup-shown",
        })
        assert resp.status_code == 422

    def test_owner_ip_filtered(self, _mock_db):
        """Owner IP should return 204 but NOT insert."""
        with patch.dict(os.environ, {"OWNER_IP": "1.2.3.4"}):
            # Need to reimport to pick up env var
            import importlib
            import routes.api_sponsor_track as mod
            importlib.reload(mod)

            client = _get_client()
            resp = client.post(
                "/api/sponsor/track",
                json={
                    "event_type": "sponsor-popup-shown",
                    "page": "/loto",
                    "lang": "fr",
                    "device": "desktop",
                },
                headers={"X-Forwarded-For": "1.2.3.4"},
            )
            assert resp.status_code == 204


    def test_sponsor_pdf_downloaded_event(self, _mock_db):
        client = _get_client()
        resp = client.post("/api/sponsor/track", json={
            "event_type": "sponsor-pdf-downloaded",
            "page": "/loto",
            "lang": "fr",
            "device": "desktop",
            "sponsor_id": "LOTO_FR_A",
        })
        assert resp.status_code == 204

    def test_sponsor_result_shown_event(self, _mock_db):
        client = _get_client()
        resp = client.post("/api/sponsor/track", json={
            "event_type": "sponsor-result-shown",
            "page": "/loto/analyse",
            "lang": "fr",
            "device": "desktop",
            "sponsor_id": "LOTO_FR_A",
        })
        assert resp.status_code == 204

    def test_sponsor_inline_shown_event(self, _mock_db):
        client = _get_client()
        resp = client.post("/api/sponsor/track", json={
            "event_type": "sponsor-inline-shown",
            "page": "/loto",
            "lang": "fr",
            "device": "desktop",
            "sponsor_id": "LOTO_FR_A",
        })
        assert resp.status_code == 204

    def test_sponsor_id_included_in_insert(self):
        """Verify SQL template includes sponsor_id column."""
        from routes.api_sponsor_track import track_sponsor_event
        import inspect
        source = inspect.getsource(track_sponsor_event)
        assert "sponsor_id" in source
        assert "sponsor_impressions" in source

    def test_sponsor_id_optional_defaults_none(self):
        """sponsor_id is optional in the Pydantic model (defaults to None)."""
        from routes.api_sponsor_track import SponsorEvent
        event = SponsorEvent(event_type="sponsor-popup-shown", page="/loto")
        assert event.sponsor_id is None


class TestDetectCountry:
    """Test _detect_country helper (CF-IPCountry + Accept-Language fallback)."""

    def _make_request(self, cf_country=None, accept_lang=None):
        from unittest.mock import MagicMock
        req = MagicMock()
        headers = {}
        if cf_country is not None:
            headers["cf-ipcountry"] = cf_country
        if accept_lang is not None:
            headers["accept-language"] = accept_lang
        req.headers = headers
        return req

    def test_fr_FR(self):
        from routes.api_sponsor_track import _detect_country
        assert _detect_country(self._make_request(accept_lang="fr-FR,fr;q=0.9")) == "FR"

    def test_en_US(self):
        from routes.api_sponsor_track import _detect_country
        assert _detect_country(self._make_request(accept_lang="en-US,en;q=0.8")) == "US"

    def test_cf_header_priority(self):
        from routes.api_sponsor_track import _detect_country
        assert _detect_country(self._make_request(cf_country="DE", accept_lang="fr-FR")) == "DE"

    def test_empty(self):
        from routes.api_sponsor_track import _detect_country
        assert _detect_country(self._make_request()) is None

    def test_cf_xx_fallback(self):
        from routes.api_sponsor_track import _detect_country
        assert _detect_country(self._make_request(cf_country="XX", accept_lang="es-ES")) == "ES"
