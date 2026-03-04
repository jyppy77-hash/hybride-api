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

    # --- Top N extraction multilingual ---

    def test_top_10_en(self):
        """EN: 'give me the top 10 most frequent' → limit=10."""
        r = _detect_requete_complexe_em("Give me the top 10 most frequent numbers")
        assert r is not None
        assert r["limit"] == 10

    def test_top_7_pt(self):
        """PT: 'top 7' → limit=7."""
        r = _detect_requete_complexe_em("top 7 dos numeros les plus frequents")
        assert r is not None
        assert r["limit"] == 7

    def test_default_limit_no_number(self):
        """Sans nombre → limit=5 par défaut (non-régression)."""
        r = _detect_requete_complexe_em("quels numeros sont les plus frequents")
        assert r is not None
        assert r["limit"] == 5

    # --- ecart_desc multilingual ---

    def test_ecart_desc_pt_maior_atraso(self):
        """PT: 'maior atraso' → ecart_desc."""
        r = _detect_requete_complexe_em(
            "Qual número tem o maior atraso atual desde o seu último sorteio EuroMillions ?"
        )
        assert r is not None
        assert r["tri"] == "ecart_desc"

    def test_ecart_desc_en_largest_gap(self):
        """EN: 'largest gap' → ecart_desc."""
        r = _detect_requete_complexe_em("Which number has the largest gap?")
        assert r is not None
        assert r["tri"] == "ecart_desc"

    def test_ecart_desc_es_mayor_retraso(self):
        """ES: 'mayor retraso' → ecart_desc."""
        r = _detect_requete_complexe_em("¿Qué número tiene el mayor retraso?")
        assert r is not None
        assert r["tri"] == "ecart_desc"

    def test_ecart_desc_de_groesster_abstand(self):
        """DE: 'größter Abstand' → ecart_desc."""
        r = _detect_requete_complexe_em("Welche Zahl hat den größten Abstand?")
        assert r is not None
        assert r["tri"] == "ecart_desc"

    def test_ecart_desc_nl_grootste_achterstand(self):
        """NL: 'grootste achterstand' → ecart_desc."""
        r = _detect_requete_complexe_em("Welk nummer heeft de grootste achterstand?")
        assert r is not None
        assert r["tri"] == "ecart_desc"

    # --- ecart_asc multilingual ---

    def test_ecart_asc_en_smallest_gap(self):
        """EN: 'smallest gap' → ecart_asc."""
        r = _detect_requete_complexe_em("Which number has the smallest gap?")
        assert r is not None
        assert r["tri"] == "ecart_asc"

    def test_ecart_asc_pt_menor_atraso(self):
        """PT: 'menor atraso' → ecart_asc."""
        r = _detect_requete_complexe_em("Qual número tem o menor atraso?")
        assert r is not None
        assert r["tri"] == "ecart_asc"

    def test_ecart_asc_es_menor_retraso(self):
        """ES: 'menor retraso' → ecart_asc."""
        r = _detect_requete_complexe_em("¿Qué número tiene el menor retraso?")
        assert r is not None
        assert r["tri"] == "ecart_asc"

    def test_ecart_asc_de_kleinster_abstand(self):
        """DE: 'kleinster Abstand' → ecart_asc."""
        r = _detect_requete_complexe_em("Welche Zahl hat den kleinsten Abstand?")
        assert r is not None
        assert r["tri"] == "ecart_asc"

    def test_ecart_asc_nl_kleinste_achterstand(self):
        """NL: 'kleinste achterstand' → ecart_asc."""
        r = _detect_requete_complexe_em("Welk nummer heeft de kleinste achterstand?")
        assert r is not None
        assert r["tri"] == "ecart_asc"


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

# ═══════════════════════════════════════════════════════════════════════
# Phase T — Neutralisation par mots statistiques (EM, shared _detect_tirage)
# ═══════════════════════════════════════════════════════════════════════

from services.chat_detectors import _detect_tirage


class TestPhaseTNeutralize:
    """Statistical words must prevent Phase T from firing."""

    def test_ecart_depuis_dernier_tirage_em_fr(self):
        """FR: 'écart depuis son dernier tirage EuroMillions' → Phase T NOT triggered."""
        result = _detect_tirage(
            "Quel numéro a le plus grand écart actuel depuis son dernier tirage EuroMillions ?"
        )
        assert result is None

    def test_dernier_tirage_simple_still_works(self):
        """Non-regression: 'quel était le dernier tirage' → Phase T triggered."""
        result = _detect_tirage("Quel était le dernier tirage ?")
        assert result == "latest"

    def test_gap_since_last_draw_en(self):
        """EN: 'gap since its last draw' → Phase T NOT triggered."""
        result = _detect_tirage(
            "Which number has the largest gap since its last draw?"
        )
        assert result is None

    def test_frequency_tirage_neutralise(self):
        """FR: 'fréquence' neutralise Phase T."""
        result = _detect_tirage("fréquence des numéros au dernier tirage EuroMillions")
        assert result is None

    def test_retraso_sorteo_es(self):
        """ES: 'retraso' neutralise Phase T."""
        result = _detect_tirage("retraso del número desde el último sorteo")
        assert result is None

    def test_atraso_sorteio_pt(self):
        """PT: 'atraso' neutralise Phase T."""
        result = _detect_tirage("atraso do número desde o último sorteio")
        assert result is None

    def test_abstand_ziehung_de(self):
        """DE: 'abstand' neutralise Phase T."""
        result = _detect_tirage("Abstand seit der letzten Ziehung")
        assert result is None

    def test_achterstand_trekking_nl(self):
        """NL: 'achterstand' neutralise Phase T."""
        result = _detect_tirage("achterstand sinds de laatste trekking")
        assert result is None

    def test_resultats_seul_still_works(self):
        """Non-regression: 'résultats' alone → Phase T triggered."""
        result = _detect_tirage("résultats")
        assert result == "latest"

    # --- P3/3: "sorti le plus souvent" → fréquence, PAS tirage ---

    def test_sorti_le_plus_souvent_em(self):
        """FR: 'sorti le plus souvent' → None (fréquence, pas tirage)."""
        assert _detect_tirage("Quel numéro est sorti le plus souvent à l'EuroMillions ?") is None

    def test_en_most_often_em(self):
        """EN: 'most often' → None."""
        assert _detect_tirage("Which EuroMillions number came out most often?") is None

    def test_es_a_menudo_em(self):
        """ES: 'a menudo' → None."""
        assert _detect_tirage("Qué número de EuroMillions salió a menudo?") is None

    def test_pt_frequentemente_em(self):
        """PT: 'frequentemente' → None."""
        assert _detect_tirage("Qual número do EuroMillions saiu mais frequentemente?") is None

    def test_de_haeufig_em(self):
        """DE: 'häufig' → None."""
        assert _detect_tirage("Welche EuroMillions Zahl kam am häufigsten?") is None

    def test_nl_vaakst_em(self):
        """NL: 'vaak' → None."""
        assert _detect_tirage("Welk EuroMillions nummer kwam het vaakst voor?") is None


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
