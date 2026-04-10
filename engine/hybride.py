"""
Engine d'analyse Loto - Version HYBRIDE_OPTIMAL V1
Thin wrapper over HybrideEngine (E06 audit fix).
"""

from config.engine import LOTO_CONFIG
from .hybride_base import HybrideEngine
from .db import get_connection

# Singleton engine instance
_engine = HybrideEngine(LOTO_CONFIG)


# === BACKWARD COMPATIBILITY RE-EXPORTS ===
# Kept only for symbols still imported by production code or tests.
# New code should import from engine.hybride_base or config.engine directly.

def valider_contraintes(numeros):
    """Used by: tests/test_hybride.py, tests/test_forced_numbers.py."""
    return _engine.valider_contraintes(numeros)


def generer_badges(numeros, scores_hybrides):
    """Used by: tests/test_hybride.py, tests/test_forced_numbers.py."""
    return _engine._generer_badges(numeros, scores_hybrides)


# ── Main API (backward compat signatures) ─────────────────────────────

async def generate_grids(
    n=5, mode="balanced", lang="fr",
    forced_nums=None, forced_chance=None, exclusions=None,
    anti_collision=False, decay_state=None,
):
    """Generate N Loto grids. Used by: services/chat_pipeline.py, tests."""
    forced_secondary = [forced_chance] if forced_chance is not None else None
    return await _engine.generate_grids(
        n=n, mode=mode, lang=lang, anti_collision=anti_collision,
        forced_nums=forced_nums, forced_secondary=forced_secondary,
        exclusions=exclusions, decay_state=decay_state,
        _get_connection=get_connection,
    )
