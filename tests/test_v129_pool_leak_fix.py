"""
V129 — Fix double-yield leak + ip_ban rate limit.

Tests critiques qui protègent contre la régression du bug production
(révision 00831-ccr, 21/04/2026) :

    [IP_BAN] auto-ban insert failed: generator didn't stop after athrow()

Root cause : `get_connection()` en @asynccontextmanager avec 2ᵉ yield illégal
après exception dans le user-block → RuntimeError + leak de connexion →
corruption du pool → 502 sur /api/pitch-grilles.

Fixes V129 couverts par ces tests :
  1. get_connection() / get_connection_readonly() ne font plus de retry
     (single yield, propagation directe).
  2. Retry déplacé dans `_execute_with_retry(op, readonly=)` utilisé par
     async_query/fetchone/fetchall.
  3. Middleware ip_ban `_auto_ban_ip` : debounce 2s/IP + Semaphore(5) +
     asyncio.wait_for timeout 2s + swallow toute exception.

Mocks exclusifs — aucune connexion MySQL nécessaire.
"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _make_pool(healthy: bool = True, acquire_fail_count: int = 0):
    """Mock aiomysql pool avec tracking acquire/release (détection leaks).

    Args:
        healthy: si False, l'acquire lève une exception.
        acquire_fail_count: si > 0, les N premiers acquires échouent puis
            les suivants réussissent (simule erreur transitoire).
    """
    pool = MagicMock()
    conn = AsyncMock()
    cursor = AsyncMock()
    cursor.execute = AsyncMock()
    conn.cursor = AsyncMock(return_value=cursor)

    pool.acquired = 0
    pool.released = 0
    pool.fail_remaining = acquire_fail_count

    @asynccontextmanager
    async def _acquire():
        if not healthy:
            raise RuntimeError("simulated pool failure")
        if pool.fail_remaining > 0:
            pool.fail_remaining -= 1
            raise RuntimeError("simulated transient acquire failure")
        pool.acquired += 1
        try:
            yield conn
        finally:
            pool.released += 1

    pool.acquire = _acquire
    pool.close = MagicMock()
    pool.wait_closed = AsyncMock()
    return pool, conn, cursor


# ═══════════════════════════════════════════════════════════════════════
# 1-2. get_connection / get_connection_readonly : single yield
# ═══════════════════════════════════════════════════════════════════════

class TestSingleYieldContract:

    @pytest.mark.asyncio
    async def test_get_connection_single_yield_on_user_exception(self, caplog):
        """V129 : exception depuis le user-block propage directement, pas de
        RuntimeError 'generator didn't stop after athrow()'.
        """
        import db_cloudsql
        import logging
        caplog.set_level(logging.WARNING)
        pool, _, _ = _make_pool(healthy=True)
        original_pool = db_cloudsql._pool
        db_cloudsql._pool = pool

        try:
            with pytest.raises(ValueError, match="user block error"):
                async with db_cloudsql.get_connection():
                    raise ValueError("user block error")
            # Vérifier zéro RuntimeError athrow dans les logs
            assert "generator didn't stop after athrow" not in caplog.text
            # Connexion libérée proprement (pas de leak)
            assert pool.acquired == pool.released == 1
        finally:
            db_cloudsql._pool = original_pool

    @pytest.mark.asyncio
    async def test_get_connection_readonly_single_yield_on_user_exception(self, caplog):
        """V129 : même contrat single-yield pour readonly."""
        import db_cloudsql
        import logging
        caplog.set_level(logging.WARNING)
        pool, _, _ = _make_pool(healthy=True)
        original_ro = db_cloudsql._pool_readonly
        original_main = db_cloudsql._pool
        db_cloudsql._pool_readonly = pool
        db_cloudsql._pool = MagicMock()

        try:
            with pytest.raises(ValueError, match="user block error"):
                async with db_cloudsql.get_connection_readonly():
                    raise ValueError("user block error")
            assert "generator didn't stop after athrow" not in caplog.text
            assert pool.acquired == pool.released == 1
        finally:
            db_cloudsql._pool_readonly = original_ro
            db_cloudsql._pool = original_main


# ═══════════════════════════════════════════════════════════════════════
# 3-5. _execute_with_retry : retry au niveau helper
# ═══════════════════════════════════════════════════════════════════════

class TestExecuteWithRetry:

    @pytest.mark.asyncio
    async def test_execute_with_retry_retries_once_on_first_failure(self):
        """V129 : si le 1er acquire échoue, recreate_pool est appelé puis on
        retente une fois et on réussit."""
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
                async def _op(conn):
                    return "success"
                result = await db_cloudsql._execute_with_retry(_op)
                assert result == "success"
                mock_recreate.assert_awaited_once()
                # Connexion du retry libérée proprement
                assert healthy_pool.acquired == healthy_pool.released == 1
            finally:
                db_cloudsql._pool = original_pool

    @pytest.mark.asyncio
    async def test_execute_with_retry_propagates_second_failure(self):
        """V129 : 2ᵉ échec → propagation de l'exception originale."""
        import db_cloudsql
        dead_pool, _, _ = _make_pool(healthy=False)

        original_pool = db_cloudsql._pool
        db_cloudsql._pool = dead_pool

        with patch.object(db_cloudsql, '_recreate_pool', new_callable=AsyncMock):
            # Le pool reste dead après "recreation"
            try:
                async def _op(conn):
                    return "never reached"
                with pytest.raises(RuntimeError, match="simulated pool failure"):
                    await db_cloudsql._execute_with_retry(_op)
            finally:
                db_cloudsql._pool = original_pool

    @pytest.mark.asyncio
    async def test_execute_with_retry_no_leak_on_repeated_failures(self, caplog):
        """V129 reproduction-lite : 20 échecs d'affilée ne doivent pas leak."""
        import db_cloudsql
        import logging
        caplog.set_level(logging.WARNING)
        dead_pool, _, _ = _make_pool(healthy=False)

        original_pool = db_cloudsql._pool
        db_cloudsql._pool = dead_pool

        with patch.object(db_cloudsql, '_recreate_pool', new_callable=AsyncMock):
            try:
                async def _op(conn):
                    return None
                # Boucle d'échecs (chaque appel fail 2× et propage)
                for _ in range(20):
                    with pytest.raises(RuntimeError):
                        await db_cloudsql._execute_with_retry(_op)
                # Zéro athrow RuntimeError
                assert "generator didn't stop after athrow" not in caplog.text
                # Aucune connexion n'a jamais été acquise (acquire fail avant yield)
                assert dead_pool.acquired == 0
                assert dead_pool.released == 0
            finally:
                db_cloudsql._pool = original_pool


# ═══════════════════════════════════════════════════════════════════════
# 6-9. middleware/ip_ban : debounce + semaphore + timeout + swallow
# ═══════════════════════════════════════════════════════════════════════

class TestIpBanRateLimiting:

    def setup_method(self):
        """Reset debounce + semaphore entre chaque test."""
        from middleware import ip_ban
        ip_ban._last_ban_attempt.clear()
        ip_ban._ban_semaphore = None

    @pytest.mark.asyncio
    async def test_auto_ban_debounces_same_ip_within_2s(self):
        """V129 : 2 appels successifs même IP <2s → 1 seul INSERT."""
        from middleware import ip_ban
        insert_calls = []

        async def fake_query(sql, params):
            insert_calls.append(params[0])  # ip

        with patch("db_cloudsql.async_query", fake_query):
            await ip_ban._auto_ban_ip("1.2.3.4", "auto_spam")
            await ip_ban._auto_ban_ip("1.2.3.4", "auto_spam")  # debounced
            await ip_ban._auto_ban_ip("1.2.3.4", "auto_spam")  # debounced

        assert insert_calls == ["1.2.3.4"]  # 1 seul INSERT malgré 3 appels

    @pytest.mark.asyncio
    async def test_auto_ban_semaphore_limits_concurrent_inserts(self):
        """V129 : max 5 INSERT concurrents via Semaphore."""
        from middleware import ip_ban

        concurrent_peak = {"value": 0, "current": 0}

        async def slow_query(sql, params):
            concurrent_peak["current"] += 1
            concurrent_peak["value"] = max(
                concurrent_peak["value"], concurrent_peak["current"]
            )
            await asyncio.sleep(0.05)
            concurrent_peak["current"] -= 1

        with patch("db_cloudsql.async_query", slow_query):
            tasks = [
                ip_ban._auto_ban_ip(f"10.0.0.{i}", "auto_spam")
                for i in range(20)
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        assert concurrent_peak["value"] <= ip_ban._BAN_MAX_CONCURRENT, (
            f"Peak concurrent INSERTs {concurrent_peak['value']} > max "
            f"{ip_ban._BAN_MAX_CONCURRENT}"
        )

    @pytest.mark.asyncio
    async def test_auto_ban_timeout_swallowed(self, caplog):
        """V129 : wait_for timeout → log warning, pas de raise."""
        from middleware import ip_ban
        import logging
        caplog.set_level(logging.WARNING)

        async def hanging_query(sql, params):
            await asyncio.sleep(10)  # > timeout 2s

        with patch("db_cloudsql.async_query", hanging_query):
            # Réduire le timeout pour test rapide
            with patch.object(ip_ban, "_BAN_INSERT_TIMEOUT", 0.1):
                # Ne doit pas raise
                await ip_ban._auto_ban_ip("9.9.9.9", "auto_spam")

        assert "timeout" in caplog.text.lower()
        assert "swallowed" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_auto_ban_swallows_any_exception(self, caplog):
        """V129 contrat API : any Exception → log warning, pas de raise."""
        from middleware import ip_ban
        import logging
        caplog.set_level(logging.WARNING)

        async def failing_query(sql, params):
            raise RuntimeError("generator didn't stop after athrow()")  # le vrai bug

        with patch("db_cloudsql.async_query", failing_query):
            # Ne doit JAMAIS raise
            await ip_ban._auto_ban_ip("8.8.8.8", "auto_spam")

        assert "swallowed" in caplog.text.lower()
        assert "RuntimeError" in caplog.text


# ═══════════════════════════════════════════════════════════════════════
# 10. Reproduction scénario production (log révision 00831-ccr)
# ═══════════════════════════════════════════════════════════════════════

class TestProductionReproduction:

    def setup_method(self):
        from middleware import ip_ban
        ip_ban._last_ban_attempt.clear()
        ip_ban._ban_semaphore = None

    @pytest.mark.asyncio
    async def test_reproduction_48_concurrent_scanner_no_pool_leak(self, caplog):
        """Reproduit EXACTEMENT le scénario prod (21/04/2026 03:39:38) :
          - 48 INSERT concurrents en <500ms (scanner Joomla)
          - 1 INSERT forcé à échouer (simule deadlock/lock wait timeout)
          - Vérifie qu'aucun 'generator didn't stop after athrow()' n'apparaît
          - Vérifie qu'aucune connexion n'est leak
          - Vérifie que le pool reste utilisable après la rafale
        """
        import db_cloudsql
        from middleware import ip_ban
        import logging
        caplog.set_level(logging.WARNING)

        pool, _, cursor = _make_pool(healthy=True)
        original_pool = db_cloudsql._pool
        db_cloudsql._pool = pool

        # Forcer le 5ᵉ cursor.execute à lever (simule deadlock)
        fail_ctr = {"n": 0}
        original_execute = cursor.execute

        async def flaky_execute(sql, params=None):
            fail_ctr["n"] += 1
            if fail_ctr["n"] == 5:
                raise RuntimeError("simulated deadlock")
            return await original_execute(sql, params)

        cursor.execute = flaky_execute

        try:
            # Lancer 48 auto_ban en parallèle — IPs distinctes pour bypass debounce
            tasks = [
                ip_ban._auto_ban_ip(f"195.178.110.{i}", "auto_spam")
                for i in range(48)
            ]
            # return_exceptions=True : aucune exception ne doit remonter (swallow)
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Aucune exception remontée (swallow total)
            assert all(r is None for r in results), (
                f"Exceptions remontées : {[r for r in results if r is not None]}"
            )

            # Contrat V129 : zéro RuntimeError athrow dans les logs
            assert "generator didn't stop after athrow" not in caplog.text

            # Pool intact : autant d'acquire que de release (zéro leak)
            assert pool.acquired == pool.released, (
                f"Connection leak: acquired={pool.acquired}, released={pool.released}"
            )

            # Le pool est toujours fonctionnel après la rafale
            async with db_cloudsql.get_connection() as conn:
                assert conn is not None
        finally:
            db_cloudsql._pool = original_pool
