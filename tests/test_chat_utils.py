"""
Tests unitaires pour services/chat_utils.py.
Fonctions de formatage, nettoyage, enrichissement contextuel.
"""

import json
from unittest.mock import MagicMock, patch

from services.chat_utils import (
    _enrich_with_context, _clean_response, _strip_sponsor_from_text,
    _get_sponsor_if_due, _format_date_fr, _format_complex_context,
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

    # ── F05 V86: blocs tool_code / python ────────────────────────────

    def test_strips_tool_code_block(self):
        raw = 'Intéressant !\n```tool_code\nfrom datetime import datetime\nresult = execute_sql("SELECT")\n```\n'
        cleaned = _clean_response(raw)
        assert "tool_code" not in cleaned
        assert "import" not in cleaned
        assert "execute_sql" not in cleaned

    def test_strips_python_block(self):
        raw = 'Voici :\n```python\ndef foo():\n    pass\n```\n'
        cleaned = _clean_response(raw)
        assert "```python" not in cleaned
        assert "def foo" not in cleaned

    def test_strips_truncated_tool_code(self):
        raw = 'Un instant...\n```tool_code\nfrom datetime import datetime\nresult = execute_sql("SELECT'
        cleaned = _clean_response(raw)
        assert "tool_code" not in cleaned
        assert "execute_sql" not in cleaned

    def test_fallback_after_code_removal(self):
        raw = '```tool_code\nimport os\nos.listdir()\n```'
        cleaned = _clean_response(raw)
        assert len(cleaned) > 10
        assert "tool_code" not in cleaned
        assert "import" not in cleaned

    def test_code_removal_preserves_surrounding_text(self):
        raw = 'Le 7 est sorti 142 fois.\n```tool_code\nimport os\n```\nBonne question !'
        cleaned = _clean_response(raw)
        assert "142 fois" in cleaned
        assert "Bonne question" in cleaned
        assert "tool_code" not in cleaned


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


# ═══════════════════════════════════════════════════════════════════════
# _get_sponsor_if_due — rotation A/B
# ═══════════════════════════════════════════════════════════════════════

_SPONSORS_V2 = {
    "version": 3,
    "enabled": True,
    "frequency": 3,
    "slots": {
        "loto_fr": {
            "slot_a": {
                "id": "LOTO_FR_A", "tier": "premium", "name": "Espace Premium",
                "tagline": {"fr": "Espace premium partenaire officiel", "en": "Premium official partner"},
                "url": "mailto:partenariats@lotoia.fr", "active": True,
            },
            "slot_b": {
                "id": "LOTO_FR_B", "tier": "standard", "name": "Espace Standard",
                "tagline": {"fr": "Espace partenaires", "en": "Partner space"},
                "url": "mailto:partenariats@lotoia.fr", "active": True,
            },
        },
        "em_fr": {
            "slot_a": {
                "id": "EM_FR_A", "tier": "premium", "name": "Espace Premium EM",
                "tagline": {"fr": "Espace premium EuroMillions partenaire officiel"},
                "url": "mailto:partenariats@lotoia.fr", "active": True,
            },
            "slot_b": {
                "id": "EM_FR_B", "tier": "standard", "name": "Espace Standard EM",
                "tagline": {"fr": "Espace EuroMillions partenaires"},
                "url": "mailto:partenariats@lotoia.fr", "active": True,
            },
        },
        "em_en": {
            "slot_a": {
                "id": "EM_EN_A", "tier": "premium", "name": "Premium EM Space",
                "tagline": {"en": "Premium EuroMillions official partner"},
                "url": "mailto:partenariats@lotoia.fr", "active": True,
            },
            "slot_b": {
                "id": "EM_EN_B", "tier": "standard", "name": "Standard EM Space",
                "tagline": {"en": "EuroMillions partner space"},
                "url": "mailto:partenariats@lotoia.fr", "active": True,
            },
        },
        "em_pt": {
            "slot_a": {
                "id": "EM_PT_A", "tier": "premium", "name": "Espaco Premium EM",
                "tagline": {"pt": "Espaco premium EuroMillions parceiro oficial"},
                "url": "mailto:partenariats@lotoia.fr", "active": True,
            },
            "slot_b": {
                "id": "EM_PT_B", "tier": "standard", "name": "Espaco Standard EM",
                "tagline": {"pt": "Espaco EuroMillions parceiros"},
                "url": "mailto:partenariats@lotoia.fr", "active": True,
            },
        },
    },
}


def _reset_sponsor_cache():
    """Reset the module-level sponsor config cache."""
    import services.chat_utils as mod
    mod._sponsors_config = None


class TestGetSponsorIfDue:

    def setup_method(self):
        _reset_sponsor_cache()

    def teardown_method(self):
        _reset_sponsor_cache()

    def _history(self, n_bot):
        """Build a fake history with n_bot assistant messages."""
        h = []
        for _ in range(n_bot):
            h.append(_msg("user", "question"))
            h.append(_msg("assistant", "reponse"))
        return h

    def test_3_bot_messages_returns_slot_a(self):
        with patch("services.chat_utils._load_sponsors_config", return_value=_SPONSORS_V2):
            result = _get_sponsor_if_due(self._history(2), lang="fr")
            assert result is not None
            assert "[SPONSOR:LOTO_FR_A]" in result

    def test_6_bot_messages_returns_slot_b(self):
        with patch("services.chat_utils._load_sponsors_config", return_value=_SPONSORS_V2):
            result = _get_sponsor_if_due(self._history(5), lang="fr")
            assert result is not None
            assert "[SPONSOR:LOTO_FR_B]" in result

    def test_9_bot_messages_returns_slot_a_again(self):
        with patch("services.chat_utils._load_sponsors_config", return_value=_SPONSORS_V2):
            result = _get_sponsor_if_due(self._history(8), lang="fr")
            assert result is not None
            assert "[SPONSOR:LOTO_FR_A]" in result

    def test_12_bot_messages_returns_slot_b_again(self):
        with patch("services.chat_utils._load_sponsors_config", return_value=_SPONSORS_V2):
            result = _get_sponsor_if_due(self._history(11), lang="fr")
            assert result is not None
            assert "[SPONSOR:LOTO_FR_B]" in result

    def test_2_bot_messages_returns_none(self):
        with patch("services.chat_utils._load_sponsors_config", return_value=_SPONSORS_V2):
            result = _get_sponsor_if_due(self._history(1), lang="fr")
            assert result is None

    def test_disabled_returns_none(self):
        config = {**_SPONSORS_V2, "enabled": False}
        with patch("services.chat_utils._load_sponsors_config", return_value=config):
            result = _get_sponsor_if_due(self._history(2), lang="fr")
            assert result is None

    def test_slot_a_inactive_falls_back_to_b(self):
        config = json.loads(json.dumps(_SPONSORS_V2))
        config["slots"]["loto_fr"]["slot_a"]["active"] = False
        with patch("services.chat_utils._load_sponsors_config", return_value=config):
            result = _get_sponsor_if_due(self._history(2), lang="fr")
            assert result is not None
            assert "[SPONSOR:LOTO_FR_B]" in result

    def test_english_lang_uses_en_tagline(self):
        with patch("services.chat_utils._load_sponsors_config", return_value=_SPONSORS_V2):
            result = _get_sponsor_if_due(self._history(2), lang="en")
            assert "Premium official partner" in result

    def test_contains_email(self):
        with patch("services.chat_utils._load_sponsors_config", return_value=_SPONSORS_V2):
            result = _get_sponsor_if_due(self._history(2), lang="fr")
            assert "partenariats@lotoia.fr" in result

    # ── EM module tests ──────────────────────────────────────────────

    def test_em_fr_3_bot_messages_returns_em_fr_a(self):
        with patch("services.chat_utils._load_sponsors_config", return_value=_SPONSORS_V2):
            result = _get_sponsor_if_due(self._history(2), lang="fr", module="em")
            assert result is not None
            assert "[SPONSOR:EM_FR_A]" in result

    def test_em_en_3_bot_messages_returns_em_en_a(self):
        with patch("services.chat_utils._load_sponsors_config", return_value=_SPONSORS_V2):
            result = _get_sponsor_if_due(self._history(2), lang="en", module="em")
            assert result is not None
            assert "[SPONSOR:EM_EN_A]" in result

    def test_em_pt_6_bot_messages_returns_em_pt_b(self):
        with patch("services.chat_utils._load_sponsors_config", return_value=_SPONSORS_V2):
            result = _get_sponsor_if_due(self._history(5), lang="pt", module="em")
            assert result is not None
            assert "[SPONSOR:EM_PT_B]" in result

    def test_em_unknown_lang_returns_none(self):
        with patch("services.chat_utils._load_sponsors_config", return_value=_SPONSORS_V2):
            result = _get_sponsor_if_due(self._history(2), lang="ja", module="em")
            assert result is None

    def test_em_module_does_not_use_loto_slots(self):
        with patch("services.chat_utils._load_sponsors_config", return_value=_SPONSORS_V2):
            result = _get_sponsor_if_due(self._history(2), lang="fr", module="em")
            assert "LOTO_FR" not in result


# ─────────────────────────────────────────────────────────────────────────────
# V125 Sous-phase 1 — Couverture 14/14 patterns code-leak (audit V124 tableau B.2)
# Cas déclencheur : log chat_log#2093 (19/04/2026, Loto FR) — leak ```sql + ```json[
# ─────────────────────────────────────────────────────────────────────────────

class TestV125CodeLeak:
    """V125 Sous-phase 1 : _RE_CODE_BLOCK doit stripper 14/14 patterns du tableau B.2."""

    def test_strips_python_single_line(self):
        """B.2 pattern #1 — ```python x=1``` single-line avec espace (nouveau V125)."""
        result = _clean_response("Voici: ```python x=1```")
        assert "```" not in result
        assert "x=1" not in result

    def test_strips_python_multiline(self):
        """B.2 pattern #2 — ```python\\ncode\\n``` (V86 existant, non-régression)."""
        raw = "Voici :\n```python\ndef foo():\n    pass\n```\n"
        result = _clean_response(raw)
        assert "```python" not in result
        assert "def foo" not in result

    def test_strips_tool_code(self):
        """B.2 pattern #3 — ```tool_code\\n…\\n``` (V86 existant, non-régression)."""
        raw = "Un instant...\n```tool_code\nfrom datetime import datetime\n```"
        result = _clean_response(raw)
        assert "tool_code" not in result

    def test_strips_sql_lowercase(self):
        """B.2 pattern #4 — ```sql\\nSELECT…``` (CAS #2093 premier bloc)."""
        raw = "```sql\nSELECT * FROM tirages WHERE boule_1 = 30\n```"
        result = _clean_response(raw)
        assert "SELECT" not in result
        assert "tirages" not in result

    def test_strips_sql_uppercase(self):
        """B.2 pattern #5 — ```SQL majuscules (case-insensitive V125)."""
        raw = "```SQL\nSELECT 1\n```"
        result = _clean_response(raw)
        assert "SELECT" not in result

    def test_strips_json_block(self):
        """B.2 pattern #6 — ```json\\n[…]\\n```."""
        raw = '```json\n[{"Date": "2024-01-01"}]\n```'
        result = _clean_response(raw)
        assert "Date" not in result
        assert "2024" not in result

    def test_strips_json_bracket_glued(self):
        """B.2 pattern #7 — ```json[ crochet collé (CAS #2093 second bloc)."""
        raw = '```json[\n{"Date": "12 février 2024", "N1": 4}\n]```'
        result = _clean_response(raw)
        assert "Date" not in result
        assert "février" not in result

    def test_strips_javascript(self):
        """B.2 pattern #8 — ```javascript\\ncode\\n```."""
        raw = "```javascript\nconsole.log(1)\n```"
        result = _clean_response(raw)
        assert "console" not in result

    def test_strips_js_short(self):
        """B.2 pattern #8b — ```js\\ncode\\n```."""
        raw = "```js\nconsole.log('secret')\n```"
        result = _clean_response(raw)
        assert "console" not in result
        assert "secret" not in result

    def test_strips_plaintext(self):
        """B.2 pattern #9 — ```plaintext\\n…\\n```."""
        raw = "```plaintext\nSECRET_TOKEN=abc123\n```"
        result = _clean_response(raw)
        assert "SECRET_TOKEN" not in result

    def test_strips_bare_fence(self):
        """B.2 pattern #10 — ```\\ncode\\n``` fence nu sans langage."""
        raw = "Voici le code:\n```\nrm -rf /\n```\nFin."
        result = _clean_response(raw)
        assert "rm -rf" not in result

    def test_strips_truncated_sql(self):
        """B.2 pattern #11 — ```sql tronqué sans closing ``` (CAS #2093 stream coupé)."""
        raw = "Un instant...\n```sql\nSELECT * FROM tirages WHERE"
        result = _clean_response(raw)
        assert "SELECT" not in result
        assert "tirages" not in result

    def test_strips_truncated_json(self):
        """B.2 pattern #11b — ```json[ tronqué (CAS #2093)."""
        raw = '```json[\n{"Date": "12 février 2024", "N1":'
        result = _clean_response(raw)
        assert "Date" not in result

    def test_strips_multi_blocks_sql_json(self):
        """B.2 pattern #12 — multi code blocks SQL + JSON (CAS #2093 complet)."""
        raw = (
            '```sql\nSELECT * FROM tirages\n```\n'
            '```json[\n{"Date": "2024", "N1": 4}\n]```'
        )
        result = _clean_response(raw)
        assert "SELECT" not in result
        assert "tirages" not in result
        assert "Date" not in result

    def test_preserves_inline_backticks(self):
        """B.2 pattern #14 — backticks inline (simple `x`) NE doivent PAS être strippés (anti-FP)."""
        raw = "La variable `x` vaut 3 et `y` est défini aussi."
        result = _clean_response(raw)
        assert "`x`" in result
        assert "`y`" in result
        assert "3" in result


class TestV125Scenario2093:
    """V125 — Reproduction du cas exact chat_log#2093 (19/04/2026, Loto FR)."""

    def test_scenario_2093_fully_stripped(self):
        """Reproduit la réponse Gemini leakée dans log#2093. Aucun artefact ne doit subsister."""
        gemini_response_2093 = (
            '```sql\n'
            'SELECT\n'
            ' date_tirage AS "Date",\n'
            ' num_1 AS "N1",\n'
            ' num_2 AS "N2",\n'
            ' num_3 AS "N3",\n'
            ' num_4 AS "N4",\n'
            ' num_5 AS "N5",\n'
            ' num_chance AS "Chance"\n'
            'FROM\n'
            ' tirages\n'
            'WHERE\n'
            ' num_1 = 30 OR num_2 = 30 OR num_3 = 30 OR num_4 = 30 OR num_5 = 30\n'
            'ORDER BY\n'
            ' date_tirage DESC\n'
            'LIMIT\n'
            ' 5;\n'
            '```\n'
            '```json[\n'
            ' {\n'
            ' "Date": "12 février 2024",\n'
            ' "N1": 4,\n'
            ' "N2": 10,\n'
            ' "N3": 27,\n'
            ' "N4": 30,\n'
            ' "N5": 41,\n'
            ' "Chance": 4\n'
            ' },\n'
            ' {\n'
            ' "Date": "27 décembre 2023",\n'
            ' "N1": 6,\n'
            ' "N2": 26,\n'
            ' "N3": 30,\n'
            ' "N4": 32,\n'
            ' "N5": 47,\n'
            ' "'
        )
        cleaned = _clean_response(gemini_response_2093)
        # Tous les artefacts SQL doivent disparaître
        assert "SELECT" not in cleaned
        assert "FROM" not in cleaned
        assert "tirages" not in cleaned
        assert "date_tirage" not in cleaned
        assert "num_1" not in cleaned
        assert "num_chance" not in cleaned
        # Tous les artefacts JSON doivent disparaître
        assert "```" not in cleaned
        assert '"Date"' not in cleaned
        assert "février" not in cleaned
        assert "décembre" not in cleaned
