"""
EuroMillions access control middleware.

Blocks all EM routes except for the site owner until public launch (15/03/2026).
Toggle via EM_PUBLIC_ACCESS env var on Cloud Run.

Access hierarchy:
  1. EM_PUBLIC_ACCESS=True → everyone passes
  2. Owner IP (/64 match) → direct access
  3. Valid press token (URL param or cookie) + not expired → access
  4. Everyone else → 302 redirect

RGPD: IPs are anonymized in all log output (IPv6 /64, IPv4 /24).
IPv6: uses /64 network match to handle privacy extensions (suffix rotation).
"""

import logging
import os
import re
import secrets
from datetime import datetime, timezone
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

# ── Press preview token ───────────────────────────────────────────────────────

PRESS_PREVIEW_TOKEN = os.getenv("PRESS_PREVIEW_TOKEN", "LOTOIA_EM_PREVIEW_2026")
PRESS_PREVIEW_EXPIRY = os.getenv("PRESS_PREVIEW_EXPIRY", "2026-03-15T00:00:00Z")
_PRESS_COOKIE_NAME = "lotoia_em_press_preview"

# ── Protected route patterns (compiled once at import) ────────────────────────

_I = re.IGNORECASE

_EM_PROTECTED = [
    re.compile(r"^/euromillions(/.*)?$", _I),            # FR pages
    re.compile(r"^/en/euromillions(/.*)?$", _I),          # EN pages
    re.compile(r"^/es/euromillions(/.*)?$", _I),          # ES pages
    re.compile(r"^/pt/euromilhoes(/.*)?$", _I),           # PT pages
    re.compile(r"^/de/euromillionen(/.*)?$", _I),         # DE pages
    re.compile(r"^/nl/euromillions(/.*)?$", _I),          # NL pages
    re.compile(r"^/api/euromillions(/.*)?$", _I),         # All EM API endpoints
    re.compile(r"^/static/pdf/em_", _I),                  # EM PDF assets
]


# ── Utility functions ─────────────────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """Extract real client IP from Cloud Run X-Forwarded-For header.

    Takes the LAST IP in X-Forwarded-For: it is the one appended by
    Google's trusted GFE proxy and cannot be forged by the client.
    (ips[0] is attacker-controlled via a spoofed header.)
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        ips = [ip.strip() for ip in forwarded.split(",")]
        return ips[-1]
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


# ── Press token functions ─────────────────────────────────────────────────────

def _parse_expiry() -> datetime | None:
    """Parse PRESS_PREVIEW_EXPIRY as timezone-aware datetime, or None."""
    try:
        return datetime.fromisoformat(PRESS_PREVIEW_EXPIRY)
    except (ValueError, TypeError):
        return None


def validate_press_token(token: str) -> bool:
    """Validate press preview token (timing-safe) and check expiry."""
    if not PRESS_PREVIEW_TOKEN:
        return False
    if not secrets.compare_digest(token, PRESS_PREVIEW_TOKEN):
        return False
    expiry = _parse_expiry()
    if expiry is None:
        return False
    return datetime.now(timezone.utc) < expiry


def get_cookie_max_age() -> int:
    """Seconds remaining until PRESS_PREVIEW_EXPIRY (0 if expired/invalid)."""
    expiry = _parse_expiry()
    if expiry is None:
        return 0
    remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
    return max(0, int(remaining))


# ── Middleware ─────────────────────────────────────────────────────────────────

async def em_access_middleware(request: Request, call_next):
    """Block EuroMillions routes for non-owner IPs (302 → homepage).

    Access hierarchy: public toggle → owner IP → press token → block.
    """
    # a) Public access toggle
    if EM_PUBLIC_ACCESS:
        return await call_next(request)

    path = request.url.path

    # b) Non-EM route → pass
    if not is_em_route(path):
        return await call_next(request)

    # c) Owner IP → pass
    client_ip = get_client_ip(request)
    if is_owner_ip(client_ip):
        logger.info("EM access granted | IP: OWNER | Route: %s", path)
        return await call_next(request)

    anon_ip = anonymize_ip(client_ip)

    # d) Extract tokens
    token_from_url = request.query_params.get("press_token")
    token_from_cookie = request.cookies.get(_PRESS_COOKIE_NAME)

    # e) Token URL (priority) — valid → set cookie + redirect to clean URL
    if token_from_url:
        if validate_press_token(token_from_url):
            clean_url = str(request.url.remove_query_params("press_token"))
            response = RedirectResponse(url=clean_url, status_code=302)
            response.set_cookie(
                key=_PRESS_COOKIE_NAME,
                value=token_from_url,
                max_age=get_cookie_max_age(),
                httponly=True,
                secure=True,
                samesite="lax",
                path="/",
            )
            logger.info(
                "EM access granted | IP: %s | Token: valid (URL) | Route: %s",
                anon_ip, path,
            )
            return response
        # Token URL invalid → block (ignore cookie)
        logger.warning(
            "EM access blocked | IP: %s | Token: invalid | Route: %s",
            anon_ip, path,
        )
        return RedirectResponse(url=get_redirect_url(path), status_code=302)

    # f) Cookie token (no URL token present)
    if token_from_cookie and validate_press_token(token_from_cookie):
        logger.info(
            "EM access granted | IP: %s | Token: valid (cookie) | Route: %s",
            anon_ip, path,
        )
        return await call_next(request)

    # g) Block
    logger.warning("EM access blocked | IP: %s | Route: %s", anon_ip, path)
    return RedirectResponse(url=get_redirect_url(path), status_code=302)
