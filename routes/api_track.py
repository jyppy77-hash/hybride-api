"""
Universal event tracking endpoint — POST /api/track
=====================================================
Receives all frontend events from tracker.js (fire-and-forget).
RGPD-compliant: stores SHA-256 session hash only, no raw IP.
Filters out owner IP to avoid polluting analytics data.
"""

import hashlib
import json
import logging
import os
import re
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import Response

import db_cloudsql
from rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["tracking"])

_ALLOWED_DEVICES = frozenset(["mobile", "desktop", "tablet"])
_MAX_EVENT_LEN = 80
_MAX_PAGE_LEN = 200
_MAX_PRODUCT_CODE_LEN = 20

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
    from utils import get_client_ip
    return get_client_ip(request)


def _detect_country(accept_lang: str) -> str:
    """Extract browser locale from Accept-Language header (NOT GeoIP).

    Returns a 2-letter country code derived from the browser's language
    preference (e.g. "fr-FR" → "FR", "en-US" → "US"). This reflects
    the user's language settings, not their actual geolocation.
    Stored in event_log.country column for backward compatibility.
    """
    if not accept_lang:
        return ""
    m = re.search(r"([a-z]{2})-([A-Z]{2})", accept_lang)
    if m:
        return m.group(2)
    m = re.search(r"([a-z]{2})", accept_lang)
    if m:
        return m.group(1).upper()
    return ""


@router.post("/track", status_code=204, response_class=Response)
@limiter.limit("30/minute")
async def track_event(request: Request):
    """Record a universal frontend event (fire-and-forget).

    Parses body with json.loads to accept any Content-Type
    (sendBeacon may send text/plain despite Blob hint).
    """
    # Robust JSON parsing — accept text/plain AND application/json
    try:
        body = await request.body()
        data = json.loads(body)
    except (json.JSONDecodeError, Exception):
        return Response(status_code=204)

    # Validate required field
    event = data.get("event", "")
    if not event or not isinstance(event, str) or len(event) > _MAX_EVENT_LEN:
        return Response(status_code=204)

    # Filter owner IP — silent 204
    client_ip = _get_client_ip(request)
    if _is_owner_ip(client_ip):
        return Response(status_code=204)

    # Session hash (RGPD)
    ua = request.headers.get("user-agent", "")
    today = date.today().isoformat()
    session_hash = hashlib.sha256(f"{client_ip}|{ua}|{today}".encode()).hexdigest()

    # Extract and sanitize fields
    page = str(data.get("page", ""))[:_MAX_PAGE_LEN]
    module = str(data.get("module", ""))[:80]
    lang = str(data.get("lang", ""))[:5]
    device = str(data.get("device", "desktop"))
    if device not in _ALLOWED_DEVICES:
        device = "desktop"
    country = _detect_country(request.headers.get("accept-language", ""))
    product_code = str(data.get("product_code", ""))[:_MAX_PRODUCT_CODE_LEN] or None
    meta = data.get("meta")
    meta_json = json.dumps(meta) if isinstance(meta, dict) else None

    try:
        await db_cloudsql.async_query(
            """
            INSERT INTO event_log
                (event_type, page, module, lang, device, country, session_hash, meta_json, product_code)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (event, page, module, lang, device,
             country, session_hash, meta_json, product_code),
        )
    except Exception as e:
        logger.error("[EVENT TRACK] insert failed: %s", e)

    return Response(status_code=204)
