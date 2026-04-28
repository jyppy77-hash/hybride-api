"""
V131.E — Tests pour les endpoints admin /admin/api/breakers (GET liste + POST reset individuel).

Reproduit le pattern de tests/test_admin_monitoring.py (T8-T9 sur l'endpoint legacy
/admin/api/circuit-breaker/reset) : reload modules + cookie session +
TestClient. Réutilise la chaîne d'init de tests/test_admin_chatbot_monitor.py.
"""

import os
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

_TEST_TOKEN = "test_admin_token_v131e"

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "ADMIN_TOKEN": _TEST_TOKEN, "ADMIN_PASSWORD": "testpw",
})


def _get_client():
    """Reload chain identique à tests/test_admin_chatbot_monitor.py."""
    with _db_env, _static_patch, _static_call:
        import importlib
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
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _authed_client():
    client = _get_client()
    client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
    return client


@pytest.fixture(autouse=True)
def _reset_breakers():
    """V131.E — Reset les 3 breakers avant/après chaque test (isolation)."""
    from services.circuit_breaker import ALL_BREAKERS
    for b in ALL_BREAKERS.values():
        b.force_close()
    yield
    for b in ALL_BREAKERS.values():
        b.force_close()


# ═══════════════════════════════════════════════════════════════════════
# GET /admin/api/breakers
# ═══════════════════════════════════════════════════════════════════════

class TestGetBreakers:
    """V131.E — GET /admin/api/breakers"""

    def test_get_breakers_returns_3_breakers_with_state(self):
        """GET /admin/api/breakers (auth OK) → 200 + 3 entrées chat/sql/pitch
        avec les 5 champs name/state/failures/threshold/open_timeout."""
        client = _authed_client()
        r = client.get("/admin/api/breakers")
        assert r.status_code == 200
        data = r.json()
        assert "breakers" in data
        assert len(data["breakers"]) == 3
        names = {b["name"] for b in data["breakers"]}
        assert names == {"chat", "sql", "pitch"}
        for b in data["breakers"]:
            assert "state" in b
            assert "failures" in b
            assert "threshold" in b
            assert "open_timeout" in b

    def test_get_breakers_unauthorized_without_cookie(self):
        """GET /admin/api/breakers sans cookie → 401."""
        client = _get_client()  # pas de cookie
        r = client.get("/admin/api/breakers")
        assert r.status_code == 401

    def test_get_breakers_includes_threshold_and_failure_count(self):
        """GET /admin/api/breakers → asserter threshold correct par breaker
        (chat=5, sql=3, pitch=10) ET que failures est un int ≥ 0."""
        client = _authed_client()
        r = client.get("/admin/api/breakers")
        assert r.status_code == 200
        by_name = {b["name"]: b for b in r.json()["breakers"]}
        assert by_name["chat"]["threshold"] == 5
        assert by_name["sql"]["threshold"] == 3
        assert by_name["pitch"]["threshold"] == 10
        for b in by_name.values():
            assert isinstance(b["failures"], int)
            assert b["failures"] >= 0


# ═══════════════════════════════════════════════════════════════════════
# POST /admin/api/breakers/{name}/reset
# ═══════════════════════════════════════════════════════════════════════

class TestPostBreakerReset:
    """V131.E — POST /admin/api/breakers/{name}/reset"""

    def test_post_reset_breaker_sql_force_closes_it(self):
        """Mettre sql en OPEN puis reset → state=closed + previous_state=open.

        Note : `_opened_at = time.monotonic()` est requis pour que la `state`
        property maintienne OPEN (sans cela, auto-transition vers HALF_OPEN
        après _open_timeout=60s puisque _opened_at default = 0.0).
        """
        import time
        from services.circuit_breaker import gemini_breaker_sql
        gemini_breaker_sql._failure_count = 3
        gemini_breaker_sql._set_state(gemini_breaker_sql.OPEN)
        gemini_breaker_sql._opened_at = time.monotonic()
        client = _authed_client()
        r = client.post("/admin/api/breakers/sql/reset")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "sql"
        assert data["state"] == "closed"
        assert data["failures"] == 0
        assert data["previous_state"] == "open"
        assert gemini_breaker_sql.state == "closed"

    def test_post_reset_breaker_unauthorized_without_cookie(self):
        """POST sans cookie → 401."""
        client = _get_client()
        r = client.post("/admin/api/breakers/sql/reset")
        assert r.status_code == 401

    def test_post_reset_breaker_unknown_returns_404(self):
        """POST sur breaker inexistant → 404 + payload error+available."""
        client = _authed_client()
        r = client.post("/admin/api/breakers/inexistant/reset")
        assert r.status_code == 404
        data = r.json()
        assert data["error"] == "unknown_breaker"
        assert data["name"] == "inexistant"
        assert "available" in data
        assert set(data["available"]) == {"chat", "sql", "pitch"}

    def test_post_reset_breaker_idempotent(self):
        """Reset 2× successifs sur chat (déjà closed) → 2× 200, état stays closed."""
        client = _authed_client()
        r1 = client.post("/admin/api/breakers/chat/reset")
        assert r1.status_code == 200
        r2 = client.post("/admin/api/breakers/chat/reset")
        assert r2.status_code == 200
        from services.circuit_breaker import gemini_breaker_chat
        assert gemini_breaker_chat.state == "closed"

    def test_post_reset_logs_admin_audit_with_correct_action_and_name(self):
        """Asserter qu'un log [ADMIN_AUDIT] action=breaker_reset_individual name=sql est émis."""
        client = _authed_client()
        with patch("routes.admin_monitoring.logger") as mock_logger:
            r = client.post("/admin/api/breakers/sql/reset")
        assert r.status_code == 200
        # Concaténer les call_args pour matcher le pattern (logger.info accepte format args)
        calls_repr = []
        for c in mock_logger.info.call_args_list:
            args = c.args if hasattr(c, "args") else c[0]
            # Format: logger.info(fmt, *args) → reconstituer le message final
            if args:
                fmt = args[0]
                params = args[1:]
                try:
                    msg = fmt % params if params else fmt
                except (TypeError, ValueError):
                    msg = " ".join(str(a) for a in args)
                calls_repr.append(msg)
        assert any(
            "[ADMIN_AUDIT]" in m
            and "action=breaker_reset_individual" in m
            and "name=sql" in m
            for m in calls_repr
        ), f"Expected audit log not found in calls: {calls_repr}"
