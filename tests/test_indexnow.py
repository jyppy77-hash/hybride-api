"""
Tests IndexNow integration — V97.
Route verification key, service submit, admin endpoint, URL collection.
"""

import os
from contextlib import asynccontextmanager
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# ── Patches applied BEFORE main.py import ───────────────────────────

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake",
    "DB_USER": "test",
    "DB_NAME": "testdb",
})


def _get_client():
    with _db_env, _static_patch, _static_call:
        import importlib
        import routes.admin_helpers as admin_helpers_mod
        importlib.reload(admin_helpers_mod)
        import routes.admin_monitoring as admin_monitoring_mod
        importlib.reload(admin_monitoring_mod)
        import routes.admin as admin_mod
        importlib.reload(admin_mod)
        import main
        importlib.reload(main)
        # Reset rate limiter to avoid 429 across tests
        import rate_limit as rl_mod
        rl_mod.limiter.reset()
        rl_mod._api_hits.clear()
        return TestClient(main.app, raise_server_exceptions=False)


# ══════════════════════════════════════════════════════════════════════════════
# Chantier 1 — Route verification key
# ══════════════════════════════════════════════════════════════════════════════


def test_indexnow_key_route_returns_key():
    """GET /<key>.txt → 200 text/plain with key content."""
    client = _get_client()
    from services.indexnow import INDEXNOW_KEY
    if not INDEXNOW_KEY:
        pytest.skip("No IndexNow key detected")
    resp = client.get(f"/{INDEXNOW_KEY}.txt")
    assert resp.status_code == 200
    assert resp.text == INDEXNOW_KEY
    assert "text/plain" in resp.headers.get("content-type", "")


def test_indexnow_fake_txt_returns_404():
    """GET /fake_key.txt → 404 (no catch-all .txt route)."""
    client = _get_client()
    resp = client.get("/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.txt")
    assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# Chantier 2 — Service indexnow.py
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_submit_indexnow_success():
    """submit_indexnow() with mock 200 response."""
    from services.indexnow import submit_indexnow, INDEXNOW_KEY
    if not INDEXNOW_KEY:
        pytest.skip("No IndexNow key detected")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    result = await submit_indexnow(["https://lotoia.fr/accueil"], client=mock_client)
    assert result["status"] == 200
    assert result["submitted"] == 1
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_submit_indexnow_202_accepted():
    """IndexNow returns 202 (accepted) — still success."""
    from services.indexnow import submit_indexnow, INDEXNOW_KEY
    if not INDEXNOW_KEY:
        pytest.skip("No IndexNow key detected")

    mock_resp = MagicMock()
    mock_resp.status_code = 202

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    result = await submit_indexnow(
        ["https://lotoia.fr/accueil", "https://lotoia.fr/loto"],
        client=mock_client,
    )
    assert result["status"] == 202
    assert result["submitted"] == 2


@pytest.mark.asyncio
async def test_submit_indexnow_timeout():
    """submit_indexnow() handles timeout gracefully."""
    import httpx
    from services.indexnow import submit_indexnow, INDEXNOW_KEY
    if not INDEXNOW_KEY:
        pytest.skip("No IndexNow key detected")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    result = await submit_indexnow(["https://lotoia.fr/accueil"], client=mock_client)
    assert result["status"] == "timeout"
    assert result["submitted"] == 0


@pytest.mark.asyncio
async def test_submit_indexnow_http_error():
    """submit_indexnow() handles HTTP 403 error."""
    from services.indexnow import submit_indexnow, INDEXNOW_KEY
    if not INDEXNOW_KEY:
        pytest.skip("No IndexNow key detected")

    mock_resp = MagicMock()
    mock_resp.status_code = 403

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    result = await submit_indexnow(["https://lotoia.fr/accueil"], client=mock_client)
    assert result["status"] == 403
    assert result["submitted"] == 1


@pytest.mark.asyncio
async def test_submit_indexnow_network_error():
    """submit_indexnow() handles network error gracefully."""
    from services.indexnow import submit_indexnow, INDEXNOW_KEY
    if not INDEXNOW_KEY:
        pytest.skip("No IndexNow key detected")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=ConnectionError("network down"))

    result = await submit_indexnow(["https://lotoia.fr/accueil"], client=mock_client)
    assert result["status"] == "error"
    assert "detail" in result


@pytest.mark.asyncio
async def test_submit_indexnow_empty_urls():
    """submit_indexnow() with empty list → no API call."""
    from services.indexnow import submit_indexnow
    result = await submit_indexnow([])
    assert result["status"] == "empty"
    assert result["submitted"] == 0


@pytest.mark.asyncio
async def test_submit_all_sitemap_urls():
    """submit_all_sitemap_urls() collects URLs and submits them."""
    from services.indexnow import submit_all_sitemap_urls, collect_all_urls, INDEXNOW_KEY
    if not INDEXNOW_KEY:
        pytest.skip("No IndexNow key detected")

    all_urls = collect_all_urls()
    assert len(all_urls) > 50  # sanity check — sitemap has ~98 URLs

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    result = await submit_all_sitemap_urls(client=mock_client)
    assert result["status"] == 200
    assert result["submitted"] == len(all_urls)

    # Verify the payload sent to IndexNow
    call_kwargs = mock_client.post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert payload["host"] == "lotoia.fr"
    assert payload["key"] == INDEXNOW_KEY
    assert len(payload["urlList"]) == len(all_urls)


def test_collect_all_urls_structure():
    """collect_all_urls() returns valid https URLs."""
    from services.indexnow import collect_all_urls
    urls = collect_all_urls()
    assert len(urls) > 0
    for url in urls:
        assert url.startswith("https://lotoia.fr/"), f"Invalid URL: {url}"
    # No duplicates
    assert len(urls) == len(set(urls))


# ══════════════════════════════════════════════════════════════════════════════
# Chantier 3 — Admin route
# ══════════════════════════════════════════════════════════════════════════════


class TestAdminIndexNow:
    """Admin IndexNow endpoint tests — uses single client to manage rate limits."""

    @classmethod
    def setup_class(cls):
        cls.client = _get_client()

    def setup_method(self):
        """Reset rate limiter before each test method."""
        import rate_limit as rl_mod
        rl_mod.limiter.reset()
        rl_mod._api_hits.clear()
        # Clear slowapi internal MemoryStorage dict (survives module reload)
        rl_mod.limiter._storage.storage.clear()
        rl_mod.limiter._storage.expirations.clear()
        rl_mod.limiter._storage.events.clear()

    def test_submit_requires_auth(self):
        """POST /admin/api/indexnow/submit without auth → 401."""
        resp = self.client.post("/admin/api/indexnow/submit", json={})
        assert resp.status_code in (401, 403, 302, 307)

    def test_submit_with_auth(self):
        """POST /admin/api/indexnow/submit with valid auth → 200."""
        from services.indexnow import INDEXNOW_KEY
        if not INDEXNOW_KEY:
            pytest.skip("No IndexNow key detected")

        with patch("services.indexnow.submit_all_sitemap_urls", new_callable=AsyncMock) as mock_submit, \
             patch("routes.admin_helpers.is_authenticated", return_value=True):
            mock_submit.return_value = {"status": 200, "submitted": 98}
            resp = self.client.post("/admin/api/indexnow/submit", json={})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["submitted"] == 98

    def test_submit_custom_urls(self):
        """POST /admin/api/indexnow/submit with custom URLs."""
        from services.indexnow import INDEXNOW_KEY
        if not INDEXNOW_KEY:
            pytest.skip("No IndexNow key detected")

        with patch("services.indexnow.submit_indexnow", new_callable=AsyncMock) as mock_submit, \
             patch("routes.admin_helpers.is_authenticated", return_value=True):
            mock_submit.return_value = {"status": 200, "submitted": 2}
            resp = self.client.post("/admin/api/indexnow/submit", json={
                "urls": ["https://lotoia.fr/accueil", "https://lotoia.fr/loto"]
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["submitted"] == 2

    def test_submit_invalid_urls(self):
        """POST /admin/api/indexnow/submit with invalid URLs → 400."""
        from services.indexnow import INDEXNOW_KEY
        if not INDEXNOW_KEY:
            pytest.skip("No IndexNow key detected")

        with patch("routes.admin_helpers.is_authenticated", return_value=True):
            resp = self.client.post("/admin/api/indexnow/submit", json={
                "urls": ["http://evil.com", "not-a-url"]
            })
            assert resp.status_code == 400
