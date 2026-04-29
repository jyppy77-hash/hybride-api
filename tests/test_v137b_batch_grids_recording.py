"""V137.B — Batch grids recording (TOUTES les grilles) + frontend UTC→Paris + V110 brake MIN(grid_id).

V137 enregistrait UNIQUEMENT la 1ère grille du batch (grids[0]). V137.B boucle
sur TOUTES les grilles via record_canonical_selection (1 UUID par grille).
Avec N grilles dans la même seconde, V110 brake doit filtrer MIN(grid_id)
pour ne lire que la 1ère grille déterministe.

Tests :
- TestBatchGridsRecording (3) : boucle batch loto/em + graceful failure
- TestFrontendUtcToParis (1) : admin.js contient toLocaleTimeString + Europe/Paris
- TestV110BrakeMinGridIdFilter (2) : MIN(grid_id) + clause IS NULL OR legacy-safe
"""

import datetime
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

_TEST_TOKEN = "test_admin_token_v137b_xxx"

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(
    os.environ,
    {
        "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
        "ADMIN_TOKEN": _TEST_TOKEN, "ADMIN_PASSWORD": "testpw",
    },
)


def _get_client():
    with _db_env, _static_patch, _static_call:
        import importlib
        import routes.api_analyse_unified as api_mod
        importlib.reload(api_mod)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _make_async_cm(value=None):
    """AsyncContextManager mock pour `async with ...` patterns."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=value if value is not None else MagicMock())
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_mock_engine(grids: list, secondary_name: str = "chance", num_max: int = 49):
    """Mock engine returning a predefined batch of grids."""
    engine = MagicMock()
    engine.cfg = MagicMock()
    engine.cfg.saturation_persistent_enabled = True
    engine.cfg.secondary_name = secondary_name
    engine.cfg.secondary_min = 1
    engine.cfg.secondary_max = 10 if secondary_name == "chance" else 12
    engine.generate_grids = AsyncMock(return_value={
        "grids": grids,
        "metadata": {"window_size": 100, "mode": "balanced"},
    })
    return engine


# ════════════════════════════════════════════════════════════════════
# TestBatchGridsRecording
# ════════════════════════════════════════════════════════════════════


class TestBatchGridsRecording:

    def test_batch_records_all_grids_loto(self):
        """V137.B — /api/loto/generate avec n=3 → 3 appels record_canonical_selection."""
        client = _get_client()
        grids = [
            {"nums": [3, 12, 25, 33, 47], "chance": 7},
            {"nums": [1, 19, 22, 40, 45], "chance": 4},
            {"nums": [4, 13, 24, 35, 49], "chance": 1},
        ]
        record_spy = AsyncMock(return_value={"grid_id": "uuid-mock", "inserted": 6, "ignored": 0})
        with patch(
            "routes.api_analyse_unified.get_engine",
            return_value=_make_mock_engine(grids, secondary_name="chance"),
        ), patch(
            "routes.api_analyse_unified.db_cloudsql.get_connection",
            return_value=_make_async_cm(),
        ), patch(
            "routes.api_analyse_unified.record_canonical_selection",
            new=record_spy,
        ), patch(
            "routes.api_analyse_unified.check_and_update_decay",
            new=AsyncMock(),
        ), patch(
            "routes.api_analyse_unified.get_decay_state",
            new=AsyncMock(return_value={}),
        ), patch(
            "routes.api_analyse_unified.get_persistent_brake_map",
            new=AsyncMock(return_value={}),
        ):
            resp = client.get("/api/loto/generate?n=3&mode=balanced")
        assert resp.status_code == 200
        # V137.B : 3 appels record_canonical_selection (1 par grille du batch)
        assert record_spy.await_count == 3, (
            f"V137.B : 3 grilles dans le batch → 3 appels attendus, "
            f"got {record_spy.await_count}"
        )

    def test_batch_records_all_grids_em(self):
        """V137.B — Symétrie EuroMillions : /api/euromillions/generate avec n=3 → 3 appels."""
        client = _get_client()
        grids = [
            {"nums": [3, 12, 25, 33, 47], "etoile": [2, 7]},
            {"nums": [1, 19, 22, 40, 45], "etoile": [4, 9]},
            {"nums": [4, 13, 24, 35, 49], "etoile": [1, 11]},
        ]
        record_spy = AsyncMock(return_value={"grid_id": "uuid-mock", "inserted": 6, "ignored": 0})
        with patch(
            "routes.api_analyse_unified.get_engine",
            return_value=_make_mock_engine(grids, secondary_name="etoile"),
        ), patch(
            "routes.api_analyse_unified.db_cloudsql.get_connection",
            return_value=_make_async_cm(),
        ), patch(
            "routes.api_analyse_unified.record_canonical_selection",
            new=record_spy,
        ), patch(
            "routes.api_analyse_unified.check_and_update_decay",
            new=AsyncMock(),
        ), patch(
            "routes.api_analyse_unified.get_decay_state",
            new=AsyncMock(return_value={}),
        ), patch(
            "routes.api_analyse_unified.get_persistent_brake_map",
            new=AsyncMock(return_value={}),
        ):
            resp = client.get("/api/euromillions/generate?n=3&mode=balanced")
        assert resp.status_code == 200
        assert record_spy.await_count == 3, (
            f"V137.B EM : 3 grilles → 3 appels attendus, got {record_spy.await_count}"
        )

    def test_batch_continues_on_partial_failure(self):
        """V137.B — Si grille #2 lève Exception, #1+#3+#4+#5 continuent (graceful)."""
        client = _get_client()
        grids = [
            {"nums": [1, 2, 3, 4, 5], "chance": 1},
            {"nums": [6, 7, 8, 9, 10], "chance": 2},  # Cette grille échouera
            {"nums": [11, 12, 13, 14, 15], "chance": 3},
            {"nums": [16, 17, 18, 19, 20], "chance": 4},
            {"nums": [21, 22, 23, 24, 25], "chance": 5},
        ]
        # AsyncMock side_effect : 1ère grille OK, 2ème exception, 3+4+5 OK
        call_count = {"n": 0}

        async def record_with_partial_fail(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise Exception("simulated DB transient error grid #2")
            return {"grid_id": f"uuid-{call_count['n']}", "inserted": 6, "ignored": 0}

        record_spy = AsyncMock(side_effect=record_with_partial_fail)
        with patch(
            "routes.api_analyse_unified.get_engine",
            return_value=_make_mock_engine(grids, secondary_name="chance"),
        ), patch(
            "routes.api_analyse_unified.db_cloudsql.get_connection",
            return_value=_make_async_cm(),
        ), patch(
            "routes.api_analyse_unified.record_canonical_selection",
            new=record_spy,
        ), patch(
            "routes.api_analyse_unified.check_and_update_decay",
            new=AsyncMock(),
        ), patch(
            "routes.api_analyse_unified.get_decay_state",
            new=AsyncMock(return_value={}),
        ), patch(
            "routes.api_analyse_unified.get_persistent_brake_map",
            new=AsyncMock(return_value={}),
        ):
            resp = client.get("/api/loto/generate?n=5&mode=balanced")
        assert resp.status_code == 200
        # V137.B : 5 appels tentés (1 fail, 4 OK), boucle ne s'arrête pas
        assert record_spy.await_count == 5, (
            f"V137.B graceful : 5 appels attendus malgré 1 fail, "
            f"got {record_spy.await_count}"
        )


# ════════════════════════════════════════════════════════════════════
# TestFrontendUtcToParis
# ════════════════════════════════════════════════════════════════════


class TestFrontendUtcToParis:

    def test_admin_js_contains_paris_timezone_conversion(self):
        """V137.B — admin.js doit contenir toLocaleTimeString + Europe/Paris
        pour convertir les timestamps UTC en heure locale dans le modal admin."""
        with open("ui/static/admin.js", encoding="utf-8") as f:
            content = f.read()
        assert "toLocaleTimeString" in content, (
            "V137.B : admin.js doit utiliser toLocaleTimeString pour formater l'heure"
        )
        assert "Europe/Paris" in content, (
            "V137.B : admin.js doit spécifier timeZone='Europe/Paris' pour la conversion UTC"
        )
        # Heuristique : la conversion doit être dans le contexte first_seen
        assert "first_seen" in content
        # Heuristique : UTC explicite via 'Z' suffix
        assert "+ 'Z'" in content or "+'Z'" in content, (
            "V137.B : ajout 'Z' suffix pour interpréter first_seen comme UTC requis"
        )


# ════════════════════════════════════════════════════════════════════
# TestV110BrakeMinGridIdFilter
# ════════════════════════════════════════════════════════════════════


class TestV110BrakeMinGridIdFilter:

    @pytest.mark.asyncio
    async def test_brake_sql_contains_min_grid_id_filter(self):
        """V137.B — get_persistent_brake_map SQL contient MIN(grid_id) +
        clause `IS NULL OR =` pour gérer 5+ grilles dans la même seconde
        (sinon ~30 numéros bloqués au lieu de 5 → V110 dégénère)."""
        from services.selection_history import get_persistent_brake_map
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchall = AsyncMock(side_effect=[
            [{"draw_date_target": datetime.date(2026, 4, 28)}],  # T-1
            [],
        ])
        conn = MagicMock()
        conn.cursor = AsyncMock(return_value=cursor)

        from dataclasses import dataclass

        @dataclass
        class _Cfg:
            saturation_persistent_enabled: bool = True
            saturation_brake_persistent_t1: float = 0.20
            saturation_brake_persistent_t2: float = 0.50
            saturation_persistent_window: int = 2

        await get_persistent_brake_map(
            conn, "loto", datetime.date(2026, 4, 29), "ball", _Cfg(),
        )
        executed_sql = " ".join(
            (call.args[0] if call.args else "") for call in cursor.execute.await_args_list
        )
        # V137 préservé
        assert "MIN(selected_at)" in executed_sql
        assert "INTERVAL 1 SECOND" in executed_sql
        # V137.B nouveau : MIN(grid_id) + clause legacy-safe
        assert "MIN(grid_id)" in executed_sql, (
            f"V137.B : MIN(grid_id) requis pour filtrer 1 grille déterministe "
            f"parmi N grilles enregistrées même seconde. SQL = {executed_sql}"
        )
        assert "first_grid_id IS NULL" in executed_sql, (
            f"V137.B : clause `f.first_grid_id IS NULL OR ...` requise pour "
            f"fallback legacy V136.A (rows grid_id=NULL). SQL = {executed_sql}"
        )

    @pytest.mark.asyncio
    async def test_brake_value_with_5_grids_same_second(self):
        """V137.B — Avec 5 grilles V137.B enregistrées dans la même seconde,
        seule la 1ère grille (1er grid_id alphabétique) contribue au brake.
        Le SQL filter retourne uniquement 5 numéros (1 grille), pas 25 (5 grilles)."""
        from services.selection_history import get_persistent_brake_map
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        # Le SQL avec MIN(grid_id) retourne uniquement les 5 numéros de la 1ère grille
        # (les 4 autres grilles sont filtrées car grid_id != first_grid_id)
        cursor.fetchall = AsyncMock(side_effect=[
            [{"draw_date_target": datetime.date(2026, 4, 28)}],  # T-1
            [
                {"number_value": 3, "draw_date_target": datetime.date(2026, 4, 28)},
                {"number_value": 12, "draw_date_target": datetime.date(2026, 4, 28)},
                {"number_value": 25, "draw_date_target": datetime.date(2026, 4, 28)},
                {"number_value": 33, "draw_date_target": datetime.date(2026, 4, 28)},
                {"number_value": 47, "draw_date_target": datetime.date(2026, 4, 28)},
            ],
        ])
        conn = MagicMock()
        conn.cursor = AsyncMock(return_value=cursor)

        from dataclasses import dataclass

        @dataclass
        class _Cfg:
            saturation_persistent_enabled: bool = True
            saturation_brake_persistent_t1: float = 0.20
            saturation_brake_persistent_t2: float = 0.50
            saturation_persistent_window: int = 2

        brake = await get_persistent_brake_map(
            conn, "loto", datetime.date(2026, 4, 29), "ball", _Cfg(),
        )
        # V137.B critique : brake = 5 numéros (1 grille filtrée), pas 25
        assert len(brake) == 5, (
            f"V137.B PRIO V110 : brake doit contenir 5 numéros (1 grille via "
            f"MIN(grid_id)), pas 25 (5 grilles cumulées). Got {len(brake)}."
        )
        assert brake == {3: 0.20, 12: 0.20, 25: 0.20, 33: 0.20, 47: 0.20}
