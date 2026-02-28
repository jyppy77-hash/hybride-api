"""
Tests unitaires pour les routes FastAPI.
Utilise TestClient + mocks complets (BDD, Gemini, fichiers).
Aucune connexion MySQL ni API Gemini requise.
"""

import os
import json
from contextlib import asynccontextmanager
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import date

import pytest
from fastapi.testclient import TestClient


def _async_cm_conn(cursor):
    """Retourne un callable qui produit un async context manager (simule get_connection)."""
    @asynccontextmanager
    async def _cm():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn
    return _cm


# ── Patches appliques AVANT l'import de main.py ───────────────────────

# Empecher le mount StaticFiles de planter (dossier ui/ absent en CI)
_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)

# Empecher db_cloudsql de lire .env / tenter une connexion a l'import
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake",
    "DB_USER": "test",
    "DB_NAME": "testdb",
})


def _get_client():
    """Cree un TestClient frais avec tous les patches actifs."""
    with _db_module_patch, _static_patch, _static_call:
        # Re-import pour appliquer les patches
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════════════════

@patch("main.db_cloudsql")
def test_health_db_ok(mock_db):
    """GET /health retourne status ok + tous les champs ameliores."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        main_mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert data["gemini"] in ("ok", "circuit_open")
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], int)
    assert "version" in data
    assert "engine" in data


@patch("main.db_cloudsql")
def test_health_db_down(mock_db):
    """GET /health retourne status degraded quand BDD inaccessible."""
    mock_db.get_connection.side_effect = Exception("Connection refused")

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        main_mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["database"] == "unreachable"
    assert "gemini" in data
    assert "uptime_seconds" in data


# ═══════════════════════════════════════════════════════════════════════
# Tirages
# ═══════════════════════════════════════════════════════════════════════

@patch("routes.api_data_unified.db_cloudsql")
def test_tirages_count(mock_db):
    """GET /api/tirages/count retourne un nombre."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchone.return_value = {"total": 967}

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        import routes.api_data_unified as unified_mod
        unified_mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/tirages/count")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 967


@patch("routes.api_data_unified.db_cloudsql")
def test_tirages_latest(mock_db):
    """GET /api/tirages/latest retourne un tirage."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)
    cursor.fetchone.return_value = {
        "date_de_tirage": date(2026, 2, 3),
        "boule_1": 5, "boule_2": 12, "boule_3": 23,
        "boule_4": 34, "boule_5": 45, "numero_chance": 7,
    }

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        import routes.api_data_unified as unified_mod
        unified_mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/tirages/latest")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "boule_1" in data["data"]


# ═══════════════════════════════════════════════════════════════════════
# Stats number
# ═══════════════════════════════════════════════════════════════════════

@patch("routes.api_data_unified.db_cloudsql")
def test_stats_number_valid(mock_db):
    """GET /api/stats/number/7 retourne des stats."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)

    cursor.fetchall.side_effect = [
        # appearances du numero 7
        [
            {"date_de_tirage": date(2020, 3, 14)},
            {"date_de_tirage": date(2024, 11, 2)},
        ],
    ]
    cursor.fetchone.side_effect = [
        {"gap": 5},   # ecart
    ]

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        import routes.api_data_unified as unified_mod
        unified_mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/stats/number/7")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["number"] == 7
    assert "total_appearances" in data


def test_stats_number_invalid():
    """GET /api/stats/number/99 retourne 400."""
    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.get("/api/stats/number/99")

    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False


# ═══════════════════════════════════════════════════════════════════════
# Hybride Chat (mock Gemini)
# ═══════════════════════════════════════════════════════════════════════

@patch("services.chat_pipeline.stream_gemini_chat")
@patch("services.chat_pipeline.load_prompt", return_value="Tu es un assistant.")
@patch.dict(os.environ, {"GEM_API_KEY": "fake-key"})
def test_hybride_chat(mock_prompt, mock_stream):
    """POST /api/hybride-chat retourne des events SSE (mock Gemini stream)."""
    async def fake_gen(*a, **kw):
        yield "Voici ma reponse test."

    mock_stream.side_effect = lambda *a, **kw: fake_gen()

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)

        import httpx
        mock_client = MagicMock(spec=httpx.AsyncClient)
        main_mod.app.state.httpx_client = mock_client

        resp = client.post("/api/hybride-chat", json={
            "message": "Bonjour, quels numeros jouer ?",
            "page": "accueil",
        })

    assert resp.status_code == 200
    # Parse SSE events
    events = []
    for block in resp.text.strip().split("\n\n"):
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    done_events = [e for e in events if e.get("is_done")]
    assert len(done_events) >= 1
    chunks = [e["chunk"] for e in events if e.get("chunk")]
    assert "Voici ma reponse test." in "".join(chunks)
    assert done_events[-1]["source"] == "gemini"


# ═══════════════════════════════════════════════════════════════════════
# Rate Limiting
# ═══════════════════════════════════════════════════════════════════════

@patch("services.chat_pipeline.stream_gemini_chat")
@patch("services.chat_pipeline.load_prompt", return_value="Tu es un assistant.")
@patch.dict(os.environ, {"GEM_API_KEY": "fake-key"})
def test_rate_limit_429(mock_prompt, mock_stream):
    """Envoyer 15 requetes rapides sur /api/hybride-chat → 429."""
    async def fake_gen(*a, **kw):
        yield "Reponse."

    mock_stream.side_effect = lambda *a, **kw: fake_gen()

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)

        import httpx
        mock_client = MagicMock(spec=httpx.AsyncClient)
        main_mod.app.state.httpx_client = mock_client

        got_429 = False
        for i in range(15):
            resp = client.post("/api/hybride-chat", json={
                "message": f"Test {i}",
                "page": "accueil",
            })
            if resp.status_code == 429:
                got_429 = True
                break

    assert got_429, "Attendu un 429 apres 10+ requetes rapides (limite 10/min)"


# ═══════════════════════════════════════════════════════════════════════
# Correlation ID
# ═══════════════════════════════════════════════════════════════════════

@patch("main.db_cloudsql")
def test_correlation_id_generated(mock_db):
    """Chaque reponse contient un header X-Request-ID unique."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        main_mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)

        resp1 = client.get("/health")
        resp2 = client.get("/health")

    rid1 = resp1.headers.get("x-request-id")
    rid2 = resp2.headers.get("x-request-id")

    assert rid1 is not None
    assert rid2 is not None
    assert len(rid1) == 16
    assert rid1 != rid2


@patch("main.db_cloudsql")
def test_correlation_id_forwarded(mock_db):
    """Si le client envoie X-Request-ID, il est reutilise."""
    cursor = AsyncMock()
    mock_db.get_connection = _async_cm_conn(cursor)

    with _db_module_patch, _static_patch, _static_call:
        import importlib, main as main_mod
        importlib.reload(main_mod)
        main_mod.db_cloudsql = mock_db
        client = TestClient(main_mod.app, raise_server_exceptions=False)

        resp = client.get("/health", headers={"x-request-id": "my-custom-id-123"})

    assert resp.headers.get("x-request-id") == "my-custom-id-123"
