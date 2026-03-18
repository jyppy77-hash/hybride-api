"""
Tests for temporal filter bypass — regression for the bug where
'top 5 depuis janvier 2026' fell back to all-time stats via Phase 3
when Phase SQL failed.

The fix: when force_sql=True and SQL fails, do NOT fallback to
get_classement_numeros() (which has no date filter).
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
# Pipeline: force_sql=True → Phase SQL fail → NO fallback to Phase 3
# ═══════════════════════════════════════════════════════════════════════

class TestPipelinePhase3HandlesTemporalClassement:
    """V43-bis: When temporal filter is detected AND Phase 3 detects a classement,
    Phase 3 handles it natively (structured query) and cancels force_sql.
    Phase SQL is NOT needed for classement/categorie queries."""

    @pytest.mark.asyncio
    async def test_loto_phase3_handles_temporal_classement(self):
        """Loto pipeline: force_sql=True + Phase 3 detects classement → Phase 3 called, force_sql cancelled."""
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
             patch("services.chat_pipeline._generate_sql", new_callable=AsyncMock, return_value="NO_SQL"), \
             patch("services.chat_pipeline.get_classement_numeros", new_callable=AsyncMock) as mock_classement, \
             patch("services.chat_pipeline._build_session_context", return_value=""):

            _, ctx = await _prepare_chat_context(
                "les 5 numéros les plus sortis depuis le 1er janvier 2026",
                [], "accueil", mock_client,
            )

            # Phase 3 SHOULD handle this (classement detected) even with temporal filter
            mock_classement.assert_called_once()

    @pytest.mark.asyncio
    async def test_em_phase3_handles_temporal_classement(self):
        """EM pipeline: force_sql=True + Phase 3 detects classement → Phase 3 called, force_sql cancelled."""
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
             patch("services.chat_pipeline_em._generate_sql_em", new_callable=AsyncMock, return_value="NO_SQL"), \
             patch("services.chat_pipeline_em.get_classement_numeros", new_callable=AsyncMock) as mock_classement, \
             patch("services.chat_pipeline_em._build_session_context_em", return_value=""):

            _, ctx = await _prepare_chat_context_em(
                "top 5 since January 2026",
                [], "accueil-em", mock_client, "en",
            )

            # Phase 3 SHOULD handle this (classement detected) even with temporal filter
            mock_classement.assert_called_once()
