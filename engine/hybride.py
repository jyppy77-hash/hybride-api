"""
Engine d'analyse Loto - Version HYBRIDE_OPTIMAL V1
Modèle hybride pondéré basé sur l'analyse statistique réelle
"""

import logging
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Import pour les explications
from .db import get_connection

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Paramètres du modèle hybride V1
CONFIG = {
    'fenetre_principale_annees': 5.0,
    'fenetre_recente_annees': 2.0,
    'poids_principal': 0.6,
    'poids_recent': 0.4,
    'coef_frequence': 0.7,
    'coef_retard': 0.3,
}


# ============================================================================
# EXTRACTION STATISTIQUES
# ============================================================================

async def calculer_frequences(conn, date_limite: datetime) -> Dict[int, float]:
    """
    Calcule la fréquence normalisée de chaque numéro depuis date_limite

    Args:
        conn: Connexion MariaDB
        date_limite: Date à partir de laquelle analyser

    Returns:
        Dict {numéro: fréquence_normalisée}
    """
    cursor = await conn.cursor()

    # Initialiser compteurs
    freq = {n: 0 for n in range(1, 50)}

    # Récupérer tous les tirages depuis date_limite
    await cursor.execute("""
        SELECT boule_1, boule_2, boule_3, boule_4, boule_5
        FROM tirages
        WHERE date_de_tirage >= %s
        ORDER BY date_de_tirage
    """, (date_limite.strftime("%Y-%m-%d"),))

    tirages = await cursor.fetchall()
    nb_tirages = len(tirages)

    if nb_tirages == 0:
        # Fallback : distribution uniforme
        return {n: 1/49 for n in range(1, 50)}

    # Compter les apparitions
    for tirage in tirages:
        for key in ['boule_1', 'boule_2', 'boule_3', 'boule_4', 'boule_5']:
            num = tirage[key]
            freq[num] += 1

    # Normaliser par nombre de tirages
    for n in freq:
        freq[n] = freq[n] / nb_tirages

    return freq


async def calculer_retards(conn, date_limite: datetime) -> Dict[int, float]:
    """
    Calcule le retard normalisé de chaque numéro (tirages depuis dernière apparition)

    Args:
        conn: Connexion MariaDB
        date_limite: Date à partir de laquelle analyser

    Returns:
        Dict {numéro: retard_normalisé} (0 = récent, 1 = très en retard)
    """
    cursor = await conn.cursor()

    # Initialiser retards
    retard = {n: 0 for n in range(1, 50)}
    derniere_apparition = {n: None for n in range(1, 50)}

    # Récupérer tirages du plus récent au plus ancien
    await cursor.execute("""
        SELECT boule_1, boule_2, boule_3, boule_4, boule_5, date_de_tirage
        FROM tirages
        WHERE date_de_tirage >= %s
        ORDER BY date_de_tirage DESC
    """, (date_limite.strftime("%Y-%m-%d"),))

    tirages = await cursor.fetchall()

    if not tirages:
        return {n: 0 for n in range(1, 50)}

    # Pour chaque tirage (du plus récent au plus ancien)
    for idx, tirage in enumerate(tirages):
        nums = [tirage['boule_1'], tirage['boule_2'], tirage['boule_3'], tirage['boule_4'], tirage['boule_5']]

        for num in nums:
            if derniere_apparition[num] is None:
                derniere_apparition[num] = idx

    # Convertir en retard (nombre de tirages depuis dernière apparition)
    for n in range(1, 50):
        if derniere_apparition[n] is not None:
            retard[n] = derniere_apparition[n]
        else:
            # Jamais apparu dans la fenêtre
            retard[n] = len(tirages)

    # Normaliser [0, 1]
    max_retard = max(retard.values()) if retard.values() else 1
    if max_retard > 0:
        for n in retard:
            retard[n] = retard[n] / max_retard

    return retard


# ============================================================================
# SCORING HYBRIDE
# ============================================================================

def _minmax_normalize(values: Dict[int, float]) -> Dict[int, float]:
    """
    Normalise un dictionnaire de valeurs sur [0, 1] via min-max.
    Si toutes les valeurs sont identiques (max == min), retourne 0.0 pour tous
    (aucune différenciation possible sur cette métrique).
    """
    v_min = min(values.values())
    v_max = max(values.values())
    if v_max == v_min:
        return {k: 0.0 for k in values}
    return {k: (v - v_min) / (v_max - v_min) for k, v in values.items()}


async def calculer_scores_fenetre(conn, date_limite: datetime) -> Dict[int, float]:
    """
    Calcule le score composite pour une fenêtre temporelle
    Score = 0.7 × fréquence_norm + 0.3 × retard_norm

    Les deux métriques sont ramenées sur [0, 1] (min-max) avant pondération.
    Sans cette normalisation, la fréquence brute (~0.08-0.13) et le retard (0-1)
    sont sur des échelles différentes, ce qui fait que le retard domine la variance
    du score malgré un poids configuré inférieur (0.3 vs 0.7).

    Args:
        conn: Connexion MariaDB
        date_limite: Date limite de la fenêtre

    Returns:
        Dict {numéro: score}
    """
    freq = await calculer_frequences(conn, date_limite)
    retard = await calculer_retards(conn, date_limite)

    # Normalisation min-max [0,1] pour que les poids 0.7/0.3 reflètent
    # réellement l'importance relative voulue (fréquence > retard)
    freq = _minmax_normalize(freq)
    retard = _minmax_normalize(retard)

    scores = {}
    for n in range(1, 50):
        scores[n] = (
            CONFIG['coef_frequence'] * freq[n] +
            CONFIG['coef_retard'] * retard[n]
        )

    return scores


async def get_reference_date(conn) -> datetime:
    """
    Retourne la date de référence pour les calculs statistiques.
    On utilise la dernière date_de_tirage présente en base (tirage le plus récent).
    Fallback : datetime.now() si la table est vide ou en cas d'anomalie.
    """
    try:
        cursor = await conn.cursor()
        await cursor.execute("SELECT MAX(date_de_tirage) as max_date FROM tirages")
        row = await cursor.fetchone()
        max_date = row['max_date'] if row else None
        if not max_date:
            return datetime.now()

        # MariaDB retourne souvent un type date (YYYY-MM-DD) pour une colonne DATE
        # On convertit proprement en datetime.
        return datetime.strptime(str(max_date), "%Y-%m-%d")
    except Exception:
        return datetime.now()


async def calculer_scores_hybrides(conn, mode: str = "balanced") -> Dict[int, float]:
    """
    Combine les scores des 2 fenêtres (5 ans + 2 ans) selon pondération variable

    Args:
        conn: Connexion MariaDB
        mode: Mode de génération
            - "conservative" : favorise l'historique long terme (70% / 30%)
            - "balanced" : équilibre long/court terme (60% / 40%) [défaut]
            - "recent" : favorise les tendances récentes (40% / 60%)

    Returns:
        Dict {numéro: score_hybride}
    """
    # Date de référence (dernier tirage connu en base)
    now = await get_reference_date(conn)

    # Dates limites
    date_limite_5ans = now - timedelta(days=CONFIG['fenetre_principale_annees'] * 365.25)
    date_limite_2ans = now - timedelta(days=CONFIG['fenetre_recente_annees'] * 365.25)

    # Scores par fenêtre
    scores_5ans = await calculer_scores_fenetre(conn, date_limite_5ans)
    scores_2ans = await calculer_scores_fenetre(conn, date_limite_2ans)

    # Adapter les poids selon le mode
    if mode == "conservative":
        poids_5ans, poids_2ans = 0.7, 0.3
    elif mode == "recent":
        poids_5ans, poids_2ans = 0.4, 0.6
    else:  # balanced (défaut)
        poids_5ans, poids_2ans = CONFIG['poids_principal'], CONFIG['poids_recent']

    # Combinaison pondérée
    scores_hybrides = {}
    for n in range(1, 50):
        scores_hybrides[n] = (
            poids_5ans * scores_5ans[n] +
            poids_2ans * scores_2ans[n]
        )

    return scores_hybrides


def normaliser_en_probabilites(scores: Dict[int, float]) -> Dict[int, float]:
    """
    Convertit les scores en probabilités de tirage (somme = 1)

    Args:
        scores: Dict {numéro: score}

    Returns:
        Dict {numéro: probabilité}
    """
    total = sum(scores.values())

    if total == 0:
        # Fallback : distribution uniforme
        return {n: 1/49 for n in range(1, 50)}

    probas = {n: scores[n] / total for n in scores}
    return probas


# ============================================================================
# VALIDATION CONTRAINTES DOUCES
# ============================================================================

def valider_contraintes(numeros: List[int]) -> float:
    """
    Vérifie les contraintes douces et retourne un score de conformité [0-1]

    Ces contraintes sont basées sur l'analyse empirique des tirages FDJ (2019-2026).
    Elles visent à éviter les grilles "atypiques" (ex: 1-2-3-4-5, ou 45-46-47-48-49).

    ⚠️ IMPORTANT : Ces contraintes N'AMÉLIORENT PAS les chances de gagner.
    Toutes les combinaisons ont exactement P = 1 / C(49,5) ≈ 1 / 1 906 884.

    Elles servent uniquement à créer une expérience utilisateur cohérente.

    Contraintes appliquées :
    - Pairs/Impairs : 1-4 de chaque (pénalité: 0.8)
      Justification : 85% des tirages FDJ historiques respectent cette règle.
      Combinaisons comme 5 pairs ou 5 impairs sont rares mais aussi probables.

    - Bas/Haut : 1-4 numéros dans [1-24] (pénalité: 0.85)
      Justification : Évite les grilles trop concentrées sur une moitié.
      Distribution équilibrée améliore la "cohérence visuelle".

    - Somme : entre 70 et 150 (pénalité: 0.7)
      Justification : 80% des tirages FDJ ont une somme dans cet intervalle.
      Sommes extrêmes (< 70 ou > 150) correspondent à grilles très regroupées.

    - Dispersion : >= 15 (pénalité: 0.6)
      Justification : Évite les grilles trop concentrées (ex: 20-21-22-23-24).
      Une dispersion minimale garantit une couverture raisonnable.

    - Suites consécutives : max 2 (pénalité: 0.75)
      Justification : Évite les suites longues (ex: 10-11-12-13-14).
      Suites courtes (1-2) sont acceptables et fréquentes.

    Args:
        numeros: Liste de 5 numéros [1-49]

    Returns:
        Score de conformité [0-1] (1 = parfait, <0.5 = non conforme)
    """
    score_conformite = 1.0

    # 1. Pairs / Impairs
    # Analyse empirique : 85% des tirages FDJ 2019-2026 ont 1-4 pairs
    nb_pairs = sum(1 for n in numeros if n % 2 == 0)
    if nb_pairs < 1 or nb_pairs > 4:
        score_conformite *= 0.8

    # 2. Bas / Haut
    # Évite les grilles trop concentrées sur [1-24] ou [25-49]
    nb_bas = sum(1 for n in numeros if n <= 24)
    if nb_bas < 1 or nb_bas > 4:
        score_conformite *= 0.85

    # 3. Somme
    # 80% des tirages FDJ ont une somme entre 70 et 150
    # Somme minimale théorique : 1+2+3+4+5 = 15
    # Somme maximale théorique : 45+46+47+48+49 = 235
    somme = sum(numeros)
    if somme < 70 or somme > 150:
        score_conformite *= 0.7

    # 4. Dispersion
    # Évite les grilles trop concentrées (ex: 20-21-22-23-24, dispersion = 4)
    # Dispersion minimale théorique : 4 (pour 5 numéros consécutifs)
    # Dispersion maximale théorique : 48 (1 et 49)
    dispersion = max(numeros) - min(numeros)
    if dispersion < 15:
        score_conformite *= 0.6

    # 5. Suites consécutives
    # Compte le nombre de paires consécutives (n, n+1)
    # Ex: [5,6,7,10,20] → 2 suites (5-6 et 6-7)
    nums_sorted = sorted(numeros)
    suites = 0
    for i in range(len(nums_sorted) - 1):
        if nums_sorted[i+1] - nums_sorted[i] == 1:
            suites += 1

    if suites > 2:
        score_conformite *= 0.75

    return score_conformite


# ============================================================================
# GÉNÉRATION DE BADGES
# ============================================================================

def generer_badges(numeros: List[int], scores_hybrides: Dict[int, float]) -> List[str]:
    """
    Génère des badges explicatifs pour la grille

    Args:
        numeros: Liste de 5 numéros
        scores_hybrides: Scores hybrides de tous les numéros

    Returns:
        Liste de badges (strings)
    """
    badges = []

    # Score moyen des numéros de la grille
    score_moyen = sum(scores_hybrides[n] for n in numeros) / 5
    score_global_moyen = sum(scores_hybrides.values()) / len(scores_hybrides)

    # Badge fréquence
    if score_moyen > score_global_moyen * 1.1:
        badges.append("Numéros chauds")
    elif score_moyen < score_global_moyen * 0.9:
        badges.append("Mix de retards")
    else:
        badges.append("Équilibré")

    # Badge dispersion
    dispersion = max(numeros) - min(numeros)
    if dispersion > 35:
        badges.append("Large spectre")

    # Badge pairs/impairs
    nb_pairs = sum(1 for n in numeros if n % 2 == 0)
    if nb_pairs == 2 or nb_pairs == 3:
        badges.append("Pair/Impair OK")

    # Badge modèle
    badges.append("Hybride V1")

    return badges


# ============================================================================
# GÉNÉRATION DE GRILLE
# ============================================================================

async def generer_grille(
    conn,
    scores_hybrides: Dict[int, float]
) -> Dict[str, Any]:
    """
    Génère une grille unique avec validation des contraintes

    Utilise une boucle (non récursive) pour éviter les risques de stack overflow.

    Args:
        conn: Connexion MariaDB
        scores_hybrides: Scores hybrides pré-calculés

    Returns:
        Dict représentant la grille
    """
    MAX_TENTATIVES = 10

    # Convertir scores en probabilités
    probas = normaliser_en_probabilites(scores_hybrides)

    # Variables pour la meilleure grille trouvée
    meilleure_grille = None
    meilleur_score_conformite = 0

    # Boucle de génération (non récursive)
    for tentative in range(MAX_TENTATIVES):
        # Tirage pondéré de 5 numéros uniques
        numeros_disponibles = list(range(1, 50))
        probas_list = [probas[n] for n in numeros_disponibles]

        numeros = []
        for _ in range(5):
            # Tirage pondéré
            num = random.choices(numeros_disponibles, weights=probas_list, k=1)[0]
            numeros.append(num)

            # Retirer de la liste
            idx = numeros_disponibles.index(num)
            numeros_disponibles.pop(idx)
            probas_list.pop(idx)

        numeros = sorted(numeros)

        # Validation contraintes
        score_conformite = valider_contraintes(numeros)

        # Garder la meilleure grille trouvée
        if score_conformite > meilleur_score_conformite:
            meilleure_grille = numeros
            meilleur_score_conformite = score_conformite

        # Si score acceptable, on arrête
        if score_conformite >= 0.5:
            break

    # Utiliser la meilleure grille trouvée (même si score < 0.5)
    numeros = meilleure_grille
    score_conformite = meilleur_score_conformite

    # Numéro chance (fréquence simple)
    chance = await generer_numero_chance(conn)

    # Calcul du score moyen
    score_moyen = sum(scores_hybrides[n] for n in numeros) / 5

    # Score final de grille [50-100] (conservé pour compatibilité interne)
    score_final = int(score_moyen * score_conformite * 10000)
    score_final = min(100, max(50, score_final))

    # Badges explicatifs
    badges = generer_badges(numeros, scores_hybrides)

    return {
        'nums': numeros,
        'chance': chance,
        'score': score_final,  # Conservé pour compatibilité interne
        'badges': badges
    }


async def generer_numero_chance(conn) -> int:
    """
    Génère le numéro chance selon fréquence historique (5 ans)

    Returns:
        Numéro chance [1-10]
    """
    cursor = await conn.cursor()

    # Date limite (5 ans) basée sur le dernier tirage connu en base
    now = await get_reference_date(conn)
    date_limite = now - timedelta(days=CONFIG['fenetre_principale_annees'] * 365.25)

    # Fréquence des numéros chance
    await cursor.execute("""
        SELECT numero_chance, COUNT(*) as freq
        FROM tirages
        WHERE date_de_tirage >= %s
        GROUP BY numero_chance
    """, (date_limite.strftime("%Y-%m-%d"),))

    freq_chance = {i: 0 for i in range(1, 11)}
    for row in await cursor.fetchall():
        freq_chance[row['numero_chance']] = row['freq']

    # Normaliser en probabilités
    total = sum(freq_chance.values())
    if total == 0:
        # Fallback : uniforme
        return random.randint(1, 10)

    probas = [freq_chance[i] / total for i in range(1, 11)]

    # Tirage pondéré
    chance = random.choices(range(1, 11), weights=probas, k=1)[0]

    return chance


# ============================================================================
# EXPLICATIONS PÉDAGOGIQUES
# ============================================================================

async def build_explanation(nums: List[int], chance_num: int) -> Dict[str, Any]:
    """
    Construit les explications pédagogiques pour une grille générée
    Réutilise l'analyse statistique existante (lecture seule BDD)

    Args:
        nums: Liste des 5 numéros principaux
        chance_num: Numéro chance (1-10)

    Returns:
        Structure explain avec données descriptives par numéro

    Note: En cas d'erreur, retourne une structure minimale
    """
    from .stats import analyze_number

    explain = {
        "numbers": {},
        "chance": {},
        "summary": "Grille construite pour maximiser la cohérence interne : diversité des profils, équilibre pair/impair, répartition spatiale."
    }

    try:
        # Analyser chaque numéro principal (1-49)
        for num in nums:
            stats = await analyze_number(num)

            # Inférer des tags factuels basés sur la fréquence
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

        # Analyser le numéro chance (1-10, logique spécifique)
        async with get_connection() as conn:
            cursor = await conn.cursor()

            await cursor.execute(
                "SELECT COUNT(*) as count FROM tirages WHERE numero_chance = %s",
                (chance_num,)
            )
            result = await cursor.fetchone()
            chance_count = result['count'] if result else 0

            await cursor.execute(
                "SELECT date_de_tirage FROM tirages WHERE numero_chance = %s ORDER BY date_de_tirage DESC LIMIT 1",
                (chance_num,)
            )
            chance_last = await cursor.fetchone()
            chance_last_date = chance_last['date_de_tirage'] if chance_last else None

            # Calculer gap pour chance
            if chance_last_date:
                await cursor.execute(
                    "SELECT COUNT(*) as count FROM tirages WHERE date_de_tirage > %s",
                    (chance_last_date,)
                )
                result = await cursor.fetchone()
                chance_gap = result['count'] if result else 0
            else:
                chance_gap = 0

        # Tags pour chance
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
        # Graceful degradation : si erreur, on retourne une structure minimale
        # L'UI gérera l'absence d'explications détaillées
        logger.warning(f"[HYBRIDE] Erreur generation explications grille: {e}")

    return explain


# ============================================================================
# API PRINCIPALE
# ============================================================================

async def generate_grids(n: int = 5, mode: str = "balanced") -> Dict[str, Any]:
    """
    Point d'entrée principal : génère N grilles optimisées

    Args:
        n: Nombre de grilles à générer (max 20)
        mode: Mode de génération
            - "conservative" : favorise l'historique long terme (70% 5ans / 30% 2ans)
            - "balanced" : équilibre long/court terme (60% 5ans / 40% 2ans) [défaut]
            - "recent" : favorise les tendances récentes (40% 5ans / 60% 2ans)

    Returns:
        Dict {
            'grids': List[Dict],
            'metadata': Dict
        }
    """
    async with get_connection() as conn:
        # 1. Calcul des scores hybrides selon le mode choisi
        scores_hybrides = await calculer_scores_hybrides(conn, mode=mode)

        # 2. Génération des grilles
        grilles = []
        for i in range(n):
            grille = await generer_grille(conn, scores_hybrides)
            grilles.append(grille)

        # 3. Tri par score décroissant
        grilles = sorted(grilles, key=lambda g: g['score'], reverse=True)

        # 4. Métadonnées
        cursor = await conn.cursor()
        await cursor.execute("SELECT COUNT(*) as count FROM tirages")
        result = await cursor.fetchone()
        nb_tirages = result['count'] if result else 0

        await cursor.execute("SELECT MIN(date_de_tirage) as min_date, MAX(date_de_tirage) as max_date FROM tirages")
        result = await cursor.fetchone()
        date_min = result['min_date'] if result else None
        date_max = result['max_date'] if result else None

        # Pondérations réelles utilisées selon le mode
        if mode == "conservative":
            ponderation = "70/30"
        elif mode == "recent":
            ponderation = "40/60"
        else:  # balanced
            ponderation = f"{int(CONFIG['poids_principal']*100)}/{int(CONFIG['poids_recent']*100)}"

        metadata = {
            'mode': 'HYBRIDE_OPTIMAL_V1',
            'mode_generation': mode,  # conservative, balanced, ou recent
            'fenetre_principale_annees': CONFIG['fenetre_principale_annees'],
            'fenetre_recente_annees': CONFIG['fenetre_recente_annees'],
            'ponderation': ponderation,  # Poids long terme / court terme
            'nb_tirages_total': nb_tirages,
            'periode_base': f"{date_min} -> {date_max}",
            'avertissement': 'Le Loto reste un jeu de pur hasard. Aucune garantie de gain.'
        }

        return {
            'grids': grilles,
            'metadata': metadata
        }


# ============================================================================
# COMPATIBILITÉ ANCIENNE API (si nécessaire)
# ============================================================================

async def run_analysis(target_date: str) -> str:
    """
    Fonction de compatibilité pour l'ancienne interface CLI
    Génère 3 grilles et les formate en texte

    Args:
        target_date: Date du tirage au format JJ/MM/AAAA

    Returns:
        Résultat formaté en texte
    """
    # Validation basique de la date
    try:
        parsed_date = datetime.strptime(target_date, "%d/%m/%Y")
        formatted_date = parsed_date.strftime("%d/%m/%Y")
    except ValueError:
        formatted_date = target_date

    # Génération avec nouvelle API
    result_json = await generate_grids(n=3)
    grids = result_json['grids']
    metadata = result_json['metadata']

    # Construction du résultat texte
    result = []
    result.append(f"ANALYSE POUR LE TIRAGE DU {formatted_date}")
    result.append("")
    result.append("=" * 55)
    result.append("")

    # Informations modèle
    result.append("MODÈLE : HYBRIDE OPTIMAL V1")
    result.append(f"  Fenêtre principale : {metadata['fenetre_principale_annees']} ans")
    result.append(f"  Fenêtre récente    : {metadata['fenetre_recente_annees']} ans")
    result.append(f"  Pondération        : {metadata['ponderation']}")
    result.append(f"  Tirages analysés   : {metadata['nb_tirages_total']}")
    result.append("")
    result.append("=" * 55)
    result.append("")

    # Grilles recommandées
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
# ============================================================================
# API ENTRYPOINT (FastAPI / Cloud Run)
# ============================================================================

async def generate(prompt: str) -> dict:
    """
    Wrapper API pour FastAPI / Cloud Run.
    Le prompt est ignoré pour l'instant (choix volontaire).
    """

    try:
        # Appel du moteur principal
        result = await generate_grids(n=3, mode="balanced")

        return {
            "engine": "HYBRIDE_OPTIMAL_V1",
            "timestamp": datetime.utcnow().isoformat(),
            "input": prompt,
            "result": result
        }

    except Exception as e:
        return {
            "engine": "HYBRIDE_OPTIMAL_V1",
            "error": str(e)
        }
