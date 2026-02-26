from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
import db_cloudsql

router = APIRouter()


# =========================
# Helpers
# =========================

def serve_em_page(filename: str):
    """Sert une page HTML depuis ui/em/."""
    return FileResponse(f"ui/em/{filename}", media_type="text/html")


# =========================
# Routes EuroMillions — Pages HTML
# =========================

@router.get("/euromillions", include_in_schema=False)
async def em_accueil():
    """EuroMillions — Accueil (hub)."""
    return serve_em_page("accueil-em.html")


@router.get("/euromillions/generateur", include_in_schema=False)
async def em_generateur():
    """EuroMillions — Exploration de grilles (generateur)."""
    return serve_em_page("euromillions.html")


@router.get("/euromillions/simulateur", include_in_schema=False)
async def em_simulateur():
    """EuroMillions — Analyse de grille (simulateur)."""
    return serve_em_page("simulateur-em.html")


@router.get("/euromillions/statistiques", include_in_schema=False)
async def em_statistiques():
    """EuroMillions — Statistiques et historique."""
    return serve_em_page("statistiques-em.html")


@router.get("/euromillions/historique", include_in_schema=False)
async def em_historique():
    """EuroMillions — Historique des tirages."""
    return serve_em_page("historique-em.html")


@router.get("/euromillions/faq", include_in_schema=False)
async def em_faq():
    """EuroMillions — FAQ avec stats BDD injectees."""
    try:
        total = await db_cloudsql.get_em_tirages_count()
    except Exception:
        total = 0
    with open("ui/em/faq-em.html", "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__EM_DB_TOTAL__", str(total))
    return HTMLResponse(content=html)


@router.get("/euromillions/news", include_in_schema=False)
async def em_news():
    """EuroMillions — Actualites."""
    return serve_em_page("news-em.html")
