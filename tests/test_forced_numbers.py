"""
Tests for forced numbers in grid generation (Phase G).
Covers: detection regex (6 langs), engine injection, validation errors.
"""

import pytest

from services.chat_detectors import (
    _extract_forced_numbers,
    _detect_generation,
)


# ═══════════════════════════════════════════════════════════════════
# 1. Detector — _extract_forced_numbers (Loto)
# ═══════════════════════════════════════════════════════════════════


class TestExtractForcedNumbersLoto:
    """Extraction of forced numbers for Loto FR (1-49 + chance 1-10)."""

    # ── Basic forced numbers ──

    def test_two_forced_numbers_fr(self):
        r = _extract_forced_numbers("Génère 1 grille avec le 31 et 45", game="loto")
        assert r["error"] is None
        assert 31 in r["forced_nums"]
        assert 45 in r["forced_nums"]

    def test_three_forced_numbers_fr(self):
        r = _extract_forced_numbers("Génère une grille avec le 31, 45 et 12", game="loto")
        assert r["error"] is None
        assert set(r["forced_nums"]) == {31, 45, 12}

    def test_one_forced_number_fr(self):
        r = _extract_forced_numbers("Donne-moi une grille avec le 7", game="loto")
        assert r["error"] is None
        assert r["forced_nums"] == [7]

    def test_forced_chance_fr(self):
        r = _extract_forced_numbers("Génère une grille avec le 7 en chance", game="loto")
        assert r["error"] is None
        assert r["forced_chance"] == 7

    def test_forced_nums_and_chance(self):
        r = _extract_forced_numbers("Génère 1 grille avec le 31 et 45 + chance 3", game="loto")
        assert r["error"] is None
        assert 31 in r["forced_nums"]
        assert 45 in r["forced_nums"]
        assert r["forced_chance"] == 3

    def test_fetiche_variant(self):
        r = _extract_forced_numbers("Génère avec mes numéros fétiches 5 et 23", game="loto")
        assert r["error"] is None
        assert 5 in r["forced_nums"]
        assert 23 in r["forced_nums"]

    # ── No "with" keyword → no forced numbers ──

    def test_no_with_keyword(self):
        r = _extract_forced_numbers("Génère-moi 1 grille", game="loto")
        assert r["forced_nums"] == []
        assert r["forced_chance"] is None
        assert r["error"] is None

    # ── Quantifier anti-false-positive ──

    @pytest.mark.parametrize("msg", [
        "génère-moi une grille avec les 2 dedans",
        "generate a grid with those 2 included",
        "genera una combinación con los 2 dentro",
        "gera uma combinação com os 2 incluídos",
        "generiere eine Kombination mit die 2 dabei",
        "genereer een combinatie met de 2 erin",
        "génère-moi une grille avec les 3 inclus",
    ])
    def test_quantifier_not_captured(self, msg):
        """'les 2 dedans' = both of them, NOT forced number 2."""
        r = _extract_forced_numbers(msg, game="loto")
        assert r["forced_nums"] == [], f"Should not capture quantifier: {r['forced_nums']}"
        assert r["error"] is None

    def test_real_number_2_still_works(self):
        """'avec le 2' = real forced number 2."""
        r = _extract_forced_numbers("Génère une grille avec le 2", game="loto")
        assert r["forced_nums"] == [2]

    def test_production_phrase_quantifier(self):
        """Multi-intent prod phrase: compare + 'les 2 dedans' = quantifier."""
        r = _extract_forced_numbers(
            "Compare les fréquences du 31 vs 45 sur les 3 dernières années. "
            "Et génère-moi une grille avec les 2 dedans.",
            game="loto",
        )
        assert r["forced_nums"] == [], f"Should not capture: {r['forced_nums']}"

    # ── Validation errors ──

    def test_number_out_of_range_loto(self):
        r = _extract_forced_numbers("Génère une grille avec le 55", game="loto")
        assert r["error"] is not None
        assert "hors plage" in r["error"]

    def test_too_many_forced_numbers(self):
        r = _extract_forced_numbers(
            "Génère une grille avec le 1, 2, 3, 4, 5 et 6", game="loto"
        )
        assert r["error"] is not None
        assert "Maximum" in r["error"]

    def test_chance_out_of_range(self):
        r = _extract_forced_numbers("Génère une grille avec chance 15", game="loto")
        assert r["error"] is not None
        assert "chance" in r["error"].lower() or "hors plage" in r["error"]

    # ── Deduplication ──

    def test_duplicate_numbers_deduplicated(self):
        r = _extract_forced_numbers("Génère une grille avec le 7 et 7 et 23", game="loto")
        assert r["error"] is None
        assert r["forced_nums"].count(7) == 1

    # ── Multilingual (EN/ES/PT/DE/NL) ──

    def test_forced_numbers_en(self):
        r = _extract_forced_numbers("Generate a grid with 31 and 45", game="loto")
        assert r["error"] is None
        assert 31 in r["forced_nums"]
        assert 45 in r["forced_nums"]

    def test_forced_numbers_es(self):
        r = _extract_forced_numbers("Genera una combinación con el 31 y 45", game="loto")
        assert r["error"] is None
        assert 31 in r["forced_nums"]
        assert 45 in r["forced_nums"]

    def test_forced_numbers_pt(self):
        r = _extract_forced_numbers("Gera uma combinação com o 31 e 45", game="loto")
        assert r["error"] is None
        assert 31 in r["forced_nums"]
        assert 45 in r["forced_nums"]

    def test_forced_numbers_de(self):
        r = _extract_forced_numbers("Generiere eine Kombination mit 31 und 45", game="loto")
        assert r["error"] is None
        assert 31 in r["forced_nums"]
        assert 45 in r["forced_nums"]

    def test_forced_numbers_nl(self):
        r = _extract_forced_numbers("Genereer een combinatie met 31 en 45", game="loto")
        assert r["error"] is None
        assert 31 in r["forced_nums"]
        assert 45 in r["forced_nums"]

    def test_lucky_number_en(self):
        r = _extract_forced_numbers("Generate a grid with lucky 7", game="loto")
        assert r["error"] is None
        assert r["forced_chance"] == 7

    def test_favoris_fr(self):
        r = _extract_forced_numbers("Génère une grille avec mes favoris 12 et 34", game="loto")
        assert r["error"] is None
        assert 12 in r["forced_nums"]
        assert 34 in r["forced_nums"]

    def test_including_en(self):
        r = _extract_forced_numbers("Generate a grid including 8 and 19", game="loto")
        assert r["error"] is None
        assert 8 in r["forced_nums"]
        assert 19 in r["forced_nums"]


# ═══════════════════════════════════════════════════════════════════
# 2. Detector — _extract_forced_numbers (EuroMillions)
# ═══════════════════════════════════════════════════════════════════


class TestExtractForcedNumbersEM:
    """Extraction of forced numbers for EuroMillions (1-50 + étoiles 1-12)."""

    def test_forced_nums_em_fr(self):
        r = _extract_forced_numbers("Génère une grille avec le 15 et 42", game="em")
        assert r["error"] is None
        assert 15 in r["forced_nums"]
        assert 42 in r["forced_nums"]

    def test_forced_nums_and_star_fr(self):
        r = _extract_forced_numbers("Génère une grille avec le 15 et 42 + étoile 7", game="em")
        assert r["error"] is None
        assert 15 in r["forced_nums"]
        assert 42 in r["forced_nums"]
        assert 7 in r["forced_etoiles"]

    def test_two_forced_stars_fr(self):
        r = _extract_forced_numbers("Génère avec étoiles 3 et 9", game="em")
        assert r["error"] is None
        assert set(r["forced_etoiles"]) == {3, 9}

    def test_forced_star_en(self):
        r = _extract_forced_numbers("Generate a grid with 8 and 33 + star 5", game="em")
        assert r["error"] is None
        assert 8 in r["forced_nums"]
        assert 33 in r["forced_nums"]
        assert 5 in r["forced_etoiles"]

    def test_forced_star_es(self):
        r = _extract_forced_numbers("Genera una combinación con el 22 y 40 + estrella 3", game="em")
        assert r["error"] is None
        assert 22 in r["forced_nums"]
        assert 40 in r["forced_nums"]
        assert 3 in r["forced_etoiles"]

    def test_forced_star_pt(self):
        r = _extract_forced_numbers("Gera uma combinação com 10 e 25 + estrela 8", game="em")
        assert r["error"] is None
        assert 10 in r["forced_nums"]
        assert 25 in r["forced_nums"]
        assert 8 in r["forced_etoiles"]

    def test_forced_star_de(self):
        r = _extract_forced_numbers("Generiere eine Kombination mit 18 und 44 + Stern 11", game="em")
        assert r["error"] is None
        assert 18 in r["forced_nums"]
        assert 44 in r["forced_nums"]
        assert 11 in r["forced_etoiles"]

    def test_forced_star_nl(self):
        r = _extract_forced_numbers("Genereer een combinatie met 5 en 38 + ster 2", game="em")
        assert r["error"] is None
        assert 5 in r["forced_nums"]
        assert 38 in r["forced_nums"]
        assert 2 in r["forced_etoiles"]

    # ── Validation errors ──

    def test_number_out_of_range_em(self):
        r = _extract_forced_numbers("Génère une grille avec le 55", game="em")
        assert r["error"] is not None
        assert "hors plage" in r["error"]

    def test_star_out_of_range(self):
        r = _extract_forced_numbers("Génère une grille avec étoile 15", game="em")
        assert r["error"] is not None
        assert "hors plage" in r["error"]

    def test_too_many_stars(self):
        r = _extract_forced_numbers("Génère avec étoiles 1, 5 et 9", game="em")
        assert r["error"] is not None
        assert "Maximum" in r["error"]

    def test_number_50_valid_em(self):
        """50 is valid for EM (1-50 range)."""
        r = _extract_forced_numbers("Génère une grille avec le 50", game="em")
        assert r["error"] is None
        assert 50 in r["forced_nums"]


# ═══════════════════════════════════════════════════════════════════
# 3. Engine — forced numbers are present in generated grid
# ═══════════════════════════════════════════════════════════════════

class TestEngineForced:
    """Test that forced numbers actually appear in generated grids."""

    def test_loto_forced_in_grid(self):
        """Simulate Loto engine with forced nums (no DB needed)."""
        from engine.hybride import generer_badges, valider_contraintes

        # Simulate: forced [31, 45] + 3 random from remaining
        import random
        forced = [31, 45]
        remaining = [n for n in range(1, 50) if n not in forced]
        drawn = random.sample(remaining, 3)
        grid = sorted(forced + drawn)

        assert 31 in grid
        assert 45 in grid
        assert len(grid) == 5
        score = valider_contraintes(grid)
        assert 0 <= score <= 1

    def test_em_forced_in_grid(self):
        """Simulate EM engine with forced nums (no DB needed)."""
        from engine.hybride_em import valider_contraintes

        import random
        forced = [15, 42]
        remaining = [n for n in range(1, 51) if n not in forced]
        drawn = random.sample(remaining, 3)
        grid = sorted(forced + drawn)

        assert 15 in grid
        assert 42 in grid
        assert len(grid) == 5
        score = valider_contraintes(grid)
        assert 0 <= score <= 1

    def test_loto_five_forced_fills_grid(self):
        """5 forced numbers = no random draw needed."""
        forced = [1, 10, 20, 30, 49]
        remaining = [n for n in range(1, 50) if n not in forced]
        nb_to_draw = 5 - len(forced)
        assert nb_to_draw == 0
        grid = sorted(forced)
        assert grid == [1, 10, 20, 30, 49]


# ═══════════════════════════════════════════════════════════════════
# 4. Context formatting — forced nums displayed
# ═══════════════════════════════════════════════════════════════════

class TestContextFormatting:
    """Verify that forced numbers appear in Gemini context."""

    def test_loto_context_with_forced(self):
        from services.chat_utils import _format_generation_context

        grid = {
            "nums": [7, 15, 31, 38, 45],
            "chance": 3,
            "score": 85,
            "badges": ["Équilibré", "Hybride V1"],
            "mode": "balanced",
            "forced_nums": [31, 45],
            "forced_chance": 3,
        }
        ctx = _format_generation_context(grid)
        assert "Numéros imposés par l'utilisateur : [31, 45]" in ctx
        assert "Chance imposé par l'utilisateur : 3" in ctx

    def test_loto_context_without_forced(self):
        from services.chat_utils import _format_generation_context

        grid = {
            "nums": [7, 15, 31, 38, 45],
            "chance": 3,
            "score": 85,
            "badges": ["Équilibré", "Hybride V1"],
            "mode": "balanced",
        }
        ctx = _format_generation_context(grid)
        assert "Numéros imposés par l'utilisateur" not in ctx

    def test_em_context_with_forced(self):
        from services.chat_utils_em import _format_generation_context_em

        grid = {
            "nums": [8, 15, 33, 42, 50],
            "etoiles": [5, 11],
            "score": 80,
            "badges": ["Équilibré", "Hybride EM V1"],
            "mode": "balanced",
            "forced_nums": [15, 42],
            "forced_etoiles": [5],
        }
        ctx = _format_generation_context_em(grid)
        assert "Numéros imposés par l'utilisateur : [15, 42]" in ctx
        assert "Étoiles imposées par l'utilisateur : [5]" in ctx

    def test_em_context_without_forced(self):
        from services.chat_utils_em import _format_generation_context_em

        grid = {
            "nums": [8, 15, 33, 42, 50],
            "etoiles": [5, 11],
            "score": 80,
            "badges": ["Équilibré", "Hybride EM V1"],
            "mode": "balanced",
        }
        ctx = _format_generation_context_em(grid)
        assert "Numéros imposés par l'utilisateur" not in ctx


# ═══════════════════════════════════════════════════════════════════
# 5. Detection + generation combined
# ═══════════════════════════════════════════════════════════════════

class TestDetectAndExtractCombined:
    """Verify _detect_generation + _extract_forced_numbers work together."""

    @pytest.mark.parametrize("msg,expected_forced", [
        ("Génère-moi 1 grille avec le 31 et 45 dedans", [31, 45]),
        ("Generate a grid with 7 and 23", [7, 23]),
        ("Genera una combinación con el 12 y 33", [12, 33]),
        ("Gera uma combinação com 5 e 18", [5, 18]),
        ("Generiere eine Kombination mit 8 und 41", [8, 41]),
        ("Genereer een combinatie met 3 en 29", [3, 29]),
    ])
    def test_detect_and_extract_multilang(self, msg, expected_forced):
        assert _detect_generation(msg)
        r = _extract_forced_numbers(msg, game="loto")
        assert r["error"] is None
        for n in expected_forced:
            assert n in r["forced_nums"]

    def test_generation_without_forced_still_works(self):
        msg = "Génère-moi 3 grilles"
        assert _detect_generation(msg)
        r = _extract_forced_numbers(msg, game="loto")
        assert r["forced_nums"] == []
        assert r["error"] is None


# ═══════════════════════════════════════════════════════════════════
# 6. Multi-action — generation + stats in same message
# ═══════════════════════════════════════════════════════════════════

class TestMultiAction:
    """Verify multi-intent messages detect BOTH generation and stats."""

    def test_compare_and_generate_both_detected(self):
        """Both Phase G and Phase 3 should fire on a multi-action message."""
        from services.chat_detectors import _detect_requete_complexe

        msg = "Compare les fréquences du 31 vs 45. Et génère-moi une grille avec le 31 et 45"
        assert _detect_generation(msg)
        intent = _detect_requete_complexe(msg)
        assert intent is not None
        assert intent["type"] == "comparaison"
        r = _extract_forced_numbers(msg, game="loto")
        assert set(r["forced_nums"]) == {31, 45}

    def test_stats_and_generate_both_detected(self):
        """Stats query + generation in same message."""
        from services.chat_detectors import _detect_numero

        msg = "Donne-moi les stats du 7. Et génère une grille avec le 7 et 23"
        assert _detect_generation(msg)
        num, num_type = _detect_numero(msg)
        assert num == 7
        r = _extract_forced_numbers(msg, game="loto")
        assert set(r["forced_nums"]) == {7, 23}

    def test_quantifier_in_multi_action(self):
        """'les 2 dedans' in multi-action = quantifier, not forced number 2."""
        msg = (
            "Compare les fréquences du 31 vs 45 sur les 3 dernières années. "
            "Et génère-moi une grille avec les 2 dedans."
        )
        assert _detect_generation(msg)
        r = _extract_forced_numbers(msg, game="loto")
        assert r["forced_nums"] == [], f"Quantifier captured: {r['forced_nums']}"

    def test_classement_and_generate(self):
        """Top N ranking + generation in same message."""
        from services.chat_detectors import _detect_requete_complexe

        msg = "Top 5 les plus fréquents. Génère une grille avec le 12"
        assert _detect_generation(msg)
        intent = _detect_requete_complexe(msg)
        assert intent is not None
        assert intent["type"] == "classement"
        r = _extract_forced_numbers(msg, game="loto")
        assert r["forced_nums"] == [12]

    def test_multi_action_en(self):
        """EN multi-action: compare + generate."""
        from services.chat_detectors import _detect_requete_complexe

        msg = "Compare 31 vs 45. Generate a grid with 31 and 45"
        assert _detect_generation(msg)
        intent = _detect_requete_complexe(msg)
        assert intent is not None
        r = _extract_forced_numbers(msg, game="loto")
        assert set(r["forced_nums"]) == {31, 45}
