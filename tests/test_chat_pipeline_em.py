"""
Tests d'integration legere pour services/chat_pipeline_em.py.
Mock toutes les phases (Gemini, DB, stats) pour tester l'orchestration.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from google.genai import errors as genai_errors

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
        with patch("services.chat_pipeline_em.load_prompt_em", return_value=None):
            result = await handle_chat_em("bonjour", [], "accueil-em", MagicMock())
        assert result["source"] == "fallback"
        assert result["response"] == FALLBACK_RESPONSE_EM

    @pytest.mark.asyncio
    async def test_fallback_no_api_key(self):
        """Si cle API manquante → fallback."""
        with patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch.dict("os.environ", {}, clear=True):
            result = await handle_chat_em("bonjour", [], "accueil-em", MagicMock())
        assert result["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_insult_pure_returns_insult(self):
        """Insulte pure → early return hybride_insult."""
        with patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em._detect_insulte", return_value="insulte"):
            result = await handle_chat_em("t'es nul", [], "accueil-em", MagicMock())
        assert result["source"] == "hybride_insult"

    @pytest.mark.asyncio
    async def test_compliment_pure_returns_compliment(self):
        """Compliment sans question → early return hybride_compliment."""
        with patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value="compliment"), \
             patch("services.chat_pipeline_em._count_compliment_streak", return_value=0):
            result = await handle_chat_em("t'es genial", [], "accueil-em", MagicMock())
        assert result["source"] == "hybride_compliment"

    @pytest.mark.asyncio
    async def test_oor_returns_hybride_oor(self):
        """Numero hors range → hybride_oor."""
        with patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
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
    async def test_salutation_returns_local(self):
        """Salutation 'bonjour' (history vide) → early return hybride_salutation."""
        with patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value=None), \
             patch("services.chat_pipeline_em._detect_salutation", return_value=True):
            result = await handle_chat_em("bonjour", [], "accueil-em", MagicMock())
        assert result["source"] == "hybride_salutation"

    @pytest.mark.asyncio
    async def test_argent_returns_pedagogique(self):
        """Question argent/addiction → early return hybride_argent."""
        with patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value=None), \
             patch("services.chat_pipeline_em._detect_salutation", return_value=False), \
             patch("services.chat_pipeline_em._detect_generation", return_value=False), \
             patch("services.chat_pipeline_em._detect_grid_evaluation", return_value=None), \
             patch("services.chat_pipeline_em._detect_argent_em", return_value=True):
            result = await handle_chat_em("comment gagner à l'euromillions", [], "accueil-em", MagicMock())
        assert result["source"] == "hybride_argent"

    @pytest.mark.asyncio
    async def test_continuation_oui(self, mock_vertex_client):
        """'oui' with history → continuation mode, still goes to Gemini."""
        mock_client = MagicMock()

        history = [
            _msg("user", "le numéro 7 sort souvent en EM ?"),
            _msg("assistant", "Le 7 est sorti 45 fois."),
        ]

        # V131.C.2 — patch.dict GEM_API_KEY="fake" restauré : chat_pipeline_shared.py:611
        # legacy guard V131.A conservé pour chat_sql* (V131.D backlog) → test mock doit
        # fournir la var sinon fallback early en CI Docker clean env (vs local shell Jyppy).
        with mock_vertex_client() as vc, \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value=None), \
             patch("services.chat_pipeline_em._detect_salutation", return_value=False), \
             patch("services.chat_pipeline_em._is_short_continuation", return_value=True), \
             patch("services.chat_pipeline_em._detect_prochain_tirage_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_tirage", return_value=None), \
             patch("services.chat_pipeline_em._has_temporal_filter", return_value=False), \
             patch("services.chat_pipeline_em._detect_grille_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_requete_complexe_em", return_value=None), \
             patch("services.chat_pipeline_em._detect_out_of_range_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_numero_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._generate_sql_em", return_value=None), \
             patch("services.chat_pipeline_em._build_session_context_em", return_value=""):
            vc.set_response(text="Suite de la reponse EM")
            result = await handle_chat_em("oui", history, "accueil-em", mock_client)
        assert result["source"] == "gemini"

    @pytest.mark.asyncio
    async def test_gemini_ok(self, mock_vertex_client):
        """Flow normal → appel Gemini → source=gemini."""
        mock_client = MagicMock()

        # V131.C.2 — patch.dict GEM_API_KEY="fake" restauré : chat_pipeline_shared.py:611
        # legacy guard V131.A conservé pour chat_sql* (V131.D backlog) → test mock doit
        # fournir la var sinon fallback early en CI Docker clean env (vs local shell Jyppy).
        with mock_vertex_client() as vc, \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value=None), \
             patch("services.chat_pipeline_em._detect_salutation", return_value=False), \
             patch("services.chat_pipeline_em._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline_em._detect_prochain_tirage_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_tirage", return_value=None), \
             patch("services.chat_pipeline_em._has_temporal_filter", return_value=False), \
             patch("services.chat_pipeline_em._detect_grille_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_requete_complexe_em", return_value=None), \
             patch("services.chat_pipeline_em._detect_out_of_range_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_numero_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._generate_sql_em", return_value=None), \
             patch("services.chat_pipeline_em._build_session_context_em", return_value=""):
            vc.set_response(text="Voici les stats EM")
            result = await handle_chat_em("bonjour", [], "accueil-em", mock_client)
        assert result["source"] == "gemini"
        assert "stats EM" in result["response"]

    @pytest.mark.asyncio
    async def test_gemini_error_returns_fallback(self, mock_vertex_client):
        """Gemini ServerError (5xx) → fallback."""
        mock_client = MagicMock()

        # V131.C.2 — patch.dict GEM_API_KEY="fake" restauré : chat_pipeline_shared.py:611
        # legacy guard V131.A conservé pour chat_sql* (V131.D backlog) → test mock doit
        # fournir la var sinon fallback early en CI Docker clean env (vs local shell Jyppy).
        # Sans ce patch, fallback atteint mais pour la mauvaise raison (GEM_API_KEY vide
        # au lieu du ServerError voulu) — sémantique cassée, anti-régression V131.D.
        with mock_vertex_client() as vc, \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value=None), \
             patch("services.chat_pipeline_em._detect_salutation", return_value=False), \
             patch("services.chat_pipeline_em._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline_em._detect_prochain_tirage_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_tirage", return_value=None), \
             patch("services.chat_pipeline_em._has_temporal_filter", return_value=False), \
             patch("services.chat_pipeline_em._detect_grille_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_requete_complexe_em", return_value=None), \
             patch("services.chat_pipeline_em._detect_out_of_range_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_numero_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._generate_sql_em", return_value=None), \
             patch("services.chat_pipeline_em._build_session_context_em", return_value=""):
            vc.set_error(genai_errors.ServerError(
                500, {"error": {"code": 500, "message": "test", "status": "INTERNAL"}},
            ))
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
    async def test_pitch_ok(self, mock_vertex_client):
        """Pitch complet avec mock Gemini → success."""
        mock_client = MagicMock()

        with mock_vertex_client() as vc, \
             patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch("services.chat_pipeline_em.prepare_grilles_pitch_context",
                   new_callable=AsyncMock, return_value="ctx"):
            # V127 — clear cache pour ne pas avoir un hit d'un test précédent
            from services.gemini_cache import pitch_cache
            pitch_cache.clear()
            vc.set_response(text='{"pitchs": ["Super grille !"]}')
            result = await handle_pitch_em(
                [_grille([5, 15, 25, 35, 45])],
                mock_client,
            )
        assert result["success"] is True
        assert result["data"]["pitchs"] == ["Super grille !"]

    @pytest.mark.asyncio
    async def test_pitch_no_prompt(self):
        # V127 — clear cache (pollution possible depuis test_pitch_ok même grille)
        from services.gemini_cache import pitch_cache
        pitch_cache.clear()
        with patch("services.chat_pipeline_em.load_prompt_em", return_value=None), \
             patch("services.chat_pipeline_em.prepare_grilles_pitch_context", new_callable=AsyncMock, return_value="ctx"):
            result = await handle_pitch_em(
                [_grille([5, 15, 25, 35, 45])],
                MagicMock(),
            )
        assert result["success"] is False
        assert result["status_code"] == 500
