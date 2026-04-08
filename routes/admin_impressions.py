"""
Admin impressions — sponsor impressions page, API, CSV/PDF exports.
===================================================================
Split from routes/admin.py (Phase 2 refacto V88).
"""

import csv
import io
import logging

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

import db_cloudsql
from config.templates import env
from routes.admin_helpers import (
    require_auth as _require_auth,
    require_auth_json as _require_auth_json,
    dec as _dec,
    period_label as _period_label,
    build_impressions_where as _build_impressions_where,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


# ── Impressions page ──────────────────────────────────────────────────────────

@router.get("/admin/impressions", response_class=HTMLResponse, include_in_schema=False)
async def admin_impressions_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/impressions.html")
    return HTMLResponse(tpl.render(active="impressions"))


# ── API: Impressions data ─────────────────────────────────────────────────────

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
            if et in ("sponsor-popup-shown", "sponsor-inline-shown", "sponsor-result-shown"):
                total_imp += _dec(r["cnt"])
            elif et == "sponsor-click":
                kpi["clicks"] = _dec(r["cnt"])
                total_clicks = _dec(r["cnt"])
            elif et == "sponsor-video-played":
                kpi["videos"] = _dec(r["cnt"])
        kpi["impressions"] = total_imp

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
            f"  SUM(CASE WHEN event_type IN ('sponsor-popup-shown', 'sponsor-inline-shown', 'sponsor-result-shown') THEN 1 ELSE 0 END) AS impressions, "
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


# ── Exports ──────────────────────────────────────────────────────────────────

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
            if et in ("sponsor-popup-shown", "sponsor-inline-shown", "sponsor-result-shown"):
                total_imp += _dec(r["cnt"])
            elif et == "sponsor-click":
                kpi["clicks"] = _dec(r["cnt"]); total_clicks = _dec(r["cnt"])
            elif et == "sponsor-video-played":
                kpi["videos"] = _dec(r["cnt"])
        kpi["impressions"] = total_imp
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
