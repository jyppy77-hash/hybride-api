"""V136.A — Tests adaptés V137 (multi-grilles).

Originellement V136.A testait l'heuristique "1ère grille canonique uniquement"
(filtre MIN(selected_at) à la seconde près). V137 abandonne ce filtre côté
detail tirage : data.grids[] retourne TOUTES les grilles séparément (chaque
visiteur a sa propre grille avec grid_id distinct).

Ces tests sont adaptés au contrat V137 :
- TestDrawDetailFirstGridOnly (5) : tests transformés pour valider
  data.grids[] (1 grille = 5 boules + 1 secondary, sans union triviale)
- TestCalendarMonthFirstGridOnly (1) : best_match_count = MAX par jour
"""

import datetime
import os
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.testclient import TestClient

_TEST_TOKEN = "test_admin_token_v136a_xxx"

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
# Detail tirage — 1ère grille canonique uniquement
# ════════════════════════════════════════════════════════════════════


class TestDrawDetailFirstGridOnly:

    def test_filters_first_canonical_only(self):
        """V137 — Detail retourne data.grids[] avec chaque grille à 5+1 numéros
        (pas d'union triviale de toutes les grilles)."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 28)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)  # FDJ pré-tirage
        # V137 : 1 grille (gid=g1) avec 6 rows
        cursor.fetchall = AsyncMock(return_value=[
            {"grid_id": "g1", "source": "generator", "number_value": 10, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 19, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 23, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 31, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 46, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 9, "number_type": "chance", "first_seen": "2026-04-27 08:00:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        # V137 : data.grids[] avec 1 grille
        assert data["summary"]["total_grids"] == 1
        gen = data["grids"][0]
        # ASSERT CRITIQUE : 5 boules SEULEMENT (1 grille), pas l'union triviale
        assert len(gen["balls"]) == 5
        assert gen["balls"] == [10, 19, 23, 31, 46]
        assert gen["secondary"] == 9

    def test_groups_within_same_second(self):
        """V137 — Tous les numéros d'une grille (même grid_id) sont retournés
        ensemble dans data.grids[0].balls."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 28)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)  # FDJ pré-tirage
        # V137 : 1 grille (gid=g1) — tous les numéros groupés sous le même grid_id
        cursor.fetchall = AsyncMock(return_value=[
            {"grid_id": "g1", "source": "generator", "number_value": 5, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 11, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 22, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 33, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 49, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 4, "number_type": "chance", "first_seen": "2026-04-27 08:00:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total_grids"] == 1
        gen = data["grids"][0]
        assert len(gen["balls"]) == 5
        assert gen["secondary"] == 4

    def test_excludes_later_grids_via_sql_filter(self):
        """V137 — Multi-grilles : le SQL detail ne filtre PLUS par INTERVAL
        1 SECOND (cette logique a été déplacée dans V110 brake uniquement, cf.
        TestV110BrakeRegression dans test_v137_multi_grids.py).
        Le detail récupère TOUTES les grilles via GROUP BY grid_id côté Python.
        Ce test vérifie que 2 grilles distinctes (g1, g2) sont retournées
        séparément dans data.grids[]."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 28)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)  # FDJ pré-tirage
        cursor.fetchall = AsyncMock(return_value=[
            # g1 (1ère grille)
            {"grid_id": "g1", "source": "generator", "number_value": 1, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 2, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 3, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 4, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 5, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 1, "number_type": "chance", "first_seen": "2026-04-27 08:00:00"},
            # g2 (grille later — V137 la conserve désormais, V136.A l'ignorait)
            {"grid_id": "g2", "source": "generator", "number_value": 10, "number_type": "ball", "first_seen": "2026-04-27 08:00:01"},
            {"grid_id": "g2", "source": "generator", "number_value": 20, "number_type": "ball", "first_seen": "2026-04-27 08:00:01"},
            {"grid_id": "g2", "source": "generator", "number_value": 30, "number_type": "ball", "first_seen": "2026-04-27 08:00:01"},
            {"grid_id": "g2", "source": "generator", "number_value": 40, "number_type": "ball", "first_seen": "2026-04-27 08:00:01"},
            {"grid_id": "g2", "source": "generator", "number_value": 49, "number_type": "ball", "first_seen": "2026-04-27 08:00:01"},
            {"grid_id": "g2", "source": "generator", "number_value": 9, "number_type": "chance", "first_seen": "2026-04-27 08:00:01"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        # V137 : 2 grilles distinctes retournées (au lieu de 1 seule en V136.A)
        assert data["summary"]["total_grids"] == 2
        gids = sorted([g["grid_id"] for g in data["grids"]])
        assert gids == ["g1", "g2"]

    def test_pdf_meta_unchanged_when_generator_present(self):
        """V137 — Generator + 2 pdf_meta_* : 3 grilles distinctes dans data.grids[]."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 28)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value={  # FDJ post-tirage
            "date_de_tirage": target_date,
            "boule_1": 5, "boule_2": 18, "boule_3": 22, "boule_4": 31, "boule_5": 49,
            "numero_chance": 3,
        })
        cursor.fetchall = AsyncMock(return_value=[
            # generator (gid=g1) : 1 grille (1 match : 22)
            {"grid_id": "g1", "source": "generator", "number_value": 7, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 22, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 27, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 33, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 41, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"grid_id": "g1", "source": "generator", "number_value": 8, "number_type": "chance", "first_seen": "2026-04-27 08:00:00"},
            # pdf_meta_global (gid=p1) : 4 matches (5, 18, 31, +chance 3)
            {"grid_id": "p1", "source": "pdf_meta_global", "number_value": 5, "number_type": "ball", "first_seen": "2026-04-27 09:00:00"},
            {"grid_id": "p1", "source": "pdf_meta_global", "number_value": 18, "number_type": "ball", "first_seen": "2026-04-27 09:00:00"},
            {"grid_id": "p1", "source": "pdf_meta_global", "number_value": 22, "number_type": "ball", "first_seen": "2026-04-27 09:00:00"},
            {"grid_id": "p1", "source": "pdf_meta_global", "number_value": 31, "number_type": "ball", "first_seen": "2026-04-27 09:00:00"},
            {"grid_id": "p1", "source": "pdf_meta_global", "number_value": 44, "number_type": "ball", "first_seen": "2026-04-27 09:00:00"},
            {"grid_id": "p1", "source": "pdf_meta_global", "number_value": 3, "number_type": "chance", "first_seen": "2026-04-27 09:00:00"},
            # pdf_meta_5a (gid=p2) : 1 match (49)
            {"grid_id": "p2", "source": "pdf_meta_5a", "number_value": 10, "number_type": "ball", "first_seen": "2026-04-27 09:01:00"},
            {"grid_id": "p2", "source": "pdf_meta_5a", "number_value": 15, "number_type": "ball", "first_seen": "2026-04-27 09:01:00"},
            {"grid_id": "p2", "source": "pdf_meta_5a", "number_value": 28, "number_type": "ball", "first_seen": "2026-04-27 09:01:00"},
            {"grid_id": "p2", "source": "pdf_meta_5a", "number_value": 40, "number_type": "ball", "first_seen": "2026-04-27 09:01:00"},
            {"grid_id": "p2", "source": "pdf_meta_5a", "number_value": 49, "number_type": "ball", "first_seen": "2026-04-27 09:01:00"},
            {"grid_id": "p2", "source": "pdf_meta_5a", "number_value": 7, "number_type": "chance", "first_seen": "2026-04-27 09:01:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        # V137 : 3 grilles distinctes
        assert data["summary"]["total_grids"] == 3
        gen = next(g for g in data["grids"] if g["grid_id"] == "g1")
        pdf_g = next(g for g in data["grids"] if g["grid_id"] == "p1")
        pdf_5a = next(g for g in data["grids"] if g["grid_id"] == "p2")
        assert gen["matches_balls"] == 1
        assert pdf_g["matches_balls"] == 4
        assert len(pdf_5a["balls"]) == 5
        # V137 : best_match_grid_id pointe pdf_meta_global (4 matches)
        assert data["summary"]["best_match_grid_id"] == "p1"
        assert data["summary"]["best_match_count"] == 4

    def test_no_generator_only_pdf_meta(self):
        """V137 — Aucune grille generator → seules les grilles pdf_meta_* dans data.grids[]."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 30)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)  # FDJ pré-tirage
        cursor.fetchall = AsyncMock(return_value=[
            {"grid_id": "p1", "source": "pdf_meta_global", "number_value": 7, "number_type": "ball", "first_seen": "2026-04-29 11:00:00"},
            {"grid_id": "p1", "source": "pdf_meta_global", "number_value": 18, "number_type": "ball", "first_seen": "2026-04-29 11:00:00"},
            {"grid_id": "p1", "source": "pdf_meta_global", "number_value": 22, "number_type": "ball", "first_seen": "2026-04-29 11:00:00"},
            {"grid_id": "p1", "source": "pdf_meta_global", "number_value": 33, "number_type": "ball", "first_seen": "2026-04-29 11:00:00"},
            {"grid_id": "p1", "source": "pdf_meta_global", "number_value": 41, "number_type": "ball", "first_seen": "2026-04-29 11:00:00"},
            {"grid_id": "p1", "source": "pdf_meta_global", "number_value": 9, "number_type": "chance", "first_seen": "2026-04-29 11:00:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        # V137 : 1 seule grille pdf_meta, pas de generator
        assert data["summary"]["total_grids"] == 1
        assert all(g["source"] != "generator" for g in data["grids"])
        pdf_g = data["grids"][0]
        assert pdf_g["source"] == "pdf_meta_global"
        assert len(pdf_g["balls"]) == 5


# ════════════════════════════════════════════════════════════════════
# Calendar month — 1ère grille canonique uniquement
# ════════════════════════════════════════════════════════════════════


class TestCalendarMonthFirstGridOnly:

    def test_calendar_month_best_match_uses_first_grid(self):
        """V137 — best_match_count = MAX(matches) parmi toutes les grilles du jour.

        V137 : SQL month = 1 query history (rows avec grid_id) + 1 FDJ rows.
        Donc 2 fetchall (au lieu de 3 V136.A).
        """
        client = _authed_client()
        target_date = datetime.date(2026, 4, 6)  # Lundi tirage Loto
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchall = AsyncMock(side_effect=[
            # 1) FDJ : tirage 2026-04-06 — balls {3,12,30,36,42}, chance 7
            [{
                "date_de_tirage": target_date,
                "boule_1": 3, "boule_2": 12, "boule_3": 30, "boule_4": 36, "boule_5": 42,
                "numero_chance": 7,
            }],
            # 2) V137 history : rows avec grid_id (1 grille = 1 match loyal sur 3)
            [
                {"draw_date_target": target_date, "grid_id": "g1", "source": "generator", "number_value": 3, "number_type": "ball", "first_seen": "2026-04-05 14:00:00"},
                {"draw_date_target": target_date, "grid_id": "g1", "source": "generator", "number_value": 25, "number_type": "ball", "first_seen": "2026-04-05 14:00:00"},
                {"draw_date_target": target_date, "grid_id": "g1", "source": "generator", "number_value": 33, "number_type": "ball", "first_seen": "2026-04-05 14:00:00"},
                {"draw_date_target": target_date, "grid_id": "g1", "source": "generator", "number_value": 41, "number_type": "ball", "first_seen": "2026-04-05 14:00:00"},
                {"draw_date_target": target_date, "grid_id": "g1", "source": "generator", "number_value": 47, "number_type": "ball", "first_seen": "2026-04-05 14:00:00"},
                {"draw_date_target": target_date, "grid_id": "g1", "source": "generator", "number_value": 9, "number_type": "chance", "first_seen": "2026-04-05 14:00:00"},
            ],
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get("/admin/api/calendar-perf/loto/2026/4")
        assert resp.status_code == 200
        data = resp.json()
        target = next(d for d in data["draws"] if d["date"] == "2026-04-06")
        assert target["fdj_drawn"] is True
        # V137 : month n'expose plus stats par source, juste best_match_count + total_grids
        assert target["total_grids"] == 1
        assert target["best_match_count"] == 1  # match loyal (3 seulement)
