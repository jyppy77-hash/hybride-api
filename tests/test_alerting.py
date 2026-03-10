"""
Tests — services/alerting.py
Alert detection, cooldown, event_log insertion, email async.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call
from dataclasses import asdict

from services.alerting import (
    check_alerts,
    process_alerts,
    _send_email_sync,
    _log_alert_to_event_log,
    Alert,
    DEFAULT_THRESHOLDS,
    ALERT_COOLDOWN,
    EMAIL_COOLDOWN,
)


# Helper: metrics fixtures
def _healthy_metrics():
    return {
        "error_rate_5xx": 0.002,
        "latency_p95_ms": 500,
        "cpu_utilization": 0.30,
        "memory_utilization": 0.35,
    }

def _healthy_gemini():
    return {"avg_response_time_ms": 1200, "calls_today": 50}

def _healthy_costs():
    return {"estimated_month_eur": 28.5}


# ═══════════════════════════════════════════════════════════════════════
# Alert detection — healthy → no alerts
# ═══════════════════════════════════════════════════════════════════════

class TestCheckAlertsHealthy:

    @pytest.mark.asyncio
    async def test_healthy_metrics_no_alerts(self):
        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
        ):
            alerts = await check_alerts(_healthy_metrics(), _healthy_gemini(), _healthy_costs())
            assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_zero_values_no_alerts(self):
        m = {k: 0 for k in _healthy_metrics()}
        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
        ):
            alerts = await check_alerts(m, {"avg_response_time_ms": 0}, {"estimated_month_eur": 0})
            assert len(alerts) == 0


# ═══════════════════════════════════════════════════════════════════════
# Alert detection — threshold breaches
# ═══════════════════════════════════════════════════════════════════════

class TestCheckAlertsBreach:

    @pytest.mark.asyncio
    async def test_cpu_warning(self):
        m = _healthy_metrics()
        m["cpu_utilization"] = 0.85  # > 0.70 warn, < 0.90 crit
        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
        ):
            alerts = await check_alerts(m, _healthy_gemini(), _healthy_costs())
            assert len(alerts) == 1
            assert alerts[0].level == "warning"
            assert alerts[0].metric_name == "cpu_utilization"

    @pytest.mark.asyncio
    async def test_error_rate_critical(self):
        m = _healthy_metrics()
        m["error_rate_5xx"] = 0.07  # > 0.05 crit
        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
        ):
            alerts = await check_alerts(m, _healthy_gemini(), _healthy_costs())
            assert len(alerts) == 1
            assert alerts[0].level == "critical"
            assert alerts[0].metric_name == "error_rate_5xx"

    @pytest.mark.asyncio
    async def test_multiple_alerts(self):
        m = _healthy_metrics()
        m["cpu_utilization"] = 0.95     # > crit
        m["error_rate_5xx"] = 0.03      # > warn
        m["latency_p95_ms"] = 6000      # > crit
        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
        ):
            alerts = await check_alerts(m, _healthy_gemini(), _healthy_costs())
            assert len(alerts) == 3
            names = {a.metric_name for a in alerts}
            assert "cpu_utilization" in names
            assert "error_rate_5xx" in names
            assert "latency_p95_ms" in names

    @pytest.mark.asyncio
    async def test_gemini_avg_warning(self):
        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
        ):
            alerts = await check_alerts(
                _healthy_metrics(),
                {"avg_response_time_ms": 4000},  # > 3000 warn
                _healthy_costs(),
            )
            assert len(alerts) == 1
            assert alerts[0].metric_name == "gemini_avg_response"
            assert alerts[0].level == "warning"

    @pytest.mark.asyncio
    async def test_cost_month_critical(self):
        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
        ):
            alerts = await check_alerts(
                _healthy_metrics(),
                _healthy_gemini(),
                {"estimated_month_eur": 150},  # > 120 crit
            )
            assert len(alerts) == 1
            assert alerts[0].metric_name == "cost_month"
            assert alerts[0].level == "critical"

    @pytest.mark.asyncio
    async def test_critical_takes_priority_over_warning(self):
        """When value exceeds critical threshold, only critical fires (not warning)."""
        m = _healthy_metrics()
        m["cpu_utilization"] = 0.95  # > crit 0.90
        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
        ):
            alerts = await check_alerts(m, _healthy_gemini(), _healthy_costs())
            cpu_alerts = [a for a in alerts if a.metric_name == "cpu_utilization"]
            assert len(cpu_alerts) == 1
            assert cpu_alerts[0].level == "critical"


# ═══════════════════════════════════════════════════════════════════════
# Cooldown — same alert not re-fired within 15 min
# ═══════════════════════════════════════════════════════════════════════

class TestAlertCooldown:

    @pytest.mark.asyncio
    async def test_cooled_down_alert_not_fired(self):
        m = _healthy_metrics()
        m["cpu_utilization"] = 0.85

        async def mock_cooled(key, cd):
            return "cpu_utilization" in key  # CPU is cooled down

        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", mock_cooled),
            patch("services.alerting._set_cooldown", AsyncMock()),
        ):
            alerts = await check_alerts(m, _healthy_gemini(), _healthy_costs())
            assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_cooldown_set_on_alert(self):
        m = _healthy_metrics()
        m["cpu_utilization"] = 0.85
        mock_set = AsyncMock()
        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", mock_set),
        ):
            alerts = await check_alerts(m, _healthy_gemini(), _healthy_costs())
            assert len(alerts) == 1
            mock_set.assert_called_once_with("cpu_utilization:warning", ALERT_COOLDOWN)


# ═══════════════════════════════════════════════════════════════════════
# Event log insertion
# ═══════════════════════════════════════════════════════════════════════

class TestAlertEventLog:

    @pytest.mark.asyncio
    async def test_log_warning_to_event_log(self):
        alert = Alert("warning", "cpu_utilization", 0.85, 0.70, "CPU a 85% (seuil: 70%)")
        mock_query = AsyncMock()
        with patch("db_cloudsql.async_query", mock_query):
            await _log_alert_to_event_log(alert)
            mock_query.assert_called_once()
            args = mock_query.call_args[0]
            assert "INSERT INTO event_log" in args[0]
            params = args[1]
            assert params[0] == "alert_warning"
            assert params[1] == "/admin/monitoring"

    @pytest.mark.asyncio
    async def test_log_critical_to_event_log(self):
        alert = Alert("critical", "error_rate_5xx", 0.07, 0.05, "Taux erreur a 7%")
        mock_query = AsyncMock()
        with patch("db_cloudsql.async_query", mock_query):
            await _log_alert_to_event_log(alert)
            args = mock_query.call_args[0]
            params = args[1]
            assert params[0] == "alert_critical"

    @pytest.mark.asyncio
    async def test_log_db_error_no_crash(self):
        alert = Alert("warning", "cpu", 0.85, 0.70, "test")
        with patch("db_cloudsql.async_query", AsyncMock(side_effect=Exception("DB down"))):
            await _log_alert_to_event_log(alert)  # should not raise


# ═══════════════════════════════════════════════════════════════════════
# Email — async, non-blocking
# ═══════════════════════════════════════════════════════════════════════

class TestAlertEmail:

    def test_no_smtp_config_no_crash(self):
        """If SMTP not configured, email is skipped with warning."""
        alert = Alert("critical", "error_rate_5xx", 0.07, 0.05, "Taux erreur a 7%")
        with (
            patch("services.alerting._SMTP_HOST", ""),
            patch("services.alerting._SMTP_USER", ""),
        ):
            _send_email_sync(alert)  # should not raise

    def test_smtp_ssl_called(self):
        """Email sent via SMTP_SSL on port 465."""
        alert = Alert("critical", "error_rate_5xx", 0.07, 0.05, "Taux erreur a 7%")
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        with (
            patch("services.alerting._SMTP_HOST", "smtp.test.com"),
            patch("services.alerting._SMTP_PORT", 465),
            patch("services.alerting._SMTP_USER", "user@test.com"),
            patch("services.alerting._SMTP_PASS", "pass123"),
            patch("smtplib.SMTP_SSL", return_value=mock_smtp),
        ):
            _send_email_sync(alert)
            mock_smtp.login.assert_called_once_with("user@test.com", "pass123")
            mock_smtp.send_message.assert_called_once()

    def test_smtp_tls_called(self):
        """Email sent via SMTP + STARTTLS on port 587."""
        alert = Alert("critical", "cpu", 0.95, 0.90, "CPU critique")
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        with (
            patch("services.alerting._SMTP_HOST", "smtp.test.com"),
            patch("services.alerting._SMTP_PORT", 587),
            patch("services.alerting._SMTP_USER", "user@test.com"),
            patch("services.alerting._SMTP_PASS", "pass123"),
            patch("smtplib.SMTP", return_value=mock_smtp),
        ):
            _send_email_sync(alert)
            mock_smtp.starttls.assert_called_once()
            mock_smtp.login.assert_called_once()
            mock_smtp.send_message.assert_called_once()

    def test_smtp_error_no_crash(self):
        """SMTP connection error doesn't raise."""
        alert = Alert("critical", "cpu", 0.95, 0.90, "CPU critique")
        with (
            patch("services.alerting._SMTP_HOST", "smtp.bad.com"),
            patch("services.alerting._SMTP_PORT", 465),
            patch("services.alerting._SMTP_USER", "user"),
            patch("services.alerting._SMTP_PASS", "pass"),
            patch("smtplib.SMTP_SSL", side_effect=Exception("Connection refused")),
        ):
            _send_email_sync(alert)  # should not raise


# ═══════════════════════════════════════════════════════════════════════
# Email anti-spam cooldown
# ═══════════════════════════════════════════════════════════════════════

class TestEmailCooldown:

    @pytest.mark.asyncio
    async def test_email_cooldown_prevents_resend(self):
        """Same critical alert within 1 hour → no re-send."""
        from services.alerting import _send_email_async
        alert = Alert("critical", "cpu", 0.95, 0.90, "CPU critique")

        # cooldown is active
        with (
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=True)),
            patch("asyncio.to_thread", AsyncMock()) as mock_thread,
        ):
            await _send_email_async(alert)
            mock_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_sent_when_no_cooldown(self):
        from services.alerting import _send_email_async
        alert = Alert("critical", "cpu", 0.95, 0.90, "CPU critique")

        with (
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
            patch("asyncio.to_thread", AsyncMock()) as mock_thread,
        ):
            await _send_email_async(alert)
            mock_thread.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# process_alerts — full pipeline
# ═══════════════════════════════════════════════════════════════════════

class TestProcessAlerts:

    @pytest.mark.asyncio
    async def test_healthy_returns_empty_list(self):
        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
        ):
            result = await process_alerts(_healthy_metrics(), _healthy_gemini(), _healthy_costs())
            assert result == []

    @pytest.mark.asyncio
    async def test_critical_triggers_event_log_and_email(self):
        m = _healthy_metrics()
        m["error_rate_5xx"] = 0.07  # critical

        mock_log = AsyncMock()
        mock_email = AsyncMock()

        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
            patch("services.alerting._log_alert_to_event_log", mock_log),
            patch("services.alerting._send_email_async", mock_email),
            patch("asyncio.ensure_future"),
        ):
            # Patch ensure_future to call the coroutine directly
            import asyncio
            original_ef = asyncio.ensure_future
            with patch("services.alerting.asyncio.ensure_future", side_effect=lambda coro: original_ef(coro)):
                result = await process_alerts(m, _healthy_gemini(), _healthy_costs())

            assert len(result) == 1
            assert result[0]["level"] == "critical"
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_warning_triggers_event_log_no_email(self):
        m = _healthy_metrics()
        m["cpu_utilization"] = 0.85  # warning

        mock_log = AsyncMock()

        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
            patch("services.alerting._log_alert_to_event_log", mock_log),
            patch("services.alerting.asyncio.ensure_future") as mock_ef,
        ):
            result = await process_alerts(m, _healthy_gemini(), _healthy_costs())
            assert len(result) == 1
            assert result[0]["level"] == "warning"
            mock_log.assert_called_once()
            mock_ef.assert_not_called()  # no email for warnings

    @pytest.mark.asyncio
    async def test_returns_serializable_dicts(self):
        m = _healthy_metrics()
        m["cpu_utilization"] = 0.85

        with (
            patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))),
            patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)),
            patch("services.alerting._set_cooldown", AsyncMock()),
            patch("services.alerting._log_alert_to_event_log", AsyncMock()),
        ):
            result = await process_alerts(m, _healthy_gemini(), _healthy_costs())
            assert isinstance(result[0], dict)
            assert "level" in result[0]
            assert "metric_name" in result[0]
            assert "current_value" in result[0]
            assert "threshold" in result[0]
            assert "message" in result[0]


# ═══════════════════════════════════════════════════════════════════════
# Default thresholds
# ═══════════════════════════════════════════════════════════════════════

class TestDefaultThresholds:

    def test_all_keys_present(self):
        expected = {
            "alert_error_rate_warn", "alert_error_rate_crit",
            "alert_latency_p95_warn", "alert_latency_p95_crit",
            "alert_cpu_warn", "alert_cpu_crit",
            "alert_memory_warn", "alert_memory_crit",
            "alert_gemini_avg_warn", "alert_gemini_avg_crit",
            "alert_cost_month_warn", "alert_cost_month_crit",
        }
        assert set(DEFAULT_THRESHOLDS.keys()) == expected

    def test_warn_less_than_crit(self):
        pairs = [
            ("alert_error_rate_warn", "alert_error_rate_crit"),
            ("alert_latency_p95_warn", "alert_latency_p95_crit"),
            ("alert_cpu_warn", "alert_cpu_crit"),
            ("alert_memory_warn", "alert_memory_crit"),
            ("alert_gemini_avg_warn", "alert_gemini_avg_crit"),
            ("alert_cost_month_warn", "alert_cost_month_crit"),
        ]
        for w, c in pairs:
            assert float(DEFAULT_THRESHOLDS[w]) < float(DEFAULT_THRESHOLDS[c]), \
                f"{w}={DEFAULT_THRESHOLDS[w]} should be < {c}={DEFAULT_THRESHOLDS[c]}"
