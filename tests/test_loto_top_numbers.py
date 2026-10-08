"""
Tests Cycle 2A lot (b) (1.6.053) — /loto/numeros-les-plus-sortis rendu serveur.

Couvre : get_secondary_snapshot (tri, départage, tirages au Chance NULL exclus = fenêtre
d'import V135, `pending` dans la clé de cache), valeurs de la page = snapshot, cohérence avec
/loto/statistiques et /api/stats/top-flop, classement Chance, mentions d'égalité dans les <p>
existants, squelette DOM strictement identique au fichier d'avant le lot (golden capturé AVANT
modification), title / meta / og / twitter / canonical inchangés, aucune ancienne valeur fausse,
aucun marqueur visible, fallbacks (DB down, timeout, Chance seul, dernier snapshot < 7 j),
JSON-LD dateModified, ETag / Last-Modified / 304 sur toute la pile de middlewares.
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
from html.parser import HTMLParser
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import services.cache as cache_mod
import services.loto_key_figures as kf
import services.loto_top_numbers as tn
from services import stats_service

PATH = "/loto/numeros-les-plus-sortis"

# ── Patches (pattern test_loto_key_figures.py) ───────────────────────────

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
# Chance live 08/10 (1 084) moins le tirage du 07/10 → somme 1 083
CHANCE_FREQ = {1: 105, 2: 119, 3: 107, 4: 109, 5: 105, 6: 96, 7: 113, 8: 105, 9: 117, 10: 107}
LIVE_TOTAL = 1083
FIRST = "2019-11-06"
LAST = "2026-10-05"

EXPECTED_TOP10 = [31, 30, 15, 24, 5, 6, 22, 38, 3, 7]
EXPECTED_FLOP10 = [43, 1, 33, 11, 14, 2, 20, 40, 27, 37]
EXPECTED_CHANCE5 = [2, 9, 7, 4, 3]

# Golden capturés AVANT modification (fichier ui/numeros-les-plus-sortis.html de acd5e40, 1.6.052)
GOLDEN_SKELETON_MD5 = "068ffbb3e851fffa830002b9dbcd4dab"
GOLDEN_SKELETON_LEN = 686
GOLDEN_HEAD_SEGMENT_MD5 = "58d81a3338fd9e1ab066f79ebbc8bfc5"
GOLDEN_TITLE = "<title>Numéros Loto les Plus Sortis depuis 2019 | LotoIA</title>"
GOLDEN_META_DESC = ('<meta name="description" content="Quels sont les numéros du Loto les plus sortis ? '
                    'Classement des 49 numéros par fréquence depuis 2019. Top 10, flop 10 et numéros Chance.">')
GOLDEN_CANONICAL = '<link rel="canonical" href="https://lotoia.fr/loto/numeros-les-plus-sortis">'

# Les 25 lignes FAUSSES d'avant le lot (num, sorties, fréquence)
OLD_ROWS = [
    ("hot", 7, 128, "13,0%"), ("hot", 34, 125, "12,7%"), ("hot", 3, 123, "12,5%"), ("hot", 23, 121, "12,3%"),
    ("hot", 44, 119, "12,1%"), ("hot", 19, 118, "12,0%"), ("hot", 26, 117, "11,9%"), ("hot", 49, 116, "11,8%"),
    ("hot", 12, 115, "11,7%"), ("hot", 41, 114, "11,6%"),
    ("cold", 46, 82, "8,3%"), ("cold", 18, 83, "8,4%"), ("cold", 37, 85, "8,6%"), ("cold", 28, 86, "8,7%"),
    ("cold", 14, 87, "8,8%"), ("cold", 42, 88, "8,9%"), ("cold", 2, 89, "9,0%"), ("cold", 30, 90, "9,1%"),
    ("cold", 15, 91, "9,2%"), ("cold", 39, 92, "9,3%"),
    ("chance", 2, 112, "11,4%"), ("chance", 9, 108, "11,0%"), ("chance", 5, 105, "10,7%"),
    ("chance", 7, 103, "10,5%"), ("chance", 1, 101, "10,2%"),
]

_RE_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_RE_ROW = re.compile(r'<tr><td class="rank">(\d+)</td><td class="num (hot|cold|chance)">([^<]*)</td>'
                     r'<td>([^<]*)</td><td>([^<]*)</td></tr>')
_RE_KF_ROW = re.compile(r'<th scope="row" class="num (hot|cold)">(\d+)</th><td>([^<]*)</td>')


class _FakeCursor:
    """Curseur DB minimal : répond selon la requête SQL exécutée."""

    def __init__(self, freq=None, chance=None, total=LIVE_TOTAL, first=FIRST, last=LAST, pending=0):
        self.freq = LIVE_FREQ if freq is None else freq
        self.chance = CHANCE_FREQ if chance is None else chance
        self.total, self.first, self.last, self.pending = total, first, last, pending
        self.sql = ""
        self.calls = []

    async def execute(self, sql, params=None):
        self.sql = sql
        self.calls.append(sql)

    async def fetchone(self):
        if "AS pending" in self.sql:
            if not self.total:
                return {"total": 0, "first_draw": None, "last_draw": None, "pending": None}
            return {"total": self.total, "first_draw": date.fromisoformat(self.first),
                    "last_draw": date.fromisoformat(self.last), "pending": self.pending}
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
        if "numero_chance AS num" in self.sql:
            return [{"num": n, "freq": c} for n, c in sorted(self.chance.items())]
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
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _secondary(cursor=None):
    cursor = cursor or _FakeCursor()
    with patch("db_cloudsql.get_connection", _cm(cursor)):
        return _run(stats_service.get_secondary_snapshot())


def _main_snapshot(cursor=None):
    cursor = cursor or _FakeCursor()
    with patch("db_cloudsql.get_connection", _cm(cursor)):
        return _run(stats_service.get_frequency_snapshot())


class _Skeleton(HTMLParser):
    """Séquence (balise, attributs triés) sans le texte — preuve de structure DOM identique."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        self.out.append(("<", tag, tuple(sorted(attrs))))

    def handle_startendtag(self, tag, attrs):
        self.out.append(("<>", tag, tuple(sorted(attrs))))

    def handle_endtag(self, tag):
        self.out.append((">", tag, ()))


def _skeleton(html: str) -> tuple[str, int]:
    p = _Skeleton()
    p.feed(html)
    return hashlib.md5(repr(p.out).encode()).hexdigest(), len(p.out)


def _rows(html, css):
    return [(int(r), n, c, p) for r, k, n, c, p in _RE_ROW.findall(html) if k == css]


def _ld_blocks(html):
    return [json.loads(b) for b in _RE_LD.findall(html)]


def _article(html):
    return next(b for b in _ld_blocks(html) if b.get("@type") == "Article")


def _middleware_last_modified(day: str) -> str:
    stamp = time.mktime(datetime.strptime(day, "%Y-%m-%d").timetuple())
    return formatdate(timeval=stamp, localtime=False, usegmt=True)


def _version_etag(path: str) -> str:
    from config.version import APP_VERSION
    return '"%s"' % hashlib.md5(f"{APP_VERSION}:{path}".encode()).hexdigest()


def _pct(count, total):
    return tn._fmt_pct_page(count, total, "fr_FR")


def _int(n):
    return kf._fmt_int(n, "fr_FR")


@pytest.fixture(autouse=True)
def _reset_state():
    cache_mod._mem_cache.clear()
    kf._unavailable_until = 0.0
    tn._chance_unavailable_until = 0.0
    tn._last_good.clear()
    yield
    cache_mod._mem_cache.clear()
    kf._unavailable_until = 0.0
    tn._chance_unavailable_until = 0.0
    tn._last_good.clear()


@pytest.fixture(scope="module")
def client():
    return _get_client()


def _get(client, path=PATH, cursor=None, **kwargs):
    cursor = cursor or _FakeCursor()
    with patch("db_cloudsql.get_connection", _cm(cursor)), \
            patch("engine.db.get_connection", _cm(cursor)):
        return client.get(path, **kwargs)


def _get_down(client, path=PATH, **kwargs):
    with patch("db_cloudsql.get_connection", _cm_raising()), \
            patch("engine.db.get_connection", _cm_raising()):
        return client.get(path, **kwargs)


def _assert_no_leak(html):
    assert "__NPS_" not in html
    assert "__DATE_MODIFIED__" not in html
    assert not re.search(r"__[A-Z_]+__", "".join(_RE_LD.findall(html)))


def _assert_no_old_rows(html):
    for css, num, count, pct in OLD_ROWS:
        assert f'<td class="num {css}">{num}</td><td>{count}</td><td>{pct}</td>' not in html, (css, num)


# ═══════════════════════════════════════════════
# get_secondary_snapshot : tri, V135, cache
# ═══════════════════════════════════════════════

class TestSecondarySnapshot:

    def test_sort_and_tiebreak(self):
        snap = _secondary()
        assert [d["number"] for d in snap["ranking"]] == [2, 9, 7, 4, 3, 10, 1, 5, 8, 6]
        assert snap["ranking"][0] == {"number": 2, "count": 119}
        assert (snap["total_draws"], snap["pending"], snap["draws"]) == (LIVE_TOTAL, 0, LIVE_TOTAL)
        assert (snap["first_draw"], snap["last_draw"]) == (FIRST, LAST)

    def test_missing_number_counts_zero(self):
        chance = dict(CHANCE_FREQ)
        del chance[6]
        snap = _secondary(_FakeCursor(chance=chance))
        assert snap["ranking"][-1] == {"number": 6, "count": 0}
        assert len(snap["ranking"]) == 10

    def test_sql_excludes_null_and_out_of_range(self):
        cursor = _FakeCursor()
        _secondary(cursor)
        meta_sql = next(s for s in cursor.calls if "AS pending" in s)
        freq_sql = next(s for s in cursor.calls if "numero_chance AS num" in s)
        assert "numero_chance BETWEEN 1 AND 10" in meta_sql
        assert "WHERE numero_chance BETWEEN 1 AND 10" in freq_sql

    def test_pending_excluded_from_denominator(self):
        """Fenêtre V135 : tirage inséré sans Chance → exclu, dénominateur = N - 1."""
        snap = _secondary(_FakeCursor(total=LIVE_TOTAL + 1, last="2026-10-07", pending=1))
        assert snap["pending"] == 1
        assert snap["draws"] == LIVE_TOTAL
        assert sum(d["count"] for d in snap["ranking"]) == LIVE_TOTAL

    def test_pending_logs_warning(self):
        with patch("services.base_stats.logger") as log:
            _secondary(_FakeCursor(total=LIVE_TOTAL + 1, last="2026-10-07", pending=1))
        assert any(c.args[0].startswith("[SECONDARY-SNAPSHOT]") for c in log.warning.call_args_list)

    def test_pending_in_cache_key_update_recomputes(self):
        """INSERT (pending=1) puis UPDATE du Chance (pending=0) : la clé change → recalcul."""
        during = _secondary(_FakeCursor(total=LIVE_TOTAL + 1, last="2026-10-07", pending=1))
        cache_mod._mem_cache.pop("snapshot:secmeta", None)  # expiration de la méta (5 min)
        chance = dict(CHANCE_FREQ)
        chance[5] += 1
        after = _secondary(_FakeCursor(chance=chance, total=LIVE_TOTAL + 1, last="2026-10-07", pending=0))
        assert during["pending"] == 1 and after["pending"] == 0
        assert after["draws"] == LIVE_TOTAL + 1
        assert sum(d["count"] for d in after["ranking"]) == LIVE_TOTAL + 1

    def test_meta_and_snapshot_cached(self):
        _secondary()
        cursor = _FakeCursor()
        _secondary(cursor)
        assert cursor.calls == []

    def test_empty_table_raises(self):
        with pytest.raises(LookupError):
            _secondary(_FakeCursor(total=0))

    def test_cache_ttls(self):
        with patch("services.base_stats.cache_set", AsyncMock()) as cs:
            _secondary()
        ttls = {c.args[0].split(":")[1]: c.kwargs.get("ttl") for c in cs.await_args_list}
        assert ttls == {"secmeta": 300, "sec": 7 * 24 * 3600}


# ═══════════════════════════════════════════════
# Rendu nominal : valeurs = snapshot, cohérence, égalités
# ═══════════════════════════════════════════════

class TestPageValues:

    def test_top10_flop10_equal_snapshot(self, client):
        html = _get(client).text
        snap = _main_snapshot()
        for css, ranking in (("hot", snap["top"]), ("cold", snap["flop"])):
            rows = _rows(html, css)
            assert [r for r, *_ in rows] == list(range(1, 11))
            assert [(int(n), c, p) for _, n, c, p in rows] == [
                (d["number"], _int(d["count"]), _pct(d["count"], LIVE_TOTAL)) for d in ranking[:10]
            ]
        assert [int(n) for _, n, _, _ in _rows(html, "hot")] == EXPECTED_TOP10
        assert [int(n) for _, n, _, _ in _rows(html, "cold")] == EXPECTED_FLOP10

    def test_golden_first_rows(self, client):
        html = _get(client).text
        assert '<td class="num hot">31</td><td>132</td><td>12,2%</td>' in html
        assert '<td class="num cold">43</td><td>87</td><td>8,0%</td>' in html
        assert '<td class="num chance">2</td><td>119</td><td>11,0%</td>' in html

    def test_chance_top5(self, client):
        html = _get(client).text
        rows = _rows(html, "chance")
        assert [r for r, *_ in rows] == [1, 2, 3, 4, 5]
        assert [int(n) for _, n, _, _ in rows] == EXPECTED_CHANCE5
        assert [c for _, _, c, _ in rows] == [_int(CHANCE_FREQ[n]) for n in EXPECTED_CHANCE5]
        assert [p for _, _, _, p in rows] == [_pct(CHANCE_FREQ[n], LIVE_TOTAL) for n in EXPECTED_CHANCE5]

    def test_pct_format_page_no_space(self, client):
        html = _get(client).text
        pcts = [p for _, _, _, p in _rows(html, "hot") + _rows(html, "cold") + _rows(html, "chance")]
        assert len(pcts) == 25
        assert all(re.fullmatch(r"\d+,\d%", p) for p in pcts)

    def test_top5_consistent_with_statistiques_and_api(self, client):
        page = _rows(_get(client).text, "hot")[:5], _rows(_get(client).text, "cold")[:5]
        stats_html = _get(client, "/loto/statistiques").text
        kf_rows = _RE_KF_ROW.findall(stats_html)
        assert [(int(n), c) for _, n, c, _ in page[0]] == [(int(n), c) for k, n, c in kf_rows if k == "hot"]
        assert [(int(n), c) for _, n, c, _ in page[1]] == [(int(n), c) for k, n, c in kf_rows if k == "cold"]
        api = _get(client, "/api/stats/top-flop").json()
        assert [int(n) for _, n, _, _ in _rows(_get(client).text, "hot")] == [d["number"] for d in api["top"][:10]]
        assert [int(n) for _, n, _, _ in _rows(_get(client).text, "cold")] == [d["number"] for d in api["flop"][:10]]

    def test_total_and_period(self, client):
        html = _get(client).text
        assert f"<strong>{_int(LIVE_TOTAL)} tirages officiels FDJ</strong> depuis novembre 2019." in html
        assert f"<p>Avec {_int(LIVE_TOTAL)} tirages, on s'attend" in html
        assert "fréquences d'apparition depuis 2019 — mis à jour après chaque tirage" in html
        assert "dans les tirages du Loto depuis 2019 :</p>" in html
        assert "plus de 1&nbsp;000" not in html

    def test_period_follows_first_draw(self, client):
        html = _get(client, cursor=_FakeCursor(first="2020-01-04")).text
        assert "depuis janvier 2020." in html
        assert "fréquences d'apparition depuis 2020 —" in html
        assert "dans les tirages du Loto depuis 2020 :</p>" in html

    def test_tie_notes_in_existing_paragraphs(self, client):
        """Option (b) : mention d'égalité ajoutée en TEXTE dans le <p> qui suit le tableau."""
        html = _get(client).text
        assert ("sur un échantillon de cette taille. À égalité avec le 10e (119 sorties) : "
                "numéros 13, 26.</p>") in html
        assert "un biais cognitif classique.</p>" in html  # flop : 11e (18) à 104 ≠ 103 → aucune mention
        assert ("compatibles avec le hasard. À égalité avec le 5e (107 sorties) : numéro 10.</p>") in html

    def test_no_tie_no_mention(self, client):
        freq = dict(LIVE_FREQ)
        freq[13], freq[26] = 118, 118
        chance = dict(CHANCE_FREQ)
        chance[10] = 106
        html = _get(client, cursor=_FakeCursor(freq=freq, chance=chance)).text
        assert "À égalité" not in html
        assert "sur un échantillon de cette taille.</p>" in html
        assert "compatibles avec le hasard.</p>" in html

    @pytest.mark.parametrize("extra,expected", [
        ([], ""),
        ([5], " À égalité avec le 10e (100 sorties) : numéro 5."),
        ([5, 6], " À égalité avec le 10e (100 sorties) : numéros 5, 6."),
    ])
    def test_tie_note_unit(self, extra, expected):
        ranking = [{"number": n, "count": 200 - n} for n in range(1, 10)] + [{"number": 10, "count": 100}]
        ranking += [{"number": n, "count": 100} for n in extra] + [{"number": 99, "count": 50}]
        assert tn.build_tie_note(ranking, 10) == expected

    def test_no_placeholder_leak(self, client):
        _assert_no_leak(_get(client).text)

    def test_old_false_values_absent(self, client):
        html = _get(client).text
        _assert_no_old_rows(html)
        assert "13,0%" not in html
        assert ">82<" not in html and ">112<" not in html

    def test_every_source_token_is_rendered(self):
        with open("ui/numeros-les-plus-sortis.html", "r", encoding="utf-8") as f:
            source = f.read()
        tokens = set(tn._RE_TOKEN.findall(source))
        assert len(tokens) == 81  # 25 lignes × 3 + 3 égalités + total + année + mois/année
        values = tn.build_values({"main": _main_snapshot(), "chance": _secondary()})
        assert tokens == set(values)


# ═══════════════════════════════════════════════
# Structure strictement intacte + SEO head inchangé
# ═══════════════════════════════════════════════

class TestStructureIntact:

    def test_source_skeleton_equals_golden(self):
        with open("ui/numeros-les-plus-sortis.html", "r", encoding="utf-8") as f:
            assert _skeleton(f.read()) == (GOLDEN_SKELETON_MD5, GOLDEN_SKELETON_LEN)

    @pytest.mark.parametrize("mode", ["nominal", "fallback", "chance_down", "pending"])
    def test_rendered_skeleton_equals_golden(self, client, mode):
        if mode == "nominal":
            html = _get(client).text
        elif mode == "fallback":
            html = _get_down(client).text
        elif mode == "pending":
            html = _get(client, cursor=_FakeCursor(total=LIVE_TOTAL + 1, last="2026-10-07", pending=1)).text
        else:
            with patch("services.loto_top_numbers.get_secondary_snapshot",
                       AsyncMock(side_effect=RuntimeError("down"))):
                html = _get(client).text
        assert _skeleton(html) == (GOLDEN_SKELETON_MD5, GOLDEN_SKELETON_LEN)

    @pytest.mark.parametrize("mode", ["nominal", "fallback"])
    def test_seo_head_unchanged(self, client, mode):
        html = _get(client).text if mode == "nominal" else _get_down(client).text
        seg = re.search(r"<title>.*?<meta name=\"twitter:image\"[^>]*>", html, re.S).group(0)
        assert hashlib.md5(seg.encode()).hexdigest() == GOLDEN_HEAD_SEGMENT_MD5
        assert GOLDEN_TITLE in html and GOLDEN_META_DESC in html and GOLDEN_CANONICAL in html

    def test_table_and_breadcrumb_ld_unchanged(self, client):
        blocks = _ld_blocks(_get(client).text)
        assert [b["@type"] for b in blocks] == ["Article", "BreadcrumbList", "Table"]
        assert blocks[2]["about"] == "Numéros du Loto français les plus fréquemment tirés depuis 2019"
        assert "temporalCoverage" not in blocks[0]


# ═══════════════════════════════════════════════
# JSON-LD dateModified + sitemap
# ═══════════════════════════════════════════════

class TestJsonLd:

    def test_date_modified_is_last_draw(self, client):
        art = _article(_get(client).text)
        assert art["dateModified"] == LAST
        assert art["datePublished"] == "2026-02-22"

    def test_date_modified_matches_sitemap_lastmod(self, client):
        from xml.etree import ElementTree
        art = _article(_get(client).text)
        xml = _get(client, "/sitemap.xml").text
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        root = ElementTree.fromstring(xml)
        lastmod = next(u.find("s:lastmod", ns).text for u in root.findall("s:url", ns)
                       if u.find("s:loc", ns).text.endswith(PATH))
        assert lastmod == art["dateModified"]

    def test_fallback_removes_date_modified_valid_json(self, client):
        art = _article(_get_down(client).text)
        assert "dateModified" not in art
        assert art["datePublished"] == "2026-02-22"


# ═══════════════════════════════════════════════
# Fallbacks : jamais de 500, jamais les anciennes valeurs
# ═══════════════════════════════════════════════

class TestFallback:

    def _assert_neutral(self, html):
        for css in ("hot", "cold", "chance"):
            rows = _rows(html, css)
            assert rows and all((n, c, p) == ("—", "—", "—") for _, n, c, p in rows), css
        assert "<strong>plus de 1&nbsp;000 tirages officiels FDJ</strong> depuis novembre 2019." in html
        assert "<p>Avec plus de 1&nbsp;000 tirages, on s'attend" in html
        assert "À égalité" not in html
        assert ">128<" not in html and ">82<" not in html and ">112<" not in html and "13,0%" not in html
        _assert_no_old_rows(html)
        _assert_no_leak(html)

    def test_db_down_neutral_values(self, client):
        resp = _get_down(client)
        assert resp.status_code == 200
        self._assert_neutral(resp.text)

    def test_timeout_neutral_values(self, client):
        async def _slow():
            await asyncio.sleep(1)

        with patch.object(kf, "_SNAPSHOT_TIMEOUT_S", 0.01), patch.object(tn, "_SNAPSHOT_TIMEOUT_S", 0.01), \
                patch("services.loto_key_figures.get_frequency_snapshot", _slow), \
                patch("services.loto_top_numbers.get_secondary_snapshot", _slow):
            resp = client.get(PATH)
        assert resp.status_code == 200
        self._assert_neutral(resp.text)

    def test_cache_backend_error_neutral(self, client):
        with patch("services.base_stats.cache_get", AsyncMock(side_effect=ConnectionError("redis"))):
            resp = _get(client)
        assert resp.status_code == 200
        self._assert_neutral(resp.text)

    def test_empty_table_neutral(self, client):
        resp = _get(client, cursor=_FakeCursor(total=0))
        assert resp.status_code == 200
        self._assert_neutral(resp.text)

    def test_chance_only_down(self, client):
        with patch("services.loto_top_numbers.get_secondary_snapshot",
                   AsyncMock(side_effect=RuntimeError("down"))):
            resp = _get(client)
        html = resp.text
        assert resp.status_code == 200
        assert [int(n) for _, n, _, _ in _rows(html, "hot")] == EXPECTED_TOP10
        assert all((n, c, p) == ("—", "—", "—") for _, n, c, p in _rows(html, "chance"))
        assert "compatibles avec le hasard.</p>" in html
        assert _article(html)["dateModified"] == LAST
        _assert_no_leak(html)

    def test_last_good_reserved_within_7_days(self, client):
        good = _get(client).text
        cache_mod._mem_cache.clear()
        degraded = _get_down(client)
        assert degraded.status_code == 200
        assert _rows(degraded.text, "hot") == _rows(good, "hot")
        assert _rows(degraded.text, "chance") == _rows(good, "chance")
        assert _article(degraded.text)["dateModified"] == LAST

    def test_last_good_expired_after_7_days(self, client):
        _get(client)
        cache_mod._mem_cache.clear()
        for kind, (snap, ts) in list(tn._last_good.items()):
            tn._last_good[kind] = (snap, ts - 7 * 24 * 3600 - 1)
        self._assert_neutral(_get_down(client).text)

    def test_chance_negative_cache_30s(self):
        spy = AsyncMock(side_effect=RuntimeError("down"))
        with patch("services.loto_top_numbers.get_secondary_snapshot", spy):
            assert _run(tn._get_chance_snapshot()) is None
            assert _run(tn._get_chance_snapshot()) is None
        assert spy.await_count == 1
        assert 29 < tn._chance_unavailable_until - time.monotonic() <= 30


# ═══════════════════════════════════════════════
# Fenêtre d'import V135 (INSERT boules → UPDATE Chance différé)
# ═══════════════════════════════════════════════

class TestV135Window:

    def test_pending_chance_on_n_minus_1(self, client):
        cursor = _FakeCursor(total=LIVE_TOTAL + 1, last="2026-10-07", pending=1)
        html = _get(client, cursor=cursor).text
        rows = _rows(html, "chance")
        assert [p for _, _, _, p in rows] == [_pct(CHANCE_FREQ[n], LIVE_TOTAL) for n in EXPECTED_CHANCE5]
        assert f"<strong>{_int(LIVE_TOTAL + 1)} tirages officiels FDJ</strong>" in html

    def test_etag_changes_when_update_lands(self, client):
        during = _get(client, cursor=_FakeCursor(total=LIVE_TOTAL + 1, last="2026-10-07", pending=1))
        cache_mod._mem_cache.pop("snapshot:secmeta", None)
        chance = dict(CHANCE_FREQ)
        chance[3] += 1  # le Chance du tirage du 07/10 arrive : 3 → 108 (reste 5e)
        after_cursor = _FakeCursor(chance=chance, total=LIVE_TOTAL + 1, last="2026-10-07", pending=0)
        after = _get(client, cursor=after_cursor, headers={"If-None-Match": during.headers["etag"]})
        assert after.status_code == 200
        assert after.headers["etag"] != during.headers["etag"]
        assert (f'<td class="num chance">3</td><td>108</td><td>{_pct(108, LIVE_TOTAL + 1)}</td>'
                in after.text)
        assert "À égalité avec le 5e" not in after.text


# ═══════════════════════════════════════════════
# ETag / Last-Modified / 304
# ═══════════════════════════════════════════════

class TestConditionalGet:

    def test_headers_data_dated(self, client):
        resp = _get(client)
        data = {"main": _main_snapshot(), "chance": _secondary()}
        assert resp.headers["etag"] == tn.page_etag(data) != _version_etag(PATH)
        assert resp.headers["last-modified"] == "Mon, 05 Oct 2026 00:00:00 GMT"
        assert resp.headers["cache-control"] == "private, max-age=3600"

    def test_304_then_new_draw_gives_200(self, client):
        etag = _get(client).headers["etag"]
        assert _get(client, headers={"If-None-Match": etag}).status_code == 304
        cache_mod._mem_cache.clear()
        resp = _get(client, cursor=_FakeCursor(last="2026-10-07", total=1084), headers={"If-None-Match": etag})
        assert resp.status_code == 200
        assert resp.headers["etag"] != etag
        assert resp.headers["last-modified"] == "Wed, 07 Oct 2026 00:00:00 GMT"

    @pytest.mark.parametrize("fmt", ["{e}", "W/{e}", '"zzz", W/{e}', '"a","b" ,{e}', "*"])
    def test_if_none_match_weak_and_multi(self, client, fmt):
        etag = _get(client).headers["etag"]
        assert _get(client, headers={"If-None-Match": fmt.format(e=etag)}).status_code == 304

    def test_if_none_match_mismatch_gives_200(self, client):
        assert _get(client, headers={"If-None-Match": 'W/"nope", "other"'}).status_code == 200

    def test_304_carries_headers_no_body(self, client):
        r200 = _get(client)
        r304 = _get(client, headers={"If-None-Match": r200.headers["etag"]})
        assert r304.status_code == 304
        assert r304.content == b""
        for h in ("etag", "last-modified", "cache-control"):
            assert r304.headers[h] == r200.headers[h]

    def test_fallback_version_etag_and_middleware_last_modified(self, client):
        import main as main_mod
        etag = _version_etag(PATH)
        r200 = _get_down(client)
        assert r200.headers["etag"] == etag
        assert r200.headers["last-modified"] == _middleware_last_modified(main_mod.LAST_DEPLOY_DATE)
        for value in (etag, "W/" + etag, f'"x", W/{etag}'):
            r304 = _get_down(client, headers={"If-None-Match": value})
            assert r304.status_code == 304
            assert r304.headers["etag"] == etag
            assert r304.headers["cache-control"] == "private, max-age=3600"

    def test_etag_unit(self):
        main = {"first_draw": FIRST, "last_draw": LAST, "total_draws": LIVE_TOTAL}
        chance = {"last_draw": LAST, "total_draws": LIVE_TOTAL, "pending": 0}
        e_full = tn.page_etag({"main": main, "chance": chance})
        e_pending = tn.page_etag({"main": main, "chance": {**chance, "pending": 1}})
        e_no_chance = tn.page_etag({"main": main, "chance": None})
        assert len({e_full, e_pending, e_no_chance, _version_etag(PATH)}) == 4
        assert tn.page_etag({"main": None, "chance": None}) == _version_etag(PATH)

    def test_route_in_data_dated_routes(self):
        import main as main_mod
        assert PATH in main_mod._DATA_DATED_ROUTES


# ═══════════════════════════════════════════════
# Pile de middlewares complète : 200 et 304 identiques par profil
# (UmamiOwnerFilterMiddleware réécrit Cache-Control pour owner + bots dont Googlebot/Bingbot)
# ═══════════════════════════════════════════════

_UA_GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
_UA_BINGBOT = "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"
_UA_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0 Safari/537.36"

_PROFILES = {
    "visiteur": (_UA_BROWSER, False, "private, max-age=3600", None),
    "owner": (_UA_BROWSER, True, "private, no-cache", "window.__OWNER__=true"),
    "googlebot": (_UA_GOOGLEBOT, False, "private, no-cache", "window.__IS_AI_BOT__=true"),
    "bingbot": (_UA_BINGBOT, False, "private, no-cache", "window.__IS_AI_BOT__=true"),
}


def _profile_get(client, path, profile, conn_cm, inm=None):
    import main as main_mod
    ua, owner, _, _ = _PROFILES[profile]
    headers = {"User-Agent": ua}
    if inm:
        headers["If-None-Match"] = inm
    with patch.object(main_mod, "_is_owner_ip", return_value=owner), \
            patch("config.ai_bots.AI_BOTS_WHITELIST_ENABLED", True), \
            patch("db_cloudsql.get_connection", conn_cm), \
            patch("engine.db.get_connection", conn_cm):
        return client.get(path, headers=headers)


class TestCacheControl200vs304:

    @pytest.mark.parametrize("mode", ["nominal", "fallback"])
    @pytest.mark.parametrize("profile", list(_PROFILES))
    def test_200_304_headers_identical(self, client, profile, mode):
        conn_cm = _cm(_FakeCursor()) if mode == "nominal" else _cm_raising()
        _, _, expected_cc, marker = _PROFILES[profile]
        r200 = _profile_get(client, PATH, profile, conn_cm)
        assert r200.status_code == 200
        if marker:
            assert marker in r200.text
        else:
            assert "__OWNER__=true" not in r200.text and "__IS_AI_BOT__=true" not in r200.text
        assert ('<td class="num hot">31</td>' in r200.text) is (mode == "nominal")
        etag = r200.headers["etag"]
        if mode == "fallback":
            assert etag == _version_etag(PATH)
        for inm in (etag, "W/" + etag, f'"zzz", W/{etag}'):
            r304 = _profile_get(client, PATH, profile, conn_cm, inm=inm)
            assert r304.status_code == 304
            assert r304.content == b""
            for h in ("etag", "last-modified", "cache-control"):
                assert r304.headers[h] == r200.headers[h], (profile, mode, inm, h)
        assert r200.headers["cache-control"] == expected_cc


# ═══════════════════════════════════════════════
# Non-régression : /loto/statistiques (1B) et routes middleware
# ═══════════════════════════════════════════════

class TestNonRegression:

    def test_statistiques_etag_unchanged_formula(self, client):
        resp = _get(client, "/loto/statistiques")
        snap = {"first_draw": FIRST, "last_draw": LAST, "total_draws": LIVE_TOTAL}
        assert resp.headers["etag"] == kf.page_etag(snap)
        assert 'class="key-figures"' in resp.text

    @pytest.mark.parametrize("path", ["/loto", "/news", "/loto/analyse"])
    def test_middleware_routes_unchanged(self, client, path):
        import main as main_mod
        etag = _version_etag(path)
        r = _get(client, path)
        assert r.status_code == 200
        assert r.headers["etag"] == etag
        assert r.headers["last-modified"] == _middleware_last_modified(main_mod.LAST_DEPLOY_DATE)
        assert _get(client, path, headers={"If-None-Match": etag}).status_code == 304

    def test_loto_ia_still_uses_deploy_date(self, client):
        import main as main_mod
        html = _get(client, "/loto/intelligence-artificielle").text
        assert "__DATE_MODIFIED__" not in html
        assert main_mod.LAST_DEPLOY_DATE in html
