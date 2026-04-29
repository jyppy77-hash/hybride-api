"""
Admin back-office — /admin/
============================
Main router that includes sub-routers by domain.
Retains votes, engagement, and get_admin_config() locally.
Phase 2 refacto V88: split into admin_dashboard, admin_impressions,
admin_sponsors, admin_monitoring.
"""

import csv
import io
import logging

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

import db_cloudsql
from config.templates import env
from rate_limit import limiter
from routes.admin_helpers import (
    require_auth as _require_auth,
    require_auth_json as _require_auth_json,
    dec as _dec,
    EVENT_CATEGORIES as _EVENT_CATEGORIES,
    load_sponsor_names as _load_sponsor_names,
    build_votes_where as _build_votes_where,
    build_engagement_where as _build_engagement_where,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

# ── Include sub-routers ──────────────────────────────────────────────────────
from routes.admin_dashboard import router as _dashboard_router
from routes.admin_impressions import router as _impressions_router
from routes.admin_sponsors import router as _sponsors_router
from routes.admin_monitoring import router as _monitoring_router
from routes.admin_calendar import router as _calendar_router
from routes.admin_perf_calendar import router as _perf_calendar_router

router.include_router(_dashboard_router)
router.include_router(_impressions_router)
router.include_router(_sponsors_router)
router.include_router(_monitoring_router)
router.include_router(_calendar_router)
router.include_router(_perf_calendar_router)


# ══════════════════════════════════════════════════════════════════════════════
# VOTES
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/votes", response_class=HTMLResponse, include_in_schema=False)
async def admin_votes_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    # Update last_seen for votes badge
    try:
        await db_cloudsql.async_query(
            "INSERT INTO admin_last_seen (section, last_seen) VALUES ('votes', NOW()) "
            "ON DUPLICATE KEY UPDATE last_seen = NOW()"
        )
    except Exception as e:
        logger.error("[ADMIN] votes last_seen update error: %s", e)
    tpl = env.get_template("admin/votes.html")
    return HTMLResponse(tpl.render(active="votes"))


@router.get("/admin/api/votes", include_in_schema=False)
async def admin_api_votes(
    request: Request,
    period: str = Query("all"),
    source: str = Query(""),
    rating: str = Query(""),
):
    err = _require_auth_json(request)
    if err:
        return err

    w, params, ds, de = _build_votes_where(period, source, rating)

    # Summary
    summary = {"avg_rating": "0.0", "total": 0, "chatbot_loto": 0, "chatbot_em": 0, "popup_accueil": 0}
    try:
        row = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(*) AS total, COALESCE(ROUND(AVG(rating), 1), 0) AS avg_rating FROM ratings WHERE {w}",
            tuple(params),
        )
        if row:
            summary["total"] = _dec(row["total"]) or 0
            summary["avg_rating"] = str(row["avg_rating"] or "0.0")

        src_rows = await db_cloudsql.async_fetchall(
            f"SELECT source, COUNT(*) AS cnt FROM ratings WHERE {w} GROUP BY source",
            tuple(params),
        )
        for r in src_rows:
            if r["source"] in summary:
                summary[r["source"]] = _dec(r["cnt"])
    except Exception as e:
        logger.error("[ADMIN API] votes summary failed: %s", e)

    # Distribution (5 → 1)
    distribution = []
    try:
        total = summary["total"] or 0
        dist_rows = await db_cloudsql.async_fetchall(
            f"SELECT rating, COUNT(*) AS cnt FROM ratings WHERE {w} GROUP BY rating",
            tuple(params),
        )
        dist_map = {r["rating"]: _dec(r["cnt"]) for r in dist_rows}
        for s in range(5, 0, -1):
            distribution.append({"stars": s, "count": dist_map.get(s, 0), "total": total})
    except Exception as e:
        logger.error("[ADMIN API] votes distribution failed: %s", e)
        distribution = [{"stars": s, "count": 0, "total": 0} for s in range(5, 0, -1)]

    # Table
    table_data = []
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT created_at, source, rating, comment, page FROM ratings WHERE {w} "
            f"ORDER BY created_at DESC LIMIT 500",
            tuple(params),
        )
        table_data = [
            {"created_at": str(r["created_at"]), "source": r["source"], "rating": r["rating"],
             "comment": r["comment"] or "", "page": r["page"] or "/"}
            for r in rows
        ]
    except Exception as e:
        logger.error("[ADMIN API] votes table failed: %s", e)

    return JSONResponse({"summary": summary, "distribution": distribution, "table": table_data})


@router.get("/admin/api/votes/count-new", include_in_schema=False)
async def admin_api_votes_count_new(request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS cnt FROM ratings WHERE created_at > "
            "COALESCE((SELECT last_seen FROM admin_last_seen WHERE section = 'votes'), '2099-01-01')"
        )
        return JSONResponse({"new_votes": _dec(row["cnt"]) if row else 0})
    except Exception as e:
        logger.error("[ADMIN] count new votes error: %s", e)
        return JSONResponse({"new_votes": 0})


@router.get("/admin/api/votes/csv", include_in_schema=False)
@limiter.limit("30/minute")  # F05 V117
async def admin_export_votes_csv(
    request: Request,
    period: str = Query("all"),
    source: str = Query(""),
    rating: str = Query(""),
):
    err = _require_auth_json(request)
    if err:
        return err

    w, params, ds, de = _build_votes_where(period, source, rating)

    rows = []
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT created_at, source, rating, comment, page FROM ratings WHERE {w} "
            f"ORDER BY created_at DESC LIMIT 5000",
            tuple(params),
        )
    except Exception as e:
        logger.error("[ADMIN] CSV votes export failed: %s", e)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "source", "rating", "comment", "page"])
    for r in rows:
        writer.writerow([str(r["created_at"]), r["source"], r["rating"], r["comment"] or "", r["page"] or "/"])

    output = buf.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(output),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=votes_{ds}_{de}.csv"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# ENGAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/engagement", response_class=HTMLResponse, include_in_schema=False)
async def admin_engagement_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/engagement.html")
    return HTMLResponse(tpl.render(active="engagement"))


@router.get("/admin/api/engagement", include_in_schema=False)
async def admin_api_engagement(
    request: Request,
    period: str = Query("24h"),
    date_start: str = Query(""),
    date_end: str = Query(""),
    event_type: str = Query(""),
    module: str = Query(""),
    lang: str = Query(""),
    device: str = Query(""),
    category: str = Query(""),
    product_code: str = Query(""),
):
    err = _require_auth_json(request)
    if err:
        return err

    w, params, ds, de = _build_engagement_where(period, date_start, date_end, event_type, module, lang, device, category, product_code)

    # KPI
    kpi = {"total_events": 0, "chatbot_events": 0, "rating_events": 0,
           "simulateur_events": 0, "sponsor_events": 0, "unique_sessions": 0}
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT event_type, COUNT(*) AS cnt "
            f"FROM event_log WHERE {w} GROUP BY event_type",
            tuple(params),
        )
        total = 0
        for r in rows:
            cnt = _dec(r["cnt"])
            total += cnt
            cat = _EVENT_CATEGORIES.get(r["event_type"])
            if cat == "chatbot":
                kpi["chatbot_events"] += cnt
            elif cat == "rating":
                kpi["rating_events"] += cnt
            elif cat == "simulateur":
                kpi["simulateur_events"] += cnt
            elif cat == "sponsor":
                kpi["sponsor_events"] += cnt
        kpi["total_events"] = total

        sess_row = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(DISTINCT session_hash) AS s FROM event_log WHERE {w}",
            tuple(params),
        )
        kpi["unique_sessions"] = _dec(sess_row["s"]) if sess_row else 0
    except Exception as e:
        logger.error("[ADMIN API] engagement KPI failed: %s", e)

    # By category
    by_category = []
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT event_type, COUNT(*) AS cnt, COUNT(DISTINCT session_hash) AS sessions "
            f"FROM event_log WHERE {w} GROUP BY event_type",
            tuple(params),
        )
        cat_map = {}
        for r in rows:
            cat = _EVENT_CATEGORIES.get(r["event_type"], "other")
            if cat not in cat_map:
                cat_map[cat] = {"events": 0, "sessions": set()}
            cat_map[cat]["events"] += _dec(r["cnt"])
        # Sessions per category need a separate query (DISTINCT across event types)
        for cat_name in ("chatbot", "rating", "simulateur", "sponsor"):
            cat_events = [ev for ev, c in _EVENT_CATEGORIES.items() if c == cat_name]
            if not cat_events:
                continue
            placeholders = ",".join(["%s"] * len(cat_events))
            cat_sess = await db_cloudsql.async_fetchone(
                f"SELECT COUNT(DISTINCT session_hash) AS s FROM event_log "
                f"WHERE {w} AND event_type IN ({placeholders})",
                tuple(params) + tuple(cat_events),
            )
            sessions = _dec(cat_sess["s"]) if cat_sess else 0
            events = cat_map.get(cat_name, {}).get("events", 0)
            by_category.append({"category": cat_name, "events": events, "sessions": sessions})
        by_category.sort(key=lambda x: x["events"], reverse=True)
    except Exception as e:
        logger.error("[ADMIN API] engagement by_category failed: %s", e)

    # Chart data (pivoted by category per day)
    chart_data = []
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT DATE(created_at) AS day, event_type, COUNT(*) AS cnt "
            f"FROM event_log WHERE {w} "
            f"GROUP BY day, event_type ORDER BY day",
            tuple(params),
        )
        day_map = {}
        for r in rows:
            d = str(r["day"])
            cat = _EVENT_CATEGORIES.get(r["event_type"], "other")
            if d not in day_map:
                day_map[d] = {"day": d, "chatbot": 0, "rating": 0, "simulateur": 0, "sponsor": 0}
            if cat in day_map[d]:
                day_map[d][cat] += _dec(r["cnt"])
        chart_data = list(day_map.values())
    except Exception as e:
        logger.error("[ADMIN API] engagement chart failed: %s", e)

    # Table data
    table_data = []
    sponsor_names = _load_sponsor_names()
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT DATE(created_at) AS day, event_type, page, module, lang, device, country, "
            f"COALESCE(product_code, '') AS product_code, COUNT(*) AS cnt "
            f"FROM event_log WHERE {w} "
            f"GROUP BY day, event_type, page, module, lang, device, country, product_code "
            f"ORDER BY day DESC, cnt DESC LIMIT 500",
            tuple(params),
        )
        table_data = [
            {"day": str(r["day"]), "event_type": r["event_type"], "page": r["page"] or "",
             "module": r["module"] or "", "lang": r["lang"] or "", "device": r["device"] or "",
             "country": r["country"] or "", "product_code": r["product_code"] or "",
             "sponsor_name": sponsor_names.get(r["product_code"] or "", ""),
             "cnt": _dec(r["cnt"])}
            for r in rows
        ]
    except Exception as e:
        logger.error("[ADMIN API] engagement table failed: %s", e)

    return JSONResponse({"kpi": kpi, "by_category": by_category, "chart": chart_data,
                         "table": table_data, "sponsor_map": sponsor_names})
