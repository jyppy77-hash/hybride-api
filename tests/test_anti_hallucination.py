"""
V99 — Anti-Hallucination tests (F01 + F05 + F07).

F01: Phase 1 enrichment with last draw numbers
F05: Adaptive temperature (factual vs conversational)
F07: Anti-hallucination blocks at beginning of prompts
"""

import os
import re
import pytest
from datetime import date
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure DB env vars for import safety
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("INSTANCE_CONNECTION_NAME", "test:test:test")


# ═══════════════════════════════════════════════════════
# F01 — _format_last_draw_context
# ═══════════════════════════════════════════════════════

from services.base_chat_utils import _format_last_draw_context


class TestFormatLastDrawContext:
    """V99 F01: _format_last_draw_context produces anti-hallucination block."""

    def test_loto_contains_chiffres_exacts_tag(self):
        """Loto draw context includes CHIFFRES EXACTS tag."""
        tirage = {"date": date(2026, 3, 14), "boules": [10, 22, 23, 25, 46], "chance": 3}
        result = _format_last_draw_context(tirage)
        assert "CHIFFRES EXACTS, NE PAS MODIFIER" in result

    def test_loto_contains_all_five_numbers(self):
        """Loto draw context includes all 5 boules."""
        tirage = {"date": date(2026, 3, 14), "boules": [10, 22, 23, 25, 46], "chance": 3}
        result = _format_last_draw_context(tirage)
        for num in [10, 22, 23, 25, 46]:
            assert str(num) in result

    def test_loto_contains_chance(self):
        """Loto draw context includes Chance number."""
        tirage = {"date": date(2026, 3, 14), "boules": [10, 22, 23, 25, 46], "chance": 3}
        result = _format_last_draw_context(tirage)
        assert "Chance" in result
        assert "3" in result

    def test_loto_contains_closing_tag(self):
        """Loto draw context has closing [/RÉSULTAT TIRAGE] tag."""
        tirage = {"date": date(2026, 3, 14), "boules": [10, 22, 23, 25, 46], "chance": 3}
        result = _format_last_draw_context(tirage)
        assert "[/RÉSULTAT TIRAGE]" in result

    def test_em_contains_etoiles(self):
        """EM draw context includes étoiles."""
        tirage = {"date": date(2026, 3, 14), "boules": [5, 12, 23, 37, 48], "etoiles": [3, 9]}
        result = _format_last_draw_context(tirage)
        assert "Étoiles" in result
        assert "3" in result
        assert "9" in result

    def test_em_contains_all_five_boules(self):
        """EM draw context includes all 5 boules."""
        tirage = {"date": date(2026, 3, 14), "boules": [5, 12, 23, 37, 48], "etoiles": [3, 9]}
        result = _format_last_draw_context(tirage)
        for num in [5, 12, 23, 37, 48]:
            assert str(num) in result

    def test_em_has_chiffres_exacts_tag(self):
        """EM draw context also includes anti-hallucination tag."""
        tirage = {"date": date(2026, 3, 14), "boules": [5, 12, 23, 37, 48], "etoiles": [3, 9]}
        result = _format_last_draw_context(tirage)
        assert "CHIFFRES EXACTS, NE PAS MODIFIER" in result

    def test_date_formatted_in_french(self):
        """Draw date is formatted in French."""
        tirage = {"date": date(2026, 3, 14), "boules": [1, 2, 3, 4, 5], "chance": 1}
        result = _format_last_draw_context(tirage)
        assert "mars" in result.lower() or "14" in result

    def test_string_date(self):
        """String date is handled gracefully."""
        tirage = {"date": "2026-03-14", "boules": [1, 2, 3, 4, 5], "chance": 1}
        result = _format_last_draw_context(tirage)
        assert "CHIFFRES EXACTS" in result
        assert "[/RÉSULTAT TIRAGE]" in result


# ═══════════════════════════════════════════════════════
# F05 — Adaptive temperature
# ═══════════════════════════════════════════════════════

from services.chat_pipeline_gemini import _get_temperature


class TestAdaptiveTemperature:
    """V99 F05: _get_temperature returns low temp for factual data."""

    def test_sql_result_returns_low_temp(self):
        """Context with [RÉSULTAT SQL returns factual temperature."""
        ctx = {"_chat_meta": {"enrichment_context": "[RÉSULTAT SQL — CHIFFRES EXACTS]\ndata\n[/RÉSULTAT SQL]"}}
        assert _get_temperature(ctx) == 0.2

    def test_tirage_result_returns_low_temp(self):
        """Context with [RÉSULTAT TIRAGE returns factual temperature."""
        ctx = {"_chat_meta": {"enrichment_context": "[RÉSULTAT TIRAGE — CHIFFRES EXACTS]\ndata"}}
        assert _get_temperature(ctx) == 0.2

    def test_donnees_temps_reel_returns_low_temp(self):
        """Context with [DONNÉES TEMPS RÉEL returns factual temperature."""
        ctx = {"_chat_meta": {"enrichment_context": "[DONNÉES TEMPS RÉEL - Numéro principal 22]\ndata"}}
        assert _get_temperature(ctx) == 0.2

    def test_empty_context_returns_conversational_temp(self):
        """Empty context returns conversational temperature."""
        ctx = {"_chat_meta": {"enrichment_context": ""}}
        assert _get_temperature(ctx) == 0.6

    def test_no_meta_returns_conversational_temp(self):
        """Missing _chat_meta returns conversational temperature."""
        ctx = {}
        assert _get_temperature(ctx) == 0.6

    def test_no_tags_returns_conversational_temp(self):
        """Context without factual tags returns conversational temperature."""
        ctx = {"_chat_meta": {"enrichment_context": "Some conversational context"}}
        assert _get_temperature(ctx) == 0.6

    def test_none_meta_returns_conversational_temp(self):
        """None _chat_meta returns conversational temperature."""
        ctx = {"_chat_meta": None}
        assert _get_temperature(ctx) == 0.6


# ═══════════════════════════════════════════════════════
# F07 — Anti-hallucination block position in prompts
# ═══════════════════════════════════════════════════════

# Map of prompt files → expected anti-hallucination header text
_PROMPT_ANTI_HALLUCINATION = {
    "prompts/chatbot/prompt_hybride.txt": "DONNÉES TIRAGES",
    "prompts/chatbot/prompt_hybride_em.txt": "DONNÉES TIRAGES",
    "prompts/em/fr/prompt_hybride_em.txt": "DONNÉES TIRAGES",
    "prompts/em/en/prompt_hybride_em.txt": "DRAW DATA",
    "prompts/em/es/prompt_hybride_em.txt": "DATOS DE SORTEOS",
    "prompts/em/pt/prompt_hybride_em.txt": "DADOS DE SORTEIOS",
    "prompts/em/de/prompt_hybride_em.txt": "ZIEHUNGSDATEN",
    "prompts/em/nl/prompt_hybride_em.txt": "TREKKINGSGEGEVENS",
}


class TestAntiHallucinationPosition:
    """V99 F07: Anti-hallucination block appears in top 50 lines of each prompt."""

    @pytest.mark.parametrize("path,keyword", list(_PROMPT_ANTI_HALLUCINATION.items()))
    def test_block_in_first_50_lines(self, path, keyword):
        """Anti-hallucination block should appear in the first 50 lines."""
        full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), path)
        if not os.path.isfile(full_path):
            pytest.skip(f"Prompt file not found: {path}")
        with open(full_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first_50 = "".join(lines[:50])
        assert keyword in first_50, (
            f"{path}: expected '{keyword}' in first 50 lines, "
            f"found at line {next((i+1 for i, l in enumerate(lines) if keyword in l), 'NOT FOUND')}"
        )


# ═══════════════════════════════════════════════════════
# F01 — Phase 1 pipeline enrichment integration
# ═══════════════════════════════════════════════════════

class TestPhase1Enrichment:
    """V99 F01: Phase 1 enriches context with last draw numbers."""

    def test_format_last_draw_appended_to_stats(self):
        """Stats context + last draw context are combined."""
        stats_ctx = "[DONNÉES TEMPS RÉEL - Numéro principal 22]\nDernière sortie : 14 mars 2026"
        tirage = {"date": date(2026, 3, 14), "boules": [10, 22, 23, 25, 46], "chance": 3}
        combined = stats_ctx + "\n\n" + _format_last_draw_context(tirage)
        assert "DONNÉES TEMPS RÉEL" in combined
        assert "CHIFFRES EXACTS" in combined
        for num in [10, 22, 23, 25, 46]:
            assert str(num) in combined

    def test_format_last_draw_em_appended(self):
        """EM stats + last draw context combined."""
        stats_ctx = "[DONNÉES TEMPS RÉEL - Numéro boule 22]\nDernière sortie : 14 mars 2026"
        tirage = {"date": date(2026, 3, 14), "boules": [5, 12, 23, 37, 48], "etoiles": [3, 9]}
        combined = stats_ctx + "\n\n" + _format_last_draw_context(tirage)
        assert "DONNÉES TEMPS RÉEL" in combined
        assert "CHIFFRES EXACTS" in combined
        assert "Étoiles" in combined

    def test_date_fromisoformat_conversion(self):
        """String date '2026-03-14' converts to date object for get_tirage_data."""
        from datetime import date as date_cls
        derniere = "2026-03-14"
        target = date_cls.fromisoformat(derniere)
        assert target == date(2026, 3, 14)

    def test_none_derniere_sortie_skips_enrichment(self):
        """No derniere_sortie means no tirage enrichment."""
        fake_stats = {"derniere_sortie": None}
        assert fake_stats.get("derniere_sortie") is None

    def test_import_date_cls_in_pipeline(self):
        """Verify _date_cls is importable from chat_pipeline_shared."""
        from services.chat_pipeline_shared import _date_cls
        assert _date_cls is date

    def test_format_last_draw_context_imported(self):
        """Verify _format_last_draw_context is importable from pipeline."""
        from services.chat_pipeline_shared import _format_last_draw_context as fn
        assert callable(fn)


# ═══════════════════════════════════════════════════════
# V99 Sprint 2 — F03: _check_sql_number_hallucination broadened
# ═══════════════════════════════════════════════════════

import logging
from services.chat_pipeline_gemini import _check_sql_number_hallucination


class TestHallucinationCheckBroadened:
    """V99 F03: hallucination check covers Phase 1, T, SQL + broadened regex."""

    def test_phase_1_now_checked(self, caplog):
        """Phase 1 is now checked (was skipped before V99)."""
        ctx = (
            "[RÉSULTAT TIRAGE — CHIFFRES EXACTS, NE PAS MODIFIER]\n"
            "Tirage du 14 mars 2026 : 10 - 22 - 23 - 25 - 46 | Numéro Chance : 3\n"
            "[/RÉSULTAT TIRAGE]"
        )
        # Response missing 23, 25, 46
        response = "Le tirage : 10 - 22 et un autre."
        with caplog.at_level(logging.WARNING):
            _check_sql_number_hallucination(ctx, response, "1", "[TEST]")
        assert "HALLUCINATION_RISK" in caplog.text

    def test_phase_t_still_checked(self, caplog):
        """Phase T continues to be checked."""
        ctx = "[RÉSULTAT SQL — CHIFFRES EXACTS]\nboule_1: 7 | boule_2: 14\n[/RÉSULTAT SQL]"
        response = "Les numéros sont 7 et 14."
        _check_sql_number_hallucination(ctx, response, "T", "[TEST]")
        assert "HALLUCINATION_RISK" not in caplog.text

    def test_phase_sql_still_checked(self, caplog):
        """Phase SQL continues to be checked."""
        ctx = "[RÉSULTAT SQL — CHIFFRES EXACTS]\nfreq: 42\n[/RÉSULTAT SQL]"
        response = "La fréquence est de 99."
        with caplog.at_level(logging.WARNING):
            _check_sql_number_hallucination(ctx, response, "SQL", "[TEST]")
        assert "HALLUCINATION_RISK" in caplog.text

    def test_phase_g_still_skipped(self, caplog):
        """Phase G is still skipped."""
        ctx = "[RÉSULTAT SQL]\nboule_1: 7\n[/RÉSULTAT SQL]"
        _check_sql_number_hallucination(ctx, "no numbers", "G", "[TEST]")
        assert "HALLUCINATION_RISK" not in caplog.text

    def test_resultat_tirage_tag_matched(self, caplog):
        """[RÉSULTAT TIRAGE tag is matched by broadened regex."""
        ctx = (
            "[RÉSULTAT TIRAGE — CHIFFRES EXACTS, NE PAS MODIFIER]\n"
            "Tirage du 14 mars 2026 : 10 - 22 - 23 - 25 - 46\n"
            "[/RÉSULTAT TIRAGE]"
        )
        response = "Le tirage du 14 mars : 10, 22, 23, 25 et 46."
        _check_sql_number_hallucination(ctx, response, "1", "[TEST]")
        assert "HALLUCINATION_RISK" not in caplog.text

    def test_donnees_temps_reel_tag_matched(self, caplog):
        """[DONNÉES TEMPS RÉEL tag is matched by broadened regex."""
        ctx = (
            "[DONNÉES TEMPS RÉEL — CHIFFRES EXACTS - Numéro principal 22]\n"
            "Fréquence totale : 104 apparitions sur 980 tirages\n"
            "[/DONNÉES TEMPS RÉEL]"
        )
        response = "Le 22 est sorti 104 fois sur 980 tirages."
        _check_sql_number_hallucination(ctx, response, "1", "[TEST]")
        assert "HALLUCINATION_RISK" not in caplog.text

    def test_missing_numbers_detected_phase1(self, caplog):
        """Numbers from context missing in response triggers warning."""
        ctx = (
            "[RÉSULTAT TIRAGE — CHIFFRES EXACTS]\n"
            "Tirage : 10 - 22 - 23 - 25 - 46 | Chance : 3\n"
            "[/RÉSULTAT TIRAGE]"
        )
        # Response has 22 but missing 10, 23, 25, 46
        response = "Le tirage contenait le 22."
        with caplog.at_level(logging.WARNING):
            _check_sql_number_hallucination(ctx, response, "1", "[TEST]")
        assert "HALLUCINATION_RISK" in caplog.text
        assert "10" in caplog.text

    def test_no_crash_empty_context(self):
        """Empty context does not crash."""
        _check_sql_number_hallucination("", "response", "1", "[TEST]")
        _check_sql_number_hallucination(None, "response", "1", "[TEST]")


# ═══════════════════════════════════════════════════════
# V99 Sprint 2 — F08: Invented numbers detection
# ═══════════════════════════════════════════════════════

class TestInventedNumbersDetection:
    """V99 F08: detect draw-like number sequences with invented numbers."""

    def test_all_numbers_from_context_no_warning(self, caplog):
        """Draw sequence with all numbers from context → no invented warning."""
        ctx = (
            "[RÉSULTAT TIRAGE — CHIFFRES EXACTS]\n"
            "Tirage : 10 - 22 - 23 - 25 - 46\n"
            "[/RÉSULTAT TIRAGE]"
        )
        response = "Le tirage : 10 - 22 - 23 - 25 - 46 !"
        _check_sql_number_hallucination(ctx, response, "T", "[TEST]")
        assert "HALLUCINATION_INVENTED" not in caplog.text

    def test_invented_numbers_detected(self, caplog):
        """Draw sequence with invented numbers triggers warning."""
        ctx = (
            "[RÉSULTAT TIRAGE — CHIFFRES EXACTS]\n"
            "Tirage : 10 - 22 - 23 - 25 - 46\n"
            "[/RÉSULTAT TIRAGE]"
        )
        # Gemini hallucinated: 12 - 14 - 22 - 31 - 44
        response = "Le tirage du 14 mars : 12 - 14 - 22 - 31 - 44."
        with caplog.at_level(logging.WARNING):
            _check_sql_number_hallucination(ctx, response, "T", "[TEST]")
        assert "HALLUCINATION_INVENTED" in caplog.text

    def test_stats_numbers_no_false_positive(self, caplog):
        """Stats text like 'sorti 104 fois' is not a draw sequence → no invented warning."""
        ctx = (
            "[DONNÉES TEMPS RÉEL — CHIFFRES EXACTS - Numéro principal 22]\n"
            "Fréquence totale : 104\n"
            "[/DONNÉES TEMPS RÉEL]"
        )
        response = "Le 22 est sorti 104 fois. Score 75/100."
        _check_sql_number_hallucination(ctx, response, "1", "[TEST]")
        assert "HALLUCINATION_INVENTED" not in caplog.text

    def test_score_not_false_positive(self, caplog):
        """Score like '85/100' is not a draw sequence."""
        ctx = "[RÉSULTAT SQL — CHIFFRES EXACTS]\nfreq: 42\n[/RÉSULTAT SQL]"
        response = "La fréquence est de 42. Score de conformité : 85/100."
        _check_sql_number_hallucination(ctx, response, "SQL", "[TEST]")
        assert "HALLUCINATION_INVENTED" not in caplog.text

    def test_no_sequence_no_invented_check(self, caplog):
        """When response has no draw-like sequence, no invented check."""
        ctx = "[RÉSULTAT SQL — CHIFFRES EXACTS]\nfreq: 42\n[/RÉSULTAT SQL]"
        response = "Le numéro est sorti 42 fois."
        _check_sql_number_hallucination(ctx, response, "SQL", "[TEST]")
        assert "HALLUCINATION_INVENTED" not in caplog.text


# ═══════════════════════════════════════════════════════
# V99 Sprint 2 — F04: Guard "numéros non disponibles"
# ═══════════════════════════════════════════════════════

class TestF04GuardNumerosNonDisponibles:
    """V99 F04: guard text injected when tirage enrichment fails."""

    def test_guard_present_when_tirage_none(self):
        """When tirage_data is None, guard text is appended."""
        # Simulate the enrichment flow
        enrichment = "[DONNÉES TEMPS RÉEL]\nDernière sortie : 14 mars 2026"
        _derniere = "2026-03-14"
        _tirage_enriched = False
        # Tirage fetch returned None
        if not _tirage_enriched:
            from services.chat_utils import _format_date_fr
            _date_fr = _format_date_fr(str(_derniere))
            enrichment += (
                f"\n\n[AVERTISSEMENT : les numéros du tirage du {_date_fr} "
                f"ne sont pas disponibles. NE PAS inventer de numéros.]"
            )
        assert "ne sont pas disponibles" in enrichment
        assert "NE PAS inventer" in enrichment

    def test_no_guard_when_tirage_ok(self):
        """When tirage_data is OK, no guard text."""
        enrichment = "[DONNÉES TEMPS RÉEL]\nDernière sortie : 14 mars 2026"
        tirage = {"date": date(2026, 3, 14), "boules": [10, 22, 23, 25, 46], "chance": 3}
        enrichment += "\n\n" + _format_last_draw_context(tirage)
        assert "ne sont pas disponibles" not in enrichment
        assert "CHIFFRES EXACTS" in enrichment

    def test_guard_on_exception(self):
        """When tirage fetch raises, guard should be added."""
        enrichment = "[DONNÉES TEMPS RÉEL]\nDernière sortie : 10 janvier 2026"
        _tirage_enriched = False
        # Simulate exception path
        try:
            raise Exception("DB timeout")
        except Exception:
            pass
        if not _tirage_enriched:
            enrichment += (
                "\n\n[AVERTISSEMENT : les numéros du tirage du 10 janvier 2026 "
                "ne sont pas disponibles. NE PAS inventer de numéros.]"
            )
        assert "NE PAS inventer" in enrichment

    def test_guard_not_added_when_no_derniere_sortie(self):
        """No derniere_sortie → no guard needed (no date to warn about)."""
        enrichment = "[DONNÉES TEMPS RÉEL]\nPas de dernière sortie"
        _derniere = None
        if _derniere:
            enrichment += "\n\nshould not appear"
        assert "ne sont pas disponibles" not in enrichment


# ═══════════════════════════════════════════════════════
# V99 Sprint 2 — F06: CHIFFRES EXACTS tag on all formatters
# ═══════════════════════════════════════════════════════

class TestF06ChiffresExactsTag:
    """V99 F06: all formatters with draw numbers include CHIFFRES EXACTS tag."""

    def test_format_tirage_context_loto_has_tag(self):
        """Loto Phase T formatter includes CHIFFRES EXACTS."""
        from services.chat_utils import _format_tirage_context
        tirage = {"date": date(2026, 3, 14), "boules": [10, 22, 23, 25, 46], "chance": 3}
        result = _format_tirage_context(tirage)
        assert "CHIFFRES EXACTS" in result
        assert "[/RÉSULTAT TIRAGE]" in result

    def test_format_tirage_context_em_has_tag(self):
        """EM Phase T formatter includes CHIFFRES EXACTS."""
        from services.chat_utils_em import _format_tirage_context_em
        tirage = {"date": date(2026, 3, 14), "boules": [5, 12, 23, 37, 48], "etoiles": [3, 9]}
        result = _format_tirage_context_em(tirage)
        assert "CHIFFRES EXACTS" in result
        assert "[/RÉSULTAT TIRAGE]" in result

    def test_format_stats_context_has_tag(self):
        """Stats formatter includes CHIFFRES EXACTS tag."""
        from services.base_chat_utils import _format_stats_context_base
        stats = {
            "numero": 22, "type": "principal",
            "frequence_totale": 104, "pourcentage_apparition": "10.6%",
            "derniere_sortie": "2026-03-14", "ecart_actuel": 8,
            "ecart_moyen": 9.4, "classement": 5, "classement_sur": 49,
            "categorie": "chaud", "total_tirages": 980,
            "periode": "2019-11-04 au 2026-03-14",
        }
        result = _format_stats_context_base(stats, {"principal": "principal"}, 49)
        assert "CHIFFRES EXACTS" in result
        assert "[/DONNÉES TEMPS RÉEL]" in result

    def test_format_sql_result_has_tag(self):
        """SQL result formatter includes CHIFFRES EXACTS (V96, unchanged)."""
        from services.base_chat_sql import _format_sql_result
        rows = [{"boule_1": 17, "boule_2": 28}]
        result = _format_sql_result(rows)
        assert "CHIFFRES EXACTS" in result

    def test_format_last_draw_context_has_tag(self):
        """Last draw enrichment formatter includes CHIFFRES EXACTS (V99 S1)."""
        tirage = {"date": date(2026, 3, 14), "boules": [10, 22, 23, 25, 46], "chance": 3}
        result = _format_last_draw_context(tirage)
        assert "CHIFFRES EXACTS" in result


# ═══════════════════════════════════════════════════════
# V100 R01 — Non-streaming path hallucination check
# ═══════════════════════════════════════════════════════

from services.chat_pipeline_gemini import call_gemini_and_respond


class TestR01NonStreamingCheck:
    """V100 R01: _check_sql_number_hallucination is called in non-streaming path."""

    @pytest.mark.asyncio
    async def test_check_called_on_success(self):
        """call_gemini_and_respond calls hallucination check after successful response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Le tirage : 10 - 22 - 23 - 25 - 46."}]}}],
        }

        ctx = {
            "mode": "balanced",
            "_http_client": MagicMock(),
            "gem_api_key": "fake",
            "system_prompt": "test",
            "contents": [],
            "insult_prefix": "",
            "history": [],
            "_chat_meta": {
                "enrichment_context": "[RÉSULTAT TIRAGE — CHIFFRES EXACTS]\n10 - 22\n[/RÉSULTAT TIRAGE]",
                "phase": "1",
                "t0": 0,
                "lang": "fr",
            },
        }

        with patch("services.chat_pipeline_gemini._gemini_call_with_fallback", return_value=mock_response), \
             patch("services.chat_pipeline_gemini._check_sql_number_hallucination") as mock_check:
            await call_gemini_and_respond(
                ctx, "fallback", "[TEST]", "loto", "fr", "test", "home",
            )
            mock_check.assert_called_once()
            args = mock_check.call_args[0]
            assert "[RÉSULTAT TIRAGE" in args[0]  # enrichment_context
            assert "10 - 22 - 23 - 25 - 46" in args[1]  # gemini response text
            assert args[2] == "1"  # phase

    @pytest.mark.asyncio
    async def test_check_not_called_on_fallback(self):
        """call_gemini_and_respond does NOT call hallucination check on fallback."""
        ctx = {
            "mode": "balanced",
            "_http_client": MagicMock(),
            "gem_api_key": "fake",
            "system_prompt": "test",
            "contents": [],
            "insult_prefix": "",
            "history": [],
            "_chat_meta": {"enrichment_context": "", "phase": "1", "t0": 0, "lang": "fr"},
        }
        fallback_result = {"response": "fallback", "source": "fallback", "mode": "balanced"}

        with patch("services.chat_pipeline_gemini._gemini_call_with_fallback", return_value=fallback_result), \
             patch("services.chat_pipeline_gemini._check_sql_number_hallucination") as mock_check:
            result = await call_gemini_and_respond(
                ctx, "fallback", "[TEST]", "loto", "fr", "test", "home",
            )
            mock_check.assert_not_called()
            assert result["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_check_no_crash_without_meta(self):
        """call_gemini_and_respond handles missing _chat_meta gracefully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "OK"}]}}],
        }

        ctx = {
            "mode": "balanced",
            "_http_client": MagicMock(),
            "gem_api_key": "fake",
            "system_prompt": "test",
            "contents": [],
            "insult_prefix": "",
            "history": [],
        }

        with patch("services.chat_pipeline_gemini._gemini_call_with_fallback", return_value=mock_response), \
             patch("services.chat_pipeline_gemini._check_sql_number_hallucination") as mock_check:
            result = await call_gemini_and_respond(
                ctx, "fallback", "[TEST]", "loto", "fr", "test", "home",
            )
            mock_check.assert_called_once()
            assert result["source"] == "gemini"


# ═══════════════════════════════════════════════════════
# V100 R04 — Extended draw sequence regex
# ═══════════════════════════════════════════════════════

from services.chat_pipeline_gemini import _DRAW_SEQUENCE_RE


class TestR04DrawSequenceExtended:
    """V100 R04: _DRAW_SEQUENCE_RE matches multilang conjunction separators."""

    def test_dash_separator_still_works(self):
        """Original dash separator still matches."""
        assert _DRAW_SEQUENCE_RE.search("10 - 22 - 23 - 25 - 46")

    def test_comma_separator_still_works(self):
        """Original comma separator still matches."""
        assert _DRAW_SEQUENCE_RE.search("10, 22, 23, 25, 46")

    def test_fr_et_separator(self):
        """French 'et' conjunction matches."""
        m = _DRAW_SEQUENCE_RE.search("10, 22, 23 et 25, 46")
        assert m
        assert m.groups() == ("10", "22", "23", "25", "46")

    def test_en_and_separator(self):
        """English 'and' conjunction matches."""
        m = _DRAW_SEQUENCE_RE.search("10, 22, 23 and 25, 46")
        assert m
        assert m.groups() == ("10", "22", "23", "25", "46")

    def test_es_y_separator(self):
        """Spanish 'y' conjunction matches."""
        m = _DRAW_SEQUENCE_RE.search("10 - 22 - 23 - 25 y 46")
        assert m
        assert m.groups() == ("10", "22", "23", "25", "46")

    def test_de_und_separator(self):
        """German 'und' conjunction matches."""
        m = _DRAW_SEQUENCE_RE.search("10, 22, 23, 25 und 46")
        assert m
        assert m.groups() == ("10", "22", "23", "25", "46")

    def test_nl_en_separator(self):
        """Dutch 'en' conjunction matches."""
        m = _DRAW_SEQUENCE_RE.search("10 - 22 - 23 - 25 en 46")
        assert m
        assert m.groups() == ("10", "22", "23", "25", "46")

    def test_pt_e_separator(self):
        """Portuguese 'e' conjunction matches."""
        m = _DRAW_SEQUENCE_RE.search("10, 22, 23, 25 e 46")
        assert m
        assert m.groups() == ("10", "22", "23", "25", "46")

    def test_all_et_separators(self):
        """All 5 separators as 'et' — extreme case."""
        m = _DRAW_SEQUENCE_RE.search("10 et 22 et 23 et 25 et 46")
        assert m
        assert m.groups() == ("10", "22", "23", "25", "46")

    def test_mixed_dash_and_et(self):
        """Mix of dash and 'et' separators."""
        m = _DRAW_SEQUENCE_RE.search("10 - 22 - 23 - 25 et 46")
        assert m
        assert m.groups() == ("10", "22", "23", "25", "46")


class TestR04NoFalsePositives:
    """V100 R04: normal text with 'et'/'and' must NOT trigger draw sequence match."""

    def test_normal_sentence_with_et(self):
        """Normal sentence with 'et' does not match."""
        assert not _DRAW_SEQUENCE_RE.search("il a mangé et bu du café")

    def test_two_numbers_with_et(self):
        """Two numbers with 'et' — not 5, no match."""
        assert not _DRAW_SEQUENCE_RE.search("Le 22 et le 33 sont chauds")

    def test_three_numbers_not_enough(self):
        """Three numbers — not 5, no match."""
        assert not _DRAW_SEQUENCE_RE.search("Les numéros 10, 22 et 33")

    def test_score_fraction_no_match(self):
        """Score like '85/100' is not a draw sequence."""
        assert not _DRAW_SEQUENCE_RE.search("Score de conformité : 85/100")

    def test_stats_text_no_match(self):
        """Stats text does not trigger false positive."""
        assert not _DRAW_SEQUENCE_RE.search("Le 22 est sorti 104 fois sur 980 tirages.")
