"""
Admin monitoring — realtime, activity, messages, chatbot monitor, GCP metrics, IP bans.
========================================================================================
Split from routes/admin.py (Phase 2 refacto V88).
"""

import csv
import io
import logging

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

import db_cloudsql
from config.templates import env
from rate_limit import limiter  # S15 V94
from routes.admin_helpers import (
    require_auth as _require_auth,
    require_auth_json as _require_auth_json,
    dec as _dec,
    period_to_dates as _period_to_dates,
    PERIOD_SQL as _PERIOD_SQL,
    PERIOD_LABELS as _PERIOD_LABELS,
    CM_PERIOD_SQL as _CM_PERIOD_SQL,
    VALID_LANGS as _VALID_LANGS,
    build_realtime_where as _build_realtime_where,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


# ── Realtime feed ─────────────────────────────────────────────────────────────

@router.get("/admin/realtime", response_class=HTMLResponse, include_in_schema=False)
async def admin_realtime_page(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    tpl = env.get_template("admin/realtime.html")
    return HTMLResponse(tpl.render(active="realtime"))


@router.get("/admin/api/realtime", include_in_schema=False)
async def admin_api_realtime(request: Request, event_type: str = "all", period: str = "24h"):
    err = _require_auth_json(request)
    if err:
        return err
    if period not in _PERIOD_SQL:
        period = "24h"
    try:
        where, params = _build_realtime_where(event_type, period)

        # Last 100 events
        rows = await db_cloudsql.async_fetchall(
            f"SELECT event_type, page, module, lang, device, country, created_at "
            f"FROM event_log {where} ORDER BY created_at DESC LIMIT 100",
            tuple(params),
        )
        events = []
        for r in rows:
            events.append({
                "event_type": r["event_type"],
                "page": r.get("page", ""),
                "module": r.get("module", ""),
                "lang": r.get("lang", ""),
                "device": r.get("device", ""),
                "country": r.get("country", ""),
                "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r.get("created_at") else "",
            })

        # KPI
        kpi_row = await db_cloudsql.async_fetchone(
            f"SELECT "
            f"  COUNT(*) AS total_count, "
            f"  SUM(CASE WHEN created_at >= NOW() - INTERVAL 1 HOUR THEN 1 ELSE 0 END) AS hour_count, "
            f"  COUNT(DISTINCT event_type) AS type_count, "
            f"  COUNT(DISTINCT session_hash) AS unique_visitors "
            f"FROM event_log {where}",
            tuple(params),
        )
        kpi = {
            "total": _dec(kpi_row["total_count"]) if kpi_row else 0,
            "hour": _dec(kpi_row["hour_count"]) if kpi_row else 0,
            "types": _dec(kpi_row["type_count"]) if kpi_row else 0,
            "unique_visitors": _dec(kpi_row["unique_visitors"]) if kpi_row else 0,
        }

        # Counts by event type (for KPI cards)
        bt_rows = await db_cloudsql.async_fetchall(
            f"SELECT event_type, COUNT(*) AS cnt FROM event_log {where} GROUP BY event_type ORDER BY cnt DESC",
            tuple(params),
        )
        by_type = {r["event_type"]: _dec(r["cnt"]) for r in bt_rows}

        # Distinct event types for filter dropdown (bounded to 30 days)
        type_rows = await db_cloudsql.async_fetchall(
            "SELECT DISTINCT event_type FROM event_log "
            "WHERE created_at >= NOW() - INTERVAL 30 DAY ORDER BY event_type"
        )
        event_types = [r["event_type"] for r in type_rows]

        return JSONResponse({"events": events, "kpi": kpi, "by_type": by_type, "event_types": event_types})
    except Exception as e:
        logger.error("[ADMIN] realtime: %s", e)
        return JSONResponse({"events": [], "kpi": {"total": 0, "hour": 0, "types": 0, "unique_visitors": 0}, "by_type": {}, "event_types": []})


# ── Realtime exports ──────────────────────────────────────────────────────────

@router.get("/admin/export/realtime/csv", include_in_schema=False)
@limiter.limit("30/minute")  # S15 V94
async def admin_export_realtime_csv(request: Request, event_type: str = "all", period: str = "24h"):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    if period not in _PERIOD_SQL:
        period = "24h"
    try:
        where, params = _build_realtime_where(event_type, period)
        rows = await db_cloudsql.async_fetchall(
            f"SELECT event_type, page, module, lang, device, country, created_at "
            f"FROM event_log {where} ORDER BY created_at DESC LIMIT 5000",
            tuple(params),
        )
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["event_type", "page", "module", "lang", "device", "country", "created_at"])
        for r in rows:
            w.writerow([
                r["event_type"], r.get("page", ""), r.get("module", ""),
                r.get("lang", ""), r.get("device", ""), r.get("country", ""),
                r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r.get("created_at") else "",
            ])
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=realtime_{period}.csv"},
        )
    except Exception as e:
        logger.error("[ADMIN] realtime CSV: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/admin/export/realtime/pdf", include_in_schema=False)
@limiter.limit("30/minute")  # S15 V94
async def admin_export_realtime_pdf(request: Request, event_type: str = "all", period: str = "24h"):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    if period not in _PERIOD_SQL:
        period = "24h"
    try:
        where, params = _build_realtime_where(event_type, period)

        kpi_row = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(*) AS total_count, "
            f"SUM(CASE WHEN created_at >= NOW() - INTERVAL 1 HOUR THEN 1 ELSE 0 END) AS hour_count, "
            f"COUNT(DISTINCT event_type) AS type_count "
            f"FROM event_log {where}",
            tuple(params),
        )
        kpi = {
            "total": _dec(kpi_row["total_count"]) if kpi_row else 0,
            "hour": _dec(kpi_row["hour_count"]) if kpi_row else 0,
            "types": _dec(kpi_row["type_count"]) if kpi_row else 0,
        }

        bt_rows = await db_cloudsql.async_fetchall(
            f"SELECT event_type, COUNT(*) AS cnt FROM event_log {where} GROUP BY event_type ORDER BY cnt DESC",
            tuple(params),
        )
        by_type = {r["event_type"]: _dec(r["cnt"]) for r in bt_rows}

        rows = await db_cloudsql.async_fetchall(
            f"SELECT event_type, page, module, lang, device, country, created_at "
            f"FROM event_log {where} ORDER BY created_at DESC LIMIT 200",
            tuple(params),
        )
        table_data = []
        for r in rows:
            table_data.append({
                "event_type": r["event_type"], "page": r.get("page", ""),
                "module": r.get("module", ""), "lang": r.get("lang", ""),
                "device": r.get("device", ""), "country": r.get("country", ""),
                "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r.get("created_at") else "",
            })

        from services.admin_pdf import generate_realtime_report_pdf
        period_label = _PERIOD_LABELS.get(period, period)
        buf = generate_realtime_report_pdf(kpi, by_type, table_data, period_label)
        return StreamingResponse(
            buf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=realtime_{period}.pdf"},
        )
    except Exception as e:
        logger.error("[ADMIN] realtime PDF: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── GCP Monitoring ────────────────────────────────────────────────────────────

@router.get("/admin/api/gcp-metrics", include_in_schema=False)
async def admin_api_gcp_metrics(request: Request):
    """Real-time Cloud Run metrics + Gemini tracking + cost estimation."""
    err = _require_auth_json(request)
    if err:
        return err
    try:
        from services.gcp_monitoring import get_gcp_metrics
        data = await get_gcp_metrics()
        return JSONResponse(data)
    except Exception as e:
        logger.error("[ADMIN] gcp-metrics: %s", e)
        return JSONResponse({"status": "unknown", "error": str(e)}, status_code=500)


@router.get("/admin/api/gcp-metrics/history", include_in_schema=False)
async def admin_api_gcp_metrics_history(request: Request):
    """Historical metrics for Chart.js graphs."""
    err = _require_auth_json(request)
    if err:
        return err
    period = request.query_params.get("period", "24h")
    if period not in ("24h", "7d", "30d"):
        period = "24h"
    try:
        from services.gcp_monitoring import get_metrics_history
        data = await get_metrics_history(period)
        return JSONResponse({"period": period, "points": data})
    except Exception as e:
        logger.error("[ADMIN] gcp-metrics-history: %s", e)
        return JSONResponse({"period": period, "points": []}, status_code=500)


@router.get("/admin/api/gemini-breakdown", include_in_schema=False)
async def admin_api_gemini_breakdown(request: Request):
    """Gemini usage breakdown by type and language."""
    err = _require_auth_json(request)
    if err:
        return err
    try:
        from services.gcp_monitoring import get_gemini_breakdown
        data = await get_gemini_breakdown()
        return JSONResponse(data)
    except Exception as e:
        logger.error("[ADMIN] gemini-breakdown: %s", e)
        return JSONResponse({"by_type": [], "by_lang": []}, status_code=500)


@router.get("/admin/monitoring", include_in_schema=False)
async def admin_monitoring_page(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    tpl = env.get_template("admin/monitoring.html")
    return HTMLResponse(tpl.render(active="monitoring"))


# I16 V66: Circuit breaker admin reset
@router.post("/admin/api/circuit-breaker/reset", include_in_schema=False)
async def admin_circuit_breaker_reset(request: Request):
    """Force Gemini circuit breaker to CLOSED state."""
    err = _require_auth_json(request)
    if err:
        return err
    from utils import get_client_ip
    real_ip = get_client_ip(request)
    from services.circuit_breaker import gemini_breaker
    prev_state = gemini_breaker.state
    gemini_breaker.force_close()
    logger.info("[ADMIN_AUDIT] action=circuit_breaker_reset ip=%s prev_state=%s", real_ip, prev_state)
    return JSONResponse({"status": "closed", "previous_state": prev_state, "message": "Circuit breaker reset"})


# V94 hotfix: Decay state admin update
@router.post("/admin/api/decay/update", include_in_schema=False)
async def admin_decay_update(request: Request):
    """Trigger decay state update for both games (auto-detects new draws)."""
    err = _require_auth_json(request)
    if err:
        return err
    from utils import get_client_ip
    real_ip = get_client_ip(request)
    from services.decay_state import check_and_update_decay
    results = {}
    try:
        async with db_cloudsql.get_connection() as conn:
            results["loto"] = await check_and_update_decay(conn, "loto", "tirages")
        async with db_cloudsql.get_connection() as conn:
            results["euromillions"] = await check_and_update_decay(conn, "euromillions", "tirages_euromillions")
    except Exception as e:
        logger.error("[ADMIN] decay update error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)
    logger.info("[ADMIN_AUDIT] action=decay_update ip=%s results=%s", real_ip, results)
    return JSONResponse({"status": "ok", "results": results})


# ── Activity monitor ─────────────────────────────────────────────────────────

@router.get("/admin/activity", response_class=HTMLResponse, include_in_schema=False)
async def admin_activity_page(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    tpl = env.get_template("admin/activity.html")
    return HTMLResponse(tpl.render(active="activity"))


@router.get("/admin/api/activity", include_in_schema=False)
async def admin_api_activity(request: Request, minutes: int = 5):
    err = _require_auth_json(request)
    if err:
        return err
    if minutes < 1 or minutes > 60:
        minutes = 5
    try:
        rows = await db_cloudsql.async_fetchall(
            "SELECT session_hash, MAX(country) AS country, MAX(device) AS device, "
            "MAX(page) AS page, MAX(lang) AS lang, MAX(event_type) AS event_type, "
            "COUNT(*) AS hits, MAX(created_at) AS last_seen, MIN(created_at) AS first_seen "
            "FROM event_log "
            "WHERE created_at >= NOW() - INTERVAL %s MINUTE "
            "GROUP BY session_hash "
            "ORDER BY last_seen DESC LIMIT 100",
            (minutes,),
        )
        sessions = []
        for r in rows:
            sessions.append({
                "session_hash": r["session_hash"][:8] if r.get("session_hash") else "—",
                "country": r.get("country", ""),
                "device": r.get("device", ""),
                "lang": r.get("lang", ""),
                "last_page": r.get("page", ""),
                "hits": _dec(r["hits"]),
                "last_seen": r["last_seen"].strftime("%Y-%m-%d %H:%M:%S") if r.get("last_seen") else "",
                "first_seen": r["first_seen"].strftime("%Y-%m-%d %H:%M:%S") if r.get("first_seen") else "",
            })

        # Pages detail per session (top 10 sessions only)
        top_hashes = [r["session_hash"] for r in rows[:10] if r.get("session_hash")]
        pages_map = {}
        if top_hashes:
            ph = ",".join(["%s"] * len(top_hashes))
            page_rows = await db_cloudsql.async_fetchall(
                f"SELECT session_hash, page FROM event_log "
                f"WHERE created_at >= NOW() - INTERVAL %s MINUTE "
                f"AND session_hash IN ({ph}) "
                f"ORDER BY created_at ASC",
                (minutes, *top_hashes),
            )
            for pr in page_rows:
                h = pr["session_hash"][:8] if pr.get("session_hash") else ""
                pages_map.setdefault(h, [])
                p = pr.get("page", "")
                if p and (not pages_map[h] or pages_map[h][-1] != p):
                    pages_map[h].append(p)

        for s in sessions:
            s["pages"] = pages_map.get(s["session_hash"], [])

        return JSONResponse({
            "total": len(sessions),
            "minutes": minutes,
            "active_sessions": sessions,
        })
    except Exception as e:
        logger.error("[ADMIN] activity: %s", e)
        return JSONResponse({"total": 0, "minutes": minutes, "active_sessions": []})


@router.get("/admin/api/activity/history", include_in_schema=False)
async def admin_api_activity_history(request: Request, hours: int = 24):
    err = _require_auth_json(request)
    if err:
        return err
    if hours < 1 or hours > 72:
        hours = 24
    try:
        rows = await db_cloudsql.async_fetchall(
            "SELECT session_hash, MAX(country) AS country, MAX(device) AS device, MAX(lang) AS lang, "
            "GROUP_CONCAT(DISTINCT event_type) AS event_types, "
            "COUNT(*) AS hits, "
            "MAX(created_at) AS last_seen, MIN(created_at) AS first_seen, "
            "SUBSTRING_INDEX(GROUP_CONCAT(page ORDER BY created_at DESC), ',', 1) AS last_page "
            "FROM event_log "
            "WHERE created_at >= NOW() - INTERVAL %s HOUR "
            "GROUP BY session_hash "
            "ORDER BY last_seen DESC LIMIT 200",
            (hours,),
        )
        sessions = []
        total_hits = 0
        countries = set()
        page_counts: dict = {}
        all_hashes = []
        for r in rows:
            h = r["session_hash"][:8] if r.get("session_hash") else "—"
            hits = _dec(r["hits"])
            total_hits += hits
            c = r.get("country", "")
            if c:
                countries.add(c)
            lp = r.get("last_page", "")
            if lp:
                page_counts[lp] = page_counts.get(lp, 0) + hits
            evt = r.get("event_types", "") or ""
            sessions.append({
                "session_hash": h,
                "country": c,
                "device": r.get("device", ""),
                "lang": r.get("lang", ""),
                "hits": hits,
                "last_page": lp,
                "event_types": [e.strip() for e in evt.split(",") if e.strip()],
                "last_seen": r["last_seen"].strftime("%Y-%m-%d %H:%M:%S") if r.get("last_seen") else "",
                "first_seen": r["first_seen"].strftime("%Y-%m-%d %H:%M:%S") if r.get("first_seen") else "",
            })
            if r.get("session_hash"):
                all_hashes.append(r["session_hash"])

        # Pages detail (top 30 sessions)
        top_hashes = all_hashes[:30]
        pages_map: dict = {}
        if top_hashes:
            ph = ",".join(["%s"] * len(top_hashes))
            page_rows = await db_cloudsql.async_fetchall(
                f"SELECT session_hash, page, created_at FROM event_log "
                f"WHERE created_at >= NOW() - INTERVAL %s HOUR "
                f"AND session_hash IN ({ph}) "
                f"ORDER BY created_at ASC",
                (hours, *top_hashes),
            )
            for pr in page_rows:
                h8 = pr["session_hash"][:8] if pr.get("session_hash") else ""
                pages_map.setdefault(h8, [])
                p = pr.get("page", "")
                ts_str = pr["created_at"].strftime("%Y-%m-%d %H:%M:%S") if pr.get("created_at") else ""
                if p:
                    pages_map[h8].append({"page": p, "ts": ts_str})

        for s in sessions:
            s["pages"] = pages_map.get(s["session_hash"], [])

        top_page = max(page_counts, key=page_counts.get) if page_counts else "—"

        return JSONResponse({
            "total_sessions": len(sessions),
            "total_hits": total_hits,
            "unique_countries": len(countries),
            "top_page": top_page,
            "hours": hours,
            "sessions": sessions,
        })
    except Exception as e:
        logger.error("[ADMIN] activity/history: %s", e)
        return JSONResponse({
            "total_sessions": 0, "total_hits": 0,
            "unique_countries": 0, "top_page": "—",
            "hours": hours, "sessions": [],
        })


# ── IP ban management ────────────────────────────────────────────────────────

@router.post("/admin/api/ban", include_in_schema=False)
async def admin_api_ban(request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        body = await request.json()
        ip = (body.get("ip") or "").strip()
        if not ip:
            return JSONResponse({"error": "ip required"}, status_code=400)
        reason = (body.get("reason") or "manual ban").strip()[:255]
        duration = body.get("duration_hours")  # None = permanent
        if duration is not None:
            await db_cloudsql.async_query(
                "INSERT INTO banned_ips (ip, reason, source, banned_by, expires_at) "
                "VALUES (%s, %s, 'manual', 'admin', NOW() + INTERVAL %s HOUR) "
                "ON DUPLICATE KEY UPDATE is_active=1, reason=%s, "
                "expires_at=NOW() + INTERVAL %s HOUR, banned_at=NOW()",
                (ip, reason, int(duration), reason, int(duration)),
            )
        else:
            await db_cloudsql.async_query(
                "INSERT INTO banned_ips (ip, reason, source, banned_by, expires_at) "
                "VALUES (%s, %s, 'manual', 'admin', NULL) "
                "ON DUPLICATE KEY UPDATE is_active=1, reason=%s, "
                "expires_at=NULL, banned_at=NOW()",
                (ip, reason, reason),
            )
        from middleware.ip_ban import invalidate_cache
        invalidate_cache()
        logger.info("[ADMIN_AUDIT] action=ban_ip target=%s reason=%s duration_hours=%s", ip, reason, duration)
        return JSONResponse({"ok": True, "ip": ip})
    except Exception as e:
        logger.error("[ADMIN] ban error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/admin/api/unban", include_in_schema=False)
async def admin_api_unban(request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        body = await request.json()
        ip = (body.get("ip") or "").strip()
        if not ip:
            return JSONResponse({"error": "ip required"}, status_code=400)
        await db_cloudsql.async_query(
            "UPDATE banned_ips SET is_active=0 WHERE ip=%s", (ip,)
        )
        from middleware.ip_ban import invalidate_cache
        invalidate_cache()
        logger.info("[ADMIN_AUDIT] action=unban_ip target=%s", ip)
        return JSONResponse({"ok": True, "ip": ip})
    except Exception as e:
        logger.error("[ADMIN] unban error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/admin/api/banned", include_in_schema=False)
async def admin_api_banned(request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        rows = await db_cloudsql.async_fetchall(
            "SELECT ip, reason, source, banned_at, expires_at, banned_by "
            "FROM banned_ips "
            "WHERE is_active=1 AND (expires_at IS NULL OR expires_at > NOW()) "
            "ORDER BY banned_at DESC"
        )
        banned = []
        for r in rows:
            banned.append({
                "ip": r["ip"],
                "reason": r.get("reason", ""),
                "source": r.get("source", "manual"),
                "banned_at": r["banned_at"].strftime("%Y-%m-%d %H:%M") if r.get("banned_at") else "",
                "expires_at": r["expires_at"].strftime("%Y-%m-%d %H:%M") if r.get("expires_at") else "permanent",
                "banned_by": r.get("banned_by", ""),
            })
        return JSONResponse({"total": len(banned), "banned": banned})
    except Exception as e:
        logger.error("[ADMIN] banned list: %s", e)
        return JSONResponse({"total": 0, "banned": []})


@router.post("/admin/api/refresh-bot-ips", include_in_schema=False)
async def admin_api_refresh_bot_ips(request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        from config.bot_ips import refresh_from_remote
        stats = await refresh_from_remote(request.app.state.httpx_client)
        logger.info("[ADMIN_AUDIT] action=refresh_bot_ips stats=%s", stats)
        return JSONResponse(stats)
    except Exception as e:
        logger.error("[ADMIN] refresh-bot-ips error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── V122 Phase 2/4 — Bot feeds health + AI bots access (BONUS Q8) ───────────

@router.get("/admin/api/bot-feeds-status", include_in_schema=False)
async def admin_api_bot_feeds_status(request: Request):
    """Return latest refresh per bot IP feed source + health flags.

    Identifies silent failures (feed not refreshed > 24h → red flag) to prevent
    production running on stale fallback CIDRs (scenario identified Phase ÉTAPE 1).
    """
    err = _require_auth_json(request)
    if err:
        return err
    try:
        from services.bot_feeds_monitor import get_feeds_status
        data = await get_feeds_status()
        return JSONResponse(data)
    except Exception as e:
        logger.error("[ADMIN] bot-feeds-status: %s", e)
        return JSONResponse({"feeds": [], "summary": {"total": 0, "green": 0, "orange": 0, "red": 0}},
                            status_code=500)


@router.get("/admin/api/ai-bots/stats", include_in_schema=False)
async def admin_api_ai_bots_stats(request: Request, hours: int = Query(24, ge=1, le=720)):
    """Aggregate AI bots access counters (Catégorie A) over last N hours.

    Query param `hours`: 1-720 (30 days max). Default 24h.
    """
    err = _require_auth_json(request)
    if err:
        return err
    try:
        from services.bot_feeds_monitor import get_ai_bots_stats
        data = await get_ai_bots_stats(hours=hours)
        return JSONResponse(data)
    except Exception as e:
        logger.error("[ADMIN] ai-bots/stats: %s", e)
        return JSONResponse({"period_hours": hours, "bots": [], "total_hits": 0},
                            status_code=500)


# ── V123 Phase 2.5 — Blocked bots + Timeline (widgets 2, 4) ─────────────────

@router.get("/admin/api/ai-bots/blocked", include_in_schema=False)
async def admin_api_ai_bots_blocked(request: Request, hours: int = Query(24, ge=1, le=720)):
    """V123 Phase 2.5 — Aggregated Cat C blocked UAs over last N hours."""
    err = _require_auth_json(request)
    if err:
        return err
    try:
        from services.bot_feeds_monitor import get_blocked_bots_stats
        data = await get_blocked_bots_stats(hours=hours)
        return JSONResponse(data)
    except Exception as e:
        logger.error("[ADMIN] ai-bots/blocked: %s", e)
        return JSONResponse({"period_hours": hours, "blocked_bots": [], "total_blocked": 0},
                            status_code=500)


@router.get("/admin/api/ai-bots/timeline", include_in_schema=False)
async def admin_api_ai_bots_timeline(request: Request, hours: int = Query(24, ge=1, le=720)):
    """V123 Phase 2.5 — Bucketized timeline (1h/6h/1d) for Chart.js line chart."""
    err = _require_auth_json(request)
    if err:
        return err
    try:
        from services.bot_feeds_monitor import get_ai_bots_timeline
        data = await get_ai_bots_timeline(hours=hours)
        return JSONResponse(data)
    except Exception as e:
        logger.error("[ADMIN] ai-bots/timeline: %s", e)
        return JSONResponse({"period_hours": hours, "buckets": [], "series": []},
                            status_code=500)


# ══════════════════════════════════════════════════════════════════════════════
# CONTACT MESSAGES (V41)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/messages", response_class=HTMLResponse, include_in_schema=False)
async def admin_messages_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/messages.html")
    return HTMLResponse(tpl.render(active="messages"))


@router.get("/admin/api/messages", include_in_schema=False)
async def admin_api_messages(
    request: Request,
    period: str = Query("all"),
    sujet: str = Query(""),
    lu: str = Query(""),
):
    err = _require_auth_json(request)
    if err:
        return err

    where = ["1=1"]
    params: list = []

    # Period filter
    ds, de = None, None
    if period != "all":
        ds, de = _period_to_dates(period)
    if ds and de:
        where.append("created_at BETWEEN %s AND %s")
        params.extend([ds, de])

    # Sujet filter
    if sujet and sujet != "all":
        where.append("sujet = %s")
        params.append(sujet)

    # Lu filter
    if lu == "1":
        where.append("lu = 1")
    elif lu == "0":
        where.append("lu = 0")

    where.append("deleted = 0")
    w = " AND ".join(where)

    # KPI summary
    summary = {"total": 0, "unread": 0, "today": 0}
    try:
        row = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(*) AS total, SUM(CASE WHEN lu = 0 THEN 1 ELSE 0 END) AS unread, "
            f"SUM(CASE WHEN created_at >= NOW() - INTERVAL 24 HOUR THEN 1 ELSE 0 END) AS today "
            f"FROM contact_messages WHERE {w}",
            tuple(params),
        )
        if row:
            summary["total"] = _dec(row["total"]) or 0
            summary["unread"] = _dec(row["unread"]) or 0
            summary["today"] = _dec(row["today"]) or 0
    except Exception as e:
        logger.error("[ADMIN API] messages summary failed: %s", e)

    # Table data
    table_data = []
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT id, created_at, nom, email, sujet, message, page_source, lang, lu "
            f"FROM contact_messages WHERE {w} ORDER BY created_at DESC LIMIT 500",
            tuple(params),
        )
        table_data = [
            {
                "id": r["id"],
                "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r.get("created_at") else "",
                "nom": r["nom"] or "",
                "email": r["email"] or "",
                "sujet": r["sujet"],
                "message": r["message"],
                "page_source": r["page_source"] or "",
                "lang": r["lang"] or "fr",
                "lu": r["lu"],
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("[ADMIN API] messages table failed: %s", e)

    return JSONResponse({"summary": summary, "table": table_data})


@router.post("/admin/api/messages/{msg_id}/read", include_in_schema=False)
async def admin_api_message_mark_read(msg_id: int, request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        await db_cloudsql.async_query("UPDATE contact_messages SET lu = 1 WHERE id = %s", (msg_id,))
        logger.info("[ADMIN_AUDIT] action=mark_message_read id=%s", msg_id)
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error("[ADMIN] mark read error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/admin/api/messages/{msg_id}/unread", include_in_schema=False)
async def admin_api_message_mark_unread(msg_id: int, request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        await db_cloudsql.async_query("UPDATE contact_messages SET lu = 0 WHERE id = %s", (msg_id,))
        logger.info("[ADMIN_AUDIT] action=mark_message_unread id=%s", msg_id)
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error("[ADMIN] mark unread error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/admin/api/messages/{msg_id}", include_in_schema=False)
async def admin_api_message_delete(msg_id: int, request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        row = await db_cloudsql.async_fetchone(
            "SELECT id FROM contact_messages WHERE id = %s AND deleted = 0", (msg_id,)
        )
        if not row:
            return JSONResponse({"error": "not found"}, status_code=404)
        await db_cloudsql.async_query("UPDATE contact_messages SET deleted = 1 WHERE id = %s", (msg_id,))
        logger.info("[ADMIN_AUDIT] action=delete_message id=%s", msg_id)
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error("[ADMIN] delete message error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/admin/api/messages/count-unread", include_in_schema=False)
async def admin_api_messages_count_unread(request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS cnt FROM contact_messages WHERE lu = 0 AND deleted = 0"
        )
        return JSONResponse({"unread": _dec(row["cnt"]) if row else 0})
    except Exception as e:
        logger.error("[ADMIN] count unread error: %s", e)
        return JSONResponse({"unread": 0})


# ── Chatbot Monitor (V44) ────────────────────────────────────────────────────

@router.get("/admin/chatbot-monitor", response_class=HTMLResponse, include_in_schema=False)
async def admin_chatbot_monitor_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/chatbot-monitor.html")
    return HTMLResponse(tpl.render(active="chatbot"))


@router.get("/admin/api/chatbot-log", include_in_schema=False)
async def admin_api_chatbot_log(
    request: Request,
    period: str = Query("24h"),
    module: str = Query("all"),
    phase: str = Query("all"),
    status: str = Query("all"),
    lang: str = Query("all"),
    errors_only: bool = Query(False),
    limit: int = Query(200),
):
    err = _require_auth_json(request)
    if err:
        return err

    where = []
    params: list = []

    # Period
    period_clause = _CM_PERIOD_SQL.get(period, _CM_PERIOD_SQL["24h"])
    where.append(period_clause)

    # Module filter
    if module in ("loto", "em"):
        where.append("module = %s")
        params.append(module)

    # Phase filter
    if phase != "all":
        where.append("phase_detected = %s")
        params.append(phase)

    # SQL status filter
    if status != "all":
        where.append("sql_status = %s")
        params.append(status)

    # Lang filter
    if lang != "all" and lang in _VALID_LANGS:
        where.append("lang = %s")
        params.append(lang)

    # Errors only
    if errors_only:
        where.append("(is_error = 1 OR sql_status IN ('REJECTED', 'ERROR'))")

    w = " AND ".join(where) if where else "1=1"

    # KPI
    kpi = {"total": 0, "rejected_pct": 0, "error_pct": 0, "avg_duration": 0, "unique_sessions": 0, "sql_count": 0}
    try:
        row = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(*) AS total, "
            f"SUM(CASE WHEN sql_status = 'REJECTED' THEN 1 ELSE 0 END) AS rejected, "
            f"SUM(CASE WHEN sql_status NOT IN ('N/A') THEN 1 ELSE 0 END) AS sql_total, "
            f"SUM(CASE WHEN is_error = 1 THEN 1 ELSE 0 END) AS errors, "
            f"AVG(duration_ms) AS avg_dur, "
            f"COUNT(DISTINCT session_hash) AS sessions, "
            f"SUM(CASE WHEN phase_detected = 'SQL' THEN 1 ELSE 0 END) AS sql_count "
            f"FROM chat_log WHERE {w}",
            tuple(params),
        )
        if row:
            total = _dec(row["total"]) or 0
            sql_total = _dec(row["sql_total"]) or 0
            kpi["total"] = total
            kpi["rejected_pct"] = round((_dec(row["rejected"]) or 0) / sql_total * 100, 1) if sql_total > 0 else 0
            kpi["error_pct"] = round((_dec(row["errors"]) or 0) / total * 100, 1) if total > 0 else 0
            kpi["avg_duration"] = int(_dec(row["avg_dur"]) or 0)
            kpi["unique_sessions"] = _dec(row["sessions"]) or 0
            kpi["sql_count"] = _dec(row["sql_count"]) or 0
    except Exception as e:
        logger.error("[ADMIN API] chatbot-log KPI failed: %s", e)

    # Table data
    exchanges = []
    limit = min(limit, 500)
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT id, created_at, module, lang, question, response_preview, "
            f"phase_detected, sql_generated, sql_status, duration_ms, "
            f"grid_count, has_exclusions, is_error, error_detail, "
            f"gemini_tokens_in, gemini_tokens_out, session_hash "
            f"FROM chat_log WHERE {w} ORDER BY created_at DESC LIMIT %s",
            tuple(params) + (limit,),
        )
        for r in rows:
            exchanges.append({
                "id": r["id"],
                "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r.get("created_at") else "",
                "module": r["module"],
                "lang": r["lang"],
                "question": r["question"] or "",
                "response_preview": r["response_preview"] or "",
                "phase": r["phase_detected"] or "unknown",
                "sql_generated": r["sql_generated"] or "",
                "sql_status": r["sql_status"] or "N/A",
                "duration_ms": _dec(r["duration_ms"]) or 0,
                "grid_count": _dec(r["grid_count"]) or 0,
                "has_exclusions": bool(r["has_exclusions"]),
                "is_error": bool(r["is_error"]),
                "error_detail": r["error_detail"] or "",
                "tokens_in": _dec(r["gemini_tokens_in"]) or 0,
                "tokens_out": _dec(r["gemini_tokens_out"]) or 0,
                "session_hash": (r["session_hash"] or "")[:12],
            })
    except Exception as e:
        logger.error("[ADMIN API] chatbot-log table failed: %s", e)

    return JSONResponse({"kpi": kpi, "exchanges": exchanges})


@router.get("/admin/export/chatbot-log/csv", include_in_schema=False)
@limiter.limit("30/minute")  # S15 V94
async def admin_export_chatbot_log_csv(
    request: Request,
    period: str = Query("24h"),
    module: str = Query("all"),
    phase: str = Query("all"),
    status: str = Query("all"),
    lang: str = Query("all"),
    errors_only: bool = Query(False),
):
    redir = _require_auth(request)
    if redir:
        return redir

    where = []
    params: list = []
    period_clause = _CM_PERIOD_SQL.get(period, _CM_PERIOD_SQL["24h"])
    where.append(period_clause)
    if module in ("loto", "em"):
        where.append("module = %s")
        params.append(module)
    if phase != "all":
        where.append("phase_detected = %s")
        params.append(phase)
    if status != "all":
        where.append("sql_status = %s")
        params.append(status)
    if lang != "all" and lang in _VALID_LANGS:
        where.append("lang = %s")
        params.append(lang)
    if errors_only:
        where.append("(is_error = 1 OR sql_status IN ('REJECTED', 'ERROR'))")
    w = " AND ".join(where) if where else "1=1"

    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT id, created_at, module, lang, question, response_preview, "
            f"phase_detected, sql_generated, sql_status, duration_ms, "
            f"grid_count, has_exclusions, is_error, error_detail, "
            f"gemini_tokens_in, gemini_tokens_out, ip_hash, session_hash "
            f"FROM chat_log WHERE {w} ORDER BY created_at DESC LIMIT 5000",
            tuple(params),
        )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "id", "created_at", "module", "lang", "question", "response_preview",
            "phase", "sql", "sql_status", "duration_ms",
            "grid_count", "has_exclusions", "is_error", "error_detail",
            "tokens_in", "tokens_out", "ip_hash", "session_hash",
        ])
        for r in rows:
            writer.writerow([
                r["id"],
                r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r.get("created_at") else "",
                r["module"], r["lang"], r["question"] or "",
                r["response_preview"] or "",
                r["phase_detected"], (r["sql_generated"] or "")[:500],
                r["sql_status"], _dec(r["duration_ms"]) or 0,
                _dec(r["grid_count"]) or 0, int(r["has_exclusions"]),
                int(r["is_error"]), r["error_detail"] or "",
                _dec(r["gemini_tokens_in"]) or 0, _dec(r["gemini_tokens_out"]) or 0,
                (r["ip_hash"] or "")[:12], (r["session_hash"] or "")[:12],
            ])
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=chatbot_log_{period}.csv"},
        )
    except Exception as e:
        logger.error("[ADMIN] chatbot-log CSV: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── IndexNow submit (V97) ───────────────────────────────────────────────────

@router.post("/admin/api/indexnow/submit", include_in_schema=False)
@limiter.limit("10/hour")
async def admin_indexnow_submit(request: Request):
    """Submit URLs to IndexNow (Bing/Yandex/Naver/Seznam).

    Body JSON optional: {"urls": ["https://..."]}
    If urls absent or empty → submits all sitemap URLs.
    Rate limit: 5/hour to avoid spamming IndexNow.
    """
    err = _require_auth_json(request)
    if err:
        return err

    from services.indexnow import submit_indexnow, submit_all_sitemap_urls, INDEXNOW_KEY

    if not INDEXNOW_KEY:
        return JSONResponse({"error": "IndexNow key not configured"}, status_code=503)

    try:
        body = await request.json()
    except Exception:
        body = {}

    custom_urls = body.get("urls") if isinstance(body, dict) else None

    if custom_urls and isinstance(custom_urls, list):
        # Validate: only accept strings starting with https://
        valid_urls = [u for u in custom_urls if isinstance(u, str) and u.startswith("https://")]
        if not valid_urls:
            return JSONResponse({"error": "No valid URLs provided"}, status_code=400)
        result = await submit_indexnow(valid_urls)
    else:
        result = await submit_all_sitemap_urls()

    return JSONResponse({
        "status": "ok",
        "submitted": result.get("submitted", 0),
        "indexnow_response": result.get("status"),
    })
