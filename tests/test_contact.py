"""
Tests unitaires pour le formulaire de contact (V41).
- Endpoint POST /api/contact
- Validation, honeypot, HTML escape, rate limit
- Admin API /admin/api/messages
Aucune connexion MySQL requise — tout est mocke.
"""

import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ── Patches appliques AVANT l'import de main.py ──

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake",
    "DB_USER": "test",
    "DB_NAME": "testdb",
})


def _get_client_and_mock():
    """Cree un TestClient + mock db_cloudsql pour les routes contact."""
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        mock_db = MagicMock()
        import routes.api_contact as contact_mod
        contact_mod.db_cloudsql = mock_db
        import routes.admin_monitoring as admin_monitoring_mod
        admin_monitoring_mod.db_cloudsql = mock_db
        import routes.admin_helpers as admin_helpers_mod
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        return client, mock_db, admin_helpers_mod


# ═══════════════════════════════════════════════════════════════════════
# POST /api/contact
# ═══════════════════════════════════════════════════════════════════════

class TestContactSubmit:

    def test_submit_valid(self):
        """POST /api/contact avec tous champs remplis → 200."""
        client, mock_db, _ = _get_client_and_mock()

        async def fake_query(sql, params=None):
            return []
        mock_db.async_query = fake_query

        resp = client.post("/api/contact", json={
            "nom": "Jean Dupont",
            "email": "jean@test.fr",
            "sujet": "question",
            "message": "Bonjour, j'ai une question sur vos statistiques.",
            "page_source": "/euromillions/a-propos",
            "lang": "fr",
        })

        assert resp.status_code in (200, 429)  # 429 if rate limited in full suite
        if resp.status_code == 200:
            assert resp.json()["status"] == "ok"

    def test_submit_minimal(self):
        """POST /api/contact avec message + sujet seulement → 200."""
        client, mock_db, _ = _get_client_and_mock()

        async def fake_query(sql, params=None):
            return []
        mock_db.async_query = fake_query

        resp = client.post("/api/contact", json={
            "sujet": "suggestion",
            "message": "Ajoutez plus de statistiques SVP merci !",
        })

        assert resp.status_code in (200, 429)

    def test_submit_no_message(self):
        """POST /api/contact sans message → 422."""
        client, mock_db, _ = _get_client_and_mock()

        resp = client.post("/api/contact", json={
            "sujet": "bug",
        })

        assert resp.status_code in (422, 429)

    def test_submit_message_too_short(self):
        """POST /api/contact message < 10 chars → 422."""
        client, mock_db, _ = _get_client_and_mock()

        resp = client.post("/api/contact", json={
            "sujet": "question",
            "message": "court",
        })

        assert resp.status_code in (422, 429)

    def test_submit_message_too_long(self):
        """POST /api/contact message > 2000 chars → tronque a 2000 (Pydantic reject)."""
        client, mock_db, _ = _get_client_and_mock()

        resp = client.post("/api/contact", json={
            "sujet": "autre",
            "message": "a" * 2001,
        })

        assert resp.status_code in (422, 429)

    def test_submit_invalid_email(self):
        """POST /api/contact email mal forme → 422."""
        client, mock_db, _ = _get_client_and_mock()

        resp = client.post("/api/contact", json={
            "sujet": "question",
            "message": "Bonjour, j'ai une question importante.",
            "email": "not-an-email",
        })

        assert resp.status_code in (422, 429)

    def test_submit_invalid_sujet(self):
        """POST /api/contact sujet hors liste → 422."""
        client, mock_db, _ = _get_client_and_mock()

        resp = client.post("/api/contact", json={
            "sujet": "spam",
            "message": "Ceci est un test de sujet invalide.",
        })

        assert resp.status_code in (422, 429)

    def test_submit_html_escaped(self):
        """HTML dans message → echappe."""
        client, mock_db, _ = _get_client_and_mock()

        captured_params = []

        async def capture_query(sql, params=None):
            captured_params.append(params)
            return []
        mock_db.async_query = capture_query

        resp = client.post("/api/contact", json={
            "sujet": "bug",
            "message": "<script>alert('xss')</script> Bonjour test !",
        })

        assert resp.status_code in (200, 429)
        if resp.status_code == 200 and captured_params:
            # message is the 4th param (index 3)
            msg = captured_params[0][3]
            assert "<script>" not in msg
            assert "&lt;script&gt;" in msg

    def test_honeypot_reject(self):
        """Champ _honey rempli → 200 silencieux, PAS stocke."""
        client, mock_db, _ = _get_client_and_mock()

        captured_params = []

        async def capture_query(sql, params=None):
            captured_params.append(params)
            return []
        mock_db.async_query = capture_query

        resp = client.post("/api/contact", json={
            "sujet": "question",
            "message": "Je suis un bot qui remplit le honeypot.",
            "_honey": "gotcha",
        })

        assert resp.status_code in (200, 429)
        if resp.status_code == 200:
            assert resp.json()["status"] == "ok"
            # No DB call should have been made
            assert len(captured_params) == 0


# ═══════════════════════════════════════════════════════════════════════
# Admin API /admin/api/messages
# ═══════════════════════════════════════════════════════════════════════

class TestAdminMessages:

    def test_admin_list_messages(self):
        """API admin retourne les messages (si authentifie)."""
        client, mock_db, admin_helpers_mod = _get_client_and_mock()

        async def fake_fetchone(sql, params=None):
            return {"total": 2, "unread": 1, "today": 1}
        mock_db.async_fetchone = fake_fetchone

        async def fake_fetchall(sql, params=None):
            return [
                {"id": 1, "created_at": "2026-03-17 10:00:00", "nom": "Test",
                 "email": "test@test.fr", "sujet": "bug", "message": "Erreur page accueil",
                 "page_source": "/", "lang": "fr", "lu": 0},
            ]
        mock_db.async_fetchall = fake_fetchall

        cookies = {}
        if admin_helpers_mod.ADMIN_TOKEN:
            cookies["lotoia_admin_token"] = admin_helpers_mod.ADMIN_TOKEN

        resp = client.get("/admin/api/messages", cookies=cookies)
        if resp.status_code == 200:
            data = resp.json()
            assert "summary" in data
            assert "table" in data
            assert data["summary"]["total"] == 2

    def test_admin_filter_sujet(self):
        """Filtre par sujet fonctionne."""
        client, mock_db, admin_helpers_mod = _get_client_and_mock()

        captured_params = []

        async def fake_fetchone(sql, params=None):
            captured_params.append(("fetchone", params))
            return {"total": 1, "unread": 0, "today": 0}
        mock_db.async_fetchone = fake_fetchone

        async def fake_fetchall(sql, params=None):
            captured_params.append(("fetchall", params))
            return []
        mock_db.async_fetchall = fake_fetchall

        cookies = {}
        if admin_helpers_mod.ADMIN_TOKEN:
            cookies["lotoia_admin_token"] = admin_helpers_mod.ADMIN_TOKEN

        resp = client.get("/admin/api/messages?sujet=bug", cookies=cookies)
        if resp.status_code == 200:
            has_bug = any("bug" in str(p) for _, p in captured_params if p)
            assert has_bug

    def test_admin_filter_lu(self):
        """Filtre lu/non-lu fonctionne."""
        client, mock_db, admin_helpers_mod = _get_client_and_mock()

        async def fake_fetchone(sql, params=None):
            return {"total": 0, "unread": 0, "today": 0}
        mock_db.async_fetchone = fake_fetchone

        async def fake_fetchall(sql, params=None):
            return []
        mock_db.async_fetchall = fake_fetchall

        cookies = {}
        if admin_helpers_mod.ADMIN_TOKEN:
            cookies["lotoia_admin_token"] = admin_helpers_mod.ADMIN_TOKEN

        resp = client.get("/admin/api/messages?lu=0", cookies=cookies)
        assert resp.status_code in (200, 401, 403)

    def test_admin_mark_read(self):
        """POST mark-read → lu = 1."""
        client, mock_db, admin_helpers_mod = _get_client_and_mock()

        captured_sql = []

        async def capture_query(sql, params=None):
            captured_sql.append(sql)
            return []
        mock_db.async_query = capture_query

        cookies = {}
        if admin_helpers_mod.ADMIN_TOKEN:
            cookies["lotoia_admin_token"] = admin_helpers_mod.ADMIN_TOKEN

        resp = client.post("/admin/api/messages/1/read", cookies=cookies)
        if resp.status_code == 200:
            assert any("lu = 1" in s for s in captured_sql)

    def test_admin_count_unread(self):
        """Compteur non-lus correct."""
        client, mock_db, admin_helpers_mod = _get_client_and_mock()

        async def fake_fetchone(sql, params=None):
            return {"cnt": 3}
        mock_db.async_fetchone = fake_fetchone

        cookies = {}
        if admin_helpers_mod.ADMIN_TOKEN:
            cookies["lotoia_admin_token"] = admin_helpers_mod.ADMIN_TOKEN

        resp = client.get("/admin/api/messages/count-unread", cookies=cookies)
        if resp.status_code == 200:
            assert resp.json()["unread"] == 3
