"""
EuroMillions access control middleware.

Blocks all EM routes except for the site owner until public launch (15/03/2026).
Toggle via EM_PUBLIC_ACCESS env var on Cloud Run.

RGPD: IPs are anonymized in all log output (IPv6 /64, IPv4 /24).
IPv6: uses /64 network match to handle privacy extensions (suffix rotation).
"""

import logging
import os
import re
from ipaddress import ip_address, ip_network

from fastapi import Request
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

EM_PUBLIC_ACCESS = os.getenv("EM_PUBLIC_ACCESS", "false").lower() in (
    "true", "1", "yes",
)

OWNER_IPV6 = "2a01:cb05:8700:5900:180b:4c1b:2226:7349"

# /64 network match: covers IPv6 privacy extensions (OS rotates the suffix).
# The /64 prefix is assigned per household by the ISP — safe to match on.
_OWNER_NET_V6 = ip_network(OWNER_IPV6 + "/64", strict=False)

# Optional IPv4 from env (already set on Cloud Run for Umami owner filter).
_OWNER_IPV4 = os.getenv("OWNER_IP", "").strip()

# ── Protected route patterns (compiled once at import) ────────────────────────

_EM_PROTECTED = [
    re.compile(r"^/euromillions(/.*)?$"),            # FR pages
    re.compile(r"^/en/euromillions(/.*)?$"),          # EN pages
    re.compile(r"^/es/euromillions(/.*)?$"),          # ES pages
    re.compile(r"^/pt/euromilhoes(/.*)?$"),           # PT pages
    re.compile(r"^/de/euromillionen(/.*)?$"),         # DE pages
    re.compile(r"^/nl/euromillions(/.*)?$"),          # NL pages
    re.compile(r"^/api/euromillions(/.*)?$"),         # All EM API endpoints
    re.compile(r"^/static/pdf/em_"),                  # EM PDF assets
]


# ── Utility functions ─────────────────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """Extract real client IP from Cloud Run X-Forwarded-For header."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def is_owner_ip(client_ip_str: str) -> bool:
    """Check if client IP belongs to the site owner (IPv6 /64 or IPv4)."""
    try:
        client = ip_address(client_ip_str)
    except ValueError:
        return False
    if client.is_loopback:
        return True
    if client.version == 6:
        return client in _OWNER_NET_V6
    if _OWNER_IPV4:
        try:
            return client == ip_address(_OWNER_IPV4)
        except ValueError:
            pass
    return False


def is_em_route(path: str) -> bool:
    """Check if path matches any protected EuroMillions route."""
    return any(p.match(path) for p in _EM_PROTECTED)


def get_redirect_url(path: str) -> str:
    """Derive language-appropriate homepage from the blocked URL path."""
    parts = path.strip("/").split("/")
    if parts and parts[0] in ("en", "es", "pt", "de", "nl"):
        return f"/{parts[0]}"
    return "/"


def anonymize_ip(ip_str: str) -> str:
    """Anonymize IP for RGPD-compliant logging (keep /64 for IPv6, /24 for IPv4)."""
    try:
        ip_obj = ip_address(ip_str)
        if ip_obj.version == 6:
            parts = ip_obj.exploded.split(":")
            return ":".join(parts[:4]) + ":xxxx:xxxx:xxxx:xxxx"
        parts = str(ip_obj).split(".")
        return ".".join(parts[:3]) + ".xxx"
    except ValueError:
        return "invalid"


# ── Middleware ─────────────────────────────────────────────────────────────────

async def em_access_middleware(request: Request, call_next):
    """Block EuroMillions routes for non-owner IPs (302 → homepage)."""
    if EM_PUBLIC_ACCESS:
        return await call_next(request)

    path = request.url.path

    if not is_em_route(path):
        return await call_next(request)

    client_ip = get_client_ip(request)

    if is_owner_ip(client_ip):
        logger.info("EM access granted | IP: OWNER | Route: %s", path)
        return await call_next(request)

    anon_ip = anonymize_ip(client_ip)
    logger.warning("EM access blocked | IP: %s | Route: %s", anon_ip, path)
    return RedirectResponse(url=get_redirect_url(path), status_code=302)
