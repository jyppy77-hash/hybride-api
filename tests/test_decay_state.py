"""
Tests for services/decay_state.py and decay integration in engine pipeline.
V79 — F04 terrain: anti-lock rotation via score decay.
"""

import random
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from services.decay_state import (
    calculate_decay_multiplier,
    get_decay_state,
    update_decay_after_generation,
    update_decay_after_draw,
)
from config.engine import LOTO_CONFIG, EM_CONFIG
from engine.hybride_base import HybrideEngine


# ═══════════════════════════════════════════════════════════════════════
# calculate_decay_multiplier — pure function tests
# ═══════════════════════════════════════════════════════════════════════

class TestCalculateDecayMultiplier:

    def test_zero_misses(self):
        """0 misses → 1.0 (no penalty)."""
        assert calculate_decay_multiplier(0) == 1.0

    def test_one_miss(self):
        """1 miss → 0.95 with default rate 0.05."""
        assert calculate_decay_multiplier(1) == pytest.approx(0.95)

    def test_five_misses(self):
        """5 misses → 0.75."""
        assert calculate_decay_multiplier(5) == pytest.approx(0.75)

    def test_ten_misses_hits_floor(self):
        """10 misses → 0.50 (floor)."""
        assert calculate_decay_multiplier(10) == pytest.approx(0.50)

    def test_twenty_misses_clamped_at_floor(self):
        """20 misses → 0.50 (clamped, does not go below floor)."""
        assert calculate_decay_multiplier(20) == pytest.approx(0.50)

    def test_negative_misses(self):
        """Negative misses → 1.0 (guard)."""
        assert calculate_decay_multiplier(-1) == 1.0

    def test_custom_rate(self):
        """Custom decay_rate=0.10 → 3 misses = 0.70."""
        assert calculate_decay_multiplier(3, decay_rate=0.10) == pytest.approx(0.70)

    def test_custom_floor(self):
        """Custom floor=0.30 → 15 misses = 0.30 (not 0.25)."""
        assert calculate_decay_multiplier(15, decay_rate=0.05, floor=0.30) == pytest.approx(0.30)

    def test_zero_rate(self):
        """decay_rate=0.0 → always 1.0 regardless of misses."""
        assert calculate_decay_multiplier(100, decay_rate=0.0) == 1.0

    def test_floor_one(self):
        """floor=1.0 → always 1.0 (decay effectively disabled)."""
        assert calculate_decay_multiplier(10, decay_rate=0.05, floor=1.0) == 1.0


# ═══════════════════════════════════════════════════════════════════════
# apply_decay — engine method tests
# ═══════════════════════════════════════════════════════════════════════

class TestApplyDecay:

    def test_empty_decay_state_noop(self):
        """Empty decay_state → scores unchanged."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {1: 0.8, 2: 0.6, 3: 0.4}
        result = engine.apply_decay(scores, {})
        assert result == scores

    def test_none_decay_state_noop(self):
        """None decay_state treated as empty → scores unchanged."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {1: 0.8, 2: 0.6}
        # apply_decay is called with None guard in generer_grille
        # but the method itself handles empty dict
        result = engine.apply_decay(scores, {})
        assert result == scores

    def test_decay_applied(self):
        """Numbers with misses get decayed scores."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {1: 1.0, 2: 1.0, 3: 1.0}
        decay = {1: 0, 2: 5, 3: 10}
        result = engine.apply_decay(scores, decay)
        assert result[1] == pytest.approx(1.0)   # 0 misses → ×1.00
        assert result[2] == pytest.approx(0.75)   # 5 misses → ×0.75
        assert result[3] == pytest.approx(0.50)   # 10 misses → ×0.50

    def test_decay_preserves_zero_scores(self):
        """T-1 hard-excluded (score=0.0) stays 0.0 after decay."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {1: 0.0, 2: 0.8}
        decay = {1: 5, 2: 5}
        result = engine.apply_decay(scores, decay)
        assert result[1] == 0.0  # 0 × 0.75 = 0
        assert result[2] == pytest.approx(0.6)  # 0.8 × 0.75

    def test_unknown_numbers_get_no_decay(self):
        """Numbers not in decay_state treated as 0 misses."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {1: 0.8, 2: 0.8}
        decay = {1: 5}  # only num 1 in decay
        result = engine.apply_decay(scores, decay)
        assert result[1] == pytest.approx(0.6)   # 0.8 × 0.75
        assert result[2] == pytest.approx(0.8)   # no decay (0 misses)


# ═══════════════════════════════════════════════════════════════════════
# Decay config in EngineConfig
# ═══════════════════════════════════════════════════════════════════════

class TestDecayConfig:

    def test_loto_decay_defaults(self):
        assert LOTO_CONFIG.decay_enabled is True
        assert LOTO_CONFIG.decay_rate == 0.05
        assert LOTO_CONFIG.decay_floor == 0.50

    def test_em_decay_defaults(self):
        assert EM_CONFIG.decay_enabled is True
        assert EM_CONFIG.decay_rate == 0.05
        assert EM_CONFIG.decay_floor == 0.50


# ═══════════════════════════════════════════════════════════════════════
# Pipeline integration — decay_state parameter flows through
# ═══════════════════════════════════════════════════════════════════════

class TestDecayPipelineIntegration:

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_generate_grids_accepts_decay_state(self, mock_get_conn):
        """generate_grids() accepts decay_state kwarg without error."""
        from engine.hybride import generate_grids
        from tests.conftest import AsyncSmartMockCursor, make_async_conn
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        decay = {10: 5, 20: 10, 30: 3}
        result = await generate_grids(n=1, mode="balanced", decay_state=decay)
        assert len(result["grids"]) == 1
        assert result["metadata"]["decay"]["enabled"] is True
        assert result["metadata"]["decay"]["active"] is True

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_decay_none_metadata_inactive(self, mock_get_conn):
        """decay_state=None → metadata shows active=False."""
        from engine.hybride import generate_grids
        from tests.conftest import AsyncSmartMockCursor, make_async_conn
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        result = await generate_grids(n=1, mode="balanced")
        assert result["metadata"]["decay"]["enabled"] is True
        assert result["metadata"]["decay"]["active"] is False

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_decay_affects_grid_diversity(self, mock_get_conn):
        """With heavy decay on common numbers, grids should differ from no-decay."""
        from engine.hybride import generate_grids
        from tests.conftest import AsyncSmartMockCursor, make_async_conn
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)

        # Generate without decay
        random.seed(42)
        result_no_decay = await generate_grids(n=5, mode="balanced")

        # Generate with heavy decay on top-frequent numbers
        heavy_decay = {n: 20 for n in range(20, 40)}  # 20 nums at floor
        random.seed(42)
        result_decay = await generate_grids(n=5, mode="balanced", decay_state=heavy_decay)

        # Collect all nums from both
        nums_no_decay = set()
        nums_decay = set()
        for g in result_no_decay["grids"]:
            nums_no_decay.update(g["nums"])
        for g in result_decay["grids"]:
            nums_decay.update(g["nums"])

        # Decay should produce different number selection
        assert nums_no_decay != nums_decay, (
            "Decay on 20 numbers should change at least some grid content"
        )


# ═══════════════════════════════════════════════════════════════════════
# Async DB functions — mock tests
# ═══════════════════════════════════════════════════════════════════════

class TestDecayDBFunctions:

    @pytest.mark.asyncio
    async def test_get_decay_state_returns_dict(self):
        """get_decay_state returns {number: misses} dict."""
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[
            {"number_value": 5, "consecutive_misses": 3},
            {"number_value": 12, "consecutive_misses": 7},
        ])
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)

        result = await get_decay_state(mock_conn, "loto", "ball")
        assert result == {5: 3, 12: 7}

    @pytest.mark.asyncio
    async def test_get_decay_state_empty_table(self):
        """Empty table → empty dict."""
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)

        result = await get_decay_state(mock_conn, "euromillions", "ball")
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_decay_state_error_graceful(self):
        """DB error → empty dict (graceful degradation)."""
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(side_effect=Exception("DB down"))

        result = await get_decay_state(mock_conn, "loto", "ball")
        assert result == {}

    @pytest.mark.asyncio
    async def test_update_after_generation_calls_execute(self):
        """update_decay_after_generation executes INSERT...ON DUPLICATE KEY."""
        mock_cursor = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        await update_decay_after_generation(mock_conn, "loto", [5, 10, 15])
        assert mock_cursor.execute.call_count == 3  # one per ball
        mock_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_after_draw_resets_misses(self):
        """update_decay_after_draw executes INSERT...consecutive_misses=0."""
        mock_cursor = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        await update_decay_after_draw(mock_conn, "euromillions", [5, 10], drawn_stars=[3, 7])
        # 2 balls + 2 stars = 4 calls
        assert mock_cursor.execute.call_count == 4
        mock_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_after_generation_error_graceful(self):
        """DB error on update → no crash (graceful degradation)."""
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(side_effect=Exception("DB down"))

        # Should not raise
        await update_decay_after_generation(mock_conn, "loto", [1, 2, 3])

    @pytest.mark.asyncio
    async def test_update_after_draw_error_graceful(self):
        """DB error on draw update → no crash."""
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(side_effect=Exception("DB down"))

        await update_decay_after_draw(mock_conn, "loto", [1, 2, 3])
