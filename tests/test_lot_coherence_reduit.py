"""
Tests — Lot cohérence réduit (1.6.062, 31/10/2026).

Pages, FAQ et méthodologie alignées sur le moteur (config/engine.py) sans aucun poids chiffré :
  G7  — aucune trace de l'ancien modèle 60/40 ni de pourcentage de pondération ;
  G8  — aucune somme fausse (100-150, 100 et 140, 70 et 150, ~125) ;
  G9  — vraies bornes de somme : 93-157 Loto, 94-161 EM ;
  G10 — 3 fenêtres décrites (« ensemble de l'historique disponible ») ;
  G11 — 11 msgid EM traduits dans les 5 langues, anciens msgid absents ;
  G12 — /meta-analyse-local (Loto + EM) sans « biais algorithmique », clé `analysis` conservée ;
  G14 — /methodologie charge version-inject.js ;
  G15 — rendu des pages EM × 6 langues et des pages Loto FR ;
  G16 — badge « Équilibre » sans critères pair/impair, bas/haut, somme, suites ;
  G17 — mode Récent jamais décrit par des tendances récentes (règle option 3).
Le test golden des pages intouchables (tests/test_seo_golden_intouchables.py) n'est pas modifié.
"""
import html
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from config.templates import EM_URLS

_REPO = Path(__file__).resolve().parent.parent
_LANGS = ("fr", "en", "es", "pt", "de", "nl")
_FOREIGN = ("en", "es", "pt", "de", "nl")

_LOTO_PAGES = ["ui/faq.html", "ui/methodologie.html", "ui/loto.html", "ui/accueil.html"]
_EM_TEMPLATES = {
    "methodologie": "ui/templates/em/methodologie.html",
    "faq": "ui/templates/em/faq.html",
    "accueil": "ui/templates/em/accueil.html",
    "generateur": "ui/templates/em/generateur.html",
    "disclaimer": "ui/templates/em/disclaimer.html",
}
_MODIFIED_FILES = _LOTO_PAGES + list(_EM_TEMPLATES.values())

# G7 — pondération chiffrée (ne touche pas les dégradés CSS « transparent 40% » ni « 100% gratuit »)
_FORBIDDEN_WEIGHTS = [
    r"\(\s*(?:60|40|70|30)\s?%\s*\)",           # « (60%) », « (40 %) »
    r"\b\d{2}\s?%\s*/\s*\d{2}\s?%",              # « 40% / 35% »
    r"\b(?:70/30|60/40|40/60|40/35/25|50/30/20|25/35/40)\b",
    r"\b(?:70|30)\s?% du score",
    r"\b(?:60|40)\s?% de pondération",
    r"\b50\s?% période",
]
# G8 — sommes fausses
_WRONG_SUMS = [r"100-150", r"100 et 140", r"100 à 140", r"70 et 150", r"~\s?125"]

# Nouveaux msgid FR (B1-B10, C3) : sous-chaîne distinctive → template
_NEW_MSGIDS = {
    "B1": ("methodologie", "Elle combine trois fenêtres d'analyse — les 5 dernières années"),
    "B2": ("methodologie", "Analyse de fréquence sur les 5 dernières années de tirages"),
    "B3": ("methodologie", "Analyse des 2 dernières années pour capter les tendances récentes ;"),
    "B4": ("methodologie", "Somme totale (plage de référence : 94 à 161"),
    "B5": ("methodologie", "Le moteur HYBRIDE combine trois fenêtres d'analyse, regroupées en deux couches"),
    "B6": ("methodologie", "Les 5 dernières années et l'ensemble de l'historique disponible des tirages EuroMillions"),
    "B7": ("methodologie", "Les 2 dernières années sont analysées à part."),
    "B8": ("methodologie", "désigne les fenêtres des 5 et des 2 dernières années"),
    "B9": ("faq", "le mode Équilibré répartit l'analyse entre les trois périodes"),
    "B10": ("accueil", "Il combine trois fenêtres d'analyse (5 dernières années, 2 dernières années et ensemble"),
    "C3": ("generateur", "pour générer des grilles de 5 numéros + 2 étoiles statistiquement"),
    "F1": ("faq", "%(total)s+ tirages historiques de l'EuroMillions. Le système combine analyse long terme, "),
    "F2": ("faq", "Le système combine analyse long terme, tendances récentes et ensemble de l'historique disponible "
                  "pour générer des grilles de <strong>"),
}
_OLD_MSGID_FRAGMENTS = [
    "Elle combine deux horizons temporels",
    "Analyse de fréquence sur l'ensemble de l'historique disponible (2019-2026)",
    "Pondération renforcée sur les 2 dernières années",
    "Somme totale (plage optimale : ~125)",
    "applique un système de pondération en deux couches",
    "L'historique complet des tirages EuroMillions est analysé",
    "reçoivent un coefficient de pondération plus élevé",
    "Ce double horizon est la raison du nom",
    "le mode Récent accentue les tendances des derniers tirages",
    "Il combine une pondération long terme (60%)",
    "Il combine analyse long terme (60%)",
    "Le système combine analyse long terme et tendances récentes",
]

# D1-D6 — disclaimer EM, ligne « pondération temporelle » par langue
_DISCLAIMER = {
    "fr": "Combinaison de trois fenêtres d'analyse : 5 dernières années, 2 dernières années et ensemble de "
          "l'historique disponible",
    "en": "Combination of three analysis windows: last 5 years, last 2 years and the entire available history",
    "es": "Combinacion de tres ventanas de analisis: ultimos 5 años, ultimos 2 años y el conjunto del "
          "historial disponible",
    "pt": "Combinacao de tres janelas de analise: ultimos 5 anos, ultimos 2 anos e o conjunto do historico "
          "disponivel",
    "de": "Kombination von drei Analysefenstern: letzte 5 Jahre, letzte 2 Jahre und gesamter verfugbarer Verlauf",
    "nl": "Combinatie van drie analysevensters: laatste 5 jaar, laatste 2 jaar en de volledige beschikbare "
          "geschiedenis",
}

# G17 — description du mode Récent : aucun vocabulaire « tendances récentes », par langue
_RECENT_FORBIDDEN = {
    "fr": r"tendance|derniers tirages|dernières années|actuel",
    "en": r"trend|latest draws|last \d years|current",
    "es": r"tendencia|últimos sorteos|últimos \d años|actual",
    "pt": r"tendência|últimos sorteios|últimos \d anos|atua",
    "de": r"Trend|jüngsten Ziehungen|letzten \d Jahre|aktuelle[nrs]?\b",
    "nl": r"trend|laatste trekkingen|laatste \d jaar|actue",
}


# ── Helpers ──────────────────────────────────────────────────────────────

def _read(rel: str) -> str:
    return (_REPO / rel).read_text(encoding="utf-8")


def _tpl_text(rel: str) -> str:
    """Template EM lu comme texte, apostrophes Jinja dé-échappées."""
    return _read(rel).replace("\\'", "'")


_CALL = re.compile(r"""_\(\s*'((?:[^'\\]|\\.)*)'\s*\)""")


def _new_msgid(key: str) -> str:
    page, fragment = _NEW_MSGIDS[key]
    for m in _CALL.finditer(_read(_EM_TEMPLATES[page])):
        s = m.group(1).replace("\\'", "'")
        if fragment in s:
            return s
    raise AssertionError(f"{key}: msgid introuvable dans {_EM_TEMPLATES[page]}")


def _po_entries(lang: str) -> dict:
    """msgid → (msgstr, fuzzy) ; parsing texte simple d'un .po."""
    path = _REPO / "translations" / lang / "LC_MESSAGES" / "messages.po"
    entries, msgid, msgstr, cur, fuzzy, pending = {}, None, None, None, False, False

    def _unq(s):
        return s.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#,") and "fuzzy" in line:
            pending = True
        elif line.startswith("msgid "):
            if msgid is not None:
                entries[msgid] = (msgstr or "", fuzzy)
            msgid, msgstr, cur, fuzzy, pending = _unq(line[7:-1]), None, "id", pending, False
        elif line.startswith("msgstr "):
            msgstr, cur = _unq(line[8:-1]), "str"
        elif line.startswith('"') and cur == "id":
            msgid += _unq(line[1:-1])
        elif line.startswith('"') and cur == "str":
            msgstr += _unq(line[1:-1])
    if msgid is not None:
        entries[msgid] = (msgstr or "", fuzzy)
    return entries


_PO_CACHE: dict = {}


def _po(lang: str) -> dict:
    if lang not in _PO_CACHE:
        _PO_CACHE[lang] = _po_entries(lang)
    return _PO_CACHE[lang]


def _expected_text(key: str, lang: str) -> str:
    msgid = _new_msgid(key)
    return msgid if lang == "fr" else _po(lang)[msgid][0]


# ── Client de test (pattern tests/test_seo_golden_intouchables.py) ─────────

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


def _get(client, path: str):
    with patch("db_cloudsql.get_connection", _async_cm_conn(_make_cursor())):
        return client.get(path)


def _assert_clean(text: str, where: str):
    for pattern in _FORBIDDEN_WEIGHTS:
        m = re.search(pattern, text)
        assert not m, f"{where}: pondération chiffrée « {m.group(0)} »"
    for pattern in _WRONG_SUMS:
        assert not re.search(pattern, text), f"{where}: somme fausse « {pattern} »"


# ═══════════════════════════════════════════════════════════════════════
# G7 / G8 — sources : ni 60/40, ni pourcentage de pondération, ni somme fausse
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("rel", _MODIFIED_FILES)
def test_sources_no_weights_no_wrong_sums(rel):
    _assert_clean(_read(rel), rel)


@pytest.mark.parametrize("lang", _FOREIGN)
def test_po_new_msgstr_no_weights(lang):
    for key in _NEW_MSGIDS:
        _assert_clean(_expected_text(key, lang), f"{lang}/{key}")


# ═══════════════════════════════════════════════════════════════════════
# G9 — vraies bornes de somme
# ═══════════════════════════════════════════════════════════════════════

def test_true_sum_bounds_loto_faq():
    text = _read("ui/faq.html")
    assert "93 et 157" in text and "93 à 157" in text


def test_true_sum_bounds_loto_methodologie():
    assert "93 à 157" in _read("ui/methodologie.html")


def test_true_sum_bounds_em_methodologie():
    assert "94 à 161" in _tpl_text("ui/templates/em/methodologie.html")


def test_true_sum_bounds_loto_prompt_badge():
    text = _read("prompts/chatbot/prompt_hybride.txt")
    line = next(ln for ln in text.splitlines() if ln.startswith("R : Ce badge indique"))
    assert "93 à 157" in line and "pénalisée, pas exclue" in line


# ═══════════════════════════════════════════════════════════════════════
# G10 — 3 fenêtres décrites
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("rel", ["ui/methodologie.html", "ui/templates/em/methodologie.html"])
def test_three_windows_described(rel):
    text = _tpl_text(rel)
    assert "trois fenêtres d'analyse" in text
    assert "ensemble de l'historique disponible" in text


def test_three_windows_faq_simulateur_answer():
    """G10 — 1re réponse « Fonctionnement Général » de /faq (visible + JSON-LD) : 3ᵉ fenêtre présente."""
    text = _read("ui/faq.html")
    start = text.index("<span>Comment fonctionne le simulateur de grilles Loto ?</span>")
    visible = text[start:text.index('<div class="faq-item">', start)]
    assert "<li><strong>Historique complet</strong> : Analyse de l'ensemble de l'historique disponible</li>" in visible
    m = re.search(r'"name": "Comment fonctionne le simulateur de grilles Loto \?",.*?"text": "([^"]*)"', text, re.S)
    assert m and "ensemble de l'historique disponible" in m.group(1)


@pytest.mark.parametrize("key", ["F1", "F2"])
def test_three_windows_em_faq_simulateur_answer(key):
    """G10 — FAQ EM « simulateur » (JSON-LD F1 + visible F2) : 3ᵉ fenêtre, en FR et dans les 5 .po."""
    assert "analyse long terme, tendances récentes et ensemble de l'historique disponible" in _new_msgid(key)
    for lang in _FOREIGN:
        assert _expected_text(key, lang) != _new_msgid(key)


# ═══════════════════════════════════════════════════════════════════════
# G11 — msgid EM traduits, anciens msgid absents
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lang", _LANGS)
def test_po_new_msgids_present(lang):
    entries = _po(lang)
    for key in _NEW_MSGIDS:
        msgid = _new_msgid(key)
        assert msgid in entries, f"{lang}: msgid {key} absent"
        msgstr, fuzzy = entries[msgid]
        assert not fuzzy, f"{lang}: msgid {key} fuzzy"
        if lang != "fr":
            assert msgstr.strip(), f"{lang}: msgstr {key} vide"
            assert msgstr != msgid, f"{lang}: msgstr {key} non traduit"


@pytest.mark.parametrize("lang", _LANGS)
def test_po_old_msgids_gone(lang):
    ids = list(_po(lang))
    for fragment in _OLD_MSGID_FRAGMENTS:
        assert not any(fragment in i for i in ids), f"{lang}: ancien msgid encore présent « {fragment} »"


@pytest.mark.parametrize("lang", _FOREIGN)
def test_po_markup_preserved(lang):
    for key in ("B1", "B8"):
        assert _expected_text(key, lang).count("<strong>") == 1


# ═══════════════════════════════════════════════════════════════════════
# G12 — /meta-analyse-local sans « biais algorithmique »
# ═══════════════════════════════════════════════════════════════════════

def _meta_cursor(n_balls: int, secondary_rows: list):
    cursor = AsyncMock()
    cursor.fetchone.side_effect = [
        {"total": 1014},
        {"min_date": date(2019, 11, 6), "max_date": date(2026, 10, 28)},
    ]
    cursor.fetchall.side_effect = [
        [{"id": i} for i in range(1, 1015)],
        [{"num": i, "freq": 100} for i in range(1, n_balls + 1)],
        [],
        secondary_rows,
    ]
    return cursor


@pytest.mark.parametrize("path, n_balls, secondary", [
    ("/api/loto/meta-analyse-local?window=GLOBAL", 49,
     [{"num": i, "freq": 101} for i in range(1, 10)] + [{"num": 10, "freq": 105}]),
    ("/api/euromillions/meta-analyse-local?window=GLOBAL", 50,
     [{"num": i, "freq": 169} for i in range(1, 13)]),
])
@patch("routes.api_analyse_unified.get_persistent_brake_map", new=AsyncMock(return_value={}))
@patch("routes.api_analyse_unified.get_decay_state", new=AsyncMock(return_value={}))
@patch("routes.api_analyse_unified.check_and_update_decay", new=AsyncMock(return_value=None))
def test_meta_analyse_local_no_bias_claim(client, path, n_balls, secondary):
    with patch("routes.api_analyse_unified.db_cloudsql") as mock_db:
        mock_db.get_connection = _async_cm_conn(_meta_cursor(n_balls, secondary))
        resp = client.get(path)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    analysis = data["analysis"]
    assert "biais" not in analysis.lower()
    assert analysis.endswith(").")
    assert ".." not in analysis and not analysis.endswith(" ")


# ═══════════════════════════════════════════════════════════════════════
# G14 — version dynamique du pied de page /methodologie
# ═══════════════════════════════════════════════════════════════════════

def test_methodologie_loads_version_inject():
    assert '<script src="/ui/static/version-inject.js" defer></script>' in _read("ui/methodologie.html")


# ═══════════════════════════════════════════════════════════════════════
# G15 — rendu : pages EM × 6 langues, pages Loto FR
# ═══════════════════════════════════════════════════════════════════════

_PAGE_KEYS = {
    "methodologie": ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"],
    "faq": ["B9", "F2"],
    "accueil": ["B10"],
    "generateur": ["C3"],
    "disclaimer": [],
}


@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("page", list(_PAGE_KEYS))
def test_em_page_rendered(client, page, lang):
    path = EM_URLS[lang][page]
    resp = _get(client, path)
    assert resp.status_code == 200, f"{path}: HTTP {resp.status_code}"
    body = html.unescape(resp.text)
    _assert_clean(body, path)
    for key in _PAGE_KEYS[page]:
        expected = _expected_text(key, lang)
        assert expected in body, f"{path}: texte {key} ({lang}) absent"
    if page == "disclaimer":
        assert _DISCLAIMER[lang] in body, f"{path}: ligne disclaimer ({lang}) absente"
    if lang != "fr":
        for key in _NEW_MSGIDS:
            assert _new_msgid(key) not in body, f"{path}: msgid FR {key} visible en {lang}"
        if page == "disclaimer":
            assert _DISCLAIMER["fr"] not in body


def _jsonld_answers(body: str) -> list[str]:
    """Textes des réponses FAQPage des blocs JSON-LD d'une page rendue."""
    answers = []
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S):
        data = json.loads(raw)
        for item in data.get("mainEntity", []) if isinstance(data, dict) else []:
            text = item.get("acceptedAnswer", {}).get("text") if isinstance(item, dict) else None
            if text:
                answers.append(text)
    return answers


@pytest.mark.parametrize("lang", _LANGS)
def test_em_faq_jsonld_simulator_answer(client, lang):
    """G15 — JSON-LD FAQ EM (F1, |format|tojson) : texte traduit présent, aucun texte FR hors FR."""
    resp = _get(client, EM_URLS[lang]["faq"])
    assert resp.status_code == 200
    answers = _jsonld_answers(resp.text)
    head, tail = _expected_text("F1", lang).split("%(total)s")
    assert any(a.startswith(head) and a.endswith(tail) for a in answers), f"{lang}: réponse F1 absente du JSON-LD"
    if lang != "fr":
        fr_tail = _new_msgid("F1").split("%(total)s")[1]
        assert not any(fr_tail in a for a in answers), f"{lang}: texte FR F1 dans le JSON-LD"


@pytest.mark.parametrize("path", ["/faq", "/methodologie", "/loto", "/accueil"])
def test_loto_page_rendered(client, path):
    resp = _get(client, path)
    assert resp.status_code == 200, f"{path}: HTTP {resp.status_code}"
    _assert_clean(html.unescape(resp.text), path)


# ═══════════════════════════════════════════════════════════════════════
# G16 — badge « Équilibre » (FAQ Loto)
# ═══════════════════════════════════════════════════════════════════════

def test_badge_equilibre_no_false_criteria():
    text = _read("ui/faq.html")
    start = text.index('<span>Que signifie "Équilibre" ?</span>')
    block = text[start:text.index('<div class="faq-item">', start)]
    for word in ("Pair/Impair", "Bas/Haut", "Somme", "Suites"):
        assert word not in block, f"badge Équilibre : critère « {word} » encore présent"
    assert "Il ne dépend ni de la somme ni de la parité." in block


# ═══════════════════════════════════════════════════════════════════════
# G17 — mode Récent : jamais « tendances récentes »
# ═══════════════════════════════════════════════════════════════════════

def test_recent_mode_faq_visible():
    text = _read("ui/faq.html")
    line = next(ln for ln in text.splitlines() if "<li><strong>Récent</strong>" in ln)
    assert not re.search(_RECENT_FORBIDDEN["fr"], line, re.IGNORECASE), line.strip()


def test_recent_mode_faq_jsonld():
    text = _read("ui/faq.html")
    m = re.search(r"Récent : ([^.]*)\.", text)
    assert m, "JSON-LD : description « Récent : … » absente"
    assert not re.search(_RECENT_FORBIDDEN["fr"], m.group(1), re.IGNORECASE), m.group(0)


@pytest.mark.parametrize("lang", _LANGS)
def test_recent_mode_em_faq_msgid(lang):
    text = _expected_text("B9", lang)
    assert not re.search(_RECENT_FORBIDDEN[lang], text, re.IGNORECASE if lang != "de" else 0), \
        f"{lang}: description des modes liée aux tendances récentes : {text}"
