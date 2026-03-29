"""
Tests for gemini_shared.py — V71 R3c.
"""

from services.gemini_shared import ENRICHMENT_INSTRUCTIONS, enrich_analysis_base


class TestEnrichmentInstructions:
    """Shared instructions dict covers all 6 languages."""

    def test_all_6_langs(self):
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            assert lang in ENRICHMENT_INSTRUCTIONS
            assert len(ENRICHMENT_INSTRUCTIONS[lang]) > 50

    def test_fr_has_accents(self):
        assert "accents" in ENRICHMENT_INSTRUCTIONS["fr"]

    def test_en_no_french(self):
        assert "accents" not in ENRICHMENT_INSTRUCTIONS["en"]


class TestBackwardCompat:
    """Verify imports still work from original modules."""

    def test_loto_enrich_importable(self):
        from services.gemini import enrich_analysis
        assert callable(enrich_analysis)

    def test_em_enrich_importable(self):
        from services.em_gemini import enrich_analysis_em
        assert callable(enrich_analysis_em)

    def test_loto_instructions_alias(self):
        from services.gemini import _ENRICHMENT_INSTRUCTIONS
        assert _ENRICHMENT_INSTRUCTIONS is ENRICHMENT_INSTRUCTIONS

    def test_stream_still_in_gemini(self):
        from services.gemini import stream_gemini_chat
        assert callable(stream_gemini_chat)
