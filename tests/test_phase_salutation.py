"""
Tests Phase SALUTATION (V65) — 6 langues, guards historique/longueur, variantes.
F10 audit V71.
"""

from services.base_chat_detectors import (
    _detect_salutation, _get_salutation_response, _SALUTATION_MAX_WORDS,
)


# ═══════════════════════════════════════════════════════
# Detection 6 langues
# ═══════════════════════════════════════════════════════

class TestSalutationDetection6Langs:
    """_detect_salutation must match greetings in all 6 languages."""

    def test_fr_bonjour(self):
        assert _detect_salutation("bonjour") is True

    def test_en_hello(self):
        assert _detect_salutation("hello") is True

    def test_es_hola(self):
        assert _detect_salutation("hola") is True

    def test_pt_ola(self):
        assert _detect_salutation("olá") is True

    def test_de_hallo(self):
        assert _detect_salutation("hallo") is True

    def test_nl_hallo(self):
        assert _detect_salutation("hallo!") is True


# ═══════════════════════════════════════════════════════
# Variantes
# ═══════════════════════════════════════════════════════

class TestSalutationVariants:
    """Additional greeting variants."""

    def test_fr_salut(self):
        assert _detect_salutation("salut") is True

    def test_fr_coucou(self):
        assert _detect_salutation("coucou") is True

    def test_en_hi_there(self):
        assert _detect_salutation("hi there") is True

    def test_de_guten_tag(self):
        assert _detect_salutation("guten tag") is True

    def test_es_buenos_dias(self):
        assert _detect_salutation("buenos días") is True

    def test_pt_bom_dia(self):
        assert _detect_salutation("bom dia") is True


# ═══════════════════════════════════════════════════════
# Guards
# ═══════════════════════════════════════════════════════

class TestSalutationGuards:
    """SALUTATION must NOT trigger on long messages or when combined with a question."""

    def test_long_message_not_salutation(self):
        """Message >= 8 words must NOT trigger SALUTATION."""
        long_msg = "bonjour quel est le numéro le plus fréquent au loto"
        assert len(long_msg.split()) > _SALUTATION_MAX_WORDS
        assert _detect_salutation(long_msg) is False

    def test_greeting_plus_question_not_salutation(self):
        """'bonjour quel est le numéro le plus fréquent' -> NOT salutation."""
        assert _detect_salutation("bonjour quel est le numéro le plus fréquent") is False

    def test_greeting_plus_generation(self):
        """'salut génère-moi une grille' -> NOT salutation (question embedded)."""
        assert _detect_salutation("salut génère-moi une grille") is False

    def test_empty_message_not_salutation(self):
        assert _detect_salutation("") is False

    def test_random_word_not_salutation(self):
        assert _detect_salutation("pizza") is False

    def test_number_not_salutation(self):
        assert _detect_salutation("42") is False


# ═══════════════════════════════════════════════════════
# Response — no Gemini, local response
# ═══════════════════════════════════════════════════════

class TestSalutationResponse:
    """_get_salutation_response returns a local string (no Gemini call)."""

    def test_loto_fr(self):
        resp = _get_salutation_response("loto", "fr")
        assert "HYBRIDE" in resp
        assert "Loto" in resp

    def test_em_en(self):
        resp = _get_salutation_response("em", "en")
        assert "HYBRIDE" in resp
        assert "EuroMillions" in resp

    def test_em_es(self):
        resp = _get_salutation_response("em", "es")
        assert "HYBRIDE" in resp

    def test_em_de(self):
        resp = _get_salutation_response("em", "de")
        assert "HYBRIDE" in resp

    def test_fallback_unknown_lang(self):
        """Unknown lang falls back to FR."""
        resp = _get_salutation_response("loto", "xx")
        assert "HYBRIDE" in resp
        assert "Loto" in resp

    def test_fallback_unknown_module(self):
        """Unknown module falls back to loto."""
        resp = _get_salutation_response("unknown", "fr")
        assert "HYBRIDE" in resp
