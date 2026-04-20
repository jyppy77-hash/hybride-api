"""
V126 Sous-phase 3.5/5 — Phase 0 post-hoc draw-date reapply (option 3.5-A).

Test phare : `test_bug_28_03_2026_F01_phase0_reapply` reproduit le bug
terrain du 19/04/2026 (admin log 19:05:54) et vérifie que V126 3.5-A
corrige la réponse avec le vrai tirage via DB re-query.

Scope : option A retenue (post-hoc + DB re-query). Remplacement effectif
sur path non-stream, log-only sur path streaming.
"""

from datetime import date
import logging
from unittest.mock import AsyncMock

import pytest

from services.chat_pipeline_gemini import (
    _recheck_phase0_draw_accuracy,
    _parse_draw_date_multilang,
)


# ─────────────────────────────────────────────────────────────────────
# BUG TERRAIN 28/03/2026 — Reproduction exacte + correction V126
# ─────────────────────────────────────────────────────────────────────


class TestBug28March2026Phase0Reapply:
    """Le test obligatoire Jyppy : bug 28/03/2026 corrigé post-V126."""

    @pytest.mark.asyncio
    async def test_bug_28_03_2026_F01_phase0_reapply(self, caplog):
        """Reproduction exacte du bug chat 19/04/2026 19:05:54.

        User : "stats du 30" → bot Phase 1 (vrai) cite date "28 mars 2026".
        User : "oui" → bot Phase 0 hallucine :
               "Date : 28 mars 2026 — Numéros : 8 - 12 - 28 - 30 - 48 — Chance : 4"
        Vrai tirage 28/03/2026 (DB) : 17-28-30-38-45 Chance 6.

        V126 3.5-A : détecte mismatch → remplace par safe message contenant
        les vrais chiffres via `_format_last_draw_context`.
        """
        caplog.set_level(logging.WARNING)
        halluc = (
            "Oui bien sûr ! Le tirage du 28 mars 2026 avait :\n"
            "Numéros : 8 - 12 - 28 - 30 - 48 — Chance : 4"
        )
        real_tirage = {
            "date": date(2026, 3, 28),
            "boules": [17, 28, 30, 38, 45],
            "chance": 6,
        }
        get_tirage_fn = AsyncMock(return_value=real_tirage)

        result = await _recheck_phase0_draw_accuracy(
            halluc, phase="0", lang="fr",
            log_prefix="[TEST BUG 28/03]",
            get_tirage_fn=get_tirage_fn,
        )
        # Remplacement effectif
        assert result is not None
        # Les vrais chiffres doivent être présents dans le safe replacement
        assert "17" in result
        assert "38" in result
        assert "45" in result
        # Log warning de mismatch émis
        assert any(
            "PHASE0_DRAW_MISMATCH" in r.message for r in caplog.records
        ), "Pas de log warning PHASE0_DRAW_MISMATCH émis"
        # DB re-query a bien été appelée avec la bonne date
        get_tirage_fn.assert_awaited_once_with(date(2026, 3, 28))


# ─────────────────────────────────────────────────────────────────────
# Cas de passage correct / garde-fous
# ─────────────────────────────────────────────────────────────────────


class TestPhase0ReapplyGraceful:
    """Cas où V126 3.5-A ne doit PAS intervenir / ne doit PAS crasher."""

    @pytest.mark.asyncio
    async def test_phase0_response_with_correct_draw_untouched(self):
        """Réponse cite la date + le VRAI tirage → None (aucun replace)."""
        response = (
            "Oui ! Le tirage du 28 mars 2026 : 17 - 28 - 30 - 38 - 45 Chance 6"
        )
        real_tirage = {
            "date": date(2026, 3, 28),
            "boules": [17, 28, 30, 38, 45],
            "chance": 6,
        }
        result = await _recheck_phase0_draw_accuracy(
            response, "0", "fr", "[TEST]",
            get_tirage_fn=AsyncMock(return_value=real_tirage),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_phase0_response_without_draw_untouched(self):
        """Pas de séquence 5-nums → None (rien à vérifier)."""
        response = "Oui, le 30 est un beau numéro. Tu veux autre chose ?"
        result = await _recheck_phase0_draw_accuracy(
            response, "0", "fr", "[TEST]",
            get_tirage_fn=AsyncMock(),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_phase0_date_not_in_db_returns_safe_message(self, caplog):
        """Date citée mais absent de la DB → warning + safe replacement."""
        caplog.set_level(logging.WARNING)
        response = "Le tirage du 28 mars 2026 : 1 - 2 - 3 - 4 - 5"
        result = await _recheck_phase0_draw_accuracy(
            response, "0", "fr", "[TEST]",
            get_tirage_fn=AsyncMock(return_value=None),  # DB returns None
        )
        assert result is not None
        assert "aucune donnée" in result.lower()
        assert any(
            "PHASE0_DATE_NOT_IN_DB" in r.message for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_phase0_invalid_date_format_graceful(self):
        """Date mal formée (ex: '32 mars 2026') → pas de crash, None."""
        response = "Le tirage du 32 mars 2026 avait 1-2-3-4-5"
        # _parse_draw_date_multilang retournera None sur date(2026,3,32)
        result = await _recheck_phase0_draw_accuracy(
            response, "0", "fr", "[TEST]",
            get_tirage_fn=AsyncMock(),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_phase_not_0_skipped(self):
        """Phase != 0 → return None immédiatement (guard anti-loop)."""
        response = "Le tirage du 28 mars 2026 : 1-2-3-4-5"
        for phase in ("1", "T", "SQL", "AFFIRMATION", ""):
            result = await _recheck_phase0_draw_accuracy(
                response, phase, "fr", "[TEST]",
                get_tirage_fn=AsyncMock(),
            )
            assert result is None, f"Phase {phase} should be skipped"

    @pytest.mark.asyncio
    async def test_no_get_tirage_fn_graceful(self):
        """Pas de get_tirage_fn dans ctx → None (ne crash pas)."""
        response = "Le tirage du 28 mars 2026 : 1-2-3-4-5"
        result = await _recheck_phase0_draw_accuracy(
            response, "0", "fr", "[TEST]", get_tirage_fn=None,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_db_timeout_graceful(self, caplog):
        """DB timeout → warning + None (ne bloque pas)."""
        import asyncio
        caplog.set_level(logging.WARNING)
        response = "Le tirage du 28 mars 2026 : 1-2-3-4-5"

        async def _slow_fn(d):
            await asyncio.sleep(10)
            return None

        result = await _recheck_phase0_draw_accuracy(
            response, "0", "fr", "[TEST]", get_tirage_fn=_slow_fn,
        )
        assert result is None
        assert any("TIMEOUT" in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────
# Parseur date multi-langue
# ─────────────────────────────────────────────────────────────────────


class TestParseDrawDateMultilang:
    """_parse_draw_date_multilang couvre FR/EN/ES/PT/DE/NL + ISO."""

    def test_parse_iso_yyyy_mm_dd(self):
        assert _parse_draw_date_multilang("tirage 2026-03-28") == date(2026, 3, 28)

    def test_parse_fr_d_month_yyyy(self):
        assert _parse_draw_date_multilang("28 mars 2026") == date(2026, 3, 28)

    def test_parse_en_d_month_yyyy(self):
        assert _parse_draw_date_multilang("28 March 2026") == date(2026, 3, 28)

    def test_parse_en_month_d_yyyy(self):
        assert _parse_draw_date_multilang("March 28, 2026") == date(2026, 3, 28)

    def test_parse_es_de_marzo_de(self):
        assert _parse_draw_date_multilang("28 de marzo de 2026") == date(2026, 3, 28)

    def test_parse_pt_marco(self):
        assert _parse_draw_date_multilang("28 de março de 2026") == date(2026, 3, 28)

    def test_parse_de_maerz(self):
        assert _parse_draw_date_multilang("28 März 2026") == date(2026, 3, 28)

    def test_parse_nl_maart(self):
        assert _parse_draw_date_multilang("28 maart 2026") == date(2026, 3, 28)

    def test_parse_invalid_day_returns_none(self):
        assert _parse_draw_date_multilang("32 mars 2026") is None

    def test_parse_no_date_returns_none(self):
        assert _parse_draw_date_multilang("hello world") is None


# ─────────────────────────────────────────────────────────────────────
# Symétrie EM (V99 F09) — réponse EM avec étoiles
# ─────────────────────────────────────────────────────────────────────


class TestPhase0ReapplyEmSymmetry:
    """EM : même mécanisme, tirage contient `etoiles` au lieu de `chance`."""

    @pytest.mark.asyncio
    async def test_em_mismatch_replaces_with_real_em_draw(self):
        """EM : mismatch → replace via _format_last_draw_context qui
        utilise la clef 'etoiles'."""
        halluc = "Le tirage EM du 14 mars 2026 : 1 - 2 - 3 - 4 - 5"
        real_em = {
            "date": date(2026, 3, 14),
            "boules": [10, 22, 23, 25, 46],
            "etoiles": [3, 7],
        }
        result = await _recheck_phase0_draw_accuracy(
            halluc, "0", "fr", "[TEST EM]",
            get_tirage_fn=AsyncMock(return_value=real_em),
        )
        assert result is not None
        assert "10" in result
        assert "22" in result
        # Étoiles présentes dans le safe replacement
        assert "Étoiles" in result or "3" in result

    @pytest.mark.asyncio
    async def test_em_correct_draw_untouched(self):
        real_em = {
            "date": date(2026, 3, 14),
            "boules": [10, 22, 23, 25, 46],
            "etoiles": [3, 7],
        }
        response = "Tirage EM 14 mars 2026 : 10 - 22 - 23 - 25 - 46 étoiles 3-7"
        result = await _recheck_phase0_draw_accuracy(
            response, "0", "fr", "[TEST EM]",
            get_tirage_fn=AsyncMock(return_value=real_em),
        )
        assert result is None
