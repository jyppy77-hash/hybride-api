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
    _extract_grid_count, _extract_exclusions,
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

    # ── "depuis le [date]" / "since [month] [year]" patterns ──

    def test_fr_depuis_le_1er_janvier_2026(self):
        assert _has_temporal_filter("les 5 numéros les plus sortis depuis le 1er janvier 2026") is True

    def test_fr_depuis_janvier_2026(self):
        assert _has_temporal_filter("top 5 depuis janvier 2026") is True

    def test_fr_a_partir_de(self):
        assert _has_temporal_filter("numéros les plus fréquents à partir de février 2026") is True

    def test_fr_les_3_derniers_mois(self):
        assert _has_temporal_filter("les 3 derniers mois quels numéros ?") is True

    def test_en_since_january_2026(self):
        assert _has_temporal_filter("top 5 since January 2026") is True

    def test_en_from_march_2025(self):
        assert _has_temporal_filter("most drawn from March 2025") is True

    def test_en_last_3_months(self):
        assert _has_temporal_filter("most drawn in the last 3 months") is True

    def test_en_past_6_months(self):
        assert _has_temporal_filter("numbers in the past 6 months") is True

    def test_es_desde_el_1_de_enero(self):
        assert _has_temporal_filter("los 5 más sorteados desde el 1 de enero de 2026") is True

    def test_es_desde_enero_2026(self):
        assert _has_temporal_filter("top 5 desde enero 2026") is True

    def test_es_los_ultimos_3_meses(self):
        assert _has_temporal_filter("números más frecuentes los últimos 3 meses") is True

    def test_pt_desde_janeiro_2026(self):
        assert _has_temporal_filter("os mais sorteados desde janeiro 2026") is True

    def test_pt_os_ultimos_3_meses(self):
        assert _has_temporal_filter("números dos os últimos 3 meses") is True

    def test_de_seit_januar_2026(self):
        assert _has_temporal_filter("die häufigsten seit Januar 2026") is True

    def test_de_ab_maerz_2025(self):
        assert _has_temporal_filter("top 3 ab märz 2025") is True

    def test_de_die_letzten_3_monate(self):
        assert _has_temporal_filter("die letzten 3 monate welche Zahlen?") is True

    def test_nl_sinds_januari_2026(self):
        assert _has_temporal_filter("de meest getrokken sinds januari 2026") is True

    def test_nl_vanaf_maart_2025(self):
        assert _has_temporal_filter("top 3 vanaf maart 2025") is True

    def test_nl_de_laatste_3_maanden(self):
        assert _has_temporal_filter("nummers van de laatste 3 maanden") is True

    # ── Bug regression: "SEULEMENT" suffix must not break detection ──

    def test_fr_depuis_seulement_suffix(self):
        assert _has_temporal_filter("les 5 numéros les plus sortis depuis le 1er janvier 2026 SEULEMENT") is True

    def test_fr_top5_depuis_janvier_seulement(self):
        assert _has_temporal_filter("top 5 depuis janvier 2026 seulement") is True

    def test_en_since_only(self):
        assert _has_temporal_filter("top 5 since January 2026 only") is True

    def test_es_desde_solamente(self):
        assert _has_temporal_filter("top 5 desde enero 2026 solamente") is True


# ═══════════════════════════════════════════════════════════════════════
# V43 — Fuzzy continuation detection (typos, multi-word)
# ═══════════════════════════════════════════════════════════════════════

class TestFuzzyContinuation:
    """Catch typos and multi-word short continuations."""

    def test_vas_ymontre_les(self):
        """'vas ymontre les' — the exact typo from production."""
        assert _is_short_continuation("vas ymontre les") is True

    def test_vas_y_montre_les(self):
        """'vas y montre les' — correct spacing variant."""
        assert _is_short_continuation("vas y montre les") is True

    def test_oui_montre(self):
        """'oui montre' — two continuation words."""
        assert _is_short_continuation("oui montre") is True

    def test_montre_les(self):
        """'montre les' — verb + article."""
        assert _is_short_continuation("montre les") is True

    def test_go_ahead(self):
        """'go ahead' — English continuation."""
        assert _is_short_continuation("go ahead") is True

    def test_show_me(self):
        """'show me' — English continuation."""
        assert _is_short_continuation("show me") is True

    def test_si_dale(self):
        """'sí dale' — Spanish continuation."""
        assert _is_short_continuation("sí dale") is True

    def test_ja_zeig(self):
        """'ja zeig' — German continuation."""
        assert _is_short_continuation("ja zeig") is True

    def test_sim_mostra(self):
        """'sim mostra' — Portuguese continuation."""
        assert _is_short_continuation("sim mostra") is True

    def test_long_message_not_continuation(self):
        """Long message should NOT be continuation even if starts with keyword."""
        assert _is_short_continuation("oui je veux voir les statistiques complètes de tous les numéros") is False

    def test_exact_patterns_still_work(self):
        """Original exact patterns must still work."""
        assert _is_short_continuation("oui") is True
        assert _is_short_continuation("vas-y") is True
        assert _is_short_continuation("montre-moi") is True
        assert _is_short_continuation("je veux voir") is True
        assert _is_short_continuation("non") is True

    def test_six_words_not_continuation(self):
        """6+ words should NOT be fuzzy continuation."""
        assert _is_short_continuation("montre moi les stats du numéro") is False


class TestFuzzyContinuationDigitGuard:
    """V46: messages containing digits should NOT be treated as continuation,
    even if short and starting with a continuation word."""

    def test_oui_le_7_stp(self):
        """'oui le 7 stp' — number query, not continuation."""
        assert _is_short_continuation("oui le 7 stp") is False

    def test_ouais_le_42(self):
        """'ouais le 42' — number query."""
        assert _is_short_continuation("ouais le 42") is False

    def test_go_3_grilles(self):
        """'go 3 grilles' — grid count, not continuation."""
        assert _is_short_continuation("go 3 grilles") is False

    def test_non_le_13_please(self):
        """'non le 13 please' — number query."""
        assert _is_short_continuation("non le 13 please") is False

    def test_si_5_numeros(self):
        """'si 5 números' — Spanish number query."""
        assert _is_short_continuation("si 5 números") is False

    def test_ja_zeig_7(self):
        """'ja zeig 7' — German with number."""
        assert _is_short_continuation("ja zeig 7") is False

    def test_show_me_10(self):
        """'show me 10' — English with number."""
        assert _is_short_continuation("show me 10") is False

    def test_pure_continuation_still_works(self):
        """Continuations WITHOUT digits must still work."""
        assert _is_short_continuation("oui montre moi") is True
        assert _is_short_continuation("go ahead") is True
        assert _is_short_continuation("ja zeig mal") is True
        assert _is_short_continuation("sim mostra") is True

    def test_exact_patterns_with_digits_still_work(self):
        """Exact regex patterns containing digits should still match
        (the digit guard only applies to the fuzzy path)."""
        # Exact patterns are matched BEFORE the fuzzy check
        assert _is_short_continuation("oui") is True
        assert _is_short_continuation("non") is True

    def test_continue_sans_nombre(self):
        """'continue please' — no digit, should be continuation."""
        assert _is_short_continuation("continue please") is True


# ═══════════════════════════════════════════════════════════════════════
# V43-bis — Multi-grid count extraction
# ═══════════════════════════════════════════════════════════════════════

class TestExtractGridCount:
    """Extract number of grids requested from message."""

    def test_default_no_number(self):
        """No number mentioned → default 1."""
        assert _extract_grid_count("génère une grille") == 1

    def test_fr_3_grilles(self):
        """'3 grilles' → 3."""
        assert _extract_grid_count("donne-moi 3 grilles EuroMillions") == 3

    def test_fr_5_combinaisons(self):
        """'5 combinaisons' → 5."""
        assert _extract_grid_count("génère 5 combinaisons") == 5

    def test_en_3_grids(self):
        """'3 grids' → 3."""
        assert _extract_grid_count("generate 3 grids for me") == 3

    def test_en_2_combinations(self):
        """'2 combinations' → 2."""
        assert _extract_grid_count("give me 2 combinations") == 2

    def test_es_3_combinaciones(self):
        """'3 combinaciones' → 3."""
        assert _extract_grid_count("genera 3 combinaciones") == 3

    def test_pt_4_grelhas(self):
        """'4 grelhas' → 4."""
        assert _extract_grid_count("gera 4 grelhas") == 4

    def test_de_3_kombinationen(self):
        """'3 Kombinationen' → 3."""
        assert _extract_grid_count("generiere 3 Kombinationen") == 3

    def test_nl_2_combinaties(self):
        """'2 combinaties' → 2."""
        assert _extract_grid_count("genereer 2 combinaties") == 2

    def test_cap_at_5(self):
        """Requested > 5 → capped at 5."""
        assert _extract_grid_count("génère 10 grilles") == 5

    def test_zero_becomes_1(self):
        """0 grilles → 1 (minimum)."""
        assert _extract_grid_count("génère 0 grilles") == 1

    def test_single_grille(self):
        """'1 grille' → 1."""
        assert _extract_grid_count("génère 1 grille") == 1

    def test_en_3_euromillions_grids(self):
        """'3 EuroMillions grids' — word between number and keyword."""
        assert _extract_grid_count("Give me 3 EuroMillions grids") == 3

    def test_de_3_euromillions_kombinationen(self):
        """'3 EuroMillions Kombinationen' — word between."""
        assert _extract_grid_count("Gib mir 3 EuroMillions Kombinationen") == 3

    def test_nl_3_euromillions_combinaties(self):
        """'3 EuroMillions combinaties' — word between."""
        assert _extract_grid_count("Geef me 3 EuroMillions combinaties") == 3


# ═══════════════════════════════════════════════════════════════════════
# V43-bis — PT generation detection (grelha)
# ═══════════════════════════════════════════════════════════════════════

class TestGenerationMultilang:
    """Generation detection must work in all 6 languages."""

    def test_fr_generation(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Donne-moi 3 grilles EuroMillions") is True

    def test_en_generation(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Give me 3 EuroMillions grids") is True

    def test_pt_generation_grelhas(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Dá-me 3 grelhas EuroMillions") is True

    def test_pt_generation_long(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Dá-me 3 grelhas EuroMillions baseadas nos números mais frequentes dos últimos 12 meses") is True

    def test_es_generation(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Dame 3 combinaciones EuroMillions") is True

    def test_de_generation(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Gib mir 3 EuroMillions Kombinationen") is True

    def test_nl_generation(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Geef me 3 EuroMillions combinaties") is True

    def test_pt_cria_grelha(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Cria uma grelha otimizada") is True

    def test_pt_faz_me_grelha(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Faz-me uma grelha EuroMillions") is True


# ═══════════════════════════════════════════════════════════════════════
# V43-bis — Exclusion extraction
# ═══════════════════════════════════════════════════════════════════════

class TestExtractExclusions:
    """Extract exclusion constraints from generation requests."""

    def test_no_exclusions(self):
        """No exclusion keywords → empty."""
        result = _extract_exclusions("génère une grille EuroMillions")
        assert result["exclude_ranges"] == []
        assert result["exclude_multiples"] == []
        assert result["exclude_nums"] == []

    def test_birthdays_fr(self):
        """'pas de dates de naissance' → range (1, 31)."""
        result = _extract_exclusions("pas de dates de naissance")
        assert (1, 31) in result["exclude_ranges"]

    def test_birthdays_en(self):
        """'no birthdays' → range (1, 31)."""
        result = _extract_exclusions("no birthdays please")
        assert (1, 31) in result["exclude_ranges"]

    def test_birthdays_es(self):
        """'sin fechas de nacimiento' → range (1, 31)."""
        result = _extract_exclusions("sin fechas de nacimiento")
        assert (1, 31) in result["exclude_ranges"]

    def test_birthdays_pt(self):
        """'sem datas de nascimento' → range (1, 31)."""
        result = _extract_exclusions("sem datas de nascimento")
        assert (1, 31) in result["exclude_ranges"]

    def test_birthdays_de(self):
        """'keine Geburtstage' → range (1, 31)."""
        result = _extract_exclusions("keine Geburtstage bitte")
        assert (1, 31) in result["exclude_ranges"]

    def test_birthdays_nl(self):
        """'geen verjaardagen' → range (1, 31)."""
        result = _extract_exclusions("geen verjaardagen alsjeblieft")
        assert (1, 31) in result["exclude_ranges"]

    def test_multiples_of_5_fr(self):
        """'pas de multiples de 5' → exclude_multiples [5]."""
        result = _extract_exclusions("pas de multiples de 5")
        assert 5 in result["exclude_multiples"]

    def test_multiples_of_5_and_10_fr(self):
        """'pas de multiples de 5 ou 10' → [5, 10]."""
        result = _extract_exclusions("pas de multiples de 5 ou 10")
        assert 5 in result["exclude_multiples"]
        assert 10 in result["exclude_multiples"]

    def test_multiples_en(self):
        """'no multiples of 5' → [5]."""
        result = _extract_exclusions("no multiples of 5")
        assert 5 in result["exclude_multiples"]

    def test_multiples_de(self):
        """'keine Vielfachen von 5' → [5]."""
        result = _extract_exclusions("keine Vielfachen von 5")
        assert 5 in result["exclude_multiples"]

    def test_exclude_range_fr(self):
        """'rien entre 1 et 31' → range (1, 31)."""
        result = _extract_exclusions("rien entre 1 et 31")
        assert (1, 31) in result["exclude_ranges"]

    def test_exclude_range_en(self):
        """'nothing between 1 and 31' → range (1, 31)."""
        result = _extract_exclusions("nothing between 1 and 31")
        assert (1, 31) in result["exclude_ranges"]

    def test_combined_fr(self):
        """Combined: birthdays + multiples of 5."""
        msg = "pas de dates de naissance, pas de multiples de 5 ou 10"
        result = _extract_exclusions(msg)
        assert (1, 31) in result["exclude_ranges"]
        assert 5 in result["exclude_multiples"]
        assert 10 in result["exclude_multiples"]

    def test_exclude_specific_num_fr(self):
        """'sans le 13' → exclude_nums [13]."""
        result = _extract_exclusions("sans le 13")
        assert 13 in result["exclude_nums"]

    def test_full_anticlassique_fr(self):
        """Full anti-classic request."""
        msg = "grille anti-classique : pas de dates de naissance, pas de multiples de 5 ou 10"
        result = _extract_exclusions(msg)
        assert (1, 31) in result["exclude_ranges"]
        assert 5 in result["exclude_multiples"]
        assert 10 in result["exclude_multiples"]
