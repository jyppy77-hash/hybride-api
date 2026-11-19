"""
Tests — Lot 1.6.073 (18/11/2026) : fix chatbot, routage des questions sur un numéro
(audit étoiles / numéros du 18/11, causes CE-1, CE-2, CE-6).

T1  Matrice de routage : les 28 formulations de l'audit, pipeline RÉEL (`_prepare_chat_context*`),
    détecteurs réels ; seules la base et Gemini sont mockés (modèle : tests/test_lot_phase_p.py:109-187).
T2  Cas limites de la garde (mot « prochain », dernier tirage sans numéro, date masquée).
T2b Fonction pure `_number_question_guard` (critères a / b) + journal de neutralisation.
T3  Libellé du bloc [PROCHAIN TIRAGE] Loto + EM (base mockée).
T4  Règle « numéro sans données » : une fois, et une seule, dans chacun des 7 prompts chatbot ;
    chaîne épinglée par langue ; zéro mot FR dans la règle des prompts non FR.
T5  Version 1.6.073 / VERSION_DATE 2026-11-18 (config + /api/version).

Aucun accès base, réseau ou Gemini (garde autouse tests/conftest.py:450-468).
"""

import contextlib
import logging
import os
import re
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════
# Harnais pipeline (base et Gemini mockés, détecteurs réels)
# ═══════════════════════════════════════════════════════

def _stats(numero, type_num=None):
    return {"numero": numero, "type": type_num or "boule", "frequence_totale": 62, "total_tirages": 732,
            "pourcentage_apparition": "8.47%", "derniere_sortie": "2026-09-29", "ecart_actuel": 14,
            "ecart_moyen": 11.7, "classement": 30, "classement_sur": 50, "categorie": "neutre",
            "periode": "2019-11-15 au 2026-11-17"}


def _tirage(game):
    async def _f(target):
        d = target if isinstance(target, date) else date(2026, 11, 17)
        base = {"date": d, "boules": [3, 12, 14, 17, 37]}
        return {**base, "chance": 7} if game == "loto" else {**base, "etoiles": [3, 12]}
    return _f


async def _run(game, msg, lang="fr"):
    """Retourne (meta, mocks) pour un tour unique, historique vide."""
    mod = "services.chat_pipeline" if game == "loto" else "services.chat_pipeline_em"
    names = ({"prochain": "_get_prochain_tirage", "tirage": "_get_tirage_data", "sql": "_generate_sql",
              "prompt": "load_prompt"} if game == "loto" else
             {"prochain": "_get_prochain_tirage_em", "tirage": "_get_tirage_data_em", "sql": "_generate_sql_em",
              "prompt": "load_prompt_em"})
    with contextlib.ExitStack() as st:
        st.enter_context(patch("services.chat_pipeline._get_draw_count", new_callable=AsyncMock, return_value=1000))
        st.enter_context(patch(f"{mod}.{names['prompt']}", return_value="sys"))
        prochain = st.enter_context(patch(
            f"{mod}.{names['prochain']}", new_callable=AsyncMock,
            return_value="[PROCHAIN TIRAGE]\nDate du prochain tirage : (mock)"))
        tirage = st.enter_context(patch(f"{mod}.{names['tirage']}", side_effect=_tirage(game)))
        stats = st.enter_context(patch(f"{mod}.get_numero_stats", new_callable=AsyncMock, side_effect=_stats))
        gen_sql = st.enter_context(patch(f"{mod}.{names['sql']}", new_callable=AsyncMock, return_value="NO_SQL"))
        for fn in ("analyze_grille_for_chat", "get_classement_numeros", "get_comparaison_numeros",
                   "get_comparaison_with_period", "get_numeros_par_categorie", "get_pair_correlations",
                   "get_triplet_correlations", "get_single_pair", "get_grid_numbers_stats"):
            st.enter_context(patch(f"{mod}.{fn}", new_callable=AsyncMock, return_value=None))
        if game == "loto":
            from services.chat_pipeline import _prepare_chat_context as prep
            early, ctx = await prep(msg, [], "loto", MagicMock(), lang=lang)
        else:
            from services.chat_pipeline_em import _prepare_chat_context_em as prep
            early, ctx = await prep(msg, [], "euromillions", MagicMock(), lang=lang)
    assert early is None, f"court-circuit inattendu : {early}"
    return ctx["_chat_meta"], {"prochain": prochain, "tirage": tirage, "stats": stats, "sql": gen_sql}


# ═══════════════════════════════════════════════════════
# T1 — matrice de routage (28 formulations)
# ═══════════════════════════════════════════════════════
# (n°, jeu, langue, formulation, phase attendue, appel get_numero_stats attendu | None, SQL tenté)

MATRIX = [
    (1, "loto", "fr", "Quels numéros sont sortis au tirage du Loto du 26 octobre 2022 ?", "T", None, False),
    (2, "em", "fr", "Quand le numéro 4 est-il sorti pour la dernière fois à l'EuroMillions ?", "1", (4, "boule"), False),
    (3, "em", "en", "How many times was number 19 drawn in 2025?", "SQL", None, True),
    (4, "em", "es", "¿Qué números salieron en el sorteo del 20 de diciembre de 2022?", "T", None, False),
    (5, "em", "pt", "Quando foi a última vez que o número 17 saiu no Euromilhões?", "1", (17, "boule"),
     False),  # 1.6.074 CF-4
    (6, "em", "de", "Wie oft wurde die Zahl 44 im Jahr 2025 gezogen?", "SQL", None, True),
    (7, "em", "nl", "Welke nummers zijn er getrokken bij de trekking van 14 september 2021?", "T", None, False),
    (8, "loto", "fr", "Quand le numéro 7 est-il sorti pour la dernière fois au Loto ?", "1", (7, "principal"), False),
    (9, "loto", "fr", "Quand le numéro 2 est-il sorti pour la dernière fois au Loto ?", "1", (2, "principal"), False),
    (10, "em", "fr", "Quand le numéro 4 est-il sorti pour la dernière fois ?", "1", (4, "boule"), False),
    (11, "em", "fr", "Dernière sortie du numéro 4", "1", (4, "boule"), False),
    (12, "em", "fr", "Quand est sortie l'étoile 4 pour la dernière fois à l'EuroMillions ?", "1", (4, "etoile"),
     False),
    (13, "em", "fr", "Dernière sortie de l'étoile 4", "1", (4, "etoile"), False),
    (14, "em", "fr", "Date de la dernière sortie du 4 au tirage EuroMillions", "1", (4, "boule"), False),
    (15, "em", "en", "When was number 4 last drawn?", "1", (4, "boule"), False),  # 1.6.074 CF-4
    (16, "em", "en", "When was number 4 last drawn in EuroMillions?", "1", (4, "boule"), False),  # 1.6.074 CF-4
    (17, "em", "es", "¿Cuándo salió por última vez el número 4 en el EuroMillones?", "1", (4, "boule"),
     False),  # 1.6.074 CF-4
    (18, "em", "pt", "Quando saiu pela última vez a estrela 4?", "1", (4, "etoile"), False),
    (19, "em", "de", "Wann wurde die Zahl 4 zuletzt bei EuroMillions gezogen?", "1", (4, "boule"),
     False),  # 1.6.074 CF-4
    (20, "em", "nl", "Wanneer is nummer 4 voor het laatst getrokken bij EuroMillions?", "1", (4, "boule"),
     False),  # 1.6.074 CF-4
    (21, "loto", "fr", "Quand est sorti le numéro chance 4 pour la dernière fois au Loto ?", "1", (4, "chance"),
     False),
    (22, "loto", "fr", "Dernière sortie du numéro chance 4", "1", (4, "chance"), False),
    (23, "loto", "fr", "Quand le numéro 4 est-il sorti pour la dernière fois ?", "1", (4, "principal"), False),
    (24, "em", "fr", "C'est quand le prochain tirage EuroMillions ?", "0-bis", None, False),
    (25, "em", "fr", "Quand a lieu le prochain tirage ?", "0-bis", None, False),
    (26, "em", "en", "When is the next EuroMillions draw?", "0-bis", None, False),  # 1.6.074 CF-5
    (27, "loto", "fr", "C'est quand le prochain tirage du Loto ?", "0-bis", None, False),
    (28, "em", "fr", "Quel est le dernier tirage ?", "T", None, False),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("n,game,lang,msg,phase,stats_args,sql", MATRIX, ids=[f"q{m[0]}" for m in MATRIX])
async def test_t1_routing_matrix(n, game, lang, msg, phase, stats_args, sql):
    meta, mocks = await _run(game, msg, lang)
    enrich = meta["enrichment_context"] or ""
    assert meta["phase"] == phase, f"#{n} : phase {meta['phase']!r} au lieu de {phase!r}"
    if stats_args is None:
        mocks["stats"].assert_not_called()
        assert "[DONNÉES TEMPS RÉEL" not in enrich
    else:
        mocks["stats"].assert_awaited_once_with(*stats_args)
        assert "[DONNÉES TEMPS RÉEL" in enrich, f"#{n} : données du numéro absentes du contexte"
        assert "[PROCHAIN TIRAGE" not in enrich
    assert (mocks["sql"].await_count > 0) is sql, f"#{n} : SQL tenté = {mocks['sql'].await_count > 0}"
    if phase == "0-bis":
        assert enrich.startswith("[PROCHAIN TIRAGE]")


# ═══════════════════════════════════════════════════════
# T2 — cas limites de la garde
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_t2_i_next_word_keeps_0bis_even_with_number():
    meta, mocks = await _run("em", "C'est quand le prochain tirage ? Le 7 a des chances ?")
    assert meta["phase"] == "0-bis"
    mocks["stats"].assert_not_called()
    mocks["prochain"].assert_awaited_once()


@pytest.mark.asyncio
async def test_t2_ii_latest_without_number_keeps_t():
    meta, mocks = await _run("em", "Quels numéros sont sortis au dernier tirage ?")
    assert meta["phase"] == "T"
    mocks["tirage"].assert_called_once_with("latest")
    mocks["stats"].assert_not_called()


@pytest.mark.asyncio
async def test_t2_iii_dated_target_never_guarded():
    meta, mocks = await _run("em", "Le tirage du 13 octobre 2026, quels numéros ?")
    assert meta["phase"] == "T"
    mocks["tirage"].assert_called_once_with(date(2026, 10, 13))
    mocks["stats"].assert_not_called()


@pytest.mark.asyncio
async def test_t2_iv_latest_draw_keyword_keeps_t():
    meta, mocks = await _run("em", "Dernier tirage EuroMillions ?")
    assert meta["phase"] == "T"
    mocks["tirage"].assert_called_once_with("latest")


@pytest.mark.asyncio
async def test_t2_guard_logs_neutralisation(caplog):
    with caplog.at_level(logging.INFO):
        await _run("em", "Quand le numéro 4 est-il sorti pour la dernière fois à l'EuroMillions ?")
        await _run("em", "When was 4 last drawn?", lang="en")  # 1.6.074 : sans « number » → critère b
    text = caplog.text
    assert "Lot 1.6.073 garde numero : Phase 0-bis neutralisee (critere a)" in text
    assert "Lot 1.6.073 garde numero : Phase T latest neutralisee (critere b)" in text
    caplog.clear()
    with caplog.at_level(logging.INFO):
        await _run("em", "When was number 4 last drawn?", lang="en")  # 1.6.074 CF-4 : « number 4 » → critère a
    assert "Lot 1.6.073 garde numero : Phase T latest neutralisee (critere a)" in caplog.text


# ── T2b — fonction pure ──────────────────────────────────────────────────

def _none(_msg):
    return None, None


@pytest.mark.parametrize("msg", [
    "When was number 4 last drawn?",
    "When did 12 come out last time?",
    "¿Cuándo salió el 4?",
    "Quando saiu o 9?",
    "Wann wurde die 44 zuletzt gezogen?",
    "Wanneer is 4 voor het laatst getrokken?",
    "le 4 est sorti quand ?",
])
def test_t2b_guard_criterion_b_six_langs(msg):
    from services.chat_pipeline_shared import _number_question_guard
    assert _number_question_guard(msg, _none) == "b"


@pytest.mark.parametrize("msg", [
    "Quels numéros sont sortis au dernier tirage ?",          # pas de nombre
    "Les numéros sortis le 13/10/2026 ?",                      # nombre = date masquée
    "Quels numéros sont sortis le 26 octobre 2022 ?",          # idem, date textuelle
    "When was the last draw?",                                 # pas de mot de sortie ni de nombre
    "Combien de tirages en 2025 ?",                            # année : pas un nombre 1-50
    "Quel est le dernier tirage ?",
])
def test_t2b_guard_negative(msg):
    from services.chat_pipeline_shared import _number_question_guard
    assert _number_question_guard(msg, _none) is None


def test_t2b_guard_criterion_a_uses_detect_numero():
    from services.chat_pipeline_shared import _number_question_guard
    assert _number_question_guard("n'importe quoi", lambda m: (4, "boule")) == "a"


def test_t2b_guard_detector_failure_falls_back_to_b():
    from services.chat_pipeline_shared import _number_question_guard

    def _boom(_m):
        raise RuntimeError("détecteur")
    assert _number_question_guard("When was number 4 last drawn?", _boom) == "b"
    assert _number_question_guard("Quel est le dernier tirage ?", _boom) is None


# ═══════════════════════════════════════════════════════
# T3 — libellé du bloc [PROCHAIN TIRAGE] (base mockée)
# ═══════════════════════════════════════════════════════

_NEW_LABEL = ("Date du dernier tirage enregistré (tirage le plus récent, tous numéros confondus — "
              "ce n'est PAS la dernière sortie d'un numéro) : 2026-11-16")


def _readonly_cm(last):
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value={"last": last})
    conn = AsyncMock()
    conn.cursor = AsyncMock(return_value=cursor)

    @contextlib.asynccontextmanager
    async def _cm():
        yield conn
    return _cm


@pytest.mark.asyncio
@pytest.mark.parametrize("game", ["loto", "em"])
async def test_t3_prochain_tirage_label(game):
    if game == "loto":
        from services.chat_sql import _get_prochain_tirage as fn
    else:
        from services.chat_sql_em import _get_prochain_tirage_em as fn
    with patch("db_cloudsql.get_connection_readonly", _readonly_cm(date(2026, 11, 16))):
        bloc = await fn()
    assert bloc.startswith("[PROCHAIN TIRAGE]")
    assert _NEW_LABEL in bloc
    assert "Dernier tirage en base" not in bloc


def test_t3_old_label_gone_from_sources():
    for rel in ("services/chat_sql.py", "services/chat_sql_em.py"):
        with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
            src = fh.read()
        assert "Dernier tirage en base" not in src, rel


# ═══════════════════════════════════════════════════════
# T4 — règle « numéro sans données » dans les 7 prompts chatbot
# ═══════════════════════════════════════════════════════

_RULES = {
    "loto_fr": ("prompts/chatbot/prompt_hybride.txt",
                "- RÈGLE NUMÉRO SANS DONNÉES (CRITIQUE) : si la question porte sur un numéro ou un numéro Chance "
                "précis, et que le contexte ne contient AUCUN bloc de statistiques pour CE numéro, "
                "n'invente AUCUN chiffre : ni fréquence, ni écart, ni date de dernière sortie, ni rang, ni "
                "catégorie. Un bloc [PROCHAIN TIRAGE] ou un bloc de tirage ne contient PAS les statistiques d'un "
                "numéro. Dans ce cas, dis simplement que tu n'as pas cette statistique sous la main et invite "
                "l'utilisateur à consulter la page Statistiques."),
    "em_fr": ("prompts/em/fr/prompt_hybride_em.txt",
              "- RÈGLE NUMÉRO SANS DONNÉES (CRITIQUE) : si la question porte sur un numéro ou une étoile "
              "précis, et que le contexte ne contient AUCUN bloc de statistiques pour CE numéro, "
              "n'invente AUCUN chiffre : ni fréquence, ni écart, ni date de dernière sortie, ni rang, ni "
              "catégorie. Un bloc [PROCHAIN TIRAGE] ou un bloc de tirage ne contient PAS les statistiques d'un "
              "numéro. Dans ce cas, dis simplement que tu n'as pas cette statistique sous la main et invite "
              "l'utilisateur à consulter la page Statistiques."),
    "em_en": ("prompts/em/en/prompt_hybride_em.txt",
              "- NUMBER WITHOUT DATA RULE (CRITICAL): if the question is about a specific number or star, "
              "and the context contains NO statistics block for THAT number, do NOT make up ANY figure: "
              "no frequency, no gap, no last appearance date, no rank, no category. A [PROCHAIN TIRAGE] block or "
              "a draw block does NOT contain a number's statistics. In that case, simply say that you don't have "
              "that statistic at hand and invite the user to check the Statistics page."),
    "em_es": ("prompts/em/es/prompt_hybride_em.txt",
              "- REGLA NÚMERO SIN DATOS (CRÍTICA): si la pregunta trata sobre un número o una estrella "
              "concretos, y el contexto NO contiene NINGÚN bloque de estadísticas para ESE número, no "
              "inventes NINGUNA cifra: ni frecuencia, ni desviación, ni fecha de última aparición, ni posición, ni "
              "categoría. Un bloque [PROCHAIN TIRAGE] o un bloque de sorteo NO contiene las estadísticas de un "
              "número. En ese caso, di simplemente que no tienes esa estadística a mano e invita al usuario a "
              "consultar la página de Estadísticas."),
    "em_pt": ("prompts/em/pt/prompt_hybride_em.txt",
              "- REGRA NÚMERO SEM DADOS (CRÍTICA): se a pergunta for sobre um número ou uma estrela "
              "específicos, e o contexto NÃO contiver NENHUM bloco de estatísticas para ESSE número, não "
              "inventes NENHUM valor: nem frequência, nem desvio, nem data da última aparição, nem posição, nem "
              "categoria. Um bloco [PROCHAIN TIRAGE] ou um bloco de sorteio NÃO contém as estatísticas de um "
              "número. Nesse caso, diz simplesmente que não tens essa estatística à mão e convida o utilizador a "
              "consultar a página de Estatísticas."),
    "em_de": ("prompts/em/de/prompt_hybride_em.txt",
              "- REGEL ZAHL OHNE DATEN (KRITISCH): Wenn sich die Frage auf eine bestimmte Zahl oder einen "
              "bestimmten Stern bezieht und der Kontext KEINEN Statistik-Block für GENAU DIESE Zahl enthält, "
              "erfinde KEINEN Wert: weder Häufigkeit noch Abstand, noch Datum des letzten Auftretens, noch Rang, "
              "noch Kategorie. Ein [PROCHAIN TIRAGE]-Block oder ein Ziehungsblock enthält NICHT die Statistiken "
              "einer Zahl. Sag in diesem Fall einfach, dass du diese Statistik nicht zur Hand hast, und lade den "
              "Nutzer ein, die Statistik-Seite zu besuchen."),
    "em_nl": ("prompts/em/nl/prompt_hybride_em.txt",
              "- REGEL NUMMER ZONDER GEGEVENS (KRITIEK): als de vraag over een specifiek nummer of een specifieke "
              "ster gaat en de context GEEN ENKEL statistiekenblok voor DAT nummer bevat, verzin dan "
              "GEEN ENKEL cijfer: geen frequentie, geen tussenpoze, geen datum van laatste verschijning, geen "
              "rang, geen categorie. Een [PROCHAIN TIRAGE]-blok of een trekkingsblok bevat NIET de statistieken "
              "van een nummer. Zeg in dat geval gewoon dat je die statistiek niet bij de hand hebt en nodig de "
              "gebruiker uit om de Statistiekenpagina te bekijken."),
}

# Marqueur de tête par langue (une occurrence exacte attendue)
_HEADS = {"loto_fr": "RÈGLE NUMÉRO SANS DONNÉES", "em_fr": "RÈGLE NUMÉRO SANS DONNÉES",
          "em_en": "NUMBER WITHOUT DATA RULE", "em_es": "REGLA NÚMERO SIN DATOS",
          "em_pt": "REGRA NÚMERO SEM DADOS", "em_de": "REGEL ZAHL OHNE DATEN",
          "em_nl": "REGEL NUMMER ZONDER GEGEVENS"}
# Mots FR proscrits dans la règle des prompts non FR (le tag interne [PROCHAIN TIRAGE] est retiré avant)
_FR_WORDS = re.compile(r"\b(?:numéro|étoile|règle|statistiques|n'invente|dernière|sortie|écart|chiffre|"
                       r"utilisateur|bloc|tirage|aucun|précis)\b", re.IGNORECASE)


def _read(rel):
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


@pytest.mark.parametrize("key", sorted(_RULES))
def test_t4_rule_present_once(key):
    rel, rule = _RULES[key]
    src = _read(rel)
    assert src.count(_HEADS[key]) == 1, f"{rel} : tête de règle absente ou dupliquée"
    assert src.count(rule) == 1, f"{rel} : règle épinglée absente ou modifiée"


@pytest.mark.parametrize("key", sorted(_RULES))
def test_t4_rule_follows_existing_fallback(key):
    rel, rule = _RULES[key]
    lines = _read(rel).splitlines()
    idx = lines.index(rule)
    prev = lines[idx - 1]
    assert prev.rstrip().endswith('!"'), f"{rel} : la règle ne suit pas la consigne de repli ({prev!r})"


@pytest.mark.parametrize("key", [k for k in sorted(_RULES) if not k.endswith("_fr")])
def test_t4_zero_fr_string_in_non_fr_rule(key):
    rule = _RULES[key][1].replace("[PROCHAIN TIRAGE]", "")
    hit = _FR_WORDS.search(rule)
    assert hit is None, f"{key} : mot FR « {hit.group(0)} » dans la règle"


def test_t4_all_prompts_mention_real_tag():
    for key, (rel, rule) in _RULES.items():
        assert "[PROCHAIN TIRAGE]" in rule, key
    # tag réellement posé par le pipeline (services/chat_sql.py, services/chat_sql_em.py)
    assert '"[PROCHAIN TIRAGE]"' in _read("services/chat_sql_em.py")


@pytest.mark.parametrize("key", sorted(_RULES))
def test_t4_rule_matches_game(key):
    """Décision 7 (phase B) : Loto = numéro / numéro Chance, jamais d'étoile ; EM = numéro / étoile, jamais de Chance."""
    rule = _RULES[key][1]
    if key.startswith("loto"):
        assert "Chance" in rule and "étoile" not in rule.lower()
    else:
        assert "chance" not in rule.lower(), f"{key} : mention du Chance dans un prompt EM"


# ═══════════════════════════════════════════════════════
# T5 — version
# ═══════════════════════════════════════════════════════

def test_t5_version_config():
    from config.version import APP_VERSION, VERSION_DATE
    assert tuple(int(p) for p in APP_VERSION.split(".")) >= (1, 6, 73)  # plancher (lot 1.6.074)
    assert VERSION_DATE >= "2026-11-18"


def test_t5_api_version():
    env = patch.dict(os.environ, {"DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
                                  "EM_PUBLIC_ACCESS": "true"})
    with env, patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None), \
         patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None):
        import importlib
        import rate_limit as rl_mod
        importlib.reload(rl_mod)
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        rl_mod.limiter.reset()
        resp = TestClient(main_mod.app, raise_server_exceptions=False).get("/api/version")
    assert resp.status_code == 200
    body = resp.json()
    assert tuple(int(p) for p in body["version"].split(".")) >= (1, 6, 73)  # plancher (lot 1.6.074)
    assert body["date"] >= "2026-11-18"
