"""
Tests — rate_limit.py IP extraction (H2 fix: use LAST IP from X-Forwarded-For).

Verifies that the rate limiter correctly extracts the trusted proxy IP
(last in the chain), not the client-controlled first IP.
"""

import pytest
from unittest.mock import MagicMock

from rate_limit import _get_real_ip


def _make_request(forwarded: str | None = None, client_host: str = "127.0.0.1"):
    """Create a mock FastAPI Request with optional X-Forwarded-For header."""
    request = MagicMock()
    headers = {}
    if forwarded is not None:
        headers["x-forwarded-for"] = forwarded
    request.headers = headers
    request.client = MagicMock()
    request.client.host = client_host
    return request


class TestGetRealIp:

    def test_single_ip(self):
        """Single IP in X-Forwarded-For → extracted correctly."""
        req = _make_request(forwarded="1.2.3.4")
        assert _get_real_ip(req) == "1.2.3.4"

    def test_multiple_ips_uses_last(self):
        """Multiple IPs → last IP used (trusted proxy, not spoofable)."""
        req = _make_request(forwarded="10.0.0.1, 192.168.1.1, 34.56.78.90")
        assert _get_real_ip(req) == "34.56.78.90"

    def test_no_forwarded_header_falls_back(self):
        """No X-Forwarded-For → falls back to request.client.host."""
        req = _make_request(forwarded=None, client_host="192.168.0.5")
        assert _get_real_ip(req) == "192.168.0.5"

    def test_two_ips_uses_last(self):
        """Two IPs → last IP used (Cloud Run adds its proxy IP last)."""
        req = _make_request(forwarded="spoofed.ip, 100.200.300.400")
        assert _get_real_ip(req) == "100.200.300.400"

    def test_whitespace_stripped(self):
        """Whitespace around IPs is stripped."""
        req = _make_request(forwarded="  10.0.0.1 ,  34.56.78.90  ")
        assert _get_real_ip(req) == "34.56.78.90"

    def test_ipv6_forwarded(self):
        """IPv6 address in X-Forwarded-For is extracted."""
        req = _make_request(forwarded="2001:db8::1, 2a01:cb05:8700:5900::1")
        assert _get_real_ip(req) == "2a01:cb05:8700:5900::1"

    def test_empty_forwarded_falls_back(self):
        """Empty X-Forwarded-For string → falls back to client host."""
        req = _make_request(forwarded="", client_host="10.10.10.10")
        assert _get_real_ip(req) == "10.10.10.10"

    def test_no_client_returns_unknown(self):
        """No X-Forwarded-For and no client → returns 'unknown'."""
        req = MagicMock()
        req.headers = {}
        req.client = None
        assert _get_real_ip(req) == "unknown"
