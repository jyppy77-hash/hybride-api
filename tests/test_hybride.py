"""
Tests unitaires pour engine/hybride.py
Utilise SmartMockCursor pour simuler la BDD.
"""

import random
from unittest.mock import patch

import pytest

from engine.hybride import (
    generate,
    generate_grids,
    valider_contraintes,
    normaliser_en_probabilites,
    generer_badges,
    _minmax_normalize,
    CONFIG,
)
from tests.conftest import AsyncSmartMockCursor, make_async_conn


# ═══════════════════════════════════════════════════════════════════════
# Fonctions pures (aucun mock BDD necessaire)
# ═══════════════════════════════════════════════════════════════════════

class TestValiderContraintes:

    def test_grille_parfaite(self):
        """Grille equilibree → score = 1.0."""
        nums = [3, 15, 24, 33, 47]  # pairs=1, bas=3, somme=122, disp=44, suites=0
        assert valider_contraintes(nums) == 1.0

    def test_penalite_pairs(self):
        """5 pairs → penalite 0.8."""
        nums = [2, 4, 6, 8, 10]
        score = valider_contraintes(nums)
        assert score < 1.0
        # 5 pairs: *0.8, 5 bas: *0.85, somme=30 <70: *0.7, disp=8 <15: *0.6, suites=0
        assert score == pytest.approx(0.8 * 0.85 * 0.7 * 0.6, rel=1e-6)

    def test_penalite_somme(self):
        """Somme hors [70, 150] → penalite."""
        nums = [1, 2, 3, 4, 5]  # somme=15
        score = valider_contraintes(nums)
        assert score < 1.0

    def test_penalite_dispersion(self):
        """Dispersion < 15 → penalite 0.6."""
        nums = [20, 21, 23, 25, 30]  # disp=10, suites=1
        score = valider_contraintes(nums)
        assert score < 1.0

    def test_penalite_suites(self):
        """3+ consecutifs → penalite 0.75."""
        nums = [10, 11, 12, 13, 40]
        score = valider_contraintes(nums)
        assert score < 1.0


class TestNormaliserEnProbabilites:

    def test_somme_egale_un(self):
        """La somme des probabilites doit etre 1."""
        scores = {n: random.random() for n in range(1, 50)}
        probas = normaliser_en_probabilites(scores)
        assert pytest.approx(sum(probas.values()), abs=1e-9) == 1.0

    def test_fallback_uniforme(self):
        """Scores tous a 0 → distribution uniforme."""
        scores = {n: 0.0 for n in range(1, 50)}
        probas = normaliser_en_probabilites(scores)
        assert pytest.approx(probas[1], abs=1e-9) == 1 / 49
        assert pytest.approx(sum(probas.values()), abs=1e-9) == 1.0

    def test_proportionnalite(self):
        """Numero avec score 2x doit avoir proba 2x."""
        scores = {n: 1.0 for n in range(1, 50)}
        scores[7] = 2.0
        probas = normaliser_en_probabilites(scores)
        assert probas[7] > probas[1]
        assert pytest.approx(probas[7] / probas[1], rel=1e-6) == 2.0


class TestMinmaxNormalize:

    def test_range_zero_un(self):
        """Les valeurs normalisees sont dans [0, 1]."""
        values = {1: 10, 2: 20, 3: 30}
        result = _minmax_normalize(values)
        assert result[1] == 0.0
        assert result[3] == 1.0
        assert 0.0 <= result[2] <= 1.0

    def test_valeurs_identiques(self):
        """Toutes identiques → 0.0 pour tous."""
        values = {n: 5.0 for n in range(1, 50)}
        result = _minmax_normalize(values)
        assert all(v == 0.0 for v in result.values())


class TestGenererBadges:

    def test_badge_hybride_v1_toujours_present(self):
        """Le badge 'Hybride V1' est toujours inclus."""
        scores = {n: 1.0 for n in range(1, 50)}
        badges = generer_badges([5, 15, 25, 35, 45], scores)
        assert "Hybride V1" in badges

    def test_badge_large_spectre(self):
        """Dispersion > 35 → badge 'Large spectre'."""
        scores = {n: 1.0 for n in range(1, 50)}
        badges = generer_badges([1, 10, 20, 30, 49], scores)
        assert "Large spectre" in badges

    def test_badge_pair_impair(self):
        """2 ou 3 pairs → badge 'Pair/Impair OK'."""
        scores = {n: 1.0 for n in range(1, 50)}
        badges = generer_badges([2, 4, 15, 25, 35], scores)  # 2 pairs
        assert "Pair/Impair OK" in badges


# ═══════════════════════════════════════════════════════════════════════
# Fonctions avec BDD (SmartMockCursor)
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_generate_grids_returns_valid_structure(mock_get_conn):
    """generate_grids retourne grids + metadata avec structure valide."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=3, mode="balanced")

    assert "grids" in result
    assert "metadata" in result
    assert len(result["grids"]) == 3

    for grid in result["grids"]:
        assert set(grid.keys()) == {"nums", "chance", "score", "badges"}
        assert len(grid["nums"]) == 5
        assert len(set(grid["nums"])) == 5  # uniques
        assert all(1 <= n <= 49 for n in grid["nums"])
        assert grid["nums"] == sorted(grid["nums"])
        assert 1 <= grid["chance"] <= 10
        assert 50 <= grid["score"] <= 100
        assert isinstance(grid["badges"], list)
        assert len(grid["badges"]) >= 1


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_generate_grids_count(mock_get_conn):
    """Le nombre de grilles retournees correspond a n."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    for n in (1, 5, 10):
        result = await generate_grids(n=n, mode="balanced")
        assert len(result["grids"]) == n


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_generate_grids_sorted_by_score(mock_get_conn):
    """Les grilles sont triees par score decroissant."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=5, mode="balanced")
    scores = [g["score"] for g in result["grids"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_generate_mode_conservative(mock_get_conn):
    """Mode conservative → metadata.ponderation = '70/30'."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=1, mode="conservative")
    assert result["metadata"]["mode_generation"] == "conservative"
    assert result["metadata"]["ponderation"] == "70/30"


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_generate_mode_balanced(mock_get_conn):
    """Mode balanced → metadata.ponderation = '60/40'."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=1, mode="balanced")
    assert result["metadata"]["mode_generation"] == "balanced"
    assert result["metadata"]["ponderation"] == "60/40"


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_generate_mode_recent(mock_get_conn):
    """Mode recent → metadata.ponderation = '40/60'."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=1, mode="recent")
    assert result["metadata"]["mode_generation"] == "recent"
    assert result["metadata"]["ponderation"] == "40/60"


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_generate_metadata_fields(mock_get_conn):
    """Metadata contient tous les champs attendus."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=1, mode="balanced")
    meta = result["metadata"]

    expected_keys = {
        "mode", "mode_generation", "fenetre_principale_annees",
        "fenetre_recente_annees", "ponderation", "nb_tirages_total",
        "periode_base", "avertissement",
    }
    assert expected_keys.issubset(set(meta.keys()))
    assert meta["mode"] == "HYBRIDE_OPTIMAL_V1"
    assert meta["nb_tirages_total"] > 0
    assert "hasard" in meta["avertissement"].lower()


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_generate_wrapper(mock_get_conn):
    """generate(prompt) retourne la structure attendue."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate("test prompt")

    assert "engine" in result
    assert result["engine"] == "HYBRIDE_OPTIMAL_V1"
    assert "result" in result
    assert "grids" in result["result"]
    assert "timestamp" in result
    assert result["input"] == "test prompt"
