"""
Tests pour la feature "Corrélations de Triplets" (combinaisons de 3 numéros).
Couvre :
- get_triplet_correlations() dans base_stats
- Endpoint /api/{game}/stats/triplets
- Détecteurs regex _detect_triplets (6 langues)
- Formatage contexte chatbot
"""

import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from services.base_stats import GameConfig, BaseStatsService
from services.stats_service import LOTO_CONFIG, LotoStats
from services.em_stats_service import EM_CONFIG, EMStats
from services.chat_detectors import _detect_triplets
from services.chat_detectors_em import _detect_triplets_em
from services.chat_utils import _format_triplets_context
from services.chat_utils_em import _format_triplets_context_em

from tests.conftest import make_async_conn


# ── Helper : subclass testable ──────────────────────────────────────

class TestableStats(BaseStatsService):
    def __init__(self, cfg, conn_cm):
        super().__init__(cfg)
        self._conn_cm = conn_cm

    @asynccontextmanager
    async def _get_connection(self):
        async with self._conn_cm as conn:
            yield conn


def _make_triplets_cursor_no_window(triplet_rows, total=200):
    """Cursor pour get_triplet_correlations sans window (global)."""
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value={"total": total})
    cursor.fetchall = AsyncMock(return_value=triplet_rows)
    cursor.execute = AsyncMock()
    return cursor


def _make_triplets_cursor(triplet_rows, total=200, date_max=date(2026, 2, 3)):
    """Cursor pre-configure pour get_triplet_correlations avec window."""
    cursor = AsyncMock()
    call_count = {"n": 0}

    async def mock_fetchone():
        call_count["n"] += 1
        n = call_count["n"]
        if n == 1:
            return {"d": date_max}
        if n == 2:
            return {"total": total}
        return {"total": total}

    cursor.fetchone = mock_fetchone
    cursor.fetchall = AsyncMock(return_value=triplet_rows)
    cursor.execute = AsyncMock()
    return cursor


# ═══════════════════════════════════════════════════════════════════════
# get_triplet_correlations — structure retour
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_triplet_correlations_structure():
    """get_triplet_correlations retourne la bonne structure."""
    triplet_rows = [
        {"num_a": 5, "num_b": 12, "num_c": 34, "triplet_count": 8},
        {"num_a": 7, "num_b": 23, "num_c": 45, "triplet_count": 6},
    ]
    cursor = _make_triplets_cursor_no_window(triplet_rows, total=200)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result = await svc.get_triplet_correlations(top_n=10)
    assert result is not None
    assert "triplets" in result
    assert "total_draws" in result
    assert result["total_draws"] == 200
    assert len(result["triplets"]) == 2
    assert result["triplets"][0]["num_a"] == 5
    assert result["triplets"][0]["num_b"] == 12
    assert result["triplets"][0]["num_c"] == 34
    assert result["triplets"][0]["count"] == 8
    assert result["triplets"][0]["rank"] == 1
    assert "percentage" in result["triplets"][0]


@pytest.mark.asyncio
async def test_triplet_correlations_top_n():
    """get_triplet_correlations respecte top_n."""
    triplet_rows = [
        {"num_a": 1, "num_b": 2, "num_c": 3, "triplet_count": 10},
        {"num_a": 4, "num_b": 5, "num_c": 6, "triplet_count": 8},
        {"num_a": 7, "num_b": 8, "num_c": 9, "triplet_count": 6},
    ]
    cursor = _make_triplets_cursor_no_window(triplet_rows, total=200)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result = await svc.get_triplet_correlations(top_n=3)
    assert result is not None
    assert len(result["triplets"]) == 3
    assert result["triplets"][2]["rank"] == 3


@pytest.mark.asyncio
async def test_triplet_correlations_window():
    """get_triplet_correlations avec window filtre par date."""
    triplet_rows = [{"num_a": 10, "num_b": 20, "num_c": 30, "triplet_count": 3}]
    cursor = _make_triplets_cursor(triplet_rows, total=100)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result = await svc.get_triplet_correlations(top_n=5, window="5A")
    assert result is not None
    assert result["window"] == "5A"
    assert result["total_draws"] == 100


@pytest.mark.asyncio
async def test_triplet_correlations_percentage():
    """get_triplet_correlations calcule le pourcentage correctement."""
    triplet_rows = [{"num_a": 5, "num_b": 12, "num_c": 34, "triplet_count": 50}]
    cursor = _make_triplets_cursor_no_window(triplet_rows, total=1000)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result = await svc.get_triplet_correlations(top_n=1)
    assert result["triplets"][0]["percentage"] == 5.0


@pytest.mark.asyncio
async def test_triplet_correlations_empty():
    """get_triplet_correlations avec 0 tirages retourne liste vide."""
    cursor = _make_triplets_cursor_no_window([], total=0)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result = await svc.get_triplet_correlations(top_n=10)
    assert result is not None
    assert result["triplets"] == []
    assert result["total_draws"] == 0


@pytest.mark.asyncio
async def test_triplet_correlations_cache():
    """get_triplet_correlations utilise le cache au 2e appel."""
    triplet_rows = [{"num_a": 5, "num_b": 12, "num_c": 34, "triplet_count": 8}]
    cursor = _make_triplets_cursor_no_window(triplet_rows, total=200)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result1 = await svc.get_triplet_correlations(top_n=10)
    assert result1 is not None

    cursor.execute.reset_mock()
    result2 = await svc.get_triplet_correlations(top_n=10)
    assert result2 == result1
    cursor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_triplet_correlations_em():
    """get_triplet_correlations fonctionne pour EM."""
    triplet_rows = [
        {"num_a": 3, "num_b": 15, "num_c": 42, "triplet_count": 5},
    ]
    cursor = _make_triplets_cursor_no_window(triplet_rows, total=500)
    svc = TestableStats(EM_CONFIG, make_async_conn(cursor))

    result = await svc.get_triplet_correlations(top_n=5)
    assert result is not None
    assert len(result["triplets"]) == 1
    assert result["triplets"][0]["num_c"] == 42


# ═══════════════════════════════════════════════════════════════════════
# _detect_triplets — regex 6 langues
# ═══════════════════════════════════════════════════════════════════════

def test_detect_triplets_fr():
    assert _detect_triplets("quels triplets sortent le plus souvent ?")
    assert _detect_triplets("les trios les plus fréquents")
    assert _detect_triplets("combinaison de 3 numéros")
    assert _detect_triplets("3 numéros ensemble les plus fréquents")
    assert _detect_triplets("quels trois numéros sortent ensemble")
    assert _detect_triplets("groupement de 3 boules")


def test_detect_triplets_en():
    assert _detect_triplets("which triplets appear most often?")
    assert _detect_triplets("combination of 3 numbers")
    assert _detect_triplets("3 numbers together most frequent")
    assert _detect_triplets("group of 3 numbers")
    assert _detect_triplets("three numbers that come together")


def test_detect_triplets_es():
    assert _detect_triplets("qué tripletes salen más ?")
    assert _detect_triplets("trío de números más frecuente")
    assert _detect_triplets("combinación de 3 números")
    assert _detect_triplets("3 números juntos")
    assert _detect_triplets("tres números que salen juntos")


def test_detect_triplets_pt():
    assert _detect_triplets("quais tripletos saem mais ?")
    assert _detect_triplets("trio de números mais frequente")
    assert _detect_triplets("combinação de 3 números")
    assert _detect_triplets("3 números juntos")
    assert _detect_triplets("três números que saem juntos")


def test_detect_triplets_de():
    assert _detect_triplets("welche Tripletts kommen am häufigsten vor?")
    assert _detect_triplets("Dreiergruppe der häufigsten Zahlen")
    assert _detect_triplets("Kombination von 3 Zahlen")
    assert _detect_triplets("3 Zahlen zusammen")
    assert _detect_triplets("drei Zahlen die zusammen kommen")


def test_detect_triplets_nl():
    assert _detect_triplets("welke drietallen komen het vaakst voor?")
    assert _detect_triplets("combinatie van 3 nummers")
    assert _detect_triplets("3 nummers samen")
    assert _detect_triplets("drie nummers die samen voorkomen")


def test_detect_triplets_negative():
    """Messages qui ne doivent PAS déclencher la détection triplets."""
    assert not _detect_triplets("quel numéro sort le plus ?")
    assert not _detect_triplets("quelles paires sortent ensemble ?")
    assert not _detect_triplets("donne moi le classement")
    assert not _detect_triplets("bonjour comment ça va")
    assert not _detect_triplets("analyse ma grille 5 12 23 34 45")


def test_detect_triplets_em():
    """_detect_triplets_em reutilise le meme regex."""
    assert _detect_triplets_em("quels triplets de boules sortent le plus ?")
    assert _detect_triplets_em("combination of 3 numbers")
    assert not _detect_triplets_em("quel numéro sort le plus ?")


# ═══════════════════════════════════════════════════════════════════════
# _format_triplets_context / _format_triplets_context_em
# ═══════════════════════════════════════════════════════════════════════

def test_format_triplets_context():
    data = {
        "triplets": [
            {"num_a": 5, "num_b": 12, "num_c": 34, "count": 8, "percentage": 4.0, "rank": 1},
            {"num_a": 7, "num_b": 23, "num_c": 45, "count": 6, "percentage": 3.0, "rank": 2},
        ],
        "total_draws": 200,
        "window": None,
    }
    result = _format_triplets_context(data)
    assert "CORRÉLATIONS DE TRIPLETS" in result
    assert "5 + 12 + 34" in result
    assert "8 fois" in result
    assert "4.0%" in result
    assert "hasard" in result.lower()
    assert "200" in result


def test_format_triplets_context_with_window():
    data = {
        "triplets": [{"num_a": 1, "num_b": 2, "num_c": 3, "count": 5, "percentage": 2.5, "rank": 1}],
        "total_draws": 200,
        "window": "5A",
    }
    result = _format_triplets_context(data)
    assert "5A" in result


def test_format_triplets_context_em():
    data = {
        "triplets": [
            {"num_a": 3, "num_b": 15, "num_c": 42, "count": 5, "percentage": 1.0, "rank": 1},
        ],
        "total_draws": 500,
        "window": None,
    }
    result = _format_triplets_context_em(data)
    assert "Boules EuroMillions" in result
    assert "3 + 15 + 42" in result
    assert "hasard" in result.lower()


# ═══════════════════════════════════════════════════════════════════════
# Endpoint /api/{game}/stats/triplets
# ═══════════════════════════════════════════════════════════════════════

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})


def _mock_triplet_correlations(top_n=10, window=None):
    """Retourne un resultat mocke pour get_triplet_correlations."""
    return {
        "triplets": [
            {"num_a": 5, "num_b": 12, "num_c": 34, "count": 8, "percentage": 4.0, "rank": 1},
        ],
        "total_draws": 200,
        "window": window,
    }


def test_endpoint_triplets_loto():
    with _db_env, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)

        with patch("services.stats_service.get_triplet_correlations",
                   new=AsyncMock(return_value=_mock_triplet_correlations())):
            resp = client.get("/api/loto/stats/triplets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["game"] == "loto"
    assert len(data["triplets"]) == 1
    assert data["triplets"][0]["num_a"] == 5
    assert data["triplets"][0]["num_c"] == 34


def test_endpoint_triplets_em():
    with _db_env, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)

        with patch("services.em_stats_service.get_triplet_correlations",
                   new=AsyncMock(return_value=_mock_triplet_correlations())):
            resp = client.get("/api/euromillions/stats/triplets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["game"] == "euromillions"
    assert len(data["triplets"]) == 1


def test_endpoint_triplets_top_n():
    with _db_env, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)

        mock_fn = AsyncMock(return_value=_mock_triplet_correlations(top_n=3))
        with patch("services.stats_service.get_triplet_correlations", new=mock_fn):
            resp = client.get("/api/loto/stats/triplets?top_n=3")
    assert resp.status_code == 200
    mock_fn.assert_called_once_with(top_n=3, window=None)


def test_endpoint_triplets_window():
    with _db_env, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)

        mock_fn = AsyncMock(return_value=_mock_triplet_correlations(window="5A"))
        with patch("services.stats_service.get_triplet_correlations", new=mock_fn):
            resp = client.get("/api/loto/stats/triplets?window=5A")
    assert resp.status_code == 200
    mock_fn.assert_called_once_with(top_n=10, window="5A")
