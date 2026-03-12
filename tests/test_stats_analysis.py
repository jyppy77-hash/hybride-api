"""Tests pour services/stats_analysis.py + services/penalization.get_collision_risk_numbers."""
import math
import pytest

from services.stats_analysis import (
    compute_zscore,
    compute_zscore_batch,
    detect_windowing_artifact,
    should_inject_pedagogical_context,
    PEDAGOGICAL_CONTEXT,
)
from services.penalization import get_collision_risk_numbers


# ═══════════════════════════════════════════════
# SCORE Z TESTS (8)
# ═══════════════════════════════════════════════

def test_zscore_single_number_above_expected():
    """freq=71, n=521, p=0.10 -> z_score positif, deviation ~+36%."""
    result = compute_zscore(observed=71, n_draws=521, p=0.10)
    assert result["observed"] == 71
    assert result["expected"] == 52.1
    assert result["z_score"] > 2.5  # ~2.76
    assert result["z_score"] < 3.0
    assert result["deviation_pct"] > 35.0
    assert result["deviation_pct"] < 37.0
    assert result["p_value"] < 0.01  # significant at individual level


def test_zscore_single_number_below_expected():
    """freq=35, n=521, p=0.10 -> z_score negatif."""
    result = compute_zscore(observed=35, n_draws=521, p=0.10)
    assert result["z_score"] < 0
    assert result["deviation_pct"] < 0
    assert result["expected"] == 52.1


def test_zscore_bonferroni_not_significant():
    """z~2.76, p~0.0058 -> bonferroni_significant=False (seuil 0.001 pour 50 numeros)."""
    result = compute_zscore(observed=71, n_draws=521, p=0.10)
    # p_value ~ 0.0058, bonferroni threshold for 50 nums = 0.001
    assert result["p_value"] > 0.001  # NOT bonferroni significant
    # Check via batch which sets the flag
    batch = compute_zscore_batch({1: 71}, n_draws=521, n_balls_drawn=5, n_balls_total=50)
    assert batch[0]["bonferroni_significant"] is False


def test_zscore_bonferroni_significant():
    """Cas extreme : freq=90 sur 521 tirages -> bonferroni significant."""
    result = compute_zscore(observed=90, n_draws=521, p=0.10)
    # z should be very high (~5.5+)
    assert result["z_score"] > 5.0
    assert result["p_value"] < 0.001
    # Check via batch
    batch = compute_zscore_batch({1: 90}, n_draws=521, n_balls_drawn=5, n_balls_total=50)
    assert batch[0]["bonferroni_significant"] is True


def test_zscore_loto_params():
    """Loto France : p = 5/49 ~= 0.10204."""
    p_loto = 5 / 49
    result = compute_zscore(observed=55, n_draws=500, p=p_loto)
    expected = 500 * p_loto  # ~51.02
    assert abs(result["expected"] - round(expected, 2)) < 0.01
    assert result["z_score"] > 0  # 55 > 51.02


def test_zscore_em_params():
    """EuroMillions boules : p = 5/50 = 0.10."""
    result = compute_zscore(observed=52, n_draws=500, p=5/50)
    assert result["expected"] == 50.0  # 500 * 0.10
    assert result["z_score"] > 0  # 52 > 50


def test_zscore_etoiles_params():
    """EuroMillions etoiles : p = 2/12 ~= 0.1667."""
    p_etoiles = 2 / 12
    result = compute_zscore(observed=100, n_draws=500, p=p_etoiles)
    expected = 500 * p_etoiles  # ~83.33
    assert abs(result["expected"] - round(expected, 2)) < 0.01
    assert result["z_score"] > 0  # 100 > 83.33


def test_zscore_chance_params():
    """Loto chance : p = 1/10 = 0.10."""
    result = compute_zscore(observed=60, n_draws=500, p=1/10)
    assert result["expected"] == 50.0
    assert result["z_score"] > 0


# ═══════════════════════════════════════════════
# ANTI-COLLISION TESTS (4)
# ═══════════════════════════════════════════════

def test_collision_risk_calendar_bias():
    """Numeros 1-31 dans calendar_bias."""
    result = get_collision_risk_numbers(game="euromillions")
    assert set(result["calendar_bias"]) == set(range(1, 32))


def test_collision_risk_superstition():
    """7 et 13 dans superstition."""
    result = get_collision_risk_numbers(game="euromillions")
    assert 7 in result["superstition"]
    assert 13 in result["superstition"]


def test_collision_risk_em():
    """game=euromillions -> max_num=50, high_ev_range 32-50."""
    result = get_collision_risk_numbers(game="euromillions")
    assert result["max_num"] == 50
    assert 32 in result["high_ev_range"]
    assert 50 in result["high_ev_range"]
    assert 31 not in result["high_ev_range"]


def test_collision_risk_loto():
    """game=loto -> max_num=49, high_ev_range 32-49."""
    result = get_collision_risk_numbers(game="loto")
    assert result["max_num"] == 49
    assert 32 in result["high_ev_range"]
    assert 49 in result["high_ev_range"]
    assert 50 not in result["high_ev_range"]


# ═══════════════════════════════════════════════
# ARTEFACT DE FENETRAGE TESTS (4)
# ═══════════════════════════════════════════════

def test_windowing_artifact_detected():
    """Numero top 3 sur fenetre courte mais top 20 sur fenetre longue -> artifact."""
    # freq_3A: num 35 is ranked 2nd
    freq_3a = {i: 100 - i for i in range(1, 51)}
    freq_3a[35] = 110  # boost to rank 2
    # freq_global: num 35 is ranked ~20th
    freq_global = {i: 100 - i for i in range(1, 51)}
    freq_global[35] = 30  # low rank

    result = detect_windowing_artifact(35, {"3A": freq_3a, "GLOBAL": freq_global})
    assert result["is_windowing_artifact"] is True
    assert result["ranks_by_window"]["3A"] <= 5
    assert result["ranks_by_window"]["GLOBAL"] > 15


def test_windowing_artifact_not_detected():
    """Numero top 5 sur toutes les fenetres -> pas d'artifact."""
    freq_3a = {i: 100 - i for i in range(1, 51)}
    freq_3a[3] = 120  # top on 3A
    freq_global = {i: 100 - i for i in range(1, 51)}
    freq_global[3] = 115  # still top on global

    result = detect_windowing_artifact(3, {"3A": freq_3a, "GLOBAL": freq_global})
    assert result["is_windowing_artifact"] is False


def test_windowing_artifact_multiple_windows():
    """Test avec 3 fenetres (3A, 5A, 7A)."""
    freq_3a = {i: 50 for i in range(1, 51)}
    freq_3a[42] = 100  # rank 1 on 3A
    freq_5a = {i: 50 for i in range(1, 51)}
    freq_5a[42] = 80  # still high on 5A
    freq_7a = {i: 50 for i in range(1, 51)}
    freq_7a[42] = 35  # low on 7A -> rank 50

    result = detect_windowing_artifact(42, {"3A": freq_3a, "5A": freq_5a, "7A": freq_7a})
    assert result["ranks_by_window"]["3A"] == 1
    assert result["ranks_by_window"]["7A"] > 15
    assert result["is_windowing_artifact"] is True


def test_windowing_artifact_loto():
    """Meme logique appliquee au Loto France (49 numeros)."""
    freq_3a = {i: 60 for i in range(1, 50)}
    freq_3a[13] = 90  # rank 1 on 3A
    freq_global = {i: 60 for i in range(1, 50)}
    freq_global[13] = 40  # low on global

    result = detect_windowing_artifact(13, {"3A": freq_3a, "GLOBAL": freq_global})
    assert result["is_windowing_artifact"] is True
    assert result["number"] == 13


# ═══════════════════════════════════════════════
# CONTEXTE CHATBOT TESTS (2)
# ═══════════════════════════════════════════════

def test_zscore_context_injected_for_hot_numbers():
    """Le contexte pedagogique est detecte pour les questions sur les numeros chauds."""
    assert should_inject_pedagogical_context("Quels sont les numéros les plus chauds ?")
    assert should_inject_pedagogical_context("Which numbers are most frequently drawn?")
    assert should_inject_pedagogical_context("le 42 est en retard")
    assert should_inject_pedagogical_context("top 5 des numéros les plus sortis")
    assert should_inject_pedagogical_context("Quelle est la tendance actuelle ?")
    assert should_inject_pedagogical_context("Welche Zahlen sind am heisssten?")  # DE


def test_zscore_context_not_injected_for_other_questions():
    """Le contexte n'est PAS injecte pour les questions non liees aux frequences."""
    assert not should_inject_pedagogical_context("Bonjour")
    assert not should_inject_pedagogical_context("Comment fonctionne le moteur ?")
    assert not should_inject_pedagogical_context("Quand est le prochain tirage ?")
    assert not should_inject_pedagogical_context("Analyse ma grille 3-12-25-38-47")
    assert not should_inject_pedagogical_context("Merci beaucoup !")
