"""
V125 Sous-phase 2 Volet B — SQL continuation re-routing.

Tests de la détection d'une affirmation courte ("oui"/"ok"/"yes"/…) qui
suit une proposition modèle SQL-évocatrice ("Tu veux connaître son
historique complet ?"). Le re-routage bascule le pipeline vers
Text-to-SQL (Phase SQL) au lieu de fallback Gemini conversationnel.

Déclencheur terrain : chat_log#2093 (19/04/2026, Loto FR).
"""

from unittest.mock import MagicMock

from services.base_chat_detect_intent import (
    _is_sql_continuation,
    _sql_continuation_reroute,
    _SQL_EVOCATIVE_KEYWORDS,
    _SQL_REROUTE_TEMPLATES,
    _NUM_EXTRACT_RE,
)


def _msg(role: str, content: str):
    m = MagicMock()
    m.role = role
    m.content = content
    return m


# ─────────────────────────────────────────────────────────────────────────────
# _is_sql_continuation — détection lang par lang
# ─────────────────────────────────────────────────────────────────────────────

class TestIsSqlContinuation:
    """Validation des mots-clés SQL-évocateurs par langue."""

    def test_fr_historique(self):
        assert _is_sql_continuation("Tu veux connaître son historique complet ?", "fr") is True

    def test_fr_liste_complete(self):
        assert _is_sql_continuation("Je peux te donner la liste complète.", "fr") is True

    def test_fr_detail(self):
        assert _is_sql_continuation("Tu veux le détail de ce tirage ?", "fr") is True

    def test_fr_conversation_not_sql(self):
        """Message assistant conversationnel sans keyword SQL → False.
        V126 L13 : 'creuser' est désormais keyword → message changé pour
        préserver l'esprit du test V125 (conversation pure sans keyword)."""
        assert _is_sql_continuation("Tu veux parler d'autre chose ?", "fr") is False

    def test_en_history(self):
        assert _is_sql_continuation("Want to see the full history?", "en") is True

    def test_en_details(self):
        assert _is_sql_continuation("Want the details of each draw?", "en") is True

    def test_es_historial(self):
        assert _is_sql_continuation("¿Quieres el historial completo?", "es") is True

    def test_pt_historico(self):
        assert _is_sql_continuation("Queres o histórico completo?", "pt") is True

    def test_de_verlauf(self):
        assert _is_sql_continuation("Möchtest du den vollständigen Verlauf?", "de") is True

    def test_nl_geschiedenis(self):
        assert _is_sql_continuation("Wil je de volledige geschiedenis?", "nl") is True

    def test_empty_message(self):
        assert _is_sql_continuation("", "fr") is False

    def test_unknown_lang_falls_back_fr(self):
        """Lang inconnue → fallback FR keywords."""
        assert _is_sql_continuation("Tu veux l'historique complet ?", "xx") is True


# ─────────────────────────────────────────────────────────────────────────────
# _sql_continuation_reroute — reformulation + extraction numéro
# ─────────────────────────────────────────────────────────────────────────────

class TestSqlContinuationReroute:
    """Validation du re-routage complet en 6 langues + cas limites."""

    def test_oui_after_historique_reroutes_fr(self):
        """Cas #2093 : oui après 'historique complet ?' → reformule en FR."""
        history = [
            _msg("user", "est-ce que le 30 est sorti récemment ?"),
            _msg("assistant", "Oui, le 30 est sorti 115 fois. Tu veux connaître son historique complet ?"),
        ]
        result = _sql_continuation_reroute(history, "fr")
        assert result is not None
        assert "historique" in result.lower()
        assert "30" in result

    def test_yes_after_history_reroutes_en(self):
        history = [
            _msg("user", "did number 30 come out recently?"),
            _msg("assistant", "The number 30 came out 115 times. Want to see the full history?"),
        ]
        result = _sql_continuation_reroute(history, "en")
        assert result is not None
        assert "history" in result.lower()
        assert "30" in result

    def test_si_after_historial_reroutes_es(self):
        history = [
            _msg("user", "¿el número 30 salió recientemente?"),
            _msg("assistant", "El número 30 salió 115 veces. ¿Quieres el historial completo?"),
        ]
        result = _sql_continuation_reroute(history, "es")
        assert result is not None
        assert "historial" in result.lower()
        assert "30" in result

    def test_sim_after_historico_reroutes_pt(self):
        history = [
            _msg("user", "o número 30 saiu recentemente?"),
            _msg("assistant", "O número 30 saiu 115 vezes. Queres o histórico completo?"),
        ]
        result = _sql_continuation_reroute(history, "pt")
        assert result is not None
        assert "histórico" in result.lower()
        assert "30" in result

    def test_ja_after_verlauf_reroutes_de(self):
        history = [
            _msg("user", "Ist die Nummer 30 kürzlich erschienen?"),
            _msg("assistant", "Die Nummer 30 erschien 115-mal. Möchtest du den vollständigen Verlauf?"),
        ]
        result = _sql_continuation_reroute(history, "de")
        assert result is not None
        assert "verlauf" in result.lower()
        assert "30" in result

    def test_ja_after_geschiedenis_reroutes_nl(self):
        history = [
            _msg("user", "is nummer 30 recent verschenen?"),
            _msg("assistant", "Nummer 30 verscheen 115 keer. Wil je de volledige geschiedenis?"),
        ]
        result = _sql_continuation_reroute(history, "nl")
        assert result is not None
        assert "geschiedenis" in result.lower()
        assert "30" in result

    def test_oui_after_conversation_no_reroute(self):
        """Message assistant sans keyword SQL → None (comportement V124).
        V126 L13 : wording changé de 'creuser un autre sujet' à 'parler d'autre
        chose' car 'creuser' est désormais keyword SQL-évocateur."""
        history = [
            _msg("user", "salut"),
            _msg("assistant", "Salut ! Tu veux parler d'autre chose ?"),
        ]
        assert _sql_continuation_reroute(history, "fr") is None

    def test_oui_no_previous_assistant_no_reroute(self):
        """History vide ou 1 seul message → None."""
        assert _sql_continuation_reroute([], "fr") is None
        assert _sql_continuation_reroute([_msg("user", "oui")], "fr") is None

    def test_extraction_number_30_from_previous_msg(self):
        """Regex extraction : le chiffre mentionné dans le msg assistant doit être repris."""
        history = [
            _msg("user", "?"),
            _msg("assistant", "Le 30 est sorti 115 fois. Tu veux l'historique complet ?"),
        ]
        result = _sql_continuation_reroute(history, "fr")
        assert result is not None
        assert "30" in result

    def test_no_number_generic_reroute(self):
        """Pas de numéro extractible → reformulation générique (sans chiffre)."""
        history = [
            _msg("user", "stats ?"),
            _msg("assistant", "Je peux te donner l'historique complet ?"),
        ]
        result = _sql_continuation_reroute(history, "fr")
        assert result is not None
        # Le template fallback ne contient pas de {num}
        assert "{num}" not in result

    def test_extraction_etoile_em(self):
        """Extraction avec keyword étoile (EM 6 langues)."""
        history = [
            _msg("user", "?"),
            _msg("assistant", "L'étoile 7 est sortie 50 fois. Tu veux l'historique complet ?"),
        ]
        result = _sql_continuation_reroute(history, "fr")
        assert result is not None
        assert "7" in result

    def test_extraction_star_em_en(self):
        history = [
            _msg("user", "?"),
            _msg("assistant", "Star 7 appeared 50 times. Want the full history?"),
        ]
        result = _sql_continuation_reroute(history, "en")
        assert result is not None
        assert "7" in result

    def test_reroute_targets_phase_sql_not_phase_1(self):
        """Anti-boucle : le message reformulé ne doit PAS déclencher Phase 1 comme seule réponse.

        V125 garantit que `_sql_reroute_applied=True` → `force_sql=True` → Phase 1
        skippée (condition `not force_sql` ligne 1060 chat_pipeline_shared.py).
        Ici on vérifie que le TEMPLATE contient bien le mot-clé qui sera utilisé
        par le pipeline pour forcer Phase SQL (via le flag `_sql_reroute_applied`
        déclenché dès que `_sql_continuation_reroute` retourne non-None).
        """
        history = [
            _msg("user", "?"),
            _msg("assistant", "Le 30 est sorti 115 fois. Tu veux l'historique complet ?"),
        ]
        result = _sql_continuation_reroute(history, "fr")
        assert result is not None
        # Le template contient "historique" → data signal + Gemini génère SELECT WHERE boule_N=30
        assert "historique" in result.lower()
        # Et pour toutes les langues, le template est différent du message raw "oui"
        assert result != "oui"
        assert result != "ok"
        assert result != "yes"


# ─────────────────────────────────────────────────────────────────────────────
# Regex _NUM_EXTRACT_RE — indicateurs linguistiques étendus (étoile, chance, …)
# ─────────────────────────────────────────────────────────────────────────────

class TestNumExtractRegex:
    """Validation de la couverture de l'extraction numéro (6 langues × N indicateurs)."""

    def test_extracts_after_le(self):
        m = _NUM_EXTRACT_RE.search("Le 30 est sorti 115 fois")
        assert m and m.group(1) == "30"

    def test_extracts_after_the(self):
        m = _NUM_EXTRACT_RE.search("The 30 came out 115 times")
        assert m and m.group(1) == "30"

    def test_extracts_after_numero(self):
        m = _NUM_EXTRACT_RE.search("Le numéro 7 est sorti.")
        assert m and m.group(1) == "7"

    def test_extracts_after_etoile(self):
        m = _NUM_EXTRACT_RE.search("L'étoile 7 est sortie.")
        assert m and m.group(1) == "7"

    def test_extracts_after_chance(self):
        m = _NUM_EXTRACT_RE.search("La chance 3 est apparue.")
        assert m and m.group(1) == "3"

    def test_extracts_after_star_en(self):
        m = _NUM_EXTRACT_RE.search("Star 7 appeared.")
        assert m and m.group(1) == "7"

    def test_extracts_after_stern_de(self):
        m = _NUM_EXTRACT_RE.search("Stern 7 erschien.")
        assert m and m.group(1) == "7"


# ─────────────────────────────────────────────────────────────────────────────
# Constantes V125 — invariants de configuration
# ─────────────────────────────────────────────────────────────────────────────

class TestV125Constants:
    """Invariants : 6 langues présentes, pas de fuite de keyword entre langues."""

    def test_keywords_6_langs(self):
        assert set(_SQL_EVOCATIVE_KEYWORDS.keys()) == {"fr", "en", "es", "pt", "de", "nl"}

    def test_templates_6_langs(self):
        assert set(_SQL_REROUTE_TEMPLATES.keys()) == {"fr", "en", "es", "pt", "de", "nl"}

    def test_templates_contain_num_placeholder(self):
        for lang, tpl in _SQL_REROUTE_TEMPLATES.items():
            assert "{num}" in tpl, f"Template {lang} manque {{num}}: {tpl}"
