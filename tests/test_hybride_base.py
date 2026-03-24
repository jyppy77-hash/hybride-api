"""
Tests for engine/hybride_base.py and config/engine.py.
Config validation, base class, forced number validation, 3-window merge.
"""

import random
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from config.engine import LOTO_CONFIG, EM_CONFIG, EngineConfig
from engine.hybride_base import HybrideEngine
from tests.conftest import AsyncSmartMockCursor, make_async_conn


# ═══════════════════════════════════════════════════════════════════════
# EngineConfig (frozen dataclass)
# ═══════════════════════════════════════════════════════════════════════

class TestEngineConfig:

    def test_loto_config_frozen(self):
        with pytest.raises(FrozenInstanceError):
            LOTO_CONFIG.num_max = 99

    def test_em_config_frozen(self):
        with pytest.raises(FrozenInstanceError):
            EM_CONFIG.num_max = 99

    def test_loto_values(self):
        assert LOTO_CONFIG.game == "loto"
        assert LOTO_CONFIG.num_max == 49
        assert LOTO_CONFIG.secondary_max == 10
        assert LOTO_CONFIG.secondary_count == 1
        assert LOTO_CONFIG.somme_min == 70
        assert LOTO_CONFIG.somme_max == 150
        assert LOTO_CONFIG.anti_collision_threshold == 24
        assert LOTO_CONFIG.table_name == "tirages"

    def test_em_values(self):
        assert EM_CONFIG.game == "em"
        assert EM_CONFIG.num_max == 50
        assert EM_CONFIG.secondary_max == 12
        assert EM_CONFIG.secondary_count == 2
        assert EM_CONFIG.somme_min == 75
        assert EM_CONFIG.somme_max == 175
        assert EM_CONFIG.anti_collision_threshold == 31
        assert EM_CONFIG.table_name == "tirages_euromillions"

    def test_modes_3_weights(self):
        for cfg in (LOTO_CONFIG, EM_CONFIG):
            for mode, weights in cfg.modes.items():
                assert len(weights) == 3, f"{cfg.game} mode {mode} has {len(weights)} weights"
                assert abs(sum(weights) - 1.0) < 0.01, f"{cfg.game} mode {mode} weights sum to {sum(weights)}"

    def test_penalty_coefficients(self):
        assert LOTO_CONFIG.penalty_coefficients == (0.0, 0.65, 0.80, 0.90)
        assert EM_CONFIG.penalty_coefficients == (0.0, 0.65, 0.80, 0.90)

    def test_temperature_by_mode(self):
        for cfg in (LOTO_CONFIG, EM_CONFIG):
            assert cfg.temperature_by_mode['conservative'] == 1.0
            assert cfg.temperature_by_mode['balanced'] == 1.3
            assert cfg.temperature_by_mode['recent'] == 1.5

    def test_superstitious_numbers(self):
        assert LOTO_CONFIG.superstitious_numbers == frozenset({3, 7, 9, 11, 13})
        assert EM_CONFIG.superstitious_secondary == frozenset({3, 7, 9, 11})


# ═══════════════════════════════════════════════════════════════════════
# HybrideEngine instantiation
# ═══════════════════════════════════════════════════════════════════════

class TestHybrideEngineInit:

    def test_init_loto(self):
        engine = HybrideEngine(LOTO_CONFIG)
        assert engine.cfg.game == "loto"

    def test_init_em(self):
        engine = HybrideEngine(EM_CONFIG)
        assert engine.cfg.game == "em"


# ═══════════════════════════════════════════════════════════════════════
# Static helpers
# ═══════════════════════════════════════════════════════════════════════

class TestBaseMinmaxNormalize:

    def test_basic(self):
        result = HybrideEngine._minmax_normalize({1: 10, 2: 20, 3: 30})
        assert result[1] == 0.0
        assert result[3] == 1.0

    def test_all_equal(self):
        result = HybrideEngine._minmax_normalize({1: 5, 2: 5, 3: 5})
        assert all(v == 0.0 for v in result.values())


class TestBaseNormaliserEnProbabilites:

    def test_sum_to_one(self):
        scores = {n: random.random() + 0.01 for n in range(1, 50)}
        result = HybrideEngine.normaliser_en_probabilites(scores, temperature=1.3)
        assert pytest.approx(sum(result.values()), abs=1e-9) == 1.0

    def test_temperature_flattens(self):
        scores = {1: 0.1, 2: 1.0}
        t1 = HybrideEngine.normaliser_en_probabilites(scores, temperature=1.0)
        t2 = HybrideEngine.normaliser_en_probabilites(scores, temperature=2.0)
        assert t2[2] / t2[1] < t1[2] / t1[1]


class TestBaseScoreFinal:

    def test_stars(self):
        m = LOTO_CONFIG.star_to_legacy_score
        assert HybrideEngine._calculer_score_final(1.0, m) == 95
        assert HybrideEngine._calculer_score_final(0.90, m) == 85
        assert HybrideEngine._calculer_score_final(0.75, m) == 75
        assert HybrideEngine._calculer_score_final(0.55, m) == 60
        assert HybrideEngine._calculer_score_final(0.40, m) == 50


# ═══════════════════════════════════════════════════════════════════════
# Forced numbers validation (E08)
# ═══════════════════════════════════════════════════════════════════════

class TestForcedNumbersValidation:

    def test_valid_nums(self):
        engine = HybrideEngine(LOTO_CONFIG)
        nums, sec = engine.valider_forced_numbers([5, 10, 30], [3])
        assert nums == [5, 10, 30]
        assert sec == [3]

    def test_out_of_range_removed(self):
        engine = HybrideEngine(LOTO_CONFIG)
        nums, _ = engine.valider_forced_numbers([0, 25, 55], None)
        assert nums == [25]

    def test_duplicates_removed(self):
        engine = HybrideEngine(LOTO_CONFIG)
        nums, _ = engine.valider_forced_numbers([7, 7, 7, 14], None)
        assert nums == [7, 14]

    def test_truncated_if_too_many(self):
        engine = HybrideEngine(LOTO_CONFIG)
        nums, _ = engine.valider_forced_numbers([1, 2, 3, 4, 5, 6, 7], None)
        assert len(nums) == 5

    def test_em_etoiles_max_2(self):
        engine = HybrideEngine(EM_CONFIG)
        _, sec = engine.valider_forced_numbers(None, [1, 5, 9])
        assert len(sec) == 2

    def test_em_etoiles_range(self):
        engine = HybrideEngine(EM_CONFIG)
        _, sec = engine.valider_forced_numbers(None, [0, 5, 13])
        assert sec == [5]

    def test_none_inputs(self):
        engine = HybrideEngine(LOTO_CONFIG)
        nums, sec = engine.valider_forced_numbers(None, None)
        assert nums == []
        assert sec == []

    def test_loto_chance_max_1(self):
        engine = HybrideEngine(LOTO_CONFIG)
        _, sec = engine.valider_forced_numbers(None, [3, 7])
        assert len(sec) == 1  # secondary_count=1


# ═══════════════════════════════════════════════════════════════════════
# Constraint validation via config
# ═══════════════════════════════════════════════════════════════════════

class TestBaseValiderContraintes:

    def test_loto_perfect(self):
        engine = HybrideEngine(LOTO_CONFIG)
        assert engine.valider_contraintes([3, 15, 24, 33, 47]) == 1.0

    def test_em_perfect(self):
        engine = HybrideEngine(EM_CONFIG)
        assert engine.valider_contraintes([3, 15, 26, 33, 47]) == 1.0

    def test_loto_bas_haut_threshold(self):
        """Loto: seuil_bas_haut=24."""
        engine = HybrideEngine(LOTO_CONFIG)
        # All 5 numbers > 24 → nb_bas=0 → penalty
        score = engine.valider_contraintes([25, 30, 35, 40, 45])
        assert score < 1.0

    def test_em_bas_haut_threshold(self):
        """EM: seuil_bas_haut=25."""
        engine = HybrideEngine(EM_CONFIG)
        # All 5 numbers > 25 → nb_bas=0 → penalty
        score = engine.valider_contraintes([26, 30, 35, 40, 45])
        assert score < 1.0


# ═══════════════════════════════════════════════════════════════════════
# Anti-collision via config
# ═══════════════════════════════════════════════════════════════════════

class TestBaseAntiCollision:

    def test_loto_threshold(self):
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {20: 1.0, 30: 1.0}
        result = engine.apply_anti_collision(scores)
        assert result[20] == 1.0  # <=24
        assert result[30] == pytest.approx(1.15)  # >24

    def test_em_threshold(self):
        engine = HybrideEngine(EM_CONFIG)
        scores = {25: 1.0, 35: 1.0}
        result = engine.apply_anti_collision(scores)
        assert result[25] == 1.0  # <=31
        assert result[35] == pytest.approx(1.15)  # >31

    def test_secondary_anti_collision_em(self):
        engine = HybrideEngine(EM_CONFIG)
        scores = {n: 1.0 for n in range(1, 13)}
        result = engine.apply_secondary_anti_collision(scores)
        assert result[3] == pytest.approx(0.85)
        assert result[7] == pytest.approx(0.85)
        assert result[1] == 1.0  # not superstitious

    def test_secondary_anti_collision_loto_noop(self):
        """Loto has no superstitious secondary (empty frozenset)."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: 1.0 for n in range(1, 11)}
        result = engine.apply_secondary_anti_collision(scores)
        assert result == scores


# ═══════════════════════════════════════════════════════════════════════
# Three-window merge (F04)
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_three_window_metadata(mock_get_conn):
    """generate_grids metadata includes fenetre_globale."""
    from engine.hybride import generate_grids
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=1, mode="balanced")
    assert result["metadata"]["fenetre_globale"] is True


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_three_window_grids_valid(mock_get_conn):
    """Grids from 3-window engine are structurally valid."""
    from engine.hybride import generate_grids
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=5, mode="balanced")
    for grid in result["grids"]:
        assert len(grid["nums"]) == 5
        assert all(1 <= n <= 49 for n in grid["nums"])
        assert 1 <= grid["chance"] <= 10
