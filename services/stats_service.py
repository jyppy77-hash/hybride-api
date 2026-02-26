"""
Service metier — fonctions statistiques Loto.
Wrapper fin autour de BaseStatsService avec config Loto + hooks SQL specifiques.
"""

import db_cloudsql
from services.base_stats import GameConfig, BaseStatsService


# ────────────────────────────────────────────
# Configuration Loto
# ────────────────────────────────────────────

LOTO_CONFIG = GameConfig(
    table="tirages",
    type_principal="principal",
    type_secondary="chance",
    range_principal=(1, 49),
    range_secondary=(1, 10),
    secondary_columns=["numero_chance"],
    cache_prefix="",
    log_label="",
    mid_threshold=24,
    somme_range=(70, 150),
    somme_pitch_range=(100, 140),
    freq_divisor=49,
    secondary_key="chance",
    secondary_match_key="chance_match",
    secondary_label="Chance",
)


class LotoStats(BaseStatsService):
    """Loto-specific hooks : filtrage SQL par numero_chance."""

    def _get_connection(self):
        return db_cloudsql.get_connection()

    def _query_exact_matches(self, cursor, nums, secondary):
        if secondary is not None:
            cursor.execute("""
                SELECT date_de_tirage FROM tirages
                WHERE boule_1 IN (%s, %s, %s, %s, %s)
                  AND boule_2 IN (%s, %s, %s, %s, %s)
                  AND boule_3 IN (%s, %s, %s, %s, %s)
                  AND boule_4 IN (%s, %s, %s, %s, %s)
                  AND boule_5 IN (%s, %s, %s, %s, %s)
                  AND numero_chance = %s
                ORDER BY date_de_tirage DESC
            """, (*nums, *nums, *nums, *nums, *nums, secondary))
        else:
            cursor.execute("""
                SELECT date_de_tirage FROM tirages
                WHERE boule_1 IN (%s, %s, %s, %s, %s)
                  AND boule_2 IN (%s, %s, %s, %s, %s)
                  AND boule_3 IN (%s, %s, %s, %s, %s)
                  AND boule_4 IN (%s, %s, %s, %s, %s)
                  AND boule_5 IN (%s, %s, %s, %s, %s)
                ORDER BY date_de_tirage DESC
            """, (*nums, *nums, *nums, *nums, *nums))
        return cursor.fetchall()

    def _query_best_match(self, cursor, nums, secondary):
        if secondary is not None:
            cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                    numero_chance,
                    (
                        (boule_1 IN (%s, %s, %s, %s, %s)) +
                        (boule_2 IN (%s, %s, %s, %s, %s)) +
                        (boule_3 IN (%s, %s, %s, %s, %s)) +
                        (boule_4 IN (%s, %s, %s, %s, %s)) +
                        (boule_5 IN (%s, %s, %s, %s, %s))
                    ) AS match_count,
                    (numero_chance = %s) AS chance_match
                FROM tirages
                ORDER BY match_count DESC, chance_match DESC, date_de_tirage DESC
                LIMIT 1
            """, (*nums, *nums, *nums, *nums, *nums, secondary))
        else:
            cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                    (
                        (boule_1 IN (%s, %s, %s, %s, %s)) +
                        (boule_2 IN (%s, %s, %s, %s, %s)) +
                        (boule_3 IN (%s, %s, %s, %s, %s)) +
                        (boule_4 IN (%s, %s, %s, %s, %s)) +
                        (boule_5 IN (%s, %s, %s, %s, %s))
                    ) AS match_count
                FROM tirages
                ORDER BY match_count DESC, date_de_tirage DESC
                LIMIT 1
            """, (*nums, *nums, *nums, *nums, *nums))
        return cursor.fetchone()

    def _extract_secondary_match(self, best_match, secondary):
        return bool(best_match.get('chance_match', 0))


# ────────────────────────────────────────────
# Instance singleton + re-exports
# ────────────────────────────────────────────

_svc = LotoStats(LOTO_CONFIG)

_get_all_frequencies = _svc._get_all_frequencies
_get_all_ecarts = _svc._get_all_ecarts
get_numero_stats = _svc.get_numero_stats
get_classement_numeros = _svc.get_classement_numeros
get_comparaison_numeros = _svc.get_comparaison_numeros
get_numeros_par_categorie = _svc.get_numeros_par_categorie
prepare_grilles_pitch_context = _svc.prepare_grilles_pitch_context


def analyze_grille_for_chat(nums: list, chance: int = None) -> dict:
    """Wrapper preservant la signature originale (chance: int)."""
    return _svc.analyze_grille_for_chat(nums, chance)
