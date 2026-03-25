"""
Tests for V61 admin features:
- Feature 1: Soft-delete contact messages
- Feature 2: Votes badge notification (new votes count)
"""

import os
from unittest.mock import patch, AsyncMock

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


# ══════════════════════════════════════════════════════════════════════════════
# Feature 1: Soft-delete messages
# ══════════════════════════════════════════════════════════════════════════════


class TestMessageSoftDelete:
    """DELETE /admin/api/messages/{id} — soft delete."""

    def test_delete_existing_message_returns_ok(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"id": 42})
            mock_db.async_query = AsyncMock()
            resp = client.delete("/admin/api/messages/42")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_delete_nonexistent_message_returns_404(self):
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value=None)
            resp = client.delete("/admin/api/messages/999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["error"]

    def test_delete_requires_auth(self):
        client = _get_client()
        resp = client.delete("/admin/api/messages/1")
        assert resp.status_code == 401

    def test_delete_sets_deleted_flag(self):
        """Verify the UPDATE query sets deleted=1."""
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"id": 7})
            mock_db.async_query = AsyncMock()
            client.delete("/admin/api/messages/7")
            # Check the UPDATE call
            call_args = mock_db.async_query.call_args
            assert "deleted = 1" in call_args[0][0]
            assert call_args[0][1] == (7,)


class TestMessageListingExcludesDeleted:
    """Messages listing and counters exclude deleted=1 messages."""

    def test_listing_includes_deleted_filter(self):
        """SQL queries include deleted = 0 condition."""
        client = _authed_client()
        captured_sqls = []
        with patch("routes.admin.db_cloudsql") as mock_db:
            async def capture_fetchone(sql, params=None):
                captured_sqls.append(sql)
                return {"total": 0, "unread": 0, "today": 0}
            async def capture_fetchall(sql, params=None):
                captured_sqls.append(sql)
                return []
            mock_db.async_fetchone = capture_fetchone
            mock_db.async_fetchall = capture_fetchall
            client.get("/admin/api/messages")
        # Both summary and table queries should have deleted = 0
        for sql in captured_sqls:
            assert "deleted = 0" in sql, f"Missing deleted filter in: {sql}"

    def test_count_unread_excludes_deleted(self):
        """count-unread endpoint also filters deleted=0."""
        client = _authed_client()
        captured_sql = []
        with patch("routes.admin.db_cloudsql") as mock_db:
            async def capture_fetchone(sql, params=None):
                captured_sql.append(sql)
                return {"cnt": 3}
            mock_db.async_fetchone = capture_fetchone
            resp = client.get("/admin/api/messages/count-unread")
        assert resp.status_code == 200
        assert "deleted = 0" in captured_sql[0]

    def test_counters_reflect_non_deleted_only(self):
        """Summary KPI returns counts for non-deleted messages only."""
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"total": 5, "unread": 2, "today": 1})
            mock_db.async_fetchall = AsyncMock(return_value=[])
            resp = client.get("/admin/api/messages")
        data = resp.json()
        assert data["summary"]["total"] == 5
        assert data["summary"]["unread"] == 2
        assert data["summary"]["today"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# Feature 2: Votes badge notification
# ══════════════════════════════════════════════════════════════════════════════


class TestVotesBadge:
    """Badge notification for new votes since last admin visit."""

    def test_votes_page_updates_last_seen(self):
        """Visiting /admin/votes triggers INSERT/UPDATE on admin_last_seen."""
        client = _authed_client()
        captured_sqls = []
        with patch("routes.admin.db_cloudsql") as mock_db:
            async def capture_query(sql, params=None):
                captured_sqls.append(sql)
            mock_db.async_query = capture_query
            resp = client.get("/admin/votes")
        assert resp.status_code == 200
        last_seen_sqls = [s for s in captured_sqls if "admin_last_seen" in s]
        assert len(last_seen_sqls) >= 1, "Expected INSERT INTO admin_last_seen"
        assert "votes" in last_seen_sqls[0]

    def test_count_new_votes_returns_count(self):
        """Endpoint returns new_votes count."""
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 3})
            resp = client.get("/admin/api/votes/count-new")
        assert resp.status_code == 200
        assert resp.json()["new_votes"] == 3

    def test_count_new_votes_zero(self):
        """No new votes returns 0."""
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0})
            resp = client.get("/admin/api/votes/count-new")
        assert resp.status_code == 200
        assert resp.json()["new_votes"] == 0

    def test_count_new_votes_requires_auth(self):
        client = _get_client()
        resp = client.get("/admin/api/votes/count-new")
        assert resp.status_code == 401

    def test_count_new_votes_no_last_seen_returns_zero(self):
        """When admin_last_seen has no 'votes' row, COALESCE to far-future → 0 new."""
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            # COALESCE to '2099-01-01' means no ratings are newer → cnt=0
            mock_db.async_fetchone = AsyncMock(return_value={"cnt": 0})
            resp = client.get("/admin/api/votes/count-new")
        assert resp.status_code == 200
        assert resp.json()["new_votes"] == 0

    def test_count_new_votes_db_error_returns_zero(self):
        """DB error returns 0 gracefully."""
        client = _authed_client()
        with patch("routes.admin.db_cloudsql") as mock_db:
            mock_db.async_fetchone = AsyncMock(side_effect=Exception("DB down"))
            resp = client.get("/admin/api/votes/count-new")
        assert resp.status_code == 200
        assert resp.json()["new_votes"] == 0


class TestVotesBadgeInNavbar:
    """Badge HTML presence in navbar template."""

    def test_votes_badge_span_in_base_template(self):
        with open("ui/templates/admin/_base.html", "r", encoding="utf-8") as f:
            html = f.read()
        assert 'id="votes-badge"' in html
        assert "count-new" in html

    def test_messages_badge_still_present(self):
        with open("ui/templates/admin/_base.html", "r", encoding="utf-8") as f:
            html = f.read()
        assert 'id="msg-badge"' in html


class TestMessageDeleteButtonInJS:
    """admin.js includes delete button for messages."""

    def test_delete_button_present(self):
        with open("ui/static/admin.js", "r", encoding="utf-8") as f:
            js = f.read()
        assert "btn-msg-delete" in js
        assert "deleteMessage" in js
        assert "Supprimer ce message" in js

    def test_delete_button_uses_data_attribute(self):
        """Delete button uses data-msg-id, not inline onclick."""
        with open("ui/static/admin.js", "r", encoding="utf-8") as f:
            js = f.read()
        assert 'onclick="deleteMessage' not in js, "Found inline onclick XSS pattern"
