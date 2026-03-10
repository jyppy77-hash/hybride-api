"""
GCP Monitoring — Cloud Run metrics + Gemini tracking + cost estimation.

Fetches real-time Cloud Run metrics via Cloud Monitoring API,
reads Gemini usage counters from Redis, estimates daily costs.

Cache: 60s Redis (key "gcp_metrics") to avoid spamming Google API.
"""

import logging
import os
import time
from datetime import datetime, timezone

from services.cache import cache_get, cache_set, _redis, _REDIS_PREFIX

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

# Gemini Redis keys (incremented by tracking helper)
_GEMINI_KEYS = {
    "calls": "gemini:calls_today",
    "errors": "gemini:errors_today",
    "tokens_in": "gemini:tokens_in_today",
    "tokens_out": "gemini:tokens_out_today",
    "total_ms": "gemini:total_ms_today",
}

_GEMINI_TTL = 86400  # 24h — auto-reset daily


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

async def track_gemini_call(
    duration_ms: float,
    tokens_in: int = 0,
    tokens_out: int = 0,
    error: bool = False,
) -> None:
    """Increment Gemini usage counters in Redis. Safe no-op if Redis unavailable."""
    if not _redis:
        return
    try:
        pipe = _redis.pipeline(transaction=False)
        key_prefix = _REDIS_PREFIX
        pipe.incr(f"{key_prefix}{_GEMINI_KEYS['calls']}")
        if error:
            pipe.incr(f"{key_prefix}{_GEMINI_KEYS['errors']}")
        if tokens_in > 0:
            pipe.incrby(f"{key_prefix}{_GEMINI_KEYS['tokens_in']}", tokens_in)
        if tokens_out > 0:
            pipe.incrby(f"{key_prefix}{_GEMINI_KEYS['tokens_out']}", tokens_out)
        pipe.incrby(f"{key_prefix}{_GEMINI_KEYS['total_ms']}", int(duration_ms))
        await pipe.execute()
        # Set TTL on all keys (idempotent)
        for k in _GEMINI_KEYS.values():
            await _redis.expire(f"{key_prefix}{k}", _GEMINI_TTL)
    except Exception as e:
        logger.debug("Gemini tracking Redis error: %s", e)


async def _get_gemini_counters() -> dict:
    """Read Gemini counters from Redis. Returns zeros if unavailable."""
    defaults = {"calls": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0, "total_ms": 0}
    if not _redis:
        return defaults
    try:
        pipe = _redis.pipeline(transaction=False)
        for k in _GEMINI_KEYS.values():
            pipe.get(f"{_REDIS_PREFIX}{k}")
        results = await pipe.execute()
        keys = list(_GEMINI_KEYS.keys())
        return {keys[i]: int(results[i] or 0) for i in range(len(keys))}
    except Exception as e:
        logger.debug("Gemini counters Redis error: %s", e)
        return defaults


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

        # Request count (total + 5xx)
        _fetch_request_count(client, project_name, base_filter, interval, metrics)
        # Latencies
        _fetch_latencies(client, project_name, base_filter, interval, metrics)
        # Instance count
        _fetch_instance_count(client, project_name, base_filter, interval, metrics)
        # CPU utilization
        _fetch_utilization(client, project_name, base_filter, interval, metrics,
                          "run.googleapis.com/container/cpu/utilizations", "cpu_utilization")
        # Memory utilization
        _fetch_utilization(client, project_name, base_filter, interval, metrics,
                          "run.googleapis.com/container/memory/utilizations", "memory_utilization")

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

        agg = Aggregation()
        agg.alignment_period = {"seconds": 300}
        agg.per_series_aligner = Aggregation.Aligner.ALIGN_PERCENTILE_50

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

    # Read Gemini counters from Redis
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
    gemini_section = {
        "avg_response_time_ms": round(total_ms / calls) if calls else 0,
        "errors_last_hour": gem_counters["errors"],
        "calls_today": calls,
        "tokens_in_today": gem_counters["tokens_in"],
        "tokens_out_today": gem_counters["tokens_out"],
        "estimated_cost_today_eur": 0,
    }

    # Cost estimation
    costs = _estimate_costs(m, gem_counters)
    gemini_section["estimated_cost_today_eur"] = costs["gemini_today_eur"]

    # Status determination
    if not cloud_metrics:
        status = "unknown"
    else:
        status = _determine_status(m["error_rate_5xx"], m["latency_p95_ms"])

    payload = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": m,
        "gemini": gemini_section,
        "costs": costs,
    }

    # Cache result
    await cache_set(CACHE_KEY, payload, CACHE_TTL)

    return payload
