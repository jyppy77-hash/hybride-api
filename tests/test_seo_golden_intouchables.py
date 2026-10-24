"""
T9 — Golden <head> SEO des pages intouchables (lot redirection, 24/10/2026).

Instantané capturé sur f7ce5d6 (1.6.058) AVANT toute modification du lot :
title, meta description, canonical, hreflang et JSON-LD de /accueil, /loto et
/euromillions/generateur. Tout écart = régression SEO sur une page intouchable.

Références externes /accueil (balise complète) :
  title 094f295af9f51122435e843b8b11578d / meta aec9d0400b333ea1b45b081afb6cd7cc.
JSON-LD hashé après normalisation \r\n → \n (sources en LF, garde-fou CRLF).
/accueil : DB mockée (ratings < 5) → bloc AggregateRating retiré, chemin déterministe.
"""
import hashlib
import os
import re
from contextlib import asynccontextmanager
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})


def _async_cm_conn(cursor):
    @asynccontextmanager
    async def _cm():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn
    return _cm


def _make_cursor():
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=None)
    cursor.fetchall = AsyncMock(return_value=[])
    cursor.close = AsyncMock()
    return cursor


def _get(path):
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
    with patch("db_cloudsql.get_connection", _async_cm_conn(_make_cursor())):
        return client.get(path)


def _md5(text: str) -> str:
    return hashlib.md5(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _head(html: str) -> str:
    return html.split("</head>", 1)[0]


_GOLDEN = {
    "/accueil": {
        "title_md5": "094f295af9f51122435e843b8b11578d",
        "meta_md5": "aec9d0400b333ea1b45b081afb6cd7cc",
        "canonical": "https://lotoia.fr/accueil",
        "hreflang": [
            ("fr", "https://lotoia.fr/accueil"),
            ("x-default", "https://lotoia.fr/accueil"),
        ],
        "jsonld_md5": [
            "8ad1946d8803438930633557e268cc80",
            "f7be305a4fcc1acd54d9e25773281ceb",
            "221196693f7094535070b013f0c99509",
        ],
    },
    "/loto": {
        "title_md5": "26bd8b25a06deea62821146a0f03dc2e",
        "meta_md5": "02c9a22662ec628993b91588b8e56344",
        "canonical": "https://lotoia.fr/loto",
        "hreflang": [
            ("fr", "https://lotoia.fr/loto"),
            ("x-default", "https://lotoia.fr/loto"),
        ],
        "jsonld_md5": [
            "43f3156f74b6d4cdeb745783dfd8169e",
            "8d3d578d10029a780d45cd19b15aca6f",
        ],
    },
    "/euromillions/generateur": {
        "title_md5": "ddddd5e703058125a73096ca9c2ec1dc",
        "meta_md5": "6883e7e5b40b6e02602d0a677e475ac8",
        "canonical": "https://lotoia.fr/euromillions/generateur",
        "hreflang": [
            ("fr", "https://lotoia.fr/euromillions/generateur"),
            ("en", "https://lotoia.fr/en/euromillions/generator"),
            ("es", "https://lotoia.fr/es/euromillions/generador"),
            ("pt", "https://lotoia.fr/pt/euromillions/gerador"),
            ("de", "https://lotoia.fr/de/euromillions/generator"),
            ("nl", "https://lotoia.fr/nl/euromillions/generator"),
            ("x-default", "https://lotoia.fr/euromillions/generateur"),
        ],
        "jsonld_md5": [
            "b4ac7456864e781214f7beb823de8400",
            "b811e7685c4476887a2dd0ba600fba3a",
        ],
    },
}

_PATHS = list(_GOLDEN)


@pytest.fixture(scope="module")
def heads():
    out = {}
    for path in _PATHS:
        resp = _get(path)
        assert resp.status_code == 200, f"{path}: HTTP {resp.status_code}"
        out[path] = _head(resp.text)
    return out


class TestGoldenIntouchables:
    """T9 — <head> SEO strictement identique à l'instantané d'avant lot."""

    @pytest.mark.parametrize("path", _PATHS)
    def test_title_tag_unchanged(self, heads, path):
        title = re.search(r"<title>.*?</title>", heads[path], re.S).group(0)
        assert _md5(title) == _GOLDEN[path]["title_md5"], f"{path}: <title> modifié"

    @pytest.mark.parametrize("path", _PATHS)
    def test_meta_description_tag_unchanged(self, heads, path):
        meta = re.search(r'<meta name="description"[^>]*>', heads[path]).group(0)
        assert _md5(meta) == _GOLDEN[path]["meta_md5"], f"{path}: meta description modifiée"

    @pytest.mark.parametrize("path", _PATHS)
    def test_canonical_unchanged(self, heads, path):
        canonicals = re.findall(r'<link rel="canonical" href="([^"]+)"', heads[path])
        assert canonicals == [_GOLDEN[path]["canonical"]], f"{path}: canonical modifié"

    @pytest.mark.parametrize("path", _PATHS)
    def test_hreflang_unchanged(self, heads, path):
        tags = re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', heads[path])
        assert tags == _GOLDEN[path]["hreflang"], f"{path}: hreflang modifiés"

    @pytest.mark.parametrize("path", _PATHS)
    def test_jsonld_unchanged(self, heads, path):
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', heads[path], re.S)
        assert [_md5(b) for b in blocks] == _GOLDEN[path]["jsonld_md5"], f"{path}: JSON-LD modifié"
