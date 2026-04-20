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

    def force_close(self) -> None:
        """I16 V66: Force circuit to CLOSED state (admin reset)."""
        prev = self._state
        self._state = self.CLOSED
        self._failure_count = 0
        self._opened_at = 0.0
        logger.warning("[CIRCUIT] Force closed by admin (was %s, failures=%d)", prev, 0)


# V127 — Per-phase breakers (audit V126.1 : éviter qu'un 429 SQL tue chat+pitch)
# Threshold différencié par criticité user-facing :
#   chat=5  : tolérant (UX humain), 5 failures ≈ 5 req user avant fallback
#   sql=3   : strict (défense DB, T=0)
#   pitch=3 : strict (1 appel lourd 600 tokens, T=0.9)
gemini_breaker_chat = GeminiCircuitBreaker(failure_threshold=5, open_timeout=60.0)
gemini_breaker_sql = GeminiCircuitBreaker(failure_threshold=3, open_timeout=60.0)
gemini_breaker_pitch = GeminiCircuitBreaker(failure_threshold=3, open_timeout=60.0)

# Alias rétrocompat V127 — `gemini_breaker` continue de pointer sur le chat
# breaker pour ne pas casser les imports existants (gemini.py, gemini_shared.py,
# em_gemini.py, gcp_monitoring.py, main.py, admin_monitoring.py).
gemini_breaker = gemini_breaker_chat

# Helper pour reset/state des 3 breakers (admin + /health)
ALL_BREAKERS = {
    "chat": gemini_breaker_chat,
    "sql": gemini_breaker_sql,
    "pitch": gemini_breaker_pitch,
}
