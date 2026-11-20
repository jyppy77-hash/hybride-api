"""
Tests — LOT 1.6.075 « audit journaliste » (Release 1.6.075, 21/11/2026).

Couvre :
  T1  version : APP_VERSION 1.6.075, VERSION_DATE 2026-11-21 ;
  T2  garde de version : tout <span class="app-version">vX</span> en dur d'un gabarit servi = APP_VERSION
      (aucune variable de version dans le contexte global Jinja, pages Loto statiques) ;
  T3  absences : « depuis novembre 2019 » et « v1.5.004 » (gabarits servis + .po), « 1.001 » (news Loto + EM
      + .po), « Grounded » / « grounding » / « connecté en temps réel » / « Connexion temps réel » (pages F et
      D6, launcher hors <style>), « (à cette date) » (gabarits servis + .po actifs), « 729 / 981 tirages »
      (news servies) ;
  T4  présences : FAQ A (Loto + EM), mention B (21/11), « sur les 7 dernières années », phrase F, D5, D7 ;
      dateModified 2026-11-21 des articles modifiés, datePublished de l'article B, LAST_NEWS_DATE ;
  T5  FAQ A : question et réponse identiques entre HTML visible et JSON-LD FAQPage (Loto + EM 6 langues) ;
  T6  ZÉRO string FR visible : chaînes FR du lot absentes des pages EM rendues (EN/ES/PT/DE/NL), pages hybride,
      faq, à-propos, news, euromillions-ia, générateur, simulateur, statistiques ;
  T7  aucune pondération du score (40 / 35 / 25 %) dans les pages HYBRIDE, FAQ, Méthodologie, Moteur ;
  T8  .po : msgid du lot présents une fois, msgstr remplis hors FR, aucun fuzzy, anciens msgid absents.

Hors assertions : classes CSS .grounded-* et commentaire CSS du launcher (non visibles), prompts du chatbot,
textes générés par services/loto_key_figures.py et loto_top_numbers.py.
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

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
EM_TPL = UI / "templates" / "em"

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})

LANGS = ("fr", "en", "es", "pt", "de", "nl")
NON_FR = ("en", "es", "pt", "de", "nl")

# Pages Loto FR statiques servies (ui/index.html = legacy en 301 ; ui/em/ et ui/en/ = legacy non servis)
LOTO_SERVED = sorted(p for p in UI.glob("*.html") if p.name != "index.html")
EM_SERVED = sorted(EM_TPL.glob("*.html"))

LOTO_F_PAGES = ("faq.html", "a-propos.html", "hybride.html", "methodologie.html",
                "loto-ia.html", "loto.html", "simulateur.html", "statistiques.html", "news.html")  # + D6
EM_F_PAGES = ("faq.html", "a-propos.html", "hybride.html", "methodologie.html",
              "euromillions-ia.html", "generateur.html", "simulateur.html", "statistiques.html", "news.html")  # + D6
LAUNCHER = UI / "templates" / "launcher.html"

EM_PATHS = {
    "hybride": {"fr": "/euromillions/hybride", "en": "/en/euromillions/hybride", "es": "/es/euromillions/hybride",
                "pt": "/pt/euromillions/hybride", "de": "/de/euromillions/hybride",
                "nl": "/nl/euromillions/hybride"},
    "faq": {lg: ("/euromillions/faq" if lg == "fr" else f"/{lg}/euromillions/faq") for lg in LANGS},
    "a_propos": {"fr": "/euromillions/a-propos", "en": "/en/euromillions/about", "es": "/es/euromillions/acerca-de",
                 "pt": "/pt/euromillions/sobre", "de": "/de/euromillions/ueber-uns",
                 "nl": "/nl/euromillions/over-ons"},
    "news": {"fr": "/euromillions/news", "en": "/en/euromillions/news", "es": "/es/euromillions/noticias",
             "pt": "/pt/euromillions/noticias", "de": "/de/euromillions/nachrichten",
             "nl": "/nl/euromillions/nieuws"},
    # D6
    "ia": {"fr": "/euromillions/intelligence-artificielle", "en": "/en/euromillions/artificial-intelligence",
           "es": "/es/euromillions/inteligencia-artificial", "pt": "/pt/euromillions/inteligencia-artificial",
           "de": "/de/euromillions/kuenstliche-intelligenz", "nl": "/nl/euromillions/kunstmatige-intelligentie"},
    "generateur": {"fr": "/euromillions/generateur", "en": "/en/euromillions/generator",
                   "es": "/es/euromillions/generador", "pt": "/pt/euromillions/gerador",
                   "de": "/de/euromillions/generator", "nl": "/nl/euromillions/generator"},
    "simulateur": {"fr": "/euromillions/simulateur", "en": "/en/euromillions/simulator",
                   "es": "/es/euromillions/simulador", "pt": "/pt/euromillions/simulador",
                   "de": "/de/euromillions/simulator", "nl": "/nl/euromillions/simulator"},
    "statistiques": {"fr": "/euromillions/statistiques", "en": "/en/euromillions/statistics",
                     "es": "/es/euromillions/estadisticas", "pt": "/pt/euromillions/estatisticas",
                     "de": "/de/euromillions/statistiken", "nl": "/nl/euromillions/statistieken"},
}

# ── Textes du lot ─────────────────────────────────────────────────────────

A_Q = "HYBRIDE peut-il me donner des numéros gagnants ?"
A_R_LOTO = (
    "Non. Personne ne peut prédire un tirage : chaque combinaison a exactement la même probabilité de sortir "
    "(1 sur 19 068 840 au Loto, 1 sur 139 838 160 à l'EuroMillions). HYBRIDE peut générer des grilles à votre "
    "demande : le moteur les construit à partir des statistiques des tirages passés (fréquences, écarts, "
    "équilibre de la grille). Ce sont des grilles générées, pas des pronostics : elles n'ont pas plus de chances "
    "de gagner qu'une grille choisie au hasard. Le score sur 100 affiché avec une grille indique seulement à quel "
    "point elle respecte les critères statistiques du moteur ; ce n'est pas une probabilité de gain."
)
A_R_EM = A_R_LOTO.replace("(1 sur 19 068 840 au Loto, 1 sur 139 838 160 à l'EuroMillions)",
                          "(1 sur 139 838 160 à l'EuroMillions)")
B_NOTE = "Article mis à jour le 21 novembre 2026."
E_NEW = "sur les 7 dernières années"
F_TARGET = "ancrées sur la base officielle des tirages, mise à jour après chaque tirage"
D5_TXT = "le serveur récupère d'abord les données pertinentes dans la base, puis le modèle rédige sa réponse"
D7_TXT = "les grilles qu'il génère ne sont pas des pronostics"
ACCROCHE_LOTO = ("Notre chatbot intelligent répond à vos questions sur les statistiques du Loto. Ses réponses sont "
                 "ancrées sur la base officielle des tirages, mise à jour après chaque tirage.")

# msgid FR du lot (nouveaux) et anciens msgid retirés (extraits)
NEW_MSGIDS = [
    A_Q, A_R_EM, B_NOTE,
    "Une IA ancrée sur les tirages officiels",
    "Sur quelles données s'appuient les réponses de LotoIA ?",
    "Des réponses ancrées sur les données officielles",
    "Comment HYBRIDE accède aux données",
    "<strong>Il interroge la base de données</strong> Cloud SQL",
    "HYBRIDE — Chatbot IA pour l'EuroMillions | LotoIA",
    "HYBRIDE — Chatbot IA EuroMillions | LotoIA",
    "Réponses ancrées sur les %(total)s+ tirages officiels EuroMillions, base mise à jour après chaque tirage",
    # phase B
    "Réponses ancrées sur les tirages officiels",
    "Explorez l'espace combinatoire avec le moteur HYBRIDE de LotoIA.",
    "Il <strong>ne donne PAS</strong> de « numéros magiques » : les grilles qu'il génère ne sont pas des pronostics",
    "<strong>L'historique officiel des tirages</strong> en base de données sécurisée, alimentant l'ensemble des "
    "analyses du moteur EuroMillions.",
    "Notre chatbot intelligent répond à vos questions sur les statistiques de l'EuroMillions. Ses réponses sont "
    "ancrées sur la base officielle des tirages, mise à jour après chaque tirage.",
]
OLD_MSGIDS = [
    # phase B
    "Technologie IA Grounded",
    "Article mis à jour le 9 novembre 2026.",
    "Explorez l'espace combinatoire avec le moteur HYBRIDE — LotoIA v1.5.0.",
    "Notre chatbot intelligent analyse les tirages EuroMillions en temps réel grâce à l'IA Grounded. Posez vos "
    "questions sur les statistiques.",
    "Le chatbot peut-il prédire les résultats EuroMillions ?",
    "L'IA Grounded",
    "Qu'est-ce que la technologie « IA Grounded » de LotoIA ?",
    "Qu'est-ce qu'une IA « Grounded » ?",
    "Comment HYBRIDE accède aux données en temps réel",
    "Connexion temps réel aux %(total)s+ tirages officiels EuroMillions",
]

# Chaînes FR qui ne doivent jamais apparaître dans une page EM rendue hors FR
FR_FORBIDDEN_NON_FR = [
    A_Q, "Personne ne peut prédire un tirage", "Ce sont des grilles générées", B_NOTE,
    F_TARGET, "Une IA ancrée sur les tirages officiels",
    "Sur quelles données s'appuient", "Des réponses ancrées sur les données officielles",
    "Comment HYBRIDE accède aux données", "sur les 7 dernières années",
    "Le chatbot peut-il prédire", "Qu'est-ce qu'une IA", "depuis novembre 2019", "connecté en temps réel",
    # phase B
    "le serveur récupère", D7_TXT, "L'historique officiel des tirages", "l'historique des tirages officiels",
    "notre base des tirages officiels", "Notre chatbot intelligent répond", "s'appuyant sur une base de données",
    "Article mis à jour le 9 novembre 2026", "moteur HYBRIDE de LotoIA", "Réponses ancrées sur les tirages officiels",
]


# ── Helpers ───────────────────────────────────────────────────────────────

def _read(p: Path) -> str:
    return p.read_bytes().decode("utf-8")


def _unesc(s: str) -> str:
    return s.replace("\\'", "'")


def _strip(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _po(lang: str):
    with open(ROOT / "translations" / lang / "LC_MESSAGES" / "messages.po", "rb") as f:
        return read_po(f, locale=lang)


def _active(cat):
    return [m for m in cat if m.id and isinstance(m.id, str)]


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


_CACHE: dict[str, str] = {}


def _page(client, path: str) -> str:
    if path not in _CACHE:
        with patch("db_cloudsql.get_connection", _async_cm_conn(_make_cursor())), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
            resp = client.get(path)
        assert resp.status_code == 200, f"{path} → {resp.status_code}"
        _CACHE[path] = resp.text
    return _CACHE[path]


def _visible(page: str) -> str:
    """Texte visible : sans <script>, <style>, <head>, commentaires."""
    body = re.sub(r"<head\b.*?</head>", " ", page, flags=re.S | re.I)
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    return _strip(body)


def _faq_ld(page: str) -> list[dict]:
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        data = json.loads(block)
        if data.get("@type") == "FAQPage":
            return data["mainEntity"]
    raise AssertionError("FAQPage absent")


def _visible_qa(page: str, question: str) -> str:
    m = re.search(r"<h3>\s*" + re.escape(html.escape(question, quote=False)) + r"\s*</h3>\s*<p>(.*?)</p>",
                  page.replace("&#39;", "'"), re.S)
    assert m, f"Q visible introuvable : {question}"
    return _strip(m.group(1))


# ═══════════════════════════════════════════════════════
# T1 — version
# ═══════════════════════════════════════════════════════

def test_t1_version_config():
    from config.version import APP_VERSION, VERSION_DATE
    assert APP_VERSION == "1.6.075"
    assert VERSION_DATE == "2026-11-21"


# ═══════════════════════════════════════════════════════
# T2 — garde de version des pieds de page
# ═══════════════════════════════════════════════════════

def test_t2_footer_version_matches_config():
    """Toute valeur en dur de .app-version dans un gabarit servi = APP_VERSION (garde pour les bumps)."""
    from config.version import APP_VERSION
    seen = 0
    for p in LOTO_SERVED + EM_SERVED:
        for val in re.findall(r'<span class="app-version">([^<]*)</span>', _read(p)):
            if val == "":
                continue  # paires.html : vide, rempli par version-inject.js
            seen += 1
            assert val == f"v{APP_VERSION}", f"{p.name} : {val} ≠ v{APP_VERSION}"
    assert seen >= 18


# ═══════════════════════════════════════════════════════
# T3 — absences
# ═══════════════════════════════════════════════════════

@pytest.mark.parametrize("p", LOTO_SERVED + EM_SERVED, ids=lambda p: p.relative_to(UI).as_posix())
def test_t3_no_depuis_novembre_2019_nor_old_version(p):
    txt = _unesc(_read(p))
    assert "depuis novembre 2019" not in txt
    assert "v1.5.004" not in txt


@pytest.mark.parametrize("p", [UI / f for f in LOTO_F_PAGES] + [EM_TPL / f for f in EM_F_PAGES],
                         ids=lambda p: p.relative_to(UI).as_posix())
def test_t3_no_grounded_nor_realtime_connection(p):
    txt = _unesc(_read(p))
    assert "Grounded" not in txt
    assert "grounding" not in txt
    assert "connecté en temps réel" not in txt
    assert "Connexion temps réel" not in txt
    assert "accède aux données en temps réel" not in txt
    assert "grâce à l'IA Grounded" not in txt


def test_t3_launcher_no_grounded_outside_css():
    """D6 : libellé du badge sans « Grounded » ; classes CSS .grounded-* et commentaire CSS non visibles."""
    txt = re.sub(r"<style\b.*?</style>", " ", _read(LAUNCHER), flags=re.S)
    assert "Grounded" not in txt and "grounding" not in txt
    assert '_("Réponses ancrées sur les tirages officiels")' in txt
    assert 'class="grounded-label"' in txt  # classes conservées


def test_t3_no_1001_in_news():
    for p in (UI / "news.html", EM_TPL / "news.html"):
        assert "1.001" not in _read(p), p.name


@pytest.mark.parametrize("p", LOTO_SERVED + EM_SERVED, ids=lambda p: p.relative_to(UI).as_posix())
def test_t3_no_a_cette_date(p):
    assert "(à cette date" not in _read(p)


def test_t3_no_dated_counters_in_news():
    for p in (UI / "news.html", EM_TPL / "news.html"):
        assert not re.search(r"\b(729|981) tirages", _read(p)), p.name


@pytest.mark.parametrize("lang", LANGS)
def test_t3_po_active_entries_clean(lang):
    for m in _active(_po(lang)):
        for s in (m.id, m.string):
            if not s:
                continue
            assert "depuis novembre 2019" not in s
            assert "1.001" not in s, m.id[:60]
            assert "(à cette date" not in s, m.id[:60]


# ═══════════════════════════════════════════════════════
# T4 — présences
# ═══════════════════════════════════════════════════════

def test_t4_loto_texts_present():
    hyb = _read(UI / "hybride.html")
    assert hyb.count(A_Q) == 2
    assert hyb.count(A_R_LOTO) == 1  # JSON-LD (le visible porte <strong>Non.</strong>, texte égal : T5)
    assert hyb.count("<p><strong>Non.</strong> " + A_R_LOTO[len("Non. "):] + "</p>") == 1
    news = _read(UI / "news.html")
    art = re.search(r"EuroMillions arrive sur LotoIA — 15 mars 2026</h2>(.*?)</article>", news, re.S).group(1)
    assert f"<p><em>{B_NOTE}</em></p>" in art
    assert '"datePublished": "2026-02-14"' in news  # date de publication inchangée
    assert '<span class="news-date">14 février 2026</span>' in news
    for name in ("a-propos.html", "faq.html", "hybride.html"):
        assert F_TARGET in _read(UI / name), name
    total_e = sum(_read(UI / n).count(E_NEW) for n in ("a-propos.html", "disclaimer.html", "faq.html",
                                                        "hybride.html", "methodologie.html", "statistiques.html"))
    assert total_e == 10
    assert D5_TXT in hyb and D7_TXT in hyb
    for name in ("loto.html", "simulateur.html", "statistiques.html"):
        assert ACCROCHE_LOTO in _read(UI / name), name
    assert "<p>Explorez l'espace combinatoire avec le moteur HYBRIDE de LotoIA.</p>" in news


def test_t4_em_templates_present():
    hyb = _unesc(_read(EM_TPL / "hybride.html"))
    assert hyb.count(f"_('{A_Q}')") == 2 and hyb.count(f"_('{A_R_EM}')") == 2
    assert f"_('{B_NOTE}')" in _unesc(_read(EM_TPL / "news.html"))
    for name in ("a-propos.html", "faq.html", "hybride.html", "euromillions-ia.html", "generateur.html",
                 "simulateur.html", "statistiques.html"):
        assert F_TARGET in _unesc(_read(EM_TPL / name)), name
    assert D5_TXT in hyb and D7_TXT in hyb


def test_t4_news_dates():
    """D2 : dateModified 2026-11-21 des articles modifiés présents dans le JSON-LD ; publication inchangée."""
    loto = _read(UI / "news.html")
    for pub in ("2026-03-15", "2026-02-14", "2026-02-11"):
        assert re.search(rf'"datePublished": "{pub}",\s*"dateModified": "2026-11-21"', loto), pub
    em = _read(EM_TPL / "news.html")
    for pub in ("2026-03-15", "2026-02-14", "2026-02-11", "2026-02-10"):
        assert f'"datePublished": "{pub}", "dateModified": "2026-11-21",' in em, pub
    for text in (loto, em):
        assert text.count('"datePublished": "2026-02-14"') == 1
    from config.version import LAST_NEWS_DATE
    assert LAST_NEWS_DATE == "2026-11-21"


# ═══════════════════════════════════════════════════════
# T5 — FAQ A : HTML visible == JSON-LD
# ═══════════════════════════════════════════════════════

def test_t5_loto_faq_html_equals_jsonld():
    page = _read(UI / "hybride.html")
    entry = next(e for e in _faq_ld(page) if e["name"] == A_Q)
    assert entry["acceptedAnswer"]["text"] == A_R_LOTO
    assert _visible_qa(page, A_Q) == A_R_LOTO


@pytest.mark.parametrize("lang", LANGS)
def test_t5_em_faq_html_equals_jsonld(client, lang):
    page = _page(client, EM_PATHS["hybride"][lang])
    entries = _faq_ld(page)
    # la question A est la 2e entrée du FAQPage (ordre du gabarit)
    q, a = entries[1]["name"], entries[1]["acceptedAnswer"]["text"]
    assert _visible_qa(page, q) == a
    if lang == "fr":
        assert (q, a) == (A_Q, A_R_EM)
    else:
        assert q != A_Q and a != A_R_EM
        assert "139" in a and "838" in a and "160" in a


# ═══════════════════════════════════════════════════════
# T6 — ZÉRO string FR visible (pages EM touchées, hors FR)
# ═══════════════════════════════════════════════════════

@pytest.mark.parametrize("page_key", list(EM_PATHS))
@pytest.mark.parametrize("lang", NON_FR)
def test_t6_zero_fr_string(client, lang, page_key):
    page = _page(client, EM_PATHS[page_key][lang])
    full = html.unescape(page).replace("&#39;", "'")
    for s in FR_FORBIDDEN_NON_FR:
        assert s not in full, f"{lang} {page_key} : « {s} »"
    visible = re.sub(r"<style\b.*?</style>", " ", full, flags=re.S | re.I)
    assert "Grounded" not in visible and "grounding" not in visible.lower()


@pytest.mark.parametrize("page_key", list(EM_PATHS))
def test_t6_fr_em_pages_render_new_texts(client, page_key):
    full = html.unescape(_page(client, EM_PATHS[page_key]["fr"])).replace("&#39;", "'")
    expected = {"hybride": A_Q, "faq": F_TARGET, "a_propos": E_NEW, "news": B_NOTE, "ia": F_TARGET,
                "generateur": F_TARGET, "simulateur": F_TARGET, "statistiques": F_TARGET}[page_key]
    assert expected in full
    visible = re.sub(r"<style\b.*?</style>", " ", full, flags=re.S | re.I)
    assert "Grounded" not in visible


# ═══════════════════════════════════════════════════════
# T7 — aucune pondération publique du score
# ═══════════════════════════════════════════════════════

_WEIGHT_RE = re.compile(r"\b(40|35|25)\s?(?:&nbsp;| | )?%")


@pytest.mark.parametrize("name", ("hybride.html", "faq.html", "methodologie.html", "moteur.html"))
def test_t7_no_weighting_loto(name):
    assert not _WEIGHT_RE.search(_read(UI / name)), name


@pytest.mark.parametrize("lang", LANGS)
def test_t7_no_weighting_em(client, lang):
    for key in ("hybride", "faq"):
        assert not _WEIGHT_RE.search(_page(client, EM_PATHS[key][lang])), (lang, key)


# ═══════════════════════════════════════════════════════
# T8 — catalogues
# ═══════════════════════════════════════════════════════

@pytest.mark.parametrize("lang", LANGS)
def test_t8_po_catalogs(lang):
    cat = _po(lang)
    ids = [m.id for m in _active(cat)]
    for mid in NEW_MSGIDS:
        assert ids.count(mid) == 1, (lang, mid[:60])
        msg = cat.get(mid)
        assert not msg.fuzzy, (lang, mid[:60])
        if lang != "fr":
            assert msg.string, (lang, mid[:60])
            assert "Grounded" not in msg.string and "grounding" not in msg.string.lower()
    for mid in OLD_MSGIDS:
        assert mid not in ids, (lang, mid)
