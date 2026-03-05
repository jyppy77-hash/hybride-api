"""
Admin back-office — /admin/
============================
Auth via cookie (timing-safe) + password login.
Dashboard with live KPI cards (sponsor impressions + ratings).
"""

import logging
import os
import secrets

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

import db_cloudsql
from config.templates import env

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])

_ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
_COOKIE_NAME = "lotoia_admin_token"


def _is_authenticated(request: Request) -> bool:
    """Check admin cookie with timing-safe comparison."""
    if not _ADMIN_TOKEN:
        return False
    token = request.cookies.get(_COOKIE_NAME, "")
    if not token:
        return False
    return secrets.compare_digest(token, _ADMIN_TOKEN)


@router.get("/admin/login", response_class=HTMLResponse, include_in_schema=False)
async def admin_login_page(request: Request):
    """Render login form."""
    if _is_authenticated(request):
        return RedirectResponse(url="/admin", status_code=302)
    tpl = env.get_template("admin/login.html")
    return HTMLResponse(tpl.render(error=None))


@router.post("/admin/login", response_class=HTMLResponse, include_in_schema=False)
async def admin_login(request: Request, password: str = Form(...)):
    """Validate password, set auth cookie."""
    if not _ADMIN_PASSWORD or not secrets.compare_digest(password, _ADMIN_PASSWORD):
        tpl = env.get_template("admin/login.html")
        return HTMLResponse(tpl.render(error="Mot de passe incorrect."), status_code=401)

    response = RedirectResponse(url="/admin", status_code=302)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=_ADMIN_TOKEN,
        max_age=86400 * 7,  # 7 days
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )
    return response


@router.get("/admin/logout", include_in_schema=False)
async def admin_logout():
    """Clear auth cookie."""
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(key=_COOKIE_NAME, path="/")
    return response


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_dashboard(request: Request):
    """Main dashboard with live KPI cards."""
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    # Fetch sponsor impression KPIs (today)
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

    # Fetch ratings KPIs (global)
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
        impressions=impressions,
        clicks=clicks,
        videos=videos,
        avg_rating=avg_rating,
        review_count=review_count,
    ))
