"""
V126 Sous-phase 3/5 — Température 0.4 Phase 0 avec historique SQL-évocateur.

Non-régression obligatoire :
- V99 F05 : T=0.2 si contexte factuel tag, T=0.6 sinon (Phases 1/T/SQL)
- V126 3/5 : T=0.4 additionnel si Phase 0 + dernier assistant SQL-évocateur
"""

from unittest.mock import MagicMock

from services.chat_pipeline_gemini import (
    _get_temperature,
    _history_has_sql_evocative_tail,
    _TEMPERATURE_FACTUAL,
    _TEMPERATURE_CONVERSATIONAL,
    _TEMPERATURE_PHASE0_SQL_EVOCATIVE,
)


def _msg(role: str, content: str):
    m = MagicMock()
    m.role = role
    m.content = content
    return m


class TestV126TemperaturePhase0:
    """V126 3/5 : T=0.4 si Phase 0 + dernier assistant contient keyword SQL."""

    def test_T04_on_phase0_with_sql_keyword_history(self):
        history = [
            _msg("user", "stats du 30 ?"),
            _msg(
                "assistant",
                "Le 30 est sorti 115 fois. Tu veux l'historique complet ?",
            ),
        ]
        ctx = {
            "_chat_meta": {
                "phase": "0",
                "enrichment_context": "",
                "lang": "fr",
            },
            "history": history,
        }
        assert _get_temperature(ctx) == _TEMPERATURE_PHASE0_SQL_EVOCATIVE == 0.4

    def test_T06_on_phase0_without_sql_keyword(self):
        """Phase 0 + historique conversationnel SANS keyword → T=0.6 (V125 comportement)."""
        history = [
            _msg("user", "merci"),
            _msg("assistant", "De rien ! Autre chose ?"),
        ]
        ctx = {
            "_chat_meta": {"phase": "0", "enrichment_context": "", "lang": "fr"},
            "history": history,
        }
        assert _get_temperature(ctx) == _TEMPERATURE_CONVERSATIONAL == 0.6

    def test_T06_on_phase0_empty_history(self):
        """Phase 0 sans historique → T=0.6 (pas d'assistant à scanner)."""
        ctx = {
            "_chat_meta": {"phase": "0", "enrichment_context": "", "lang": "fr"},
            "history": [],
        }
        assert _get_temperature(ctx) == _TEMPERATURE_CONVERSATIONAL

    def test_T06_on_phase0_no_history_key(self):
        ctx = {"_chat_meta": {"phase": "0", "enrichment_context": "", "lang": "fr"}}
        assert _get_temperature(ctx) == _TEMPERATURE_CONVERSATIONAL

    def test_T04_respects_history_as_dict(self):
        """history dict-style (non-Pydantic) doit aussi matcher."""
        history = [
            {"role": "assistant", "content": "Tu veux le détail complet ?"},
        ]
        ctx = {
            "_chat_meta": {"phase": "0", "enrichment_context": "", "lang": "fr"},
            "history": history,
        }
        assert _get_temperature(ctx) == _TEMPERATURE_PHASE0_SQL_EVOCATIVE

    def test_T02_phase1_factual_unchanged_non_regression_V99(self):
        """Non-régression V99 F05 : Phase 1 + tag factuel → T=0.2 toujours."""
        ctx = {
            "_chat_meta": {
                "phase": "1",
                "enrichment_context": "[RÉSULTAT TIRAGE — CHIFFRES EXACTS]\n17-28-30",
                "lang": "fr",
            },
        }
        assert _get_temperature(ctx) == _TEMPERATURE_FACTUAL == 0.2

    def test_T02_phase_T_factual_unchanged(self):
        ctx = {
            "_chat_meta": {
                "phase": "T",
                "enrichment_context": "[RÉSULTAT TIRAGE]\n17-28-30",
                "lang": "fr",
            },
        }
        assert _get_temperature(ctx) == _TEMPERATURE_FACTUAL

    def test_T06_empty_context_no_meta_unchanged(self):
        """Non-régression V99 F05."""
        assert _get_temperature({}) == _TEMPERATURE_CONVERSATIONAL
        assert _get_temperature({"_chat_meta": None}) == _TEMPERATURE_CONVERSATIONAL
        assert _get_temperature({"_chat_meta": {"enrichment_context": ""}}) == _TEMPERATURE_CONVERSATIONAL

    def test_T06_phase1_non_factual_unchanged(self):
        """Phase 1 sans tag factuel → T=0.6 (V99 F05 contexte vide)."""
        ctx = {
            "_chat_meta": {
                "phase": "1",
                "enrichment_context": "",
                "lang": "fr",
            },
        }
        assert _get_temperature(ctx) == _TEMPERATURE_CONVERSATIONAL

    def test_factual_tag_priority_over_phase0(self):
        """Si Phase 0 MAIS tag factuel présent → T=0.2 (priorité V99 F05)."""
        history = [_msg("assistant", "Tu veux l'historique complet ?")]
        ctx = {
            "_chat_meta": {
                "phase": "0",
                "enrichment_context": "[DONNÉES TEMPS RÉEL]\nstats",
                "lang": "fr",
            },
            "history": history,
        }
        assert _get_temperature(ctx) == _TEMPERATURE_FACTUAL


class TestHistoryHasSqlEvocativeTail:
    """Unit-test la fonction helper dédiée V126 3/5."""

    def test_empty_history_false(self):
        assert _history_has_sql_evocative_tail([], "fr") is False
        assert _history_has_sql_evocative_tail(None, "fr") is False

    def test_last_assistant_with_keyword_true(self):
        history = [_msg("assistant", "Tu veux l'historique complet ?")]
        assert _history_has_sql_evocative_tail(history, "fr") is True

    def test_last_assistant_without_keyword_false(self):
        history = [_msg("assistant", "De rien !")]
        assert _history_has_sql_evocative_tail(history, "fr") is False

    def test_only_user_messages_false(self):
        history = [_msg("user", "historique"), _msg("user", "detail")]
        assert _history_has_sql_evocative_tail(history, "fr") is False

    def test_skips_older_assistant_after_conversational(self):
        """Si dernier assistant conversationnel, on ne remonte pas plus loin."""
        history = [
            _msg("assistant", "Tu veux l'historique ?"),
            _msg("user", "merci"),
            _msg("assistant", "De rien !"),
        ]
        # Dernier assistant = "De rien !" sans keyword → False
        assert _history_has_sql_evocative_tail(history, "fr") is False
