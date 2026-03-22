"""
Routes — Launcher multilingue (V53).
GET / → 302 redirect vers /{lang} selon CF-IPCountry.
GET /{lang} → launcher dans la langue fixe.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from markupsafe import Markup

from config import killswitch
from config.i18n import ctx_lang
from config.templates import env, BASE_URL, _OG_LOCALE, EM_URLS

router = APIRouter()

# ── Country → Language mapping (ISO 3166-1 alpha-2) ────────────────────

COUNTRY_TO_LANG = {
    # Francophone
    "FR": "fr", "MC": "fr", "LU": "fr", "BE": "fr", "CH": "fr",
    # Hispanophone
    "ES": "es", "AR": "es", "CL": "es", "CO": "es", "MX": "es",
    "PE": "es", "VE": "es", "EC": "es", "UY": "es", "PY": "es",
    "BO": "es", "CR": "es", "PA": "es", "DO": "es", "GT": "es",
    "HN": "es", "SV": "es", "NI": "es", "CU": "es",
    # Lusophone
    "PT": "pt", "BR": "pt", "AO": "pt", "MZ": "pt",
    # Germanophone
    "DE": "de", "AT": "de",
    # Néerlandophone
    "NL": "nl",
    # Anglophone (fallback)
    "GB": "en", "IE": "en", "US": "en", "CA": "en",
    "AU": "en", "NZ": "en", "ZA": "en",
}
DEFAULT_LANG = "en"

# ── EM home URL per language ────────────────────────────────────────────

_EM_HOME = {
    "fr": "/euromillions",
    "en": "/en/euromillions",
    "es": "/es/euromillions",
    "pt": "/pt/euromillions",
    "de": "/de/euromillions",
    "nl": "/nl/euromillions",
}

# ── Flag SVGs (language selector — 6 flags) ────────────────────────────

_FLAG_SVGS = {
    "fr": Markup(
        '<svg viewBox="0 0 24 16"><rect width="8" height="16" fill="#002395"/>'
        '<rect x="8" width="8" height="16" fill="#fff"/>'
        '<rect x="16" width="8" height="16" fill="#ED2939"/></svg>'
    ),
    "en": Markup(
        '<svg viewBox="0 0 24 16"><rect width="24" height="16" fill="#012169"/>'
        '<path d="M0 0L24 16M24 0L0 16" stroke="#fff" stroke-width="2.8"/>'
        '<path d="M0 0L24 16M24 0L0 16" stroke="#C8102E" stroke-width="1.6"/>'
        '<path d="M12 0v16M0 8h24" stroke="#fff" stroke-width="4.8"/>'
        '<path d="M12 0v16M0 8h24" stroke="#C8102E" stroke-width="2.8"/></svg>'
    ),
    "es": Markup(
        '<svg viewBox="0 0 24 16"><rect width="24" height="4" fill="#AA151B"/>'
        '<rect y="4" width="24" height="8" fill="#F1BF00"/>'
        '<rect y="12" width="24" height="4" fill="#AA151B"/></svg>'
    ),
    "pt": Markup(
        '<svg viewBox="0 0 24 16"><rect width="9" height="16" fill="#006600"/>'
        '<rect x="9" width="15" height="16" fill="#FF0000"/>'
        '<circle cx="9" cy="8" r="3.2" fill="#FF0000" stroke="#F1BF00" stroke-width="0.8"/></svg>'
    ),
    "de": Markup(
        '<svg viewBox="0 0 24 16"><rect width="24" height="5.33" fill="#000"/>'
        '<rect y="5.33" width="24" height="5.34" fill="#DD0000"/>'
        '<rect y="10.67" width="24" height="5.33" fill="#FFCC00"/></svg>'
    ),
    "nl": Markup(
        '<svg viewBox="0 0 24 16"><rect width="24" height="5.33" fill="#AE1C28"/>'
        '<rect y="5.33" width="24" height="5.34" fill="#fff"/>'
        '<rect y="10.67" width="24" height="5.33" fill="#21468B"/></svg>'
    ),
}

# ── EM country flag SVGs (9 countries for EM card) ─────────────────────

_EM_COUNTRY_FLAGS = [
    # FR
    _FLAG_SVGS["fr"],
    # GB
    _FLAG_SVGS["en"],
    # ES
    _FLAG_SVGS["es"],
    # PT
    _FLAG_SVGS["pt"],
    # DE
    _FLAG_SVGS["de"],
    # BE
    Markup(
        '<svg viewBox="0 0 24 16"><rect width="8" height="16" fill="#000"/>'
        '<rect x="8" width="8" height="16" fill="#FAE042"/>'
        '<rect x="16" width="8" height="16" fill="#ED2939"/></svg>'
    ),
    # NL
    _FLAG_SVGS["nl"],
    # AT
    Markup(
        '<svg viewBox="0 0 24 16"><rect width="24" height="5.33" fill="#ED2939"/>'
        '<rect y="5.33" width="24" height="5.34" fill="#fff"/>'
        '<rect y="10.67" width="24" height="5.33" fill="#ED2939"/></svg>'
    ),
    # LU
    Markup(
        '<svg viewBox="0 0 24 16"><rect width="24" height="5.33" fill="#ED2939"/>'
        '<rect y="5.33" width="24" height="5.34" fill="#fff"/>'
        '<rect y="10.67" width="24" height="5.33" fill="#00A1DE"/></svg>'
    ),
]


# ── Render helper ───────────────────────────────────────────────────────

def _render_launcher(lang: str, request: Request) -> HTMLResponse:
    """Render the launcher template in the given language."""
    token = ctx_lang.set(lang)
    try:
        is_french = (lang == "fr")

        # Build flag data for language selector
        flags = []
        for fl in killswitch.ENABLED_LANGS:
            if fl in _FLAG_SVGS:
                flags.append({
                    "lang": fl,
                    "svg": _FLAG_SVGS[fl],
                    "active": fl == lang,
                    "url": f"/{fl}",
                })

        # Legal page URLs (FR = Loto site-wide, others = EM localized)
        if is_french:
            legal_urls = {
                "mentions": "/mentions-legales",
                "confidentialite": "/politique-confidentialite",
                "cookies": "/politique-cookies",
            }
        else:
            lang_urls = EM_URLS.get(lang, EM_URLS["en"])
            legal_urls = {
                "mentions": lang_urls["mentions"],
                "confidentialite": lang_urls["confidentialite"],
                "cookies": lang_urls["cookies"],
            }

        # hreflang alternates (same on every launcher page)
        hreflang_tags = [
            {"lang": lc, "url": f"{BASE_URL}/{lc}"}
            for lc in killswitch.ENABLED_LANGS
        ]
        hreflang_tags.append({"lang": "x-default", "url": f"{BASE_URL}/{DEFAULT_LANG}"})

        ctx = {
            "lang": lang,
            "request": request,
            "is_french": is_french,
            "flags": flags,
            "loto_url": "/accueil",
            "loto_flag": _FLAG_SVGS["fr"],
            "em_url": _EM_HOME.get(lang, _EM_HOME["en"]),
            "em_country_flags": _EM_COUNTRY_FLAGS,
            "base_url": BASE_URL,
            "canonical_url": f"{BASE_URL}/{lang}",
            "og_locale": _OG_LOCALE.get(lang, "en_GB"),
            "hreflang_tags": hreflang_tags,
            "legal_urls": legal_urls,
        }

        template = env.get_template("launcher.html")
        html = template.render(**ctx)
        return HTMLResponse(content=html, headers={"Content-Language": lang})
    finally:
        ctx_lang.reset(token)


# ── GET / → 302 redirect ───────────────────────────────────────────────

@router.get("/", include_in_schema=False)
async def launcher_redirect(request: Request):
    """302 redirect to /{lang} based on CF-IPCountry, then Accept-Language fallback."""
    # 1. CF-IPCountry (Cloudflare GeoIP — most reliable when available)
    country = request.headers.get("cf-ipcountry", "").upper()
    lang = COUNTRY_TO_LANG.get(country)

    # 2. Fallback: Accept-Language header (browser preference)
    if not lang:
        accept = request.headers.get("accept-language", "")
        for part in accept.split(","):
            short = part.split(";")[0].strip().lower()[:2]
            if short in killswitch.ENABLED_LANGS:
                lang = short
                break

    # 3. Fallback final
    if not lang or lang not in killswitch.ENABLED_LANGS:
        lang = DEFAULT_LANG

    return RedirectResponse(url=f"/{lang}", status_code=302)


# ── GET /{lang} → launcher page ────────────────────────────────────────

@router.get("/fr", include_in_schema=False)
async def launcher_fr(request: Request):
    return _render_launcher("fr", request)


@router.get("/en", include_in_schema=False)
async def launcher_en(request: Request):
    return _render_launcher("en", request)


@router.get("/es", include_in_schema=False)
async def launcher_es(request: Request):
    return _render_launcher("es", request)


@router.get("/pt", include_in_schema=False)
async def launcher_pt(request: Request):
    return _render_launcher("pt", request)


@router.get("/de", include_in_schema=False)
async def launcher_de(request: Request):
    return _render_launcher("de", request)


@router.get("/nl", include_in_schema=False)
async def launcher_nl(request: Request):
    return _render_launcher("nl", request)
