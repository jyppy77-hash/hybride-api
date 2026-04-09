"""
Admin calendar heatmap — monthly stats API.
============================================
Aggregates daily visitors, impressions, sessions, chatbot counts
from existing tables (event_log, sponsor_impressions, chat_log).
No pre-aggregated table — queries run on-the-fly with GROUP BY day.
"""

import calendar
import logging
from datetime import date

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse

import db_cloudsql
from config.templates import env
from routes.admin_helpers import (
    require_auth as _require_auth,
    require_auth_json as _require_auth_json,
    dec as _dec,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

# Timezone conversion fragment (UTC → Europe/Paris) — V88 convention
_TZ = "CONVERT_TZ(created_at, '+00:00', 'Europe/Paris')"


@router.get("/admin/calendar", response_class=HTMLResponse, include_in_schema=False)
async def admin_calendar_page(request: Request):
    """Calendar heatmap page."""
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/calendar.html")
    return HTMLResponse(tpl.render(active="calendar"))


@router.get("/admin/api/calendar-data", include_in_schema=False)
async def admin_api_calendar_data(
    request: Request,
    year: int = Query(default=None),
    month: int = Query(default=None),
):
    err = _require_auth_json(request)
    if err:
        return err

    # Defaults: current month
    today = date.today()
    if year is None:
        year = today.year
    if month is None:
        month = today.month

    # Validation
    if year < 2025 or year > 2030:
        return JSONResponse({"error": "year must be between 2025 and 2030"}, status_code=400)
    if month < 1 or month > 12:
        return JSONResponse({"error": "month must be between 1 and 12"}, status_code=400)

    num_days = calendar.monthrange(year, month)[1]

    # Init all days to zero
    days: dict[str, dict] = {}
    for d in range(1, num_days + 1):
        days[str(d)] = {"visitors": 0, "impressions": 0, "sessions": 0, "chatbot": 0}

    # WHERE fragment reused across 3 queries
    where_tz = (
        f"YEAR({_TZ}) = %s AND MONTH({_TZ}) = %s"
    )
    params = (year, month)

    # ──────────────────────────────────────────────────────────────────
    # MÉTHODOLOGIE VISITEURS (V92 S09)
    # ──────────────────────────────────────────────────────────────────
    # Les visiteurs uniques sont comptés via UNION (dedup) de 3 tables :
    #   - event_log.ip_address : IP brute du visiteur
    #   - sponsor_impressions.session_hash : SHA-256(ip|ua|date)
    #   - chat_log.ip_hash : SHA-256(ip)
    #
    # LIMITATION : un même visiteur peut être compté 2-3× car les
    # identifiants diffèrent structurellement entre tables (IP brute
    # vs hash). Le UNION déduplique les doublons intra-table mais
    # pas les doublons cross-table.
    #
    # IMPACT : sur-estimation estimée ~10-20% sur les jours à fort
    # trafic. Acceptable pour un dashboard admin interne. Pour un
    # reporting sponsor, utiliser les métriques GA4 ou Umami qui
    # dédupliquent nativement par client_id/session.
    # ──────────────────────────────────────────────────────────────────
    try:
        async with db_cloudsql.get_connection_readonly() as conn:
            cur = await conn.cursor()
            await cur.execute(
                f"SELECT day, COUNT(DISTINCT visitor_id) AS visitors FROM ("
                f"  SELECT DAY({_TZ}) AS day, ip_address AS visitor_id"
                f"  FROM event_log WHERE {where_tz}"
                f"  UNION"
                f"  SELECT DAY({_TZ}) AS day, session_hash AS visitor_id"
                f"  FROM sponsor_impressions WHERE {where_tz}"
                f"  UNION"
                f"  SELECT DAY({_TZ}) AS day, ip_hash AS visitor_id"
                f"  FROM chat_log WHERE {where_tz}"
                f") AS all_ips GROUP BY day",
                params * 3,
            )
            rows = await cur.fetchall()
        for r in rows:
            d = str(_dec(r["day"]))
            if d in days:
                days[d]["visitors"] = _dec(r["visitors"])
    except Exception as e:
        logger.error("[ADMIN CALENDAR] visitors query failed: %s", e)

    # --- Query 2: sessions from event_log ---
    try:
        async with db_cloudsql.get_connection_readonly() as conn:
            cur = await conn.cursor()
            await cur.execute(
                f"SELECT DAY({_TZ}) AS day, "
                f"COUNT(*) AS sessions "
                f"FROM event_log WHERE {where_tz} "
                f"GROUP BY day",
                params,
            )
            rows = await cur.fetchall()
        for r in rows:
            d = str(_dec(r["day"]))
            if d in days:
                days[d]["sessions"] = _dec(r["sessions"])
    except Exception as e:
        logger.error("[ADMIN CALENDAR] sessions query failed: %s", e)

    # --- Query 3: impressions from sponsor_impressions ---
    try:
        async with db_cloudsql.get_connection_readonly() as conn:
            cur = await conn.cursor()
            await cur.execute(
                f"SELECT DAY({_TZ}) AS day, "
                f"COUNT(*) AS impressions "
                f"FROM sponsor_impressions WHERE {where_tz} "
                f"GROUP BY day",
                params,
            )
            rows = await cur.fetchall()
        for r in rows:
            d = str(_dec(r["day"]))
            if d in days:
                days[d]["impressions"] = _dec(r["impressions"])
    except Exception as e:
        logger.error("[ADMIN CALENDAR] sponsor_impressions query failed: %s", e)

    # --- Query 4: chatbot from chat_log ---
    try:
        async with db_cloudsql.get_connection_readonly() as conn:
            cur = await conn.cursor()
            await cur.execute(
                f"SELECT DAY({_TZ}) AS day, "
                f"COUNT(*) AS chatbot "
                f"FROM chat_log WHERE {where_tz} "
                f"GROUP BY day",
                params,
            )
            rows = await cur.fetchall()
        for r in rows:
            d = str(_dec(r["day"]))
            if d in days:
                days[d]["chatbot"] = _dec(r["chatbot"])
    except Exception as e:
        logger.error("[ADMIN CALENDAR] chat_log query failed: %s", e)

    return JSONResponse({"year": year, "month": month, "days": days})
