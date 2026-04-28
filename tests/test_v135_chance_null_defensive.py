"""V135 — Tests defensifs NULL transitoire numero_chance / etoile_1 / etoile_2.

Couvre l'hypothese F du diagnostic V2 (28/04/2026) :
pipeline d'import externe en 2 etapes peut laisser numero_chance / etoile_1 /
etoile_2 NULL temporairement entre INSERT et UPDATE.

3 surfaces de defense :
  1. routes/api_analyse_unified.py : SQL filtre NULL/range + log error si asymetrie
  2. engine/hybride_base.py        : guard NULL/range + log warning, skip ligne
  3. observabilite                 : preffix [META-CHANCE] / [META-STARS] / [HYBRIDE-SECONDARY]
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Helpers (pattern de tests/test_unified_routes.py) ────────────────────

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


def _build_chance_freq_rows(per_value: int = 101, total_target: int = 1014):
    """Build 10 rows summing to total_target (Loto chance).

    Default 9 rows × 101 + 1 row × 105 = 909 + 105 = 1014.
    Ajuste la dernière entrée pour atteindre la cible exacte.
    """
    rows = [{"num": i, "freq": per_value} for i in range(1, 10)]
    remaining = total_target - per_value * 9
    rows.append({"num": 10, "freq": remaining})
    return rows


def _build_em_stars_rows(per_value: int = 169, total_target: int = 2028):
    """Build 12 rows summing to total_target (EM stars).

    Default 11 × 169 + 1 × 169 = 2028 (cible = 2 × 1014 tirages).
    """
    rows = [{"num": i, "freq": per_value} for i in range(1, 12)]
    remaining = total_target - per_value * 11
    rows.append({"num": 12, "freq": remaining})
    return rows


# ═══════════════════════════════════════════════════════════════════════
# Test 1 — Loto Global : sum chance == len(window_ids) → AUCUN log error
# ═══════════════════════════════════════════════════════════════════════

@patch("routes.api_analyse_unified.get_persistent_brake_map", new=AsyncMock(return_value={}))
@patch("routes.api_analyse_unified.get_decay_state", new=AsyncMock(return_value={}))
@patch("routes.api_analyse_unified.check_and_update_decay", new=AsyncMock(return_value=None))
@patch("routes.api_analyse_unified.db_cloudsql")
def test_meta_analyse_local_loto_chance_consistency_no_log(mock_db):
    """Loto Global : tous numero_chance valides -> sum == 1014, pas de [META-CHANCE]."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchone.side_effect = [
        {"total": 1014},                                                     # COUNT(*)
        {"min_date": date(2019, 11, 6), "max_date": date(2026, 4, 27)},      # MIN/MAX dates
    ]
    cursor.fetchall.side_effect = [
        [{"id": i} for i in range(1, 1015)],                                 # window_ids (1014)
        [{"num": i, "freq": 100} for i in range(1, 50)],                     # boules
        [],                                                                   # recent_draws (LIMIT 4)
        _build_chance_freq_rows(per_value=101, total_target=1014),           # chance freq cohérent
    ]

    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        with patch("routes.api_analyse_unified.logger") as mock_logger:
            resp = client.get("/api/loto/meta-analyse-local?window=GLOBAL")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # AUCUN log [META-CHANCE] ne doit être émis quand symétrique
    error_calls = [
        c for c in mock_logger.error.call_args_list
        if c.args and "[META-CHANCE]" in c.args[0]
    ]
    assert len(error_calls) == 0, f"Expected NO [META-CHANCE] log, got {error_calls}"


# ═══════════════════════════════════════════════════════════════════════
# Test 2 — Loto Global : SQL renvoie sum=1013 (NULL filtré) → log error
# ═══════════════════════════════════════════════════════════════════════

@patch("routes.api_analyse_unified.get_persistent_brake_map", new=AsyncMock(return_value={}))
@patch("routes.api_analyse_unified.get_decay_state", new=AsyncMock(return_value={}))
@patch("routes.api_analyse_unified.check_and_update_decay", new=AsyncMock(return_value=None))
@patch("routes.api_analyse_unified.db_cloudsql")
def test_meta_analyse_local_loto_chance_asymetrie_logs_error(mock_db):
    """Loto Global : 1014 IDs mais SQL filtre 1 NULL -> sum=1013 -> [META-CHANCE] log."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchone.side_effect = [
        {"total": 1014},
        {"min_date": date(2019, 11, 6), "max_date": date(2026, 4, 27)},
    ]
    cursor.fetchall.side_effect = [
        [{"id": i} for i in range(1, 1015)],                  # 1014 window_ids
        [{"num": i, "freq": 100} for i in range(1, 50)],
        [],
        _build_chance_freq_rows(per_value=101, total_target=1013),  # NULL filtré → -1
    ]

    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        # V135: patch logger directement (caplog ne propage pas avec handler JSON custom)
        with patch("routes.api_analyse_unified.logger") as mock_logger:
            resp = client.get("/api/loto/meta-analyse-local?window=GLOBAL")

    assert resp.status_code == 200
    # Verifie que logger.error a ete appele avec le prefixe [META-CHANCE] et les bonnes valeurs
    error_calls = [
        c for c in mock_logger.error.call_args_list
        if c.args and "[META-CHANCE]" in c.args[0]
    ]
    assert len(error_calls) == 1, f"Expected 1 [META-CHANCE] log, got {len(error_calls)}: {mock_logger.error.call_args_list}"
    # Verifie les valeurs interpolées : args[1]=window_used, args[2]=total_chance, args[3]=len(window_ids)
    call_args = error_calls[0].args
    assert call_args[1] == "GLOBAL"
    assert call_args[2] == 1013
    assert call_args[3] == 1014


# ═══════════════════════════════════════════════════════════════════════
# Test 3 — EM Global : sum stars == 2 × len(window_ids) → AUCUN log error
# ═══════════════════════════════════════════════════════════════════════

@patch("routes.api_analyse_unified.get_persistent_brake_map", new=AsyncMock(return_value={}))
@patch("routes.api_analyse_unified.get_decay_state", new=AsyncMock(return_value={}))
@patch("routes.api_analyse_unified.check_and_update_decay", new=AsyncMock(return_value=None))
@patch("routes.api_analyse_unified.db_cloudsql")
def test_meta_analyse_local_em_stars_consistency_no_log(mock_db):
    """EM Global : tous etoile_1/etoile_2 valides -> sum == 2028, pas de [META-STARS]."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchone.side_effect = [
        {"total": 1014},
        {"min_date": date(2019, 11, 6), "max_date": date(2026, 4, 27)},
    ]
    cursor.fetchall.side_effect = [
        [{"id": i} for i in range(1, 1015)],
        [{"num": i, "freq": 100} for i in range(1, 51)],     # 50 boules EM
        [],
        _build_em_stars_rows(per_value=169, total_target=2028),
    ]

    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        with patch("routes.api_analyse_unified.logger") as mock_logger:
            resp = client.get("/api/euromillions/meta-analyse-local?window=GLOBAL")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    error_calls = [
        c for c in mock_logger.error.call_args_list
        if c.args and "[META-STARS]" in c.args[0]
    ]
    assert len(error_calls) == 0, f"Expected NO [META-STARS] log, got {error_calls}"


# ═══════════════════════════════════════════════════════════════════════
# Test 4 — EM Global : sum stars=2027 (1 NULL filtré) → log error EM
# ═══════════════════════════════════════════════════════════════════════

@patch("routes.api_analyse_unified.get_persistent_brake_map", new=AsyncMock(return_value={}))
@patch("routes.api_analyse_unified.get_decay_state", new=AsyncMock(return_value={}))
@patch("routes.api_analyse_unified.check_and_update_decay", new=AsyncMock(return_value=None))
@patch("routes.api_analyse_unified.db_cloudsql")
def test_meta_analyse_local_em_stars_asymetrie_logs_error(mock_db):
    """EM Global : 1 etoile NULL filtrée -> sum=2027 vs expected 2028 -> [META-STARS] log."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchone.side_effect = [
        {"total": 1014},
        {"min_date": date(2019, 11, 6), "max_date": date(2026, 4, 27)},
    ]
    cursor.fetchall.side_effect = [
        [{"id": i} for i in range(1, 1015)],
        [{"num": i, "freq": 100} for i in range(1, 51)],
        [],
        _build_em_stars_rows(per_value=169, total_target=2027),  # NULL filtré → -1
    ]

    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        with patch("routes.api_analyse_unified.logger") as mock_logger:
            resp = client.get("/api/euromillions/meta-analyse-local?window=GLOBAL")

    assert resp.status_code == 200
    error_calls = [
        c for c in mock_logger.error.call_args_list
        if c.args and "[META-STARS]" in c.args[0]
    ]
    assert len(error_calls) == 1, f"Expected 1 [META-STARS] log, got {len(error_calls)}"
    call_args = error_calls[0].args
    assert call_args[1] == "GLOBAL"
    assert call_args[2] == 2027
    assert call_args[3] == 2028


# ═══════════════════════════════════════════════════════════════════════
# Test 5 — engine.calculer_frequences_secondary skip None Loto
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_hybride_secondary_skips_null_loto(caplog):
    """LotoStats.calculer_frequences_secondary skip row[col]=None + log warning."""
    from engine.hybride_base import HybrideEngine
    from config.engine import LOTO_CONFIG

    engine = HybrideEngine(LOTO_CONFIG)
    cursor = AsyncMock()
    conn = AsyncMock()
    conn.cursor = AsyncMock(return_value=cursor)
    cursor.fetchall.return_value = [
        {"numero_chance": 1, "freq": 100},
        {"numero_chance": None, "freq": 1},   # ← NULL must be skipped
        {"numero_chance": 3, "freq": 95},
    ]
    cursor.fetchone.return_value = {"count": 196}

    with caplog.at_level(logging.WARNING, logger="engine.hybride_base"):
        result = await engine.calculer_frequences_secondary(conn, date_limite=None)

    assert None not in result
    # freq dict normalisé /count : 1 doit avoir 100/196, 3 doit avoir 95/196, autres 0
    assert result[1] > 0
    assert result[3] > 0
    assert "[HYBRIDE-SECONDARY]" in caplog.text
    assert "NULL" in caplog.text


# ═══════════════════════════════════════════════════════════════════════
# Test 6 — engine.calculer_frequences_secondary skip out-of-range EM (UNION)
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_hybride_secondary_skips_out_of_range_em(caplog):
    """EM (UNION ALL multi-col) skip etoile=99 hors range [1,12] + log warning."""
    from engine.hybride_base import HybrideEngine
    from config.engine import EM_CONFIG

    engine = HybrideEngine(EM_CONFIG)
    cursor = AsyncMock()
    conn = AsyncMock()
    conn.cursor = AsyncMock(return_value=cursor)
    cursor.fetchall.return_value = [
        {"num": 1, "freq": 100},
        {"num": 99, "freq": 1},   # ← out of range [1,12] doit être skipped
        {"num": 5, "freq": 80},
        {"num": None, "freq": 1}, # ← NULL UNION doit aussi être skipped
    ]
    cursor.fetchone.return_value = {"count": 181}

    with caplog.at_level(logging.WARNING, logger="engine.hybride_base"):
        result = await engine.calculer_frequences_secondary(conn, date_limite=None)

    assert 99 not in result
    assert None not in result
    assert result[1] > 0
    assert result[5] > 0
    assert "[HYBRIDE-SECONDARY]" in caplog.text
    assert "out of range" in caplog.text or "NULL" in caplog.text
