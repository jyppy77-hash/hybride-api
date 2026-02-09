"""
Tests unitaires pour engine/stats.py
Mocker la BDD — aucune connexion MySQL requise.
"""

from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from engine.stats import analyze_number, get_global_stats, get_top_flop_numbers


# ═══════════════════════════════════════════════════════════════════════
# analyze_number
# ═══════════════════════════════════════════════════════════════════════

@patch("engine.stats.get_connection")
def test_analyze_number_format(mock_get_conn):
    """Verifie le format de retour : cles presentes et types corrects."""
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_get_conn.return_value = conn

    cursor.fetchall.side_effect = [
        # Query 1 : dates d'apparition du numero
        [
            {"date_de_tirage": date(2020, 3, 14)},
            {"date_de_tirage": date(2022, 7, 20)},
            {"date_de_tirage": date(2024, 11, 2)},
        ],
    ]
    cursor.fetchone.side_effect = [
        {"count": 15},   # ecart actuel
        {"count": 800},  # total tirages
    ]

    result = analyze_number(5)

    # Cles obligatoires
    assert set(result.keys()) == {
        "number", "total_appearances", "first_appearance",
        "last_appearance", "current_gap", "appearance_dates", "total_draws",
    }

    # Types
    assert isinstance(result["number"], int)
    assert isinstance(result["total_appearances"], int)
    assert isinstance(result["first_appearance"], date)
    assert isinstance(result["last_appearance"], date)
    assert isinstance(result["current_gap"], int)
    assert isinstance(result["appearance_dates"], list)
    assert isinstance(result["total_draws"], int)


@patch("engine.stats.get_connection")
def test_analyze_number_values(mock_get_conn):
    """Verifie les valeurs calculees."""
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_get_conn.return_value = conn

    cursor.fetchall.side_effect = [
        [
            {"date_de_tirage": date(2020, 3, 14)},
            {"date_de_tirage": date(2022, 7, 20)},
            {"date_de_tirage": date(2024, 11, 2)},
        ],
    ]
    cursor.fetchone.side_effect = [
        {"count": 15},
        {"count": 800},
    ]

    result = analyze_number(5)

    assert result["number"] == 5
    assert result["total_appearances"] == 3
    assert result["first_appearance"] == date(2020, 3, 14)
    assert result["last_appearance"] == date(2024, 11, 2)
    assert result["current_gap"] == 15
    assert result["total_draws"] == 800
    assert len(result["appearance_dates"]) == 3


@patch("engine.stats.get_connection")
def test_analyze_number_no_appearances(mock_get_conn):
    """Numero jamais sorti : 0 apparitions, gap=0, dates None."""
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_get_conn.return_value = conn

    cursor.fetchall.side_effect = [
        [],  # aucune apparition
    ]
    cursor.fetchone.side_effect = [
        # pas de requete gap (last_appearance est None)
        {"count": 800},  # total tirages
    ]

    result = analyze_number(42)

    assert result["number"] == 42
    assert result["total_appearances"] == 0
    assert result["first_appearance"] is None
    assert result["last_appearance"] is None
    assert result["current_gap"] == 0
    assert result["total_draws"] == 800
    assert result["appearance_dates"] == []


def test_analyze_number_invalid_low():
    """Numero < 1 → ValueError."""
    with pytest.raises(ValueError, match="entre 1 et 49"):
        analyze_number(0)


def test_analyze_number_invalid_high():
    """Numero > 49 → ValueError."""
    with pytest.raises(ValueError, match="entre 1 et 49"):
        analyze_number(50)


# ═══════════════════════════════════════════════════════════════════════
# get_global_stats
# ═══════════════════════════════════════════════════════════════════════

@patch("engine.stats.get_connection")
def test_get_global_stats_format(mock_get_conn):
    """Verifie les cles et types de get_global_stats()."""
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_get_conn.return_value = conn

    cursor.fetchone.side_effect = [
        {"count": 967},
        {"min_date": date(2019, 3, 4), "max_date": date(2026, 2, 3)},
    ]

    result = get_global_stats()

    assert set(result.keys()) == {
        "total_draws", "first_draw_date", "last_draw_date", "period_covered",
    }
    assert result["total_draws"] == 967
    assert result["first_draw_date"] == date(2019, 3, 4)
    assert result["last_draw_date"] == date(2026, 2, 3)
    assert "2019-03-04" in result["period_covered"]
    assert "2026-02-03" in result["period_covered"]


@patch("engine.stats.get_connection")
def test_get_global_stats_cached(mock_get_conn):
    """Deuxieme appel ne re-interroge pas la BDD (cache TTL 1h)."""
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_get_conn.return_value = conn

    cursor.fetchone.side_effect = [
        {"count": 967},
        {"min_date": date(2019, 3, 4), "max_date": date(2026, 2, 3)},
    ]

    result1 = get_global_stats()
    result2 = get_global_stats()

    assert result1 == result2
    # get_connection appele une seule fois (cache hit au 2e appel)
    assert mock_get_conn.call_count == 1


# ═══════════════════════════════════════════════════════════════════════
# get_top_flop_numbers
# ═══════════════════════════════════════════════════════════════════════

@patch("engine.stats.get_connection")
def test_get_top_flop_numbers_format(mock_get_conn):
    """Verifie structure et tri de get_top_flop_numbers()."""
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_get_conn.return_value = conn

    # Generer des frequences variees pour 49 numeros
    freq_data = [{"num": n, "freq": 100 - n} for n in range(1, 50)]

    cursor.fetchone.side_effect = [
        {"count": 800},  # total tirages
    ]
    cursor.fetchall.side_effect = [
        freq_data,
    ]

    result = get_top_flop_numbers()

    assert set(result.keys()) == {"total_draws", "top", "flop"}
    assert result["total_draws"] == 800
    assert len(result["top"]) == 49
    assert len(result["flop"]) == 49

    # Top : tri count DESC
    counts_top = [item["count"] for item in result["top"]]
    assert counts_top == sorted(counts_top, reverse=True)

    # Flop : tri count ASC
    counts_flop = [item["count"] for item in result["flop"]]
    assert counts_flop == sorted(counts_flop)

    # Premier du top = numero avec la plus haute frequence
    assert result["top"][0]["number"] == 1
    assert result["top"][0]["count"] == 99  # 100 - 1

    # Premier du flop = numero avec la plus basse frequence
    assert result["flop"][0]["number"] == 49
    assert result["flop"][0]["count"] == 51  # 100 - 49


@patch("engine.stats.get_connection")
def test_get_top_flop_numbers_missing_nums(mock_get_conn):
    """Numeros absents de la BDD → count=0."""
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_get_conn.return_value = conn

    # Seulement 3 numeros presents
    freq_data = [
        {"num": 7, "freq": 50},
        {"num": 13, "freq": 30},
        {"num": 25, "freq": 40},
    ]

    cursor.fetchone.side_effect = [{"count": 100}]
    cursor.fetchall.side_effect = [freq_data]

    result = get_top_flop_numbers()

    # Les 46 numeros manquants ont count=0
    zero_count = [item for item in result["top"] if item["count"] == 0]
    assert len(zero_count) == 46

    # Le top commence par le numero 7 (freq=50)
    assert result["top"][0]["number"] == 7
    assert result["top"][0]["count"] == 50
