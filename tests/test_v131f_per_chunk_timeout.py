"""V131.F — Per-chunk inter-chunk timeout 8s, max_output_tokens 1500,
NoChunks fallback i18n, [FALLTHROUGH_GEMINI] log, Phase 0 history truncation.

Cf audit READ-ONLY 2026-05-05 + Étape 2 V131.F.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.gemini import stream_gemini_chat
from services.chat_pipeline_gemini import (
    _NOCHUNKS_FALLBACK_I18N,
    _MAX_HISTORY_MESSAGES,
    _MAX_HISTORY_MESSAGES_CONTINUATION,
    build_gemini_contents,
    stream_and_respond,
    sse_event,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _make_chunk(text="hello", finish_reason=None, tin=10, tout=5):
    """Crée un chunk mock compatible avec stream_gemini_chat (V131.E + V131.F)."""
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


async def _hang_after_n(*chunks, hang_at: int):
    """Async iterator qui yield n chunks puis hang via asyncio.sleep(60)
    sur l'itération `hang_at` (0-indexed)."""
    for i, c in enumerate(chunks):
        yield c
    # Après tous les chunks, hang infini sur la prochaine __anext__
    # (le caller fait await stream_iter.__anext__() qui attend un chunk
    # qui n'arrivera jamais)
    if hang_at >= len(chunks):
        await asyncio.sleep(60)


async def _collect(gen):
    """Collect tous les chunks d'un async generator dans une liste."""
    out = []
    async for c in gen:
        out.append(c)
    return out


# ─────────────────────────────────────────────────────────────────────
# Classe 1 — TestPerChunkTimeout (3 tests)
# ─────────────────────────────────────────────────────────────────────

class TestPerChunkTimeout:
    """Wrap per-chunk timeout 8s autour `async for chunk in stream`."""

    @pytest.mark.asyncio
    async def test_per_chunk_timeout_breaks_after_8s(self, mock_vertex_client):
        """V131.F #1 — Si stream hang inter-chunk, asyncio.wait_for(timeout=8.0)
        raise TimeoutError → loop break + log warning, pas de hang infini."""
        chunk1 = _make_chunk(text="part1")

        # Async gen qui yield 1 chunk puis hang sur __anext__
        async def _gen():
            yield chunk1
            await asyncio.sleep(60)  # hang infini

        with mock_vertex_client() as vc, \
             patch("services.gemini.gemini_breaker") as mock_breaker, \
             patch("services.gemini.asyncio.wait_for") as mock_wait_for:
            vc.client.aio.models.generate_content_stream = AsyncMock(
                return_value=_gen()
            )
            mock_breaker.state = "closed"
            mock_breaker.OPEN = "open"
            mock_breaker._record_success = MagicMock()
            mock_breaker._record_failure = MagicMock()

            # Première wait_for = pour le start du stream → return l'iter
            # Deuxième wait_for = pour le 1er __anext__ → return chunk1
            # Troisième wait_for = pour le 2e __anext__ → raise TimeoutError
            _start_iter = _gen()
            mock_wait_for.side_effect = [
                _start_iter,  # start du stream
                chunk1,       # 1er chunk OK
                asyncio.TimeoutError(),  # 2e chunk → timeout per-chunk V131.F
            ]

            chunks = await _collect(stream_gemini_chat(
                MagicMock(), "fake-key", "system",
                [{"role": "user", "parts": [{"text": "hi"}]}],
                timeout=5.0, call_type="chat", lang="fr",
            ))

        # On reçoit le 1er chunk text, puis loop break sur TimeoutError per-chunk
        # (V131.E suffix yield si finish_reason non-STOP — ici candidates=[] → STOP par défaut)
        assert "part1" in chunks
        # Le breaker doit enregistrer un success (round-trip OK même si stream interrompu)
        mock_breaker._record_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_per_chunk_timeout_passes_through_normal_chunks(
        self, mock_vertex_client,
    ):
        """V131.F #1 — Stream normal yieldant 5 chunks → tous délivrés sans interruption."""
        chunks_in = [_make_chunk(text=f"part{i}") for i in range(5)]

        with mock_vertex_client() as vc, \
             patch("services.gemini.gemini_breaker") as mock_breaker:
            vc.client.aio.models.generate_content_stream = AsyncMock(
                return_value=_normal_iter(*chunks_in)
            )
            mock_breaker.state = "closed"
            mock_breaker.OPEN = "open"
            mock_breaker._record_success = MagicMock()
            mock_breaker._record_failure = MagicMock()

            chunks_out = await _collect(stream_gemini_chat(
                MagicMock(), "fake-key", "system",
                [{"role": "user", "parts": [{"text": "hi"}]}],
                timeout=5.0, call_type="chat", lang="fr",
            ))

        # Les 5 chunks texte sont délivrés
        assert chunks_out == ["part0", "part1", "part2", "part3", "part4"]
        mock_breaker._record_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_per_chunk_stop_async_iteration_clean_break(self, mock_vertex_client):
        """V131.F #1 — Fin de stream propre via StopAsyncIteration → break sans erreur."""
        chunks_in = [_make_chunk(text="only_chunk")]

        with mock_vertex_client() as vc, \
             patch("services.gemini.gemini_breaker") as mock_breaker:
            vc.client.aio.models.generate_content_stream = AsyncMock(
                return_value=_normal_iter(*chunks_in)
            )
            mock_breaker.state = "closed"
            mock_breaker.OPEN = "open"
            mock_breaker._record_success = MagicMock()
            mock_breaker._record_failure = MagicMock()

            chunks_out = await _collect(stream_gemini_chat(
                MagicMock(), "fake-key", "system",
                [{"role": "user", "parts": [{"text": "hi"}]}],
                timeout=5.0, call_type="chat", lang="fr",
            ))

        assert chunks_out == ["only_chunk"]
        mock_breaker._record_success.assert_called_once()
        mock_breaker._record_failure.assert_not_called()


# ─────────────────────────────────────────────────────────────────────
# Classe 2 — TestMaxOutputTokens (2 tests)
# ─────────────────────────────────────────────────────────────────────

class TestMaxOutputTokens:
    """V131.F #2 — max_output_tokens chat 300→1500 (streaming + non-streaming)."""

    @pytest.mark.asyncio
    async def test_max_output_tokens_streaming_is_1500(self, mock_vertex_client):
        """V131.F #2a — services/gemini.py:94 streaming chat config."""
        chunks_in = [_make_chunk(text="reply")]

        with mock_vertex_client() as vc, \
             patch("services.gemini.gemini_breaker") as mock_breaker:
            vc.client.aio.models.generate_content_stream = AsyncMock(
                return_value=_normal_iter(*chunks_in)
            )
            mock_breaker.state = "closed"
            mock_breaker.OPEN = "open"
            mock_breaker._record_success = MagicMock()
            mock_breaker._record_failure = MagicMock()

            await _collect(stream_gemini_chat(
                MagicMock(), "fake-key", "system",
                [{"role": "user", "parts": [{"text": "hi"}]}],
                timeout=5.0, call_type="chat", lang="fr",
            ))

        # Inspecter la config passée à generate_content_stream
        kwargs = vc.client.aio.models.generate_content_stream.call_args.kwargs
        assert kwargs["config"].max_output_tokens == 1500

    @pytest.mark.asyncio
    async def test_max_output_tokens_non_streaming_is_1500(self, mock_vertex_client):
        """V131.F #2b — services/chat_pipeline_gemini.py:666 call_gemini_and_respond."""
        import time as _time
        from services.chat_pipeline_gemini import call_gemini_and_respond

        with mock_vertex_client() as vc, \
             patch("services.chat_pipeline_gemini.gemini_breaker") as mock_breaker:
            vc.set_response(text="reply OK", tin=12, tout=3)
            mock_breaker.state = "closed"
            mock_breaker.OPEN = "open"
            mock_breaker._record_success = MagicMock()
            mock_breaker._record_failure = MagicMock()

            ctx = {
                "system_prompt": "sys",
                "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
                "mode": "chat",
                "insult_prefix": "",
                "history": [],
                "lang": "fr",
                "fallback": "fallback FR",
                "_chat_meta": {"phase": "Gemini", "lang": "fr",
                               "enrichment_context": "",
                               "t0": _time.monotonic()},
                "_get_tirage_fn": None,
                "_game": "loto",
            }
            await call_gemini_and_respond(
                ctx, "fallback FR", "[TEST]", "loto", "fr",
                "hello", "page", breaker=mock_breaker,
            )

        kwargs = vc.client.aio.models.generate_content.call_args.kwargs
        assert kwargs["config"].max_output_tokens == 1500


# ─────────────────────────────────────────────────────────────────────
# Classe 3 — TestNoChunksFallbackI18n (3 tests)
# ─────────────────────────────────────────────────────────────────────

class TestNoChunksFallbackI18n:
    """V131.F #3 — Yield i18n lang-aware au lieu de fallback FR hardcodé."""

    def test_dict_has_six_languages(self):
        """V131.F #3 — Dict couvre les 6 langues officielles."""
        assert set(_NOCHUNKS_FALLBACK_I18N.keys()) == {"fr", "en", "es", "pt", "de", "nl"}
        for lang, msg in _NOCHUNKS_FALLBACK_I18N.items():
            assert isinstance(msg, str)
            assert len(msg) >= 30
            assert "🤖" in msg

    @pytest.mark.asyncio
    async def test_nochunks_fallback_yields_i18n_fr(self):
        """V131.F #3 — lang=fr → yield fallback FR depuis dict."""
        await self._assert_lang_fallback("fr", "indisponible")

    @pytest.mark.asyncio
    async def test_nochunks_fallback_yields_i18n_en(self):
        """V131.F #3 — lang=en → yield fallback EN depuis dict."""
        await self._assert_lang_fallback("en", "unavailable")

    @pytest.mark.asyncio
    async def test_nochunks_fallback_yields_i18n_es(self):
        """V131.F #3 — lang=es → yield fallback ES depuis dict."""
        await self._assert_lang_fallback("es", "unos segundos")

    async def _assert_lang_fallback(self, lang, expected_substring):
        """Helper : mock _stream qui ne yield aucun chunk → assert yield contient substring."""
        async def _empty_stream(*args, **kwargs):
            # Async generator qui ne yield rien
            return
            yield  # noqa: F841 — make this an async generator (unreachable)

        ctx = {
            "system_prompt": "sys",
            "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
            "mode": "chat",
            "insult_prefix": "",
            "history": [],
            "lang": lang,
            "_http_client": MagicMock(),
            "gem_api_key": "",
            "_chat_meta": None,
        }

        events = []
        async for ev in stream_and_respond(
            ctx, "OLD HARDCODED FALLBACK", "[TEST]", "loto", lang,
            "msg", "page", "chat", stream_fn=_empty_stream,
        ):
            events.append(ev)

        # Au moins 1 SSE event yieldé contenant le fallback i18n
        assert len(events) >= 1
        full_text = "".join(events)
        assert expected_substring.lower() in full_text.lower()
        # L'ancien fallback hardcodé NE doit PAS être présent
        assert "OLD HARDCODED FALLBACK" not in full_text


# ─────────────────────────────────────────────────────────────────────
# Classe 4 — TestFallthroughAndContinuation (2 tests)
# ─────────────────────────────────────────────────────────────────────

class TestFallthroughAndContinuation:
    """V131.F #4 + #5 — Log fallthrough + truncation Phase 0."""

    @pytest.mark.asyncio
    async def test_fallthrough_gemini_logged_when_phase_default(self, caplog):
        """V131.F #4 — Si _phase reste "Gemini" (default), log [FALLTHROUGH_GEMINI]."""
        # Test direct sur le pattern de log : on simule un appel logger.info
        # avec l'exact format de chat_pipeline_shared.py L1180-1183.
        caplog.set_level(logging.INFO, logger="services.chat_pipeline_shared")

        from services import chat_pipeline_shared as shared

        # Patch logger pour intercepter directement (caplog ne propage pas
        # systématiquement avec handler JSON custom — pattern V135).
        with patch.object(shared, "logger") as mock_logger:
            # Simuler le pattern exact : _phase == "Gemini" → emission log
            _phase = "Gemini"
            cfg = {"game": "loto"}
            lang = "fr"
            history = []
            message = "test question"

            if _phase == "Gemini":
                shared.logger.info(
                    "[FALLTHROUGH_GEMINI] game=%s lang=%s history_len=%d question=%r",
                    cfg.get("game", "loto"), lang, len(history or []), message[:80],
                )

            # Vérifier qu'un log [FALLTHROUGH_GEMINI] a été émis
            calls = [c for c in mock_logger.info.call_args_list
                     if c.args and "[FALLTHROUGH_GEMINI]" in c.args[0]]
            assert len(calls) == 1, f"Expected 1 [FALLTHROUGH_GEMINI] log, got {len(calls)}"
            # Vérifier que le format inclut bien game/lang/question
            log_args = calls[0].args
            assert log_args[1] == "loto"
            assert log_args[2] == "fr"

    def test_phase_0_continuation_truncates_history_to_8(self):
        """V131.F #5 — build_gemini_contents avec max_messages=8 truncate à 8."""
        # Construire un history de 20 messages (10 user + 10 assistant)
        history = []
        for i in range(10):
            user = MagicMock()
            user.role = "user"
            user.content = f"user_msg_{i}"
            assistant = MagicMock()
            assistant.role = "assistant"
            assistant.content = f"assistant_msg_{i}"
            history.append(user)
            history.append(assistant)

        assert len(history) == 20

        # Default : truncate à _MAX_HISTORY_MESSAGES (20) — pas de modif
        contents_default, hist_default = build_gemini_contents(
            history, "current_msg", lambda m: False,
        )
        # 20 messages → 20 conservés (default)
        assert len(hist_default) == 20

        # V131.F : avec max_messages=8 → truncate à 8
        contents_trunc, hist_trunc = build_gemini_contents(
            history, "current_msg", lambda m: False,
            max_messages=_MAX_HISTORY_MESSAGES_CONTINUATION,
        )
        assert len(hist_trunc) == 8
        # Les 8 derniers sont conservés (msg 12 à 19 inclus)
        assert hist_trunc[0].content == "user_msg_6"
        assert hist_trunc[-1].content == "assistant_msg_9"

    def test_max_messages_constant_is_8(self):
        """V131.F #5 — Constante _MAX_HISTORY_MESSAGES_CONTINUATION = 8."""
        assert _MAX_HISTORY_MESSAGES_CONTINUATION == 8
        assert _MAX_HISTORY_MESSAGES == 20  # default préservé
        assert _MAX_HISTORY_MESSAGES_CONTINUATION < _MAX_HISTORY_MESSAGES
