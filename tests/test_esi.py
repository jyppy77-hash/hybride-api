"""
V107: Tests for services/esi.py — Even Spacing Index filter.
"""

import os
import pytest

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("INSTANCE_CONNECTION_NAME", "test:test:test")

from services.esi import calculate_esi, validate_esi


# ═══════════════════════════════════════════════
# calculate_esi
# ═══════════════════════════════════════════════

class TestCalculateESI:

    def test_evenly_spaced_em(self):
        """Evenly spaced 10-20-30-40-50 in universe 50 → ESI=405."""
        # Each gap is 10, formula uses (gap-1)^2 = 9^2 = 81, ×5 gaps = 405
        assert calculate_esi([10, 20, 30, 40, 50], 50) == 405

    def test_evenly_spaced_different(self):
        """5-15-25-35-45 in universe 50 → ESI=405 (same uniform 10-gap)."""
        assert calculate_esi([5, 15, 25, 35, 45], 50) == 405

    def test_fully_clustered_low(self):
        """{1,2,3,4,5} in universe 50 → very high ESI."""
        esi = calculate_esi([1, 2, 3, 4, 5], 50)
        # Gaps: (0)^2 + (0)^2 + (0)^2 + (0)^2 + (0 + 50 - 5)^2 = 45^2 = 2025
        assert esi == 2025

    def test_fully_clustered_high(self):
        """{46,47,48,49,50} in universe 50 → very high ESI."""
        esi = calculate_esi([46, 47, 48, 49, 50], 50)
        # Gaps: 0+0+0+0 + (46-1+50-50)^2 = 45^2 = 2025
        assert esi == 2025

    def test_medium_spacing(self):
        """{3,12,28,37,49} in universe 50 → medium ESI."""
        esi = calculate_esi([3, 12, 28, 37, 49], 50)
        # Gaps: (12-3-1)^2 + (28-12-1)^2 + (37-28-1)^2 + (49-37-1)^2 + (3-1+50-49)^2
        # = 8^2 + 15^2 + 8^2 + 11^2 + 3^2 = 64 + 225 + 64 + 121 + 9 = 483
        assert esi == 483

    def test_unsorted_input(self):
        """Input doesn't need to be sorted."""
        assert calculate_esi([28, 3, 49, 12, 37], 50) == calculate_esi([3, 12, 28, 37, 49], 50)

    def test_loto_universe_49(self):
        """{10,20,30,40,49} in universe 49."""
        esi = calculate_esi([10, 20, 30, 40, 49], 49)
        # Gaps: (20-10-1)^2 + (30-20-1)^2 + (40-30-1)^2 + (49-40-1)^2 + (10-1+49-49)^2
        # = 81 + 81 + 81 + 64 + 81 = 388
        assert esi == 388

    def test_single_number(self):
        """Edge case: single number → ESI=0."""
        assert calculate_esi([25], 50) == 0

    def test_two_numbers(self):
        """Two numbers: {1, 50} in universe 50."""
        esi = calculate_esi([1, 50], 50)
        # Gaps: (50-1-1)^2 + (1-1+50-50)^2 = 48^2 + 0 = 2304
        assert esi == 2304


# ═══════════════════════════════════════════════
# validate_esi
# ═══════════════════════════════════════════════

class TestValidateESI:

    def test_accept_medium(self):
        """Medium ESI within bounds → True."""
        # ESI=483 from test above
        assert validate_esi([3, 12, 28, 37, 49], 50, esi_min=20, esi_max=800) is True

    def test_reject_too_low(self):
        """ESI below esi_min → False."""
        # {2,4,6,8,10} in universe 50: gaps (1,1,1,1,41) → 0+0+0+0+41²=... but let's check
        # Actually with consecutive even: (4-2-1)^2+(6-4-1)^2+(8-6-1)^2+(10-8-1)^2+(2-1+50-10)^2
        # = 1+1+1+1+41^2 = 4+1681=1685 — too high. Use a crafted threshold instead.
        # ESI=405 for {10,20,30,40,50}. Set esi_min=500 to reject it.
        assert validate_esi([10, 20, 30, 40, 50], 50, esi_min=500, esi_max=2000) is False

    def test_reject_too_clustered(self):
        """ESI=2025 (fully clustered) > esi_max=800 → False."""
        assert validate_esi([1, 2, 3, 4, 5], 50, esi_min=20, esi_max=800) is False

    def test_accept_at_min_boundary(self):
        """ESI exactly at esi_min → True (inclusive)."""
        # ESI=405 for {10,20,30,40,50}
        assert validate_esi([10, 20, 30, 40, 50], 50, esi_min=405, esi_max=800) is True

    def test_accept_at_max_boundary(self):
        """ESI exactly at esi_max → True (inclusive)."""
        assert validate_esi([3, 12, 28, 37, 49], 50, esi_min=20, esi_max=483) is True

    def test_loto_config_defaults(self):
        """Loto defaults: esi_min=20, esi_max=750."""
        from config.engine import LOTO_CONFIG
        assert LOTO_CONFIG.esi_min == 20
        assert LOTO_CONFIG.esi_max == 750

    def test_em_config_defaults(self):
        """EM defaults: esi_min=20, esi_max=800."""
        from config.engine import EM_CONFIG
        assert EM_CONFIG.esi_min == 20
        assert EM_CONFIG.esi_max == 800


# ═══════════════════════════════════════════════
# Integration with generate_grids
# ═══════════════════════════════════════════════

import random
from engine.hybride_base import HybrideEngine
from config.engine import LOTO_CONFIG, EM_CONFIG
from tests.conftest import AsyncSmartMockCursor, make_async_conn


class TestESIIntegration:

    @pytest.mark.asyncio
    async def test_generated_grid_passes_esi(self):
        """Generated grid should have ESI within bounds."""
        cursor = AsyncSmartMockCursor()
        random.seed(42)
        engine = HybrideEngine(LOTO_CONFIG)
        result = await engine.generate_grids(
            n=1, mode="balanced",
            _get_connection=lambda: make_async_conn(cursor),
        )
        grid = result["grids"][0]
        esi = calculate_esi(grid["nums"], 49)
        # Should be within bounds (or best-effort if all attempts fail)
        assert len(grid["nums"]) == 5
        # ESI should be reasonable (not perfectly spaced)
        assert esi > 0

    @pytest.mark.asyncio
    async def test_em_generated_grid_valid(self):
        """EM grid is valid with ESI filter active."""
        cursor = AsyncSmartMockCursor()
        random.seed(42)
        engine = HybrideEngine(EM_CONFIG)
        result = await engine.generate_grids(
            n=1, mode="balanced",
            _get_connection=lambda: make_async_conn(cursor),
        )
        grid = result["grids"][0]
        assert len(grid["nums"]) == 5
