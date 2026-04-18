"""
Tests — services/bot_feeds_monitor.py (V122 Phase 2/4 BONUS Q8).

Covers:
- log_refresh_result() fail-safe INSERT
- get_feeds_status() health flags (green/orange/red)
- get_ai_bots_stats() aggregation
- flush_ai_bot_counters() batches in-memory counters to DB
"""

from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import AsyncMock, patch

from services.bot_feeds_monitor import (
    log_refresh_result,
    get_feeds_status,
    get_ai_bots_stats,
    flush_ai_bot_counters,
    get_blocked_bots_stats,
    get_ai_bots_timeline,
    get_bot_dashboard_kpis,
)


# ═══════════════════════════════════════════════════════════════════════
# log_refresh_result
# ═══════════════════════════════════════════════════════════════════════

class TestLogRefreshResult:

    @pytest.mark.asyncio
    async def test_log_ok_status(self):
        with patch("db_cloudsql.async_query", new=AsyncMock()) as mock_q:
            await log_refresh_result("googlebot", "ok", 127)
            mock_q.assert_awaited_once()
            call_args = mock_q.call_args
            assert "bot_feed_refresh_log" in call_args[0][0]
            assert call_args[0][1] == ("googlebot", "ok", 127, None)

    @pytest.mark.asyncio
    async def test_log_error_status(self):
        with patch("db_cloudsql.async_query", new=AsyncMock()) as mock_q:
            await log_refresh_result("bingbot", "error", 0, "timeout after 10s")
            mock_q.assert_awaited_once()
            assert mock_q.call_args[0][1] == ("bingbot", "error", 0, "timeout after 10s")

    @pytest.mark.asyncio
    async def test_log_fails_silently_on_db_error(self):
        """Fail-safe: DB errors must not propagate."""
        with patch("db_cloudsql.async_query", new=AsyncMock(side_effect=Exception("db down"))):
            # Must not raise
            await log_refresh_result("applebot", "ok", 12)

    @pytest.mark.asyncio
    async def test_error_msg_truncated_to_500(self):
        with patch("db_cloudsql.async_query", new=AsyncMock()) as mock_q:
            long_err = "x" * 1000
            await log_refresh_result("gptbot", "error", 0, long_err)
            mock_q.assert_awaited_once()
            params = mock_q.call_args[0][1]
            assert len(params[3]) == 500


# ═══════════════════════════════════════════════════════════════════════
# get_feeds_status — health flags
# ═══════════════════════════════════════════════════════════════════════

class TestGetFeedsStatus:

    @pytest.mark.asyncio
    async def test_empty_db_all_red(self):
        """No refresh log rows → all 9 sources return red health."""
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=[])):
            result = await get_feeds_status()
            assert result["summary"]["total"] == 9
            assert result["summary"]["red"] == 9
            assert result["summary"]["green"] == 0
            for f in result["feeds"]:
                assert f["health"] == "red"
                assert f["last_refresh"] is None

    @pytest.mark.asyncio
    async def test_fresh_refresh_green(self):
        now = datetime.now(timezone.utc)
        mock_rows = [
            {"source": "googlebot", "ts": now - timedelta(hours=2),
             "status": "ok", "cidrs_count": 127, "error_msg": None},
        ]
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=mock_rows)):
            result = await get_feeds_status()
            googlebot = next(f for f in result["feeds"] if f["source"] == "googlebot")
            assert googlebot["health"] == "green"
            assert googlebot["cidrs_count"] == 127
            assert googlebot["age_hours"] < 3

    @pytest.mark.asyncio
    async def test_12_to_24h_orange(self):
        now = datetime.now(timezone.utc)
        mock_rows = [
            {"source": "bingbot", "ts": now - timedelta(hours=15),
             "status": "ok", "cidrs_count": 5, "error_msg": None},
        ]
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=mock_rows)):
            result = await get_feeds_status()
            bingbot = next(f for f in result["feeds"] if f["source"] == "bingbot")
            assert bingbot["health"] == "orange"

    @pytest.mark.asyncio
    async def test_over_24h_red(self):
        now = datetime.now(timezone.utc)
        mock_rows = [
            {"source": "applebot", "ts": now - timedelta(hours=30),
             "status": "ok", "cidrs_count": 12, "error_msg": None},
        ]
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=mock_rows)):
            result = await get_feeds_status()
            applebot = next(f for f in result["feeds"] if f["source"] == "applebot")
            assert applebot["health"] == "red"

    @pytest.mark.asyncio
    async def test_last_error_orange_even_if_recent(self):
        """Recent refresh with status=error must flag orange."""
        now = datetime.now(timezone.utc)
        mock_rows = [
            {"source": "gptbot", "ts": now - timedelta(minutes=30),
             "status": "error", "cidrs_count": 0, "error_msg": "timeout"},
        ]
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=mock_rows)):
            result = await get_feeds_status()
            gpt = next(f for f in result["feeds"] if f["source"] == "gptbot")
            assert gpt["health"] == "orange"
            assert gpt["last_status"] == "error"


# ═══════════════════════════════════════════════════════════════════════
# get_ai_bots_stats
# ═══════════════════════════════════════════════════════════════════════

class TestGetAiBotsStats:

    @pytest.mark.asyncio
    async def test_empty_returns_zero(self):
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=[])):
            result = await get_ai_bots_stats(hours=24)
            assert result["total_hits"] == 0
            assert result["bots"] == []
            assert result["period_hours"] == 24

    @pytest.mark.asyncio
    async def test_groupby_canonical(self):
        mock_rows = [
            {"canonical_name": "Googlebot", "hits": 1247},
            {"canonical_name": "ClaudeBot", "hits": 89},
            {"canonical_name": "GPTBot", "hits": 42},
        ]
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=mock_rows)):
            result = await get_ai_bots_stats(hours=24)
            assert result["total_hits"] == 1247 + 89 + 42
            assert len(result["bots"]) == 3
            assert result["bots"][0]["canonical_name"] == "Googlebot"

    @pytest.mark.asyncio
    async def test_hours_clamped(self):
        """hours out of range → clamped to [1, 720]."""
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=[])):
            result = await get_ai_bots_stats(hours=0)
            assert result["period_hours"] == 1
            result = await get_ai_bots_stats(hours=9999)
            assert result["period_hours"] == 24 * 30


# ═══════════════════════════════════════════════════════════════════════
# flush_ai_bot_counters
# ═══════════════════════════════════════════════════════════════════════

class TestFlushAiBotCounters:

    def setup_method(self):
        from config.ai_bots import reset_session_counters
        reset_session_counters()

    @pytest.mark.asyncio
    async def test_flush_empty_noop(self):
        """No counters → no DB calls."""
        with patch("db_cloudsql.async_query", new=AsyncMock()) as mock_q:
            await flush_ai_bot_counters()
            mock_q.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_flush_batches_counters(self):
        from config.ai_bots import record_ai_bot_access, get_session_counters
        record_ai_bot_access("Googlebot")
        record_ai_bot_access("Googlebot")
        record_ai_bot_access("ClaudeBot")
        with patch("db_cloudsql.async_query", new=AsyncMock()) as mock_q:
            await flush_ai_bot_counters()
            # 2 distinct canonical names → 2 INSERTs
            assert mock_q.await_count == 2
        # Counters reset after successful flush
        assert get_session_counters() == {}

    @pytest.mark.asyncio
    async def test_flush_preserves_counters_on_db_error(self):
        """Counters must NOT reset if DB write fails — retry next cycle."""
        from config.ai_bots import record_ai_bot_access, get_session_counters
        record_ai_bot_access("Googlebot")
        with patch("db_cloudsql.async_query", new=AsyncMock(side_effect=Exception("db down"))):
            await flush_ai_bot_counters()
        # Counter still there for next retry
        assert get_session_counters().get("Googlebot") == 1


# ═══════════════════════════════════════════════════════════════════════
# Admin endpoint — /admin/api/bot-feeds-status + /admin/api/ai-bots/stats
# ═══════════════════════════════════════════════════════════════════════

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)


# ═══════════════════════════════════════════════════════════════════════
# V123 Phase 2.5 — get_blocked_bots_stats
# ═══════════════════════════════════════════════════════════════════════

class TestGetBlockedBotsStats:

    @pytest.mark.asyncio
    async def test_empty_returns_zero(self):
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=[])):
            result = await get_blocked_bots_stats(hours=24)
            assert result["total_blocked"] == 0
            assert result["blocked_bots"] == []
            assert result["period_hours"] == 24

    @pytest.mark.asyncio
    async def test_groupby_canonical_blocked_only(self):
        from datetime import datetime, timezone
        mock_rows = [
            {"canonical_name": "Ahrefsbot", "hits": 18,
             "last_seen": datetime.now(timezone.utc)},
            {"canonical_name": "Semrushbot", "hits": 7,
             "last_seen": datetime.now(timezone.utc)},
        ]
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=mock_rows)):
            result = await get_blocked_bots_stats(hours=24)
            assert result["total_blocked"] == 25
            assert len(result["blocked_bots"]) == 2
            assert result["blocked_bots"][0]["canonical_name"] == "Ahrefsbot"

    @pytest.mark.asyncio
    async def test_hours_clamped(self):
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=[])):
            result = await get_blocked_bots_stats(hours=0)
            assert result["period_hours"] == 1
            result = await get_blocked_bots_stats(hours=9999)
            assert result["period_hours"] == 24 * 30


# ═══════════════════════════════════════════════════════════════════════
# V123 Phase 2.5 — get_ai_bots_timeline
# ═══════════════════════════════════════════════════════════════════════

class TestGetAiBotsTimeline:

    @pytest.mark.asyncio
    async def test_empty_no_top_bots(self):
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=[])):
            result = await get_ai_bots_timeline(hours=24)
            assert result["buckets"] == []
            assert result["series"] == []

    @pytest.mark.asyncio
    async def test_24h_returns_series_for_top5(self):
        async def side_effect(q, args=None):
            if "LIMIT 5" in q:
                return [
                    {"canonical_name": "Googlebot", "hits": 200},
                    {"canonical_name": "ClaudeBot", "hits": 50},
                ]
            return [
                {"bucket": "2026-04-18 10:00", "canonical_name": "Googlebot", "hits": 120},
                {"bucket": "2026-04-18 10:00", "canonical_name": "ClaudeBot", "hits": 30},
                {"bucket": "2026-04-18 11:00", "canonical_name": "Googlebot", "hits": 80},
            ]
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(side_effect=side_effect)):
            result = await get_ai_bots_timeline(hours=24)
            assert len(result["buckets"]) == 2
            assert len(result["series"]) == 2
            names = [s["name"] for s in result["series"]]
            assert "Googlebot" in names and "ClaudeBot" in names

    @pytest.mark.asyncio
    async def test_hours_clamped_timeline(self):
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=[])):
            result = await get_ai_bots_timeline(hours=0)
            assert result["period_hours"] == 1
            result = await get_ai_bots_timeline(hours=9999)
            assert result["period_hours"] == 720

    @pytest.mark.asyncio
    async def test_db_error_returns_defaults(self):
        with patch("db_cloudsql.async_fetchall", new=AsyncMock(side_effect=Exception("db"))):
            result = await get_ai_bots_timeline(hours=24)
            assert result["buckets"] == []
            assert result["series"] == []


# ═══════════════════════════════════════════════════════════════════════
# V123 Phase 2.5 — get_bot_dashboard_kpis
# ═══════════════════════════════════════════════════════════════════════

class TestGetBotDashboardKpis:

    @pytest.mark.asyncio
    async def test_empty_returns_zero_fields(self):
        with patch("db_cloudsql.async_fetchone", new=AsyncMock(return_value=None)):
            result = await get_bot_dashboard_kpis(hours=24)
            assert result["bot_allowed_24h"] == 0
            assert result["bot_blocked_24h"] == 0
            assert result["bot_distinct_count"] == 0
            assert result["bot_human_ratio_pct"] == 0
            assert result["human_hits_24h"] == 0

    @pytest.mark.asyncio
    async def test_ratio_computation(self):
        calls = []
        async def fetchone(q, args=None):
            calls.append(q)
            if "ai_bot_access_log" in q:
                return {"allowed": 300, "blocked": 28, "distinct_cnt": 8}
            return {"hits": 1000}  # event_log humans
        with patch("db_cloudsql.async_fetchone", new=AsyncMock(side_effect=fetchone)):
            result = await get_bot_dashboard_kpis(hours=24)
            assert result["bot_allowed_24h"] == 300
            assert result["bot_blocked_24h"] == 28
            assert result["bot_distinct_count"] == 8
            assert result["human_hits_24h"] == 1000
            assert result["bot_human_ratio_pct"] == 30  # round(300/1000*100) = 30

    @pytest.mark.asyncio
    async def test_db_error_returns_defaults(self):
        with patch("db_cloudsql.async_fetchone", new=AsyncMock(side_effect=Exception("db"))):
            result = await get_bot_dashboard_kpis(hours=24)
            assert all(v == 0 for v in result.values())

    @pytest.mark.asyncio
    async def test_human_hits_zero_ratio_is_zero(self):
        async def fetchone(q, args=None):
            if "ai_bot_access_log" in q:
                return {"allowed": 100, "blocked": 0, "distinct_cnt": 3}
            return {"hits": 0}
        with patch("db_cloudsql.async_fetchone", new=AsyncMock(side_effect=fetchone)):
            result = await get_bot_dashboard_kpis(hours=24)
            assert result["bot_human_ratio_pct"] == 0


class TestAdminEndpoints:

    def _build_client(self):
        import os
        import importlib
        env = {
            "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
            "ADMIN_TOKEN": "test_token_xyz",
            "ADMIN_PASSWORD": "test_pass",
            "OWNER_IP": "86.212.92.243",
        }
        with patch.dict(os.environ, env), _static_patch, _static_call:
            import rate_limit as rl_mod
            importlib.reload(rl_mod)
            import routes.admin_monitoring as mon_mod
            importlib.reload(mon_mod)
            import routes.admin as admin_mod
            importlib.reload(admin_mod)
            import main as main_mod
            importlib.reload(main_mod)
            rl_mod.limiter.reset()
            rl_mod._api_hits.clear()
            from starlette.testclient import TestClient
            client = TestClient(main_mod.app, raise_server_exceptions=False)
            client.cookies.set("lotoia_admin_token", "test_token_xyz")
            return client

    def test_bot_feeds_status_non_owner_blocked(self):
        """Non-owner IP receives 403 on /admin endpoints."""
        client = self._build_client()
        resp = client.get(
            "/admin/api/bot-feeds-status",
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        assert resp.status_code == 403

    def test_ai_bots_stats_non_owner_blocked(self):
        client = self._build_client()
        resp = client.get(
            "/admin/api/ai-bots/stats",
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        assert resp.status_code == 403
