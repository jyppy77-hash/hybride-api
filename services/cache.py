"""
Cache en memoire avec TTL — evite les appels BDD repetitifs.
Thread-safe grace au GIL CPython (dict ops atomiques).
"""

import time
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}

DEFAULT_TTL = 3600  # 1 heure


def cache_get(key: str) -> Any | None:
    """Retourne la valeur si presente et non expiree, sinon None."""
    entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() > expires_at:
        _cache.pop(key, None)
        return None
    return value


def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Stocke une valeur avec un TTL en secondes."""
    _cache[key] = (time.monotonic() + ttl, value)


def cache_clear() -> None:
    """Vide tout le cache (utile pour les tests)."""
    _cache.clear()
