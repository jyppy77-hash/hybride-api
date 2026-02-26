"""
Cache async avec Redis (partage entre instances) + fallback dict in-memory.
Compatible Memorystore, Redis Cloud, ou tout Redis >= 6.

Interface : await cache_get(key), await cache_set(key, value, ttl), await cache_clear()
Lifecycle : init_cache() au startup, close_cache() au shutdown.
"""

import logging
import os
import pickle
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TTL = 3600  # 1 heure

# ── In-memory fallback ──────────────────────────────────────────────
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
                return pickle.loads(data)
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


async def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Stocke une valeur avec un TTL en secondes."""
    # Redis
    if _redis:
        try:
            await _redis.set(f"{_REDIS_PREFIX}{key}", pickle.dumps(value), ex=ttl)
            return
        except Exception as e:
            logger.warning(f"Redis SET error ({e}) — fallback in-memory")

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
