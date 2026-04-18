"""
AI bots whitelist — User-Agent-based authorization for legitimate LLM crawlers
and user-triggered fetchers (V122, Phase 2/4 Audit Bot IA).

Philosophy (JyppY, 17/04/2026): "Sovereignty over code, transparency for audits."
Code reste artisanal et souverain, contenu ouvert aux LLM légitimes pour audits
sponsors/partenaires et visibilité AI Search (SGE, Perplexity, ChatGPT Search).

Pipeline integration: stage 2 in middleware/ip_ban.py, AFTER whitelist CIDR +
suspicious path check, BEFORE blacklist IP + MySQL banned + flood counter.

Kill-switch: AI_BOTS_WHITELIST_ENABLED (default true).
Rate limit: 100 req/min per (IP, UA) tuple.
Monitoring: compteurs in-memory flush 60s vers ai_bot_access_log.

Incident déclencheur: 17/04/2026 — audit Gemini Deep Research rendu en
"pages vides" (timestamps 1er janvier 1970 = fetch échoué). Cause racine:
IPs Gemini Deep Research/Grok non whitelistées → rate-limit 10 req/1s → 403.
"""

import logging
import os
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


# ── Kill switch ──────────────────────────────────────────────────────────────

AI_BOTS_WHITELIST_ENABLED = os.getenv("AI_BOTS_WHITELIST_ENABLED", "true").lower() == "true"

# Auto-disable in local dev (no K_SERVICE) to simplify manual curl testing.
# Kept explicit so ops can override via env var.
_IS_CLOUD_RUN = bool(os.getenv("K_SERVICE"))
if not _IS_CLOUD_RUN and os.getenv("AI_BOTS_WHITELIST_ENABLED") is None:
    AI_BOTS_WHITELIST_ENABLED = False


# ── Rate limit config ────────────────────────────────────────────────────────

_AI_RATE_LIMIT = 100              # req/min per (IP, UA) tuple
_AI_RATE_WINDOW = 60.0            # seconds
_AI_MAX_TRACKED_TUPLES = 5_000    # OOM bound


# ── V123 Phase 2.5 — Blocked bots tracking (BLOCKED_COUNTER_PREFIX sentinel) ─
# Prefix pour distinguer les compteurs blocked dans _ai_bot_counters.
# Exemple: record_ai_bot_blocked("ahrefsbot") → _ai_bot_counters["BLOCKED:Ahrefsbot"] += 1.
# flush_ai_bot_counters() détecte le préfixe et insère ai_bot_access_log.status='blocked'.

BLOCKED_COUNTER_PREFIX = "BLOCKED:"


# ── Allowed UA substrings (case-insensitive, ordered by specificity) ────────
# IMPORTANT: order matters — more specific UAs FIRST (Googlebot-News before
# Googlebot) so match_ai_bot() returns the correct canonical name.

ALLOWED_AI_USER_AGENTS: list[tuple[str, str]] = [
    # (substring, canonical_name)
    # === Google ===
    ("googlebot-news",        "Googlebot-News"),
    ("googlebot-image",       "Googlebot-Image"),
    ("google-extended",       "Google-Extended"),
    ("google-cloudvertexbot", "Google-CloudVertexBot"),
    ("googlebot",             "Googlebot"),
    # === Microsoft ===
    ("bingbot",               "Bingbot"),
    # === Apple ===
    ("applebot-extended",     "Applebot-Extended"),
    ("applebot",              "Applebot"),
    # === Anthropic (BONUS Q7 — retrait blacklist CIDR V122) ===
    ("claudebot",             "ClaudeBot"),
    ("claude-web",            "Claude-Web"),
    ("anthropic-ai",          "anthropic-ai"),
    # === OpenAI (pivot politique V122) ===
    ("oai-searchbot",         "OAI-SearchBot"),
    ("chatgpt-user",          "ChatGPT-User"),
    ("gptbot",                "GPTBot"),
    # === Perplexity ===
    ("perplexity-user",       "Perplexity-User"),
    ("perplexitybot",         "PerplexityBot"),
    # === Autres search IA ===
    ("duckduckbot",           "DuckDuckBot"),
    ("yandex",                "YandexBot"),
    ("baiduspider",           "Baiduspider"),
    ("you.com",               "You.com"),
    ("youbot",                "YouBot"),
    # === Meta ===
    ("meta-externalagent",    "meta-externalagent"),
    # === Common Crawl ===
    ("ccbot",                 "CCBot"),
    # === Cohere ===
    ("cohere-ai",             "cohere-ai"),
    # === Diffbot ===
    ("diffbot",               "Diffbot"),
]


# ── Explicitly BLOCKED UAs (defense-in-depth — SEO scrapers & ambigus) ──────
# Même si l'IP change, l'UA suffit à bloquer. Conservé même si
# AI_BOTS_WHITELIST_ENABLED=false (toujours appliqué).

BLOCKED_AI_USER_AGENTS: list[str] = [
    "ahrefsbot",
    "semrushbot",
    "mj12bot",
    "dotbot",
    "petalbot",
    "amazonbot",
    "bytespider",
]


# ── Runtime state ────────────────────────────────────────────────────────────

# (ip, canonical_name) -> deque of monotonic timestamps
_ai_bot_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

# canonical_name -> in-memory counter, flushed every 60s to ai_bot_access_log
_ai_bot_counters: dict[str, int] = defaultdict(int)


# ── Public API ───────────────────────────────────────────────────────────────

def match_ai_bot(user_agent: str) -> str | None:
    """Return canonical name if UA matches an allowed AI bot, else None.

    Case-insensitive substring match. Order-sensitive (specific first).
    Returns None for empty/malformed UAs (fail-safe: not whitelisted).
    """
    if not user_agent or not isinstance(user_agent, str):
        return None
    ua_lower = user_agent.lower()
    if len(ua_lower) > 500:
        return None
    for substring, canonical in ALLOWED_AI_USER_AGENTS:
        if substring in ua_lower:
            return canonical
    return None


def is_blocked_ai_bot(user_agent: str) -> bool:
    """Return True if UA matches an explicitly blocked AI bot (defense-in-depth)."""
    if not user_agent or not isinstance(user_agent, str):
        return False
    ua_lower = user_agent.lower()
    if len(ua_lower) > 500:
        return False
    return any(substring in ua_lower for substring in BLOCKED_AI_USER_AGENTS)


def _evict_oldest_ai_tuples() -> None:
    """LRU eviction — remove oldest 20% entries when exceeding cap."""
    n_remove = max(1, _AI_MAX_TRACKED_TUPLES // 5)
    sorted_keys = sorted(
        _ai_bot_hits.keys(),
        key=lambda k: _ai_bot_hits[k][-1] if _ai_bot_hits[k] else 0,
    )
    for key in sorted_keys[:n_remove]:
        del _ai_bot_hits[key]
    logger.warning(
        "[AI_BOTS] LRU eviction: %d tuples removed (%d remaining)",
        n_remove, len(_ai_bot_hits),
    )


def check_ai_bot_rate_limit(ip: str, canonical: str) -> bool:
    """Return True if (ip, canonical) is within rate limit, False if exceeded.

    Sliding window 100/60s per tuple. Called AFTER match_ai_bot() returned a
    canonical name. LRU eviction above 5K tracked tuples.
    """
    key = (ip, canonical)
    now = time.monotonic()

    if len(_ai_bot_hits) > _AI_MAX_TRACKED_TUPLES:
        _evict_oldest_ai_tuples()

    bucket = _ai_bot_hits[key]
    cutoff = now - _AI_RATE_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.popleft()

    if len(bucket) >= _AI_RATE_LIMIT:
        return False

    bucket.append(now)
    return True


def record_ai_bot_access(canonical: str) -> None:
    """Increment session counter for this canonical bot name (status='allowed').

    Flushed batched every 60s to ai_bot_access_log via flush_ai_bot_counters().
    """
    _ai_bot_counters[canonical] += 1


def record_ai_bot_blocked(ua_substring: str) -> None:
    """Increment blocked counter for a Catégorie C User-Agent substring (V123).

    Called by middleware when is_blocked_ai_bot() matches. The substring
    (e.g. "ahrefsbot") is stored prefixed by BLOCKED_COUNTER_PREFIX and
    capitalized (AhrefsBot) in the in-memory counter.
    flush_ai_bot_counters() detects the prefix and inserts with status='blocked'.
    """
    canonical = ua_substring[:1].upper() + ua_substring[1:] if ua_substring else "Unknown"
    key = f"{BLOCKED_COUNTER_PREFIX}{canonical}"
    _ai_bot_counters[key] += 1


def get_session_counters() -> dict[str, int]:
    """Return a snapshot of in-memory counters (for tests/debug)."""
    return dict(_ai_bot_counters)


def reset_session_counters() -> None:
    """Reset in-memory counters (called after successful flush)."""
    _ai_bot_counters.clear()
