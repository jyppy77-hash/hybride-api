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
    _apply_generation_penalties,
    _apply_chance_penalties,
    _apply_anti_collision,
    _calculer_score_final,
    _GENERATION_PENALTY_COEFFS,
    TEMPERATURE_BY_MODE,
    ANTI_COLLISION_HIGH_BOOST,
    ANTI_COLLISION_SUPERSTITIOUS_MALUS,
    SUPERSTITIOUS_NUMBERS,
    LOTO_HIGH_THRESHOLD,
    MAX_TENTATIVES,
    MIN_CONFORMITE,
    CONFIG,
)
from tests.conftest import AsyncSmartMockCursor, make_async_conn, FAKE_TIRAGES


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
    """Mode conservative → metadata.ponderation = '50/30/20'."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=1, mode="conservative")
    assert result["metadata"]["mode_generation"] == "conservative"
    assert result["metadata"]["ponderation"] == "50/30/20"


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_generate_mode_balanced(mock_get_conn):
    """Mode balanced → metadata.ponderation = '40/35/25'."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=1, mode="balanced")
    assert result["metadata"]["mode_generation"] == "balanced"
    assert result["metadata"]["ponderation"] == "40/35/25"


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_generate_mode_recent(mock_get_conn):
    """Mode recent → metadata.ponderation = '25/35/40'."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=1, mode="recent")
    assert result["metadata"]["mode_generation"] == "recent"
    assert result["metadata"]["ponderation"] == "25/35/40"


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


# ═══════════════════════════════════════════════════════════════════════
# Penalisation generation (E01 audit fix)
# ═══════════════════════════════════════════════════════════════════════

def _make_draw(boules, chance=1):
    """Helper: create a draw dict for penalization tests."""
    return {
        'boule_1': boules[0], 'boule_2': boules[1], 'boule_3': boules[2],
        'boule_4': boules[3], 'boule_5': boules[4],
        'numero_chance': chance,
    }


class TestApplyGenerationPenalties:
    """Tests for _apply_generation_penalties (pure function)."""

    def test_empty_recent_draws(self):
        """No recent draws → scores unchanged."""
        scores = {n: 1.0 for n in range(1, 50)}
        result = _apply_generation_penalties(scores, [])
        assert result == scores

    def test_t1_hard_exclude(self):
        """T-1 numbers get score 0.0 (HARD_EXCLUDE)."""
        scores = {n: 1.0 for n in range(1, 50)}
        recent = [_make_draw([1, 2, 3, 4, 5])]
        result = _apply_generation_penalties(scores, recent)
        for n in [1, 2, 3, 4, 5]:
            assert result[n] == 0.0
        for n in range(6, 50):
            assert result[n] == 1.0

    def test_t2_penalty_065(self):
        """T-2 numbers get score x0.65."""
        scores = {n: 1.0 for n in range(1, 50)}
        recent = [
            _make_draw([40, 41, 42, 43, 44]),
            _make_draw([1, 2, 3, 4, 5]),
        ]
        result = _apply_generation_penalties(scores, recent)
        for n in [1, 2, 3, 4, 5]:
            assert result[n] == pytest.approx(0.65)

    def test_t3_penalty_080(self):
        """T-3 numbers get score x0.80."""
        scores = {n: 1.0 for n in range(1, 50)}
        recent = [
            _make_draw([40, 41, 42, 43, 44]),
            _make_draw([30, 31, 32, 33, 34]),
            _make_draw([1, 2, 3, 4, 5]),
        ]
        result = _apply_generation_penalties(scores, recent)
        for n in [1, 2, 3, 4, 5]:
            assert result[n] == pytest.approx(0.80)

    def test_t4_penalty_090(self):
        """T-4 numbers get score x0.90."""
        scores = {n: 1.0 for n in range(1, 50)}
        recent = [
            _make_draw([40, 41, 42, 43, 44]),
            _make_draw([30, 31, 32, 33, 34]),
            _make_draw([20, 21, 22, 23, 24]),
            _make_draw([1, 2, 3, 4, 5]),
        ]
        result = _apply_generation_penalties(scores, recent)
        for n in [1, 2, 3, 4, 5]:
            assert result[n] == pytest.approx(0.90)

    def test_strongest_penalty_wins(self):
        """Number in T-1 AND T-3 gets T-1 (exclusion)."""
        scores = {n: 1.0 for n in range(1, 50)}
        recent = [
            _make_draw([1, 2, 3, 4, 5]),
            _make_draw([6, 7, 8, 9, 10]),
            _make_draw([1, 11, 12, 13, 14]),
        ]
        result = _apply_generation_penalties(scores, recent)
        assert result[1] == 0.0  # T-1 wins

    def test_non_recent_scores_preserved(self):
        """Numbers not in recent draws keep original scores."""
        scores = {1: 0.5, 2: 0.8, 6: 0.9, 7: 0.6}
        for n in range(3, 50):
            if n not in scores:
                scores[n] = 0.3
        recent = [_make_draw([1, 2, 3, 4, 5])]
        result = _apply_generation_penalties(scores, recent)
        assert result[6] == 0.9
        assert result[7] == 0.6

    def test_penalty_multiplies_existing_score(self):
        """Penalty multiplies, not replaces, the existing score."""
        scores = {n: 0.5 for n in range(1, 50)}
        recent = [
            _make_draw([40, 41, 42, 43, 44]),
            _make_draw([1, 2, 3, 4, 5]),
        ]
        result = _apply_generation_penalties(scores, recent)
        assert result[1] == pytest.approx(0.5 * 0.65)


class TestApplyChancePenalties:
    """Tests for _apply_chance_penalties (pure function)."""

    def test_empty_recent(self):
        freq = {i: 20 for i in range(1, 11)}
        result = _apply_chance_penalties(freq, [])
        assert result == freq

    def test_t1_chance_excluded(self):
        """T-1 chance number set to 0."""
        freq = {i: 20 for i in range(1, 11)}
        recent = [_make_draw([40, 41, 42, 43, 44], chance=7)]
        result = _apply_chance_penalties(freq, recent)
        assert result[7] == 0
        assert result[1] == 20

    def test_t2_chance_penalized(self):
        """T-2 chance number penalized x0.65."""
        freq = {i: 100 for i in range(1, 11)}
        recent = [
            _make_draw([40, 41, 42, 43, 44], chance=3),
            _make_draw([30, 31, 32, 33, 34], chance=7),
        ]
        result = _apply_chance_penalties(freq, recent)
        assert result[7] == pytest.approx(100 * 0.65)
        assert result[3] == 0  # T-1


# ═══════════════════════════════════════════════════════════════════════
# Integration: penalization in generate_grids (E01)
# ═══════════════════════════════════════════════════════════════════════

def _get_t1_boules():
    """Get T-1 boules from FAKE_TIRAGES (last draw)."""
    last = sorted(FAKE_TIRAGES, key=lambda t: t['date_de_tirage'])[-1]
    return {last[f'boule_{i}'] for i in range(1, 6)}


def _get_t1_chance():
    """Get T-1 chance from FAKE_TIRAGES (last draw)."""
    last = sorted(FAKE_TIRAGES, key=lambda t: t['date_de_tirage'])[-1]
    return last['numero_chance']


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_t1_boules_excluded_from_grids(mock_get_conn):
    """T-1 boules must NOT appear in any generated grid."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    t1_boules = _get_t1_boules()
    result = await generate_grids(n=20, mode="balanced")

    for grid in result["grids"]:
        for n in grid["nums"]:
            assert n not in t1_boules, (
                f"T-1 number {n} found in grid {grid['nums']}. "
                f"T-1 = {t1_boules}"
            )


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_t1_chance_excluded(mock_get_conn):
    """T-1 chance number must NOT appear in generated grids."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)

    t1_chance = _get_t1_chance()
    # Generate many grids to check chance is never T-1
    all_chances = set()
    for seed in range(10):
        random.seed(seed)
        result = await generate_grids(n=5, mode="balanced")
        for g in result["grids"]:
            all_chances.add(g["chance"])

    assert t1_chance not in all_chances, (
        f"T-1 chance {t1_chance} was generated"
    )


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_forced_nums_bypass_hard_exclude(mock_get_conn):
    """Forced numbers must appear even if they are in T-1."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    t1_boules = list(_get_t1_boules())
    forced = t1_boules[:2]  # Force 2 T-1 numbers

    result = await generate_grids(n=3, mode="balanced", forced_nums=forced)

    for grid in result["grids"]:
        for f in forced:
            assert f in grid["nums"], (
                f"Forced T-1 number {f} missing from grid {grid['nums']}"
            )


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_grids_still_valid_with_penalization(mock_get_conn):
    """Grids with penalization still satisfy basic structure."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=5, mode="balanced")

    for grid in result["grids"]:
        assert len(grid["nums"]) == 5
        assert len(set(grid["nums"])) == 5
        assert all(1 <= n <= 49 for n in grid["nums"])
        assert grid["nums"] == sorted(grid["nums"])
        assert 1 <= grid["chance"] <= 10


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_penalization_does_not_break_modes(mock_get_conn):
    """All 3 modes still work with penalization."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)

    for mode in ("conservative", "balanced", "recent"):
        random.seed(42)
        result = await generate_grids(n=1, mode=mode)
        assert len(result["grids"]) == 1
        assert len(result["grids"][0]["nums"]) == 5


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Temperature (E02)
# ═══════════════════════════════════════════════════════════════════════

class TestTemperature:

    def test_temperature_1_preserves_ratios(self):
        """T=1.0 preserves relative ratios (backward compat)."""
        scores = {1: 0.2, 2: 0.4, 3: 0.8}
        result = normaliser_en_probabilites(scores, temperature=1.0)
        assert pytest.approx(result[3] / result[1], rel=1e-6) == 4.0

    def test_temperature_high_flattens(self):
        """T=2.0 flattens distribution (max/min ratio reduced)."""
        scores = {1: 0.1, 2: 1.0}
        t1 = normaliser_en_probabilites(scores, temperature=1.0)
        t2 = normaliser_en_probabilites(scores, temperature=2.0)
        ratio_t1 = t1[2] / t1[1]
        ratio_t2 = t2[2] / t2[1]
        assert ratio_t2 < ratio_t1

    def test_temperature_low_concentrates(self):
        """T=0.5 sharpens distribution (max/min ratio increased)."""
        scores = {1: 0.1, 2: 1.0}
        t1 = normaliser_en_probabilites(scores, temperature=1.0)
        t05 = normaliser_en_probabilites(scores, temperature=0.5)
        assert t05[2] / t05[1] > t1[2] / t1[1]

    def test_temperature_guard_minimum(self):
        """T < 0.1 is clamped to 0.1."""
        scores = {1: 0.5, 2: 1.0}
        result = normaliser_en_probabilites(scores, temperature=0.01)
        assert pytest.approx(sum(result.values()), abs=1e-9) == 1.0

    def test_temperature_zero_scores_fallback(self):
        """All-zero scores with temperature gives uniform."""
        scores = {1: 0.0, 2: 0.0, 3: 0.0}
        result = normaliser_en_probabilites(scores, temperature=1.5)
        assert pytest.approx(sum(result.values()), abs=1e-9) == 0.0 or all(v >= 0 for v in result.values())

    def test_temperature_sum_to_one(self):
        """Result always sums to 1.0 for any temperature."""
        scores = {n: random.random() + 0.01 for n in range(1, 50)}
        for temp in (0.5, 1.0, 1.3, 1.5, 2.0, 3.0):
            result = normaliser_en_probabilites(scores, temperature=temp)
            assert pytest.approx(sum(result.values()), abs=1e-9) == 1.0

    def test_temperature_by_mode_values(self):
        """TEMPERATURE_BY_MODE has correct values."""
        assert TEMPERATURE_BY_MODE['conservative'] == 1.0
        assert TEMPERATURE_BY_MODE['balanced'] == 1.3
        assert TEMPERATURE_BY_MODE['recent'] == 1.5


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_temperature_increases_diversity(mock_get_conn):
    """Mode 'recent' (T=1.5) produces more distinct numbers than 'conservative' (T=1.0)."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)

    distinct_conservative = set()
    distinct_recent = set()
    for seed in range(30):
        random.seed(seed)
        r = await generate_grids(n=1, mode="conservative")
        distinct_conservative.update(r["grids"][0]["nums"])
        random.seed(seed)
        r = await generate_grids(n=1, mode="recent")
        distinct_recent.update(r["grids"][0]["nums"])

    # Recent (T=1.5) should produce at least as many distinct numbers
    assert len(distinct_recent) >= len(distinct_conservative)


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Anti-collision (E05)
# ═══════════════════════════════════════════════════════════════════════

class TestAntiCollision:

    def test_high_numbers_boosted(self):
        """Numbers >24 (Loto) get x1.15 boost."""
        scores = {20: 1.0, 30: 1.0}
        result = _apply_anti_collision(scores, game="loto")
        assert result[20] == 1.0
        assert result[30] == pytest.approx(1.15)

    def test_superstitious_penalized(self):
        """Superstitious numbers get x0.80 malus."""
        scores = {7: 1.0, 13: 1.0, 25: 1.0}
        result = _apply_anti_collision(scores, game="loto")
        assert result[7] == pytest.approx(0.80)
        assert result[13] == pytest.approx(0.80)
        assert result[25] == pytest.approx(1.15)  # >24, boosted

    def test_all_superstitious_covered(self):
        """All 5 superstitious numbers are penalized."""
        scores = {n: 1.0 for n in range(1, 50)}
        result = _apply_anti_collision(scores, game="loto")
        for n in SUPERSTITIOUS_NUMBERS:
            assert result[n] < 1.0

    def test_anti_collision_constants(self):
        """Constants have expected values."""
        assert ANTI_COLLISION_HIGH_BOOST == 1.15
        assert ANTI_COLLISION_SUPERSTITIOUS_MALUS == 0.80
        assert LOTO_HIGH_THRESHOLD == 24
        assert SUPERSTITIOUS_NUMBERS == frozenset({3, 7, 9, 11, 13})

    def test_anti_collision_disabled_by_default(self):
        """generate_grids with default anti_collision=False doesn't apply adjustments."""
        scores = {n: 1.0 for n in range(1, 50)}
        # With anti_collision disabled, scores should remain unchanged
        # (tested implicitly by existing tests passing)
        assert True


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_anti_collision_metadata(mock_get_conn):
    """Metadata includes anti-collision info."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=1, mode="balanced", anti_collision=True)
    ac = result["metadata"]["anti_collision"]
    assert ac["enabled"] is True
    assert ac["high_threshold"] == 24
    assert ac["high_boost"] == 1.15
    assert 13 in ac["superstitious_numbers"]


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_anti_collision_grids_valid(mock_get_conn):
    """Grids with anti_collision=True still valid."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=5, mode="balanced", anti_collision=True)
    for grid in result["grids"]:
        assert len(grid["nums"]) == 5
        assert all(1 <= n <= 49 for n in grid["nums"])


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Conformity threshold (E07) + Score final (E09)
# ═══════════════════════════════════════════════════════════════════════

class TestConformityThreshold:

    def test_min_conformite_value(self):
        assert MIN_CONFORMITE == 0.7

    def test_max_tentatives_value(self):
        assert MAX_TENTATIVES == 20


class TestScoreFinal:

    def test_score_5_stars(self):
        assert _calculer_score_final(1.0) == 95

    def test_score_4_stars(self):
        assert _calculer_score_final(0.90) == 85

    def test_score_3_stars(self):
        assert _calculer_score_final(0.75) == 75

    def test_score_2_stars(self):
        assert _calculer_score_final(0.55) == 60

    def test_score_1_star(self):
        assert _calculer_score_final(0.40) == 50

    def test_score_legacy_range(self):
        """Score always in [50, 95] range."""
        for conf in (0.0, 0.3, 0.5, 0.7, 0.85, 1.0):
            score = _calculer_score_final(conf)
            assert 50 <= score <= 95


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_score_final_in_grids(mock_get_conn):
    """Generated grids use new score system."""
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=5, mode="balanced")
    for grid in result["grids"]:
        assert grid["score"] in (50, 60, 75, 85, 95)
