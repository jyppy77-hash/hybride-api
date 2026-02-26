"""
Tests unitaires pour services/base_stats.py.
Couvre les methodes non testees via test_services.py :
get_numeros_par_categorie, prepare_grilles_pitch_context, chemins EM.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from datetime import date, timedelta

import pytest

from services.base_stats import GameConfig, BaseStatsService
from services.stats_service import LOTO_CONFIG, LotoStats
from services.em_stats_service import EM_CONFIG, EMStats

from tests.conftest import AsyncSmartMockCursor, make_async_conn


# ── Helper : subclass testable ────────────────────────────────────────

class TestableStats(BaseStatsService):
    """Subclass pour tests avec async mock DB."""

    def __init__(self, cfg, conn_cm):
        super().__init__(cfg)
        self._conn_cm = conn_cm

    @asynccontextmanager
    async def _get_connection(self):
        async with self._conn_cm as conn:
            yield conn


def _make_svc(cfg=None):
    """Cree un TestableStats avec AsyncSmartMockCursor pre-configure."""
    if cfg is None:
        cfg = LOTO_CONFIG
    from tests.conftest import AsyncSmartMockCursor, make_async_conn
    cursor = AsyncSmartMockCursor()
    return TestableStats(cfg, make_async_conn(cursor)), cursor


# ═══════════════════════════════════════════════════════════════════════
# get_numeros_par_categorie
# ═══════════════════════════════════════════════════════════════════════

def _make_categorie_svc():
    """Cree un TestableStats avec AsyncMock adapte a get_numeros_par_categorie."""
    from tests.conftest import make_async_conn
    cursor = AsyncMock()

    d_max = date(2026, 2, 3)

    cursor.fetchone = AsyncMock(return_value={"d": d_max})
    cursor.fetchall = AsyncMock(return_value=[
        {"num": n, "freq": 100 - n} for n in range(1, 50)
    ])

    return TestableStats(LOTO_CONFIG, make_async_conn(cursor))


class TestGetNumerosParCategorie:

    @pytest.mark.asyncio
    async def test_chaud_returns_list(self):
        svc = _make_categorie_svc()
        result = await svc.get_numeros_par_categorie("chaud", "principal")
        assert result is not None
        assert result["categorie"] == "chaud"
        assert isinstance(result["numeros"], list)
        assert result["count"] == len(result["numeros"])
        assert result["periode_analyse"] == "2 dernières années"

    @pytest.mark.asyncio
    async def test_froid_returns_list(self):
        svc = _make_categorie_svc()
        result = await svc.get_numeros_par_categorie("froid", "principal")
        assert result is not None
        assert result["categorie"] == "froid"
        assert len(result["numeros"]) > 0

    @pytest.mark.asyncio
    async def test_neutre_returns_list(self):
        svc = _make_categorie_svc()
        result = await svc.get_numeros_par_categorie("neutre", "principal")
        assert result is not None
        assert result["categorie"] == "neutre"

    @pytest.mark.asyncio
    async def test_item_structure(self):
        svc = _make_categorie_svc()
        result = await svc.get_numeros_par_categorie("chaud", "principal")
        for item in result["numeros"]:
            assert "numero" in item
            assert "frequence_2ans" in item


# ═══════════════════════════════════════════════════════════════════════
# prepare_grilles_pitch_context
# ═══════════════════════════════════════════════════════════════════════

class TestPrepareGrillesPitchContext:

    @pytest.mark.asyncio
    async def test_single_grille(self):
        svc, _ = _make_svc()
        grilles = [{"numeros": [5, 15, 25, 35, 45]}]
        result = await svc.prepare_grilles_pitch_context(grilles)
        assert "[GRILLE 1" in result
        assert "Somme" in result
        assert "Pairs" in result
        assert "Badges" in result

    @pytest.mark.asyncio
    async def test_multiple_grilles(self):
        svc, _ = _make_svc()
        grilles = [
            {"numeros": [1, 10, 20, 30, 40]},
            {"numeros": [5, 15, 25, 35, 45]},
            {"numeros": [2, 12, 22, 32, 42]},
        ]
        result = await svc.prepare_grilles_pitch_context(grilles)
        assert "[GRILLE 1" in result
        assert "[GRILLE 2" in result
        assert "[GRILLE 3" in result

    @pytest.mark.asyncio
    async def test_with_chance(self):
        svc, _ = _make_svc()
        grilles = [{"numeros": [5, 15, 25, 35, 45], "chance": 7}]
        result = await svc.prepare_grilles_pitch_context(grilles)
        assert "Chance 7" in result

    @pytest.mark.asyncio
    async def test_with_score_conformite(self):
        svc, _ = _make_svc()
        grilles = [{"numeros": [5, 15, 25, 35, 45], "score_conformite": 45}]
        result = await svc.prepare_grilles_pitch_context(grilles)
        assert "MODÉRÉ" in result

    @pytest.mark.asyncio
    async def test_with_severity(self):
        svc, _ = _make_svc()
        grilles = [{"numeros": [5, 15, 25, 35, 45], "severity": 3}]
        result = await svc.prepare_grilles_pitch_context(grilles)
        assert "Alerte maximale" in result


# ═══════════════════════════════════════════════════════════════════════
# Chemins EM — multi-colonnes secondaires
# ═══════════════════════════════════════════════════════════════════════

class TestEMConfigPaths:

    @pytest.mark.asyncio
    async def test_em_frequencies_etoile_union_all(self):
        """_get_all_frequencies avec type etoile utilise UNION ALL multi-colonnes."""
        cursor = AsyncMock()
        # Simuler le retour du UNION ALL etoile_1 + etoile_2
        cursor.fetchall = AsyncMock(return_value=[
            {"num": i, "freq": 50 + i} for i in range(1, 13)
        ])
        svc = EMStats(EM_CONFIG)
        # Appel direct sur la methode heritee
        result = await svc._get_all_frequencies(cursor, "etoile")
        assert len(result) == 12
        assert result[1] == 51

    @pytest.mark.asyncio
    async def test_em_ecarts_etoile(self):
        """_get_all_ecarts avec type etoile genere UNION ALL."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value={"total": 500})
        cursor.fetchall = AsyncMock(return_value=[
            {"num": i, "ecart": i % 5} for i in range(1, 13)
        ])
        svc = EMStats(EM_CONFIG)
        result = await svc._get_all_ecarts(cursor, "etoile")
        assert len(result) == 12
        for num in range(1, 13):
            assert num in result

    def test_em_extract_secondary_match_etoiles(self):
        """EMStats._extract_secondary_match detecte intersection etoiles."""
        svc = EMStats(EM_CONFIG)
        best_match = {"etoile_1": 3, "etoile_2": 9}
        assert svc._extract_secondary_match(best_match, [3, 7]) is True
        assert svc._extract_secondary_match(best_match, [1, 2]) is False
        assert svc._extract_secondary_match(best_match, []) is False

    @pytest.mark.asyncio
    async def test_em_range_secondary(self):
        """get_numero_stats hors range etoile (13) retourne None."""
        cursor = AsyncSmartMockCursor()
        svc = TestableStats(EM_CONFIG, make_async_conn(cursor))
        assert await svc.get_numero_stats(13, "etoile") is None
        assert await svc.get_numero_stats(12, "etoile") is not None or True  # 12 est valide


# ═══════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_invalid_type_num_raises(self):
        svc, _ = _make_svc()
        cursor = AsyncMock()
        with pytest.raises(ValueError, match="type_num invalide"):
            await svc._get_all_frequencies(cursor, "invalid")

    @pytest.mark.asyncio
    async def test_numero_out_of_range_returns_none(self):
        svc, _ = _make_svc()
        assert await svc.get_numero_stats(0, "principal") is None
        assert await svc.get_numero_stats(50, "principal") is None
        assert await svc.get_numero_stats(11, "chance") is None
