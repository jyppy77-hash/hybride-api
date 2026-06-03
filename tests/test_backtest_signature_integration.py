"""Tests V_X.F LOT 2 — intégration signature dans tools/backtest_hybride.py.

Couvre :
    - _compute_tier1_stats (méthode pure, testable sans DB)
    - _compute_tier2_signature (méthode pure, baseline lru_cache)
    - run_config end-to-end via mocks (load_tirages + _generate_grilles)

⚠️ Contrainte dure : test_run_config_keys_backward_compat doit vérifier
les 5 clés historiques consommées par grid_search_hybride.py + compare().

Tests purs en mémoire — pas de DB. Mocks via monkeypatch.
"""
from __future__ import annotations

import json
import math
from datetime import date

import pytest

from tools.backtest_hybride import (
    _TIER1_FEATURES,
    BacktestConfig,
    BacktestHarness,
    TirageRecord,
)


# ════════════════════════════════════════════════════════════════════════
# Fixtures — mini-run sans DB
# ════════════════════════════════════════════════════════════════════════

_FAKE_TIRAGES_LOTO: list[TirageRecord] = [
    TirageRecord(draw_date=date(2026, 1, 1), balls=[3, 14, 22, 31, 42], secondary=[5]),
    TirageRecord(draw_date=date(2026, 1, 8), balls=[7, 19, 24, 36, 48], secondary=[3]),
    TirageRecord(draw_date=date(2026, 1, 15), balls=[1, 11, 21, 38, 49], secondary=[8]),
]

_FAKE_GRILLES_LOTO: list[dict] = [
    {"nums": [5, 13, 21, 34, 45], "chance": 7, "score": 95, "badges": []},
    {"nums": [2, 17, 28, 33, 47], "chance": 2, "score": 85, "badges": []},
    {"nums": [9, 14, 25, 31, 41], "chance": 9, "score": 75, "badges": []},
    {"nums": [4, 11, 23, 37, 48], "chance": 4, "score": 60, "badges": []},
    {"nums": [6, 15, 26, 32, 49], "chance": 6, "score": 50, "badges": []},
]


def _make_harness(game: str = "loto") -> BacktestHarness:
    return BacktestHarness(game=game, n_tirages=3, n_grilles_per_tirage=5)


@pytest.fixture
def mocked_harness(monkeypatch):
    """Harness Loto avec load_tirages + _generate_grilles mockés (zéro DB)."""
    h = _make_harness("loto")

    async def fake_load_tirages():
        h._tirages_cache = list(_FAKE_TIRAGES_LOTO)
        return h._tirages_cache

    async def fake_generate(engine, brake_balls, brake_secondary, recent_draws=None):
        # 5 grilles fictives identiques par tirage (suffisant pour smoke)
        return [dict(g) for g in _FAKE_GRILLES_LOTO]

    monkeypatch.setattr(h, "load_tirages", fake_load_tirages)
    monkeypatch.setattr(h, "_generate_grilles", fake_generate)
    return h


# ════════════════════════════════════════════════════════════════════════
# _compute_tier1_stats (méthode pure)
# ════════════════════════════════════════════════════════════════════════

class TestComputeTier1Stats:

    def test_basic_structure(self):
        h = _make_harness("loto")
        # Valeurs synthétiques par feature
        feature_values = {
            "somme": [100.0, 125.0, 150.0, 130.0, 110.0],
            "dispersion": [20.0, 25.0, 30.0, 35.0, 40.0],
            "std": [10.0, 12.0, 14.0, 16.0, 18.0],
            "freq_1_31": [3.0, 2.0, 4.0, 3.0, 2.0],
            "nb_pairs": [2.0, 3.0, 2.0, 3.0, 1.0],
            "nb_consecutifs": [0.0, 1.0, 0.0, 2.0, 0.0],
            "esi": [200.0, 250.0, 300.0, 180.0, 220.0],
        }
        tier1 = h._compute_tier1_stats(feature_values)
        # 5 features Tier 1 attendues
        assert set(tier1.keys()) == set(_TIER1_FEATURES)
        # freq_1_31 et nb_pairs absents de Tier 1
        assert "freq_1_31" not in tier1
        assert "nb_pairs" not in tier1
        # stats de base présentes
        for fname in _TIER1_FEATURES:
            entry = tier1[fname]
            assert "n" in entry
            assert "mean" in entry
            assert "median" in entry
            assert "std" in entry
            assert "min" in entry
            assert "max" in entry

    def test_pct_out_of_bounds_somme_loto(self):
        h = _make_harness("loto")
        # LOTO_CONFIG : somme_min=93, somme_max=157
        # values : 2 sous min (50, 80), 1 dans [93, 157] (125), 2 sur max (180, 200)
        feature_values = {fname: [] for fname in (
            "somme", "dispersion", "std", "freq_1_31", "nb_pairs",
            "nb_consecutifs", "esi",
        )}
        feature_values["somme"] = [50.0, 80.0, 125.0, 180.0, 200.0]
        feature_values["dispersion"] = [20.0] * 5
        feature_values["std"] = [10.0] * 5
        feature_values["nb_consecutifs"] = [0.0] * 5
        feature_values["esi"] = [200.0] * 5
        tier1 = h._compute_tier1_stats(feature_values)
        # 4/5 hors bornes → 80%
        assert tier1["somme"]["pct_out_of_bounds"] == 80.0
        assert tier1["somme"]["bounds"] == [93, 157]

    def test_pct_above_max_nb_consecutifs_loto(self):
        h = _make_harness("loto")
        # LOTO_CONFIG : max_consecutifs=2
        feature_values = {fname: [10.0] * 5 for fname in (
            "somme", "dispersion", "std", "freq_1_31", "nb_pairs", "esi",
        )}
        feature_values["nb_consecutifs"] = [0.0, 1.0, 2.0, 3.0, 4.0]  # 2/5 > 2
        tier1 = h._compute_tier1_stats(feature_values)
        assert tier1["nb_consecutifs"]["pct_above_max"] == 40.0
        assert tier1["nb_consecutifs"]["max_threshold"] == 2

    def test_pct_below_min_dispersion_loto(self):
        h = _make_harness("loto")
        # LOTO_CONFIG : dispersion_min=15
        feature_values = {fname: [10.0] * 5 for fname in (
            "somme", "std", "freq_1_31", "nb_pairs", "nb_consecutifs", "esi",
        )}
        feature_values["dispersion"] = [5.0, 10.0, 15.0, 20.0, 25.0]  # 2/5 < 15
        tier1 = h._compute_tier1_stats(feature_values)
        assert tier1["dispersion"]["pct_below_min"] == 40.0
        assert tier1["dispersion"]["min_threshold"] == 15

    def test_empty_values_no_crash(self):
        h = _make_harness("loto")
        feature_values = {fname: [] for fname in (
            "somme", "dispersion", "std", "freq_1_31", "nb_pairs",
            "nb_consecutifs", "esi",
        )}
        tier1 = h._compute_tier1_stats(feature_values)
        for fname in _TIER1_FEATURES:
            assert tier1[fname] == {"n": 0}


# ════════════════════════════════════════════════════════════════════════
# _compute_tier2_signature (méthode pure, baseline cached)
# ════════════════════════════════════════════════════════════════════════

class TestComputeTier2Signature:

    def test_basic_structure(self):
        h = _make_harness("loto")
        # mini sample HYBRIDE
        feature_values = {
            "somme": [125.0, 130.0, 140.0],
            "dispersion": [30.0, 35.0, 40.0],
            "std": [12.0, 14.0, 16.0],
            "freq_1_31": [3.0, 2.0, 4.0],
            "nb_pairs": [2.0, 3.0, 2.0],
            "nb_consecutifs": [0.0, 1.0, 0.0],
            "esi": [200.0, 220.0, 240.0],
        }
        # n=200 pour rapidité (lru_cache mémorise pour test suivants)
        from tools.backtest_hybride import _SIGNATURE_BASELINE_SEED
        # On override la constante via monkey du résultat — plus simple :
        # appeler la méthode et vérifier la structure
        tier2 = h._compute_tier2_signature(feature_values, n_hybride_samples=3)
        # Structure obligatoire
        assert "feature_jsd" in tier2
        assert "baseline" in tier2
        assert "base" in tier2
        assert "n_hybride_samples" in tier2
        # 7 features dans feature_jsd
        assert set(tier2["feature_jsd"].keys()) == {
            "somme", "dispersion", "std", "freq_1_31",
            "nb_pairs", "nb_consecutifs", "esi",
        }
        # baseline metadata
        assert tier2["baseline"]["n"] > 0
        assert tier2["baseline"]["seed"] == _SIGNATURE_BASELINE_SEED
        assert tier2["baseline"]["source"] == "random.sample uniform"
        assert tier2["baseline"]["num_max"] == 49
        assert tier2["base"] == "e"
        assert tier2["n_hybride_samples"] == 3

    def test_jsd_bounded_in_natural_log(self):
        h = _make_harness("loto")
        feature_values = {
            "somme": [125.0] * 100,
            "dispersion": [30.0] * 100,
            "std": [12.0] * 100,
            "freq_1_31": [3.0] * 100,
            "nb_pairs": [2.0] * 100,
            "nb_consecutifs": [0.0] * 100,
            "esi": [200.0] * 100,
        }
        tier2 = h._compute_tier2_signature(feature_values, n_hybride_samples=100)
        for fname, jsd in tier2["feature_jsd"].items():
            assert 0.0 <= jsd <= math.log(2) + 1e-9, (
                f"feature {fname}: JSD={jsd} hors bornes"
            )

    def test_em_num_max_50_in_baseline(self):
        h = _make_harness("em")
        feature_values = {
            "somme": [125.0],
            "dispersion": [30.0],
            "std": [12.0],
            "freq_1_31": [3.0],
            "nb_pairs": [2.0],
            "nb_consecutifs": [0.0],
            "esi": [200.0],
        }
        tier2 = h._compute_tier2_signature(feature_values, n_hybride_samples=1)
        assert tier2["baseline"]["num_max"] == 50


# ════════════════════════════════════════════════════════════════════════
# run_config intégration (via mocks) — non-régression OBLIGATOIRE
# ════════════════════════════════════════════════════════════════════════

class TestRunConfigIntegration:

    HISTORICAL_KEYS: tuple[str, ...] = (
        "total_grilles_generated",
        "gagnantes_pct_global",
        "gagnantes_per_palier",
        "stratification_distribution_generated",
        "ratio_observed_vs_hasard",
    )

    NEW_KEYS: tuple[str, ...] = ("tier1", "tier2", "by_construction")

    @pytest.mark.asyncio
    async def test_run_config_keys_backward_compat(self, mocked_harness):
        """⚠️ CONTRAINTE DURE V_X.F LOT 2 : 5 clés historiques préservées.

        grid_search_hybride.py:212-218 et tools/backtest_hybride.py:580,
        585-586, 620 lisent directement ces clés. Une seule disparue/
        renommée casse le grid search en silence.
        """
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg)
        for k in self.HISTORICAL_KEYS:
            assert k in result, f"clé historique disparue : {k!r}"
        # Types préservés
        assert isinstance(result["total_grilles_generated"], int)
        assert isinstance(result["gagnantes_pct_global"], float)
        assert isinstance(result["gagnantes_per_palier"], dict)
        assert isinstance(result["stratification_distribution_generated"], dict)
        assert isinstance(result["ratio_observed_vs_hasard"], float)

    @pytest.mark.asyncio
    async def test_run_config_has_new_keys(self, mocked_harness):
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg)
        for k in self.NEW_KEYS:
            assert k in result, f"clé V_X.F manquante : {k!r}"

    @pytest.mark.asyncio
    async def test_run_config_tier2_jsd_per_feature(self, mocked_harness):
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg)
        tier2 = result["tier2"]
        feature_jsd = tier2["feature_jsd"]
        # 7 features attendues
        expected = {"somme", "dispersion", "std", "freq_1_31",
                    "nb_pairs", "nb_consecutifs", "esi"}
        assert set(feature_jsd.keys()) == expected
        # Toutes valeurs dans [0, log(2)]
        for fname, jsd in feature_jsd.items():
            assert 0.0 <= jsd <= math.log(2) + 1e-9, (
                f"JSD hors bornes pour {fname}: {jsd}"
            )

    @pytest.mark.asyncio
    async def test_run_config_total_grilles_matches(self, mocked_harness):
        """3 tirages × 5 grilles = 15 grilles totales attendues."""
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg)
        assert result["total_grilles_generated"] == 15
        assert result["tier2"]["n_hybride_samples"] == 15

    @pytest.mark.asyncio
    async def test_run_config_by_construction_metadata(self, mocked_harness):
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg)
        bc = result["by_construction"]
        assert "stratification" in bc
        assert "monochrome" in bc
        assert "_draw_stratified" in bc["stratification"]
        assert "hard-rejected" in bc["monochrome"]


# ════════════════════════════════════════════════════════════════════════
# V_X.F LOT 3 — Smoke E2E : histograms, JSON export, plots PNG, sanity
# ════════════════════════════════════════════════════════════════════════

class TestSmokeE2E:

    @pytest.mark.asyncio
    async def test_run_config_produces_histograms_in_tier2(self, mocked_harness):
        """V_X.F LOT 3 — tier2 contient maintenant 'histograms' (additif)."""
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg)
        tier2 = result["tier2"]
        assert "histograms" in tier2, "clé 'histograms' V_X.F LOT 3 manquante"
        # 7 features dans histograms, chacune avec bins/hybride/random/real_tirages
        assert set(tier2["histograms"].keys()) == {
            "somme", "dispersion", "std", "freq_1_31",
            "nb_pairs", "nb_consecutifs", "esi",
        }
        for fname, h in tier2["histograms"].items():
            assert "bins" in h
            assert "hybride" in h
            assert "random" in h
            assert "real_tirages" in h
            # Densités sommables à ~1 (sauf si toutes nulles)
            for key in ("hybride", "random"):
                s = sum(h[key])
                assert 0.0 <= s <= 1.0 + 1e-6, f"{fname}.{key} sum={s}"

    @pytest.mark.asyncio
    async def test_real_tirages_features_in_histograms(self, mocked_harness):
        """Vrais tirages (overlay narratif) bien injectés dans histograms."""
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg)
        histograms = result["tier2"]["histograms"]
        for fname in ("somme", "dispersion", "esi"):
            real = histograms[fname]["real_tirages"]
            assert real is not None, f"{fname}.real_tirages None (tirages non passés)"
            # 3 fake tirages → distribution non vide
            assert sum(real) > 0.0

    @pytest.mark.asyncio
    async def test_json_export_serializable(self, mocked_harness, tmp_path):
        """JSON round-trip complet : tier1, tier2, by_construction sérialisables."""
        cfg = BacktestConfig()
        result_A = await mocked_harness.run_config(cfg)
        # Simuler le wrapper compare() minimal (sans 2nd run pour rapidité)
        wrapper = {
            "metadata": {
                "harness_version": "v1.0",
                "run_at": "2026-05-28T00:00:00Z",
                "game": "loto",
                "n_tirages": 3,
                "n_grilles_per_tirage": 5,
                "mode": "balanced",
                "tirages_replayed_range": {"first": "2026-01-01", "last": "2026-01-15"},
                "elapsed_seconds": 0.1,
                "limitations_mvp": [],
            },
            "config_actuelle": {},
            "config_test": {},
            "hasard_theorique_min_palier_pct": 7.46,
            "results_config_actuelle": result_A,
            "results_config_test": result_A,
            "stratification_distribution_real_empirical": {},
            "diff": {},
        }
        json_path = tmp_path / "test_out.json"
        mocked_harness.export_json(wrapper, str(json_path))
        # Vérif fichier non vide + parsable + contient les clés V_X.F
        assert json_path.exists()
        assert json_path.stat().st_size > 0
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "tier1" in data["results_config_actuelle"]
        assert "tier2" in data["results_config_actuelle"]
        assert "by_construction" in data["results_config_actuelle"]
        assert "histograms" in data["results_config_actuelle"]["tier2"]
        # Histograms sont bien des list (pas des np.ndarray stringifiés)
        assert isinstance(
            data["results_config_actuelle"]["tier2"]["histograms"]["somme"]["hybride"],
            list,
        )

    @pytest.mark.asyncio
    async def test_plot_signature_distributions_creates_png(
        self, mocked_harness, tmp_path,
    ):
        """plot_signature_distributions génère un PNG non vide."""
        cfg = BacktestConfig()
        result_A = await mocked_harness.run_config(cfg)
        wrapper = {
            "metadata": {
                "game": "loto", "n_tirages": 3, "n_grilles_per_tirage": 5,
                "mode": "balanced", "elapsed_seconds": 0.1,
                "harness_version": "v1.0", "run_at": "2026-05-28T00:00:00Z",
            },
            "results_config_actuelle": result_A,
            "results_config_test": result_A,
            "config_actuelle": {}, "config_test": {},
        }
        png_path = tmp_path / "sig_dist.png"
        mocked_harness.plot_signature_distributions(wrapper, str(png_path))
        assert png_path.exists()
        assert png_path.stat().st_size > 5_000  # PNG min raisonnable

    @pytest.mark.asyncio
    async def test_plot_signature_summary_creates_png(
        self, mocked_harness, tmp_path,
    ):
        """plot_signature_summary génère un PNG non vide."""
        cfg = BacktestConfig()
        result_A = await mocked_harness.run_config(cfg)
        wrapper = {
            "metadata": {
                "game": "loto", "n_tirages": 3, "n_grilles_per_tirage": 5,
                "mode": "balanced", "elapsed_seconds": 0.1,
                "harness_version": "v1.0", "run_at": "2026-05-28T00:00:00Z",
            },
            "results_config_actuelle": result_A,
            "results_config_test": result_A,
            "config_actuelle": {}, "config_test": {},
        }
        png_path = tmp_path / "sig_summary.png"
        mocked_harness.plot_signature_summary(wrapper, str(png_path))
        assert png_path.exists()
        assert png_path.stat().st_size > 5_000

    @pytest.mark.asyncio
    async def test_signature_sanity_dispersion_synthetic(self, monkeypatch):
        """Sanity : grilles synthétiques 1-par-zone (HYBRIDE-like) → JSD
        dispersion > 0.05 vs random pur (signature spatiale détectée).
        """
        import random as _stdlib_random
        h = BacktestHarness(game="loto", n_tirages=3, n_grilles_per_tirage=20)

        async def fake_load_tirages():
            h._tirages_cache = list(_FAKE_TIRAGES_LOTO)
            return h._tirages_cache

        rng = _stdlib_random.Random(2026)
        zones = [(1, 10), (11, 20), (21, 30), (31, 40), (41, 49)]

        async def fake_generate(engine, brake_balls, brake_secondary, recent_draws=None):
            # 20 grilles synthétiques 1-par-zone
            return [
                {"nums": [rng.randint(lo, hi) for lo, hi in zones],
                 "chance": rng.randint(1, 10), "score": 95, "badges": []}
                for _ in range(20)
            ]

        monkeypatch.setattr(h, "load_tirages", fake_load_tirages)
        monkeypatch.setattr(h, "_generate_grilles", fake_generate)

        cfg = BacktestConfig()
        result = await h.run_config(cfg)
        jsd_dispersion = result["tier2"]["feature_jsd"]["dispersion"]
        # Signature spatiale 1-par-zone → JSD substantielle
        assert jsd_dispersion > 0.05, (
            f"signature dispersion JSD trop faible : {jsd_dispersion}"
        )
