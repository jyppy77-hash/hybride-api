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
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

import db_cloudsql
from config.templates import env

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])

_ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
_COOKIE_NAME = "lotoia_admin_token"

_VALID_EVENTS = {"sponsor-popup-shown", "sponsor-click", "sponsor-video-played", "sponsor-inline-shown", "sponsor-result-shown", "sponsor-pdf-downloaded"}
_VALID_LANGS = {"fr", "en", "es", "pt", "de", "nl"}
_VALID_DEVICES = {"mobile", "desktop", "tablet"}
_VALID_SOURCES = {"chatbot_loto", "chatbot_em", "popup_accueil"}
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
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)
    return None


def _require_auth_json(request: Request):
    if not _is_authenticated(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


# ── Period helpers ────────────────────────────────────────────────────────────

def _period_to_dates(period: str, date_start: str = "", date_end: str = ""):
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


def _period_label(period: str, ds, de):
    labels = {"today": "Aujourd'hui", "7d": "7 derniers jours", "30d": "30 derniers jours",
              "month": "Ce mois", "last_month": "Mois dernier", "all": "Toute la periode"}
    return labels.get(period, f"{ds} — {de}")


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
                _kpi_vals[key] = r["cnt"]
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
        inline_shown=inline_shown,
        result_shown=result_shown,
        pdf_downloaded=pdf_downloaded,
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

def _build_impressions_where(period, date_start, date_end, event_type, lang, device):
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
    return " AND ".join(where), params, ds, de


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

    w, params, ds, de = _build_impressions_where(period, date_start, date_end, event_type, lang, device)

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


# ══════════════════════════════════════════════════════════════════════════════
# EXPORTS (CSV / PDF)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/api/impressions/csv", include_in_schema=False)
async def admin_export_impressions_csv(
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

    w, params, ds, de = _build_impressions_where(period, date_start, date_end, event_type, lang, device)

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
    period: str = Query("7d"),
    date_start: str = Query(""),
    date_end: str = Query(""),
):
    err = _require_auth_json(request)
    if err:
        return err

    w, params, ds, de = _build_impressions_where(period, date_start, date_end, "", "", "")

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
                kpi["impressions"] = r["cnt"]; total_imp = r["cnt"]
            elif et == "sponsor-click":
                kpi["clicks"] = r["cnt"]; total_clicks = r["cnt"]
            elif et == "sponsor-video-played":
                kpi["videos"] = r["cnt"]
        sess = await db_cloudsql.async_fetchone(
            f"SELECT COUNT(DISTINCT session_hash) AS s FROM sponsor_impressions WHERE {w}", tuple(params))
        kpi["sessions"] = sess["s"] if sess else 0
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
             "lang": r["lang"], "device": r["device"], "country": r["country"] or "", "cnt": r["cnt"]}
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
        sponsors = await db_cloudsql.async_fetchall("SELECT * FROM fia_sponsors ORDER BY nom")
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

        # Count events in period from sponsor_impressions
        lignes = []
        montant_ht = Decimal("0")
        for g in grille:
            row = await db_cloudsql.async_fetchone(
                "SELECT COUNT(*) AS cnt FROM sponsor_impressions "
                "WHERE event_type = %s AND DATE(created_at) >= %s AND DATE(created_at) <= %s",
                (g["event_type"], pd.isoformat(), pf.isoformat()),
            )
            qty = row["cnt"] if row else 0
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

        # Invoice number
        cnt_row = await db_cloudsql.async_fetchone(
            "SELECT COUNT(*) AS cnt FROM fia_factures WHERE numero LIKE %s",
            (f"FIA-{date.today().strftime('%Y%m')}-%",))
        numero = _next_invoice_number(cnt_row["cnt"] if cnt_row else 0)

        date_echeance_str = form.get("date_echeance", "")
        date_ech = date.fromisoformat(date_echeance_str) if date_echeance_str else (date.today() + timedelta(days=30))

        await db_cloudsql.async_query(
            "INSERT INTO fia_factures (numero, sponsor_id, date_emission, date_echeance, "
            "periode_debut, periode_fin, montant_ht, montant_tva, montant_ttc, statut, lignes, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (numero, sponsor_id, date.today().isoformat(), date_ech.isoformat(),
             pd.isoformat(), pf.isoformat(),
             float(montant_ht), float(montant_tva), float(montant_ttc),
             "brouillon", json.dumps(lignes), form.get("notes", "")),
        )
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
    tpl = env.get_template("admin/config.html")
    return HTMLResponse(tpl.render(active="config", cfg=cfg, success=False))


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
            "tva_intra=%s, taux_tva=%s, iban=%s, bic=%s WHERE id=1",
            (form.get("raison_sociale", ""), form.get("siret", ""),
             form.get("adresse", ""), form.get("code_postal", ""),
             form.get("ville", ""), form.get("pays", "France"),
             form.get("email", ""), form.get("telephone", ""),
             form.get("tva_intra", ""), float(form.get("taux_tva", 20)),
             form.get("iban", ""), form.get("bic", "")),
        )
    except Exception as e:
        logger.error("[ADMIN] config save: %s", e)

    cfg = {}
    try:
        cfg = await db_cloudsql.async_fetchone("SELECT * FROM fia_config_entreprise WHERE id = 1") or {}
    except Exception:
        pass
    tpl = env.get_template("admin/config.html")
    return HTMLResponse(tpl.render(active="config", cfg=cfg, success=True))


# ── Realtime feed ─────────────────────────────────────────────────────────────

@router.get("/admin/realtime", response_class=HTMLResponse, include_in_schema=False)
async def admin_realtime_page(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    tpl = env.get_template("admin/realtime.html")
    return HTMLResponse(tpl.render(active="realtime"))


@router.get("/admin/api/realtime", include_in_schema=False)
async def admin_api_realtime(request: Request, event_type: str = "all"):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        # Last 100 events
        where = ""
        params = []
        if event_type != "all":
            where = "WHERE event_type = %s"
            params.append(event_type)
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
                "created_at": r["created_at"].strftime("%H:%M:%S") if r.get("created_at") else "",
            })

        # KPI
        kpi_row = await db_cloudsql.async_fetchone(
            "SELECT "
            "  COUNT(*) AS today_count, "
            "  SUM(CASE WHEN created_at >= NOW() - INTERVAL 1 HOUR THEN 1 ELSE 0 END) AS hour_count, "
            "  COUNT(DISTINCT event_type) AS type_count "
            "FROM event_log WHERE created_at >= CURDATE()"
        )
        kpi = {
            "today": kpi_row["today_count"] if kpi_row else 0,
            "hour": kpi_row["hour_count"] if kpi_row else 0,
            "types": kpi_row["type_count"] if kpi_row else 0,
        }

        # Distinct event types for filter dropdown
        type_rows = await db_cloudsql.async_fetchall(
            "SELECT DISTINCT event_type FROM event_log ORDER BY event_type"
        )
        event_types = [r["event_type"] for r in type_rows]

        return JSONResponse({"events": events, "kpi": kpi, "event_types": event_types})
    except Exception as e:
        logger.error("[ADMIN] realtime: %s", e)
        return JSONResponse({"events": [], "kpi": {"today": 0, "hour": 0, "types": 0}, "event_types": []})
