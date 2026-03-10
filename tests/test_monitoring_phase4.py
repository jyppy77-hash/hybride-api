"""
Tests — Monitoring Phase 4
metrics_history snapshot, history endpoint, gemini breakdown, call_type/lang tracking.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════
# track_gemini_call with call_type / lang
# ═══════════════════════════════════════════════════════════════════════

class TestTrackGeminiCallBreakdown:

    @pytest.mark.asyncio
    async def test_call_type_counters(self):
        """track_gemini_call increments per-type breakdown counters."""
        mock_pipe = MagicMock()
        mock_pipe.incr = MagicMock(return_value=mock_pipe)
        mock_pipe.incrby = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=[])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        mock_redis.expire = AsyncMock()

        with patch("services.gcp_monitoring._redis", mock_redis):
            from services.gcp_monitoring import track_gemini_call
            await track_gemini_call(200.0, 100, 50, call_type="chat_loto", lang="fr")

            # Should have incr for: global calls, bt:chat_loto:calls, bl:fr:calls
            incr_calls = [str(c) for c in mock_pipe.incr.call_args_list]
            assert any("chat_loto" in c for c in incr_calls)
            assert any("bl:fr" in c for c in incr_calls)

    @pytest.mark.asyncio
    async def test_call_type_empty_skips_breakdown(self):
        """No breakdown keys when call_type is empty."""
        mock_pipe = MagicMock()
        mock_pipe.incr = MagicMock(return_value=mock_pipe)
        mock_pipe.incrby = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=[])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        mock_redis.expire = AsyncMock()

        with patch("services.gcp_monitoring._redis", mock_redis):
            from services.gcp_monitoring import track_gemini_call
            await track_gemini_call(100.0, 50, 25)

            incr_calls = [str(c) for c in mock_pipe.incr.call_args_list]
            assert not any("bt:" in c for c in incr_calls)
            assert not any("bl:" in c for c in incr_calls)

    @pytest.mark.asyncio
    async def test_error_with_call_type(self):
        """Error flag also increments per-type error counter."""
        mock_pipe = MagicMock()
        mock_pipe.incr = MagicMock(return_value=mock_pipe)
        mock_pipe.incrby = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=[])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        mock_redis.expire = AsyncMock()

        with patch("services.gcp_monitoring._redis", mock_redis):
            from services.gcp_monitoring import track_gemini_call
            await track_gemini_call(100.0, error=True, call_type="enrichment_em", lang="pt")

            incr_calls = [str(c) for c in mock_pipe.incr.call_args_list]
            # Global calls + global errors + bt:enrichment_em:calls + bt:enrichment_em:errors + bl:pt:calls
            assert mock_pipe.incr.call_count == 5

    @pytest.mark.asyncio
    async def test_lang_only(self):
        """Can pass lang without call_type."""
        mock_pipe = MagicMock()
        mock_pipe.incr = MagicMock(return_value=mock_pipe)
        mock_pipe.incrby = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=[])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        mock_redis.expire = AsyncMock()

        with patch("services.gcp_monitoring._redis", mock_redis):
            from services.gcp_monitoring import track_gemini_call
            await track_gemini_call(150.0, 100, 50, lang="de")

            incr_calls = [str(c) for c in mock_pipe.incr.call_args_list]
            assert any("bl:de" in c for c in incr_calls)
            assert not any("bt:" in c for c in incr_calls)


# ═══════════════════════════════════════════════════════════════════════
# Gemini breakdown
# ═══════════════════════════════════════════════════════════════════════

class TestGeminiBreakdown:

    @pytest.mark.asyncio
    async def test_no_redis_returns_empty(self):
        with patch("services.gcp_monitoring._redis", None):
            from services.gcp_monitoring import get_gemini_breakdown
            result = await get_gemini_breakdown()
            assert result == {"by_type": [], "by_lang": []}

    @pytest.mark.asyncio
    async def test_breakdown_structure(self):
        """Returns correct structure with by_type and by_lang."""
        # 5 types × 5 fields = 25 values for type pipe
        type_vals = [b"10", b"5000", b"1200", b"8000", b"1"] * 5
        # 6 langs × 3 fields = 18 values for lang pipe
        lang_vals = [b"5", b"2500", b"600"] * 6

        mock_pipe1 = MagicMock()
        mock_pipe1.get = MagicMock(return_value=mock_pipe1)
        mock_pipe1.execute = AsyncMock(return_value=type_vals)

        mock_pipe2 = MagicMock()
        mock_pipe2.get = MagicMock(return_value=mock_pipe2)
        mock_pipe2.execute = AsyncMock(return_value=lang_vals)

        call_count = [0]
        def mock_pipeline(**kwargs):
            call_count[0] += 1
            return mock_pipe1 if call_count[0] == 1 else mock_pipe2

        mock_redis = MagicMock()
        mock_redis.pipeline = mock_pipeline

        with patch("services.gcp_monitoring._redis", mock_redis):
            from services.gcp_monitoring import get_gemini_breakdown
            result = await get_gemini_breakdown()

            assert len(result["by_type"]) == 5
            assert result["by_type"][0]["type"] == "chat_loto"
            assert result["by_type"][0]["calls"] == 10
            assert result["by_type"][0]["tokens_in"] == 5000
            assert result["by_type"][0]["avg_ms"] == 800

            assert len(result["by_lang"]) == 6
            assert result["by_lang"][0]["lang"] == "fr"
            assert result["by_lang"][0]["calls"] == 5

    @pytest.mark.asyncio
    async def test_breakdown_redis_error(self):
        """Redis error returns empty breakdown gracefully."""
        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(side_effect=Exception("Redis down"))

        with patch("services.gcp_monitoring._redis", mock_redis):
            from services.gcp_monitoring import get_gemini_breakdown
            result = await get_gemini_breakdown()
            assert result["by_type"] == []
            assert result["by_lang"] == []


# ═══════════════════════════════════════════════════════════════════════
# Snapshot
# ═══════════════════════════════════════════════════════════════════════

class TestSnapshot:

    @pytest.mark.asyncio
    async def test_snapshot_acquires_lock(self):
        """Snapshot inserts when Redis lock is acquired."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)

        with (
            patch("services.gcp_monitoring._redis", mock_redis),
            patch("services.gcp_monitoring.db_cloudsql") as mock_db,
        ):
            mock_db.async_query = AsyncMock()
            from services.gcp_monitoring import _maybe_snapshot
            payload = {
                "metrics": {"requests_per_second": 1.5, "error_rate_5xx": 0.001},
                "gemini": {"calls_today": 10, "avg_response_time_ms": 500},
                "costs": {"cloud_run_today_eur": 2.0, "total_today_eur": 3.5},
            }
            await _maybe_snapshot(payload)
            mock_db.async_query.assert_called_once()
            sql = mock_db.async_query.call_args[0][0]
            assert "INSERT INTO metrics_history" in sql

    @pytest.mark.asyncio
    async def test_snapshot_skips_when_locked(self):
        """Snapshot is skipped when cooldown lock is active."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=False)

        with (
            patch("services.gcp_monitoring._redis", mock_redis),
            patch("services.gcp_monitoring.db_cloudsql") as mock_db,
        ):
            mock_db.async_query = AsyncMock()
            from services.gcp_monitoring import _maybe_snapshot
            await _maybe_snapshot({"metrics": {}, "gemini": {}, "costs": {}})
            mock_db.async_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_snapshot_no_redis(self):
        """Snapshot is noop without Redis."""
        with (
            patch("services.gcp_monitoring._redis", None),
            patch("services.gcp_monitoring.db_cloudsql") as mock_db,
        ):
            mock_db.async_query = AsyncMock()
            from services.gcp_monitoring import _maybe_snapshot
            await _maybe_snapshot({"metrics": {}, "gemini": {}, "costs": {}})
            mock_db.async_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_snapshot_db_error_graceful(self):
        """DB error in snapshot doesn't raise."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)

        with (
            patch("services.gcp_monitoring._redis", mock_redis),
            patch("services.gcp_monitoring.db_cloudsql") as mock_db,
        ):
            mock_db.async_query = AsyncMock(side_effect=Exception("DB error"))
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
        import routes.admin as admin_mod
        importlib.reload(admin_mod)
        import main as main_mod
        importlib.reload(main_mod)
        from rate_limit import limiter
        limiter.reset()
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
# Call types constants
# ═══════════════════════════════════════════════════════════════════════

class TestConstants:

    def test_call_types_list(self):
        from services.gcp_monitoring import _CALL_TYPES
        assert "chat_loto" in _CALL_TYPES
        assert "chat_em" in _CALL_TYPES
        assert "enrichment_loto" in _CALL_TYPES
        assert "enrichment_em" in _CALL_TYPES
        assert "meta_analyse" in _CALL_TYPES

    def test_langs_list(self):
        from services.gcp_monitoring import _LANGS
        assert set(_LANGS) == {"fr", "en", "es", "pt", "de", "nl"}

    def test_snapshot_cooldown(self):
        from services.gcp_monitoring import _SNAPSHOT_COOLDOWN
        assert _SNAPSHOT_COOLDOWN == 300
