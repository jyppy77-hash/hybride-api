"""
Tests Cycle 2A Phase 1B (1.6.052) — bloc « Statistiques du Loto : les chiffres clés »
rendu serveur sur /loto/statistiques.

Couvre : snapshot source unique (tri, ex-aequo, cache indexé sur la période), cohérence
page ↔ /api/stats/top-flop, forme API inchangée (golden capturé AVANT modification),
fallbacks (DB down / timeout / cache KO → 200), JSON-LD (dateModified, temporalCoverage),
ETag / Last-Modified / 304 (W/, multi-valeurs, fallback par version), textes exacts,
égalité à la 5e place, non-régression headers middleware et périmètre SEO interdit.
"""

import asyncio
import hashlib
import json
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from email.utils import formatdate
from unittest.mock import AsyncMock, patch
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

import services.cache as cache_mod
import services.loto_key_figures as kf
from services import stats_service


# ── Patches (pattern test_seo_indexation.py) ─────────────────────────────

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})


def _get_client():
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


# ── Jeu de données : fréquences live prod au 06/10/2026 (1 083 tirages) ──

LIVE_FREQ = {
    1: 93, 2: 98, 3: 120, 4: 109, 5: 121, 6: 121, 7: 119, 8: 112, 9: 113, 10: 113,
    11: 97, 12: 114, 13: 119, 14: 97, 15: 124, 16: 108, 17: 111, 18: 104, 19: 107, 20: 99,
    21: 108, 22: 121, 23: 104, 24: 122, 25: 109, 26: 119, 27: 103, 28: 116, 29: 109, 30: 128,
    31: 132, 32: 114, 33: 93, 34: 110, 35: 112, 36: 114, 37: 103, 38: 121, 39: 105, 40: 100,
    41: 115, 42: 112, 43: 87, 44: 109, 45: 112, 46: 108, 47: 111, 48: 108, 49: 111,
}
LIVE_TOTAL = 1083
FIRST = "2019-11-06"
LAST = "2026-10-05"

# Golden capturé AVANT modification (ancien unified_stats_top_flop, même LIVE_FREQ)
GOLDEN_TOP_ORDER = [31, 30, 15, 24, 5, 6, 22, 38, 3, 7, 13, 26, 28, 41, 12, 32, 36, 9, 10, 8, 35,
                    42, 45, 17, 47, 49, 34, 4, 25, 29, 44, 16, 21, 46, 48, 19, 39, 18, 23, 27, 37,
                    40, 20, 2, 11, 14, 1, 33, 43]
GOLDEN_FLOP_ORDER = [43, 1, 33, 11, 14, 2, 20, 40, 27, 37, 18, 23, 39, 19, 16, 21, 46, 48, 4, 25,
                     29, 44, 34, 17, 47, 49, 8, 35, 42, 45, 9, 10, 12, 32, 36, 41, 28, 7, 13, 26,
                     3, 5, 6, 22, 38, 24, 15, 30, 31]

NOMINAL_INTRO = (
    "Ces statistiques portent sur 1 083 tirages du Loto analysés depuis le 6 novembre 2019 : "
    "le numéro 31 est le plus sorti (132 fois) et le numéro 43 le moins sorti (87 fois). "
    "Données mises à jour après le tirage du lundi 5 octobre 2026."
)

_RE_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_RE_ROW = re.compile(r'<tr><td class="rank">\d+</td><th scope="row" class="num (hot|cold)">(\d+)</th>'
                     r'<td>(\d+)</td>')


class _FakeCursor:
    """Curseur DB minimal : répond selon la requête SQL exécutée."""

    def __init__(self, freq=None, total=LIVE_TOTAL, first=FIRST, last=LAST):
        self.freq = LIVE_FREQ if freq is None else freq
        self.total, self.first, self.last = total, first, last
        self.sql = ""
        self.calls = []

    async def execute(self, sql, params=None):
        self.sql = sql
        self.calls.append(sql)

    async def fetchone(self):
        if "MAX(date_de_tirage) AS last_draw" in self.sql:
            if not self.total:
                return {"total": 0, "first_draw": None, "last_draw": None}
            return {"total": self.total, "first_draw": date.fromisoformat(self.first),
                    "last_draw": date.fromisoformat(self.last)}
        if "ORDER BY date_de_tirage DESC" in self.sql and "LIMIT 1" in self.sql:
            return {"date_de_tirage": date.fromisoformat(self.last)}
        return None

    async def fetchall(self):
        if "boule_1 as num" in self.sql:
            return [{"num": n, "freq": c} for n, c in sorted(self.freq.items())]
        return []

    async def close(self):
        pass

    def count(self, needle):
        return sum(1 for s in self.calls if needle in s)


def _cm(cursor):
    @asynccontextmanager
    async def _conn_cm():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn
    return _conn_cm


def _cm_raising():
    @asynccontextmanager
    async def _conn_cm():
        raise RuntimeError("Cloud SQL down")
        yield  # pragma: no cover
    return _conn_cm


def _run(coro):
    """Boucle locale fermée après usage. PAS asyncio.run() : il détache la boucle du thread
    principal et casse les tests qui utilisent asyncio.get_event_loop() (ordre d'exécution)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _real_snapshot(cursor=None):
    """Snapshot via le VRAI code (get_frequency_snapshot) sur un curseur simulé."""
    cursor = cursor or _FakeCursor()
    with patch("db_cloudsql.get_connection", _cm(cursor)):
        return _run(stats_service.get_frequency_snapshot())


def _freq(**changes):
    """LIVE_FREQ modifié : _freq(n30=132) → numéro 30 à 132 sorties."""
    f = dict(LIVE_FREQ)
    for k, v in changes.items():
        f[int(k[1:])] = v
    return f


def _rows(html, css):
    return [(int(n), int(c)) for k, n, c in _RE_ROW.findall(html) if k == css]


def _ld_blocks(html):
    return [json.loads(b) for b in _RE_LD.findall(html)]


def _middleware_last_modified(day: str) -> str:
    stamp = time.mktime(datetime.strptime(day, "%Y-%m-%d").timetuple())
    return formatdate(timeval=stamp, localtime=False, usegmt=True)


def _version_etag(path: str) -> str:
    from config.version import APP_VERSION
    return '"%s"' % hashlib.md5(f"{APP_VERSION}:{path}".encode()).hexdigest()


@pytest.fixture(autouse=True)
def _reset_state():
    cache_mod._mem_cache.clear()
    kf._unavailable_until = 0.0
    yield
    cache_mod._mem_cache.clear()
    kf._unavailable_until = 0.0


@pytest.fixture(scope="module")
def client():
    return _get_client()


def _get(client, path, cursor=None, **kwargs):
    cursor = cursor or _FakeCursor()
    with patch("db_cloudsql.get_connection", _cm(cursor)), \
            patch("engine.db.get_connection", _cm(cursor)):
        return client.get(path, **kwargs)


# ═══════════════════════════════════════════════
# 1-4. Snapshot : tri, cache, période
# ═══════════════════════════════════════════════

class TestSnapshot:

    def test_snapshot_sort_and_tiebreak(self):
        """1 : top (count DESC, number ASC) / flop (count ASC, number ASC) = golden avant modif."""
        snap = _real_snapshot()
        assert [d["number"] for d in snap["top"]] == GOLDEN_TOP_ORDER
        assert [d["number"] for d in snap["flop"]] == GOLDEN_FLOP_ORDER
        # ex-aequo 121 : 5, 6, 22, 38 dans l'ordre croissant
        assert [d["number"] for d in snap["top"][4:8]] == [5, 6, 22, 38]
        assert snap["total_draws"] == LIVE_TOTAL
        assert snap["first_draw"] == FIRST and snap["last_draw"] == LAST

    def test_snapshot_missing_number_counts_zero(self):
        f = dict(LIVE_FREQ)
        del f[43]
        snap = _real_snapshot(_FakeCursor(freq=f))
        assert snap["flop"][0] == {"number": 43, "count": 0}
        assert len(snap["top"]) == 49

    def test_snapshot_cache_key_includes_last_draw(self):
        """2 : même dernier tirage → 1 seul calcul ; nouveau tirage → recalcul."""
        cur = _FakeCursor()
        _real_snapshot(cur)
        _real_snapshot(cur)
        assert cur.count("boule_1 as num") == 1
        cache_mod._mem_cache.pop("snapshot:meta")  # expiration TTL méta simulée
        cur2 = _FakeCursor(last="2026-10-07", total=LIVE_TOTAL + 1, freq=_freq(n43=88))
        snap = _real_snapshot(cur2)
        assert cur2.count("boule_1 as num") == 1
        assert snap["last_draw"] == "2026-10-07"
        assert snap["flop"][0] == {"number": 43, "count": 88}

    def test_snapshot_cache_key_changes_with_first_draw(self):
        """Complément 6 : glissement de fenêtre (first_draw) → nouvelle clé → recalcul."""
        cur = _FakeCursor()
        _real_snapshot(cur)
        key_before = stats_service._svc._snapshot_key({"first_draw": FIRST, "last_draw": LAST,
                                                       "total_draws": LIVE_TOTAL})
        assert key_before == f"snapshot:freq:{FIRST}:{LAST}:{LIVE_TOTAL}"
        assert key_before in cache_mod._mem_cache
        cache_mod._mem_cache.pop("snapshot:meta")
        cur2 = _FakeCursor(first="2019-11-09")
        snap = _real_snapshot(cur2)
        assert cur2.count("boule_1 as num") == 1
        assert snap["first_draw"] == "2019-11-09"
        assert f"snapshot:freq:2019-11-09:{LAST}:{LIVE_TOTAL}" in cache_mod._mem_cache

    def test_snapshot_ignores_stale_legacy_freq_cache(self):
        """3 : un freq:principal:None périmé n'est pas lu (et il est rafraîchi)."""
        _run(cache_mod.cache_set("freq:principal:None", {n: 999 for n in range(1, 50)}))
        snap = _real_snapshot()
        assert snap["top"][0] == {"number": 31, "count": 132}
        refreshed = _run(cache_mod.cache_get("freq:principal:None"))
        assert refreshed[31] == 132

    def test_snapshot_meta_ttl_300_and_hit_without_sql(self):
        """4 : méta en cache 300 s ; snapshot complet servi sans aucune requête SQL."""
        cur = _FakeCursor()
        _real_snapshot(cur)
        expires_at, meta = cache_mod._mem_cache["snapshot:meta"]
        assert meta == {"first_draw": FIRST, "last_draw": LAST, "total_draws": LIVE_TOTAL}
        assert 290 < expires_at - time.monotonic() <= 300
        n_calls = len(cur.calls)
        _real_snapshot(cur)
        assert len(cur.calls) == n_calls

    def test_snapshot_empty_table_raises(self):
        with pytest.raises(LookupError):
            _real_snapshot(_FakeCursor(total=0))


# ═══════════════════════════════════════════════
# 5-6. Rendu page + cohérence page ↔ API
# ═══════════════════════════════════════════════

class TestPageRender:

    def test_page_renders_key_figures(self, client):
        """5 : top/flop 5, total, dates FR, pourcentages."""
        resp = _get(client, "/loto/statistiques")
        assert resp.status_code == 200
        html = resp.text
        assert _rows(html, "hot") == [(31, 132), (30, 128), (15, 124), (24, 122), (5, 121)]
        assert _rows(html, "cold") == [(43, 87), (1, 93), (33, 93), (11, 97), (14, 97)]
        assert "<dt>Tirages analysés</dt><dd>1 083</dd>" in html
        assert '<time datetime="2026-10-05">lundi 5 octobre 2026</time>' in html
        assert "<td>12,2 %</td>" in html and "<td>8,0 %</td>" in html
        assert "Fréquence théorique : 10,2 % (5/49)" in html

    def test_block_placed_before_tabs(self, client):
        html = _get(client, "/loto/statistiques").text
        assert html.index('<section class="key-figures"') < html.index('<div class="tabs-card">')
        assert html.index("<h1>") < html.index('<section class="key-figures"')

    def test_page_and_api_same_top5_flop5(self, client):
        """6 : une seule source → top 5 / flop 5 identiques page et API."""
        cur = _FakeCursor(freq=_freq(n30=132, n43=93))
        html = _get(client, "/loto/statistiques", cursor=cur).text
        api = _get(client, "/api/stats/top-flop", cursor=cur).json()
        assert _rows(html, "hot") == [(d["number"], d["count"]) for d in api["top"][:5]]
        assert _rows(html, "cold") == [(d["number"], d["count"]) for d in api["flop"][:5]]
        assert cur.count("boule_1 as num") == 1  # page + API servies par le même snapshot

    def test_canonical_preserved(self, client):
        html = _get(client, "/loto/statistiques").text
        assert '<link rel="canonical" href="https://lotoia.fr/loto/statistiques">' in html


# ═══════════════════════════════════════════════
# 7. API /api/stats/top-flop : forme inchangée
# ═══════════════════════════════════════════════

class TestApiTopFlop:

    def test_api_loto_shape_identical_to_before(self, client):
        """7 : mêmes clés (+ last_draw), mêmes clés/types d'éléments, même ordre que le golden."""
        resp = _get(client, "/api/stats/top-flop")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) - {"last_draw"} == {"success", "top", "flop"}
        assert body["success"] is True and body["last_draw"] == LAST
        for key in ("top", "flop"):
            assert len(body[key]) == 49
            for item in body[key]:
                assert set(item) == {"number", "count"}
                assert type(item["number"]) is int and type(item["count"]) is int
        assert [d["number"] for d in body["top"]] == GOLDEN_TOP_ORDER
        assert [d["number"] for d in body["flop"]] == GOLDEN_FLOP_ORDER
        assert all(d["count"] == LIVE_FREQ[d["number"]] for d in body["top"])

    def test_api_loto_uses_snapshot(self, client):
        spy = AsyncMock(return_value={"first_draw": FIRST, "last_draw": LAST, "total_draws": 1,
                                      "top": [{"number": 7, "count": 1}],
                                      "flop": [{"number": 7, "count": 1}]})
        with patch("services.stats_service.get_frequency_snapshot", spy):
            body = _get(client, "/api/stats/top-flop").json()
        spy.assert_awaited_once()
        assert body["top"] == [{"number": 7, "count": 1}]

    def test_api_loto_db_error_still_500_json(self, client):
        with patch("db_cloudsql.get_connection", _cm_raising()):
            resp = client.get("/api/stats/top-flop")
        assert resp.status_code == 500
        assert resp.json()["success"] is False

    def test_api_em_branch_unchanged(self, client):
        boom = AsyncMock(side_effect=AssertionError("snapshot Loto appelé pour EM"))
        with patch("services.stats_service.get_frequency_snapshot", boom):
            resp = _get(client, "/api/euromillions/stats/top-flop")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"success", "top_boules", "flop_boules", "top_etoiles", "flop_etoiles"}
        assert len(body["top_boules"]) == 50 and len(body["top_etoiles"]) == 12
        boom.assert_not_awaited()


# ═══════════════════════════════════════════════
# 8-11. Fallbacks — jamais de 500
# ═══════════════════════════════════════════════

def _assert_fallback_page(resp):
    assert resp.status_code == 200
    html = resp.text
    assert 'class="key-figures"' not in html
    assert "__KEY_FIGURES__" not in html
    assert "__DATA_DATE_MODIFIED__" not in html
    blocks = _ld_blocks(html)
    dataset = next(b for b in blocks if b["@type"] == "Dataset")
    assert "dateModified" not in dataset
    assert dataset["temporalCoverage"] == "2019-11-06/.."
    assert '<div class="tabs-card">' in html  # reste de la page intact
    assert resp.headers["etag"] == _version_etag("/loto/statistiques")


class TestFallback:

    def test_db_down_returns_200_without_block(self, client):
        """8"""
        with patch("db_cloudsql.get_connection", _cm_raising()):
            resp = client.get("/loto/statistiques")
        _assert_fallback_page(resp)

    def test_timeout_returns_200_without_block(self, client):
        """9"""
        async def _slow():
            await asyncio.sleep(1)

        with patch.object(kf, "_SNAPSHOT_TIMEOUT_S", 0.01), \
                patch("services.loto_key_figures.get_frequency_snapshot", _slow):
            resp = client.get("/loto/statistiques")
        _assert_fallback_page(resp)

    def test_cache_backend_error_returns_200(self, client):
        """10 : panne du cache (Redis/in-memory) → page servie quand même."""
        with patch("services.base_stats.cache_get", AsyncMock(side_effect=ConnectionError("redis"))):
            resp = _get(client, "/loto/statistiques")
        _assert_fallback_page(resp)

    def test_empty_table_returns_200(self, client):
        _assert_fallback_page(_get(client, "/loto/statistiques", cursor=_FakeCursor(total=0)))

    def test_negative_cache_skips_db_for_30s(self):
        spy = AsyncMock(side_effect=RuntimeError("down"))
        with patch("services.loto_key_figures.get_frequency_snapshot", spy):
            assert _run(kf.get_key_figures_snapshot()) is None
            assert _run(kf.get_key_figures_snapshot()) is None
        assert spy.await_count == 1
        assert 29 < kf._unavailable_until - time.monotonic() <= 30

    def test_no_placeholder_leak_nominal(self, client):
        """11"""
        html = _get(client, "/loto/statistiques").text
        assert "__KEY_FIGURES__" not in html
        assert "__DATA_DATE_MODIFIED__" not in html
        assert not re.search(r"__[A-Z_]+__", "".join(_RE_LD.findall(html)))


# ═══════════════════════════════════════════════
# 12-13. JSON-LD : dateModified honnête + temporalCoverage + sitemap
# ═══════════════════════════════════════════════

class TestJsonLd:

    def test_jsonld_valid_and_date_modified_is_last_draw(self, client):
        """12 : JSON valide, dateModified = dernier tirage (jamais aujourd'hui)."""
        resp = _get(client, "/loto/statistiques", cursor=_FakeCursor(last="2024-03-02"))
        blocks = _ld_blocks(resp.text)
        assert len(blocks) == 2
        dataset = next(b for b in blocks if b["@type"] == "Dataset")
        assert dataset["dateModified"] == "2024-03-02"
        assert dataset["dateModified"] != date.today().isoformat()
        assert date.fromisoformat(dataset["dateModified"])  # ISO 8601
        assert dataset["temporalCoverage"] == "2019-11-06/2024-03-02"

    def test_date_modified_matches_sitemap_lastmod(self, client):
        """13 : dateModified == <lastmod> de /loto/statistiques dans le sitemap."""
        cur = _FakeCursor(last="2026-10-03")
        dataset = next(b for b in _ld_blocks(_get(client, "/loto/statistiques", cursor=cur).text)
                       if b["@type"] == "Dataset")
        sm = _get(client, "/sitemap.xml", cursor=cur)
        root = ElementTree.fromstring(sm.content)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        lastmod = next(u.find("sm:lastmod", ns).text for u in root.findall("sm:url", ns)
                       if u.find("sm:loc", ns).text == "https://lotoia.fr/loto/statistiques")
        assert dataset["dateModified"] == lastmod == "2026-10-03"

    def test_first_draw_dynamic(self, client):
        """Complément 6 : first_draw ≠ 2019-11-06 → intro, ligne Période, temporalCoverage."""
        html = _get(client, "/loto/statistiques", cursor=_FakeCursor(first="2020-01-04")).text
        assert "tirages du Loto analysés depuis le 4 janvier 2020 :" in html
        assert '<dt>Période</dt><dd>depuis le <time datetime="2020-01-04">4 janvier 2020</time></dd>' in html
        dataset = next(b for b in _ld_blocks(html) if b["@type"] == "Dataset")
        assert dataset["temporalCoverage"] == f"2020-01-04/{LAST}"
        block = re.search(r'<section class="key-figures".*?</section>', html, re.S).group(0)
        assert "2019" not in block


# ═══════════════════════════════════════════════
# 14, 18, 19. ETag / Last-Modified / 304
# ═══════════════════════════════════════════════

class TestConditionalGet:

    def test_headers_data_dated(self, client):
        resp = _get(client, "/loto/statistiques")
        snap = {"first_draw": FIRST, "last_draw": LAST, "total_draws": LIVE_TOTAL}
        assert resp.headers["etag"] == kf.page_etag(snap) != _version_etag("/loto/statistiques")
        assert resp.headers["last-modified"] == "Mon, 05 Oct 2026 00:00:00 GMT"
        assert resp.headers["cache-control"] == "private, max-age=3600"

    def test_304_then_new_draw_gives_200(self, client):
        """14 : même données → 304 ; nouveau tirage → 200 + nouvel ETag."""
        etag = _get(client, "/loto/statistiques").headers["etag"]
        assert _get(client, "/loto/statistiques", headers={"If-None-Match": etag}).status_code == 304
        cache_mod._mem_cache.clear()
        resp = _get(client, "/loto/statistiques", cursor=_FakeCursor(last="2026-10-07", total=1084),
                    headers={"If-None-Match": etag})
        assert resp.status_code == 200
        assert resp.headers["etag"] != etag
        assert resp.headers["last-modified"] == "Wed, 07 Oct 2026 00:00:00 GMT"

    @pytest.mark.parametrize("fmt", ["{e}", "W/{e}", '"zzz", W/{e}', '"a","b" ,{e}', "*"])
    def test_if_none_match_weak_and_multi(self, client, fmt):
        """18 : W/ et listes multi-valeurs → 304."""
        etag = _get(client, "/loto/statistiques").headers["etag"]
        resp = _get(client, "/loto/statistiques", headers={"If-None-Match": fmt.format(e=etag)})
        assert resp.status_code == 304

    def test_if_none_match_mismatch_gives_200(self, client):
        resp = _get(client, "/loto/statistiques", headers={"If-None-Match": 'W/"nope", "other"'})
        assert resp.status_code == 200

    def test_304_carries_headers_no_body(self, client):
        """19 : 304 = ETag + Last-Modified + Cache-Control, sans corps."""
        r200 = _get(client, "/loto/statistiques")
        r304 = _get(client, "/loto/statistiques", headers={"If-None-Match": r200.headers["etag"]})
        assert r304.status_code == 304
        assert r304.content == b""
        for h in ("etag", "last-modified", "cache-control"):
            assert r304.headers[h] == r200.headers[h]

    def test_fallback_304_on_version_etag(self, client):
        """Complément 1 : snapshot None → 304 sur l'ETag par version (W/ et multi compris)."""
        import main as main_mod
        etag = _version_etag("/loto/statistiques")
        with patch("db_cloudsql.get_connection", _cm_raising()):
            r200 = client.get("/loto/statistiques")
            assert r200.headers["etag"] == etag
            assert r200.headers["last-modified"] == _middleware_last_modified(main_mod.LAST_DEPLOY_DATE)
            for value in (etag, "W/" + etag, f'"x", W/{etag}'):
                r304 = client.get("/loto/statistiques", headers={"If-None-Match": value})
                assert r304.status_code == 304
                assert r304.headers["etag"] == etag
                assert r304.headers["last-modified"] == r200.headers["last-modified"]
                assert r304.headers["cache-control"] == "private, max-age=3600"

    @pytest.mark.parametrize("header,expected", [
        (None, False), ("", False), ('"abc"', True), ('W/"abc"', True), ('"x", W/"abc"', True),
        ("*", True), ('"abcd"', False), ('W/"x"', False),
    ])
    def test_if_none_match_hit_unit(self, header, expected):
        assert kf.if_none_match_hit(header, '"abc"') is expected


# ═══════════════════════════════════════════════
# Non-régression headers middleware (/loto, /news, /loto/analyse)
# ═══════════════════════════════════════════════

class TestMiddlewareHeadersNonRegression:
    """Ancré AVANT modification (scratch test_headers_before.py, 3/3 verts sur 1.6.051)."""

    @pytest.mark.parametrize("path", ["/loto", "/news", "/loto/analyse"])
    def test_etag_lastmod_304_unchanged(self, client, path):
        import main as main_mod
        etag = _version_etag(path)
        r = _get(client, path)
        assert r.status_code == 200
        assert r.headers["etag"] == etag
        assert r.headers["last-modified"] == _middleware_last_modified(main_mod.LAST_DEPLOY_DATE)
        assert r.headers["cache-control"] == "private, max-age=3600"
        r2 = _get(client, path, headers={"If-None-Match": etag})
        assert r2.status_code == 304 and r2.headers["etag"] == etag
        # middleware : égalité stricte inchangée (W/ non reconnu)
        assert _get(client, path, headers={"If-None-Match": "W/" + etag}).status_code == 200

    def test_loto_analyse_canonical_unchanged(self, client):
        html = _get(client, "/loto/analyse").text
        assert '<link rel="canonical" href="https://lotoia.fr/loto/analyse">' in html

    def test_data_dated_routes_scope(self):
        import main as main_mod
        assert main_mod._DATA_DATED_ROUTES == frozenset({"/loto/statistiques"})


# ═══════════════════════════════════════════════
# 15, 21. Textes exacts : H2 + intro (ex-aequo)
# ═══════════════════════════════════════════════

class TestTexts:

    def test_h2_exact(self):
        html = kf.build_key_figures_html(_real_snapshot())
        assert '<h2 id="key-figures-title">Statistiques du Loto : les chiffres clés</h2>' in html

    def test_intro_nominal_exact(self):
        """21 : cas nominal."""
        assert kf.build_intro(_real_snapshot()) == NOMINAL_INTRO

    @pytest.mark.parametrize("freq,top_clause,flop_clause", [
        (_freq(n30=132), "les numéros 30 et 31 sont les plus sortis (132 fois chacun)",
         "le numéro 43 le moins sorti (87 fois)"),
        (_freq(n30=132, n15=132), "les numéros 15, 30 et 31 sont les plus sortis (132 fois chacun)",
         "le numéro 43 le moins sorti (87 fois)"),
        (_freq(n30=132, n15=132, n24=132), "plusieurs numéros sont à égalité en tête (132 fois)",
         "le numéro 43 le moins sorti (87 fois)"),
        (_freq(n1=87), "le numéro 31 est le plus sorti (132 fois)",
         "les numéros 1 et 43 sont les moins sortis (87 fois chacun)"),
        (_freq(n1=87, n33=87), "le numéro 31 est le plus sorti (132 fois)",
         "les numéros 1, 33 et 43 sont les moins sortis (87 fois chacun)"),
        (_freq(n1=87, n33=87, n11=87), "le numéro 31 est le plus sorti (132 fois)",
         "plusieurs numéros sont à égalité en queue (87 fois)"),
    ])
    def test_intro_ties(self, freq, top_clause, flop_clause):
        """15 + 21 : ex-aequo 2 / 3 / >3, top et flop."""
        intro = kf.build_intro(_real_snapshot(_FakeCursor(freq=freq)))
        assert intro == (
            "Ces statistiques portent sur 1 083 tirages du Loto analysés depuis le "
            f"6 novembre 2019 : {top_clause} et {flop_clause}. "
            "Données mises à jour après le tirage du lundi 5 octobre 2026."
        )

    def test_note_and_link_unchanged(self):
        html = kf.build_key_figures_html(_real_snapshot())
        assert ("Données descriptives, sans valeur prédictive. "
                '<a href="/loto/numeros-les-plus-sortis">Voir le classement complet des 49 numéros</a>') in html


# ═══════════════════════════════════════════════
# 20. Structure des tableaux
# ═══════════════════════════════════════════════

class TestTableStructure:

    def test_tables_semantics(self):
        """20 : caption, th scope=col, th scope=row (num hot/cold), aucune div à la place."""
        html = kf.build_key_figures_html(_real_snapshot())
        assert html.count('<table class="freq-table">') == 2
        assert "<caption>Top 5 des numéros les plus sortis</caption>" in html
        assert "<caption>Flop 5 des numéros les moins sortis</caption>" in html
        assert html.count("<thead>") == 2
        assert html.count('<th scope="col">') == 8
        assert html.count('<th scope="row" class="num hot">') == 5
        assert html.count('<th scope="row" class="num cold">') == 5
        assert html.count("<tr><td class=\"rank\">") == 10
        assert "<dl class=\"key-figures-meta\">" in html


# ═══════════════════════════════════════════════
# 22. Égalité à la 5e place
# ═══════════════════════════════════════════════

class TestFifthPlaceTie:

    @staticmethod
    def _cols(freq):
        html = kf.build_key_figures_html(_real_snapshot(_FakeCursor(freq=freq)))
        top, flop = html.split('<div class="key-figures-col">')[1:3]
        return top, flop

    def test_top_tie_plural_live(self):
        top, flop = self._cols(LIVE_FREQ)
        assert len(_rows(top, "hot")) == 5
        assert '<p class="key-figures-tie">À égalité avec le 5e (121 sorties) : numéros 6, 22, 38.</p>' in top
        assert "key-figures-tie" not in flop

    def test_top_tie_singular(self):
        top, _ = self._cols(_freq(n22=120, n38=120))
        assert '<p class="key-figures-tie">À égalité avec le 5e (121 sorties) : numéro 6.</p>' in top

    def test_flop_tie_plural(self):
        # flop : 43, 1, 33, 11, 14 (97) puis 20, 40 à 97 → hors tableau
        _, flop = self._cols(_freq(n20=97, n40=97))
        assert _rows(flop, "cold") == [(43, 87), (1, 93), (33, 93), (11, 97), (14, 97)]
        assert '<p class="key-figures-tie">À égalité avec le 5e (97 sorties) : numéros 20, 40.</p>' in flop

    def test_flop_tie_singular(self):
        _, flop = self._cols(_freq(n20=97))
        assert '<p class="key-figures-tie">À égalité avec le 5e (97 sorties) : numéro 20.</p>' in flop

    def test_tie_number_below_fifth_enters_table(self):
        """Départage par le tri : un ex-aequo de plus petit numéro entre dans le tableau."""
        _, flop = self._cols(_freq(n2=97))
        assert _rows(flop, "cold") == [(43, 87), (1, 93), (33, 93), (2, 97), (11, 97)]
        assert '<p class="key-figures-tie">À égalité avec le 5e (97 sorties) : numéro 14.</p>' in flop

    def test_no_tie_no_mention(self):
        top, flop = self._cols(_freq(n6=120, n22=120, n38=120))
        assert "key-figures-tie" not in top and "key-figures-tie" not in flop

    def test_tables_strictly_top5_flop5_slices(self):
        snap = _real_snapshot()
        html = kf.build_key_figures_html(snap)
        assert _rows(html, "hot") == [(d["number"], d["count"]) for d in snap["top"][:5]]
        assert _rows(html, "cold") == [(d["number"], d["count"]) for d in snap["flop"][:5]]


# ═══════════════════════════════════════════════
# 16-17. Périmètre interdit : /accueil + éléments 1A
# ═══════════════════════════════════════════════

_RE_TITLE = re.compile(r"<title>.*?</title>", re.S)
_RE_META = re.compile(r'<meta\s+name="description"[^>]*>', re.S)
_RE_LD_FULL = re.compile(r'<script type="application/ld\+json">.*?</script>', re.S)


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


class TestForbiddenScope:

    def test_accueil_seo_baseline_md5_source(self):
        """16 : baseline audit 1B (06/10/2026) — source ui/accueil.html."""
        with open("ui/accueil.html", "r", encoding="utf-8") as f:
            html = f.read()
        assert _md5(_RE_TITLE.search(html).group(0)) == "094f295af9f51122435e843b8b11578d"
        assert _md5(_RE_META.search(html).group(0)) == "aec9d0400b333ea1b45b081afb6cd7cc"
        assert _md5("".join(_RE_LD_FULL.findall(html))) == "a2e845a7a91c7cf10626f8dd371fb9fe"

    def test_accueil_seo_baseline_md5_rendered(self, client):
        """16 : baseline rendu (0 avis → AggregateRating retiré)."""
        html = _get(client, "/accueil").text
        assert _md5(_RE_TITLE.search(html).group(0)) == "094f295af9f51122435e843b8b11578d"
        assert _md5(_RE_META.search(html).group(0)) == "aec9d0400b333ea1b45b081afb6cd7cc"
        assert _md5("".join(_RE_LD_FULL.findall(html))) == "886195c29e5f99050652d046c6313b31"

    def test_stats_phase1a_untouched(self, client):
        """17 : title / meta / H1 / FAQ 4 <details> de la Phase 1A inchangés."""
        html = _get(client, "/loto/statistiques").text
        assert ("<title>Statistiques Loto : fréquences, écarts et historique des tirages | LotoIA</title>"
                in html)
        assert ('<meta name="description" content="Statistiques du Loto mises à jour après chaque tirage : '
                'fréquences des 49 numéros et du Chance, écarts, paires et historique depuis 2019.">') in html
        assert "<h1><span>📊</span> Statistiques du Loto : fréquences et historique des tirages</h1>" in html
        assert html.count("<h1>") == 1
        for summary in (
            "Quel numéro sort le plus au Loto ?",
            "Comment lire la fréquence de sortie d'un numéro ?",
            "Que signifient l'écart actuel et l'écart moyen ?",
            "Quels tirages sont pris en compte dans ces statistiques ?",
        ):
            assert f"<summary><strong>{summary}</strong></summary>" in html
        faq = re.search(r'<section class="editorial-intro stats-faq">.*?</section>', html, re.S).group(0)
        assert faq.count("<details>") == 4
        assert {b["@type"] for b in _ld_blocks(html)} == {"Dataset", "BreadcrumbList"}  # pas de FAQPage

    def test_temporal_coverage_fallback_literal_present_in_source(self):
        with open("ui/statistiques.html", "r", encoding="utf-8") as f:
            html = f.read()
        assert html.count(kf.TEMPORAL_COVERAGE_FALLBACK) == 1
        assert html.count(kf.KEY_FIGURES_MARKER) == 1
        assert html.count(kf.DATE_MODIFIED_PLACEHOLDER) == 1


# ═══════════════════════════════════════════════
# Smoke 1B (3 KO) — 200 et 304 identiques, pile de middlewares complète
# (UmamiOwnerFilterMiddleware réécrit Cache-Control pour owner + bots IA dont Googlebot/Bingbot)
# ═══════════════════════════════════════════════

_UA_GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
_UA_BINGBOT = "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"
_UA_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0 Safari/537.36"

# profil → (UA, owner ?, Cache-Control attendu, marqueur injecté attendu dans le 200)
_PROFILES = {
    "visiteur": (_UA_BROWSER, False, "private, max-age=3600", None),
    "owner": (_UA_BROWSER, True, "private, no-cache", "window.__OWNER__=true"),
    "googlebot": (_UA_GOOGLEBOT, False, "private, no-cache", "window.__IS_AI_BOT__=true"),
    "bingbot": (_UA_BINGBOT, False, "private, no-cache", "window.__IS_AI_BOT__=true"),
}


def _profile_get(client, path, profile, conn_cm, inm=None):
    """GET à travers toute la pile (middlewares compris) pour un profil donné."""
    import main as main_mod
    ua, owner, _, _ = _PROFILES[profile]
    headers = {"User-Agent": ua}
    if inm:
        headers["If-None-Match"] = inm
    # AI bots auto-désactivés hors Cloud Run (config/ai_bots.py) → forcé comme en prod
    with patch.object(main_mod, "_is_owner_ip", return_value=owner), \
            patch("config.ai_bots.AI_BOTS_WHITELIST_ENABLED", True), \
            patch("db_cloudsql.get_connection", conn_cm), \
            patch("engine.db.get_connection", conn_cm):
        return client.get(path, headers=headers)


class TestCacheControl200vs304:

    @pytest.mark.parametrize("mode", ["nominal", "fallback"])
    @pytest.mark.parametrize("profile", list(_PROFILES))
    def test_200_304_headers_identical(self, client, profile, mode):
        """ETag / Last-Modified / Cache-Control strictement identiques entre 200 et 304."""
        conn_cm = _cm(_FakeCursor()) if mode == "nominal" else _cm_raising()
        _, _, expected_cc, marker = _PROFILES[profile]
        r200 = _profile_get(client, "/loto/statistiques", profile, conn_cm)
        assert r200.status_code == 200
        if marker:
            assert marker in r200.text  # le chemin owner / bot IA est bien actif
        else:
            assert "__OWNER__=true" not in r200.text and "__IS_AI_BOT__=true" not in r200.text
        assert ('class="key-figures"' in r200.text) is (mode == "nominal")
        etag = r200.headers["etag"]
        if mode == "fallback":
            assert etag == _version_etag("/loto/statistiques")
        for inm in (etag, "W/" + etag, f'"zzz", W/{etag}'):
            r304 = _profile_get(client, "/loto/statistiques", profile, conn_cm, inm=inm)
            assert r304.status_code == 304
            assert r304.content == b""
            for h in ("etag", "last-modified", "cache-control"):
                assert r304.headers[h] == r200.headers[h], (profile, mode, inm, h)
        assert r200.headers["cache-control"] == expected_cc

    @pytest.mark.parametrize("profile", ["owner", "googlebot"])
    def test_news_middleware_304_unchanged(self, client, profile):
        """Non-régression : 304 du middleware sur /news = ETag seul, sans Cache-Control (comme 1.6.051)."""
        conn_cm = _cm(_FakeCursor())
        r200 = _profile_get(client, "/news", profile, conn_cm)
        assert r200.status_code == 200
        assert r200.headers["cache-control"] == "private, no-cache"
        etag = _version_etag("/news")
        assert r200.headers["etag"] == etag
        r304 = _profile_get(client, "/news", profile, conn_cm, inm=etag)
        assert r304.status_code == 304
        assert r304.headers["etag"] == etag
        assert "cache-control" not in r304.headers
        assert "last-modified" not in r304.headers

    def test_injected_cache_control_single_source(self):
        import main as main_mod
        assert main_mod._INJECTED_CACHE_CONTROL == b"private, no-cache"
