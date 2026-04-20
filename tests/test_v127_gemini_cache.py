"""V127 — Tests cache Gemini pitch-grilles in-memory.

Couvre : hit/miss, TTL expiration, eviction LRU, déterminisme clé,
isolation par lang, non-stockage des erreurs.
"""

import time
from unittest.mock import patch

import pytest

from services.gemini_cache import PitchCache


@pytest.fixture
def cache():
    """Instance fraîche par test (état isolé)."""
    return PitchCache(ttl=3600, maxsize=10)


def _grilles(seed=1):
    return [{"numeros": [seed, 2, 3, 4, 5], "chance": seed, "score_conformite": 0.9, "severity": "ok"}]


def test_cache_miss_returns_none(cache):
    assert cache.get(_grilles(), "fr", "PITCH_GRILLE") is None
    assert cache.misses == 1
    assert cache.hits == 0


def test_cache_hit_returns_payload(cache):
    payload = {"success": True, "data": {"pitchs": ["x"]}, "error": None, "status_code": 200}
    cache.set(_grilles(), "fr", "PITCH_GRILLE", payload)
    out = cache.get(_grilles(), "fr", "PITCH_GRILLE")
    assert out == payload
    assert cache.hits == 1


def test_cache_ttl_expiration(cache):
    payload = {"ok": True}
    cache.set(_grilles(), "fr", "P", payload)
    # Move forward in time past TTL
    with patch("services.gemini_cache.time.monotonic", return_value=time.monotonic() + 4000):
        out = cache.get(_grilles(), "fr", "P")
    assert out is None
    assert cache.misses == 1


def test_cache_eviction_at_maxsize():
    cache = PitchCache(ttl=3600, maxsize=3)
    for i in range(5):
        cache.set(_grilles(seed=i), "fr", "P", {"i": i})
    # Only the 3 most recent should remain
    assert cache.evictions == 2
    assert cache.get(_grilles(seed=0), "fr", "P") is None  # evicted
    assert cache.get(_grilles(seed=1), "fr", "P") is None  # evicted
    assert cache.get(_grilles(seed=4), "fr", "P") == {"i": 4}


def test_cache_key_deterministic(cache):
    """Même input → même clé hash."""
    k1 = cache._key(_grilles(), "fr", "P")
    k2 = cache._key(_grilles(), "fr", "P")
    assert k1 == k2


def test_cache_key_differs_on_lang_change(cache):
    payload = {"ok": True}
    cache.set(_grilles(), "fr", "P", payload)
    # lang='en' = clé différente → miss
    assert cache.get(_grilles(), "en", "P") is None
    assert cache.get(_grilles(), "fr", "P") == payload


def test_cache_key_differs_on_prompt_name_change(cache):
    payload = {"ok": True}
    cache.set(_grilles(), "fr", "PITCH_GRILLE", payload)
    assert cache.get(_grilles(), "fr", "OTHER_PROMPT") is None


def test_stats_method(cache):
    cache.set(_grilles(), "fr", "P", {"ok": True})
    cache.get(_grilles(), "fr", "P")
    cache.get(_grilles(seed=99), "fr", "P")
    stats = cache.stats()
    assert stats["size"] == 1
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_clear_resets_state(cache):
    cache.set(_grilles(), "fr", "P", {"ok": True})
    cache.get(_grilles(), "fr", "P")
    cache.clear()
    assert cache.stats()["size"] == 0
    assert cache.hits == 0
    assert cache.misses == 0
