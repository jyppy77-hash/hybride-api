"""
Tests F01 V122 — query timeout double layer.

1. Client-side: `execute_with_timeout()` wraps `cur.execute()` in
   `asyncio.wait_for` → raises `asyncio.TimeoutError` on slow queries.
2. Server-side: `_build_pool_kwargs()` injects
   `init_command="SET SESSION MAX_EXECUTION_TIME=10000"` on every pool connection.
"""

import asyncio
import inspect
from unittest.mock import AsyncMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════
# Client-side layer — execute_with_timeout()
# ═══════════════════════════════════════════════════════════════════════

class TestExecuteWithTimeout:

    @pytest.mark.asyncio
    async def test_execute_with_timeout_success(self):
        """Fast query (< timeout) completes without raising."""
        from db_cloudsql import execute_with_timeout

        cur = AsyncMock()
        cur.execute = AsyncMock(return_value=None)

        await execute_with_timeout(cur, "SELECT 1", timeout=5.0)

        cur.execute.assert_awaited_once_with("SELECT 1", None)

    @pytest.mark.asyncio
    async def test_execute_with_timeout_exceeds(self):
        """Slow query (> timeout) raises asyncio.TimeoutError."""
        from db_cloudsql import execute_with_timeout

        cur = AsyncMock()

        async def _slow(sql, params=None):
            await asyncio.sleep(2)

        cur.execute = _slow

        with pytest.raises(asyncio.TimeoutError):
            await execute_with_timeout(cur, "SELECT SLEEP(2)", timeout=0.1)

    @pytest.mark.asyncio
    async def test_execute_with_timeout_passes_params_correctly(self):
        """Parameterized query — params tuple forwarded verbatim to cur.execute."""
        from db_cloudsql import execute_with_timeout

        cur = AsyncMock()
        cur.execute = AsyncMock(return_value=None)

        params = (42, "active", "2026-04-17")
        sql = "SELECT * FROM tirages WHERE id = %s AND status = %s AND date = %s"

        await execute_with_timeout(cur, sql, params, timeout=5.0)

        cur.execute.assert_awaited_once_with(sql, params)

    def test_execute_with_timeout_default_10s(self):
        """Signature default: timeout = 10.0 seconds."""
        from db_cloudsql import execute_with_timeout

        sig = inspect.signature(execute_with_timeout)
        assert sig.parameters["timeout"].default == 10.0


# ═══════════════════════════════════════════════════════════════════════
# Server-side layer — init_command in _build_pool_kwargs
# ═══════════════════════════════════════════════════════════════════════

class TestSessionMaxExecutionTime:

    def test_build_pool_kwargs_includes_init_command(self):
        """_build_pool_kwargs injects SET SESSION MAX_EXECUTION_TIME=10000."""
        import db_cloudsql

        with patch.object(db_cloudsql, "is_production", return_value=False):
            kwargs = db_cloudsql._build_pool_kwargs("user", "pass", 5, 10)

        assert "init_command" in kwargs
        assert "MAX_EXECUTION_TIME" in kwargs["init_command"]
        assert "10000" in kwargs["init_command"]
