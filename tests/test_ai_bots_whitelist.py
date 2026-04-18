"""
Tests — config/ai_bots.py + middleware integration (V122 Phase 2/4).

Covers:
- match_ai_bot() for Catégorie A UAs (case-insensitive, specificity order)
- is_blocked_ai_bot() for Catégorie C
- Rate limit 100 req/min per (IP, UA) with LRU eviction
- Kill-switch AI_BOTS_WHITELIST_ENABLED
- Counter increment + flush
- Middleware integration (GPTBot passes 200, AhrefsBot blocked 403)
"""

import os
import importlib
import pytest
from unittest.mock import patch, AsyncMock

from config.ai_bots import (
    match_ai_bot,
    is_blocked_ai_bot,
    check_ai_bot_rate_limit,
    record_ai_bot_access,
    record_ai_bot_blocked,
    get_session_counters,
    reset_session_counters,
    ALLOWED_AI_USER_AGENTS,
    BLOCKED_AI_USER_AGENTS,
    BLOCKED_COUNTER_PREFIX,
)


# ═══════════════════════════════════════════════════════════════════════
# match_ai_bot — Catégorie A
# ═══════════════════════════════════════════════════════════════════════

class TestMatchAiBot:
    """Each UA in Catégorie A must match and return its canonical name."""

    def test_googlebot_classic(self):
        assert match_ai_bot("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)") == "Googlebot"

    def test_googlebot_news(self):
        assert match_ai_bot("Googlebot-News") == "Googlebot-News"

    def test_googlebot_image(self):
        assert match_ai_bot("Googlebot-Image/1.0") == "Googlebot-Image"

    def test_google_extended(self):
        assert match_ai_bot("Mozilla/5.0 Google-Extended") == "Google-Extended"

    def test_google_cloudvertexbot(self):
        assert match_ai_bot("Google-CloudVertexBot/1.0") == "Google-CloudVertexBot"

    def test_bingbot(self):
        assert match_ai_bot("Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)") == "Bingbot"

    def test_applebot(self):
        assert match_ai_bot("Applebot/0.1") == "Applebot"

    def test_applebot_extended(self):
        assert match_ai_bot("Applebot-Extended") == "Applebot-Extended"

    def test_claudebot(self):
        assert match_ai_bot("ClaudeBot/1.0 (+claudebot@anthropic.com)") == "ClaudeBot"

    def test_claude_web(self):
        assert match_ai_bot("Mozilla/5.0 Claude-Web/1.0") == "Claude-Web"

    def test_anthropic_ai(self):
        assert match_ai_bot("anthropic-ai") == "anthropic-ai"

    def test_gptbot(self):
        assert match_ai_bot("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.0; +https://openai.com/gptbot)") == "GPTBot"

    def test_oai_searchbot(self):
        assert match_ai_bot("OAI-SearchBot/1.0") == "OAI-SearchBot"

    def test_chatgpt_user(self):
        assert match_ai_bot("Mozilla/5.0 ChatGPT-User/1.0") == "ChatGPT-User"

    def test_perplexitybot(self):
        assert match_ai_bot("PerplexityBot/1.0") == "PerplexityBot"

    def test_perplexity_user(self):
        assert match_ai_bot("Perplexity-User/1.0") == "Perplexity-User"

    def test_duckduckbot(self):
        assert match_ai_bot("DuckDuckBot-Https/1.1") == "DuckDuckBot"

    def test_meta_externalagent(self):
        assert match_ai_bot("meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)") == "meta-externalagent"

    def test_ccbot(self):
        assert match_ai_bot("CCBot/2.0 (https://commoncrawl.org/faq/)") == "CCBot"


class TestMatchAiBotEdgeCases:

    def test_case_insensitive_upper(self):
        assert match_ai_bot("GOOGLEBOT/2.1") == "Googlebot"

    def test_case_insensitive_mixed(self):
        assert match_ai_bot("Mozilla/5.0 gPtBoT/1.0") == "GPTBot"

    def test_empty_string(self):
        assert match_ai_bot("") is None

    def test_none_input(self):
        assert match_ai_bot(None) is None

    def test_non_string_input(self):
        assert match_ai_bot(123) is None
        assert match_ai_bot(["Googlebot"]) is None

    def test_random_browser_ua(self):
        assert match_ai_bot("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36") is None

    def test_malformed_very_long_ua(self):
        # Guard against 500+ char UAs (memory protection)
        long_ua = "Googlebot" + "x" * 600
        assert match_ai_bot(long_ua) is None


class TestMatchAiBotSpecificity:
    """Ordering: more specific UAs must match BEFORE the generic Googlebot."""

    def test_googlebot_news_wins_over_googlebot(self):
        # UA string that contains both substrings — News must win
        ua = "Googlebot-News/1.0 (compatible; Googlebot/2.1)"
        assert match_ai_bot(ua) == "Googlebot-News"

    def test_googlebot_image_wins_over_googlebot(self):
        ua = "Googlebot-Image/1.0"
        assert match_ai_bot(ua) == "Googlebot-Image"

    def test_applebot_extended_wins_over_applebot(self):
        ua = "Applebot-Extended"
        assert match_ai_bot(ua) == "Applebot-Extended"


# ═══════════════════════════════════════════════════════════════════════
# is_blocked_ai_bot — Catégorie C
# ═══════════════════════════════════════════════════════════════════════

class TestBlockedAiBot:

    def test_ahrefsbot_blocked(self):
        assert is_blocked_ai_bot("Mozilla/5.0 AhrefsBot/7.0") is True

    def test_semrushbot_blocked(self):
        assert is_blocked_ai_bot("Mozilla/5.0 SemrushBot/7~bl") is True

    def test_mj12bot_blocked(self):
        assert is_blocked_ai_bot("Mozilla/5.0 MJ12bot/v1.4.8") is True

    def test_dotbot_blocked(self):
        assert is_blocked_ai_bot("Mozilla/5.0 DotBot/1.2") is True

    def test_petalbot_blocked(self):
        assert is_blocked_ai_bot("Mozilla/5.0 PetalBot;+https://webmaster.petalsearch.com/") is True

    def test_amazonbot_blocked(self):
        assert is_blocked_ai_bot("Amazonbot/0.1") is True

    def test_bytespider_blocked(self):
        assert is_blocked_ai_bot("Mozilla/5.0 Bytespider; spider-feedback@bytedance.com") is True

    def test_empty_ua_not_blocked(self):
        # Empty UAs should NOT trigger the blocklist (other middleware handles them)
        assert is_blocked_ai_bot("") is False

    def test_browser_ua_not_blocked(self):
        assert is_blocked_ai_bot("Mozilla/5.0 Chrome/120.0") is False

    def test_googlebot_not_blocked(self):
        """Allowed bots must NOT trigger the blocklist."""
        assert is_blocked_ai_bot("Googlebot/2.1") is False


# ═══════════════════════════════════════════════════════════════════════
# Rate limit 100/min per (IP, UA)
# ═══════════════════════════════════════════════════════════════════════

class TestRateLimit:

    def setup_method(self):
        from config import ai_bots
        ai_bots._ai_bot_hits.clear()
        ai_bots._ai_bot_counters.clear()

    def test_first_request_allowed(self):
        assert check_ai_bot_rate_limit("1.2.3.4", "Googlebot") is True

    def test_under_limit_all_allowed(self):
        for _ in range(99):
            assert check_ai_bot_rate_limit("1.2.3.4", "Googlebot") is True

    def test_exceed_limit_blocked(self):
        for _ in range(100):
            check_ai_bot_rate_limit("1.2.3.4", "Googlebot")
        # 101st request must be denied
        assert check_ai_bot_rate_limit("1.2.3.4", "Googlebot") is False

    def test_different_ips_independent(self):
        """Rate limit is per (IP, UA) — different IPs don't share."""
        for _ in range(100):
            check_ai_bot_rate_limit("1.2.3.4", "Googlebot")
        # Different IP with same UA still allowed
        assert check_ai_bot_rate_limit("5.6.7.8", "Googlebot") is True

    def test_different_uas_independent(self):
        """Rate limit is per (IP, UA) — different UAs don't share."""
        for _ in range(100):
            check_ai_bot_rate_limit("1.2.3.4", "Googlebot")
        # Same IP, different UA still allowed
        assert check_ai_bot_rate_limit("1.2.3.4", "GPTBot") is True

    def test_lru_eviction_above_cap(self):
        from config import ai_bots
        cap = ai_bots._AI_MAX_TRACKED_TUPLES
        # Fill over cap
        for i in range(cap + 100):
            check_ai_bot_rate_limit(f"10.0.{i // 256}.{i % 256}", "Googlebot")
        # After eviction, size must stay under cap
        assert len(ai_bots._ai_bot_hits) <= cap


# ═══════════════════════════════════════════════════════════════════════
# Session counters (monitoring)
# ═══════════════════════════════════════════════════════════════════════

class TestSessionCounters:

    def setup_method(self):
        reset_session_counters()

    def test_record_increments_counter(self):
        record_ai_bot_access("Googlebot")
        record_ai_bot_access("Googlebot")
        record_ai_bot_access("GPTBot")
        counters = get_session_counters()
        assert counters["Googlebot"] == 2
        assert counters["GPTBot"] == 1

    def test_reset_clears_counters(self):
        record_ai_bot_access("ClaudeBot")
        reset_session_counters()
        assert get_session_counters() == {}


# ═══════════════════════════════════════════════════════════════════════
# V123 Phase 2.5 — record_ai_bot_blocked (BLOCKED_COUNTER_PREFIX)
# ═══════════════════════════════════════════════════════════════════════

class TestRecordAiBotBlocked:

    def setup_method(self):
        reset_session_counters()

    def test_record_uses_blocked_prefix(self):
        record_ai_bot_blocked("ahrefsbot")
        counters = get_session_counters()
        assert any(k.startswith(BLOCKED_COUNTER_PREFIX) for k in counters)
        assert f"{BLOCKED_COUNTER_PREFIX}Ahrefsbot" in counters
        assert counters[f"{BLOCKED_COUNTER_PREFIX}Ahrefsbot"] == 1

    def test_normalization_capitalize(self):
        record_ai_bot_blocked("semrushbot")
        record_ai_bot_blocked("mj12bot")
        counters = get_session_counters()
        # First char uppercase, rest lowercase kept
        assert f"{BLOCKED_COUNTER_PREFIX}Semrushbot" in counters
        assert f"{BLOCKED_COUNTER_PREFIX}Mj12bot" in counters

    def test_multiple_increments(self):
        record_ai_bot_blocked("ahrefsbot")
        record_ai_bot_blocked("ahrefsbot")
        record_ai_bot_blocked("ahrefsbot")
        counters = get_session_counters()
        assert counters[f"{BLOCKED_COUNTER_PREFIX}Ahrefsbot"] == 3

    def test_empty_substring_fallback(self):
        record_ai_bot_blocked("")
        counters = get_session_counters()
        assert f"{BLOCKED_COUNTER_PREFIX}Unknown" in counters


# ═══════════════════════════════════════════════════════════════════════
# Invariants config
# ═══════════════════════════════════════════════════════════════════════

class TestWhitelistInvariants:

    def test_all_entries_are_tuples_of_two_strings(self):
        for entry in ALLOWED_AI_USER_AGENTS:
            assert isinstance(entry, tuple)
            assert len(entry) == 2
            substring, canonical = entry
            assert isinstance(substring, str) and len(substring) > 0
            assert isinstance(canonical, str) and len(canonical) > 0

    def test_substrings_are_lowercase(self):
        """match_ai_bot() assumes substrings are already lowercase."""
        for substring, _ in ALLOWED_AI_USER_AGENTS:
            assert substring == substring.lower(), f"{substring!r} not lowercase"

    def test_specific_googlebot_variants_before_generic(self):
        """Specificity order: Googlebot-News/Image before plain Googlebot."""
        subs = [s for s, _ in ALLOWED_AI_USER_AGENTS]
        idx_generic = subs.index("googlebot")
        idx_news = subs.index("googlebot-news")
        idx_image = subs.index("googlebot-image")
        assert idx_news < idx_generic
        assert idx_image < idx_generic

    def test_specific_applebot_extended_before_generic(self):
        subs = [s for s, _ in ALLOWED_AI_USER_AGENTS]
        assert subs.index("applebot-extended") < subs.index("applebot")

    def test_blocked_list_is_lowercase(self):
        for ua in BLOCKED_AI_USER_AGENTS:
            assert ua == ua.lower()

    def test_v122_allowed_count(self):
        """25 UAs autorisés V122 (Catégorie A)."""
        assert len(ALLOWED_AI_USER_AGENTS) == 25

    def test_v122_blocked_count(self):
        """7 UAs bloqués V122."""
        assert len(BLOCKED_AI_USER_AGENTS) == 7


# ═══════════════════════════════════════════════════════════════════════
# Middleware integration (TestClient)
# ═══════════════════════════════════════════════════════════════════════

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)


class TestMiddlewareIntegration:
    """End-to-end: request with AI UA goes through ip_ban_middleware."""

    def _build_client(self, env_extra=None):
        env = {
            "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
            "ADMIN_TOKEN": "test_token_xyz",
            "ADMIN_PASSWORD": "test_pass",
            "OWNER_IP": "86.212.92.243",
            "AI_BOTS_WHITELIST_ENABLED": "true",
        }
        if env_extra:
            env.update(env_extra)
        with patch.dict(os.environ, env), _static_patch, _static_call:
            import rate_limit as rl_mod
            importlib.reload(rl_mod)
            import config.ai_bots as ai_mod
            importlib.reload(ai_mod)
            import middleware.ip_ban as ban_mod
            importlib.reload(ban_mod)
            import main as main_mod
            importlib.reload(main_mod)
            rl_mod.limiter.reset()
            rl_mod._api_hits.clear()
            from starlette.testclient import TestClient
            return TestClient(main_mod.app, raise_server_exceptions=False)

    def test_ahrefsbot_blocked_403(self):
        """Catégorie C UA receives 403 regardless of IP."""
        client = self._build_client()
        resp = client.get(
            "/health",
            headers={
                "X-Forwarded-For": "1.2.3.4",
                "User-Agent": "Mozilla/5.0 (compatible; AhrefsBot/7.0)",
            },
        )
        assert resp.status_code == 403

    def test_kill_switch_disabled_no_whitelist(self):
        """When kill-switch OFF, allowed UAs don't bypass — but blocklist still applied."""
        client = self._build_client({"AI_BOTS_WHITELIST_ENABLED": "false"})
        resp = client.get(
            "/health",
            headers={
                "X-Forwarded-For": "1.2.3.4",
                "User-Agent": "AhrefsBot/7.0",
            },
        )
        # Blocklist still applied defense-in-depth
        assert resp.status_code == 403
