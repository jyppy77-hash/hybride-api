"""
Tests — Lot 1.6.069 (11/11/2026) : « site propre » avant la salve presse.

  T1  A1 : sponsor-popup-em.css, .sponsor-popup-modal ramené à 3 ombres (10 copies dorées décalées supprimées) ;
  T2  cache-busters : sponsor-popup-em.css ?v=15 (générateur + simulateur EM), sponsor-popup.css ?v=15
      (/loto + /loto/analyse), plus aucun ?v=14 pour ces deux feuilles dans les pages servies ;
  T3  A2 : .stats-faq summary coloré par --theme-text-primary ; « depuis novembre 2019 (lundi » ;
      « 6 novembre 2019 » absent ; repli JSON-LD 2019-11-06 conservé (1.6.070) ;
  T4  B4 min. : /historique charge version-inject.js ;
  T5  B8a + B6 : titre des résultats en nuit (Loto + EM) ; padding-right de .generator-header (EM) ;
  T6  B9 : .console-title de sponsor-popup.css en blanc ;
  T7  rendu servi (TestClient) : /loto, /loto/statistiques, /loto/analyse, /historique, générateur et
      simulateur EM dans les 6 langues, en 200 avec les nouvelles références ;
  T8  version 1.6.069 / 2026-11-11.

Le correctif P (pitch, sortie « cap total 14s » → 503) est couvert dans tests/test_v131_retry.py.
"""
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

_REPO = Path(__file__).resolve().parent.parent

_EM_CSS = "ui/static/em/sponsor-popup-em.css"
_LOTO_CSS = "ui/static/sponsor-popup.css"
_EM_GEN = "ui/templates/em/generateur.html"
_EM_SIM = "ui/templates/em/simulateur.html"
_STATS = "ui/statistiques.html"
_HISTO = "ui/historique.html"
_LOTO = "ui/loto.html"
_LOTO_SIM = "ui/simulateur.html"

_REMOVED_SHADOWS = [
    "55px 72px 2px", "195px 145px 2px", "340px 88px 2px", "485px 132px 2px", "260px 42px 2px",
    "120px 258px 2px", "415px 195px 2px", "540px 282px 2px", "65px 155px 2px", "330px 305px 2px",
]
_KEPT_SHADOWS = (
    "box-shadow:\n"
    "        0 25px 80px rgba(0, 0, 0, 0.5),\n"
    "        0 0 40px rgba(0, 51, 153, 0.15),\n"
    "        0 0 0 1px rgba(255, 215, 0, 0.1) inset;\n"
    "    position: relative;"
)
_RESULT_TITLE_RULE = "body.theme-night #result-title{color:var(--theme-text-primary)}"
_GEN_HEADER_RULE = "@media (min-width:769px){.generator-header{padding-right:120px}}"
_SUMMARY_RULE = ".stats-faq summary{cursor:pointer;color:var(--theme-text-primary)}"
_VERSION_INJECT = '<script src="/ui/static/version-inject.js" defer></script>'
_EM_CSS_V15 = "/ui/static/em/sponsor-popup-em.css?v=15"
_LOTO_CSS_V15 = "/ui/static/sponsor-popup.css?v=15"

_EM_GEN_URLS = [
    "/euromillions/generateur", "/en/euromillions/generator", "/es/euromillions/generador",
    "/pt/euromillions/gerador", "/de/euromillions/generator", "/nl/euromillions/generator",
]
_EM_SIM_URLS = [
    "/euromillions/simulateur", "/en/euromillions/simulator", "/es/euromillions/simulador",
    "/pt/euromillions/simulador", "/de/euromillions/simulator", "/nl/euromillions/simulator",
]


def _read(rel: str) -> str:
    # Lecture texte : \r\n → \n (copie de travail CRLF ou LF selon le fichier).
    return (_REPO / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def _css_block(css: str, selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r" \{(.*?)^\}", css, re.S)
    assert m, f"bloc {selector} introuvable"
    return m.group(1)


# ── Client (même schéma que tests/test_lot_1_6_068.py) ───────────────────────

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb", "EM_PUBLIC_ACCESS": "true",
})


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


@pytest.fixture(scope="module")
def client():
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import rate_limit as rl_mod
        importlib.reload(rl_mod)
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        rl_mod.limiter.reset()
        rl_mod._api_hits.clear()
        yield TestClient(main_mod.app, raise_server_exceptions=False)


def _get(client, path: str):
    with patch("db_cloudsql.get_connection", _async_cm_conn(_make_cursor())), \
         patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
        return client.get(path)


# ── T1 — A1 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("shadow", _REMOVED_SHADOWS)
def test_t1_em_modal_offset_shadows_removed(shadow):
    block = _css_block(_read(_EM_CSS), ".sponsor-popup-modal")
    assert shadow not in block


def test_t1_em_modal_three_shadows_kept():
    css = _read(_EM_CSS)
    assert _KEPT_SHADOWS in _css_block(css, ".sponsor-popup-modal")
    assert css.count("rgba(255,215,0,0.") == 0  # plus aucune ombre dorée décalée dans la feuille


# ── T2 — cache-busters ───────────────────────────────────────────────────────

@pytest.mark.parametrize("rel", [_EM_GEN, _EM_SIM])
def test_t2_em_css_v15(rel):
    src = _read(rel)
    assert src.count(_EM_CSS_V15) == 1
    assert "sponsor-popup-em.css?v=14" not in src


@pytest.mark.parametrize("rel", [_LOTO, _LOTO_SIM])
def test_t2_loto_css_v15(rel):
    src = _read(rel)
    assert src.count(_LOTO_CSS_V15) == 1
    assert "sponsor-popup.css?v=14" not in src


def test_t2_sponsor_popup75_em_css_untouched():
    assert "/ui/static/em/sponsor-popup75-em.css?v=14" in _read(_EM_GEN)


# ── T3 — A2 ──────────────────────────────────────────────────────────────────

def test_t3_stats_faq_summary_color():
    src = _read(_STATS)
    assert src.count(_SUMMARY_RULE) == 1
    assert ".stats-faq summary{cursor:pointer}" not in src


def test_t3_stats_faq_date_wording():
    src = _read(_STATS)
    assert "6 novembre 2019" not in src
    assert "tirages officiels du Loto FDJ depuis novembre 2019 (lundi, mercredi et samedi)" in src


def test_t3_temporal_coverage_fallback_kept():
    # Repli JSON-LD (l.54) volontairement inchangé : relève de la 1.6.070.
    assert _read(_STATS).count('"temporalCoverage": "2019-11-06/.."') == 1


# ── T4 — B4 min. ─────────────────────────────────────────────────────────────

def test_t4_historique_loads_version_inject():
    src = _read(_HISTO)
    assert src.count(_VERSION_INJECT) == 1
    assert src.index(_VERSION_INJECT) < src.index("</body>")


# ── T5 — B8a + B6 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("rel", [_LOTO, _EM_GEN])
def test_t5_result_title_night_rule(rel):
    assert _read(rel).count(_RESULT_TITLE_RULE) == 1


def test_t5_em_generator_header_padding():
    assert _read(_EM_GEN).count(_GEN_HEADER_RULE) == 1


# ── T6 — B9 ──────────────────────────────────────────────────────────────────

def test_t6_loto_console_title_white():
    block = _css_block(_read(_LOTO_CSS), ".console-title")
    assert "color: #ffffff;" in block
    assert block.index("color: #ffffff;") < block.index("opacity: 0.9;")


# ── T7 — rendu servi ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", _EM_GEN_URLS)
def test_t7_em_generator_rendered(client, path):
    resp = _get(client, path)
    assert resp.status_code == 200, path
    body = resp.text
    assert _EM_CSS_V15 in body
    assert _RESULT_TITLE_RULE in body
    assert _GEN_HEADER_RULE in body
    assert "sponsor-popup-em.css?v=14" not in body


@pytest.mark.parametrize("path", _EM_SIM_URLS)
def test_t7_em_simulator_rendered(client, path):
    resp = _get(client, path)
    assert resp.status_code == 200, path
    assert _EM_CSS_V15 in resp.text
    assert "sponsor-popup-em.css?v=14" not in resp.text


@pytest.mark.parametrize("path, expected", [
    ("/loto", [_LOTO_CSS_V15, _RESULT_TITLE_RULE]),
    ("/loto/analyse", [_LOTO_CSS_V15]),
    ("/loto/statistiques", [_SUMMARY_RULE, "depuis novembre 2019 (lundi"]),
    ("/historique", [_VERSION_INJECT]),
])
def test_t7_loto_pages_rendered(client, path, expected):
    resp = _get(client, path)
    assert resp.status_code == 200, path
    for needle in expected:
        assert needle in resp.text, f"{path} : {needle}"
    assert "sponsor-popup.css?v=14" not in resp.text


# ── T8 — version ─────────────────────────────────────────────────────────────

def test_t8_app_version():
    # Plancher : le lot reste couvert après les bumps suivants (épinglage exact dans test_launcher_seo.py / test_seo_indexation.py).
    from config.version import APP_VERSION, VERSION_DATE
    assert tuple(int(p) for p in APP_VERSION.split(".")) >= (1, 6, 69)
    assert VERSION_DATE >= "2026-11-11"
