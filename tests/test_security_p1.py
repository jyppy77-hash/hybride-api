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
        import routes.admin as mod
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
        """Le code source admin.py contient max_age=86400, pas 86400 * 7."""
        import routes.admin as mod
        src = open(mod.__file__, encoding="utf-8").read()
        assert "max_age=86400," in src
        assert "max_age=86400 * 7" not in src
