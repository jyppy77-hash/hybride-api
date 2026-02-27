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
    },
}

# Reverse mapping for lang switch: page_key → other-lang URL
_LANG_SWITCH = {
    "fr": {k: EM_URLS["en"][k] for k in EM_URLS["en"]},
    "en": {k: EM_URLS["fr"][k] for k in EM_URLS["fr"]},
}

# ── Hreflang helpers ─────────────────────────────────────────────────────

def hreflang_tags(page_key: str) -> list[dict]:
    """Return hreflang link data [{lang, url}, ...] for a page."""
    tags = []
    for lc in ("fr", "en"):
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
}

# ── OG locale per language ───────────────────────────────────────────────

_OG_LOCALE = {"fr": "fr_FR", "en": "en_GB"}

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

            # Lang switch
            "lang_switch_url": _LANG_SWITCH.get(lang, {}).get(page_key, "/"),
            "lang_switch_label": "EN" if is_fr else "FR",
            "lang_switch_title": "English version" if is_fr else "Version française",

            # OG & locale
            "og_locale": _OG_LOCALE.get(lang, "fr_FR"),
            "date_locale": "en-GB" if not is_fr else "fr-FR",

            # JS paths (FR vs EN variants)
            "chatbot_js": (
                "/ui/static/hybride-chatbot-em.js?v=1.0"
                if is_fr else
                "/ui/en/euromillions/static/hybride-chatbot-em-en.js?v=1.0"
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
