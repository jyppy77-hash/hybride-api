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

# Owner IP filtering — V87 F04: single source of truth in utils.py
from utils import is_owner_ip as _is_owner_ip


def _get_client_ip(request: Request) -> str:
    from utils import get_client_ip
    return get_client_ip(request)


def _detect_country(request: Request) -> str:
    """Detect visitor country.

    Priority 1: CF-IPCountry header (real GeoIP via Cloudflare, free).
    Priority 2: Accept-Language fallback (browser locale, not reliable geo).
    CF special codes: XX (unknown), T1 (Tor) → treated as unknown.
    """
    cf = request.headers.get("cf-ipcountry", "").strip().upper()
    if cf and cf not in ("XX", "T1", ""):
        return cf
    accept_lang = request.headers.get("accept-language", "")
    if accept_lang:
        m = re.search(r"([a-z]{2})-([A-Z]{2})", accept_lang)
        if m:
            return m.group(2)
    return "??"


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
    country = _detect_country(request)
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
