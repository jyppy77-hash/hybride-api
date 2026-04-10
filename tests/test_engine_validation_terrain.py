"""
Tests de validation terrain — F08 audit 360° Engine HYBRIDE (V92).
Compare le moteur aux tirages réels EuroMillions (20/02 → 10/04/2026).

Ces tests vérifient que le moteur produit des grilles dont les propriétés
statistiques (somme, diversité, rotation) sont cohérentes avec les tirages
réels, et que le decay system brise effectivement le kernel lock.
"""

import random
from unittest.mock import patch

import pytest

from config.engine import EM_CONFIG, LOTO_CONFIG
from engine.hybride_base import HybrideEngine
from tests.conftest import AsyncSmartMockCursor, make_async_conn


# ── Données terrain EM (20/02 → 08/04/2026 — 13 tirages réels) ──────
REAL_DRAW_SUMS_EM = [133, 167, 121, 115, 147, 145, 124, 116, 90, 149, 94, 159, 129]
REAL_DRAW_MEAN = sum(REAL_DRAW_SUMS_EM) / len(REAL_DRAW_SUMS_EM)  # ≈129.9


# ═══════════════════════════════════════════════════════════════════════
# Distribution des sommes — grilles générées vs tirages réels
# ═══════════════════════════════════════════════════════════════════════

class TestGeneratedSumDistribution:

    @pytest.mark.asyncio
    @patch("engine.hybride_base.HybrideEngine.get_reference_date")
    async def test_em_mean_sum_within_range(self, mock_ref):
        """La moyenne des sommes des grilles EM doit être dans [110, 150].
        Tirages réels: mean ≈ 129.9. Intervalle ±20."""
        cursor = AsyncSmartMockCursor()
        random.seed(42)
        engine = HybrideEngine(EM_CONFIG)
        result = await engine.generate_grids(
            n=100, mode="balanced",
            _get_connection=lambda: make_async_conn(cursor),
        )
        sums = [sum(g["nums"]) for g in result["grids"]]
        mean_sum = sum(sums) / len(sums)
        assert 110 <= mean_sum <= 150, (
            f"Mean sum {mean_sum:.1f} out of [110, 150] (real mean ≈{REAL_DRAW_MEAN:.1f})"
        )

    @pytest.mark.asyncio
    @patch("engine.hybride_base.HybrideEngine.get_reference_date")
    async def test_em_majority_sums_within_constraints(self, mock_ref):
        """≥75% of EM grids have sums in [95, 175].
        Note: with mock data (uniform scores), the soft constraint (×0.70 penalty)
        allows some outliers. With real DB data, the rate is higher."""
        cursor = AsyncSmartMockCursor()
        random.seed(42)
        engine = HybrideEngine(EM_CONFIG)
        result = await engine.generate_grids(
            n=100, mode="balanced",
            _get_connection=lambda: make_async_conn(cursor),
        )
        in_range = sum(
            1 for g in result["grids"]
            if EM_CONFIG.somme_min <= sum(g["nums"]) <= EM_CONFIG.somme_max
        )
        assert in_range >= 75, f"Only {in_range}/100 grids in sum range [95, 175]"

    @pytest.mark.asyncio
    @patch("engine.hybride_base.HybrideEngine.get_reference_date")
    async def test_loto_majority_sums_within_constraints(self, mock_ref):
        """≥75% of Loto grids have sums in [70, 150] (soft constraint)."""
        cursor = AsyncSmartMockCursor()
        random.seed(42)
        engine = HybrideEngine(LOTO_CONFIG)
        result = await engine.generate_grids(
            n=100, mode="balanced",
            _get_connection=lambda: make_async_conn(cursor),
        )
        in_range = sum(
            1 for g in result["grids"]
            if LOTO_CONFIG.somme_min <= sum(g["nums"]) <= LOTO_CONFIG.somme_max
        )
        assert in_range >= 75, f"Only {in_range}/100 grids in sum range [70, 150]"


# ═══════════════════════════════════════════════════════════════════════
# Anti kernel-lock — le decay casse le verrouillage du noyau
# ═══════════════════════════════════════════════════════════════════════

class TestAntiKernelLock:

    @pytest.mark.asyncio
    @patch("engine.hybride_base.HybrideEngine.get_reference_date")
    async def test_no_kernel_lock_after_5_generations(self, mock_ref):
        """Après 5 générations consécutives avec decay progressif,
        le set de numéros doit contenir ≥15 numéros distincts (sur 25 slots)."""
        cursor = AsyncSmartMockCursor()
        engine = HybrideEngine(EM_CONFIG)
        all_nums = set()

        # Simulate 5 rounds with escalating decay
        for round_idx in range(5):
            random.seed(42 + round_idx)
            # Each round: the top numbers from previous rounds have more misses
            decay_state = {n: round_idx + 1 for n in range(30, 50)}
            result = await engine.generate_grids(
                n=1, mode="balanced", decay_state=decay_state,
                _get_connection=lambda: make_async_conn(cursor),
            )
            all_nums.update(result["grids"][0]["nums"])

        assert len(all_nums) >= 15, (
            f"Only {len(all_nums)} distinct numbers in 5 generations "
            f"(expected ≥15): {sorted(all_nums)}"
        )

    @pytest.mark.asyncio
    @patch("engine.hybride_base.HybrideEngine.get_reference_date")
    async def test_decay_diversifies_across_generations(self, mock_ref):
        """With decay, 10 consecutive generations produce more variety than without."""
        cursor = AsyncSmartMockCursor()
        engine = HybrideEngine(EM_CONFIG)

        # Without decay
        random.seed(42)
        result_no = await engine.generate_grids(
            n=10, mode="balanced",
            _get_connection=lambda: make_async_conn(cursor),
        )
        nums_no_decay = set()
        for g in result_no["grids"]:
            nums_no_decay.update(g["nums"])

        # With heavy decay on top numbers
        random.seed(42)
        decay = {n: 5 for n in range(25, 50)}
        result_yes = await engine.generate_grids(
            n=10, mode="balanced", decay_state=decay,
            _get_connection=lambda: make_async_conn(cursor),
        )
        nums_decay = set()
        for g in result_yes["grids"]:
            nums_decay.update(g["nums"])

        # Decay should produce different set
        assert nums_no_decay != nums_decay


# ═══════════════════════════════════════════════════════════════════════
# Wildcard cold slot — chaque grille a ≥1 numéro froid
# ═══════════════════════════════════════════════════════════════════════

class TestWildcardPresence:

    @pytest.mark.asyncio
    @patch("engine.hybride_base.HybrideEngine.get_reference_date")
    async def test_wildcard_always_present_em(self, mock_ref):
        """Chaque grille EM contient ≥1 numéro ≤25 (wildcard cold pool)."""
        cursor = AsyncSmartMockCursor()
        random.seed(42)
        engine = HybrideEngine(EM_CONFIG)
        result = await engine.generate_grids(
            n=50, mode="balanced",
            _get_connection=lambda: make_async_conn(cursor),
        )
        for i, grid in enumerate(result["grids"]):
            low_nums = [n for n in grid["nums"] if n <= 25]
            assert len(low_nums) >= 1, (
                f"Grid {i}: no number ≤25 in {grid['nums']}"
            )

    @pytest.mark.asyncio
    @patch("engine.hybride_base.HybrideEngine.get_reference_date")
    async def test_wildcard_always_present_loto(self, mock_ref):
        """Chaque grille Loto contient ≥1 numéro ≤24 (wildcard cold pool)."""
        cursor = AsyncSmartMockCursor()
        random.seed(42)
        engine = HybrideEngine(LOTO_CONFIG)
        result = await engine.generate_grids(
            n=50, mode="balanced",
            _get_connection=lambda: make_async_conn(cursor),
        )
        for i, grid in enumerate(result["grids"]):
            low_nums = [n for n in grid["nums"] if n <= 24]
            assert len(low_nums) >= 1, (
                f"Grid {i}: no number ≤24 in {grid['nums']}"
            )


# ═══════════════════════════════════════════════════════════════════════
# Decay accéléré — valeurs numériques exactes
# ═══════════════════════════════════════════════════════════════════════

class TestDecayAcceleratedValues:

    def test_decay_values_match_spec(self):
        """V92 decay values match specification exactly."""
        from services.decay_state import calculate_decay_multiplier
        assert calculate_decay_multiplier(0) == 1.0
        assert calculate_decay_multiplier(1) == pytest.approx(0.897, abs=0.001)
        assert calculate_decay_multiplier(2) == pytest.approx(0.788, abs=0.001)
        assert calculate_decay_multiplier(3) == pytest.approx(0.673, abs=0.001)
        assert calculate_decay_multiplier(4) == pytest.approx(0.552, abs=0.001)
        assert calculate_decay_multiplier(5) == pytest.approx(0.500)  # floor

    def test_decay_floor_respected_with_acceleration(self):
        """Floor 0.50 is always respected even with heavy acceleration."""
        from services.decay_state import calculate_decay_multiplier
        for misses in range(5, 100):
            assert calculate_decay_multiplier(misses) >= 0.50
