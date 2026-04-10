"""
Chat rate limit — per-IP hourly limit on chatbot endpoints.

Separate from the global API rate limit (slowapi / APIGlobalRateLimitMiddleware).
Owner IPs are always exempt.
"""

import logging
import time
from collections import deque

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
# S07 V94: centralized in utils.py — single source of truth
from utils import is_owner_ip as _is_owner  # noqa: E402


# ── Rate limit state ────────────────────────────────────────────────────────

_chat_hits: dict[str, deque[float]] = {}


def _evict_oldest_deque(d: dict[str, deque], max_size: int, pct: float = 0.2) -> None:
    """S05 V94: LRU eviction — remove oldest pct% entries by last-seen timestamp."""
    n_remove = int(max_size * pct)
    if n_remove < 1:
        n_remove = 1
    sorted_ips = sorted(d.keys(), key=lambda ip: d[ip][-1] if d[ip] else 0)
    for ip in sorted_ips[:n_remove]:
        del d[ip]
    logger.warning("[CHAT_RATE_LIMIT] LRU eviction: %d IPs removed (%d remaining)", n_remove, len(d))


def check_chat_rate(ip: str) -> tuple[bool, int]:
    """Check if IP is within chat rate limit.

    Returns (allowed, retry_after_seconds).
    """
    if _is_owner(ip):
        return True, 0

    now = time.monotonic()

    # S05 V94: LRU eviction instead of full clear (prevents rate limit bypass)
    if len(_chat_hits) > _CHAT_MAX_TRACKED_IPS:
        _evict_oldest_deque(_chat_hits, _CHAT_MAX_TRACKED_IPS)

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
