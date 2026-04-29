"""V136.A — Hotfix tests : 1ère grille canonique generator uniquement.

V136 affichait l'union de toutes les grilles canoniques générées par tous les
visiteurs au cours de la journée (42 boules EM cumulées sur 50 = 4 boules
matchées triviales). V136.A filtre côté generator au timestamp MIN(selected_at)
à la seconde près pour ne récupérer que les 5+1 numéros de la 1ère grille.

Tests :
- TestDrawDetailFirstGridOnly (5) : detail tirage filtre 1ère grille
- TestCalendarMonthFirstGridOnly (1) : best_match_count loyal sur 1ère grille
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
        """V136.A — Detail retourne uniquement les 5+1 numéros de la 1ère grille
        canonique du jour-cible, pas l'union de toutes les grilles générées
        par tous les visiteurs."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 28)
        first_ts = datetime.datetime(2026, 4, 27, 8, 0, 0)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        # 3 fetchone : FDJ row → first_ts row → (rien, fetchall pour les rows)
        cursor.fetchone = AsyncMock(side_effect=[
            None,  # FDJ : pré-tirage (pas encore drawn) — assez pour ne pas calc matchs
            {"first_ts": first_ts},  # query 1 V136.A : MIN selected_at
        ])
        # query 2 V136.A : SEULEMENT les 6 rows de la 1ère grille filtrée par SQL
        # (le SQL avec INTERVAL 1 SECOND a déjà fait son boulot de filtre)
        cursor.fetchall = AsyncMock(return_value=[
            {"source": "generator", "number_value": 10, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 19, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 23, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 31, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 46, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 9, "number_type": "chance", "first_seen": "2026-04-27 08:00:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        gen = data["hybride"]["generator"]
        assert gen is not None
        # ASSERT CRITIQUE : 5 boules SEULEMENT (1 grille), pas 15 ou plus (3 grilles unioniées)
        assert len(gen["balls"]) == 5
        assert gen["balls"] == [10, 19, 23, 31, 46]
        assert gen["secondary"] == 9

    def test_groups_within_same_second(self):
        """V136.A — DATETIME précision seconde : tous les numéros enregistrés
        dans la même seconde (timestamps ms variants) sont récupérés ensemble."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 28)
        first_ts = datetime.datetime(2026, 4, 27, 8, 0, 0)  # arrondi à la seconde
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(side_effect=[
            None,  # FDJ pré-tirage
            {"first_ts": first_ts},
        ])
        # MariaDB DATETIME(0) : tous les inserts dans la seconde 08:00:00 ont
        # le même first_seen "2026-04-27 08:00:00" (pas de fraction stockée)
        cursor.fetchall = AsyncMock(return_value=[
            {"source": "generator", "number_value": 5, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 11, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 22, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 33, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 49, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 4, "number_type": "chance", "first_seen": "2026-04-27 08:00:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        gen = data["hybride"]["generator"]
        assert len(gen["balls"]) == 5
        assert gen["secondary"] == 4

    def test_excludes_later_grids_via_sql_filter(self):
        """V136.A — Le SQL contient le filtre INTERVAL 1 SECOND qui exclut les
        rows enregistrées après la 1ère seconde. Test du SQL généré."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 28)
        first_ts = datetime.datetime(2026, 4, 27, 8, 0, 0)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(side_effect=[None, {"first_ts": first_ts}])
        cursor.fetchall = AsyncMock(return_value=[])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        # Vérifier qu'au moins un execute a contenu INTERVAL 1 SECOND
        executed_sql = " ".join(
            (call.args[0] if call.args else "") for call in cursor.execute.await_args_list
        )
        assert "INTERVAL 1 SECOND" in executed_sql, (
            f"V136.A : le SQL doit contenir INTERVAL 1 SECOND pour filtrer la 1ère grille. SQL = {executed_sql}"
        )
        # Vérifier que first_ts a été utilisé comme paramètre
        any_uses_first_ts = any(
            len(call.args) > 1 and first_ts in call.args[1]
            for call in cursor.execute.await_args_list
        )
        assert any_uses_first_ts, "V136.A : first_ts doit être passé en paramètre SQL"

    def test_pdf_meta_unchanged_when_generator_present(self):
        """V136.A — pdf_meta_* sources : agrégat top fréquences V136 inchangé.
        Les rows pdf_meta_* sont retournées intégralement à côté de la 1ère
        grille generator filtrée."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 28)
        first_ts = datetime.datetime(2026, 4, 27, 8, 0, 0)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(side_effect=[
            {  # FDJ post-tirage
                "date_de_tirage": target_date,
                "boule_1": 5, "boule_2": 18, "boule_3": 22, "boule_4": 31, "boule_5": 49,
                "numero_chance": 3,
            },
            {"first_ts": first_ts},
        ])
        cursor.fetchall = AsyncMock(return_value=[
            # generator : 1 grille canonique (1 match avec FDJ : 22)
            {"source": "generator", "number_value": 7, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 22, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 27, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 33, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 41, "number_type": "ball", "first_seen": "2026-04-27 08:00:00"},
            {"source": "generator", "number_value": 8, "number_type": "chance", "first_seen": "2026-04-27 08:00:00"},
            # pdf_meta_global : top 5 fréquences (5,18,22,31,44 = 4 matches !)
            {"source": "pdf_meta_global", "number_value": 5, "number_type": "ball", "first_seen": "2026-04-27 09:00:00"},
            {"source": "pdf_meta_global", "number_value": 18, "number_type": "ball", "first_seen": "2026-04-27 09:00:00"},
            {"source": "pdf_meta_global", "number_value": 22, "number_type": "ball", "first_seen": "2026-04-27 09:00:00"},
            {"source": "pdf_meta_global", "number_value": 31, "number_type": "ball", "first_seen": "2026-04-27 09:00:00"},
            {"source": "pdf_meta_global", "number_value": 44, "number_type": "ball", "first_seen": "2026-04-27 09:00:00"},
            {"source": "pdf_meta_global", "number_value": 3, "number_type": "chance", "first_seen": "2026-04-27 09:00:00"},
            # pdf_meta_5a : top 5 différents (10,15,28,40,49 = 2 matches: 28? non / 49 oui)
            {"source": "pdf_meta_5a", "number_value": 10, "number_type": "ball", "first_seen": "2026-04-27 09:01:00"},
            {"source": "pdf_meta_5a", "number_value": 15, "number_type": "ball", "first_seen": "2026-04-27 09:01:00"},
            {"source": "pdf_meta_5a", "number_value": 28, "number_type": "ball", "first_seen": "2026-04-27 09:01:00"},
            {"source": "pdf_meta_5a", "number_value": 40, "number_type": "ball", "first_seen": "2026-04-27 09:01:00"},
            {"source": "pdf_meta_5a", "number_value": 49, "number_type": "ball", "first_seen": "2026-04-27 09:01:00"},
            {"source": "pdf_meta_5a", "number_value": 7, "number_type": "chance", "first_seen": "2026-04-27 09:01:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        # generator : 5 boules + 1 chance, 1 match (22)
        gen = data["hybride"]["generator"]
        assert len(gen["balls"]) == 5
        assert gen["matches_balls"] == 1
        # pdf_meta_global : 5 boules retournées intégralement (V136 OK), 4 matches
        pdf_g = data["hybride"]["pdf_meta_global"]
        assert pdf_g is not None
        assert len(pdf_g["balls"]) == 5
        assert pdf_g["matches_balls"] == 4
        # pdf_meta_5a : présent
        pdf_5a = data["hybride"]["pdf_meta_5a"]
        assert pdf_5a is not None
        assert len(pdf_5a["balls"]) == 5
        # Best match = pdf_meta_global avec 4 boules
        assert data["summary"]["best_match_source"] == "pdf_meta_global"
        assert data["summary"]["best_match_count"] == 4

    def test_no_generator_only_pdf_meta(self):
        """V136.A — Si aucune grille generator pour ce jour, le SQL "else
        branch" (pdf_meta_* uniquement) est exécuté et generator = None."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 30)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(side_effect=[
            None,  # FDJ : pré-tirage
            {"first_ts": None},  # MIN(selected_at) generator → None (aucune grille)
        ])
        cursor.fetchall = AsyncMock(return_value=[
            {"source": "pdf_meta_global", "number_value": 7, "number_type": "ball", "first_seen": "2026-04-29 11:00:00"},
            {"source": "pdf_meta_global", "number_value": 18, "number_type": "ball", "first_seen": "2026-04-29 11:00:00"},
            {"source": "pdf_meta_global", "number_value": 22, "number_type": "ball", "first_seen": "2026-04-29 11:00:00"},
            {"source": "pdf_meta_global", "number_value": 33, "number_type": "ball", "first_seen": "2026-04-29 11:00:00"},
            {"source": "pdf_meta_global", "number_value": 41, "number_type": "ball", "first_seen": "2026-04-29 11:00:00"},
            {"source": "pdf_meta_global", "number_value": 9, "number_type": "chance", "first_seen": "2026-04-29 11:00:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hybride"]["generator"] is None
        assert data["hybride"]["pdf_meta_global"] is not None
        assert len(data["hybride"]["pdf_meta_global"]["balls"]) == 5


# ════════════════════════════════════════════════════════════════════
# Calendar month — 1ère grille canonique uniquement
# ════════════════════════════════════════════════════════════════════


class TestCalendarMonthFirstGridOnly:

    def test_calendar_month_best_match_uses_first_grid(self):
        """V136.A — best_match_count est calculé sur la 1ère grille uniquement,
        pas sur l'union de toutes les grilles du jour. Avec 1 vraie grille =
        1 match loyal, on évite le 4 matches triviaux d'agrégat."""
        client = _authed_client()
        target_date = datetime.date(2026, 4, 6)  # Lundi tirage Loto
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        # 3 fetchall successifs : (1) FDJ rows, (2) generator filtré, (3) pdf_meta_*
        cursor.fetchall = AsyncMock(side_effect=[
            # 1) FDJ : tirage 2026-04-06 — balls {3,12,30,36,42}, chance 7
            [{
                "date_de_tirage": target_date,
                "boule_1": 3, "boule_2": 12, "boule_3": 30, "boule_4": 36, "boule_5": 42,
                "numero_chance": 7,
            }],
            # 2) generator filtré (subquery JOIN MIN selected_at) : 1 grille = 5+1 boules
            # 1 match seulement (3) — loyal
            [
                {"draw_date_target": target_date, "source": "generator", "number_value": 3, "number_type": "ball"},
                {"draw_date_target": target_date, "source": "generator", "number_value": 25, "number_type": "ball"},
                {"draw_date_target": target_date, "source": "generator", "number_value": 33, "number_type": "ball"},
                {"draw_date_target": target_date, "source": "generator", "number_value": 41, "number_type": "ball"},
                {"draw_date_target": target_date, "source": "generator", "number_value": 47, "number_type": "ball"},
                {"draw_date_target": target_date, "source": "generator", "number_value": 9, "number_type": "chance"},
            ],
            # 3) pdf_meta_* : aucun pour ce mois-ci dans le test
            [],
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
        gen = target["stats"]["generator"]
        assert gen is not None
        assert len(gen["balls"]) == 5  # 1 grille pure, pas l'union de plusieurs
        assert gen["matches_balls"] == 1  # match loyal (3 seulement)
        assert target["best_match_count"] == 1
        # Vérifier que le SQL generator contient bien la subquery JOIN INTERVAL 1 SECOND
        executed_sql = " ".join(
            (call.args[0] if call.args else "") for call in cursor.execute.await_args_list
        )
        assert "INTERVAL 1 SECOND" in executed_sql
        assert "MIN(selected_at)" in executed_sql
