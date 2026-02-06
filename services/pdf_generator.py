import os
import io
import logging

logger = logging.getLogger(__name__)


def _utf8_clean(text):
    """Nettoie le texte en preservant tous les caracteres UTF-8."""
    if not text:
        return ""
    return text.encode("utf-8").decode("utf-8")


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


def generate_meta_pdf(analysis: str = "", window: str = "75 tirages",
                      engine: str = "HYBRIDE_OPTIMAL_V1", graph: str = None,
                      sponsor: str = None) -> io.BytesIO:
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

    # Image graphique si presente
    graph_path = graph or ""
    if graph_path and os.path.isfile(graph_path):
        try:
            img_w = 160 * mm
            img_h = 80 * mm
            img_x = (w - img_w) / 2
            c.drawImage(
                graph_path, img_x, y - img_h,
                width=img_w, height=img_h,
                preserveAspectRatio=True, mask="auto"
            )
            y -= (img_h + 10 * mm)
            logger.info("[META-PDF] Image inseree OK")
        except Exception as img_err:
            logger.warning(f"[META-PDF] Image ignoree: {img_err}")

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
    c.drawCentredString(w / 2, y, "LotoIA \u2014 Rapport META DONN\u00c9E v0.1")
    y -= 4 * mm
    c.drawCentredString(w / 2, y, "Ce rapport est enti\u00e8rement g\u00e9n\u00e9r\u00e9 par intelligence artificielle en collaboration avec le moteur HYBRIDE_OPTIMAL_V1.")
    y -= 4 * mm
    c.drawCentredString(w / 2, y, "Graphiques et visuels en cours de d\u00e9veloppement.")

    # Footer bas de page — position dynamique, toujours y=20
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.setFont("DejaVuSans", 8)
    c.drawCentredString(w / 2, 20, "* Ce rapport META DONN\u00c9E est en version 0.1 \u2013 Version graphique \u00e0 venir.")

    c.save()
    buf.seek(0)
    logger.info("[META-PDF] PDF genere OK")

    return buf
