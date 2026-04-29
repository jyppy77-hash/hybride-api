"""V136 — Admin performance calendar tests.

Couvre :
- routes/admin_perf_calendar.py : 3 endpoints (page HTML + 2 JSON)
- services/selection_history.py : record_pdf_meta_top + filtre source='generator'
- Regression V110 : get_persistent_brake_map ignore les rows pdf_meta_*
"""

import datetime
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

_TEST_TOKEN = "test_admin_token_v136_xxx"

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


# ════════════════════════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════════════════════════


class TestAdminPerfCalendarAuth:

    def test_page_requires_auth(self):
        """V136 — /admin/calendar-perf redirects to login if not authed."""
        client = _get_client()
        resp = client.get("/admin/calendar-perf", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers.get("location", "")

    def test_api_month_requires_auth(self):
        """V136 — JSON API returns 401 if not authed."""
        client = _get_client()
        resp = client.get("/admin/api/calendar-perf/loto/2026/4")
        assert resp.status_code == 401

    def test_api_draw_detail_requires_auth(self):
        """V136 — JSON detail API returns 401 if not authed."""
        client = _get_client()
        resp = client.get("/admin/api/calendar-perf/draw/loto/2026-04-27")
        assert resp.status_code == 401


# ════════════════════════════════════════════════════════════════════
# CALENDAR MONTH
# ════════════════════════════════════════════════════════════════════


class TestCalendarPerfMonth:

    def test_invalid_game_returns_400(self):
        client = _authed_client()
        resp = client.get("/admin/api/calendar-perf/poker/2026/4")
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_game"

    def test_invalid_year_returns_400(self):
        client = _authed_client()
        resp = client.get("/admin/api/calendar-perf/loto/2010/4")
        assert resp.status_code == 400

    def test_invalid_month_returns_400(self):
        client = _authed_client()
        resp = client.get("/admin/api/calendar-perf/loto/2026/13")
        assert resp.status_code == 400

    def test_loto_filters_only_draw_weekdays(self):
        """V136 — Loto draws appear only on Monday (0), Wednesday (2), Saturday (5)."""
        client = _authed_client()
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get("/admin/api/calendar-perf/loto/2026/4")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game"] == "loto"
        assert data["year"] == 2026
        assert data["month"] == 4
        # Avril 2026: lundis 6/13/20/27, mercredis 1/8/15/22/29, samedis 4/11/18/25
        # Total = 4 + 5 + 4 = 13 jours de tirage
        assert len(data["draws"]) == 13
        # Tous doivent être lundi(0), mercredi(2), samedi(5)
        for draw in data["draws"]:
            assert draw["weekday"] in (0, 2, 5)

    def test_em_filters_only_draw_weekdays(self):
        """V136 — EM draws appear only on Tuesday (1), Friday (4)."""
        client = _authed_client()
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get("/admin/api/calendar-perf/euromillions/2026/4")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game"] == "euromillions"
        # Avril 2026: mardis 7/14/21/28, vendredis 3/10/17/24 = 4 + 4 = 8 jours
        assert len(data["draws"]) == 8
        for draw in data["draws"]:
            assert draw["weekday"] in (1, 4)

    def test_month_aggregates_matches_when_fdj_drawn(self):
        """V136 — best_match_count is computed from history vs FDJ on draw days.

        V136.A : SQL generator filtré par subquery JOIN MIN(selected_at) — le test
        mock retourne directement la 1ère grille canonique (filtre fait côté SQL).
        Le mois fait désormais 3 fetchall (FDJ + generator filtré + pdf_meta_*)
        au lieu de 2 (FDJ + history agrégé).
        """
        client = _authed_client()
        # Tirage FDJ Loto 2026-04-06 (lundi) : balls = {3, 12, 30, 36, 42}, chance = 7
        # Generator (V110) avait sélectionné: balls=[3, 12, 25, 33, 47], chance=7
        # → 2 matches balls + 1 secondary
        target_date = datetime.date(2026, 4, 6)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()

        cursor.fetchall = AsyncMock(side_effect=[
            # 1) FDJ rows
            [{
                "date_de_tirage": target_date,
                "boule_1": 3, "boule_2": 12, "boule_3": 30, "boule_4": 36, "boule_5": 42,
                "numero_chance": 7,
            }],
            # 2) V136.A generator filtré : 1ère grille canonique uniquement
            [
                {"draw_date_target": target_date, "source": "generator", "number_value": 3, "number_type": "ball"},
                {"draw_date_target": target_date, "source": "generator", "number_value": 12, "number_type": "ball"},
                {"draw_date_target": target_date, "source": "generator", "number_value": 25, "number_type": "ball"},
                {"draw_date_target": target_date, "source": "generator", "number_value": 33, "number_type": "ball"},
                {"draw_date_target": target_date, "source": "generator", "number_value": 47, "number_type": "ball"},
                {"draw_date_target": target_date, "source": "generator", "number_value": 7, "number_type": "chance"},
            ],
            # 3) V136.A pdf_meta_* : aucun ici
            [],
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get("/admin/api/calendar-perf/loto/2026/4")
        assert resp.status_code == 200
        data = resp.json()
        # Trouver le tirage du 06/04
        target = next(d for d in data["draws"] if d["date"] == "2026-04-06")
        assert target["fdj_drawn"] is True
        assert target["fdj_balls"] == [3, 12, 30, 36, 42]
        assert target["fdj_secondary"] == [7]
        assert target["best_match_count"] == 2  # 3, 12 matchent
        gen = target["stats"]["generator"]
        assert gen is not None
        assert gen["matches_balls"] == 2
        assert gen["matches_secondary"] is True


# ════════════════════════════════════════════════════════════════════
# CALENDAR DRAW DETAIL
# ════════════════════════════════════════════════════════════════════


class TestCalendarPerfDrawDetail:

    def test_invalid_date_format(self):
        client = _authed_client()
        resp = client.get("/admin/api/calendar-perf/draw/loto/not-a-date")
        assert resp.status_code == 400

    def test_pre_tirage_returns_no_fdj_data(self):
        """V136 — Pré-tirage : fdj.drawn=False, matches=null (à venir).

        V136.A : SQL detail = 2 queries successives (MIN(selected_at) + rows
        filtrés). Mock fournit donc 2 fetchone (FDJ + first_ts) + 1 fetchall.
        """
        client = _authed_client()
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        target_date = datetime.date(2026, 4, 27)
        first_ts = datetime.datetime(2026, 4, 26, 14, 30, 0)
        cursor.fetchone = AsyncMock(side_effect=[
            None,  # 1) FDJ row → pré-tirage
            {"first_ts": first_ts},  # 2) V136.A MIN(selected_at) generator
        ])
        # 3) V136.A : rows filtrés (1ère grille canonique generator)
        cursor.fetchall = AsyncMock(return_value=[
            {"source": "generator", "number_value": 10, "number_type": "ball", "first_seen": "2026-04-26 14:30:00"},
            {"source": "generator", "number_value": 19, "number_type": "ball", "first_seen": "2026-04-26 14:30:00"},
            {"source": "generator", "number_value": 23, "number_type": "ball", "first_seen": "2026-04-26 14:30:00"},
            {"source": "generator", "number_value": 31, "number_type": "ball", "first_seen": "2026-04-26 14:30:00"},
            {"source": "generator", "number_value": 46, "number_type": "ball", "first_seen": "2026-04-26 14:30:00"},
            {"source": "generator", "number_value": 9, "number_type": "chance", "first_seen": "2026-04-26 14:30:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get("/admin/api/calendar-perf/draw/loto/2026-04-27")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fdj"]["drawn"] is False
        assert data["fdj"]["balls"] is None
        assert data["hybride"]["generator"] is not None
        assert data["hybride"]["generator"]["balls"] == [10, 19, 23, 31, 46]
        assert data["hybride"]["generator"]["secondary"] == 9
        # Pré-tirage : matches = None
        assert data["hybride"]["generator"]["matches_balls"] is None
        assert data["summary"]["best_match_count"] is None

    def test_post_tirage_calculates_matches(self):
        """V136 — Post-tirage : matches calculés correctement, best_match_source identifié.

        V136.A : SQL detail = 2 queries successives. Mock fournit 2 fetchone
        (FDJ + first_ts) + 1 fetchall (generator filtré + pdf_meta_*).
        """
        client = _authed_client()
        target_date = datetime.date(2026, 4, 25)
        first_ts = datetime.datetime(2026, 4, 24, 12, 0, 0)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(side_effect=[
            {  # 1) FDJ row
                "date_de_tirage": target_date,
                "boule_1": 5, "boule_2": 18, "boule_3": 22, "boule_4": 31, "boule_5": 49,
                "numero_chance": 3,
            },
            {"first_ts": first_ts},  # 2) V136.A MIN(selected_at) generator
        ])
        cursor.fetchall = AsyncMock(return_value=[
            # generator: 1 match (22)
            {"source": "generator", "number_value": 7, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"source": "generator", "number_value": 22, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"source": "generator", "number_value": 27, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"source": "generator", "number_value": 33, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"source": "generator", "number_value": 41, "number_type": "ball", "first_seen": "2026-04-24 12:00:00"},
            {"source": "generator", "number_value": 8, "number_type": "chance", "first_seen": "2026-04-24 12:00:00"},
            # pdf_meta_global: 3 matches (5, 18, 31) + chance 3
            {"source": "pdf_meta_global", "number_value": 5, "number_type": "ball", "first_seen": "2026-04-24 13:00:00"},
            {"source": "pdf_meta_global", "number_value": 11, "number_type": "ball", "first_seen": "2026-04-24 13:00:00"},
            {"source": "pdf_meta_global", "number_value": 18, "number_type": "ball", "first_seen": "2026-04-24 13:00:00"},
            {"source": "pdf_meta_global", "number_value": 31, "number_type": "ball", "first_seen": "2026-04-24 13:00:00"},
            {"source": "pdf_meta_global", "number_value": 44, "number_type": "ball", "first_seen": "2026-04-24 13:00:00"},
            {"source": "pdf_meta_global", "number_value": 3, "number_type": "chance", "first_seen": "2026-04-24 13:00:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get("/admin/api/calendar-perf/draw/loto/2026-04-25")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fdj"]["drawn"] is True
        assert data["fdj"]["balls"] == [5, 18, 22, 31, 49]
        # generator: 1 match
        assert data["hybride"]["generator"]["matches_balls"] == 1
        assert data["hybride"]["generator"]["matches_secondary"] is False
        # pdf_meta_global: 3 matches + secondary True
        assert data["hybride"]["pdf_meta_global"]["matches_balls"] == 3
        assert data["hybride"]["pdf_meta_global"]["matches_secondary"] is True
        # best = pdf_meta_global avec 3 boules
        assert data["summary"]["best_match_count"] == 3
        assert data["summary"]["best_match_source"] == "pdf_meta_global"


# ════════════════════════════════════════════════════════════════════
# record_pdf_meta_top
# ════════════════════════════════════════════════════════════════════


def _mock_record_conn(rowcounts):
    """Mock conn for record_pdf_meta_top — controls cursor.rowcount per execute."""
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


class TestRecordPdfMetaTop:

    @pytest.mark.asyncio
    async def test_inserts_5_balls_plus_secondary_loto(self):
        """V136 — Loto top5 + chance → 6 INSERTs source=pdf_meta_global."""
        from services.selection_history import record_pdf_meta_top
        conn, cursor = _mock_record_conn([1] * 6)
        result = await record_pdf_meta_top(
            conn, "loto", datetime.date(2026, 4, 27),
            "pdf_meta_global", [3, 12, 25, 33, 47], 7,
        )
        assert result["inserted"] == 6
        assert result["ignored"] == 0
        assert result["source"] == "pdf_meta_global"
        assert cursor.execute.await_count == 6
        conn.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_idempotent_via_unique_key(self):
        """V136 — second call same content → all rowcount=0, ignored=6."""
        from services.selection_history import record_pdf_meta_top
        conn, cursor = _mock_record_conn([0] * 6)
        result = await record_pdf_meta_top(
            conn, "loto", datetime.date(2026, 4, 27),
            "pdf_meta_global", [3, 12, 25, 33, 47], 7,
        )
        assert result["inserted"] == 0
        assert result["ignored"] == 6

    @pytest.mark.asyncio
    async def test_invalid_source_returns_error(self):
        """V136 — source='invalid' returns error flag without DB call."""
        from services.selection_history import record_pdf_meta_top
        conn = MagicMock()
        conn.cursor = AsyncMock()
        result = await record_pdf_meta_top(
            conn, "loto", datetime.date(2026, 4, 27),
            "generator",  # generator is reserved for record_canonical_selection
            [3, 12, 25, 33, 47], 7,
        )
        assert result.get("error") is True
        conn.cursor.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_em_uses_star_secondary_type(self):
        """V136 — EuroMillions secondary inserted as number_type='star'."""
        from services.selection_history import record_pdf_meta_top
        conn, cursor = _mock_record_conn([1] * 6)
        result = await record_pdf_meta_top(
            conn, "euromillions", datetime.date(2026, 4, 28),
            "pdf_meta_5a", [11, 18, 22, 33, 44], 9,
        )
        assert result["inserted"] == 6
        # Le 6e execute (secondary) doit utiliser 'star'
        last_call = cursor.execute.await_args_list[-1]
        sql = last_call.args[0]
        params = last_call.args[1]
        assert "VALUES (%s, %s, %s, %s, %s)" in sql
        # params order: (game, n_int, secondary_type, draw_date_target, source)
        assert params[2] == "star"


# ════════════════════════════════════════════════════════════════════
# REGRESSION V110 — get_persistent_brake_map ignores pdf_meta_*
# ════════════════════════════════════════════════════════════════════


class TestV110RegressionFilterByGenerator:

    @pytest.mark.asyncio
    async def test_get_persistent_brake_map_filters_source_generator(self):
        """V136 régression V110 — get_persistent_brake_map ne lit que les rows
        source='generator'. SQL doit contenir 'source = ' filter."""
        from services.selection_history import get_persistent_brake_map

        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[])  # aucun résultat → brake vide
        conn = MagicMock()
        conn.cursor = AsyncMock(return_value=cursor)

        from dataclasses import dataclass

        @dataclass
        class _Cfg:
            saturation_persistent_enabled: bool = True
            saturation_brake_persistent_t1: float = 0.20
            saturation_brake_persistent_t2: float = 0.50
            saturation_persistent_window: int = 2

        result = await get_persistent_brake_map(
            conn, "loto", datetime.date(2026, 4, 27), "ball", _Cfg(),
        )
        assert result == {}
        # Le SELECT distinct doit avoir été exécuté avec source='generator'
        assert cursor.execute.await_count >= 1
        first_sql = cursor.execute.await_args_list[0].args[0]
        assert "source = 'generator'" in first_sql, (
            f"V136 régression V110 : le filtre source='generator' est manquant dans get_persistent_brake_map. SQL = {first_sql}"
        )
