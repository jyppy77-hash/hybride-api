"""Tests harness — fenêtrage relatif de recent_draws (fix future-leak).

Vérifie que `run_config` injecte le T-1 RELATIF au target rejoué :
  - mapping TirageRecord → format colonne (boule_1..5 + secondary_columns) ;
  - off-by-one : le target tirages[idx] n'est JAMAIS dans ses propres recent_draws ;
  - ordre : T-1 en position 0 (most-recent-first, aligné get_recent_draws DESC) ;
  - fenêtre partielle idx < penalty_window ;
  - [] (liste, pas None) à idx=0.

Tests purs en mémoire — load_tirages + _generate_grilles mockés (zéro DB).
"""
from __future__ import annotations

from datetime import date

import pytest

from tools.backtest_hybride import BacktestConfig, BacktestHarness, TirageRecord


# ════════════════════════════════════════════════════════════════════════
# Helper _tirage_to_recent_draw_dict
# ════════════════════════════════════════════════════════════════════════

class TestTirageToRecentDrawDict:

    def test_mapping_loto(self):
        h = BacktestHarness(game="loto", n_tirages=3, n_grilles_per_tirage=2)
        t = TirageRecord(draw_date=date(2026, 1, 1), balls=[3, 14, 22, 31, 42], secondary=[5])
        d = h._tirage_to_recent_draw_dict(t)
        assert d["boule_1"] == 3
        assert d["boule_2"] == 14
        assert d["boule_3"] == 22
        assert d["boule_4"] == 31
        assert d["boule_5"] == 42
        assert d["numero_chance"] == 5          # secondary_columns Loto
        assert d["date_de_tirage"] == "2026-01-01"

    def test_mapping_em(self):
        h = BacktestHarness(game="em", n_tirages=3, n_grilles_per_tirage=2)
        t = TirageRecord(draw_date=date(2026, 1, 2), balls=[7, 19, 24, 36, 48], secondary=[3, 9])
        d = h._tirage_to_recent_draw_dict(t)
        assert d["boule_1"] == 7
        assert d["boule_5"] == 48
        assert d["etoile_1"] == 3               # secondary_columns EM
        assert d["etoile_2"] == 9


# ════════════════════════════════════════════════════════════════════════
# Fenêtrage relatif dans run_config
# ════════════════════════════════════════════════════════════════════════

def _fake_tirages(n: int) -> list[TirageRecord]:
    """n tirages ASC, chance = idx+1 (1..n) pour identifier l'ordre au readback."""
    return [
        TirageRecord(
            draw_date=date(2026, 1, 1 + i),
            balls=[1 + i, 11 + i, 21 + i, 31 + i, 41 - i],
            secondary=[i + 1],                  # chance distincte 1..n
        )
        for i in range(n)
    ]


class TestRecentDrawsWindowRelative:

    @pytest.mark.asyncio
    async def test_window_relative_per_idx(self, monkeypatch):
        """Capture les recent_draws passés par run_config à chaque idx.

        penalty_window Loto = 4. 6 tirages (chances 1..6).
        Attendu :
          idx=0 → []                         (aucun T-1)
          idx=1 → [chance 1]                 (T-1 = tirages[0])
          idx=5 → [5, 4, 3, 2]               (T-1..T-4, target chance 6 exclu,
                                              tirages[0] chance 1 hors fenêtre W=4)
        """
        h = BacktestHarness(game="loto", n_tirages=6, n_grilles_per_tirage=1)
        tirages = _fake_tirages(6)

        async def fake_load_tirages():
            h._tirages_cache = list(tirages)
            return h._tirages_cache

        captured: list = []

        async def fake_generate(engine, brake_balls, brake_secondary, recent_draws=None):
            captured.append(recent_draws)
            return [{"nums": [1, 2, 3, 4, 5], "chance": 1, "score": 50, "badges": []}]

        monkeypatch.setattr(h, "load_tirages", fake_load_tirages)
        monkeypatch.setattr(h, "_generate_grilles", fake_generate)

        await h.run_config(BacktestConfig())

        assert len(captured) == 6
        # Invariant : jamais None (toujours une liste)
        assert all(c is not None for c in captured), "recent_draws None détecté (re-leak)"

        # idx=0 : aucun T-1 → liste vide
        assert captured[0] == []

        # idx=1 : T-1 = tirages[0] (chance 1)
        assert [d["numero_chance"] for d in captured[1]] == [1]

        # idx=2 : T-1, T-2 = tirages[1], tirages[0] → chances [2, 1] (most-recent-first)
        assert [d["numero_chance"] for d in captured[2]] == [2, 1]

        # idx=5 : fenêtre W=4 → tirages[1..4] reversed = [5, 4, 3, 2].
        #   - target tirages[5] (chance 6) EXCLU (off-by-one) ;
        #   - tirages[0] (chance 1) hors fenêtre (cap W=4) ;
        #   - ordre décroissant = T-1 en position 0.
        assert [d["numero_chance"] for d in captured[5]] == [5, 4, 3, 2]

    @pytest.mark.asyncio
    async def test_target_never_in_own_recent_draws(self, monkeypatch):
        """Aucun target tirages[idx] ne figure dans ses propres recent_draws."""
        h = BacktestHarness(game="loto", n_tirages=6, n_grilles_per_tirage=1)
        tirages = _fake_tirages(6)

        async def fake_load_tirages():
            h._tirages_cache = list(tirages)
            return h._tirages_cache

        captured: list = []

        async def fake_generate(engine, brake_balls, brake_secondary, recent_draws=None):
            captured.append(recent_draws)
            return [{"nums": [1, 2, 3, 4, 5], "chance": 1, "score": 50, "badges": []}]

        monkeypatch.setattr(h, "load_tirages", fake_load_tirages)
        monkeypatch.setattr(h, "_generate_grilles", fake_generate)

        await h.run_config(BacktestConfig())

        for idx, recent in enumerate(captured):
            target_chance = tirages[idx].secondary[0]
            chances = [d["numero_chance"] for d in recent]
            assert target_chance not in chances, (
                f"idx={idx}: target chance {target_chance} présent dans recent_draws {chances}"
            )
