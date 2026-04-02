"""
Tests unitaires pour Phase 0-bis — prochain tirage detection (Loto + EM).
F09 V82: _detect_prochain_tirage() n'avait que 3 tests EM, 0 Loto.
"""

from services.chat_detectors import _detect_prochain_tirage
from services.chat_detectors_em import _detect_prochain_tirage_em


# ═══════════════════════════════════════════════════════════════════════
# _detect_prochain_tirage — Loto (FR)
# ═══════════════════════════════════════════════════════════════════════

class TestProchainTirageLoto:

    def test_prochain_tirage_simple(self):
        assert _detect_prochain_tirage("prochain tirage") is True

    def test_c_est_quand_le_prochain_tirage(self):
        assert _detect_prochain_tirage("c'est quand le prochain tirage") is True

    def test_quand_est_le_prochain_tirage(self):
        assert _detect_prochain_tirage("quand est le prochain tirage") is True

    def test_prochain_tirage_loto(self):
        assert _detect_prochain_tirage("prochain tirage loto") is True

    def test_date_du_prochain_tirage(self):
        assert _detect_prochain_tirage("date du prochain tirage") is True

    def test_le_loto_c_est_quand(self):
        assert _detect_prochain_tirage("le loto c'est quand") is True

    def test_quand_a_lieu_le_tirage(self):
        assert _detect_prochain_tirage("quand a lieu le tirage") is True

    def test_prochain_loto(self):
        assert _detect_prochain_tirage("prochain loto") is True


# ═══════════════════════════════════════════════════════════════════════
# _detect_prochain_tirage_em — EuroMillions (FR + multilingue partiel)
# ═══════════════════════════════════════════════════════════════════════

class TestProchainTirageEM:

    # FR
    def test_fr_prochain_tirage_em(self):
        assert _detect_prochain_tirage_em("prochain tirage euromillions") is True

    def test_fr_c_est_quand_em(self):
        assert _detect_prochain_tirage_em("c'est quand le prochain euromillions") is True

    def test_fr_date_tirage_em(self):
        assert _detect_prochain_tirage_em("date du prochain tirage") is True

    def test_fr_quand_a_lieu_em(self):
        assert _detect_prochain_tirage_em("quand a lieu le tirage") is True

    # EN — the regex supports "draw" keyword
    def test_en_next_draw(self):
        assert _detect_prochain_tirage_em("quand est le prochain draw") is True

    # Patterns with "euromillions" keyword
    def test_prochain_euromillions(self):
        assert _detect_prochain_tirage_em("prochain euromillions") is True

    def test_euromillions_prochain(self):
        assert _detect_prochain_tirage_em("euromillions prochain") is True


# ═══════════════════════════════════════════════════════════════════════
# Cas négatifs — ne doivent PAS trigger prochain tirage
# ═══════════════════════════════════════════════════════════════════════

class TestProchainTirageNegative:

    def test_tirage_du_15_mars(self):
        """Phase T, pas prochain tirage."""
        assert _detect_prochain_tirage("tirage du 15 mars") is False

    def test_resultat_dernier_tirage(self):
        """Phase 2, pas prochain tirage."""
        assert _detect_prochain_tirage("résultat du dernier tirage") is False

    def test_stats_numero(self):
        assert _detect_prochain_tirage("donne-moi les stats du 7") is False

    def test_genere_grille(self):
        assert _detect_prochain_tirage("génère une grille") is False

    def test_tirage_du_15_mars_em(self):
        assert _detect_prochain_tirage_em("tirage du 15 mars") is False

    def test_stats_em(self):
        assert _detect_prochain_tirage_em("statistiques des boules") is False
