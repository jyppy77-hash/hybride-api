"""1.6.055 GO 1 — garde-fou conftest : aucun appel réel Vertex / DB pendant pytest.

Chaque test qui déclenche volontairement le garde-fou vide `real_call_attempts`
avant de finir, pour ne pas échouer au teardown.
"""

import asyncio
from unittest.mock import patch

import pytest


def _run_isolated(coro):
    """Boucle dédiée, jamais déclarée boucle courante : contrairement à asyncio.run(),
    ne remet pas à zéro la boucle courante dont dépendent d'autres fichiers
    (asyncio.get_event_loop().run_until_complete)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_guard_blocks_vertex_client(real_call_attempts):
    import services.gemini_shared as gs
    gs._CLIENT = None
    with pytest.raises(RuntimeError, match=r"google\.genai\.Client"):
        gs._get_client()
    assert gs._CLIENT is None
    assert real_call_attempts == ["google.genai.Client"]
    real_call_attempts.clear()


def test_guard_blocks_create_pool(real_call_attempts):
    import db_cloudsql
    with patch.object(db_cloudsql, "_pool", None), \
         patch.object(db_cloudsql, "DB_PASSWORD", "fake-not-a-secret"):
        with pytest.raises(RuntimeError, match=r"aiomysql\.create_pool"):
            _run_isolated(db_cloudsql.init_pool())
        assert db_cloudsql._pool is None
    assert real_call_attempts == ["aiomysql.create_pool"]
    real_call_attempts.clear()


def test_guard_blocks_aiomysql_connect(real_call_attempts):
    import aiomysql
    with pytest.raises(RuntimeError, match=r"aiomysql\.connect"):
        aiomysql.connect(host="127.0.0.1", port=3306)
    assert real_call_attempts == ["aiomysql.connect"]
    real_call_attempts.clear()


def test_guard_detects_swallowed_call(real_call_attempts):
    """Exception avalée (pattern `except Exception` du code de prod) : tentative quand même enregistrée."""
    import services.gemini_shared as gs
    gs._CLIENT = None
    try:
        gs._get_client()
    except Exception:
        pass
    assert real_call_attempts == ["google.genai.Client"]
    real_call_attempts.clear()


def test_mock_vertex_client_still_works(mock_vertex_client, real_call_attempts):
    import services.gemini_shared as gs
    with mock_vertex_client() as vc:
        assert gs._get_client() is vc.client
    assert real_call_attempts == []


def test_inner_patch_still_wins(real_call_attempts):
    """Un patch posé dans le test (pattern test_db_pool) reste prioritaire sur le garde-fou."""
    import aiomysql
    sentinel = object()

    async def _fake_create_pool(**kwargs):
        return sentinel

    with patch("aiomysql.create_pool", _fake_create_pool):
        assert _run_isolated(aiomysql.create_pool()) is sentinel
    assert real_call_attempts == []
