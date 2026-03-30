"""
Tests for Phase EVAL — Grid evaluation detection (V70).
Covers _detect_grid_evaluation() in base_chat_detectors.py
and pipeline integration in chat_pipeline.py / chat_pipeline_em.py.
"""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from services.base_chat_detectors import _detect_grid_evaluation


# ═══════════════════════════════════════════════════════════════════════
# Detection — French
# ═══════════════════════════════════════════════════════════════════════

class TestDetectGridEvalFR:

    def test_que_pensez_vous_de(self):
        r = _detect_grid_evaluation("que pensez-vous de 8 17 18 31 37", game="loto")
        assert r is not None
        assert r["numeros"] == [8, 17, 18, 31, 37]

    def test_que_penses_tu_de_with_chance(self):
        r = _detect_grid_evaluation(
            "que penses-tu de 8-17-18-31-37 et le 10 en chance", game="loto"
        )
        assert r is not None
        assert r["numeros"] == [8, 17, 18, 31, 37]
        assert r["chance"] == 10

    def test_votre_avis_sur(self):
        r = _detect_grid_evaluation("votre avis sur les numéros 3 12 25 33 44", game="loto")
        assert r is not None
        assert r["numeros"] == [3, 12, 25, 33, 44]

    def test_analyser_ces_numeros(self):
        r = _detect_grid_evaluation("peux-tu analyser ces numéros: 5 14 22 38 41", game="loto")
        assert r is not None
        assert r["numeros"] == [5, 14, 22, 38, 41]

    def test_evaluer_ma_grille(self):
        r = _detect_grid_evaluation("évaluer ma grille 7 19 23 36 49", game="loto")
        assert r is not None
        assert len(r["numeros"]) == 5

    def test_ces_numeros_sont_bons(self):
        r = _detect_grid_evaluation("ces numéros sont bons ? 2 11 28 34 47", game="loto")
        assert r is not None
        assert r["numeros"] == [2, 11, 28, 34, 47]

    def test_que_vaut_cette_grille(self):
        r = _detect_grid_evaluation("que vaut cette grille 6 15 21 30 45", game="loto")
        assert r is not None

    def test_verifier_mes_numeros(self):
        r = _detect_grid_evaluation("vérifier mes numéros 1 9 16 29 42", game="loto")
        assert r is not None

    def test_donne_ton_avis(self):
        r = _detect_grid_evaluation("donne-moi ton avis sur 4 13 27 35 48", game="loto")
        assert r is not None

    def test_production_log_message(self):
        """The exact message from the 28/03/2026 production log."""
        r = _detect_grid_evaluation(
            "Bonjour jai besoin de vos conseils que pensez de ses numéros "
            "pour le loto de ce soir 8-17-18-31-37 et le 10 en chance",
            game="loto",
        )
        assert r is not None
        assert r["numeros"] == [8, 17, 18, 31, 37]
        assert r["chance"] == 10


# ═══════════════════════════════════════════════════════════════════════
# Detection — English
# ═══════════════════════════════════════════════════════════════════════

class TestDetectGridEvalEN:

    def test_what_do_you_think(self):
        r = _detect_grid_evaluation("what do you think of 5 12 23 34 45", game="loto")
        assert r is not None
        assert r["numeros"] == [5, 12, 23, 34, 45]

    def test_check_my_numbers(self):
        r = _detect_grid_evaluation("check my numbers 3 18 29 37 44", game="loto")
        assert r is not None

    def test_evaluate_my_grid(self):
        r = _detect_grid_evaluation("evaluate my grid: 7 14 26 33 41", game="loto")
        assert r is not None

    def test_are_these_numbers_good(self):
        r = _detect_grid_evaluation("are these numbers good? 1 10 22 35 49", game="loto")
        assert r is not None

    def test_rate_my_combination(self):
        r = _detect_grid_evaluation("rate my combination 6 15 24 38 47", game="loto")
        assert r is not None


# ═══════════════════════════════════════════════════════════════════════
# Detection — Spanish
# ═══════════════════════════════════════════════════════════════════════

class TestDetectGridEvalES:

    def test_que_opinas(self):
        r = _detect_grid_evaluation("qué opinas de 4 18 25 33 47", game="em")
        assert r is not None

    def test_analizar_estos_numeros(self):
        r = _detect_grid_evaluation("analizar estos números 7 12 30 41 50", game="em")
        assert r is not None


# ═══════════════════════════════════════════════════════════════════════
# Detection — Portuguese
# ═══════════════════════════════════════════════════════════════════════

class TestDetectGridEvalPT:

    def test_o_que_achas(self):
        r = _detect_grid_evaluation("o que achas de 3 15 28 39 48", game="em")
        assert r is not None

    def test_analisar_estes_numeros(self):
        r = _detect_grid_evaluation("analisar estes números 6 11 22 35 44", game="em")
        assert r is not None


# ═══════════════════════════════════════════════════════════════════════
# Detection — German
# ═══════════════════════════════════════════════════════════════════════

class TestDetectGridEvalDE:

    def test_was_haeltst_du_von(self):
        r = _detect_grid_evaluation("was hältst du von 2 14 27 36 49", game="em")
        assert r is not None

    def test_diese_zahlen_analysieren(self):
        r = _detect_grid_evaluation("diese Zahlen analysieren: 8 19 31 42 50", game="em")
        assert r is not None


# ═══════════════════════════════════════════════════════════════════════
# Detection — Dutch
# ═══════════════════════════════════════════════════════════════════════

class TestDetectGridEvalNL:

    def test_wat_vind_je_van(self):
        r = _detect_grid_evaluation("wat vind je van 5 16 24 37 48", game="em")
        assert r is not None

    def test_mijn_nummers_beoordelen(self):
        r = _detect_grid_evaluation("mijn nummers beoordelen: 3 11 22 33 44", game="em")
        assert r is not None


# ═══════════════════════════════════════════════════════════════════════
# Extraction — numbers and secondary
# ═══════════════════════════════════════════════════════════════════════

class TestGridEvalExtraction:

    def test_loto_chance_extraction(self):
        r = _detect_grid_evaluation(
            "que pensez-vous de 5 12 23 34 45 chance 7", game="loto"
        )
        assert r is not None
        assert r["chance"] == 7

    def test_em_stars_extraction(self):
        r = _detect_grid_evaluation(
            "what do you think of 5 12 23 34 45 étoiles 3 et 9", game="em"
        )
        assert r is not None
        assert r["etoiles"] == [3, 9]

    def test_partial_grid_3_nums(self):
        """Partial grids (>= 3 nums) should be accepted."""
        r = _detect_grid_evaluation("que pensez-vous de 8 17 31", game="loto")
        assert r is not None
        assert r["numeros"] == [8, 17, 31]

    def test_partial_grid_2_nums_rejected(self):
        """Grids with < 3 numbers should be rejected."""
        r = _detect_grid_evaluation("que pensez-vous de 8 17", game="loto")
        assert r is None

    def test_loto_range_filtering(self):
        """Numbers outside Loto range (1-49) should be filtered."""
        r = _detect_grid_evaluation("que pensez-vous de 5 12 23 34 55", game="loto")
        assert r is not None
        assert 55 not in r["numeros"]
        assert len(r["numeros"]) == 4

    def test_em_range_50(self):
        """EM allows numbers up to 50."""
        r = _detect_grid_evaluation("what do you think of 5 12 23 34 50", game="em")
        assert r is not None
        assert 50 in r["numeros"]

    def test_deduplication(self):
        """Duplicate numbers should be deduplicated."""
        r = _detect_grid_evaluation("que pensez-vous de 5 5 12 23 34", game="loto")
        assert r is not None
        assert r["numeros"] == [5, 12, 23, 34]

    def test_max_5_nums(self):
        """Only first 5 valid numbers kept."""
        r = _detect_grid_evaluation(
            "que pensez-vous de 1 2 3 4 5 6 7", game="loto"
        )
        assert r is not None
        assert len(r["numeros"]) == 5
        assert r["numeros"] == [1, 2, 3, 4, 5]


# ═══════════════════════════════════════════════════════════════════════
# Non-detection — should NOT trigger Phase EVAL
# ═══════════════════════════════════════════════════════════════════════

class TestGridEvalNonDetection:

    def test_generation_request(self):
        """Grid generation should NOT trigger evaluation."""
        r = _detect_grid_evaluation("génère-moi une grille", game="loto")
        assert r is None

    def test_draw_result_question(self):
        """Asking about draw results should NOT trigger."""
        r = _detect_grid_evaluation("quel est le résultat du tirage de samedi", game="loto")
        assert r is None

    def test_simple_number_question(self):
        """Simple number question should NOT trigger."""
        r = _detect_grid_evaluation("le numéro 7 sort souvent ?", game="loto")
        assert r is None

    def test_no_numbers_in_message(self):
        """Evaluation words without numbers should NOT trigger."""
        r = _detect_grid_evaluation("que pensez-vous de ma grille", game="loto")
        assert r is None

    def test_too_few_numbers(self):
        """Only 2 numbers should NOT trigger."""
        r = _detect_grid_evaluation("que pensez-vous de 8 17", game="loto")
        assert r is None

    def test_ranking_question(self):
        """Ranking/classement question should NOT trigger."""
        r = _detect_grid_evaluation("quels sont les 5 numéros les plus fréquents", game="loto")
        assert r is None

    def test_generic_greeting(self):
        """Greeting should NOT trigger."""
        r = _detect_grid_evaluation("bonjour comment ça va", game="loto")
        assert r is None


# ═══════════════════════════════════════════════════════════════════════
# Pipeline integration — Phase EVAL enrichment
# ═══════════════════════════════════════════════════════════════════════

class TestPhaseEvalPipeline:

    @pytest.mark.asyncio
    async def test_loto_eval_sets_phase(self):
        """Grid evaluation message sets _phase to EVAL in Loto pipeline."""
        from services.chat_pipeline import _prepare_chat_context

        mock_analysis = {
            "numeros": [8, 17, 18, 31, 37],
            "chance": 10,
            "analyse": {
                "somme": 111, "somme_ok": True,
                "pairs": 2, "impairs": 3, "equilibre_pair_impair": True,
                "bas": 2, "hauts": 3, "equilibre_bas_haut": True,
                "dispersion": 29, "dispersion_ok": True,
                "consecutifs": 1,
                "numeros_chauds": [17, 31], "numeros_froids": [8],
                "numeros_neutres": [18, 37],
                "conformite_pct": 82,
                "badges": ["Équilibré", "Loto"],
            },
            "historique": {
                "deja_sortie": False,
                "exact_dates": [],
                "meilleure_correspondance": {
                    "nb_numeros_communs": 3,
                    "numeros_communs": [8, 17, 31],
                    "date": "2025-12-15",
                    "chance_match": False,
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
                 "numeros": [8, 17, 18, 31, 37], "chance": 10,
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
             patch("services.chat_pipeline._generate_sql", new_callable=AsyncMock, return_value=None), \
             patch("services.chat_pipeline._build_session_context", return_value=""), \
             patch("services.chat_pipeline._get_draw_count", new_callable=AsyncMock, return_value=980):
            early, ctx = await _prepare_chat_context(
                "que pensez-vous de 8-17-18-31-37 et le 10 en chance",
                [], "loto", MagicMock(), lang="fr",
            )

        assert early is None  # not an early return
        assert ctx is not None
        assert ctx["_chat_meta"]["phase"] == "EVAL"
        # Verify the enrichment context contains evaluation tag
        user_parts = ctx["contents"][-1]["parts"][0]["text"]
        assert "ÉVALUATION GRILLE UTILISATEUR" in user_parts

    @pytest.mark.asyncio
    async def test_eval_skipped_when_generation(self):
        """Phase EVAL should NOT trigger when Phase G already produced context."""
        from services.base_chat_detectors import _detect_grid_evaluation

        # If message triggers generation, eval should be skipped
        # (the pipeline guards: if not _generation_context)
        r = _detect_grid_evaluation("génère une grille avec 8 17 18 31 37", game="loto")
        # Even if eval matches, the pipeline skips it when _generation_context is set
        # This test verifies the detector itself — pipeline logic is tested above
        # A generation request with "génère" should not match eval patterns
        # because eval patterns look for opinion/analysis words
        assert r is None


# ═══════════════════════════════════════════════════════
# F10: Additional edge case tests
# ═══════════════════════════════════════════════════════

class TestGridEvalEdgeCases:
    """Edge cases for _detect_grid_evaluation."""

    def test_partial_grid_3_numbers(self):
        """Partial grid with only 3 numbers should still detect."""
        from services.base_chat_detectors import _detect_grid_evaluation
        r = _detect_grid_evaluation("que penses-tu de la grille 5 12 23", game="loto")
        assert r is not None
        assert len(r["numeros"]) == 3

    def test_numbers_out_of_range_filtered_loto(self):
        """Numbers outside Loto range (1-49) should be filtered out."""
        from services.base_chat_detectors import _detect_grid_evaluation
        r = _detect_grid_evaluation("évalue ma grille 5 12 55 99 23 34 45", game="loto")
        if r:
            for n in r["numeros"]:
                assert 1 <= n <= 49

    def test_no_numbers_no_detection(self):
        """Message without numbers should not trigger eval."""
        from services.base_chat_detectors import _detect_grid_evaluation
        r = _detect_grid_evaluation("que penses-tu de mon approche statistique", game="loto")
        assert r is None

    def test_em_grid_evaluation(self):
        """EM grid should detect with valid EM eval pattern."""
        from services.base_chat_detectors import _detect_grid_evaluation
        r = _detect_grid_evaluation("what do you think of 5 12 23 34 45", game="em")
        assert r is not None
        assert len(r["numeros"]) == 5

    def test_chance_detection(self):
        """Chance number should be extracted when present."""
        from services.base_chat_detectors import _detect_grid_evaluation
        r = _detect_grid_evaluation("évalue ma grille 5 12 23 34 45 chance 7", game="loto")
        assert r is not None
        assert r["chance"] == 7
