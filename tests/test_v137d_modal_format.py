"""V137.D — Tests modal /admin/calendar-perf : 3 bugs UX corrigés.

Bug 1 (frontend admin.js) : header "Date / Heure" + format DD/MM HH:MM
  → testé manuellement via smoke test (rendu JS non mockable raisonnablement)

Bug 2 (backend tri chronologique pur) : retrait priorité generator
  → TestModalChronologicalSort

Bug 3 (backend secondary_balls liste) : EM 2 stars affichées (avant : 1 seule)
  → TestModalSecondaryBallsBackend (2 tests symétrie Loto/EM)
  → TestModalCalcMatchSecondaryEm (calc match avec liste secondaires)

Pattern tests : TestClient + mock cursor (réutilise pattern test_v137_multi_grids.py).
"""

import datetime
import os
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.testclient import TestClient

from routes.admin_perf_calendar import _calc_match


_TEST_TOKEN = "test_admin_token_v137d_xxx"

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
    """Build a mock conn usable via async with db.get_connection_readonly() as conn."""
    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cursor)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ════════════════════════════════════════════════════════════════════════
# TestModalSecondaryBallsBackend (2 tests — Bug 3 backend symétrie Loto/EM)
# ════════════════════════════════════════════════════════════════════════


class TestModalSecondaryBallsBackend:

    def test_em_returns_secondary_balls_list_two_stars(self):
        """V137.D Bug 3 : EM grille avec 2 stars [6, 11] → secondary_balls=[6, 11].

        AVANT V137.D : seul star_1=6 stocké dans `secondary` scalaire,
        star_2=11 silencieusement ignoré → modal affichait `Sec: 6` au lieu
        de `Sec: 6 - 11`. La correction backend remonte secondary_balls
        (liste) ET secondary (scalaire = 1er, rétrocompat).
        """
        client = _authed_client()
        target_date = datetime.date(2026, 5, 1)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)  # tirage à venir
        cursor.fetchall = AsyncMock(return_value=[
            # Grille EM avec 2 stars
            {"grid_id": "em-grid-1", "source": "generator", "number_value": 7, "number_type": "ball", "first_seen": "2026-04-30 06:16:00"},
            {"grid_id": "em-grid-1", "source": "generator", "number_value": 16, "number_type": "ball", "first_seen": "2026-04-30 06:16:00"},
            {"grid_id": "em-grid-1", "source": "generator", "number_value": 28, "number_type": "ball", "first_seen": "2026-04-30 06:16:00"},
            {"grid_id": "em-grid-1", "source": "generator", "number_value": 34, "number_type": "ball", "first_seen": "2026-04-30 06:16:00"},
            {"grid_id": "em-grid-1", "source": "generator", "number_value": 45, "number_type": "ball", "first_seen": "2026-04-30 06:16:00"},
            {"grid_id": "em-grid-1", "source": "generator", "number_value": 6, "number_type": "star", "first_seen": "2026-04-30 06:16:00"},
            {"grid_id": "em-grid-1", "source": "generator", "number_value": 11, "number_type": "star", "first_seen": "2026-04-30 06:16:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/euromillions/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["grids"]) == 1
        g = data["grids"][0]
        # V137.D : secondary_balls liste avec 2 stars triées
        assert g["secondary_balls"] == [6, 11], (
            f"V137.D Bug 3 : EM doit remonter [6, 11], got {g.get('secondary_balls')}"
        )
        # Rétrocompat : secondary scalaire = 1er star
        assert g["secondary"] == 6
        assert g["balls"] == [7, 16, 28, 34, 45]

    def test_loto_returns_secondary_balls_list_one_chance(self):
        """V137.D symétrie Loto : 1 chance → secondary_balls=[chance] (1 élément)."""
        client = _authed_client()
        target_date = datetime.date(2026, 5, 2)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[
            {"grid_id": "loto-grid-1", "source": "generator", "number_value": 4, "number_type": "ball", "first_seen": "2026-05-01 10:00:00"},
            {"grid_id": "loto-grid-1", "source": "generator", "number_value": 12, "number_type": "ball", "first_seen": "2026-05-01 10:00:00"},
            {"grid_id": "loto-grid-1", "source": "generator", "number_value": 23, "number_type": "ball", "first_seen": "2026-05-01 10:00:00"},
            {"grid_id": "loto-grid-1", "source": "generator", "number_value": 35, "number_type": "ball", "first_seen": "2026-05-01 10:00:00"},
            {"grid_id": "loto-grid-1", "source": "generator", "number_value": 47, "number_type": "ball", "first_seen": "2026-05-01 10:00:00"},
            {"grid_id": "loto-grid-1", "source": "generator", "number_value": 7, "number_type": "chance", "first_seen": "2026-05-01 10:00:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["grids"]) == 1
        g = data["grids"][0]
        # V137.D : Loto liste 1 élément
        assert g["secondary_balls"] == [7], (
            f"V137.D : Loto secondary_balls doit être [7], got {g.get('secondary_balls')}"
        )
        assert g["secondary"] == 7  # rétrocompat


# ════════════════════════════════════════════════════════════════════════
# TestModalChronologicalSort (1 test — Bug 2 tri chronologique pur)
# ════════════════════════════════════════════════════════════════════════


class TestModalChronologicalSort:

    def test_grids_sorted_purely_by_first_seen_ascending(self):
        """V137.D Bug 2 : tri chronologique pur (ASC), retrait priorité generator.

        Avant V137.D : sort key (source != 'generator', first_seen, grid_id)
        plaçait les `generator` AVANT tous les `pdf_meta_*`, indépendamment des
        timestamps. Si pdf_meta inséré à 06:16 et generator à 06:30, l'ordre
        était [generator 06:30, pdf_meta 06:16] = anti-chrono visible.

        V137.D : tri (first_seen, grid_id) → ordre purement chronologique.
        """
        client = _authed_client()
        target_date = datetime.date(2026, 5, 2)
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        # 3 grilles : pdf_meta (06:16) AVANT generator (06:30) AVANT generator (07:00)
        cursor.fetchall = AsyncMock(return_value=[
            # 1ère temporelle = pdf_meta_global
            {"grid_id": "pdf-grid-1", "source": "pdf_meta_global", "number_value": 5, "number_type": "ball", "first_seen": "2026-05-01 06:16:00"},
            {"grid_id": "pdf-grid-1", "source": "pdf_meta_global", "number_value": 11, "number_type": "ball", "first_seen": "2026-05-01 06:16:00"},
            {"grid_id": "pdf-grid-1", "source": "pdf_meta_global", "number_value": 22, "number_type": "ball", "first_seen": "2026-05-01 06:16:00"},
            {"grid_id": "pdf-grid-1", "source": "pdf_meta_global", "number_value": 33, "number_type": "ball", "first_seen": "2026-05-01 06:16:00"},
            {"grid_id": "pdf-grid-1", "source": "pdf_meta_global", "number_value": 44, "number_type": "ball", "first_seen": "2026-05-01 06:16:00"},
            {"grid_id": "pdf-grid-1", "source": "pdf_meta_global", "number_value": 1, "number_type": "chance", "first_seen": "2026-05-01 06:16:00"},
            # 2ème temporelle = generator (06:30)
            {"grid_id": "gen-grid-1", "source": "generator", "number_value": 6, "number_type": "ball", "first_seen": "2026-05-01 06:30:00"},
            {"grid_id": "gen-grid-1", "source": "generator", "number_value": 12, "number_type": "ball", "first_seen": "2026-05-01 06:30:00"},
            {"grid_id": "gen-grid-1", "source": "generator", "number_value": 23, "number_type": "ball", "first_seen": "2026-05-01 06:30:00"},
            {"grid_id": "gen-grid-1", "source": "generator", "number_value": 34, "number_type": "ball", "first_seen": "2026-05-01 06:30:00"},
            {"grid_id": "gen-grid-1", "source": "generator", "number_value": 45, "number_type": "ball", "first_seen": "2026-05-01 06:30:00"},
            {"grid_id": "gen-grid-1", "source": "generator", "number_value": 2, "number_type": "chance", "first_seen": "2026-05-01 06:30:00"},
            # 3ème temporelle = generator (07:00)
            {"grid_id": "gen-grid-2", "source": "generator", "number_value": 7, "number_type": "ball", "first_seen": "2026-05-01 07:00:00"},
            {"grid_id": "gen-grid-2", "source": "generator", "number_value": 13, "number_type": "ball", "first_seen": "2026-05-01 07:00:00"},
            {"grid_id": "gen-grid-2", "source": "generator", "number_value": 24, "number_type": "ball", "first_seen": "2026-05-01 07:00:00"},
            {"grid_id": "gen-grid-2", "source": "generator", "number_value": 35, "number_type": "ball", "first_seen": "2026-05-01 07:00:00"},
            {"grid_id": "gen-grid-2", "source": "generator", "number_value": 46, "number_type": "ball", "first_seen": "2026-05-01 07:00:00"},
            {"grid_id": "gen-grid-2", "source": "generator", "number_value": 3, "number_type": "chance", "first_seen": "2026-05-01 07:00:00"},
        ])
        with patch(
            "routes.admin_perf_calendar.db_cloudsql.get_connection_readonly",
            return_value=_make_async_conn(cursor),
        ):
            resp = client.get(f"/admin/api/calendar-perf/draw/loto/{target_date.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        grids = data["grids"]
        assert len(grids) == 3
        # V137.D : ordre chronologique pur (pdf_meta 06:16 → gen 06:30 → gen 07:00)
        assert grids[0]["grid_id"] == "pdf-grid-1", (
            f"V137.D Bug 2 : 1ère grille doit être pdf_meta (06:16), "
            f"got {grids[0]['grid_id']} (source={grids[0]['source']})"
        )
        assert grids[1]["grid_id"] == "gen-grid-1"
        assert grids[2]["grid_id"] == "gen-grid-2"


# ════════════════════════════════════════════════════════════════════════
# TestModalCalcMatchSecondaryEm (1 test — _calc_match avec liste secondaires)
# ════════════════════════════════════════════════════════════════════════


class TestModalCalcMatchSecondaryEm:

    def test_em_secondary_match_when_one_of_two_stars_matches(self):
        """V137.D Bug 3 corollaire : matches_secondary=True si AU MOINS 1 des
        N stars HYBRIDE est dans le tirage FDJ (avant V137.D : seul le 1er
        star testé → ~50% sous-évaluation EM).

        Cas EM : HYBRIDE secondary_balls=[6, 11], FDJ secondary={6, 9}.
        - Avant V137.D : `secondary=6` (scalaire) → match (par chance).
        - Mais si HYBRIDE=[11, 6] (ordre BDD différent), avant V137.D
          aurait stocké `secondary=11` → 11 ∉ {6, 9} → False.
        - V137.D : on teste les 2 → True dans tous les cas où ≥1 match.
        """
        # Cas 1 : HYBRIDE [6, 11], FDJ {6, 9} — match (6 commun)
        result = _calc_match(
            hybride_balls=[5, 18, 22, 31, 49],
            hybride_secondary=[6, 11],
            fdj_balls={5, 18, 22, 31, 49},
            fdj_secondary={6, 9},
        )
        assert result["matches_secondary"] is True
        assert result["matches_balls"] == 5

        # Cas 2 : HYBRIDE [11, 6] (ordre inverse), FDJ {6, 9} — match (6 commun)
        result2 = _calc_match(
            hybride_balls=[5, 18, 22, 31, 49],
            hybride_secondary=[11, 6],
            fdj_balls={5, 18, 22, 31, 49},
            fdj_secondary={6, 9},
        )
        assert result2["matches_secondary"] is True

        # Cas 3 : aucun match secondaire — HYBRIDE [11, 12], FDJ {6, 9}
        result3 = _calc_match(
            hybride_balls=[1, 2, 3, 4, 5],
            hybride_secondary=[11, 12],
            fdj_balls={1, 2, 3, 4, 5},
            fdj_secondary={6, 9},
        )
        assert result3["matches_secondary"] is False

        # Cas 4 : rétrocompat scalaire — HYBRIDE 6 (int), FDJ {6, 9} — match
        result4 = _calc_match(
            hybride_balls=[1, 2, 3, 4, 5],
            hybride_secondary=6,
            fdj_balls={1, 2, 3, 4, 5},
            fdj_secondary={6, 9},
        )
        assert result4["matches_secondary"] is True
