"""
V128 → V129.1 — Tests retry exponential backoff sur 429 Gemini.

V129.1 (21/04/2026): 3 tests timing supprimés (backoff passé de 200/400ms à
2/4/8s, cap 3s→14s). Les timings sont désormais testés dans
test_v129_1_calibration.py. Les contrats comportementaux (no-retry-default,
CB-open-abort, exhausted-1-failure, Retry-After override, 429 vs 500) restent
ici car indépendants du coef de backoff.

Mock asyncio.sleep to keep tests fast (<1s each).
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from services.circuit_breaker import GeminiCircuitBreaker, CircuitOpenError


def _mock_response(status_code: int, retry_after: str | None = None):
    """Build a minimal httpx-like response mock."""
    resp = MagicMock()
    resp.status_code = status_code
    headers = {}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    resp.headers = headers
    return resp


def _mock_client(responses):
    """Build an async client whose .post() returns responses sequentially."""
    client = MagicMock()
    client.post = AsyncMock(side_effect=responses)
    return client


# ═══════════════════════════════════════════════════════════════════════
# V128: retry exponential backoff
# ═══════════════════════════════════════════════════════════════════════

class TestV128RetryBackoff:

    @pytest.mark.asyncio
    async def test_no_retry_default_preserves_v127(self):
        """max_retries=0 (default) → single attempt, V127 behavior unchanged."""
        breaker = GeminiCircuitBreaker(failure_threshold=5)
        client = _mock_client([_mock_response(429)])
        with patch("services.circuit_breaker.asyncio.sleep", AsyncMock()) as sleep:
            resp = await breaker.call(client, "https://example.com")
            assert resp.status_code == 429
            assert client.post.call_count == 1
            sleep.assert_not_called()
        assert breaker._failure_count == 1  # 1 failure recorded

    @pytest.mark.asyncio
    async def test_success_first_attempt_no_retry(self):
        """max_retries=2 but 200 on 1st → no retry, no sleep."""
        breaker = GeminiCircuitBreaker(failure_threshold=5)
        client = _mock_client([_mock_response(200)])
        with patch("services.circuit_breaker.asyncio.sleep", AsyncMock()) as sleep:
            resp = await breaker.call(client, "https://example.com", max_retries=2)
            assert resp.status_code == 200
            assert client.post.call_count == 1
            sleep.assert_not_called()
        assert breaker._failure_count == 0

    # V129.1 — 2 tests timing supprimés (obsolètes) :
    #   test_retry_on_429_then_success (asserts 0.2s)
    #   test_retry_exponential_backoff_timing (asserts 0.2, 0.4)
    # Remplacés par test_backoff_exponential_large_2s_4s dans
    # test_v129_1_calibration.py.

    @pytest.mark.asyncio
    async def test_retry_honors_retry_after_header(self):
        """Retry-After: 1 → backoff=1.0s (overrides exponential default)."""
        breaker = GeminiCircuitBreaker(failure_threshold=5)
        client = _mock_client([
            _mock_response(429, retry_after="1"), _mock_response(200),
        ])
        with patch("services.circuit_breaker.asyncio.sleep", AsyncMock()) as sleep:
            await breaker.call(client, "https://example.com", max_retries=2)
            sleep.assert_called_once()
            assert sleep.call_args[0][0] == pytest.approx(1.0, abs=0.01)

    # V129.1 — test_retry_cap_total_time_3s supprimé (cap 3s → 14s obsolète).
    # Remplacé par test_cap_total_14s_not_3s dans test_v129_1_calibration.py.

    @pytest.mark.asyncio
    async def test_retry_cb_open_abort_immediately(self):
        """Breaker OPEN at iteration start → raise CircuitOpenError, no post call."""
        breaker = GeminiCircuitBreaker(failure_threshold=1)
        breaker._state = breaker.OPEN
        breaker._opened_at = float("inf")  # prevent transition to half_open
        client = _mock_client([_mock_response(200)])
        with patch("services.circuit_breaker.asyncio.sleep", AsyncMock()):
            with pytest.raises(CircuitOpenError):
                await breaker.call(client, "https://example.com", max_retries=2)
        client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_exhausted_records_one_failure(self):
        """3 attempts all 429 → exactly 1 _record_failure (not 3)."""
        breaker = GeminiCircuitBreaker(failure_threshold=10)
        client = _mock_client([
            _mock_response(429), _mock_response(429), _mock_response(429),
        ])
        with patch("services.circuit_breaker.asyncio.sleep", AsyncMock()):
            resp = await breaker.call(client, "https://example.com", max_retries=2)
            assert resp.status_code == 429
            assert client.post.call_count == 3
        assert breaker._failure_count == 1  # max 1/user request

    @pytest.mark.asyncio
    async def test_retry_only_on_429_not_500(self):
        """500 → no retry, immediate record_failure + return 500."""
        breaker = GeminiCircuitBreaker(failure_threshold=5)
        client = _mock_client([_mock_response(500)])
        with patch("services.circuit_breaker.asyncio.sleep", AsyncMock()) as sleep:
            resp = await breaker.call(client, "https://example.com", max_retries=2)
            assert resp.status_code == 500
            assert client.post.call_count == 1
            sleep.assert_not_called()
        assert breaker._failure_count == 1
