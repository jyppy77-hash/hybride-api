"""
Circuit breaker pour les appels Gemini API.

Etats :
  CLOSED    → fonctionnement normal
  OPEN      → fallback immediat (apres 3 echecs consecutifs, pendant 60s)
  HALF_OPEN → 1 requete test autorisee, si OK → CLOSED, sinon → OPEN
"""

import time
import logging

import httpx

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Levee quand le circuit est ouvert — le caller doit faire fallback."""


class GeminiCircuitBreaker:

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 3, open_timeout: float = 60.0):
        self._state: str = self.CLOSED
        self._failure_count: int = 0
        self._failure_threshold = failure_threshold
        self._open_timeout = open_timeout
        self._opened_at: float = 0.0

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            if time.monotonic() - self._opened_at >= self._open_timeout:
                self._set_state(self.HALF_OPEN)
        return self._state

    def _set_state(self, new_state: str) -> None:
        if new_state != self._state:
            logger.warning(
                "[CIRCUIT BREAKER] %s -> %s (failures=%d)",
                self._state, new_state, self._failure_count,
            )
            self._state = new_state

    async def call(
        self, client: httpx.AsyncClient, *args, **kwargs
    ) -> httpx.Response:
        """Wrap client.post() avec logique circuit breaker."""
        current = self.state
        if current == self.OPEN:
            raise CircuitOpenError("Circuit ouvert — fallback immediat")

        try:
            response = await client.post(*args, **kwargs)
        except (httpx.TimeoutException, httpx.ConnectError, OSError):
            self._record_failure()
            raise

        if response.status_code >= 500 or response.status_code == 429:
            self._record_failure()
        else:
            self._record_success()

        return response

    def _record_success(self) -> None:
        if self._state == self.HALF_OPEN:
            self._set_state(self.CLOSED)
        self._failure_count = 0

    def _record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._set_state(self.OPEN)
            self._opened_at = time.monotonic()


# Instance partagee — un circuit pour toute l'API Gemini
gemini_breaker = GeminiCircuitBreaker()
