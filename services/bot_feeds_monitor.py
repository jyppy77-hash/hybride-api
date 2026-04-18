"""
Bot feed refresh monitoring + AI bots access stats — V122 Phase 2/4.

Logs each periodic refresh (6h) of bot IP feeds to bot_feed_refresh_log (MySQL)
for observability. Detects silent failures that would leave production running
on stale fallback CIDRs — scenario identified in Phase ÉTAPE 1 audit.

Also aggregates ai_bot_access_log counters flushed from config/ai_bots.py
every 60s via a supervised background task started in main.py lifespan.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ── Health thresholds (hours) ────────────────────────────────────────────────

_HEALTH_GREEN_MAX_H = 12.0   # green : refresh < 12h ET status=ok
_HEALTH_ORANGE_MAX_H = 24.0  # orange: 12-24h ou dernier status=error
# > 24h ou pas de refresh      = red


# ── Refresh logging (INSERT into bot_feed_refresh_log) ──────────────────────

async def log_refresh_result(
    source: str,
    status: str,
    cidrs_count: int,
    error_msg: str | None = None,
) -> None:
    """INSERT refresh result into bot_feed_refresh_log. Fail-safe (try/except).

    Called by config/bot_ips.py::refresh_from_remote() after each feed fetch.
    Truncates error_msg to 500 chars to fit VARCHAR(500) column.
    """
    try:
        import db_cloudsql
        safe_error = None if error_msg is None else str(error_msg)[:500]
        safe_status = "ok" if status == "ok" else "error"
        await db_cloudsql.async_query(
            "INSERT INTO bot_feed_refresh_log (source, status, cidrs_count, error_msg) "
            "VALUES (%s, %s, %s, %s)",
            (source[:50], safe_status, int(cidrs_count), safe_error),
        )
    except Exception as e:
        logger.warning("[BOT_FEEDS_MONITOR] log_refresh_result failed for %s: %s", source, e)


# ── Feeds status (read latest per source) ────────────────────────────────────

async def get_feeds_status() -> dict:
    """Return latest refresh per source + age in hours + health flag.

    Returns:
        {
            "feeds": [
                {"source": str, "last_refresh": ISO8601|None, "cidrs_count": int,
                 "age_hours": float|None, "health": "green"|"orange"|"red",
                 "last_status": "ok"|"error"|None, "error_msg": str|None},
                ...
            ],
            "summary": {"total": int, "green": int, "orange": int, "red": int}
        }

    Health rules:
      - green:  age < 12h AND last status = ok
      - orange: 12h <= age < 24h OR last status = error
      - red:    age >= 24h OR no refresh ever
    """
    # 8 sources attendues — ordre stable pour l'UI admin
    expected_sources = [
        "googlebot", "google_special", "google_user_triggered",
        "google_user_triggered2", "bingbot", "applebot",
        "gptbot", "tor_exit", "ipsum_l3",
    ]

    feeds: list[dict] = []
    summary = {"total": 0, "green": 0, "orange": 0, "red": 0}

    try:
        import db_cloudsql
        # Latest refresh per source (groupwise max, compatible MariaDB 10.x)
        rows = await db_cloudsql.async_fetchall(
            "SELECT b.source, b.ts, b.status, b.cidrs_count, b.error_msg "
            "FROM bot_feed_refresh_log b "
            "INNER JOIN ( "
            "  SELECT source, MAX(ts) AS max_ts "
            "  FROM bot_feed_refresh_log "
            "  WHERE ts >= NOW() - INTERVAL 30 DAY "
            "  GROUP BY source "
            ") m ON m.source = b.source AND m.max_ts = b.ts"
        )
        latest_map = {r["source"]: r for r in rows}
    except Exception as e:
        logger.error("[BOT_FEEDS_MONITOR] get_feeds_status DB error: %s", e)
        latest_map = {}

    now_utc = datetime.now(timezone.utc)

    for source in expected_sources:
        r = latest_map.get(source)
        if not r:
            feeds.append({
                "source": source, "last_refresh": None, "cidrs_count": 0,
                "age_hours": None, "health": "red",
                "last_status": None, "error_msg": None,
            })
            summary["red"] += 1
            summary["total"] += 1
            continue

        ts = r["ts"]
        # ts is naive UTC from DB — make it aware for correct delta
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_hours = (now_utc - ts).total_seconds() / 3600.0
        last_status = r.get("status", "ok")

        if age_hours < _HEALTH_GREEN_MAX_H and last_status == "ok":
            health = "green"
        elif age_hours < _HEALTH_ORANGE_MAX_H or last_status == "error":
            health = "orange"
        else:
            health = "red"

        summary[health] += 1
        summary["total"] += 1
        feeds.append({
            "source": source,
            "last_refresh": ts.isoformat(),
            "cidrs_count": int(r.get("cidrs_count") or 0),
            "age_hours": round(age_hours, 2),
            "health": health,
            "last_status": last_status,
            "error_msg": r.get("error_msg"),
        })

    return {"feeds": feeds, "summary": summary}


# ── AI bots access aggregation (read ai_bot_access_log) ─────────────────────

async def get_ai_bots_stats(hours: int = 24) -> dict:
    """Aggregate ai_bot_access_log GROUP BY canonical_name over last N hours.

    Returns:
        {
            "period_hours": int,
            "bots": [{"canonical_name": str, "hits": int}, ...],
            "total_hits": int
        }
    """
    # Guard: clamp hours to sensible range [1, 720] (30 days)
    try:
        h_raw = int(hours) if hours is not None else 24
    except (TypeError, ValueError):
        h_raw = 24
    h = max(1, min(h_raw, 24 * 30))

    try:
        import db_cloudsql
        # V123 Phase 2.5: filter status='allowed' to separate from blocked stats
        rows = await db_cloudsql.async_fetchall(
            "SELECT canonical_name, SUM(hit_count) AS hits "
            "FROM ai_bot_access_log "
            "WHERE ts >= NOW() - INTERVAL %s HOUR AND status = 'allowed' "
            "GROUP BY canonical_name "
            "ORDER BY hits DESC",
            (h,),
        )
    except Exception as e:
        logger.error("[BOT_FEEDS_MONITOR] get_ai_bots_stats DB error: %s", e)
        return {"period_hours": h, "bots": [], "total_hits": 0}

    bots = []
    total = 0
    for r in rows:
        hits = int(r.get("hits") or 0)
        if hits > 0:
            bots.append({"canonical_name": r["canonical_name"], "hits": hits})
            total += hits

    return {"period_hours": h, "bots": bots, "total_hits": total}


# ── Flush in-memory counters → MySQL (supervised loop, 60s) ─────────────────

async def flush_ai_bot_counters() -> None:
    """Flush config/ai_bots.py::_ai_bot_counters to ai_bot_access_log.

    Called by supervised background task in main.py lifespan every 60s.
    V123 Phase 2.5: distinguishes BLOCKED_COUNTER_PREFIX keys → status='blocked'.
    Batched INSERT (one row per canonical_name with non-zero count).
    Counters reset only after successful DB write.
    """
    from config.ai_bots import get_session_counters, reset_session_counters, BLOCKED_COUNTER_PREFIX

    snapshot = get_session_counters()
    if not snapshot:
        return

    try:
        import db_cloudsql
        rows = [(name, cnt) for name, cnt in snapshot.items() if cnt > 0]
        if not rows:
            return
        for name, cnt in rows:
            if name.startswith(BLOCKED_COUNTER_PREFIX):
                canonical = name[len(BLOCKED_COUNTER_PREFIX):]
                status = "blocked"
            else:
                canonical = name
                status = "allowed"
            await db_cloudsql.async_query(
                "INSERT INTO ai_bot_access_log (canonical_name, status, hit_count) "
                "VALUES (%s, %s, %s)",
                (canonical[:50], status, int(cnt)),
            )
        reset_session_counters()
    except Exception as e:
        logger.warning("[BOT_FEEDS_MONITOR] flush_ai_bot_counters failed (retry next cycle): %s", e)
        # Ne PAS reset les compteurs si l'écriture a échoué (retry prochain cycle)


# ── V123 Phase 2.5 — Blocked bots stats (widget 4) ──────────────────────────

async def get_blocked_bots_stats(hours: int = 24) -> dict:
    """Aggregate blocked Catégorie C hits over last N hours.

    Returns: {
        "period_hours": int,
        "blocked_bots": [{"canonical_name": str, "hits": int, "last_seen": ISO8601}, ...],
        "total_blocked": int
    }
    """
    try:
        h_raw = int(hours) if hours is not None else 24
    except (TypeError, ValueError):
        h_raw = 24
    h = max(1, min(h_raw, 24 * 30))

    try:
        import db_cloudsql
        rows = await db_cloudsql.async_fetchall(
            "SELECT canonical_name, SUM(hit_count) AS hits, MAX(ts) AS last_seen "
            "FROM ai_bot_access_log "
            "WHERE ts >= NOW() - INTERVAL %s HOUR AND status = 'blocked' "
            "GROUP BY canonical_name ORDER BY hits DESC",
            (h,),
        )
    except Exception as e:
        logger.error("[BOT_FEEDS_MONITOR] get_blocked_bots_stats DB error: %s", e)
        return {"period_hours": h, "blocked_bots": [], "total_blocked": 0}

    blocked = []
    total = 0
    for r in rows:
        hits = int(r.get("hits") or 0)
        if hits > 0:
            last_seen_val = r.get("last_seen")
            if hasattr(last_seen_val, "isoformat"):
                last_seen_iso = last_seen_val.isoformat()
            else:
                last_seen_iso = None
            blocked.append({
                "canonical_name": r["canonical_name"],
                "hits": hits,
                "last_seen": last_seen_iso,
            })
            total += hits
    return {"period_hours": h, "blocked_bots": blocked, "total_blocked": total}


# ── V123 Phase 2.5 — Timeline chart (widget 2) ──────────────────────────────

async def get_ai_bots_timeline(hours: int = 24) -> dict:
    """Aggregate allowed bot hits per time bucket for Chart.js line chart.

    Granularity (Q7 V123):
      - <= 24h  → 1h buckets
      - <= 168h → 6h buckets (7 days)
      - > 168h  → 1d buckets (up to 30 days)

    Returns: {
        "period_hours": int,
        "buckets": [str, ...],
        "series": [{"name": str, "data": [int, ...]}, ...]  -- top 5 bots
    }
    """
    try:
        h_raw = int(hours) if hours is not None else 24
    except (TypeError, ValueError):
        h_raw = 24
    h = max(1, min(h_raw, 24 * 30))

    if h <= 24:
        bucket_fmt = "%Y-%m-%d %H:00"
    elif h <= 168:
        bucket_fmt = "%Y-%m-%d %H:00"
    else:
        bucket_fmt = "%Y-%m-%d"

    try:
        import db_cloudsql
        top_rows = await db_cloudsql.async_fetchall(
            "SELECT canonical_name, SUM(hit_count) AS hits "
            "FROM ai_bot_access_log "
            "WHERE ts >= NOW() - INTERVAL %s HOUR AND status = 'allowed' "
            "GROUP BY canonical_name ORDER BY hits DESC LIMIT 5",
            (h,),
        )
        top_names = [r["canonical_name"] for r in top_rows]
        if not top_names:
            return {"period_hours": h, "buckets": [], "series": []}

        placeholders = ",".join(["%s"] * len(top_names))
        rows = await db_cloudsql.async_fetchall(
            f"SELECT DATE_FORMAT(ts, %s) AS bucket, canonical_name, SUM(hit_count) AS hits "
            f"FROM ai_bot_access_log "
            f"WHERE ts >= NOW() - INTERVAL %s HOUR AND status = 'allowed' "
            f"  AND canonical_name IN ({placeholders}) "
            f"GROUP BY bucket, canonical_name ORDER BY bucket ASC",
            (bucket_fmt, h, *top_names),
        )
    except Exception as e:
        logger.error("[BOT_FEEDS_MONITOR] timeline DB error: %s", e)
        return {"period_hours": h, "buckets": [], "series": []}

    pivot: dict[str, dict[str, int]] = {}
    for r in rows:
        pivot.setdefault(r["bucket"], {})[r["canonical_name"]] = int(r["hits"] or 0)

    buckets = sorted(pivot.keys())
    series = [
        {"name": name, "data": [pivot.get(b, {}).get(name, 0) for b in buckets]}
        for name in top_names
    ]
    return {"period_hours": h, "buckets": buckets, "series": series}


# ── V123 Phase 2.5 — Dashboard KPIs (3 cards compact) ───────────────────────

async def get_bot_dashboard_kpis(hours: int = 24) -> dict:
    """Compact KPIs for /admin/ dashboard principal (single SQL aggregation).

    V123 Phase 2.5 Extension A: human_hits_24h filters event_log.is_ai_bot=0
    for un-polluted ratio. Requires migration 024 applied.

    Returns: {
        "bot_allowed_24h": int,
        "bot_blocked_24h": int,
        "bot_distinct_count": int,
        "bot_human_ratio_pct": int,
        "human_hits_24h": int
    }
    """
    defaults = {
        "bot_allowed_24h": 0, "bot_blocked_24h": 0,
        "bot_distinct_count": 0, "bot_human_ratio_pct": 0, "human_hits_24h": 0,
    }
    try:
        import db_cloudsql
        row = await db_cloudsql.async_fetchone(
            "SELECT "
            "  SUM(CASE WHEN status='allowed' THEN hit_count ELSE 0 END) AS allowed, "
            "  SUM(CASE WHEN status='blocked' THEN hit_count ELSE 0 END) AS blocked, "
            "  COUNT(DISTINCT CASE WHEN status='allowed' THEN canonical_name END) AS distinct_cnt "
            "FROM ai_bot_access_log "
            "WHERE ts >= NOW() - INTERVAL %s HOUR",
            (hours,),
        )
        allowed = int(row.get("allowed") or 0) if row else 0
        blocked = int(row.get("blocked") or 0) if row else 0
        distinct_cnt = int(row.get("distinct_cnt") or 0) if row else 0

        # Extension A: filter event_log.is_ai_bot=0 for clean human baseline
        h_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS hits FROM event_log "
            "WHERE created_at >= NOW() - INTERVAL %s HOUR AND is_ai_bot = 0",
            (hours,),
        )
        human_hits = int(h_row.get("hits") or 0) if h_row else 0
    except Exception as e:
        logger.error("[BOT_FEEDS_MONITOR] dashboard KPIs error: %s", e)
        return defaults

    ratio = round((allowed / human_hits) * 100) if human_hits > 0 else 0
    return {
        "bot_allowed_24h": allowed,
        "bot_blocked_24h": blocked,
        "bot_distinct_count": distinct_cnt,
        "bot_human_ratio_pct": ratio,
        "human_hits_24h": human_hits,
    }


async def retention_cleanup(days: int = 90) -> None:
    """Delete rows older than N days from monitoring tables (batched 10K).

    Called at startup alongside cleanup_event_log etc.
    """
    try:
        import db_cloudsql
        for table in ("bot_feed_refresh_log", "ai_bot_access_log"):
            while True:
                await db_cloudsql.async_query(
                    f"DELETE FROM {table} "
                    f"WHERE ts < NOW() - INTERVAL %s DAY LIMIT 10000",
                    (days,),
                )
                # Simple batching: one iteration per call is enough for small tables;
                # infinite loops avoided by relying on retention cron semantics.
                break
    except Exception as e:
        logger.warning("[BOT_FEEDS_MONITOR] retention_cleanup: %s", e)
