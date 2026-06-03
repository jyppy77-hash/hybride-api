"""Tests fix future-leak — injection optionnelle de `recent_draws` dans generate_grids.

Contrat additif behavior-preserving (option courte, validée Jyppy 2026-06-03) :
  - recent_draws OMIS (None)  → get_recent_draws(conn) EST appelé (comportement prod inchangé).
  - recent_draws FOURNI        → get_recent_draws N'EST PAS appelé ; la liste fournie est
                                 utilisée (hard-exclude T-1 appliqué sur les numéros injectés).
  - recent_draws=[] (idx=0 backtest) → get_recent_draws NON appelé (invariant : liste
                                 jamais None côté harness, [] = pas de pénalisation).

Tests purs en mémoire via AsyncSmartMockCursor (zéro DB réelle).
"""
import random
from unittest.mock import AsyncMock, patch

import pytest

from config.engine import LOTO_CONFIG
from engine.hybride_base import HybrideEngine
from tests.conftest import AsyncSmartMockCursor, make_async_conn


def _draw(balls: list[int], chance: int) -> dict:
    """Construit un dict au format get_recent_draws (boule_1..5 + numero_chance)."""
    d = {f"boule_{i}": b for i, b in enumerate(balls, 1)}
    d["numero_chance"] = chance
    d["date_de_tirage"] = "2026-04-01"
    return d


class TestRecentDrawsInjection:

    @pytest.mark.asyncio
    async def test_omitted_calls_get_recent_draws(self):
        """recent_draws omis → get_recent_draws(conn) appelé (path prod inchangé)."""
        cursor = AsyncSmartMockCursor()
        random.seed(42)
        engine = HybrideEngine(LOTO_CONFIG)
        spy = AsyncMock(return_value=[_draw([1, 2, 3, 4, 5], 7)])
        with patch.object(HybrideEngine, "get_recent_draws", spy):
            result = await engine.generate_grids(
                n=2, mode="balanced",
                _get_connection=lambda: make_async_conn(cursor),
            )
        spy.assert_awaited()  # appelé au moins une fois
        assert len(result["grids"]) == 2

    @pytest.mark.asyncio
    async def test_provided_skips_get_recent_draws(self):
        """recent_draws fourni → get_recent_draws NON appelé."""
        cursor = AsyncSmartMockCursor()
        random.seed(42)
        engine = HybrideEngine(LOTO_CONFIG)
        spy = AsyncMock(return_value=[_draw([1, 2, 3, 4, 5], 7)])
        injected = [_draw([6, 16, 26, 36, 46], 3)]
        with patch.object(HybrideEngine, "get_recent_draws", spy):
            result = await engine.generate_grids(
                n=2, mode="balanced",
                _get_connection=lambda: make_async_conn(cursor),
                recent_draws=injected,
            )
        spy.assert_not_awaited()  # JAMAIS appelé
        assert len(result["grids"]) == 2

    @pytest.mark.asyncio
    async def test_provided_recent_draws_hard_exclude_applied(self):
        """Les boules T-1 injectées sont hard-excluded (score 0.0) des grilles générées.

        Preuve fonctionnelle que les recent_draws fournis sont bien CONSOMMÉS
        (pas seulement que get_recent_draws est court-circuité).
        T-1 = 1 boule par zone → aucune zone vidée → pas de fallback ESI/zone.
        """
        cursor = AsyncSmartMockCursor()
        random.seed(42)
        engine = HybrideEngine(LOTO_CONFIG)
        t1_balls = [6, 16, 26, 36, 46]
        injected = [_draw(t1_balls, 3)]
        spy = AsyncMock(return_value=[_draw([1, 2, 3, 4, 5], 7)])
        with patch.object(HybrideEngine, "get_recent_draws", spy):
            result = await engine.generate_grids(
                n=10, mode="balanced",
                _get_connection=lambda: make_async_conn(cursor),
                recent_draws=injected,
            )
        spy.assert_not_awaited()
        for grid in result["grids"]:
            overlap = set(grid["nums"]) & set(t1_balls)
            assert not overlap, f"boule T-1 hard-excluded présente dans {grid['nums']}: {overlap}"

    @pytest.mark.asyncio
    async def test_empty_list_skips_get_recent_draws(self):
        """recent_draws=[] (cas idx=0 backtest) → get_recent_draws NON appelé.

        Invariant harness : toujours passer une liste (jamais None). [] n'est
        pas None → la garde `if recent_draws is None` est False → pas de fetch,
        pas de pénalisation (correct : aucun T-1 n'existe au 1er tirage rejoué).
        """
        cursor = AsyncSmartMockCursor()
        random.seed(42)
        engine = HybrideEngine(LOTO_CONFIG)
        spy = AsyncMock(return_value=[_draw([1, 2, 3, 4, 5], 7)])
        with patch.object(HybrideEngine, "get_recent_draws", spy):
            result = await engine.generate_grids(
                n=2, mode="balanced",
                _get_connection=lambda: make_async_conn(cursor),
                recent_draws=[],
            )
        spy.assert_not_awaited()
        assert len(result["grids"]) == 2
