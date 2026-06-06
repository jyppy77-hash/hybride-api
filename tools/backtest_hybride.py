"""
Backtest harness HYBRIDE engine — MVP étendu V_X.G (V142.G).

Rejoue N tirages historiques (Loto FR / EuroMillions), simule la génération
HYBRIDE avec 2 configs (actuelle vs test), mesure :
  - % gagnantes par palier
  - Distribution stratification empirique
  - Ratio observé / hasard théorique

Outputs : 1 JSON structuré + 3 PNG matplotlib dans `--output-dir`.

────────────────────────────────────────────────────────────────────────
USAGE CLI
────────────────────────────────────────────────────────────────────────

  python tools/backtest_hybride.py \
      --game loto \
      --n-tirages 200 \
      --n-grilles-per-tirage 100 \
      --output-dir /tmp/backtest_results/

  python tools/backtest_hybride.py \
      --game em \
      --n-tirages 200 \
      --n-grilles-per-tirage 100 \
      --config-test path/to/test_config.json \
      --output-dir /tmp/backtest_results_em/

────────────────────────────────────────────────────────────────────────
USAGE PROGRAMMATIC
────────────────────────────────────────────────────────────────────────

  from tools.backtest_hybride import BacktestHarness, BacktestConfig

  cfg_actuel = BacktestConfig()  # défaut = lit LOTO_CONFIG / EM_CONFIG
  cfg_test = BacktestConfig(saturation_brake_persistent_t1=0.0)  # hard exclude T-1

  harness = BacktestHarness(game="loto", n_tirages=200, n_grilles_per_tirage=100)
  results = await harness.compare(cfg_actuel, cfg_test)
  harness.export_json(results, "/tmp/backtest_results/loto_200.json")
  harness.plot_palier_distribution(results, "/tmp/backtest_results/palier_distribution.png")
  harness.plot_stratification(results, "/tmp/backtest_results/stratification.png")
  harness.plot_summary(results, "/tmp/backtest_results/summary.png")

────────────────────────────────────────────────────────────────────────
PRÉREQUIS LOCAL
────────────────────────────────────────────────────────────────────────

  1. Cloud SQL Proxy lancé : `cloud-sql-proxy ... &` (127.0.0.1:3306)
  2. .env présent avec DB_USER / DB_PASSWORD / DB_NAME
  3. matplotlib==3.9.2 (déjà dans requirements.txt)

────────────────────────────────────────────────────────────────────────
LIMITATIONS MVP DOCUMENTÉES (assumées, validées par Jyppy 2026-05-20)
────────────────────────────────────────────────────────────────────────

  1. **Future leak léger sur `calculer_scores_hybrides`** : l'engine voit
     l'intégralité de la table `tirages` (incluant T+1..T+latest) lors du
     calcul des fréquences globales. Le différentiel config_actuelle vs
     config_test reste valide car le biais est symétrique entre les 2
     configs comparées. Pour isolation stricte → backlog V143+.

  2. **`recent_draws` (pénalisation T-1..T-4)** : `engine.get_recent_draws()`
     retourne les 4 derniers tirages ABSOLUS de la table, pas relatifs à T.
     Décalage minime pour 200 tirages historiques (~98% des cas inchangés).

  3. **decay_state désactivé (=None)** : `services/decay_state` lit table
     prod `decay_state_history` non reconstituable historiquement. Le test
     isole V110 + V104 + V105 + V106 + V107 + contraintes ; le V92 decay
     est testé séparément si pertinent.

  4. **Mode READ-ONLY strict** : aucune écriture BDD. Toutes les queries
     sont SELECT. Le brake_map V110 est reconstitué EN MÉMOIRE (cascade
     chronologique) sans toucher `hybride_selection_history`.

────────────────────────────────────────────────────────────────────────
SCOPE ENGINE TESTÉ
────────────────────────────────────────────────────────────────────────

  ✓ V104 stratification zones                (engine/hybride_base.py:763)
  ✓ V105 saturation intra-batch              (engine/hybride_base.py:834)
  ✓ V106 unpopularity                        (engine/hybride_base.py:841)
  ✓ V107 ESI filter                          (engine/hybride_base.py:919)
  ✓ V110 persistent brake T-1/T-2            (engine/hybride_base.py:828) ← CIBLE
  ✓ Contraintes pair/impair/somme/dispersion (engine/hybride_base.py:664)
  ✗ V92 decay state (désactivé MVP)
"""

from __future__ import annotations

# ════════════════════════════════════════════════════════════════════════
# Standard library + project bootstrap
# ════════════════════════════════════════════════════════════════════════
import argparse
import asyncio
import dataclasses
import json
import logging
import os
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from math import comb
from pathlib import Path
from typing import Any

# Bootstrap : add project root to sys.path so `engine` / `config` / `db_cloudsql`
# resolve when this script is run from anywhere (`python tools/backtest_hybride.py`).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ════════════════════════════════════════════════════════════════════════
# Project imports (after sys.path bootstrap)
# ════════════════════════════════════════════════════════════════════════
from config.engine import LOTO_CONFIG, EM_CONFIG, EngineConfig, LOTO_ZONES, EM_ZONES
from engine.hybride_base import HybrideEngine
from db_cloudsql import get_connection, init_pool, close_pool
# V_X.F LOT 2 — Briques signature statistique (LOT 1, livré)
from tools.signature_features import (
    FEATURE_NAMES,
    apply_fdr_correction,
    build_bins,
    compute_feature_jsd,
    compute_noise_floor,
    extract_features,
    generate_random_baseline,
)
# LOT S1 — briques secondaire (feature reine `*_in_T1`), additives
from tools.signature_features import (
    SECONDARY_FEATURE_NAMES,
    build_secondary_bins,
    extract_secondary_in_t1,
    generate_secondary_in_t1_baseline,
)
# LOT S2 — briques secondaire POSITIONNELLES (non-temporelles), additives
from tools.signature_features import (
    SECONDARY_POSITIONAL_NAMES,
    extract_secondary_positional,
    generate_secondary_positional_baseline,
)
# V_X.B — briques stratification CATÉGORIELLE (additives)
from tools.signature_features import (
    STRATIFICATION_BINS,
    classify_stratification_index,
    generate_stratification_baseline,
)

# Matplotlib in Agg backend (headless / Windows-safe)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402 — transitif via matplotlib, utilisé par LOT 3 plots

logger = logging.getLogger("backtest_hybride")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


# ════════════════════════════════════════════════════════════════════════
# Constants : paliers, hasard théorique, stratification
# ════════════════════════════════════════════════════════════════════════

HARNESS_VERSION = "v1.0"

# V_X.F LOT 2 — Baseline aléatoire pour signature statistique Tier 2
_SIGNATURE_BASELINE_N: int = 100_000
_SIGNATURE_BASELINE_SEED: int = 42
# Features Tier 1 (stats descriptives) — invariants MOUS uniquement.
# freq_1_31 et nb_pairs exclus (pas de bornes hard dans engine config —
# uniquement reportés via Tier 2 JSD).
_TIER1_FEATURES: tuple[str, ...] = ("somme", "dispersion", "std", "nb_consecutifs", "esi")

# LOT noise-floor — plancher de bruit Monte Carlo + correction FDR (opt-in).
# K différencié : boules ≥10 bins (1000 suffit) / secondaire 2-3 bins (10000
# pour lisser le quantile 95% sur petit univers, coût négligeable).
_NOISE_FLOOR_K_BALLS: int = 1000
_NOISE_FLOOR_K_SECONDARY: int = 10_000
_NOISE_FLOOR_QUANTILE: float = 0.95
_NOISE_FLOOR_FDR_ALPHA: float = 0.05

# LOT 3 — seuil d'effet pratique (taille d'effet JSD). Distingue un signal
# MATÉRIEL FORT d'un matériel NÉGLIGEABLE. Calé sur l'échelle empirique des runs :
# signatures fortes boules 0.15-0.30 / *_in_T1 0.04-0.13 ; micro-biais positionnelles
# 0.0002-0.01. Le trou naturel ~0.01-0.04 -> 0.02 sépare proprement. Paramétrable.
_EFFECT_SIZE_THRESHOLD: float = 0.02

# 7 paliers Loto (descending). Key = (n_balls_match, n_secondary_match).
LOTO_PALIERS: list[tuple[str, int, int]] = [
    ("5_boules_chance", 5, 1),
    ("5_boules", 5, 0),
    ("4_boules_chance", 4, 1),
    ("4_boules", 4, 0),
    ("3_boules_chance", 3, 1),
    ("3_boules", 3, 0),
    ("2_boules", 2, 0),
]

# 13 paliers EuroMillions. Secondary = nombre d'étoiles matchées (0/1/2).
EM_PALIERS: list[tuple[str, int, int]] = [
    ("5_boules_2etoiles", 5, 2),
    ("5_boules_1etoile", 5, 1),
    ("5_boules", 5, 0),
    ("4_boules_2etoiles", 4, 2),
    ("4_boules_1etoile", 4, 1),
    ("4_boules", 4, 0),
    ("3_boules_2etoiles", 3, 2),
    ("3_boules_1etoile", 3, 1),
    ("3_boules", 3, 0),
    ("2_boules_2etoiles", 2, 2),
    ("2_boules_1etoile", 2, 1),
    ("2_boules", 2, 0),
    ("1_boule_2etoiles", 1, 2),
]

STRATIFICATION_BUCKETS = ("1_per_zone", "2_in_one_zone", "3_in_one_zone", "libre")


def _hasard_theorique_min_palier_pct(game: str) -> float:
    """Probabilité (%) d'atteindre au moins le palier MINIMUM (gagnante).

    Loto : ≥2 boules sur 5 tirées parmi 49 (palier min = 2 boules).
    EM   : ≥2 boules sur 5 tirées parmi 50 (palier min = 2 boules, étoiles non requises).

    Calcul exact hypergéométrique :
        P(k=i) = C(K,i)·C(N-K,n-i) / C(N,n)
    où N=univers, K=numéros tirés (5), n=numéros pickés (5), i=matchs.
    """
    if game == "loto":
        N, K, n = 49, 5, 5
    else:
        N, K, n = 50, 5, 5
    p_zero = comb(N - K, n) / comb(N, n)
    p_one = comb(K, 1) * comb(N - K, n - 1) / comb(N, n)
    return round(100.0 * (1 - p_zero - p_one), 4)


# ════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass
class BacktestConfig:
    """Snapshot des params engine modifiables pour backtest.

    Defaults = identiques à LOTO_CONFIG / EM_CONFIG (V110 actif T-1=0.20, T-2=0.50).
    Pour tester un hard-exclude T-1 : `BacktestConfig(saturation_brake_persistent_t1=0.0)`.
    """
    saturation_brake_persistent_t1: float = 0.20
    saturation_brake_persistent_t2: float = 0.50
    saturation_persistent_window: int = 2
    saturation_persistent_enabled: bool = True

    @classmethod
    def from_json_file(cls, path: str) -> BacktestConfig:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        valid_keys = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    def to_engine_config(self, base: EngineConfig) -> EngineConfig:
        """Applique les overrides sur LOTO_CONFIG ou EM_CONFIG (frozen → replace)."""
        return dataclasses.replace(base, **asdict(self))


@dataclass
class TirageRecord:
    """Tirage historique réel (depuis table `tirages` ou `tirages_euromillions`)."""
    draw_date: date
    balls: list[int]
    secondary: list[int]  # Loto: [chance], EM: [s1, s2]


@dataclass
class VirtualGrid:
    """Grille canonique virtuelle utilisée pour reconstituer le brake_map cascade."""
    target_date: date
    balls: list[int]
    secondary: list[int]


def _density_histogram(values, bins) -> list[float]:
    """Histogramme normalisé en densité (sum = 1) sans epsilon. Pour plotting.

    Sémantique distincte de `signature_features._histogram_normalize` (qui ajoute
    un epsilon de smoothing pour la KL divergence). Ici on veut une vraie
    densité empirique pour l'affichage des distributions.

    Returns:
        list[float] JSON-friendly de longueur (len(bins) - 1). Zéros partout
        si values vide ou somme nulle.
    """
    n_bins = len(bins) - 1
    if values is None or len(values) == 0:
        return [0.0] * n_bins
    hist, _ = np.histogram(np.asarray(values, dtype=np.float64), bins=bins)
    total = float(hist.sum())
    if total == 0.0:
        return [0.0] * n_bins
    return (hist.astype(np.float64) / total).tolist()


# ════════════════════════════════════════════════════════════════════════
# Main harness class
# ════════════════════════════════════════════════════════════════════════

class BacktestHarness:
    """Backtest harness HYBRIDE — replay historique + comparaison 2 configs.

    Pipeline :
        load_tirages → run_config(cfg_A) + run_config(cfg_B) → compare → export.

    Le brake_map V110 est reconstitué en cascade chronologique EN MÉMOIRE
    (virtual_history list) — `hybride_selection_history` BDD non touchée.
    """

    def __init__(
        self,
        game: str = "loto",
        n_tirages: int = 200,
        n_grilles_per_tirage: int = 100,
        mode: str = "balanced",
        date_max: str | None = None,
    ):
        if game not in ("loto", "em"):
            raise ValueError(f"game must be 'loto' or 'em', got {game!r}")
        self.game = game
        self.n_tirages = n_tirages
        self.n_grilles_per_tirage = n_grilles_per_tirage
        self.mode = mode
        # OOS support : cutoff date YYYY-MM-DD. None = N tirages les plus récents (défaut, inchangé).
        self.date_max = date_max
        self.base_config = LOTO_CONFIG if game == "loto" else EM_CONFIG
        self.paliers = LOTO_PALIERS if game == "loto" else EM_PALIERS
        self.zones = LOTO_ZONES if game == "loto" else EM_ZONES
        self.secondary_count = self.base_config.secondary_count
        self._tirages_cache: list[TirageRecord] | None = None

    # ── DB readers ────────────────────────────────────────────────────

    async def load_tirages(self) -> list[TirageRecord]:
        """SELECT N derniers tirages depuis table prod (READ-ONLY).

        Returns ASC sorted (oldest first) — required for cascade chronologique.
        Cache result : repeated calls (compare = 2 runs) reuse the same list.
        """
        if self._tirages_cache is not None:
            return self._tirages_cache

        table = self.base_config.table_name
        sec_cols = ", ".join(self.base_config.secondary_columns)
        # OOS : si date_max fourni, on borne par le haut → N tirages ENDING <= date_max
        # (fenêtre ancienne). Sinon comportement inchangé (N plus récents).
        where_clause = ""
        params: list[Any] = []
        if self.date_max is not None:
            where_clause = "WHERE date_de_tirage <= %s "
            params.append(self.date_max)
        params.append(int(self.n_tirages))
        sql = (
            f"SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, {sec_cols} "
            f"FROM {table} {where_clause}ORDER BY date_de_tirage DESC LIMIT %s"
        )
        async with get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(sql, tuple(params))
            rows = await cursor.fetchall()

        tirages: list[TirageRecord] = []
        for row in rows:
            balls = [int(row[f"boule_{i}"]) for i in range(1, 6)]
            sec = [int(row[c]) for c in self.base_config.secondary_columns if row.get(c) is not None]
            raw_date = row["date_de_tirage"]
            d = raw_date if isinstance(raw_date, date) else datetime.strptime(str(raw_date), "%Y-%m-%d").date()
            tirages.append(TirageRecord(draw_date=d, balls=sorted(balls), secondary=sorted(sec)))

        # Sort ASC (oldest first) for cascade chronologique
        tirages.sort(key=lambda t: t.draw_date)
        self._tirages_cache = tirages
        logger.info(
            "load_tirages OK : %d tirages from %s to %s",
            len(tirages),
            tirages[0].draw_date if tirages else None,
            tirages[-1].draw_date if tirages else None,
        )
        return tirages

    # ── Brake map virtuel (cascade chronologique) ─────────────────────

    @staticmethod
    def _build_brake_map_virtuel(
        virtual_history: list[VirtualGrid],
        t1_mult: float,
        t2_mult: float,
        window: int,
        attr: str,
    ) -> dict[int, float]:
        """Construit le brake_map en lisant virtual_history[-window:].

        Mirrors la logique de services/selection_history.get_persistent_brake_map :
            - T-1 (dernier ajouté) → t1_mult
            - T-2 (avant-dernier) → t2_mult
            - Collision T-1∩T-2 → min(mult) (brake plus fort gagne)

        Args:
            virtual_history: list ordonnée chronologiquement (le plus ancien en [0]).
            attr: "balls" ou "secondary" — quel attribut de VirtualGrid utiliser.
        """
        if not virtual_history or window <= 0:
            return {}
        # tier_multipliers indexed by position from-the-end : 0 = T-1, 1 = T-2
        tier_multipliers = (t1_mult, t2_mult)
        max_tier = min(window, len(tier_multipliers), len(virtual_history))
        brake: dict[int, float] = {}
        for tier in range(max_tier):
            grid = virtual_history[-(tier + 1)]
            nums = getattr(grid, attr)
            mult = tier_multipliers[tier]
            for n in nums:
                if n in brake:
                    brake[n] = min(brake[n], mult)
                else:
                    brake[n] = mult
        return brake

    # ── Engine invocation ─────────────────────────────────────────────

    def _tirage_to_recent_draw_dict(self, tirage: TirageRecord) -> dict:
        """Mappe un TirageRecord vers le format dict attendu par les pénalisations.

        Format identique à `HybrideEngine.get_recent_draws` (consommé par
        `apply_boule_penalties` via `boule_1..5` et `apply_secondary_penalties`
        via `secondary_columns`). Sert à injecter le T-1 RELATIF au target rejoué
        (fix future-leak) à la place du fetch absolu `get_recent_draws`.
        """
        d: dict = {f"boule_{i}": b for i, b in enumerate(tirage.balls, 1)}
        for col, val in zip(self.base_config.secondary_columns, tirage.secondary):
            d[col] = val
        d["date_de_tirage"] = str(tirage.draw_date)
        return d

    async def _generate_grilles(
        self,
        engine: HybrideEngine,
        brake_map_balls: dict[int, float],
        brake_map_secondary: dict[int, float],
        recent_draws: list[dict] | None = None,
    ) -> list[dict]:
        """Génère N grilles via engine.generate_grids().

        Bypass `services.selection_history.get_persistent_brake_map` en passant
        directement nos brake_maps virtuels en kwargs. `decay_state=None` par
        choix MVP (cf. docstring module).

        `recent_draws` : T-1 RELATIF au target rejoué (fix future-leak). Toujours
        une liste (jamais None) côté run_config — [] à idx=0. Passé tel quel à
        generate_grids qui court-circuite alors le fetch absolu get_recent_draws.
        """
        result = await engine.generate_grids(
            n=self.n_grilles_per_tirage,
            mode=self.mode,
            lang="fr",
            anti_collision=False,
            forced_nums=None,
            forced_secondary=None,
            exclusions=None,
            decay_state=None,
            persistent_brake_map=brake_map_balls if brake_map_balls else None,
            persistent_brake_map_secondary=brake_map_secondary if brake_map_secondary else None,
            _get_connection=get_connection,
            recent_draws=recent_draws,
        )
        return result.get("grids", [])

    # ── Metrics ───────────────────────────────────────────────────────

    def _compute_matches(
        self,
        grille: dict,
        tirage_reel: TirageRecord,
    ) -> tuple[int, int]:
        """Retourne (n_balls_match, n_secondary_match) pour 1 grille vs tirage réel."""
        grille_balls = set(grille.get("nums", []))
        # secondary key depends on game : 'chance' (int) for Loto, 'etoiles' (list) for EM
        sec_key = self.base_config.secondary_name
        sec_val = grille.get(sec_key)
        if isinstance(sec_val, int):
            grille_secondary = {sec_val}
        elif isinstance(sec_val, (list, tuple, set)):
            grille_secondary = set(sec_val)
        else:
            grille_secondary = set()
        n_balls = len(grille_balls & set(tirage_reel.balls))
        n_secondary = len(grille_secondary & set(tirage_reel.secondary))
        return n_balls, n_secondary

    def _palier_atteint(self, n_balls: int, n_secondary: int) -> str | None:
        """Retourne le NOM du palier le plus élevé atteint, ou None si non gagnante.

        Les paliers sont ordonnés descendant — on retourne le PREMIER matchant.
        """
        for palier_name, req_balls, req_secondary in self.paliers:
            if n_balls >= req_balls and n_secondary >= req_secondary:
                return palier_name
        return None

    def _compute_stratification(self, balls: list[int]) -> str:
        """Catégorise la stratification d'une grille selon self.zones.

        - "1_per_zone"      : exactement 1 dans chaque zone (5 zones uniques touchées)
        - "2_in_one_zone"   : max(count par zone) == 2
        - "3_in_one_zone"   : max(count par zone) == 3
        - "libre"           : max ≥ 4 (4 ou 5 dans une zone)
        """
        # V_X.B — délègue à la fonction pure (source unique de vérité), puis
        # mappe l'index -> nom de bucket. Comportement strictement inchangé.
        return STRATIFICATION_BUCKETS[
            classify_stratification_index(balls, self.zones)
        ]

    # ── Pipeline principal ────────────────────────────────────────────

    async def run_config(
        self,
        cfg: BacktestConfig,
        *,
        include_secondary: bool = False,
        noise_floor: bool = False,
    ) -> dict:
        """Pipeline cascade chronologique pour 1 config.

        Pour chaque tirage T historique (ordonné ASC) :
          1. Construit brake_map_balls + brake_map_secondary depuis virtual_history[-window:]
          2. Génère N grilles via engine.generate_grids
          3. Ajoute la 1ère grille générée (sorted by score DESC) à virtual_history
          4. Compare les N grilles aux numéros réels de T, agrège par palier

        LOT S1 — `include_secondary` (kwarg-only, défaut False) : si True, accumule
        EN BOUCLE la feature reine `*_in_T1` (overlap secondaire grille ∩ T-1
        relatif, skip idx=0) dans un dict parallèle, exposé sous tier2["secondary"].
        Défaut False = comportement strictement inchangé (clé absente).

        Returns:
            {
              "total_grilles_generated": int,
              "gagnantes_pct_global": float,
              "gagnantes_per_palier": dict[str, int],
              "stratification_distribution_generated": dict[str, float],
              "ratio_observed_vs_hasard": float,
            }
        """
        engine_cfg = cfg.to_engine_config(self.base_config)
        engine = HybrideEngine(engine_cfg)
        tirages = await self.load_tirages()

        gagnantes_per_palier: dict[str, int] = {name: 0 for name, _, _ in self.paliers}
        strat_counts: dict[str, int] = {b: 0 for b in STRATIFICATION_BUCKETS}
        total_grilles = 0
        n_gagnantes = 0
        # V_X.F LOT 2 — Accumulation valeurs brutes par feature (histos en fin de run)
        feature_values: dict[str, list[float]] = {fname: [] for fname in FEATURE_NAMES}
        # LOT S1 — accumulateur SECONDAIRE parallèle (rempli IN-LOOP, idx>0 only —
        # la feature *_in_T1 dépend du contexte temporel, cf. audit vigilance #1/#6)
        secondary_feature_values: dict[str, list[float]] = {}
        # LOT S2 — accumulateur POSITIONNEL parallèle (rempli IN-LOOP mais SANS
        # garde idx>0 : non-temporel, toutes les grilles comptent y compris idx=0).
        # Séparé de secondary_feature_values (n≈20000 vs n≈19900 pour *_in_T1).
        positional_feature_values: dict[str, list[float]] = {}

        virtual_history: list[VirtualGrid] = []
        t_start = time.monotonic()

        for idx, tirage in enumerate(tirages):
            brake_balls = self._build_brake_map_virtuel(
                virtual_history,
                cfg.saturation_brake_persistent_t1,
                cfg.saturation_brake_persistent_t2,
                cfg.saturation_persistent_window,
                attr="balls",
            )
            brake_secondary = self._build_brake_map_virtuel(
                virtual_history,
                cfg.saturation_brake_persistent_t1,
                cfg.saturation_brake_persistent_t2,
                cfg.saturation_persistent_window,
                attr="secondary",
            )

            # Fix future-leak : recent_draws RELATIFS au target rejoué (T-1, T-2, …)
            # construits depuis la fenêtre chronologique STRICTEMENT antérieure.
            # ⚠️ INVARIANT : toujours une liste, jamais None — [] à idx=0 (aucun T-1)
            # évite le re-fallback get_recent_draws absolu (re-leak). reversed →
            # T-1 en position 0 (aligné format DESC de get_recent_draws).
            _start = max(0, idx - engine_cfg.penalty_window)
            _window_asc = tirages[_start:idx]  # exclut le target tirages[idx]
            recent = [self._tirage_to_recent_draw_dict(t) for t in reversed(_window_asc)]

            try:
                grilles = await self._generate_grilles(
                    engine, brake_balls, brake_secondary, recent_draws=recent,
                )
            except Exception as exc:
                logger.warning("Tirage %s skipped — generate_grids error: %s", tirage.draw_date, exc)
                continue

            # Determine the canonical grid (highest score, mirrors prod V137.B sort)
            canonical = grilles[0] if grilles else None
            if canonical is not None:
                sec_val = canonical.get(self.base_config.secondary_name)
                if isinstance(sec_val, int):
                    sec_list = [sec_val]
                elif isinstance(sec_val, (list, tuple, set)):
                    sec_list = sorted(sec_val)
                else:
                    sec_list = []
                virtual_history.append(VirtualGrid(
                    target_date=tirage.draw_date,
                    balls=sorted(canonical.get("nums", [])),
                    secondary=sec_list,
                ))
                # Cap virtual_history to needed window (avoid unbounded growth)
                _max_window = max(cfg.saturation_persistent_window, 2)
                if len(virtual_history) > _max_window:
                    virtual_history = virtual_history[-_max_window:]

            # LOT S1 — T-1 RELATIF pour la feature reine *_in_T1. None si flag off
            # ou idx=0 (pas de T-1 → on SKIP, pas de faux 0 — audit vigilance #6).
            prev_secondary = (
                tirages[idx - 1].secondary
                if (include_secondary and idx > 0) else None
            )

            # Aggregate metrics for ALL N grilles
            for grille in grilles:
                total_grilles += 1
                n_balls, n_secondary = self._compute_matches(grille, tirage)
                palier = self._palier_atteint(n_balls, n_secondary)
                if palier:
                    gagnantes_per_palier[palier] += 1
                    n_gagnantes += 1
                bucket = self._compute_stratification(grille.get("nums", []))
                strat_counts[bucket] += 1
                # V_X.F LOT 2 — Extraction features V_X.F (valeurs brutes)
                feat = extract_features(grille, num_max=self.base_config.num_max)
                for fname, fval in feat.items():
                    feature_values[fname].append(fval)
                # LOT S1 — feature reine secondaire *_in_T1 (accumulée in-loop)
                if prev_secondary is not None:
                    sec_feat = extract_secondary_in_t1(
                        grille.get(self.base_config.secondary_name), prev_secondary,
                    )
                    for sfname, sfval in sec_feat.items():
                        secondary_feature_values.setdefault(sfname, []).append(sfval)
                # LOT S2 — features POSITIONNELLES (non-temporelles : PAS de garde
                # idx>0, toutes les grilles comptent). Gardé par include_secondary.
                if include_secondary:
                    pos_feat = extract_secondary_positional(
                        grille.get(self.base_config.secondary_name), self.game,
                    )
                    for pfname, pfval in pos_feat.items():
                        positional_feature_values.setdefault(pfname, []).append(pfval)

            if (idx + 1) % 25 == 0:
                elapsed = time.monotonic() - t_start
                logger.info(
                    "  [%s] tirage %d/%d done — %d gagnantes / %d grilles (%.2fs)",
                    cfg.saturation_brake_persistent_t1,
                    idx + 1, len(tirages), n_gagnantes, total_grilles, elapsed,
                )

        gagnantes_pct = round(100.0 * n_gagnantes / total_grilles, 4) if total_grilles else 0.0
        strat_distribution = {
            b: round(strat_counts[b] / total_grilles, 4) if total_grilles else 0.0
            for b in STRATIFICATION_BUCKETS
        }
        hasard_pct = _hasard_theorique_min_palier_pct(self.game)
        ratio = round(gagnantes_pct / hasard_pct, 4) if hasard_pct > 0 else 0.0

        # V_X.F LOT 2 — Calculs tier1/tier2 EN FIN de run (rebinning possible
        # sans refaire la boucle). 100% additif : 3 nouvelles clés côte à côte
        # des 5 historiques (contrat consommé par grid_search_hybride.py).
        tier1 = self._compute_tier1_stats(feature_values)
        # V_X.F LOT 3 — passer tirages pour histos overlay narratif
        tier2 = self._compute_tier2_signature(
            feature_values, total_grilles, tirages=tirages,
        )
        # LOT S1 — bloc secondaire ADDITIF, uniquement si --include-secondary.
        # Clé tier2["secondary"] côte à côte de tier2["feature_jsd"] boules
        # (jamais touché). Absente si flag off → contrat boules strictement inchangé.
        if include_secondary:
            # LOT S2 — positionnelles passées EN PLUS (non-temporelles, baseline
            # simple). Le même flag --include-secondary active reine + positionnelles.
            tier2["secondary"] = self._compute_tier2_secondary(
                secondary_feature_values, positional_feature_values, tirages=tirages,
            )
        # V_X.B — bloc signature STRATIFICATION (catégorielle, baseline hasard),
        # gated sous --noise-floor (signature des boules ; pas de flag dédié).
        # Rangé sous tier2["stratification"] AVANT _attach_noise_floor (qui lit son
        # JSD pour le plancher + l'englobe dans FDR/is_material/effect_tier).
        if noise_floor:
            tier2["stratification"] = self._compute_tier2_stratification(
                strat_counts, total_grilles, tirages=tirages,
            )
        # LOT noise-floor — plancher Monte Carlo + verdict FDR GLOBAL (ADDITIF,
        # opt-in). Ne touche AUCUNE clé existante de tier2 ; ajoute 3 clés au
        # niveau tier2. FDR global sur boules + *_in_T1 + positionnelles (si présent).
        if noise_floor:
            self._attach_noise_floor(
                tier2, feature_values, secondary_feature_values, positional_feature_values,
            )
        by_construction = {
            "stratification": (
                "1_per_zone forcée via _draw_stratified "
                "(engine/hybride_base.py:763-790)"
            ),
            "monochrome": (
                "hard-rejected (parité ∈ {1..4}, "
                "engine/hybride_base.py:669-670)"
            ),
        }

        return {
            # Clés historiques — INTOUCHÉES (contrat dur grid_search_hybride + compare)
            "total_grilles_generated": total_grilles,
            "gagnantes_pct_global": gagnantes_pct,
            "gagnantes_per_palier": gagnantes_per_palier,
            "stratification_distribution_generated": strat_distribution,
            "ratio_observed_vs_hasard": ratio,
            # V_X.F LOT 2 — 3 nouvelles clés (ADDITIF strict)
            "tier1": tier1,
            "tier2": tier2,
            "by_construction": by_construction,
        }

    def _stratification_empirique_real(self, tirages: list[TirageRecord]) -> dict[str, float]:
        """Distribution stratification sur les tirages réels (palier de référence)."""
        counts: dict[str, int] = {b: 0 for b in STRATIFICATION_BUCKETS}
        for t in tirages:
            bucket = self._compute_stratification(t.balls)
            counts[bucket] += 1
        n = len(tirages) if tirages else 1
        return {b: round(counts[b] / n, 4) for b in STRATIFICATION_BUCKETS}

    # ── V_X.F LOT 2 — Tier 1 / Tier 2 calculators ────────────────────

    def _compute_tier1_stats(
        self, feature_values: dict[str, list[float]],
    ) -> dict[str, dict]:
        """Tier 1 — stats descriptives continues sur invariants MOUS.

        Pour chaque feature ∈ _TIER1_FEATURES : mean/median/std/min/max
        + % hors bornes engine config quand applicable (somme, dispersion,
        nb_consecutifs, esi). std reporté sans bornes (pas de contrainte engine).

        freq_1_31 et nb_pairs sont volontairement exclus (pas de bornes
        dures engine — reportés uniquement via Tier 2 JSD).

        Args:
            feature_values: dict[str, list[float]] accumulé pendant run_config.

        Returns:
            dict[str, dict] — 1 entrée par feature avec stats + bornes config.
            Échantillon vide → entrée avec n=0 (pas de crash).
        """
        cfg = self.base_config
        # Bornes engine pour % out-of-bounds par feature
        bounds_map: dict[str, dict] = {
            "somme": {"lo": cfg.somme_min, "hi": cfg.somme_max},
            "dispersion": {"lo": cfg.dispersion_min, "hi": None},
            "nb_consecutifs": {"lo": None, "hi": cfg.max_consecutifs},
            "esi": {"lo": cfg.esi_min, "hi": cfg.esi_max},
            "std": {"lo": None, "hi": None},
        }

        out: dict[str, dict] = {}
        for fname in _TIER1_FEATURES:
            values = feature_values.get(fname, [])
            n = len(values)
            if n == 0:
                out[fname] = {"n": 0}
                continue
            entry: dict = {
                "n": n,
                "mean": round(statistics.mean(values), 4),
                "median": round(statistics.median(values), 4),
                "std": round(statistics.stdev(values), 4) if n >= 2 else 0.0,
                "min": round(min(values), 4),
                "max": round(max(values), 4),
            }
            b = bounds_map.get(fname, {})
            lo, hi = b.get("lo"), b.get("hi")
            if lo is not None and hi is not None:
                pct_oob = sum(1 for v in values if v < lo or v > hi) / n
                entry["pct_out_of_bounds"] = round(100.0 * pct_oob, 4)
                entry["bounds"] = [lo, hi]
            elif lo is not None:
                pct_below = sum(1 for v in values if v < lo) / n
                entry["pct_below_min"] = round(100.0 * pct_below, 4)
                entry["min_threshold"] = lo
            elif hi is not None:
                pct_above = sum(1 for v in values if v > hi) / n
                entry["pct_above_max"] = round(100.0 * pct_above, 4)
                entry["max_threshold"] = hi
            out[fname] = entry
        return out

    def _compute_tier2_signature(
        self,
        feature_values: dict[str, list[float]],
        n_hybride_samples: int,
        *,
        tirages: list[TirageRecord] | None = None,
    ) -> dict:
        """Tier 2 — JSD per-feature HYBRIDE vs random pur baseline.

        JSD per-feature uniquement. Aucune JSD jointe multivariée.
        Aucun score composite scalaire (on reporte le vecteur).
        Baseline cacheée via lru_cache (signature_features.generate_random_baseline).

        V_X.F LOT 3 — ajout kwarg-only `tirages` (additif) : si fourni,
        extrait les features des vrais tirages historiques pour overlay
        narratif dans plot_signature_distributions. Les histogrammes
        normalisés des 3 distributions (HYBRIDE / random pur / vrais
        tirages) sont stockés dans la clé "histograms" pour replot ultérieur
        sans recalcul.

        Args:
            feature_values: dict[str, list[float]] accumulé pendant run_config.
            n_hybride_samples: total_grilles_generated (pour metadata).
            tirages: list[TirageRecord] — vrais tirages pour overlay narratif.
                     None (default) → "real_tirages" sera None dans histograms.

        Returns:
            dict avec clés "feature_jsd" (dict 7 features → float),
            "histograms" (dict feature → {bins, hybride, random, real_tirages}),
            "baseline" (metadata), "base" ("e"), "n_hybride_samples".
        """
        num_max = self.base_config.num_max
        baseline = generate_random_baseline(
            n=_SIGNATURE_BASELINE_N,
            num_max=num_max,
            k=self.base_config.num_count,
            seed=_SIGNATURE_BASELINE_SEED,
        )

        # V_X.F LOT 3 — extraction features des vrais tirages (overlay narratif)
        real_tirages_features: dict[str, list[float]] = {fn: [] for fn in FEATURE_NAMES}
        if tirages:
            for t in tirages:
                feat = extract_features({"nums": t.balls}, num_max=num_max)
                for fn, fv in feat.items():
                    real_tirages_features[fn].append(fv)

        feature_jsd: dict[str, float] = {}
        histograms: dict[str, dict] = {}
        for fname in FEATURE_NAMES:
            hybride_vals = feature_values.get(fname, [])
            baseline_vals = [b[fname] for b in baseline]
            real_vals = real_tirages_features.get(fname, [])
            bins = build_bins(fname, num_max=num_max)
            feature_jsd[fname] = round(
                compute_feature_jsd(hybride_vals, baseline_vals, bins),
                6,
            )
            # V_X.F LOT 3 — histogrammes normalisés (densité, sans epsilon)
            # pour plot_signature_distributions. .tolist() pour JSON-safe.
            histograms[fname] = {
                "bins": bins.tolist(),
                "hybride": _density_histogram(hybride_vals, bins),
                "random": _density_histogram(baseline_vals, bins),
                "real_tirages": _density_histogram(real_vals, bins) if real_vals else None,
            }

        return {
            "feature_jsd": feature_jsd,
            "histograms": histograms,
            "baseline": {
                "n": _SIGNATURE_BASELINE_N,
                "seed": _SIGNATURE_BASELINE_SEED,
                "source": "random.sample uniform",
                "num_max": num_max,
            },
            "base": "e",
            "n_hybride_samples": n_hybride_samples,
        }

    def _compute_tier2_secondary(
        self,
        secondary_feature_values: dict[str, list[float]],
        positional_feature_values: dict[str, list[float]] | None = None,
        *,
        tirages: list[TirageRecord] | None = None,
    ) -> dict:
        """LOT S1+S2 — Tier 2 SECONDAIRE : JSD `*_in_T1` (temporel) + positionnelles.

        Feature reine `*_in_T1` (chance_in_T1 Loto / etoiles_in_T1 EM) vs baseline
        APPARIÉE (LOT S1) + features POSITIONNELLES (chance_value / etoiles_basse,
        haute, ecart) vs baseline SIMPLE non appariée (LOT S2). Boucles SÉPARÉES de
        la boucle boules FEATURE_NAMES (audit vigilance #2), fusionnées dans les
        MÊMES dicts feature_jsd / histograms (additif).

        Baseline `*_in_T1` = SIMULATION APPARIÉE (generate_secondary_in_t1_baseline) :
        overlap secondaire random vs T-1 random indépendant (arbitrage Jyppy #1).
        Baseline positionnelle = SIMPLE (generate_secondary_positional_baseline) :
        tirage random uniforme du secondaire seul, PAS de T-1 (LOT S2).

        Overlay `real_tirages` :
            - `*_in_T1` : appariement SÉQUENTIEL (|T_i ∩ T_{i-1}|), feature temporelle.
            - positionnelles : extraction NON-temporelle de chaque tirage (pas
              d'appariement T_i/T_{i-1} — audit LOT S2 vigilance #5, piège copier-coller).

        Args:
            secondary_feature_values: dict accumulé in-loop (`*_in_T1`, idx>0).
            positional_feature_values: dict accumulé in-loop (positionnelles, tous idx).
                None/absent → bloc positionnel non calculé (rétrocompat S1).
            tirages: vrais tirages pour l'overlay narratif réel.

        Returns:
            dict {feature_jsd, histograms, baseline, base, n_hybride_samples,
            anj_disclaimer}. feature_jsd/histograms contiennent `*_in_T1` ET
            positionnelles côte à côte.
        """
        positional_feature_values = positional_feature_values or {}
        cfg = self.base_config
        sec_min, sec_max, count = cfg.secondary_min, cfg.secondary_max, cfg.secondary_count
        feature_names = SECONDARY_FEATURE_NAMES.get(self.game, ())

        baseline = generate_secondary_in_t1_baseline(
            n=_SIGNATURE_BASELINE_N,
            sec_min=sec_min,
            sec_max=sec_max,
            count=count,
            seed=_SIGNATURE_BASELINE_SEED,
        )

        # Overlay vrais tirages : appariement séquentiel réel (T_i vs T_{i-1}).
        real_secondary_values: dict[str, list[float]] = {}
        if tirages:
            for i in range(1, len(tirages)):
                sec_feat = extract_secondary_in_t1(
                    tirages[i].secondary, tirages[i - 1].secondary,
                )
                for fn, fv in sec_feat.items():
                    real_secondary_values.setdefault(fn, []).append(fv)

        feature_jsd: dict[str, float] = {}
        histograms: dict[str, dict] = {}
        for fname in feature_names:
            hybride_vals = secondary_feature_values.get(fname, [])
            baseline_vals = [b[fname] for b in baseline if fname in b]
            real_vals = real_secondary_values.get(fname, [])
            bins = build_secondary_bins(fname)
            feature_jsd[fname] = round(
                compute_feature_jsd(hybride_vals, baseline_vals, bins),
                6,
            )
            histograms[fname] = {
                "bins": bins.tolist(),
                "hybride": _density_histogram(hybride_vals, bins),
                "random": _density_histogram(baseline_vals, bins),
                "real_tirages": _density_histogram(real_vals, bins) if real_vals else None,
            }

        # ── LOT S2 — features POSITIONNELLES (non-temporelles, baseline SIMPLE) ──
        positional_names = SECONDARY_POSITIONAL_NAMES.get(self.game, ())
        if positional_names:
            pos_baseline = generate_secondary_positional_baseline(
                n=_SIGNATURE_BASELINE_N,
                sec_min=sec_min,
                sec_max=sec_max,
                count=count,
                seed=_SIGNATURE_BASELINE_SEED,
                game=self.game,
            )
            # Overlay vrais tirages : extraction NON-temporelle (PAS d'appariement
            # T_i/T_{i-1} — c'est le piège copier-coller du bloc *_in_T1 ci-dessus).
            real_positional_values: dict[str, list[float]] = {}
            if tirages:
                for t in tirages:
                    pos_feat = extract_secondary_positional(t.secondary, self.game)
                    for fn, fv in pos_feat.items():
                        real_positional_values.setdefault(fn, []).append(fv)

            for fname in positional_names:
                hybride_vals = positional_feature_values.get(fname, [])
                baseline_vals = [b[fname] for b in pos_baseline if fname in b]
                real_vals = real_positional_values.get(fname, [])
                bins = build_secondary_bins(fname)
                feature_jsd[fname] = round(
                    compute_feature_jsd(hybride_vals, baseline_vals, bins),
                    6,
                )
                histograms[fname] = {
                    "bins": bins.tolist(),
                    "hybride": _density_histogram(hybride_vals, bins),
                    "random": _density_histogram(baseline_vals, bins),
                    "real_tirages": _density_histogram(real_vals, bins) if real_vals else None,
                }

        n_hybride_samples = sum(len(v) for v in secondary_feature_values.values())
        return {
            "feature_jsd": feature_jsd,
            "histograms": histograms,
            "baseline": {
                "n": _SIGNATURE_BASELINE_N,
                "seed": _SIGNATURE_BASELINE_SEED,
                "source": "paired random overlap (secondary random vs T-1 random)",
                "sec_min": sec_min,
                "sec_max": sec_max,
                "count": count,
            },
            "base": "e",
            "n_hybride_samples": n_hybride_samples,
            # Garde-fou ANJ : le recouvrement T-1 est un ARTEFACT DE CONSTRUCTION
            # du moteur (hard-exclude / brake des numéros récents), PAS un biais du
            # jeu ni une probabilité de gain. Un creux sous le hasard = signature de
            # la rotation anti-répétition — neutre, jamais une promesse de gain.
            "anj_disclaimer": (
                "Le recouvrement avec le tirage T-1 mesure un artefact de "
                "construction du moteur (hard-exclude/brake des numeros recents), "
                "PAS un biais du jeu ni une probabilite de gain. Un creux sous le "
                "hasard = signature de la rotation anti-repetition, neutre."
            ),
        }

    def _compute_tier2_stratification(
        self,
        strat_counts: dict[str, int],
        total_grilles: int,
        *,
        tirages: list[TirageRecord] | None = None,
    ) -> dict:
        """V_X.B — Tier 2 STRATIFICATION : JSD de la signature catégorielle vs hasard.

        La stratification (répartition des 5 boules dans les 5 zones) est une
        variable CATÉGORIELLE à 4 modalités. Approche (a) : catégories encodées en
        INDICES 0-3, bins STRATIFICATION_BINS [0,1,2,3,4] → compute_feature_jsd
        s'applique TEL QUEL (zéro fonction JSD dédiée).

        HYBRIDE : indices reconstruits depuis strat_counts (déjà comptés in-loop —
        gratuit, exact ; l'ordre est indifférent à l'histogramme).
        Baseline : HASARD uniforme (generate_stratification_baseline, lru_cache).
        Overlay réel : _stratification_empirique_real sur les vrais tirages.

        Bloc dédié rangé sous tier2["stratification"] (miroir de tier2["secondary"])
        — JAMAIS dans tier2["feature_jsd"] boules (régression plots/build_bins).

        Args:
            strat_counts: comptes HYBRIDE par bucket (dict bucket -> int).
            total_grilles: nombre total de grilles générées (sanity + n_samples).
            tirages: vrais tirages pour l'overlay narratif réel.

        Returns:
            dict {feature_jsd, hybride_distribution, baseline_distribution,
            real_distribution, base, n_hybride_samples}.
        """
        cfg = self.base_config
        # HYBRIDE : reconstruction du tableau d'indices depuis les comptes.
        hybride_values: list[int] = []
        for idx, bucket in enumerate(STRATIFICATION_BUCKETS):
            hybride_values.extend([idx] * strat_counts[bucket])
        # Sanity : la somme des comptes doit égaler le total de grilles.
        if len(hybride_values) != total_grilles:
            logger.warning(
                "[STRATIFICATION] somme counts %d != total_grilles %d",
                len(hybride_values), total_grilles,
            )

        baseline_values = generate_stratification_baseline(
            n=_SIGNATURE_BASELINE_N,
            num_max=cfg.num_max,
            k=cfg.num_count,
            seed=_SIGNATURE_BASELINE_SEED,
            zones=self.zones,
        )

        jsd = round(
            compute_feature_jsd(hybride_values, baseline_values, STRATIFICATION_BINS),
            6,
        )

        # Distributions (proportions) pour la restitution narrative.
        hybride_distribution = {
            b: round(strat_counts[b] / total_grilles, 4) if total_grilles else 0.0
            for b in STRATIFICATION_BUCKETS
        }
        n_base = len(baseline_values)
        baseline_counts = [0, 0, 0, 0]
        for v in baseline_values:
            baseline_counts[v] += 1
        baseline_distribution = {
            b: round(baseline_counts[i] / n_base, 4) if n_base else 0.0
            for i, b in enumerate(STRATIFICATION_BUCKETS)
        }
        real_distribution = (
            self._stratification_empirique_real(tirages) if tirages else None
        )

        return {
            "feature_jsd": {"stratification": jsd},
            "hybride_distribution": hybride_distribution,
            "baseline_distribution": baseline_distribution,
            "real_distribution": real_distribution,
            "base": "e",
            "n_hybride_samples": total_grilles,
        }

    def _attach_noise_floor(
        self,
        tier2: dict,
        feature_values: dict[str, list[float]],
        secondary_feature_values: dict[str, list[float]],
        positional_feature_values: dict[str, list[float]] | None = None,
        *,
        effect_threshold: float = _EFFECT_SIZE_THRESHOLD,
    ) -> None:
        """LOT noise-floor — attache plancher Monte Carlo + verdict FDR GLOBAL au tier2.

        100% ADDITIF : ne touche AUCUNE clé existante (feature_jsd / histograms /
        baseline, boules ET secondary — les méthodes _compute_tier2_* restent
        intactes). Ajoute 4 clés au niveau tier2 :
            tier2["noise_floor"]      : dict[feature -> compute_noise_floor(...)]
            tier2["is_material"]      : dict[feature -> bool] (verdict FDR B-H)
            tier2["effect_tier"]      : dict[feature -> "bruit"|"materiel_negligeable"|
                                        "materiel_fort"] (LOT 3, taille d'effet JSD)
            tier2["noise_floor_meta"] : params (k_boules, k_secondary, quantile, ...,
                                        effect_size_threshold)

        Modèle nul = Option B (bootstrap de n valeurs avec remise dans la baseline
        100k FIXE, JSD vs cette même réf). Les baselines sont réutilisées via leur
        lru_cache (mêmes args que dans _compute_tier2_* → cache hit, ~instantané).

        ROUTAGE BASELINE (LOT S2) : la baseline du plancher DOIT être celle utilisée
        pour le JSD observé. On aiguille par appartenance au registre :
            - feature ∈ SECONDARY_FEATURE_NAMES    → baseline APPARIÉE (`*_in_T1`)
            - feature ∈ SECONDARY_POSITIONAL_NAMES → baseline SIMPLE (positionnelles)

        Correction FDR GLOBALE : sur l'ensemble des p-values (boules + `*_in_T1` +
        positionnelles) car les tests sont SIMULTANÉS — sans elle, ~30% de faux
        positifs sur 7+ tests (audit + double cross-review).
        """
        positional_feature_values = positional_feature_values or {}
        num_max = self.base_config.num_max
        baseline = generate_random_baseline(
            n=_SIGNATURE_BASELINE_N,
            num_max=num_max,
            k=self.base_config.num_count,
            seed=_SIGNATURE_BASELINE_SEED,
        )

        noise_floor_out: dict[str, dict] = {}
        p_values: dict[str, float] = {}

        feature_jsd = tier2["feature_jsd"]
        for fname in FEATURE_NAMES:
            hybride_vals = feature_values.get(fname, [])
            if len(hybride_vals) == 0:
                continue  # run dégénéré — pas de plancher calculable
            baseline_vals = [b[fname] for b in baseline]
            bins = build_bins(fname, num_max=num_max)
            nf = compute_noise_floor(
                baseline_vals,
                bins,
                n_samples=len(hybride_vals),
                observed_jsd=feature_jsd[fname],
                k=_NOISE_FLOOR_K_BALLS,
                seed=_SIGNATURE_BASELINE_SEED,
                quantile=_NOISE_FLOOR_QUANTILE,
            )
            noise_floor_out[fname] = nf
            p_values[fname] = nf["p_value"]

        # Secondaire : uniquement si le bloc existe (--include-secondary actif).
        if "secondary" in tier2:
            cfg = self.base_config
            sec_baseline = generate_secondary_in_t1_baseline(
                n=_SIGNATURE_BASELINE_N,
                sec_min=cfg.secondary_min,
                sec_max=cfg.secondary_max,
                count=cfg.secondary_count,
                seed=_SIGNATURE_BASELINE_SEED,
            )
            sec_jsd = tier2["secondary"]["feature_jsd"]
            # ── *_in_T1 : baseline APPARIÉE ──────────────────────────────
            for fname in SECONDARY_FEATURE_NAMES.get(self.game, ()):
                hybride_vals = secondary_feature_values.get(fname, [])
                if fname not in sec_jsd or len(hybride_vals) == 0:
                    continue
                baseline_vals = [b[fname] for b in sec_baseline if fname in b]
                bins = build_secondary_bins(fname)
                nf = compute_noise_floor(
                    baseline_vals,
                    bins,
                    n_samples=len(hybride_vals),
                    observed_jsd=sec_jsd[fname],
                    k=_NOISE_FLOOR_K_SECONDARY,
                    seed=_SIGNATURE_BASELINE_SEED,
                    quantile=_NOISE_FLOOR_QUANTILE,
                )
                noise_floor_out[fname] = nf
                p_values[fname] = nf["p_value"]

            # ── LOT S2 — positionnelles : baseline SIMPLE non appariée ────
            positional_names = SECONDARY_POSITIONAL_NAMES.get(self.game, ())
            if positional_names:
                pos_baseline = generate_secondary_positional_baseline(
                    n=_SIGNATURE_BASELINE_N,
                    sec_min=cfg.secondary_min,
                    sec_max=cfg.secondary_max,
                    count=cfg.secondary_count,
                    seed=_SIGNATURE_BASELINE_SEED,
                    game=self.game,
                )
                for fname in positional_names:
                    hybride_vals = positional_feature_values.get(fname, [])
                    if fname not in sec_jsd or len(hybride_vals) == 0:
                        continue
                    baseline_vals = [b[fname] for b in pos_baseline if fname in b]
                    bins = build_secondary_bins(fname)
                    nf = compute_noise_floor(
                        baseline_vals,
                        bins,
                        n_samples=len(hybride_vals),
                        observed_jsd=sec_jsd[fname],
                        k=_NOISE_FLOOR_K_SECONDARY,
                        seed=_SIGNATURE_BASELINE_SEED,
                        quantile=_NOISE_FLOOR_QUANTILE,
                    )
                    noise_floor_out[fname] = nf
                    p_values[fname] = nf["p_value"]

        # ── V_X.B — plancher STRATIFICATION (catégorielle, baseline hasard) ──
        # Baseline rappelée via lru_cache (mêmes args qu'en _compute_tier2_
        # stratification → cache hit instantané). bins = STRATIFICATION_BINS.
        if "stratification" in tier2:
            strat_jsd = tier2["stratification"]["feature_jsd"]["stratification"]
            strat_baseline = generate_stratification_baseline(
                n=_SIGNATURE_BASELINE_N,
                num_max=self.base_config.num_max,
                k=self.base_config.num_count,
                seed=_SIGNATURE_BASELINE_SEED,
                zones=self.zones,
            )
            n_strat = tier2["stratification"]["n_hybride_samples"]
            if n_strat > 0:
                nf = compute_noise_floor(
                    strat_baseline,
                    STRATIFICATION_BINS,
                    n_samples=n_strat,
                    observed_jsd=strat_jsd,
                    k=_NOISE_FLOOR_K_SECONDARY,
                    seed=_SIGNATURE_BASELINE_SEED,
                    quantile=_NOISE_FLOOR_QUANTILE,
                )
                noise_floor_out["stratification"] = nf
                p_values["stratification"] = nf["p_value"]

        # FDR GLOBALE Benjamini-Hochberg sur toutes les features testées.
        fdr = apply_fdr_correction(p_values, alpha=_NOISE_FLOOR_FDR_ALPHA)
        tier2["noise_floor"] = noise_floor_out
        tier2["is_material"] = {fn: fdr[fn]["is_material_fdr"] for fn in fdr}

        # LOT 3 — verdict 3 niveaux (taille d'effet). Additif : ne touche PAS is_material.
        # bruit = non-materiel (FDR) ; sinon subdivise par le seuil JSD.
        jsd_unifie = {
            **tier2["feature_jsd"],
            **tier2.get("secondary", {}).get("feature_jsd", {}),
            **tier2.get("stratification", {}).get("feature_jsd", {}),  # V_X.B
        }
        effect_tier: dict[str, str] = {}
        for fname, materiel in tier2["is_material"].items():
            if not materiel:
                effect_tier[fname] = "bruit"
                continue
            jsd = jsd_unifie.get(fname)
            if jsd is None:
                # défense : feature materielle sans JSD source (ne devrait pas arriver).
                # Conservateur : ne pas sur-classer en fort sans preuve de taille d'effet.
                logger.warning("[EFFECT-TIER] JSD manquant pour %s -> materiel_negligeable", fname)
                effect_tier[fname] = "materiel_negligeable"
                continue
            effect_tier[fname] = "materiel_fort" if jsd >= effect_threshold else "materiel_negligeable"
        tier2["effect_tier"] = effect_tier

        tier2["noise_floor_meta"] = {
            "k_boules": _NOISE_FLOOR_K_BALLS,
            "k_secondary": _NOISE_FLOOR_K_SECONDARY,
            "quantile": _NOISE_FLOOR_QUANTILE,
            "null_model": "bootstrap_vs_fixed_reference",
            "fdr_alpha": _NOISE_FLOOR_FDR_ALPHA,
            "fdr_method": "benjamini_hochberg",
            "effect_size_threshold": effect_threshold,
            "seed": _SIGNATURE_BASELINE_SEED,
        }

    async def compare(
        self,
        cfg_actuel: BacktestConfig,
        cfg_test: BacktestConfig,
        *,
        include_secondary: bool = False,
        noise_floor: bool = False,
    ) -> dict:
        """Run cfg_actuel + cfg_test en cascade, retourne dict complet avec diff."""
        t0 = time.monotonic()
        tirages = await self.load_tirages()

        logger.info("Run config_actuelle ...")
        results_A = await self.run_config(
            cfg_actuel, include_secondary=include_secondary, noise_floor=noise_floor,
        )
        logger.info("Run config_test ...")
        results_B = await self.run_config(
            cfg_test, include_secondary=include_secondary, noise_floor=noise_floor,
        )

        strat_real = self._stratification_empirique_real(tirages)
        hasard_pct = _hasard_theorique_min_palier_pct(self.game)

        # Diff
        delta_per_palier = {
            name: results_B["gagnantes_per_palier"][name] - results_A["gagnantes_per_palier"][name]
            for name, _, _ in self.paliers
        }
        delta_strat = {
            b: round(
                results_B["stratification_distribution_generated"][b]
                - results_A["stratification_distribution_generated"][b],
                4,
            )
            for b in STRATIFICATION_BUCKETS
        }

        elapsed = round(time.monotonic() - t0, 2)
        return {
            "metadata": {
                "harness_version": HARNESS_VERSION,
                "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "game": self.game,
                "n_tirages": self.n_tirages,
                "n_grilles_per_tirage": self.n_grilles_per_tirage,
                "mode": self.mode,
                "include_secondary": include_secondary,
                "noise_floor": noise_floor,
                "tirages_replayed_range": {
                    "first": str(tirages[0].draw_date) if tirages else None,
                    "last": str(tirages[-1].draw_date) if tirages else None,
                },
                "elapsed_seconds": elapsed,
                "limitations_mvp": [
                    "future_leak_calculer_scores_hybrides_accepted",
                    "decay_state_disabled",
                ],
            },
            "config_actuelle": asdict(cfg_actuel),
            "config_test": asdict(cfg_test),
            "hasard_theorique_min_palier_pct": hasard_pct,
            "results_config_actuelle": results_A,
            "results_config_test": results_B,
            "stratification_distribution_real_empirical": strat_real,
            "diff": {
                "delta_gagnantes_pct_global": round(
                    results_B["gagnantes_pct_global"] - results_A["gagnantes_pct_global"], 4
                ),
                "delta_per_palier": delta_per_palier,
                "delta_stratification": delta_strat,
            },
        }

    async def run_oos(
        self,
        cfg: BacktestConfig,
        *,
        include_secondary: bool = False,
        noise_floor: bool = False,
    ) -> dict:
        """OOS mono-config — exécute run_config UNE seule fois (≈ ÷2 vs compare).

        Levier A (perf, offline) : pour un OOS de référence où config_test ==
        config_actuelle, le second run de compare() est redondant. run_oos n'en
        fait qu'UN.

        Format de sortie IDENTIQUE à compare() — `results_config_actuelle` ET
        `results_config_test` pointent sur le MÊME run (diff nul) — pour que les
        exports JSON/PNG existants fonctionnent sans aucun changement.
        """
        t0 = time.monotonic()
        tirages = await self.load_tirages()

        logger.info("Run OOS mono-config (no-compare) ...")
        results = await self.run_config(
            cfg, include_secondary=include_secondary, noise_floor=noise_floor,
        )

        strat_real = self._stratification_empirique_real(tirages)
        hasard_pct = _hasard_theorique_min_palier_pct(self.game)

        elapsed = round(time.monotonic() - t0, 2)
        return {
            "metadata": {
                "harness_version": HARNESS_VERSION,
                "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "game": self.game,
                "n_tirages": self.n_tirages,
                "n_grilles_per_tirage": self.n_grilles_per_tirage,
                "mode": self.mode,
                "run_mode": "single_no_compare",
                "include_secondary": include_secondary,
                "noise_floor": noise_floor,
                "tirages_replayed_range": {
                    "first": str(tirages[0].draw_date) if tirages else None,
                    "last": str(tirages[-1].draw_date) if tirages else None,
                },
                "elapsed_seconds": elapsed,
                "limitations_mvp": [
                    "future_leak_calculer_scores_hybrides_accepted",
                    "decay_state_disabled",
                ],
            },
            "config_actuelle": asdict(cfg),
            "config_test": asdict(cfg),
            "hasard_theorique_min_palier_pct": hasard_pct,
            "results_config_actuelle": results,
            "results_config_test": results,  # même run réutilisé → plots OK, diff nul
            "stratification_distribution_real_empirical": strat_real,
            "diff": {
                "delta_gagnantes_pct_global": 0.0,
                "delta_per_palier": {name: 0 for name, _, _ in self.paliers},
                "delta_stratification": {b: 0.0 for b in STRATIFICATION_BUCKETS},
            },
        }

    # ── Exports ───────────────────────────────────────────────────────

    def export_json(self, results: dict, path: str) -> None:
        """Sérialise les résultats en JSON structuré (cf. format dans le prompt V_X.G)."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        logger.info("JSON exported : %s", path)

    def plot_palier_distribution(self, results: dict, path: str) -> None:
        """Bar chart groupé : distribution gagnantes par palier (cfg_actuel vs cfg_test).

        Ligne horizontale : nombre attendu sous hasard théorique (info repère).
        """
        palier_names = [p[0] for p in self.paliers]
        vals_A = [results["results_config_actuelle"]["gagnantes_per_palier"][n] for n in palier_names]
        vals_B = [results["results_config_test"]["gagnantes_per_palier"][n] for n in palier_names]

        x = list(range(len(palier_names)))
        width = 0.4
        fig, ax = plt.subplots(figsize=(13, 6.5), dpi=120)
        ax.bar([i - width / 2 for i in x], vals_A, width=width, label="config_actuelle", color="#1f77b4")
        ax.bar([i + width / 2 for i in x], vals_B, width=width, label="config_test", color="#ff7f0e")

        ax.set_xticks(x)
        ax.set_xticklabels(palier_names, rotation=30, ha="right", fontsize=9)
        ax.set_ylabel("Nombre de grilles atteignant ce palier")
        meta = results["metadata"]
        ax.set_title(
            f"Distribution gagnantes par palier — {meta['game'].upper()} — "
            f"{meta['n_tirages']} tirages × {meta['n_grilles_per_tirage']} grilles"
        )
        ax.legend()
        ax.grid(True, axis="y", linestyle=":", alpha=0.5)

        # Annotations valeurs sur les barres
        for i, (a, b) in enumerate(zip(vals_A, vals_B)):
            if a > 0:
                ax.text(i - width / 2, a, str(a), ha="center", va="bottom", fontsize=7)
            if b > 0:
                ax.text(i + width / 2, b, str(b), ha="center", va="bottom", fontsize=7)

        fig.tight_layout()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path)
        plt.close(fig)
        logger.info("PNG exported : %s", path)

    def plot_stratification(self, results: dict, path: str) -> None:
        """Pie chart 1×N : distribution stratification (réel vs cfg_actuel vs cfg_test si diff)."""
        cfg_a_diff_b = (
            results["config_actuelle"] != results["config_test"]
        )
        n_panels = 3 if cfg_a_diff_b else 2

        fig, axes = plt.subplots(1, n_panels, figsize=(5 * n_panels, 5.5), dpi=120)
        if n_panels == 2:
            axes = list(axes)

        labels = list(STRATIFICATION_BUCKETS)
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

        def _pie(ax, distribution: dict, title: str):
            vals = [distribution.get(b, 0.0) for b in labels]
            # matplotlib pie autopct expects fractions; we have already fractions
            non_zero_idx = [i for i, v in enumerate(vals) if v > 0.001]
            display_labels = [labels[i] if i in non_zero_idx else "" for i in range(len(labels))]
            ax.pie(
                vals,
                labels=display_labels,
                colors=colors,
                autopct=lambda p: f"{p:.1f}%" if p > 0.5 else "",
                startangle=90,
                textprops={"fontsize": 9},
            )
            ax.set_title(title, fontsize=11)

        _pie(axes[0], results["stratification_distribution_real_empirical"],
             f"Tirages réels ({results['metadata']['n_tirages']})")
        _pie(axes[1], results["results_config_actuelle"]["stratification_distribution_generated"],
             "Grilles générées — config_actuelle")
        if n_panels == 3:
            _pie(axes[2], results["results_config_test"]["stratification_distribution_generated"],
                 "Grilles générées — config_test")

        meta = results["metadata"]
        fig.suptitle(
            f"Distribution stratification — {meta['game'].upper()}",
            fontsize=13, y=1.02,
        )
        fig.tight_layout()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        logger.info("PNG exported : %s", path)

    def plot_summary(self, results: dict, path: str) -> None:
        """Tableau récap + métriques normalisées (matplotlib `ax.table`)."""
        meta = results["metadata"]
        ra = results["results_config_actuelle"]
        rb = results["results_config_test"]
        hasard = results["hasard_theorique_min_palier_pct"]

        rows = [
            ["Métrique", "config_actuelle", "config_test"],
            ["Total grilles", f"{ra['total_grilles_generated']:,}", f"{rb['total_grilles_generated']:,}"],
            ["Gagnantes (%) global", f"{ra['gagnantes_pct_global']:.4f}", f"{rb['gagnantes_pct_global']:.4f}"],
            ["Hasard théorique (%)", f"{hasard:.4f}", f"{hasard:.4f}"],
            ["Ratio observed/hasard", f"{ra['ratio_observed_vs_hasard']:.4f}",
             f"{rb['ratio_observed_vs_hasard']:.4f}"],
            ["—", "—", "—"],
        ]
        # 1 ligne par palier
        for palier_name, _, _ in self.paliers:
            rows.append([
                f"Palier {palier_name}",
                str(ra["gagnantes_per_palier"][palier_name]),
                str(rb["gagnantes_per_palier"][palier_name]),
            ])
        rows.append(["—", "—", "—"])
        # 1 ligne par bucket stratification
        for b in STRATIFICATION_BUCKETS:
            rows.append([
                f"Strat {b}",
                f"{ra['stratification_distribution_generated'][b] * 100:.2f}%",
                f"{rb['stratification_distribution_generated'][b] * 100:.2f}%",
            ])

        fig, ax = plt.subplots(figsize=(11, 0.36 * len(rows) + 1.2), dpi=120)
        ax.axis("off")
        table = ax.table(
            cellText=rows[1:],
            colLabels=rows[0],
            loc="upper left",
            cellLoc="center",
            colWidths=[0.45, 0.275, 0.275],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.15)

        title = (
            f"Backtest summary — {meta['game'].upper()} — {meta['n_tirages']} tirages "
            f"× {meta['n_grilles_per_tirage']} grilles  (mode={meta['mode']}, elapsed={meta['elapsed_seconds']}s)"
        )
        fig.suptitle(title, fontsize=11, y=0.98)
        footer = f"Harness {meta['harness_version']}  |  {meta['run_at']}"
        ax.text(0.5, -0.01, footer, ha="center", transform=ax.transAxes, fontsize=8, color="#666")

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        logger.info("PNG exported : %s", path)

    # ── V_X.F LOT 3 — Signature plots (config_actuelle uniquement) ───

    def plot_signature_distributions(self, results: dict, path: str) -> None:
        """Overlay des distributions par feature : HYBRIDE vs random pur vs vrais tirages.

        Layout 2×4 subplots (7 features, 1 cellule cachée). Pour chaque feature :
            - Histogramme HYBRIDE (bleu, alpha 0.6)
            - Histogramme random pur (orange, alpha 0.5)
            - Step plot vrais tirages (gris pointillés, narratif uniquement)
        Titre subplot : "feature — JSD = 0.XXXX". Légende sur 1er subplot seulement.

        Cible : config_actuelle uniquement (un seul PNG, simple+lisible).

        Framing ANJ : ce plot mesure une SIGNATURE STATISTIQUE — divergence
        de forme entre distributions, JAMAIS une supériorité prédictive.

        Args:
            results: dict retourné par compare() — lit results["results_config_actuelle"]["tier2"].
            path: chemin de sortie PNG.
        """
        tier2 = results["results_config_actuelle"].get("tier2")
        if tier2 is None or "histograms" not in tier2:
            logger.warning("plot_signature_distributions: tier2/histograms absent — skipped")
            return
        histograms = tier2["histograms"]
        feature_jsd = tier2["feature_jsd"]
        features = list(FEATURE_NAMES)  # 7 features

        fig, axes = plt.subplots(2, 4, figsize=(20, 10), dpi=120)
        axes_flat = axes.flatten()

        for i, fname in enumerate(features):
            ax = axes_flat[i]
            h = histograms[fname]
            bins = np.asarray(h["bins"], dtype=np.float64)
            widths = np.diff(bins)
            hyb = np.asarray(h["hybride"], dtype=np.float64)
            rnd = np.asarray(h["random"], dtype=np.float64)
            real = h.get("real_tirages")

            ax.bar(bins[:-1], hyb, width=widths, align="edge",
                   color="#1f77b4", alpha=0.6, edgecolor="none",
                   label="HYBRIDE")
            ax.bar(bins[:-1], rnd, width=widths, align="edge",
                   color="#ff7f0e", alpha=0.5, edgecolor="none",
                   label="Random pur")
            if real is not None:
                real_arr = np.asarray(real, dtype=np.float64)
                # Step plot centré sur les bin centers, pointillés gris narratifs
                centers = (bins[:-1] + bins[1:]) / 2.0
                ax.step(centers, real_arr, where="mid",
                        color="#444444", linestyle="--", linewidth=1.5,
                        label="Vrais tirages (narratif)")

            jsd = feature_jsd.get(fname, 0.0)
            ax.set_title(f"{fname} — JSD = {jsd:.4f}", fontsize=10)
            ax.set_ylabel("densité")
            ax.grid(True, axis="y", linestyle=":", alpha=0.4)
            # ESI : axe-x log lisible
            if fname == "esi":
                ax.set_xscale("symlog", linthresh=10.0)
            if i == 0:
                ax.legend(loc="upper right", fontsize=8, frameon=True)

        # Cellule 8 (idx 7) cachée — 7 features uniquement
        axes_flat[7].set_visible(False)

        meta = results["metadata"]
        max_jsd_nat = float(np.log(2))
        fig.suptitle(
            f"Signature statistique des grilles HYBRIDE — {meta['game'].upper()} — "
            f"{meta['n_tirages']}×{meta['n_grilles_per_tirage']} grilles\n"
            f"Divergence de forme per-feature (JSD base e, max théorique = log(2) ≈ {max_jsd_nat:.3f})",
            fontsize=12, y=0.995,
        )
        fig.text(
            0.5, 0.005,
            "Mesure de divergence de distribution — pas une promesse de gain. "
            f"Baseline = {tier2['baseline']['n']:,} grilles aléatoires uniformes (seed={tier2['baseline']['seed']}).",
            ha="center", fontsize=8, color="#666",
        )
        fig.tight_layout(rect=(0, 0.02, 1, 0.95))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        logger.info("PNG exported : %s", path)

    def plot_signature_summary(self, results: dict, path: str) -> None:
        """Tableau récap signature : 7 features × {HYBRIDE mean, Random mean, JSD, bornes Tier 1}.

        Section dédiée — ne surcharge pas plot_summary existant. Tableau B&W
        uniforme (pas de gradient JSD car une haute JSD = forte signature,
        neutre — pas une "mauvaise" valeur).

        Args:
            results: dict retourné par compare().
            path: chemin de sortie PNG.
        """
        ra = results["results_config_actuelle"]
        tier1 = ra.get("tier1", {})
        tier2 = ra.get("tier2")
        if tier2 is None:
            logger.warning("plot_signature_summary: tier2 absent — skipped")
            return
        feature_jsd = tier2["feature_jsd"]
        histograms = tier2.get("histograms", {})
        meta = results["metadata"]

        # Format des bornes Tier 1 (ou "—" si non applicable)
        def _format_bounds(fname: str) -> str:
            entry = tier1.get(fname, {})
            if "bounds" in entry:
                lo, hi = entry["bounds"]
                pct = entry.get("pct_out_of_bounds", 0.0)
                return f"[{lo}, {hi}] ({pct:.1f}% OOB)"
            if "min_threshold" in entry:
                pct = entry.get("pct_below_min", 0.0)
                return f"≥{entry['min_threshold']} ({pct:.1f}% below)"
            if "max_threshold" in entry:
                pct = entry.get("pct_above_max", 0.0)
                return f"≤{entry['max_threshold']} ({pct:.1f}% above)"
            return "—"

        # HYBRIDE mean et Random mean : recalcul depuis histograms (centers·density)
        def _hist_mean(hist_list, bins_list) -> float:
            if not hist_list or not bins_list:
                return 0.0
            bins_arr = np.asarray(bins_list, dtype=np.float64)
            centers = (bins_arr[:-1] + bins_arr[1:]) / 2.0
            density = np.asarray(hist_list, dtype=np.float64)
            return float((centers * density).sum())

        rows: list[list[str]] = [
            ["Feature", "HYBRIDE mean", "Random mean", "JSD", "Bornes Tier 1"],
        ]
        for fname in FEATURE_NAMES:
            h = histograms.get(fname, {})
            hyb_mean = _hist_mean(h.get("hybride", []), h.get("bins", []))
            rnd_mean = _hist_mean(h.get("random", []), h.get("bins", []))
            rows.append([
                fname,
                f"{hyb_mean:.3f}",
                f"{rnd_mean:.3f}",
                f"{feature_jsd.get(fname, 0.0):.4f}",
                _format_bounds(fname),
            ])

        fig, ax = plt.subplots(figsize=(12, 0.45 * len(rows) + 1.6), dpi=120)
        ax.axis("off")
        table = ax.table(
            cellText=rows[1:],
            colLabels=rows[0],
            loc="upper left",
            cellLoc="center",
            colWidths=[0.18, 0.18, 0.18, 0.13, 0.33],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.25)

        fig.suptitle(
            f"Signature statistique — résumé tabulaire — {meta['game'].upper()} — "
            f"{meta['n_tirages']}×{meta['n_grilles_per_tirage']} grilles",
            fontsize=11, y=0.98,
        )
        max_jsd_nat = float(np.log(2))
        footer = (
            f"JSD per-feature (base e, max = log(2) ≈ {max_jsd_nat:.3f}) "
            f"vs baseline {tier2['baseline']['n']:,} grilles random pur. "
            f"Tier 1 = invariants mou-bornés engine config."
        )
        ax.text(0.5, -0.02, footer, ha="center", transform=ax.transAxes,
                fontsize=8, color="#666")

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        logger.info("PNG exported : %s", path)


# ════════════════════════════════════════════════════════════════════════
# CLI entrypoint
# ════════════════════════════════════════════════════════════════════════

def _default_output_dir() -> str:
    """Cross-platform default : /tmp/backtest_results on Linux, %TEMP%/ on Windows."""
    return str(Path(tempfile.gettempdir()) / "backtest_results")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="backtest_hybride",
        description="HYBRIDE engine backtest harness — replay historique + compare 2 configs.",
    )
    p.add_argument("--game", choices=["loto", "em"], default="loto",
                   help="Loterie cible (default: loto).")
    p.add_argument("--n-tirages", type=int, default=200,
                   help="Nombre de tirages historiques à rejouer (default: 200).")
    p.add_argument("--n-grilles-per-tirage", type=int, default=100,
                   help="Nombre de grilles générées par tirage (default: 100).")
    p.add_argument("--mode", choices=["conservative", "balanced", "recent"], default="balanced",
                   help="Mode HYBRIDE engine (default: balanced).")
    p.add_argument("--date-max", type=str, default=None,
                   help="Cutoff YYYY-MM-DD (OOS) : N tirages se terminant <= cette date. Défaut: N plus récents.")
    p.add_argument("--config-test", type=str, default=None,
                   help="Path JSON params overrides pour config_test (default: identique à config_actuelle).")
    p.add_argument("--no-compare", action="store_true",
                   help="OOS mono-config : exécute run_config 1× (≈÷2 runtime). Ignore --config-test. "
                        "Sortie JSON/PNG identique (diff nul).")
    p.add_argument("--include-secondary", action="store_true",
                   help="LOT S1 : mesure la signature secondaire `*_in_T1` (overlap grille ∩ T-1 : "
                        "chance Loto / etoiles EM). Défaut off. Expose tier2['secondary']. "
                        "Offline pur, aucun impact engine/prod.")
    p.add_argument("--noise-floor", action="store_true",
                   help="Plancher de bruit Monte Carlo (modèle nul Option B) + correction "
                        "FDR Benjamini-Hochberg sur toutes les features. Défaut off. Expose "
                        "tier2['noise_floor'/'is_material'/'noise_floor_meta']. Offline pur.")
    p.add_argument("--output-dir", type=str, default=_default_output_dir(),
                   help="Dossier de sortie JSON + PNG.")
    return p.parse_args(argv)


async def _main_async(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg_actuel = BacktestConfig()
    if args.config_test:
        cfg_test = BacktestConfig.from_json_file(args.config_test)
    else:
        cfg_test = BacktestConfig()  # default = identical (sanity baseline)

    if args.date_max is not None:
        datetime.strptime(args.date_max, "%Y-%m-%d")  # fail-fast : ValueError clair si typo

    harness = BacktestHarness(
        game=args.game,
        n_tirages=args.n_tirages,
        n_grilles_per_tirage=args.n_grilles_per_tirage,
        mode=args.mode,
        date_max=args.date_max,
    )

    logger.info("Backtest start : game=%s n_tirages=%d n_grilles=%d mode=%s date_max=%s",
                args.game, args.n_tirages, args.n_grilles_per_tirage, args.mode, args.date_max)
    t0 = time.monotonic()
    # aiomysql pool : init for this standalone script (FastAPI server normally
    # owns the pool, but here we run from CLI so we init/close ourselves).
    await init_pool()
    try:
        if args.no_compare:
            results = await harness.run_oos(
                cfg_actuel,
                include_secondary=args.include_secondary,
                noise_floor=args.noise_floor,
            )
        else:
            results = await harness.compare(
                cfg_actuel, cfg_test,
                include_secondary=args.include_secondary,
                noise_floor=args.noise_floor,
            )
    finally:
        await close_pool()
    elapsed = time.monotonic() - t0
    logger.info("Backtest done in %.1fs", elapsed)

    json_path = output_dir / f"{args.game}_{args.n_tirages}.json"
    palier_png = output_dir / f"{args.game}_palier_distribution.png"
    strat_png = output_dir / f"{args.game}_stratification.png"
    summary_png = output_dir / f"{args.game}_summary.png"
    # V_X.F LOT 3 — restitution signature statistique (config_actuelle uniquement)
    signature_dist_png = output_dir / f"{args.game}_signature_distributions.png"
    signature_summary_png = output_dir / f"{args.game}_signature_summary.png"

    harness.export_json(results, str(json_path))
    harness.plot_palier_distribution(results, str(palier_png))
    harness.plot_stratification(results, str(strat_png))
    harness.plot_summary(results, str(summary_png))
    # V_X.F LOT 3 — 2 nouveaux plots additifs
    harness.plot_signature_distributions(results, str(signature_dist_png))
    harness.plot_signature_summary(results, str(signature_summary_png))

    logger.info("Outputs : %s + 5 PNG dans %s", json_path.name, output_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
