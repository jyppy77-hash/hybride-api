"""
Tests supplementaires pour services/chat_detectors.py.
Couvre les fonctions non testees dans test_insult_oor.py :
_detect_grille, _detect_mode, _detect_requete_complexe,
_detect_prochain_tirage, _is_short_continuation.
"""

from services.chat_detectors import (
    _detect_grille, _detect_mode, _detect_requete_complexe,
    _detect_prochain_tirage, _is_short_continuation,
    _extract_top_n, _has_temporal_filter,
)


# ═══════════════════════════════════════════════════════════════════════
# _detect_grille
# ═══════════════════════════════════════════════════════════════════════

class TestDetectGrille:

    def test_five_numbers(self):
        nums, chance = _detect_grille("5 12 23 34 45")
        assert nums == [5, 12, 23, 34, 45]
        assert chance is None

    def test_with_chance_keyword(self):
        nums, chance = _detect_grille("5 12 23 34 45 chance 7")
        assert nums == [5, 12, 23, 34, 45]
        assert chance == 7

    def test_with_plus_notation(self):
        nums, chance = _detect_grille("5 12 23 34 45 + 3")
        assert nums == [5, 12, 23, 34, 45]
        assert chance == 3

    def test_four_numbers_returns_none(self):
        nums, chance = _detect_grille("5 12 23 34")
        assert nums is None
        assert chance is None

    def test_six_numbers_returns_none(self):
        nums, chance = _detect_grille("5 12 23 34 45 46")
        assert nums is None
        assert chance is None

    def test_duplicates_collapsed(self):
        """Doublons elimines → moins de 5 uniques → None."""
        nums, chance = _detect_grille("5 12 23 5 12")
        assert nums is None
        assert chance is None

    def test_chance_out_of_range_pollutes_nums(self):
        """Chance hors range (15) reste dans le texte → 6 nums → None."""
        nums, chance = _detect_grille("5 12 23 34 45 chance 15")
        assert nums is None


# ═══════════════════════════════════════════════════════════════════════
# _detect_mode
# ═══════════════════════════════════════════════════════════════════════

class TestDetectMode:

    def test_meta_keyword(self):
        assert _detect_mode("quel algorithme utilises-tu ?", "accueil") == "meta"

    def test_meta_ponderation(self):
        assert _detect_mode("explique la pondération", "accueil") == "meta"

    def test_analyse_page_simulateur(self):
        assert _detect_mode("donne-moi une grille", "simulateur") == "analyse"

    def test_analyse_page_statistiques(self):
        assert _detect_mode("stats du 7", "statistiques") == "analyse"

    def test_decouverte_default(self):
        assert _detect_mode("bonjour", "accueil") == "decouverte"


# ═══════════════════════════════════════════════════════════════════════
# _detect_requete_complexe
# ═══════════════════════════════════════════════════════════════════════

class TestDetectRequeteComplexe:

    def test_comparaison(self):
        result = _detect_requete_complexe("compare le 7 et le 23")
        assert result is not None
        assert result["type"] == "comparaison"
        assert result["num1"] == 7
        assert result["num2"] == 23

    def test_comparaison_vs(self):
        result = _detect_requete_complexe("7 vs 14")
        assert result is not None
        assert result["type"] == "comparaison"

    def test_classement_top5(self):
        result = _detect_requete_complexe("top 5 des numeros les plus frequents")
        assert result is not None
        assert result["type"] == "classement"
        assert result["tri"] == "frequence_desc"
        assert result["limit"] == 5

    def test_classement_ecart(self):
        result = _detect_requete_complexe("quels numeros ont le plus gros ecart")
        assert result is not None
        assert result["type"] == "classement"
        assert result["tri"] == "ecart_desc"

    def test_categorie_chaud(self):
        result = _detect_requete_complexe("quels numeros sont chauds en ce moment")
        assert result is not None
        assert result["type"] == "categorie"
        assert result["categorie"] == "chaud"

    def test_categorie_froid(self):
        result = _detect_requete_complexe("quels numeros sont froids actuellement")
        assert result is not None
        assert result["type"] == "categorie"
        assert result["categorie"] == "froid"

    def test_no_match_returns_none(self):
        assert _detect_requete_complexe("bonjour comment ca va") is None

    # --- Top N extraction (Loto FR) ---

    def test_top_10_frequence_desc(self):
        """'top 10 des numéros les plus fréquents' → limit=10."""
        r = _detect_requete_complexe("Donne-moi le top 10 des numéros les plus fréquents")
        assert r is not None
        assert r["limit"] == 10

    def test_top_3_frequence_desc(self):
        """'top 3' → limit=3."""
        r = _detect_requete_complexe("Top 3 des numéros les plus fréquents")
        assert r is not None
        assert r["limit"] == 3

    def test_les_10_plus_frequents(self):
        """'les 10 plus fréquents' → limit=10 (not default 5)."""
        r = _detect_requete_complexe("les 10 numéros les plus fréquents")
        assert r is not None
        assert r["limit"] == 10

    def test_default_limit_5(self):
        """Sans nombre → limit=5 par défaut."""
        r = _detect_requete_complexe("quels sont les numéros les plus fréquents")
        assert r is not None
        assert r["limit"] == 5

    def test_max_cap_20(self):
        """N > 20 → capped à 20."""
        assert _extract_top_n("top 25") == 5  # 25 > 20 → default

    def test_top_20_accepted(self):
        """N = 20 → accepted."""
        assert _extract_top_n("top 20") == 20


# ═══════════════════════════════════════════════════════════════════════
# _extract_top_n — Multilingual
# ═══════════════════════════════════════════════════════════════════════

class TestExtractTopN:

    def test_top_10(self):
        assert _extract_top_n("top 10 des plus fréquents") == 10

    def test_les_10_plus(self):
        assert _extract_top_n("les 10 plus fréquents") == 10

    def test_the_10_most(self):
        assert _extract_top_n("the 10 most frequent numbers") == 10

    def test_os_5_mais(self):
        assert _extract_top_n("os 5 mais frequentes") == 5

    def test_los_10_mas(self):
        assert _extract_top_n("los 10 más frecuentes") == 10

    def test_die_10_haeufigsten(self):
        assert _extract_top_n("die 10 häufigsten Zahlen") == 10

    def test_de_10_meest(self):
        assert _extract_top_n("de 10 meest voorkomende nummers") == 10

    def test_donne_moi_10(self):
        assert _extract_top_n("donne-moi 10 numéros") == 10

    def test_give_me_10(self):
        assert _extract_top_n("give me 10 numbers") == 10

    def test_default_no_number(self):
        assert _extract_top_n("quels sont les plus fréquents") == 5

    def test_over_20_returns_default(self):
        assert _extract_top_n("top 25 numéros") == 5

    def test_zero_returns_default(self):
        assert _extract_top_n("top 0") == 5


# ═══════════════════════════════════════════════════════════════════════
# _detect_prochain_tirage
# ═══════════════════════════════════════════════════════════════════════

class TestDetectProchainTirage:

    def test_detected(self):
        assert _detect_prochain_tirage("c'est quand le prochain tirage ?") is True

    def test_detected_quand(self):
        assert _detect_prochain_tirage("quand a lieu le prochain loto") is True

    def test_not_detected(self):
        assert _detect_prochain_tirage("donne-moi les stats du 7") is False


# ═══════════════════════════════════════════════════════════════════════
# _is_short_continuation
# ═══════════════════════════════════════════════════════════════════════

class TestIsShortContinuation:

    def test_oui_detected(self):
        assert _is_short_continuation("oui") is True

    def test_vas_y_detected(self):
        assert _is_short_continuation("vas-y !") is True

    def test_long_message_not_detected(self):
        msg = "Quelle est la frequence du numero 7 sur les deux dernieres annees ?"
        assert _is_short_continuation(msg) is False

    def test_empty_not_detected(self):
        assert _is_short_continuation("") is False


# ═══════════════════════════════════════════════════════════════════════
# _has_temporal_filter — Multilingual
# ═══════════════════════════════════════════════════════════════════════

class TestHasTemporalFilter:

    # ── FR (existing patterns — regression) ──

    def test_fr_en_2024(self):
        assert _has_temporal_filter("Combien de fois le 12 est sorti en 2024 ?") is True

    def test_fr_cette_annee(self):
        assert _has_temporal_filter("Le 7 est sorti combien de fois cette année ?") is True

    def test_fr_janvier(self):
        assert _has_temporal_filter("Quel numéro a le plus sorti en janvier 2025 ?") is True

    def test_fr_depuis(self):
        assert _has_temporal_filter("depuis 2023 combien de fois le 5 ?") is True

    def test_fr_no_temporal(self):
        assert _has_temporal_filter("Combien de fois le 12 est sorti ?") is False

    # ── EN ──

    def test_en_in_2024(self):
        assert _has_temporal_filter("How many times did 12 appear in 2024?") is True

    def test_en_this_year(self):
        assert _has_temporal_filter("How often did 7 come up this year?") is True

    def test_en_last_year(self):
        assert _has_temporal_filter("What numbers came up most last year?") is True

    def test_en_since(self):
        assert _has_temporal_filter("since 2023 how many times did 5 appear?") is True

    def test_en_last_month(self):
        assert _has_temporal_filter("which numbers appeared last month?") is True

    def test_en_in_january(self):
        assert _has_temporal_filter("how many times in january?") is True

    def test_en_between(self):
        assert _has_temporal_filter("between 2023 and 2024 how many draws?") is True

    def test_en_no_temporal(self):
        assert _has_temporal_filter("How many times did 12 appear?") is False

    # ── ES ──

    def test_es_en_2024(self):
        assert _has_temporal_filter("Cuántas veces salió el 12 en 2024?") is True

    def test_es_este_año(self):
        assert _has_temporal_filter("cuántas veces salió este año?") is True

    def test_es_desde(self):
        assert _has_temporal_filter("desde 2023 cuántas veces?") is True

    def test_es_en_enero(self):
        assert _has_temporal_filter("cuántas veces en enero?") is True

    # ── PT ──

    def test_pt_em_2024(self):
        assert _has_temporal_filter("Quantas vezes o 12 saiu em 2024?") is True

    def test_pt_este_ano(self):
        assert _has_temporal_filter("quantas vezes saiu este ano?") is True

    def test_pt_ano_passado(self):
        assert _has_temporal_filter("o que mais saiu o ano passado?") is True

    def test_pt_desde(self):
        assert _has_temporal_filter("desde 2023 quantas vezes?") is True

    def test_pt_em_janeiro(self):
        assert _has_temporal_filter("quantas vezes em janeiro?") is True

    def test_pt_no_temporal(self):
        assert _has_temporal_filter("Quantas vezes o 12 saiu?") is False

    # ── DE ──

    def test_de_im_jahr_2024(self):
        assert _has_temporal_filter("Wie oft kam die 12 im Jahr 2024?") is True

    def test_de_im_2024(self):
        assert _has_temporal_filter("Wie oft kam 12 im 2024?") is True

    def test_de_dieses_jahr(self):
        assert _has_temporal_filter("welche Zahlen kamen dieses Jahr?") is True

    def test_de_letztes_jahr(self):
        assert _has_temporal_filter("was kam am meisten letztes Jahr?") is True

    def test_de_seit(self):
        assert _has_temporal_filter("seit 2023 wie oft kam die 5?") is True

    def test_de_im_januar(self):
        assert _has_temporal_filter("wie oft im januar?") is True

    def test_de_no_temporal(self):
        assert _has_temporal_filter("Wie oft kam die 12?") is False

    # ── NL ──

    def test_nl_in_2024(self):
        assert _has_temporal_filter("Hoe vaak kwam 12 voor in 2024?") is True

    def test_nl_dit_jaar(self):
        assert _has_temporal_filter("welke nummers kwamen dit jaar?") is True

    def test_nl_vorig_jaar(self):
        assert _has_temporal_filter("wat kwam het meest vorig jaar?") is True

    def test_nl_sinds(self):
        assert _has_temporal_filter("sinds 2023 hoe vaak kwam 5?") is True

    def test_nl_in_januari(self):
        assert _has_temporal_filter("hoe vaak in januari?") is True

    def test_nl_no_temporal(self):
        assert _has_temporal_filter("Hoe vaak kwam 12 voor?") is False
