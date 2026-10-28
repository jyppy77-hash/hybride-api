"""
Lot phase P — combinaisons exactes : HYBRIDE calcule, il n'invente pas.

- Paire précise (2 boules / 2 étoiles EM) → get_single_pair / get_single_star_pair (déterministe)
- Triplet, boule + chance / étoile, paire sur période → SQL encadré (force_sql)
- Échec (paire None, SQL 429 / rejet / erreur) → garde honnête 6 langues, jamais de top 5
- Dates masquées avant extraction des numéros (cas 8546, 8697)

Base entièrement mockée : aucun accès DB, aucun appel Gemini.
"""

import contextlib
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.base_chat_detect_correlation import (
    _detect_combo_count, _detect_combo_with_secondary, _extract_combo_numbers,
)
from services.base_chat_detect_generation import _detect_generation
from services.base_chat_sql import _MAX_SQL_PER_SESSION, _SQL_LIMIT_MESSAGES
from services.base_chat_detect_generation import _extract_forced_numbers
from services.base_chat_detect_temporal import _mask_dates
from services.base_chat_utils import _format_single_pair_context_base
from services.chat_detectors import _detect_numero
from services.chat_detectors_em_intent import _detect_numero_em
from services.chat_pipeline_shared import _COMBO_UNAVAILABLE_MESSAGES

LANGS = ["fr", "en", "es", "pt", "de", "nl"]

# Étalon : paire 22 + 10 = 13 en Loto (5 boules, chance non compté), rang 94 / 1176
PAIR_22_10 = {"n1": 10, "n2": 22, "count": 13, "percentage": 1.2, "rank": 94,
              "total_draws": 1090, "total_pairs": 1176}
STAR_PAIR_3_7 = {"s1": 3, "s2": 7, "count": 21, "percentage": 2.9, "rank": 40,
                 "total_draws": 732, "total_pairs": 66}

PAIR_MSGS = {
    "fr": "combien de fois le 22 et le 10 sont sortis ensemble ?",
    "en": "how many times did 22 and 10 come out together?",
    "es": "¿cuántas veces salieron juntos el 22 y el 10?",
    "pt": "quantas vezes saíram juntos o 22 e o 10?",
    "de": "wie oft wurden die 22 und die 10 zusammen gezogen?",
    "nl": "hoe vaak zijn de 22 en de 10 samen getrokken?",
}
TRIPLET_MSGS = {
    "fr": "le 22, le 10 et le 35 sont sortis ensemble combien de fois ?",
    "en": "how many times did 22, 10 and 35 come out together?",
    "es": "¿cuántas veces salieron juntos el 22, el 10 y el 35?",
    "pt": "quantas vezes saíram juntos o 22, o 10 e o 35?",
    "de": "wie oft kamen 22, 10 und 35 zusammen?",
    "nl": "hoe vaak zijn 22, 10 en 35 samen getrokken?",
}
BALL_CHANCE_MSGS = {
    "fr": "le 22 avec le numéro chance 10, combien de fois ?",
    "en": "how many times did 22 come out with lucky number 10?",
    "es": "¿cuántas veces salió el 22 con el número de la suerte 10?",
    "pt": "quantas vezes saiu o 22 com o número da sorte 10?",
    "de": "wie oft kam die 22 mit der Glückszahl 10?",
    "nl": "hoe vaak viel de 22 met geluksnummer 10?",
}
BALL_STAR_MSGS = {
    "fr": "combien de fois le 22 est sorti avec l'étoile 3 ?",
    "en": "how many times did 22 come out with star 3?",
    "es": "¿cuántas veces salió el 22 con la estrella 3?",
    "pt": "quantas vezes saiu o 22 com a estrela 3?",
    "de": "wie oft kam die 22 mit Stern 3?",
    "nl": "hoe vaak viel de 22 met ster 3?",
}
WITH_CHANCE_MSGS = {  # Q2 : sans « combien de fois » ni « ensemble »
    "fr": "le 22 avec le chance 10 ?",
    "en": "22 with lucky number 10?",
    "es": "¿el 22 con el número de la suerte 10?",
    "pt": "o 22 com o número da sorte 10?",
    "de": "die 22 mit der Glückszahl 10?",
    "nl": "de 22 met geluksnummer 10?",
}
WITH_STAR_MSGS = {
    "fr": "le 22 avec l'étoile 3 ?",
    "en": "22 with star 3?",
    "es": "¿el 22 con la estrella 3?",
    "pt": "o 22 com a estrela 3?",
    "de": "die 22 mit Stern 3?",
    "nl": "de 22 met ster 3?",
}
GEN_FORCED_MSGS = {  # Phase G avec numéros imposés : jamais de bloc paire à côté de la grille
    "fr": "fais-moi une grille avec le 22 et le 10",
    "en": "make me a grid with 22 and 10",
    "es": "hazme una combinación con el 22 y el 10",
    "pt": "faz-me uma grelha com o 22 e o 10",
    "de": "erstelle mir eine Kombination mit der 22 und der 10",
    "nl": "maak een combinatie met de 22 en de 10",
}
STAR_PAIR_MSGS = {
    "fr": "les étoiles 3 et 7 sont sorties ensemble combien de fois ?",
    "en": "how many times did stars 3 and 7 come out together?",
    "es": "¿cuántas veces salieron juntas las estrellas 3 y 7?",
    "pt": "quantas vezes saíram juntas as estrelas 3 e 7?",
    "de": "wie oft kamen die Sterne 3 und 7 zusammen?",
    "nl": "hoe vaak zijn de sterren 3 en 7 samen getrokken?",
}


# ═══════════════════════════════════════════════════════
# Helpers — patches pipeline (détecteurs paires/triplets/période RÉELS)
# ═══════════════════════════════════════════════════════

def _loto_patches(stack, **overrides):
    defaults = {
        "load_prompt": "sys",
        "_detect_insulte": None,
        "_detect_compliment": None,
        "_detect_salutation": False,
        "_detect_generation": False,
        "_detect_grid_evaluation": None,
        "_detect_argent": False,
        "_is_short_continuation": False,
        "_detect_prochain_tirage": False,
        "_detect_tirage": None,
        "_detect_grille": (None, None),
        "_detect_requete_complexe": None,
        "_detect_cooccurrence_high_n": False,
        "_detect_out_of_range": (None, None),
        "_detect_numero": (None, None),
        "_build_session_context": "",
    }
    defaults.update(overrides)
    for name, rv in defaults.items():
        stack.enter_context(patch(f"services.chat_pipeline.{name}", return_value=rv))
    stack.enter_context(patch(
        "services.chat_pipeline._get_draw_count", new_callable=AsyncMock, return_value=1090,
    ))


def _em_patches(stack, **overrides):
    em = "services.chat_pipeline_em"
    defaults = {
        "load_prompt_em": "sys",
        "_detect_insulte": None,
        "_detect_compliment": None,
        "_detect_salutation": False,
        "_detect_generation": False,
        "_detect_grid_evaluation": None,
        "_detect_argent_em": False,
        "_detect_country_em": False,
        "_is_short_continuation": False,
        "_detect_prochain_tirage_em": False,
        "_detect_tirage": None,
        "_detect_grille_em": (None, None),
        "_detect_requete_complexe_em": None,
        "_detect_cooccurrence_high_n": False,
        "_detect_out_of_range_em": (None, None),
        "_detect_numero_em": (None, None),
        "_build_session_context_em": "",
    }
    defaults.update(overrides)
    for name, rv in defaults.items():
        stack.enter_context(patch(f"{em}.{name}", return_value=rv))
    stack.enter_context(patch(
        "services.chat_pipeline._get_draw_count", new_callable=AsyncMock, return_value=732,
    ))


def _gen_patches(stack, game):
    """Phase G réelle (détection) avec moteur et base neutralisés (aucune connexion)."""
    engine, mod, fmt = (("engine.hybride", "services.chat_pipeline", "_format_generation_context")
                        if game == "loto" else
                        ("engine.hybride_em", "services.chat_pipeline_em", "_format_generation_context_em"))
    stack.enter_context(patch(f"{mod}._detect_generation", side_effect=_detect_generation))
    stack.enter_context(patch("db_cloudsql.get_connection", side_effect=ConnectionError("mock")))
    gen = stack.enter_context(patch(
        f"{engine}.generate_grids", new_callable=AsyncMock,
        return_value={"grids": [{"nums": [3, 10, 22, 30, 41]}]}))
    stack.enter_context(patch(
        f"{mod}.{fmt}", return_value="[GRILLE GÉNÉRÉE PAR HYBRIDE]\nNuméros : [3, 10, 22, 30, 41]"))
    return gen


async def _loto_ctx(message, lang="fr", history=None):
    from services.chat_pipeline import _prepare_chat_context
    return await _prepare_chat_context(message, history or [], "loto", MagicMock(), lang=lang)


async def _em_ctx(message, lang="fr"):
    from services.chat_pipeline_em import _prepare_chat_context_em
    return await _prepare_chat_context_em(message, [], "euromillions", MagicMock(), lang=lang)


# ═══════════════════════════════════════════════════════
# S1 — _mask_dates (6 langues)
# ═══════════════════════════════════════════════════════

@pytest.mark.parametrize("text", [
    "26 octobre 2026", "le 1er mai", "October 26, 2026", "the 26th of October",
    "26 de octubre de 2026", "26 de outubro de 2026", "26. Oktober 2026", "26 oktober 2026",
    "26/10", "26/10/2026", "26-10-2026", "26.10.2026", "May 22, 2026", "22nd of May",
])
def test_mask_dates_removes_day_number(text):
    assert not any(ch.isdigit() for ch in _mask_dates(text))


@pytest.mark.parametrize("text", [
    "grille 5-12-23-34-45", "score 95/100", "2.5 fois", "22 may come with 10",
    "le 22 et le 10", "32/13",
])
def test_mask_dates_keeps_non_dates(text):
    assert _mask_dates(text) == text


def test_mask_dates_empty():
    assert _mask_dates("") == ""


# ═══════════════════════════════════════════════════════
# S1 — _extract_combo_numbers
# ═══════════════════════════════════════════════════════

@pytest.mark.parametrize("lang", LANGS)
def test_extract_pair_6_langs(lang):
    r = _extract_combo_numbers(PAIR_MSGS[lang], "loto")
    assert r == {"main": [22, 10], "secondary": [], "out_of_range": False}


@pytest.mark.parametrize("lang", LANGS)
def test_extract_triplet_6_langs(lang):
    assert _extract_combo_numbers(TRIPLET_MSGS[lang], "loto")["main"] == [22, 10, 35]


@pytest.mark.parametrize("lang", LANGS)
def test_extract_ball_chance_6_langs(lang):
    r = _extract_combo_numbers(BALL_CHANCE_MSGS[lang], "loto")
    assert r["main"] == [22] and r["secondary"] == [10] and not r["out_of_range"]


@pytest.mark.parametrize("lang", LANGS)
def test_extract_ball_star_6_langs(lang):
    r = _extract_combo_numbers(BALL_STAR_MSGS[lang], "em")
    assert r["main"] == [22] and r["secondary"] == [3]


@pytest.mark.parametrize("lang", LANGS)
def test_extract_star_pair_6_langs(lang):
    r = _extract_combo_numbers(STAR_PAIR_MSGS[lang], "em")
    assert r["main"] == [] and r["secondary"] == [3, 7]


def test_extract_chance_before_keyword():
    r = _extract_combo_numbers("le 10 en numéro chance avec le 22", "loto")
    assert r["main"] == [22] and r["secondary"] == [10]


def test_extract_loto_single_chance_next_number_is_ball():
    r = _extract_combo_numbers("chance 10 et 22", "loto")
    assert r["secondary"] == [10] and r["main"] == [22]


def test_extract_out_of_range_ball():
    assert _extract_combo_numbers("le 22 et le 55 ensemble", "loto")["out_of_range"]
    assert not _extract_combo_numbers("le 22 et le 50 ensemble", "em")["out_of_range"]


def test_extract_out_of_range_star_and_chance():
    assert _extract_combo_numbers("étoiles 3 et 15", "em")["out_of_range"]
    assert _extract_combo_numbers("le 22 avec le chance 12", "loto")["out_of_range"]


def test_extract_duplicate_number():
    assert _extract_combo_numbers("le 22 et le 22 ensemble", "loto")["main"] == [22]


def test_extract_ignores_dates_and_quantities():
    assert _extract_combo_numbers("22 et 10 ensemble depuis le 23 octobre 2025", "loto")["main"] == [22, 10]
    assert _extract_combo_numbers("les 2 meilleures paires sur les 10 derniers tirages", "loto")["main"] == []
    assert _extract_combo_numbers("le 22 et le 10, score 95/100, top 5", "loto")["main"] == [22, 10]
    assert _extract_combo_numbers("le 22 et le 10 sur 20 % des tirages", "loto")["main"] == [22, 10]
    assert _extract_combo_numbers("le 1er et le 2e tirage avec le 22", "loto")["main"] == [22]


def test_extract_em_numbers_default_to_balls():
    """Q6 : EM « le 3 et le 7 » sans mot étoile → boules."""
    r = _extract_combo_numbers("le 3 et le 7 ensemble ?", "em")
    assert r["main"] == [3, 7] and r["secondary"] == []


@pytest.mark.parametrize("msg", list(PAIR_MSGS.values())[1:] + ["combien de fois le 22 et le 10 ?"])
def test_detect_combo_count(msg):
    assert _detect_combo_count(msg)


def test_detect_combo_count_negative():
    assert not _detect_combo_count("et le 22 et 10 ensemble ?")


@pytest.mark.parametrize("lang", LANGS)
def test_detect_combo_with_secondary_6_langs(lang):
    assert _detect_combo_with_secondary(WITH_CHANCE_MSGS[lang], "loto")
    assert _detect_combo_with_secondary(WITH_STAR_MSGS[lang], "em")


@pytest.mark.parametrize("msg", [
    "stats du numéro chance 10", "le chance 10 ?", "le 22 avec le 10", "avec la chance, le 22 ?",
])
def test_detect_combo_with_secondary_negative(msg):
    assert not _detect_combo_with_secondary(msg, "loto")


@pytest.mark.parametrize("lang", LANGS)
def test_generation_forced_msgs_are_detected_as_generation(lang):
    assert _detect_generation(GEN_FORCED_MSGS[lang])


# ═══════════════════════════════════════════════════════
# S6 / S6b — dates hors Phase 1 et hors numéros forcés
# ═══════════════════════════════════════════════════════

def test_detect_numero_ignores_date_8697():
    assert _detect_numero("Le loto du 26 octobre 2026") == (None, None)


def test_detect_numero_em_ignores_date_8546():
    assert _detect_numero_em("5 grilles pour l'euro million du 23 octobre 2026") == (None, None)


@pytest.mark.parametrize("msg,expected", [
    ("le 26 ?", (26, "principal")), ("numéro 23", (23, "principal")), ("27", (27, "principal")),
    ("combien de fois le 12 en mai 2025", (12, "principal")), ("chance 7", (7, "chance")),
])
def test_detect_numero_non_regression(msg, expected):
    assert _detect_numero(msg) == expected


def test_detect_numero_em_non_regression():
    assert _detect_numero_em("le 26 ?") == (26, "boule")
    assert _detect_numero_em("étoile 5") == (5, "etoile")


def test_forced_numbers_ignore_date_8546():
    r = _extract_forced_numbers(
        "Donne moi 5 grilles avec les etoiles pour l'euro million du 23 octobre 2026", game="em")
    assert r["forced_nums"] == []


def test_forced_numbers_non_regression():
    assert _extract_forced_numbers("génère une grille avec le 7 et le 23", game="loto")["forced_nums"] == [7, 23]


# ═══════════════════════════════════════════════════════
# S3 — format du bloc paire
# ═══════════════════════════════════════════════════════

def test_format_single_pair_block():
    block = _format_single_pair_context_base(
        PAIR_22_10, "PAIRE DEMANDÉE (Numéros principaux)",
        "les 5 boules principales de chaque tirage, numéro chance non compté")
    assert block.startswith("[CORRÉLATIONS DE PAIRES — PAIRE DEMANDÉE")
    assert "Paire 10 + 22 → 13 fois sur 1090 tirages (1.2%)" in block
    assert "Rang : 94 sur 1176 paires observées" in block
    assert "numéro chance non compté" in block


def test_format_single_pair_zero():
    block = _format_single_pair_context_base(
        {**PAIR_22_10, "count": 0, "percentage": 0.0}, "PAIRE DEMANDÉE", "x")
    assert "jamais sortie ensemble sur 1090 tirages" in block
    assert "Rang" not in block


def test_format_single_star_pair_block():
    block = _format_single_pair_context_base(STAR_PAIR_3_7, "PAIRE D'ÉTOILES DEMANDÉE", "x")
    assert "Paire 3 + 7 → 21 fois sur 732 tirages" in block


# ═══════════════════════════════════════════════════════
# S2 — routage Loto
# ═══════════════════════════════════════════════════════

class TestRoutingLoto:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGS)
    async def test_pair_22_10_is_13_6_langs(self, lang):
        """Étalon : 22 + 10 = 13 (5 boules) via get_single_pair, sans top 5 ni SQL."""
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            single = stack.enter_context(patch(
                "services.chat_pipeline.get_single_pair", new_callable=AsyncMock, return_value=PAIR_22_10))
            top5 = stack.enter_context(patch(
                "services.chat_pipeline.get_pair_correlations", new_callable=AsyncMock))
            gen_sql = stack.enter_context(patch(
                "services.chat_pipeline._generate_sql", new_callable=AsyncMock))
            early, ctx = await _loto_ctx(PAIR_MSGS[lang], lang)

        assert early is None
        meta = ctx["_chat_meta"]
        assert meta["phase"] == "P"
        assert "10 + 22 → 13 fois" in meta["enrichment_context"]
        assert "numéro chance non compté" in meta["enrichment_context"]
        single.assert_awaited_once_with(n1=22, n2=10)
        top5.assert_not_called()
        gen_sql.assert_not_called()

    @pytest.mark.asyncio
    async def test_pair_without_ensemble_word_q1(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            single = stack.enter_context(patch(
                "services.chat_pipeline.get_single_pair", new_callable=AsyncMock, return_value=PAIR_22_10))
            early, ctx = await _loto_ctx("combien de fois le 22 et le 10 ?")
        assert ctx["_chat_meta"]["phase"] == "P"
        single.assert_awaited_once_with(n1=22, n2=10)

    @pytest.mark.asyncio
    async def test_star_pair_not_called_for_loto(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch(
                "services.chat_pipeline.get_single_pair", new_callable=AsyncMock, return_value=PAIR_22_10))
            _, ctx = await _loto_ctx("et le 22 et 10 ensemble ?")
        from services.chat_pipeline import _build_loto_config
        assert "get_single_star_pair" not in _build_loto_config()
        assert "10 + 22" in ctx["_chat_meta"]["enrichment_context"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("msgs", [TRIPLET_MSGS, BALL_CHANCE_MSGS])
    @pytest.mark.parametrize("lang", LANGS)
    async def test_triplet_and_ball_chance_cede_to_sql(self, msgs, lang):
        """Q2 : triplet / boule + chance → SQL encadré (force_sql), sans Phase 1 ni top 5."""
        with contextlib.ExitStack() as stack:
            _loto_patches(stack, _detect_numero=(22, "principal"))
            single = stack.enter_context(patch(
                "services.chat_pipeline.get_single_pair", new_callable=AsyncMock))
            stats = stack.enter_context(patch(
                "services.chat_pipeline.get_numero_stats", new_callable=AsyncMock))
            rts = stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                return_value=("[RÉSULTAT SQL — CHIFFRES EXACTS, NE PAS MODIFIER]\nensemble: 2\n[/RÉSULTAT SQL]",
                              "SELECT COUNT(*) ...", "OK")))
            _, ctx = await _loto_ctx(msgs[lang], lang)

        assert rts.await_args.kwargs["force_sql"] is True
        assert ctx["_chat_meta"]["phase"] == "SQL"
        single.assert_not_called()
        stats.assert_not_called()

    @pytest.mark.asyncio
    async def test_pair_with_period_cedes_to_sql_q7(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            single = stack.enter_context(patch(
                "services.chat_pipeline.get_single_pair", new_callable=AsyncMock))
            top5 = stack.enter_context(patch(
                "services.chat_pipeline.get_pair_correlations", new_callable=AsyncMock))
            rts = stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                return_value=("[RÉSULTAT SQL]\nensemble: 4\n[/RÉSULTAT SQL]", "SELECT ...", "OK")))
            _, ctx = await _loto_ctx("le 22 et le 10 ensemble depuis 2020 ?")
        assert rts.await_args.kwargs["force_sql"] is True
        single.assert_not_called()
        top5.assert_not_called()

    @pytest.mark.asyncio
    async def test_out_of_range_goes_to_oor_q4(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack, _detect_out_of_range=(55, "principal"))
            top5 = stack.enter_context(patch(
                "services.chat_pipeline.get_pair_correlations", new_callable=AsyncMock))
            single = stack.enter_context(patch(
                "services.chat_pipeline.get_single_pair", new_callable=AsyncMock))
            early, ctx = await _loto_ctx("le 22 et le 55 ensemble")
        assert early is not None
        assert ctx is None
        top5.assert_not_called()
        single.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_number_general_phase_p_q5(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            top5 = stack.enter_context(patch(
                "services.chat_pipeline.get_pair_correlations", new_callable=AsyncMock,
                return_value={"pairs": [], "total_draws": 1090, "window": None}))
            single = stack.enter_context(patch(
                "services.chat_pipeline.get_single_pair", new_callable=AsyncMock))
            _, ctx = await _loto_ctx("le 22 et le 22 ensemble")
        top5.assert_awaited_once()
        single.assert_not_called()
        assert ctx["_chat_meta"]["phase"] == "P"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("msg", [
        "quelles sont les paires les plus fréquentes ?",
        "quel numéro sort le plus souvent avec le 15",
    ])
    async def test_general_phase_p_unchanged(self, msg):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            top5 = stack.enter_context(patch(
                "services.chat_pipeline.get_pair_correlations", new_callable=AsyncMock,
                return_value={"pairs": [], "total_draws": 1090, "window": None}))
            single = stack.enter_context(patch(
                "services.chat_pipeline.get_single_pair", new_callable=AsyncMock))
            _, ctx = await _loto_ctx(msg)
        top5.assert_awaited_once()
        single.assert_not_called()
        assert "Période demandée non prise en charge" not in ctx["_chat_meta"]["enrichment_context"]

    @pytest.mark.asyncio
    async def test_general_triplets_unchanged(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            tri = stack.enter_context(patch(
                "services.chat_pipeline.get_triplet_correlations", new_callable=AsyncMock,
                return_value={"triplets": [], "total_draws": 1090, "window": None}))
            _, ctx = await _loto_ctx("quels sont les triplets les plus sortis ?")
        tri.assert_awaited_once()
        assert ctx["_chat_meta"]["phase"] == "P"

    @pytest.mark.asyncio
    async def test_general_pairs_with_period_note_q15(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch(
                "services.chat_pipeline.get_pair_correlations", new_callable=AsyncMock,
                return_value={"pairs": [], "total_draws": 1090, "window": None}))
            _, ctx = await _loto_ctx("quelles paires sortent le plus en 2025 ?")
        enr = ctx["_chat_meta"]["enrichment_context"]
        assert enr.startswith("[CORRÉLATIONS DE PAIRES")
        assert "Période demandée non prise en charge" in enr

    @pytest.mark.asyncio
    async def test_general_triplets_with_period_note_q15(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch(
                "services.chat_pipeline.get_triplet_correlations", new_callable=AsyncMock,
                return_value={"triplets": [], "total_draws": 1090, "window": None}))
            _, ctx = await _loto_ctx("quels triplets sortent le plus en 2025 ?")
        enr = ctx["_chat_meta"]["enrichment_context"]
        assert enr.startswith("[CORRÉLATIONS DE TRIPLETS")
        assert "Période demandée non prise en charge" in enr

    @pytest.mark.asyncio
    @pytest.mark.parametrize("side_effect,rv", [(None, None), (TimeoutError(), None)])
    @pytest.mark.parametrize("lang", LANGS)
    async def test_pair_unavailable_honest_guard_q9(self, side_effect, rv, lang):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch(
                "services.chat_pipeline.get_single_pair", new_callable=AsyncMock,
                return_value=rv, side_effect=side_effect))
            top5 = stack.enter_context(patch(
                "services.chat_pipeline.get_pair_correlations", new_callable=AsyncMock))
            _, ctx = await _loto_ctx(PAIR_MSGS[lang], lang)
        enr = ctx["_chat_meta"]["enrichment_context"]
        assert enr.startswith("[CORRÉLATIONS DE PAIRES — INDISPONIBLE]")
        assert _COMBO_UNAVAILABLE_MESSAGES[lang] in enr
        assert "13" not in enr
        top5.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGS)
    async def test_sql_generation_failure_honest_guard(self, lang):
        """Point 4 : SQL encadré en échec (429 → _generate_sql None) → garde, pas d'invention."""
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch(
                "services.chat_pipeline._generate_sql", new_callable=AsyncMock, return_value=None))
            _, ctx = await _loto_ctx(TRIPLET_MSGS[lang], lang)
        meta = ctx["_chat_meta"]
        assert meta["sql_status"] == "ERROR"
        assert meta["enrichment_context"].startswith("[RÉSULTAT SQL — INDISPONIBLE]")
        assert _COMBO_UNAVAILABLE_MESSAGES[lang] in meta["enrichment_context"]
        assert "aucun résultat" not in meta["enrichment_context"].lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGS)
    async def test_sql_session_limit_honest_guard(self, lang):
        """Point 1 : plafond de SQL par session (LIMIT) → garde + message de plafond."""
        history = [SimpleNamespace(role="assistant", content="[RÉSULTAT SQL]\nensemble: 1")] * _MAX_SQL_PER_SESSION
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            gen_sql = stack.enter_context(patch(
                "services.chat_pipeline._generate_sql", new_callable=AsyncMock))
            _, ctx = await _loto_ctx(TRIPLET_MSGS[lang], lang, history=history)
        meta = ctx["_chat_meta"]
        assert meta["sql_status"] == "LIMIT"
        assert meta["enrichment_context"].startswith("[RÉSULTAT SQL — INDISPONIBLE]")
        assert _SQL_LIMIT_MESSAGES[lang] in meta["enrichment_context"]
        gen_sql.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGS)
    async def test_with_chance_cedes_to_sql_q2(self, lang):
        """Point 3 : « le 22 avec le chance 10 ? » → SQL encadré, pas Phase 1."""
        with contextlib.ExitStack() as stack:
            _loto_patches(stack, _detect_numero=(22, "principal"))
            stats = stack.enter_context(patch(
                "services.chat_pipeline.get_numero_stats", new_callable=AsyncMock))
            rts = stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                return_value=("[RÉSULTAT SQL]\nensemble: 2\n[/RÉSULTAT SQL]", "SELECT ...", "OK")))
            _, ctx = await _loto_ctx(WITH_CHANCE_MSGS[lang], lang)
        assert rts.await_args.kwargs["force_sql"] is True
        assert ctx["_chat_meta"]["phase"] == "SQL"
        stats.assert_not_called()

    @pytest.mark.asyncio
    async def test_chance_stats_stays_phase_1(self):
        """Non-régression point 3 : « stats du numéro chance 10 » reste en Phase 1."""
        stats_10 = {"numero": 10, "type": "chance", "derniere_sortie": None}
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch("services.chat_pipeline._detect_numero", side_effect=_detect_numero))
            stats = stack.enter_context(patch(
                "services.chat_pipeline.get_numero_stats", new_callable=AsyncMock, return_value=stats_10))
            stack.enter_context(patch(
                "services.chat_pipeline._format_stats_context", return_value="[DONNÉES TEMPS RÉEL]\nchance 10"))
            rts = stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                return_value=("[DONNÉES TEMPS RÉEL]\nchance 10", None, "N/A")))
            _, ctx = await _loto_ctx("stats du numéro chance 10")
        stats.assert_awaited_once_with(10, "chance")
        assert ctx["_chat_meta"]["phase"] == "1"
        assert rts.await_args.kwargs["force_sql"] is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGS)
    async def test_generation_with_forced_numbers_no_pair_block(self, lang):
        """Point 2 : Phase G avec numéros imposés → ni P-exact ni top 5 à côté de la grille."""
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            gen = _gen_patches(stack, "loto")
            single = stack.enter_context(patch(
                "services.chat_pipeline.get_single_pair", new_callable=AsyncMock))
            top5 = stack.enter_context(patch(
                "services.chat_pipeline.get_pair_correlations", new_callable=AsyncMock))
            stack.enter_context(patch(
                "services.chat_pipeline._generate_sql", new_callable=AsyncMock, return_value=None))
            _, ctx = await _loto_ctx(GEN_FORCED_MSGS[lang], lang)
        enr = ctx["_chat_meta"]["enrichment_context"]
        gen.assert_awaited_once()
        assert gen.await_args.kwargs["forced_nums"] == [22, 10]
        assert "[GRILLE GÉNÉRÉE PAR HYBRIDE]" in enr
        assert "[CORRÉLATIONS DE PAIRES" not in enr
        assert "INDISPONIBLE" not in enr
        single.assert_not_called()
        top5.assert_not_called()

    @pytest.mark.asyncio
    async def test_sql_exec_error_honest_guard(self):
        sql = ("SELECT COUNT(*) as ensemble FROM tirages WHERE (boule_1 = 22 OR boule_2 = 22 OR boule_3 = 22 "
               "OR boule_4 = 22 OR boule_5 = 22) AND numero_chance = 10")
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch(
                "services.chat_pipeline._generate_sql", new_callable=AsyncMock, return_value=sql))
            stack.enter_context(patch(
                "services.chat_pipeline._execute_safe_sql", new_callable=AsyncMock, return_value=None))
            _, ctx = await _loto_ctx(BALL_CHANCE_MSGS["fr"])
        assert ctx["_chat_meta"]["enrichment_context"].startswith("[RÉSULTAT SQL — INDISPONIBLE]")

    @pytest.mark.asyncio
    async def test_sql_ok_keeps_result(self):
        sql = ("SELECT COUNT(*) as ensemble FROM tirages WHERE (boule_1 = 22 OR boule_2 = 22 OR boule_3 = 22 "
               "OR boule_4 = 22 OR boule_5 = 22) AND numero_chance = 10")
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch(
                "services.chat_pipeline._generate_sql", new_callable=AsyncMock, return_value=sql))
            stack.enter_context(patch(
                "services.chat_pipeline._execute_safe_sql", new_callable=AsyncMock,
                return_value=[{"ensemble": 3}]))
            _, ctx = await _loto_ctx(BALL_CHANCE_MSGS["fr"])
        meta = ctx["_chat_meta"]
        assert meta["sql_status"] == "OK"
        assert "ensemble: 3" in meta["enrichment_context"]
        assert "INDISPONIBLE" not in meta["enrichment_context"]

    @pytest.mark.asyncio
    async def test_date_not_routed_to_phase_1_8697(self):
        """S6 : « Le loto du 26 octobre 2026 » → pas de stats du 26 (détecteur réel)."""
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch(
                "services.chat_pipeline._detect_numero", side_effect=_detect_numero))
            stats = stack.enter_context(patch(
                "services.chat_pipeline.get_numero_stats", new_callable=AsyncMock))
            stack.enter_context(patch(
                "services.chat_pipeline._generate_sql", new_callable=AsyncMock, return_value=None))
            _, ctx = await _loto_ctx("Le loto du 26 octobre 2026")
        stats.assert_not_called()
        assert ctx["_chat_meta"]["phase"] != "1"


# ═══════════════════════════════════════════════════════
# S2 — routage EuroMillions
# ═══════════════════════════════════════════════════════

class TestRoutingEM:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGS)
    async def test_pair_balls_em_6_langs(self, lang):
        em_pair = {**PAIR_22_10, "count": 9, "total_draws": 732, "total_pairs": 1225}
        with contextlib.ExitStack() as stack:
            _em_patches(stack)
            single = stack.enter_context(patch(
                "services.chat_pipeline_em.get_single_pair", new_callable=AsyncMock, return_value=em_pair))
            star = stack.enter_context(patch(
                "services.chat_pipeline_em.get_single_star_pair", new_callable=AsyncMock))
            _, ctx = await _em_ctx(PAIR_MSGS[lang], lang)
        enr = ctx["_chat_meta"]["enrichment_context"]
        assert "10 + 22 → 9 fois sur 732 tirages" in enr
        assert "étoiles non comptées" in enr
        single.assert_awaited_once_with(n1=22, n2=10)
        star.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGS)
    async def test_star_pair_em_6_langs(self, lang):
        with contextlib.ExitStack() as stack:
            _em_patches(stack)
            star = stack.enter_context(patch(
                "services.chat_pipeline_em.get_single_star_pair", new_callable=AsyncMock,
                return_value=STAR_PAIR_3_7))
            single = stack.enter_context(patch(
                "services.chat_pipeline_em.get_single_pair", new_callable=AsyncMock))
            top5 = stack.enter_context(patch(
                "services.chat_pipeline_em.get_star_pair_correlations", new_callable=AsyncMock))
            _, ctx = await _em_ctx(STAR_PAIR_MSGS[lang], lang)
        enr = ctx["_chat_meta"]["enrichment_context"]
        assert enr.startswith("[CORRÉLATIONS DE PAIRES — PAIRE D'ÉTOILES DEMANDÉE]")
        assert "3 + 7 → 21 fois" in enr
        star.assert_awaited_once_with(s1=3, s2=7)
        single.assert_not_called()
        top5.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("msgs", [TRIPLET_MSGS, BALL_STAR_MSGS])
    @pytest.mark.parametrize("lang", LANGS)
    async def test_triplet_and_ball_star_cede_to_sql_q3(self, msgs, lang):
        with contextlib.ExitStack() as stack:
            _em_patches(stack)
            single = stack.enter_context(patch(
                "services.chat_pipeline_em.get_single_pair", new_callable=AsyncMock))
            rts = stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                return_value=("[RÉSULTAT SQL]\nensemble: 1\n[/RÉSULTAT SQL]", "SELECT ...", "OK")))
            _, ctx = await _em_ctx(msgs[lang], lang)
        assert rts.await_args.kwargs["force_sql"] is True
        single.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGS)
    async def test_sql_failure_em_honest_guard(self, lang):
        with contextlib.ExitStack() as stack:
            _em_patches(stack)
            stack.enter_context(patch(
                "services.chat_pipeline_em._generate_sql_em", new_callable=AsyncMock, return_value=None))
            _, ctx = await _em_ctx(BALL_STAR_MSGS[lang], lang)
        enr = ctx["_chat_meta"]["enrichment_context"]
        assert enr.startswith("[RÉSULTAT SQL — INDISPONIBLE]")
        assert _COMBO_UNAVAILABLE_MESSAGES[lang] in enr

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGS)
    async def test_with_star_cedes_to_sql_q2(self, lang):
        """Point 3 : « le 22 avec l'étoile 3 ? » → SQL encadré, pas Phase 1."""
        with contextlib.ExitStack() as stack:
            _em_patches(stack, _detect_numero_em=(22, "boule"))
            stats = stack.enter_context(patch(
                "services.chat_pipeline_em.get_numero_stats", new_callable=AsyncMock))
            rts = stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                return_value=("[RÉSULTAT SQL]\nensemble: 5\n[/RÉSULTAT SQL]", "SELECT ...", "OK")))
            _, ctx = await _em_ctx(WITH_STAR_MSGS[lang], lang)
        assert rts.await_args.kwargs["force_sql"] is True
        stats.assert_not_called()

    @pytest.mark.asyncio
    async def test_em_generation_star_first_no_pair_block(self):
        """Point 2 (EM), message Jyppy : aucun bloc paire ni P-exact, quelle que soit l'issue de Phase G.

        NB défaut préexistant hors lot : _STAR_PATTERN (base_chat_detect_generation.py) lit
        « 3 et le 22 » comme étoiles → « Étoile hors plage : 22 » → [ERREUR GÉNÉRATION].
        """
        with contextlib.ExitStack() as stack:
            _em_patches(stack)
            _gen_patches(stack, "em")
            single = stack.enter_context(patch(
                "services.chat_pipeline_em.get_single_pair", new_callable=AsyncMock))
            star = stack.enter_context(patch(
                "services.chat_pipeline_em.get_single_star_pair", new_callable=AsyncMock))
            top5 = stack.enter_context(patch(
                "services.chat_pipeline_em.get_pair_correlations", new_callable=AsyncMock))
            rts = stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            _, ctx = await _em_ctx("génère 3 grilles avec l'étoile 3 et le 22")
        enr = ctx["_chat_meta"]["enrichment_context"]
        assert "[CORRÉLATIONS DE PAIRES" not in enr
        assert rts.await_args.kwargs["force_sql"] is False
        single.assert_not_called()
        star.assert_not_called()
        top5.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("msg", list(GEN_FORCED_MSGS.values()) + ["génère 3 grilles avec le 22 et l'étoile 3"])
    async def test_em_generation_with_forced_numbers_no_pair_block(self, msg):
        """Point 2 (EM) : génération avec numéros / étoile imposés → aucun bloc paire."""
        with contextlib.ExitStack() as stack:
            _em_patches(stack)
            gen = _gen_patches(stack, "em")
            single = stack.enter_context(patch(
                "services.chat_pipeline_em.get_single_pair", new_callable=AsyncMock))
            star = stack.enter_context(patch(
                "services.chat_pipeline_em.get_single_star_pair", new_callable=AsyncMock))
            top5 = stack.enter_context(patch(
                "services.chat_pipeline_em.get_pair_correlations", new_callable=AsyncMock))
            rts = stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            _, ctx = await _em_ctx(msg)
        enr = ctx["_chat_meta"]["enrichment_context"]
        gen.assert_awaited_once()
        assert "[GRILLE GÉNÉRÉE PAR HYBRIDE]" in enr
        assert "[CORRÉLATIONS DE PAIRES" not in enr
        assert rts.await_args.kwargs["force_sql"] is False
        single.assert_not_called()
        star.assert_not_called()
        top5.assert_not_called()

    @pytest.mark.asyncio
    async def test_em_generation_forced_star_extracted(self):
        with contextlib.ExitStack() as stack:
            _em_patches(stack)
            gen = _gen_patches(stack, "em")
            stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            await _em_ctx("génère 3 grilles avec le 22 et l'étoile 3")
        kw = gen.await_args.kwargs
        assert kw["n"] == 3
        assert kw["forced_nums"] == [22]
        assert kw["forced_etoiles"] == [3]

    @pytest.mark.asyncio
    async def test_em_balls_default_q6(self):
        with contextlib.ExitStack() as stack:
            _em_patches(stack)
            single = stack.enter_context(patch(
                "services.chat_pipeline_em.get_single_pair", new_callable=AsyncMock,
                return_value={**PAIR_22_10, "n1": 3, "n2": 7}))
            star = stack.enter_context(patch(
                "services.chat_pipeline_em.get_single_star_pair", new_callable=AsyncMock))
            await _em_ctx("le 3 et le 7 ensemble ?")
        single.assert_awaited_once_with(n1=3, n2=7)
        star.assert_not_called()


# ═══════════════════════════════════════════════════════
# S4 — prompts SQL (sémantique chance / étoiles, tirage complet)
# ═══════════════════════════════════════════════════════

_PROMPTS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")


def _read(*parts):
    with open(os.path.join(_PROMPTS, *parts), encoding="utf-8") as f:
        return f.read()


def test_prompt_sql_loto_chance_rule():
    p = _read("chatbot", "prompt_sql_generator.txt")
    assert "RÈGLE NUMÉRO CHANCE (CRITIQUE)" in p
    assert "N'ajoute JAMAIS numero_chance dans le bloc d'un numéro" in p
    assert "AND numero_chance = 10" in p
    assert "RÈGLE TIRAGE COMPLET" in p


@pytest.mark.parametrize("lang", LANGS)
def test_prompt_sql_em_rules_and_examples(lang):
    p = _read("em", lang, "prompt_sql_generator_em.txt")
    assert "boule_1..boule_5" in p
    # exemple paire d'étoiles (absent avant le lot en EN/ES/PT/DE/NL)
    assert "WHERE (etoile_1 = 3 OR etoile_2 = 3) AND (etoile_1 = 7 OR etoile_2 = 7)" in p
    # exemple boule + étoile
    assert "boule_5 = 22) AND (etoile_1 = 3 OR etoile_2 = 3)" in p
    # exemple triplet compté
    assert "SELECT COUNT(*) as ensemble FROM tirages_euromillions WHERE (boule_1 = 9" in p
    assert "boule_5 = 41)\n" in p.replace("\r\n", "\n")


@pytest.mark.parametrize("path", [("chatbot", "prompt_sql_generator.txt")]
                         + [("em", lang, "prompt_sql_generator_em.txt") for lang in LANGS])
def test_prompt_sql_no_partial_draw_select(path):
    lines = _read(*path).splitlines()
    assert not any(line.startswith("SELECT date_de_tirage FROM") for line in lines)
    assert not any("(SELECT date_de_tirage)" in line for line in lines)


# ═══════════════════════════════════════════════════════
# S7 — grille avec numéros imposés : la grille porte seule la réponse
# (régression staging 28/10 : Phase 1 sur le 22 à côté de la grille → contrôle 1 bloquait)
# ═══════════════════════════════════════════════════════

_GRID_REPLY = "Voici ta grille : 3 - 10 - 22 - 30 - 41, bonne chance !"
GEN_FORCED_FR_LOTO = [
    GEN_FORCED_MSGS["fr"],
    "génère une grille avec le 7",
    "fais-moi une grille avec le 22 et le chance 4",
]
GEN_FORCED_FR_EM = ["génère une grille avec le 22 et le 10", "une grille avec l'étoile 3"]
STATS_AND_GRID_MSG = "donne-moi les stats du 22 et fais-moi une grille"


def _check_1(ctx):
    from services.chat_pipeline_gemini import _check_sql_number_hallucination
    meta = ctx["_chat_meta"]
    return _check_sql_number_hallucination(meta["enrichment_context"], _GRID_REPLY, meta["phase"], "test")


class TestGenerationForcedNumbers:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("msg", list(GEN_FORCED_MSGS.values()) + GEN_FORCED_FR_LOTO[1:])
    async def test_loto_forced_grid_alone(self, msg):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch("services.chat_pipeline._detect_numero", side_effect=_detect_numero))
            gen = _gen_patches(stack, "loto")
            stats = stack.enter_context(patch(
                "services.chat_pipeline.get_numero_stats", new_callable=AsyncMock))
            stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            _, ctx = await _loto_ctx(msg)
        enr = ctx["_chat_meta"]["enrichment_context"]
        gen.assert_awaited_once()
        stats.assert_not_called()
        assert enr.startswith("[GRILLE GÉNÉRÉE PAR HYBRIDE]")
        assert "[DONNÉES TEMPS RÉEL" not in enr
        assert ctx["_chat_meta"]["phase"] == "G"
        assert _check_1(ctx) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("msg", GEN_FORCED_FR_LOTO)
    async def test_loto_forced_fr_skips_phase_1_and_sql(self, msg):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch("services.chat_pipeline._detect_numero", side_effect=_detect_numero))
            _gen_patches(stack, "loto")
            stats = stack.enter_context(patch(
                "services.chat_pipeline.get_numero_stats", new_callable=AsyncMock))
            rts = stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock))
            _, ctx = await _loto_ctx(msg)
        stats.assert_not_called()
        rts.assert_not_called()
        assert ctx["_chat_meta"]["sql_status"] == "N/A"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("msg", list(GEN_FORCED_MSGS.values()) + GEN_FORCED_FR_EM)
    async def test_em_forced_grid_alone(self, msg):
        with contextlib.ExitStack() as stack:
            _em_patches(stack)
            stack.enter_context(patch(
                "services.chat_pipeline_em._detect_numero_em", side_effect=_detect_numero_em))
            gen = _gen_patches(stack, "em")
            stats = stack.enter_context(patch(
                "services.chat_pipeline_em.get_numero_stats", new_callable=AsyncMock))
            stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            _, ctx = await _em_ctx(msg)
        enr = ctx["_chat_meta"]["enrichment_context"]
        gen.assert_awaited_once()
        stats.assert_not_called()
        assert enr.startswith("[GRILLE GÉNÉRÉE PAR HYBRIDE]")
        assert "[DONNÉES TEMPS RÉEL" not in enr
        assert ctx["_chat_meta"]["phase"] == "G"
        assert _check_1(ctx) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("game", ["loto", "em"])
    async def test_stats_and_grid_multi_action_unchanged(self, game):
        """Vraie multi-action : les stats du 22 restent injectées avant la grille."""
        mod = "services.chat_pipeline" if game == "loto" else "services.chat_pipeline_em"
        type_num = "principal" if game == "loto" else "boule"
        with contextlib.ExitStack() as stack:
            if game == "loto":
                _loto_patches(stack)
                stack.enter_context(patch(f"{mod}._detect_numero", side_effect=_detect_numero))
            else:
                _em_patches(stack)
                stack.enter_context(patch(f"{mod}._detect_numero_em", side_effect=_detect_numero_em))
            _gen_patches(stack, game)
            stats = stack.enter_context(patch(
                f"{mod}.get_numero_stats", new_callable=AsyncMock,
                return_value={"numero": 22, "type": type_num}))
            stack.enter_context(patch(
                f"{mod}.{'_format_stats_context' if game == 'loto' else '_format_stats_context_em'}",
                return_value="[DONNÉES TEMPS RÉEL — CHIFFRES EXACTS - Numéro 22]\nstats\n[/DONNÉES TEMPS RÉEL]"))
            stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            _, ctx = await (_loto_ctx(STATS_AND_GRID_MSG) if game == "loto" else _em_ctx(STATS_AND_GRID_MSG))
        enr = ctx["_chat_meta"]["enrichment_context"]
        stats.assert_awaited_once_with(22, type_num)
        assert ctx["_chat_meta"]["phase"] == "1"
        assert enr.index("[DONNÉES TEMPS RÉEL") < enr.index("[GRILLE GÉNÉRÉE PAR HYBRIDE]")
