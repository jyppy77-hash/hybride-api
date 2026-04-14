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
    check_admin_ip as _check_admin_ip,
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
    # F01 V117: OWNER_IP restriction on login page
    ip_block = _check_admin_ip(request)
    if ip_block:
        return ip_block
    if _is_authenticated(request):
        return RedirectResponse(url="/admin", status_code=302)
    tpl = env.get_template("admin/login.html")
    return HTMLResponse(tpl.render(error=None))


@router.post("/admin/login", response_class=HTMLResponse, include_in_schema=False)
@limiter.limit("3/minute")
async def admin_login(request: Request, password: str = Form(...)):
    # F01 V117: OWNER_IP restriction on login POST
    ip_block = _check_admin_ip(request)
    if ip_block:
        return ip_block
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


# ── Dashboard KPIs shared fetcher (F02 V117: DRY refacto) ───────────────────

_KPI_EVENT_MAP = {
    "sponsor-popup-shown": "impressions",
    "sponsor-click": "clicks",
    "sponsor-video-played": "videos",
    "sponsor-inline-shown": "inline_shown",
    "sponsor-result-shown": "result_shown",
    "sponsor-pdf-downloaded": "pdf_downloaded",
    "sponsor-pdf-mention": "pdf_mention",
}


async def _fetch_dashboard_kpis(sponsor_where: str) -> dict:
    """Fetch all dashboard KPIs from DB. Single source of truth for HTML + JSON."""
    kpis = {
        "impressions": 0, "clicks": 0, "videos": 0,
        "inline_shown": 0, "result_shown": 0, "pdf_downloaded": 0,
        "pdf_mention": 0, "total_impressions": 0,
        "avg_rating": 0.0, "review_count": 0,
        "active_visitors": 0, "hits_24h": 0, "banned_count": 0,
        "factures_impayees_count": 0, "factures_impayees_total": 0.0,
        "contrats_proches_count": 0,
    }

    # Sponsor impressions
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT event_type, COUNT(*) AS cnt FROM sponsor_impressions "
            f"WHERE {sponsor_where} GROUP BY event_type",
        )
        for r in rows:
            key = _KPI_EVENT_MAP.get(r["event_type"])
            if key:
                kpis[key] = _dec(r["cnt"])
    except Exception as e:
        logger.error("[ADMIN] dashboard KPI sponsor query failed: %s", e)

    kpis["total_impressions"] = kpis["impressions"] + kpis["inline_shown"] + kpis["result_shown"]

    # Ratings
    try:
        row = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(*) AS review_count, COALESCE(ROUND(AVG(rating), 1), 0) AS avg_rating "
            f"FROM ratings WHERE {sponsor_where}"
        )
        if row:
            kpis["review_count"] = row["review_count"] or 0
            kpis["avg_rating"] = float(row["avg_rating"] or 0)
    except Exception as e:
        logger.error("[ADMIN] dashboard KPI ratings query failed: %s", e)

    # Activity
    try:
        act_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(DISTINCT session_hash) AS active "
            "FROM event_log WHERE created_at >= NOW() - INTERVAL 5 MINUTE"
        )
        if act_row:
            kpis["active_visitors"] = _dec(act_row["active"])
        h24_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS hits FROM event_log "
            "WHERE created_at >= NOW() - INTERVAL 24 HOUR"
        )
        if h24_row:
            kpis["hits_24h"] = _dec(h24_row["hits"])
        ban_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS cnt FROM banned_ips "
            "WHERE is_active=1 AND (expires_at IS NULL OR expires_at > NOW())"
        )
        if ban_row:
            kpis["banned_count"] = _dec(ban_row["cnt"])
    except Exception as e:
        logger.error("[ADMIN] dashboard KPI activity query failed: %s", e)

    # Alertes factures impayées
    try:
        f_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(montant_ttc), 0) AS total "
            "FROM fia_factures WHERE statut = 'envoyee' "
            "AND date_emission < NOW() - INTERVAL 60 DAY"
        )
        if f_row:
            kpis["factures_impayees_count"] = _dec(f_row["cnt"])
            kpis["factures_impayees_total"] = round(float(f_row["total"] or 0), 2)
    except Exception as e:
        logger.error("[ADMIN] dashboard KPI unpaid invoices query failed: %s", e)

    # Contrats proches échéance
    try:
        c_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS cnt FROM fia_contrats "
            "WHERE statut = 'actif' AND date_fin IS NOT NULL "
            "AND DATEDIFF(date_fin, NOW()) <= 30"
        )
        if c_row:
            kpis["contrats_proches_count"] = _dec(c_row["cnt"])
    except Exception as e:
        logger.error("[ADMIN] dashboard KPI contract expiry query failed: %s", e)

    return kpis


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_dashboard(request: Request, period: str = Query("today")):
    redir = _require_auth(request)
    if redir:
        return redir

    if period not in _PERIOD_SQL:
        period = "today"
    period_label = _PERIOD_LABELS.get(period, period)

    kpis = await _fetch_dashboard_kpis(_PERIOD_SQL[period])

    # HTML-specific: detailed contrats proches list (with sponsor names)
    contrats_proches = []
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
        logger.error("[ADMIN] contract expiry detail query failed: %s", e)

    tpl = env.get_template("admin/dashboard.html")
    resp = HTMLResponse(tpl.render(
        active="dashboard",
        period=period,
        period_label=period_label,
        contrats_proches=contrats_proches,
        **kpis,
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

    kpis = await _fetch_dashboard_kpis(_PERIOD_SQL[period])

    # JSON endpoint omits pdf_mention (not displayed in polling)
    kpis.pop("pdf_mention", None)

    return JSONResponse(kpis, headers={"Cache-Control": "no-store"})
