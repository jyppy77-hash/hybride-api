"""
IP ban middleware — blocks banned IPs + auto-ban on flood thresholds.

Checks against `banned_ips` table in MySQL with a local cache (60s TTL).
Auto-ban thresholds (per instance, sliding window):
  - 10 req/1s  → auto_spam  (ban 1h)
  - 200 req/5min → auto_flood (ban 1h)

Cloud Run: no filesystem, everything in MySQL.
# TODO: migrate to Cloud Armor for L7 DDoS protection
"""

import logging
import os
import time
from collections import defaultdict
from ipaddress import ip_address

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── Paths excluded from auto-ban counter ─────────────────────────────────────

# NOTE AUDIT 2026-03-19: /robots.txt exclu du flood counter.
# Risque accepté: path statique léger, nécessaire pour crawlers.
_COUNTER_SKIP_PREFIXES = (
    "/ui/static/", "/static/", "/favicon", "/robots.txt",
    "/sitemap.xml", "/site.webmanifest", "/admin/",
)

# ── Kill switch ──────────────────────────────────────────────────────────────

IP_BAN_ENABLED = os.getenv("IP_BAN_ENABLED", "true").lower() == "true"

# ── Configuration ────────────────────────────────────────────────────────────

_SPAM_LIMIT = 10        # requests
_SPAM_WINDOW = 1.0      # seconds
_FLOOD_LIMIT = 200      # requests
_FLOOD_WINDOW = 300.0   # seconds (5 min)
_AUTO_BAN_HOURS = 1     # auto-ban duration

# ── Owner exclusion (never auto-ban) ────────────────────────────────────────

_OWNER_IP = os.environ.get("OWNER_IP", "").strip()
_OWNER_IPV6 = os.environ.get("OWNER_IPV6", "").strip()
_OWNER_EXACT: set[str] = {"127.0.0.1", "::1"}
if _OWNER_IP:
    _OWNER_EXACT.add(_OWNER_IP)
_OWNER_PREFIXES: list[str] = []
if _OWNER_IPV6:
    _OWNER_PREFIXES.append(_OWNER_IPV6)


def _is_owner_or_loopback(ip_str: str) -> bool:
    """Never auto-ban owner or loopback IPs."""
    if ip_str in _OWNER_EXACT:
        return True
    try:
        addr = ip_address(ip_str)
        if addr.is_loopback:
            return True
    except ValueError:
        return False
    for prefix in _OWNER_PREFIXES:
        if ip_str.startswith(prefix.rstrip(":")):
            return True
    return False


# ── Banned IPs cache (from MySQL) ───────────────────────────────────────────

_banned_set: set[str] = set()
_cache_ts: float = 0.0
_CACHE_TTL = 60  # seconds


def _extract_client_ip(request: Request) -> str:
    """Extract real client IP from Cloud Run X-Forwarded-For header.

    Takes the FIRST IP (real client on Cloud Run without CDN).
    Returns empty string for TestClient (skip ban checks in tests).
    """
    from utils import get_client_ip
    ip = get_client_ip(request)
    return "" if ip == "testclient" else ip


async def _refresh_cache() -> None:
    """Reload banned IPs from MySQL if cache expired.

    Fail-safe: on error, sets _cache_ts so we don't retry every request
    (avoids blocking workers when DB is not yet ready at Cloud Run startup).
    """
    global _banned_set, _cache_ts
    now = time.monotonic()
    if now - _cache_ts < _CACHE_TTL:
        return
    # Set timestamp BEFORE the query — prevents retry storm on failure
    _cache_ts = now
    try:
        import db_cloudsql
        rows = await db_cloudsql.async_fetchall(
            "SELECT ip FROM banned_ips "
            "WHERE is_active = 1 AND (expires_at IS NULL OR expires_at > NOW())"
        )
        _banned_set = {r["ip"] for r in rows}
    except Exception as e:
        logger.warning("[IP_BAN] cache refresh failed (will retry in %ds): %s", _CACHE_TTL, e)


def invalidate_cache() -> None:
    """Force cache refresh on next request (called after ban/unban)."""
    global _cache_ts
    _cache_ts = 0.0


async def is_banned(ip: str) -> bool:
    """Check if IP is banned (uses cache)."""
    await _refresh_cache()
    return ip in _banned_set


# ── Auto-ban: request counters (sliding window) ─────────────────────────────

_request_log: dict[str, list[float]] = defaultdict(list)


def _record_request(ip: str) -> None:
    """Record a request timestamp for the IP, prune old entries."""
    now = time.monotonic()
    timestamps = _request_log[ip]
    # Prune entries older than FLOOD_WINDOW
    cutoff = now - _FLOOD_WINDOW
    _request_log[ip] = [t for t in timestamps if t > cutoff]
    _request_log[ip].append(now)


def _check_auto_ban(ip: str) -> str | None:
    """Check if IP exceeds auto-ban thresholds. Returns source or None."""
    now = time.monotonic()
    timestamps = _request_log.get(ip, [])

    # Seuil 1: spam (10 req/1s)
    recent_1s = sum(1 for t in timestamps if now - t <= _SPAM_WINDOW)
    if recent_1s >= _SPAM_LIMIT:
        return "auto_spam"

    # Seuil 2: flood (200 req/5min)
    if len(timestamps) >= _FLOOD_LIMIT:
        return "auto_flood"

    return None


async def _auto_ban_ip(ip: str, source: str) -> None:
    """Insert auto-ban into MySQL with 1h expiry."""
    reason = {
        "auto_spam": f"{_SPAM_LIMIT} req/{_SPAM_WINDOW:.0f}s — spam bot detected",
        "auto_flood": f"{_FLOOD_LIMIT} req/{_FLOOD_WINDOW:.0f}s — flood detected",
    }.get(source, "auto-ban")
    try:
        import db_cloudsql
        await db_cloudsql.async_query(
            "INSERT INTO banned_ips (ip, reason, source, banned_by, expires_at) "
            "VALUES (%s, %s, %s, 'system', NOW() + INTERVAL %s HOUR) "
            "ON DUPLICATE KEY UPDATE is_active=1, reason=%s, source=%s, "
            "expires_at=NOW() + INTERVAL %s HOUR, banned_at=NOW()",
            (ip, reason, source, _AUTO_BAN_HOURS,
             reason, source, _AUTO_BAN_HOURS),
        )
        _banned_set.add(ip)
        # Clear the request log for this IP to avoid re-triggering
        _request_log.pop(ip, None)
        logger.warning("[IP_BAN] auto-ban %s source=%s reason=%s", ip, source, reason)
    except Exception as e:
        logger.error("[IP_BAN] auto-ban insert failed: %s", e)


# ── Middleware ───────────────────────────────────────────────────────────────

async def ip_ban_middleware(request: Request, call_next):
    """Block banned IPs + auto-ban on flood thresholds + bot whitelist/blacklist."""
    if not IP_BAN_ENABLED:
        return await call_next(request)

    client_ip = _extract_client_ip(request)
    if not client_ip:
        return await call_next(request)

    # 0. Owner/loopback always passes (fast path)
    if _is_owner_or_loopback(client_ip):
        return await call_next(request)

    # 1. Whitelist check — skip ALL rate limiting for known good bots (GCP, Google, Meta, etc.)
    from config.bot_ips import is_whitelisted_bot, is_blacklisted, is_suspicious_path
    if is_whitelisted_bot(client_ip):
        return await call_next(request)

    # 2. Blacklist check — instant block for known bad IPs (AI scrapers, Tor, etc.)
    is_bl, bl_source = is_blacklisted(client_ip)
    if is_bl:
        logger.warning("[BOT_IPS] blacklisted IP blocked: %s on %s (source=%s)", client_ip, request.url.path, bl_source)
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    # 3. Suspicious path check — instant ban for vulnerability scanners
    path = request.url.path
    if is_suspicious_path(path):
        logger.warning("[BOT_IPS] suspicious path scan: %s -> %s", client_ip, path)
        await _auto_ban_ip(client_ip, f"suspicious_path:{path[:80]}")
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    # 4. Check if already banned (MySQL cache)
    if await is_banned(client_ip):
        logger.warning("[IP_BAN] blocked %s on %s", client_ip, request.url.path)
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    # 5. Record + check auto-ban (skip static/admin paths)
    if not any(path.startswith(p) for p in _COUNTER_SKIP_PREFIXES):
        _record_request(client_ip)
        source = _check_auto_ban(client_ip)
        if source:
            await _auto_ban_ip(client_ip, source)
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    return await call_next(request)
