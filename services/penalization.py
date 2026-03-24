"""
Filtre de penalisation post-tirage pour META ANALYSE 75 Grilles.
Ajuste le classement des frequences pour reduire le biais vers les numeros recemment sortis.
Les frequences brutes affichees ne sont jamais modifiees.

V2 — Hard-exclude T-1 + fenetre 4 tirages (F01+F02 audit 360°).
"""

from config.engine import PENALTY_COEFFICIENTS, _SUPERSTITIOUS

# Legacy constants — kept for backward-compat imports in tests
COEFF_LAST_DRAW = 0.7
COEFF_SECOND_LAST = 0.85

# V2 coefficients — imported from config/engine.py (single source of truth).
PENALIZATION_COEFFS = list(PENALTY_COEFFICIENTS)


def compute_penalized_ranking(
    raw_freq: dict[int, int],
    last_draw_numbers: set[int],
    second_last_draw_numbers: set[int],
    num_range: range,
    top_n: int,
    *,
    recent_draws: list[set[int]] | None = None,
) -> tuple[list[dict], dict]:
    """
    Applique une penalisation post-tirage sur les frequences pour le classement.

    Args:
        raw_freq: {numero: frequence_brute} issu de la BDD
        last_draw_numbers: set des numeros du dernier tirage (legacy)
        second_last_draw_numbers: set des numeros de l'avant-dernier tirage (legacy)
        num_range: plage de numeros valides (ex: range(1, 50) pour Loto boules)
        top_n: nombre de numeros a retourner (5 pour boules, 3 pour chance/etoiles)
        recent_draws: [T-1, T-2, T-3, T-4] sets — V2 mode. Quand fourni,
            last_draw_numbers et second_last_draw_numbers sont ignores.

    Returns:
        (top_list, penalization_info)
        - top_list: [{"number": N, "count": freq_brute}, ...] trie par freq penalisee
        - penalization_info: metadata pour transparence API
    """
    use_v2 = recent_draws is not None and len(recent_draws) > 0

    # Build number -> best (lowest index) draw position
    draw_position: dict[int, int] = {}
    if use_v2:
        for pos, draw_set in enumerate(recent_draws):
            for n in draw_set:
                if n not in draw_position:
                    draw_position[n] = pos

    penalized_map: dict[int, float] = {}
    penalized_numbers: dict[int, float] = {}
    excluded_set: set[int] = set()

    for n in num_range:
        raw = raw_freq.get(n, 0)

        if use_v2:
            pos = draw_position.get(n)
            if pos is not None and pos < len(PENALIZATION_COEFFS):
                coeff = PENALIZATION_COEFFS[pos]
            else:
                coeff = 1.0

            if coeff == 0.0:
                excluded_set.add(n)
                penalized_map[n] = -1.0  # sentinel — excluded
                penalized_numbers[n] = 0.0
            else:
                penalized_map[n] = raw * coeff
                if coeff < 1.0:
                    penalized_numbers[n] = coeff
        else:
            # Legacy V1 path
            coeff = 1.0
            if n in last_draw_numbers:
                coeff = COEFF_LAST_DRAW
            elif n in second_last_draw_numbers:
                coeff = COEFF_SECOND_LAST

            penalized_map[n] = raw * coeff
            if coeff < 1.0:
                penalized_numbers[n] = coeff

    # Build sorted list — excluded numbers sink to the bottom
    all_items = [{"number": n, "count": raw_freq.get(n, 0)} for n in num_range]
    all_items.sort(key=lambda x: (-penalized_map[x["number"]], x["number"]))

    if use_v2 and excluded_set:
        # Hard-exclude: pick top_n from non-excluded numbers
        top_list = []
        for item in all_items:
            if item["number"] not in excluded_set:
                top_list.append(item)
                if len(top_list) == top_n:
                    break
    else:
        top_list = all_items[:top_n]

    # Raw (unpenalized) ranking for transparency
    raw_sorted = sorted(all_items, key=lambda x: (-x["count"], x["number"]))
    top_before = [{"number": x["number"], "count": x["count"]} for x in raw_sorted[:top_n]]

    penalization_info: dict = {
        "penalized_numbers": penalized_numbers,
        "top_before_penalization": top_before,
    }
    if use_v2:
        penalization_info["excluded_numbers"] = sorted(excluded_set)

    return top_list, penalization_info


# ─────────────────────────────────────────────
# Indicateur anti-collision
# ─────────────────────────────────────────────

def get_collision_risk_numbers(game: str = "euromillions") -> dict:
    """
    Retourne les numeros a risque de collision (partages par beaucoup de joueurs).
    Base sur les biais comportementaux documentes :
    - Dates de naissance (1-31) : sur-selectionnes massivement
    - Numeros culturels / superstitieux : 7, 13, 3, 9, 11
    Privilegier les numeros > 31 maximise l'esperance de gain en cas de jackpot.
    """
    max_num = 50 if game == "euromillions" else 49
    calendar_bias = set(range(1, min(32, max_num + 1)))
    superstition = set(_SUPERSTITIOUS)
    high_ev_range = set(range(32, max_num + 1))

    return {
        "calendar_bias": sorted(calendar_bias),
        "superstition": sorted(superstition),
        "high_ev_range": sorted(high_ev_range),
        "max_num": max_num,
    }
