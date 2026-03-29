"""
Tests for chat_pipeline_shared.py — V71 R3a backward-compat + shared helpers.
"""

import json
from types import SimpleNamespace

from services.chat_pipeline_shared import (
    sse_event, log_from_meta, build_gemini_contents, parse_pitch_json,
)


# ═══════════════════════════════════════════════════════
# Backward-compat: imports still work from original modules
# ═══════════════════════════════════════════════════════

class TestBackwardCompatImports:
    """Verify that the public API surface of both pipelines is unchanged."""

    def test_loto_pipeline_exports(self):
        """All public functions still importable from services.chat_pipeline."""
        from services.chat_pipeline import (
            handle_chat, handle_chat_stream, handle_pitch,
            _prepare_chat_context, _sse_event, _log_from_meta, _get_draw_count,
        )
        assert callable(handle_chat)
        assert callable(handle_chat_stream)
        assert callable(handle_pitch)
        assert callable(_prepare_chat_context)
        assert callable(_sse_event)
        assert callable(_log_from_meta)
        assert callable(_get_draw_count)

    def test_em_pipeline_exports(self):
        """All public functions still importable from services.chat_pipeline_em."""
        from services.chat_pipeline_em import (
            handle_chat_em, handle_chat_stream_em, handle_pitch_em,
            _prepare_chat_context_em, _sse_event_em, _log_from_meta_em,
        )
        assert callable(handle_chat_em)
        assert callable(handle_chat_stream_em)
        assert callable(handle_pitch_em)
        assert callable(_prepare_chat_context_em)
        assert callable(_sse_event_em)
        assert callable(_log_from_meta_em)

    def test_shared_module_exists(self):
        """chat_pipeline_shared module is importable."""
        import services.chat_pipeline_shared as shared
        assert hasattr(shared, 'sse_event')
        assert hasattr(shared, 'log_from_meta')
        assert hasattr(shared, 'build_gemini_contents')
        assert hasattr(shared, 'run_text_to_sql')
        assert hasattr(shared, 'call_gemini_and_respond')
        assert hasattr(shared, 'stream_and_respond')
        assert hasattr(shared, 'handle_pitch_common')
        assert hasattr(shared, 'parse_pitch_json')


# ═══════════════════════════════════════════════════════
# Shared helper unit tests
# ═══════════════════════════════════════════════════════

class TestSseEvent:
    def test_format(self):
        event = sse_event({"chunk": "hello"})
        assert event.startswith("data: ")
        assert event.endswith("\n\n")
        assert json.loads(event[6:].strip())["chunk"] == "hello"

    def test_loto_sse_delegates(self):
        """Loto _sse_event delegates to shared sse_event."""
        from services.chat_pipeline import _sse_event
        event = _sse_event({"test": True})
        assert '"test": true' in event

    def test_em_sse_delegates(self):
        """EM _sse_event_em delegates to shared sse_event."""
        from services.chat_pipeline_em import _sse_event_em
        event = _sse_event_em({"test": True})
        assert '"test": true' in event


class TestBuildGeminiContents:
    def test_empty_history(self):
        contents, history = build_gemini_contents([], "hello", lambda x: False)
        assert contents == []
        assert history == []

    def test_strips_insult_exchanges(self):
        """Insult user messages and their assistant responses are stripped."""
        msgs = [
            SimpleNamespace(role="user", content="t'es nul"),
            SimpleNamespace(role="assistant", content="calm down"),
            SimpleNamespace(role="user", content="quel numéro"),
        ]
        contents, _ = build_gemini_contents(msgs, "le 7", lambda x: "nul" in x)
        assert len(contents) == 1
        assert contents[0]["parts"][0]["text"] == "quel numéro"

    def test_dedup_last_message(self):
        """If last history message == current message, it's trimmed."""
        msgs = [SimpleNamespace(role="user", content="hello")]
        contents, history = build_gemini_contents(msgs, "hello", lambda x: False)
        assert len(history) == 0


class TestParsePitchJson:
    def test_valid_json(self):
        pitchs, err = parse_pitch_json('{"pitchs": ["Super !"]}')
        assert err is None
        assert pitchs == ["Super !"]

    def test_backtick_cleaning(self):
        pitchs, err = parse_pitch_json('```json\n{"pitchs": ["OK"]}\n```')
        assert err is None
        assert pitchs == ["OK"]

    def test_invalid_json(self):
        pitchs, err = parse_pitch_json("not json at all")
        assert pitchs is None
        assert err["status_code"] == 502
