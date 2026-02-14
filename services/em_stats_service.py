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


def analyze_grille_for_chat(nums: list, etoiles: list = None) -> dict:
    """
    Analyse complete d'une grille EM pour le chatbot HYBRIDE.

    Args:
        nums: liste de 5 numeros (1-50), uniques
        etoiles: liste de 0-2 etoiles (1-12), optionnel

    Returns:
        dict avec analyse complete ou None si erreur
    """
    nums = sorted(nums)
    etoiles = sorted(etoiles or [])

    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*) as total FROM {TABLE}")
        total_tirages = cursor.fetchone()['total']

        # Frequences boules
        freq_map = _get_all_frequencies(cursor, "boule")
        frequencies = [freq_map.get(num, 0) for num in nums]

        # Classification chaud/neutre/froid
        all_freq_sorted = sorted(freq_map.values(), reverse=True)
        seuil_chaud = all_freq_sorted[len(all_freq_sorted) // 3]
        seuil_froid = all_freq_sorted[2 * len(all_freq_sorted) // 3]

        numeros_chauds = [n for n in nums if freq_map.get(n, 0) >= seuil_chaud]
        numeros_froids = [n for n in nums if freq_map.get(n, 0) <= seuil_froid]
        numeros_neutres = [n for n in nums if n not in numeros_chauds and n not in numeros_froids]

        # Verification historique — combinaison exacte (boules uniquement)
        cursor.execute(f"""
            SELECT date_de_tirage FROM {TABLE}
            WHERE boule_1 = %s AND boule_2 = %s AND boule_3 = %s
                  AND boule_4 = %s AND boule_5 = %s
            ORDER BY date_de_tirage DESC
        """, tuple(nums))
        exact_matches = cursor.fetchall()
        exact_dates = [str(row['date_de_tirage']) for row in exact_matches]

        # Meilleure correspondance (boules)
        cursor.execute(f"""
            SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                   etoile_1, etoile_2,
                (
                    (boule_1 IN (%s, %s, %s, %s, %s)) +
                    (boule_2 IN (%s, %s, %s, %s, %s)) +
                    (boule_3 IN (%s, %s, %s, %s, %s)) +
                    (boule_4 IN (%s, %s, %s, %s, %s)) +
                    (boule_5 IN (%s, %s, %s, %s, %s))
                ) AS match_count
            FROM {TABLE}
            ORDER BY match_count DESC, date_de_tirage DESC
            LIMIT 1
        """, (*nums, *nums, *nums, *nums, *nums))
        best_match = cursor.fetchone()

        best_match_numbers = []
        best_match_count = 0
        best_match_date = None
        best_match_etoiles = False
        if best_match:
            tirage_nums = [best_match['boule_1'], best_match['boule_2'],
                           best_match['boule_3'], best_match['boule_4'],
                           best_match['boule_5']]
            best_match_numbers = sorted([n for n in nums if n in tirage_nums])
            best_match_count = best_match['match_count']
            best_match_date = str(best_match['date_de_tirage'])
            if etoiles:
                tirage_etoiles = {best_match['etoile_1'], best_match['etoile_2']}
                best_match_etoiles = bool(set(etoiles) & tirage_etoiles)

    except Exception as e:
        logger.error(f"Erreur analyze_grille_for_chat EM ({nums}): {e}")
        return None
    finally:
        conn.close()

    # Metriques de la grille
    nb_pairs = sum(1 for n in nums if n % 2 == 0)
    nb_impairs = 5 - nb_pairs
    nb_bas = sum(1 for n in nums if n <= 25)
    nb_hauts = 5 - nb_bas
    somme = sum(nums)
    dispersion = max(nums) - min(nums)
    consecutifs = sum(1 for i in range(4) if nums[i + 1] - nums[i] == 1)

    # Score de conformite
    score_conformite = 100
    if nb_pairs < 1 or nb_pairs > 4:
        score_conformite -= 15
    if nb_bas < 1 or nb_bas > 4:
        score_conformite -= 10
    if somme < 75 or somme > 175:
        score_conformite -= 20
    if dispersion < 15:
        score_conformite -= 25
    if consecutifs > 2:
        score_conformite -= 15

    # Score frequence
    freq_moyenne = sum(frequencies) / 5
    freq_attendue = total_tirages * 5 / 50
    score_freq = min(100, (freq_moyenne / freq_attendue) * 100) if freq_attendue else 50

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
        "etoiles": etoiles,
        "analyse": {
            "somme": somme,
            "somme_ok": 75 <= somme <= 175,
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
                "etoiles_match": best_match_etoiles,
            }
        }
    }


def prepare_grilles_pitch_context(grilles: list) -> str:
    """
    Prepare le contexte stats de N grilles EM pour le prompt Gemini pitch.

    Args:
        grilles: [{"numeros": [5, 20, 25, 38, 45], "etoiles": [3, 9]}, ...]

    Returns:
        str: bloc de contexte formate pour Gemini
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
        date_max = info['date_max']

        freq_map = _get_all_frequencies(cursor, "boule")
        ecart_map = _get_all_ecarts(cursor, "boule")

        date_2ans = date_max - timedelta(days=730)
        freq_2ans = _get_all_frequencies(cursor, "boule", date_from=date_2ans)

    except Exception as e:
        logger.error(f"Erreur prepare_grilles_pitch_context EM: {e}")
        return ""
    finally:
        conn.close()

    freq_2ans_values = sorted(freq_2ans.values(), reverse=True)
    tiers = len(freq_2ans_values) // 3
    seuil_chaud = freq_2ans_values[tiers] if tiers < len(freq_2ans_values) else 0
    seuil_froid = freq_2ans_values[2 * tiers] if 2 * tiers < len(freq_2ans_values) else 0

    blocks = []
    for i, grille in enumerate(grilles, 1):
        nums = sorted(grille["numeros"])
        etoiles = sorted(grille.get("etoiles") or [])

        somme = sum(nums)
        nb_pairs = sum(1 for n in nums if n % 2 == 0)
        dispersion = max(nums) - min(nums)

        somme_ok = "\u2713" if 75 <= somme <= 175 else "\u2717"
        equil_ok = "\u2713" if 1 <= nb_pairs <= 4 else "\u2717"

        nums_str = " ".join(str(n) for n in nums)
        etoiles_str = f" + \u00c9toiles {' '.join(str(e) for e in etoiles)}" if etoiles else ""

        lines = [f"[GRILLE {i} \u2014 Num\u00e9ros : {nums_str}{etoiles_str}]"]
        lines.append(f"Somme : {somme} (id\u00e9al 75-175) {somme_ok}")
        lines.append(f"Pairs : {nb_pairs} / Impairs : {5 - nb_pairs} {equil_ok}")
        lines.append(f"Dispersion : {dispersion}")
        lines.append(f"Total tirages analys\u00e9s : {total}")

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
            for j, sl in enumerate(severity_lines):
                lines.insert(1 + j, sl)

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)
