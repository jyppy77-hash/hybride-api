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
    from services.cache import _mem_cache
    _mem_cache.clear()
    yield
    _mem_cache.clear()


# ═══════════════════════════════════════════════════════════════════════
# V131.B — Google Gen AI SDK mock fixture (Vertex AI migration)
# ═══════════════════════════════════════════════════════════════════════

import asyncio as _asyncio
from contextlib import contextmanager as _contextmanager
from unittest.mock import patch, PropertyMock

from google.genai import errors as genai_errors


def _make_client_error(code: int, status: str = None) -> "genai_errors.ClientError":
    """V131.B — helper créer ClientError SDK B instance pour tests.

    Réutilisé par test_v131_retry.py (5 tests) + test_chat_pipeline.py +
    test_chat_pipeline_em.py + test_anti_hallucination.py via fixture
    make_client_error (pattern pytest canonique, pas d'import direct).
    """
    status = status or ("RESOURCE_EXHAUSTED" if code == 429 else "INVALID_ARGUMENT")
    response_json = {"error": {"code": code, "message": f"test {status}", "status": status}}
    return genai_errors.ClientError(code, response_json)


class _VertexController:
    """V131.B — Controller mock exposé via fixture mock_vertex_client.

    Expose .client (MagicMock) patché sur services.gemini_shared._CLIENT,
    plus 6 helpers .set_*() pour configurer le comportement par test.
    """

    def __init__(self):
        self.client = MagicMock()
        self.client.aio = MagicMock()
        self.client.aio.models = MagicMock()
        self.client.aio.models.generate_content = AsyncMock()
        self.client.aio.models.generate_content_stream = AsyncMock()

    def set_response(self, text: str, tin: int = 10, tout: int = 5):
        """Mock generate_content → response.text = `text` + usage_metadata."""
        resp = MagicMock()
        resp.text = text
        resp.usage_metadata = MagicMock(
            prompt_token_count=tin,
            candidates_token_count=tout,
        )
        self.client.aio.models.generate_content = AsyncMock(return_value=resp)

    def set_blocked_safety(self):
        """Mock generate_content → response.text lève ValueError (SAFETY/RECITATION)."""
        resp = MagicMock()
        _prop = PropertyMock(side_effect=ValueError("SAFETY blocked"))
        type(resp).text = _prop  # isolation OK : chaque MagicMock() = type anonyme
        resp.usage_metadata = None
        self.client.aio.models.generate_content = AsyncMock(return_value=resp)

    def set_error(self, exc: Exception):
        """Mock generate_content → lève exc (ClientError 429, ServerError, APIError...)."""
        self.client.aio.models.generate_content = AsyncMock(side_effect=exc)

    def set_timeout(self):
        """Mock generate_content → lève asyncio.TimeoutError (via asyncio.wait_for)."""
        self.client.aio.models.generate_content = AsyncMock(
            side_effect=_asyncio.TimeoutError()
        )

    def set_stream_chunks(self, chunks: list):
        """Mock generate_content_stream → async iterator yieldant chunks.

        chunks = [{"text": str, "usage": dict|None}, ...]
        Le dernier chunk contient typiquement {"usage": {"prompt_token_count": N, ...}}.
        """
        async def _async_gen():
            for c in chunks:
                chunk = MagicMock()
                chunk.text = c.get("text", "")
                usage = c.get("usage")
                chunk.usage_metadata = MagicMock(**usage) if usage else None
                yield chunk
        self.client.aio.models.generate_content_stream = AsyncMock(
            return_value=_async_gen()
        )

    def set_stream_error(self, exc: Exception):
        """Mock await generate_content_stream → lève exc au démarrage du stream."""
        self.client.aio.models.generate_content_stream = AsyncMock(side_effect=exc)


@pytest.fixture
def mock_vertex_client():
    """V131.B — Context manager qui patch services.gemini_shared._CLIENT.

    Couvre les 3 modules V131.A (gemini_shared, gemini, chat_pipeline_gemini)
    via 1 seul patch — tous appellent _get_client() qui lit _CLIENT global.

    Usage:
        def test_xxx(mock_vertex_client):
            with mock_vertex_client() as vc:
                vc.set_response(text="mock reply", tin=10, tout=5)
                result = await function_under_test(...)
                assert result == expected
    """
    @_contextmanager
    def _cm():
        controller = _VertexController()
        with patch("services.gemini_shared._CLIENT", controller.client):
            yield controller
    return _cm


@pytest.fixture
def make_client_error():
    """V131.B — fixture exposant helper _make_client_error (pattern pytest canonique).

    Évite l'anti-pattern `from tests.conftest import _make_client_error`
    qui dépend de la config rootdir.

    Usage:
        def test_xxx(mock_vertex_client, make_client_error):
            error = make_client_error(429)
            with mock_vertex_client() as vc:
                vc.set_error(error)
    """
    return _make_client_error


@pytest.fixture(autouse=True)
def _reset_vertex_client():
    """V131.B — Reset _CLIENT global à None avant/après chaque test.

    Défensif no-op si _CLIENT jamais initialisé (lazy via _get_client()).
    Empêche pollution inter-tests si un test initialise le vrai client.
    """
    import services.gemini_shared as _gs
    _gs._CLIENT = None
    yield
    _gs._CLIENT = None
