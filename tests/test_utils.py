"""
Tests for utils.py — shared IP extraction + owner IP detection.
"""

import importlib
import os
from unittest.mock import MagicMock

from utils import get_client_ip, get_client_ip_from_scope


class TestGetClientIp:

    def _make_request(self, forwarded_for=None, client_host="127.0.0.1"):
        """Create a mock FastAPI Request with optional X-Forwarded-For."""
        req = MagicMock()
        headers = {}
        if forwarded_for is not None:
            headers["x-forwarded-for"] = forwarded_for
        req.headers = headers
        req.client = MagicMock()
        req.client.host = client_host
        return req

    def test_single_ip(self):
        """Single IP in X-Forwarded-For → returns it."""
        req = self._make_request(forwarded_for="1.2.3.4")
        assert get_client_ip(req) == "1.2.3.4"

    def test_multiple_ips(self):
        """Multiple IPs → returns FIRST (client real IP on Cloud Run)."""
        req = self._make_request(forwarded_for="1.2.3.4, 10.0.0.1")
        assert get_client_ip(req) == "1.2.3.4"

    def test_multiple_ips_three(self):
        """Three IPs → still returns first."""
        req = self._make_request(forwarded_for="203.0.113.50, 10.0.0.1, 35.191.0.1")
        assert get_client_ip(req) == "203.0.113.50"

    def test_with_spaces(self):
        """IPs with extra spaces → strips correctly."""
        req = self._make_request(forwarded_for=" 1.2.3.4 , 10.0.0.1 ")
        assert get_client_ip(req) == "1.2.3.4"

    def test_no_header(self):
        """No X-Forwarded-For → fallback to request.client.host."""
        req = self._make_request(forwarded_for=None, client_host="192.168.1.1")
        assert get_client_ip(req) == "192.168.1.1"

    def test_empty_header(self):
        """Empty X-Forwarded-For → fallback to request.client.host."""
        req = self._make_request(forwarded_for="", client_host="192.168.1.1")
        assert get_client_ip(req) == "192.168.1.1"

    def test_testclient(self):
        """TestClient host → returns 'testclient' (test environment)."""
        req = self._make_request(forwarded_for=None, client_host="testclient")
        assert get_client_ip(req) == "testclient"

    def test_ipv6(self):
        """IPv6 address in X-Forwarded-For → returns it."""
        req = self._make_request(forwarded_for="2001:db8::1, 10.0.0.1")
        assert get_client_ip(req) == "2001:db8::1"

    def test_no_header_no_client_returns_empty(self):
        """S07: No X-Forwarded-For + no client → returns '' (not 'unknown')."""
        req = MagicMock()
        req.headers = {}
        req.client = None
        assert get_client_ip(req) == ""


class TestGetClientIpFromScope:

    def test_with_forwarded_for(self):
        """Scope with X-Forwarded-For → returns first IP."""
        scope = {
            "headers": [(b"x-forwarded-for", b"203.0.113.50, 10.0.0.1")],
            "client": ("127.0.0.1", 8000),
        }
        assert get_client_ip_from_scope(scope) == "203.0.113.50"

    def test_without_forwarded_for(self):
        """Scope without X-Forwarded-For → returns client tuple IP."""
        scope = {
            "headers": [],
            "client": ("192.168.1.1", 8000),
        }
        assert get_client_ip_from_scope(scope) == "192.168.1.1"

    def test_no_client(self):
        """Scope without client → returns empty string."""
        scope = {"headers": []}
        assert get_client_ip_from_scope(scope) == ""


# ═══════════════════════════════════════════════════════════════════════════════
# is_owner_ip  (V87 F04 — single source of truth in utils.py)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsOwnerIp:
    """Test owner IP detection with proper CIDR /64 matching."""

    def _reload_with_env(self, ipv4="", ipv6=""):
        """Reload utils with custom OWNER_IP / OWNER_IPV6 env vars."""
        with (
            MagicMock()  # placeholder
        ):
            pass
        env = {"OWNER_IP": ipv4, "OWNER_IPV6": ipv6}
        orig_ip = os.environ.get("OWNER_IP", "")
        orig_v6 = os.environ.get("OWNER_IPV6", "")
        os.environ["OWNER_IP"] = ipv4
        os.environ["OWNER_IPV6"] = ipv6
        try:
            import utils as utils_mod
            importlib.reload(utils_mod)
            return utils_mod.is_owner_ip
        finally:
            os.environ["OWNER_IP"] = orig_ip
            os.environ["OWNER_IPV6"] = orig_v6

    def _cleanup(self):
        import utils as utils_mod
        importlib.reload(utils_mod)

    def test_ipv4_exact_match(self):
        fn = self._reload_with_env(ipv4="86.212.92.243")
        try:
            assert fn("86.212.92.243") is True
        finally:
            self._cleanup()

    def test_ipv4_no_match(self):
        fn = self._reload_with_env(ipv4="86.212.92.243")
        try:
            assert fn("203.0.113.50") is False
        finally:
            self._cleanup()

    def test_ipv6_cidr64_match(self):
        fn = self._reload_with_env(ipv6="2a01:cb05:8700:5900:")
        try:
            assert fn("2a01:cb05:8700:5900:1111:2222:3333:4444") is True
        finally:
            self._cleanup()

    def test_ipv6_cidr64_different_prefix(self):
        fn = self._reload_with_env(ipv6="2a01:cb05:8700:5900:")
        try:
            assert fn("2a01:cb05:8700:5901:180b:4c1b:2226:7349") is False
        finally:
            self._cleanup()

    def test_ipv6_compressed_form(self):
        fn = self._reload_with_env(ipv6="2a01:cb05:8700:5900:")
        try:
            assert fn("2a01:cb05:8700:5900::1") is True
        finally:
            self._cleanup()

    def test_loopback_v4_always(self):
        fn = self._reload_with_env()
        try:
            assert fn("127.0.0.1") is True
        finally:
            self._cleanup()

    def test_loopback_v6_always(self):
        fn = self._reload_with_env()
        try:
            assert fn("::1") is True
        finally:
            self._cleanup()

    def test_invalid_ip_returns_false(self):
        fn = self._reload_with_env(ipv4="1.2.3.4")
        try:
            assert fn("not-an-ip") is False
        finally:
            self._cleanup()

    def test_empty_string_returns_false(self):
        fn = self._reload_with_env(ipv4="1.2.3.4")
        try:
            assert fn("") is False
        finally:
            self._cleanup()
