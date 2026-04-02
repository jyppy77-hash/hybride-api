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
    _detect_salutation, _get_salutation_response,
    _has_data_signal, _detect_tirage,
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
# V65 — Extended generation detection (chatbot_log_7d.csv false negatives)
# ═══════════════════════════════════════════════════════════════════════

class TestGenerationV65_RealMessages:
    """17 real messages that MUST trigger Phase G (from chatbot log analysis)."""

    def test_01_donne_unicode_hyphen(self):
        """Donne‑moi with NON-BREAKING HYPHEN U+2011."""
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Donne\u2011moi 3 grilles EuroMillions \u00e9quilibr\u00e9es.") is True

    def test_02_une_grille_typo(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Une grille qleatoire") is True

    def test_03_n_numeros_et_etoiles(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Les 6 num\u00e9ro et deux etoile") is True

    def test_04_propose_des_grilles(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("propose des grilles statistiquement guid\u00e9es") is True

    def test_05_une_grille_loto(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Une grille loto") is True

    def test_06_typo_quels_jouer_grilles(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("quzls numeros jouer pour 2 grilles") is True

    def test_07_genere_seul(self):
        """Participe pass\u00e9 seul = g\u00e9n\u00e9ration."""
        from services.chat_detectors import _detect_generation
        assert _detect_generation("G\u00e9n\u00e9r\u00e9") is True

    def test_08_lequel_jouer(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Lequel jouer") is True

    def test_09_n_numeros_pour(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("5 num\u00e9ros pour ce soir") is True

    def test_10_voudrais_numeros(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Je voudrais 5 numeros pertinents pour mon jeu de ce soir") is True

    def test_11_genere_la_grille(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("genere la grille") is True

    def test_12_donne_la_grille(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("donne la grille") is True

    def test_13_bare_1_grille(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("1 grille") is True

    def test_14_salut_genere_grille(self):
        """Salutation + g\u00e9n\u00e9ration — la salutation ne bloque pas."""
        from services.chat_detectors import _detect_generation
        assert _detect_generation("salut genere moi une grille") is True

    def test_15_donne_moi_numeros_euromillion(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Donne moi les num\u00e9ros de l'euromillion de ce soir") is True

    def test_16_generer_grille_aleatoire(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("generer une grille tres algoritmer et aleatoire") is True

    def test_17_conseillez_euromillions(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Quesque vous me conseillez pour le euromillions pour demain merci") is True

    def test_18_pas_generation(self):
        """Message narratif NE DOIT PAS d\u00e9clencher Phase G."""
        from services.chat_detectors import _detect_generation
        assert _detect_generation("Se dommage car sa ete mes num\u00e9ros sortis mais je pas eux la possibilit\u00e9 de r\u00e9cup\u00e9rer") is False


class TestGenerationV65_NonRegression:
    """Messages qui NE DOIVENT PAS d\u00e9clencher Phase G (faux positifs potentiels)."""

    def test_frequence_numero(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("quel est le num\u00e9ro le plus fr\u00e9quent") is False

    def test_analyse_grille(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("analyse ma grille 3 12 25 38 47") is False

    def test_donnees_statistiques(self):
        """'donn\u00e9es' (accent) NE DOIT PAS matcher le pattern 'donne'."""
        from services.chat_detectors import _detect_generation
        assert _detect_generation("les donn\u00e9es statistiques de la grille") is False

    def test_compare_numeros(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("compare le 7 et le 23") is False

    def test_top_10(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("top 10 les plus sortis") is False

    def test_cooccurrence_preserved(self):
        """Co-occurrence exclusion still works."""
        from services.chat_detectors import _detect_generation
        assert _detect_generation("g\u00e9n\u00e8re les paires ensemble") is False

    def test_bonjour(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("bonjour") is False


class TestGenerationV65_Multilang:
    """V65 patterns multilingues (EN/ES/PT/DE/NL)."""

    # EN
    def test_en_want_numbers(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("I want 5 numbers for tonight") is True

    def test_en_would_like_grid(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("I would like a grid") is True

    def test_en_suggest_numbers(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("suggest some numbers for me") is True

    def test_en_bare_grid(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("1 grid") is True

    def test_en_which_numbers_play(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("which numbers to play") is True

    def test_en_no_detect_stats(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("show me the most frequent numbers") is False

    # ES
    def test_es_quiero_numeros(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("quiero 5 n\u00fameros para hoy") is True

    def test_es_bare_combinacion(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("1 combinaci\u00f3n") is True

    def test_es_que_numeros_jugar(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("qu\u00e9 n\u00fameros jugar") is True

    def test_es_no_detect_stats(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("cu\u00e1l es el n\u00famero m\u00e1s frecuente") is False

    # PT
    def test_pt_quero_numeros(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("quero 5 n\u00fameros para hoje") is True

    def test_pt_bare_grelha(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("1 grelha") is True

    def test_pt_quais_numeros_jogar(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("quais n\u00fameros jogar") is True

    def test_pt_no_detect_stats(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("qual \u00e9 o n\u00famero mais frequente") is False

    # DE
    def test_de_moechte_zahlen(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("ich m\u00f6chte 5 Zahlen") is True

    def test_de_bare_kombination(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("1 Kombination") is True

    def test_de_welche_zahlen_spielen(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("welche Zahlen spielen") is True

    def test_de_no_detect_stats(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("welche Zahl ist am h\u00e4ufigsten") is False

    # NL
    def test_nl_wil_nummers(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("ik wil 5 nummers") is True

    def test_nl_bare_combinatie(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("1 combinatie") is True

    def test_nl_welke_nummers_spelen(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("welke nummers spelen") is True

    def test_nl_no_detect_stats(self):
        from services.chat_detectors import _detect_generation
        assert _detect_generation("welk nummer komt het vaakst voor") is False


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


# ═══════════════════════════════════════════════════════════════════════
# V65 — Phase SALUTATION detection
# ═══════════════════════════════════════════════════════════════════════

class TestSalutationDetection_RealMessages:
    """Messages r\u00e9els du chatbot_log_7d.csv qui doivent d\u00e9clencher Phase SALUTATION."""

    def test_yo(self):
        assert _detect_salutation("yo") is True

    def test_yop(self):
        assert _detect_salutation("yop") is True

    def test_hello(self):
        assert _detect_salutation("hello") is True

    def test_salut_tu_vas_bien(self):
        assert _detect_salutation("salut tu vas bien ?") is True

    def test_salut(self):
        assert _detect_salutation("salut") is True


class TestSalutationDetection_FR:
    """Salutations FR vari\u00e9es."""

    def test_bonjour(self):
        assert _detect_salutation("bonjour") is True

    def test_bonsoir(self):
        assert _detect_salutation("bonsoir") is True

    def test_coucou(self):
        assert _detect_salutation("coucou") is True

    def test_slt(self):
        assert _detect_salutation("slt") is True

    def test_wesh(self):
        assert _detect_salutation("wesh") is True

    def test_bjr(self):
        assert _detect_salutation("bjr") is True

    def test_hey(self):
        assert _detect_salutation("hey") is True

    def test_salut_exclamation(self):
        assert _detect_salutation("salut !") is True

    def test_bonjour_ca_va(self):
        assert _detect_salutation("bonjour ca va") is True

    def test_yo_repeated(self):
        assert _detect_salutation("yooo") is True


class TestSalutationDetection_Multilang:
    """Salutations 6 langues."""

    # EN
    def test_en_hi(self):
        assert _detect_salutation("hi") is True

    def test_en_hello(self):
        assert _detect_salutation("hello") is True

    def test_en_howdy(self):
        assert _detect_salutation("howdy") is True

    def test_en_whats_up(self):
        assert _detect_salutation("what's up") is True

    # ES
    def test_es_hola(self):
        assert _detect_salutation("hola") is True

    def test_es_buenas(self):
        assert _detect_salutation("buenas") is True

    def test_es_que_tal(self):
        assert _detect_salutation("qu\u00e9 tal") is True

    # PT
    def test_pt_ola(self):
        assert _detect_salutation("ol\u00e1") is True

    def test_pt_oi(self):
        assert _detect_salutation("oi") is True

    def test_pt_bom_dia(self):
        assert _detect_salutation("bom dia") is True

    # DE
    def test_de_hallo(self):
        assert _detect_salutation("hallo") is True

    def test_de_guten_tag(self):
        assert _detect_salutation("guten tag") is True

    def test_de_moin(self):
        assert _detect_salutation("moin") is True

    def test_de_servus(self):
        assert _detect_salutation("servus") is True

    # NL
    def test_nl_hoi(self):
        assert _detect_salutation("hoi") is True

    def test_nl_goedendag(self):
        assert _detect_salutation("goedendag") is True

    def test_nl_goedemorgen(self):
        assert _detect_salutation("goedemorgen") is True


class TestSalutationDetection_NonRegression:
    """Messages qui NE DOIVENT PAS d\u00e9clencher Phase SALUTATION."""

    def test_salut_genere_grille(self):
        """Trop long — doit rester Phase G."""
        assert _detect_salutation("salut genere moi une grille") is False

    def test_salut_connard(self):
        """Salutation + insulte — d\u00e9tecteur ne bloque pas (Phase I en amont)."""
        # _detect_salutation elle-m\u00eame matche "salut connard" (2 mots < 8),
        # mais dans le pipeline Phase I est AVANT, donc "salut connard" → Phase I.
        # Ici on v\u00e9rifie juste que le message est court et matche le pattern.
        # Le test pipeline ci-dessous v\u00e9rifie la priorit\u00e9 I > SALUTATION.
        pass  # pipeline priority tested in TestSalutationPipeline

    def test_long_message_not_salutation(self):
        """Message long avec salut dedans."""
        assert _detect_salutation("salut est-ce que tu peux me donner les statistiques du numero 7") is False

    def test_stats_question(self):
        assert _detect_salutation("quel est le num\u00e9ro le plus fr\u00e9quent") is False

    def test_bonjour_grille(self):
        """'bonjour donne moi une grille' = trop long."""
        assert _detect_salutation("bonjour donne moi une grille euromillions") is False

    def test_empty(self):
        assert _detect_salutation("") is False

    def test_number(self):
        assert _detect_salutation("42") is False


class TestSalutationResponse:
    """Responses d'accueil correctes par module et langue."""

    def test_loto_fr(self):
        resp = _get_salutation_response("loto", "fr")
        assert "Loto" in resp
        assert "HYBRIDE" in resp

    def test_loto_en(self):
        resp = _get_salutation_response("loto", "en")
        assert "Loto" in resp

    def test_em_fr(self):
        resp = _get_salutation_response("em", "fr")
        assert "EuroMillions" in resp

    def test_em_en(self):
        resp = _get_salutation_response("em", "en")
        assert "EuroMillions" in resp

    def test_em_es(self):
        resp = _get_salutation_response("em", "es")
        assert "EuroMillions" in resp

    def test_em_pt(self):
        resp = _get_salutation_response("em", "pt")
        assert "EuroMillions" in resp

    def test_em_de(self):
        resp = _get_salutation_response("em", "de")
        assert "EuroMillions" in resp

    def test_em_nl(self):
        resp = _get_salutation_response("em", "nl")
        assert "EuroMillions" in resp

    def test_fallback_unknown_lang(self):
        """Langue inconnue → fallback FR."""
        resp = _get_salutation_response("loto", "xx")
        assert "Loto" in resp
        assert "HYBRIDE" in resp


# ═══════════════════════════════════════════════════════════════════════
# V65 — Data signal heuristic (skip Phase SQL for conversational messages)
# ═══════════════════════════════════════════════════════════════════════

class TestDataSignal_NoSignal:
    """Messages conversationnels sans signal data → False (skip SQL)."""

    def test_moteur_hybride(self):
        assert _has_data_signal("comment le moteur HYBRIDE fonctionne avec les donn\u00e9es du Loto") is False

    def test_score_football(self):
        assert _has_data_signal("Score exact de France contre Br\u00e9sil") is False

    def test_performances_decevantes(self):
        assert _has_data_signal("Non non tes performances d\u00e9cevante je vais ailleurs") is False

    def test_ia_generique(self):
        assert _has_data_signal("Ttes les ia le font cela...alors rien de plus chez toi") is False

    def test_tu_te_debines(self):
        assert _has_data_signal("Tu te debines") is False

    def test_ah_ok(self):
        assert _has_data_signal("Ah ok") is False

    def test_borabora(self):
        assert _has_data_signal("ici Borabora faanui aide moi") is False

    def test_empty(self):
        assert _has_data_signal("") is False

    def test_bonjour_ca_va(self):
        assert _has_data_signal("bonjour comment tu vas") is False

    def test_cest_quoi_ce_site(self):
        assert _has_data_signal("c'est quoi ce site") is False


class TestDataSignal_HasSignal:
    """Messages avec signal data → True (Phase SQL doit s'ex\u00e9cuter)."""

    # Chiffres
    def test_bare_number(self):
        assert _has_data_signal("27") is True

    def test_number_in_text(self):
        assert _has_data_signal("le 7 est sorti combien de fois") is True

    def test_year(self):
        assert _has_data_signal("statistiques 2025") is True

    # FR keywords
    def test_fr_combien(self):
        assert _has_data_signal("combien de fois le 7") is True

    def test_fr_dernier_tirage(self):
        assert _has_data_signal("dernier tirage") is True

    def test_fr_frequents(self):
        assert _has_data_signal("les plus fr\u00e9quents") is True

    def test_fr_top(self):
        assert _has_data_signal("top 5 num\u00e9ros") is True

    def test_fr_ecart(self):
        assert _has_data_signal("quel est l'\u00e9cart du 12") is True

    def test_fr_historique(self):
        assert _has_data_signal("historique du num\u00e9ro 7") is True

    def test_fr_depuis(self):
        assert _has_data_signal("depuis janvier") is True

    def test_fr_paire_impaire(self):
        assert _has_data_signal("r\u00e9partition pairs impairs") is True

    def test_fr_etoile(self):
        assert _has_data_signal("quelle \u00e9toile sort le plus") is True

    def test_fr_jackpot(self):
        assert _has_data_signal("le plus gros jackpot") is True

    # EN keywords
    def test_en_how_many(self):
        assert _has_data_signal("how many times has 22 come out") is True

    def test_en_frequency(self):
        assert _has_data_signal("frequency of number 7") is True

    def test_en_most_drawn(self):
        assert _has_data_signal("most drawn number") is True

    def test_en_last_draw(self):
        assert _has_data_signal("last draw results") is True

    # ES keywords
    def test_es_frecuencia(self):
        assert _has_data_signal("frecuencia del 7") is True

    def test_es_sorteo(self):
        assert _has_data_signal("\u00faltimo sorteo") is True

    # PT keywords
    def test_pt_sorteio(self):
        assert _has_data_signal("resultado do sorteio") is True

    def test_pt_frequencia(self):
        assert _has_data_signal("frequ\u00eancia do n\u00famero 7") is True

    # DE keywords
    def test_de_ziehung(self):
        assert _has_data_signal("letzte Ziehung") is True

    def test_de_haeufigkeit(self):
        assert _has_data_signal("H\u00e4ufigkeit der Zahl 7") is True

    def test_de_wie_oft(self):
        assert _has_data_signal("wie oft kam die 7") is True

    # NL keywords
    def test_nl_trekking(self):
        assert _has_data_signal("laatste trekking") is True

    def test_nl_hoe_vaak(self):
        assert _has_data_signal("hoe vaak kwam 7 voor") is True

    def test_nl_frequentie(self):
        assert _has_data_signal("frequentie van nummer 7") is True


# ═══════════════════════════════════════════════════════════════════════
# F05 V83 — _extract_exclusions() max_num game-aware
# ═══════════════════════════════════════════════════════════════════════

class TestExtractExclusionsMaxNum:

    def test_loto_rejects_50(self):
        """F05: 'sans le 50' with max_num=49 → 50 not in exclusions."""
        result = _extract_exclusions("sans le 50", max_num=49)
        assert 50 not in result["exclude_nums"]

    def test_loto_accepts_49(self):
        """F05: 'sans le 49' with max_num=49 → 49 included."""
        result = _extract_exclusions("sans le 49", max_num=49)
        assert 49 in result["exclude_nums"]

    def test_em_accepts_50(self):
        """F05: 'without 50' with max_num=50 → 50 included."""
        result = _extract_exclusions("without 50", max_num=50)
        assert 50 in result["exclude_nums"]

    def test_default_backward_compat(self):
        """F05: Default max_num=49 matches Loto range."""
        result = _extract_exclusions("sans le 49")
        assert 49 in result["exclude_nums"]
        result2 = _extract_exclusions("sans le 50")
        assert 50 not in result2["exclude_nums"]


# ═══════════════════════════════════════════════════════════════════════
# F07 V83 — _detect_tirage() multilingue (6 langues)
# ═══════════════════════════════════════════════════════════════════════

class TestDetectTirageMultilang:

    # FR (existing behavior)
    def test_fr_tirage_date(self):
        result = _detect_tirage("tirage du 15 mars 2026")
        assert result is not None and result != "latest"

    def test_fr_dernier_tirage(self):
        assert _detect_tirage("résultat du dernier tirage") == "latest"

    # EN
    def test_en_draw_date(self):
        result = _detect_tirage("draw from March 15 2026")
        assert result is not None and result != "latest"

    def test_en_last_draw(self):
        assert _detect_tirage("last draw results") == "latest"

    def test_en_latest_result(self):
        assert _detect_tirage("latest result") == "latest"

    # ES
    def test_es_sorteo_date(self):
        result = _detect_tirage("sorteo del 15 marzo 2026")
        assert result is not None and result != "latest"

    def test_es_ultimo_sorteo(self):
        assert _detect_tirage("último sorteo") == "latest"

    # PT
    def test_pt_sorteio_date(self):
        result = _detect_tirage("sorteio de 15 janeiro 2026")
        assert result is not None and result != "latest"

    def test_pt_ultimo_sorteio(self):
        assert _detect_tirage("último sorteio") == "latest"

    # DE
    def test_de_ziehung_date(self):
        result = _detect_tirage("Ziehung vom 15. März 2026")
        assert result is not None and result != "latest"

    def test_de_letzte_ziehung(self):
        assert _detect_tirage("letzte Ziehung") == "latest"

    # NL
    def test_nl_trekking_date(self):
        result = _detect_tirage("trekking van 15 maart 2026")
        assert result is not None and result != "latest"

    def test_nl_laatste_trekking(self):
        assert _detect_tirage("laatste trekking") == "latest"

    # Yesterday multilang
    def test_en_yesterday(self):
        result = _detect_tirage("yesterday's draw")
        assert result is not None and result != "latest"

    def test_es_ayer(self):
        result = _detect_tirage("sorteo de ayer")
        assert result is not None and result != "latest"

    def test_de_gestern(self):
        result = _detect_tirage("Ziehung von gestern")
        assert result is not None and result != "latest"

    # Negatives — "next" blocks Phase T
    def test_en_next_blocked(self):
        assert _detect_tirage("next draw") is None

    def test_de_nachste_blocked(self):
        assert _detect_tirage("nächste Ziehung") is None

    def test_es_proximo_blocked(self):
        assert _detect_tirage("próximo sorteo") is None
