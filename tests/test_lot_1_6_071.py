"""
Tests — LOT 1.6.071 : papier news « Merci : LotoIA grandit grâce à vous » (14/11/2026).

Couvre :
  T1  version : APP_VERSION 1.6.071, VERSION_DATE et LAST_NEWS_DATE 2026-11-14 ;
  T2  /news + 6 pages news EM : nouvel article en premier, seul « featured », papier du 10/06 conservé,
      lien contact = modale existante ;
  T3  trois chiffres exacts (forme locale) + deux sources nommées, par langue ;
  T4  absences dans le nouvel article (chiffres et sujets interdits, « génère », prédiction hors 🎓 / suite) ;
  T5  phrase 🎓 identique octet pour octet aux 2 premières phrases du papier du 10/06 (msgid / msgstr) ;
  T6  JSON-LD valide, premier NewsArticle = titre localisé, dates 2026-11-14 ;
  T7  ZÉRO string FR visible dans le nouvel article (EN / ES / PT / DE / NL) ;
  T8  sitemap : lastmod des pages news = 2026-11-14 ;
  T9  .po / .pot : 18 msgid présents une fois, msgstr remplis hors FR, aucun fuzzy.
"""
import html
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch
from xml.etree import ElementTree

import pytest
from babel.messages.pofile import read_po
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})

LANGS = ("fr", "en", "es", "pt", "de", "nl")
NON_FR = ("en", "es", "pt", "de", "nl")

# FR = /news (Loto, statique) ; les autres langues = pages news EM.
PAGES = {
    "fr_loto": "/news",
    "fr": "/euromillions/news",
    "en": "/en/euromillions/news",
    "es": "/es/euromillions/noticias",
    "pt": "/pt/euromillions/noticias",
    "de": "/de/euromillions/nachrichten",
    "nl": "/nl/euromillions/nieuws",
}
ALL_PAGES = list(PAGES.items())


def _lang(key: str) -> str:
    return "fr" if key == "fr_loto" else key


TITLES = {
    "fr": "Merci : LotoIA grandit grâce à vous",
    "en": "Thank you: LotoIA is growing thanks to you",
    "es": "Gracias: LotoIA crece con ustedes",
    "pt": "Obrigado: a LotoIA cresce graças a vocês",
    "de": "Danke: LotoIA wächst dank Ihnen",
    "nl": "Bedankt: LotoIA groeit dankzij u",
}

# Chiffres sous leur forme brute dans le HTML (msgstr |safe, &nbsp; conservé).
FIGURES = {
    "fr": ("7&nbsp;821 clics", "9&nbsp;015 visiteurs", "<strong>4,5/5</strong>", "243 avis"),
    "en": ("7,821 clicks", "9,015 visitors", "<strong>4.5/5</strong>", "243 reviews"),
    "es": ("7.821 clics", "9.015 visitantes", "<strong>4,5/5</strong>", "243 opiniones"),
    "pt": ("7&nbsp;821 cliques", "9&nbsp;015 visitantes", "<strong>4,5/5</strong>", "243 avaliações"),
    "de": ("7.821 Klicks", "9.015 Besucher", "<strong>4,5/5</strong>", "243 Bewertungen"),
    "nl": ("7.821 klikken", "9.015 bezoekers", "<strong>4,5/5</strong>", "243 beoordelingen"),
}

CONTACT_LABEL = {
    "fr": "Nous contacter", "en": "Contact us", "es": "Contactarnos",
    "pt": "Contactar-nos", "de": "Kontakt", "nl": "Contact",
}
CONTACT_ONCLICK = ('onclick="event.preventDefault();if(window.LotoIAContact)'
                   'LotoIAContact.openModal(window.location.pathname);"')
# GO B bis : lien lisible en thème sombre (attribut inline, CSP style-src 'unsafe-inline').
CONTACT_STYLE = 'style="color:inherit;text-decoration:underline;font-weight:600"'

# Marqueurs du papier du 10/06 (doit rester présent, non featured).
MARKER_1006 = {
    "fr": "renforce sa transparence",
    "en": "strengthens its transparency",
    "es": "refuerza su transparencia",
    "pt": "reforça a sua transparência",
    "de": "stärkt seine Transparenz",
    "nl": "versterkt zijn transparantie",
}

# Interdits par langue (regex, insensibles à la casse) — dans le nouvel article.
# « donnée » : le texte validé contient le participe « donnée par les visiteurs » ; on interdit le nom
# (« données », « une/la donnée », « donnée(s) personnelle(s) »).
FORBIDDEN = {
    "fr": [r"\bdonnées\b", r"\b(?:une|la|des) donnée", r"données? personnelle", r"\bquestions?\b",
           r"\bgénèr(?:e|ent)\b", r"\bgénérée?s?\b", r"\bgénérer\b"],
    "en": [r"\bdata\b", r"\bquestions?\b", r"\bgenerat(?:e|es|ed|ing)\b"],
    "es": [r"\bdatos\b", r"\bpreguntas?\b", r"\bgenera(?:n)?\b", r"\bgenerad[ao]s?\b"],
    "pt": [r"\bdados\b", r"\bperguntas?\b", r"\bgera(?:m)?\b", r"\bgerad[ao]s?\b"],
    "de": [r"\bdaten\b", r"\bfragen?\b", r"generier"],
    "nl": [r"\bgegevens\b", r"\bvra(?:a)?g(?:en)?\b", r"genereer", r"gegenereerd"],
}
FORBIDDEN_COMMON = [r"8[\s .,]000", r"8&nbsp;000", r"%", r"chatbot", r"cookie"]
PREDICT = {
    "fr": r"prédi", "en": r"predict", "es": r"predic", "pt": r"previs|prever|prevê",
    "de": r"vorhers", "nl": r"voorspel",
}

# Mots FR propres au nouvel article (aucun n'est un invariable ni un mot des 5 autres langues ici).
FR_WORDS = ["Merci", "grandit", "visiteurs", "chiffres", "repères", "amélioré", "sombre", "inscription",
            "remarque", "souci", "équipe", "novembre", "octobre", "désormais", "tirage", "Nous contacter"]

NEW_MSGIDS = [
    "14 novembre 2026",
    "Merci",
    "Merci : LotoIA grandit grâce à vous",
    "Vous êtes de plus en plus nombreux à utiliser LotoIA. Avant tout, nous voulions simplement vous dire merci.",
    "Quelques chiffres",
    "Quelques repères, chacun avec sa source :",
    "<strong>7&nbsp;821 clics</strong> depuis Google entre le 11 octobre et le 7 novembre 2026 "
    "(source : Google Search Console) ;",
    "<strong>9&nbsp;015 visiteurs</strong> en octobre 2026 (source : Umami) ;",
    "une note moyenne de <strong>4,5/5</strong> donnée par les visiteurs sur LotoIA "
    "(243 avis au 12 novembre 2026).",
    "Derrière ces chiffres, il y a vous : vos visites et vos avis.",
    "Ce que nous avons amélioré pour vous",
    "Nous avons amélioré le confort de lecture : la FAQ de la page Statistiques du Loto est désormais lisible "
    "en thème sombre, et l'affichage du générateur EuroMillions a été corrigé (plus d'effet de cascade pendant "
    "le calcul, titres et date du prochain tirage lisibles en thème sombre).",
    "Ce que LotoIA est, et n'est pas",
    "LotoIA est un outil d'<strong>analyse statistique</strong>, pas un outil de prédiction. Le résultat d'un "
    "tirage de loterie reste totalement aléatoire : aucune méthode ne permet de le prévoir ni d'augmenter les "
    "chances de gain.",
    "La suite",
    "Nous continuons d'améliorer le site régulièrement. Le cap, lui, ne change pas : un outil gratuit, sans "
    "inscription, d'analyse, pas de prédiction.",
    "Une idée, une remarque, un souci ?",
    "chacun de vos retours compte.",
]
PHRASE_MSGID = NEW_MSGIDS[13]
MSGID_1006 = (
    "LotoIA est un outil d'<strong>analyse statistique</strong>, pas un outil de prédiction. Le résultat d'un "
    "tirage de loterie reste totalement aléatoire : aucune méthode ne permet de le prévoir ni d'augmenter les "
    "chances de gain. Ce que nous faisons, c'est analyser la <strong>forme</strong> et la "
    "<strong>construction</strong> des grilles générées — leur répartition, leur équilibre, leurs "
    "caractéristiques statistiques. Et nous pensons que cette analyse doit être <strong>lisible par "
    "tous</strong>, pas réservée aux initiés."
)


# ── Helpers ───────────────────────────────────────────────────────────────

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


def _article(text: str) -> str:
    m = re.search(r'<article class="news-post featured">(.*?)</article>', text, re.S)
    assert m, "article featured introuvable"
    return m.group(1)


def _visible(fragment: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", fragment)
    txt = html.unescape(txt).replace(" ", " ")
    return re.sub(r"\s+", " ", txt).strip()


def _catalog(lang: str):
    with open(ROOT / "translations" / lang / "LC_MESSAGES" / "messages.po", "rb") as f:
        return read_po(f)


def _two_sentences(s: str) -> str:
    first = s.index(". ")
    second = s.index(". ", first + 2)
    return s[: second + 1]


def _expected_phrase(lang: str) -> str:
    """2 premières phrases du papier du 10/06 (msgid FR, msgstr ailleurs)."""
    if lang == "fr":
        return _two_sentences(MSGID_1006)
    return _two_sentences(_catalog(lang).get(MSGID_1006).string)


# ── T1 — version ──────────────────────────────────────────────────────────

def test_t1_version():
    from config.version import APP_VERSION, LAST_NEWS_DATE, VERSION_DATE
    assert APP_VERSION == "1.6.071"
    assert VERSION_DATE == "2026-11-14"
    assert LAST_NEWS_DATE == "2026-11-14"


# ── T2 — position, featured, 10/06 conservé, contact ─────────────────────

@pytest.mark.parametrize("key,path", ALL_PAGES)
def test_t2_new_article_first_and_only_featured(client, key, path):
    text = _page(client, path)
    lang = _lang(key)
    assert text.count("news-post featured") == 1
    first = re.search(r'<article class="([^"]+)">', text)
    assert first and first.group(1) == "news-post featured"
    art = _article(text)
    assert TITLES[lang] in _visible(art)
    assert 'news-tag news-tag-launch' in art
    after_new = text[text.find("</article>"):]
    assert MARKER_1006[lang] in after_new, "papier du 10/06 absent après le nouvel article"


@pytest.mark.parametrize("key,path", ALL_PAGES)
def test_t2_contact_link_is_existing_modal(client, key, path):
    art = _article(_page(client, path))
    lang = _lang(key)
    assert f'<a href="#" {CONTACT_STYLE} {CONTACT_ONCLICK}>{CONTACT_LABEL[lang]}</a>' in art


# ── T10 — GO B ter v2 : liens des news lisibles en thème sombre + bouton 13/04 EM ──

LINK_RULE = ".news-content a:not([class]):not([style]){color:inherit;text-decoration:underline}"


def _news_contents(text: str) -> list[str]:
    return re.findall(r'<div class="news-content">(.*?)</div>\s*</article>', text, re.S)


@pytest.mark.parametrize("key,path", ALL_PAGES)
def test_t10_link_rule_present(client, key, path):
    text = _page(client, path)
    styles = re.findall(r"<style>(.*?)</style>", text, re.S)
    assert any(LINK_RULE in s for s in styles), f"{path}: règle absente des blocs <style>"
    assert text.count(LINK_RULE) == 1


@pytest.mark.parametrize("key,path", ALL_PAGES)
def test_t10_every_bare_link_covered(client, key, path):
    """Inventaire rendu : chaque <a> d'un .news-content est soit nu (couvert par la règle), soit doté
    d'une classe ou d'un style ; le lien du nouvel article garde son style B bis ; aucun href vide."""
    text = _page(client, path)
    contents = _news_contents(text)
    assert len(contents) >= 10
    bare = 0
    for content in contents:
        for attrs in re.findall(r"<a\s([^>]*)>", content):
            has_class = re.search(r'\bclass="', attrs) is not None
            has_style = re.search(r'\bstyle="', attrs) is not None
            # la règle couvre exactement les liens sans class ni style
            bare += int(not has_class and not has_style)
            href = re.search(r'href="([^"]*)"', attrs)
            assert href and href.group(1), f"{path}: lien sans href : {attrs[:80]}"
    assert bare >= 4, f"{path}: inventaire inattendu ({bare} liens nus)"
    assert CONTACT_STYLE in _article(text)


@pytest.mark.parametrize("lang", LANGS)
def test_t10_em_cta_1304_points_to_generator(client, lang):
    from config.templates import EM_URLS
    text = _page(client, PAGES[lang])
    hrefs = re.findall(r'<a href="([^"]*)" class="news-cta-btn">', text)
    assert hrefs == [EM_URLS[lang]["generateur"]]


def test_t2_es_suite_phrase_reworded():
    msg = _catalog("es").get(NEW_MSGIDS[15])
    assert "eso sí, sigue siendo el mismo" in msg.string
    assert "en cambio" not in msg.string


# ── T3 — chiffres et sources ──────────────────────────────────────────────

@pytest.mark.parametrize("key,path", ALL_PAGES)
def test_t3_figures_and_sources(client, key, path):
    art = _article(_page(client, path))
    for fig in FIGURES[_lang(key)]:
        assert fig in art, f"{path}: « {fig} » absent"
    assert "Google Search Console" in art
    assert "Umami" in art


# ── T4 — absences ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("key,path", ALL_PAGES)
def test_t4_forbidden_absent(client, key, path):
    art = _article(_page(client, path))
    lang = _lang(key)
    raw_vis = art + " " + _visible(art)
    for pat in FORBIDDEN_COMMON:
        assert not re.search(pat, raw_vis, re.I), f"{path}: motif interdit {pat!r}"
    vis = _visible(art)
    for pat in FORBIDDEN[lang]:
        assert not re.search(pat, vis, re.I), f"{path}: motif interdit {pat!r}"


@pytest.mark.parametrize("key,path", ALL_PAGES)
def test_t4_prediction_only_in_allowed_paragraphs(client, key, path):
    art = _article(_page(client, path))
    lang = _lang(key)
    blocks = re.split(r"(?=<h3)", art)
    assert len(blocks) == 5, "structure attendue : intro + 4 sous-titres"
    suite = re.sub(r"<p>.*?</p>", "", blocks[4], count=1, flags=re.S)  # retire la phrase « La suite »
    for chunk in (blocks[0], blocks[1], blocks[2], suite):
        assert not re.search(PREDICT[lang], _visible(chunk), re.I), f"{path}: prédiction hors 🎓 / suite"
    assert re.search(PREDICT[lang], _visible(blocks[3]), re.I)
    assert re.search(PREDICT[lang], _visible(blocks[4]), re.I)


# ── T5 — phrase 🎓 octet pour octet ───────────────────────────────────────

@pytest.mark.parametrize("key,path", ALL_PAGES)
def test_t5_phrase_identical_to_1006(client, key, path):
    art = _article(_page(client, path))
    expected = _expected_phrase(_lang(key))
    assert f"<p>{expected}</p>" in art


@pytest.mark.parametrize("lang", NON_FR)
def test_t5_po_msgstr_copied_from_1006(lang):
    cat = _catalog(lang)
    assert cat.get(PHRASE_MSGID).string == _expected_phrase(lang)


def test_t5_fr_msgid_is_prefix_of_1006():
    assert _two_sentences(MSGID_1006) == PHRASE_MSGID


# ── T6 — JSON-LD ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("key,path", ALL_PAGES)
def test_t6_jsonld_first_newsarticle(client, key, path):
    text = _page(client, path)
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)
    assert blocks
    graphs = []
    for raw in blocks:
        data = json.loads(raw)
        if isinstance(data, dict) and "@graph" in data:
            graphs.append(data["@graph"])
    news = [g for g in graphs if g and g[0].get("@type") == "NewsArticle"]
    assert len(news) == 1
    first = news[0][0]
    assert first["headline"] == TITLES[_lang(key)]
    assert first["datePublished"] == "2026-11-14"
    assert first["dateModified"] == "2026-11-14"
    assert news[0][1]["datePublished"] == "2026-06-10"


# ── T7 — ZÉRO string FR visible ───────────────────────────────────────────

@pytest.mark.parametrize("lang", NON_FR)
def test_t7_zero_french_visible(client, lang):
    vis = _visible(_article(_page(client, PAGES[lang])))
    for msgid in NEW_MSGIDS:
        assert _visible(msgid) not in vis, f"{lang}: msgid FR visible : {msgid[:50]}"
    for word in FR_WORDS:
        assert not re.search(rf"(?<!\w){re.escape(word)}(?!\w)", vis), f"{lang}: mot FR visible « {word} »"


def test_t7_counter_check_fr_pages_show_french(client):
    for path in (PAGES["fr_loto"], PAGES["fr"]):
        vis = _visible(_article(_page(client, path)))
        assert "Merci : LotoIA grandit grâce à vous" in vis
        assert "Nous contacter" in vis


# ── T8 — sitemap ──────────────────────────────────────────────────────────

def test_t8_sitemap_news_lastmod():
    cursor = _make_cursor()
    # Objets patch neufs : ceux du module sont déjà actifs dans la fixture « client ».
    env = patch.dict(os.environ, {"DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
                                  "EM_PUBLIC_ACCESS": "true"})
    with env, patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None), \
         patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None), \
         patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
         patch("routes.sitemap._fetch_last_draw_date_loto", AsyncMock(return_value="2026-11-11")), \
         patch("routes.sitemap._fetch_last_draw_date_em", AsyncMock(return_value="2026-11-10")):
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        resp = TestClient(main_mod.app, raise_server_exceptions=False).get("/sitemap.xml")
    assert resp.status_code == 200
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ElementTree.fromstring(resp.content)
    lastmods = {u.findtext("sm:loc", namespaces=ns): u.findtext("sm:lastmod", namespaces=ns)
                for u in root.findall("sm:url", ns)}
    for path in PAGES.values():
        assert lastmods[f"https://lotoia.fr{path}"] == "2026-11-14", path


# ── T9 — catalogues ───────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
def test_t9_po_entries(lang):
    raw = (ROOT / "translations" / lang / "LC_MESSAGES" / "messages.po").read_text(encoding="utf-8")
    cat = _catalog(lang)
    for msgid in NEW_MSGIDS:
        assert raw.count(f'msgid "{msgid}"\n') == 1, f"{lang}: {msgid[:40]}"
        msg = cat.get(msgid)
        assert msg is not None and not msg.fuzzy
        if lang == "fr":
            assert msg.string == ""
        else:
            assert msg.string and msg.string != msgid, f"{lang}: msgstr vide ou FR : {msgid[:40]}"
            assert msg.string.count("<strong>") == msgid.count("<strong>")
            assert "%" not in msg.string


def test_t9_pot_entries():
    raw = (ROOT / "translations" / "messages.pot").read_text(encoding="utf-8")
    for msgid in NEW_MSGIDS:
        assert raw.count(f'msgid "{msgid}"\n') == 1, msgid[:40]
