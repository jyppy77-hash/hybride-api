"""
Fixtures communes pour les tests engine/.
Fournit un SmartMockCursor qui dispatche les reponses
en fonction du contenu SQL, sans connexion MySQL reelle.
"""

import random as _random
from contextlib import asynccontextmanager
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Donnees de tirage deterministes ──────────────────────────────────────

def _make_fake_tirages(n=200):
    """Genere *n* tirages deterministes (seed=42)."""
    rng = _random.Random(42)
    tirages = []
    base = date(2020, 1, 6)
    for i in range(n):
        nums = sorted(rng.sample(range(1, 50), 5))
        tirages.append({
            "boule_1": nums[0],
            "boule_2": nums[1],
            "boule_3": nums[2],
            "boule_4": nums[3],
            "boule_5": nums[4],
            "date_de_tirage": base + timedelta(days=i * 3),
            "numero_chance": rng.randint(1, 10),
        })
    return tirages


FAKE_TIRAGES = _make_fake_tirages()


# ── SmartMockCursor ──────────────────────────────────────────────────────

class SmartMockCursor:
    """Mock cursor qui dispatche automatiquement en fonction du SQL."""

    def __init__(self, tirages=None):
        self._tirages = tirages or FAKE_TIRAGES
        self._q = ""
        self._params = None

    # ── API pymysql ──

    def execute(self, query, params=None):
        self._q = " ".join(query.split()).lower()
        self._params = params

    # ── helpers internes ──

    def _parse_date_param(self, idx=0):
        if not self._params:
            return None
        p = self._params
        val = p[idx] if isinstance(p, (list, tuple)) and len(p) > idx else p
        if isinstance(val, str):
            return date.fromisoformat(val)
        if isinstance(val, date):
            return val
        return None

    def _filter_gte(self):
        d = self._parse_date_param()
        if d:
            return [t for t in self._tirages if t["date_de_tirage"] >= d]
        return list(self._tirages)

    # ── fetchone ──

    def fetchone(self):
        q = self._q

        # MAX(date_de_tirage) seul
        if "max(date_de_tirage)" in q and "min" not in q and "count" not in q:
            d = max((t["date_de_tirage"] for t in self._tirages), default=None)
            return {"max_date": d, "last": d}

        # COUNT + MIN + MAX
        if "count(*)" in q and "min(" in q:
            dates = [t["date_de_tirage"] for t in self._tirages]
            return {
                "total": len(dates), "count": len(dates),
                "date_min": min(dates, default=None),
                "date_max": max(dates, default=None),
                "min_date": min(dates, default=None),
                "max_date": max(dates, default=None),
            }

        # MIN + MAX (sans count)
        if "min(date_de_tirage)" in q:
            dates = [t["date_de_tirage"] for t in self._tirages]
            return {
                "min_date": min(dates, default=None),
                "max_date": max(dates, default=None),
            }

        # COUNT avec WHERE date_de_tirage > %s (ecart / gap)
        if "count(*)" in q and "date_de_tirage >" in q:
            d = self._parse_date_param()
            c = sum(1 for t in self._tirages if t["date_de_tirage"] > d) if d else 0
            return {"count": c, "gap": c}

        # COUNT simple
        if "count(*)" in q:
            return {"count": len(self._tirages), "total": len(self._tirages)}

        return None

    # ── fetchall ──

    def fetchall(self):
        q = self._q

        # Filtre par numero : WHERE boule_1 = %s OR boule_2 = %s ...
        if "boule_1 = %s" in q and "or" in q:
            num = self._params[0] if self._params else None
            if num is None:
                return []
            result = []
            for t in self._tirages:
                if num in (t["boule_1"], t["boule_2"], t["boule_3"],
                           t["boule_4"], t["boule_5"]):
                    result.append({"date_de_tirage": t["date_de_tirage"]})
            result.sort(key=lambda x: x["date_de_tirage"])
            return result

        # Frequence chance groupee
        if "numero_chance" in q and "count(*)" in q and "group by" in q:
            filtered = self._filter_gte()
            freq = {}
            for t in filtered:
                c = t["numero_chance"]
                freq[c] = freq.get(c, 0) + 1
            return [{"numero_chance": k, "freq": v} for k, v in sorted(freq.items())]

        # UNION ALL + ecart SQL (correlated subquery — _get_all_ecarts v2)
        if "union all" in q and "as ecart" in q:
            last = {}
            for t in self._tirages:
                for col in ("boule_1", "boule_2", "boule_3", "boule_4", "boule_5"):
                    n = t[col]
                    d = t["date_de_tirage"]
                    if n not in last or d > last[n]:
                        last[n] = d
            result = []
            for num, last_date in sorted(last.items()):
                ecart = sum(1 for t in self._tirages if t["date_de_tirage"] > last_date)
                result.append({"num": num, "ecart": ecart})
            return result

        # Ecart SQL for chance (correlated subquery)
        if "numero_chance" in q and "as ecart" in q:
            last = {}
            for t in self._tirages:
                c = t["numero_chance"]
                d = t["date_de_tirage"]
                if c not in last or d > last[c]:
                    last[c] = d
            result = []
            for num, last_date in sorted(last.items()):
                ecart = sum(1 for t in self._tirages if t["date_de_tirage"] > last_date)
                result.append({"num": num, "ecart": ecart})
            return result

        # UNION ALL + COUNT (frequences)
        if "union all" in q and "count(*)" in q:
            filtered = self._filter_gte()
            freq = {}
            for t in filtered:
                for col in ("boule_1", "boule_2", "boule_3", "boule_4", "boule_5"):
                    n = t[col]
                    freq[n] = freq.get(n, 0) + 1
            return [{"num": k, "freq": v} for k, v in sorted(freq.items())]

        # UNION ALL + MAX(date) (dernieres apparitions — legacy compat)
        if "union all" in q and "max(date_de_tirage)" in q:
            last = {}
            for t in self._tirages:
                for col in ("boule_1", "boule_2", "boule_3", "boule_4", "boule_5"):
                    n = t[col]
                    d = t["date_de_tirage"]
                    if n not in last or d > last[n]:
                        last[n] = d
            return [{"num": k, "last_date": v} for k, v in sorted(last.items())]

        # Tirages complets (SELECT boule_1..5 FROM tirages)
        if "boule_1" in q and "from tirages" in q:
            filtered = self._filter_gte()
            if "desc" in q:
                return list(reversed(filtered))
            return list(filtered)

        # Dates seules
        if "date_de_tirage" in q and "from tirages" in q:
            filtered = self._filter_gte()
            rows = [{"date_de_tirage": t["date_de_tirage"]} for t in filtered]
            if "desc" in q:
                rows.reverse()
            return rows

        return []


class AsyncSmartMockCursor(SmartMockCursor):
    """Async wrapper around SmartMockCursor for aiomysql compatibility."""

    async def execute(self, query, params=None):
        super().execute(query, params)

    async def fetchone(self):
        return super().fetchone()

    async def fetchall(self):
        return super().fetchall()


@asynccontextmanager
async def make_async_conn(cursor=None):
    """Async context manager that mimics db_cloudsql.get_connection()."""
    cur = cursor or AsyncSmartMockCursor()
    conn = AsyncMock()
    conn.cursor = AsyncMock(return_value=cur)
    yield conn


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def smart_mock_db():
    """Retourne (async_conn_cm, cursor) avec AsyncSmartMockCursor."""
    cursor = AsyncSmartMockCursor()
    return make_async_conn(cursor), cursor


@pytest.fixture(autouse=True)
def _clear_cache():
    """Vide le cache in-memory avant et apres chaque test."""
    from services.cache import cache_clear
    cache_clear()
    yield
    cache_clear()
