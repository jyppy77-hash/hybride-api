"""
Tests unitaires pour db_cloudsql.py — I01 V66 + V129.

V66: pool reconnection automatique.
V129: retry déplacé de get_connection() (double-yield illégal) vers
`_execute_with_retry()` utilisé par async_query/fetchone/fetchall.

Mocker aiomysql — aucune connexion MySQL requise.
"""

from contextlib import asynccontextmanager
from unittest.mock import patch, AsyncMock, MagicMock

import pytest


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _make_pool(healthy=True):
    """Create a mock aiomysql pool."""
    pool = AsyncMock()
    conn = AsyncMock()
    cursor = AsyncMock()
    cursor.execute = AsyncMock()
    conn.cursor = AsyncMock(return_value=cursor)

    @asynccontextmanager
    async def _acquire():
        if not healthy:
            raise Exception("Connection lost during query")
        yield conn

    pool.acquire = _acquire
    pool.close = MagicMock()
    pool.wait_closed = AsyncMock()
    return pool, conn, cursor


# ═══════════════════════════════════════════════════════════════════════
# get_connection — retry after pool recreation
# ═══════════════════════════════════════════════════════════════════════

class TestGetConnectionRetry:

    @pytest.mark.asyncio
    async def test_acquire_succeeds_no_retry(self):
        """Normal case: acquire works on first try, no recreation."""
        import db_cloudsql
        pool, conn, _ = _make_pool(healthy=True)
        original_pool = db_cloudsql._pool
        db_cloudsql._pool = pool
        try:
            async with db_cloudsql.get_connection() as c:
                assert c is conn
        finally:
            db_cloudsql._pool = original_pool

    @pytest.mark.asyncio
    async def test_acquire_fails_propagates_directly_v129(self):
        """V129: get_connection() ne retry plus. Exception propage directement
        (le retry est désormais dans `_execute_with_retry`).
        """
        import db_cloudsql

        dead_pool, _, _ = _make_pool(healthy=False)
        original_pool = db_cloudsql._pool
        db_cloudsql._pool = dead_pool

        try:
            with pytest.raises(Exception, match="Connection lost during query"):
                async with db_cloudsql.get_connection():
                    pass
        finally:
            db_cloudsql._pool = original_pool

    @pytest.mark.asyncio
    async def test_async_query_retry_via_helper_succeeds_v129(self):
        """V129: async_query retry is handled by _execute_with_retry — first
        attempt fails, pool recreated, second attempt succeeds.
        """
        import db_cloudsql

        dead_pool, _, _ = _make_pool(healthy=False)
        healthy_pool, _, _ = _make_pool(healthy=True)

        original_pool = db_cloudsql._pool
        db_cloudsql._pool = dead_pool

        with patch.object(db_cloudsql, '_recreate_pool', new_callable=AsyncMock) as mock_recreate:
            async def _do_recreate():
                db_cloudsql._pool = healthy_pool
            mock_recreate.side_effect = _do_recreate

            try:
                # Should not raise — retry kicks in after pool recreation
                await db_cloudsql.async_query("SELECT 1", None)
                mock_recreate.assert_awaited_once()
            finally:
                db_cloudsql._pool = original_pool

    @pytest.mark.asyncio
    async def test_pool_none_raises_runtime_error(self):
        """get_connection() with _pool=None raises RuntimeError."""
        import db_cloudsql
        original_pool = db_cloudsql._pool
        db_cloudsql._pool = None
        try:
            with pytest.raises(RuntimeError, match="Pool not initialized"):
                async with db_cloudsql.get_connection():
                    pass
        finally:
            db_cloudsql._pool = original_pool

    @pytest.mark.asyncio
    async def test_async_query_double_failure_propagates_v129(self):
        """V129: async_query — first attempt fails, recreation fails,
        original exception propagated."""
        import db_cloudsql

        dead_pool, _, _ = _make_pool(healthy=False)
        original_pool = db_cloudsql._pool
        db_cloudsql._pool = dead_pool

        with patch.object(db_cloudsql, '_recreate_pool', new_callable=AsyncMock) as mock_recreate:
            mock_recreate.side_effect = Exception("Cloud SQL unreachable")
            try:
                with pytest.raises(Exception, match="Connection lost during query"):
                    await db_cloudsql.async_query("SELECT 1", None)
            finally:
                db_cloudsql._pool = original_pool


# ═══════════════════════════════════════════════════════════════════════
# get_connection_readonly — retry
# ═══════════════════════════════════════════════════════════════════════

class TestGetConnectionReadonlyRetry:

    @pytest.mark.asyncio
    async def test_readonly_acquire_succeeds(self):
        """Normal case: readonly acquire works on first try."""
        import db_cloudsql
        pool, conn, _ = _make_pool(healthy=True)
        original_ro = db_cloudsql._pool_readonly
        original_main = db_cloudsql._pool
        db_cloudsql._pool_readonly = pool
        db_cloudsql._pool = MagicMock()  # main pool should not be used
        try:
            async with db_cloudsql.get_connection_readonly() as c:
                assert c is conn
        finally:
            db_cloudsql._pool_readonly = original_ro
            db_cloudsql._pool = original_main

    @pytest.mark.asyncio
    async def test_readonly_retry_via_helper_v129(self):
        """V129: get_connection_readonly() ne retry plus. Retry désormais
        dans `_execute_with_retry(readonly=True)`.
        """
        import db_cloudsql

        dead_pool, _, _ = _make_pool(healthy=False)
        healthy_pool, _, _ = _make_pool(healthy=True)

        original_ro = db_cloudsql._pool_readonly
        original_main = db_cloudsql._pool
        db_cloudsql._pool_readonly = dead_pool
        db_cloudsql._pool = MagicMock()

        with patch.object(db_cloudsql, '_recreate_pool_readonly', new_callable=AsyncMock) as mock_recreate:
            async def _do_recreate():
                db_cloudsql._pool_readonly = healthy_pool
            mock_recreate.side_effect = _do_recreate

            try:
                # Use the retry helper directly with readonly=True
                async def _op(conn):
                    return "ok"
                result = await db_cloudsql._execute_with_retry(_op, readonly=True)
                assert result == "ok"
                mock_recreate.assert_awaited_once()
            finally:
                db_cloudsql._pool_readonly = original_ro
                db_cloudsql._pool = original_main

    @pytest.mark.asyncio
    async def test_readonly_fallback_to_main_pool(self):
        """If readonly pool is None, falls back to main pool."""
        import db_cloudsql
        main_pool, main_conn, _ = _make_pool(healthy=True)
        original_ro = db_cloudsql._pool_readonly
        original_main = db_cloudsql._pool
        db_cloudsql._pool_readonly = None
        db_cloudsql._pool = main_pool
        try:
            async with db_cloudsql.get_connection_readonly() as c:
                assert c is main_conn
        finally:
            db_cloudsql._pool_readonly = original_ro
            db_cloudsql._pool = original_main

    @pytest.mark.asyncio
    async def test_readonly_both_none_raises(self):
        """Both pools None → RuntimeError."""
        import db_cloudsql
        original_ro = db_cloudsql._pool_readonly
        original_main = db_cloudsql._pool
        db_cloudsql._pool_readonly = None
        db_cloudsql._pool = None
        try:
            with pytest.raises(RuntimeError, match="Pool not initialized"):
                async with db_cloudsql.get_connection_readonly():
                    pass
        finally:
            db_cloudsql._pool_readonly = original_ro
            db_cloudsql._pool = original_main


# ═══════════════════════════════════════════════════════════════════════
# _recreate_pool — lock + double-check
# ═══════════════════════════════════════════════════════════════════════

class TestRecreatePool:

    @pytest.mark.asyncio
    async def test_recreate_replaces_dead_pool(self):
        """Dead pool → _recreate_pool creates a fresh pool."""
        import db_cloudsql

        dead_pool, _, _ = _make_pool(healthy=False)
        fresh_pool, _, _ = _make_pool(healthy=True)

        original_pool = db_cloudsql._pool
        db_cloudsql._pool = dead_pool

        with patch('db_cloudsql.aiomysql') as mock_aiomysql:
            mock_aiomysql.create_pool = AsyncMock(return_value=fresh_pool)
            mock_aiomysql.DictCursor = MagicMock()
            try:
                await db_cloudsql._recreate_pool()
                assert db_cloudsql._pool is fresh_pool
                mock_aiomysql.create_pool.assert_awaited_once()
            finally:
                db_cloudsql._pool = original_pool

    @pytest.mark.asyncio
    async def test_recreate_skips_if_pool_healthy(self):
        """If pool is actually healthy (SELECT 1 works), skip recreation."""
        import db_cloudsql

        healthy_pool, _, _ = _make_pool(healthy=True)

        original_pool = db_cloudsql._pool
        db_cloudsql._pool = healthy_pool

        with patch('db_cloudsql.aiomysql') as mock_aiomysql:
            mock_aiomysql.create_pool = AsyncMock()
            try:
                await db_cloudsql._recreate_pool()
                # Pool should remain the same — no recreation
                assert db_cloudsql._pool is healthy_pool
                mock_aiomysql.create_pool.assert_not_awaited()
            finally:
                db_cloudsql._pool = original_pool


# ═══════════════════════════════════════════════════════════════════════
# pool_recycle config
# ═══════════════════════════════════════════════════════════════════════

class TestPoolConfig:

    def test_pool_recycle_1800(self):
        """Pool recycle should be 1800s (30min), not the old 3600s."""
        import db_cloudsql
        assert db_cloudsql._POOL_RECYCLE == 1800

    def test_build_pool_kwargs_production(self):
        """Production kwargs use unix_socket."""
        import db_cloudsql
        with patch.object(db_cloudsql, 'is_production', return_value=True):
            kwargs = db_cloudsql._build_pool_kwargs("user", "pass", 5, 10)
            assert "unix_socket" in kwargs
            assert kwargs["pool_recycle"] == 1800
            assert kwargs["connect_timeout"] == 5

    def test_build_pool_kwargs_local(self):
        """Local kwargs use host+port."""
        import db_cloudsql
        with patch.object(db_cloudsql, 'is_production', return_value=False):
            kwargs = db_cloudsql._build_pool_kwargs("user", "pass", 2, 5)
            assert "host" in kwargs
            assert "port" in kwargs
            assert "unix_socket" not in kwargs
