"""
Tests — Admin audit logging (M4 fix).
Verifies that sensitive admin actions emit structured [ADMIN_AUDIT] log entries.
Uses capsys to capture stdout since the JSON logger writes to stdout, not caplog.
"""

import logging
import os
from unittest.mock import patch, AsyncMock

import pytest
from starlette.testclient import TestClient


_TEST_TOKEN = "test_admin_token_audit"
_TEST_PASSWORD = "test_admin_password_audit"

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


class TestAdminAuditBan:
    """Verify [ADMIN_AUDIT] log on ban/unban actions."""

    def test_ban_ip_logs_audit(self, capsys):
        client = _authed_client()
        with patch("routes.admin_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            resp = client.post(
                "/admin/api/ban",
                json={"ip": "1.2.3.4", "reason": "test ban"},
            )
        assert resp.status_code == 200
        captured = capsys.readouterr().out
        assert "ADMIN_AUDIT" in captured
        assert "action=ban_ip" in captured
        assert "target=1.2.3.4" in captured

    def test_unban_ip_logs_audit(self, capsys):
        client = _authed_client()
        with patch("routes.admin_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            resp = client.post(
                "/admin/api/unban",
                json={"ip": "1.2.3.4"},
            )
        assert resp.status_code == 200
        captured = capsys.readouterr().out
        assert "ADMIN_AUDIT" in captured
        assert "action=unban_ip" in captured


class TestAdminAuditSponsor:
    """Verify [ADMIN_AUDIT] log on sponsor create."""

    def test_sponsor_create_logs_audit(self, capsys):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            mock_db.async_fetchone = AsyncMock(return_value={"id": 42})
            resp = client.post(
                "/admin/sponsors/new",
                data={"nom": "TestSponsor", "actif": "1"},
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)
        captured = capsys.readouterr().out
        assert "ADMIN_AUDIT" in captured
        assert "action=sponsor_create" in captured
        assert "TestSponsor" in captured
