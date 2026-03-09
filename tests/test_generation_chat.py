"""
Tests unitaires pour Phase G — detection generation de grilles + format context.
Couvre _detect_generation, _detect_generation_mode, exclusion Phase A,
_format_generation_context, _format_generation_context_em.
"""

import pytest

from services.chat_detectors import (
    _detect_generation, _detect_generation_mode, _detect_argent,
    _detect_cooccurrence_high_n, _get_cooccurrence_high_n_response,
)
from services.chat_detectors_em import _detect_argent_em
from services.chat_utils import _format_generation_context, _clean_response
from services.chat_utils_em import _format_generation_context_em


# ═══════════════════════════════════════════════════════════════════════
# _detect_generation — TRUE (demandes legit de generation)
# ═══════════════════════════════════════════════════════════════════════

class TestDetectGenerationPositive:
    """Demandes de generation qui DOIVENT matcher."""

    def test_fr_genere_grille(self):
        assert _detect_generation("génère-moi une grille") is True

    def test_fr_genere_sans_accent(self):
        assert _detect_generation("genere-moi une grille") is True

    def test_fr_donne_combinaison_optimisee(self):
        assert _detect_generation("donne-moi une combinaison optimisée") is True

    def test_fr_propose_numeros(self):
        assert _detect_generation("propose-moi des numéros") is True

    def test_fr_cree_grille_equilibree(self):
        assert _detect_generation("crée-moi une grille équilibrée") is True

    def test_fr_fais_grille(self):
        assert _detect_generation("fais-moi une grille") is True

    def test_fr_grille_optimisee(self):
        assert _detect_generation("je veux une grille optimisée") is True

    def test_fr_choisis_numeros(self):
        assert _detect_generation("choisis-moi des numéros") is True

    def test_fr_tire_numeros(self):
        assert _detect_generation("tire-moi des numéros") is True

    def test_en_generate_grid(self):
        assert _detect_generation("generate an optimized grid") is True

    def test_en_give_me_numbers(self):
        assert _detect_generation("give me some numbers for EuroMillions") is True

    def test_en_create_combination(self):
        assert _detect_generation("create a combination for me") is True

    def test_en_make_grid(self):
        assert _detect_generation("make me a grid") is True

    def test_en_pick_numbers(self):
        assert _detect_generation("pick some numbers for me") is True

    def test_es_genera_combinacion(self):
        assert _detect_generation("genera una combinación") is True

    def test_es_dame_numeros(self):
        assert _detect_generation("dame una combinación optimizada") is True

    def test_es_hazme_combinacion(self):
        assert _detect_generation("hazme una combinación") is True

    def test_pt_gera_combinacao(self):
        assert _detect_generation("gera uma combinação") is True

    def test_pt_da_me_numeros(self):
        assert _detect_generation("dá-me uma combinação") is True

    def test_pt_cria_combinacao(self):
        assert _detect_generation("cria uma combinação optimizada") is True

    def test_de_generier_kombination(self):
        assert _detect_generation("generier mir eine Kombination") is True

    def test_de_gib_mir_zahlen(self):
        assert _detect_generation("gib mir eine Kombination") is True

    def test_de_erstell_kombination(self):
        assert _detect_generation("erstelle eine Kombination") is True

    def test_nl_genereer_combinatie(self):
        assert _detect_generation("genereer een combinatie") is True

    def test_nl_geef_me_nummers(self):
        assert _detect_generation("geef me een combinatie") is True

    def test_nl_maak_combinatie(self):
        assert _detect_generation("maak een combinatie voor mij") is True


# ═══════════════════════════════════════════════════════════════════════
# _detect_generation — FALSE (PAS des demandes de generation)
# ═══════════════════════════════════════════════════════════════════════

class TestDetectGenerationNegative:
    """Messages qui ne doivent PAS matcher la generation."""

    def test_stats_numero(self):
        assert _detect_generation("le 7 est sorti combien de fois") is False

    def test_jackpot(self):
        assert _detect_generation("combien vaut le jackpot") is False

    def test_devenir_riche(self):
        assert _detect_generation("je veux devenir riche") is False

    def test_simple_question(self):
        assert _detect_generation("quelle est la fréquence du 42 ?") is False

    def test_bonjour(self):
        assert _detect_generation("bonjour") is False

    def test_prochain_tirage(self):
        assert _detect_generation("c'est quand le prochain tirage ?") is False

    def test_es_genera_sans_contexte(self):
        """'genera' seul sans contexte grille ne doit pas matcher."""
        assert _detect_generation("genera problemas") is False

    def test_pt_gera_sans_contexte(self):
        """'gera' seul sans contexte grille ne doit pas matcher."""
        assert _detect_generation("gera conflito") is False


# ═══════════════════════════════════════════════════════════════════════
# _detect_generation_mode
# ═══════════════════════════════════════════════════════════════════════

class TestDetectGenerationMode:

    def test_default_balanced(self):
        assert _detect_generation_mode("génère-moi une grille") == "balanced"

    def test_conservative(self):
        assert _detect_generation_mode("grille conservative") == "conservative"

    def test_prudent(self):
        assert _detect_generation_mode("grille prudente") == "conservative"

    def test_recent(self):
        assert _detect_generation_mode("grille basée sur les tendances récentes") == "recent"

    def test_trend(self):
        assert _detect_generation_mode("generate a trend-based grid") == "recent"


# ═══════════════════════════════════════════════════════════════════════
# Phase A exclusion — _detect_argent ne bloque PAS les generations
# ═══════════════════════════════════════════════════════════════════════

class TestArgentExcludesGeneration:
    """Phase A ne doit PAS bloquer les demandes de generation."""

    def test_genere_grille_optimisee_loto(self):
        """Demande generation ne doit PAS declencher Phase A Loto."""
        assert _detect_argent("génère-moi une grille optimisée") is False

    def test_donne_combinaison_loto(self):
        assert _detect_argent("donne-moi une combinaison") is False

    def test_generate_grid_em_en(self):
        """Demande generation ne doit PAS declencher Phase A EM."""
        assert _detect_argent_em("generate an optimized grid", "en") is False

    def test_genera_combinacion_em_es(self):
        assert _detect_argent_em("genera una combinación", "es") is False

    def test_devenir_riche_toujours_bloque(self):
        """Les vrais cas argent doivent TOUJOURS etre bloques."""
        assert _detect_argent("je veux devenir riche") is True

    def test_jackpot_toujours_bloque(self):
        assert _detect_argent("combien vaut le jackpot") is True

    def test_parier_toujours_bloque(self):
        assert _detect_argent("je veux parier") is True

    def test_get_rich_em_toujours_bloque(self):
        assert _detect_argent_em("I want to get rich", "en") is True

    def test_hacerse_rico_em_toujours_bloque(self):
        assert _detect_argent_em("quiero hacerme rico", "es") is True


# ═══════════════════════════════════════════════════════════════════════
# _format_generation_context (Loto)
# ═══════════════════════════════════════════════════════════════════════

class TestFormatGenerationContext:

    def test_contains_tag(self):
        ctx = _format_generation_context({
            "nums": [3, 12, 25, 33, 47],
            "chance": 7,
            "score": 85,
            "badges": ["Équilibré", "Pair/Impair OK", "Hybride V1"],
            "mode": "balanced",
        })
        assert "[GRILLE GÉNÉRÉE PAR HYBRIDE]" in ctx

    def test_contains_nums(self):
        ctx = _format_generation_context({
            "nums": [3, 12, 25, 33, 47],
            "chance": 7,
            "score": 85,
            "badges": ["Équilibré"],
            "mode": "balanced",
        })
        assert "[3, 12, 25, 33, 47]" in ctx

    def test_contains_chance(self):
        ctx = _format_generation_context({
            "nums": [3, 12, 25, 33, 47],
            "chance": 7,
            "score": 85,
            "badges": [],
            "mode": "balanced",
        })
        assert "7" in ctx

    def test_contains_score(self):
        ctx = _format_generation_context({
            "nums": [3, 12, 25, 33, 47],
            "chance": 7,
            "score": 85,
            "badges": [],
            "mode": "balanced",
        })
        assert "85/100" in ctx

    def test_contains_hasard_warning(self):
        ctx = _format_generation_context({
            "nums": [3, 12, 25, 33, 47],
            "chance": 7,
            "score": 85,
            "badges": [],
            "mode": "balanced",
        })
        assert "hasard" in ctx


# ═══════════════════════════════════════════════════════════════════════
# _format_generation_context_em (EuroMillions)
# ═══════════════════════════════════════════════════════════════════════

class TestFormatGenerationContextEM:

    def test_contains_tag(self):
        ctx = _format_generation_context_em({
            "nums": [5, 14, 28, 37, 49],
            "etoiles": [3, 11],
            "score": 78,
            "badges": ["Numéros chauds", "Hybride EM V1"],
            "mode": "recent",
        })
        assert "[GRILLE GÉNÉRÉE PAR HYBRIDE]" in ctx

    def test_contains_etoiles(self):
        ctx = _format_generation_context_em({
            "nums": [5, 14, 28, 37, 49],
            "etoiles": [3, 11],
            "score": 78,
            "badges": [],
            "mode": "recent",
        })
        assert "Étoiles" in ctx
        assert "[3, 11]" in ctx

    def test_no_etoiles_if_missing(self):
        ctx = _format_generation_context_em({
            "nums": [5, 14, 28, 37, 49],
            "score": 78,
            "badges": [],
            "mode": "recent",
        })
        assert "Étoiles" not in ctx

    def test_contains_mode(self):
        ctx = _format_generation_context_em({
            "nums": [5, 14, 28, 37, 49],
            "etoiles": [3, 11],
            "score": 78,
            "badges": [],
            "mode": "conservative",
        })
        assert "conservative" in ctx


# ═══════════════════════════════════════════════════════════════════════
# _clean_response — tag nettoyage
# ═══════════════════════════════════════════════════════════════════════

class TestCleanResponseGenerationTag:

    def test_strips_generation_tag(self):
        text = "[GRILLE GÉNÉRÉE PAR HYBRIDE]\nVoici ta grille !"
        cleaned = _clean_response(text)
        assert "[GRILLE GÉNÉRÉE PAR HYBRIDE]" not in cleaned
        assert "Voici ta grille" in cleaned

    def test_strips_generation_tag_no_accent(self):
        text = "[GRILLE GENEREE PAR HYBRIDE]\nVoici ta grille !"
        cleaned = _clean_response(text)
        assert "[GRILLE GENEREE PAR HYBRIDE]" not in cleaned


# ═══════════════════════════════════════════════════════════════════════
# _detect_generation — co-occurrence exclusion (Phase P priority)
# ═══════════════════════════════════════════════════════════════════════

class TestGenerationCooccurrenceExclusion:
    """Phase G must NOT fire when co-occurrence keywords are present."""

    def test_fr_donne_numeros_ensemble(self):
        assert _detect_generation("donne-moi les 5 numéros sortis ensemble") is False

    def test_fr_donne_numeros_associes(self):
        assert _detect_generation("donne-moi les numéros associés") is False

    def test_fr_propose_numeros_correles(self):
        assert _detect_generation("propose-moi les numéros en corrélation") is False

    def test_en_give_numbers_together(self):
        assert _detect_generation("give me the 5 numbers that came together") is False

    def test_en_give_numbers_correlation(self):
        assert _detect_generation("give me numbers with correlation") is False

    def test_es_dame_numeros_juntos(self):
        assert _detect_generation("dame los números juntos") is False

    def test_pt_da_me_numeros_associados(self):
        assert _detect_generation("dá-me os números associados") is False

    def test_de_gib_zahlen_zusammen(self):
        assert _detect_generation("gib mir die Zahlen die zusammen kommen") is False

    def test_nl_geef_nummers_samen(self):
        assert _detect_generation("geef me de nummers die samen voorkomen") is False

    def test_fr_paire_donne(self):
        assert _detect_generation("donne-moi les paires fréquentes") is False

    def test_fr_duo_propose(self):
        assert _detect_generation("propose-moi les duos qui sortent") is False

    def test_legit_generation_still_works(self):
        """Normal generation requests must still pass."""
        assert _detect_generation("donne-moi une grille optimisée") is True
        assert _detect_generation("give me some numbers for EuroMillions") is True
        assert _detect_generation("propose-moi des numéros") is True
        assert _detect_generation("génère-moi une grille") is True


# ═══════════════════════════════════════════════════════════════════════
# Phase P+ — _detect_cooccurrence_high_n (N>3)
# ═══════════════════════════════════════════════════════════════════════

class TestDetectCooccurrenceHighN:
    """Detection of co-occurrence requests for 4+ numbers (6 languages)."""

    # --- TRUE: N>3 requests ---

    def test_fr_5_numeros_ensemble(self):
        assert _detect_cooccurrence_high_n("5 numéros ensemble le plus souvent")

    def test_fr_5_numeros_qui_sortent_ensemble(self):
        assert _detect_cooccurrence_high_n("5 numéros qui sortent ensemble")

    def test_fr_5_numeros_sortis_ensemble(self):
        assert _detect_cooccurrence_high_n("5 numéros qui sont sortis ensemble")

    def test_fr_4_numeros(self):
        assert _detect_cooccurrence_high_n("4 numéros qui sortent ensemble")

    def test_fr_combinaison_de_5(self):
        assert _detect_cooccurrence_high_n("combinaison de 5 numéros")

    def test_fr_groupe_de_5(self):
        assert _detect_cooccurrence_high_n("groupe de 5 numéros")

    def test_fr_quadruplet(self):
        assert _detect_cooccurrence_high_n("les quadruplets les plus fréquents")

    def test_fr_quintuplet(self):
        assert _detect_cooccurrence_high_n("quintuplet de numéros")

    def test_fr_5_boules_ensemble(self):
        assert _detect_cooccurrence_high_n("5 boules ensemble le plus souvent")

    def test_en_5_numbers_together(self):
        assert _detect_cooccurrence_high_n("5 numbers that come together most often")

    def test_en_group_of_4(self):
        assert _detect_cooccurrence_high_n("group of 4 numbers")

    def test_en_combination_of_5(self):
        assert _detect_cooccurrence_high_n("combination of 5")

    def test_es_5_numeros_juntos(self):
        assert _detect_cooccurrence_high_n("5 números juntos")

    def test_es_combinacion_de_5(self):
        assert _detect_cooccurrence_high_n("combinación de 5")

    def test_pt_5_numeros_juntos(self):
        assert _detect_cooccurrence_high_n("5 números juntos")

    def test_pt_combinacao_de_4(self):
        assert _detect_cooccurrence_high_n("combinação de 4")

    def test_de_5_zahlen_zusammen(self):
        assert _detect_cooccurrence_high_n("5 Zahlen zusammen")

    def test_de_kombination_von_5(self):
        assert _detect_cooccurrence_high_n("Kombination von 5")

    def test_nl_7_nummers_samen(self):
        assert _detect_cooccurrence_high_n("7 nummers samen")

    def test_nl_combinatie_van_5(self):
        assert _detect_cooccurrence_high_n("combinatie van 5")

    # --- FALSE: N<=3 and non-co-occurrence ---

    def test_fr_3_numeros_not_high_n(self):
        assert not _detect_cooccurrence_high_n("3 numéros ensemble")

    def test_fr_2_numeros_not_high_n(self):
        assert not _detect_cooccurrence_high_n("2 numéros ensemble")

    def test_paires_not_high_n(self):
        assert not _detect_cooccurrence_high_n("paires de numéros")

    def test_triplet_not_high_n(self):
        assert not _detect_cooccurrence_high_n("triplet de numéros")

    def test_combination_of_3_not_high_n(self):
        assert not _detect_cooccurrence_high_n("combination of 3")

    def test_bonjour_not_high_n(self):
        assert not _detect_cooccurrence_high_n("bonjour")

    def test_classement_not_high_n(self):
        assert not _detect_cooccurrence_high_n("donne moi le classement des numéros")


# ═══════════════════════════════════════════════════════════════════════
# _get_cooccurrence_high_n_response — réponses honnêtes (6 langues)
# ═══════════════════════════════════════════════════════════════════════

class TestCooccurrenceHighNResponse:

    def test_fr_contains_n(self):
        resp = _get_cooccurrence_high_n_response("5 numéros ensemble", "fr")
        assert "5" in resp

    def test_fr_mentions_paires_or_triplets(self):
        resp = _get_cooccurrence_high_n_response("5 numéros ensemble", "fr")
        assert "paires" in resp or "triplets" in resp

    def test_en_response(self):
        resp = _get_cooccurrence_high_n_response("5 numbers together", "en")
        assert "pairs" in resp or "triplets" in resp

    def test_es_response(self):
        resp = _get_cooccurrence_high_n_response("5 números juntos", "es")
        assert "pares" in resp or "tripletes" in resp

    def test_pt_response(self):
        resp = _get_cooccurrence_high_n_response("5 números juntos", "pt")
        assert "pares" in resp or "tripletos" in resp

    def test_de_response(self):
        resp = _get_cooccurrence_high_n_response("5 Zahlen zusammen", "de")
        assert "Paare" in resp or "Drillinge" in resp

    def test_nl_response(self):
        resp = _get_cooccurrence_high_n_response("5 nummers samen", "nl")
        assert "paren" in resp or "drietallen" in resp

    def test_extracts_n_from_message(self):
        resp = _get_cooccurrence_high_n_response("7 numéros ensemble", "fr")
        assert "7" in resp

    def test_fallback_n_when_no_digit(self):
        resp = _get_cooccurrence_high_n_response("quadruplet", "fr")
        assert "5" in resp  # default N=5
