"""
Module d'analyse statistique descriptive pour le Loto et l'EuroMillions.
Analyse UNIQUEMENT l'historique réel - Aucune prédiction.

Config-driven via EngineConfig (V55 audit fix F09).

SQL SECURITY NOTE (F08 audit 24/03/2026): table names come from EngineConfig
frozen dataclass (compile-time constants), never from user input. f-string
interpolation for table names is safe in this context.
"""

import logging
from config.engine import EngineConfig, LOTO_CONFIG
from .db import get_connection
from services.cache import cache_get, cache_set

logger = logging.getLogger(__name__)


async def analyze_number(number: int, cfg: EngineConfig = LOTO_CONFIG) -> dict:
    """
    Analyse l'historique complet d'un numéro principal.

    Args:
        number: Numéro à analyser (cfg.num_min..cfg.num_max)
        cfg: Configuration du jeu (default: LOTO_CONFIG pour rétrocompatibilité)

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
    if not cfg.num_min <= number <= cfg.num_max:
        raise ValueError(f"Le numéro doit être entre {cfg.num_min} et {cfg.num_max}")

    table = cfg.table_name

    async with get_connection() as conn:
        cursor = await conn.cursor()

        # Récupérer tous les tirages où le numéro apparaît (dans boule_1 à boule_5)
        query = f"""
            SELECT date_de_tirage
            FROM {table}
            WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s OR boule_4 = %s OR boule_5 = %s
            ORDER BY date_de_tirage ASC
        """
        await cursor.execute(query, (number, number, number, number, number))
        appearance_dates = [row['date_de_tirage'] for row in await cursor.fetchall()]

        # Nombre total d'apparitions
        total_appearances = len(appearance_dates)

        # Première et dernière apparition
        first_appearance = appearance_dates[0] if appearance_dates else None
        last_appearance = appearance_dates[-1] if appearance_dates else None

        # Calculer l'écart actuel (nombre de tirages depuis la dernière sortie)
        current_gap = 0
        if last_appearance:
            # Compter les tirages depuis la dernière apparition du numéro
            await cursor.execute(
                f"SELECT COUNT(*) as count FROM {table} WHERE date_de_tirage > %s",
                (last_appearance,)
            )
            result = await cursor.fetchone()
            current_gap = result['count'] if result else 0

        # Nombre total de tirages dans la base
        await cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
        result = await cursor.fetchone()
        total_draws = result['count'] if result else 0

    return {
        "number": number,
        "total_appearances": total_appearances,
        "first_appearance": first_appearance,
        "last_appearance": last_appearance,
        "current_gap": current_gap,
        "appearance_dates": appearance_dates,
        "total_draws": total_draws
    }


async def get_global_stats(cfg: EngineConfig = LOTO_CONFIG) -> dict:
    """
    Récupère les statistiques globales de la base de données.
    Résultat mis en cache 1 h.

    Args:
        cfg: Configuration du jeu (default: LOTO_CONFIG pour rétrocompatibilité)

    Returns:
        Dictionnaire contenant :
        - total_draws: nombre total de tirages
        - first_draw_date: date du premier tirage
        - last_draw_date: date du dernier tirage
        - period_covered: période couverte (texte)
    """
    cache_key = f"global_stats_{cfg.game}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    table = cfg.table_name

    async with get_connection() as conn:
        cursor = await conn.cursor()

        logger.debug("[STATS] get_global_stats - Debut")

        # Stats globales
        await cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
        result = await cursor.fetchone()
        logger.debug(f"[STATS] COUNT result: {result}")
        total_draws = result['count'] if result else 0

        await cursor.execute(
            f"SELECT MIN(date_de_tirage) as min_date, MAX(date_de_tirage) as max_date FROM {table}"
        )
        result = await cursor.fetchone()
        logger.debug(f"[STATS] MIN/MAX result: {result}")
        first_draw_date = result['min_date'] if result else None
        last_draw_date = result['max_date'] if result else None

    # Formater la période
    # NOTE (F09 audit 24/03/2026): Period formatted with French "à" (preposition).
    # This is cache-side/internal metadata, not user-facing. Frontend handles
    # display formatting per locale. If i18n needed, use config/i18n.py pattern.
    period_covered = f"{first_draw_date} à {last_draw_date}" if first_draw_date and last_draw_date else "N/A"

    logger.debug(f"[STATS] get_global_stats - Fin: total_draws={total_draws}, period={period_covered}")

    data = {
        "total_draws": total_draws,
        "first_draw_date": first_draw_date,
        "last_draw_date": last_draw_date,
        "period_covered": period_covered
    }
    await cache_set(cache_key, data)
    return data


async def get_top_flop_numbers(cfg: EngineConfig = LOTO_CONFIG) -> dict:
    """
    Calcule les fréquences de sortie pour tous les numéros et retourne les tops et flops.

    Args:
        cfg: Configuration du jeu (default: LOTO_CONFIG pour rétrocompatibilité)

    Returns:
        Dictionnaire contenant :
        - total_draws: nombre total de tirages dans la base
        - top: liste de tous les numéros triés par count DESC, puis number ASC
        - flop: liste de tous les numéros triés par count ASC, puis number ASC

        Chaque élément contient : {"number": int, "count": int}
    """
    table = cfg.table_name
    num_range = range(cfg.num_min, cfg.num_max + 1)

    async with get_connection() as conn:
        cursor = await conn.cursor()

        # Nombre total de tirages
        await cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
        result = await cursor.fetchone()
        total_draws = result['count'] if result else 0

        # Frequences (1 requete UNION ALL au lieu de N)
        await cursor.execute(f"""
            SELECT num, COUNT(*) as freq FROM (
                SELECT boule_1 as num FROM {table}
                UNION ALL SELECT boule_2 FROM {table}
                UNION ALL SELECT boule_3 FROM {table}
                UNION ALL SELECT boule_4 FROM {table}
                UNION ALL SELECT boule_5 FROM {table}
            ) t
            GROUP BY num
            ORDER BY num
        """)
        freq_map = {row['num']: row['freq'] for row in await cursor.fetchall()}
        number_counts = [{"number": num, "count": freq_map.get(num, 0)} for num in num_range]

    # Trier pour TOP : count DESC, puis number ASC
    top_sorted = sorted(number_counts, key=lambda x: (-x["count"], x["number"]))

    # Trier pour FLOP : count ASC, puis number ASC
    flop_sorted = sorted(number_counts, key=lambda x: (x["count"], x["number"]))

    return {
        "total_draws": total_draws,
        "top": top_sorted,
        "flop": flop_sorted
    }
