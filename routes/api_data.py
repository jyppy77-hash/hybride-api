from fastapi import APIRouter, Query
import logging

import db_cloudsql
from engine.stats import get_global_stats

logger = logging.getLogger(__name__)

router = APIRouter()


# =========================
# API Tirages (Cloud SQL)
# =========================

@router.get("/api/tirages/count")
async def api_tirages_count():
    """
    Retourne le nombre total de tirages en base.

    Returns:
        JSON {success: bool, data: {total: int}, error: str|null}
    """
    try:
        total = db_cloudsql.get_tirages_count()
        return {
            "success": True,
            "data": {"total": total},
            "error": None
        }
    except Exception as e:
        logger.error(f"Erreur /api/tirages/count: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }


@router.get("/api/tirages/latest")
async def api_tirages_latest():
    """
    Retourne le tirage le plus recent.

    Returns:
        JSON {success: bool, data: {...tirage}, error: str|null}
    """
    try:
        tirage = db_cloudsql.get_latest_tirage()
        if tirage:
            return {
                "success": True,
                "data": tirage,
                "error": None
            }
        else:
            return {
                "success": False,
                "data": None,
                "error": "Aucun tirage trouve"
            }
    except Exception as e:
        logger.error(f"Erreur /api/tirages/latest: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }


@router.get("/api/tirages/list")
async def api_tirages_list(
    limit: int = Query(default=10, ge=1, le=100, description="Nombre de tirages"),
    offset: int = Query(default=0, ge=0, description="Offset pour pagination")
):
    """
    Retourne une liste de tirages (du plus recent au plus ancien).

    Args:
        limit: Nombre max de tirages (1-100, defaut: 10)
        offset: Decalage pour pagination (defaut: 0)

    Returns:
        JSON {success: bool, data: {items: [...], count: int, limit: int}, error: str|null}
    """
    try:
        tirages = db_cloudsql.get_tirages_list(limit=limit, offset=offset)
        return {
            "success": True,
            "data": {
                "items": tirages,
                "count": len(tirages),
                "limit": limit,
                "offset": offset
            },
            "error": None
        }
    except Exception as e:
        logger.error(f"Erreur /api/tirages/list: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }


# =========================
# API Database Info
# =========================

@router.get("/database-info")
async def database_info():
    """
    Retourne les informations sur la base de donnees.
    Utilise par le frontend pour afficher le statut.
    """
    try:
        result = db_cloudsql.test_connection()

        if result['status'] == 'ok':
            return {
                "status": "success",
                "exists": True,
                "is_ready": result['total_tirages'] > 0,
                "total_rows": result['total_tirages'],
                "total_draws": result['total_tirages'],
                "date_min": result['date_min'],
                "date_max": result['date_max'],
                "first_draw": result['date_min'],
                "last_draw": result['date_max'],
                "file_size_mb": 0  # N/A pour Cloud SQL
            }
        else:
            return {
                "status": "error",
                "exists": False,
                "is_ready": False,
                "error": result.get('error', 'Connexion echouee')
            }
    except Exception as e:
        logger.error(f"Erreur /database-info: {e}")
        return {
            "status": "error",
            "exists": False,
            "is_ready": False,
            "error": str(e)
        }


# =========================
# API Database Info (light)
# =========================

@router.get("/api/database-info")
async def api_database_info():
    """
    Retourne total_draws, first_draw, last_draw.
    Endpoint léger utilisé par la FAQ pour affichage dynamique.
    """
    try:
        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total,
                   MIN(date_de_tirage) as date_min,
                   MAX(date_de_tirage) as date_max
            FROM tirages
        """)
        row = cursor.fetchone()
        conn.close()

        return {
            "total_draws": row["total"],
            "first_draw": str(row["date_min"]) if row["date_min"] else None,
            "last_draw": str(row["date_max"]) if row["date_max"] else None
        }
    except Exception as e:
        logger.error(f"Erreur /api/database-info: {e}")
        return {
            "total_draws": None,
            "first_draw": None,
            "last_draw": None
        }


@router.get("/stats")
async def stats():
    """
    Retourne les statistiques globales.
    """
    try:
        global_stats = get_global_stats()
        return {
            "success": True,
            "stats": global_stats
        }
    except Exception as e:
        logger.error(f"Erreur /stats: {e}")
        return {
            "success": False,
            "message": str(e)
        }


# =========================
# API Stats Completes
# =========================

@router.get("/api/stats")
async def api_stats():
    """
    Retourne les statistiques completes pour le simulateur et la page stats.
    Base sur les tirages reels de Cloud SQL.

    Returns:
        - total_tirages
        - periode (debut, fin)
        - frequences de chaque numero (1-49)
        - retards (tirages depuis derniere apparition)
        - top_chauds (5 numeros les plus frequents)
        - top_froids (5 numeros les moins frequents)
    """
    try:
        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        # Total tirages et periode
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                MIN(date_de_tirage) as date_min,
                MAX(date_de_tirage) as date_max
            FROM tirages
        """)
        info = cursor.fetchone()
        total_tirages = info['total']
        date_min = str(info['date_min']) if info['date_min'] else None
        date_max = str(info['date_max']) if info['date_max'] else None

        # Calculer frequences et retards pour chaque numero (1-49)
        frequences = {}
        retards = {}

        for num in range(1, 50):
            # Frequence
            cursor.execute("""
                SELECT COUNT(*) as freq
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            freq_result = cursor.fetchone()
            frequences[str(num)] = freq_result['freq'] if freq_result else 0

            # Retard (nombre de tirages depuis derniere apparition)
            cursor.execute("""
                SELECT MAX(date_de_tirage) as last_date
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            last_result = cursor.fetchone()

            if last_result and last_result['last_date']:
                cursor.execute("""
                    SELECT COUNT(*) as gap
                    FROM tirages
                    WHERE date_de_tirage > %s
                """, (last_result['last_date'],))
                gap_result = cursor.fetchone()
                retards[str(num)] = gap_result['gap'] if gap_result else 0
            else:
                retards[str(num)] = total_tirages

        conn.close()

        # Trier pour top chauds et froids
        sorted_by_freq = sorted(
            [(int(k), v) for k, v in frequences.items()],
            key=lambda x: x[1],
            reverse=True
        )

        top_chauds = [{"numero": n, "freq": f} for n, f in sorted_by_freq[:5]]
        top_froids = [{"numero": n, "freq": f} for n, f in sorted_by_freq[-5:]]

        return {
            "success": True,
            "data": {
                "total_tirages": total_tirages,
                "periode": {
                    "debut": date_min,
                    "fin": date_max
                },
                "frequences": frequences,
                "retards": retards,
                "top_chauds": top_chauds,
                "top_froids": top_froids
            },
            "error": None
        }

    except Exception as e:
        logger.error(f"Erreur /api/stats: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }


@router.get("/api/numbers-heat")
async def api_numbers_heat():
    """
    Retourne la classification chaud/neutre/froid pour chaque numero (1-49).
    Utilise par le simulateur pour colorer les boutons.
    """
    try:
        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        # Total tirages
        cursor.execute("SELECT COUNT(*) as total FROM tirages")
        total = cursor.fetchone()['total']

        # Calculer frequences
        numbers_data = {}
        frequencies = []

        for num in range(1, 50):
            cursor.execute("""
                SELECT COUNT(*) as freq
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            freq = cursor.fetchone()['freq']

            # Derniere apparition
            cursor.execute("""
                SELECT MAX(date_de_tirage) as last_date
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            last = cursor.fetchone()
            last_date = str(last['last_date']) if last and last['last_date'] else None

            numbers_data[num] = {
                "frequency": freq,
                "last_draw": last_date
            }
            frequencies.append(freq)

        conn.close()

        # Calculer seuils (top 33% = chaud, bottom 33% = froid)
        frequencies.sort(reverse=True)
        seuil_chaud = frequencies[len(frequencies) // 3]
        seuil_froid = frequencies[2 * len(frequencies) // 3]

        # Classifier chaque numero
        for num in range(1, 50):
            freq = numbers_data[num]["frequency"]
            if freq >= seuil_chaud:
                numbers_data[num]["category"] = "hot"
            elif freq <= seuil_froid:
                numbers_data[num]["category"] = "cold"
            else:
                numbers_data[num]["category"] = "neutral"

        return {
            "success": True,
            "numbers": numbers_data,
            "total_tirages": total,
            "seuils": {
                "chaud": seuil_chaud,
                "froid": seuil_froid
            }
        }

    except Exception as e:
        logger.error(f"Erreur /api/numbers-heat: {e}")
        return {
            "success": False,
            "numbers": {},
            "error": str(e)
        }


@router.get("/draw/{date}")
async def get_draw_by_date(date: str):
    """
    Recherche un tirage par date (format YYYY-MM-DD).
    """
    try:
        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance
            FROM tirages
            WHERE date_de_tirage = %s
        """, (date,))

        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                "success": True,
                "found": True,
                "draw": {
                    "date": str(result['date_de_tirage']),
                    "n1": result['boule_1'],
                    "n2": result['boule_2'],
                    "n3": result['boule_3'],
                    "n4": result['boule_4'],
                    "n5": result['boule_5'],
                    "chance": result['numero_chance']
                }
            }
        else:
            return {
                "success": True,
                "found": False,
                "message": f"Aucun tirage pour la date {date}"
            }

    except Exception as e:
        logger.error(f"Erreur /draw/{date}: {e}")
        return {
            "success": False,
            "found": False,
            "message": str(e)
        }


@router.get("/api/stats/number/{number}")
async def api_stats_number(number: int):
    """
    Analyse complete d'un numero specifique (1-49).
    """
    try:
        if not 1 <= number <= 49:
            return {"success": False, "message": "Numero doit etre entre 1 et 49"}

        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        # Toutes les apparitions
        cursor.execute("""
            SELECT date_de_tirage
            FROM tirages
            WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
               OR boule_4 = %s OR boule_5 = %s
            ORDER BY date_de_tirage ASC
        """, (number, number, number, number, number))

        results = cursor.fetchall()
        appearance_dates = [str(r['date_de_tirage']) for r in results]

        total_appearances = len(appearance_dates)
        first_appearance = appearance_dates[0] if appearance_dates else None
        last_appearance = appearance_dates[-1] if appearance_dates else None

        # Ecart actuel
        current_gap = 0
        if last_appearance:
            cursor.execute("""
                SELECT COUNT(*) as gap
                FROM tirages
                WHERE date_de_tirage > %s
            """, (last_appearance,))
            gap_result = cursor.fetchone()
            current_gap = gap_result['gap'] if gap_result else 0

        conn.close()

        return {
            "success": True,
            "number": number,
            "total_appearances": total_appearances,
            "first_appearance": first_appearance,
            "last_appearance": last_appearance,
            "current_gap": current_gap,
            "appearance_dates": appearance_dates
        }

    except Exception as e:
        logger.error(f"Erreur /api/stats/number/{number}: {e}")
        return {
            "success": False,
            "message": str(e)
        }


@router.get("/api/stats/top-flop")
async def api_stats_top_flop():
    """
    Retourne le classement des numeros par frequence (Top et Flop).
    """
    try:
        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        # Calculer frequences
        numbers_freq = []

        for num in range(1, 50):
            cursor.execute("""
                SELECT COUNT(*) as freq
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            freq = cursor.fetchone()['freq']
            numbers_freq.append({"number": num, "count": freq})

        conn.close()

        # Trier
        top = sorted(numbers_freq, key=lambda x: (-x['count'], x['number']))
        flop = sorted(numbers_freq, key=lambda x: (x['count'], x['number']))

        return {
            "success": True,
            "top": top,
            "flop": flop
        }

    except Exception as e:
        logger.error(f"Erreur /api/stats/top-flop: {e}")
        return {
            "success": False,
            "message": str(e)
        }
