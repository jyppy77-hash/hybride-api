"""
GCP Monitoring — Cloud Run metrics + Gemini tracking + cost estimation.

Fetches real-time Cloud Run metrics via Cloud Monitoring API,
reads Gemini usage counters from MySQL (gemini_tracking table),
estimates daily costs.

Cache: 60s Redis (key "gcp_metrics") for full payload.
Gemini counters: 60s local in-memory cache to avoid spamming DB.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal

import db_cloudsql
import services.cache as _cache
from services.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_SERVICE_NAME = os.getenv("K_SERVICE", "hybride-api-eu")
_LOCATION = os.getenv("CLOUD_RUN_LOCATION", "europe-west1")
_GCP_PROJECT = None  # resolved lazily

CACHE_KEY = "gcp_metrics"
CACHE_TTL = 60  # seconds

# Gemini Flash 2.0 pricing (USD per 1M tokens)
COST_CONFIG = {
    "gemini_input_per_1m_usd": 0.075,
    "gemini_output_per_1m_usd": 0.30,
    # Cloud Run: 1 vCPU allocated, price per vCPU-second
    "cloud_run_vcpu_per_sec_usd": 0.000024,
    "cloud_run_mem_gib_per_sec_usd": 0.0000025,
    "cloud_run_vcpu_count": 1,
    "cloud_run_mem_gib": 0.5,
    # Cloud SQL: flat daily estimate (micro instance)
    "cloud_sql_daily_eur": 0.85,
    # USD → EUR conversion
    "usd_to_eur": 0.92,
}

# ── Local cache for Gemini DB queries (60s TTL) ──────────────────────────────

_LOCAL_CACHE: dict[str, tuple[float, object]] = {}
_LOCAL_CACHE_TTL = 60  # seconds
_LOCAL_CACHE_MAXSIZE = 100  # I06 V67: safety cap to prevent unbounded growth


def _local_cache_get(key: str):
    """Return cached value if still valid, else None."""
    entry = _LOCAL_CACHE.get(key)
    if entry and time.monotonic() - entry[0] < _LOCAL_CACHE_TTL:
        return entry[1]
    return None


def _local_cache_set(key: str, value):
    """Store value with current timestamp. Safety cap at _LOCAL_CACHE_MAXSIZE."""
    if len(_LOCAL_CACHE) >= _LOCAL_CACHE_MAXSIZE:
        _LOCAL_CACHE.clear()
        logger.warning("[GCP_MON] Local cache cleared — reached %d entries", _LOCAL_CACHE_MAXSIZE)
    _LOCAL_CACHE[key] = (time.monotonic(), value)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_project_id() -> str | None:
    global _GCP_PROJECT
    if _GCP_PROJECT:
        return _GCP_PROJECT
    _GCP_PROJECT = (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT")
        or os.getenv("GCLOUD_PROJECT")
    )
    return _GCP_PROJECT


def _determine_status(error_rate: float, latency_p95_ms: float) -> str:
    if error_rate < 0.01 and latency_p95_ms < 3000:
        return "healthy"
    if error_rate < 0.05 and latency_p95_ms < 5000:
        return "degraded"
    return "down"


# ── Gemini tracking (called from gemini.py / pipelines) ──────────────────────

_TRACK_INSERT_SQL = (
    "INSERT INTO gemini_tracking (call_type, lang, tokens_in, tokens_out, duration_ms, is_error) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)


async def _do_track_insert(
    call_type: str, lang: str, tokens_in: int, tokens_out: int,
    duration_ms: int, is_error: int,
) -> None:
    """Fire-and-forget DB insert. Errors are logged, never raised."""
    try:
        await db_cloudsql.async_query(
            _TRACK_INSERT_SQL,
            (call_type, lang, tokens_in, tokens_out, duration_ms, is_error),
        )
    except Exception as e:
        logger.warning("[TRACK_GEMINI] DB insert error: %s", e)


async def track_gemini_call(
    duration_ms: float,
    tokens_in: int = 0,
    tokens_out: int = 0,
    error: bool = False,
    call_type: str = "",
    lang: str = "",
) -> None:
    """Insert a Gemini usage row into gemini_tracking (non-blocking)."""
    logger.info(
        "[TRACK_GEMINI] calls+1 tin=%d tout=%d dur=%.0fms type=%s lang=%s",
        tokens_in, tokens_out, duration_ms, call_type, lang,
    )
    try:
        asyncio.create_task(
            _do_track_insert(
                call_type, lang, tokens_in, tokens_out,
                int(duration_ms), int(error),
            )
        )
    except RuntimeError:
        # No running event loop (e.g. during shutdown) — run inline
        await _do_track_insert(
            call_type, lang, tokens_in, tokens_out,
            int(duration_ms), int(error),
        )


async def _get_gemini_counters() -> dict:
    """Read today's Gemini counters from gemini_tracking table (cached 60s)."""
    cached = _local_cache_get("gemini_counters")
    if cached is not None:
        return cached
    defaults = {"calls": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0, "total_ms": 0}
    try:
        row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS calls, "
            "COALESCE(SUM(is_error), 0) AS errors, "
            "COALESCE(SUM(tokens_in), 0) AS tokens_in, "
            "COALESCE(SUM(tokens_out), 0) AS tokens_out, "
            "COALESCE(SUM(duration_ms), 0) AS total_ms "
            "FROM gemini_tracking WHERE ts >= NOW() - INTERVAL 24 HOUR"
        )
        if row:
            result = {
                "calls": int(row["calls"]),
                "errors": int(row["errors"]),
                "tokens_in": int(row["tokens_in"]),
                "tokens_out": int(row["tokens_out"]),
                "total_ms": int(row["total_ms"]),
            }
        else:
            result = defaults
    except Exception as e:
        logger.warning("[GEMINI_COUNTERS] DB read error: %s", e)
        result = defaults
    _local_cache_set("gemini_counters", result)
    return result


# ── Cloud Monitoring fetch ────────────────────────────────────────────────────

async def _fetch_cloud_run_metrics() -> dict:
    """Fetch Cloud Run metrics from Cloud Monitoring API (last 5 min)."""
    try:
        from google.cloud import monitoring_v3
        from google.protobuf.timestamp_pb2 import Timestamp
    except ImportError:
        logger.warning("google-cloud-monitoring not installed — skipping metrics")
        return {}

    project_id = _get_project_id()
    if not project_id:
        logger.warning("GCP project ID not found — skipping metrics")
        return {}

    try:
        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

        now = time.time()
        interval = monitoring_v3.TimeInterval()
        end_ts = Timestamp()
        end_ts.seconds = int(now)
        start_ts = Timestamp()
        start_ts.seconds = int(now - 300)  # 5 minutes
        interval.end_time = end_ts
        interval.start_time = start_ts

        base_filter = (
            f'resource.type="cloud_run_revision" '
            f'AND resource.labels.service_name="{_SERVICE_NAME}" '
            f'AND resource.labels.location="{_LOCATION}"'
        )

        metrics = {}

        # Run blocking gRPC calls in parallel threads
        await asyncio.gather(
            asyncio.to_thread(
                _fetch_request_count, client, project_name, base_filter, interval, metrics),
            asyncio.to_thread(
                _fetch_latencies, client, project_name, base_filter, interval, metrics),
            asyncio.to_thread(
                _fetch_instance_count, client, project_name, base_filter, interval, metrics),
            asyncio.to_thread(
                _fetch_utilization, client, project_name, base_filter, interval, metrics,
                "run.googleapis.com/container/cpu/utilizations", "cpu_utilization"),
            asyncio.to_thread(
                _fetch_utilization, client, project_name, base_filter, interval, metrics,
                "run.googleapis.com/container/memory/utilizations", "memory_utilization"),
        )

        return metrics

    except Exception as e:
        logger.error("Cloud Monitoring API error: %s", e, exc_info=True)
        return {}


def _fetch_request_count(client, project_name, base_filter, interval, metrics):
    """Fetch request count and 5xx error rate."""
    try:
        total_count = 0
        error_count = 0
        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": f'{base_filter} AND metric.type="run.googleapis.com/request_count"',
                "interval": interval,
                "view": 2,  # FULL
            }
        )
        for ts in results:
            code = ts.metric.labels.get("response_code_class", "")
            for point in ts.points:
                total_count += point.value.int64_value
                if code == "5xx":
                    error_count += point.value.int64_value

        # requests per second over 5 min window
        metrics["requests_per_second"] = round(total_count / 300, 2) if total_count else 0
        metrics["error_rate_5xx"] = round(error_count / total_count, 4) if total_count else 0
        metrics["_total_requests_5min"] = total_count
    except Exception as e:
        logger.debug("request_count fetch error: %s", e)


def _fetch_latencies(client, project_name, base_filter, interval, metrics):
    """Fetch P50/P95/P99 latencies."""
    try:
        from google.cloud.monitoring_v3 import Aggregation

        for pct, aligner_name, key in [
            (50, "ALIGN_PERCENTILE_50", "latency_p50_ms"),
            (95, "ALIGN_PERCENTILE_95", "latency_p95_ms"),
            (99, "ALIGN_PERCENTILE_99", "latency_p99_ms"),
        ]:
            agg_copy = Aggregation()
            agg_copy.alignment_period = {"seconds": 300}
            agg_copy.per_series_aligner = getattr(Aggregation.Aligner, aligner_name)

            results = client.list_time_series(
                request={
                    "name": project_name,
                    "filter": f'{base_filter} AND metric.type="run.googleapis.com/request_latencies"',
                    "interval": interval,
                    "view": 2,
                    "aggregation": agg_copy,
                }
            )
            val = 0
            for ts in results:
                for point in ts.points:
                    val = max(val, point.value.double_value)
            metrics[key] = round(val, 1)

    except Exception as e:
        logger.debug("latencies fetch error: %s", e)


def _fetch_instance_count(client, project_name, base_filter, interval, metrics):
    """Fetch active instance count."""
    try:
        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": f'{base_filter} AND metric.type="run.googleapis.com/container/instance_count"',
                "interval": interval,
                "view": 2,
            }
        )
        count = 0
        for ts in results:
            for point in ts.points:
                count = max(count, point.value.int64_value)
        metrics["active_instances"] = count
    except Exception as e:
        logger.debug("instance_count fetch error: %s", e)


def _fetch_utilization(client, project_name, base_filter, interval, metrics, metric_type, key):
    """Fetch CPU or memory utilization (0-1 scale)."""
    try:
        from google.cloud.monitoring_v3 import Aggregation

        agg = Aggregation()
        agg.alignment_period = {"seconds": 300}
        agg.per_series_aligner = Aggregation.Aligner.ALIGN_MEAN

        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": f'{base_filter} AND metric.type="{metric_type}"',
                "interval": interval,
                "view": 2,
                "aggregation": agg,
            }
        )
        values = []
        for ts in results:
            for point in ts.points:
                values.append(point.value.double_value)
        metrics[key] = round(sum(values) / len(values), 4) if values else 0
    except Exception as e:
        logger.debug("%s fetch error: %s", key, e)


# ── Cost estimation ──────────────────────────────────────────────────────────

def _estimate_costs(metrics: dict, gemini: dict) -> dict:
    """Estimate daily costs from metrics and Gemini counters."""
    cfg = COST_CONFIG
    usd_to_eur = cfg["usd_to_eur"]

    # Gemini cost (from real token counts)
    tokens_in = gemini.get("tokens_in", 0)
    tokens_out = gemini.get("tokens_out", 0)
    gemini_usd = (
        tokens_in * cfg["gemini_input_per_1m_usd"] / 1_000_000
        + tokens_out * cfg["gemini_output_per_1m_usd"] / 1_000_000
    )
    gemini_eur = round(gemini_usd * usd_to_eur, 4)

    # Cloud Run cost estimate (based on active instances × 24h)
    instances = metrics.get("active_instances", 1)
    # Estimate: assume instances have been running for proportional day time
    # Use a simple model: instances × seconds_in_day × per-second cost
    seconds_in_day = 86400
    cloud_run_usd = instances * seconds_in_day * (
        cfg["cloud_run_vcpu_count"] * cfg["cloud_run_vcpu_per_sec_usd"]
        + cfg["cloud_run_mem_gib"] * cfg["cloud_run_mem_gib_per_sec_usd"]
    )
    cloud_run_eur = round(cloud_run_usd * usd_to_eur, 2)

    # Cloud SQL flat estimate
    cloud_sql_eur = cfg["cloud_sql_daily_eur"]

    total_eur = round(cloud_run_eur + cloud_sql_eur + gemini_eur, 2)

    return {
        "cloud_run_today_eur": cloud_run_eur,
        "cloud_sql_today_eur": cloud_sql_eur,
        "gemini_today_eur": gemini_eur,
        "total_today_eur": total_eur,
        "estimated_month_eur": round(total_eur * 30, 1),
    }


# ── Main entry point ─────────────────────────────────────────────────────────

async def get_gcp_metrics() -> dict:
    """
    Return full metrics payload. Uses Redis cache (60s).
    Falls back to cached values if Cloud Monitoring API is unavailable.
    """
    # Check cache first
    cached = await cache_get(CACHE_KEY)
    if cached:
        return cached

    # Fetch Cloud Run metrics
    cloud_metrics = await _fetch_cloud_run_metrics()

    # Read Gemini counters from DB
    gem_counters = await _get_gemini_counters()

    # Build metrics section (with defaults)
    m = {
        "requests_per_second": cloud_metrics.get("requests_per_second", 0),
        "error_rate_5xx": cloud_metrics.get("error_rate_5xx", 0),
        "latency_p50_ms": cloud_metrics.get("latency_p50_ms", 0),
        "latency_p95_ms": cloud_metrics.get("latency_p95_ms", 0),
        "latency_p99_ms": cloud_metrics.get("latency_p99_ms", 0),
        "active_instances": cloud_metrics.get("active_instances", 0),
        "cpu_utilization": cloud_metrics.get("cpu_utilization", 0),
        "memory_utilization": cloud_metrics.get("memory_utilization", 0),
    }

    # Gemini section
    calls = gem_counters["calls"]
    total_ms = gem_counters["total_ms"]
    # Cost estimation
    costs = _estimate_costs(m, gem_counters)

    gemini_section = {
        "avg_response_time_ms": round(total_ms / calls) if calls else 0,
        "errors_today": gem_counters["errors"],
        "calls_today": calls,
        "tokens_in_today": gem_counters["tokens_in"],
        "tokens_out_today": gem_counters["tokens_out"],
        "estimated_cost_today_eur": costs["gemini_today_eur"],
    }

    # Status determination
    if not cloud_metrics:
        status = "unknown"
    else:
        status = _determine_status(m["error_rate_5xx"], m["latency_p95_ms"])

    # Check alerts (non-blocking email in background)
    active_alerts = []
    try:
        from services.alerting import process_alerts
        active_alerts = await process_alerts(m, gemini_section, costs)
    except Exception as e:
        logger.debug("Alert check error: %s", e)

    # I16 V66: include circuit breaker state for admin dashboard
    try:
        from services.circuit_breaker import gemini_breaker
        circuit_state = gemini_breaker.state
    except Exception:
        circuit_state = "unknown"

    payload = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": m,
        "gemini": gemini_section,
        "gemini_circuit": circuit_state,
        "costs": costs,
        "active_alerts": active_alerts,
        "redis_connected": _cache._redis is not None,
    }

    # Cache result
    await cache_set(CACHE_KEY, payload, CACHE_TTL)

    # Non-blocking snapshot (every 5 min, cooldown via Redis lock)
    try:
        await _maybe_snapshot(payload)
    except Exception as e:
        logger.debug("Snapshot error: %s", e)

    return payload


# ── Snapshot to metrics_history ──────────────────────────────────────────────

_SNAPSHOT_COOLDOWN = 300  # 5 minutes

async def _maybe_snapshot(payload: dict) -> None:
    """Store a snapshot every 5 min (MySQL lock, works without Redis)."""
    try:
        # Ensure lock row exists (idempotent)
        await db_cloudsql.async_query(
            "INSERT IGNORE INTO metrics_snapshot_lock (id, locked_until) "
            "VALUES (1, '2000-01-01')"
        )
        # Atomic lock: UPDATE only if cooldown expired, check rowcount
        async with db_cloudsql.get_connection() as conn:
            cur = await conn.cursor()
            await cur.execute(
                "UPDATE metrics_snapshot_lock SET locked_until = "
                "DATE_ADD(NOW(), INTERVAL %s SECOND) "
                "WHERE id = 1 AND locked_until <= NOW()",
                (_SNAPSHOT_COOLDOWN,),
            )
            if cur.rowcount == 0:
                return  # cooldown still active (another instance claimed it)
    except Exception as e:
        logger.debug("Snapshot lock error: %s", e)
        return

    m = payload.get("metrics", {})
    g = payload.get("gemini", {})
    c = payload.get("costs", {})
    try:
        await db_cloudsql.async_query(
            "INSERT INTO metrics_history "
            "(requests_per_second, error_rate_5xx, latency_p50_ms, latency_p95_ms, "
            "latency_p99_ms, active_instances, cpu_utilization, memory_utilization, "
            "gemini_calls, gemini_errors, gemini_tokens_in, gemini_tokens_out, "
            "gemini_avg_ms, cost_cloud_run_eur, cost_cloud_sql_eur, cost_gemini_eur, "
            "cost_total_eur) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                m.get("requests_per_second", 0),
                m.get("error_rate_5xx", 0),
                m.get("latency_p50_ms", 0),
                m.get("latency_p95_ms", 0),
                m.get("latency_p99_ms", 0),
                m.get("active_instances", 0),
                m.get("cpu_utilization", 0),
                m.get("memory_utilization", 0),
                g.get("calls_today", 0),
                g.get("errors_today", 0),
                g.get("tokens_in_today", 0),
                g.get("tokens_out_today", 0),
                g.get("avg_response_time_ms", 0),
                c.get("cloud_run_today_eur", 0),
                c.get("cloud_sql_today_eur", 0),
                c.get("gemini_today_eur", 0),
                c.get("total_today_eur", 0),
            ),
        )
    except Exception as e:
        logger.debug("Snapshot insert error: %s", e)


# ── History endpoint helpers ──────────────────────────────────────────────────

async def get_metrics_history(period: str = "24h") -> list[dict]:
    """
    Return metrics_history rows for a given period.
    Aggregates (GROUP BY hour) for periods > 1 day.
    """
    now_sql = "NOW()"
    if period == "7d":
        where = f"ts >= DATE_SUB({now_sql}, INTERVAL 7 DAY)"
        group = True
    elif period == "30d":
        where = f"ts >= DATE_SUB({now_sql}, INTERVAL 30 DAY)"
        group = True
    else:  # 24h
        where = f"ts >= DATE_SUB({now_sql}, INTERVAL 24 HOUR)"
        group = False

    if group:
        sql = (
            "SELECT DATE_FORMAT(ts, '%%Y-%%m-%%d %%H:00') AS ts_label, "
            "AVG(requests_per_second) AS requests_per_second, "
            "AVG(error_rate_5xx) AS error_rate_5xx, "
            "AVG(latency_p50_ms) AS latency_p50_ms, "
            "AVG(latency_p95_ms) AS latency_p95_ms, "
            "AVG(latency_p99_ms) AS latency_p99_ms, "
            "MAX(active_instances) AS active_instances, "
            "AVG(cpu_utilization) AS cpu_utilization, "
            "AVG(memory_utilization) AS memory_utilization, "
            "MAX(gemini_calls) AS gemini_calls, "
            "SUM(gemini_errors) AS gemini_errors, "
            "MAX(gemini_tokens_in) AS gemini_tokens_in, "
            "MAX(gemini_tokens_out) AS gemini_tokens_out, "
            "AVG(gemini_avg_ms) AS gemini_avg_ms, "
            "AVG(cost_cloud_run_eur) AS cost_cloud_run_eur, "
            "AVG(cost_cloud_sql_eur) AS cost_cloud_sql_eur, "
            "AVG(cost_gemini_eur) AS cost_gemini_eur, "
            "AVG(cost_total_eur) AS cost_total_eur "
            f"FROM metrics_history WHERE {where} "
            "GROUP BY ts_label ORDER BY ts_label"
        )
    else:
        sql = (
            "SELECT DATE_FORMAT(ts, '%%Y-%%m-%%d %%H:%%i') AS ts_label, "
            "requests_per_second, error_rate_5xx, "
            "latency_p50_ms, latency_p95_ms, latency_p99_ms, "
            "active_instances, cpu_utilization, memory_utilization, "
            "gemini_calls, gemini_errors, gemini_tokens_in, gemini_tokens_out, "
            "gemini_avg_ms, cost_cloud_run_eur, cost_cloud_sql_eur, "
            "cost_gemini_eur, cost_total_eur "
            f"FROM metrics_history WHERE {where} ORDER BY ts"
        )

    try:
        rows = await db_cloudsql.async_fetchall(sql)
        return [
            {k: (round(float(v), 4) if isinstance(v, (int, float, Decimal)) and k != "ts_label" else
                 (str(v) if v is not None else None))
             for k, v in row.items()}
            for row in rows
        ]
    except Exception as e:
        logger.error("metrics_history query error: %s", e)
        return []


# ── Gemini breakdown (per type / per lang) ────────────────────────────────────

_CALL_TYPES = ["chat_loto", "chat_em", "enrichment_loto", "enrichment_em", "meta_analyse"]
_LANGS = ["fr", "en", "es", "pt", "de", "nl"]

async def get_gemini_breakdown() -> dict:
    """
    Read per-type and per-lang Gemini counters from gemini_tracking table.
    Returns {by_type: [...], by_lang: [...]}.
    Cached locally for 60s.
    """
    cached = _local_cache_get("gemini_breakdown")
    if cached is not None:
        return cached

    result = {"by_type": [], "by_lang": []}
    try:
        # By call_type
        type_rows = await db_cloudsql.async_fetchall(
            "SELECT call_type, COUNT(*) AS calls, "
            "COALESCE(SUM(tokens_in), 0) AS tokens_in, "
            "COALESCE(SUM(tokens_out), 0) AS tokens_out, "
            "COALESCE(SUM(duration_ms), 0) AS total_ms, "
            "COALESCE(SUM(is_error), 0) AS errors "
            "FROM gemini_tracking WHERE ts >= NOW() - INTERVAL 24 HOUR "
            "GROUP BY call_type"
        )
        type_map = {r["call_type"]: r for r in type_rows} if type_rows else {}
        for ct in _CALL_TYPES:
            r = type_map.get(ct, {})
            calls = int(r.get("calls", 0))
            result["by_type"].append({
                "type": ct,
                "calls": calls,
                "tokens_in": int(r.get("tokens_in", 0)),
                "tokens_out": int(r.get("tokens_out", 0)),
                "avg_ms": round(int(r.get("total_ms", 0)) / calls) if calls else 0,
                "errors": int(r.get("errors", 0)),
            })

        # By lang
        lang_rows = await db_cloudsql.async_fetchall(
            "SELECT lang, COUNT(*) AS calls, "
            "COALESCE(SUM(tokens_in), 0) AS tokens_in, "
            "COALESCE(SUM(tokens_out), 0) AS tokens_out "
            "FROM gemini_tracking WHERE ts >= NOW() - INTERVAL 24 HOUR "
            "GROUP BY lang"
        )
        lang_map = {r["lang"]: r for r in lang_rows} if lang_rows else {}
        for lang in _LANGS:
            r = lang_map.get(lang, {})
            result["by_lang"].append({
                "lang": lang,
                "calls": int(r.get("calls", 0)),
                "tokens_in": int(r.get("tokens_in", 0)),
                "tokens_out": int(r.get("tokens_out", 0)),
            })
    except Exception as e:
        logger.warning("[GEMINI_BREAKDOWN] DB error: %s", e)

    _local_cache_set("gemini_breakdown", result)
    return result


# ── Cleanup (retention 90 days) — I11 V66: batched DELETE ─────────────────────

_CLEANUP_BATCH_SIZE = 10_000
_CLEANUP_MAX_ITERATIONS = 100


async def _batched_cleanup(table: str, ts_column: str, days: int, batch_size: int = _CLEANUP_BATCH_SIZE) -> int:
    """I11 V66: Delete old rows in batches to avoid long table locks.

    Loops DELETE ... LIMIT batch_size until no more rows match.
    Safety cap: max 100 iterations to prevent infinite loop.
    Returns total rows deleted.
    """
    total = 0
    batches = 0
    sql = f"DELETE FROM {table} WHERE {ts_column} < DATE_SUB(NOW(), INTERVAL %s DAY) LIMIT {batch_size}"
    try:
        for _ in range(_CLEANUP_MAX_ITERATIONS):
            async with db_cloudsql.get_connection() as conn:
                cur = await conn.cursor()
                await cur.execute(sql, (days,))
                deleted = cur.rowcount
            if deleted == 0:
                break
            total += deleted
            batches += 1
            await asyncio.sleep(0.1)
    except Exception as e:
        logger.warning("[CLEANUP] %s error after %d rows in %d batches: %s", table, total, batches, e)
        return total
    if total > 0:
        logger.info("[CLEANUP] %s: %d rows deleted in %d batches (older than %d days)", table, total, batches, days)
    return total


async def cleanup_metrics_history(days: int = 90) -> int:
    """Delete metrics_history rows older than *days* in batches."""
    return await _batched_cleanup("metrics_history", "ts", days)


async def cleanup_event_log(days: int = 90) -> int:
    """Delete event_log rows older than *days* in batches."""
    return await _batched_cleanup("event_log", "created_at", days)


async def cleanup_chat_log(days: int = 90) -> int:
    """Delete chat_log rows older than *days* in batches."""
    return await _batched_cleanup("chat_log", "created_at", days)


async def cleanup_gemini_tracking(days: int = 90) -> int:
    """Delete gemini_tracking rows older than *days* in batches."""
    return await _batched_cleanup("gemini_tracking", "ts", days)
