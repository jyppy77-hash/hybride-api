"""
Routes — English EuroMillions HTML pages.
P2/5 — Same Jinja2 templates as FR, with lang="en".
"""
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import db_cloudsql

from config import killswitch
from config.templates import render_template

_KS_HEADERS = {"Cache-Control": "no-cache, no-store"}

router = APIRouter()


# =========================
# Routes EN EuroMillions — Pages HTML
# =========================

@router.get("/en/euromillions", include_in_schema=False)
async def en_em_home(request: Request):
    """EuroMillions EN — Home (hub) + AggregateRating dynamique."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
    em_rating_value, em_rating_count = 0, 0
    try:
        result = await db_cloudsql.async_fetchone(
            "SELECT review_count, avg_rating FROM ratings_aggregate WHERE source = %s",
            ("popup_em",),
        )
        if result and result.get("review_count"):
            em_rating_count = int(result["review_count"])
            em_rating_value = round(float(result["avg_rating"]), 1)
    except Exception:
        pass

    return render_template(
        "em/accueil.html", request, lang="en", page_key="accueil",
        nav_back_url="/",
        body_class="accueil-page em-page",
        show_disclaimer_link=True,
        em_rating_value=em_rating_value,
        em_rating_count=em_rating_count,
    )


@router.get("/en/euromillions/generator", include_in_schema=False)
async def en_em_generator(request: Request):
    """EuroMillions EN — Grid Explorer (generator)."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
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
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
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
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
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
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
    return render_template(
        "em/historique.html", request, lang="en", page_key="historique",
        hero_icon="📅",
        hero_title="EuroMillions Draw History",
        hero_subtitle="Search for a EuroMillions draw by date",
        footer_style="margin-top: 48px;",
    )


@router.get("/en/euromillions/faq", include_in_schema=False)
async def en_em_faq(request: Request):
    """EuroMillions EN — FAQ with injected DB stats."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
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
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
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

@router.get("/en/euromillions/hybride", include_in_schema=False)
async def en_em_hybride_page(request: Request):
    """EuroMillions EN — HYBRIDE Chatbot."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
    try:
        total = await db_cloudsql.get_em_tirages_count()
    except Exception:
        total = 0
    return render_template(
        "em/hybride.html", request, lang="en", page_key="hybride_page",
        body_class="subpage em-page",
        include_nav_scroll=True,
        hero_icon="\U0001f916",
        hero_title="HYBRIDE Chatbot EuroMillions",
        hero_subtitle="Conversational AI grounded in real data",
        em_db_total=total,
    )


@router.get("/en/euromillions/artificial-intelligence", include_in_schema=False)
async def en_em_ai(request: Request):
    """EuroMillions EN — Artificial Intelligence."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
    try:
        total = await db_cloudsql.get_em_tirages_count()
    except Exception:
        total = 0
    return render_template(
        "em/euromillions-ia.html", request, lang="en", page_key="ia",
        body_class="subpage em-page",
        include_nav_scroll=True,
        hero_icon="\U0001f916",
        hero_title="EuroMillions and Artificial Intelligence",
        hero_subtitle="What AI can \u2014 and cannot \u2014 do for lotteries",
        em_db_total=total,
    )


@router.get("/en/euromillions/engine", include_in_schema=False)
async def en_em_engine(request: Request):
    """EuroMillions EN — HYBRIDE Engine."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
    return render_template(
        "em/moteur.html", request, lang="en", page_key="moteur",
        body_class="subpage em-page",
        include_nav_scroll=True,
        hero_icon="⚙️",
        hero_title="HYBRIDE Engine EuroMillions",
        hero_subtitle="Technical architecture and analysis algorithms",
    )


@router.get("/en/euromillions/methodology", include_in_schema=False)
async def en_em_methodology(request: Request):
    """EuroMillions EN — Methodology."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
    return render_template(
        "em/methodologie.html", request, lang="en", page_key="methodologie",
        body_class="subpage em-page",
        include_nav_scroll=True,
        hero_icon="📐",
        hero_title="EuroMillions Methodology",
        hero_subtitle="Our scientific approach to statistical analysis",
    )


@router.get("/en/euromillions/about", include_in_schema=False)
async def en_em_about(request: Request):
    """EuroMillions EN — About."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
    return render_template(
        "em/a-propos.html", request, lang="en", page_key="a_propos",
        body_class="subpage em-page",
        include_nav_scroll=True,
        hero_icon="ℹ️",
        hero_title="About LotoIA EuroMillions",
        hero_subtitle="Our mission: making statistics accessible and understandable",
    )


@router.get("/en/euromillions/legal-notices", include_in_schema=False)
async def en_em_mentions(request: Request):
    """EuroMillions EN — Legal Notices."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
    return render_template(
        "em/mentions-legales.html", request, lang="en", page_key="mentions",
        body_class="subpage legal-page em-page",
    )


@router.get("/en/euromillions/privacy", include_in_schema=False)
async def en_em_privacy(request: Request):
    """EuroMillions EN — Privacy Policy."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
    return render_template(
        "em/confidentialite.html", request, lang="en", page_key="confidentialite",
        body_class="subpage legal-page em-page",
    )


@router.get("/en/euromillions/cookies", include_in_schema=False)
async def en_em_cookies(request: Request):
    """EuroMillions EN — Cookie Policy."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
    return render_template(
        "em/cookies.html", request, lang="en", page_key="cookies",
        body_class="subpage legal-page em-page",
    )


@router.get("/en/euromillions/pairs", include_in_schema=False)
async def en_em_pairs(request: Request):
    """EuroMillions EN — Number Pairs (co-occurrences)."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
    return render_template(
        "em/paires.html", request, lang="en", page_key="paires",
        body_class="subpage em-page",
        include_nav_scroll=True,
        hero_icon="\U0001f517",
        hero_title="EuroMillions Pairs — Co-occurrences",
        hero_subtitle="Hot/cold rankings and interactive pair search for balls and stars",
    )


@router.get("/en/euromillions/disclaimer", include_in_schema=False)
async def en_em_disclaimer(request: Request):
    """EuroMillions EN — Disclaimer."""
    if "en" not in killswitch.ENABLED_LANGS:
        return RedirectResponse(url="/accueil", status_code=302, headers=_KS_HEADERS)
    return render_template(
        "em/disclaimer.html", request, lang="en", page_key="disclaimer",
        body_class="subpage legal-page em-page",
        show_disclaimer_link=True,
    )
