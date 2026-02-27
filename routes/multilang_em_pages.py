"""
Routes — Multilingual EuroMillions HTML pages (PT/ES/DE/NL).
Factory-based route generation: same Jinja2 templates as FR/EN,
with kill switch check (redirect to FR if language disabled).
"""
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import db_cloudsql

from config.templates import render_template, EM_URLS
from config import killswitch

router = APIRouter()

# ── Hero texts per language ──────────────────────────────────────────────

_HERO_TEXTS = {
    "pt": {
        "generateur": ("Explorador de Grelhas EuroMillions",
                       "Analise estatistica baseada nos sorteios oficiais EuroMillions"),
        "simulateur": ("Analise de Grelha EuroMillions",
                       "Componha a sua grelha e obtenha uma auditoria estatistica descritiva"),
        "statistiques": ("Estatisticas EuroMillions",
                         "Frequencias, tendencias e analise dos numeros e estrelas"),
        "historique": ("Historico de Sorteios",
                       "Pesquise um sorteio EuroMillions por data"),
        "faq": ("FAQ EuroMillions",
                "Todas as respostas sobre a analise EuroMillions"),
        "news": ("Noticias EuroMillions",
                 "Atualizacoes, metodologias e lancamentos do motor EuroMillions"),
    },
    "es": {
        "generateur": ("Explorador de Cuadriculas EuroMillions",
                       "Analisis estadistico basado en los sorteos oficiales EuroMillions"),
        "simulateur": ("Analisis de Cuadricula EuroMillions",
                       "Componga su cuadricula y obtenga una auditoria estadistica descriptiva"),
        "statistiques": ("Estadisticas EuroMillions",
                         "Frecuencias, tendencias y analisis de numeros y estrellas"),
        "historique": ("Historial de Sorteos",
                       "Busque un sorteo EuroMillions por fecha"),
        "faq": ("FAQ EuroMillions",
                "Todas las respuestas sobre el analisis EuroMillions"),
        "news": ("Noticias EuroMillions",
                 "Actualizaciones, metodologias y lanzamientos del motor EuroMillions"),
    },
    "de": {
        "generateur": ("EuroMillions Raster-Explorer",
                       "Statistische Analyse basierend auf offiziellen EuroMillions-Ziehungen"),
        "simulateur": ("EuroMillions Raster-Analyse",
                       "Erstellen Sie Ihr Raster und erhalten Sie ein statistisches Audit"),
        "statistiques": ("EuroMillions Statistiken",
                         "Haufigkeiten, Trends und Analyse der Zahlen und Sterne"),
        "historique": ("Ziehungsverlauf",
                       "Suchen Sie eine EuroMillions-Ziehung nach Datum"),
        "faq": ("EuroMillions FAQ",
                "Alle Antworten zur EuroMillions-Analyse"),
        "news": ("EuroMillions Nachrichten",
                 "Updates, Methoden und Motor-Releases fur EuroMillions"),
    },
    "nl": {
        "generateur": ("EuroMillions Rooster Verkenner",
                       "Statistische analyse op basis van officiele EuroMillions-trekkingen"),
        "simulateur": ("EuroMillions Rooster Analyse",
                       "Stel uw rooster samen en ontvang een statistisch audit"),
        "statistiques": ("EuroMillions Statistieken",
                         "Frequenties, trends en analyse van nummers en sterren"),
        "historique": ("Trekkingsgeschiedenis",
                       "Zoek een EuroMillions-trekking op datum"),
        "faq": ("EuroMillions FAQ",
                "Alle antwoorden over de EuroMillions-analyse"),
        "news": ("EuroMillions Nieuws",
                 "Updates, methodologieen en motor-releases voor EuroMillions"),
    },
}

# ── Page definitions ─────────────────────────────────────────────────────
# (page_key, template, base_extra)

_PAGE_DEFS = [
    ("accueil", "em/accueil.html", {
        "nav_back_url": "/",
        "body_class": "accueil-page em-page",
        "show_disclaimer_link": True,
    }),
    ("generateur", "em/generateur.html", {
        "body_class": "loto-page em-page",
        "include_nav_scroll": True,
        "show_disclaimer_link": True,
        "hero_icon": "\u2b50",
    }),
    ("simulateur", "em/simulateur.html", {
        "body_class": "simulator-page em-page",
        "include_nav_scroll": True,
        "hero_icon": "\u2b50",
    }),
    ("statistiques", "em/statistiques.html", {
        "include_nav_scroll": True,
        "show_disclaimer_link": True,
        "hero_icon": "\U0001f4ca",
    }),
    ("historique", "em/historique.html", {
        "hero_icon": "\U0001f4c5",
        "footer_style": "margin-top: 48px;",
    }),
    ("faq", "em/faq.html", {
        "hero_icon": "\u2753",
    }),
    ("news", "em/news.html", {
        "include_nav_scroll": True,
        "hero_icon": "\U0001f4f0",
    }),
]


# ── Route factory ────────────────────────────────────────────────────────

def _make_handler(lang_code, page_key, template, extra):
    """Create a standard page handler with kill switch check."""
    async def handler(request: Request):
        if lang_code not in killswitch.ENABLED_LANGS:
            return RedirectResponse(url=EM_URLS["fr"][page_key], status_code=302)
        return render_template(template, request, lang=lang_code, page_key=page_key, **extra)
    handler.__name__ = f"{lang_code}_em_{page_key}"
    handler.__doc__ = f"EuroMillions {lang_code.upper()} — {page_key}"
    return handler


def _make_faq_handler(lang_code, template, extra):
    """Create FAQ handler with DB call + kill switch check."""
    async def handler(request: Request):
        if lang_code not in killswitch.ENABLED_LANGS:
            return RedirectResponse(url=EM_URLS["fr"]["faq"], status_code=302)
        try:
            total = await db_cloudsql.get_em_tirages_count()
        except Exception:
            total = 0
        return render_template(
            template, request, lang=lang_code, page_key="faq",
            em_db_total=total, **extra,
        )
    handler.__name__ = f"{lang_code}_em_faq"
    handler.__doc__ = f"EuroMillions {lang_code.upper()} — FAQ"
    return handler


def _register_routes():
    """Register routes for PT/ES/DE/NL with closure binding."""
    for lang_code in ("pt", "es", "de", "nl"):
        urls = EM_URLS.get(lang_code)
        if not urls:
            continue

        hero_texts = _HERO_TEXTS.get(lang_code, {})

        for page_key, template, base_extra in _PAGE_DEFS:
            path = urls[page_key]
            extra = {**base_extra}

            # Inject hero texts if available
            hero = hero_texts.get(page_key)
            if hero:
                extra["hero_title"] = hero[0]
                extra["hero_subtitle"] = hero[1]

            if page_key == "faq":
                handler = _make_faq_handler(lang_code, template, extra)
            else:
                handler = _make_handler(lang_code, page_key, template, extra)

            router.add_api_route(
                path, handler, methods=["GET"], include_in_schema=False,
            )


_register_routes()
