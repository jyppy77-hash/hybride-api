"""
Tests for services/chat_logger.py — Chat Monitor V44.
"""

import os
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
})


class TestChatLoggerInsert:
    """Test log_chat_exchange INSERT behavior."""

    def test_insert_basic(self):
        """Basic call creates an asyncio task."""
        with _db_env:
            import importlib
            import services.chat_logger as mod
            importlib.reload(mod)
            with patch.object(mod, "db_cloudsql") as mock_db:
                mock_db.async_query = AsyncMock(return_value=None)
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(self._call_and_wait(mod))
                    assert mock_db.async_query.called
                    args = mock_db.async_query.call_args
                    assert "INSERT INTO chat_log" in args[0][0]
                    params = args[0][1]
                    assert params[0] == "loto"  # module
                    assert params[1] == "fr"    # lang
                    assert params[2] == "test question"  # question
                finally:
                    loop.close()

    def test_insert_with_sql(self):
        """SQL fields are passed correctly."""
        with _db_env:
            import importlib
            import services.chat_logger as mod
            importlib.reload(mod)
            with patch.object(mod, "db_cloudsql") as mock_db:
                mock_db.async_query = AsyncMock(return_value=None)
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(self._call_sql_and_wait(mod))
                    params = mock_db.async_query.call_args[0][1]
                    assert params[4] == "SQL"           # phase_detected
                    assert params[5] == "SELECT 1"      # sql_generated
                    assert params[6] == "OK"            # sql_status
                finally:
                    loop.close()

    def test_insert_error_fields(self):
        """Error fields are passed correctly."""
        with _db_env:
            import importlib
            import services.chat_logger as mod
            importlib.reload(mod)
            with patch.object(mod, "db_cloudsql") as mock_db:
                mock_db.async_query = AsyncMock(return_value=None)
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(self._call_error_and_wait(mod))
                    params = mock_db.async_query.call_args[0][1]
                    assert params[12] == 1  # is_error (int)
                    assert params[13] == "Timeout"  # error_detail
                finally:
                    loop.close()

    def test_insert_truncates_response(self):
        """Response preview is truncated to 500 chars."""
        with _db_env:
            import importlib
            import services.chat_logger as mod
            importlib.reload(mod)
            with patch.object(mod, "db_cloudsql") as mock_db:
                mock_db.async_query = AsyncMock(return_value=None)
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(self._call_long_response_and_wait(mod))
                    params = mock_db.async_query.call_args[0][1]
                    assert len(params[3]) <= 500  # response_preview
                finally:
                    loop.close()

    def test_insert_failure_doesnt_crash(self):
        """DB failure is caught and logged, never raised."""
        with _db_env:
            import importlib
            import services.chat_logger as mod
            importlib.reload(mod)
            with patch.object(mod, "db_cloudsql") as mock_db:
                mock_db.async_query = AsyncMock(side_effect=Exception("DB down"))
                loop = asyncio.new_event_loop()
                try:
                    # Should NOT raise
                    loop.run_until_complete(self._call_and_wait(mod))
                finally:
                    loop.close()

    def test_no_event_loop_doesnt_crash(self):
        """When no event loop is running, log_chat_exchange skips silently."""
        with _db_env:
            import importlib
            import services.chat_logger as mod
            importlib.reload(mod)
            with patch.object(mod, "asyncio") as mock_asyncio:
                mock_asyncio.create_task = MagicMock(side_effect=RuntimeError("no loop"))
                # Should NOT raise
                mod.log_chat_exchange(
                    module="loto", lang="fr", question="test",
                )

    # ── async helpers ──

    async def _call_and_wait(self, mod):
        mod.log_chat_exchange(
            module="loto", lang="fr", question="test question",
            response_preview="test response", phase_detected="Gemini",
            duration_ms=150,
        )
        await asyncio.sleep(0.05)

    async def _call_sql_and_wait(self, mod):
        mod.log_chat_exchange(
            module="em", lang="en", question="show stats",
            phase_detected="SQL", sql_generated="SELECT 1", sql_status="OK",
            duration_ms=200,
        )
        await asyncio.sleep(0.05)

    async def _call_error_and_wait(self, mod):
        mod.log_chat_exchange(
            module="loto", lang="fr", question="error test",
            phase_detected="Gemini", is_error=True, error_detail="Timeout",
            duration_ms=15000,
        )
        await asyncio.sleep(0.05)

    async def _call_long_response_and_wait(self, mod):
        mod.log_chat_exchange(
            module="loto", lang="fr", question="long response",
            response_preview="x" * 1000,
            phase_detected="Gemini", duration_ms=100,
        )
        await asyncio.sleep(0.05)


class TestChatLoggerPhaseDetection:
    """Test that phase strings are valid."""

    def test_valid_phase_names(self):
        """All expected phase names are strings."""
        valid = {"I", "C", "R", "G", "A", "GEO", "0", "0-bis", "T",
                 "2", "3", "3-bis", "P+", "P", "OOR", "1", "SQL", "Gemini", "unknown"}
        for p in valid:
            assert isinstance(p, str)
            assert len(p) <= 30

    def test_default_phase_is_gemini(self):
        """Default phase_detected parameter is 'unknown'."""
        with _db_env:
            import importlib
            import services.chat_logger as mod
            importlib.reload(mod)
            with patch.object(mod, "db_cloudsql") as mock_db:
                mock_db.async_query = AsyncMock(return_value=None)
                loop = asyncio.new_event_loop()
                try:
                    async def _run():
                        mod.log_chat_exchange(module="loto", lang="fr", question="hi")
                        await asyncio.sleep(0.05)
                    loop.run_until_complete(_run())
                    params = mock_db.async_query.call_args[0][1]
                    assert params[4] == "unknown"  # default phase
                finally:
                    loop.close()

    def test_grid_count_and_exclusions(self):
        """grid_count and has_exclusions are passed correctly."""
        with _db_env:
            import importlib
            import services.chat_logger as mod
            importlib.reload(mod)
            with patch.object(mod, "db_cloudsql") as mock_db:
                mock_db.async_query = AsyncMock(return_value=None)
                loop = asyncio.new_event_loop()
                try:
                    async def _run():
                        mod.log_chat_exchange(
                            module="loto", lang="fr", question="genere 3 grilles",
                            phase_detected="G", grid_count=3, has_exclusions=True,
                            duration_ms=500,
                        )
                        await asyncio.sleep(0.05)
                    loop.run_until_complete(_run())
                    params = mock_db.async_query.call_args[0][1]
                    assert params[10] == 3   # grid_count
                    assert params[11] == 1   # has_exclusions (int)
                finally:
                    loop.close()
