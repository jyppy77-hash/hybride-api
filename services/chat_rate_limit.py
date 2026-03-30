"""
Chat rate limit — per-IP hourly limit on chatbot endpoints.

Separate from the global API rate limit (slowapi / APIGlobalRateLimitMiddleware).
Owner IPs are always exempt.
"""

import logging
import os
import time
from collections import deque
from ipaddress import ip_address, ip_network

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────────────

CHAT_RATE_LIMIT = 70          # max messages per window
CHAT_RATE_WINDOW = 3600       # 1 hour (seconds)
_CHAT_MAX_TRACKED_IPS = 10_000  # memory bound

# ── i18n messages ───────────────────────────────────────────────────────────

_RATE_LIMIT_MESSAGES: dict[str, str] = {
    "fr": "Vous avez atteint la limite de 70 questions par heure. Revenez dans quelques minutes !",
    "en": "You've reached the limit of 70 questions per hour. Come back in a few minutes!",
    "es": "Has alcanzado el límite de 70 preguntas por hora. ¡Vuelve en unos minutos!",
    "pt": "Atingiu o limite de 70 perguntas por hora. Volte dentro de alguns minutos!",
    "de": "Du hast das Limit von 70 Fragen pro Stunde erreicht. Komm in ein paar Minuten wieder!",
    "nl": "Je hebt de limiet van 70 vragen per uur bereikt. Kom over een paar minuten terug!",
}

# ── Owner exclusion ─────────────────────────────────────────────────────────

_OWNER_IP = os.environ.get("OWNER_IP", "").strip()
_OWNER_IPV6 = os.environ.get("OWNER_IPV6", "").strip()
_OWNER_EXACT: set[str] = {"127.0.0.1", "::1"}
if _OWNER_IP:
    _OWNER_EXACT.add(_OWNER_IP)

_owner_net_v6 = None
if _OWNER_IPV6:
    _v6_clean = _OWNER_IPV6.rstrip(":")
    if "::" not in _v6_clean:
        _v6_clean += "::"
    try:
        _owner_net_v6 = ip_network(f"{_v6_clean}/64", strict=False)
    except ValueError:
        pass


def _is_owner(ip_str: str) -> bool:
    """Check if IP belongs to owner (exempt from rate limit)."""
    if ip_str in _OWNER_EXACT:
        return True
    try:
        addr = ip_address(ip_str)
        if addr.is_loopback:
            return True
        if _owner_net_v6 and addr in _owner_net_v6:
            return True
    except ValueError:
        return False
    return False


# ── Rate limit state ────────────────────────────────────────────────────────

_chat_hits: dict[str, deque[float]] = {}


def check_chat_rate(ip: str) -> tuple[bool, int]:
    """Check if IP is within chat rate limit.

    Returns (allowed, retry_after_seconds).
    """
    if _is_owner(ip):
        return True, 0

    now = time.monotonic()

    # Memory bound: clear all if too many IPs tracked
    if len(_chat_hits) > _CHAT_MAX_TRACKED_IPS:
        _chat_hits.clear()
        logger.warning("[CHAT_RATE_LIMIT] _chat_hits cleared — exceeded %d entries", _CHAT_MAX_TRACKED_IPS)

    if ip not in _chat_hits:
        _chat_hits[ip] = deque()

    bucket = _chat_hits[ip]

    # Prune expired timestamps
    cutoff = now - CHAT_RATE_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.popleft()

    if len(bucket) >= CHAT_RATE_LIMIT:
        oldest = bucket[0]
        retry_after = int(CHAT_RATE_WINDOW - (now - oldest))
        return False, max(retry_after, 1)

    bucket.append(now)
    return True, 0


def get_rate_limit_message(lang: str = "fr") -> str:
    """Return the i18n rate limit message for the given language."""
    return _RATE_LIMIT_MESSAGES.get(lang, _RATE_LIMIT_MESSAGES["fr"])
