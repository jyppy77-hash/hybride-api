"""
Tests — Monitoring Phase 4
gemini_tracking DB persistence, breakdown, history, cleanup.
"""

import pytest
from contextlib import asynccontextmanager
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime

from services.gcp_monitoring import (
    track_gemini_call,
    _get_gemini_counters,
    get_gemini_breakdown,
    cleanup_gemini_tracking,
    cleanup_event_log,
    cleanup_chat_log,
    cleanup_metrics_history,
    get_metrics_history,
    _LOCAL_CACHE,
    _CALL_TYPES,
    _LANGS,
    _SNAPSHOT_COOLDOWN,
    _local_cache_get,
    _local_cache_set,
)


# ═══════════════════════════════════════════════════════════════════════
# track_gemini_call — DB insert
# ═══════════════════════════════════════════════════════════════════════

class TestTrackGeminiCallDB:

    @pytest.mark.asyncio
    async def test_inserts_with_call_type_and_lang(self):
        import asyncio
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            await track_gemini_call(200.0, 100, 50, call_type="chat_loto", lang="fr")
            await asyncio.sleep(0.05)
            mock_db.async_query.assert_called_once()
            sql, params = mock_db.async_query.call_args[0]
            assert "INSERT INTO gemini_tracking" in sql
            assert params[0] == "chat_loto"
            assert params[1] == "fr"
            assert params[2] == 100   # tokens_in
            assert params[3] == 50    # tokens_out
            assert params[4] == 200   # duration_ms
            assert params[5] == 0     # is_error

    @pytest.mark.asyncio
    async def test_empty_call_type_inserts_empty_string(self):
        import asyncio
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            await track_gemini_call(100.0, 50, 25)
            await asyncio.sleep(0.05)
            _, params = mock_db.async_query.call_args[0]
            assert params[0] == ""  # call_type
            assert params[1] == ""  # lang

    @pytest.mark.asyncio
    async def test_error_flag_set(self):
        import asyncio
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            await track_gemini_call(100.0, error=True, call_type="enrichment_em", lang="pt")
            await asyncio.sleep(0.05)
            _, params = mock_db.async_query.call_args[0]
            assert params[0] == "enrichment_em"
            assert params[1] == "pt"
            assert params[5] == 1  # is_error

    @pytest.mark.asyncio
    async def test_lang_only_no_type(self):
        import asyncio
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            await track_gemini_call(150.0, 100, 50, lang="de")
            await asyncio.sleep(0.05)
            _, params = mock_db.async_query.call_args[0]
            assert params[0] == ""    # call_type empty
            assert params[1] == "de"  # lang set

    @pytest.mark.asyncio
    async def test_db_error_does_not_raise(self):
        import asyncio
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(side_effect=Exception("DB error"))
            await track_gemini_call(100.0, 50, 25, call_type="chat_loto")
            await asyncio.sleep(0.05)
            # Should not raise


# ═══════════════════════════════════════════════════════════════════════
# _get_gemini_counters — DB SELECT with local cache
# ═══════════════════════════════════════════════════════════════════════

class TestGeminiCountersDB:

    def setup_method(self):
        _LOCAL_CACHE.clear()

    @pytest.mark.asyncio
    async def test_reads_from_db(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "calls": 42, "errors": 2, "tokens_in": 10000, "tokens_out": 3000, "total_ms": 50000,
            })
            counters = await _get_gemini_counters()
            assert counters["calls"] == 42
            assert counters["errors"] == 2
            assert counters["tokens_in"] == 10000
            assert counters["tokens_out"] == 3000
            assert counters["total_ms"] == 50000
            sql = mock_db.async_fetchone.call_args[0][0]
            assert "CURDATE()" in sql

    @pytest.mark.asyncio
    async def test_cached_locally_60s(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "calls": 5, "errors": 0, "tokens_in": 100, "tokens_out": 50, "total_ms": 500,
            })
            first = await _get_gemini_counters()
            second = await _get_gemini_counters()
            assert first == second
            assert mock_db.async_fetchone.call_count == 1  # only one DB call

    @pytest.mark.asyncio
    async def test_db_error_returns_defaults(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(side_effect=Exception("Connection lost"))
            counters = await _get_gemini_counters()
            assert counters["calls"] == 0
            assert counters["errors"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Gemini breakdown — DB GROUP BY
# ═══════════════════════════════════════════════════════════════════════

class TestGeminiBreakdown:

    def setup_method(self):
        _LOCAL_CACHE.clear()

    @pytest.mark.asyncio
    async def test_breakdown_by_type(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=[
                # by_type query
                [
                    {"call_type": "chat_loto", "calls": 10, "tokens_in": 5000, "tokens_out": 1200, "total_ms": 8000, "errors": 1},
                    {"call_type": "chat_em", "calls": 5, "tokens_in": 2000, "tokens_out": 600, "total_ms": 3000, "errors": 0},
                ],
                # by_lang query
                [
                    {"lang": "fr", "calls": 8, "tokens_in": 4000, "tokens_out": 1000},
                    {"lang": "en", "calls": 7, "tokens_in": 3000, "tokens_out": 800},
                ],
            ])
            result = await get_gemini_breakdown()

            assert len(result["by_type"]) == 5
            chat_loto = next(e for e in result["by_type"] if e["type"] == "chat_loto")
            assert chat_loto["calls"] == 10
            assert chat_loto["tokens_in"] == 5000
            assert chat_loto["avg_ms"] == 800
            assert chat_loto["errors"] == 1

            # Types not in DB should be zero
            enrichment_loto = next(e for e in result["by_type"] if e["type"] == "enrichment_loto")
            assert enrichment_loto["calls"] == 0

    @pytest.mark.asyncio
    async def test_breakdown_by_lang(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=[
                [],  # no type data
                [{"lang": "fr", "calls": 3, "tokens_in": 1000, "tokens_out": 300}],
            ])
            result = await get_gemini_breakdown()

            assert len(result["by_lang"]) == 6
            fr = next(e for e in result["by_lang"] if e["lang"] == "fr")
            assert fr["calls"] == 3
            assert fr["tokens_in"] == 1000
            # Langs not in DB should be zero
            de = next(e for e in result["by_lang"] if e["lang"] == "de")
            assert de["calls"] == 0

    @pytest.mark.asyncio
    async def test_breakdown_db_error(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=Exception("DB down"))
            result = await get_gemini_breakdown()
            assert result["by_type"] == []
            assert result["by_lang"] == []

    @pytest.mark.asyncio
    async def test_breakdown_cached_60s(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=[
                [{"call_type": "chat_loto", "calls": 1, "tokens_in": 100, "tokens_out": 50, "total_ms": 200, "errors": 0}],
                [{"lang": "fr", "calls": 1, "tokens_in": 100, "tokens_out": 50}],
            ])
            first = await get_gemini_breakdown()
            second = await get_gemini_breakdown()
            assert first == second
            assert mock_db.async_fetchall.call_count == 2  # two queries (type + lang) on first call only


# ═══════════════════════════════════════════════════════════════════════
# Local cache helper
# ═══════════════════════════════════════════════════════════════════════

class TestLocalCache:

    def setup_method(self):
        _LOCAL_CACHE.clear()

    def test_get_miss(self):
        assert _local_cache_get("nonexistent") is None

    def test_set_and_get(self):
        _local_cache_set("key1", {"foo": "bar"})
        assert _local_cache_get("key1") == {"foo": "bar"}

    def test_expired_returns_none(self):
        import time
        _LOCAL_CACHE["expired"] = (time.monotonic() - 120, "old_value")
        assert _local_cache_get("expired") is None


# ═══════════════════════════════════════════════════════════════════════
# Cleanup (90-day retention)
# ═══════════════════════════════════════════════════════════════════════

def _mock_cleanup_conn(rowcounts):
    """Create a mock get_connection that yields a cursor with successive rowcounts.

    I11 V66: cleanup now uses batched DELETE via get_connection + cursor.rowcount.
    """
    call_idx = {"i": 0}

    @asynccontextmanager
    async def _cm():
        cursor = AsyncMock()
        idx = call_idx["i"]
        cursor.rowcount = rowcounts[idx] if idx < len(rowcounts) else 0
        call_idx["i"] += 1
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn

    return _cm


class TestGeminiCleanup:

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_rows(self):
        """Batched cleanup deletes rows and returns total."""
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _mock_cleanup_conn([150, 0])
            mock_aio.sleep = AsyncMock()
            count = await cleanup_gemini_tracking(90)
            assert count == 150

    @pytest.mark.asyncio
    async def test_cleanup_nothing_to_delete(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _mock_cleanup_conn([0])
            mock_aio.sleep = AsyncMock()
            count = await cleanup_gemini_tracking(90)
            assert count == 0

    @pytest.mark.asyncio
    async def test_cleanup_db_error(self):
        @asynccontextmanager
        async def _err_cm():
            raise Exception("DB error")
            yield  # noqa: unreachable

        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _err_cm
            mock_aio.sleep = AsyncMock()
            count = await cleanup_gemini_tracking(90)
            assert count == 0

    @pytest.mark.asyncio
    async def test_cleanup_custom_days(self):
        """Batched cleanup passes days param in SQL."""
        captured_params = []

        @asynccontextmanager
        async def _cap_cm():
            cursor = AsyncMock()
            cursor.rowcount = 0

            async def _exec(sql, params=None):
                captured_params.append(params)

            cursor.execute = _exec
            conn = AsyncMock()
            conn.cursor = AsyncMock(return_value=cursor)
            yield conn

        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _cap_cm
            mock_aio.sleep = AsyncMock()
            await cleanup_gemini_tracking(30)
            assert captured_params[0] == (30,)


# ═══════════════════════════════════════════════════════════════════════
# Snapshot
# ═══════════════════════════════════════════════════════════════════════

def _mock_cursor(rowcount=1):
    """Create a mock async cursor with given rowcount for atomic UPDATE."""
    cur = AsyncMock()
    cur.rowcount = rowcount
    return cur


def _mock_conn(cursor):
    """Create a mock async connection context manager."""
    conn = AsyncMock()
    conn.cursor = AsyncMock(return_value=cursor)
    return conn


class _FakeConnCtx:
    """Fake async context manager for db_cloudsql.get_connection()."""
    def __init__(self, conn):
        self._conn = conn
    async def __aenter__(self):
        return self._conn
    async def __aexit__(self, *args):
        pass


class TestSnapshot:

    @pytest.mark.asyncio
    async def test_snapshot_acquires_lock_and_inserts(self):
        """Snapshot inserts when atomic UPDATE claims lock (rowcount=1)."""
        cur = _mock_cursor(rowcount=1)
        conn = _mock_conn(cur)
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            mock_db.get_connection = MagicMock(return_value=_FakeConnCtx(conn))
            from services.gcp_monitoring import _maybe_snapshot
            payload = {
                "metrics": {"requests_per_second": 1.5, "error_rate_5xx": 0.001},
                "gemini": {"calls_today": 10, "avg_response_time_ms": 500},
                "costs": {"cloud_run_today_eur": 2.0, "total_today_eur": 3.5},
            }
            await _maybe_snapshot(payload)
            # INSERT IGNORE (lock row) + INSERT (history)
            assert mock_db.async_query.call_count == 2
            last_sql = mock_db.async_query.call_args_list[-1][0][0]
            assert "INSERT INTO metrics_history" in last_sql
            # Atomic UPDATE was called on cursor
            cur.execute.assert_called_once()
            update_sql = cur.execute.call_args[0][0]
            assert "UPDATE metrics_snapshot_lock" in update_sql
            assert "locked_until <= NOW()" in update_sql

    @pytest.mark.asyncio
    async def test_snapshot_skips_when_locked(self):
        """Snapshot is skipped when atomic UPDATE claims 0 rows (lock active)."""
        cur = _mock_cursor(rowcount=0)
        conn = _mock_conn(cur)
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            mock_db.get_connection = MagicMock(return_value=_FakeConnCtx(conn))
            from services.gcp_monitoring import _maybe_snapshot
            await _maybe_snapshot({"metrics": {}, "gemini": {}, "costs": {}})
            # Only INSERT IGNORE lock row, atomic UPDATE got 0 rows → stop
            assert mock_db.async_query.call_count == 1  # only the INSERT IGNORE

    @pytest.mark.asyncio
    async def test_snapshot_works_without_redis(self):
        """Snapshot works even without Redis (MySQL atomic lock)."""
        cur = _mock_cursor(rowcount=1)
        conn = _mock_conn(cur)
        with (
            patch("services.cache._redis", None),
            patch("services.gcp_monitoring.db_cloudsql") as mock_db,
        ):
            mock_db.async_query = AsyncMock()
            mock_db.get_connection = MagicMock(return_value=_FakeConnCtx(conn))
            from services.gcp_monitoring import _maybe_snapshot
            await _maybe_snapshot({
                "metrics": {"requests_per_second": 1.0},
                "gemini": {"calls_today": 5},
                "costs": {"total_today_eur": 1.0},
            })
            # Should still insert into metrics_history
            assert mock_db.async_query.call_count == 2
            last_sql = mock_db.async_query.call_args_list[-1][0][0]
            assert "INSERT INTO metrics_history" in last_sql

    @pytest.mark.asyncio
    async def test_snapshot_db_error_graceful(self):
        """DB error in snapshot doesn't raise."""
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(side_effect=Exception("DB error"))
            mock_db.get_connection = MagicMock(side_effect=Exception("DB error"))
            from services.gcp_monitoring import _maybe_snapshot
            # Should not raise
            await _maybe_snapshot({"metrics": {}, "gemini": {}, "costs": {}})


# ═══════════════════════════════════════════════════════════════════════
# History query
# ═══════════════════════════════════════════════════════════════════════

class TestMetricsHistory:

    @pytest.mark.asyncio
    async def test_24h_no_group_by(self):
        """24h period uses raw rows without GROUP BY."""
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[
                {"ts_label": "2026-03-10 14:30", "requests_per_second": 1.5, "error_rate_5xx": 0.0},
            ])
            from services.gcp_monitoring import get_metrics_history
            result = await get_metrics_history("24h")
            sql = mock_db.async_fetchall.call_args[0][0]
            assert "GROUP BY" not in sql
            assert "24 HOUR" in sql
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_7d_uses_group_by(self):
        """7d period aggregates by hour."""
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            from services.gcp_monitoring import get_metrics_history
            await get_metrics_history("7d")
            sql = mock_db.async_fetchall.call_args[0][0]
            assert "GROUP BY ts_label" in sql
            assert "7 DAY" in sql

    @pytest.mark.asyncio
    async def test_30d_uses_group_by(self):
        """30d period aggregates by hour."""
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            from services.gcp_monitoring import get_metrics_history
            await get_metrics_history("30d")
            sql = mock_db.async_fetchall.call_args[0][0]
            assert "GROUP BY ts_label" in sql
            assert "30 DAY" in sql

    @pytest.mark.asyncio
    async def test_db_error_returns_empty(self):
        """DB error returns empty list."""
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=Exception("DB down"))
            from services.gcp_monitoring import get_metrics_history
            result = await get_metrics_history("24h")
            assert result == []

    @pytest.mark.asyncio
    async def test_values_are_rounded(self):
        """Numeric values are rounded to 4 decimals."""
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[
                {"ts_label": "2026-03-10 14:00", "requests_per_second": 1.55555555, "error_rate_5xx": 0.00123456},
            ])
            from services.gcp_monitoring import get_metrics_history
            result = await get_metrics_history("24h")
            assert result[0]["requests_per_second"] == 1.5556
            assert result[0]["error_rate_5xx"] == 0.0012


# ═══════════════════════════════════════════════════════════════════════
# Admin routes (history + breakdown)
# ═══════════════════════════════════════════════════════════════════════

import os
from starlette.testclient import TestClient

_TEST_TOKEN = "test_mon_p4_token_1234567890"
_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "ADMIN_TOKEN": _TEST_TOKEN,
})


def _get_client():
    with _db_env, _static_patch, _static_call:
        import importlib
        import rate_limit as rl_mod
        importlib.reload(rl_mod)
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


class TestAdminHistoryRoute:

    def test_history_endpoint_returns_json(self):
        client = _authed_client()
        with patch("services.gcp_monitoring.get_metrics_history", new_callable=AsyncMock, return_value=[]):
            resp = client.get("/admin/api/gcp-metrics/history?period=24h")
            assert resp.status_code == 200
            data = resp.json()
            assert "period" in data
            assert "points" in data
            assert data["period"] == "24h"

    def test_history_invalid_period_defaults_24h(self):
        client = _authed_client()
        with patch("services.gcp_monitoring.get_metrics_history", new_callable=AsyncMock, return_value=[]):
            resp = client.get("/admin/api/gcp-metrics/history?period=invalid")
            assert resp.status_code == 200
            assert resp.json()["period"] == "24h"

    def test_history_no_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/gcp-metrics/history")
        assert resp.status_code == 401

    def test_breakdown_endpoint_returns_json(self):
        client = _authed_client()
        with patch("services.gcp_monitoring.get_gemini_breakdown", new_callable=AsyncMock,
                    return_value={"by_type": [], "by_lang": []}):
            resp = client.get("/admin/api/gemini-breakdown")
            assert resp.status_code == 200
            data = resp.json()
            assert "by_type" in data
            assert "by_lang" in data

    def test_breakdown_no_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/gemini-breakdown")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════

class TestConstants:

    def test_call_types_list(self):
        assert "chat_loto" in _CALL_TYPES
        assert "chat_em" in _CALL_TYPES
        assert "enrichment_loto" in _CALL_TYPES
        assert "enrichment_em" in _CALL_TYPES
        assert "meta_analyse" in _CALL_TYPES

    def test_langs_list(self):
        assert set(_LANGS) == {"fr", "en", "es", "pt", "de", "nl"}

    def test_snapshot_cooldown(self):
        assert _SNAPSHOT_COOLDOWN == 300


# ═══════════════════════════════════════════════════════════════════════
# Alerting cooldown (still in-memory — unrelated to Gemini tracking)
# ═══════════════════════════════════════════════════════════════════════

class TestAlertingCooldown:

    @pytest.mark.asyncio
    async def test_alerting_cooldown_without_redis(self):
        """Alerting cooldown works in-memory when Redis is None."""
        from services.alerting import _is_cooled_down, _set_cooldown, _mem_cooldowns
        _mem_cooldowns.clear()
        with patch("services.cache._redis", None):
            assert not await _is_cooled_down("test_key", 900)
            await _set_cooldown("test_key", 900)
            assert await _is_cooled_down("test_key", 900)


# ═══════════════════════════════════════════════════════════════════════
# R-3: Decimal values in metrics_history (SUM returns Decimal from MySQL)
# ═══════════════════════════════════════════════════════════════════════

class TestHistoryDecimalHandling:

    def setup_method(self):
        _LOCAL_CACHE.clear()

    @pytest.mark.asyncio
    async def test_decimal_values_converted_to_float(self):
        """SUM() of INT columns returns Decimal — must be serialized as float, not string."""
        from decimal import Decimal
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[
                {
                    "ts_label": "2026-03-10 14:00",
                    "requests_per_second": 1.5,
                    "error_rate_5xx": 0.001,
                    "gemini_errors": Decimal("3"),
                    "gemini_calls": 42,
                    "gemini_tokens_in": Decimal("5000"),
                    "gemini_tokens_out": Decimal("1200"),
                    "latency_p50_ms": 45.0,
                    "latency_p95_ms": 850.0,
                    "latency_p99_ms": 2100.0,
                    "active_instances": 2,
                    "cpu_utilization": 0.35,
                    "memory_utilization": 0.42,
                    "gemini_avg_ms": 500.0,
                    "cost_cloud_run_eur": 2.0,
                    "cost_cloud_sql_eur": 0.85,
                    "cost_gemini_eur": 0.01,
                    "cost_total_eur": 2.86,
                },
            ])
            result = await get_metrics_history("7d")
            row = result[0]
            # Decimal values must become floats, not strings
            assert isinstance(row["gemini_errors"], float)
            assert row["gemini_errors"] == 3.0
            assert isinstance(row["gemini_tokens_in"], float)
            assert row["gemini_tokens_in"] == 5000.0
            assert isinstance(row["gemini_tokens_out"], float)
            assert row["gemini_tokens_out"] == 1200.0
            # ts_label stays as string
            assert row["ts_label"] == "2026-03-10 14:00"
            # Regular float stays as float
            assert isinstance(row["requests_per_second"], float)

    @pytest.mark.asyncio
    async def test_mixed_types_all_numeric(self):
        """int, float, and Decimal all end up as float in output."""
        from decimal import Decimal
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[
                {
                    "ts_label": "2026-03-10 15:00",
                    "requests_per_second": Decimal("2.3456"),
                    "error_rate_5xx": 0.0,
                    "gemini_errors": Decimal("0"),
                    "gemini_calls": 10,
                    "gemini_tokens_in": 1000,
                    "gemini_tokens_out": 500,
                    "latency_p50_ms": Decimal("42.1234"),
                    "latency_p95_ms": 100.0,
                    "latency_p99_ms": 200.0,
                    "active_instances": 1,
                    "cpu_utilization": Decimal("0.12345678"),
                    "memory_utilization": 0.2,
                    "gemini_avg_ms": 300.0,
                    "cost_cloud_run_eur": 1.0,
                    "cost_cloud_sql_eur": 0.85,
                    "cost_gemini_eur": 0.0,
                    "cost_total_eur": Decimal("1.85"),
                },
            ])
            result = await get_metrics_history("30d")
            row = result[0]
            # Decimal rounded to 4 decimals
            assert row["requests_per_second"] == 2.3456
            assert row["latency_p50_ms"] == 42.1234
            assert row["cpu_utilization"] == 0.1235  # rounded
            assert row["cost_total_eur"] == 1.85
            # All numeric values are float
            for k, v in row.items():
                if k != "ts_label":
                    assert isinstance(v, float), f"{k} should be float, got {type(v)}"


# ═══════════════════════════════════════════════════════════════════════
# R-5: cleanup_metrics_history (retention 90 days)
# ═══════════════════════════════════════════════════════════════════════

class TestMetricsHistoryCleanup:

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_rows(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _mock_cleanup_conn([200, 0])
            mock_aio.sleep = AsyncMock()
            count = await cleanup_metrics_history(90)
            assert count == 200

    @pytest.mark.asyncio
    async def test_cleanup_nothing_to_delete(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _mock_cleanup_conn([0])
            mock_aio.sleep = AsyncMock()
            count = await cleanup_metrics_history(90)
            assert count == 0

    @pytest.mark.asyncio
    async def test_cleanup_db_error(self):
        @asynccontextmanager
        async def _err_cm():
            raise Exception("DB error")
            yield  # noqa: unreachable

        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _err_cm
            mock_aio.sleep = AsyncMock()
            count = await cleanup_metrics_history(90)
            assert count == 0

    @pytest.mark.asyncio
    async def test_cleanup_custom_days(self):
        captured_params = []

        @asynccontextmanager
        async def _cap_cm():
            cursor = AsyncMock()
            cursor.rowcount = 0

            async def _exec(sql, params=None):
                captured_params.append(params)

            cursor.execute = _exec
            conn = AsyncMock()
            conn.cursor = AsyncMock(return_value=cursor)
            yield conn

        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _cap_cm
            mock_aio.sleep = AsyncMock()
            await cleanup_metrics_history(30)
            assert captured_params[0] == (30,)


# ═══════════════════════════════════════════════════════════════════════
# M5: cleanup_event_log (retention 90 days)
# ═══════════════════════════════════════════════════════════════════════

class TestEventLogCleanup:

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_rows(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _mock_cleanup_conn([500, 0])
            mock_aio.sleep = AsyncMock()
            count = await cleanup_event_log(90)
            assert count == 500

    @pytest.mark.asyncio
    async def test_cleanup_preserves_recent_rows(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _mock_cleanup_conn([0])
            mock_aio.sleep = AsyncMock()
            count = await cleanup_event_log(90)
            assert count == 0

    @pytest.mark.asyncio
    async def test_cleanup_days_zero_edge_case(self):
        """days=0 is passed correctly to SQL params."""
        captured_params = []
        call_idx = {"i": 0}

        @asynccontextmanager
        async def _cap_cm():
            cursor = AsyncMock()
            idx = call_idx["i"]
            cursor.rowcount = 1000 if idx == 0 else 0
            call_idx["i"] += 1

            _orig_execute = cursor.execute

            async def _exec(sql, params=None):
                captured_params.append(params)

            cursor.execute = _exec
            conn = AsyncMock()
            conn.cursor = AsyncMock(return_value=cursor)
            yield conn

        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _cap_cm
            mock_aio.sleep = AsyncMock()
            count = await cleanup_event_log(0)
            assert count == 1000
            assert captured_params[0] == (0,)


# ═══════════════════════════════════════════════════════════════════════
# V46: cleanup_chat_log (retention 90 days)
# ═══════════════════════════════════════════════════════════════════════

class TestChatLogCleanup:

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_rows(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _mock_cleanup_conn([200, 0])
            mock_aio.sleep = AsyncMock()
            count = await cleanup_chat_log(90)
            assert count == 200

    @pytest.mark.asyncio
    async def test_cleanup_preserves_recent_rows(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _mock_cleanup_conn([0])
            mock_aio.sleep = AsyncMock()
            count = await cleanup_chat_log(90)
            assert count == 0

    @pytest.mark.asyncio
    async def test_cleanup_handles_db_error(self):
        @asynccontextmanager
        async def _err_cm():
            raise Exception("DB down")
            yield  # noqa: unreachable

        with patch("services.gcp_monitoring.db_cloudsql") as mock_db, \
             patch("services.gcp_monitoring.asyncio") as mock_aio:
            mock_db.get_connection = _err_cm
            mock_aio.sleep = AsyncMock()
            count = await cleanup_chat_log(90)
            assert count == 0
