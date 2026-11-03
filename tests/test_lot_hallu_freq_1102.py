"""
Tests — Lot 1.6.065 « hallucination fréquences / grilles inventées » (incident 02/11/2026, chat_log 9401-9405).

- D1  « encore une grille », « une autre »… après un tour de génération → Phase G (6 langues)
- D2  question d'avis sans numéros après une grille → EVAL_H (6 langues) ; apostrophe U+2019
- D3  _detect_grille_em : « / » et message purement numérique (7398, 7400) ; Loto déjà couvert (7330)
- A   bloc [STATS PAR NUMÉRO] (une requête, définition chaud / froid de [ANALYSE DE GRILLE]),
      toutes les égalités de meilleure correspondance, priorité de la source de la grille
- C   contrôle 4 (journal seul par défaut, bloquant avec STRICT_STAT_CHECK) + faux positifs
- E   7 prompts chargés sans exemples chiffrés concrets, consignes conditionnelles
- Annexe ORPHAN_STAT_SINGLE « Fréquence observée 125 »
- R3  non-régressions : 8300, V125 « Oui », paire 22 + 10, 8011

Base entièrement mockée, Gemini simulé : aucun accès DB ni réseau.
"""

import contextlib
import logging
import re
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from schemas import ChatMessage
from services.base_chat_detect_generation import _detect_generation, _detect_generation_followup
from services.base_chat_detect_intent import (
    _detect_grid_evaluation, _detect_opinion_followup, _is_affirmation_simple, _is_refusal,
    _is_short_continuation,
)
from services.base_chat_utils import (
    _INTERNAL_TAGS_PATTERNS, _clean_response, _extract_grids_from_text, _format_grille_context_base,
    _format_numbers_stats_context_base,
)
from services.base_stats import _tercile_category, _tercile_thresholds
from services.chat_detectors import _detect_grille
from services.chat_detectors_em_intent import _detect_grille_em
from services.chat_pipeline_gemini import (
    _FACTUAL_TAGS, _ORPHAN_STAT_FREQ_FIRST_RE, _ORPHAN_STAT_RE, _STRICT_BLOCK_FALLBACK_I18N,
    _get_temperature, stream_and_respond,
)
from services.chat_stat_check import ENGINE_SCORES, check_number_stats

ROOT = Path(__file__).resolve().parent.parent
LANGS = ["fr", "en", "es", "pt", "de", "nl"]


def _h(*pairs):
    """Historique ChatMessage à partir de (role, content)."""
    return [ChatMessage(role=r, content=c) for r, c in pairs]


# ── Textes terrain (chat_log 9401-9405, aperçus) ─────────────────────────────
T9401 = ("Alors, pour ce soir, voici une grille que le moteur HYBRIDE t'a concoctée : "
         "6 - 12 - 29 - 38 - 46 et le Numéro Chance 7 !\n\nElle a un score de conformité de 75/100.")
T9403 = ("Grille n°4\nNuméros principaux : 2 - 14 - 27 - 35 - 41\nNuméro Chance : 8\n"
         "Score de conformité : 82/100\nBadges : Hybride V1, Numéros chauds, Équilibre, Pair/Impair OK, "
         "Large spectre, Mix de retards")
T9404 = ("Ta combinaison 2 - 14 - 27 - 35 - 41 avec le Numéro Chance 8 est super équilibrée ! Elle a une "
         "somme de 119, 2 pairs et 3 impairs, et une belle dispersion de 39. Elle n'est jamais sortie dans "
         "l'historique, mais a déjà eu 3 numéros en commun avec le tirage du 16 août 2023.")
T9405 = """Grille : 2-14-27-35-41 Chance 8
Score de conformité : 82/100
Badges : Hybride V1, Numéros chauds, Équilibre, Pair/Impair OK, Large spectre, Mix de retards
Historique : Cette combinaison n'est jamais apparue dans l'historique des tirages du Loto FDJ.
Meilleure correspondance : 3 numéros identiques (2-14-35) le 16 août 2023.
Analyse des numéros :
- Numéro 2 : Fréquence observée 125, retard 1, chaud.
- Numéro 14 : Fréquence observée 105, retard 2, chaud.
- Numéro 27 : Fréquence observée 109, retard 3, neutre."""
T7318 = "[NUMÉROS PRINCIPAUX] - Numéro 1: 17 (Fréquence observée: 108, Retard actuel: 2, Catégorie: Neutre)"

HISTORY_9405 = _h(
    ("user", "Fais moi une grille loto ce soir"), ("assistant", T9401),
    ("user", "Encore mieux"), ("assistant", "Grille n°2\nNuméros principaux : 1 - 15 - 28 - 33 - 42\n"
                                            "Numéro Chance : 3\nScore de conformité : 88/100"),
    ("user", "Encore une grille"), ("assistant", T9403),
    ("user", "2 14 27 35 41 chance 8"), ("assistant", T9404),
)

STATS_9405 = {
    "total_tirages": 1094, "date_min": "2019-11-06", "date_max": "2026-10-31",
    "principaux": [
        {"numero": 2, "frequence": 100, "ecart_actuel": 2, "derniere_sortie": "2026-10-26", "rang": 43,
         "rang_sur": 49, "categorie": "froid"},
        {"numero": 14, "frequence": 99, "ecart_actuel": 1, "derniere_sortie": "2026-10-28", "rang": 45,
         "rang_sur": 49, "categorie": "froid"},
        {"numero": 27, "frequence": 103, "ecart_actuel": 40, "derniere_sortie": "2026-07-29", "rang": 40,
         "rang_sur": 49, "categorie": "froid"},
        {"numero": 35, "frequence": 114, "ecart_actuel": 8, "derniere_sortie": "2026-10-12", "rang": 17,
         "rang_sur": 49, "categorie": "chaud"},
        {"numero": 41, "frequence": 115, "ecart_actuel": 38, "derniere_sortie": "2026-08-03", "rang": 15,
         "rang_sur": 49, "categorie": "chaud"},
    ],
    "secondaires": [
        {"numero": 8, "frequence": 105, "ecart_actuel": 10, "derniere_sortie": "2026-10-07", "rang": 9,
         "rang_sur": 10, "categorie": "froid"},
    ],
}
ANALYSIS_9405 = {
    "numeros": [2, 14, 27, 35, 41], "chance": 8, "total_tirages": 1094,
    "analyse": {"somme": 119, "somme_ok": True, "pairs": 2, "impairs": 3, "equilibre_pair_impair": True,
                "bas": 2, "hauts": 3, "equilibre_bas_haut": True, "dispersion": 39, "dispersion_ok": True,
                "consecutifs": 0, "numeros_chauds": [35, 41], "numeros_froids": [2, 14, 27],
                "numeros_neutres": [], "conformite_pct": 98,
                "badges": ["Équilibre", "Large spectre", "Pair/Impair OK"]},
    "historique": {"deja_sortie": False, "exact_dates": [], "meilleure_correspondance": {
        "nb_numeros_communs": 3, "date": "2023-08-16", "numeros_communs": [27, 35, 41], "chance_match": False,
        "egalites": [
            {"date": "2023-08-16", "numeros_communs": [27, 35, 41], "chance_match": False},
            {"date": "2022-01-10", "numeros_communs": [14, 35, 41], "chance_match": False},
            {"date": "2021-10-18", "numeros_communs": [27, 35, 41], "chance_match": False},
            {"date": "2021-03-31", "numeros_communs": [2, 27, 35], "chance_match": False},
        ], "nb_egalites": 4}},
}


def _ctx_9405():
    grille = _format_grille_context_base(
        ANALYSIS_9405, secondary_key="chance", secondary_label="chance", sum_range="93-157",
        low_threshold=24, high_label="25-49", match_key="chance_match", match_label=" + chance")
    return grille + "\n\n" + _format_numbers_stats_context_base(STATS_9405, "Chance")


# ═══════════════════════════════════════════════════════
# D1 — génération de suite
# ═══════════════════════════════════════════════════════

FOLLOWUPS = {
    "fr": ["Encore une grille", "Encore mieux", "Une autre", "Une autre grille", "Encore une", "Refais-en une",
           "Une de plus", "Encore", "Encore 3 grilles", "une autre grille svp"],
    "en": ["Another grid", "Another one", "One more", "Again", "Even better"],
    "es": ["Otra combinación", "Otra", "Una más", "Otra vez"],
    "pt": ["Outra grelha", "Mais uma", "Outra"],
    "de": ["Noch eine Kombination", "Noch eine", "Nochmal"],
    "nl": ["Nog een combinatie", "Nog een", "Nog eens"],
}
GEN_HISTORY = _h(("user", "Fais moi une grille loto ce soir"), ("assistant", T9401))


class TestD1Followup:

    @pytest.mark.parametrize("msg", [m for v in FOLLOWUPS.values() for m in v])
    def test_generation_followup_after_engine_grid(self, msg):
        assert not _detect_generation(msg) or msg == "Encore 3 grilles"
        assert _detect_generation_followup(msg, GEN_HISTORY) == "Fais moi une grille loto ce soir"

    def test_generation_followup_chain_9402_9403(self):
        history = _h(("user", "Fais moi une grille loto ce soir"), ("assistant", T9401),
                     ("user", "Encore mieux"), ("assistant", "Grille n°2 : 1 - 15 - 28 - 33 - 42, chance 3"))
        assert _detect_generation_followup("Encore une grille", history) == "Fais moi une grille loto ce soir"

    def test_un_autre_after_number_stats_not_generation(self):
        """Cas 8300 : « Un autre » après la stat d'un numéro → pas de Phase G."""
        history = _h(("user", "stats du 7"), ("assistant", "Le 7 est sorti 120 fois, écart actuel 2."))
        assert _detect_generation_followup("Un autre", history) is None

    def test_followup_after_user_grid_analysis_not_generation(self):
        """La dernière grille vient de l'utilisateur, pas d'un tour de génération."""
        history = _h(("user", "2 14 27 35 41 chance 8"), ("assistant", T9404))
        assert _detect_generation_followup("Une autre", history) is None

    def test_followup_without_history(self):
        assert _detect_generation_followup("Encore une grille", []) is None

    @pytest.mark.parametrize("msg", ["Oui", "Encore une fois merci pour tout le travail", "une autre question"])
    def test_not_followup_text(self, msg):
        assert _detect_generation_followup(msg, GEN_HISTORY) is None

    @pytest.mark.asyncio
    async def test_followup_runs_phase_g_with_origin_mode_and_count(self):
        history = _h(("user", "génère 3 grilles en mode conservateur"),
                     ("assistant", "Grille 1/3 : 3 - 13 - 24 - 34 - 44 et le Numéro Chance 7, score 85/100"))
        gen = AsyncMock(return_value={"grids": [{"nums": [3, 13, 24, 34, 44], "chance": 7, "score": 85,
                                                  "badges": []}] * 3})
        with contextlib.ExitStack() as stack:
            _common_patches(stack)
            stack.enter_context(patch("engine.hybride.generate_grids", gen))
            from services.chat_pipeline import _prepare_chat_context
            _, ctx = await _prepare_chat_context("Encore", history, "loto", MagicMock(), lang="fr")
        assert ctx["_chat_meta"]["phase"] == "G"
        kw = gen.await_args.kwargs
        assert kw["n"] == 3 and kw["mode"] == "conservative"


# ═══════════════════════════════════════════════════════
# D2 — question d'avis sans numéros
# ═══════════════════════════════════════════════════════

OPINIONS = {
    "fr": ["C'est bien ?", "C’est bien ?", "Elle est bien ?", "Elle est bonne ?", "Tu en penses quoi ?",
           "Qu'en penses-tu ?", "Qu’en penses-tu ?", "Analyse-la", "Détaille-la", "Et celle-là ?"],
    "en": ["Is it good?", "Is this good?", "Any good?", "Worth it?", "What do you think?", "Analyse it"],
    "es": ["¿Está bien?", "¿Es buena?", "¿Qué te parece?", "¿Vale la pena?", "Analízala"],
    "pt": ["Está bem?", "É boa?", "O que achas?", "Vale a pena?", "Analisa-a"],
    "de": ["Ist das gut?", "Ist sie gut?", "Was hältst du davon?", "Lohnt sich das?", "Analysiere sie"],
    "nl": ["Is het goed?", "Is die goed?", "Wat vind je ervan?", "Is het de moeite waard?", "Analyseer hem"],
}


class TestD2Opinion:

    @pytest.mark.parametrize("msg", [m for v in OPINIONS.values() for m in v])
    def test_opinion_followup_detected(self, msg):
        assert _detect_opinion_followup(msg)

    @pytest.mark.parametrize("msg", ["Bonjour", "C'est quoi le loto ?", "C'est bien le 22 ?", "Oui",
                                     "Elle est bien la grille 2 14 27 35 41 ?", "Merci beaucoup"])
    def test_opinion_followup_rejected(self, msg):
        assert not _detect_opinion_followup(msg)

    def test_typographic_apostrophe_g8_affirmation_refusal(self):
        assert _detect_grid_evaluation("qu’en penses-tu de 2 14 27 35 41 chance 8", "loto")
        assert _detect_grid_evaluation("c’est bien cette grille 2 14 27 35 41 ?", "loto")
        assert _is_affirmation_simple("d’accord")
        assert _is_affirmation_simple("c’est bon")
        assert _is_refusal("c’est bon")
        assert _is_refusal("non c’est bon")

    @pytest.mark.asyncio
    async def test_eval_h_replay_9405_user_grid_with_stats_block(self, caplog):
        """Rejeu 9405 : « C’est bien ? » → EVAL_H, grille du message utilisateur 9404, blocs A."""
        analyze = AsyncMock(return_value=ANALYSIS_9405)
        stats = AsyncMock(return_value=STATS_9405)
        with contextlib.ExitStack() as stack, caplog.at_level(logging.INFO):
            _common_patches(stack)
            stack.enter_context(patch("services.chat_pipeline.analyze_grille_for_chat", analyze))
            stack.enter_context(patch("services.chat_pipeline.get_grid_numbers_stats", stats))
            from services.chat_pipeline import _prepare_chat_context
            early, ctx = await _prepare_chat_context("C’est bien ?", HISTORY_9405, "loto", MagicMock(), lang="fr")
        assert early is None
        meta = ctx["_chat_meta"]
        assert meta["phase"] == "EVAL_H"
        assert analyze.await_args.args[:2] == ([2, 14, 27, 35, 41], 8)
        assert stats.await_args.args[:2] == ([2, 14, 27, 35, 41], 8)
        enr = meta["enrichment_context"]
        assert "[ANALYSE DE GRILLE - 2 14 27 35 41" in enr and "[STATS PAR NUMÉRO" in enr
        assert "Numéro 2 : 100 sorties" in enr and "Chance 8 : 105 sorties" in enr
        assert "le 2021-03-31 (2, 27, 35)" in enr
        assert "EVAL_FROM_HISTORY: source=user" in caplog.text

    @pytest.mark.asyncio
    async def test_opinion_without_grid_in_history_stays_gemini(self):
        with contextlib.ExitStack() as stack:
            _common_patches(stack)
            from services.chat_pipeline import _prepare_chat_context
            _, ctx = await _prepare_chat_context(
                "C’est bien ?", _h(("user", "bonjour"), ("assistant", "Salut !")), "loto", MagicMock(), lang="fr")
        assert ctx["_chat_meta"]["phase"] == "Gemini"

    @pytest.mark.asyncio
    async def test_ca_vaut_le_coup_stays_phase_A(self):
        """Décision Jyppy c : « ça vaut le coup ? » reste en Phase A, même après une grille."""
        with contextlib.ExitStack() as stack:
            _common_patches(stack)
            from services.chat_pipeline import _prepare_chat_context
            early, _ = await _prepare_chat_context("Ça vaut le coup ?", HISTORY_9405, "loto", MagicMock(), lang="fr")
        assert early is not None and early["_chat_meta"]["phase"] == "A"

    @pytest.mark.asyncio
    async def test_eval_h_em_from_engine_turn(self):
        history = _h(("user", "génère une grille euromillions"),
                     ("assistant", "Voici ta grille : 3 - 15 - 22 - 41 - 48 et les étoiles 2 et 9, score 85/100"))
        analyze = AsyncMock(return_value=None)
        with contextlib.ExitStack() as stack:
            _common_patches(stack, game="em")
            stack.enter_context(patch("services.chat_pipeline_em.analyze_grille_for_chat", analyze))
            from services.chat_pipeline_em import _prepare_chat_context_em
            _, ctx = await _prepare_chat_context_em("Is it good?", history, "euromillions", MagicMock(), lang="en")
        assert ctx["_chat_meta"]["phase"] == "EVAL_H"
        assert analyze.await_args.args[:2] == ([3, 15, 22, 41, 48], [2, 9])


# ═══════════════════════════════════════════════════════
# Source de la grille (point Claude n°2)
# ═══════════════════════════════════════════════════════

def _cfg(game="loto"):
    from services.chat_pipeline import _build_loto_config
    from services.chat_pipeline_em import _build_em_config
    return _build_loto_config() if game == "loto" else _build_em_config()


class TestGridSource:

    def test_grid_source_priority(self):
        from services.chat_pipeline_shared import _find_last_exchange_grid
        cfg = _cfg()
        # (2) message utilisateur du dernier échange
        r = _find_last_exchange_grid(_h(("user", "2 14 27 35 41 chance 8"), ("assistant", T9404)), cfg)
        assert r == {"numeros": [2, 14, 27, 35, 41], "secondary": 8, "source": "user"}
        # (3) tour de génération reconstruit, score possible du moteur
        r = _find_last_exchange_grid(GEN_HISTORY, cfg)
        assert r["source"] == "engine_turn" and r["numeros"] == [6, 12, 29, 38, 46] and r["secondary"] == 7
        # (4) texte libre du bot
        r = _find_last_exchange_grid(_h(("user", "salut"), ("assistant", "Tiens : 1 - 2 - 3 - 4 - 5, chance 6")), cfg)
        assert r["source"] == "bot_text"

    def test_invented_grid_in_bot_text_not_trusted(self):
        """9403 : tour « Encore une grille », score 82 impossible pour le moteur → « bot_text »."""
        from services.chat_pipeline_shared import _engine_turn_grids, _find_last_exchange_grid
        cfg = _cfg()
        history = _h(("user", "Fais moi une grille loto ce soir"), ("assistant", T9401),
                     ("user", "Encore une grille"), ("assistant", T9403))
        assert _find_last_exchange_grid(history, cfg)["source"] == "bot_text"
        assert 82 not in ENGINE_SCORES
        # le contrôle 4 n'accepte pas ce « rappel »
        f = check_number_stats(T9403, "", phase="Gemini", lang="fr", game="loto",
                               engine_turn_grids=_engine_turn_grids(history, cfg))
        assert any(x["check"] == "GRID_SCORE_ORPHAN" for x in f)

    def test_extract_grids_from_text_formats(self):
        assert _extract_grids_from_text("2-14-27-35-41 Chance 8") == [([2, 14, 27, 35, 41], 8)]
        assert _extract_grids_from_text(T9401) == [([6, 12, 29, 38, 46], 7)]
        assert _extract_grids_from_text("Numéros : [2, 14, 27, 35, 41]") == [([2, 14, 27, 35, 41], None)]
        assert _extract_grids_from_text("3 - 15 - 22 - 41 - 48 et les étoiles 2 et 9", game="em") == \
            [([3, 15, 22, 41, 48], [2, 9])]
        assert _extract_grids_from_text("sorti 104 fois sur 1094 tirages") == []


# ═══════════════════════════════════════════════════════
# A — blocs de données
# ═══════════════════════════════════════════════════════

class _Cursor:
    """Curseur simulé : renvoie les lots dans l'ordre et compte les requêtes."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.queries = []

    async def execute(self, sql, params=None):
        self.queries.append(sql)

    async def fetchall(self):
        return self.batches.pop(0)

    async def fetchone(self):
        return self.batches.pop(0)


@contextlib.asynccontextmanager
async def _conn(cursor):
    class _C:
        async def cursor(self):
            return cursor
    yield _C()


def _draw_rows():
    """3 tirages : 2 apparaît aux index 0 et 2, chance 8 à l'index 1."""
    from datetime import date
    return [
        {"date_de_tirage": date(2026, 10, 1), "boule_1": 2, "boule_2": 14, "boule_3": 27, "boule_4": 35,
         "boule_5": 41, "numero_chance": 3},
        {"date_de_tirage": date(2026, 10, 3), "boule_1": 5, "boule_2": 6, "boule_3": 7, "boule_4": 9,
         "boule_5": 10, "numero_chance": 8},
        {"date_de_tirage": date(2026, 10, 5), "boule_1": 2, "boule_2": 11, "boule_3": 12, "boule_4": 13,
         "boule_5": 15, "numero_chance": 1},
    ]


FREQ_MAIN = [{"num": n, "freq": 60 + n} for n in range(1, 50)]
FREQ_CHANCE = [{"num": n, "freq": 100 + n} for n in range(1, 11)]


class TestStatsBlock:

    @pytest.mark.asyncio
    async def test_numbers_stats_single_draw_query(self):
        from services.cache import cache_clear
        from services.stats_service import _svc
        await cache_clear()
        cur = _Cursor([FREQ_MAIN, FREQ_CHANCE, _draw_rows()])
        with patch.object(_svc, "_get_connection", lambda: _conn(cur)):
            s = await _svc.get_grid_numbers_stats([41, 2, 14, 27, 35], 8)
        assert sum("ORDER BY date_de_tirage ASC" in q for q in cur.queries) == 1
        assert [e["numero"] for e in s["principaux"]] == [2, 14, 27, 35, 41]
        two = s["principaux"][0]
        assert two["frequence"] == 62 and two["ecart_actuel"] == 0 and two["derniere_sortie"] == "2026-10-05"
        assert two["rang"] == 48 and two["rang_sur"] == 49
        chance = s["secondaires"][0]
        assert chance["numero"] == 8 and chance["ecart_actuel"] == 1 and chance["rang_sur"] == 10
        # cache chaud : une seule requête (la liste des tirages)
        cur2 = _Cursor([_draw_rows()])
        with patch.object(_svc, "_get_connection", lambda: _conn(cur2)):
            await _svc.get_grid_numbers_stats([2, 14, 27, 35, 41], 8)
        assert len(cur2.queries) == 1

    @pytest.mark.asyncio
    async def test_stars_stats_em(self):
        from services.cache import cache_clear
        from services.em_stats_service import _svc
        from datetime import date
        await cache_clear()
        rows = [{"date_de_tirage": date(2026, 10, 1), "boule_1": 3, "boule_2": 15, "boule_3": 22,
                 "boule_4": 41, "boule_5": 48, "etoile_1": 2, "etoile_2": 9}]
        cur = _Cursor([[{"num": n, "freq": 50 + n} for n in range(1, 51)],
                       [{"num": n, "freq": 80 + n} for n in range(1, 13)], rows])
        with patch.object(_svc, "_get_connection", lambda: _conn(cur)):
            s = await _svc.get_grid_numbers_stats([3, 15, 22, 41, 48], [9, 2])
        assert [e["numero"] for e in s["secondaires"]] == [2, 9]
        block = _format_numbers_stats_context_base(s, "Étoile")
        assert "Étoile 2 : 82 sorties" in block and "rang 11/12" in block

    def test_both_blocks_same_category_definition(self):
        """Décision a : [STATS PAR NUMÉRO] et [ANALYSE DE GRILLE] — mêmes terciles (historique entier)."""
        freq = {r["num"]: r["freq"] for r in FREQ_MAIN}
        chaud, froid = _tercile_thresholds(freq.values())
        for n in (1, 20, 49):
            in_hot = freq[n] >= chaud
            in_cold = freq[n] <= froid
            expected = "chaud" if in_hot else ("froid" if in_cold else "neutre")
            assert _tercile_category(freq[n], chaud, froid) == expected
        # le bloc nomme sa période et sa définition
        block = _format_numbers_stats_context_base(STATS_9405, "Chance")
        assert "ensemble de l'historique" in block and "même définition que [ANALYSE DE GRILLE]" in block
        assert "Numéros chauds (sur l'ensemble de l'historique) : 35, 41" in _ctx_9405()

    @pytest.mark.asyncio
    async def test_best_match_all_ties_listed(self):
        from services.cache import cache_clear
        from services.stats_service import _svc
        from datetime import date
        await cache_clear()
        best = {"date_de_tirage": date(2023, 8, 16), "boule_1": 24, "boule_2": 41, "boule_3": 19,
                "boule_4": 35, "boule_5": 27, "numero_chance": 9, "match_count": 3, "chance_match": 0}
        ties = [
            {"date_de_tirage": date(2023, 8, 16), "boule_1": 24, "boule_2": 41, "boule_3": 19, "boule_4": 35,
             "boule_5": 27, "numero_chance": 9},
            {"date_de_tirage": date(2022, 1, 10), "boule_1": 14, "boule_2": 43, "boule_3": 34, "boule_4": 41,
             "boule_5": 35, "numero_chance": 9},
            {"date_de_tirage": date(2021, 10, 18), "boule_1": 41, "boule_2": 27, "boule_3": 36, "boule_4": 35,
             "boule_5": 9, "numero_chance": 6},
            {"date_de_tirage": date(2021, 3, 31), "boule_1": 2, "boule_2": 27, "boule_3": 24, "boule_4": 35,
             "boule_5": 22, "numero_chance": 8},
        ]
        cur = _Cursor([{"total": 1094}, FREQ_MAIN, [], best, ties])
        with patch.object(_svc, "_get_connection", lambda: _conn(cur)):
            r = await _svc.analyze_grille_for_chat([2, 14, 27, 35, 41], 8)
        mc = r["historique"]["meilleure_correspondance"]
        assert mc["nb_egalites"] == 4 and len(mc["egalites"]) == 4
        assert mc["egalites"][3] == {"date": "2021-03-31", "numeros_communs": [2, 27, 35], "chance_match": True}
        from services.chat_utils import _format_grille_context
        txt = _format_grille_context(r)
        assert "Tirages à égalité (3 numéros communs) : 4 au total" in txt
        assert "le 2021-03-31 (2, 27, 35 + chance)" in txt

    @pytest.mark.asyncio
    async def test_ties_failure_keeps_analysis(self):
        """Une erreur sur la requête d'égalités n'invalide pas l'analyse (liste vide)."""
        from services.cache import cache_clear
        from services.stats_service import _svc
        from datetime import date
        await cache_clear()
        best = {"date_de_tirage": date(2023, 8, 16), "boule_1": 24, "boule_2": 41, "boule_3": 19,
                "boule_4": 35, "boule_5": 27, "numero_chance": 9, "match_count": 3, "chance_match": 0}
        cur = _Cursor([{"total": 1094}, FREQ_MAIN, [], best])  # pas de lot pour les égalités
        with patch.object(_svc, "_get_connection", lambda: _conn(cur)):
            r = await _svc.analyze_grille_for_chat([2, 14, 27, 35, 41], 8)
        assert r is not None and r["historique"]["meilleure_correspondance"]["egalites"] == []

    def test_numbers_stats_tag_is_factual_and_hidden(self):
        assert "[STATS PAR NUMÉRO" in _FACTUAL_TAGS
        assert any("STATS PAR NUM" in p for p in _INTERNAL_TAGS_PATTERNS)
        ctx = {"_chat_meta": {"enrichment_context": _ctx_9405(), "phase": "EVAL_H"}}
        assert _get_temperature(ctx) == 0.2
        leaked = "[STATS PAR NUMÉRO — CHIFFRES EXACTS — grille 2 14 27 35 41] Le 2 est froid."
        assert "STATS PAR" not in _clean_response(leaked)


# ═══════════════════════════════════════════════════════
# C — contrôle 4
# ═══════════════════════════════════════════════════════

def _c4(resp, ctx="", phase="Gemini", **kw):
    return check_number_stats(resp, ctx, phase=phase, lang=kw.pop("lang", "fr"), game=kw.pop("game", "loto"),
                              draw_count=kw.pop("draw_count", 1094), **kw)


class TestCheck4:

    def test_check4_stat_without_block_in_gemini_phase(self):
        f = _c4(T9405)
        kinds = {x["check"] for x in f}
        assert kinds == {"STAT_MISMATCH", "PARTIAL_MATCH_MISMATCH", "GRID_SCORE_ORPHAN"}
        assert {(x["num"], x["field"], x["cited"]) for x in f if x["check"] == "STAT_MISMATCH"} >= {
            (2, "freq", 125), (2, "ecart", 1), (2, "cat", "chaud"), (14, "freq", 105)}
        assert all(x["expected"] in ("aucun bloc", "aucun bloc moteur") for x in f)

    def test_check4_wrong_frequency_with_block(self):
        f = _c4("- Numéro 2 : Fréquence observée 125, retard 1.", _ctx_9405(), phase="EVAL_H")
        assert {(x["field"], x["cited"], x["expected"]) for x in f} == {("freq", 125, "100"), ("ecart", 1, "2")}

    def test_check4_correct_values_pass(self):
        resp = ("Ta grille 2-14-27-35-41 a une conformité de 98/100.\nLe 2 est sorti 100 fois, écart actuel "
                "2 tirages, il est froid.\nLe 35 : 114 sorties, chaud. Meilleure correspondance : "
                "3 numéros (27-35-41) le 16 août 2023.\nChance 8 : 105 sorties.")
        assert _c4(resp, _ctx_9405(), phase="EVAL_H") == []

    def test_check4_hot_label_on_cold_number(self):
        f = _c4("Le 14 est chaud !", _ctx_9405(), phase="EVAL_H")
        assert [(x["num"], x["field"], x["cited"], x["expected"]) for x in f] == [(14, "cat", "chaud", "froid")]

    def test_check4_partial_match_wrong_trio(self):
        f = _c4("Meilleure correspondance : 3 numéros identiques (2-14-35) le 16 août 2023.", _ctx_9405(),
                phase="EVAL_H")
        assert [x["check"] for x in f] == ["PARTIAL_MATCH_MISMATCH"]
        assert f[0]["cited"] == [2, 14, 35] and "2023-08-16 (27, 35, 41)" in f[0]["expected"]

    def test_check4_partial_match_other_tie_date_ok(self):
        assert _c4("3 numéros en commun (14, 35, 41) le 10 janvier 2022.", _ctx_9405(), phase="EVAL_H") == []

    def test_check4_grid_score_without_engine_block(self):
        f = _c4(T9403)
        assert [x["check"] for x in f] == ["GRID_SCORE_ORPHAN"]
        assert f[0]["score"] == 82

    def test_check4_allows_engine_score_phase_g(self):
        gen = ("[GRILLE GÉNÉRÉE PAR HYBRIDE]\nNuméros : [6, 12, 29, 38, 46]\nNuméro Chance : 7\n"
               "Score de conformité : 75/100\n[/GRILLE GÉNÉRÉE PAR HYBRIDE]")
        assert _c4(T9401, gen, phase="G") == []
        assert _c4(T9401.replace("75/100", "88/100"), gen, phase="G")[0]["check"] == "GRID_SCORE_ORPHAN"

    def test_check4_allows_recall_of_engine_grid(self):
        """Exception C′ : rappel d'une grille d'un tour de génération, score possible du moteur."""
        recall = [(frozenset({6, 12, 29, 38, 46}), 75)]
        assert _c4("Ta grille 6 - 12 - 29 - 38 - 46 avait 75/100.", engine_turn_grids=recall) == []
        assert _c4("Ta grille 6 - 12 - 29 - 38 - 46 avait 82/100.", engine_turn_grids=recall)

    def test_check4_ignores_tags_in_history_or_response(self):
        """7318 : un faux bloc écrit par Gemini n'est jamais une source."""
        f = _c4(T7318)
        assert f and all(x["expected"] == "aucun bloc" for x in f)

    @pytest.mark.parametrize("resp,phase,ctx", [
        ("Le jeu reste 100% aléatoire, sur 1094 tirages analysés.", "Gemini", ""),
        ("La paire 22 et 10 est sortie 13 fois ensemble.", "P", "[PAIRE DEMANDÉE (Numéros principaux)]\n13"),
        ("Le 7 est sorti 131 fois.", "SQL", "[RÉSULTAT SQL — CHIFFRES EXACTS]\nnumero: 7 | sorties: 131"),
        ("Le tirage du 22 octobre 2026 : 4 - 8 - 19 - 22 - 35.", "T", "[RÉSULTAT TIRAGE]\n4 - 8 - 19 - 22 - 35"),
        ("Somme de 119, 2 pairs et 3 impairs, dispersion de 39.", "2", ""),
    ])
    def test_check4_false_positives_neutralised(self, resp, phase, ctx):
        assert _c4(resp, ctx, phase=phase) == []

    def test_check4_ignores_values_from_user_message(self):
        assert _c4("Tu dis qu'il est sorti 120 fois ?", user_message="le 7 est sorti 120 fois ?") == []

    def test_check4_phase1_block(self):
        rt = ("[DONNÉES TEMPS RÉEL — CHIFFRES EXACTS - Numéro principal 22]\nFréquence totale : 123 apparitions "
              "sur 1094 tirages (11.24%)\nDernière sortie : 1 novembre 2026\nÉcart actuel : 1 tirages\n"
              "Écart moyen : 8.9 tirages\nClassement fréquence : 4e sur 49\nCatégorie : CHAUD\n[/DONNÉES TEMPS RÉEL]")
        assert _c4("Le 22 est sorti 123 fois, écart 1, rang 4, chaud !", rt, phase="1") == []
        assert _c4("Le 22 est sorti 125 fois.", rt, phase="1")[0]["expected"] == "123"

    def test_check4_log_fields_no_personal_data(self, caplog):
        with caplog.at_level(logging.WARNING):
            _c4(T9405, log_prefix="[HYBRIDE CHAT]")
        line = next(r.getMessage() for r in caplog.records if "STAT_MISMATCH" in r.getMessage())
        for part in ("phase=Gemini", "lang=fr", "game=loto", "num=2", "field=freq", "cited=125",
                     "expected=aucun bloc", "line=- Numéro 2 : Fréquence observée 125, retard 1, chaud."):
            assert part in line
        assert not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", caplog.text)

    def test_check4_numero_chance_is_secondary(self):
        rt = ("[DONNÉES TEMPS RÉEL — CHIFFRES EXACTS - Numéro chance 7]\nFréquence totale : 118 apparitions "
              "sur 1094 tirages (10.8%)\nÉcart actuel : 3 tirages\nCatégorie : CHAUD\n[/DONNÉES TEMPS RÉEL]")
        assert _c4("Le Numéro Chance 7 est sorti 118 fois, écart 3.", rt, phase="1") == []
        assert _c4("Le Numéro Chance 7 est sorti 120 fois.", rt, phase="1")[0]["kind"] == "sec"

    def test_check4_em_stars(self):
        f = _c4("Étoile 9 : 140 sorties.", game="em")
        assert f[0]["kind"] == "sec" and f[0]["num"] == 9


def _stream_ctx(strict_block=True, stat_check=False, enrichment="", phase="Gemini"):
    return {
        "system_prompt": "sys", "contents": [{"role": "user", "parts": [{"text": "q"}]}],
        "mode": "chat", "insult_prefix": "", "history": [], "lang": "fr",
        "_http_client": MagicMock(), "gem_api_key": "",
        "_strict_hallucination_block": strict_block, "_grid_fallback": "",
        "_strict_stat_check": stat_check, "_draw_count": 1094, "_engine_turn_grids": [],
        "_chat_meta": {"phase": phase, "lang": "fr", "t0": time.monotonic(), "enrichment_context": enrichment},
        "_get_tirage_fn": None, "_game": "loto",
    }


async def _stream_9405(*a, **kw):
    for part in T9405.split("\n"):
        yield part + "\n"


async def _run(ctx):
    with patch("services.chat_pipeline_gemini.log_from_meta"):
        return "".join([e async for e in stream_and_respond(
            ctx, "FB", "[T]", "loto", "fr", "C’est bien ?", "loto", "chat", stream_fn=_stream_9405)])


class TestCheck4Flag:

    @pytest.mark.asyncio
    async def test_check4_flag_off_response_unchanged(self, caplog):
        with caplog.at_level(logging.WARNING):
            text = await _run(_stream_ctx(stat_check=False))
        assert "Fréquence observée 125" in text
        assert _STRICT_BLOCK_FALLBACK_I18N["fr"] not in text
        assert "STAT_MISMATCH" in caplog.text and "STRICT_STAT_CHECK" not in caplog.text

    @pytest.mark.asyncio
    async def test_check4_flag_on_blocks(self, caplog):
        with caplog.at_level(logging.WARNING):
            text = await _run(_stream_ctx(stat_check=True))
        assert _STRICT_BLOCK_FALLBACK_I18N["fr"] in text
        assert "Fréquence observée 125" not in text
        assert "STRICT_STAT_CHECK" in caplog.text

    @pytest.mark.asyncio
    async def test_check4_log_only_when_strict_buffer_off(self, caplog):
        with caplog.at_level(logging.WARNING):
            text = await _run(_stream_ctx(strict_block=False, stat_check=True))
        assert "Fréquence observée 125" in text  # flux déjà émis : jamais remplacé
        assert "STAT_MISMATCH" in caplog.text

    def test_flag_read_with_env_bool(self, monkeypatch):
        from config import engine
        for raw, expected in (("true", True), ("TRUE", True), ("True", True), ("1", True), ("off", False),
                              ("vrai", False)):
            monkeypatch.setenv("STRICT_STAT_CHECK", raw)
            assert engine._env_bool("STRICT_STAT_CHECK", False) is expected
        assert engine.STRICT_STAT_CHECK_ENABLED in (True, False)


# ═══════════════════════════════════════════════════════
# E — prompts
# ═══════════════════════════════════════════════════════

PROMPTS = [ROOT / "prompts/chatbot/prompt_hybride.txt"] + [
    ROOT / f"prompts/em/{lang}/prompt_hybride_em.txt" for lang in LANGS]


class TestPrompts:

    @pytest.mark.parametrize("path", PROMPTS, ids=lambda p: p.parent.name)
    def test_prompts_no_concrete_example_stats(self, path):
        text = path.read_text(encoding="utf-8")
        for pat in (r"\b104\b", r"\b112\b", r"\b98\b", r"120 fois contre 100", r"15 fois contre 10",
                    r"9\.? (?:de )?(?:février|February|febrero|fevereiro|Februar|februari)(?: de)? 2026",
                    r"à peine 1 tirage", r"just 1 draw", r"hace solo 1", r"há apenas 1", r"erst 1 Ziehung",
                    r"slechts 1 trekking", r"3-8-10-23-41", r"3 - 17 - 22 - 38 - 45", r"\(22 (?:sorties|appear)",
                    r"Tout chaud", r"red hot", r"rojo vivo", r"ao rubro", r"brandheet"):
            assert not re.search(pat, text, re.IGNORECASE), (path.name, pat)

    @pytest.mark.parametrize("path", PROMPTS, ids=lambda p: p.parent.name)
    def test_stats_section_and_conditional_instructions(self, path):
        text = path.read_text(encoding="utf-8")
        assert text.count("[STATS PAR NUMÉRO]") >= 4
        assert "[N]" in text and "[F]" in text
        for pat in (r"fréquence observée, retard actuel", r"frecuencia observada, retardo actual",
                    r"frequência observada, atraso atual", r"beobachtete Häufigkeit, aktueller Rückstand",
                    r"waargenomen frequentie, huidige achterstand"):
            assert not re.search(pat, text), (path.name, pat)

    @pytest.mark.parametrize("path", PROMPTS[:2], ids=["loto", "em_fr"])
    def test_exact_instruction_fr(self, path):
        assert ("Bloc [STATS PAR NUMÉRO] : cite UNIQUEMENT ces chiffres ; ils priment sur tout chiffre de "
                "l'historique, y compris tes propres réponses précédentes.") in path.read_text(encoding="utf-8")

    def test_breakdown_instruction_conditional(self):
        from services.chat_utils import _format_generation_context
        from services.chat_utils_em import _format_generation_context_em
        loto = _format_generation_context({"nums": [3, 13, 24, 34, 44], "chance": 7, "score": 85, "badges": []})
        em = _format_generation_context_em({"nums": [3, 15, 22, 41, 48], "etoiles": [2, 9], "score": 85,
                                            "badges": []})
        for ctx in (loto, em):
            assert "fréquences, retards" not in ctx
            assert "AUCUNE fréquence ni AUCUN retard par numéro" in ctx


# ═══════════════════════════════════════════════════════
# D3 + annexe ORPHAN + non-régressions R3
# ═══════════════════════════════════════════════════════

class TestD3AndAnnex:

    @pytest.mark.parametrize("msg,expected", [
        ("22/15/16/29/30    3/4", ([22, 15, 16, 29, 30], [3, 4])),       # 7398
        ("4/28/20/33/45.   3/12", ([4, 28, 20, 33, 45], [3, 12])),       # 7400
        ("3/15/22/41/48 étoiles 2/9", ([3, 15, 22, 41, 48], [2, 9])),
        ("3 15 22 41 48 / 2 9", ([3, 15, 22, 41, 48], [2, 9])),
    ])
    def test_em_slash_and_multiple_spaces(self, msg, expected):
        assert _detect_grille_em(msg) == expected

    def test_em_date_still_masked_in_sentence(self):
        """Hors message purement numérique, « 3/4 » reste une date (comportement 1.6.061 inchangé)."""
        assert _detect_grille_em("le tirage du 3/4 avec 22 15 16 29 30") != ([22, 15, 16, 29, 30], [3, 4])

    @pytest.mark.parametrize("msg,expected", [
        ("19 22 37 33 47     10", ([19, 22, 37, 33, 47], 10)),            # 7330
        ("2/14/27/35/41 chance 8", ([2, 14, 27, 35, 41], 8)),
        ("8 3 2 9 10 6", ([8, 3, 2, 9, 10], 6)),                          # 7731 : comportement 1.6.061 inchangé
    ])
    def test_loto_separators_unchanged(self, msg, expected):
        assert _detect_grille(msg) == expected

    @pytest.mark.parametrize("text", [
        "Numéro 2 : Fréquence observée 125, retard 1", "Number 2: observed frequency 125",
        "Número 2: frecuencia 125", "Número 2: frequência 125", "Zahl 2: Häufigkeit 125",
        "Nummer 2: frequentie 125",
    ])
    def test_orphan_stat_regex_matches_frequence_observee(self, text):
        assert _ORPHAN_STAT_RE.search(text) or _ORPHAN_STAT_FREQ_FIRST_RE.search(text)

    def test_orphan_stat_freq_first_ignores_percent(self):
        assert not _ORPHAN_STAT_FREQ_FIRST_RE.search("Le 2 : fréquence 10 %")


class TestR3:

    def test_oui_after_sql_proposal_unchanged(self):
        """V125 : « Oui » reste une continuation, jamais une suite de génération ni un avis."""
        assert _is_short_continuation("Oui")
        assert not _detect_opinion_followup("Oui")
        assert _detect_generation_followup("Oui", GEN_HISTORY) is None

    def test_pair_question_unchanged(self):
        msg = "combien de fois le 22 et le 10 sont sortis ensemble ?"
        assert not _detect_opinion_followup(msg)
        assert _detect_generation_followup(msg, GEN_HISTORY) is None

    def test_8011_phase2_citation_no_false_positive(self):
        resp = ("Ta grille 2 - 14 - 27 - 35 - 41 n'est jamais sortie. Elle a eu 3 numéros en commun "
                "(27, 35, 41) avec le tirage du 16 août 2023.")
        assert _c4(resp, _ctx_9405(), phase="2") == []


# ═══════════════════════════════════════════════════════
# Phase 1-bis — points 1 à 4
# ═══════════════════════════════════════════════════════

GEN_HISTORY_EM = _h(("user", "génère une grille euromillions"),
                    ("assistant", "Voici ta grille : 3 - 15 - 22 - 41 - 48 et les étoiles 2 et 9, score 85/100"))


class TestPhase1bisChain:
    """Point 1 : une question d'avis est un maillon transparent de la chaîne de génération."""

    @pytest.mark.parametrize("game,history", [("loto", GEN_HISTORY), ("em", GEN_HISTORY_EM)])
    def test_followup_after_opinion_turn_is_generation(self, game, history):
        h = history + _h(("user", "C’est bien ?"),
                         ("assistant", "Elle est conforme aux tendances historiques, conformité 98 %."))
        assert _detect_generation_followup("Une autre", h, game=game) == history[0].content
        h2 = h + _h(("user", "Tu en penses quoi ?"), ("assistant", "Toujours conforme."))
        assert _detect_generation_followup("Encore une grille", h2, game=game) == history[0].content

    def test_followup_after_opinion_on_user_grid_not_generation(self):
        h = _h(("user", "2 14 27 35 41 chance 8"), ("assistant", T9404),
               ("user", "C’est bien ?"), ("assistant", "Elle est conforme, conformité 98 %."))
        assert _detect_generation_followup("Une autre", h) is None

    def test_followup_hop_limit(self):
        h = list(GEN_HISTORY)
        for _ in range(5):
            h += _h(("user", "C’est bien ?"), ("assistant", "Conforme."))
        assert _detect_generation_followup("Une autre", h) is None

    @pytest.mark.asyncio
    async def test_followup_after_opinion_runs_phase_g_one_grid(self):
        h = GEN_HISTORY + _h(("user", "C’est bien ?"), ("assistant", "Conforme, 98 %."))
        gen = AsyncMock(return_value={"grids": [{"nums": [3, 13, 24, 34, 44], "chance": 7, "score": 85,
                                                  "badges": []}]})
        with contextlib.ExitStack() as stack:
            _common_patches(stack)
            stack.enter_context(patch("engine.hybride.generate_grids", gen))
            from services.chat_pipeline import _prepare_chat_context
            _, ctx = await _prepare_chat_context("Une autre", h, "loto", MagicMock(), lang="fr")
        assert ctx["_chat_meta"]["phase"] == "G" and gen.await_args.kwargs["n"] == 1


SINGULAR = {
    "fr": ["Une autre", "Une autre grille", "Encore une", "Encore une grille", "Une de plus", "Une nouvelle grille"],
    "en": ["Another one", "Another grid", "One more", "A new one"],
    "es": ["Otra", "Otra combinación", "Una más"],
    "pt": ["Outra", "Outra grelha", "Mais uma"],
    "de": ["Noch eine", "Noch eine Kombination", "Eine andere"],
    "nl": ["Nog een", "Nog een combinatie", "Een andere"],
}
REPEAT = ["Encore", "Encore une fois", "Encore mieux", "Again", "Even better", "Otra vez", "De nuevo", "De novo",
          "Nochmal", "Noch mal", "Nog eens"]


class TestPhase1bisCount:
    """Point 2 : singulier → 1 grille ; répétition nue → nombre d'origine ; nombre explicite → ce nombre."""

    @pytest.mark.parametrize("msg", [m for v in SINGULAR.values() for m in v])
    def test_followup_singular_gives_one_grid(self, msg):
        from services.base_chat_detect_generation import _followup_grid_count
        assert _detect_generation_followup(msg, GEN_HISTORY) is not None
        assert _followup_grid_count(msg, 3) == 1

    @pytest.mark.parametrize("msg", REPEAT)
    def test_followup_bare_repeat_keeps_origin_count(self, msg):
        from services.base_chat_detect_generation import _followup_grid_count
        assert _detect_generation_followup(msg, GEN_HISTORY) is not None
        assert _followup_grid_count(msg, 3) == 3

    @pytest.mark.parametrize("msg,expected", [("Encore 2 grilles", 2), ("Encore deux grilles", 2),
                                              ("Encore 9 grilles", 5)])
    def test_followup_explicit_number_wins(self, msg, expected):
        from services.base_chat_detect_generation import _followup_grid_count
        assert _followup_grid_count(msg, 3) == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize("msg,n", [("Une autre", 1), ("Encore", 3), ("One more", 1), ("Encore 2 grilles", 2)])
    async def test_followup_count_in_pipeline(self, msg, n):
        history = _h(("user", "génère 3 grilles"),
                     ("assistant", "Grille 1/3 : 3 - 13 - 24 - 34 - 44 et le Numéro Chance 7, score 85/100"))
        gen = AsyncMock(return_value={"grids": [{"nums": [3, 13, 24, 34, 44], "chance": 7, "score": 85,
                                                  "badges": []}] * 3})
        with contextlib.ExitStack() as stack:
            _common_patches(stack)
            stack.enter_context(patch("engine.hybride.generate_grids", gen))
            from services.chat_pipeline import _prepare_chat_context
            _, ctx = await _prepare_chat_context(msg, history, "loto", MagicMock(), lang="fr")
        assert ctx["_chat_meta"]["phase"] == "G" and gen.await_args.kwargs["n"] == n


WORTH = {"fr": "Ça vaut le coup ?", "en": "Worth it?", "es": "¿Vale la pena?", "pt": "Vale a pena?",
         "de": "Lohnt sich das?", "nl": "Is het de moeite waard?"}
# Routage réel constaté (phase 1-bis) : la Phase A ne capte « ça vaut le coup » qu'en Loto FR.
WORTH_EXPECTED = {("loto", "fr"): "A"}


class TestPhase1bisWorthIt:
    """Point 3 : décision c en 6 langues, routage réel après une grille (pipeline complet)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("game", ["loto", "em"])
    @pytest.mark.parametrize("lang", LANGS)
    async def test_worth_it_routing(self, game, lang):
        history = GEN_HISTORY if game == "loto" else GEN_HISTORY_EM
        expected = WORTH_EXPECTED.get((game, lang), "EVAL_H")
        with contextlib.ExitStack() as stack:
            _common_patches(stack, game=game)
            mod = "services.chat_pipeline" if game == "loto" else "services.chat_pipeline_em"
            stack.enter_context(patch(f"{mod}.analyze_grille_for_chat", new_callable=AsyncMock, return_value=None))
            if game == "loto":
                from services.chat_pipeline import _prepare_chat_context as prep
                early, ctx = await prep(WORTH[lang], history, "loto", MagicMock(), lang=lang)
            else:
                from services.chat_pipeline_em import _prepare_chat_context_em as prep
                early, ctx = await prep(WORTH[lang], history, "euromillions", MagicMock(), lang=lang)
        phase = (early or {}).get("_chat_meta", {}).get("phase") if early else ctx["_chat_meta"]["phase"]
        assert phase == expected, (game, lang, phase)

    def test_worth_it_stays_phase_A_fr(self):
        from services.chat_detectors import _detect_argent
        assert _detect_argent(WORTH["fr"], "fr")


# ── Point 4 : vérité lue depuis les VRAIS formatteurs ─────────────────────────

def _real_blocks():
    from services.chat_utils import (
        _format_complex_context, _format_generation_context, _format_grille_context,
        _format_numbers_stats_context, _format_stats_context,
    )
    from services.chat_utils_em import (
        _format_complex_context_em, _format_generation_context_em, _format_grille_context_em,
        _format_numbers_stats_context_em, _format_stats_context_em,
    )
    stats_loto = {"numero": 22, "type": "principal", "frequence_totale": 123, "pourcentage_apparition": "11.24%",
                  "derniere_sortie": "2026-11-01", "ecart_actuel": 1, "ecart_moyen": 8.9, "classement": 4,
                  "classement_sur": 49, "categorie": "chaud", "total_tirages": 1094,
                  "periode": "2019-11-06 au 2026-10-31"}
    chance_loto = dict(stats_loto, numero=7, type="chance", frequence_totale=118, classement=2,
                       classement_sur=10, ecart_actuel=3, categorie="neutre")
    stats_em = dict(stats_loto, type="boule", frequence_totale=88, classement=5, classement_sur=50, total_tirages=732)
    star_em = dict(stats_loto, numero=9, type="etoile", frequence_totale=140, classement=1, classement_sur=12,
                   ecart_actuel=2, total_tirages=732)
    classement = {"items": [{"numero": 31, "frequence": 134, "ecart_actuel": 3, "categorie": "chaud"},
                            {"numero": 30, "frequence": 129, "ecart_actuel": 12, "categorie": "chaud"}],
                  "total_tirages": 1094, "periode": "2019-11-06 au 2026-10-31"}
    classement_chance = {"items": [{"numero": 7, "frequence": 120, "ecart_actuel": 4, "categorie": "chaud"}],
                         "total_tirages": 1094, "periode": "2019-11-06 au 2026-10-31"}
    comparaison = {"num1": {"numero": 7, "frequence_totale": 112, "pourcentage_apparition": "10.2%",
                            "ecart_actuel": 3, "categorie": "chaud"},
                   "num2": {"numero": 23, "frequence_totale": 98, "pourcentage_apparition": "9.0%",
                            "ecart_actuel": 11, "categorie": "froid"},
                   "diff_frequence": 14, "favori_frequence": 7}
    categorie = {"categorie": "froid", "numeros": [{"numero": 43}, {"numero": 1}], "count": 2,
                 "periode_analyse": "2 dernières années"}
    analysis_em = dict(ANALYSIS_9405, numeros=[3, 15, 22, 41, 48], etoiles=[2, 9])
    analysis_em["analyse"] = dict(ANALYSIS_9405["analyse"], numeros_chauds=[22], numeros_froids=[3, 15],
                                  numeros_neutres=[41, 48])
    analysis_em["historique"] = {"deja_sortie": False, "exact_dates": [], "meilleure_correspondance": {
        "nb_numeros_communs": 3, "date": "2024-05-10", "numeros_communs": [3, 22, 48], "etoiles_match": False,
        "egalites": [{"date": "2024-05-10", "numeros_communs": [3, 22, 48], "etoiles_match": False}],
        "nb_egalites": 1}}
    stats_block_em = {"total_tirages": 732, "date_min": "2019-10-29", "date_max": "2026-10-30",
                      "principaux": [{"numero": 22, "frequence": 49, "ecart_actuel": 5, "derniere_sortie": "2026-10-10",
                                      "rang": 50, "rang_sur": 50, "categorie": "froid"}],
                      "secondaires": [{"numero": 9, "frequence": 140, "ecart_actuel": 2,
                                       "derniere_sortie": "2026-10-23", "rang": 1, "rang_sur": 12,
                                       "categorie": "chaud"}]}
    cx = {"type": "classement", "tri": "frequence_desc", "limit": 2, "num_type": "principal"}
    cx_ch = dict(cx, num_type="chance", limit=1)
    cx_st = dict(cx, num_type="etoile", limit=1)
    comp = {"type": "comparaison"}
    cat = {"type": "categorie"}
    return [
        # (id, jeu, phase, contexte, réponse juste, réponse fausse, contrôle attendu sur la fausse)
        ("gen_loto", "loto", "G", _format_generation_context({"nums": [3, 13, 24, 34, 44], "chance": 7, "score": 85,
                                                             "badges": ["Équilibre"]}),
         "Voici ta grille 3 - 13 - 24 - 34 - 44, chance 7, score de conformité 85/100.",
         "Voici ta grille 3 - 13 - 24 - 34 - 44, chance 7, score de conformité 88/100.", "GRID_SCORE_ORPHAN"),
        ("gen_em", "em", "G", _format_generation_context_em({"nums": [3, 15, 22, 41, 48], "etoiles": [2, 9],
                                                            "score": 95, "badges": []}),
         "Ta grille : 3 - 15 - 22 - 41 - 48, étoiles 2 et 9, score 95/100.",
         "Ta grille : 3 - 15 - 22 - 41 - 48, étoiles 2 et 9, score 97/100.", "GRID_SCORE_ORPHAN"),
        ("stats_loto", "loto", "1", _format_stats_context(stats_loto),
         "Le 22 est sorti 123 fois, écart actuel 1, rang 4, il est chaud !",
         "Le 22 est sorti 125 fois.", "STAT_MISMATCH"),
        ("stats_chance_loto", "loto", "1", _format_stats_context(chance_loto),
         "Le numéro chance 7 est sorti 118 fois, écart 3, neutre.",
         "Le numéro chance 7 est sorti 118 fois, il est chaud.", "STAT_MISMATCH"),
        ("stats_em", "em", "1", _format_stats_context_em(stats_em),
         "Le 22 est sorti 88 fois, écart 1, rang 5.", "Le 22 est sorti 90 fois.", "STAT_MISMATCH"),
        ("stats_star_em", "em", "1", _format_stats_context_em(star_em),
         "L'étoile 9 est sortie 140 fois, écart 2, rang 1, chaude !",
         "L'étoile 9 est sortie 141 fois.", "STAT_MISMATCH"),
        ("classement_loto", "loto", "3", _format_complex_context(cx, classement),
         "Le 31 : 134 sorties, écart actuel 3, chaud. Le 30 : 129 sorties.",
         "Le 31 : 136 sorties.", "STAT_MISMATCH"),
        ("classement_chance_loto", "loto", "3", _format_complex_context(cx_ch, classement_chance),
         "Le 7 est le numéro chance le plus sorti : 120 sorties.", "Le 7 : 121 sorties.", "STAT_MISMATCH"),
        ("classement_star_em", "em", "3", _format_complex_context_em(cx_st, classement_chance),
         "L'étoile 7 : 120 sorties, écart 4.", "L'étoile 7 : 125 sorties.", "STAT_MISMATCH"),
        ("comparaison_loto", "loto", "3", _format_complex_context(comp, comparaison),
         "Le 7 est sorti 112 fois contre 98 pour le 23.", "Le 7 est sorti 115 fois.", "STAT_MISMATCH"),
        ("comparaison_em", "em", "3", _format_complex_context_em(comp, comparaison),
         "Le 23 : 98 sorties, écart 11, froid.", "Le 23 : 98 sorties, chaud.", "STAT_MISMATCH"),
        ("categorie_loto", "loto", "3", _format_complex_context(cat, categorie),
         "Le 43 et le 1 sont froids.", "Le 43 est chaud.", "STAT_MISMATCH"),
        ("grille_loto", "loto", "2", _format_grille_context(ANALYSIS_9405),
         "Le 35 et le 41 sont chauds, le 2 est froid. Conformité 98/100.", "Le 2 est chaud.", "STAT_MISMATCH"),
        ("grille_em", "em", "2", _format_grille_context_em(analysis_em),
         "Le 22 est chaud, le 3 est froid. 3 numéros communs (3, 22, 48) le 10 mai 2024.",
         "3 numéros communs (3, 15, 22) le 10 mai 2024.", "PARTIAL_MATCH_MISMATCH"),
        ("stats_bloc_loto", "loto", "EVAL_H", _format_numbers_stats_context(STATS_9405),
         "Le 2 : 100 sorties, écart 2, froid. Chance 8 : 105 sorties, écart 10.",
         "Chance 8 : 107 sorties.", "STAT_MISMATCH"),
        ("stats_bloc_em", "em", "EVAL_H", _format_numbers_stats_context_em(stats_block_em),
         "Le 22 : 49 sorties, écart 5, froid. Étoile 9 : 140 sorties, chaude.",
         "Étoile 9 : 139 sorties.", "STAT_MISMATCH"),
    ]


class TestCheck4RealFormatters:

    @pytest.mark.parametrize("case", _real_blocks(), ids=lambda c: c[0])
    def test_check4_truth_from_real_formatters(self, case):
        _id, game, phase, ctx, good, bad, expected = case
        assert check_number_stats(good, ctx, phase=phase, lang="fr", game=game, draw_count=1094) == [], _id
        f = check_number_stats(bad, ctx, phase=phase, lang="fr", game=game, draw_count=1094)
        assert len(f) == 1 and f[0]["check"] == expected, (_id, f)


# ═══════════════════════════════════════════════════════
# Patches communs (pipeline réel, données simulées)
# ═══════════════════════════════════════════════════════

def _common_patches(stack, game="loto"):
    mod = "services.chat_pipeline" if game == "loto" else "services.chat_pipeline_em"
    stack.enter_context(patch("services.chat_pipeline._get_draw_count", new_callable=AsyncMock,
                              return_value=1094 if game == "loto" else 732))
    stack.enter_context(patch(f"{mod}.{'load_prompt' if game == 'loto' else 'load_prompt_em'}", return_value="sys"))
    stack.enter_context(patch("db_cloudsql.get_connection", side_effect=ConnectionError("mock")))
    stack.enter_context(patch(f"{mod}.get_grid_numbers_stats", new_callable=AsyncMock, return_value=None))
    stack.enter_context(patch(
        "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
        side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
