"""Tests LOT S2 — features positionnelles secondaire (non-temporelles).

Couvre tools/signature_features.py :
    - extract_secondary_positional (Loto chance_value / EM basse-haute-ecart)
    - build_secondary_bins (extension positionnelle + séparation registres)
    - generate_secondary_positional_baseline (baseline SIMPLE non appariée)
et l'intégration tools/backtest_hybride.py (harness mocké, zéro DB) :
    - tier2["secondary"]["feature_jsd"] contient les positionnelles
    - plancher noise_floor / is_material (FDR globale) les englobent
    - non-régression *_in_T1 + boules

Tests purs en mémoire — pas de DB. Mocks via monkeypatch.
"""
from __future__ import annotations

import math
import random as _stdlib_random
from datetime import date

import numpy as np
import pytest

from tools.signature_features import (
    SECONDARY_FEATURE_NAMES,
    SECONDARY_POSITIONAL_NAMES,
    build_bins,
    build_secondary_bins,
    extract_secondary_positional,
    generate_secondary_in_t1_baseline,
    generate_secondary_positional_baseline,
)
from tools.backtest_hybride import BacktestConfig, BacktestHarness, TirageRecord

_LN2 = math.log(2.0)


# ════════════════════════════════════════════════════════════════════════
# extract_secondary_positional
# ════════════════════════════════════════════════════════════════════════

class TestExtractSecondaryPositional:

    def test_loto_chance_value_int(self):
        assert extract_secondary_positional(7, "loto") == {"chance_value": 7.0}

    def test_loto_chance_value_list(self):
        # Loto peut arriver en list[int] selon le call-site → normalisé.
        assert extract_secondary_positional([3], "loto") == {"chance_value": 3.0}

    def test_em_basse_haute_ecart(self):
        out = extract_secondary_positional([9, 2], "em")  # non trié exprès
        assert out == {"etoiles_basse": 2.0, "etoiles_haute": 9.0, "etoiles_ecart": 7.0}

    def test_em_ecart_never_zero(self):
        # 2 étoiles distinctes → écart ≥ 1 (jamais 0).
        for pair in ([1, 2], [11, 12], [1, 12], [5, 6]):
            out = extract_secondary_positional(pair, "em")
            assert out["etoiles_ecart"] >= 1.0

    def test_em_min_max_consistency(self):
        out = extract_secondary_positional({4, 11}, "em")
        assert out["etoiles_basse"] == 4.0
        assert out["etoiles_haute"] == 11.0
        assert out["etoiles_ecart"] == 7.0

    def test_loto_empty_defense(self):
        assert extract_secondary_positional(None, "loto") == {}
        assert extract_secondary_positional([], "loto") == {}

    def test_em_incomplete_defense(self):
        # EM a besoin de 2 étoiles → dict vide sinon (le caller ignore).
        assert extract_secondary_positional([5], "em") == {}
        assert extract_secondary_positional(None, "em") == {}


# ════════════════════════════════════════════════════════════════════════
# build_secondary_bins — extension positionnelle + séparation registres
# ════════════════════════════════════════════════════════════════════════

class TestBuildSecondaryBinsPositional:

    def test_chance_value_edges(self):
        np.testing.assert_array_equal(
            build_secondary_bins("chance_value"), np.arange(1, 12, 1, dtype=np.float64)
        )

    def test_etoiles_basse_edges(self):
        np.testing.assert_array_equal(
            build_secondary_bins("etoiles_basse"), np.arange(1, 13, 1, dtype=np.float64)
        )

    def test_etoiles_haute_edges(self):
        np.testing.assert_array_equal(
            build_secondary_bins("etoiles_haute"), np.arange(2, 14, 1, dtype=np.float64)
        )

    def test_etoiles_ecart_edges_no_zero_bin(self):
        edges = build_secondary_bins("etoiles_ecart")
        np.testing.assert_array_equal(edges, np.arange(1, 13, 1, dtype=np.float64))
        assert edges[0] == 1.0  # pas de bin 0 (écart ≥ 1)

    def test_each_integer_in_own_bin(self):
        # Convention np.histogram : value v dans [edge_i, edge_{i+1}).
        edges = build_secondary_bins("chance_value")
        hist, _ = np.histogram([1, 5, 10], bins=edges)
        assert hist.sum() == 3
        assert hist[0] == 1 and hist[4] == 1 and hist[-1] == 1

    def test_in_t1_bins_still_intact(self):
        # LOT S1 non régressé.
        np.testing.assert_array_equal(
            build_secondary_bins("chance_in_T1"), np.array([0.0, 1.0, 2.0])
        )
        np.testing.assert_array_equal(
            build_secondary_bins("etoiles_in_T1"), np.array([0.0, 1.0, 2.0, 3.0])
        )

    def test_unknown_feature_raises(self):
        with pytest.raises(ValueError):
            build_secondary_bins("inexistante")

    def test_registry_separation_boules_rejects_positional(self):
        # build_bins (boules) lève sur un nom positionnel, et réciproquement.
        with pytest.raises(ValueError):
            build_bins("chance_value")
        with pytest.raises(ValueError):
            build_bins("etoiles_basse")


# ════════════════════════════════════════════════════════════════════════
# generate_secondary_positional_baseline — baseline SIMPLE non appariée
# ════════════════════════════════════════════════════════════════════════

class TestGeneratePositionalBaseline:

    def test_game_required_raises(self):
        with pytest.raises(ValueError):
            generate_secondary_positional_baseline(n=100, game=None)
        with pytest.raises(ValueError):
            generate_secondary_positional_baseline(n=100, game="poker")

    def test_reproducible_same_args_cached(self):
        a = generate_secondary_positional_baseline(n=500, sec_min=1, sec_max=12, count=2, seed=42, game="em")
        b = generate_secondary_positional_baseline(n=500, sec_min=1, sec_max=12, count=2, seed=42, game="em")
        assert a is b  # lru_cache → même objet

    def test_loto_chance_value_domain(self):
        base = generate_secondary_positional_baseline(
            n=5000, sec_min=1, sec_max=10, count=1, seed=42, game="loto"
        )
        assert all(set(d.keys()) == {"chance_value"} for d in base)
        vals = {d["chance_value"] for d in base}
        assert vals <= {float(v) for v in range(1, 11)}

    def test_em_positional_domains(self):
        base = generate_secondary_positional_baseline(
            n=5000, sec_min=1, sec_max=12, count=2, seed=42, game="em"
        )
        assert all(set(d.keys()) == {"etoiles_basse", "etoiles_haute", "etoiles_ecart"} for d in base)
        basse = {d["etoiles_basse"] for d in base}
        haute = {d["etoiles_haute"] for d in base}
        ecart = {d["etoiles_ecart"] for d in base}
        assert basse <= {float(v) for v in range(1, 12)}    # [1, 11]
        assert haute <= {float(v) for v in range(2, 13)}    # [2, 12]
        assert ecart <= {float(v) for v in range(1, 12)}    # [1, 11]
        assert 0.0 not in ecart                             # jamais 0

    def test_distinct_from_paired_baseline(self):
        # Baseline simple (positionnelle) ≠ baseline appariée (*_in_T1) : clés différentes.
        simple = generate_secondary_positional_baseline(n=300, sec_min=1, sec_max=10, count=1, seed=42, game="loto")
        paired = generate_secondary_in_t1_baseline(n=300, sec_min=1, sec_max=10, count=1, seed=42)
        assert "chance_value" in simple[0]
        assert "chance_in_T1" in paired[0]
        assert "chance_value" not in paired[0]

    def test_rng_global_not_mutated(self):
        _stdlib_random.seed(123)
        before = _stdlib_random.getstate()
        generate_secondary_positional_baseline(n=1000, sec_min=1, sec_max=12, count=2, seed=7, game="em")
        after = _stdlib_random.getstate()
        assert before == after  # RNG local — aucune pollution du global


# ════════════════════════════════════════════════════════════════════════
# Intégration harness (mocks, zéro DB) — Loto + EM
# ════════════════════════════════════════════════════════════════════════

_FAKE_TIRAGES_LOTO = [
    TirageRecord(draw_date=date(2026, 1, 1), balls=[3, 14, 22, 31, 42], secondary=[5]),
    TirageRecord(draw_date=date(2026, 1, 8), balls=[7, 19, 24, 36, 48], secondary=[3]),
    TirageRecord(draw_date=date(2026, 1, 15), balls=[1, 11, 21, 38, 49], secondary=[8]),
]
_FAKE_GRILLES_LOTO = [
    {"nums": [5, 13, 21, 34, 45], "chance": 7, "score": 95, "badges": []},
    {"nums": [2, 17, 28, 33, 47], "chance": 2, "score": 85, "badges": []},
    {"nums": [9, 14, 25, 31, 41], "chance": 9, "score": 75, "badges": []},
    {"nums": [4, 11, 23, 37, 48], "chance": 4, "score": 60, "badges": []},
    {"nums": [6, 15, 26, 32, 49], "chance": 6, "score": 50, "badges": []},
]

_FAKE_TIRAGES_EM = [
    TirageRecord(draw_date=date(2026, 1, 2), balls=[3, 14, 22, 31, 42], secondary=[4, 10]),
    TirageRecord(draw_date=date(2026, 1, 9), balls=[7, 19, 24, 36, 48], secondary=[2, 11]),
    TirageRecord(draw_date=date(2026, 1, 16), balls=[1, 11, 21, 38, 49], secondary=[1, 5]),
]
_FAKE_GRILLES_EM = [
    {"nums": [5, 13, 21, 34, 45], "etoiles": [1, 2], "score": 95, "badges": []},
    {"nums": [2, 17, 28, 33, 47], "etoiles": [3, 7], "score": 85, "badges": []},
    {"nums": [9, 14, 25, 31, 41], "etoiles": [5, 12], "score": 75, "badges": []},
    {"nums": [4, 11, 23, 37, 48], "etoiles": [2, 9], "score": 60, "badges": []},
    {"nums": [6, 15, 26, 32, 49], "etoiles": [6, 11], "score": 50, "badges": []},
]


def _mock_harness(monkeypatch, game, tirages, grilles):
    h = BacktestHarness(game=game, n_tirages=3, n_grilles_per_tirage=5)

    async def fake_load_tirages():
        h._tirages_cache = list(tirages)
        return h._tirages_cache

    async def fake_generate(engine, brake_balls, brake_secondary, recent_draws=None):
        return [dict(g) for g in grilles]

    monkeypatch.setattr(h, "load_tirages", fake_load_tirages)
    monkeypatch.setattr(h, "_generate_grilles", fake_generate)
    return h


class TestPositionalIntegrationLoto:

    @pytest.mark.asyncio
    async def test_feature_jsd_contains_positional_and_in_t1(self, monkeypatch):
        h = _mock_harness(monkeypatch, "loto", _FAKE_TIRAGES_LOTO, _FAKE_GRILLES_LOTO)
        result = await h.run_config(BacktestConfig(), include_secondary=True)
        sec_jsd = result["tier2"]["secondary"]["feature_jsd"]
        assert "chance_value" in sec_jsd          # positionnelle (LOT S2)
        assert "chance_in_T1" in sec_jsd          # reine (LOT S1) — non régressé
        assert 0.0 <= sec_jsd["chance_value"] <= _LN2

    @pytest.mark.asyncio
    async def test_noise_floor_and_fdr_include_positional(self, monkeypatch):
        h = _mock_harness(monkeypatch, "loto", _FAKE_TIRAGES_LOTO, _FAKE_GRILLES_LOTO)
        result = await h.run_config(BacktestConfig(), include_secondary=True, noise_floor=True)
        tier2 = result["tier2"]
        assert "chance_value" in tier2["noise_floor"]
        assert "chance_value" in tier2["is_material"]
        # FDR globale : boules (7) + *_in_T1 + positionnelle toutes présentes.
        assert "somme" in tier2["is_material"]
        assert "chance_in_T1" in tier2["is_material"]
        nf = tier2["noise_floor"]["chance_value"]
        assert 0.0 < nf["noise_floor"] <= _LN2
        assert 0.0 < nf["p_value"] <= 1.0


class TestPositionalIntegrationEM:

    @pytest.mark.asyncio
    async def test_feature_jsd_contains_three_positional(self, monkeypatch):
        h = _mock_harness(monkeypatch, "em", _FAKE_TIRAGES_EM, _FAKE_GRILLES_EM)
        result = await h.run_config(BacktestConfig(), include_secondary=True)
        sec_jsd = result["tier2"]["secondary"]["feature_jsd"]
        for fname in ("etoiles_basse", "etoiles_haute", "etoiles_ecart"):
            assert fname in sec_jsd
            assert 0.0 <= sec_jsd[fname] <= _LN2
        assert "etoiles_in_T1" in sec_jsd  # reine non régressée

    @pytest.mark.asyncio
    async def test_noise_floor_includes_three_positional(self, monkeypatch):
        h = _mock_harness(monkeypatch, "em", _FAKE_TIRAGES_EM, _FAKE_GRILLES_EM)
        result = await h.run_config(BacktestConfig(), include_secondary=True, noise_floor=True)
        tier2 = result["tier2"]
        for fname in ("etoiles_basse", "etoiles_haute", "etoiles_ecart"):
            assert fname in tier2["noise_floor"]
            assert fname in tier2["is_material"]


class TestPositionalNonRegression:

    @pytest.mark.asyncio
    async def test_secondary_absent_without_flag(self, monkeypatch):
        # include_secondary=False → pas de bloc secondary du tout (contrat boules pur).
        h = _mock_harness(monkeypatch, "loto", _FAKE_TIRAGES_LOTO, _FAKE_GRILLES_LOTO)
        result = await h.run_config(BacktestConfig())
        assert "secondary" not in result["tier2"]

    @pytest.mark.asyncio
    async def test_boules_feature_jsd_unchanged_keys(self, monkeypatch):
        # Les 7 features boules restent les seules clés du feature_jsd boules.
        from tools.signature_features import FEATURE_NAMES
        h = _mock_harness(monkeypatch, "loto", _FAKE_TIRAGES_LOTO, _FAKE_GRILLES_LOTO)
        result = await h.run_config(BacktestConfig(), include_secondary=True)
        assert set(result["tier2"]["feature_jsd"].keys()) == set(FEATURE_NAMES)

    def test_registries_disjoint(self):
        # Aucune feature partagée entre les 2 registres secondaire.
        for game in ("loto", "em"):
            in_t1 = set(SECONDARY_FEATURE_NAMES.get(game, ()))
            positional = set(SECONDARY_POSITIONAL_NAMES.get(game, ()))
            assert in_t1.isdisjoint(positional)
