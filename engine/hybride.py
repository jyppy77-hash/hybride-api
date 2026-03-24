"""
Engine d'analyse Loto - Version HYBRIDE_OPTIMAL V1
Thin wrapper over HybrideEngine (E06 audit fix).
"""

import logging
from datetime import datetime, timezone

from config.engine import LOTO_CONFIG
from .hybride_base import HybrideEngine
from .db import get_connection

logger = logging.getLogger(__name__)

# Singleton engine instance
_engine = HybrideEngine(LOTO_CONFIG)

# === BACKWARD COMPATIBILITY RE-EXPORTS ===
# These re-exports allow existing modules to import from engine.hybride
# instead of engine.hybride_base or config.engine. Migration plan:
# - New code should import from engine.hybride_base or config.engine directly.
# - Existing callers: tests/test_hybride.py, services/chat_pipeline.py.

_GENERATION_PENALTY_COEFFS = list(LOTO_CONFIG.penalty_coefficients)
TEMPERATURE_BY_MODE = dict(LOTO_CONFIG.temperature_by_mode)
ANTI_COLLISION_HIGH_BOOST = LOTO_CONFIG.anti_collision_high_boost
ANTI_COLLISION_SUPERSTITIOUS_MALUS = LOTO_CONFIG.anti_collision_superstitious_malus
SUPERSTITIOUS_NUMBERS = LOTO_CONFIG.superstitious_numbers
LOTO_HIGH_THRESHOLD = LOTO_CONFIG.anti_collision_threshold
MAX_TENTATIVES = LOTO_CONFIG.max_tentatives
MIN_CONFORMITE = LOTO_CONFIG.min_conformite

# Static function re-exports
_minmax_normalize = HybrideEngine._minmax_normalize
normaliser_en_probabilites = HybrideEngine.normaliser_en_probabilites
_apply_exclusions = HybrideEngine._apply_exclusions


def _apply_generation_penalties(scores, recent_draws):
    return _engine.apply_boule_penalties(scores, recent_draws)


def _apply_chance_penalties(freq_chance, recent_draws):
    return _engine.apply_secondary_penalties(freq_chance, recent_draws)


def _apply_anti_collision(scores, game="loto"):
    return _engine.apply_anti_collision(scores)


def _calculer_score_final(score_conformite):
    return HybrideEngine._calculer_score_final(score_conformite, LOTO_CONFIG.star_to_legacy_score)


def valider_contraintes(numeros):
    return _engine.valider_contraintes(numeros)


def generer_badges(numeros, scores_hybrides):
    return _engine._generer_badges(numeros, scores_hybrides)


# ── Main API (backward compat signatures) ─────────────────────────────

async def generate_grids(
    n=5, mode="balanced", lang="fr",
    forced_nums=None, forced_chance=None, exclusions=None,
    anti_collision=False,
):
    """Generate N Loto grids. Backward-compatible signature."""
    forced_secondary = [forced_chance] if forced_chance is not None else None
    return await _engine.generate_grids(
        n=n, mode=mode, lang=lang, anti_collision=anti_collision,
        forced_nums=forced_nums, forced_secondary=forced_secondary,
        exclusions=exclusions,
        _get_connection=get_connection,
    )


# ── DEPRECATED — kept for /ask backward compat (routes/api_analyse.py) ─

async def generate(prompt):
    """DEPRECATED: Legacy wrapper. Use generate_grids() directly."""
    try:
        result = await generate_grids(n=3, mode="balanced")
        return {
            "engine": "HYBRIDE_OPTIMAL_V1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input": prompt,
            "result": result
        }
    except Exception as e:
        return {
            "engine": "HYBRIDE_OPTIMAL_V1",
            "error": str(e)
        }
