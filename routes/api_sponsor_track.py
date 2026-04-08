"""
Sponsor tracking endpoint — POST /api/sponsor/track
====================================================
Receives sponsor events from frontend JS (fire-and-forget).
RGPD-compliant: stores SHA-256 hashes only, no raw IP.
Filters out owner IP to avoid polluting billing data.
"""

import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

import db_cloudsql
from rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["sponsor-tracking"])

# E5 banner (sponsor-result-shown / sponsor-inline-shown) is tracked via
# simulateur.js (Loto) and simulateur-em.js (EM) — inline sponsors shown
# after grille generation. sponsor-pdf-downloaded is tracked from PDF CTA.
_ALLOWED_EVENTS = frozenset(["sponsor-popup-shown", "sponsor-click", "sponsor-video-played", "sponsor-inline-shown", "sponsor-result-shown", "sponsor-pdf-downloaded"])
_ALLOWED_DEVICES = frozenset(["mobile", "desktop", "tablet"])

# Valid sponsor IDs loaded from sponsors.json (S10 — integrity check)
_VALID_SPONSOR_IDS: frozenset[str] = frozenset()
try:
    _sponsors_path = Path(__file__).resolve().parent.parent / "config" / "sponsors.json"
    with open(_sponsors_path, encoding="utf-8") as _f:
        _cfg = json.load(_f)
    _VALID_SPONSOR_IDS = frozenset(
        slot["id"]
        for group in _cfg.get("slots", {}).values()
        for slot in group.values()
        if isinstance(slot, dict) and "id" in slot
    )
except Exception:
    logger.warning("[SPONSOR TRACK] Failed to load valid sponsor IDs from sponsors.json")

# Owner IP filtering — V87 F04: single source of truth in utils.py
from utils import is_owner_ip as _is_owner_ip


def _get_client_ip(request: Request) -> str:
    from utils import get_client_ip
    return get_client_ip(request)


def _detect_country(request: Request) -> str | None:
    """Detect visitor country (CF-IPCountry GeoIP → Accept-Language fallback)."""
    cf = request.headers.get("cf-ipcountry", "").strip().upper()
    if cf and cf not in ("XX", "T1", ""):
        return cf
    accept_lang = request.headers.get("accept-language", "")
    if accept_lang:
        m = re.search(r"([a-z]{2})-([A-Z]{2})", accept_lang)
        if m:
            return m.group(2)
    return None


class SponsorEvent(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=50)
    page: str = Field(..., min_length=1, max_length=200)
    lang: str = Field(default="fr", max_length=5)
    device: str = Field(default="desktop", max_length=20)
    sponsor_id: str | None = Field(default=None, max_length=50)


@router.post("/sponsor/track", status_code=204, response_class=Response)
@limiter.limit("30/minute")
async def track_sponsor_event(data: SponsorEvent, request: Request):
    """Record a sponsor event (popup-shown, click, video-played)."""
    # Validate event_type
    if data.event_type not in _ALLOWED_EVENTS:
        return Response(status_code=204)

    # Validate sponsor_id — reject unknown IDs (S10 integrity)
    if data.sponsor_id and _VALID_SPONSOR_IDS and data.sponsor_id not in _VALID_SPONSOR_IDS:
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
    country = _detect_country(request)

    try:
        await db_cloudsql.async_query(
            """
            INSERT INTO sponsor_impressions
                (event_type, page, lang, country, device, session_hash, user_agent_hash, sponsor_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (data.event_type, data.page, data.lang, country, device, session_hash, user_agent_hash, data.sponsor_id),
        )
    except Exception as e:
        logger.error("[SPONSOR TRACK] insert failed: %s", e)

    return Response(status_code=204, headers={"Cache-Control": "no-store"})
