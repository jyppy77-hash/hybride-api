"""
Admin back-office — /admin/
============================
Auth via cookie (timing-safe) + password login.
Dashboard, impressions detail, votes detail, JSON API endpoints.
Exports (CSV / PDF), FacturIA (sponsors CRUD, invoices CRUD, config).
"""

import csv
import io
import json
import logging
import os
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

import db_cloudsql
from config.templates import env
from rate_limit import limiter

logger = logging.getLogger(__name__)


def _dec(v):
    """Convert Decimal to int/float for JSON serialization."""
    if isinstance(v, Decimal):
        return int(v) if v == int(v) else float(v)
    return v
router = APIRouter(tags=["admin"])

_ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
_COOKIE_NAME = "lotoia_admin_token"

# ── Admin IP restriction (L2 fix) ────────────────────────────────────────────
# Reuses the SAME owner detection as ip_ban.py (single source of truth).

def _check_admin_ip(request: Request) -> JSONResponse | None:
    """Restrict admin access to OWNER_IP only. Returns 403 response or None."""
    from middleware.ip_ban import _is_owner_or_loopback, _extract_client_ip
    real_ip = _extract_client_ip(request)
    if not real_ip or real_ip == "testclient":
        return None  # TestClient / empty → allow (dev)
    if _is_owner_or_loopback(real_ip):
        return None
    logger.warning("[ADMIN_AUDIT] action=admin_ip_blocked ip=%s path=%s", real_ip, request.url.path)
    return JSONResponse({"error": "Forbidden"}, status_code=403)

_VALID_EVENTS = {"sponsor-popup-shown", "sponsor-click", "sponsor-video-played", "sponsor-inline-shown", "sponsor-result-shown", "sponsor-pdf-downloaded"}
_VALID_LANGS = {"fr", "en", "es", "pt", "de", "nl"}
_VALID_DEVICES = {"mobile", "desktop", "tablet"}
_VALID_SOURCES = {"chatbot_loto", "chatbot_em", "chatbot_em_en", "popup_accueil", "popup_em"}
_VALID_STATUTS = {"brouillon", "envoyee", "payee"}


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _is_authenticated(request: Request) -> bool:
    if not _ADMIN_TOKEN:
        return False
    token = request.cookies.get(_COOKIE_NAME, "")
    if not token:
        return False
    return secrets.compare_digest(token, _ADMIN_TOKEN)


def _require_auth(request: Request):
    ip_block = _check_admin_ip(request)
    if ip_block:
        return ip_block
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)
    return None


def _require_auth_json(request: Request):
    ip_block = _check_admin_ip(request)
    if ip_block:
        return ip_block
    if not _is_authenticated(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


# ── Period helpers ────────────────────────────────────────────────────────────

def _period_to_dates(period: str, date_start: str = "", date_end: str = ""):
    today = date.today()
    if period == "24h":
        now = datetime.now()
        return now - timedelta(hours=24), now + timedelta(minutes=5)
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


def _period_label(period: str, ds, de):
    labels = {"24h": "24 dernieres heures", "today": "Aujourd'hui", "7d": "7 derniers jours",
              "30d": "30 derniers jours", "month": "Ce mois", "last_month": "Mois dernier",
              "all": "Toute la periode"}
    return labels.get(period, f"{ds} — {de}")


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
async def admin_dashboard(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    impressions = clicks = videos = inline_shown = result_shown = pdf_downloaded = 0
    try:
        rows = await db_cloudsql.async_fetchall(
            "SELECT event_type, COUNT(*) AS cnt FROM sponsor_impressions "
            "WHERE DATE(created_at) = CURDATE() GROUP BY event_type",
        )
        _kpi_map = {
            "sponsor-popup-shown": "impressions",
            "sponsor-click": "clicks",
            "sponsor-video-played": "videos",
            "sponsor-inline-shown": "inline_shown",
            "sponsor-result-shown": "result_shown",
            "sponsor-pdf-downloaded": "pdf_downloaded",
        }
        _kpi_vals = {"impressions": 0, "clicks": 0, "videos": 0,
                     "inline_shown": 0, "result_shown": 0, "pdf_downloaded": 0}
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
    except Exception as e:
        logger.error("[ADMIN] sponsor query failed: %s", e)

    avg_rating = 0.0
    review_count = 0
    try:
        row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS review_count, COALESCE(ROUND(AVG(rating), 1), 0) AS avg_rating "
            "FROM ratings WHERE created_at >= NOW() - INTERVAL 90 DAY"
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

    tpl = env.get_template("admin/dashboard.html")
    return HTMLResponse(tpl.render(
        active="dashboard",
        impressions=impressions,
        clicks=clicks,
        videos=videos,
        inline_shown=inline_shown,
        result_shown=result_shown,
        pdf_downloaded=pdf_downloaded,
        avg_rating=avg_rating,
        review_count=review_count,
        active_visitors=active_visitors,
        hits_24h=hits_24h,
        banned_count=banned_count,
    ))


# ── Impressions page ──────────────────────────────────────────────────────────

@router.get("/admin/impressions", response_class=HTMLResponse, include_in_schema=False)
async def admin_impressions_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/impressions.html")
    return HTMLResponse(tpl.render(active="impressions"))


# ── Engagement page ──────────────────────────────────────────────────────────

@router.get("/admin/engagement", response_class=HTMLResponse, include_in_schema=False)
async def admin_engagement_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/engagement.html")
    return HTMLResponse(tpl.render(active="engagement"))


# ── Votes page ────────────────────────────────────────────────────────────────

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


# ── API: Impressions data ─────────────────────────────────────────────────────

_VALID_SPONSORS = frozenset([
    "LOTO_FR_A", "LOTO_FR_B", "EM_FR_A", "EM_FR_B",
    "EM_EN_A", "EM_EN_B", "EM_ES_A", "EM_ES_B",
    "EM_PT_A", "EM_PT_B", "EM_DE_A", "EM_DE_B",
    "EM_NL_A", "EM_NL_B",
])


def _build_impressions_where(period, date_start, date_end, event_type, lang, device, sponsor_id="", tarif=""):
    ds, de = _period_to_dates(period, date_start, date_end)
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
    if sponsor_id and sponsor_id in _VALID_SPONSORS:
        where.append("sponsor_id = %s")
        params.append(sponsor_id)
    if tarif and tarif in ("A", "B"):
        where.append("sponsor_id LIKE %s")
        params.append(f"%_{tarif}")
    return " AND ".join(where), params, ds, de


@router.get("/admin/api/impressions", include_in_schema=False)
async def admin_api_impressions(
    request: Request,
    period: str = Query("24h"),
    date_start: str = Query(""),
    date_end: str = Query(""),
    event_type: str = Query(""),
    lang: str = Query(""),
    device: str = Query(""),
    sponsor_id: str = Query(""),
    tarif: str = Query(""),
):
    err = _require_auth_json(request)
    if err:
        return err

    w, params, ds, de = _build_impressions_where(period, date_start, date_end, event_type, lang, device, sponsor_id, tarif)

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
        for r in rows:
            et = r["event_type"]
            if et == "sponsor-popup-shown":
                kpi["impressions"] = _dec(r["cnt"])
                total_imp = _dec(r["cnt"])
            elif et == "sponsor-click":
                kpi["clicks"] = _dec(r["cnt"])
                total_clicks = _dec(r["cnt"])
            elif et == "sponsor-video-played":
                kpi["videos"] = _dec(r["cnt"])

        sess_row = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(DISTINCT session_hash) AS s FROM sponsor_impressions WHERE {w}",
            tuple(params),
        )
        kpi["sessions"] = _dec(sess_row["s"]) if sess_row else 0
        if total_imp > 0:
            kpi["ctr"] = f"{(total_clicks / total_imp * 100):.2f}%"
    except Exception as e:
        logger.error("[ADMIN API] impressions KPI failed: %s", e)

    # By-sponsor breakdown
    by_sponsor = []
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT sponsor_id, "
            f"  COUNT(*) AS total, "
            f"  SUM(CASE WHEN event_type = 'sponsor-popup-shown' THEN 1 ELSE 0 END) AS impressions, "
            f"  SUM(CASE WHEN event_type = 'sponsor-click' THEN 1 ELSE 0 END) AS clics, "
            f"  SUM(CASE WHEN event_type = 'sponsor-video-played' THEN 1 ELSE 0 END) AS videos, "
            f"  COUNT(DISTINCT session_hash) AS sessions "
            f"FROM sponsor_impressions WHERE {w} "
            f"GROUP BY sponsor_id ORDER BY total DESC",
            tuple(params),
        )
        for r in rows:
            imp = _dec(r["impressions"])
            cli = _dec(r["clics"])
            by_sponsor.append({
                "sponsor_id": r["sponsor_id"] or "",
                "impressions": imp,
                "clics": cli,
                "videos": _dec(r["videos"]),
                "sessions": _dec(r["sessions"]),
                "ctr": f"{(cli / imp * 100):.2f}%" if imp > 0 else "0.00%",
            })
    except Exception as e:
        logger.error("[ADMIN API] impressions by_sponsor failed: %s", e)

    # Chart data
    chart_data = []
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT DATE(created_at) AS day, event_type, COUNT(*) AS cnt "
            f"FROM sponsor_impressions WHERE {w} "
            f"GROUP BY day, event_type ORDER BY day",
            tuple(params),
        )
        chart_data = [{"day": str(r["day"]), "event_type": r["event_type"], "cnt": _dec(r["cnt"])} for r in rows]
    except Exception as e:
        logger.error("[ADMIN API] impressions chart failed: %s", e)

    # Table data (now includes sponsor_id)
    table_data = []
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT DATE(created_at) AS day, sponsor_id, event_type, page, lang, device, country, COUNT(*) AS cnt "
            f"FROM sponsor_impressions WHERE {w} "
            f"GROUP BY day, sponsor_id, event_type, page, lang, device, country "
            f"ORDER BY day DESC, cnt DESC LIMIT 500",
            tuple(params),
        )
        table_data = [
            {"day": str(r["day"]), "sponsor_id": r["sponsor_id"] or "", "event_type": r["event_type"],
             "page": r["page"], "lang": r["lang"], "device": r["device"],
             "country": r["country"] or "", "cnt": _dec(r["cnt"])}
            for r in rows
        ]
    except Exception as e:
        logger.error("[ADMIN API] impressions table failed: %s", e)

    return JSONResponse({"kpi": kpi, "by_sponsor": by_sponsor, "chart": chart_data, "table": table_data})


# ── API: Votes data ───────────────────────────────────────────────────────────

def _build_votes_where(period, source, rating):
    ds, de = _period_to_dates(period)
    where = ["created_at >= %s", "created_at < %s"]
    params = [ds.isoformat(), de.isoformat()]
    if source and source in _VALID_SOURCES:
        where.append("source = %s")
        params.append(source)
    if rating and rating.isdigit() and 1 <= int(rating) <= 5:
        where.append("rating = %s")
        params.append(int(rating))
    return " AND ".join(where), params, ds, de


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


# ══════════════════════════════════════════════════════════════════════════════
# EXPORTS (CSV / PDF)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/api/impressions/csv", include_in_schema=False)
async def admin_export_impressions_csv(
    request: Request,
    period: str = Query("24h"),
    date_start: str = Query(""),
    date_end: str = Query(""),
    event_type: str = Query(""),
    lang: str = Query(""),
    device: str = Query(""),
    sponsor_id: str = Query(""),
    tarif: str = Query(""),
):
    err = _require_auth_json(request)
    if err:
        return err

    w, params, ds, de = _build_impressions_where(period, date_start, date_end, event_type, lang, device, sponsor_id, tarif)

    rows = []
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT DATE(created_at) AS day, sponsor_id, event_type, page, lang, device, country, COUNT(*) AS cnt "
            f"FROM sponsor_impressions WHERE {w} "
            f"GROUP BY day, sponsor_id, event_type, page, lang, device, country "
            f"ORDER BY day DESC, cnt DESC LIMIT 5000",
            tuple(params),
        )
    except Exception as e:
        logger.error("[ADMIN] CSV impressions export failed: %s", e)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "sponsor_id", "event_type", "page", "lang", "device", "country", "count"])
    for r in rows:
        writer.writerow([str(r["day"]), r["sponsor_id"] or "", r["event_type"], r["page"], r["lang"], r["device"], r["country"] or "", r["cnt"]])

    output = buf.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(output),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=impressions_{ds}_{de}.csv"},
    )


@router.get("/admin/api/votes/csv", include_in_schema=False)
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


@router.get("/admin/api/sponsor-report/pdf", include_in_schema=False)
async def admin_export_sponsor_report_pdf(
    request: Request,
    period: str = Query("24h"),
    date_start: str = Query(""),
    date_end: str = Query(""),
    event_type: str = Query(""),
    lang: str = Query(""),
    device: str = Query(""),
    sponsor_id: str = Query(""),
    tarif: str = Query(""),
):
    err = _require_auth_json(request)
    if err:
        return err

    w, params, ds, de = _build_impressions_where(period, date_start, date_end, event_type, lang, device, sponsor_id, tarif)

    kpi = {"impressions": 0, "clicks": 0, "videos": 0, "ctr": "0.00%", "sessions": 0}
    table_data = []
    try:
        rows = await db_cloudsql.async_fetchall(
            f"SELECT event_type, COUNT(*) AS cnt FROM sponsor_impressions WHERE {w} GROUP BY event_type",
            tuple(params),
        )
        total_imp = total_clicks = 0
        for r in rows:
            et = r["event_type"]
            if et == "sponsor-popup-shown":
                kpi["impressions"] = _dec(r["cnt"]); total_imp = _dec(r["cnt"])
            elif et == "sponsor-click":
                kpi["clicks"] = _dec(r["cnt"]); total_clicks = _dec(r["cnt"])
            elif et == "sponsor-video-played":
                kpi["videos"] = _dec(r["cnt"])
        sess = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(DISTINCT session_hash) AS s FROM sponsor_impressions WHERE {w}", tuple(params))
        kpi["sessions"] = _dec(sess["s"]) if sess else 0
        if total_imp > 0:
            kpi["ctr"] = f"{(total_clicks / total_imp * 100):.2f}%"

        table_rows = await db_cloudsql.async_fetchall(
            f"SELECT DATE(created_at) AS day, event_type, page, lang, device, country, COUNT(*) AS cnt "
            f"FROM sponsor_impressions WHERE {w} "
            f"GROUP BY day, event_type, page, lang, device, country ORDER BY day DESC LIMIT 200",
            tuple(params),
        )
        table_data = [
            {"day": str(r["day"]), "event_type": r["event_type"], "page": r["page"],
             "lang": r["lang"], "device": r["device"], "country": r["country"] or "", "cnt": _dec(r["cnt"])}
            for r in table_rows
        ]
    except Exception as e:
        logger.error("[ADMIN] PDF report failed: %s", e)

    from services.admin_pdf import generate_sponsor_report_pdf
    label = _period_label(period, ds, de)
    pdf_buf = generate_sponsor_report_pdf(kpi, table_data, label)

    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=rapport_sponsor_{ds}_{de}.pdf"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# SPONSORS CRUD
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/sponsors", response_class=HTMLResponse, include_in_schema=False)
async def admin_sponsors_list(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    sponsors = []
    try:
        sponsors = await db_cloudsql.async_fetchall(
            "SELECT id, nom, contact_nom, contact_email, contact_tel, adresse, siret, notes, actif "
            "FROM fia_sponsors ORDER BY nom"
        )
    except Exception as e:
        logger.error("[ADMIN] sponsors list: %s", e)
    tpl = env.get_template("admin/sponsors.html")
    return HTMLResponse(tpl.render(active="sponsors", sponsors=sponsors))


@router.get("/admin/sponsors/new", response_class=HTMLResponse, include_in_schema=False)
async def admin_sponsor_new_form(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/sponsor_form.html")
    return HTMLResponse(tpl.render(active="sponsors", sponsor=None, grille=None, error=None))


@router.post("/admin/sponsors/new", response_class=HTMLResponse, include_in_schema=False)
async def admin_sponsor_create(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    nom = (form.get("nom") or "").strip()
    if not nom:
        tpl = env.get_template("admin/sponsor_form.html")
        return HTMLResponse(tpl.render(active="sponsors", sponsor=None, grille=None, error="Le nom est obligatoire."), status_code=400)

    try:
        await db_cloudsql.async_query(
            "INSERT INTO fia_sponsors (nom, contact_nom, contact_email, contact_tel, adresse, siret, notes, actif) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (nom, form.get("contact_nom", ""), form.get("contact_email", ""),
             form.get("contact_tel", ""), form.get("adresse", ""),
             form.get("siret", ""), form.get("notes", ""), int(form.get("actif", 1))),
        )
        row = await db_cloudsql.async_fetchone("SELECT LAST_INSERT_ID() AS id")
        sponsor_id = row["id"]
        logger.info("[ADMIN_AUDIT] action=sponsor_create sponsor_id=%s name=%s", sponsor_id, nom)

        # Save pricing grid
        events = form.getlist("tarif_event[]")
        prices = form.getlist("tarif_prix[]")
        descs = form.getlist("tarif_desc[]")
        for ev, pr, desc in zip(events, prices, descs):
            if ev in _VALID_EVENTS and pr:
                await db_cloudsql.async_query(
                    "INSERT INTO fia_grille_tarifaire (sponsor_id, event_type, prix_unitaire, description) "
                    "VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE prix_unitaire=%s, description=%s",
                    (sponsor_id, ev, float(pr), desc, float(pr), desc),
                )
    except Exception as e:
        logger.error("[ADMIN] sponsor create: %s", e)
        tpl = env.get_template("admin/sponsor_form.html")
        return HTMLResponse(tpl.render(active="sponsors", sponsor=None, grille=None, error=str(e)), status_code=500)

    return RedirectResponse(url="/admin/sponsors", status_code=302)


@router.get("/admin/sponsors/{sponsor_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def admin_sponsor_edit_form(request: Request, sponsor_id: int):
    redir = _require_auth(request)
    if redir:
        return redir
    sponsor = await db_cloudsql.async_fetchone("SELECT * FROM fia_sponsors WHERE id = %s", (sponsor_id,))
    if not sponsor:
        return RedirectResponse(url="/admin/sponsors", status_code=302)
    grille = await db_cloudsql.async_fetchall("SELECT * FROM fia_grille_tarifaire WHERE sponsor_id = %s", (sponsor_id,))
    tpl = env.get_template("admin/sponsor_form.html")
    return HTMLResponse(tpl.render(active="sponsors", sponsor=sponsor, grille=grille, error=None))


@router.post("/admin/sponsors/{sponsor_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def admin_sponsor_update(request: Request, sponsor_id: int):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    nom = (form.get("nom") or "").strip()
    if not nom:
        sponsor = await db_cloudsql.async_fetchone("SELECT * FROM fia_sponsors WHERE id = %s", (sponsor_id,))
        grille = await db_cloudsql.async_fetchall("SELECT * FROM fia_grille_tarifaire WHERE sponsor_id = %s", (sponsor_id,))
        tpl = env.get_template("admin/sponsor_form.html")
        return HTMLResponse(tpl.render(active="sponsors", sponsor=sponsor, grille=grille, error="Le nom est obligatoire."), status_code=400)

    try:
        await db_cloudsql.async_query(
            "UPDATE fia_sponsors SET nom=%s, contact_nom=%s, contact_email=%s, contact_tel=%s, "
            "adresse=%s, siret=%s, notes=%s, actif=%s WHERE id=%s",
            (nom, form.get("contact_nom", ""), form.get("contact_email", ""),
             form.get("contact_tel", ""), form.get("adresse", ""),
             form.get("siret", ""), form.get("notes", ""), int(form.get("actif", 1)), sponsor_id),
        )
        logger.info("[ADMIN_AUDIT] action=sponsor_update sponsor_id=%s name=%s", sponsor_id, nom)

        # Replace pricing grid
        await db_cloudsql.async_query("DELETE FROM fia_grille_tarifaire WHERE sponsor_id = %s", (sponsor_id,))
        events = form.getlist("tarif_event[]")
        prices = form.getlist("tarif_prix[]")
        descs = form.getlist("tarif_desc[]")
        for ev, pr, desc in zip(events, prices, descs):
            if ev in _VALID_EVENTS and pr:
                await db_cloudsql.async_query(
                    "INSERT INTO fia_grille_tarifaire (sponsor_id, event_type, prix_unitaire, description) VALUES (%s, %s, %s, %s)",
                    (sponsor_id, ev, float(pr), desc),
                )
    except Exception as e:
        logger.error("[ADMIN] sponsor update: %s", e)

    return RedirectResponse(url="/admin/sponsors", status_code=302)


# ══════════════════════════════════════════════════════════════════════════════
# FACTURES CRUD
# ══════════════════════════════════════════════════════════════════════════════

def _next_invoice_number(existing_count: int) -> str:
    today = date.today()
    return f"FIA-{today.strftime('%Y%m')}-{existing_count + 1:04d}"


@router.get("/admin/factures", response_class=HTMLResponse, include_in_schema=False)
async def admin_factures_list(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    factures = []
    try:
        factures = await db_cloudsql.async_fetchall(
            "SELECT f.*, s.nom AS sponsor_nom FROM fia_factures f "
            "LEFT JOIN fia_sponsors s ON f.sponsor_id = s.id "
            "ORDER BY f.date_emission DESC"
        )
    except Exception as e:
        logger.error("[ADMIN] factures list: %s", e)
    tpl = env.get_template("admin/factures.html")
    return HTMLResponse(tpl.render(active="factures", factures=factures))


@router.get("/admin/factures/new", response_class=HTMLResponse, include_in_schema=False)
async def admin_facture_new_form(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    sponsors = []
    try:
        sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom")
    except Exception as e:
        logger.error("[ADMIN] facture form sponsors: %s", e)
    tpl = env.get_template("admin/facture_form.html")
    return HTMLResponse(tpl.render(active="factures", sponsors=sponsors, error=None))


@router.post("/admin/factures/new", response_class=HTMLResponse, include_in_schema=False)
async def admin_facture_create(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    sponsor_id = form.get("sponsor_id")
    periode_debut = form.get("periode_debut", "")
    periode_fin = form.get("periode_fin", "")

    sponsors = []
    try:
        sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom")
    except Exception:
        pass

    if not sponsor_id or not periode_debut or not periode_fin:
        tpl = env.get_template("admin/facture_form.html")
        return HTMLResponse(tpl.render(active="factures", sponsors=sponsors, error="Tous les champs sont obligatoires."), status_code=400)

    try:
        sponsor_id = int(sponsor_id)
        pd = date.fromisoformat(periode_debut)
        pf = date.fromisoformat(periode_fin)
    except (ValueError, TypeError):
        tpl = env.get_template("admin/facture_form.html")
        return HTMLResponse(tpl.render(active="factures", sponsors=sponsors, error="Dates invalides."), status_code=400)

    try:
        # Get sponsor pricing grid
        grille = await db_cloudsql.async_fetchall(
            "SELECT * FROM fia_grille_tarifaire WHERE sponsor_id = %s", (sponsor_id,))

        # Count events in period from sponsor_impressions (single GROUP BY — A07)
        event_types = [g["event_type"] for g in grille]
        counts_by_type = {}
        if event_types:
            placeholders = ",".join(["%s"] * len(event_types))
            count_rows = await db_cloudsql.async_fetchall(
                f"SELECT event_type, COUNT(*) AS cnt FROM sponsor_impressions "
                f"WHERE event_type IN ({placeholders}) "
                f"AND DATE(created_at) >= %s AND DATE(created_at) <= %s "
                f"GROUP BY event_type",
                (*event_types, pd.isoformat(), pf.isoformat()),
            )
            counts_by_type = {r["event_type"]: r["cnt"] for r in count_rows}

        lignes = []
        montant_ht = Decimal("0")
        for g in grille:
            qty = counts_by_type.get(g["event_type"], 0)
            prix = Decimal(str(g["prix_unitaire"]))
            total_ligne = prix * qty
            montant_ht += total_ligne
            desc = g["description"] or g["event_type"]
            lignes.append({"event_type": g["event_type"], "description": desc,
                           "quantite": qty, "prix_unitaire": float(prix), "total_ht": float(total_ligne)})

        # TVA
        config_row = await db_cloudsql.async_fetchone("SELECT taux_tva FROM fia_config_entreprise WHERE id = 1")
        taux_tva = Decimal(str(config_row["taux_tva"])) if config_row else Decimal("20")
        montant_tva = (montant_ht * taux_tva / Decimal("100")).quantize(Decimal("0.01"))
        montant_ttc = montant_ht + montant_tva

        # Invoice number — retry on duplicate (S15 unique constraint)
        date_echeance_str = form.get("date_echeance", "")
        date_ech = date.fromisoformat(date_echeance_str) if date_echeance_str else (date.today() + timedelta(days=30))

        for _attempt in range(3):
            cnt_row = await db_cloudsql.async_fetchone(
                "SELECT COUNT(*) AS cnt FROM fia_factures WHERE numero LIKE %s",
                (f"FIA-{date.today().strftime('%Y%m')}-%",))
            numero = _next_invoice_number(cnt_row["cnt"] if cnt_row else 0)
            try:
                await db_cloudsql.async_query(
                    "INSERT INTO fia_factures (numero, sponsor_id, date_emission, date_echeance, "
                    "periode_debut, periode_fin, montant_ht, montant_tva, montant_ttc, statut, lignes, notes) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (numero, sponsor_id, date.today().isoformat(), date_ech.isoformat(),
                     pd.isoformat(), pf.isoformat(),
                     float(montant_ht), float(montant_tva), float(montant_ttc),
                     "brouillon", json.dumps(lignes), form.get("notes", "")),
                )
                break
            except Exception as dup_err:
                if "Duplicate" in str(dup_err) and _attempt < 2:
                    continue
                raise
        logger.info("[ADMIN_AUDIT] action=facture_create numero=%s sponsor_id=%s montant_ttc=%s", numero, sponsor_id, float(montant_ttc))
    except Exception as e:
        logger.error("[ADMIN] facture create: %s", e)
        tpl = env.get_template("admin/facture_form.html")
        return HTMLResponse(tpl.render(active="factures", sponsors=sponsors, error=str(e)), status_code=500)

    return RedirectResponse(url="/admin/factures", status_code=302)


@router.get("/admin/factures/{facture_id}", response_class=HTMLResponse, include_in_schema=False)
async def admin_facture_detail(request: Request, facture_id: int):
    redir = _require_auth(request)
    if redir:
        return redir
    facture = await db_cloudsql.async_fetchone(
        "SELECT f.*, s.nom AS sponsor_nom FROM fia_factures f "
        "LEFT JOIN fia_sponsors s ON f.sponsor_id = s.id WHERE f.id = %s", (facture_id,))
    if not facture:
        return RedirectResponse(url="/admin/factures", status_code=302)
    lignes = json.loads(facture.get("lignes") or "[]")
    tpl = env.get_template("admin/facture_detail.html")
    return HTMLResponse(tpl.render(active="factures", facture=facture, lignes=lignes))


@router.post("/admin/factures/{facture_id}/status", include_in_schema=False)
async def admin_facture_update_status(request: Request, facture_id: int):
    redir = _require_auth(request)
    if redir:
        return redir
    form = await request.form()
    new_statut = form.get("statut", "")
    if new_statut in _VALID_STATUTS:
        try:
            await db_cloudsql.async_query(
                "UPDATE fia_factures SET statut = %s WHERE id = %s", (new_statut, facture_id))
            logger.info("[ADMIN_AUDIT] action=facture_status_update facture_id=%s new_statut=%s", facture_id, new_statut)
        except Exception as e:
            logger.error("[ADMIN] facture status update: %s", e)
    return RedirectResponse(url=f"/admin/factures/{facture_id}", status_code=302)


@router.get("/admin/factures/{facture_id}/pdf", include_in_schema=False)
async def admin_facture_pdf(request: Request, facture_id: int):
    redir = _require_auth(request)
    if redir:
        return redir

    facture = await db_cloudsql.async_fetchone(
        "SELECT f.*, s.nom AS sponsor_nom, s.adresse AS sponsor_adresse FROM fia_factures f "
        "LEFT JOIN fia_sponsors s ON f.sponsor_id = s.id WHERE f.id = %s", (facture_id,))
    if not facture:
        return RedirectResponse(url="/admin/factures", status_code=302)

    config = await db_cloudsql.async_fetchone("SELECT * FROM fia_config_entreprise WHERE id = 1") or {}
    lignes = json.loads(facture.get("lignes") or "[]")

    # Convert date objects to strings for PDF
    for key in ("date_emission", "date_echeance", "periode_debut", "periode_fin"):
        if facture.get(key) and not isinstance(facture[key], str):
            facture[key] = str(facture[key])

    from services.admin_pdf import generate_invoice_pdf
    pdf_buf = generate_invoice_pdf(facture, config, lignes)

    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={facture['numero']}.pdf"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# CONTRATS CRUD (S06)
# ══════════════════════════════════════════════════════════════════════════════

_VALID_CONTRAT_STATUTS = ("brouillon", "envoye", "signe", "actif", "expire", "resilie")


def _next_contrat_number(existing_count: int) -> str:
    today = date.today()
    return f"CTR-{today.strftime('%Y%m')}-{existing_count + 1:04d}"


@router.get("/admin/contrats", response_class=HTMLResponse, include_in_schema=False)
async def admin_contrats_list(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    contrats = []
    try:
        contrats = await db_cloudsql.async_fetchall(
            "SELECT c.*, s.nom AS sponsor_nom FROM fia_contrats c "
            "LEFT JOIN fia_sponsors s ON c.sponsor_id = s.id "
            "ORDER BY c.created_at DESC"
        )
    except Exception as e:
        logger.error("[ADMIN] contrats list: %s", e)
    tpl = env.get_template("admin/contrats.html")
    return HTMLResponse(tpl.render(active="contrats", contrats=contrats))


@router.get("/admin/contrats/new", response_class=HTMLResponse, include_in_schema=False)
async def admin_contrat_new_form(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom") or []
    tpl = env.get_template("admin/contrat_form.html")
    return HTMLResponse(tpl.render(active="contrats", contrat=None, sponsors=sponsors, error=None))


@router.post("/admin/contrats/new", response_class=HTMLResponse, include_in_schema=False)
async def admin_contrat_create(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    sponsor_id = form.get("sponsor_id")
    if not sponsor_id:
        sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom") or []
        tpl = env.get_template("admin/contrat_form.html")
        return HTMLResponse(tpl.render(active="contrats", contrat=None, sponsors=sponsors, error="Le sponsor est obligatoire."), status_code=400)

    try:
        # Generate numero with retry on duplicate
        for _attempt in range(3):
            cnt_row = await db_cloudsql.async_fetchone(
                "SELECT COUNT(*) AS cnt FROM fia_contrats WHERE numero LIKE %s",
                (f"CTR-{date.today().strftime('%Y%m')}-%",))
            numero = _next_contrat_number(cnt_row["cnt"] if cnt_row else 0)
            try:
                await db_cloudsql.async_query(
                    "INSERT INTO fia_contrats (sponsor_id, numero, type_contrat, product_codes, "
                    "date_debut, date_fin, montant_mensuel_ht, conditions_particulieres) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (int(sponsor_id), numero, form.get("type_contrat", "standard"),
                     form.get("product_codes", "") or None,
                     form.get("date_debut"), form.get("date_fin"),
                     float(form.get("montant_mensuel_ht", 0)),
                     form.get("conditions_particulieres", "") or None),
                )
                break
            except Exception as dup_err:
                if "Duplicate" in str(dup_err) and _attempt < 2:
                    continue
                raise
        logger.info("[ADMIN_AUDIT] action=contrat_create numero=%s sponsor_id=%s", numero, sponsor_id)
    except Exception as e:
        logger.error("[ADMIN] contrat create: %s", e)
        sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom") or []
        tpl = env.get_template("admin/contrat_form.html")
        return HTMLResponse(tpl.render(active="contrats", contrat=None, sponsors=sponsors, error=str(e)), status_code=500)

    return RedirectResponse(url="/admin/contrats", status_code=302)


@router.get("/admin/contrats/{contrat_id}", response_class=HTMLResponse, include_in_schema=False)
async def admin_contrat_detail(request: Request, contrat_id: int):
    redir = _require_auth(request)
    if redir:
        return redir
    contrat = await db_cloudsql.async_fetchone(
        "SELECT c.*, s.nom AS sponsor_nom FROM fia_contrats c "
        "LEFT JOIN fia_sponsors s ON c.sponsor_id = s.id WHERE c.id = %s", (contrat_id,))
    if not contrat:
        return RedirectResponse(url="/admin/contrats", status_code=302)
    tpl = env.get_template("admin/contrat_detail.html")
    return HTMLResponse(tpl.render(active="contrats", contrat=contrat))


@router.get("/admin/contrats/{contrat_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def admin_contrat_edit_form(request: Request, contrat_id: int):
    redir = _require_auth(request)
    if redir:
        return redir
    contrat = await db_cloudsql.async_fetchone("SELECT * FROM fia_contrats WHERE id = %s", (contrat_id,))
    if not contrat:
        return RedirectResponse(url="/admin/contrats", status_code=302)
    sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom") or []
    tpl = env.get_template("admin/contrat_form.html")
    return HTMLResponse(tpl.render(active="contrats", contrat=contrat, sponsors=sponsors, error=None))


@router.post("/admin/contrats/{contrat_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def admin_contrat_update(request: Request, contrat_id: int):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    sponsor_id = form.get("sponsor_id")
    if not sponsor_id:
        contrat = await db_cloudsql.async_fetchone("SELECT * FROM fia_contrats WHERE id = %s", (contrat_id,))
        sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom") or []
        tpl = env.get_template("admin/contrat_form.html")
        return HTMLResponse(tpl.render(active="contrats", contrat=contrat, sponsors=sponsors, error="Le sponsor est obligatoire."), status_code=400)

    try:
        await db_cloudsql.async_query(
            "UPDATE fia_contrats SET sponsor_id=%s, type_contrat=%s, product_codes=%s, "
            "date_debut=%s, date_fin=%s, montant_mensuel_ht=%s, conditions_particulieres=%s WHERE id=%s",
            (int(sponsor_id), form.get("type_contrat", "standard"),
             form.get("product_codes", "") or None,
             form.get("date_debut"), form.get("date_fin"),
             float(form.get("montant_mensuel_ht", 0)),
             form.get("conditions_particulieres", "") or None,
             contrat_id),
        )
        logger.info("[ADMIN_AUDIT] action=contrat_update contrat_id=%s", contrat_id)
    except Exception as e:
        logger.error("[ADMIN] contrat update: %s", e)

    return RedirectResponse(url=f"/admin/contrats/{contrat_id}", status_code=302)


@router.post("/admin/contrats/{contrat_id}/status", include_in_schema=False)
async def admin_contrat_update_status(request: Request, contrat_id: int):
    redir = _require_auth(request)
    if redir:
        return redir
    form = await request.form()
    new_statut = form.get("statut", "")
    if new_statut in _VALID_CONTRAT_STATUTS:
        try:
            await db_cloudsql.async_query(
                "UPDATE fia_contrats SET statut = %s WHERE id = %s", (new_statut, contrat_id))
            logger.info("[ADMIN_AUDIT] action=contrat_status_update contrat_id=%s new_statut=%s", contrat_id, new_statut)
        except Exception as e:
            logger.error("[ADMIN] contrat status update: %s", e)
    return RedirectResponse(url=f"/admin/contrats/{contrat_id}", status_code=302)


@router.get("/admin/contrats/{contrat_id}/pdf", include_in_schema=False)
async def admin_contrat_pdf(request: Request, contrat_id: int):
    redir = _require_auth(request)
    if redir:
        return redir

    contrat = await db_cloudsql.async_fetchone(
        "SELECT c.*, s.nom AS sponsor_nom, s.adresse AS sponsor_adresse, s.siret AS sponsor_siret "
        "FROM fia_contrats c LEFT JOIN fia_sponsors s ON c.sponsor_id = s.id WHERE c.id = %s", (contrat_id,))
    if not contrat:
        return RedirectResponse(url="/admin/contrats", status_code=302)

    config = await db_cloudsql.async_fetchone("SELECT * FROM fia_config_entreprise WHERE id = 1") or {}

    from services.admin_pdf import generate_contrat_pdf
    pdf_buf = generate_contrat_pdf(contrat, config)

    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={contrat['numero']}.pdf"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG ENTREPRISE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/config", response_class=HTMLResponse, include_in_schema=False)
async def admin_config_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    cfg = {}
    try:
        cfg = await db_cloudsql.async_fetchone("SELECT * FROM fia_config_entreprise WHERE id = 1") or {}
    except Exception as e:
        logger.error("[ADMIN] config read: %s", e)
    from services.alerting import DEFAULT_THRESHOLDS, get_alert_thresholds
    try:
        alert_cfg = await get_alert_thresholds()
    except Exception:
        alert_cfg = dict(DEFAULT_THRESHOLDS)
    tpl = env.get_template("admin/config.html")
    return HTMLResponse(tpl.render(active="config", cfg=cfg, success=False,
                                   alert_cfg=alert_cfg, alert_success=False))


@router.post("/admin/config", response_class=HTMLResponse, include_in_schema=False)
async def admin_config_save(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    try:
        await db_cloudsql.async_query(
            "UPDATE fia_config_entreprise SET raison_sociale=%s, siret=%s, adresse=%s, "
            "code_postal=%s, ville=%s, pays=%s, email=%s, telephone=%s, "
            "tva_intra=%s, taux_tva=%s, iban=%s, bic=%s, "
            "forme_juridique=%s, rcs=%s, capital_social=%s WHERE id=1",
            (form.get("raison_sociale", ""), form.get("siret", ""),
             form.get("adresse", ""), form.get("code_postal", ""),
             form.get("ville", ""), form.get("pays", "France"),
             form.get("email", ""), form.get("telephone", ""),
             form.get("tva_intra", ""), float(form.get("taux_tva", 20)),
             form.get("iban", ""), form.get("bic", ""),
             form.get("forme_juridique", "EI"), form.get("rcs", ""),
             form.get("capital_social", "")),
        )
        from middleware.ip_ban import _extract_client_ip
        logger.info("[ADMIN_AUDIT] action=config_update ip=%s", _extract_client_ip(request))
    except Exception as e:
        logger.error("[ADMIN] config save: %s", e)

    cfg = {}
    try:
        cfg = await db_cloudsql.async_fetchone("SELECT * FROM fia_config_entreprise WHERE id = 1") or {}
    except Exception:
        pass
    from services.alerting import DEFAULT_THRESHOLDS, get_alert_thresholds
    try:
        alert_cfg = await get_alert_thresholds()
    except Exception:
        alert_cfg = dict(DEFAULT_THRESHOLDS)
    tpl = env.get_template("admin/config.html")
    return HTMLResponse(tpl.render(active="config", cfg=cfg, success=True,
                                   alert_cfg=alert_cfg, alert_success=False))


@router.post("/admin/config/alerts", response_class=HTMLResponse, include_in_schema=False)
async def admin_config_alerts_save(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    _ALERT_KEYS = {
        "alert_error_rate_warn": lambda v: str(float(v) / 100),  # % → ratio
        "alert_error_rate_crit": lambda v: str(float(v) / 100),
        "alert_latency_p95_warn": lambda v: str(int(float(v))),
        "alert_latency_p95_crit": lambda v: str(int(float(v))),
        "alert_cpu_warn": lambda v: str(float(v) / 100),  # % → ratio
        "alert_cpu_crit": lambda v: str(float(v) / 100),
        "alert_memory_warn": lambda v: str(float(v) / 100),
        "alert_memory_crit": lambda v: str(float(v) / 100),
        "alert_gemini_avg_warn": lambda v: str(int(float(v))),
        "alert_gemini_avg_crit": lambda v: str(int(float(v))),
        "alert_cost_month_warn": lambda v: str(int(float(v))),
        "alert_cost_month_crit": lambda v: str(int(float(v))),
    }
    try:
        for key, convert in _ALERT_KEYS.items():
            val = form.get(key, "")
            if val:
                stored = convert(val)
                await db_cloudsql.async_query(
                    "INSERT INTO admin_config (config_key, config_value) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE config_value = %s",
                    (key, stored, stored),
                )
        logger.info("[ADMIN_AUDIT] action=alert_config_save keys_updated=%d", len(_ALERT_KEYS))
    except Exception as e:
        logger.error("[ADMIN] alert config save: %s", e)

    cfg = {}
    try:
        cfg = await db_cloudsql.async_fetchone("SELECT * FROM fia_config_entreprise WHERE id = 1") or {}
    except Exception:
        pass
    from services.alerting import get_alert_thresholds
    try:
        alert_cfg = await get_alert_thresholds()
    except Exception:
        from services.alerting import DEFAULT_THRESHOLDS
        alert_cfg = dict(DEFAULT_THRESHOLDS)
    tpl = env.get_template("admin/config.html")
    return HTMLResponse(tpl.render(active="config", cfg=cfg, success=False,
                                   alert_cfg=alert_cfg, alert_success=True))


# ── Realtime feed ─────────────────────────────────────────────────────────────

@router.get("/admin/realtime", response_class=HTMLResponse, include_in_schema=False)
async def admin_realtime_page(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    tpl = env.get_template("admin/realtime.html")
    return HTMLResponse(tpl.render(active="realtime"))


_PERIOD_SQL = {
    "24h": "created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)",
    "today": "created_at >= CURDATE()",
    "week": "created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)",
    "month": "created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)",
}
_PERIOD_LABELS = {"24h": "24 dernieres heures", "today": "Aujourd'hui",
                  "week": "7 derniers jours", "month": "30 derniers jours"}


def _build_realtime_where(event_type: str, period: str):
    clauses = []
    params: list = []
    p = _PERIOD_SQL.get(period, _PERIOD_SQL["today"])
    clauses.append(p)
    if event_type != "all":
        clauses.append("event_type = %s")
        params.append(event_type)
    where = "WHERE " + " AND ".join(clauses)
    return where, params


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


# ── Engagement API ────────────────────────────────────────────────────────────

# ── Sponsor name resolver (from config/sponsors.json) ─────────────────────────

_SPONSORS_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "sponsors.json")
_sponsor_name_cache: dict | None = None


def _load_sponsor_names() -> dict:
    """Build product_code → sponsor name map from sponsors.json. Cached."""
    global _sponsor_name_cache
    if _sponsor_name_cache is not None:
        return _sponsor_name_cache
    result = {}
    try:
        with open(_SPONSORS_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for _slot_group in data.get("slots", {}).values():
            for slot in _slot_group.values():
                if isinstance(slot, dict) and "id" in slot:
                    result[slot["id"]] = slot.get("name", "Vacant")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("[ADMIN] sponsors.json load failed: %s", e)
    _sponsor_name_cache = result
    return result


_ENGAGEMENT_EVENTS = frozenset([
    "chatbot-open", "chatbot-close", "chatbot-message",
    "rating-submitted", "rating-popup-shown", "rating-dismissed",
    "simulateur-grille-generated", "simulateur-grille-audited",
    "meta75-launched", "meta75-pdf-download",
])

_EVENT_CATEGORIES = {
    "chatbot-open": "chatbot", "chatbot-close": "chatbot", "chatbot-message": "chatbot",
    "rating-submitted": "rating", "rating-popup-shown": "rating", "rating-dismissed": "rating",
    "simulateur-grille-generated": "simulateur", "simulateur-grille-audited": "simulateur",
    "meta75-launched": "sponsor", "meta75-pdf-download": "sponsor",
}

_VALID_MODULES = {"loto", "euromillions"}
_VALID_CATEGORIES = {"chatbot", "rating", "simulateur", "sponsor"}


_VALID_PRODUCT_CODES = frozenset([
    "LOTO_FR", "LOTO_FR_A", "LOTO_FR_B",
    "EM_FR", "EM_FR_A", "EM_FR_B", "EM_EN", "EM_EN_A", "EM_EN_B",
    "EM_ES", "EM_ES_A", "EM_ES_B", "EM_PT", "EM_PT_A", "EM_PT_B",
    "EM_DE", "EM_DE_A", "EM_DE_B", "EM_NL", "EM_NL_A", "EM_NL_B",
])


def _build_engagement_where(period, date_start, date_end, event_type, module, lang, device, category="", product_code=""):
    ds, de = _period_to_dates(period, date_start, date_end)
    where = ["created_at >= %s", "created_at < %s", "event_type NOT LIKE 'sponsor-%%'"]
    params = [ds.isoformat(), de.isoformat()]
    if category and category in _VALID_CATEGORIES:
        cat_events = [ev for ev, c in _EVENT_CATEGORIES.items() if c == category]
        if cat_events:
            placeholders = ",".join(["%s"] * len(cat_events))
            where.append(f"event_type IN ({placeholders})")
            params.extend(cat_events)
    if event_type and event_type in _ENGAGEMENT_EVENTS:
        where.append("event_type = %s")
        params.append(event_type)
    if module and module in _VALID_MODULES:
        where.append("module = %s")
        params.append(module)
    if lang and lang in _VALID_LANGS:
        where.append("lang = %s")
        params.append(lang)
    if device and device in _VALID_DEVICES:
        where.append("device = %s")
        params.append(device)
    if product_code and product_code in _VALID_PRODUCT_CODES:
        where.append("product_code = %s")
        params.append(product_code)
    return " AND ".join(where), params, ds, de


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


# ══════════════════════════════════════════════════════════════════════════════
# TARIFS — Grille tarifaire EU + Switch EI/SASU
# ══════════════════════════════════════════════════════════════════════════════

_PACKS = [
    {"name": "FR Complet", "codes": "LOTO_FR_A + EM_FR_A", "pays": "France (Loto+EM)", "tarif": "799 EUR (-10%)", "requires_sasu": False},
    {"name": "DACH", "codes": "EM_DE_A", "pays": "DE, AT, CH", "tarif": "549 EUR", "requires_sasu": True},
    {"name": "Benelux", "codes": "EM_FR_A + EM_NL_A", "pays": "BE, NL, LU", "tarif": "799 EUR (-10%)", "requires_sasu": True},
    {"name": "Iberique", "codes": "EM_ES_A + EM_PT_A", "pays": "ES, PT", "tarif": "759 EUR (-15%)", "requires_sasu": True},
    {"name": "Continental A", "codes": "LOTO_FR_A + 6x EM_*_A", "pays": "9 pays Premium", "tarif": "2 499 EUR (-25%)", "requires_sasu": True},
    {"name": "Continental B", "codes": "LOTO_FR_B + 6x EM_*_B", "pays": "9 pays Standard", "tarif": "1 189 EUR (-20%)", "requires_sasu": True},
]

_PALIERS = [
    {"name": "Lancement", "impressions": "0-10K", "standard": "199 EUR (gel)", "premium": "449 EUR / 549 EUR T1", "hausse": "—"},
    {"name": "Croissance", "impressions": "10K-30K", "standard": "249 EUR", "premium": "549 EUR / 649 EUR T1", "hausse": "+25% max"},
    {"name": "Traction", "impressions": "30K-100K", "standard": "349 EUR", "premium": "699 EUR / 799 EUR T1", "hausse": "+25% max"},
    {"name": "Scale", "impressions": "100K+", "standard": "Sur mesure", "premium": "Sur mesure", "hausse": "Negocie"},
]

_VALID_TARIF_CODES = frozenset([
    "LOTO_FR_A", "LOTO_FR_B", "EM_FR_A", "EM_FR_B",
    "EM_EN_A", "EM_EN_B", "EM_ES_A", "EM_ES_B",
    "EM_PT_A", "EM_PT_B", "EM_DE_A", "EM_DE_B",
    "EM_NL_A", "EM_NL_B",
])


async def _get_admin_config():
    """Read admin_config key-value pairs into a dict."""
    cfg = {"billing_mode": "EI", "ei_raison_sociale": "EmovisIA — Jean-Philippe Godard",
           "ei_siret": "", "sasu_raison_sociale": "LotoIA SASU", "sasu_siret": ""}
    try:
        rows = await db_cloudsql.async_fetchall("SELECT config_key, config_value FROM admin_config")
        for r in rows:
            cfg[r["config_key"]] = r["config_value"]
    except Exception as e:
        logger.error("[ADMIN] admin_config read: %s", e)
    return cfg


@router.get("/admin/tarifs", response_class=HTMLResponse, include_in_schema=False)
async def admin_tarifs_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    cfg = await _get_admin_config()
    tarifs = []
    try:
        tarifs = await db_cloudsql.async_fetchall(
            "SELECT * FROM sponsor_tarifs ORDER BY FIELD(langue,'fr','en','es','pt','de','nl'), tier DESC"
        )
        tarifs = [{k: (_dec(v) if isinstance(v, Decimal) else v) for k, v in row.items()} for row in tarifs]
    except Exception as e:
        logger.error("[ADMIN] tarifs read: %s", e)

    tpl = env.get_template("admin/tarifs.html")
    return HTMLResponse(tpl.render(
        active="tarifs",
        billing_mode=cfg["billing_mode"],
        ei_raison_sociale=cfg["ei_raison_sociale"],
        ei_siret=cfg["ei_siret"],
        sasu_raison_sociale=cfg["sasu_raison_sociale"],
        sasu_siret=cfg["sasu_siret"],
        tarifs=tarifs,
        packs=_PACKS,
        paliers=_PALIERS,
    ))


@router.post("/admin/api/tarifs/mode", include_in_schema=False)
async def admin_api_tarifs_mode(request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        body = await request.json()
        mode = body.get("mode", "")
        if mode not in ("EI", "SASU"):
            return JSONResponse({"ok": False, "error": "Mode invalide"}, status_code=400)
        await db_cloudsql.async_query(
            "INSERT INTO admin_config (config_key, config_value) VALUES ('billing_mode', %s) "
            "ON DUPLICATE KEY UPDATE config_value = %s",
            (mode, mode),
        )
        from middleware.ip_ban import _extract_client_ip
        logger.info("[ADMIN_AUDIT] action=tarif_mode_change mode=%s ip=%s", mode, _extract_client_ip(request))
        return JSONResponse({"ok": True, "mode": mode})
    except Exception as e:
        logger.error("[ADMIN] tarifs mode switch: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.put("/admin/api/tarifs/{code}", include_in_schema=False)
async def admin_api_tarifs_update(request: Request, code: str):
    err = _require_auth_json(request)
    if err:
        return err
    if code not in _VALID_TARIF_CODES:
        return JSONResponse({"ok": False, "error": "Code invalide"}, status_code=400)
    try:
        body = await request.json()
        tarif = float(body.get("tarif_mensuel", 0))
        engagement = int(body.get("engagement_min_mois", 3))
        red6 = float(body.get("reduction_6m", 10))
        red12 = float(body.get("reduction_12m", 20))
        active = int(body.get("active", 1))
        if tarif < 0 or engagement < 1 or not (0 <= red6 <= 100) or not (0 <= red12 <= 100):
            return JSONResponse({"ok": False, "error": "Valeurs invalides"}, status_code=400)
        await db_cloudsql.async_query(
            "UPDATE sponsor_tarifs SET tarif_mensuel=%s, engagement_min_mois=%s, "
            "reduction_6m=%s, reduction_12m=%s, active=%s WHERE code=%s",
            (tarif, engagement, red6, red12, active, code),
        )
        from middleware.ip_ban import _extract_client_ip
        logger.info("[ADMIN_AUDIT] action=tarif_update code=%s ip=%s", code, _extract_client_ip(request))
        return JSONResponse({"ok": True, "code": code})
    except Exception as e:
        logger.error("[ADMIN] tarif update %s: %s", code, e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/admin/api/tarifs", include_in_schema=False)
async def admin_api_tarifs_data(request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        cfg = await _get_admin_config()
        tarifs = await db_cloudsql.async_fetchall("SELECT * FROM sponsor_tarifs ORDER BY code")
        tarifs = [{k: (_dec(v) if isinstance(v, Decimal) else v) for k, v in row.items()} for row in tarifs]
        return JSONResponse({"billing_mode": cfg["billing_mode"], "tarifs": tarifs, "packs": _PACKS, "paliers": _PALIERS})
    except Exception as e:
        logger.error("[ADMIN] tarifs API: %s", e)
        return JSONResponse({"billing_mode": "EI", "tarifs": [], "packs": [], "paliers": []}, status_code=500)


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
    from middleware.ip_ban import _extract_client_ip
    real_ip = _extract_client_ip(request)
    from services.circuit_breaker import gemini_breaker
    prev_state = gemini_breaker.state
    gemini_breaker.force_close()
    logger.info("[ADMIN_AUDIT] action=circuit_breaker_reset ip=%s prev_state=%s", real_ip, prev_state)
    return JSONResponse({"status": "closed", "previous_state": prev_state, "message": "Circuit breaker reset"})


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
            f"SUM(CASE WHEN DATE(created_at) = CURDATE() THEN 1 ELSE 0 END) AS today "
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

_CM_PERIOD_SQL = {
    "1h": "created_at >= NOW() - INTERVAL 1 HOUR",
    "6h": "created_at >= NOW() - INTERVAL 6 HOUR",
    "24h": "created_at >= NOW() - INTERVAL 24 HOUR",
    "7d": "created_at >= NOW() - INTERVAL 7 DAY",
    "30d": "created_at >= NOW() - INTERVAL 30 DAY",
}


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
            f"SELECT created_at, module, lang, question, phase_detected, sql_generated, "
            f"sql_status, duration_ms, is_error, error_detail, grid_count, has_exclusions "
            f"FROM chat_log WHERE {w} ORDER BY created_at DESC LIMIT 5000",
            tuple(params),
        )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["created_at", "module", "lang", "question", "phase", "sql", "sql_status",
                         "duration_ms", "is_error", "error_detail", "grid_count", "has_exclusions"])
        for r in rows:
            writer.writerow([
                r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r.get("created_at") else "",
                r["module"], r["lang"], r["question"][:200],
                r["phase_detected"], (r["sql_generated"] or "")[:200],
                r["sql_status"], r["duration_ms"],
                int(r["is_error"]), r["error_detail"] or "",
                r["grid_count"], int(r["has_exclusions"]),
            ])
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=chatbot_log_{period}.csv"},
        )
    except Exception as e:
        logger.error("[ADMIN] chatbot-log CSV: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)
