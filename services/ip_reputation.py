"""
IP reputation check via AbuseIPDB API. Best-effort, non-blocking.
Env var: ABUSEIPDB_API_KEY (optional — if absent, returns unknown).
"""

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("ABUSEIPDB_API_KEY", "")
_CACHE: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 3600  # 1 hour


async def check_ip_reputation(ip: str) -> dict:
    """Check IP reputation. Returns {score, label, color}."""
    if not ip or not _API_KEY:
        return {"score": 0, "label": "Inconnu", "color": "#7f8c8d"}

    now = time.monotonic()
    cached = _CACHE.get(ip)
    if cached and now - cached[1] < _CACHE_TTL:
        return cached[0]

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(
                "https://api.abuseipdb.com/api/v2/check",
                params={"ipAddress": ip, "maxAgeInDays": 90},
                headers={"Key": _API_KEY, "Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            score = data.get("abuseConfidenceScore", 0)
    except Exception as e:
        logger.debug("[IP_REP] AbuseIPDB check failed for %s: %s", ip, e)
        result = {"score": 0, "label": "Inconnu", "color": "#7f8c8d"}
        _CACHE[ip] = (result, now)
        return result

    if score >= 75:
        result = {"score": score, "label": "Critique", "color": "#ef4444"}
    elif score >= 25:
        result = {"score": score, "label": "Suspect", "color": "#f59e0b"}
    else:
        result = {"score": score, "label": "Clean", "color": "#10b981"}

    _CACHE[ip] = (result, now)
    return result
