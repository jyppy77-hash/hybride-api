"""Tests V_X.F LOT 1 — tools/signature_features.py briques de base.

Tests purs en mémoire — pas de DB, pas de fixture lourde.
"""
import math
import random as _stdlib_random

import numpy as np
import pytest

from tools.signature_features import (
    FEATURE_NAMES,
    _histogram_normalize,
    _kl_divergence,
    build_bins,
    compute_feature_jsd,
    extract_features,
    generate_random_baseline,
)


# ════════════════════════════════════════════════════════════════════════
# Brique 1 — extract_features
# ════════════════════════════════════════════════════════════════════════

class TestExtractFeatures:

    def test_basic_grid_loto(self):
        # Grille {1, 12, 23, 34, 45} sur 49
        # Somme = 115, dispersion = 44, freq_1_31 = 3, pairs = 2 (12, 34)
        # ESI : gaps 10,10,10,10 → 100×4=400 ; wrap (1-1+49-45)²=16 → ESI=416
        grille = {"nums": [1, 12, 23, 34, 45]}
        feat = extract_features(grille, num_max=49)
        assert feat["somme"] == 115.0
        assert feat["dispersion"] == 44.0
        # std : mean=23, var = ((22²+11²+0+11²+22²)/4) = 302.5 → stdev ≈ 17.39
        assert feat["std"] == pytest.approx(math.sqrt(302.5), rel=1e-6)
        assert feat["freq_1_31"] == 3.0
        assert feat["nb_pairs"] == 2.0
        assert feat["nb_consecutifs"] == 0.0
        assert feat["esi"] == 416.0

    def test_basic_grid_em(self):
        # Grille {1, 13, 25, 37, 49} sur 50
        # gaps 11,11,11,11 → 121×4=484 ; wrap (0+1)²=1 → ESI=485
        grille = {"nums": [1, 13, 25, 37, 49]}
        feat = extract_features(grille, num_max=50)
        assert feat["somme"] == 125.0
        assert feat["dispersion"] == 48.0
        assert feat["freq_1_31"] == 3.0
        assert feat["nb_pairs"] == 0.0
        assert feat["nb_consecutifs"] == 0.0
        assert feat["esi"] == 485.0

    def test_consecutive_pairs_counted(self):
        # {1, 2, 3, 10, 20} → 2 paires consécutives (1-2, 2-3)
        feat = extract_features({"nums": [1, 2, 3, 10, 20]}, num_max=49)
        assert feat["nb_consecutifs"] == 2.0
        # 4 consécutifs → 3 paires
        feat2 = extract_features({"nums": [1, 2, 3, 4, 20]}, num_max=49)
        assert feat2["nb_consecutifs"] == 3.0

    def test_unsorted_input_normalized(self):
        feat_a = extract_features({"nums": [45, 1, 34, 12, 23]}, num_max=49)
        feat_b = extract_features({"nums": [1, 12, 23, 34, 45]}, num_max=49)
        assert feat_a == feat_b

    def test_missing_nums_key_raises_KeyError(self):
        with pytest.raises(KeyError):
            extract_features({"foo": "bar"}, num_max=49)

    def test_wrong_length_raises_ValueError(self):
        with pytest.raises(ValueError, match="expected 5"):
            extract_features({"nums": [1, 2, 3]}, num_max=49)

    def test_returns_all_feature_names(self):
        feat = extract_features({"nums": [1, 12, 23, 34, 45]}, num_max=49)
        assert set(feat.keys()) == set(FEATURE_NAMES)

    def test_esi_uses_correct_universe(self):
        # Même grille, num_max différent → ESI wrap term différent
        grille = {"nums": [1, 12, 23, 34, 45]}
        esi_loto = extract_features(grille, num_max=49)["esi"]
        esi_em = extract_features(grille, num_max=50)["esi"]
        # wrap Loto = (0 + 49-45)² = 16, EM = (0 + 50-45)² = 25 → diff = 9
        assert esi_em - esi_loto == 9.0


# ════════════════════════════════════════════════════════════════════════
# Brique 2 — generate_random_baseline
# ════════════════════════════════════════════════════════════════════════

class TestRandomBaseline:

    def test_size_matches_n(self):
        baseline = generate_random_baseline(n=100, num_max=49, k=5, seed=42)
        assert len(baseline) == 100

    def test_returns_immutable_tuple(self):
        baseline = generate_random_baseline(n=10, num_max=49, k=5, seed=42)
        assert isinstance(baseline, tuple)
        # tuple n'a pas .append → AttributeError
        with pytest.raises(AttributeError):
            baseline.append({"nums": [1, 2, 3, 4, 5]})

    def test_reproducibility_same_seed_same_object(self):
        a = generate_random_baseline(n=50, num_max=49, k=5, seed=42)
        b = generate_random_baseline(n=50, num_max=49, k=5, seed=42)
        # lru_cache → même objet physique
        assert a is b

    def test_different_seeds_different_outputs(self):
        a = generate_random_baseline(n=50, num_max=49, k=5, seed=42)
        b = generate_random_baseline(n=50, num_max=49, k=5, seed=99)
        # Probabilité d'égalité fortuite ~ 0
        assert a != b

    def test_features_in_expected_ranges_loto(self):
        baseline = generate_random_baseline(n=500, num_max=49, k=5, seed=42)
        for feat in baseline:
            assert 15 <= feat["somme"] <= 235  # 5/49 bounds
            assert 4 <= feat["dispersion"] <= 48
            assert 0 <= feat["freq_1_31"] <= 5
            assert 0 <= feat["nb_pairs"] <= 5
            assert 0 <= feat["nb_consecutifs"] <= 4
            assert 0 <= feat["esi"] <= 1936  # max Loto = 44²
            assert feat["std"] >= 0

    def test_em_universe_50(self):
        baseline = generate_random_baseline(n=200, num_max=50, k=5, seed=42)
        max_somme = max(f["somme"] for f in baseline)
        # 5/50 max somme = 240
        assert max_somme <= 240


# ════════════════════════════════════════════════════════════════════════
# Brique 3 — compute_feature_jsd + helpers
# ════════════════════════════════════════════════════════════════════════

class TestComputeFeatureJsd:

    def test_identity_zero(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0, 100.0, 150.0]
        bins = build_bins("somme")
        jsd = compute_feature_jsd(values, values, bins)
        assert jsd < 1e-6

    def test_symmetry(self):
        a = [10.0, 20.0, 30.0, 40.0, 50.0]
        b = [15.0, 25.0, 35.0, 45.0, 55.0]
        bins = build_bins("somme")
        jsd_ab = compute_feature_jsd(a, b, bins)
        jsd_ba = compute_feature_jsd(b, a, bins)
        assert jsd_ab == pytest.approx(jsd_ba, abs=1e-12)

    def test_bounded_below(self):
        a = [10.0, 20.0, 30.0]
        b = [40.0, 50.0, 60.0]
        bins = build_bins("somme")
        jsd = compute_feature_jsd(a, b, bins)
        assert jsd >= 0.0

    def test_bounded_above_base_e(self):
        # Supports parfaitement disjoints → JSD ≈ log(2)
        bins = build_bins("somme")
        a = [20.0] * 100  # tombe dans le bin [20, 25)
        b = [200.0] * 100  # bin [200, 205)
        jsd = compute_feature_jsd(a, b, bins)
        assert jsd <= math.log(2) + 1e-9

    def test_bounded_above_base_2(self):
        bins = build_bins("somme")
        a = [20.0] * 100
        b = [200.0] * 100
        jsd_b2 = compute_feature_jsd(a, b, bins, base="2")
        assert 0.0 <= jsd_b2 <= 1.0 + 1e-9

    def test_disjoint_supports_near_max(self):
        # JSD doit s'approcher de log(2) si supports disjoints
        bins = build_bins("somme")
        a = [20.0] * 100
        b = [200.0] * 100
        jsd = compute_feature_jsd(a, b, bins)
        # >95% du max théorique log(2)
        assert jsd > math.log(2) * 0.95

    def test_empty_a_no_crash(self):
        bins = build_bins("somme")
        jsd = compute_feature_jsd([], [10.0, 20.0, 30.0], bins)
        assert jsd >= 0.0
        assert jsd <= math.log(2) + 1e-9

    def test_empty_b_no_crash(self):
        bins = build_bins("somme")
        jsd = compute_feature_jsd([10.0, 20.0, 30.0], [], bins)
        assert jsd >= 0.0

    def test_invalid_base_raises(self):
        bins = build_bins("somme")
        with pytest.raises(ValueError, match="base must be"):
            compute_feature_jsd([10.0], [20.0], bins, base="10")

    def test_esi_log_binning_jsd_stable(self):
        # Sur ESI (queue longue), JSD reste finie et bornée
        bins = build_bins("esi")
        a = list(np.random.RandomState(0).randint(0, 2000, size=1000))
        b = list(np.random.RandomState(1).randint(0, 2000, size=1000))
        jsd = compute_feature_jsd(a, b, bins)
        assert 0.0 <= jsd <= math.log(2) + 1e-9


# ════════════════════════════════════════════════════════════════════════
# Brique 4 — build_bins
# ════════════════════════════════════════════════════════════════════════

class TestBuildBins:

    def test_somme_bins(self):
        bins = build_bins("somme")
        assert bins[0] == 15
        assert bins[-1] == 245
        assert bins[1] - bins[0] == 5  # bin width = 5

    def test_dispersion_bins(self):
        bins = build_bins("dispersion")
        assert bins[0] == 4
        assert bins[-1] == 50

    def test_freq_1_31_unit_bins(self):
        bins = build_bins("freq_1_31")
        assert list(bins) == [0, 1, 2, 3, 4, 5, 6]

    def test_nb_pairs_unit_bins(self):
        bins = build_bins("nb_pairs")
        assert list(bins) == [0, 1, 2, 3, 4, 5, 6]

    def test_nb_consecutifs_bins(self):
        bins = build_bins("nb_consecutifs")
        assert list(bins) == [0, 1, 2, 3, 4, 5]

    def test_std_bins(self):
        bins = build_bins("std")
        assert bins[0] == 0
        assert bins[-1] == 30
        assert bins[1] - bins[0] == 1.0

    def test_esi_log_binning(self):
        bins = build_bins("esi")
        # Premier edge = 0 (capture ESI=0)
        assert bins[0] == 0.0
        # Second edge ≈ 1.0 (début geomspace)
        assert bins[1] == pytest.approx(1.0, rel=1e-9)
        # Couvre ≥ 2025 (max EM)
        assert bins[-1] >= 2025.0
        # Croissance monotone stricte
        assert all(bins[i] < bins[i + 1] for i in range(len(bins) - 1))

    def test_unknown_feature_raises(self):
        with pytest.raises(ValueError, match="not in FEATURE_NAMES"):
            build_bins("foobar")

    def test_loto_em_same_bins_for_shared_features(self):
        # Bins identiques pour features non-num_max-dépendantes
        for fname in ("somme", "dispersion", "freq_1_31", "nb_pairs",
                      "nb_consecutifs", "std"):
            assert np.array_equal(
                build_bins(fname, num_max=49),
                build_bins(fname, num_max=50),
            )


# ════════════════════════════════════════════════════════════════════════
# Helpers privés
# ════════════════════════════════════════════════════════════════════════

class TestPrivateHelpers:

    def test_histogram_normalize_sums_to_one(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        bins = np.array([0, 25, 50, 75, 100], dtype=float)
        p = _histogram_normalize(values, bins)
        assert p.sum() == pytest.approx(1.0, abs=1e-9)

    def test_histogram_normalize_empty_uniform(self):
        bins = np.array([0, 25, 50, 75, 100], dtype=float)
        p = _histogram_normalize([], bins)
        # 4 bins → uniforme 0.25
        assert all(x == pytest.approx(0.25) for x in p)

    def test_histogram_normalize_invalid_bins(self):
        with pytest.raises(ValueError, match="at least 2 edges"):
            _histogram_normalize([1.0], np.array([5.0]))

    def test_kl_divergence_identity_zero(self):
        p = np.array([0.25, 0.25, 0.25, 0.25])
        assert _kl_divergence(p, p) == pytest.approx(0.0, abs=1e-12)


# ════════════════════════════════════════════════════════════════════════
# Sanity end-to-end : signature détectable sur synthétique
# ════════════════════════════════════════════════════════════════════════

class TestEndToEndSanity:

    def test_hybride_synthetic_vs_random_has_dispersion_signature(self):
        """Sanity : grilles synthétiques 1-par-zone (HYBRIDE-like)
        doivent avoir une JSD non-nulle sur 'dispersion' vs random pur.
        """
        rng = _stdlib_random.Random(2026)
        hybride_disp: list[float] = []
        zones = [(1, 10), (11, 20), (21, 30), (31, 40), (41, 49)]
        for _ in range(500):
            grille = [rng.randint(lo, hi) for lo, hi in zones]
            feat = extract_features({"nums": grille}, num_max=49)
            hybride_disp.append(feat["dispersion"])

        baseline = generate_random_baseline(n=5000, num_max=49, k=5, seed=42)
        random_disp = [f["dispersion"] for f in baseline]

        bins = build_bins("dispersion")
        jsd = compute_feature_jsd(hybride_disp, random_disp, bins)
        # 1-par-zone biaise dispersion vers haut → JSD substantielle
        assert jsd > 0.05, f"signature JSD trop faible : {jsd}"

    def test_random_vs_random_jsd_low(self):
        """Sanity inverse : random vs random (seeds différents) →
        JSD très faible (bruit de sondage seulement).
        """
        a = generate_random_baseline(n=5000, num_max=49, k=5, seed=42)
        b = generate_random_baseline(n=5000, num_max=49, k=5, seed=99)
        a_somme = [f["somme"] for f in a]
        b_somme = [f["somme"] for f in b]
        bins = build_bins("somme")
        jsd = compute_feature_jsd(a_somme, b_somme, bins)
        assert jsd < 0.01, f"random vs random JSD inattendue : {jsd}"
