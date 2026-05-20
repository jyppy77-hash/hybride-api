"""V142.E — Fix patch PDF EM 2 étoiles tracking calendar admin.

Couvre :
- services/selection_history.py::record_pdf_meta_top — signature `secondary_top`
  accepte int | list[int] | None (rétrocompat V136 singleton).
- routes/api_analyse_unified.py — call site L420-434 : EM passe 2 stars, Loto 1 chance.

Contexte : anomalie identifiée audit READ-ONLY 2026-05-20 §Axe 5
(docs/AUDIT_ENGINE_HYBRIDE_PRE_V142_2026-05-20.md). Le call site EM passait
`secondary_top[0]` singleton → record_pdf_meta_top enregistrait 1 étoile au lieu
de 2 dans hybride_selection_history (source='pdf_meta_*'). Impact calendar admin
sous-évaluant matches EM ~50% (_calc_match V137.D accepte déjà liste 2 stars).
"""

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────
# Helper mock — pattern identique tests/test_v136_admin_calendar.py
# ─────────────────────────────────────────────────────────────────────


def _mock_record_conn(rowcounts=None):
    """Mock conn for record_pdf_meta_top — controls cursor.rowcount per execute."""
    rowcounts = rowcounts if rowcounts is not None else [1] * 10
    cursor = AsyncMock()
    seq = iter(rowcounts)

    async def execute_with_rowcount(*args, **kwargs):
        try:
            cursor.rowcount = next(seq)
        except StopIteration:
            cursor.rowcount = 1

    cursor.execute = AsyncMock(side_effect=execute_with_rowcount)
    cursor.rowcount = 1
    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cursor)
    conn.commit = AsyncMock()
    return conn, cursor


# ═══════════════════════════════════════════════════════════════════
# T1 — EM avec list[int, int] → 2 INSERTs star
# ═══════════════════════════════════════════════════════════════════


class TestRecordPdfMetaTopV142E:

    @pytest.mark.asyncio
    async def test_em_writes_2_stars_when_list_provided(self):
        """V142.E — EM : secondary_top=[7, 9] → 2 INSERTs star + 5 INSERTs ball = 7 total."""
        from services.selection_history import record_pdf_meta_top
        conn, cursor = _mock_record_conn([1] * 7)
        result = await record_pdf_meta_top(
            conn, "euromillions", datetime.date(2026, 5, 20),
            "pdf_meta_global", [11, 18, 22, 33, 44], [7, 9],
        )
        assert result["inserted"] == 7
        assert result["ignored"] == 0
        # 5 boules + 2 étoiles = 7 INSERTs
        assert cursor.execute.await_count == 7
        # Les 2 derniers INSERTs sont les 2 étoiles
        last_2_calls = cursor.execute.await_args_list[-2:]
        star_values = []
        for call in last_2_calls:
            sql = call.args[0]
            params = call.args[1]
            assert "INSERT IGNORE INTO hybride_selection_history" in sql
            # number_type est params[2] : 'star' pour EM
            assert params[2] == "star"
            star_values.append(params[1])
        assert sorted(star_values) == [7, 9]
        conn.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_loto_writes_1_chance_when_int_provided(self):
        """V142.E — Rétrocompat V136 : Loto singleton int=7 → 1 INSERT chance."""
        from services.selection_history import record_pdf_meta_top
        conn, cursor = _mock_record_conn([1] * 6)
        result = await record_pdf_meta_top(
            conn, "loto", datetime.date(2026, 5, 20),
            "pdf_meta_global", [3, 12, 25, 33, 47], 7,
        )
        assert result["inserted"] == 6
        # 5 boules + 1 chance = 6 INSERTs (rétrocompat singleton)
        assert cursor.execute.await_count == 6
        last_call = cursor.execute.await_args_list[-1]
        assert last_call.args[1][1] == 7
        assert last_call.args[1][2] == "chance"

    @pytest.mark.asyncio
    async def test_loto_writes_1_chance_when_list_provided(self):
        """V142.E — Loto : secondary_top=[7] (liste 1 élément) → 1 INSERT chance."""
        from services.selection_history import record_pdf_meta_top
        conn, cursor = _mock_record_conn([1] * 6)
        result = await record_pdf_meta_top(
            conn, "loto", datetime.date(2026, 5, 20),
            "pdf_meta_5a", [3, 12, 25, 33, 47], [7],
        )
        assert result["inserted"] == 6
        assert cursor.execute.await_count == 6
        last_call = cursor.execute.await_args_list[-1]
        assert last_call.args[1][1] == 7
        assert last_call.args[1][2] == "chance"

    @pytest.mark.asyncio
    async def test_em_empty_list_no_secondary_insert(self):
        """V142.E — EM : secondary_top=[] (vide) → 0 INSERT secondary, juste 5 boules."""
        from services.selection_history import record_pdf_meta_top
        conn, cursor = _mock_record_conn([1] * 5)
        result = await record_pdf_meta_top(
            conn, "euromillions", datetime.date(2026, 5, 20),
            "pdf_meta_2a", [11, 18, 22, 33, 44], [],
        )
        # Liste vide ≠ None → branche if secondary_top is not None vraie mais boucle for vide
        assert result["inserted"] == 5
        assert cursor.execute.await_count == 5

    @pytest.mark.asyncio
    async def test_em_none_secondary_no_secondary_insert(self):
        """V142.E — EM : secondary_top=None → 0 INSERT secondary, juste 5 boules (rétrocompat)."""
        from services.selection_history import record_pdf_meta_top
        conn, cursor = _mock_record_conn([1] * 5)
        result = await record_pdf_meta_top(
            conn, "euromillions", datetime.date(2026, 5, 20),
            "pdf_meta_global", [11, 18, 22, 33, 44], None,
        )
        assert result["inserted"] == 5
        assert cursor.execute.await_count == 5

    @pytest.mark.asyncio
    async def test_em_invalid_value_in_list_skipped_others_inserted(self):
        """V142.E — EM : secondary_top=['abc', 7] → 1 INSERT (invalid skipped via except)."""
        from services.selection_history import record_pdf_meta_top
        # 5 boules + 1 star valide = 6 INSERTs (le 'abc' est skipped, pas d'INSERT pour lui)
        conn, cursor = _mock_record_conn([1] * 6)
        result = await record_pdf_meta_top(
            conn, "euromillions", datetime.date(2026, 5, 20),
            "pdf_meta_5a", [11, 18, 22, 33, 44], ["abc", 7],
        )
        assert result["inserted"] == 6
        # Vérifier qu'aucun execute n'a été appelé avec 'abc' comme number_value
        for call in cursor.execute.await_args_list:
            params = call.args[1]
            # params[1] est number_value (int)
            assert params[1] != "abc"

    @pytest.mark.asyncio
    async def test_em_none_in_list_skipped(self):
        """V142.E — EM : secondary_top=[None, 7] → 1 INSERT (None skipped)."""
        from services.selection_history import record_pdf_meta_top
        conn, cursor = _mock_record_conn([1] * 6)
        result = await record_pdf_meta_top(
            conn, "euromillions", datetime.date(2026, 5, 20),
            "pdf_meta_global", [11, 18, 22, 33, 44], [None, 7],
        )
        # 5 boules + 1 star (7) = 6 (None skipped explicitement par if _s is None)
        assert result["inserted"] == 6
        last_call = cursor.execute.await_args_list[-1]
        assert last_call.args[1][1] == 7
