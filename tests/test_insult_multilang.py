"""
Tests F07 — Insult detection multilingual (EN/ES/PT/DE/NL).
Verifies _detect_insulte() works across all 6 languages.
"""

import pytest

from services.base_chat_detect_guardrails import _detect_insulte


class TestDetectInsulteEN:

    def test_you_are_stupid(self):
        assert _detect_insulte("you are stupid") == "directe"

    def test_you_suck(self):
        assert _detect_insulte("you suck") == "directe"

    def test_shut_up(self):
        assert _detect_insulte("shut up already") == "directe"

    def test_this_bot_is_useless(self):
        assert _detect_insulte("this bot is useless") == "directe"

    def test_en_threat(self):
        assert _detect_insulte("I'll hack you") == "menace"


class TestDetectInsulteES:

    def test_eres_idiota(self):
        assert _detect_insulte("eres idiota") == "directe"

    def test_callate(self):
        assert _detect_insulte("cállate ya") == "directe"

    def test_no_sirves_para_nada(self):
        assert _detect_insulte("no sirves para nada") == "directe"

    def test_es_threat(self):
        assert _detect_insulte("voy a hackear este bot") == "menace"


class TestDetectInsultePT:

    def test_es_estupido(self):
        assert _detect_insulte("tu és estúpido") == "directe"

    def test_cala_te(self):
        assert _detect_insulte("cala-te") == "directe"

    def test_nao_serves(self):
        assert _detect_insulte("não serves para nada") == "directe"

    def test_pt_threat(self):
        assert _detect_insulte("vou hackear") == "menace"


class TestDetectInsulteDE:

    def test_du_bist_dumm(self):
        assert _detect_insulte("du bist dumm") == "directe"

    def test_halts_maul(self):
        assert _detect_insulte("halts maul") == "directe"

    def test_dieser_bot_ist_muell(self):
        assert _detect_insulte("dieser bot ist müll") == "directe"

    def test_de_threat(self):
        assert _detect_insulte("ich werde dich hacken") == "menace"


class TestDetectInsulteNL:

    def test_je_bent_dom(self):
        assert _detect_insulte("je bent dom") == "directe"

    def test_hou_je_mond(self):
        assert _detect_insulte("hou je mond") == "directe"

    def test_deze_bot_is_waardeloos(self):
        assert _detect_insulte("deze bot is waardeloos") == "directe"

    def test_nl_threat(self):
        assert _detect_insulte("ik ga je hacken") == "menace"


class TestDetectInsulteMultilangWords:
    """Verify _INSULTE_MOTS word-level detection across languages."""

    @pytest.mark.parametrize("word,lang", [
        ("stupid you", "EN"),
        ("idiot you are", "EN"),
        ("tonto eres", "ES"),
        ("tu és idiota", "PT"),
        ("du trottel", "DE"),
        ("jij sukkel", "NL"),
    ])
    def test_insult_word_detected(self, word, lang):
        result = _detect_insulte(word)
        assert result is not None, f"Insult not detected in {lang}: '{word}'"
