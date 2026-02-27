"""
Routes — EuroMillions HTML pages (FR).
P2/5 — Jinja2 templates with gettext i18n.
"""
from fastapi import APIRouter, Request
import db_cloudsql

from config.templates import render_template

router = APIRouter()


# =========================
# Routes EuroMillions — Pages HTML (FR)
# =========================

@router.get("/euromillions", include_in_schema=False)
async def em_accueil(request: Request):
    """EuroMillions — Accueil (hub)."""
    return render_template(
        "em/accueil.html", request, lang="fr", page_key="accueil",
        nav_back_url="/",
        body_class="accueil-page em-page",
        show_disclaimer_link=True,
    )


@router.get("/euromillions/generateur", include_in_schema=False)
async def em_generateur(request: Request):
    """EuroMillions — Exploration de grilles (generateur)."""
    return render_template(
        "em/generateur.html", request, lang="fr", page_key="generateur",
        body_class="loto-page em-page",
        include_nav_scroll=True,
        show_disclaimer_link=True,
        hero_icon="⭐",
        hero_title="Exploration de grilles EuroMillions",
        hero_subtitle="Analyse statistique basée sur les tirages officiels EuroMillions",
        sponsor75_js="/ui/static/sponsor-popup75-em.js?v=8",
        sponsor_js="/ui/static/sponsor-popup-em.js?v=4",
        app_js="/ui/static/app-em.js?v=1",
    )


@router.get("/euromillions/simulateur", include_in_schema=False)
async def em_simulateur(request: Request):
    """EuroMillions — Analyse de grille (simulateur)."""
    return render_template(
        "em/simulateur.html", request, lang="fr", page_key="simulateur",
        body_class="simulator-page em-page",
        include_nav_scroll=True,
        hero_icon="⭐",
        hero_title="Analyse de grille EuroMillions",
        hero_subtitle="Composez votre grille et obtenez un audit statistique descriptif",
        simulateur_js="/ui/static/simulateur-em.js?v=1",
        sponsor_js="/ui/static/em/sponsor-popup-em.js?v=3",
    )


@router.get("/euromillions/statistiques", include_in_schema=False)
async def em_statistiques(request: Request):
    """EuroMillions — Statistiques et historique."""
    return render_template(
        "em/statistiques.html", request, lang="fr", page_key="statistiques",
        include_nav_scroll=True,
        show_disclaimer_link=True,
        hero_icon="📊",
        hero_title="Statistiques EuroMillions",
        hero_subtitle="Fréquences, tendances et analyse des numéros et étoiles",
    )


@router.get("/euromillions/historique", include_in_schema=False)
async def em_historique(request: Request):
    """EuroMillions — Historique des tirages."""
    return render_template(
        "em/historique.html", request, lang="fr", page_key="historique",
        hero_icon="📅",
        hero_title="Historique des tirages",
        hero_subtitle="Recherchez un tirage EuroMillions par date",
        footer_style="margin-top: 48px;",
    )


@router.get("/euromillions/faq", include_in_schema=False)
async def em_faq(request: Request):
    """EuroMillions — FAQ avec stats BDD injectees."""
    try:
        total = await db_cloudsql.get_em_tirages_count()
    except Exception:
        total = 0
    return render_template(
        "em/faq.html", request, lang="fr", page_key="faq",
        hero_icon="❓",
        hero_title="FAQ EuroMillions",
        hero_subtitle="Toutes les réponses sur l'analyse EuroMillions",
        em_db_total=total,
        faq_js="/ui/static/faq-em.js?v=1",
    )


@router.get("/euromillions/news", include_in_schema=False)
async def em_news(request: Request):
    """EuroMillions — Actualites."""
    return render_template(
        "em/news.html", request, lang="fr", page_key="news",
        include_nav_scroll=True,
        hero_icon="📰",
        hero_title="Actualités EuroMillions",
        hero_subtitle="Évolutions, méthodologies et mises à jour du moteur EuroMillions",
    )
