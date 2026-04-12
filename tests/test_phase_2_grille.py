"""
Tests F05 V98 — Phase 2: detection de grille soumise par l'utilisateur.

Loto: 5 numéros (1-49) + chance optionnel (1-10)
EM:   5 numéros (1-50) + 2 étoiles optionnelles (1-12)
"""

import pytest

from services.chat_detectors import _detect_grille
from services.chat_detectors_em_intent import _detect_grille_em


# ═══════════════════════════════════════════════════════
# Loto — _detect_grille
# ═══════════════════════════════════════════════════════

class TestDetectGrilleLoto:
    """Phase 2 Loto: détection de 5 numéros + chance optionnel."""

    def test_valid_5_numbers(self):
        nums, chance = _detect_grille("1 12 23 34 45")
        assert nums == [1, 12, 23, 34, 45]
        assert chance is None

    def test_valid_5_numbers_with_chance(self):
        nums, chance = _detect_grille("3 15 27 38 49 chance 7")
        assert nums == [3, 15, 27, 38, 49]
        assert chance == 7

    def test_invalid_4_numbers(self):
        nums, chance = _detect_grille("1 12 23 34")
        assert nums is None

    def test_invalid_6_numbers(self):
        nums, chance = _detect_grille("1 12 23 34 45 47")
        # 6 unique valid numbers → not exactly 5 → None
        assert nums is None

    def test_with_text_around(self):
        nums, chance = _detect_grille("analyse ma grille 5 12 23 34 49")
        assert nums == [5, 12, 23, 34, 49]

    def test_separators_comma(self):
        nums, chance = _detect_grille("5, 12, 23, 34, 49")
        assert nums == [5, 12, 23, 34, 49]

    def test_separators_dash(self):
        nums, chance = _detect_grille("5-12-23-34-49")
        assert nums == [5, 12, 23, 34, 49]

    def test_duplicate_numbers_ignored(self):
        """Duplicates are removed; if <5 unique → None."""
        nums, chance = _detect_grille("5 5 12 23 34")
        assert nums is None  # only 4 unique

    def test_out_of_range_50(self):
        """Number >49 is filtered out for Loto."""
        nums, chance = _detect_grille("5 12 23 34 50")
        assert nums is None  # 50 is invalid, only 4 valid

    def test_chance_plus_notation(self):
        """Chance via + notation."""
        nums, chance = _detect_grille("5 12 23 34 49 + 3")
        assert nums == [5, 12, 23, 34, 49]
        assert chance == 3

    def test_chance_out_of_range(self):
        """Chance >10 is not captured; the value stays in text as a 6th number → None."""
        nums, chance = _detect_grille("5 12 23 34 49 chance 15")
        # 15 stays in text → 6 valid numbers → not exactly 5 → None
        assert nums is None


# ═══════════════════════════════════════════════════════
# EuroMillions — _detect_grille_em
# ═══════════════════════════════════════════════════════

class TestDetectGrilleEM:
    """Phase 2 EM: détection de 5 numéros (1-50) + 2 étoiles (1-12)."""

    def test_valid_5_numbers_no_stars(self):
        nums, etoiles = _detect_grille_em("3 15 27 38 50")
        assert nums == [3, 15, 27, 38, 50]
        assert etoiles is None

    def test_valid_5_numbers_2_stars(self):
        nums, etoiles = _detect_grille_em("3 15 27 38 50 étoiles 5 11")
        assert nums == [3, 15, 27, 38, 50]
        assert etoiles == [5, 11]

    def test_unicode_stars(self):
        """Unicode star notation ★."""
        nums, etoiles = _detect_grille_em("3 15 27 38 50 ★5-11")
        assert nums == [3, 15, 27, 38, 50]
        assert etoiles == [5, 11]

    def test_star_emoji(self):
        """Star emoji ⭐."""
        nums, etoiles = _detect_grille_em("3 15 27 38 50 ⭐5-11⭐")
        assert nums == [3, 15, 27, 38, 50]
        assert etoiles == [5, 11]

    def test_plus_notation_stars(self):
        nums, etoiles = _detect_grille_em("3 15 27 38 50 + 5 11")
        assert nums == [3, 15, 27, 38, 50]
        assert etoiles == [5, 11]

    def test_invalid_4_numbers(self):
        nums, etoiles = _detect_grille_em("3 15 27 38")
        assert nums is None

    def test_out_of_range_51(self):
        """Number >50 is filtered for EM."""
        nums, etoiles = _detect_grille_em("3 15 27 38 51")
        assert nums is None

    def test_star_out_of_range_13(self):
        """Star pair with one >12 → pair extraction fails, values stay in text → too many numbers."""
        nums, etoiles = _detect_grille_em("3 15 27 38 50 étoiles 5 13")
        # 5 and 13 stay in text → 7 valid numbers → not exactly 5 → None
        assert nums is None

    def test_with_text_around(self):
        nums, etoiles = _detect_grille_em("voici ma grille 3 15 27 38 50")
        assert nums == [3, 15, 27, 38, 50]

    def test_single_star(self):
        """Only 1 star provided — fallback to single."""
        nums, etoiles = _detect_grille_em("3 15 27 38 50 étoile 7")
        assert nums == [3, 15, 27, 38, 50]
        assert etoiles == [7]

    def test_separators_comma(self):
        nums, etoiles = _detect_grille_em("3, 15, 27, 38, 50")
        assert nums == [3, 15, 27, 38, 50]
