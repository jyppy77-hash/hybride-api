"""
Tests F02+F04 V98 — Portuguese (PT) detection patterns for complex queries.

Verifies that PT patterns are present and functional in both
EuroMillions (chat_detectors_em_intent.py) and Loto (chat_detectors.py) detectors.
"""

import pytest

from services.chat_detectors_em_intent import (
    _CAT_CHAUD_RE,
    _FREQ_DESC_RE,
    _ECART_DESC_RE,
    _ECART_ASC_RE,
    _EM_COMP_RE,
    _detect_requete_complexe_em,
)
from services.chat_detectors import (
    _LOTO_CAT_CHAUD_RE,
    _LOTO_FREQ_DESC_RE,
    _LOTO_ECART_DESC_RE,
    _LOTO_ECART_ASC_RE,
    _detect_requete_complexe,
)


def _any_match(patterns, text: str) -> bool:
    """Return True if any pattern in the list matches the text."""
    for pat in patterns:
        if pat.search(text):
            return True
    return False


# ═══════════════════════════════════════════════════════
# F02 — EuroMillions PT patterns
# ═══════════════════════════════════════════════════════

class TestEM_PT_CatChaud:
    def test_numeros_quentes(self):
        assert _any_match(_CAT_CHAUD_RE, "quais são os números quentes?")

    def test_numeros_do_momento(self):
        assert _any_match(_CAT_CHAUD_RE, "números do momento euromillions")

    def test_numeros_em_alta(self):
        assert _any_match(_CAT_CHAUD_RE, "números em alta agora")

    def test_numeros_em_tendencia(self):
        assert _any_match(_CAT_CHAUD_RE, "números em tendência")


class TestEM_PT_FreqDesc:
    def test_mais_sorteados(self):
        assert _any_match(_FREQ_DESC_RE, "números mais sorteados euromillions")

    def test_mais_frequentes(self):
        assert _any_match(_FREQ_DESC_RE, "números mais frequentes")

    def test_top_numeros(self):
        assert _any_match(_FREQ_DESC_RE, "top 5 números euromillions")


class TestEM_PT_EcartDesc:
    def test_maior_atraso(self):
        assert _any_match(_ECART_DESC_RE, "números com maior atraso")

    def test_maior_intervalo(self):
        assert _any_match(_ECART_DESC_RE, "maior intervalo entre sorteios")

    def test_mais_tempo_sem_sair(self):
        assert _any_match(_ECART_DESC_RE, "mais tempo sem sair")


class TestEM_PT_EcartAsc:
    def test_menor_atraso(self):
        assert _any_match(_ECART_ASC_RE, "números com menor atraso")

    def test_menor_pausa(self):
        assert _any_match(_ECART_ASC_RE, "menor pausa entre sorteios")

    def test_saiu_recentemente(self):
        assert _any_match(_ECART_ASC_RE, "saído mais recentemente")


class TestEM_PT_Comp:
    def test_comparar_dois(self):
        assert _any_match(_EM_COMP_RE, "comparar o 3 e o 7")

    def test_comparar_com(self):
        assert _any_match(_EM_COMP_RE, "comparar 12 com 25")


class TestEM_PT_Integration:
    """Integration: _detect_requete_complexe_em with PT messages."""

    def test_quentes_detected(self):
        result = _detect_requete_complexe_em("quais são os números quentes do euromillions?")
        assert result is not None
        assert result.get("type") == "categorie"

    def test_mais_sorteados_detected(self):
        result = _detect_requete_complexe_em("números mais sorteados no euromillions")
        assert result is not None
        assert result.get("type") == "classement"


# ═══════════════════════════════════════════════════════
# F04 — Loto PT + multilang patterns
# ═══════════════════════════════════════════════════════

class TestLoto_PT_CatChaud:
    def test_numeros_quentes(self):
        assert _any_match(_LOTO_CAT_CHAUD_RE, "números quentes do loto")

    def test_numeros_calientes(self):
        assert _any_match(_LOTO_CAT_CHAUD_RE, "números calientes")

    def test_hot_numbers(self):
        assert _any_match(_LOTO_CAT_CHAUD_RE, "hot numbers loto")

    def test_heisse_zahlen(self):
        assert _any_match(_LOTO_CAT_CHAUD_RE, "heiße zahlen")

    def test_hete_nummers(self):
        assert _any_match(_LOTO_CAT_CHAUD_RE, "hete nummers loto")


class TestLoto_PT_FreqDesc:
    def test_mais_sorteados(self):
        assert _any_match(_LOTO_FREQ_DESC_RE, "números mais sorteados")

    def test_most_drawn(self):
        assert _any_match(_LOTO_FREQ_DESC_RE, "most drawn numbers")

    def test_mas_frecuentes(self):
        assert _any_match(_LOTO_FREQ_DESC_RE, "números más frecuentes")

    def test_meistgezogen(self):
        assert _any_match(_LOTO_FREQ_DESC_RE, "meistgezogen zahlen")

    def test_meest_getrokken(self):
        assert _any_match(_LOTO_FREQ_DESC_RE, "meest getrokken nummers")


class TestLoto_PT_EcartDesc:
    def test_maior_atraso(self):
        assert _any_match(_LOTO_ECART_DESC_RE, "maior atraso")

    def test_largest_gap(self):
        assert _any_match(_LOTO_ECART_DESC_RE, "largest gap")

    def test_mayor_retraso(self):
        assert _any_match(_LOTO_ECART_DESC_RE, "mayor retraso")

    def test_groesste_abstand(self):
        assert _any_match(_LOTO_ECART_DESC_RE, "größte abstand")

    def test_grootste_achterstand(self):
        assert _any_match(_LOTO_ECART_DESC_RE, "grootste achterstand")


class TestLoto_PT_EcartAsc:
    def test_menor_atraso(self):
        assert _any_match(_LOTO_ECART_ASC_RE, "menor atraso")

    def test_smallest_gap(self):
        assert _any_match(_LOTO_ECART_ASC_RE, "smallest gap")

    def test_menor_retraso(self):
        assert _any_match(_LOTO_ECART_ASC_RE, "menor retraso")

    def test_kleinste_abstand(self):
        assert _any_match(_LOTO_ECART_ASC_RE, "kleinste abstand")

    def test_kleinste_achterstand(self):
        assert _any_match(_LOTO_ECART_ASC_RE, "kleinste achterstand")


class TestLoto_Multilang_Integration:
    """Integration: _detect_requete_complexe with multilang messages."""

    def test_pt_quentes_detected(self):
        result = _detect_requete_complexe("quais são os números quentes?")
        assert result is not None
        assert result.get("type") == "categorie"

    def test_en_hot_detected(self):
        result = _detect_requete_complexe("hot numbers loto")
        assert result is not None
        assert result.get("type") == "categorie"

    def test_pt_mais_sorteados_detected(self):
        result = _detect_requete_complexe("números mais sorteados no loto")
        assert result is not None
        assert result.get("type") == "classement"

    def test_en_most_drawn_detected(self):
        result = _detect_requete_complexe("most drawn numbers")
        assert result is not None
        assert result.get("type") == "classement"
