"""
Tests — Lot 1.6.068 (10/11/2026) : libellés IA / génération sur /accueil (doctrine : analyse statistique,
pas de génération par IA). Un seul fichier de contenu : ui/accueil.html (page FR statique, sans i18n).

  T1  anciens libellés absents (source + rendu) : « Génération de grilles par IA », « générateur IA »,
      « équilibre, équilibre », « modélisation IA » ;
  T2  nouveaux libellés présents (source + rendu) : puce moteur, carte Analyse, encart EuroMillions ;
  T3  og:description = twitter:description = variante B, sans « modélisation » ;
  T4  meta description (l.7) inchangée (même balise que la référence golden T9) ;
  T5  version courante 1.6.068.

Contrôles de chaînes sur texte aux espaces normalisés (la phrase de la carte Analyse est coupée par un
retour à la ligne). Pas de garde globale « génération + IA » sur tout le site : le titre du générateur EM
(« … IA », 6 langues) est hors lot.
"""
import hashlib
import html
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

_REPO = Path(__file__).resolve().parent.parent
_SRC = "ui/accueil.html"

_OLD = [
    "Génération de grilles par IA",
    "générateur IA",
    "équilibre, équilibre",
    "modélisation IA",
]
_NEW = [
    "<li>Exploration de grilles statistiquement équilibrées</li>",
    "Composez votre grille et obtenez un audit complet : équilibre, "
    "convergence statistique et vérification historique.",
    "Statistiques, exploration de grilles et chatbot en 6 langues.",
]
_OG_B = ("Plateforme d'analyse du Loto FDJ par intelligence artificielle. "
         "Statistiques, moteur HYBRIDE, historique complet.")
_META_TAG = ('<meta name="description" content="Analyse statistique du Loto FDJ par intelligence artificielle. '
             'Moteur HYBRIDE, chatbot IA, simulateur et historique complet. 100% gratuit.">')
_META_MD5 = "aec9d0400b333ea1b45b081afb6cd7cc"  # référence golden T9 (test_seo_golden_intouchables.py)

_RE_SOCIAL = re.compile(r'<meta (?:property="og:description"|name="twitter:description") content="([^"]*)"')


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _read(rel: str) -> str:
    return (_REPO / rel).read_text(encoding="utf-8")


# ── Client (même schéma que tests/test_lot_1_6_067.py) ───────────────────────

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


@pytest.fixture(scope="module")
def rendered(client):
    with patch("db_cloudsql.get_connection", _async_cm_conn(_make_cursor())), \
         patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
        resp = client.get("/accueil")
    assert resp.status_code == 200
    return resp.text


@pytest.fixture(scope="module", params=["source", "rendu"])
def page(request, rendered):
    return _read(_SRC) if request.param == "source" else rendered


# ── T1 / T2 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("old", _OLD)
def test_t1_old_labels_absent(page, old):
    assert old not in _norm(html.unescape(page)), f"libellé AVANT encore présent : « {old} »"


@pytest.mark.parametrize("new", _NEW)
def test_t2_new_labels_present(page, new):
    assert new in _norm(html.unescape(page)), f"libellé APRÈS absent : « {new} »"


def test_t2_bullet_appears_once(page):
    assert page.count("Exploration de grilles statistiquement équilibrées") == 1


# ── T3 ───────────────────────────────────────────────────────────────────────

def test_t3_og_twitter_variant_b(page):
    contents = [html.unescape(c) for c in _RE_SOCIAL.findall(page)]
    assert len(contents) == 2, contents
    assert contents[0] == contents[1] == _OG_B
    assert all("modélisation" not in c for c in contents)


# ── T4 ───────────────────────────────────────────────────────────────────────

def test_t4_meta_description_unchanged(page):
    tag = re.search(r'<meta name="description"[^>]*>', page).group(0)
    assert tag == _META_TAG
    assert hashlib.md5(tag.encode("utf-8")).hexdigest() == _META_MD5


# ── T5 ───────────────────────────────────────────────────────────────────────

def test_t5_app_version():
    from config.version import APP_VERSION, VERSION_DATE
    assert APP_VERSION == "1.6.068"
    assert VERSION_DATE == "2026-11-10"
