"""
Tests de régression — synonymes Numéro Chance (Loto) + Étoiles (EM)
et correction SSE word-collage (StreamBuffer).

Protège les fixes :
- "complémentaire", "bonus", "spécial" → chance (Loto) / étoile (EM)
- StreamBuffer.strip('\n\r') au lieu de .strip() → pas de mots collés
"""

import pytest

from services.chat_detectors import (
    _is_chance_query, _detect_numero, _detect_grille,
    _detect_requete_complexe, _detect_out_of_range,
)
from services.chat_detectors_em import (
    _is_star_query, _detect_numero_em, _detect_grille_em,
    _detect_requete_complexe_em, _detect_out_of_range_em,
)
from services.chat_utils import _clean_response, StreamBuffer


# ═══════════════════════════════════════════════════════════════════════
# 1. SSE StreamBuffer — word-collage regression
# ═══════════════════════════════════════════════════════════════════════

class TestStreamBufferWordCollage:
    """Le bug : .strip() mangeait les espaces aux bords des chunks SSE,
    produisant 'Jene peux pas' au lieu de 'Je ne peux pas'."""

    def _stream(self, chunks):
        buf = StreamBuffer()
        result = ""
        for c in chunks:
            safe = buf.add_chunk(c)
            if safe:
                result += safe
        remaining = buf.flush()
        if remaining:
            result += remaining
        return result

    def test_basic_word_spacing(self):
        result = self._stream(["Je ", "ne peux pas ", "prédire."])
        assert "Je ne peux pas" in result

    def test_direction_la_page(self):
        result = self._stream(["Direction ", "la page ", "des résultats."])
        assert "Direction la page" in result

    def test_le_numero(self):
        result = self._stream(["Le ", "numéro 31 ", "est chaud."])
        assert "Le numéro 31" in result

    def test_single_chunk(self):
        result = self._stream(["Bonjour le monde."])
        assert result.strip() == "Bonjour le monde."

    def test_tag_removal_preserves_spacing(self):
        result = self._stream(["Le ", "[DONNÉES TEMPS RÉEL]", " numéro 31."])
        assert "numéro 31" in result
        # Le tag est supprimé, pas de collage
        assert "[DONNÉES" not in result

    def test_newlines_still_collapsed(self):
        assert "\n\n\n" not in _clean_response("Hello\n\n\n\n\nWorld")
        assert "Hello\n\nWorld" == _clean_response("Hello\n\n\n\n\nWorld")


# ═══════════════════════════════════════════════════════════════════════
# 2. Loto — _is_chance_query + synonymes
# ═══════════════════════════════════════════════════════════════════════

class TestIsChanceQuery:

    @pytest.mark.parametrize("msg", [
        "numéro chance le plus fréquent",
        "quel est le numéro complémentaire le plus fréquent",
        "le complementaire le plus sorti",
        "numéro bonus le plus sorti",
        "numéro spécial le plus fréquent",
        "le special le plus chaud",
    ])
    def test_synonyms_detected(self, msg):
        assert _is_chance_query(msg.lower())

    def test_principal_not_detected(self):
        assert not _is_chance_query("quel numéro sort le plus")


class TestDetectNumeroChanceSynonyms:

    @pytest.mark.parametrize("msg,expected_num", [
        ("chance 7", 7),
        ("complémentaire 3", 3),
        ("complementaire 5", 5),
        ("bonus 2", 2),
        ("spécial 8", 8),
        ("special 1", 1),
    ])
    def test_synonym_returns_chance(self, msg, expected_num):
        num, type_num = _detect_numero(msg)
        assert num == expected_num
        assert type_num == "chance"


class TestDetectGrilleChanceSynonyms:

    def test_bonus_keyword(self):
        nums, chance = _detect_grille("5 12 23 34 45 bonus 7")
        assert nums == [5, 12, 23, 34, 45]
        assert chance == 7

    def test_complementaire_keyword(self):
        nums, chance = _detect_grille("5 12 23 34 45 complémentaire 3")
        assert nums == [5, 12, 23, 34, 45]
        assert chance == 3


class TestRequeteComplexeChanceSynonyms:
    """Le bug Ecosia : 'quel est le numéro complémentaire le plus fréquent'
    retournait num_type='principal' au lieu de 'chance'."""

    @pytest.mark.parametrize("msg", [
        "quel est le numéro complémentaire le plus fréquent",
        "numéro bonus le plus sorti",
        "numéro spécial le plus fréquent",
        "numéro chance le plus sorti",
    ])
    def test_classement_chance(self, msg):
        result = _detect_requete_complexe(msg)
        assert result is not None
        assert result["num_type"] == "chance"
        assert result["tri"] == "frequence_desc"

    @pytest.mark.parametrize("msg", [
        "numéros complémentaires les plus chauds",
        "numéros bonus les plus chauds",
    ])
    def test_categorie_chaud_chance(self, msg):
        result = _detect_requete_complexe(msg)
        assert result is not None
        assert result["num_type"] == "chance"
        assert result["categorie"] == "chaud"

    def test_principal_unchanged(self):
        result = _detect_requete_complexe("les numéros les plus sortis")
        assert result is not None
        assert result["num_type"] == "principal"


class TestOORChanceSynonyms:

    @pytest.mark.parametrize("msg,expected", [
        ("complémentaire 15", 15),
        ("bonus 20", 20),
    ])
    def test_oor_chance_synonym(self, msg, expected):
        num, ctx = _detect_out_of_range(msg)
        assert num == expected
        assert ctx == "chance_high"


# ═══════════════════════════════════════════════════════════════════════
# 3. EM — _is_star_query + synonymes (6 langues)
# ═══════════════════════════════════════════════════════════════════════

class TestIsStarQuery:

    @pytest.mark.parametrize("msg", [
        # FR
        "numéro complémentaire le plus fréquent",
        "quelle étoile sort le plus",
        "numéro bonus le plus sorti",
        # EN
        "which star is drawn the most",
        "complementary number most frequent",
        # ES
        "cual es la estrella más frecuente",
        # PT
        "qual estrela sai mais",
        # DE
        "welcher stern wird am häufigsten gezogen",
        # NL
        "welke ster komt het meest voor",
    ])
    def test_star_synonyms_detected(self, msg):
        assert _is_star_query(msg.lower())

    @pytest.mark.parametrize("msg", [
        "quel numéro sort le plus",
        "master class de loto",
        "faster than light",
        "les numéros les plus fréquents",
    ])
    def test_false_positives_rejected(self, msg):
        assert not _is_star_query(msg.lower())


class TestDetectNumeroEmStarSynonyms:

    @pytest.mark.parametrize("msg,expected_num", [
        ("étoile 3", 3),
        ("star 5", 5),
        ("complémentaire 7", 7),
        ("bonus 2", 2),
        ("estrella 4", 4),
        ("estrela 8", 8),
        ("stern 1", 1),
        ("ster 10", 10),
    ])
    def test_synonym_returns_etoile(self, msg, expected_num):
        num, type_num = _detect_numero_em(msg)
        assert num == expected_num
        assert type_num == "etoile"


class TestDetectGrilleEmStarSynonyms:

    def test_bonus_two_stars(self):
        nums, stars = _detect_grille_em("5 12 23 34 45 bonus 3 7")
        assert nums == [5, 12, 23, 34, 45]
        assert stars == [3, 7]

    def test_complementaire_single_star(self):
        nums, stars = _detect_grille_em("5 12 23 34 45 complémentaire 4")
        assert nums == [5, 12, 23, 34, 45]
        assert stars == [4]


class TestRequeteComplexeEmStarSynonyms:

    @pytest.mark.parametrize("msg", [
        "quel est le numéro complémentaire le plus fréquent",
        "which complementary number is drawn the most",
        "cuál es la estrella más frecuente",
    ])
    def test_classement_etoile(self, msg):
        result = _detect_requete_complexe_em(msg)
        assert result is not None
        assert result["num_type"] == "etoile"
        assert result["tri"] == "frequence_desc"

    def test_categorie_chaud_etoile(self):
        result = _detect_requete_complexe_em("numéros complémentaires les plus chauds")
        assert result is not None
        assert result["num_type"] == "etoile"
        assert result["categorie"] == "chaud"

    def test_boule_unchanged(self):
        result = _detect_requete_complexe_em("les numéros les plus sortis")
        assert result is not None
        assert result["num_type"] == "boule"


class TestOOREmStarSynonyms:

    @pytest.mark.parametrize("msg,expected", [
        ("complémentaire 15", 15),
        ("star 20", 20),
        ("bonus 25", 25),
    ])
    def test_oor_etoile_synonym(self, msg, expected):
        num, ctx = _detect_out_of_range_em(msg)
        assert num == expected
        assert ctx == "etoile_high"
