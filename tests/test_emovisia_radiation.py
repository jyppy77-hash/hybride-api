"""
Tests — Lot radiation EmovisIA (1.6.064, 02/11/2026).

LotoIA est édité à titre non professionnel par Jean-Philippe Godard (EI EmovisIA radiée,
effet 31/10/2026). Garde-fou :
  G1 — pages légales + À propos, Loto FR et EM 6 langues : aucun nom d'entreprise,
       identifiant, adresse postale ou téléphone personnel ; aucun cadrage « société » ;
  G2 — dates de mise à jour au 2 novembre 2026 (mentions + confidentialité) ;
  G3 — JSON-LD des pages À propos : pas de parentOrganization ni de sameAs emovisia.fr ;
  G4 — fichiers sources publics (ui/, prompts/, translations/) : aucun motif interdit ;
  G5 — exercice des droits RGPD sur rgpd@lotoia.fr, plus de « DPO » / « délégué ».
Back-office, migrations et fixtures admin exclus (hors périmètre public, décision D9).
"""
import html
import json
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

_FORBIDDEN = re.compile(
    r"EmovisIA|emovisia|511\s?245\s?730|51124573000029|917\s?420\s?077|Alexandre Riou|Machecoul|44270"
    r"|06[ .]?99[ .]?55[ .]?22[ .]?10|\+33\s?6\s?99|\+33699552210",
    re.IGNORECASE,
)
_COMPANY = re.compile(
    r"French company|empresa francesa|franz.sisches Unternehmen|Frans bedrijf|Company name|Raison sociale :\s*EmovisIA"
    r"|Entreprise individuelle|repr.sentant l.gal|SIRET",
)
_DATES = {
    "fr": "2 novembre 2026", "en": "2 November 2026", "es": "2 de noviembre de 2026",
    "pt": "2 de novembro de 2026", "de": "2. November 2026", "nl": "2 november 2026",
}
_LOTO_PAGES = ("/mentions-legales", "/politique-confidentialite", "/a-propos")
_EM_PAGES = ("mentions", "confidentialite", "a_propos")

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


def _all_pages():
    pages = [("fr", p) for p in _LOTO_PAGES]
    pages += [(lang, EM_URLS[lang][key]) for lang in _LANGS for key in _EM_PAGES]
    return pages


# ── G1 ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lang,path", _all_pages())
def test_g1_no_company_identity(client, lang, path):
    body = html.unescape(_get(client, path))
    assert not _FORBIDDEN.search(body), f"{path}: motif interdit {_FORBIDDEN.search(body).group(0)!r}"
    assert not _COMPANY.search(body), f"{path}: cadrage société {_COMPANY.search(body).group(0)!r}"


# ── G2 ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("key", ("mentions", "confidentialite"))
def test_g2_em_update_date(client, lang, key):
    body = html.unescape(_get(client, EM_URLS[lang][key]))
    assert _DATES[lang] in body, f"{lang} {key}: date « {_DATES[lang]} » absente"


@pytest.mark.parametrize("path", ("/mentions-legales", "/politique-confidentialite"))
def test_g2_loto_update_date(client, path):
    assert "Dernière mise à jour : 2 novembre 2026" in html.unescape(_get(client, path))


# ── G3 ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("path", ["/a-propos"] + [EM_URLS[lang]["a_propos"] for lang in _LANGS])
def test_g3_about_jsonld(client, path):
    raw = _get(client, path)
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', raw, re.S)
    assert blocks, f"{path}: aucun JSON-LD"
    orgs = []
    for b in blocks:
        data = json.loads(b)
        assert "parentOrganization" not in data, path
        assert "emovisia" not in json.dumps(data).lower(), path
        if data.get("@type") == "Organization":
            orgs.append(data)
    assert orgs and orgs[0]["name"] == "LotoIA", f"{path}: Organization LotoIA absente"


# ── G4 ────────────────────────────────────────────────────────────────────────
def _public_sources():
    roots = [_REPO / "ui", _REPO / "prompts", _REPO / "translations"]
    for root in roots:
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix not in {".html", ".txt", ".po", ".pot", ".js", ".json"}:
                continue
            rel = p.relative_to(_REPO).as_posix()
            if rel.startswith("ui/templates/admin/"):
                continue
            yield p


def test_g4_public_sources_clean():
    hits = []
    for p in _public_sources():
        text = p.read_text(encoding="utf-8", errors="replace")
        m = _FORBIDDEN.search(text)
        if m:
            hits.append(f"{p.relative_to(_REPO).as_posix()}: {m.group(0)}")
    assert not hits, "motifs interdits :\n" + "\n".join(hits)


# ── G5 ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lang", _LANGS)
def test_g5_em_rights_on_rgpd(client, lang):
    body = html.unescape(_get(client, EM_URLS[lang]["confidentialite"]))
    assert "(DPO)" not in body and "(DSB)" not in body, f"{lang}: DPO encore affiché"
    assert "rgpd@lotoia.fr" in body


def test_g5_loto_rights_on_rgpd(client):
    body = html.unescape(_get(client, "/mentions-legales"))
    assert "délégué à la protection des données" not in body
    assert "médiateur de la consommation" not in body
    assert body.count("rgpd@lotoia.fr") >= 2
