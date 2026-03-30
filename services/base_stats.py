"""
Base class for game statistics services (Loto, EuroMillions).
Config-driven methods + overridable hooks for game-specific SQL.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from services.cache import cache_get, cache_set
from config.i18n import _badges

logger = logging.getLogger(__name__)


@dataclass
class GameConfig:
    """Configuration for a lottery game's statistics service."""
    table: str                   # "tirages" | "tirages_euromillions"
    type_principal: str          # "principal" | "boule"
    type_secondary: str          # "chance" | "etoile"
    range_principal: tuple       # (1, 49) | (1, 50)
    range_secondary: tuple       # (1, 10) | (1, 12)
    secondary_columns: list      # ["numero_chance"] | ["etoile_1", "etoile_2"]
    cache_prefix: str            # "" | "em:"
    log_label: str               # "" | " EM"
    mid_threshold: int           # 24 | 25
    somme_range: tuple           # (70, 150) | (75, 175) — conformity scoring
    somme_pitch_range: tuple     # (100, 140) | (75, 175) — pitch display
    freq_divisor: int            # 49 | 50
    secondary_key: str           # "chance" | "etoiles"
    secondary_match_key: str     # "chance_match" | "etoiles_match"
    secondary_label: str         # "Chance" | "Étoiles"


class BaseStatsService:
    """Config-driven statistics service. Subclass for game-specific SQL hooks."""

    def __init__(self, cfg: GameConfig):
        self.cfg = cfg
        self._allowed_types = {cfg.type_principal, cfg.type_secondary}

    # ──────────────────────────────────────
    # Abstract: subclass MUST override
    # ──────────────────────────────────────

    async def _get_connection(self):
        """Return an async context manager for DB connection. Override in subclass."""
        raise NotImplementedError

    # ──────────────────────────────────────
    # Hooks: override for game-specific SQL
    # ──────────────────────────────────────

    async def _query_exact_matches(self, cursor, nums, secondary):
        """Query exact historical matches (boules only, no secondary filter)."""
        await cursor.execute(f"""
            SELECT date_de_tirage FROM {self.cfg.table}
            WHERE boule_1 IN (%s, %s, %s, %s, %s)
              AND boule_2 IN (%s, %s, %s, %s, %s)
              AND boule_3 IN (%s, %s, %s, %s, %s)
              AND boule_4 IN (%s, %s, %s, %s, %s)
              AND boule_5 IN (%s, %s, %s, %s, %s)
            ORDER BY date_de_tirage DESC
        """, (*nums, *nums, *nums, *nums, *nums))
        return await cursor.fetchall()

    async def _query_best_match(self, cursor, nums, secondary):
        """Query best historical match. Default: boules only."""
        await cursor.execute(f"""
            SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                (
                    (boule_1 IN (%s, %s, %s, %s, %s)) +
                    (boule_2 IN (%s, %s, %s, %s, %s)) +
                    (boule_3 IN (%s, %s, %s, %s, %s)) +
                    (boule_4 IN (%s, %s, %s, %s, %s)) +
                    (boule_5 IN (%s, %s, %s, %s, %s))
                ) AS match_count
            FROM {self.cfg.table}
            ORDER BY match_count DESC, date_de_tirage DESC
            LIMIT 1
        """, (*nums, *nums, *nums, *nums, *nums))
        return await cursor.fetchone()

    def _extract_secondary_match(self, best_match, secondary):
        """Extract secondary number match from best_match row. Default: False."""
        return False

    # ──────────────────────────────────────
    # Helpers BDD (avec cache)
    # ──────────────────────────────────────

    async def _get_all_frequencies(self, cursor, type_num=None, date_from=None):
        """
        Calcule la frequence de TOUS les numeros en UNE seule requete SQL.
        Retourne un dict {numero: frequence}.
        Resultat mis en cache 1 h (sauf si date_from est fourni).
        """
        if type_num is None:
            type_num = self.cfg.type_principal
        if type_num not in self._allowed_types:
            raise ValueError(f"type_num invalide: {type_num}")

        cache_key = f"{self.cfg.cache_prefix}freq:{type_num}:{date_from}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        if type_num == self.cfg.type_principal:
            if date_from:
                date_filter = "WHERE date_de_tirage >= %s"
                params = [date_from] * 5
            else:
                date_filter = ""
                params = []
            await cursor.execute(f"""
                SELECT num, COUNT(*) as freq FROM (
                    SELECT boule_1 as num FROM {self.cfg.table} {date_filter}
                    UNION ALL SELECT boule_2 FROM {self.cfg.table} {date_filter}
                    UNION ALL SELECT boule_3 FROM {self.cfg.table} {date_filter}
                    UNION ALL SELECT boule_4 FROM {self.cfg.table} {date_filter}
                    UNION ALL SELECT boule_5 FROM {self.cfg.table} {date_filter}
                ) t
                GROUP BY num
                ORDER BY num
            """, params)
        else:
            cols = self.cfg.secondary_columns
            if len(cols) == 1:
                col = cols[0]
                if date_from:
                    await cursor.execute(f"""
                        SELECT {col} as num, COUNT(*) as freq
                        FROM {self.cfg.table} WHERE date_de_tirage >= %s
                        GROUP BY {col} ORDER BY {col}
                    """, [date_from])
                else:
                    await cursor.execute(f"""
                        SELECT {col} as num, COUNT(*) as freq
                        FROM {self.cfg.table}
                        GROUP BY {col} ORDER BY {col}
                    """)
            else:
                unions = []
                params = []
                for col in cols:
                    if date_from:
                        unions.append(
                            f"SELECT {col} as num FROM {self.cfg.table} WHERE date_de_tirage >= %s"
                        )
                        params.append(date_from)
                    else:
                        unions.append(f"SELECT {col} as num FROM {self.cfg.table}")
                await cursor.execute(f"""
                    SELECT num, COUNT(*) as freq FROM (
                        {' UNION ALL '.join(unions)}
                    ) t
                    GROUP BY num
                    ORDER BY num
                """, params)

        result = {row['num']: row['freq'] for row in await cursor.fetchall()}
        await cache_set(cache_key, result)
        return result

    async def _get_all_ecarts(self, cursor, type_num=None):
        """
        Calcule l'ecart actuel de TOUS les numeros via SQL COUNT.
        Retourne un dict {numero: ecart_actuel}.
        Resultat mis en cache 1 h.
        """
        if type_num is None:
            type_num = self.cfg.type_principal

        cache_key = f"{self.cfg.cache_prefix}ecarts:{type_num}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        await cursor.execute(f"SELECT COUNT(*) as total FROM {self.cfg.table}")
        total = (await cursor.fetchone())['total']

        if type_num == self.cfg.type_principal:
            await cursor.execute(f"""
                SELECT sub.num,
                       (SELECT COUNT(*) FROM {self.cfg.table}
                        WHERE date_de_tirage > sub.last_date) AS ecart
                FROM (
                    SELECT num, MAX(date_de_tirage) as last_date FROM (
                        SELECT boule_1 as num, date_de_tirage FROM {self.cfg.table}
                        UNION ALL SELECT boule_2, date_de_tirage FROM {self.cfg.table}
                        UNION ALL SELECT boule_3, date_de_tirage FROM {self.cfg.table}
                        UNION ALL SELECT boule_4, date_de_tirage FROM {self.cfg.table}
                        UNION ALL SELECT boule_5, date_de_tirage FROM {self.cfg.table}
                    ) t
                    GROUP BY num
                ) sub
            """)
        else:
            cols = self.cfg.secondary_columns
            if len(cols) == 1:
                col = cols[0]
                await cursor.execute(f"""
                    SELECT sub.num,
                           (SELECT COUNT(*) FROM {self.cfg.table}
                            WHERE date_de_tirage > sub.last_date) AS ecart
                    FROM (
                        SELECT {col} as num, MAX(date_de_tirage) as last_date
                        FROM {self.cfg.table}
                        GROUP BY {col}
                    ) sub
                """)
            else:
                unions = [
                    f"SELECT {col} as num, date_de_tirage FROM {self.cfg.table}"
                    for col in cols
                ]
                await cursor.execute(f"""
                    SELECT sub.num,
                           (SELECT COUNT(*) FROM {self.cfg.table}
                            WHERE date_de_tirage > sub.last_date) AS ecart
                    FROM (
                        SELECT num, MAX(date_de_tirage) as last_date FROM (
                            {' UNION ALL '.join(unions)}
                        ) t
                        GROUP BY num
                    ) sub
                """)

        ecarts = {row['num']: row['ecart'] for row in await cursor.fetchall()}

        r_min, r_max = (self.cfg.range_principal if type_num == self.cfg.type_principal
                        else self.cfg.range_secondary)
        for num in range(r_min, r_max + 1):
            if num not in ecarts:
                ecarts[num] = total

        await cache_set(cache_key, ecarts)
        return ecarts

    # ──────────────────────────────────────
    # Fonctions metier
    # ──────────────────────────────────────

    async def get_numero_stats(self, numero: int, type_num: str = None) -> dict:
        """
        Calcule les statistiques completes d'un numero.

        Args:
            numero: le numero a analyser
            type_num: type de numero (principal/chance ou boule/etoile)

        Returns:
            dict avec toutes les stats ou None si erreur
        """
        if type_num is None:
            type_num = self.cfg.type_principal

        r_min, r_max = (self.cfg.range_principal if type_num == self.cfg.type_principal
                        else self.cfg.range_secondary)
        if not r_min <= numero <= r_max:
            return None

        async with self._get_connection() as conn:
          try:
            cursor = await conn.cursor()

            await cursor.execute(f"""
                SELECT COUNT(*) as total,
                       MIN(date_de_tirage) as date_min,
                       MAX(date_de_tirage) as date_max
                FROM {self.cfg.table}
            """)
            info = await cursor.fetchone()
            total_tirages = info['total']
            date_min = info['date_min']
            date_max = info['date_max']

            if type_num == self.cfg.type_principal:
                await cursor.execute(f"""
                    SELECT date_de_tirage
                    FROM {self.cfg.table}
                    WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                       OR boule_4 = %s OR boule_5 = %s
                    ORDER BY date_de_tirage ASC
                """, (numero, numero, numero, numero, numero))
            else:
                conditions = [f"{col} = %s" for col in self.cfg.secondary_columns]
                params = [numero] * len(self.cfg.secondary_columns)
                await cursor.execute(f"""
                    SELECT date_de_tirage
                    FROM {self.cfg.table}
                    WHERE {' OR '.join(conditions)}
                    ORDER BY date_de_tirage ASC
                """, params)

            rows = await cursor.fetchall()
            appearance_dates = [row['date_de_tirage'] for row in rows]
            frequence_totale = len(appearance_dates)

            derniere_sortie = appearance_dates[-1] if appearance_dates else None

            ecart_actuel = 0
            if derniere_sortie:
                await cursor.execute(
                    f"SELECT COUNT(*) as gap FROM {self.cfg.table} WHERE date_de_tirage > %s",
                    (derniere_sortie,)
                )
                ecart_actuel = (await cursor.fetchone())['gap']

            ecart_moyen = 0.0
            if len(appearance_dates) >= 2:
                await cursor.execute(
                    f"SELECT date_de_tirage FROM {self.cfg.table} ORDER BY date_de_tirage ASC"
                )
                all_dates = [r['date_de_tirage'] for r in await cursor.fetchall()]
                date_to_index = {d: i for i, d in enumerate(all_dates)}

                indices = [date_to_index[d] for d in appearance_dates if d in date_to_index]
                if len(indices) >= 2:
                    gaps = [indices[i+1] - indices[i] for i in range(len(indices) - 1)]
                    ecart_moyen = round(sum(gaps) / len(gaps), 1)

            all_freq = await self._get_all_frequencies(cursor, type_num)
            classement = 1 + sum(
                1 for num, f in all_freq.items() if num != numero and f > frequence_totale
            )
            classement_sur = r_max

            date_2ans = date_max - timedelta(days=730)
            freq_2ans_map = await self._get_all_frequencies(cursor, type_num, date_from=date_2ans)
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
            logger.error(f"Erreur get_numero_stats{self.cfg.log_label} ({numero}, {type_num}): {e}")
            return None

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

    async def analyze_grille_for_chat(self, nums: list, secondary=None, lang: str = "fr") -> dict:
        """
        Analyse complete d'une grille pour le chatbot HYBRIDE.

        Args:
            nums: liste de 5 numeros principaux
            secondary: numero chance (int) ou etoiles (list), selon le jeu

        Returns:
            dict avec analyse complete ou None si erreur
        """
        nums = sorted(nums)

        async with self._get_connection() as conn:
          try:
            cursor = await conn.cursor()

            await cursor.execute(f"SELECT COUNT(*) as total FROM {self.cfg.table}")
            total_tirages = (await cursor.fetchone())['total']

            freq_map = await self._get_all_frequencies(cursor, self.cfg.type_principal)
            frequencies = [freq_map.get(num, 0) for num in nums]

            all_freq_sorted = sorted(freq_map.values(), reverse=True)
            seuil_chaud = all_freq_sorted[len(all_freq_sorted) // 3]
            seuil_froid = all_freq_sorted[2 * len(all_freq_sorted) // 3]

            numeros_chauds = [n for n in nums if freq_map.get(n, 0) >= seuil_chaud]
            numeros_froids = [n for n in nums if freq_map.get(n, 0) <= seuil_froid]
            numeros_neutres = [n for n in nums if n not in numeros_chauds and n not in numeros_froids]

            exact_matches = await self._query_exact_matches(cursor, nums, secondary)
            exact_dates = [str(row['date_de_tirage']) for row in exact_matches]

            best_match = await self._query_best_match(cursor, nums, secondary)

            best_match_numbers = []
            best_match_count = 0
            best_match_date = None
            best_match_secondary = False
            if best_match:
                tirage_nums = [int(best_match['boule_1']), int(best_match['boule_2']),
                               int(best_match['boule_3']), int(best_match['boule_4']),
                               int(best_match['boule_5'])]
                best_match_numbers = sorted([n for n in nums if n in tirage_nums])
                best_match_count = len(best_match_numbers)
                best_match_date = str(best_match['date_de_tirage'])
                best_match_secondary = self._extract_secondary_match(best_match, secondary)

          except Exception as e:
            logger.error(f"Erreur analyze_grille_for_chat{self.cfg.log_label} ({nums}): {e}")
            return None

        # Metriques de la grille
        nb_pairs = sum(1 for n in nums if n % 2 == 0)
        nb_impairs = 5 - nb_pairs
        nb_bas = sum(1 for n in nums if n <= self.cfg.mid_threshold)
        nb_hauts = 5 - nb_bas
        somme = sum(nums)
        dispersion = max(nums) - min(nums)
        consecutifs = sum(1 for i in range(4) if nums[i+1] - nums[i] == 1)

        # Score de conformite
        somme_min, somme_max = self.cfg.somme_range
        score_conformite = 100
        if nb_pairs < 1 or nb_pairs > 4:
            score_conformite -= 15
        if nb_bas < 1 or nb_bas > 4:
            score_conformite -= 10
        if somme < somme_min or somme > somme_max:
            score_conformite -= 20
        if dispersion < 15:
            score_conformite -= 25
        if consecutifs > 2:
            score_conformite -= 15

        # Score frequence
        freq_moyenne = sum(frequencies) / 5
        freq_attendue = total_tirages * 5 / self.cfg.freq_divisor
        score_freq = min(100, (freq_moyenne / freq_attendue) * 100) if freq_attendue else 50

        # Score final
        conformite_pct = int(0.6 * score_conformite + 0.4 * score_freq)
        conformite_pct = max(0, min(100, conformite_pct))

        # Badges
        b = _badges(lang)
        badges = []
        if freq_moyenne > freq_attendue * 1.1:
            badges.append(b["hot"])
        elif freq_moyenne < freq_attendue * 0.9:
            badges.append(b["overdue"])
        else:
            badges.append(b["balanced"])
        if dispersion > 35:
            badges.append(b["wide_spectrum"])
        if nb_pairs == 2 or nb_pairs == 3:
            badges.append(b["even_odd"])

        result = {
            "numeros": nums,
            self.cfg.secondary_key: secondary,
            "analyse": {
                "somme": somme,
                "somme_ok": somme_min <= somme <= somme_max,
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
                    self.cfg.secondary_match_key: best_match_secondary,
                }
            }
        }
        return result

    async def get_classement_numeros(self, type_num=None, tri="frequence_desc", limit=5):
        """
        Retourne un classement de numeros selon le critere demande.

        Args:
            type_num: type de numero (principal/chance ou boule/etoile)
            tri: "frequence_desc", "frequence_asc", "ecart_desc", "ecart_asc"
            limit: nombre de resultats (defaut 5)
        """
        if type_num is None:
            type_num = self.cfg.type_principal

        async with self._get_connection() as conn:
          try:
            cursor = await conn.cursor()

            await cursor.execute(f"""
                SELECT COUNT(*) as total,
                       MIN(date_de_tirage) as date_min,
                       MAX(date_de_tirage) as date_max
                FROM {self.cfg.table}
            """)
            info = await cursor.fetchone()
            total = info['total']
            date_min = info['date_min']
            date_max = info['date_max']

            freq_map = await self._get_all_frequencies(cursor, type_num)
            ecart_map = await self._get_all_ecarts(cursor, type_num)

            date_2ans = date_max - timedelta(days=730)
            freq_2ans = await self._get_all_frequencies(cursor, type_num, date_from=date_2ans)
          except Exception as e:
            logger.error(f"Erreur get_classement_numeros{self.cfg.log_label}: {e}")
            return None

        freq_2ans_values = sorted(freq_2ans.values(), reverse=True)
        tiers = len(freq_2ans_values) // 3
        seuil_chaud = freq_2ans_values[tiers] if tiers < len(freq_2ans_values) else 0
        seuil_froid = freq_2ans_values[2 * tiers] if 2 * tiers < len(freq_2ans_values) else 0

        r_min, r_max = (self.cfg.range_principal if type_num == self.cfg.type_principal
                        else self.cfg.range_secondary)
        items = []
        for num in range(r_min, r_max + 1):
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

    async def get_comparaison_numeros(self, num1, num2, type_num=None):
        """Compare deux numeros cote a cote."""
        if type_num is None:
            type_num = self.cfg.type_principal

        stats1 = await self.get_numero_stats(num1, type_num)
        stats2 = await self.get_numero_stats(num2, type_num)
        if not stats1 or not stats2:
            return None

        diff_freq = stats1["frequence_totale"] - stats2["frequence_totale"]

        return {
            "num1": stats1,
            "num2": stats2,
            "diff_frequence": diff_freq,
            "favori_frequence": num1 if diff_freq > 0 else num2 if diff_freq < 0 else None,
        }

    async def get_comparaison_with_period(self, num1, num2, type_num=None, date_from=None):
        """Compare deux numeros avec progression temporelle optionnelle.

        Si date_from est fourni, calcule en plus :
        - frequence de chaque numero sur la periode
        - frequence attendue (extrapolee depuis l'historique complet)
        - pourcentage de progression
        """
        if type_num is None:
            type_num = self.cfg.type_principal

        stats1 = await self.get_numero_stats(num1, type_num)
        stats2 = await self.get_numero_stats(num2, type_num)
        if not stats1 or not stats2:
            return None

        diff_freq = stats1["frequence_totale"] - stats2["frequence_totale"]
        result = {
            "num1": stats1,
            "num2": stats2,
            "diff_frequence": diff_freq,
            "favori_frequence": num1 if diff_freq > 0 else num2 if diff_freq < 0 else None,
        }

        if date_from:
            async with self._get_connection() as conn:
              try:
                cursor = await conn.cursor()

                freq_map = await self._get_all_frequencies(cursor, type_num, date_from=date_from)

                await cursor.execute(
                    f"SELECT COUNT(*) as total FROM {self.cfg.table} WHERE date_de_tirage >= %s",
                    (date_from,)
                )
                total_period = (await cursor.fetchone())['total']

                freq1_period = freq_map.get(num1, 0)
                freq2_period = freq_map.get(num2, 0)

                total_all = stats1["total_tirages"]
                freq1_all = stats1["frequence_totale"]
                freq2_all = stats2["frequence_totale"]

                if total_all > 0 and total_period > 0:
                    expected1 = freq1_all * total_period / total_all
                    expected2 = freq2_all * total_period / total_all
                    prog1 = round((freq1_period / expected1 - 1) * 100, 1) if expected1 > 0 else 0.0
                    prog2 = round((freq2_period / expected2 - 1) * 100, 1) if expected2 > 0 else 0.0
                else:
                    expected1 = expected2 = prog1 = prog2 = 0.0

                result["period"] = {
                    "date_from": str(date_from),
                    "total_tirages_period": total_period,
                    "num1_freq_period": freq1_period,
                    "num2_freq_period": freq2_period,
                    "num1_expected": round(expected1, 1),
                    "num2_expected": round(expected2, 1),
                    "num1_progression_pct": prog1,
                    "num2_progression_pct": prog2,
                    "plus_progresse": num1 if prog1 > prog2 else num2 if prog2 > prog1 else None,
                }
              except Exception as e:
                logger.error(f"Erreur comparaison period{self.cfg.log_label}: {e}")

        return result

    async def get_numeros_par_categorie(self, categorie, type_num=None):
        """Retourne la liste des numeros d'une categorie (chaud/froid/neutre)."""
        if type_num is None:
            type_num = self.cfg.type_principal

        async with self._get_connection() as conn:
          try:
            cursor = await conn.cursor()
            await cursor.execute(f"SELECT MAX(date_de_tirage) as d FROM {self.cfg.table}")
            date_max = (await cursor.fetchone())['d']
            date_2ans = date_max - timedelta(days=730)
            freq_2ans = await self._get_all_frequencies(cursor, type_num, date_from=date_2ans)
          except Exception as e:
            logger.error(f"Erreur get_numeros_par_categorie{self.cfg.log_label}: {e}")
            return None

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
            "periode_analyse": "2 derni\u00e8res ann\u00e9es",
        }

    async def prepare_grilles_pitch_context(self, grilles: list, lang: str = "fr") -> str:
        """
        Prepare le contexte stats de N grilles pour le prompt Gemini pitch.
        Optimise : 1 seule connexion BDD, requetes UNION ALL.

        Args:
            grilles: [{"numeros": [...], "chance": N} | {"numeros": [...], "etoiles": [...]}]

        Returns:
            str: bloc de contexte formate pour Gemini
        """
        async with self._get_connection() as conn:
          try:
            cursor = await conn.cursor()

            await cursor.execute(f"""
                SELECT COUNT(*) as total,
                       MIN(date_de_tirage) as date_min,
                       MAX(date_de_tirage) as date_max
                FROM {self.cfg.table}
            """)
            info = await cursor.fetchone()
            total = info['total']
            date_max = info['date_max']

            freq_map = await self._get_all_frequencies(cursor, self.cfg.type_principal)
            ecart_map = await self._get_all_ecarts(cursor, self.cfg.type_principal)

            date_2ans = date_max - timedelta(days=730)
            freq_2ans = await self._get_all_frequencies(
                cursor, self.cfg.type_principal, date_from=date_2ans
            )

          except Exception as e:
            logger.error(f"Erreur prepare_grilles_pitch_context{self.cfg.log_label}: {e}")
            return ""

        # Seuils
        freq_2ans_values = sorted(freq_2ans.values(), reverse=True)
        tiers = len(freq_2ans_values) // 3
        seuil_chaud = freq_2ans_values[tiers] if tiers < len(freq_2ans_values) else 0
        seuil_froid = freq_2ans_values[2 * tiers] if 2 * tiers < len(freq_2ans_values) else 0

        pitch_min, pitch_max = self.cfg.somme_pitch_range

        blocks = []
        for i, grille in enumerate(grilles, 1):
            nums = sorted(grille["numeros"])
            sec_val = grille.get(self.cfg.secondary_key)

            # Format secondary label
            if sec_val is not None:
                if isinstance(sec_val, list):
                    sec_str = (
                        f" + {self.cfg.secondary_label} "
                        f"{' '.join(str(e) for e in sorted(sec_val))}"
                    )
                else:
                    sec_str = f" + {self.cfg.secondary_label} {sec_val}"
            else:
                sec_str = ""

            somme = sum(nums)
            nb_pairs = sum(1 for n in nums if n % 2 == 0)
            dispersion = max(nums) - min(nums)

            somme_ok = "\u2713" if pitch_min <= somme <= pitch_max else "\u2717"
            equil_ok = "\u2713" if 1 <= nb_pairs <= 4 else "\u2717"

            nums_str = " ".join(str(n) for n in nums)

            lines = [f"[GRILLE {i} \u2014 Num\u00e9ros : {nums_str}{sec_str}]"]
            lines.append(f"Somme : {somme} (id\u00e9al {pitch_min}-{pitch_max}) {somme_ok}")
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
            b = _badges(lang)
            badges = []
            if len(chauds) >= 3:
                badges.append(b["hot"])
            elif len(froids) >= 3:
                badges.append(b["overdue"])
            else:
                badges.append(b["balanced"])
            if 1 <= nb_pairs <= 4:
                badges.append(b["even_odd"])

            lines.append(f"Badges : {', '.join(badges)}")

            # Score de conformite et severite (optionnel, inject par caller)
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
                        sc_label = "MOD\u00c9R\u00c9"
                    else:
                        sc_label = "BON"
                    severity_lines.append(f"Score conformit\u00e9 : {sc}% ({sc_label})")
                if sev is not None:
                    sev_labels = {1: "Bon", 2: "Mod\u00e9r\u00e9", 3: "Alerte maximale"}
                    severity_lines.append(
                        f"Palier de s\u00e9v\u00e9rit\u00e9 : {sev}/3 - {sev_labels.get(sev, 'Inconnu')}"
                    )
                for j, sl in enumerate(severity_lines):
                    lines.insert(1 + j, sl)

            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    # ──────────────────────────────────────
    # Corrélations de paires
    # ──────────────────────────────────────

    async def get_pair_correlations(self, *, top_n=10, window=None, order="hot"):
        """
        Top paires de boules co-occurrentes (C(5,2)=10 paires par tirage).
        window: "2A","5A" etc. = filtre date en annees, None = global.
        order: "hot" (DESC, most frequent) or "cold" (ASC, least frequent).
        Cache: {prefix}pairs:{window}:{top_n}:{order}, TTL 1h.
        Retour: dict(pairs=[{num_a, num_b, count, percentage, rank}], total_draws, window)
        """
        cache_key = f"{self.cfg.cache_prefix}pairs:{window}:{top_n}:{order}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        async with self._get_connection() as conn:
          try:
            cursor = await conn.cursor()

            # Build optional date filter
            if window:
                years = int(window.replace("A", ""))
                await cursor.execute(
                    f"SELECT MAX(date_de_tirage) as d FROM {self.cfg.table}"
                )
                date_max = (await cursor.fetchone())['d']
                from datetime import timedelta
                date_from = date_max - timedelta(days=365 * years)
                date_filter = "WHERE date_de_tirage >= %s"
                params_per_union = [date_from]
            else:
                date_filter = ""
                params_per_union = []

            # Count total draws in window
            if date_filter:
                await cursor.execute(
                    f"SELECT COUNT(*) as total FROM {self.cfg.table} {date_filter}",
                    params_per_union,
                )
            else:
                await cursor.execute(
                    f"SELECT COUNT(*) as total FROM {self.cfg.table}"
                )
            total_draws = (await cursor.fetchone())['total']

            if total_draws == 0:
                result = {"pairs": [], "total_draws": 0, "window": window}
                await cache_set(cache_key, result)
                return result

            # 10 UNION ALL for C(5,2) pairs
            pair_cols = [
                ("boule_1", "boule_2"), ("boule_1", "boule_3"),
                ("boule_1", "boule_4"), ("boule_1", "boule_5"),
                ("boule_2", "boule_3"), ("boule_2", "boule_4"),
                ("boule_2", "boule_5"), ("boule_3", "boule_4"),
                ("boule_3", "boule_5"), ("boule_4", "boule_5"),
            ]
            unions = []
            all_params = []
            for a, b in pair_cols:
                unions.append(
                    f"SELECT LEAST({a}, {b}) AS num_a, "
                    f"GREATEST({a}, {b}) AS num_b "
                    f"FROM {self.cfg.table} {date_filter}"
                )
                all_params.extend(params_per_union)

            sort_dir = "ASC" if order == "cold" else "DESC"
            sql = (
                f"SELECT num_a, num_b, COUNT(*) AS pair_count FROM ("
                f"{' UNION ALL '.join(unions)}"
                f") AS pairs GROUP BY num_a, num_b "
                f"ORDER BY pair_count {sort_dir} LIMIT %s"
            )
            all_params.append(top_n)

            await cursor.execute(sql, all_params)
            rows = await cursor.fetchall()

            pairs = []
            for rank, row in enumerate(rows, 1):
                pct = round(row['pair_count'] / total_draws * 100, 1)
                pairs.append({
                    "num_a": row['num_a'],
                    "num_b": row['num_b'],
                    "count": row['pair_count'],
                    "percentage": pct,
                    "rank": rank,
                })

            result = {
                "pairs": pairs,
                "total_draws": total_draws,
                "window": window,
            }
            await cache_set(cache_key, result)
            return result

          except Exception as e:
            logger.error(
                f"Erreur get_pair_correlations{self.cfg.log_label}: {e}"
            )
            return None

    async def get_single_pair(self, *, n1: int, n2: int):
        """
        Co-occurrence count + rank for a specific pair of numbers.
        n1 and n2 are normalized (n1 < n2).
        Cache: {prefix}pair_single:{n1}:{n2}, TTL 1h.
        Returns: dict(n1, n2, count, percentage, rank, total_draws, total_pairs) or None.
        """
        a, b = min(n1, n2), max(n1, n2)
        cache_key = f"{self.cfg.cache_prefix}pair_single:{a}:{b}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        async with self._get_connection() as conn:
          try:
            cursor = await conn.cursor()

            await cursor.execute(
                f"SELECT COUNT(*) as total FROM {self.cfg.table}"
            )
            total_draws = (await cursor.fetchone())['total']

            if total_draws == 0:
                result = {"n1": a, "n2": b, "count": 0, "percentage": 0.0,
                          "rank": 0, "total_draws": 0, "total_pairs": 0}
                await cache_set(cache_key, result)
                return result

            # Count for the specific pair
            pair_cols = [
                ("boule_1", "boule_2"), ("boule_1", "boule_3"),
                ("boule_1", "boule_4"), ("boule_1", "boule_5"),
                ("boule_2", "boule_3"), ("boule_2", "boule_4"),
                ("boule_2", "boule_5"), ("boule_3", "boule_4"),
                ("boule_3", "boule_5"), ("boule_4", "boule_5"),
            ]
            unions = " UNION ALL ".join(
                f"SELECT LEAST({ca}, {cb}) AS num_a, GREATEST({ca}, {cb}) AS num_b "
                f"FROM {self.cfg.table}"
                for ca, cb in pair_cols
            )

            # Get count for this specific pair
            sql_count = (
                f"SELECT COUNT(*) AS pair_count FROM ({unions}) AS pairs "
                f"WHERE num_a = %s AND num_b = %s"
            )
            await cursor.execute(sql_count, [a, b])
            row = await cursor.fetchone()
            pair_count = row['pair_count']

            # Get rank + total pairs in a single query (avoids 2 extra heavy scans)
            sql_rank = (
                f"SELECT "
                f"SUM(CASE WHEN pair_count > %s THEN 1 ELSE 0 END) AS better, "
                f"COUNT(*) AS tp "
                f"FROM ("
                f"SELECT num_a, num_b, COUNT(*) AS pair_count FROM ({unions}) AS p2 "
                f"GROUP BY num_a, num_b"
                f") AS ranked"
            )
            await cursor.execute(sql_rank, [pair_count])
            rank_row = await cursor.fetchone()
            rank = rank_row['better'] + 1
            total_pairs = rank_row['tp']

            pct = round(pair_count / total_draws * 100, 1)
            result = {
                "n1": a, "n2": b, "count": pair_count,
                "percentage": pct, "rank": rank,
                "total_draws": total_draws, "total_pairs": total_pairs,
            }
            await cache_set(cache_key, result)
            return result

          except Exception as e:
            logger.error(
                f"Erreur get_single_pair{self.cfg.log_label}: {e}"
            )
            return None

    async def get_triplet_correlations(self, *, top_n=10, window=None):
        """
        Top triplets de boules co-occurrents (C(5,3)=10 triplets par tirage).
        window: "2A","5A" etc. = filtre date en annees, None = global.
        Cache: {prefix}triplets:{window}:{top_n}, TTL 1h.
        Retour: dict(triplets=[{num_a, num_b, num_c, count, percentage, rank}], total_draws, window)
        """
        cache_key = f"{self.cfg.cache_prefix}triplets:{window}:{top_n}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        async with self._get_connection() as conn:
          try:
            cursor = await conn.cursor()

            # Build optional date filter
            if window:
                years = int(window.replace("A", ""))
                await cursor.execute(
                    f"SELECT MAX(date_de_tirage) as d FROM {self.cfg.table}"
                )
                date_max = (await cursor.fetchone())['d']
                from datetime import timedelta
                date_from = date_max - timedelta(days=365 * years)
                date_filter = "WHERE date_de_tirage >= %s"
                params_per_union = [date_from]
            else:
                date_filter = ""
                params_per_union = []

            # Count total draws in window
            if date_filter:
                await cursor.execute(
                    f"SELECT COUNT(*) as total FROM {self.cfg.table} {date_filter}",
                    params_per_union,
                )
            else:
                await cursor.execute(
                    f"SELECT COUNT(*) as total FROM {self.cfg.table}"
                )
            total_draws = (await cursor.fetchone())['total']

            if total_draws == 0:
                result = {"triplets": [], "total_draws": 0, "window": window}
                await cache_set(cache_key, result)
                return result

            # 10 UNION ALL for C(5,3) triplets
            # Canonical ordering: LEAST for num_a, GREATEST for num_c,
            # middle = sum - min - max for num_b
            triplet_cols = [
                ("boule_1", "boule_2", "boule_3"),
                ("boule_1", "boule_2", "boule_4"),
                ("boule_1", "boule_2", "boule_5"),
                ("boule_1", "boule_3", "boule_4"),
                ("boule_1", "boule_3", "boule_5"),
                ("boule_1", "boule_4", "boule_5"),
                ("boule_2", "boule_3", "boule_4"),
                ("boule_2", "boule_3", "boule_5"),
                ("boule_2", "boule_4", "boule_5"),
                ("boule_3", "boule_4", "boule_5"),
            ]
            unions = []
            all_params = []
            for a, b, c in triplet_cols:
                unions.append(
                    f"SELECT LEAST({a}, {b}, {c}) AS num_a, "
                    f"({a} + {b} + {c} - LEAST({a}, {b}, {c}) - GREATEST({a}, {b}, {c})) AS num_b, "
                    f"GREATEST({a}, {b}, {c}) AS num_c "
                    f"FROM {self.cfg.table} {date_filter}"
                )
                all_params.extend(params_per_union)

            sql = (
                f"SELECT num_a, num_b, num_c, COUNT(*) AS triplet_count FROM ("
                f"{' UNION ALL '.join(unions)}"
                f") AS triplets GROUP BY num_a, num_b, num_c "
                f"ORDER BY triplet_count DESC LIMIT %s"
            )
            all_params.append(top_n)

            await cursor.execute(sql, all_params)
            rows = await cursor.fetchall()

            triplets = []
            for rank, row in enumerate(rows, 1):
                pct = round(row['triplet_count'] / total_draws * 100, 1)
                triplets.append({
                    "num_a": row['num_a'],
                    "num_b": row['num_b'],
                    "num_c": row['num_c'],
                    "count": row['triplet_count'],
                    "percentage": pct,
                    "rank": rank,
                })

            result = {
                "triplets": triplets,
                "total_draws": total_draws,
                "window": window,
            }
            await cache_set(cache_key, result)
            return result

          except Exception as e:
            logger.error(
                f"Erreur get_triplet_correlations{self.cfg.log_label}: {e}"
            )
            return None

    async def get_star_pair_correlations(self, *, top_n=10, window=None, order="hot"):
        """
        Paires d'etoiles EM (1 seule paire par tirage → simple GROUP BY).
        Ne fait rien si le jeu n'a pas exactement 2 colonnes secondaires.
        order: "hot" (DESC) or "cold" (ASC).
        """
        if len(self.cfg.secondary_columns) != 2:
            return None

        col_a, col_b = self.cfg.secondary_columns
        cache_key = f"{self.cfg.cache_prefix}star_pairs:{window}:{top_n}:{order}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        async with self._get_connection() as conn:
          try:
            cursor = await conn.cursor()

            if window:
                years = int(window.replace("A", ""))
                await cursor.execute(
                    f"SELECT MAX(date_de_tirage) as d FROM {self.cfg.table}"
                )
                date_max = (await cursor.fetchone())['d']
                from datetime import timedelta
                date_from = date_max - timedelta(days=365 * years)
                date_filter = "WHERE date_de_tirage >= %s"
                params = [date_from]
            else:
                date_filter = ""
                params = []

            if params:
                await cursor.execute(
                    f"SELECT COUNT(*) as total FROM {self.cfg.table} {date_filter}",
                    params,
                )
            else:
                await cursor.execute(
                    f"SELECT COUNT(*) as total FROM {self.cfg.table}"
                )
            total_draws = (await cursor.fetchone())['total']

            sort_dir = "ASC" if order == "cold" else "DESC"
            sql = (
                f"SELECT LEAST({col_a}, {col_b}) AS num_a, "
                f"GREATEST({col_a}, {col_b}) AS num_b, "
                f"COUNT(*) AS pair_count "
                f"FROM {self.cfg.table} {date_filter} "
                f"GROUP BY num_a, num_b "
                f"ORDER BY pair_count {sort_dir} LIMIT %s"
            )
            params.append(top_n)
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()

            pairs = []
            for rank, row in enumerate(rows, 1):
                pct = round(row['pair_count'] / total_draws * 100, 1) if total_draws else 0
                pairs.append({
                    "num_a": row['num_a'],
                    "num_b": row['num_b'],
                    "count": row['pair_count'],
                    "percentage": pct,
                    "rank": rank,
                })

            result = {
                "pairs": pairs,
                "total_draws": total_draws,
                "window": window,
            }
            await cache_set(cache_key, result)
            return result

          except Exception as e:
            logger.error(
                f"Erreur get_star_pair_correlations{self.cfg.log_label}: {e}"
            )
            return None

    async def get_single_star_pair(self, *, s1: int, s2: int):
        """
        Co-occurrence count + rank for a specific star pair.
        Returns None if the game has no star columns.
        """
        if len(self.cfg.secondary_columns) != 2:
            return None

        col_a, col_b = self.cfg.secondary_columns
        a, b = min(s1, s2), max(s1, s2)
        cache_key = f"{self.cfg.cache_prefix}star_pair_single:{a}:{b}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        async with self._get_connection() as conn:
          try:
            cursor = await conn.cursor()

            await cursor.execute(
                f"SELECT COUNT(*) as total FROM {self.cfg.table}"
            )
            total_draws = (await cursor.fetchone())['total']

            if total_draws == 0:
                result = {"s1": a, "s2": b, "count": 0, "percentage": 0.0,
                          "rank": 0, "total_draws": 0, "total_pairs": 0}
                await cache_set(cache_key, result)
                return result

            # Count for this specific star pair
            sql_count = (
                f"SELECT COUNT(*) AS pair_count FROM {self.cfg.table} "
                f"WHERE LEAST({col_a}, {col_b}) = %s AND GREATEST({col_a}, {col_b}) = %s"
            )
            await cursor.execute(sql_count, [a, b])
            pair_count = (await cursor.fetchone())['pair_count']

            # Rank + total pairs in a single query
            sql_rank = (
                f"SELECT "
                f"SUM(CASE WHEN pair_count > %s THEN 1 ELSE 0 END) AS better, "
                f"COUNT(*) AS tp "
                f"FROM ("
                f"SELECT LEAST({col_a}, {col_b}) AS sa, GREATEST({col_a}, {col_b}) AS sb, "
                f"COUNT(*) AS pair_count "
                f"FROM {self.cfg.table} GROUP BY sa, sb"
                f") AS ranked"
            )
            await cursor.execute(sql_rank, [pair_count])
            rank_row = await cursor.fetchone()
            rank = rank_row['better'] + 1
            total_pairs = rank_row['tp']

            pct = round(pair_count / total_draws * 100, 1)
            result = {
                "s1": a, "s2": b, "count": pair_count,
                "percentage": pct, "rank": rank,
                "total_draws": total_draws, "total_pairs": total_pairs,
            }
            await cache_set(cache_key, result)
            return result

          except Exception as e:
            logger.error(
                f"Erreur get_single_star_pair{self.cfg.log_label}: {e}"
            )
            return None
