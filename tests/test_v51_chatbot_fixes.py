"""
Tests V51 — Chatbot HYBRIDE fixes (FIX 1-5).
FIX 1: Affirmation simple (Oui/Ok/Non) detection + pipeline handling
FIX 2: Bare number detection (27 seul)
FIX 3: Grille EM Unicode stars
FIX 4: Remerciements + conseil detection
FIX 5: Game keyword alone detection
"""

import pytest
import re
from unittest.mock import AsyncMock, MagicMock, patch

from services.base_chat_detectors import (
    _is_affirmation_simple,
    _detect_game_keyword_alone,
    _detect_compliment,
    _detect_generation,
)
from services.chat_detectors import _detect_numero
from services.chat_detectors_em import _detect_numero_em, _detect_grille_em


# ═══════════════════════════════════════════════════════
# FIX 1 — _is_affirmation_simple (15 tests)
# ═══════════════════════════════════════════════════════


class TestAffirmationSimple:
    """FIX 1: Affirmation simple detection."""

    def test_oui_simple(self):
        assert _is_affirmation_simple("Oui") is True

    def test_ok_simple(self):
        assert _is_affirmation_simple("Ok") is True

    def test_non_simple(self):
        assert _is_affirmation_simple("Non") is True

    def test_oui_with_emoji(self):
        """Strip emojis, match ok."""
        assert _is_affirmation_simple("Ok 🥹") is True

    def test_oui_je_veux_bien(self):
        assert _is_affirmation_simple("Oui je veux bien") is False  # >1 word, "oui" alone matches but "je veux bien" not in pattern as multi-word after oui
        # Actually "oui" alone matches the pattern, but the full text "Oui je veux bien" stripped of emojis is 4 words.
        # The regex ^(oui)[\s!.?…]*$ only matches "oui" alone. 4 words fails regex. So False.

    def test_avec_plaisir(self):
        assert _is_affirmation_simple("Avec plaisir") is True

    def test_oui_le_7_not_captured(self):
        """Digit guard V46 — must NOT be captured."""
        assert _is_affirmation_simple("oui le 7") is False

    def test_oui_le_7_stp_not_captured(self):
        """Digit guard V46 — must NOT be captured."""
        assert _is_affirmation_simple("oui le 7 stp") is False

    def test_27_not_captured(self):
        """Bare number must NOT be captured by affirmation."""
        assert _is_affirmation_simple("27") is False

    # 6 langues
    def test_affirmation_en(self):
        assert _is_affirmation_simple("Yes") is True
        assert _is_affirmation_simple("Sure") is True
        assert _is_affirmation_simple("Nope") is True

    def test_affirmation_es(self):
        assert _is_affirmation_simple("Sí") is True
        assert _is_affirmation_simple("Claro") is True
        assert _is_affirmation_simple("Vale") is True

    def test_affirmation_pt(self):
        assert _is_affirmation_simple("Sim") is True
        assert _is_affirmation_simple("Não") is True
        assert _is_affirmation_simple("Com certeza") is True

    def test_affirmation_de(self):
        assert _is_affirmation_simple("Ja") is True
        assert _is_affirmation_simple("Nein") is True
        assert _is_affirmation_simple("Natürlich") is True

    def test_affirmation_nl(self):
        assert _is_affirmation_simple("Nee") is True
        assert _is_affirmation_simple("Prima") is True
        assert _is_affirmation_simple("Akkoord") is True

    def test_long_message_not_captured(self):
        """Messages > 5 words should not be captured."""
        assert _is_affirmation_simple("Oui aide moi pour ma famille stp") is False

    def test_non_sa_je_suis_conscient(self):
        """5 words, starts with 'non' but contains extra words — regex won't match full."""
        # "Non sa je suis conscient" = 5 words, text_only starts with "Non" but regex expects ^(non)[\s!.?]*$
        # This won't match because there are extra words. Correct behavior.
        assert _is_affirmation_simple("Non sa je suis conscient") is False

    def test_empty_message(self):
        assert _is_affirmation_simple("") is False

    def test_emoji_only(self):
        assert _is_affirmation_simple("🥹💖") is False


# ═══════════════════════════════════════════════════════
# FIX 2 — Bare number detection (8 tests)
# ═══════════════════════════════════════════════════════


class TestBareNumber:
    """FIX 2: Bare integer detection in _detect_numero / _detect_numero_em."""

    def test_bare_27_loto(self):
        num, type_num = _detect_numero("27")
        assert num == 27
        assert type_num == "principal"

    def test_bare_7_loto(self):
        num, type_num = _detect_numero("7")
        assert num == 7
        assert type_num == "principal"

    def test_bare_49_loto_max(self):
        num, type_num = _detect_numero("49")
        assert num == 49
        assert type_num == "principal"

    def test_bare_50_loto_oor(self):
        """50 is out of range for Loto (1-49)."""
        num, _ = _detect_numero("50")
        assert num is None

    def test_bare_0_invalid(self):
        num, _ = _detect_numero("0")
        assert num is None

    def test_bare_7_em(self):
        num, type_num = _detect_numero_em("7")
        assert num == 7
        assert type_num == "boule"

    def test_bare_50_em_valid(self):
        num, type_num = _detect_numero_em("50")
        assert num == 50
        assert type_num == "boule"

    def test_bare_51_em_oor(self):
        """51 is out of range for EM (1-50)."""
        num, _ = _detect_numero_em("51")
        assert num is None

    def test_bare_number_with_text_not_bare(self):
        """'le 27' should still work via existing pattern, not bare pattern."""
        num, type_num = _detect_numero("le 27")
        assert num == 27
        assert type_num == "principal"


# ═══════════════════════════════════════════════════════
# FIX 3 — Grille EM Unicode stars (8 tests)
# ═══════════════════════════════════════════════════════


class TestGrilleEmUnicode:
    """FIX 3: Grille EM with Unicode star characters."""

    def test_grille_em_tirets_etoiles_unicode(self):
        """Real CSV format: '18-22-33-41-46 ☆11-12☆'"""
        nums, etoiles = _detect_grille_em("18-22-33-41-46 ☆11-12☆")
        assert nums == [18, 22, 33, 41, 46]
        assert etoiles == [11, 12]

    def test_grille_em_star_unicode_filled(self):
        nums, etoiles = _detect_grille_em("1-2-3-4-5 ★6-7★")
        assert nums == [1, 2, 3, 4, 5]
        assert etoiles == [6, 7]

    def test_grille_em_star_emoji(self):
        nums, etoiles = _detect_grille_em("10 20 30 40 50 ⭐3 7⭐")
        assert nums is not None
        assert len(nums) == 5
        assert etoiles is not None

    def test_grille_em_tirets_sans_etoiles(self):
        """5 boules with dashes, no stars."""
        nums, etoiles = _detect_grille_em("18-22-33-41-46")
        assert nums == [18, 22, 33, 41, 46]
        assert etoiles is None

    def test_grille_em_keyword_etoiles_tirets(self):
        """'étoiles 11-12' with dash separator."""
        nums, etoiles = _detect_grille_em("18 22 33 41 46 étoiles 11-12")
        assert nums == [18, 22, 33, 41, 46]
        assert etoiles == [11, 12]

    def test_grille_em_existing_format_still_works(self):
        """Existing space-separated format must still work."""
        nums, etoiles = _detect_grille_em("18 22 33 41 46 étoiles 11 12")
        assert nums == [18, 22, 33, 41, 46]
        assert etoiles == [11, 12]

    def test_grille_em_plus_format_still_works(self):
        """Existing '+' format must still work."""
        nums, etoiles = _detect_grille_em("18 22 33 41 46 + 11 12")
        assert nums == [18, 22, 33, 41, 46]
        assert etoiles == [11, 12]

    def test_grille_em_unicode_star_invalid_range(self):
        """Star values > 12 should not be captured as stars."""
        nums, etoiles = _detect_grille_em("18-22-33-41-46 ☆13-14☆")
        # 13 and 14 are > 12, so not valid stars. They become boules → 7 numbers → None
        assert nums is None


# ═══════════════════════════════════════════════════════
# FIX 4 — Remerciements + conseil (10 tests)
# ═══════════════════════════════════════════════════════


class TestRemerciementsConseil:
    """FIX 4: Extended compliment detection + conseil → generation."""

    def test_je_vous_remercie(self):
        result = _detect_compliment("Je vous remercie beaucoup")
        assert result == "merci"

    def test_je_te_remercie(self):
        result = _detect_compliment("Je te remercie")
        assert result == "merci"

    def test_merci_existing_still_works(self):
        result = _detect_compliment("Merci")
        assert result == "merci"

    def test_thank_you_very_much(self):
        result = _detect_compliment("Thank you very much for your help")
        assert result == "merci"

    def test_muchas_gracias(self):
        result = _detect_compliment("Muchas gracias por tu ayuda")
        assert result == "merci"

    def test_muito_obrigado(self):
        result = _detect_compliment("Muito obrigado pela ajuda")
        assert result == "merci"

    def test_vielen_dank(self):
        result = _detect_compliment("Vielen Dank fuer die Hilfe")
        assert result == "merci"

    def test_heel_erg_bedankt(self):
        result = _detect_compliment("Heel erg bedankt voor je hulp")
        assert result == "merci"

    def test_conseil_fr_generation(self):
        """'Que me conseillez-vous pour une grille' → generation detection."""
        assert _detect_generation("que me conseillez-vous pour une grille") is True

    def test_conseil_en_generation(self):
        """'What do you recommend' needs grid context to trigger."""
        # Without grid context, still matches because pattern doesn't require context
        assert _detect_generation("what do you recommend for my grid") is True


# ═══════════════════════════════════════════════════════
# FIX 5 — Game keyword alone (4 tests)
# ═══════════════════════════════════════════════════════


class TestGameKeywordAlone:
    """FIX 5: Game keyword alone detection."""

    def test_loto_alone(self):
        assert _detect_game_keyword_alone("Loto") is True

    def test_euromillions_alone(self):
        assert _detect_game_keyword_alone("Euromillions") is True

    def test_euromillions_question_mark(self):
        assert _detect_game_keyword_alone("Euromillions?") is True

    def test_loto_with_question(self):
        """Should NOT match when there's a real question."""
        assert _detect_game_keyword_alone("Loto dernier tirage") is False

    def test_euro_millions_space(self):
        assert _detect_game_keyword_alone("Euro millions") is True

    def test_case_insensitive(self):
        assert _detect_game_keyword_alone("LOTO") is True
        assert _detect_game_keyword_alone("euromillions") is True


# ═══════════════════════════════════════════════════════
# Pipeline integration — AFFIRMATION + GAME_KEYWORD phases
# ═══════════════════════════════════════════════════════

def _make_mock_history(n=3):
    """Create mock history with n messages (alternating user/assistant)."""
    history = []
    for i in range(n):
        msg = MagicMock()
        msg.role = "user" if i % 2 == 0 else "assistant"
        msg.content = f"Message {i}" if i % 2 == 0 else f"Response {i}"
        history.append(msg)
    return history


class TestPipelineAffirmation:
    """Integration tests: affirmation handling in pipelines."""

    @pytest.mark.asyncio
    async def test_affirmation_sans_contexte_loto(self):
        """Oui without history → invitation message."""
        from services.chat_pipeline import _prepare_chat_context
        with patch("services.chat_pipeline.load_prompt", return_value="system prompt"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake_key"}), \
             patch("services.stats_analysis.should_inject_pedagogical_context", return_value=False):
            result, ctx = await _prepare_chat_context("Oui", [], "home", None)
        assert result is not None
        assert ctx is None
        assert result["source"] == "hybride_affirmation"
        assert result["_chat_meta"]["phase"] == "AFFIRMATION_SANS_CONTEXTE"

    @pytest.mark.asyncio
    async def test_continuation_with_history_takes_priority(self):
        """Ok with history → Phase 0 continuation takes priority over AFFIRMATION."""
        history = _make_mock_history(4)
        from services.chat_pipeline import _prepare_chat_context
        with patch("services.chat_pipeline.load_prompt", return_value="system prompt"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake_key"}), \
             patch("services.stats_analysis.should_inject_pedagogical_context", return_value=False):
            result, ctx = await _prepare_chat_context("Ok", history, "home", None)
        # "Ok" with history: Phase 0 continuation catches it first (priority)
        assert ctx is not None
        assert ctx["_chat_meta"]["phase"] == "0"

    @pytest.mark.asyncio
    async def test_game_keyword_loto(self):
        """'Loto' alone → orientation message."""
        from services.chat_pipeline import _prepare_chat_context
        with patch("services.chat_pipeline.load_prompt", return_value="system prompt"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake_key"}), \
             patch("services.stats_analysis.should_inject_pedagogical_context", return_value=False):
            result, ctx = await _prepare_chat_context("Loto", [], "home", None)
        assert result is not None
        assert ctx is None
        assert result["source"] == "hybride_game_keyword"
        assert result["_chat_meta"]["phase"] == "GAME_KEYWORD"

    @pytest.mark.asyncio
    async def test_game_keyword_em(self):
        """'Euromillions' alone → orientation message EM."""
        from services.chat_pipeline_em import _prepare_chat_context_em
        with patch("services.chat_pipeline_em.load_prompt_em", return_value="system prompt"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake_key"}):
            result, ctx = await _prepare_chat_context_em("Euromillions", [], "home-em-fr", None, lang="fr")
        assert result is not None
        assert ctx is None
        assert result["source"] == "hybride_game_keyword"
        assert result["_chat_meta"]["phase"] == "GAME_KEYWORD"

    @pytest.mark.asyncio
    async def test_affirmation_em_en(self):
        """'Yes' without history in EM EN → invitation in English."""
        from services.chat_pipeline_em import _prepare_chat_context_em
        with patch("services.chat_pipeline_em.load_prompt_em", return_value="system prompt"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake_key"}):
            result, ctx = await _prepare_chat_context_em("Yes", [], "home-em-en", None, lang="en")
        assert result is not None
        assert "analyse" in result["response"].lower() or "help" in result["response"].lower()
        assert result["_chat_meta"]["phase"] == "AFFIRMATION_SANS_CONTEXTE"
        assert result["_chat_meta"]["lang"] == "en"
