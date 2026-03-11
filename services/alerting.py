"""
Alerting service — detect threshold breaches, log to event_log, send email.

Thresholds are stored in admin_config (key-value table).
Cooldown via Redis to prevent spam (15min for alerts, 1h for emails).
Email sent async via asyncio.to_thread() to avoid blocking.
"""

import asyncio
import json
import logging
import os
import smtplib
import time
from dataclasses import dataclass, asdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

import services.cache as _cache
from services.cache import _REDIS_PREFIX

logger = logging.getLogger(__name__)

# ── Default thresholds ────────────────────────────────────────────────────────

DEFAULT_THRESHOLDS = {
    "alert_error_rate_warn": "0.01",
    "alert_error_rate_crit": "0.05",
    "alert_latency_p95_warn": "3000",
    "alert_latency_p95_crit": "5000",
    "alert_cpu_warn": "0.70",
    "alert_cpu_crit": "0.90",
    "alert_memory_warn": "0.70",
    "alert_memory_crit": "0.90",
    "alert_gemini_avg_warn": "3000",
    "alert_gemini_avg_crit": "5000",
    "alert_cost_month_warn": "90",
    "alert_cost_month_crit": "120",
}

ALERT_COOLDOWN = 900     # 15 minutes between same alert
EMAIL_COOLDOWN = 3600    # 1 hour between same email alert

# In-memory cooldown fallback (when Redis unavailable)
_mem_cooldowns: dict[str, float] = {}  # key → expiry timestamp

# SMTP config from env
_SMTP_HOST = os.getenv("SMTP_HOST", "")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
_SMTP_USER = os.getenv("SMTP_USER", "")
_SMTP_PASS = os.getenv("SMTP_PASS", "")
_ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "partenariats@lotoia.fr")
_ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", _SMTP_USER or "alerts@lotoia.fr")


@dataclass
class Alert:
    level: str           # "warning" or "critical"
    metric_name: str     # e.g. "cpu_utilization"
    current_value: float
    threshold: float
    message: str         # human-readable


# ── Threshold loading ─────────────────────────────────────────────────────────

async def get_alert_thresholds() -> dict:
    """Load alert thresholds from admin_config, with defaults."""
    thresholds = dict(DEFAULT_THRESHOLDS)
    try:
        import db_cloudsql
        rows = await db_cloudsql.async_fetchall(
            "SELECT config_key, config_value FROM admin_config WHERE config_key LIKE 'alert_%'"
        )
        for r in rows:
            thresholds[r["config_key"]] = r["config_value"]
    except Exception as e:
        logger.debug("Alert thresholds DB read: %s", e)
    return thresholds


def _t(thresholds: dict, key: str) -> float:
    """Get threshold as float."""
    return float(thresholds.get(key, DEFAULT_THRESHOLDS.get(key, "0")))


# ── Cooldown (Redis) ─────────────────────────────────────────────────────────

async def _is_cooled_down(key: str, cooldown: int) -> bool:
    """Return True if alert is still in cooldown (should NOT fire)."""
    _redis = _cache._redis
    if not _redis:
        # In-memory fallback
        exp = _mem_cooldowns.get(key)
        return exp is not None and time.time() < exp
    try:
        val = await _redis.get(f"{_REDIS_PREFIX}alert_cd:{key}")
        return val is not None
    except Exception:
        return False


async def _set_cooldown(key: str, cooldown: int) -> None:
    """Set cooldown for an alert key."""
    _redis = _cache._redis
    if not _redis:
        _mem_cooldowns[key] = time.time() + cooldown
        return
    try:
        await _redis.set(f"{_REDIS_PREFIX}alert_cd:{key}", "1", ex=cooldown)
    except Exception:
        pass


# ── Alert detection ──────────────────────────────────────────────────────────

async def check_alerts(metrics: dict, gemini: dict, costs: dict) -> list[Alert]:
    """
    Compare metrics against thresholds. Returns list of Alert objects.
    Respects cooldown: same alert not fired more than once per 15 min.
    """
    th = await get_alert_thresholds()
    alerts = []

    checks = [
        # (metric_name, current_value, warn_key, crit_key, label, unit, multiplier)
        ("error_rate_5xx", metrics.get("error_rate_5xx", 0),
         "alert_error_rate_warn", "alert_error_rate_crit",
         "Taux erreur 5xx", "%", 100),
        ("latency_p95_ms", metrics.get("latency_p95_ms", 0),
         "alert_latency_p95_warn", "alert_latency_p95_crit",
         "Latence P95", "ms", 1),
        ("cpu_utilization", metrics.get("cpu_utilization", 0),
         "alert_cpu_warn", "alert_cpu_crit",
         "CPU", "%", 100),
        ("memory_utilization", metrics.get("memory_utilization", 0),
         "alert_memory_warn", "alert_memory_crit",
         "RAM", "%", 100),
        ("gemini_avg_response", gemini.get("avg_response_time_ms", 0),
         "alert_gemini_avg_warn", "alert_gemini_avg_crit",
         "Gemini temps moyen", "ms", 1),
        ("cost_month", costs.get("estimated_month_eur", 0),
         "alert_cost_month_warn", "alert_cost_month_crit",
         "Cout mensuel estime", "EUR", 1),
    ]

    for metric_name, value, warn_key, crit_key, label, unit, mult in checks:
        crit_threshold = _t(th, crit_key)
        warn_threshold = _t(th, warn_key)

        # Check critical first
        if value >= crit_threshold and crit_threshold > 0:
            cd_key = f"{metric_name}:critical"
            if not await _is_cooled_down(cd_key, ALERT_COOLDOWN):
                display_val = round(value * mult, 1) if mult != 1 else round(value, 2)
                display_thr = round(crit_threshold * mult, 1) if mult != 1 else round(crit_threshold, 2)
                alerts.append(Alert(
                    level="critical",
                    metric_name=metric_name,
                    current_value=value,
                    threshold=crit_threshold,
                    message=f"{label} a {display_val}{unit} (seuil: {display_thr}{unit})",
                ))
                await _set_cooldown(cd_key, ALERT_COOLDOWN)
        elif value >= warn_threshold and warn_threshold > 0:
            cd_key = f"{metric_name}:warning"
            if not await _is_cooled_down(cd_key, ALERT_COOLDOWN):
                display_val = round(value * mult, 1) if mult != 1 else round(value, 2)
                display_thr = round(warn_threshold * mult, 1) if mult != 1 else round(warn_threshold, 2)
                alerts.append(Alert(
                    level="warning",
                    metric_name=metric_name,
                    current_value=value,
                    threshold=warn_threshold,
                    message=f"{label} a {display_val}{unit} (seuil: {display_thr}{unit})",
                ))
                await _set_cooldown(cd_key, ALERT_COOLDOWN)

    return alerts


# ── Event log insertion ──────────────────────────────────────────────────────

async def _log_alert_to_event_log(alert: Alert) -> None:
    """Insert alert into event_log table for realtime feed."""
    event_type = f"alert_{alert.level}"
    icon = "🔴" if alert.level == "critical" else "⚠️"
    meta = {
        "metric": alert.metric_name,
        "value": alert.current_value,
        "threshold": alert.threshold,
        "message": f"{icon} {alert.message}",
    }
    try:
        import db_cloudsql
        await db_cloudsql.async_query(
            """INSERT INTO event_log
                (event_type, page, module, lang, device, country, session_hash, meta_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (event_type, "/admin/monitoring", "alerting", "", "server", "",
             "", json.dumps(meta)),
        )
    except Exception as e:
        logger.error("Alert event_log insert: %s", e)


# ── Email (async, non-blocking) ─────────────────────────────────────────────

def _send_email_sync(alert: Alert) -> None:
    """Synchronous email send via smtplib. Called in thread."""
    if not _SMTP_HOST or not _SMTP_USER:
        logger.warning("SMTP not configured — skipping alert email")
        return

    subject = f"[LotoIA ALERTE] {alert.metric_name} critique"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    body = f"""ALERTE CRITIQUE — LotoIA Monitoring

Metrique : {alert.metric_name}
Valeur actuelle : {alert.current_value}
Seuil critique : {alert.threshold}
Message : {alert.message}
Timestamp : {ts}

---
Alerte automatique generee par LotoIA Monitoring.
Dashboard : https://lotoia.fr/admin/monitoring
"""

    msg = MIMEMultipart()
    msg["From"] = _ALERT_EMAIL_FROM
    msg["To"] = _ALERT_EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        if _SMTP_PORT == 465:
            with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, timeout=10) as server:
                server.login(_SMTP_USER, _SMTP_PASS)
                server.send_message(msg)
        else:
            with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(_SMTP_USER, _SMTP_PASS)
                server.send_message(msg)
        logger.info("Alert email sent: %s", alert.metric_name)
    except Exception as e:
        logger.error("Alert email send failed: %s", e)


async def _send_email_async(alert: Alert) -> None:
    """Send email in background thread (non-blocking)."""
    # Check email cooldown (1h)
    email_cd_key = f"email:{alert.metric_name}"
    if await _is_cooled_down(email_cd_key, EMAIL_COOLDOWN):
        logger.debug("Email cooldown active for %s", alert.metric_name)
        return
    await _set_cooldown(email_cd_key, EMAIL_COOLDOWN)

    try:
        await asyncio.to_thread(_send_email_sync, alert)
    except Exception as e:
        logger.error("Alert email thread error: %s", e)


# ── Main entry point ─────────────────────────────────────────────────────────

async def process_alerts(metrics: dict, gemini: dict, costs: dict) -> list[dict]:
    """
    Check alerts, log to event_log, send emails for critical.
    Returns list of active alert dicts for API response.
    Non-blocking: email sent in background thread.
    """
    alerts = await check_alerts(metrics, gemini, costs)

    for alert in alerts:
        # Log to event_log (async DB)
        await _log_alert_to_event_log(alert)

        # Email for critical alerts (non-blocking thread)
        if alert.level == "critical":
            asyncio.create_task(_send_email_async(alert))

    return [asdict(a) for a in alerts]
