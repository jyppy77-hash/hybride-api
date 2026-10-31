"""
Tests — Lot i18n express (1.6.062, 30/10/2026), audit accents de Muse sur la prod.

  I1 — /euromillions/cookies FR réaccentuée (clés <code> intactes, « site visité ») ;
  I2 — /euromillions/avertissement FR réaccentuée (ligne D1 comprise) ;
  I4 — titre de la news « Release 1.5.0 » traduit dans les 5 langues, plus d'entrée fuzzy ;
  I5 — « 100%% » jamais affiché (gettext newstyle=False : le msgstr est rendu sans formatage) ;
  I6 — H1 du simulateur ES/PT accentué ;
  I7 — « coup d'œil » sur /euromillions, « Outil d'analyse » dans le JSON-LD du simulateur ;
  garde de build — Catalog.check() sans erreur (pybabel compile du Dockerfile échoue sinon).
Le test golden des pages intouchables (tests/test_seo_golden_intouchables.py) n'est pas modifié.
"""
import html
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from babel.messages.pofile import read_po
from fastapi.testclient import TestClient

from config.templates import EM_URLS

_REPO = Path(__file__).resolve().parent.parent
_LANGS = ("fr", "en", "es", "pt", "de", "nl")
_FOREIGN = ("en", "es", "pt", "de", "nl")

_RELEASE_TITLE = {
    "en": "Release 1.5.0 — The platform levels up",
    "es": "Release 1.5.0 — La plataforma sube de nivel",
    "pt": "Release 1.5.0 — A plataforma sobe de nível",
    "de": "Release 1.5.0 — Die Plattform erreicht das nächste Level",
    "nl": "Release 1.5.0 — Het platform bereikt het volgende niveau",
}
_RELEASE_MSGID = "Release 1.5.0 — La plateforme passe au niveau supérieur"

_SIMULATEUR_H1 = {
    "es": "Análisis de Cuadrícula EuroMillions",
    "pt": "Análise de Grelha EuroMillions",
}
_SIMULATEUR_H1_OLD = {
    "es": "Analisis de Cuadricula",
    "pt": "Analise de Grelha",
}


def _po_path(lang: str) -> Path:
    return _REPO / "translations" / lang / "LC_MESSAGES" / "messages.po"


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


def _page(client, lang: str, page: str) -> str:
    path = EM_URLS[lang][page]
    with patch("db_cloudsql.get_connection", _async_cm_conn(_make_cursor())):
        resp = client.get(path)
    assert resp.status_code == 200, f"{path}: HTTP {resp.status_code}"
    return resp.text


# ═══════════════════════════════════════════════════════════════════════
# I1 / I2 — pages légales EM FR réaccentuées
# ═══════════════════════════════════════════════════════════════════════

def test_cookies_fr_accented(client):
    raw = _page(client, "fr", "cookies")
    body = html.unescape(raw)
    for expected in ("Dernière mise à jour : 1 mars 2026", "Politique de confidentialité",
                     "déposés par le site visité", "Gérer mes préférences cookies",
                     "délibération n°2020-091", "Au-delà de cette période"):
        assert expected in body, f"cookies FR : « {expected} » absent"
    for old in ("Derniere mise a jour", "donnees", "necessaire", "prealable", "proprietaires",
                "site visite<", "Gerer mes preferences"):
        assert old not in body, f"cookies FR : forme sans accent « {old} » encore visible"
    for key in ("lotoia-theme", "lotoia_cookie_consent", "lotoia_session"):
        assert f"<code>{key}</code>" in raw, f"cookies FR : clé technique <code>{key}</code> altérée"


def test_disclaimer_fr_accented(client):
    body = html.unescape(_page(client, "fr", "disclaimer"))
    for expected in ("Avertissements Légaux", "Dernière mise à jour : 1 mars 2026",
                     "JOUER COMPORTE DES RISQUES : ENDETTEMENT, ISOLEMENT, DÉPENDANCE.",
                     "Pondération temporelle", "EN L'ÉTAT", "(appel non surtaxé)",
                     "Chaque combinaison a <strong>exactement la même probabilité</strong>"):
        assert expected in body, f"avertissement FR : « {expected} » absent"
    for old in ("Derniere mise a jour", "DEPENDANCE", "Ponderation temporelle", "EN L'ETAT",
                "non surtaxe)", "fenetres", "systeme"):
        assert old not in body, f"avertissement FR : forme sans accent « {old} » encore visible"


# ═══════════════════════════════════════════════════════════════════════
# I4 — titre de la news Release 1.5.0, entrées fuzzy
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lang", _FOREIGN)
def test_news_release_title_translated(client, lang):
    body = html.unescape(_page(client, lang, "news"))
    assert _RELEASE_TITLE[lang] in body, f"news {lang} : titre traduit absent"
    assert _RELEASE_MSGID not in body, f"news {lang} : titre FR visible"


@pytest.mark.parametrize("lang", _FOREIGN)
def test_po_no_fuzzy_foreign(lang):
    text = _po_path(lang).read_text(encoding="utf-8")
    assert not re.search(r"^#,.*\bfuzzy\b", text, re.M), f"{lang} : entrée fuzzy (ignorée à la compilation)"


def test_po_fr_fuzzy_only_untranslated():
    """FR : seules restent des entrées fuzzy à msgstr vide (sans effet : le msgid s'affiche de toute façon)."""
    with open(_po_path("fr"), "rb") as f:
        catalog = read_po(f)
    bad = [m.id for m in catalog if m.id and m.fuzzy and m.string]
    assert not bad, f"FR : entrées fuzzy traduites ignorées à la compilation : {bad}"


# ═══════════════════════════════════════════════════════════════════════
# I5 — « 100%% » jamais affiché
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("page", ["hybride_page", "news"])
def test_no_double_percent_rendered(client, page, lang):
    body = html.unescape(_page(client, lang, page))
    assert "100%%" not in body, f"{page} {lang} : « 100%% » visible"
    assert "100%" in body, f"{page} {lang} : « 100% » absent"


# ═══════════════════════════════════════════════════════════════════════
# Garde de build — pybabel compile (Dockerfile) échoue sur une erreur de format
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lang", _LANGS)
def test_po_catalog_check_no_error(lang):
    with open(_po_path(lang), "rb") as f:
        catalog = read_po(f)
    errors = [(m.id, [str(e) for e in errs]) for m, errs in catalog.check()]
    assert not errors, f"{lang} : erreurs Babel (pybabel compile sortirait en code 1) : {errors}"


# ═══════════════════════════════════════════════════════════════════════
# I6 / I7 — petits points
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lang", ["es", "pt"])
def test_simulateur_h1_accented(client, lang):
    body = html.unescape(_page(client, lang, "simulateur"))
    h1 = re.search(r"<h1>(.*?)</h1>", body, re.S)
    assert h1 and _SIMULATEUR_H1[lang] in h1.group(1), f"simulateur {lang} : H1 accentué absent"
    assert _SIMULATEUR_H1_OLD[lang] not in body


def test_em_accueil_coup_d_oeil(client):
    body = html.unescape(_page(client, "fr", "accueil"))
    assert "Le moteur HYBRIDE en un coup d'œil" in body
    assert "coup d'oeil" not in body


def test_simulateur_jsonld_description_fr(client):
    raw = _page(client, "fr", "simulateur")
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', raw, re.S)
    descriptions = [json.loads(b).get("description") for b in blocks]
    assert "Outil d'analyse statistique descriptive pour grilles EuroMillions" in descriptions
    assert "Outil d analyse" not in html.unescape(raw)


# ═══════════════════════════════════════════════════════════════════════
# Étape 2 bis — second passage de Muse
# ═══════════════════════════════════════════════════════════════════════

_HYBRIDE_EM_ANSWER = ("Oui. HYBRIDE est connecté aux deux bases de données (Loto et EuroMillions) "
                      "pour répondre à vos questions sur les deux jeux. Le module EuroMillions répond en 6 langues.")


def test_loto_hybride_faq_euromillions_present_tense(client):
    with patch("db_cloudsql.get_connection", _async_cm_conn(_make_cursor())):
        resp = client.get("/hybride")
    assert resp.status_code == 200
    raw = resp.text
    body = html.unescape(raw)
    for old in ("15 mars 2026", "Bientôt", "arrive le", "sera alors connecté"):
        assert old not in body, f"/hybride : « {old} » (EuroMillions au futur) encore présent"
    assert '<a href="/euromillions">EuroMillions</a>' in raw
    # JSON-LD FAQPage identique au texte visible
    answers = []
    for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', raw, re.S):
        data = json.loads(b)
        if data.get("@type") == "FAQPage":
            answers += [q["acceptedAnswer"]["text"] for q in data["mainEntity"]
                        if q["name"] == "HYBRIDE fonctionne-t-il pour l'EuroMillions ?"]
    assert answers == [_HYBRIDE_EM_ANSWER]
    visible = re.search(r"<h3>HYBRIDE fonctionne-t-il pour l'EuroMillions \?</h3>\s*<p>(.*?)</p>", body, re.S)
    assert visible and re.sub(r"<[^>]+>", "", visible.group(1)) == _HYBRIDE_EM_ANSWER


def test_em_faq_ou_trouver_aide_accented(client):
    raw = _page(client, "fr", "faq")
    body = html.unescape(raw)
    assert "<span>Où trouver de l'aide en cas d'addiction ?</span>" in body
    assert "Ou trouver de l'aide" not in body
    names = []
    for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', raw, re.S):
        data = json.loads(b)
        if data.get("@type") == "FAQPage":
            names += [q["name"] for q in data["mainEntity"]]
    assert "Où trouver de l'aide en cas d'addiction ?" in names
