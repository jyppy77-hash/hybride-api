"""Tests LOT 3 — verdict 3 niveaux `effect_tier` (seuil d'effet pratique) +
nettoyage de la limitation obsolète `recent_draws_absolute_not_relative`.

Prolonge la métrique V_X.F (lots c539a5c / a6c979f / b960af0). OFFLINE PUR.

Couvre :
    - Cohérence stricte avec is_material (bruit <=> is_material False).
    - Partition par le seuil JSD (materiel_fort >= seuil ; sinon negligeable).
    - "bruit ne depend PAS du JSD" (non-materiel a JSD eleve reste bruit).
    - Override kwarg-only effect_threshold respecte.
    - Tracabilite noise_floor_meta["effect_size_threshold"].
    - Defense JSD manquant pour feature materielle -> negligeable + warning.
    - Additivite : feature_jsd / is_material / noise_floor / histograms intacts.
    - Run sans --include-secondary : effect_tier ne contient que les boules.
    - Nettoyage : compare().limitations_mvp == run_oos().limitations_mvp, sans
      la chaine obsolete.

Verdict deterministe : on patche `apply_fdr_correction` (importe dans le
namespace backtest_hybride) pour controler is_material exactement, et on fixe
le JSD via tier2["feature_jsd"]. Le plancher Monte Carlo tourne mais son
verdict est court-circuite par le patch -> assertions purement deterministes.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from tools.backtest_hybride import (
    FEATURE_NAMES,
    BacktestConfig,
    BacktestHarness,
    TirageRecord,
    _EFFECT_SIZE_THRESHOLD,
)


# ════════════════════════════════════════════════════════════════════════
# Fixtures
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


# JSD boules choisis autour du seuil 0.02 pour exercer la partition.
_BOULES_JSD: dict[str, float] = {
    "somme": 0.30,            # fort
    "dispersion": 0.021,      # juste au-dessus -> fort
    "std": 0.019,             # juste en-dessous -> negligeable
    "freq_1_31": 0.010,       # negligeable
    "nb_pairs": 0.001,        # (non-materiel -> bruit)
    "nb_consecutifs": 0.15,   # JSD eleve MAIS non-materiel -> bruit
    "esi": 0.05,              # fort
}


def _patch_fdr(monkeypatch, material_map: dict[str, bool]):
    """Patche apply_fdr_correction pour imposer is_material exactement.

    material_map peut contenir une feature ABSENTE de feature_jsd (test defense).
    """
    def fake_fdr(p_values, alpha=0.05):
        out = {}
        # features reellement testees (plancher calcule)
        for fn in p_values:
            out[fn] = {
                "p_value": p_values[fn],
                "is_material_fdr": material_map.get(fn, False),
                "bh_threshold": 0.0,
            }
        # features fantomes (forcees materielles, absentes du plancher) pour
        # exercer la branche defense JSD manquant.
        for fn, mat in material_map.items():
            if fn not in out:
                out[fn] = {"p_value": 1.0, "is_material_fdr": mat, "bh_threshold": 0.0}
        return out

    monkeypatch.setattr("tools.backtest_hybride.apply_fdr_correction", fake_fdr)


def _run_attach(h, monkeypatch, material_map, *, effect_threshold=None, jsd=None):
    """Appelle _attach_noise_floor sur un tier2 minimal (boules only)."""
    tier2 = {"feature_jsd": dict(jsd if jsd is not None else _BOULES_JSD)}
    feature_values = {fn: [10.0] * 50 for fn in FEATURE_NAMES}
    _patch_fdr(monkeypatch, material_map)
    if effect_threshold is None:
        h._attach_noise_floor(tier2, feature_values, {}, {})
    else:
        h._attach_noise_floor(
            tier2, feature_values, {}, {}, effect_threshold=effect_threshold,
        )
    return tier2


# ════════════════════════════════════════════════════════════════════════
# Verdict 3 niveaux — cohérence is_material + partition seuil
# ════════════════════════════════════════════════════════════════════════

class TestEffectTierVerdict:

    def test_coherence_bruit_iff_non_material(self, monkeypatch):
        h = _make_harness("loto")
        material_map = {
            "somme": True, "dispersion": True, "std": True, "freq_1_31": True,
            "nb_pairs": False, "nb_consecutifs": False, "esi": True,
        }
        tier2 = _run_attach(h, monkeypatch, material_map)
        et = tier2["effect_tier"]
        for fn in FEATURE_NAMES:
            if material_map[fn] is False:
                assert et[fn] == "bruit", f"{fn} non-materiel doit etre bruit"
            else:
                assert et[fn] != "bruit", f"{fn} materiel ne doit pas etre bruit"

    def test_partition_autour_du_seuil(self, monkeypatch):
        """0.021 -> fort ; 0.019 -> negligeable (seuil 0.02)."""
        h = _make_harness("loto")
        material_map = {fn: True for fn in FEATURE_NAMES}
        tier2 = _run_attach(h, monkeypatch, material_map)
        et = tier2["effect_tier"]
        assert et["dispersion"] == "materiel_fort"        # 0.021 >= 0.02
        assert et["std"] == "materiel_negligeable"        # 0.019 < 0.02
        assert et["somme"] == "materiel_fort"             # 0.30
        assert et["esi"] == "materiel_fort"               # 0.05
        assert et["freq_1_31"] == "materiel_negligeable"  # 0.010

    def test_bruit_ne_depend_pas_du_jsd(self, monkeypatch):
        """nb_consecutifs JSD=0.15 (eleve) mais non-materiel -> bruit."""
        h = _make_harness("loto")
        material_map = {fn: True for fn in FEATURE_NAMES}
        material_map["nb_consecutifs"] = False
        tier2 = _run_attach(h, monkeypatch, material_map)
        assert tier2["feature_jsd"]["nb_consecutifs"] == 0.15
        assert tier2["effect_tier"]["nb_consecutifs"] == "bruit"

    def test_seuil_exact_inclusif(self, monkeypatch):
        """JSD == seuil -> materiel_fort (comparaison >=)."""
        h = _make_harness("loto")
        jsd = {fn: _EFFECT_SIZE_THRESHOLD for fn in FEATURE_NAMES}
        material_map = {fn: True for fn in FEATURE_NAMES}
        tier2 = _run_attach(h, monkeypatch, material_map, jsd=jsd)
        for fn in FEATURE_NAMES:
            assert tier2["effect_tier"][fn] == "materiel_fort"


# ════════════════════════════════════════════════════════════════════════
# Override + traçabilité
# ════════════════════════════════════════════════════════════════════════

class TestEffectThresholdOverride:

    def test_override_reclasse_fort_en_negligeable(self, monkeypatch):
        """effect_threshold=0.5 : meme une signature forte (0.30) devient negligeable."""
        h = _make_harness("loto")
        material_map = {fn: True for fn in FEATURE_NAMES}
        material_map["nb_pairs"] = False  # reste bruit
        tier2 = _run_attach(h, monkeypatch, material_map, effect_threshold=0.5)
        et = tier2["effect_tier"]
        assert et["somme"] == "materiel_negligeable"      # 0.30 < 0.5
        assert et["esi"] == "materiel_negligeable"        # 0.05 < 0.5
        assert et["dispersion"] == "materiel_negligeable"
        assert et["nb_pairs"] == "bruit"                  # non-materiel inchange

    def test_meta_effect_size_threshold_defaut(self, monkeypatch):
        h = _make_harness("loto")
        material_map = {fn: True for fn in FEATURE_NAMES}
        tier2 = _run_attach(h, monkeypatch, material_map)
        assert tier2["noise_floor_meta"]["effect_size_threshold"] == _EFFECT_SIZE_THRESHOLD
        assert tier2["noise_floor_meta"]["effect_size_threshold"] == 0.02

    def test_meta_effect_size_threshold_override(self, monkeypatch):
        h = _make_harness("loto")
        material_map = {fn: True for fn in FEATURE_NAMES}
        tier2 = _run_attach(h, monkeypatch, material_map, effect_threshold=0.5)
        assert tier2["noise_floor_meta"]["effect_size_threshold"] == 0.5


# ════════════════════════════════════════════════════════════════════════
# Défense JSD manquant
# ════════════════════════════════════════════════════════════════════════

class TestEffectTierDefense:

    def test_feature_materielle_sans_jsd_negligeable_et_warning(self, monkeypatch):
        """Feature materielle absente de feature_jsd -> negligeable + logger.warning."""
        h = _make_harness("loto")
        mock_logger = MagicMock()
        monkeypatch.setattr("tools.backtest_hybride.logger", mock_logger)
        material_map = {fn: True for fn in FEATURE_NAMES}
        material_map["ghost_feature"] = True  # materielle mais absente du JSD
        tier2 = _run_attach(h, monkeypatch, material_map)
        assert tier2["effect_tier"]["ghost_feature"] == "materiel_negligeable"
        # warning emis avec le bon prefixe et le bon nom
        assert mock_logger.warning.called
        msg = mock_logger.warning.call_args[0]
        assert "[EFFECT-TIER]" in msg[0]
        assert "ghost_feature" in msg


# ════════════════════════════════════════════════════════════════════════
# Additivité (pipeline complet) + run sans secondary
# ════════════════════════════════════════════════════════════════════════

class TestEffectTierAdditivity:

    @pytest.mark.asyncio
    async def test_pipeline_effect_tier_additif(self, mocked_harness):
        """noise_floor=True : effect_tier present, cles existantes intactes."""
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(
            cfg, include_secondary=True, noise_floor=True,
        )
        tier2 = result["tier2"]
        # cles existantes preservees
        for key in ("feature_jsd", "histograms", "is_material", "noise_floor",
                    "noise_floor_meta", "secondary"):
            assert key in tier2, f"cle existante disparue : {key!r}"
        # 7 features boules dans feature_jsd (contrat inchange)
        assert set(tier2["feature_jsd"].keys()) == set(FEATURE_NAMES)
        # nouvelle cle
        assert "effect_tier" in tier2
        # cles effect_tier == cles is_material (liste de reference canonique)
        assert set(tier2["effect_tier"].keys()) == set(tier2["is_material"].keys())
        # valeurs dans le vocabulaire ferme
        for v in tier2["effect_tier"].values():
            assert v in {"bruit", "materiel_negligeable", "materiel_fort"}

    @pytest.mark.asyncio
    async def test_pipeline_sans_secondary_boules_only(self, mocked_harness):
        """Sans include_secondary : effect_tier = boules (+ stratification V_X.B)."""
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg, noise_floor=True)
        tier2 = result["tier2"]
        assert "secondary" not in tier2
        # V_X.B : la stratification (signature des boules) s'ajoute sous --noise-floor,
        # indépendamment du secondaire. Ensemble autorisé = boules + "stratification".
        allowed = set(FEATURE_NAMES) | {"stratification"}
        assert set(tier2["effect_tier"].keys()) <= allowed
        # aucune feature SECONDAIRE ne fuite
        assert "chance_in_T1" not in tier2["effect_tier"]
        assert "chance_value" not in tier2["effect_tier"]

    @pytest.mark.asyncio
    async def test_pipeline_sans_noise_floor_pas_de_effect_tier(self, mocked_harness):
        """noise_floor off : effect_tier absent (opt-in strict)."""
        cfg = BacktestConfig()
        result = await mocked_harness.run_config(cfg)
        assert "effect_tier" not in result["tier2"]
        assert "is_material" not in result["tier2"]


# ════════════════════════════════════════════════════════════════════════
# Nettoyage limitation obsolète
# ════════════════════════════════════════════════════════════════════════

class TestLimitationsCleanup:

    EXPECTED = [
        "future_leak_calculer_scores_hybrides_accepted",
        "decay_state_disabled",
    ]

    @pytest.mark.asyncio
    async def test_compare_limitations_sans_recent_draws(self, mocked_harness):
        cfg = BacktestConfig()
        result = await mocked_harness.compare(cfg, cfg)
        lim = result["metadata"]["limitations_mvp"]
        assert "recent_draws_absolute_not_relative" not in lim
        assert lim == self.EXPECTED

    @pytest.mark.asyncio
    async def test_compare_equals_run_oos_limitations(self, mocked_harness):
        cfg = BacktestConfig()
        res_cmp = await mocked_harness.compare(cfg, cfg)
        res_oos = await mocked_harness.run_oos(cfg)
        assert (
            res_cmp["metadata"]["limitations_mvp"]
            == res_oos["metadata"]["limitations_mvp"]
        )
        assert res_oos["metadata"]["limitations_mvp"] == self.EXPECTED
