"""
Tests — Lot 1.6.067 (09/11/2026) : vérité HYBRIDE (partie A) + coûts de la console Monitoring (partie B).

Partie A
  T1  G7 étendu — sources : aucune pondération chiffrée ni « 24 derniers mois » dans toutes les pages servies
      (routes.pages.SEO_PAGES + tous les templates EM hors `_*.html`) ;
  T2  G7 étendu — .po : tous les msgid et msgstr des 6 catalogues ;
  T3  G7 + promesses — rendu des pages modifiées (Loto FR + EM × 6 langues) ;
  T4  promesses (« zéro hallucination », « vérification systématique »…, 6 langues) : sources + .po ;
  T5  promesses — 7 prompts actifs du chatbot, consigne « zéro invention » conservée ;
  T6  G17 étendu — tableau des modes de /moteur (Loto + EM) = texte de la FAQ, Récent sans « tendances » ;
  T7  G11 enrichi — anciens msgid absents des 6 .po ;
  T8  nouveaux msgid présents dans les 6 .po, non fuzzy ;
  T8-bis (prompt n° 2) 33 msgid du lot : msgstr non vide et non fuzzy en EN, ES, PT, DE, NL ;
  T8-ter (prompt n° 2) msgid python-format : mêmes placeholders dans le msgstr ;
  T19 (prompt n° 2) « ZÉRO string FR visible » : pages EM news / moteur / IA / hybride / à propos rendues
      en EN, ES, PT, DE, NL sans aucun des 33 msgid français (fragments ≥ 40 caractères) ;
  T9  news datées : note « Mise à jour du 09/11/2026 », compteurs « (à cette date) », meta EM « plus de 700 » ;
  T10 dateModified des NewsArticle corrigés = 2026-11-09 ;
  T11 note JSON-LD /euromillions = toutes les sources EM (services/em_rating.py) ; /accueil inchangé.
Partie B
  T12 get_cost_config (défauts, surcharge, valeurs invalides, base indisponible) ;
  T13 _estimate_costs (forfaits + Gemini 2.5 + « autres ») ;
  T14 get_gcp_metrics : latence Gemini sur chat_* seulement, seuils de la carte dans le payload ;
  T15 traçage des 4 appels Vertex (chat_*_sync, pitch_*, sql_loto, sql_em) ;
  T16 répartition Gemini : 10 types, sans meta_analyse ;
  T17 /admin/config : route POST /admin/config/costs, libellés, carte Monitoring sans 90/120 en dur ;
  T18 seuils coût mensuel 165 / 200.
"""
import html
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from config.templates import EM_URLS

_REPO = Path(__file__).resolve().parent.parent
_LANGS = ("fr", "en", "es", "pt", "de", "nl")

# ── Motifs ────────────────────────────────────────────────────────────────

# G7 (repris de tests/test_lot_coherence_reduit.py) + « 24 derniers mois » 6 langues
_FORBIDDEN_WEIGHTS = [
    r"\(\s*(?:60|40|70|30)\s?%\s*\)",
    r"\b\d{2}\s?%\s*/\s*\d{2}\s?%",
    r"\b(?:70/30|60/40|40/60|40/35/25|50/30/20|25/35/40)\b",
    r"\b(?:70|30)\s?% du score",
    r"\b(?:60|40)\s?% de pondération",
    r"\b50\s?% période",
    r"24 derniers mois|24 (?:months|meses|Monate|maanden)\b",
]
# Promesses d'infaillibilité (6 langues)
_PROMISES = [
    r"(?i)z[ée]ro hallucin", r"(?i)zero alucina", r"(?i)cero alucina", r"(?i)null halluzin",
    r"(?i)nul hallucin", r"(?i)sans hallucination", r"(?i)sin alucinaci", r"(?i)sem alucina",
    r"(?i)without hallucination", r"(?i)ohne halluzin", r"(?i)zonder hallucin", r"(?i)geen hallucin",
    r"(?i)vérification systématique(?! des données)", r"(?i)vérifie systématiquement",
]

_ACTIVE_PROMPTS = {
    "loto_fr": ("prompts/chatbot/prompt_hybride.txt", "Zéro invention."),
    "em_fr": ("prompts/em/fr/prompt_hybride_em.txt", "Zéro invention."),
    "em_en": ("prompts/em/en/prompt_hybride_em.txt", "Zero invention."),
    "em_es": ("prompts/em/es/prompt_hybride_em.txt", "Cero invenciones."),
    "em_pt": ("prompts/em/pt/prompt_hybride_em.txt", "Zero invenções."),
    "em_de": ("prompts/em/de/prompt_hybride_em.txt", "Null Erfindungen."),
    "em_nl": ("prompts/em/nl/prompt_hybride_em.txt", "Nul verzinsels."),
}

# Anciens msgid (fragments) supprimés par le lot
_OLD_MSGID_FRAGMENTS = [
    "<strong>Analyse historique (60%)</strong>",
    "<strong>Analyse des tendances récentes (40%)</strong>",
    "en combinant deux approches complémentaires, adaptées",
    "Le moteur combine deux horizons temporels",
    "Application de coefficients privilégiant",
    "Application de coefficients de pondération privilégiant",
    "Privilégie les numéros fréquents (chauds)",
    "Équilibre entre fréquences et retards",
    "Pondération forte sur les tendances récentes",
    "729 tirages historiques. 100%",
    "729 tirages européens",
    "Anti-hallucination par vérification systématique",
    "Analyse fréquentielle sur 5 ans",
]

# Nouveaux msgid (fragments distinctifs) — 33 au total, échantillon représentatif par template
_NEW_MSGID_FRAGMENTS = [
    "plus de 700 tirages historiques. 100% gratuit",
    "plus de 700 tirages européens.",
    "un outil transparent, fondé sur les données réelles",
    "(à cette date, période 2019-2026)",
    "<strong>729 tirages historiques</strong> (à cette date)",
    "encadre ses réponses pour éviter toute prédiction.",
    "notre base de 729 tirages officiels (à cette date)",
    "avec 729 tirages historiques (à cette date).",
    "en combinant plusieurs approches complémentaires, adaptées",
    "<strong>Trois fenêtres d'analyse</strong> : les 5 dernières années",
    "<strong>Poids des tirages récents</strong>",
    "Mise à jour du 09/11/2026 :",
    "Analyse fréquentielle sur trois fenêtres (5 ans, 2 ans, historique complet)",
    "Combinaison des trois fenêtres d'analyse : les tirages récents",
    "Privilégie l'historique long terme. Idéal si vous préférez",
    "Répartition harmonieuse entre les 3 périodes. C'est le mode par défaut",
    "Pour ceux qui veulent davantage de diversité dans les grilles proposées.",
    "EuroMillions : ses réponses s'appuient sur ces données réelles.",
    "— Combinaison des trois fenêtres : les tirages récents",
    "Le moteur combine trois fenêtres d'analyse : <strong>les 5 dernières",
    "Analyses factuelles, avec contrôles automatiques des chiffres cités.",
    "Analyse factuelle fondée sur les tirages officiels.",
    "Contrôles automatiques des chiffres cités",
    "Des contrôles automatiques comparent ensuite la réponse aux données.",
    "Aucune IA n'est infaillible : en cas de doute, vérifiez sur l'historique officiel.",
    "<strong>Contrôles anti-hallucination</strong>",
]

# ── Helpers ───────────────────────────────────────────────────────────────


def _read(rel: str) -> str:
    return (_REPO / rel).read_text(encoding="utf-8")


def _served_sources() -> list[str]:
    from routes.pages import SEO_PAGES
    loto = sorted({f"ui/{f}" for f in SEO_PAGES.values()})
    em = sorted(f"ui/templates/em/{p.name}" for p in (_REPO / "ui/templates/em").glob("*.html")
                if not p.name.startswith("_"))
    return loto + em


def _po_entries(lang: str) -> list[dict]:
    """Toutes les entrées d'un .po (y compris fuzzy et #~) : msgid, msgstr, fuzzy."""
    path = _REPO / "translations" / lang / "LC_MESSAGES" / "messages.po"
    entries, cur, field, fuzzy = [], None, None, False

    def _unq(s):
        return s.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw[2:].strip() if raw.startswith("#~") else raw.strip()
        if raw.startswith("#,"):
            fuzzy = "fuzzy" in raw
            continue
        if line.startswith("msgid "):
            if cur:
                entries.append(cur)
            cur, field = {"id": _unq(line[7:-1]), "str": "", "fuzzy": fuzzy}, "id"
            fuzzy = False
        elif line.startswith("msgstr ") and cur is not None:
            cur["str"], field = _unq(line[8:-1]), "str"
        elif line.startswith('"') and cur is not None:
            cur[field] += _unq(line[1:-1])
    if cur:
        entries.append(cur)
    return entries


_PO_CACHE: dict = {}


def _po(lang: str) -> list[dict]:
    if lang not in _PO_CACHE:
        _PO_CACHE[lang] = _po_entries(lang)
    return _PO_CACHE[lang]


def _first_hit(text: str, patterns: list[str]):
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(0)
    return None


# ── Client de test (pattern tests/test_lot_coherence_reduit.py) ───────────

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_TEST_TOKEN = "test_admin_token_1234567890"
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true", "ADMIN_TOKEN": _TEST_TOKEN, "ADMIN_PASSWORD": "test_admin_password",
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
        import routes.admin_helpers as admin_helpers_mod
        importlib.reload(admin_helpers_mod)
        import routes.admin_sponsors as admin_sponsors_mod
        importlib.reload(admin_sponsors_mod)
        import main as main_mod
        importlib.reload(main_mod)
        rl_mod.limiter.reset()
        rl_mod._api_hits.clear()
        yield TestClient(main_mod.app, raise_server_exceptions=False)


def _get(client, path: str):
    with patch("db_cloudsql.get_connection", _async_cm_conn(_make_cursor())), \
         patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
        return client.get(path)


# ═══════════════════════════════════════════════════════════════════════
# PARTIE A
# ═══════════════════════════════════════════════════════════════════════

def test_served_sources_list_is_complete():
    """La liste dérivée couvre bien les pages modifiées par le lot (garde-fou du garde-fou)."""
    srcs = _served_sources()
    for rel in ("ui/news.html", "ui/moteur.html", "ui/loto-ia.html", "ui/hybride.html", "ui/faq.html",
                "ui/a-propos.html", "ui/disclaimer.html", "ui/templates/em/news.html",
                "ui/templates/em/moteur.html", "ui/templates/em/euromillions-ia.html",
                "ui/templates/em/hybride.html", "ui/templates/em/a-propos.html"):
        assert rel in srcs, rel


@pytest.mark.parametrize("rel", _served_sources())
def test_t1_sources_no_weights(rel):
    hit = _first_hit(_read(rel).replace("\\'", "'"), _FORBIDDEN_WEIGHTS)
    assert hit is None, f"{rel}: pondération chiffrée « {hit} »"


@pytest.mark.parametrize("lang", _LANGS)
def test_t2_po_no_weights(lang):
    for e in _po(lang):
        for s in (e["id"], e["str"]):
            hit = _first_hit(s, _FORBIDDEN_WEIGHTS)
            assert hit is None, f"{lang}: « {hit} » dans {s[:80]}"


@pytest.mark.parametrize("rel", _served_sources())
def test_t4_sources_no_promises(rel):
    hit = _first_hit(_read(rel).replace("\\'", "'"), _PROMISES)
    assert hit is None, f"{rel}: promesse « {hit} »"


@pytest.mark.parametrize("lang", _LANGS)
def test_t4_po_no_promises(lang):
    for e in _po(lang):
        for s in (e["id"], e["str"]):
            hit = _first_hit(s, _PROMISES)
            assert hit is None, f"{lang}: « {hit} » dans {s[:80]}"


@pytest.mark.parametrize("key", list(_ACTIVE_PROMPTS))
def test_t5_prompts_no_promises_keep_no_invention(key):
    rel, keep = _ACTIVE_PROMPTS[key]
    text = _read(rel)
    hit = _first_hit(text, _PROMISES)
    assert hit is None, f"{rel}: promesse « {hit} »"
    assert keep in text, f"{rel}: consigne « {keep} » absente"


_LOTO_RENDERED = ["/news", "/moteur", "/loto/intelligence-artificielle", "/hybride", "/a-propos",
                  "/disclaimer", "/faq"]
_EM_RENDERED = ["news", "moteur", "ia", "hybride_page", "a_propos", "disclaimer"]


@pytest.mark.parametrize("path", _LOTO_RENDERED)
def test_t3_loto_pages_rendered_clean(client, path):
    resp = _get(client, path)
    assert resp.status_code == 200, f"{path}: HTTP {resp.status_code}"
    body = html.unescape(resp.text)
    assert _first_hit(body, _FORBIDDEN_WEIGHTS) is None, path
    assert _first_hit(body, _PROMISES) is None, path


@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("page", _EM_RENDERED)
def test_t3_em_pages_rendered_clean(client, page, lang):
    path = EM_URLS[lang][page]
    resp = _get(client, path)
    assert resp.status_code == 200, f"{path}: HTTP {resp.status_code}"
    body = html.unescape(resp.text)
    assert _first_hit(body, _FORBIDDEN_WEIGHTS) is None, path
    assert _first_hit(body, _PROMISES) is None, path


# G17 étendu — formulations interdites pour le mode Récent (reprise de test_lot_coherence_reduit)
_RECENT_FORBIDDEN = {
    "fr": r"tendance|derniers tirages|dernières années|actuel",
    "en": r"trend|latest draws|last \d years|current",
    "es": r"tendencia|últimos sorteos|últimos \d años|actual",
    "pt": r"tendência|últimos sorteios|últimos \d anos|atua",
    "de": r"Trend|jüngsten Ziehungen|letzten \d Jahre|aktuelle[nrs]?\b",
    "nl": r"trend|laatste trekkingen|laatste \d jaar|actue",
}
_MODE_CELL = re.compile(r"<code>(conservative|balanced|recent)</code></td>\s*<td[^>]*>(.*?)</td>", re.S)


def _mode_cells(body: str) -> dict:
    return {m.group(1): html.unescape(m.group(2)).strip() for m in _MODE_CELL.finditer(body)}


def test_t6_loto_moteur_modes_match_faq():
    cells = _mode_cells(_read("ui/moteur.html"))
    faq = _read("ui/faq.html")
    assert set(cells) == {"conservative", "balanced", "recent"}
    for mode, label in (("conservative", "Conservateur"), ("balanced", "Équilibré"), ("recent", "Récent")):
        m = re.search(rf"<li><strong>{label}</strong> : (.*?)</li>", faq)
        assert m, label
        expected = m.group(1)
        assert cells[mode] == expected[0].upper() + expected[1:], mode
    assert not re.search(_RECENT_FORBIDDEN["fr"], cells["recent"], re.IGNORECASE)
    assert "fréquences et retards" not in cells["balanced"]


@pytest.mark.parametrize("lang", _LANGS)
def test_t6_em_moteur_modes(client, lang):
    resp = _get(client, EM_URLS[lang]["moteur"])
    assert resp.status_code == 200
    cells = _mode_cells(resp.text)
    assert set(cells) == {"conservative", "balanced", "recent"}
    flags = re.IGNORECASE if lang != "de" else 0
    assert not re.search(_RECENT_FORBIDDEN[lang], cells["recent"], flags), cells["recent"]
    assert "fréquences et retards" not in cells["balanced"]


@pytest.mark.parametrize("lang", _LANGS)
def test_t7_old_msgids_gone(lang):
    ids = [e["id"] for e in _po(lang)]
    for frag in _OLD_MSGID_FRAGMENTS:
        assert not any(frag in i for i in ids), f"{lang}: ancien msgid encore présent « {frag} »"


@pytest.mark.parametrize("lang", _LANGS)
def test_t8_new_msgids_present(lang):
    entries = _po(lang)
    for frag in _NEW_MSGID_FRAGMENTS:
        hits = [e for e in entries if frag in e["id"]]
        assert hits, f"{lang}: nouveau msgid absent « {frag} »"
        assert not any(e["fuzzy"] for e in hits), f"{lang}: msgid fuzzy « {frag} »"


def test_t8_new_msgids_match_templates():
    """Chaque fragment est bien un msgid de template EM (pas une entrée orpheline)."""
    tpl = "".join(_read(f"ui/templates/em/{t}").replace("\\'", "'") for t in
                  ("news.html", "moteur.html", "euromillions-ia.html", "hybride.html", "a-propos.html"))
    for frag in _NEW_MSGID_FRAGMENTS:
        assert frag in tpl, frag


# ── T8-bis / T8-ter / T19 — traductions (prompt n° 2) ──────────────────────

_FOREIGN = ("en", "es", "pt", "de", "nl")

# Les 33 msgid du lot (page EM, msgid FR exact), généré depuis les templates
_LOT_MSGIDS = (
    ('news', 'Actualités du module EuroMillions de LotoIA. Moteur HYBRIDE adapté 5+2, chatbot IA Gemini, plus de 700 tirages historiques. 100% gratuit, sans inscription.'),
    ('news', 'Actualités du module EuroMillions de LotoIA. Moteur HYBRIDE adapté 5+2, chatbot IA Gemini, plus de 700 tirages européens.'),
    ('news', 'Notre engagement reste le même : un outil transparent, fondé sur les données réelles, et toujours plus agréable à utiliser. Merci à toute la communauté qui nous fait remonter ces petits détails — chacun de vos retours compte.'),
    ('news', '<strong>729 tirages officiels analysés</strong> (à cette date, période 2019-2026) — importés depuis les données officielles FDJ.'),
    ('news', "<strong>729 tirages historiques</strong> (à cette date) en base de données sécurisée, alimentant l'ensemble des analyses du moteur EuroMillions."),
    ('news', '<strong>Chatbot HYBRIDE dédié</strong> déployé en production : il interroge directement la base de données EuroMillions, conserve le fil de la conversation et encadre ses réponses pour éviter toute prédiction.'),
    ('news', '<strong>Accès direct aux données EuroMillions</strong> : le chatbot interroge directement notre base de 729 tirages officiels (à cette date) pour vous donner des réponses précises et vérifiables.'),
    ('news', '<strong>Base de données dédiée</strong> : table <code>tirages_euromillions</code> en Cloud SQL, indépendante de la base Loto, avec 729 tirages historiques (à cette date).'),
    ('news', 'Le moteur HYBRIDE EuroMillions est le cœur algorithmique du module européen. Il explore les statistiques des tirages en combinant plusieurs approches complémentaires, adaptées au format 5+2 :'),
    ('news', "<strong>Trois fenêtres d'analyse</strong> : les 5 dernières années, les 2 dernières années et l'ensemble de l'historique disponible, pour les numéros comme pour les étoiles."),
    ('news', "<strong>Poids des tirages récents</strong> : présents dans les trois fenêtres, ils pèsent davantage dans l'analyse."),
    ('news', 'Mise à jour du 09/11/2026 : la première version de cet article décrivait, de façon imprécise, l\'ancien modèle à deux périodes. Depuis mars 2026, le moteur HYBRIDE combine trois fenêtres d\'analyse. Détails sur la page <a href="%(methodo_url)s">Méthodologie</a>.'),
    ('moteur', 'Analyse fréquentielle sur trois fenêtres (5 ans, 2 ans, historique complet)'),
    ('moteur', "Calcul des fréquences d'apparition de chaque numéro (1-50) et de chaque étoile (1-12) sur trois fenêtres : les 5 dernières années, les 2 dernières années et l'ensemble de l'historique disponible."),
    ('moteur', "Combinaison des trois fenêtres d'analyse : les tirages récents, présents dans les trois, pèsent davantage (méthodologie « 5 ans + 2 »)."),
    ('moteur', "Privilégie l'historique long terme. Idéal si vous préférez des numéros qui ont fait leurs preuves sur la durée."),
    ('moteur', "Répartition harmonieuse entre les 3 périodes. C'est le mode par défaut, utilisé par le générateur du site ; les deux autres modes peuvent être demandés au chatbot HYBRIDE."),
    ('moteur', 'Pour ceux qui veulent davantage de diversité dans les grilles proposées.'),
    ('ia', "ChatGPT est un modèle de langage génératif qui n'a pas accès aux données réelles des tirages. Il invente des numéros sans fondement statistique. LotoIA utilise une IA Grounded connectée aux %(total)s+ tirages officiels EuroMillions : ses réponses s'appuient sur ces données réelles."),
    ('ia', "<strong>Analyse fréquentielle</strong> — Calcul des fréquences d'apparition de chaque numéro (1-50) et de chaque étoile (1-12) sur trois fenêtres : les 5 dernières années, les 2 dernières années et l'ensemble de l'historique disponible."),
    ('ia', '<strong>Pondération temporelle</strong> — Combinaison des trois fenêtres : les tirages récents, présents dans les trois, pèsent davantage (<a href="%(methodo_url)s">méthodologie « 5 ans + 2 »</a>).'),
    ('ia', "Le moteur combine trois fenêtres d'analyse : <strong>les 5 dernières années</strong>, <strong>les 2 dernières années</strong> et <strong>l'ensemble de l'historique disponible</strong>. Les tirages récents, présents dans les trois fenêtres, pèsent davantage : la méthode équilibre stabilité statistique et réactivité."),
    ('ia', "LotoIA intègre un chatbot alimenté par <strong>Gemini</strong> (Google DeepMind) en mode « Grounded » : l'IA est connectée en temps réel à la base de données des tirages. Chaque réponse est ancrée sur des données vérifiées. Vous pouvez lui poser des questions sur les statistiques, les fréquences ou demander une analyse personnalisée."),
    ('ia', "ChatGPT invente des numéros sans accès aux données réelles. LotoIA utilise une IA « Grounded » connectée aux tirages officiels EuroMillions : ses réponses s'appuient sur les données réelles, pas sur des connaissances générales."),
    ('hybride_page', 'Assistant IA connecté en temps réel aux %(total)s+ tirages officiels EuroMillions. Analyses factuelles, avec contrôles automatiques des chiffres cités.'),
    ('hybride_page', 'Assistant IA connecté aux tirages officiels EuroMillions. Analyses factuelles, avec contrôles automatiques des chiffres cités.'),
    ('hybride_page', 'Assistant IA conversationnel connecté en temps réel aux tirages officiels EuroMillions. Analyse factuelle fondée sur les tirages officiels.'),
    ('hybride_page', 'Contrôles automatiques des chiffres cités'),
    ('hybride_page', 'HYBRIDE utilise une architecture Grounded (RAG) : il interroge la base de données des %(total)s+ tirages officiels EuroMillions en temps réel, puis Gemini (Google DeepMind) formule une réponse factuelle à partir des données récupérées. Des contrôles automatiques comparent ensuite la réponse aux données.'),
    ('hybride_page', "En termes techniques, HYBRIDE utilise une architecture appelée <strong>RAG</strong> (Retrieval-Augmented Generation) : le modèle « récupère » d'abord les données pertinentes dans la base, puis « augmente » sa réponse avec ces données vérifiées. Le résultat : des réponses ancrées sur les données réelles des tirages. Aucune IA n'est infaillible : en cas de doute, vérifiez sur l'historique officiel."),
    ('hybride_page', '<strong>Contrôles anti-hallucination</strong> : les chiffres cités sont comparés aux données EuroMillions'),
    ('hybride_page', 'Contrôles automatiques'),
    ('a_propos', 'Notre chatbot intelligent est alimenté par <strong>Gemini</strong> (Google DeepMind) en mode « Grounded » : il est connecté en temps réel à nos bases de données de tirages officiels. Chaque réponse est ancrée sur des données réelles et vérifiables.'),
)
_PLACEHOLDER = re.compile(r"%\([a-z_]+\)s")
_TAG = re.compile(r"<[^>]+>")


def test_t8bis_lot_msgids_count_and_templates():
    assert len(_LOT_MSGIDS) == 33
    tpl = {p: _read(f"ui/templates/em/{f}").replace("\\'", "'") for p, f in (
        ("news", "news.html"), ("moteur", "moteur.html"), ("ia", "euromillions-ia.html"),
        ("hybride_page", "hybride.html"), ("a_propos", "a-propos.html"))}
    for page, msgid in _LOT_MSGIDS:
        assert f"_('{msgid}')" in tpl[page], f"{page}: msgid absent du template : {msgid[:60]}"


def _entry(lang: str, msgid: str) -> dict | None:
    return next((e for e in _po(lang) if e["id"] == msgid), None)


@pytest.mark.parametrize("lang", _FOREIGN)
def test_t8bis_msgstr_filled(lang):
    for _page, msgid in _LOT_MSGIDS:
        e = _entry(lang, msgid)
        assert e is not None, f"{lang}: msgid absent : {msgid[:60]}"
        assert e["str"].strip(), f"{lang}: msgstr vide : {msgid[:60]}"
        assert not e["fuzzy"], f"{lang}: fuzzy : {msgid[:60]}"
        assert e["str"] != msgid, f"{lang}: msgstr identique au français : {msgid[:60]}"


@pytest.mark.parametrize("lang", _FOREIGN)
def test_t8ter_python_format_placeholders(lang):
    checked = 0
    for _page, msgid in _LOT_MSGIDS:
        ph = sorted(_PLACEHOLDER.findall(msgid))
        if not ph:
            continue
        checked += 1
        assert sorted(_PLACEHOLDER.findall(_entry(lang, msgid)["str"])) == ph, f"{lang}: {msgid[:60]}"
    assert checked == 5  # N13, I1, I3, H-og, H5


@pytest.mark.parametrize("lang", _FOREIGN)
def test_t8ter_tags_preserved(lang):
    for _page, msgid in _LOT_MSGIDS:
        dst = _entry(lang, msgid)["str"]
        for tag in ("<strong>", "</strong>", "<code>", "</code>", "<a ", "</a>"):
            assert msgid.count(tag) == dst.count(tag), f"{lang}: balise {tag} : {msgid[:60]}"


def _norm(text: str) -> str:
    """Texte visible : balises retirées, entités décodées, espaces normalisés."""
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text))).strip()


_JSON_U = re.compile(r"\\u([0-9a-fA-F]{4})")


def _haystacks(page_html: str) -> tuple[str, str]:
    """(HTML brut décodé, texte visible) d'une page rendue.

    Le brut décodé couvre les attributs (meta og/twitter) et le JSON-LD (`|tojson` encode les accents
    et < > & ' en \\uXXXX) ; le texte visible couvre les msgid contenant des balises.
    """
    raw = html.unescape(_JSON_U.sub(lambda m: chr(int(m.group(1), 16)), page_html))
    raw = re.sub(r"\s+", " ", raw)
    return raw, _norm(raw)


def _fr_fragments(msgid: str) -> list[str]:
    """Fragments FR significatifs d'un msgid : morceaux de 40 caractères (pas de 20) de chaque segment
    hors placeholder ; un msgid plus court que 40 caractères est cherché en entier."""
    frags = []
    for seg in _PLACEHOLDER.split(msgid):
        seg = _norm(seg)
        if len(seg) < 40:
            if seg and len(_norm(_PLACEHOLDER.sub("", msgid))) < 40:
                frags.append(seg)
            continue
        starts = list(range(0, len(seg) - 40 + 1, 20)) + [len(seg) - 40]
        frags += [seg[i:i + 40] for i in sorted(set(starts))]
    return frags


_T19_PAGES = ("news", "moteur", "ia", "hybride_page", "a_propos")


@pytest.mark.parametrize("lang", _FOREIGN)
@pytest.mark.parametrize("page", _T19_PAGES)
def test_t19_zero_fr_string_visible(client, page, lang):
    """« ZÉRO string FR visible » : aucun fragment des 33 msgid français dans la page EM rendue."""
    path = EM_URLS[lang][page]
    resp = _get(client, path)
    assert resp.status_code == 200, f"{path}: HTTP {resp.status_code}"
    raw, text = _haystacks(resp.text)
    found = sorted({f for _p, msgid in _LOT_MSGIDS for f in _fr_fragments(msgid) if f in raw or f in text})
    assert not found, f"{path}: chaînes FR visibles : {found}"
    # preuve positive : les traductions de la page sont bien rendues (texte, attributs ou JSON-LD)
    for p, msgid in _LOT_MSGIDS:
        if p != page:
            continue
        dst = _norm(_PLACEHOLDER.split(_entry(lang, msgid)["str"])[0])[:40]
        assert dst in text or dst in raw, f"{path}: traduction absente : {dst}"


@pytest.mark.parametrize("page", _T19_PAGES)
def test_t19_detector_sees_french_on_fr_page(client, page):
    """Contre-épreuve : sur la page FR, le détecteur de T19 trouve bien les msgid de la page
    (y compris ceux en meta og/twitter et en JSON-LD), sinon T19 serait vide de sens."""
    resp = _get(client, EM_URLS["fr"][page])
    assert resp.status_code == 200
    raw, text = _haystacks(resp.text)
    for p, msgid in _LOT_MSGIDS:
        if p != page:
            continue
        frags = _fr_fragments(msgid)
        assert frags and any(f in raw or f in text for f in frags), f"{page}: msgid FR non détecté : {msgid[:60]}"


def test_t9_loto_news_dated():
    text = _read("ui/news.html")
    assert "Mise à jour du 09/11/2026" in text
    assert '<a href="/methodologie">Méthodologie</a>' in text
    for m in re.finditer(r"\b(981|729) tirages", text):
        tail = text[m.end():m.end() + 80]
        assert "(à cette date" in tail, f"compteur non daté : {text[m.start():m.end() + 40]}"


def test_t9_em_news_template_dated():
    text = _read("ui/templates/em/news.html").replace("\\'", "'")
    assert "Mise à jour du 09/11/2026" in text
    assert "|format(methodo_url=urls.methodologie)" in text
    assert "729 tirages historiques. 100%" not in text and "729 tirages européens" not in text
    for m in re.finditer(r"\b729 tirages", text):
        tail = text[m.end():m.end() + 80]
        assert "(à cette date" in tail, text[m.start():m.end() + 40]


def test_t9_em_news_meta_rendered(client):
    resp = _get(client, "/euromillions/news")
    assert resp.status_code == 200
    meta = re.findall(r'<meta (?:property="og:description"|name="twitter:description") content="([^"]*)"',
                      resp.text)
    assert len(meta) == 2
    for content in meta:
        content = html.unescape(content)
        assert "plus de 700 tirages" in content and "729" not in content
    assert 'href="/euromillions/methodologie">Méthodologie</a>' in resp.text


def test_t10_loto_news_date_modified():
    text = _read("ui/news.html")
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)
    for raw in blocks:
        json.loads(raw)  # JSON-LD toujours valide
    for pub in ("2026-04-27", "2026-02-14", "2026-02-11"):
        assert re.search(rf'"datePublished": "{pub}",\s*"dateModified": "2026-11-09"', text), pub
    for pub in ("2026-06-10", "2026-03-30", "2026-03-25", "2026-03-15", "2026-03-11"):
        assert re.search(rf'"datePublished": "{pub}",\s*"dateModified": "{pub}"', text), pub


def test_t10_em_news_date_modified():
    text = _read("ui/templates/em/news.html")
    for pub in ("2026-04-27", "2026-02-14", "2026-02-11", "2026-02-10"):
        assert f'"datePublished": "{pub}", "dateModified": "2026-11-09",' in text, pub
    for pub in ("2026-06-10", "2026-04-13", "2026-03-30", "2026-03-25", "2026-03-15"):
        assert f'"datePublished": "{pub}", "dateModified": "{pub}",' in text, pub


# ── T11 — note JSON-LD EuroMillions ───────────────────────────────────────

@pytest.mark.asyncio
async def test_t11_fetch_em_rating_sources():
    from services import em_rating
    mock = AsyncMock(return_value={"review_count": 52, "avg_rating": 4.46})
    with patch("db_cloudsql.async_fetchone", mock):
        value, count = await em_rating.fetch_em_rating()
    assert (value, count) == (4.5, 52)
    sql, params = mock.call_args.args
    assert "FROM ratings WHERE source IN (%s, %s, %s)" in sql
    assert params == ("popup_em", "chatbot_em", "chatbot_em_en")


@pytest.mark.asyncio
async def test_t11_fetch_em_rating_error_and_empty():
    from services import em_rating
    with patch("db_cloudsql.async_fetchone", AsyncMock(side_effect=RuntimeError("db down"))):
        assert await em_rating.fetch_em_rating() == (0, 0)
    with patch("db_cloudsql.async_fetchone", AsyncMock(return_value={"review_count": 0, "avg_rating": None})):
        assert await em_rating.fetch_em_rating() == (0, 0)


def test_t11_em_rating_debt_documented():
    text = _read("services/em_rating.py")
    assert "chatbot_em_es" in text and "schemas.py:77" in text and "migration 014" in text


@pytest.mark.parametrize("path", ["/euromillions", "/en/euromillions", "/de/euromillions"])
def test_t11_em_accueil_uses_all_sources(client, path):
    mock = AsyncMock(return_value={"review_count": 12, "avg_rating": 4.6})
    with patch("db_cloudsql.get_connection", _async_cm_conn(_make_cursor())), \
         patch("db_cloudsql.async_fetchone", mock):
        resp = client.get(path)
    assert resp.status_code == 200
    assert '"ratingValue": "4.6"' in resp.text and '"ratingCount": "12"' in resp.text
    assert any("source IN (%s, %s, %s)" in str(c.args[0]) for c in mock.call_args_list)
    assert not any("ratings_aggregate" in str(c.args[0]) for c in mock.call_args_list)


def test_t11_loto_accueil_unchanged():
    text = _read("routes/pages.py")
    assert 'SELECT review_count, avg_rating FROM ratings_global' in text


# ═══════════════════════════════════════════════════════════════════════
# PARTIE B
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def clean_cost_cache():
    import services.gcp_monitoring as gm
    gm._LOCAL_CACHE.clear()
    yield gm
    gm._LOCAL_CACHE.clear()


@pytest.mark.asyncio
async def test_t12_cost_config_defaults(clean_cost_cache):
    gm = clean_cost_cache
    with patch("db_cloudsql.async_fetchall", AsyncMock(return_value=[])):
        cfg = await gm.get_cost_config()
    assert cfg["cloud_run_daily_eur"] == 0.88 and cfg["cloud_sql_daily_eur"] == 2.97
    assert cfg["other_daily_eur"] == 0.33 and cfg["usd_to_eur"] == 0.92
    assert cfg["gemini_input_per_1m_usd"] == 0.30 and cfg["gemini_output_per_1m_usd"] == 2.50
    assert cfg["calibration_label"] == "facture octobre 2026"


@pytest.mark.asyncio
async def test_t12_cost_config_overrides_and_invalid(clean_cost_cache):
    gm = clean_cost_cache
    rows = [
        {"config_key": "cost_cloud_sql_daily_eur", "config_value": "1.10"},
        {"config_key": "cost_cloud_run_daily_eur", "config_value": "abc"},
        {"config_key": "cost_other_daily_eur", "config_value": "-1"},
        {"config_key": "cost_calibration_label", "config_value": "x" * 150},
        {"config_key": "cost_inconnu", "config_value": "9"},
    ]
    with patch("db_cloudsql.async_fetchall", AsyncMock(return_value=rows)):
        cfg = await gm.get_cost_config()
    assert cfg["cloud_sql_daily_eur"] == 1.10
    assert cfg["cloud_run_daily_eur"] == 0.88  # non numérique → défaut
    assert cfg["other_daily_eur"] == 0.33      # négatif → défaut
    assert cfg["calibration_label"] == "x" * 100
    assert "inconnu" not in cfg


@pytest.mark.asyncio
async def test_t12_cost_config_db_error(clean_cost_cache):
    gm = clean_cost_cache
    with patch("db_cloudsql.async_fetchall", AsyncMock(side_effect=RuntimeError("down"))):
        cfg = await gm.get_cost_config()
    assert cfg["cloud_sql_daily_eur"] == 2.97


def test_t13_estimate_costs_defaults():
    from services.gcp_monitoring import _estimate_costs
    costs = _estimate_costs({"active_instances": 2}, {"tokens_in": 0, "tokens_out": 0})
    assert costs["total_today_eur"] == 4.18
    assert costs["estimated_month_eur"] == 125.4
    assert costs["other_today_eur"] == 0.33
    assert costs["calibration_label"] == "facture octobre 2026"


def test_t13_estimate_costs_gemini_25():
    from services.gcp_monitoring import _estimate_costs
    costs = _estimate_costs({}, {"tokens_in": 1_000_000, "tokens_out": 1_000_000})
    assert costs["gemini_today_eur"] == round((0.30 + 2.50) * 0.92, 4)


@pytest.mark.asyncio
async def test_t14_metrics_chat_latency_and_thresholds(clean_cost_cache):
    gm = clean_cost_cache
    counters = {"calls": 12, "errors": 0, "tokens_in": 0, "tokens_out": 0, "total_ms": 60000,
                "chat_calls": 10, "chat_ms": 12000}
    with patch("services.gcp_monitoring.cache_get", AsyncMock(return_value=None)), \
         patch("services.gcp_monitoring.cache_set", AsyncMock()), \
         patch("services.gcp_monitoring._fetch_cloud_run_metrics", AsyncMock(return_value={})), \
         patch("services.gcp_monitoring._get_gemini_counters", AsyncMock(return_value=counters)), \
         patch("services.gcp_monitoring._maybe_snapshot", AsyncMock()), \
         patch("services.alerting.process_alerts", AsyncMock(return_value=[])), \
         patch("db_cloudsql.async_fetchall", AsyncMock(return_value=[])):
        payload = await gm.get_gcp_metrics()
    assert payload["gemini"]["avg_response_time_ms"] == 1200
    assert payload["gemini"]["calls_today"] == 12
    assert payload["costs"]["thresholds"] == {"warn": 165.0, "crit": 200.0}


@pytest.mark.asyncio
async def test_t14_counters_sql_has_chat_columns(clean_cost_cache):
    gm = clean_cost_cache
    mock = AsyncMock(return_value={"calls": 3, "errors": 0, "tokens_in": 1, "tokens_out": 2, "total_ms": 30})
    with patch("db_cloudsql.async_fetchone", mock):
        res = await gm._get_gemini_counters()
    assert "AS chat_calls" in mock.call_args.args[0] and "AS chat_ms" in mock.call_args.args[0]
    assert res["chat_calls"] == 0 and res["chat_ms"] == 0  # colonnes absentes du mock → 0


# ── T15 — traçage des 4 appels Vertex ─────────────────────────────────────

def _track_calls(mock):
    return [(c.kwargs.get("call_type"), c.kwargs.get("lang"), c.args[1:3] if len(c.args) > 2 else None,
             c.kwargs.get("error", False)) for c in mock.call_args_list]


@pytest.mark.asyncio
async def test_t15_sql_loto_tracked(mock_vertex_client):
    track = AsyncMock()
    with mock_vertex_client() as vc, \
         patch("services.chat_sql.load_prompt", return_value="prompt"), \
         patch("services.gcp_monitoring.track_gemini_call", track):
        vc.set_response(text="SELECT 1", tin=120, tout=8)
        from services.chat_sql import _generate_sql
        await _generate_sql("combien de tirages", MagicMock(), "fake-key")
    assert ("sql_loto", "fr", (120, 8), False) in _track_calls(track)


@pytest.mark.asyncio
async def test_t15_sql_em_tracked_error(mock_vertex_client):
    track = AsyncMock()
    with mock_vertex_client() as vc, \
         patch("services.chat_sql_em.load_prompt_em", return_value="prompt"), \
         patch("services.gcp_monitoring.track_gemini_call", track):
        vc.set_timeout()
        from services.chat_sql_em import _generate_sql_em
        await _generate_sql_em("how many draws", MagicMock(), "fake-key", lang="en")
    calls = _track_calls(track)
    assert any(c[0] == "sql_em" and c[1] == "en" and c[3] is True for c in calls), calls


@pytest.mark.asyncio
async def test_t15_pitch_tracked_success_and_failure(mock_vertex_client, make_client_error):
    from services.chat_pipeline_gemini import handle_pitch_common
    from services.gemini_cache import pitch_cache

    async def _ctx():
        return "ctx"

    async def _run(call_type):
        pitch_cache.clear()
        return await handle_pitch_common(
            {"t": call_type}, MagicMock(), "fr", context_coro=_ctx(), load_prompt_fn=lambda n: "prompt",
            prompt_name="PITCH_TEST", log_prefix="[T15]", timeout_context=5, timeout_gemini=10,
            max_retries=0, call_type=call_type,
        )

    track = AsyncMock()
    with mock_vertex_client() as vc, patch("services.gcp_monitoring.track_gemini_call", track):
        vc.set_response(text='{"pitchs": ["ok"]}', tin=300, tout=900)
        ok = await _run("pitch_em")
        vc.set_error(make_client_error(400))
        ko = await _run("pitch_loto")
    assert ok["success"] is True and ko["success"] is False
    calls = _track_calls(track)
    assert ("pitch_em", "fr", (300, 900), False) in calls
    assert any(c[0] == "pitch_loto" and c[3] is True for c in calls), calls


@pytest.mark.asyncio
async def test_t15_chat_sync_tracked(mock_vertex_client):
    from services.chat_pipeline_gemini import call_gemini_and_respond
    ctx = {"mode": "balanced", "system_prompt": "sys", "contents": [], "history": [], "insult_prefix": "",
           "_chat_meta": None}
    track = AsyncMock()
    with mock_vertex_client() as vc, patch("services.gcp_monitoring.track_gemini_call", track), \
         patch("services.chat_pipeline_gemini.log_from_meta", MagicMock()):
        vc.set_timeout()
        await call_gemini_and_respond(ctx, "fallback", "[T15]", "em", "de", "frage", "/de/euromillions")
    assert any(c[0] == "chat_em_sync" and c[1] == "de" and c[3] is True for c in _track_calls(track))


def test_t16_call_types():
    from services.gcp_monitoring import _CALL_TYPES
    assert "meta_analyse" not in _CALL_TYPES
    for t in ("chat_loto", "chat_em", "chat_loto_sync", "chat_em_sync", "pitch_loto", "pitch_em",
              "sql_loto", "sql_em", "enrichment_loto", "enrichment_em"):
        assert t in _CALL_TYPES
    assert len(_CALL_TYPES) == 10


def test_t16_pitch_call_sites_pass_call_type():
    assert 'call_type="pitch_loto"' in _read("services/chat_pipeline.py")
    assert 'call_type="pitch_em"' in _read("services/chat_pipeline_em.py")


# ── T17 — /admin/config + carte Monitoring ────────────────────────────────

def test_t17_admin_config_costs_save(client, clean_cost_cache):
    client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
    query = AsyncMock()
    with patch("db_cloudsql.async_query", query), \
         patch("db_cloudsql.async_fetchone", AsyncMock(return_value={})), \
         patch("db_cloudsql.async_fetchall", AsyncMock(return_value=[])):
        resp = client.post("/admin/config/costs", data={
            "cost_cloud_sql_daily_eur": "1,10",
            "cost_cloud_run_daily_eur": "-2",
            "cost_other_daily_eur": "abc",
            "cost_usd_to_eur": "0",
            "cost_calibration_label": "facture novembre 2026",
        })
    assert resp.status_code == 200
    stored = {c.args[1][0]: c.args[1][1] for c in query.call_args_list}
    assert stored == {"cost_cloud_sql_daily_eur": "1.1", "cost_calibration_label": "facture novembre 2026"}
    assert "Modèle de coûts enregistré." in resp.text


def test_t17_admin_config_page_labels(client, clean_cost_cache):
    client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
    with patch("db_cloudsql.async_fetchone", AsyncMock(return_value={})), \
         patch("db_cloudsql.async_fetchall", AsyncMock(return_value=[])):
        resp = client.get("/admin/config")
    assert resp.status_code == 200
    body = html.unescape(resp.text)
    assert "règle : coût mensuel attendu × 1,15" in body and "règle : coût mensuel attendu × 1,40" in body
    for name in ("cost_cloud_run_daily_eur", "cost_cloud_sql_daily_eur", "cost_other_daily_eur",
                 "cost_gemini_input_per_1m_usd", "cost_gemini_output_per_1m_usd", "cost_usd_to_eur",
                 "cost_calibration_label"):
        assert f'name="{name}"' in body, name
    assert 'value="facture octobre 2026"' in body


def test_t17_admin_config_costs_requires_auth(client):
    client.cookies.clear()
    resp = client.post("/admin/config/costs", data={"cost_cloud_sql_daily_eur": "1"}, follow_redirects=False)
    assert resp.status_code in (302, 303, 401, 403)


def test_t17_monitoring_card_reads_thresholds():
    text = _read("ui/templates/admin/monitoring.html")
    assert "estimated_month_eur >= 120" not in text and "estimated_month_eur >= 90" not in text
    assert "c.thresholds" in text and "v-cost-note" in text and "calibration_label" in text
    assert "meta_analyse" not in text and "pitch_em: 'Pitch EM'" in text


# ── T18 — seuils coût mensuel ─────────────────────────────────────────────

def test_t18_default_cost_thresholds():
    from services.alerting import DEFAULT_THRESHOLDS
    assert DEFAULT_THRESHOLDS["alert_cost_month_warn"] == "165"
    assert DEFAULT_THRESHOLDS["alert_cost_month_crit"] == "200"


@pytest.mark.asyncio
@pytest.mark.parametrize("month, expected", [(143, None), (170, "warning"), (210, "critical")])
async def test_t18_cost_alert_levels(month, expected):
    from services.alerting import DEFAULT_THRESHOLDS, check_alerts
    metrics = {"error_rate_5xx": 0, "latency_p95_ms": 0, "cpu_utilization": 0, "memory_utilization": 0}
    with patch("services.alerting.get_alert_thresholds", AsyncMock(return_value=dict(DEFAULT_THRESHOLDS))), \
         patch("services.alerting._is_cooled_down", AsyncMock(return_value=False)), \
         patch("services.alerting._set_cooldown", AsyncMock()):
        alerts = await check_alerts(metrics, {"avg_response_time_ms": 0}, {"estimated_month_eur": month})
    levels = [a.level for a in alerts if a.metric_name == "cost_month"]
    assert levels == ([] if expected is None else [expected])
