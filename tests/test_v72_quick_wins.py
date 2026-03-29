"""
Tests for V72 Sprint Quick Wins: F01, F03, F04, F05, F07, F08, F09, F10.
"""

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest


# ═══════════════════════════════════════════════════════════
# Shared test helpers
# ═══════════════════════════════════════════════════════════

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
        s.enter_context(patch("services.chat_pipeline_em._get_draw_count",
                              new_callable=AsyncMock, return_value=500))
        yield


def _loto_pipeline_patches(**overrides):
    """Return patches for Loto pipeline."""
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


# ═══════════════════════════════════════════════════════════
# F01 — Phase I EM: _has_question multilingual keywords ES/PT/DE/NL
# ═══════════════════════════════════════════════════════════

class TestF01PhaseIEmMultilangKeywords:

    @pytest.mark.asyncio
    async def test_insult_plus_es_keyword_em(self):
        """Insult + ES keyword 'sorteo' in EM → prefix, not early return."""
        from services.chat_pipeline_em import _prepare_chat_context_em
        with em_patches(**{
            "services.chat_pipeline_em._detect_insulte": "insulte",
            "services.chat_pipeline_em._count_insult_streak": 0,
        }):
            early, ctx = await _prepare_chat_context_em(
                "idiota ultimo sorteo", [], "euromillions", MagicMock(), lang="es",
            )
        assert early is None  # insult+question → prefix, proceeds to Gemini

    @pytest.mark.asyncio
    async def test_insult_plus_pt_keyword_em(self):
        """Insult + PT keyword 'sorteio' in EM → prefix, not early return."""
        from services.chat_pipeline_em import _prepare_chat_context_em
        with em_patches(**{
            "services.chat_pipeline_em._detect_insulte": "insulte",
            "services.chat_pipeline_em._count_insult_streak": 0,
        }):
            early, ctx = await _prepare_chat_context_em(
                "idiota ultimo sorteio", [], "euromillions", MagicMock(), lang="pt",
            )
        assert early is None

    @pytest.mark.asyncio
    async def test_insult_plus_de_keyword_em(self):
        """Insult + DE keyword 'ziehung' in EM → prefix, not early return."""
        from services.chat_pipeline_em import _prepare_chat_context_em
        with em_patches(**{
            "services.chat_pipeline_em._detect_insulte": "insulte",
            "services.chat_pipeline_em._count_insult_streak": 0,
        }):
            early, ctx = await _prepare_chat_context_em(
                "dummkopf letzte ziehung", [], "euromillions", MagicMock(), lang="de",
            )
        assert early is None

    @pytest.mark.asyncio
    async def test_insult_plus_nl_keyword_em(self):
        """Insult + NL keyword 'trekking' in EM → prefix, not early return."""
        from services.chat_pipeline_em import _prepare_chat_context_em
        with em_patches(**{
            "services.chat_pipeline_em._detect_insulte": "insulte",
            "services.chat_pipeline_em._count_insult_streak": 0,
        }):
            early, ctx = await _prepare_chat_context_em(
                "idioot laatste trekking", [], "euromillions", MagicMock(), lang="nl",
            )
        assert early is None


# ═══════════════════════════════════════════════════════════
# F05 — Loto AFFIRMATION/GAME_KEYWORD i18n
# ═══════════════════════════════════════════════════════════

class TestF05LotoAffirmationI18n:

    @pytest.mark.asyncio
    async def test_affirmation_en(self):
        """Affirmation with lang=en returns English response."""
        from services.chat_pipeline import _prepare_chat_context
        with loto_patches(**{
            "services.chat_pipeline._is_affirmation_simple": True,
        }):
            early, ctx = await _prepare_chat_context(
                "ok", [], "loto", MagicMock(), lang="en",
            )
        assert early is not None
        assert "I'm ready" in early["response"]

    @pytest.mark.asyncio
    async def test_affirmation_fr(self):
        """Affirmation with lang=fr returns French response."""
        from services.chat_pipeline import _prepare_chat_context
        with loto_patches(**{
            "services.chat_pipeline._is_affirmation_simple": True,
        }):
            early, ctx = await _prepare_chat_context(
                "ok", [], "loto", MagicMock(), lang="fr",
            )
        assert early is not None
        assert "analyser" in early["response"]

    @pytest.mark.asyncio
    async def test_game_keyword_en(self):
        """Game keyword with lang=en returns English response."""
        from services.chat_pipeline import _prepare_chat_context
        with loto_patches(**{
            "services.chat_pipeline._detect_game_keyword_alone": True,
        }):
            early, ctx = await _prepare_chat_context(
                "loto", [], "loto", MagicMock(), lang="en",
            )
        assert early is not None
        assert "Welcome" in early["response"]

    @pytest.mark.asyncio
    async def test_game_keyword_es(self):
        """Game keyword with lang=es returns Spanish response."""
        from services.chat_pipeline import _prepare_chat_context
        with loto_patches(**{
            "services.chat_pipeline._detect_game_keyword_alone": True,
        }):
            early, ctx = await _prepare_chat_context(
                "loto", [], "loto", MagicMock(), lang="es",
            )
        assert early is not None
        assert "Bienvenido" in early["response"]

    def test_loto_affirmation_dict_6_langs(self):
        """Loto affirmation dict has 6 languages."""
        from services.chat_responses_loto import _AFFIRMATION_INVITATION_LOTO
        assert len(_AFFIRMATION_INVITATION_LOTO) == 6

    def test_loto_game_keyword_dict_6_langs(self):
        """Loto game keyword dict has 6 languages."""
        from services.chat_responses_loto import _GAME_KEYWORD_INVITATION_LOTO
        assert len(_GAME_KEYWORD_INVITATION_LOTO) == 6


# ═══════════════════════════════════════════════════════════
# F07 — Tirage introuvable i18n
# ═══════════════════════════════════════════════════════════

class TestF07TirageNotFoundI18n:

    @pytest.mark.asyncio
    async def test_tirage_not_found_en_loto(self):
        """Tirage introuvable with lang=en → English message (Loto)."""
        from services.chat_pipeline import _prepare_chat_context
        with loto_patches(**{
            "services.chat_pipeline._detect_tirage": "2025-01-01",
        }):
            with patch("services.chat_pipeline._get_tirage_data",
                       new_callable=AsyncMock, return_value=None):
                early, ctx = await _prepare_chat_context(
                    "tirage du 1er janvier 2025", [], "loto", MagicMock(), lang="en",
                )
        # Not an early return, but enrichment_context should be set in English
        assert early is None
        assert ctx is not None

    @pytest.mark.asyncio
    async def test_tirage_not_found_fr_loto(self):
        """Tirage introuvable with lang=fr → French message (Loto)."""
        from services.chat_pipeline import _prepare_chat_context
        with loto_patches(**{
            "services.chat_pipeline._detect_tirage": "2025-01-01",
        }):
            with patch("services.chat_pipeline._get_tirage_data",
                       new_callable=AsyncMock, return_value=None):
                early, ctx = await _prepare_chat_context(
                    "tirage du 1er janvier 2025", [], "loto", MagicMock(), lang="fr",
                )
        assert early is None
        assert ctx is not None


# ═══════════════════════════════════════════════════════════
# F09 — Gemini fallback prompt test
# ═══════════════════════════════════════════════════════════

class TestF09GeminiFallbackPrompt:

    @pytest.mark.asyncio
    async def test_fallback_prompt_when_file_missing(self):
        """When prompt file is missing, fallback FR prompt is used without crash."""
        from services.gemini import enrich_analysis
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Enriched text"}]}}]
        }
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("services.gemini.load_prompt", return_value=None):
            with patch("services.gemini.enrich_analysis_base",
                       new_callable=AsyncMock, return_value={"text": "ok"}) as mock_base:
                result = await enrich_analysis(
                    "Test analysis", "GLOBAL",
                    http_client=mock_client, lang="fr",
                )
                # Verify the fallback prompt was passed (contains the FR rules)
                call_args = mock_base.call_args
                prompt_arg = call_args[0][1]  # second positional arg is the prompt
                assert "RÈGLE ABSOLUE" in prompt_arg
                assert "expert en statistiques" in prompt_arg
