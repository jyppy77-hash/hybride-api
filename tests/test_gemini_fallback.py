"""
Tests F03 — _gemini_call_with_fallback: CircuitOpen/Timeout/Error → fallback.
Tests F12 — _PENDING_TASKS tracking + await_pending_tasks.
"""

import asyncio
import pytest
import httpx

from services.gemini_shared import (
    _gemini_call_with_fallback,
    _PENDING_TASKS, _track_task, await_pending_tasks,
)
from services.circuit_breaker import CircuitOpenError


# ═══════════════════════════════════════════════════════
# F03: _gemini_call_with_fallback
# ═══════════════════════════════════════════════════════

class TestGeminiCallWithFallback:

    @pytest.mark.asyncio
    async def test_success_returns_response(self):
        """On success, the coroutine result is returned (not fallback)."""
        async def _ok():
            return {"status": "ok"}

        result = await _gemini_call_with_fallback(
            _ok(),
            fallback_fn=lambda t: {"status": "fallback"},
            log_prefix="[TEST]",
        )
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_circuit_open_returns_fallback(self):
        """CircuitOpenError → fallback_fn('circuit_open')."""
        async def _raise():
            raise CircuitOpenError()

        result = await _gemini_call_with_fallback(
            _raise(),
            fallback_fn=lambda t: {"error": t},
            log_prefix="[TEST]",
        )
        assert result == {"error": "circuit_open"}

    @pytest.mark.asyncio
    async def test_timeout_returns_fallback(self):
        """httpx.TimeoutException → fallback_fn('timeout')."""
        async def _raise():
            raise httpx.TimeoutException("test")

        result = await _gemini_call_with_fallback(
            _raise(),
            fallback_fn=lambda t: {"error": t},
            log_prefix="[TEST]",
        )
        assert result == {"error": "timeout"}

    @pytest.mark.asyncio
    async def test_generic_error_returns_fallback(self):
        """Generic Exception → fallback_fn('error')."""
        async def _raise():
            raise RuntimeError("boom")

        result = await _gemini_call_with_fallback(
            _raise(),
            fallback_fn=lambda t: {"error": t},
            log_prefix="[TEST]",
        )
        assert result == {"error": "error"}


# ═══════════════════════════════════════════════════════
# F12: _PENDING_TASKS + _track_task + await_pending_tasks
# ═══════════════════════════════════════════════════════

class TestPendingTasks:

    def test_pending_tasks_is_set(self):
        """_PENDING_TASKS must be a set."""
        assert isinstance(_PENDING_TASKS, set)

    def test_await_pending_tasks_is_callable(self):
        """await_pending_tasks must be an async function."""
        assert asyncio.iscoroutinefunction(await_pending_tasks)

    @pytest.mark.asyncio
    async def test_track_task_adds_and_discards(self):
        """_track_task adds task to set; done callback discards it."""
        before = len(_PENDING_TASKS)

        async def _noop():
            return 1

        task = asyncio.ensure_future(_noop())
        _track_task(task)
        assert task in _PENDING_TASKS
        await task
        # Allow done callback to fire
        await asyncio.sleep(0)
        assert task not in _PENDING_TASKS
        assert len(_PENDING_TASKS) == before

    @pytest.mark.asyncio
    async def test_await_pending_drains(self):
        """await_pending_tasks waits for tracked tasks."""
        results = []

        async def _slow():
            await asyncio.sleep(0.05)
            results.append(1)

        task = asyncio.ensure_future(_slow())
        _track_task(task)
        await await_pending_tasks(timeout=2.0)
        assert results == [1]
