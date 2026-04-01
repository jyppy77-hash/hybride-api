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
# Kept only for symbols still imported by production code or tests.
# New code should import from engine.hybride_base or config.engine directly.

def valider_contraintes(numeros):
    """Used by: tests/test_hybride_em.py, tests/test_forced_numbers.py."""
    return _engine.valider_contraintes(numeros)


def generer_badges(numeros, scores_hybrides, lang="fr"):
    """Used by: tests/test_hybride_em.py, tests/test_hybride_base.py."""
    return _engine._generer_badges(numeros, scores_hybrides, lang)


# ── Main API (backward compat signature) ──────────────────────────────

async def generate_grids(
    n=5, mode="balanced", lang="fr",
    forced_nums=None, forced_etoiles=None, exclusions=None,
    anti_collision=False, decay_state=None,
):
    """Generate N EuroMillions grids. Used by: services/chat_pipeline_em.py, tests."""
    return await _engine.generate_grids(
        n=n, mode=mode, lang=lang, anti_collision=anti_collision,
        forced_nums=forced_nums, forced_secondary=forced_etoiles,
        exclusions=exclusions, decay_state=decay_state,
        _get_connection=get_connection,
    )
