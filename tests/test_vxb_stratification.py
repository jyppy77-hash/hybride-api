"""Tests V_X.B — stratification comme dimension de signature (catégorielle).

Prolonge la métrique V_X.F (lots c539a5c / a6c979f / b960af0 / c4d7963).
OFFLINE PUR. Approche (a) : 4 modalités encodées en indices 0-3, bins
STRATIFICATION_BINS [0,1,2,3,4] → compute_feature_jsd + compute_noise_floor
réutilisés tels quels.

Couvre :
    - Équivalence classify_stratification_index <-> _compute_stratification
      (refactor sans régression — test OBLIGATOIRE), 4 catégories + grille vide.
    - Baseline hasard : déterminisme seed, proportions plausibles (1_per_zone
      rare), zones=None -> ValueError, Loto/EM distinctes.
    - _compute_tier2_stratification : JSD élevé, distributions cohérentes
      (somme baseline ≈ 1), total_grilles == sum(strat_counts).
    - Pipeline : tier2["stratification"] présent sous --noise-floor, plancher +
      is_material + effect_tier (materiel_fort), additivité, gate, Loto ET EM.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from config.engine import EM_ZONES, LOTO_ZONES
from tools.backtest_hybride import (
    FEATURE_NAMES,
    STRATIFICATION_BUCKETS,
    BacktestConfig,
    BacktestHarness,
    TirageRecord,
)
from tools.signature_features import (
    STRATIFICATION_BINS,
    classify_stratification_index,
    generate_stratification_baseline,
)


# ════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════

_FAKE_TIRAGES_LOTO: list[TirageRecord] = [
    TirageRecord(draw_date=date(2026, 1, 1), balls=[3, 14, 22, 31, 42], secondary=[5]),
    TirageRecord(draw_date=date(2026, 1, 8), balls=[7, 19, 24, 36, 48], secondary=[3]),
    TirageRecord(draw_date=date(2026, 1, 15), balls=[1, 11, 21, 38, 49], secondary=[8]),
]

# Les 5 grilles fictives sont TOUTES 1_per_zone (1 boule par zone) → HYBRIDE
# ~100% 1_per_zone vs baseline hasard ~3% → JSD stratification très élevé.
_FAKE_GRILLES_LOTO: list[dict] = [
    {"nums": [5, 13, 21, 34, 45], "chance": 7, "score": 95, "badges": []},
    {"nums": [2, 17, 28, 33, 47], "chance": 2, "score": 85, "badges": []},
    {"nums": [9, 14, 25, 31, 41], "chance": 9, "score": 75, "badges": []},
    {"nums": [4, 11, 23, 37, 48], "chance": 4, "score": 60, "badges": []},
    {"nums": [6, 15, 26, 32, 49], "chance": 6, "score": 50, "badges": []},
]

_FAKE_TIRAGES_EM: list[TirageRecord] = [
    TirageRecord(draw_date=date(2026, 1, 2), balls=[3, 14, 22, 31, 42], secondary=[2, 9]),
    TirageRecord(draw_date=date(2026, 1, 9), balls=[7, 19, 24, 36, 50], secondary=[1, 7]),
    TirageRecord(draw_date=date(2026, 1, 16), balls=[1, 11, 21, 38, 49], secondary=[5, 11]),
]


def _make_harness(game: str = "loto") -> BacktestHarness:
    return BacktestHarness(game=game, n_tirages=3, n_grilles_per_tirage=5)


@pytest.fixture
def mocked_harness(monkeypatch):
    """Harness Loto avec load_tirages + _generate_grilles mockes (zero DB)."""
    h = _make_harness("loto")

    async def fake_load_tirages():
        h._tirages_cache = list(_FAKE_TIRAGES_LOTO)
        return h._tirages_cache

    async def fake_generate(engine, brake_balls, brake_secondary, recent_draws=None):
        return [dict(g) for g in _FAKE_GRILLES_LOTO]

    monkeypatch.setattr(h, "load_tirages", fake_load_tirages)
    monkeypatch.setattr(h, "_generate_grilles", fake_generate)
    return h


# ════════════════════════════════════════════════════════════════════════
# Équivalence classification (refactor sans régression) — OBLIGATOIRE
# ════════════════════════════════════════════════════════════════════════

class TestClassificationEquivalence:

    # grilles couvrant les 4 catégories (zones Loto 1-10/11-20/21-30/31-40/41-49)
    _CASES = [
        ([5, 15, 25, 35, 45], "1_per_zone"),
        ([5, 6, 25, 35, 45], "2_in_one_zone"),      # 2 dans z1
        ([5, 6, 7, 35, 45], "3_in_one_zone"),       # 3 dans z1
        ([5, 6, 7, 8, 45], "libre"),                # 4 dans z1
        ([5, 6, 7, 8, 9], "libre"),                 # 5 dans z1
    ]

    def test_index_maps_to_method_4_categories(self):
        h = _make_harness("loto")
        for balls, expected_bucket in self._CASES:
            idx = classify_stratification_index(balls, h.zones)
            assert STRATIFICATION_BUCKETS[idx] == expected_bucket
            # équivalence stricte avec la méthode (source historique)
            assert STRATIFICATION_BUCKETS[idx] == h._compute_stratification(balls)

    def test_grille_vide_libre(self):
        h = _make_harness("loto")
        assert classify_stratification_index([], h.zones) == 3
        assert h._compute_stratification([]) == "libre"

    def test_equivalence_em_zones(self):
        h = _make_harness("em")
        # 50 est dans la dernière zone EM (41-50), pas dans Loto (41-49)
        balls = [5, 15, 25, 35, 50]
        idx = classify_stratification_index(balls, h.zones)
        assert STRATIFICATION_BUCKETS[idx] == h._compute_stratification(balls)
        assert STRATIFICATION_BUCKETS[idx] == "1_per_zone"


# ════════════════════════════════════════════════════════════════════════
# Baseline hasard
# ════════════════════════════════════════════════════════════════════════

class TestStratificationBaseline:

    def test_zones_none_raises(self):
        with pytest.raises(ValueError):
            generate_stratification_baseline(n=10, num_max=49, k=5, seed=42, zones=None)

    def test_deterministic_seed(self):
        # __wrapped__ : bypass lru_cache pour comparer 2 calculs frais
        gen = generate_stratification_baseline.__wrapped__
        a = gen(n=3000, num_max=49, k=5, seed=42, zones=LOTO_ZONES)
        b = gen(n=3000, num_max=49, k=5, seed=42, zones=LOTO_ZONES)
        assert a == b
        assert len(a) == 3000
        assert all(isinstance(v, int) and 0 <= v <= 3 for v in a)

    def test_proportions_plausibles_1_per_zone_rare(self):
        gen = generate_stratification_baseline.__wrapped__
        base = gen(n=20000, num_max=49, k=5, seed=42, zones=LOTO_ZONES)
        counts = [0, 0, 0, 0]
        for v in base:
            counts[v] += 1
        props = [c / len(base) for c in counts]
        assert abs(sum(props) - 1.0) < 1e-9
        # 1_per_zone (index 0) est RARE dans le hasard (~3%)
        assert props[0] < 0.10, f"1_per_zone hasard trop fréquent : {props[0]}"
        # une catégorie non-1_per_zone domine
        assert max(props[1:]) > props[0]

    def test_loto_em_distinctes(self):
        gen = generate_stratification_baseline.__wrapped__
        loto = gen(n=2000, num_max=49, k=5, seed=42, zones=LOTO_ZONES)
        em = gen(n=2000, num_max=50, k=5, seed=42, zones=EM_ZONES)
        # univers différent (49 vs 50) + zones différentes → séquences distinctes
        assert loto != em


# ════════════════════════════════════════════════════════════════════════
# _compute_tier2_stratification (méthode directe)
# ════════════════════════════════════════════════════════════════════════

class TestComputeTier2Stratification:

    def _counts(self, n1=100, n2=0, n3=0, nlibre=0):
        return {
            "1_per_zone": n1, "2_in_one_zone": n2,
            "3_in_one_zone": n3, "libre": nlibre,
        }

    def test_structure_et_jsd_eleve(self):
        h = _make_harness("loto")
        strat_counts = self._counts(n1=100)
        out = h._compute_tier2_stratification(
            strat_counts, 100, tirages=_FAKE_TIRAGES_LOTO,
        )
        assert "stratification" in out["feature_jsd"]
        jsd = out["feature_jsd"]["stratification"]
        # HYBRIDE 100% 1_per_zone vs hasard étalé → JSD très élevé
        assert jsd > 0.3, f"JSD stratification trop faible : {jsd}"
        assert out["base"] == "e"
        assert out["n_hybride_samples"] == 100

    def test_distributions_coherentes(self):
        h = _make_harness("loto")
        strat_counts = self._counts(n1=80, n2=20)
        out = h._compute_tier2_stratification(
            strat_counts, 100, tirages=_FAKE_TIRAGES_LOTO,
        )
        hyb = out["hybride_distribution"]
        assert hyb["1_per_zone"] == 0.8
        assert hyb["2_in_one_zone"] == 0.2
        # MICRO-POINT 1 : baseline_distribution = proportions cohérentes (somme ≈ 1)
        base = out["baseline_distribution"]
        assert abs(sum(base.values()) - 1.0) < 0.01
        assert set(base.keys()) == set(STRATIFICATION_BUCKETS)
        # real_distribution présent (tirages fournis)
        assert out["real_distribution"] is not None
        assert abs(sum(out["real_distribution"].values()) - 1.0) < 0.01

    def test_total_grilles_egal_somme_counts_pas_de_warning(self, monkeypatch):
        # MICRO-POINT 2 : total_grilles == sum(strat_counts) → aucun warning
        h = _make_harness("loto")
        mock_logger = MagicMock()
        monkeypatch.setattr("tools.backtest_hybride.logger", mock_logger)
        strat_counts = self._counts(n1=60, n2=30, n3=10)  # somme = 100
        h._compute_tier2_stratification(strat_counts, 100, tirages=_FAKE_TIRAGES_LOTO)
        assert not mock_logger.warning.called

    def test_total_grilles_mismatch_warning(self, monkeypatch):
        h = _make_harness("loto")
        mock_logger = MagicMock()
        monkeypatch.setattr("tools.backtest_hybride.logger", mock_logger)
        strat_counts = self._counts(n1=100)  # somme = 100 != 99
        h._compute_tier2_stratification(strat_counts, 99, tirages=_FAKE_TIRAGES_LOTO)
        assert mock_logger.warning.called
        assert "[STRATIFICATION]" in mock_logger.warning.call_args[0][0]

    def test_em_path(self):
        h = _make_harness("em")
        strat_counts = self._counts(n1=100)
        out = h._compute_tier2_stratification(
            strat_counts, 100, tirages=_FAKE_TIRAGES_EM,
        )
        assert out["feature_jsd"]["stratification"] > 0.3
        assert abs(sum(out["baseline_distribution"].values()) - 1.0) < 0.01


# ════════════════════════════════════════════════════════════════════════
# Pipeline complet (mocks) — plancher / effect_tier / additivité / gate
# ════════════════════════════════════════════════════════════════════════

class TestPipelineIntegration:

    @pytest.mark.asyncio
    async def test_stratification_dans_tier2_avec_noise_floor(self, mocked_harness):
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg, noise_floor=True)
        tier2 = result["tier2"]
        assert "stratification" in tier2
        assert "stratification" in tier2["stratification"]["feature_jsd"]

    @pytest.mark.asyncio
    async def test_plancher_et_effect_tier_stratification(self, mocked_harness):
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg, noise_floor=True)
        tier2 = result["tier2"]
        # plancher présent
        assert "stratification" in tier2["noise_floor"]
        assert "p_value" in tier2["noise_floor"]["stratification"]
        # FDR + verdict englobent la stratification
        assert "stratification" in tier2["is_material"]
        assert "stratification" in tier2["effect_tier"]
        # signature la plus forte → matériel fort
        assert tier2["is_material"]["stratification"] is True
        assert tier2["effect_tier"]["stratification"] == "materiel_fort"

    @pytest.mark.asyncio
    async def test_additivite(self, mocked_harness):
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg, noise_floor=True)
        tier2 = result["tier2"]
        # feature_jsd boules INTACT (7 features, pas de "stratification" dedans)
        assert set(tier2["feature_jsd"].keys()) == set(FEATURE_NAMES)
        assert "stratification" not in tier2["feature_jsd"]
        # stratification_distribution_generated (résultats) inchangé + cohérent
        sdg = result["stratification_distribution_generated"]
        assert set(sdg.keys()) == set(STRATIFICATION_BUCKETS)
        assert sdg == tier2["stratification"]["hybride_distribution"]

    @pytest.mark.asyncio
    async def test_gate_sans_noise_floor(self, mocked_harness):
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg)
        assert "stratification" not in result["tier2"]
