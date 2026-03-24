"""
Tests unitaires pour engine/hybride_em.py
Penalisation integree (E01) + etoiles hybrides (E03).
"""

import random as _random
from contextlib import asynccontextmanager
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from engine.hybride_em import (
    generate_grids,
    valider_contraintes,
    normaliser_en_probabilites,
    generer_badges,
    generer_etoiles,
    _minmax_normalize,
    _apply_generation_penalties,
    _apply_star_penalties,
    _apply_anti_collision,
    _apply_star_anti_collision,
    _calculer_score_final,
    _GENERATION_PENALTY_COEFFS,
    TEMPERATURE_BY_MODE,
    ANTI_COLLISION_HIGH_BOOST,
    SUPERSTITIOUS_NUMBERS,
    EM_HIGH_THRESHOLD,
    SUPERSTITIOUS_STARS,
    STAR_ANTI_COLLISION_MALUS,
    MAX_TENTATIVES,
    MIN_CONFORMITE,
    BOULE_MIN, BOULE_MAX,
    ETOILE_MIN, ETOILE_MAX,
    NB_BOULES, NB_ETOILES,
)


# ═══════════════════════════════════════════════════════════════════════
# EM fake tirages + mock cursor
# ═══════════════════════════════════════════════════════════════════════

def _make_fake_tirages_em(n=200):
    """Generate deterministic EM tirages (seed=42)."""
    rng = _random.Random(42)
    tirages = []
    base = date(2020, 1, 7)
    for i in range(n):
        boules = sorted(rng.sample(range(1, 51), 5))
        etoiles = sorted(rng.sample(range(1, 13), 2))
        tirages.append({
            "boule_1": boules[0], "boule_2": boules[1], "boule_3": boules[2],
            "boule_4": boules[3], "boule_5": boules[4],
            "etoile_1": etoiles[0], "etoile_2": etoiles[1],
            "date_de_tirage": base + timedelta(days=i * 3),
        })
    return tirages


FAKE_EM_TIRAGES = _make_fake_tirages_em()


class EMSmartMockCursor:
    """Mock cursor for EuroMillions with star support."""

    def __init__(self, tirages=None):
        self._tirages = tirages or FAKE_EM_TIRAGES
        self._q = ""
        self._params = None

    def execute(self, query, params=None):
        self._q = " ".join(query.split()).lower()
        self._params = params

    def _parse_date_param(self, idx=0):
        if not self._params:
            return None
        p = self._params
        val = p[idx] if isinstance(p, (list, tuple)) and len(p) > idx else p
        if isinstance(val, str):
            return date.fromisoformat(val)
        if isinstance(val, date):
            return val
        return None

    def _filter_gte(self):
        d = self._parse_date_param()
        if d:
            return [t for t in self._tirages if t["date_de_tirage"] >= d]
        return list(self._tirages)

    def fetchone(self):
        q = self._q

        if "max(date_de_tirage)" in q and "min" not in q and "count" not in q:
            d = max((t["date_de_tirage"] for t in self._tirages), default=None)
            return {"max_date": d, "last": d}

        if "count(*)" in q and "min(" in q:
            dates = [t["date_de_tirage"] for t in self._tirages]
            return {
                "total": len(dates), "count": len(dates),
                "min_date": min(dates, default=None),
                "max_date": max(dates, default=None),
            }

        if "min(date_de_tirage)" in q:
            dates = [t["date_de_tirage"] for t in self._tirages]
            return {
                "min_date": min(dates, default=None),
                "max_date": max(dates, default=None),
            }

        if "count(*)" in q and "date_de_tirage >" in q:
            d = self._parse_date_param()
            c = sum(1 for t in self._tirages if t["date_de_tirage"] > d) if d else 0
            return {"count": c, "gap": c}

        if "count(*)" in q:
            return {"count": len(self._tirages), "total": len(self._tirages)}

        return None

    def fetchall(self):
        q = self._q

        # Star frequency: etoile UNION ALL with COUNT
        if "etoile" in q and "union all" in q and "count(*)" in q:
            filtered = self._filter_gte()
            freq = {}
            for t in filtered:
                for col in ("etoile_1", "etoile_2"):
                    n = t.get(col)
                    if n is not None:
                        freq[n] = freq.get(n, 0) + 1
            return [{"num": k, "freq": v} for k, v in sorted(freq.items())]

        # Star retard: SELECT etoile_1, etoile_2 (no boule_1 in query)
        if "etoile_1" in q and "etoile_2" in q and "from tirages" in q and "boule_1" not in q:
            filtered = self._filter_gte()
            if "desc" in q:
                filtered = list(reversed(filtered))
            return filtered

        # Boule frequency: UNION ALL with COUNT (for boules)
        if "union all" in q and "count(*)" in q:
            filtered = self._filter_gte()
            freq = {}
            for t in filtered:
                for col in ("boule_1", "boule_2", "boule_3", "boule_4", "boule_5"):
                    n = t[col]
                    freq[n] = freq.get(n, 0) + 1
            return [{"num": k, "freq": v} for k, v in sorted(freq.items())]

        # Full tirages (boule_1..5 + etoile_1..2)
        if "boule_1" in q and "from tirages" in q:
            filtered = self._filter_gte()
            if "desc" in q:
                return list(reversed(filtered))
            return list(filtered)

        return []


class EMAsyncSmartMockCursor(EMSmartMockCursor):
    """Async wrapper for EM mock cursor."""

    async def execute(self, query, params=None):
        super().execute(query, params)

    async def fetchone(self):
        return super().fetchone()

    async def fetchall(self):
        return super().fetchall()


@asynccontextmanager
async def make_em_conn(cursor=None):
    """Async context manager mimicking get_connection() for EM."""
    cur = cursor or EMAsyncSmartMockCursor()
    conn = AsyncMock()
    conn.cursor = AsyncMock(return_value=cur)
    yield conn


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _make_draw_em(boules, etoiles):
    """Helper: create an EM draw dict."""
    return {
        'boule_1': boules[0], 'boule_2': boules[1], 'boule_3': boules[2],
        'boule_4': boules[3], 'boule_5': boules[4],
        'etoile_1': etoiles[0], 'etoile_2': etoiles[1],
    }


def _get_em_t1():
    """Get T-1 boules and etoiles from fake EM tirages."""
    last = sorted(FAKE_EM_TIRAGES, key=lambda t: t['date_de_tirage'])[-1]
    boules = {last[f'boule_{i}'] for i in range(1, 6)}
    etoiles = {last['etoile_1'], last['etoile_2']}
    return boules, etoiles


# ═══════════════════════════════════════════════════════════════════════
# Pure function tests
# ═══════════════════════════════════════════════════════════════════════

class TestEMValiderContraintes:

    def test_grille_parfaite(self):
        nums = [3, 15, 26, 33, 47]  # pairs=2, bas=2(<=25), somme=124, disp=44, suites=0
        assert valider_contraintes(nums) == 1.0

    def test_penalite_somme_em(self):
        """Somme hors [75, 175]."""
        nums = [1, 2, 3, 4, 5]
        assert valider_contraintes(nums) < 1.0


class TestEMNormaliserEnProbabilites:

    def test_somme_un(self):
        scores = {n: _random.random() for n in range(1, 51)}
        probas = normaliser_en_probabilites(scores)
        assert pytest.approx(sum(probas.values()), abs=1e-9) == 1.0

    def test_fallback_uniforme(self):
        scores = {n: 0.0 for n in range(1, 51)}
        probas = normaliser_en_probabilites(scores)
        assert pytest.approx(probas[1], abs=1e-9) == 1 / 50


class TestEMMinmaxNormalize:

    def test_range_zero_un(self):
        values = {1: 10, 2: 20, 3: 30}
        result = _minmax_normalize(values)
        assert result[1] == 0.0
        assert result[3] == 1.0


class TestEMBadges:

    def test_badge_hybride_em(self):
        scores = {n: 1.0 for n in range(1, 51)}
        badges = generer_badges([5, 15, 25, 35, 45], scores, lang="fr")
        # Should contain the hybride_em badge
        assert len(badges) >= 1


# ═══════════════════════════════════════════════════════════════════════
# Penalization tests — boules (E01)
# ═══════════════════════════════════════════════════════════════════════

class TestEMApplyGenerationPenalties:

    def test_empty_recent(self):
        scores = {n: 1.0 for n in range(1, 51)}
        assert _apply_generation_penalties(scores, []) == scores

    def test_t1_hard_exclude(self):
        scores = {n: 1.0 for n in range(1, 51)}
        recent = [_make_draw_em([1, 2, 3, 4, 5], [1, 2])]
        result = _apply_generation_penalties(scores, recent)
        for n in [1, 2, 3, 4, 5]:
            assert result[n] == 0.0
        assert result[6] == 1.0

    def test_t2_penalty(self):
        scores = {n: 1.0 for n in range(1, 51)}
        recent = [
            _make_draw_em([40, 41, 42, 43, 44], [11, 12]),
            _make_draw_em([1, 2, 3, 4, 5], [9, 10]),
        ]
        result = _apply_generation_penalties(scores, recent)
        for n in [1, 2, 3, 4, 5]:
            assert result[n] == pytest.approx(0.65)

    def test_t3_penalty(self):
        scores = {n: 1.0 for n in range(1, 51)}
        recent = [
            _make_draw_em([40, 41, 42, 43, 44], [11, 12]),
            _make_draw_em([30, 31, 32, 33, 34], [9, 10]),
            _make_draw_em([1, 2, 3, 4, 5], [7, 8]),
        ]
        result = _apply_generation_penalties(scores, recent)
        for n in [1, 2, 3, 4, 5]:
            assert result[n] == pytest.approx(0.80)

    def test_t4_penalty(self):
        scores = {n: 1.0 for n in range(1, 51)}
        recent = [
            _make_draw_em([40, 41, 42, 43, 44], [11, 12]),
            _make_draw_em([30, 31, 32, 33, 34], [9, 10]),
            _make_draw_em([20, 21, 22, 23, 24], [7, 8]),
            _make_draw_em([1, 2, 3, 4, 5], [5, 6]),
        ]
        result = _apply_generation_penalties(scores, recent)
        for n in [1, 2, 3, 4, 5]:
            assert result[n] == pytest.approx(0.90)

    def test_strongest_wins(self):
        scores = {n: 1.0 for n in range(1, 51)}
        recent = [
            _make_draw_em([1, 2, 3, 4, 5], [1, 2]),
            _make_draw_em([6, 7, 8, 9, 10], [3, 4]),
            _make_draw_em([1, 11, 12, 13, 14], [5, 6]),
        ]
        result = _apply_generation_penalties(scores, recent)
        assert result[1] == 0.0  # T-1 wins


# ═══════════════════════════════════════════════════════════════════════
# Penalization tests — etoiles (E03)
# ═══════════════════════════════════════════════════════════════════════

class TestApplyStarPenalties:

    def test_empty_recent(self):
        scores = {n: 1.0 for n in range(1, 13)}
        assert _apply_star_penalties(scores, []) == scores

    def test_t1_stars_excluded(self):
        """T-1 stars get score 0.0."""
        scores = {n: 1.0 for n in range(1, 13)}
        recent = [_make_draw_em([1, 2, 3, 4, 5], [5, 9])]
        result = _apply_star_penalties(scores, recent)
        assert result[5] == 0.0
        assert result[9] == 0.0
        assert result[1] == 1.0  # Not a star, unchanged

    def test_t2_stars_penalized(self):
        """T-2 stars penalized x0.65."""
        scores = {n: 1.0 for n in range(1, 13)}
        recent = [
            _make_draw_em([1, 2, 3, 4, 5], [11, 12]),
            _make_draw_em([6, 7, 8, 9, 10], [5, 9]),
        ]
        result = _apply_star_penalties(scores, recent)
        assert result[5] == pytest.approx(0.65)
        assert result[9] == pytest.approx(0.65)
        assert result[11] == 0.0  # T-1
        assert result[12] == 0.0  # T-1

    def test_t3_stars_penalized(self):
        """T-3 stars penalized x0.80."""
        scores = {n: 1.0 for n in range(1, 13)}
        recent = [
            _make_draw_em([1, 2, 3, 4, 5], [11, 12]),
            _make_draw_em([6, 7, 8, 9, 10], [9, 10]),
            _make_draw_em([11, 12, 13, 14, 15], [5, 6]),
        ]
        result = _apply_star_penalties(scores, recent)
        assert result[5] == pytest.approx(0.80)
        assert result[6] == pytest.approx(0.80)

    def test_t4_stars_penalized(self):
        """T-4 stars penalized x0.90."""
        scores = {n: 1.0 for n in range(1, 13)}
        recent = [
            _make_draw_em([1, 2, 3, 4, 5], [11, 12]),
            _make_draw_em([6, 7, 8, 9, 10], [9, 10]),
            _make_draw_em([11, 12, 13, 14, 15], [7, 8]),
            _make_draw_em([16, 17, 18, 19, 20], [5, 6]),
        ]
        result = _apply_star_penalties(scores, recent)
        assert result[5] == pytest.approx(0.90)
        assert result[6] == pytest.approx(0.90)

    def test_star_in_t1_and_t3(self):
        """Star in T-1 AND T-3 gets T-1 exclusion."""
        scores = {n: 1.0 for n in range(1, 13)}
        recent = [
            _make_draw_em([1, 2, 3, 4, 5], [5, 9]),
            _make_draw_em([6, 7, 8, 9, 10], [11, 12]),
            _make_draw_em([11, 12, 13, 14, 15], [5, 6]),
        ]
        result = _apply_star_penalties(scores, recent)
        assert result[5] == 0.0  # T-1 wins

    def test_star_penalty_multiplies(self):
        """Penalty multiplies the existing score."""
        scores = {n: 0.5 for n in range(1, 13)}
        recent = [
            _make_draw_em([1, 2, 3, 4, 5], [11, 12]),
            _make_draw_em([6, 7, 8, 9, 10], [5, 9]),
        ]
        result = _apply_star_penalties(scores, recent)
        assert result[5] == pytest.approx(0.5 * 0.65)


# ═══════════════════════════════════════════════════════════════════════
# Integration: generate_grids EM (E01 + E03)
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_generate_grids_valid_structure(mock_get_conn):
    """generate_grids EM returns valid structure."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    _random.seed(42)

    result = await generate_grids(n=3, mode="balanced", lang="fr")

    assert "grids" in result
    assert "metadata" in result
    assert len(result["grids"]) == 3

    for grid in result["grids"]:
        assert "nums" in grid
        assert "etoiles" in grid
        assert "score" in grid
        assert "badges" in grid
        assert len(grid["nums"]) == 5
        assert len(set(grid["nums"])) == 5
        assert all(BOULE_MIN <= n <= BOULE_MAX for n in grid["nums"])
        assert grid["nums"] == sorted(grid["nums"])
        assert len(grid["etoiles"]) == 2
        assert len(set(grid["etoiles"])) == 2
        assert all(ETOILE_MIN <= e <= ETOILE_MAX for e in grid["etoiles"])
        assert grid["etoiles"] == sorted(grid["etoiles"])
        assert 50 <= grid["score"] <= 100


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_t1_boules_excluded(mock_get_conn):
    """T-1 boules must NOT appear in generated EM grids."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    _random.seed(42)

    t1_boules, _ = _get_em_t1()

    result = await generate_grids(n=20, mode="balanced", lang="fr")

    for grid in result["grids"]:
        for n in grid["nums"]:
            assert n not in t1_boules, (
                f"T-1 boule {n} in grid {grid['nums']}. T-1={t1_boules}"
            )


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_t1_etoiles_excluded(mock_get_conn):
    """T-1 etoiles must NOT appear in generated EM grids."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    _random.seed(42)

    _, t1_etoiles = _get_em_t1()

    result = await generate_grids(n=20, mode="balanced", lang="fr")

    for grid in result["grids"]:
        for e in grid["etoiles"]:
            assert e not in t1_etoiles, (
                f"T-1 etoile {e} in grid {grid['etoiles']}. T-1={t1_etoiles}"
            )


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_forced_nums_bypass_exclude(mock_get_conn):
    """Forced boules must appear even if in T-1."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    _random.seed(42)

    t1_boules, _ = _get_em_t1()
    forced = list(t1_boules)[:2]

    result = await generate_grids(n=3, mode="balanced", lang="fr", forced_nums=forced)

    for grid in result["grids"]:
        for f in forced:
            assert f in grid["nums"], (
                f"Forced T-1 number {f} missing from {grid['nums']}"
            )


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_forced_etoiles_override(mock_get_conn):
    """Forced etoiles are included regardless of penalization."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    _random.seed(42)

    result = await generate_grids(
        n=3, mode="balanced", lang="fr", forced_etoiles=[5, 9]
    )

    for grid in result["grids"]:
        assert 5 in grid["etoiles"]
        assert 9 in grid["etoiles"]


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_modes_work(mock_get_conn):
    """All 3 modes work with penalization."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)

    for mode in ("conservative", "balanced", "recent"):
        _random.seed(42)
        result = await generate_grids(n=1, mode=mode, lang="fr")
        assert len(result["grids"]) == 1
        grid = result["grids"][0]
        assert len(grid["nums"]) == 5
        assert len(grid["etoiles"]) == 2


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_metadata_correct(mock_get_conn):
    """Metadata has expected structure."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    _random.seed(42)

    result = await generate_grids(n=1, mode="balanced", lang="fr")
    meta = result["metadata"]
    assert meta["mode"] == "HYBRIDE_OPTIMAL_V1_EM"
    assert meta["mode_generation"] == "balanced"
    assert meta["ponderation"] == "40/35/25"
    assert meta["nb_tirages_total"] > 0


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_generate_grids_count(mock_get_conn):
    """Number of grids matches n."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    _random.seed(42)

    for n in (1, 5, 10):
        result = await generate_grids(n=n, mode="balanced", lang="fr")
        assert len(result["grids"]) == n


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_grids_sorted_by_score(mock_get_conn):
    """Grids sorted by score descending."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    _random.seed(42)

    result = await generate_grids(n=5, mode="balanced", lang="fr")
    scores = [g["score"] for g in result["grids"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_exclusions_applied(mock_get_conn):
    """User exclusions are applied correctly."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    _random.seed(42)

    exclusions = {"exclude_nums": [7, 13], "exclude_ranges": [], "exclude_multiples": []}
    result = await generate_grids(n=5, mode="balanced", lang="fr", exclusions=exclusions)

    for grid in result["grids"]:
        assert 7 not in grid["nums"]
        assert 13 not in grid["nums"]


# ═══════════════════════════════════════════════════════════════════════
# Star hybrid scoring (E03)
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_etoiles_always_two_distinct(mock_get_conn):
    """generer_etoiles always returns 2 distinct stars."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)

    for seed in range(20):
        _random.seed(seed)
        async with make_em_conn(cursor) as conn:
            etoiles = await generer_etoiles(conn)
        assert len(etoiles) == 2
        assert len(set(etoiles)) == 2
        assert all(ETOILE_MIN <= e <= ETOILE_MAX for e in etoiles)
        assert etoiles == sorted(etoiles)


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_etoiles_with_mode(mock_get_conn):
    """generer_etoiles respects mode parameter."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)

    for mode in ("conservative", "balanced", "recent"):
        _random.seed(42)
        async with make_em_conn(cursor) as conn:
            etoiles = await generer_etoiles(conn, mode=mode)
        assert len(etoiles) == 2
        assert all(ETOILE_MIN <= e <= ETOILE_MAX for e in etoiles)


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_etoiles_penalized(mock_get_conn):
    """T-1 etoiles are excluded from generer_etoiles."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)

    _, t1_etoiles = _get_em_t1()

    # Get recent draws from mock
    last_4 = sorted(FAKE_EM_TIRAGES, key=lambda t: t['date_de_tirage'])[-4:]
    last_4.reverse()

    excluded = set()
    for seed in range(20):
        _random.seed(seed)
        async with make_em_conn(cursor) as conn:
            etoiles = await generer_etoiles(conn, recent_draws=last_4)
        for e in etoiles:
            if e in t1_etoiles:
                excluded.add(e)

    assert len(excluded) == 0, (
        f"T-1 etoiles {t1_etoiles} appeared in generated stars"
    )


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_etoiles_range(mock_get_conn):
    """All generated etoiles are in [1-12]."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)

    for seed in range(10):
        _random.seed(seed)
        async with make_em_conn(cursor) as conn:
            etoiles = await generer_etoiles(conn)
        for e in etoiles:
            assert 1 <= e <= 12


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Temperature EM (E02)
# ═══════════════════════════════════════════════════════════════════════

class TestEMTemperature:

    def test_temperature_1_preserves_ratios(self):
        scores = {1: 0.2, 2: 0.4, 3: 0.8}
        result = normaliser_en_probabilites(scores, temperature=1.0)
        assert pytest.approx(result[3] / result[1], rel=1e-6) == 4.0

    def test_temperature_high_flattens(self):
        scores = {1: 0.1, 2: 1.0}
        t1 = normaliser_en_probabilites(scores, temperature=1.0)
        t2 = normaliser_en_probabilites(scores, temperature=2.0)
        assert t2[2] / t2[1] < t1[2] / t1[1]

    def test_temperature_sum_to_one(self):
        scores = {n: _random.random() + 0.01 for n in range(1, 51)}
        for temp in (0.5, 1.0, 1.3, 1.5, 3.0):
            result = normaliser_en_probabilites(scores, temperature=temp)
            assert pytest.approx(sum(result.values()), abs=1e-9) == 1.0

    def test_temperature_by_mode(self):
        assert TEMPERATURE_BY_MODE['conservative'] == 1.0
        assert TEMPERATURE_BY_MODE['balanced'] == 1.3
        assert TEMPERATURE_BY_MODE['recent'] == 1.5


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Anti-collision EM (E05)
# ═══════════════════════════════════════════════════════════════════════

class TestEMAntiCollision:

    def test_em_high_threshold_31(self):
        """EM: numbers >31 get boosted."""
        scores = {25: 1.0, 35: 1.0}
        result = _apply_anti_collision(scores)
        assert result[25] == 1.0  # <=31, no boost
        assert result[35] == pytest.approx(ANTI_COLLISION_HIGH_BOOST)

    def test_em_superstitious_penalized(self):
        scores = {7: 1.0, 13: 1.0, 40: 1.0}
        result = _apply_anti_collision(scores)
        assert result[7] < 1.0
        assert result[13] < 1.0
        assert result[40] > 1.0  # >31, boosted

    def test_em_threshold_constant(self):
        assert EM_HIGH_THRESHOLD == 31


class TestEMStarAntiCollision:

    def test_superstitious_stars_penalized(self):
        """Stars {3,7,9,11} get x0.85 malus."""
        scores = {n: 1.0 for n in range(1, 13)}
        result = _apply_star_anti_collision(scores)
        for s in SUPERSTITIOUS_STARS:
            assert result[s] == pytest.approx(STAR_ANTI_COLLISION_MALUS)
        # Non-superstitious unchanged
        assert result[1] == 1.0
        assert result[2] == 1.0

    def test_star_anti_collision_constants(self):
        assert SUPERSTITIOUS_STARS == frozenset({3, 7, 9, 11})
        assert STAR_ANTI_COLLISION_MALUS == 0.85


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_anti_collision_metadata(mock_get_conn):
    """Metadata includes anti-collision info."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    _random.seed(42)

    result = await generate_grids(n=1, mode="balanced", lang="fr", anti_collision=True)
    ac = result["metadata"]["anti_collision"]
    assert ac["enabled"] is True
    assert ac["high_threshold"] == 31


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_anti_collision_grids_valid(mock_get_conn):
    """Grids with anti_collision=True still valid."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    _random.seed(42)

    result = await generate_grids(n=5, mode="balanced", lang="fr", anti_collision=True)
    for grid in result["grids"]:
        assert len(grid["nums"]) == 5
        assert len(grid["etoiles"]) == 2
        assert all(BOULE_MIN <= n <= BOULE_MAX for n in grid["nums"])
        assert all(ETOILE_MIN <= e <= ETOILE_MAX for e in grid["etoiles"])


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Conformity + Score final EM (E07, E09)
# ═══════════════════════════════════════════════════════════════════════

class TestEMConformityThreshold:

    def test_min_conformite(self):
        assert MIN_CONFORMITE == 0.7

    def test_max_tentatives(self):
        assert MAX_TENTATIVES == 20


class TestEMScoreFinal:

    def test_score_stars(self):
        assert _calculer_score_final(1.0) == 95
        assert _calculer_score_final(0.90) == 85
        assert _calculer_score_final(0.75) == 75
        assert _calculer_score_final(0.55) == 60
        assert _calculer_score_final(0.40) == 50


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_em_score_final_in_grids(mock_get_conn):
    """Generated EM grids use new score system."""
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    _random.seed(42)

    result = await generate_grids(n=5, mode="balanced", lang="fr")
    for grid in result["grids"]:
        assert grid["score"] in (50, 60, 75, 85, 95)
