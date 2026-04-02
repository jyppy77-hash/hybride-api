"""
Tests d'integration legere pour services/chat_pipeline.py (Loto).
Mirror de test_chat_pipeline_em.py — mock toutes les phases (Gemini, DB, stats)
pour tester l'orchestration du pipeline Loto.
"""

import contextlib
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


# ═══════════════════════════════════════════════════════════════════════
# F12 V82 — Message truncation (MAX_MESSAGE_LENGTH)
# ═══════════════════════════════════════════════════════════════════════

class TestMessageTruncation:

    @pytest.mark.asyncio
    async def test_long_message_does_not_crash(self):
        """A 5000-char message must not crash the pipeline (hits fallback path)."""
        long_msg = "a" * 5000
        with patch("services.chat_pipeline.load_prompt", return_value=None):
            result = await handle_chat(long_msg, [], "loto", MagicMock())
        assert result["source"] == "fallback"
        assert "response" in result

    def test_max_message_length_constant(self):
        """MAX_MESSAGE_LENGTH is importable and equals 2000."""
        from services.chat_pipeline_shared import MAX_MESSAGE_LENGTH
        assert MAX_MESSAGE_LENGTH == 2000


# ═══════════════════════════════════════════════════════════════════════
# F02 V84 — Phase A skipped when message contains grid evaluation
# ═══════════════════════════════════════════════════════════════════════

def _loto_pipeline_patches(stack, **overrides):
    """Helper: apply common Loto pipeline patches via ExitStack, return mocks dict."""
    defaults = {
        "load_prompt": "sys",
        "_detect_insulte": None,
        "_detect_compliment": None,
        "_detect_salutation": False,
        "_detect_generation": False,
        "_detect_grid_evaluation": None,
        "_detect_argent": False,
        "_is_short_continuation": False,
        "_detect_prochain_tirage": False,
        "_detect_tirage": None,
        "_has_temporal_filter": False,
        "_detect_grille": (None, None),
        "_detect_requete_complexe": None,
        "_detect_cooccurrence_high_n": False,
        "_detect_triplets": False,
        "_detect_paires": False,
        "_detect_out_of_range": (None, None),
        "_detect_numero": (None, None),
        "_generate_sql": None,
        "_build_session_context": "",
    }
    defaults.update(overrides)
    stack.enter_context(patch.dict("os.environ", {"GEM_API_KEY": "fake"}))
    mocks = {}
    for name, rv in defaults.items():
        m = stack.enter_context(patch(f"services.chat_pipeline.{name}", return_value=rv))
        mocks[name] = m
    mocks["_get_draw_count"] = stack.enter_context(
        patch("services.chat_pipeline._get_draw_count", new_callable=AsyncMock, return_value=980)
    )
    return mocks


class TestPhaseAGridEvalGuard:

    @pytest.mark.asyncio
    async def test_grille_with_euros_not_blocked_by_phase_a(self):
        """F02: 'évalue ma grille ... euros' → Phase EVAL, NOT Phase A."""
        from services.chat_pipeline import _prepare_chat_context

        mock_analysis = {
            "numeros": [5, 12, 23, 34, 45], "chance": None,
            "analyse": {
                "somme": 119, "somme_ok": True,
                "pairs": 2, "impairs": 3, "equilibre_pair_impair": True,
                "bas": 2, "hauts": 3, "equilibre_bas_haut": True,
                "dispersion": 40, "dispersion_ok": True,
                "consecutifs": 0,
                "numeros_chauds": [12], "numeros_froids": [5],
                "numeros_neutres": [23, 34, 45],
                "conformite_pct": 82,
                "badges": ["Équilibré"],
            },
            "historique": {
                "deja_sortie": False, "exact_dates": [],
                "meilleure_correspondance": {
                    "nb_numeros_communs": 1,
                    "numeros_communs": [12],
                    "date": "2025-10-01",
                },
            },
        }

        with contextlib.ExitStack() as stack:
            _loto_pipeline_patches(stack,
                _detect_grid_evaluation={"numeros": [5, 12, 23, 34, 45], "chance": None},
                _detect_argent=True,
            )
            stack.enter_context(patch(
                "services.chat_pipeline.analyze_grille_for_chat",
                new_callable=AsyncMock, return_value=mock_analysis,
            ))
            early, ctx = await _prepare_chat_context(
                "évalue ma grille 5 12 23 34 45 pour 2 euros", [], "loto", MagicMock(),
            )

        # Must NOT be blocked by Phase A — must reach Phase EVAL
        assert early is None
        assert ctx["_chat_meta"]["phase"] == "EVAL"

    @pytest.mark.asyncio
    async def test_pure_argent_still_detected(self):
        """F02: Pure money question without grid → Phase A still works."""
        with contextlib.ExitStack() as stack:
            _loto_pipeline_patches(stack, _detect_argent=True)
            result = await handle_chat("comment gagner de l'argent au loto", [], "loto", MagicMock())
        assert result["source"] == "hybride_argent"


# ═══════════════════════════════════════════════════════════════════════
# F03 V84 — Pipeline integration tests for Phase P+ and Phase P
# ═══════════════════════════════════════════════════════════════════════

class TestPhasePPipelineIntegration:

    @pytest.mark.asyncio
    async def test_pipeline_paires_enriches_context(self):
        """F03: 'paires les plus fréquentes' → Phase P with pairs enrichment."""
        from services.chat_pipeline import _prepare_chat_context

        mock_pairs = [
            {"pair": (7, 12), "count": 45},
            {"pair": (3, 25), "count": 38},
        ]

        with contextlib.ExitStack() as stack:
            _loto_pipeline_patches(stack, _detect_paires=True)
            stack.enter_context(patch(
                "services.chat_pipeline.get_pair_correlations",
                new_callable=AsyncMock, return_value=mock_pairs,
            ))
            mock_fmt = stack.enter_context(patch(
                "services.chat_pipeline._format_pairs_context",
                return_value="[PAIRES]\n7-12: 45 fois",
            ))
            early, ctx = await _prepare_chat_context(
                "quelles sont les paires les plus fréquentes", [], "loto", MagicMock(),
            )

        assert early is None
        assert ctx["_chat_meta"]["phase"] == "P"
        mock_fmt.assert_called_once_with(mock_pairs)

    @pytest.mark.asyncio
    async def test_pipeline_triplets_enriches_context(self):
        """F03: 'triplets les plus sortis' → Phase P with triplets enrichment."""
        from services.chat_pipeline import _prepare_chat_context

        mock_triplets = [
            {"triplet": (1, 7, 12), "count": 22},
        ]

        with contextlib.ExitStack() as stack:
            _loto_pipeline_patches(stack, _detect_triplets=True)
            stack.enter_context(patch(
                "services.chat_pipeline.get_triplet_correlations",
                new_callable=AsyncMock, return_value=mock_triplets,
            ))
            mock_fmt = stack.enter_context(patch(
                "services.chat_pipeline._format_triplets_context",
                return_value="[TRIPLETS]\n1-7-12: 22 fois",
            ))
            early, ctx = await _prepare_chat_context(
                "les triplets les plus sortis", [], "loto", MagicMock(),
            )

        assert early is None
        assert ctx["_chat_meta"]["phase"] == "P"
        mock_fmt.assert_called_once_with(mock_triplets)

    @pytest.mark.asyncio
    async def test_pipeline_cooccurrence_high_n_redirects(self):
        """F03: 'quadruplets les plus fréquents' → Phase P+ early return."""
        with contextlib.ExitStack() as stack:
            _loto_pipeline_patches(stack,
                _detect_cooccurrence_high_n=True,
            )
            stack.enter_context(patch(
                "services.chat_pipeline._get_cooccurrence_high_n_response",
                return_value="Max triplets supportés.",
            ))
            result = await handle_chat(
                "les quadruplets les plus fréquents", [], "loto", MagicMock(),
            )

        assert result["source"] == "hybride_cooccurrence"

    @pytest.mark.asyncio
    async def test_pipeline_em_star_pairs_enriches_context(self):
        """F03: EM 'paires d'étoiles' → Phase P with star pairs enrichment."""
        from services.chat_pipeline_em import _prepare_chat_context_em

        mock_pairs = [{"pair": (3, 7), "count": 30}]
        mock_star_pairs = [{"pair": (1, 2), "count": 55}]

        em = "services.chat_pipeline_em"
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict("os.environ", {"GEM_API_KEY": "fake"}))
            for name, rv in [
                ("load_prompt_em", "sys"),
                ("_detect_insulte", None),
                ("_detect_compliment", None),
                ("_detect_salutation", False),
                ("_detect_generation", False),
                ("_detect_grid_evaluation", None),
                ("_detect_argent_em", False),
                ("_detect_country_em", False),
                ("_is_short_continuation", False),
                ("_detect_prochain_tirage_em", False),
                ("_detect_tirage", None),
                ("_has_temporal_filter", False),
                ("_detect_grille_em", (None, None)),
                ("_detect_requete_complexe_em", None),
                ("_detect_cooccurrence_high_n", False),
                ("_detect_triplets_em", False),
                ("_detect_paires_em", True),
                ("_detect_out_of_range_em", (None, None)),
                ("_detect_numero_em", (None, None)),
                ("_generate_sql_em", None),
                ("_build_session_context_em", ""),
            ]:
                stack.enter_context(patch(f"{em}.{name}", return_value=rv))
            stack.enter_context(patch(
                f"{em}.get_pair_correlations",
                new_callable=AsyncMock, return_value=mock_pairs,
            ))
            stack.enter_context(patch(
                f"{em}._format_pairs_context_em",
                return_value="[PAIRES]\n3-7: 30 fois",
            ))
            stack.enter_context(patch(
                f"{em}.get_star_pair_correlations",
                new_callable=AsyncMock, return_value=mock_star_pairs,
            ))
            mock_star_fmt = stack.enter_context(patch(
                f"{em}._format_star_pairs_context_em",
                return_value="[PAIRES ÉTOILES]\n1-2: 55 fois",
            ))
            stack.enter_context(patch(
                "services.chat_pipeline._get_draw_count",
                new_callable=AsyncMock, return_value=730,
            ))
            early, ctx = await _prepare_chat_context_em(
                "paires d'étoiles les plus fréquentes", [], "euromillions", MagicMock(), lang="fr",
            )

        assert early is None
        assert ctx["_chat_meta"]["phase"] == "P"
        mock_star_fmt.assert_called_once_with(mock_star_pairs)
