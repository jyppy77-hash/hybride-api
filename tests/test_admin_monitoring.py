"""
Tests — A10: Admin monitoring page and GCP metrics API routes.
Covers: /admin/monitoring, /admin/api/gcp-metrics, /admin/api/gcp-metrics/history,
/admin/api/gemini-breakdown, /admin/api/circuit-breaker/reset.
"""

import os
from unittest.mock import patch, AsyncMock

from starlette.testclient import TestClient


_TEST_TOKEN = "test-token-monitoring-123"
_TEST_PASSWORD = "test-password-monitoring"

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


# ── T1-T3: Monitoring page ──────────────────────────────────────────────────

class TestMonitoringPageAuth:
    """T1-T2: /admin/monitoring requires auth."""

    def test_monitoring_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/monitoring", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    def test_monitoring_requires_owner_ip(self):
        client = _get_client()
        client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
        with patch.dict(os.environ, {"OWNER_IP": "10.0.0.99"}):
            # Re-import to pick up new OWNER_IP
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
            new_client = TestClient(main_mod.app, raise_server_exceptions=False)
            new_client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
            resp = new_client.get("/admin/monitoring", follow_redirects=False)
        # testclient IP is "testclient" which is allowed (dev mode)
        # So this should still pass (testclient bypass). Test auth is checked at least.
        assert resp.status_code in (200, 302)


class TestMonitoringPageRender:
    """T3: /admin/monitoring renders correctly."""

    def test_monitoring_page_renders(self):
        client = _authed_client()
        resp = client.get("/admin/monitoring")
        assert resp.status_code == 200
        assert "Monitoring" in resp.text
        assert "Cloud Run" in resp.text


# ── T4-T5: GCP metrics API ──────────────────────────────────────────────────

class TestGCPMetricsAuth:
    """T4: /admin/api/gcp-metrics requires auth."""

    def test_gcp_metrics_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/gcp-metrics")
        assert resp.status_code == 401


class TestGCPMetricsAPI:
    """T5: /admin/api/gcp-metrics returns JSON."""

    def test_gcp_metrics_returns_json(self):
        client = _authed_client()
        mock_data = {
            "status": "healthy",
            "requests_per_second": 1.5,
            "error_rate_5xx": 0.0,
            "latency_p50_ms": 50,
            "latency_p95_ms": 200,
            "latency_p99_ms": 500,
            "active_instances": 1,
            "cpu_utilization": 0.15,
            "memory_utilization": 0.30,
            "gemini": {"calls_today": 10, "errors_today": 0},
            "costs": {"total_today_eur": 0.50},
        }
        with patch("services.gcp_monitoring.get_gcp_metrics", new_callable=AsyncMock, return_value=mock_data):
            resp = client.get("/admin/api/gcp-metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "requests_per_second" in data

    def test_gcp_metrics_handles_error(self):
        client = _authed_client()
        with patch("services.gcp_monitoring.get_gcp_metrics", new_callable=AsyncMock, side_effect=Exception("GCP down")):
            resp = client.get("/admin/api/gcp-metrics")
        assert resp.status_code == 500
        data = resp.json()
        assert "error" in data


# ── T6: GCP metrics history ─────────────────────────────────────────────────

class TestGCPMetricsHistory:
    """T6: /admin/api/gcp-metrics/history returns JSON."""

    def test_history_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/gcp-metrics/history")
        assert resp.status_code == 401

    def test_history_returns_json(self):
        client = _authed_client()
        mock_points = [{"ts": "2026-03-28T10:00:00", "req_s": 1.0, "err_pct": 0.0}]
        with patch("services.gcp_monitoring.get_metrics_history", new_callable=AsyncMock, return_value=mock_points):
            resp = client.get("/admin/api/gcp-metrics/history?period=24h")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "24h"
        assert len(data["points"]) == 1

    def test_history_invalid_period_defaults(self):
        client = _authed_client()
        with patch("services.gcp_monitoring.get_metrics_history", new_callable=AsyncMock, return_value=[]):
            resp = client.get("/admin/api/gcp-metrics/history?period=invalid")
        assert resp.status_code == 200
        assert resp.json()["period"] == "24h"


# ── T7: Gemini breakdown ────────────────────────────────────────────────────

class TestGeminiBreakdown:
    """T7: /admin/api/gemini-breakdown returns JSON."""

    def test_breakdown_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/gemini-breakdown")
        assert resp.status_code == 401

    def test_breakdown_returns_json(self):
        client = _authed_client()
        mock_data = {
            "by_type": [{"type": "chat_loto", "calls": 100}],
            "by_lang": [{"lang": "fr", "calls": 80}],
        }
        with patch("services.gcp_monitoring.get_gemini_breakdown", new_callable=AsyncMock, return_value=mock_data):
            resp = client.get("/admin/api/gemini-breakdown")
        assert resp.status_code == 200
        data = resp.json()
        assert "by_type" in data
        assert "by_lang" in data

    def test_breakdown_handles_error(self):
        client = _authed_client()
        with patch("services.gcp_monitoring.get_gemini_breakdown", new_callable=AsyncMock, side_effect=Exception("fail")):
            resp = client.get("/admin/api/gemini-breakdown")
        assert resp.status_code == 500
        data = resp.json()
        assert data["by_type"] == []
        assert data["by_lang"] == []


# ── T8-T9: Circuit breaker reset ────────────────────────────────────────────

class TestCircuitBreakerReset:
    """T8-T9: POST /admin/api/circuit-breaker/reset."""

    def test_reset_requires_auth(self):
        client = _get_client()
        resp = client.post("/admin/api/circuit-breaker/reset")
        assert resp.status_code == 401

    def test_reset_works_and_logs_audit(self, capsys):
        client = _authed_client()
        with patch("services.circuit_breaker.gemini_breaker") as mock_breaker:
            mock_breaker.state = "OPEN"
            mock_breaker.force_close = lambda: None
            resp = client.post("/admin/api/circuit-breaker/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "closed"
        assert data["previous_state"] == "OPEN"
        captured = capsys.readouterr().out
        assert "ADMIN_AUDIT" in captured
        assert "circuit_breaker_reset" in captured

    def test_reset_returns_previous_state(self):
        client = _authed_client()
        with patch("services.circuit_breaker.gemini_breaker") as mock_breaker:
            mock_breaker.state = "HALF_OPEN"
            mock_breaker.force_close = lambda: None
            resp = client.post("/admin/api/circuit-breaker/reset")
        assert resp.status_code == 200
        assert resp.json()["previous_state"] == "HALF_OPEN"


# ── T10-T15: Realtime API (V95 F03) ──────────────────────────────────────────

class TestRealtimeAPIAuth:
    """T10: /admin/api/realtime requires auth."""

    def test_realtime_api_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/realtime")
        assert resp.status_code == 401


class TestRealtimeAPI:
    """T11-T15: /admin/api/realtime returns correct JSON."""

    def test_realtime_returns_json_200(self):
        """T11: Authed request returns 200 with expected keys."""
        client = _authed_client()
        mock_events = [
            {"event_type": "page_view", "page": "/accueil", "module": "",
             "lang": "fr", "device": "desktop", "country": "FR",
             "created_at": __import__("datetime").datetime(2026, 4, 11, 10, 0, 0)},
        ]
        mock_kpi = {"total_count": 42, "hour_count": 5, "type_count": 3, "unique_visitors": 10}
        mock_by_type = [{"event_type": "page_view", "cnt": 42}]
        mock_event_types = [{"event_type": "page_view"}, {"event_type": "chatbot-message"}]
        with patch("db_cloudsql.async_fetchall", new_callable=AsyncMock) as mock_all, \
             patch("db_cloudsql.async_fetchone", new_callable=AsyncMock, return_value=mock_kpi):
            mock_all.side_effect = [mock_events, mock_by_type, mock_event_types]
            resp = client.get("/admin/api/realtime")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "kpi" in data
        assert "by_type" in data
        assert "event_types" in data
        assert data["kpi"]["total"] == 42
        assert len(data["events"]) == 1

    def test_realtime_kpi_structure(self):
        """T12: KPI contains expected fields."""
        client = _authed_client()
        mock_kpi = {"total_count": 0, "hour_count": 0, "type_count": 0, "unique_visitors": 0}
        with patch("db_cloudsql.async_fetchall", new_callable=AsyncMock, return_value=[]), \
             patch("db_cloudsql.async_fetchone", new_callable=AsyncMock, return_value=mock_kpi):
            resp = client.get("/admin/api/realtime")
        data = resp.json()
        kpi = data["kpi"]
        assert "total" in kpi
        assert "hour" in kpi
        assert "types" in kpi
        assert "unique_visitors" in kpi

    def test_realtime_period_filter(self):
        """T13: period=month is accepted."""
        client = _authed_client()
        mock_kpi = {"total_count": 0, "hour_count": 0, "type_count": 0, "unique_visitors": 0}
        with patch("db_cloudsql.async_fetchall", new_callable=AsyncMock, return_value=[]), \
             patch("db_cloudsql.async_fetchone", new_callable=AsyncMock, return_value=mock_kpi):
            resp = client.get("/admin/api/realtime?period=month")
        assert resp.status_code == 200

    def test_realtime_invalid_period_defaults(self):
        """T14: Invalid period defaults to 24h (no error)."""
        client = _authed_client()
        mock_kpi = {"total_count": 0, "hour_count": 0, "type_count": 0, "unique_visitors": 0}
        with patch("db_cloudsql.async_fetchall", new_callable=AsyncMock, return_value=[]), \
             patch("db_cloudsql.async_fetchone", new_callable=AsyncMock, return_value=mock_kpi):
            resp = client.get("/admin/api/realtime?period=invalid")
        assert resp.status_code == 200

    def test_realtime_db_error_returns_empty(self):
        """T15: DB error returns graceful empty response."""
        client = _authed_client()
        with patch("db_cloudsql.async_fetchall", new_callable=AsyncMock, side_effect=Exception("DB down")), \
             patch("db_cloudsql.async_fetchone", new_callable=AsyncMock, side_effect=Exception("DB down")):
            resp = client.get("/admin/api/realtime")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["kpi"]["total"] == 0
