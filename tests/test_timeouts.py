"""
Tests F05 — _TIMEOUTS centralized timeout constants.
Tests F13 — _get_draw_count per-game cache separation.
"""

import pytest
from unittest.mock import patch, AsyncMock
from contextlib import asynccontextmanager

from services.chat_pipeline_shared import _TIMEOUTS


# ═══════════════════════════════════════════════════════
# F05: _TIMEOUTS dict
# ═══════════════════════════════════════════════════════

class TestTimeouts:

    def test_all_keys_present(self):
        """All expected timeout keys must exist."""
        expected = {
            "sql_generate", "sql_execute",
            "gemini_chat", "gemini_stream",
            "pitch_context", "pitch_gemini",
            "stats_analysis", "enrichment",
        }
        assert expected.issubset(set(_TIMEOUTS.keys()))

    def test_all_values_positive(self):
        """All timeout values must be positive numbers."""
        for key, val in _TIMEOUTS.items():
            assert isinstance(val, (int, float)), f"{key} is not numeric"
            assert val > 0, f"{key} must be positive"

    def test_sql_faster_than_stats(self):
        """SQL timeouts should be shorter than stats analysis."""
        assert _TIMEOUTS["sql_generate"] < _TIMEOUTS["stats_analysis"]
        assert _TIMEOUTS["sql_execute"] < _TIMEOUTS["stats_analysis"]


# ═══════════════════════════════════════════════════════
# F13: _get_draw_count per-game cache
# ═══════════════════════════════════════════════════════

@asynccontextmanager
async def _mock_conn(cursor):
    conn = AsyncMock()
    conn.cursor = AsyncMock(return_value=cursor)
    yield conn


class TestDrawCountPerGame:

    @pytest.mark.asyncio
    @patch("services.chat_pipeline.db_cloudsql")
    async def test_loto_uses_tirages_table(self, mock_db):
        """_get_draw_count('loto') queries 'tirages' table."""
        from services.chat_pipeline import _get_draw_count, _draw_count_cache

        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value={"cnt": 981})
        mock_db.get_connection = lambda: _mock_conn(cursor)

        # Clear cache
        _draw_count_cache.clear()
        result = await _get_draw_count("loto")
        assert result == 981
        sql_called = cursor.execute.call_args[0][0]
        assert "tirages" in sql_called
        assert "euromillions" not in sql_called

    @pytest.mark.asyncio
    @patch("services.chat_pipeline.db_cloudsql")
    async def test_em_uses_euromillions_table(self, mock_db):
        """_get_draw_count('euromillions') queries 'tirages_euromillions' table."""
        from services.chat_pipeline import _get_draw_count, _draw_count_cache

        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value={"cnt": 450})
        mock_db.get_connection = lambda: _mock_conn(cursor)

        _draw_count_cache.clear()
        result = await _get_draw_count("euromillions")
        assert result == 450
        sql_called = cursor.execute.call_args[0][0]
        assert "tirages_euromillions" in sql_called

    @pytest.mark.asyncio
    @patch("services.chat_pipeline.db_cloudsql")
    async def test_caches_are_separate(self, mock_db):
        """Loto and EM draw counts use separate cache entries."""
        from services.chat_pipeline import _get_draw_count, _draw_count_cache

        call_count = 0

        async def _mock_execute(sql):
            nonlocal call_count
            call_count += 1

        cursor = AsyncMock()
        cursor.execute = _mock_execute
        cursor.fetchone = AsyncMock(return_value={"cnt": 100})
        mock_db.get_connection = lambda: _mock_conn(cursor)

        _draw_count_cache.clear()
        await _get_draw_count("loto")
        await _get_draw_count("euromillions")
        assert call_count == 2  # Both must hit DB (separate cache keys)

        # Second calls should be cached
        await _get_draw_count("loto")
        await _get_draw_count("euromillions")
        assert call_count == 2  # No additional DB calls
