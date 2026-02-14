import os
import io
import tempfile
import logging

from config.version import APP_VERSION

logger = logging.getLogger(__name__)


def _utf8_clean(text):
    """Nettoie le texte : remplace les caracteres Unicode problematiques par des equivalents ASCII safe pour ReportLab/Vera."""
    if not text:
        return ""
    replacements = {
        "\u2192": "->",   # → RIGHTWARDS ARROW
        "\u2190": "<-",   # ← LEFTWARDS ARROW
        "\u2194": "<->",  # ↔ LEFT RIGHT ARROW
        "\u2013": "-",    # – EN DASH
        "\u2014": "-",    # — EM DASH
        "\u2018": "'",    # ' LEFT SINGLE QUOTATION MARK
        "\u2019": "'",    # ' RIGHT SINGLE QUOTATION MARK
        "\u201C": '"',    # " LEFT DOUBLE QUOTATION MARK
        "\u201D": '"',    # " RIGHT DOUBLE QUOTATION MARK
        "\u2026": "...",  # … HORIZONTAL ELLIPSIS
        "\u00A0": " ",    # NO-BREAK SPACE
        "\u2022": "-",    # • BULLET
        "\u25A0": "-",    # ■ BLACK SQUARE
        "\u25A1": "-",    # □ WHITE SQUARE
        "\u2023": "-",    # ‣ TRIANGULAR BULLET
        "\u00B7": ".",    # · MIDDLE DOT
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def _register_fonts(pdfmetrics, TTFont):
    """Enregistre polices UTF-8 : DejaVuSans (Linux/Cloud Run) -> Vera (fallback ReportLab)."""
    import reportlab as _rl
    _rl_fonts = os.path.join(os.path.dirname(_rl.__file__), 'fonts')
    _font_map = {
        'DejaVuSans': [
            os.path.join(_rl_fonts, 'DejaVuSans.ttf'),
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            os.path.join(_rl_fonts, 'Vera.ttf'),
        ],
        'DejaVuSans-Bold': [
            os.path.join(_rl_fonts, 'DejaVuSans-Bold.ttf'),
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            os.path.join(_rl_fonts, 'VeraBd.ttf'),
        ],
        'DejaVuSans-Oblique': [
            os.path.join(_rl_fonts, 'DejaVuSans-Oblique.ttf'),
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf',
            os.path.join(_rl_fonts, 'VeraIt.ttf'),
        ],
    }
    for _name, _paths in _font_map.items():
        for _path in _paths:
            if os.path.isfile(_path):
                try:
                    pdfmetrics.registerFont(TTFont(_name, _path))
                    logger.info(f"[META-PDF] Police {_name} \u2192 {os.path.basename(_path)}")
                except Exception as _fe:
                    logger.warning(f"[META-PDF] Echec {_name} avec {_path}: {_fe}")
                    continue
                break
        else:
            logger.error(f"[META-PDF] Aucune police trouvee pour {_name}")


def generate_meta_graph_image(graph_data: dict) -> str:
    """
    Genere une image PNG contenant un bar chart + pie chart cote a cote.
    Retourne le chemin du fichier temporaire PNG.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    labels = graph_data.get("labels", [])
    values = graph_data.get("values", [])

    if not labels or not values or len(labels) != len(values):
        raise ValueError("graph_data invalide : labels et values requis, memes longueurs")

    bar_colors = ['#4285F4', '#34A853', '#FBBC05', '#EA4335', '#A142F4']
    pie_colors = ['#1A73E8', '#188038', '#F9AB00', '#D93025', '#9334E6']

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    # Bar chart (gauche)
    ax1.bar(labels, values, color=bar_colors[:len(labels)])
    ax1.set_title("Top 5 Fréquences", fontsize=13, fontweight='bold')
    ax1.set_xlabel("Numéros")
    ax1.set_ylabel("Fréquence")
    ax1.grid(axis='y', alpha=0.15)

    # Pie chart (droite)
    pie_labels = [f"N°{l} ({v})" for l, v in zip(labels, values)]
    ax2.pie(
        values, labels=pie_labels, colors=pie_colors[:len(labels)],
        autopct='%1.0f%%', startangle=90, counterclock=False,
        textprops={'fontsize': 9},
        wedgeprops={'linewidth': 0.5, 'edgecolor': 'white'}
    )
    ax2.set_title("Répartition Top 5", fontsize=13, fontweight='bold')

    plt.tight_layout()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp_path = tmp.name
    tmp.close()

    fig.savefig(tmp_path, format="png", dpi=200, facecolor='white', bbox_inches='tight')
    plt.close(fig)

    logger.info(f"[META-PDF] Graph image generee : {tmp_path}")
    return tmp_path


def generate_meta_pdf(analysis: str = "", window: str = "75 tirages",
                      engine: str = "HYBRIDE_OPTIMAL_V1", graph: str = None,
                      graph_data: dict = None, sponsor: str = None) -> io.BytesIO:
    """
    Genere le PDF officiel META75 via ReportLab.
    Retourne un BytesIO contenant le PDF.

    Raises:
        ImportError: si reportlab n'est pas installe
        Exception: toute erreur de generation
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    logger.info("[META-PDF] Debut generation PDF")

    # Enregistrer polices UTF-8
    _register_fonts(pdfmetrics, TTFont)

    buf = io.BytesIO()
    w, h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    margin_bottom = 30 * mm

    y = h - 40 * mm
    logger.info("[META-PDF] Canvas cree OK")

    # Titre
    c.setFont("DejaVuSans-Bold", 22)
    c.drawCentredString(w / 2, y, "Rapport META DONN\u00c9E - 75 Grilles")
    y -= 12 * mm

    # Sous-titre
    c.setFont("DejaVuSans-Bold", 16)
    c.drawCentredString(w / 2, y, "Analyse HYBRIDE")
    y -= 10 * mm

    # Separateur
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.5)
    c.line(15 * mm, y, w - 15 * mm, y)
    y -= 10 * mm

    # --- Validation robuste graph_data ---
    valid_graph = (
        isinstance(graph_data, dict)
        and isinstance(graph_data.get("labels"), list)
        and isinstance(graph_data.get("values"), list)
        and len(graph_data["labels"]) == len(graph_data["values"])
        and len(graph_data["labels"]) > 0
    ) if graph_data else False

    logger.info(f"[META-PDF] graph_data valid: {valid_graph}, "
                f"raw type: {type(graph_data).__name__}, "
                f"graph file: {graph!r}")

    # --- Generation image matplotlib si graph_data valide ---
    generated_graph_path = None
    if valid_graph:
        try:
            generated_graph_path = generate_meta_graph_image(graph_data)
            logger.info(f"[META-PDF] PNG genere OK: {generated_graph_path}")
        except Exception as gen_err:
            logger.warning(f"[META-PDF] Generation graph_data echouee: {gen_err}")

    try:
        # --- Insertion image (graph_data prioritaire, sinon fallback graph path) ---
        effective_graph = generated_graph_path or (graph if graph and os.path.isfile(graph) else "")
        if effective_graph and os.path.isfile(effective_graph):
            try:
                from reportlab.lib.utils import ImageReader
                img = ImageReader(effective_graph)

                # Coordonnees A4 safe (portrait 595x842 points)
                img_x = 60
                img_draw_y = y - 200          # image juste sous separateur
                img_draw_w = 480
                img_draw_h = 190

                c.drawImage(
                    img, img_x, img_draw_y,
                    width=img_draw_w, height=img_draw_h,
                    preserveAspectRatio=True, mask='auto'
                )
                y = img_draw_y - 8 * mm       # pousser Y sous l'image
                logger.info(f"[META-PDF] Image inseree OK a y={img_draw_y}")
            except Exception as img_err:
                logger.warning(f"[META-PDF] Image ignoree: {img_err}")
        else:
            logger.info("[META-PDF] Aucune image a inserer")

        # Bloc analyse
        c.setFont("DejaVuSans-Bold", 13)
        c.drawString(15 * mm, y, "Analyse :")
        y -= 7 * mm

        analysis_text = _utf8_clean(analysis) or "Aucune analyse disponible."
        text_obj = c.beginText(15 * mm, y)
        text_obj.setFont("DejaVuSans", 11)
        text_obj.setLeading(16)
        max_chars = 90
        for raw_line in analysis_text.split('\n'):
            line = raw_line
            while len(line) > max_chars:
                cut = line[:max_chars].rfind(' ')
                if cut <= 0:
                    cut = max_chars
                text_obj.textLine(line[:cut])
                line = line[cut:].lstrip()
            text_obj.textLine(line)
        c.drawText(text_obj)
        y = text_obj.getY() - 8 * mm
        logger.info("[META-PDF] Bloc analyse OK")

        # Saut de page si espace insuffisant
        if y < margin_bottom:
            c.showPage()
            y = h - 30 * mm

        # Bloc infos
        c.setFont("DejaVuSans-Bold", 13)
        c.drawString(15 * mm, y, "Informations :")
        y -= 7 * mm

        c.setFont("DejaVuSans", 11)
        window_text = _utf8_clean(window) or "75 tirages"
        engine_text = _utf8_clean(engine) or "HYBRIDE_OPTIMAL_V1"
        c.drawString(15 * mm, y, f"Fen\u00eatre analys\u00e9e : {window_text}")
        y -= 6 * mm
        c.drawString(15 * mm, y, f"Moteur : {engine_text}")
        y -= 10 * mm

        # Bloc sponsor si present
        sponsor_text = _utf8_clean(sponsor)
        if sponsor_text:
            c.setStrokeColorRGB(0.7, 0.7, 0.7)
            c.setLineWidth(0.4)
            c.line(15 * mm, y, w - 15 * mm, y)
            y -= 8 * mm

            # Titre partenariat
            c.setFillColorRGB(0.1, 0.1, 0.1)
            c.setFont("DejaVuSans", 10)
            c.drawCentredString(w / 2, y, "Analyse offerte par un Partenaire Officiel")
            y -= 6 * mm

            # Sous-titre
            c.setFont("DejaVuSans", 9)
            c.drawCentredString(w / 2, y, "Partenariat & sponsoring :")
            y -= 5 * mm

            # Email cliquable
            email_text = "contact@lotoia.fr"
            email_width = c.stringWidth(email_text, "DejaVuSans", 9)
            email_x1 = (w - email_width) / 2
            email_x2 = email_x1 + email_width
            c.drawCentredString(w / 2, y, email_text)
            c.linkURL("mailto:contact@lotoia.fr", (email_x1, y - 2, email_x2, y + 10), relative=0)
            y -= 10 * mm

        # Saut de page si espace insuffisant
        if y < margin_bottom:
            c.showPage()
            y = h - 30 * mm

        # Separateur
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.5)
        c.line(15 * mm, y, w - 15 * mm, y)
        y -= 10 * mm

        # Signature HYBRIDE
        c.setFillColorRGB(0, 0, 0)
        c.setFont("DejaVuSans-Bold", 11)
        c.drawCentredString(w / 2, y, "Analyse g\u00e9n\u00e9r\u00e9e par HYBRIDE_OPTIMAL_V1")
        y -= 6 * mm
        c.setFont("DejaVuSans", 10)
        c.drawCentredString(w / 2, y, "Moteur statistique p\u00e9dagogique")
        y -= 8 * mm

        # Mention produit
        c.setFont("DejaVuSans-Oblique", 10)
        c.drawCentredString(w / 2, y, "G\u00e9n\u00e9r\u00e9 par LotoIA - Module META DONN\u00c9E")
        y -= 10 * mm

        # Disclaimer
        c.setFont("DejaVuSans", 9)
        c.drawCentredString(w / 2, y, "Analyse statistique p\u00e9dagogique.")
        y -= 5 * mm
        c.drawCentredString(w / 2, y, "Aucun r\u00e9sultat n\u2019est garanti.")
        y -= 10 * mm

        # Version + notes IA
        c.setFillColorRGB(150 / 255, 150 / 255, 150 / 255)
        c.setFont("DejaVuSans-Oblique", 8)
        c.drawCentredString(w / 2, y, f"LotoIA \u2014 Rapport META DONN\u00c9E v{APP_VERSION}")
        y -= 7 * mm
        c.drawCentredString(w / 2, y, "Ce rapport est enti\u00e8rement g\u00e9n\u00e9r\u00e9 par intelligence artificielle en collaboration avec le moteur HYBRIDE_OPTIMAL_V1.")
        y -= 7 * mm
        c.drawCentredString(w / 2, y, "Graphiques et visuels en cours de d\u00e9veloppement.")

        c.save()
        buf.seek(0)
        logger.info("[META-PDF] PDF genere OK")

        return buf

    finally:
        # Nettoyage fichier temporaire graph_data
        if generated_graph_path:
            try:
                os.unlink(generated_graph_path)
                logger.info(f"[META-PDF] Fichier temp supprime : {generated_graph_path}")
            except OSError:
                pass
