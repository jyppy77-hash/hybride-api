"""
Tests P5/5 — Routes multilingues + SEO.
Covers:
  - Kill switch (ENABLED_LANGS)
  - EM_URLS for all 6 languages
  - hreflang_tags dynamic filtering
  - Multilang route registration (28 routes: 7 pages x 4 langs)
  - Kill switch redirect (disabled lang → 302 to FR)
  - Dynamic sitemap (/sitemap.xml)
  - Lang switch mapping
  - Gambling help + OG locale coverage
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from config.killswitch import ENABLED_LANGS
from config.templates import (
    EM_URLS, hreflang_tags, _LANG_SWITCH, _GAMBLING_HELP,
    _OG_LOCALE, _DATE_LOCALE, BASE_URL,
)


# ═══════════════════════════════════════════════
# 1. Kill switch defaults
# ═══════════════════════════════════════════════

def test_killswitch_default():
    """Default ENABLED_LANGS is fr + en + es."""
    assert ENABLED_LANGS == ["fr", "en", "es"]


def test_killswitch_excludes_new_langs():
    """PT/DE/NL are OFF by default."""
    for lang in ("pt", "de", "nl"):
        assert lang not in ENABLED_LANGS


# ═══════════════════════════════════════════════
# 2. EM_URLS coverage
# ═══════════════════════════════════════════════

_ALL_LANGS = ("fr", "en", "pt", "es", "de", "nl")
_PAGE_KEYS = ("home", "accueil", "simulateur", "generateur",
              "statistiques", "historique", "news", "faq")


@pytest.mark.parametrize("lang", _ALL_LANGS)
def test_em_urls_has_lang(lang):
    """EM_URLS contains entry for each language."""
    assert lang in EM_URLS


@pytest.mark.parametrize("lang", _ALL_LANGS)
def test_em_urls_has_all_page_keys(lang):
    """Each language has all required page keys."""
    for key in _PAGE_KEYS:
        assert key in EM_URLS[lang], f"Missing {key} in EM_URLS[{lang}]"


@pytest.mark.parametrize("lang", ("pt", "es", "de", "nl"))
def test_em_urls_has_lang_prefix(lang):
    """Non-FR/EN URLs start with /{lang}/euromillions."""
    for key, url in EM_URLS[lang].items():
        assert url.startswith(f"/{lang}/euromillions"), (
            f"EM_URLS[{lang}][{key}] = {url} doesn't start with /{lang}/euromillions"
        )


def test_em_urls_fr_no_prefix():
    """FR URLs start with /euromillions (no lang prefix)."""
    for url in EM_URLS["fr"].values():
        assert url.startswith("/euromillions")
        assert not url.startswith("/fr/")


def test_em_urls_en_prefix():
    """EN URLs start with /en/euromillions."""
    for url in EM_URLS["en"].values():
        assert url.startswith("/en/euromillions")


def test_em_urls_no_duplicate_paths():
    """No two languages share the same URL path."""
    all_urls = []
    for lang_urls in EM_URLS.values():
        all_urls.extend(lang_urls.values())
    # home and accueil point to same URL per lang, so filter unique per lang first
    per_lang_unique = set()
    for lang, lang_urls in EM_URLS.items():
        for url in lang_urls.values():
            per_lang_unique.add((lang, url))
    # Check cross-lang uniqueness (exclude home/accueil dups within same lang)
    seen = {}
    for lang, url in per_lang_unique:
        if url in seen and seen[url] != lang:
            pytest.fail(f"URL {url} shared by {seen[url]} and {lang}")
        seen[url] = lang


# ═══════════════════════════════════════════════
# 3. hreflang_tags
# ═══════════════════════════════════════════════

def test_hreflang_default_fr_en_es():
    """Default hreflang includes fr + en + es + x-default."""
    tags = hreflang_tags("accueil")
    langs = [t["lang"] for t in tags]
    assert "fr" in langs
    assert "en" in langs
    assert "es" in langs
    assert "x-default" in langs
    assert len(tags) == 4


def test_hreflang_excludes_disabled():
    """Disabled languages are NOT in hreflang tags."""
    tags = hreflang_tags("accueil")
    langs = [t["lang"] for t in tags]
    for lang in ("pt", "de", "nl"):
        assert lang not in langs


def test_hreflang_includes_enabled():
    """When PT is enabled, hreflang includes it."""
    with patch("config.killswitch.ENABLED_LANGS", ["fr", "en", "pt"]):
        tags = hreflang_tags("accueil")
    langs = [t["lang"] for t in tags]
    assert "pt" in langs
    assert len(tags) == 4  # fr, en, pt, x-default


def test_hreflang_all_enabled():
    """When all langs enabled, hreflang includes all 6 + x-default."""
    with patch("config.killswitch.ENABLED_LANGS", list(_ALL_LANGS)):
        tags = hreflang_tags("accueil")
    langs = [t["lang"] for t in tags]
    for lang in _ALL_LANGS:
        assert lang in langs
    assert "x-default" in langs
    assert len(tags) == 7


def test_hreflang_xdefault_is_fr():
    """x-default always points to FR URL."""
    tags = hreflang_tags("generateur")
    xdef = [t for t in tags if t["lang"] == "x-default"]
    assert len(xdef) == 1
    assert xdef[0]["url"] == f"{BASE_URL}/euromillions/generateur"


# ═══════════════════════════════════════════════
# 4. _LANG_SWITCH mapping
# ═══════════════════════════════════════════════

def test_lang_switch_fr_to_en():
    """FR lang switch points to EN URLs."""
    assert _LANG_SWITCH["fr"]["accueil"] == "/en/euromillions"


def test_lang_switch_en_to_fr():
    """EN lang switch points to FR URLs."""
    assert _LANG_SWITCH["en"]["accueil"] == "/euromillions"


@pytest.mark.parametrize("lang", ("pt", "es", "de", "nl"))
def test_lang_switch_new_to_fr(lang):
    """New languages switch to FR URLs."""
    assert _LANG_SWITCH[lang]["accueil"] == "/euromillions"
    assert _LANG_SWITCH[lang]["generateur"] == "/euromillions/generateur"


# ═══════════════════════════════════════════════
# 5. Gambling help + OG locale + date locale
# ═══════════════════════════════════════════════

@pytest.mark.parametrize("lang", _ALL_LANGS)
def test_gambling_help_all_langs(lang):
    """Each language has gambling help URL + name."""
    assert lang in _GAMBLING_HELP
    assert "url" in _GAMBLING_HELP[lang]
    assert "name" in _GAMBLING_HELP[lang]
    assert _GAMBLING_HELP[lang]["url"].startswith("https://")


@pytest.mark.parametrize("lang", _ALL_LANGS)
def test_og_locale_all_langs(lang):
    """Each language has OG locale."""
    assert lang in _OG_LOCALE
    assert "_" in _OG_LOCALE[lang]  # e.g. "fr_FR"


@pytest.mark.parametrize("lang", _ALL_LANGS)
def test_date_locale_all_langs(lang):
    """Each language has date locale."""
    assert lang in _DATE_LOCALE
    assert "-" in _DATE_LOCALE[lang]  # e.g. "fr-FR"


# ═══════════════════════════════════════════════
# 6. Route registration (multilang_em_pages)
# ═══════════════════════════════════════════════

def test_multilang_routes_registered():
    """28 routes registered (7 pages x 4 langs)."""
    from routes.multilang_em_pages import router
    paths = [r.path for r in router.routes]
    # Check all 4 langs have routes
    for lang in ("pt", "es", "de", "nl"):
        lang_paths = [p for p in paths if p.startswith(f"/{lang}/")]
        assert len(lang_paths) == 7, (
            f"Expected 7 routes for {lang}, got {len(lang_paths)}: {lang_paths}"
        )


def test_multilang_routes_match_em_urls():
    """All registered route paths match EM_URLS entries."""
    from routes.multilang_em_pages import router
    paths = set(r.path for r in router.routes)
    for lang in ("pt", "es", "de", "nl"):
        for key in ("home", "generateur", "simulateur", "statistiques",
                     "historique", "news", "faq"):
            url = EM_URLS[lang][key]
            # home and accueil share same URL — accueil is the route
            if key == "home":
                continue
            assert url in paths, f"Missing route for EM_URLS[{lang}][{key}] = {url}"


# ═══════════════════════════════════════════════
# 7. Kill switch redirect (integration via test client)
# ═══════════════════════════════════════════════

def _get_client():
    """Build a TestClient with standard mocks."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient

    with patch("main.StaticFiles", return_value=MagicMock()), \
         patch.dict("os.environ", {
             "DB_HOST": "x", "DB_USER": "x", "DB_PASS": "x", "DB_NAME": "x",
         }):
        from main import app
        return TestClient(app, raise_server_exceptions=False)


def test_disabled_lang_redirects_to_fr():
    """PT route with PT disabled → 302 redirect to FR equivalent."""
    client = _get_client()
    resp = client.get("/pt/euromillions/gerador", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/euromillions/generateur"


def test_disabled_lang_faq_redirects_to_fr():
    """PT FAQ route with PT disabled → 302 redirect to FR FAQ."""
    client = _get_client()
    resp = client.get("/pt/euromillions/faq", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/euromillions/faq"


@pytest.mark.parametrize("lang,path", [
    ("de", "/de/euromillions/generator"),
    ("nl", "/nl/euromillions/nieuws"),
])
def test_all_disabled_langs_redirect(lang, path):
    """All disabled lang routes redirect to FR."""
    client = _get_client()
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("/euromillions")


def test_es_enabled_returns_200():
    """ES is enabled — pages return 200, not redirect."""
    client = _get_client()
    resp = client.get("/es/euromillions", follow_redirects=False)
    assert resp.status_code == 200


# ═══════════════════════════════════════════════
# 8. Dynamic sitemap
# ═══════════════════════════════════════════════

def test_sitemap_returns_xml():
    """GET /sitemap.xml returns valid XML."""
    client = _get_client()
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert '<?xml version="1.0"' in resp.text


def test_sitemap_contains_loto_pages():
    """Sitemap includes FR Loto pages."""
    client = _get_client()
    resp = client.get("/sitemap.xml")
    assert f"{BASE_URL}/loto" in resp.text
    assert f"{BASE_URL}/accueil" in resp.text
    assert f"{BASE_URL}/historique" in resp.text


def test_sitemap_contains_fr_em():
    """Sitemap includes FR EuroMillions pages."""
    client = _get_client()
    resp = client.get("/sitemap.xml")
    assert f"{BASE_URL}/euromillions" in resp.text
    assert f"{BASE_URL}/euromillions/generateur" in resp.text


def test_sitemap_contains_en_em():
    """Sitemap includes EN EuroMillions pages."""
    client = _get_client()
    resp = client.get("/sitemap.xml")
    assert f"{BASE_URL}/en/euromillions" in resp.text
    assert f"{BASE_URL}/en/euromillions/generator" in resp.text


def test_sitemap_includes_es():
    """Sitemap includes ES EuroMillions pages."""
    client = _get_client()
    resp = client.get("/sitemap.xml")
    assert f"{BASE_URL}/es/euromillions" in resp.text


def test_sitemap_excludes_disabled_langs():
    """Sitemap does NOT include disabled language pages."""
    client = _get_client()
    resp = client.get("/sitemap.xml")
    for lang in ("pt", "de", "nl"):
        assert f"/{lang}/euromillions" not in resp.text


def test_sitemap_includes_enabled_lang():
    """When PT is enabled, sitemap includes PT pages."""
    with patch("config.killswitch.ENABLED_LANGS", ["fr", "en", "pt"]):
        client = _get_client()
        resp = client.get("/sitemap.xml")
    assert f"{BASE_URL}/pt/euromillions" in resp.text
    assert f"{BASE_URL}/pt/euromillions/gerador" in resp.text


# ═══════════════════════════════════════════════
# 9. Sitemap structure
# ═══════════════════════════════════════════════

def test_sitemap_has_urlset():
    """Sitemap has proper urlset wrapper."""
    client = _get_client()
    resp = client.get("/sitemap.xml")
    assert "<urlset" in resp.text
    assert "</urlset>" in resp.text


def test_sitemap_has_priority():
    """Sitemap entries have priority tags."""
    client = _get_client()
    resp = client.get("/sitemap.xml")
    assert "<priority>" in resp.text


def test_sitemap_has_lastmod():
    """Sitemap entries have lastmod tags."""
    client = _get_client()
    resp = client.get("/sitemap.xml")
    assert "<lastmod>" in resp.text


# ═══════════════════════════════════════════════
# 10. Config/languages.py PAGE_SLUGS coverage
# ═══════════════════════════════════════════════

def test_page_slugs_all_langs():
    """PAGE_SLUGS has entries for all 6 languages."""
    from config.languages import PAGE_SLUGS, ValidLang
    for lang in ValidLang:
        assert lang in PAGE_SLUGS, f"Missing PAGE_SLUGS for {lang}"
        assert len(PAGE_SLUGS[lang]) == 7  # 7 page types
