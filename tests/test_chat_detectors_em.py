"""
Tests unitaires pour services/chat_detectors_em.py.
Couvre les detecteurs EM, response pools et OOR.
"""

from types import SimpleNamespace

from services.chat_detectors_em import (
    _detect_mode_em, _detect_prochain_tirage_em,
    _detect_numero_em, _detect_grille_em,
    _detect_requete_complexe_em, _detect_out_of_range_em,
    _count_oor_streak_em, _get_oor_response_em,
    _get_insult_response_em, _get_insult_short_em, _get_menace_response_em,
    _get_compliment_response_em,
    _INSULT_L1_EM, _INSULT_L2_EM, _INSULT_L3_EM, _INSULT_L4_EM,
    _INSULT_SHORT_EM, _MENACE_RESPONSES_EM,
    _COMPLIMENT_L1_EM, _COMPLIMENT_L2_EM, _COMPLIMENT_L3_EM,
    _COMPLIMENT_LOVE_EM, _COMPLIMENT_MERCI_EM,
    _OOR_L1_EM, _OOR_ETOILE_EM,
)


def _msg(role, content):
    return SimpleNamespace(role=role, content=content)


# ═══════════════════════════════════════════════════════════════════════
# _detect_mode_em
# ═══════════════════════════════════════════════════════════════════════

class TestDetectModeEM:

    def test_meta_keyword(self):
        assert _detect_mode_em("quel algorithme utilises-tu ?", "accueil-em") == "meta"

    def test_meta_ponderation(self):
        assert _detect_mode_em("explique la pondération", "accueil-em") == "meta"

    def test_analyse_page_euromillions(self):
        assert _detect_mode_em("donne-moi une grille", "euromillions") == "analyse"

    def test_analyse_page_simulateur_em(self):
        assert _detect_mode_em("stats du 7", "simulateur-em") == "analyse"

    def test_analyse_page_statistiques_em(self):
        assert _detect_mode_em("bonjour", "statistiques-em") == "analyse"

    def test_decouverte_default(self):
        assert _detect_mode_em("bonjour", "accueil-em") == "decouverte"


# ═══════════════════════════════════════════════════════════════════════
# _detect_prochain_tirage_em
# ═══════════════════════════════════════════════════════════════════════

class TestDetectProchainTirageEM:

    def test_detected(self):
        assert _detect_prochain_tirage_em("c'est quand le prochain tirage ?") is True

    def test_detected_euromillions(self):
        assert _detect_prochain_tirage_em("quand a lieu le prochain euromillions") is True

    def test_not_detected(self):
        assert _detect_prochain_tirage_em("donne-moi les stats du 7") is False


# ═══════════════════════════════════════════════════════════════════════
# _detect_numero_em
# ═══════════════════════════════════════════════════════════════════════

class TestDetectNumeroEM:

    def test_etoile(self):
        num, typ = _detect_numero_em("étoile 5")
        assert num == 5
        assert typ == "etoile"

    def test_boule(self):
        num, typ = _detect_numero_em("le numéro 23")
        assert num == 23
        assert typ == "boule"

    def test_boule_50(self):
        """50 est valide pour EM (vs 49 pour Loto)."""
        num, typ = _detect_numero_em("le 50?")
        assert num == 50
        assert typ == "boule"

    def test_etoile_out_of_range_returns_none(self):
        """Etoile 13 hors range → None."""
        num, typ = _detect_numero_em("étoile 13")
        assert num is None

    def test_none_for_text(self):
        num, typ = _detect_numero_em("bonjour comment ca va")
        assert num is None
        assert typ is None


# ═══════════════════════════════════════════════════════════════════════
# _detect_grille_em
# ═══════════════════════════════════════════════════════════════════════

class TestDetectGrilleEM:

    def test_five_numbers(self):
        nums, etoiles = _detect_grille_em("5 12 23 34 45")
        assert nums == [5, 12, 23, 34, 45]
        assert etoiles is None

    def test_with_etoiles_keyword(self):
        nums, etoiles = _detect_grille_em("5 12 23 34 45 étoiles 3 9")
        assert nums == [5, 12, 23, 34, 45]
        assert etoiles == [3, 9]

    def test_with_star_notation(self):
        nums, etoiles = _detect_grille_em("5 12 23 34 45 * 3 9")
        assert nums == [5, 12, 23, 34, 45]
        assert etoiles == [3, 9]

    def test_four_numbers_returns_none(self):
        nums, etoiles = _detect_grille_em("5 12 23 34")
        assert nums is None
        assert etoiles is None

    def test_duplicates_collapsed(self):
        """Doublons elimines → moins de 5 uniques → None."""
        nums, etoiles = _detect_grille_em("5 12 23 5 12")
        assert nums is None
        assert etoiles is None

    def test_number_50_valid(self):
        """50 est valide pour EM (vs Loto max 49)."""
        nums, etoiles = _detect_grille_em("10 20 30 40 50")
        assert nums == [10, 20, 30, 40, 50]


# ═══════════════════════════════════════════════════════════════════════
# _detect_requete_complexe_em
# ═══════════════════════════════════════════════════════════════════════

class TestDetectRequeteComplexeEM:

    def test_comparaison(self):
        result = _detect_requete_complexe_em("compare le 7 et le 23")
        assert result is not None
        assert result["type"] == "comparaison"
        assert result["num1"] == 7
        assert result["num2"] == 23
        assert result["num_type"] == "boule"

    def test_comparaison_etoile(self):
        result = _detect_requete_complexe_em("compare le 3 et le 9 étoile")
        assert result is not None
        assert result["num_type"] == "etoile"

    def test_classement_top5(self):
        result = _detect_requete_complexe_em("top 5 des numeros les plus frequents")
        assert result is not None
        assert result["type"] == "classement"
        assert result["tri"] == "frequence_desc"
        assert result["limit"] == 5

    def test_classement_ecart(self):
        result = _detect_requete_complexe_em("quels numeros ont le plus gros ecart")
        assert result is not None
        assert result["type"] == "classement"
        assert result["tri"] == "ecart_desc"

    def test_categorie_chaud(self):
        result = _detect_requete_complexe_em("quels numeros sont chauds en ce moment")
        assert result is not None
        assert result["type"] == "categorie"
        assert result["categorie"] == "chaud"

    def test_categorie_froid(self):
        result = _detect_requete_complexe_em("quels numeros sont froids actuellement")
        assert result is not None
        assert result["type"] == "categorie"
        assert result["categorie"] == "froid"

    def test_no_match_returns_none(self):
        assert _detect_requete_complexe_em("bonjour comment ca va") is None


# ═══════════════════════════════════════════════════════════════════════
# _detect_out_of_range_em
# ═══════════════════════════════════════════════════════════════════════

class TestDetectOutOfRangeEM:

    def test_etoile_high(self):
        num, ctx = _detect_out_of_range_em("étoile 15")
        assert num == 15
        assert ctx == "etoile_high"

    def test_boule_high(self):
        num, ctx = _detect_out_of_range_em("le numéro 99?")
        assert num == 99
        assert ctx == "boule_high"

    def test_close(self):
        num, ctx = _detect_out_of_range_em("le 51?")
        assert num == 51
        assert ctx == "close"

    def test_zero_neg(self):
        num, ctx = _detect_out_of_range_em("le numéro 0?")
        assert num == 0
        assert ctx == "zero_neg"

    def test_valid_range_returns_none(self):
        num, ctx = _detect_out_of_range_em("le numéro 25?")
        assert num is None
        assert ctx is None


# ═══════════════════════════════════════════════════════════════════════
# _count_oor_streak_em
# ═══════════════════════════════════════════════════════════════════════

class TestCountOorStreakEM:

    def test_no_history(self):
        assert _count_oor_streak_em([]) == 0

    def test_one_oor(self):
        history = [_msg("user", "le numéro 99?")]
        assert _count_oor_streak_em(history) == 1

    def test_streak_broken(self):
        history = [
            _msg("user", "le numéro 99?"),
            _msg("assistant", "hors range"),
            _msg("user", "le numéro 25?"),  # valid → breaks streak
        ]
        assert _count_oor_streak_em(history) == 0


# ═══════════════════════════════════════════════════════════════════════
# Response pools — insult
# ═══════════════════════════════════════════════════════════════════════

class TestInsultResponseEM:

    def test_streak_0_uses_l1(self):
        resp = _get_insult_response_em(0, [])
        assert resp in _INSULT_L1_EM

    def test_streak_1_uses_l2(self):
        resp = _get_insult_response_em(1, [])
        assert resp in _INSULT_L2_EM

    def test_streak_2_uses_l3(self):
        resp = _get_insult_response_em(2, [])
        assert resp in _INSULT_L3_EM

    def test_streak_3_uses_l4(self):
        resp = _get_insult_response_em(3, [])
        assert resp in _INSULT_L4_EM

    def test_short_returns_pool(self):
        resp = _get_insult_short_em()
        assert resp in _INSULT_SHORT_EM

    def test_menace_returns_pool(self):
        resp = _get_menace_response_em()
        assert resp in _MENACE_RESPONSES_EM


# ═══════════════════════════════════════════════════════════════════════
# Response pools — compliment
# ═══════════════════════════════════════════════════════════════════════

class TestComplimentResponseEM:

    def test_streak_0_uses_l1(self):
        resp = _get_compliment_response_em("compliment", 0)
        assert resp in _COMPLIMENT_L1_EM

    def test_streak_2_uses_l2(self):
        resp = _get_compliment_response_em("compliment", 2)
        assert resp in _COMPLIMENT_L2_EM

    def test_streak_3_uses_l3(self):
        resp = _get_compliment_response_em("compliment", 3)
        assert resp in _COMPLIMENT_L3_EM

    def test_love_type(self):
        resp = _get_compliment_response_em("love", 0)
        assert resp in _COMPLIMENT_LOVE_EM

    def test_merci_type(self):
        resp = _get_compliment_response_em("merci", 0)
        assert resp in _COMPLIMENT_MERCI_EM


# ═══════════════════════════════════════════════════════════════════════
# Response pools — OOR
# ═══════════════════════════════════════════════════════════════════════

class TestOorResponseEM:

    def test_boule_high_format(self):
        resp = _get_oor_response_em(99, "boule_high", 0)
        assert "99" in resp

    def test_etoile_high_format(self):
        resp = _get_oor_response_em(15, "etoile_high", 0)
        assert "15" in resp

    def test_close_format(self):
        resp = _get_oor_response_em(51, "close", 0)
        assert "51" in resp

    def test_zero_neg_format(self):
        resp = _get_oor_response_em(0, "zero_neg", 0)
        assert "0" in resp
