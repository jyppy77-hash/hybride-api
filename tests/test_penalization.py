"""Tests pour services/penalization.py"""
import pytest
from services.penalization import compute_penalized_ranking, COEFF_LAST_DRAW, COEFF_SECOND_LAST


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
