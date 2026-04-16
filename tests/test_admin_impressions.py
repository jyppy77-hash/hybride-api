"""
Tests for admin impressions — page, API, CSV/PDF exports.
Routes: /admin/impressions, /admin/api/impressions, /admin/api/impressions/csv,
        /admin/api/sponsor-report/pdf
"""

import os
from unittest.mock import patch, AsyncMock

import pytest
from starlette.testclient import TestClient


_TEST_TOKEN = "test_admin_token_1234567890"
_TEST_PASSWORD = "test_admin_password"

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "ADMIN_TOKEN": _TEST_TOKEN,
    "ADMIN_PASSWORD": _TEST_PASSWORD,
})


def _get_client():
    with _db_env, _static_patch, _static_call:
        import importlib
        import rate_limit as rl_mod
        importlib.reload(rl_mod)
        import routes.admin_helpers as admin_helpers_mod
        importlib.reload(admin_helpers_mod)
        import routes.admin_dashboard as admin_dashboard_mod
        importlib.reload(admin_dashboard_mod)
        import routes.admin_impressions as admin_impressions_mod
        importlib.reload(admin_impressions_mod)
        import routes.admin_sponsors as admin_sponsors_mod
        importlib.reload(admin_sponsors_mod)
        import routes.admin_monitoring as admin_monitoring_mod
        importlib.reload(admin_monitoring_mod)
        import routes.admin_calendar as admin_calendar_mod
        importlib.reload(admin_calendar_mod)
        import routes.admin as admin_mod
        importlib.reload(admin_mod)
        import main as main_mod
        importlib.reload(main_mod)
        rl_mod.limiter.reset()
        rl_mod._api_hits.clear()
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _authed_client():
    client = _get_client()
    client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
    return client


# ══════════════════════════════════════════════════════════════════════════════
# Auth
# ══════════════════════════════════════════════════════════════════════════════


class TestImpressionsAuth:
    """Auth guard on impressions routes."""

    def test_page_no_auth_redirects(self):
        client = _get_client()
        resp = client.get("/admin/impressions", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_api_no_auth_returns_401(self):
        client = _get_client()
        resp = client.get("/admin/api/impressions")
        assert resp.status_code in (401, 403)

    def test_csv_no_auth_returns_401(self):
        client = _get_client()
        resp = client.get("/admin/api/impressions/csv")
        assert resp.status_code in (401, 403)

    def test_pdf_no_auth_returns_401(self):
        client = _get_client()
        resp = client.get("/admin/api/sponsor-report/pdf")
        assert resp.status_code in (401, 403)


# ══════════════════════════════════════════════════════════════════════════════
# Page
# ══════════════════════════════════════════════════════════════════════════════


class TestImpressionsPage:
    """HTML page rendering."""

    def test_page_renders_200(self):
        client = _authed_client()
        resp = client.get("/admin/impressions")
        assert resp.status_code == 200
        assert "Impressions" in resp.text


# ══════════════════════════════════════════════════════════════════════════════
# API data
# ══════════════════════════════════════════════════════════════════════════════


_SAMPLE_ROWS_KPI = [
    {"event_type": "sponsor-popup-shown", "cnt": 100, "sessions": 40},
    {"event_type": "sponsor-inline-shown", "cnt": 50, "sessions": 20},
    {"event_type": "sponsor-result-shown", "cnt": 30, "sessions": 15},
    {"event_type": "sponsor-pdf-mention", "cnt": 20, "sessions": 10},
    {"event_type": "sponsor-click", "cnt": 18, "sessions": 12},
    {"event_type": "sponsor-video-played", "cnt": 7, "sessions": 5},
    {"event_type": "sponsor-pdf-downloaded", "cnt": 3, "sessions": 2},
]


class TestImpressionsAPI:
    """GET /admin/api/impressions data tests."""

    def test_api_returns_json_structure(self):
        """Response contains kpi, by_sponsor, chart, table keys."""
        client = _authed_client()
        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(return_value={"s": 0})
            resp = client.get("/admin/api/impressions?period=24h")

        assert resp.status_code == 200
        data = resp.json()
        assert "kpi" in data
        assert "by_sponsor" in data
        assert "chart" in data
        assert "table" in data

    def test_kpi_impressions_total(self):
        """V87 F01: total impressions = popup + inline + result (not clicks)."""
        client = _authed_client()

        call_count = {"i": 0}

        async def mock_fetchall(sql, params=None):
            call_count["i"] += 1
            if call_count["i"] == 1:
                return _SAMPLE_ROWS_KPI
            return []

        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=mock_fetchall)
            mock_db.async_fetchone = AsyncMock(return_value={"s": 60})
            resp = client.get("/admin/api/impressions?period=month")

        kpi = resp.json()["kpi"]
        # V121: 4 types = 100 popup + 50 inline + 30 result + 20 pdf-mention
        assert kpi["impressions"] == 200
        assert kpi["clicks"] == 18
        assert kpi["videos"] == 7
        assert kpi["sessions"] == 60

    def test_kpi_ctr_calculation(self):
        """CTR = clicks / impressions * 100."""
        client = _authed_client()

        async def mock_fetchall(sql, params=None):
            if "GROUP BY event_type" in sql:
                return [
                    {"event_type": "sponsor-popup-shown", "cnt": 200, "sessions": 50},
                    {"event_type": "sponsor-click", "cnt": 10, "sessions": 8},
                ]
            return []

        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=mock_fetchall)
            mock_db.async_fetchone = AsyncMock(return_value={"s": 50})
            resp = client.get("/admin/api/impressions?period=24h")

        kpi = resp.json()["kpi"]
        assert kpi["ctr"] == "5.00%"

    def test_empty_period_returns_zeros(self):
        """No impressions → KPIs all zero, no crash."""
        client = _authed_client()
        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(return_value={"s": 0})
            resp = client.get("/admin/api/impressions?period=today")

        kpi = resp.json()["kpi"]
        assert kpi["impressions"] == 0
        assert kpi["clicks"] == 0
        assert kpi["videos"] == 0
        assert kpi["ctr"] == "0.00%"
        assert kpi["sessions"] == 0

    def test_by_sponsor_breakdown(self):
        """by_sponsor includes per-sponsor impressions/clicks/CTR."""
        client = _authed_client()

        call_count = {"i": 0}

        async def mock_fetchall(sql, params=None):
            call_count["i"] += 1
            if call_count["i"] == 1:
                return _SAMPLE_ROWS_KPI
            if call_count["i"] == 2:
                return [
                    {"sponsor_id": "LOTO_FR_A", "total": 120, "impressions": 100,
                     "clics": 15, "videos": 5, "sessions": 30},
                    {"sponsor_id": "LOTO_FR_B", "total": 80, "impressions": 60,
                     "clics": 3, "videos": 2, "sessions": 20},
                ]
            return []

        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=mock_fetchall)
            mock_db.async_fetchone = AsyncMock(return_value={"s": 50})
            resp = client.get("/admin/api/impressions?period=24h")

        by_sponsor = resp.json()["by_sponsor"]
        assert len(by_sponsor) == 2
        assert by_sponsor[0]["sponsor_id"] == "LOTO_FR_A"
        assert by_sponsor[0]["impressions"] == 100
        assert by_sponsor[0]["clics"] == 15
        assert by_sponsor[1]["sponsor_id"] == "LOTO_FR_B"

    def test_db_error_returns_empty_kpi(self):
        """DB exception → graceful degradation, KPIs at 0."""
        client = _authed_client()
        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=Exception("DB down"))
            mock_db.async_fetchone = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin/api/impressions?period=24h")

        assert resp.status_code == 200
        kpi = resp.json()["kpi"]
        assert kpi["impressions"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# CSV export
# ══════════════════════════════════════════════════════════════════════════════


class TestImpressionsCSV:
    """GET /admin/api/impressions/csv export tests."""

    def test_csv_content_type(self):
        """Returns text/csv with correct headers."""
        client = _authed_client()
        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/impressions/csv?period=24h")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_csv_headers_row(self):
        """CSV first row contains expected column headers."""
        client = _authed_client()
        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/impressions/csv?period=24h")

        # BOM-aware: skip potential BOM bytes
        text = resp.text.lstrip("\ufeff")
        first_line = text.strip().split("\n")[0]
        assert "date" in first_line
        assert "sponsor_id" in first_line
        assert "event_type" in first_line
        assert "count" in first_line

    def test_csv_with_data(self):
        """CSV includes data rows from mock."""
        client = _authed_client()

        from datetime import date as dt_date
        mock_rows = [
            {"day": dt_date(2026, 4, 1), "sponsor_id": "LOTO_FR_A",
             "event_type": "sponsor-popup-shown", "page": "/loto",
             "lang": "fr", "device": "desktop", "country": "FR", "cnt": 42},
        ]

        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=mock_rows)
            resp = client.get("/admin/api/impressions/csv?period=month")

        text = resp.text.lstrip("\ufeff")
        lines = text.strip().split("\n")
        assert len(lines) >= 2  # header + at least 1 data row
        assert "LOTO_FR_A" in lines[1]
        assert "42" in lines[1]


# ══════════════════════════════════════════════════════════════════════════════
# PDF export
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# V121 — Coherence tests (4 types impression alignment)
# ══════════════════════════════════════════════════════════════════════════════


# Shared fixture: 10 popup + 5 inline + 3 result + 2 pdf-mention = 20 impressions
# + 7 click + 4 video + 3 pdf-dl = 14 non-impressions. Total brut = 34.
_V121_FIXTURE = [
    {"event_type": "sponsor-popup-shown", "cnt": 10, "sessions": 5},
    {"event_type": "sponsor-inline-shown", "cnt": 5, "sessions": 3},
    {"event_type": "sponsor-result-shown", "cnt": 3, "sessions": 2},
    {"event_type": "sponsor-pdf-mention", "cnt": 2, "sessions": 1},
    {"event_type": "sponsor-click", "cnt": 7, "sessions": 4},
    {"event_type": "sponsor-video-played", "cnt": 4, "sessions": 3},
    {"event_type": "sponsor-pdf-downloaded", "cnt": 3, "sessions": 2},
]


class TestV121Coherence:
    """V121: all impression sources must agree on the same 4-type total."""

    def test_all_sources_return_same_total_on_fixture(self):
        """Dashboard total_impressions == /impressions KPI == 20 (4 types only)."""
        client = _authed_client()

        # --- Source 1: Dashboard KPIs ---
        async def dash_fetchall(sql, params=None):
            if "sponsor_impressions" in sql:
                return _V121_FIXTURE
            return []

        async def dash_fetchone(sql, params=None):
            if "ratings" in sql:
                return {"review_count": 0, "avg_rating": 0}
            return {"active": 0, "hits": 0, "cnt": 0, "s": 0}

        with patch("routes.admin_dashboard.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=dash_fetchall)
            mock_db.async_fetchone = AsyncMock(side_effect=dash_fetchone)
            dash_resp = client.get("/admin/api/dashboard-kpis?period=today")

        dash_total = dash_resp.json()["total_impressions"]

        # --- Source 2: /admin/api/impressions KPI ---
        call_count = {"i": 0}

        async def imp_fetchall(sql, params=None):
            call_count["i"] += 1
            if call_count["i"] == 1:
                return _V121_FIXTURE
            return []

        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=imp_fetchall)
            mock_db.async_fetchone = AsyncMock(return_value={"s": 10})
            imp_resp = client.get("/admin/api/impressions?period=today")

        imp_total = imp_resp.json()["kpi"]["impressions"]

        # Both must return exactly 20 (10+5+3+2)
        assert dash_total == 20, f"Dashboard total_impressions={dash_total}, expected 20"
        assert imp_total == 20, f"Impressions KPI={imp_total}, expected 20"
        assert dash_total == imp_total, "Dashboard and /impressions KPI disagree"

    def test_impressions_kpi_includes_pdf_mention(self):
        """V121: sponsor-pdf-mention is counted in KPI impressions total."""
        client = _authed_client()

        async def mock_fetchall(sql, params=None):
            if "GROUP BY event_type" in sql:
                return [
                    {"event_type": "sponsor-popup-shown", "cnt": 50, "sessions": 20},
                    {"event_type": "sponsor-pdf-mention", "cnt": 15, "sessions": 8},
                ]
            return []

        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=mock_fetchall)
            mock_db.async_fetchone = AsyncMock(return_value={"s": 25})
            resp = client.get("/admin/api/impressions?period=24h")

        kpi = resp.json()["kpi"]
        # pdf-mention must be included: 50 + 15 = 65
        assert kpi["impressions"] == 65, f"Expected 65 (50+15), got {kpi['impressions']}"

    def test_impressions_table_sponsor_includes_pdf_mention(self):
        """V121: by-sponsor 'impressions' column includes sponsor-pdf-mention."""
        client = _authed_client()

        call_count = {"i": 0}

        async def mock_fetchall(sql, params=None):
            call_count["i"] += 1
            if call_count["i"] == 1:
                return _V121_FIXTURE
            if call_count["i"] == 2:
                # by-sponsor breakdown: SQL SUM(CASE) now includes pdf-mention
                return [
                    {"sponsor_id": "LOTO_FR_A", "total": 34,
                     "impressions": 20,  # 10+5+3+2 (4 types)
                     "clics": 7, "videos": 4, "sessions": 15},
                ]
            return []

        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=mock_fetchall)
            mock_db.async_fetchone = AsyncMock(return_value={"s": 15})
            resp = client.get("/admin/api/impressions?period=24h")

        by_sponsor = resp.json()["by_sponsor"]
        assert len(by_sponsor) == 1
        # impressions column = 20 (includes pdf-mention)
        assert by_sponsor[0]["impressions"] == 20

    def test_impressions_excludes_click_video_pdfdl(self):
        """V121: click, video, pdf-downloaded are NOT counted as impressions."""
        client = _authed_client()

        async def mock_fetchall(sql, params=None):
            if "GROUP BY event_type" in sql:
                return [
                    {"event_type": "sponsor-click", "cnt": 100, "sessions": 50},
                    {"event_type": "sponsor-video-played", "cnt": 80, "sessions": 40},
                    {"event_type": "sponsor-pdf-downloaded", "cnt": 60, "sessions": 30},
                ]
            return []

        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=mock_fetchall)
            mock_db.async_fetchone = AsyncMock(return_value={"s": 80})
            resp = client.get("/admin/api/impressions?period=24h")

        kpi = resp.json()["kpi"]
        # No impression types → impressions must be 0
        assert kpi["impressions"] == 0, f"Non-impression types leaked: {kpi['impressions']}"
        assert kpi["clicks"] == 100
        assert kpi["videos"] == 80

    def test_dashboard_excludes_click_video_pdfdl_from_total(self):
        """V121: dashboard total_impressions excludes click/video/pdf-dl."""
        client = _authed_client()

        async def mock_fetchall(sql, params=None):
            if "sponsor_impressions" in sql:
                return [
                    {"event_type": "sponsor-click", "cnt": 50},
                    {"event_type": "sponsor-video-played", "cnt": 30},
                    {"event_type": "sponsor-pdf-downloaded", "cnt": 20},
                ]
            return []

        async def mock_fetchone(sql, params=None):
            if "ratings" in sql:
                return {"review_count": 0, "avg_rating": 0}
            return {"active": 0, "hits": 0, "cnt": 0}

        with patch("routes.admin_dashboard.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=mock_fetchall)
            mock_db.async_fetchone = AsyncMock(side_effect=mock_fetchone)
            resp = client.get("/admin/api/dashboard-kpis?period=today")

        data = resp.json()
        # Only non-impression types → total must be 0
        assert data["total_impressions"] == 0, f"Non-impression types in total: {data['total_impressions']}"
        assert data["clicks"] == 50
        assert data["videos"] == 30
        assert data["pdf_downloaded"] == 20


class TestImpressionsPDF:
    """GET /admin/api/sponsor-report/pdf export tests."""

    def test_pdf_content_type(self):
        """Returns application/pdf."""
        client = _authed_client()
        with patch("routes.admin_impressions.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(return_value={"s": 0})
            resp = client.get("/admin/api/sponsor-report/pdf?period=24h")

        assert resp.status_code == 200
        assert "application/pdf" in resp.headers.get("content-type", "")
        # PDF magic bytes
        assert resp.content[:4] == b"%PDF"
