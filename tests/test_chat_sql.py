"""
Tests unitaires pour services/chat_sql.py.
Priorite P0 : validation securite SQL (injection defense).
"""

import re
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from services.chat_sql import (
    _validate_sql, _ensure_limit, _format_sql_result,
    _get_tirage_data, _execute_safe_sql, _SQL_FORBIDDEN,
)
from services.prompt_loader import load_prompt, load_prompt_em


@asynccontextmanager
async def _async_conn(cursor):
    conn = AsyncMock()
    conn.cursor = AsyncMock(return_value=cursor)
    yield conn


# ═══════════════════════════════════════════════════════════════════════
# _validate_sql — P0 securite
# ═══════════════════════════════════════════════════════════════════════

class TestValidateSql:

    def test_valid_select(self):
        assert _validate_sql("SELECT boule_1 FROM tirages") is True

    def test_valid_select_complex(self):
        assert _validate_sql("SELECT COUNT(*) as total FROM tirages WHERE boule_1 = 7") is True

    def test_rejects_empty(self):
        assert _validate_sql("") is False

    def test_rejects_none(self):
        assert _validate_sql(None) is False

    def test_rejects_too_long(self):
        assert _validate_sql("SELECT " + "x" * 1000) is False

    def test_rejects_non_select(self):
        assert _validate_sql("INSERT INTO tirages VALUES (1,2,3,4,5,1)") is False

    def test_rejects_semicolon(self):
        assert _validate_sql("SELECT 1; DROP TABLE tirages") is False

    def test_rejects_dash_comment(self):
        assert _validate_sql("SELECT 1 -- comment") is False

    def test_rejects_block_comment(self):
        assert _validate_sql("SELECT /* injection */ 1") is False

    @pytest.mark.parametrize("kw", _SQL_FORBIDDEN)
    def test_rejects_forbidden_keyword(self, kw):
        sql = f"SELECT * FROM tirages WHERE {kw} something"
        assert _validate_sql(sql) is False

    def test_allows_union_all(self):
        """UNION ALL is legitimate for frequency counting (unpivot pattern)."""
        sql = (
            "SELECT num, COUNT(*) as freq FROM ("
            "SELECT boule_1 as num FROM tirages WHERE date_de_tirage >= '2026-01-01' "
            "UNION ALL SELECT boule_2 FROM tirages WHERE date_de_tirage >= '2026-01-01' "
            "UNION ALL SELECT boule_3 FROM tirages WHERE date_de_tirage >= '2026-01-01' "
            "UNION ALL SELECT boule_4 FROM tirages WHERE date_de_tirage >= '2026-01-01' "
            "UNION ALL SELECT boule_5 FROM tirages WHERE date_de_tirage >= '2026-01-01'"
            ") t GROUP BY num ORDER BY freq DESC LIMIT 5"
        )
        assert _validate_sql(sql) is True

    def test_rejects_bare_union(self):
        """Bare UNION (without ALL) is blocked as SQL injection vector."""
        sql = "SELECT boule_1 FROM tirages UNION SELECT password FROM users"
        assert _validate_sql(sql) is False

    def test_allows_union_all_no_where(self):
        """UNION ALL for all-time frequency query."""
        sql = (
            "SELECT num, COUNT(*) as freq FROM ("
            "SELECT boule_1 as num FROM tirages "
            "UNION ALL SELECT boule_2 FROM tirages "
            "UNION ALL SELECT boule_3 FROM tirages "
            "UNION ALL SELECT boule_4 FROM tirages "
            "UNION ALL SELECT boule_5 FROM tirages"
            ") t GROUP BY num ORDER BY freq DESC LIMIT 1"
        )
        assert _validate_sql(sql) is True


# ═══════════════════════════════════════════════════════════════════════
# _ensure_limit
# ═══════════════════════════════════════════════════════════════════════

class TestEnsureLimit:

    def test_adds_limit_when_absent(self):
        result = _ensure_limit("SELECT * FROM tirages")
        assert result.endswith("LIMIT 50")

    def test_preserves_existing_limit(self):
        sql = "SELECT * FROM tirages LIMIT 10"
        assert _ensure_limit(sql) == sql

    def test_custom_max_limit(self):
        result = _ensure_limit("SELECT * FROM tirages", max_limit=20)
        assert result.endswith("LIMIT 20")


# ═══════════════════════════════════════════════════════════════════════
# _format_sql_result
# ═══════════════════════════════════════════════════════════════════════

class TestFormatSqlResult:

    def test_empty_rows(self):
        result = _format_sql_result([])
        assert "Aucun" in result
        assert "RÉSULTAT SQL" in result

    def test_dict_rows_formatted(self):
        rows = [{"boule_1": 7, "boule_2": 14}]
        result = _format_sql_result(rows)
        assert "boule_1: 7" in result
        assert " | " in result

    def test_date_string_formatted_fr(self):
        rows = [{"date_de_tirage": "2024-01-15"}]
        result = _format_sql_result(rows)
        assert "janvier" in result

    def test_truncates_at_20(self):
        rows = [{"num": i} for i in range(25)]
        result = _format_sql_result(rows)
        assert "25 résultats au total" in result
        lines = [l for l in result.split("\n") if l.startswith("num:")]
        assert len(lines) == 20


# ═══════════════════════════════════════════════════════════════════════
# _get_tirage_data — mock DB
# ═══════════════════════════════════════════════════════════════════════

class TestGetTirageData:

    @pytest.mark.asyncio
    @patch("services.chat_sql.db_cloudsql")
    async def test_latest(self, mock_db):
        cursor = AsyncMock()
        mock_db.get_connection = lambda: _async_conn(cursor)

        cursor.fetchone = AsyncMock(return_value={
            "date_de_tirage": date(2026, 2, 3),
            "boule_1": 5, "boule_2": 12, "boule_3": 23,
            "boule_4": 34, "boule_5": 45, "numero_chance": 7,
        })

        result = await _get_tirage_data("latest")
        assert result is not None
        assert result["boules"] == [5, 12, 23, 34, 45]
        assert result["chance"] == 7

    @pytest.mark.asyncio
    @patch("services.chat_sql.db_cloudsql")
    async def test_by_date(self, mock_db):
        cursor = AsyncMock()
        mock_db.get_connection = lambda: _async_conn(cursor)

        cursor.fetchone = AsyncMock(return_value={
            "date_de_tirage": date(2024, 6, 1),
            "boule_1": 1, "boule_2": 2, "boule_3": 3,
            "boule_4": 4, "boule_5": 5, "numero_chance": 1,
        })

        result = await _get_tirage_data(date(2024, 6, 1))
        assert result is not None
        assert result["date"] == date(2024, 6, 1)

    @pytest.mark.asyncio
    @patch("services.chat_sql.db_cloudsql")
    async def test_returns_none_when_no_row(self, mock_db):
        cursor = AsyncMock()
        mock_db.get_connection = lambda: _async_conn(cursor)
        cursor.fetchone = AsyncMock(return_value=None)

        assert await _get_tirage_data(date(1999, 1, 1)) is None


# ═══════════════════════════════════════════════════════════════════════
# _execute_safe_sql — mock DB
# ═══════════════════════════════════════════════════════════════════════

class TestExecuteSafeSql:

    @pytest.mark.asyncio
    @patch("services.chat_sql.db_cloudsql")
    async def test_returns_rows(self, mock_db):
        cursor = AsyncMock()
        mock_db.get_connection = lambda: _async_conn(cursor)
        cursor.fetchall = AsyncMock(return_value=[{"num": 7, "freq": 120}])

        result = await _execute_safe_sql("SELECT num, freq FROM tirages")
        assert result == [{"num": 7, "freq": 120}]

    @pytest.mark.asyncio
    @patch("services.chat_sql.db_cloudsql")
    async def test_returns_none_on_error(self, mock_db):
        cursor = AsyncMock()
        mock_db.get_connection = lambda: _async_conn(cursor)
        cursor.execute = AsyncMock(side_effect=Exception("DB error"))

        assert await _execute_safe_sql("SELECT 1") is None


# ═══════════════════════════════════════════════════════════════════════
# Prompt temporal few-shot examples — regression tests
# ═══════════════════════════════════════════════════════════════════════

class TestPromptTemporalExamples:
    """Verify SQL prompts contain 'depuis/since' temporal few-shot examples."""

    def test_loto_prompt_has_depuis_janvier(self):
        prompt = load_prompt("SQL_GENERATOR")
        assert "depuis le 1er janvier 2026" in prompt
        assert "date_de_tirage >= '2026-01-01'" in prompt

    def test_loto_prompt_has_depuis_mars(self):
        prompt = load_prompt("SQL_GENERATOR")
        assert "depuis mars 2025" in prompt
        assert "date_de_tirage >= '2025-03-01'" in prompt

    def test_loto_prompt_has_a_partir_de(self):
        prompt = load_prompt("SQL_GENERATOR")
        assert "à partir de" in prompt
        assert "date_de_tirage >= '2026-02-01'" in prompt

    def test_em_fr_prompt_has_depuis_examples(self):
        prompt = load_prompt_em("prompt_sql_generator_em", lang="fr")
        assert "depuis le 1er janvier 2026" in prompt
        assert "date_de_tirage >= '2026-01-01'" in prompt

    def test_em_en_prompt_has_since_examples(self):
        prompt = load_prompt_em("prompt_sql_generator_em", lang="en")
        assert "since January 1st 2026" in prompt
        assert "date_de_tirage >= '2026-01-01'" in prompt

    def test_em_es_prompt_has_desde_examples(self):
        prompt = load_prompt_em("prompt_sql_generator_em", lang="es")
        assert "desde el 1 de enero de 2026" in prompt
        assert "date_de_tirage >= '2026-01-01'" in prompt

    def test_em_pt_prompt_has_desde_examples(self):
        prompt = load_prompt_em("prompt_sql_generator_em", lang="pt")
        assert "desde 1 de janeiro de 2026" in prompt
        assert "date_de_tirage >= '2026-01-01'" in prompt

    def test_em_de_prompt_has_seit_examples(self):
        prompt = load_prompt_em("prompt_sql_generator_em", lang="de")
        assert "seit dem 1. Januar 2026" in prompt
        assert "date_de_tirage >= '2026-01-01'" in prompt

    def test_em_nl_prompt_has_sinds_examples(self):
        prompt = load_prompt_em("prompt_sql_generator_em", lang="nl")
        assert "sinds 1 januari 2026" in prompt
        assert "date_de_tirage >= '2026-01-01'" in prompt
