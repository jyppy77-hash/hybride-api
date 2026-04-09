"""
Admin PDF generation — sponsor reports + invoices.
Aligned with FacturIA visual style (bleu fonce / dore / gris).
UTF-8 font support via DejaVuSans (fallback Vera from ReportLab).
"""

import io
import os
import logging
from datetime import date, datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)


def _register_fonts():
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
                except Exception:
                    continue
                break
        else:
            logger.error("[ADMIN-PDF] Aucune police trouvée pour %s", _name)


_register_fonts()


# FacturIA palette
BLEU_FONCE = HexColor('#1a2744')
BLEU = HexColor('#2c4a7c')
DORE = HexColor('#d4a843')
GRIS = HexColor('#8891a4')
GRIS_CLAIR = HexColor('#f7f8fa')
NOIR = HexColor('#1a202c')
BLANC = HexColor('#ffffff')

_base = getSampleStyleSheet()

_LOGO = ParagraphStyle('Logo', fontName='DejaVuSans-Bold', fontSize=18, textColor=BLEU_FONCE, leading=22)
_TITLE_R = ParagraphStyle('TitleR', fontName='DejaVuSans-Bold', fontSize=16, textColor=BLEU_FONCE, alignment=TA_RIGHT, leading=20)
_SECTION = ParagraphStyle('Section', parent=_base['Heading2'], fontName='DejaVuSans-Bold', fontSize=11, textColor=BLEU, spaceBefore=6*mm, spaceAfter=3*mm)
_NORMAL = ParagraphStyle('Normal2', parent=_base['Normal'], fontName='DejaVuSans', fontSize=9, textColor=NOIR, leading=13)
_PETIT = ParagraphStyle('Petit', parent=_base['Normal'], fontName='DejaVuSans', fontSize=8, textColor=GRIS, leading=11)
_FOOTER = ParagraphStyle('Footer', parent=_base['Normal'], fontName='DejaVuSans', fontSize=7, textColor=GRIS, alignment=TA_CENTER)


def _format_euros(montant):
    """Formate un montant en EUR français : 1234.56 → '1 234,56 EUR'."""
    from babel.numbers import format_currency
    if montant is None:
        montant = 0
    return format_currency(montant, 'EUR', locale='fr_FR', currency_digits=True, format_type='standard')


def _format_date_fr(d):
    if isinstance(d, (date, datetime)):
        return d.strftime("%d/%m/%Y")
    if isinstance(d, str) and len(d) >= 10:
        try:
            return datetime.strptime(d[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            pass
    return str(d) if d else ""


def _detail_table_style(num_rows):
    styles = [
        ('BACKGROUND', (0, 0), (-1, 0), BLEU_FONCE),
        ('TEXTCOLOR', (0, 0), (-1, 0), BLANC),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 3*mm),
        ('TOPPADDING', (0, 0), (-1, 0), 3*mm),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TEXTCOLOR', (0, 1), (-1, -1), NOIR),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 2.5*mm),
        ('TOPPADDING', (0, 1), (-1, -1), 2.5*mm),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, GRIS_CLAIR),
        ('LINEBELOW', (0, -1), (-1, -1), 1, GRIS),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
    ]
    for i in range(2, num_rows, 2):
        styles.append(('BACKGROUND', (0, i), (-1, i), GRIS_CLAIR))
    return TableStyle(styles)


# ═══════════════════════════════════════════════════════════════
# Sponsor report PDF
# ═══════════════════════════════════════════════════════════════

def generate_sponsor_report_pdf(kpi: dict, table_data: list, period_label: str) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=25*mm)
    elements = []

    # Header
    header = Table([
        [
            Paragraph("<font color='#d4a843'>⚡</font> <b>Loto<font color='#d4a843'>IA</font></b>", _LOGO),
            Paragraph("<b>RAPPORT SPONSOR</b>", _TITLE_R),
        ]
    ], colWidths=[90*mm, 80*mm])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    elements.append(header)
    elements.append(Spacer(1, 4*mm))

    elements.append(Paragraph(f"Période : {period_label} | Généré le {_format_date_fr(date.today())}", _PETIT))
    elements.append(Spacer(1, 8*mm))

    # KPI block
    elements.append(Paragraph("INDICATEURS", _SECTION))
    kpi_rows = [
        ["Impressions", "Clics", "Vidéos", "CTR", "Sessions"],
        [
            str(kpi.get("impressions", 0)),
            str(kpi.get("clicks", 0)),
            str(kpi.get("videos", 0)),
            kpi.get("ctr", "0.00%"),
            str(kpi.get("sessions", 0)),
        ],
    ]
    t = Table(kpi_rows, colWidths=[34*mm]*5)
    t.setStyle(_detail_table_style(2))
    elements.append(t)
    elements.append(Spacer(1, 10*mm))

    # Detail table
    if table_data:
        elements.append(Paragraph("DÉTAIL PAR JOUR / EVENT / PAGE", _SECTION))
        headers = ["Date", "Event", "Page", "Lang", "Device", "Pays", "Nb"]
        rows = [headers]
        for r in table_data[:200]:
            rows.append([
                r.get("day", ""), r.get("event_type", ""), r.get("page", ""),
                r.get("lang", ""), r.get("device", ""), r.get("country", ""),
                str(r.get("cnt", 0)),
            ])
        t = Table(rows, colWidths=[22*mm, 32*mm, 38*mm, 12*mm, 18*mm, 15*mm, 15*mm])
        t.setStyle(_detail_table_style(len(rows)))
        elements.append(t)

    def footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont('DejaVuSans', 7)
        canvas_obj.setFillColor(GRIS)
        canvas_obj.drawCentredString(A4[0] / 2, 12*mm, "LotoIA — Rapport généré automatiquement")
        canvas_obj.restoreState()

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    return buf


# ═══════════════════════════════════════════════════════════════
# Invoice PDF (FacturIA style)
# ═══════════════════════════════════════════════════════════════

def generate_invoice_pdf(facture: dict, config: dict, lignes: list) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=25*mm)
    statut = (facture.get("statut") or "brouillon").lower()
    elements = []

    # Header
    numero = facture.get('numero', '')
    header = Table([
        [
            Paragraph("<font color='#d4a843'>⚡</font> <b>Factur<font color='#d4a843'>IA</font></b>", _LOGO),
            Paragraph(f"<b>FACTURE</b><br/><font size=10 color='#8891a4'>{numero}</font>", _TITLE_R),
        ]
    ], colWidths=[90*mm, 80*mm])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    elements.append(header)
    elements.append(Spacer(1, 8*mm))

    # Emitter / Client side by side
    rs = config.get("raison_sociale", "")
    addr = config.get("adresse", "")
    cp = config.get("code_postal", "")
    ville = config.get("ville", "")
    siret = config.get("siret", "")
    forme = config.get("forme_juridique", "") or "EI"
    rcs = config.get("rcs", "") or ""
    capital = config.get("capital_social", "") or ""
    tva_intra = config.get("tva_intra", "") or ""

    emitter_parts = [f"<b>{rs}</b>"]
    # A09: Forme juridique
    if forme.upper() in ("EI", ""):
        emitter_parts.append("Entrepreneur Individuel")
    else:
        legal_line = forme
        if capital:
            legal_line += f" au capital de {capital} EUR"
        if rcs:
            legal_line += f" — RCS {rcs}"
        emitter_parts.append(legal_line)
    if addr:
        emitter_parts.append(addr.replace('\n', '<br/>'))
    if cp or ville:
        emitter_parts.append(f"{cp} {ville}".strip())
    if siret:
        emitter_parts.append(f"SIRET : {siret}")
    # A02: TVA intracommunautaire or exoneration
    if tva_intra:
        emitter_parts.append(f"TVA intra. : {tva_intra}")
    else:
        emitter_parts.append("TVA non applicable, art. 293 B du CGI")
    email = config.get("email", "")
    if email:
        emitter_parts.append(email)

    client_parts = [f"<b>{facture.get('sponsor_nom', '')}</b>"]
    sponsor_addr = facture.get("sponsor_adresse", "")
    if sponsor_addr:
        client_parts.append(sponsor_addr.replace('\n', '<br/>'))

    addr_table = Table([
        [Paragraph("<br/>".join(emitter_parts), _NORMAL), Paragraph("<br/>".join(client_parts), _NORMAL)]
    ], colWidths=[85*mm, 85*mm])
    addr_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), GRIS_CLAIR),
        ('TOPPADDING', (0, 0), (-1, -1), 3*mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3*mm),
        ('LEFTPADDING', (0, 0), (-1, -1), 3*mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3*mm),
    ]))
    elements.append(addr_table)
    elements.append(Spacer(1, 6*mm))

    # Dates — A01: date d'echeance now rendered
    de = _format_date_fr(facture.get('date_emission', ''))
    dec_raw = facture.get('date_echeance', '')
    dec = _format_date_fr(dec_raw) if dec_raw else "À réception"
    pd = _format_date_fr(facture.get('periode_debut', ''))
    pf = _format_date_fr(facture.get('periode_fin', ''))
    info = Table(
        [
            ["Date d'émission :", de, "Période :", f"{pd} au {pf}"],
            ["Échéance :", dec, "", ""],
        ],
        colWidths=[35*mm, 50*mm, 25*mm, 60*mm],
    )
    info.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'DejaVuSans-Bold'),
        ('FONTNAME', (2, 0), (2, 0), 'DejaVuSans-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), GRIS),
        ('TEXTCOLOR', (2, 0), (2, 0), GRIS),
        ('TEXTCOLOR', (1, 0), (1, -1), NOIR),
        ('TEXTCOLOR', (3, 0), (3, 0), NOIR),
    ]))
    elements.append(info)
    elements.append(Spacer(1, 8*mm))

    # Detail lines
    elements.append(Paragraph("DÉTAIL DE LA PRESTATION", _SECTION))
    rows = [["Désignation", "Quantité", "Prix unit.", "Montant HT"]]
    for l in lignes:
        rows.append([
            l.get("description", ""),
            str(l.get("quantite", 0)),
            _format_euros(l.get("prix_unitaire", 0)),
            _format_euros(l.get("total_ht", 0)),
        ])
    t = Table(rows, colWidths=[75*mm, 30*mm, 30*mm, 35*mm])
    t.setStyle(_detail_table_style(len(rows)))
    elements.append(t)
    elements.append(Spacer(1, 6*mm))

    # Totals (aligned right, TTC in bleu fonce)
    taux = config.get("taux_tva", 20)
    totaux = [
        ["Total HT", _format_euros(facture.get("montant_ht", 0))],
        [f"TVA ({taux}%)", _format_euros(facture.get("montant_tva", 0))],
        ["TOTAL TTC", _format_euros(facture.get("montant_ttc", 0))],
    ]
    tt = Table(totaux, colWidths=[35*mm, 35*mm], hAlign='RIGHT')
    nb = len(totaux)
    tt.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 2*mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2*mm),
        ('TEXTCOLOR', (0, 0), (-1, -2), NOIR),
        ('LINEBELOW', (0, 0), (-1, nb - 2), 0.5, GRIS),
        ('FONTNAME', (0, nb - 1), (-1, nb - 1), 'DejaVuSans-Bold'),
        ('FONTSIZE', (0, nb - 1), (-1, nb - 1), 12),
        ('BACKGROUND', (0, nb - 1), (-1, nb - 1), BLEU_FONCE),
        ('TEXTCOLOR', (0, nb - 1), (-1, nb - 1), BLANC),
        ('TOPPADDING', (0, nb - 1), (-1, nb - 1), 3*mm),
        ('BOTTOMPADDING', (0, nb - 1), (-1, nb - 1), 3*mm),
        ('LEFTPADDING', (0, nb - 1), (-1, nb - 1), 3*mm),
        ('RIGHTPADDING', (0, nb - 1), (-1, nb - 1), 3*mm),
    ]))
    elements.append(tt)
    elements.append(Spacer(1, 6*mm))

    # Payment conditions
    elements.append(HRFlowable(width="100%", thickness=0.5, color=GRIS, spaceBefore=2*mm, spaceAfter=2*mm))
    elements.append(Paragraph(
        "Conditions de paiement : règlement à 30 jours à compter de la date d'émission.",
        _PETIT,
    ))

    # Bank info
    iban = config.get("iban", "")
    bic = config.get("bic", "")
    if iban:
        elements.append(Spacer(1, 3*mm))
        elements.append(Paragraph(f"Coordonnées bancaires : IBAN {iban} | BIC {bic}", _PETIT))

    # A03: Mentions legales — penalites de retard + indemnite recouvrement
    elements.append(Spacer(1, 5*mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=GRIS, spaceBefore=1*mm, spaceAfter=2*mm))
    elements.append(Paragraph(
        "Mentions légales : En cas de retard de paiement, une pénalité de 3 fois le taux "
        "d'intérêt légal sera appliquée (Art. L441-10 du Code de Commerce). Une indemnité "
        "forfaitaire de 40 EUR pour frais de recouvrement sera également due "
        "(Art. D441-5 du Code de Commerce).",
        _PETIT,
    ))

    # Footer with page numbering + conditional BROUILLON watermark (V92 S07)
    footer_text = f"{rs} — SIRET : {siret}" if siret else rs
    _is_brouillon = statut == "brouillon"

    def add_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        # V92 S07: watermark BROUILLON (diagonal, semi-transparent)
        if _is_brouillon:
            canvas_obj.setFont('DejaVuSans-Bold', 60)
            canvas_obj.setFillColor(HexColor("#FF0000"))
            canvas_obj.setFillAlpha(0.08)
            canvas_obj.saveState()
            canvas_obj.translate(A4[0] / 2, A4[1] / 2)
            canvas_obj.rotate(45)
            canvas_obj.drawCentredString(0, 0, "BROUILLON")
            canvas_obj.restoreState()
        # Footer text + page number
        canvas_obj.setFont('DejaVuSans', 7)
        canvas_obj.setFillColor(GRIS)
        canvas_obj.setFillAlpha(1.0)
        page_num = canvas_obj.getPageNumber()
        canvas_obj.drawCentredString(A4[0] / 2, 12*mm, f"{footer_text}  —  Page {page_num}")
        canvas_obj.restoreState()

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    buf.seek(0)
    return buf


# ═══════════════════════════════════════════════════════════════
# Realtime report PDF
# ═══════════════════════════════════════════════════════════════

def generate_realtime_report_pdf(kpi: dict, by_type: dict, table_data: list, period_label: str) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=25*mm)
    elements = []

    # Header
    header = Table([
        [
            Paragraph("<font color='#d4a843'>⚡</font> <b>Loto<font color='#d4a843'>IA</font></b>", _LOGO),
            Paragraph("<b>RAPPORT REALTIME</b>", _TITLE_R),
        ]
    ], colWidths=[90*mm, 80*mm])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    elements.append(header)
    elements.append(Spacer(1, 4*mm))

    elements.append(Paragraph(f"Période : {period_label} | Généré le {_format_date_fr(date.today())}", _PETIT))
    elements.append(Spacer(1, 8*mm))

    # KPI block
    elements.append(Paragraph("INDICATEURS", _SECTION))
    kpi_rows = [
        ["Total events", "Dernière heure", "Types distincts"],
        [str(kpi.get("total", 0)), str(kpi.get("hour", 0)), str(kpi.get("types", 0))],
    ]
    t = Table(kpi_rows, colWidths=[56*mm]*3)
    t.setStyle(_detail_table_style(2))
    elements.append(t)
    elements.append(Spacer(1, 8*mm))

    # By type breakdown
    if by_type:
        elements.append(Paragraph("RÉPARTITION PAR TYPE", _SECTION))
        bt_rows = [["Type", "Nombre"]]
        for etype, cnt in sorted(by_type.items(), key=lambda x: -x[1]):
            bt_rows.append([etype, str(cnt)])
        t = Table(bt_rows, colWidths=[120*mm, 40*mm])
        t.setStyle(_detail_table_style(len(bt_rows)))
        elements.append(t)
        elements.append(Spacer(1, 8*mm))

    # Detail table
    if table_data:
        elements.append(Paragraph("DÉTAIL DES ÉVÉNEMENTS", _SECTION))
        headers = ["Date/Heure", "Event", "Page", "Lang", "Device", "Pays"]
        rows = [headers]
        for r in table_data[:200]:
            rows.append([
                r.get("created_at", ""), r.get("event_type", ""), r.get("page", ""),
                r.get("lang", ""), r.get("device", ""), r.get("country", ""),
            ])
        t = Table(rows, colWidths=[32*mm, 35*mm, 38*mm, 14*mm, 18*mm, 18*mm])
        t.setStyle(_detail_table_style(len(rows)))
        elements.append(t)

    def footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont('DejaVuSans', 7)
        canvas_obj.setFillColor(GRIS)
        canvas_obj.drawCentredString(A4[0] / 2, 12*mm, "LotoIA — Rapport realtime généré automatiquement")
        canvas_obj.restoreState()

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    return buf


# ═══════════════════════════════════════════════════════════════
# Contrat PDF (S06)
# ═══════════════════════════════════════════════════════════════

def generate_contrat_pdf(contrat: dict, config: dict) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=25*mm)
    elements = []

    numero = contrat.get("numero", "")

    # Header
    header = Table([
        [
            Paragraph("<font color='#d4a843'>⚡</font> <b>Factur<font color='#d4a843'>IA</font></b>", _LOGO),
            Paragraph(f"<b>CONTRAT DE SPONSORING</b><br/><font size=10 color='#8891a4'>{numero}</font>", _TITLE_R),
        ]
    ], colWidths=[90*mm, 80*mm])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    elements.append(header)
    elements.append(Spacer(1, 8*mm))

    # Emitter / Client side by side
    rs = config.get("raison_sociale", "")
    addr = config.get("adresse", "")
    cp = config.get("code_postal", "")
    ville = config.get("ville", "")
    siret = config.get("siret", "")
    emitter_parts = [f"<b>{rs}</b>"]
    if addr:
        emitter_parts.append(addr.replace('\n', '<br/>'))
    if cp or ville:
        emitter_parts.append(f"{cp} {ville}".strip())
    if siret:
        emitter_parts.append(f"SIRET : {siret}")
    email = config.get("email", "")
    if email:
        emitter_parts.append(email)

    client_parts = [f"<b>{contrat.get('sponsor_nom', '')}</b>"]
    sponsor_addr = contrat.get("sponsor_adresse", "")
    if sponsor_addr:
        client_parts.append(sponsor_addr.replace('\n', '<br/>'))
    sponsor_siret = contrat.get("sponsor_siret", "")
    if sponsor_siret:
        client_parts.append(f"SIRET : {sponsor_siret}")

    addr_table = Table([
        [Paragraph("<br/>".join(emitter_parts), _NORMAL), Paragraph("<br/>".join(client_parts), _NORMAL)]
    ], colWidths=[85*mm, 85*mm])
    addr_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), GRIS_CLAIR),
        ('TOPPADDING', (0, 0), (-1, -1), 3*mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3*mm),
        ('LEFTPADDING', (0, 0), (-1, -1), 3*mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3*mm),
    ]))
    elements.append(addr_table)
    elements.append(Spacer(1, 8*mm))

    # Contract details
    dd = _format_date_fr(contrat.get("date_debut", ""))
    df = _format_date_fr(contrat.get("date_fin", ""))
    type_c = contrat.get("type_contrat", "standard")
    montant = _format_euros(contrat.get("montant_mensuel_ht", 0))

    elements.append(Paragraph("OBJET DU CONTRAT", _SECTION))
    elements.append(Spacer(1, 3*mm))

    details_rows = [
        ["Type :", type_c.replace("_", " ").title()],
        ["Durée :", f"Du {dd} au {df}"],
        ["Tarif mensuel HT :", montant],
    ]
    product_codes = contrat.get("product_codes", "")
    if product_codes:
        details_rows.append(["Product codes :", str(product_codes)])

    dt = Table(details_rows, colWidths=[45*mm, 125*mm])
    dt.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'DejaVuSans-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), GRIS),
        ('TEXTCOLOR', (1, 0), (1, -1), NOIR),
        ('TOPPADDING', (0, 0), (-1, -1), 2*mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2*mm),
    ]))
    elements.append(dt)
    elements.append(Spacer(1, 8*mm))

    # Emplacements
    elements.append(Paragraph("EMPLACEMENTS SPONSORS", _SECTION))
    elements.append(Spacer(1, 3*mm))
    emplacements = [
        ["E1", "Popup interstitiel", "Affichage avant génération de grille"],
        ["E2", "Vidéo META 75", "Spot vidéo dans l'analyse META 75 grilles"],
        ["E3", "Mention PDF", "Logo et mention dans les PDFs d'analyse"],
        ["E4", "Chatbot inline", "Insertion dans le chatbot (3 messages sur 6)"],
        ["E5", "Bannière résultats", "Bannière après les résultats du simulateur"],
        ["E6", "PDF download", "Tracking au téléchargement PDF"],
    ]
    if type_c == "standard":
        emplacements = [e for e in emplacements if e[0] in ("E1", "E4", "E5")]
    emp_rows = [["#", "Emplacement", "Description"]] + emplacements
    et = Table(emp_rows, colWidths=[15*mm, 50*mm, 105*mm])
    et.setStyle(_detail_table_style(len(emp_rows)))
    elements.append(et)
    elements.append(Spacer(1, 8*mm))

    # Conditions
    elements.append(Paragraph("CONDITIONS", _SECTION))
    elements.append(Spacer(1, 3*mm))
    conditions = [
        "Paiement : règlement à 30 jours à compter de la date de facturation.",
        "Résiliation : possible avec un préavis de 30 jours.",
        "Données : conformité RGPD — seuls des hash SHA-256 anonymes sont stockés. Aucune donnée personnelle.",
        "Reporting : accès au dashboard d'impressions, export CSV et PDF inclus.",
    ]
    for c in conditions:
        elements.append(Paragraph(f"• {c}", _NORMAL))
        elements.append(Spacer(1, 1*mm))

    cond_part = contrat.get("conditions_particulieres", "")
    if cond_part:
        elements.append(Spacer(1, 4*mm))
        elements.append(Paragraph("CONDITIONS PARTICULIERES", _SECTION))
        elements.append(Spacer(1, 3*mm))
        elements.append(Paragraph(str(cond_part), _NORMAL))

    elements.append(Spacer(1, 12*mm))

    # Signature blocks
    sig_table = Table([
        [Paragraph(f"<b>L'editeur</b><br/>{rs}", _NORMAL),
         Paragraph(f"<b>Le sponsor</b><br/>{contrat.get('sponsor_nom', '')}", _NORMAL)],
        ["Date et signature :", "Date et signature :"],
        ["", ""],
        ["", ""],
    ], colWidths=[85*mm, 85*mm])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 3*mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3*mm),
        ('LINEBELOW', (0, 0), (0, 0), 0.5, GRIS),
        ('LINEBELOW', (1, 0), (1, 0), 0.5, GRIS),
        ('FONTNAME', (0, 1), (-1, 1), 'DejaVuSans'),
        ('TEXTCOLOR', (0, 1), (-1, 1), GRIS),
        ('FONTSIZE', (0, 1), (-1, 1), 8),
    ]))
    elements.append(sig_table)

    footer_text = f"{rs} — SIRET : {siret}" if siret else rs

    def add_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont('DejaVuSans', 7)
        canvas_obj.setFillColor(GRIS)
        canvas_obj.drawCentredString(A4[0] / 2, 12*mm, footer_text)
        canvas_obj.restoreState()

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    buf.seek(0)
    return buf
