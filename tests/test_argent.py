"""
Tests unitaires pour Phase A — Detection argent / gains / paris.
Couvre la detection FR (Loto), multilingue (EM), les niveaux L1/L2/L3,
la langue de reponse, et la non-regression des phases existantes.
"""

from services.chat_detectors import (
    _detect_argent, _get_argent_response,
    _ARGENT_L1, _ARGENT_L2, _ARGENT_L3,
    _detect_insulte, _detect_compliment, _detect_out_of_range,
)
from services.chat_detectors_em import (
    _detect_argent_em, _get_argent_response_em,
    _ARGENT_L1_EM, _ARGENT_L2_EM, _ARGENT_L3_EM,
    _ARGENT_L1_EM_ES, _ARGENT_L2_EM_ES, _ARGENT_L3_EM_ES,
    _ARGENT_L1_EM_PT, _ARGENT_L2_EM_PT, _ARGENT_L3_EM_PT,
    _ARGENT_L1_EM_DE, _ARGENT_L2_EM_DE, _ARGENT_L3_EM_DE,
    _ARGENT_L1_EM_NL, _ARGENT_L2_EM_NL, _ARGENT_L3_EM_NL,
    _detect_out_of_range_em,
)
from services.chat_responses_em_en import (
    _get_argent_response_em_en,
    _ARGENT_L1_EM_EN, _ARGENT_L2_EM_EN, _ARGENT_L3_EM_EN,
)


# ═══════════════════════════════════════════════════════
# Detection FR (Loto)
# ═══════════════════════════════════════════════════════

class TestDetectArgentFR:

    def test_jackpot(self):
        assert _detect_argent("combien vaut le jackpot") is True

    def test_devenir_riche(self):
        assert _detect_argent("je veux devenir riche") is True

    def test_parier(self):
        assert _detect_argent("je veux parier gros") is True

    def test_argent(self):
        assert _detect_argent("comment gagner de l'argent") is True

    def test_gains(self):
        assert _detect_argent("quels sont les gains possibles") is True

    def test_gros_lot(self):
        assert _detect_argent("comment toucher le gros lot") is True

    def test_cagnotte(self):
        assert _detect_argent("la cagnotte est à combien") is True

    def test_strategie_gagner(self):
        assert _detect_argent("quelle stratégie pour gagner") is True

    def test_fortune(self):
        assert _detect_argent("je veux faire fortune") is True

    def test_miser(self):
        assert _detect_argent("combien miser cette semaine") is True

    def test_pognon(self):
        assert _detect_argent("c'est une question de pognon") is True

    def test_fric(self):
        assert _detect_argent("ça rapporte du fric") is True

    def test_thune(self):
        assert _detect_argent("je veux de la thune") is True

    def test_combien_on_gagne(self):
        assert _detect_argent("combien on gagne au loto") is True

    def test_combien_ca_rapporte(self):
        assert _detect_argent("combien ça rapporte") is True

    # --- Faux positifs (NE DOIVENT PAS declencher) ---

    def test_no_detect_frequence(self):
        assert _detect_argent("quel est le numero le plus frequent") is False

    def test_no_detect_numero_simple(self):
        assert _detect_argent("le numero 7 est sorti 38 fois") is False

    def test_no_detect_stats(self):
        assert _detect_argent("quelle est la frequence du 12") is False

    def test_no_detect_bonjour(self):
        assert _detect_argent("bonjour") is False

    def test_no_detect_tirage(self):
        assert _detect_argent("quand est le prochain tirage") is False

    def test_no_detect_grille(self):
        assert _detect_argent("analyse ma grille 3 12 25 38 47") is False


# ═══════════════════════════════════════════════════════
# Detection EN (EM)
# ═══════════════════════════════════════════════════════

class TestDetectArgentEN:

    def test_how_much_win(self):
        assert _detect_argent_em("how much can I win", "en") is True

    def test_jackpot(self):
        assert _detect_argent_em("what is the jackpot", "en") is True

    def test_get_rich(self):
        assert _detect_argent_em("I want to get rich", "en") is True

    def test_gambling(self):
        assert _detect_argent_em("is this gambling", "en") is True

    def test_money(self):
        assert _detect_argent_em("how much money", "en") is True

    def test_prize(self):
        assert _detect_argent_em("what is the prize", "en") is True

    def test_betting(self):
        assert _detect_argent_em("I like betting", "en") is True

    def test_strategy_to_win(self):
        assert _detect_argent_em("strategy to win the lottery", "en") is True

    def test_no_detect_frequent(self):
        assert _detect_argent_em("what is the most frequent number", "en") is False

    def test_no_detect_hello(self):
        assert _detect_argent_em("hello", "en") is False

    def test_no_detect_stats(self):
        assert _detect_argent_em("show me the statistics", "en") is False


# ═══════════════════════════════════════════════════════
# Detection ES/PT/DE/NL (EM)
# ═══════════════════════════════════════════════════════

class TestDetectArgentMultilang:

    # --- ES ---
    def test_es_cuanto_se_gana(self):
        assert _detect_argent_em("cuanto se gana", "es") is True

    def test_es_dinero(self):
        assert _detect_argent_em("quiero dinero", "es") is True

    def test_es_apostar(self):
        assert _detect_argent_em("quiero apostar", "es") is True

    def test_es_hacerse_rico(self):
        assert _detect_argent_em("quiero hacerse rico", "es") is True

    def test_es_no_detect(self):
        assert _detect_argent_em("cual es el numero mas frecuente", "es") is False

    # --- PT ---
    def test_pt_quanto_se_ganha(self):
        assert _detect_argent_em("quanto se ganha", "pt") is True

    def test_pt_dinheiro(self):
        assert _detect_argent_em("quero dinheiro", "pt") is True

    def test_pt_apostar(self):
        assert _detect_argent_em("quero apostar", "pt") is True

    def test_pt_ficar_rico(self):
        assert _detect_argent_em("quero ficar rico", "pt") is True

    def test_pt_no_detect(self):
        assert _detect_argent_em("qual e o numero mais frequente", "pt") is False

    # --- DE ---
    def test_de_wie_viel_gewinnen(self):
        assert _detect_argent_em("wie viel kann man gewinnen", "de") is True

    def test_de_geld(self):
        assert _detect_argent_em("wie viel geld", "de") is True

    def test_de_wetten(self):
        assert _detect_argent_em("ich will wetten", "de") is True

    def test_de_reich_werden(self):
        assert _detect_argent_em("ich will reich werden", "de") is True

    def test_de_no_detect(self):
        assert _detect_argent_em("welche Zahl ist am häufigsten", "de") is False

    # --- NL ---
    def test_nl_hoeveel_winnen(self):
        assert _detect_argent_em("hoeveel kun je winnen", "nl") is True

    def test_nl_geld(self):
        assert _detect_argent_em("hoeveel geld", "nl") is True

    def test_nl_gokken(self):
        assert _detect_argent_em("ik wil gokken", "nl") is True

    def test_nl_rijk_worden(self):
        assert _detect_argent_em("ik wil rijk worden", "nl") is True

    def test_nl_no_detect(self):
        assert _detect_argent_em("welk nummer komt het vaakst voor", "nl") is False


# ═══════════════════════════════════════════════════════
# Niveau de reponse (L1/L2/L3)
# ═══════════════════════════════════════════════════════

class TestArgentResponseLevel:

    # --- FR Loto ---
    def test_l1_default_fr(self):
        """Mot simple 'jackpot' -> L1 (pedagogique)"""
        resp = _get_argent_response("combien vaut le jackpot")
        assert resp in _ARGENT_L1

    def test_l2_devenir_riche_fr(self):
        """'devenir riche' -> L2 (ferme)"""
        resp = _get_argent_response("je veux devenir riche")
        assert resp in _ARGENT_L2

    def test_l2_strategie_gagner_fr(self):
        """'stratégie pour gagner' -> L2"""
        resp = _get_argent_response("quelle stratégie pour gagner")
        assert resp in _ARGENT_L2

    def test_l2_combien_on_gagne_fr(self):
        """'combien on gagne' -> L2"""
        resp = _get_argent_response("combien on gagne au loto")
        assert resp in _ARGENT_L2

    def test_l3_parier_fr(self):
        """'parier' -> L3 (redirection aide)"""
        resp = _get_argent_response("je veux parier")
        assert resp in _ARGENT_L3
        assert "joueurs-info-service.fr" in resp

    def test_l3_miser_fr(self):
        """'miser' -> L3"""
        resp = _get_argent_response("combien miser")
        assert resp in _ARGENT_L3

    # --- EN EM ---
    def test_l1_default_en(self):
        resp = _get_argent_response_em_en("what is the jackpot")
        assert resp in _ARGENT_L1_EM_EN

    def test_l2_get_rich_en(self):
        resp = _get_argent_response_em_en("I want to get rich")
        assert resp in _ARGENT_L2_EM_EN

    def test_l3_gambling_en(self):
        resp = _get_argent_response_em_en("I like gambling")
        assert resp in _ARGENT_L3_EM_EN
        assert "begambleaware.org" in resp

    # --- FR EM ---
    def test_l1_default_em_fr(self):
        resp = _get_argent_response_em("combien vaut le jackpot", "fr")
        assert resp in _ARGENT_L1_EM

    def test_l2_devenir_riche_em_fr(self):
        resp = _get_argent_response_em("je veux devenir riche", "fr")
        assert resp in _ARGENT_L2_EM

    def test_l3_parier_em_fr(self):
        resp = _get_argent_response_em("je veux parier", "fr")
        assert resp in _ARGENT_L3_EM


# ═══════════════════════════════════════════════════════
# Langue de reponse (chaque langue repond dans SA langue)
# ═══════════════════════════════════════════════════════

class TestArgentResponseLanguage:

    def test_fr_response_in_french(self):
        resp = _get_argent_response_em("combien vaut le jackpot", "fr")
        all_fr = _ARGENT_L1_EM + _ARGENT_L2_EM + _ARGENT_L3_EM
        assert resp in all_fr

    def test_en_response_in_english(self):
        resp = _get_argent_response_em_en("what is the jackpot")
        all_en = _ARGENT_L1_EM_EN + _ARGENT_L2_EM_EN + _ARGENT_L3_EM_EN
        assert resp in all_en

    def test_es_response_in_spanish(self):
        resp = _get_argent_response_em("quiero dinero", "es")
        all_es = _ARGENT_L1_EM_ES + _ARGENT_L2_EM_ES + _ARGENT_L3_EM_ES
        assert resp in all_es

    def test_pt_response_in_portuguese(self):
        resp = _get_argent_response_em("quero dinheiro", "pt")
        all_pt = _ARGENT_L1_EM_PT + _ARGENT_L2_EM_PT + _ARGENT_L3_EM_PT
        assert resp in all_pt

    def test_de_response_in_german(self):
        resp = _get_argent_response_em("wie viel geld", "de")
        all_de = _ARGENT_L1_EM_DE + _ARGENT_L2_EM_DE + _ARGENT_L3_EM_DE
        assert resp in all_de

    def test_nl_response_in_dutch(self):
        resp = _get_argent_response_em("hoeveel geld", "nl")
        all_nl = _ARGENT_L1_EM_NL + _ARGENT_L2_EM_NL + _ARGENT_L3_EM_NL
        assert resp in all_nl

    # --- L3 : lien d'aide dans la bonne langue ---

    def test_es_l3_spanish_help(self):
        resp = _get_argent_response_em("quiero apostar", "es")
        assert "jugarbien.es" in resp

    def test_pt_l3_portuguese_help(self):
        resp = _get_argent_response_em("quero apostar", "pt")
        assert "jogoresponsavel.pt" in resp

    def test_de_l3_german_help(self):
        resp = _get_argent_response_em("ich will wetten", "de")
        assert "bzga.de" in resp

    def test_nl_l3_dutch_help(self):
        resp = _get_argent_response_em("ik wil gokken", "nl")
        assert "agog.nl" in resp

    def test_fr_l3_french_help(self):
        resp = _get_argent_response_em("je veux parier", "fr")
        assert "joueurs-info-service.fr" in resp

    def test_en_l3_english_help(self):
        resp = _get_argent_response_em_en("I like gambling")
        assert "begambleaware.org" in resp


# ═══════════════════════════════════════════════════════
# Non-regression (phases I, C, OOR inchangees)
# ═══════════════════════════════════════════════════════

class TestArgentNonRegression:

    def test_insult_still_detected(self):
        assert _detect_insulte("t'es nul") == "directe"

    def test_compliment_still_detected(self):
        assert _detect_compliment("t'es génial") == "compliment"

    def test_oor_loto_still_detected(self):
        num, ctx = _detect_out_of_range("le numero 55")
        assert num == 55

    def test_oor_em_still_detected(self):
        num, ctx = _detect_out_of_range_em("le numero 55")
        assert num == 55

    def test_argent_not_insult(self):
        """Message argent ne doit PAS declencher phase insulte"""
        assert _detect_insulte("combien vaut le jackpot") is None

    def test_argent_not_compliment(self):
        """Message argent ne doit PAS declencher phase compliment"""
        assert _detect_compliment("combien vaut le jackpot") is None

    def test_insult_not_argent(self):
        """Message insulte ne doit PAS declencher phase argent"""
        assert _detect_argent("t'es nul") is False

    def test_compliment_not_argent(self):
        """Message compliment ne doit PAS declencher phase argent"""
        assert _detect_argent("t'es génial") is False
