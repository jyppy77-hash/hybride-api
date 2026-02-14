"""
Service metier — fonctions statistiques EuroMillions.
Cache TTL 1 h pour les requetes lourdes (frequences, ecarts, stats).
Cles cache prefixees em: pour eviter collision avec Loto.
"""

import logging
from datetime import timedelta

import db_cloudsql
from services.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────
# Constantes
# ────────────────────────────────────────────

TABLE = "tirages_euromillions"
_ALLOWED_TYPE_NUM = {"boule", "etoile"}

# ────────────────────────────────────────────
# Helpers BDD (avec cache)
# ────────────────────────────────────────────

def _get_all_frequencies(cursor, type_num="boule", date_from=None):
    """
    Calcule la frequence de TOUS les numeros en UNE seule requete SQL.
    Retourne un dict {numero: frequence}.
    Resultat mis en cache 1 h (sauf si date_from est fourni).
    """
    if type_num not in _ALLOWED_TYPE_NUM:
        raise ValueError(f"type_num invalide: {type_num}")

    cache_key = f"em:freq:{type_num}:{date_from}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    if type_num == "boule":
        if date_from:
            date_filter = "WHERE date_de_tirage >= %s"
            params = [date_from] * 5
        else:
            date_filter = ""
            params = []
        cursor.execute(f"""
            SELECT num, COUNT(*) as freq FROM (
                SELECT boule_1 as num FROM {TABLE} {date_filter}
                UNION ALL SELECT boule_2 FROM {TABLE} {date_filter}
                UNION ALL SELECT boule_3 FROM {TABLE} {date_filter}
                UNION ALL SELECT boule_4 FROM {TABLE} {date_filter}
                UNION ALL SELECT boule_5 FROM {TABLE} {date_filter}
            ) t
            GROUP BY num
            ORDER BY num
        """, params)
    else:
        # etoile : UNION ALL de etoile_1 et etoile_2
        if date_from:
            date_filter = "WHERE date_de_tirage >= %s"
            params = [date_from] * 2
        else:
            date_filter = ""
            params = []
        cursor.execute(f"""
            SELECT num, COUNT(*) as freq FROM (
                SELECT etoile_1 as num FROM {TABLE} {date_filter}
                UNION ALL SELECT etoile_2 FROM {TABLE} {date_filter}
            ) t
            GROUP BY num
            ORDER BY num
        """, params)

    result = {row['num']: row['freq'] for row in cursor.fetchall()}
    cache_set(cache_key, result)
    return result


def _get_all_ecarts(cursor, type_num="boule"):
    """
    Calcule l'ecart actuel de TOUS les numeros via SQL COUNT.
    Retourne un dict {numero: ecart_actuel}.
    Resultat mis en cache 1 h.
    """
    cache_key = f"em:ecarts:{type_num}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    cursor.execute(f"SELECT COUNT(*) as total FROM {TABLE}")
    total = cursor.fetchone()['total']

    if type_num == "boule":
        cursor.execute(f"""
            SELECT sub.num,
                   (SELECT COUNT(*) FROM {TABLE} WHERE date_de_tirage > sub.last_date) AS ecart
            FROM (
                SELECT num, MAX(date_de_tirage) as last_date FROM (
                    SELECT boule_1 as num, date_de_tirage FROM {TABLE}
                    UNION ALL SELECT boule_2, date_de_tirage FROM {TABLE}
                    UNION ALL SELECT boule_3, date_de_tirage FROM {TABLE}
                    UNION ALL SELECT boule_4, date_de_tirage FROM {TABLE}
                    UNION ALL SELECT boule_5, date_de_tirage FROM {TABLE}
                ) t
                GROUP BY num
            ) sub
        """)
    else:
        cursor.execute(f"""
            SELECT sub.num,
                   (SELECT COUNT(*) FROM {TABLE} WHERE date_de_tirage > sub.last_date) AS ecart
            FROM (
                SELECT num, MAX(date_de_tirage) as last_date FROM (
                    SELECT etoile_1 as num, date_de_tirage FROM {TABLE}
                    UNION ALL SELECT etoile_2, date_de_tirage FROM {TABLE}
                ) t
                GROUP BY num
            ) sub
        """)

    ecarts = {row['num']: row['ecart'] for row in cursor.fetchall()}

    num_range = range(1, 51) if type_num == "boule" else range(1, 13)
    for num in num_range:
        if num not in ecarts:
            ecarts[num] = total

    cache_set(cache_key, ecarts)
    return ecarts


# ────────────────────────────────────────────
# Fonctions metier
# ────────────────────────────────────────────

def get_numero_stats(numero: int, type_num: str = "boule") -> dict:
    """
    Calcule les statistiques completes d'un numero EM.

    Args:
        numero: le numero a analyser
        type_num: "boule" (1-50) ou "etoile" (1-12)

    Returns:
        dict avec toutes les stats ou None si erreur
    """
    if type_num == "boule" and not 1 <= numero <= 50:
        return None
    if type_num == "etoile" and not 1 <= numero <= 12:
        return None

    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(f"""
            SELECT COUNT(*) as total,
                   MIN(date_de_tirage) as date_min,
                   MAX(date_de_tirage) as date_max
            FROM {TABLE}
        """)
        info = cursor.fetchone()
        total_tirages = info['total']
        date_min = info['date_min']
        date_max = info['date_max']

        if type_num == "boule":
            cursor.execute(f"""
                SELECT date_de_tirage
                FROM {TABLE}
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
                ORDER BY date_de_tirage ASC
            """, (numero, numero, numero, numero, numero))
        else:
            cursor.execute(f"""
                SELECT date_de_tirage
                FROM {TABLE}
                WHERE etoile_1 = %s OR etoile_2 = %s
                ORDER BY date_de_tirage ASC
            """, (numero, numero))

        rows = cursor.fetchall()
        appearance_dates = [row['date_de_tirage'] for row in rows]
        frequence_totale = len(appearance_dates)

        derniere_sortie = appearance_dates[-1] if appearance_dates else None

        ecart_actuel = 0
        if derniere_sortie:
            cursor.execute(
                f"SELECT COUNT(*) as gap FROM {TABLE} WHERE date_de_tirage > %s",
                (derniere_sortie,)
            )
            ecart_actuel = cursor.fetchone()['gap']

        # Ecart moyen
        ecart_moyen = 0.0
        if len(appearance_dates) >= 2:
            cursor.execute(
                f"SELECT date_de_tirage FROM {TABLE} ORDER BY date_de_tirage ASC"
            )
            all_dates = [r['date_de_tirage'] for r in cursor.fetchall()]
            date_to_index = {d: i for i, d in enumerate(all_dates)}

            indices = [date_to_index[d] for d in appearance_dates if d in date_to_index]
            if len(indices) >= 2:
                gaps = [indices[i + 1] - indices[i] for i in range(len(indices) - 1)]
                ecart_moyen = round(sum(gaps) / len(gaps), 1)

        # Classement par frequence
        all_freq = _get_all_frequencies(cursor, type_num)
        classement = 1 + sum(1 for num, f in all_freq.items() if num != numero and f > frequence_totale)
        classement_sur = 50 if type_num == "boule" else 12

        # Categorie chaud/neutre/froid (sur 2 ans)
        date_2ans = date_max - timedelta(days=730)
        freq_2ans_map = _get_all_frequencies(cursor, type_num, date_from=date_2ans)
        freq_2ans = freq_2ans_map.get(numero, 0)
        all_freq_2ans = sorted(freq_2ans_map.values(), reverse=True)
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
        logger.error(f"Erreur get_numero_stats EM ({numero}, {type_num}): {e}")
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


def get_classement_numeros(type_num="boule", tri="frequence_desc", limit=5):
    """
    Retourne un classement de numeros selon le critere demande.

    Args:
        type_num: "boule" (1-50) ou "etoile" (1-12)
        tri: "frequence_desc", "frequence_asc", "ecart_desc", "ecart_asc"
        limit: nombre de resultats (defaut 5)
    """
    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(f"""
            SELECT COUNT(*) as total,
                   MIN(date_de_tirage) as date_min,
                   MAX(date_de_tirage) as date_max
            FROM {TABLE}
        """)
        info = cursor.fetchone()
        total = info['total']
        date_min = info['date_min']
        date_max = info['date_max']

        freq_map = _get_all_frequencies(cursor, type_num)
        ecart_map = _get_all_ecarts(cursor, type_num)

        date_2ans = date_max - timedelta(days=730)
        freq_2ans = _get_all_frequencies(cursor, type_num, date_from=date_2ans)
    except Exception as e:
        logger.error(f"Erreur get_classement_numeros EM: {e}")
        return None
    finally:
        conn.close()

    freq_2ans_values = sorted(freq_2ans.values(), reverse=True)
    tiers = len(freq_2ans_values) // 3
    seuil_chaud = freq_2ans_values[tiers] if tiers < len(freq_2ans_values) else 0
    seuil_froid = freq_2ans_values[2 * tiers] if 2 * tiers < len(freq_2ans_values) else 0

    num_range = range(1, 51) if type_num == "boule" else range(1, 13)
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


def get_comparaison_numeros(num1, num2, type_num="boule"):
    """Compare deux numeros cote a cote."""
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


def get_numeros_par_categorie(categorie, type_num="boule"):
    """Retourne la liste des numeros d'une categorie (chaud/froid/neutre)."""
    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT MAX(date_de_tirage) as d FROM {TABLE}")
        date_max = cursor.fetchone()['d']
        date_2ans = date_max - timedelta(days=730)
        freq_2ans = _get_all_frequencies(cursor, type_num, date_from=date_2ans)
    except Exception as e:
        logger.error(f"Erreur get_numeros_par_categorie EM: {e}")
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

    if categorie == "froid":
        result.sort(key=lambda x: x["frequence_2ans"])
    else:
        result.sort(key=lambda x: -x["frequence_2ans"])

    return {
        "categorie": categorie,
        "numeros": result,
        "count": len(result),
        "periode_analyse": "2 dernieres annees",
    }
