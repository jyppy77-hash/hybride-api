"""
Tests du parser cockpit V_X.F — services/cockpit_parser.py::normalize_run.
=========================================================================
Défensif aux schémas partiels (vieux runs réduits) et malformés.

Fixtures INLINE (fidèles au schéma réel des runs OOS V_X.F) car les JSON de
référence sous docs/run OOS/ sont gitignorés → absents en CI. Un test optionnel
charge le vrai fichier stratification_20260606 quand il est présent en local
(skip sinon) pour vérrouiller la valeur JSD réelle ~0.596738.
"""

import json
import os

import pytest

from services.cockpit_parser import normalize_run

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REAL_FULL = os.path.join(_REPO, "docs", "run OOS", "stratification_20260606", "loto_200.json")
_REAL_OLD = os.path.join(_REPO, "docs", "run OOS", "oos_reference_20260529", "loto_200.json")


# ── Fixtures inline ──────────────────────────────────────────────────────

_CONFIG = {
    "saturation_brake_persistent_t1": 0.2,
    "saturation_brake_persistent_t2": 0.5,
    "saturation_persistent_window": 2,
    "saturation_persistent_enabled": True,
}

_TIER1 = {
    "somme": {"n": 20000, "mean": 126.8567, "median": 127.0, "std": 6.2891,
              "min": 107.0, "max": 148.0, "pct_out_of_bounds": 0.0, "bounds": [93, 157]},
    "dispersion": {"n": 20000, "mean": 39.1418, "median": 39.0, "std": 3.7133,
                   "min": 31.0, "max": 48.0, "pct_below_min": 0.0, "min_threshold": 15},
    "std": {"n": 20000, "mean": 15.7709, "median": 15.7892, "std": 1.3262,
            "min": 11.649, "max": 19.6291},
    "nb_consecutifs": {"n": 20000, "mean": 0.0498, "median": 0.0, "std": 0.2197,
                       "min": 0.0, "max": 2.0, "pct_above_max": 0.0, "max_threshold": 2},
    "esi": {"n": 20000, "mean": 466.0702, "median": 458.0, "std": 47.5631,
            "min": 388.0, "max": 694.0, "pct_out_of_bounds": 0.0, "bounds": [20, 750]},
}

_PRIMARY_JSD = {
    "somme": 0.298642, "dispersion": 0.160111, "std": 0.186701, "freq_1_31": 0.187157,
    "nb_pairs": 0.018032, "nb_consecutifs": 0.084001, "esi": 0.283955,
}

_NF_ENTRY = {"p99_null": 0.0004, "mean_null": 0.0002, "std_null": 5e-05,
             "k": 1000, "n_samples": 20000, "n_reference": 100000, "quantile": 0.95, "base": "e"}

_DISCLAIMER = (
    "Le recouvrement avec le tirage T-1 mesure un artefact de construction du moteur "
    "(hard-exclude/brake des numeros recents), PAS un biais du jeu ni une probabilite de gain. "
    "Un creux sous le hasard = signature de la rotation anti-repetition, neutre."
)


def _full_run():
    """Run complet : metadata + tier1 + tier2 (primary + secondary + stratification
    + noise_floor + is_material + effect_tier) + diff. single_no_compare."""
    return {
        "metadata": {
            "harness_version": "v1.0", "run_at": "2026-06-06T11:25:46Z",
            "game": "loto", "n_tirages": 200, "n_grilles_per_tirage": 100,
            "mode": "balanced", "run_mode": "single_no_compare",
            "include_secondary": True, "noise_floor": True,
            "tirages_replayed_range": {"first": "2025-02-24", "last": "2026-06-03"},
            "elapsed_seconds": 103.98,
            "limitations_mvp": ["future_leak_calculer_scores_hybrides_accepted",
                                "decay_state_disabled"],
        },
        "config_actuelle": dict(_CONFIG),
        "config_test": dict(_CONFIG),
        "results_config_actuelle": {
            "tier1": _TIER1,
            "tier2": {
                "feature_jsd": dict(_PRIMARY_JSD),
                "secondary": {
                    "feature_jsd": {"chance_in_T1": 0.036273, "chance_value": 0.007159},
                    "anj_disclaimer": _DISCLAIMER,
                },
                "stratification": {
                    "feature_jsd": {"stratification": 0.596738},
                    "hybride_distribution": {"1_per_zone": 1.0, "2_in_one_zone": 0.0,
                                             "3_in_one_zone": 0.0, "libre": 0.0},
                    "baseline_distribution": {"1_per_zone": 0.0473, "2_in_one_zone": 0.7127,
                                              "3_in_one_zone": 0.2188, "libre": 0.0211},
                    "real_distribution": {"1_per_zone": 0.03, "2_in_one_zone": 0.75,
                                          "3_in_one_zone": 0.185, "libre": 0.035},
                },
                "noise_floor": {
                    "somme": {"noise_floor": 0.000374, "p_value": 0.000999, **_NF_ENTRY},
                    "dispersion": {"noise_floor": 0.00038, "p_value": 0.000999, **_NF_ENTRY},
                    "std": {"noise_floor": 0.000233, "p_value": 0.000999, **_NF_ENTRY},
                    "freq_1_31": {"noise_floor": 7.3e-05, "p_value": 0.000999, **_NF_ENTRY},
                    "nb_pairs": {"noise_floor": 6.9e-05, "p_value": 0.000999, **_NF_ENTRY},
                    "nb_consecutifs": {"noise_floor": 5.3e-05, "p_value": 0.000999, **_NF_ENTRY},
                    "esi": {"noise_floor": 7.8e-05, "p_value": 0.000999, **_NF_ENTRY},
                    "chance_in_T1": {"noise_floor": 2.3e-05, "p_value": 0.0001, **_NF_ENTRY},
                    "chance_value": {"noise_floor": 0.000105, "p_value": 0.0001, **_NF_ENTRY},
                    "stratification": {"noise_floor": 4.8e-05, "p_value": 0.0001, **_NF_ENTRY},
                },
                "is_material": {
                    "somme": True, "dispersion": True, "std": True, "freq_1_31": True,
                    "nb_pairs": True, "nb_consecutifs": True, "esi": True,
                    "chance_in_T1": True, "chance_value": True, "stratification": True,
                },
                "effect_tier": {
                    "somme": "materiel_fort", "dispersion": "materiel_fort",
                    "std": "materiel_fort", "freq_1_31": "materiel_fort",
                    "nb_pairs": "materiel_negligeable", "nb_consecutifs": "materiel_fort",
                    "esi": "materiel_fort", "chance_in_T1": "materiel_fort",
                    "chance_value": "materiel_negligeable", "stratification": "materiel_fort",
                },
            },
        },
        "stratification_distribution_real_empirical": {
            "1_per_zone": 0.03, "2_in_one_zone": 0.75, "3_in_one_zone": 0.185, "libre": 0.035,
        },
        "diff": {
            "delta_gagnantes_pct_global": 0.0,
            "delta_stratification": {"1_per_zone": 0.0, "2_in_one_zone": 0.0,
                                     "3_in_one_zone": 0.0, "libre": 0.0},
        },
    }


def _partial_old_run():
    """Vieux run réduit : metadata + tier1 + tier2.feature_jsd seulement.
    Pas de secondary, stratification, noise_floor, is_material, effect_tier."""
    return {
        "metadata": {
            "harness_version": "v1.0", "game": "loto", "n_tirages": 200,
            "n_grilles_per_tirage": 100, "mode": "balanced",
            "run_mode": "single_no_compare", "include_secondary": False,
            "noise_floor": False,
            "tirages_replayed_range": {"first": "2025-01-01", "last": "2026-05-28"},
            "elapsed_seconds": 88.0, "limitations_mvp": [],
        },
        "config_actuelle": dict(_CONFIG),
        "config_test": dict(_CONFIG),
        "results_config_actuelle": {
            "tier1": _TIER1,
            "tier2": {"feature_jsd": dict(_PRIMARY_JSD)},
        },
        "diff": {"delta_gagnantes_pct_global": 0.0},
    }


def _comparative_run():
    """Run comparatif : run_mode != single_no_compare ET configs différentes."""
    run = _full_run()
    run["metadata"]["run_mode"] = "compare_morning_vs_evening"
    run["config_test"] = dict(_CONFIG)
    run["config_test"]["saturation_brake_persistent_t1"] = 0.35  # diffère de config_actuelle
    run["diff"]["delta_gagnantes_pct_global"] = 0.42
    return run


# ── TestNormalizeFullRun ─────────────────────────────────────────────────

class TestNormalizeFullRun:
    """Run complet → 4 étages present=True, jointures correctes."""

    def setup_method(self):
        self.vm = normalize_run(_full_run())

    def test_no_error(self):
        assert self.vm["error"] is None

    def test_all_stages_present(self):
        assert self.vm["meta"]["present"] is True
        assert self.vm["signature"]["present"] is True
        assert self.vm["conformity"]["present"] is True
        assert self.vm["stratification"]["present"] is True
        assert self.vm["secondary"]["present"] is True

    def test_meta_fields(self):
        m = self.vm["meta"]
        assert m["game"] == "loto"
        assert m["n_tirages"] == 200
        assert m["n_grilles_per_tirage"] == 100
        assert m["mode"] == "balanced"
        assert m["run_mode"] == "single_no_compare"
        assert m["harness_version"] == "v1.0"
        assert m["tirages_range"] == {"first": "2025-02-24", "last": "2026-06-03"}
        assert m["limitations_mvp"] == ["future_leak_calculer_scores_hybrides_accepted",
                                        "decay_state_disabled"]

    def test_signature_has_10_rows(self):
        # 7 primary + 2 secondary + 1 stratification
        assert len(self.vm["signature"]["rows"]) == 10

    def test_stratification_in_head_of_signature(self):
        first = self.vm["signature"]["rows"][0]
        assert first["feature"] == "stratification"
        assert first["family"] == "stratification"
        assert first["jsd"] == pytest.approx(0.596738)

    def test_signature_joins(self):
        strat = self.vm["signature"]["rows"][0]
        assert strat["effect_tier"] == "materiel_fort"
        assert strat["is_material"] is True
        assert strat["noise_floor"] == pytest.approx(4.8e-05)
        assert strat["p_value"] == pytest.approx(0.0001)

    def test_secondary_disclaimer_verbatim(self):
        assert self.vm["secondary"]["anj_disclaimer"] == _DISCLAIMER

    def test_stratification_block(self):
        st = self.vm["stratification"]
        assert st["jsd"] == pytest.approx(0.596738)
        assert st["hybride"]["1_per_zone"] == 1.0
        assert st["baseline"]["2_in_one_zone"] == 0.7127
        assert st["real"]["3_in_one_zone"] == 0.185

    def test_not_comparative(self):
        assert self.vm["is_comparative"] is False
        assert self.vm["diff"]["present"] is False


# ── TestNormalizePartialOldRun ───────────────────────────────────────────

class TestNormalizePartialOldRun:
    """Vieux run réduit → étages manquants masqués, aucun crash."""

    def setup_method(self):
        self.vm = normalize_run(_partial_old_run())

    def test_no_error_no_crash(self):
        assert self.vm["error"] is None

    def test_missing_stages_absent(self):
        assert self.vm["secondary"]["present"] is False
        assert self.vm["stratification"]["present"] is False

    def test_primary_signature_still_present(self):
        assert self.vm["signature"]["present"] is True
        assert len(self.vm["signature"]["rows"]) == 7
        assert all(r["family"] == "primary" for r in self.vm["signature"]["rows"])

    def test_joins_are_none_when_absent(self):
        for r in self.vm["signature"]["rows"]:
            assert r["effect_tier"] is None
            assert r["noise_floor"] is None
            assert r["p_value"] is None
            assert r["is_material"] is None

    def test_conformity_present(self):
        assert self.vm["conformity"]["present"] is True
        assert len(self.vm["conformity"]["rows"]) == 5


# ── TestNormalizeMalformed ───────────────────────────────────────────────

class TestNormalizeMalformed:
    """Schémas malformés → view-model dégradé propre, jamais d'exception."""

    @pytest.mark.parametrize("raw", [{}, {"results_config_actuelle": {}}, None, [], "x", 42])
    def test_degraded_with_error(self, raw):
        vm = normalize_run(raw)
        assert vm["error"] == "schéma non reconnu"
        assert vm["meta"]["present"] is False
        assert vm["signature"]["present"] is False
        assert vm["conformity"]["present"] is False
        assert vm["stratification"]["present"] is False
        assert vm["secondary"]["present"] is False
        assert vm["is_comparative"] is False

    def test_degraded_structure_complete(self):
        vm = normalize_run({})
        # Toutes les clés du view-model présentes même en dégradé
        for key in ("meta", "is_comparative", "signature", "conformity",
                    "stratification", "secondary", "diff", "error"):
            assert key in vm


# ── TestComparativeFlag ──────────────────────────────────────────────────

class TestComparativeFlag:
    """is_comparative = run_mode != single_no_compare ET configs différentes."""

    def test_single_no_compare_is_false(self):
        vm = normalize_run(_full_run())
        assert vm["is_comparative"] is False

    def test_same_configs_is_false_even_if_run_mode_differs(self):
        run = _full_run()
        run["metadata"]["run_mode"] = "compare_ab"  # mais configs identiques
        vm = normalize_run(run)
        assert vm["is_comparative"] is False

    def test_comparative_true_and_diff_present(self):
        vm = normalize_run(_comparative_run())
        assert vm["is_comparative"] is True
        assert vm["diff"]["present"] is True
        assert vm["diff"]["delta_gagnantes_pct_global"] == pytest.approx(0.42)


# ── TestSignatureSorting ─────────────────────────────────────────────────

class TestSignatureSorting:
    """rows triées par JSD strictement décroissant."""

    def test_descending(self):
        rows = normalize_run(_full_run())["signature"]["rows"]
        jsds = [r["jsd"] for r in rows]
        assert jsds == sorted(jsds, reverse=True)

    def test_strat_top_somme_second(self):
        rows = normalize_run(_full_run())["signature"]["rows"]
        assert rows[0]["feature"] == "stratification"   # 0.596738
        assert rows[1]["feature"] == "somme"            # 0.298642


# ── TestConformityPctNormalization ───────────────────────────────────────

class TestConformityPctNormalization:
    """pct_below_min / pct_above_max normalisés vers pct_out_of_bounds."""

    def setup_method(self):
        rows = normalize_run(_full_run())["conformity"]["rows"]
        self.by_feat = {r["feature"]: r for r in rows}

    def test_somme_keeps_out_of_bounds(self):
        assert self.by_feat["somme"]["pct_out_of_bounds"] == 0.0

    def test_dispersion_below_min_mapped(self):
        assert self.by_feat["dispersion"]["pct_out_of_bounds"] == 0.0

    def test_nb_consecutifs_above_max_mapped(self):
        assert self.by_feat["nb_consecutifs"]["pct_out_of_bounds"] == 0.0

    def test_std_no_pct_is_none(self):
        assert self.by_feat["std"]["pct_out_of_bounds"] is None


# ── Tests optionnels sur les vrais fichiers (skip si absents — gitignorés) ─

class TestRealFilesWhenPresent:
    """Verrouille la valeur JSD réelle quand le run de référence est en local."""

    @pytest.mark.skipif(not os.path.exists(_REAL_FULL),
                        reason="run de référence gitignoré (absent en CI)")
    def test_real_full_run_strat_jsd(self):
        with open(_REAL_FULL, encoding="utf-8") as f:
            vm = normalize_run(json.load(f))
        assert vm["error"] is None
        assert vm["stratification"]["present"] is True
        assert vm["stratification"]["jsd"] == pytest.approx(0.596738, abs=1e-6)
        assert vm["signature"]["rows"][0]["feature"] == "stratification"
        assert vm["secondary"]["anj_disclaimer"]  # non vide, verbatim

    @pytest.mark.skipif(not os.path.exists(_REAL_OLD),
                        reason="vieux run gitignoré (absent en CI)")
    def test_real_old_run_no_crash(self):
        with open(_REAL_OLD, encoding="utf-8") as f:
            vm = normalize_run(json.load(f))
        assert vm["error"] is None
        assert vm["signature"]["present"] is True
        assert vm["stratification"]["present"] is False
