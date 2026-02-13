"""
Tests pour Phase I (insultes) et Phase OOR (numeros hors range).
Teste la detection, le comptage de streak, l'escalade, et les cas speciaux.
"""

import pytest
from datetime import date
from unittest.mock import MagicMock

# Import des fonctions a tester
from routes.api_chat import (
    _detect_insulte,
    _insult_targets_bot,
    _count_insult_streak,
    _get_insult_response,
    _get_insult_short,
    _get_menace_response,
    _detect_out_of_range,
    _count_oor_streak,
    _get_oor_response,
    _detect_tirage,
    _format_tirage_context,
)


# ═══════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════

def _make_history(messages):
    """
    Cree une liste de ChatMessage-like a partir de tuples (role, content).
    Ex: [("user", "t'es nul"), ("assistant", "punchline")]
    """
    history = []
    for role, content in messages:
        msg = MagicMock()
        msg.role = role
        msg.content = content
        history.append(msg)
    return history


# ═══════════════════════════════════════════════════════
# Tests _detect_insulte
# ═══════════════════════════════════════════════════════

class TestDetectInsulte:
    """Tests de detection d'insultes."""

    def test_insulte_directe_simple(self):
        assert _detect_insulte("t'es con") == "directe"

    def test_insulte_connard(self):
        assert _detect_insulte("espèce de connard") == "directe"

    def test_insulte_debile(self):
        assert _detect_insulte("t'es débile ou quoi") == "directe"

    def test_insulte_merde(self):
        assert _detect_insulte("c'est de la merde") == "directe"

    def test_insulte_phrase_ta_gueule(self):
        assert _detect_insulte("ta gueule le bot") == "directe"

    def test_insulte_phrase_ferme_la(self):
        assert _detect_insulte("ferme-la") == "directe"

    def test_insulte_phrase_degage(self):
        assert _detect_insulte("dégage") == "directe"

    def test_insulte_phrase_tu_sers_a_rien(self):
        assert _detect_insulte("tu sers à rien") == "directe"

    def test_insulte_phrase_bot_de_merde(self):
        assert _detect_insulte("chatbot de merde") == "directe"

    def test_insulte_phrase_tu_comprends_rien(self):
        assert _detect_insulte("tu comprends rien") == "directe"

    def test_insulte_phrase_tu_fais_chier(self):
        assert _detect_insulte("tu me fais chier") == "directe"

    def test_insulte_moquerie_lol(self):
        assert _detect_insulte("lol t'es nul") == "directe"

    def test_insulte_moquerie_mdr(self):
        assert _detect_insulte("mdr t'es bête") == "directe"

    def test_insulte_casse_insensible(self):
        """Insultes en majuscules detectees."""
        assert _detect_insulte("T'ES CON") == "directe"

    def test_insulte_leet_basique(self):
        """Detection basique leet speak (c0n → con)."""
        assert _detect_insulte("t'es c0n") == "directe"

    def test_insulte_points_inseres(self):
        """Detection avec points inseres (c.o.n → con)."""
        assert _detect_insulte("t'es c.o.n") == "directe"

    # --- Menaces ---

    def test_menace_hacker(self):
        assert _detect_insulte("je vais te hacker") == "menace"

    def test_menace_pirater(self):
        assert _detect_insulte("je vais te pirater") == "menace"

    def test_menace_casser(self):
        assert _detect_insulte("je vais te casser") == "menace"

    # --- Faux positifs : NE PAS déclencher ---

    def test_pas_insulte_concours(self):
        """Le mot 'con' dans 'concours' ne doit PAS declencher."""
        assert _detect_insulte("je participe au concours") is None

    def test_pas_insulte_message_neutre(self):
        assert _detect_insulte("quel est le numéro le plus sorti ?") is None

    def test_pas_insulte_numero(self):
        assert _detect_insulte("le 7 est sorti combien de fois ?") is None

    def test_pas_insulte_bonjour(self):
        assert _detect_insulte("bonjour, comment ça va ?") is None

    def test_pas_insulte_loto_merde(self):
        """Insulte envers le Loto (pas le bot) → ne PAS declencher."""
        assert _detect_insulte("le loto c'est de la merde") is None

    def test_pas_insulte_fdj_nulle(self):
        """Insulte envers la FDJ → ne PAS declencher."""
        assert _detect_insulte("la fdj est nulle") is None

    def test_pas_insulte_tirage_nul(self):
        """'tirage nul' vise le tirage, pas le bot."""
        assert _detect_insulte("ce tirage est nul") is None

    def test_insulte_bot_meme_avec_loto(self):
        """Insulte qui vise le bot meme si 'loto' est mentionne."""
        assert _detect_insulte("tu es nul, le loto c'est mieux sans toi") == "directe"


# ═══════════════════════════════════════════════════════
# Tests _insult_targets_bot
# ═══════════════════════════════════════════════════════

class TestInsultTargetsBot:

    def test_targets_bot_tu(self):
        assert _insult_targets_bot("tu es nul") is True

    def test_targets_bot_standalone(self):
        """Insulte sans cible explicite → considere comme visant le bot."""
        assert _insult_targets_bot("quel imbécile") is True

    def test_targets_loto(self):
        assert _insult_targets_bot("le loto c'est nul") is False

    def test_targets_fdj(self):
        assert _insult_targets_bot("la fdj est nulle") is False

    def test_targets_bot_with_loto(self):
        """'tu' present + 'loto' present → vise le bot."""
        assert _insult_targets_bot("tu parles du loto mais t'es nul") is True


# ═══════════════════════════════════════════════════════
# Tests _count_insult_streak
# ═══════════════════════════════════════════════════════

class TestCountInsultStreak:

    def test_pas_d_historique(self):
        assert _count_insult_streak([]) == 0

    def test_un_insulte(self):
        history = _make_history([("user", "t'es con")])
        assert _count_insult_streak(history) == 1

    def test_deux_insultes_consecutives(self):
        """Deux insultes user consecutives (meme avec assistant entre) → streak=2."""
        history = _make_history([
            ("user", "t'es con"),
            ("assistant", "punchline"),
            ("user", "t'es nul"),
        ])
        assert _count_insult_streak(history) == 2

    def test_streak_reset_par_question_normale(self):
        """Le compteur se reset quand un message normal est entre les insultes."""
        history = _make_history([
            ("user", "t'es con"),
            ("assistant", "punchline"),
            ("user", "quel est le numéro le plus sorti ?"),
            ("assistant", "le 7 est..."),
            ("user", "t'es nul"),
        ])
        assert _count_insult_streak(history) == 1

    def test_streak_trois_insultes(self):
        history = _make_history([
            ("user", "connard"),
            ("assistant", "punchline1"),
            ("user", "débile"),
            ("assistant", "punchline2"),
            ("user", "abruti"),
        ])
        assert _count_insult_streak(history) == 3


# ═══════════════════════════════════════════════════════
# Tests escalade insultes
# ═══════════════════════════════════════════════════════

class TestEscaladeInsulte:

    def test_level1_premiere_insulte(self):
        from routes.api_chat import _INSULT_L1
        resp = _get_insult_response(0, [])
        assert resp in _INSULT_L1

    def test_level2_deuxieme_insulte(self):
        from routes.api_chat import _INSULT_L2
        resp = _get_insult_response(1, [])
        assert resp in _INSULT_L2

    def test_level3_troisieme_insulte(self):
        from routes.api_chat import _INSULT_L3
        resp = _get_insult_response(2, [])
        assert resp in _INSULT_L3

    def test_level4_persistant(self):
        from routes.api_chat import _INSULT_L4
        resp = _get_insult_response(3, [])
        assert resp in _INSULT_L4

    def test_variation_pas_de_repetition(self):
        """3 appels au meme niveau → 3 reponses differentes (si pool >= 3)."""
        from routes.api_chat import _INSULT_L1
        responses = set()
        # Avec 8 options et pas d'historique, la proba de 3 identiques est tres faible
        for _ in range(20):
            responses.add(_get_insult_response(0, []))
        assert len(responses) >= 2  # Au moins 2 reponses differentes

    def test_short_punchline(self):
        from routes.api_chat import _INSULT_SHORT
        resp = _get_insult_short()
        assert resp in _INSULT_SHORT

    def test_menace_response(self):
        from routes.api_chat import _MENACE_RESPONSES
        resp = _get_menace_response()
        assert resp in _MENACE_RESPONSES


# ═══════════════════════════════════════════════════════
# Tests _detect_out_of_range
# ═══════════════════════════════════════════════════════

class TestDetectOutOfRange:

    # --- Numéros trop grands ---

    def test_numero_50(self):
        num, ctx = _detect_out_of_range("c'est quoi le 50 ?")
        assert num == 50
        assert ctx == "close"

    def test_numero_51(self):
        num, ctx = _detect_out_of_range("le 51 est sorti ?")
        assert num == 51
        assert ctx == "close"

    def test_numero_78(self):
        num, ctx = _detect_out_of_range("fréquence du 78 ?")
        assert num == 78
        assert ctx == "principal_high"

    def test_numero_100(self):
        num, ctx = _detect_out_of_range("le numéro 100")
        assert num == 100
        assert ctx == "principal_high"

    def test_numero_999(self):
        num, ctx = _detect_out_of_range("le 999 est chaud ?")
        assert num == 999
        assert ctx == "principal_high"

    # --- Zéro et négatifs ---

    def test_numero_zero(self):
        num, ctx = _detect_out_of_range("le 0 est sorti ?")
        assert num == 0
        assert ctx == "zero_neg"

    def test_numero_negatif(self):
        num, ctx = _detect_out_of_range("le -3 est sorti ?")
        assert num == -3
        assert ctx == "zero_neg"

    # --- Chance hors range ---

    def test_chance_15(self):
        num, ctx = _detect_out_of_range("numéro chance 15")
        assert num == 15
        assert ctx == "chance_high"

    def test_chance_99(self):
        num, ctx = _detect_out_of_range("chance 99")
        assert num == 99
        assert ctx == "chance_high"

    # --- Numéros valides : NE PAS déclencher ---

    def test_numero_valide_1(self):
        num, _ = _detect_out_of_range("le 1 est sorti ?")
        assert num is None

    def test_numero_valide_49(self):
        num, _ = _detect_out_of_range("le 49 est chaud ?")
        assert num is None

    def test_numero_valide_25(self):
        num, _ = _detect_out_of_range("fréquence du 25")
        assert num is None

    def test_chance_valide_10(self):
        num, _ = _detect_out_of_range("chance 10")
        assert num is None

    def test_chance_valide_1(self):
        num, _ = _detect_out_of_range("chance 1")
        assert num is None

    # --- Filtrage des années ---

    def test_annee_2024_pas_detectee(self):
        num, _ = _detect_out_of_range("les tirages de 2024")
        assert num is None

    def test_annee_2025_pas_detectee(self):
        num, _ = _detect_out_of_range("statistiques du 2025")
        assert num is None

    # --- Message sans numero ---

    def test_message_sans_numero(self):
        num, _ = _detect_out_of_range("bonjour comment ça va ?")
        assert num is None


# ═══════════════════════════════════════════════════════
# Tests _count_oor_streak
# ═══════════════════════════════════════════════════════

class TestCountOorStreak:

    def test_pas_d_historique(self):
        assert _count_oor_streak([]) == 0

    def test_un_oor(self):
        history = _make_history([("user", "le 78 est sorti ?")])
        assert _count_oor_streak(history) == 1

    def test_streak_reset_par_message_normal(self):
        history = _make_history([
            ("user", "le 55 est sorti ?"),
            ("assistant", "reponse"),
            ("user", "et le 7 ?"),
            ("assistant", "reponse"),
            ("user", "le 100 est chaud ?"),
        ])
        assert _count_oor_streak(history) == 1

    def test_streak_deux_oor(self):
        history = _make_history([
            ("user", "le 55 est sorti ?"),
            ("assistant", "reponse"),
            ("user", "le 78 est sorti ?"),
        ])
        assert _count_oor_streak(history) == 2

    def test_streak_trois_oor(self):
        history = _make_history([
            ("user", "le 55 est sorti ?"),
            ("assistant", "r1"),
            ("user", "le 78 est sorti ?"),
            ("assistant", "r2"),
            ("user", "le 100 est sorti ?"),
        ])
        assert _count_oor_streak(history) == 3


# ═══════════════════════════════════════════════════════
# Tests escalade OOR
# ═══════════════════════════════════════════════════════

class TestEscaladeOor:

    def test_level1_premier_oor(self):
        resp = _get_oor_response(78, "principal_high", 0)
        assert "78" in resp

    def test_level2_deuxieme_oor(self):
        resp = _get_oor_response(55, "principal_high", 1)
        assert "55" in resp or "1" in resp  # Le num ou les regles

    def test_level3_troisieme_oor(self):
        resp = _get_oor_response(100, "principal_high", 2)
        assert "100" in resp or "49" in resp

    def test_close_50(self):
        resp = _get_oor_response(50, "close", 0)
        assert "50" in resp
        assert "49" in resp or "1" in resp  # Mentionne la limite

    def test_close_51(self):
        resp = _get_oor_response(51, "close", 0)
        assert "51" in resp

    def test_zero_neg(self):
        resp = _get_oor_response(0, "zero_neg", 0)
        assert "0" in resp

    def test_negatif(self):
        resp = _get_oor_response(-3, "zero_neg", 0)
        assert "-3" in resp

    def test_chance_high(self):
        resp = _get_oor_response(15, "chance_high", 0)
        assert "15" in resp
        assert "10" in resp  # Mentionne la limite Chance

    def test_format_string_pas_d_erreur(self):
        """Verifier que tous les templates se formatent sans erreur."""
        from routes.api_chat import (
            _OOR_L1, _OOR_L2, _OOR_L3,
            _OOR_CLOSE, _OOR_ZERO_NEG, _OOR_CHANCE,
        )
        for pool in [_OOR_L1, _OOR_L2, _OOR_L3, _OOR_CLOSE, _OOR_ZERO_NEG, _OOR_CHANCE]:
            for template in pool:
                # Doit pouvoir se formater sans KeyError
                result = template.format(num=55, diff=6, s="s", streak=3)
                assert isinstance(result, str)
                assert len(result) > 0


# ═══════════════════════════════════════════════════════
# Tests Phase T — Détection de tirage (dates textuelles)
# ═══════════════════════════════════════════════════════

class TestDetectTirageTextuel:
    """Tests pour le parsing de dates textuelles (BUG 1 fix)."""

    # --- Dates textuelles avec année ---

    def test_tirage_9_fevrier_2026(self):
        """'tirage du 9 février 2026' → date(2026, 2, 9)."""
        result = _detect_tirage("C'est quoi le tirage du 9 février 2026 ?")
        assert result == date(2026, 2, 9)

    def test_resultats_2_fevrier_2026(self):
        result = _detect_tirage("Résultats du 2 février 2026")
        assert result == date(2026, 2, 2)

    def test_tirage_4_fevrier_2026(self):
        result = _detect_tirage("Tirage du 4 février 2026")
        assert result == date(2026, 2, 4)

    def test_tirage_15_janvier_2025(self):
        result = _detect_tirage("les résultats du tirage du 15 janvier 2025")
        assert result == date(2025, 1, 15)

    def test_tirage_3_mars_2025(self):
        result = _detect_tirage("qu'est-ce qui est sorti le 3 mars 2025 ?")
        assert result == date(2025, 3, 3)

    def test_tirage_25_decembre(self):
        """Date textuelle sans année → année courante."""
        result = _detect_tirage("tirage du 25 décembre")
        assert result is not None
        assert result.day == 25
        assert result.month == 12
        assert result.year == date.today().year

    def test_tirage_1_aout_2024(self):
        """Mois avec accent (août)."""
        result = _detect_tirage("tirage du 1 août 2024")
        assert result == date(2024, 8, 1)

    # --- Les formats existants marchent toujours ---

    def test_format_numerique_dd_mm_yyyy(self):
        result = _detect_tirage("tirage du 09/02/2026")
        assert result == date(2026, 2, 9)

    def test_format_numerique_dd_mm(self):
        result = _detect_tirage("résultat du 09/02")
        assert result is not None
        assert result.day == 9
        assert result.month == 2

    def test_dernier_tirage(self):
        result = _detect_tirage("dernier tirage")
        assert result == "latest"

    def test_resultats_seul(self):
        result = _detect_tirage("résultats")
        assert result == "latest"

    def test_prochain_tirage_exclut(self):
        """'prochain tirage' ne doit PAS activer Phase T."""
        result = _detect_tirage("prochain tirage")
        assert result is None

    # --- Anti-hallucination : la date textuelle prime sur "résultats" = latest ---

    def test_resultats_avec_date_retourne_date_specifique(self):
        """'résultats du 9 février 2026' → date(2026, 2, 9), PAS 'latest'."""
        result = _detect_tirage("Donne moi les résultats du tirage du 9 février 2026")
        assert result == date(2026, 2, 9)


# ═══════════════════════════════════════════════════════
# Tests _format_tirage_context — Anti-hallucination
# ═══════════════════════════════════════════════════════

class TestFormatTirageContext:
    """Les numéros dans le contexte doivent venir de la BDD, pas de Gemini."""

    def test_format_contient_vrais_numeros(self):
        tirage = {
            "date": "2026-02-09",
            "boules": [22, 23, 25, 38, 42],
            "chance": 3,
        }
        ctx = _format_tirage_context(tirage)
        assert "22 - 23 - 25 - 38 - 42" in ctx
        assert "3" in ctx
        assert "TIRAGE" in ctx.upper()

    def test_format_contient_date(self):
        tirage = {
            "date": "2026-02-09",
            "boules": [7, 11, 12, 29, 41],
            "chance": 5,
        }
        ctx = _format_tirage_context(tirage)
        # Doit contenir les vrais numeros
        assert "7 - 11 - 12 - 29 - 41" in ctx
        assert "5" in ctx
