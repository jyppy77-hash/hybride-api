"""
Tests for admin back-office routes.
Auth, login, logout, dashboard, impressions, votes, API endpoints.
Exports (CSV/PDF), Sponsors CRUD, Factures CRUD, Config.
"""

import json
import os
from unittest.mock import patch, AsyncMock

import pytest
from starlette.testclient import TestClient


_TEST_TOKEN = "test_admin_token_1234567890"
_TEST_PASSWORD = "test_admin_password"

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
        import routes.admin as admin_mod
        importlib.reload(admin_mod)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _authed_client():
    client = _get_client()
    client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
    return client


class TestAdminAuth:
    """Authentication tests."""

    def test_dashboard_redirects_to_login_without_cookie(self):
        client = _get_client()
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    def test_login_page_renders(self):
        client = _get_client()
        resp = client.get("/admin/login")
        assert resp.status_code == 200
        assert "Mot de passe" in resp.text

    def test_login_wrong_password(self):
        client = _get_client()
        resp = client.post("/admin/login", data={"password": "wrong"})
        assert resp.status_code == 401
        assert "incorrect" in resp.text

    def test_login_correct_password_sets_cookie(self):
        client = _get_client()
        resp = client.post(
            "/admin/login",
            data={"password": _TEST_PASSWORD},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin" in resp.headers["location"]
        assert "lotoia_admin_token" in resp.headers.get("set-cookie", "")

    def test_dashboard_accessible_with_valid_cookie(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0, "review_count": 0, "avg_rating": 0})
            resp = client.get("/admin")
        assert resp.status_code == 200
        assert "LotoIA Admin" in resp.text

    def test_dashboard_rejects_invalid_cookie(self):
        client = _get_client()
        client.cookies.set("lotoia_admin_token", "bad_token")
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code == 302

    def test_logout_clears_cookie(self):
        client = _get_client()
        resp = client.get("/admin/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]
        set_cookie = resp.headers.get("set-cookie", "")
        assert "lotoia_admin_token" in set_cookie

    def test_login_page_redirects_if_already_authed(self):
        client = _authed_client()
        resp = client.get("/admin/login", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin" in resp.headers["location"]


class TestAdminDashboard:
    """Dashboard KPI display tests."""

    def test_dashboard_shows_kpi_values(self):
        client = _authed_client()

        async def mock_fetchall(sql, params=None):
            if "sponsor_impressions" in sql:
                return [
                    {"event_type": "sponsor-popup-shown", "cnt": 42},
                    {"event_type": "sponsor-click", "cnt": 7},
                    {"event_type": "sponsor-video-played", "cnt": 3},
                    {"event_type": "sponsor-inline-shown", "cnt": 5},
                    {"event_type": "sponsor-result-shown", "cnt": 2},
                    {"event_type": "sponsor-pdf-downloaded", "cnt": 1},
                ]
            return []

        async def mock_fetchone(sql, params=None):
            if "ratings" in sql:
                return {"review_count": 10, "avg_rating": 4.5}
            return None

        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=mock_fetchall)
            mock_db.async_fetchone = AsyncMock(side_effect=mock_fetchone)
            resp = client.get("/admin")

        assert resp.status_code == 200
        assert "42" in resp.text
        assert "4.5" in resp.text
        assert "10" in resp.text

    def test_dashboard_handles_db_error(self):
        client = _authed_client()

        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=Exception("DB down"))
            mock_db.async_fetchone = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin")

        assert resp.status_code == 200
        assert "0" in resp.text

    def test_dashboard_has_active_nav_links(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0, "review_count": 0, "avg_rating": 0})
            resp = client.get("/admin")
        assert '/admin/impressions' in resp.text
        assert '/admin/votes' in resp.text
        assert '/admin/sponsors' in resp.text
        assert '/admin/factures' in resp.text
        assert '/admin/tarifs' in resp.text
        assert '/admin/config' in resp.text


class TestAdminPages:
    """Impressions and votes page tests."""

    def test_impressions_page_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/impressions", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    def test_impressions_page_renders(self):
        client = _authed_client()
        resp = client.get("/admin/impressions")
        assert resp.status_code == 200
        assert "Impressions" in resp.text
        assert "chart" in resp.text.lower() or "canvas" in resp.text.lower()

    def test_votes_page_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/votes", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    def test_votes_page_renders(self):
        client = _authed_client()
        resp = client.get("/admin/votes")
        assert resp.status_code == 200
        assert "Votes" in resp.text


class TestAdminAPIImpressions:
    """API /admin/api/impressions tests."""

    def test_api_impressions_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/impressions")
        assert resp.status_code == 401

    def test_api_impressions_returns_json(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(return_value={"s": 0})
            resp = client.get("/admin/api/impressions?period=7d")

        assert resp.status_code == 200
        data = resp.json()
        assert "kpi" in data
        assert "chart" in data
        assert "table" in data
        assert "impressions" in data["kpi"]
        assert "ctr" in data["kpi"]

    def test_api_impressions_with_filters(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(return_value={"s": 0})
            resp = client.get("/admin/api/impressions?period=today&event_type=sponsor-click&lang=fr&device=mobile")

        assert resp.status_code == 200
        data = resp.json()
        assert data["kpi"]["impressions"] == 0

    def test_api_impressions_custom_period(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(return_value={"s": 0})
            resp = client.get("/admin/api/impressions?period=custom&date_start=2026-03-01&date_end=2026-03-05")

        assert resp.status_code == 200

    def test_api_impressions_invalid_filter_ignored(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(return_value={"s": 0})
            resp = client.get("/admin/api/impressions?event_type=hacked&lang=xx&device=hacked")

        assert resp.status_code == 200

    def test_api_impressions_db_error(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=Exception("DB down"))
            mock_db.async_fetchone = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin/api/impressions?period=7d")

        assert resp.status_code == 200
        data = resp.json()
        assert data["kpi"]["impressions"] == 0
        assert data["chart"] == []
        assert data["table"] == []


class TestAdminAPIVotes:
    """API /admin/api/votes tests."""

    def test_api_votes_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/votes")
        assert resp.status_code == 401

    def test_api_votes_returns_json(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"total": 5, "avg_rating": 4.2})
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/votes?period=all")

        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "distribution" in data
        assert "table" in data
        assert len(data["distribution"]) == 5

    def test_api_votes_with_source_filter(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"total": 2, "avg_rating": 5.0})
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/votes?source=chatbot_loto")

        assert resp.status_code == 200

    def test_api_votes_with_rating_filter(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"total": 1, "avg_rating": 5.0})
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/votes?rating=5")

        assert resp.status_code == 200

    def test_api_votes_invalid_source_ignored(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"total": 0, "avg_rating": 0})
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/votes?source=hacked")

        assert resp.status_code == 200

    def test_api_votes_db_error(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(side_effect=Exception("DB down"))
            mock_db.async_fetchall = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin/api/votes?period=all")

        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total"] == 0
        assert data["table"] == []


class TestPeriodHelper:
    """Test _period_to_dates helper."""

    def test_today(self):
        from routes.admin import _period_to_dates
        from datetime import date, timedelta
        ds, de = _period_to_dates("today")
        assert ds == date.today()
        assert de == date.today() + timedelta(days=1)

    def test_7d(self):
        from routes.admin import _period_to_dates
        from datetime import date, timedelta
        ds, de = _period_to_dates("7d")
        assert ds == date.today() - timedelta(days=6)

    def test_custom_valid(self):
        from routes.admin import _period_to_dates
        from datetime import date, timedelta
        ds, de = _period_to_dates("custom", "2026-01-01", "2026-01-31")
        assert ds == date(2026, 1, 1)
        assert de == date(2026, 2, 1)

    def test_custom_invalid_falls_back(self):
        from routes.admin import _period_to_dates
        from datetime import date
        ds, de = _period_to_dates("custom", "bad", "bad")
        assert ds == date.today()

    def test_all(self):
        from routes.admin import _period_to_dates
        from datetime import date
        ds, de = _period_to_dates("all")
        assert ds == date(2020, 1, 1)


# ══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ══════════════════════════════════════════════════════════════════════════════

class TestExportCSV:
    """CSV export tests."""

    def test_csv_impressions_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/impressions/csv")
        assert resp.status_code == 401

    def test_csv_impressions_returns_csv(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[
                {"day": "2026-03-01", "sponsor_id": "EM_FR_A", "event_type": "sponsor-popup-shown", "page": "/",
                 "lang": "fr", "device": "mobile", "country": "FR", "cnt": 5}
            ])
            resp = client.get("/admin/api/impressions/csv?period=7d")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "date,sponsor_id,event_type" in resp.text
        assert "EM_FR_A" in resp.text
        assert "sponsor-popup-shown" in resp.text

    def test_csv_votes_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/votes/csv")
        assert resp.status_code == 401

    def test_csv_votes_returns_csv(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[
                {"created_at": "2026-03-01 10:00:00", "source": "chatbot_loto",
                 "rating": 5, "comment": "Super", "page": "/"}
            ])
            resp = client.get("/admin/api/votes/csv?period=all")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "date,source,rating" in resp.text

    def test_csv_impressions_db_error_returns_empty(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin/api/impressions/csv?period=7d")

        assert resp.status_code == 200
        assert "date,sponsor_id,event_type" in resp.text


class TestExportPDF:
    """PDF sponsor report export tests."""

    def test_pdf_report_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/sponsor-report/pdf")
        assert resp.status_code == 401

    def test_pdf_report_returns_pdf(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(return_value={"s": 0})
            resp = client.get("/admin/api/sponsor-report/pdf?period=7d")

        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/pdf"
        assert resp.content[:4] == b"%PDF"


# ══════════════════════════════════════════════════════════════════════════════
# SPONSORS CRUD
# ══════════════════════════════════════════════════════════════════════════════

class TestSponsors:
    """Sponsors CRUD tests."""

    def test_sponsors_list_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/sponsors", follow_redirects=False)
        assert resp.status_code == 302

    def test_sponsors_list_renders(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/sponsors")
        assert resp.status_code == 200
        assert "Sponsors" in resp.text

    def test_sponsor_new_form_renders(self):
        client = _authed_client()
        resp = client.get("/admin/sponsors/new")
        assert resp.status_code == 200
        assert "Nouveau" in resp.text

    def test_sponsor_create_missing_name(self):
        client = _authed_client()
        resp = client.post("/admin/sponsors/new", data={"nom": ""})
        assert resp.status_code == 400
        assert "obligatoire" in resp.text

    def test_sponsor_create_success(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            mock_db.async_fetchone = AsyncMock(return_value={"id": 1})
            resp = client.post("/admin/sponsors/new", data={
                "nom": "TestSponsor",
                "contact_nom": "Jean",
                "contact_email": "j@test.fr",
                "actif": "1",
            }, follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/sponsors" in resp.headers["location"]

    def test_sponsor_edit_form_renders(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "id": 1, "nom": "Test", "contact_nom": "", "contact_email": "",
                "contact_tel": "", "adresse": "", "siret": "", "notes": "", "actif": 1,
            })
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/sponsors/1/edit")
        assert resp.status_code == 200
        assert "Editer" in resp.text

    def test_sponsor_edit_not_found_redirects(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value=None)
            resp = client.get("/admin/sponsors/999/edit", follow_redirects=False)
        assert resp.status_code == 302

    def test_sponsor_update_success(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.post("/admin/sponsors/1/edit", data={
                "nom": "Updated",
                "actif": "1",
            }, follow_redirects=False)
        assert resp.status_code == 302


# ══════════════════════════════════════════════════════════════════════════════
# FACTURES CRUD
# ══════════════════════════════════════════════════════════════════════════════

class TestFactures:
    """Factures CRUD tests."""

    def test_factures_list_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/factures", follow_redirects=False)
        assert resp.status_code == 302

    def test_factures_list_renders(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/factures")
        assert resp.status_code == 200
        assert "Factures" in resp.text

    def test_facture_new_form_renders(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[{"id": 1, "nom": "Sponsor1"}])
            resp = client.get("/admin/factures/new")
        assert resp.status_code == 200
        assert "Generer" in resp.text

    def test_facture_create_missing_fields(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.post("/admin/factures/new", data={"sponsor_id": "", "periode_debut": "", "periode_fin": ""})
        assert resp.status_code == 400

    def test_facture_create_success(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=[
                [{"id": 1, "nom": "S1"}],  # sponsors list
                [{"id": 1, "event_type": "sponsor-popup-shown", "prix_unitaire": 0.01, "description": "Impression"}],  # grille
            ])
            mock_db.async_fetchone = AsyncMock(side_effect=[
                {"cnt": 100},  # count events
                {"taux_tva": 20},  # config
                {"cnt": 0},  # invoice count
            ])
            mock_db.async_query = AsyncMock()
            resp = client.post("/admin/factures/new", data={
                "sponsor_id": "1",
                "periode_debut": "2026-02-01",
                "periode_fin": "2026-02-28",
            }, follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/factures" in resp.headers["location"]

    def test_facture_detail_renders(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "id": 1, "numero": "FIA-202603-0001", "sponsor_id": 1,
                "sponsor_nom": "TestSponsor", "date_emission": "2026-03-01",
                "date_echeance": "2026-03-31", "periode_debut": "2026-02-01",
                "periode_fin": "2026-02-28", "montant_ht": 1.0, "montant_tva": 0.2,
                "montant_ttc": 1.2, "statut": "brouillon", "notes": "",
                "lignes": json.dumps([{"description": "Impressions", "quantite": 100, "prix_unitaire": 0.01, "total_ht": 1.0}]),
            })
            resp = client.get("/admin/factures/1")
        assert resp.status_code == 200
        assert "FIA-202603-0001" in resp.text

    def test_facture_detail_not_found(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value=None)
            resp = client.get("/admin/factures/999", follow_redirects=False)
        assert resp.status_code == 302

    def test_facture_status_update(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            resp = client.post("/admin/factures/1/status", data={"statut": "envoyee"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_facture_status_invalid_ignored(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            resp = client.post("/admin/factures/1/status", data={"statut": "hacked"}, follow_redirects=False)
        assert resp.status_code == 302
        mock_db.async_query.assert_not_called()

    def test_facture_pdf_download(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(side_effect=[
                {  # facture
                    "id": 1, "numero": "FIA-202603-0001", "sponsor_id": 1,
                    "sponsor_nom": "Test", "sponsor_adresse": "1 rue test",
                    "date_emission": "2026-03-01", "date_echeance": "2026-03-31",
                    "periode_debut": "2026-02-01", "periode_fin": "2026-02-28",
                    "montant_ht": 1.0, "montant_tva": 0.2, "montant_ttc": 1.2,
                    "statut": "brouillon", "notes": "",
                    "lignes": json.dumps([{"description": "Impressions", "quantite": 100, "prix_unitaire": 0.01, "total_ht": 1.0}]),
                },
                {  # config
                    "raison_sociale": "LotoIA", "siret": "123", "adresse": "Paris",
                    "code_postal": "75000", "ville": "Paris", "pays": "France",
                    "email": "a@b.fr", "telephone": "", "tva_intra": "",
                    "taux_tva": 20, "iban": "", "bic": "", "logo_url": "",
                },
            ])
            resp = client.get("/admin/factures/1/pdf")
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/pdf"
        assert resp.content[:4] == b"%PDF"


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

class TestConfig:
    """Enterprise config tests."""

    def test_config_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/config", follow_redirects=False)
        assert resp.status_code == 302

    def test_config_page_renders(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "raison_sociale": "LotoIA", "siret": "", "adresse": "",
                "code_postal": "", "ville": "", "pays": "France",
                "email": "", "telephone": "", "tva_intra": "",
                "taux_tva": 20, "iban": "", "bic": "", "logo_url": "",
            })
            resp = client.get("/admin/config")
        assert resp.status_code == 200
        assert "Configuration" in resp.text

    def test_config_save(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            mock_db.async_fetchone = AsyncMock(return_value={
                "raison_sociale": "Updated", "siret": "123",
                "adresse": "", "code_postal": "", "ville": "",
                "pays": "France", "email": "", "telephone": "",
                "tva_intra": "", "taux_tva": 20, "iban": "", "bic": "", "logo_url": "",
            })
            resp = client.post("/admin/config", data={
                "raison_sociale": "Updated",
                "siret": "123",
                "taux_tva": "20",
            })
        assert resp.status_code == 200
        assert "enregistree" in resp.text


# ══════════════════════════════════════════════════════════════════════════════
# REALTIME
# ══════════════════════════════════════════════════════════════════════════════

class TestRealtime:
    """Realtime feed page tests."""

    def test_realtime_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/realtime", follow_redirects=False)
        assert resp.status_code == 302

    def test_realtime_page_renders(self):
        client = _authed_client()
        resp = client.get("/admin/realtime")
        assert resp.status_code == 200
        assert "Realtime Feed" in resp.text

    def test_realtime_api_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/realtime")
        assert resp.status_code == 401

    def test_realtime_api_returns_json(self):
        client = _authed_client()
        from datetime import datetime
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=[
                [{"event_type": "chatbot-open", "page": "/loto", "module": "loto",
                  "lang": "fr", "device": "desktop", "country": "FR",
                  "created_at": datetime(2026, 3, 5, 14, 30, 0)}],
                [{"event_type": "chatbot-open"}, {"event_type": "rating-submitted"}],
            ])
            mock_db.async_fetchone = AsyncMock(return_value={
                "today_count": 42, "hour_count": 5, "type_count": 3,
            })
            resp = client.get("/admin/api/realtime")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "kpi" in data
        assert data["kpi"]["today"] == 42
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "chatbot-open"

    def test_nav_contains_realtime_link(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0, "review_count": 0, "avg_rating": 0})
            resp = client.get("/admin")
        assert "/admin/realtime" in resp.text


# ══════════════════════════════════════════════════════════════════════════════
# TARIFS
# ══════════════════════════════════════════════════════════════════════════════

class TestTarifs:
    """Tarifs page and API tests."""

    _SAMPLE_TARIFS = [
        {"code": "LOTO_FR_A", "langue": "fr", "pays": "France", "tier": "premium",
         "tarif_mensuel": 349.00, "engagement_min_mois": 6, "reduction_6m": 10.00,
         "reduction_12m": 20.00, "emplacements": "E1-E5", "requires_sasu": 0, "active": 1},
        {"code": "EM_EN_A", "langue": "en", "pays": "UK,IE", "tier": "premium",
         "tarif_mensuel": 349.00, "engagement_min_mois": 6, "reduction_6m": 10.00,
         "reduction_12m": 20.00, "emplacements": "E1-E5", "requires_sasu": 1, "active": 1},
    ]

    _SAMPLE_CONFIG = [
        {"config_key": "billing_mode", "config_value": "EI"},
        {"config_key": "ei_raison_sociale", "config_value": "EmovisIA"},
        {"config_key": "ei_siret", "config_value": "123"},
        {"config_key": "sasu_raison_sociale", "config_value": "LotoIA SASU"},
        {"config_key": "sasu_siret", "config_value": ""},
    ]

    def test_tarifs_page_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/tarifs", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    def test_tarifs_page_renders(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=[
                self._SAMPLE_CONFIG,   # admin_config
                self._SAMPLE_TARIFS,   # sponsor_tarifs
            ])
            resp = client.get("/admin/tarifs")
        assert resp.status_code == 200
        assert "Grille tarifaire" in resp.text
        assert "LOTO_FR_A" in resp.text
        assert "EmovisIA" in resp.text

    def test_tarifs_page_shows_locked_in_ei_mode(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=[
                self._SAMPLE_CONFIG,
                self._SAMPLE_TARIFS,
            ])
            resp = client.get("/admin/tarifs")
        assert resp.status_code == 200
        assert "SASU" in resp.text  # badge-lock SASU on EN codes
        assert "tarif-card-locked" in resp.text

    def test_tarifs_page_sasu_mode(self):
        client = _authed_client()
        sasu_config = [{"config_key": "billing_mode", "config_value": "SASU"}] + self._SAMPLE_CONFIG[1:]
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=[
                sasu_config,
                self._SAMPLE_TARIFS,
            ])
            resp = client.get("/admin/tarifs")
        assert resp.status_code == 200
        assert "tarif-card-locked" not in resp.text

    def test_tarifs_page_db_error(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin/tarifs")
        assert resp.status_code == 200
        assert "Grille tarifaire" in resp.text

    def test_api_tarifs_mode_requires_auth(self):
        client = _get_client()
        resp = client.post("/admin/api/tarifs/mode", json={"mode": "SASU"})
        assert resp.status_code == 401

    def test_api_tarifs_mode_switch_to_sasu(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            resp = client.post("/admin/api/tarifs/mode", json={"mode": "SASU"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["mode"] == "SASU"

    def test_api_tarifs_mode_switch_to_ei(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            resp = client.post("/admin/api/tarifs/mode", json={"mode": "EI"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_api_tarifs_mode_invalid(self):
        client = _authed_client()
        resp = client.post("/admin/api/tarifs/mode", json={"mode": "INVALID"})
        assert resp.status_code == 400

    def test_api_tarifs_mode_db_error(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(side_effect=Exception("DB down"))
            resp = client.post("/admin/api/tarifs/mode", json={"mode": "SASU"})
        assert resp.status_code == 500

    def test_api_tarifs_update_requires_auth(self):
        client = _get_client()
        resp = client.put("/admin/api/tarifs/LOTO_FR_A", json={"tarif_mensuel": 399})
        assert resp.status_code == 401

    def test_api_tarifs_update_success(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            resp = client.put("/admin/api/tarifs/LOTO_FR_A", json={
                "tarif_mensuel": 399.00,
                "engagement_min_mois": 6,
                "reduction_6m": 10,
                "reduction_12m": 20,
                "active": 1,
            })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["code"] == "LOTO_FR_A"

    def test_api_tarifs_update_invalid_code(self):
        client = _authed_client()
        resp = client.put("/admin/api/tarifs/HACKED", json={"tarif_mensuel": 100})
        assert resp.status_code == 400

    def test_api_tarifs_update_negative_tarif(self):
        client = _authed_client()
        resp = client.put("/admin/api/tarifs/LOTO_FR_A", json={
            "tarif_mensuel": -10, "engagement_min_mois": 3, "reduction_6m": 10, "reduction_12m": 20, "active": 1,
        })
        assert resp.status_code == 400

    def test_api_tarifs_update_db_error(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock(side_effect=Exception("DB down"))
            resp = client.put("/admin/api/tarifs/EM_FR_A", json={
                "tarif_mensuel": 349, "engagement_min_mois": 6, "reduction_6m": 10, "reduction_12m": 20, "active": 1,
            })
        assert resp.status_code == 500

    def test_api_tarifs_data_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/tarifs")
        assert resp.status_code == 401

    def test_api_tarifs_data_returns_json(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=[
                self._SAMPLE_CONFIG,
                self._SAMPLE_TARIFS,
            ])
            resp = client.get("/admin/api/tarifs")
        assert resp.status_code == 200
        data = resp.json()
        assert "billing_mode" in data
        assert "tarifs" in data
        assert "packs" in data
        assert "paliers" in data
        assert data["billing_mode"] == "EI"
        assert len(data["tarifs"]) == 2

    def test_api_tarifs_data_db_error(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin/api/tarifs")
        assert resp.status_code == 500
        data = resp.json()
        assert data["tarifs"] == []
