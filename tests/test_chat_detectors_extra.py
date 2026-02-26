"""
Tests supplementaires pour services/chat_detectors.py.
Couvre les fonctions non testees dans test_insult_oor.py :
_detect_grille, _detect_mode, _detect_requete_complexe,
_detect_prochain_tirage, _is_short_continuation.
"""

from services.chat_detectors import (
    _detect_grille, _detect_mode, _detect_requete_complexe,
    _detect_prochain_tirage, _is_short_continuation,
)


# ═══════════════════════════════════════════════════════════════════════
# _detect_grille
# ═══════════════════════════════════════════════════════════════════════

class TestDetectGrille:

    def test_five_numbers(self):
        nums, chance = _detect_grille("5 12 23 34 45")
        assert nums == [5, 12, 23, 34, 45]
        assert chance is None

    def test_with_chance_keyword(self):
        nums, chance = _detect_grille("5 12 23 34 45 chance 7")
        assert nums == [5, 12, 23, 34, 45]
        assert chance == 7

    def test_with_plus_notation(self):
        nums, chance = _detect_grille("5 12 23 34 45 + 3")
        assert nums == [5, 12, 23, 34, 45]
        assert chance == 3

    def test_four_numbers_returns_none(self):
        nums, chance = _detect_grille("5 12 23 34")
        assert nums is None
        assert chance is None

    def test_six_numbers_returns_none(self):
        nums, chance = _detect_grille("5 12 23 34 45 46")
        assert nums is None
        assert chance is None

    def test_duplicates_collapsed(self):
        """Doublons elimines → moins de 5 uniques → None."""
        nums, chance = _detect_grille("5 12 23 5 12")
        assert nums is None
        assert chance is None

    def test_chance_out_of_range_pollutes_nums(self):
        """Chance hors range (15) reste dans le texte → 6 nums → None."""
        nums, chance = _detect_grille("5 12 23 34 45 chance 15")
        assert nums is None


# ═══════════════════════════════════════════════════════════════════════
# _detect_mode
# ═══════════════════════════════════════════════════════════════════════

class TestDetectMode:

    def test_meta_keyword(self):
        assert _detect_mode("quel algorithme utilises-tu ?", "accueil") == "meta"

    def test_meta_ponderation(self):
        assert _detect_mode("explique la pondération", "accueil") == "meta"

    def test_analyse_page_simulateur(self):
        assert _detect_mode("donne-moi une grille", "simulateur") == "analyse"

    def test_analyse_page_statistiques(self):
        assert _detect_mode("stats du 7", "statistiques") == "analyse"

    def test_decouverte_default(self):
        assert _detect_mode("bonjour", "accueil") == "decouverte"


# ═══════════════════════════════════════════════════════════════════════
# _detect_requete_complexe
# ═══════════════════════════════════════════════════════════════════════

class TestDetectRequeteComplexe:

    def test_comparaison(self):
        result = _detect_requete_complexe("compare le 7 et le 23")
        assert result is not None
        assert result["type"] == "comparaison"
        assert result["num1"] == 7
        assert result["num2"] == 23

    def test_comparaison_vs(self):
        result = _detect_requete_complexe("7 vs 14")
        assert result is not None
        assert result["type"] == "comparaison"

    def test_classement_top5(self):
        result = _detect_requete_complexe("top 5 des numeros les plus frequents")
        assert result is not None
        assert result["type"] == "classement"
        assert result["tri"] == "frequence_desc"
        assert result["limit"] == 5

    def test_classement_ecart(self):
        result = _detect_requete_complexe("quels numeros ont le plus gros ecart")
        assert result is not None
        assert result["type"] == "classement"
        assert result["tri"] == "ecart_desc"

    def test_categorie_chaud(self):
        result = _detect_requete_complexe("quels numeros sont chauds en ce moment")
        assert result is not None
        assert result["type"] == "categorie"
        assert result["categorie"] == "chaud"

    def test_categorie_froid(self):
        result = _detect_requete_complexe("quels numeros sont froids actuellement")
        assert result is not None
        assert result["type"] == "categorie"
        assert result["categorie"] == "froid"

    def test_no_match_returns_none(self):
        assert _detect_requete_complexe("bonjour comment ca va") is None


# ═══════════════════════════════════════════════════════════════════════
# _detect_prochain_tirage
# ═══════════════════════════════════════════════════════════════════════

class TestDetectProchainTirage:

    def test_detected(self):
        assert _detect_prochain_tirage("c'est quand le prochain tirage ?") is True

    def test_detected_quand(self):
        assert _detect_prochain_tirage("quand a lieu le prochain loto") is True

    def test_not_detected(self):
        assert _detect_prochain_tirage("donne-moi les stats du 7") is False


# ═══════════════════════════════════════════════════════════════════════
# _is_short_continuation
# ═══════════════════════════════════════════════════════════════════════

class TestIsShortContinuation:

    def test_oui_detected(self):
        assert _is_short_continuation("oui") is True

    def test_vas_y_detected(self):
        assert _is_short_continuation("vas-y !") is True

    def test_long_message_not_detected(self):
        msg = "Quelle est la frequence du numero 7 sur les deux dernieres annees ?"
        assert _is_short_continuation(msg) is False

    def test_empty_not_detected(self):
        assert _is_short_continuation("") is False
