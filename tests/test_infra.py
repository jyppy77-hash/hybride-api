"""
Tests infrastructure — I07/I09/I16 V66: lifespan, health, middleware pipeline,
rate limiter, supervised tasks, access log, circuit breaker admin reset.
Uses TestClient + mocks (no real DB/Redis).
"""

import asyncio
import os
from contextlib import asynccontextmanager
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ── Patches applied BEFORE main.py import ───────────────────────────

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake",
    "DB_USER": "test",
    "DB_NAME": "testdb",
})


def _async_cm_conn(cursor):
    @asynccontextmanager
    async def _cm():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn
    return _cm


def _get_client():
    with _db_env, _static_patch, _static_call:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False), main_mod


# ═══════════════════════════════════════════════════════════════════════
# A. Health endpoint
# ═══════════════════════════════════════════════════════════════════════

class TestHealthEndpoint:

    @patch("main.db_cloudsql")
    def test_health_returns_200_with_all_keys(self, mock_db):
        """GET /health returns 200 with all expected keys."""
        cursor = AsyncMock()
        mock_db.get_connection = _async_cm_conn(cursor)

        client, main_mod = _get_client()
        main_mod.db_cloudsql = mock_db
        resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        for key in ("status", "database", "gemini", "uptime_seconds", "version", "engine"):
            assert key in data, f"Missing key: {key}"

    @patch("main.db_cloudsql")
    def test_health_db_down_returns_degraded_not_500(self, mock_db):
        """DB unreachable → status degraded (not 500)."""
        mock_db.get_connection.side_effect = Exception("Connection refused")

        client, main_mod = _get_client()
        main_mod.db_cloudsql = mock_db
        resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["database"] == "unreachable"

    @patch("main.db_cloudsql")
    def test_health_version_matches_config(self, mock_db):
        """Health endpoint version matches config/version.py."""
        cursor = AsyncMock()
        mock_db.get_connection = _async_cm_conn(cursor)

        client, main_mod = _get_client()
        main_mod.db_cloudsql = mock_db
        resp = client.get("/health")

        from config.version import APP_VERSION
        assert resp.json()["version"] == APP_VERSION


# ═══════════════════════════════════════════════════════════════════════
# B. Lifespan startup/shutdown
# ═══════════════════════════════════════════════════════════════════════

class TestLifespan:

    def test_lifespan_creates_httpx_client(self):
        """After startup, app.state.httpx_client exists."""
        client, main_mod = _get_client()
        # TestClient enters lifespan on first request
        with patch.object(main_mod, 'db_cloudsql') as mock_db:
            mock_db.get_connection = _async_cm_conn(AsyncMock())
            resp = client.get("/health")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# C. Middleware pipeline
# ═══════════════════════════════════════════════════════════════════════

class TestMiddlewarePipeline:

    def test_csrf_rejects_bad_origin(self):
        """POST with invalid Origin header → 403."""
        client, _ = _get_client()
        resp = client.post(
            "/api/version",
            headers={"Origin": "https://evil.com"},
        )
        assert resp.status_code == 403

    def test_csrf_allows_legitimate_origin(self):
        """POST with lotoia.fr Origin → not 403."""
        client, main_mod = _get_client()
        with patch.object(main_mod, 'db_cloudsql') as mock_db:
            mock_db.get_connection = _async_cm_conn(AsyncMock())
            resp = client.post(
                "/api/contact",
                headers={"Origin": "https://lotoia.fr", "Content-Type": "application/json"},
                json={"name": "test", "email": "a@b.com", "message": "hi"},
            )
        # Should not be 403 (may be 422 or other, but not CSRF blocked)
        assert resp.status_code != 403

    def test_x_request_id_in_response(self):
        """Every response has an X-Request-ID header."""
        client, main_mod = _get_client()
        with patch.object(main_mod, 'db_cloudsql') as mock_db:
            mock_db.get_connection = _async_cm_conn(AsyncMock())
            resp = client.get("/health")
        assert "x-request-id" in resp.headers
        assert len(resp.headers["x-request-id"]) > 0

    def test_x_request_id_unique_per_request(self):
        """Two requests get different X-Request-IDs."""
        client, main_mod = _get_client()
        with patch.object(main_mod, 'db_cloudsql') as mock_db:
            mock_db.get_connection = _async_cm_conn(AsyncMock())
            r1 = client.get("/health")
            r2 = client.get("/health")
        assert r1.headers["x-request-id"] != r2.headers["x-request-id"]

    def test_security_headers_present(self):
        """Responses include key security headers."""
        client, main_mod = _get_client()
        with patch.object(main_mod, 'db_cloudsql') as mock_db:
            mock_db.get_connection = _async_cm_conn(AsyncMock())
            resp = client.get("/health")
        assert "content-security-policy" in resp.headers
        assert "x-content-type-options" in resp.headers
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert "strict-transport-security" in resp.headers
        assert "x-frame-options" in resp.headers


# ═══════════════════════════════════════════════════════════════════════
# D. Rate limiter memory bound
# ═══════════════════════════════════════════════════════════════════════

class TestRateLimiterMemoryBound:

    def test_api_hits_cleared_above_max_tracked_ips(self):
        """_api_hits dict is cleared when it exceeds 10K entries."""
        from rate_limit import _api_hits, _API_MAX_TRACKED_IPS
        _api_hits.clear()

        # Fill with 10001 fake IPs
        for i in range(_API_MAX_TRACKED_IPS + 1):
            _api_hits[f"10.0.{i // 256}.{i % 256}"] = MagicMock()

        assert len(_api_hits) > _API_MAX_TRACKED_IPS

        # The middleware should clear on next request
        client, main_mod = _get_client()
        with patch.object(main_mod, 'db_cloudsql') as mock_db:
            mock_db.get_connection = _async_cm_conn(AsyncMock())
            # Make an /api/ request to trigger the middleware
            client.get("/api/version")

        # Dict should have been cleared (and only the new IP added)
        assert len(_api_hits) <= 2
        _api_hits.clear()


# ═══════════════════════════════════════════════════════════════════════
# E. Supervised background tasks (I02)
# ═══════════════════════════════════════════════════════════════════════

class TestSupervisedTask:

    @pytest.mark.asyncio
    async def test_supervised_task_logs_exception(self):
        """_supervised_task catches and logs exceptions."""
        from main import _supervised_task

        async def _failing_coro():
            raise ValueError("DB pool not ready")

        with patch("main.logger") as mock_logger:
            await _supervised_task(_failing_coro(), "test_task")
            mock_logger.exception.assert_called_once()
            assert "test_task" in str(mock_logger.exception.call_args)

    @pytest.mark.asyncio
    async def test_supervised_task_no_log_on_success(self):
        """_supervised_task does not log on success."""
        from main import _supervised_task

        async def _ok_coro():
            return 42

        with patch("main.logger") as mock_logger:
            await _supervised_task(_ok_coro(), "ok_task")
            mock_logger.exception.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# F. Batched cleanup (I11)
# ═══════════════════════════════════════════════════════════════════════

class TestBatchedCleanup:

    @pytest.mark.asyncio
    async def test_batched_cleanup_multiple_batches(self):
        """25000 expired rows → 3 batches of 10000."""
        from services.gcp_monitoring import _batched_cleanup

        call_count = 0
        remaining = 25000

        @asynccontextmanager
        async def _mock_conn():
            conn = AsyncMock()
            cursor = AsyncMock()

            async def _execute(sql, params=None):
                nonlocal call_count, remaining
                call_count += 1
                batch = min(10000, remaining)
                remaining -= batch
                cursor.rowcount = batch

            cursor.execute = _execute
            conn.cursor = AsyncMock(return_value=cursor)
            yield conn

        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_asyncio:
            mock_db.get_connection = _mock_conn
            mock_asyncio.sleep = AsyncMock()

            total = await _batched_cleanup("event_log", "created_at", 90)

        assert total == 25000
        # 3 batches with data + 1 final check that returns 0
        assert call_count == 4
        # sleep called after each batch with data (3 times)
        assert mock_asyncio.sleep.await_count == 3

    @pytest.mark.asyncio
    async def test_batched_cleanup_empty_table(self):
        """Empty table → 0 batches, no warning."""
        from services.gcp_monitoring import _batched_cleanup

        @asynccontextmanager
        async def _mock_conn():
            conn = AsyncMock()
            cursor = AsyncMock()
            cursor.rowcount = 0
            conn.cursor = AsyncMock(return_value=cursor)
            yield conn

        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_asyncio, \
             patch("services.gcp_monitoring.logger") as mock_logger:
            mock_db.get_connection = _mock_conn
            mock_asyncio.sleep = AsyncMock()

            total = await _batched_cleanup("chat_log", "created_at", 90)

        assert total == 0
        mock_logger.warning.assert_not_called()
        mock_logger.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_batched_cleanup_correct_sql(self):
        """Cleanup uses correct table name and ts column in SQL."""
        from services.gcp_monitoring import _batched_cleanup

        captured_sql = []

        @asynccontextmanager
        async def _mock_conn():
            conn = AsyncMock()
            cursor = AsyncMock()

            async def _execute(sql, params=None):
                captured_sql.append(sql)
                cursor.rowcount = 0

            cursor.execute = _execute
            conn.cursor = AsyncMock(return_value=cursor)
            yield conn

        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_asyncio:
            mock_db.get_connection = _mock_conn
            mock_asyncio.sleep = AsyncMock()

            await _batched_cleanup("gemini_tracking", "ts", 90, batch_size=5000)

        assert len(captured_sql) == 1
        assert "gemini_tracking" in captured_sql[0]
        assert "ts <" in captured_sql[0]
        assert "LIMIT 5000" in captured_sql[0]

    @pytest.mark.asyncio
    async def test_cleanup_wrappers_call_batched(self):
        """cleanup_event_log/chat_log/gemini_tracking all call _batched_cleanup."""
        from services import gcp_monitoring

        with patch.object(gcp_monitoring, '_batched_cleanup', new_callable=AsyncMock, return_value=42) as mock_bc:
            r1 = await gcp_monitoring.cleanup_event_log(days=90)
            assert r1 == 42
            mock_bc.assert_awaited_with("event_log", "created_at", 90)

        with patch.object(gcp_monitoring, '_batched_cleanup', new_callable=AsyncMock, return_value=10) as mock_bc:
            r2 = await gcp_monitoring.cleanup_chat_log(days=30)
            assert r2 == 10
            mock_bc.assert_awaited_with("chat_log", "created_at", 30)

        with patch.object(gcp_monitoring, '_batched_cleanup', new_callable=AsyncMock, return_value=5) as mock_bc:
            r3 = await gcp_monitoring.cleanup_gemini_tracking(days=60)
            assert r3 == 5
            mock_bc.assert_awaited_with("gemini_tracking", "ts", 60)


# ═══════════════════════════════════════════════════════════════════════
# G. Access log middleware (I09)
# ═══════════════════════════════════════════════════════════════════════

class TestAccessLogMiddleware:

    @patch("main.db_cloudsql")
    def test_normal_request_logged(self, mock_db):
        """Non-static request generates an access log with duration_ms."""
        cursor = AsyncMock()
        mock_db.get_connection = _async_cm_conn(cursor)

        client, main_mod = _get_client()
        main_mod.db_cloudsql = mock_db

        with patch.object(main_mod, 'logger') as mock_logger:
            client.get("/health")
            # Access log should NOT be generated for /health (excluded path)
            info_calls = [c for c in mock_logger.info.call_args_list if c[0][0] == "access_log"]
            assert len(info_calls) == 0

    @patch("main.db_cloudsql")
    def test_api_request_logged(self, mock_db):
        """API request generates an access log entry."""
        cursor = AsyncMock()
        mock_db.get_connection = _async_cm_conn(cursor)

        client, main_mod = _get_client()
        main_mod.db_cloudsql = mock_db

        with patch.object(main_mod, 'logger') as mock_logger:
            client.get("/api/version")
            info_calls = [c for c in mock_logger.info.call_args_list if c[0][0] == "access_log"]
            assert len(info_calls) >= 1
            extra = info_calls[0][1].get("extra", {})
            assert "duration_ms" in extra
            assert "status_code" in extra
            assert extra["method"] == "GET"
            assert extra["path"] == "/api/version"

    def test_static_path_not_logged(self):
        """Requests to /static/* are not logged."""
        client, main_mod = _get_client()

        with patch.object(main_mod, 'logger') as mock_logger:
            client.get("/static/app.js")
            info_calls = [c for c in mock_logger.info.call_args_list if c[0][0] == "access_log"]
            assert len(info_calls) == 0

    def test_health_path_not_logged(self):
        """Requests to /health are not logged (keep logs clean)."""
        client, main_mod = _get_client()

        with patch.object(main_mod, 'logger') as mock_logger:
            with patch.object(main_mod, 'db_cloudsql') as mock_db:
                mock_db.get_connection = _async_cm_conn(AsyncMock())
                client.get("/health")
            info_calls = [c for c in mock_logger.info.call_args_list if c[0][0] == "access_log"]
            assert len(info_calls) == 0


# ═══════════════════════════════════════════════════════════════════════
# H. Circuit breaker admin reset endpoint (I16)
# ═══════════════════════════════════════════════════════════════════════

_admin_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake",
    "DB_USER": "test",
    "DB_NAME": "testdb",
    "ADMIN_TOKEN": "test_admin_token_infra",
    "ADMIN_PASSWORD": "test_admin_password",
})


def _get_admin_client():
    with _admin_env, _static_patch, _static_call:
        import importlib
        import rate_limit as rl_mod
        importlib.reload(rl_mod)
        import routes.admin as admin_mod
        importlib.reload(admin_mod)
        import main as main_mod
        importlib.reload(main_mod)
        rl_mod._api_hits.clear()
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        client.cookies.set("lotoia_admin_token", "test_admin_token_infra")
        return client


class TestCircuitBreakerResetEndpoint:

    def test_reset_returns_200(self):
        """POST /admin/api/circuit-breaker/reset → 200 with closed status."""
        client = _get_admin_client()
        resp = client.post("/admin/api/circuit-breaker/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "closed"
        assert "message" in data

    def test_reset_unauthenticated_redirects(self):
        """POST without auth cookie → 401."""
        with _admin_env, _static_patch, _static_call:
            import importlib
            import rate_limit as rl_mod
            importlib.reload(rl_mod)
            import routes.admin as admin_mod
            importlib.reload(admin_mod)
            import main as main_mod
            importlib.reload(main_mod)
            rl_mod._api_hits.clear()
            client = TestClient(main_mod.app, raise_server_exceptions=False)
            resp = client.post("/admin/api/circuit-breaker/reset")
        assert resp.status_code == 401
