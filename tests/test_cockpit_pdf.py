"""
Tests de l'export PDF cockpit — services/cockpit_pdf_generator.py + endpoint
POST /admin/cockpit/pdf (routes/admin_cockpit.py).
===========================================================================
Fixtures INLINE (les vrais JSON de run OOS sont gitignorés). Couvre :
  - génération bytes PDF valides (%PDF) sur run complet ;
  - défensif : run sans secondaire / sans stratification → section sautée, 0 crash ;
  - histogramme strato → io.BytesIO signature PNG, AUCUN temp file disque ;
  - disclaimer ANJ de repli TOUJOURS présent dans le plan du document ;
  - framing neutre : 0 mot interdit hors des blocs 'disclaimer' ;
  - endpoint : 401 non-owner, 200 application/pdf + Content-Disposition (run
    valide), 400 (run dégradé, jamais de PDF vide).

Pattern client/auth identique à tests/test_admin_cockpit_routes.py (reload chain
+ cookie session + StaticFiles patché + env DB/admin fake).
"""

import json
import os
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from services.cockpit_pdf_generator import (
    generate_cockpit_pdf,
    _render_stratification_histogram,
    _build_blocks,
    _blocks_text,
    _ANJ_FALLBACK,
)

_TEST_TOKEN = "test_admin_token_cockpit_pdf"

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "ADMIN_TOKEN": _TEST_TOKEN, "ADMIN_PASSWORD": "testpw",
})

# Mots bannis hors disclaimer (framing ANJ strict).
_FORBIDDEN = ("performance", "prédiction", "gain", "avantage")


# ── Fixtures inline ──────────────────────────────────────────────────────────

def _full_run():
    return {
        "metadata": {
            "harness_version": "v1.0", "game": "loto", "n_tirages": 200,
            "n_grilles_per_tirage": 100, "mode": "balanced",
            "run_mode": "single_no_compare", "include_secondary": True,
            "noise_floor": True,
            "tirages_replayed_range": {"first": "2025-02-24", "last": "2026-06-03"},
            "elapsed_seconds": 103.98,
            "limitations_mvp": ["future_leak_calculer_scores_hybrides_accepted",
                                "decay_state_disabled"],
        },
        "config_actuelle": {"x": 1}, "config_test": {"x": 1},
        "results_config_actuelle": {
            "tier1": {
                "somme": {"mean": 126.85, "median": 127.0, "std": 6.28,
                          "min": 107.0, "max": 148.0, "pct_out_of_bounds": 0.0},
                "esi": {"mean": 466.07, "median": 458.0, "std": 47.56,
                        "min": 388.0, "max": 694.0, "pct_out_of_bounds": 0.0},
            },
            "tier2": {
                "feature_jsd": {"somme": 0.2986, "esi": 0.2839},
                "secondary": {
                    "feature_jsd": {"chance_in_T1": 0.036273, "chance_value": 0.007159},
                    "anj_disclaimer": (
                        "Le recouvrement avec le tirage T-1 mesure un artefact de construction "
                        "du moteur, PAS un biais du jeu ni une probabilite de gain."
                    ),
                },
                "stratification": {
                    "feature_jsd": {"stratification": 0.596738},
                    "hybride_distribution": {"1_per_zone": 1.0, "2_in_one_zone": 0.0,
                                             "3_in_one_zone": 0.0, "libre": 0.0},
                    "baseline_distribution": {"1_per_zone": 0.0473, "2_in_one_zone": 0.7127,
                                              "3_in_one_zone": 0.2188, "libre": 0.0211},
                    "real_distribution": {"1_per_zone": 0.03, "2_in_one_zone": 0.75,
                                          "3_in_one_zone": 0.185, "libre": 0.035},
                },
                "effect_tier": {"somme": "materiel_fort", "esi": "materiel_fort",
                                "chance_in_T1": "materiel_fort",
                                "chance_value": "materiel_negligeable",
                                "stratification": "materiel_fort"},
                "is_material": {"somme": True, "esi": True, "chance_in_T1": True,
                                "chance_value": True, "stratification": True},
                "noise_floor": {
                    "somme": {"noise_floor": 0.000374, "p_value": 0.000999},
                    "esi": {"noise_floor": 7.8e-05, "p_value": 0.000999},
                    "stratification": {"noise_floor": 4.8e-05, "p_value": 0.0001},
                },
            },
        },
    }


def _run_no_secondary():
    run = _full_run()
    run["metadata"]["include_secondary"] = False
    run["results_config_actuelle"]["tier2"].pop("secondary", None)
    return run


def _run_no_strat():
    run = _full_run()
    run["results_config_actuelle"]["tier2"].pop("stratification", None)
    return run


def _normalize(run):
    from services.cockpit_parser import normalize_run
    return normalize_run(run)


# ── Génération PDF (générateur isolé) ─────────────────────────────────────────

class TestGenerateCockpitPdf:

    def test_full_run_produces_valid_pdf(self):
        buf = generate_cockpit_pdf(_normalize(_full_run()))
        data = buf.getvalue()
        assert data[:4] == b"%PDF"
        assert len(data) > 1000  # un vrai document, pas un stub

    def test_run_without_secondary_no_crash(self):
        vm = _normalize(_run_no_secondary())
        assert vm["secondary"]["present"] is False
        buf = generate_cockpit_pdf(vm)
        assert buf.getvalue()[:4] == b"%PDF"

    def test_run_without_stratification_no_crash(self):
        vm = _normalize(_run_no_strat())
        assert vm["stratification"]["present"] is False
        buf = generate_cockpit_pdf(vm)
        assert buf.getvalue()[:4] == b"%PDF"

    def test_degraded_run_still_renders_minimal_pdf(self):
        # Le générateur reste défensif même si l'endpoint filtre en amont (400).
        vm = _normalize({"garbage": True})
        assert vm["error"] is not None
        buf = generate_cockpit_pdf(vm)
        assert buf.getvalue()[:4] == b"%PDF"


# ── Histogramme stratification ────────────────────────────────────────────────

class TestStratHistogram:

    def test_returns_png_bytesio(self):
        vm = _normalize(_full_run())
        buf = _render_stratification_histogram(vm["stratification"])
        data = buf.getvalue()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(data) > 1000

    def test_no_tempfile_written(self):
        # Stateless strict : aucune écriture disque (pas de NamedTemporaryFile).
        vm = _normalize(_full_run())
        with patch("tempfile.NamedTemporaryFile") as ntf:
            _render_stratification_histogram(vm["stratification"])
            ntf.assert_not_called()


# ── Contenu : disclaimer ANJ + framing neutre ─────────────────────────────────

class TestContentAndFraming:

    def test_anj_fallback_always_present(self):
        for run in (_full_run(), _run_no_secondary(), _run_no_strat()):
            blocks = _build_blocks(_normalize(run))
            texts = [t for _, t in _blocks_text(blocks)]
            assert _ANJ_FALLBACK in texts

    def test_secondary_disclaimer_present_when_secondary(self):
        blocks = _build_blocks(_normalize(_full_run()))
        disc = [t for k, t in _blocks_text(blocks) if k == "disclaimer"]
        assert any("artefact de construction" in t for t in disc)

    def test_neutral_framing_outside_disclaimers(self):
        # Les mots bannis n'apparaissent QUE dans les blocs 'disclaimer'
        # (cadre légal, employés en négation). Partout ailleurs : 0 occurrence.
        blocks = _build_blocks(_normalize(_full_run()))
        non_disc = [t.lower() for k, t in _blocks_text(blocks) if k != "disclaimer"]
        joined = " ".join(non_disc)
        for word in _FORBIDDEN:
            assert word not in joined, f"mot interdit hors disclaimer : {word!r}"

    def test_effect_tier_labels_neutralized(self):
        blocks = _build_blocks(_normalize(_full_run()))
        joined = " ".join(t for _, t in _blocks_text(blocks))
        assert "divergence de forme marquée" in joined
        # Le code interne effect_tier ne fuit pas tel quel dans une cellule.
        cells = [t for k, t in _blocks_text(blocks) if k == "table"]
        assert "materiel_fort" not in cells


# ── Endpoint POST /admin/cockpit/pdf ──────────────────────────────────────────

def _get_client():
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


def _run_bytes(run):
    return json.dumps(run).encode("utf-8")


class TestCockpitPdfEndpoint:

    def test_unauthenticated_json_401(self):
        client = _get_client()
        r = client.post("/admin/cockpit/pdf",
                        files={"file": ("run.json", _run_bytes(_full_run()), "application/json")})
        assert r.status_code == 401

    def test_valid_run_returns_pdf(self):
        client = _authed_client()
        r = client.post("/admin/cockpit/pdf",
                        files={"file": ("run.json", _run_bytes(_full_run()), "application/json")})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert "attachment" in r.headers.get("content-disposition", "")
        assert "cockpit-run.pdf" in r.headers.get("content-disposition", "")
        assert r.content[:4] == b"%PDF"

    def test_degraded_run_400_no_pdf(self):
        client = _authed_client()
        r = client.post("/admin/cockpit/pdf",
                        files={"file": ("run.json", _run_bytes({"garbage": True}), "application/json")})
        assert r.status_code == 400
        assert r.headers["content-type"].startswith("application/json")
        assert r.json()["ok"] is False

    def test_malformed_json_400(self):
        client = _authed_client()
        r = client.post("/admin/cockpit/pdf",
                        files={"file": ("bad.json", b"{not json", "application/json")})
        assert r.status_code == 400
        assert r.json()["error"] == "JSON invalide"

    def test_no_file_400(self):
        client = _authed_client()
        r = client.post("/admin/cockpit/pdf", data={"foo": "bar"})
        assert r.status_code == 400
        assert r.json()["ok"] is False

    def test_too_big_413(self):
        client = _authed_client()
        import routes.admin_cockpit as cockpit_mod
        with patch.object(cockpit_mod, "_MAX_UPLOAD_BYTES", 10):
            r = client.post("/admin/cockpit/pdf",
                            files={"file": ("run.json", _run_bytes(_full_run()), "application/json")})
        assert r.status_code == 413
        assert r.json()["ok"] is False
