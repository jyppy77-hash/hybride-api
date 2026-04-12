"""
Tests unitaires — Fix 8 : comparaison multi-numeros avec progression temporelle.
- _extract_temporal_date : extraction de date depuis expressions temporelles (6 langues)
- Phase 3-bis : comparaison non bloquee par force_sql
- _format_complex_context / _format_complex_context_em : progression temporelle
- Phase A toujours active sur les vraies questions d'argent
"""

import re
import pytest
from datetime import date, timedelta

from services.chat_detectors import (
    _extract_temporal_date,
    _detect_requete_complexe,
    _has_temporal_filter,
    _detect_argent,
)
from services.chat_detectors_em import (
    _detect_requete_complexe_em,
    _detect_argent_em,
)
from services.chat_utils import _format_complex_context
from services.chat_utils_em import _format_complex_context_em


# ═══════════════════════════════════════════════════════════════════════
# _extract_temporal_date — extraction de date (6 langues)
# ═══════════════════════════════════════════════════════════════════════

class TestExtractTemporalDate:
    """_extract_temporal_date extrait une date depuis une expression temporelle."""

    def test_fr_12_derniers_mois(self):
        d = _extract_temporal_date("sur les 12 derniers mois")
        assert d is not None
        expected = date.today() - timedelta(days=12 * 30)
        assert d == expected

    def test_fr_3_dernieres_annees(self):
        d = _extract_temporal_date("sur les 3 dernières années")
        assert d is not None
        expected = date.today() - timedelta(days=3 * 365)
        assert d == expected

    def test_fr_6_dernieres_semaines(self):
        d = _extract_temporal_date("sur les 6 dernières semaines")
        assert d is not None
        expected = date.today() - timedelta(weeks=6)
        assert d == expected

    def test_en_last_12_months(self):
        d = _extract_temporal_date("over the last 12 months")
        assert d is not None
        expected = date.today() - timedelta(days=12 * 30)
        assert d == expected

    def test_en_last_3_years(self):
        d = _extract_temporal_date("in the last 3 years")
        assert d is not None
        expected = date.today() - timedelta(days=3 * 365)
        assert d == expected

    def test_es_ultimos_12_meses(self):
        d = _extract_temporal_date("en los últimos 12 meses")
        assert d is not None
        expected = date.today() - timedelta(days=12 * 30)
        assert d == expected

    def test_es_ultimos_2_anos(self):
        d = _extract_temporal_date("en los últimos 2 años")
        assert d is not None
        expected = date.today() - timedelta(days=2 * 365)
        assert d == expected

    def test_pt_ultimos_12_meses(self):
        d = _extract_temporal_date("nos últimos 12 meses")
        assert d is not None
        expected = date.today() - timedelta(days=12 * 30)
        assert d == expected

    def test_pt_ultimos_2_anos(self):
        d = _extract_temporal_date("nos últimos 2 anos")
        assert d is not None
        expected = date.today() - timedelta(days=2 * 365)
        assert d == expected

    def test_de_letzten_12_monate(self):
        d = _extract_temporal_date("in den letzten 12 Monaten")
        assert d is not None
        expected = date.today() - timedelta(days=12 * 30)
        assert d == expected

    def test_de_letzten_3_jahre(self):
        d = _extract_temporal_date("in den letzten 3 Jahren")
        assert d is not None
        expected = date.today() - timedelta(days=3 * 365)
        assert d == expected

    def test_nl_laatste_12_maanden(self):
        d = _extract_temporal_date("in de laatste 12 maanden")
        assert d is not None
        expected = date.today() - timedelta(days=12 * 30)
        assert d == expected

    def test_nl_laatste_3_jaar(self):
        d = _extract_temporal_date("in de laatste 3 jaar")
        assert d is not None
        expected = date.today() - timedelta(days=3 * 365)
        assert d == expected

    def test_no_temporal_expression(self):
        d = _extract_temporal_date("compare le 31 et le 24")
        assert d is None

    def test_fr_reversed_order_derniers_12_mois(self):
        d = _extract_temporal_date("compare sur les derniers 12 mois")
        assert d is not None
        expected = date.today() - timedelta(days=12 * 30)
        assert d == expected


# ═══════════════════════════════════════════════════════════════════════
# Comparaison + filtre temporel — détection conjointe
# ═══════════════════════════════════════════════════════════════════════

class TestComparaisonTemporelleDetection:
    """Vérifie que la comparaison est détectée même avec filtre temporel."""

    def test_fr_compare_31_24_12_mois(self):
        msg = "Compare la fréquence du 31 et du 24 sur les 12 derniers mois"
        assert _has_temporal_filter(msg) is True
        intent = _detect_requete_complexe(msg)
        assert intent is not None
        assert intent["type"] == "comparaison"
        assert intent["num1"] == 31
        assert intent["num2"] == 24

    def test_en_compare_12_45(self):
        msg = "Compare 12 and 45 over the last 6 months"
        assert _has_temporal_filter(msg) is True
        intent = _detect_requete_complexe(msg)
        assert intent is not None
        assert intent["type"] == "comparaison"

    def test_fr_31_vs_24_12_mois(self):
        msg = "31 vs 24 sur les 12 derniers mois, lequel progresse le plus ?"
        assert _has_temporal_filter(msg) is True
        intent = _detect_requete_complexe(msg)
        assert intent is not None
        assert intent["type"] == "comparaison"

    def test_em_compare_with_temporal(self):
        msg = "Compare le 7 et le 23 sur les 3 dernières années"
        assert _has_temporal_filter(msg) is True
        intent = _detect_requete_complexe_em(msg)
        assert intent is not None
        assert intent["type"] == "comparaison"

    def test_pt_compara_do_12_e_do_45(self):
        msg = "Compara a frequência do 12 e do 45 nos últimos 12 meses"
        assert _has_temporal_filter(msg) is True
        intent = _detect_requete_complexe_em(msg)
        assert intent is not None
        assert intent["type"] == "comparaison"
        assert intent["num1"] == 12
        assert intent["num2"] == 45


# ═══════════════════════════════════════════════════════════════════════
# Formatage contexte — progression temporelle
# ═══════════════════════════════════════════════════════════════════════

class TestComparaisonContextProgression:
    """Le contexte comparaison affiche la progression quand des données period sont présentes."""

    _INTENT = {"type": "comparaison", "num1": 31, "num2": 24, "num_type": "principal"}

    _DATA_WITH_PERIOD = {
        "num1": {
            "numero": 31, "frequence_totale": 120, "pourcentage_apparition": "12.2%",
            "ecart_actuel": 5, "categorie": "chaud", "total_tirages": 990,
        },
        "num2": {
            "numero": 24, "frequence_totale": 100, "pourcentage_apparition": "10.1%",
            "ecart_actuel": 12, "categorie": "neutre", "total_tirages": 990,
        },
        "diff_frequence": 20,
        "favori_frequence": 31,
        "period": {
            "date_from": "2025-03-10",
            "total_tirages_period": 156,
            "num1_freq_period": 22,
            "num2_freq_period": 14,
            "num1_expected": 18.9,
            "num2_expected": 15.8,
            "num1_progression_pct": 16.4,
            "num2_progression_pct": -11.4,
            "plus_progresse": 31,
        },
    }

    _DATA_WITHOUT_PERIOD = {
        "num1": {
            "numero": 31, "frequence_totale": 120, "pourcentage_apparition": "12.2%",
            "ecart_actuel": 5, "categorie": "chaud", "total_tirages": 990,
        },
        "num2": {
            "numero": 24, "frequence_totale": 100, "pourcentage_apparition": "10.1%",
            "ecart_actuel": 12, "categorie": "neutre", "total_tirages": 990,
        },
        "diff_frequence": 20,
        "favori_frequence": 31,
    }

    def test_loto_with_period_has_comparaison_sur_periode(self):
        ctx = _format_complex_context(self._INTENT, self._DATA_WITH_PERIOD)
        assert "[COMPARAISON SUR PÉRIODE" in ctx

    def test_loto_with_period_has_freq_sur_periode_section(self):
        ctx = _format_complex_context(self._INTENT, self._DATA_WITH_PERIOD)
        assert "[FRÉQUENCE SUR LA PÉRIODE" in ctx

    def test_loto_with_period_has_freq_period(self):
        ctx = _format_complex_context(self._INTENT, self._DATA_WITH_PERIOD)
        assert "22 apparitions" in ctx
        assert "14 apparitions" in ctx

    def test_loto_with_period_has_expected(self):
        ctx = _format_complex_context(self._INTENT, self._DATA_WITH_PERIOD)
        assert "attendu" in ctx
        assert "18.9" in ctx

    def test_loto_with_period_has_progression_pct(self):
        ctx = _format_complex_context(self._INTENT, self._DATA_WITH_PERIOD)
        assert "+16.4%" in ctx
        assert "-11.4%" in ctx

    def test_loto_with_period_has_plus_progresse(self):
        ctx = _format_complex_context(self._INTENT, self._DATA_WITH_PERIOD)
        assert "31 a le plus progressé" in ctx

    def test_loto_with_period_has_reference_section(self):
        """Fréquence totale historique est en RÉFÉRENCE, pas en principal."""
        ctx = _format_complex_context(self._INTENT, self._DATA_WITH_PERIOD)
        assert "[RÉFÉRENCE" in ctx
        assert "historique total" in ctx

    def test_loto_with_period_has_important_instruction(self):
        ctx = _format_complex_context(self._INTENT, self._DATA_WITH_PERIOD)
        assert "IMPORTANT" in ctx
        assert "PÉRIODE" in ctx

    def test_loto_with_period_freq_period_before_total(self):
        """freq_period apparaît AVANT freq_total dans le contexte."""
        ctx = _format_complex_context(self._INTENT, self._DATA_WITH_PERIOD)
        pos_period = ctx.index("22 apparitions")
        pos_total = ctx.index("120 apparitions")
        assert pos_period < pos_total

    def test_loto_without_period_no_periode_section(self):
        ctx = _format_complex_context(self._INTENT, self._DATA_WITHOUT_PERIOD)
        assert "[COMPARAISON SUR PÉRIODE" not in ctx
        assert "[FRÉQUENCE SUR LA PÉRIODE" not in ctx

    def test_loto_without_period_still_has_comparaison(self):
        ctx = _format_complex_context(self._INTENT, self._DATA_WITHOUT_PERIOD)
        assert "[COMPARAISON" in ctx
        assert "120 apparitions" in ctx

    # EM variant
    _INTENT_EM = {"type": "comparaison", "num1": 31, "num2": 24, "num_type": "boule"}

    def test_em_with_period_has_periode_section(self):
        ctx = _format_complex_context_em(self._INTENT_EM, self._DATA_WITH_PERIOD)
        assert "[COMPARAISON SUR PÉRIODE" in ctx
        assert "[FRÉQUENCE SUR LA PÉRIODE" in ctx
        assert "+16.4%" in ctx

    def test_em_with_period_freq_period_before_total(self):
        ctx = _format_complex_context_em(self._INTENT_EM, self._DATA_WITH_PERIOD)
        pos_period = ctx.index("22 apparitions")
        pos_total = ctx.index("120 apparitions")
        assert pos_period < pos_total

    def test_em_without_period_no_periode_section(self):
        ctx = _format_complex_context_em(self._INTENT_EM, self._DATA_WITHOUT_PERIOD)
        assert "[COMPARAISON SUR PÉRIODE" not in ctx


# ═══════════════════════════════════════════════════════════════════════
# Phase A toujours active — argent réel non bloqué par l'exclusion score
# ═══════════════════════════════════════════════════════════════════════

class TestPhaseANotBypassedByComparison:
    """Phase A doit toujours bloquer les vraies questions d'argent."""

    def test_compare_combien_je_gagne(self):
        """Argent dans une comparaison = bloqué."""
        assert _detect_argent("combien je gagne avec le 31 vs le 24") is True

    def test_compare_sans_argent_not_blocked(self):
        assert _detect_argent("compare le 31 et le 24") is False

    def test_em_compare_how_much_win(self):
        assert _detect_argent_em("how much can I win comparing 12 vs 45", "en") is True

    def test_em_compare_sans_argent(self):
        assert _detect_argent_em("compare 12 and 45 over last 6 months", "en") is False


# ═══════════════════════════════════════════════════════════════════════
# Multilang comparison detection (EM)
# ═══════════════════════════════════════════════════════════════════════

class TestComparaisonMultilangEM:
    """_detect_requete_complexe_em matche les comparaisons en toutes langues."""

    def test_fr_compare(self):
        intent = _detect_requete_complexe_em("compare le 7 et le 23")
        assert intent is not None and intent["type"] == "comparaison"

    def test_en_compare(self):
        # Uses "vs" which is language-neutral
        intent = _detect_requete_complexe_em("12 vs 45")
        assert intent is not None and intent["type"] == "comparaison"

    def test_de_compare(self):
        intent = _detect_requete_complexe_em("vergleiche 31 vs 24")
        assert intent is not None and intent["type"] == "comparaison"

    def test_es_compare(self):
        intent = _detect_requete_complexe_em("compara el 7 vs 23")
        assert intent is not None and intent["type"] == "comparaison"

    def test_pt_compare(self):
        intent = _detect_requete_complexe_em("compara o 31 vs 24")
        assert intent is not None and intent["type"] == "comparaison"

    def test_nl_compare(self):
        intent = _detect_requete_complexe_em("vergelijk 7 vs 23")
        assert intent is not None and intent["type"] == "comparaison"

    # --- Articles / contractions spécifiques par langue ---

    def test_fr_du_article(self):
        intent = _detect_requete_complexe_em("compare la fréquence du 31 et du 24")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 31 and intent["num2"] == 24

    def test_pt_do_article(self):
        intent = _detect_requete_complexe_em("compara a frequência do 12 e do 45")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 12 and intent["num2"] == 45

    def test_pt_da_article(self):
        intent = _detect_requete_complexe_em("compara da 5 e da 18")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 5 and intent["num2"] == 18

    def test_pt_dos_article(self):
        intent = _detect_requete_complexe_em("compara dos 10 e dos 20")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 10 and intent["num2"] == 20

    def test_pt_das_article(self):
        intent = _detect_requete_complexe_em("compara das 3 e das 7")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 3 and intent["num2"] == 7

    def test_pt_de_preposition(self):
        intent = _detect_requete_complexe_em("compara de 15 e de 30")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 15 and intent["num2"] == 30

    def test_pt_o_article(self):
        intent = _detect_requete_complexe_em("compara o 31 e o 24")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 31 and intent["num2"] == 24

    def test_es_el_article(self):
        intent = _detect_requete_complexe_em("compara el 7 y el 23")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 7 and intent["num2"] == 23

    def test_es_del_article(self):
        intent = _detect_requete_complexe_em("compara la frecuencia del 12 y del 45")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 12 and intent["num2"] == 45

    def test_de_von_preposition(self):
        intent = _detect_requete_complexe_em("vergleiche die Häufigkeit von 31 und von 24")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 31 and intent["num2"] == 24

    def test_nl_van_preposition(self):
        intent = _detect_requete_complexe_em("vergelijk de frequentie van 12 en van 45")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 12 and intent["num2"] == 45

    def test_en_compare_and(self):
        intent = _detect_requete_complexe_em("compare 12 and 45")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 12 and intent["num2"] == 45


# ═══════════════════════════════════════════════════════════════════════
# Multilang comparison detection (Loto)
# ═══════════════════════════════════════════════════════════════════════

class TestComparaisonMultilangLoto:
    """_detect_requete_complexe matche les comparaisons avec articles multilingues."""

    def test_fr_du(self):
        intent = _detect_requete_complexe("compare du 31 et du 24")
        assert intent is not None and intent["type"] == "comparaison"

    def test_pt_do(self):
        intent = _detect_requete_complexe("compara do 12 e do 45")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 12 and intent["num2"] == 45

    def test_es_del(self):
        intent = _detect_requete_complexe("compara del 7 y del 23")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 7 and intent["num2"] == 23

    def test_de_von(self):
        intent = _detect_requete_complexe("compare von 31 und von 24")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 31 and intent["num2"] == 24

    def test_nl_van(self):
        intent = _detect_requete_complexe("compare van 12 en van 45")
        assert intent is not None and intent["type"] == "comparaison"
        assert intent["num1"] == 12 and intent["num2"] == 45


# ═══════════════════════════════════════════════════════════════════════
# _clean_response — tags internes jamais visibles par l'utilisateur
# ═══════════════════════════════════════════════════════════════════════

class TestCleanResponseStripsTags:
    """_clean_response doit supprimer tous les tags internes du contexte."""

    def test_strip_comparaison_sur_periode(self):
        from services.chat_utils import _clean_response
        text = "[COMPARAISON SUR PÉRIODE — 12 vs 45] Voici les résultats."
        result = _clean_response(text)
        assert "[COMPARAISON" not in result
        assert "Voici les résultats" in result

    def test_strip_frequence_sur_periode(self):
        from services.chat_utils import _clean_response
        text = "[FRÉQUENCE SUR LA PÉRIODE — C'EST CE CHIFFRE QUE TU DOIS CITER] 22 apparitions"
        result = _clean_response(text)
        assert "[FRÉQUENCE" not in result
        assert "22 apparitions" in result

    def test_strip_progression(self):
        from services.chat_utils import _clean_response
        text = "[PROGRESSION PAR RAPPORT À LA MOYENNE HISTORIQUE] +16.4%"
        result = _clean_response(text)
        assert "[PROGRESSION" not in result
        assert "+16.4%" in result

    def test_strip_reference(self):
        from services.chat_utils import _clean_response
        text = "[RÉFÉRENCE — fréquence totale historique (ne PAS citer en premier)] 120 fois"
        result = _clean_response(text)
        assert "[RÉFÉRENCE" not in result
        assert "120 fois" in result

    def test_strip_breakdown(self):
        from services.chat_utils import _clean_response
        text = "[BREAKDOWN — Critères de sélection] pair/impair 3/2"
        result = _clean_response(text)
        assert "[BREAKDOWN" not in result
        assert "pair/impair" in result

    def test_strip_message_a_adapter(self):
        from services.chat_utils import _clean_response
        text = "[MESSAGE A ADAPTER] Reformule en allemand."
        result = _clean_response(text)
        assert "[MESSAGE A ADAPTER]" not in result

    def test_strip_all_period_tags_combined(self):
        """Simule une réponse Gemini qui aurait échoé à reformuler le contexte brut."""
        from services.chat_utils import _clean_response
        raw = (
            "[COMPARAISON SUR PÉRIODE — 12 vs 45]\n"
            "[FRÉQUENCE SUR LA PÉRIODE — C'EST CE CHIFFRE QUE TU DOIS CITER]\n"
            "N°12 : 22 apparitions\n"
            "[PROGRESSION PAR RAPPORT À LA MOYENNE HISTORIQUE]\n"
            "+16.4%\n"
            "[RÉFÉRENCE — fréquence totale historique (ne PAS citer en premier)]\n"
            "120 fois\n"
            "[MESSAGE A ADAPTER]\n"
            "Voici la comparaison."
        )
        result = _clean_response(raw)
        assert "[COMPARAISON" not in result
        assert "[FRÉQUENCE" not in result
        assert "[PROGRESSION" not in result
        assert "[RÉFÉRENCE" not in result
        assert "[MESSAGE A ADAPTER]" not in result
        assert "22 apparitions" in result
        assert "+16.4%" in result
        assert "Voici la comparaison" in result

    def test_existing_tags_still_stripped(self):
        """Vérifie que les tags existants (pre-Fix 8c) sont toujours nettoyés."""
        from services.chat_utils import _clean_response
        text = "[RÉSULTAT SQL] données [CLASSEMENT top 10] résultats [ANALYSE DE GRILLE 5/5]"
        result = _clean_response(text)
        assert "[RÉSULTAT SQL]" not in result
        assert "[CLASSEMENT" not in result
        assert "[ANALYSE DE GRILLE" not in result


# ═══════════════════════════════════════════════════════════════════════
# test_no_raw_context_leak — aucun tag technique ne fuit dans la réponse
# ═══════════════════════════════════════════════════════════════════════

class TestNoRawContextLeak:
    """Aucun tag technique entre crochets ne doit apparaître dans la réponse finale."""

    # Regex couvrant TOUS les tags internes connus
    _LEAK_RE = re.compile(
        r'\['
        r'(?:COMPARAISON|FRÉQUENCE|FREQUENCE|RÉFÉRENCE|REFERENCE|'
        r'PROGRESSION|BREAKDOWN|MESSAGE A ADAPTER|'
        r'RÉSULTAT SQL|RESULTAT SQL|RÉSULTAT TIRAGE|RESULTAT TIRAGE|'
        r'ANALYSE DE GRILLE|CLASSEMENT|'
        r'NUMÉROS? (?:CHAUDS?|FROIDS?)|NUMEROS? (?:CHAUDS?|FROIDS?)|'
        r'DONNÉES TEMPS RÉEL|DONNEES TEMPS REEL|'
        r'PROCHAIN TIRAGE|'
        r'CORR[EÉ]LATIONS? DE PAIRES|CORRELATIONS? DE PAIRES|'
        r'GRILLE G[EÉ]N[EÉ]R[EÉ]E PAR HYBRIDE|GRILLE GENEREE PAR HYBRIDE|'
        r'Page:|Question utilisateur|CONTEXTE CONTINUATION)'
    )

    def _assert_no_leak(self, text: str):
        from services.chat_utils import _clean_response
        cleaned = _clean_response(text)
        match = self._LEAK_RE.search(cleaned)
        assert match is None, f"Tag technique fuite dans la réponse : {match.group()}"

    def test_comparison_period_full_context_de(self):
        """Simule un contexte brut DE retourné par Gemini."""
        raw = (
            "[COMPARAISON SUR PÉRIODE — Nummer 12 vs Nummer 45]\n"
            "[FRÉQUENCE SUR LA PÉRIODE — C'EST CE CHIFFRE QUE TU DOIS CITER]\n"
            "Nummer 12: 1 Auftritt, Nummer 45: 4 Auftritte\n"
            "[PROGRESSION PAR RAPPORT À LA MOYENNE HISTORIQUE]\n"
            "Nr. 12: -85.7%, Nr. 45: +42.9%\n"
            "[RÉFÉRENCE — fréquence totale historique (ne PAS citer en premier)]\n"
            "Nummer 12: 72 Auftritte, Nummer 45: 68 Auftritte\n"
            "In den letzten 12 Monaten wurde die 45 also 4 Mal gezogen."
        )
        self._assert_no_leak(raw)

    def test_comparison_period_full_context_es(self):
        raw = (
            "[COMPARAISON SUR PÉRIODE — Número 12 vs Número 45]\n"
            "[FRÉQUENCE SUR LA PÉRIODE — C'EST CE CHIFFRE QUE TU DOIS CITER]\n"
            "Número 12: 1 aparición, Número 45: 4 apariciones\n"
            "[RÉFÉRENCE — fréquence totale historique (ne PAS citer en premier)]\n"
            "Número 12: 72 apariciones\n"
            "En los últimos 12 meses el 45 salió 4 veces."
        )
        self._assert_no_leak(raw)

    def test_comparison_period_full_context_pt(self):
        raw = (
            "[COMPARAISON SUR PÉRIODE — Número 12 vs Número 45]\n"
            "[FRÉQUENCE SUR LA PÉRIODE — C'EST CE CHIFFRE QUE TU DOIS CITER]\n"
            "Número 12: 1 aparição, Número 45: 4 aparições\n"
            "[RÉFÉRENCE — fréquence totale historique (ne PAS citer en premier)]\n"
            "Número 12: 72 aparições\n"
            "Nos últimos 12 meses o 45 saiu 4 vezes."
        )
        self._assert_no_leak(raw)

    def test_comparison_period_full_context_nl(self):
        raw = (
            "[COMPARAISON SUR PÉRIODE — Nummer 12 vs Nummer 45]\n"
            "[FRÉQUENCE SUR LA PÉRIODE — C'EST CE CHIFFRE QUE TU DOIS CITER]\n"
            "Nummer 12: 1 keer, Nummer 45: 4 keer\n"
            "[RÉFÉRENCE — fréquence totale historique (ne PAS citer en premier)]\n"
            "Nummer 12: 72 keer\n"
            "In de laatste 12 maanden kwam 45 vier keer voor."
        )
        self._assert_no_leak(raw)

    def test_sql_result_tag(self):
        self._assert_no_leak("[RÉSULTAT SQL] SELECT * FROM tirages LIMIT 10")

    def test_breakdown_tag(self):
        self._assert_no_leak("[BREAKDOWN — Critères de sélection] pair/impair 3/2")

    def test_grille_generee_tag(self):
        self._assert_no_leak("[GRILLE GÉNÉRÉE PAR HYBRIDE — mode equilibre] 5 12 23 34 45")

    def test_clean_text_passes(self):
        """Texte normal sans tag ne doit pas être modifié."""
        text = "Le numéro 45 est sorti 4 fois sur les 12 derniers mois."
        from services.chat_utils import _clean_response
        assert _clean_response(text) == text


# ═══════════════════════════════════════════════════════════════════════
# Cohérence prompts chatbot — règle de langue obligatoire
# ═══════════════════════════════════════════════════════════════════════

class TestPromptLanguageRule:
    """Chaque prompt chatbot EM non-FR doit avoir une règle de langue obligatoire."""

    _LANG_HEADERS = {
        "en": "[LANGUAGE — MANDATORY RULE]",
        "es": "[IDIOMA — REGLA OBLIGATORIA]",
        "pt": "[IDIOMA — REGRA OBRIGATÓRIA]",
        "de": "[SPRACHE — PFLICHT-REGEL]",
        "nl": "[TAAL — VERPLICHTE REGEL]",
    }

    def _read_prompt(self, lang: str) -> str:
        import os
        path = os.path.join("prompts", "em", lang, "prompt_hybride_em.txt")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_en_has_language_rule(self):
        content = self._read_prompt("en")
        assert self._LANG_HEADERS["en"] in content

    def test_es_has_language_rule(self):
        content = self._read_prompt("es")
        assert self._LANG_HEADERS["es"] in content

    def test_pt_has_language_rule(self):
        content = self._read_prompt("pt")
        assert self._LANG_HEADERS["pt"] in content

    def test_de_has_language_rule(self):
        content = self._read_prompt("de")
        assert self._LANG_HEADERS["de"] in content

    def test_nl_has_language_rule(self):
        content = self._read_prompt("nl")
        assert self._LANG_HEADERS["nl"] in content

    def test_pt_has_anti_spanish_rule(self):
        """PT doit explicitement interdire le basculement en espagnol."""
        content = self._read_prompt("pt")
        assert "NUNCA" in content and "espanhol" in content


# ═══════════════════════════════════════════════════════════════════════
# StreamBuffer — buffer SSE anti-fuite tags fragmentés
# ═══════════════════════════════════════════════════════════════════════

class TestStreamBuffer:
    """Le StreamBuffer accumule les chunks et nettoie les tags fragmentés."""

    def _make_buf(self):
        from services.chat_utils import StreamBuffer
        return StreamBuffer()

    def test_tag_complete_single_chunk(self):
        """Tag complet dans un seul chunk → nettoyé."""
        buf = self._make_buf()
        result = buf.add_chunk("[COMPARAISON SUR PÉRIODE — 12 vs 45] Voici.")
        assert "[COMPARAISON" not in result
        assert "Voici." in result

    def test_tag_fragmented_4_chunks(self):
        """Tag fragmenté sur 4 chunks → accumulé puis nettoyé."""
        buf = self._make_buf()
        r1 = buf.add_chunk("Texte avant [COMP")
        assert "Texte avant" in r1  # texte safe avant le '['
        assert "[COMP" not in r1

        r2 = buf.add_chunk("ARAISON SUR ")
        assert r2 == ""  # encore en attente du ']'

        r3 = buf.add_chunk("PÉRIODE — 12 vs 45")
        assert r3 == ""  # toujours pas de ']'

        r4 = buf.add_chunk("] Suite du texte.")
        assert "[COMPARAISON" not in r4
        assert "Suite du texte." in r4

    def test_normal_text_passthrough(self):
        """Texte normal sans tag → passé directement."""
        buf = self._make_buf()
        result = buf.add_chunk("Le numéro 45 est sorti 4 fois.")
        assert result == "Le numéro 45 est sorti 4 fois."

    def test_open_bracket_then_normal_text(self):
        """'[' en fin de chunk suivi de texte normal avec ']' → géré."""
        buf = self._make_buf()
        r1 = buf.add_chunk("Début [")
        assert "Début" in r1

        r2 = buf.add_chunk("simple crochet] fin.")
        # Le contenu entre crochets n'est pas un tag connu → préservé
        assert "fin." in r2

    def test_multiple_tags_in_buffer(self):
        """Tags multiples dans un buffer → tous nettoyés."""
        buf = self._make_buf()
        text = (
            "[FRÉQUENCE SUR LA PÉRIODE — chiffre] données "
            "[RÉFÉRENCE — historique] résultat "
            "[PROGRESSION pct] final"
        )
        result = buf.add_chunk(text)
        assert "[FRÉQUENCE" not in result
        assert "[RÉFÉRENCE" not in result
        assert "[PROGRESSION" not in result
        assert "données" in result
        assert "final" in result

    def test_flush_final(self):
        """Flush final vide le buffer proprement."""
        buf = self._make_buf()
        r1 = buf.add_chunk("Texte [BREAK")
        assert "Texte" in r1

        r2 = buf.flush()
        # Le tag incomplet est flushé et nettoyé si possible
        assert isinstance(r2, str)

    def test_flush_empty_buffer(self):
        """Flush sur buffer vide retourne chaîne vide."""
        buf = self._make_buf()
        assert buf.flush() == ""

    def test_real_comparison_context_de(self):
        """Simule le cas réel DE : contexte comparaison fragmenté."""
        buf = self._make_buf()
        chunks = [
            "[COMPARAISON SUR PÉRIODE",
            " — Nummer 12 vs Nummer 45]",
            "\n[FRÉQUENCE SUR LA PÉRIODE",
            " — C'EST CE CHIFFRE]\n",
            "Nummer 12: 1 Auftritt\n",
            "[RÉFÉRENCE — historique]",
            "\nAntwort auf Deutsch.",
        ]
        collected = ""
        for c in chunks:
            safe = buf.add_chunk(c)
            collected += safe
        collected += buf.flush()

        assert "[COMPARAISON" not in collected
        assert "[FRÉQUENCE" not in collected
        assert "[RÉFÉRENCE" not in collected
        assert "Nummer 12: 1 Auftritt" in collected
        assert "Antwort auf Deutsch." in collected

    def test_breakdown_tag_fragmented(self):
        """Tag [BREAKDOWN] fragmenté → nettoyé."""
        buf = self._make_buf()
        r1 = buf.add_chunk("Voici [BREAK")
        r2 = buf.add_chunk("DOWN — Critères] la grille.")
        collected = r1 + r2 + buf.flush()
        assert "[BREAKDOWN" not in collected
        assert "la grille." in collected

    def test_sponsor_line_passes(self):
        """Les lignes sponsor ne contiennent pas de tags → passent directement."""
        buf = self._make_buf()
        sponsor = "\n\n📢 Découvrez notre partenaire : LotoBonus.fr"
        result = buf.add_chunk(sponsor)
        assert "LotoBonus.fr" in result


# ═══════════════════════════════════════════════════════════════════════
# F06 V98 — Phase 3-bis temporal filter multilang (ES/PT/DE/NL)
# ═══════════════════════════════════════════════════════════════════════

class TestTemporalFilterMultilang:
    """_has_temporal_filter detects temporal expressions in all 6 languages."""

    # ── ES ──
    def test_es_ultimos_meses(self):
        assert _has_temporal_filter("los últimos 6 meses") is True

    def test_es_en_2024(self):
        assert _has_temporal_filter("estadísticas en 2024") is True

    def test_es_entre_anos(self):
        assert _has_temporal_filter("entre 2024 y 2025") is True

    # ── PT ──
    def test_pt_ultimos_meses(self):
        assert _has_temporal_filter("nos últimos 6 meses") is True

    def test_pt_em_2024(self):
        assert _has_temporal_filter("estatísticas em 2024") is True

    def test_pt_entre_anos(self):
        assert _has_temporal_filter("entre 2024 e 2025") is True

    # ── DE ──
    def test_de_letzten_monate(self):
        assert _has_temporal_filter("die letzten 6 monate") is True

    def test_de_im_2024(self):
        assert _has_temporal_filter("Statistik im 2024") is True

    def test_de_zwischen_jahren(self):
        assert _has_temporal_filter("zwischen 2024 und 2025") is True

    # ── NL ──
    def test_nl_laatste_maanden(self):
        assert _has_temporal_filter("de laatste 6 maanden") is True

    def test_nl_in_2024(self):
        assert _has_temporal_filter("statistieken in 2024") is True

    def test_nl_tussen_jaren(self):
        assert _has_temporal_filter("tussen 2024 en 2025") is True


class TestComparaisonTemporelleMultilang:
    """Phase 3-bis: comparison + temporal filter in ES/PT/DE/NL."""

    def test_es_compare_temporal(self):
        msg = "Compara el 12 y el 34 en los últimos 6 meses"
        assert _has_temporal_filter(msg) is True
        intent = _detect_requete_complexe_em(msg)
        assert intent is not None
        assert intent["type"] == "comparaison"

    def test_pt_compare_temporal(self):
        msg = "Compara o 12 e o 34 nos últimos 6 meses"
        assert _has_temporal_filter(msg) is True
        intent = _detect_requete_complexe_em(msg)
        assert intent is not None
        assert intent["type"] == "comparaison"

    def test_de_vergleich_temporal(self):
        msg = "Vergleiche die 12 und 34 die letzten 6 monate"
        assert _has_temporal_filter(msg) is True

    def test_nl_vergelijk_temporal(self):
        msg = "Vergelijk 12 en 34 in de laatste 6 maanden"
        assert _has_temporal_filter(msg) is True
