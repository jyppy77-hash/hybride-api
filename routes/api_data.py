from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from datetime import timedelta
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
        return JSONResponse(status_code=500, content={
            "success": False,
            "data": None,
            "error": "Erreur interne du serveur"
        })


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
            return JSONResponse(status_code=404, content={
                "success": False,
                "data": None,
                "error": "Aucun tirage trouve"
            })
    except Exception as e:
        logger.error(f"Erreur /api/tirages/latest: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "data": None,
            "error": "Erreur interne du serveur"
        })


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
        return JSONResponse(status_code=500, content={
            "success": False,
            "data": None,
            "error": "Erreur interne du serveur"
        })


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
            return JSONResponse(status_code=503, content={
                "status": "error",
                "exists": False,
                "is_ready": False,
                "error": result.get('error', 'Connexion echouee')
            })
    except Exception as e:
        logger.error(f"Erreur /database-info: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "exists": False,
            "is_ready": False,
            "error": "Erreur interne du serveur"
        })


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
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as total,
                       MIN(date_de_tirage) as date_min,
                       MAX(date_de_tirage) as date_max
                FROM tirages
            """)
            row = cursor.fetchone()
        finally:
            conn.close()

        return {
            "total_draws": row["total"],
            "first_draw": str(row["date_min"]) if row["date_min"] else None,
            "last_draw": str(row["date_max"]) if row["date_max"] else None
        }
    except Exception as e:
        logger.error(f"Erreur /api/database-info: {e}")
        return JSONResponse(status_code=500, content={
            "total_draws": None,
            "first_draw": None,
            "last_draw": None
        })


# =========================
# API META Windows Info (slider)
# =========================

@router.get("/api/meta-windows-info")
async def api_meta_windows_info():
    """
    Retourne les plages de dates et le nombre de tirages
    pour chaque fenêtre d'analyse (slider META).
    Un seul appel, toutes les fenêtres.
    """
    from datetime import timedelta

    try:
        conn = db_cloudsql.get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT date_de_tirage FROM tirages
                ORDER BY date_de_tirage DESC
            """)
            all_dates = [row["date_de_tirage"] for row in cursor.fetchall()]
        finally:
            conn.close()

        total = len(all_dates)
        last_draw = all_dates[0] if all_dates else None
        first_draw = all_dates[-1] if all_dates else None

        # Fenêtres par nombre de tirages
        tirages_windows = {}
        for size in [100, 200, 300, 400, 500, 600, 700, 800]:
            if size <= total:
                tirages_windows[size] = {
                    "draws": size,
                    "start": str(all_dates[size - 1]),
                    "end": str(last_draw)
                }
            else:
                tirages_windows[size] = {
                    "draws": total,
                    "start": str(first_draw),
                    "end": str(last_draw)
                }
        tirages_windows["GLOBAL"] = {
            "draws": total,
            "start": str(first_draw),
            "end": str(last_draw)
        }

        # Fenêtres par années (timedelta fallback, pas de dateutil)
        annees_windows = {}
        for y in [1, 2, 3, 4, 5, 6]:
            date_limit = last_draw - timedelta(days=365 * y)
            draws_in_range = [d for d in all_dates if d >= date_limit]
            annees_windows[y] = {
                "draws": len(draws_in_range),
                "start": str(draws_in_range[-1]) if draws_in_range else str(first_draw),
                "end": str(last_draw)
            }
        annees_windows["GLOBAL"] = {
            "draws": total,
            "start": str(first_draw),
            "end": str(last_draw)
        }

        return {
            "tirages": tirages_windows,
            "annees": annees_windows,
            "total_draws": total,
            "last_draw": str(last_draw),
            "first_draw": str(first_draw)
        }

    except Exception as e:
        logger.error(f"Erreur /api/meta-windows-info: {e}")
        return JSONResponse(status_code=500, content={"tirages": None, "annees": None})


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
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": "Erreur interne du serveur"
        })


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
        try:
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
        finally:
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
        return JSONResponse(status_code=500, content={
            "success": False,
            "data": None,
            "error": "Erreur interne du serveur"
        })


@router.get("/api/numbers-heat")
async def api_numbers_heat():
    """
    Retourne la classification chaud/neutre/froid pour chaque numero (1-49).
    Utilise par le simulateur pour colorer les boutons.
    """
    try:
        conn = db_cloudsql.get_connection()
        try:
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
        finally:
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
        return JSONResponse(status_code=500, content={
            "success": False,
            "numbers": {},
            "error": "Erreur interne du serveur"
        })


@router.get("/draw/{date}")
async def get_draw_by_date(date: str):
    """
    Recherche un tirage par date (format YYYY-MM-DD).
    """
    try:
        conn = db_cloudsql.get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance
                FROM tirages
                WHERE date_de_tirage = %s
            """, (date,))

            result = cursor.fetchone()
        finally:
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
            return JSONResponse(status_code=404, content={
                "success": True,
                "found": False,
                "message": f"Aucun tirage pour la date {date}"
            })

    except Exception as e:
        logger.error(f"Erreur /draw/{date}: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "found": False,
            "message": "Erreur interne du serveur"
        })


@router.get("/api/stats/number/{number}")
async def api_stats_number(number: int):
    """
    Analyse complete d'un numero specifique (1-49).
    """
    try:
        if not 1 <= number <= 49:
            return JSONResponse(status_code=400, content={
                "success": False, "message": "Numero doit etre entre 1 et 49"
            })

        conn = db_cloudsql.get_connection()
        try:
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
        finally:
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
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": "Erreur interne du serveur"
        })


@router.get("/api/stats/top-flop")
async def api_stats_top_flop():
    """
    Retourne le classement des numeros par frequence (Top et Flop).
    """
    try:
        conn = db_cloudsql.get_connection()
        try:
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
        finally:
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
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": "Erreur interne du serveur"
        })


# =========================
# API Hybride Stats (chatbot BDD)
# =========================

def get_numero_stats(numero: int, type_num: str = "principal") -> dict:
    """
    Calcule les statistiques completes d'un numero pour le chatbot HYBRIDE.
    Appelable en interne (depuis api_chat.py) ou via l'endpoint.

    Args:
        numero: le numero a analyser
        type_num: "principal" (1-49) ou "chance" (1-10)

    Returns:
        dict avec toutes les stats ou None si erreur
    """
    if type_num == "principal" and not 1 <= numero <= 49:
        return None
    if type_num == "chance" and not 1 <= numero <= 10:
        return None

    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()

        # Total tirages et periode
        cursor.execute("""
            SELECT COUNT(*) as total,
                   MIN(date_de_tirage) as date_min,
                   MAX(date_de_tirage) as date_max
            FROM tirages
        """)
        info = cursor.fetchone()
        total_tirages = info['total']
        date_min = info['date_min']
        date_max = info['date_max']

        # Toutes les apparitions du numero (triees ASC)
        if type_num == "principal":
            cursor.execute("""
                SELECT date_de_tirage
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
                ORDER BY date_de_tirage ASC
            """, (numero, numero, numero, numero, numero))
        else:
            cursor.execute("""
                SELECT date_de_tirage
                FROM tirages
                WHERE numero_chance = %s
                ORDER BY date_de_tirage ASC
            """, (numero,))

        rows = cursor.fetchall()
        appearance_dates = [row['date_de_tirage'] for row in rows]
        frequence_totale = len(appearance_dates)

        # Derniere sortie
        derniere_sortie = appearance_dates[-1] if appearance_dates else None

        # Ecart actuel
        ecart_actuel = 0
        if derniere_sortie:
            cursor.execute(
                "SELECT COUNT(*) as gap FROM tirages WHERE date_de_tirage > %s",
                (derniere_sortie,)
            )
            ecart_actuel = cursor.fetchone()['gap']

        # Ecart moyen (moyenne des ecarts entre apparitions consecutives)
        ecart_moyen = 0.0
        if len(appearance_dates) >= 2:
            # Recuperer toutes les dates de tirages pour calculer les index
            cursor.execute(
                "SELECT date_de_tirage FROM tirages ORDER BY date_de_tirage ASC"
            )
            all_dates = [r['date_de_tirage'] for r in cursor.fetchall()]
            date_to_index = {d: i for i, d in enumerate(all_dates)}

            indices = [date_to_index[d] for d in appearance_dates if d in date_to_index]
            if len(indices) >= 2:
                gaps = [indices[i+1] - indices[i] for i in range(len(indices) - 1)]
                ecart_moyen = round(sum(gaps) / len(gaps), 1)

        # Classement par frequence (parmi les 49 principaux ou 10 chances)
        classement = 1
        if type_num == "principal":
            for num in range(1, 50):
                if num == numero:
                    continue
                cursor.execute("""
                    SELECT COUNT(*) as freq FROM tirages
                    WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                       OR boule_4 = %s OR boule_5 = %s
                """, (num, num, num, num, num))
                if cursor.fetchone()['freq'] > frequence_totale:
                    classement += 1
            classement_sur = 49
        else:
            for num in range(1, 11):
                if num == numero:
                    continue
                cursor.execute(
                    "SELECT COUNT(*) as freq FROM tirages WHERE numero_chance = %s",
                    (num,)
                )
                if cursor.fetchone()['freq'] > frequence_totale:
                    classement += 1
            classement_sur = 10

        # Categorie chaud/neutre/froid (sur 2 ans)
        date_2ans = date_max - timedelta(days=730)
        if type_num == "principal":
            cursor.execute("""
                SELECT COUNT(*) as freq FROM tirages
                WHERE date_de_tirage >= %s
                  AND (boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                       OR boule_4 = %s OR boule_5 = %s)
            """, (date_2ans, numero, numero, numero, numero, numero))
            freq_2ans = cursor.fetchone()['freq']

            # Compter pour tous les numeros sur 2 ans
            all_freq_2ans = []
            for num in range(1, 50):
                cursor.execute("""
                    SELECT COUNT(*) as freq FROM tirages
                    WHERE date_de_tirage >= %s
                      AND (boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                           OR boule_4 = %s OR boule_5 = %s)
                """, (date_2ans, num, num, num, num, num))
                all_freq_2ans.append(cursor.fetchone()['freq'])
        else:
            cursor.execute("""
                SELECT COUNT(*) as freq FROM tirages
                WHERE date_de_tirage >= %s AND numero_chance = %s
            """, (date_2ans, numero))
            freq_2ans = cursor.fetchone()['freq']

            all_freq_2ans = []
            for num in range(1, 11):
                cursor.execute("""
                    SELECT COUNT(*) as freq FROM tirages
                    WHERE date_de_tirage >= %s AND numero_chance = %s
                """, (date_2ans, num))
                all_freq_2ans.append(cursor.fetchone()['freq'])

        all_freq_2ans.sort(reverse=True)
        tiers = len(all_freq_2ans) // 3
        seuil_chaud = all_freq_2ans[tiers] if tiers < len(all_freq_2ans) else 0
        seuil_froid = all_freq_2ans[2 * tiers] if 2 * tiers < len(all_freq_2ans) else 0

        if freq_2ans >= seuil_chaud:
            categorie = "chaud"
        elif freq_2ans <= seuil_froid:
            categorie = "froid"
        else:
            categorie = "neutre"

    except Exception as e:
        logger.error(f"Erreur get_numero_stats({numero}, {type_num}): {e}")
        return None
    finally:
        conn.close()

    pourcentage = round(frequence_totale / total_tirages * 100, 2) if total_tirages else 0

    return {
        "numero": numero,
        "type": type_num,
        "frequence_totale": frequence_totale,
        "pourcentage_apparition": f"{pourcentage}%",
        "derniere_sortie": str(derniere_sortie) if derniere_sortie else None,
        "ecart_actuel": ecart_actuel,
        "ecart_moyen": ecart_moyen,
        "classement": classement,
        "classement_sur": classement_sur,
        "categorie": categorie,
        "total_tirages": total_tirages,
        "periode": f"{date_min} au {date_max}" if date_min and date_max else "N/A"
    }


@router.get("/api/hybride-stats")
async def api_hybride_stats(
    numero: int = Query(..., description="Numero a analyser"),
    type: str = Query(default="principal", description="principal ou chance")
):
    """
    Retourne les statistiques completes d'un numero pour le chatbot HYBRIDE.
    """
    if type not in ("principal", "chance"):
        return JSONResponse(status_code=400, content={
            "success": False, "data": None, "error": "type doit etre 'principal' ou 'chance'"
        })

    stats = get_numero_stats(numero, type)
    if stats is None:
        return JSONResponse(status_code=404, content={
            "success": False, "data": None, "error": f"Numero {numero} invalide pour type {type}"
        })

    return {"success": True, "data": stats, "error": None}


# =========================
# Analyse grille pour chatbot
# =========================

def analyze_grille_for_chat(nums: list, chance: int = None) -> dict:
    """
    Analyse complete d'une grille pour le chatbot HYBRIDE.
    Reutilise la logique de /api/analyze-custom-grid.

    Args:
        nums: liste de 5 numeros (1-49), uniques
        chance: numero chance optionnel (1-10)

    Returns:
        dict avec analyse complete ou None si erreur
    """
    nums = sorted(nums)

    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()

        # Total tirages
        cursor.execute("SELECT COUNT(*) as total FROM tirages")
        total_tirages = cursor.fetchone()['total']

        # Frequences de chaque numero de la grille
        frequencies = []
        for num in nums:
            cursor.execute("""
                SELECT COUNT(*) as freq FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            frequencies.append(cursor.fetchone()['freq'])

        # Classification chaud/neutre/froid (seuils globaux)
        all_freq = []
        for n in range(1, 50):
            cursor.execute("""
                SELECT COUNT(*) as freq FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (n, n, n, n, n))
            all_freq.append((n, cursor.fetchone()['freq']))

        all_freq_sorted = sorted([f for _, f in all_freq], reverse=True)
        seuil_chaud = all_freq_sorted[len(all_freq_sorted) // 3]
        seuil_froid = all_freq_sorted[2 * len(all_freq_sorted) // 3]

        num_freq_map = {n: f for n, f in all_freq}
        numeros_chauds = [n for n in nums if num_freq_map[n] >= seuil_chaud]
        numeros_froids = [n for n in nums if num_freq_map[n] <= seuil_froid]
        numeros_neutres = [n for n in nums if n not in numeros_chauds and n not in numeros_froids]

        # Verification historique — combinaison exacte
        if chance is not None:
            cursor.execute("""
                SELECT date_de_tirage FROM tirages
                WHERE boule_1 = %s AND boule_2 = %s AND boule_3 = %s
                      AND boule_4 = %s AND boule_5 = %s AND numero_chance = %s
                ORDER BY date_de_tirage DESC
            """, (*nums, chance))
        else:
            cursor.execute("""
                SELECT date_de_tirage FROM tirages
                WHERE boule_1 = %s AND boule_2 = %s AND boule_3 = %s
                      AND boule_4 = %s AND boule_5 = %s
                ORDER BY date_de_tirage DESC
            """, tuple(nums))
        exact_matches = cursor.fetchall()
        exact_dates = [str(row['date_de_tirage']) for row in exact_matches]

        # Meilleure correspondance
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
            ORDER BY match_count DESC
            LIMIT 1
        """, (*nums, *nums, *nums, *nums, *nums))
        best_match = cursor.fetchone()

        best_match_numbers = []
        best_match_count = 0
        best_match_date = None
        if best_match:
            tirage_nums = [best_match['boule_1'], best_match['boule_2'],
                           best_match['boule_3'], best_match['boule_4'],
                           best_match['boule_5']]
            best_match_numbers = sorted([n for n in nums if n in tirage_nums])
            best_match_count = best_match['match_count']
            best_match_date = str(best_match['date_de_tirage'])

    except Exception as e:
        logger.error(f"Erreur analyze_grille_for_chat({nums}): {e}")
        return None
    finally:
        conn.close()

    # Metriques de la grille
    nb_pairs = sum(1 for n in nums if n % 2 == 0)
    nb_impairs = 5 - nb_pairs
    nb_bas = sum(1 for n in nums if n <= 24)
    nb_hauts = 5 - nb_bas
    somme = sum(nums)
    dispersion = max(nums) - min(nums)
    consecutifs = sum(1 for i in range(4) if nums[i+1] - nums[i] == 1)

    # Score de conformite
    score_conformite = 100
    if nb_pairs < 1 or nb_pairs > 4:
        score_conformite -= 15
    if nb_bas < 1 or nb_bas > 4:
        score_conformite -= 10
    if somme < 70 or somme > 150:
        score_conformite -= 20
    if dispersion < 15:
        score_conformite -= 25
    if consecutifs > 2:
        score_conformite -= 15

    # Score frequence
    freq_moyenne = sum(frequencies) / 5
    freq_attendue = total_tirages * 5 / 49
    score_freq = min(100, (freq_moyenne / freq_attendue) * 100)

    # Score final
    conformite_pct = int(0.6 * score_conformite + 0.4 * score_freq)
    conformite_pct = max(0, min(100, conformite_pct))

    # Badges
    badges = []
    if freq_moyenne > freq_attendue * 1.1:
        badges.append("Num\u00e9ros chauds")
    elif freq_moyenne < freq_attendue * 0.9:
        badges.append("Mix de retards")
    else:
        badges.append("\u00c9quilibre")
    if dispersion > 35:
        badges.append("Large spectre")
    if nb_pairs == 2 or nb_pairs == 3:
        badges.append("Pair/Impair OK")

    return {
        "numeros": nums,
        "chance": chance,
        "analyse": {
            "somme": somme,
            "somme_ok": 70 <= somme <= 150,
            "pairs": nb_pairs,
            "impairs": nb_impairs,
            "equilibre_pair_impair": 1 <= nb_pairs <= 4,
            "bas": nb_bas,
            "hauts": nb_hauts,
            "equilibre_bas_haut": 1 <= nb_bas <= 4,
            "dispersion": dispersion,
            "dispersion_ok": dispersion >= 15,
            "consecutifs": consecutifs,
            "numeros_chauds": numeros_chauds,
            "numeros_froids": numeros_froids,
            "numeros_neutres": numeros_neutres,
            "conformite_pct": conformite_pct,
            "badges": badges,
        },
        "historique": {
            "deja_sortie": len(exact_dates) > 0,
            "exact_dates": exact_dates,
            "meilleure_correspondance": {
                "nb_numeros_communs": best_match_count,
                "date": best_match_date,
                "numeros_communs": best_match_numbers,
            }
        }
    }


# =========================
# Phase 3 — Classements, comparaisons, categories
# =========================

_ALLOWED_TYPE_NUM = {"principal", "chance"}

def _get_all_frequencies(cursor, type_num="principal", date_from=None):
    """
    Calcule la frequence de TOUS les numeros en UNE seule requete SQL.
    Retourne un dict {numero: frequence}.
    """
    if type_num not in _ALLOWED_TYPE_NUM:
        raise ValueError(f"type_num invalide: {type_num}")

    if type_num == "principal":
        if date_from:
            date_filter = "WHERE date_de_tirage >= %s"
            params = [date_from] * 5
        else:
            date_filter = ""
            params = []
        cursor.execute(f"""
            SELECT num, COUNT(*) as freq FROM (
                SELECT boule_1 as num FROM tirages {date_filter}
                UNION ALL SELECT boule_2 FROM tirages {date_filter}
                UNION ALL SELECT boule_3 FROM tirages {date_filter}
                UNION ALL SELECT boule_4 FROM tirages {date_filter}
                UNION ALL SELECT boule_5 FROM tirages {date_filter}
            ) t
            GROUP BY num
            ORDER BY num
        """, params)
    else:
        if date_from:
            date_filter = "WHERE date_de_tirage >= %s"
            params = [date_from]
        else:
            date_filter = ""
            params = []
        cursor.execute(f"""
            SELECT numero_chance as num, COUNT(*) as freq
            FROM tirages {date_filter}
            GROUP BY numero_chance
            ORDER BY numero_chance
        """, params)
    return {row['num']: row['freq'] for row in cursor.fetchall()}


def _get_all_ecarts(cursor, type_num="principal"):
    """
    Calcule l'ecart actuel de TOUS les numeros en requetes optimisees.
    Retourne un dict {numero: ecart_actuel}.
    """
    # Date du dernier tirage
    cursor.execute("SELECT MAX(date_de_tirage) as last FROM tirages")
    last_draw = cursor.fetchone()['last']

    # Derniere apparition de chaque numero
    if type_num == "principal":
        cursor.execute("""
            SELECT num, MAX(date_de_tirage) as last_date FROM (
                SELECT boule_1 as num, date_de_tirage FROM tirages
                UNION ALL SELECT boule_2, date_de_tirage FROM tirages
                UNION ALL SELECT boule_3, date_de_tirage FROM tirages
                UNION ALL SELECT boule_4, date_de_tirage FROM tirages
                UNION ALL SELECT boule_5, date_de_tirage FROM tirages
            ) t
            GROUP BY num
        """)
    else:
        cursor.execute("""
            SELECT numero_chance as num, MAX(date_de_tirage) as last_date
            FROM tirages
            GROUP BY numero_chance
        """)
    last_dates = {row['num']: row['last_date'] for row in cursor.fetchall()}

    # Toutes les dates de tirages pour compter les ecarts
    cursor.execute("SELECT date_de_tirage FROM tirages ORDER BY date_de_tirage DESC")
    all_dates = [row['date_de_tirage'] for row in cursor.fetchall()]

    ecarts = {}
    num_range = range(1, 50) if type_num == "principal" else range(1, 11)
    for num in num_range:
        if num in last_dates and last_dates[num]:
            ecarts[num] = sum(1 for d in all_dates if d > last_dates[num])
        else:
            ecarts[num] = len(all_dates)

    return ecarts


def get_classement_numeros(type_num="principal", tri="frequence_desc", limit=5):
    """
    Retourne un classement de numeros selon le critere demande.

    Args:
        type_num: "principal" (1-49) ou "chance" (1-10)
        tri: "frequence_desc", "frequence_asc", "ecart_desc", "ecart_asc"
        limit: nombre de resultats (defaut 5)
    """
    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()

        # Total tirages et periode
        cursor.execute("""
            SELECT COUNT(*) as total,
                   MIN(date_de_tirage) as date_min,
                   MAX(date_de_tirage) as date_max
            FROM tirages
        """)
        info = cursor.fetchone()
        total = info['total']
        date_min = info['date_min']
        date_max = info['date_max']

        # Frequences (1 requete)
        freq_map = _get_all_frequencies(cursor, type_num)

        # Ecarts (2 requetes)
        ecart_map = _get_all_ecarts(cursor, type_num)

        # Categories chaud/froid (sur 2 ans)
        date_2ans = date_max - timedelta(days=730)
        freq_2ans = _get_all_frequencies(cursor, type_num, date_from=date_2ans)
    except Exception as e:
        logger.error(f"Erreur get_classement_numeros: {e}")
        return None
    finally:
        conn.close()

    freq_2ans_values = sorted(freq_2ans.values(), reverse=True)
    tiers = len(freq_2ans_values) // 3
    seuil_chaud = freq_2ans_values[tiers] if tiers < len(freq_2ans_values) else 0
    seuil_froid = freq_2ans_values[2 * tiers] if 2 * tiers < len(freq_2ans_values) else 0

    # Construire la liste
    num_range = range(1, 50) if type_num == "principal" else range(1, 11)
    items = []
    for num in num_range:
        f = freq_map.get(num, 0)
        e = ecart_map.get(num, 0)
        f2 = freq_2ans.get(num, 0)

        if f2 >= seuil_chaud:
            cat = "chaud"
        elif f2 <= seuil_froid:
            cat = "froid"
        else:
            cat = "neutre"

        items.append({
            "numero": num,
            "frequence": f,
            "ecart_actuel": e,
            "categorie": cat,
        })

    # Trier selon le critere
    if tri == "frequence_desc":
        items.sort(key=lambda x: (-x["frequence"], x["numero"]))
    elif tri == "frequence_asc":
        items.sort(key=lambda x: (x["frequence"], x["numero"]))
    elif tri == "ecart_desc":
        items.sort(key=lambda x: (-x["ecart_actuel"], x["numero"]))
    elif tri == "ecart_asc":
        items.sort(key=lambda x: (x["ecart_actuel"], x["numero"]))

    return {
        "items": items[:limit],
        "total_tirages": total,
        "periode": f"{date_min} au {date_max}" if date_min and date_max else "N/A",
    }


def get_comparaison_numeros(num1, num2, type_num="principal"):
    """
    Compare deux numeros cote a cote.
    Reutilise get_numero_stats() de Phase 1.
    """
    stats1 = get_numero_stats(num1, type_num)
    stats2 = get_numero_stats(num2, type_num)
    if not stats1 or not stats2:
        return None

    diff_freq = stats1["frequence_totale"] - stats2["frequence_totale"]

    return {
        "num1": stats1,
        "num2": stats2,
        "diff_frequence": diff_freq,
        "favori_frequence": num1 if diff_freq > 0 else num2 if diff_freq < 0 else None,
    }


def get_numeros_par_categorie(categorie, type_num="principal"):
    """
    Retourne la liste des numeros d'une categorie (chaud/froid/neutre).
    """
    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT MAX(date_de_tirage) as d FROM tirages")
        date_max = cursor.fetchone()['d']
        date_2ans = date_max - timedelta(days=730)

        freq_2ans = _get_all_frequencies(cursor, type_num, date_from=date_2ans)
    except Exception as e:
        logger.error(f"Erreur get_numeros_par_categorie: {e}")
        return None
    finally:
        conn.close()

    freq_values = sorted(freq_2ans.values(), reverse=True)
    tiers = len(freq_values) // 3
    seuil_chaud = freq_values[tiers] if tiers < len(freq_values) else 0
    seuil_froid = freq_values[2 * tiers] if 2 * tiers < len(freq_values) else 0

    result = []
    for num, f in sorted(freq_2ans.items()):
        if categorie == "chaud" and f >= seuil_chaud:
            result.append({"numero": num, "frequence_2ans": f})
        elif categorie == "froid" and f <= seuil_froid:
            result.append({"numero": num, "frequence_2ans": f})
        elif categorie == "neutre" and seuil_froid < f < seuil_chaud:
            result.append({"numero": num, "frequence_2ans": f})

    # Trier par frequence desc pour chaud, asc pour froid
    if categorie == "froid":
        result.sort(key=lambda x: x["frequence_2ans"])
    else:
        result.sort(key=lambda x: -x["frequence_2ans"])

    return {
        "categorie": categorie,
        "numeros": result,
        "count": len(result),
        "periode_analyse": "2 derni\u00e8res ann\u00e9es",
    }


# =========================
# Pitch grilles — contexte stats pour Gemini
# =========================

def prepare_grilles_pitch_context(grilles: list) -> str:
    """
    Prepare le contexte stats de N grilles pour le prompt Gemini pitch.
    Optimise : 1 seule connexion BDD, requetes UNION ALL.

    Args:
        grilles: [{"numeros": [15, 20, 25, 28, 45], "chance": 5}, ...]

    Returns:
        str: bloc de contexte formate pour Gemini
    """
    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()

        # Total tirages et periode
        cursor.execute("""
            SELECT COUNT(*) as total,
                   MIN(date_de_tirage) as date_min,
                   MAX(date_de_tirage) as date_max
            FROM tirages
        """)
        info = cursor.fetchone()
        total = info['total']
        date_max = info['date_max']

        # Frequences globales (1 requete UNION ALL)
        freq_map = _get_all_frequencies(cursor, "principal")

        # Ecarts (optimise)
        ecart_map = _get_all_ecarts(cursor, "principal")

        # Categories chaud/froid (sur 2 ans)
        date_2ans = date_max - timedelta(days=730)
        freq_2ans = _get_all_frequencies(cursor, "principal", date_from=date_2ans)

    except Exception as e:
        logger.error(f"Erreur prepare_grilles_pitch_context: {e}")
        return ""
    finally:
        conn.close()

    # Seuils
    freq_2ans_values = sorted(freq_2ans.values(), reverse=True)
    tiers = len(freq_2ans_values) // 3
    seuil_chaud = freq_2ans_values[tiers] if tiers < len(freq_2ans_values) else 0
    seuil_froid = freq_2ans_values[2 * tiers] if 2 * tiers < len(freq_2ans_values) else 0

    blocks = []
    for i, grille in enumerate(grilles, 1):
        nums = sorted(grille["numeros"])
        chance = grille.get("chance")

        # Metriques grille
        somme = sum(nums)
        nb_pairs = sum(1 for n in nums if n % 2 == 0)
        dispersion = max(nums) - min(nums)

        somme_ok = "\u2713" if 100 <= somme <= 140 else "\u2717"
        equil_ok = "\u2713" if 1 <= nb_pairs <= 4 else "\u2717"

        nums_str = " ".join(str(n) for n in nums)
        chance_str = f" + Chance {chance}" if chance else ""

        lines = [f"[GRILLE {i} \u2014 Num\u00e9ros : {nums_str}{chance_str}]"]
        lines.append(f"Somme : {somme} (id\u00e9al 100-140) {somme_ok}")
        lines.append(f"Pairs : {nb_pairs} / Impairs : {5 - nb_pairs} {equil_ok}")
        lines.append(f"Dispersion : {dispersion}")
        lines.append(f"Total tirages analys\u00e9s : {total}")

        # Stats par numero
        chauds = []
        froids = []
        for n in nums:
            f = freq_map.get(n, 0)
            e = ecart_map.get(n, 0)
            f2 = freq_2ans.get(n, 0)

            if f2 >= seuil_chaud:
                cat = "CHAUD"
                chauds.append(n)
            elif f2 <= seuil_froid:
                cat = "FROID"
                froids.append(n)
            else:
                cat = "NEUTRE"

            lines.append(f"Num\u00e9ro {n} : {f} sorties, \u00e9cart {e}, {cat}")

        # Badges
        badges = []
        if len(chauds) >= 3:
            badges.append("Num\u00e9ros chauds")
        elif len(froids) >= 3:
            badges.append("Mix de retards")
        else:
            badges.append("\u00c9quilibre")
        if 1 <= nb_pairs <= 4:
            badges.append("Pair/Impair OK")

        lines.append(f"Badges : {', '.join(badges)}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)
