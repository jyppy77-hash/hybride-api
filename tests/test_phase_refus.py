"""
Tests V98c — Phase REFUS : court-circuit Python après refus utilisateur.

Le chatbot doit répondre localement (pas Gemini) quand l'utilisateur
envoie un refus simple APRÈS au moins un échange.
"""

import pytest

from services.base_chat_detect_intent import (
    _is_refusal, _get_refusal_response, _REFUSAL_RESPONSES,
)


# ═══════════════════════════════════════════════════════
# _is_refusal — détection regex
# ═══════════════════════════════════════════════════════

class TestIsRefusal:
    """_is_refusal détecte les refus simples dans 6 langues."""

    # ── FR ──
    def test_fr_non(self):
        assert _is_refusal("non") is True

    def test_fr_non_merci(self):
        assert _is_refusal("Non merci") is True

    def test_fr_pas_interesse(self):
        assert _is_refusal("pas intéressé") is True

    def test_fr_pas_besoin(self):
        assert _is_refusal("pas besoin") is True

    def test_fr_cest_bon(self):
        assert _is_refusal("c'est bon") is True

    def test_fr_ca_ira(self):
        assert _is_refusal("ça ira") is True

    def test_fr_osef(self):
        assert _is_refusal("osef") is True

    def test_fr_men_fiche(self):
        assert _is_refusal("je m'en fiche") is True

    # ── EN ──
    def test_en_no_thanks(self):
        assert _is_refusal("No thanks") is True

    def test_en_not_interested(self):
        assert _is_refusal("not interested") is True

    def test_en_im_good(self):
        assert _is_refusal("I'm good") is True

    def test_en_nope(self):
        assert _is_refusal("nope") is True

    def test_en_whatever(self):
        assert _is_refusal("whatever") is True

    def test_en_dont_care(self):
        assert _is_refusal("don't care") is True

    # ── ES ──
    def test_es_no_gracias(self):
        assert _is_refusal("No gracias") is True

    def test_es_no_me_interesa(self):
        assert _is_refusal("no me interesa") is True

    def test_es_paso(self):
        assert _is_refusal("paso") is True

    # ── PT ──
    def test_pt_nao_obrigado(self):
        assert _is_refusal("Não obrigado") is True

    def test_pt_tanto_faz(self):
        assert _is_refusal("tanto faz") is True

    # ── DE ──
    def test_de_nein_danke(self):
        assert _is_refusal("Nein danke") is True

    def test_de_kein_interesse(self):
        assert _is_refusal("kein interesse") is True

    def test_de_egal(self):
        assert _is_refusal("egal") is True

    # ── NL ──
    def test_nl_nee_bedankt(self):
        assert _is_refusal("Nee bedankt") is True

    def test_nl_niet_nodig(self):
        assert _is_refusal("niet nodig") is True

    def test_nl_boeit_niet(self):
        assert _is_refusal("boeit niet") is True

    # ── Ponctuation / whitespace ──
    def test_with_exclamation(self):
        assert _is_refusal("non!") is True

    def test_with_period(self):
        assert _is_refusal("non.") is True

    def test_with_trailing_space(self):
        assert _is_refusal("  non  ") is True


# ═══════════════════════════════════════════════════════
# Négatifs : NE DOIT PAS matcher
# ═══════════════════════════════════════════════════════

class TestIsRefusalNegative:
    """Messages qui contiennent un refus + contenu additionnel → pas Phase REFUS."""

    def test_non_plus_question(self):
        assert _is_refusal("non, quels sont les numéros chauds ?") is False

    def test_non_plus_demand(self):
        assert _is_refusal("non mais donne moi une grille") is False

    def test_no_but_what_about(self):
        assert _is_refusal("no but what about number 7?") is False

    def test_non_genere_grille(self):
        assert _is_refusal("non, génère moi une grille") is False

    def test_long_message_starting_with_no(self):
        assert _is_refusal("non je veux savoir les statistiques du 42") is False

    def test_first_message_non(self):
        """'non' as a valid first word in a longer sentence."""
        assert _is_refusal("non merci mais dis moi plutôt") is False

    def test_empty_string(self):
        assert _is_refusal("") is False

    def test_number_only(self):
        assert _is_refusal("42") is False


# ═══════════════════════════════════════════════════════
# _get_refusal_response — pools 6 langues
# ═══════════════════════════════════════════════════════

class TestRefusalResponses:
    """Réponses locales : pas de '?', 6 langues."""

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_no_question_mark(self, lang):
        """Aucune réponse de refus ne doit se terminer par '?'."""
        pool = _REFUSAL_RESPONSES[lang]
        for resp in pool:
            assert not resp.rstrip().endswith("?"), (
                f"Refusal response in {lang} ends with '?': {resp}"
            )

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_pool_not_empty(self, lang):
        """Chaque langue a au moins 3 réponses."""
        assert len(_REFUSAL_RESPONSES[lang]) >= 3

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_get_refusal_response_returns_string(self, lang):
        """_get_refusal_response retourne une string non vide."""
        resp = _get_refusal_response(lang)
        assert isinstance(resp, str)
        assert len(resp) > 5

    def test_fallback_to_fr(self):
        """Langue inconnue → fallback FR."""
        resp = _get_refusal_response("xx")
        assert isinstance(resp, str)
        assert len(resp) > 5
