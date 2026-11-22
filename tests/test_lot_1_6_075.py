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
  T8  .po : msgid du lot présents une fois, msgstr remplis hors FR, aucun fuzzy, anciens msgid absents ;
  C   dette i18n préexistante (phases C-A et C-B) : passages A1-A7 (euromillions-ia) et B1-B3 (hybride)
      traduits en EN, boutons « Voir tous les numéros / toutes les étoiles » des statistiques EM et libellés JS
      « Voir moins / Voir les dates / Masquer les dates » (statistiques, paires) traduits (5 langues),
      contrôle « page entière » (nœuds de texte visibles identiques à la page FR) sur euromillions-ia, hybride,
      statistiques et paires × 5 langues (20 pages), sans exception ;
  D   audit journaliste du 21/11 : R-4 « Tout refuser » lisible dans le panneau et le bandeau de consentement
      (règle CSS dédiée, ratios WCAG calculés, cache-buster legal.css unique ?v=16 sur toutes les références
      servies) ; R-5 phrase « 2089 tests automatiques … Zéro régression possible » remplacée (Loto + EM 6 langues) ;
      R-6 « premier chatbot » retiré (titre, headline JSON-LD = titre visible, corps, .po) ; R-10 pied EM (lien
      disclaimer identique dans les 6 langues, libellé DE « Haftungsausschluss », pied DE sans texte FR) ; ZÉRO FR sur les pages news EM.

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
    assert tuple(int(p) for p in APP_VERSION.split(".")) >= (1, 6, 75)  # plancher (lot 1.6.076)
    assert VERSION_DATE >= "2026-11-21"


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
    # phase D (R-5) : + article Release 1.5.0 du 11/03 (Loto ; absent du JSON-LD EM)
    for pub in ("2026-03-15", "2026-02-14", "2026-02-11", "2026-03-11"):
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


# ═══════════════════════════════════════════════════════
# C — dette i18n préexistante (présente en prod 1.6.074) : msgstr EN vides (A1-A6 euromillions-ia,
# B1-B3 hybride) et msgid absents des 6 .po (C : boutons « Voir tous les numéros / toutes les étoiles »
# des statistiques EM, aussi repris par l'objet i18n JS de la page via |tojson).
# Phase C-B : A7 (euromillions-ia.html:169, msgstr EN vide) ; libellés JS « Voir moins », « Voir les dates »,
# « Masquer les dates » (objets i18n inline de statistiques.html et paires.html, msgid absents des 6 .po).
# ═══════════════════════════════════════════════════════

_C_TPL = {  # code -> (gabarit, ligne du _('…'))
    "A1": ("euromillions-ia.html", 126), "A2": ("euromillions-ia.html", 153), "A3": ("euromillions-ia.html", 162),
    "A4": ("euromillions-ia.html", 215), "A5": ("euromillions-ia.html", 226), "A6": ("euromillions-ia.html", 235),
    "A7": ("euromillions-ia.html", 169),
    "B1": ("hybride.html", 277), "B2": ("hybride.html", 295), "B3": ("hybride.html", 353),
}
_C_EN = {  # extraits des msgstr EN ajoutés
    "A1": "This article looks at what artificial intelligence can",
    "A2": "AI identifies which numbers (1-50) and which stars (1-12)",
    "A3": "evaluates your selection against objective criteria",
    "A4": "LotoIA is a dedicated tool, built for analysing EuroMillions and Loto draws",
    "A5": "Find out more on the",
    "A6": "LotoIA is an independent project whose mission is to make statistics accessible",
    "A7": "is LotoIA's algorithmic core",
    "B1": "HYBRIDE is not a decorative chatbot",
    "B2": "as the data shown on the",
    "B3": "This honesty is not a limitation",
}
_C_LABELS = {"Voir tous les numéros": {"en": "View all numbers", "es": "Ver todos los números",
                                       "pt": "Ver todos os números", "de": "Alle Zahlen anzeigen",
                                       "nl": "Alle nummers bekijken"},
             "Voir toutes les étoiles": {"en": "View all stars", "es": "Ver todas las estrellas",
                                         "pt": "Ver todas as estrelas", "de": "Alle Sterne anzeigen",
                                         "nl": "Alle sterren bekijken"}}
# Libellés posés par le JS inline (objets STRINGS / PS, |tojson), visibles après interaction
_C_JS_LABELS = {"Voir moins": {"en": "Show less", "es": "Ver menos", "pt": "Ver menos", "de": "Weniger anzeigen",
                               "nl": "Minder bekijken"},
                "Voir les dates": {"en": "Show dates", "es": "Ver las fechas", "pt": "Ver as datas",
                                   "de": "Daten anzeigen", "nl": "Datums bekijken"},
                "Masquer les dates": {"en": "Hide dates", "es": "Ocultar las fechas", "pt": "Ocultar as datas",
                                      "de": "Daten ausblenden", "nl": "Datums verbergen"}}
_C_PATHS = {**EM_PATHS,
            "paires": {"fr": "/euromillions/paires", "en": "/en/euromillions/pairs", "es": "/es/euromillions/pares",
                       "pt": "/pt/euromillions/pares", "de": "/de/euromillions/paare",
                       "nl": "/nl/euromillions/paren"}}
_C_TAG_OR_PH = re.compile(r"%\(\w+\)s|<[^>]+>")


def _c_msgid(code: str) -> str:
    name, line = _C_TPL[code]
    src = _read(EM_TPL / name).splitlines()[line - 1]
    m = re.search(r"_\('((?:[^'\\]|\\.)*)'\)", src)
    assert m, (code, name, line)
    return _unesc(m.group(1))


def _c_fr_fragment(code: str) -> str:
    """40 premiers caractères du plus long segment du msgid sans balise ni placeholder."""
    seg = max(_C_TAG_OR_PH.split(_c_msgid(code)), key=len)
    return " ".join(seg.split())[:40]


@pytest.mark.parametrize("code", list(_C_TPL))
def test_c1_en_fr_passages_translated(client, code):
    key = "ia" if code.startswith("A") else "hybride"
    visible = _visible(_page(client, EM_PATHS[key]["en"]))
    frag = _c_fr_fragment(code)
    assert len(frag) == 40
    assert frag not in visible, f"{code} : « {frag} »"
    assert _C_EN[code] in visible, code
    # la page FR garde le texte source
    assert frag in _visible(_page(client, EM_PATHS[key]["fr"])), code


@pytest.mark.parametrize("lang", NON_FR)
def test_c2_stats_buttons_translated(client, lang):
    page = _page(client, EM_PATHS["statistiques"][lang])
    full = html.unescape(page)
    for fr, tr in _C_LABELS.items():
        assert fr not in full, (lang, fr)
        assert json.dumps(fr)[1:-1] not in page, (lang, fr, "objet i18n JS")
        assert full.count(tr[lang]) >= 2, (lang, tr[lang])        # 2 boutons
        assert json.dumps(tr[lang])[1:-1] in page, (lang, tr[lang], "objet i18n JS")
    fr_page = html.unescape(_page(client, EM_PATHS["statistiques"]["fr"]))
    for fr in _C_LABELS:
        assert fr_page.count(fr) >= 2, fr
    # libellés JS (objet STRINGS) : forme |tojson traduite présente, forme FR absente
    raw_fr = _page(client, EM_PATHS["statistiques"]["fr"])
    for fr, tr in _C_JS_LABELS.items():
        assert json.dumps(fr) not in page, (lang, fr, "objet i18n JS")
        assert json.dumps(tr[lang]) in page, (lang, tr[lang], "objet i18n JS")
        assert json.dumps(fr) in raw_fr, fr


@pytest.mark.parametrize("lang", NON_FR)
def test_c2_pairs_js_labels_translated(client, lang):
    page = _page(client, _C_PATHS["paires"][lang])
    raw_fr = _page(client, _C_PATHS["paires"]["fr"])
    for fr in ("Voir les dates", "Masquer les dates"):
        tr = _C_JS_LABELS[fr][lang]
        assert json.dumps(fr) not in page, (lang, fr)
        assert json.dumps(tr) in page, (lang, tr)
        assert json.dumps(fr) in raw_fr, fr


# Contrôle « page entière » : nœuds de texte visibles (hors <head>, <script>, <style>, <template>, <noscript>,
# donc hors JSON-LD) de >= 15 caractères, identiques à un nœud de la page FR.
_C_MIN_LEN = 15
_C_WL_RE = (re.compile(r"^[\d\s.,:;/+\-–—%()×x]+$"), re.compile(r"^(https?://|www\.)\S+$"))
_C_WHITELIST = {
    # noms propres seuls
    "Google Cloud SQL", "Gemini (Google DeepMind)", "HYBRIDE (LotoIA)",
    # identiques par choix de traduction (msgstr rempli = texte FR) : es/pt, nl, en
    "Chatbot HYBRIDE", "HYBRIDE — Chatbot IA", "Chatbot HYBRIDE EuroMillions", "Analyse Loto France",
    "Anti-hallucination",
}


def _c_text_nodes(page: str) -> list[str]:
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.depth, self.nodes = 0, []

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "head", "template", "noscript"):
                self.depth += 1

        def handle_endtag(self, tag):
            if tag in ("script", "style", "head", "template", "noscript") and self.depth:
                self.depth -= 1

        def handle_data(self, data):
            t = " ".join(data.split())
            if t and not self.depth:
                self.nodes.append(t)

    p = _P()
    p.feed(page)
    return p.nodes


@pytest.mark.parametrize("page_key", ("ia", "hybride", "statistiques", "paires"))
@pytest.mark.parametrize("lang", NON_FR)
def test_c3_whole_page_no_fr_text_node(client, lang, page_key):
    fr_nodes = set(_c_text_nodes(_page(client, _C_PATHS[page_key]["fr"])))
    left = []
    for t in _c_text_nodes(_page(client, _C_PATHS[page_key][lang])):
        if (len(t) >= _C_MIN_LEN and t in fr_nodes and t not in _C_WHITELIST
                and not any(r.match(t) for r in _C_WL_RE)):
            left.append(t)
    assert left == [], f"{lang} {page_key} : {left}"


@pytest.mark.parametrize("lang", LANGS)
def test_c4_po_entries(lang):
    cat = _po(lang)
    ids = [m.id for m in _active(cat)]
    for code in _C_TPL:
        mid = _c_msgid(code)
        assert ids.count(mid) == 1, (lang, code)
        msg = cat.get(mid)
        assert not msg.fuzzy, (lang, code)
        if lang != "fr":
            assert msg.string, (lang, code)
            assert sorted(re.findall(r"%\(\w+\)s", mid)) == sorted(re.findall(r"%\(\w+\)s", msg.string))
            assert re.findall(r'href="([^"]*)"', mid) == re.findall(r'href="([^"]*)"', msg.string)
            assert "Grounded" not in msg.string
    for fr, tr in {**_C_LABELS, **_C_JS_LABELS}.items():
        assert ids.count(fr) == 1, (lang, fr)
        msg = cat.get(fr)
        assert not msg.fuzzy
        assert msg.string == ("" if lang == "fr" else tr[lang]), (lang, fr)


# ═══════════════════════════════════════════════════════
# D — audit journaliste du 21/11 (Muse)
#   R-4  « Tout refuser » : blanc sur blanc dans le panneau « Personnaliser » (1,00:1) ; contour du bandeau 2,72:1.
#   R-5  « 2089 tests automatiques … Zéro régression possible » (article Release 1.5.0 du 11/03) remplacée.
#   R-6  « premier chatbot » (article du 15/03 : titre, headline JSON-LD, corps) retiré.
#   R-10 pied EM DE : le lien disclaimer est présent ; phase D-B (option a) : msgstr DE de « Avertissements »
#        « Hinweise » → « Haftungsausschluss » (slug et titre de la page). 3 ou 4 liens selon la page dans les
#        6 langues (drapeau show_disclaimer_link) : inchangé (option b reportée au 076).
# ═══════════════════════════════════════════════════════

LEGAL_CSS = UI / "static" / "legal.css"
_D_CSS_VERSION = "?v=16"

_D_TITLE = {"fr": "LotoIA lance son chatbot EuroMillions intelligent et gratuit",
            "en": "LotoIA launches its intelligent and free EuroMillions chatbot",
            "es": "LotoIA lanza su chatbot EuroMillions inteligente y gratuito",
            "pt": "LotoIA lança o seu chatbot EuroMillions inteligente e gratuito",
            "de": "LotoIA startet seinen intelligenten und kostenlosen EuroMillions-Chatbot",
            "nl": "LotoIA lanceert zijn intelligente en gratis EuroMillions-chatbot"}
_D_BODY = {"fr": "un chatbot EuroMillions ancré sur données réelles",
           "en": "a EuroMillions chatbot anchored in real data",
           "es": "un chatbot de EuroMillions basado en datos reales",
           "pt": "um chatbot EuroMillions baseado em dados reais",
           "de": "ein EuroMillions-Chatbot auf Basis realer Daten",
           "nl": "een EuroMillions-chatbot gebaseerd op echte data"}
_D_R5 = {"fr": "Une suite de <strong>tests automatisés</strong> vérifie chaque version avant sa mise en ligne.",
         "en": "A suite of <strong>automated tests</strong> checks every version before it goes live.",
         "es": "Un conjunto de <strong>tests automatizados</strong> verifica cada versión antes de su puesta en línea.",
         "pt": "Um conjunto de <strong>testes automatizados</strong> verifica cada versão antes de ser colocada online.",
         "de": "Eine Reihe <strong>automatisierter Tests</strong> prüft jede Version vor ihrer Veröffentlichung.",
         "nl": "Een reeks <strong>geautomatiseerde tests</strong> controleert elke versie voordat deze online gaat."}
_D_BODY_MSGID = ("Au cœur de cette nouveauté : <strong>HYBRIDE</strong>, un chatbot EuroMillions ancré sur données "
                 "réelles, s'appuyant sur une base de données de plus de 730 tirages depuis 2019, mise à jour après "
                 "chaque tirage. Posez-lui vos questions en français, anglais, espagnol, portugais, allemand ou "
                 "néerlandais — il analyse les données et vous répond instantanément. Pas de réponses génériques : "
                 "chaque réponse est calculée à partir des vrais résultats officiels.")
_D_OLD_MSGIDS = [
    "LotoIA lance le premier chatbot EuroMillions intelligent et gratuit",
    _D_BODY_MSGID.replace(", un chatbot", ", le premier chatbot"),
    "Chaque mise en production est précédée de <strong>2089 tests automatiques</strong> dans le pipeline cloud. "
    "Si le moindre test échoue, le déploiement est bloqué. Zéro régression possible en production.",
]
# Formes interdites (FR et traductions relevées à l'inventaire de la phase D)
_D_BANNED = [re.compile(p) for p in (
    r"premier chatbot", r"\bfirst\b[^.<\n]{0,40}chatbot", r"\bprimer\b[^.<\n]{0,20}chatbot",
    r"\bprimeiro\b[^.<\n]{0,20}chatbot", r"\berste[nrs]?\b[^.<\n]{0,40}[Cc]hatbot", r"\beerste\b[^.<\n]{0,40}chatbot",
    r"\b2[ ,.  ]?089\b", r"Zéro régression", r"Zero regress", r"Cero regresi", r"Null Regression",
    r"Nul regressie")]
# Nœuds identiques légitimes des pages news (numéros de version, adresse e-mail, marque, nom de table, chemin
# d'API, nom du produit)
_D_NEWS_WL_RE = (re.compile(r"^Release \d+\.\d+\.\d+$"), re.compile(r"^\S+@\S+\.\S+$"))
_D_NEWS_WHITELIST = {"Google for Startups", "tirages_euromillions", "/api/euromillions/*",
                     "chatbot HYBRIDE EuroMillions", "✅ Chatbot HYBRIDE EuroMillions"}


def _d_css_rule(css: str, selector: str) -> dict:
    """Déclarations de la règle dont la liste de sélecteurs contient exactement `selector`."""
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
        if selector in [s.strip() for s in sel.split(",")]:
            return {k.strip(): v.strip() for k, v in re.findall(r"([\w-]+)\s*:\s*([^;]+);", body)}
    raise AssertionError(f"règle absente : {selector}")


def _d_lum(hexc: str) -> float:
    r, g, b = (int(hexc.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = (lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _d_ratio(a: str, b: str) -> float:
    x, y = sorted((_d_lum(a), _d_lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def _d_color(value: str) -> str:
    """Première couleur hexadécimale de la valeur, normalisée en #rrggbb."""
    m = re.search(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", value)
    assert m, value
    h = m.group(1).lower()
    return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h)


def _d_border_color(decl: dict) -> str:
    return _d_color(decl.get("border-color") or decl["border"])


_NIGHT = ('body.night', 'body[data-theme="night"]', 'body.theme-night')


def test_d_r4_panel_reject_readable():
    css = _read(LEGAL_CSS)
    panel_bg = _d_color(_d_css_rule(css, ".cookie-settings-panel")["background"])
    assert panel_bg == "#ffffff"
    rule = _d_css_rule(css, ".cookie-settings-panel .cookie-btn-reject")
    fg = _d_color(rule["color"])
    assert fg != panel_bg
    assert _d_ratio(fg, panel_bg) >= 4.5
    assert _d_ratio(_d_border_color(rule), panel_bg) >= 3          # contour visible (non-texte)
    hover = _d_css_rule(css, ".cookie-settings-panel .cookie-btn-reject:hover")
    assert _d_ratio(fg, _d_color(hover["background"])) >= 4.5
    # nuit : même trois sélecteurs que le fond du panneau
    for night in _NIGHT:
        bg = _d_color(_d_css_rule(css, f"{night} .cookie-settings-panel")["background"])
        r = _d_css_rule(css, f"{night} .cookie-settings-panel .cookie-btn-reject")
        assert _d_ratio(_d_color(r["color"]), bg) >= 4.5, night
        assert _d_ratio(_d_border_color(r), bg) >= 3, night


def test_d_r4_banner_reject_readable():
    css = _read(LEGAL_CSS)
    bg = _d_color(_d_css_rule(css, ".cookie-banner")["background"])
    fg = _d_color(_d_css_rule(css, ".cookie-btn-reject")["color"])
    assert fg != bg
    assert _d_ratio(fg, bg) >= 4.5
    assert _d_ratio(_d_border_color(_d_css_rule(css, ".cookie-banner .cookie-btn-reject")), bg) >= 3


def test_d_r4_same_size_as_accept():
    """Présence équivalente : les règles dédiées ne changent ni taille, ni marge, ni police (même .cookie-btn)."""
    css = _read(LEGAL_CSS)
    sels = [".cookie-settings-panel .cookie-btn-reject", ".cookie-settings-panel .cookie-btn-reject:hover",
            ".cookie-banner .cookie-btn-reject"] + [f"{n} .cookie-settings-panel .cookie-btn-reject" for n in _NIGHT]
    for sel in sels:
        decl = _d_css_rule(css, sel)
        assert not {"padding", "font-size", "width", "height", "font-weight", "display"} & set(decl), sel
    js = _read(UI / "static" / "cookie-consent.js")
    assert js.count('class="cookie-btn cookie-btn-reject"') == 2      # bandeau + panneau
    assert js.count('class="cookie-btn cookie-btn-accept"') == 2


def test_d_r4_legal_css_cache_buster():
    refs = []
    for p in LOTO_SERVED + EM_SERVED + [LAUNCHER]:
        refs += [(p.name, v) for v in re.findall(r'/ui/static/legal\.css(\?v=\d+)?"', _read(p))]
    assert len(refs) == 26, refs
    assert {v for _, v in refs} == {_D_CSS_VERSION}, sorted(set(refs))


def _d_news_paths() -> list[tuple[str, str]]:
    return [("fr", "/news")] + [(lg, EM_PATHS["news"][lg]) for lg in LANGS]


@pytest.mark.parametrize("lang,path", _d_news_paths())
def test_d_r5_r6_news_pages(client, lang, path):
    page = _page(client, path)
    visible = _visible(page)
    raw = html.unescape(page)
    for rx in _D_BANNED:
        assert not rx.search(visible), (path, rx.pattern)
        assert not rx.search(raw), (path, rx.pattern, "source (JSON-LD, meta)")
    tr = "fr" if lang == "fr" else lang
    assert _strip(_D_R5[tr]) in visible, path
    assert _D_BODY[tr] in visible, path
    assert _D_TITLE[tr] in visible, path


@pytest.mark.parametrize("lang,path", _d_news_paths())
def test_d_r6_headline_equals_visible_title(client, lang, path):
    page = _page(client, path)
    titles = [_strip(h).replace("\U0001f680", "").strip()
              for h in re.findall(r'<h2 class="news-title">(.*?)</h2>', page, re.S)]
    arts = []
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        arts += [a for a in json.loads(block).get("@graph", []) if a.get("@type") == "NewsArticle"]
    launch = [a for a in arts if a["datePublished"] == "2026-03-15"]
    assert len(launch) == 1, path
    assert launch[0]["headline"] == _D_TITLE["fr" if lang == "fr" else lang], path
    assert launch[0]["headline"] in titles, path
    assert launch[0]["dateModified"] == "2026-11-21"
    if path == "/news":  # article R-5 (Release 1.5.0) : présent dans le JSON-LD Loto seulement
        rel = [a for a in arts if a["datePublished"] == "2026-03-11"]
        assert len(rel) == 1 and rel[0]["dateModified"] == "2026-11-21"


def test_d_r5_r6_sources():
    """Gabarits et pages servis (Loto, EM, launcher) : aucune forme interdite, y compris JSON-LD et meta."""
    for p in LOTO_SERVED + EM_SERVED + [LAUNCHER]:
        text = _unesc(_read(p))
        for rx in _D_BANNED:
            assert not rx.search(text), (p.name, rx.pattern)
    loto = _read(UI / "news.html")
    assert '"headline": "LotoIA lance son chatbot EuroMillions intelligent et gratuit"' in loto
    assert _D_R5["fr"] in loto


@pytest.mark.parametrize("lang", LANGS)
def test_d_po_entries(lang):
    cat = _po(lang)
    ids = [m.id for m in _active(cat)]
    for mid, tr in ((_D_TITLE["fr"], _D_TITLE), (_D_R5["fr"], _D_R5), (_D_BODY_MSGID, _D_BODY)):
        assert ids.count(mid) == 1, (lang, mid[:50])
        msg = cat.get(mid)
        assert not msg.fuzzy, (lang, mid[:50])
        if lang == "fr":
            assert msg.string == ""
        else:
            assert msg.string, (lang, mid[:50])
            assert (tr[lang] == msg.string) if tr is not _D_BODY else (tr[lang] in msg.string), (lang, msg.string)
            assert msg.string.count("<strong>") == mid.count("<strong>"), (lang, mid[:50])
            assert msg.string.count("</strong>") == mid.count("</strong>"), (lang, mid[:50])
    # R-10 (phase D-B, option a) : libellé du lien disclaimer du pied EM
    disc = cat.get("Avertissements")
    assert ids.count("Avertissements") == 1 and not disc.fuzzy, lang
    if lang == "de":
        assert disc.string == "Haftungsausschluss"
    for old in _D_OLD_MSGIDS:
        assert old not in ids, (lang, old[:50])
    for m in _active(cat):
        for rx in _D_BANNED:
            assert not rx.search(m.id) and not rx.search(m.string or ""), (lang, rx.pattern, m.id[:60])


@pytest.mark.parametrize("lang", NON_FR)
def test_d_news_whole_page_no_fr_text_node(client, lang):
    fr_nodes = set(_c_text_nodes(_page(client, EM_PATHS["news"]["fr"])))
    left = []
    for t in _c_text_nodes(_page(client, EM_PATHS["news"][lang])):
        if (len(t) >= _C_MIN_LEN and t in fr_nodes and t not in _C_WHITELIST and t not in _D_NEWS_WHITELIST
                and not any(r.match(t) for r in _D_NEWS_WL_RE + _C_WL_RE)):
            left.append(t)
    assert left == [], f"{lang} news : {left}"


def _d_legal_links(page: str) -> list[tuple[str, str]]:
    m = re.search(r'<div class="footer-legal">(.*?)</div>', page, re.S)
    assert m, "footer-legal absent"
    return [(h, _strip(t)) for h, t in re.findall(r'<a href="([^"]*)"[^>]*>(.*?)</a>', m.group(1), re.S) if h != "#"]


@pytest.mark.parametrize("page_key", ("accueil", "generateur", "statistiques", "mentions", "confidentialite",
                                      "cookies", "disclaimer"))
def test_d_r10_footer_disclaimer_link_6_langs(client, page_key):
    """Constat R-10 : sur les pages à lien disclaimer, 4 liens légaux dans les 6 langues, même route localisée."""
    from config.templates import EM_URLS
    for lang in LANGS:
        links = _d_legal_links(_page(client, EM_URLS[lang][page_key]))
        assert [h for h, _ in links] == [EM_URLS[lang][k] for k in ("mentions", "confidentialite", "cookies",
                                                                     "disclaimer")], (lang, page_key, links)
    # phase D-B (R-10, option a) : libellé DE « Hinweise » → « Haftungsausschluss »
    assert _d_legal_links(_page(client, EM_URLS["de"]["accueil"]))[3] == ("/de/euromillions/haftungsausschluss",
                                                                           "Haftungsausschluss")
    assert "Hinweise" not in [t for _, t in _d_legal_links(_page(client, EM_URLS["de"][page_key]))]


@pytest.mark.parametrize("page_key", ("accueil", "news", "simulateur", "historique", "faq", "a_propos", "moteur",
                                      "methodologie", "ia", "hybride_page", "statistiques", "disclaimer"))
def test_d_r10_de_footer_no_fr_text_node(client, page_key):
    from config.templates import EM_URLS

    def _footer_nodes(path):
        m = re.search(r'<footer class="footer".*?</footer>', _page(client, path), re.S)
        assert m, path
        return _c_text_nodes(m.group(0))
    fr = set(_footer_nodes(EM_URLS["fr"][page_key]))
    left = [t for t in _footer_nodes(EM_URLS["de"][page_key])
            if len(t) >= _C_MIN_LEN and t in fr and t not in _C_WHITELIST and not any(r.match(t) for r in _C_WL_RE)]
    assert left == [], (page_key, left)
