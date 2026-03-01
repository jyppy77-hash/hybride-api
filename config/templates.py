"""
Jinja2 template engine for LotoIA EuroMillions pages.
Thread-safe i18n via ContextVar — NO per-request install_gettext_translations.
Uses install_gettext_callables so _() reads ctx_lang at render time.
"""
import os

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
from fastapi.responses import HTMLResponse
from starlette.requests import Request

from config.i18n import ctx_lang, get_translations, SUPPORTED_LANGS, DEFAULT_LANG
from config.js_i18n import get_js_labels
from config import killswitch

# ── Paths ────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(_ROOT, "ui", "templates")
BASE_URL = "https://lotoia.fr"

# ── Thread-safe gettext callables (read ctx_lang at render time) ─────────

def _gettext(message: str) -> str:
    lang = ctx_lang.get()
    return get_translations(lang).gettext(message)


def _ngettext(singular: str, plural: str, n: int) -> str:
    lang = ctx_lang.get()
    return get_translations(lang).ngettext(singular, plural, n)


# ── Jinja2 Environment ──────────────────────────────────────────────────

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=True,
    extensions=["jinja2.ext.i18n"],
)
env.install_gettext_callables(_gettext, _ngettext, newstyle=False)

# ── URL maps per language ────────────────────────────────────────────────

EM_URLS = {
    "fr": {
        "home":         "/euromillions",
        "accueil":      "/euromillions",
        "simulateur":   "/euromillions/simulateur",
        "generateur":   "/euromillions/generateur",
        "statistiques": "/euromillions/statistiques",
        "historique":   "/euromillions/historique",
        "news":         "/euromillions/news",
        "faq":          "/euromillions/faq",
        "mentions":         "/euromillions/mentions-legales",
        "confidentialite":  "/euromillions/confidentialite",
        "cookies":          "/euromillions/cookies",
        "disclaimer":       "/euromillions/avertissement",
    },
    "en": {
        "home":         "/en/euromillions",
        "accueil":      "/en/euromillions",
        "simulateur":   "/en/euromillions/simulator",
        "generateur":   "/en/euromillions/generator",
        "statistiques": "/en/euromillions/statistics",
        "historique":   "/en/euromillions/history",
        "news":         "/en/euromillions/news",
        "faq":          "/en/euromillions/faq",
        "mentions":         "/en/euromillions/legal-notices",
        "confidentialite":  "/en/euromillions/privacy",
        "cookies":          "/en/euromillions/cookies",
        "disclaimer":       "/en/euromillions/disclaimer",
    },
    "pt": {
        "home":         "/pt/euromillions",
        "accueil":      "/pt/euromillions",
        "simulateur":   "/pt/euromillions/simulador",
        "generateur":   "/pt/euromillions/gerador",
        "statistiques": "/pt/euromillions/estatisticas",
        "historique":   "/pt/euromillions/historico",
        "news":         "/pt/euromillions/noticias",
        "faq":          "/pt/euromillions/faq",
        "mentions":         "/pt/euromillions/avisos-legais",
        "confidentialite":  "/pt/euromillions/privacidade",
        "cookies":          "/pt/euromillions/cookies",
        "disclaimer":       "/pt/euromillions/aviso",
    },
    "es": {
        "home":         "/es/euromillions",
        "accueil":      "/es/euromillions",
        "simulateur":   "/es/euromillions/simulador",
        "generateur":   "/es/euromillions/generador",
        "statistiques": "/es/euromillions/estadisticas",
        "historique":   "/es/euromillions/historial",
        "news":         "/es/euromillions/noticias",
        "faq":          "/es/euromillions/faq",
        "mentions":         "/es/euromillions/aviso-legal",
        "confidentialite":  "/es/euromillions/privacidad",
        "cookies":          "/es/euromillions/cookies",
        "disclaimer":       "/es/euromillions/aviso",
    },
    "de": {
        "home":         "/de/euromillions",
        "accueil":      "/de/euromillions",
        "simulateur":   "/de/euromillions/simulator",
        "generateur":   "/de/euromillions/generator",
        "statistiques": "/de/euromillions/statistiken",
        "historique":   "/de/euromillions/ziehungen",
        "news":         "/de/euromillions/nachrichten",
        "faq":          "/de/euromillions/faq",
        "mentions":         "/de/euromillions/impressum",
        "confidentialite":  "/de/euromillions/datenschutz",
        "cookies":          "/de/euromillions/cookies",
        "disclaimer":       "/de/euromillions/haftungsausschluss",
    },
    "nl": {
        "home":         "/nl/euromillions",
        "accueil":      "/nl/euromillions",
        "simulateur":   "/nl/euromillions/simulator",
        "generateur":   "/nl/euromillions/generator",
        "statistiques": "/nl/euromillions/statistieken",
        "historique":   "/nl/euromillions/geschiedenis",
        "news":         "/nl/euromillions/nieuws",
        "faq":          "/nl/euromillions/faq",
        "mentions":         "/nl/euromillions/juridische-kennisgeving",
        "confidentialite":  "/nl/euromillions/privacy",
        "cookies":          "/nl/euromillions/cookies",
        "disclaimer":       "/nl/euromillions/disclaimer",
    },
}

# Reverse mapping for lang switch: page_key → other-lang URL
# FR → EN toggle; all other langs → FR
_LANG_SWITCH = {"fr": {k: EM_URLS["en"][k] for k in EM_URLS["en"]}}
for _lc in EM_URLS:
    if _lc != "fr":
        _LANG_SWITCH[_lc] = {k: EM_URLS["fr"][k] for k in EM_URLS["fr"]}

# Lang switch labels, titles & flags
_LANG_SWITCH_META = {
    "fr": {"label": "FR", "title": "Version française", "flag": "\U0001f1eb\U0001f1f7"},
    "en": {"label": "EN", "title": "English version", "flag": "\U0001f1ec\U0001f1e7"},
    "es": {"label": "ES", "title": "Versión en español", "flag": "\U0001f1ea\U0001f1f8"},
    "pt": {"label": "PT", "title": "Versão em português", "flag": "\U0001f1f5\U0001f1f9"},
    "de": {"label": "DE", "title": "Deutsche Version", "flag": "\U0001f1e9\U0001f1ea"},
    "nl": {"label": "NL", "title": "Nederlandse versie", "flag": "\U0001f1f3\U0001f1f1"},
}


def _build_lang_switches(current_lang: str, page_key: str) -> list[dict]:
    """Build list of lang switch buttons for all enabled langs except current."""
    from config import killswitch
    switches = []
    for lc in killswitch.ENABLED_LANGS:
        if lc == current_lang:
            continue
        url = EM_URLS.get(lc, {}).get(page_key, "/")
        meta = _LANG_SWITCH_META.get(lc, {"label": lc.upper(), "title": lc})
        switches.append({
            "url": url,
            "label": meta["label"],
            "title": meta["title"],
        })
    return switches


def _build_all_lang_switches(current_lang: str, page_key: str) -> list[dict]:
    """Build list of ALL enabled langs with flags, marking current."""
    from config import killswitch
    switches = []
    for lc in killswitch.ENABLED_LANGS:
        url = EM_URLS.get(lc, {}).get(page_key, "/")
        meta = _LANG_SWITCH_META.get(lc, {"label": lc.upper(), "title": lc, "flag": ""})
        switches.append({
            "url": url,
            "label": meta["label"],
            "title": meta["title"],
            "flag": meta.get("flag", ""),
            "current": lc == current_lang,
        })
    return switches

# ── Hreflang helpers ─────────────────────────────────────────────────────

def hreflang_tags(page_key: str) -> list[dict]:
    """Return hreflang link data [{lang, url}, ...] for a page.
    Only includes languages present in killswitch.ENABLED_LANGS."""
    tags = []
    for lc in killswitch.ENABLED_LANGS:
        url = EM_URLS.get(lc, {}).get(page_key)
        if url:
            tags.append({"lang": lc, "url": f"{BASE_URL}{url}"})
    # x-default → FR
    fr_url = EM_URLS["fr"].get(page_key)
    if fr_url:
        tags.append({"lang": "x-default", "url": f"{BASE_URL}{fr_url}"})
    return tags


# ── Gambling help per language ───────────────────────────────────────────

_GAMBLING_HELP = {
    "fr": {
        "url":  "https://www.joueurs-info-service.fr",
        "name": "Joueurs Info Service",
    },
    "en": {
        "url":  "https://www.begambleaware.org",
        "name": "BeGambleAware",
    },
    "pt": {
        "url":  "https://www.jogoresponsavel.pt",
        "name": "Jogo Responsavel",
    },
    "es": {
        "url":  "https://www.jugarbien.es",
        "name": "Jugar Bien",
    },
    "de": {
        "url":  "https://www.spielen-mit-verantwortung.de",
        "name": "Spielen mit Verantwortung",
    },
    "nl": {
        "url":  "https://www.agog.nl",
        "name": "AGOG",
    },
}

# ── OG locale per language ───────────────────────────────────────────────

_OG_LOCALE = {
    "fr": "fr_FR", "en": "en_GB", "pt": "pt_PT",
    "es": "es_ES", "de": "de_DE", "nl": "nl_NL",
}

# ── Date locale per language (JS Intl) ───────────────────────────────────

_DATE_LOCALE = {
    "fr": "fr-FR", "en": "en-GB", "pt": "pt-PT",
    "es": "es-ES", "de": "de-DE", "nl": "nl-NL",
}

# ── render_template ──────────────────────────────────────────────────────

def render_template(
    template_name: str,
    request: Request,
    lang: str = "fr",
    page_key: str = "home",
    **extra,
) -> HTMLResponse:
    """
    Render a Jinja2 template with full i18n context.

    Args:
        template_name: path relative to ui/templates/ (e.g. "em/historique.html")
        request: Starlette Request object
        lang: "fr" or "en"
        page_key: identifier for hreflang + active-nav ("accueil","generateur",...)
        **extra: additional template variables
    """
    token = ctx_lang.set(lang)
    try:
        is_fr = (lang == "fr")
        urls = EM_URLS.get(lang, EM_URLS["fr"])
        help_info = _GAMBLING_HELP.get(lang, _GAMBLING_HELP["fr"])

        ctx = {
            # Core
            "lang": lang,
            "request": request,
            "page_key": page_key,
            "active_page": page_key,

            # URLs
            "urls": urls,
            "em_base": urls["home"],
            "base_url": BASE_URL,
            "canonical_url": f"{BASE_URL}{urls.get(page_key, '/')}",
            "hreflang_tags": hreflang_tags(page_key),

            # Lang switches (one button per other enabled language)
            "lang_switches": _build_lang_switches(lang, page_key),

            # Mobile lang selector (all langs with flags, current marked)
            "all_lang_switches": _build_all_lang_switches(lang, page_key),
            "lang_flag": _LANG_SWITCH_META.get(lang, {}).get("flag", ""),

            # OG & locale
            "og_locale": _OG_LOCALE.get(lang, "fr_FR"),
            "date_locale": _DATE_LOCALE.get(lang, "fr-FR"),

            # JS paths (FR vs EN variants)
            "chatbot_js": (
                "/ui/en/euromillions/static/hybride-chatbot-em-en.js?v=1.0"
                if lang == "en" else
                "/ui/static/hybride-chatbot-em.js?v=1.1"
            ),
            "rating_js": "/ui/static/rating-popup.js?v=7",

            # Gambling help
            "gambling_help_url": help_info["url"],
            "gambling_help_name": help_info["name"],

            # Nav scroll (off by default, pages override)
            "include_nav_scroll": False,

            # JS i18n labels (window.LotoIA_i18n)
            "js_labels": get_js_labels(lang),

            # Default JS paths (pages may override via **extra)
            "app_js": "/ui/static/app-em.js?v=7",
            "simulateur_js": "/ui/static/simulateur-em.js?v=7",
            "sponsor_js": "/ui/static/em/sponsor-popup-em.js?v=7",
            "sponsor75_js": "/ui/static/sponsor-popup75-em.js?v=7",
            "faq_js": "/ui/static/faq-em.js?v=7",

            # Page overrides
            **extra,
        }

        template = env.get_template(template_name)
        html = template.render(**ctx)
        return HTMLResponse(content=html)
    finally:
        ctx_lang.reset(token)
