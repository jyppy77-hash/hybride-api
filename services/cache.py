"""
Cache async avec Redis (partage entre instances) + fallback dict in-memory.
Compatible Memorystore, Redis Cloud, ou tout Redis >= 6.

Interface : await cache_get(key), await cache_set(key, value, ttl), await cache_clear()
Lifecycle : init_cache() au startup, close_cache() au shutdown.
"""

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TTL = 3600  # 1 heure

# ── In-memory fallback (I04 V66: bounded to prevent OOM) ──────────
_MEM_CACHE_MAXSIZE = 10_000
_mem_cache: dict[str, tuple[float, Any]] = {}

# ── Redis client ────────────────────────────────────────────────────
_redis = None

_REDIS_PREFIX = "hybride:"


async def init_cache():
    """Initialise la connexion Redis. Fallback in-memory si indisponible."""
    global _redis
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.info("REDIS_URL non defini — cache in-memory (fallback)")
        return

    if not redis_url.startswith("rediss://") and os.getenv("K_SERVICE"):
        # GCP VPC internal traffic is encrypted at the network layer by default,
        # but TLS on the Redis link (rediss://) is recommended as defense-in-depth.
        logger.error("[CACHE] Redis URL does not use TLS (rediss://). Data transits unencrypted on the Redis link.")

    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(
            redis_url,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        await _redis.ping()
        # Masquer le mot de passe dans les logs
        safe_url = redis_url.split("@")[-1] if "@" in redis_url else redis_url
        logger.info(f"Cache Redis connecte: {safe_url}")
    except Exception as e:
        logger.warning(f"Redis indisponible ({e}) — fallback in-memory")
        _redis = None


async def close_cache():
    """Ferme la connexion Redis."""
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        logger.info("Cache Redis ferme")


async def cache_get(key: str) -> Any | None:
    """Retourne la valeur si presente et non expiree, sinon None."""
    # Redis
    if _redis:
        try:
            data = await _redis.get(f"{_REDIS_PREFIX}{key}")
            if data is not None:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning(f"Redis GET error ({e}) — fallback in-memory")

    # Fallback in-memory
    entry = _mem_cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() > expires_at:
        _mem_cache.pop(key, None)
        return None
    return value


def _evict_mem_cache() -> None:
    """I04 V66: Evict entries when in-memory cache reaches maxsize.

    Strategy: 1) purge expired entries first, 2) if still full, remove oldest 20% (FIFO).
    """
    now = time.monotonic()
    expired = [k for k, (expires_at, _) in _mem_cache.items() if expires_at < now]
    for k in expired:
        del _mem_cache[k]
    if len(_mem_cache) < _MEM_CACHE_MAXSIZE:
        return
    # Still full — FIFO eviction: remove 20% oldest by expiry timestamp
    to_remove = sorted(_mem_cache, key=lambda k: _mem_cache[k][0])[:len(_mem_cache) // 5 or 1]
    for k in to_remove:
        del _mem_cache[k]
    logger.warning("[CACHE] In-memory eviction triggered: %d entries removed", len(expired) + len(to_remove))


async def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Stocke une valeur avec un TTL en secondes."""
    # Redis
    if _redis:
        try:
            await _redis.set(f"{_REDIS_PREFIX}{key}", json.dumps(value), ex=ttl)
            return
        except Exception as e:
            logger.warning(f"Redis SET error ({e}) — fallback in-memory")

    # I04 V66: Evict before writing if at capacity
    if len(_mem_cache) >= _MEM_CACHE_MAXSIZE:
        _evict_mem_cache()

    # Fallback in-memory
    _mem_cache[key] = (time.monotonic() + ttl, value)


async def cache_clear() -> None:
    """Vide tout le cache."""
    if _redis:
        try:
            cursor = 0
            while True:
                cursor, keys = await _redis.scan(
                    cursor, match=f"{_REDIS_PREFIX}*", count=100
                )
                if keys:
                    await _redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(f"Redis CLEAR error: {e}")

    _mem_cache.clear()
