"""Rate limiter partage — utilise par main.py et les routes."""

import logging
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse as StarletteJSONResponse
from slowapi import Limiter
from fastapi import Request

from utils import get_client_ip

logger = logging.getLogger(__name__)


def _get_real_ip(request: Request) -> str:
    """Extrait l'IP client reelle derriere le proxy Cloud Run."""
    return get_client_ip(request)


limiter = Limiter(key_func=_get_real_ip)


# ---------------------------------------------------------------------------
# Global rate-limit middleware for /api/* paths (P1-1 audit 360)
# Sliding-window counter per IP — 60 req/min on all /api/ endpoints.
# Per-route @limiter.limit decorators (10/min chat, 10/min PDF…) still apply
# on top of this global cap.
# ---------------------------------------------------------------------------
_API_GLOBAL_LIMIT = 60          # requests per window
_API_WINDOW_SECONDS = 60        # 1-minute sliding window
_API_MAX_TRACKED_IPS = 10_000   # S04: memory bound — clear dict above this
_api_hits: dict[str, deque[float]] = defaultdict(deque)


class APIGlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """Reject /api/* requests exceeding the global per-IP budget."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        ip = _get_real_ip(request)
        now = time.monotonic()

        # S04: prevent unbounded memory growth under distributed DDoS
        if len(_api_hits) > _API_MAX_TRACKED_IPS:
            _api_hits.clear()
            logger.warning("[RATE_LIMIT] _api_hits cleared — exceeded %d entries", _API_MAX_TRACKED_IPS)

        bucket = _api_hits[ip]

        # Prune expired timestamps — S10: deque.popleft() is O(1)
        cutoff = now - _API_WINDOW_SECONDS
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= _API_GLOBAL_LIMIT:
            return StarletteJSONResponse(
                status_code=429,
                content={
                    "error": "Trop de requetes. Reessayez dans quelques instants."
                },
            )

        bucket.append(now)
        return await call_next(request)
