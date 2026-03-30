"""Tests for pairs stats API — order=hot/cold, normalization, sorting."""

import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from services.base_stats import BaseStatsService


# ── Fixtures ────────────────────────────────────────────────────────────────

# Simulated DB rows (already LEAST/GREATEST normalized by SQL)
_HOT_ROWS = [
    {"num_a": 7, "num_b": 11, "pair_count": 19},
    {"num_a": 3, "num_b": 49, "pair_count": 17},
    {"num_a": 1, "num_b": 34, "pair_count": 16},
    {"num_a": 5, "num_b": 22, "pair_count": 15},
    {"num_a": 12, "num_b": 30, "pair_count": 14},
    {"num_a": 8, "num_b": 44, "pair_count": 13},
    {"num_a": 2, "num_b": 19, "pair_count": 12},
    {"num_a": 6, "num_b": 33, "pair_count": 11},
    {"num_a": 15, "num_b": 40, "pair_count": 10},
    {"num_a": 20, "num_b": 25, "pair_count": 9},
]

_COLD_ROWS = [
    {"num_a": 41, "num_b": 48, "pair_count": 1},
    {"num_a": 43, "num_b": 47, "pair_count": 1},
    {"num_a": 39, "num_b": 46, "pair_count": 2},
    {"num_a": 37, "num_b": 45, "pair_count": 2},
    {"num_a": 35, "num_b": 42, "pair_count": 2},
    {"num_a": 31, "num_b": 38, "pair_count": 3},
    {"num_a": 29, "num_b": 36, "pair_count": 3},
    {"num_a": 27, "num_b": 32, "pair_count": 3},
    {"num_a": 23, "num_b": 28, "pair_count": 4},
    {"num_a": 21, "num_b": 26, "pair_count": 4},
]


def _make_stats(rows):
    """Create a BaseStatsService instance with mocked DB connection returning rows."""
    from services.stats_service import LOTO_CONFIG
    svc = BaseStatsService(LOTO_CONFIG)

    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value={"total": 1000, "d": None})
    cursor.fetchall = AsyncMock(return_value=rows)

    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cursor)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)

    svc._get_connection = MagicMock(return_value=ctx)
    return svc


# ── Tests ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hot_pairs_returns_10():
    """Hot pairs returns 10 results with correct structure."""
    svc = _make_stats(_HOT_ROWS)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_pair_correlations(top_n=10, order="hot")
    assert result is not None
    assert len(result["pairs"]) == 10
    assert result["total_draws"] == 1000


@pytest.mark.asyncio
async def test_cold_pairs_returns_10():
    """Cold pairs returns 10 results."""
    svc = _make_stats(_COLD_ROWS)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_pair_correlations(top_n=10, order="cold")
    assert result is not None
    assert len(result["pairs"]) == 10


@pytest.mark.asyncio
async def test_pairs_n1_less_than_n2():
    """All pairs have num_a < num_b (LEAST/GREATEST normalization)."""
    svc = _make_stats(_HOT_ROWS)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_pair_correlations(top_n=10, order="hot")
    for p in result["pairs"]:
        assert p["num_a"] < p["num_b"], f"{p['num_a']} should be < {p['num_b']}"


@pytest.mark.asyncio
async def test_hot_sorted_desc():
    """Hot pairs are sorted by count descending."""
    svc = _make_stats(_HOT_ROWS)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_pair_correlations(top_n=10, order="hot")
    counts = [p["count"] for p in result["pairs"]]
    assert counts == sorted(counts, reverse=True)


@pytest.mark.asyncio
async def test_cold_sorted_asc():
    """Cold pairs are sorted by count ascending."""
    svc = _make_stats(_COLD_ROWS)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_pair_correlations(top_n=10, order="cold")
    counts = [p["count"] for p in result["pairs"]]
    assert counts == sorted(counts)


@pytest.mark.asyncio
async def test_pairs_have_percentage_and_rank():
    """Each pair has percentage and rank fields."""
    svc = _make_stats(_HOT_ROWS[:3])
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_pair_correlations(top_n=3, order="hot")
    for p in result["pairs"]:
        assert "percentage" in p
        assert "rank" in p
        assert p["rank"] >= 1
        assert p["percentage"] > 0


@pytest.mark.asyncio
async def test_cache_key_includes_order():
    """Cache key should differ between hot and cold."""
    svc = _make_stats(_HOT_ROWS)
    cache_keys = []

    async def mock_cache_get(key):
        cache_keys.append(key)
        return None

    with patch("services.base_stats.cache_get", side_effect=mock_cache_get), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        await svc.get_pair_correlations(top_n=10, order="hot")
        await svc.get_pair_correlations(top_n=10, order="cold")

    assert len(cache_keys) == 2
    assert cache_keys[0] != cache_keys[1]
    assert "hot" in cache_keys[0]
    assert "cold" in cache_keys[1]


# ── Single pair lookup tests ────────────────────────────────────────────────

def _make_single_pair_stats(pair_count, rank_better, total_pairs):
    """Create a BaseStatsService for get_single_pair() with mocked DB."""
    from services.stats_service import LOTO_CONFIG
    svc = BaseStatsService(LOTO_CONFIG)

    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(side_effect=[
        {"total": 1000},                            # total draws
        {"pair_count": pair_count},                  # count for this pair
        {"better": rank_better, "tp": total_pairs},  # rank + total pairs (single query)
    ])

    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cursor)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)

    svc._get_connection = MagicMock(return_value=ctx)
    return svc


@pytest.mark.asyncio
async def test_single_pair_returns_correct_data():
    """get_single_pair returns count, percentage, rank for a specific pair."""
    svc = _make_single_pair_stats(pair_count=19, rank_better=0, total_pairs=1176)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_single_pair(n1=7, n2=11)
    assert result is not None
    assert result["n1"] == 7
    assert result["n2"] == 11
    assert result["count"] == 19
    assert result["percentage"] == 1.9
    assert result["rank"] == 1  # 0 better → rank 1
    assert result["total_draws"] == 1000
    assert result["total_pairs"] == 1176


@pytest.mark.asyncio
async def test_single_pair_normalizes_order():
    """get_single_pair normalizes n1 < n2 even if called with n1 > n2."""
    svc = _make_single_pair_stats(pair_count=5, rank_better=50, total_pairs=1176)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_single_pair(n1=30, n2=3)
    assert result["n1"] == 3
    assert result["n2"] == 30


@pytest.mark.asyncio
async def test_single_pair_rank_coherent():
    """Rank 1 means no pair has higher count (0 better)."""
    svc = _make_single_pair_stats(pair_count=19, rank_better=0, total_pairs=1176)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_single_pair(n1=7, n2=11)
    assert result["rank"] == 1

    svc2 = _make_single_pair_stats(pair_count=10, rank_better=25, total_pairs=1176)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result2 = await svc2.get_single_pair(n1=1, n2=2)
    assert result2["rank"] == 26  # 25 better → rank 26


@pytest.mark.asyncio
async def test_single_pair_route_rejects_same_numbers():
    """Route /api/loto/stats/pair?n1=5&n2=5 returns 422."""
    os.environ.setdefault("DB_USER", "test")
    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("DB_NAME", "test")
    with patch("main.StaticFiles", side_effect=lambda **kw: MagicMock()):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/loto/stats/pair?n1=5&n2=5")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_single_pair_route_rejects_out_of_range():
    """Route /api/loto/stats/pair?n1=0&n2=51 returns 422."""
    os.environ.setdefault("DB_USER", "test")
    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("DB_NAME", "test")
    with patch("main.StaticFiles", side_effect=lambda **kw: MagicMock()):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/loto/stats/pair?n1=0&n2=51")
    assert resp.status_code == 422
