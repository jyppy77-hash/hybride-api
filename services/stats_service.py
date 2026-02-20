"""
Service metier — fonctions statistiques extraites de routes/api_data.py.
Cache TTL 1 h pour les requetes lourdes (frequences, ecarts, stats globales).
"""

import logging
from datetime import timedelta

import db_cloudsql
from services.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────
# Constantes
# ────────────────────────────────────────────

_ALLOWED_TYPE_NUM = {"principal", "chance"}

# ────────────────────────────────────────────
# Helpers BDD (avec cache)
# ────────────────────────────────────────────

def _get_all_frequencies(cursor, type_num="principal", date_from=None):
    """
    Calcule la frequence de TOUS les numeros en UNE seule requete SQL.
    Retourne un dict {numero: frequence}.
    Resultat mis en cache 1 h (sauf si date_from est fourni).
    """
    if type_num not in _ALLOWED_TYPE_NUM:
        raise ValueError(f"type_num invalide: {type_num}")

    cache_key = f"freq:{type_num}:{date_from}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

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

    result = {row['num']: row['freq'] for row in cursor.fetchall()}
    cache_set(cache_key, result)
    return result


def _get_all_ecarts(cursor, type_num="principal"):
    """
    Calcule l'ecart actuel de TOUS les numeros via SQL COUNT.
    Retourne un dict {numero: ecart_actuel}.
    Resultat mis en cache 1 h.
    """
    cache_key = f"ecarts:{type_num}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    # Total tirages (pour les numeros jamais apparus)
    cursor.execute("SELECT COUNT(*) as total FROM tirages")
    total = cursor.fetchone()['total']

    # Ecart = nombre de tirages apres la derniere apparition de chaque numero
    # Calcule entierement en SQL via COUNT + sous-requete
    if type_num == "principal":
        cursor.execute("""
            SELECT sub.num,
                   (SELECT COUNT(*) FROM tirages WHERE date_de_tirage > sub.last_date) AS ecart
            FROM (
                SELECT num, MAX(date_de_tirage) as last_date FROM (
                    SELECT boule_1 as num, date_de_tirage FROM tirages
                    UNION ALL SELECT boule_2, date_de_tirage FROM tirages
                    UNION ALL SELECT boule_3, date_de_tirage FROM tirages
                    UNION ALL SELECT boule_4, date_de_tirage FROM tirages
                    UNION ALL SELECT boule_5, date_de_tirage FROM tirages
                ) t
                GROUP BY num
            ) sub
        """)
    else:
        cursor.execute("""
            SELECT sub.num,
                   (SELECT COUNT(*) FROM tirages WHERE date_de_tirage > sub.last_date) AS ecart
            FROM (
                SELECT numero_chance as num, MAX(date_de_tirage) as last_date
                FROM tirages
                GROUP BY numero_chance
            ) sub
        """)
    ecarts = {row['num']: row['ecart'] for row in cursor.fetchall()}

    # Numeros jamais apparus → ecart = total tirages
    num_range = range(1, 50) if type_num == "principal" else range(1, 11)
    for num in num_range:
        if num not in ecarts:
            ecarts[num] = total

    cache_set(cache_key, ecarts)
    return ecarts


# ────────────────────────────────────────────
# Fonctions metier
# ────────────────────────────────────────────

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

        # Classement par frequence (1 requete UNION ALL au lieu de ~48)
        all_freq = _get_all_frequencies(cursor, type_num)
        classement = 1 + sum(1 for num, f in all_freq.items() if num != numero and f > frequence_totale)
        classement_sur = 49 if type_num == "principal" else 10

        # Categorie chaud/neutre/froid (sur 2 ans — 1 requete UNION ALL)
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

        # Frequences de chaque numero (1 requete UNION ALL au lieu de 49+5)
        freq_map = _get_all_frequencies(cursor, "principal")
        frequencies = [freq_map.get(num, 0) for num in nums]

        # Classification chaud/neutre/froid (seuils globaux)
        all_freq_sorted = sorted(freq_map.values(), reverse=True)
        seuil_chaud = all_freq_sorted[len(all_freq_sorted) // 3]
        seuil_froid = all_freq_sorted[2 * len(all_freq_sorted) // 3]

        num_freq_map = freq_map
        numeros_chauds = [n for n in nums if num_freq_map[n] >= seuil_chaud]
        numeros_froids = [n for n in nums if num_freq_map[n] <= seuil_froid]
        numeros_neutres = [n for n in nums if n not in numeros_chauds and n not in numeros_froids]

        # Verification historique — combinaison exacte
        # Utilise IN pour les boules (independant de l'ordre de stockage)
        if chance is not None:
            cursor.execute("""
                SELECT date_de_tirage FROM tirages
                WHERE boule_1 IN (%s, %s, %s, %s, %s)
                  AND boule_2 IN (%s, %s, %s, %s, %s)
                  AND boule_3 IN (%s, %s, %s, %s, %s)
                  AND boule_4 IN (%s, %s, %s, %s, %s)
                  AND boule_5 IN (%s, %s, %s, %s, %s)
                  AND numero_chance = %s
                ORDER BY date_de_tirage DESC
            """, (*nums, *nums, *nums, *nums, *nums, chance))
        else:
            cursor.execute("""
                SELECT date_de_tirage FROM tirages
                WHERE boule_1 IN (%s, %s, %s, %s, %s)
                  AND boule_2 IN (%s, %s, %s, %s, %s)
                  AND boule_3 IN (%s, %s, %s, %s, %s)
                  AND boule_4 IN (%s, %s, %s, %s, %s)
                  AND boule_5 IN (%s, %s, %s, %s, %s)
                ORDER BY date_de_tirage DESC
            """, (*nums, *nums, *nums, *nums, *nums))
        exact_matches = cursor.fetchall()
        exact_dates = [str(row['date_de_tirage']) for row in exact_matches]

        # Meilleure correspondance (alignee avec le simulateur)
        if chance is not None:
            cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance,
                    (
                        (boule_1 IN (%s, %s, %s, %s, %s)) +
                        (boule_2 IN (%s, %s, %s, %s, %s)) +
                        (boule_3 IN (%s, %s, %s, %s, %s)) +
                        (boule_4 IN (%s, %s, %s, %s, %s)) +
                        (boule_5 IN (%s, %s, %s, %s, %s))
                    ) AS match_count,
                    (numero_chance = %s) AS chance_match
                FROM tirages
                ORDER BY match_count DESC, chance_match DESC, date_de_tirage DESC
                LIMIT 1
            """, (*nums, *nums, *nums, *nums, *nums, chance))
        else:
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
                ORDER BY match_count DESC, date_de_tirage DESC
                LIMIT 1
            """, (*nums, *nums, *nums, *nums, *nums))
        best_match = cursor.fetchone()

        best_match_numbers = []
        best_match_count = 0
        best_match_date = None
        best_match_chance = False
        if best_match:
            # Cast int() pour garantir la coherence de type (BDD peut renvoyer str/Decimal)
            tirage_nums = [int(best_match['boule_1']), int(best_match['boule_2']),
                           int(best_match['boule_3']), int(best_match['boule_4']),
                           int(best_match['boule_5'])]
            best_match_numbers = sorted([n for n in nums if n in tirage_nums])
            best_match_count = len(best_match_numbers)
            best_match_date = str(best_match['date_de_tirage'])
            best_match_chance = bool(best_match.get('chance_match', 0))

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
                "chance_match": best_match_chance,
            }
        }
    }


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

        # Injecter score de conformite et severite en tete du bloc
        sc = grille.get("score_conformite")
        sev = grille.get("severity")
        if sc is not None or sev is not None:
            severity_lines = []
            if sc is not None:
                if sc < 20:
                    sc_label = "CRITIQUE"
                elif sc < 40:
                    sc_label = "FAIBLE"
                elif sc < 70:
                    sc_label = "MODERE"
                else:
                    sc_label = "BON"
                severity_lines.append(f"Score conformite : {sc}% ({sc_label})")
            if sev is not None:
                sev_labels = {1: "Bon", 2: "Modere", 3: "Alerte maximale"}
                severity_lines.append(f"Palier de severite : {sev}/3 - {sev_labels.get(sev, 'Inconnu')}")
            # Inserer en position 1 (apres le titre de la grille)
            for j, sl in enumerate(severity_lines):
                lines.insert(1 + j, sl)

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)
