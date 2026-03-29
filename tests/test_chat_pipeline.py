"""
Tests d'integration legere pour services/chat_pipeline.py (Loto).
Mirror de test_chat_pipeline_em.py — mock toutes les phases (Gemini, DB, stats)
pour tester l'orchestration du pipeline Loto.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from services.chat_pipeline import handle_chat, handle_pitch
from services.chat_utils import FALLBACK_RESPONSE


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
# handle_chat — basic flow
# ═══════════════════════════════════════════════════════════════════════

class TestHandleChatLoto:

    @pytest.mark.asyncio
    async def test_fallback_no_prompt(self):
        """Si prompt introuvable → fallback."""
        with patch("services.chat_pipeline.load_prompt", return_value=None):
            result = await handle_chat("bonjour", [], "loto", MagicMock())
        assert result["source"] == "fallback"
        assert result["response"] == FALLBACK_RESPONSE

    @pytest.mark.asyncio
    async def test_fallback_no_api_key(self):
        """Si cle API manquante → fallback."""
        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {}, clear=True):
            result = await handle_chat("bonjour", [], "loto", MagicMock())
        assert result["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_insult_pure_returns_insult(self):
        """Insulte pure → early return hybride_insult (Phase I)."""
        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value="insulte"):
            result = await handle_chat("t'es nul", [], "loto", MagicMock())
        assert result["source"] == "hybride_insult"

    @pytest.mark.asyncio
    async def test_compliment_pure_returns_compliment(self):
        """Compliment sans question → early return hybride_compliment (Phase C)."""
        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value="compliment"), \
             patch("services.chat_pipeline._count_compliment_streak", return_value=0):
            result = await handle_chat("t'es genial", [], "loto", MagicMock())
        assert result["source"] == "hybride_compliment"

    @pytest.mark.asyncio
    async def test_salutation_returns_local(self):
        """Salutation 'bonjour' → early return hybride_salutation (Phase SALUTATION)."""
        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value=None), \
             patch("services.chat_pipeline._detect_salutation", return_value=True):
            result = await handle_chat("bonjour", [], "loto", MagicMock())
        assert result["source"] == "hybride_salutation"

    @pytest.mark.asyncio
    async def test_argent_returns_pedagogique(self):
        """Question argent → early return hybride_argent (Phase A)."""
        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value=None), \
             patch("services.chat_pipeline._detect_salutation", return_value=False), \
             patch("services.chat_pipeline._detect_generation", return_value=False), \
             patch("services.chat_pipeline._detect_grid_evaluation", return_value=None), \
             patch("services.chat_pipeline._detect_argent", return_value=True):
            result = await handle_chat("comment gagner au loto", [], "loto", MagicMock())
        assert result["source"] == "hybride_argent"

    @pytest.mark.asyncio
    async def test_oor_returns_hybride_oor(self):
        """Numero hors range → hybride_oor (Phase OOR)."""
        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value=None), \
             patch("services.chat_pipeline._detect_salutation", return_value=False), \
             patch("services.chat_pipeline._detect_generation", return_value=False), \
             patch("services.chat_pipeline._detect_grid_evaluation", return_value=None), \
             patch("services.chat_pipeline._detect_argent", return_value=False), \
             patch("services.chat_pipeline._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline._detect_prochain_tirage", return_value=False), \
             patch("services.chat_pipeline._detect_tirage", return_value=None), \
             patch("services.chat_pipeline._has_temporal_filter", return_value=False), \
             patch("services.chat_pipeline._detect_grille", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_requete_complexe", return_value=None), \
             patch("services.chat_pipeline._detect_out_of_range", return_value=(55, "boule_high")), \
             patch("services.chat_pipeline._count_oor_streak", return_value=0):
            result = await handle_chat("le numéro 55?", [], "loto", MagicMock())
        assert result["source"] == "hybride_oor"

    @pytest.mark.asyncio
    async def test_gemini_ok(self):
        """Flow normal → appel Gemini → source=gemini."""
        mock_client = MagicMock()

        async def fake_call(*args, **kwargs):
            return _make_gemini_response("Voici les stats Loto")

        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value=None), \
             patch("services.chat_pipeline._detect_salutation", return_value=False), \
             patch("services.chat_pipeline._detect_generation", return_value=False), \
             patch("services.chat_pipeline._detect_grid_evaluation", return_value=None), \
             patch("services.chat_pipeline._detect_argent", return_value=False), \
             patch("services.chat_pipeline._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline._detect_prochain_tirage", return_value=False), \
             patch("services.chat_pipeline._detect_tirage", return_value=None), \
             patch("services.chat_pipeline._has_temporal_filter", return_value=False), \
             patch("services.chat_pipeline._detect_grille", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_requete_complexe", return_value=None), \
             patch("services.chat_pipeline._detect_out_of_range", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_numero", return_value=(None, None)), \
             patch("services.chat_pipeline._generate_sql", return_value=None), \
             patch("services.chat_pipeline._build_session_context", return_value=""), \
             patch("services.chat_pipeline.gemini_breaker") as mock_breaker:
            mock_breaker.call = fake_call
            result = await handle_chat("bonjour", [], "loto", mock_client)
        assert result["source"] == "gemini"
        assert "stats Loto" in result["response"]

    @pytest.mark.asyncio
    async def test_gemini_error_returns_fallback(self):
        """Gemini HTTP 500 → fallback."""
        mock_client = MagicMock()

        async def fake_call(*args, **kwargs):
            return _make_gemini_response("", status=500)

        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value=None), \
             patch("services.chat_pipeline._detect_salutation", return_value=False), \
             patch("services.chat_pipeline._detect_generation", return_value=False), \
             patch("services.chat_pipeline._detect_grid_evaluation", return_value=None), \
             patch("services.chat_pipeline._detect_argent", return_value=False), \
             patch("services.chat_pipeline._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline._detect_prochain_tirage", return_value=False), \
             patch("services.chat_pipeline._detect_tirage", return_value=None), \
             patch("services.chat_pipeline._has_temporal_filter", return_value=False), \
             patch("services.chat_pipeline._detect_grille", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_requete_complexe", return_value=None), \
             patch("services.chat_pipeline._detect_out_of_range", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_numero", return_value=(None, None)), \
             patch("services.chat_pipeline._generate_sql", return_value=None), \
             patch("services.chat_pipeline._build_session_context", return_value=""), \
             patch("services.chat_pipeline.gemini_breaker") as mock_breaker:
            mock_breaker.call = fake_call
            result = await handle_chat("bonjour", [], "loto", mock_client)
        assert result["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_continuation_oui(self):
        """'oui' with history → continuation mode, still goes to Gemini."""
        mock_client = MagicMock()

        async def fake_call(*args, **kwargs):
            return _make_gemini_response("Suite de la reponse")

        history = [
            _msg("user", "le numéro 7 sort souvent ?"),
            _msg("assistant", "Le 7 est sorti 45 fois."),
        ]

        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value=None), \
             patch("services.chat_pipeline._detect_salutation", return_value=False), \
             patch("services.chat_pipeline._detect_generation", return_value=False), \
             patch("services.chat_pipeline._detect_grid_evaluation", return_value=None), \
             patch("services.chat_pipeline._detect_argent", return_value=False), \
             patch("services.chat_pipeline._is_short_continuation", return_value=True), \
             patch("services.chat_pipeline._detect_out_of_range", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_numero", return_value=(None, None)), \
             patch("services.chat_pipeline._generate_sql", return_value=None), \
             patch("services.chat_pipeline._build_session_context", return_value=""), \
             patch("services.chat_pipeline.gemini_breaker") as mock_breaker:
            mock_breaker.call = fake_call
            result = await handle_chat("oui", history, "loto", mock_client)
        assert result["source"] == "gemini"

    @pytest.mark.asyncio
    async def test_eval_phase_triggered(self):
        """Grid evaluation message → Phase EVAL with enrichment."""
        from services.chat_pipeline import _prepare_chat_context

        mock_analysis = {
            "numeros": [8, 17, 18, 31, 37], "chance": None,
            "analyse": {
                "somme": 111, "somme_ok": True,
                "pairs": 2, "impairs": 3, "equilibre_pair_impair": True,
                "bas": 2, "hauts": 3, "equilibre_bas_haut": True,
                "dispersion": 29, "dispersion_ok": True,
                "consecutifs": 1,
                "numeros_chauds": [17], "numeros_froids": [8],
                "numeros_neutres": [18, 31, 37],
                "conformite_pct": 78,
                "badges": ["Équilibré"],
            },
            "historique": {
                "deja_sortie": False, "exact_dates": [],
                "meilleure_correspondance": {
                    "nb_numeros_communs": 2,
                    "numeros_communs": [17, 31],
                    "date": "2025-11-01",
                },
            },
        }

        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value=None), \
             patch("services.chat_pipeline._detect_salutation", return_value=False), \
             patch("services.chat_pipeline._detect_generation", return_value=False), \
             patch("services.chat_pipeline._detect_grid_evaluation", return_value={
                 "numeros": [8, 17, 18, 31, 37], "chance": None,
             }), \
             patch("services.chat_pipeline.analyze_grille_for_chat", new_callable=AsyncMock, return_value=mock_analysis), \
             patch("services.chat_pipeline._detect_argent", return_value=False), \
             patch("services.chat_pipeline._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline._detect_prochain_tirage", return_value=False), \
             patch("services.chat_pipeline._detect_tirage", return_value=None), \
             patch("services.chat_pipeline._has_temporal_filter", return_value=False), \
             patch("services.chat_pipeline._detect_grille", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_requete_complexe", return_value=None), \
             patch("services.chat_pipeline._detect_out_of_range", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_numero", return_value=(None, None)), \
             patch("services.chat_pipeline._generate_sql", return_value=None), \
             patch("services.chat_pipeline._build_session_context", return_value=""), \
             patch("services.chat_pipeline._get_draw_count", new_callable=AsyncMock, return_value=980):
            early, ctx = await _prepare_chat_context(
                "que pensez-vous de 8 17 18 31 37", [], "loto", MagicMock(),
            )

        assert early is None
        assert ctx["_chat_meta"]["phase"] == "EVAL"


# ═══════════════════════════════════════════════════════════════════════
# handle_pitch — Loto
# ═══════════════════════════════════════════════════════════════════════

def _grille(nums, chance=None, score=None, severity=None):
    return SimpleNamespace(numeros=nums, chance=chance, score_conformite=score, severity=severity)


class TestHandlePitchLoto:

    @pytest.mark.asyncio
    async def test_validation_empty(self):
        result = await handle_pitch([], MagicMock())
        assert result["success"] is False
        assert result["status_code"] == 400

    @pytest.mark.asyncio
    async def test_validation_too_many(self):
        grilles = [_grille([1, 2, 3, 4, 5]) for _ in range(6)]
        result = await handle_pitch(grilles, MagicMock())
        assert result["success"] is False
        assert result["status_code"] == 400

    @pytest.mark.asyncio
    async def test_validation_wrong_count(self):
        result = await handle_pitch([_grille([1, 2, 3, 4])], MagicMock())
        assert result["success"] is False
        assert "5 numéros" in result["error"]

    @pytest.mark.asyncio
    async def test_validation_duplicates(self):
        result = await handle_pitch([_grille([1, 1, 3, 4, 5])], MagicMock())
        assert result["success"] is False
        assert "uniques" in result["error"]

    @pytest.mark.asyncio
    async def test_validation_boule_out_of_range(self):
        result = await handle_pitch([_grille([1, 2, 3, 4, 50])], MagicMock())
        assert result["success"] is False
        assert "entre 1 et 49" in result["error"]

    @pytest.mark.asyncio
    async def test_pitch_ok(self):
        """Pitch complet avec mock Gemini → success."""
        mock_client = MagicMock()
        gemini_resp = _make_gemini_response('{"pitchs": ["Super grille !"]}')

        async def fake_call(*args, **kwargs):
            return gemini_resp

        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline.prepare_grilles_pitch_context", new_callable=AsyncMock, return_value="ctx"), \
             patch("services.chat_pipeline.gemini_breaker") as mock_breaker:
            mock_breaker.call = fake_call
            result = await handle_pitch(
                [_grille([5, 15, 25, 35, 45])],
                mock_client,
            )
        assert result["success"] is True
        assert result["data"]["pitchs"] == ["Super grille !"]

    @pytest.mark.asyncio
    async def test_pitch_no_prompt(self):
        with patch("services.chat_pipeline.load_prompt", return_value=None), \
             patch("services.chat_pipeline.prepare_grilles_pitch_context", new_callable=AsyncMock, return_value="ctx"):
            result = await handle_pitch(
                [_grille([5, 15, 25, 35, 45])],
                MagicMock(),
            )
        assert result["success"] is False
        assert result["status_code"] == 500
