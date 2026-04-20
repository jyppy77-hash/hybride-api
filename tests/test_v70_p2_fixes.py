"""
Tests for V70 Sprint P2 fixes: F03, F04, F06, F13, F05.
"""

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest


# ═══════════════════════════════════════════════════════════
# Shared test helpers — reduce nesting depth
# ═══════════════════════════════════════════════════════════

def _loto_pipeline_patches(**overrides):
    """Return a combined context manager that patches all Loto pipeline phases."""
    defaults = {
        "services.chat_pipeline.load_prompt": "sys",
        "services.chat_pipeline._detect_insulte": None,
        "services.chat_pipeline._detect_compliment": None,
        "services.chat_pipeline._detect_salutation": False,
        "services.chat_pipeline._detect_generation": False,
        "services.chat_pipeline._detect_grid_evaluation": None,
        "services.chat_pipeline._detect_argent": False,
        "services.chat_pipeline._is_short_continuation": False,
        "services.chat_pipeline._detect_prochain_tirage": False,
        "services.chat_pipeline._detect_tirage": None,
        "services.chat_pipeline._has_temporal_filter": False,
        "services.chat_pipeline._detect_grille": (None, None),
        "services.chat_pipeline._detect_requete_complexe": None,
        "services.chat_pipeline._detect_out_of_range": (None, None),
        "services.chat_pipeline._detect_numero": (None, None),
        "services.chat_pipeline._build_session_context": "",
    }
    defaults.update(overrides)

    patches = [patch.dict("os.environ", {"GEM_API_KEY": "fake"})]
    for target, rv in defaults.items():
        patches.append(patch(target, return_value=rv))
    # Async mocks
    patches.append(patch("services.chat_pipeline._generate_sql",
                         new_callable=AsyncMock, return_value=None))
    patches.append(patch("services.chat_pipeline._get_draw_count",
                         new_callable=AsyncMock, return_value=980))

    return contextlib.ExitStack(), patches


@contextlib.contextmanager
def loto_patches(**overrides):
    """Combined context manager for Loto pipeline patches."""
    stack, patches = _loto_pipeline_patches(**overrides)
    with stack as s:
        for p in patches:
            s.enter_context(p)
        yield


@contextlib.contextmanager
def em_patches(**overrides):
    """Combined context manager for EM pipeline patches."""
    defaults = {
        "services.chat_pipeline_em.load_prompt_em": "sys",
        "services.chat_pipeline_em._detect_insulte": None,
        "services.chat_pipeline_em._detect_compliment": None,
        "services.chat_pipeline_em._detect_salutation": False,
        "services.chat_pipeline_em._detect_generation": False,
        "services.chat_pipeline_em._detect_grid_evaluation": None,
        "services.chat_pipeline_em._detect_argent_em": False,
        "services.chat_pipeline_em._is_short_continuation": False,
        "services.chat_pipeline_em._detect_prochain_tirage_em": False,
        "services.chat_pipeline_em._detect_tirage": None,
        "services.chat_pipeline_em._has_temporal_filter": False,
        "services.chat_pipeline_em._detect_grille_em": (None, None),
        "services.chat_pipeline_em._detect_requete_complexe_em": None,
        "services.chat_pipeline_em._detect_out_of_range_em": (None, None),
        "services.chat_pipeline_em._detect_numero_em": (None, None),
        "services.chat_pipeline_em._build_session_context_em": "",
    }
    defaults.update(overrides)

    stack = contextlib.ExitStack()
    with stack as s:
        s.enter_context(patch.dict("os.environ", {"GEM_API_KEY": "fake"}))
        for target, rv in defaults.items():
            s.enter_context(patch(target, return_value=rv))
        s.enter_context(patch("services.chat_pipeline_em._generate_sql_em",
                              new_callable=AsyncMock, return_value=None))
        s.enter_context(patch("services.chat_pipeline._get_draw_count",
                              new_callable=AsyncMock, return_value=500))
        yield


# ═══════════════════════════════════════════════════════════
# F03 — handle_pitch() Loto accepts lang parameter
# ═══════════════════════════════════════════════════════════

class TestF03HandlePitchLang:

    @pytest.mark.asyncio
    async def test_handle_pitch_accepts_lang_fr(self):
        from services.chat_pipeline import handle_pitch
        grille = SimpleNamespace(numeros=[5, 15, 25, 35, 45], chance=None,
                                 score_conformite=None, severity=None)
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": '{"pitchs": ["Bon"]}'}]}}]
        }
        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline.prepare_grilles_pitch_context",
                   new_callable=AsyncMock, return_value="ctx"), \
             patch("services.chat_pipeline.gemini_breaker_pitch") as mb:
            mb.call = AsyncMock(return_value=resp)
            result = await handle_pitch([grille], MagicMock(), lang="fr")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_handle_pitch_accepts_lang_en(self):
        from services.chat_pipeline import handle_pitch
        grille = SimpleNamespace(numeros=[5, 15, 25, 35, 45], chance=None,
                                 score_conformite=None, severity=None)
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": '{"pitchs": ["Good"]}'}]}}]
        }
        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline.prepare_grilles_pitch_context",
                   new_callable=AsyncMock, return_value="ctx"), \
             patch("services.chat_pipeline.gemini_breaker_pitch") as mb:
            mb.call = AsyncMock(return_value=resp)
            result = await handle_pitch([grille], MagicMock(), lang="en")
        assert result["success"] is True


# ═══════════════════════════════════════════════════════════
# F04 — gemini.py enrichment i18n system instructions
# ═══════════════════════════════════════════════════════════

class TestF04EnrichmentI18n:

    def test_enrichment_instructions_has_6_langs(self):
        from services.gemini import _ENRICHMENT_INSTRUCTIONS
        for lang_code in ("fr", "en", "es", "pt", "de", "nl"):
            assert lang_code in _ENRICHMENT_INSTRUCTIONS

    def test_enrichment_instructions_fr_has_accents(self):
        from services.gemini import _ENRICHMENT_INSTRUCTIONS
        assert "accents" in _ENRICHMENT_INSTRUCTIONS["fr"].lower()

    def test_enrichment_instructions_en_is_english(self):
        from services.gemini import _ENRICHMENT_INSTRUCTIONS
        assert "English" in _ENRICHMENT_INSTRUCTIONS["en"]

    def test_enrich_analysis_signature_has_lang(self):
        import inspect
        from services.gemini import enrich_analysis
        sig = inspect.signature(enrich_analysis)
        assert "lang" in sig.parameters


# ═══════════════════════════════════════════════════════════
# F06 — Phase I _has_question multilingual keywords (Loto)
# ═══════════════════════════════════════════════════════════

class TestF06PhaseIMultilangKeywords:

    @pytest.mark.asyncio
    async def test_insult_plus_en_keyword(self):
        """Insult + EN keyword 'number' → not early return."""
        from services.chat_pipeline import _prepare_chat_context
        with loto_patches(**{
            "services.chat_pipeline._detect_insulte": "insulte",
            "services.chat_pipeline._count_insult_streak": 0,
            "services.chat_pipeline._get_insult_short": "Hey.",
        }):
            early, ctx = await _prepare_chat_context(
                "idiot what is the most frequent number", [], "loto", MagicMock(),
            )
        assert early is None  # insult+question → prefix, proceeds to Gemini

    @pytest.mark.asyncio
    async def test_insult_plus_es_keyword(self):
        """Insult + ES keyword 'sorteo' → not early return."""
        from services.chat_pipeline import _prepare_chat_context
        with loto_patches(**{
            "services.chat_pipeline._detect_insulte": "insulte",
            "services.chat_pipeline._count_insult_streak": 0,
            "services.chat_pipeline._get_insult_short": "Hey.",
        }):
            early, ctx = await _prepare_chat_context(
                "tonto ultimo sorteo", [], "loto", MagicMock(),
            )
        assert early is None

    @pytest.mark.asyncio
    async def test_insult_plus_de_keyword(self):
        """Insult + DE keyword 'ziehung' → not early return."""
        from services.chat_pipeline import _prepare_chat_context
        with loto_patches(**{
            "services.chat_pipeline._detect_insulte": "insulte",
            "services.chat_pipeline._count_insult_streak": 0,
            "services.chat_pipeline._get_insult_short": "Hey.",
        }):
            early, ctx = await _prepare_chat_context(
                "dummkopf letzte ziehung", [], "loto", MagicMock(),
            )
        assert early is None


# ═══════════════════════════════════════════════════════════
# F13 — Phase C _has_question_c multilingual keywords
# ═══════════════════════════════════════════════════════════

class TestF13PhaseCMultilangKeywords:

    @pytest.mark.asyncio
    async def test_compliment_plus_en_keyword_loto(self):
        """Compliment + EN keyword 'number' → not early return (Loto)."""
        from services.chat_pipeline import _prepare_chat_context
        with loto_patches(**{
            "services.chat_pipeline._detect_compliment": "compliment",
        }):
            early, ctx = await _prepare_chat_context(
                "great bot! what is the hottest number", [], "loto", MagicMock(),
            )
        assert early is None

    @pytest.mark.asyncio
    async def test_compliment_plus_nl_keyword_em(self):
        """Compliment + NL keyword 'nummers' → not early return (EM)."""
        from services.chat_pipeline_em import _prepare_chat_context_em
        with em_patches(**{
            "services.chat_pipeline_em._detect_compliment": "compliment",
        }):
            early, ctx = await _prepare_chat_context_em(
                "super bot! welke nummers zijn populair", [], "euromillions",
                MagicMock(), lang="nl",
            )
        assert early is None


# ═══════════════════════════════════════════════════════════
# F05 — i18n dicts moved to chat_responses_em_multilang.py
# ═══════════════════════════════════════════════════════════

class TestF05I18nDictsMoved:

    def test_affirmation_invitation_importable(self):
        from services.chat_responses_em_multilang import _AFFIRMATION_INVITATION_EM
        assert isinstance(_AFFIRMATION_INVITATION_EM, dict)
        assert len(_AFFIRMATION_INVITATION_EM) == 6

    def test_game_keyword_invitation_importable(self):
        from services.chat_responses_em_multilang import _GAME_KEYWORD_INVITATION_EM
        assert isinstance(_GAME_KEYWORD_INVITATION_EM, dict)
        assert len(_GAME_KEYWORD_INVITATION_EM) == 6

    def test_pipeline_em_still_uses_dicts(self):
        import services.chat_pipeline_em as mod
        assert hasattr(mod, "_AFFIRMATION_INVITATION_EM")
        assert hasattr(mod, "_GAME_KEYWORD_INVITATION_EM")
