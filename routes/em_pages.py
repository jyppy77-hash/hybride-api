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
        sponsor_js="/ui/static/em/sponsor-popup-em.js?v=7",
        app_js="/ui/static/app-em.js?v=7",
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
        hero_title="Historique des Tirages EuroMillions",
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


# =========================
# Pages légales EM (FR)
# =========================

@router.get("/euromillions/hybride", include_in_schema=False)
async def em_hybride_page(request: Request):
    """EuroMillions — Chatbot HYBRIDE."""
    try:
        total = await db_cloudsql.get_em_tirages_count()
    except Exception:
        total = 0
    return render_template(
        "em/hybride.html", request, lang="fr", page_key="hybride_page",
        body_class="subpage em-page",
        include_nav_scroll=True,
        hero_icon="\U0001f916",
        hero_title="Chatbot HYBRIDE EuroMillions",
        hero_subtitle="L\u2019IA conversationnelle ancr\u00e9e dans les donn\u00e9es r\u00e9elles",
        em_db_total=total,
    )


@router.get("/euromillions/intelligence-artificielle", include_in_schema=False)
async def em_ia(request: Request):
    """EuroMillions — Intelligence Artificielle."""
    try:
        total = await db_cloudsql.get_em_tirages_count()
    except Exception:
        total = 0
    return render_template(
        "em/euromillions-ia.html", request, lang="fr", page_key="ia",
        body_class="subpage em-page",
        include_nav_scroll=True,
        hero_icon="\U0001f916",
        hero_title="EuroMillions et Intelligence Artificielle",
        hero_subtitle="Ce que l\u2019IA peut \u2014 et ne peut pas \u2014 faire pour les loteries",
        em_db_total=total,
    )


@router.get("/euromillions/moteur", include_in_schema=False)
async def em_moteur(request: Request):
    """EuroMillions — Moteur HYBRIDE."""
    return render_template(
        "em/moteur.html", request, lang="fr", page_key="moteur",
        body_class="subpage em-page",
        include_nav_scroll=True,
        hero_icon="⚙️",
        hero_title="Moteur HYBRIDE EuroMillions",
        hero_subtitle="Architecture technique et algorithmes d'analyse",
    )


@router.get("/euromillions/methodologie", include_in_schema=False)
async def em_methodologie(request: Request):
    """EuroMillions — Méthodologie."""
    return render_template(
        "em/methodologie.html", request, lang="fr", page_key="methodologie",
        body_class="subpage em-page",
        include_nav_scroll=True,
        hero_icon="📐",
        hero_title="Méthodologie EuroMillions",
        hero_subtitle="Notre approche scientifique de l'analyse statistique",
    )


@router.get("/euromillions/a-propos", include_in_schema=False)
async def em_a_propos(request: Request):
    """EuroMillions — À propos."""
    return render_template(
        "em/a-propos.html", request, lang="fr", page_key="a_propos",
        body_class="subpage em-page",
        include_nav_scroll=True,
        hero_icon="ℹ️",
        hero_title="À propos de LotoIA EuroMillions",
        hero_subtitle="Notre mission : rendre les statistiques accessibles et compréhensibles",
    )


@router.get("/euromillions/mentions-legales", include_in_schema=False)
async def em_mentions(request: Request):
    """EuroMillions — Mentions légales."""
    return render_template(
        "em/mentions-legales.html", request, lang="fr", page_key="mentions",
        body_class="subpage legal-page em-page",
    )


@router.get("/euromillions/confidentialite", include_in_schema=False)
async def em_confidentialite(request: Request):
    """EuroMillions — Politique de confidentialité."""
    return render_template(
        "em/confidentialite.html", request, lang="fr", page_key="confidentialite",
        body_class="subpage legal-page em-page",
    )


@router.get("/euromillions/cookies", include_in_schema=False)
async def em_cookies(request: Request):
    """EuroMillions — Politique de cookies."""
    return render_template(
        "em/cookies.html", request, lang="fr", page_key="cookies",
        body_class="subpage legal-page em-page",
    )


@router.get("/euromillions/avertissement", include_in_schema=False)
async def em_disclaimer(request: Request):
    """EuroMillions — Avertissements."""
    return render_template(
        "em/disclaimer.html", request, lang="fr", page_key="disclaimer",
        body_class="subpage legal-page em-page",
        show_disclaimer_link=True,
    )
