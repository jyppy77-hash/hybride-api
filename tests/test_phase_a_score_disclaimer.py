"""
Tests unitaires — Fix 5+6+7 :
- Phase A exclusion score de conformite (BUG 1)
- Disclaimer score dans le contexte de generation (BUG 2)
- Donnees source dans les prompts (BUG 3)
"""

import pytest

from services.chat_detectors import _detect_argent, _detect_score_question
from services.chat_detectors_em import _detect_argent_em, _detect_score_question_em
from services.chat_utils import _format_generation_context
from services.chat_utils_em import _format_generation_context_em


# ═══════════════════════════════════════════════════════════════════════
# BUG 1 — Phase A exclusion score de conformité
# ═══════════════════════════════════════════════════════════════════════

class TestScoreQuestionDetection:
    """_detect_score_question doit matcher les questions sur le score."""

    def test_fr_score_chances_gagner(self):
        assert _detect_score_question(
            "Quand tu dis score 100/100, ça veut dire que cette grille a plus de chances de gagner ?"
        ) is True

    def test_fr_score_interne(self):
        assert _detect_score_question("c'est un score interne ?") is True

    def test_fr_score_de_conformite(self):
        assert _detect_score_question("que signifie le score de conformité ?") is True

    def test_fr_100_100_gagner(self):
        assert _detect_score_question("100/100 veut dire que je vais gagner ?") is True

    def test_fr_conformite_probabilite(self):
        assert _detect_score_question(
            "la conformité a un impact sur la probabilité ?"
        ) is True

    def test_fr_gagner_score(self):
        assert _detect_score_question(
            "est-ce que gagner est plus facile avec un meilleur score ?"
        ) is True

    def test_fr_not_triggered_on_plain_gagner(self):
        """'gagner' seul sans contexte score ne matche PAS."""
        assert _detect_score_question("combien je vais gagner ?") is False

    def test_fr_not_triggered_on_plain_argent(self):
        assert _detect_score_question("est-ce rentable ?") is False


class TestScoreQuestionDetectionEM:
    """_detect_score_question_em doit matcher les questions score multilingues."""

    def test_en_score_chances_winning(self):
        assert _detect_score_question_em(
            "does a score of 100/100 mean better chances of winning?", "en"
        ) is True

    def test_en_conformity_score(self):
        assert _detect_score_question_em("what does the conformity score mean?", "en") is True

    def test_en_internal_score(self):
        assert _detect_score_question_em("is it an internal score?", "en") is True

    def test_es_puntuacion_ganar(self):
        assert _detect_score_question_em(
            "la puntuación 100/100 significa que voy a ganar?", "es"
        ) is True

    def test_es_puntuacion_interna(self):
        assert _detect_score_question_em("es una puntuación interna?", "es") is True

    def test_pt_pontuacao_ganhar(self):
        assert _detect_score_question_em(
            "a pontuação 100/100 significa que vou ganhar?", "pt"
        ) is True

    def test_pt_pontuacao_interna(self):
        assert _detect_score_question_em("é uma pontuação interna?", "pt") is True

    def test_de_score_gewinnen(self):
        assert _detect_score_question_em(
            "bedeutet ein Score von 100/100 mehr Chancen zu gewinnen?", "de"
        ) is True

    def test_de_interner_score(self):
        assert _detect_score_question_em("ist das ein interner Score?", "de") is True

    def test_nl_score_winnen(self):
        assert _detect_score_question_em(
            "betekent een score van 100/100 meer kans om te winnen?", "nl"
        ) is True

    def test_nl_interne_score(self):
        assert _detect_score_question_em("is het een interne score?", "nl") is True

    def test_en_not_triggered_on_plain_winning(self):
        assert _detect_score_question_em("how much can I win?", "en") is False


class TestPhaseAScoreExclusion:
    """Phase A ne doit PAS bloquer les questions sur le score de conformité."""

    def test_loto_score_chances_not_blocked(self):
        assert _detect_argent(
            "Quand tu dis score 100/100, ça veut dire que cette grille a plus de chances de gagner ?"
        ) is False

    def test_loto_score_interne_not_blocked(self):
        assert _detect_argent(
            "le score 100/100 c'est un score interne ou une probabilité de gagner ?"
        ) is False

    def test_loto_conformite_chances_not_blocked(self):
        assert _detect_argent(
            "la conformité a un lien avec les chances de gagner ?"
        ) is False

    def test_em_fr_score_not_blocked(self):
        assert _detect_argent_em(
            "score 100/100 = plus de chances de gagner ?", "fr"
        ) is False

    def test_em_en_score_not_blocked(self):
        assert _detect_argent_em(
            "does a score of 100/100 mean better chances of winning?", "en"
        ) is False

    def test_em_es_score_not_blocked(self):
        assert _detect_argent_em(
            "la puntuación 100/100 significa más probabilidad de ganar?", "es"
        ) is False

    def test_em_pt_score_not_blocked(self):
        assert _detect_argent_em(
            "a pontuação 100/100 significa mais probabilidade de ganhar?", "pt"
        ) is False

    def test_em_de_score_not_blocked(self):
        assert _detect_argent_em(
            "bedeutet der Score 100/100 eine höhere Chance zu gewinnen?", "de"
        ) is False

    def test_em_nl_score_not_blocked(self):
        assert _detect_argent_em(
            "betekent de score 100/100 meer kans om te winnen?", "nl"
        ) is False


class TestPhaseAStillBlocksRealArgent:
    """Phase A doit TOUJOURS bloquer les VRAIES questions d'argent."""

    def test_combien_gagner(self):
        assert _detect_argent("combien je vais gagner au Loto ?") is True

    def test_est_ce_rentable(self):
        assert _detect_argent("est-ce rentable de jouer ?") is True

    def test_devenir_riche(self):
        assert _detect_argent("comment devenir riche avec le Loto") is True

    def test_em_how_much_win(self):
        assert _detect_argent_em("how much can I win?", "en") is True

    def test_em_hacerse_rico(self):
        assert _detect_argent_em("quiero hacerme rico", "es") is True

    def test_em_ficar_rico(self):
        assert _detect_argent_em("quero ficar rico", "pt") is True

    def test_em_reich_werden(self):
        assert _detect_argent_em("ich will reich werden", "de") is True

    def test_em_rijk_worden(self):
        assert _detect_argent_em("ik wil rijk worden", "nl") is True

    def test_joue_50_euros(self):
        assert _detect_argent("joue 50€ par semaine") is True

    def test_strategie_gagner(self):
        assert _detect_argent("stratégie pour gagner au Loto") is True


# ═══════════════════════════════════════════════════════════════════════
# BUG 2 — Disclaimer score dans le contexte de génération
# ═══════════════════════════════════════════════════════════════════════

class TestDisclaimerScoreContext:
    """Le contexte de génération doit contenir le disclaimer score."""

    _LOTO_GRID = {
        "nums": [3, 14, 22, 35, 48],
        "chance": 7,
        "score": 100,
        "badges": ["equilibre"],
        "mode": "balanced",
    }

    _EM_GRID = {
        "nums": [5, 14, 28, 37, 49],
        "etoiles": [3, 11],
        "score": 85,
        "badges": [],
        "mode": "balanced",
    }

    def test_loto_disclaimer_present(self):
        ctx = _format_generation_context(self._LOTO_GRID)
        assert "DISCLAIMER SCORE" in ctx

    def test_loto_disclaimer_not_probability(self):
        ctx = _format_generation_context(self._LOTO_GRID)
        assert "NE mesure PAS une probabilité de gain" in ctx

    def test_loto_disclaimer_same_probability(self):
        ctx = _format_generation_context(self._LOTO_GRID)
        assert "même probabilité mathématique" in ctx

    def test_em_disclaimer_present(self):
        ctx = _format_generation_context_em(self._EM_GRID)
        assert "DISCLAIMER SCORE" in ctx

    def test_em_disclaimer_not_probability(self):
        ctx = _format_generation_context_em(self._EM_GRID)
        assert "NE mesure PAS une probabilité de gain" in ctx

    def test_em_disclaimer_same_probability(self):
        ctx = _format_generation_context_em(self._EM_GRID)
        assert "même probabilité mathématique" in ctx


# ═══════════════════════════════════════════════════════════════════════
# BUG 3 — Données source dans les prompts
# ═══════════════════════════════════════════════════════════════════════

class TestDataSourceInPrompts:
    """Les prompts doivent contenir les infos de période et volume."""

    def test_loto_prompt_since_2019(self):
        with open("prompts/chatbot/prompt_hybride.txt", encoding="utf-8") as f:
            content = f.read()
        assert "depuis 2019" in content
        assert "990 tirages" in content

    def test_loto_prompt_data_source_section(self):
        with open("prompts/chatbot/prompt_hybride.txt", encoding="utf-8") as f:
            content = f.read()
        assert "[DONNÉES SOURCE" in content

    def test_em_fr_prompt_since_2004(self):
        with open("prompts/em/fr/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "depuis 2004" in content
        assert "733 tirages" in content

    def test_em_fr_prompt_data_source_section(self):
        with open("prompts/em/fr/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "[DONNÉES SOURCE" in content

    def test_em_en_prompt_since_2004(self):
        with open("prompts/em/en/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "since 2004" in content
        assert "733 draws" in content
        assert "[DATA SOURCE" in content

    def test_em_es_prompt_since_2004(self):
        with open("prompts/em/es/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "desde 2004" in content
        assert "733 sorteos" in content
        assert "[FUENTE DE DATOS" in content

    def test_em_pt_prompt_since_2004(self):
        with open("prompts/em/pt/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "desde 2004" in content
        assert "733 sorteios" in content
        assert "[FONTE DE DADOS" in content

    def test_em_de_prompt_since_2004(self):
        with open("prompts/em/de/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "seit 2004" in content
        assert "733" in content
        assert "[DATENQUELLE" in content

    def test_em_nl_prompt_since_2004(self):
        with open("prompts/em/nl/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "sinds 2004" in content
        assert "733" in content
        assert "[GEGEVENSBRON" in content


class TestDisclaimerInPrompts:
    """Les prompts doivent contenir le disclaimer score de conformité."""

    def test_loto_prompt_disclaimer(self):
        with open("prompts/chatbot/prompt_hybride.txt", encoding="utf-8") as f:
            content = f.read()
        assert "DISCLAIMER SCORE" in content

    def test_em_fr_prompt_disclaimer(self):
        with open("prompts/em/fr/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "DISCLAIMER SCORE" in content

    def test_em_en_prompt_disclaimer(self):
        with open("prompts/em/en/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "DISCLAIMER" in content
        assert "CONFORMITY SCORE" in content

    def test_em_es_prompt_disclaimer(self):
        with open("prompts/em/es/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "DISCLAIMER" in content

    def test_em_pt_prompt_disclaimer(self):
        with open("prompts/em/pt/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "DISCLAIMER" in content

    def test_em_de_prompt_disclaimer(self):
        with open("prompts/em/de/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "DISCLAIMER" in content

    def test_em_nl_prompt_disclaimer(self):
        with open("prompts/em/nl/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "DISCLAIMER" in content

    def test_em_legacy_prompt_disclaimer(self):
        with open("prompts/chatbot/prompt_hybride_em.txt", encoding="utf-8") as f:
            content = f.read()
        assert "DISCLAIMER SCORE" in content
