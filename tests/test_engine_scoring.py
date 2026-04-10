"""
Tests unitaires isolés pour les fonctions de scoring du moteur HYBRIDE.
Couvre calculer_frequences(), calculer_retards(), calculer_scores_fenetre().
Faille F06 audit 360° Engine HYBRIDE (10/04/2026).
"""

import pytest
from unittest.mock import patch

from config.engine import LOTO_CONFIG, EM_CONFIG
from engine.hybride_base import HybrideEngine
from tests.conftest import AsyncSmartMockCursor, make_async_conn


# ═══════════════════════════════════════════════════════════════════════
# calculer_frequences — unit tests
# ═══════════════════════════════════════════════════════════════════════

class TestCalculerFrequences:

    @pytest.mark.asyncio
    async def test_frequences_basic(self):
        """Fréquences sur données simples — chaque numéro compté correctement."""
        engine = HybrideEngine(LOTO_CONFIG)
        cursor = AsyncSmartMockCursor()
        async with make_async_conn(cursor) as conn:
            freq = await engine.calculer_frequences(conn, None)
        # SmartMockCursor returns uniform data → all numbers have frequencies
        assert len(freq) == 49
        for n in range(1, 50):
            assert n in freq
            assert isinstance(freq[n], float)

    @pytest.mark.asyncio
    async def test_frequences_values_are_ratios(self):
        """Fréquences are ratios (count/total_draws), not raw counts."""
        engine = HybrideEngine(LOTO_CONFIG)
        cursor = AsyncSmartMockCursor()
        async with make_async_conn(cursor) as conn:
            freq = await engine.calculer_frequences(conn, None)
        # All values should be in [0, 1] since they're count/total
        for v in freq.values():
            assert 0.0 <= v <= 1.0

    @pytest.mark.asyncio
    async def test_frequences_normalization_minmax(self):
        """After min-max normalization, min → 0.0, max → 1.0."""
        engine = HybrideEngine(LOTO_CONFIG)
        cursor = AsyncSmartMockCursor()
        async with make_async_conn(cursor) as conn:
            freq = await engine.calculer_frequences(conn, None)
        normalized = engine._minmax_normalize(freq)
        vals = list(normalized.values())
        assert min(vals) == 0.0
        assert max(vals) == pytest.approx(1.0) or max(vals) == 0.0  # all-equal edge case

    @pytest.mark.asyncio
    async def test_frequences_em_range(self):
        """EM frequencies cover 1-50."""
        engine = HybrideEngine(EM_CONFIG)
        cursor = AsyncSmartMockCursor()
        async with make_async_conn(cursor) as conn:
            freq = await engine.calculer_frequences(conn, None)
        assert len(freq) == 50
        for n in range(1, 51):
            assert n in freq


# ═══════════════════════════════════════════════════════════════════════
# calculer_retards — unit tests
# ═══════════════════════════════════════════════════════════════════════

class TestCalculerRetards:

    @pytest.mark.asyncio
    async def test_retards_basic(self):
        """Retard values are non-negative floats for all numbers."""
        engine = HybrideEngine(LOTO_CONFIG)
        cursor = AsyncSmartMockCursor()
        async with make_async_conn(cursor) as conn:
            retard = await engine.calculer_retards(conn, None)
        assert len(retard) == 49
        for n in range(1, 50):
            assert n in retard
            assert retard[n] >= 0.0

    @pytest.mark.asyncio
    async def test_retards_normalized(self):
        """Retards are normalized to [0, 1] after division by max."""
        engine = HybrideEngine(LOTO_CONFIG)
        cursor = AsyncSmartMockCursor()
        async with make_async_conn(cursor) as conn:
            retard = await engine.calculer_retards(conn, None)
        for v in retard.values():
            assert 0.0 <= v <= 1.0

    @pytest.mark.asyncio
    async def test_retards_em_range(self):
        """EM retards cover 1-50."""
        engine = HybrideEngine(EM_CONFIG)
        cursor = AsyncSmartMockCursor()
        async with make_async_conn(cursor) as conn:
            retard = await engine.calculer_retards(conn, None)
        assert len(retard) == 50


# ═══════════════════════════════════════════════════════════════════════
# calculer_scores_fenetre — unit tests
# ═══════════════════════════════════════════════════════════════════════

class TestCalculerScoresFenetre:

    @pytest.mark.asyncio
    async def test_scores_weighted_combination(self):
        """Score = poids_frequence × freq_norm + poids_retard × retard_norm.
        Both components are normalized min-max, so scores are in [0, 1]."""
        engine = HybrideEngine(LOTO_CONFIG)
        cursor = AsyncSmartMockCursor()
        async with make_async_conn(cursor) as conn:
            scores = await engine.calculer_scores_fenetre(conn, None)
        assert len(scores) == 49
        for n in range(1, 50):
            assert n in scores
            # Score = 0.7*freq + 0.3*retard, both in [0,1] → score in [0, 1]
            assert 0.0 <= scores[n] <= 1.0

    @pytest.mark.asyncio
    async def test_scores_secondary_weights(self):
        """Secondary: poids_frequence_secondary × freq + poids_retard_secondary × retard."""
        engine = HybrideEngine(LOTO_CONFIG)
        cursor = AsyncSmartMockCursor()
        async with make_async_conn(cursor) as conn:
            scores = await engine.calculer_scores_fenetre_secondary(conn, None)
        # Loto chance: 1-10
        assert len(scores) == 10
        for n in range(1, 11):
            assert n in scores
            assert 0.0 <= scores[n] <= 1.0

    @pytest.mark.asyncio
    async def test_scores_em_secondary_etoiles(self):
        """EM secondary scores cover 1-12 (étoiles)."""
        engine = HybrideEngine(EM_CONFIG)
        cursor = AsyncSmartMockCursor()
        async with make_async_conn(cursor) as conn:
            scores = await engine.calculer_scores_fenetre_secondary(conn, None)
        assert len(scores) == 12
        for n in range(1, 13):
            assert n in scores

    @pytest.mark.asyncio
    async def test_scores_hybrides_3_windows(self):
        """calculer_scores_hybrides combines 3 windows with mode weights."""
        engine = HybrideEngine(LOTO_CONFIG)
        cursor = AsyncSmartMockCursor()
        async with make_async_conn(cursor) as conn:
            scores = await engine.calculer_scores_hybrides(conn, mode="balanced")
        assert len(scores) == 49
        # All scores should be non-negative
        for s in scores.values():
            assert s >= 0.0
