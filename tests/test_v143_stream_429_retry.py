"""V143 — Retry 429 chat streaming (pattern V129.1) + error_detail différencié
+ timeout 1er-token 15s distinct de l'inter-chunk 8s.

Cf audits READ-ONLY 11/06/2026 : NoChunks 52%/24h = 429 DSQ régional Vertex
(gemini-2.5-flash europe-west1, aucun quota RPM par projet, capacité partagée).
Garde anti-double-émission SSE `_yielded_any` = LE point critique du lot.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from google.genai import errors as genai_errors

from services.gemini import stream_gemini_chat


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _make_chunk(text="hello", finish_reason=None, tin=10, tout=5):
    """Crée un chunk mock compatible avec stream_gemini_chat (pattern V131.F)."""
    chunk = MagicMock()
    chunk.text = text
    if finish_reason is not None:
        cand = MagicMock()
        cand.finish_reason = finish_reason
        chunk.candidates = [cand]
    else:
        chunk.candidates = []
    chunk.usage_metadata = MagicMock(
        prompt_token_count=tin,
        candidates_token_count=tout,
    )
    return chunk


async def _normal_iter(*chunks):
    """Async iterator qui yield les chunks normalement puis termine."""
    for c in chunks:
        yield c


def _make_429():
    """ClientError 429 sans dépendre de la signature du constructeur SDK
    (varie selon versions google-genai) — attributs lus par _is_rate_limit_error."""
    err = genai_errors.ClientError.__new__(genai_errors.ClientError)
    Exception.__init__(
        err, "429 RESOURCE_EXHAUSTED: Resource exhausted. Please try again later.")
    err.code = 429
    err.status = "RESOURCE_EXHAUSTED"
    return err


def _make_server_error(code=500):
    """ServerError 5xx (non-429) — ne doit JAMAIS déclencher le retry V143."""
    err = genai_errors.ServerError.__new__(genai_errors.ServerError)
    Exception.__init__(err, f"{code} INTERNAL: internal error")
    err.code = code
    err.status = "INTERNAL"
    return err


def _make_client(stream_side_effect):
    """Client Vertex mock — generate_content_stream pilote via side_effect
    (exception → raise au await ; valeur → async iterator retourné)."""
    client = MagicMock()
    client.aio.models.generate_content_stream = AsyncMock(side_effect=stream_side_effect)
    return client


def _make_breaker(state="closed"):
    """Breaker mock pattern test_v131f (state str + OPEN sentinel)."""
    breaker = MagicMock()
    breaker.state = state
    breaker.OPEN = "open"
    breaker._record_success = MagicMock()
    breaker._record_failure = MagicMock()
    return breaker


async def _collect(gen):
    """Collect tous les chunks d'un async generator dans une liste."""
    out = []
    async for c in gen:
        out.append(c)
    return out


_CONTENTS = [{"role": "user", "parts": [{"text": "hi"}]}]


def _call_stream(box=None, max_retries=2, **kw):
    """Appel stream_gemini_chat avec kwargs V143 par défaut."""
    return stream_gemini_chat(
        MagicMock(), "fake-key", "system", _CONTENTS,
        timeout=5.0, call_type="chat", lang="fr",
        max_retries=max_retries, failure_box=box, **kw,
    )


# ─────────────────────────────────────────────────────────────────────
# Classe 1 — TestStream429Retry (5 tests)
# ─────────────────────────────────────────────────────────────────────

class TestStream429Retry:
    """V143 #2 — retry 429 pattern V129.1 : opt-in, backoff, cap, 429-only."""

    @pytest.mark.asyncio
    async def test_retry_on_429_then_success(self):
        """429 au 1er essai → backoff [2,3]s → succès au 2e essai, chunks délivrés."""
        client = _make_client([_make_429(), _normal_iter(_make_chunk("ok"))])
        box = {}

        with patch("services.gemini._get_client", return_value=client), \
             patch("services.gemini.gemini_breaker", _make_breaker()) as breaker, \
             patch("services.gemini.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            chunks = await _collect(_call_stream(box=box))

        assert chunks == ["ok"]
        assert client.aio.models.generate_content_stream.call_count == 2
        # Backoff V129.1 attempt 0 : 2.0 + jitter [0,1] → [2.0, 3.0]
        mock_sleep.assert_awaited_once()
        backoff = mock_sleep.await_args.args[0]
        assert 2.0 <= backoff <= 3.0
        # Retry silencieux : succès final → record_success, JAMAIS record_failure
        breaker._record_success.assert_called_once()
        breaker._record_failure.assert_not_called()
        assert "cause" not in box

    @pytest.mark.asyncio
    async def test_429_exhausted_max_retries_2(self):
        """3× 429 avec max_retries=2 → 3 tentatives, zéro chunk, cause=Vertex429."""
        client = _make_client([_make_429(), _make_429(), _make_429()])
        box = {}

        with patch("services.gemini._get_client", return_value=client), \
             patch("services.gemini.gemini_breaker", _make_breaker()) as breaker, \
             patch("services.gemini.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            chunks = await _collect(_call_stream(box=box))

        assert chunks == []
        assert client.aio.models.generate_content_stream.call_count == 3
        assert mock_sleep.await_count == 2  # 2 backoffs (attempts 1 et 2)
        assert box["cause"] == "Vertex429"
        breaker._record_failure.assert_called_once()  # max 1 failure/requête
        breaker._record_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_retries_default_zero_single_attempt(self):
        """Défaut max_retries=0 (rétrocompat V131.F) → 1 seule tentative, pas de sleep."""
        client = _make_client([_make_429()])
        box = {}

        with patch("services.gemini._get_client", return_value=client), \
             patch("services.gemini.gemini_breaker", _make_breaker()) as breaker, \
             patch("services.gemini.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            chunks = await _collect(stream_gemini_chat(
                MagicMock(), "fake-key", "system", _CONTENTS,
                timeout=5.0, call_type="chat", lang="fr",
                failure_box=box,  # max_retries non passé → défaut 0
            ))

        assert chunks == []
        assert client.aio.models.generate_content_stream.call_count == 1
        mock_sleep.assert_not_awaited()
        assert box["cause"] == "Vertex429"
        breaker._record_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_retry_on_server_error_500(self):
        """ServerError 5xx → JAMAIS de retry (failure mode différent), cause=VertexError."""
        client = _make_client([_make_server_error(500)])
        box = {}

        with patch("services.gemini._get_client", return_value=client), \
             patch("services.gemini.gemini_breaker", _make_breaker()) as breaker, \
             patch("services.gemini.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            chunks = await _collect(_call_stream(box=box))

        assert chunks == []
        assert client.aio.models.generate_content_stream.call_count == 1
        mock_sleep.assert_not_awaited()
        assert box["cause"] == "VertexError"  # V143 D2
        breaker._record_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_cap_budget_exhausted_stops_retry(self):
        """Cap wall-time épuisé → pas de retry malgré max_retries restants
        (piège pitch 'no budget left at attempt=1' couvert)."""
        client = _make_client([_make_429()])
        box = {}

        with patch("services.gemini._get_client", return_value=client), \
             patch("services.gemini.gemini_breaker", _make_breaker()) as breaker, \
             patch("services.gemini._V143_RETRY_CAP_TOTAL", 0.0), \
             patch("services.gemini.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            chunks = await _collect(_call_stream(box=box))

        assert chunks == []
        assert client.aio.models.generate_content_stream.call_count == 1
        mock_sleep.assert_not_awaited()
        assert box["cause"] == "Vertex429"
        breaker._record_failure.assert_called_once()


# ─────────────────────────────────────────────────────────────────────
# Classe 2 — TestNoDoubleEmission (2 tests) — LE risque du lot
# ─────────────────────────────────────────────────────────────────────

class TestNoDoubleEmission:
    """V143 — garde `_yielded_any` : retry interdit dès qu'un chunk est émis."""

    @pytest.mark.asyncio
    async def test_429_then_success_chunks_emitted_exactly_once(self):
        """429 → retry → succès : les chunks du 2e essai sont émis UNE fois."""
        client = _make_client([
            _make_429(),
            _normal_iter(_make_chunk("part0"), _make_chunk("part1")),
        ])

        with patch("services.gemini._get_client", return_value=client), \
             patch("services.gemini.gemini_breaker", _make_breaker()), \
             patch("services.gemini.asyncio.sleep", new_callable=AsyncMock):
            chunks = await _collect(_call_stream())

        # Égalité STRICTE : pas de duplication, pas de chunk fantôme du 1er essai
        assert chunks == ["part0", "part1"]

    @pytest.mark.asyncio
    async def test_client_error_after_yield_never_retries(self):
        """429 levé APRÈS un chunk émis → pas de retry (sinon double-émission),
        comportement terminal V131.F préservé (failure + return)."""
        async def _yield_then_429():
            yield _make_chunk("part0")
            raise _make_429()

        client = _make_client([_yield_then_429(), _normal_iter(_make_chunk("dup"))])

        with patch("services.gemini._get_client", return_value=client), \
             patch("services.gemini.gemini_breaker", _make_breaker()) as breaker, \
             patch("services.gemini.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            chunks = await _collect(_call_stream())

        # 1 seul essai consommé : le chunk "dup" du 2e iterator ne sort JAMAIS
        assert chunks == ["part0"]
        assert client.aio.models.generate_content_stream.call_count == 1
        mock_sleep.assert_not_awaited()
        breaker._record_failure.assert_called_once()


# ─────────────────────────────────────────────────────────────────────
# Classe 3 — TestFirstTokenTimeout (2 tests)
# ─────────────────────────────────────────────────────────────────────

class TestFirstTokenTimeout:
    """V143 #5 — fenêtre 1er-token distincte (15s) de l'inter-chunk (8s)."""

    @pytest.mark.asyncio
    async def test_slow_first_token_passes_wide_window(self):
        """1er token lent passe la fenêtre 1er-token, mais le même délai
        inter-chunk est coupé ensuite (fenêtres patchées 0.5 / 0.02)."""
        async def _slow_gen():
            await asyncio.sleep(0.1)   # < 0.5 first-token → passe
            yield _make_chunk("part0")
            await asyncio.sleep(0.1)   # > 0.02 inter-chunk → coupé
            yield _make_chunk("part1")

        client = _make_client([_slow_gen()])
        box = {}

        with patch("services.gemini._get_client", return_value=client), \
             patch("services.gemini.gemini_breaker", _make_breaker()) as breaker, \
             patch("services.gemini._FIRST_TOKEN_TIMEOUT", 0.5), \
             patch("services.gemini._INTER_CHUNK_TIMEOUT", 0.02):
            chunks = await _collect(_call_stream(box=box))

        assert chunks == ["part0"]
        # Un chunk a été émis → pas de cause zéro-chunk
        assert "cause" not in box
        breaker._record_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_zero_token_timeout_sets_interchunktimeout(self):
        """Timeout AVANT le 1er token → zéro chunk + cause=InterChunkTimeout.
        NB : record_success appelé = bug connu #4 V131.F préservé (hors scope V143)."""
        async def _too_slow_gen():
            await asyncio.sleep(0.2)   # > 0.05 first-token → coupé avant 1er token
            yield _make_chunk("never")

        client = _make_client([_too_slow_gen()])
        box = {}

        with patch("services.gemini._get_client", return_value=client), \
             patch("services.gemini.gemini_breaker", _make_breaker()) as breaker, \
             patch("services.gemini._FIRST_TOKEN_TIMEOUT", 0.05), \
             patch("services.gemini._INTER_CHUNK_TIMEOUT", 0.02):
            chunks = await _collect(_call_stream(box=box))

        assert chunks == []
        assert box["cause"] == "InterChunkTimeout"
        # Sémantique V131.F préservée à l'identique (bug #4 signalé, hors scope)
        breaker._record_success.assert_called_once()
        breaker._record_failure.assert_not_called()


# ─────────────────────────────────────────────────────────────────────
# Classe 4 — TestErrorDetailDifferentiation (2 tests, intégration)
# ─────────────────────────────────────────────────────────────────────

class TestErrorDetailDifferentiation:
    """V143 #3 — stream_and_respond logue Vertex429 / NoChunks selon failure_box."""

    def _ctx(self):
        return {
            "system_prompt": "sys",
            "contents": _CONTENTS,
            "mode": "chat",
            "insult_prefix": "",
            "history": [],
            "lang": "fr",
            "_http_client": MagicMock(),
            "gem_api_key": "",
            "_chat_meta": None,
        }

    @pytest.mark.asyncio
    async def test_error_detail_vertex429_end_to_end(self):
        """429 persistant via le VRAI stream_gemini_chat (identity gate active)
        → error_detail='Vertex429' + 1 seul SSE fallback émis."""
        from services.chat_pipeline_gemini import stream_and_respond

        client = _make_client([_make_429(), _make_429(), _make_429()])

        with patch("services.gemini._get_client", return_value=client), \
             patch("services.gemini.gemini_breaker", _make_breaker()), \
             patch("services.gemini.asyncio.sleep", new_callable=AsyncMock), \
             patch("services.chat_pipeline_gemini.log_from_meta") as mock_log:
            events = await _collect(stream_and_respond(
                self._ctx(), "FALLBACK", "[TEST]", "loto", "fr",
                "msg", "page", "chat", stream_fn=stream_gemini_chat,
            ))

        # Identity gate : max_retries=2 transmis → 3 tentatives SDK
        assert client.aio.models.generate_content_stream.call_count == 3
        assert mock_log.call_args.kwargs.get("error_detail") == "Vertex429"
        # 1 seul event SSE fallback (pas de double-émission)
        assert len(events) == 1
        assert "indisponible" in events[0]

    @pytest.mark.asyncio
    async def test_custom_stream_fn_keeps_nochunks_and_no_typeerror(self):
        """stream_fn custom signature historique → aucun TypeError (identity gate)
        + error_detail reste 'NoChunks' (vrai zéro-token sans erreur)."""
        from services.chat_pipeline_gemini import stream_and_respond

        async def _empty_stream(*args, **kwargs):
            return
            yield  # noqa: F841 — async generator (unreachable)

        with patch("services.chat_pipeline_gemini.log_from_meta") as mock_log:
            events = await _collect(stream_and_respond(
                self._ctx(), "FALLBACK", "[TEST]", "loto", "fr",
                "msg", "page", "chat", stream_fn=_empty_stream,
            ))

        assert len(events) == 1
        assert mock_log.call_args.kwargs.get("error_detail") == "NoChunks"


# ─────────────────────────────────────────────────────────────────────
# Classe 5 — TestBreakerAccounting (2 tests)
# ─────────────────────────────────────────────────────────────────────

class TestBreakerAccounting:
    """V143 — retries silencieux (max 1 failure/requête) + check OPEN per-itération."""

    @pytest.mark.asyncio
    async def test_single_failure_despite_n_retries(self):
        """3× 429 (2 retries) → _record_failure exactement 1× (terminal seul)."""
        client = _make_client([_make_429(), _make_429(), _make_429()])

        with patch("services.gemini._get_client", return_value=client), \
             patch("services.gemini.gemini_breaker", _make_breaker()) as breaker, \
             patch("services.gemini.asyncio.sleep", new_callable=AsyncMock):
            await _collect(_call_stream())

        breaker._record_failure.assert_called_once()
        breaker._record_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_breaker_open_during_backoff_aborts_retry(self):
        """OPEN posé (failures concurrentes) pendant le backoff → CircuitOpenError
        au réveil, pas de 2e appel SDK (check per-itération pattern V129.1)."""
        from services.circuit_breaker import CircuitOpenError

        breaker = MagicMock()
        type(breaker).state = PropertyMock(side_effect=["closed", "open"])
        breaker.OPEN = "open"
        client = _make_client([_make_429()])

        with patch("services.gemini._get_client", return_value=client), \
             patch("services.gemini.gemini_breaker", breaker), \
             patch("services.gemini.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(CircuitOpenError):
                await _collect(_call_stream())

        assert client.aio.models.generate_content_stream.call_count == 1
        breaker._record_failure.assert_not_called()  # retry silencieux, abort propre
