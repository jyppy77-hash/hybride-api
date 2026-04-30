"""V137 — Multi-grilles avec grid_id UUID tests.

V136.A affichait 1 seule grille canonique (heuristique MIN(selected_at) à la
seconde). V137 introduit grid_id UUID v4 pour permettre l'enregistrement et
l'affichage de TOUTES les grilles générées par chaque visiteur séparément.

Tests :
- TestRecordCanonicalSelectionGridId (3) : grid_id UUID v4 propagé
- TestRecordPdfMetaTopGridId (1) : grid_id UUID v4 par fenêtre PDF
- TestCalendarDetailMultiGrids (4) : data.grids[] (au lieu de data.hybride{})
- TestV110BrakeRegression (2) : V110 brake preserved (subquery JOIN MIN)
"""

import datetime
import os
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

_TEST_TOKEN = "test_admin_token_v137_xxx"

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(
    os.environ,
    {
        "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
        "ADMIN_TOKEN": _TEST_TOKEN, "ADMIN_PASSWORD": "testpw",
    },
)

_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _get_client():
    with _db_env, _static_patch, _static_call:
        import importlib
        import routes.admin_helpers as admin_helpers_mod
        importlib.reload(admin_helpers_mod)
        import routes.admin_perf_calendar as admin_perf_mod
        importlib.reload(admin_perf_mod)
        import routes.admin as admin_mod
        importlib.reload(admin_mod)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _authed_client():
    client = _get_client()
    client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
    return client


def _make_async_conn(cursor):
    """Build a mock conn usable via `async with db_cloudsql.get_connection_readonly() as conn`."""
    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cursor)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _mock_record_conn(rowcount=1):
    """Mock conn pour record_canonical / record_pdf_meta — rowcount fixe."""
    cursor = AsyncMock()
    cursor.rowcount = rowcount
    cursor.execute = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=[])
    cursor.fetchone = AsyncMock(return_value=None)
    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cursor)
    conn.commit = AsyncMock()
    return conn, cursor


# ════════════════════════════════════════════════════════════════════
# TestRecordCanonicalSelectionGridId
# ════════════════════════════════════════════════════════════════════


class TestRecordCanonicalSelectionGridId:

    @pytest.mark.asyncio
    async def test_generates_uuid_v4_format(self):
        """V137 — record_canonical_selection retourne un grid_id UUID v4 valide."""
        from services.selection_history import record_canonical_selection
        conn, _ = _mock_record_conn()
        result = await record_canonical_selection(
            conn, "loto", datetime.date(2026, 4, 29),
            {"ball": [3, 12, 25, 33, 47], "chance": [7]},
        )
        assert "grid_id" in result
        gid = result["grid_id"]
        assert _UUID_V4_RE.match(gid), f"V137 grid_id n'est pas un UUID v4 valide: {gid}"

    @pytest.mark.asyncio
    async def test_propagates_grid_id_to_all_inserts(self):
        """V137 — Tous les 6 INSERTs (5 boules + 1 chance) reçoivent le même grid_id."""
        from services.selection_history import record_canonical_selection
        conn, cursor = _mock_record_conn()
        result = await record_canonical_selection(
            conn, "loto", datetime.date(2026, 4, 29),
            {"ball": [3, 12, 25, 33, 47], "chance": [7]},
        )
        expected_gid = result["grid_id"]
        # Inspecter chaque cursor.execute call : le dernier paramètre du tuple = grid_id
        assert cursor.execute.await_count == 6
        for call in cursor.execute.await_args_list:
            sql = call.args[0]
            params = call.args[1]
            assert "grid_id" in sql, "V137 SQL doit contenir grid_id"
            # params order: (game, n_int, ntype, draw_date_target, grid_id)
            assert params[-1] == expected_gid, (
                f"V137 tous les INSERTs doivent avoir le même grid_id, "
                f"attendu={expected_gid} obtenu={params[-1]}"
            )

    @pytest.mark.asyncio
    async def test_two_consecutive_calls_have_different_grid_ids(self):
        """V137 — 2 appels successifs (2 visiteurs) génèrent 2 UUIDs distincts."""
        from services.selection_history import record_canonical_selection
        conn1, _ = _mock_record_conn()
        conn2, _ = _mock_record_conn()
        result1 = await record_canonical_selection(
            conn1, "loto", datetime.date(2026, 4, 29),
            {"ball": [1, 2, 3, 4, 5], "chance": [1]},
        )
        result2 = await record_canonical_selection(
            conn2, "loto", datetime.date(2026, 4, 29),
            {"ball": [10, 20, 30, 40, 49], "chance": [9]},
        )
        assert result1["grid_id"] != result2["grid_id"]
        assert _UUID_V4_RE.match(result1["grid_id"])
        assert _UUID_V4_RE.match(result2["grid_id"])


# ════════════════════════════════════════════════════════════════════
# TestRecordPdfMetaTopGridId
# ════════════════════════════════════════════════════════════════════


class TestRecordPdfMetaTopGridId:

    @pytest.mark.asyncio
    async def test_pdf_meta_generates_distinct_grid_id(self):
        """V137 — record_pdf_meta_top génère un grid_id UUID v4 distinct par appel."""
        from services.selection_history import record_pdf_meta_top
        conn1, cursor1 = _mock_record_conn()
        conn2, cursor2 = _mock_record_conn()
        r1 = await record_pdf_meta_top(
            conn1, "euromillions", datetime.date(2026, 4, 29),
            "pdf_meta_global", [11, 18, 22, 33, 44], 9,
        )
        r2 = await record_pdf_meta_top(
            conn2, "euromillions", datetime.date(2026, 4, 29),
            "pdf_meta_5a", [5, 11, 18, 28, 49], 7,
        )
        assert r1["grid_id"] != r2["grid_id"]
        assert _UUID_V4_RE.match(r1["grid_id"])
        assert _UUID_V4_RE.match(r2["grid_id"])
        # Vérifier propagation aux INSERTs (params order: game, n, [type], date, source, grid_id)
        for call in cursor1.execute.await_args_list:
            assert call.args[1][-1] == r1["grid_id"]


# ════════════════════════════════════════════════════════════════════
# TestCalendarDetailMultiGrids
# ════════════════════════════════════════════════════════════════════


class TestCalendarDetailMultiGrids:

    def test_returns_all_grids_separately(self):
        """V137 — 3 grilles enregistrées → data.grids[] contient 3 items distincts."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 28)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)  # FDJ pré-tirage
        # 3 grilles distinctes generator + 1 grille pdf_meta_global
        cursor.fetchall = AsyncMock(return_value=[
            # Grille 1 (gid=g1) — 5 boules + 1 chance
            {"grid_id": "g1-uuid-aaaa-bbbb-cccc-111111111111", "source": "generator", "number_value": 10, "number_type": "ball", "first_seen": "2026-04-27 08:12:00"},
            {"grid_id": "g1-uuid-aaaa-bbbb-cccc-111111111111", "source": "generator", "number_value": 19, "number_type": "ball", "first_seen": "2026-04-27 08:12:00"},
            {"grid_id": "g1-uuid-aaaa-bbbb-cccc-111111111111", "source": "generator", "number_value": 23, "number_type": "ball", "first_seen": "2026-04-27 08:12:00"},
            {"grid_id": "g1-uuid-aaaa-bbbb-cccc-111111111111", "source": "generator", "number_value": 31, "number_type": "ball", "first_seen": "2026-04-27 08:12:00"},
            {"grid_id": "g1-uuid-aaaa-bbbb-cccc-111111111111", "source": "generator", "number_value": 46, "number_type": "ball", "first_seen": "2026-04-27 08:12:00"},
            {"grid_id": "g1-uuid-aaaa-bbbb-cccc-111111111111", "source": "generator", "number_value": 9, "number_type": "chance", "first_seen": "2026-04-27 08:12:00"},
            # Grille 2 (gid=g2)
            {"grid_id": "g2-uuid-aaaa-bbbb-cccc-222222222222", "source": "generator", "number_value": 7, "number_type": "ball", "first_seen": "2026-04-27 09:45:00"},
            {"grid_id": "g2-uuid-aaaa-bbbb-cccc-222222222222", "source": "generator", "number_value": 15, "number_type": "ball", "first_seen": "2026-04-27 09:45:00"},
            {"grid_id": "g2-uuid-aaaa-bbbb-cccc-222222222222", "source": "generator", "number_value": 22, "number_type": "ball", "first_seen": "2026-04-27 09:45:00"},
            {"grid_id": "g2-uuid-aaaa-bbbb-cccc-222222222222", "source": "generator", "number_value": 33, "number_type": "ball", "first_seen": "2026-04-27 09:45:00"},
            {"grid_id": "g2-uuid-aaaa-bbbb-cccc-222222222222", "source": "generator", "number_value": 41, "number_type": "ball", "first_seen": "2026-04-27 09:45:00"},
            {"grid_id": "g2-uuid-aaaa-bbbb-cccc-222222222222", "source": "generator", "number_value": 4, "number_type": "chance", "first_seen": "2026-04-27 09:45:00"},
            # Grille 3 (gid=g3)
            {"grid_id": "g3-uuid-aaaa-bbbb-cccc-333333333333", "source": "generator", "number_value": 3, "number_type": "ball", "first_seen": "2026-04-27 11:20:00"},
            {"grid_id": "g3-uuid-aaaa-bbbb-cccc-333333333333", "source": "generator", "number_value": 12, "number_type": "ball", "first_seen": "2026-04-27 11:20:00"},
            {"grid_id": "g3-uuid-aaaa-bbbb-cccc-333333333333", "source": "generator", "number_value": 28, "number_type": "ball", "first_seen": "2026-04-27 11:20:00"},
            {"grid_id": "g3-uuid-aaaa-bbbb-cccc-333333333333", "source": "generator", "number_value": 35, "number_type": "ball", "first_seen": "2026-04-27 11:20:00"},
            {"grid_id": "g3-uuid-aaaa-bbbb-cccc-333333333333", "source": "generator", "number_value": 47, "number_type": "ball", "first_seen": "2026-04-27 11:20:00"},
            {"grid_id": "g3-uuid-aaaa-bbbb-cccc-333333333333", "source": "generator", "number_value": 2, "number_type": "chance", "first_seen": "2026-04-27 11:20:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        assert "grids" in data, "V137 contrat API : data.grids[] obligatoire"
        assert "hybride" not in data or data.get("hybride") in (None, {}), "V137 retire data.hybride"
        assert data["summary"]["total_grids"] == 3
        # 3 grilles distinctes
        gids = sorted([g["grid_id"] for g in data["grids"]])
        assert len(set(gids)) == 3
        # Chaque grille a ses 5 boules + N secondaires (V137.D : liste)
        for g in data["grids"]:
            assert len(g["balls"]) == 5
            assert g["secondary_balls"]  # V137.D : liste non-vide
            assert g["secondary"] is not None  # V137.D : rétrocompat scalaire

    def test_calculates_match_per_grid(self):
        """V137 — Chaque grille a son matches_balls propre (pas un agrégat)."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 25)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        # FDJ post-tirage : balls={5,18,22,31,49}, chance=3
        cursor.fetchone = AsyncMock(return_value={
            "date_de_tirage": target_date,
            "boule_1": 5, "boule_2": 18, "boule_3": 22, "boule_4": 31, "boule_5": 49,
            "numero_chance": 3,
        })
        # 2 grilles : g1 = 1 match (22), g2 = 3 matches (5, 18, 31)
        cursor.fetchall = AsyncMock(return_value=[
            # g1 : [7, 22, 27, 33, 41] + chance 8 → 1 match boules
            {"grid_id": "g1", "source": "generator", "number_value": 7, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 22, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 27, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 33, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 41, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 8, "number_type": "chance", "first_seen": "2026-04-24 12:00:00"},
            # g2 : [5, 11, 18, 31, 44] + chance 3 → 3 matches boules + chance match
            {"grid_id": "g2", "source": "generator", "number_value": 5, "number_type": "ball", "first_seen": "2026-04-24 14:00:00"},
            {"grid_id": "g2", "source": "generator", "number_value": 11, "number_type": "ball", "first_seen": "2026-04-24 14:00:00"},
            {"grid_id": "g2", "source": "generator", "number_value": 18, "number_type": "ball", "first_seen": "2026-04-24 14:00:00"},
            {"grid_id": "g2", "source": "generator", "number_value": 31, "number_type": "ball", "first_seen": "2026-04-24 14:00:00"},
            {"grid_id": "g2", "source": "generator", "number_value": 44, "number_type": "ball", "first_seen": "2026-04-24 14:00:00"},
            {"grid_id": "g2", "source": "generator", "number_value": 3, "number_type": "chance", "first_seen": "2026-04-24 14:00:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        # Récupérer les 2 grilles
        g1 = next(g for g in data["grids"] if g["grid_id"] == "g1")
        g2 = next(g for g in data["grids"] if g["grid_id"] == "g2")
        # Matchs propres calculés par grille
        assert g1["matches_balls"] == 1, f"g1 doit avoir 1 match (22), got {g1['matches_balls']}"
        assert g2["matches_balls"] == 3, f"g2 doit avoir 3 matches (5,18,31), got {g2['matches_balls']}"
        assert g2["matches_secondary"] is True, "g2 chance=3 = FDJ chance"

    def test_best_match_grid_id_pointed_correctly(self):
        """V137 — summary.best_match_grid_id pointe la grille avec le plus de matchs."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 25)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value={
            "date_de_tirage": target_date,
            "boule_1": 5, "boule_2": 18, "boule_3": 22, "boule_4": 31, "boule_5": 49,
            "numero_chance": 3,
        })
        # g1 = 1 match, g2 = 3 matches → best = g2
        cursor.fetchall = AsyncMock(return_value=[
            {"grid_id": "g1", "source": "generator", "number_value": 22, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 7, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 27, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 33, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 41, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 8, "number_type": "chance", "first_seen": "2026-04-24 12:00:00"},
            {"grid_id": "g2", "source": "generator", "number_value": 5, "number_type": "ball", "first_seen": "2026-04-24 14:00:00"},
            {"grid_id": "g2", "source": "generator", "number_value": 18, "number_type": "ball", "first_seen": "2026-04-24 14:00:00"},
            {"grid_id": "g2", "source": "generator", "number_value": 31, "number_type": "ball", "first_seen": "2026-04-24 14:00:00"},
            {"grid_id": "g2", "source": "generator", "number_value": 11, "number_type": "ball", "first_seen": "2026-04-24 14:00:00"},
            {"grid_id": "g2", "source": "generator", "number_value": 44, "number_type": "ball", "first_seen": "2026-04-24 14:00:00"},
            {"grid_id": "g2", "source": "generator", "number_value": 3, "number_type": "chance", "first_seen": "2026-04-24 14:00:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["best_match_count"] == 3
        assert data["summary"]["best_match_grid_id"] == "g2"

    def test_legacy_rows_grouped_with_is_legacy_flag(self):
        """V137 — Rows pré-V137 (grid_id NULL) → 1 grille agrégée par source avec is_legacy=true."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 27)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)  # pré-tirage
        # 6 rows generator avec grid_id=NULL (legacy V136.A pre-V137)
        cursor.fetchall = AsyncMock(return_value=[
            {"grid_id": None, "source": "generator", "number_value": 10, "number_type": "ball", "first_seen": "2026-04-26 14:30:00"},
            {"grid_id": None, "source": "generator", "number_value": 19, "number_type": "ball", "first_seen": "2026-04-26 14:30:00"},
            {"grid_id": None, "source": "generator", "number_value": 23, "number_type": "ball", "first_seen": "2026-04-26 14:30:00"},
            {"grid_id": None, "source": "generator", "number_value": 31, "number_type": "ball", "first_seen": "2026-04-26 14:30:00"},
            {"grid_id": None, "source": "generator", "number_value": 46, "number_type": "ball", "first_seen": "2026-04-26 14:30:00"},
            {"grid_id": None, "source": "generator", "number_value": 9, "number_type": "chance", "first_seen": "2026-04-26 14:30:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total_grids"] == 1
        legacy = data["grids"][0]
        assert legacy["is_legacy"] is True
        assert legacy["grid_id"].startswith("_legacy_loto_2026-04-27_")
        assert legacy["balls"] == [10, 19, 23, 31, 46]


# ════════════════════════════════════════════════════════════════════
# TestV110BrakeRegression — préservation sémantique V110
# ════════════════════════════════════════════════════════════════════


class TestV110BrakeRegression:

    @pytest.mark.asyncio
    async def test_brake_uses_only_first_grid_per_day(self):
        """V137 régression V110 — get_persistent_brake_map utilise subquery JOIN
        MIN(selected_at) INTERVAL 1 SECOND pour ne lire que la 1ère grille
        temporelle par draw_date_target. Sinon multi-grilles V137 dégénèrerait
        le brake (~60 numéros bloqués au lieu de ~5 par tier)."""
        from services.selection_history import get_persistent_brake_map
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        # 1ère query : draw_date_target liste DESC
        # 2ème query : numéros filtrés par subquery JOIN
        cursor.fetchall = AsyncMock(side_effect=[
            [{"draw_date_target": datetime.date(2026, 4, 26)}],  # T-1 unique
            [],  # rows filtrés (vide pour ce test, on vérifie le SQL généré)
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
            conn, "loto", datetime.date(2026, 4, 27), "ball", _Cfg(),
        )
        # Le 2ème SELECT doit contenir INTERVAL 1 SECOND + INNER JOIN MIN
        executed_sql = " ".join(
            (call.args[0] if call.args else "") for call in cursor.execute.await_args_list
        )
        assert "INTERVAL 1 SECOND" in executed_sql, (
            f"V137 régression V110 : get_persistent_brake_map doit filtrer 1ère "
            f"grille via INTERVAL 1 SECOND. SQL = {executed_sql}"
        )
        assert "MIN(selected_at)" in executed_sql, (
            f"V137 régression V110 : subquery JOIN MIN(selected_at) requis. SQL = {executed_sql}"
        )
        assert "source = 'generator'" in executed_sql, (
            "V136 préservé — filtre source='generator' obligatoire"
        )
        # V137.B — MIN(grid_id) + clause legacy-safe IS NULL OR
        assert "MIN(grid_id)" in executed_sql, (
            f"V137.B régression V110 : MIN(grid_id) requis pour filtrer 1 grille "
            f"déterministe parmi N grilles enregistrées même seconde. SQL = {executed_sql}"
        )
        assert "first_grid_id IS NULL" in executed_sql, (
            f"V137.B régression V110 : clause `IS NULL OR =` requise pour fallback "
            f"legacy V136.A. SQL = {executed_sql}"
        )

    @pytest.mark.asyncio
    async def test_brake_value_unchanged_with_multi_grids_in_db(self):
        """V137 régression V110 — Si 2 grilles distinctes (g1, g2) sont
        enregistrées pour T-1, seule g1 (1ère temporelle) doit influencer le brake.
        Le SQL filtre via INTERVAL 1 SECOND ; le mock simule cela en retournant
        SEULEMENT les 5 numéros de g1 (le SQL filtré n'a pas accès à g2)."""
        from services.selection_history import get_persistent_brake_map
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        # T-1 : g1 = [3,12,25,33,47] (1ère) ; g2 = [7,15,22,33,41] (2ème)
        # Le SQL filtre INTERVAL 1 SECOND retourne SEULEMENT g1 (5 numéros)
        cursor.fetchall = AsyncMock(side_effect=[
            [{"draw_date_target": datetime.date(2026, 4, 26)}],
            [
                {"number_value": 3, "draw_date_target": datetime.date(2026, 4, 26)},
                {"number_value": 12, "draw_date_target": datetime.date(2026, 4, 26)},
                {"number_value": 25, "draw_date_target": datetime.date(2026, 4, 26)},
                {"number_value": 33, "draw_date_target": datetime.date(2026, 4, 26)},
                {"number_value": 47, "draw_date_target": datetime.date(2026, 4, 26)},
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
            conn, "loto", datetime.date(2026, 4, 27), "ball", _Cfg(),
        )
        # Brake T-1 = exactement 5 numéros (g1 seul), pas 10 (g1+g2 cumul)
        assert len(brake) == 5, (
            f"V137 régression V110 : brake T-1 doit contenir 5 numéros (1ère "
            f"grille seule), pas l'union de N grilles. Got: {len(brake)} numbers."
        )
        assert brake == {3: 0.20, 12: 0.20, 25: 0.20, 33: 0.20, 47: 0.20}
