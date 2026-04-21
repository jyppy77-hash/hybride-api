"""
Circuit breaker pour les appels Gemini API.

Etats :
  CLOSED    → fonctionnement normal
  OPEN      → fallback immediat (apres 3 echecs consecutifs, pendant 60s)
  HALF_OPEN → 1 requete test autorisee, si OK → CLOSED, sinon → OPEN
"""

import asyncio
import random
import time
import logging

import httpx

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Levee quand le circuit est ouvert — le caller doit faire fallback."""


# V129.1 — Retry calibration (calibration post-mortem logs prod 21/04/2026).
# Backoff exponential large (2/4/8s) au lieu de 200/400ms : Google 429 signale
# un throttle per-second, retry 200ms plus tard garantit un nouveau rejet.
# 2/4/8s laisse la fenêtre de throttle se réinitialiser côté Google.
#
# V129.1 refinement — jitter [0, 1.0] : sans jitter, 2 users en 429 simultanés
# retry synchronisés à T+2s → collision garantie. random.uniform(0, 1.0) étale
# les retries sur une fenêtre de 1s (pattern AWS/Google SRE "equal jitter").
_V129_RETRY_BACKOFF_BASE = 2.0  # seconds (was 0.2 in V128)
_V129_RETRY_CAP_TOTAL = 14.0    # seconds (was 3.0 in V128), défensif pour max_retries=3+
_V129_RETRY_JITTER_MAX = 1.0    # seconds — uniform jitter added to backoff


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
        self,
        client: httpx.AsyncClient,
        *args,
        max_retries: int = 0,
        **kwargs,
    ) -> httpx.Response:
        """Wrap client.post() with circuit breaker + optional V128 retry on 429.

        max_retries=0 (default, V127 behavior): single attempt, failure recorded
        on 429/5xx, success otherwise. Zero regression vs V127.

        max_retries=N (V128, opt-in): retry exponential backoff on 429.
          - Backoff = 200ms * 2**attempt (200, 400, 800ms...), honoring
            Retry-After header when present (numeric seconds).
          - Total wall time capped at 3s cumulative — abort if exhausted.
          - CB state re-checked at each iteration (OPEN → abort immediately).
          - Max 1 failure recorded per user request (not per attempt):
            retries are silent, only the terminal response counts.
          - Retry only on 429 (throttle). 5xx / network exceptions = 1 attempt.
        """
        start = time.monotonic()
        last_response: httpx.Response | None = None

        for attempt in range(max_retries + 1):
            # CB state check — respect OPEN set by concurrent failures
            if self.state == self.OPEN:
                raise CircuitOpenError("Circuit ouvert — fallback immediat")

            # V129.1: cap total wall time élargi 3s → 14s (défensif max_retries=3+).
            if attempt > 0 and time.monotonic() - start >= _V129_RETRY_CAP_TOTAL:
                logger.info(
                    "[V129_1_RETRY] cap total=%.0fs exhausted before attempt=%d",
                    _V129_RETRY_CAP_TOTAL, attempt,
                )
                break

            try:
                response = await client.post(*args, **kwargs)
            except (httpx.TimeoutException, httpx.ConnectError, OSError):
                # Network exception = hard failure, no retry (different failure mode)
                self._record_failure()
                raise

            last_response = response

            # V128→V129.1: retry on 429 if budget remaining. Backoff 2/4/8s
            # (était 200/400/800ms) + jitter [0,1s]. Cap total 14s (était 3s).
            if response.status_code == 429 and attempt < max_retries:
                retry_after_raw = response.headers.get("retry-after")
                # 2s, 4s, 8s + jitter uniform [0, 1.0s] → 2-3s, 4-5s, 8-9s.
                # Jitter évite les retries synchronisés (thundering herd)
                # quand plusieurs users tombent en 429 dans la même ms.
                backoff = (
                    _V129_RETRY_BACKOFF_BASE * (2 ** attempt)
                    + random.uniform(0, _V129_RETRY_JITTER_MAX)
                )
                if retry_after_raw:
                    try:
                        backoff = float(retry_after_raw)
                    except (ValueError, TypeError):
                        pass  # non-numeric (HTTP-date) → keep exponential default

                remaining = _V129_RETRY_CAP_TOTAL - (time.monotonic() - start)
                if remaining <= 0:
                    logger.info("[V129_1_RETRY] no budget left at attempt=%d", attempt)
                    break
                backoff = min(backoff, remaining)

                logger.info(
                    "[V129_1_RETRY] attempt=%d/%d 429, backoff=%.1fs (retry_after=%r)",
                    attempt + 1, max_retries, backoff, retry_after_raw,
                )
                await asyncio.sleep(backoff)
                continue  # next iteration

            # Terminal response (not 429, OR 429 on last attempt)
            if response.status_code >= 500 or response.status_code == 429:
                self._record_failure()
            else:
                self._record_success()
            return response

        # Loop exhausted via cap — record 1 failure on last response (max 1/user)
        if last_response is not None:
            self._record_failure()
            return last_response

        # Defensive — unreachable (except branch raises before reaching here)
        raise CircuitOpenError("V128 retry exhausted without response")

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
#   chat=5   : tolérant (UX humain), 5 failures ≈ 5 req user avant fallback
#   sql=3    : strict (défense DB, T=0)
#   pitch=10 : V129.1 — threshold élargi 3→10 après calibration post-mortem
#             logs prod 21/04/2026. Avec backoff 2/4/8s, 3 failures cascade
#             trop vite pendant fenêtres throttle adaptatif Google.
gemini_breaker_chat = GeminiCircuitBreaker(failure_threshold=5, open_timeout=60.0)
gemini_breaker_sql = GeminiCircuitBreaker(failure_threshold=3, open_timeout=60.0)
gemini_breaker_pitch = GeminiCircuitBreaker(failure_threshold=10, open_timeout=60.0)

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
