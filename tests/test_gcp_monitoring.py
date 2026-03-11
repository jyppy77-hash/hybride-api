"""
Tests — services/gcp_monitoring.py
Monitoring endpoint: Cloud Run metrics, Gemini tracking (DB), cost estimation, status.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime

from services.gcp_monitoring import (
    _determine_status,
    _estimate_costs,
    _get_gemini_counters,
    get_gcp_metrics,
    track_gemini_call,
    COST_CONFIG,
    _LOCAL_CACHE,
)


# ═══════════════════════════════════════════════════════════════════════
# Status determination
# ═══════════════════════════════════════════════════════════════════════

class TestDetermineStatus:

    def test_healthy(self):
        assert _determine_status(0.005, 2000) == "healthy"

    def test_healthy_zero(self):
        assert _determine_status(0.0, 0) == "healthy"

    def test_degraded_high_error(self):
        assert _determine_status(0.03, 2000) == "degraded"

    def test_degraded_high_latency(self):
        assert _determine_status(0.005, 4000) == "degraded"

    def test_down_very_high_error(self):
        assert _determine_status(0.06, 1000) == "down"

    def test_down_very_high_latency(self):
        assert _determine_status(0.03, 6000) == "down"

    def test_boundary_healthy(self):
        assert _determine_status(0.0099, 2999) == "healthy"

    def test_boundary_degraded(self):
        assert _determine_status(0.01, 3000) == "degraded"

    def test_boundary_down(self):
        assert _determine_status(0.05, 5000) == "down"


# ═══════════════════════════════════════════════════════════════════════
# Cost estimation
# ═══════════════════════════════════════════════════════════════════════

class TestCostEstimation:

    def test_zero_usage(self):
        costs = _estimate_costs({"active_instances": 0}, {"tokens_in": 0, "tokens_out": 0})
        assert costs["gemini_today_eur"] == 0
        assert costs["cloud_sql_today_eur"] == COST_CONFIG["cloud_sql_daily_eur"]
        assert costs["total_today_eur"] >= costs["cloud_sql_today_eur"]

    def test_gemini_cost_calculation(self):
        costs = _estimate_costs(
            {"active_instances": 1},
            {"tokens_in": 1_000_000, "tokens_out": 1_000_000},
        )
        expected_usd = (
            1_000_000 * COST_CONFIG["gemini_input_per_1m_usd"] / 1_000_000
            + 1_000_000 * COST_CONFIG["gemini_output_per_1m_usd"] / 1_000_000
        )
        expected_eur = round(expected_usd * COST_CONFIG["usd_to_eur"], 4)
        assert costs["gemini_today_eur"] == expected_eur

    def test_cloud_run_cost_scales_with_instances(self):
        costs_1 = _estimate_costs({"active_instances": 1}, {"tokens_in": 0, "tokens_out": 0})
        costs_3 = _estimate_costs({"active_instances": 3}, {"tokens_in": 0, "tokens_out": 0})
        assert costs_1["cloud_run_today_eur"] > 0
        assert abs(costs_3["cloud_run_today_eur"] - costs_1["cloud_run_today_eur"] * 3) < 0.02

    def test_monthly_estimate(self):
        costs = _estimate_costs({"active_instances": 1}, {"tokens_in": 0, "tokens_out": 0})
        assert costs["estimated_month_eur"] == round(costs["total_today_eur"] * 30, 1)

    def test_all_keys_present(self):
        costs = _estimate_costs({"active_instances": 1}, {"tokens_in": 100, "tokens_out": 50})
        assert "cloud_run_today_eur" in costs
        assert "cloud_sql_today_eur" in costs
        assert "gemini_today_eur" in costs
        assert "total_today_eur" in costs
        assert "estimated_month_eur" in costs


# ═══════════════════════════════════════════════════════════════════════
# Gemini counters (DB)
# ═══════════════════════════════════════════════════════════════════════

class TestGeminiCounters:

    def setup_method(self):
        _LOCAL_CACHE.clear()

    @pytest.mark.asyncio
    async def test_returns_db_values(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "calls": 10, "errors": 1, "tokens_in": 5000, "tokens_out": 1200, "total_ms": 8000,
            })
            counters = await _get_gemini_counters()
            assert counters["calls"] == 10
            assert counters["errors"] == 1
            assert counters["tokens_in"] == 5000
            assert counters["tokens_out"] == 1200
            assert counters["total_ms"] == 8000

    @pytest.mark.asyncio
    async def test_db_error_returns_defaults(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(side_effect=Exception("DB down"))
            counters = await _get_gemini_counters()
            assert counters["calls"] == 0

    @pytest.mark.asyncio
    async def test_none_row_returns_defaults(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value=None)
            counters = await _get_gemini_counters()
            assert counters == {"calls": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0, "total_ms": 0}

    @pytest.mark.asyncio
    async def test_cached_60s(self):
        """Second call within 60s returns cached value without hitting DB."""
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "calls": 5, "errors": 0, "tokens_in": 100, "tokens_out": 50, "total_ms": 500,
            })
            first = await _get_gemini_counters()
            second = await _get_gemini_counters()
            assert first == second
            assert mock_db.async_fetchone.call_count == 1


# ═══════════════════════════════════════════════════════════════════════
# Track Gemini call (DB insert)
# ═══════════════════════════════════════════════════════════════════════

class TestTrackGeminiCall:

    @pytest.mark.asyncio
    async def test_inserts_into_db(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            await track_gemini_call(250.0, 500, 100)
            # create_task fires, but await _do_track_insert is the fallback
            # Give the task a chance to complete
            import asyncio
            await asyncio.sleep(0.05)
            mock_db.async_query.assert_called_once()
            sql, params = mock_db.async_query.call_args[0]
            assert "INSERT INTO gemini_tracking" in sql
            assert params[2] == 500  # tokens_in
            assert params[3] == 100  # tokens_out
            assert params[4] == 250  # duration_ms
            assert params[5] == 0   # is_error

    @pytest.mark.asyncio
    async def test_inserts_error_flag(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            await track_gemini_call(100.0, error=True, call_type="chat_em", lang="fr")
            import asyncio
            await asyncio.sleep(0.05)
            mock_db.async_query.assert_called_once()
            _, params = mock_db.async_query.call_args[0]
            assert params[0] == "chat_em"  # call_type
            assert params[1] == "fr"       # lang
            assert params[5] == 1          # is_error

    @pytest.mark.asyncio
    async def test_db_error_does_not_raise(self):
        with patch("services.gcp_monitoring.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(side_effect=Exception("DB error"))
            await track_gemini_call(150.0, 100, 50)
            import asyncio
            await asyncio.sleep(0.05)
            # Should not raise


# ═══════════════════════════════════════════════════════════════════════
# Full payload (get_gcp_metrics)
# ═══════════════════════════════════════════════════════════════════════

class TestGetGcpMetrics:

    @pytest.mark.asyncio
    async def test_returns_cached_value(self):
        cached = {"status": "healthy", "cached": True}
        with patch("services.gcp_monitoring.cache_get", AsyncMock(return_value=cached)):
            result = await get_gcp_metrics()
            assert result == cached

    @pytest.mark.asyncio
    async def test_cloud_monitoring_unavailable_returns_unknown(self):
        _LOCAL_CACHE.clear()
        with (
            patch("services.gcp_monitoring.cache_get", AsyncMock(return_value=None)),
            patch("services.gcp_monitoring.cache_set", AsyncMock()),
            patch("services.gcp_monitoring._fetch_cloud_run_metrics", AsyncMock(return_value={})),
            patch("services.gcp_monitoring._get_gemini_counters", AsyncMock(return_value={
                "calls": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0, "total_ms": 0,
            })),
        ):
            result = await get_gcp_metrics()
            assert result["status"] == "unknown"
            assert "metrics" in result
            assert "gemini" in result
            assert "costs" in result
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_healthy_metrics(self):
        _LOCAL_CACHE.clear()
        cloud_metrics = {
            "requests_per_second": 2.5,
            "error_rate_5xx": 0.002,
            "latency_p50_ms": 45,
            "latency_p95_ms": 850,
            "latency_p99_ms": 2100,
            "active_instances": 2,
            "cpu_utilization": 0.35,
            "memory_utilization": 0.42,
        }
        gem_counters = {
            "calls": 156,
            "errors": 0,
            "tokens_in": 45200,
            "tokens_out": 12800,
            "total_ms": 187200,
        }
        with (
            patch("services.gcp_monitoring.cache_get", AsyncMock(return_value=None)),
            patch("services.gcp_monitoring.cache_set", AsyncMock()),
            patch("services.gcp_monitoring._fetch_cloud_run_metrics", AsyncMock(return_value=cloud_metrics)),
            patch("services.gcp_monitoring._get_gemini_counters", AsyncMock(return_value=gem_counters)),
        ):
            result = await get_gcp_metrics()
            assert result["status"] == "healthy"
            assert result["metrics"]["requests_per_second"] == 2.5
            assert result["metrics"]["error_rate_5xx"] == 0.002
            assert result["metrics"]["active_instances"] == 2
            assert result["gemini"]["calls_today"] == 156
            assert result["gemini"]["tokens_in_today"] == 45200
            assert result["gemini"]["avg_response_time_ms"] == 1200
            assert result["costs"]["cloud_sql_today_eur"] == COST_CONFIG["cloud_sql_daily_eur"]

    @pytest.mark.asyncio
    async def test_degraded_status(self):
        _LOCAL_CACHE.clear()
        cloud_metrics = {
            "error_rate_5xx": 0.03,
            "latency_p95_ms": 4000,
        }
        with (
            patch("services.gcp_monitoring.cache_get", AsyncMock(return_value=None)),
            patch("services.gcp_monitoring.cache_set", AsyncMock()),
            patch("services.gcp_monitoring._fetch_cloud_run_metrics", AsyncMock(return_value=cloud_metrics)),
            patch("services.gcp_monitoring._get_gemini_counters", AsyncMock(return_value={
                "calls": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0, "total_ms": 0,
            })),
        ):
            result = await get_gcp_metrics()
            assert result["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_payload_structure(self):
        _LOCAL_CACHE.clear()
        with (
            patch("services.gcp_monitoring.cache_get", AsyncMock(return_value=None)),
            patch("services.gcp_monitoring.cache_set", AsyncMock()),
            patch("services.gcp_monitoring._fetch_cloud_run_metrics", AsyncMock(return_value={
                "requests_per_second": 1, "error_rate_5xx": 0, "latency_p50_ms": 10,
                "latency_p95_ms": 100, "latency_p99_ms": 200, "active_instances": 1,
                "cpu_utilization": 0.1, "memory_utilization": 0.2,
            })),
            patch("services.gcp_monitoring._get_gemini_counters", AsyncMock(return_value={
                "calls": 5, "errors": 0, "tokens_in": 1000, "tokens_out": 500, "total_ms": 5000,
            })),
        ):
            result = await get_gcp_metrics()

            # Top-level keys
            assert set(result.keys()) == {"status", "timestamp", "metrics", "gemini", "costs", "active_alerts", "redis_connected"}

            # Metrics keys
            expected_metric_keys = {
                "requests_per_second", "error_rate_5xx",
                "latency_p50_ms", "latency_p95_ms", "latency_p99_ms",
                "active_instances", "cpu_utilization", "memory_utilization",
            }
            assert set(result["metrics"].keys()) == expected_metric_keys

            # Gemini keys
            expected_gemini_keys = {
                "avg_response_time_ms", "errors_today", "calls_today",
                "tokens_in_today", "tokens_out_today", "estimated_cost_today_eur",
            }
            assert set(result["gemini"].keys()) == expected_gemini_keys

            # Costs keys
            expected_cost_keys = {
                "cloud_run_today_eur", "cloud_sql_today_eur",
                "gemini_today_eur", "total_today_eur", "estimated_month_eur",
            }
            assert set(result["costs"].keys()) == expected_cost_keys

    @pytest.mark.asyncio
    async def test_caches_result(self):
        _LOCAL_CACHE.clear()
        mock_set = AsyncMock()
        with (
            patch("services.gcp_monitoring.cache_get", AsyncMock(return_value=None)),
            patch("services.gcp_monitoring.cache_set", mock_set),
            patch("services.gcp_monitoring._fetch_cloud_run_metrics", AsyncMock(return_value={})),
            patch("services.gcp_monitoring._get_gemini_counters", AsyncMock(return_value={
                "calls": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0, "total_ms": 0,
            })),
        ):
            result = await get_gcp_metrics()
            mock_set.assert_called_once()
            args = mock_set.call_args
            assert args[0][0] == "gcp_metrics"
            assert args[0][1] == result
            assert args[0][2] == 60


# ═══════════════════════════════════════════════════════════════════════
# Cloud Monitoring API unavailable fallback
# ═══════════════════════════════════════════════════════════════════════

class TestCloudMonitoringFallback:

    @pytest.mark.asyncio
    async def test_import_error_returns_empty(self):
        """If google-cloud-monitoring is not installed, _fetch returns {}."""
        from services.gcp_monitoring import _fetch_cloud_run_metrics
        with patch.dict("sys.modules", {"google.cloud": None, "google.cloud.monitoring_v3": None}):
            # Force re-import failure
            with patch("builtins.__import__", side_effect=ImportError("no module")):
                result = await _fetch_cloud_run_metrics()
                assert result == {}

    @pytest.mark.asyncio
    async def test_no_project_id_returns_empty(self):
        from services.gcp_monitoring import _fetch_cloud_run_metrics
        with patch("services.gcp_monitoring._get_project_id", return_value=None):
            result = await _fetch_cloud_run_metrics()
            assert result == {}
