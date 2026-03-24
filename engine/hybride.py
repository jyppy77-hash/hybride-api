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
# - Existing callers: tests/test_hybride.py, tests/test_models.py,
#   services/chat_pipeline.py, routes/api_analyse_unified.py (via config/games.py).

# Legacy CONFIG dict for backward compat (tests/test_models.py imports this)
CONFIG = {
    'fenetre_principale_annees': LOTO_CONFIG.fenetre_principale_annees,
    'fenetre_recente_annees': LOTO_CONFIG.fenetre_recente_annees,
    'poids_principal': 0.6,  # Legacy 2-window balanced weight
    'poids_recent': 0.4,     # Legacy 2-window balanced weight
    'coef_frequence': LOTO_CONFIG.poids_frequence,
    'coef_retard': LOTO_CONFIG.poids_retard,
}

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


# ── DEPRECATED Loto-only functions ────────────────────────────────────
# Kept for backward compatibility with admin/CLI tools.
# New code should use HybrideEngine.generate_grids() directly.

async def build_explanation(nums, chance_num):
    """DEPRECATED: Loto-only, non i18n. Explications pedagogiques pour une grille Loto."""
    from .stats import analyze_number

    explain = {
        "numbers": {},
        "chance": {},
        "summary": "Grille construite pour maximiser la coherence interne : "
                   "diversite des profils, equilibre pair/impair, repartition spatiale."
    }

    try:
        for num in nums:
            stats = await analyze_number(num)
            tags = []
            if stats["total_appearances"] >= 100:
                tags.append("fréquence élevée observée")
            elif stats["total_appearances"] >= 80:
                tags.append("fréquence moyenne observée")
            else:
                tags.append("fréquence modérée observée")
            if stats["current_gap"] == 0:
                tags.append("sorti au dernier tirage")
            elif stats["current_gap"] <= 5:
                tags.append("sorti récemment")
            explain["numbers"][num] = {
                "freq_observed": stats["total_appearances"],
                "last_date": stats["last_appearance"] or "Inconnu",
                "gap_draws": stats["current_gap"],
                "tags": tags
            }

        async with get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT COUNT(*) as count FROM tirages WHERE numero_chance = %s",
                (chance_num,)
            )
            result = await cursor.fetchone()
            chance_count = result['count'] if result else 0

            await cursor.execute(
                "SELECT date_de_tirage FROM tirages WHERE numero_chance = %s "
                "ORDER BY date_de_tirage DESC LIMIT 1",
                (chance_num,)
            )
            chance_last = await cursor.fetchone()
            chance_last_date = chance_last['date_de_tirage'] if chance_last else None

            if chance_last_date:
                await cursor.execute(
                    "SELECT COUNT(*) as count FROM tirages WHERE date_de_tirage > %s",
                    (chance_last_date,)
                )
                result = await cursor.fetchone()
                chance_gap = result['count'] if result else 0
            else:
                chance_gap = 0

        chance_tags = []
        if chance_count >= 90:
            chance_tags.append("fréquence observée élevée")
        elif chance_count >= 70:
            chance_tags.append("fréquence observée moyenne")
        else:
            chance_tags.append("fréquence observée modérée")
        if chance_gap == 0:
            chance_tags.append("sorti au dernier tirage")
        elif chance_gap <= 3:
            chance_tags.append("sorti récemment")

        explain["chance"] = {
            "freq_observed": chance_count,
            "last_date": chance_last_date or "Inconnu",
            "gap_draws": chance_gap,
            "tags": chance_tags
        }
    except Exception as e:
        logger.warning(f"[HYBRIDE] Erreur generation explications grille: {e}")

    return explain


async def run_analysis(target_date):
    """DEPRECATED: Loto-only legacy CLI wrapper. Use generate_grids() directly."""
    try:
        parsed_date = datetime.strptime(target_date, "%d/%m/%Y")
        formatted_date = parsed_date.strftime("%d/%m/%Y")
    except ValueError:
        formatted_date = target_date

    result_json = await generate_grids(n=3)
    grids = result_json['grids']
    metadata = result_json['metadata']

    result = []
    result.append(f"ANALYSE POUR LE TIRAGE DU {formatted_date}")
    result.append("")
    result.append("=" * 55)
    result.append("")
    result.append("MODÈLE : HYBRIDE OPTIMAL V1")
    result.append(f"  Fenêtre principale : {metadata['fenetre_principale_annees']} ans")
    result.append(f"  Fenêtre récente    : {metadata['fenetre_recente_annees']} ans")
    result.append(f"  Pondération        : {metadata['ponderation']}")
    result.append(f"  Tirages analysés   : {metadata['nb_tirages_total']}")
    result.append("")
    result.append("=" * 55)
    result.append("")
    result.append("GRILLES RECOMMANDÉES")
    result.append("")

    for idx, grid in enumerate(grids, 1):
        nums_str = " - ".join(f"{n:02d}" for n in grid['nums'])
        badges_str = ", ".join(grid['badges'])
        result.append(f"  Grille #{idx}")
        result.append(f"    Numéros : {nums_str}")
        result.append(f"    Chance  : {grid['chance']}")
        result.append(f"    Score   : {grid['score']}/100")
        result.append(f"    Badges  : {badges_str}")
        result.append("")

    result.append("=" * 55)
    result.append("")
    result.append("AVERTISSEMENT")
    result.append("")
    result.append("  Le Loto est un jeu de pur hasard.")
    result.append("  Ces grilles sont statistiquement guidées mais")
    result.append("  ne garantissent AUCUN gain.")
    result.append("")
    result.append("  Jouez responsable.")

    return "\n".join(result)


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
