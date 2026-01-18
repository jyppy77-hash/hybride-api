"""
Module d'analyse statistique descriptive pour le Loto
Analyse UNIQUEMENT l'historique réel - Aucune prédiction
"""

from typing import Dict, List, Optional
from .db import get_connection


def analyze_number(number: int) -> Dict:
    """
    Analyse l'historique complet d'un numéro principal (1-49)

    Args:
        number: Numéro à analyser (1-49)

    Returns:
        Dictionnaire contenant :
        - number: le numéro analysé
        - total_appearances: nombre total de sorties
        - first_appearance: date de première apparition (ou None)
        - last_appearance: date de dernière apparition (ou None)
        - current_gap: nombre de tirages depuis la dernière sortie
        - appearance_dates: liste des dates d'apparition
        - total_draws: nombre total de tirages dans la base
    """
    if not 1 <= number <= 49:
        raise ValueError("Le numéro doit être entre 1 et 49")

    conn = get_connection()
    cursor = conn.cursor()

    # Récupérer tous les tirages où le numéro apparaît (dans boule_1 à boule_5)
    query = """
        SELECT date_de_tirage
        FROM tirages
        WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s OR boule_4 = %s OR boule_5 = %s
        ORDER BY date_de_tirage ASC
    """
    cursor.execute(query, (number, number, number, number, number))
    appearance_dates = [row['date_de_tirage'] for row in cursor.fetchall()]

    # Nombre total d'apparitions
    total_appearances = len(appearance_dates)

    # Première et dernière apparition
    first_appearance = appearance_dates[0] if appearance_dates else None
    last_appearance = appearance_dates[-1] if appearance_dates else None

    # Calculer l'écart actuel (nombre de tirages depuis la dernière sortie)
    current_gap = 0
    if last_appearance:
        # Compter les tirages depuis la dernière apparition du numéro
        cursor.execute(
            "SELECT COUNT(*) as count FROM tirages WHERE date_de_tirage > %s",
            (last_appearance,)
        )
        result = cursor.fetchone()
        current_gap = result['count'] if result else 0

    # Nombre total de tirages dans la base
    cursor.execute("SELECT COUNT(*) as count FROM tirages")
    result = cursor.fetchone()
    total_draws = result['count'] if result else 0

    conn.close()

    return {
        "number": number,
        "total_appearances": total_appearances,
        "first_appearance": first_appearance,
        "last_appearance": last_appearance,
        "current_gap": current_gap,
        "appearance_dates": appearance_dates,
        "total_draws": total_draws
    }


def get_global_stats() -> Dict:
    """
    Récupère les statistiques globales de la base de données

    Returns:
        Dictionnaire contenant :
        - total_draws: nombre total de tirages
        - first_draw_date: date du premier tirage
        - last_draw_date: date du dernier tirage
        - period_covered: période couverte (texte)
    """
    conn = get_connection()
    cursor = conn.cursor()

    print("[DEBUG] get_global_stats - Début")

    # Stats globales
    cursor.execute("SELECT COUNT(*) as count FROM tirages")
    result = cursor.fetchone()
    print(f"[DEBUG] COUNT result: {result}, type: {type(result)}")
    total_draws = result['count'] if result else 0

    cursor.execute("SELECT MIN(date_de_tirage) as min_date, MAX(date_de_tirage) as max_date FROM tirages")
    result = cursor.fetchone()
    print(f"[DEBUG] MIN/MAX result: {result}, type: {type(result)}")
    first_draw_date = result['min_date'] if result else None
    last_draw_date = result['max_date'] if result else None

    conn.close()

    # Formater la période
    period_covered = f"{first_draw_date} à {last_draw_date}" if first_draw_date and last_draw_date else "N/A"

    print(f"[DEBUG] get_global_stats - Fin: total_draws={total_draws}, period={period_covered}")

    return {
        "total_draws": total_draws,
        "first_draw_date": first_draw_date,
        "last_draw_date": last_draw_date,
        "period_covered": period_covered
    }


def get_top_flop_numbers() -> Dict:
    """
    Calcule les fréquences de sortie pour tous les numéros (1-49)
    et retourne les tops et flops

    Returns:
        Dictionnaire contenant :
        - total_draws: nombre total de tirages dans la base
        - top: liste de tous les numéros triés par count DESC, puis number ASC
        - flop: liste de tous les numéros triés par count ASC, puis number ASC

        Chaque élément contient : {"number": int, "count": int}
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Nombre total de tirages
    cursor.execute("SELECT COUNT(*) as count FROM tirages")
    result = cursor.fetchone()
    total_draws = result['count'] if result else 0

    # Calculer la fréquence de chaque numéro (1-49)
    number_counts = []

    for number in range(1, 50):  # 1 à 49 inclus
        # Compter les apparitions dans boule_1 à boule_5
        query = """
            SELECT COUNT(*) as count
            FROM tirages
            WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s OR boule_4 = %s OR boule_5 = %s
        """
        cursor.execute(query, (number, number, number, number, number))
        result = cursor.fetchone()
        count = result['count'] if result else 0

        number_counts.append({
            "number": number,
            "count": count
        })

    conn.close()

    # Trier pour TOP : count DESC, puis number ASC
    top_sorted = sorted(number_counts, key=lambda x: (-x["count"], x["number"]))

    # Trier pour FLOP : count ASC, puis number ASC
    flop_sorted = sorted(number_counts, key=lambda x: (x["count"], x["number"]))

    return {
        "total_draws": total_draws,
        "top": top_sorted,
        "flop": flop_sorted
    }
