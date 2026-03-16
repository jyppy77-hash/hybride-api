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

class TestBlacklist:

    def test_claudebot_ip_blacklisted(self):
        """ClaudeBot IP 160.79.104.x is blacklisted."""
        assert is_blacklisted("160.79.104.1") is True

    def test_petalbot_ip_blacklisted(self):
        """PetalBot IP 114.119.130.x is blacklisted."""
        assert is_blacklisted("114.119.130.1") is True

    def test_claudebot_ipv6_blacklisted(self):
        """ClaudeBot IPv6 2607:6bc0::x is blacklisted."""
        assert is_blacklisted("2607:6bc0::1") is True

    def test_random_public_ip_not_blacklisted(self):
        """Random public IP is NOT blacklisted."""
        assert is_blacklisted("8.8.8.8") is False

    def test_malformed_ip_returns_false(self):
        """Malformed IP string returns False."""
        assert is_blacklisted("garbage") is False

    def test_empty_string_returns_false(self):
        """Empty string returns False."""
        assert is_blacklisted("") is False


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


# ═══════════════════════════════════════════════════════════════════════
# Admin IP restriction
# ═══════════════════════════════════════════════════════════════════════

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)


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
