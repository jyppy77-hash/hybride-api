"""Tests pour services/penalization.py — V2 hard-exclude & fenetre 4 tirages.

V1 legacy tests removed in V79 (F02 audit Engine HYBRIDE).
All callers now pass recent_draws (V2 mode required).
"""
import pytest
from services.penalization import (
    compute_penalized_ranking,
    PENALIZATION_COEFFS,
)


# ═══════════════════════════════════════════════
# V2 — recent_draws REQUIRED (V79)
# ═══════════════════════════════════════════════

def test_recent_draws_none_raises():
    """recent_draws=None raises ValueError since V79."""
    freq = {1: 100, 2: 90, 3: 80}
    with pytest.raises(ValueError, match="recent_draws is required"):
        compute_penalized_ranking(freq, set(), set(), range(1, 4), top_n=3)


def test_no_penalization_empty_recent():
    """Empty recent_draws list: classement par frequence brute."""
    freq = {1: 100, 2: 90, 3: 80, 4: 70, 5: 60, 6: 50}
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 7), top_n=3, recent_draws=[],
    )
    assert [x["number"] for x in top] == [1, 2, 3]
    assert [x["count"] for x in top] == [100, 90, 80]
    assert info["penalized_numbers"] == {}


def test_raw_counts_always_preserved():
    """Le champ count montre toujours la frequence brute."""
    freq = {1: 200, 2: 100, 3: 50}
    top, _ = compute_penalized_ranking(
        freq, set(), set(), range(1, 4), top_n=3, recent_draws=[{1, 2}],
    )
    for item in top:
        assert item["count"] == freq[item["number"]]


def test_top_before_penalization():
    """penalization_info contient le classement original avant penalites."""
    freq = {1: 100, 2: 95, 3: 90}
    _, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 4), top_n=2, recent_draws=[{1}],
    )
    before = info["top_before_penalization"]
    assert before[0]["number"] == 1  # classement brut : 1 reste premier
    assert before[1]["number"] == 2


def test_zero_frequency_not_affected():
    """Numero avec frequence 0 : penalisation sans effet."""
    freq = {1: 0, 2: 10, 3: 5}
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 4), top_n=2, recent_draws=[{1}],
    )
    assert top[0]["number"] == 2
    assert top[1]["number"] == 3


def test_tie_break_by_number_ascending():
    """En cas d'egalite de frequence penalisee, le plus petit numero gagne."""
    freq = {5: 50, 3: 50, 7: 50}
    top, _ = compute_penalized_ranking(
        freq, set(), set(), range(1, 8), top_n=3, recent_draws=[],
        unpopularity=False,  # disable to test pure tie-break
    )
    penalized_top = [x for x in top if x["count"] == 50]
    numbers = [x["number"] for x in penalized_top]
    assert numbers == sorted(numbers)


def test_loto_range():
    """Simule le cas reel Loto France : range(1, 50), top 5."""
    freq = {i: 50 - abs(i - 25) for i in range(1, 50)}  # pic au milieu
    recent = [{24, 25, 26, 27, 28}]  # T-1
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5, recent_draws=recent,
    )
    top_numbers = {x["number"] for x in top}
    assert not top_numbers & {24, 25, 26, 27, 28}  # T-1 excluded


def test_euromillions_stars_range():
    """Simule le cas reel EuroMillions etoiles : range(1, 13), top 3."""
    freq = {i: 30 + i for i in range(1, 13)}  # 12 a la plus haute freq
    recent = [{12, 11}]  # T-1
    top, _ = compute_penalized_ranking(
        freq, set(), set(), range(1, 13), top_n=3, recent_draws=recent,
        unpopularity=False,  # stars: no unpopularity (universe too small)
    )
    assert top[0]["number"] == 10  # 40 * 1.0 = 40 (12 and 11 excluded)


# ═══════════════════════════════════════════════
# V2 — HARD_EXCLUDE TESTS (6)
# ═══════════════════════════════════════════════

def test_hard_exclude_last_draw_removed_from_top():
    """Numero a score brut tres eleve est EXCLU du top quand dans T-1."""
    freq = {42: 96, 13: 60, 35: 55, 29: 50, 21: 48, 44: 45, 8: 40}
    recent = [{42}]  # T-1 only
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5, recent_draws=recent,
        unpopularity=False,
    )
    top_nums = [x["number"] for x in top]
    assert 42 not in top_nums
    assert top_nums == [13, 35, 29, 21, 44]
    assert 42 in info["excluded_numbers"]


def test_hard_exclude_multiple_numbers():
    """Multiple numeros T-1 exclus, top rempli par les suivants."""
    freq = {42: 96, 13: 60, 35: 55, 29: 50, 21: 48, 44: 45, 8: 40, 7: 38}
    recent = [{42, 13, 35}]  # 3 numeros du dernier tirage
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5, recent_draws=recent,
        unpopularity=False,
    )
    top_nums = [x["number"] for x in top]
    assert 42 not in top_nums
    assert 13 not in top_nums
    assert 35 not in top_nums
    assert top_nums == [29, 21, 44, 8, 7]


def test_hard_exclude_preserves_raw_freq():
    """Les frequences brutes ne sont pas modifiees — count est toujours la freq originale."""
    freq = {42: 96, 13: 60, 35: 55, 29: 50, 21: 48}
    recent = [{42}]
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=4, recent_draws=recent,
    )
    for item in top:
        assert item["count"] == freq[item["number"]]
    # Also check top_before still has 42 at rank 1
    assert info["top_before_penalization"][0]["number"] == 42
    assert info["top_before_penalization"][0]["count"] == 96


def test_hard_exclude_excluded_numbers_tracked():
    """Le champ excluded_numbers liste les numeros exclus."""
    freq = {1: 100, 2: 90, 3: 80, 4: 70, 5: 60}
    recent = [{1, 2}]
    _, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 6), top_n=3, recent_draws=recent,
    )
    assert sorted(info["excluded_numbers"]) == [1, 2]
    assert info["penalized_numbers"][1] == 0.0
    assert info["penalized_numbers"][2] == 0.0


def test_hard_exclude_em_etoiles():
    """Hard-exclude sur les etoiles EM (range 1-12, top 3)."""
    freq = {i: 30 + i for i in range(1, 13)}  # 12=42, 11=41, 10=40, ...
    recent = [{12, 11}]  # T-1 etoiles
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 13), top_n=3, recent_draws=recent,
        unpopularity=False,  # stars: no unpopularity
    )
    top_nums = [x["number"] for x in top]
    assert 12 not in top_nums
    assert 11 not in top_nums
    assert top_nums == [10, 9, 8]  # next 3 by freq


def test_hard_exclude_loto_chance():
    """Hard-exclude sur le numero chance Loto (range 1-10, top 3)."""
    freq = {i: 50 + i * 3 for i in range(1, 11)}  # 10=80, 9=77, 8=74, ...
    recent = [{10}]  # T-1 chance
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 11), top_n=3, recent_draws=recent,
        unpopularity=False,  # chance: no unpopularity
    )
    top_nums = [x["number"] for x in top]
    assert 10 not in top_nums
    assert top_nums == [9, 8, 7]


# ═══════════════════════════════════════════════
# V2 — FENETRE 4 TIRAGES TESTS (6)
# ═══════════════════════════════════════════════

def test_four_draw_window_t2_penalty():
    """Numero dans T-2 penalise a x0.65."""
    freq = {1: 100, 2: 66, 3: 60}
    recent = [{99}, {1}]  # T-1={99}, T-2={1}
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 100), top_n=3, recent_draws=recent,
    )
    # 1: 100*0.65=65 < 66 (numero 2)
    assert top[0]["number"] == 2
    assert top[1]["number"] == 1
    assert info["penalized_numbers"][1] == 0.65


def test_four_draw_window_t3_penalty():
    """Numero dans T-3 penalise a x0.80."""
    freq = {1: 100, 2: 81, 3: 70}
    recent = [{99}, {98}, {1}]  # T-3={1}
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 100), top_n=3, recent_draws=recent,
    )
    # 1: 100*0.80=80 < 81 (numero 2)
    assert top[0]["number"] == 2
    assert top[1]["number"] == 1
    assert info["penalized_numbers"][1] == 0.80


def test_four_draw_window_t4_penalty():
    """Numero dans T-4 penalise a x0.90."""
    freq = {1: 100, 2: 91, 3: 70}
    recent = [{99}, {98}, {97}, {1}]  # T-4={1}
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 100), top_n=3, recent_draws=recent,
    )
    # 1: 100*0.90=90 < 91 (numero 2)
    assert top[0]["number"] == 2
    assert top[1]["number"] == 1
    assert info["penalized_numbers"][1] == 0.90


def test_four_draw_window_t1_excluded():
    """Numero dans T-1 est EXCLU, pas juste penalise."""
    freq = {1: 1000, 2: 50, 3: 40, 4: 30, 5: 20, 6: 10}
    recent = [{1}, {99}, {98}, {97}]
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 100), top_n=5, recent_draws=recent,
    )
    top_nums = [x["number"] for x in top]
    assert 1 not in top_nums  # excluded, not just penalized
    assert 1 in info["excluded_numbers"]


def test_four_draw_window_t5_no_penalty():
    """Numero sorti il y a 5 tirages (au-dela de la fenetre) : aucune penalite."""
    freq = {1: 100, 2: 50}
    # 5 draws — only 4 coefficients defined, so T-5 = no penalty
    recent = [{99}, {98}, {97}, {96}, {1}]
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 100), top_n=2, recent_draws=recent,
    )
    assert top[0]["number"] == 1  # no penalty, freq=100 wins
    assert 1 not in info["penalized_numbers"]


def test_four_draw_window_same_number_multiple_draws():
    """Numero present dans T-1 ET T-3 : la plus forte penalite (T-1 exclusion) s'applique."""
    freq = {1: 100, 2: 50, 3: 40, 4: 30, 5: 20, 6: 10}
    recent = [{1}, {99}, {1}, {98}]  # 1 in T-1 AND T-3
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 100), top_n=5, recent_draws=recent,
    )
    top_nums = [x["number"] for x in top]
    assert 1 not in top_nums  # T-1 exclusion wins over T-3 x0.80
    assert 1 in info["excluded_numbers"]


# ═══════════════════════════════════════════════
# V2 — INTEGRATION TESTS (2)
# ═══════════════════════════════════════════════

def test_integration_loto_full_range():
    """49 boules Loto avec 4 tirages realistes — top 5 correct."""
    freq = {i: 50 - abs(i - 25) for i in range(1, 50)}
    # freq: 1=26, 2=27, ... 24=49, 25=50, 26=49, ... 49=26
    recent = [
        {24, 25, 26, 27, 28},  # T-1: excluded
        {23, 24, 25, 26, 27},  # T-2: x0.65
        {22, 23, 24, 25, 26},  # T-3: x0.80
        {21, 22, 23, 24, 25},  # T-4: x0.90
    ]
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5, recent_draws=recent,
    )
    top_nums = {x["number"] for x in top}
    # T-1 numbers must NOT appear in top
    assert not top_nums & {24, 25, 26, 27, 28}
    # excluded_numbers should list T-1
    assert set(info["excluded_numbers"]) == {24, 25, 26, 27, 28}
    # Top 5 should still contain high-freq numbers not in T-1
    assert len(top) == 5
    for item in top:
        assert item["count"] == freq[item["number"]]


def test_integration_em_boules_et_etoiles():
    """50 boules + 12 etoiles EM avec 4 tirages — top 5 boules ET top 3 etoiles."""
    freq_b = {i: 60 - abs(i - 25) for i in range(1, 51)}
    freq_e = {i: 30 + i for i in range(1, 13)}

    recent_b = [
        {25, 26, 27, 28, 29},  # T-1 boules
        {24, 25, 26, 27, 28},  # T-2
        {23, 24, 25, 26, 27},  # T-3
        {22, 23, 24, 25, 26},  # T-4
    ]
    recent_e = [
        {12, 11},  # T-1 etoiles
        {11, 10},  # T-2
        {10, 9},   # T-3
        {9, 8},    # T-4
    ]

    top_b, info_b = compute_penalized_ranking(
        freq_b, set(), set(), range(1, 51), top_n=5, recent_draws=recent_b,
    )
    top_e, info_e = compute_penalized_ranking(
        freq_e, set(), set(), range(1, 13), top_n=3, recent_draws=recent_e,
    )

    # Boules: T-1 excluded
    top_b_nums = {x["number"] for x in top_b}
    assert not top_b_nums & {25, 26, 27, 28, 29}
    assert set(info_b["excluded_numbers"]) == {25, 26, 27, 28, 29}
    assert len(top_b) == 5

    # Etoiles: T-1 excluded
    top_e_nums = {x["number"] for x in top_e}
    assert 12 not in top_e_nums
    assert 11 not in top_e_nums
    assert set(info_e["excluded_numbers"]) == {11, 12}
    assert len(top_e) == 3


# ═══════════════════════════════════════════════════════════════════════
# V55-ter — F06: superstitious set aligned with config
# ═══════════════════════════════════════════════════════════════════════

class TestCollisionRiskSuperstitious:

    def test_superstitious_matches_config(self):
        """get_collision_risk_numbers() superstition set matches config._SUPERSTITIOUS."""
        from config.engine import _SUPERSTITIOUS
        from services.penalization import get_collision_risk_numbers
        result = get_collision_risk_numbers("euromillions")
        assert set(result["superstition"]) == set(_SUPERSTITIOUS)

    def test_superstitious_matches_loto(self):
        """Loto collision risk uses the same superstitious set."""
        from config.engine import _SUPERSTITIOUS
        from services.penalization import get_collision_risk_numbers
        result = get_collision_risk_numbers("loto")
        assert set(result["superstition"]) == set(_SUPERSTITIOUS)


# ═══════════════════════════════════════════════════════════════════════
# V79 — F02: V1 legacy path removed, excluded_numbers always present
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════
# V102 — DECAY STATE INTEGRATION (7)
# ═══════════════════════════════════════════════

def test_decay_none_no_change():
    """decay_state=None → identical to existing behavior (non-regression)."""
    freq = {1: 100, 2: 90, 3: 80, 4: 70, 5: 60}
    top_without, info_without = compute_penalized_ranking(
        freq, set(), set(), range(1, 6), top_n=3, recent_draws=[], decay_state=None,
    )
    top_empty, info_empty = compute_penalized_ranking(
        freq, set(), set(), range(1, 6), top_n=3, recent_draws=[], decay_state={},
    )
    assert [x["number"] for x in top_without] == [x["number"] for x in top_empty]
    assert info_without["decay_applied"] == {}
    assert info_empty["decay_applied"] == {}


def test_decay_misses_reduce_ranking():
    """Numbers with consecutive_misses > 0 get reduced score, changing ranking."""
    freq = {1: 100, 2: 95, 3: 80}
    # Number 1 has 3 consecutive misses → multiplier ~0.673 → penalized=67.3
    # Number 2 has 0 misses → stays 95
    decay = {1: 3, 2: 0}
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 4), top_n=3, recent_draws=[], decay_state=decay,
    )
    assert top[0]["number"] == 2  # 95 * 1.0 = 95 > 67.3
    assert top[1]["number"] == 3  # 80 * 1.0 = 80 > 67.3
    assert top[2]["number"] == 1  # 100 * 0.673 ≈ 67.3
    assert 1 in info["decay_applied"]
    assert 2 not in info["decay_applied"]  # misses=0, no decay


def test_decay_misses_zero_no_impact():
    """Numbers with consecutive_misses=0 → multiplier=1.0, no change."""
    freq = {1: 100, 2: 90}
    decay = {1: 0, 2: 0}
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 3), top_n=2, recent_draws=[], decay_state=decay,
    )
    assert top[0]["number"] == 1
    assert top[1]["number"] == 2
    assert info["decay_applied"] == {}


def test_decay_floor_at_050():
    """5+ consecutive misses → floor multiplier 0.50."""
    freq = {1: 100, 2: 51}
    decay = {1: 10}  # way past floor
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 3), top_n=2, recent_draws=[], decay_state=decay,
    )
    # 100 * 0.50 = 50 < 51
    assert top[0]["number"] == 2
    assert top[1]["number"] == 1
    assert info["decay_applied"][1] == 0.50


def test_decay_skips_excluded_t1():
    """T-1 excluded numbers are not affected by decay (already out)."""
    freq = {1: 200, 2: 90, 3: 80, 4: 70, 5: 60, 6: 50}
    decay = {1: 5}  # number 1 has high decay BUT is T-1 excluded
    recent = [{1}]  # T-1
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 7), top_n=3, recent_draws=recent, decay_state=decay,
    )
    assert 1 not in [x["number"] for x in top]  # excluded by T-1
    assert 1 in info["excluded_numbers"]
    assert 1 not in info["decay_applied"]  # decay not applied to excluded


def test_decay_loto_chance():
    """Loto chance range(1,11) with decay on secondary numbers."""
    freq = {i: 50 + i * 3 for i in range(1, 11)}  # 10=80, 9=77, ...
    decay = {10: 4, 9: 3}  # top 2 have high decay
    recent = []
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 11), top_n=3, recent_draws=recent, decay_state=decay,
    )
    # 10: 80 * ~0.552 = 44.2, 9: 77 * ~0.673 = 51.8, 8: 74 * 1.0 = 74
    assert top[0]["number"] == 8
    assert 10 in info["decay_applied"]
    assert 9 in info["decay_applied"]


def test_decay_em_etoiles():
    """EM stars range(1,13) with decay."""
    freq = {i: 30 + i for i in range(1, 13)}  # 12=42, 11=41, 10=40, ...
    decay = {12: 3, 11: 2}
    recent = []
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 13), top_n=3, recent_draws=recent, decay_state=decay,
        unpopularity=False,  # stars: no unpopularity
    )
    # 12: 42 * ~0.673 = 28.3, 11: 41 * ~0.788 = 32.3, 10: 40 * 1.0 = 40
    assert top[0]["number"] == 10  # 40 wins
    assert 12 in info["decay_applied"]
    assert 11 in info["decay_applied"]


# ═══════════════════════════════════════════════
# V104 — ZONE STRATIFICATION (10)
# ═══════════════════════════════════════════════

from config.engine import LOTO_ZONES, EM_ZONES


def test_zones_none_no_stratified():
    """zones=None → stratified_top is empty (non-regression)."""
    freq = {i: 50 for i in range(1, 50)}
    _, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5, recent_draws=[], zones=None,
    )
    assert info["stratified_top"] == []


def test_stratified_returns_5_numbers():
    """With LOTO_ZONES → stratified_top has exactly 5 entries."""
    freq = {i: 100 - i for i in range(1, 50)}
    _, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5, recent_draws=[], zones=LOTO_ZONES,
    )
    assert len(info["stratified_top"]) == 5


def test_stratified_one_per_zone():
    """Each stratified number falls within its declared zone."""
    freq = {i: 100 - i for i in range(1, 50)}
    _, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5, recent_draws=[], zones=LOTO_ZONES,
    )
    for entry in info["stratified_top"]:
        lo, hi = map(int, entry["zone"].split("-"))
        assert lo <= entry["number"] <= hi


def test_stratified_picks_best_in_zone():
    """Stratified picks the highest-scored number in each zone."""
    # Zone 1 (1-10): number 1 has highest freq
    freq = {i: 100 - i for i in range(1, 50)}
    _, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5, recent_draws=[], zones=LOTO_ZONES,
        unpopularity=False,  # test pure stratification logic
    )
    zone_tops = {e["zone"]: e["number"] for e in info["stratified_top"]}
    assert zone_tops["1-10"] == 1   # freq=99
    assert zone_tops["11-20"] == 11  # freq=89
    assert zone_tops["21-30"] == 21  # freq=79
    assert zone_tops["31-40"] == 31  # freq=69
    assert zone_tops["41-49"] == 41  # freq=59


def test_stratified_hard_exclude_skips_t1():
    """T-1 excluded number is skipped — next best in zone is selected."""
    freq = {i: 100 - i for i in range(1, 50)}
    # T-1 = {1} — number 1 excluded from zone 1-10
    _, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5,
        recent_draws=[{1}], zones=LOTO_ZONES,
    )
    zone_tops = {e["zone"]: e["number"] for e in info["stratified_top"]}
    assert zone_tops["1-10"] == 2  # 1 is excluded, 2 is next best


def test_stratified_em_zones():
    """EM zones (1-50) produce 5 stratified numbers."""
    freq = {i: 60 - abs(i - 25) for i in range(1, 51)}
    _, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 51), top_n=5, recent_draws=[], zones=EM_ZONES,
    )
    assert len(info["stratified_top"]) == 5
    for entry in info["stratified_top"]:
        lo, hi = map(int, entry["zone"].split("-"))
        assert lo <= entry["number"] <= hi


def test_stratified_loto_zone5_is_41_49():
    """Loto zone 5 spans 41-49 (9 numbers, not 10)."""
    freq = {i: i for i in range(1, 50)}  # higher number = higher freq
    _, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5, recent_draws=[], zones=LOTO_ZONES,
    )
    zone_tops = {e["zone"]: e["number"] for e in info["stratified_top"]}
    assert zone_tops["41-49"] == 49  # highest in zone


def test_stratified_with_decay():
    """Decay reduces a zone's top number, promoting the next one."""
    freq = {i: 100 - i for i in range(1, 50)}
    # Number 1 (zone 1) has decay misses=5 → floor 0.50
    # freq=99*0.50=49.5, number 2 has freq=98*1.0=98 → 2 wins zone 1
    decay = {1: 5}
    _, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5,
        recent_draws=[], decay_state=decay, zones=LOTO_ZONES,
    )
    zone_tops = {e["zone"]: e["number"] for e in info["stratified_top"]}
    assert zone_tops["1-10"] == 2  # decay pushed 1 down


def test_stratified_preserves_global_top():
    """Global top_list is unchanged by zones parameter."""
    freq = {i: 100 - i for i in range(1, 50)}
    top_no_zones, _ = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5, recent_draws=[], zones=None,
    )
    top_with_zones, _ = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5, recent_draws=[], zones=LOTO_ZONES,
    )
    assert [x["number"] for x in top_no_zones] == [x["number"] for x in top_with_zones]


def test_stratified_each_zone_has_entry():
    """Even with heavy exclusions, each zone produces an entry."""
    freq = {i: 50 for i in range(1, 50)}
    # Exclude many numbers in zone 1 via T-1
    recent = [{1, 2, 3, 4, 5, 6, 7, 8}]
    _, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5,
        recent_draws=recent, zones=LOTO_ZONES,
    )
    zones_found = {e["zone"] for e in info["stratified_top"]}
    assert "1-10" in zones_found  # 9 and 10 still available


# ═══════════════════════════════════════════════
# V106 — UNPOPULARITY SCORING (9)
# ═══════════════════════════════════════════════

from services.penalization import get_unpopularity_multiplier


def test_unpop_lucky_seven():
    """Number 7 gets lucky-seven malus 0.80."""
    assert get_unpopularity_multiplier(7) == pytest.approx(0.80)


def test_unpop_birthday_month():
    """Number 3 (birthday month, not 7) gets 0.85."""
    assert get_unpopularity_multiplier(3) == pytest.approx(0.85)


def test_unpop_birthday_month_plus_multiple5():
    """Number 5 = birthday month (0.85) × multiple of 5 (0.93) = 0.7905."""
    assert get_unpopularity_multiplier(5) == pytest.approx(0.85 * 0.93)


def test_unpop_birthday_day():
    """Number 15 = birthday day (0.92) × multiple of 5 (0.93) = 0.8556."""
    assert get_unpopularity_multiplier(15) == pytest.approx(0.92 * 0.93)


def test_unpop_birthday_day_not_multiple5():
    """Number 17 = birthday day only (0.92)."""
    assert get_unpopularity_multiplier(17) == pytest.approx(0.92)


def test_unpop_high_number_no_malus():
    """Number 38 = no malus (1.0)."""
    assert get_unpopularity_multiplier(38) == pytest.approx(1.0)


def test_unpop_high_multiple5():
    """Number 35 = multiple of 5 only (0.93)."""
    assert get_unpopularity_multiplier(35) == pytest.approx(0.93)


def test_unpop_43_no_malus():
    """Number 43 = no malus (1.0)."""
    assert get_unpopularity_multiplier(43) == pytest.approx(1.0)


def test_unpop_ranking_favors_high_numbers():
    """With equal freq, high numbers (no malus) rank above low numbers (malus)."""
    freq = {i: 100 for i in range(1, 50)}
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5,
        recent_draws=[], unpopularity=True,
    )
    # All top 5 should be > 31 (no malus) since freq is equal
    for item in top:
        assert item["number"] > 31, f"Expected >31, got {item['number']}"
    assert len(info["unpopularity_applied"]) > 0


def test_unpop_disabled_no_change():
    """unpopularity=False → no unpopularity applied (non-regression)."""
    freq = {i: 100 for i in range(1, 50)}
    top_off, info_off = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5,
        recent_draws=[], unpopularity=False,
    )
    assert info_off["unpopularity_applied"] == {}
    # With unpopularity off + equal freq, top 5 should be 1-5 (lowest number tie-break)
    assert [x["number"] for x in top_off] == [1, 2, 3, 4, 5]


def test_unpop_cumulates_with_decay():
    """Decay × unpopularity cumulate correctly."""
    freq = {7: 200, 38: 100}
    # Number 7: freq=200, decay misses=2 → mult ~0.788, unpop=0.80
    # → 200 × 0.788 × 0.80 = 126.1
    # Number 38: freq=100, no decay, no unpop → 100
    decay = {7: 2}
    top, _ = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=2,
        recent_draws=[], decay_state=decay, unpopularity=True,
    )
    assert top[0]["number"] == 7  # 126.1 > 100 — still first despite penalties
    assert top[1]["number"] == 38


class TestV79NoV1Legacy:

    def test_no_v1_constants_in_module(self):
        """V1 constants COEFF_LAST_DRAW/COEFF_SECOND_LAST are removed."""
        import services.penalization as mod
        assert not hasattr(mod, "COEFF_LAST_DRAW")
        assert not hasattr(mod, "COEFF_SECOND_LAST")

    def test_excluded_numbers_always_in_info(self):
        """excluded_numbers is always present in penalization_info (even if empty)."""
        freq = {1: 100, 2: 90, 3: 80}
        _, info = compute_penalized_ranking(
            freq, set(), set(), range(1, 4), top_n=3, recent_draws=[],
        )
        assert "excluded_numbers" in info
        assert info["excluded_numbers"] == []
