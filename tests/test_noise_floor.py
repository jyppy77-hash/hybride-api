"""Tests V_X.F — plancher de bruit Monte Carlo + correction FDR Benjamini-Hochberg.

Couvre tools/signature_features.py :
    - compute_noise_floor  (modèle nul Option B, bootstrap vs réf fixe)
    - apply_fdr_correction (Benjamini-Hochberg step-up)

Tests purs en mémoire — pas de DB, pas de fixture lourde.
"""
import math
import random as _stdlib_random

import numpy as np
import pytest

from tools.signature_features import (
    DEFAULT_RANDOM_SEED,
    apply_fdr_correction,
    build_bins,
    build_secondary_bins,
    compute_noise_floor,
    generate_random_baseline,
    generate_secondary_in_t1_baseline,
)

_LN2 = math.log(2.0)


# ════════════════════════════════════════════════════════════════════════
# Helpers — populations de référence réalistes (cachées via lru_cache)
# ════════════════════════════════════════════════════════════════════════

def _somme_reference(n: int = 20_000) -> list[float]:
    """Valeurs de feature 'somme' d'une baseline random uniforme (≥10 bins)."""
    baseline = generate_random_baseline(n=n, num_max=49, k=5, seed=DEFAULT_RANDOM_SEED)
    return [b["somme"] for b in baseline]


def _chance_reference(n: int = 100_000) -> list[float]:
    """Overlaps chance_in_T1 d'une baseline appariée (petit univers 2 bins, P(1)=0.1)."""
    baseline = generate_secondary_in_t1_baseline(
        n=n, sec_min=1, sec_max=10, count=1, seed=DEFAULT_RANDOM_SEED,
    )
    return [b["chance_in_T1"] for b in baseline]


# ════════════════════════════════════════════════════════════════════════
# compute_noise_floor — cœur générique
# ════════════════════════════════════════════════════════════════════════

class TestComputeNoiseFloorCore:

    def test_returns_all_expected_keys(self):
        ref = _somme_reference()
        bins = build_bins("somme")
        res = compute_noise_floor(ref, bins, n_samples=2000, observed_jsd=0.05, k=300)
        for key in (
            "noise_floor", "p99_null", "mean_null", "std_null", "p_value",
            "k", "n_samples", "n_reference", "quantile", "base",
        ):
            assert key in res, f"clé manquante : {key}"
        assert res["k"] == 300
        assert res["n_samples"] == 2000
        assert res["n_reference"] == len(ref)

    def test_reproducibility_same_seed(self):
        ref = _somme_reference()
        bins = build_bins("somme")
        a = compute_noise_floor(ref, bins, n_samples=2000, observed_jsd=0.05, k=500, seed=7)
        b = compute_noise_floor(ref, bins, n_samples=2000, observed_jsd=0.05, k=500, seed=7)
        assert a == b  # déterminisme total (RNG local seedé)

    def test_different_seeds_differ(self):
        ref = _somme_reference()
        bins = build_bins("somme")
        a = compute_noise_floor(ref, bins, n_samples=2000, observed_jsd=0.05, k=500, seed=1)
        b = compute_noise_floor(ref, bins, n_samples=2000, observed_jsd=0.05, k=500, seed=2)
        assert a["noise_floor"] != b["noise_floor"]

    def test_noise_floor_in_bounds(self):
        ref = _somme_reference()
        bins = build_bins("somme")
        res = compute_noise_floor(ref, bins, n_samples=2000, observed_jsd=0.05, k=500)
        assert 0.0 < res["noise_floor"] <= _LN2
        assert res["mean_null"] >= 0.0

    def test_p99_ge_noise_floor_95(self):
        ref = _somme_reference()
        bins = build_bins("somme")
        res = compute_noise_floor(ref, bins, n_samples=2000, observed_jsd=0.05, k=1000)
        assert res["p99_null"] >= res["noise_floor"]

    def test_monotonicity_smaller_n_higher_floor(self):
        # Plus l'échantillon HYBRIDE est petit, plus le bruit (donc le plancher) est grand.
        ref = _somme_reference()
        bins = build_bins("somme")
        floor_small = compute_noise_floor(ref, bins, n_samples=100, observed_jsd=0.0, k=1000, seed=3)
        floor_large = compute_noise_floor(ref, bins, n_samples=5000, observed_jsd=0.0, k=1000, seed=3)
        assert floor_small["noise_floor"] > floor_large["noise_floor"]

    def test_p_value_addone_bounds(self):
        # Convention add-one : p ∈ [1/(K+1), 1], jamais 0.0 strict.
        ref = _somme_reference()
        bins = build_bins("somme")
        k = 500
        res = compute_noise_floor(ref, bins, n_samples=2000, observed_jsd=0.0, k=k)
        assert res["p_value"] <= 1.0
        assert res["p_value"] >= 1.0 / (k + 1) - 1e-9

    def test_p_value_addone_floor_when_observed_dominates(self):
        # JSD observé énorme → aucune réplique nulle ≥ → p = 1/(K+1) (jamais 0).
        ref = _somme_reference()
        bins = build_bins("somme")
        k = 500
        res = compute_noise_floor(ref, bins, n_samples=2000, observed_jsd=10.0, k=k)
        assert res["p_value"] == pytest.approx(round(1.0 / (k + 1), 6))

    def test_p_value_high_when_observed_is_typical_null(self):
        # Observé = moyenne de la loi nulle (pas de signal) → p modérée, NON matériel.
        ref = _somme_reference()
        bins = build_bins("somme")
        base = compute_noise_floor(ref, bins, n_samples=2000, observed_jsd=0.0, k=2000, seed=11)
        typical = base["mean_null"]
        res = compute_noise_floor(ref, bins, n_samples=2000, observed_jsd=typical, k=2000, seed=11)
        assert 0.1 < res["p_value"] < 0.9

    # ── Gardes d'entrée ──────────────────────────────────────────────
    def test_empty_reference_raises(self):
        with pytest.raises(ValueError):
            compute_noise_floor([], build_bins("somme"), n_samples=100, observed_jsd=0.05)

    def test_non_positive_n_samples_raises(self):
        ref = _somme_reference()
        with pytest.raises(ValueError):
            compute_noise_floor(ref, build_bins("somme"), n_samples=0, observed_jsd=0.05)

    def test_non_positive_k_raises(self):
        ref = _somme_reference()
        with pytest.raises(ValueError):
            compute_noise_floor(ref, build_bins("somme"), n_samples=100, observed_jsd=0.05, k=0)

    def test_invalid_base_raises(self):
        ref = _somme_reference()
        with pytest.raises(ValueError):
            compute_noise_floor(ref, build_bins("somme"), n_samples=100, observed_jsd=0.05, base="10")


# ════════════════════════════════════════════════════════════════════════
# compute_noise_floor — petit univers (secondaire 2-3 bins)
# ════════════════════════════════════════════════════════════════════════

class TestComputeNoiseFloorSmallUniverse:

    def test_chance_in_t1_floor_positive_and_bounded(self):
        ref = _chance_reference()
        bins = build_secondary_bins("chance_in_T1")
        res = compute_noise_floor(ref, bins, n_samples=20_000, observed_jsd=0.0, k=10_000)
        assert 0.0 < res["noise_floor"] <= _LN2

    def test_small_universe_quantile_stable_across_seeds(self):
        # Petit univers (2 bins) : K=10000 doit lisser le quantile 95% → 2 seeds proches.
        ref = _chance_reference()
        bins = build_secondary_bins("chance_in_T1")
        f1 = compute_noise_floor(ref, bins, n_samples=20_000, observed_jsd=0.0, k=10_000, seed=1)["noise_floor"]
        f2 = compute_noise_floor(ref, bins, n_samples=20_000, observed_jsd=0.0, k=10_000, seed=2)["noise_floor"]
        assert f1 > 0 and f2 > 0
        rel = abs(f1 - f2) / max(f1, f2)
        assert rel < 0.30, f"quantile instable entre seeds : f1={f1}, f2={f2}, rel={rel:.3f}"

    def test_etoiles_in_t1_three_bins(self):
        baseline = generate_secondary_in_t1_baseline(
            n=100_000, sec_min=1, sec_max=12, count=2, seed=DEFAULT_RANDOM_SEED,
        )
        ref = [b["etoiles_in_T1"] for b in baseline]
        bins = build_secondary_bins("etoiles_in_T1")
        res = compute_noise_floor(ref, bins, n_samples=20_000, observed_jsd=0.0, k=10_000)
        assert 0.0 < res["noise_floor"] <= _LN2


# ════════════════════════════════════════════════════════════════════════
# apply_fdr_correction — Benjamini-Hochberg
# ════════════════════════════════════════════════════════════════════════

class TestApplyFDR:

    def test_empty_returns_empty(self):
        assert apply_fdr_correction({}) == {}

    def test_single_feature_equals_simple_threshold(self):
        # m=1 : seuil BH = (1/1)*alpha = alpha.
        below = apply_fdr_correction({"a": 0.04}, alpha=0.05)
        above = apply_fdr_correction({"a": 0.06}, alpha=0.05)
        assert below["a"]["is_material_fdr"] is True
        assert below["a"]["bh_threshold"] == pytest.approx(0.05)
        assert above["a"]["is_material_fdr"] is False

    def test_all_significant(self):
        res = apply_fdr_correction({"a": 0.001, "b": 0.002, "c": 0.0005}, alpha=0.05)
        assert all(v["is_material_fdr"] for v in res.values())

    def test_none_significant(self):
        res = apply_fdr_correction({"a": 0.5, "b": 0.6, "c": 0.9}, alpha=0.05)
        assert not any(v["is_material_fdr"] for v in res.values())

    def test_stepup_rejects_middle_failing_its_own_threshold(self):
        # m=4, alpha=0.05. Seuils rang : 0.0125 / 0.025 / 0.0375 / 0.05.
        # p triés : 0.001, 0.03, 0.035, 0.5.
        # rang3 (0.035 ≤ 0.0375) ✓ → step-up rejette AUSSI rang2 (0.03 > 0.025).
        pvals = {"a": 0.001, "b": 0.03, "c": 0.035, "d": 0.5}
        res = apply_fdr_correction(pvals, alpha=0.05)
        assert res["a"]["is_material_fdr"] is True
        assert res["b"]["is_material_fdr"] is True   # ← subtilité step-up
        assert res["c"]["is_material_fdr"] is True
        assert res["d"]["is_material_fdr"] is False

    def test_bh_threshold_values_per_rank(self):
        pvals = {"a": 0.001, "b": 0.03, "c": 0.035, "d": 0.5}
        res = apply_fdr_correction(pvals, alpha=0.05)
        assert res["a"]["bh_threshold"] == pytest.approx((1 / 4) * 0.05)
        assert res["b"]["bh_threshold"] == pytest.approx((2 / 4) * 0.05)
        assert res["c"]["bh_threshold"] == pytest.approx((3 / 4) * 0.05)
        assert res["d"]["bh_threshold"] == pytest.approx((4 / 4) * 0.05)

    def test_bh_less_strict_than_bonferroni(self):
        # Même jeu : BH rejette 3, Bonferroni (alpha/m) n'en rejette qu'1.
        pvals = {"a": 0.001, "b": 0.03, "c": 0.035, "d": 0.5}
        alpha = 0.05
        m = len(pvals)
        res = apply_fdr_correction(pvals, alpha=alpha)
        n_bh = sum(1 for v in res.values() if v["is_material_fdr"])
        n_bonf = sum(1 for p in pvals.values() if p <= alpha / m)
        assert n_bh == 3
        assert n_bonf == 1
        assert n_bh > n_bonf

    def test_tie_pvalues_deterministic(self):
        # Ex-aequo → tri secondaire sur le nom → sortie reproductible.
        pvals = {"b": 0.01, "a": 0.01, "c": 0.01}
        r1 = apply_fdr_correction(pvals, alpha=0.05)
        r2 = apply_fdr_correction(dict(pvals), alpha=0.05)
        assert r1 == r2

    def test_invalid_alpha_raises(self):
        with pytest.raises(ValueError):
            apply_fdr_correction({"a": 0.01}, alpha=0.0)
        with pytest.raises(ValueError):
            apply_fdr_correction({"a": 0.01}, alpha=1.5)


# ════════════════════════════════════════════════════════════════════════
# RNG — pas de pollution du générateur global (seed LOCAL uniquement)
# ════════════════════════════════════════════════════════════════════════

class TestRNGIsolation:

    def test_numpy_global_state_not_mutated(self):
        np.random.seed(12345)
        state_before = np.random.get_state()
        ref = _somme_reference()
        compute_noise_floor(ref, build_bins("somme"), n_samples=1000, observed_jsd=0.05, k=200)
        state_after = np.random.get_state()
        assert state_before[0] == state_after[0]
        assert np.array_equal(state_before[1], state_after[1])
        assert state_before[2:] == state_after[2:]

    def test_stdlib_random_state_not_mutated(self):
        _stdlib_random.seed(999)
        before = _stdlib_random.getstate()
        ref = _somme_reference()
        compute_noise_floor(ref, build_bins("somme"), n_samples=1000, observed_jsd=0.05, k=200)
        after = _stdlib_random.getstate()
        assert before == after
