"""
Engine d'analyse EuroMillions - Version HYBRIDE_OPTIMAL V1 EM
Thin wrapper over HybrideEngine (E06 audit fix).

Badge EM ("Hybride V1 EM") is config-driven via EM_CONFIG.badge_key.
No subclass override needed — base class _generer_badges reads badge_key.
"""

from config.engine import EM_CONFIG
from .db import get_connection
from .hybride_base import HybrideEngine

# Singleton engine (config-driven badges via EM_CONFIG.badge_key="hybride_em")
_engine = HybrideEngine(EM_CONFIG)

# === BACKWARD COMPATIBILITY RE-EXPORTS ===
# These re-exports allow existing modules to import from engine.hybride_em
# instead of engine.hybride_base or config.engine. Migration plan:
# - New code should import from engine.hybride_base or config.engine directly.
# - Existing callers: tests/test_hybride_em.py, services/chat_pipeline_em.py.

TABLE = EM_CONFIG.table_name
BOULE_MIN, BOULE_MAX = EM_CONFIG.num_min, EM_CONFIG.num_max
ETOILE_MIN, ETOILE_MAX = EM_CONFIG.secondary_min, EM_CONFIG.secondary_max
NB_BOULES = EM_CONFIG.num_count
NB_ETOILES = EM_CONFIG.secondary_count

_GENERATION_PENALTY_COEFFS = list(EM_CONFIG.penalty_coefficients)
TEMPERATURE_BY_MODE = dict(EM_CONFIG.temperature_by_mode)
ANTI_COLLISION_HIGH_BOOST = EM_CONFIG.anti_collision_high_boost
ANTI_COLLISION_SUPERSTITIOUS_MALUS = EM_CONFIG.anti_collision_superstitious_malus
SUPERSTITIOUS_NUMBERS = EM_CONFIG.superstitious_numbers
EM_HIGH_THRESHOLD = EM_CONFIG.anti_collision_threshold
SUPERSTITIOUS_STARS = EM_CONFIG.superstitious_secondary
STAR_ANTI_COLLISION_MALUS = EM_CONFIG.secondary_anti_collision_malus
MAX_TENTATIVES = EM_CONFIG.max_tentatives
MIN_CONFORMITE = EM_CONFIG.min_conformite

# Static function re-exports
_minmax_normalize = HybrideEngine._minmax_normalize
normaliser_en_probabilites = HybrideEngine.normaliser_en_probabilites


def _apply_generation_penalties(scores, recent_draws):
    return _engine.apply_boule_penalties(scores, recent_draws)


def _apply_star_penalties(scores, recent_draws):
    return _engine.apply_secondary_penalties(scores, recent_draws)


def _apply_anti_collision(scores):
    return _engine.apply_anti_collision(scores)


def _apply_star_anti_collision(scores):
    return _engine.apply_secondary_anti_collision(scores)


def _calculer_score_final(score_conformite):
    return HybrideEngine._calculer_score_final(score_conformite, EM_CONFIG.star_to_legacy_score)


def valider_contraintes(numeros):
    return _engine.valider_contraintes(numeros)


def generer_badges(numeros, scores_hybrides, lang="fr"):
    return _engine._generer_badges(numeros, scores_hybrides, lang)


async def generer_etoiles(conn, mode="balanced", recent_draws=None, anti_collision=False):
    """DEPRECATED: Use generate_grids() which calls generer_secondary() internally."""
    return await _engine.generer_secondary(
        conn, mode=mode, recent_draws=recent_draws, anti_collision=anti_collision,
    )


# ── Main API (backward compat signature) ──────────────────────────────

async def generate_grids(
    n=5, mode="balanced", lang="fr",
    forced_nums=None, forced_etoiles=None, exclusions=None,
    anti_collision=False,
):
    """Generate N EuroMillions grids. Backward-compatible signature."""
    return await _engine.generate_grids(
        n=n, mode=mode, lang=lang, anti_collision=anti_collision,
        forced_nums=forced_nums, forced_secondary=forced_etoiles,
        exclusions=exclusions,
        _get_connection=get_connection,
    )
