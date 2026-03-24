"""
Engine d'analyse EuroMillions - Version HYBRIDE_OPTIMAL V1 EM
Thin wrapper over HybrideEngine (E06 audit fix).
"""

from config.engine import EM_CONFIG
from config.i18n import _badges as _i18n_badges
from .db import get_connection
from .hybride_base import HybrideEngine

# ── EM engine with custom badges ─────────────────────────────────────


class _EMEngine(HybrideEngine):
    """EuroMillions engine with i18n badge support."""

    def _generer_badges(self, numeros, scores_hybrides, lang="fr"):
        b = _i18n_badges(lang)
        badges = []

        score_moyen = sum(scores_hybrides[n] for n in numeros) / self.cfg.num_count
        score_global = sum(scores_hybrides.values()) / len(scores_hybrides)

        if score_moyen > score_global * 1.1:
            badges.append(b["hot"])
        elif score_moyen < score_global * 0.9:
            badges.append(b["overdue"])
        else:
            badges.append(b["balanced"])

        dispersion = max(numeros) - min(numeros)
        if dispersion > 35:
            badges.append(b["wide_spectrum"])

        nb_pairs = sum(1 for n in numeros if n % 2 == 0)
        if nb_pairs == 2 or nb_pairs == 3:
            badges.append(b["even_odd"])

        badges.append(b["hybride_em"])
        return badges


# Singleton engine
_engine = _EMEngine(EM_CONFIG)

# ── Backward-compat re-exports ────────────────────────────────────────

CONFIG = {
    'fenetre_principale_annees': EM_CONFIG.fenetre_principale_annees,
    'fenetre_recente_annees': EM_CONFIG.fenetre_recente_annees,
    'poids_principal': EM_CONFIG.modes['balanced'][0],
    'poids_recent': EM_CONFIG.modes['balanced'][1],
    'coef_frequence': EM_CONFIG.poids_frequence,
    'coef_retard': EM_CONFIG.poids_retard,
}

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
    """Generate 2 stars via hybrid scoring. Backward compat."""
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
