"""Tests pour services/penalization.py — V1 legacy + V2 hard-exclude & fenetre 4 tirages."""
import pytest
from services.penalization import (
    compute_penalized_ranking,
    COEFF_LAST_DRAW, COEFF_SECOND_LAST,
    PENALIZATION_COEFFS,
)


# ═══════════════════════════════════════════════
# EXISTING V1 LEGACY TESTS (10) — must all pass
# ═══════════════════════════════════════════════

def test_no_penalization():
    """Sans tirages recents, classement par frequence brute."""
    freq = {1: 100, 2: 90, 3: 80, 4: 70, 5: 60, 6: 50}
    top, info = compute_penalized_ranking(freq, set(), set(), range(1, 7), top_n=3)
    assert [x["number"] for x in top] == [1, 2, 3]
    assert [x["count"] for x in top] == [100, 90, 80]
    assert info["penalized_numbers"] == {}


def test_last_draw_penalty_drops_ranking():
    """Numero du dernier tirage penalise et recule dans le classement."""
    freq = {1: 100, 2: 95, 3: 90}
    # Numero 1 au dernier tirage : 100 * 0.7 = 70 < 95 et 90
    top, info = compute_penalized_ranking(freq, {1}, set(), range(1, 4), top_n=3)
    assert top[0]["number"] == 2  # 95 * 1.0 = 95
    assert top[1]["number"] == 3  # 90 * 1.0 = 90
    assert top[2]["number"] == 1  # 100 * 0.7 = 70
    assert top[2]["count"] == 100  # frequence brute preservee


def test_second_last_penalty():
    """Numero de l'avant-dernier tirage penalise a 0.85."""
    freq = {1: 100, 2: 90, 3: 80}
    # Numero 1 : 100 * 0.85 = 85 => passe sous 2 (90) mais reste au-dessus de 3 (80)
    top, info = compute_penalized_ranking(freq, set(), {1}, range(1, 4), top_n=3)
    assert top[0]["number"] == 2  # 90
    assert top[1]["number"] == 1  # 85 penalise
    assert top[2]["number"] == 3  # 80
    assert info["penalized_numbers"][1] == COEFF_SECOND_LAST


def test_both_draws_worst_penalty():
    """Numero present dans les 2 derniers tirages : pire penalite (0.7), pas de cumul."""
    freq = {1: 100, 2: 71, 3: 69}
    top, info = compute_penalized_ranking(freq, {1}, {1}, range(1, 4), top_n=3)
    # Numero 1 : 100 * 0.7 = 70 < 71 (numero 2)
    assert top[0]["number"] == 2
    assert top[1]["number"] == 1
    assert info["penalized_numbers"][1] == COEFF_LAST_DRAW  # 0.7, pas 0.595


def test_raw_counts_always_preserved():
    """Le champ count montre toujours la frequence brute."""
    freq = {1: 200, 2: 100, 3: 50}
    top, _ = compute_penalized_ranking(freq, {1, 2}, set(), range(1, 4), top_n=3)
    for item in top:
        assert item["count"] == freq[item["number"]]


def test_top_before_penalization():
    """penalization_info contient le classement original avant penalites."""
    freq = {1: 100, 2: 95, 3: 90}
    _, info = compute_penalized_ranking(freq, {1}, set(), range(1, 4), top_n=2)
    before = info["top_before_penalization"]
    assert before[0]["number"] == 1  # classement brut : 1 reste premier
    assert before[1]["number"] == 2


def test_zero_frequency_not_affected():
    """Numero avec frequence 0 : penalisation sans effet."""
    freq = {1: 0, 2: 10, 3: 5}
    top, info = compute_penalized_ranking(freq, {1}, set(), range(1, 4), top_n=2)
    assert top[0]["number"] == 2
    assert top[1]["number"] == 3


def test_tie_break_by_number_ascending():
    """En cas d'egalite de frequence penalisee, le plus petit numero gagne."""
    freq = {5: 50, 3: 50, 7: 50}
    top, _ = compute_penalized_ranking(freq, set(), set(), range(1, 8), top_n=3)
    penalized_top = [x for x in top if x["count"] == 50]
    numbers = [x["number"] for x in penalized_top]
    assert numbers == sorted(numbers)


def test_loto_range():
    """Simule le cas reel Loto France : range(1, 50), top 5."""
    freq = {i: 50 - abs(i - 25) for i in range(1, 50)}  # pic au milieu
    last = {24, 25, 26, 27, 28}
    top, info = compute_penalized_ranking(freq, last, set(), range(1, 50), top_n=5)
    # Les numeros 24-28 sont penalises, d'autres doivent monter
    top_numbers = {x["number"] for x in top}
    assert not top_numbers.issubset(last)  # au moins un numero hors dernier tirage


def test_euromillions_stars_range():
    """Simule le cas reel EuroMillions etoiles : range(1, 13), top 3."""
    freq = {i: 30 + i for i in range(1, 13)}  # 12 a la plus haute freq
    last_stars = {12, 11}
    top, _ = compute_penalized_ranking(freq, last_stars, set(), range(1, 13), top_n=3)
    # 12: 42*0.7=29.4, 11: 41*0.7=28.7 => devraient reculer
    assert top[0]["number"] == 10  # 40 * 1.0 = 40


# ═══════════════════════════════════════════════
# V2 — HARD_EXCLUDE TESTS (6)
# ═══════════════════════════════════════════════

def test_hard_exclude_last_draw_removed_from_top():
    """Numero a score brut tres eleve est EXCLU du top quand dans T-1."""
    freq = {42: 96, 13: 60, 35: 55, 29: 50, 21: 48, 44: 45, 8: 40}
    recent = [{42}]  # T-1 only
    top, info = compute_penalized_ranking(
        freq, set(), set(), range(1, 50), top_n=5, recent_draws=recent,
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
# V2 — RETROCOMPATIBILITE TESTS (2)
# ═══════════════════════════════════════════════

def test_backward_compat_two_draws():
    """Appel avec l'ancienne signature (2 tirages) fonctionne comme V1."""
    freq = {1: 100, 2: 95, 3: 90}
    top, info = compute_penalized_ranking(freq, {1}, set(), range(1, 4), top_n=3)
    # V1 behavior: 1 penalized at 0.7 -> 70
    assert top[0]["number"] == 2
    assert top[1]["number"] == 3
    assert top[2]["number"] == 1
    assert info["penalized_numbers"][1] == COEFF_LAST_DRAW
    assert "excluded_numbers" not in info  # V1 doesn't have this field


def test_backward_compat_no_recent_draws():
    """Appel sans recent_draws ni tirages recents : classement brut."""
    freq = {1: 100, 2: 90, 3: 80}
    top, info = compute_penalized_ranking(freq, set(), set(), range(1, 4), top_n=3)
    assert [x["number"] for x in top] == [1, 2, 3]
    assert info["penalized_numbers"] == {}
    assert "excluded_numbers" not in info


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
