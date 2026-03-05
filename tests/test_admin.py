"""
Tests for admin back-office routes.
Auth, login, logout, dashboard, impressions, votes, API endpoints.
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
        import routes.admin as admin_mod
        importlib.reload(admin_mod)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _authed_client():
    client = _get_client()
    client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
    return client


class TestAdminAuth:
    """Authentication tests."""

    def test_dashboard_redirects_to_login_without_cookie(self):
        client = _get_client()
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    def test_login_page_renders(self):
        client = _get_client()
        resp = client.get("/admin/login")
        assert resp.status_code == 200
        assert "Mot de passe" in resp.text

    def test_login_wrong_password(self):
        client = _get_client()
        resp = client.post("/admin/login", data={"password": "wrong"})
        assert resp.status_code == 401
        assert "incorrect" in resp.text

    def test_login_correct_password_sets_cookie(self):
        client = _get_client()
        resp = client.post(
            "/admin/login",
            data={"password": _TEST_PASSWORD},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin" in resp.headers["location"]
        assert "lotoia_admin_token" in resp.headers.get("set-cookie", "")

    def test_dashboard_accessible_with_valid_cookie(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0, "review_count": 0, "avg_rating": 0})
            resp = client.get("/admin")
        assert resp.status_code == 200
        assert "LotoIA Admin" in resp.text

    def test_dashboard_rejects_invalid_cookie(self):
        client = _get_client()
        client.cookies.set("lotoia_admin_token", "bad_token")
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code == 302

    def test_logout_clears_cookie(self):
        client = _get_client()
        resp = client.get("/admin/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]
        set_cookie = resp.headers.get("set-cookie", "")
        assert "lotoia_admin_token" in set_cookie

    def test_login_page_redirects_if_already_authed(self):
        client = _authed_client()
        resp = client.get("/admin/login", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin" in resp.headers["location"]


class TestAdminDashboard:
    """Dashboard KPI display tests."""

    def test_dashboard_shows_kpi_values(self):
        client = _authed_client()

        async def mock_fetchone(sql, params=None):
            if "sponsor_impressions" in sql:
                return {"cnt": 42}
            if "ratings" in sql:
                return {"review_count": 10, "avg_rating": 4.5}
            return None

        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(side_effect=mock_fetchone)
            resp = client.get("/admin")

        assert resp.status_code == 200
        assert "42" in resp.text
        assert "4.5" in resp.text
        assert "10" in resp.text

    def test_dashboard_handles_db_error(self):
        client = _authed_client()

        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin")

        assert resp.status_code == 200
        assert "0" in resp.text

    def test_dashboard_has_active_nav_links(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0, "review_count": 0, "avg_rating": 0})
            resp = client.get("/admin")
        assert '/admin/impressions' in resp.text
        assert '/admin/votes' in resp.text


class TestAdminPages:
    """Impressions and votes page tests."""

    def test_impressions_page_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/impressions", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    def test_impressions_page_renders(self):
        client = _authed_client()
        resp = client.get("/admin/impressions")
        assert resp.status_code == 200
        assert "Impressions" in resp.text
        assert "chart" in resp.text.lower() or "canvas" in resp.text.lower()

    def test_votes_page_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/votes", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    def test_votes_page_renders(self):
        client = _authed_client()
        resp = client.get("/admin/votes")
        assert resp.status_code == 200
        assert "Votes" in resp.text


class TestAdminAPIImpressions:
    """API /admin/api/impressions tests."""

    def test_api_impressions_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/impressions")
        assert resp.status_code == 401

    def test_api_impressions_returns_json(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(return_value={"s": 0})
            resp = client.get("/admin/api/impressions?period=7d")

        assert resp.status_code == 200
        data = resp.json()
        assert "kpi" in data
        assert "chart" in data
        assert "table" in data
        assert "impressions" in data["kpi"]
        assert "ctr" in data["kpi"]

    def test_api_impressions_with_filters(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(return_value={"s": 0})
            resp = client.get("/admin/api/impressions?period=today&event_type=sponsor-click&lang=fr&device=mobile")

        assert resp.status_code == 200
        data = resp.json()
        assert data["kpi"]["impressions"] == 0

    def test_api_impressions_custom_period(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(return_value={"s": 0})
            resp = client.get("/admin/api/impressions?period=custom&date_start=2026-03-01&date_end=2026-03-05")

        assert resp.status_code == 200

    def test_api_impressions_invalid_filter_ignored(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(return_value={"s": 0})
            resp = client.get("/admin/api/impressions?event_type=hacked&lang=xx&device=hacked")

        assert resp.status_code == 200

    def test_api_impressions_db_error(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=Exception("DB down"))
            mock_db.async_fetchone = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin/api/impressions?period=7d")

        assert resp.status_code == 200
        data = resp.json()
        assert data["kpi"]["impressions"] == 0
        assert data["chart"] == []
        assert data["table"] == []


class TestAdminAPIVotes:
    """API /admin/api/votes tests."""

    def test_api_votes_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/votes")
        assert resp.status_code == 401

    def test_api_votes_returns_json(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"total": 5, "avg_rating": 4.2})
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/votes?period=all")

        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "distribution" in data
        assert "table" in data
        assert len(data["distribution"]) == 5

    def test_api_votes_with_source_filter(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"total": 2, "avg_rating": 5.0})
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/votes?source=chatbot_loto")

        assert resp.status_code == 200

    def test_api_votes_with_rating_filter(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"total": 1, "avg_rating": 5.0})
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/votes?rating=5")

        assert resp.status_code == 200

    def test_api_votes_invalid_source_ignored(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"total": 0, "avg_rating": 0})
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/votes?source=hacked")

        assert resp.status_code == 200

    def test_api_votes_db_error(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(side_effect=Exception("DB down"))
            mock_db.async_fetchall = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin/api/votes?period=all")

        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total"] == 0
        assert data["table"] == []


class TestPeriodHelper:
    """Test _period_to_dates helper."""

    def test_today(self):
        from routes.admin import _period_to_dates
        from datetime import date, timedelta
        ds, de = _period_to_dates("today")
        assert ds == date.today()
        assert de == date.today() + timedelta(days=1)

    def test_7d(self):
        from routes.admin import _period_to_dates
        from datetime import date, timedelta
        ds, de = _period_to_dates("7d")
        assert ds == date.today() - timedelta(days=6)

    def test_custom_valid(self):
        from routes.admin import _period_to_dates
        from datetime import date, timedelta
        ds, de = _period_to_dates("custom", "2026-01-01", "2026-01-31")
        assert ds == date(2026, 1, 1)
        assert de == date(2026, 2, 1)

    def test_custom_invalid_falls_back(self):
        from routes.admin import _period_to_dates
        from datetime import date
        ds, de = _period_to_dates("custom", "bad", "bad")
        assert ds == date.today()

    def test_all(self):
        from routes.admin import _period_to_dates
        from datetime import date
        ds, de = _period_to_dates("all")
        assert ds == date(2020, 1, 1)
