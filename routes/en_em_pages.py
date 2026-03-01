"""
Routes — English EuroMillions HTML pages.
P2/5 — Same Jinja2 templates as FR, with lang="en".
"""
from fastapi import APIRouter, Request
import db_cloudsql

from config.templates import render_template

router = APIRouter()


# =========================
# Routes EN EuroMillions — Pages HTML
# =========================

@router.get("/en/euromillions", include_in_schema=False)
async def en_em_home(request: Request):
    """EuroMillions EN — Home (hub)."""
    return render_template(
        "em/accueil.html", request, lang="en", page_key="accueil",
        nav_back_url="/",
        body_class="accueil-page em-page",
        show_disclaimer_link=True,
    )


@router.get("/en/euromillions/generator", include_in_schema=False)
async def en_em_generator(request: Request):
    """EuroMillions EN — Grid Explorer (generator)."""
    return render_template(
        "em/generateur.html", request, lang="en", page_key="generateur",
        body_class="loto-page em-page",
        include_nav_scroll=True,
        show_disclaimer_link=True,
        hero_icon="⭐",
        hero_title="EuroMillions Grid Explorer",
        hero_subtitle="Statistical analysis based on official EuroMillions draws",
    )


@router.get("/en/euromillions/simulator", include_in_schema=False)
async def en_em_simulator(request: Request):
    """EuroMillions EN — Grid Analysis (simulator)."""
    return render_template(
        "em/simulateur.html", request, lang="en", page_key="simulateur",
        body_class="simulator-page em-page",
        include_nav_scroll=True,
        hero_icon="⭐",
        hero_title="EuroMillions Grid Analysis",
        hero_subtitle="Build your grid and get a descriptive statistical audit",
    )


@router.get("/en/euromillions/statistics", include_in_schema=False)
async def en_em_statistics(request: Request):
    """EuroMillions EN — Statistics and history."""
    return render_template(
        "em/statistiques.html", request, lang="en", page_key="statistiques",
        include_nav_scroll=True,
        show_disclaimer_link=True,
        hero_icon="📊",
        hero_title="EuroMillions Statistics",
        hero_subtitle="Frequencies, trends and analysis of numbers and stars",
    )


@router.get("/en/euromillions/history", include_in_schema=False)
async def en_em_history(request: Request):
    """EuroMillions EN — Draw history."""
    return render_template(
        "em/historique.html", request, lang="en", page_key="historique",
        hero_icon="📅",
        hero_title="Draw History",
        hero_subtitle="Search for a EuroMillions draw by date",
        footer_style="margin-top: 48px;",
    )


@router.get("/en/euromillions/faq", include_in_schema=False)
async def en_em_faq(request: Request):
    """EuroMillions EN — FAQ with injected DB stats."""
    try:
        total = await db_cloudsql.get_em_tirages_count()
    except Exception:
        total = 0
    return render_template(
        "em/faq.html", request, lang="en", page_key="faq",
        hero_icon="❓",
        hero_title="EuroMillions FAQ",
        hero_subtitle="All the answers about EuroMillions analysis",
        em_db_total=total,
    )


@router.get("/en/euromillions/news", include_in_schema=False)
async def en_em_news(request: Request):
    """EuroMillions EN — News."""
    return render_template(
        "em/news.html", request, lang="en", page_key="news",
        include_nav_scroll=True,
        hero_icon="📰",
        hero_title="EuroMillions News",
        hero_subtitle="Updates, methodologies and engine releases for EuroMillions",
    )


# =========================
# Legal pages EN
# =========================

@router.get("/en/euromillions/legal-notices", include_in_schema=False)
async def en_em_mentions(request: Request):
    """EuroMillions EN — Legal Notices."""
    return render_template(
        "em/mentions-legales.html", request, lang="en", page_key="mentions",
        body_class="subpage legal-page em-page",
    )


@router.get("/en/euromillions/privacy", include_in_schema=False)
async def en_em_privacy(request: Request):
    """EuroMillions EN — Privacy Policy."""
    return render_template(
        "em/confidentialite.html", request, lang="en", page_key="confidentialite",
        body_class="subpage legal-page em-page",
    )


@router.get("/en/euromillions/cookies", include_in_schema=False)
async def en_em_cookies(request: Request):
    """EuroMillions EN — Cookie Policy."""
    return render_template(
        "em/cookies.html", request, lang="en", page_key="cookies",
        body_class="subpage legal-page em-page",
    )


@router.get("/en/euromillions/disclaimer", include_in_schema=False)
async def en_em_disclaimer(request: Request):
    """EuroMillions EN — Disclaimer."""
    return render_template(
        "em/disclaimer.html", request, lang="en", page_key="disclaimer",
        body_class="subpage legal-page em-page",
        show_disclaimer_link=True,
    )
