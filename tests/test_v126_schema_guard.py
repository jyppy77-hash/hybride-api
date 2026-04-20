"""
V126 Sous-phase 4/5 — DB schema whitelist + hallucinated identifier guard
(option 4-Y : DESCRIBE boot + fallback statique).

Ajustements A1 + A2 :
- A1 : regex resserrée `[a-z]{3,}_\\d+` + liste noire explicite
  `_KNOWN_HALLUCINATED_IDENTIFIERS`
- A2 : liste fallback statique exhaustive + test CI de drift
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.chat_pipeline_gemini import (
    _SCHEMA_WHITELIST_FALLBACK,
    _KNOWN_HALLUCINATED_IDENTIFIERS,
    _check_sql_schema_hallucination,
    _build_schema_whitelist,
)
import services.chat_pipeline_gemini as _gemini_mod


# ─────────────────────────────────────────────────────────────────────
# _build_schema_whitelist — boot DESCRIBE + fallback
# ─────────────────────────────────────────────────────────────────────


class TestSchemaWhitelistBuild:
    """V126 4/5 boot : DESCRIBE populate le cache, fallback si DB down."""

    @pytest.mark.asyncio
    async def test_schema_whitelist_built_from_describe(self):
        """Mock DESCRIBE → whitelist contient les colonnes attendues."""
        mock_rows_tirages = [
            {"Field": "id"}, {"Field": "date_de_tirage"},
            {"Field": "boule_1"}, {"Field": "boule_2"},
            {"Field": "boule_3"}, {"Field": "boule_4"},
            {"Field": "boule_5"}, {"Field": "numero_chance"},
        ]
        mock_rows_em = [
            {"Field": "id"}, {"Field": "date_de_tirage"},
            {"Field": "boule_1"}, {"Field": "boule_2"},
            {"Field": "boule_3"}, {"Field": "boule_4"},
            {"Field": "boule_5"}, {"Field": "etoile_1"},
            {"Field": "etoile_2"},
        ]
        cursor_mock = AsyncMock()
        cursor_mock.execute = AsyncMock()
        # Alternance : premier appel → tirages, second → euromillions
        cursor_mock.fetchall = AsyncMock(
            side_effect=[mock_rows_tirages, mock_rows_em],
        )
        conn_mock = AsyncMock()
        conn_mock.cursor = AsyncMock(return_value=cursor_mock)
        ctx_mock = MagicMock()
        ctx_mock.__aenter__ = AsyncMock(return_value=conn_mock)
        ctx_mock.__aexit__ = AsyncMock(return_value=None)
        db_mock = MagicMock()
        db_mock.get_connection_readonly = MagicMock(return_value=ctx_mock)
        with patch.dict("sys.modules", {"db_cloudsql": db_mock}):
            columns = await _build_schema_whitelist()
        assert "date_de_tirage" in columns
        assert "boule_1" in columns
        assert "numero_chance" in columns
        assert "etoile_1" in columns
        assert "etoile_2" in columns

    @pytest.mark.asyncio
    async def test_schema_fallback_on_db_down_boot(self, caplog):
        """DB down → fallback statique + logger.error."""
        caplog.set_level(logging.ERROR)
        db_mock = MagicMock()
        db_mock.get_connection_readonly = MagicMock(
            side_effect=Exception("DB down"),
        )
        with patch.dict("sys.modules", {"db_cloudsql": db_mock}):
            columns = await _build_schema_whitelist()
        # Fallback utilisé : colonnes connues présentes
        assert "date_de_tirage" in columns
        assert "boule_1" in columns
        assert "numero_chance" in columns
        assert "etoile_1" in columns
        # logger.error émis
        assert any("falling back" in r.message.lower() for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────
# _check_sql_schema_hallucination — détection identifiants hallucinés
# ─────────────────────────────────────────────────────────────────────


class TestCheckSchemaHallucination:
    """V126 4/5 : regex resserrée (A1) + liste noire (A1) combinées."""

    def setup_method(self):
        """Préparer le cache whitelist avec le fallback statique."""
        _gemini_mod._SCHEMA_WHITELIST = set(_SCHEMA_WHITELIST_FALLBACK)

    def test_detect_num_1_halluciné(self):
        """`num_1` halluciné (vrai: `boule_1`) → match regex."""
        result = _check_sql_schema_hallucination(
            "la colonne num_1 contient 17", "[TEST]", "fr",
        )
        assert result is not None
        assert "retourne" in result.lower() or "reformule" in result.lower() or "technique" in result.lower()

    def test_detect_ball_1_halluciné_EN(self):
        """`ball_1` halluciné (EN pseudo-schema) → match regex."""
        result = _check_sql_schema_hallucination(
            "the column ball_1 contains 17", "[TEST]", "en",
        )
        assert result is not None

    def test_detect_num_chance_halluciné_via_blacklist(self):
        """`num_chance` pas capté par regex (pas de chiffre suffixé) mais
        présent dans _KNOWN_HALLUCINATED_IDENTIFIERS."""
        result = _check_sql_schema_hallucination(
            "la colonne num_chance vaut 4", "[TEST]", "fr",
        )
        assert result is not None

    def test_detect_date_tirage_halluciné_via_blacklist(self):
        """`date_tirage` (pas `date_de_tirage`) → liste noire."""
        result = _check_sql_schema_hallucination(
            "date_tirage : 2026-03-28", "[TEST]", "fr",
        )
        assert result is not None

    def test_detect_draw_date_halluciné_via_blacklist(self):
        result = _check_sql_schema_hallucination(
            "draw_date field returns the value", "[TEST]", "en",
        )
        assert result is not None

    def test_valid_boule_1_not_flagged(self):
        """`boule_1` est DANS la whitelist → pas de warning."""
        result = _check_sql_schema_hallucination(
            "la boule_1 vaut 17 dans ce tirage", "[TEST]", "fr",
        )
        assert result is None

    def test_valid_numero_chance_not_flagged(self):
        """`numero_chance` est DANS la whitelist → pas de warning."""
        result = _check_sql_schema_hallucination(
            "numero_chance est le 6ème champ", "[TEST]", "fr",
        )
        assert result is None

    def test_valid_date_de_tirage_not_flagged(self):
        """`date_de_tirage` ne match pas la regex (pas de pattern `xxx_N`)
        et est dans la whitelist donc pas flagué par la liste noire."""
        result = _check_sql_schema_hallucination(
            "la date_de_tirage est 2026-03-28", "[TEST]", "fr",
        )
        assert result is None

    def test_valid_etoile_1_etoile_2_not_flagged(self):
        """EM : etoile_1 et etoile_2 dans whitelist."""
        result = _check_sql_schema_hallucination(
            "etoile_1 et etoile_2 sont les deux étoiles", "[TEST]", "fr",
        )
        assert result is None

    def test_no_false_positive_on_generic_number(self):
        """Texte naturel avec un nombre → pas de match regex `[a-z]{3,}_\\d+`."""
        result = _check_sql_schema_hallucination(
            "le 30 est sorti 115 fois depuis 2019", "[TEST]", "fr",
        )
        assert result is None

    def test_no_false_positive_on_french_underscore_phrases(self):
        """A1 — regex resserrée ne match PAS `foo_bar` (mots FR avec underscore)."""
        # Note: si Gemini utilisait `base_de_donnees` — regex V126 ne match pas
        result = _check_sql_schema_hallucination(
            "la base_de_donnees contient les tirages", "[TEST]", "fr",
        )
        assert result is None

    def test_empty_whitelist_graceful_returns_none(self):
        """Guard : whitelist vide (boot non exécuté) → None."""
        _gemini_mod._SCHEMA_WHITELIST = set()
        result = _check_sql_schema_hallucination(
            "num_1 vaut 17", "[TEST]", "fr",
        )
        assert result is None
        # Restore pour les autres tests
        _gemini_mod._SCHEMA_WHITELIST = set(_SCHEMA_WHITELIST_FALLBACK)

    def test_empty_response_returns_none(self):
        assert _check_sql_schema_hallucination("", "[TEST]", "fr") is None


# ─────────────────────────────────────────────────────────────────────
# A2 — Test de drift statique fallback (CI safety)
# ─────────────────────────────────────────────────────────────────────


class TestFallbackSchemaNonDrift:
    """A2 : assure que la liste statique inclut toutes les colonnes vues
    dans le code V124 (chat_sql.py, chat_sql_em.py, stats_service.py)."""

    def test_fallback_includes_all_loto_columns(self):
        """Colonnes citées dans `services/chat_sql.py` et stats_service.py."""
        expected = {
            "date_de_tirage", "boule_1", "boule_2", "boule_3", "boule_4",
            "boule_5", "numero_chance",
        }
        assert expected.issubset(_SCHEMA_WHITELIST_FALLBACK)

    def test_fallback_includes_all_em_columns(self):
        """Colonnes citées dans `services/chat_sql_em.py`."""
        expected = {
            "date_de_tirage", "boule_1", "boule_2", "boule_3", "boule_4",
            "boule_5", "etoile_1", "etoile_2",
        }
        assert expected.issubset(_SCHEMA_WHITELIST_FALLBACK)

    def test_fallback_includes_sql_generator_columns(self):
        """Colonnes supplémentaires déclarées dans prompt_sql_generator.txt
        (jour_de_tirage, nombre_de_gagnant_au_rang1, rapport_du_rang1)."""
        expected = {
            "jour_de_tirage",
            "nombre_de_gagnant_au_rang1",
            "rapport_du_rang1",
        }
        assert expected.issubset(_SCHEMA_WHITELIST_FALLBACK)

    def test_known_hallucinated_identifiers_not_in_whitelist(self):
        """Invariant de sécurité : les identifiants hallucinés connus NE
        doivent JAMAIS être dans la whitelist fallback (auto-FP)."""
        for halluc in _KNOWN_HALLUCINATED_IDENTIFIERS:
            assert halluc not in _SCHEMA_WHITELIST_FALLBACK, (
                f"Halluc identifier {halluc} leaked into whitelist fallback"
            )
