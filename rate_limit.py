"""Rate limiter partage — utilise par main.py et les routes."""

from slowapi import Limiter
from fastapi import Request


def _get_real_ip(request: Request) -> str:
    """Extrait l'IP client reelle derriere le proxy Cloud Run."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_get_real_ip)
