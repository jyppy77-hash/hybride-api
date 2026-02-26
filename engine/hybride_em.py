"""
Engine d'analyse EuroMillions - Version HYBRIDE_OPTIMAL V1 EM
Modele hybride pondere base sur l'analyse statistique reelle
Adapte pour EuroMillions : 5 boules [1-50], 2 etoiles [1-12]
"""

import logging
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any

from .db import get_connection

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    'fenetre_principale_annees': 5.0,
    'fenetre_recente_annees': 2.0,
    'poids_principal': 0.6,
    'poids_recent': 0.4,
    'coef_frequence': 0.7,
    'coef_retard': 0.3,
}

TABLE = "tirages_euromillions"
BOULE_MIN, BOULE_MAX = 1, 50
ETOILE_MIN, ETOILE_MAX = 1, 12
NB_BOULES = 5
NB_ETOILES = 2


# ============================================================================
# EXTRACTION STATISTIQUES
# ============================================================================

async def calculer_frequences(conn, date_limite: datetime) -> Dict[int, float]:
    """
    Calcule la frequence normalisee de chaque boule depuis date_limite.
    """
    cursor = await conn.cursor()
    freq = {n: 0 for n in range(BOULE_MIN, BOULE_MAX + 1)}

    await cursor.execute(f"""
        SELECT boule_1, boule_2, boule_3, boule_4, boule_5
        FROM {TABLE}
        WHERE date_de_tirage >= %s
        ORDER BY date_de_tirage
    """, (date_limite.strftime("%Y-%m-%d"),))

    tirages = await cursor.fetchall()
    nb_tirages = len(tirages)

    if nb_tirages == 0:
        return {n: 1 / BOULE_MAX for n in range(BOULE_MIN, BOULE_MAX + 1)}

    for tirage in tirages:
        for key in ['boule_1', 'boule_2', 'boule_3', 'boule_4', 'boule_5']:
            num = tirage[key]
            freq[num] += 1

    for n in freq:
        freq[n] = freq[n] / nb_tirages

    return freq


async def calculer_retards(conn, date_limite: datetime) -> Dict[int, float]:
    """
    Calcule le retard normalise de chaque boule (tirages depuis derniere apparition).
    """
    cursor = await conn.cursor()
    retard = {n: 0 for n in range(BOULE_MIN, BOULE_MAX + 1)}
    derniere_apparition = {n: None for n in range(BOULE_MIN, BOULE_MAX + 1)}

    await cursor.execute(f"""
        SELECT boule_1, boule_2, boule_3, boule_4, boule_5, date_de_tirage
        FROM {TABLE}
        WHERE date_de_tirage >= %s
        ORDER BY date_de_tirage DESC
    """, (date_limite.strftime("%Y-%m-%d"),))

    tirages = await cursor.fetchall()

    if not tirages:
        return {n: 0 for n in range(BOULE_MIN, BOULE_MAX + 1)}

    for idx, tirage in enumerate(tirages):
        nums = [tirage['boule_1'], tirage['boule_2'], tirage['boule_3'],
                tirage['boule_4'], tirage['boule_5']]
        for num in nums:
            if derniere_apparition[num] is None:
                derniere_apparition[num] = idx

    for n in range(BOULE_MIN, BOULE_MAX + 1):
        if derniere_apparition[n] is not None:
            retard[n] = derniere_apparition[n]
        else:
            retard[n] = len(tirages)

    max_retard = max(retard.values()) if retard.values() else 1
    if max_retard > 0:
        for n in retard:
            retard[n] = retard[n] / max_retard

    return retard


# ============================================================================
# SCORING HYBRIDE
# ============================================================================

def _minmax_normalize(values: Dict[int, float]) -> Dict[int, float]:
    """Normalise un dictionnaire de valeurs sur [0, 1] via min-max."""
    v_min = min(values.values())
    v_max = max(values.values())
    if v_max == v_min:
        return {k: 0.0 for k in values}
    return {k: (v - v_min) / (v_max - v_min) for k, v in values.items()}


async def calculer_scores_fenetre(conn, date_limite: datetime) -> Dict[int, float]:
    """
    Calcule le score composite pour une fenetre temporelle.
    Score = 0.7 x frequence_norm + 0.3 x retard_norm
    """
    freq = await calculer_frequences(conn, date_limite)
    retard = await calculer_retards(conn, date_limite)

    freq = _minmax_normalize(freq)
    retard = _minmax_normalize(retard)

    scores = {}
    for n in range(BOULE_MIN, BOULE_MAX + 1):
        scores[n] = (
            CONFIG['coef_frequence'] * freq[n] +
            CONFIG['coef_retard'] * retard[n]
        )

    return scores


async def get_reference_date(conn) -> datetime:
    """Retourne la date du dernier tirage EM en base."""
    try:
        cursor = await conn.cursor()
        await cursor.execute(f"SELECT MAX(date_de_tirage) as max_date FROM {TABLE}")
        row = await cursor.fetchone()
        max_date = row['max_date'] if row else None
        if not max_date:
            return datetime.now()
        return datetime.strptime(str(max_date), "%Y-%m-%d")
    except Exception:
        return datetime.now()


async def calculer_scores_hybrides(conn, mode: str = "balanced") -> Dict[int, float]:
    """
    Combine les scores des 2 fenetres (5 ans + 2 ans) selon ponderation variable.

    Args:
        mode: "conservative" (70/30), "balanced" (60/40), "recent" (40/60)
    """
    now = await get_reference_date(conn)
    date_limite_5ans = now - timedelta(days=CONFIG['fenetre_principale_annees'] * 365.25)
    date_limite_2ans = now - timedelta(days=CONFIG['fenetre_recente_annees'] * 365.25)

    scores_5ans = await calculer_scores_fenetre(conn, date_limite_5ans)
    scores_2ans = await calculer_scores_fenetre(conn, date_limite_2ans)

    if mode == "conservative":
        poids_5ans, poids_2ans = 0.7, 0.3
    elif mode == "recent":
        poids_5ans, poids_2ans = 0.4, 0.6
    else:
        poids_5ans, poids_2ans = CONFIG['poids_principal'], CONFIG['poids_recent']

    scores_hybrides = {}
    for n in range(BOULE_MIN, BOULE_MAX + 1):
        scores_hybrides[n] = (
            poids_5ans * scores_5ans[n] +
            poids_2ans * scores_2ans[n]
        )

    return scores_hybrides


def normaliser_en_probabilites(scores: Dict[int, float]) -> Dict[int, float]:
    """Convertit les scores en probabilites de tirage (somme = 1)."""
    total = sum(scores.values())
    if total == 0:
        return {n: 1 / BOULE_MAX for n in range(BOULE_MIN, BOULE_MAX + 1)}
    return {n: scores[n] / total for n in scores}


# ============================================================================
# VALIDATION CONTRAINTES DOUCES
# ============================================================================

def valider_contraintes(numeros: List[int]) -> float:
    """
    Verifie les contraintes douces et retourne un score de conformite [0-1].
    Adapte pour EuroMillions : 5 boules dans [1-50].
    """
    score_conformite = 1.0

    # 1. Pairs / Impairs (1-4 de chaque)
    nb_pairs = sum(1 for n in numeros if n % 2 == 0)
    if nb_pairs < 1 or nb_pairs > 4:
        score_conformite *= 0.8

    # 2. Bas / Haut (bas = 1-25, haut = 26-50)
    nb_bas = sum(1 for n in numeros if n <= 25)
    if nb_bas < 1 or nb_bas > 4:
        score_conformite *= 0.85

    # 3. Somme (plage normale EM : 75-175)
    somme = sum(numeros)
    if somme < 75 or somme > 175:
        score_conformite *= 0.7

    # 4. Dispersion (min 15)
    dispersion = max(numeros) - min(numeros)
    if dispersion < 15:
        score_conformite *= 0.6

    # 5. Suites consecutives (max 2 paires)
    nums_sorted = sorted(numeros)
    suites = 0
    for i in range(len(nums_sorted) - 1):
        if nums_sorted[i + 1] - nums_sorted[i] == 1:
            suites += 1
    if suites > 2:
        score_conformite *= 0.75

    return score_conformite


# ============================================================================
# GENERATION DE BADGES
# ============================================================================

def generer_badges(numeros: List[int], scores_hybrides: Dict[int, float]) -> List[str]:
    """Genere des badges explicatifs pour la grille EM."""
    badges = []

    score_moyen = sum(scores_hybrides[n] for n in numeros) / NB_BOULES
    score_global_moyen = sum(scores_hybrides.values()) / len(scores_hybrides)

    if score_moyen > score_global_moyen * 1.1:
        badges.append("Numéros chauds")
    elif score_moyen < score_global_moyen * 0.9:
        badges.append("Mix de retards")
    else:
        badges.append("Équilibre")

    dispersion = max(numeros) - min(numeros)
    if dispersion > 35:
        badges.append("Large spectre")

    nb_pairs = sum(1 for n in numeros if n % 2 == 0)
    if nb_pairs == 2 or nb_pairs == 3:
        badges.append("Pair/Impair OK")

    badges.append("Hybride V1 EM")

    return badges


# ============================================================================
# GENERATION DES ETOILES
# ============================================================================

async def generer_etoiles(conn) -> List[int]:
    """
    Genere 2 etoiles selon frequence historique (5 ans).
    Tirage pondere SANS remplacement parmi [1-12].

    Returns:
        Liste triee de 2 etoiles [1-12]
    """
    cursor = await conn.cursor()
    now = await get_reference_date(conn)
    date_limite = now - timedelta(days=CONFIG['fenetre_principale_annees'] * 365.25)

    await cursor.execute(f"""
        SELECT num, COUNT(*) as freq FROM (
            SELECT etoile_1 as num FROM {TABLE} WHERE date_de_tirage >= %s
            UNION ALL SELECT etoile_2 FROM {TABLE} WHERE date_de_tirage >= %s
        ) t
        GROUP BY num
    """, (date_limite.strftime("%Y-%m-%d"), date_limite.strftime("%Y-%m-%d")))

    freq_etoiles = {i: 0 for i in range(ETOILE_MIN, ETOILE_MAX + 1)}
    for row in await cursor.fetchall():
        freq_etoiles[row['num']] = row['freq']

    total = sum(freq_etoiles.values())
    if total == 0:
        return sorted(random.sample(range(ETOILE_MIN, ETOILE_MAX + 1), NB_ETOILES))

    # Tirage pondere de 2 etoiles sans remplacement
    disponibles = list(range(ETOILE_MIN, ETOILE_MAX + 1))
    probas = [freq_etoiles[i] for i in disponibles]

    etoiles = []
    for _ in range(NB_ETOILES):
        e = random.choices(disponibles, weights=probas, k=1)[0]
        etoiles.append(e)
        idx = disponibles.index(e)
        disponibles.pop(idx)
        probas.pop(idx)

    return sorted(etoiles)


# ============================================================================
# GENERATION DE GRILLE
# ============================================================================

async def generer_grille(conn, scores_hybrides: Dict[int, float]) -> Dict[str, Any]:
    """
    Genere une grille EM unique avec validation des contraintes.
    5 boules [1-50] + 2 etoiles [1-12].
    """
    MAX_TENTATIVES = 10

    probas = normaliser_en_probabilites(scores_hybrides)

    meilleure_grille = None
    meilleur_score_conformite = 0

    for tentative in range(MAX_TENTATIVES):
        numeros_disponibles = list(range(BOULE_MIN, BOULE_MAX + 1))
        probas_list = [probas[n] for n in numeros_disponibles]

        numeros = []
        for _ in range(NB_BOULES):
            num = random.choices(numeros_disponibles, weights=probas_list, k=1)[0]
            numeros.append(num)
            idx = numeros_disponibles.index(num)
            numeros_disponibles.pop(idx)
            probas_list.pop(idx)

        numeros = sorted(numeros)
        score_conformite = valider_contraintes(numeros)

        if score_conformite > meilleur_score_conformite:
            meilleure_grille = numeros
            meilleur_score_conformite = score_conformite

        if score_conformite >= 0.5:
            break

    numeros = meilleure_grille
    score_conformite = meilleur_score_conformite

    # 2 etoiles parmi [1-12] sans remplacement
    etoiles = await generer_etoiles(conn)

    # Score moyen
    score_moyen = sum(scores_hybrides[n] for n in numeros) / NB_BOULES

    # Score final [50-100]
    score_final = int(score_moyen * score_conformite * 10000)
    score_final = min(100, max(50, score_final))

    badges = generer_badges(numeros, scores_hybrides)

    return {
        'nums': numeros,
        'etoiles': etoiles,
        'score': score_final,
        'badges': badges
    }


# ============================================================================
# API PRINCIPALE
# ============================================================================

async def generate_grids(n: int = 5, mode: str = "balanced") -> Dict[str, Any]:
    """
    Point d'entree principal : genere N grilles EM optimisees.

    Args:
        n: Nombre de grilles (max 20)
        mode: conservative, balanced, recent
    """
    async with get_connection() as conn:
        scores_hybrides = await calculer_scores_hybrides(conn, mode=mode)

        grilles = []
        for i in range(n):
            grille = await generer_grille(conn, scores_hybrides)
            grilles.append(grille)

        grilles = sorted(grilles, key=lambda g: g['score'], reverse=True)

        cursor = await conn.cursor()
        await cursor.execute(f"SELECT COUNT(*) as count FROM {TABLE}")
        result = await cursor.fetchone()
        nb_tirages = result['count'] if result else 0

        await cursor.execute(f"SELECT MIN(date_de_tirage) as min_date, MAX(date_de_tirage) as max_date FROM {TABLE}")
        result = await cursor.fetchone()
        date_min = result['min_date'] if result else None
        date_max = result['max_date'] if result else None

        if mode == "conservative":
            ponderation = "70/30"
        elif mode == "recent":
            ponderation = "40/60"
        else:
            ponderation = f"{int(CONFIG['poids_principal'] * 100)}/{int(CONFIG['poids_recent'] * 100)}"

        metadata = {
            'mode': 'HYBRIDE_OPTIMAL_V1_EM',
            'mode_generation': mode,
            'fenetre_principale_annees': CONFIG['fenetre_principale_annees'],
            'fenetre_recente_annees': CONFIG['fenetre_recente_annees'],
            'ponderation': ponderation,
            'nb_tirages_total': nb_tirages,
            'periode_base': f"{date_min} -> {date_max}",
            'avertissement': "L'EuroMillions reste un jeu de pur hasard. Aucune garantie de gain."
        }

        return {
            'grids': grilles,
            'metadata': metadata
        }
