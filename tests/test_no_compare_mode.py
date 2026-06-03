"""Tests levier A — mode OOS mono-config (run_oos / --no-compare).

Vérifie que run_oos :
  - n'exécute qu'UN seul run_config (1 appel _generate_grilles par tirage,
    pas 2× comme compare) → ÷2 runtime ;
  - produit un format IDENTIQUE à compare() (results_config_actuelle ET
    results_config_test présents, diff nul) → exports JSON/PNG inchangés ;
  - préserve les 5 clés historiques dans le bloc résultats.

Tests purs en mémoire — load_tirages + _generate_grilles mockés (zéro DB).
"""
from __future__ import annotations

from datetime import date

import pytest

from tools.backtest_hybride import BacktestConfig, BacktestHarness, TirageRecord


_FAKE_TIRAGES = [
    TirageRecord(draw_date=date(2026, 1, 1), balls=[3, 14, 22, 31, 42], secondary=[5]),
    TirageRecord(draw_date=date(2026, 1, 8), balls=[7, 19, 24, 36, 48], secondary=[3]),
    TirageRecord(draw_date=date(2026, 1, 15), balls=[1, 11, 21, 38, 49], secondary=[8]),
]
_FAKE_GRILLES = [
    {"nums": [5, 13, 21, 34, 45], "chance": 7, "score": 95, "badges": []},
    {"nums": [2, 17, 28, 33, 47], "chance": 2, "score": 85, "badges": []},
]

_HISTORICAL_KEYS = (
    "total_grilles_generated",
    "gagnantes_pct_global",
    "gagnantes_per_palier",
    "stratification_distribution_generated",
    "ratio_observed_vs_hasard",
)


@pytest.fixture
def mocked_harness(monkeypatch):
    h = BacktestHarness(game="loto", n_tirages=3, n_grilles_per_tirage=2)
    counter = {"n": 0}

    async def fake_load_tirages():
        h._tirages_cache = list(_FAKE_TIRAGES)
        return h._tirages_cache

    async def fake_generate(engine, brake_balls, brake_secondary, recent_draws=None):
        counter["n"] += 1
        return [dict(g) for g in _FAKE_GRILLES]

    monkeypatch.setattr(h, "load_tirages", fake_load_tirages)
    monkeypatch.setattr(h, "_generate_grilles", fake_generate)
    h._gen_counter = counter
    return h


class TestRunOosSingleConfig:

    @pytest.mark.asyncio
    async def test_runs_only_one_config(self, mocked_harness):
        """run_oos = 1 seul run_config → 1 appel _generate_grilles par tirage (3),
        vs 2× (6) en compare()."""
        await mocked_harness.run_oos(BacktestConfig())
        assert mocked_harness._gen_counter["n"] == 3, (
            f"attendu 3 (1 run_config × 3 tirages), obtenu {mocked_harness._gen_counter['n']}"
        )

    @pytest.mark.asyncio
    async def test_compare_runs_two_configs(self, mocked_harness):
        """Contrôle : compare() fait bien 2× run_config (6 appels) — non régressé."""
        await mocked_harness.compare(BacktestConfig(), BacktestConfig())
        assert mocked_harness._gen_counter["n"] == 6

    @pytest.mark.asyncio
    async def test_output_format_compare_compatible(self, mocked_harness):
        """Format identique à compare : mêmes clés top-level + A/B + diff nul."""
        r = await mocked_harness.run_oos(BacktestConfig())
        for k in ("metadata", "config_actuelle", "config_test",
                  "hasard_theorique_min_palier_pct", "results_config_actuelle",
                  "results_config_test", "stratification_distribution_real_empirical",
                  "diff"):
            assert k in r, f"clé top-level manquante : {k!r}"
        # A et B = le même objet (run réutilisé)
        assert r["results_config_actuelle"] is r["results_config_test"]
        # diff nul
        assert r["diff"]["delta_gagnantes_pct_global"] == 0.0
        assert all(v == 0 for v in r["diff"]["delta_per_palier"].values())
        # marqueur de mode
        assert r["metadata"]["run_mode"] == "single_no_compare"

    @pytest.mark.asyncio
    async def test_historical_keys_preserved(self, mocked_harness):
        """Les 5 clés historiques restent dans le bloc résultats (contrat dur)."""
        r = await mocked_harness.run_oos(BacktestConfig())
        for k in _HISTORICAL_KEYS:
            assert k in r["results_config_actuelle"], f"clé historique disparue : {k!r}"

    @pytest.mark.asyncio
    async def test_tier2_signature_present(self, mocked_harness):
        """La signature V_X.F (tier2.feature_jsd) est bien produite en mono-config."""
        r = await mocked_harness.run_oos(BacktestConfig())
        feature_jsd = r["results_config_actuelle"]["tier2"]["feature_jsd"]
        assert set(feature_jsd.keys()) == {
            "somme", "dispersion", "std", "freq_1_31",
            "nb_pairs", "nb_consecutifs", "esi",
        }
