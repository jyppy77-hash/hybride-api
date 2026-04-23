"""
Tests for stream_gemini_chat retry on timeout (F06 audit V71 / V131.B google-genai SDK).

V131.B — mocks migrés de httpx.AsyncClient.stream vers
client.aio.models.generate_content_stream via fixture mock_vertex_client.
Retry pattern préservé : 2 attempts max + backoff 2s sur asyncio.TimeoutError.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.gemini import stream_gemini_chat


async def _collect(gen):
    """Collect all chunks from async generator."""
    chunks = []
    async for c in gen:
        chunks.append(c)
    return chunks


async def _gen_hello():
    """Async generator yieldant un chunk 'hello' + usage_metadata."""
    chunk = MagicMock()
    chunk.text = "hello"
    chunk.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=5)
    yield chunk


@pytest.mark.asyncio
async def test_retry_success_after_timeout(mock_vertex_client):
    """First attempt raises asyncio.TimeoutError, second succeeds → chunks returned."""
    with mock_vertex_client() as vc, \
         patch("services.gemini.gemini_breaker") as mock_breaker, \
         patch("services.gemini.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # V131.B pattern validé empiriquement : side_effect=[exc, async_gen_instance]
        # 1er await → TimeoutError, 2ème await → async_generator itérable
        vc.client.aio.models.generate_content_stream = AsyncMock(
            side_effect=[asyncio.TimeoutError(), _gen_hello()]
        )
        mock_breaker.state = "closed"
        mock_breaker.OPEN = "open"
        mock_breaker._record_success = MagicMock()
        mock_breaker._record_failure = MagicMock()

        chunks = await _collect(stream_gemini_chat(
            MagicMock(), "fake-key", "system",
            [{"role": "user", "parts": [{"text": "hi"}]}],
            timeout=5.0,
        ))

    assert chunks == ["hello"]
    assert vc.client.aio.models.generate_content_stream.await_count == 2
    mock_sleep.assert_awaited_once_with(2)
    mock_breaker._record_success.assert_called_once()


@pytest.mark.asyncio
async def test_retry_both_timeout_raises(mock_vertex_client):
    """Both attempts raise asyncio.TimeoutError → raises, failure recorded."""
    with mock_vertex_client() as vc, \
         patch("services.gemini.gemini_breaker") as mock_breaker, \
         patch("services.gemini.asyncio.sleep", new_callable=AsyncMock):
        vc.client.aio.models.generate_content_stream = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        mock_breaker.state = "closed"
        mock_breaker.OPEN = "open"
        mock_breaker._record_failure = MagicMock()

        with pytest.raises(asyncio.TimeoutError):
            await _collect(stream_gemini_chat(
                MagicMock(), "fake-key", "system",
                [{"role": "user", "parts": [{"text": "hi"}]}],
                timeout=5.0,
            ))

    mock_breaker._record_failure.assert_called_once()
