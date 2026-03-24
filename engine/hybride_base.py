"""
Moteur HYBRIDE — Base class config-driven (E06 audit fix).

Eliminates ~75% duplication between hybride.py and hybride_em.py.
All game-specific differences are handled by EngineConfig.
"""

import logging
import random
from datetime import datetime, timedelta, timezone

from config.engine import EngineConfig
from config.i18n import _badges as _i18n_badges

logger = logging.getLogger(__name__)


class HybrideEngine:
    """Moteur de generation de grilles HYBRIDE — config-driven.

    Scoring hybride = poids_frequence x frequence + poids_retard x retard.

    Note epistemologique :
        Le composant "retard" (lag) dans la formule de scoring
        est un mecanisme de DIVERSIFICATION UX, pas un indicateur predictif.
        Chaque tirage est un evenement stochastique independant — le retard
        n'a aucune valeur predictive (confirme par analyse Gemini Deep Search,
        correction de Bonferroni). Le lag sert uniquement a eviter que le
        moteur propose toujours les memes numeros.
    """

    def __init__(self, cfg: EngineConfig):
        self.cfg = cfg

    # ── Static helpers ────────────────────────────────────────────────

    @staticmethod
    def _minmax_normalize(values: dict[int, float]) -> dict[int, float]:
        v_min = min(values.values())
        v_max = max(values.values())
        if v_max == v_min:
            return {k: 0.0 for k in values}
        return {k: (v - v_min) / (v_max - v_min) for k, v in values.items()}

    @staticmethod
    def normaliser_en_probabilites(scores: dict[int, float], temperature: float = 1.0) -> dict[int, float]:
        t = max(temperature, 0.1)
        adjusted = {}
        for n, s in scores.items():
            adjusted[n] = s ** (1.0 / t) if s > 0 else 0.0
        total = sum(adjusted.values())
        if total == 0:
            positives = [n for n, s in scores.items() if s > 0]
            if not positives:
                return {n: 1.0 / len(scores) for n in scores} if scores else {}
            return {n: (1.0 / len(positives) if s > 0 else 0.0) for n, s in scores.items()}
        return {n: v / total for n, v in adjusted.items()}

    @staticmethod
    def _apply_exclusions(candidates: list[int], exclusions: dict | None) -> list[int]:
        if not exclusions:
            return candidates
        filtered = candidates
        for low, high in exclusions.get("exclude_ranges", []):
            filtered = [n for n in filtered if n < low or n > high]
        for mult in exclusions.get("exclude_multiples", []):
            if mult > 0:
                filtered = [n for n in filtered if n % mult != 0]
        for num in exclusions.get("exclude_nums", []):
            filtered = [n for n in filtered if n != num]
        return filtered

    @staticmethod
    def _calculer_score_final(score_conformite: float, star_map: dict) -> int:
        if score_conformite >= 1.0:
            stars = 5
        elif score_conformite >= 0.85:
            stars = 4
        elif score_conformite >= 0.70:
            stars = 3
        elif score_conformite >= 0.50:
            stars = 2
        else:
            stars = 1
        return star_map[stars]

    # ── Reference date ────────────────────────────────────────────────

    async def get_reference_date(self, conn) -> datetime:
        try:
            cursor = await conn.cursor()
            await cursor.execute(
                f"SELECT MAX(date_de_tirage) as max_date FROM {self.cfg.table_name}"
            )
            row = await cursor.fetchone()
            max_date = row['max_date'] if row else None
            if not max_date:
                return datetime.now(timezone.utc)
            return datetime.strptime(str(max_date), "%Y-%m-%d")
        except Exception:
            return datetime.now(timezone.utc)

    # ── Boule scoring ─────────────────────────────────────────────────

    async def calculer_frequences(self, conn, date_limite: datetime | None) -> dict[int, float]:
        cursor = await conn.cursor()
        freq = {n: 0 for n in range(self.cfg.num_min, self.cfg.num_max + 1)}

        if date_limite:
            await cursor.execute(
                f"SELECT boule_1, boule_2, boule_3, boule_4, boule_5 "
                f"FROM {self.cfg.table_name} WHERE date_de_tirage >= %s "
                f"ORDER BY date_de_tirage",
                (date_limite.strftime("%Y-%m-%d"),)
            )
        else:
            await cursor.execute(
                f"SELECT boule_1, boule_2, boule_3, boule_4, boule_5 "
                f"FROM {self.cfg.table_name} ORDER BY date_de_tirage"
            )

        tirages = await cursor.fetchall()
        nb_tirages = len(tirages)
        if nb_tirages == 0:
            count = self.cfg.num_max - self.cfg.num_min + 1
            return {n: 1.0 / count for n in freq}

        for tirage in tirages:
            for key in ['boule_1', 'boule_2', 'boule_3', 'boule_4', 'boule_5']:
                freq[tirage[key]] += 1

        for n in freq:
            freq[n] = freq[n] / nb_tirages
        return freq

    async def calculer_retards(self, conn, date_limite: datetime | None) -> dict[int, float]:
        """Calcule le retard (lag) de chaque numero = nombre de tirages depuis sa derniere apparition.

        ATTENTION : Le retard n'a AUCUNE valeur predictive. Un numero "en retard" n'est pas "du".
        Ce calcul sert uniquement a diversifier les grilles generees (mecanisme UX).
        Cf. rapport Gemini Deep Search — loi des grands nombres par DILUTION, pas COMPENSATION.
        """
        cursor = await conn.cursor()
        retard = {n: 0 for n in range(self.cfg.num_min, self.cfg.num_max + 1)}
        derniere = {n: None for n in retard}

        if date_limite:
            await cursor.execute(
                f"SELECT boule_1, boule_2, boule_3, boule_4, boule_5, date_de_tirage "
                f"FROM {self.cfg.table_name} WHERE date_de_tirage >= %s "
                f"ORDER BY date_de_tirage DESC",
                (date_limite.strftime("%Y-%m-%d"),)
            )
        else:
            await cursor.execute(
                f"SELECT boule_1, boule_2, boule_3, boule_4, boule_5, date_de_tirage "
                f"FROM {self.cfg.table_name} ORDER BY date_de_tirage DESC"
            )

        tirages = await cursor.fetchall()
        if not tirages:
            return retard

        for idx, tirage in enumerate(tirages):
            for key in ['boule_1', 'boule_2', 'boule_3', 'boule_4', 'boule_5']:
                num = tirage[key]
                if derniere[num] is None:
                    derniere[num] = idx

        for n in retard:
            retard[n] = derniere[n] if derniere[n] is not None else len(tirages)

        max_r = max(retard.values()) or 1
        if max_r > 0:
            for n in retard:
                retard[n] = retard[n] / max_r
        return retard

    async def calculer_scores_fenetre(self, conn, date_limite: datetime | None) -> dict[int, float]:
        freq = await self.calculer_frequences(conn, date_limite)
        retard = await self.calculer_retards(conn, date_limite)
        freq = self._minmax_normalize(freq)
        retard = self._minmax_normalize(retard)
        # Le retard (poids 0.3) est un facteur de DIVERSIFICATION UX, pas un signal predictif.
        # Sans lui, le moteur convergerait vers les memes 5-7 numeros a chaque tirage.
        return {
            n: self.cfg.poids_frequence * freq[n] + self.cfg.poids_retard * retard[n]
            for n in range(self.cfg.num_min, self.cfg.num_max + 1)
        }

    async def calculer_scores_hybrides(self, conn, mode: str = "balanced") -> dict[int, float]:
        now = await self.get_reference_date(conn)
        date_princ = now - timedelta(days=self.cfg.fenetre_principale_annees * 365.25)
        date_rec = now - timedelta(days=self.cfg.fenetre_recente_annees * 365.25)

        scores_princ = await self.calculer_scores_fenetre(conn, date_princ)
        scores_rec = await self.calculer_scores_fenetre(conn, date_rec)

        poids = self.cfg.modes.get(mode, self.cfg.modes['balanced'])

        if self.cfg.fenetre_globale and len(poids) == 3:
            scores_glob = await self.calculer_scores_fenetre(conn, date_limite=None)
            p_p, p_r, p_g = poids
            return {
                n: p_p * scores_princ[n] + p_r * scores_rec[n] + p_g * scores_glob[n]
                for n in range(self.cfg.num_min, self.cfg.num_max + 1)
            }

        p_p, p_r = poids[0], poids[1]
        return {
            n: p_p * scores_princ[n] + p_r * scores_rec[n]
            for n in range(self.cfg.num_min, self.cfg.num_max + 1)
        }

    # ── Secondary scoring (chance / etoiles) ──────────────────────────

    async def calculer_frequences_secondary(self, conn, date_limite: datetime | None) -> dict[int, float]:
        cursor = await conn.cursor()
        cols = self.cfg.secondary_columns
        freq = {n: 0 for n in range(self.cfg.secondary_min, self.cfg.secondary_max + 1)}

        if len(cols) == 1:
            col = cols[0]
            if date_limite:
                await cursor.execute(
                    f"SELECT {col}, COUNT(*) as freq FROM {self.cfg.table_name} "
                    f"WHERE date_de_tirage >= %s GROUP BY {col}",
                    (date_limite.strftime("%Y-%m-%d"),)
                )
            else:
                await cursor.execute(
                    f"SELECT {col}, COUNT(*) as freq FROM {self.cfg.table_name} GROUP BY {col}"
                )
            for row in await cursor.fetchall():
                freq[row[col]] = row['freq']
        else:
            parts = []
            params = []
            for col in cols:
                if date_limite:
                    parts.append(f"SELECT {col} as num FROM {self.cfg.table_name} WHERE date_de_tirage >= %s")
                    params.append(date_limite.strftime("%Y-%m-%d"))
                else:
                    parts.append(f"SELECT {col} as num FROM {self.cfg.table_name}")
            await cursor.execute(
                f"SELECT num, COUNT(*) as freq FROM ({' UNION ALL '.join(parts)}) t GROUP BY num",
                params
            )
            for row in await cursor.fetchall():
                freq[row['num']] = row['freq']

        # Normalize by draw count
        if date_limite:
            await cursor.execute(
                f"SELECT COUNT(*) as count FROM {self.cfg.table_name} WHERE date_de_tirage >= %s",
                (date_limite.strftime("%Y-%m-%d"),)
            )
        else:
            await cursor.execute(f"SELECT COUNT(*) as count FROM {self.cfg.table_name}")
        result = await cursor.fetchone()
        nb = result['count'] if result else 0

        if nb == 0:
            count = self.cfg.secondary_max - self.cfg.secondary_min + 1
            return {n: 1.0 / count for n in freq}

        for n in freq:
            freq[n] = freq[n] / nb
        return freq

    async def calculer_retards_secondary(self, conn, date_limite: datetime | None) -> dict[int, float]:
        cursor = await conn.cursor()
        cols = self.cfg.secondary_columns
        retard = {n: 0 for n in range(self.cfg.secondary_min, self.cfg.secondary_max + 1)}
        derniere = {n: None for n in retard}

        col_list = ", ".join(cols) + ", date_de_tirage"
        if date_limite:
            await cursor.execute(
                f"SELECT {col_list} FROM {self.cfg.table_name} "
                f"WHERE date_de_tirage >= %s ORDER BY date_de_tirage DESC",
                (date_limite.strftime("%Y-%m-%d"),)
            )
        else:
            await cursor.execute(
                f"SELECT {col_list} FROM {self.cfg.table_name} ORDER BY date_de_tirage DESC"
            )

        tirages = await cursor.fetchall()
        if not tirages:
            return retard

        for idx, tirage in enumerate(tirages):
            for col in cols:
                n = tirage.get(col)
                if n is not None and derniere.get(n) is None:
                    derniere[n] = idx

        for n in retard:
            retard[n] = derniere[n] if derniere[n] is not None else len(tirages)

        max_r = max(retard.values()) or 1
        if max_r > 0:
            for n in retard:
                retard[n] = retard[n] / max_r
        return retard

    async def calculer_scores_fenetre_secondary(self, conn, date_limite: datetime | None) -> dict[int, float]:
        freq = await self.calculer_frequences_secondary(conn, date_limite)
        retard = await self.calculer_retards_secondary(conn, date_limite)
        freq = self._minmax_normalize(freq)
        retard = self._minmax_normalize(retard)
        return {
            n: self.cfg.poids_frequence * freq.get(n, 0) + self.cfg.poids_retard * retard.get(n, 0)
            for n in range(self.cfg.secondary_min, self.cfg.secondary_max + 1)
        }

    async def calculer_scores_hybrides_secondary(self, conn, mode: str = "balanced") -> dict[int, float]:
        now = await self.get_reference_date(conn)
        date_princ = now - timedelta(days=self.cfg.fenetre_principale_annees * 365.25)
        date_rec = now - timedelta(days=self.cfg.fenetre_recente_annees * 365.25)

        scores_princ = await self.calculer_scores_fenetre_secondary(conn, date_princ)
        scores_rec = await self.calculer_scores_fenetre_secondary(conn, date_rec)

        poids = self.cfg.modes.get(mode, self.cfg.modes['balanced'])

        if self.cfg.fenetre_globale and len(poids) == 3:
            scores_glob = await self.calculer_scores_fenetre_secondary(conn, date_limite=None)
            p_p, p_r, p_g = poids
            return {
                n: p_p * scores_princ.get(n, 0) + p_r * scores_rec.get(n, 0) + p_g * scores_glob.get(n, 0)
                for n in range(self.cfg.secondary_min, self.cfg.secondary_max + 1)
            }

        p_p, p_r = poids[0], poids[1]
        return {
            n: p_p * scores_princ.get(n, 0) + p_r * scores_rec.get(n, 0)
            for n in range(self.cfg.secondary_min, self.cfg.secondary_max + 1)
        }

    # ── Penalization ──────────────────────────────────────────────────

    async def get_recent_draws(self, conn, n: int | None = None) -> list[dict]:
        n = n or self.cfg.penalty_window
        cursor = await conn.cursor()
        cols = "date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5"
        for col in self.cfg.secondary_columns:
            cols += f", {col}"
        await cursor.execute(
            f"SELECT {cols} FROM {self.cfg.table_name} ORDER BY date_de_tirage DESC LIMIT %s",
            (n,)
        )
        rows = await cursor.fetchall()
        return rows[:n]

    def apply_boule_penalties(self, scores: dict[int, float], recent_draws: list[dict]) -> dict[int, float]:
        if not recent_draws:
            return scores
        penalized = dict(scores)
        num_coeff: dict[int, float] = {}
        coeffs = self.cfg.penalty_coefficients
        for position, draw in enumerate(recent_draws[:len(coeffs)]):
            coeff = coeffs[position]
            for i in range(1, 6):
                n = draw.get(f'boule_{i}')
                if n is not None and n not in num_coeff:
                    num_coeff[n] = coeff
        for n, coeff in num_coeff.items():
            if n in penalized:
                penalized[n] = 0.0 if coeff == 0.0 else penalized[n] * coeff
        return penalized

    def apply_secondary_penalties(self, scores: dict[int, float], recent_draws: list[dict]) -> dict[int, float]:
        if not recent_draws:
            return scores
        penalized = dict(scores)
        coeff_map: dict[int, float] = {}
        coeffs = self.cfg.penalty_coefficients
        for position, draw in enumerate(recent_draws[:len(coeffs)]):
            coeff = coeffs[position]
            for col in self.cfg.secondary_columns:
                s = draw.get(col)
                if s is not None and s not in coeff_map:
                    coeff_map[s] = coeff
        for s, coeff in coeff_map.items():
            if s in penalized:
                penalized[s] = 0.0 if coeff == 0.0 else penalized[s] * coeff
        return penalized

    # ── Anti-collision ────────────────────────────────────────────────

    def apply_anti_collision(self, scores: dict[int, float]) -> dict[int, float]:
        adjusted = dict(scores)
        for n in adjusted:
            if n > self.cfg.anti_collision_threshold:
                adjusted[n] *= self.cfg.anti_collision_high_boost
            if n in self.cfg.superstitious_numbers:
                adjusted[n] *= self.cfg.anti_collision_superstitious_malus
        return adjusted

    def apply_secondary_anti_collision(self, scores: dict[int, float]) -> dict[int, float]:
        if not self.cfg.superstitious_secondary:
            return scores
        adjusted = dict(scores)
        for s in self.cfg.superstitious_secondary:
            if s in adjusted:
                adjusted[s] *= self.cfg.secondary_anti_collision_malus
        return adjusted

    # ── Validation ────────────────────────────────────────────────────

    def valider_contraintes(self, numeros: list[int]) -> float:
        score = 1.0
        nb_pairs = sum(1 for n in numeros if n % 2 == 0)
        if nb_pairs < 1 or nb_pairs > 4:
            score *= 0.8
        nb_bas = sum(1 for n in numeros if n <= self.cfg.seuil_bas_haut)
        if nb_bas < 1 or nb_bas > 4:
            score *= 0.85
        somme = sum(numeros)
        if somme < self.cfg.somme_min or somme > self.cfg.somme_max:
            score *= 0.7
        dispersion = max(numeros) - min(numeros)
        if dispersion < self.cfg.dispersion_min:
            score *= 0.6
        nums_sorted = sorted(numeros)
        suites = sum(1 for i in range(len(nums_sorted) - 1) if nums_sorted[i + 1] - nums_sorted[i] == 1)
        if suites > self.cfg.max_consecutifs:
            score *= 0.75
        return score

    def valider_forced_numbers(
        self, forced_nums: list[int] | None, forced_secondary: list[int] | None,
    ) -> tuple[list[int], list[int]]:
        cleaned_nums = []
        if forced_nums:
            seen: set[int] = set()
            for n in forced_nums:
                if (self.cfg.num_min <= n <= self.cfg.num_max
                        and n not in seen and len(cleaned_nums) < self.cfg.num_count):
                    cleaned_nums.append(n)
                    seen.add(n)
        cleaned_sec = []
        if forced_secondary:
            seen_s: set[int] = set()
            for s in forced_secondary:
                if (self.cfg.secondary_min <= s <= self.cfg.secondary_max
                        and s not in seen_s and len(cleaned_sec) < self.cfg.secondary_count):
                    cleaned_sec.append(s)
                    seen_s.add(s)
        return cleaned_nums, cleaned_sec

    # ── Secondary generation ──────────────────────────────────────────

    async def generer_secondary(
        self, conn, mode: str = "balanced",
        recent_draws: list[dict] | None = None,
        anti_collision: bool = False,
    ) -> list[int]:
        scores = await self.calculer_scores_hybrides_secondary(conn, mode=mode)
        scores = self.apply_secondary_penalties(scores, recent_draws or [])
        if anti_collision:
            scores = self.apply_secondary_anti_collision(scores)

        hard_excluded = {n for n in range(self.cfg.secondary_min, self.cfg.secondary_max + 1)
                         if scores.get(n, 0) == 0.0}
        disponibles = [n for n in range(self.cfg.secondary_min, self.cfg.secondary_max + 1)
                       if n not in hard_excluded]
        if len(disponibles) < self.cfg.secondary_count:
            disponibles = list(range(self.cfg.secondary_min, self.cfg.secondary_max + 1))
            scores = {n: 1.0 for n in disponibles}

        temperature = self.cfg.temperature_by_mode.get(mode, 1.3)
        scores_draw = {n: scores[n] for n in disponibles}
        probas_dict = self.normaliser_en_probabilites(scores_draw, temperature=temperature)
        probas = [probas_dict[n] for n in disponibles]

        result = []
        for _ in range(self.cfg.secondary_count):
            choice = random.choices(disponibles, weights=probas, k=1)[0]
            result.append(choice)
            idx = disponibles.index(choice)
            disponibles.pop(idx)
            probas.pop(idx)
        return sorted(result)

    # ── Grid generation ───────────────────────────────────────────────

    async def generer_grille(
        self, conn,
        scores_hybrides: dict[int, float],
        mode: str = "balanced",
        anti_collision: bool = False,
        forced_nums: list[int] | None = None,
        forced_secondary: list[int] | None = None,
        exclusions: dict | None = None,
        recent_draws: list[dict] | None = None,
        lang: str = "fr",
    ) -> dict:
        if forced_nums is None:
            forced_nums = []
        if forced_secondary is None:
            forced_secondary = []
        forced_set = set(forced_nums)

        # Penalization
        penalized = self.apply_boule_penalties(scores_hybrides, recent_draws or [])
        # Anti-collision
        if anti_collision:
            penalized = self.apply_anti_collision(penalized)

        hard_excluded = {n for n in range(self.cfg.num_min, self.cfg.num_max + 1)
                         if penalized.get(n, 0) == 0.0 and n not in forced_set}

        temperature = self.cfg.temperature_by_mode.get(mode, 1.3)
        probas = self.normaliser_en_probabilites(penalized, temperature=temperature)

        meilleure_grille = None
        meilleur_score = 0
        nb_to_draw = self.cfg.num_count - len(forced_nums)

        for _ in range(self.cfg.max_tentatives):
            disponibles = [n for n in range(self.cfg.num_min, self.cfg.num_max + 1)
                           if n not in forced_set and n not in hard_excluded]
            disponibles = self._apply_exclusions(disponibles, exclusions)
            if len(disponibles) < nb_to_draw:
                disponibles = [n for n in range(self.cfg.num_min, self.cfg.num_max + 1)
                               if n not in forced_set]
            p_list = [probas[n] for n in disponibles]

            numeros = list(forced_nums)
            for _ in range(nb_to_draw):
                num = random.choices(disponibles, weights=p_list, k=1)[0]
                numeros.append(num)
                idx = disponibles.index(num)
                disponibles.pop(idx)
                p_list.pop(idx)

            numeros = sorted(numeros)
            conf = self.valider_contraintes(numeros)
            if conf > meilleur_score:
                meilleure_grille = numeros
                meilleur_score = conf
            if conf >= self.cfg.min_conformite:
                break

        numeros = meilleure_grille
        score_conformite = meilleur_score

        # Secondary numbers
        if len(forced_secondary) >= self.cfg.secondary_count:
            secondary = sorted(forced_secondary[:self.cfg.secondary_count])
        elif forced_secondary:
            all_sec = await self.generer_secondary(
                conn, mode=mode, recent_draws=recent_draws, anti_collision=anti_collision,
            )
            secondary = list(forced_secondary)
            for s in all_sec:
                if s not in secondary and len(secondary) < self.cfg.secondary_count:
                    secondary.append(s)
            secondary = sorted(secondary)
        else:
            secondary = await self.generer_secondary(
                conn, mode=mode, recent_draws=recent_draws, anti_collision=anti_collision,
            )

        score_final = self._calculer_score_final(score_conformite, self.cfg.star_to_legacy_score)

        result = {
            'nums': numeros,
            self.cfg.secondary_name: secondary[0] if self.cfg.secondary_count == 1 else secondary,
            'score': score_final,
            'badges': self._generer_badges(numeros, scores_hybrides, lang),
        }
        if forced_nums:
            result['forced_nums'] = forced_nums
        if forced_secondary:
            key = 'forced_chance' if self.cfg.secondary_name == 'chance' else 'forced_etoiles'
            result[key] = forced_secondary
        return result

    def _generer_badges(self, numeros: list[int], scores_hybrides: dict[int, float], lang: str = "fr") -> list[str]:
        """Generate descriptive badges for a grid. Uses i18n labels."""
        b = _i18n_badges(lang)
        badges = []
        score_moyen = sum(scores_hybrides[n] for n in numeros) / self.cfg.num_count
        score_global = sum(scores_hybrides.values()) / len(scores_hybrides)
        if score_moyen > score_global * 1.1:
            badges.append(b["hot"])
        elif score_moyen < score_global * 0.9:
            badges.append(b["overdue"])
        else:
            badges.append(b["balanced"])
        dispersion = max(numeros) - min(numeros)
        if dispersion > 35:
            badges.append(b["wide_spectrum"])
        nb_pairs = sum(1 for n in numeros if n % 2 == 0)
        if nb_pairs == 2 or nb_pairs == 3:
            badges.append(b["even_odd"])
        badges.append("Hybride V1")  # brand name — not translated
        return badges

    # ── Main API ──────────────────────────────────────────────────────

    async def generate_grids(
        self, n: int = 5, mode: str = "balanced", lang: str = "fr",
        anti_collision: bool = False,
        forced_nums: list[int] | None = None,
        forced_secondary: list[int] | None = None,
        exclusions: dict | None = None,
        _get_connection=None,
    ) -> dict:
        if _get_connection is None:
            from .db import get_connection as _get_connection

        async with _get_connection() as conn:
            scores_hybrides = await self.calculer_scores_hybrides(conn, mode=mode)
            recent_draws = await self.get_recent_draws(conn)

            grilles = []
            for _ in range(n):
                grille = await self.generer_grille(
                    conn, scores_hybrides, mode=mode,
                    anti_collision=anti_collision,
                    forced_nums=forced_nums, forced_secondary=forced_secondary,
                    exclusions=exclusions, recent_draws=recent_draws, lang=lang,
                )
                grilles.append(grille)

            grilles = sorted(grilles, key=lambda g: g['score'], reverse=True)

            cursor = await conn.cursor()
            await cursor.execute(f"SELECT COUNT(*) as count FROM {self.cfg.table_name}")
            result = await cursor.fetchone()
            nb_tirages = result['count'] if result else 0

            await cursor.execute(
                f"SELECT MIN(date_de_tirage) as min_date, MAX(date_de_tirage) as max_date "
                f"FROM {self.cfg.table_name}"
            )
            result = await cursor.fetchone()
            date_min = result['min_date'] if result else None
            date_max = result['max_date'] if result else None

            # Ponderation display string (legacy 2-window format for API/frontend compat).
            # Real 3-window weights are in cfg.modes: conservative=50/30/20, balanced=40/35/25, recent=25/35/40.
            _legacy_pond = {"conservative": "70/30", "balanced": "60/40", "recent": "40/60"}
            ponderation = _legacy_pond.get(mode, "60/40")

            metadata = {
                'mode': self.cfg.mode_label,
                'mode_generation': mode,
                'fenetre_principale_annees': self.cfg.fenetre_principale_annees,
                'fenetre_recente_annees': self.cfg.fenetre_recente_annees,
                'fenetre_globale': self.cfg.fenetre_globale,
                'ponderation': ponderation,
                'nb_tirages_total': nb_tirages,
                'periode_base': f"{date_min} -> {date_max}",
                'avertissement': self.cfg.avertissement,
                'anti_collision': {
                    'enabled': anti_collision,
                    'high_threshold': self.cfg.anti_collision_threshold,
                    'high_boost': self.cfg.anti_collision_high_boost,
                    'superstitious_malus': self.cfg.anti_collision_superstitious_malus,
                    'superstitious_numbers': sorted(self.cfg.superstitious_numbers),
                    'note': f"Les numeros 1-31 sont sur-selectionnes. "
                            f"Privilegier les numeros >{self.cfg.anti_collision_threshold} "
                            f"maximise l'esperance de gain en cas de jackpot partage.",
                },
                'temperature': self.cfg.temperature_by_mode.get(mode, 1.3),
            }

            return {'grids': grilles, 'metadata': metadata}
