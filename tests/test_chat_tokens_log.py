"""1.6.055 — Point F : tokens Gemini remontés jusqu'à chat_log.

Seuls les tokens de la RÉPONSE FINALE sont comptés (flux ou hors flux) ;
ceux de la génération SQL (chat_sql / chat_sql_em) ne le sont pas.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from google.genai import errors as genai_errors

from services.gemini import _as_int, stream_gemini_chat

_CONTENTS = [{"role": "user", "parts": [{"text": "hi"}]}]


def _chunk(text, usage=None):
    c = MagicMock()
    c.text = text
    c.candidates = []
    c.usage_metadata = MagicMock(**usage) if usage else None
    return c


async def _aiter(*chunks):
    for c in chunks:
        yield c


def _client(side_effect):
    client = MagicMock()
    client.aio.models.generate_content_stream = AsyncMock(side_effect=side_effect)
    return client


def _breaker():
    b = MagicMock()
    b.state = "closed"
    b.OPEN = "open"
    return b


def _make_429():
    err = genai_errors.ClientError.__new__(genai_errors.ClientError)
    Exception.__init__(err, "429 RESOURCE_EXHAUSTED")
    err.code = 429
    err.status = "RESOURCE_EXHAUSTED"
    return err


async def _drain(gen):
    return [c async for c in gen]


def _ctx(strict=False):
    return {
        "system_prompt": "sys", "contents": _CONTENTS, "mode": "chat",
        "insult_prefix": "", "history": [], "lang": "fr",
        "_http_client": MagicMock(), "gem_api_key": "", "_chat_meta": None,
        "_strict_hallucination_block": strict,
    }


@pytest.fixture
def _no_tracking():
    with patch("services.gcp_monitoring.track_gemini_call", new_callable=AsyncMock):
        yield


# ── _as_int ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (1234, 1234), (0, 0), (None, 7), (MagicMock(), 7), ("12", 7), (True, 7), (3.5, 7),
])
def test_as_int(value, expected):
    assert _as_int(value, 7) == expected


# ── stream_gemini_chat → usage_box ──────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_box_filled_from_last_chunk(_no_tracking):
    client = _client([_aiter(_chunk("Bon"), _chunk("jour", {"prompt_token_count": 1234,
                                                              "candidates_token_count": 56}))])
    box = {}
    with patch("services.gemini._get_client", return_value=client), \
         patch("services.gemini.gemini_breaker", _breaker()):
        out = await _drain(stream_gemini_chat(MagicMock(), "", "sys", _CONTENTS, usage_box=box))
    assert "".join(out) == "Bonjour"
    assert box == {"tokens_in": 1234, "tokens_out": 56}


@pytest.mark.asyncio
async def test_usage_box_zero_without_usage_metadata(_no_tracking):
    client = _client([_aiter(_chunk("Bonjour"))])
    box = {}
    with patch("services.gemini._get_client", return_value=client), \
         patch("services.gemini.gemini_breaker", _breaker()):
        await _drain(stream_gemini_chat(MagicMock(), "", "sys", _CONTENTS, usage_box=box))
    assert box == {"tokens_in": 0, "tokens_out": 0}


@pytest.mark.asyncio
async def test_usage_box_ignores_non_int_counts(_no_tracking):
    usage = MagicMock()  # attributs MagicMock (pas d'int) → 0
    c = _chunk("Bonjour")
    c.usage_metadata = usage
    client = _client([_aiter(c)])
    box = {}
    with patch("services.gemini._get_client", return_value=client), \
         patch("services.gemini.gemini_breaker", _breaker()):
        await _drain(stream_gemini_chat(MagicMock(), "", "sys", _CONTENTS, usage_box=box))
    assert box == {"tokens_in": 0, "tokens_out": 0}


@pytest.mark.asyncio
async def test_usage_box_429_then_success_keeps_successful_attempt(_no_tracking):
    client = _client([_make_429(), _aiter(_chunk("OK", {"prompt_token_count": 900,
                                                          "candidates_token_count": 40}))])
    box = {}
    with patch("services.gemini._get_client", return_value=client), \
         patch("services.gemini.gemini_breaker", _breaker()), \
         patch("services.gemini.asyncio.sleep", new_callable=AsyncMock):
        out = await _drain(stream_gemini_chat(MagicMock(), "", "sys", _CONTENTS,
                                              max_retries=2, usage_box=box))
    assert "".join(out) == "OK"
    assert box == {"tokens_in": 900, "tokens_out": 40}


@pytest.mark.asyncio
async def test_usage_box_untouched_on_terminal_error(_no_tracking):
    client = _client([_make_429()])
    box = {}
    with patch("services.gemini._get_client", return_value=client), \
         patch("services.gemini.gemini_breaker", _breaker()):
        await _drain(stream_gemini_chat(MagicMock(), "", "sys", _CONTENTS, usage_box=box))
    assert box == {}


# ── stream_and_respond → log_from_meta ──────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("strict", [False, True])
async def test_stream_and_respond_logs_tokens(strict, _no_tracking):
    from services.chat_pipeline_gemini import stream_and_respond
    client = _client([_aiter(_chunk("Le 7 est sorti.", {"prompt_token_count": 1234,
                                                          "candidates_token_count": 56}))])
    with patch("services.gemini._get_client", return_value=client), \
         patch("services.gemini.gemini_breaker", _breaker()), \
         patch("services.chat_pipeline_gemini.log_from_meta") as mock_log:
        await _drain(stream_and_respond(_ctx(strict), "FB", "[T]", "loto", "fr",
                                        "msg", "page", "chat", stream_fn=stream_gemini_chat))
    kw = mock_log.call_args.kwargs
    assert (kw["tokens_in"], kw["tokens_out"]) == (1234, 56)


@pytest.mark.asyncio
async def test_stream_and_respond_custom_stream_fn_zero_tokens_no_typeerror():
    from services.chat_pipeline_gemini import stream_and_respond

    async def _legacy_stream(*args, **kwargs):  # signature historique (sans usage_box)
        yield "Bonjour"

    with patch("services.chat_pipeline_gemini.log_from_meta") as mock_log:
        await _drain(stream_and_respond(_ctx(), "FB", "[T]", "loto", "fr",
                                        "msg", "page", "chat", stream_fn=_legacy_stream))
    kw = mock_log.call_args.kwargs
    assert (kw["tokens_in"], kw["tokens_out"]) == (0, 0)


# ── call_gemini_and_respond (hors flux) ─────────────────────────────────

def _nonstream_ctx():
    return {
        "mode": "balanced", "_http_client": MagicMock(), "gem_api_key": "",
        "system_prompt": "sys", "contents": [], "insult_prefix": "", "history": [],
        "_chat_meta": {"phase": "1", "t0": 0, "lang": "fr"},
    }


@pytest.mark.asyncio
async def test_non_stream_logs_tokens(mock_vertex_client):
    from services.chat_pipeline_gemini import call_gemini_and_respond
    with mock_vertex_client() as vc, \
         patch("services.chat_pipeline_gemini.log_from_meta") as mock_log:
        vc.set_response(text="OK", tin=10, tout=5)
        await call_gemini_and_respond(_nonstream_ctx(), "fb", "[T]", "loto", "fr", "q", "home")
    kw = mock_log.call_args.kwargs
    assert (kw["tokens_in"], kw["tokens_out"]) == (10, 5)


@pytest.mark.asyncio
async def test_non_stream_without_usage_metadata_zero(mock_vertex_client):
    from services.chat_pipeline_gemini import call_gemini_and_respond
    with mock_vertex_client() as vc, \
         patch("services.chat_pipeline_gemini.log_from_meta") as mock_log:
        vc.set_response(text="OK")
        vc.client.aio.models.generate_content.return_value.usage_metadata = None
        await call_gemini_and_respond(_nonstream_ctx(), "fb", "[T]", "loto", "fr", "q", "home")
    kw = mock_log.call_args.kwargs
    assert (kw["tokens_in"], kw["tokens_out"]) == (0, 0)


# ── log_from_meta → log_chat_exchange ───────────────────────────────────

def test_log_from_meta_forwards_tokens():
    from services.chat_pipeline_gemini import log_from_meta
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_lce:
        log_from_meta({"t0": 0, "phase": "1"}, "loto", "fr", "q", "r", tokens_in=1234, tokens_out=56)
    kw = mock_lce.call_args.kwargs
    assert (kw["gemini_tokens_in"], kw["gemini_tokens_out"]) == (1234, 56)


def test_log_from_meta_default_tokens_zero():
    from services.chat_pipeline_gemini import log_from_meta
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_lce:
        log_from_meta({"t0": 0}, "loto", "fr", "q", "r")
    kw = mock_lce.call_args.kwargs
    assert (kw["gemini_tokens_in"], kw["gemini_tokens_out"]) == (0, 0)
