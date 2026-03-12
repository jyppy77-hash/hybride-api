"""
Analyse statistique pedagogique — Score Z, artefact de fenetrage, contexte biais.
Fonctions pures (pas de DB) utilisables par Loto France ET EuroMillions.
Zero dependance externe (math.erfc pour la p-value, pas de scipy).
"""

import math
from typing import Dict, List


# ─────────────────────────────────────────────
# Score Z (modele binomial)
# ─────────────────────────────────────────────

def compute_zscore(
    observed: int,
    n_draws: int,
    p: float,
) -> dict:
    """
    Calcule le score Z d'un numero par rapport au modele binomial.

    Args:
        observed: nombre d'apparitions du numero dans la fenetre
        n_draws: nombre total de tirages dans la fenetre
        p: probabilite theorique par tirage (ex: 5/50=0.10 pour boules EM)

    Returns:
        dict avec expected, z_score, p_value, deviation_pct, bonferroni_significant
    """
    expected = n_draws * p
    sigma = math.sqrt(n_draws * p * (1 - p))

    if sigma == 0:
        return {
            "observed": observed,
            "expected": round(expected, 2),
            "z_score": 0.0,
            "p_value": 1.0,
            "bonferroni_significant": False,
            "deviation_pct": 0.0,
        }

    z_score = (observed - expected) / sigma

    # Two-tailed p-value via math.erfc (exact, no scipy needed)
    p_value = math.erfc(abs(z_score) / math.sqrt(2))

    deviation_pct = ((observed - expected) / expected * 100) if expected > 0 else 0.0

    return {
        "observed": observed,
        "expected": round(expected, 2),
        "z_score": round(z_score, 4),
        "p_value": round(p_value, 6),
        "bonferroni_significant": False,  # caller sets this with correct N
        "deviation_pct": round(deviation_pct, 2),
    }


def compute_zscore_batch(
    freq_map: Dict[int, int],
    n_draws: int,
    n_balls_drawn: int,
    n_balls_total: int,
) -> List[dict]:
    """
    Calcule le score Z pour tous les numeros d'un jeu.

    Args:
        freq_map: {numero: frequence_observee}
        n_draws: nombre total de tirages
        n_balls_drawn: boules tirees par tirage (5 pour Loto/EM boules, 2 pour etoiles, 1 pour chance)
        n_balls_total: taille du pool (49 Loto, 50 EM boules, 12 etoiles, 10 chance)

    Returns:
        Liste de dicts triee par |z_score| decroissant
    """
    p = n_balls_drawn / n_balls_total
    alpha_corrected = 0.05 / n_balls_total  # Bonferroni

    results = []
    for num, observed in freq_map.items():
        entry = compute_zscore(observed, n_draws, p)
        entry["num"] = num
        entry["bonferroni_significant"] = entry["p_value"] < alpha_corrected
        results.append(entry)

    results.sort(key=lambda x: abs(x["z_score"]), reverse=True)
    return results


# ─────────────────────────────────────────────
# Detection d'artefact de fenetrage
# ─────────────────────────────────────────────

def detect_windowing_artifact(
    number: int,
    freq_by_window: Dict[str, Dict[int, int]],
) -> dict:
    """
    Detecte si un numero est dominant uniquement sur des fenetres courtes
    mais pas sur l'historique long (= artefact de data dredging).

    Args:
        number: le numero a analyser
        freq_by_window: {"3A": {1: 50, 2: 48, ...}, "5A": {...}, "GLOBAL": {...}}
            Chaque valeur est un dict {numero: frequence}.

    Returns:
        dict avec ranks_by_window, is_windowing_artifact
    """
    ranks: Dict[str, int] = {}
    for window_label, freq_map in freq_by_window.items():
        sorted_nums = sorted(freq_map.keys(), key=lambda n: (-freq_map[n], n))
        try:
            rank = sorted_nums.index(number) + 1
        except ValueError:
            rank = len(sorted_nums) + 1
        ranks[window_label] = rank

    best_rank = min(ranks.values())
    worst_rank = max(ranks.values())

    # Artifact = top 5 on at least one window but > top 15 on another
    is_artifact = best_rank <= 5 and worst_rank > 15

    return {
        "number": number,
        "ranks_by_window": ranks,
        "is_windowing_artifact": is_artifact,
    }


# ─────────────────────────────────────────────
# Contexte pedagogique pour le chatbot
# ─────────────────────────────────────────────

PEDAGOGICAL_CONTEXT = (
    "\n\n[CONTEXTE PÉDAGOGIQUE — BIAIS STATISTIQUES]\n"
    "IMPORTANT : Les écarts de fréquence observés sur des fenêtres de 3 à 7 ans "
    "sont statistiquement normaux. "
    "Sur 50 numéros analysés simultanément, il y a ~13% de chance qu'au moins un "
    "numéro dévie de +36% ou plus par rapport à l'espérance (correction de Bonferroni). "
    "Le \"retard\" d'un numéro ne prédit PAS sa sortie future — chaque tirage est "
    "stochastiquement indépendant (loi des grands nombres par DILUTION, pas par compensation). "
    "Les numéros 1 à 31 sont sur-sélectionnés par les joueurs (dates de naissance), "
    "ce qui réduit l'espérance de gain en cas de jackpot partagé. "
    "Rappelle ces éléments de manière pédagogique quand tu mentionnes des numéros "
    "\"chauds\" ou \"en retard\"."
)


def should_inject_pedagogical_context(message: str) -> bool:
    """
    Detecte si la question de l'utilisateur porte sur les frequences,
    numeros chauds/froids, retard, ou predictions — necessitant le contexte pedagogique.
    """
    msg_lower = message.lower()
    keywords = (
        "chaud", "froid", "hot", "cold", "fréquent", "frequent", "rare",
        "retard", "overdue", "en retard", "dû", "due",
        "prédire", "predict", "prédiction", "prediction",
        "plus sorti", "moins sorti", "most drawn", "least drawn",
        "tendance", "trend", "favori", "favorite",
        "gagnant", "winner", "gagner", "win",
        "prochain numéro", "prochain numero", "next number", "sortir", "come out",
        "top 5", "top 3", "classement", "ranking",
        "heiss", "kalt", "häufig", "selten",  # DE
        "caliente", "frío", "frecuente",  # ES
        "quente", "frio", "frequente",  # PT
        "heet", "koud", "frequent",  # NL
    )
    return any(kw in msg_lower for kw in keywords)
