"""
Tests Lot SEO #5 (Release 1.6.048) — <lastmod> sitemap par catégorie de page.

Couvre :
  - DB down → fallback LAST_DEPLOY_DATE, sitemap répond toujours 200 (jamais 500)
  - Pages dynamiques Loto → date dernier tirage Loto / EM → date dernier tirage EM
  - Pages news (FR + EM 6 langues) → LAST_NEWS_DATE
  - Pages éditoriales + launcher → _EDITORIAL_LASTMOD
  - Non-régression structure (nombre d'URLs, hreflang, XML bien formé, format W3C)

Point de patch : routes.sitemap._fetch_last_draw_date_loto / _fetch_last_draw_date_em
(bindings locaux au module sitemap — importés depuis routes/api_pdf.py et
routes/em_analyse.py). Sans patch, la vraie connexion échoue sur l'env DB fake du
harnais → except → None → fallback (chemin DB-down exercé naturellement).
"""
import os
import re
from contextlib import asynccontextmanager
from unittest.mock import patch, AsyncMock
from xml.etree import ElementTree

from fastapi.testclient import TestClient


# ── Patches (same pattern as test_seo_indexation.py) ──────────────────────

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


_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "xhtml": "http://www.w3.org/1999/xhtml",
}

_LOTO_DRAW_DATE = "2026-06-08"
_EM_DRAW_DATE = "2026-06-09"


def _get_sitemap(loto_date=None, em_date=None):
    """GET /sitemap.xml avec fetchs tirage mockés (None = DB down)."""
    cursor = _make_cursor()
    with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
         patch("routes.sitemap._fetch_last_draw_date_loto",
               AsyncMock(return_value=loto_date)), \
         patch("routes.sitemap._fetch_last_draw_date_em",
               AsyncMock(return_value=em_date)):
        client = _get_client()
        return client.get("/sitemap.xml")


def _lastmod_map(xml_text: str) -> dict:
    """{loc: lastmod} pour chaque <url> du sitemap."""
    root = ElementTree.fromstring(xml_text)
    out = {}
    for url_el in root.findall(".//sm:url", _NS):
        loc = url_el.find("sm:loc", _NS).text
        out[loc] = url_el.find("sm:lastmod", _NS).text
    return out


# ═══════════════════════════════════════════════
# 1. DB down → fallback LAST_DEPLOY_DATE, jamais 500
# ═══════════════════════════════════════════════

class TestDbDownFallback:
    """Le sitemap est critique SEO : il doit répondre 200 même si la DB tousse."""

    def test_sitemap_200_when_fetch_returns_none(self):
        """Fetchs → None (DB down) → 200 + dynamiques en LAST_DEPLOY_DATE."""
        resp = _get_sitemap(loto_date=None, em_date=None)
        assert resp.status_code == 200

        from config.version import LAST_DEPLOY_DATE
        lastmods = _lastmod_map(resp.text)
        assert lastmods["https://lotoia.fr/loto"] == LAST_DEPLOY_DATE
        assert lastmods["https://lotoia.fr/euromillions"] == LAST_DEPLOY_DATE

    def test_sitemap_200_without_any_fetch_patch(self):
        """Sans patch des fetchs : la vraie connexion échoue sur l'env DB fake
        → chemin except → None → fallback exercé de bout en bout, toujours 200."""
        cursor = _make_cursor()
        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/sitemap.xml")
        assert resp.status_code == 200
        assert "application/xml" in resp.headers["content-type"]


# ═══════════════════════════════════════════════
# 2. Pages dynamiques → date du dernier tirage
# ═══════════════════════════════════════════════

class TestDynamicPagesLastmod:
    """7 pages Loto dynamiques → tirage Loto ; pages EM dynamiques → tirage EM."""

    def test_loto_dynamic_pages_get_loto_draw_date(self):
        resp = _get_sitemap(loto_date=_LOTO_DRAW_DATE, em_date=_EM_DRAW_DATE)
        lastmods = _lastmod_map(resp.text)

        from routes.sitemap import _LOTO_DYNAMIC_PATHS
        assert len(_LOTO_DYNAMIC_PATHS) == 7
        for path in _LOTO_DYNAMIC_PATHS:
            loc = f"https://lotoia.fr{path}"
            assert lastmods[loc] == _LOTO_DRAW_DATE, \
                f"{loc} devrait porter la date du tirage Loto, got {lastmods[loc]}"

    def test_em_dynamic_pages_get_em_draw_date_all_langs(self):
        resp = _get_sitemap(loto_date=_LOTO_DRAW_DATE, em_date=_EM_DRAW_DATE)
        lastmods = _lastmod_map(resp.text)

        from config.templates import EM_URLS
        from config import killswitch
        from routes.sitemap import _EM_DYNAMIC_KEYS
        for lang in killswitch.ENABLED_LANGS:
            for key in _EM_DYNAMIC_KEYS:
                url = EM_URLS.get(lang, {}).get(key)
                if url:
                    loc = f"https://lotoia.fr{url}"
                    assert lastmods[loc] == _EM_DRAW_DATE, \
                        f"{loc} ({lang}/{key}) devrait porter la date EM"

    def test_loto_and_em_dates_are_independent(self):
        """Un sitemap, deux dates de tirage distinctes (rythmes différents)."""
        resp = _get_sitemap(loto_date=_LOTO_DRAW_DATE, em_date=_EM_DRAW_DATE)
        lastmods = _lastmod_map(resp.text)
        assert lastmods["https://lotoia.fr/loto/statistiques"] == _LOTO_DRAW_DATE
        assert lastmods["https://lotoia.fr/euromillions/statistiques"] == _EM_DRAW_DATE

    def test_datetime_value_truncated_to_w3c_date(self):
        """Si la colonne devenait DATETIME, [:10] garantit YYYY-MM-DD."""
        resp = _get_sitemap(loto_date="2026-06-08 21:05:00", em_date=_EM_DRAW_DATE)
        lastmods = _lastmod_map(resp.text)
        assert lastmods["https://lotoia.fr/loto"] == "2026-06-08"


# ═══════════════════════════════════════════════
# 3. Pages news → LAST_NEWS_DATE
# ═══════════════════════════════════════════════

class TestNewsLastmod:

    def test_news_fr_and_em_get_last_news_date(self):
        resp = _get_sitemap(loto_date=_LOTO_DRAW_DATE, em_date=_EM_DRAW_DATE)
        lastmods = _lastmod_map(resp.text)

        from config.version import LAST_NEWS_DATE
        assert lastmods["https://lotoia.fr/news"] == LAST_NEWS_DATE

        from config.templates import EM_URLS
        from config import killswitch
        for lang in killswitch.ENABLED_LANGS:
            url = EM_URLS.get(lang, {}).get("news")
            if url:
                assert lastmods[f"https://lotoia.fr{url}"] == LAST_NEWS_DATE, \
                    f"news {lang} devrait porter LAST_NEWS_DATE"


# ═══════════════════════════════════════════════
# 4. Pages éditoriales + launcher → _EDITORIAL_LASTMOD
# ═══════════════════════════════════════════════

class TestEditorialLastmod:

    def test_loto_editorial_pages_get_dict_date(self):
        resp = _get_sitemap(loto_date=_LOTO_DRAW_DATE, em_date=_EM_DRAW_DATE)
        lastmods = _lastmod_map(resp.text)

        from routes.sitemap import _EDITORIAL_LASTMOD
        for path in ("/moteur", "/methodologie", "/loto/intelligence-artificielle",
                     "/hybride", "/a-propos", "/faq"):
            loc = f"https://lotoia.fr{path}"
            assert lastmods[loc] == _EDITORIAL_LASTMOD[path], \
                f"{loc} devrait porter la date éditoriale du dict"
            assert lastmods[loc] != _LOTO_DRAW_DATE

    def test_em_editorial_pages_get_dict_date_all_langs(self):
        resp = _get_sitemap(loto_date=_LOTO_DRAW_DATE, em_date=_EM_DRAW_DATE)
        lastmods = _lastmod_map(resp.text)

        from config.templates import EM_URLS
        from config import killswitch
        from routes.sitemap import _EDITORIAL_LASTMOD
        for lang in killswitch.ENABLED_LANGS:
            for key in ("faq", "a_propos", "moteur", "methodologie", "ia",
                        "hybride_page"):
                url = EM_URLS.get(lang, {}).get(key)
                if url:
                    loc = f"https://lotoia.fr{url}"
                    assert lastmods[loc] == _EDITORIAL_LASTMOD[key], \
                        f"{loc} ({lang}/{key}) devrait porter la date éditoriale"

    def test_launcher_pages_get_launcher_date(self):
        resp = _get_sitemap(loto_date=_LOTO_DRAW_DATE, em_date=_EM_DRAW_DATE)
        lastmods = _lastmod_map(resp.text)

        from config import killswitch
        from routes.sitemap import _EDITORIAL_LASTMOD
        for lc in killswitch.ENABLED_LANGS:
            loc = f"https://lotoia.fr/{lc}"
            assert lastmods[loc] == _EDITORIAL_LASTMOD["launcher"], \
                f"launcher {lc} devrait porter la date launcher"

    def test_editorial_dict_covers_all_non_dynamic_pages(self):
        """Garde-fou : aucune page éditoriale ne retombe silencieusement sur le
        fallback LAST_DEPLOY_DATE faute d'entrée dans le dict."""
        from routes.sitemap import (
            _LOTO_PAGES, _LOTO_DYNAMIC_PATHS, _EM_PAGE_PRIORITY,
            _EM_DYNAMIC_KEYS, _EDITORIAL_LASTMOD,
        )
        for path, _prio, _freq in _LOTO_PAGES:
            if path not in _LOTO_DYNAMIC_PATHS and path != "/news":
                assert path in _EDITORIAL_LASTMOD, f"entrée manquante : {path}"
        for key in _EM_PAGE_PRIORITY:
            if key not in _EM_DYNAMIC_KEYS and key != "news":
                assert key in _EDITORIAL_LASTMOD, f"entrée manquante : {key}"


# ═══════════════════════════════════════════════
# 5. Non-régression structure
# ═══════════════════════════════════════════════

class TestStructureRegression:

    def test_url_count_unchanged(self):
        """Le lot change le lastmod, pas la liste d'URLs (~98)."""
        resp = _get_sitemap(loto_date=_LOTO_DRAW_DATE, em_date=_EM_DRAW_DATE)
        lastmods = _lastmod_map(resp.text)
        assert len(lastmods) >= 90, f"sitemap appauvri : {len(lastmods)} URLs"

    def test_all_lastmod_are_w3c_dates(self):
        resp = _get_sitemap(loto_date=_LOTO_DRAW_DATE, em_date=_EM_DRAW_DATE)
        lastmods = _lastmod_map(resp.text)
        for loc, lm in lastmods.items():
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", lm), \
                f"lastmod non-W3C sur {loc}: {lm}"

    def test_hreflang_alternates_intact_on_launcher(self):
        """7 alternates (6 langues + x-default) toujours présents sur /fr."""
        resp = _get_sitemap(loto_date=_LOTO_DRAW_DATE, em_date=_EM_DRAW_DATE)
        root = ElementTree.fromstring(resp.text)
        for url_el in root.findall(".//sm:url", _NS):
            if url_el.find("sm:loc", _NS).text == "https://lotoia.fr/fr":
                hreflangs = {a.get("hreflang")
                             for a in url_el.findall("xhtml:link", _NS)}
                assert "x-default" in hreflangs
                for lang in ("fr", "en", "es", "pt", "de", "nl"):
                    assert lang in hreflangs
                break
        else:
            raise AssertionError("URL launcher /fr absente du sitemap")

    def test_every_url_has_changefreq_and_priority(self):
        resp = _get_sitemap(loto_date=_LOTO_DRAW_DATE, em_date=_EM_DRAW_DATE)
        root = ElementTree.fromstring(resp.text)
        for url_el in root.findall(".//sm:url", _NS):
            loc = url_el.find("sm:loc", _NS).text
            assert url_el.find("sm:changefreq", _NS) is not None, loc
            assert url_el.find("sm:priority", _NS) is not None, loc
