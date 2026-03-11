"""
Tests — _detect_pedagogie_limites (Loto FR) et _detect_pedagogie_limites_em (EM multilingue).
Bug 1 P0 — Phase A faux positif sur questions pédagogiques.
"""

import pytest
from services.chat_detectors import (
    _detect_pedagogie_limites,
    _detect_argent,
)
from services.chat_detectors_em import (
    _detect_pedagogie_limites_em,
    _detect_argent_em,
)


# ═══════════════════════════════════════════════════════════════════════
# Loto FR — _detect_pedagogie_limites
# ═══════════════════════════════════════════════════════════════════════

class TestPedagogieLimitesFR:
    """Detections positives — questions pédagogiques FR."""

    def test_peut_on_predire_le_loto(self):
        assert _detect_pedagogie_limites("Peut-on prédire le loto ?")

    def test_est_il_possible_predire(self):
        assert _detect_pedagogie_limites("Est-il possible de prédire les tirages ?")

    def test_est_ce_possible_predire(self):
        assert _detect_pedagogie_limites("Est-ce possible de prédire le loto ?")

    def test_pourquoi_on_ne_peut_pas_predire(self):
        assert _detect_pedagogie_limites("Pourquoi on ne peut pas prédire le loto ?")

    def test_loto_est_il_previsible(self):
        assert _detect_pedagogie_limites("Le loto est-il prévisible ?")

    def test_tirage_aleatoire(self):
        assert _detect_pedagogie_limites("Le tirage est-il vraiment aléatoire ?")

    def test_loto_truque(self):
        assert _detect_pedagogie_limites("Est-ce que le loto est truqué ?")

    def test_impossible_de_predire(self):
        assert _detect_pedagogie_limites("C'est impossible de prédire le prochain tirage")

    def test_statistiques_peuvent_predire(self):
        assert _detect_pedagogie_limites("Les statistiques peuvent-elles prédire les résultats ?")

    def test_ton_ia_peut_gagner(self):
        assert _detect_pedagogie_limites("Ton IA peut gagner au loto ?")

    def test_votre_algorithme_peut_predire(self):
        assert _detect_pedagogie_limites("Votre algorithme peut prédire les numéros ?")

    def test_est_ce_que_ca_marche_vraiment(self):
        assert _detect_pedagogie_limites("Est-ce que ça marche vraiment pour gagner ?")

    def test_existe_methode_pour_gagner(self):
        assert _detect_pedagogie_limites("Existe-t-il une méthode pour gagner ?")

    def test_loi_grands_nombres(self):
        assert _detect_pedagogie_limites("La loi des grands nombres s'applique au loto ?")

    def test_gamblers_fallacy(self):
        assert _detect_pedagogie_limites("C'est quoi la gambler's fallacy ?")

    def test_biais_du_joueur(self):
        assert _detect_pedagogie_limites("Qu'est-ce que le biais du joueur ?")

    def test_biais_cognitif(self):
        assert _detect_pedagogie_limites("Y a-t-il un biais cognitif dans le jeu ?")

    def test_chaque_tirage_independant(self):
        assert _detect_pedagogie_limites("Chaque tirage est indépendant ?")

    def test_numeros_ont_memoire(self):
        assert _detect_pedagogie_limites("Les numéros ont-ils une mémoire ?")

    def test_hasard_vraiment_aleatoire(self):
        assert _detect_pedagogie_limites("Le hasard est vraiment aléatoire ?")

    def test_pourquoi_personne(self):
        assert _detect_pedagogie_limites("Pourquoi personne ne peut prédire le loto ?")

    def test_impossible_gagner(self):
        assert _detect_pedagogie_limites("C'est impossible de gagner à coup sûr ?")

    def test_algo_peut_predire(self):
        assert _detect_pedagogie_limites("Un algorithme peut prédire les résultats ?")


class TestPedagogieLimitesFRNegatif:
    """Detections négatives — ces messages ne doivent PAS être pédagogiques."""

    def test_combien_je_peux_gagner(self):
        assert not _detect_pedagogie_limites("Combien je peux gagner au loto ?")

    def test_strategie_gagner(self):
        assert not _detect_pedagogie_limites("Donne-moi une stratégie pour gagner")

    def test_devenir_riche(self):
        assert not _detect_pedagogie_limites("Je veux devenir riche")

    def test_simple_stats_question(self):
        assert not _detect_pedagogie_limites("Quelles sont les stats du numéro 7 ?")

    def test_top_5_numeros(self):
        assert not _detect_pedagogie_limites("Top 5 numéros les plus fréquents")

    def test_generation_grille(self):
        assert not _detect_pedagogie_limites("Génère-moi une grille optimisée")


# ═══════════════════════════════════════════════════════════════════════
# Phase A bypass — _detect_argent retourne False sur pédagogie
# ═══════════════════════════════════════════════════════════════════════

class TestPhaseABypassFR:
    """Les questions pédagogiques ne doivent PAS déclencher Phase A."""

    def test_peut_on_predire_no_argent(self):
        assert not _detect_argent("Peut-on prédire le loto ?")

    def test_ton_ia_peut_gagner_no_argent(self):
        assert not _detect_argent("Ton IA peut gagner au loto ?")

    def test_impossible_gagner_no_argent(self):
        assert not _detect_argent("C'est impossible de gagner à tous les coups ?")

    def test_existe_methode_no_argent(self):
        assert not _detect_argent("Existe-t-il une méthode pour gagner au loto ?")

    def test_algo_peut_predire_no_argent(self):
        assert not _detect_argent("Un algorithme peut prédire les résultats ?")


# ═══════════════════════════════════════════════════════════════════════
# EM multilingue — _detect_pedagogie_limites_em
# ═══════════════════════════════════════════════════════════════════════

class TestPedagogieLimitesEN:
    """Detections positives — questions pédagogiques EN."""

    def test_can_you_predict(self):
        assert _detect_pedagogie_limites_em("Can you predict the lottery?", "en")

    def test_is_it_possible_to_predict(self):
        assert _detect_pedagogie_limites_em("Is it possible to predict lottery numbers?", "en")

    def test_why_cant_anyone_predict(self):
        assert _detect_pedagogie_limites_em("Why can't anyone predict the draw?", "en")

    def test_lottery_predictable(self):
        assert _detect_pedagogie_limites_em("Is the lottery predictable?", "en")

    def test_impossible_to_predict(self):
        assert _detect_pedagogie_limites_em("It's impossible to predict lottery results", "en")

    def test_can_ai_predict(self):
        assert _detect_pedagogie_limites_em("Can AI predict lottery numbers?", "en")

    def test_does_your_algorithm_work(self):
        assert _detect_pedagogie_limites_em("Does your algorithm really work?", "en")

    def test_gamblers_fallacy_en(self):
        assert _detect_pedagogie_limites_em("What is the gambler's fallacy?", "en")

    def test_each_draw_independent(self):
        assert _detect_pedagogie_limites_em("Each draw is independent, right?", "en")

    def test_can_your_ai_win(self):
        assert _detect_pedagogie_limites_em("Can your AI help me win?", "en")

    def test_is_there_a_method_to_win(self):
        assert _detect_pedagogie_limites_em("Is there a method to win the lottery?", "en")

    def test_lottery_rigged(self):
        assert _detect_pedagogie_limites_em("Is the lottery rigged?", "en")


class TestPedagogieLimitesES:
    """Detections positives — questions pédagogiques ES."""

    def test_se_puede_predecir(self):
        assert _detect_pedagogie_limites_em("¿Se puede predecir la lotería?", "es")

    def test_es_posible_predecir(self):
        assert _detect_pedagogie_limites_em("¿Es posible predecir los números?", "es")

    def test_imposible_predecir(self):
        assert _detect_pedagogie_limites_em("Es imposible de predecir el sorteo", "es")

    def test_falacia_del_jugador(self):
        assert _detect_pedagogie_limites_em("¿Qué es la falacia del jugador?", "es")

    def test_cada_sorteo_independiente(self):
        assert _detect_pedagogie_limites_em("Cada sorteo es independiente?", "es")

    def test_algoritmo_puede_predecir(self):
        assert _detect_pedagogie_limites_em("Tu algoritmo puede predecir?", "es")


class TestPedagogieLimitesPT:
    """Detections positives — questions pédagogiques PT."""

    def test_e_possivel_prever(self):
        assert _detect_pedagogie_limites_em("É possível prever os resultados?", "pt")

    def test_impossivel_prever(self):
        assert _detect_pedagogie_limites_em("É impossível de prever a lotaria", "pt")

    def test_falacia_do_jogador(self):
        assert _detect_pedagogie_limites_em("O que é a falácia do jogador?", "pt")

    def test_cada_sorteio_independente(self):
        assert _detect_pedagogie_limites_em("Cada sorteio é independente?", "pt")

    def test_algoritmo_pode_prever(self):
        assert _detect_pedagogie_limites_em("O teu algoritmo pode prever o resultado?", "pt")


class TestPedagogieLimitesDE:
    """Detections positives — questions pédagogiques DE."""

    def test_kann_man_vorhersagen(self):
        assert _detect_pedagogie_limites_em("Kann man die Lotterie vorhersagen?", "de")

    def test_ist_es_moeglich(self):
        assert _detect_pedagogie_limites_em("Ist es möglich vorherzusagen?", "de")

    def test_unmoeglich_vorherzusagen(self):
        assert _detect_pedagogie_limites_em("Es ist unmöglich vorherzusagen", "de")

    def test_spielerfehlschluss(self):
        assert _detect_pedagogie_limites_em("Was ist der Spielerfehlschluss?", "de")

    def test_jede_ziehung_unabhaengig(self):
        assert _detect_pedagogie_limites_em("Jede Ziehung ist unabhängig?", "de")


class TestPedagogieLimitesNL:
    """Detections positives — questions pédagogiques NL."""

    def test_kan_je_voorspellen(self):
        assert _detect_pedagogie_limites_em("Kan je de loterij voorspellen?", "nl")

    def test_is_het_mogelijk(self):
        assert _detect_pedagogie_limites_em("Is het mogelijk om te voorspellen?", "nl")

    def test_onmogelijk_voorspellen(self):
        assert _detect_pedagogie_limites_em("Het is onmogelijk om te voorspellen", "nl")

    def test_gokkersdrogreden(self):
        assert _detect_pedagogie_limites_em("Wat is de gokkersdrogreden?", "nl")

    def test_elke_trekking_onafhankelijk(self):
        assert _detect_pedagogie_limites_em("Elke trekking is onafhankelijk?", "nl")


# ═══════════════════════════════════════════════════════════════════════
# EM Phase A bypass — _detect_argent_em retourne False sur pédagogie
# ═══════════════════════════════════════════════════════════════════════

class TestPhaseABypassEM:
    """Les questions pédagogiques ne doivent PAS déclencher Phase A EM."""

    def test_en_can_you_predict_no_argent(self):
        assert not _detect_argent_em("Can you predict the lottery?", "en")

    def test_en_can_your_ai_win_no_argent(self):
        assert not _detect_argent_em("Can your AI help me win?", "en")

    def test_es_se_puede_predecir_no_argent(self):
        assert not _detect_argent_em("¿Se puede predecir la lotería?", "es")

    def test_pt_e_possivel_prever_no_argent(self):
        assert not _detect_argent_em("É possível prever os resultados?", "pt")

    def test_de_kann_man_vorhersagen_no_argent(self):
        assert not _detect_argent_em("Kann man die Lotterie vorhersagen?", "de")

    def test_nl_kan_je_voorspellen_no_argent(self):
        assert not _detect_argent_em("Kan je de loterij voorspellen?", "nl")

    def test_fr_peut_on_predire_no_argent_em(self):
        assert not _detect_argent_em("Peut-on prédire l'EuroMillions ?", "fr")

    def test_en_is_there_method_no_argent(self):
        assert not _detect_argent_em("Is there a method to win the lottery?", "en")


# ═══════════════════════════════════════════════════════════════════════
# Fallback lang → FR quand lang inconnu
# ═══════════════════════════════════════════════════════════════════════

class TestPedagogieFallback:

    def test_unknown_lang_falls_back_to_fr(self):
        assert _detect_pedagogie_limites_em("Peut-on prédire le loto ?", "xx")

    def test_unknown_lang_en_fails(self):
        """English message with unknown lang → FR patterns, should not match."""
        assert not _detect_pedagogie_limites_em("Can you predict the lottery?", "xx")
