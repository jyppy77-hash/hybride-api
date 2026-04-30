"""
Tests for /admin/chatbot-monitor routes — Chatbot Monitor V44.
"""

import os
from unittest.mock import patch, AsyncMock, MagicMock
from decimal import Decimal

from starlette.testclient import TestClient

_TEST_TOKEN = "test_admin_token_1234567890"

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "ADMIN_TOKEN": _TEST_TOKEN, "ADMIN_PASSWORD": "testpw",
})


def _get_client():
    with _db_env, _static_patch, _static_call:
        import importlib
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
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _authed_client():
    client = _get_client()
    client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
    return client


class TestChatbotMonitorAuth:
    """Authentication tests for chatbot-monitor."""

    def test_chatbot_monitor_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/chatbot-monitor", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers.get("location", "")

    def test_api_chatbot_log_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/chatbot-log")
        assert resp.status_code == 401

    def test_export_csv_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/export/chatbot-log/csv", follow_redirects=False)
        assert resp.status_code == 302


class TestChatbotMonitorPage:
    """Template rendering tests."""

    def test_chatbot_monitor_page_renders(self):
        client = _authed_client()
        resp = client.get("/admin/chatbot-monitor")
        assert resp.status_code == 200
        assert "Chatbot Monitor" in resp.text
        assert "cm-period" in resp.text
        assert "cm-module" in resp.text
        assert "cm-phase" in resp.text
        assert "admin.js?v=22" in resp.text  # F08 V117: v15 → ... → V137.B: v21 → V137.D: v22 (modal date+chrono+secondary_balls)

    def test_nav_contains_chatbot_link(self):
        client = _authed_client()
        resp = client.get("/admin/chatbot-monitor")
        assert "chatbot-monitor" in resp.text
        assert 'active' in resp.text  # "chatbot" nav link is active


class TestChatbotMonitorAPI:
    """JSON API tests."""

    def test_api_chatbot_log_returns_json(self):
        client = _authed_client()
        with patch("routes.admin_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "total": Decimal(5), "rejected": Decimal(1),
                "sql_total": Decimal(3), "errors": Decimal(0),
                "avg_dur": Decimal(250), "sessions": Decimal(2),
                "sql_count": Decimal(3),
            })
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/chatbot-log")
        assert resp.status_code == 200
        data = resp.json()
        assert "kpi" in data
        assert "exchanges" in data
        assert data["kpi"]["total"] == 5
        assert data["kpi"]["unique_sessions"] == 2

    def test_api_chatbot_log_with_filters(self):
        client = _authed_client()
        with patch("routes.admin_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "total": Decimal(2), "rejected": Decimal(0),
                "sql_total": Decimal(0), "errors": Decimal(0),
                "avg_dur": Decimal(100), "sessions": Decimal(1),
                "sql_count": Decimal(0),
            })
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/chatbot-log?period=1h&module=em&phase=SQL&status=OK&lang=fr&errors_only=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kpi"]["total"] == 2

    def test_api_chatbot_log_kpi_calculations(self):
        client = _authed_client()
        with patch("routes.admin_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "total": Decimal(100), "rejected": Decimal(5),
                "sql_total": Decimal(20), "errors": Decimal(3),
                "avg_dur": Decimal(350), "sessions": Decimal(15),
                "sql_count": Decimal(20),
            })
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/chatbot-log")
        data = resp.json()
        kpi = data["kpi"]
        assert kpi["total"] == 100
        assert kpi["rejected_pct"] == 25.0   # 5/20 * 100
        assert kpi["error_pct"] == 3.0       # 3/100 * 100
        assert kpi["avg_duration"] == 350
        assert kpi["unique_sessions"] == 15
        assert kpi["sql_count"] == 20

    def test_api_chatbot_log_table_data(self):
        from datetime import datetime
        client = _authed_client()
        mock_row = {
            "id": 42,
            "created_at": datetime(2026, 3, 18, 14, 30, 0),
            "module": "em",
            "lang": "en",
            "question": "show me top 5 numbers",
            "response_preview": "Here are the top numbers...",
            "phase_detected": "SQL",
            "sql_generated": "SELECT num FROM stats LIMIT 5",
            "sql_status": "OK",
            "duration_ms": 234,
            "grid_count": 0,
            "has_exclusions": 0,
            "is_error": 0,
            "error_detail": None,
            "gemini_tokens_in": 150,
            "gemini_tokens_out": 80,
            "session_hash": "abc123def456xyz",
        }
        with patch("routes.admin_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "total": Decimal(1), "rejected": Decimal(0),
                "sql_total": Decimal(1), "errors": Decimal(0),
                "avg_dur": Decimal(234), "sessions": Decimal(1),
                "sql_count": Decimal(1),
            })
            mock_db.async_fetchall = AsyncMock(return_value=[mock_row])
            resp = client.get("/admin/api/chatbot-log")
        data = resp.json()
        assert len(data["exchanges"]) == 1
        row = data["exchanges"][0]
        assert row["id"] == 42
        assert row["module"] == "em"
        assert row["phase"] == "SQL"
        assert row["sql_status"] == "OK"
        assert row["duration_ms"] == 234
        assert row["session_hash"] == "abc123def456"  # truncated to 12

    def test_api_chatbot_log_db_error_returns_empty(self):
        client = _authed_client()
        with patch("routes.admin_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(side_effect=Exception("DB down"))
            mock_db.async_fetchall = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin/api/chatbot-log")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kpi"]["total"] == 0
        assert data["exchanges"] == []


class TestChatbotMonitorExport:
    """CSV export tests."""

    def test_export_csv_returns_csv(self):
        from datetime import datetime
        client = _authed_client()
        mock_row = {
            "id": 99,
            "created_at": datetime(2026, 3, 18, 14, 0, 0),
            "module": "loto", "lang": "fr",
            "question": "test question",
            "response_preview": "Voici la réponse...",
            "phase_detected": "Gemini",
            "sql_generated": None, "sql_status": "N/A",
            "duration_ms": 200, "is_error": 0,
            "error_detail": None, "grid_count": 0,
            "has_exclusions": 0,
            "gemini_tokens_in": 100, "gemini_tokens_out": 50,
            "ip_hash": "a1b2c3d4e5f6", "session_hash": "s1s2s3s4s5s6",
        }
        with patch("routes.admin_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[mock_row])
            resp = client.get("/admin/export/chatbot-log/csv?period=24h")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "chatbot_log_" in resp.headers.get("content-disposition", "")
        lines = resp.text.strip().split("\n")
        assert len(lines) == 2  # header + 1 row
        header = lines[0]
        assert "created_at" in header
        assert "response_preview" in header
        assert "tokens_in" in header
        assert "tokens_out" in header
        assert "ip_hash" in header
        assert "session_hash" in header
        # Verify data row contains response
        assert "Voici la réponse" in lines[1]

    def test_export_csv_with_filters(self):
        client = _authed_client()
        with patch("routes.admin_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/export/chatbot-log/csv?period=7d&module=em&phase=SQL")
        assert resp.status_code == 200
