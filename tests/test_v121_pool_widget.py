"""
V121 — Tests for get_contract_impressions_consumed() helper.
Pool consumption calculation: 4 impression types, calendar cycle Europe/Paris.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from routes.admin_helpers import get_contract_impressions_consumed, _TZ_PARIS


def _run(coro):
    """Run async coroutine in sync test."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_contrat(pool=10000, mode="HYBRIDE"):
    return {"pool_impressions": pool, "mode_depassement": mode}


def _patch_db(mock_row):
    """Patch db_cloudsql in sys.modules so the local import inside the helper picks it up."""
    mock_db = MagicMock()
    mock_db.async_fetchone = AsyncMock(return_value=mock_row)
    return patch.dict(sys.modules, {"db_cloudsql": mock_db}), mock_db


class TestPoolBreakdown:
    """V121: breakdown by 4 impression types."""

    def test_pool_returns_4_types_breakdown(self):
        """Fixture 10p+5i+3r+2pm -> popup=10, inline=5, result=3, pdf_mention=2, total=20."""
        mock_row = {
            "popup": 10, "inline_shown": 5, "result_shown": 3, "pdf_mention": 2,
        }
        patcher, mock_db = _patch_db(mock_row)
        with patcher:
            result = _run(get_contract_impressions_consumed(_make_contrat()))

        assert result["popup"] == 10
        assert result["inline"] == 5
        assert result["result"] == 3
        assert result["pdf_mention"] == 2
        assert result["total"] == 20
        assert result["quota"] == 10000

    def test_pool_excludes_click_video_pdfdl(self):
        """Only non-impression types in DB -> total=0 (SQL WHERE filters them out)."""
        mock_row = {
            "popup": None, "inline_shown": None,
            "result_shown": None, "pdf_mention": None,
        }
        patcher, _ = _patch_db(mock_row)
        with patcher:
            result = _run(get_contract_impressions_consumed(_make_contrat()))

        assert result["total"] == 0
        assert result["popup"] == 0
        assert result["inline"] == 0
        assert result["result"] == 0
        assert result["pdf_mention"] == 0

    def test_pool_excludes_events_outside_cycle(self):
        """SQL uses CONVERT_TZ with cycle_start/cycle_end params."""
        captured = {}

        async def capturing_fetchone(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return {"popup": 0, "inline_shown": 0, "result_shown": 0, "pdf_mention": 0}

        mock_db = MagicMock()
        mock_db.async_fetchone = AsyncMock(side_effect=capturing_fetchone)
        with patch.dict(sys.modules, {"db_cloudsql": mock_db}):
            _run(get_contract_impressions_consumed(_make_contrat()))

        assert "CONVERT_TZ" in captured["sql"]
        assert len(captured["params"]) == 2
        start_str = captured["params"][0]
        assert start_str.endswith("00:00:00")
        assert "-01 " in start_str


class TestPoolStatus:
    """V121: status thresholds and surplus."""

    def test_pool_status_thresholds(self):
        """quota=100: total=50->ok, 75->warn, 95->critical, 105->exceeded."""
        cases = [
            (50, "ok"), (69, "ok"),
            (70, "warn"), (75, "warn"), (89, "warn"),
            (90, "critical"), (95, "critical"), (99, "critical"),
            (100, "exceeded"), (105, "exceeded"), (200, "exceeded"),
        ]
        for total, expected_status in cases:
            mock_row = {"popup": total, "inline_shown": 0, "result_shown": 0, "pdf_mention": 0}
            patcher, _ = _patch_db(mock_row)
            with patcher:
                result = _run(get_contract_impressions_consumed(_make_contrat(pool=100)))
            assert result["status"] == expected_status, (
                f"total={total}: expected {expected_status}, got {result['status']}"
            )

    def test_pool_surplus_calculation(self):
        """total=12000 on quota=10000 -> surplus=2000."""
        mock_row = {"popup": 12000, "inline_shown": 0, "result_shown": 0, "pdf_mention": 0}
        patcher, _ = _patch_db(mock_row)
        with patcher:
            result = _run(get_contract_impressions_consumed(_make_contrat(pool=10000)))

        assert result["total"] == 12000
        assert result["surplus"] == 2000
        assert result["status"] == "exceeded"

    def test_pool_percent_rounded_one_decimal(self):
        """total=3333, quota=10000 -> 33.3%."""
        mock_row = {"popup": 3333, "inline_shown": 0, "result_shown": 0, "pdf_mention": 0}
        patcher, _ = _patch_db(mock_row)
        with patcher:
            result = _run(get_contract_impressions_consumed(_make_contrat(pool=10000)))

        assert result["percent"] == 33.3


class TestPoolCycleTZ:
    """V121: cycle dates respect Europe/Paris timezone."""

    def test_pool_cycle_dates_europe_paris(self):
        """1st May 2026 00:30 Paris (= 30 April 22:30 UTC) -> cycle = May, not April."""
        fake_now_paris = datetime(2026, 5, 1, 0, 30, 0, tzinfo=_TZ_PARIS)

        mock_row = {"popup": 0, "inline_shown": 0, "result_shown": 0, "pdf_mention": 0}
        mock_db = MagicMock()
        mock_db.async_fetchone = AsyncMock(return_value=mock_row)

        with patch.dict(sys.modules, {"db_cloudsql": mock_db}), \
             patch("routes.admin_helpers.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now_paris
            # datetime.now() is mocked, but replace() is called on the returned
            # fake_now_paris object (a real datetime), so it works natively.
            # strftime is also called on real datetime objects.
            # timedelta is imported separately, not affected by mock.
            result = _run(get_contract_impressions_consumed(_make_contrat()))

        # cycle_start must be May 1st, not April 1st
        assert result["cycle_start"].month == 5, (
            f"Expected May (5), got month {result['cycle_start'].month}"
        )
        assert result["cycle_start"].day == 1
        assert result["cycle_start"].year == 2026
        # cycle_end must be June 1st
        assert result["cycle_end"].month == 6
        assert result["cycle_end"].day == 1
        # cycle_label must reference mai/juin
        assert "mai 2026" in result["cycle_label"]
        assert "juin 2026" in result["cycle_label"]

    def test_pool_next_month_label_december(self):
        """December 2026 -> next_month_label = 'janvier 2027'."""
        fake_now = datetime(2026, 12, 5, 12, 0, 0, tzinfo=_TZ_PARIS)

        mock_row = {"popup": 0, "inline_shown": 0, "result_shown": 0, "pdf_mention": 0}
        mock_db = MagicMock()
        mock_db.async_fetchone = AsyncMock(return_value=mock_row)

        with patch.dict(sys.modules, {"db_cloudsql": mock_db}), \
             patch("routes.admin_helpers.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            result = _run(get_contract_impressions_consumed(_make_contrat()))

        assert result["next_month_label"] == "janvier 2027"
        assert result["cycle_start"].month == 12
        assert result["cycle_end"].month == 1
        assert result["cycle_end"].year == 2027


# ══════════════════════════════════════════════════════════════════════════════
# V121 — Route integration tests (admin_contrats_list + admin_contrat_detail)
# ══════════════════════════════════════════════════════════════════════════════

import os

_TEST_TOKEN = "test-token-pool-v121"
_TEST_PASSWORD = "test-password-pool-v121"

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "ADMIN_TOKEN": _TEST_TOKEN,
    "ADMIN_PASSWORD": _TEST_PASSWORD,
})


def _get_route_client():
    from starlette.testclient import TestClient
    with _db_env, _static_patch, _static_call:
        import importlib
        import rate_limit as rl_mod
        importlib.reload(rl_mod)
        import routes.admin_helpers as h
        importlib.reload(h)
        import routes.admin_dashboard as d
        importlib.reload(d)
        import routes.admin_impressions as i
        importlib.reload(i)
        import routes.admin_sponsors as s
        importlib.reload(s)
        import routes.admin_monitoring as m
        importlib.reload(m)
        import routes.admin_calendar as cal
        importlib.reload(cal)
        import routes.admin as a
        importlib.reload(a)
        import main as main_mod
        importlib.reload(main_mod)
        rl_mod.limiter.reset()
        rl_mod._api_hits.clear()
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
        return client


def _pool_result(total=500, quota=10000, status="ok", mode="HYBRIDE", surplus=0,
                 popup=300, inline=100, result=80, pdf_mention=20):
    """Build a mock return value for _get_pool_consumed."""
    return {
        "popup": popup, "inline": inline, "result": result, "pdf_mention": pdf_mention,
        "total": total, "quota": quota, "percent": round(total / quota * 100, 1) if quota else 0,
        "status": status, "mode_depassement": mode, "surplus": surplus,
        "cycle_start": datetime(2026, 4, 1), "cycle_end": datetime(2026, 5, 1),
        "cycle_label": "1er au 30 avril 2026 — reset le 1er mai 2026",
    }


class TestContratListPoolData:
    """V121: admin_contrats_list injects pool_data for active/brouillon contracts."""

    def test_contrats_list_includes_pool_data_for_active_contracts(self):
        client = _get_route_client()
        mock_contrats = [
            {"id": 1, "numero": "CTR-001", "sponsor_id": 1, "sponsor_nom": "Test",
             "product_codes": "LOTOIA_EXCLU", "date_debut": "2026-03-15",
             "date_fin": "2026-06-15", "montant_mensuel_ht": 650.0,
             "mode_depassement": "HYBRIDE", "statut": "actif",
             "engagement_mois": 3, "pool_impressions": 10000,
             "plafond_mensuel": None, "conditions_particulieres": None,
             "created_at": "2026-03-15"},
        ]
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db, \
             patch("routes.admin_sponsors._get_pool_consumed", new_callable=AsyncMock) as mock_pool, \
             patch("routes.admin_sponsors.env") as mock_env:
            mock_db.async_fetchall = AsyncMock(return_value=mock_contrats)
            mock_pool.return_value = _pool_result(total=500)
            mock_tpl = MagicMock()
            mock_tpl.render.return_value = "<html>OK</html>"
            mock_env.get_template.return_value = mock_tpl
            resp = client.get("/admin/contrats")

        assert resp.status_code == 200
        kwargs = mock_tpl.render.call_args.kwargs
        assert "pool_data" in kwargs
        assert 1 in kwargs["pool_data"]
        assert kwargs["pool_data"][1]["total"] == 500
        mock_pool.assert_called_once()

    def test_contrats_list_includes_pool_data_for_brouillon_contracts(self):
        client = _get_route_client()
        mock_contrats = [
            {"id": 2, "numero": "CTR-002", "sponsor_id": 1, "sponsor_nom": "Test",
             "product_codes": "LOTOIA_EXCLU", "date_debut": "2026-04-16",
             "date_fin": "2026-07-16", "montant_mensuel_ht": 585.0,
             "mode_depassement": "HYBRIDE", "statut": "brouillon",
             "engagement_mois": 6, "pool_impressions": 10000,
             "plafond_mensuel": None, "conditions_particulieres": None,
             "created_at": "2026-04-16"},
        ]
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db, \
             patch("routes.admin_sponsors._get_pool_consumed", new_callable=AsyncMock) as mock_pool, \
             patch("routes.admin_sponsors.env") as mock_env:
            mock_db.async_fetchall = AsyncMock(return_value=mock_contrats)
            mock_pool.return_value = _pool_result(total=0)
            mock_tpl = MagicMock()
            mock_tpl.render.return_value = "<html>OK</html>"
            mock_env.get_template.return_value = mock_tpl
            resp = client.get("/admin/contrats")

        assert resp.status_code == 200
        kwargs = mock_tpl.render.call_args.kwargs
        assert 2 in kwargs["pool_data"]
        mock_pool.assert_called_once()

    def test_contrats_list_excludes_pool_data_for_terminated_contracts(self):
        client = _get_route_client()
        mock_contrats = [
            {"id": 3, "numero": "CTR-003", "sponsor_id": 1, "sponsor_nom": "Test",
             "product_codes": "LOTOIA_EXCLU", "date_debut": "2025-01-01",
             "date_fin": "2025-04-01", "montant_mensuel_ht": 650.0,
             "mode_depassement": "CPC", "statut": "expire",
             "engagement_mois": 3, "pool_impressions": 10000,
             "plafond_mensuel": None, "conditions_particulieres": None,
             "created_at": "2025-01-01"},
        ]
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db, \
             patch("routes.admin_sponsors._get_pool_consumed", new_callable=AsyncMock) as mock_pool, \
             patch("routes.admin_sponsors.env") as mock_env:
            mock_db.async_fetchall = AsyncMock(return_value=mock_contrats)
            mock_tpl = MagicMock()
            mock_tpl.render.return_value = "<html>OK</html>"
            mock_env.get_template.return_value = mock_tpl
            resp = client.get("/admin/contrats")

        assert resp.status_code == 200
        kwargs = mock_tpl.render.call_args.kwargs
        assert 3 not in kwargs["pool_data"]
        mock_pool.assert_not_called()

    def test_contrats_list_excludes_pool_data_for_cancelled_contracts(self):
        client = _get_route_client()
        mock_contrats = [
            {"id": 4, "numero": "CTR-004", "sponsor_id": 1, "sponsor_nom": "Test",
             "product_codes": "LOTOIA_EXCLU", "date_debut": "2026-01-01",
             "date_fin": "2026-04-01", "montant_mensuel_ht": 650.0,
             "mode_depassement": "CPC", "statut": "resilie",
             "engagement_mois": 3, "pool_impressions": 10000,
             "plafond_mensuel": None, "conditions_particulieres": None,
             "created_at": "2026-01-01"},
        ]
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db, \
             patch("routes.admin_sponsors._get_pool_consumed", new_callable=AsyncMock) as mock_pool, \
             patch("routes.admin_sponsors.env") as mock_env:
            mock_db.async_fetchall = AsyncMock(return_value=mock_contrats)
            mock_tpl = MagicMock()
            mock_tpl.render.return_value = "<html>OK</html>"
            mock_env.get_template.return_value = mock_tpl
            resp = client.get("/admin/contrats")

        assert resp.status_code == 200
        kwargs = mock_tpl.render.call_args.kwargs
        assert 4 not in kwargs["pool_data"]
        mock_pool.assert_not_called()


class TestContratDetailPoolData:
    """V121: admin_contrat_detail injects impressions_data."""

    def test_contrat_detail_shows_breakdown_4_types(self):
        client = _get_route_client()
        mock_contrat = {
            "id": 1, "numero": "CTR-001", "sponsor_id": 1, "sponsor_nom": "Test",
            "product_codes": "LOTOIA_EXCLU", "date_debut": "2026-03-15",
            "date_fin": "2026-06-15", "montant_mensuel_ht": 650.0,
            "mode_depassement": "HYBRIDE", "statut": "actif",
            "engagement_mois": 3, "pool_impressions": 10000,
            "plafond_mensuel": None, "conditions_particulieres": None,
        }
        pool = _pool_result(popup=300, inline=100, result=80, pdf_mention=20, total=500)
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db, \
             patch("routes.admin_sponsors._get_pool_consumed", new_callable=AsyncMock) as mock_pool, \
             patch("routes.admin_sponsors.env") as mock_env:
            mock_db.async_fetchone = AsyncMock(return_value=mock_contrat)
            mock_pool.return_value = pool
            mock_tpl = MagicMock()
            mock_tpl.render.return_value = "<html>OK</html>"
            mock_env.get_template.return_value = mock_tpl
            resp = client.get("/admin/contrats/1")

        assert resp.status_code == 200
        kwargs = mock_tpl.render.call_args.kwargs
        data = kwargs["impressions_data"]
        assert data is not None
        assert data["popup"] == 300
        assert data["inline"] == 100
        assert data["result"] == 80
        assert data["pdf_mention"] == 20
        assert data["total"] == 500

    def test_contrat_detail_mode_hybride_shows_bonus_on_exceed(self):
        client = _get_route_client()
        mock_contrat = {
            "id": 1, "numero": "CTR-001", "sponsor_id": 1, "sponsor_nom": "Test",
            "product_codes": "LOTOIA_EXCLU", "date_debut": "2026-03-15",
            "date_fin": "2026-06-15", "montant_mensuel_ht": 650.0,
            "mode_depassement": "HYBRIDE", "statut": "actif",
            "engagement_mois": 3, "pool_impressions": 10000,
            "plafond_mensuel": None, "conditions_particulieres": None,
        }
        pool = _pool_result(total=12000, quota=10000, surplus=2000,
                            status="exceeded", mode="HYBRIDE")
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db, \
             patch("routes.admin_sponsors._get_pool_consumed", new_callable=AsyncMock) as mock_pool, \
             patch("routes.admin_sponsors.env") as mock_env:
            mock_db.async_fetchone = AsyncMock(return_value=mock_contrat)
            mock_pool.return_value = pool
            mock_tpl = MagicMock()
            mock_tpl.render.return_value = "<html>OK</html>"
            mock_env.get_template.return_value = mock_tpl
            resp = client.get("/admin/contrats/1")

        assert resp.status_code == 200
        data = mock_tpl.render.call_args.kwargs["impressions_data"]
        assert data["status"] == "exceeded"
        assert data["surplus"] == 2000
        assert data["mode_depassement"] == "HYBRIDE"

    def test_contrat_detail_none_for_terminated(self):
        client = _get_route_client()
        mock_contrat = {
            "id": 5, "numero": "CTR-005", "sponsor_id": 1, "sponsor_nom": "Test",
            "product_codes": "LOTOIA_EXCLU", "date_debut": "2025-01-01",
            "date_fin": "2025-04-01", "montant_mensuel_ht": 650.0,
            "mode_depassement": "CPC", "statut": "expire",
            "engagement_mois": 3, "pool_impressions": 10000,
            "plafond_mensuel": None, "conditions_particulieres": None,
        }
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db, \
             patch("routes.admin_sponsors._get_pool_consumed", new_callable=AsyncMock) as mock_pool, \
             patch("routes.admin_sponsors.env") as mock_env:
            mock_db.async_fetchone = AsyncMock(return_value=mock_contrat)
            mock_tpl = MagicMock()
            mock_tpl.render.return_value = "<html>OK</html>"
            mock_env.get_template.return_value = mock_tpl
            resp = client.get("/admin/contrats/5")

        assert resp.status_code == 200
        kwargs = mock_tpl.render.call_args.kwargs
        assert kwargs["impressions_data"] is None
        mock_pool.assert_not_called()

    def test_contrat_detail_shows_plafond_if_set(self):
        """V121 4.1: plafond_mensuel appears in template context when set."""
        client = _get_route_client()
        mock_contrat = {
            "id": 1, "numero": "CTR-001", "sponsor_id": 1, "sponsor_nom": "Test",
            "product_codes": "LOTOIA_EXCLU", "date_debut": "2026-03-15",
            "date_fin": "2026-06-15", "montant_mensuel_ht": 650.0,
            "mode_depassement": "CPM", "statut": "actif",
            "engagement_mois": 3, "pool_impressions": 10000,
            "plafond_mensuel": 2000.00, "conditions_particulieres": None,
        }
        pool = _pool_result(total=500, mode="CPM")
        with patch("routes.admin_sponsors.db_cloudsql") as mock_db, \
             patch("routes.admin_sponsors._get_pool_consumed", new_callable=AsyncMock) as mock_pool, \
             patch("routes.admin_sponsors.env") as mock_env:
            mock_db.async_fetchone = AsyncMock(return_value=mock_contrat)
            mock_pool.return_value = pool
            mock_tpl = MagicMock()
            mock_tpl.render.return_value = "<html>OK</html>"
            mock_env.get_template.return_value = mock_tpl
            resp = client.get("/admin/contrats/1")

        assert resp.status_code == 200
        kwargs = mock_tpl.render.call_args.kwargs
        # contrat dict passed to template includes plafond_mensuel
        assert kwargs["contrat"]["plafond_mensuel"] == 2000.00
        # impressions_data is present (active contract)
        assert kwargs["impressions_data"] is not None
