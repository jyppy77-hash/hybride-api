"""
Tests unitaires pour services/chat_utils.py.
Fonctions de formatage, nettoyage, enrichissement contextuel.
"""

from unittest.mock import MagicMock

from services.chat_utils import (
    _enrich_with_context, _clean_response, _strip_sponsor_from_text,
    _format_date_fr, _format_complex_context,
)


# ── Helper ────────────────────────────────────────────────────────────

def _msg(role, content):
    m = MagicMock()
    m.role = role
    m.content = content
    return m


# ═══════════════════════════════════════════════════════════════════════
# _enrich_with_context
# ═══════════════════════════════════════════════════════════════════════

class TestEnrichWithContext:

    def test_no_history_returns_original(self):
        assert _enrich_with_context("oui", []) == "oui"

    def test_short_history_returns_original(self):
        assert _enrich_with_context("oui", [_msg("user", "salut")]) == "oui"

    def test_enriches_with_last_exchange(self):
        history = [
            _msg("user", "le 7 est sorti combien de fois ?"),
            _msg("assistant", "Le numero 7 est sorti 120 fois."),
        ]
        result = _enrich_with_context("et le 14 ?", history)
        assert "CONTEXTE CONTINUATION" in result
        assert "le 7 est sorti" in result
        assert "et le 14 ?" in result

    def test_missing_assistant_returns_original(self):
        history = [
            _msg("user", "question 1"),
            _msg("user", "question 2"),
        ]
        assert _enrich_with_context("oui", history) == "oui"


# ═══════════════════════════════════════════════════════════════════════
# _clean_response — suppression des tags internes
# ═══════════════════════════════════════════════════════════════════════

class TestCleanResponse:

    def test_strips_resultat_sql(self):
        assert "[RÉSULTAT SQL]" not in _clean_response("[RÉSULTAT SQL] Voici les donnees")

    def test_strips_resultat_tirage(self):
        assert "[RÉSULTAT TIRAGE" not in _clean_response("[RÉSULTAT TIRAGE - 9 février 2026] Boules")

    def test_strips_analyse_grille(self):
        assert "[ANALYSE DE GRILLE" not in _clean_response("[ANALYSE DE GRILLE - 5 15 25] Analyse")

    def test_strips_classement(self):
        assert "[CLASSEMENT" not in _clean_response("[CLASSEMENT - Top 5] Liste")

    def test_strips_numeros_chauds(self):
        assert "[NUMÉROS CHAUDS" not in _clean_response("[NUMÉROS CHAUDS - 16] Liste")

    def test_strips_donnees_temps_reel(self):
        assert "[DONNÉES TEMPS RÉEL" not in _clean_response("[DONNÉES TEMPS RÉEL - 7] Stats")

    def test_strips_prochain_tirage(self):
        assert "[PROCHAIN TIRAGE" not in _clean_response("[PROCHAIN TIRAGE] Samedi")

    def test_strips_page_tag(self):
        assert "[Page:" not in _clean_response("[Page: accueil] Bienvenue")

    def test_strips_question_utilisateur(self):
        assert "[Question utilisateur" not in _clean_response("[Question utilisateur - algo] Explication")

    def test_strips_contexte_continuation(self):
        assert "[CONTEXTE CONTINUATION" not in _clean_response("[CONTEXTE CONTINUATION - suite] Voici")

    def test_collapses_multiple_newlines(self):
        text = "Ligne 1\n\n\n\n\nLigne 2"
        result = _clean_response(text)
        assert "\n\n\n" not in result
        assert "Ligne 1" in result and "Ligne 2" in result

    def test_preserves_normal_text(self):
        text = "Le numero 7 est sorti 120 fois sur 967 tirages."
        assert _clean_response(text) == text


# ═══════════════════════════════════════════════════════════════════════
# _strip_sponsor_from_text
# ═══════════════════════════════════════════════════════════════════════

class TestStripSponsor:

    def test_strips_partenaires(self):
        text = "Reponse normale\n📢 Cet espace est réservé à nos partenaires"
        result = _strip_sponsor_from_text(text)
        assert "partenaires" not in result
        assert "Reponse normale" in result

    def test_strips_espace_partenaire(self):
        text = "Info\n— Espace partenaire disponible"
        result = _strip_sponsor_from_text(text)
        assert "Espace partenaire" not in result

    def test_strips_email(self):
        text = "Texte\nContactez partenariats@lotoia.fr"
        result = _strip_sponsor_from_text(text)
        assert "partenariats@lotoia.fr" not in result

    def test_preserves_clean_text(self):
        text = "Le numero 7 est chaud, essaie-le !"
        assert _strip_sponsor_from_text(text) == text


# ═══════════════════════════════════════════════════════════════════════
# _format_date_fr — edge cases
# ═══════════════════════════════════════════════════════════════════════

class TestFormatDateFr:

    def test_valid_date(self):
        assert _format_date_fr("2026-02-09") == "9 février 2026"

    def test_invalid_string(self):
        assert _format_date_fr("not-a-date") == "not-a-date"

    def test_none_returns_inconnue(self):
        assert _format_date_fr(None) == "inconnue"


# ═══════════════════════════════════════════════════════════════════════
# _format_complex_context — 3 branches
# ═══════════════════════════════════════════════════════════════════════

class TestFormatComplexContext:

    def test_classement(self):
        intent = {"type": "classement", "tri": "frequence_desc", "limit": 3, "num_type": "principal"}
        data = {
            "items": [
                {"numero": 7, "frequence": 120, "ecart_actuel": 3, "categorie": "chaud"},
                {"numero": 14, "frequence": 110, "ecart_actuel": 5, "categorie": "neutre"},
                {"numero": 23, "frequence": 100, "ecart_actuel": 8, "categorie": "froid"},
            ],
            "total_tirages": 967,
            "periode": "2019-11-04 au 2026-02-07",
        }
        result = _format_complex_context(intent, data)
        assert "[CLASSEMENT" in result
        assert "Numéro 7" in result
        assert "120 apparitions" in result

    def test_comparaison(self):
        intent = {"type": "comparaison"}
        data = {
            "num1": {"numero": 7, "frequence_totale": 120, "pourcentage_apparition": "12.4%",
                     "ecart_actuel": 3, "categorie": "chaud"},
            "num2": {"numero": 14, "frequence_totale": 100, "pourcentage_apparition": "10.3%",
                     "ecart_actuel": 8, "categorie": "froid"},
            "diff_frequence": 20,
            "favori_frequence": 7,
        }
        result = _format_complex_context(intent, data)
        assert "[COMPARAISON" in result
        assert "Numéro 7" in result
        assert "Numéro 14" in result

    def test_categorie(self):
        intent = {"type": "categorie"}
        data = {
            "categorie": "chaud",
            "numeros": [{"numero": 7}, {"numero": 14}],
            "count": 2,
            "periode_analyse": "2 dernières années",
        }
        result = _format_complex_context(intent, data)
        assert "CHAUD" in result
        assert "7" in result
