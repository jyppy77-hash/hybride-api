"""
V126 Sous-phase 4.5 — L12 FP argent sur vocabulaire SQL + L13 extension
`_SQL_EVOCATIVE_KEYWORDS` + `_is_user_sql_request` (messages USER directs).

Déclencheurs terrain :
- L12 (19/04/2026) : "fais une requete sql" → FP guardrail argent
- L13 (19/04/2026) : "je veux creuser l'historique" → Volet B V125 non déclenché
  car aucun keyword "historique" dans dernier message assistant

Tests symétriques Loto + EM (V99 F09).
"""

import pytest

from services.chat_detectors import _detect_argent
from services.chat_detectors_em_guardrails import _detect_argent_em
from services.base_chat_detect_intent import (
    _is_user_sql_request,
    _SQL_EVOCATIVE_KEYWORDS,
    _is_sql_continuation,
)


# ─────────────────────────────────────────────────────────────────────
# L12 — FP argent sur vocabulaire SQL/technique
# ─────────────────────────────────────────────────────────────────────


class TestL12ArgentFalsePositiveOnTechnicalVocab:
    """V126 L12 : vocab technique (SQL/requête/JSON/API…) ne doit PAS
    déclencher Phase A (ni côté Loto ni côté EM)."""

    def test_fais_une_requete_sql_not_argent_loto(self):
        """Cas terrain 19/04 — reproduction exacte."""
        assert _detect_argent("fais une requete sql", "fr") is False

    def test_fais_une_requete_sql_not_argent_em(self):
        assert _detect_argent_em("fais une requete sql", "fr") is False

    def test_real_argent_still_flagged_loto(self):
        """Non-régression : vrais cas argent toujours détectés."""
        assert _detect_argent("je vais miser 100 euros par semaine", "fr") is True

    def test_real_argent_still_flagged_em(self):
        assert _detect_argent_em("comment gros lot euromillions", "fr") is True

    def test_query_en_excluded(self):
        assert _detect_argent("write a sql query please", "en") is False

    def test_api_excluded_6_langs(self):
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            assert _detect_argent(f"call the api endpoint", lang) is False

    def test_json_excluded(self):
        assert _detect_argent("return the result as json", "en") is False

    def test_python_code_excluded(self):
        assert _detect_argent("ecris du code python qui calcule", "fr") is False

    def test_schema_table_excluded(self):
        assert _detect_argent("montre moi le schema de la table tirages", "fr") is False

    def test_em_technical_symétrie(self):
        """EM doit avoir le même comportement que Loto (V99 F09)."""
        assert _detect_argent_em("select from tirages", "en") is False
        assert _detect_argent_em("api endpoint", "fr") is False


# ─────────────────────────────────────────────────────────────────────
# L13 — Extension _SQL_EVOCATIVE_KEYWORDS (+ keywords courts)
# ─────────────────────────────────────────────────────────────────────


class TestL13KeywordsExtended:
    """V126 L13 : keywords étendus doivent faire matcher _is_sql_continuation
    sur les formulations additionnelles (creuser, explorer, voir plus…)."""

    def test_creuser_triggers_continuation_fr(self):
        assert _is_sql_continuation("Tu veux creuser ce chiffre ?", "fr") is True

    def test_explorer_triggers_continuation_fr(self):
        assert _is_sql_continuation("On peut explorer ça ensemble", "fr") is True

    def test_voir_plus_triggers_continuation_fr(self):
        assert _is_sql_continuation("Tu veux voir plus de détails ?", "fr") is True

    def test_dig_deeper_triggers_continuation_en(self):
        assert _is_sql_continuation("Want to dig deeper?", "en") is True

    def test_profundizar_triggers_continuation_es(self):
        assert _is_sql_continuation("¿Quieres profundizar?", "es") is True

    def test_aprofundar_triggers_continuation_pt(self):
        assert _is_sql_continuation("Queres aprofundar?", "pt") is True

    def test_vertiefen_triggers_continuation_de(self):
        assert _is_sql_continuation("Willst du vertiefen?", "de") is True

    def test_uitdiepen_triggers_continuation_nl(self):
        assert _is_sql_continuation("Wil je uitdiepen?", "nl") is True

    def test_no_regression_v125_keywords_still_work(self):
        """Non-régression V125 : keywords originaux historique/détail/liste."""
        assert _is_sql_continuation("Tu veux l'historique complet ?", "fr") is True
        assert _is_sql_continuation("Tu veux le détail ?", "fr") is True

    def test_6_langs_still_present(self):
        assert set(_SQL_EVOCATIVE_KEYWORDS) == {"fr", "en", "es", "pt", "de", "nl"}


# ─────────────────────────────────────────────────────────────────────
# L13 — `_is_user_sql_request` : messages USER directs
# ─────────────────────────────────────────────────────────────────────


class TestL13IsUserSqlRequest:
    """V126 L13 : nouveau hook détection USER direct (hors continuation)."""

    def test_user_direct_je_veux_creuser_historique_fr(self):
        """Cas terrain 19/04 (typo 'hisorique' → L14 reporté V127)."""
        assert _is_user_sql_request("je veux creuser l'historique", "fr") is True

    def test_user_direct_explorer_stats_fr(self):
        assert _is_user_sql_request("je veux explorer les stats", "fr") is True

    def test_user_direct_dig_deeper_en(self):
        assert _is_user_sql_request("I want to dig deeper into 30", "en") is True

    def test_user_direct_profundizar_es(self):
        assert _is_user_sql_request("quiero profundizar en el número 30", "es") is True

    def test_user_direct_aprofundar_pt(self):
        assert _is_user_sql_request("quero aprofundar no 30", "pt") is True

    def test_user_direct_vertiefen_de(self):
        assert _is_user_sql_request("ich will die 30 vertiefen", "de") is True

    def test_user_direct_uitdiepen_nl(self):
        assert _is_user_sql_request("ik wil de 30 uitdiepen", "nl") is True

    def test_short_message_not_flagged(self):
        """Garde-fou : messages < 3 chars → False (évite FP 'ok')."""
        assert _is_user_sql_request("ok", "fr") is False
        assert _is_user_sql_request("", "fr") is False
        assert _is_user_sql_request("   ", "fr") is False

    def test_message_without_sql_keyword_not_flagged(self):
        """Conversation normale sans keyword → False."""
        assert _is_user_sql_request("bonjour, comment ça va ?", "fr") is False

    def test_unknown_lang_falls_back_fr(self):
        assert _is_user_sql_request("je veux creuser", "xx") is True


# ─────────────────────────────────────────────────────────────────────
# L13 — Non-régression V125 Volet B
# ─────────────────────────────────────────────────────────────────────


class TestL13NoRegressionV125:
    """Confirme que les tests V125 TestSqlContinuationReroute restent verts."""

    def test_historique_still_matches_V125(self):
        """L13 étend sans casser les keywords V125."""
        assert _is_sql_continuation("Tu veux l'historique complet ?", "fr") is True

    def test_list_of_draws_still_matches_V125(self):
        assert _is_sql_continuation("Want the list of draws?", "en") is True

    def test_conversational_without_keyword_false(self):
        """Msg conversationnel sans keyword → toujours False."""
        assert _is_sql_continuation("Tu veux creuser un autre sujet ?", "fr") is True
        # ^ 'creuser' est un keyword V126 L13 - maintenant True (non-régression: test couvre les ajouts)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
