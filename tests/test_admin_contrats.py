"""
Tests for S06 — Contrats CRUD in FacturIA admin.
V9: mono-annonceur exclusif (LOTOIA_EXCLU, engagement, pool, depassement).
"""

import json
import os
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

import pytest
from starlette.testclient import TestClient


_TEST_TOKEN = "test-token-contrats-123"
_TEST_PASSWORD = "test-password-contrats"

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


def _authed_client():
    client = _get_client()
    client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
    return client


class TestContratsAuth:
    """Contrats pages require authentication."""

    def test_contrats_list_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/contrats", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    def test_contrats_new_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/contrats/new", follow_redirects=False)
        assert resp.status_code == 302


class TestContratsListPage:
    """GET /admin/contrats page rendering."""

    def test_contrats_list_renders(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/contrats")
        assert resp.status_code == 200
        assert "Contrats" in resp.text
        assert "Nouveau contrat" in resp.text

    def test_contrats_list_with_data(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[{
                "id": 1, "numero": "CTR-202604-0001", "sponsor_id": 1,
                "sponsor_nom": "Test Sponsor", "type_contrat": "exclusif",
                "product_codes": "LOTOIA_EXCLU",
                "date_debut": "2026-04-01", "date_fin": "2026-06-30",
                "montant_mensuel_ht": 650.00, "statut": "actif",
                "mode_depassement": "CPC",
            }])
            resp = client.get("/admin/contrats")
        assert resp.status_code == 200
        assert "CTR-202604-0001" in resp.text
        assert "Test Sponsor" in resp.text
        assert "LOTOIA_EXCLU" in resp.text

    def test_contrats_list_shows_v9_columns(self):
        """V9: list shows Code produit and Depassement columns."""
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[{
                "id": 1, "numero": "CTR-202604-0001", "sponsor_id": 1,
                "sponsor_nom": "S", "type_contrat": "exclusif",
                "product_codes": "LOTOIA_EXCLU",
                "date_debut": "2026-04-01", "date_fin": "2026-06-30",
                "montant_mensuel_ht": 650.00, "statut": "brouillon",
                "mode_depassement": "CPM",
            }])
            resp = client.get("/admin/contrats")
        assert resp.status_code == 200
        assert "Code produit" in resp.text
        assert "Depassement" in resp.text
        assert "CPM" in resp.text


class TestContratsCreate:
    """POST /admin/contrats/new — create contrat."""

    def test_contrats_new_form_renders(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[
                {"id": 1, "nom": "Sponsor A"},
            ])
            resp = client.get("/admin/contrats/new")
        assert resp.status_code == 200
        assert "Nouveau contrat" in resp.text

    def test_new_form_has_v9_fields(self):
        """V9 form has LOTOIA_EXCLU, engagement, pool, depassement."""
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.get("/admin/contrats/new")
        body = resp.text
        assert "LOTOIA_EXCLU" in body
        assert "cf-engagement" in body
        assert "mode_depassement" in body
        assert "plafond_mensuel" in body
        assert "10 000" in body

    def test_create_contrat_success(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0})
            mock_db.async_query = AsyncMock(return_value=None)
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "Sponsor A"}])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "1",
                "type_contrat": "exclusif",
                "product_codes": "LOTOIA_EXCLU",
                "date_debut": "2026-04-01",
                "date_fin": "2026-06-30",
                "montant_mensuel_ht": "650.00",
                "engagement_mois": "3",
                "pool_impressions": "10000",
                "mode_depassement": "CPC",
                "plafond_mensuel": "",
                "conditions_particulieres": "Test conditions",
            }, follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/contrats" in resp.headers["location"]

    def test_create_contrat_6_mois_engagement(self):
        """V9: 6-month engagement stores engagement_mois=6."""
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0})
            mock_db.async_query = AsyncMock(return_value=None)
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "1",
                "product_codes": "LOTOIA_EXCLU",
                "date_debut": "2026-04-01",
                "date_fin": "2026-09-30",
                "montant_mensuel_ht": "585.00",
                "engagement_mois": "6",
                "pool_impressions": "10000",
                "mode_depassement": "CPM",
                "plafond_mensuel": "2000",
            }, follow_redirects=False)
        assert resp.status_code == 302
        # Verify INSERT was called with V9 fields
        call_args = mock_db.async_query.call_args_list[-1]
        sql = call_args[0][0]
        params = call_args[0][1]
        assert "engagement_mois" in sql
        assert "mode_depassement" in sql
        assert 6 in params  # engagement_mois
        assert "CPM" in params  # mode_depassement
        assert 2000.0 in params  # plafond_mensuel

    def test_create_contrat_missing_sponsor(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "",
                "type_contrat": "exclusif",
                "date_debut": "2026-04-01",
                "date_fin": "2026-06-30",
                "montant_mensuel_ht": "650",
            })
        assert resp.status_code == 400
        assert "obligatoire" in resp.text

    def test_create_contrat_product_codes_json_wrap(self):
        """V9: bare product code is wrapped in JSON array."""
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0})
            mock_db.async_query = AsyncMock(return_value=None)
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "1",
                "product_codes": "LOTOIA_EXCLU",
                "date_debut": "2026-04-01",
                "date_fin": "2026-06-30",
                "montant_mensuel_ht": "650",
                "engagement_mois": "3",
                "pool_impressions": "10000",
                "mode_depassement": "CPC",
            }, follow_redirects=False)
        assert resp.status_code == 302
        call_args = mock_db.async_query.call_args_list[-1]
        params = call_args[0][1]
        assert '["LOTOIA_EXCLU"]' in params

    def test_create_contrat_invalid_mode_depassement_defaults_cpc(self):
        """V9: invalid mode_depassement falls back to CPC."""
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0})
            mock_db.async_query = AsyncMock(return_value=None)
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "1",
                "product_codes": "LOTOIA_EXCLU",
                "date_debut": "2026-04-01",
                "date_fin": "2026-06-30",
                "montant_mensuel_ht": "650",
                "engagement_mois": "3",
                "mode_depassement": "HACKED",
            }, follow_redirects=False)
        assert resp.status_code == 302
        call_args = mock_db.async_query.call_args_list[-1]
        params = call_args[0][1]
        assert "CPC" in params


class TestContratsDetail:
    """GET /admin/contrats/{id} — detail view."""

    def test_contrat_detail_renders(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "id": 1, "numero": "CTR-202604-0001", "sponsor_id": 1,
                "sponsor_nom": "Sponsor X", "type_contrat": "exclusif",
                "date_debut": "2026-04-01", "date_fin": "2026-06-30",
                "montant_mensuel_ht": 650.00, "statut": "brouillon",
                "product_codes": '["LOTOIA_EXCLU"]',
                "conditions_particulieres": "Custom clause",
                "engagement_mois": 3, "pool_impressions": 10000,
                "mode_depassement": "CPC", "plafond_mensuel": None,
                "sponsor_adresse": "", "sponsor_siret": "",
            })
            resp = client.get("/admin/contrats/1")
        assert resp.status_code == 200
        assert "CTR-202604-0001" in resp.text
        assert "Sponsor X" in resp.text

    def test_contrat_detail_shows_v9_fields(self):
        """V9/V121 detail shows engagement, pool widget with consumption data."""
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "id": 1, "numero": "CTR-202604-0001", "sponsor_id": 1,
                "sponsor_nom": "S", "type_contrat": "exclusif",
                "date_debut": "2026-04-01", "date_fin": "2026-09-30",
                "montant_mensuel_ht": 585.00, "statut": "actif",
                "product_codes": "LOTOIA_EXCLU",
                "conditions_particulieres": None,
                "engagement_mois": 6, "pool_impressions": 10000,
                "mode_depassement": "CPM", "plafond_mensuel": 2000.00,
                "sponsor_adresse": "", "sponsor_siret": "",
            })
            resp = client.get("/admin/contrats/1")
        body = resp.text
        assert "6 mois" in body
        # V121: widget shows "10 000" (formatted) + mode description
        assert "10 000" in body
        assert "Facturation" in body

    def test_contrat_detail_not_found_redirects(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value=None)
            resp = client.get("/admin/contrats/999", follow_redirects=False)
        assert resp.status_code == 302


class TestContratsUpdate:
    """POST /admin/contrats/{id}/edit — update contrat."""

    def test_update_contrat_success(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/1/edit", data={
                "sponsor_id": "1",
                "type_contrat": "exclusif",
                "product_codes": "LOTOIA_EXCLU",
                "date_debut": "2026-04-01",
                "date_fin": "2026-12-31",
                "montant_mensuel_ht": "650.00",
                "engagement_mois": "3",
                "pool_impressions": "10000",
                "mode_depassement": "CPC",
            }, follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/contrats/1" in resp.headers["location"]

    def test_update_contrat_v9_fields_in_sql(self):
        """V9 update sends engagement_mois, pool, depassement, plafond to DB."""
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/1/edit", data={
                "sponsor_id": "1",
                "product_codes": "LOTOIA_EXCLU",
                "date_debut": "2026-04-01",
                "date_fin": "2026-09-30",
                "montant_mensuel_ht": "585.00",
                "engagement_mois": "6",
                "pool_impressions": "10000",
                "mode_depassement": "HYBRIDE",
                "plafond_mensuel": "3000",
            }, follow_redirects=False)
        assert resp.status_code == 302
        call_args = mock_db.async_query.call_args_list[-1]
        sql = call_args[0][0]
        params = call_args[0][1]
        assert "engagement_mois" in sql
        assert "mode_depassement" in sql
        assert "plafond_mensuel" in sql
        assert 6 in params
        assert "HYBRIDE" in params
        assert 3000.0 in params


class TestContratsStatusWorkflow:
    """POST /admin/contrats/{id}/status — status transitions."""

    @pytest.mark.parametrize("new_statut", ["brouillon", "envoye", "signe", "actif", "expire", "resilie"])
    def test_valid_status_transition(self, new_statut):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post(f"/admin/contrats/1/status", data={
                "statut": new_statut,
            }, follow_redirects=False)
        assert resp.status_code == 302
        mock_db.async_query.assert_called_once()

    def test_invalid_status_ignored(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(return_value=None)
            resp = client.post("/admin/contrats/1/status", data={
                "statut": "hacked_status",
            }, follow_redirects=False)
        assert resp.status_code == 302
        mock_db.async_query.assert_not_called()


class TestContratsPDF:
    """GET /admin/contrats/{id}/pdf — PDF generation."""

    def test_contrat_pdf_returns_pdf(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(side_effect=[
                # First call: contrat data
                {
                    "id": 1, "numero": "CTR-202604-0001", "sponsor_id": 1,
                    "sponsor_nom": "PDF Test Sponsor", "type_contrat": "exclusif",
                    "date_debut": "2026-04-01", "date_fin": "2026-06-30",
                    "montant_mensuel_ht": 650.00, "statut": "signe",
                    "product_codes": '["LOTOIA_EXCLU"]',
                    "conditions_particulieres": "Clause speciale",
                    "sponsor_adresse": "123 Rue Test", "sponsor_siret": "12345678901234",
                },
                # Second call: config entreprise
                {
                    "raison_sociale": "EmovisIA", "siret": "98765432109876",
                    "adresse": "1 Rue LotoIA", "code_postal": "75001", "ville": "Paris",
                    "email": "contact@lotoia.fr", "telephone": "", "taux_tva": 0,
                    "iban": "FR7612345", "bic": "BOUSFRPP",
                },
            ])
            resp = client.get("/admin/contrats/1/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"

    def test_contrat_pdf_not_found_redirects(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value=None)
            resp = client.get("/admin/contrats/999/pdf", follow_redirects=False)
        assert resp.status_code == 302


# TestContratsMigration removed — migration files are gitignored (local-only).


class TestContratsEditForm:
    """A20: GET /admin/contrats/{id}/edit — edit form page."""

    def test_edit_form_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/contrats/1/edit", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    def test_edit_form_renders(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "id": 1, "numero": "CTR-202604-0001", "sponsor_id": 1,
                "type_contrat": "exclusif", "product_codes": '["LOTOIA_EXCLU"]',
                "date_debut": "2026-04-01", "date_fin": "2026-06-30",
                "montant_mensuel_ht": 650.00, "statut": "brouillon",
                "conditions_particulieres": "Test clause",
                "engagement_mois": 3, "pool_impressions": 10000,
                "mode_depassement": "CPC", "plafond_mensuel": None,
            })
            mock_db.async_fetchall = AsyncMock(return_value=[
                {"id": 1, "nom": "Sponsor A"},
            ])
            resp = client.get("/admin/contrats/1/edit")
        assert resp.status_code == 200
        assert "Modifier contrat" in resp.text or "contrat" in resp.text.lower()

    def test_edit_form_not_found_redirects(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value=None)
            resp = client.get("/admin/contrats/9999/edit", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/contrats" in resp.headers["location"]


class TestContratsValidation:
    """Validation on contrat creation — missing required fields."""

    def test_create_contrat_missing_dates(self):
        """Empty dates are allowed (nullable) — route succeeds."""
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0})
            mock_db.async_query = AsyncMock()
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "1",
                "type_contrat": "exclusif",
                "date_debut": "",
                "date_fin": "",
                "montant_mensuel_ht": "650",
            }, follow_redirects=False)
        assert resp.status_code == 302


class TestContratsDateValidation:
    """S04 V93: server-side date validation on contrat create/update."""

    def test_create_invalid_date_debut_returns_400(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "1",
                "date_debut": "not-a-date",
                "date_fin": "2026-06-30",
                "montant_mensuel_ht": "650",
            })
        assert resp.status_code == 400
        assert "Date de début invalide" in resp.text

    def test_create_invalid_date_fin_returns_400(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "1",
                "date_debut": "2026-04-01",
                "date_fin": "31/06/2026",
                "montant_mensuel_ht": "650",
            })
        assert resp.status_code == 400
        assert "Date de fin invalide" in resp.text

    def test_create_date_fin_before_debut_returns_400(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "1",
                "date_debut": "2026-06-01",
                "date_fin": "2026-04-01",
                "montant_mensuel_ht": "650",
            })
        assert resp.status_code == 400
        assert "postérieure" in resp.text

    def test_create_date_fin_equals_debut_returns_400(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "1",
                "date_debut": "2026-04-01",
                "date_fin": "2026-04-01",
                "montant_mensuel_ht": "650",
            })
        assert resp.status_code == 400
        assert "postérieure" in resp.text

    def test_create_valid_dates_succeeds(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0})
            mock_db.async_query = AsyncMock()
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "1",
                "date_debut": "2026-04-01",
                "date_fin": "2026-06-30",
                "montant_mensuel_ht": "650",
                "engagement_mois": "3",
                "pool_impressions": "10000",
                "mode_depassement": "CPC",
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_update_invalid_date_debut_returns_400(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "id": 1, "sponsor_id": 1, "type_contrat": "exclusif",
                "date_debut": "2026-04-01", "date_fin": "2026-06-30",
                "montant_mensuel_ht": 650.00, "statut": "brouillon",
                "product_codes": "LOTOIA_EXCLU", "conditions_particulieres": None,
                "engagement_mois": 3, "pool_impressions": 10000,
                "mode_depassement": "CPC", "plafond_mensuel": None,
            })
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/1/edit", data={
                "sponsor_id": "1",
                "date_debut": "invalid",
                "date_fin": "2026-06-30",
                "montant_mensuel_ht": "650",
            })
        assert resp.status_code == 400
        assert "Date de début invalide" in resp.text

    def test_update_date_fin_before_debut_returns_400(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "id": 1, "sponsor_id": 1, "type_contrat": "exclusif",
                "date_debut": "2026-04-01", "date_fin": "2026-06-30",
                "montant_mensuel_ht": 650.00, "statut": "brouillon",
                "product_codes": "LOTOIA_EXCLU", "conditions_particulieres": None,
                "engagement_mois": 3, "pool_impressions": 10000,
                "mode_depassement": "CPC", "plafond_mensuel": None,
            })
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/1/edit", data={
                "sponsor_id": "1",
                "date_debut": "2026-06-01",
                "date_fin": "2026-04-01",
                "montant_mensuel_ht": "650",
            })
        assert resp.status_code == 400
        assert "postérieure" in resp.text

    def test_update_valid_dates_succeeds(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/1/edit", data={
                "sponsor_id": "1",
                "date_debut": "2026-04-01",
                "date_fin": "2026-12-31",
                "montant_mensuel_ht": "650",
                "engagement_mois": "3",
                "pool_impressions": "10000",
                "mode_depassement": "CPC",
            }, follow_redirects=False)
        assert resp.status_code == 302


class TestContratsMontantValidation:
    """S14 V93: montant_mensuel_ht must be >= 0."""

    def test_create_negative_montant_returns_400(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "1",
                "date_debut": "2026-04-01",
                "date_fin": "2026-06-30",
                "montant_mensuel_ht": "-100",
            })
        assert resp.status_code == 400
        assert "négatif" in resp.text

    def test_update_negative_montant_returns_400(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "id": 1, "sponsor_id": 1, "type_contrat": "exclusif",
                "date_debut": "2026-04-01", "date_fin": "2026-06-30",
                "montant_mensuel_ht": 650.00, "statut": "brouillon",
                "product_codes": "LOTOIA_EXCLU", "conditions_particulieres": None,
                "engagement_mois": 3, "pool_impressions": 10000,
                "mode_depassement": "CPC", "plafond_mensuel": None,
            })
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/1/edit", data={
                "sponsor_id": "1",
                "date_debut": "2026-04-01",
                "date_fin": "2026-06-30",
                "montant_mensuel_ht": "-50",
            })
        assert resp.status_code == 400
        assert "négatif" in resp.text

    def test_create_zero_montant_succeeds(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0})
            mock_db.async_query = AsyncMock()
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "S"}])
            resp = client.post("/admin/contrats/new", data={
                "sponsor_id": "1",
                "date_debut": "2026-04-01",
                "date_fin": "2026-06-30",
                "montant_mensuel_ht": "0",
                "engagement_mois": "3",
                "pool_impressions": "10000",
                "mode_depassement": "CPC",
            }, follow_redirects=False)
        assert resp.status_code == 302


class TestContratsNavbar:
    """Verify Contrats link appears in admin navbar."""

    def test_navbar_has_contrats_link(self):
        path = Path(__file__).resolve().parent.parent / "ui" / "templates" / "admin" / "_base.html"
        content = path.read_text(encoding="utf-8")
        assert "/admin/contrats" in content
        assert "Contrats" in content
