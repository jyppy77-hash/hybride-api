"""
Generate V8 sponsor pricing grids (Loto FR + EM Europe) as PDF.
Usage: py -3 scripts/generate_grilles_v8.py
UTF-8 font support via DejaVuSans (fallback Vera from ReportLab).
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def _register_fonts():
    """Enregistre polices UTF-8 : DejaVuSans -> Vera (fallback ReportLab)."""
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


_register_fonts()

# ── Colors ──
DARK_BLUE = HexColor("#1B2A4A")
MEDIUM_BLUE = HexColor("#2C3E6B")
HEADER_BLUE = HexColor("#2C3E6B")
LIGHT_GRAY = HexColor("#F5F5F5")
WHITE = white
GOLD = HexColor("#D4A017")
PURPLE = HexColor("#6B21A8")
GREEN_HIGHLIGHT = HexColor("#E8F5E9")
VERSION_TAG = "V8 \u2014 Pool Global"
UPDATE_DATE = "Mis \u00e0 jour le 19 mars 2026"

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm


# ── Styles ──
def make_styles():
    ss = getSampleStyleSheet()
    styles = {}
    styles["title"] = ParagraphStyle(
        "title", parent=ss["Title"],
        fontName="DejaVuSans-Bold", fontSize=22, leading=28,
        textColor=DARK_BLUE, alignment=TA_CENTER, spaceAfter=4,
    )
    styles["subtitle"] = ParagraphStyle(
        "subtitle", parent=ss["Normal"],
        fontName="DejaVuSans", fontSize=11, leading=14,
        textColor=DARK_BLUE, alignment=TA_CENTER, spaceAfter=2,
    )
    styles["confidential"] = ParagraphStyle(
        "confidential", parent=ss["Normal"],
        fontName="DejaVuSans-Bold", fontSize=9, leading=12,
        textColor=white, alignment=TA_CENTER,
        backColor=DARK_BLUE, spaceBefore=6, spaceAfter=6,
        borderPadding=(6, 10, 6, 10),
    )
    styles["h2"] = ParagraphStyle(
        "h2", parent=ss["Heading2"],
        fontName="DejaVuSans-Bold", fontSize=15, leading=20,
        textColor=DARK_BLUE, spaceBefore=14, spaceAfter=8,
    )
    styles["h3"] = ParagraphStyle(
        "h3", parent=ss["Heading3"],
        fontName="DejaVuSans-Bold", fontSize=12, leading=16,
        textColor=DARK_BLUE, spaceBefore=10, spaceAfter=6,
    )
    styles["body"] = ParagraphStyle(
        "body", parent=ss["Normal"],
        fontName="DejaVuSans", fontSize=9, leading=13,
        textColor=black, alignment=TA_JUSTIFY,
    )
    styles["body_small"] = ParagraphStyle(
        "body_small", parent=ss["Normal"],
        fontName="DejaVuSans", fontSize=7.5, leading=10,
        textColor=HexColor("#666666"), alignment=TA_LEFT,
    )
    styles["body_italic"] = ParagraphStyle(
        "body_italic", parent=ss["Normal"],
        fontName="DejaVuSans-Oblique", fontSize=7.5, leading=10,
        textColor=HexColor("#666666"),
    )
    styles["bullet"] = ParagraphStyle(
        "bullet", parent=ss["Normal"],
        fontName="DejaVuSans", fontSize=9, leading=13,
        textColor=black, leftIndent=14, bulletIndent=0,
        spaceBefore=2, spaceAfter=2,
    )
    styles["contact_center"] = ParagraphStyle(
        "contact_center", parent=ss["Normal"],
        fontName="DejaVuSans", fontSize=10, leading=14,
        textColor=DARK_BLUE, alignment=TA_CENTER,
    )
    styles["contact_bold"] = ParagraphStyle(
        "contact_bold", parent=ss["Normal"],
        fontName="DejaVuSans-Bold", fontSize=11, leading=15,
        textColor=DARK_BLUE, alignment=TA_CENTER,
    )
    styles["gold_banner"] = ParagraphStyle(
        "gold_banner", parent=ss["Normal"],
        fontName="DejaVuSans-Bold", fontSize=10, leading=14,
        textColor=DARK_BLUE, alignment=TA_CENTER,
        backColor=GOLD, borderPadding=(6, 10, 6, 10),
    )
    return styles


def _p(text, style):
    return Paragraph(text, style)


def _b(text):
    return f"<b>{text}</b>"


# ── Table helpers ──
def _base_table_style(header_bg=HEADER_BLUE, n_rows=1):
    """Standard table style with colored header and alternating rows."""
    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "DejaVuSans-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("FONTNAME", (0, 1), (-1, -1), "DejaVuSans"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
    ]
    return ts


def _pack_table_style(header_bg=HEADER_BLUE, n_rows=14):
    """Style for 2-column pack comparison tables (label | B | A)."""
    ts = [
        ("BACKGROUND", (1, 0), (1, 0), HEADER_BLUE),
        ("BACKGROUND", (2, 0), (2, 0), PURPLE),
        ("TEXTCOLOR", (1, 0), (2, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "DejaVuSans-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("FONTNAME", (0, 1), (-1, -1), "DejaVuSans"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    ts.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]))
    return ts


# ── Footer callback ──
def _footer(canvas, doc, version_tag=VERSION_TAG):
    canvas.saveState()
    canvas.setFont("DejaVuSans", 7)
    canvas.setFillColor(HexColor("#999999"))
    canvas.drawString(MARGIN, 12 * mm, version_tag)
    canvas.drawRightString(PAGE_W - MARGIN, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


# ── Pool Global table (shared) ──
def pool_global_section(S):
    elements = []
    elements.append(_p("Pool Global d'Impressions", S["h2"]))
    data = [
        ["Couverture du Partenariat", "D\u00e9finition", "Pool Mensuel Global"],
        ["Mono-March\u00e9", "1 code produit\n(ex : LOTO_FR_A, EM_DE_A)", "10 000 impressions"],
        ["R\u00e9gionale / Multi-March\u00e9s", "2 \u00e0 4 codes produits\n(ex : Pack FR Complet, Benelux, Ib\u00e9rique)", "15 000 impressions"],
        ["Continentale / Scale", "5+ codes produits\n(ex : Continental A ou B)", "25 000 impressions"],
    ]
    col_w = [55 * mm, 65 * mm, 45 * mm]
    t = Table(data, colWidths=col_w, repeatRows=1)
    ts = _base_table_style(n_rows=3)
    ts.append(("ALIGN", (0, 1), (0, -1), "LEFT"))
    ts.append(("ALIGN", (1, 1), (1, -1), "LEFT"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 4 * mm))
    elements.append(_p(
        "Le Pool Mensuel Global est mutualis\u00e9 sur l\u2019ensemble des march\u00e9s territoriaux souscrits. "
        "Au-del\u00e0 de ce volume, la facturation s\u2019effectue selon le mode de d\u00e9passement choisi (CPC ou CPM). "
        "Un plafond budg\u00e9taire de s\u00e9curit\u00e9 (Hard Cap) peut \u00eatre d\u00e9fini par l\u2019annonceur.",
        S["body"],
    ))
    elements.append(Spacer(1, 6 * mm))
    return elements


# ── Clause de revision V8 text ──
CLAUSE_V8_TEXT = (
    "Le partenariat accorde \u00e0 l\u2019annonceur un <b>Pool Mensuel Global</b> d\u2019impressions, "
    "mutualis\u00e9 sur l\u2019ensemble des march\u00e9s territoriaux souscrits "
    "(Mono-march\u00e9 : 10 000 ; R\u00e9gional : 15 000 ; Continental : 25 000). "
    "Au-del\u00e0 de ce volume global, la facturation des impressions suppl\u00e9mentaires "
    "s\u2019effectue selon le mode de d\u00e9passement choisi (CPC ou CPM)."
)


# ── Contact section ──
def contact_section(S):
    elements = []
    # gold banner
    ct = Table(
        [["Contact"]],
        colWidths=[165 * mm],
    )
    ct.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GOLD),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK_BLUE),
        ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(ct)
    elements.append(Spacer(1, 4 * mm))
    elements.append(_p("<b>Jean-Philippe Godard</b>", S["contact_center"]))
    elements.append(_p("Fondateur \u2014 LotoIA", S["contact_center"]))
    elements.append(_p("partenariats@lotoia.fr", S["contact_center"]))
    elements.append(_p("lotoia.fr", S["contact_center"]))
    elements.append(Spacer(1, 3 * mm))
    elements.append(_p("<i>Soutenu par Google for Startups</i>", S["contact_center"]))
    return elements


# ── Sources ──
def sources_section_loto(S):
    elements = []
    elements.append(_p("Sources", S["h2"]))
    sources = [
        "1. Reacheffect \u2014 Online Banner Advertising Rates in 2026",
        "2. The Creative Stable \u2014 Average Cost Per Click Guide 2026",
        "3. Google Ads Benchmarks 2025 (Search CPC ~2,69$ / Display CPC ~0,63$)",
        "4. L\u2019Internaute / FDJ \u2014 ~21 millions de joueurs, ~5 millions de r\u00e9guliers",
        "5. ANJ \u2014 Lignes directrices publicit\u00e9 jeux d\u2019argent (max 3 comm./jour/support)",
        "6. iGaming Business \u2014 Taxe 15% d\u00e9penses publicitaires op\u00e9rateurs jeux (juillet 2025)",
        "7. Audit interne des co\u00fbts API \u2014 Pipeline HYBRIDE (mars 2026)",
        "8. Google Analytics 4 \u2014 M\u00e9triques d\u2019engagement LotoIA (3-10 mars 2026)",
        "9. Umami Analytics \u2014 Volume r\u00e9el cookieless (3-10 mars 2026)",
    ]
    for s in sources:
        elements.append(_p(s, S["body"]))
    return elements


def sources_section_em(S):
    elements = []
    elements.append(_p("Sources", S["h2"]))
    sources = [
        "1. FDJ / EuroMillions.com \u2014 ~76 millions de joueurs par semaine en Europe",
        "2. Superads \u2014 Facebook Ads CPM/CPC Benchmarks par pays (2025-2026)",
        "3. AdAmigo.ai \u2014 Meta Ads CPM and CPC Benchmarks by Country 2026",
        "4. Growth Angels \u2014 Taux moyens Google Ads par secteur d\u2019activit\u00e9",
        "5. Agence Anode \u2014 Combien co\u00fbte Google Ads en 2026",
        "6. ANJ \u2014 Lignes directrices publicit\u00e9 jeux d\u2019argent",
        "7. iGaming Business \u2014 Taxe 15% d\u00e9penses publicitaires op\u00e9rateurs jeux (juillet 2025)",
        "8. Audit interne des co\u00fbts API \u2014 Pipeline HYBRIDE (mars 2026)",
        "9. Google Analytics 4 \u2014 M\u00e9triques d\u2019engagement LotoIA (3-10 mars 2026)",
        "10. Umami Analytics \u2014 Volume r\u00e9el cookieless (3-10 mars 2026)",
    ]
    for s in sources:
        elements.append(_p(s, S["body"]))
    return elements


# ========================================================================
#  LOTO FR PDF
# ========================================================================
def generate_loto_pdf(output_path):
    S = make_styles()
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=20 * mm,
    )
    elements = []

    # ── Page 1 : Header + Contexte + Chiffres ──
    elements.append(_p("Offre Sponsoring LotoIA 2026", S["title"]))
    elements.append(_p("Grille tarifaire \u2014 Codes produit LOTO_FR_A / LOTO_FR_B", S["subtitle"]))
    elements.append(Spacer(1, 3 * mm))

    # confidential banner
    conf_t = Table(
        [[f"Document confidentiel \u2014 Prospection partenaires pionniers | {UPDATE_DATE}"]],
        colWidths=[165 * mm],
    )
    conf_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, -1), white),
        ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(conf_t)
    elements.append(Spacer(1, 6 * mm))

    # Contexte
    elements.append(_p("Contexte", S["h2"]))
    elements.append(_p(
        "LotoIA est la premi\u00e8re plateforme fran\u00e7aise d\u2019analyse du Loto et de l\u2019EuroMillions par intelligence artificielle. "
        "La plateforme combine un algorithme propri\u00e9taire, le chatbot HYBRIDE (unique en France) et des rapports PDF professionnels. "
        "Soutenue par <b>Google for Startups</b>, positionn\u00e9e <b>#1 sur Bing</b> et en <b>page 1 de Google</b> sur ses mots-cl\u00e9s strat\u00e9giques.",
        S["body"],
    ))
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Base technique : 990+ tirages Loto + 733+ tirages EuroMillions | Architecture 100% Python/Cloud Run | "
        "Chatbot IA Grounded connect\u00e9 aux donn\u00e9es officielles FDJ en temps r\u00e9el | 1 400+ tests automatis\u00e9s.",
        S["body_italic"],
    ))
    elements.append(Spacer(1, 4 * mm))

    # Technologie Grounded AI
    elements.append(_p("Technologie Grounded AI", S["h2"]))
    elements.append(_p(
        "Le chatbot HYBRIDE repose sur une architecture dite <b>Grounded AI</b> (IA ancr\u00e9e) : contrairement aux chatbots "
        "g\u00e9n\u00e9ratifs classiques qui peuvent inventer des r\u00e9ponses (hallucinations), HYBRIDE g\u00e9n\u00e8re ses r\u00e9ponses "
        "exclusivement \u00e0 partir de donn\u00e9es v\u00e9rifi\u00e9es et structur\u00e9es (base SQL officielle FDJ).",
        S["body"],
    ))
    bullets_grounded = [
        "<b>Ancr\u00e9e dans les donn\u00e9es r\u00e9elles</b> \u2014 chaque statistique est tra\u00e7able",
        "<b>V\u00e9rifiable</b> \u2014 l\u2019utilisateur peut recouper avec les r\u00e9sultats officiels FDJ",
        "<b>Anti-hallucination</b> \u2014 le syst\u00e8me refuse de r\u00e9pondre plut\u00f4t que d\u2019inventer",
        "<b>Refus de pr\u00e9diction</b> \u2014 HYBRIDE ne pr\u00e9dit jamais les num\u00e9ros gagnants",
    ]
    for b in bullets_grounded:
        elements.append(_p(f"\u2022 {b}", S["bullet"]))
    elements.append(Spacer(1, 4 * mm))

    # Chiffres cles
    elements.append(_p("Chiffres cl\u00e9s", S["h2"]))
    data_kpi = [
        ["Audience cible", "Concurrence directe", "Emplacements sponsors", "Modules"],
        ["~5 millions\njoueurs r\u00e9guliers FDJ", "0 concurrent\nchatbot IA Loto en France",
         "2 par module\nexclusivit\u00e9 garantie", "Loto FR + EuroMillions\nlancement EM 15/03/26"],
    ]
    t = Table(data_kpi, colWidths=[42 * mm] * 4)
    t.setStyle(TableStyle(_base_table_style(n_rows=1)))
    elements.append(t)
    elements.append(Spacer(1, 4 * mm))

    # Metriques engagement
    elements.append(_p("M\u00e9triques d\u2019engagement (semaine du 3-10 mars 2026)", S["h3"]))
    data_eng = [
        ["Engagement / visiteur", "Session record", "Taux de rebond\nsimulateur", "Trafic organique"],
        ["32 events / visiteur\nvs 3-5 moyenne web\n(+600%)", "53 min 24 s\n38 events (utilisateur\norganique)",
         "3,1%\nsource : GA4", "62%\ngoogle/organic (GA4)"],
    ]
    t = Table(data_eng, colWidths=[42 * mm] * 4)
    t.setStyle(TableStyle(_base_table_style(n_rows=1)))
    elements.append(t)

    # ── Page 2 : Nomenclature + Emplacements ──
    elements.append(PageBreak())
    elements.append(_p("1. Nomenclature produit", S["h2"]))
    elements.append(_p(
        "Chaque emplacement sponsor est identifi\u00e9 par un code produit unique, directement visible sur la plateforme et dans les rapports analytics.",
        S["body"],
    ))
    elements.append(Spacer(1, 3 * mm))

    data_nom = [
        ["Code produit", "Tier", "Module", "Emplacements", "Tarif lancement"],
        ["LOTO_FR_A", "Premium", "Loto France", "E1 + E2 + E3 + E4 + E5\n(5 emplacements)", "449 EUR / mois"],
        ["LOTO_FR_B", "Standard", "Loto France", "E1 + E4 + E5\n(3 emplacements)", "199 EUR / mois"],
    ]
    col_w_nom = [30 * mm, 22 * mm, 25 * mm, 48 * mm, 35 * mm]
    t = Table(data_nom, colWidths=col_w_nom)
    ts = _base_table_style(n_rows=2)
    ts.append(("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"))
    ts.append(("FONTNAME", (4, 1), (4, -1), "DejaVuSans-Bold"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "\u00c0 terme, le m\u00eame mod\u00e8le sera r\u00e9pliqu\u00e9 pour l\u2019EuroMillions par secteur de langue : "
        "EM_FR_A/B, EM_EN_A/B, EM_ES_A/B, EM_PT_A/B, EM_DE_A/B, EM_NL_A/B \u2014 soit 14 codes produit au total.",
        S["body_italic"],
    ))
    elements.append(Spacer(1, 6 * mm))

    # Emplacements publicitaires
    elements.append(_p("2. Emplacements publicitaires", S["h2"]))
    elements.append(_p(
        "Cinq emplacements natifs int\u00e9gr\u00e9s au parcours utilisateur, conformes aux recommandations ANJ "
        "(maximum 3 communications par jour par support). En moyenne, un utilisateur actif voit le sponsor jusqu\u2019\u00e0 "
        "<b>9 fois par session</b>, sans format intrusif.",
        S["body"],
    ))
    elements.append(Spacer(1, 3 * mm))
    data_emp = [
        ["#", "Emplacement", "Format", "Dur\u00e9e / Fr\u00e9quence", "Codes produit"],
        ["E1", "Simulateur /\nG\u00e9n\u00e9rateur", "2 encarts c\u00f4te \u00e0 c\u00f4te", "3 \u00e0 15 sec par\ng\u00e9n\u00e9ration", "LOTO_FR_A\n+ LOTO_FR_B"],
        ["E2", "Analyse META 75", "Vid\u00e9o 30 sec pre-roll", "Avant remise du PDF", "LOTO_FR_A\nuniquement"],
        ["E3", "Rapport PDF", 'Mention "Analyse\nofferte par..."', "Permanente (PDF)", "LOTO_FR_A\nuniquement"],
        ["E4", "Chatbot\nHYBRIDE", "Message sponsoris\u00e9\ninline", "Rotation A/B :\nmsg 3=A, msg 6=B", "LOTO_FR_A\n+ LOTO_FR_B"],
        ["E5", "R\u00e9sultats\ng\u00e9n\u00e9rateur", "Banni\u00e8re sous\nchaque grille", "Apr\u00e8s chaque grille", "LOTO_FR_A\n+ LOTO_FR_B"],
    ]
    col_w_emp = [12 * mm, 30 * mm, 35 * mm, 38 * mm, 30 * mm]
    t = Table(data_emp, colWidths=col_w_emp)
    ts = _base_table_style(n_rows=5)
    ts.append(("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "R\u00e9partition indicative des impressions pour 10 000 impressions/mois : Simulateur ~30% | "
        "Chatbot ~30% | R\u00e9sultats ~20% | Vid\u00e9o META 75 ~10% | PDF ~10%",
        S["body_italic"],
    ))

    # ── Page 3 : Packs tarifaires ──
    elements.append(PageBreak())
    elements.append(_p("3. Packs tarifaires", S["h2"]))

    data_pack = [
        ["", "LOTO_FR_B\nStandard", "LOTO_FR_A\nPremium"],
        ["Tarif mensuel", "199 EUR / mois", "449 EUR / mois"],
        ["Engagement minimum", "3 mois", "6 mois"],
        ["R\u00e9duction 6 mois", "-10% (179 EUR/mois)", "-10% (404 EUR/mois)"],
        ["R\u00e9duction 12 mois", "-20% (159 EUR/mois)", "-20% (359 EUR/mois)"],
        ["Emplacements", "E1, E4, E5", "E1, E2, E3, E4, E5"],
        ["Vid\u00e9o META 75", "Non", "Oui \u2014 vid\u00e9o 30s pre-roll"],
        ["Mention rapport PDF", "Non", '"Analyse offerte par..."'],
        ["Badge", "Partenaire officiel", "Sponsor fondateur\n+ Partenaire officiel"],
        ["Exclusivit\u00e9 sectorielle", "Non", "Oui (optionnelle)"],
        ["Rapport analytics", "Mensuel", "Hebdomadaire"],
        ["Impressions incluses", "voir Pool Global\nci-dessous", "voir Pool Global\nci-dessous"],
        ["Chatbot rotation", "Msg 6, 12, 18...", "Msg 3, 9, 15... (priorit\u00e9)"],
        ["Acc\u00e8s EuroMillions", "Tarif n\u00e9goci\u00e9", "Tarif n\u00e9goci\u00e9"],
    ]
    col_w_pack = [45 * mm, 58 * mm, 58 * mm]
    t = Table(data_pack, colWidths=col_w_pack)
    t.setStyle(TableStyle(_pack_table_style()))
    elements.append(t)
    elements.append(Spacer(1, 4 * mm))

    # Avantage Pionnier
    ap_t = Table(
        [["Avantage Pionnier"]],
        colWidths=[165 * mm],
    )
    ap_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GOLD),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK_BLUE),
        ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(ap_t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Les 2 premiers partenaires b\u00e9n\u00e9ficient d\u2019un <b>gel tarifaire de 6 mois</b> au tarif de lancement. "
        "\u00c0 l\u2019issue des 6 mois, le tarif est r\u00e9vis\u00e9 selon des paliers d\u2019audience d\u00e9finis contractuellement.",
        S["body"],
    ))

    # ── Pool Global ──
    elements.append(Spacer(1, 6 * mm))
    elements.extend(pool_global_section(S))

    # ── Page 4 : Clause + Garanties ──
    elements.append(_p("4. Clause de r\u00e9vision tarifaire", S["h2"]))
    elements.append(_p(CLAUSE_V8_TEXT, S["body"]))
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p("Au-del\u00e0, deux modes de facturation au choix :", S["body"]))
    elements.append(Spacer(1, 3 * mm))

    data_cpc = [
        ["", "CPC (Co\u00fbt par clic)", "CPM (Co\u00fbt par mille)"],
        ["Tarif", "0,30 EUR / clic", "15 EUR / 1 000 impressions"],
        ["Id\u00e9al pour", "Performance (leads)", "Notori\u00e9t\u00e9 (branding)"],
        ["Exemple +10K", "200 clics (2% CTR) = 60 EUR", "10 000 impr. = 150 EUR"],
    ]
    t = Table(data_cpc, colWidths=[38 * mm, 62 * mm, 62 * mm])
    ts = _base_table_style(n_rows=3)
    ts.append(("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"))
    ts.append(("FONTNAME", (1, 1), (-1, 1), "DejaVuSans-Bold"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Comparatif march\u00e9 : Google Ads ~2,50 EUR/clic | Facebook ~0,80 EUR/clic | LotoIA : 4x \u00e0 8x moins cher. "
        "Display Google : 2-5 EUR CPM | LotoIA : fourchette premium.",
        S["body_italic"],
    ))
    elements.append(Spacer(1, 2 * mm))
    bullets_clause = [
        "<b>Choix modifiable</b> : le mode CPC ou CPM est r\u00e9visable chaque trimestre",
        "<b>Plafond optionnel</b> : le partenaire peut fixer un montant max (ex : 200 EUR)",
        "<b>Formule hybride</b> : CPC sur chatbot (E4) + CPM sur banni\u00e8res (E1, E5)",
        "<b>Suivi conversions</b> : actions post-clic via GA4 events personnalis\u00e9s",
    ]
    for b in bullets_clause:
        elements.append(_p(f"\u2022 {b}", S["bullet"]))

    # ── Page 5 : Garanties + Conformite + Mesure ──
    elements.append(PageBreak())
    elements.append(_p("5. Garanties et paliers d\u2019audience", S["h2"]))
    elements.append(_p("Garantie de volume", S["h3"]))
    elements.append(_p(
        "Si LotoIA n\u2019atteint pas <b>5 000 impressions</b> sur un mois donn\u00e9, les impressions manquantes sont "
        "report\u00e9es sur le mois suivant (cr\u00e9dit cumul\u00e9 sur 3 mois maximum).",
        S["body"],
    ))
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Si LotoIA n\u2019atteint pas <b>2 000 impressions</b> sur 2 mois cons\u00e9cutifs, le partenaire peut r\u00e9silier "
        "sans frais avec un pr\u00e9avis de 15 jours.",
        S["body"],
    ))
    elements.append(Spacer(1, 4 * mm))

    elements.append(_p("Paliers d\u2019audience et r\u00e9vision tarifaire", S["h3"]))
    data_pal = [
        ["Palier", "Impressions / mois", "LOTO_FR_B", "LOTO_FR_A", "Hausse max"],
        ["Lancement", "0 - 10 000", "199 EUR (gel)", "449 EUR (gel)", "\u2014"],
        ["Croissance", "10 001 - 30 000", "249 EUR", "549 EUR", "+25% max"],
        ["Traction", "30 001 - 100 000", "349 EUR", "749 EUR", "+25% max"],
        ["Scale", "100 001+", "Sur mesure", "Sur mesure", "N\u00e9goci\u00e9"],
    ]
    col_w_pal = [28 * mm, 35 * mm, 30 * mm, 30 * mm, 25 * mm]
    t = Table(data_pal, colWidths=col_w_pal)
    ts = _base_table_style(n_rows=4)
    ts.append(("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"))
    ts.append(("FONTNAME", (2, 1), (3, 1), "DejaVuSans-Bold"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "La clause de hausse maximum (+25%) garantit que le tarif ne peut pas plus que doubler sur 24 mois.",
        S["body_italic"],
    ))
    elements.append(Spacer(1, 6 * mm))

    # Conformite
    elements.append(_p("6. Conformit\u00e9 r\u00e9glementaire", S["h2"]))
    bullets_conf = [
        "<b>Limitation d\u2019exposition</b> : max 3 communications commerciales par jour par support (ANJ)",
        "<b>Chatbot</b> : rotation A/B, 1 message sponsor toutes les 3 r\u00e9ponses (msg 3=A, msg 6=B)",
        "<b>Protection des joueurs</b> : aucune incitation \u00e0 jouer davantage",
        "<b>RGPD</b> : aucune donn\u00e9e personnelle partag\u00e9e avec les sponsors. Rapports GA4 anonymis\u00e9s",
        "<b>Clause d\u2019adaptation</b> : en cas d\u2019\u00e9volution r\u00e9glementaire ANJ, adaptation sans frais",
        "<b>Taxe 15%</b> : ne s\u2019applique pas aux annonceurs non-op\u00e9rateurs de jeux",
    ]
    for b in bullets_conf:
        elements.append(_p(f"\u2022 {b}", S["bullet"]))
    elements.append(Spacer(1, 6 * mm))

    # Mesure de performance
    elements.append(_p("7. Mesure de performance et transparence", S["h2"]))
    data_perf = [
        ["Indicateur", "Description", "Pack"],
        ["Impressions", "Affichages par emplacement (avec sponsor_id)", "Tous"],
        ["Clics", "Clics sur banni\u00e8re / message sponsor", "Tous"],
        ["CTR", "Taux de clics (clics / impressions)", "Tous"],
        ["Conversions", "Actions post-clic via GA4 events", "Tous"],
        ["PDF downloads", "Rapports PDF avec mention sponsor", "LOTO_FR_A"],
        ["Vid\u00e9o completion", "Taux de visionnage vid\u00e9o 30s", "LOTO_FR_A"],
    ]
    col_w_perf = [32 * mm, 100 * mm, 28 * mm]
    t = Table(data_perf, colWidths=col_w_perf)
    ts = _base_table_style(n_rows=6)
    ts.append(("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"))
    ts.append(("ALIGN", (0, 1), (0, -1), "LEFT"))
    ts.append(("ALIGN", (1, 1), (1, -1), "LEFT"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Tous les indicateurs sont mesur\u00e9s via Google Analytics 4, accessible au partenaire en lecture seule. "
        "Chaque impression est track\u00e9e avec le code produit (LOTO_FR_A ou LOTO_FR_B) pour une facturation pr\u00e9cise.",
        S["body_italic"],
    ))

    # ── Page 6 : Vision EM + Pourquoi + Contact + Sources ──
    elements.append(PageBreak())
    elements.append(_p("8. Vision EuroMillions \u2014 Extension multi-langue", S["h2"]))
    elements.append(_p(
        "Le m\u00eame mod\u00e8le 2 slots (A Premium + B Standard) sera r\u00e9pliqu\u00e9 pour chaque secteur de langue EuroMillions "
        "d\u00e8s le <b>15 mars 2026</b>. L\u2019ajout d\u2019un pays = de la configuration, z\u00e9ro code \u00e0 toucher.",
        S["body"],
    ))
    elements.append(Spacer(1, 3 * mm))

    data_em_vision = [
        ["Code produit A", "Code produit B", "Langue", "Pays couverts"],
        ["EM_FR_A", "EM_FR_B", "Fran\u00e7ais", "France, Belgique (FR), Luxembourg,\nSuisse (FR)"],
        ["EM_EN_A", "EM_EN_B", "English", "United Kingdom, Ireland"],
        ["EM_ES_A", "EM_ES_B", "Espa\u00f1ol", "Espa\u00f1a"],
        ["EM_PT_A", "EM_PT_B", "Portugu\u00eas", "Portugal"],
        ["EM_DE_A", "EM_DE_B", "Deutsch", "\u00d6sterreich, Schweiz (DE)"],
        ["EM_NL_A", "EM_NL_B", "Nederlands", "Nederland, Belgi\u00eb (NL)"],
    ]
    col_w_emv = [32 * mm, 32 * mm, 28 * mm, 65 * mm]
    t = Table(data_em_vision, colWidths=col_w_emv)
    ts = _base_table_style(n_rows=6)
    ts.append(("FONTNAME", (0, 1), (1, -1), "DejaVuSans-Bold"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 4 * mm))

    # Packs commerciaux
    elements.append(_p("Packs commerciaux", S["h3"]))
    bullets_pc = [
        "<b>Slot unitaire</b> : 1 code produit (ex: LOTO_FR_B = 199 EUR/mois)",
        "<b>Pack langue</b> : Loto + EM m\u00eame langue (ex: LOTO_FR_A + EM_FR_A = tarif n\u00e9goci\u00e9)",
        "<b>Pack multi-langue</b> : tous les slots A d\u2019une r\u00e9gion (ex: Pack DACH = EM_DE_A, id\u00e9al n\u00e9obanques)",
        "<b>Pack continental</b> : 7 slots A (LOTO_FR + 6 EM) = sur mesure, id\u00e9al Revolut/N26/Lydia",
    ]
    for b in bullets_pc:
        elements.append(_p(f"\u2022 {b}", S["bullet"]))
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Total : 14 codes produit (2 Loto FR + 12 EM). Chaque code = 1 contrat = 1 facturation = 1 tracking analytics.",
        S["body_italic"],
    ))
    elements.append(Spacer(1, 6 * mm))

    # Pourquoi
    elements.append(_p("9. Pourquoi devenir partenaire pionnier", S["h2"]))
    bullets_why = [
        "<b>Tarif de lancement gel\u00e9 6 mois</b> \u2014 vous entrez au prix le plus bas",
        "<b>Exclusivit\u00e9 (2 sponsors max par module)</b> \u2014 pas de r\u00e9gie publicitaire",
        "<b>Oc\u00e9an bleu</b> \u2014 z\u00e9ro concurrent direct sur le chatbot IA Loto en France",
        "<b>EuroMillions en bonus</b> \u2014 acc\u00e8s prioritaire module EM, potentiel audience x3",
        "<b>Garantie de volume</b> \u2014 report d\u2019impressions ou r\u00e9siliation sans frais",
        "<b>Transparence totale</b> \u2014 GA4 en lecture seule, tracking par code produit",
        "<b>Clause +25% max</b> \u2014 protection contre les hausses brutales de tarif",
        "<b>Codes produit clairs</b> \u2014 LOTO_FR_A/B visibles sur le site = ce que vous achetez",
        "<b>Infrastructure scalable</b> \u2014 architecture 100% Cloud, co\u00fbt marginal quasi nul par impression",
    ]
    for b in bullets_why:
        elements.append(_p(f"\u2022 {b}", S["bullet"]))
    elements.append(Spacer(1, 6 * mm))

    # Contact
    elements.extend(contact_section(S))
    elements.append(Spacer(1, 8 * mm))

    # Sources
    elements.extend(sources_section_loto(S))

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    print(f"[OK] {output_path}")


# ========================================================================
#  EM EUROPE PDF
# ========================================================================
def generate_em_pdf(output_path):
    S = make_styles()
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=20 * mm,
    )
    elements = []

    # ── Page 1 : Header + Contexte + Chiffres ──
    elements.append(_p("Offre Sponsoring LotoIA 2026", S["title"]))
    elements.append(_p("EuroMillions Europe \u2014 12 codes produit \u00d7 6 langues \u00d7 9 pays", S["subtitle"]))
    elements.append(Spacer(1, 3 * mm))

    conf_t = Table(
        [[f"Document confidentiel \u2014 Prospection partenaires pionniers | {UPDATE_DATE}"]],
        colWidths=[165 * mm],
    )
    conf_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, -1), white),
        ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(conf_t)
    elements.append(Spacer(1, 6 * mm))

    # Contexte
    elements.append(_p("Contexte", S["h2"]))
    elements.append(_p(
        "L\u2019EuroMillions est le plus grand jeu de loterie europ\u00e9en, jou\u00e9 dans <b>9 pays</b> : France, Royaume-Uni, Irlande, "
        "Espagne, Portugal, Autriche, Suisse, Belgique et Luxembourg.",
        S["body"],
    ))
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "LotoIA lance le <b>15 mars 2026</b> son module EuroMillions multilingue avec chatbot HYBRIDE en 6 langues "
        "(FR, EN, ES, PT, DE, NL), couvrant les 9 pays participants.",
        S["body"],
    ))
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Base technique : 733+ tirages EM | 42 pages multilingues | 1 400+ tests automatis\u00e9s | "
        "Architecture 100% Python/Cloud Run | Chatbot IA Grounded connect\u00e9 aux donn\u00e9es officielles.",
        S["body_italic"],
    ))
    elements.append(Spacer(1, 4 * mm))

    # Chiffres cles
    elements.append(_p("Chiffres cl\u00e9s", S["h2"]))
    data_kpi = [
        ["Audience cible", "Concurrence", "Sponsors par langue", "Langues"],
        ["~76M joueurs\nEM/semaine\nen Europe", "0 chatbot IA EM\nen Europe",
         "2 max\n(exclusivit\u00e9)", "6\n(FR EN ES PT DE NL)"],
    ]
    t = Table(data_kpi, colWidths=[42 * mm] * 4)
    t.setStyle(TableStyle(_base_table_style(n_rows=1)))
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Source : FDJ / EuroMillions.com \u2014 environ 76 millions de joueurs par semaine en Europe.",
        S["body_italic"],
    ))

    # ── Page 2 : Nomenclature 12 codes + Emplacements ──
    elements.append(PageBreak())
    elements.append(_p("1. Nomenclature des 12 codes produit EM", S["h2"]))
    elements.append(_p(
        "Chaque emplacement sponsor est identifi\u00e9 par un code produit unique. Les tarifs sont diff\u00e9renci\u00e9s par "
        "<b>Tier de march\u00e9</b> selon les co\u00fbts publicitaires locaux.",
        S["body"],
    ))
    elements.append(Spacer(1, 3 * mm))

    # Tier explanation table
    data_tier = [
        ["Tier", "March\u00e9s", "Justification"],
        ["Tier 1 \u2014 Premium+", "EN (UK, IE)\nDE (AT, CH)",
         "CPM Meta/Google 25-30% sup\u00e9rieur \u00e0 la France.\nMarch\u00e9s pub les plus chers d\u2019Europe."],
        ["Tier 2 \u2014 Standard", "FR (FR, BE, LU, CH)\nNL (NL, BE)\nES (ES) / PT (PT)",
         "Alignement sur les tarifs Loto FR valid\u00e9s.\nVolume de joueurs massif en Espagne/Portugal."],
    ]
    t = Table(data_tier, colWidths=[38 * mm, 42 * mm, 80 * mm])
    ts = _base_table_style(n_rows=2)
    ts.append(("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"))
    ts.append(("ALIGN", (1, 1), (-1, -1), "LEFT"))
    ts.append(("BACKGROUND", (0, 1), (-1, 1), HexColor("#E8E0F0")))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 4 * mm))

    # 12 codes table
    data_codes = [
        ["Code A\n(Premium)", "Code B\n(Standard)", "Langue", "Pays couverts", "Tarif A", "Tarif B", "Tier"],
        ["EM_EN_A", "EM_EN_B", "English", "UK, Ireland", "549 EUR", "249 EUR", "1"],
        ["EM_DE_A", "EM_DE_B", "Deutsch", "AT, CH(DE)", "549 EUR", "249 EUR", "1"],
        ["EM_FR_A", "EM_FR_B", "Fran\u00e7ais", "FR, BE(FR), LU,\nCH(FR)", "449 EUR", "199 EUR", "2"],
        ["EM_NL_A", "EM_NL_B", "Nederlands", "NL, BE(NL)", "449 EUR", "199 EUR", "2"],
        ["EM_ES_A", "EM_ES_B", "Espa\u00f1ol", "Espa\u00f1a", "449 EUR", "199 EUR", "2"],
        ["EM_PT_A", "EM_PT_B", "Portugu\u00eas", "Portugal", "449 EUR", "199 EUR", "2"],
    ]
    col_w_codes = [24 * mm, 24 * mm, 22 * mm, 35 * mm, 22 * mm, 22 * mm, 14 * mm]
    t = Table(data_codes, colWidths=col_w_codes)
    ts = _base_table_style(n_rows=6)
    ts.append(("FONTNAME", (0, 1), (1, -1), "DejaVuSans-Bold"))
    ts.append(("FONTNAME", (4, 1), (5, -1), "DejaVuSans-Bold"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Total : 12 codes produit EM + 2 Loto FR = 14 codes. Chaque code = 1 contrat = 1 facturation = 1 tracking.",
        S["body_italic"],
    ))
    elements.append(Spacer(1, 6 * mm))

    # Emplacements
    elements.append(_p("2. Emplacements publicitaires", S["h2"]))
    elements.append(_p(
        "Cinq emplacements natifs int\u00e9gr\u00e9s au parcours utilisateur, conformes aux recommandations ANJ "
        "(maximum 3 communications par jour par support).",
        S["body"],
    ))
    elements.append(Spacer(1, 3 * mm))
    data_emp = [
        ["#", "Emplacement", "Format", "Dur\u00e9e / Fr\u00e9quence", "Codes produit"],
        ["E1", "Simulateur /\nG\u00e9n\u00e9rateur", "2 encarts c\u00f4te \u00e0 c\u00f4te", "3 \u00e0 15 sec par\ng\u00e9n\u00e9ration", "EM_xx_A\n+ EM_xx_B"],
        ["E2", "Analyse META 75", "Vid\u00e9o 30 sec pre-roll", "Avant remise du PDF", "EM_xx_A\nuniquement"],
        ["E3", "Rapport PDF", 'Mention "Analyse\nofferte par..."', "Permanente (PDF)", "EM_xx_A\nuniquement"],
        ["E4", "Chatbot\nHYBRIDE", "Message sponsoris\u00e9\ninline", "Rotation A/B :\nmsg 3=A, msg 6=B", "EM_xx_A\n+ EM_xx_B"],
        ["E5", "R\u00e9sultats\ng\u00e9n\u00e9rateur", "Banni\u00e8re sous\nchaque grille", "Apr\u00e8s chaque grille", "EM_xx_A\n+ EM_xx_B"],
    ]
    col_w_emp = [12 * mm, 30 * mm, 35 * mm, 38 * mm, 30 * mm]
    t = Table(data_emp, colWidths=col_w_emp)
    ts = _base_table_style(n_rows=5)
    ts.append(("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "xx = code langue (FR, EN, ES, PT, DE, NL). R\u00e9partition : Simulateur ~30% | Chatbot ~30% | "
        "R\u00e9sultats ~20% | Vid\u00e9o ~10% | PDF ~10%",
        S["body_italic"],
    ))

    # ── Page 3 : Packs tarifaires Tier 1 + Tier 2 ──
    elements.append(PageBreak())
    elements.append(_p("3. Packs tarifaires (par langue)", S["h2"]))

    # Tier 1
    elements.append(_p("Tier 1 \u2014 March\u00e9s Premium+ (EN / DE)", S["h3"]))
    data_t1 = [
        ["", "EM_xx_B\nStandard", "EM_xx_A\nPremium"],
        ["Tarif mensuel", "249 EUR / mois", "549 EUR / mois"],
        ["Engagement minimum", "3 mois", "6 mois"],
        ["R\u00e9duction 6 mois", "-10% (224 EUR/mois)", "-10% (494 EUR/mois)"],
        ["R\u00e9duction 12 mois", "-20% (199 EUR/mois)", "-20% (439 EUR/mois)"],
        ["Emplacements", "E1, E4, E5", "E1, E2, E3, E4, E5"],
        ["Vid\u00e9o META 75", "Non", "Oui \u2014 vid\u00e9o 30s pre-roll"],
        ["Mention rapport PDF", "Non", '"Analyse offerte par..."'],
        ["Badge", "Partenaire officiel", "Sponsor fondateur\n+ Partenaire officiel"],
        ["Exclusivit\u00e9 sectorielle", "Non", "Oui (optionnelle)"],
        ["Rapport analytics", "Mensuel", "Hebdomadaire"],
        ["Impressions incluses", "voir Pool Global\nci-dessous", "voir Pool Global\nci-dessous"],
        ["Chatbot rotation", "Msg 6, 12, 18...", "Msg 3, 9, 15... (priorit\u00e9)"],
    ]
    t = Table(data_t1, colWidths=[45 * mm, 58 * mm, 58 * mm])
    t.setStyle(TableStyle(_pack_table_style()))
    elements.append(t)
    elements.append(Spacer(1, 6 * mm))

    # Tier 2
    elements.append(_p("Tier 2 \u2014 March\u00e9s Standard (FR / NL / ES / PT)", S["h3"]))
    data_t2 = [
        ["", "EM_xx_B\nStandard", "EM_xx_A\nPremium"],
        ["Tarif mensuel", "199 EUR / mois", "449 EUR / mois"],
        ["Engagement minimum", "3 mois", "6 mois"],
        ["R\u00e9duction 6 mois", "-10% (179 EUR/mois)", "-10% (404 EUR/mois)"],
        ["R\u00e9duction 12 mois", "-20% (159 EUR/mois)", "-20% (359 EUR/mois)"],
        ["Emplacements", "E1, E4, E5", "E1, E2, E3, E4, E5"],
        ["Vid\u00e9o META 75", "Non", "Oui \u2014 vid\u00e9o 30s pre-roll"],
        ["Mention rapport PDF", "Non", '"Analyse offerte par..."'],
        ["Badge", "Partenaire officiel", "Sponsor fondateur\n+ Partenaire officiel"],
        ["Exclusivit\u00e9 sectorielle", "Non", "Oui (optionnelle)"],
        ["Rapport analytics", "Mensuel", "Hebdomadaire"],
        ["Impressions incluses", "voir Pool Global\nci-dessous", "voir Pool Global\nci-dessous"],
        ["Chatbot rotation", "Msg 6, 12, 18...", "Msg 3, 9, 15... (priorit\u00e9)"],
    ]
    t = Table(data_t2, colWidths=[45 * mm, 58 * mm, 58 * mm])
    t.setStyle(TableStyle(_pack_table_style()))
    elements.append(t)
    elements.append(Spacer(1, 4 * mm))

    # Avantage Pionnier
    ap_t = Table(
        [["Avantage Pionnier"]],
        colWidths=[165 * mm],
    )
    ap_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GOLD),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK_BLUE),
        ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(ap_t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Les 2 premiers partenaires par langue b\u00e9n\u00e9ficient d\u2019un <b>gel tarifaire de 6 mois</b> au tarif de lancement. "
        "\u00c0 l\u2019issue des 6 mois, le tarif est r\u00e9vis\u00e9 selon des paliers d\u2019audience d\u00e9finis contractuellement.",
        S["body"],
    ))

    # ── Page 4 : Packs regionaux + Pool Global ──
    elements.append(PageBreak())
    elements.append(_p("4. Packs r\u00e9gionaux", S["h2"]))
    elements.append(_p(
        "Regroupements commerciaux pour sponsors multi-pays. Id\u00e9al pour les n\u00e9obanques europ\u00e9ennes "
        "(Revolut, N26, Lydia) et les services financiers transfrontaliers.",
        S["body"],
    ))
    elements.append(Spacer(1, 3 * mm))

    data_reg = [
        ["Pack", "Codes inclus", "Pays\ncouverts", "Prix\ncumul\u00e9", "R\u00e9duction", "Tarif Pack", "Pool\nAttribu\u00e9"],
        ["FR Complet", "LOTO_FR_A\n+ EM_FR_A", "France\n(Loto + EM)", "898 EUR", "-10%", "799 EUR", "15 000\n/mois"],
        ["Pack DACH", "EM_DE_A", "DE, AT, CH", "549 EUR", "\u2014", "549 EUR", "10 000\n/mois"],
        ["Benelux", "EM_FR_A\n+ EM_NL_A", "BE, NL, LU", "898 EUR", "-10%", "799 EUR", "15 000\n/mois"],
        ["Ib\u00e9rique", "EM_ES_A\n+ EM_PT_A", "ES, PT", "898 EUR", "-15%", "759 EUR", "15 000\n/mois"],
        ["Continental A", "LOTO_FR_A\n+ 6 \u00d7 EM_*_A", "9 pays\n(Premium)", "3 343 EUR", "-25%", "2 499 EUR", "25 000\n/mois"],
        ["Continental B", "LOTO_FR_B\n+ 6 \u00d7 EM_*_B", "9 pays\n(Standard)", "1 493 EUR", "-20%", "1 189 EUR", "25 000\n/mois"],
    ]
    col_w_reg = [24 * mm, 26 * mm, 22 * mm, 22 * mm, 18 * mm, 22 * mm, 22 * mm]
    t = Table(data_reg, colWidths=col_w_reg)
    ts = _base_table_style(n_rows=6)
    ts.append(("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"))
    ts.append(("FONTNAME", (5, 1), (5, -1), "DejaVuSans-Bold"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Le Pack DACH, bien qu\u2019adressant une r\u00e9gion multi-pays (AT, CH), ne mobilise qu\u2019un seul code produit "
        "(EM_DE_A) et rel\u00e8ve donc du palier Mono-March\u00e9 (10 000 impressions).",
        S["body_italic"],
    ))
    elements.append(Spacer(1, 6 * mm))

    # Pool Global
    elements.extend(pool_global_section(S))

    # ── Clause de revision ──
    elements.append(_p("5. Clause de r\u00e9vision tarifaire", S["h2"]))
    elements.append(_p(CLAUSE_V8_TEXT, S["body"]))
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p("Au-del\u00e0, facturation au choix :", S["body"]))
    elements.append(Spacer(1, 3 * mm))

    data_cpc = [
        ["", "CPC (Co\u00fbt par clic)", "CPM (Co\u00fbt par mille)"],
        ["Tarif", "0,45 EUR / clic", "15 EUR / 1 000 impressions"],
        ["Id\u00e9al pour", "Performance (leads)", "Notori\u00e9t\u00e9 (branding)"],
        ["Exemple +10K", "200 clics (2% CTR) = 90 EUR", "10 000 impr. = 150 EUR"],
    ]
    t = Table(data_cpc, colWidths=[38 * mm, 62 * mm, 62 * mm])
    ts = _base_table_style(n_rows=3)
    ts.append(("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"))
    ts.append(("FONTNAME", (1, 1), (-1, 1), "DejaVuSans-Bold"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Comparatif march\u00e9 : Google Ads ~2,50-15 EUR/clic selon pays | Facebook ~0,80-1,50 EUR/clic | "
        "LotoIA : 3x \u00e0 30x moins cher selon le march\u00e9.",
        S["body_italic"],
    ))
    elements.append(Spacer(1, 2 * mm))
    bullets_clause = [
        "<b>Choix modifiable</b> : le mode CPC ou CPM est r\u00e9visable chaque trimestre",
        "<b>Plafond optionnel</b> : le partenaire peut fixer un montant max (ex : 200 EUR)",
        "<b>Formule hybride</b> : CPC sur chatbot (E4) + CPM sur banni\u00e8res (E1, E5)",
        "<b>Suivi conversions</b> : actions post-clic via GA4 events personnalis\u00e9s",
    ]
    for b in bullets_clause:
        elements.append(_p(f"\u2022 {b}", S["bullet"]))

    # ── Page 5 : Garanties + Conformite + Mesure ──
    elements.append(PageBreak())
    elements.append(_p("6. Garanties et paliers d\u2019audience", S["h2"]))
    elements.append(_p("Garantie de volume", S["h3"]))
    elements.append(_p(
        "Si LotoIA n\u2019atteint pas <b>5 000 impressions</b> sur un mois donn\u00e9, les impressions manquantes sont "
        "report\u00e9es sur le mois suivant (cr\u00e9dit cumul\u00e9 sur 3 mois maximum).",
        S["body"],
    ))
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Si LotoIA n\u2019atteint pas <b>2 000 impressions</b> sur 2 mois cons\u00e9cutifs, le partenaire peut r\u00e9silier "
        "sans frais avec un pr\u00e9avis de 15 jours.",
        S["body"],
    ))
    elements.append(Spacer(1, 4 * mm))

    elements.append(_p("Paliers d\u2019audience et r\u00e9vision tarifaire", S["h3"]))

    # Tier 1 paliers
    elements.append(_p("Tier 1 (EN / DE) :", S["body"]))
    elements.append(Spacer(1, 2 * mm))
    data_pal1 = [
        ["Palier", "Impressions / mois", "EM_xx_B", "EM_xx_A", "Hausse max"],
        ["Lancement", "0 - 10 000", "249 EUR (gel)", "549 EUR (gel)", "\u2014"],
        ["Croissance", "10 001 - 30 000", "309 EUR", "679 EUR", "+25% max"],
        ["Traction", "30 001 - 100 000", "389 EUR", "849 EUR", "+25% max"],
        ["Scale", "100 001+", "Sur mesure", "Sur mesure", "N\u00e9goci\u00e9"],
    ]
    col_w_pal = [28 * mm, 35 * mm, 28 * mm, 28 * mm, 25 * mm]
    t = Table(data_pal1, colWidths=col_w_pal)
    ts = _base_table_style(n_rows=4)
    ts.append(("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"))
    ts.append(("FONTNAME", (2, 1), (3, 1), "DejaVuSans-Bold"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 4 * mm))

    # Tier 2 paliers
    elements.append(_p("Tier 2 (FR / NL / ES / PT) :", S["body"]))
    elements.append(Spacer(1, 2 * mm))
    data_pal2 = [
        ["Palier", "Impressions / mois", "EM_xx_B", "EM_xx_A", "Hausse max"],
        ["Lancement", "0 - 10 000", "199 EUR (gel)", "449 EUR (gel)", "\u2014"],
        ["Croissance", "10 001 - 30 000", "249 EUR", "549 EUR", "+25% max"],
        ["Traction", "30 001 - 100 000", "349 EUR", "749 EUR", "+25% max"],
        ["Scale", "100 001+", "Sur mesure", "Sur mesure", "N\u00e9goci\u00e9"],
    ]
    t = Table(data_pal2, colWidths=col_w_pal)
    ts = _base_table_style(n_rows=4)
    ts.append(("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"))
    ts.append(("FONTNAME", (2, 1), (3, 1), "DejaVuSans-Bold"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "La clause de hausse maximum (+25%) garantit que le tarif ne peut pas plus que doubler sur 24 mois.",
        S["body_italic"],
    ))
    elements.append(Spacer(1, 6 * mm))

    # Conformite
    elements.append(_p("7. Conformit\u00e9 r\u00e9glementaire", S["h2"]))
    bullets_conf = [
        "<b>Limitation d\u2019exposition</b> : max 3 communications commerciales par jour par support (ANJ)",
        "<b>Chatbot</b> : rotation A/B, 1 message sponsor toutes les 3 r\u00e9ponses",
        "<b>Protection des joueurs</b> : aucune incitation \u00e0 jouer davantage",
        "<b>RGPD</b> : aucune donn\u00e9e personnelle partag\u00e9e. Rapports GA4 anonymis\u00e9s",
        "<b>Clause d\u2019adaptation</b> : en cas d\u2019\u00e9volution r\u00e9glementaire, adaptation sans frais",
        "<b>Taxe 15%</b> : ne s\u2019applique pas aux annonceurs non-op\u00e9rateurs de jeux",
    ]
    for b in bullets_conf:
        elements.append(_p(f"\u2022 {b}", S["bullet"]))
    elements.append(Spacer(1, 6 * mm))

    # Mesure de performance
    elements.append(_p("8. Mesure de performance", S["h2"]))
    data_perf = [
        ["Indicateur", "Description", "Pack"],
        ["Impressions", "Affichages par emplacement (avec sponsor_id)", "Tous"],
        ["Clics", "Clics sur banni\u00e8re / message sponsor", "Tous"],
        ["CTR", "Taux de clics (clics / impressions)", "Tous"],
        ["Conversions", "Actions post-clic via GA4 events", "Tous"],
        ["PDF downloads", "Rapports PDF avec mention sponsor", "EM_xx_A"],
        ["Vid\u00e9o completion", "Taux de visionnage vid\u00e9o 30s", "EM_xx_A"],
    ]
    col_w_perf = [32 * mm, 100 * mm, 28 * mm]
    t = Table(data_perf, colWidths=col_w_perf)
    ts = _base_table_style(n_rows=6)
    ts.append(("FONTNAME", (0, 1), (0, -1), "DejaVuSans-Bold"))
    ts.append(("ALIGN", (0, 1), (0, -1), "LEFT"))
    ts.append(("ALIGN", (1, 1), (1, -1), "LEFT"))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(_p(
        "Chaque impression est track\u00e9e avec le code produit (EM_FR_A, EM_EN_B, etc.) pour une facturation pr\u00e9cise.",
        S["body_italic"],
    ))

    # ── Page 6 : Pourquoi + Contact + Sources ──
    elements.append(PageBreak())
    elements.append(_p("9. Pourquoi devenir partenaire pionnier", S["h2"]))
    bullets_why = [
        "<b>Tarif de lancement gel\u00e9 6 mois</b> \u2014 vous entrez au prix le plus bas",
        "<b>Exclusivit\u00e9 (2 sponsors max par langue)</b> \u2014 pas de r\u00e9gie publicitaire",
        "<b>Oc\u00e9an bleu</b> \u2014 z\u00e9ro concurrent chatbot IA EuroMillions en Europe",
        "<b>9 pays en 6 langues</b> \u2014 potentiel d\u2019audience x15 vs Loto FR seul (76M joueurs/semaine)",
        "<b>Effet Super-Cagnotte</b> \u2014 pics de trafic massifs et gratuits lors des jackpots 100M\u20ac+",
        "<b>Garantie de volume</b> \u2014 report d\u2019impressions ou r\u00e9siliation sans frais",
        "<b>Transparence totale</b> \u2014 GA4 en lecture seule, tracking par code produit",
        "<b>Clause +25% max</b> \u2014 protection contre les hausses brutales de tarif",
        "<b>Codes produit clairs</b> \u2014 EM_FR_A visible sur le site = ce que vous achetez",
        "<b>Infrastructure scalable</b> \u2014 co\u00fbt marginal quasi nul, marge croissante avec le volume",
    ]
    for b in bullets_why:
        elements.append(_p(f"\u2022 {b}", S["bullet"]))
    elements.append(Spacer(1, 8 * mm))

    # Contact
    elements.extend(contact_section(S))
    elements.append(Spacer(1, 8 * mm))

    # Sources
    elements.extend(sources_section_em(S))

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    print(f"[OK] {output_path}")


# ========================================================================
if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__), "..", "docs", "PDF Sponsors")
    os.makedirs(out_dir, exist_ok=True)

    loto_path = os.path.join(out_dir, "grille_tarifaire_lotoia_V8.pdf")
    em_path = os.path.join(out_dir, "grille_tarifaire_em_europe_V8.pdf")

    generate_loto_pdf(loto_path)
    generate_em_pdf(em_path)
    print("\nDone. Both V8 PDFs generated.")
