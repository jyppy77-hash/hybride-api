"""
Routes — English EuroMillions HTML pages.
Phase 11 — /en/euromillions/...
"""

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
import db_cloudsql

router = APIRouter()


# =========================
# Helpers
# =========================

def serve_en_em_page(filename: str):
    """Sert une page HTML depuis ui/en/euromillions/."""
    return FileResponse(f"ui/en/euromillions/{filename}", media_type="text/html")


# =========================
# Routes EN EuroMillions — Pages HTML
# =========================

@router.get("/en/euromillions", include_in_schema=False)
async def en_em_home():
    """EuroMillions EN — Home (hub)."""
    return serve_en_em_page("home.html")


@router.get("/en/euromillions/generator", include_in_schema=False)
async def en_em_generator():
    """EuroMillions EN — Grid Explorer (generator)."""
    return serve_en_em_page("generator.html")


@router.get("/en/euromillions/simulator", include_in_schema=False)
async def en_em_simulator():
    """EuroMillions EN — Grid Analysis (simulator)."""
    return serve_en_em_page("simulator.html")


@router.get("/en/euromillions/statistics", include_in_schema=False)
async def en_em_statistics():
    """EuroMillions EN — Statistics and history."""
    return serve_en_em_page("statistics.html")


@router.get("/en/euromillions/history", include_in_schema=False)
async def en_em_history():
    """EuroMillions EN — Draw history."""
    return serve_en_em_page("history.html")


@router.get("/en/euromillions/faq", include_in_schema=False)
async def en_em_faq():
    """EuroMillions EN — FAQ with injected DB stats."""
    try:
        total = await db_cloudsql.get_em_tirages_count()
    except Exception:
        total = 0
    with open("ui/en/euromillions/faq.html", "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__EM_DB_TOTAL__", str(total))
    return HTMLResponse(content=html)


@router.get("/en/euromillions/news", include_in_schema=False)
async def en_em_news():
    """EuroMillions EN — News."""
    return serve_en_em_page("news.html")
