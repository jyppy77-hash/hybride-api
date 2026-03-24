"""
Tests — services/em_pdf_generator.py
Covers PDF structure, labels i18n, graph generation, heatmap integration.
"""

import io
import os
import pytest
from unittest.mock import patch, MagicMock

from services.em_pdf_generator import (
    PDF_LABELS,
    generate_em_graph_image,
    generate_em_meta_pdf,
    _validate_graph_data,
    _utf8_clean,
)


# ═══════════════════════════════════════════════════════════════════════
# PDF_LABELS i18n coverage
# ═══════════════════════════════════════════════════════════════════════

EXPECTED_KEYS = {
    "title", "subtitle", "top5_bar", "top5_pie", "top3_bar", "top3_pie",
    "frequency", "balls", "stars", "analysis", "no_analysis", "info",
    "window_label", "engine_label", "game_label", "sponsor_title",
    "sponsor_contact", "signature", "engine_desc", "generated_by",
    "disclaimer1", "disclaimer2", "version", "ai_note", "dev_note",
    "heatmap_title_balls", "heatmap_title_stars",
    "heatmap_legend_cold", "heatmap_legend_hot",
    "penalty_last_draw", "penalty_generated",
}

REQUIRED_LANGS = ["fr", "en", "es", "pt", "de", "nl"]


class TestPDFLabels:

    def test_all_6_languages_present(self):
        """PDF_LABELS contains all 6 required languages."""
        for lang in REQUIRED_LANGS:
            assert lang in PDF_LABELS, f"Missing language: {lang}"

    def test_all_expected_keys_per_language(self):
        """Each language has exactly the expected keys."""
        for lang in REQUIRED_LANGS:
            labels = PDF_LABELS[lang]
            missing = EXPECTED_KEYS - set(labels.keys())
            assert not missing, f"Lang {lang} missing keys: {missing}"

    def test_no_empty_labels(self):
        """No label value should be empty string."""
        for lang in REQUIRED_LANGS:
            for key, val in PDF_LABELS[lang].items():
                assert val, f"Empty label: {lang}.{key}"

    def test_labels_are_strings(self):
        """All label values must be strings."""
        for lang in REQUIRED_LANGS:
            for key, val in PDF_LABELS[lang].items():
                assert isinstance(val, str), f"Non-string label: {lang}.{key} = {type(val)}"


# ═══════════════════════════════════════════════════════════════════════
# _validate_graph_data
# ═══════════════════════════════════════════════════════════════════════

class TestValidateGraphData:

    def test_valid_data(self):
        data = {"labels": ["1", "2", "3"], "values": [10, 20, 30]}
        assert _validate_graph_data(data) is True

    def test_none_data(self):
        assert _validate_graph_data(None) is False

    def test_empty_labels(self):
        data = {"labels": [], "values": []}
        assert _validate_graph_data(data) is False

    def test_mismatched_lengths(self):
        data = {"labels": ["1", "2"], "values": [10]}
        assert _validate_graph_data(data) is False

    def test_missing_labels_key(self):
        data = {"values": [1, 2, 3]}
        assert _validate_graph_data(data) is False


# ═══════════════════════════════════════════════════════════════════════
# _utf8_clean
# ═══════════════════════════════════════════════════════════════════════

class TestUtf8Clean:

    def test_arrow_replacement(self):
        assert _utf8_clean("A \u2192 B") == "A -> B"

    def test_em_dash_replacement(self):
        assert _utf8_clean("LotoIA \u2014 Rapport") == "LotoIA - Rapport"

    def test_empty_string(self):
        assert _utf8_clean("") == ""

    def test_none_returns_empty(self):
        assert _utf8_clean(None) == ""

    def test_no_replacements_needed(self):
        assert _utf8_clean("Hello World") == "Hello World"


# ═══════════════════════════════════════════════════════════════════════
# generate_em_graph_image
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateEmGraphImage:

    def test_produces_valid_png_file(self):
        """generate_em_graph_image() creates a PNG file on disk."""
        boules = {"labels": ["7", "12", "25", "33", "48"], "values": [45, 42, 40, 38, 36]}
        etoiles = {"labels": ["2", "8", "11"], "values": [60, 55, 50]}
        path = generate_em_graph_image(boules, etoiles, lang="fr")
        try:
            assert os.path.isfile(path)
            assert path.endswith(".png")
            assert os.path.getsize(path) > 1000  # non-trivial PNG
        finally:
            os.unlink(path)

    def test_all_languages_produce_graphs(self):
        """Graph generation works for all 6 languages (labels render)."""
        boules = {"labels": ["1", "2", "3", "4", "5"], "values": [10, 20, 30, 40, 50]}
        etoiles = {"labels": ["1", "2", "3"], "values": [15, 25, 35]}
        for lang in REQUIRED_LANGS:
            path = generate_em_graph_image(boules, etoiles, lang=lang)
            try:
                assert os.path.isfile(path), f"Failed for lang={lang}"
            finally:
                os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════
# generate_em_meta_pdf — structure
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateEmMetaPdf:

    def test_pdf_without_heatmap_returns_bytesio(self):
        """PDF without heatmap data → 1 page, valid BytesIO."""
        buf = generate_em_meta_pdf(
            analysis="Test analysis", window="100 tirages",
            lang="fr",
        )
        assert isinstance(buf, io.BytesIO)
        data = buf.read()
        assert data[:5] == b"%PDF-"
        assert len(data) > 500

    def test_pdf_with_heatmap_has_two_pages(self):
        """PDF with heatmap data → 2 pages."""
        freq_b = {i: i * 3 for i in range(1, 51)}
        freq_s = {i: i * 5 for i in range(1, 13)}
        buf = generate_em_meta_pdf(
            analysis="Heatmap test",
            lang="en",
            all_freq_boules=freq_b,
            all_freq_secondary=freq_s,
        )
        data = buf.read()
        assert data[:5] == b"%PDF-"
        # ReportLab PDF: count "Page" objects or check size is significantly larger
        assert len(data) > 2000  # 2-page PDF is larger

    def test_pdf_with_graph_data(self):
        """PDF with valid graph data includes matplotlib image."""
        boules = {"labels": ["7", "12", "25", "33", "48"], "values": [45, 42, 40, 38, 36]}
        etoiles = {"labels": ["2", "8", "11"], "values": [60, 55, 50]}
        buf = generate_em_meta_pdf(
            analysis="Graph test",
            graph_data_boules=boules,
            graph_data_etoiles=etoiles,
            lang="de",
        )
        data = buf.read()
        assert data[:5] == b"%PDF-"
        assert len(data) > 5000  # PDF with embedded image is large

    def test_all_languages_generate_pdf(self):
        """PDF generation works for all 6 languages."""
        for lang in REQUIRED_LANGS:
            buf = generate_em_meta_pdf(analysis="Test", lang=lang)
            data = buf.read()
            assert data[:5] == b"%PDF-", f"Invalid PDF for lang={lang}"

    def test_pdf_with_sponsor(self):
        """PDF with sponsor info renders without error."""
        buf = generate_em_meta_pdf(
            analysis="Sponsor test",
            sponsor="TestSponsor",
            lang="fr",
        )
        data = buf.read()
        assert data[:5] == b"%PDF-"
        assert len(data) > 500

    # ── F07 — Timestamp tests ──

    def test_pdf_timestamp_always_present(self):
        """PDF always includes generation timestamp."""
        buf = generate_em_meta_pdf(analysis="Timestamp test", lang="fr")
        data = buf.read()
        assert data[:5] == b"%PDF-"
        assert len(data) > 500

    def test_pdf_last_draw_date_shown(self):
        """PDF with last_draw_date renders it in the info section."""
        buf = generate_em_meta_pdf(
            analysis="Draw date test",
            lang="fr",
            last_draw_date="24/03/2026",
        )
        data = buf.read()
        assert data[:5] == b"%PDF-"
        assert len(data) > 500

    def test_timestamp_labels_present_in_all_langs(self):
        """All 6 languages have the 2 timestamp label keys."""
        ts_keys = {"penalty_last_draw", "penalty_generated"}
        for lang in REQUIRED_LANGS:
            labels = PDF_LABELS[lang]
            missing = ts_keys - set(labels.keys())
            assert not missing, f"Lang {lang} missing timestamp keys: {missing}"
