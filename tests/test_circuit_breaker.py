"""
Tests unitaires pour services/circuit_breaker.py
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import httpx

from services.circuit_breaker import GeminiCircuitBreaker, CircuitOpenError


def _make_response(status_code=200):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    return resp


@pytest.fixture
def breaker():
    return GeminiCircuitBreaker(failure_threshold=3, open_timeout=0.1)


@pytest.mark.asyncio
async def test_closed_on_success(breaker):
    """Appel reussi → circuit reste ferme."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _make_response(200)

    resp = await breaker.call(client, "https://example.com")
    assert resp.status_code == 200
    assert breaker.state == GeminiCircuitBreaker.CLOSED


@pytest.mark.asyncio
async def test_opens_after_threshold(breaker):
    """3 echecs consecutifs (500) → circuit ouvert."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _make_response(500)

    for _ in range(3):
        await breaker.call(client, "https://example.com")

    assert breaker.state == GeminiCircuitBreaker.OPEN


@pytest.mark.asyncio
async def test_open_raises_circuit_open_error(breaker):
    """Circuit ouvert → CircuitOpenError sans appel reseau."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _make_response(500)

    for _ in range(3):
        await breaker.call(client, "https://example.com")

    with pytest.raises(CircuitOpenError):
        await breaker.call(client, "https://example.com")

    # Le 4eme appel ne doit PAS avoir touche le client
    assert client.post.call_count == 3


@pytest.mark.asyncio
async def test_half_open_after_timeout(breaker):
    """Apres open_timeout → passe en half_open."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _make_response(500)

    for _ in range(3):
        await breaker.call(client, "https://example.com")

    assert breaker.state == GeminiCircuitBreaker.OPEN

    # Attendre le timeout (0.1s)
    time.sleep(0.15)

    assert breaker.state == GeminiCircuitBreaker.HALF_OPEN


@pytest.mark.asyncio
async def test_half_open_success_closes(breaker):
    """Requete test reussie en half_open → ferme le circuit."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _make_response(500)

    for _ in range(3):
        await breaker.call(client, "https://example.com")

    time.sleep(0.15)
    assert breaker.state == GeminiCircuitBreaker.HALF_OPEN

    # Requete test reussie
    client.post.return_value = _make_response(200)
    await breaker.call(client, "https://example.com")

    assert breaker.state == GeminiCircuitBreaker.CLOSED


@pytest.mark.asyncio
async def test_half_open_failure_reopens(breaker):
    """Echec en half_open → re-ouvre le circuit."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _make_response(500)

    for _ in range(3):
        await breaker.call(client, "https://example.com")

    time.sleep(0.15)
    assert breaker.state == GeminiCircuitBreaker.HALF_OPEN

    # Requete test echouee
    await breaker.call(client, "https://example.com")

    assert breaker.state == GeminiCircuitBreaker.OPEN


@pytest.mark.asyncio
async def test_timeout_exception_counts_as_failure(breaker):
    """httpx.TimeoutException compte comme echec."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = httpx.TimeoutException("timeout")

    for _ in range(3):
        with pytest.raises(httpx.TimeoutException):
            await breaker.call(client, "https://example.com")

    assert breaker.state == GeminiCircuitBreaker.OPEN


@pytest.mark.asyncio
async def test_success_resets_failure_count(breaker):
    """2 echecs puis 1 succes remet le compteur a 0."""
    client = AsyncMock(spec=httpx.AsyncClient)

    client.post.return_value = _make_response(500)
    await breaker.call(client, "https://example.com")
    await breaker.call(client, "https://example.com")

    client.post.return_value = _make_response(200)
    await breaker.call(client, "https://example.com")

    assert breaker.state == GeminiCircuitBreaker.CLOSED

    # 2 echecs de plus ne suffisent pas (compteur remis a 0)
    client.post.return_value = _make_response(500)
    await breaker.call(client, "https://example.com")
    await breaker.call(client, "https://example.com")

    assert breaker.state == GeminiCircuitBreaker.CLOSED


@pytest.mark.asyncio
async def test_429_counts_as_failure(breaker):
    """HTTP 429 compte comme echec (rate limited par Gemini)."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _make_response(429)

    for _ in range(3):
        await breaker.call(client, "https://example.com")

    assert breaker.state == GeminiCircuitBreaker.OPEN
