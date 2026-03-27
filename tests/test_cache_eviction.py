"""
Tests unitaires pour services/cache.py — I04 V66: cache in-memory borné.
"""

import time
from unittest.mock import patch

import pytest

from services.cache import (
    cache_get, cache_set, cache_clear,
    _mem_cache, _MEM_CACHE_MAXSIZE, _evict_mem_cache,
)


# ═══════════════════════════════════════════════════════════════════════
# I04 V66: In-memory cache eviction
# ═══════════════════════════════════════════════════════════════════════

class TestCacheEviction:

    @pytest.mark.asyncio
    async def test_maxsize_constant(self):
        """_MEM_CACHE_MAXSIZE should be 10000."""
        assert _MEM_CACHE_MAXSIZE == 10_000

    @pytest.mark.asyncio
    async def test_under_maxsize_no_eviction(self):
        """Cache below maxsize — no eviction, writes work normally."""
        await cache_clear()
        await cache_set("key_a", "value_a", ttl=3600)
        await cache_set("key_b", "value_b", ttl=3600)
        assert await cache_get("key_a") == "value_a"
        assert await cache_get("key_b") == "value_b"
        await cache_clear()

    @pytest.mark.asyncio
    async def test_evict_expired_first(self):
        """When at maxsize, expired entries are purged first."""
        await cache_clear()

        # Fill cache to maxsize with expired entries
        now = time.monotonic()
        for i in range(_MEM_CACHE_MAXSIZE):
            _mem_cache[f"expired_{i}"] = (now - 1, f"val_{i}")  # Already expired

        assert len(_mem_cache) == _MEM_CACHE_MAXSIZE

        # This write should trigger eviction — expired entries purged
        await cache_set("new_key", "new_value", ttl=3600)

        # All expired entries should be gone, only the new one remains
        assert len(_mem_cache) == 1
        assert await cache_get("new_key") == "new_value"
        await cache_clear()

    @pytest.mark.asyncio
    async def test_evict_fifo_when_no_expired(self):
        """When at maxsize with no expired entries, remove oldest 20%."""
        await cache_clear()

        # Fill cache to maxsize with non-expired entries (ascending timestamps)
        base_time = time.monotonic()
        for i in range(_MEM_CACHE_MAXSIZE):
            _mem_cache[f"live_{i}"] = (base_time + 3600 + i, f"val_{i}")

        assert len(_mem_cache) == _MEM_CACHE_MAXSIZE

        # Trigger eviction
        await cache_set("new_after_evict", "value", ttl=3600)

        # 20% oldest should have been removed (2000 entries)
        expected_max = _MEM_CACHE_MAXSIZE - (_MEM_CACHE_MAXSIZE // 5) + 1
        assert len(_mem_cache) <= expected_max
        assert await cache_get("new_after_evict") == "value"

        # The oldest entries (lowest timestamps = lowest indices) should be gone
        assert _mem_cache.get("live_0") is None
        assert _mem_cache.get("live_1") is None

        await cache_clear()

    @pytest.mark.asyncio
    async def test_after_eviction_writes_work(self):
        """After eviction, subsequent writes succeed."""
        await cache_clear()

        now = time.monotonic()
        for i in range(_MEM_CACHE_MAXSIZE):
            _mem_cache[f"temp_{i}"] = (now - 1, "expired")

        # First write triggers eviction
        await cache_set("post_evict_1", "a", ttl=3600)
        # Second write should work without issues
        await cache_set("post_evict_2", "b", ttl=3600)

        assert await cache_get("post_evict_1") == "a"
        assert await cache_get("post_evict_2") == "b"
        await cache_clear()


class TestEvictMemCacheDirect:

    def test_evict_removes_expired(self):
        """_evict_mem_cache purges expired entries."""
        _mem_cache.clear()
        now = time.monotonic()
        _mem_cache["old"] = (now - 10, "expired")
        _mem_cache["fresh"] = (now + 3600, "alive")
        _evict_mem_cache()
        assert "old" not in _mem_cache
        assert "fresh" in _mem_cache

    def test_evict_fifo_oldest_20pct(self):
        """_evict_mem_cache removes 20% oldest when all entries are live."""
        _mem_cache.clear()
        base = time.monotonic() + 3600
        for i in range(100):
            _mem_cache[f"k{i}"] = (base + i, f"v{i}")

        # Force eviction (pretend we are at maxsize)
        with patch('services.cache._MEM_CACHE_MAXSIZE', 100):
            _evict_mem_cache()

        # 20 entries should have been removed (20% of 100)
        assert len(_mem_cache) == 80
        # Oldest (lowest index) should be gone
        assert "k0" not in _mem_cache
        assert "k19" not in _mem_cache
        # Newest should remain
        assert "k99" in _mem_cache
        assert "k80" in _mem_cache
        _mem_cache.clear()

    def test_evict_logs_warning(self):
        """_evict_mem_cache logs a warning when eviction happens."""
        _mem_cache.clear()
        base = time.monotonic() + 3600
        for i in range(10):
            _mem_cache[f"k{i}"] = (base + i, f"v{i}")

        with patch('services.cache._MEM_CACHE_MAXSIZE', 10):
            with patch('services.cache.logger') as mock_logger:
                _evict_mem_cache()
                mock_logger.warning.assert_called_once()
                assert "eviction" in mock_logger.warning.call_args[0][0].lower()
        _mem_cache.clear()
