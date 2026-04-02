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
    ALLOWED_TABLES_LOTO, ALLOWED_TABLES_EM,
    _SQL_LIMIT_MESSAGES, _MAX_SQL_INPUT_LENGTH,
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
        assert _validate_sql("SELECT boule_1 FROM tirages", allowed_tables=ALLOWED_TABLES_LOTO) is True

    def test_valid_select_complex(self):
        assert _validate_sql("SELECT COUNT(*) as total FROM tirages WHERE boule_1 = 7", allowed_tables=ALLOWED_TABLES_LOTO) is True

    def test_rejects_empty(self):
        assert _validate_sql("", allowed_tables=ALLOWED_TABLES_LOTO) is False

    def test_rejects_none(self):
        assert _validate_sql(None, allowed_tables=ALLOWED_TABLES_LOTO) is False

    def test_rejects_too_long(self):
        assert _validate_sql("SELECT " + "x" * 1000, allowed_tables=ALLOWED_TABLES_LOTO) is False

    def test_rejects_non_select(self):
        assert _validate_sql("INSERT INTO tirages VALUES (1,2,3,4,5,1)", allowed_tables=ALLOWED_TABLES_LOTO) is False

    def test_rejects_semicolon(self):
        assert _validate_sql("SELECT 1; DROP TABLE tirages", allowed_tables=ALLOWED_TABLES_LOTO) is False

    def test_rejects_dash_comment(self):
        assert _validate_sql("SELECT 1 -- comment", allowed_tables=ALLOWED_TABLES_LOTO) is False

    def test_rejects_block_comment(self):
        assert _validate_sql("SELECT /* injection */ 1", allowed_tables=ALLOWED_TABLES_LOTO) is False

    @pytest.mark.parametrize("kw", _SQL_FORBIDDEN)
    def test_rejects_forbidden_keyword(self, kw):
        sql = f"SELECT * FROM tirages WHERE {kw} something"
        assert _validate_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO) is False

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
        assert _validate_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO) is True

    def test_rejects_bare_union(self):
        """Bare UNION (without ALL) is blocked as SQL injection vector."""
        sql = "SELECT boule_1 FROM tirages UNION SELECT password FROM users"
        assert _validate_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO) is False

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
        assert _validate_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO) is True

    # F05: subquery nesting defense-in-depth
    def test_allows_single_select(self):
        """Simple SELECT must pass."""
        assert _validate_sql("SELECT boule_1 FROM tirages LIMIT 10", allowed_tables=ALLOWED_TABLES_LOTO) is True

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
        assert _validate_sql(sql, allowed_tables=ALLOWED_TABLES_EM) is True

    def test_rejects_excessive_subqueries(self):
        """More than 10 SELECTs must be rejected (pathological nesting)."""
        parts = " UNION ALL ".join(f"SELECT boule_1 FROM t{i}" for i in range(12))
        sql = f"SELECT * FROM ({parts}) x LIMIT 10"
        assert _validate_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO) is False


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
        mock_db.get_connection_readonly = lambda: _async_conn(cursor)

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
        mock_db.get_connection_readonly = lambda: _async_conn(cursor)

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
        mock_db.get_connection_readonly = lambda: _async_conn(cursor)
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

        result = await _execute_safe_sql("SELECT num, freq FROM tirages", allowed_tables=ALLOWED_TABLES_LOTO)
        assert result == [{"num": 7, "freq": 120}]

    @pytest.mark.asyncio
    @patch("services.base_chat_sql.db_cloudsql")
    async def test_returns_none_on_error(self, mock_db):
        cursor = AsyncMock()
        mock_db.get_connection_readonly = lambda: _async_conn(cursor)
        cursor.execute = AsyncMock(side_effect=Exception("DB error"))

        assert await _execute_safe_sql("SELECT 1 FROM tirages", allowed_tables=ALLOWED_TABLES_LOTO) is None

    # F03: defense-in-depth — _execute_safe_sql rejects invalid SQL
    @pytest.mark.asyncio
    async def test_rejects_drop_table(self):
        """F03: _execute_safe_sql must reject DROP TABLE without hitting DB."""
        result = await _execute_safe_sql("DROP TABLE tirages", allowed_tables=ALLOWED_TABLES_LOTO)
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_insert(self):
        """F03: _execute_safe_sql must reject INSERT without hitting DB."""
        result = await _execute_safe_sql("INSERT INTO tirages VALUES (1,2,3,4,5,1)", allowed_tables=ALLOWED_TABLES_LOTO)
        assert result is None

    @pytest.mark.asyncio
    @patch("services.base_chat_sql.db_cloudsql")
    async def test_uses_readonly_pool(self, mock_db):
        """S04: _execute_safe_sql must use get_connection_readonly (not get_connection)."""
        cursor = AsyncMock()
        mock_db.get_connection_readonly = lambda: _async_conn(cursor)
        mock_db.get_connection = MagicMock(side_effect=AssertionError("Must not use main pool"))
        cursor.fetchall = AsyncMock(return_value=[{"n": 1}])

        result = await _execute_safe_sql("SELECT 1 FROM tirages", allowed_tables=ALLOWED_TABLES_LOTO)
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


# ═══════════════════════════════════════════════════════════════════════
# F01 V82 — Table whitelist (semantic SQL injection defense)
# ═══════════════════════════════════════════════════════════════════════

class TestTableWhitelist:

    def test_accepts_tirages_loto(self):
        assert _validate_sql("SELECT * FROM tirages WHERE boule_1 = 7", allowed_tables=ALLOWED_TABLES_LOTO) is True

    def test_accepts_tirages_em(self):
        assert _validate_sql(
            "SELECT * FROM tirages_euromillions WHERE boule_1 = 7",
            allowed_tables=ALLOWED_TABLES_EM,
        ) is True

    def test_rejects_unauthorized_table(self):
        assert _validate_sql(
            "SELECT * FROM admin_config", allowed_tables=ALLOWED_TABLES_LOTO
        ) is False

    def test_rejects_join_unauthorized(self):
        assert _validate_sql(
            "SELECT t.* FROM tirages t JOIN sponsors s ON t.id = s.id",
            allowed_tables=ALLOWED_TABLES_LOTO,
        ) is False

    def test_rejects_subquery_unauthorized(self):
        assert _validate_sql(
            "SELECT * FROM tirages WHERE boule_1 IN (SELECT id FROM chat_log)",
            allowed_tables=ALLOWED_TABLES_LOTO,
        ) is False

    def test_rejects_no_from(self):
        assert _validate_sql("SELECT 1+1", allowed_tables=ALLOWED_TABLES_LOTO) is False

    def test_accepts_union_all_same_table(self):
        sql = (
            "SELECT boule_1 as num FROM tirages "
            "UNION ALL SELECT boule_2 FROM tirages "
            "UNION ALL SELECT boule_3 FROM tirages"
        )
        assert _validate_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO) is True

    def test_rejects_union_all_mixed_tables(self):
        sql = (
            "SELECT boule_1 FROM tirages "
            "UNION ALL SELECT id FROM sponsors"
        )
        assert _validate_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO) is False

    def test_case_insensitive_table_match(self):
        assert _validate_sql(
            "SELECT * FROM TIRAGES WHERE boule_1 = 1",
            allowed_tables=ALLOWED_TABLES_LOTO,
        ) is True

    def test_validate_sql_requires_allowed_tables(self):
        """F03 V83: allowed_tables is required — omitting raises TypeError."""
        with pytest.raises(TypeError):
            _validate_sql("SELECT * FROM admin_config")

    def test_em_rejects_loto_table(self):
        assert _validate_sql(
            "SELECT * FROM tirages", allowed_tables=ALLOWED_TABLES_EM
        ) is False

    def test_loto_rejects_em_table(self):
        assert _validate_sql(
            "SELECT * FROM tirages_euromillions", allowed_tables=ALLOWED_TABLES_LOTO
        ) is False


# ═══════════════════════════════════════════════════════════════════════
# F03 V82 — Multi-statement newline guard
# ═══════════════════════════════════════════════════════════════════════

class TestMultiStatementNewline:

    def test_rejects_newline_multi_statement(self):
        sql = "SELECT * FROM tirages\nSELECT * FROM tirages"
        assert _validate_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO) is False

    def test_accepts_union_all_multiline(self):
        sql = (
            "SELECT boule_1 as num FROM tirages\n"
            "UNION ALL\n"
            "SELECT boule_2 FROM tirages"
        )
        assert _validate_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO) is True

    def test_accepts_single_line(self):
        assert _validate_sql("SELECT * FROM tirages LIMIT 10", allowed_tables=ALLOWED_TABLES_LOTO) is True

    def test_rejects_newline_different_tables(self):
        sql = "SELECT * FROM tirages\nDELETE FROM tirages"
        assert _validate_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO) is False

    def test_accepts_union_all_multiline_with_whitelist(self):
        sql = (
            "SELECT boule_1 as num FROM tirages\n"
            "UNION ALL\n"
            "SELECT boule_2 FROM tirages"
        )
        assert _validate_sql(sql, allowed_tables=ALLOWED_TABLES_LOTO) is True


# ═══════════════════════════════════════════════════════════════════════
# F05 V82 — Readonly pool fallback logs ERROR
# ═══════════════════════════════════════════════════════════════════════

class TestReadonlyPoolFallbackLogLevel:

    @pytest.mark.asyncio
    async def test_readonly_fallback_logs_error(self):
        """When DB_USER_READONLY is not set, init_pool_readonly logs at ERROR level."""
        import db_cloudsql
        with patch.object(db_cloudsql, "DB_USER_READONLY", ""), \
             patch.object(db_cloudsql, "DB_PASSWORD_READONLY", ""), \
             patch.object(db_cloudsql, "_pool_readonly", None), \
             patch.object(db_cloudsql.logger, "error") as mock_err:
            await db_cloudsql.init_pool_readonly()
            mock_err.assert_called_once()
            assert "SECURITY" in mock_err.call_args[0][0]


# ═══════════════════════════════════��═════════════════════════════��═════
# F01 V83 — SQL session limit applied with user message
# ═════════════���══════════════════════════════════════════════��══════════

class TestSqlSessionLimit:

    @pytest.mark.asyncio
    async def test_sql_limit_applied_returns_message(self):
        """F01: When 10 SQL results in history, next SQL query is blocked with i18n message."""
        from services.chat_pipeline_shared import run_text_to_sql

        # Build history with 10 [RÉSULTAT SQL] assistant messages
        history = []
        for i in range(10):
            msg = MagicMock()
            msg.role = "assistant"
            msg.content = f"[RÉSULTAT SQL]\nboule_1: {i}"
            history.append(msg)

        enrichment, sql_query, sql_status = await run_text_to_sql(
            message="combien de tirages",
            http_client=MagicMock(), gem_api_key="fake",
            history=history,
            generate_sql_fn=AsyncMock(), validate_sql_fn=MagicMock(),
            ensure_limit_fn=MagicMock(), execute_sql_fn=AsyncMock(),
            format_result_fn=MagicMock(), max_per_session=10,
            log_prefix="[TEST]", force_sql=True,
            has_data_signal_fn=lambda m: True,
            continuation_mode=False, enrichment_context=None,
            lang="fr",
        )
        assert enrichment == _SQL_LIMIT_MESSAGES["fr"]
        assert sql_status == "LIMIT"
        assert sql_query is None

    @pytest.mark.asyncio
    async def test_sql_limit_not_reached_allows_query(self):
        """F01: With < 10 SQL results, query proceeds normally."""
        from services.chat_pipeline_shared import run_text_to_sql

        # Build history with 5 [RÉSULTAT SQL] assistant messages
        history = []
        for i in range(5):
            msg = MagicMock()
            msg.role = "assistant"
            msg.content = f"[RÉSULTAT SQL]\nboule_1: {i}"
            history.append(msg)

        mock_gen = AsyncMock(return_value="NO_SQL")
        enrichment, sql_query, sql_status = await run_text_to_sql(
            message="bonjour",
            http_client=MagicMock(), gem_api_key="fake",
            history=history,
            generate_sql_fn=mock_gen, validate_sql_fn=MagicMock(),
            ensure_limit_fn=MagicMock(), execute_sql_fn=AsyncMock(),
            format_result_fn=MagicMock(), max_per_session=10,
            log_prefix="[TEST]", force_sql=True,
            has_data_signal_fn=lambda m: True,
            continuation_mode=False, enrichment_context=None,
            lang="fr",
        )
        # generate_sql_fn was called — query was not blocked
        mock_gen.assert_called_once()
        assert sql_status == "NO_SQL"

    @pytest.mark.asyncio
    async def test_sql_limit_message_lang_en(self):
        """F01: English message when lang='en'."""
        from services.chat_pipeline_shared import run_text_to_sql

        history = []
        for i in range(10):
            msg = MagicMock()
            msg.role = "assistant"
            msg.content = f"[RÉSULTAT SQL]\ndata: {i}"
            history.append(msg)

        enrichment, _, status = await run_text_to_sql(
            message="how many draws",
            http_client=MagicMock(), gem_api_key="fake",
            history=history,
            generate_sql_fn=AsyncMock(), validate_sql_fn=MagicMock(),
            ensure_limit_fn=MagicMock(), execute_sql_fn=AsyncMock(),
            format_result_fn=MagicMock(), max_per_session=10,
            log_prefix="[TEST]", force_sql=True,
            has_data_signal_fn=lambda m: True,
            continuation_mode=False, enrichment_context=None,
            lang="en",
        )
        assert enrichment == _SQL_LIMIT_MESSAGES["en"]
        assert status == "LIMIT"


# ════════════��═════════════════���═════════════════════════════��══════════
# F03 V83 — allowed_tables required (keyword-only)
# ══════════════════════════════════════���═══════════════════════════════���

class TestAllowedTablesRequired:

    def test_validate_sql_requires_allowed_tables(self):
        """F03: Calling _validate_sql without allowed_tables raises TypeError."""
        with pytest.raises(TypeError):
            _validate_sql("SELECT * FROM tirages")

    @pytest.mark.asyncio
    async def test_execute_safe_sql_requires_allowed_tables(self):
        """F03: Calling _execute_safe_sql without allowed_tables raises TypeError."""
        with pytest.raises(TypeError):
            await _execute_safe_sql("SELECT * FROM tirages")


# ══════════════════��══════���═════════════════════════════════════════════
# F09 V83 — SQL input truncated at 500 chars
# ═════════════════════════��═════════════════════════════���═══════════════

class TestSqlInputTruncation:

    @pytest.mark.asyncio
    async def test_sql_input_truncated_at_500_chars(self):
        """F09: Message longer than 500 chars is truncated before Gemini SQL call."""
        from services.chat_pipeline_shared import run_text_to_sql

        long_message = "a" * 800
        captured_input = []

        async def fake_generate(msg, *args, **kwargs):
            captured_input.append(msg)
            return "NO_SQL"

        await run_text_to_sql(
            message=long_message,
            http_client=MagicMock(), gem_api_key="fake",
            history=[],
            generate_sql_fn=fake_generate, validate_sql_fn=MagicMock(),
            ensure_limit_fn=MagicMock(), execute_sql_fn=AsyncMock(),
            format_result_fn=MagicMock(), max_per_session=10,
            log_prefix="[TEST]", force_sql=True,
            has_data_signal_fn=lambda m: True,
            continuation_mode=False, enrichment_context=None,
        )
        assert len(captured_input) == 1
        assert len(captured_input[0]) == 500
