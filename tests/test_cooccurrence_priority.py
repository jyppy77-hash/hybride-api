"""
Tests — Bug 2 P1 : _detect_cooccurrence_high_n exclut les requêtes ranking/top-N.
"""

from services.chat_detectors import (
    _detect_cooccurrence_high_n,
)


class TestCooccurrenceExcludesRanking:
    """Messages ranking/top-N NE doivent PAS déclencher co-occurrence."""

    def test_top_5_numeros_plus_frequents(self):
        assert not _detect_cooccurrence_high_n("top 5 numéros les plus fréquents")

    def test_top_5_numeros_plus_sortis(self):
        assert not _detect_cooccurrence_high_n("top 5 numéros les plus sortis")

    def test_5_numbers_most_drawn_no_together(self):
        """Ranking EN sans 'together' → Phase 3."""
        assert not _detect_cooccurrence_high_n("5 numbers most frequently drawn")

    def test_most_drawn_5_numbers(self):
        """Pure ranking sans 'together' → Phase 3."""
        assert not _detect_cooccurrence_high_n("5 numbers most drawn")

    def test_top_10_numeros_sans_ensemble(self):
        """Ranking sans 'ensemble' → Phase 3."""
        assert not _detect_cooccurrence_high_n("top 10 numéros les plus fréquents")

    def test_classement_5_numeros(self):
        """Classement sans 'ensemble' → Phase 3."""
        assert not _detect_cooccurrence_high_n("classement des 5 numéros les plus sortis")

    def test_ranking_7_numbers(self):
        """Ranking sans 'together' → Phase 3."""
        assert not _detect_cooccurrence_high_n("ranking of 7 numbers most common")

    def test_haeufigsten_ohne_zusammen(self):
        """Ranking DE sans 'zusammen' → Phase 3."""
        assert not _detect_cooccurrence_high_n("die 5 häufigsten Zahlen im Ranking")


class TestCooccurrenceStillDetects:
    """Les vraies co-occurrences N>3 doivent toujours être détectées."""

    def test_5_numeros_ensemble(self):
        assert _detect_cooccurrence_high_n("quels 5 numéros sortent ensemble ?")

    def test_4_numeros_qui_sortent(self):
        assert _detect_cooccurrence_high_n("4 numéros qui sortent ensemble")

    def test_quadruplet(self):
        assert _detect_cooccurrence_high_n("y a-t-il des quadruplets fréquents ?")

    def test_quintuplet(self):
        assert _detect_cooccurrence_high_n("montre-moi les quintuplets")

    def test_combinaison_de_5(self):
        assert _detect_cooccurrence_high_n("combinaison de 5 numéros ensemble")

    def test_5_numbers_together_en(self):
        assert _detect_cooccurrence_high_n("which 5 numbers come together?")

    def test_5_zahlen_zusammen(self):
        assert _detect_cooccurrence_high_n("5 Zahlen zusammen gezogen")

    def test_5_nummers_samen(self):
        assert _detect_cooccurrence_high_n("5 nummers samen getrokken")

    def test_5_numeros_juntos_es(self):
        assert _detect_cooccurrence_high_n("5 números juntos en un sorteo")

    def test_5_numeros_juntos_pt(self):
        assert _detect_cooccurrence_high_n("5 números juntos no sorteio")

    def test_groupe_de_6(self):
        assert _detect_cooccurrence_high_n("groupe de 6 numéros")

    def test_combination_of_7(self):
        assert _detect_cooccurrence_high_n("combination of 7 numbers")
