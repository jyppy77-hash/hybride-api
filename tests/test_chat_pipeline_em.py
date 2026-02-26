"""
Tests d'integration legere pour services/chat_pipeline_em.py.
Mock toutes les phases (Gemini, DB, stats) pour tester l'orchestration.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from services.chat_pipeline_em import handle_chat_em, handle_pitch_em
from services.chat_utils_em import FALLBACK_RESPONSE_EM


def _msg(role, content):
    return SimpleNamespace(role=role, content=content)


def _make_gemini_response(text, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = {
        "candidates": [{
            "content": {"parts": [{"text": text}]}
        }]
    }
    return resp


# ═══════════════════════════════════════════════════════════════════════
# handle_chat_em — basic flow
# ═══════════════════════════════════════════════════════════════════════

class TestHandleChatEM:

    @pytest.mark.asyncio
    async def test_fallback_no_prompt(self):
        """Si prompt introuvable → fallback."""
        with patch("services.chat_pipeline_em.load_prompt", return_value=None):
            result = await handle_chat_em("bonjour", [], "accueil-em", MagicMock())
        assert result["source"] == "fallback"
        assert result["response"] == FALLBACK_RESPONSE_EM

    @pytest.mark.asyncio
    async def test_fallback_no_api_key(self):
        """Si cle API manquante → fallback."""
        with patch("services.chat_pipeline_em.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {}, clear=True):
            result = await handle_chat_em("bonjour", [], "accueil-em", MagicMock())
        assert result["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_insult_pure_returns_insult(self):
        """Insulte pure → early return hybride_insult."""
        with patch("services.chat_pipeline_em.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em._detect_insulte", return_value="insulte"):
            result = await handle_chat_em("t'es nul", [], "accueil-em", MagicMock())
        assert result["source"] == "hybride_insult"

    @pytest.mark.asyncio
    async def test_compliment_pure_returns_compliment(self):
        """Compliment sans question → early return hybride_compliment."""
        with patch("services.chat_pipeline_em.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value="compliment"), \
             patch("services.chat_pipeline_em._count_compliment_streak", return_value=0):
            result = await handle_chat_em("t'es genial", [], "accueil-em", MagicMock())
        assert result["source"] == "hybride_compliment"

    @pytest.mark.asyncio
    async def test_oor_returns_hybride_oor(self):
        """Numero hors range → hybride_oor."""
        with patch("services.chat_pipeline_em.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value=None), \
             patch("services.chat_pipeline_em._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline_em._detect_prochain_tirage_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_tirage", return_value=None), \
             patch("services.chat_pipeline_em._has_temporal_filter", return_value=False), \
             patch("services.chat_pipeline_em._detect_grille_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_requete_complexe_em", return_value=None), \
             patch("services.chat_pipeline_em._detect_out_of_range_em", return_value=(99, "boule_high")), \
             patch("services.chat_pipeline_em._count_oor_streak_em", return_value=0):
            result = await handle_chat_em("le numéro 99?", [], "accueil-em", MagicMock())
        assert result["source"] == "hybride_oor"
        assert "99" in result["response"]

    @pytest.mark.asyncio
    async def test_gemini_ok(self):
        """Flow normal → appel Gemini → source=gemini."""
        mock_client = MagicMock()

        async def fake_call(*args, **kwargs):
            return _make_gemini_response("Voici les stats EM")

        with patch("services.chat_pipeline_em.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value=None), \
             patch("services.chat_pipeline_em._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline_em._detect_prochain_tirage_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_tirage", return_value=None), \
             patch("services.chat_pipeline_em._has_temporal_filter", return_value=False), \
             patch("services.chat_pipeline_em._detect_grille_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_requete_complexe_em", return_value=None), \
             patch("services.chat_pipeline_em._detect_out_of_range_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_numero_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._generate_sql_em", return_value=None), \
             patch("services.chat_pipeline_em._build_session_context_em", return_value=""), \
             patch("services.chat_pipeline_em.gemini_breaker") as mock_breaker:
            mock_breaker.call = fake_call
            result = await handle_chat_em("bonjour", [], "accueil-em", mock_client)
        assert result["source"] == "gemini"
        assert "stats EM" in result["response"]

    @pytest.mark.asyncio
    async def test_gemini_error_returns_fallback(self):
        """Gemini HTTP 500 → fallback."""
        mock_client = MagicMock()

        async def fake_call(*args, **kwargs):
            return _make_gemini_response("", status=500)

        with patch("services.chat_pipeline_em.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value=None), \
             patch("services.chat_pipeline_em._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline_em._detect_prochain_tirage_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_tirage", return_value=None), \
             patch("services.chat_pipeline_em._has_temporal_filter", return_value=False), \
             patch("services.chat_pipeline_em._detect_grille_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_requete_complexe_em", return_value=None), \
             patch("services.chat_pipeline_em._detect_out_of_range_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_numero_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._generate_sql_em", return_value=None), \
             patch("services.chat_pipeline_em._build_session_context_em", return_value=""), \
             patch("services.chat_pipeline_em.gemini_breaker") as mock_breaker:
            mock_breaker.call = fake_call
            result = await handle_chat_em("bonjour", [], "accueil-em", mock_client)
        assert result["source"] == "fallback"


# ═══════════════════════════════════════════════════════════════════════
# handle_pitch_em
# ═══════════════════════════════════════════════════════════════════════

def _grille(nums, etoiles=None, score=None, severity=None):
    return SimpleNamespace(numeros=nums, etoiles=etoiles, score_conformite=score, severity=severity)


class TestHandlePitchEM:

    @pytest.mark.asyncio
    async def test_validation_empty(self):
        result = await handle_pitch_em([], MagicMock())
        assert result["success"] is False
        assert result["status_code"] == 400

    @pytest.mark.asyncio
    async def test_validation_too_many(self):
        grilles = [_grille([1, 2, 3, 4, 5]) for _ in range(6)]
        result = await handle_pitch_em(grilles, MagicMock())
        assert result["success"] is False
        assert result["status_code"] == 400

    @pytest.mark.asyncio
    async def test_validation_wrong_count(self):
        result = await handle_pitch_em([_grille([1, 2, 3, 4])], MagicMock())
        assert result["success"] is False
        assert "5 numéros" in result["error"]

    @pytest.mark.asyncio
    async def test_validation_duplicates(self):
        result = await handle_pitch_em([_grille([1, 1, 3, 4, 5])], MagicMock())
        assert result["success"] is False
        assert "uniques" in result["error"]

    @pytest.mark.asyncio
    async def test_validation_boule_out_of_range(self):
        result = await handle_pitch_em([_grille([1, 2, 3, 4, 51])], MagicMock())
        assert result["success"] is False
        assert "entre 1 et 50" in result["error"]

    @pytest.mark.asyncio
    async def test_validation_etoile_out_of_range(self):
        result = await handle_pitch_em([_grille([1, 2, 3, 4, 5], etoiles=[1, 13])], MagicMock())
        assert result["success"] is False
        assert "étoiles entre 1 et 12" in result["error"]

    @pytest.mark.asyncio
    async def test_validation_etoile_duplicates(self):
        result = await handle_pitch_em([_grille([1, 2, 3, 4, 5], etoiles=[3, 3])], MagicMock())
        assert result["success"] is False
        assert "uniques" in result["error"]

    @pytest.mark.asyncio
    async def test_pitch_ok(self):
        """Pitch complet avec mock Gemini → success."""
        mock_client = MagicMock()
        gemini_resp = _make_gemini_response('{"pitchs": ["Super grille !"]}')

        async def fake_call(*args, **kwargs):
            return gemini_resp

        with patch("services.chat_pipeline_em.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em.prepare_grilles_pitch_context", return_value="ctx"), \
             patch("services.chat_pipeline_em.gemini_breaker") as mock_breaker:
            mock_breaker.call = fake_call
            result = await handle_pitch_em(
                [_grille([5, 15, 25, 35, 45])],
                mock_client,
            )
        assert result["success"] is True
        assert result["data"]["pitchs"] == ["Super grille !"]

    @pytest.mark.asyncio
    async def test_pitch_no_prompt(self):
        with patch("services.chat_pipeline_em.load_prompt", return_value=None), \
             patch("services.chat_pipeline_em.prepare_grilles_pitch_context", return_value="ctx"):
            result = await handle_pitch_em(
                [_grille([5, 15, 25, 35, 45])],
                MagicMock(),
            )
        assert result["success"] is False
        assert result["status_code"] == 500
