"""
Tests — Lot redirection (24/10/2026).

A+ : GET / et les 11 redirections legacy conservent la query string.
B2 : repli FR si Accept-Language absent / vide / espaces, EN s'il est présent sans langue supportée.
C  : x-default du launcher → /fr, même constante pour la page et le sitemap.
302 de / : Cache-Control "private, no-cache" + Vary: Accept-Language.
(T9 golden des pages intouchables : tests/test_seo_golden_intouchables.py)
"""
import os
import re
from contextlib import asynccontextmanager
from unittest.mock import patch, AsyncMock
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})

BASE = "https://lotoia.fr"
LANGS = ["fr", "en", "es", "pt", "de", "nl"]
UTM = "utm_source=t&utm_medium=m"

_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "xhtml": "http://www.w3.org/1999/xhtml",
}


def _async_cm_conn(cursor):
    @asynccontextmanager
    async def _cm():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn
    return _cm


def _make_cursor():
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=None)
    cursor.fetchall = AsyncMock(return_value=[])
    cursor.close = AsyncMock()
    return cursor


def _get_client():
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def client():
    return _get_client()


def _root(client, accept_lang=None, query="", **headers):
    if accept_lang is not None:
        headers["accept-language"] = accept_lang
    url = f"/?{query}" if query else "/"
    return client.get(url, headers=headers, follow_redirects=False)


# =========================================================================
# A+ — GET / conserve la query string (T1, T2, T3)
# =========================================================================

class TestRootQueryString:

    def test_utm_kept_fr(self, client):
        """T1 — /?utm_source=a&utm_medium=b (AL fr) → /fr?utm_source=a&utm_medium=b."""
        resp = _root(client, "fr-FR,fr;q=0.9", query="utm_source=a&utm_medium=b")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/fr?utm_source=a&utm_medium=b"

    @pytest.mark.parametrize("lang", LANGS)
    def test_utm_kept_all_langs(self, client, lang):
        """T2 — query conservée pour chacune des 6 langues."""
        resp = _root(client, f"{lang};q=1.0", query=UTM)
        assert resp.status_code == 302
        assert resp.headers["location"] == f"/{lang}?{UTM}"

    def test_no_query_no_trailing_question_mark(self, client):
        """T3 — sans query, Location sans « ? » final."""
        resp = _root(client, "fr-FR")
        assert resp.headers["location"] == "/fr"


# =========================================================================
# B2 — repli de langue (T4, T5, T6)
# =========================================================================

class TestRootFallbackB2:

    def test_no_accept_language_goes_fr(self, client):
        """T4 — ni CF-IPCountry ni Accept-Language → /fr."""
        resp = _root(client)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/fr"

    @pytest.mark.parametrize("accept_lang", ["", "   "])
    def test_empty_accept_language_goes_fr(self, client, accept_lang):
        """T4 — Accept-Language vide ou espaces seuls → /fr."""
        resp = _root(client, accept_lang)
        assert resp.headers["location"] == "/fr"

    @pytest.mark.parametrize("accept_lang", ["it-IT", "zh-CN,zh", "ja"])
    def test_unsupported_language_stays_en(self, client, accept_lang):
        """T5 — Accept-Language présent sans langue supportée → /en (inchangé)."""
        resp = _root(client, accept_lang)
        assert resp.headers["location"] == "/en"

    def test_real_english_visitor_stays_en(self, client):
        """T5 — visiteur EN réel → /en (inchangé)."""
        resp = _root(client, "en-US,en;q=0.9")
        assert resp.headers["location"] == "/en"

    def test_googlebot_without_accept_language_goes_fr(self, client):
        """T6 — UA Googlebot sans Accept-Language → /fr (aucun traitement par user-agent)."""
        ua = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        resp = _root(client, **{"user-agent": ua})
        assert resp.status_code == 302
        assert resp.headers["location"] == "/fr"


# =========================================================================
# En-têtes du 302 (T8)
# =========================================================================

class TestRootHeaders:

    @pytest.mark.parametrize("accept_lang", [None, "fr-FR", "en-US", "it-IT"])
    def test_cache_control_and_vary(self, client, accept_lang):
        """T8 — 302 de / : Cache-Control private, no-cache + Vary: Accept-Language."""
        resp = _root(client, accept_lang)
        assert resp.status_code == 302
        assert resp.headers.get("cache-control") == "private, no-cache"
        assert "Accept-Language" in resp.headers.get("vary", "")


# =========================================================================
# C — x-default launcher : page == sitemap == /fr (T7)
# =========================================================================

class TestLauncherXDefaultConsistency:

    def test_constant_is_fr(self):
        from routes.launcher import LAUNCHER_X_DEFAULT_URL
        assert LAUNCHER_X_DEFAULT_URL == f"{BASE}/fr"

    @pytest.mark.parametrize("lang", LANGS)
    def test_page_x_default_is_fr(self, client, lang):
        resp = client.get(f"/{lang}")
        found = re.findall(r'hreflang="x-default" href="([^"]+)"', resp.text)
        assert found == [f"{BASE}/fr"], f"/{lang}: x-default = {found}"

    def test_sitemap_launcher_x_default_matches_page(self, client):
        """T7 — x-default des 6 blocs launcher du sitemap == x-default des pages."""
        with patch("db_cloudsql.get_connection", _async_cm_conn(_make_cursor())), \
             patch("routes.sitemap._fetch_last_draw_date_loto", AsyncMock(return_value=None)), \
             patch("routes.sitemap._fetch_last_draw_date_em", AsyncMock(return_value=None)):
            resp = client.get("/sitemap.xml")
        assert resp.status_code == 200
        root = ElementTree.fromstring(resp.text)
        launcher_locs = {f"{BASE}/{lc}" for lc in LANGS}
        seen = set()
        for url_el in root.findall(".//sm:url", _NS):
            loc = url_el.find("sm:loc", _NS).text
            if loc not in launcher_locs:
                continue
            seen.add(loc)
            xdef = [a.get("href") for a in url_el.findall("xhtml:link", _NS)
                    if a.get("hreflang") == "x-default"]
            assert xdef == [f"{BASE}/fr"], f"sitemap {loc}: x-default = {xdef}"
        assert seen == launcher_locs


# =========================================================================
# A+ — 11 redirections legacy conservent la query (T11)
# =========================================================================

_LEGACY_301 = [
    ("/analyse", "/loto/analyse"),
    ("/statistiques", "/loto/statistiques"),
    ("/simulateur", "/loto/analyse"),
    ("/exploration", "/loto"),
    ("/loto/exploration", "/loto"),
    ("/loto/accueil", "/accueil"),
    ("/loto/historique", "/historique"),
    ("/loto/chatbot", "/loto"),
    ("/loto/pronostics", "/loto"),
    ("/euromillions/accueil", "/euromillions"),
    ("/euromillions/chatbot", "/euromillions"),
]


class TestLegacyRedirectsKeepQuery:

    @pytest.mark.parametrize("path,target", _LEGACY_301)
    def test_query_kept(self, client, path, target):
        resp = client.get(f"{path}?{UTM}", follow_redirects=False)
        assert resp.status_code == 301
        assert resp.headers["location"] == f"{target}?{UTM}"

    @pytest.mark.parametrize("path,target", _LEGACY_301)
    def test_no_query_unchanged(self, client, path, target):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 301
        assert resp.headers["location"] == target


# =========================================================================
# Comportement déjà correct, désormais couvert (T12, T13)
# =========================================================================

class TestOtherRedirectsKeepQuery:

    def test_trailing_slash_keeps_query(self, client):
        """T12 — slash final : query conservée."""
        resp = client.get(f"/euromillions/generateur/?{UTM}", follow_redirects=False)
        assert resp.status_code == 301
        assert resp.headers["location"] == f"/euromillions/generateur?{UTM}"

    def test_ui_html_keeps_query(self, client):
        """T12 — /ui/*.html : query conservée."""
        resp = client.get(f"/ui/loto.html?{UTM}", follow_redirects=False)
        assert resp.status_code == 301
        assert resp.headers["location"] == f"/loto?{UTM}"

    def test_ui_launcher_chain_keeps_query(self, client):
        """T13 — /ui/launcher.html?x=1 → /?x=1 → /fr?x=1 (2 sauts, query au bout)."""
        first = client.get("/ui/launcher.html?x=1", follow_redirects=False)
        assert first.status_code == 301
        assert first.headers["location"] == "/?x=1"
        second = client.get(first.headers["location"], headers={"accept-language": "fr-FR"},
                            follow_redirects=False)
        assert second.status_code == 302
        assert second.headers["location"] == "/fr?x=1"
