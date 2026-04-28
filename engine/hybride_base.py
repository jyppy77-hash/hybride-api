"""
Moteur HYBRIDE — Base class config-driven (E06 audit fix).

Eliminates ~75% duplication between hybride.py and hybride_em.py.
All game-specific differences are handled by EngineConfig.
"""

import logging
import math
import random
import statistics
from datetime import datetime, timedelta, timezone

from config.engine import EngineConfig
from config.i18n import _badges as _i18n_badges
from services.decay_state import calculate_decay_multiplier, get_decay_state
from services.penalization import get_unpopularity_multiplier
from services.esi import validate_esi

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

    Note securite SQL :
        Les requetes utilisent des f-strings pour le nom de table
        ({self.cfg.table_name}). C'est sur car table_name provient d'un
        EngineConfig frozen dont les valeurs sont des constantes internes
        ("tirages", "tirages_euromillions"). Aucune entree utilisateur ne
        peut atteindre table_name. Les parametres dynamiques (dates, etc.)
        utilisent des placeholders %s (parameterized queries).
    """

    def __init__(self, cfg: EngineConfig):
        self.cfg = cfg

    # ── Static helpers ────────────────────────────────────────────────

    @staticmethod
    def _minmax_normalize(values: dict[int, float]) -> dict[int, float]:
        """Min-max normalize values to [0, 1].

        If all values are identical (max == min), returns 0.0 for all keys.
        This is intentional: a uniform frequency distribution means no number
        stands out, so all receive the minimum score. The temperature in
        normaliser_en_probabilites() compensates by flattening toward uniform.
        """
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
            return datetime.strptime(str(max_date), "%Y-%m-%d").replace(tzinfo=timezone.utc)
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
            logger.warning(
                "calculer_frequences: 0 tirages for %s (date_limite=%s) — uniform fallback",
                self.cfg.table_name, date_limite,
            )
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
            logger.warning(
                "calculer_retards: 0 tirages for %s (date_limite=%s) — zero retard fallback",
                self.cfg.table_name, date_limite,
            )
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
        # Les scores par fenetre sont dans [0, 1] grace a la normalisation min-max
        # dans calculer_scores_fenetre(). La combinaison ponderee (sum poids * score)
        # produit un resultat dans [0, 1] car sum(poids) = 1.0. Pas besoin de
        # re-normaliser — normaliser_en_probabilites() le fera en fin de pipeline.
        #
        # DESIGN NOTE (F01 audit 24/03/2026): Identical scoring formula for main
        # numbers and secondary numbers (stars/chance). The reduced space of EM stars
        # (12 vs 50) does NOT require separate weights because:
        # 1. Scoring serves UX diversification, not statistical prediction
        # 2. Temperature-based sampling already compensates for space differences
        # 3. Min-max normalization homogenizes scales regardless of space size
        #
        # DESIGN NOTE (F02 audit 24/03/2026): Intentional overlap between windows.
        # The global window includes draws from the principal and recent windows.
        # This is by design: global acts as a stabilizer, smoothing noise from
        # shorter windows. Weights sum to 1.0 per mode, which compensates for
        # the overlap. See also inline comment at window combination below.
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
                # V135: guard NULL/range — pipeline import 2 étapes peut laisser
                # secondary NULL temporairement (diagnostic V2 hyp F, 28/04/2026).
                val = row[col]
                if val is None:
                    logger.warning(
                        "[HYBRIDE-SECONDARY] %s NULL détecté dans %s.%s — skipped "
                        "(probable NULL transitoire pipeline import).",
                        self.cfg.game, self.cfg.table_name, col,
                    )
                    continue
                if not (self.cfg.secondary_min <= val <= self.cfg.secondary_max):
                    logger.warning(
                        "[HYBRIDE-SECONDARY] %s value %s out of range [%d,%d] in %s.%s — skipped.",
                        self.cfg.game, val, self.cfg.secondary_min, self.cfg.secondary_max,
                        self.cfg.table_name, col,
                    )
                    continue
                freq[val] = row['freq']
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
                # V135: guard NULL/range (idem branche single-col, pour EM stars).
                val = row['num']
                if val is None:
                    logger.warning(
                        "[HYBRIDE-SECONDARY] %s NULL détecté dans %s (UNION) — skipped.",
                        self.cfg.game, self.cfg.table_name,
                    )
                    continue
                if not (self.cfg.secondary_min <= val <= self.cfg.secondary_max):
                    logger.warning(
                        "[HYBRIDE-SECONDARY] %s value %s out of range [%d,%d] — skipped.",
                        self.cfg.game, val, self.cfg.secondary_min, self.cfg.secondary_max,
                    )
                    continue
                freq[val] = row['freq']

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
            logger.warning(
                "calculer_frequences_secondary: 0 tirages for %s (date_limite=%s) — uniform fallback",
                self.cfg.table_name, date_limite,
            )
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
            logger.warning(
                "calculer_retards_secondary: 0 tirages for %s (date_limite=%s) — zero retard fallback",
                self.cfg.table_name, date_limite,
            )
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
        # F08 audit: dedicated weights for secondary (85/15 vs primary 70/30)
        pf = self.cfg.poids_frequence_secondary
        pr = self.cfg.poids_retard_secondary
        return {
            n: pf * freq.get(n, 0) + pr * retard.get(n, 0)
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

    # ── Z-score penalization (alternative) ───────────────────────────

    def apply_penalties_z_score(
        self, scores: dict[int, float], recent_draws: list[dict],
    ) -> dict[int, float]:
        """Z-score alternative for recent-draw penalization.

        Converts scores to z-scores (mean=0, std=1), then subtracts offsets
        by tier (T-2: -2.0, T-3: -1.0, T-4: -0.5). T-1 remains hard-exclude.
        Normalizes automatically across windows of different sizes.

        Falls back to multiplicative method if std=0.
        See audit 360° Engine HYBRIDE F06 — 01/04/2026.
        """
        if not recent_draws:
            return scores

        vals = [v for v in scores.values() if v > 0]
        if len(vals) < 2:
            return self.apply_boule_penalties(scores, recent_draws)
        mean = statistics.mean(vals)
        std = statistics.stdev(vals)
        if std == 0:
            return self.apply_boule_penalties(scores, recent_draws)

        # Convert to z-scores
        z_scores = {n: (s - mean) / std for n, s in scores.items()}

        # Build number -> tier mapping (same logic as apply_boule_penalties)
        offsets = self.cfg.z_score_offsets
        num_offset: dict[int, float] = {}
        for position, draw in enumerate(recent_draws[:len(offsets)]):
            for i in range(1, 6):
                n = draw.get(f'boule_{i}')
                if n is not None and n not in num_offset:
                    num_offset[n] = offsets[position]

        # Apply offsets
        for n, offset in num_offset.items():
            if n in z_scores:
                if offset == 0.0:  # T-1: hard exclude
                    z_scores[n] = -999.0
                else:
                    z_scores[n] -= offset

        # Convert back to positive scores
        z_min = min(z_scores.values())
        epsilon = 0.01
        result = {}
        for n, z in z_scores.items():
            if num_offset.get(n, 1.0) == 0.0:  # T-1 hard excluded
                result[n] = 0.0
            else:
                result[n] = max(0.0, z - z_min + epsilon)
        return result

    # ── Anti-collision ────────────────────────────────────────────────

    def apply_anti_collision(self, scores: dict[int, float]) -> dict[int, float]:
        """Adjust scores to reduce jackpot sharing risk.

        Boost and malus are applied independently. A number could theoretically
        receive both (if > threshold AND superstitious). With current configs
        this cannot happen (all superstitious numbers are <= 13, thresholds
        are 24/31). If configs evolve, the net effect is a reduced boost.
        """
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

    # ── Decay score (anti-lock rotation) ────────────────────────────

    def apply_decay(
        self, scores: dict[int, float], decay_state: dict[int, int],
        rate: float | None = None,
    ) -> dict[int, float]:
        """Apply accelerated decay multiplier to break kernel lock.

        Numbers selected N times without appearing in real draws
        get progressively penalized (score × decay_multiplier).
        V92: acceleration makes each consecutive selection weigh more.

        Args:
            rate: override decay_rate (used for secondary with decay_rate_secondary).

        Pipeline position: step 4a (after penalization, before persistent brake).
        """
        if not self.cfg.decay_enabled or not decay_state:
            return scores
        r = rate if rate is not None else self.cfg.decay_rate
        decayed = {}
        for n, score in scores.items():
            selections = decay_state.get(n, 0)
            multiplier = calculate_decay_multiplier(
                selections, r, self.cfg.decay_floor, self.cfg.decay_acceleration,
            )
            decayed[n] = score * multiplier
        return decayed

    # ── V110: Persistent saturation brake (inter-draw rotation) ──────

    def apply_persistent_brake(
        self,
        scores: dict[int, float],
        brake_map: dict[int, float] | None,
    ) -> dict[int, float]:
        """V110 — Apply inter-draw persistent saturation brake.

        Unlike the uniform decay multiplier which preserves the ratio
        score_a / score_b for all not-drawn numbers, this brake is applied
        ONLY to numbers selected in canonical grids of T-1 (×0.20) and T-2 (×0.50).
        This creates a differential that CAN reverse intra-zone ordering.

        Numbers not in brake_map keep their score unchanged (implicit ×1.0).
        Numbers already at score 0 (hard-excluded T-1) stay at 0.

        Pipeline position: step 4b (after decay 4a, before intra-batch saturation 4c).
        See docs/AUDIT_360_DECAY_META_PIPELINE_V123.md axis 4 — F01.1-01.
        """
        if not brake_map:
            return scores
        return {n: s * brake_map.get(n, 1.0) for n, s in scores.items()}

    # ── Noise (intra-session diversification) ───────────────────────

    @staticmethod
    def apply_noise(scores: dict[int, float], noise_factor: float) -> dict[int, float]:
        """Add gaussian noise proportional to score std-dev.

        The noise amplitude auto-adapts: tight score windows get less noise,
        dispersed windows get more. Each call produces a different draw.

        Pipeline position: step 4b (after decay, before anti-collision).
        See audit 360° Engine HYBRIDE F01 — 01/04/2026.
        """
        if noise_factor <= 0.0 or len(scores) < 2:
            return scores
        vals = [v for v in scores.values() if v > 0]
        if len(vals) < 2:
            return scores
        std = statistics.stdev(vals)
        if std == 0:
            return scores
        sigma = noise_factor * std
        return {n: max(0.0, s + random.gauss(0, sigma)) for n, s in scores.items()}

    # ── Wildcard froid (guaranteed cold slot) ────────────────────────

    def _select_wildcard(
        self, scores: dict[int, float], excluded: set[int],
    ) -> int | None:
        """Pick 1 number from the coldest pool (bottom-N by score).

        Weighted random within the cold pool (T=1.5 for extra randomness).
        Returns None if wildcard disabled or pool empty.
        """
        if not self.cfg.wildcard_enabled:
            return None
        candidates = sorted(
            ((n, s) for n, s in scores.items() if n not in excluded and s > 0),
            key=lambda x: x[1],
        )
        pool = candidates[:self.cfg.wildcard_pool_size]
        if not pool:
            return None
        pool_scores = {n: s for n, s in pool}
        probas = self.normaliser_en_probabilites(pool_scores, temperature=1.5)
        nums = list(probas.keys())
        weights = [probas[n] for n in nums]
        return random.choices(nums, weights=weights, k=1)[0]

    # ── Validation ────────────────────────────────────────────────────

    def valider_contraintes(self, numeros: list[int]) -> float:
        if len(numeros) != self.cfg.num_count:
            raise ValueError(f"Expected {self.cfg.num_count} numbers, got {len(numeros)}")
        nb_pairs = sum(1 for n in numeros if n % 2 == 0)
        # Hard-reject: all-even or all-odd (F05 audit 01/04/2026)
        if nb_pairs == 0 or nb_pairs == self.cfg.num_count:
            return 0.0
        score = 1.0
        # Soft penalty for near-extreme pair counts (1 or num_count-1)
        if nb_pairs == 1 or nb_pairs == (self.cfg.num_count - 1):
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
        decay_state_secondary: dict[int, int] | None = None,
        saturated_secondary: set[int] | None = None,
        persistent_brake_map_secondary: dict[int, float] | None = None,
    ) -> list[int]:
        scores = await self.calculer_scores_hybrides_secondary(conn, mode=mode)
        scores = self.apply_secondary_penalties(scores, recent_draws or [])
        # V92: decay for secondary numbers (stars/chance) with dedicated rate
        if decay_state_secondary:
            scores = self.apply_decay(
                scores, decay_state_secondary, rate=self.cfg.decay_rate_secondary,
            )
        # V110: Persistent saturation brake for secondary (step 4b — inter-draw)
        if persistent_brake_map_secondary:
            scores = self.apply_persistent_brake(scores, persistent_brake_map_secondary)
        # V105: Saturation Brake for secondary numbers (step 4c — intra-batch)
        if saturated_secondary:
            _brake = self.cfg.saturation_brake_secondary
            scores = {n: (s * _brake if n in saturated_secondary else s)
                      for n, s in scores.items()}
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

    # ── V104: Zone-stratified selection ─────────────────────────────────

    def _draw_stratified(
        self,
        probas: dict[int, float],
        forced_set: set[int],
        hard_excluded: set[int],
        exclusions: dict | None,
    ) -> list[int]:
        """Draw 1 number per zone using weighted sampling.

        Each zone yields exactly 1 number. If a zone is empty after
        exclusions and hard-exclude, the exclusions are relaxed for that zone.
        """
        result = []
        for lo, hi in self.cfg.zones:
            pool = [n for n in range(lo, hi + 1)
                    if n not in forced_set and n not in hard_excluded]
            pool = self._apply_exclusions(pool, exclusions)
            if not pool:
                # Relax exclusions — keep only hard-exclude
                pool = [n for n in range(lo, hi + 1)
                        if n not in forced_set and n not in hard_excluded]
            if not pool:
                # Ultimate fallback — any number in zone (ignore hard-exclude too)
                pool = [n for n in range(lo, hi + 1) if n not in forced_set]
            weights = [probas.get(n, 0.001) for n in pool]
            choice = random.choices(pool, weights=weights, k=1)[0]
            result.append(choice)
        return result

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
        decay_state: dict[int, int] | None = None,
        decay_state_secondary: dict[int, int] | None = None,
        saturated_balls: set[int] | None = None,
        saturated_secondary: set[int] | None = None,
        persistent_brake_map: dict[int, float] | None = None,
        persistent_brake_map_secondary: dict[int, float] | None = None,
    ) -> dict:
        if forced_nums is None:
            forced_nums = []
        if forced_secondary is None:
            forced_secondary = []
        forced_set = set(forced_nums)

        # Penalization (step 3 — multiplicative or z-score)
        if self.cfg.penalization_method == "z_score":
            penalized = self.apply_penalties_z_score(scores_hybrides, recent_draws or [])
        else:
            penalized = self.apply_boule_penalties(scores_hybrides, recent_draws or [])
        # Decay score (step 4a — break kernel lock)
        if decay_state:
            penalized = self.apply_decay(penalized, decay_state)
        # V110: Persistent saturation brake (step 4b — inter-draw rotation)
        # Brakes specifically the numbers selected in the canonical grid of T-1 (and T-2).
        # forced_nums are excluded (user-chosen must be respected).
        if persistent_brake_map:
            _brake_map_filtered = {n: m for n, m in persistent_brake_map.items() if n not in forced_set}
            penalized = self.apply_persistent_brake(penalized, _brake_map_filtered)
        # V105: Saturation Brake (step 4c — intra-batch rotation, after persistent)
        # Numbers selected in a previous grid of the same batch get heavily penalized.
        # forced_nums are excluded from saturation (user-chosen, must be respected).
        if saturated_balls:
            _brake = self.cfg.saturation_brake
            penalized = {n: (s * _brake if n in saturated_balls and n not in forced_set else s)
                         for n, s in penalized.items()}
        # V106: Unpopularity scoring (step 4d — after saturation, before anti-collision)
        # Penalizes over-played numbers (calendar bias, lucky 7, multiples of 5).
        # Applied to balls only, not secondary (universe too small).
        if self.cfg.unpopularity_enabled:
            penalized = {n: s * get_unpopularity_multiplier(n) for n, s in penalized.items()}
        # Anti-collision (step 5)
        if anti_collision:
            penalized = self.apply_anti_collision(penalized)

        hard_excluded = {n for n in range(self.cfg.num_min, self.cfg.num_max + 1)
                         if penalized.get(n, 0) == 0.0 and n not in forced_set}

        temperature = self.cfg.temperature_by_mode.get(mode, 1.3)
        noise_factor = self.cfg.noise_by_mode.get(mode, self.cfg.noise_factor)

        nb_to_draw = self.cfg.num_count - len(forced_nums)

        # V104: use zone-stratified draw when zones configured and no forced numbers
        use_stratified = bool(self.cfg.zones) and not forced_nums

        # Wildcard: reserve 1 slot for a cold number if enabled and slots available
        # Disabled in stratified mode (zone 5 already guarantees high/cold numbers)
        use_wildcard = (
            self.cfg.wildcard_enabled
            and nb_to_draw >= 2
            and not use_stratified
        )
        normal_draw_count = (nb_to_draw - 1) if use_wildcard else nb_to_draw

        meilleure_grille = None
        meilleur_score = 0

        for _ in range(self.cfg.max_tentatives):
            # Step 4b: fresh noise per attempt (intra-session diversification)
            noisy = self.apply_noise(penalized, noise_factor)
            probas = self.normaliser_en_probabilites(noisy, temperature=temperature)

            if use_stratified:
                # V104: 1 number per zone
                numeros = self._draw_stratified(probas, forced_set, hard_excluded, exclusions)
            else:
                # Legacy global draw (used when forced_nums or zones not configured)
                disponibles = [n for n in range(self.cfg.num_min, self.cfg.num_max + 1)
                               if n not in forced_set and n not in hard_excluded]
                disponibles = self._apply_exclusions(disponibles, exclusions)
                if len(disponibles) < nb_to_draw:
                    disponibles = [n for n in range(self.cfg.num_min, self.cfg.num_max + 1)
                                   if n not in forced_set]
                p_list = [probas[n] for n in disponibles]

                numeros = list(forced_nums)
                drawn_set = set(forced_nums)
                # Weighted sampling without replacement
                for _ in range(normal_draw_count):
                    num = random.choices(disponibles, weights=p_list, k=1)[0]
                    numeros.append(num)
                    drawn_set.add(num)
                    idx = disponibles.index(num)
                    disponibles.pop(idx)
                    p_list.pop(idx)

                # Step 7b: wildcard cold slot
                if use_wildcard:
                    excl_set = set(exclusions.get("exclude_nums", [])) if exclusions else set()
                    wc = self._select_wildcard(noisy, drawn_set | hard_excluded | excl_set)
                    if wc is not None and wc not in drawn_set:
                        numeros.append(wc)
                    else:
                        if disponibles and p_list:
                            num = random.choices(disponibles, weights=p_list, k=1)[0]
                            numeros.append(num)
                        elif disponibles:
                            numeros.append(random.choice(disponibles))
                        else:
                            remaining = [n for n in range(self.cfg.num_min, self.cfg.num_max + 1)
                                         if n not in drawn_set]
                            if remaining:
                                numeros.append(random.choice(remaining))

            numeros = sorted(numeros)
            conf = self.valider_contraintes(numeros)
            # V107: ESI filter — reject over-regular or clustered grids
            _esi_ok = validate_esi(
                numeros, self.cfg.num_max,
                self.cfg.esi_min, self.cfg.esi_max,
            )
            # Grid quality: conformity score, penalized if ESI fails
            _effective_conf = conf if _esi_ok else conf * 0.5
            if meilleure_grille is None or _effective_conf > meilleur_score:
                meilleure_grille = numeros
                meilleur_score = _effective_conf
            if conf >= self.cfg.min_conformite and _esi_ok:
                break

        numeros = meilleure_grille
        score_conformite = meilleur_score

        # Secondary numbers
        if len(forced_secondary) >= self.cfg.secondary_count:
            secondary = sorted(forced_secondary[:self.cfg.secondary_count])
        elif forced_secondary:
            all_sec = await self.generer_secondary(
                conn, mode=mode, recent_draws=recent_draws, anti_collision=anti_collision,
                decay_state_secondary=decay_state_secondary,
                saturated_secondary=saturated_secondary,
                persistent_brake_map_secondary=persistent_brake_map_secondary,
            )
            secondary = list(forced_secondary)
            for s in all_sec:
                if s not in secondary and len(secondary) < self.cfg.secondary_count:
                    secondary.append(s)
            secondary = sorted(secondary)
        else:
            secondary = await self.generer_secondary(
                conn, mode=mode, recent_draws=recent_draws, anti_collision=anti_collision,
                decay_state_secondary=decay_state_secondary,
                saturated_secondary=saturated_secondary,
                persistent_brake_map_secondary=persistent_brake_map_secondary,
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
        badges.append(b[self.cfg.badge_key])
        return badges

    # ── Window health check ──────────────────────────────────────────

    async def _check_degraded_windows(
        self, conn, nb_tirages: int, date_min, date_max,
    ) -> list[dict]:
        """Check if time windows have sufficient data (<50% of expected draws).

        Returns a list of degraded window descriptors (empty if all healthy).
        Uses the actual draws-per-year rate from DB to estimate expected counts.
        """
        if not date_min or not date_max or nb_tirages == 0:
            return []

        from datetime import date as _date
        d_min = date_min if isinstance(date_min, _date) else _date.fromisoformat(str(date_min))
        d_max = date_max if isinstance(date_max, _date) else _date.fromisoformat(str(date_max))
        span_days = (d_max - d_min).days
        if span_days <= 0:
            return []

        draws_per_year = nb_tirages / (span_days / 365.25)
        ref = await self.get_reference_date(conn)
        degraded: list[dict] = []
        cursor = await conn.cursor()

        for name, years in [
            ("principale", self.cfg.fenetre_principale_annees),
            ("recente", self.cfg.fenetre_recente_annees),
        ]:
            date_limit = ref - timedelta(days=years * 365.25)
            await cursor.execute(
                f"SELECT COUNT(*) as count FROM {self.cfg.table_name} "
                f"WHERE date_de_tirage >= %s",
                (date_limit.strftime("%Y-%m-%d"),),
            )
            actual = (await cursor.fetchone())["count"]
            expected = int(years * draws_per_year)
            if expected > 0 and actual < expected * 0.5:
                degraded.append({
                    "window": name,
                    "expected": expected,
                    "actual": actual,
                    "impact": f"Less than 50% of expected draws for {years}y window",
                })

        return degraded

    # ── Main API ──────────────────────────────────────────────────────

    _ANTI_COLLISION_NOTES: dict[str, str] = {
        "fr": "Les numéros 1-31 sont sur-sélectionnés (biais calendaire). "
              "Privilégier les numéros au-dessus du seuil maximise l'espérance en cas de jackpot partagé.",
        "en": "Numbers 1-31 are over-selected (calendar bias). "
              "Favoring numbers above the threshold maximizes expected value in case of shared jackpot.",
        "es": "Los números 1-31 están sobre-seleccionados (sesgo de calendario). "
              "Favorecer los números por encima del umbral maximiza el valor esperado en caso de bote compartido.",
        "pt": "Os números 1-31 são sobre-selecionados (viés de calendário). "
              "Favorecer números acima do limiar maximiza o valor esperado em caso de jackpot partilhado.",
        "de": "Die Zahlen 1-31 werden überproportional gewählt (Kalender-Bias). "
              "Zahlen über der Schwelle bevorzugen maximiert den Erwartungswert bei geteiltem Jackpot.",
        "nl": "De nummers 1-31 worden oververtegenwoordigd gekozen (kalender-bias). "
              "Nummers boven de drempel bevoordelen maximaliseert de verwachte waarde bij gedeeld jackpot.",
    }

    async def generate_grids(
        self, n: int = 5, mode: str = "balanced", lang: str = "fr",
        anti_collision: bool = False,
        forced_nums: list[int] | None = None,
        forced_secondary: list[int] | None = None,
        exclusions: dict | None = None,
        decay_state: dict[int, int] | None = None,
        persistent_brake_map: dict[int, float] | None = None,
        persistent_brake_map_secondary: dict[int, float] | None = None,
        _get_connection=None,
    ) -> dict:
        if _get_connection is None:
            from .db import get_connection as _get_connection

        if decay_state is None and self.cfg.decay_enabled:
            logger.debug("generate_grids: decay_enabled but no decay_state provided — skipping decay")

        async with _get_connection() as conn:
            scores_hybrides = await self.calculer_scores_hybrides(conn, mode=mode)
            recent_draws = await self.get_recent_draws(conn)

            # V92: load secondary decay state (stars/chance) for rotation
            decay_state_secondary = None
            if self.cfg.decay_enabled and decay_state is not None:
                try:
                    game_name = "euromillions" if self.cfg.game == "em" else "loto"
                    ntype = "star" if self.cfg.game == "em" else "chance"
                    decay_state_secondary = await get_decay_state(conn, game_name, ntype)
                except Exception:
                    logger.debug("decay_state_secondary unavailable — generating without secondary decay")

            grilles = []
            # V105: Saturation Brake — accumulate selected numbers across batch
            _saturated_balls: set[int] = set()
            _saturated_secondary: set[int] = set()
            for _ in range(n):
                grille = await self.generer_grille(
                    conn, scores_hybrides, mode=mode,
                    anti_collision=anti_collision,
                    forced_nums=forced_nums, forced_secondary=forced_secondary,
                    exclusions=exclusions, recent_draws=recent_draws, lang=lang,
                    decay_state=decay_state,
                    decay_state_secondary=decay_state_secondary,
                    saturated_balls=_saturated_balls if _saturated_balls else None,
                    saturated_secondary=_saturated_secondary if _saturated_secondary else None,
                    persistent_brake_map=persistent_brake_map,
                    persistent_brake_map_secondary=persistent_brake_map_secondary,
                )
                grilles.append(grille)
                # Accumulate for next grid in batch
                _saturated_balls.update(grille['nums'])
                _sec = grille.get(self.cfg.secondary_name)
                if isinstance(_sec, list):
                    _saturated_secondary.update(_sec)
                elif _sec is not None:
                    _saturated_secondary.add(_sec)

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

            # Real 3-window weights: principale/recente/globale — generated from config.
            weights = self.cfg.modes.get(mode, self.cfg.modes['balanced'])
            ponderation = '/'.join(str(int(w * 100)) for w in weights)

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
                    'note': self._ANTI_COLLISION_NOTES.get(lang, self._ANTI_COLLISION_NOTES['fr']),
                },
                'temperature': self.cfg.temperature_by_mode.get(mode, 1.3),
                'decay': {
                    'enabled': self.cfg.decay_enabled,
                    'active': decay_state is not None and len(decay_state) > 0,
                    'rate': self.cfg.decay_rate,
                    'rate_secondary': self.cfg.decay_rate_secondary,
                    'acceleration': self.cfg.decay_acceleration,
                    'floor': self.cfg.decay_floor,
                },
                'persistent_brake': {
                    'enabled': self.cfg.saturation_persistent_enabled,
                    'active_balls': bool(persistent_brake_map),
                    'active_secondary': bool(persistent_brake_map_secondary),
                    't1_multiplier': self.cfg.saturation_brake_persistent_t1,
                    't2_multiplier': self.cfg.saturation_brake_persistent_t2,
                    'window': self.cfg.saturation_persistent_window,
                },
                'degraded_windows': await self._check_degraded_windows(
                    conn, nb_tirages, date_min, date_max,
                ),
            }

            return {'grids': grilles, 'metadata': metadata}
