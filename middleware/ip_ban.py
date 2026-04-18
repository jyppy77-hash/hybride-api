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
import time
from collections import defaultdict

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

import os

# ── Kill switch ──────────────────────────────────────────────────────────────

IP_BAN_ENABLED = os.getenv("IP_BAN_ENABLED", "true").lower() == "true"

# ── Configuration ────────────────────────────────────────────────────────────

_SPAM_LIMIT = 10        # requests
_SPAM_WINDOW = 1.0      # seconds
_FLOOD_LIMIT = 200      # requests
_FLOOD_WINDOW = 300.0   # seconds (5 min)
_AUTO_BAN_HOURS = 1     # auto-ban duration

# ── Owner exclusion (never auto-ban) ────────────────────────────────────────
# S07 V94: centralized in utils.py — single source of truth
from utils import is_owner_ip as _is_owner_or_loopback  # noqa: E402


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
_MAX_TRACKED_IPS = 10_000  # S04 V94: memory bound


def _evict_oldest(d: dict, max_size: int, pct: float = 0.2) -> None:
    """S04 V94: LRU eviction — remove oldest pct% entries by last-seen timestamp."""
    n_remove = int(max_size * pct)
    if n_remove < 1:
        n_remove = 1
    sorted_ips = sorted(d.keys(), key=lambda ip: d[ip][-1] if d[ip] else 0)
    for ip in sorted_ips[:n_remove]:
        del d[ip]
    logger.warning("[IP_BAN] LRU eviction: %d IPs removed (%d remaining)", n_remove, len(d))


def _record_request(ip: str) -> None:
    """Record a request timestamp for the IP, prune old entries."""
    now = time.monotonic()
    timestamps = _request_log[ip]
    # Prune entries older than FLOOD_WINDOW
    cutoff = now - _FLOOD_WINDOW
    _request_log[ip] = [t for t in timestamps if t > cutoff]
    _request_log[ip].append(now)
    # S04 V94: LRU eviction when exceeding cap
    if len(_request_log) > _MAX_TRACKED_IPS:
        _evict_oldest(_request_log, _MAX_TRACKED_IPS)


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

    # 2. Suspicious path check — défense-en-profondeur (appliqué avant AI bots)
    # V122: déplacé AVANT le stage AI pour empêcher tout bot IA détourné de scanner /.env
    path = request.url.path
    if is_suspicious_path(path):
        logger.warning("[BOT_IPS] suspicious path scan: %s -> %s", client_ip, path)
        await _auto_ban_ip(client_ip, f"suspicious_path:{path[:80]}")
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    # 3. V122 — AI UA whitelist (pivot "Sovereignty over code, transparency for audits")
    # Kill-switch: AI_BOTS_WHITELIST_ENABLED (default true on Cloud Run, false in dev).
    # Blocklist UA (Ahrefs/Semrush/...) appliquée même si kill-switch OFF (défense-en-profondeur).
    from config.ai_bots import (
        AI_BOTS_WHITELIST_ENABLED, BLOCKED_AI_USER_AGENTS, match_ai_bot, is_blocked_ai_bot,
        check_ai_bot_rate_limit, record_ai_bot_access, record_ai_bot_blocked,
    )
    ua = request.headers.get("user-agent", "")
    if is_blocked_ai_bot(ua):
        # V123 Phase 2.5 — log blocked bot for admin monitoring widget 4
        ua_lower = ua.lower()
        matched_sub = next((s for s in BLOCKED_AI_USER_AGENTS if s in ua_lower), "unknown")
        record_ai_bot_blocked(matched_sub)
        logger.warning("[AI_BOTS] blocked UA: %s (match=%s) on %s (ip=%s)",
                       ua[:100], matched_sub, path, client_ip)
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    if AI_BOTS_WHITELIST_ENABLED:
        canonical = match_ai_bot(ua)
        if canonical:
            if not check_ai_bot_rate_limit(client_ip, canonical):
                logger.warning("[AI_BOTS] rate limit exceeded: %s (ip=%s) on %s",
                               canonical, client_ip, path)
                return JSONResponse(
                    status_code=429,
                    content={"error": "Trop de requetes. Reessayez dans quelques instants."},
                )
            record_ai_bot_access(canonical)
            # V123 Phase 2.5 Extension A — mark request for downstream handlers
            # (api_track skip, template injection for analytics guard).
            request.state.ai_bot_canonical = canonical
            # Bonus C — downgrade allowed log to debug (100K+ req/day economy)
            logger.debug("[AI_BOTS] allowed: %s (ip=%s) on %s", canonical, client_ip, path)
            return await call_next(request)

    # 4. Blacklist check — instant block for known bad IPs (Tor, IPsum, PetalBot, etc.)
    is_bl, bl_source = is_blacklisted(client_ip)
    if is_bl:
        logger.warning("[BOT_IPS] blacklisted IP blocked: %s on %s (source=%s)", client_ip, request.url.path, bl_source)
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    # 5. Check if already banned (MySQL cache)
    if await is_banned(client_ip):
        logger.warning("[IP_BAN] blocked %s on %s", client_ip, request.url.path)
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    # 6. Record + check auto-ban (skip static/admin paths)
    if not any(path.startswith(p) for p in _COUNTER_SKIP_PREFIXES):
        _record_request(client_ip)
        source = _check_auto_ban(client_ip)
        if source:
            await _auto_ban_ip(client_ip, source)
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    return await call_next(request)
