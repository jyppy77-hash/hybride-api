"""
Admin back-office — /admin/
============================
Auth via cookie (timing-safe) + password login.
Dashboard, impressions detail, votes detail, JSON API endpoints.
"""

import logging
import os
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import db_cloudsql
from config.templates import env

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])

_ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
_COOKIE_NAME = "lotoia_admin_token"

_VALID_EVENTS = {"sponsor-popup-shown", "sponsor-click", "sponsor-video-played"}
_VALID_LANGS = {"fr", "en", "es", "pt", "de", "nl"}
_VALID_DEVICES = {"mobile", "desktop", "tablet"}
_VALID_SOURCES = {"chatbot_loto", "chatbot_em", "popup_accueil"}


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _is_authenticated(request: Request) -> bool:
    """Check admin cookie with timing-safe comparison."""
    if not _ADMIN_TOKEN:
        return False
    token = request.cookies.get(_COOKIE_NAME, "")
    if not token:
        return False
    return secrets.compare_digest(token, _ADMIN_TOKEN)


def _require_auth(request: Request):
    """Return RedirectResponse if not authenticated, else None."""
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)
    return None


def _require_auth_json(request: Request):
    """Return 401 JSON if not authenticated, else None."""
    if not _is_authenticated(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


# ── Period helpers ────────────────────────────────────────────────────────────

def _period_to_dates(period: str, date_start: str = "", date_end: str = ""):
    """Convert period string to (start_date, end_date) as date objects."""
    today = date.today()
    if period == "today":
        return today, today + timedelta(days=1)
    if period == "7d":
        return today - timedelta(days=6), today + timedelta(days=1)
    if period == "30d":
        return today - timedelta(days=29), today + timedelta(days=1)
    if period == "month":
        return today.replace(day=1), today + timedelta(days=1)
    if period == "last_month":
        first_this = today.replace(day=1)
        last_month_end = first_this - timedelta(days=1)
        return last_month_end.replace(day=1), first_this
    if period == "custom" and date_start and date_end:
        try:
            ds = date.fromisoformat(date_start)
            de = date.fromisoformat(date_end) + timedelta(days=1)
            return ds, de
        except ValueError:
            pass
    if period == "all":
        return date(2020, 1, 1), today + timedelta(days=1)
    return today, today + timedelta(days=1)


# ── Auth routes ───────────────────────────────────────────────────────────────

@router.get("/admin/login", response_class=HTMLResponse, include_in_schema=False)
async def admin_login_page(request: Request):
    if _is_authenticated(request):
        return RedirectResponse(url="/admin", status_code=302)
    tpl = env.get_template("admin/login.html")
    return HTMLResponse(tpl.render(error=None))


@router.post("/admin/login", response_class=HTMLResponse, include_in_schema=False)
async def admin_login(request: Request, password: str = Form(...)):
    if not _ADMIN_PASSWORD or not secrets.compare_digest(password, _ADMIN_PASSWORD):
        tpl = env.get_template("admin/login.html")
        return HTMLResponse(tpl.render(error="Mot de passe incorrect."), status_code=401)

    response = RedirectResponse(url="/admin", status_code=302)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=_ADMIN_TOKEN,
        max_age=86400 * 7,
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
async def admin_dashboard(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    impressions = clicks = videos = 0
    try:
        for event_type, label in [
            ("sponsor-popup-shown", "impressions"),
            ("sponsor-click", "clicks"),
            ("sponsor-video-played", "videos"),
        ]:
            row = await db_cloudsql.async_fetchone(
                "SELECT COUNT(*) AS cnt FROM sponsor_impressions "
                "WHERE event_type = %s AND DATE(created_at) = CURDATE()",
                (event_type,),
            )
            val = row["cnt"] if row else 0
            if label == "impressions":
                impressions = val
            elif label == "clicks":
                clicks = val
            else:
                videos = val
    except Exception as e:
        logger.error("[ADMIN] sponsor query failed: %s", e)

    avg_rating = 0.0
    review_count = 0
    try:
        row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS review_count, COALESCE(ROUND(AVG(rating), 1), 0) AS avg_rating FROM ratings"
        )
        if row:
            review_count = row["review_count"] or 0
            avg_rating = float(row["avg_rating"] or 0)
    except Exception as e:
        logger.error("[ADMIN] ratings query failed: %s", e)

    tpl = env.get_template("admin/dashboard.html")
    return HTMLResponse(tpl.render(
        active="dashboard",
        impressions=impressions,
        clicks=clicks,
        videos=videos,
        avg_rating=avg_rating,
        review_count=review_count,
    ))


# ── Impressions page ──────────────────────────────────────────────────────────

@router.get("/admin/impressions", response_class=HTMLResponse, include_in_schema=False)
async def admin_impressions_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/impressions.html")
    return HTMLResponse(tpl.render(active="impressions"))


# ── Votes page ────────────────────────────────────────────────────────────────

@router.get("/admin/votes", response_class=HTMLResponse, include_in_schema=False)
async def admin_votes_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/votes.html")
    return HTMLResponse(tpl.render(active="votes"))


# ── API: Impressions data ─────────────────────────────────────────────────────

@router.get("/admin/api/impressions", include_in_schema=False)
async def admin_api_impressions(
    request: Request,
    period: str = Query("7d"),
    date_start: str = Query(""),
    date_end: str = Query(""),
    event_type: str = Query(""),
    lang: str = Query(""),
    device: str = Query(""),
):
    err = _require_auth_json(request)
    if err:
        return err

    ds, de = _period_to_dates(period, date_start, date_end)

    # Build WHERE clause
    where = ["created_at >= %s", "created_at < %s"]
    params = [ds.isoformat(), de.isoformat()]

    if event_type and event_type in _VALID_EVENTS:
        where.append("event_type = %s")
        params.append(event_type)
    if lang and lang in _VALID_LANGS:
        where.append("lang = %s")
        params.append(lang)
    if device and device in _VALID_DEVICES:
        where.append("device = %s")
        params.append(device)

    w = " AND ".join(where)

    # KPI
    kpi = {"impressions": 0, "clicks": 0, "videos": 0, "ctr": "0.00%", "sessions": 0}
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT event_type, COUNT(*) AS cnt, COUNT(DISTINCT session_hash) AS sessions "
            f"FROM sponsor_impressions WHERE {w} GROUP BY event_type",
            tuple(params),
        )
        total_imp = 0
        total_clicks = 0
        total_sessions = set()
        for r in rows:
            et = r["event_type"]
            if et == "sponsor-popup-shown":
                kpi["impressions"] = r["cnt"]
                total_imp = r["cnt"]
            elif et == "sponsor-click":
                kpi["clicks"] = r["cnt"]
                total_clicks = r["cnt"]
            elif et == "sponsor-video-played":
                kpi["videos"] = r["cnt"]

        sess_row = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(DISTINCT session_hash) AS s FROM sponsor_impressions WHERE {w}",
            tuple(params),
        )
        kpi["sessions"] = sess_row["s"] if sess_row else 0
        if total_imp > 0:
            kpi["ctr"] = f"{(total_clicks / total_imp * 100):.2f}%"
    except Exception as e:
        logger.error("[ADMIN API] impressions KPI failed: %s", e)

    # Chart data
    chart_data = []
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT DATE(created_at) AS day, event_type, COUNT(*) AS cnt "
            f"FROM sponsor_impressions WHERE {w} "
            f"GROUP BY day, event_type ORDER BY day",
            tuple(params),
        )
        chart_data = [{"day": str(r["day"]), "event_type": r["event_type"], "cnt": r["cnt"]} for r in rows]
    except Exception as e:
        logger.error("[ADMIN API] impressions chart failed: %s", e)

    # Table data
    table_data = []
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT DATE(created_at) AS day, event_type, page, lang, device, country, COUNT(*) AS cnt "
            f"FROM sponsor_impressions WHERE {w} "
            f"GROUP BY day, event_type, page, lang, device, country "
            f"ORDER BY day DESC, cnt DESC LIMIT 500",
            tuple(params),
        )
        table_data = [
            {"day": str(r["day"]), "event_type": r["event_type"], "page": r["page"],
             "lang": r["lang"], "device": r["device"], "country": r["country"] or "", "cnt": r["cnt"]}
            for r in rows
        ]
    except Exception as e:
        logger.error("[ADMIN API] impressions table failed: %s", e)

    return JSONResponse({"kpi": kpi, "chart": chart_data, "table": table_data})


# ── API: Votes data ───────────────────────────────────────────────────────────

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

    ds, de = _period_to_dates(period)

    where = ["created_at >= %s", "created_at < %s"]
    params = [ds.isoformat(), de.isoformat()]

    if source and source in _VALID_SOURCES:
        where.append("source = %s")
        params.append(source)
    if rating and rating.isdigit() and 1 <= int(rating) <= 5:
        where.append("rating = %s")
        params.append(int(rating))

    w = " AND ".join(where)

    # Summary
    summary = {"avg_rating": "0.0", "total": 0, "chatbot_loto": 0, "chatbot_em": 0, "popup_accueil": 0}
    try:
        row = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(*) AS total, COALESCE(ROUND(AVG(rating), 1), 0) AS avg_rating FROM ratings WHERE {w}",
            tuple(params),
        )
        if row:
            summary["total"] = row["total"] or 0
            summary["avg_rating"] = str(row["avg_rating"] or "0.0")

        src_rows = await db_cloudsql.async_fetchall(
            f"SELECT source, COUNT(*) AS cnt FROM ratings WHERE {w} GROUP BY source",
            tuple(params),
        )
        for r in src_rows:
            if r["source"] in summary:
                summary[r["source"]] = r["cnt"]
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
        dist_map = {r["rating"]: r["cnt"] for r in dist_rows}
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
