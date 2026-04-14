"""
Shared utilities — used across routes, middleware, and main.py.
"""

import os
from ipaddress import ip_address, ip_network

from fastapi import Request

# ── Owner IP detection (single source of truth) ─────────────────────────────
# IPv4: exact match.  IPv6: CIDR /64 (handles privacy extensions).
# Aligned with middleware/ip_ban.py logic.

_OWNER_IP_RAW = os.environ.get("OWNER_IP", "").strip()
_OWNER_IPV6_RAW = os.environ.get("OWNER_IPV6", "").strip()

# V113: support pipe-separated multi-IP (e.g. "ip1|ip2|ip3")
# V114: support CIDR notation for IPv4 (e.g. "92.184.0.0/16")
_OWNER_EXACT: set[str] = {"127.0.0.1", "::1"}
_owner_nets_v4: list = []
for _ip in _OWNER_IP_RAW.split("|"):
    _ip = _ip.strip()
    if not _ip:
        continue
    if "/" in _ip:
        try:
            _owner_nets_v4.append(ip_network(_ip, strict=False))
        except ValueError:
            import logging as _logging
            _logging.getLogger(__name__).warning("Invalid CIDR in OWNER_IP: %s", _ip)
    else:
        _OWNER_EXACT.add(_ip)

_owner_nets_v6: list = []
for _v6_raw in _OWNER_IPV6_RAW.split("|"):
    _v6_raw = _v6_raw.strip()
    if not _v6_raw:
        continue
    _v6 = _v6_raw.rstrip(":")
    if "::" not in _v6:
        _v6 += "::"
    try:
        _owner_nets_v6.append(ip_network(f"{_v6}/64", strict=False))
    except ValueError:
        pass


def is_owner_ip(ip: str) -> bool:
    """Owner IP detection — IPv4 exact + IPv6 CIDR /64 + loopback.

    S07 V94: single source of truth for owner detection.
    V113: supports pipe-separated multi-IP in OWNER_IP / OWNER_IPV6.
    V114: supports CIDR IPv4 notation (e.g. 92.184.0.0/16).
    Used by middleware/ip_ban.py, services/chat_rate_limit.py, routes/*.
    """
    if ip in _OWNER_EXACT:
        return True
    try:
        addr = ip_address(ip)
        if addr.is_loopback:
            return True
        for net in _owner_nets_v4:
            if addr in net:
                return True
        for net in _owner_nets_v6:
            if addr in net:
                return True
    except ValueError:
        pass
    return False


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


def detect_country(request: Request) -> str | None:
    """Detect visitor country from CF-IPCountry header with Accept-Language fallback.

    CF special codes: XX (unknown), T1 (Tor) → treated as unknown.
    Returns None if unavailable.
    """
    import re
    cf = request.headers.get("cf-ipcountry", "").strip().upper()
    if cf and cf not in ("XX", "T1", ""):
        return cf
    accept_lang = request.headers.get("accept-language", "")
    if accept_lang:
        m = re.search(r"([a-z]{2})-([A-Z]{2})", accept_lang)
        if m:
            return m.group(2)
    return None


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
