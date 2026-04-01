"""Configuration moteur HYBRIDE — Loto et EuroMillions."""
from dataclasses import dataclass


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

    # Decay score — anti-lock rotation (F04 terrain 01/04/2026)
    decay_enabled: bool = True
    decay_rate: float = 0.05       # penalty per consecutive miss
    decay_floor: float = 0.50      # minimum multiplier (50% of raw score)

    # Noise factor — intra-session diversification (F01 audit 01/04/2026)
    noise_factor: float = 0.0      # default 0.0 = off; per-mode override in _NOISE_BY_MODE

    # Wildcard froid — guaranteed cold number slot (F01 terrain 01/04/2026)
    wildcard_enabled: bool = True
    wildcard_pool_size: int = 15   # bottom-N numbers form the cold pool

    # Scoring secondaire dédié (F08 audit — poids étoiles/chance)
    poids_frequence_secondary: float = 0.85  # frequency weighs more for small spaces
    poids_retard_secondary: float = 0.15     # lag weighs less (12 stars → every ~6 draws)

    # Z-score penalization alternative (F06 terrain — opt-in)
    penalization_method: str = "multiplicative"  # "multiplicative" (default) or "z_score"
    z_score_offsets: tuple = (0.0, 2.0, 1.0, 0.5)  # T-1 (exclusion), T-2, T-3, T-4


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
    somme_min=70,
    somme_max=150,
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
    # V79 F04 terrain: resserré [75,175]→[95,160] pour corriger biais somme haute (+28pts vs réel)
    somme_min=95,
    somme_max=160,
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
)
