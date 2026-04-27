"""Configuration moteur HYBRIDE — Loto et EuroMillions."""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EngineConfig:
    """Configuration d'un moteur HYBRIDE pour un jeu donne."""

    # Game identity
    game: str
    table_name: str
    mode_label: str  # "HYBRIDE_OPTIMAL_V1" | "HYBRIDE_OPTIMAL_V1_EM"

    # Boule range
    num_min: int
    num_max: int
    num_count: int  # 5

    # Secondary (chance or etoiles)
    secondary_name: str
    secondary_min: int
    secondary_max: int
    secondary_count: int
    secondary_columns: tuple

    # Time windows
    fenetre_principale_annees: float
    fenetre_recente_annees: float
    fenetre_globale: bool

    # Scoring weights
    poids_frequence: float
    poids_retard: float

    # Mode weights: (principale, recente, globale)
    modes: dict

    # Temperature per mode
    temperature_by_mode: dict

    # Constraint validation
    somme_min: int
    somme_max: int
    seuil_bas_haut: int
    dispersion_min: int
    max_consecutifs: int
    min_conformite: float
    max_tentatives: int

    # Anti-collision
    anti_collision_threshold: int
    anti_collision_high_boost: float
    anti_collision_superstitious_malus: float
    superstitious_numbers: frozenset
    superstitious_secondary: frozenset
    secondary_anti_collision_malus: float

    # Penalization
    penalty_window: int
    penalty_coefficients: tuple

    # Avertissement
    avertissement: str

    # Star rating
    star_to_legacy_score: dict

    # Badge key for i18n (used by _generer_badges)
    badge_key: str

    # Decay score — anti-lock rotation (V79 F04, V92 calibration)
    decay_enabled: bool = True
    decay_rate: float = 0.10       # penalty per consecutive miss (V92: 0.05→0.10)
    decay_floor: float = 0.50      # minimum multiplier (50% of raw score)
    decay_acceleration: float = 0.03  # progressive acceleration per miss (V92)
    decay_rate_secondary: float = 0.10  # secondary numbers (stars/chance) — override per game

    # Noise factor — intra-session diversification (V79 F01, V92 F04: migrated to config)
    noise_factor: float = 0.0      # default 0.0 = off; overridden by noise_by_mode
    noise_by_mode: dict = field(default_factory=lambda: {
        "conservative": 0.0,
        "balanced": 0.08,
        "recent": 0.12,
    })

    # Wildcard froid — guaranteed cold number slot (F01 terrain 01/04/2026)
    wildcard_enabled: bool = True
    wildcard_pool_size: int = 15   # bottom-N numbers form the cold pool

    # Scoring secondaire dédié (F08 audit — poids étoiles/chance)
    poids_frequence_secondary: float = 0.85  # frequency weighs more for small spaces
    poids_retard_secondary: float = 0.15     # lag weighs less (12 stars → every ~6 draws)

    # Z-score penalization alternative (F06 terrain — opt-in)
    penalization_method: str = "multiplicative"  # "multiplicative" (default) or "z_score"
    z_score_offsets: tuple = (0.0, 2.0, 1.0, 0.5)  # T-1 (exclusion), T-2, T-3, T-4

    # V104: Zone stratification — 1 number per zone for spatial diversity
    # Empty tuple = disabled (legacy global draw). Set per game below.
    zones: tuple = ()

    # V105: Saturation Brake — intra-batch rotation (Gemini Deep Research R4)
    # Numbers selected in grid i get score × saturation_brake in grid i+1.
    saturation_brake: float = 0.20        # ×0.20 for balls (80% reduction)
    saturation_brake_secondary: float = 0.30  # ×0.30 for stars/chance (70% reduction, smaller universe)

    # V110: Persistent Saturation Brake — inter-draw rotation (audit 01.1 rev.2 — F01.1-01)
    # Numbers from the canonical grid of draw T-1 get score × t1_multiplier on draw T.
    # Addresses the mathematical uniformity of decay documented in audit (intra-zone lock).
    # Shadow rollout: enabled=False by default → activation via env var after 48h pre-fill.
    saturation_brake_persistent_t1: float = 0.20      # multiplier for T-1 canonical selections
    saturation_brake_persistent_t2: float = 0.50      # multiplier for T-2 canonical selections
    saturation_persistent_enabled: bool = False       # master flag (read+write). ENV controlled at instantiation: CONFIG_SATURATION_PERSISTENT_ENABLED (see _env_bool below + LOTO_CONFIG/EM_CONFIG)
    saturation_persistent_window: int = 2             # 1 = T-1 only, 2 = T-1 + T-2

    # V106: Unpopularity scoring — penalize over-played numbers (Gemini Deep Research R3)
    # Applied to balls only (not stars/chance — universe too small).
    unpopularity_enabled: bool = True

    # V107: ESI (Even Spacing Index) filter — reject over-regular or clustered grids
    # Post-generation validation, not scoring. Applied in generer_grille() retry loop.
    esi_min: int = 20    # reject if ESI < min (too regular, over-played pattern)
    esi_max: int = 800   # reject if ESI > max (too clustered, atypical)


# V104: Zone boundaries for stratified selection (Gemini Deep Research R1)
LOTO_ZONES = ((1, 10), (11, 20), (21, 30), (31, 40), (41, 49))
EM_ZONES = ((1, 10), (11, 20), (21, 30), (31, 40), (41, 50))

# V106: Unpopularity coefficients (Gemini Deep Research R3 P2)
# Source: "Number preferences in lotteries" (Cambridge),
#         "The Demand for Lotto: Conscious Selection" (ResearchGate)
UNPOP_BIRTHDAY_MONTHS = 0.85    # 1-12: over-selected as birth months
UNPOP_BIRTHDAY_DAYS = 0.92      # 13-31: over-selected as birth days
UNPOP_LUCKY_SEVEN = 0.80        # 7: universal lucky number
UNPOP_MULTIPLES_OF_5 = 0.93     # 5,10,15,...: round-number preference

_STAR_SCORES = {5: 95, 4: 85, 3: 75, 2: 60, 1: 50}

_MODES_3W = {
    "conservative": (0.50, 0.30, 0.20),
    "balanced": (0.40, 0.35, 0.25),
    "recent": (0.25, 0.35, 0.40),
}

_TEMPERATURES = {"conservative": 1.0, "balanced": 1.3, "recent": 1.5}

# Single source of truth for penalty coefficients.
# T-1 = hard exclude (0.0), T-2 = x0.65, T-3 = x0.80, T-4 = x0.90.
# Imported by services/penalization.py and used in EngineConfig.
PENALTY_COEFFICIENTS = (0.0, 0.65, 0.80, 0.90)
PENALTY_WINDOW = 4

_SUPERSTITIOUS = frozenset({3, 7, 9, 11, 13})


def _env_bool(name: str, default: bool) -> bool:
    """Read boolean env var with strict truthy parsing.

    Truthy values (case-insensitive, after .strip()): "true", "1", "yes", "on" → True.
    Var absent (os.environ.get returns None) → default.
    Any other value (empty, "false", "0", "no", "off", typo, whitespace) → False.
    Fail-closed semantics: only explicit truthy strings activate; unknown/falsy
    values return False even if default=True. Used to gate V110
    (saturation_persistent_enabled) at module-load time so a Cloud Run env var
    update can toggle the feature without rebuild.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


LOTO_CONFIG = EngineConfig(
    game="loto",
    table_name="tirages",
    mode_label="HYBRIDE_OPTIMAL_V1",
    num_min=1,
    num_max=49,
    num_count=5,
    secondary_name="chance",
    secondary_min=1,
    secondary_max=10,
    secondary_count=1,
    secondary_columns=("numero_chance",),
    fenetre_principale_annees=5.0,
    fenetre_recente_annees=2.0,
    fenetre_globale=True,
    poids_frequence=0.7,
    poids_retard=0.3,
    modes=_MODES_3W,
    temperature_by_mode=_TEMPERATURES,
    # V103: calibré [μ-σ, μ+σ] — E(S)=125.0, σ=32.4 pour 5/49
    somme_min=93,
    somme_max=157,
    seuil_bas_haut=24,
    dispersion_min=15,
    max_consecutifs=2,
    min_conformite=0.7,
    max_tentatives=20,
    anti_collision_threshold=24,
    anti_collision_high_boost=1.15,
    anti_collision_superstitious_malus=0.80,
    superstitious_numbers=_SUPERSTITIOUS,
    superstitious_secondary=frozenset(),
    secondary_anti_collision_malus=1.0,
    penalty_window=4,
    penalty_coefficients=PENALTY_COEFFICIENTS,
    avertissement="Le Loto reste un jeu de pur hasard. Aucune garantie de gain.",
    star_to_legacy_score=_STAR_SCORES,
    badge_key="hybride_loto",
    # V92 calibration — decay accéléré + secondary dédié
    decay_rate=0.10,
    decay_rate_secondary=0.12,  # chance — univers de 10
    decay_acceleration=0.03,
    # V104: zone stratification
    zones=LOTO_ZONES,
    # V107: ESI — Loto 5/49
    esi_max=750,
    # V110: env-aware activation (CONFIG_SATURATION_PERSISTENT_ENABLED, default False)
    saturation_persistent_enabled=_env_bool("CONFIG_SATURATION_PERSISTENT_ENABLED", False),
)

EM_CONFIG = EngineConfig(
    game="em",
    table_name="tirages_euromillions",
    mode_label="HYBRIDE_OPTIMAL_V1_EM",
    num_min=1,
    num_max=50,
    num_count=5,
    secondary_name="etoiles",
    secondary_min=1,
    secondary_max=12,
    secondary_count=2,
    secondary_columns=("etoile_1", "etoile_2"),
    fenetre_principale_annees=5.0,
    fenetre_recente_annees=2.0,
    fenetre_globale=True,
    poids_frequence=0.7,
    poids_retard=0.3,
    modes=_MODES_3W,
    temperature_by_mode=_TEMPERATURES,
    # V103: calibré [μ-σ, μ+σ] — E(S)=127.5, σ=33.8 pour 5/50
    somme_min=94,
    somme_max=161,
    seuil_bas_haut=25,
    dispersion_min=15,
    max_consecutifs=2,
    min_conformite=0.7,
    max_tentatives=20,
    anti_collision_threshold=31,
    anti_collision_high_boost=1.15,
    anti_collision_superstitious_malus=0.80,
    superstitious_numbers=_SUPERSTITIOUS,
    superstitious_secondary=frozenset({3, 7, 9, 11}),
    secondary_anti_collision_malus=0.85,
    penalty_window=4,
    penalty_coefficients=PENALTY_COEFFICIENTS,
    avertissement="L'EuroMillions reste un jeu de pur hasard. Aucune garantie de gain.",
    star_to_legacy_score=_STAR_SCORES,
    badge_key="hybride_em",
    # V92 calibration — decay accéléré + secondary agressif (univers 12 étoiles)
    decay_rate=0.10,
    decay_rate_secondary=0.15,  # étoiles — univers de 12, rotation rapide
    decay_acceleration=0.03,
    # V92 F04: noise migré dans config, EM légèrement plus élevé (diversité univers 50)
    noise_by_mode={"conservative": 0.0, "balanced": 0.10, "recent": 0.15},
    # V104: zone stratification
    zones=EM_ZONES,
    # V110: env-aware activation (CONFIG_SATURATION_PERSISTENT_ENABLED, default False)
    saturation_persistent_enabled=_env_bool("CONFIG_SATURATION_PERSISTENT_ENABLED", False),
)
