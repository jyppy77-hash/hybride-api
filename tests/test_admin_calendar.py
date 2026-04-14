"""
Tests for admin calendar heatmap API.
GET /admin/api/calendar-data — monthly aggregated stats by day.
"""

import os
from unittest.mock import patch, AsyncMock, MagicMock

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
        import routes.admin_calendar as admin_calendar_mod
        importlib.reload(admin_calendar_mod)
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


# ── Helper: build async context manager mock for get_connection_readonly ──

def _make_conn_mock(rows_sequence):
    """Create a mock for db_cloudsql.get_connection_readonly().

    rows_sequence: list of lists — each entry is the fetchall() result
    for successive cursor.execute() calls.
    """
    call_idx = {"i": 0}

    class FakeCursor:
        async def execute(self, sql, params=None):
            pass

        async def fetchall(self):
            idx = call_idx["i"]
            call_idx["i"] += 1
            if idx < len(rows_sequence):
                return rows_sequence[idx]
            return []

    class FakeConn:
        async def cursor(self):
            return FakeCursor()

    class FakeCtx:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, *args):
            pass

    return FakeCtx()


class TestCalendarAuth:
    """Auth / validation tests."""

    def test_no_auth_returns_401(self):
        client = _get_client()
        resp = client.get("/admin/api/calendar-data")
        assert resp.status_code == 401

    def test_invalid_year_returns_400(self):
        client = _authed_client()
        resp = client.get("/admin/api/calendar-data?year=2099&month=4")
        assert resp.status_code == 400
        assert "year" in resp.json()["error"]

    def test_invalid_month_returns_400(self):
        client = _authed_client()
        resp = client.get("/admin/api/calendar-data?year=2026&month=13")
        assert resp.status_code == 400
        assert "month" in resp.json()["error"]

    def test_month_zero_returns_400(self):
        client = _authed_client()
        resp = client.get("/admin/api/calendar-data?year=2026&month=0")
        assert resp.status_code == 400


class TestCalendarData:
    """Data response tests."""

    def test_returns_data_for_3_days(self):
        """Mock DB returns data for days 1, 5, 10 — other days should be 0."""
        # 4 queries: visitors (UNION ALL), sessions, impressions, chatbot
        visitor_rows = [
            {"day": 1, "visitors": 42},
            {"day": 5, "visitors": 38},
            {"day": 10, "visitors": 15},
        ]
        session_rows = [
            {"day": 1, "sessions": 65},
            {"day": 5, "sessions": 51},
            {"day": 10, "sessions": 22},
        ]
        impression_rows = [
            {"day": 1, "impressions": 128},
            {"day": 5, "impressions": 95},
        ]
        chatbot_rows = [
            {"day": 1, "chatbot": 3},
            {"day": 10, "chatbot": 7},
        ]

        call_idx = {"i": 0}
        all_rows = [visitor_rows, session_rows, impression_rows, chatbot_rows]

        class FakeCursor:
            def __init__(self):
                self._idx = None

            async def execute(self, sql, params=None):
                self._idx = call_idx["i"]
                call_idx["i"] += 1

            async def fetchall(self):
                if self._idx is not None and self._idx < len(all_rows):
                    return all_rows[self._idx]
                return []

        class FakeConn:
            async def cursor(self):
                return FakeCursor()

        class FakeCtx:
            async def __aenter__(self):
                return FakeConn()

            async def __aexit__(self, *args):
                pass

        client = _authed_client()
        with patch("routes.admin_calendar.db_cloudsql") as mock_db:
            mock_db.get_connection_readonly.return_value = FakeCtx()
            resp = client.get("/admin/api/calendar-data?year=2026&month=4")

        assert resp.status_code == 200
        data = resp.json()
        assert data["year"] == 2026
        assert data["month"] == 4
        # 30 days in April
        assert len(data["days"]) == 30

        # Day 1: merged from all 4 queries
        assert data["days"]["1"]["visitors"] == 42
        assert data["days"]["1"]["sessions"] == 65
        assert data["days"]["1"]["impressions"] == 128
        assert data["days"]["1"]["chatbot"] == 3

        # Day 5: visitors + sessions + impressions, no chatbot
        assert data["days"]["5"]["visitors"] == 38
        assert data["days"]["5"]["impressions"] == 95
        assert data["days"]["5"]["chatbot"] == 0

        # Day 10: visitors + sessions + chatbot, no impressions
        assert data["days"]["10"]["visitors"] == 15
        assert data["days"]["10"]["impressions"] == 0
        assert data["days"]["10"]["chatbot"] == 7

        # Day 15: all zeros
        assert data["days"]["15"] == {"visitors": 0, "impressions": 0, "sessions": 0, "chatbot": 0}

    def test_default_month_is_current(self):
        """Call without params returns current month."""
        from datetime import date
        today = date.today()

        mock_ctx = _make_conn_mock([[], [], []])

        client = _authed_client()
        with patch("routes.admin_calendar.db_cloudsql") as mock_db:
            mock_db.get_connection_readonly.return_value = mock_ctx

            # Need fresh mock for each call
            class FakeCtx:
                async def __aenter__(self):
                    class FakeConn:
                        async def cursor(self):
                            class FakeCursor:
                                async def execute(self, sql, params=None):
                                    pass

                                async def fetchall(self):
                                    return []
                            return FakeCursor()
                    return FakeConn()

                async def __aexit__(self, *args):
                    pass

            mock_db.get_connection_readonly.return_value = FakeCtx()
            resp = client.get("/admin/api/calendar-data")

        assert resp.status_code == 200
        data = resp.json()
        assert data["year"] == today.year
        assert data["month"] == today.month

    def test_empty_month_all_zeros(self):
        """DB returns no rows — all days should be zero."""
        client = _authed_client()
        with patch("routes.admin_calendar.db_cloudsql") as mock_db:

            class FakeCtx:
                async def __aenter__(self):
                    class FakeConn:
                        async def cursor(self):
                            class FakeCursor:
                                async def execute(self, sql, params=None):
                                    pass

                                async def fetchall(self):
                                    return []
                            return FakeCursor()
                    return FakeConn()

                async def __aexit__(self, *args):
                    pass

            mock_db.get_connection_readonly.return_value = FakeCtx()
            resp = client.get("/admin/api/calendar-data?year=2026&month=3")

        assert resp.status_code == 200
        data = resp.json()
        # March = 31 days
        assert len(data["days"]) == 31
        for d in range(1, 32):
            assert data["days"][str(d)] == {"visitors": 0, "impressions": 0, "sessions": 0, "chatbot": 0}

    def test_february_leap_year_29_days(self):
        """February 2028 is a leap year — should have 29 days."""
        client = _authed_client()
        with patch("routes.admin_calendar.db_cloudsql") as mock_db:

            class FakeCtx:
                async def __aenter__(self):
                    class FakeConn:
                        async def cursor(self):
                            class FakeCursor:
                                async def execute(self, sql, params=None):
                                    pass

                                async def fetchall(self):
                                    return []
                            return FakeCursor()
                    return FakeConn()

                async def __aexit__(self, *args):
                    pass

            mock_db.get_connection_readonly.return_value = FakeCtx()
            resp = client.get("/admin/api/calendar-data?year=2028&month=2")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["days"]) == 29
        assert "29" in data["days"]

    def test_february_non_leap_28_days(self):
        """February 2026 is NOT a leap year — should have 28 days."""
        client = _authed_client()
        with patch("routes.admin_calendar.db_cloudsql") as mock_db:

            class FakeCtx:
                async def __aenter__(self):
                    class FakeConn:
                        async def cursor(self):
                            class FakeCursor:
                                async def execute(self, sql, params=None):
                                    pass

                                async def fetchall(self):
                                    return []
                            return FakeCursor()
                    return FakeConn()

                async def __aexit__(self, *args):
                    pass

            mock_db.get_connection_readonly.return_value = FakeCtx()
            resp = client.get("/admin/api/calendar-data?year=2026&month=2")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["days"]) == 28
        assert "29" not in data["days"]

    def test_db_error_returns_zeros(self):
        """If DB raises an exception, days should still be zero (graceful degradation)."""
        client = _authed_client()
        with patch("routes.admin_calendar.db_cloudsql") as mock_db:

            class FakeCtx:
                async def __aenter__(self):
                    raise Exception("DB down")

                async def __aexit__(self, *args):
                    pass

            mock_db.get_connection_readonly.return_value = FakeCtx()
            resp = client.get("/admin/api/calendar-data?year=2026&month=4")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["days"]) == 30
        # All zeros despite DB error
        for d in range(1, 31):
            assert data["days"][str(d)] == {"visitors": 0, "impressions": 0, "sessions": 0, "chatbot": 0}

    def test_merge_4_queries_independent(self):
        """Each query contributes different metrics to the same day."""
        call_idx = {"i": 0}
        all_rows = [
            # visitors (UNION ALL): day 7
            [{"day": 7, "visitors": 100}],
            # sessions (event_log): day 7
            [{"day": 7, "sessions": 200}],
            # impressions (sponsor_impressions): day 7
            [{"day": 7, "impressions": 50}],
            # chatbot (chat_log): day 7
            [{"day": 7, "chatbot": 12}],
        ]

        class FakeCursor:
            def __init__(self):
                self._idx = None

            async def execute(self, sql, params=None):
                self._idx = call_idx["i"]
                call_idx["i"] += 1

            async def fetchall(self):
                if self._idx is not None and self._idx < len(all_rows):
                    return all_rows[self._idx]
                return []

        class FakeConn:
            async def cursor(self):
                return FakeCursor()

        class FakeCtx:
            async def __aenter__(self):
                return FakeConn()

            async def __aexit__(self, *args):
                pass

        client = _authed_client()
        with patch("routes.admin_calendar.db_cloudsql") as mock_db:
            mock_db.get_connection_readonly.return_value = FakeCtx()
            resp = client.get("/admin/api/calendar-data?year=2026&month=1")

        assert resp.status_code == 200
        data = resp.json()
        # January = 31 days
        assert len(data["days"]) == 31
        # Day 7: all 3 tables merged
        assert data["days"]["7"] == {"visitors": 100, "impressions": 50, "sessions": 200, "chatbot": 12}
        # Day 8: nothing
        assert data["days"]["8"] == {"visitors": 0, "impressions": 0, "sessions": 0, "chatbot": 0}


    def test_visitors_cross_tables(self):
        """Visitors counted from all 3 tables — even if event_log has 0 rows."""
        call_idx = {"i": 0}
        all_rows = [
            # visitors UNION ALL: IPs from sponsor_impressions + chat_log only
            [{"day": 19, "visitors": 25}],
            # sessions (event_log): no data
            [],
            # impressions: day 19
            [{"day": 19, "impressions": 670}],
            # chatbot: day 19
            [{"day": 19, "chatbot": 52}],
        ]

        class FakeCursor:
            def __init__(self):
                self._idx = None

            async def execute(self, sql, params=None):
                self._idx = call_idx["i"]
                call_idx["i"] += 1

            async def fetchall(self):
                if self._idx is not None and self._idx < len(all_rows):
                    return all_rows[self._idx]
                return []

        class FakeConn:
            async def cursor(self):
                return FakeCursor()

        class FakeCtx:
            async def __aenter__(self):
                return FakeConn()

            async def __aexit__(self, *args):
                pass

        client = _authed_client()
        with patch("routes.admin_calendar.db_cloudsql") as mock_db:
            mock_db.get_connection_readonly.return_value = FakeCtx()
            resp = client.get("/admin/api/calendar-data?year=2026&month=3")

        assert resp.status_code == 200
        data = resp.json()
        day19 = data["days"]["19"]
        # Visitors > 0 even though event_log had no rows
        assert day19["visitors"] == 25
        assert day19["sessions"] == 0
        assert day19["impressions"] == 670
        assert day19["chatbot"] == 52


class TestCalendarPage:
    """HTML page tests."""

    def test_page_returns_200_with_auth(self):
        """GET /admin/calendar with valid session returns 200 + contains title."""
        client = _authed_client()
        resp = client.get("/admin/calendar")
        assert resp.status_code == 200
        assert "Calendrier" in resp.text

    def test_page_redirects_without_auth(self):
        """GET /admin/calendar without session redirects to login."""
        client = _get_client()
        resp = client.get("/admin/calendar", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    # V115: Cache-Control + LIVE dot

    def test_page_cache_control_no_store(self):
        """V115: Calendar page has Cache-Control: no-store."""
        client = _authed_client()
        resp = client.get("/admin/calendar")
        assert resp.status_code == 200
        assert "no-store" in resp.headers.get("cache-control", "")

    def test_api_cache_control_no_store(self):
        """V115: Calendar API has Cache-Control: no-store."""
        client = _authed_client()
        with patch("routes.admin_calendar.db_cloudsql") as mock_db:

            class FakeCtx:
                async def __aenter__(self):
                    class FakeConn:
                        async def cursor(self):
                            class FakeCursor:
                                async def execute(self, sql, params=None):
                                    pass

                                async def fetchall(self):
                                    return []
                            return FakeCursor()
                    return FakeConn()

                async def __aexit__(self, *args):
                    pass

            mock_db.get_connection_readonly.return_value = FakeCtx()
            resp = client.get("/admin/api/calendar-data?year=2026&month=4")

        assert resp.status_code == 200
        assert "no-store" in resp.headers.get("cache-control", "")

    def test_page_has_live_dot(self):
        """V115: Calendar page has LIVE pulse indicator."""
        client = _authed_client()
        resp = client.get("/admin/calendar")
        assert resp.status_code == 200
        assert 'id="cal-live-dot"' in resp.text
        assert 'rt-dot-live' in resp.text
