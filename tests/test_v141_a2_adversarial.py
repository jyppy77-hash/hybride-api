"""V141 A.2 - Tests adversarial Bugs Phase T (incremental).

Couvre 2 categories du rapport V140 Phase 2.5 :
- Categorie A (ordinaux dates Phase T) - fix BUG #1 + BUG #2
- BONUS X (parser Gemini reponse) - fix BUG #5 + BUG #9

Strategie incrementale : tests ajoutes au fur et a mesure que A6.x/A9
sont implementes (pytest vert a chaque etape, filet de securite Sprint A).

Refs:
- docs/AUDIT_V140_PHASE2_5_TESTS_ADVERSARIAL.md
- docs/_v140_simulation.py
"""
from datetime import date

from services.base_chat_detect_temporal import _detect_tirage
from services.chat_pipeline_gemini import _parse_draw_date_multilang


class TestV141A_OrdinauxNumeriques:
    """V141 A.2 A6.1 - Ordinaux numeriques ligne 211 (1er/1st/1degree/etc.)."""

    def test_v141_a1_fr_1er_mai_em(self):
        """A1 - FR `1er mai 2026` doit retourner date(2026, 5, 1)."""
        result = _detect_tirage("tu peux me donner le tirage du 1er mai 2026")
        assert result == date(2026, 5, 1)

    def test_v141_a2_fr_1er_janvier_loto(self):
        """A2 - FR `1er janvier 2026` Loto."""
        result = _detect_tirage("tirage du 1er janvier 2026")
        assert result == date(2026, 1, 1)

    # NOTE: test_v141_a6_de_dot_format_regression (Ziehung vom 1. Mai 2026)
    # deplace dans TestV141A_RestrictionEN apres livraison A6.2 — le BUG #1
    # multilang ligne 227 intercepte avant que _DE_DATE_RE ligne 243 ait sa
    # chance, donc ce test ne peut passer qu'apres restriction _MOIS_NOM_EN_RE.

    def test_v141_a_regression_sans_ordinal_fr(self):
        """Regression - FR `12 mars 2026` sans ordinal continue de matcher."""
        result = _detect_tirage("tirage du 12 mars 2026")
        assert result == date(2026, 3, 12)


class TestV141A_RestrictionEN:
    """V141 A.2 A6.2 - Restriction _MOIS_NOM_EN_RE ligne 227 (fix BUG #1).

    Tests :
    - MDY EN avec et sans ordinal doivent matcher ligne 227
    - FR/DE multilang ne doit PAS matcher ligne 227 (regression BUG #1)
    - Effet collateral : DE `1. Mai 2026` ligne 243 retrouve sa chance
    """

    def test_v141_a3_en_may_1st_2026(self):
        """A3 - EN `May 1st 2026` doit matcher pattern EN ligne 227."""
        result = _detect_tirage("give me the EM draw of May 1st 2026")
        assert result == date(2026, 5, 1)

    def test_v141_a3bis_en_sans_ordinal_control(self):
        """A3bis - EN `May 1 2026` (control sans ordinal)."""
        result = _detect_tirage("give me the EM draw of May 1 2026")
        assert result == date(2026, 5, 1)

    def test_v141_a3ter_en_mdy_with_comma(self):
        """EN `January 15, 2026` MDY avec virgule (regression format US classique)."""
        result = _detect_tirage("give me the draw of January 15, 2026")
        assert result == date(2026, 1, 15)

    def test_v141_bug1_no_false_positive_fr_mai_2026(self):
        """BUG #1 critique - FR `1er mai 2026` ne doit JAMAIS retourner date(2026,5,20).

        Reproduit cas terrain Jyppy 8/05 08:55:39 : le pattern multilang
        `_MOIS_NOM_RE` ligne 227 attrapait `mai 2026` comme MDY EN et
        capturait `("mai", "20", None)` -> date(today.year, 5, 20).
        """
        result = _detect_tirage("tirage du 1er mai 2026")
        assert result != date(2026, 5, 20), (
            "BUG #1 regression : pattern EN ligne 227 a faux-matche FR `mai 2026` "
            "comme `Month D, YYYY` et capture `20` (les 2 premiers chiffres de 2026)"
        )
        # Bonus : confirme que A6.1 retourne bien la bonne date
        assert result == date(2026, 5, 1)

    def test_v141_bug1_no_false_positive_fr_mai_2026_sans_jour(self):
        """BUG #1 cas pur - FR `tirage de mai 2026` SANS jour ne doit pas
        capturer `(mai, "20", None)` -> faux-positif date(2026,5,20).

        Apres A6.2, ligne 227 ne matche plus `mai` (EN-only) -> fallthrough
        sur ligne 243 (pas de \\d.) -> autres patterns -> None ou latest.
        """
        result = _detect_tirage("tirage de mai 2026")
        assert result != date(2026, 5, 20)

    def test_v141_a6_de_dot_format_post_a62(self):
        """A6 differé d'A6.1 - DE `1. Mai 2026` regression V126.1 F1-bis.

        Apres A6.2, ligne 227 ne matche plus `mai` (EN-only), donc le code
        atteint enfin _DE_DATE_RE ligne 243 qui matche `1. Mai 2026` ->
        date(2026, 5, 1). BUG #1 latent depuis V126.1 F1-bis fixe gratuit.
        """
        result = _detect_tirage("Ziehung vom 1. Mai 2026")
        assert result == date(2026, 5, 1)


class TestV141A_OrdinauxLettres:
    """V141 A.2 A6.3 - Ordinaux mots 6 langs (premier/first/primero/etc.)."""

    def test_v141_a1bis_fr_premier_mai(self):
        """A1bis - FR `premier mai 2026` (mot ordinal lettres)."""
        result = _detect_tirage("tu peux me donner le tirage du premier mai 2026")
        assert result == date(2026, 5, 1)

    def test_v141_a3ter_en_first_of_may(self):
        """A3ter - EN `first of May 2026` via A6.3.

        NB: `first of May 2026` ne match PAS A6.1 (le `\\b(\\d{1,2})` ligne
        211 exige un vrai chiffre, le `1` de `first` est dans un mot lettres).
        Pattern A6.3 obligatoire via mots ordinaux + connecteur `of\\s+the\\s+`.
        """
        result = _detect_tirage("give me the EM draw of the first of May 2026")
        assert result == date(2026, 5, 1)

    def test_v141_a4bis_es_primero_de_mayo(self):
        """A4bis - ES `primero de mayo 2026`."""
        result = _detect_tirage("el sorteo del primero de mayo 2026")
        assert result == date(2026, 5, 1)

    def test_v141_a5bis_pt_primeiro_de_maio(self):
        """A5bis - PT `primeiro de maio 2026`."""
        result = _detect_tirage("o sorteio do primeiro de maio 2026")
        assert result == date(2026, 5, 1)

    def test_v141_a6bis_de_ersten_mai(self):
        """A6bis - DE `ersten Mai 2026` (declinaison genitive/accusative)."""
        result = _detect_tirage("Ziehung vom ersten Mai 2026")
        assert result == date(2026, 5, 1)

    def test_v141_a7bis_nl_eerste_mei(self):
        """A7bis - NL `eerste mei 2026`."""
        result = _detect_tirage("de trekking van eerste mei 2026")
        assert result == date(2026, 5, 1)


# ════════════════════════════════════════════════════════════════════
# BONUS X — Parser date Gemini reponse (9 tests : 7 cibles + 2 regressions)
# Fix BUG #5 (ordinaux dans reponse Gemini) + BUG #9 (DD/MM/YYYY)
# Symetrie A9 : restriction _DATE_RE_MDY a _MONTH_EN_RE (defense-in-depth).
# ════════════════════════════════════════════════════════════════════


class TestV141X_ParserGeminiReponse:
    """V141 A.2 A9 - _parse_draw_date_multilang sur reponses Gemini."""

    def test_v141_x1_fr_1er_mai(self):
        """X1 - FR ordinal `1er mai 2026` dans reponse Gemini."""
        result = _parse_draw_date_multilang("Le tirage du 1er mai 2026 etait...")
        assert result == date(2026, 5, 1)

    def test_v141_x1bis_fr_premier_mai(self):
        """X1bis - FR ordinal lettres `premier mai 2026`."""
        result = _parse_draw_date_multilang("Le tirage du premier mai 2026 etait...")
        assert result == date(2026, 5, 1)

    def test_v141_x2_en_1st(self):
        """X2 - EN `May 1st 2026`."""
        result = _parse_draw_date_multilang("The draw of May 1st 2026 was...")
        assert result == date(2026, 5, 1)

    def test_v141_x3_dd_mm_yyyy_numeric(self):
        """X3 - Format DD/MM/YYYY numerique europeen (BUG #9)."""
        result = _parse_draw_date_multilang("Tirage du 09/02/2026")
        assert result == date(2026, 2, 9)

    def test_v141_x4_es_1_de_mayo(self):
        """X4 - ES `1° de mayo 2026`."""
        result = _parse_draw_date_multilang("El sorteo del 1° de mayo 2026")
        assert result == date(2026, 5, 1)

    def test_v141_x5_de_dot_format(self):
        """X5 - DE `1. Mai 2026` (regression V126.1 F1-bis)."""
        result = _parse_draw_date_multilang("Ziehung vom 1. Mai 2026")
        assert result == date(2026, 5, 1)

    def test_v141_x6_iso(self):
        """X6 - ISO 2026-05-01 (regression V99)."""
        result = _parse_draw_date_multilang("ISO date 2026-05-01 le tirage")
        assert result == date(2026, 5, 1)

    def test_v141_x_regression_fr_dmy_sans_ordinal(self):
        """Regression - FR DMY sans ordinal `15 mars 2026` doit continuer a matcher."""
        result = _parse_draw_date_multilang("Le 15 mars 2026 le tirage etait...")
        assert result == date(2026, 3, 15)

    def test_v141_x_regression_en_mdy_sans_ordinal(self):
        """Regression - EN MDY sans ordinal `March 15, 2026` doit continuer a matcher."""
        result = _parse_draw_date_multilang("March 15, 2026 the draw was...")
        assert result == date(2026, 3, 15)
