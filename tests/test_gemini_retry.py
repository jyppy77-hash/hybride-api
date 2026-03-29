"""
Tests for stream_gemini_chat retry on timeout (F06 audit V71).
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from services.gemini import stream_gemini_chat
from services.circuit_breaker import CircuitOpenError


async def _collect(gen):
    """Collect all chunks from async generator."""
    chunks = []
    async for c in gen:
        chunks.append(c)
    return chunks


def _make_mock_response(status_code=200, lines=None):
    """Build a mock streaming response."""
    if lines is None:
        lines = [
            'data: {"candidates":[{"content":{"parts":[{"text":"hello"}]}}]}',
            'data: {"usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":5}}',
        ]
    resp = MagicMock()
    resp.status_code = status_code
    resp.aiter_lines = lambda: AsyncIterator(lines)
    return resp


class AsyncIterator:
    """Helper to make a list behave as an async iterator."""
    def __init__(self, items):
        self._items = iter(items)
    def __aiter__(self):
        return self
    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


@pytest.mark.asyncio
async def test_retry_success_after_timeout():
    """First attempt times out, second succeeds → chunks returned."""
    call_count = 0

    class FakeClient:
        def stream(self, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("timeout")
            return _AsyncCM(_make_mock_response())

    with patch("services.gemini.gemini_breaker") as mock_breaker, \
         patch("services.gemini.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_breaker.state = "closed"
        mock_breaker.OPEN = "open"
        mock_breaker._record_success = MagicMock()
        mock_breaker._record_failure = MagicMock()

        chunks = await _collect(stream_gemini_chat(
            FakeClient(), "fake-key", "system", [{"role": "user", "parts": [{"text": "hi"}]}],
            timeout=5.0,
        ))

    assert call_count == 2
    assert chunks == ["hello"]
    mock_sleep.assert_awaited_once_with(2)
    mock_breaker._record_success.assert_called_once()


@pytest.mark.asyncio
async def test_retry_both_timeout_raises():
    """Both attempts time out → TimeoutException raised, failure recorded."""
    class FakeClient:
        def stream(self, *args, **kwargs):
            raise httpx.TimeoutException("timeout")

    with patch("services.gemini.gemini_breaker") as mock_breaker, \
         patch("services.gemini.asyncio.sleep", new_callable=AsyncMock):
        mock_breaker.state = "closed"
        mock_breaker.OPEN = "open"
        mock_breaker._record_failure = MagicMock()

        with pytest.raises(httpx.TimeoutException):
            await _collect(stream_gemini_chat(
                FakeClient(), "fake-key", "system", [{"role": "user", "parts": [{"text": "hi"}]}],
                timeout=5.0,
            ))

    mock_breaker._record_failure.assert_called_once()


class _AsyncCM:
    """Async context manager wrapper for mock responses."""
    def __init__(self, resp):
        self._resp = resp
    async def __aenter__(self):
        return self._resp
    async def __aexit__(self, *args):
        pass
