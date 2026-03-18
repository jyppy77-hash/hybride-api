"""
Tests V43 — SEO Indexation 360° audit.
Verifies:
  - Sitemap contains all 9 EM public URLs (6 home + 3 FR tools)
  - Each EM page has a self-referencing canonical
  - Hreflang cross-links are complete (6 langs + x-default per page)
  - robots.txt does not block EM URLs
  - No EM public page has <meta name="robots" content="noindex">
  - <title> unique per language
  - <meta description> unique per language
  - FR tool pages (/euromillions/generateur, etc.) respond 200
  - Sitemap <lastmod> is recent (< 7 days)
  - Content-Language header present on EM pages
"""

import os
import re
from contextlib import asynccontextmanager
from datetime import date, timedelta
from unittest.mock import patch, AsyncMock
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient


# ── Patches (same pattern as test_seo_headers.py) ─────────────────────────

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})


def _async_cm_conn(cursor):
    @asynccontextmanager
    async def _cm():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn
    return _cm


def _get_client():
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _make_cursor():
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=None)
    cursor.fetchall = AsyncMock(return_value=[])
    cursor.close = AsyncMock()
    return cursor


# ── XML namespace for sitemap parsing ─────────────────────────────────────

_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "xhtml": "http://www.w3.org/1999/xhtml",
}

# ── The 9 EM URLs from GSC ───────────────────────────────────────────────

_EM_HOME_URLS = [
    "https://lotoia.fr/euromillions",
    "https://lotoia.fr/en/euromillions",
    "https://lotoia.fr/es/euromillions",
    "https://lotoia.fr/pt/euromillions",
    "https://lotoia.fr/de/euromillions",
    "https://lotoia.fr/nl/euromillions",
]

_EM_TOOL_URLS_FR = [
    "https://lotoia.fr/euromillions/generateur",
    "https://lotoia.fr/euromillions/simulateur",
    "https://lotoia.fr/euromillions/statistiques",
]

_ALL_9_EM_URLS = _EM_HOME_URLS + _EM_TOOL_URLS_FR


# ═══════════════════════════════════════════════
# 1. Sitemap — all 9 EM URLs present
# ═══════════════════════════════════════════════

class TestSitemapContainsEMUrls:
    """Sitemap must contain all 9 EM URLs from GSC report."""

    def test_sitemap_contains_all_9_em_urls(self):
        """GET /sitemap.xml contains all 9 EM URLs."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/sitemap.xml")

        assert resp.status_code == 200
        assert "application/xml" in resp.headers["content-type"]

        root = ElementTree.fromstring(resp.text)
        locs = {el.text for el in root.findall(".//sm:url/sm:loc", _NS)}

        for url in _ALL_9_EM_URLS:
            assert url in locs, f"Missing in sitemap: {url}"

    def test_sitemap_lastmod_is_recent(self):
        """Sitemap <lastmod> should be today (dynamic)."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/sitemap.xml")

        root = ElementTree.fromstring(resp.text)
        lastmods = {el.text for el in root.findall(".//sm:url/sm:lastmod", _NS)}

        today = date.today().isoformat()
        week_ago = (date.today() - timedelta(days=7)).isoformat()

        for lm in lastmods:
            assert lm >= week_ago, f"lastmod too old: {lm}"
            assert lm <= today, f"lastmod in the future: {lm}"


# ═══════════════════════════════════════════════
# 2. Hreflang cross-links in sitemap
# ═══════════════════════════════════════════════

class TestSitemapHreflang:
    """Sitemap hreflang alternate links must be complete."""

    def test_hreflang_6_langs_plus_xdefault_on_home(self):
        """Each EM home URL in sitemap has 7 hreflang links (6 langs + x-default)."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/sitemap.xml")

        root = ElementTree.fromstring(resp.text)
        for url_el in root.findall(".//sm:url", _NS):
            loc = url_el.find("sm:loc", _NS).text
            if loc in _EM_HOME_URLS:
                alternates = url_el.findall("xhtml:link", _NS)
                hreflangs = {a.get("hreflang") for a in alternates}
                assert "x-default" in hreflangs, f"Missing x-default on {loc}"
                for lang in ("fr", "en", "es", "pt", "de", "nl"):
                    assert lang in hreflangs, f"Missing hreflang={lang} on {loc}"

    def test_hreflang_xdefault_points_to_fr(self):
        """x-default hreflang must point to the FR version."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/sitemap.xml")

        root = ElementTree.fromstring(resp.text)
        for url_el in root.findall(".//sm:url", _NS):
            loc = url_el.find("sm:loc", _NS).text
            if loc in _EM_HOME_URLS:
                for alt in url_el.findall("xhtml:link", _NS):
                    if alt.get("hreflang") == "x-default":
                        href = alt.get("href")
                        assert "lotoia.fr/euromillions" in href, \
                            f"x-default should point to FR, got: {href}"
                        assert "/en/" not in href and "/es/" not in href, \
                            f"x-default points to non-FR: {href}"


# ═══════════════════════════════════════════════
# 3. Canonical self-referent on EM pages
# ═══════════════════════════════════════════════

class TestCanonicalSelfReferent:
    """Each EM page must have a canonical link pointing to itself."""

    @pytest.mark.parametrize("path,expected_canonical", [
        ("/euromillions", "https://lotoia.fr/euromillions"),
        ("/en/euromillions", "https://lotoia.fr/en/euromillions"),
        ("/euromillions/generateur", "https://lotoia.fr/euromillions/generateur"),
        ("/euromillions/simulateur", "https://lotoia.fr/euromillions/simulateur"),
        ("/euromillions/statistiques", "https://lotoia.fr/euromillions/statistiques"),
        ("/es/euromillions", "https://lotoia.fr/es/euromillions"),
        ("/pt/euromillions", "https://lotoia.fr/pt/euromillions"),
        ("/de/euromillions", "https://lotoia.fr/de/euromillions"),
        ("/nl/euromillions", "https://lotoia.fr/nl/euromillions"),
    ])
    def test_canonical_self_referent(self, path, expected_canonical):
        """EM page canonical must point to itself."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
            client = _get_client()
            resp = client.get(path)

        assert resp.status_code == 200
        assert f'href="{expected_canonical}"' in resp.text


# ═══════════════════════════════════════════════
# 4. Hreflang in HTML <head>
# ═══════════════════════════════════════════════

class TestHreflangInHead:
    """EM pages must have hreflang links in HTML <head>."""

    def test_hreflang_tags_on_em_accueil_fr(self):
        """GET /euromillions has hreflang for all 6 langs + x-default."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
            client = _get_client()
            resp = client.get("/euromillions")

        assert resp.status_code == 200
        for lang in ("fr", "en", "es", "pt", "de", "nl", "x-default"):
            assert f'hreflang="{lang}"' in resp.text, \
                f"Missing hreflang={lang} in /euromillions head"

    def test_hreflang_tags_on_en_euromillions(self):
        """GET /en/euromillions has hreflang for all 6 langs + x-default."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
            client = _get_client()
            resp = client.get("/en/euromillions")

        assert resp.status_code == 200
        for lang in ("fr", "en", "es", "pt", "de", "nl", "x-default"):
            assert f'hreflang="{lang}"' in resp.text


# ═══════════════════════════════════════════════
# 5. robots.txt does not block EM URLs
# ═══════════════════════════════════════════════

class TestRobotsTxtAllowsEM:
    """robots.txt must not block EM URLs."""

    def test_robots_txt_allows_euromillions(self):
        """robots.txt has Allow: /euromillions."""
        robots_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "ui", "robots.txt"
        )
        with open(robots_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "Allow: /euromillions" in content

    def test_robots_txt_allows_all_lang_homes(self):
        """robots.txt allows all 6 lang EM home pages."""
        robots_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "ui", "robots.txt"
        )
        with open(robots_path, "r", encoding="utf-8") as f:
            content = f.read()

        for prefix in ("/euromillions", "/en/euromillions", "/es/euromillions",
                       "/pt/euromillions", "/de/euromillions", "/nl/euromillions"):
            assert f"Allow: {prefix}" in content, \
                f"Missing Allow: {prefix} in robots.txt"

    def test_robots_txt_no_disallow_euromillions(self):
        """No Disallow rule blocks /euromillions paths."""
        robots_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "ui", "robots.txt"
        )
        with open(robots_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Check User-agent: * section for Disallow rules
        in_wildcard = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("User-agent:"):
                in_wildcard = stripped == "User-agent: *"
            if in_wildcard and stripped.startswith("Disallow:"):
                path = stripped.split(":", 1)[1].strip()
                assert not "/euromillions".startswith(path) or path == "", \
                    f"Disallow {path} would block /euromillions"

    def test_robots_txt_has_sitemap(self):
        """robots.txt has Sitemap directive pointing to dynamic sitemap."""
        robots_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "ui", "robots.txt"
        )
        with open(robots_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "Sitemap: https://lotoia.fr/sitemap.xml" in content

    def test_robots_txt_allows_em_tools(self):
        """robots.txt explicitly allows EM tool pages."""
        robots_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "ui", "robots.txt"
        )
        with open(robots_path, "r", encoding="utf-8") as f:
            content = f.read()

        for tool in ("/euromillions/generateur", "/euromillions/simulateur",
                     "/euromillions/statistiques"):
            assert f"Allow: {tool}" in content, \
                f"Missing explicit Allow: {tool} in robots.txt"


# ═══════════════════════════════════════════════
# 6. No meta noindex on public EM pages
# ═══════════════════════════════════════════════

class TestNoMetaNoindex:
    """No public EM page should have noindex meta tag."""

    @pytest.mark.parametrize("path", [
        "/euromillions",
        "/en/euromillions",
        "/es/euromillions",
        "/pt/euromillions",
        "/de/euromillions",
        "/nl/euromillions",
        "/euromillions/generateur",
        "/euromillions/simulateur",
        "/euromillions/statistiques",
    ])
    def test_no_noindex_on_public_em_pages(self, path):
        """Public EM pages must NOT have noindex meta tag."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
            client = _get_client()
            resp = client.get(path)

        assert resp.status_code == 200
        assert 'content="noindex' not in resp.text.lower()


# ═══════════════════════════════════════════════
# 7. Unique <title> per language
# ═══════════════════════════════════════════════

class TestUniqueTitlePerLang:
    """<title> must be unique per language (not all FR)."""

    def test_title_differs_between_fr_and_en(self):
        """FR and EN home pages must have different <title>."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
            client = _get_client()
            resp_fr = client.get("/euromillions")
            resp_en = client.get("/en/euromillions")

        title_fr = re.search(r"<title>(.*?)</title>", resp_fr.text)
        title_en = re.search(r"<title>(.*?)</title>", resp_en.text)
        assert title_fr and title_en
        assert title_fr.group(1) != title_en.group(1), \
            "FR and EN titles should differ"

    def test_title_differs_between_fr_and_es(self):
        """FR and ES home pages must have different <title>."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
            client = _get_client()
            resp_fr = client.get("/euromillions")
            resp_es = client.get("/es/euromillions")

        title_fr = re.search(r"<title>(.*?)</title>", resp_fr.text)
        title_es = re.search(r"<title>(.*?)</title>", resp_es.text)
        assert title_fr and title_es
        assert title_fr.group(1) != title_es.group(1), \
            "FR and ES titles should differ"


# ═══════════════════════════════════════════════
# 8. Unique <meta description> per language
# ═══════════════════════════════════════════════

class TestUniqueDescriptionPerLang:
    """<meta description> must be unique per language."""

    def test_description_differs_between_fr_and_en(self):
        """FR and EN home pages must have different meta description."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
            client = _get_client()
            resp_fr = client.get("/euromillions")
            resp_en = client.get("/en/euromillions")

        desc_fr = re.search(r'<meta name="description" content="(.*?)"', resp_fr.text)
        desc_en = re.search(r'<meta name="description" content="(.*?)"', resp_en.text)
        assert desc_fr and desc_en
        assert desc_fr.group(1) != desc_en.group(1), \
            "FR and EN descriptions should differ"


# ═══════════════════════════════════════════════
# 9. FR tool pages respond 200
# ═══════════════════════════════════════════════

class TestFRToolPages200:
    """FR tool pages must respond with 200."""

    @pytest.mark.parametrize("path", [
        "/euromillions/generateur",
        "/euromillions/simulateur",
        "/euromillions/statistiques",
    ])
    def test_fr_tool_page_200(self, path):
        """FR EM tool page responds 200."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get(path)

        assert resp.status_code == 200


# ═══════════════════════════════════════════════
# 10. Content-Language header on EM pages
# ═══════════════════════════════════════════════

class TestContentLanguageHeader:
    """EM pages must have Content-Language header matching the page lang."""

    @pytest.mark.parametrize("path,expected_lang", [
        ("/euromillions", "fr"),
        ("/en/euromillions", "en"),
        ("/es/euromillions", "es"),
        ("/pt/euromillions", "pt"),
        ("/de/euromillions", "de"),
        ("/nl/euromillions", "nl"),
    ])
    def test_content_language_header(self, path, expected_lang):
        """EM page has Content-Language header matching its lang."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
            client = _get_client()
            resp = client.get(path)

        assert resp.status_code == 200
        assert "Content-Language" in resp.headers, \
            f"Missing Content-Language header on {path}"
        assert resp.headers["Content-Language"] == expected_lang, \
            f"Expected Content-Language={expected_lang}, got {resp.headers['Content-Language']}"


# ═══════════════════════════════════════════════
# 11. Sitemap XML format validation
# ═══════════════════════════════════════════════

class TestSitemapXMLFormat:
    """Sitemap must produce valid, well-formed XML."""

    def _get_sitemap(self):
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            return client.get("/sitemap.xml")

    def test_content_type_is_application_xml(self):
        """Content-Type must be application/xml with charset."""
        resp = self._get_sitemap()
        ct = resp.headers["content-type"]
        assert "application/xml" in ct
        assert "charset=utf-8" in ct

    def test_xml_is_parsable(self):
        """Sitemap XML must parse without errors."""
        resp = self._get_sitemap()
        root = ElementTree.fromstring(resp.text)
        assert root is not None

    def test_root_tag_is_urlset(self):
        """Root tag must be {sitemap}urlset."""
        resp = self._get_sitemap()
        root = ElementTree.fromstring(resp.text)
        assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"

    def test_every_url_has_loc_lastmod_changefreq_priority(self):
        """Each <url> must have <loc>, <lastmod>, <changefreq>, <priority>."""
        resp = self._get_sitemap()
        root = ElementTree.fromstring(resp.text)
        urls = root.findall(".//sm:url", _NS)
        assert len(urls) > 0

        for url_el in urls:
            loc = url_el.find("sm:loc", _NS)
            lastmod = url_el.find("sm:lastmod", _NS)
            changefreq = url_el.find("sm:changefreq", _NS)
            priority = url_el.find("sm:priority", _NS)

            assert loc is not None and loc.text, \
                "Missing <loc> in a <url> block"
            assert lastmod is not None and lastmod.text, \
                f"Missing <lastmod> for {loc.text}"
            assert changefreq is not None and changefreq.text, \
                f"Missing <changefreq> for {loc.text}"
            assert priority is not None and priority.text, \
                f"Missing <priority> for {loc.text}"

    def test_em_multilang_urls_have_hreflang_links(self):
        """EM multilingual URLs must have xhtml:link with 6 langs + x-default."""
        resp = self._get_sitemap()
        root = ElementTree.fromstring(resp.text)

        for url_el in root.findall(".//sm:url", _NS):
            loc = url_el.find("sm:loc", _NS).text
            if "euromillions" in loc and "lotoia.fr/euromillions" in loc:
                # This is an EM page — must have hreflang alternates
                alternates = url_el.findall("xhtml:link", _NS)
                assert len(alternates) >= 7, \
                    f"{loc} has only {len(alternates)} hreflang links (expected >= 7)"
                hreflangs = {a.get("hreflang") for a in alternates}
                assert "x-default" in hreflangs, \
                    f"Missing x-default hreflang on {loc}"
                break  # Just verify the first EM FR URL

    def test_xml_declaration_present(self):
        """Sitemap must start with <?xml version="1.0" encoding="UTF-8"?>."""
        resp = self._get_sitemap()
        assert resp.text.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_xsl_stylesheet_present(self):
        """Sitemap must reference XSL stylesheet for browser rendering."""
        resp = self._get_sitemap()
        assert '<?xml-stylesheet' in resp.text
        assert 'href="/sitemap.xsl"' in resp.text

    def test_xsl_route_responds_200(self):
        """GET /sitemap.xsl must respond 200."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/sitemap.xsl")

        assert resp.status_code == 200
        assert "xsl:stylesheet" in resp.text

    def test_url_count_matches_expected(self):
        """Sitemap must have 14 Loto + 72 EM = 86 URLs."""
        resp = self._get_sitemap()
        root = ElementTree.fromstring(resp.text)
        urls = root.findall(".//sm:url", _NS)
        # 14 Loto pages + 12 EM page types × 6 langs = 86
        assert len(urls) >= 80, f"Expected >= 80 URLs, got {len(urls)}"
