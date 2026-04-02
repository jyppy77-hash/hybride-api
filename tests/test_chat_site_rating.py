"""
Tests unitaires pour Phase R — site rating detection + responses.
F08 V82: cette phase n'avait aucun test dédié.
"""

import pytest

from services.chat_detectors import _detect_site_rating, get_site_rating_response


# ═══════════════════════════════════════════════════════════════════════
# _detect_site_rating — positifs (6 langues)
# ═══════════════════════════════════════════════════════════════════════

class TestDetectSiteRatingPositive:

    # FR
    def test_fr_noter_le_site(self):
        assert _detect_site_rating("je veux noter le site") is True

    def test_fr_donner_note(self):
        assert _detect_site_rating("donner une note au site") is True

    def test_fr_evaluer_le_site(self):
        assert _detect_site_rating("évaluer le site") is True

    def test_fr_mettre_note_lotoia(self):
        assert _detect_site_rating("mettre une note lotoia") is True

    def test_fr_donner_avis_plateforme(self):
        assert _detect_site_rating("donner mon avis pour le site") is True

    # EN
    def test_en_rate_this_site(self):
        assert _detect_site_rating("rate this site") is True

    def test_en_leave_a_review(self):
        assert _detect_site_rating("leave a review for the website") is True

    def test_en_give_a_rating(self):
        assert _detect_site_rating("give a rating for the site") is True

    # ES
    def test_es_calificar_el_sitio(self):
        assert _detect_site_rating("calificar el sitio") is True

    def test_es_dar_nota(self):
        assert _detect_site_rating("dar una nota al sitio") is True

    # PT
    def test_pt_avaliar_o_site(self):
        assert _detect_site_rating("avaliar o site") is True

    def test_pt_dar_nota_lotoia(self):
        assert _detect_site_rating("dar uma nota ao lotoia") is True

    # DE
    def test_de_seite_bewerten(self):
        assert _detect_site_rating("die Seite bewerten") is True

    def test_de_bewertung_geben(self):
        assert _detect_site_rating("eine Bewertung geben der Seite") is True

    # NL
    def test_nl_site_beoordelen(self):
        assert _detect_site_rating("de site beoordelen") is True

    def test_nl_beoordeling_geven(self):
        assert _detect_site_rating("een beoordeling geven voor de website") is True


# ═══════════════════════════════════════════════════════════════════════
# _detect_site_rating — négatifs (faux positifs à éviter)
# ═══════════════════════════════════════════════════════════════════════

class TestDetectSiteRatingNegative:

    def test_taux_sortie(self):
        assert _detect_site_rating("quel est le taux de sortie du 7") is False

    def test_note_numero(self):
        assert _detect_site_rating("note du numéro 7") is False

    def test_statistiques(self):
        assert _detect_site_rating("donne-moi les statistiques") is False

    def test_genere_grille(self):
        assert _detect_site_rating("génère-moi une grille") is False

    def test_bonjour(self):
        assert _detect_site_rating("bonjour") is False

    def test_tirage(self):
        assert _detect_site_rating("résultat du dernier tirage") is False


# ═══════════════════════════════════════════════════════════════════════
# get_site_rating_response — 6 langues
# ═══════════════════════════════════════════════════════════════════════

class TestSiteRatingResponse:

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_response_non_empty(self, lang):
        resp = get_site_rating_response(lang)
        assert resp
        assert len(resp) > 20

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_response_mentions_stars(self, lang):
        """Each response should mention stars/étoiles/estrellas/Sterne/sterren."""
        resp = get_site_rating_response(lang).lower()
        star_words = ["étoile", "star", "estrella", "estrela", "sterne", "sterren"]
        assert any(w in resp for w in star_words)

    def test_unknown_lang_falls_back_to_fr(self):
        resp = get_site_rating_response("xx")
        assert resp == get_site_rating_response("fr")
