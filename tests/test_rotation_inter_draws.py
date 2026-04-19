"""
V110 — Regression tests for inter-draw rotation.

Reproduces the terrain cases documented in audit 01.1 rev.2:
- Loto L3 → L4 → L5: grids near-identical (4/5 or 5/5 shared)
- EM #15 → #16: 4/5 balls shared

With V110 persistent brake active, these repetitions MUST NOT occur
on scores alone (the brake pushes previously-selected numbers way down).

Tests use synthetic scores (no DB) to isolate the brake mechanism.
"""
import pytest

from engine.hybride_base import HybrideEngine
from config.engine import LOTO_CONFIG, EM_CONFIG
from dataclasses import replace


# ═══════════════════════════════════════════════════════════════════════
# Test 1 — rotation after 3 draws without hit (synthetic)
# ═══════════════════════════════════════════════════════════════════════

class TestRotationAfterThreeDraws:

    def test_rotation_3_consecutive_draws_without_hit(self):
        """
        V110: after 3 consecutive generations where none of the top 5 per zone
        actually appears in a real draw, the brake map accumulates and the
        scoring of those numbers is pushed below challengers.

        Scenario: 36 (score 22) leads Z4 Loto. 32 (score 20) challenger.
        - Draw T: 36 selected, 32 not. 32 has no brake, 36 has no brake yet.
        - Draw T+1: 36 has brake ×0.20 (T-1). Brake map = {36: 0.20}.
          Without brake: 36=22, 32=20 → 36 wins again.
          With brake: 36=22×0.20=4.4, 32=20 → 32 wins. ✅
        """
        engine = HybrideEngine(LOTO_CONFIG)
        # Simulated scores for Z4 Loto (zone 31-40)
        scores = {36: 22.0, 32: 20.0, 34: 18.0, 31: 17.0, 38: 15.0}
        # After draw T: 36 was selected → brake T-1 active for next generation
        brake_map_t_plus_1 = {36: 0.20}
        result = engine.apply_persistent_brake(scores, brake_map_t_plus_1)
        # 36: 22 × 0.20 = 4.4 → below 32 (20). Ordering reversed!
        assert result[36] == pytest.approx(4.40)
        assert result[32] == pytest.approx(20.0)
        # Leader of Z4 after brake:
        leader = max(result, key=result.get)
        assert leader == 32, "With brake on 36, challenger 32 takes leadership"

    def test_rotation_cascades_over_3_draws(self):
        """After 3 draws (T, T+1, T+2), 3 different leaders of Z4 emerge."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {36: 22.0, 32: 20.0, 34: 18.0, 31: 17.0, 38: 15.0}

        # Draw T: no brake yet → 36 wins
        leader_t = max(scores, key=scores.get)
        assert leader_t == 36

        # Draw T+1: brake T-1 on 36 → 32 wins
        brake_t1 = {36: 0.20}
        scores_t1 = engine.apply_persistent_brake(scores, brake_t1)
        leader_t1 = max(scores_t1, key=scores_t1.get)
        assert leader_t1 == 32

        # Draw T+2: brake T-1 on 32, T-2 on 36 → leader becomes 34 or 36 depends on math
        # 36: 22 × 0.50 (T-2) = 11.0
        # 32: 20 × 0.20 (T-1) = 4.0
        # 34: 18 × 1.00 = 18.0 ← winner
        # 31: 17.0
        # 38: 15.0
        brake_t2 = {36: 0.50, 32: 0.20}
        scores_t2 = engine.apply_persistent_brake(scores, brake_t2)
        leader_t2 = max(scores_t2, key=scores_t2.get)
        assert leader_t2 == 34, "After 2 draws, challenger 34 wins"

        # Verify: 3 different leaders in 3 draws
        assert len({leader_t, leader_t1, leader_t2}) == 3


# ═══════════════════════════════════════════════════════════════════════
# Test 2 — Loto L4 → L5 rotation (terrain case)
# ═══════════════════════════════════════════════════════════════════════

class TestSimulationL4toL5Rotation:

    def test_simulation_l4_to_l5_rotation(self):
        """
        Terrain case: L4 (18/04/2026) generated 3-12-30-36-42.
        L5 (19/04/2026 simulated) was identical (V123 bug).
        With V110 brake T-1 on [3, 12, 30, 36, 42], L5 cannot repeat.
        """
        engine = HybrideEngine(LOTO_CONFIG)
        # Simulated L4 canonical grid
        l4_grid = [3, 12, 30, 36, 42]
        # Hypothetical scores for Z1 (1-10), Z2 (11-20), Z3 (21-30), Z4 (31-40), Z5 (41-49)
        # These mimic the 1A Loto top values from audit
        scores_z1 = {3: 19.0, 5: 17.0, 8: 16.0, 1: 14.0, 7: 13.0}
        scores_z2 = {12: 15.0, 15: 14.0, 11: 13.0, 18: 12.0, 13: 11.0}
        scores_z3 = {30: 22.0, 28: 20.0, 26: 18.0, 25: 17.0, 21: 15.0}
        scores_z4 = {36: 22.0, 32: 20.0, 34: 18.0, 31: 17.0, 38: 15.0}
        scores_z5 = {42: 19.0, 49: 18.0, 45: 16.0, 44: 15.0, 47: 14.0}

        # Brake T-1 active for L5 (numbers from L4 canonical)
        brake_map = {n: 0.20 for n in l4_grid}

        # Apply brake to each zone and find new leaders
        def new_leader(scores_zone):
            braked = engine.apply_persistent_brake(scores_zone, brake_map)
            return max(braked, key=braked.get)

        new_z1 = new_leader(scores_z1)
        new_z2 = new_leader(scores_z2)
        new_z3 = new_leader(scores_z3)
        new_z4 = new_leader(scores_z4)
        new_z5 = new_leader(scores_z5)

        # None of the L4 numbers should remain as zone leaders
        for n in l4_grid:
            if n in {new_z1, new_z2, new_z3, new_z4, new_z5}:
                pytest.fail(f"L4 number {n} still leader of a zone — brake insufficient")

        # L5 grid should differ from L4 by at least 4/5 (total rotation expected)
        new_grid = {new_z1, new_z2, new_z3, new_z4, new_z5}
        overlap = len(new_grid & set(l4_grid))
        assert overlap == 0, f"Expected 0 overlap, got {overlap} numbers shared with L4"


# ═══════════════════════════════════════════════════════════════════════
# Test 3 — EM #15 → #16 rotation (terrain case)
# ═══════════════════════════════════════════════════════════════════════

class TestSimulationEm15to16Rotation:

    def test_simulation_em_15_to_16_rotation(self):
        """
        Terrain case: EM #15 (14/04) = 8-19-29-36-42 ⭐7-⭐12.
        EM #16 (17/04) = 8-19-29-36-49 ⭐6-⭐7 (4/5 shared, only 42→49 change).
        With V110 brake T-1 on [8, 19, 29, 36, 42], #16 cannot repeat.
        """
        engine = HybrideEngine(EM_CONFIG)
        # EM #15 canonical balls
        em15_grid = [8, 19, 29, 36, 42]

        # Simulated scores per EM zone (1-10, 11-20, 21-30, 31-40, 41-50)
        scores_z1 = {8: 17.0, 10: 15.0, 4: 14.0, 2: 12.0, 6: 11.0}
        scores_z2 = {19: 12.0, 14: 11.0, 11: 10.0, 17: 9.5, 15: 9.0}
        scores_z3 = {29: 16.0, 24: 14.0, 21: 13.0, 26: 12.0, 28: 11.0}
        scores_z4 = {36: 15.0, 35: 14.0, 34: 13.0, 33: 12.0, 31: 11.0}
        scores_z5 = {42: 19.0, 49: 18.0, 44: 17.0, 45: 16.0, 47: 15.0}

        # Brake T-1 for next gen (EM #16)
        brake_map = {n: 0.20 for n in em15_grid}

        def new_leader(scores_zone):
            braked = engine.apply_persistent_brake(scores_zone, brake_map)
            return max(braked, key=braked.get)

        new_z1 = new_leader(scores_z1)
        new_z2 = new_leader(scores_z2)
        new_z3 = new_leader(scores_z3)
        new_z4 = new_leader(scores_z4)
        new_z5 = new_leader(scores_z5)

        new_grid_set = {new_z1, new_z2, new_z3, new_z4, new_z5}
        # Expect at most 1 overlap (edge case: brake so strong another ball pops
        # in same slot but different zone)
        overlap = len(new_grid_set & set(em15_grid))
        assert overlap == 0, (
            f"With V110 brake 0.20 on T-1, EM #16 should not overlap #15. "
            f"Got overlap = {overlap}: {new_grid_set & set(em15_grid)}"
        )

    def test_stars_rotation_em(self):
        """V110 brake applies to stars too — ⭐7 and ⭐12 should rotate for #16."""
        engine = HybrideEngine(EM_CONFIG)
        star_scores = {7: 18.0, 12: 17.0, 6: 16.0, 10: 15.0, 3: 14.0, 8: 13.0}
        em15_stars = [7, 12]
        brake_stars = {n: 0.20 for n in em15_stars}
        braked = engine.apply_persistent_brake(star_scores, brake_stars)
        # 7: 18 × 0.20 = 3.6
        # 12: 17 × 0.20 = 3.4
        # 6: 16 → new leader
        top2 = sorted(braked, key=braked.get, reverse=True)[:2]
        assert 7 not in top2
        assert 12 not in top2
        assert 6 in top2, "⭐6 should rise to top after brake on 7/12"


# ═══════════════════════════════════════════════════════════════════════
# Test 4 — No rotation when brake_map empty (V123 behavior preserved)
# ═══════════════════════════════════════════════════════════════════════

class TestNoRotationWithoutBrake:

    def test_v123_behavior_preserved_when_brake_empty(self):
        """With brake_map={} (or None), scores are untouched — identical to V123."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {36: 22.0, 32: 20.0, 34: 18.0}
        # Same leader with or without brake when brake is empty
        leader_no_brake = max(scores, key=scores.get)
        result_empty = engine.apply_persistent_brake(scores, {})
        result_none = engine.apply_persistent_brake(scores, None)
        assert max(result_empty, key=result_empty.get) == leader_no_brake
        assert max(result_none, key=result_none.get) == leader_no_brake
        assert result_empty == scores
        assert result_none == scores
