"""Tests for chatbot per-IP rate limiting (services/chat_rate_limit.py)."""

import os
import time
from unittest.mock import patch

import pytest


# ── Helpers ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_state():
    """Reset rate limit state between tests."""
    from services.chat_rate_limit import _chat_hits
    _chat_hits.clear()
    yield
    _chat_hits.clear()


# ── Tests ───────────────────────────────────────────────────────────────────

def test_messages_1_to_70_allowed():
    """Messages 1-70 within window should all be allowed."""
    from services.chat_rate_limit import check_chat_rate
    for i in range(70):
        allowed, retry = check_chat_rate("192.168.1.100")
        assert allowed, f"Message {i + 1} should be allowed"
        assert retry == 0


def test_message_71_blocked_with_retry():
    """Message 71 should be blocked with retry_after > 0."""
    from services.chat_rate_limit import check_chat_rate
    for _ in range(70):
        check_chat_rate("192.168.1.200")
    allowed, retry = check_chat_rate("192.168.1.200")
    assert not allowed
    assert retry > 0
    assert retry <= 3600


def test_owner_ip_always_allowed():
    """Owner IP should be exempt even beyond 70 messages."""
    with patch.dict(os.environ, {"OWNER_IP": "10.99.99.99"}):
        # Re-import to pick up new OWNER_IP
        import importlib
        import services.chat_rate_limit as mod
        importlib.reload(mod)
        try:
            for _ in range(100):
                allowed, retry = mod.check_chat_rate("10.99.99.99")
                assert allowed
                assert retry == 0
        finally:
            importlib.reload(mod)


def test_loopback_always_allowed():
    """Loopback IPs (127.0.0.1, ::1) are always exempt."""
    from services.chat_rate_limit import check_chat_rate
    for _ in range(100):
        allowed, _ = check_chat_rate("127.0.0.1")
        assert allowed


def test_reset_after_window_expired():
    """After the window expires, requests should be allowed again."""
    from services.chat_rate_limit import check_chat_rate, _chat_hits, CHAT_RATE_WINDOW
    ip = "192.168.1.50"
    # Fill up to limit
    for _ in range(70):
        check_chat_rate(ip)
    # Simulate window expiry by shifting all timestamps back
    bucket = _chat_hits[ip]
    shift = CHAT_RATE_WINDOW + 1
    _chat_hits[ip] = type(bucket)(t - shift for t in bucket)
    # Should be allowed again
    allowed, retry = check_chat_rate(ip)
    assert allowed
    assert retry == 0


def test_memory_bound_10k():
    """Dict should not exceed _CHAT_MAX_TRACKED_IPS entries."""
    from services.chat_rate_limit import check_chat_rate, _chat_hits, _CHAT_MAX_TRACKED_IPS
    # Fill with 10001 fake IPs directly
    for i in range(_CHAT_MAX_TRACKED_IPS + 1):
        _chat_hits[f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}"] = type(_chat_hits.get("x", []))()
    # Next call should trigger cleanup
    check_chat_rate("192.168.99.99")
    assert len(_chat_hits) <= _CHAT_MAX_TRACKED_IPS


def test_i18n_message_lang_en():
    """Rate limit message should be in the requested language."""
    from services.chat_rate_limit import get_rate_limit_message
    msg = get_rate_limit_message("en")
    assert "limit of 70 questions" in msg
    assert "Come back" in msg


def test_i18n_message_all_langs():
    """All 6 languages should have a message."""
    from services.chat_rate_limit import get_rate_limit_message, _RATE_LIMIT_MESSAGES
    for lang in ("fr", "en", "es", "pt", "de", "nl"):
        msg = get_rate_limit_message(lang)
        assert "70" in msg, f"Missing '70' in {lang} message"


def test_i18n_fallback_to_fr():
    """Unknown lang should fallback to French."""
    from services.chat_rate_limit import get_rate_limit_message
    msg = get_rate_limit_message("ja")
    assert "Vous avez atteint" in msg


def test_different_ips_independent():
    """Different IPs should have independent counters."""
    from services.chat_rate_limit import check_chat_rate
    # Fill IP A to the limit
    for _ in range(70):
        check_chat_rate("192.168.1.1")
    # IP B should still be allowed
    allowed, _ = check_chat_rate("192.168.2.2")
    assert allowed


def test_429_response_structure():
    """Verify the 429 response has the expected JSON structure."""
    from services.chat_rate_limit import check_chat_rate, get_rate_limit_message
    ip = "192.168.5.5"
    for _ in range(70):
        check_chat_rate(ip)
    allowed, retry_after = check_chat_rate(ip)
    assert not allowed
    # Build the response as the route would
    content = {
        "error": "rate_limit",
        "message": get_rate_limit_message("es"),
        "retry_after_seconds": retry_after,
    }
    assert content["error"] == "rate_limit"
    assert "70 preguntas" in content["message"]
    assert isinstance(content["retry_after_seconds"], int)
    assert content["retry_after_seconds"] >= 1
