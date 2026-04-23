"""
Tests F12 — _PENDING_TASKS tracking + await_pending_tasks.

V131.B — Classe TestGeminiCallWithFallback SUPPRIMÉE (fonction
_gemini_call_with_fallback supprimée en V131.A, migration google-genai SDK).
Seule la classe TestPendingTasks subsiste — elle teste des symbols
(_PENDING_TASKS, _track_task, await_pending_tasks) toujours exportés par
services.gemini_shared.
"""

import asyncio
import pytest

from services.gemini_shared import (
    _PENDING_TASKS, _track_task, await_pending_tasks,
)


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
