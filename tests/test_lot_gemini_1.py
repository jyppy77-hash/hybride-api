"""
Lot Gemini 1 — socle presse : moins de faux blocages, aucune réponse chiffrée sans données,
la grille du moteur survit à un échec Gemini.

- G7  contrôle 1 : union de tous les blocs factuels (a), numéros du message ignorés (b),
      séquences suivantes en journal seul (c)
- G16 SQL tenté puis en échec (GEN_ERROR / TIMEOUT / EXEC_ERROR) → garde « indisponible »
- G5  repli grille déterministe 6 langues (stream, non-stream, blocage strict)
- G8  grilles saisies librement (6e numéro chance, 2 étoiles finales, EVAL 6 langues, garde combinaison)
- G12a Phase T : date complète sans mot-clé, JJ.MM.AAAA, « de » ES/PT
- G10 replis absents de l'historique, réponse recopiée → is_error

Base entièrement mockée : aucun accès DB, aucun appel Gemini.
"""

import asyncio
import contextlib
import logging
import time
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.base_chat_detect_generation import _detect_generation
from services.base_chat_detect_intent import _detect_grid_evaluation
from services.base_chat_detect_temporal import _detect_tirage, _has_tirage_keyword, _mask_dates
from services.base_chat_sql import _SQL_UNAVAILABLE_GUARD, _SQL_UNAVAILABLE_MESSAGES
from services.chat_detectors import _detect_grille
from services.chat_detectors_em_intent import _detect_grille_em
from services.chat_pipeline_gemini import (
    _NOCHUNKS_FALLBACK_I18N,
    _STRICT_BLOCK_FALLBACK_I18N,
    _check_sql_number_hallucination,
    build_gemini_contents,
    call_gemini_and_respond,
    stream_and_respond,
)
from services.chat_pipeline_shared import _format_grid_fallback, run_text_to_sql

LANGS = ["fr", "en", "es", "pt", "de", "nl"]

GRID_BLOCK = (
    "[GRILLE GÉNÉRÉE PAR HYBRIDE]\nNuméros : [3, 13, 24, 34, 44]\nNuméro Chance : 7\n"
    "Score de conformité : 80/100\n[/GRILLE GÉNÉRÉE PAR HYBRIDE]"
)
SQL_TOP5_BLOCK = (
    "[RÉSULTAT SQL — CHIFFRES EXACTS, NE PAS MODIFIER]\n"
    "numero: 7 | sorties: 131\nnumero: 13 | sorties: 128\nnumero: 49 | sorties: 127\n"
    "numero: 41 | sorties: 126\nnumero: 24 | sorties: 125\n[/RÉSULTAT SQL]"
)
STATS_BLOCK = (
    "[DONNÉES TEMPS RÉEL — CHIFFRES EXACTS - Numéro principal 8]\n"
    "Fréquence totale : 118 apparitions sur 1092 tirages (10.8%)\n[/DONNÉES TEMPS RÉEL]\n\n"
    "[RÉSULTAT TIRAGE — CHIFFRES EXACTS, NE PAS MODIFIER]\n"
    "Tirage du 10 octobre 2026 : 4 - 8 - 19 - 22 - 35 | Numéro Chance : 2\n[/RÉSULTAT TIRAGE]"
)

GRID_FALLBACK_LOTO = {
    "fr": "🎲 Grille HYBRIDE : 3 - 13 - 24 - 34 - 44 · Chance 7 (commentaire IA momentanément indisponible)",
    "en": "🎲 HYBRIDE grid: 3 - 13 - 24 - 34 - 44 · Lucky number 7 (AI commentary temporarily unavailable)",
    "es": "🎲 Combinación HYBRIDE: 3 - 13 - 24 - 34 - 44 · Número de la suerte 7 "
          "(comentario de la IA momentáneamente no disponible)",
    "pt": "🎲 Grelha HYBRIDE: 3 - 13 - 24 - 34 - 44 · Número da sorte 7 "
          "(comentário da IA momentaneamente indisponível)",
    "de": "🎲 HYBRIDE-Kombination: 3 - 13 - 24 - 34 - 44 · Glückszahl 7 (KI-Kommentar vorübergehend nicht verfügbar)",
    "nl": "🎲 HYBRIDE-combinatie: 3 - 13 - 24 - 34 - 44 · Geluksnummer 7 (AI-commentaar tijdelijk niet beschikbaar)",
}
GRID_FALLBACK_EM = {
    "fr": "🎲 Grille HYBRIDE : 3 - 15 - 22 - 41 - 48 · Étoiles 2 - 9 (commentaire IA momentanément indisponible)",
    "en": "🎲 HYBRIDE grid: 3 - 15 - 22 - 41 - 48 · Stars 2 - 9 (AI commentary temporarily unavailable)",
    "es": "🎲 Combinación HYBRIDE: 3 - 15 - 22 - 41 - 48 · Estrellas 2 - 9 "
          "(comentario de la IA momentáneamente no disponible)",
    "pt": "🎲 Grelha HYBRIDE: 3 - 15 - 22 - 41 - 48 · Estrelas 2 - 9 "
          "(comentário da IA momentaneamente indisponível)",
    "de": "🎲 HYBRIDE-Kombination: 3 - 15 - 22 - 41 - 48 · Sterne 2 - 9 (KI-Kommentar vorübergehend nicht verfügbar)",
    "nl": "🎲 HYBRIDE-combinatie: 3 - 15 - 22 - 41 - 48 · Sterren 2 - 9 (AI-commentaar tijdelijk niet beschikbaar)",
}


# ═══════════════════════════════════════════════════════
# G7 — contrôle 1
# ═══════════════════════════════════════════════════════

class TestCheck1:

    def test_8655_grid_after_sql_block_not_blocked(self):
        """(a) multi-action SQL top 5 + grille : la grille citée n'est pas inventée."""
        enr = SQL_TOP5_BLOCK + "\n\n" + GRID_BLOCK
        assert _check_sql_number_hallucination(enr, "Ta grille : 3 - 13 - 24 - 34 - 44", "SQL", "t") is None

    def test_8546_grid_after_stats_block_not_blocked(self):
        """(a) multi-action Phase 1 (stats + dernier tirage) + grille."""
        enr = STATS_BLOCK + "\n\n" + GRID_BLOCK
        assert _check_sql_number_hallucination(enr, "Grille : 3 - 13 - 24 - 34 - 44", "1", "t") is None

    def test_8452_user_grid_echoed_not_blocked(self):
        """(b) la grille saisie par l'utilisateur, recopiée, n'est pas une invention."""
        msg = "10 12 29 34 46 et le 8"
        resp = "Ta grille 10, 12, 29, 34, 46 avec le 8 : équilibrée."
        assert _check_sql_number_hallucination(STATS_BLOCK, resp, "1", "t") is not None
        assert _check_sql_number_hallucination(STATS_BLOCK, resp, "1", "t", user_message=msg) is None

    def test_real_invention_still_blocked(self):
        """Q18 — vraie invention reconstituée (ni dans le contexte, ni dans le message) : bloquée."""
        enr = SQL_TOP5_BLOCK + "\n\n" + GRID_BLOCK
        repl = _check_sql_number_hallucination(
            enr, "Le prochain tirage sera 5 - 16 - 27 - 38 - 47", "SQL", "t",
            user_message="donnez moi 5 numéros")
        assert repl is not None
        assert repl.startswith("Voici les données exactes")

    def test_extra_sequence_log_only(self, caplog):
        """(c) 2e séquence inventée : journalisée, jamais bloquante."""
        enr = SQL_TOP5_BLOCK + "\n\n" + GRID_BLOCK
        resp = "Grille 1 : 3 - 13 - 24 - 34 - 44\nGrille 2 : 5 - 16 - 27 - 38 - 47"
        with caplog.at_level(logging.WARNING):
            assert _check_sql_number_hallucination(enr, resp, "SQL", "t") is None
        assert "HALLUCINATION_INVENTED_EXTRA" in caplog.text
        assert "HALLUCINATION_INVENTED:" not in caplog.text

    def test_no_result_block_alone_skips(self):
        enr = "[RÉSULTAT SQL]\nAucun résultat trouvé pour cette requête."
        assert _check_sql_number_hallucination(enr, "Tirage 5 - 16 - 27 - 38 - 47", "SQL", "t") is None

    def test_phase_outside_scope_unchanged(self):
        assert _check_sql_number_hallucination(STATS_BLOCK, "5 - 16 - 27 - 38 - 47", "G", "t") is None


# ═══════════════════════════════════════════════════════
# G16 — SQL tenté puis en échec
# ═══════════════════════════════════════════════════════

async def _rts(generate=None, execute=None, gen_side_effect=None, data_signal=True, force_sql=False, lang="fr"):
    gen = AsyncMock(return_value=generate, side_effect=gen_side_effect)
    exe = AsyncMock(return_value=execute)
    return await run_text_to_sql(
        "fréquence du 7 en 2024", MagicMock(), "", [],
        generate_sql_fn=gen, validate_sql_fn=lambda s: True, ensure_limit_fn=lambda s: s,
        execute_sql_fn=exe, format_result_fn=lambda rows: "[RÉSULTAT SQL]\nok\n[/RÉSULTAT SQL]",
        max_per_session=10, log_prefix="[T]", force_sql=force_sql,
        has_data_signal_fn=lambda m: data_signal, continuation_mode=False,
        enrichment_context="", lang=lang,
    )


class TestSqlFailureGuard:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGS)
    async def test_gen_error_429_guard(self, lang):
        """8321 / 8335 : génération SQL en échec (429 → None) → garde, plus de réponse libre."""
        enr, _, status = await _rts(generate=None, lang=lang)
        assert status == "ERROR"
        assert enr == _SQL_UNAVAILABLE_GUARD + _SQL_UNAVAILABLE_MESSAGES[lang]

    @pytest.mark.asyncio
    async def test_exec_error_guard_not_no_result(self):
        """8346 : erreur d'exécution → garde « indisponible », plus « Aucun résultat »."""
        enr, _, status = await _rts(generate="SELECT 1 FROM tirages", execute=None)
        assert status == "ERROR"
        assert enr.startswith(_SQL_UNAVAILABLE_GUARD)
        assert "Aucun résultat" not in enr

    @pytest.mark.asyncio
    async def test_timeout_guard(self):
        enr, _, status = await _rts(gen_side_effect=asyncio.TimeoutError())
        assert status == "ERROR"
        assert enr.startswith(_SQL_UNAVAILABLE_GUARD)

    @pytest.mark.asyncio
    async def test_force_sql_without_data_signal_guard(self):
        enr, _, _ = await _rts(generate=None, data_signal=False, force_sql=True)
        assert enr.startswith(_SQL_UNAVAILABLE_GUARD)

    @pytest.mark.asyncio
    async def test_free_conversation_unchanged(self):
        """Pas de signal de données ni force_sql : SQL non tenté, aucune garde."""
        enr, _, status = await _rts(generate=None, data_signal=False)
        assert (enr, status) == ("", "N/A")

    @pytest.mark.asyncio
    async def test_no_sql_and_empty_unchanged(self):
        enr, _, status = await _rts(generate="NO_SQL")
        assert (enr, status) == ("", "NO_SQL")
        enr, _, status = await _rts(generate="SELECT 1 FROM tirages", execute=[])
        assert status == "EMPTY"
        assert "Aucun résultat" in enr


# ═══════════════════════════════════════════════════════
# G5 — repli grille
# ═══════════════════════════════════════════════════════

@pytest.mark.parametrize("lang", LANGS)
def test_grid_fallback_text_loto(lang):
    grids = [{"nums": [3, 13, 24, 34, 44], "chance": 7}]
    assert _format_grid_fallback(grids, "loto", lang) == GRID_FALLBACK_LOTO[lang]


@pytest.mark.parametrize("lang", LANGS)
def test_grid_fallback_text_em(lang):
    grids = [{"nums": [3, 15, 22, 41, 48], "etoiles": [2, 9]}]
    assert _format_grid_fallback(grids, "em", lang) == GRID_FALLBACK_EM[lang]


def test_grid_fallback_several_grids():
    grids = [{"nums": [1, 2, 3, 4, 5], "chance": 1}, {"nums": [6, 7, 8, 9, 10], "chance": 2}]
    assert _format_grid_fallback(grids, "loto", "fr") == (
        "🎲 Grille HYBRIDE 1 : 1 - 2 - 3 - 4 - 5 · Chance 1\n"
        "🎲 Grille HYBRIDE 2 : 6 - 7 - 8 - 9 - 10 · Chance 2\n"
        "(commentaire IA momentanément indisponible)"
    )


def _stream_ctx(grid_fallback="", strict=False, enrichment=GRID_BLOCK, phase="G"):
    return {
        "system_prompt": "sys", "contents": [{"role": "user", "parts": [{"text": "q"}]}],
        "mode": "chat", "insult_prefix": "", "history": [], "lang": "fr",
        "_http_client": MagicMock(), "gem_api_key": "",
        "_strict_hallucination_block": strict, "_grid_fallback": grid_fallback,
        "_chat_meta": {"phase": phase, "lang": "fr", "t0": time.monotonic(), "enrichment_context": enrichment},
        "_get_tirage_fn": None, "_game": "loto",
    }


async def _collect(gen):
    return [e async for e in gen]


def _raising_stream(exc):
    async def _s(*a, **kw):
        raise exc
        yield  # pragma: no cover
    return _s


async def _empty_stream(*a, **kw):
    return
    yield  # pragma: no cover


class TestGridFallback:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stream", [
        _empty_stream,
        _raising_stream(asyncio.TimeoutError()),
        _raising_stream(RuntimeError("Vertex 429")),
    ], ids=["no_chunk", "timeout", "exception"])
    async def test_stream_failure_keeps_grid(self, stream):
        with patch("services.chat_pipeline_gemini.log_from_meta"):
            events = await _collect(stream_and_respond(
                _stream_ctx(GRID_FALLBACK_LOTO["fr"]), "FB", "[T]", "loto", "fr", "q", "p", "chat",
                stream_fn=stream))
        text = "".join(events)
        assert "3 - 13 - 24 - 34 - 44 · Chance 7" in text
        assert "FB" not in text

    @pytest.mark.asyncio
    async def test_stream_circuit_open_keeps_grid(self):
        from services.circuit_breaker import CircuitOpenError
        with patch("services.chat_pipeline_gemini.log_from_meta"):
            events = await _collect(stream_and_respond(
                _stream_ctx(GRID_FALLBACK_LOTO["fr"]), "FB", "[T]", "loto", "fr", "q", "p", "chat",
                stream_fn=_raising_stream(CircuitOpenError("open"))))
        assert "3 - 13 - 24 - 34 - 44" in "".join(events)

    @pytest.mark.asyncio
    async def test_strict_block_in_phase_g_keeps_grid_q4(self):
        async def _s(*a, **kw):
            yield "Voici : 5 - 16 - 27 - 38 - 47"
        ctx = _stream_ctx(GRID_FALLBACK_LOTO["fr"], strict=True, enrichment=SQL_TOP5_BLOCK, phase="SQL")
        with patch("services.chat_pipeline_gemini.log_from_meta") as log:
            text = "".join(await _collect(stream_and_respond(
                ctx, "FB", "[T]", "loto", "fr", "q", "p", "chat", stream_fn=_s)))
        assert GRID_FALLBACK_LOTO["fr"] in text
        assert "5 - 16 - 27 - 38 - 47" not in text
        assert log.call_args.kwargs["error_detail"] == "StrictHallucinationBlock"

    @pytest.mark.asyncio
    async def test_without_grid_fallback_unchanged(self):
        with patch("services.chat_pipeline_gemini.log_from_meta"):
            text = "".join(await _collect(stream_and_respond(
                _stream_ctx(""), "FB", "[T]", "loto", "fr", "q", "p", "chat", stream_fn=_empty_stream)))
        assert _NOCHUNKS_FALLBACK_I18N["fr"] in text

    @pytest.mark.asyncio
    async def test_non_stream_circuit_open_keeps_grid(self):
        breaker = MagicMock(OPEN="open", state="open")
        with patch("services.chat_pipeline_gemini.log_from_meta"):
            out = await call_gemini_and_respond(
                _stream_ctx(GRID_FALLBACK_EM["fr"]), "FB", "[T]", "em", "fr", "q", "p", breaker=breaker)
        assert out["response"] == GRID_FALLBACK_EM["fr"]
        assert out["source"] == "fallback_circuit"

    @pytest.mark.asyncio
    async def test_non_stream_exception_keeps_grid_and_without_grid_unchanged(self):
        breaker = MagicMock(OPEN="open", state="closed")
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("services.chat_pipeline_gemini.log_from_meta"), \
                patch("services.chat_pipeline_gemini._get_client", return_value=client):
            out = await call_gemini_and_respond(
                _stream_ctx(GRID_FALLBACK_LOTO["fr"]), "FB", "[T]", "loto", "fr", "q", "p", breaker=breaker)
            assert out["response"] == GRID_FALLBACK_LOTO["fr"]
            out = await call_gemini_and_respond(
                _stream_ctx(""), "FB", "[T]", "loto", "fr", "q", "p", breaker=breaker)
            assert out["response"] == "FB"


# ═══════════════════════════════════════════════════════
# G10 — replis absents de l'historique, recopie comptée en erreur
# ═══════════════════════════════════════════════════════

class TestFallbackEcho:

    @pytest.mark.parametrize("lang", LANGS)
    def test_strict_and_nochunk_messages_not_sent_to_gemini(self, lang):
        hist = [
            MagicMock(role="user", content="10 12 29 34 46 et le 8"),
            MagicMock(role="assistant", content=_STRICT_BLOCK_FALLBACK_I18N[lang]),
            MagicMock(role="user", content="et alors ?"),
            MagicMock(role="assistant", content=_NOCHUNKS_FALLBACK_I18N[lang]),
            MagicMock(role="user", content="Audite cette grille"),
            MagicMock(role="assistant", content="Ta grille est équilibrée."),
        ]
        contents, _ = build_gemini_contents(hist, "suite", lambda m: None)
        texts = " ".join(p["text"] for c in contents for p in c["parts"])
        assert _STRICT_BLOCK_FALLBACK_I18N[lang] not in texts
        assert _NOCHUNKS_FALLBACK_I18N[lang] not in texts
        assert "Ta grille est équilibrée." in texts

    def test_game_fallback_not_sent_to_gemini(self):
        hist = [MagicMock(role="user", content="q"), MagicMock(role="assistant", content="FB du jeu"),
                MagicMock(role="user", content="q2"), MagicMock(role="assistant", content="ok")]
        contents, _ = build_gemini_contents(hist, "suite", lambda m: None, fallback_texts=("FB du jeu",))
        assert "FB du jeu" not in " ".join(p["text"] for c in contents for p in c["parts"])

    @pytest.mark.asyncio
    async def test_echoed_strict_message_is_error_8453(self):
        async def _s(*a, **kw):
            yield _STRICT_BLOCK_FALLBACK_I18N["fr"]
        with patch("services.chat_pipeline_gemini.log_from_meta") as log:
            await _collect(stream_and_respond(
                _stream_ctx("", enrichment="", phase="SQL"), "FB", "[T]", "loto", "fr", "q", "p", "chat",
                stream_fn=_s))
        assert log.call_args.kwargs["is_error"] is True
        assert log.call_args.kwargs["error_detail"] == "EchoedFallback"

    @pytest.mark.asyncio
    async def test_normal_answer_not_error(self):
        async def _s(*a, **kw):
            yield "Le 7 est sorti 131 fois."
        with patch("services.chat_pipeline_gemini.log_from_meta") as log:
            await _collect(stream_and_respond(
                _stream_ctx("", enrichment="", phase="Gemini"), "FB", "[T]", "loto", "fr", "q", "p", "chat",
                stream_fn=_s))
        assert log.call_args.kwargs["is_error"] is False


# ═══════════════════════════════════════════════════════
# G8 — grilles saisies librement
# ═══════════════════════════════════════════════════════

class TestFreeGrids:

    @pytest.mark.parametrize("msg", [
        "10 12 29 34 46 et le 8", "10 12 29 34 46 et 8", "10 12 29 34 46 + 8", "10, 12, 29, 34, 46, 8",
        "5 11 25 33 49 8", "10 12 29 34 46 et 8 etoile au loto", "10 12 29 34 46 étoile 8",
    ])
    def test_loto_sixth_number_is_chance(self, msg):
        nums, chance = _detect_grille(msg)
        assert chance == 8
        assert len(nums) == 5 and 8 not in nums

    def test_loto_bare_8498(self):
        assert _detect_grille("5 11 25 33 49 7") == ([5, 11, 25, 33, 49], 7)

    @pytest.mark.parametrize("msg", [
        "3 15 22 41 48 et 2 et 9", "3 15 22 41 48 y 2 y 9", "3 15 22 41 48 and 2 and 9",
        "3 15 22 41 48 e 2 e 9", "3 15 22 41 48 und 2 und 9", "3 15 22 41 48 en 2 en 9",
    ])
    def test_em_two_final_stars_6_langs(self, msg):
        assert _detect_grille_em(msg) == ([3, 15, 22, 41, 48], [2, 9])

    def test_em_bare_dashes_8411(self):
        assert _detect_grille_em("19-23-25-30-29-3-5") == ([19, 23, 25, 30, 29], [3, 5])

    @pytest.mark.parametrize("msg", [
        "le 10, 12, 29, 34, 46 et 8 sont sortis ensemble ?",
        "combien de fois 10 12 29 34 46 et 8 ?",
    ])
    def test_combination_question_stays_phase_p(self, msg):
        assert _detect_grille(msg) == (None, None)
        assert _detect_grille_em(msg.replace(" et 8", " et 2 et 9")) == (None, None)

    def test_existing_five_numbers_unchanged(self):
        assert _detect_grille("5 12 23 34 45 chance 3") == ([5, 12, 23, 34, 45], 3)
        assert _detect_grille("5 12 23 34 45") == ([5, 12, 23, 34, 45], None)
        assert _detect_grille_em("5 12 23 34 45 étoiles 2 et 9") == ([5, 12, 23, 34, 45], [2, 9])

    def test_date_is_not_a_chance(self):
        assert _detect_grille("3 15 22 41 48 pour le tirage du 4/11") == (None, None)
        assert _detect_grille("3 15 22 41 48 du 4 novembre") == (None, None)

    @pytest.mark.parametrize("loto_msg,em_msg", [
        ("fais-moi une grille avec 3 7 12 25 33 et 8", "génère une grille avec 3 15 22 41 48 et 2 et 9"),
        ("make me a grid with 3 7 12 25 33 and 8", "generate a grid with 3 15 22 41 48 and 2 and 9"),
        ("genera una combinación con 3 7 12 25 33 y 8", "genera una combinación con 3 15 22 41 48 y 2 y 9"),
        ("gera uma grelha com 3 7 12 25 33 e 8", "gera uma grelha com 3 15 22 41 48 e 2 e 9"),
        ("erstelle eine Kombination mit 3 7 12 25 33 und 8", "erstelle eine Kombination mit 3 15 22 41 48 und 2 und 9"),
        ("maak een combinatie met 3 7 12 25 33 en 8", "maak een combinatie met 3 15 22 41 48 en 2 en 9"),
    ])
    def test_generation_request_is_not_a_user_grid(self, loto_msg, em_msg):
        """Demande de génération : la règle 6e / 7e numéro ne crée pas de grille utilisateur (Phase 2)."""
        assert _detect_generation(loto_msg) and _detect_generation(em_msg)
        assert _detect_grille(loto_msg) == (None, None)
        assert _detect_grille_em(em_msg) == (None, None)

    def test_sixth_number_out_of_chance_range(self):
        assert _detect_grille("10 12 29 34 46 41") == (None, None)

    @pytest.mark.parametrize("msg", [
        "Audite cette grille 10 12 29 34 46 et 8 etoile au loto",
        "analyse ma grille 10 12 29 34 46 chance 8",
        "3 16 24 39 48 et 8 qu en pense tu",
        "10 12 29 34 46 8 t'en penses quoi ?",
        "what do you think 10 12 29 34 46 8",
        "¿qué te parece 10 12 29 34 46 8?",
        "o que achas 10 12 29 34 46 8",
        "was meinst du 10 12 29 34 46 8",
        "wat vind je 10 12 29 34 46 8",
    ])
    def test_eval_triggers_6_langs_loto(self, msg):
        res = _detect_grid_evaluation(msg, game="loto")
        assert res is not None
        assert res["chance"] == 8
        assert len(res["numeros"]) == 5

    def test_eval_em_final_stars(self):
        res = _detect_grid_evaluation("analyse ma grille 3 15 22 41 48 2 9", game="em")
        assert res == {"numeros": [3, 15, 22, 41, 48], "etoiles": [2, 9]}

    def test_eval_combination_guard(self):
        assert _detect_grid_evaluation("qu'en penses-tu, 10 12 29 sortent ensemble ?", game="loto") is None


# ═══════════════════════════════════════════════════════
# G12a — Phase T : date complète sans mot-clé, JJ.MM.AAAA, « de » ES/PT
# ═══════════════════════════════════════════════════════

PERIOD_MSGS = [
    "depuis le 1er janvier 2024 combien de fois le 22",
    "combien de fois le 22 depuis le 1er janvier 2024 ?",
    "entre le 1/1/2025 et le 30/6/2025 combien de fois le 22",
    "le 22 est sorti combien de fois entre le 1/1/2025 et le 30/6/2025 ?",
    "avant le 1er janvier 2024, le 22 sortait souvent ?",
    "à partir du 1er janvier 2024 le 22",
    "jusqu'au 30 juin 2025 le 22",
    "since January 1 2024 how often has 22 come out",
    "how many times 22 between 1/1/2025 and 30/6/2025",
    "before January 1, 2024 was 22 frequent?",
    "after March 15, 2025 the most frequent numbers",
    "desde el 1 de enero de 2024 cuántas veces el 22",
    "entre el 1/1/2025 y el 30/6/2025 el 22",
    "antes del 1 de enero de 2024 el 22",
    "desde 1 de janeiro de 2024 quantas vezes o 22",
    "entre 1/1/2025 e 30/6/2025 o 22",
    "depois de 15 de março de 2025 o 22",
    "seit 1.1.2024 wie oft die 22",
    "seit dem 1. Januar 2024 wie oft die 22",
    "zwischen 1.1.2025 und 30.6.2025 die 22",
    "vor dem 1. Januar 2024 die 22",
    "sinds 1 januari 2024 hoe vaak de 22",
    "tussen 1/1/2025 en 30/6/2025 de 22",
    "na 15 maart 2025 de 22",
]

class TestDrawDate:

    @pytest.mark.parametrize("msg,expected", [
        ("Le loto du 26 octobre 2026", date(2026, 10, 26)),
        ("l'euromillions du 24 octobre 2026", date(2026, 10, 24)),
        ("le tirage du 26.10.2026", date(2026, 10, 26)),
        ("26/10/2026 ?", date(2026, 10, 26)),
        ("el sorteo del 26 de octubre de 2026", date(2026, 10, 26)),
        ("o sorteio de 26 de outubro de 2026", date(2026, 10, 26)),
        ("die Ziehung vom 26. Oktober 2026", date(2026, 10, 26)),
        ("the draw of October 26, 2026", date(2026, 10, 26)),
        ("de trekking van 26 oktober 2026", date(2026, 10, 26)),
    ])
    def test_full_dates_6_langs(self, msg, expected):
        assert _detect_tirage(msg) == expected

    @pytest.mark.parametrize("msg", ["on se voit le 26 octobre", "rendez-vous le 26/10", "mercredi 23"])
    def test_no_year_no_keyword_unchanged(self, msg):
        assert _detect_tirage(msg) is None

    def test_decimal_not_a_date(self):
        assert _detect_tirage("le score est de 2.5") is None

    @pytest.mark.parametrize("msg", PERIOD_MSGS)
    def test_period_date_is_not_a_draw(self, msg):
        """Une date avec année introduite par une période borne une statistique : pas de Phase T."""
        assert _detect_tirage(msg) is None

    @pytest.mark.parametrize("msg", [
        "Le loto du 26 octobre 2026", "le tirage du 26.10.2026", "el sorteo del 26 de octubre de 2026",
        "o sorteio de 26 de outubro de 2026", "die Ziehung vom 26. Oktober 2026", "26/10/2026",
    ])
    def test_coherent_with_mask_dates(self, msg):
        """Toute date reconnue par la Phase T est masquée pour la Phase 1 (le 26 n'est pas un numéro)."""
        assert "26" not in _mask_dates(msg.lower())

    def test_keyword_helper(self):
        assert _has_tirage_keyword("le tirage du 26 octobre 2026")
        assert not _has_tirage_keyword("5 grilles pour l'euro million du 23 octobre 2026")


# ═══════════════════════════════════════════════════════
# Pipeline — G5, G16, G12a de bout en bout (détecteurs réels utiles, données mockées)
# ═══════════════════════════════════════════════════════

def _loto_patches(stack, **overrides):
    defaults = {
        "load_prompt": "sys", "_detect_insulte": None, "_detect_compliment": None,
        "_detect_salutation": False, "_detect_generation": False, "_detect_grid_evaluation": None,
        "_detect_argent": False, "_is_short_continuation": False, "_detect_prochain_tirage": False,
        "_detect_tirage": None, "_detect_grille": (None, None), "_detect_requete_complexe": None,
        "_detect_cooccurrence_high_n": False, "_detect_out_of_range": (None, None),
        "_detect_numero": (None, None), "_build_session_context": "",
    }
    defaults.update(overrides)
    for name, rv in defaults.items():
        stack.enter_context(patch(f"services.chat_pipeline.{name}", return_value=rv))
    stack.enter_context(patch("services.chat_pipeline._get_draw_count", new_callable=AsyncMock, return_value=1092))


def _gen_patches(stack):
    stack.enter_context(patch("services.chat_pipeline._detect_generation", side_effect=_detect_generation))
    stack.enter_context(patch("db_cloudsql.get_connection", side_effect=ConnectionError("mock")))
    return stack.enter_context(patch(
        "engine.hybride.generate_grids", new_callable=AsyncMock,
        return_value={"grids": [{"nums": [3, 13, 24, 34, 44], "chance": 7, "score": 80, "badges": []}]}))


async def _loto_ctx(message, lang="fr"):
    from services.chat_pipeline import _prepare_chat_context
    return await _prepare_chat_context(message, [], "loto", MagicMock(), lang=lang)


def _em_patches(stack):
    em = "services.chat_pipeline_em"
    defaults = {
        "load_prompt_em": "sys", "_detect_insulte": None, "_detect_compliment": None,
        "_detect_salutation": False, "_detect_generation": False, "_detect_grid_evaluation": None,
        "_detect_argent_em": False, "_detect_country_em": False, "_is_short_continuation": False,
        "_detect_prochain_tirage_em": False, "_detect_tirage": None, "_detect_grille_em": (None, None),
        "_detect_requete_complexe_em": None, "_detect_cooccurrence_high_n": False,
        "_detect_out_of_range_em": (None, None), "_detect_numero_em": (None, None),
        "_build_session_context_em": "",
    }
    for name, rv in defaults.items():
        stack.enter_context(patch(f"{em}.{name}", return_value=rv))
    stack.enter_context(patch("services.chat_pipeline._get_draw_count", new_callable=AsyncMock, return_value=732))


async def _em_ctx(message, lang="fr"):
    from services.chat_pipeline_em import _prepare_chat_context_em
    return await _prepare_chat_context_em(message, [], "euromillions", MagicMock(), lang=lang)


class TestPipeline:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang,msg", [
        ("fr", "génère une grille"), ("en", "generate a grid"), ("es", "genera una combinación"),
        ("pt", "gera uma grelha"), ("de", "generiere eine Kombination"), ("nl", "genereer een combinatie"),
    ])
    async def test_grid_fallback_in_ctx_6_langs(self, lang, msg):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            _gen_patches(stack)
            stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            _, ctx = await _loto_ctx(msg, lang)
        assert ctx["_grid_fallback"] == GRID_FALLBACK_LOTO[lang]

    @pytest.mark.asyncio
    async def test_no_generation_no_grid_fallback(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            _, ctx = await _loto_ctx("bonjour, comment ça marche ?")
        assert ctx["_grid_fallback"] == ""

    @pytest.mark.asyncio
    async def test_sql_failure_next_to_grid_drops_guard(self):
        """G16 + phase G : la garde « ne cite aucun chiffre » ne doit pas masquer la grille."""
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            _gen_patches(stack)
            stack.enter_context(patch("services.chat_pipeline._generate_sql", new_callable=AsyncMock,
                                      return_value=None))
            _, ctx = await _loto_ctx("make me a grid with 22 and 10", "en")
        enr = ctx["_chat_meta"]["enrichment_context"]
        assert ctx["_chat_meta"]["sql_status"] == "ERROR"
        assert "Données momentanément indisponibles" not in enr
        assert "[GRILLE GÉNÉRÉE PAR HYBRIDE]" in enr

    @pytest.mark.asyncio
    async def test_sql_failure_without_grid_guard(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch("services.chat_pipeline._generate_sql", new_callable=AsyncMock,
                                      return_value=None))
            _, ctx = await _loto_ctx("quelle est la fréquence du numéro 7 en 2024 ?")
        assert ctx["_chat_meta"]["enrichment_context"].startswith(_SQL_UNAVAILABLE_GUARD)

    @pytest.mark.asyncio
    async def test_dated_draw_goes_to_phase_t_8697(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch("services.chat_pipeline._detect_tirage", side_effect=_detect_tirage))
            tirage = stack.enter_context(patch(
                "services.chat_pipeline._get_tirage_data", new_callable=AsyncMock, return_value=None))
            stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            _, ctx = await _loto_ctx("Le loto du 26 octobre 2026")
        tirage.assert_awaited_once_with(date(2026, 10, 26))
        assert ctx["_chat_meta"]["phase"] == "T"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("game,msg", [
        ("loto", "fais-moi une grille avec 3 7 12 25 33 et 8"),
        ("loto", "make me a grid with 3 7 12 25 33 and 8"),
        ("em", "génère une grille avec 3 15 22 41 48 et 2 et 9"),
        ("em", "generate a grid with 3 15 22 41 48 and 2 and 9"),
    ])
    async def test_generation_with_six_or_seven_numbers_no_phase_2(self, game, msg):
        """G8 × Phase G : aucune analyse de grille utilisateur à côté d'une demande de génération."""
        from services.chat_detectors import _detect_grille as _real_loto
        from services.chat_detectors_em_intent import _detect_grille_em as _real_em
        mod = "services.chat_pipeline" if game == "loto" else "services.chat_pipeline_em"
        with contextlib.ExitStack() as stack:
            if game == "loto":
                _loto_patches(stack)
                stack.enter_context(patch(f"{mod}._detect_grille", side_effect=_real_loto))
            else:
                _em_patches(stack)
                stack.enter_context(patch(f"{mod}._detect_grille_em", side_effect=_real_em))
            stack.enter_context(patch(f"{mod}._detect_generation", side_effect=_detect_generation))
            stack.enter_context(patch("db_cloudsql.get_connection", side_effect=ConnectionError("mock")))
            analyze = stack.enter_context(patch(f"{mod}.analyze_grille_for_chat", new_callable=AsyncMock))
            stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            _, ctx = await (_loto_ctx(msg) if game == "loto" else _em_ctx(msg))
        analyze.assert_not_called()
        assert ctx["_chat_meta"]["phase"] != "2"
        assert "[ANALYSE DE GRILLE" not in ctx["_chat_meta"]["enrichment_context"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("game,msg,phase,nums,secondary", [
        ("loto", "10 12 29 34 46 et le 8", "2", [10, 12, 29, 34, 46], 8),
        ("loto", "analyse ma grille 3 7 12 25 33 et 8", "EVAL", [3, 7, 12, 25, 33], 8),
        ("loto", "what do you think 3 7 12 25 33 8", "EVAL", [3, 7, 12, 25, 33], 8),
        ("em", "3 15 22 41 48 et 2 et 9", "2", [3, 15, 22, 41, 48], [2, 9]),
        ("em", "analyse ma grille 3 15 22 41 48 et 2 et 9", "EVAL", [3, 15, 22, 41, 48], [2, 9]),
    ])
    async def test_user_grid_without_generation_still_analysed(self, game, msg, phase, nums, secondary):
        """G8 : sans demande de génération, la grille saisie (6e / 7e numéro) est bien analysée."""
        from services.base_chat_detect_intent import _detect_grid_evaluation as _real_eval
        from services.chat_detectors import _detect_grille as _real_loto
        from services.chat_detectors_em_intent import _detect_grille_em as _real_em
        mod = "services.chat_pipeline" if game == "loto" else "services.chat_pipeline_em"
        with contextlib.ExitStack() as stack:
            if game == "loto":
                _loto_patches(stack)
                stack.enter_context(patch(f"{mod}._detect_grille", side_effect=_real_loto))
            else:
                _em_patches(stack)
                stack.enter_context(patch(f"{mod}._detect_grille_em", side_effect=_real_em))
            stack.enter_context(patch(f"{mod}._detect_grid_evaluation", side_effect=_real_eval))
            stack.enter_context(patch(f"{mod}._detect_generation", side_effect=_detect_generation))
            analyze = stack.enter_context(patch(
                f"{mod}.analyze_grille_for_chat", new_callable=AsyncMock, return_value={"ok": True}))
            stack.enter_context(patch(
                f"{mod}.{'_format_grille_context' if game == 'loto' else '_format_grille_context_em'}",
                return_value="[ANALYSE DE GRILLE]\nok"))
            stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            _, ctx = await (_loto_ctx(msg) if game == "loto" else _em_ctx(msg))
        assert analyze.await_args.args[:2] == (nums, secondary)
        assert ctx["_chat_meta"]["phase"] == phase

    @pytest.mark.asyncio
    async def test_force_sql_failure_next_to_grid_nothing_reinjected(self, caplog):
        """G16 × force_sql : SQL tenté une seule fois, garde retirée, branche « force_sql » = journal seul."""
        import services.chat_pipeline_shared as sh
        real_rts = sh.run_text_to_sql
        calls = []

        async def _spy(*a, **kw):
            calls.append(kw["force_sql"])
            return await real_rts(*a, **kw)
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            _gen_patches(stack)
            stack.enter_context(patch("services.chat_pipeline_shared.run_text_to_sql", side_effect=_spy))
            stack.enter_context(patch("services.chat_pipeline._generate_sql", new_callable=AsyncMock,
                                      return_value=None))
            with caplog.at_level(logging.INFO):
                _, ctx = await _loto_ctx("génère une grille avec les numéros les plus sortis en 2024")
        enr = ctx["_chat_meta"]["enrichment_context"]
        assert calls == [True]
        assert "garde retiree" in caplog.text
        assert "Phase SQL echouee avec filtre temporel" in caplog.text
        assert enr.startswith("[GRILLE GÉNÉRÉE PAR HYBRIDE]")
        assert _SQL_UNAVAILABLE_GUARD not in enr
        assert ctx["_grid_fallback"].startswith("🎲 Grille HYBRIDE : 3 - 13 - 24 - 34 - 44")

    @pytest.mark.asyncio
    async def test_period_question_not_phase_t(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            stack.enter_context(patch("services.chat_pipeline._detect_tirage", side_effect=_detect_tirage))
            tirage = stack.enter_context(patch(
                "services.chat_pipeline._get_tirage_data", new_callable=AsyncMock, return_value=None))
            stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            _, ctx = await _loto_ctx("à partir du 1er janvier 2024 le 22")
        tirage.assert_not_called()
        assert ctx["_chat_meta"]["phase"] != "T"

    @pytest.mark.asyncio
    async def test_dated_generation_skips_phase_t_8546(self):
        with contextlib.ExitStack() as stack:
            _loto_patches(stack)
            _gen_patches(stack)
            stack.enter_context(patch("services.chat_pipeline._detect_tirage", side_effect=_detect_tirage))
            tirage = stack.enter_context(patch(
                "services.chat_pipeline._get_tirage_data", new_callable=AsyncMock, return_value=None))
            stack.enter_context(patch(
                "services.chat_pipeline_shared.run_text_to_sql", new_callable=AsyncMock,
                side_effect=lambda *a, **kw: (kw["enrichment_context"], None, "N/A")))
            _, ctx = await _loto_ctx("donne moi 5 grilles pour le loto du 26 octobre 2026")
        tirage.assert_not_called()
        assert "[GRILLE GÉNÉRÉE PAR HYBRIDE]" in ctx["_chat_meta"]["enrichment_context"]
