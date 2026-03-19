"""
Tests for temporal filter bypass — V46 fix for the Phase 3 regression.

Bug: V43-bis removed the force_sql guard on Phase 3, so "top 10 en 2025"
would match classement → get_classement_numeros() (which has NO date_from
param) → returns all-time data → cancels force_sql → Phase SQL never runs.

Fix: restored `not force_sql` guard on Phase 3.  When temporal filter is
detected, Phase 3 is skipped and the pipeline falls through to Phase SQL
which handles the temporal constraint correctly.
"""

from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from services.chat_detectors import _has_temporal_filter, _detect_requete_complexe


# ═══════════════════════════════════════════════════════════════════════
# _has_temporal_filter detects the bug-triggering formulations
# ═══════════════════════════════════════════════════════════════════════

class TestTemporalDetectsComplexTemporal:
    """Ensure _has_temporal_filter returns True for all 'top N depuis ...' variants."""

    def test_top5_depuis_1er_janvier_2026(self):
        assert _has_temporal_filter("les 5 numéros les plus sortis depuis le 1er janvier 2026") is True

    def test_top5_depuis_1er_janvier_2026_seulement(self):
        assert _has_temporal_filter("les 5 numéros les plus sortis depuis le 1er janvier 2026 SEULEMENT") is True

    def test_top10_en_2025(self):
        assert _has_temporal_filter("top 10 des numéros les plus fréquents en 2025") is True

    def test_classement_cette_annee(self):
        assert _has_temporal_filter("quels numéros sont les plus sortis cette année") is True

    def test_top5_since_january_en(self):
        assert _has_temporal_filter("top 5 most drawn since January 2026") is True


# ═══════════════════════════════════════════════════════════════════════
# _detect_requete_complexe also matches these (proving the conflict)
# ═══════════════════════════════════════════════════════════════════════

class TestComplexAlsoMatches:
    """Prove that _detect_requete_complexe matches 'top 5 + temporal',
    which is exactly why the fallback was dangerous."""

    def test_top5_depuis_matches_classement(self):
        result = _detect_requete_complexe("les 5 numéros les plus sortis depuis le 1er janvier 2026")
        assert result is not None
        assert result["type"] == "classement"

    def test_top5_plus_frequents_matches(self):
        result = _detect_requete_complexe("top 5 des numéros les plus fréquents cette année")
        assert result is not None
        assert result["type"] == "classement"


# ═══════════════════════════════════════════════════════════════════════
# V46 Pipeline: force_sql=True → Phase 3 SKIPPED → Phase SQL handles it
# ═══════════════════════════════════════════════════════════════════════

class TestPipelinePhase3SkippedWhenForceSql:
    """V46 fix: When force_sql=True (temporal filter detected), Phase 3 must
    be SKIPPED so the pipeline falls through to Phase SQL, which handles
    temporal constraints correctly via TEXT2SQL."""

    @pytest.mark.asyncio
    async def test_loto_temporal_skips_phase3(self):
        """Loto: 'top 10 en 2025' → force_sql=True → Phase 3 skip → SQL called."""
        from services.chat_pipeline import _prepare_chat_context

        mock_client = MagicMock()

        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value=None), \
             patch("services.chat_pipeline._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline._detect_prochain_tirage", return_value=False), \
             patch("services.chat_pipeline._detect_tirage", return_value=None), \
             patch("services.chat_pipeline._detect_grille", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_out_of_range", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_numero", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_paires", return_value=False), \
             patch("services.chat_pipeline._detect_argent", return_value=False), \
             patch("services.chat_pipeline._detect_generation", return_value=False), \
             patch("services.chat_pipeline._generate_sql", new_callable=AsyncMock, return_value="SELECT 1") as mock_sql, \
             patch("services.chat_pipeline._execute_safe_sql", new_callable=AsyncMock, return_value=[{"n": 1}]), \
             patch("services.chat_pipeline._format_sql_result", return_value="result"), \
             patch("services.chat_pipeline.get_classement_numeros", new_callable=AsyncMock) as mock_classement, \
             patch("services.chat_pipeline._build_session_context", return_value=""):

            _, ctx = await _prepare_chat_context(
                "top 10 des numéros les plus fréquents en 2025",
                [], "accueil", mock_client,
            )

            # Phase 3 must NOT be called (force_sql=True skips it)
            mock_classement.assert_not_called()
            # Phase SQL must be called instead
            mock_sql.assert_called_once()

    @pytest.mark.asyncio
    async def test_loto_no_temporal_phase3_works(self):
        """Loto: 'top 10' without temporal → force_sql=False → Phase 3 runs normally."""
        from services.chat_pipeline import _prepare_chat_context

        mock_client = MagicMock()
        mock_data = {"items": [{"numero": 7}], "total_tirages": 100, "periode": "tout"}

        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value=None), \
             patch("services.chat_pipeline._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline._detect_prochain_tirage", return_value=False), \
             patch("services.chat_pipeline._detect_tirage", return_value=None), \
             patch("services.chat_pipeline._detect_grille", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_out_of_range", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_numero", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_paires", return_value=False), \
             patch("services.chat_pipeline._detect_argent", return_value=False), \
             patch("services.chat_pipeline._detect_generation", return_value=False), \
             patch("services.chat_pipeline.get_classement_numeros", new_callable=AsyncMock, return_value=mock_data) as mock_classement, \
             patch("services.chat_pipeline._build_session_context", return_value=""):

            _, ctx = await _prepare_chat_context(
                "top 10 des numéros les plus fréquents",
                [], "accueil", mock_client,
            )

            # Phase 3 SHOULD be called (no temporal filter → force_sql=False)
            mock_classement.assert_called_once()

    @pytest.mark.asyncio
    async def test_em_temporal_skips_phase3(self):
        """EM: 'top 5 since January 2026' → force_sql=True → Phase 3 skip → SQL called."""
        from services.chat_pipeline_em import _prepare_chat_context_em

        mock_client = MagicMock()

        with patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value=None), \
             patch("services.chat_pipeline_em._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline_em._detect_prochain_tirage_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_tirage", return_value=None), \
             patch("services.chat_pipeline_em._detect_grille_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_out_of_range_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_numero_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_paires_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_argent_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_generation", return_value=False), \
             patch("services.chat_pipeline_em._generate_sql_em", new_callable=AsyncMock, return_value="SELECT 1") as mock_sql, \
             patch("services.chat_pipeline_em._execute_safe_sql", new_callable=AsyncMock, return_value=[{"n": 1}]), \
             patch("services.chat_pipeline_em._format_sql_result", return_value="result"), \
             patch("services.chat_pipeline_em.get_classement_numeros", new_callable=AsyncMock) as mock_classement, \
             patch("services.chat_pipeline_em._build_session_context_em", return_value=""):

            _, ctx = await _prepare_chat_context_em(
                "top 5 since January 2026",
                [], "accueil-em", mock_client, "en",
            )

            mock_classement.assert_not_called()
            mock_sql.assert_called_once()

    @pytest.mark.asyncio
    async def test_em_no_temporal_phase3_works(self):
        """EM: 'top 5' without temporal → force_sql=False → Phase 3 runs."""
        from services.chat_pipeline_em import _prepare_chat_context_em

        mock_client = MagicMock()
        mock_data = {"items": [{"numero": 7}], "total_tirages": 100, "periode": "tout"}

        with patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value=None), \
             patch("services.chat_pipeline_em._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline_em._detect_prochain_tirage_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_tirage", return_value=None), \
             patch("services.chat_pipeline_em._detect_grille_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_out_of_range_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_numero_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_paires_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_argent_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_generation", return_value=False), \
             patch("services.chat_pipeline_em.get_classement_numeros", new_callable=AsyncMock, return_value=mock_data) as mock_classement, \
             patch("services.chat_pipeline_em._build_session_context_em", return_value=""):

            _, ctx = await _prepare_chat_context_em(
                "top 5 most drawn numbers",
                [], "accueil-em", mock_client, "en",
            )

            mock_classement.assert_called_once()

    @pytest.mark.asyncio
    async def test_loto_top5_depuis_janvier_forces_sql(self):
        """Loto: 'top 5 depuis janvier 2026' → force_sql → Phase SQL."""
        from services.chat_pipeline import _prepare_chat_context

        mock_client = MagicMock()

        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value=None), \
             patch("services.chat_pipeline._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline._detect_prochain_tirage", return_value=False), \
             patch("services.chat_pipeline._detect_tirage", return_value=None), \
             patch("services.chat_pipeline._detect_grille", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_out_of_range", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_numero", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_paires", return_value=False), \
             patch("services.chat_pipeline._detect_argent", return_value=False), \
             patch("services.chat_pipeline._detect_generation", return_value=False), \
             patch("services.chat_pipeline._generate_sql", new_callable=AsyncMock, return_value="SELECT 1") as mock_sql, \
             patch("services.chat_pipeline._execute_safe_sql", new_callable=AsyncMock, return_value=[{"n": 1}]), \
             patch("services.chat_pipeline._format_sql_result", return_value="result"), \
             patch("services.chat_pipeline.get_classement_numeros", new_callable=AsyncMock) as mock_classement, \
             patch("services.chat_pipeline._build_session_context", return_value=""):

            _, ctx = await _prepare_chat_context(
                "les 5 numéros les plus sortis depuis le 1er janvier 2026",
                [], "accueil", mock_client,
            )

            mock_classement.assert_not_called()
            mock_sql.assert_called_once()

    @pytest.mark.asyncio
    async def test_em_top5_depuis_janvier_forces_sql(self):
        """EM: 'top 5 depuis janvier 2026' → force_sql → Phase SQL."""
        from services.chat_pipeline_em import _prepare_chat_context_em

        mock_client = MagicMock()

        with patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline_em._detect_insulte", return_value=None), \
             patch("services.chat_pipeline_em._detect_compliment", return_value=None), \
             patch("services.chat_pipeline_em._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline_em._detect_prochain_tirage_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_tirage", return_value=None), \
             patch("services.chat_pipeline_em._detect_grille_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_out_of_range_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_numero_em", return_value=(None, None)), \
             patch("services.chat_pipeline_em._detect_paires_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_argent_em", return_value=False), \
             patch("services.chat_pipeline_em._detect_generation", return_value=False), \
             patch("services.chat_pipeline_em._generate_sql_em", new_callable=AsyncMock, return_value="SELECT 1") as mock_sql, \
             patch("services.chat_pipeline_em._execute_safe_sql", new_callable=AsyncMock, return_value=[{"n": 1}]), \
             patch("services.chat_pipeline_em._format_sql_result", return_value="result"), \
             patch("services.chat_pipeline_em.get_classement_numeros", new_callable=AsyncMock) as mock_classement, \
             patch("services.chat_pipeline_em._build_session_context_em", return_value=""):

            _, ctx = await _prepare_chat_context_em(
                "les 5 numéros les plus sortis depuis le 1er janvier 2026",
                [], "accueil-em", mock_client, "fr",
            )

            mock_classement.assert_not_called()
            mock_sql.assert_called_once()
