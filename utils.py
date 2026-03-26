"""
Shared utilities — used across routes, middleware, and main.py.
"""

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Extract real client IP from Cloud Run X-Forwarded-For header.

    On Cloud Run (no CDN), X-Forwarded-For = "client_ip, gfe_proxy_ip".
    The FIRST element is the real client IP.
    The LAST is the Google Front End proxy IP (shared across all visitors
    on the same PoP — useless for rate limiting).

    Falls back to request.client.host when header is absent (local dev).
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client_host = request.client.host if request.client else ""
    return client_host or ""


def get_client_ip_from_scope(scope: dict) -> str:
    """Extract real client IP from raw ASGI scope headers.

    Same logic as get_client_ip() but operates on raw ASGI scope
    (for pure ASGI middleware that doesn't have a Request object).
    """
    headers_raw = dict(scope.get("headers", []))
    forwarded = headers_raw.get(b"x-forwarded-for", b"").decode()
    if forwarded:
        return forwarded.split(",")[0].strip()
    client_addr = scope.get("client")
    return client_addr[0] if client_addr else ""
