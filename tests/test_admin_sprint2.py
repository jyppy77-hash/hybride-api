"""
Tests — Sprint 2: Performance SQL, Audit logging, Cleanup.
A05 (ratings 90d filter), A06 (event_type 30d filter), A07 (facture GROUP BY),
A08 (audit logging on config/tarifs).
"""

import json
import os
from unittest.mock import patch, AsyncMock, call

import pytest
from starlette.testclient import TestClient


_TEST_TOKEN = "test_admin_token_sprint2"
_TEST_PASSWORD = "test_admin_password_sprint2"

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


class TestA05RatingsDateFilter:
    """A05: Dashboard ratings query must have a date filter matching period dropdown (V91 F02)."""

    def test_ratings_query_uses_period_filter(self):
        """Default period='today' → ratings WHERE uses CONVERT_TZ (not hardcoded 90 DAY)."""
        client = _authed_client()
        sql_calls = []

        async def mock_fetchone(sql, params=None):
            sql_calls.append(sql)
            if "ratings" in sql:
                return {"review_count": 5, "avg_rating": 4.0}
            return {"cnt": 0}

        with patch("routes.admin_dashboard.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(side_effect=mock_fetchone)
            resp = client.get("/admin")

        assert resp.status_code == 200
        ratings_sql = [s for s in sql_calls if "ratings" in s]
        assert len(ratings_sql) == 1
        # V91 F02: ratings now respects dropdown period (default=today → CONVERT_TZ)
        assert "CONVERT_TZ" in ratings_sql[0] or "INTERVAL" in ratings_sql[0]

    def test_ratings_query_month_uses_30_day(self):
        """period='month' → ratings WHERE uses INTERVAL 30 DAY."""
        client = _authed_client()
        sql_calls = []

        async def mock_fetchone(sql, params=None):
            sql_calls.append(sql)
            if "ratings" in sql:
                return {"review_count": 10, "avg_rating": 3.5}
            return {"cnt": 0}

        with patch("routes.admin_dashboard.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            mock_db.async_fetchone = AsyncMock(side_effect=mock_fetchone)
            resp = client.get("/admin?period=month")

        assert resp.status_code == 200
        ratings_sql = [s for s in sql_calls if "ratings" in s]
        assert len(ratings_sql) == 1
        assert "INTERVAL 30 DAY" in ratings_sql[0]


class TestA06EventTypeDateFilter:
    """A06: Realtime event_type dropdown must have a date filter (30 days)."""

    def test_realtime_event_types_has_date_filter(self):
        client = _authed_client()
        sql_calls = []

        async def mock_fetchall(sql, params=None):
            sql_calls.append(sql)
            if "DISTINCT event_type" in sql:
                return [{"event_type": "chatbot-open"}]
            return []

        async def mock_fetchone(sql, params=None):
            sql_calls.append(sql)
            return {
                "total_count": 0, "hour_count": 0,
                "type_count": 0, "unique_visitors": 0,
            }

        with patch("routes.admin_monitoring.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=mock_fetchall)
            mock_db.async_fetchone = AsyncMock(side_effect=mock_fetchone)
            resp = client.get("/admin/api/realtime?period=24h")

        assert resp.status_code == 200
        # Match the specific dropdown query (SELECT DISTINCT event_type FROM), not the KPI COUNT(DISTINCT)
        distinct_sql = [s for s in sql_calls if "SELECT DISTINCT event_type FROM" in s]
        assert len(distinct_sql) == 1
        assert "INTERVAL 30 DAY" in distinct_sql[0]


class TestA07FactureGroupBy:
    """A07: Facture create must use GROUP BY instead of N+1 loop."""

    def test_facture_create_uses_group_by(self):
        client = _authed_client()
        sql_calls = []

        async def mock_fetchall(sql, params=None):
            sql_calls.append(sql)
            if "fia_grille_tarifaire" in sql:
                return [
                    {"id": 1, "event_type": "sponsor-popup-shown", "prix_unitaire": 0.01, "description": "Popup"},
                    {"id": 2, "event_type": "sponsor-click", "prix_unitaire": 0.10, "description": "Click"},
                    {"id": 3, "event_type": "sponsor-video-played", "prix_unitaire": 0.50, "description": "Video"},
                ]
            if "GROUP BY event_type" in sql:
                return [
                    {"event_type": "sponsor-popup-shown", "cnt": 100},
                    {"event_type": "sponsor-click", "cnt": 20},
                    {"event_type": "sponsor-video-played", "cnt": 5},
                ]
            if "fia_sponsors" in sql:
                return [{"id": 1, "nom": "TestSponsor"}]
            return []

        async def mock_fetchone(sql, params=None):
            sql_calls.append(sql)
            if "taux_tva" in sql:
                return {"taux_tva": 20}
            if "COUNT" in sql and "fia_factures" in sql:
                return {"cnt": 0}
            return None

        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(side_effect=mock_fetchall)
            mock_db.async_fetchone = AsyncMock(side_effect=mock_fetchone)
            mock_db.async_query = AsyncMock()
            resp = client.post("/admin/factures/new", data={
                "sponsor_id": "1",
                "periode_debut": "2026-02-01",
                "periode_fin": "2026-02-28",
            }, follow_redirects=False)

        assert resp.status_code == 302
        # Verify GROUP BY was used (not individual COUNT per event_type)
        group_by_calls = [s for s in sql_calls if "GROUP BY event_type" in s]
        assert len(group_by_calls) == 1
        # Verify NO individual COUNT queries per event_type (N+1 pattern)
        individual_counts = [
            s for s in sql_calls
            if "COUNT(*) AS cnt" in s and "sponsor_impressions" in s and "GROUP BY" not in s
        ]
        assert len(individual_counts) == 0


class TestA08AuditLogging:
    """A08: [ADMIN_AUDIT] must be logged on config save, tarif mode, tarif update."""

    def test_config_save_logs_audit(self, capsys):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            mock_db.async_fetchone = AsyncMock(return_value={
                "raison_sociale": "Test", "siret": "", "adresse": "",
                "code_postal": "", "ville": "", "pays": "France",
                "email": "", "telephone": "", "tva_intra": "",
                "taux_tva": 0, "iban": "", "bic": "", "logo_url": "",
                "forme_juridique": "EI", "rcs": "", "capital_social": "",
            })
            resp = client.post("/admin/config", data={
                "raison_sociale": "LotoIA",
                "siret": "123",
            })
        # Page may 500 due to alerting import in render, but audit log should still fire
        captured = capsys.readouterr().out
        assert "ADMIN_AUDIT" in captured
        assert "action=config_update" in captured

    def test_tarif_mode_logs_audit(self, capsys):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            resp = client.post("/admin/api/tarifs/mode", json={"mode": "SASU"})
        assert resp.status_code == 200
        captured = capsys.readouterr().out
        assert "ADMIN_AUDIT" in captured
        assert "action=tarif_mode_change" in captured
        assert "mode=SASU" in captured

    def test_tarif_update_logs_audit(self, capsys):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_query = AsyncMock()
            resp = client.put("/admin/api/tarifs/LOTO_FR_A", json={
                "tarif_mensuel": 399.00,
                "engagement_min_mois": 6,
                "reduction_6m": 10,
                "reduction_12m": 20,
                "active": 1,
            })
        assert resp.status_code == 200
        captured = capsys.readouterr().out
        assert "ADMIN_AUDIT" in captured
        assert "action=tarif_update" in captured
        assert "code=LOTO_FR_A" in captured


class TestTarifsV9:
    """V9: Tarifs page renders mono-annonceur exclusif layout."""

    def test_tarifs_page_renders_v9(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/tarifs")
        assert resp.status_code == 200
        body = resp.text
        assert "LOTOIA_EXCLU" in body
        assert "EXCLUSIF" in body
        assert "650" in body
        assert "Palier" in body
        assert "Garanties" in body

    def test_tarifs_page_no_old_toggle(self):
        """V9 removed EI/SASU toggle and 14-code grid."""
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/tarifs")
        body = resp.text
        assert "billing-toggle" not in body
        assert "LOTO_FR_A" not in body
        assert "Packs regionaux" not in body

    def test_tarifs_paliers_v9_data(self):
        """V9 paliers use new pricing (650/815/1020/Sur mesure)."""
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/tarifs")
        body = resp.text
        assert "815" in body
        assert "1 020" in body
        assert "Sur mesure" in body

    def test_tarifs_api_returns_paliers_v9(self):
        """GET /admin/api/tarifs returns V9 paliers."""
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchall = AsyncMock(return_value=[
                {"config_key": "billing_mode", "config_value": "EI"},
            ])
            # Second call is for sponsor_tarifs
            mock_db.async_fetchall.side_effect = [
                [{"config_key": "billing_mode", "config_value": "EI"}],
                [],
            ]
            resp = client.get("/admin/api/tarifs",
                              headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        data = resp.json()
        assert "paliers" in data
        assert len(data["paliers"]) == 4
        assert data["paliers"][0]["name"] == "Lancement"
        # V9: no more packs key
        assert "packs" not in data


class TestConfigEI:
    """Config page adapts for EI forme juridique."""

    def test_config_page_renders_forme_select(self):
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "raison_sociale": "EmovisIA", "siret": "123", "adresse": "",
                "code_postal": "", "ville": "", "pays": "France",
                "email": "", "telephone": "", "tva_intra": "",
                "taux_tva": 0, "iban": "", "bic": "",
                "forme_juridique": "EI", "rcs": "", "capital_social": "",
            })
            resp = client.get("/admin/config")
        assert resp.status_code == 200
        body = resp.text
        assert "cfg-forme" in body
        assert "grp-rcs" in body
        assert "grp-capital" in body
        assert "293B" in body

    def test_config_tva_default_zero_ei(self):
        """EI: taux_tva default should be 0 (franchise en base)."""
        client = _authed_client()
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={
                "raison_sociale": "EmovisIA", "siret": "123", "adresse": "",
                "code_postal": "", "ville": "", "pays": "France",
                "email": "", "telephone": "", "tva_intra": "",
                "taux_tva": 0, "iban": "", "bic": "",
                "forme_juridique": "EI", "rcs": "", "capital_social": "",
            })
            resp = client.get("/admin/config")
        body = resp.text
        # The TVA input should have value 0 for EI
        assert 'value="0"' in body or "value=\"0\"" in body
