"""
Service metier — fonctions statistiques EuroMillions.
Wrapper fin autour de BaseStatsService avec config EM + hooks SQL specifiques.
"""

import db_cloudsql
from services.base_stats import GameConfig, BaseStatsService


# ────────────────────────────────────────────
# Configuration EuroMillions
# ────────────────────────────────────────────

EM_CONFIG = GameConfig(
    table="tirages_euromillions",
    type_principal="boule",
    type_secondary="etoile",
    range_principal=(1, 50),
    range_secondary=(1, 12),
    secondary_columns=["etoile_1", "etoile_2"],
    cache_prefix="em:",
    log_label=" EM",
    mid_threshold=25,
    somme_range=(75, 175),
    somme_pitch_range=(75, 175),
    freq_divisor=50,
    secondary_key="etoiles",
    secondary_match_key="etoiles_match",
    secondary_label="\u00c9toiles",
)


class EMStats(BaseStatsService):
    """EuroMillions-specific hooks : etoiles multi-colonnes, pas de filtre SQL secondaire."""

    def _get_connection(self):
        return db_cloudsql.get_connection()

    # _query_exact_matches : default base (boules only, no etoile filter) — OK

    def _query_best_match(self, cursor, nums, secondary):
        cursor.execute("""
            SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                   etoile_1, etoile_2,
                (
                    (boule_1 IN (%s, %s, %s, %s, %s)) +
                    (boule_2 IN (%s, %s, %s, %s, %s)) +
                    (boule_3 IN (%s, %s, %s, %s, %s)) +
                    (boule_4 IN (%s, %s, %s, %s, %s)) +
                    (boule_5 IN (%s, %s, %s, %s, %s))
                ) AS match_count
            FROM tirages_euromillions
            ORDER BY match_count DESC, date_de_tirage DESC
            LIMIT 1
        """, (*nums, *nums, *nums, *nums, *nums))
        return cursor.fetchone()

    def _extract_secondary_match(self, best_match, secondary):
        etoiles = secondary
        if not etoiles:
            return False
        tirage_etoiles = {int(best_match['etoile_1']), int(best_match['etoile_2'])}
        return bool(set(etoiles) & tirage_etoiles)


# ────────────────────────────────────────────
# Instance singleton + re-exports
# ────────────────────────────────────────────

_svc = EMStats(EM_CONFIG)

_get_all_frequencies = _svc._get_all_frequencies
_get_all_ecarts = _svc._get_all_ecarts
get_numero_stats = _svc.get_numero_stats
get_classement_numeros = _svc.get_classement_numeros
get_comparaison_numeros = _svc.get_comparaison_numeros
get_numeros_par_categorie = _svc.get_numeros_par_categorie
prepare_grilles_pitch_context = _svc.prepare_grilles_pitch_context


def analyze_grille_for_chat(nums: list, etoiles: list = None) -> dict:
    """Wrapper preservant la signature originale (etoiles: list)."""
    return _svc.analyze_grille_for_chat(nums, sorted(etoiles or []))
