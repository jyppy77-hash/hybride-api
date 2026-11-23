"""Lot 1.6.077 — chat_log.traffic_source, compteurs admin, export CSV technique (Release 1.6.077, 23/11/2026).

ip_hash / session_hash de chat_log ne sont jamais remplis (promesse de confidentialité 1.6.072).
Aucune modification des réponses du chatbot. Aucun appel réel DB / Vertex.
"""

import ast
import asyncio
import hashlib
import os
import re
import time
from datetime import datetime
from ipaddress import ip_network
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.testclient import TestClient

import utils

# db_cloudsql lit DB_USER / DB_PASSWORD / DB_NAME à l'import (pattern _db_env des autres tests)
with patch.dict(os.environ, {"DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb"}):
    from services import chat_logger
    from services.chat_logger import TRAFFIC_SOURCES, log_chat_exchange, normalize_traffic_source
    from services.circuit_breaker import CircuitOpenError
    import services.chat_pipeline as chat_pipeline
    import services.chat_pipeline_em as chat_pipeline_em
    import services.chat_pipeline_gemini as chat_pipeline_gemini
    import services.chat_pipeline_shared as chat_pipeline_shared
    import routes.api_chat  # noqa: F401
    import routes.api_chat_em  # noqa: F401
    import routes.api_chat_unified  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
_OWNER_V4 = "203.0.113.50"
_OWNER_V6_NET = "2001:db8:77:1::/64"
_OWNER_V6_ADDR = "2001:db8:77:1::abcd"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setattr(utils, "_OWNER_EXACT", {"127.0.0.1", "::1", _OWNER_V4})
    monkeypatch.setattr(utils, "_owner_nets_v6", [ip_network(_OWNER_V6_NET)])


def _meta(**extra):
    return {"phase": "1", "t0": time.monotonic(), "lang": "fr", **extra}


# ═══════════════════════════════════════════════════════════════════════
# T-A — log_from_meta
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("meta_extra,expected", [
    ({"traffic_source": "owner"}, "owner"),
    ({"traffic_source": "test"}, "test"),
    ({"traffic_source": "public"}, "public"),
    ({}, "public"),
])
def test_ta_log_from_meta_forwards_traffic_source(meta_extra, expected):
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_log:
        chat_pipeline_gemini.log_from_meta(_meta(**meta_extra), "loto", "fr", "m", "r")
    assert mock_log.call_args.kwargs["traffic_source"] == expected


def test_ta_log_from_meta_never_passes_identifiers():
    meta = _meta(traffic_source="owner", ip_hash="x", session_hash="y", client_ip="198.51.100.9")
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_log:
        chat_pipeline_gemini.log_from_meta(meta, "loto", "fr", "m")
    kwargs = mock_log.call_args.kwargs
    assert "ip_hash" not in kwargs and "session_hash" not in kwargs
    assert "198.51.100.9" not in repr(mock_log.call_args)


@pytest.mark.parametrize("value,expected", [
    ("public", "public"), ("owner", "owner"), ("test", "test"),
    ("OWNER", "public"), ("", "public"), (None, "public"), ("x' OR 1", "public"), (3, "public"),
])
def test_ta_normalize_traffic_source(value, expected):
    assert TRAFFIC_SOURCES == {"public", "owner", "test"}
    assert normalize_traffic_source(value) == expected


@pytest.mark.no_chat_logger_stub
@pytest.mark.asyncio
async def test_ta_invalid_value_inserted_as_public():
    with patch.object(chat_logger, "db_cloudsql") as mock_db:
        mock_db.async_query = AsyncMock(return_value=None)
        log_chat_exchange("loto", "fr", "q", traffic_source="owner")
        log_chat_exchange("loto", "fr", "q", traffic_source="hacker")
        log_chat_exchange("loto", "fr", "q")
        await asyncio.sleep(0.01)
    params = [c[0][1] for c in mock_db.async_query.call_args_list]
    assert [p[-1] for p in params] == ["owner", "public", "public"]
    assert all(p[8] == "" and p[9] == "" for p in params)  # ip_hash / session_hash inchangés (vides)


# ═══════════════════════════════════════════════════════════════════════
# T-B — _INSERT_SQL
# ═══════════════════════════════════════════════════════════════════════

def test_tb_insert_sql_has_traffic_source():
    sql = chat_logger._INSERT_SQL
    cols = [c.strip() for c in re.search(r"\(([^)]*)\)\s*VALUES", sql).group(1).split(",")]
    assert "traffic_source" in cols
    assert sql.count("%s") == len(cols) == 17


# ═══════════════════════════════════════════════════════════════════════
# T-C — chemins d'écriture
# ═══════════════════════════════════════════════════════════════════════

def _log_from_meta_calls():
    out = []
    for rel in ("services/chat_pipeline_gemini.py", "services/chat_pipeline_shared.py"):
        for node in ast.walk(ast.parse(_read(rel))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "log_from_meta":
                out.append((rel, node.lineno, node))
    return out


_CALLS = _log_from_meta_calls()


def test_tc_inventory_of_write_paths():
    # 9 dans chat_pipeline_gemini + 2 retours anticipés dans chat_pipeline_shared = 11
    per = {}
    for rel, _, _ in _CALLS:
        per[rel] = per.get(rel, 0) + 1
    assert per == {"services/chat_pipeline_gemini.py": 9, "services/chat_pipeline_shared.py": 2}


@pytest.mark.parametrize("rel,lineno,node", _CALLS, ids=[f"{r.split('/')[-1]}:{n}" for r, n, _ in _CALLS])
def test_tc_each_write_path_reads_chat_meta(rel, lineno, node):
    first = node.args[0]
    assert isinstance(first, ast.Call) and getattr(first.func, "attr", "") == "get"
    assert first.func.value.id in ("ctx", "early")
    assert first.args[0].value == "_chat_meta"


def test_tc_chat_meta_built_with_traffic_source():
    """Les deux points de construction de _chat_meta portent traffic_source (et aucune clé d'identifiant)."""
    tree = ast.parse(_read("services/chat_pipeline_shared.py"))
    found = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
            if {"phase", "t0", "lang"} <= keys:
                found += 1
                assert "traffic_source" in keys
                assert not keys & {"client_ip", "ip", "ip_hash", "session_hash", "user_agent", "ua"}
    assert found == 2


def _fake_prepare(early_meta=None, ctx_extra=None):
    seen = {}

    async def prepare(message, history, page, http_client, lang="fr", *, traffic_source="public"):
        seen["traffic_source"] = traffic_source
        meta = {"phase": "1", "t0": time.monotonic(), "lang": lang, "traffic_source": traffic_source}
        if early_meta is not None:
            return {"response": "R", "source": "hybride", "mode": "decouverte", "_chat_meta": meta}, None
        ctx = {"mode": "decouverte", "system_prompt": "s", "contents": [], "_http_client": None,
               "gem_api_key": "", "history": [], "lang": lang, "insult_prefix": "", "_chat_meta": meta}
        ctx.update(ctx_extra or {})
        return None, ctx
    return prepare, seen


async def _drain(gen):
    return [e async for e in gen]


def _breaker(state="closed"):
    b = MagicMock()
    b.state = state
    b.OPEN = "open"
    return b


async def _run_stream(prepare, stream_fn, source):
    return await _drain(chat_pipeline_shared.handle_stream_common(
        "m", [], "accueil", None, "fr", prepare_context_fn=prepare, default_fallback="F",
        log_prefix="[T]", module="loto", call_type="chat_loto", stream_fn=stream_fn, breaker=None,
        traffic_source=source,
    ))


async def _run_sync(prepare, source, breaker):
    return await chat_pipeline_shared.handle_chat_common(
        "m", [], "accueil", None, "fr", prepare_context_fn=prepare, default_fallback="F",
        log_prefix="[T]", module="loto", breaker=breaker, traffic_source=source,
    )


def _gen_raise(exc):
    async def gen(*a, **kw):
        raise exc
        yield  # pragma: no cover
    return gen


def _gen_ok(*chunks):
    async def gen(*a, **kw):
        for c in chunks:
            yield c
    return gen


def _client_error():
    from google.genai import errors as genai_errors
    err = genai_errors.ClientError.__new__(genai_errors.ClientError)
    Exception.__init__(err, "429 RESOURCE_EXHAUSTED")
    err.code = 429
    err.status = "RESOURCE_EXHAUSTED"
    return err


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["public", "owner", "test"])
async def test_tc_early_stream(source):
    prepare, seen = _fake_prepare(early_meta=True)
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_log:
        await _run_stream(prepare, None, source)
    assert seen["traffic_source"] == source
    assert mock_log.call_args.kwargs["traffic_source"] == source


@pytest.mark.asyncio
async def test_tc_early_non_stream():
    prepare, seen = _fake_prepare(early_meta=True)
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_log:
        await _run_sync(prepare, "owner", None)
    assert mock_log.call_args.kwargs["traffic_source"] == "owner"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream_fn,detail", [
    (_gen_raise(CircuitOpenError("open")), "CircuitOpen"),
    (_gen_raise(asyncio.TimeoutError()), "Timeout"),
    (_gen_raise(RuntimeError("vertex down")), "vertex down"),
    (_gen_ok(), "NoChunks"),
], ids=["circuit_open", "timeout", "vertex_error", "no_chunks"])
async def test_tc_stream_error_paths(stream_fn, detail):
    prepare, _ = _fake_prepare()
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_log:
        await _run_stream(prepare, stream_fn, "test")
    kw = mock_log.call_args.kwargs
    assert kw["traffic_source"] == "test" and kw["error_detail"] == detail


@pytest.mark.asyncio
async def test_tc_stream_success():
    prepare, _ = _fake_prepare()
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_log:
        await _run_stream(prepare, _gen_ok("Réponse de test sans chiffre. ", "Fin."), "owner")
    kw = mock_log.call_args.kwargs
    assert kw["traffic_source"] == "owner" and kw["is_error"] is False


@pytest.mark.asyncio
async def test_tc_stream_strict_hallucination_block():
    prepare, _ = _fake_prepare(ctx_extra={"_strict_hallucination_block": True})
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_log, \
         patch("services.chat_pipeline_gemini._check_sql_number_hallucination", return_value="SAFE"):
        await _run_stream(prepare, _gen_ok("Le 7 est sorti 999 fois."), "test")
    kw = mock_log.call_args.kwargs
    assert kw["traffic_source"] == "test" and kw["error_detail"] == "StrictHallucinationBlock"


def _vertex_client(side_effect=None, text="Réponse de test."):
    client = MagicMock()
    if side_effect is not None:
        client.aio.models.generate_content = AsyncMock(side_effect=side_effect)
    else:
        resp = MagicMock()
        resp.text = text
        resp.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=5)
        client.aio.models.generate_content = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
async def test_tc_non_stream_vertex_error():
    prepare, _ = _fake_prepare()
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_log, \
         patch("services.chat_pipeline_gemini._get_client", return_value=_vertex_client(_client_error())), \
         patch("services.chat_pipeline_gemini._track_error"):
        await _run_sync(prepare, "owner", _breaker())
    kw = mock_log.call_args.kwargs
    assert kw["traffic_source"] == "owner" and kw["is_error"] is True


@pytest.mark.asyncio
async def test_tc_non_stream_circuit_open():
    prepare, _ = _fake_prepare()
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_log:
        await _run_sync(prepare, "test", _breaker("open"))
    kw = mock_log.call_args.kwargs
    assert kw["traffic_source"] == "test" and kw["error_detail"] == "CircuitOpen"


@pytest.mark.asyncio
async def test_tc_non_stream_success():
    prepare, _ = _fake_prepare()
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_log, \
         patch("services.chat_pipeline_gemini._get_client", return_value=_vertex_client()), \
         patch("services.chat_pipeline_gemini._track_usage"):
        await _run_sync(prepare, "owner", _breaker())
    assert mock_log.call_args_list[0].kwargs["traffic_source"] == "owner"


@pytest.mark.asyncio
@pytest.mark.parametrize("handler,draw_game", [
    (chat_pipeline.handle_chat_stream, "loto"), (chat_pipeline_em.handle_chat_stream_em, "em"),
])
async def test_tc_real_builder_early_path(handler, draw_game):
    """Vrai _prepare_chat_context_base (Phase I) : l'étiquette arrive à log_chat_exchange via _meta()."""
    real = chat_pipeline_gemini.log_from_meta
    with patch("services.chat_pipeline._get_draw_count", new_callable=AsyncMock, return_value=1000), \
         patch("services.chat_pipeline_shared.log_from_meta", side_effect=real) as spy, \
         patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_log:
        await _drain(handler("t'es vraiment nul connard", [], "accueil", None, lang="fr", traffic_source="test"))
    meta = spy.call_args[0][0]
    assert meta["traffic_source"] == "test"
    assert not set(meta) & {"client_ip", "ip", "ip_hash", "session_hash"}
    assert mock_log.call_args.kwargs["traffic_source"] == "test"


@pytest.mark.parametrize("fn", [
    chat_pipeline.handle_chat, chat_pipeline.handle_chat_stream, chat_pipeline._prepare_chat_context,
    chat_pipeline_em.handle_chat_em, chat_pipeline_em.handle_chat_stream_em, chat_pipeline_em._prepare_chat_context_em,
    chat_pipeline_shared.handle_chat_common, chat_pipeline_shared.handle_stream_common,
    chat_pipeline_shared._prepare_chat_context_base,
], ids=lambda f: f.__name__)
def test_tc_kw_only_default_public(fn):
    import inspect
    p = inspect.signature(fn).parameters["traffic_source"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY and p.default == "public"


# ═══════════════════════════════════════════════════════════════════════
# T-D — utils.classify_traffic_source
# ═══════════════════════════════════════════════════════════════════════

def _request(headers=None, client_host="testclient"):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw,
                    "client": (client_host, 1234), "query_string": b""})


def test_td_smoke_header(owner):
    assert utils.classify_traffic_source(_request({"X-LotoIA-Smoke": "1", "X-Forwarded-For": "198.51.100.1"})) == "test"
    assert utils.classify_traffic_source(_request({"X-LotoIA-Smoke": "1", "X-Forwarded-For": _OWNER_V4})) == "test"


@pytest.mark.parametrize("value", ["0", "true", "yes", "", "11"])
def test_td_smoke_header_other_values_ignored(owner, value):
    assert utils.classify_traffic_source(_request({"X-LotoIA-Smoke": value, "X-Forwarded-For": "198.51.100.1"})) == "public"


def test_td_owner_ipv4(owner):
    assert utils.classify_traffic_source(_request({"X-Forwarded-For": _OWNER_V4})) == "owner"


def test_td_owner_ipv6(owner):
    assert utils.classify_traffic_source(_request({"X-Forwarded-For": _OWNER_V6_ADDR})) == "owner"


def test_td_other_ip_public(owner):
    assert utils.classify_traffic_source(_request({"X-Forwarded-For": "198.51.100.7"})) == "public"
    assert utils.classify_traffic_source(_request({"X-Forwarded-For": "2001:db8:99::1"})) == "public"


def test_td_empty_or_invalid_ip_public(owner):
    assert utils.classify_traffic_source(_request({"X-Forwarded-For": "not-an-ip"})) == "public"
    assert utils.classify_traffic_source(_request({}, client_host="")) == "public"


def test_td_internal_exception_public(owner, monkeypatch):
    def boom(_request):
        raise RuntimeError("boom")
    monkeypatch.setattr(utils, "get_client_ip", boom)
    assert utils.classify_traffic_source(_request({"X-Forwarded-For": _OWNER_V4})) == "public"


def test_td_reuses_is_owner_ip():
    import inspect
    src = inspect.getsource(utils.classify_traffic_source)
    assert "is_owner_ip(" in src and "OWNER_IP" not in src


# ═══════════════════════════════════════════════════════════════════════
# T-E — routes Loto, EM, unifiée
# ═══════════════════════════════════════════════════════════════════════

_ROUTES = [
    ("loto", "routes.api_chat", "/api/hybride-chat", "routes.api_chat.handle_chat_stream",
     {"message": "bonjour", "page": "accueil"}),
    ("em", "routes.api_chat_em", "/api/euromillions/hybride-chat", "routes.api_chat_em.handle_chat_stream_em",
     {"message": "hello", "lang": "en"}),
    ("unified-loto", "routes.api_chat_unified", "/api/loto/hybride-chat",
     "services.chat_pipeline.handle_chat_stream", {"message": "bonjour", "page": "accueil"}),
    ("unified-em", "routes.api_chat_unified", "/api/euromillions/hybride-chat",
     "services.chat_pipeline_em.handle_chat_stream_em", {"message": "hallo", "lang": "de"}),
]
_IP_SEQ = iter(range(1, 250))


def _post(route, xff, extra_headers=None):
    import importlib
    import rate_limit
    _, modname, url, target, body = route
    rate_limit.limiter.reset()
    app = FastAPI()
    app.state.limiter = rate_limit.limiter
    app.state.httpx_client = MagicMock()
    app.include_router(importlib.import_module(modname).router)
    seen = {}

    async def fake(*args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        yield 'data: {"chunk": "ok", "is_done": true}\n\n'

    with patch(target, fake):
        resp = TestClient(app).post(url, json=body, headers={"X-Forwarded-For": xff, **(extra_headers or {})})
    assert resp.status_code == 200, resp.text
    return seen


@pytest.mark.parametrize("route", _ROUTES, ids=[r[0] for r in _ROUTES])
class TestTERoutes:

    def test_owner(self, route, owner):
        assert _post(route, _OWNER_V4)["kwargs"]["traffic_source"] == "owner"

    def test_public_and_no_ip_forwarded(self, route, owner):
        ip = f"198.51.100.{next(_IP_SEQ)}"
        seen = _post(route, ip)
        assert seen["kwargs"]["traffic_source"] == "public"
        assert set(seen["kwargs"]) == {"lang", "traffic_source"}
        assert ip not in repr(seen)

    def test_smoke(self, route, owner):
        seen = _post(route, f"198.51.100.{next(_IP_SEQ)}", {"X-LotoIA-Smoke": "1"})
        assert seen["kwargs"]["traffic_source"] == "test"


def test_te_routes_source():
    for rel in ("routes/api_chat.py", "routes/api_chat_em.py", "routes/api_chat_unified.py"):
        src = _read(rel)
        assert "classify_traffic_source(request)" in src
        assert "client_ip=" not in src


# ═══════════════════════════════════════════════════════════════════════
# T-F — export CSV technique
# ═══════════════════════════════════════════════════════════════════════

_CSV_HEADER = ("id,created_at,module,lang,phase_detected,sql_generated,sql_status,duration_ms,grid_count,"
               "has_exclusions,is_error,error_detail,gemini_tokens_in,gemini_tokens_out,traffic_source")
_FORBIDDEN = ("question", "response_preview", "ip_hash", "session_hash")


def _admin():
    from tests.test_admin_chatbot_monitor import _authed_client
    return _authed_client()


def _reset_limiter():
    import rate_limit
    rate_limit.limiter.reset()  # export CSV limité à 30/minute (S15 V94)


def _csv(query="", rows=None):
    client = _admin()
    _reset_limiter()
    with patch("routes.admin_monitoring.db_cloudsql") as mock_db:
        mock_db.async_fetchall = AsyncMock(return_value=rows or [])
        resp = client.get("/admin/export/chatbot-log/csv" + query)
    return resp, mock_db


def _row(**over):
    row = {"id": 7, "created_at": datetime(2026, 11, 23, 9, 5, 0), "module": "em", "lang": "de",
           "phase_detected": "SQL", "sql_generated": "SELECT 1", "sql_status": "OK", "duration_ms": 120,
           "grid_count": 0, "has_exclusions": 0, "is_error": 1, "error_detail": "ligne 1\nligne 2\r\nligne 3",
           "gemini_tokens_in": 11, "gemini_tokens_out": None, "traffic_source": "owner",
           "question": "SECRET-Q", "response_preview": "SECRET-R", "ip_hash": "SECRET-IP", "session_hash": "SECRET-S"}
    row.update(over)
    return row


def test_tf_header_and_sql():
    resp, mock_db = _csv("?period=24h", [_row()])
    assert resp.status_code == 200
    raw = resp.content
    assert not raw.startswith(b"\xef\xbb\xbf")  # pas de BOM
    lines = raw.decode("utf-8").splitlines()
    assert lines[0] == _CSV_HEADER
    sql = mock_db.async_fetchall.call_args[0][0]
    for col in _FORBIDDEN:
        assert col not in lines[0] and col not in sql
    for secret in ("SECRET-Q", "SECRET-R", "SECRET-IP", "SECRET-S"):
        assert secret not in resp.text


def test_tf_row_format():
    resp, _ = _csv("", [_row()])
    import csv as _csv_mod
    import io
    rows = list(_csv_mod.reader(io.StringIO(resp.text)))
    data = dict(zip(rows[0], rows[1]))
    assert data["created_at"] == "2026-11-23T09:05:00Z"
    assert data["error_detail"] == "ligne 1 ligne 2 ligne 3"  # multi-ligne aplati
    assert data["gemini_tokens_out"] == ""  # NULL → vide
    assert data["traffic_source"] == "owner" and data["is_error"] == "1"
    long_err = _csv("", [_row(error_detail="x" * 900)])[0]
    assert dict(zip(*list(_csv_mod.reader(io.StringIO(long_err.text)))[:2]))["error_detail"] == "x" * 500


def test_tf_from_to_range():
    _, mock_db = _csv("?from=2026-11-01&to=2026-11-22")
    sql, params = mock_db.async_fetchall.call_args[0]
    assert "created_at >= %s" in sql and "created_at < %s" in sql
    assert params[:2] == ("2026-11-01 00:00:00", "2026-11-23 00:00:00")  # journée du 22 incluse
    assert "INTERVAL" not in sql  # la plage remplace le raccourci


def test_tf_shortcut_kept():
    _, mock_db = _csv("?period=7d&module=em&phase=SQL")
    sql = mock_db.async_fetchall.call_args[0][0]
    assert "INTERVAL 7 DAY" in sql and "module = %s" in sql


@pytest.mark.parametrize("value", ["public", "owner", "test"])
def test_tf_traffic_source_filter(value):
    _, mock_db = _csv(f"?traffic_source={value}")
    sql, params = mock_db.async_fetchall.call_args[0]
    assert "traffic_source = %s" in sql and value in params


def test_tf_no_filter_by_default():
    _, mock_db = _csv("")
    assert "traffic_source = %s" not in mock_db.async_fetchall.call_args[0][0]


@pytest.mark.parametrize("query", [
    "?from=2026-13-01", "?from=23/11/2026", "?to=2026-11-2", "?from=2026-11-22&to=2026-11-01",
    "?traffic_source=admin", "?traffic_source=PUBLIC",
])
def test_tf_invalid_param_400(query):
    resp, mock_db = _csv(query)
    assert resp.status_code == 400
    assert not mock_db.async_fetchall.called


@pytest.mark.parametrize("query", ["?full=1", "?raw=1", "?columns=question", "?include=response_preview"])
def test_tf_no_param_reveals_text(query):
    resp, mock_db = _csv(query, [_row()])
    assert resp.status_code == 200
    assert resp.text.splitlines()[0] == _CSV_HEADER
    assert "SECRET" not in resp.text


def test_tf_auth_guard_unchanged():
    from tests.test_admin_chatbot_monitor import _get_client
    client = _get_client()
    _reset_limiter()
    resp = client.get("/admin/export/chatbot-log/csv?from=2026-11-01", follow_redirects=False)
    assert resp.status_code == 302


# ═══════════════════════════════════════════════════════════════════════
# T-G — KPI sessions, calendrier
# ═══════════════════════════════════════════════════════════════════════

def test_tg_kpi_sessions_removed():
    from decimal import Decimal
    client = _admin()
    with patch("routes.admin_monitoring.db_cloudsql") as mock_db:
        mock_db.async_fetchone = AsyncMock(return_value={
            "total": Decimal(4), "rejected": Decimal(0), "sql_total": Decimal(0), "errors": Decimal(0),
            "avg_dur": Decimal(10), "public_count": Decimal(3), "sql_count": Decimal(0)})
        mock_db.async_fetchall = AsyncMock(return_value=[])
        data = client.get("/admin/api/chatbot-log").json()
    kpi_sql = mock_db.async_fetchone.call_args[0][0]
    assert "session_hash" not in kpi_sql and "traffic_source = 'public'" in kpi_sql
    assert "unique_sessions" not in data["kpi"] and data["kpi"]["public_count"] == 3
    tpl = _read("ui/templates/admin/chatbot-monitor.html")
    assert "Visiteurs uniques" not in tpl and "cm-kpi-sessions" not in tpl and "Échanges publics" in tpl
    render_cm = _read("ui/static/admin.js").split("function renderCmKPI")[1].split("function ")[0]
    assert "unique_sessions" not in render_cm and "kpi.public_count" in render_cm  # (admin.js:629 = page Engagement)


def test_tg_calendar_without_chat_log():
    executed = []

    class FakeCursor:
        async def execute(self, sql, params=None):
            executed.append((sql, params))

        async def fetchall(self):
            return []

    class FakeConn:
        async def cursor(self):
            return FakeCursor()

    class FakeCtx:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, *a):
            return False

    from tests.test_admin_calendar import _authed_client
    client = _authed_client()
    with patch("routes.admin_calendar.db_cloudsql") as mock_db:
        mock_db.get_connection.side_effect = lambda: FakeCtx()
        assert client.get("/admin/api/calendar-data?year=2026&month=11").status_code == 200
    visitors = [(s, p) for s, p in executed if "visitor_id" in s]
    assert len(visitors) == 1
    sql, params = visitors[0]
    assert "chat_log" not in sql and sql.count("%s") == len(params)
    src = _read("routes/admin_calendar.py")
    assert "chat_log.ip_hash : SHA-256(ip)" not in src
    assert "chat_log ne contient aucun identifiant de visiteur, décision du 23/11" in src


# ═══════════════════════════════════════════════════════════════════════
# T-H — migration
# ═══════════════════════════════════════════════════════════════════════

def test_th_migration():
    sql = (ROOT / "migrations" / "029_add_chat_log_traffic_source.sql").read_text(encoding="utf-8")
    up = sql.split("-- DOWN")[0]
    assert "ADD COLUMN traffic_source VARCHAR(8) NOT NULL DEFAULT 'public'" in up
    assert "ENUM" not in "\n".join(line for line in up.splitlines() if not line.lstrip().startswith("--"))
    assert "-- DOWN" in sql


# ═══════════════════════════════════════════════════════════════════════
# T-I — promesse publique intacte
# ═══════════════════════════════════════════════════════════════════════

# MD5 du contenu normalisé (CR retirés, valeur de <span class="app-version"> neutralisée) : stable quelle que
# soit la fin de ligne du checkout ; le bump 1.6.077 ne change que la version du pied de page Loto.
_PRIVACY_NORMALIZED_MD5 = {
    "ui/politique-confidentialite.html": "8ac97016c3228aa9211ff1329dfb2aaf",
    "ui/templates/em/confidentialite.html": "08a88577a20ce0d5b1a513847085620f",
}


@pytest.mark.parametrize("rel", sorted(_PRIVACY_NORMALIZED_MD5))
def test_ti_privacy_promise_intact(rel):
    raw = (ROOT / rel).read_bytes()
    assert raw.decode("utf-8").count("ni adresse IP, ni identifiant de session") >= 2
    norm = re.sub(rb'<span class="app-version">[^<]*</span>', b'<span class="app-version"></span>', raw)
    assert hashlib.md5(norm.replace(b"\r", b"")).hexdigest() == _PRIVACY_NORMALIZED_MD5[rel]


# ═══════════════════════════════════════════════════════════════════════
# Bump
# ═══════════════════════════════════════════════════════════════════════

def test_bump_1_6_077():
    from config.version import APP_VERSION, VERSION_DATE
    assert tuple(int(p) for p in APP_VERSION.split(".")) >= (1, 6, 77)
    assert VERSION_DATE >= "2026-11-23"
