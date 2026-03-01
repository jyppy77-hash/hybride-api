"""
Tests P2 — Jinja2 templates + render_template.
Covers:
  - Jinja2 env creation, i18n extension
  - render_template() with FR/EN
  - hreflang_tags generation
  - EM_URLS correctness
  - Template rendering (all 7 pages x 2 langs)
  - ContextVar thread safety
  - Lang switch, OG locale, gambling help
  - Footer, hero partials
"""

import os
from unittest.mock import patch, MagicMock

import pytest


# ── Patches (same pattern as other test files) ─────────────────────────
_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
})


def _make_request():
    """Create a minimal mock Starlette Request."""
    r = MagicMock()
    r.url.path = "/euromillions"
    r.query_params = {}
    r.cookies = {}
    r.headers = {}
    return r


# ═══════════════════════════════════════════════
# 1-3: Jinja2 Environment
# ═══════════════════════════════════════════════

def test_jinja2_env_has_i18n():
    """Jinja2 Environment has the i18n extension loaded."""
    from config.templates import env
    assert "jinja2.ext.InternationalizationExtension" in env.extensions


def test_jinja2_env_autoescape():
    """Jinja2 Environment has autoescape=True."""
    from config.templates import env
    assert env.autoescape is True


def test_templates_dir_exists():
    """Templates directory exists on disk."""
    from config.templates import TEMPLATES_DIR
    assert os.path.isdir(TEMPLATES_DIR)


# ═══════════════════════════════════════════════
# 4-6: EM_URLS
# ═══════════════════════════════════════════════

def test_em_urls_keys():
    """EM_URLS has both FR and EN."""
    from config.templates import EM_URLS
    assert "fr" in EM_URLS
    assert "en" in EM_URLS


def test_em_urls_fr_paths():
    """FR URLs all start with /euromillions."""
    from config.templates import EM_URLS
    for key, url in EM_URLS["fr"].items():
        assert url.startswith("/euromillions"), f"FR URL {key}={url}"


def test_em_urls_en_paths():
    """EN URLs all start with /en/euromillions."""
    from config.templates import EM_URLS
    for key, url in EM_URLS["en"].items():
        assert url.startswith("/en/euromillions"), f"EN URL {key}={url}"


# ═══════════════════════════════════════════════
# 7-9: hreflang_tags
# ═══════════════════════════════════════════════

def test_hreflang_tags_structure():
    """hreflang_tags returns list of dicts with 'lang' and 'url'."""
    from config.templates import hreflang_tags
    tags = hreflang_tags("accueil")
    assert isinstance(tags, list)
    assert len(tags) == 7  # fr, en, es, pt, de, nl, x-default
    for tag in tags:
        assert "lang" in tag
        assert "url" in tag


def test_hreflang_tags_x_default():
    """x-default points to FR URL."""
    from config.templates import hreflang_tags, BASE_URL
    tags = hreflang_tags("generateur")
    x_default = [t for t in tags if t["lang"] == "x-default"]
    assert len(x_default) == 1
    assert x_default[0]["url"] == f"{BASE_URL}/euromillions/generateur"


def test_hreflang_tags_reciprocal():
    """hreflang contains both FR and EN for each page key."""
    from config.templates import hreflang_tags
    for page_key in ("accueil", "generateur", "simulateur", "statistiques",
                      "historique", "news", "faq"):
        tags = hreflang_tags(page_key)
        langs = [t["lang"] for t in tags]
        assert "fr" in langs, f"Missing FR hreflang for {page_key}"
        assert "en" in langs, f"Missing EN hreflang for {page_key}"
        assert "x-default" in langs, f"Missing x-default for {page_key}"


# ═══════════════════════════════════════════════
# 10-12: render_template basic
# ═══════════════════════════════════════════════

def test_render_template_returns_htmlresponse():
    """render_template returns an HTMLResponse."""
    from config.templates import render_template
    from fastapi.responses import HTMLResponse
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="fr", page_key="historique")
    assert isinstance(resp, HTMLResponse)
    assert resp.status_code == 200


def test_render_template_fr_contains_french():
    """FR template contains French text."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="fr", page_key="historique")
    html = resp.body.decode("utf-8")
    assert 'lang="fr"' in html
    assert "Rechercher un tirage" in html


def test_render_template_en_contains_english():
    """EN template contains English text."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="en", page_key="historique")
    html = resp.body.decode("utf-8")
    assert 'lang="en"' in html
    assert "Search for a draw" in html


# ═══════════════════════════════════════════════
# 13-15: Context variables
# ═══════════════════════════════════════════════

def test_render_template_canonical_url():
    """Rendered HTML contains the correct canonical URL."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="fr", page_key="historique")
    html = resp.body.decode("utf-8")
    assert "https://lotoia.fr/euromillions/historique" in html


def test_render_template_lang_switch():
    """FR page contains EN switch link."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="fr", page_key="historique")
    html = resp.body.decode("utf-8")
    assert "/en/euromillions/history" in html
    assert "EN" in html


def test_render_template_og_locale():
    """OG locale is set correctly per language."""
    from config.templates import render_template
    request = _make_request()
    resp_fr = render_template("em/historique.html", request, lang="fr", page_key="historique")
    resp_en = render_template("em/historique.html", request, lang="en", page_key="historique")
    assert "fr_FR" in resp_fr.body.decode("utf-8")
    assert "en_GB" in resp_en.body.decode("utf-8")


# ═══════════════════════════════════════════════
# 16-17: Gambling help
# ═══════════════════════════════════════════════

def test_gambling_help_fr():
    """FR pages include Joueurs Info Service."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="fr", page_key="historique")
    html = resp.body.decode("utf-8")
    assert "joueurs-info-service.fr" in html


def test_gambling_help_en():
    """EN pages include BeGambleAware."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="en", page_key="historique")
    html = resp.body.decode("utf-8")
    assert "begambleaware.org" in html


# ═══════════════════════════════════════════════
# 18-19: Hreflang in rendered HTML
# ═══════════════════════════════════════════════

def test_hreflang_in_rendered_html():
    """Rendered HTML contains hreflang link tags."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="fr", page_key="historique")
    html = resp.body.decode("utf-8")
    assert 'hreflang="fr"' in html
    assert 'hreflang="en"' in html
    assert 'hreflang="x-default"' in html


def test_hreflang_en_rendered():
    """EN rendered page also has FR hreflang."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="en", page_key="historique")
    html = resp.body.decode("utf-8")
    assert 'hreflang="fr"' in html


# ═══════════════════════════════════════════════
# 20-26: All 7 pages render without error (FR)
# ═══════════════════════════════════════════════

_PAGE_CONFIGS = [
    ("em/accueil.html", "accueil", {"nav_back_url": "/", "body_class": "accueil-page em-page", "show_disclaimer_link": True}),
    ("em/generateur.html", "generateur", {"body_class": "loto-page em-page", "include_nav_scroll": True, "show_disclaimer_link": True, "hero_icon": "⭐", "hero_title": "Exploration de grilles EuroMillions", "hero_subtitle": "Analyse", "sponsor75_js": "/ui/static/sponsor-popup75-em.js?v=8", "sponsor_js": "/ui/static/sponsor-popup-em.js?v=4", "app_js": "/ui/static/app-em.js?v=1"}),
    ("em/simulateur.html", "simulateur", {"body_class": "simulator-page em-page", "include_nav_scroll": True, "hero_icon": "⭐", "hero_title": "Analyse de grille EuroMillions", "hero_subtitle": "Audit", "simulateur_js": "/ui/static/simulateur-em.js?v=1", "sponsor_js": "/ui/static/em/sponsor-popup-em.js?v=3"}),
    ("em/statistiques.html", "statistiques", {"include_nav_scroll": True, "show_disclaimer_link": True, "hero_icon": "📊", "hero_title": "Statistiques EuroMillions", "hero_subtitle": "Fréquences"}),
    ("em/historique.html", "historique", {"hero_icon": "📅", "hero_title": "Historique des tirages", "hero_subtitle": "Recherchez un tirage", "footer_style": "margin-top: 48px;"}),
    ("em/faq.html", "faq", {"hero_icon": "❓", "hero_title": "FAQ EuroMillions", "hero_subtitle": "Toutes les réponses", "em_db_total": 729, "faq_js": "/ui/static/faq-em.js?v=1"}),
    ("em/news.html", "news", {"include_nav_scroll": True, "hero_icon": "📰", "hero_title": "Actualités EuroMillions", "hero_subtitle": "Évolutions"}),
]


@pytest.mark.parametrize("template,page_key,extra", _PAGE_CONFIGS,
                         ids=[c[1] for c in _PAGE_CONFIGS])
def test_page_renders_fr(template, page_key, extra):
    """Each page template renders without error in FR."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template(template, request, lang="fr", page_key=page_key, **extra)
    assert resp.status_code == 200
    html = resp.body.decode("utf-8")
    assert 'lang="fr"' in html
    assert len(html) > 500  # Sanity check — not empty


@pytest.mark.parametrize("template,page_key,extra", _PAGE_CONFIGS,
                         ids=[c[1] for c in _PAGE_CONFIGS])
def test_page_renders_en(template, page_key, extra):
    """Each page template renders without error in EN."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template(template, request, lang="en", page_key=page_key, **extra)
    assert resp.status_code == 200
    html = resp.body.decode("utf-8")
    assert 'lang="en"' in html
    assert len(html) > 500


# ═══════════════════════════════════════════════
# 34: ContextVar isolation
# ═══════════════════════════════════════════════

def test_contextvar_restored_after_render():
    """render_template resets ctx_lang after rendering."""
    from config.templates import render_template
    from config.i18n import ctx_lang
    original = ctx_lang.get()
    request = _make_request()
    render_template("em/historique.html", request, lang="en", page_key="historique")
    assert ctx_lang.get() == original


# ═══════════════════════════════════════════════
# 35-36: Footer and hero partials
# ═══════════════════════════════════════════════

def test_footer_in_rendered_page():
    """Rendered page contains footer navigation links."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="fr", page_key="historique")
    html = resp.body.decode("utf-8")
    assert "footer-nav" in html
    assert "/euromillions/faq" in html


def test_hero_in_rendered_page():
    """Rendered page contains hero section with action buttons."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/statistiques.html", request, lang="fr",
                          page_key="statistiques", include_nav_scroll=True,
                          show_disclaimer_link=True, hero_icon="📊",
                          hero_title="Statistiques EuroMillions",
                          hero_subtitle="Fréquences")
    html = resp.body.decode("utf-8")
    assert "loto-hero-header" in html
    assert "loto-hero-btn" in html


# ═══════════════════════════════════════════════
# 37: Chatbot JS path varies by language
# ═══════════════════════════════════════════════

def test_chatbot_js_varies_by_lang():
    """FR uses FR chatbot JS, EN uses EN chatbot JS."""
    from config.templates import render_template
    request = _make_request()
    fr_html = render_template("em/historique.html", request, lang="fr",
                              page_key="historique").body.decode("utf-8")
    en_html = render_template("em/historique.html", request, lang="en",
                              page_key="historique").body.decode("utf-8")
    assert "hybride-chatbot-em.js" in fr_html
    assert "hybride-chatbot-em-en.js" in en_html


# ═══════════════════════════════════════════════
# 38-42: Mobile lang globe selector
# ═══════════════════════════════════════════════

def test_mobile_globe_present_in_html():
    """Rendered HTML contains the mobile globe button and dropdown."""
    from config.templates import render_template
    request = _make_request()
    html = render_template(
        "em/historique.html", request, lang="fr", page_key="historique",
    ).body.decode("utf-8")
    assert "lang-globe-btn" in html
    assert "lang-globe-dropdown" in html


def test_mobile_globe_shows_current_lang():
    """Globe button displays the current language code."""
    from config.templates import render_template
    request = _make_request()
    for lang, expected_code in [("fr", "FR"), ("en", "EN"), ("es", "ES"),
                                 ("pt", "PT"), ("de", "DE"), ("nl", "NL")]:
        html = render_template(
            "em/historique.html", request, lang=lang, page_key="historique",
        ).body.decode("utf-8")
        # The code appears inside .lang-globe-code span
        assert f"lang-globe-code\">{expected_code}</span>" in html, (
            f"Globe should show {expected_code} for lang={lang}"
        )


def test_mobile_globe_all_6_langs_in_dropdown():
    """Dropdown contains all 6 languages regardless of current lang."""
    from config.templates import render_template
    request = _make_request()
    html = render_template(
        "em/historique.html", request, lang="es", page_key="historique",
    ).body.decode("utf-8")
    for code in ("FR", "EN", "ES", "PT", "DE", "NL"):
        assert f">{code}</span>" in html, f"{code} missing from dropdown"


def test_mobile_globe_current_lang_highlighted():
    """Current language has the lang-globe-active class."""
    from config.templates import render_template
    request = _make_request()
    for lang in ("fr", "en", "es", "pt", "de", "nl"):
        html = render_template(
            "em/historique.html", request, lang=lang, page_key="historique",
        ).body.decode("utf-8")
        # Find the active item and verify it contains the current lang code
        idx = html.index("lang-globe-active")
        snippet = html[idx:idx + 200]
        assert f">{lang.upper()}</span>" in snippet, (
            f"Active item should be {lang.upper()}"
        )


def test_mobile_globe_urls_match_page():
    """Dropdown URLs point to the correct page for each language."""
    from config.templates import render_template, EM_URLS
    request = _make_request()
    html = render_template(
        "em/historique.html", request, lang="fr", page_key="historique",
    ).body.decode("utf-8")
    for lc in ("fr", "en", "es", "pt", "de", "nl"):
        expected_url = EM_URLS[lc]["historique"]
        assert f'href="{expected_url}"' in html, (
            f"Dropdown should link to {expected_url} for {lc}"
        )


def test_desktop_lang_switches_still_present():
    """Desktop inline lang-switch buttons are still rendered."""
    from config.templates import render_template
    request = _make_request()
    html = render_template(
        "em/historique.html", request, lang="fr", page_key="historique",
    ).body.decode("utf-8")
    assert 'class="lang-switch"' in html


def test_build_all_lang_switches():
    """_build_all_lang_switches returns all enabled langs with current marked."""
    from config.templates import _build_all_lang_switches
    switches = _build_all_lang_switches("es", "accueil")
    labels = [s["label"] for s in switches]
    assert "FR" in labels
    assert "ES" in labels
    current = [s for s in switches if s["current"]]
    assert len(current) == 1
    assert current[0]["label"] == "ES"
    non_current = [s for s in switches if not s["current"]]
    assert len(non_current) == 5


# ═══════════════════════════════════════════════
# Legal pages (mentions, confidentialite, cookies, disclaimer)
# ═══════════════════════════════════════════════

_LEGAL_PAGES = [
    ("mentions", "em/mentions-legales.html"),
    ("confidentialite", "em/confidentialite.html"),
    ("cookies", "em/cookies.html"),
    ("disclaimer", "em/disclaimer.html"),
]

_ALL_LANGS = ("fr", "en", "es", "pt", "de", "nl")


@pytest.mark.parametrize("page_key,template", _LEGAL_PAGES)
@pytest.mark.parametrize("lang", _ALL_LANGS)
def test_legal_page_renders_all_langs(page_key, template, lang):
    """Each legal page renders without error for all 6 languages."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template(
        template, request, lang=lang, page_key=page_key,
        body_class="subpage legal-page em-page",
    )
    assert resp.status_code == 200
    html = resp.body.decode("utf-8")
    assert "legal-content" in html or "legal-section" in html


@pytest.mark.parametrize("page_key,template", _LEGAL_PAGES)
def test_legal_page_has_noindex(page_key, template):
    """Legal pages have noindex meta tag."""
    from config.templates import render_template
    request = _make_request()
    html = render_template(
        template, request, lang="fr", page_key=page_key,
        body_class="subpage legal-page em-page",
    ).body.decode("utf-8")
    assert 'noindex' in html


@pytest.mark.parametrize("page_key,template", _LEGAL_PAGES)
def test_legal_page_has_canonical(page_key, template):
    """Legal pages have canonical URL."""
    from config.templates import render_template
    request = _make_request()
    html = render_template(
        template, request, lang="fr", page_key=page_key,
        body_class="subpage legal-page em-page",
    ).body.decode("utf-8")
    assert 'rel="canonical"' in html


def test_legal_urls_in_em_urls():
    """All 4 legal page keys exist in EM_URLS for all 6 langs."""
    from config.templates import EM_URLS
    for lang in _ALL_LANGS:
        for key in ("mentions", "confidentialite", "cookies", "disclaimer"):
            assert key in EM_URLS[lang], f"Missing EM_URLS[{lang}][{key}]"
            assert EM_URLS[lang][key].startswith("/"), (
                f"EM_URLS[{lang}][{key}] should start with /"
            )


@pytest.mark.parametrize("lang", _ALL_LANGS)
def test_footer_legal_links_per_lang(lang):
    """Footer renders correct legal URLs for each language."""
    from config.templates import render_template, EM_URLS
    request = _make_request()
    html = render_template(
        "em/accueil.html", request, lang=lang, page_key="accueil",
        nav_back_url="/", body_class="accueil-page em-page",
        show_disclaimer_link=True,
    ).body.decode("utf-8")
    # Footer should contain the language-specific legal URLs
    assert EM_URLS[lang]["mentions"] in html, (
        f"Footer should link to {EM_URLS[lang]['mentions']} for {lang}"
    )
    assert EM_URLS[lang]["confidentialite"] in html, (
        f"Footer should link to {EM_URLS[lang]['confidentialite']} for {lang}"
    )
    assert EM_URLS[lang]["cookies"] in html, (
        f"Footer should link to {EM_URLS[lang]['cookies']} for {lang}"
    )
    assert EM_URLS[lang]["disclaimer"] in html, (
        f"Footer should link to {EM_URLS[lang]['disclaimer']} for {lang}"
    )
