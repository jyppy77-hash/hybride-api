"""V127 — Tests Per-phase circuit breakers (chat / sql / pitch).

Audit V126.1 : un 429 sur SQL ne doit plus tuer chat ni pitch.
Threshold différencié : chat=5 (UX humain tolérant), sql=3, pitch=3 (strict).
"""

import httpx
import pytest

from services.circuit_breaker import (
    ALL_BREAKERS,
    CircuitOpenError,
    GeminiCircuitBreaker,
    gemini_breaker,
    gemini_breaker_chat,
    gemini_breaker_pitch,
    gemini_breaker_sql,
)


@pytest.fixture(autouse=True)
def _reset_breakers():
    """Reset les 3 breakers avant chaque test (état partagé module-level)."""
    for b in ALL_BREAKERS.values():
        b.force_close()
    yield
    for b in ALL_BREAKERS.values():
        b.force_close()


class _FakeClient:
    """httpx.AsyncClient mock — retourne un status_code fixe."""

    def __init__(self, status_code: int):
        self._status = status_code

    async def post(self, *args, **kwargs):
        return httpx.Response(self._status, request=httpx.Request("POST", "http://x"))


# ─────────────────────────────────────────────────────────────────────────────
# Configuration & alias
# ─────────────────────────────────────────────────────────────────────────────

def test_alias_gemini_breaker_is_chat():
    """Rétrocompat V127 : `gemini_breaker` == `gemini_breaker_chat`."""
    assert gemini_breaker is gemini_breaker_chat


def test_all_breakers_dict_keys():
    """3 instances exposées via ALL_BREAKERS."""
    assert set(ALL_BREAKERS.keys()) == {"chat", "sql", "pitch"}
    assert ALL_BREAKERS["chat"] is gemini_breaker_chat
    assert ALL_BREAKERS["sql"] is gemini_breaker_sql
    assert ALL_BREAKERS["pitch"] is gemini_breaker_pitch


def test_chat_threshold_is_5():
    assert gemini_breaker_chat._failure_threshold == 5


def test_sql_threshold_is_3():
    assert gemini_breaker_sql._failure_threshold == 3


def test_pitch_threshold_is_10_v129_1():
    # V129.1: pitch threshold raised 3 → 10 (calibration post-mortem logs prod).
    assert gemini_breaker_pitch._failure_threshold == 10


# ─────────────────────────────────────────────────────────────────────────────
# Isolation per-phase
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_three_breakers_independent():
    """5 failures sur SQL n'ouvre PAS chat ni pitch."""
    fake = _FakeClient(429)
    # Trigger SQL OPEN (3 failures)
    for _ in range(3):
        await gemini_breaker_sql.call(fake, "http://x")
    assert gemini_breaker_sql.state == GeminiCircuitBreaker.OPEN
    # Chat et pitch restent CLOSED
    assert gemini_breaker_chat.state == GeminiCircuitBreaker.CLOSED
    assert gemini_breaker_pitch.state == GeminiCircuitBreaker.CLOSED


@pytest.mark.asyncio
async def test_breaker_threshold_isolation_end_to_end():
    """Bonus end-to-end : simule 5 failures chat + 3 SQL → vérifie pitch CLOSED.

    C'est exactement le bug que V127 corrige (audit V126.1) : avant V127, 1 seul
    429 sur SQL ouvrait le breaker global pour tout le service.
    """
    fake = _FakeClient(429)
    # 5 failures chat → OPEN
    for _ in range(5):
        await gemini_breaker_chat.call(fake, "http://x")
    assert gemini_breaker_chat.state == GeminiCircuitBreaker.OPEN
    # 3 failures SQL → OPEN
    for _ in range(3):
        await gemini_breaker_sql.call(fake, "http://x")
    assert gemini_breaker_sql.state == GeminiCircuitBreaker.OPEN
    # Pitch JAMAIS appelé → reste CLOSED
    assert gemini_breaker_pitch.state == GeminiCircuitBreaker.CLOSED
    # Pitch peut toujours servir
    fake_ok = _FakeClient(200)
    resp = await gemini_breaker_pitch.call(fake_ok, "http://x")
    assert resp.status_code == 200
    assert gemini_breaker_pitch.state == GeminiCircuitBreaker.CLOSED


@pytest.mark.asyncio
async def test_chat_needs_5_failures_to_open():
    """Chat = threshold 5 (vs 3 par défaut). 4 failures → still CLOSED."""
    fake = _FakeClient(500)
    for _ in range(4):
        await gemini_breaker_chat.call(fake, "http://x")
    assert gemini_breaker_chat.state == GeminiCircuitBreaker.CLOSED
    await gemini_breaker_chat.call(fake, "http://x")
    assert gemini_breaker_chat.state == GeminiCircuitBreaker.OPEN


@pytest.mark.asyncio
async def test_sql_3_failures_then_open():
    fake = _FakeClient(500)
    for _ in range(3):
        await gemini_breaker_sql.call(fake, "http://x")
    assert gemini_breaker_sql.state == GeminiCircuitBreaker.OPEN
    with pytest.raises(CircuitOpenError):
        await gemini_breaker_sql.call(fake, "http://x")


@pytest.mark.asyncio
async def test_pitch_10_failures_then_open_v129_1():
    # V129.1: pitch threshold raised 3 → 10 (calibration post-mortem logs prod).
    fake = _FakeClient(429)
    for _ in range(10):
        await gemini_breaker_pitch.call(fake, "http://x")
    assert gemini_breaker_pitch.state == GeminiCircuitBreaker.OPEN
    with pytest.raises(CircuitOpenError):
        await gemini_breaker_pitch.call(fake, "http://x")


def test_force_close_resets_all_three():
    """V127 admin reset : force_close() sur les 3 breakers."""
    gemini_breaker_chat._failure_count = 5
    gemini_breaker_chat._set_state(GeminiCircuitBreaker.OPEN)
    gemini_breaker_sql._failure_count = 3
    gemini_breaker_sql._set_state(GeminiCircuitBreaker.OPEN)
    gemini_breaker_pitch._failure_count = 3
    gemini_breaker_pitch._set_state(GeminiCircuitBreaker.OPEN)
    for b in ALL_BREAKERS.values():
        b.force_close()
    assert gemini_breaker_chat.state == GeminiCircuitBreaker.CLOSED
    assert gemini_breaker_sql.state == GeminiCircuitBreaker.CLOSED
    assert gemini_breaker_pitch.state == GeminiCircuitBreaker.CLOSED
