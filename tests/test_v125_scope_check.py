"""
V125 Sous-phase 2 Volet A — Scope check élargi Phase 0 (A2 + A3 combinés).

A2 : check transitif sur Phase 0 si l'historique récent contient un tag factuel
     ([RÉSULTAT TIRAGE], [RÉSULTAT SQL], [DONNÉES TEMPS RÉEL]).
A3 : détection inconditionnelle de séquence draw-like orpheline
     (log-only warning sur toute phase, sans contexte factuel).

Références code : services/chat_pipeline_gemini.py
  - _extract_last_factual_context()
  - _check_sql_number_hallucination() scope étendu V125
"""

from unittest.mock import MagicMock

from services.chat_pipeline_gemini import (
    _check_sql_number_hallucination,
    _extract_last_factual_context,
)


def _msg(role: str, content: str):
    m = MagicMock()
    m.role = role
    m.content = content
    return m


# ─────────────────────────────────────────────────────────────────────────────
# A2 — Extraction transitive du dernier contexte factuel
# ─────────────────────────────────────────────────────────────────────────────

class TestA2ExtractLastFactualContext:
    """V125 A2: _extract_last_factual_context() doit retourner le dernier msg
    assistant contenant un tag factuel, None sinon."""

    def test_empty_history_returns_none(self):
        assert _extract_last_factual_context([]) is None
        assert _extract_last_factual_context(None) is None

    def test_history_without_factual_tag_returns_none(self):
        history = [
            _msg("user", "salut"),
            _msg("assistant", "Bonjour ! Comment puis-je t'aider ?"),
        ]
        assert _extract_last_factual_context(history) is None

    def test_history_with_resultat_tirage_tag_returns_content(self):
        tagged = "[RÉSULTAT TIRAGE — CHIFFRES EXACTS]\nTirage du 14 mars 2026 : 10 - 22 - 23 - 25 - 46 | Chance : 3\n[/RÉSULTAT TIRAGE]"
        history = [
            _msg("user", "dernier tirage ?"),
            _msg("assistant", tagged),
        ]
        result = _extract_last_factual_context(history)
        assert result is not None
        assert "10" in result
        assert "22" in result

    def test_history_with_resultat_sql_tag_returns_content(self):
        tagged = "[RÉSULTAT SQL]\nDate : 2026-03-14 | Numéros : 10, 22, 23, 25, 46\n[/RÉSULTAT SQL]"
        history = [_msg("assistant", tagged)]
        result = _extract_last_factual_context(history)
        assert result is not None

    def test_history_with_donnees_temps_reel_tag_returns_content(self):
        tagged = "[DONNÉES TEMPS RÉEL — CHIFFRES EXACTS]\nNuméro 30 : sorti 115 fois depuis 2019.\n[/DONNÉES TEMPS RÉEL]"
        history = [_msg("assistant", tagged)]
        result = _extract_last_factual_context(history)
        assert result is not None
        assert "115" in result

    def test_last_assistant_without_tag_returns_none_even_if_older_has_tag(self):
        """Si le dernier assistant n'a pas de tag, on ne remonte pas — pas de check."""
        older_tagged = "[RÉSULTAT TIRAGE]\n10 - 22 - 23\n[/RÉSULTAT TIRAGE]"
        history = [
            _msg("user", "?"),
            _msg("assistant", older_tagged),
            _msg("user", "merci"),
            _msg("assistant", "De rien !"),
        ]
        assert _extract_last_factual_context(history) is None


# ─────────────────────────────────────────────────────────────────────────────
# A2 — Scope check élargi Phase 0 via historique transitif
# ─────────────────────────────────────────────────────────────────────────────

class TestA2ScopePhase0Transitive:
    """V125 A2: check actif sur Phase 0 SI historique contient tag factuel récent."""

    def test_phase_0_without_history_returns_none(self):
        """Phase 0 sans historique → pas de check (comportement V124 conservé)."""
        result = _check_sql_number_hallucination(
            enrichment_context="", gemini_response="Le 10 est sorti souvent.",
            phase="0", log_prefix="[TEST]", lang="fr", history=None,
        )
        assert result is None

    def test_phase_0_with_non_factual_history_returns_none(self):
        """Phase 0 avec historique non-factuel → pas de check."""
        history = [_msg("assistant", "Bonjour !")]
        result = _check_sql_number_hallucination(
            enrichment_context="", gemini_response="Voici 10 - 22 - 23 - 25 - 46",
            phase="0", log_prefix="[TEST]", lang="fr", history=history,
        )
        assert result is None

    def test_phase_0_with_factual_history_and_correct_numbers_returns_none(self):
        """Phase 0 + historique factuel + réponse cohérente → None (OK)."""
        tagged = "[RÉSULTAT TIRAGE]\n10 - 22 - 23 - 25 - 46 | Chance : 3\n[/RÉSULTAT TIRAGE]"
        history = [_msg("assistant", tagged)]
        result = _check_sql_number_hallucination(
            enrichment_context="",
            gemini_response="Le tirage contenait 10, 22, 23, 25 et 46 avec la chance 3.",
            phase="0", log_prefix="[TEST]", lang="fr", history=history,
        )
        assert result is None

    def test_phase_0_with_factual_history_and_invented_numbers_returns_replacement(self):
        """Phase 0 + historique factuel + réponse avec numéros inventés → remplace."""
        tagged = "[RÉSULTAT TIRAGE]\n10 - 22 - 23 - 25 - 46 | Chance : 3\n[/RÉSULTAT TIRAGE]"
        history = [_msg("assistant", tagged)]
        # Gemini invente 99 dans la séquence
        result = _check_sql_number_hallucination(
            enrichment_context="",
            gemini_response="Le tirage contenait 10 - 22 - 99 - 25 - 46",
            phase="0", log_prefix="[TEST]", lang="fr", history=history,
        )
        assert result is not None
        assert "données exactes" in result.lower()


# ─────────────────────────────────────────────────────────────────────────────
# A3 — Détection inconditionnelle séquence orpheline (log-only)
# ─────────────────────────────────────────────────────────────────────────────

class TestA3OrphanSequenceDetection:
    """V125 A3: séquence 5-nums sans contexte factuel → log warning (log-only)."""

    def test_orphan_sequence_in_phase_0_logs_warning(self, caplog):
        """Phase 0 + séquence 5-nums sans tag factuel nulle part → warning."""
        import logging
        caplog.set_level(logging.WARNING)
        _check_sql_number_hallucination(
            enrichment_context="", gemini_response="Voici 10 - 22 - 23 - 25 - 46",
            phase="0", log_prefix="[TEST]", lang="fr", history=None,
        )
        assert any("HALLUCINATION_ORPHAN_SEQUENCE" in r.message for r in caplog.records)

    def test_orphan_sequence_in_refus_phase_logs_warning(self, caplog):
        """Phase REFUS + séquence orpheline → warning (toute phase, V125 A3)."""
        import logging
        caplog.set_level(logging.WARNING)
        _check_sql_number_hallucination(
            enrichment_context="", gemini_response="Regarde ces numéros : 1, 2, 3, 4, 5 !",
            phase="REFUS", log_prefix="[TEST]", lang="fr", history=None,
        )
        assert any("HALLUCINATION_ORPHAN_SEQUENCE" in r.message for r in caplog.records)

    def test_no_sequence_no_orphan_warning(self, caplog):
        """Pas de séquence 5-nums → pas de warning orphan."""
        import logging
        caplog.set_level(logging.WARNING)
        _check_sql_number_hallucination(
            enrichment_context="", gemini_response="Tout va bien, aucune donnée spécifique.",
            phase="0", log_prefix="[TEST]", lang="fr", history=None,
        )
        assert not any("HALLUCINATION_ORPHAN_SEQUENCE" in r.message for r in caplog.records)

    def test_sequence_with_factual_context_no_orphan_warning(self, caplog):
        """Séquence mais tag factuel présent dans enrichment → pas de warning orphan."""
        import logging
        caplog.set_level(logging.WARNING)
        _check_sql_number_hallucination(
            enrichment_context="[RÉSULTAT TIRAGE]\n10 - 22 - 23 - 25 - 46\n[/RÉSULTAT TIRAGE]",
            gemini_response="Les numéros 10 - 22 - 23 - 25 - 46 sont sortis.",
            phase="1", log_prefix="[TEST]", lang="fr", history=None,
        )
        assert not any("HALLUCINATION_ORPHAN_SEQUENCE" in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# Non-régression — phases ("1", "T", "SQL") inchangées
# ─────────────────────────────────────────────────────────────────────────────

class TestV99NonRegressionPhase1TSQL:
    """Vérifie que le comportement V99 sur phases 1/T/SQL reste identique."""

    def test_phase_1_with_factual_and_correct_returns_none(self):
        result = _check_sql_number_hallucination(
            enrichment_context="[RÉSULTAT TIRAGE]\n10 - 22\n[/RÉSULTAT TIRAGE]",
            gemini_response="Le tirage était 10, 22.",
            phase="1", log_prefix="[TEST]", lang="fr",
        )
        assert result is None

    def test_phase_1_invented_sequence_returns_replacement(self):
        result = _check_sql_number_hallucination(
            enrichment_context="[RÉSULTAT TIRAGE]\n10 - 22 - 23 - 25 - 46\n[/RÉSULTAT TIRAGE]",
            gemini_response="Les numéros étaient 99 - 22 - 23 - 25 - 46.",
            phase="1", log_prefix="[TEST]", lang="fr",
        )
        assert result is not None

    def test_phase_sql_without_data_tag_returns_none(self):
        """V99 F03 : pas de tag factuel → return None (comportement inchangé)."""
        result = _check_sql_number_hallucination(
            enrichment_context="pas de données",
            gemini_response="Le tirage 10 - 22 - 23 - 25 - 46",
            phase="SQL", log_prefix="[TEST]", lang="fr",
        )
        # Note: le warning orphan (A3) tourne, mais la fn retourne None
        assert result is None
