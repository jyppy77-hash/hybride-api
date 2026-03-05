"""
Sponsor tracking endpoint — POST /api/sponsor/track
====================================================
Receives sponsor events from frontend JS (fire-and-forget).
RGPD-compliant: stores SHA-256 hashes only, no raw IP.
Filters out owner IP to avoid polluting billing data.
"""

import hashlib
import logging
import os
import re
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

import db_cloudsql
from rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["sponsor-tracking"])

_ALLOWED_EVENTS = frozenset(["sponsor-popup-shown", "sponsor-click", "sponsor-video-played"])
_ALLOWED_DEVICES = frozenset(["mobile", "desktop", "tablet"])

# Owner IP filtering (reuse same env vars as main.py UmamiOwnerFilter)
_OWNER_IP = os.environ.get("OWNER_IP", "").strip()
_OWNER_IPV6 = os.environ.get("OWNER_IPV6", "").strip()
_OWNER_EXACT = {"127.0.0.1", "::1"}
_OWNER_PREFIXES = []
if _OWNER_IP:
    _OWNER_EXACT.add(_OWNER_IP)
if _OWNER_IPV6:
    _OWNER_PREFIXES.append(_OWNER_IPV6)


def _is_owner_ip(ip: str) -> bool:
    if ip in _OWNER_EXACT:
        return True
    return any(ip.startswith(p) for p in _OWNER_PREFIXES)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _detect_country(accept_lang: str) -> str | None:
    """Extract approximate country from Accept-Language header."""
    if not accept_lang:
        return None
    # Match patterns like "fr-FR", "en-US", "de-DE"
    m = re.search(r"([a-z]{2})-([A-Z]{2})", accept_lang)
    if m:
        return m.group(2)
    # Fallback: first 2-char lang code → uppercase as rough country
    m = re.search(r"([a-z]{2})", accept_lang)
    if m:
        return m.group(1).upper()
    return None


class SponsorEvent(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=50)
    page: str = Field(..., min_length=1, max_length=200)
    lang: str = Field(default="fr", max_length=5)
    device: str = Field(default="desktop", max_length=20)


@router.post("/sponsor/track", status_code=204, response_class=Response)
@limiter.limit("10/minute")
async def track_sponsor_event(data: SponsorEvent, request: Request):
    """Record a sponsor event (popup-shown, click, video-played)."""
    # Validate event_type
    if data.event_type not in _ALLOWED_EVENTS:
        return Response(status_code=204)

    # Filter owner IP — silent 204, no recording
    client_ip = _get_client_ip(request)
    if _is_owner_ip(client_ip):
        return Response(status_code=204)

    # Generate RGPD-compliant hashes
    ua = request.headers.get("user-agent", "")
    today = date.today().isoformat()
    session_hash = hashlib.sha256(f"{client_ip}|{ua}|{today}".encode()).hexdigest()
    user_agent_hash = hashlib.sha256(ua.encode()).hexdigest() if ua else None

    # Sanitize device
    device = data.device if data.device in _ALLOWED_DEVICES else "desktop"

    # Detect country from Accept-Language
    country = _detect_country(request.headers.get("accept-language", ""))

    try:
        await db_cloudsql.async_query(
            """
            INSERT INTO sponsor_impressions
                (event_type, page, lang, country, device, session_hash, user_agent_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (data.event_type, data.page, data.lang, country, device, session_hash, user_agent_hash),
        )
    except Exception as e:
        logger.error("[SPONSOR TRACK] insert failed: %s", e)

    return Response(status_code=204)
