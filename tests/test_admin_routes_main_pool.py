"""1.6.055 GO 0 — routes admin calendrier sur le pool principal.

Le compte lecture seule chatbot_ro n'a SELECT que sur tirages et
tirages_euromillions : les routes admin (event_log, sponsor_impressions,
chat_log, hybride_selection_history) doivent passer par get_connection().
Les requêtes fixes du chat qui gardent get_connection_readonly() ne doivent
lire QUE les tables de tirages.

Aucune connexion réelle : les deux getters sont remplacés par des mocks,
get_connection_readonly lève si une route admin l'appelle.
"""

import os
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.testclient import TestClient

_TEST_TOKEN = "test_admin_token_1655_go0"
_ROOT = Path(__file__).resolve().parent.parent

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "ADMIN_TOKEN": _TEST_TOKEN, "ADMIN_PASSWORD": "testpw",
})


def _authed_client():
    with _db_env, _static_patch, _static_call:
        import importlib
        import routes.admin_helpers as admin_helpers_mod
        importlib.reload(admin_helpers_mod)
        import routes.admin_calendar as admin_calendar_mod
        importlib.reload(admin_calendar_mod)
        import routes.admin_perf_calendar as admin_perf_mod
        importlib.reload(admin_perf_mod)
        import routes.admin as admin_mod
        importlib.reload(admin_mod)
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
    client.cookies.set("lotoia_admin_token", _TEST_TOKEN)
    return client


def _make_conn_ctx():
    cursor = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=[])
    cursor.fetchone = AsyncMock(return_value=None)
    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cursor)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _pool_mocks(module_path: str):
    """Patch get_connection (mock OK) et get_connection_readonly (interdit)."""
    main_pool = MagicMock(side_effect=lambda: _make_conn_ctx())
    ro_pool = MagicMock(side_effect=AssertionError("get_connection_readonly interdit en route admin"))
    return (
        main_pool, ro_pool,
        patch(f"{module_path}.db_cloudsql.get_connection", main_pool),
        patch(f"{module_path}.db_cloudsql.get_connection_readonly", ro_pool),
    )


# ── Routes admin : pool utilisé ─────────────────────────────────────────


def test_admin_calendar_data_uses_main_pool():
    client = _authed_client()
    main_pool, ro_pool, p_main, p_ro = _pool_mocks("routes.admin_calendar")
    with p_main, p_ro:
        resp = client.get("/admin/api/calendar-data?year=2026&month=10")
    assert resp.status_code == 200
    assert main_pool.call_count == 4  # visiteurs, sessions, impressions, chatbot
    ro_pool.assert_not_called()


def test_admin_perf_calendar_month_uses_main_pool():
    client = _authed_client()
    main_pool, ro_pool, p_main, p_ro = _pool_mocks("routes.admin_perf_calendar")
    with p_main, p_ro:
        resp = client.get("/admin/api/calendar-perf/loto/2026/10")
    assert resp.status_code == 200
    assert main_pool.call_count == 2  # tirages FDJ + hybride_selection_history
    ro_pool.assert_not_called()


def test_admin_perf_calendar_draw_detail_uses_main_pool():
    client = _authed_client()
    main_pool, ro_pool, p_main, p_ro = _pool_mocks("routes.admin_perf_calendar")
    with p_main, p_ro:
        resp = client.get("/admin/api/calendar-perf/draw/euromillions/2026-10-13")
    assert resp.status_code == 200
    assert main_pool.call_count == 2  # tirage FDJ + hybride_selection_history
    ro_pool.assert_not_called()


def test_admin_calendar_sources_never_use_readonly_pool():
    for rel in ("routes/admin_calendar.py", "routes/admin_perf_calendar.py"):
        src = (_ROOT / rel).read_text(encoding="utf-8")
        assert "get_connection_readonly" not in src, rel


# ── Requêtes fixes du chat sur le pool lecture seule : tirages uniquement ──

_READONLY_TABLES = {"tirages", "tirages_euromillions"}
_FIXED_RO_FILES = (
    "services/chat_sql.py",
    "services/chat_sql_em.py",
    "services/chat_pipeline_gemini.py",
)
_TABLE_REF_RE = re.compile(r"\b(?:FROM|JOIN|DESCRIBE)\s+`?(\w+)", re.IGNORECASE)


def _readonly_blocks(src: str) -> list[str]:
    """Corps de chaque bloc `async with ...get_connection_readonly()` (indentation)."""
    lines = src.splitlines()
    blocks = []
    for i, line in enumerate(lines):
        if "get_connection_readonly()" not in line or "async with" not in line:
            continue
        indent = len(line) - len(line.lstrip())
        body = []
        for nxt in lines[i + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                break
            body.append(nxt)
        blocks.append("\n".join(body))
    return blocks


def test_fixed_chat_readonly_queries_read_only_draw_tables():
    found = 0
    for rel in _FIXED_RO_FILES:
        src = (_ROOT / rel).read_text(encoding="utf-8")
        for block in _readonly_blocks(src):
            found += 1
            tables = {t.lower() for t in _TABLE_REF_RE.findall(block)}
            # chat_pipeline_gemini : DESCRIBE {table} sur un tuple littéral
            tables.discard("table")
            tables |= set(re.findall(r'"(tirages(?:_euromillions)?)"', block))
            assert tables, f"{rel} : aucune table détectée"
            assert tables <= _READONLY_TABLES, f"{rel} : {tables - _READONLY_TABLES}"
    assert found == 5  # chat_sql 2 + chat_sql_em 2 + chat_pipeline_gemini 1
