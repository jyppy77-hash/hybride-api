"""
Tests pour les routes unifiees /api/{game}/... (Phase 10).
Verifie que les nouvelles URLs /api/loto/... et /api/euromillions/...
repondent correctement et que les validations fonctionnent.
"""

import os
from contextlib import asynccontextmanager
from unittest.mock import patch, AsyncMock
from datetime import date

import pytest
from fastapi.testclient import TestClient


def _async_cm_conn(cursor):
    @asynccontextmanager
    async def _cm():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn
    return _cm


_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})


def _get_patched_client_and_modules():
    """Create a TestClient with patches, return (client, main_mod)."""
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        return client, main_mod


# ═══════════════════════════════════════════════
# Invalid game → 422
# ═══════════════════════════════════════════════

def test_invalid_game_422():
    """GET /api/poker/tirages/count → 422 (FastAPI enum validation)."""
    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/poker/tirages/count")
    assert resp.status_code == 422


# ═══════════════════════════════════════════════
# Unified Data — /api/loto/...
# ═══════════════════════════════════════════════

@patch("routes.api_data_unified.db_cloudsql")
def test_unified_loto_tirages_count(mock_db):
    """GET /api/loto/tirages/count returns count."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchone.return_value = {"total": 967}

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        import routes.api_data_unified as mod
        mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/loto/tirages/count")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 967


@patch("routes.api_data_unified.db_cloudsql")
def test_unified_loto_tirages_latest(mock_db):
    """GET /api/loto/tirages/latest returns a tirage."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchone.return_value = {
        "date_de_tirage": date(2026, 2, 3),
        "boule_1": 5, "boule_2": 12, "boule_3": 23,
        "boule_4": 34, "boule_5": 45, "numero_chance": 7,
    }

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        import routes.api_data_unified as mod
        mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/loto/tirages/latest")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "boule_1" in data["data"]


@patch("routes.api_data_unified.db_cloudsql")
def test_unified_loto_tirages_list(mock_db):
    """GET /api/loto/tirages/list returns items."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchall.return_value = [
        {"date_de_tirage": date(2026, 2, 3), "boule_1": 5, "boule_2": 12,
         "boule_3": 23, "boule_4": 34, "boule_5": 45, "numero_chance": 7},
    ]

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        import routes.api_data_unified as mod
        mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/loto/tirages/list?limit=5")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "items" in data["data"]


@patch("routes.api_data_unified.db_cloudsql")
def test_unified_loto_database_info(mock_db):
    """GET /api/loto/database-info returns draws info."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchone.return_value = {
        "total": 967,
        "date_min": date(2008, 3, 6),
        "date_max": date(2026, 2, 3),
    }

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        import routes.api_data_unified as mod
        mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/loto/database-info")

    assert resp.status_code == 200
    data = resp.json()
    assert "total_draws" in data
    assert data["total_draws"] == 967


@patch("routes.api_data_unified.db_cloudsql")
def test_unified_loto_stats_number(mock_db):
    """GET /api/loto/stats/number/7 returns stats."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchall.return_value = [
        {"date_de_tirage": date(2020, 3, 14)},
        {"date_de_tirage": date(2024, 11, 2)},
    ]
    cursor.fetchone.return_value = {"gap": 5}

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        import routes.api_data_unified as mod
        mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/loto/stats/number/7")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["number"] == 7


@patch("routes.api_data_unified.db_cloudsql")
def test_unified_loto_stats_number_out_of_range(mock_db):
    """GET /api/loto/stats/number/99 → 400."""
    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/loto/stats/number/99")

    assert resp.status_code == 400


# ═══════════════════════════════════════════════
# Unified Data — /api/euromillions/...
# ═══════════════════════════════════════════════

@patch("routes.api_data_unified.db_cloudsql")
def test_unified_em_tirages_count(mock_db):
    """GET /api/euromillions/tirages/count returns count."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchone.return_value = {"total": 500}

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        importlib.reload(main_mod)
        import routes.api_data_unified as mod
        mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/euromillions/tirages/count")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 500


@patch("routes.api_data_unified.db_cloudsql")
def test_unified_em_stats_number(mock_db):
    """GET /api/euromillions/stats/number/42 returns stats with type=boule."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchall.return_value = [
        {"date_de_tirage": date(2021, 5, 10)},
    ]
    cursor.fetchone.return_value = {"gap": 3}

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        importlib.reload(main_mod)
        import routes.api_data_unified as mod
        mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/euromillions/stats/number/42")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["type"] == "boule"


# ═══════════════════════════════════════════════
# Stats Etoile — EM only, Loto 404
# ═══════════════════════════════════════════════

def test_stats_etoile_loto_404():
    """GET /api/loto/stats/etoile/5 → 404 (Loto n'a pas d'etoiles)."""
    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/loto/stats/etoile/5")

    assert resp.status_code == 404


@patch("routes.api_data_unified.db_cloudsql")
def test_stats_etoile_em_ok(mock_db):
    """GET /api/euromillions/stats/etoile/5 → 200."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchall.return_value = [
        {"date_de_tirage": date(2022, 1, 15)},
    ]
    cursor.fetchone.return_value = {"gap": 2}

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        importlib.reload(main_mod)
        import routes.api_data_unified as mod
        mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/euromillions/stats/etoile/5")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["type"] == "etoile"


def test_stats_etoile_em_invalid():
    """GET /api/euromillions/stats/etoile/99 → 400."""
    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/euromillions/stats/etoile/99")

    assert resp.status_code == 400


# ═══════════════════════════════════════════════
# Backward compat — legacy URLs still work
# ═══════════════════════════════════════════════

@patch("routes.api_data_unified.db_cloudsql")
def test_legacy_loto_tirages_count(mock_db):
    """GET /api/tirages/count still works (backward compat)."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchone.return_value = {"total": 967}

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        import routes.api_data_unified as mod
        mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/tirages/count")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


@patch("routes.api_data_unified.db_cloudsql")
def test_legacy_em_tirages_count(mock_db):
    """GET /api/euromillions/tirages/count still works (backward compat)."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchone.return_value = {"total": 500}

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        importlib.reload(main_mod)
        import routes.api_data_unified as mod
        mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/euromillions/tirages/count")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


# ═══════════════════════════════════════════════
# GameConfig registry
# ═══════════════════════════════════════════════

def test_game_config_loto():
    """GameConfig for loto has correct values."""
    from config.games import ValidGame, get_config
    cfg = get_config(ValidGame.loto)
    assert cfg.slug == "loto"
    assert cfg.table == "tirages"
    assert cfg.num_range == (1, 49)
    assert cfg.secondary_count == 1


def test_game_config_em():
    """GameConfig for euromillions has correct values."""
    from config.games import ValidGame, get_config
    cfg = get_config(ValidGame.euromillions)
    assert cfg.slug == "euromillions"
    assert cfg.table == "tirages_euromillions"
    assert cfg.num_range == (1, 50)
    assert cfg.secondary_count == 2


def test_valid_game_enum():
    """ValidGame enum has exactly loto and euromillions."""
    from config.games import ValidGame
    assert set(ValidGame) == {ValidGame.loto, ValidGame.euromillions}
