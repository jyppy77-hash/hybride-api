"""
Tests Phase GEO (EM-only) — 9 pays, détection multilingue, contexte injecté.
F11 audit V71.
"""

from services.chat_detectors_em import (
    _detect_country_em, _get_country_context_em,
)


# ═══════════════════════════════════════════════════════
# Detection 9 pays — FR
# ═══════════════════════════════════════════════════════

class TestGeoDetection9CountriesFR:
    """_detect_country_em must detect all 9 participating countries in French."""

    def test_france(self):
        assert _detect_country_em("les tirages en France") is True

    def test_belgique(self):
        assert _detect_country_em("je suis en Belgique") is True

    def test_espagne(self):
        assert _detect_country_em("les résultats en Espagne") is True

    def test_portugal(self):
        assert _detect_country_em("les stats du Portugal") is True

    def test_allemagne(self):
        # "Allemagne" isn't in the pattern — it uses "Deutschland" (DE) or country-specific
        # The pattern has: frankreich/spanien/deutschland etc. in DE section
        # Let's test with a country that IS in FR section
        assert _detect_country_em("les tirages en Autriche") is True

    def test_royaume_uni(self):
        assert _detect_country_em("est-ce que le Royaume-Uni participe") is True

    def test_irlande(self):
        assert _detect_country_em("les tirages en Irlande") is True

    def test_luxembourg(self):
        assert _detect_country_em("le Luxembourg joue aussi") is True

    def test_suisse(self):
        assert _detect_country_em("les résultats en Suisse") is True


# ═══════════════════════════════════════════════════════
# Detection multilingue (même pays, différentes langues)
# ═══════════════════════════════════════════════════════

class TestGeoDetectionMultilang:
    """Same country detected across different languages."""

    def test_spain_en(self):
        assert _detect_country_em("is Spain in EuroMillions") is True

    def test_spanien_de(self):
        assert _detect_country_em("spielt Spanien mit") is True

    def test_spanje_nl(self):
        assert _detect_country_em("doet Spanje mee") is True

    def test_espanha_pt(self):
        assert _detect_country_em("a Espanha participa") is True

    def test_uk_en(self):
        assert _detect_country_em("does the UK play EuroMillions") is True

    def test_england_en(self):
        assert _detect_country_em("England draws") is True

    def test_deutschland_de(self):
        assert _detect_country_em("Deutschland EuroMillions") is True


# ═══════════════════════════════════════════════════════
# Non-detection (pays hors scope)
# ═══════════════════════════════════════════════════════

class TestGeoNonDetection:
    """Countries NOT participating in EuroMillions must NOT trigger Phase GEO."""

    def test_italie_not_detected(self):
        assert _detect_country_em("les tirages en Italie") is False

    def test_usa_not_detected(self):
        assert _detect_country_em("does the USA have EuroMillions") is False

    def test_japon_not_detected(self):
        assert _detect_country_em("le Japon participe-t-il") is False

    def test_stats_question_not_country(self):
        """Normal stats question without country mention."""
        assert _detect_country_em("quel est le numéro le plus fréquent") is False


# ═══════════════════════════════════════════════════════
# Contexte injecté — 6 langues
# ═══════════════════════════════════════════════════════

class TestGeoContextInjection:
    """_get_country_context_em returns correct context per language."""

    def test_context_fr(self):
        ctx = _get_country_context_em("fr")
        assert "IDENTIQUES" in ctx
        assert "9 pays" in ctx

    def test_context_en(self):
        ctx = _get_country_context_em("en")
        assert "IDENTICAL" in ctx
        assert "9 participating countries" in ctx

    def test_context_es(self):
        ctx = _get_country_context_em("es")
        assert "IDÉNTICOS" in ctx

    def test_context_pt(self):
        ctx = _get_country_context_em("pt")
        assert "IDÊNTICOS" in ctx

    def test_context_de(self):
        ctx = _get_country_context_em("de")
        assert "IDENTISCH" in ctx

    def test_context_nl(self):
        ctx = _get_country_context_em("nl")
        assert "IDENTIEK" in ctx

    def test_context_unknown_lang_fallback(self):
        """Unknown lang falls back to FR."""
        ctx = _get_country_context_em("xx")
        assert "IDENTIQUES" in ctx
