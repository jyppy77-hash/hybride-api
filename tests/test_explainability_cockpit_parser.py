"""
Tests du parser de l'étage « Empreinte de génération HYBRIDE » (palier 1).
=========================================================================
Couvre services/cockpit_parser.py::_build_explainability et son intégration
dans normalize_run :
  - présent (EM star / Loto chance) → present=True, structures normalisées ;
  - absent (vieux run sans engine_explainability) → present=False (carte masquée) ;
  - _degraded() porte explainability.present=False ;
  - secondaire game-agnostique fusionné (numéro|fréquence|déviation, plage triée) ;
  - GARDE-FOU ANJ : l'encadré « Lecture rapide » ne contient JAMAIS de chiffre.

Pur, sans I/O, sans tools.* (mur étanche). Aucun mock requis.
"""

from services.cockpit_parser import (
    _build_explainability,
    _build_lecture_rapide,
    normalize_run,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _expl_em() -> dict:
    """engine_explainability minimal mais réaliste — EuroMillions (secondaire = étoiles)."""
    return {
        "total_grids": 35000,
        "uniform_expectation_per_number": 1400.0,
        "frequency_by_number": {"1": 700, "2": 2100, "3": 1400, "4": 0, "5": 1800},
        "deviation_from_uniform": {"1": -0.5, "2": 0.5, "3": 0.0, "4": -1.0, "5": 0.2857},
        "deviation_from_uniform_intra_zone": {"1": -0.4, "2": 0.6, "3": 0.0, "4": -1.0, "5": 0.5},
        "top_numbers": [
            {"number": 2, "frequency": 2100, "deviation_from_uniform": 0.5,
             "deviation_from_uniform_intra_zone": 0.6},
            {"number": 5, "frequency": 1800, "deviation_from_uniform": 0.2857,
             "deviation_from_uniform_intra_zone": 0.5},
        ],
        "frequency_by_star": {"1": 5000, "2": 7000, "3": 6000},
        "uniform_expectation_per_secondary": 6000.0,
        "deviation_from_uniform_secondary": {"1": -0.1667, "2": 0.1667, "3": 0.0},
        "top_stars": [
            {"number": 2, "frequency": 7000, "deviation_from_uniform": 0.1667},
            {"number": 3, "frequency": 6000, "deviation_from_uniform": 0.0},
        ],
        "correlation_with_zone": {"1": "1-10", "2": "1-10", "3": "11-20", "4": "11-20", "5": "41-50"},
        "correlation_with_unpopularity": {"1": 1.0, "2": 1.2, "3": 1.0, "4": 0.8, "5": 1.1},
        "correlation_with_hard_exclude": {"1": 0.30, "2": 0.25, "3": 0.10, "4": 0.05, "5": 0.40},
        "correlation_with_persistent_brake": {"1": 0.10, "2": 0.0, "3": 0.05, "4": 0.0, "5": 0.20},
        "n_contexts_with_history": 198,
        "notes": {
            "selection_is_stochastic": "Le score pilote le POIDS de tirage ; choix stochastique.",
            "decay_disabled_in_backtest": True,
            "aggregates_200_contexts": "Cascade de 200 tirages x 100 grilles.",
            "unpopularity_boules_only": True,
        },
    }


def _expl_loto() -> dict:
    """engine_explainability minimal — Loto (secondaire = chance)."""
    return {
        "total_grids": 20000,
        "uniform_expectation_per_number": 2040.0,
        "frequency_by_number": {"1": 1000, "2": 3000, "3": 2040},
        "deviation_from_uniform": {"1": -0.5, "2": 0.47, "3": 0.0},
        "deviation_from_uniform_intra_zone": {"1": -0.4, "2": 0.5, "3": 0.0},
        "top_numbers": [
            {"number": 2, "frequency": 3000, "deviation_from_uniform": 0.47,
             "deviation_from_uniform_intra_zone": 0.5},
        ],
        "frequency_by_chance": {"1": 1900, "2": 2100, "3": 2000},
        "uniform_expectation_per_secondary": 2000.0,
        "deviation_from_uniform_secondary": {"1": -0.05, "2": 0.05, "3": 0.0},
        "top_chance": [
            {"number": 2, "frequency": 2100, "deviation_from_uniform": 0.05},
        ],
        "correlation_with_zone": {"1": "1-10", "2": "1-10", "3": "11-20"},
        "correlation_with_unpopularity": {"1": 1.0, "2": 1.1, "3": 1.0},
        "correlation_with_hard_exclude": {"1": 0.02, "2": 0.03, "3": 0.01},
        "correlation_with_persistent_brake": {"1": 0.0, "2": 0.0, "3": 0.0},
        "n_contexts_with_history": 0,
        "notes": {"decay_disabled_in_backtest": True, "unpopularity_boules_only": True},
    }


def _run(expl: dict | None) -> dict:
    """Enveloppe un engine_explainability dans un JSON de run exploitable."""
    rca = {"tier1": {}, "tier2": {}}
    if expl is not None:
        rca["engine_explainability"] = expl
    return {
        "metadata": {"game": "em", "run_mode": "single_no_compare"},
        "results_config_actuelle": rca,
    }


# ── Présence / structure ──────────────────────────────────────────────────────

class TestExplainabilityPresent:
    def test_present_true_em(self):
        e = _build_explainability(_run(_expl_em())["results_config_actuelle"])
        assert e["present"] is True
        assert e["total_grids"] == 35000.0
        assert e["uniform_expectation_per_number"] == 1400.0

    def test_chart_arrays_aligned_and_sorted(self):
        e = _build_explainability(_run(_expl_em())["results_config_actuelle"])
        assert e["chart_numbers"] == [1, 2, 3, 4, 5]
        assert len(e["chart_deviation_intra_zone"]) == len(e["chart_numbers"])
        assert len(e["chart_deviation_global"]) == len(e["chart_numbers"])
        assert len(e["chart_zones"]) == len(e["chart_numbers"])
        assert e["chart_zones"] == ["1-10", "1-10", "11-20", "11-20", "41-50"]

    def test_ordered_zones_sorted_by_low_bound(self):
        e = _build_explainability(_run(_expl_em())["results_config_actuelle"])
        assert e["ordered_zones"] == ["1-10", "11-20", "41-50"]

    def test_top_numbers_enriched_with_zone(self):
        e = _build_explainability(_run(_expl_em())["results_config_actuelle"])
        assert e["top_numbers"][0]["number"] == 2
        assert e["top_numbers"][0]["zone"] == "1-10"
        assert e["top_numbers"][1]["zone"] == "41-50"

    def test_notes_passthrough(self):
        e = _build_explainability(_run(_expl_em())["results_config_actuelle"])
        assert e["notes"]["decay_disabled_in_backtest"] is True
        assert "stochastique" in e["notes"]["selection_is_stochastic"]


# ── Secondaire game-agnostique (mini-table fusionnée) ─────────────────────────

class TestSecondaryNormalization:
    def test_em_secondary_label_star(self):
        e = _build_explainability(_run(_expl_em())["results_config_actuelle"])
        assert e["secondary_label"] == "star"

    def test_loto_secondary_label_chance(self):
        e = _build_explainability(_run(_expl_loto())["results_config_actuelle"])
        assert e["secondary_label"] == "chance"

    def test_secondary_rows_merge_freq_and_deviation_em(self):
        e = _build_explainability(_run(_expl_em())["results_config_actuelle"])
        rows = e["secondary_rows"]
        assert [r["number"] for r in rows] == [1, 2, 3]      # trié croissant
        assert rows[1]["frequency"] == 7000                  # frequency_by_star["2"]
        assert rows[1]["deviation_from_uniform"] == 0.1667

    def test_secondary_rows_merge_freq_and_deviation_loto(self):
        e = _build_explainability(_run(_expl_loto())["results_config_actuelle"])
        rows = e["secondary_rows"]
        assert [r["number"] for r in rows] == [1, 2, 3]
        assert rows[1]["frequency"] == 2100                  # frequency_by_chance["2"]


# ── Défensif (vieux run / clé absente / dict vide) ────────────────────────────

class TestExplainabilityDefensive:
    def test_absent_key_present_false(self):
        e = _build_explainability(_run(None)["results_config_actuelle"])
        assert e == {"present": False}

    def test_empty_dict_present_false(self):
        assert _build_explainability({}) == {"present": False}

    def test_normalize_run_includes_explainability(self):
        vm = normalize_run(_run(_expl_em()))
        assert vm["explainability"]["present"] is True
        assert vm["error"] is None

    def test_normalize_run_old_schema_explainability_masked(self):
        vm = normalize_run(_run(None))
        assert vm["explainability"]["present"] is False

    def test_degraded_carries_explainability(self):
        vm = normalize_run({"not_a_run": True})        # pas de results_config_actuelle
        assert vm["error"] is not None
        assert vm["explainability"] == {"present": False}


# ── GARDE-FOU ANJ — encadré « Lecture rapide » : ZÉRO chiffre ─────────────────

class TestLectureRapideAnj:
    def test_lecture_rapide_non_empty_em(self):
        e = _build_explainability(_run(_expl_em())["results_config_actuelle"])
        assert isinstance(e["lecture_rapide"], list)
        assert len(e["lecture_rapide"]) >= 1

    def test_lecture_rapide_contains_no_digit_em(self):
        e = _build_explainability(_run(_expl_em())["results_config_actuelle"])
        for line in e["lecture_rapide"]:
            assert not any(ch.isdigit() for ch in line), f"chiffre interdit dans : {line!r}"

    def test_lecture_rapide_contains_no_digit_loto(self):
        e = _build_explainability(_run(_expl_loto())["results_config_actuelle"])
        for line in e["lecture_rapide"]:
            assert not any(ch.isdigit() for ch in line), f"chiffre interdit dans : {line!r}"

    def test_lecture_rapide_describes_structure_em(self):
        e = _build_explainability(_run(_expl_em())["results_config_actuelle"])
        text = " ".join(e["lecture_rapide"])
        # surpondération localisée par position (zone 41-50 = haut), levier hard-exclude actif
        assert "grille" in text
        assert "exclusion du tirage précédent" in text

    def test_lecture_rapide_brake_inactive_when_all_zero(self):
        e = _build_explainability(_run(_expl_loto())["results_config_actuelle"])
        text = " ".join(e["lecture_rapide"])
        assert "Frein persistant inter-tirages inactif" in text

    def test_lecture_rapide_empty_inputs_no_crash(self):
        assert _build_lecture_rapide({}, [], {}, {}, {}) == []
