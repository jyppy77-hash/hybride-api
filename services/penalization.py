"""
Filtre de penalisation post-tirage pour META ANALYSE 75 Grilles.
Ajuste le classement des frequences pour reduire le biais vers les numeros recemment sortis.
Les frequences brutes affichees ne sont jamais modifiees.
"""

from typing import Dict, List, Set, Tuple

COEFF_LAST_DRAW = 0.7
COEFF_SECOND_LAST = 0.85


def compute_penalized_ranking(
    raw_freq: Dict[int, int],
    last_draw_numbers: Set[int],
    second_last_draw_numbers: Set[int],
    num_range: range,
    top_n: int,
) -> Tuple[List[dict], dict]:
    """
    Applique une penalisation post-tirage sur les frequences pour le classement.

    Args:
        raw_freq: {numero: frequence_brute} issu de la BDD
        last_draw_numbers: set des numeros du dernier tirage
        second_last_draw_numbers: set des numeros de l'avant-dernier tirage
        num_range: plage de numeros valides (ex: range(1, 50) pour Loto boules)
        top_n: nombre de numeros a retourner (5 pour boules, 3 pour chance/etoiles)

    Returns:
        (top_list, penalization_info)
        - top_list: [{"number": N, "count": freq_brute}, ...] trie par freq penalisee
        - penalization_info: metadata pour transparence API
    """
    penalized_map = {}
    penalized_numbers = {}

    for n in num_range:
        raw = raw_freq.get(n, 0)
        coeff = 1.0

        if n in last_draw_numbers:
            coeff = COEFF_LAST_DRAW
        elif n in second_last_draw_numbers:
            coeff = COEFF_SECOND_LAST

        penalized_map[n] = raw * coeff

        if coeff < 1.0:
            penalized_numbers[n] = coeff

    all_items = [{"number": n, "count": raw_freq.get(n, 0)} for n in num_range]
    all_items.sort(key=lambda x: (-penalized_map[x["number"]], x["number"]))

    top_list = all_items[:top_n]

    raw_sorted = sorted(all_items, key=lambda x: (-x["count"], x["number"]))
    top_before = [{"number": x["number"], "count": x["count"]} for x in raw_sorted[:top_n]]

    penalization_info = {
        "penalized_numbers": penalized_numbers,
        "top_before_penalization": top_before,
    }

    return top_list, penalization_info
