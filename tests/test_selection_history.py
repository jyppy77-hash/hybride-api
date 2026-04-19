"""
Tests for services/selection_history.py (V110 — persistent saturation brake).
Mirrors the pattern of tests/test_decay_state.py.
"""
import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.selection_history import (
    record_canonical_selection,
    get_persistent_brake_map,
    cleanup_old_selections,
    is_first_generation_of_target_draw,
)
from config.engine import LOTO_CONFIG, EM_CONFIG
from dataclasses import replace


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _make_mock_conn(cursor_rowcount_sequence=None, fetchall_results=None, fetchone_results=None):
    """Build a mock aiomysql connection with an AsyncMock cursor.

    cursor_rowcount_sequence : list[int] — one rowcount per execute() call
    fetchall_results          : list[list[dict]] — results for successive fetchall()
    fetchone_results          : list[dict|None]  — results for successive fetchone()
    """
    cursor = AsyncMock()
    cursor.execute = AsyncMock()
    if fetchall_results is not None:
        cursor.fetchall = AsyncMock(side_effect=fetchall_results)
    else:
        cursor.fetchall = AsyncMock(return_value=[])
    if fetchone_results is not None:
        cursor.fetchone = AsyncMock(side_effect=fetchone_results)
    else:
        cursor.fetchone = AsyncMock(return_value=None)
    # rowcount is a regular attribute assigned after each execute call
    if cursor_rowcount_sequence is not None:
        rowcounts = iter(cursor_rowcount_sequence)
        async def execute_with_rowcount(*args, **kwargs):
            try:
                cursor.rowcount = next(rowcounts)
            except StopIteration:
                cursor.rowcount = 1
        cursor.execute = AsyncMock(side_effect=execute_with_rowcount)
    else:
        cursor.rowcount = 1

    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cursor)
    conn.commit = AsyncMock()
    return conn, cursor


# ═══════════════════════════════════════════════════════════════════════
# record_canonical_selection
# ═══════════════════════════════════════════════════════════════════════

class TestRecordCanonicalSelection:

    @pytest.mark.asyncio
    async def test_inserts_5_balls_plus_1_chance_loto(self):
        """Loto canonical grid = 5 balls + 1 chance. 6 INSERTs total."""
        conn, cursor = _make_mock_conn(cursor_rowcount_sequence=[1] * 6)
        result = await record_canonical_selection(
            conn, "loto", datetime.date(2026, 4, 22),
            {"ball": [3, 12, 30, 36, 42], "chance": [2]},
        )
        assert result["inserted"] == 6
        assert result["ignored"] == 0
        assert result["game"] == "loto"
        assert result["draw_date_target"] == "2026-04-22"
        assert cursor.execute.await_count == 6
        conn.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_inserts_5_balls_plus_2_stars_em(self):
        """EM canonical grid = 5 balls + 2 stars. 7 INSERTs total."""
        conn, cursor = _make_mock_conn(cursor_rowcount_sequence=[1] * 7)
        result = await record_canonical_selection(
            conn, "euromillions", datetime.date(2026, 4, 21),
            {"ball": [8, 19, 29, 36, 42], "star": [6, 7]},
        )
        assert result["inserted"] == 7
        assert result["ignored"] == 0

    @pytest.mark.asyncio
    async def test_idempotent_second_call_ignored(self):
        """Second call with same args → rowcount=0 (ignored by UNIQUE KEY)."""
        conn, cursor = _make_mock_conn(cursor_rowcount_sequence=[0] * 6)
        result = await record_canonical_selection(
            conn, "loto", datetime.date(2026, 4, 22),
            {"ball": [3, 12, 30, 36, 42], "chance": [2]},
        )
        assert result["inserted"] == 0
        assert result["ignored"] == 6

    @pytest.mark.asyncio
    async def test_handles_loto_int_chance(self):
        """Loto chance provided as int (legacy format) → wrapped to list."""
        conn, cursor = _make_mock_conn(cursor_rowcount_sequence=[1] * 6)
        result = await record_canonical_selection(
            conn, "loto", datetime.date(2026, 4, 22),
            {"ball": [3, 12, 30, 36, 42], "chance": 7},  # int, not list
        )
        assert result["inserted"] == 6
        # 5 balls + 1 chance = 6 total
        assert cursor.execute.await_count == 6

    @pytest.mark.asyncio
    async def test_handles_em_list_stars(self):
        """EM stars provided as list (native format) → treated correctly."""
        conn, cursor = _make_mock_conn(cursor_rowcount_sequence=[1] * 7)
        result = await record_canonical_selection(
            conn, "euromillions", datetime.date(2026, 4, 21),
            {"ball": [1, 2, 3, 4, 5], "star": [10, 11]},  # explicit list
        )
        assert result["inserted"] == 7

    @pytest.mark.asyncio
    async def test_graceful_db_error(self):
        """DB exception → returns error flag, does not raise."""
        conn = MagicMock()
        conn.cursor = AsyncMock(side_effect=RuntimeError("DB down"))
        conn.commit = AsyncMock()
        result = await record_canonical_selection(
            conn, "loto", datetime.date(2026, 4, 22),
            {"ball": [3, 12, 30, 36, 42], "chance": [2]},
        )
        assert result.get("error") is True
        assert result["inserted"] == 0

    @pytest.mark.asyncio
    async def test_empty_selection_no_inserts(self):
        """Empty selected_numbers → no inserts, no crash."""
        conn, cursor = _make_mock_conn()
        result = await record_canonical_selection(
            conn, "loto", datetime.date(2026, 4, 22), {},
        )
        assert result["inserted"] == 0
        assert cursor.execute.await_count == 0

    @pytest.mark.asyncio
    async def test_ignores_invalid_number_type(self):
        """Unknown number_type (e.g. 'foobar') is silently skipped."""
        conn, cursor = _make_mock_conn(cursor_rowcount_sequence=[1] * 5)
        result = await record_canonical_selection(
            conn, "loto", datetime.date(2026, 4, 22),
            {"ball": [3, 12, 30, 36, 42], "foobar": [99]},
        )
        assert result["inserted"] == 5  # only balls


# ═══════════════════════════════════════════════════════════════════════
# get_persistent_brake_map
# ═══════════════════════════════════════════════════════════════════════

class TestGetPersistentBrakeMap:

    def _make_cfg_enabled(self, window=2, t1=0.20, t2=0.50):
        """Create a LOTO_CONFIG override with brake enabled."""
        return replace(
            LOTO_CONFIG,
            saturation_persistent_enabled=True,
            saturation_persistent_window=window,
            saturation_brake_persistent_t1=t1,
            saturation_brake_persistent_t2=t2,
        )

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self):
        """saturation_persistent_enabled=False → {} without hitting DB."""
        cfg = replace(LOTO_CONFIG, saturation_persistent_enabled=False)
        conn = MagicMock()
        conn.cursor = AsyncMock()
        result = await get_persistent_brake_map(
            conn, "loto", datetime.date(2026, 4, 22), "ball", cfg,
        )
        assert result == {}
        # cursor must NOT be called when disabled
        conn.cursor.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_t1_only_gives_0_20(self):
        """Numbers from T-1 only → multiplier t1 (0.20)."""
        cfg = self._make_cfg_enabled(window=2)
        t1_date = datetime.date(2026, 4, 19)
        conn, cursor = _make_mock_conn(
            fetchall_results=[
                # First execute: SELECT DISTINCT draw_date_target
                [{"draw_date_target": t1_date}],
                # Second execute: SELECT number_value, draw_date_target
                [
                    {"number_value": 3, "draw_date_target": t1_date},
                    {"number_value": 12, "draw_date_target": t1_date},
                    {"number_value": 30, "draw_date_target": t1_date},
                ],
            ],
        )
        result = await get_persistent_brake_map(
            conn, "loto", datetime.date(2026, 4, 22), "ball", cfg,
        )
        assert result == {3: 0.20, 12: 0.20, 30: 0.20}

    @pytest.mark.asyncio
    async def test_t1_and_t2_gives_mixed_multipliers(self):
        """Numbers from T-1 and T-2 → t1 (0.20) and t2 (0.50) respectively."""
        cfg = self._make_cfg_enabled(window=2)
        t1_date = datetime.date(2026, 4, 19)
        t2_date = datetime.date(2026, 4, 17)
        conn, cursor = _make_mock_conn(
            fetchall_results=[
                [{"draw_date_target": t1_date}, {"draw_date_target": t2_date}],
                [
                    {"number_value": 3, "draw_date_target": t1_date},
                    {"number_value": 12, "draw_date_target": t1_date},
                    {"number_value": 36, "draw_date_target": t2_date},
                    {"number_value": 42, "draw_date_target": t2_date},
                ],
            ],
        )
        result = await get_persistent_brake_map(
            conn, "loto", datetime.date(2026, 4, 22), "ball", cfg,
        )
        assert result == {3: 0.20, 12: 0.20, 36: 0.50, 42: 0.50}

    @pytest.mark.asyncio
    async def test_collision_t1_and_t2_takes_min(self):
        """Number present in BOTH T-1 and T-2 → min multiplier (0.20, stronger brake)."""
        cfg = self._make_cfg_enabled(window=2)
        t1_date = datetime.date(2026, 4, 19)
        t2_date = datetime.date(2026, 4, 17)
        conn, cursor = _make_mock_conn(
            fetchall_results=[
                [{"draw_date_target": t1_date}, {"draw_date_target": t2_date}],
                [
                    # 42 appears in both T-1 and T-2
                    {"number_value": 42, "draw_date_target": t1_date},
                    {"number_value": 42, "draw_date_target": t2_date},
                ],
            ],
        )
        result = await get_persistent_brake_map(
            conn, "loto", datetime.date(2026, 4, 22), "ball", cfg,
        )
        assert result == {42: 0.20}  # min(0.20, 0.50)

    @pytest.mark.asyncio
    async def test_empty_history_returns_empty(self):
        """No rows in history → {}."""
        cfg = self._make_cfg_enabled()
        conn, cursor = _make_mock_conn(fetchall_results=[[]])
        result = await get_persistent_brake_map(
            conn, "loto", datetime.date(2026, 4, 22), "ball", cfg,
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_window_1_ignores_t2(self):
        """saturation_persistent_window=1 → only T-1, ignore T-2 (SQL LIMIT=1)."""
        cfg = self._make_cfg_enabled(window=1)
        t1_date = datetime.date(2026, 4, 19)
        conn, cursor = _make_mock_conn(
            fetchall_results=[
                [{"draw_date_target": t1_date}],  # only 1 date returned
                [{"number_value": 3, "draw_date_target": t1_date}],
            ],
        )
        result = await get_persistent_brake_map(
            conn, "loto", datetime.date(2026, 4, 22), "ball", cfg,
        )
        assert result == {3: 0.20}
        # Verify LIMIT=1 was passed to first query
        first_call_args = cursor.execute.await_args_list[0]
        assert 1 in first_call_args[0][1]  # LIMIT %s param

    @pytest.mark.asyncio
    async def test_secondary_type_star(self):
        """Works with number_type='star' for EuroMillions."""
        cfg = replace(
            EM_CONFIG,
            saturation_persistent_enabled=True,
        )
        t1_date = datetime.date(2026, 4, 19)
        conn, cursor = _make_mock_conn(
            fetchall_results=[
                [{"draw_date_target": t1_date}],
                [{"number_value": 7, "draw_date_target": t1_date}],
            ],
        )
        result = await get_persistent_brake_map(
            conn, "euromillions", datetime.date(2026, 4, 21), "star", cfg,
        )
        assert result == {7: 0.20}

    @pytest.mark.asyncio
    async def test_graceful_db_error(self):
        """DB exception → {} without raising."""
        cfg = self._make_cfg_enabled()
        conn = MagicMock()
        conn.cursor = AsyncMock(side_effect=RuntimeError("DB down"))
        result = await get_persistent_brake_map(
            conn, "loto", datetime.date(2026, 4, 22), "ball", cfg,
        )
        assert result == {}


# ═══════════════════════════════════════════════════════════════════════
# cleanup_old_selections
# ═══════════════════════════════════════════════════════════════════════

class TestCleanupOldSelections:

    @pytest.mark.asyncio
    async def test_nothing_to_prune_below_threshold(self):
        """Fewer distinct draws than keep_last_n → no deletion."""
        conn, cursor = _make_mock_conn(
            fetchall_results=[[
                {"draw_date_target": datetime.date(2026, 4, 19)},
                {"draw_date_target": datetime.date(2026, 4, 17)},
            ]]
        )
        result = await cleanup_old_selections(conn, "loto", keep_last_n_draws=20)
        assert result["deleted"] == 0

    @pytest.mark.asyncio
    async def test_deletes_old_entries(self):
        """20 distinct draws returned by SELECT → DELETE is invoked; returned dict carries deleted=rowcount.

        Simplified from the original flaky mock (see V110 rapport): we build the cursor
        directly with pre-set rowcount=42 (simulates aiomysql's behavior: after DELETE,
        cursor.rowcount exposes the number of rows deleted). No side_effect coroutines.
        """
        base_date = datetime.date(2026, 4, 19)
        rows = [{"draw_date_target": base_date - datetime.timedelta(days=i)} for i in range(20)]

        cursor = MagicMock()
        cursor.execute = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=rows)
        # Pre-set rowcount — cleanup_old_selections reads it AFTER the DELETE execute
        cursor.rowcount = 42

        conn = MagicMock()
        conn.cursor = AsyncMock(return_value=cursor)
        conn.commit = AsyncMock()

        result = await cleanup_old_selections(conn, "loto", keep_last_n_draws=20)

        # Both queries were issued: SELECT DISTINCT draw_date_target + DELETE
        assert cursor.execute.await_count == 2
        # The DELETE call was the second one and contains "DELETE" in its SQL
        delete_sql = cursor.execute.await_args_list[1][0][0]
        assert "DELETE" in delete_sql
        # Commit was awaited exactly once
        conn.commit.assert_awaited_once()
        # Returned structure reflects the rowcount
        assert result["game"] == "loto"
        assert result["deleted"] == 42


# ═══════════════════════════════════════════════════════════════════════
# is_first_generation_of_target_draw
# ═══════════════════════════════════════════════════════════════════════

class TestIsFirstGenerationOfTargetDraw:

    @pytest.mark.asyncio
    async def test_returns_true_when_no_row(self):
        conn, cursor = _make_mock_conn(fetchone_results=[None])
        result = await is_first_generation_of_target_draw(
            conn, "loto", datetime.date(2026, 4, 22),
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_row_exists(self):
        conn, cursor = _make_mock_conn(fetchone_results=[{"1": 1}])
        result = await is_first_generation_of_target_draw(
            conn, "loto", datetime.date(2026, 4, 22),
        )
        assert result is False


# ═══════════════════════════════════════════════════════════════════════
# V110 — get_next_draw_date helper (in config/games.py)
# ═══════════════════════════════════════════════════════════════════════

class TestGetNextDrawDate:
    """Validation Jyppy point 5: jour même exclu si après heure de tirage."""

    def test_get_next_draw_date_after_draw_time_returns_next(self):
        """Mardi 22h EM (après 22h cutoff) → vendredi, pas mardi."""
        from config.games import get_next_draw_date, ValidGame
        # Mardi 21 avril 2026 à 22h15 (après tirage EM 21h15)
        ref = datetime.datetime(2026, 4, 21, 22, 15)
        result = get_next_draw_date(ValidGame.euromillions, reference=ref)
        # Expected: vendredi 24 avril 2026
        assert result == datetime.date(2026, 4, 24)

    def test_get_next_draw_date_before_draw_time_returns_today(self):
        """Mardi 15h EM (avant cutoff 22h) → mardi (même jour)."""
        from config.games import get_next_draw_date, ValidGame
        ref = datetime.datetime(2026, 4, 21, 15, 0)
        result = get_next_draw_date(ValidGame.euromillions, reference=ref)
        assert result == datetime.date(2026, 4, 21)

    def test_get_next_draw_date_non_draw_day(self):
        """Mercredi EM (pas un jour de tirage) → vendredi."""
        from config.games import get_next_draw_date, ValidGame
        ref = datetime.datetime(2026, 4, 22, 10, 0)  # mercredi
        result = get_next_draw_date(ValidGame.euromillions, reference=ref)
        assert result == datetime.date(2026, 4, 24)

    def test_get_next_draw_date_loto_weekdays(self):
        """Loto FR tire lun/mer/sam — jeudi 10h → samedi."""
        from config.games import get_next_draw_date, ValidGame
        ref = datetime.datetime(2026, 4, 23, 10, 0)  # jeudi
        result = get_next_draw_date(ValidGame.loto, reference=ref)
        assert result == datetime.date(2026, 4, 25)  # samedi

    def test_get_next_draw_date_loto_after_cutoff(self):
        """Loto samedi 22h (après 21h cutoff) → lundi suivant."""
        from config.games import get_next_draw_date, ValidGame
        ref = datetime.datetime(2026, 4, 25, 22, 0)  # samedi 22h
        result = get_next_draw_date(ValidGame.loto, reference=ref)
        assert result == datetime.date(2026, 4, 27)  # lundi

    def test_get_next_draw_date_date_only_assumes_midnight(self):
        """Pure date (no time) → assume midnight, no cutoff skip."""
        from config.games import get_next_draw_date, ValidGame
        ref = datetime.date(2026, 4, 21)  # mardi, no time info
        result = get_next_draw_date(ValidGame.euromillions, reference=ref)
        assert result == datetime.date(2026, 4, 21)  # same day OK
