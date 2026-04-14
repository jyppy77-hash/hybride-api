"""
Admin dashboard — login/logout, main dashboard KPIs.
=====================================================
Split from routes/admin.py (Phase 2 refacto V88).
"""

import logging
import secrets

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

import db_cloudsql
from config.templates import env
from rate_limit import limiter
from routes.admin_helpers import (
    ADMIN_TOKEN as _ADMIN_TOKEN,
    ADMIN_PASSWORD as _ADMIN_PASSWORD,
    COOKIE_NAME as _COOKIE_NAME,
    is_authenticated as _is_authenticated,
    require_auth as _require_auth,
    dec as _dec,
    PERIOD_SQL as _PERIOD_SQL,
    PERIOD_LABELS as _PERIOD_LABELS,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


# ── Auth routes ───────────────────────────────────────────────────────────────

@router.get("/admin/login", response_class=HTMLResponse, include_in_schema=False)
async def admin_login_page(request: Request):
    if _is_authenticated(request):
        return RedirectResponse(url="/admin", status_code=302)
    tpl = env.get_template("admin/login.html")
    return HTMLResponse(tpl.render(error=None))


@router.post("/admin/login", response_class=HTMLResponse, include_in_schema=False)
@limiter.limit("3/minute")
async def admin_login(request: Request, password: str = Form(...)):
    if not _ADMIN_PASSWORD or not secrets.compare_digest(password, _ADMIN_PASSWORD):
        tpl = env.get_template("admin/login.html")
        return HTMLResponse(tpl.render(error="Mot de passe incorrect."), status_code=401)

    response = RedirectResponse(url="/admin", status_code=302)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=_ADMIN_TOKEN,
        max_age=86400,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )
    return response


@router.get("/admin/logout", include_in_schema=False)
async def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(key=_COOKIE_NAME, path="/")
    return response


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_dashboard(request: Request, period: str = Query("today")):
    redir = _require_auth(request)
    if redir:
        return redir

    if period not in _PERIOD_SQL:
        period = "today"
    sponsor_where = _PERIOD_SQL[period]
    period_label = _PERIOD_LABELS.get(period, period)

    impressions = clicks = videos = inline_shown = result_shown = pdf_downloaded = pdf_mention = 0
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT event_type, COUNT(*) AS cnt FROM sponsor_impressions "
            f"WHERE {sponsor_where} GROUP BY event_type",
        )
        _kpi_map = {
            "sponsor-popup-shown": "impressions",
            "sponsor-click": "clicks",
            "sponsor-video-played": "videos",
            "sponsor-inline-shown": "inline_shown",
            "sponsor-result-shown": "result_shown",
            "sponsor-pdf-downloaded": "pdf_downloaded",
            "sponsor-pdf-mention": "pdf_mention",
        }
        _kpi_vals = {"impressions": 0, "clicks": 0, "videos": 0,
                     "inline_shown": 0, "result_shown": 0, "pdf_downloaded": 0,
                     "pdf_mention": 0}
        for r in rows:
            key = _kpi_map.get(r["event_type"])
            if key:
                _kpi_vals[key] = _dec(r["cnt"])
        impressions = _kpi_vals["impressions"]
        clicks = _kpi_vals["clicks"]
        videos = _kpi_vals["videos"]
        inline_shown = _kpi_vals["inline_shown"]
        result_shown = _kpi_vals["result_shown"]
        pdf_downloaded = _kpi_vals["pdf_downloaded"]
        pdf_mention = _kpi_vals["pdf_mention"]
    except Exception as e:
        logger.error("[ADMIN] sponsor query failed: %s", e)

    total_impressions = impressions + inline_shown + result_shown

    avg_rating = 0.0
    review_count = 0
    try:
        row = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(*) AS review_count, COALESCE(ROUND(AVG(rating), 1), 0) AS avg_rating "
            f"FROM ratings WHERE {sponsor_where}"
        )
        if row:
            review_count = row["review_count"] or 0
            avg_rating = float(row["avg_rating"] or 0)
    except Exception as e:
        logger.error("[ADMIN] ratings query failed: %s", e)

    active_visitors = 0
    hits_24h = 0
    banned_count = 0
    try:
        act_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(DISTINCT session_hash) AS active "
            "FROM event_log WHERE created_at >= NOW() - INTERVAL 5 MINUTE"
        )
        if act_row:
            active_visitors = _dec(act_row["active"])
        h24_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS hits FROM event_log "
            "WHERE created_at >= NOW() - INTERVAL 24 HOUR"
        )
        if h24_row:
            hits_24h = _dec(h24_row["hits"])
        ban_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS cnt FROM banned_ips "
            "WHERE is_active=1 AND (expires_at IS NULL OR expires_at > NOW())"
        )
        if ban_row:
            banned_count = _dec(ban_row["cnt"])
    except Exception as e:
        logger.error("[ADMIN] activity KPI query failed: %s", e)

    # V92 S12: alertes factures impayées + échéances contrats
    factures_impayees_count = 0
    factures_impayees_total = 0.0
    contrats_proches = []
    try:
        f_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(montant_ttc), 0) AS total "
            "FROM fia_factures WHERE statut = 'envoyee' "
            "AND date_emission < NOW() - INTERVAL 60 DAY"
        )
        if f_row:
            factures_impayees_count = _dec(f_row["cnt"])
            factures_impayees_total = round(float(f_row["total"] or 0), 2)
    except Exception as e:
        logger.error("[ADMIN] unpaid invoices query failed: %s", e)
    try:
        c_rows = await db_cloudsql.async_fetchall(
            "SELECT s.nom AS sponsor_name, c.date_fin, "
            "DATEDIFF(c.date_fin, NOW()) AS days_left "
            "FROM fia_contrats c JOIN fia_sponsors s ON c.sponsor_id = s.id "
            "WHERE c.statut = 'actif' AND c.date_fin IS NOT NULL "
            "ORDER BY c.date_fin ASC LIMIT 3"
        )
        if c_rows:
            contrats_proches = [{"sponsor_name": r["sponsor_name"],
                                 "days_left": _dec(r["days_left"])} for r in c_rows]
    except Exception as e:
        logger.error("[ADMIN] contract expiry query failed: %s", e)

    tpl = env.get_template("admin/dashboard.html")
    resp = HTMLResponse(tpl.render(
        active="dashboard",
        period=period,
        period_label=period_label,
        total_impressions=total_impressions,
        impressions=impressions,
        clicks=clicks,
        videos=videos,
        inline_shown=inline_shown,
        result_shown=result_shown,
        pdf_downloaded=pdf_downloaded,
        pdf_mention=pdf_mention,
        avg_rating=avg_rating,
        review_count=review_count,
        active_visitors=active_visitors,
        hits_24h=hits_24h,
        banned_count=banned_count,
        factures_impayees_count=factures_impayees_count,
        factures_impayees_total=factures_impayees_total,
        contrats_proches=contrats_proches,
    ))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


# ── Dashboard KPIs JSON (V112: auto-refresh polling) ─────────────────────────

@router.get("/admin/api/dashboard-kpis", include_in_schema=False)
async def admin_dashboard_kpis(request: Request, period: str = Query("today")):
    """Return all dashboard KPIs as JSON for JS polling."""
    redir = _require_auth(request)
    if redir:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    if period not in _PERIOD_SQL:
        period = "today"
    sponsor_where = _PERIOD_SQL[period]

    impressions = clicks = videos = inline_shown = result_shown = pdf_downloaded = pdf_mention = 0
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT event_type, COUNT(*) AS cnt FROM sponsor_impressions "
            f"WHERE {sponsor_where} GROUP BY event_type",
        )
        _kpi_map = {
            "sponsor-popup-shown": "impressions",
            "sponsor-click": "clicks",
            "sponsor-video-played": "videos",
            "sponsor-inline-shown": "inline_shown",
            "sponsor-result-shown": "result_shown",
            "sponsor-pdf-downloaded": "pdf_downloaded",
            "sponsor-pdf-mention": "pdf_mention",
        }
        _kpi_vals = {"impressions": 0, "clicks": 0, "videos": 0,
                     "inline_shown": 0, "result_shown": 0, "pdf_downloaded": 0,
                     "pdf_mention": 0}
        for r in rows:
            key = _kpi_map.get(r["event_type"])
            if key:
                _kpi_vals[key] = _dec(r["cnt"])
        impressions = _kpi_vals["impressions"]
        clicks = _kpi_vals["clicks"]
        videos = _kpi_vals["videos"]
        inline_shown = _kpi_vals["inline_shown"]
        result_shown = _kpi_vals["result_shown"]
        pdf_downloaded = _kpi_vals["pdf_downloaded"]
        pdf_mention = _kpi_vals["pdf_mention"]
    except Exception as e:
        logger.error("[ADMIN] dashboard-kpis sponsor query failed: %s", e)

    total_impressions = impressions + inline_shown + result_shown

    avg_rating = 0.0
    review_count = 0
    try:
        row = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(*) AS review_count, COALESCE(ROUND(AVG(rating), 1), 0) AS avg_rating "
            f"FROM ratings WHERE {sponsor_where}"
        )
        if row:
            review_count = row["review_count"] or 0
            avg_rating = float(row["avg_rating"] or 0)
    except Exception as e:
        logger.error("[ADMIN] dashboard-kpis ratings query failed: %s", e)

    active_visitors = 0
    hits_24h = 0
    banned_count = 0
    try:
        act_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(DISTINCT session_hash) AS active "
            "FROM event_log WHERE created_at >= NOW() - INTERVAL 5 MINUTE"
        )
        if act_row:
            active_visitors = _dec(act_row["active"])
        h24_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS hits FROM event_log "
            "WHERE created_at >= NOW() - INTERVAL 24 HOUR"
        )
        if h24_row:
            hits_24h = _dec(h24_row["hits"])
        ban_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS cnt FROM banned_ips "
            "WHERE is_active=1 AND (expires_at IS NULL OR expires_at > NOW())"
        )
        if ban_row:
            banned_count = _dec(ban_row["cnt"])
    except Exception as e:
        logger.error("[ADMIN] dashboard-kpis activity query failed: %s", e)

    return JSONResponse({
        "total_impressions": total_impressions,
        "impressions": impressions,
        "clicks": clicks,
        "videos": videos,
        "inline_shown": inline_shown,
        "result_shown": result_shown,
        "pdf_downloaded": pdf_downloaded,
        "avg_rating": avg_rating,
        "review_count": review_count,
        "active_visitors": active_visitors,
        "hits_24h": hits_24h,
        "banned_count": banned_count,
    }, headers={"Cache-Control": "no-store"})
