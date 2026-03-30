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

    # F05: subquery nesting defense-in-depth
    def test_allows_single_select(self):
        """Simple SELECT must pass."""
        assert _validate_sql("SELECT boule_1 FROM tirages LIMIT 10") is True

    def test_allows_union_all_8_selects(self):
        """UNION ALL with 8 SELECTs (EM unpivot) must pass."""
        sql = (
            "SELECT num, COUNT(*) FROM ("
            "SELECT boule_1 as num FROM tirages_euromillions "
            "UNION ALL SELECT boule_2 FROM tirages_euromillions "
            "UNION ALL SELECT boule_3 FROM tirages_euromillions "
            "UNION ALL SELECT boule_4 FROM tirages_euromillions "
            "UNION ALL SELECT boule_5 FROM tirages_euromillions "
            "UNION ALL SELECT etoile_1 FROM tirages_euromillions "
            "UNION ALL SELECT etoile_2 FROM tirages_euromillions"
            ") t GROUP BY num ORDER BY COUNT(*) DESC LIMIT 10"
        )
        assert _validate_sql(sql) is True

    def test_rejects_excessive_subqueries(self):
        """More than 10 SELECTs must be rejected (pathological nesting)."""
        parts = " UNION ALL ".join(f"SELECT boule_1 FROM t{i}" for i in range(12))
        sql = f"SELECT * FROM ({parts}) x LIMIT 10"
        assert _validate_sql(sql) is False


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
    @patch("services.base_chat_sql.db_cloudsql")
    async def test_returns_rows(self, mock_db):
        cursor = AsyncMock()
        mock_db.get_connection_readonly = lambda: _async_conn(cursor)
        cursor.fetchall = AsyncMock(return_value=[{"num": 7, "freq": 120}])

        result = await _execute_safe_sql("SELECT num, freq FROM tirages")
        assert result == [{"num": 7, "freq": 120}]

    @pytest.mark.asyncio
    @patch("services.base_chat_sql.db_cloudsql")
    async def test_returns_none_on_error(self, mock_db):
        cursor = AsyncMock()
        mock_db.get_connection_readonly = lambda: _async_conn(cursor)
        cursor.execute = AsyncMock(side_effect=Exception("DB error"))

        assert await _execute_safe_sql("SELECT 1") is None

    # F03: defense-in-depth — _execute_safe_sql rejects invalid SQL
    @pytest.mark.asyncio
    async def test_rejects_drop_table(self):
        """F03: _execute_safe_sql must reject DROP TABLE without hitting DB."""
        result = await _execute_safe_sql("DROP TABLE tirages")
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_insert(self):
        """F03: _execute_safe_sql must reject INSERT without hitting DB."""
        result = await _execute_safe_sql("INSERT INTO tirages VALUES (1,2,3,4,5,1)")
        assert result is None

    @pytest.mark.asyncio
    @patch("services.base_chat_sql.db_cloudsql")
    async def test_uses_readonly_pool(self, mock_db):
        """S04: _execute_safe_sql must use get_connection_readonly (not get_connection)."""
        cursor = AsyncMock()
        mock_db.get_connection_readonly = lambda: _async_conn(cursor)
        mock_db.get_connection = MagicMock(side_effect=AssertionError("Must not use main pool"))
        cursor.fetchall = AsyncMock(return_value=[{"n": 1}])

        result = await _execute_safe_sql("SELECT 1 FROM tirages")
        assert result == [{"n": 1}]


# ═══════════════════════════════════════════════════════════════════════
# S04: get_connection_readonly fallback when no env var
# ═══════════════════════════════════════════════════════════════════════

class TestReadonlyPoolFallback:
    """S04 — get_connection_readonly falls back to main pool when DB_USER_READONLY not set."""

    @pytest.mark.asyncio
    async def test_readonly_fallback_uses_main_pool(self):
        """Without DB_USER_READONLY, get_connection_readonly() uses main pool."""
        import db_cloudsql
        # Save original state
        orig_pool = db_cloudsql._pool
        orig_pool_ro = db_cloudsql._pool_readonly

        try:
            # Simulate: main pool exists, readonly pool not initialized (no env var)
            mock_conn = AsyncMock()
            mock_pool = MagicMock()
            mock_pool.acquire = MagicMock(return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=False),
            ))
            db_cloudsql._pool = mock_pool
            db_cloudsql._pool_readonly = None  # Not initialized (no env var)

            async with db_cloudsql.get_connection_readonly() as conn:
                assert conn is mock_conn  # Falls back to main pool
        finally:
            db_cloudsql._pool = orig_pool
            db_cloudsql._pool_readonly = orig_pool_ro


# ═══════════════════════════════════════════════════════════════════════
# F04: _generate_sql guard — non-SQL output rejected (Loto)
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateSqlNonSqlGuard:
    """F04: _generate_sql must return NO_SQL when Gemini returns natural language."""

    @pytest.mark.asyncio
    @patch("services.chat_sql.gemini_breaker")
    async def test_rejects_natural_language(self, mock_breaker):
        """Gemini returning natural language gets rejected to NO_SQL."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Je ne peux pas générer de SQL pour cette question."}]}}]
        }
        mock_breaker.call = AsyncMock(return_value=mock_response)

        from services.chat_sql import _generate_sql
        result = await _generate_sql("test question", MagicMock(), "fake-key")
        assert result == "NO_SQL"

    @pytest.mark.asyncio
    @patch("services.chat_sql.gemini_breaker")
    async def test_allows_valid_select(self, mock_breaker):
        """Gemini returning valid SELECT passes through."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "SELECT COUNT(*) FROM tirages"}]}}]
        }
        mock_breaker.call = AsyncMock(return_value=mock_response)

        from services.chat_sql import _generate_sql
        result = await _generate_sql("combien de tirages", MagicMock(), "fake-key")
        assert result == "SELECT COUNT(*) FROM tirages"

    @pytest.mark.asyncio
    @patch("services.chat_sql.gemini_breaker")
    async def test_allows_no_sql(self, mock_breaker):
        """Gemini returning NO_SQL passes through."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "NO_SQL"}]}}]
        }
        mock_breaker.call = AsyncMock(return_value=mock_response)

        from services.chat_sql import _generate_sql
        result = await _generate_sql("bonjour", MagicMock(), "fake-key")
        assert result == "NO_SQL"


# ═══════════════════════════════════════════════════════════════════════
# F02: {DRAW_COUNT} placeholder present in chatbot prompts
# ═══════════════════════════════════════════════════════════════════════

class TestDrawCountPlaceholder:
    """F02: Chatbot prompts must use {DRAW_COUNT} placeholder (not hardcoded)."""

    def test_loto_prompt_has_placeholder(self):
        prompt = load_prompt("CHATBOT")
        assert "{DRAW_COUNT}" in prompt
        # Ensure old hardcoded values are gone
        assert "981+" not in prompt.replace("{DRAW_COUNT}+", "")

    def test_em_fr_prompt_has_placeholder(self):
        prompt = load_prompt_em("prompt_hybride_em", lang="fr")
        assert "{DRAW_COUNT}" in prompt
        assert "733" not in prompt

    def test_em_en_prompt_has_placeholder(self):
        prompt = load_prompt_em("prompt_hybride_em", lang="en")
        assert "{DRAW_COUNT}" in prompt
        assert "733" not in prompt

    def test_em_es_prompt_has_placeholder(self):
        prompt = load_prompt_em("prompt_hybride_em", lang="es")
        assert "{DRAW_COUNT}" in prompt
        assert "733" not in prompt


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


# ═══════════════════════════════════════════════════════════════════════
# V46 — SQL prompt hardening present in all 6 languages
# ═══════════════════════════════════════════════════════════════════════

class TestSqlPromptHardeningAllLangs:
    """V46: Every SQL generator prompt must contain the 'ABSOLUTE RULE'
    block that enforces SELECT-or-NO_SQL output format."""

    def test_fr_has_regle_absolue(self):
        prompt = load_prompt_em("prompt_sql_generator_em", lang="fr")
        assert "RÈGLE ABSOLUE" in prompt
        assert "NO_SQL" in prompt

    def test_en_has_absolute_rule(self):
        prompt = load_prompt_em("prompt_sql_generator_em", lang="en")
        assert "ABSOLUTE RULE" in prompt
        assert "NO_SQL" in prompt

    def test_es_has_regla_absoluta(self):
        prompt = load_prompt_em("prompt_sql_generator_em", lang="es")
        assert "REGLA ABSOLUTA" in prompt
        assert "NO_SQL" in prompt

    def test_pt_has_regra_absoluta(self):
        prompt = load_prompt_em("prompt_sql_generator_em", lang="pt")
        assert "REGRA ABSOLUTA" in prompt
        assert "NO_SQL" in prompt

    def test_de_has_absolute_regel(self):
        prompt = load_prompt_em("prompt_sql_generator_em", lang="de")
        assert "ABSOLUTE REGEL" in prompt
        assert "NO_SQL" in prompt

    def test_nl_has_absolute_regel(self):
        prompt = load_prompt_em("prompt_sql_generator_em", lang="nl")
        assert "ABSOLUTE REGEL" in prompt
        assert "NO_SQL" in prompt
