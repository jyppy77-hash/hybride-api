"""
V131.B — Tests fidèles du retry V129.1 dans handle_pitch_common (Vertex AI SDK B).

Scope : valider la calibration retry 2/4/8s + jitter [0,1s] + cap total 14s +
CB check per-iteration. Scope métier critique (calibration empirique post-incident
17-22/04/2026, logs prod). Rigueur > pragmatisme — anti-flakiness via patches
déterministes (asyncio.sleep + random.uniform) ciblés module-level
services.chat_pipeline_gemini.* pour éviter pollution asyncio.wait_for interne.
"""

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from services.chat_pipeline_gemini import handle_pitch_common


async def _fake_context_coro():
    return "mock stats context"


def _load_prompt_fn(name):
    return "mock pitch prompt"


async def _handle_pitch_common_with_retry(*, max_retries, breaker=None):
    """Helper DRY : appelle handle_pitch_common avec params standardisés."""
    from services.gemini_cache import pitch_cache
    pitch_cache.clear()
    grilles_data = {"test": True}  # dict unique par appel pour éviter cache hit
    return await handle_pitch_common(
        grilles_data=grilles_data,
        http_client=MagicMock(),
        lang="fr",
        context_coro=_fake_context_coro(),
        load_prompt_fn=_load_prompt_fn,
        prompt_name="PITCH_TEST",
        log_prefix="[TEST V131.B]",
        breaker=breaker,
        timeout_context=5,
        timeout_gemini=10,
        max_retries=max_retries,
    )


class TestV131PitchRetry:
    """V129.1 retry calibration fidèle : 2/4/8s + jitter fixe 0.5s + cap 14s."""

    @pytest.mark.asyncio
    async def test_retry_429_3x_then_success_fidele(self, mock_vertex_client, make_client_error):
        """3 × ClientError(429) puis succès → 3 sleeps 2.5/4.5/8.5s + response OK."""
        with mock_vertex_client() as vc, \
             patch("services.chat_pipeline_gemini.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("services.chat_pipeline_gemini.random.uniform", return_value=0.5):

            # Succès JSON valide après 3 × 429
            resp = MagicMock()
            resp.text = '{"pitchs": ["retry success"]}'
            resp.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=5)

            vc.client.aio.models.generate_content = AsyncMock(side_effect=[
                make_client_error(429),
                make_client_error(429),
                make_client_error(429),
                resp,
            ])

            result = await _handle_pitch_common_with_retry(max_retries=3)

        assert result["success"] is True
        assert result["data"]["pitchs"] == ["retry success"]
        # Fidélité backoff V129.1 : base 2s * 2^attempt + jitter 0.5
        # attempt 0: 2 + 0.5 = 2.5s
        # attempt 1: 4 + 0.5 = 4.5s
        # attempt 2: 8 + 0.5 = 8.5s
        assert mock_sleep.call_args_list == [call(2.5), call(4.5), call(8.5)]
        assert vc.client.aio.models.generate_content.await_count == 4

    @pytest.mark.asyncio
    async def test_retry_429_all_exhausted(self, mock_vertex_client, make_client_error):
        """4 × ClientError(429) avec max_retries=3 → retry exhausted, fallback timeout."""
        with mock_vertex_client() as vc, \
             patch("services.chat_pipeline_gemini.asyncio.sleep", new_callable=AsyncMock), \
             patch("services.chat_pipeline_gemini.random.uniform", return_value=0.5):
            vc.set_error(make_client_error(429))

            result = await _handle_pitch_common_with_retry(max_retries=3)

        assert result["success"] is False
        assert result["status_code"] == 503
        assert "Timeout Gemini" in result["error"]
        # 4 tentatives : attempt 0, 1, 2, 3 (max_retries+1)
        assert vc.client.aio.models.generate_content.await_count == 4

    @pytest.mark.asyncio
    async def test_retry_non_429_no_retry(self, mock_vertex_client, make_client_error):
        """ClientError(400) non-429 → 1 seul appel, pas de retry."""
        with mock_vertex_client() as vc, \
             patch("services.chat_pipeline_gemini.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            vc.set_error(make_client_error(400))

            result = await _handle_pitch_common_with_retry(max_retries=3)

        assert result["success"] is False
        assert result["status_code"] == 500
        # Pas de retry sur non-429
        assert vc.client.aio.models.generate_content.await_count == 1
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_cb_open_aborts(self, mock_vertex_client, make_client_error):
        """CB state = OPEN au start → short-circuit immédiat, 0 tentative Gemini.

        Note : dans handle_pitch_common, _record_failure() n'est appelé QU'EN fin
        de loop (branche 429 exhausted OU non-429). Le CB ne peut donc pas devenir
        OPEN mid-retry via 429 successifs (chaque 429 intermédiaire → sleep + continue).
        On force le CB en OPEN manuellement pour tester le check state avant appel.
        """
        import time as _time
        from services.circuit_breaker import GeminiCircuitBreaker
        breaker = GeminiCircuitBreaker(failure_threshold=1, open_timeout=60.0)
        # Force state OPEN avec _opened_at récent (sinon timeout 60s expire → HALF_OPEN)
        breaker._state = breaker.OPEN
        breaker._opened_at = _time.monotonic()

        with mock_vertex_client() as vc:
            vc.set_error(make_client_error(429))
            result = await _handle_pitch_common_with_retry(max_retries=3, breaker=breaker)

        assert result["success"] is False
        assert result["status_code"] == 503
        # CB OPEN avant 1ère tentative → 0 appel Gemini
        assert vc.client.aio.models.generate_content.await_count == 0

    @pytest.mark.asyncio
    async def test_retry_cap_14s_exhausted(self, mock_vertex_client, make_client_error):
        """Cap total 14s dépassé mid-retry → break boucle.

        Utilise fonction calculée (chaque appel time.monotonic avance de 5s)
        pour robustesse aux changements d'ordre interne (Objection #1 Jyppy).
        Pattern : état dans list mutable, step 5s → cap atteint après ~3 appels.
        """
        _mono_state = [0.0]

        def _fake_monotonic():
            _mono_state[0] += 5.0
            return _mono_state[0]

        with mock_vertex_client() as vc, \
             patch("services.chat_pipeline_gemini.asyncio.sleep", new_callable=AsyncMock), \
             patch("services.chat_pipeline_gemini.random.uniform", return_value=0.5), \
             patch("services.chat_pipeline_gemini.time.monotonic", side_effect=_fake_monotonic):
            vc.set_error(make_client_error(429))

            result = await _handle_pitch_common_with_retry(max_retries=3)

        assert result["success"] is False
        assert result["status_code"] == 503
        # Avec step 5s et cap 14s : break déclenché avant exhaustion complète
        # Nombre exact de tentatives dépend de l'implémentation, mais < max_retries+1=4
        assert vc.client.aio.models.generate_content.await_count <= 3
