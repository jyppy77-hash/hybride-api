"""
Tests unitaires pour le systeme de notation (ratings).
- Schemas Pydantic (RatingSubmit, RatingResponse, RatingAggregate)
- Endpoints API (POST /api/rating, GET /api/ratings/aggregate)
Aucune connexion MySQL requise — tout est mocke.
"""

import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from schemas import RatingSubmit, RatingResponse, RatingAggregate


# ── Patches appliques AVANT l'import de main.py ──

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake",
    "DB_USER": "test",
    "DB_NAME": "testdb",
})


def _get_client_and_mock():
    """Cree un TestClient + mock db_cloudsql pour les routes ratings."""
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        mock_db = MagicMock()
        import routes.api_ratings as ratings_mod
        ratings_mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        return client, mock_db


# ═══════════════════════════════════════════════════════════════════════
# Schemas Pydantic
# ═══════════════════════════════════════════════════════════════════════

class TestRatingSubmitSchema:

    def test_valid_chatbot_loto(self):
        r = RatingSubmit(
            source="chatbot_loto", rating=5,
            session_id="sess_1234567890", page="/loto",
        )
        assert r.source == "chatbot_loto"
        assert r.rating == 5

    def test_valid_chatbot_em(self):
        r = RatingSubmit(
            source="chatbot_em", rating=3,
            session_id="sess_abcdefghij",
        )
        assert r.source == "chatbot_em"
        assert r.page == "/"

    def test_valid_popup_accueil(self):
        r = RatingSubmit(
            source="popup_accueil", rating=1,
            session_id="sess_1234567890",
            comment="Super site !",
        )
        assert r.comment == "Super site !"

    def test_invalid_source(self):
        with pytest.raises(ValidationError):
            RatingSubmit(
                source="invalid_source", rating=5,
                session_id="sess_1234567890",
            )

    def test_rating_too_low(self):
        with pytest.raises(ValidationError):
            RatingSubmit(
                source="chatbot_loto", rating=0,
                session_id="sess_1234567890",
            )

    def test_rating_too_high(self):
        with pytest.raises(ValidationError):
            RatingSubmit(
                source="chatbot_loto", rating=6,
                session_id="sess_1234567890",
            )

    def test_session_id_too_short(self):
        with pytest.raises(ValidationError):
            RatingSubmit(
                source="chatbot_loto", rating=5,
                session_id="short",
            )

    def test_comment_too_long(self):
        with pytest.raises(ValidationError):
            RatingSubmit(
                source="chatbot_loto", rating=5,
                session_id="sess_1234567890",
                comment="x" * 501,
            )

    def test_comment_max_length_ok(self):
        r = RatingSubmit(
            source="chatbot_loto", rating=5,
            session_id="sess_1234567890",
            comment="x" * 500,
        )
        assert len(r.comment) == 500


class TestRatingResponseSchema:

    def test_success(self):
        r = RatingResponse(success=True, message="Merci !")
        assert r.success is True

    def test_failure(self):
        r = RatingResponse(success=False, message="Erreur")
        assert r.success is False


class TestRatingAggregateSchema:

    def test_with_source(self):
        r = RatingAggregate(avg_rating=4.3, review_count=42, source="chatbot_loto")
        assert r.source == "chatbot_loto"

    def test_without_source(self):
        r = RatingAggregate(avg_rating=4.5, review_count=100)
        assert r.source is None

    def test_zero_values(self):
        r = RatingAggregate(avg_rating=0, review_count=0)
        assert r.avg_rating == 0
        assert r.review_count == 0


# ═══════════════════════════════════════════════════════════════════════
# POST /api/rating
# ═══════════════════════════════════════════════════════════════════════

class TestSubmitRatingEndpoint:

    def test_submit_rating_success(self):
        """POST /api/rating avec donnees valides → 200 + success."""
        client, mock_db = _get_client_and_mock()

        # async_query retourne une coroutine (TestClient gere l'event loop)
        async def fake_query(sql, params=None):
            return []
        mock_db.async_query = fake_query

        resp = client.post("/api/rating", json={
            "source": "chatbot_loto",
            "rating": 5,
            "session_id": "sess_test_001_abcdef",
            "page": "/loto",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "Merci" in data["message"]

    def test_submit_rating_invalid_source(self):
        """POST /api/rating avec source invalide → 422."""
        client, mock_db = _get_client_and_mock()

        resp = client.post("/api/rating", json={
            "source": "invalid",
            "rating": 5,
            "session_id": "sess_test_001_abcdef",
        })

        assert resp.status_code == 422

    def test_submit_rating_missing_session(self):
        """POST /api/rating sans session_id → 422."""
        client, mock_db = _get_client_and_mock()

        resp = client.post("/api/rating", json={
            "source": "chatbot_loto",
            "rating": 5,
        })

        assert resp.status_code == 422

    def test_submit_rating_rating_out_of_range(self):
        """POST /api/rating avec rating=0 → 422."""
        client, mock_db = _get_client_and_mock()

        resp = client.post("/api/rating", json={
            "source": "chatbot_loto",
            "rating": 0,
            "session_id": "sess_test_001_abcdef",
        })

        assert resp.status_code == 422

    def test_submit_rating_db_error(self):
        """POST /api/rating avec erreur DB → 500."""
        client, mock_db = _get_client_and_mock()

        async def fail_query(sql, params=None):
            raise Exception("DB connection lost")
        mock_db.async_query = fail_query

        resp = client.post("/api/rating", json={
            "source": "chatbot_loto",
            "rating": 5,
            "session_id": "sess_test_001_abcdef",
        })

        assert resp.status_code == 500

    def test_submit_rating_all_sources(self):
        """Les 3 sources valides sont acceptees."""
        client, mock_db = _get_client_and_mock()

        async def fake_query(sql, params=None):
            return []
        mock_db.async_query = fake_query

        for source in ["chatbot_loto", "chatbot_em", "popup_accueil"]:
            resp = client.post("/api/rating", json={
                "source": source,
                "rating": 4,
                "session_id": "sess_test_001_abcdef",
            })
            assert resp.status_code == 200, f"Source {source} devrait etre acceptee"


# ═══════════════════════════════════════════════════════════════════════
# GET /api/ratings/aggregate
# ═══════════════════════════════════════════════════════════════════════

class TestAggregateEndpoint:

    def test_aggregate_with_data(self):
        """GET /api/ratings/aggregate retourne les stats globales."""
        client, mock_db = _get_client_and_mock()

        async def fake_fetchone(sql, params=None):
            return {"review_count": 42, "avg_rating": 4.3}
        mock_db.async_fetchone = fake_fetchone

        resp = client.get("/api/ratings/aggregate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["avg_rating"] == 4.3
        assert data["review_count"] == 42

    def test_aggregate_empty(self):
        """GET /api/ratings/aggregate sans votes → zeros."""
        client, mock_db = _get_client_and_mock()

        async def fake_fetchone(sql, params=None):
            return {"review_count": 0, "avg_rating": None}
        mock_db.async_fetchone = fake_fetchone

        resp = client.get("/api/ratings/aggregate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["avg_rating"] == 0
        assert data["review_count"] == 0

    def test_aggregate_db_error(self):
        """GET /api/ratings/aggregate avec erreur DB → fallback zeros."""
        client, mock_db = _get_client_and_mock()

        async def fail_fetchone(sql, params=None):
            raise Exception("DB timeout")
        mock_db.async_fetchone = fail_fetchone

        resp = client.get("/api/ratings/aggregate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["avg_rating"] == 0
        assert data["review_count"] == 0


# ═══════════════════════════════════════════════════════════════════════
# GET /api/ratings/aggregate/{source}
# ═══════════════════════════════════════════════════════════════════════

class TestAggregateBySourceEndpoint:

    def test_aggregate_chatbot_loto(self):
        """GET /api/ratings/aggregate/chatbot_loto retourne les stats."""
        client, mock_db = _get_client_and_mock()

        async def fake_fetchone(sql, params=None):
            return {"review_count": 15, "avg_rating": 4.7}
        mock_db.async_fetchone = fake_fetchone

        resp = client.get("/api/ratings/aggregate/chatbot_loto")

        assert resp.status_code == 200
        data = resp.json()
        assert data["avg_rating"] == 4.7
        assert data["review_count"] == 15
        assert data["source"] == "chatbot_loto"

    def test_aggregate_unknown_source(self):
        """GET /api/ratings/aggregate/unknown → zeros."""
        client, mock_db = _get_client_and_mock()

        async def fake_fetchone(sql, params=None):
            return None
        mock_db.async_fetchone = fake_fetchone

        resp = client.get("/api/ratings/aggregate/unknown")

        assert resp.status_code == 200
        data = resp.json()
        assert data["avg_rating"] == 0
        assert data["review_count"] == 0
        assert data["source"] == "unknown"


# ═══════════════════════════════════════════════════════════════════════
# Anti-spam : IP hashing + session_id
# ═══════════════════════════════════════════════════════════════════════

class TestAntiSpam:

    def test_ip_hash_not_plain_ip(self):
        """Le hash IP envoye a la DB n'est pas l'IP en clair."""
        client, mock_db = _get_client_and_mock()

        captured_params = []

        async def capture_query(sql, params=None):
            captured_params.append(params)
            return []
        mock_db.async_query = capture_query

        resp = client.post("/api/rating", json={
            "source": "chatbot_loto",
            "rating": 5,
            "session_id": "sess_test_001_abcdef",
        })

        assert resp.status_code == 200
        assert len(captured_params) == 1
        params = captured_params[0]
        # ip_hash est le 7eme parametre (index 6)
        ip_hash = params[6]
        assert ip_hash is not None
        # Ne doit PAS etre une IP en clair
        assert "." not in ip_hash  # pas de format x.x.x.x
        assert len(ip_hash) == 16  # SHA-256 tronque a 16 chars

    def test_upsert_sql_contains_on_duplicate(self):
        """La requete SQL contient ON DUPLICATE KEY UPDATE (MySQL upsert)."""
        client, mock_db = _get_client_and_mock()

        captured_sql = []

        async def capture_query(sql, params=None):
            captured_sql.append(sql)
            return []
        mock_db.async_query = capture_query

        resp = client.post("/api/rating", json={
            "source": "chatbot_loto",
            "rating": 5,
            "session_id": "sess_test_001_abcdef",
        })

        assert resp.status_code == 200
        assert len(captured_sql) == 1
        assert "ON DUPLICATE KEY UPDATE" in captured_sql[0]
