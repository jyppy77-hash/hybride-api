"""Tests PALIER 1 — Explicabilité moteur (fréquence de génération par numéro).

OFFLINE PUR (tools/). Couvre la clé `engine_explainability` ajoutée au retour de
`BacktestHarness.run_config` (reflétée par `run_oos`) :

    - Comptage `frequency_by_number` / secondaire : somme == total_grids × num_count.
    - `deviation_from_uniform` global : signe + magnitude exacte (numéro absent = -1.0).
    - ⭐ `deviation_from_uniform_intra_zone` : dénominateur = total_grids / |zone|
      (≠ global), deux numéros de fréquence IDENTIQUE mais de zones de tailles
      différentes ont une déviation globale identique MAIS intra-zone distincte.
    - Corrélations internes : V106 (boules only, plage [0.79,1.0]), hard_exclude /
      persistent_brake en fractions [0,1] relatives aux contextes du run.
    - `notes` d'honnêteté présentes ; garde n_tirages=1 (0 contexte) sans division.

⚠️ GARDE-FOU ANJ : aucun test ne rapproche la fréquence d'un tirage réel.
"""
from __future__ import annotations

from datetime import date

import pytest

from services.penalization import get_unpopularity_multiplier
from tools.backtest_hybride import BacktestConfig, BacktestHarness, TirageRecord

# ════════════════════════════════════════════════════════════════════════
# Fixtures — grilles déterministes (zéro DB)
# ════════════════════════════════════════════════════════════════════════

# 3 tirages Loto avec boules distinctes → hard-exclude T-1 traçable.
_TIRAGES_LOTO = [
    TirageRecord(draw_date=date(2026, 1, 1), balls=[1, 11, 21, 31, 41], secondary=[5]),
    TirageRecord(draw_date=date(2026, 1, 8), balls=[2, 12, 22, 32, 42], secondary=[3]),
    TirageRecord(draw_date=date(2026, 1, 15), balls=[3, 13, 23, 33, 43], secondary=[8]),
]

# 5 grilles : MÊMES boules (1 numéro/zone) → 5 (z1 size 10) et 45 (z5 size 9) ont
# la MÊME fréquence (déviation globale identique, intra-zone DISTINCTE). Chances
# variées → ≥3 valeurs distinctes pour valider top_chance.
_CHANCES_LOTO = [7, 3, 9, 2, 5]
_GRILLES_LOTO = [
    {"nums": [5, 15, 25, 35, 45], "chance": c, "score": 95, "badges": []}
    for c in _CHANCES_LOTO
]

_TIRAGES_EM = [
    TirageRecord(draw_date=date(2026, 1, 2), balls=[1, 11, 21, 31, 41], secondary=[2, 9]),
    TirageRecord(draw_date=date(2026, 1, 9), balls=[2, 12, 22, 32, 42], secondary=[1, 7]),
    TirageRecord(draw_date=date(2026, 1, 16), balls=[3, 13, 23, 33, 43], secondary=[5, 11]),
]
_GRILLES_EM = [
    {"nums": [5, 15, 25, 35, 45], "etoiles": [2, 9], "score": 95, "badges": []}
    for _ in range(5)
]


def _mock_harness(monkeypatch, game, tirages, grilles, n_tirages=3):
    h = BacktestHarness(game=game, n_tirages=n_tirages, n_grilles_per_tirage=len(grilles))

    async def fake_load_tirages():
        h._tirages_cache = list(tirages)
        return h._tirages_cache

    async def fake_generate(engine, brake_balls, brake_secondary, recent_draws=None):
        return [dict(g) for g in grilles]

    monkeypatch.setattr(h, "load_tirages", fake_load_tirages)
    monkeypatch.setattr(h, "_generate_grilles", fake_generate)
    return h


@pytest.fixture
def loto_harness(monkeypatch):
    return _mock_harness(monkeypatch, "loto", _TIRAGES_LOTO, _GRILLES_LOTO)


@pytest.fixture
def em_harness(monkeypatch):
    return _mock_harness(monkeypatch, "em", _TIRAGES_EM, _GRILLES_EM)


# ════════════════════════════════════════════════════════════════════════
# Comptage
# ════════════════════════════════════════════════════════════════════════

class TestFrequencyCounting:

    @pytest.mark.asyncio
    async def test_boules_sum_equals_total_times_5_loto(self, loto_harness):
        res = (await loto_harness.run_config(BacktestConfig()))["engine_explainability"]
        assert res["total_grids"] == 15  # 3 tirages × 5 grilles
        assert sum(res["frequency_by_number"].values()) == 15 * 5
        # Toute la plage Loto présente (zéros compris)
        assert len(res["frequency_by_number"]) == 49
        assert res["frequency_by_number"]["1"] == 0  # numéro jamais généré

    @pytest.mark.asyncio
    async def test_secondary_sum_loto_chance(self, loto_harness):
        res = (await loto_harness.run_config(BacktestConfig()))["engine_explainability"]
        # Loto : secondary_count=1 → somme == total_grids
        assert "frequency_by_chance" in res
        assert sum(res["frequency_by_chance"].values()) == 15
        # chances variées [7,3,9,2,5], chacune 1×/grille × 3 tirages → freq 3
        assert res["frequency_by_chance"]["7"] == 3
        assert "top_chance" in res and len(res["top_chance"]) == 3

    @pytest.mark.asyncio
    async def test_secondary_sum_em_stars(self, em_harness):
        res = (await em_harness.run_config(BacktestConfig()))["engine_explainability"]
        # EM : secondary_count=2 → somme == total_grids × 2
        assert "frequency_by_star" in res
        assert sum(res["frequency_by_star"].values()) == 15 * 2
        assert res["frequency_by_star"]["2"] == 15
        assert res["frequency_by_star"]["9"] == 15
        assert "top_stars" in res and len(res["top_stars"]) == 2


# ════════════════════════════════════════════════════════════════════════
# Déviation
# ════════════════════════════════════════════════════════════════════════

class TestDeviation:

    @pytest.mark.asyncio
    async def test_global_deviation_sign_and_value(self, loto_harness):
        res = (await loto_harness.run_config(BacktestConfig()))["engine_explainability"]
        # attendu global = 15×5/49 = 1.5306
        assert res["uniform_expectation_per_number"] == round(75 / 49, 4)
        # 5 généré 15× → dev = 15×49/75 - 1 = 8.8 exactement
        assert res["deviation_from_uniform"]["5"] == 8.8
        # numéro absent → -1.0
        assert res["deviation_from_uniform"]["1"] == -1.0

    @pytest.mark.asyncio
    async def test_intra_zone_uses_zone_size_denominator(self, loto_harness):
        res = (await loto_harness.run_config(BacktestConfig()))["engine_explainability"]
        # 5 (zone 1-10, taille 10) et 45 (zone 41-49, taille 9) ont la MÊME freq (15)
        # → déviation GLOBALE identique...
        assert res["deviation_from_uniform"]["5"] == res["deviation_from_uniform"]["45"]
        # ...mais INTRA-ZONE distincte (dénominateur = total/|zone|) :
        #   5  : 15/(15/10) - 1 = 9.0   |   45 : 15/(15/9) - 1 = 8.0
        assert res["deviation_from_uniform_intra_zone"]["5"] == 9.0
        assert res["deviation_from_uniform_intra_zone"]["45"] == 8.0
        assert res["deviation_from_uniform_intra_zone"]["5"] != res["deviation_from_uniform_intra_zone"]["45"]

    @pytest.mark.asyncio
    async def test_top_numbers_structure(self, loto_harness):
        res = (await loto_harness.run_config(BacktestConfig()))["engine_explainability"]
        top = res["top_numbers"]
        assert len(top) == 5
        assert {t["number"] for t in top} == {5, 15, 25, 35, 45}
        for t in top:
            assert {"number", "frequency", "deviation_from_uniform",
                    "deviation_from_uniform_intra_zone"} <= set(t)


# ════════════════════════════════════════════════════════════════════════
# Corrélations internes
# ════════════════════════════════════════════════════════════════════════

class TestInternalCorrelations:

    @pytest.mark.asyncio
    async def test_zone_mapping(self, loto_harness):
        res = (await loto_harness.run_config(BacktestConfig()))["engine_explainability"]
        assert res["correlation_with_zone"]["5"] == "1-10"
        assert res["correlation_with_zone"]["45"] == "41-49"

    @pytest.mark.asyncio
    async def test_unpopularity_boules_only_in_range(self, loto_harness):
        res = (await loto_harness.run_config(BacktestConfig()))["engine_explainability"]
        corr = res["correlation_with_unpopularity"]
        # boules uniquement (49 entrées, pas de secondaire)
        assert len(corr) == 49
        assert all(0.79 <= v <= 1.0 for v in corr.values())
        # cohérence avec la fonction moteur (source de vérité)
        assert corr["5"] == round(get_unpopularity_multiplier(5), 4)
        assert corr["45"] == round(get_unpopularity_multiplier(45), 4)

    @pytest.mark.asyncio
    async def test_hard_exclude_fraction(self, loto_harness):
        res = (await loto_harness.run_config(BacktestConfig()))["engine_explainability"]
        # 3 tirages → 2 contextes (idx 1,2). T-1 à idx1 = tirage0 {1,11,21,31,41},
        # T-1 à idx2 = tirage1 {2,12,22,32,42}. Chaque numéro exclu 1×/2 → 0.5.
        assert res["n_contexts_with_history"] == 2
        he = res["correlation_with_hard_exclude"]
        assert he["1"] == 0.5
        assert he["2"] == 0.5
        assert he["3"] == 0.0  # tirage2 ne devient jamais T-1
        assert all(0.0 <= v <= 1.0 for v in he.values())

    @pytest.mark.asyncio
    async def test_persistent_brake_fraction(self, loto_harness):
        res = (await loto_harness.run_config(BacktestConfig()))["engine_explainability"]
        # Grille canonique [5,15,25,35,45] entre dans virtual_history → brake aux
        # contextes idx 1 et 2 sur ces numéros → fraction 2/2 = 1.0.
        pb = res["correlation_with_persistent_brake"]
        assert pb["5"] == 1.0
        assert pb["1"] == 0.0
        assert all(0.0 <= v <= 1.0 for v in pb.values())


# ════════════════════════════════════════════════════════════════════════
# Notes d'honnêteté + garde
# ════════════════════════════════════════════════════════════════════════

class TestNotesAndGuards:

    @pytest.mark.asyncio
    async def test_notes_present(self, loto_harness):
        res = (await loto_harness.run_config(BacktestConfig()))["engine_explainability"]
        notes = res["notes"]
        assert notes["decay_disabled_in_backtest"] is True
        assert notes["unpopularity_boules_only"] is True
        assert "stochastique" in notes["selection_is_stochastic"].lower()
        # explicite : fractions relatives aux contextes du run, pas constantes moteur
        assert "FRACTIONS relatives" in notes["aggregates_200_contexts"]

    @pytest.mark.asyncio
    async def test_single_tirage_no_context_no_division(self, monkeypatch):
        # n_tirages=1 → idx 0 seul → 0 contexte avec historique → pas de division.
        h = _mock_harness(
            monkeypatch, "loto", _TIRAGES_LOTO[:1], _GRILLES_LOTO, n_tirages=1,
        )
        res = (await h.run_config(BacktestConfig()))["engine_explainability"]
        assert res["n_contexts_with_history"] == 0
        assert all(v == 0.0 for v in res["correlation_with_hard_exclude"].values())
        assert all(v == 0.0 for v in res["correlation_with_persistent_brake"].values())
        # comptage toujours cohérent (1 tirage × 5 grilles)
        assert res["total_grids"] == 5
        assert sum(res["frequency_by_number"].values()) == 5 * 5


# ════════════════════════════════════════════════════════════════════════
# PNG explicabilité (smoke) — déviation de génération par numéro
# ════════════════════════════════════════════════════════════════════════

def _wrapper(result, game):
    return {
        "metadata": {
            "game": game, "n_tirages": 3, "n_grilles_per_tirage": 5,
            "mode": "balanced", "elapsed_seconds": 0.1,
            "harness_version": "v1.0", "run_at": "2026-06-09T00:00:00Z",
        },
        "results_config_actuelle": result,
        "results_config_test": result,
        "config_actuelle": {}, "config_test": {},
    }


class TestExplainabilityPlot:

    @pytest.mark.asyncio
    async def test_plot_creates_png_loto(self, loto_harness, tmp_path):
        result = await loto_harness.run_config(BacktestConfig())
        png = tmp_path / "loto_explainability.png"
        loto_harness.plot_engine_explainability(_wrapper(result, "loto"), str(png))
        assert png.exists()
        assert png.stat().st_size > 5_000  # PNG min raisonnable

    @pytest.mark.asyncio
    async def test_plot_creates_png_em(self, em_harness, tmp_path):
        # EM : panneau secondaire à 2 étoiles
        result = await em_harness.run_config(BacktestConfig())
        png = tmp_path / "em_explainability.png"
        em_harness.plot_engine_explainability(_wrapper(result, "em"), str(png))
        assert png.exists()
        assert png.stat().st_size > 5_000

    @pytest.mark.asyncio
    async def test_plot_skips_gracefully_when_absent(self, loto_harness, tmp_path):
        # Pas de engine_explainability → skip propre, pas de crash, pas de fichier.
        wrapper = {
            "metadata": {"game": "loto", "harness_version": "v1.0",
                         "run_at": "2026-06-09T00:00:00Z"},
            "results_config_actuelle": {},
            "results_config_test": {},
        }
        png = tmp_path / "absent.png"
        loto_harness.plot_engine_explainability(wrapper, str(png))
        assert not png.exists()
