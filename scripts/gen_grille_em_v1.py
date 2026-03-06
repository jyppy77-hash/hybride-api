"""
Generate grille_tarifaire_em_ue_v1.pdf — EuroMillions Europe pricing grid.
Usage: py -3 scripts/gen_grille_em_v1.py
"""
import os, sys

def main():
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab as _rl

    # Register fonts
    _rl_fonts = os.path.join(os.path.dirname(_rl.__file__), 'fonts')
    for name, files in {
        'DV': ['DejaVuSans.ttf', 'Vera.ttf'],
        'DVB': ['DejaVuSans-Bold.ttf', 'VeraBd.ttf'],
        'DVI': ['DejaVuSans-Oblique.ttf', 'VeraIt.ttf'],
    }.items():
        for f in files:
            for p in [os.path.join(_rl_fonts, f), f'/usr/share/fonts/truetype/dejavu/{f}']:
                if os.path.isfile(p):
                    try:
                        pdfmetrics.registerFont(TTFont(name, p))
                    except Exception:
                        continue
                    break

    out_path = os.path.join(os.path.dirname(__file__), '..', 'docs', 'PDF Sponsors', 'grille_tarifaire_em_ue_v1.pdf')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    w, h = A4
    c = canvas.Canvas(out_path, pagesize=A4)

    BLUE = HexColor('#2C5F8A')
    DARK = HexColor('#1a1a1a')
    GRAY = HexColor('#666666')
    LIGHT_BG = HexColor('#F5F7FA')
    WHITE = HexColor('#FFFFFF')
    GOLD = HexColor('#D4A843')

    def draw_header_line(y_pos):
        c.setStrokeColor(BLUE)
        c.setLineWidth(2)
        c.line(w/2 - 60, y_pos, w/2 + 60, y_pos)

    def draw_table(x, y_start, headers, rows, col_widths, header_color=BLUE):
        """Draw a simple table. Returns y position after table."""
        row_h = 22
        header_h = 26
        total_w = sum(col_widths)

        # Header
        c.setFillColor(header_color)
        c.rect(x, y_start - header_h, total_w, header_h, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont('DVB', 9)
        cx = x
        for i, hdr in enumerate(headers):
            c.drawCentredString(cx + col_widths[i]/2, y_start - header_h + 8, hdr)
            cx += col_widths[i]

        y = y_start - header_h
        for ri, row in enumerate(rows):
            bg = LIGHT_BG if ri % 2 == 0 else WHITE
            c.setFillColor(bg)
            c.rect(x, y - row_h, total_w, row_h, fill=1, stroke=0)
            c.setFillColor(DARK)
            c.setFont('DV', 8.5)
            cx = x
            for i, cell in enumerate(row):
                c.drawCentredString(cx + col_widths[i]/2, y - row_h + 7, str(cell))
                cx += col_widths[i]
            y -= row_h

        # Border
        c.setStrokeColor(HexColor('#CCCCCC'))
        c.setLineWidth(0.5)
        c.rect(x, y, total_w, y_start - y, stroke=1, fill=0)
        return y

    # ═══════════════════════════════════════════
    # PAGE 1 — Couverture + Contexte
    # ═══════════════════════════════════════════
    y = h - 50

    c.setFillColor(BLUE)
    c.setFont('DVB', 26)
    c.drawCentredString(w/2, y, "Offre Sponsoring LotoIA 2026")
    y -= 14

    c.setFont('DV', 13)
    c.setFillColor(DARK)
    c.drawCentredString(w/2, y, "EuroMillions Europe")
    y -= 12

    c.setFont('DV', 11)
    c.setFillColor(GRAY)
    c.drawCentredString(w/2, y, "Grille tarifaire V1 -- 12 codes produit x 6 langues x 9 pays")
    y -= 18

    draw_header_line(y)
    y -= 14

    c.setFont('DVI', 10)
    c.setFillColor(GRAY)
    c.drawCentredString(w/2, y, "Document confidentiel -- Prospection partenaires pionniers")
    y -= 12
    c.drawCentredString(w/2, y, "Mis a jour le 6 mars 2026")
    y -= 30

    # Contexte box
    c.setStrokeColor(HexColor('#DDDDDD'))
    c.setLineWidth(0.5)
    box_y = y - 120
    c.rect(15*mm, box_y, w - 30*mm, 120, stroke=1, fill=0)

    c.setFillColor(DARK)
    c.setFont('DVB', 12)
    c.drawString(20*mm, y - 12, "Contexte")
    y -= 28

    c.setFont('DV', 10)
    lines = [
        "L'EuroMillions est le plus grand jeu de loterie europeen, joue dans 9 pays : France, Royaume-Uni,",
        "Irlande, Espagne, Portugal, Autriche, Suisse, Belgique et Luxembourg.",
        "",
        "LotoIA lance le 15 mars 2026 son module EuroMillions multilingue avec chatbot HYBRIDE",
        "en 6 langues (FR, EN, ES, PT, DE, NL), couvrant les 9 pays participants.",
        "",
        "Base technique : 733+ tirages EM | 42 pages multilingues | 1200+ tests automatises",
        "Architecture 100% Python/Cloud Run | Chatbot IA Grounded connecte aux donnees officielles."
    ]
    for line in lines:
        c.drawString(20*mm, y - 12, line)
        y -= 13
    y -= 20

    # Chiffres cles
    c.setFont('DVB', 14)
    c.setFillColor(BLUE)
    c.drawString(15*mm, y, "Chiffres cles")
    y -= 8

    headers = ["Audience cible", "Concurrence", "Sponsors par langue", "Langues"]
    rows = [["~76M joueurs EM/semaine", "0 chatbot IA EM", "2 max (exclusivite)", "6 (FR EN ES PT DE NL)"]]
    y = draw_table(15*mm, y, headers, rows, [140, 120, 140, 140])
    y -= 20

    c.setFont('DVI', 8.5)
    c.setFillColor(GRAY)
    c.drawString(15*mm, y, "Source : FDJ / EuroMillions.com -- environ 76 millions de joueurs par semaine en Europe.")

    c.showPage()

    # ═══════════════════════════════════════════
    # PAGE 2 — Nomenclature 12 codes produit
    # ═══════════════════════════════════════════
    y = h - 40

    c.setFont('DVB', 16)
    c.setFillColor(BLUE)
    c.drawString(15*mm, y, "1. Nomenclature des 12 codes produit EM")
    y -= 20

    c.setFont('DV', 10)
    c.setFillColor(DARK)
    c.drawString(15*mm, y, "Chaque emplacement sponsor est identifie par un code produit unique.")
    y -= 18

    headers = ["Code A (Premium)", "Code B (Standard)", "Langue", "Pays couverts", "Tarif A", "Tarif B"]
    rows = [
        ["EM_FR_A", "EM_FR_B", "Francais", "FR, BE(FR), LU, CH(FR)", "349 EUR", "149 EUR"],
        ["EM_EN_A", "EM_EN_B", "English", "UK, Ireland", "349 EUR", "149 EUR"],
        ["EM_ES_A", "EM_ES_B", "Espanol", "Espana", "349 EUR", "149 EUR"],
        ["EM_PT_A", "EM_PT_B", "Portugues", "Portugal", "349 EUR", "149 EUR"],
        ["EM_DE_A", "EM_DE_B", "Deutsch", "AT, CH(DE)", "349 EUR", "149 EUR"],
        ["EM_NL_A", "EM_NL_B", "Nederlands", "NL, BE(NL)", "349 EUR", "149 EUR"],
    ]
    y = draw_table(15*mm, y, headers, rows, [90, 90, 75, 120, 65, 65])
    y -= 15

    c.setFont('DVI', 9)
    c.setFillColor(GRAY)
    c.drawString(15*mm, y, "Total : 12 codes produit EM + 2 Loto FR = 14 codes. Chaque code = 1 contrat = 1 facturation = 1 tracking.")
    y -= 30

    # Emplacements
    c.setFont('DVB', 16)
    c.setFillColor(BLUE)
    c.drawString(15*mm, y, "2. Emplacements publicitaires")
    y -= 20

    c.setFont('DV', 10)
    c.setFillColor(DARK)
    c.drawString(15*mm, y, "Cinq emplacements natifs, conformes ANJ (max 3 comm./jour/support).")
    y -= 18

    headers = ["#", "Emplacement", "Format", "Duree / Frequence", "Codes produit"]
    rows = [
        ["E1", "Simulateur / Generateur", "2 encarts cote a cote", "3 a 15s par generation", "EM_xx_A + EM_xx_B"],
        ["E2", "Analyse META 75", "Video 30s pre-roll", "Avant remise du PDF", "EM_xx_A uniquement"],
        ["E3", "Rapport PDF", "\"Analyse offerte par...\"", "Permanente (PDF)", "EM_xx_A uniquement"],
        ["E4", "Chatbot HYBRIDE", "Message sponsor inline", "Rotation A/B msg 3/6", "EM_xx_A + EM_xx_B"],
        ["E5", "Resultats generateur", "Banniere sous grille", "Apres chaque grille", "EM_xx_A + EM_xx_B"],
    ]
    y = draw_table(15*mm, y, headers, rows, [25, 115, 105, 115, 115])
    y -= 15

    c.setFont('DVI', 9)
    c.setFillColor(GRAY)
    c.drawString(15*mm, y, "xx = code langue (FR, EN, ES, PT, DE, NL). Repartition : Simulateur ~30% | Chatbot ~30% | Resultats ~20% | Video ~10% | PDF ~10%")

    c.showPage()

    # ═══════════════════════════════════════════
    # PAGE 3 — Packs tarifaires
    # ═══════════════════════════════════════════
    y = h - 40

    c.setFont('DVB', 16)
    c.setFillColor(BLUE)
    c.drawString(15*mm, y, "3. Packs tarifaires (par langue)")
    y -= 20

    headers = ["", "EM_xx_B (Standard)", "EM_xx_A (Premium)"]
    rows = [
        ["Tarif mensuel", "149 EUR / mois", "349 EUR / mois"],
        ["Engagement minimum", "3 mois", "6 mois"],
        ["Reduction 6 mois", "-10% (134 EUR/mois)", "--"],
        ["Reduction 12 mois", "-20% (119 EUR/mois)", "-20% (279 EUR/mois)"],
        ["Emplacements", "E1, E4, E5", "E1, E2, E3, E4, E5"],
        ["Video META 75", "Non", "Oui -- video 30s pre-roll"],
        ["Mention rapport PDF", "Non", "Oui -- \"Analyse offerte par...\""],
        ["Badge", "Partenaire officiel", "Sponsor fondateur + Partenaire"],
        ["Exclusivite sectorielle", "Non", "Oui (optionnelle)"],
        ["Rapport analytics", "Mensuel", "Hebdomadaire"],
        ["Impressions incluses", "10 000 / mois", "10 000 / mois"],
        ["Chatbot rotation", "Msg 6, 12, 18...", "Msg 3, 9, 15... (priorite)"],
    ]
    y = draw_table(15*mm, y, headers, rows, [140, 170, 170])
    y -= 25

    # Packs regionaux
    c.setFont('DVB', 16)
    c.setFillColor(BLUE)
    c.drawString(15*mm, y, "4. Packs regionaux")
    y -= 20

    c.setFont('DV', 10)
    c.setFillColor(DARK)
    c.drawString(15*mm, y, "Regroupements commerciaux pour sponsors multi-pays :")
    y -= 18

    headers = ["Pack", "Codes inclus", "Pays couverts", "Tarif"]
    rows = [
        ["Pack FR Complet", "LOTO_FR_A + EM_FR_A", "France (Loto + EM)", "Sur mesure"],
        ["Pack DACH", "EM_DE_A", "DE, AT, CH", "349 EUR"],
        ["Pack Benelux", "EM_FR_A + EM_NL_A", "BE, NL, LU", "Sur mesure"],
        ["Pack Iberique", "EM_ES_A + EM_PT_A", "ES, PT", "Sur mesure"],
        ["Pack Continental A", "LOTO_FR_A + tous EM_*_A", "9 pays (Premium)", "Sur mesure"],
        ["Pack Continental B", "LOTO_FR_B + tous EM_*_B", "9 pays (Standard)", "Sur mesure"],
    ]
    y = draw_table(15*mm, y, headers, rows, [115, 140, 120, 100])

    c.showPage()

    # ═══════════════════════════════════════════
    # PAGE 4 — Clause de revision + Garanties
    # ═══════════════════════════════════════════
    y = h - 40

    c.setFont('DVB', 16)
    c.setFillColor(BLUE)
    c.drawString(15*mm, y, "5. Clause de revision tarifaire")
    y -= 20

    c.setFont('DV', 10)
    c.setFillColor(DARK)
    c.drawString(15*mm, y, "Chaque forfait comprend 10 000 impressions/mois. Au-dela, deux modes :")
    y -= 18

    headers = ["", "CPC (Cout par clic)", "CPM (Cout par mille)"]
    rows = [
        ["Tarif", "0,30 EUR / clic", "15 EUR / 1 000 impressions"],
        ["Ideal pour", "Performance (leads)", "Notoriete (branding)"],
        ["Exemple +10K", "200 clics (2% CTR) = 60 EUR", "10 000 impr. = 150 EUR"],
    ]
    y = draw_table(15*mm, y, headers, rows, [120, 180, 180])
    y -= 15

    c.setFont('DV', 9)
    c.setFillColor(DARK)
    lines = [
        "- Choix modifiable : CPC ou CPM revisable chaque trimestre",
        "- Plafond optionnel : le partenaire peut fixer un montant max (ex : 200 EUR)",
        "- Formule hybride : CPC sur chatbot (E4) + CPM sur bannieres (E1, E5)",
    ]
    for line in lines:
        c.drawString(15*mm, y, line)
        y -= 13
    y -= 20

    # Garanties
    c.setFont('DVB', 16)
    c.setFillColor(BLUE)
    c.drawString(15*mm, y, "6. Garanties et paliers d'audience")
    y -= 20

    c.setFont('DVB', 11)
    c.setFillColor(DARK)
    c.drawString(15*mm, y, "Garantie de volume")
    y -= 14

    c.setFont('DV', 10)
    lines = [
        "Si LotoIA n'atteint pas 5 000 impressions sur un mois donne, les impressions manquantes",
        "sont reportees sur le mois suivant (credit cumule sur 3 mois maximum).",
        "",
        "Si LotoIA n'atteint pas 2 000 impressions sur 2 mois consecutifs, le partenaire peut",
        "resilier sans frais avec un preavis de 15 jours.",
    ]
    for line in lines:
        c.drawString(15*mm, y, line)
        y -= 13
    y -= 15

    c.setFont('DVB', 11)
    c.drawString(15*mm, y, "Paliers d'audience et revision tarifaire")
    y -= 18

    headers = ["Palier", "Impressions / mois", "EM_xx_B", "EM_xx_A", "Hausse max"]
    rows = [
        ["Lancement", "0 - 10 000", "149 EUR (gel)", "349 EUR (gel)", "--"],
        ["Croissance", "10 001 - 30 000", "199 EUR", "449 EUR", "+25% max"],
        ["Traction", "30 001 - 100 000", "299 EUR", "599 EUR", "+25% max"],
        ["Scale", "100 001+", "Sur mesure", "Sur mesure", "Negocie"],
    ]
    y = draw_table(15*mm, y, headers, rows, [80, 110, 90, 90, 80])
    y -= 15

    c.setFont('DVI', 8.5)
    c.setFillColor(GRAY)
    c.drawString(15*mm, y, "La clause +25% max garantit que le tarif ne peut pas plus que doubler sur 24 mois.")

    c.showPage()

    # ═══════════════════════════════════════════
    # PAGE 5 — Conformite + Performance + Contact
    # ═══════════════════════════════════════════
    y = h - 40

    c.setFont('DVB', 16)
    c.setFillColor(BLUE)
    c.drawString(15*mm, y, "7. Conformite reglementaire")
    y -= 20

    c.setFont('DV', 10)
    c.setFillColor(DARK)
    lines = [
        "- Limitation d'exposition : max 3 communications/jour/support (ANJ)",
        "- Chatbot : rotation A/B, 1 message sponsor toutes les 3 reponses",
        "- Protection des joueurs : aucune incitation a jouer davantage",
        "- RGPD : aucune donnee personnelle partagee. Rapports GA4 anonymises",
        "- Clause d'adaptation : en cas d'evolution reglementaire, adaptation sans frais",
        "- Taxe 15% : ne s'applique pas aux annonceurs non-operateurs de jeux",
    ]
    for line in lines:
        c.drawString(15*mm, y, line)
        y -= 14
    y -= 15

    c.setFont('DVB', 16)
    c.setFillColor(BLUE)
    c.drawString(15*mm, y, "8. Mesure de performance")
    y -= 18

    headers = ["Indicateur", "Description", "Pack"]
    rows = [
        ["Impressions", "Affichages par emplacement (avec sponsor_id)", "Tous"],
        ["Clics", "Clics sur banniere / message sponsor", "Tous"],
        ["CTR", "Taux de clics (clics / impressions)", "Tous"],
        ["Conversions", "Actions post-clic via GA4 events", "Tous"],
        ["PDF downloads", "Rapports PDF avec mention sponsor", "EM_xx_A"],
        ["Video completion", "Taux de visionnage video 30s", "EM_xx_A"],
    ]
    y = draw_table(15*mm, y, headers, rows, [110, 260, 80])
    y -= 15

    c.setFont('DVI', 9)
    c.setFillColor(GRAY)
    c.drawString(15*mm, y, "Chaque impression est trackee avec le code produit (EM_FR_A, EM_EN_B, etc.) pour une facturation precise.")
    y -= 30

    # Pourquoi
    c.setFont('DVB', 16)
    c.setFillColor(BLUE)
    c.drawString(15*mm, y, "9. Pourquoi devenir partenaire pionnier")
    y -= 18

    c.setFont('DV', 10)
    c.setFillColor(DARK)
    points = [
        "- Tarif de lancement gele 6 mois -- vous entrez au prix le plus bas",
        "- Exclusivite (2 sponsors max par langue) -- pas de regie publicitaire",
        "- Ocean bleu -- zero concurrent chatbot IA EuroMillions en Europe",
        "- 9 pays en 6 langues -- potentiel d'audience x5 vs Loto FR seul",
        "- Garantie de volume -- report d'impressions ou resiliation sans frais",
        "- Transparence totale -- GA4 en lecture seule, tracking par code produit",
        "- Codes produit clairs -- EM_FR_A visible sur le site = ce que vous achetez",
    ]
    for p in points:
        c.drawString(15*mm, y, p)
        y -= 14
    y -= 25

    # Contact
    c.setFillColor(BLUE)
    c.setFont('DVB', 14)
    c.drawCentredString(w/2, y, "Contact")
    y -= 18

    c.setFont('DVB', 12)
    c.setFillColor(DARK)
    c.drawCentredString(w/2, y, "Jean-Philippe Godard")
    y -= 14
    c.setFont('DV', 10)
    c.setFillColor(GRAY)
    c.drawCentredString(w/2, y, "Fondateur -- LotoIA")
    y -= 12
    c.drawCentredString(w/2, y, "partenariats@lotoia.fr")
    y -= 12
    c.drawCentredString(w/2, y, "lotoia.fr")
    y -= 16
    c.setFont('DVI', 9)
    c.drawCentredString(w/2, y, "Soutenu par Google for Startups")

    c.save()
    print(f"PDF generated: {os.path.abspath(out_path)}")

if __name__ == "__main__":
    main()
