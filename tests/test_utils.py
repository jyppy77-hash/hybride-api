"""
Tests for utils.py — shared IP extraction utility.
"""

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
