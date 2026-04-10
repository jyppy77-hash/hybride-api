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
_API_MAX_TRACKED_IPS = 10_000   # S04: memory bound
_api_hits: dict[str, deque[float]] = defaultdict(deque)


def _evict_oldest_deque(d: dict[str, deque], max_size: int, pct: float = 0.2) -> None:
    """S05 V94: LRU eviction — remove oldest pct% entries by last-seen timestamp."""
    n_remove = int(max_size * pct)
    if n_remove < 1:
        n_remove = 1
    sorted_ips = sorted(d.keys(), key=lambda ip: d[ip][-1] if d[ip] else 0)
    for ip in sorted_ips[:n_remove]:
        del d[ip]
    logger.warning("[RATE_LIMIT] LRU eviction: %d IPs removed (%d remaining)", n_remove, len(d))


class APIGlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """Reject /api/* requests exceeding the global per-IP budget."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        ip = _get_real_ip(request)
        now = time.monotonic()

        # S05 V94: LRU eviction instead of full clear (prevents rate limit bypass)
        if len(_api_hits) > _API_MAX_TRACKED_IPS:
            _evict_oldest_deque(_api_hits, _API_MAX_TRACKED_IPS)

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
