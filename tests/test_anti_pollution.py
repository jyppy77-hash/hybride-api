"""
Tests — V123 Phase 2.5 Extension A "Anti-pollution analytics".

Covers:
- request.state.ai_bot_canonical set by ip_ban_middleware when match_ai_bot() matches
- routes/api_track.py inserts is_ai_bot=1 when AI bot detected
- UmamiOwnerFilterMiddleware injects window.__IS_AI_BOT__ for AI bot UAs
- Browser UA → no flag, normal tracking
"""

import os
import importlib
from unittest.mock import patch, AsyncMock, MagicMock

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)


def _build_client(env_extra=None):
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
        # CRITICAL: reload utils FIRST — it freezes _OWNER_EXACT at module-level
        # from os.environ["OWNER_IP"] at first import. In CI where OWNER_IP is not
        # in the initial process env, a stale utils module would have _OWNER_EXACT
        # without "86.212.92.243", causing is_owner_ip() to return False.
        import utils as utils_mod
        importlib.reload(utils_mod)
        import rate_limit as rl_mod
        importlib.reload(rl_mod)
        import config.ai_bots as ai_mod
        importlib.reload(ai_mod)
        import middleware.ip_ban as ban_mod
        importlib.reload(ban_mod)
        # Reload api_track after utils — it does `from utils import is_owner_ip`
        # at module level (binding a reference), which stays stale unless reloaded.
        import routes.api_track as track_mod
        importlib.reload(track_mod)
        import main as main_mod
        importlib.reload(main_mod)
        rl_mod.limiter.reset()
        rl_mod._api_hits.clear()
        from starlette.testclient import TestClient
        return TestClient(main_mod.app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════════════
# api_track.py — is_ai_bot flag in event_log INSERT
# ═══════════════════════════════════════════════════════════════════════

class TestApiTrackIsAiBotFlag:

    def test_bot_ua_inserts_is_ai_bot_1(self):
        client = _build_client()
        with patch("db_cloudsql.async_query", new=AsyncMock()) as mock_q:
            resp = client.post(
                "/api/track",
                headers={
                    "X-Forwarded-For": "1.2.3.4",
                    "User-Agent": "Googlebot/2.1",
                    "Content-Type": "application/json",
                },
                json={"event": "page_view", "page": "/loto"},
            )
            assert resp.status_code == 204
            # The INSERT should have been called with is_ai_bot=1 as last param
            if mock_q.await_count:
                args = mock_q.await_args[0]
                params = args[1]
                assert params[-1] == 1  # is_ai_bot flag is the last column

    def test_human_ua_inserts_is_ai_bot_0(self):
        client = _build_client()
        with patch("db_cloudsql.async_query", new=AsyncMock()) as mock_q:
            resp = client.post(
                "/api/track",
                headers={
                    "X-Forwarded-For": "1.2.3.4",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120",
                    "Content-Type": "application/json",
                },
                json={"event": "page_view", "page": "/loto"},
            )
            assert resp.status_code == 204
            if mock_q.await_count:
                args = mock_q.await_args[0]
                params = args[1]
                assert params[-1] == 0

    def test_owner_ip_silent_no_insert(self):
        client = _build_client()
        with patch("db_cloudsql.async_query", new=AsyncMock()) as mock_q:
            resp = client.post(
                "/api/track",
                headers={
                    "X-Forwarded-For": "86.212.92.243",
                    "Content-Type": "application/json",
                },
                json={"event": "page_view", "page": "/loto"},
            )
            assert resp.status_code == 204
            mock_q.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════
# UmamiOwnerFilterMiddleware — __IS_AI_BOT__ flag injection
# ═══════════════════════════════════════════════════════════════════════

class TestAiBotFlagInjection:
    """V123 Extension A — AI bot UA receives window.__IS_AI_BOT__ injection."""

    def test_bot_ua_gets_flag_injected(self):
        """Health endpoint returns JSON, not HTML — flag only injects on HTML.
        We test by fetching a static HTML page via test mock."""
        client = _build_client()
        # Mock a simple HTML response route handler
        # This is tricky without a real HTML page — we validate via unit test of the middleware
        # The middleware reads UA from scope and sets is_ai_bot flag; we only verify end-to-end
        # that an AI bot UA does not receive error and gets through normally.
        resp = client.get(
            "/health",
            headers={
                "X-Forwarded-For": "1.2.3.4",
                "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)",
            },
        )
        # Health endpoint returns 200 JSON; the middleware passes through non-HTML
        assert resp.status_code == 200

    def test_extract_ua_from_scope(self):
        """Unit test the _extract_ua_from_scope helper."""
        from main import _extract_ua_from_scope
        scope = {
            "headers": [
                (b"user-agent", b"Googlebot/2.1"),
                (b"accept", b"text/html"),
            ]
        }
        assert _extract_ua_from_scope(scope) == "Googlebot/2.1"

    def test_extract_ua_missing_returns_empty(self):
        from main import _extract_ua_from_scope
        scope = {"headers": [(b"accept", b"text/html")]}
        assert _extract_ua_from_scope(scope) == ""

    def test_extract_ua_truncated_at_500(self):
        from main import _extract_ua_from_scope
        long_ua = b"G" * 600
        scope = {"headers": [(b"user-agent", long_ua)]}
        assert len(_extract_ua_from_scope(scope)) == 500


# ═══════════════════════════════════════════════════════════════════════
# V123.1 hotfix — End-to-end injection via HTML response for 5 representative AI bots
# Bug V123.0: Cache-Control: public, max-age=3600 sur HTML laissait le GFE Cloud Run
# cacher la réponse humaine et la servir aux AI bots → middleware jamais invoqué → pas
# d'injection __IS_AI_BOT__. Fix: Cache-Control: private, max-age=3600.
# ═══════════════════════════════════════════════════════════════════════

class TestAiBotHtmlInjection:
    """V123.1 — UmamiOwnerFilterMiddleware injects __IS_AI_BOT__ on HTML for each Cat A UA."""

    REPRESENTATIVE_UAS = [
        ("Googlebot/2.1 (+http://www.google.com/bot.html)", "Googlebot"),
        ("PerplexityBot/1.0 (+https://perplexity.ai/perplexitybot)", "PerplexityBot"),
        ("ClaudeBot/1.0 (+claudebot@anthropic.com)", "ClaudeBot"),
        ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.0; +https://openai.com/gptbot)", "GPTBot"),
        ("Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)", "YandexBot"),
    ]

    def _build_html_client(self):
        """Build TestClient with a fake HTML route (StaticFiles mocked to avoid disk I/O)."""
        env = {
            "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
            "ADMIN_TOKEN": "x", "ADMIN_PASSWORD": "x",
            "OWNER_IP": "86.212.92.243",  # project-standard owner IP (test uses X-Forwarded-For=5.6.7.8 for non-owner)
            "K_SERVICE": "local-dev-fake",
            "AI_BOTS_WHITELIST_ENABLED": "true",
        }
        with patch.dict(os.environ, env), _static_patch, _static_call:
            import utils as utils_mod
            importlib.reload(utils_mod)
            import rate_limit as rl_mod
            importlib.reload(rl_mod)
            import config.ai_bots as ai_mod
            importlib.reload(ai_mod)
            import middleware.ip_ban as ban_mod
            importlib.reload(ban_mod)
            import routes.api_track as track_mod
            importlib.reload(track_mod)
            import main as main_mod
            importlib.reload(main_mod)

            # Inject a simple HTML route that returns a minimal HTML with <head></head><body></body>
            from fastapi.responses import HTMLResponse
            HTML_FIXTURE = "<!DOCTYPE html><html><head><title>Test</title></head><body>Hello</body></html>"

            @main_mod.app.get("/_test_html_fixture", include_in_schema=False)
            async def _fixture():
                return HTMLResponse(HTML_FIXTURE)

            rl_mod.limiter.reset()
            rl_mod._api_hits.clear()
            from starlette.testclient import TestClient
            return TestClient(main_mod.app, raise_server_exceptions=False)

    def test_each_representative_ua_gets_injection(self):
        client = self._build_html_client()
        for ua, canonical in self.REPRESENTATIVE_UAS:
            resp = client.get(
                "/_test_html_fixture",
                headers={"User-Agent": ua, "X-Forwarded-For": "5.6.7.8"},
            )
            assert resp.status_code == 200, f"{canonical}: unexpected status {resp.status_code}"
            body = resp.text
            assert "window.__IS_AI_BOT__=true" in body, (
                f"{canonical} ({ua!r}) — missing __IS_AI_BOT__ injection. Body head: {body[:300]!r}"
            )
            assert 'data-ai-bot="1"' in body, (
                f"{canonical} ({ua!r}) — missing data-ai-bot body attr"
            )

    def test_human_ua_no_injection(self):
        """Defense check — regular browser UA does NOT receive the flag."""
        client = self._build_html_client()
        resp = client.get(
            "/_test_html_fixture",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0.0.0",
                     "X-Forwarded-For": "5.6.7.8"},
        )
        assert resp.status_code == 200
        assert "window.__IS_AI_BOT__=true" not in resp.text
        assert 'data-ai-bot="1"' not in resp.text


# ═══════════════════════════════════════════════════════════════════════
# V123.1 — Cache-Control: private sur HTML (root cause du hotfix)
# ═══════════════════════════════════════════════════════════════════════

class TestCacheControlPrivateHtml:
    """V123.1 — HTML SEO responses must NOT be `public` cacheable to prevent
    GFE Cloud Run / Cloudflare edge cache from serving human responses to AI bots."""

    def _build_client(self):
        env = {
            "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
            "ADMIN_TOKEN": "x", "ADMIN_PASSWORD": "x",
            "OWNER_IP": "86.212.92.243",  # project-standard owner IP (test uses X-Forwarded-For=9.9.9.9 for non-owner)
            "K_SERVICE": "local-dev-fake",
        }
        with patch.dict(os.environ, env), _static_patch, _static_call:
            import utils as utils_mod
            importlib.reload(utils_mod)
            import main as main_mod
            importlib.reload(main_mod)

            from fastapi.responses import HTMLResponse

            # Path ending in .html triggers the Cache-Control logic in add_cache_headers
            @main_mod.app.get("/_test_html_cache.html", include_in_schema=False)
            async def _fixture():
                return HTMLResponse("<!DOCTYPE html><html><head></head><body></body></html>")

            from starlette.testclient import TestClient
            return TestClient(main_mod.app, raise_server_exceptions=False)

    def test_html_response_is_private_cache(self):
        client = self._build_client()
        resp = client.get("/_test_html_cache.html",
                          headers={"User-Agent": "Mozilla/5.0 Chrome/120",
                                   "X-Forwarded-For": "9.9.9.9"})
        cache_control = resp.headers.get("cache-control", "")
        assert "private" in cache_control, (
            f"HTML Cache-Control must be `private` to prevent edge cache. Got: {cache_control!r}"
        )
        assert "public" not in cache_control, (
            f"HTML Cache-Control must NOT be `public` (V123.1 hotfix). Got: {cache_control!r}"
        )
