"""
Tests for admin back-office routes.
Auth, login, logout, dashboard.
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
        client = _get_client()
        client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0, "review_count": 0, "avg_rating": 0})
            resp = client.get("/admin")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text or "Back-office" in resp.text

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
        client = _get_client()
        client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
        resp = client.get("/admin/login", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin" in resp.headers["location"]


class TestAdminDashboard:
    """Dashboard KPI display tests."""

    def test_dashboard_shows_kpi_values(self):
        client = _get_client()
        client.cookies.set("lotoia_admin_token", _TEST_TOKEN)

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
        client = _get_client()
        client.cookies.set("lotoia_admin_token", _TEST_TOKEN)

        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin")

        assert resp.status_code == 200
        assert "0" in resp.text
