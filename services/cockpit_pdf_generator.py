"""
Cockpit PDF Generator — export diffusion-grade d'un run OOS V_X.F.
=================================================================
Génère un PDF A4 (ReportLab Platypus) à partir du view-model normalisé produit
par services/cockpit_parser.py::normalize_run. Destiné à l'archivage owner ET à
la diffusion externe (ANJ / sponsor / audit) : en-tête propre, framing neutre,
disclaimer ANJ TOUJOURS présent, limitations du run affichées honnêtement.

GARDE-FOU ABSOLU — MUR ÉTANCHE tools/ <-> runtime :
    Ce module ne consomme QUE le view-model (dict). Il n'importe JAMAIS
    tools.backtest_hybride, tools.signature_features ni aucun tools.*. Couvert
    automatiquement par tests/test_cockpit_wall.py (scan AST de services/**).

STATELESS / READ-ONLY :
    L'histogramme de stratification est rendu en io.BytesIO (matplotlib Agg) —
    AUCUN fichier temporaire disque (contrairement à la brique publique
    generate_meta_graph_image). Le PDF est assemblé en RAM et renvoyé en BytesIO.

ANJ / framing neutre :
    Vocabulaire strict : « signature statistique », « divergence de forme »,
    « qualité de construction ». JAMAIS « performance / prédiction / gain /
    avantage » hors du disclaimer (qui les emploie en négation, cadre légal).
    FR-only (outil owner) — n'utilise PAS PDF_LABELS (i18n public).
"""

import io
import os
import logging
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image, PageBreak,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xml.sax.saxutils import escape as _xml_escape

logger = logging.getLogger(__name__)


# ── Polices UTF-8 (pattern admin_pdf.py, idempotent) ─────────────────────────

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
            logger.error("[COCKPIT-PDF] Aucune police trouvée pour %s", _name)


_register_fonts()


# ── Constantes / framing neutre ──────────────────────────────────────────────

# Disclaimer ANJ de repli — AFFICHÉ EN PIED DE TOUT PDF (toujours, même run
# sans secondaire). Verbatim validé Jyppy 08/06/2026.
_ANJ_FALLBACK = (
    "LotoIA est un outil d'analyse statistique. Les indicateurs de ce rapport mesurent la qualité "
    "de construction et la signature statistique des grilles générées par le moteur HYBRIDE. Ils ne "
    "constituent en aucun cas une prédiction, une probabilité de gain, ni un avantage sur le tirage. "
    "Le hasard d'un tirage de loterie est irréductible."
)

# effect_tier → libellé neutre (significativité FDR vs importance pratique JSD).
_EFFECT_TIER_FR = {
    "materiel_fort": "divergence de forme marquée",
    "materiel_negligeable": "négligeable",
    "bruit": "indistinct du hasard",
}

_FAMILY_FR = {"primary": "forme", "secondary": "secondaire", "stratification": "stratification"}

# Ordre canonique des zones de stratification (NE PAS se fier à l'ordre des dicts).
_ZONES = ["1_per_zone", "2_in_one_zone", "3_in_one_zone", "libre"]
_ZONE_LABELS_FR = ["1 par zone", "2 dans une zone", "3 dans une zone", "libre"]


# ── Couleurs & styles ────────────────────────────────────────────────────────

_NAVY = HexColor("#1a2744")
_BLUE = HexColor("#2563eb")
_GREY = HexColor("#64748b")
_DARK = HexColor("#0f172a")
_HEAD_BG = HexColor("#eef2ff")
_ROW_ALT = HexColor("#f8fafc")
_LINE = HexColor("#e2e8f0")

_TITLE = ParagraphStyle('CkTitle', fontName='DejaVuSans-Bold', fontSize=17, textColor=_NAVY, leading=21)
_SUBTITLE = ParagraphStyle('CkSubtitle', fontName='DejaVuSans', fontSize=9.5, textColor=_GREY, leading=13)
_SECTION = ParagraphStyle('CkSection', fontName='DejaVuSans-Bold', fontSize=12, textColor=_BLUE,
                          spaceBefore=5 * mm, spaceAfter=2.5 * mm, leading=15)
_NORMAL = ParagraphStyle('CkNormal', fontName='DejaVuSans', fontSize=9, textColor=_DARK, leading=13)
_SMALL = ParagraphStyle('CkSmall', fontName='DejaVuSans', fontSize=8, textColor=_GREY, leading=12)
_DISC = ParagraphStyle('CkDisclaimer', fontName='DejaVuSans', fontSize=8, textColor=_GREY,
                       leading=12, spaceBefore=1.5 * mm)

# Styles de cellule de table : Paragraph wrappable (police 8, calque _data_table_style).
# Les strings brutes ne se wrappent pas dans ReportLab → un libellé long (« divergence
# de forme marquée ») déborde sur la colonne voisine. Wrapper en Paragraph corrige.
_CELL = ParagraphStyle('CkCell', fontName='DejaVuSans', fontSize=8, textColor=_DARK, leading=10)
_CELL_R = ParagraphStyle('CkCellR', parent=_CELL, alignment=TA_RIGHT)
_CELL_H = ParagraphStyle('CkCellH', fontName='DejaVuSans-Bold', fontSize=8, textColor=_NAVY, leading=10)
_CELL_HR = ParagraphStyle('CkCellHR', parent=_CELL_H, alignment=TA_RIGHT)


def _wrap_data_rows(rows) -> list:
    """Convertit les cellules string d'une table de données en Paragraph wrappables.

    Calque l'alignement de _data_table_style : colonne 0 à gauche, colonnes
    suivantes à droite ; ligne 0 = en-tête (gras navy). Permet le retour à la
    ligne dans la largeur de colonne (anti-débordement horizontal)."""
    out = []
    for ri, row in enumerate(rows):
        wrapped = []
        for ci, cell in enumerate(row):
            if ri == 0:
                style = _CELL_H if ci == 0 else _CELL_HR
            else:
                style = _CELL if ci == 0 else _CELL_R
            wrapped.append(Paragraph(_x(cell), style))
        out.append(wrapped)
    return out


def _data_table_style() -> TableStyle:
    """Table de données : 1ʳᵉ ligne = en-tête, lignes alternées."""
    return TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TEXTCOLOR', (0, 0), (-1, 0), _NAVY),
        ('BACKGROUND', (0, 0), (-1, 0), _HEAD_BG),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, _GREY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#ffffff'), _ROW_ALT]),
        ('LINEBELOW', (0, 1), (-1, -1), 0.25, _LINE),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ])


def _kv_table_style() -> TableStyle:
    """Table clé/valeur 4 colonnes (labels gras gris en colonnes 0 et 2)."""
    return TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
        ('FONTNAME', (0, 0), (0, -1), 'DejaVuSans-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'DejaVuSans-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 0), (0, -1), _GREY),
        ('TEXTCOLOR', (2, 0), (2, -1), _GREY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ])


# Largeurs de colonnes (zone utile A4 = 210 - 2×18 = 174 mm).
_KV_COLW = [34 * mm, 53 * mm, 34 * mm, 53 * mm]
_SIG_COLW = [34 * mm, 24 * mm, 20 * mm, 32 * mm, 22 * mm, 22 * mm, 20 * mm]
_CONF_COLW = [32 * mm, 24 * mm, 24 * mm, 24 * mm, 20 * mm, 20 * mm, 30 * mm]
_SEC_COLW = [62 * mm, 30 * mm, 50 * mm, 32 * mm]


# ── Formatters défensifs ─────────────────────────────────────────────────────

def _fmt(value, nd: int = 4) -> str:
    """Numérique → str à nd décimales. None / bool / non-numérique → « — »."""
    if isinstance(value, bool):
        return "—"
    if isinstance(value, (int, float)):
        return ("%." + str(nd) + "f") % value
    return "—" if value is None else str(value)


def _fmt_p(value) -> str:
    """p-value / plancher : notation scientifique sous 0.001, sinon 4 décimales."""
    if isinstance(value, bool) or value is None:
        return "—"
    if isinstance(value, (int, float)):
        return ("%.2e" % value) if 0 < value < 0.001 else ("%.4f" % value)
    return str(value)


def _cell(value) -> str:
    return "—" if value is None else str(value)


def _bool_fr(value) -> str:
    if value is True:
        return "Oui"
    if value is False:
        return "Non"
    return "—"


def _effect_fr(tier) -> str:
    if not tier:
        return "—"
    return _EFFECT_TIER_FR.get(tier, str(tier))


# ── Histogramme stratification (matplotlib Agg → io.BytesIO) ──────────────────

def _render_stratification_histogram(strat: dict) -> io.BytesIO:
    """Bar chart groupé 3 séries (HYBRIDE / hasard / réel) sur les 4 zones, en %.

    Rendu en io.BytesIO (PNG), AUCUN fichier disque. Ordre des zones figé via
    _ZONES, lecture défensive .get(zone, 0.0) sur chaque série.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    def _series(distrib):
        d = distrib or {}
        return [float(d.get(z, 0.0) or 0.0) * 100.0 for z in _ZONES]

    s_hyb = _series(strat.get("hybride"))
    s_base = _series(strat.get("baseline"))
    s_real = _series(strat.get("real"))

    x = list(range(len(_ZONES)))
    width = 0.26
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar([i - width for i in x], s_hyb, width, label="HYBRIDE", color="#22c55e")
    ax.bar(x, s_base, width, label="hasard", color="#94a3b8")
    ax.bar([i + width for i in x], s_real, width, label="tirages réels", color="#38bdf8")

    ax.set_xticks(x)
    ax.set_xticklabels(_ZONE_LABELS_FR, fontsize=9)
    ax.set_ylabel("% des grilles", fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_title("Répartition par zone de stratification", fontsize=12, fontweight='bold')
    ax.legend(fontsize=9)
    ax.grid(axis='y', alpha=0.15)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


# ── Plan du document (pure, sans I/O ni matplotlib) ───────────────────────────

def _build_blocks(view_model: dict) -> list:
    """Plan du PDF sous forme de blocs typés (source unique de vérité).

    Chaque bloc est un tuple : ('title'|'subtitle'|'section'|'para'|'small'|
    'disclaimer', texte) · ('kvtable'|'table', rows[, colwidths]) ·
    ('strat_image', strat_dict) · ('hr',) · ('spacer', hauteur).

    Pure : ne rend PAS l'histogramme (différé au flowable via 'strat_image'),
    n'écrit rien. Chaque étage est gardé par son flag `present` (run partiel →
    section sautée, jamais de crash). Les disclaimers (kind 'disclaimer') sont
    le seul endroit où les mots « prédiction/gain/avantage » apparaissent.
    """
    vm = view_model or {}
    meta = vm.get("meta") or {}
    blocks = [
        ("title", "LotoIA — Rapport de signature statistique"),
        ("subtitle", "Run OOS (out-of-sample) du moteur HYBRIDE — mesure neutre de la qualité "
                     "de construction et de la divergence de forme des grilles générées."),
        ("spacer", 3 * mm),
        ("hr",),
        ("spacer", 3 * mm),
    ]

    # — Paramètres du run —
    rng = meta.get("tirages_range") or {}
    pairs = [
        ("Jeu", _cell(meta.get("game"))),
        ("Tirages rejoués", _cell(meta.get("n_tirages"))),
        ("Grilles / tirage", _cell(meta.get("n_grilles_per_tirage"))),
        ("Mode", _cell(meta.get("mode"))),
        ("Run mode", _cell(meta.get("run_mode"))),
        ("Harness", _cell(meta.get("harness_version"))),
        ("Plage tirages", "%s → %s" % (rng.get("first") or "?", rng.get("last") or "?")),
        ("Durée (s)", _fmt(meta.get("elapsed_seconds"), 1)),
    ]
    kv_rows = []
    for i in range(0, len(pairs), 2):
        left = pairs[i]
        right = pairs[i + 1] if i + 1 < len(pairs) else ("", "")
        kv_rows.append([left[0], left[1], right[0], right[1]])
    blocks.append(("section", "Paramètres du run"))
    blocks.append(("kvtable", kv_rows, _KV_COLW))

    # — Étage 1 : Signature —
    sig = vm.get("signature") or {}
    if sig.get("present"):
        rows = [["Feature", "Famille", "JSD", "Effet (taille)", "p-value", "Plancher", "Matériel"]]
        for r in sig.get("rows") or []:
            rows.append([
                _cell(r.get("feature")),
                _FAMILY_FR.get(r.get("family"), _cell(r.get("family"))),
                _fmt(r.get("jsd"), 4),
                _effect_fr(r.get("effect_tier")),
                _fmt_p(r.get("p_value")),
                _fmt_p(r.get("noise_floor")),
                _bool_fr(r.get("is_material")),
            ])
        blocks.append(("section", "Étage 1 — Signature statistique"))
        blocks.append(("table", rows, _SIG_COLW))

    # — Étage 2 : Conformité Tier 1 —
    conf = vm.get("conformity") or {}
    if conf.get("present"):
        rows = [["Feature", "Moyenne", "Médiane", "Écart-type", "Min", "Max", "% hors bornes"]]
        for r in conf.get("rows") or []:
            pct = r.get("pct_out_of_bounds")
            rows.append([
                _cell(r.get("feature")),
                _fmt(r.get("mean"), 3),
                _fmt(r.get("median"), 3),
                _fmt(r.get("std"), 3),
                _fmt(r.get("min"), 2),
                _fmt(r.get("max"), 2),
                "—" if pct is None else (_fmt(pct, 3) + " %"),
            ])
        blocks.append(("section", "Étage 2 — Conformité (Tier 1)"))
        blocks.append(("table", rows, _CONF_COLW))

    # — Étage 4a : Stratification —
    strat = vm.get("stratification") or {}
    if strat.get("present"):
        # Étage 4a sur une page fraîche : l'histogramme 75 mm a toute la place,
        # zéro chevauchement avec 4b. Conditionnel au flag present → pas de page
        # blanche sur un vieux run partiel sans stratification.
        blocks.append(("pagebreak",))
        blocks.append(("section", "Étage 4a — Stratification (divergence de forme)"))
        blocks.append(("para", "Divergence de forme (JSD) : %s" % _fmt(strat.get("jsd"), 4)))
        blocks.append(("strat_image", strat))

    # — Étage 4b : Secondaire —
    sec = vm.get("secondary") or {}
    if sec.get("present"):
        rows = [["Feature", "JSD", "Effet (taille)", "Matériel"]]
        for r in sec.get("rows") or []:
            rows.append([
                _cell(r.get("feature")),
                _fmt(r.get("jsd"), 4),
                _effect_fr(r.get("effect_tier")),
                _bool_fr(r.get("is_material")),
            ])
        blocks.append(("section", "Étage 4b — Indicateurs secondaires"))
        blocks.append(("table", rows, _SEC_COLW))
        disc = sec.get("anj_disclaimer")
        if disc:
            blocks.append(("small", "Avertissement (indicateur secondaire) :"))
            blocks.append(("disclaimer", disc))

    # — Limitations du run (honnêteté) —
    lims = meta.get("limitations_mvp") or []
    if lims:
        blocks.append(("section", "Limitations du run"))
        for x in lims:
            blocks.append(("small", "• %s" % x))

    # — Disclaimer ANJ de repli : TOUJOURS présent —
    blocks.append(("spacer", 4 * mm))
    blocks.append(("hr",))
    blocks.append(("section", "Avertissement (cadre ANJ)"))
    blocks.append(("disclaimer", _ANJ_FALLBACK))
    return blocks


def _blocks_text(blocks) -> list:
    """Extrait tous les textes du plan (titres, paragraphes, cellules de tables).

    Image/hr/spacer ignorés. Sert à tester contenu (disclaimer présent) et
    framing neutre (en filtrant les blocs 'disclaimer')."""
    out = []
    for b in blocks:
        kind = b[0]
        if kind in ("title", "subtitle", "section", "para", "small", "disclaimer"):
            out.append((kind, b[1]))
        elif kind in ("kvtable", "table"):
            for row in b[1]:
                for cell in row:
                    out.append((kind, str(cell)))
    return out


# ── Rendu Platypus ───────────────────────────────────────────────────────────

def _x(s) -> str:
    """Échappe le texte destiné à un Paragraph (mini-XML ReportLab)."""
    return _xml_escape("" if s is None else str(s))


def _blocks_to_flowables(blocks) -> list:
    flow = []
    for b in blocks:
        kind = b[0]
        if kind == "title":
            flow.append(Paragraph(_x(b[1]), _TITLE))
        elif kind == "subtitle":
            flow.append(Paragraph(_x(b[1]), _SUBTITLE))
        elif kind == "section":
            flow.append(Paragraph(_x(b[1]), _SECTION))
        elif kind == "para":
            flow.append(Paragraph(_x(b[1]), _NORMAL))
        elif kind == "small":
            flow.append(Paragraph(_x(b[1]), _SMALL))
        elif kind == "disclaimer":
            flow.append(Paragraph(_x(b[1]), _DISC))
        elif kind == "hr":
            flow.append(HRFlowable(width="100%", thickness=0.6, color=_GREY))
        elif kind == "spacer":
            flow.append(Spacer(1, b[1]))
        elif kind == "pagebreak":
            flow.append(PageBreak())
        elif kind == "kvtable":
            t = Table(b[1], colWidths=b[2])
            t.setStyle(_kv_table_style())
            flow.append(t)
        elif kind == "table":
            t = Table(_wrap_data_rows(b[1]), colWidths=b[2], repeatRows=1)
            t.setStyle(_data_table_style())
            flow.append(t)
        elif kind == "strat_image":
            try:
                img_buf = _render_stratification_histogram(b[1])
                flow.append(Image(img_buf, width=150 * mm, height=75 * mm))
            except Exception as e:  # pragma: no cover - défensif (matplotlib runtime)
                logger.warning("[COCKPIT-PDF] histogramme stratification indisponible: %s", e)
                flow.append(Paragraph("Histogramme indisponible.", _SMALL))
    return flow


def _footer(canvas_obj, doc_obj):
    """Pied de page : mention neutre + n° de page + date."""
    canvas_obj.saveState()
    canvas_obj.setFont("DejaVuSans", 7)
    canvas_obj.setFillColor(_GREY)
    canvas_obj.drawString(18 * mm, 12 * mm,
                          "LotoIA — Rapport généré automatiquement · usage analytique neutre")
    canvas_obj.drawRightString(A4[0] - 18 * mm, 12 * mm,
                               "%s · p. %d" % (date.today().isoformat(), doc_obj.page))
    canvas_obj.restoreState()


def generate_cockpit_pdf(view_model: dict) -> io.BytesIO:
    """Génère le PDF d'un run OOS V_X.F depuis le view-model normalisé.

    Retourne un io.BytesIO positionné en tête. Défensif aux étages absents
    (flags `present`). Aucune écriture disque/DB.
    """
    blocks = _build_blocks(view_model)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=22 * mm,
        title="Rapport de signature statistique — Run OOS HYBRIDE",
        author="LotoIA",
    )
    doc.build(_blocks_to_flowables(blocks), onFirstPage=_footer, onLaterPages=_footer)
    buf.seek(0)
    return buf
