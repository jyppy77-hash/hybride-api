"""Tests for EuroMillions pairs API — boules + étoiles, hot/cold, single lookup."""

import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from services.base_stats import BaseStatsService


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_em_stats(rows, fetchone_side_effect=None):
    """Create EM BaseStatsService with mocked DB."""
    from services.em_stats_service import EM_CONFIG
    svc = BaseStatsService(EM_CONFIG)

    cursor = AsyncMock()
    if fetchone_side_effect:
        cursor.fetchone = AsyncMock(side_effect=fetchone_side_effect)
    else:
        cursor.fetchone = AsyncMock(return_value={"total": 800})
    cursor.fetchall = AsyncMock(return_value=rows)

    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cursor)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    svc._get_connection = MagicMock(return_value=ctx)
    return svc


_BALL_ROWS = [
    {"num_a": i, "num_b": i + 10, "pair_count": 20 - i}
    for i in range(1, 11)
]

_STAR_ROWS = [
    {"num_a": 1, "num_b": 5, "pair_count": 45},
    {"num_a": 3, "num_b": 7, "pair_count": 40},
    {"num_a": 2, "num_b": 11, "pair_count": 38},
    {"num_a": 4, "num_b": 9, "pair_count": 35},
    {"num_a": 6, "num_b": 12, "pair_count": 33},
    {"num_a": 1, "num_b": 8, "pair_count": 30},
    {"num_a": 2, "num_b": 10, "pair_count": 28},
    {"num_a": 3, "num_b": 6, "pair_count": 25},
    {"num_a": 5, "num_b": 11, "pair_count": 22},
    {"num_a": 4, "num_b": 12, "pair_count": 20},
]


# ── Tests boules EM ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_em_hot_pairs_returns_10():
    """EM hot ball pairs returns 10 results."""
    svc = _make_em_stats(_BALL_ROWS)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_pair_correlations(top_n=10, order="hot")
    assert result is not None
    assert len(result["pairs"]) == 10


@pytest.mark.asyncio
async def test_em_cold_pairs_returns_10():
    """EM cold ball pairs returns 10 results."""
    svc = _make_em_stats(_BALL_ROWS)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_pair_correlations(top_n=10, order="cold")
    assert result is not None
    assert len(result["pairs"]) == 10


# ── Tests étoiles EM ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_em_star_pairs_hot():
    """EM hot star pairs returns results."""
    svc = _make_em_stats(_STAR_ROWS)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_star_pair_correlations(top_n=10, order="hot")
    assert result is not None
    assert len(result["pairs"]) == 10


@pytest.mark.asyncio
async def test_em_single_star_pair():
    """get_single_star_pair returns count, rank, total_pairs for a specific star pair."""
    from services.em_stats_service import EM_CONFIG
    svc = BaseStatsService(EM_CONFIG)

    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(side_effect=[
        {"total": 800},
        {"pair_count": 45},
        {"better": 0, "tp": 66},
    ])
    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cursor)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    svc._get_connection = MagicMock(return_value=ctx)

    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_single_star_pair(s1=3, s2=7)

    assert result is not None
    assert result["s1"] == 3
    assert result["s2"] == 7
    assert result["count"] == 45
    assert result["rank"] == 1
    assert result["total_pairs"] == 66


@pytest.mark.asyncio
async def test_star_pair_route_rejects_out_of_range():
    """Route /api/euromillions/stats/star-pair?s1=0&s2=13 returns 422."""
    os.environ.setdefault("DB_USER", "test")
    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("DB_NAME", "test")
    with patch("main.StaticFiles", side_effect=lambda **kw: MagicMock()):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/euromillions/stats/star-pair?s1=0&s2=13")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_star_pair_route_rejects_same():
    """Route /api/euromillions/stats/star-pair?s1=5&s2=5 returns 422."""
    os.environ.setdefault("DB_USER", "test")
    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("DB_NAME", "test")
    with patch("main.StaticFiles", side_effect=lambda **kw: MagicMock()):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/euromillions/stats/star-pair?s1=5&s2=5")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_em_ball_range_50():
    """EM ball pairs should work with numbers up to 50 (not 49 like Loto)."""
    rows = [{"num_a": 42, "num_b": 50, "pair_count": 7}]
    svc = _make_em_stats(rows)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_pair_correlations(top_n=1, order="hot")
    assert result["pairs"][0]["num_b"] == 50
