"""
Tests pour la feature "Corrélations de Paires".
Couvre :
- get_pair_correlations() et get_star_pair_correlations() dans base_stats
- Endpoint /api/{game}/stats/pairs
- Détecteurs regex _detect_paires (6 langues)
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
from services.chat_detectors import _detect_paires
from services.chat_detectors_em import _detect_paires_em
from services.chat_utils import _format_pairs_context
from services.chat_utils_em import _format_pairs_context_em, _format_star_pairs_context_em

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


def _make_pairs_cursor(pair_rows, total=200, date_max=date(2026, 2, 3)):
    """Cree un AsyncMock cursor pre-configure pour get_pair_correlations."""
    cursor = AsyncMock()
    call_count = {"n": 0}

    async def mock_fetchone():
        call_count["n"] += 1
        n = call_count["n"]
        if n == 1:
            # MAX(date_de_tirage) — window branch
            return {"d": date_max}
        if n == 2:
            # COUNT
            return {"total": total}
        # fallback for non-window path
        return {"total": total}

    cursor.fetchone = mock_fetchone
    cursor.fetchall = AsyncMock(return_value=pair_rows)
    cursor.execute = AsyncMock()
    return cursor


def _make_pairs_cursor_no_window(pair_rows, total=200):
    """Cursor pour get_pair_correlations sans window (global)."""
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value={"total": total})
    cursor.fetchall = AsyncMock(return_value=pair_rows)
    cursor.execute = AsyncMock()
    return cursor


# ═══════════════════════════════════════════════════════════════════════
# get_pair_correlations — structure retour
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pair_correlations_structure():
    """get_pair_correlations retourne la bonne structure."""
    pair_rows = [
        {"num_a": 7, "num_b": 23, "pair_count": 42},
        {"num_a": 15, "num_b": 34, "pair_count": 38},
    ]
    cursor = _make_pairs_cursor_no_window(pair_rows, total=200)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result = await svc.get_pair_correlations(top_n=10)
    assert result is not None
    assert "pairs" in result
    assert "total_draws" in result
    assert result["total_draws"] == 200
    assert len(result["pairs"]) == 2
    assert result["pairs"][0]["num_a"] == 7
    assert result["pairs"][0]["num_b"] == 23
    assert result["pairs"][0]["count"] == 42
    assert result["pairs"][0]["rank"] == 1
    assert "percentage" in result["pairs"][0]


@pytest.mark.asyncio
async def test_pair_correlations_top_n():
    """get_pair_correlations respecte top_n."""
    pair_rows = [
        {"num_a": 1, "num_b": 2, "pair_count": 50},
        {"num_a": 3, "num_b": 4, "pair_count": 40},
        {"num_a": 5, "num_b": 6, "pair_count": 30},
    ]
    cursor = _make_pairs_cursor_no_window(pair_rows, total=200)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result = await svc.get_pair_correlations(top_n=3)
    assert result is not None
    assert len(result["pairs"]) == 3
    assert result["pairs"][2]["rank"] == 3


@pytest.mark.asyncio
async def test_pair_correlations_window():
    """get_pair_correlations avec window filtre par date."""
    pair_rows = [{"num_a": 10, "num_b": 20, "pair_count": 15}]
    cursor = _make_pairs_cursor(pair_rows, total=100)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result = await svc.get_pair_correlations(top_n=5, window="5A")
    assert result is not None
    assert result["window"] == "5A"
    assert result["total_draws"] == 100


@pytest.mark.asyncio
async def test_pair_correlations_cache():
    """get_pair_correlations utilise le cache au 2e appel."""
    pair_rows = [{"num_a": 7, "num_b": 23, "pair_count": 42}]
    cursor = _make_pairs_cursor_no_window(pair_rows, total=200)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result1 = await svc.get_pair_correlations(top_n=10)
    assert result1 is not None

    # 2e appel : cursor.execute ne devrait plus etre appele
    cursor.execute.reset_mock()
    result2 = await svc.get_pair_correlations(top_n=10)
    assert result2 == result1
    cursor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_pair_correlations_percentage():
    """get_pair_correlations calcule le pourcentage correctement."""
    pair_rows = [{"num_a": 7, "num_b": 23, "pair_count": 50}]
    cursor = _make_pairs_cursor_no_window(pair_rows, total=1000)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result = await svc.get_pair_correlations(top_n=1)
    assert result["pairs"][0]["percentage"] == 5.0


@pytest.mark.asyncio
async def test_pair_correlations_empty():
    """get_pair_correlations avec 0 tirages retourne liste vide."""
    cursor = _make_pairs_cursor_no_window([], total=0)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result = await svc.get_pair_correlations(top_n=10)
    assert result is not None
    assert result["pairs"] == []
    assert result["total_draws"] == 0


# ═══════════════════════════════════════════════════════════════════════
# get_star_pair_correlations
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_star_pair_correlations_em():
    """get_star_pair_correlations fonctionne pour EM."""
    pair_rows = [
        {"num_a": 2, "num_b": 8, "pair_count": 30},
        {"num_a": 3, "num_b": 11, "pair_count": 25},
    ]
    cursor = _make_pairs_cursor_no_window(pair_rows, total=500)
    svc = TestableStats(EM_CONFIG, make_async_conn(cursor))

    result = await svc.get_star_pair_correlations(top_n=5)
    assert result is not None
    assert len(result["pairs"]) == 2
    assert result["pairs"][0]["num_a"] == 2
    assert result["pairs"][0]["num_b"] == 8


@pytest.mark.asyncio
async def test_star_pair_correlations_loto_returns_none():
    """get_star_pair_correlations retourne None pour Loto (1 colonne secondaire)."""
    cursor = _make_pairs_cursor_no_window([], total=200)
    svc = TestableStats(LOTO_CONFIG, make_async_conn(cursor))

    result = await svc.get_star_pair_correlations(top_n=5)
    assert result is None


# ═══════════════════════════════════════════════════════════════════════
# _detect_paires — regex 6 langues
# ═══════════════════════════════════════════════════════════════════════

def test_detect_paires_fr():
    assert _detect_paires("quelles paires sortent ensemble ?")
    assert _detect_paires("les duos les plus fréquents")
    assert _detect_paires("numéros associés entre eux")
    assert _detect_paires("corrélation entre les numéros")


def test_detect_paires_en():
    assert _detect_paires("which pairs come together most often?")
    assert _detect_paires("numbers linked to each other")
    assert _detect_paires("co-occurrence of numbers")
    assert _detect_paires("correlation between numbers")


def test_detect_paires_es():
    assert _detect_paires("qué parejas salen juntos ?")
    assert _detect_paires("combinación más frecuente")


def test_detect_paires_pt():
    assert _detect_paires("quais duplas saem juntos ?")
    assert _detect_paires("combinação mais frequente")


def test_detect_paires_de():
    assert _detect_paires("welche Paare kommen zusammen vor?")
    assert _detect_paires("Kombination häufig")


def test_detect_paires_nl():
    assert _detect_paires("welke nummers komen samen voor?")
    assert _detect_paires("combinatie frequent")


def test_detect_paires_natural_fr():
    """Formulations naturelles FR."""
    assert _detect_paires("quel numéro sort le plus souvent avec le 15")
    assert _detect_paires("quels numéros accompagnent le 7")
    assert _detect_paires("le 15 sort avec quoi")
    assert _detect_paires("quels numéros vont avec le 23")
    assert _detect_paires("il sort à côté du 15 souvent ?")


def test_detect_paires_natural_en():
    assert _detect_paires("which number comes with 15")
    assert _detect_paires("what goes with 15")
    assert _detect_paires("numbers alongside 15")
    assert _detect_paires("appears next to 7")


def test_detect_paires_natural_es():
    assert _detect_paires("qué número sale con el 15")
    assert _detect_paires("junto con el 15")
    assert _detect_paires("qué número acompaña al 7")


def test_detect_paires_natural_pt():
    assert _detect_paires("que número sai com o 15")
    assert _detect_paires("junto com o 15")
    assert _detect_paires("que número acompanha o 7")


def test_detect_paires_natural_de():
    assert _detect_paires("welche Zahl kommt mit der 15")
    assert _detect_paires("zusammen mit der 15")
    assert _detect_paires("neben der 15")
    assert _detect_paires("begleitet die 15")


def test_detect_paires_natural_nl():
    assert _detect_paires("welk nummer komt met 15")
    assert _detect_paires("samen met de 15")
    assert _detect_paires("naast de 15")
    assert _detect_paires("begeleidt de 15")


def test_detect_paires_even_odd_exclusion_fr():
    """Messages pairs/impairs (even/odd) ne doivent PAS declencher Phase P."""
    assert not _detect_paires("numéros pairs et impairs")
    assert not _detect_paires("analyse pairs impairs sur 200 tirages")
    assert not _detect_paires("répartition pair/impair")
    assert not _detect_paires("tendance des nombres pairs et impairs sur 100 tirages")


def test_detect_paires_even_odd_exclusion_multilang():
    """Even/odd exclusion fonctionne en 6 langues."""
    assert not _detect_paires("even and odd numbers over 200 draws")
    assert not _detect_paires("números pares e impares en los últimos 200 sorteos")
    assert not _detect_paires("números pares e ímpares nos últimos 200 sorteios")
    assert not _detect_paires("gerade und ungerade Zahlen der letzten 200 Ziehungen")
    assert not _detect_paires("even en oneven nummers over de laatste 200 trekkingen")


def test_detect_paires_legitimate_still_works():
    """Phase P legitimate messages still trigger after even/odd guard."""
    assert _detect_paires("quelles paires sortent ensemble")
    assert _detect_paires("numéros qui sortent en paires")
    assert _detect_paires("which pairs come together most often")
    assert _detect_paires("welke Paare kommen zusammen vor")
    assert _detect_paires("corrélation entre les numéros")


def test_detect_paires_em_even_odd_exclusion():
    """EM _detect_paires_em inherits the even/odd exclusion."""
    assert not _detect_paires_em("numéros pairs et impairs sur 200 tirages")
    assert _detect_paires_em("quelles paires de boules sortent ensemble ?")


def test_detect_paires_negative():
    """Messages qui ne doivent PAS declencher la detection paires."""
    assert not _detect_paires("quel numéro sort le plus ?")
    assert not _detect_paires("sort le plus souvent")
    assert not _detect_paires("avec combien de chance")
    assert not _detect_paires("donne moi le classement")
    assert not _detect_paires("analyse ma grille 5 12 23 34 45")
    assert not _detect_paires("bonjour comment ça va")


def test_detect_paires_em():
    """_detect_paires_em reutilise le meme regex."""
    assert _detect_paires_em("quelles paires de boules sortent ensemble ?")
    assert _detect_paires_em("quel numéro sort avec le 15 ?")
    assert not _detect_paires_em("quel numéro sort le plus ?")


# ═══════════════════════════════════════════════════════════════════════
# _format_pairs_context / _format_pairs_context_em
# ═══════════════════════════════════════════════════════════════════════

def test_format_pairs_context():
    data = {
        "pairs": [
            {"num_a": 7, "num_b": 23, "count": 42, "percentage": 4.3, "rank": 1},
            {"num_a": 15, "num_b": 34, "count": 38, "percentage": 3.9, "rank": 2},
        ],
        "total_draws": 990,
        "window": None,
    }
    result = _format_pairs_context(data)
    assert "CORRÉLATIONS DE PAIRES" in result
    assert "7 + 23" in result
    assert "42 fois" in result
    assert "4.3%" in result
    assert "hasard" in result.lower()
    assert "990" in result


def test_format_pairs_context_with_window():
    data = {
        "pairs": [{"num_a": 1, "num_b": 2, "count": 10, "percentage": 5.0, "rank": 1}],
        "total_draws": 200,
        "window": "5A",
    }
    result = _format_pairs_context(data)
    assert "5A" in result


def test_format_pairs_context_em():
    data = {
        "pairs": [
            {"num_a": 7, "num_b": 23, "count": 30, "percentage": 4.1, "rank": 1},
        ],
        "total_draws": 733,
        "window": None,
    }
    result = _format_pairs_context_em(data)
    assert "Boules EuroMillions" in result
    assert "7 + 23" in result
    assert "hasard" in result.lower()


def test_format_star_pairs_context_em():
    data = {
        "pairs": [
            {"num_a": 2, "num_b": 8, "count": 30, "percentage": 4.1, "rank": 1},
            {"num_a": 3, "num_b": 11, "count": 25, "percentage": 3.4, "rank": 2},
        ],
        "total_draws": 733,
        "window": None,
    }
    result = _format_star_pairs_context_em(data)
    assert "Étoiles" in result
    assert "⭐2" in result or "\u2b502" in result
    assert "30 fois" in result


# ═══════════════════════════════════════════════════════════════════════
# Endpoint /api/{game}/stats/pairs
# ═══════════════════════════════════════════════════════════════════════

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})


def _mock_pair_correlations(top_n=10, window=None):
    """Retourne un resultat mocke pour get_pair_correlations."""
    return {
        "pairs": [
            {"num_a": 7, "num_b": 23, "count": 42, "percentage": 4.3, "rank": 1},
        ],
        "total_draws": 990,
        "window": window,
    }


def _mock_star_pair_correlations(top_n=10, window=None):
    return {
        "pairs": [
            {"num_a": 2, "num_b": 8, "count": 30, "percentage": 4.1, "rank": 1},
        ],
        "total_draws": 733,
        "window": window,
    }


def test_endpoint_pairs_loto():
    with _db_env, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)

        with patch("services.stats_service.get_pair_correlations",
                   new=AsyncMock(return_value=_mock_pair_correlations())):
            resp = client.get("/api/loto/stats/pairs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["game"] == "loto"
    assert len(data["pairs"]) == 1
    assert data["pairs"][0]["num_a"] == 7


def test_endpoint_pairs_em():
    with _db_env, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)

        with patch("services.em_stats_service.get_pair_correlations",
                   new=AsyncMock(return_value=_mock_pair_correlations())), \
             patch("services.em_stats_service.get_star_pair_correlations",
                   new=AsyncMock(return_value=_mock_star_pair_correlations())):
            resp = client.get("/api/euromillions/stats/pairs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["game"] == "euromillions"
    assert "star_pairs" in data
    assert data["star_pairs"][0]["num_a"] == 2


def test_endpoint_pairs_top_n():
    with _db_env, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)

        mock_fn = AsyncMock(return_value=_mock_pair_correlations(top_n=3))
        with patch("services.stats_service.get_pair_correlations", new=mock_fn):
            resp = client.get("/api/loto/stats/pairs?top_n=3")
    assert resp.status_code == 200
    mock_fn.assert_called_once_with(top_n=3, window=None, order="hot")


def test_endpoint_pairs_window():
    with _db_env, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)

        mock_fn = AsyncMock(return_value=_mock_pair_correlations(window="5A"))
        with patch("services.stats_service.get_pair_correlations", new=mock_fn):
            resp = client.get("/api/loto/stats/pairs?window=5A")
    assert resp.status_code == 200
    mock_fn.assert_called_once_with(top_n=10, window="5A", order="hot")
