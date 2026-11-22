"""
Tests — LOT 1.6.076 « presse » (Release 1.6.076, 22/11/2026). Lot de textes : aucun routage, détecteur,
garde-fou ni filtre de sortie touché.

  T-A  7 prompts chatbot chargés : « grounded » une seule fois, en minuscules, entre guillemets droits ;
  T-B  formes interdites absentes (IA Grounded, connecté en temps réel, statistiques LIVE, FIER, Zéro invention,
       « est ce soir ! »…) ;
  T-C  formulation cible épinglée par langue ;
  T-D  prompt Loto : plus de « depuis 2019 », « novembre 2019 », « 6 novembre », « 24 tirages » ; fenêtre glissante ;
  T-E  consigne conditionnelle « ce soir » une fois par prompt ;
  T-F  réponses toutes faites (insultes L1) : plus de « seul chatbot » ni de « temps réel » ; taille des pools = HEAD ;
  T-G  hero EN /en/euromillions/hybride « Conversational AI based on real data » ;
  T-H  launcher : « statistiques mises à jour après chaque tirage » (gabarit, 6 .po, rendu des 6 langues) ;
  T-I  R-9 : widgets EM ES/PT/DE/NL sans aria-label « Close » / « Send », cache-busters v=1.4 ;
  T-J  version (plancher) + 18 app-version en dur = APP_VERSION ;
  T-K  lignes de balises des prompts (liées au code : _INTERNAL_TAGS_PATTERNS, CF-7) inchangées.
"""
import html
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
PROMPTS = {
    "loto": "prompts/chatbot/prompt_hybride.txt",
    **{lg: f"prompts/em/{lg}/prompt_hybride_em.txt" for lg in LANGS},
}


def _read(rel: str) -> str:
    with open(ROOT / rel, encoding="utf-8") as fh:
        return fh.read()


# ═══════════════════════════════════════════════════════
# T-A / T-B / T-C / T-E — prompts chatbot
# ═══════════════════════════════════════════════════════

@pytest.mark.parametrize("key", sorted(PROMPTS))
def test_ta_grounded_once_quoted(key):
    text = _read(PROMPTS[key])
    assert len(re.findall(r"grounded", text, re.IGNORECASE)) == 1, key
    assert text.count('"grounded"') == 1, key


_FORBIDDEN_CI = (
    "IA Grounded", "Grounded AI", '"IA ancrée"', "connecté en temps réel", "connected in real time",
    "conectado en tiempo real", "ligado em tempo real", "in realtime verbonden",
    "statistiques LIVE", "LIVE statistics", "estadísticas EN VIVO", "LIVE-Statistiken", "LIVE-statistieken",
    "estatísticas EM DIRETO",
    "Zéro invention", "Zero invention", "Cero invenciones", "Zero invenções", "Null Erfindungen", "Nul verzinsels",
    "est ce soir !", "is tonight!", "es esta noche!", "é esta noite!", "ist heute Abend!", "is vanavond!",
    "pas ces données en temps réel", "that data in real time", "esos datos en tiempo real",
    "esses dados em tempo real", "Daten nicht in Echtzeit", "gegevens niet in realtime",
)
_FORBIDDEN_WORDS_CS = ("FIER", "PROUD", "ORGULLOSO", "ORGULHOSO", "STOLZ", "TROTS")


@pytest.mark.parametrize("key", sorted(PROMPTS))
def test_tb_forbidden_forms_absent(key):
    text = _read(PROMPTS[key])
    low = text.lower()
    for s in _FORBIDDEN_CI:
        assert s.lower() not in low, (key, s)
    assert not re.search(r"in Echtzeit\b[^\n]*verbunden", text, re.IGNORECASE), key
    for w in _FORBIDDEN_WORDS_CS:
        assert not re.search(rf"\b{w}\b", text), (key, w)


_TARGET = {
    "loto": "ancrées sur la base officielle des tirages",
    "fr": "ancrées sur la base officielle des tirages",
    "en": "anchored on the official EuroMillions draw database",
    "es": "ancladas en la base de datos oficial de sorteos",
    "pt": "ancoradas na base de dados oficial de sorteios",
    "de": "in der offiziellen EuroMillions-Ziehungsdatenbank verankert",
    "nl": "verankerd in de officiele EuroMillions-trekkingsdatabase",
}
_FAQ_Q = {
    "loto": "Q : Comment HYBRIDE obtient-il ses données ?",
    "fr": "Q : Comment HYBRIDE obtient-il ses données ?",
    "en": "Q: How does HYBRIDE get its data?",
    "es": "P: ¿Cómo obtiene HYBRIDE sus datos?",
    "pt": "P: Como obtém o HYBRIDE os seus dados?",
    "de": "F: Wie erhält HYBRIDE seine Daten?",
    "nl": "V: Hoe verkrijgt HYBRIDE zijn gegevens?",
}
_NEW_TITLE = {
    "loto": "[ANCRAGE SUR LA BASE DES TIRAGES — TU DOIS MAÎTRISER CE SUJET]",
    "fr": "[ANCRAGE SUR LA BASE DES TIRAGES — TU DOIS MAÎTRISER CE SUJET]",
    "en": "[ANCHORING ON THE DRAW DATABASE — YOU MUST MASTER THIS TOPIC]",
    "es": "[ANCLAJE EN LA BASE DE SORTEOS — DEBES DOMINAR ESTE TEMA]",
    "pt": "[ANCORAGEM NA BASE DE SORTEIOS — DEVES DOMINAR ESTE TEMA]",
    "de": "[VERANKERUNG IN DER ZIEHUNGSDATENBANK — DU MUSST DIESES THEMA BEHERRSCHEN]",
    "nl": "[VERANKERING IN DE TREKKINGSDATABASE — JE MOET DIT ONDERWERP BEHEERSEN]",
}
_FALLBACK_NEW = {
    "loto": '  d\'un numéro, réponds : "Je n\'ai pas cette statistique sous la main.',
    "fr": '  d\'un numéro, réponds : "Je n\'ai pas cette statistique sous la main.',
    "en": '  respond: "I don\'t have that statistic at hand.',
    "es": '  responde: "No tengo esa estadística a mano.',
    "pt": '  responde: "Não tenho essa estatística à mão.',
    "de": '  antworte: "Diese Statistik habe ich gerade nicht zur Hand.',
    "nl": '  antwoord: "Ik heb die statistiek niet bij de hand.',
}
# Option A du kit presse (l'IA générative peut se tromper), épinglée par langue
_OPTION_A = {
    "loto": "L'IA générative met en forme les réponses et peut se tromper sur les questions complexes",
    "fr": "L'IA générative met en forme les réponses et peut se tromper sur les questions complexes",
    "en": "Generative AI formats the answers and can make mistakes on complex questions",
    "es": "La IA generativa da forma a las respuestas y puede equivocarse en las preguntas complejas",
    "pt": "A IA generativa dá forma às respostas e pode enganar-se nas perguntas complexas",
    "de": "Die generative KI bringt die Antworten in Form und kann sich bei komplexen Fragen irren",
    "nl": "De generatieve AI geeft de antwoorden vorm en kan zich vergissen bij complexe vragen",
}


@pytest.mark.parametrize("key", sorted(PROMPTS))
def test_tc_target_wording(key):
    text = _read(PROMPTS[key])
    lines = text.splitlines()
    assert _TARGET[key] in text, key
    assert lines.count(_NEW_TITLE[key]) == 1, key
    assert lines.count(_FAQ_Q[key]) == 1, key
    assert lines.count(_FALLBACK_NEW[key]) == 1, key
    assert _OPTION_A[key] in text, key


def test_tc_fallback_second_line_unchanged():
    """T3 : la 2ᵉ ligne du repli (verrou test 073 : fin `!"`) ne change pas."""
    loto = _read(PROMPTS["loto"]).splitlines()
    idx = loto.index(_FALLBACK_NEW["loto"])
    assert loto[idx + 1] == '  Consulte la page Statistiques pour voir les stats actualisées !"'
    em = _read(PROMPTS["fr"]).splitlines()
    idx = em.index(_FALLBACK_NEW["fr"])
    assert em[idx + 1] == '  Consulte la page Statistiques EM pour voir les stats actualisées !"'


_COND_TONIGHT = {
    "loto": 'N\'écris "ce soir" que si le bloc l\'indique explicitement.',
    "fr": 'N\'écris "ce soir" que si le bloc l\'indique explicitement.',
    "en": 'Only write "tonight" if the block explicitly says so.',
    "es": 'Escribe "esta noche" solo si el bloque lo indica explícitamente.',
    "pt": 'Só escrevas "esta noite" se o bloco o indicar explicitamente.',
    "de": 'Schreibe "heute Abend" nur, wenn der Block es ausdrücklich angibt.',
    "nl": 'Schrijf alleen "vanavond" als het blok dat uitdrukkelijk aangeeft.',
}


@pytest.mark.parametrize("key", sorted(PROMPTS))
def test_te_tonight_conditional_once(key):
    text = _read(PROMPTS[key])
    assert text.count(_COND_TONIGHT[key]) == 1, key
    line = next(ln for ln in text.splitlines() if _COND_TONIGHT[key] in ln)
    assert "[PROCHAIN TIRAGE]" in line, key  # balise produite par services/chat_sql*.py, conservée


# ═══════════════════════════════════════════════════════
# T-D — prompt Loto : fenêtre glissante
# ═══════════════════════════════════════════════════════

def test_td_loto_prompt_window():
    text = _read(PROMPTS["loto"])
    for s in ("depuis 2019", "novembre 2019", "6 novembre", "24 tirages"):
        assert s not in text, s
    assert "7 dernières années" in text
    assert "fenêtre glissante" in text
    # T6 : la phrase épinglée par le test 072 est conservée en tête de réponse
    assert ("R : Des résultats officiels publiés par la Française des Jeux (FDJ), saisis manuellement après chaque "
            "tirage. La base couvre les 7 dernières années (fenêtre glissante)") in text


# ═══════════════════════════════════════════════════════
# T-F — réponses toutes faites (insultes L1)
# ═══════════════════════════════════════════════════════

_POOLS_HEAD = {  # nombre d'éléments relevé à HEAD 9352a6d
    ("services.chat_responses_loto", "_INSULT_L1"): 8,
    ("services.chat_responses_em_fr", "_INSULT_L1_EM"): 8,
    ("services.chat_responses_em_en", "_INSULT_L1_EM_EN"): 8,
    ("services.chat_responses_em_multilang", "_INSULT_L1_ES"): 7,
    ("services.chat_responses_em_multilang", "_INSULT_L1_PT"): 7,
    ("services.chat_responses_em_multilang", "_INSULT_L1_DE"): 7,
    ("services.chat_responses_em_multilang", "_INSULT_L1_NL"): 7,
}
_POOL_FORBIDDEN = ("seul chatbot", "only chatbot", "único chatbot", "einzige chatbot", "enige chatbot",
                   "temps réel", "real time", "real-time", "tiempo real", "tempo real", "echtzeit", "realtime",
                   "depuis 2019")
_POOL_NEW = {
    "_INSULT_L1": "💡 Petit rappel : mes réponses sont ancrées sur plus de 1 000 tirages officiels du Loto, avec un "
                  "moteur statistique propriétaire. Mais oui, dis-moi encore que je suis nul 😉",
    "_INSULT_L1_EM": "💡 Petit rappel : mes réponses sont ancrées sur la base officielle des tirages EuroMillions, "
                     "avec un moteur statistique propriétaire. Mais oui, dis-moi encore que je suis nul 😉",
}


@pytest.mark.parametrize("mod,name", sorted(_POOLS_HEAD))
def test_tf_pools(mod, name):
    import importlib
    pool = getattr(importlib.import_module(mod), name)
    assert len(pool) == _POOLS_HEAD[(mod, name)], name
    for item in pool:
        low = item.lower()
        for s in _POOL_FORBIDDEN:
            assert s not in low, (name, s)
    if name in _POOL_NEW:
        assert _POOL_NEW[name] in pool, name


# ═══════════════════════════════════════════════════════
# Client (pages servies)
# ═══════════════════════════════════════════════════════

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


def _page(client, path: str) -> str:
    with patch("db_cloudsql.get_connection", _async_cm_conn(_make_cursor())), \
         patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
        resp = client.get(path)
    assert resp.status_code == 200, f"{path} → {resp.status_code}"
    return html.unescape(resp.text)


# ═══════════════════════════════════════════════════════
# T-G — hero EN /en/euromillions/hybride
# ═══════════════════════════════════════════════════════

def test_tg_route_source():
    src = _read("routes/en_em_pages.py")
    assert "grounded" not in src.lower()
    assert 'hero_subtitle="Conversational AI based on real data",' in src


def test_tg_en_hybride_render(client):
    page = _page(client, "/en/euromillions/hybride")
    assert "Conversational AI based on real data" in page
    assert "grounded in real data" not in page


# ═══════════════════════════════════════════════════════
# T-H — launcher (routes/launcher.py:232-260 : /fr /en /es /pt /de /nl)
# ═══════════════════════════════════════════════════════

H_OLD = ("LotoIA : analyse statistique gratuite du Loto et de l'EuroMillions par intelligence artificielle. "
         "Chatbot IA, statistiques en temps réel.")
H_NEW = ("LotoIA : analyse statistique gratuite du Loto et de l'EuroMillions par intelligence artificielle. "
         "Chatbot IA, statistiques mises à jour après chaque tirage.")
H_MSGSTR = {
    "fr": "",  # convention du .po FR : msgstr vide (repli sur le msgid)
    "en": "LotoIA: free AI-powered statistical analysis of Lottery and EuroMillions. HYBRIDE engine, AI chatbot, "
          "statistics updated after each draw.",
    "es": "LotoIA: análisis estadístico gratuito del Loto y EuroMillions con inteligencia artificial. Chatbot IA, "
          "estadísticas actualizadas después de cada sorteo.",
    "pt": "LotoIA: análise estatística gratuita do Loto e EuroMillions por inteligência artificial. Chatbot IA, "
          "estatísticas atualizadas após cada sorteio.",
    "de": "LotoIA: kostenlose statistische Analyse von Lotto und EuroMillions mit künstlicher Intelligenz. "
          "HYBRIDE-Engine, KI-Chatbot, nach jeder Ziehung aktualisierte Statistiken.",
    "nl": "LotoIA: gratis statistische analyse van Lotto en EuroMillions met kunstmatige intelligentie. "
          "HYBRIDE-engine, AI-chatbot, statistieken bijgewerkt na elke trekking.",
}


def test_th_launcher_template():
    src = _read("ui/templates/launcher.html")
    assert "statistiques en temps réel" not in src
    assert src.count(f'_("{H_NEW}")') == 3  # meta description, og:description, twitter:description


@pytest.mark.parametrize("lang", LANGS)
def test_th_po(lang):
    with open(ROOT / "translations" / lang / "LC_MESSAGES" / "messages.po", "rb") as fh:
        cat = read_po(fh, locale=lang)
    assert cat.get(H_OLD) is None, lang
    msg = cat.get(H_NEW)
    assert msg is not None, lang
    assert msg.string == H_MSGSTR[lang], lang
    assert "statistiques en temps réel" not in _read(f"translations/{lang}/LC_MESSAGES/messages.po")


@pytest.mark.parametrize("lang", LANGS)
def test_th_launcher_render(client, lang):
    page = _page(client, f"/{lang}")
    expected = H_MSGSTR[lang] or H_NEW
    for attr in ('name="description"', 'property="og:description"', 'name="twitter:description"'):
        m = re.search(r"<meta " + re.escape(attr) + r' content="([^"]*)"', page)
        assert m, (lang, attr)
        assert m.group(1) == expected, (lang, attr)


# ═══════════════════════════════════════════════════════
# T-I — R-9 widgets chatbot EM ES/PT/DE/NL
# ═══════════════════════════════════════════════════════

@pytest.mark.parametrize("lang", ("es", "pt", "de", "nl"))
def test_ti_widgets(lang):
    src = _read(f"ui/static/hybride-chatbot-em-{lang}.js")
    assert 'aria-label="Close"' not in src and 'aria-label="Send"' not in src
    assert "(LI.chatbot_close_label || '" in src
    assert "(LI.chatbot_send_label || '" in src
    tpl = _read("config/templates.py")
    assert f'"/ui/static/hybride-chatbot-em-{lang}.js?v=1.4"' in tpl


# ═══════════════════════════════════════════════════════
# T-J — version
# ═══════════════════════════════════════════════════════

_APP_VERSION_FILES = [f"ui/{p}.html" for p in (
    "a-propos", "accueil", "disclaimer", "faq", "historique", "hybride", "loto-ia", "loto", "mentions-legales",
    "methodologie", "moteur", "news", "numeros-les-plus-sortis", "politique-confidentialite", "politique-cookies",
    "simulateur", "statistiques")] + ["ui/templates/em/_footer.html"]


def test_tj_version():
    from config.version import APP_VERSION, VERSION_DATE
    assert tuple(int(p) for p in APP_VERSION.split(".")) >= (1, 6, 76)  # plancher
    assert VERSION_DATE >= "2026-11-22"
    assert len(_APP_VERSION_FILES) == 18
    for rel in _APP_VERSION_FILES:
        vals = re.findall(r'<span class="app-version">([^<]*)</span>', _read(rel))
        assert vals == [f"v{APP_VERSION}"], (rel, vals)


# ═══════════════════════════════════════════════════════
# T-K — lignes de balises des prompts (liées au code) inchangées
# ═══════════════════════════════════════════════════════

_TAG_LINES = {
    "loto": [
        "  tirages) qui ne proviennent pas d'un bloc [DONNÉES TEMPS RÉEL].",
        "- N'AFFICHE JAMAIS le tag [DONNÉES TEMPS RÉEL...] dans ta réponse.",
        "- Si un bloc [DONNÉES TEMPS RÉEL] global est présent à la place",
        "Quand un bloc [DONNÉES TEMPS RÉEL - Numéro X] est présent dans le message,",
        "[DONNÉES TEMPS RÉEL]",
        "entre crochets comme [DONNÉES TEMPS RÉEL], [RÉSULTAT TIRAGE],",
        '❌ "[DONNÉES TEMPS RÉEL] Fréquence : [F]"',
    ],
    "de": [
        "  Ziehungen), die nicht aus einem [DONNÉES TEMPS RÉEL]-Block stammen.",
        "- ZEIGE NIEMALS das Tag [DONNÉES TEMPS RÉEL...] in deiner Antwort.",
        "Wenn ein Block [DONNÉES TEMPS RÉEL - Numéro X] in der Nachricht vorhanden ist,",
        "[ECHTZEITDATEN]",
        "in eckigen Klammern wie [ECHTZEITDATEN], [ZIEHUNGSERGEBNIS],",
        '❌ "[ECHTZEITDATEN] Häufigkeit: [F]"',
    ],
    "en": [
        "  draws) that don't come from a [DONNÉES TEMPS RÉEL] block.",
        "- NEVER DISPLAY the tag [DONNÉES TEMPS RÉEL...] in your response.",
        "When a block [DONNÉES TEMPS RÉEL - Numéro X] is present in the message,",
        "[REAL-TIME DATA]",
        "in brackets like [REAL-TIME DATA], [DRAW RESULT],",
        '❌ "[REAL-TIME DATA] Frequency: [F]"',
    ],
    "es": [
        "  sorteos) que no provengan de un bloque [DONNÉES TEMPS RÉEL].",
        "- NUNCA MUESTRES la etiqueta [DONNÉES TEMPS RÉEL...] en tu respuesta.",
        "Cuando un bloque [DONNÉES TEMPS RÉEL - Numéro X] está presente en el mensaje,",
        "[DATOS EN TIEMPO REAL]",
        "entre corchetes como [DATOS EN TIEMPO REAL], [RESULTADO DEL SORTEO],",
        '❌ "[DATOS EN TIEMPO REAL] Frecuencia: [F]"',
    ],
    "fr": [
        "  tirages) qui ne proviennent pas d'un bloc [DONNÉES TEMPS RÉEL].",
        "- N'AFFICHE JAMAIS le tag [DONNÉES TEMPS RÉEL...] dans ta réponse.",
        "- Si un bloc [DONNÉES TEMPS RÉEL] global est présent à la place",
        "Quand un bloc [DONNÉES TEMPS RÉEL - Numéro X] est présent dans le message,",
        "[DONNÉES TEMPS RÉEL]",
        "entre crochets comme [DONNÉES TEMPS RÉEL], [RÉSULTAT TIRAGE],",
        '❌ "[DONNÉES TEMPS RÉEL] Fréquence : [F]"',
    ],
    "nl": [
        "  trekkingen) die niet uit een [DONNÉES TEMPS RÉEL]-blok komen.",
        "- TOON NOOIT de tag [DONNÉES TEMPS RÉEL...] in je antwoord.",
        "Wanneer een blok [DONNÉES TEMPS RÉEL - Numéro X] aanwezig is in het bericht,",
        "[REALTIMEGEGEVENS]",
        "tussen vierkante haken zoals [REALTIMEGEGEVENS], [TREKKINGSRESULTAAT],",
        '❌ "[REALTIMEGEGEVENS] Frequentie: [F]"',
    ],
    "pt": [
        "  sorteios) que não provenham de um bloco [DONNÉES TEMPS RÉEL].",
        "- NUNCA MOSTRES a etiqueta [DONNÉES TEMPS RÉEL...] na tua resposta.",
        "Quando um bloco [DONNÉES TEMPS RÉEL - Numéro X] está presente na mensagem,",
        "[DADOS EM TEMPO REAL]",
        "entre parênteses retos como [DONNÉES TEMPS RÉEL], [RÉSULTAT TIRAGE],",
        '❌ "[DONNÉES TEMPS RÉEL] Frequência: [F]"',
    ],
}


@pytest.mark.parametrize("key", sorted(PROMPTS))
def test_tk_tag_lines_unchanged(key):
    lines = _read(PROMPTS[key]).splitlines()
    for tag_line in _TAG_LINES[key]:
        assert lines.count(tag_line) == 1, (key, tag_line)
