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
