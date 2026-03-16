"""Rate limiter partage — utilise par main.py et les routes."""

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse as StarletteJSONResponse
from slowapi import Limiter
from fastapi import Request


def _get_real_ip(request: Request) -> str:
    """Extrait l'IP client reelle derriere le proxy Cloud Run."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_get_real_ip)


# ---------------------------------------------------------------------------
# Global rate-limit middleware for /api/* paths (P1-1 audit 360)
# Sliding-window counter per IP — 60 req/min on all /api/ endpoints.
# Per-route @limiter.limit decorators (10/min chat, 10/min PDF…) still apply
# on top of this global cap.
# ---------------------------------------------------------------------------
_API_GLOBAL_LIMIT = 60          # requests per window
_API_WINDOW_SECONDS = 60        # 1-minute sliding window
_api_hits: dict[str, list[float]] = defaultdict(list)


class APIGlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """Reject /api/* requests exceeding the global per-IP budget."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        ip = _get_real_ip(request)
        now = time.monotonic()
        bucket = _api_hits[ip]

        # Prune expired timestamps
        cutoff = now - _API_WINDOW_SECONDS
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)

        if len(bucket) >= _API_GLOBAL_LIMIT:
            return StarletteJSONResponse(
                status_code=429,
                content={
                    "error": "Trop de requetes. Reessayez dans quelques instants."
                },
            )

        bucket.append(now)
        return await call_next(request)
