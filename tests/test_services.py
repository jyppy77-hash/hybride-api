"""
Tests unitaires pour services/cache.py et services/stats_service.py
Mocker la BDD — aucune connexion MySQL requise.
"""

import time
from unittest.mock import patch, MagicMock
from datetime import date, timedelta

import pytest

from services.cache import cache_get, cache_set, cache_clear


# ═══════════════════════════════════════════════════════════════════════
# services/cache.py
# ═══════════════════════════════════════════════════════════════════════

class TestCache:

    def test_cache_get_set(self):
        """set une valeur, get la retrouve."""
        cache_clear()
        cache_set("test_key", {"data": 42})
        assert cache_get("test_key") == {"data": 42}

    def test_cache_ttl_expired(self):
        """set avec TTL court, verifier expiration."""
        cache_clear()
        cache_set("expire_key", "value", ttl=0)
        # TTL=0 → expire immediatement (monotonic avance)
        time.sleep(0.01)
        assert cache_get("expire_key") is None

    def test_cache_clear(self):
        """clear vide tout le cache."""
        cache_set("a", 1)
        cache_set("b", 2)
        cache_clear()
        assert cache_get("a") is None
        assert cache_get("b") is None

    def test_cache_get_missing_key(self):
        """get sur cle inexistante retourne None."""
        cache_clear()
        assert cache_get("inexistant") is None


# ═══════════════════════════════════════════════════════════════════════
# services/stats_service.py — helpers BDD caches
# ═══════════════════════════════════════════════════════════════════════

@patch("services.stats_service.db_cloudsql")
def test_get_all_frequencies_cached(mock_db):
    """Appel 2x, verifie que le 2eme ne touche pas la BDD."""
    cache_clear()

    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_db.get_connection.return_value = conn

    cursor.fetchall.return_value = [
        {"num": 1, "freq": 50}, {"num": 7, "freq": 30},
    ]

    from services.stats_service import _get_all_frequencies

    result1 = _get_all_frequencies(cursor, "principal")
    result2 = _get_all_frequencies(cursor, "principal")

    assert result1 == {1: 50, 7: 30}
    assert result1 == result2
    # cursor.execute appele 1 seule fois (cache hit au 2e)
    assert cursor.execute.call_count == 1


@patch("services.stats_service.db_cloudsql")
def test_get_all_ecarts_cached(mock_db):
    """Appel 2x _get_all_ecarts, verifie cache hit au 2eme appel."""
    cache_clear()

    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_db.get_connection.return_value = conn

    # fetchone pour COUNT(*) total
    cursor.fetchone.return_value = {"total": 967}
    # fetchall : ecarts via SQL correlated subquery
    cursor.fetchall.side_effect = [
        [{"num": n, "ecart": n % 10} for n in range(1, 50)],
    ]

    from services.stats_service import _get_all_ecarts

    result1 = _get_all_ecarts(cursor, "principal")
    result2 = _get_all_ecarts(cursor, "principal")

    assert result1 == result2
    assert isinstance(result1, dict)
    assert len(result1) == 49
    # execute appele 2 fois au 1er appel (COUNT + UNION ALL ecart), 0 au 2eme
    assert cursor.execute.call_count == 2


# ═══════════════════════════════════════════════════════════════════════
# services/stats_service.py — fonctions metier
# ═══════════════════════════════════════════════════════════════════════

@patch("services.stats_service.db_cloudsql")
def test_get_numero_stats_valid(mock_db):
    """Verifie format retour (cles, types) pour un numero valide."""
    cache_clear()

    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_db.get_connection.return_value = conn

    d_min = date(2019, 3, 4)
    d_max = date(2026, 2, 3)

    cursor.fetchone.side_effect = [
        # COUNT + MIN + MAX
        {"total": 967, "date_min": d_min, "date_max": d_max},
        # gap
        {"gap": 5},
        # ecart moyen — pas besoin si < 2 apparitions (mais on en a 3)
    ]
    cursor.fetchall.side_effect = [
        # appearances
        [
            {"date_de_tirage": date(2020, 3, 14)},
            {"date_de_tirage": date(2022, 7, 20)},
            {"date_de_tirage": date(2024, 11, 2)},
        ],
        # all dates pour ecart moyen
        [{"date_de_tirage": d_min + timedelta(days=i * 3)} for i in range(967)],
        # _get_all_frequencies (classement)
        [{"num": n, "freq": 100 - n} for n in range(1, 50)],
        # _get_all_frequencies 2 ans (categorie)
        [{"num": n, "freq": 50 - n} for n in range(1, 50)],
    ]

    from services.stats_service import get_numero_stats

    result = get_numero_stats(7, "principal")

    assert result is not None
    expected_keys = {
        "numero", "type", "frequence_totale", "pourcentage_apparition",
        "derniere_sortie", "ecart_actuel", "ecart_moyen",
        "classement", "classement_sur", "categorie",
        "total_tirages", "periode",
    }
    assert expected_keys == set(result.keys())
    assert result["numero"] == 7
    assert result["type"] == "principal"
    assert isinstance(result["frequence_totale"], int)
    assert isinstance(result["ecart_actuel"], int)
    assert result["classement_sur"] == 49


def test_get_numero_stats_invalid_range():
    """Numero hors range retourne None (pas d'appel BDD)."""
    from services.stats_service import get_numero_stats

    assert get_numero_stats(0, "principal") is None
    assert get_numero_stats(50, "principal") is None
    assert get_numero_stats(11, "chance") is None


@patch("services.stats_service.db_cloudsql")
def test_get_classement_numeros(mock_db):
    """Verifie le tri et le format de get_classement_numeros."""
    cache_clear()

    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_db.get_connection.return_value = conn

    d_min = date(2019, 3, 4)
    d_max = date(2026, 2, 3)

    cursor.fetchone.side_effect = [
        # get_classement: COUNT + MIN + MAX
        {"total": 967, "date_min": d_min, "date_max": d_max},
        # _get_all_ecarts: COUNT total
        {"total": 967},
    ]
    cursor.fetchall.side_effect = [
        # _get_all_frequencies (principal)
        [{"num": n, "freq": 100 + n} for n in range(1, 50)],
        # _get_all_ecarts (SQL correlated subquery — {num, ecart})
        [{"num": n, "ecart": n % 10} for n in range(1, 50)],
        # _get_all_frequencies 2 ans (categorie)
        [{"num": n, "freq": 50 + n} for n in range(1, 50)],
    ]

    from services.stats_service import get_classement_numeros

    result = get_classement_numeros("principal", "frequence_desc", 5)

    assert result is not None
    assert "items" in result
    assert "total_tirages" in result
    assert "periode" in result
    assert len(result["items"]) == 5

    # Tri frequence DESC
    freqs = [item["frequence"] for item in result["items"]]
    assert freqs == sorted(freqs, reverse=True)

    # Chaque item a les bonnes cles
    for item in result["items"]:
        assert set(item.keys()) == {"numero", "frequence", "ecart_actuel", "categorie"}


@patch("services.stats_service.db_cloudsql")
def test_get_comparaison_numeros(mock_db):
    """Verifie la structure de comparaison entre deux numeros."""
    cache_clear()

    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_db.get_connection.return_value = conn

    d_min = date(2019, 3, 4)
    d_max = date(2026, 2, 3)

    # get_numero_stats est appele 2x, chaque appel fait plusieurs queries
    # On fournit suffisamment de side_effects pour les 2 appels
    cursor.fetchone.side_effect = [
        # 1er appel get_numero_stats(5)
        {"total": 967, "date_min": d_min, "date_max": d_max},
        {"gap": 3},
        # 2eme appel get_numero_stats(10)
        {"total": 967, "date_min": d_min, "date_max": d_max},
        {"gap": 8},
    ]
    cursor.fetchall.side_effect = [
        # 1er: appearances
        [{"date_de_tirage": date(2020, 5, 1)}, {"date_de_tirage": date(2023, 8, 10)}],
        # 1er: all_dates ecart moyen
        [{"date_de_tirage": d_min + timedelta(days=i * 3)} for i in range(967)],
        # 1er: frequencies classement
        [{"num": n, "freq": 100 - n} for n in range(1, 50)],
        # 1er: freq 2 ans
        [{"num": n, "freq": 50 - n} for n in range(1, 50)],
        # 2eme: appearances
        [{"date_de_tirage": date(2021, 1, 1)}, {"date_de_tirage": date(2024, 6, 1)},
         {"date_de_tirage": date(2025, 3, 1)}],
        # 2eme: all_dates ecart moyen
        [{"date_de_tirage": d_min + timedelta(days=i * 3)} for i in range(967)],
        # 2eme: frequencies classement
        [{"num": n, "freq": 100 - n} for n in range(1, 50)],
        # 2eme: freq 2 ans
        [{"num": n, "freq": 50 - n} for n in range(1, 50)],
    ]

    from services.stats_service import get_comparaison_numeros

    result = get_comparaison_numeros(5, 10, "principal")

    assert result is not None
    assert "num1" in result
    assert "num2" in result
    assert "diff_frequence" in result
    assert "favori_frequence" in result
    assert result["num1"]["numero"] == 5
    assert result["num2"]["numero"] == 10


@patch("services.stats_service.db_cloudsql")
def test_analyze_grille_for_chat(mock_db):
    """Verifie la structure d'analyse de grille."""
    cache_clear()

    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_db.get_connection.return_value = conn

    # Nouveau flow : fetchone pour total + best_match, fetchall pour freq UNION ALL + exact matches
    cursor.fetchone.side_effect = [
        {"total": 967},
        # best match
        {
            "date_de_tirage": date(2024, 1, 15),
            "boule_1": 5, "boule_2": 15, "boule_3": 25,
            "boule_4": 35, "boule_5": 45,
            "match_count": 3,
        },
    ]
    cursor.fetchall.side_effect = [
        # _get_all_frequencies UNION ALL (49 numeros)
        [{"num": n, "freq": 100 - n} for n in range(1, 50)],
        # exact matches
        [],
    ]

    from services.stats_service import analyze_grille_for_chat

    result = analyze_grille_for_chat([5, 15, 25, 35, 45], chance=7)

    assert result is not None
    assert "numeros" in result
    assert "analyse" in result
    assert "historique" in result
    assert result["numeros"] == [5, 15, 25, 35, 45]
    assert result["chance"] == 7

    analyse = result["analyse"]
    assert "somme" in analyse
    assert "pairs" in analyse
    assert "conformite_pct" in analyse
    assert "badges" in analyse
    assert isinstance(analyse["badges"], list)
