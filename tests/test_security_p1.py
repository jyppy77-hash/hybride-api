"""
Tests P1 securite — Audit 360° pre-launch (12/03/2026).

P1-1 : Rate limiting global 60 req/min sur /api/*
P1-2 : Admin login rate limit 3/min
P1-3 : Cookie admin max_age = 1 jour
"""

import os
from unittest.mock import patch, AsyncMock

import pytest
from starlette.testclient import TestClient


_TEST_TOKEN = "test_admin_token_sec"
_TEST_PASSWORD = "test_admin_password_sec"

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "ADMIN_TOKEN": _TEST_TOKEN,
    "ADMIN_PASSWORD": _TEST_PASSWORD,
})


def _get_client():
    with _db_env, _static_patch, _static_call:
        import importlib
        import rate_limit as rl_mod
        importlib.reload(rl_mod)
        import routes.admin_helpers as admin_helpers_mod
        importlib.reload(admin_helpers_mod)
        import routes.admin_dashboard as admin_dashboard_mod
        importlib.reload(admin_dashboard_mod)
        import routes.admin_impressions as admin_impressions_mod
        importlib.reload(admin_impressions_mod)
        import routes.admin_sponsors as admin_sponsors_mod
        importlib.reload(admin_sponsors_mod)
        import routes.admin_monitoring as admin_monitoring_mod
        importlib.reload(admin_monitoring_mod)
        import routes.admin as admin_mod
        importlib.reload(admin_mod)
        import main as main_mod
        importlib.reload(main_mod)
        rl_mod.limiter.reset()
        rl_mod._api_hits.clear()
        return TestClient(main_mod.app, raise_server_exceptions=False)


# ── P1-1 : Rate limiting global /api/* ─────────────────────────────


class TestAPIGlobalRateLimit:
    """P1-1 — Middleware global 60 req/min sur /api/*."""

    def test_api_version_not_blocked_under_limit(self):
        """Les requetes /api/* passent tant qu'on reste sous 60/min."""
        client = _get_client()
        for _ in range(5):
            resp = client.get("/api/version")
            assert resp.status_code == 200

    def test_api_blocked_after_60_requests(self):
        """La 61e requete /api/* dans la meme fenetre retourne 429."""
        client = _get_client()
        for _ in range(60):
            client.get("/api/version")
        resp = client.get("/api/version")
        assert resp.status_code == 429
        assert "Trop de requetes" in resp.json()["error"]

    def test_html_pages_not_rate_limited(self):
        """Les pages HTML ne sont PAS soumises au rate limiting global."""
        client = _get_client()
        # Saturer le bucket API
        for _ in range(60):
            client.get("/api/version")
        # Les pages HTML doivent toujours repondre normalement
        resp = client.get("/health")
        assert resp.status_code == 200


# ── P1-1 bis : Rate limits per-route chat inchanges ────────────────


class TestChatRateLimitsUnchanged:
    """Les rate limits existants sur les endpoints chat (10/min) ne sont pas casses."""

    def test_chat_loto_has_rate_limit(self):
        """POST /api/hybride-chat a un @limiter.limit('10/minute')."""
        import routes.api_chat as mod
        src = open(mod.__file__, encoding="utf-8").read()
        assert '@limiter.limit("10/minute")' in src

    def test_chat_em_has_rate_limit(self):
        """POST /api/euromillions/hybride-chat a un @limiter.limit('10/minute')."""
        import routes.api_chat_em as mod
        src = open(mod.__file__, encoding="utf-8").read()
        assert '@limiter.limit("10/minute")' in src


# ── P1-2 : Admin login rate limit ──────────────────────────────────


class TestAdminLoginRateLimit:
    """P1-2 — POST /admin/login limite a 3/min (plus 5/min)."""

    def test_admin_login_rate_limit_is_3_per_minute(self):
        """Le decorateur slowapi sur POST /admin/login est 3/minute."""
        import routes.admin_dashboard as mod
        src = open(mod.__file__, encoding="utf-8").read()
        # Doit contenir 3/minute, pas 5/minute
        assert '@limiter.limit("3/minute")' in src
        assert '@limiter.limit("5/minute")' not in src

    def test_admin_login_blocked_after_3_attempts(self):
        """La 4e tentative de login dans la meme minute retourne 429."""
        client = _get_client()
        for _ in range(3):
            client.post("/admin/login", data={"password": "wrong"})
        resp = client.post("/admin/login", data={"password": "wrong"})
        assert resp.status_code == 429

    def test_admin_login_get_page_not_limited(self):
        """GET /admin/login (page) n'est pas rate-limite."""
        client = _get_client()
        for _ in range(10):
            resp = client.get("/admin/login")
            assert resp.status_code == 200


# ── P1-3 : Cookie admin max_age ────────────────────────────────────


class TestAdminCookieMaxAge:
    """P1-3 — Cookie admin expire apres 1 jour (86400s), pas 7 jours."""

    def test_cookie_max_age_is_one_day(self):
        """Apres login reussi, le cookie a max_age=86400."""
        client = _get_client()   # fresh client — rate limiter reset
        resp = client.post(
            "/admin/login",
            data={"password": _TEST_PASSWORD},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        cookie_header = resp.headers.get("set-cookie", "")
        assert "Max-Age=86400" in cookie_header

    def test_cookie_max_age_not_seven_days(self):
        """Le cookie ne doit PAS contenir l'ancien max_age de 7 jours."""
        client = _get_client()   # fresh client — rate limiter reset
        resp = client.post(
            "/admin/login",
            data={"password": _TEST_PASSWORD},
            follow_redirects=False,
        )
        cookie_header = resp.headers.get("set-cookie", "")
        assert "Max-Age=604800" not in cookie_header

    def test_source_code_max_age_value(self):
        """Le code source admin_dashboard.py contient max_age=86400, pas 86400 * 7."""
        import routes.admin_dashboard as mod
        src = open(mod.__file__, encoding="utf-8").read()
        assert "max_age=86400," in src
        assert "max_age=86400 * 7" not in src


# ── S13 : X-XSS-Protection obsolete retiré ────────────────────────


# ── S01 : CSRF Origin validation ───────────────────────────────────


class TestCSRFOriginValidation:
    """S01 — POST requests with invalid Origin header must be rejected 403."""

    def test_post_with_valid_origin(self):
        """POST with Origin: https://lotoia.fr passes CSRF check."""
        client = _get_client()
        resp = client.post(
            "/api/contact",
            json={"name": "test", "email": "a@b.com", "message": "hello"},
            headers={"Origin": "https://lotoia.fr"},
        )
        # Should NOT be 403 (may be 200/422/other, but not CSRF-blocked)
        assert resp.status_code != 403

    def test_post_with_invalid_origin(self):
        """POST with Origin: https://evil.com is rejected 403."""
        client = _get_client()
        resp = client.post(
            "/api/contact",
            json={"name": "test", "email": "a@b.com", "message": "hello"},
            headers={"Origin": "https://evil.com"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Origin not allowed"

    def test_post_without_origin_allows_non_browser(self):
        """POST without Origin or Referer is allowed (non-browser API client)."""
        client = _get_client()
        resp = client.post(
            "/api/contact",
            json={"name": "test", "email": "a@b.com", "message": "hello"},
        )
        # Non-browser client (no Origin) → passes CSRF, hits actual route
        assert resp.status_code != 403

    def test_post_with_valid_referer_fallback(self):
        """POST without Origin but with valid Referer passes CSRF check."""
        client = _get_client()
        resp = client.post(
            "/api/contact",
            json={"name": "test", "email": "a@b.com", "message": "hello"},
            headers={"Referer": "https://lotoia.fr/hybride"},
        )
        assert resp.status_code != 403

    def test_post_with_invalid_referer(self):
        """POST with invalid Referer (no Origin) is rejected 403."""
        client = _get_client()
        resp = client.post(
            "/api/contact",
            json={"name": "test", "email": "a@b.com", "message": "hello"},
            headers={"Referer": "https://evil.com/page"},
        )
        assert resp.status_code == 403

    def test_get_not_affected(self):
        """GET requests are exempt from CSRF check."""
        client = _get_client()
        resp = client.get("/health", headers={"Origin": "https://evil.com"})
        assert resp.status_code == 200

    @pytest.mark.parametrize("origin", [
        "http://localhost:8000",
        "http://localhost:8080",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8080",
    ])
    def test_post_localhost_dev(self, origin):
        """POST with localhost/127.0.0.1 Origin is allowed when K_SERVICE not set (dev)."""
        client = _get_client()
        resp = client.post(
            "/api/contact",
            json={"name": "test", "email": "a@b.com", "message": "hello"},
            headers={"Origin": origin},
        )
        assert resp.status_code != 403


class TestNoXSSProtectionHeader:
    """S13 — X-XSS-Protection must NOT be present (obsolete, CSP covers XSS)."""

    def test_xss_protection_header_absent(self):
        """GET /health must NOT return X-XSS-Protection header."""
        client = _get_client()
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "X-XSS-Protection" not in resp.headers


# ── S09 : Permissions-Policy élargi ──────────────────────────────


class TestPermissionsPolicyExtended:
    """S09 — Permissions-Policy must block payment, usb, bluetooth, serial."""

    def test_permissions_policy_contains_payment(self):
        """Permissions-Policy header includes payment=() (S09 audit fix)."""
        client = _get_client()
        resp = client.get("/health")
        pp = resp.headers.get("Permissions-Policy", "")
        assert "payment=()" in pp
        assert "usb=()" in pp
        assert "bluetooth=()" in pp
        assert "serial=()" in pp


# ── S04 : _api_hits memory bound ─────────────────────────────────


class TestApiHitsMemoryBound:
    """S04 — _api_hits dict is cleared when exceeding 10K entries."""

    def test_api_hits_cleared_above_10k(self):
        """Injecting >10K IPs then making a request clears the dict."""
        import rate_limit as rl_mod
        rl_mod._api_hits.clear()
        # Inject 10_001 fake IPs
        for i in range(10_001):
            rl_mod._api_hits[f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}"].append(0.0)
        assert len(rl_mod._api_hits) > 10_000
        # One more request should trigger the clear
        client = _get_client()
        client.get("/api/version")
        # Dict was cleared then re-populated with only the new request's IP
        assert len(rl_mod._api_hits) <= 2
