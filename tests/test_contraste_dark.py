"""
Tests — Lot contraste mode sombre (1.6.063, 31/10/2026), audit docs/audits/ro_contraste_dark.md.

  Correctif A — la date du prochain tirage (#next-draw-date) prend sa couleur d'une variable de thème
  (--theme-text-…), redéfinie sur body.theme-night / body.theme-day. Les variables de compatibilité
  --text-primary / --text-secondary sont calculées sur :root (style.css) et restent figées sur la valeur
  claire quel que soit le thème : #1f2937 sur la carte nuit #1e293b = contraste 1,00:1.
  Garde-fou — aucun style inline color:var(--text-primary|--text-secondary) dans les pages servies.
Le test golden des pages intouchables (tests/test_seo_golden_intouchables.py) n'est pas modifié.
"""
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from config.templates import EM_URLS

_REPO = Path(__file__).resolve().parent.parent
_LANGS = ("fr", "en", "es", "pt", "de", "nl")
_DATE_SOURCES = ("ui/loto.html", "ui/templates/em/generateur.html")

_RE_NEXT_DRAW = re.compile(r'<strong id="next-draw-date"[^>]*>')
_RE_FROZEN_INLINE = re.compile(r"""style=["'][^"']*color\s*:\s*var\(--text-(?:primary|secondary)\)""")


def _served_pages() -> list[Path]:
    """Pages servies : ui/*.html (hors index.html, redirigée vers /accueil) et ui/templates/**."""
    pages = [p for p in (_REPO / "ui").glob("*.html") if p.name != "index.html"]
    pages += list((_REPO / "ui" / "templates").rglob("*.html"))
    return sorted(pages)


def _assert_theme_color(tag: str, where: str):
    style = re.search(r'style="([^"]*)"', tag)
    assert style, f"{where} : #next-draw-date sans attribut style"
    value = style.group(1)
    assert re.search(r"color\s*:\s*var\(--theme-text-[a-z-]+\)", value), \
        f"{where} : #next-draw-date sans variable de thème ({value})"
    assert "var(--text-primary)" not in value and "var(--text-secondary)" not in value, \
        f"{where} : variable figée sur :root ({value})"
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", value), f"{where} : couleur codée en dur ({value})"


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
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        yield TestClient(main_mod.app, raise_server_exceptions=False)


def _get(client, path: str) -> str:
    with patch("db_cloudsql.get_connection", _async_cm_conn(_make_cursor())):
        resp = client.get(path)
    assert resp.status_code == 200, f"{path}: HTTP {resp.status_code}"
    return resp.text


# ═══════════════════════════════════════════════════════════════════════
# Correctif A — #next-draw-date sur une variable de thème
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("rel", _DATE_SOURCES)
def test_next_draw_date_source_uses_theme_variable(rel):
    text = (_REPO / rel).read_text(encoding="utf-8")
    tags = _RE_NEXT_DRAW.findall(text)
    assert len(tags) == 1, f"{rel} : {len(tags)} élément(s) #next-draw-date"
    _assert_theme_color(tags[0], rel)


def test_next_draw_date_rendered_loto(client):
    tags = _RE_NEXT_DRAW.findall(_get(client, "/loto"))
    assert len(tags) == 1
    _assert_theme_color(tags[0], "/loto")


@pytest.mark.parametrize("lang", _LANGS)
def test_next_draw_date_rendered_em_generateur(client, lang):
    path = EM_URLS[lang]["generateur"]
    tags = _RE_NEXT_DRAW.findall(_get(client, path))
    assert len(tags) == 1, f"{path} : {len(tags)} élément(s) #next-draw-date"
    _assert_theme_color(tags[0], path)


def test_theme_text_primary_defined_for_both_themes():
    css = (_REPO / "ui" / "static" / "style.css").read_text(encoding="utf-8")
    for selector in ("body.theme-night", "body.theme-day"):
        block = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
        assert block and "--theme-text-primary:" in block.group(1), \
            f"style.css : --theme-text-primary absente de {selector}"


# ═══════════════════════════════════════════════════════════════════════
# Garde-fou — variables de compatibilité figées sur :root jamais en inline
# ═══════════════════════════════════════════════════════════════════════

def test_no_frozen_compat_text_var_inline():
    hits = []
    for page in _served_pages():
        for n, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            if _RE_FROZEN_INLINE.search(line):
                hits.append(f"{page.relative_to(_REPO)}:{n}")
    assert not hits, f"color:var(--text-primary|--text-secondary) inline (figée en thème nuit) : {hits}"
