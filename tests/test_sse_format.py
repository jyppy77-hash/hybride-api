"""
Tests SSE format validation — data: prefix, JSON parsable, is_done termination.
F14 audit V71.
"""

import json
import asyncio

from services.chat_pipeline import _sse_event, handle_chat_stream
from services.chat_pipeline_em import handle_chat_stream_em


# ═══════════════════════════════════════════════════════
# _sse_event format
# ═══════════════════════════════════════════════════════

class TestSseEventFormat:
    """Each SSE event must be properly formatted."""

    def test_data_prefix(self):
        """SSE event must start with 'data: '."""
        event = _sse_event({"chunk": "hello", "is_done": False})
        assert event.startswith("data: ")

    def test_double_newline(self):
        """SSE event must end with double newline."""
        event = _sse_event({"chunk": "hello", "is_done": False})
        assert event.endswith("\n\n")

    def test_json_parsable(self):
        """Content after 'data: ' must be valid JSON."""
        event = _sse_event({"chunk": "hello", "source": "gemini", "is_done": False})
        json_str = event[len("data: "):].strip()
        parsed = json.loads(json_str)
        assert parsed["chunk"] == "hello"
        assert parsed["source"] == "gemini"
        assert parsed["is_done"] is False

    def test_is_done_true(self):
        """Termination event has is_done=True."""
        event = _sse_event({"chunk": "", "source": "gemini", "mode": "balanced", "is_done": True})
        parsed = json.loads(event[len("data: "):].strip())
        assert parsed["is_done"] is True

    def test_unicode_safe(self):
        """Unicode characters must be preserved (ensure_ascii=False)."""
        event = _sse_event({"chunk": "numéro étoile ★"})
        assert "numéro" in event
        assert "étoile" in event
        assert "★" in event


# ═══════════════════════════════════════════════════════
# Early return SSE (Phase I insulte — no Gemini needed)
# ═══════════════════════════════════════════════════════

def _collect_sse(async_gen):
    """Collect all SSE events from an async generator."""
    events = []
    loop = asyncio.new_event_loop()
    try:
        async def _run():
            async for event in async_gen:
                events.append(event)
        loop.run_until_complete(_run())
    finally:
        loop.close()
    return events


class TestSseEarlyReturn:
    """Phase I (insulte) must produce valid SSE even without Gemini call."""

    def test_insult_sse_format_loto(self):
        """Insult message → SSE with data: prefix, valid JSON, is_done=True."""
        import os
        os.environ.setdefault("DB_USER", "test")
        os.environ.setdefault("DB_PASS", "test")
        os.environ.setdefault("DB_NAME", "test")
        os.environ.setdefault("DB_HOST", "127.0.0.1")

        events = _collect_sse(handle_chat_stream(
            "tu es nul espèce d'idiot",
            [],
            "index",
            None,
            lang="fr",
        ))
        assert len(events) >= 1
        for event in events:
            assert event.startswith("data: "), f"Missing data: prefix: {event[:50]}"
            assert event.endswith("\n\n"), f"Missing double newline: {event[-10:]}"
            json_str = event[len("data: "):].strip()
            parsed = json.loads(json_str)
            assert "chunk" in parsed

        # Last event must be done
        last = json.loads(events[-1][len("data: "):].strip())
        assert last["is_done"] is True

    def test_insult_sse_format_em(self):
        """Insult message EM → SSE with data: prefix, valid JSON, is_done=True."""
        import os
        os.environ.setdefault("DB_USER", "test")
        os.environ.setdefault("DB_PASS", "test")
        os.environ.setdefault("DB_NAME", "test")
        os.environ.setdefault("DB_HOST", "127.0.0.1")

        events = _collect_sse(handle_chat_stream_em(
            "you are stupid idiot",
            [],
            "em_index",
            None,
            lang="en",
        ))
        assert len(events) >= 1
        for event in events:
            assert event.startswith("data: ")
            json_str = event[len("data: "):].strip()
            parsed = json.loads(json_str)
            assert "chunk" in parsed

        last = json.loads(events[-1][len("data: "):].strip())
        assert last["is_done"] is True
