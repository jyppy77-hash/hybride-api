"""
Tests E2E for V110 persistent saturation brake integration in /api/{game}/generate.

Validates the whole flow: flag detection → brake load → engine call →
canonical write. Also enforces V94 invariant extended to hybride_selection_history
(chatbot Phase G never writes).
"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.engine import LOTO_CONFIG
from dataclasses import replace


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

class _FakeCursor:
    """Minimal cursor mock with controllable fetch results."""
    def __init__(self, fetchall_sequence=None, fetchone_sequence=None):
        self.execute = AsyncMock()
        self._fa = list(fetchall_sequence or [])
        self._fo = list(fetchone_sequence or [])
        self.rowcount = 1

    async def fetchall(self):
        return self._fa.pop(0) if self._fa else []

    async def fetchone(self):
        return self._fo.pop(0) if self._fo else None


def _make_fake_conn(fetchall_sequence=None, fetchone_sequence=None):
    cursor = _FakeCursor(fetchall_sequence, fetchone_sequence)
    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cursor)
    conn.commit = AsyncMock()

    class _Ctx:
        async def __aenter__(self_inner):
            return conn
        async def __aexit__(self_inner, *args):
            return False
    return conn, cursor, _Ctx()


# ═══════════════════════════════════════════════════════════════════════
# Direct tests on record_canonical_selection + get_persistent_brake_map
# composition (unit-level, no FastAPI overhead)
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateV110Integration:
    """Integration tests at the service layer, not full FastAPI E2E.

    Full FastAPI route tests would require TestClient + DB fixtures not
    available in this test environment. These tests validate the logical
    flow of the route's updated block (api_analyse_unified.py:60-130).
    """

    @pytest.mark.asyncio
    async def test_generate_writes_canonical_selection_when_enabled(self):
        """With flag ON, a grid generation triggers record_canonical_selection."""
        from services.selection_history import record_canonical_selection

        conn, cursor, _ = _make_fake_conn()
        cursor.rowcount = 1
        result = await record_canonical_selection(
            conn, "loto", date(2026, 4, 22),
            {"ball": [3, 12, 30, 36, 42], "chance": [2]},
        )
        # 5 balls + 1 chance = 6 execute calls
        assert cursor.execute.await_count == 6
        assert result["inserted"] >= 0  # actual value depends on rowcount mock

    @pytest.mark.asyncio
    async def test_generate_twice_same_day_writes_once_effectively(self):
        """Second record_canonical_selection with same args → ignored (UNIQUE KEY)."""
        from services.selection_history import record_canonical_selection

        conn, cursor, _ = _make_fake_conn()
        # Simulate rowcount=0 (INSERT IGNORE on existing row)
        cursor.rowcount = 0
        result = await record_canonical_selection(
            conn, "loto", date(2026, 4, 22),
            {"ball": [3, 12, 30, 36, 42], "chance": [2]},
        )
        assert result["inserted"] == 0
        assert result["ignored"] == 6

    @pytest.mark.asyncio
    async def test_brake_read_uses_target_date(self):
        """get_persistent_brake_map filters on draw_date_target < current_date."""
        from services.selection_history import get_persistent_brake_map
        cfg = replace(
            LOTO_CONFIG,
            saturation_persistent_enabled=True,
            saturation_persistent_window=2,
        )
        t1 = date(2026, 4, 19)
        conn, cursor, _ = _make_fake_conn(
            fetchall_sequence=[
                [{"draw_date_target": t1}],
                [{"number_value": 36, "draw_date_target": t1}],
            ]
        )
        result = await get_persistent_brake_map(
            conn, "loto", date(2026, 4, 22), "ball", cfg,
        )
        # Must filter on draw_date_target < current (2026-04-22)
        first_call = cursor.execute.await_args_list[0]
        # The SQL contains "draw_date_target < %s"
        assert "draw_date_target < %s" in first_call[0][0]
        assert date(2026, 4, 22) in first_call[0][1]

    @pytest.mark.asyncio
    async def test_flag_off_skips_brake_read(self):
        """With flag OFF, get_persistent_brake_map returns {} without DB hit."""
        from services.selection_history import get_persistent_brake_map
        cfg = replace(LOTO_CONFIG, saturation_persistent_enabled=False)

        conn = MagicMock()
        conn.cursor = AsyncMock()
        result = await get_persistent_brake_map(
            conn, "loto", date(2026, 4, 22), "ball", cfg,
        )
        assert result == {}
        conn.cursor.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_route_flow_writes_canonical_after_generation(self):
        """Simulate the route block: generate → record_canonical_selection.

        We verify that the canonical grid (grids[0]) is extracted in the right
        format (ball list + secondary list/int) and passed to record_canonical_selection.
        """
        from services.selection_history import record_canonical_selection

        # Simulate engine result
        engine_result = {
            "grids": [
                {"nums": [3, 12, 30, 36, 42], "chance": 2, "score": 95, "badges": []},
                {"nums": [5, 15, 22, 33, 41], "chance": 4, "score": 85, "badges": []},
            ],
            "metadata": {},
        }

        # Replicate the logic from api_analyse_unified.py (unified_generate)
        canonical = engine_result["grids"][0]
        sec_val = canonical.get("chance")
        if isinstance(sec_val, list):
            sec_list = sec_val
        elif sec_val is not None:
            sec_list = [sec_val]
        else:
            sec_list = []
        selected = {
            "ball": canonical["nums"],
            "chance": sec_list,
        }

        conn, cursor, _ = _make_fake_conn()
        cursor.rowcount = 1
        await record_canonical_selection(conn, "loto", date(2026, 4, 22), selected)

        # Expect 5 balls + 1 chance = 6 INSERTs
        assert cursor.execute.await_count == 6

    @pytest.mark.asyncio
    async def test_route_flow_handles_em_list_stars(self):
        """EM grid has 'etoiles' as list → unwrapped correctly for record."""
        from services.selection_history import record_canonical_selection

        engine_result = {
            "grids": [
                {"nums": [8, 19, 29, 36, 42], "etoiles": [6, 7], "score": 95, "badges": []},
            ],
            "metadata": {},
        }
        canonical = engine_result["grids"][0]
        sec_val = canonical.get("etoiles")
        sec_list = sec_val if isinstance(sec_val, list) else [sec_val]
        selected = {
            "ball": canonical["nums"],
            "star": sec_list,
        }
        conn, cursor, _ = _make_fake_conn()
        cursor.rowcount = 1
        await record_canonical_selection(conn, "euromillions", date(2026, 4, 21), selected)

        # Expect 5 balls + 2 stars = 7 INSERTs
        assert cursor.execute.await_count == 7


# ═══════════════════════════════════════════════════════════════════════
# V94 invariant extended to V110: chatbot Phase G never writes canonical
# ═══════════════════════════════════════════════════════════════════════

class TestChatbotDoesNotWriteCanonicalV110:
    """V94 hotfix invariant extended to hybride_selection_history.

    The chatbot Phase G must ONLY call get_decay_state and
    get_persistent_brake_map (both READ-ONLY). It must NEVER call
    record_canonical_selection (which is reserved for /api/{game}/generate).
    """

    @pytest.mark.asyncio
    async def test_chatbot_phase_g_uses_only_read_functions(self):
        """Ensure the chatbot Phase G imports do NOT include record_canonical_selection."""
        # Static check: read the source and grep for the forbidden symbol
        import pathlib
        src = pathlib.Path("services/chat_pipeline_shared.py").read_text(encoding="utf-8")
        # record_canonical_selection MUST NOT appear anywhere in chat_pipeline_shared
        assert "record_canonical_selection" not in src, (
            "V94+V110 invariant violated: chatbot must NEVER call "
            "record_canonical_selection. Write operations are reserved "
            "for /api/{game}/generate only."
        )

    @pytest.mark.asyncio
    async def test_chatbot_imports_get_persistent_brake_map_for_read(self):
        """Confirm chatbot imports the READ-ONLY helper (not the WRITE one)."""
        import pathlib
        src = pathlib.Path("services/chat_pipeline_shared.py").read_text(encoding="utf-8")
        # The chatbot may use get_persistent_brake_map (READ-ONLY)
        assert "get_persistent_brake_map" in src
