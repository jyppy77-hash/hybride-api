"""
V127 — In-memory TTL cache pour réponses Gemini pitch-grilles.

Évite les appels Gemini répétés sur grilles + lang + prompt identiques.
Bornes : TTL 24h, max 1000 entrées (FIFO/LRU eviction via OrderedDict).
Metrics : hits / misses / evictions loggés via logger.info "[V127_PITCH_CACHE]".

Audit V126.1 : impact attendu -30 à -50% appels Gemini sur pitch.
Cache in-memory only (pas Redis pour V127 — V128 si Redis provisionné).
"""

import hashlib
import json
import logging
import time
from collections import OrderedDict
from threading import Lock

logger = logging.getLogger(__name__)

_TTL_SECONDS = 24 * 3600  # 24h (audit V126.1 décision 2)
_MAX_ENTRIES = 1000        # ~500 KB total (audit V126.1 décision 3)


class PitchCache:
    """OrderedDict-backed LRU cache avec TTL absolu par entrée.

    Thread-safe via Lock (Cloud Run = single asyncio loop, mais on garde la
    garantie pour cas multi-worker éventuel V128+).
    """

    def __init__(self, ttl: int = _TTL_SECONDS, maxsize: int = _MAX_ENTRIES):
        self._store: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._ttl = ttl
        self._maxsize = maxsize
        self._lock = Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    @staticmethod
    def _key(grilles_data, lang: str, prompt_name: str) -> str:
        payload = json.dumps(
            {"g": grilles_data, "l": lang, "p": prompt_name},
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, grilles_data, lang: str, prompt_name: str) -> dict | None:
        k = self._key(grilles_data, lang, prompt_name)
        with self._lock:
            entry = self._store.get(k)
            if not entry:
                self.misses += 1
                return None
            ts, payload = entry
            if time.monotonic() - ts > self._ttl:
                self._store.pop(k, None)
                self.misses += 1
                return None
            self._store.move_to_end(k)
            self.hits += 1
        logger.info(
            "[V127_PITCH_CACHE] HIT key=%s hits=%d misses=%d size=%d",
            k[:8], self.hits, self.misses, len(self._store),
        )
        return payload

    def set(self, grilles_data, lang: str, prompt_name: str, payload: dict) -> None:
        k = self._key(grilles_data, lang, prompt_name)
        with self._lock:
            self._store[k] = (time.monotonic(), payload)
            self._store.move_to_end(k)
            while len(self._store) > self._maxsize:
                self._store.popitem(last=False)
                self.evictions += 1
                logger.info(
                    "[V127_PITCH_CACHE] EVICT size=%d evictions=%d",
                    len(self._store), self.evictions,
                )

    def stats(self) -> dict:
        with self._lock:
            return {
                "size": len(self._store),
                "maxsize": self._maxsize,
                "ttl_seconds": self._ttl,
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
            }

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0
            self.evictions = 0


pitch_cache = PitchCache()
