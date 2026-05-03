"""
V138 — Origin Auth middleware tests.
=====================================
Tests for the ORIGIN_AUTH_SECRET fail-safe middleware that protects against
Cloudflare bypass via direct *.run.app URL hits.

Coverage (12 tests, 4 classes):
- TestFailOpenMode (3) — env var vide/absente → tout passe, pas de logs [ORIGIN_AUTH]
- TestSecretEnforcement (5) — env var set → header check + case-insensitive + empty
- TestWhitelistPaths (3) — Cloud Run probes + SEO + smoke test bypass auth
- TestSecurityHardening (1) — secret jamais leak dans logs (defense-in-depth Jyppy)

V137.D Audit Security F03 P0 — fix Cloudflare bypass via direct .run.app URL.
Pattern V134 _env_bool : reload module obligatoire après monkeypatch.setenv
pour re-évaluer la constante module-level _ORIGIN_AUTH_SECRET.
"""

import logging
import os
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient


_TEST_SECRET = "test_origin_secret_64_chars_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.fixture(autouse=True)
def _reset_origin_auth_after_test():
    """V138 : Reset utils._ORIGIN_AUTH_SECRET to empty after each test.

    Prevents pollution to other test files (test_pairs etc.) via Python module
    cache. Without this, _get_client() reload sets utils._ORIGIN_AUTH_SECRET to
    a test secret, and the value persists across tests because Python caches
    modules. Other test files assume fail-open mode (no secret) by default.
    """
    yield
    # Cleanup post-test : restore fail-open mode
    import utils as utils_mod
    utils_mod._ORIGIN_AUTH_SECRET = ""
    if "ORIGIN_AUTH_SECRET" in os.environ:
        del os.environ["ORIGIN_AUTH_SECRET"]
_TEST_DB_ENV = {
    "DB_PASSWORD": "fake",
    "DB_USER": "test",
    "DB_NAME": "testdb",
    "ADMIN_TOKEN": "fake_admin_token",
    "ADMIN_PASSWORD": "fake_admin_password",
}

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)


def _get_client(secret_value=None) -> TestClient:
    """Reload utils + main with ORIGIN_AUTH_SECRET set to secret_value.

    secret_value=None  -> env var unset (mode fail-open par defaut).
    secret_value=""    -> env var set vide (equivalent unset, fail-open).
    secret_value="abc" -> env var set non-vide (mode auth strict).

    Pattern V134 : reload modules pour re-evaluer constantes module-level.
    """
    env_overrides = dict(_TEST_DB_ENV)
    if secret_value is not None:
        env_overrides["ORIGIN_AUTH_SECRET"] = secret_value
    elif "ORIGIN_AUTH_SECRET" in os.environ:
        # Clean state if test runner inherited the env var from outer scope
        del os.environ["ORIGIN_AUTH_SECRET"]

    env_patch = patch.dict(os.environ, env_overrides, clear=False)

    with env_patch, _static_patch, _static_call:
        import importlib
        # Reload utils first (lit ORIGIN_AUTH_SECRET au module-load)
        import utils as utils_mod
        importlib.reload(utils_mod)
        # Reload rate_limit + admin modules (pattern test_security_p1.py)
        import rate_limit as rl_mod
        importlib.reload(rl_mod)
        import routes.admin_helpers as admin_helpers_mod
        importlib.reload(admin_helpers_mod)
        # Reload main last (re-binds origin_auth_middleware closure)
        import main as main_mod
        importlib.reload(main_mod)
        rl_mod.limiter.reset()
        rl_mod._api_hits.clear()
        return TestClient(main_mod.app, raise_server_exceptions=False)


# =============================================================================
# TestFailOpenMode (3 tests) - env var vide ou absente -> tout passe
# =============================================================================


class TestFailOpenMode:
    """V138 - Mode fail-open : ORIGIN_AUTH_SECRET vide/absent -> middleware no-op.

    Verifie que le middleware n'impacte PAS le trafic en Phase 1 deploiement
    progressif (push code dormant avant activation Phase 3 via gcloud).
    """

    def test_no_secret_configured_allows_all(self):
        """env var absente -> GET sur path NON-whitelist passe (pas de 403).

        Utilise /accueil (page HTML SEO, hors whitelist) pour vraiment tester
        le mode fail-open et non un bypass via whitelist.
        """
        client = _get_client(secret_value=None)
        resp = client.get("/accueil")
        # Assertion : tout sauf 403 (200 OK normal, ou 500 si template patche en test)
        # Le but est de verifier que origin_auth_middleware ne BLOQUE PAS, peu
        # importe la valeur exacte (200/500 selon environnement test).
        assert resp.status_code != 403, (
            f"Mode fail-open casse : middleware a rejete avec {resp.status_code} "
            f"alors que ORIGIN_AUTH_SECRET est absente"
        )

    def test_secret_empty_string_allows_all(self):
        """ORIGIN_AUTH_SECRET="" (vide) -> equivalent absent, fail-open."""
        client = _get_client(secret_value="")
        # POST /api/track : endpoint API non-whitelist
        resp = client.post(
            "/api/track",
            json={"event": "test_event", "page": "/test"},
            headers={"content-type": "application/json"},
        )
        # /api/track retourne 204 succes, ou 5xx/422 si DB indisponible - jamais 403 en fail-open
        assert resp.status_code != 403, (
            f"Mode fail-open empty-string casse : middleware a rejete avec {resp.status_code}"
        )

    def test_no_secret_does_not_log_origin_auth_anywhere(self, caplog):
        """En mode fail-open, jamais de log [ORIGIN_AUTH] rejected (helper fail-open early)."""
        client = _get_client(secret_value=None)
        with caplog.at_level(logging.WARNING):
            for _ in range(3):
                client.get("/accueil")
                client.post("/api/track", json={"event": "x"})
        # Verifier qu'aucun log [ORIGIN_AUTH] n'apparait en mode fail-open
        for record in caplog.records:
            assert "[ORIGIN_AUTH]" not in record.getMessage(), (
                f"Log [ORIGIN_AUTH] detecte en mode fail-open : {record.getMessage()}"
            )


# =============================================================================
# TestSecretEnforcement (5 tests) - env var set -> header obligatoire
# =============================================================================


class TestSecretEnforcement:
    """V138 - Mode auth strict : ORIGIN_AUTH_SECRET set -> header X-Origin-Auth obligatoire."""

    def test_secret_configured_rejects_no_header(self):
        """env var set + requete SANS header -> 403 Forbidden + body minimal."""
        client = _get_client(secret_value=_TEST_SECRET)
        resp = client.get("/accueil")
        assert resp.status_code == 403
        assert resp.content == b"Forbidden"
        # Content-Type text/plain (pas de leak info JSON, pas d'aide attaquant)
        assert "text/plain" in resp.headers.get("content-type", "")

    def test_secret_configured_rejects_wrong_header(self):
        """env var set + header avec mauvaise valeur -> 403."""
        client = _get_client(secret_value=_TEST_SECRET)
        resp = client.get(
            "/accueil",
            headers={"X-Origin-Auth": "wrong_secret_value"},
        )
        assert resp.status_code == 403
        assert resp.content == b"Forbidden"

    def test_secret_configured_rejects_empty_header(self):
        """env var set + header vide (X-Origin-Auth: ) -> 403 (bonus Jyppy).

        Empeche le bypass via header forge vide qui pourrait passer si on
        utilisait `request.headers.get(..., None) is None` au lieu de bool check.
        """
        client = _get_client(secret_value=_TEST_SECRET)
        resp = client.get(
            "/accueil",
            headers={"X-Origin-Auth": ""},
        )
        assert resp.status_code == 403

    def test_secret_configured_accepts_correct_header(self):
        """env var set + header correct -> laisse passer (pas de 403)."""
        client = _get_client(secret_value=_TEST_SECRET)
        resp = client.get(
            "/accueil",
            headers={"X-Origin-Auth": _TEST_SECRET},
        )
        # Accepte par middleware -> atteint le handler -> 200/302/500 selon route
        # mais JAMAIS 403
        assert resp.status_code != 403

    def test_case_insensitive_header_lookup(self):
        """Header HTTP case-insensitive : x-origin-auth (lowercase) matche."""
        client = _get_client(secret_value=_TEST_SECRET)
        resp = client.get(
            "/accueil",
            headers={"x-origin-auth": _TEST_SECRET},
        )
        assert resp.status_code != 403


# =============================================================================
# TestWhitelistPaths (3 tests) - Cloud Run probes + SEO + smoke test
# =============================================================================


class TestWhitelistPaths:
    """V138 - Whitelist : paths laisses passer meme en mode auth strict.

    Cloud Run liveness/startup probes (/health) + SEO crawlers (/robots.txt)
    + Cloud Build smoke test post-deploy (/api/version).
    """

    def test_whitelist_health_bypass(self):
        """GET /health SANS header -> 200 (Cloud Run probe cloudbuild.yaml:81-82)."""
        client = _get_client(secret_value=_TEST_SECRET)
        resp = client.get("/health")
        assert resp.status_code == 200
        # Verifier que c'est bien la reponse health (et non un 403 deguise)
        assert "status" in resp.json()

    def test_whitelist_robots_bypass(self):
        """GET /robots.txt SANS header -> pas 403 (SEO crawlers + V123 AI bots Cat A)."""
        client = _get_client(secret_value=_TEST_SECRET)
        resp = client.get("/robots.txt")
        # /robots.txt servi par sitemap_router ou launcher - peut etre 200 ou 404
        # selon test setup (StaticFiles patched). L'essentiel : pas 403 du middleware.
        assert resp.status_code != 403

    def test_whitelist_api_version_bypass(self):
        """GET /api/version SANS header -> 200 (Cloud Build smoke test post-deploy)."""
        client = _get_client(secret_value=_TEST_SECRET)
        resp = client.get("/api/version")
        assert resp.status_code == 200
        assert resp.json().get("name") == "LotoIA"


# =============================================================================
# TestSecurityHardening (1 test) - secret jamais leak dans logs (bonus Jyppy)
# =============================================================================


class TestSecurityHardening:
    """V138 - Defense-in-depth : le secret n'apparait JAMAIS dans les logs.

    Bonus Jyppy : audit OWASP - un secret leak dans Cloud Logging est exfiltrable
    via console GCP par toute personne avec role Logging Viewer.
    """

    def test_logging_on_reject_does_not_leak_secret(self):
        """Sur rejet 403, le log [ORIGIN_AUTH] ne contient JAMAIS le secret reel.

        V135 lecon (MEMORY.md) : caplog ne propage pas avec handler JSON custom
        de main.py (jsonlogger.JsonFormatter sur logging.root). On patch
        directement main.logger pour capturer les call_args via mock.
        """
        secret = "super_secret_xyz_should_never_appear_in_logs_v138"
        client = _get_client(secret_value=secret)

        import main as main_mod
        with patch.object(main_mod, "logger") as mock_logger:
            # Trigger 3 rejects avec differentes formes d'attaque
            client.get("/accueil")  # no header
            client.get("/accueil", headers={"X-Origin-Auth": "wrong"})
            client.get("/accueil", headers={"X-Origin-Auth": ""})

            # Filtrer les calls [ORIGIN_AUTH] depuis warning() call_args_list
            warning_calls = mock_logger.warning.call_args_list
            origin_auth_calls = [
                call for call in warning_calls
                if call.args and "[ORIGIN_AUTH]" in str(call.args[0])
            ]

        # Sanity check : 3 rejects -> au moins 1 log WARNING attendu (sinon le
        # test ne prouve rien sur l'absence de leak).
        assert len(origin_auth_calls) >= 1, (
            f"Aucun log [ORIGIN_AUTH] genere - le test ne prouve pas l'absence "
            f"de leak. warning_calls={warning_calls}"
        )

        # Verifier qu'aucun appel ne contient le secret reel
        # Format expected : logger.warning(fmt_str, path, ip, ua)
        # call.args = (fmt_str, *positional_args)
        for call in origin_auth_calls:
            all_args_str = " ".join(str(a) for a in call.args)
            assert secret not in all_args_str, (
                f"LEAK SECRET dans log call.args : {call.args!r}"
            )
            if call.kwargs:
                all_kwargs_str = " ".join(str(v) for v in call.kwargs.values())
                assert secret not in all_kwargs_str, (
                    f"LEAK SECRET dans log call.kwargs : {call.kwargs!r}"
                )
