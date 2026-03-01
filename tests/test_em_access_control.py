"""
Tests for middleware/em_access_control.py — EM access control.
Unit tests for all utility functions + integration tests for the middleware.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from middleware.em_access_control import (
    get_client_ip,
    is_owner_ip,
    is_em_route,
    get_redirect_url,
    anonymize_ip,
    OWNER_IPV6,
)


# ═══════════════════════════════════════════════════════════════════════════════
# get_client_ip
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetClientIp:
    def _make_request(self, forwarded=None, host="10.0.0.1"):
        req = MagicMock()
        req.headers = {}
        if forwarded is not None:
            req.headers["x-forwarded-for"] = forwarded
        req.client = MagicMock()
        req.client.host = host
        return req

    def test_xff_single_ip(self):
        req = self._make_request(forwarded="203.0.113.50")
        assert get_client_ip(req) == "203.0.113.50"

    def test_xff_multiple_ips_takes_last(self):
        """Last IP is the one added by Google's trusted GFE (anti-spoofing)."""
        req = self._make_request(forwarded="203.0.113.50, 10.0.0.1, 10.0.0.2")
        assert get_client_ip(req) == "10.0.0.2"

    def test_xff_spoofed_owner_ip_takes_real(self):
        """Attacker forges owner IP in XFF; GFE appends real IP last."""
        spoofed = f"{OWNER_IPV6}, 198.51.100.99"
        req = self._make_request(forwarded=spoofed)
        assert get_client_ip(req) == "198.51.100.99"

    def test_xff_ipv6(self):
        req = self._make_request(forwarded="2a01:cb05:8700:5900:aaaa:bbbb:cccc:dddd")
        assert get_client_ip(req) == "2a01:cb05:8700:5900:aaaa:bbbb:cccc:dddd"

    def test_xff_strips_whitespace(self):
        req = self._make_request(forwarded="  203.0.113.50 , 10.0.0.1")
        assert get_client_ip(req) == "10.0.0.1"

    def test_fallback_to_client_host(self):
        req = self._make_request(forwarded=None, host="192.168.1.1")
        assert get_client_ip(req) == "192.168.1.1"

    def test_no_client(self):
        req = MagicMock()
        req.headers = {}
        req.client = None
        assert get_client_ip(req) == "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# is_owner_ip
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsOwnerIp:
    def test_exact_owner_ipv6(self):
        assert is_owner_ip(OWNER_IPV6) is True

    def test_same_64_prefix_different_suffix(self):
        """Privacy extensions: same /64, different interface ID."""
        assert is_owner_ip("2a01:cb05:8700:5900:1111:2222:3333:4444") is True

    def test_different_64_prefix(self):
        assert is_owner_ip("2a01:cb05:8700:5901:180b:4c1b:2226:7349") is False

    def test_completely_different_ipv6(self):
        assert is_owner_ip("2001:db8::1") is False

    def test_loopback_v4(self):
        assert is_owner_ip("127.0.0.1") is True

    def test_loopback_v6(self):
        assert is_owner_ip("::1") is True

    def test_random_ipv4(self):
        assert is_owner_ip("203.0.113.50") is False

    def test_invalid_ip(self):
        assert is_owner_ip("not-an-ip") is False

    def test_empty_string(self):
        assert is_owner_ip("") is False

    def test_compressed_ipv6_owner(self):
        """Compressed form of a /64 sibling must still match."""
        assert is_owner_ip("2a01:cb05:8700:5900::1") is True

    def test_expanded_ipv6_owner(self):
        expanded = "2a01:cb05:8700:5900:0000:0000:0000:0001"
        assert is_owner_ip(expanded) is True


# ═══════════════════════════════════════════════════════════════════════════════
# is_em_route
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsEmRoute:
    # ── Must block ──
    @pytest.mark.parametrize("path", [
        "/euromillions",
        "/euromillions/generateur",
        "/euromillions/statistiques",
        "/euromillions/historique",
        "/euromillions/faq",
        "/euromillions/news",
        "/euromillions/mentions-legales",
        "/en/euromillions",
        "/en/euromillions/generator",
        "/en/euromillions/statistics",
        "/es/euromillions",
        "/es/euromillions/generador",
        "/pt/euromilhoes",
        "/pt/euromilhoes/gerador",
        "/de/euromillionen",
        "/de/euromillionen/generator",
        "/nl/euromillions",
        "/nl/euromillions/generator",
        "/api/euromillions/tirages/count",
        "/api/euromillions/stats",
        "/api/euromillions/generate",
        "/api/euromillions/hybride-chat",
        "/api/euromillions/meta-pdf",
        "/static/pdf/em_report.pdf",
        "/static/pdf/em_meta75.pdf",
        # Case-insensitive bypass attempts
        "/EuroMillions",
        "/EUROMILLIONS/statistiques",
        "/En/EuroMillions",
        "/API/EUROMILLIONS/stats",
        "/PT/EuroMilhoes",
        "/Static/Pdf/EM_report.pdf",
    ])
    def test_em_routes_blocked(self, path):
        assert is_em_route(path) is True

    # ── Must NOT block ──
    @pytest.mark.parametrize("path", [
        "/",
        "/accueil",
        "/loto",
        "/loto/statistiques",
        "/loto/analyse",
        "/api/loto/stats",
        "/api/loto/tirages/count",
        "/faq",
        "/news",
        "/health",
        "/api/version",
        "/static/css/style.css",
        "/static/js/app.js",
        "/static/pdf/meta75_report.pdf",
        "/en",
        "/es",
        "/pt",
        "/de",
        "/nl",
        "/mentions-legales",
        "/sitemap.xml",
        "/historique",
    ])
    def test_non_em_routes_pass(self, path):
        assert is_em_route(path) is False


# ═══════════════════════════════════════════════════════════════════════════════
# get_redirect_url
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetRedirectUrl:
    def test_fr_root(self):
        assert get_redirect_url("/euromillions") == "/"

    def test_fr_subpage(self):
        assert get_redirect_url("/euromillions/statistiques") == "/"

    def test_en(self):
        assert get_redirect_url("/en/euromillions") == "/en"

    def test_en_subpage(self):
        assert get_redirect_url("/en/euromillions/statistics") == "/en"

    def test_es(self):
        assert get_redirect_url("/es/euromillions/generador") == "/es"

    def test_pt(self):
        assert get_redirect_url("/pt/euromilhoes") == "/pt"

    def test_de(self):
        assert get_redirect_url("/de/euromillionen/statistiken") == "/de"

    def test_nl(self):
        assert get_redirect_url("/nl/euromillions") == "/nl"

    def test_api_endpoint(self):
        assert get_redirect_url("/api/euromillions/stats") == "/"

    def test_static_pdf(self):
        assert get_redirect_url("/static/pdf/em_report.pdf") == "/"


# ═══════════════════════════════════════════════════════════════════════════════
# anonymize_ip
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnonymizeIp:
    def test_ipv4(self):
        assert anonymize_ip("203.0.113.50") == "203.0.113.xxx"

    def test_ipv6(self):
        result = anonymize_ip("2a01:cb05:8700:5900:180b:4c1b:2226:7349")
        assert result == "2a01:cb05:8700:5900:xxxx:xxxx:xxxx:xxxx"

    def test_ipv6_compressed(self):
        result = anonymize_ip("2001:db8::1")
        # exploded form: 2001:0db8:0000:0000:...
        assert result.startswith("2001:0db8:0000:0000:")
        assert result.endswith(":xxxx:xxxx:xxxx:xxxx")

    def test_invalid(self):
        assert anonymize_ip("garbage") == "invalid"

    def test_empty(self):
        assert anonymize_ip("") == "invalid"

    def test_loopback_v4(self):
        assert anonymize_ip("127.0.0.1") == "127.0.0.xxx"

    def test_loopback_v6(self):
        result = anonymize_ip("::1")
        assert ":xxxx:xxxx:xxxx:xxxx" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Full middleware integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmAccessMiddleware:
    """Integration tests for em_access_middleware."""

    @pytest.fixture
    def call_next(self):
        """Mock call_next that returns a 200 response."""
        resp = MagicMock()
        resp.status_code = 200
        return AsyncMock(return_value=resp)

    def _make_request(self, path, forwarded=None, host="203.0.113.50"):
        req = MagicMock()
        req.url = MagicMock()
        req.url.path = path
        req.headers = {}
        if forwarded:
            req.headers["x-forwarded-for"] = forwarded
        req.client = MagicMock()
        req.client.host = host
        return req

    @pytest.mark.asyncio
    async def test_non_em_route_passes(self, call_next):
        from middleware.em_access_control import em_access_middleware
        req = self._make_request("/loto/statistiques")
        resp = await em_access_middleware(req, call_next)
        assert resp.status_code == 200
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_owner_ipv6_passes(self, call_next):
        from middleware.em_access_control import em_access_middleware
        req = self._make_request(
            "/euromillions",
            forwarded=OWNER_IPV6,
        )
        resp = await em_access_middleware(req, call_next)
        assert resp.status_code == 200
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_owner_ipv6_privacy_ext_passes(self, call_next):
        from middleware.em_access_control import em_access_middleware
        req = self._make_request(
            "/en/euromillions/statistics",
            forwarded="2a01:cb05:8700:5900:dead:beef:cafe:1234",
        )
        resp = await em_access_middleware(req, call_next)
        assert resp.status_code == 200
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_stranger_blocked_redirect_fr(self, call_next):
        from middleware.em_access_control import em_access_middleware
        req = self._make_request(
            "/euromillions",
            forwarded="2001:db8::1",
        )
        resp = await em_access_middleware(req, call_next)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_stranger_blocked_redirect_en(self, call_next):
        from middleware.em_access_control import em_access_middleware
        req = self._make_request(
            "/en/euromillions",
            forwarded="203.0.113.99",
        )
        resp = await em_access_middleware(req, call_next)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/en"
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_stranger_blocked_api(self, call_next):
        from middleware.em_access_control import em_access_middleware
        req = self._make_request(
            "/api/euromillions/stats",
            forwarded="198.51.100.1",
        )
        resp = await em_access_middleware(req, call_next)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_localhost_passes(self, call_next):
        from middleware.em_access_control import em_access_middleware
        req = self._make_request(
            "/euromillions",
            host="127.0.0.1",
        )
        resp = await em_access_middleware(req, call_next)
        assert resp.status_code == 200
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_public_access_mode(self, call_next, monkeypatch):
        import middleware.em_access_control as mod
        monkeypatch.setattr(mod, "EM_PUBLIC_ACCESS", True)
        req = self._make_request(
            "/euromillions",
            forwarded="2001:db8::1",
        )
        resp = await mod.em_access_middleware(req, call_next)
        assert resp.status_code == 200
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_not_blocked(self, call_next):
        from middleware.em_access_control import em_access_middleware
        req = self._make_request(
            "/health",
            forwarded="2001:db8::1",
        )
        resp = await em_access_middleware(req, call_next)
        assert resp.status_code == 200
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_loto_api_not_blocked(self, call_next):
        from middleware.em_access_control import em_access_middleware
        req = self._make_request(
            "/api/loto/stats",
            forwarded="2001:db8::1",
        )
        resp = await em_access_middleware(req, call_next)
        assert resp.status_code == 200
        call_next.assert_called_once()
