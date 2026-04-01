"""
Tests for z-score penalization alternative in engine/hybride_base.py.
V80 — F06 terrain: z-score normalizes across windows of different sizes.
"""

import random
from dataclasses import replace
from unittest.mock import patch

import pytest

from config.engine import LOTO_CONFIG, EM_CONFIG
from engine.hybride_base import HybrideEngine


def _make_recent_draws(t1_balls, t2_balls=None, t3_balls=None, t4_balls=None):
    """Helper to build recent_draws list from ball lists."""
    draws = []
    for balls in [t1_balls, t2_balls, t3_balls, t4_balls]:
        if balls is None:
            break
        draw = {"date_de_tirage": "2026-04-01"}
        for i, b in enumerate(balls, 1):
            draw[f"boule_{i}"] = b
        draws.append(draw)
    return draws


class TestZScoreT1HardExclude:

    def test_t1_numbers_excluded(self):
        """T-1 numbers get score 0.0 (hard-exclude preserved)."""
        cfg = replace(LOTO_CONFIG, penalization_method="z_score")
        engine = HybrideEngine(cfg)
        scores = {n: 0.5 + n * 0.01 for n in range(1, 50)}
        draws = _make_recent_draws([1, 2, 3, 4, 5])
        result = engine.apply_penalties_z_score(scores, draws)
        for n in [1, 2, 3, 4, 5]:
            assert result[n] == 0.0


class TestZScoreTierOrdering:

    def test_t2_stronger_than_t3(self):
        """T-2 penalty (offset 2.0) is stronger than T-3 (offset 1.0)."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: 0.5 for n in range(1, 50)}
        scores[10] = 0.8  # target for T-2
        scores[20] = 0.8  # target for T-3, same starting score
        draws = _make_recent_draws([99], [10], [20])
        result = engine.apply_penalties_z_score(scores, draws)
        assert result[10] < result[20], "T-2 should penalize more than T-3"

    def test_t3_stronger_than_t4(self):
        """T-3 penalty (offset 1.0) is stronger than T-4 (offset 0.5)."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: 0.5 for n in range(1, 50)}
        scores[10] = 0.8
        scores[20] = 0.8
        draws = _make_recent_draws([99], [98], [10], [20])
        result = engine.apply_penalties_z_score(scores, draws)
        assert result[10] < result[20], "T-3 should penalize more than T-4"


class TestZScoreProperties:

    def test_preserves_ranking_of_non_penalized(self):
        """Non-penalized numbers keep their relative order."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: n * 0.01 for n in range(1, 50)}
        draws = _make_recent_draws([1, 2, 3, 4, 5])
        result = engine.apply_penalties_z_score(scores, draws)
        # Numbers 6-49 should maintain relative order
        non_penalized = [(n, result[n]) for n in range(6, 50)]
        for i in range(len(non_penalized) - 1):
            assert non_penalized[i][1] <= non_penalized[i + 1][1]

    def test_no_negative_scores(self):
        """No score is negative after z-score penalization."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: random.random() for n in range(1, 50)}
        random.seed(42)
        draws = _make_recent_draws([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
        result = engine.apply_penalties_z_score(scores, draws)
        for n, s in result.items():
            assert s >= 0.0, f"Score for {n} is negative: {s}"

    def test_fallback_on_zero_std(self):
        """All identical scores (std=0) → falls back to multiplicative."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: 0.5 for n in range(1, 50)}
        draws = _make_recent_draws([1, 2, 3, 4, 5])
        result = engine.apply_penalties_z_score(scores, draws)
        # Fallback to multiplicative: T-1 should be 0.0
        for n in [1, 2, 3, 4, 5]:
            assert result[n] == 0.0

    def test_config_offsets_used(self):
        """Custom z_score_offsets are respected."""
        # Use wide score spread so offsets produce measurably different results
        scores = {n: n * 0.1 for n in range(1, 50)}  # 0.1 to 4.9
        scores[10] = 4.0  # high score target for T-2
        draws = _make_recent_draws([99], [10])

        cfg = replace(LOTO_CONFIG, z_score_offsets=(0.0, 5.0, 3.0, 1.0))
        result_custom = HybrideEngine(cfg).apply_penalties_z_score(scores, draws)

        result_default = HybrideEngine(LOTO_CONFIG).apply_penalties_z_score(scores, draws)
        # Custom offset 5.0 for T-2 vs default 2.0 -> more penalty
        assert result_custom[10] <= result_default[10]


class TestZScoreConfig:

    def test_multiplicative_still_default(self):
        """Default penalization_method is multiplicative."""
        assert LOTO_CONFIG.penalization_method == "multiplicative"
        assert EM_CONFIG.penalization_method == "multiplicative"

    def test_z_score_offsets_default(self):
        """Default z_score_offsets are (0.0, 2.0, 1.0, 0.5)."""
        assert LOTO_CONFIG.z_score_offsets == (0.0, 2.0, 1.0, 0.5)


class TestZScoreEndToEnd:

    @pytest.mark.asyncio
    @patch("engine.hybride_base.HybrideEngine.get_reference_date")
    async def test_z_score_generates_valid_grid(self, mock_ref):
        """Generate grid with z_score method -> valid structure."""
        from tests.conftest import AsyncSmartMockCursor, make_async_conn
        from dataclasses import replace

        cursor = AsyncSmartMockCursor()
        random.seed(42)

        cfg = replace(LOTO_CONFIG, penalization_method="z_score")
        engine = HybrideEngine(cfg)
        result = await engine.generate_grids(
            n=3, mode="balanced", _get_connection=lambda: make_async_conn(cursor),
        )
        assert len(result["grids"]) == 3
        for grid in result["grids"]:
            assert len(grid["nums"]) == 5
            assert grid["score"] in (50, 60, 75, 85, 95)
