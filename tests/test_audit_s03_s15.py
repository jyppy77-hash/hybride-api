"""
Tests for audit fixes S03, S04, S05, S07, S08, S10, S11, S13, S15.
"""

import glob
import json
import os
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
from starlette.testclient import TestClient


_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
})

_test_ip_counter = 200


def _get_client():
    with _db_env, _static_patch, _static_call:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _unique_headers():
    global _test_ip_counter
    _test_ip_counter += 1
    return {"X-Forwarded-For": f"10.99.0.{_test_ip_counter}"}


# ══════════════════════════════════════════════════════════════════════════════
# S03 — Umami cleanup verification
# ══════════════════════════════════════════════════════════════════════════════

class TestS03UmamiRemoval:
    """Verify all umami references are removed from JS and HTML files."""

    ROOT = Path(__file__).resolve().parent.parent / "ui"

    def test_no_umami_in_js_files(self):
        """No JS file under ui/static/ should contain 'umami'."""
        static_dir = self.ROOT / "static"
        for js_file in static_dir.rglob("*.js"):
            content = js_file.read_text(encoding="utf-8", errors="ignore")
            assert "umami" not in content.lower(), f"umami found in {js_file}"

    def test_no_umami_in_html_files(self):
        """No HTML file under ui/ should contain 'umami'."""
        for html_file in self.ROOT.rglob("*.html"):
            # Skip admin templates (never had umami)
            if "admin" in str(html_file):
                continue
            content = html_file.read_text(encoding="utf-8", errors="ignore")
            assert "umami" not in content.lower(), f"umami found in {html_file}"

    def test_analytics_js_no_umami_config(self):
        """analytics.js should not have umami provider config."""
        analytics = self.ROOT / "static" / "analytics.js"
        content = analytics.read_text(encoding="utf-8")
        assert "umami" not in content, "umami config still present in analytics.js"


# ══════════════════════════════════════════════════════════════════════════════
# S04 — Sponsor events accepted by /api/track (LotoIA_track mirror)
# ══════════════════════════════════════════════════════════════════════════════

class TestS04SponsorEventsInTrack:
    """Verify /api/track accepts sponsor event types with sponsor_id and product_code."""

    def test_sponsor_popup_shown_accepted(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "sponsor-popup-shown",
                "page": "/loto",
                "meta": {"sponsor_id": "LOTO_FR_A", "product_code": "LOTO_FR_A"},
            }, headers=_unique_headers())
            assert resp.status_code == 204
            mock_db.async_query.assert_called_once()

    def test_sponsor_click_accepted(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "sponsor-click",
                "page": "/loto",
                "meta": {"sponsor_id": "LOTO_FR_B", "product_code": "LOTO_FR_B"},
            }, headers=_unique_headers())
            assert resp.status_code == 204
            mock_db.async_query.assert_called_once()

    def test_sponsor_inline_shown_accepted(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "sponsor-inline-shown",
                "page": "/loto",
                "meta": {"sponsor_id": "EM_FR_A", "product_code": "EM_FR_A"},
            }, headers=_unique_headers())
            assert resp.status_code == 204
            mock_db.async_query.assert_called_once()

    def test_sponsor_video_played_accepted(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "sponsor-video-played",
                "page": "/loto",
                "meta": {"sponsor_id": "LOTO_FR_A", "product_code": "LOTO_FR_A"},
            }, headers=_unique_headers())
            assert resp.status_code == 204

    def test_sponsor_result_shown_accepted(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "sponsor-result-shown",
                "page": "/simulateur",
                "meta": {"sponsor_id": "LOTO_FR_A", "product_code": "LOTO_FR_A"},
            }, headers=_unique_headers())
            assert resp.status_code == 204

    def test_sponsor_pdf_downloaded_accepted(self):
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "sponsor-pdf-downloaded",
                "page": "/loto/meta75",
                "meta": {"sponsor_id": "LOTO_FR_A", "product_code": "LOTO_FR_A"},
            }, headers=_unique_headers())
            assert resp.status_code == 204

    def test_product_code_stored_from_meta(self):
        """product_code from meta should be stored in event_log."""
        client = _get_client()
        with patch("routes.api_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/api/track", json={
                "event": "sponsor-popup-shown",
                "page": "/loto",
                "product_code": "LOTO_FR_A",
                "meta": {"sponsor_id": "LOTO_FR_A"},
            }, headers=_unique_headers())
            assert resp.status_code == 204
            call_args = mock_db.async_query.call_args
            params = call_args[0][1]
            # product_code should be in the INSERT params
            assert any("LOTO_FR_A" in str(p) for p in params)


# ══════════════════════════════════════════════════════════════════════════════
# S05 — sponsors.json tarif fields removed
# ══════════════════════════════════════════════════════════════════════════════

class TestS05SponsorJsonNoTarifs:
    """Verify sponsors.json no longer contains tarif-related fields."""

    def test_no_tarif_fields_in_sponsors_json(self):
        json_path = Path(__file__).resolve().parent.parent / "config" / "sponsors.json"
        data = json.loads(json_path.read_text(encoding="utf-8"))
        for group_name, group in data.get("slots", {}).items():
            for slot_name, slot in group.items():
                if not isinstance(slot, dict):
                    continue
                assert "tarif_mensuel" not in slot, f"{group_name}.{slot_name} still has tarif_mensuel"
                assert "cpc" not in slot, f"{group_name}.{slot_name} still has cpc"
                assert "cpm" not in slot, f"{group_name}.{slot_name} still has cpm"
                assert "impressions_incluses" not in slot, f"{group_name}.{slot_name} still has impressions_incluses"

    def test_required_fields_still_present(self):
        """Verify essential fields (id, name, tagline, url, active) are preserved."""
        json_path = Path(__file__).resolve().parent.parent / "config" / "sponsors.json"
        data = json.loads(json_path.read_text(encoding="utf-8"))
        for group_name, group in data.get("slots", {}).items():
            for slot_name, slot in group.items():
                if not isinstance(slot, dict):
                    continue
                assert "id" in slot, f"{group_name}.{slot_name} missing id"
                assert "name" in slot, f"{group_name}.{slot_name} missing name"
                assert "tagline" in slot, f"{group_name}.{slot_name} missing tagline"
                assert "url" in slot, f"{group_name}.{slot_name} missing url"
                assert "active" in slot, f"{group_name}.{slot_name} missing active"


# ══════════════════════════════════════════════════════════════════════════════
# S07 — Orphan api_tracking.py removed
# ══════════════════════════════════════════════════════════════════════════════

class TestS07OrphanRouteRemoved:
    """Verify api_tracking.py is deleted and routes are gone."""

    def test_api_tracking_file_deleted(self):
        path = Path(__file__).resolve().parent.parent / "routes" / "api_tracking.py"
        assert not path.exists(), "routes/api_tracking.py should be deleted"

    def test_track_grid_returns_404(self):
        client = _get_client()
        resp = client.post("/api/track-grid", json={"grid_id": "test"})
        assert resp.status_code in (404, 405)

    def test_track_ad_impression_returns_404(self):
        client = _get_client()
        resp = client.post("/api/track-ad-impression", json={"ad_id": "test"})
        assert resp.status_code in (404, 405)

    def test_track_ad_click_returns_404(self):
        client = _get_client()
        resp = client.post("/api/track-ad-click", json={"ad_id": "test"})
        assert resp.status_code in (404, 405)

    def test_no_orphan_schemas(self):
        """TrackGridPayload, TrackAdImpressionPayload, TrackAdClickPayload should be removed."""
        schemas_path = Path(__file__).resolve().parent.parent / "schemas.py"
        content = schemas_path.read_text(encoding="utf-8")
        assert "TrackGridPayload" not in content
        assert "TrackAdImpressionPayload" not in content
        assert "TrackAdClickPayload" not in content


# ══════════════════════════════════════════════════════════════════════════════
# S10 — Sponsor ID integrity validation
# ══════════════════════════════════════════════════════════════════════════════

class TestS10SponsorIdValidation:
    """Verify unknown sponsor_id is rejected by /api/sponsor/track."""

    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch("routes.api_sponsor_track.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            self.mock_db = mock_db
            yield

    def test_valid_sponsor_id_accepted(self):
        client = _get_client()
        resp = client.post("/api/sponsor/track", json={
            "event_type": "sponsor-popup-shown",
            "page": "/loto",
            "sponsor_id": "LOTO_FR_A",
        }, headers=_unique_headers())
        assert resp.status_code == 204
        self.mock_db.async_query.assert_called_once()

    def test_unknown_sponsor_id_rejected(self):
        client = _get_client()
        resp = client.post("/api/sponsor/track", json={
            "event_type": "sponsor-popup-shown",
            "page": "/loto",
            "sponsor_id": "HACKED_SPONSOR_XYZ",
        }, headers=_unique_headers())
        assert resp.status_code == 204
        self.mock_db.async_query.assert_not_called()

    def test_null_sponsor_id_accepted(self):
        """Events without sponsor_id (null) should still be accepted."""
        client = _get_client()
        resp = client.post("/api/sponsor/track", json={
            "event_type": "sponsor-popup-shown",
            "page": "/loto",
        }, headers=_unique_headers())
        assert resp.status_code == 204
        self.mock_db.async_query.assert_called_once()


# S11/S15 — Migration files are gitignored (local-only).
# Existence tests removed — migrations validated at deploy time.


# ══════════════════════════════════════════════════════════════════════════════
# S13 — Admin CSS responsive
# ══════════════════════════════════════════════════════════════════════════════

class TestS13ResponsiveCSS:
    """Verify responsive rules in admin.css."""

    def test_admin_css_has_mobile_media_query(self):
        css_path = Path(__file__).resolve().parent.parent / "ui" / "static" / "admin.css"
        content = css_path.read_text(encoding="utf-8")
        assert "@media (max-width: 768px)" in content

    def test_admin_css_has_table_scroll(self):
        css_path = Path(__file__).resolve().parent.parent / "ui" / "static" / "admin.css"
        content = css_path.read_text(encoding="utf-8")
        assert "overflow-x: auto" in content
