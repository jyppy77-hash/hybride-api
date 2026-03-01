"""
PDF Heatmap — Shared module for frequency heatmap grids (EM + Loto).
Draws a color-coded grid of all numbers with their frequencies,
using a Google Material Design 4-color gradient: Blue -> Green -> Yellow -> Red.
"""

from reportlab.lib.colors import Color
from reportlab.lib.units import mm

# Google Material Design anchor colors
_GRADIENT = [
    (66 / 255, 133 / 255, 244 / 255),   # Blue  #4285F4 (rare)
    (52 / 255, 168 / 255, 83 / 255),     # Green #34A853
    (251 / 255, 188 / 255, 5 / 255),     # Yellow #FBBC05
    (234 / 255, 67 / 255, 53 / 255),     # Red   #EA4335 (frequent)
]


def _freq_to_color(freq: int, min_f: int, max_f: int) -> Color:
    """Gradient Google: Blue -> Green -> Yellow -> Red."""
    if max_f == min_f:
        ratio = 0.5
    else:
        ratio = (freq - min_f) / (max_f - min_f)

    if ratio <= 0.0:
        r, g, b = _GRADIENT[0]
    elif ratio >= 1.0:
        r, g, b = _GRADIENT[3]
    else:
        segment = ratio * 3  # 3 segments for 4 colors
        idx = min(int(segment), 2)
        t = segment - idx
        c1 = _GRADIENT[idx]
        c2 = _GRADIENT[idx + 1]
        r = c1[0] + (c2[0] - c1[0]) * t
        g = c1[1] + (c2[1] - c1[1]) * t
        b = c1[2] + (c2[2] - c1[2]) * t

    return Color(r, g, b, alpha=0.85)


def _text_color_for_bg(freq: int, min_f: int, max_f: int) -> Color:
    """Return black or white depending on background luminance."""
    bg = _freq_to_color(freq, min_f, max_f)
    lum = 0.299 * bg.red + 0.587 * bg.green + 0.114 * bg.blue
    return Color(0, 0, 0) if lum > 0.55 else Color(1, 1, 1)


def draw_heatmap_grid(canvas, x, y, freq_dict, num_range, cols, cell_w, cell_h):
    """
    Draw a heatmap grid on the canvas.

    Parameters
    ----------
    canvas : reportlab Canvas
    x, y : top-left origin (y = top of grid, goes downward)
    freq_dict : {int: int} — number -> frequency
    num_range : range object (e.g. range(1,51))
    cols : columns per row
    cell_w, cell_h : cell dimensions in points
    Returns the y position below the grid.
    """
    numbers = list(num_range)
    freqs = [freq_dict.get(n, 0) for n in numbers]
    min_f = min(freqs) if freqs else 0
    max_f = max(freqs) if freqs else 0

    for i, num in enumerate(numbers):
        col = i % cols
        row = i // cols
        cx = x + col * cell_w
        cy = y - row * cell_h

        freq = freq_dict.get(num, 0)
        bg = _freq_to_color(freq, min_f, max_f)
        fg = _text_color_for_bg(freq, min_f, max_f)

        # Cell background
        canvas.setFillColor(bg)
        canvas.setStrokeColorRGB(0.7, 0.7, 0.7)
        canvas.setLineWidth(0.3)
        canvas.rect(cx, cy - cell_h, cell_w, cell_h, fill=1, stroke=1)

        # Number (bold, top of cell)
        canvas.setFillColor(fg)
        canvas.setFont("DejaVuSans-Bold", 9)
        canvas.drawCentredString(cx + cell_w / 2, cy - 11, str(num))

        # Frequency (small, bottom of cell)
        canvas.setFont("DejaVuSans", 7)
        canvas.drawCentredString(cx + cell_w / 2, cy - cell_h + 3, str(freq))

    total_rows = (len(numbers) + cols - 1) // cols
    return y - total_rows * cell_h


def draw_legend_bar(canvas, x, y, width, height, label_cold, label_hot):
    """
    Draw a horizontal gradient legend bar (Google 4-color) with labels.
    Returns y position below the legend.
    """
    steps = 60
    step_w = width / steps
    for i in range(steps):
        ratio = i / (steps - 1)
        if ratio <= 0.0:
            r, g, b = _GRADIENT[0]
        elif ratio >= 1.0:
            r, g, b = _GRADIENT[3]
        else:
            segment = ratio * 3
            idx = min(int(segment), 2)
            t = segment - idx
            c1 = _GRADIENT[idx]
            c2 = _GRADIENT[idx + 1]
            r = c1[0] + (c2[0] - c1[0]) * t
            g = c1[1] + (c2[1] - c1[1]) * t
            b = c1[2] + (c2[2] - c1[2]) * t
        canvas.setFillColorRGB(r, g, b)
        canvas.rect(x + i * step_w, y - height, step_w + 0.5, height, fill=1, stroke=0)

    # Border
    canvas.setStrokeColorRGB(0.6, 0.6, 0.6)
    canvas.setLineWidth(0.3)
    canvas.rect(x, y - height, width, height, fill=0, stroke=1)

    # Labels
    canvas.setFillColorRGB(0.2, 0.2, 0.2)
    canvas.setFont("DejaVuSans", 7)
    canvas.drawString(x, y - height - 10, label_cold)
    canvas.drawRightString(x + width, y - height - 10, label_hot)

    return y - height - 14
