"""
Chat Logger — async INSERT into chat_log for Chatbot Monitor (V44).

Fire-and-forget pattern identical to track_gemini_call() in gcp_monitoring.py.
"""

import asyncio
import logging

import db_cloudsql

logger = logging.getLogger(__name__)

_INSERT_SQL = (
    "INSERT INTO chat_log "
    "(module, lang, question, response_preview, phase_detected, "
    "sql_generated, sql_status, duration_ms, ip_hash, session_hash, "
    "grid_count, has_exclusions, is_error, error_detail, "
    "gemini_tokens_in, gemini_tokens_out) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)


async def _do_insert(
    module: str, lang: str, question: str, response_preview: str,
    phase_detected: str, sql_generated: str | None, sql_status: str,
    duration_ms: int, ip_hash: str, session_hash: str,
    grid_count: int, has_exclusions: bool, is_error: bool,
    error_detail: str | None,
    gemini_tokens_in: int, gemini_tokens_out: int,
) -> None:
    """Fire-and-forget DB insert. Errors are logged, never raised."""
    try:
        await db_cloudsql.async_query(
            _INSERT_SQL,
            (
                module, lang, question, (response_preview or "")[:500],
                phase_detected, sql_generated, sql_status,
                duration_ms, ip_hash, session_hash,
                grid_count, int(has_exclusions), int(is_error),
                (error_detail or "")[:255] if error_detail else None,
                gemini_tokens_in, gemini_tokens_out,
            ),
        )
    except Exception as e:
        logger.warning("[CHAT_LOG] INSERT failed: %s", e)


def log_chat_exchange(
    module: str,
    lang: str,
    question: str,
    response_preview: str = "",
    phase_detected: str = "unknown",
    sql_generated: str | None = None,
    sql_status: str = "N/A",
    duration_ms: int = 0,
    ip_hash: str = "",
    session_hash: str = "",
    grid_count: int = 0,
    has_exclusions: bool = False,
    is_error: bool = False,
    error_detail: str | None = None,
    gemini_tokens_in: int = 0,
    gemini_tokens_out: int = 0,
) -> None:
    """Non-blocking INSERT into chat_log. Fire-and-forget via asyncio.create_task."""
    try:
        asyncio.create_task(
            _do_insert(
                module, lang, question, response_preview,
                phase_detected, sql_generated, sql_status,
                duration_ms, ip_hash, session_hash,
                grid_count, has_exclusions, is_error, error_detail,
                gemini_tokens_in, gemini_tokens_out,
            )
        )
    except RuntimeError:
        # No running event loop (shutdown) — skip silently
        logger.debug("[CHAT_LOG] No event loop, skipping log")
