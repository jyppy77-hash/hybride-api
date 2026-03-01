"""
Tests — PDF Heatmap module + integration into EM & Loto PDF generators.
Covers Google 4-color gradient, text color, grid rendering, legend bar,
full PDF with/without heatmap data, page count verification,
PDF_LABELS coverage, schema acceptance.
"""

import io
import pytest
from unittest.mock import MagicMock, patch

from reportlab.lib.colors import Color


# ═══════════════════════════════════════════════════════════════════════
# Color gradient tests (Google Material Design: Blue->Green->Yellow->Red)
# ═══════════════════════════════════════════════════════════════════════

class TestFreqToColor:

    def test_min_equals_max_returns_mid_gradient(self):
        from services.pdf_heatmap import _freq_to_color
        c = _freq_to_color(5, 5, 5)
        # ratio=0.5 -> midpoint between Green and Yellow
        assert c.red > 0.3
        assert c.green > 0.3

    def test_cold_end_is_google_blue(self):
        from services.pdf_heatmap import _freq_to_color
        c = _freq_to_color(0, 0, 100)
        # Should be Google Blue #4285F4 = (66/255, 133/255, 244/255)
        assert abs(c.red - 66 / 255) < 0.01
        assert abs(c.green - 133 / 255) < 0.01
        assert abs(c.blue - 244 / 255) < 0.01

    def test_hot_end_is_google_red(self):
        from services.pdf_heatmap import _freq_to_color
        c = _freq_to_color(100, 0, 100)
        # Should be Google Red #EA4335 = (234/255, 67/255, 53/255)
        assert abs(c.red - 234 / 255) < 0.01
        assert abs(c.green - 67 / 255) < 0.01
        assert abs(c.blue - 53 / 255) < 0.01

    def test_midpoint_is_green_yellow(self):
        from services.pdf_heatmap import _freq_to_color
        c = _freq_to_color(50, 0, 100)
        # ratio=0.5 -> midpoint of segment 1 (Green->Yellow)
        # Green #34A853 and Yellow #FBBC05 interpolated at t=0.5
        assert c.green > 0.4  # still greenish/yellowish
        assert c.blue < 0.5   # not blue

    def test_cold_end_blue_dominant(self):
        from services.pdf_heatmap import _freq_to_color
        c = _freq_to_color(0, 0, 100)
        assert c.blue > c.red
        assert c.blue > c.green

    def test_hot_end_red_dominant(self):
        from services.pdf_heatmap import _freq_to_color
        c = _freq_to_color(100, 0, 100)
        assert c.red > c.green
        assert c.red > c.blue


# ═══════════════════════════════════════════════════════════════════════
# Text color tests
# ═══════════════════════════════════════════════════════════════════════

class TestTextColor:

    def test_dark_bg_returns_white_text(self):
        from services.pdf_heatmap import _text_color_for_bg
        # Cold end = Google Blue (dark) -> white text
        c = _text_color_for_bg(0, 0, 100)
        assert abs(c.red - 1) < 0.01  # white

    def test_yellow_bg_returns_black_text(self):
        from services.pdf_heatmap import _text_color_for_bg
        # Yellow area is bright -> black text
        # ratio ~0.67 -> Yellow zone
        c = _text_color_for_bg(67, 0, 100)
        assert abs(c.red) < 0.01  # black

    def test_red_bg_returns_white_text(self):
        from services.pdf_heatmap import _text_color_for_bg
        # Hot end = Google Red (dark) -> white text
        c = _text_color_for_bg(100, 0, 100)
        assert abs(c.red - 1) < 0.01  # white


# ═══════════════════════════════════════════════════════════════════════
# Grid rendering tests
# ═══════════════════════════════════════════════════════════════════════

class TestDrawHeatmapGrid:

    def _make_canvas(self):
        from reportlab.pdfgen import canvas as canvas_mod
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os, reportlab
        rl_fonts = os.path.join(os.path.dirname(reportlab.__file__), 'fonts')
        for name, files in [
            ('DejaVuSans', ['DejaVuSans.ttf', 'Vera.ttf']),
            ('DejaVuSans-Bold', ['DejaVuSans-Bold.ttf', 'VeraBd.ttf']),
        ]:
            for f in files:
                path = os.path.join(rl_fonts, f)
                if os.path.isfile(path):
                    try:
                        pdfmetrics.registerFont(TTFont(name, path))
                    except Exception:
                        continue
                    break

        buf = io.BytesIO()
        c = canvas_mod.Canvas(buf, pagesize=A4)
        return c, buf

    def test_em_boules_grid_10x5(self):
        from services.pdf_heatmap import draw_heatmap_grid
        c, buf = self._make_canvas()
        freq = {i: i * 2 for i in range(1, 51)}
        y_bottom = draw_heatmap_grid(c, 57, 729, freq, range(1, 51), cols=10, cell_w=48, cell_h=28)
        assert y_bottom == 729 - 5 * 28
        c.save()

    def test_em_etoiles_grid_6x2(self):
        from services.pdf_heatmap import draw_heatmap_grid
        c, buf = self._make_canvas()
        freq = {i: i * 3 for i in range(1, 13)}
        y_bottom = draw_heatmap_grid(c, 153, 552, freq, range(1, 13), cols=6, cell_w=48, cell_h=28)
        assert y_bottom == 552 - 2 * 28
        c.save()

    def test_loto_boules_grid_7x7(self):
        from services.pdf_heatmap import draw_heatmap_grid
        c, buf = self._make_canvas()
        freq = {i: i for i in range(1, 50)}
        y_bottom = draw_heatmap_grid(c, 70, 729, freq, range(1, 50), cols=7, cell_w=65, cell_h=28)
        assert y_bottom == 729 - 7 * 28
        c.save()

    def test_loto_chance_grid_5x2(self):
        from services.pdf_heatmap import draw_heatmap_grid
        c, buf = self._make_canvas()
        freq = {i: i * 5 for i in range(1, 11)}
        y_bottom = draw_heatmap_grid(c, 135, 490, freq, range(1, 11), cols=5, cell_w=65, cell_h=28)
        assert y_bottom == 490 - 2 * 28
        c.save()

    def test_empty_freq_dict(self):
        from services.pdf_heatmap import draw_heatmap_grid
        c, buf = self._make_canvas()
        y_bottom = draw_heatmap_grid(c, 57, 729, {}, range(1, 51), cols=10, cell_w=48, cell_h=28)
        assert y_bottom == 729 - 5 * 28
        c.save()


# ═══════════════════════════════════════════════════════════════════════
# Legend bar tests
# ═══════════════════════════════════════════════════════════════════════

class TestDrawLegendBar:

    def test_legend_bar_renders(self):
        from services.pdf_heatmap import draw_legend_bar
        from reportlab.pdfgen import canvas as canvas_mod
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os, reportlab

        rl_fonts = os.path.join(os.path.dirname(reportlab.__file__), 'fonts')
        for name, files in [
            ('DejaVuSans', ['DejaVuSans.ttf', 'Vera.ttf']),
        ]:
            for f in files:
                path = os.path.join(rl_fonts, f)
                if os.path.isfile(path):
                    try:
                        pdfmetrics.registerFont(TTFont(name, path))
                    except Exception:
                        continue
                    break

        buf = io.BytesIO()
        c = canvas_mod.Canvas(buf, pagesize=A4)
        y_bottom = draw_legend_bar(c, 100, 480, 300, 12, "Froid", "Chaud")
        assert y_bottom == 480 - 12 - 14
        c.save()


# ═══════════════════════════════════════════════════════════════════════
# Full PDF integration — EM
# ═══════════════════════════════════════════════════════════════════════

def _count_pdf_pages(buf):
    """Count pages in a PDF BytesIO using PyPDF2."""
    from PyPDF2 import PdfReader
    buf.seek(0)
    reader = PdfReader(buf)
    return len(reader.pages)


class TestFullEmPdf:

    def test_em_pdf_with_heatmap(self):
        from services.em_pdf_generator import generate_em_meta_pdf
        freq_b = {str(i): i * 2 for i in range(1, 51)}
        freq_s = {str(i): i * 3 for i in range(1, 13)}
        buf = generate_em_meta_pdf(
            analysis="Test analysis",
            all_freq_boules=freq_b,
            all_freq_secondary=freq_s,
            lang="fr",
        )
        assert isinstance(buf, io.BytesIO)
        data = buf.read()
        assert len(data) > 1000
        assert data[:5] == b'%PDF-'

    def test_em_pdf_with_heatmap_exactly_2_pages(self):
        from services.em_pdf_generator import generate_em_meta_pdf
        freq_b = {str(i): i * 2 for i in range(1, 51)}
        freq_s = {str(i): i * 3 for i in range(1, 13)}
        buf = generate_em_meta_pdf(
            analysis="Test analysis",
            all_freq_boules=freq_b,
            all_freq_secondary=freq_s,
            lang="fr",
        )
        assert _count_pdf_pages(buf) == 2

    def test_em_pdf_without_heatmap(self):
        from services.em_pdf_generator import generate_em_meta_pdf
        buf = generate_em_meta_pdf(analysis="Test analysis", lang="en")
        assert isinstance(buf, io.BytesIO)
        data = buf.read()
        assert data[:5] == b'%PDF-'

    def test_em_pdf_without_heatmap_1_page(self):
        from services.em_pdf_generator import generate_em_meta_pdf
        buf = generate_em_meta_pdf(analysis="Short test", lang="fr")
        assert _count_pdf_pages(buf) == 1

    def test_em_pdf_all_langs(self):
        from services.em_pdf_generator import generate_em_meta_pdf
        freq_b = {str(i): 10 for i in range(1, 51)}
        freq_s = {str(i): 5 for i in range(1, 13)}
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            buf = generate_em_meta_pdf(
                analysis="Test",
                all_freq_boules=freq_b,
                all_freq_secondary=freq_s,
                lang=lang,
            )
            assert buf.read()[:5] == b'%PDF-', f"Failed for lang={lang}"

    def test_em_pdf_all_langs_2_pages(self):
        from services.em_pdf_generator import generate_em_meta_pdf
        freq_b = {str(i): 10 for i in range(1, 51)}
        freq_s = {str(i): 5 for i in range(1, 13)}
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            buf = generate_em_meta_pdf(
                analysis="Test",
                all_freq_boules=freq_b,
                all_freq_secondary=freq_s,
                lang=lang,
            )
            assert _count_pdf_pages(buf) == 2, f"Expected 2 pages for lang={lang}"


# ═══════════════════════════════════════════════════════════════════════
# Full PDF integration — Loto
# ═══════════════════════════════════════════════════════════════════════

class TestFullLotoPdf:

    def test_loto_pdf_with_heatmap(self):
        from services.pdf_generator import generate_meta_pdf
        freq_b = {str(i): i for i in range(1, 50)}
        freq_s = {str(i): i * 5 for i in range(1, 11)}
        buf = generate_meta_pdf(
            analysis="Test analysis",
            all_freq_boules=freq_b,
            all_freq_secondary=freq_s,
            lang="fr",
        )
        assert isinstance(buf, io.BytesIO)
        data = buf.read()
        assert len(data) > 1000
        assert data[:5] == b'%PDF-'

    def test_loto_pdf_with_heatmap_exactly_2_pages(self):
        from services.pdf_generator import generate_meta_pdf
        freq_b = {str(i): i for i in range(1, 50)}
        freq_s = {str(i): i * 5 for i in range(1, 11)}
        buf = generate_meta_pdf(
            analysis="Test analysis",
            all_freq_boules=freq_b,
            all_freq_secondary=freq_s,
            lang="fr",
        )
        assert _count_pdf_pages(buf) == 2

    def test_loto_pdf_without_heatmap(self):
        from services.pdf_generator import generate_meta_pdf
        buf = generate_meta_pdf(analysis="Test analysis")
        assert isinstance(buf, io.BytesIO)
        data = buf.read()
        assert data[:5] == b'%PDF-'

    def test_loto_pdf_without_heatmap_1_page(self):
        from services.pdf_generator import generate_meta_pdf
        buf = generate_meta_pdf(analysis="Short test", lang="fr")
        assert _count_pdf_pages(buf) == 1

    def test_loto_pdf_all_langs(self):
        from services.pdf_generator import generate_meta_pdf
        freq_b = {str(i): 10 for i in range(1, 50)}
        freq_s = {str(i): 5 for i in range(1, 11)}
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            buf = generate_meta_pdf(
                analysis="Test",
                all_freq_boules=freq_b,
                all_freq_secondary=freq_s,
                lang=lang,
            )
            assert buf.read()[:5] == b'%PDF-', f"Failed for lang={lang}"

    def test_loto_pdf_all_langs_2_pages(self):
        from services.pdf_generator import generate_meta_pdf
        freq_b = {str(i): 10 for i in range(1, 50)}
        freq_s = {str(i): 5 for i in range(1, 11)}
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            buf = generate_meta_pdf(
                analysis="Test",
                all_freq_boules=freq_b,
                all_freq_secondary=freq_s,
                lang=lang,
            )
            assert _count_pdf_pages(buf) == 2, f"Expected 2 pages for lang={lang}"


# ═══════════════════════════════════════════════════════════════════════
# PDF_LABELS coverage
# ═══════════════════════════════════════════════════════════════════════

HEATMAP_KEYS_EM = [
    "heatmap_title_balls", "heatmap_title_stars",
    "heatmap_legend_cold", "heatmap_legend_hot",
]

HEATMAP_KEYS_LOTO = [
    "heatmap_title_balls", "heatmap_title_secondary",
    "heatmap_legend_cold", "heatmap_legend_hot",
]

ALL_LANGS = ("fr", "en", "es", "pt", "de", "nl")


class TestPdfLabels:

    def test_em_labels_heatmap_keys(self):
        from services.em_pdf_generator import PDF_LABELS
        for lang in ALL_LANGS:
            for key in HEATMAP_KEYS_EM:
                assert key in PDF_LABELS[lang], f"Missing {key} in EM PDF_LABELS[{lang}]"
                assert len(PDF_LABELS[lang][key]) > 0

    def test_loto_labels_heatmap_keys(self):
        from services.pdf_generator import PDF_LABELS
        for lang in ALL_LANGS:
            for key in HEATMAP_KEYS_LOTO:
                assert key in PDF_LABELS[lang], f"Missing {key} in Loto PDF_LABELS[{lang}]"
                assert len(PDF_LABELS[lang][key]) > 0

    def test_loto_labels_all_keys_present(self):
        from services.pdf_generator import PDF_LABELS
        fr_keys = set(PDF_LABELS["fr"].keys())
        for lang in ALL_LANGS:
            assert set(PDF_LABELS[lang].keys()) == fr_keys, f"Key mismatch for lang={lang}"

    def test_em_labels_all_keys_present(self):
        from services.em_pdf_generator import PDF_LABELS
        fr_keys = set(PDF_LABELS["fr"].keys())
        for lang in ALL_LANGS:
            assert set(PDF_LABELS[lang].keys()) == fr_keys, f"Key mismatch for lang={lang}"


# ═══════════════════════════════════════════════════════════════════════
# Schema acceptance
# ═══════════════════════════════════════════════════════════════════════

class TestSchemaAcceptance:

    def test_em_schema_accepts_freq_fields(self):
        from em_schemas import EMMetaPdfPayload
        p = EMMetaPdfPayload(
            all_freq_boules={"1": 10, "2": 20},
            all_freq_secondary={"1": 5},
        )
        assert p.all_freq_boules == {"1": 10, "2": 20}
        assert p.all_freq_secondary == {"1": 5}

    def test_em_schema_freq_optional(self):
        from em_schemas import EMMetaPdfPayload
        p = EMMetaPdfPayload()
        assert p.all_freq_boules is None
        assert p.all_freq_secondary is None

    def test_loto_schema_accepts_lang(self):
        from schemas import MetaPdfPayload
        p = MetaPdfPayload(lang="en")
        assert p.lang == "en"

    def test_loto_schema_lang_default(self):
        from schemas import MetaPdfPayload
        p = MetaPdfPayload()
        assert p.lang == "fr"

    def test_loto_schema_accepts_freq_fields(self):
        from schemas import MetaPdfPayload
        p = MetaPdfPayload(
            all_freq_boules={"1": 10, "2": 20},
            all_freq_secondary={"1": 5},
            lang="de",
        )
        assert p.all_freq_boules == {"1": 10, "2": 20}
        assert p.all_freq_secondary == {"1": 5}
        assert p.lang == "de"

    def test_loto_schema_freq_optional(self):
        from schemas import MetaPdfPayload
        p = MetaPdfPayload()
        assert p.all_freq_boules is None
        assert p.all_freq_secondary is None
