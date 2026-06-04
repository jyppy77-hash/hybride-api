"""Tests LOT S1 — extension secondaire signature : feature reine `*_in_T1`.

Couvre :
    - signature_features : extract_secondary_in_t1 (overlap Loto/EM),
      build_secondary_bins (edges), generate_secondary_in_t1_baseline
      (déterminisme seed=42, domaine, modèle nul appariée), séparation
      stricte vs briques boules.
    - backtest_hybride : intégration additive (tier2["secondary"] présent SI
      --include-secondary, absent sinon), non-régression tier2["feature_jsd"]
      boules, skip idx=0.

Tests purs en mémoire — pas de DB. Mocks via monkeypatch.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from tools.signature_features import (
    FEATURE_NAMES,
    SECONDARY_FEATURE_NAMES,
    build_bins,
    build_secondary_bins,
    compute_feature_jsd,
    extract_secondary_in_t1,
    generate_secondary_in_t1_baseline,
)
from tools.backtest_hybride import BacktestConfig, BacktestHarness, TirageRecord


# ════════════════════════════════════════════════════════════════════════
# 1 — extract_secondary_in_t1 : overlap grille ∩ T-1
# ════════════════════════════════════════════════════════════════════════

class TestExtractSecondaryInT1:

    # ── Loto (chance int, 1 élément) ──────────────────────────────────
    def test_loto_chance_in_t1(self):
        # chance 7 présente dans T-1 [7] → overlap 1
        out = extract_secondary_in_t1(7, [7])
        assert out == {"chance_in_T1": 1.0}

    def test_loto_chance_not_in_t1(self):
        # chance 7 absente de T-1 [3] → overlap 0
        out = extract_secondary_in_t1(7, [3])
        assert out == {"chance_in_T1": 0.0}

    def test_loto_chance_name_from_cardinality(self):
        # Grille secondaire à 1 élément → toujours "chance_in_T1"
        assert "chance_in_T1" in extract_secondary_in_t1(5, [9])

    # ── EM (etoiles list, 2 éléments) ─────────────────────────────────
    def test_em_two_stars_match(self):
        out = extract_secondary_in_t1([2, 10], [2, 10])
        assert out == {"etoiles_in_T1": 2.0}

    def test_em_one_star_match(self):
        out = extract_secondary_in_t1([2, 10], [2, 5])
        assert out == {"etoiles_in_T1": 1.0}

    def test_em_zero_star_match(self):
        out = extract_secondary_in_t1([2, 10], [3, 5])
        assert out == {"etoiles_in_T1": 0.0}

    def test_em_name_from_cardinality(self):
        # Grille secondaire à 2 éléments → toujours "etoiles_in_T1"
        assert "etoiles_in_T1" in extract_secondary_in_t1([1, 12], [4, 8])

    # ── Robustesse ────────────────────────────────────────────────────
    def test_empty_prev_secondary_zero(self):
        # Pas de T-1 (liste vide) → overlap 0 (le skip idx=0 est côté harness)
        assert extract_secondary_in_t1(7, []) == {"chance_in_T1": 0.0}

    def test_set_and_tuple_inputs(self):
        # Accepte set / tuple indifféremment
        assert extract_secondary_in_t1({2, 10}, (2, 7)) == {"etoiles_in_T1": 1.0}


# ════════════════════════════════════════════════════════════════════════
# 2 — build_secondary_bins : edges petit-univers + séparation des registres
# ════════════════════════════════════════════════════════════════════════

class TestBuildSecondaryBins:

    def test_chance_bins(self):
        bins = build_secondary_bins("chance_in_T1")
        assert np.array_equal(bins, np.array([0.0, 1.0, 2.0]))
        # 2 bins → valeurs 0 et 1 tombent dans des bins distincts
        assert len(bins) - 1 == 2

    def test_etoiles_bins(self):
        bins = build_secondary_bins("etoiles_in_T1")
        assert np.array_equal(bins, np.array([0.0, 1.0, 2.0, 3.0]))
        assert len(bins) - 1 == 3

    def test_unknown_secondary_feature_raises(self):
        with pytest.raises(ValueError):
            build_secondary_bins("somme")  # nom boules → rejeté

    def test_registres_separes(self):
        # build_bins boules lève sur un nom secondaire …
        with pytest.raises(ValueError):
            build_bins("chance_in_T1")
        # … et build_secondary_bins lève sur un nom boules.
        with pytest.raises(ValueError):
            build_secondary_bins("esi")

    def test_histogram_assigns_values_to_distinct_bins(self):
        # Sanity binning : 0/1/2 → bins 0/1/2 pour etoiles
        bins = build_secondary_bins("etoiles_in_T1")
        hist, _ = np.histogram([0, 1, 2], bins=bins)
        assert list(hist) == [1, 1, 1]


# ════════════════════════════════════════════════════════════════════════
# 3 — generate_secondary_in_t1_baseline : simulation appariée (modèle nul)
# ════════════════════════════════════════════════════════════════════════

class TestSecondaryBaseline:

    def test_loto_domain_and_key(self):
        baseline = generate_secondary_in_t1_baseline(
            n=5000, sec_min=1, sec_max=10, count=1, seed=42,
        )
        assert len(baseline) == 5000
        for entry in baseline[:200]:
            assert set(entry.keys()) == {"chance_in_T1"}
            assert entry["chance_in_T1"] in (0.0, 1.0)

    def test_em_domain_and_key(self):
        baseline = generate_secondary_in_t1_baseline(
            n=5000, sec_min=1, sec_max=12, count=2, seed=42,
        )
        for entry in baseline[:200]:
            assert set(entry.keys()) == {"etoiles_in_T1"}
            assert entry["etoiles_in_T1"] in (0.0, 1.0, 2.0)

    def test_deterministic_seed(self):
        # Même params → tuple identique (lru_cache + random.Random local)
        a = generate_secondary_in_t1_baseline(n=3000, sec_min=1, sec_max=10, count=1, seed=42)
        b = generate_secondary_in_t1_baseline(n=3000, sec_min=1, sec_max=10, count=1, seed=42)
        assert a is b or a == b
        # Seed différente → distribution différente (overlap mean change)
        c = generate_secondary_in_t1_baseline(n=3000, sec_min=1, sec_max=10, count=1, seed=7)
        mean_a = sum(e["chance_in_T1"] for e in a) / len(a)
        mean_c = sum(e["chance_in_T1"] for e in c) / len(c)
        assert mean_a == pytest.approx(mean_c, abs=0.05)  # même loi, mêmes paramètres

    def test_loto_null_overlap_mean(self):
        # Modèle nul Loto : P(chance random == T-1 chance random) = 1/10
        baseline = generate_secondary_in_t1_baseline(
            n=40000, sec_min=1, sec_max=10, count=1, seed=42,
        )
        mean = sum(e["chance_in_T1"] for e in baseline) / len(baseline)
        assert mean == pytest.approx(0.10, abs=0.02)

    def test_em_null_overlap_mean(self):
        # Modèle nul EM : E[overlap] = 2 * (2/12) = 0.3333…
        baseline = generate_secondary_in_t1_baseline(
            n=40000, sec_min=1, sec_max=12, count=2, seed=42,
        )
        mean = sum(e["etoiles_in_T1"] for e in baseline) / len(baseline)
        assert mean == pytest.approx(2.0 * 2.0 / 12.0, abs=0.02)

    def test_jsd_bounded(self):
        baseline = generate_secondary_in_t1_baseline(
            n=5000, sec_min=1, sec_max=10, count=1, seed=42,
        )
        baseline_vals = [e["chance_in_T1"] for e in baseline]
        hybride_vals = [0.0] * 500 + [1.0] * 10  # signature : creux T-1 marqué
        bins = build_secondary_bins("chance_in_T1")
        jsd = compute_feature_jsd(hybride_vals, baseline_vals, bins)
        assert 0.0 <= jsd <= math.log(2) + 1e-9


# ════════════════════════════════════════════════════════════════════════
# 4 — Intégration harness : additivité + non-régression boules + skip idx=0
# ════════════════════════════════════════════════════════════════════════

_FAKE_TIRAGES_LOTO: list[TirageRecord] = [
    TirageRecord(draw_date=date(2026, 1, 1), balls=[3, 14, 22, 31, 42], secondary=[5]),
    TirageRecord(draw_date=date(2026, 1, 8), balls=[7, 19, 24, 36, 48], secondary=[3]),
    TirageRecord(draw_date=date(2026, 1, 15), balls=[1, 11, 21, 38, 49], secondary=[8]),
]

_FAKE_GRILLES_LOTO: list[dict] = [
    {"nums": [5, 13, 21, 34, 45], "chance": 7, "score": 95, "badges": []},
    {"nums": [2, 17, 28, 33, 47], "chance": 3, "score": 85, "badges": []},
    {"nums": [9, 14, 25, 31, 41], "chance": 9, "score": 75, "badges": []},
    {"nums": [4, 11, 23, 37, 48], "chance": 5, "score": 60, "badges": []},
    {"nums": [6, 15, 26, 32, 49], "chance": 6, "score": 50, "badges": []},
]


@pytest.fixture
def mocked_harness(monkeypatch):
    h = BacktestHarness(game="loto", n_tirages=3, n_grilles_per_tirage=5)

    async def fake_load_tirages():
        h._tirages_cache = list(_FAKE_TIRAGES_LOTO)
        return h._tirages_cache

    async def fake_generate(engine, brake_balls, brake_secondary, recent_draws=None):
        return [dict(g) for g in _FAKE_GRILLES_LOTO]

    monkeypatch.setattr(h, "load_tirages", fake_load_tirages)
    monkeypatch.setattr(h, "_generate_grilles", fake_generate)
    return h


class TestHarnessSecondaryIntegration:

    @pytest.mark.asyncio
    async def test_secondary_absent_without_flag(self, mocked_harness):
        result = await mocked_harness.run_config(BacktestConfig())
        assert "secondary" not in result["tier2"], (
            "tier2['secondary'] ne doit PAS apparaître sans --include-secondary"
        )

    @pytest.mark.asyncio
    async def test_secondary_present_with_flag(self, mocked_harness):
        result = await mocked_harness.run_config(BacktestConfig(), include_secondary=True)
        sec = result["tier2"]["secondary"]
        assert "feature_jsd" in sec
        assert "histograms" in sec
        assert "baseline" in sec
        assert "anj_disclaimer" in sec
        # Loto → feature reine chance_in_T1 uniquement
        assert set(sec["feature_jsd"].keys()) == {"chance_in_T1"}

    @pytest.mark.asyncio
    async def test_boules_feature_jsd_unchanged_by_flag(self, mocked_harness):
        """Non-régression : tier2['feature_jsd'] boules identique avec/sans flag."""
        r_off = await mocked_harness.run_config(BacktestConfig())
        r_on = await mocked_harness.run_config(BacktestConfig(), include_secondary=True)
        assert r_off["tier2"]["feature_jsd"] == r_on["tier2"]["feature_jsd"]
        # Les 7 features boules toujours là
        assert set(r_on["tier2"]["feature_jsd"].keys()) == set(FEATURE_NAMES)

    @pytest.mark.asyncio
    async def test_skip_idx0_sample_count(self, mocked_harness):
        """idx=0 sans T-1 → skippé. 3 tirages × 5 grilles, idx 1 et 2 seulement
        contribuent au secondaire = 2 × 5 = 10 samples (vs 15 pour les boules)."""
        result = await mocked_harness.run_config(BacktestConfig(), include_secondary=True)
        assert result["total_grilles_generated"] == 15
        assert result["tier2"]["secondary"]["n_hybride_samples"] == 10

    @pytest.mark.asyncio
    async def test_secondary_histograms_structure(self, mocked_harness):
        result = await mocked_harness.run_config(BacktestConfig(), include_secondary=True)
        h = result["tier2"]["secondary"]["histograms"]["chance_in_T1"]
        assert set(h.keys()) == {"bins", "hybride", "random", "real_tirages"}
        # real_tirages : appariement séquentiel réel (3 tirages → 2 paires) non None
        assert h["real_tirages"] is not None
        # bins entiers petit-univers chance
        assert h["bins"] == [0.0, 1.0, 2.0]

    @pytest.mark.asyncio
    async def test_secondary_baseline_metadata(self, mocked_harness):
        result = await mocked_harness.run_config(BacktestConfig(), include_secondary=True)
        baseline = result["tier2"]["secondary"]["baseline"]
        assert baseline["source"] == "paired random overlap (secondary random vs T-1 random)"
        assert baseline["sec_min"] == 1
        assert baseline["sec_max"] == 10  # LOTO_CONFIG chance 1-10
        assert baseline["count"] == 1

    @pytest.mark.asyncio
    async def test_jsd_secondary_bounded(self, mocked_harness):
        result = await mocked_harness.run_config(BacktestConfig(), include_secondary=True)
        for fname, jsd in result["tier2"]["secondary"]["feature_jsd"].items():
            assert 0.0 <= jsd <= math.log(2) + 1e-9, f"{fname}: JSD={jsd} hors bornes"


class TestRegistry:

    def test_registry_per_game(self):
        assert SECONDARY_FEATURE_NAMES["loto"] == ("chance_in_T1",)
        assert SECONDARY_FEATURE_NAMES["em"] == ("etoiles_in_T1",)
