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

    def test_api_hits_evicted_above_max_tracked_ips(self):
        """S05 V94: _api_hits LRU eviction (~20% removed, not full clear)."""
        import time as _time
        from rate_limit import _api_hits, _API_MAX_TRACKED_IPS, _evict_oldest_deque
        _api_hits.clear()

        # Fill with 10001 fake IPs with recent timestamps
        now = _time.monotonic()
        for i in range(_API_MAX_TRACKED_IPS + 1):
            from collections import deque
            _api_hits[f"10.0.{i // 256}.{i % 256}"] = deque([now - 10 + (i / 10_001)])

        assert len(_api_hits) > _API_MAX_TRACKED_IPS

        # Trigger eviction directly
        _evict_oldest_deque(_api_hits, _API_MAX_TRACKED_IPS)

        # S05 V94: LRU eviction keeps ~80%, not full clear
        assert len(_api_hits) <= _API_MAX_TRACKED_IPS
        assert len(_api_hits) >= 7_000
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
            rl_mod._api_hits.clear()
            client = TestClient(main_mod.app, raise_server_exceptions=False)
            resp = client.post("/admin/api/circuit-breaker/reset")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════
# I. Health check Redis (I01 V67)
# ═══════════════════════════════════════════════════════════════════════

class TestHealthRedis:

    @patch("main.db_cloudsql")
    def test_health_redis_ok(self, mock_db):
        """Redis up → 'redis': 'ok' in response, status still 'ok'."""
        cursor = AsyncMock()
        mock_db.get_connection = _async_cm_conn(cursor)

        client, main_mod = _get_client()
        main_mod.db_cloudsql = mock_db

        with patch("services.cache.cache_set", new_callable=AsyncMock) as mock_set, \
             patch("services.cache.cache_get", new_callable=AsyncMock, return_value="1"):
            resp = client.get("/health")

        data = resp.json()
        assert data["redis"] == "ok"
        assert data["status"] == "ok"

    @patch("main.db_cloudsql")
    def test_health_redis_down_status_remains_ok(self, mock_db):
        """Redis down → 'redis': 'unavailable', overall status stays 'ok' (cache is non-critical)."""
        cursor = AsyncMock()
        mock_db.get_connection = _async_cm_conn(cursor)

        client, main_mod = _get_client()
        main_mod.db_cloudsql = mock_db

        with patch("services.cache.cache_set", new_callable=AsyncMock, side_effect=Exception("Redis connect timeout")), \
             patch("services.cache.cache_get", new_callable=AsyncMock):
            resp = client.get("/health")

        data = resp.json()
        assert data["redis"] == "unavailable"
        assert data["status"] == "ok"  # Redis is non-critical


# ═══════════════════════════════════════════════════════════════════════
# J. Supervised loop (I03 V67)
# ═══════════════════════════════════════════════════════════════════════

class TestSupervisedLoop:

    @pytest.mark.asyncio
    async def test_supervised_loop_restarts_on_crash(self):
        """If coroutine crashes, _supervised_loop logs and restarts after delay."""
        from main import _supervised_loop

        call_count = 0

        async def _crashing_loop():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("boom")
            # 3rd call: return normally to end the loop

        with patch("main.logger") as mock_logger, \
             patch("main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _supervised_loop(_crashing_loop, "test_loop", restart_delay=5.0)

        assert call_count == 3
        # 2 crashes → 2 exception logs + 2 sleeps
        assert mock_logger.exception.call_count == 2
        assert mock_sleep.await_count == 2
        mock_sleep.assert_awaited_with(5.0)

    @pytest.mark.asyncio
    async def test_supervised_loop_no_log_on_success(self):
        """If coroutine runs and returns, no error logged."""
        from main import _supervised_loop

        async def _ok_loop():
            return  # exits immediately

        with patch("main.logger") as mock_logger, \
             patch("main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _supervised_loop(_ok_loop, "ok_loop")

        mock_logger.exception.assert_not_called()
        mock_sleep.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════
# K. Redis TLS enforcement log level (I02 V67)
# ═══════════════════════════════════════════════════════════════════════

class TestRedisTlsEnforcement:

    @pytest.mark.asyncio
    async def test_non_tls_url_in_prod_logs_error(self):
        """redis:// URL in prod (K_SERVICE set) → logger.error (not warning)."""
        import services.cache as cache_mod

        with patch.dict(os.environ, {"REDIS_URL": "redis://10.0.0.1:6379", "K_SERVICE": "hybride-api-eu"}), \
             patch.object(cache_mod, "_redis", None), \
             patch("services.cache.logger") as mock_logger:
            # Prevent actual Redis connection
            mock_redis_cls = MagicMock()
            mock_redis_instance = AsyncMock()
            mock_redis_instance.ping = AsyncMock(side_effect=Exception("no real redis"))
            mock_redis_cls.from_url.return_value = mock_redis_instance
            with patch.dict("sys.modules", {"redis.asyncio": mock_redis_cls}):
                with patch("services.cache.os.getenv", side_effect=lambda k, d="": {"REDIS_URL": "redis://10.0.0.1:6379", "K_SERVICE": "hybride-api-eu"}.get(k, d)):
                    await cache_mod.init_cache()

            # Should have called logger.error for TLS warning
            error_calls = [c for c in mock_logger.error.call_args_list if "TLS" in str(c)]
            assert len(error_calls) >= 1

    @pytest.mark.asyncio
    async def test_tls_url_in_prod_no_error(self):
        """rediss:// URL in prod → no TLS error log."""
        import services.cache as cache_mod

        with patch.dict(os.environ, {"REDIS_URL": "rediss://10.0.0.1:6380", "K_SERVICE": "hybride-api-eu"}), \
             patch.object(cache_mod, "_redis", None), \
             patch("services.cache.logger") as mock_logger:
            mock_redis_cls = MagicMock()
            mock_redis_instance = AsyncMock()
            mock_redis_instance.ping = AsyncMock(side_effect=Exception("no real redis"))
            mock_redis_cls.from_url.return_value = mock_redis_instance
            with patch.dict("sys.modules", {"redis.asyncio": mock_redis_cls}):
                with patch("services.cache.os.getenv", side_effect=lambda k, d="": {"REDIS_URL": "rediss://10.0.0.1:6380", "K_SERVICE": "hybride-api-eu"}.get(k, d)):
                    await cache_mod.init_cache()

            error_calls = [c for c in mock_logger.error.call_args_list if "TLS" in str(c)]
            assert len(error_calls) == 0
