"""
Tests des routes admin du cockpit V_X.F — routes/admin_cockpit.py.
==================================================================
Pattern de tests/test_v131e_breakers_admin.py : reload chain + cookie session
+ TestClient (StaticFiles patché, env DB/admin fake). Couvre auth owner, rendu
page (valide aussi le parse Jinja du template), upload OK, JSON malformé,
fichier absent, fichier trop gros (cap patché).
"""

import json
import os
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

_TEST_TOKEN = "test_admin_token_cockpit"

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "ADMIN_TOKEN": _TEST_TOKEN, "ADMIN_PASSWORD": "testpw",
})


def _get_client():
    """Reload chain identique au pattern admin + routes.admin_cockpit."""
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
        import routes.admin_cockpit as admin_cockpit_mod
        importlib.reload(admin_cockpit_mod)
        import routes.admin as admin_mod
        importlib.reload(admin_mod)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _authed_client():
    client = _get_client()
    client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
    return client


def _valid_run_bytes():
    run = {
        "metadata": {
            "harness_version": "v1.0", "game": "loto", "n_tirages": 200,
            "n_grilles_per_tirage": 100, "mode": "balanced",
            "run_mode": "single_no_compare", "include_secondary": True,
            "noise_floor": True,
            "tirages_replayed_range": {"first": "2025-02-24", "last": "2026-06-03"},
            "elapsed_seconds": 103.98, "limitations_mvp": ["decay_state_disabled"],
        },
        "config_actuelle": {"x": 1}, "config_test": {"x": 1},
        "results_config_actuelle": {
            "tier1": {"somme": {"mean": 126.0, "median": 127.0, "std": 6.0,
                                "min": 107.0, "max": 148.0, "pct_out_of_bounds": 0.0}},
            "tier2": {
                "feature_jsd": {"somme": 0.2986, "esi": 0.2839},
                "stratification": {
                    "feature_jsd": {"stratification": 0.596738},
                    "hybride_distribution": {"1_per_zone": 1.0, "2_in_one_zone": 0.0,
                                             "3_in_one_zone": 0.0, "libre": 0.0},
                    "baseline_distribution": {"1_per_zone": 0.0473, "2_in_one_zone": 0.7127,
                                              "3_in_one_zone": 0.2188, "libre": 0.0211},
                    "real_distribution": {"1_per_zone": 0.03, "2_in_one_zone": 0.75,
                                          "3_in_one_zone": 0.185, "libre": 0.035},
                },
                "effect_tier": {"somme": "materiel_fort", "stratification": "materiel_fort"},
                "is_material": {"somme": True, "stratification": True},
                "noise_floor": {"stratification": {"noise_floor": 4.8e-05, "p_value": 0.0001}},
            },
        },
    }
    return json.dumps(run).encode("utf-8")


# ── GET /admin/cockpit ───────────────────────────────────────────────────

class TestCockpitPage:

    def test_unauthenticated_redirects(self):
        client = _get_client()
        r = client.get("/admin/cockpit", follow_redirects=False)
        assert r.status_code == 302
        assert "/admin/login" in r.headers.get("location", "")

    def test_authenticated_renders_page(self):
        client = _authed_client()
        r = client.get("/admin/cockpit")
        assert r.status_code == 200
        # Le rendu Jinja du template a réussi (parse OK) + contenu attendu
        assert "Cockpit" in r.text
        assert "cockpit-dropzone" in r.text
        assert 'name="robots"' in r.text  # noindex hérité de _base.html


# ── POST /admin/cockpit/analyze ──────────────────────────────────────────

class TestCockpitAnalyze:

    def test_unauthenticated_json_401(self):
        client = _get_client()
        r = client.post("/admin/cockpit/analyze",
                        files={"file": ("run.json", _valid_run_bytes(), "application/json")})
        assert r.status_code == 401

    def test_valid_run_ok(self):
        client = _authed_client()
        r = client.post("/admin/cockpit/analyze",
                        files={"file": ("run.json", _valid_run_bytes(), "application/json")})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["error"] is None
        assert data["meta"]["game"] == "loto"
        assert data["signature"]["present"] is True
        assert data["signature"]["rows"][0]["feature"] == "stratification"
        assert data["stratification"]["jsd"] == pytest.approx(0.596738)

    def test_malformed_json_rejected(self):
        client = _authed_client()
        r = client.post("/admin/cockpit/analyze",
                        files={"file": ("bad.json", b"{not valid json", "application/json")})
        assert r.status_code == 400
        body = r.json()
        assert body["ok"] is False
        assert body["error"] == "JSON invalide"

    def test_no_file_rejected(self):
        client = _authed_client()
        r = client.post("/admin/cockpit/analyze", data={"foo": "bar"})
        assert r.status_code == 400
        assert r.json()["ok"] is False

    def test_too_big_rejected(self):
        client = _authed_client()
        import routes.admin_cockpit as cockpit_mod
        with patch.object(cockpit_mod, "_MAX_UPLOAD_BYTES", 10):
            r = client.post("/admin/cockpit/analyze",
                            files={"file": ("run.json", _valid_run_bytes(), "application/json")})
        assert r.status_code == 413
        assert r.json()["ok"] is False
