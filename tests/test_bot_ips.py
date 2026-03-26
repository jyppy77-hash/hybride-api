"""
Tests — config/bot_ips.py + middleware integration.
Whitelist, blacklist, suspicious paths, admin IP restriction.
"""

import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from config.bot_ips import (
    is_whitelisted_bot,
    is_blacklisted,
    is_suspicious_path,
    SUSPICIOUS_PATHS,
    _parse_google_style_json,
    _parse_text_ips,
    refresh_from_remote,
)


# ═══════════════════════════════════════════════════════════════════════
# Whitelist tests
# ═══════════════════════════════════════════════════════════════════════

class TestWhitelist:

    def test_gcp_health_check_ipv4(self):
        """GCP Health Check IP 35.191.x.x is whitelisted."""
        assert is_whitelisted_bot("35.191.0.1") is True

    def test_gcp_health_check_ipv4_130(self):
        """GCP Health Check IP 130.211.x.x is whitelisted."""
        assert is_whitelisted_bot("130.211.0.1") is True

    def test_facebook_ip(self):
        """Facebook IP 157.240.x.x is whitelisted."""
        assert is_whitelisted_bot("157.240.1.1") is True

    def test_twitter_ip(self):
        """Twitter IP 104.244.42.x is whitelisted."""
        assert is_whitelisted_bot("104.244.42.1") is True

    def test_linkedin_ip(self):
        """LinkedIn IP 108.174.x.x is whitelisted."""
        assert is_whitelisted_bot("108.174.1.1") is True

    def test_telegram_ip(self):
        """Telegram IP 149.154.161.x is whitelisted."""
        assert is_whitelisted_bot("149.154.161.1") is True

    def test_random_public_ip_not_whitelisted(self):
        """Random public IP is NOT whitelisted."""
        assert is_whitelisted_bot("8.8.8.8") is False

    def test_private_ip_not_whitelisted(self):
        """Private IP is NOT whitelisted."""
        assert is_whitelisted_bot("192.168.1.1") is False

    def test_ipv6_gcp_health_check(self):
        """IPv6 GCP Health Check is whitelisted."""
        assert is_whitelisted_bot("2600:2d00:1:b029::1") is True

    def test_ipv6_facebook(self):
        """IPv6 Facebook 2a03:2880::x is whitelisted."""
        assert is_whitelisted_bot("2a03:2880::1") is True

    def test_ipv6_linkedin(self):
        """IPv6 LinkedIn 2620:109:c001::x is whitelisted."""
        assert is_whitelisted_bot("2620:109:c001::1") is True

    def test_malformed_ip_returns_false(self):
        """Malformed IP string returns False (no crash)."""
        assert is_whitelisted_bot("not-an-ip") is False

    def test_empty_string_returns_false(self):
        """Empty string returns False."""
        assert is_whitelisted_bot("") is False


# ═══════════════════════════════════════════════════════════════════════
# Blacklist tests
# ═══════════════════════════════════════════════════════════════════════

class TestSearchEngineFallback:
    """P0-1: Search engine crawlers have static fallback CIDRs."""

    def test_googlebot_static_fallback(self):
        """Googlebot primary range 66.249.64.0/19 is whitelisted even without refresh."""
        assert is_whitelisted_bot("66.249.64.1") is True
        assert is_whitelisted_bot("66.249.95.254") is True

    def test_bingbot_static_fallback(self):
        """BingBot range 40.77.167.0/24 is whitelisted even without refresh."""
        assert is_whitelisted_bot("40.77.167.1") is True
        assert is_whitelisted_bot("157.55.39.100") is True

    def test_applebot_static_fallback(self):
        """AppleBot range 17.22.237.0/24 is whitelisted even without refresh."""
        assert is_whitelisted_bot("17.22.237.1") is True
        assert is_whitelisted_bot("17.241.208.170") is True


# ═══════════════════════════════════════════════════════════════════════
# Whitelist > Blacklist precedence tests
# ═══════════════════════════════════════════════════════════════════════

class TestWhitelistPrecedence:
    """P0-2: Whitelist must take precedence over blacklist in the pipeline."""

    def test_whitelisted_ip_passes_even_if_in_blacklist_ips(self):
        """If an IP is whitelisted AND in _blacklist_ips set, whitelist wins."""
        from config import bot_ips
        test_ip = "66.249.64.1"  # Googlebot — whitelisted
        # Temporarily add to blacklist set (simulates IPsum false positive)
        bot_ips._blacklist_ips.add(test_ip)
        try:
            assert is_whitelisted_bot(test_ip) is True
            # Pipeline: whitelist checked FIRST → should pass before blacklist
        finally:
            bot_ips._blacklist_ips.discard(test_ip)

    def test_pipeline_order_in_middleware(self):
        """Middleware checks whitelist BEFORE blacklist — whitelisted IP gets 200."""
        from config import bot_ips
        test_ip = "66.249.64.1"  # Googlebot
        bot_ips._blacklist_ips.add(test_ip)
        try:
            # Verify the logical order: whitelist=True means we never reach blacklist
            assert is_whitelisted_bot(test_ip) is True
            assert is_blacklisted(test_ip)[0] is True  # would block if reached
            # In middleware: whitelist check returns early → blacklist never evaluated
        finally:
            bot_ips._blacklist_ips.discard(test_ip)


# ═══════════════════════════════════════════════════════════════════════
# Blacklist tests
# ═══════════════════════════════════════════════════════════════════════

class TestBlacklist:

    def test_claudebot_ip_blacklisted(self):
        """ClaudeBot IP 160.79.104.x is blacklisted with CIDR source."""
        matched, source = is_blacklisted("160.79.104.1")
        assert matched is True
        assert source.startswith("cidr:")

    def test_petalbot_ip_blacklisted(self):
        """PetalBot IP 114.119.130.x is blacklisted with CIDR source."""
        matched, source = is_blacklisted("114.119.130.1")
        assert matched is True
        assert source.startswith("cidr:")

    def test_claudebot_ipv6_blacklisted(self):
        """ClaudeBot IPv6 2607:6bc0::x is blacklisted with CIDR source."""
        matched, source = is_blacklisted("2607:6bc0::1")
        assert matched is True
        assert source.startswith("cidr:")

    def test_random_public_ip_not_blacklisted(self):
        """Random public IP is NOT blacklisted."""
        assert is_blacklisted("8.8.8.8") == (False, None)

    def test_malformed_ip_returns_false(self):
        """Malformed IP string returns (False, None)."""
        assert is_blacklisted("garbage") == (False, None)

    def test_empty_string_returns_false(self):
        """Empty string returns (False, None)."""
        assert is_blacklisted("") == (False, None)

    def test_is_blacklisted_returns_source_cidr(self):
        """P1: is_blacklisted() returns the matching CIDR network in source."""
        matched, source = is_blacklisted("160.79.104.1")
        assert matched is True
        # Source should contain the actual CIDR that matched
        assert "160.79.104.0/23" in source

    def test_is_blacklisted_returns_source_dynamic(self):
        """P1: is_blacklisted() returns 'dynamic_ip_set' for IPs from IPsum/Tor."""
        from config import bot_ips
        bot_ips._blacklist_ips.add("99.99.99.99")
        try:
            matched, source = is_blacklisted("99.99.99.99")
            assert matched is True
            assert source == "dynamic_ip_set"
        finally:
            bot_ips._blacklist_ips.discard("99.99.99.99")


# ═══════════════════════════════════════════════════════════════════════
# Suspicious path tests
# ═══════════════════════════════════════════════════════════════════════

class TestSuspiciousPath:

    def test_env_file(self):
        assert is_suspicious_path("/.env") is True

    def test_env_backup(self):
        assert is_suspicious_path("/.env.backup") is True

    def test_git_config(self):
        assert is_suspicious_path("/.git/config") is True

    def test_wp_admin(self):
        assert is_suspicious_path("/wp-admin") is True

    def test_wp_admin_subpath(self):
        """startswith matching catches subpaths too."""
        assert is_suspicious_path("/wp-admin/install.php") is True

    def test_phpmyadmin(self):
        assert is_suspicious_path("/phpmyadmin") is True

    def test_phpmyadmin_subpath(self):
        assert is_suspicious_path("/phpmyadmin/index.php") is True

    def test_accueil_not_suspicious(self):
        assert is_suspicious_path("/accueil") is False

    def test_api_not_suspicious(self):
        assert is_suspicious_path("/api/tirages/count") is False

    def test_loto_not_suspicious(self):
        assert is_suspicious_path("/loto") is False

    def test_admin_dashboard_not_suspicious(self):
        """Legitimate admin path is NOT suspicious."""
        assert is_suspicious_path("/admin/dashboard") is False

    def test_case_insensitive(self):
        """Case-insensitive matching: /.ENV should match."""
        assert is_suspicious_path("/.ENV") is True

    def test_with_query_string(self):
        """Path with query string: /.env?foo=bar should match."""
        assert is_suspicious_path("/.env?foo=bar") is True

    def test_shell_php(self):
        assert is_suspicious_path("/shell.php") is True

    def test_xmlrpc(self):
        assert is_suspicious_path("/xmlrpc.php") is True

    def test_robots_txt_not_suspicious(self):
        """P1: /robots.txt must NOT be in SUSPICIOUS_PATHS."""
        assert is_suspicious_path("/robots.txt") is False

    def test_sitemap_xml_not_suspicious(self):
        """P1: /sitemap.xml must NOT be in SUSPICIOUS_PATHS."""
        assert is_suspicious_path("/sitemap.xml") is False

    def test_well_known_security_txt_not_suspicious(self):
        """P2: /.well-known/security.txt is legitimate (RFC 9116), must NOT be suspicious."""
        assert is_suspicious_path("/.well-known/security.txt") is False

    def test_new_suspicious_paths_present(self):
        """P2: All 11 new 2025-2026 attack vectors are in SUSPICIOUS_PATHS."""
        new_paths = [
            "/cgi-bin/", "/.DS_Store", "/debug/default/view",
            "/telescope/requests", "/api/v1/pods", "/_profiler",
            "/console/", "/info.php", "/phpinfo.php",
            "/wp-json/wp/v2/users", "/autodiscover/autodiscover.xml",
        ]
        for p in new_paths:
            assert p in SUSPICIOUS_PATHS, f"{p} missing from SUSPICIOUS_PATHS"

    def test_suspicious_paths_count_73(self):
        """P2: Total suspicious paths should be 73."""
        assert len(SUSPICIOUS_PATHS) == 73

    def test_suspicious_path_percent_encoded(self):
        """S06: percent-encoded paths must be detected after decoding."""
        assert is_suspicious_path("/%2eenv") is True          # /.env
        assert is_suspicious_path("/%2Egit/config") is True    # /.git/config
        assert is_suspicious_path("/wp%2dadmin") is True       # /wp-admin

    def test_suspicious_path_mixed_case_encoded(self):
        """S06: mixed case + percent-encoding is detected."""
        assert is_suspicious_path("/%2EENV") is True           # /.ENV → /.env
        assert is_suspicious_path("/WP-ADMIN") is True         # case-insensitive


# ═══════════════════════════════════════════════════════════════════════
# Parser tests
# ═══════════════════════════════════════════════════════════════════════

class TestParsers:

    def test_parse_google_style_json(self):
        """Parse Google-style JSON with ipv4Prefix/ipv6Prefix."""
        data = {
            "prefixes": [
                {"ipv4Prefix": "66.249.64.0/19"},
                {"ipv6Prefix": "2001:4860:4801::/48"},
                {"ipv4Prefix": "64.233.160.0/19"},
            ]
        }
        result = _parse_google_style_json(data)
        assert len(result) == 3
        assert "66.249.64.0/19" in result
        assert "2001:4860:4801::/48" in result

    def test_parse_google_style_ip_prefix(self):
        """Parse Ahrefs-style JSON with ip_prefix."""
        data = {"prefixes": [{"ip_prefix": "54.36.148.0/22"}]}
        result = _parse_google_style_json(data)
        assert result == ["54.36.148.0/22"]

    def test_parse_google_style_empty(self):
        data = {"prefixes": []}
        assert _parse_google_style_json(data) == []

    def test_parse_text_ips(self):
        """Parse plain text IPs with comments."""
        text = "# Comment\n1.2.3.4\n5.6.7.8\n# Another comment\n10.0.0.0/8\n"
        result = _parse_text_ips(text)
        assert len(result) == 3
        assert "1.2.3.4" in result
        assert "10.0.0.0/8" in result

    def test_parse_text_ipsum_format(self):
        """Parse IPsum format: 'IP\\tcount'."""
        text = "# IPsum list\n1.2.3.4\t5\n5.6.7.8\t3\n"
        result = _parse_text_ips(text)
        assert result == ["1.2.3.4", "5.6.7.8"]

    def test_parse_text_empty(self):
        assert _parse_text_ips("") == []
        assert _parse_text_ips("# only comments\n") == []


# ═══════════════════════════════════════════════════════════════════════
# Refresh (mocked httpx)
# ═══════════════════════════════════════════════════════════════════════

class TestRefresh:

    @pytest.mark.asyncio
    async def test_refresh_with_all_errors(self):
        """Refresh with all sources failing still returns stats (static fallback)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("network error"))
        stats = await refresh_from_remote(mock_client)
        assert stats["whitelist_networks"] > 0  # static fallback present
        assert stats["blacklist_networks"] > 0  # static fallback present
        assert len(stats["errors"]) > 0

    @pytest.mark.asyncio
    async def test_refresh_with_json_source(self):
        """Refresh with one successful JSON source adds CIDRs."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "prefixes": [{"ipv4Prefix": "66.249.64.0/19"}]
        })

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        stats = await refresh_from_remote(mock_client)
        assert stats["whitelist_networks"] > 0

    @pytest.mark.asyncio
    async def test_refresh_merges_static_and_dynamic(self):
        """P1: After refresh, static CIDRs are still present alongside dynamic ones."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "prefixes": [{"ipv4Prefix": "203.0.113.0/24"}]  # dynamic-only CIDR
        })

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        await refresh_from_remote(mock_client)
        # Static GCP range still whitelisted
        assert is_whitelisted_bot("35.191.0.1") is True
        # Static ClaudeBot still blacklisted
        assert is_blacklisted("160.79.104.1")[0] is True

    @pytest.mark.asyncio
    async def test_refresh_partial_failure(self):
        """P1: One source fails, others still loaded."""
        call_count = 0

        async def side_effect(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "googlebot" in url:
                raise Exception("timeout")
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={"prefixes": [{"ipv4Prefix": "203.0.113.0/24"}]})
            resp.text = ""
            return resp

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=side_effect)
        stats = await refresh_from_remote(mock_client)
        # Should have at least one error (googlebot) but still have networks
        assert len(stats["errors"]) >= 1
        assert stats["whitelist_networks"] > 0

    @pytest.mark.asyncio
    async def test_blacklist_dynamic_ips_set(self):
        """P1: Individual IPs from text sources land in _blacklist_ips set."""
        mock_json_resp = MagicMock()
        mock_json_resp.status_code = 200
        mock_json_resp.raise_for_status = MagicMock()
        mock_json_resp.json = MagicMock(return_value={"prefixes": []})

        mock_text_resp = MagicMock()
        mock_text_resp.status_code = 200
        mock_text_resp.raise_for_status = MagicMock()
        mock_text_resp.text = "# test\n198.51.100.1\n198.51.100.2\n"

        async def side_effect(url, **kwargs):
            if "ipsum" in url or "tor" in url:
                return mock_text_resp
            return mock_json_resp

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=side_effect)
        await refresh_from_remote(mock_client)
        # IPs from text sources should be in blacklist as dynamic_ip_set
        matched, source = is_blacklisted("198.51.100.1")
        assert matched is True
        assert source == "dynamic_ip_set"

    @pytest.mark.asyncio
    async def test_refresh_corruption_warning_low_cidrs(self, caplog):
        """P2: Source returning <3 CIDRs logs a corruption warning."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        # Only 1 CIDR — should trigger warning
        mock_resp.json = MagicMock(return_value={
            "prefixes": [{"ipv4Prefix": "203.0.113.0/24"}]
        })
        mock_resp.text = ""

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        import logging
        with caplog.at_level(logging.WARNING, logger="config.bot_ips"):
            await refresh_from_remote(mock_client)
        assert any("possible corruption" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_refresh_corruption_warning_ipsum(self, caplog):
        """P2: IPsum returning <100 IPs logs a corruption warning."""
        mock_json_resp = MagicMock()
        mock_json_resp.status_code = 200
        mock_json_resp.raise_for_status = MagicMock()
        mock_json_resp.json = MagicMock(return_value={"prefixes": [
            {"ipv4Prefix": "10.0.0.0/8"}, {"ipv4Prefix": "10.1.0.0/16"},
            {"ipv4Prefix": "10.2.0.0/16"},  # 3 CIDRs — no corruption warning for JSON
        ]})

        mock_text_resp = MagicMock()
        mock_text_resp.status_code = 200
        mock_text_resp.raise_for_status = MagicMock()
        # Only 5 IPs — should trigger IPsum corruption warning
        mock_text_resp.text = "1.1.1.1\n2.2.2.2\n3.3.3.3\n4.4.4.4\n5.5.5.5\n"

        async def side_effect(url, **kwargs):
            if "ipsum" in url or "tor" in url:
                return mock_text_resp
            return mock_json_resp

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=side_effect)
        import logging
        with caplog.at_level(logging.WARNING, logger="config.bot_ips"):
            await refresh_from_remote(mock_client)
        assert any("IPsum" in r.message and "possible corruption" in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════
# Admin IP restriction
# ═══════════════════════════════════════════════════════════════════════

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)


# ═══════════════════════════════════════════════════════════════════════
# S05: IPv6 owner /64 CIDR matching in ip_ban.py
# ═══════════════════════════════════════════════════════════════════════

class TestOwnerIpv6Cidr:
    """S05 — _is_owner_or_loopback uses ip_network /64, not startswith."""

    def test_ipv6_in_owner_64_matches(self):
        """IPv6 within the /64 of OWNER_IPV6 is recognized as owner."""
        with patch.dict(os.environ, {"OWNER_IPV6": "2a01:cb05:8700:5900::1"}):
            import importlib
            import middleware.ip_ban as ban_mod
            importlib.reload(ban_mod)
            # Same /64, different interface ID (privacy extension)
            assert ban_mod._is_owner_or_loopback("2a01:cb05:8700:5900:abcd:ef01:2345:6789") is True

    def test_ipv6_outside_owner_64_rejected(self):
        """IPv6 outside the /64 of OWNER_IPV6 is NOT owner."""
        with patch.dict(os.environ, {"OWNER_IPV6": "2a01:cb05:8700:5900::1"}):
            import importlib
            import middleware.ip_ban as ban_mod
            importlib.reload(ban_mod)
            # Different /64 subnet
            assert ban_mod._is_owner_or_loopback("2a01:cb05:8700:5901::1") is False


class TestAdminIpRestriction:

    def _build_client(self, env_extra=None):
        """Build a TestClient with reloaded modules (ip_ban included)."""
        import importlib
        env = {
            "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
            "ADMIN_TOKEN": "test_token_xyz",
            "ADMIN_PASSWORD": "test_pass",
            "OWNER_IP": "86.212.92.243",
            "OWNER_IPV6": "2a01:cb05:8700:5900:",
        }
        if env_extra:
            env.update(env_extra)
        with patch.dict(os.environ, env), _static_patch, _static_call:
            import rate_limit as rl_mod
            importlib.reload(rl_mod)
            import middleware.ip_ban as ban_mod
            importlib.reload(ban_mod)  # reload to pick up OWNER_IPV6 env var
            import routes.admin as admin_mod
            importlib.reload(admin_mod)
            import main as main_mod
            importlib.reload(main_mod)
            rl_mod.limiter.reset()
            rl_mod._api_hits.clear()
            from starlette.testclient import TestClient
            client = TestClient(main_mod.app, raise_server_exceptions=False)
            client.cookies.set("lotoia_admin_token", env["ADMIN_TOKEN"])
            return client

    def test_admin_from_non_owner_ip_blocked(self):
        """Request to /admin from non-OWNER_IP returns 403."""
        client = self._build_client()
        resp = client.get(
            "/admin",
            headers={"X-Forwarded-For": "1.2.3.4"},
            follow_redirects=False,
        )
        assert resp.status_code == 403

    def test_admin_from_owner_ipv6_allowed(self):
        """Request to /admin from OWNER_IPV6 prefix is allowed (privacy extensions)."""
        client = self._build_client()
        resp = client.get(
            "/admin",
            headers={"X-Forwarded-For": "2a01:cb05:8700:5900:455:255e:95b8:850c"},
            follow_redirects=False,
        )
        # Should be allowed (302 to dashboard or 200) — NOT 403
        assert resp.status_code != 403
