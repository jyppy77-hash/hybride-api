"""
V129.1 — Tests calibration retry/CB + httpx timeout strict (Release 1.6.015).

Couverture des 3 fixes chirurgicaux post-mortem logs prod 21/04/2026 :
  1. Backoff exponential LARGE (2/4/8s vs 200/400ms) + cap total 14s
  2. Threshold CB pitch 3 → 10 (absorbe throttle adaptatif Google)
  3. httpx timeout 10s strict sur les 4 call sites Gemini
     (fix bonus : gemini_shared.py n'avait PAS de timeout → hang 15s observé)
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from services.circuit_breaker import (
    GeminiCircuitBreaker,
    gemini_breaker_pitch,
    gemini_breaker_chat,
    gemini_breaker_sql,
    _V129_RETRY_BACKOFF_BASE,
    _V129_RETRY_CAP_TOTAL,
    _V129_RETRY_JITTER_MAX,
)


def _mock_response(status_code, retry_after=None):
    """Build a minimal httpx-like response mock."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"retry-after": retry_after} if retry_after is not None else {}
    return resp


def _mock_client(responses):
    """Build an async client whose .post() returns responses sequentially."""
    client = MagicMock()
    client.post = AsyncMock(side_effect=responses)
    return client


# ═══════════════════════════════════════════════════════════════════════
# 1-3. Backoff exponential LARGE (2/4/8s) + cap 14s
# ═══════════════════════════════════════════════════════════════════════

class TestBackoffLargeV129_1:

    @pytest.mark.asyncio
    async def test_backoff_exponential_large_2s_4s(self):
        """V129.1 : 429, 429, 200 → backoffs dans [2s, 3s] puis [4s, 5s]
        (base 2/4s + jitter [0, 1s])."""
        breaker = GeminiCircuitBreaker(failure_threshold=5)
        client = _mock_client([
            _mock_response(429), _mock_response(429), _mock_response(200),
        ])
        with patch("services.circuit_breaker.asyncio.sleep", AsyncMock()) as sleep:
            resp = await breaker.call(client, "https://example.com", max_retries=2)
            assert resp.status_code == 200
            assert sleep.call_count == 2
            b0 = sleep.call_args_list[0][0][0]
            b1 = sleep.call_args_list[1][0][0]
            assert 2.0 <= b0 <= 2.0 + _V129_RETRY_JITTER_MAX
            assert 4.0 <= b1 <= 4.0 + _V129_RETRY_JITTER_MAX

    @pytest.mark.asyncio
    async def test_backoff_first_attempt_in_range_2_3s(self):
        """V129.1 : premier backoff ∈ [2.0, 3.0]s (base 2s + jitter [0, 1s])."""
        breaker = GeminiCircuitBreaker(failure_threshold=5)
        client = _mock_client([_mock_response(429), _mock_response(200)])
        with patch("services.circuit_breaker.asyncio.sleep", AsyncMock()) as sleep:
            await breaker.call(client, "https://example.com", max_retries=2)
            sleep.assert_called_once()
            backoff = sleep.call_args[0][0]
            assert 2.0 <= backoff <= 2.0 + _V129_RETRY_JITTER_MAX

    @pytest.mark.asyncio
    async def test_cap_total_14s_not_3s(self):
        """V129.1 : cap total wall time = 14s (était 3s). Vérif via mock time.
        Et vérif des constantes exposées _V129_RETRY_BACKOFF_BASE / _V129_RETRY_CAP_TOTAL.
        """
        breaker = GeminiCircuitBreaker(failure_threshold=5)
        client = _mock_client([
            _mock_response(429), _mock_response(429), _mock_response(429),
        ])
        # Simuler temps écoulé 14.5s après 1er attempt → cap doit break
        times = iter([0.0, 0.1, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5])
        with (
            patch("services.circuit_breaker.asyncio.sleep", AsyncMock()),
            patch("services.circuit_breaker.time.monotonic", side_effect=lambda: next(times)),
        ):
            resp = await breaker.call(client, "https://example.com", max_retries=5)
            assert resp.status_code == 429
        assert _V129_RETRY_CAP_TOTAL == 14.0
        assert _V129_RETRY_BACKOFF_BASE == 2.0

    @pytest.mark.asyncio
    async def test_backoff_has_jitter_no_collision(self):
        """V129.1 refinement : jitter [0, 1s] évite les retries synchronisés
        (thundering herd). Deux appels successifs avec même attempt=0 doivent
        donner des backoffs DIFFÉRENTS (variance aléatoire présente).

        Note : collision théorique possible sur 2 échantillons (P≈0). On
        collecte 10 backoffs et on vérifie que l'écart-type est non-nul.
        """
        backoffs = []
        for _ in range(10):
            breaker = GeminiCircuitBreaker(failure_threshold=5)
            client = _mock_client([_mock_response(429), _mock_response(200)])
            with patch("services.circuit_breaker.asyncio.sleep", AsyncMock()) as sleep:
                await breaker.call(client, "https://example.com", max_retries=2)
                backoffs.append(sleep.call_args[0][0])
        # Tous dans [2.0, 3.0]
        assert all(2.0 <= b <= 3.0 for b in backoffs), f"out-of-range: {backoffs}"
        # Variance non-nulle → jitter effectif
        assert len(set(backoffs)) > 1, (
            f"All backoffs identical ({backoffs[0]}) — jitter missing: "
            f"2 users en 429 simultanés retry synchronisés → collision."
        )


# ═══════════════════════════════════════════════════════════════════════
# 4-7. Threshold CB pitch 3 → 10
# ═══════════════════════════════════════════════════════════════════════

class TestCbPitchThreshold10:

    def test_cb_pitch_threshold_is_10(self):
        """V129.1 : gemini_breaker_pitch.failure_threshold == 10."""
        assert gemini_breaker_pitch._failure_threshold == 10

    def test_cb_chat_sql_thresholds_unchanged(self):
        """V129.1 : chat=5, sql=3 inchangés (throttle pitch isolé)."""
        assert gemini_breaker_chat._failure_threshold == 5
        assert gemini_breaker_sql._failure_threshold == 3

    def test_cb_pitch_not_open_after_8_failures(self):
        """V129.1 : 8 failures < 10 → CB reste CLOSED (marge confirmée)."""
        breaker = GeminiCircuitBreaker(failure_threshold=10)
        for _ in range(8):
            breaker._record_failure()
        assert breaker.state == breaker.CLOSED
        assert breaker._failure_count == 8

    def test_cb_pitch_open_after_10_failures(self):
        """V129.1 : 10 failures atteignent le threshold → CB OPEN."""
        breaker = GeminiCircuitBreaker(failure_threshold=10)
        for _ in range(10):
            breaker._record_failure()
        assert breaker.state == breaker.OPEN


# ═══════════════════════════════════════════════════════════════════════
# 8-10. httpx timeout 10s strict — vérification AST des call sites Gemini
# ═══════════════════════════════════════════════════════════════════════

class TestHttpxTimeoutGeminiExplicit:

    def test_gemini_shared_has_explicit_timeout(self):
        """V129.1 fix bonus : gemini_shared.py doit avoir timeout=10.0 explicite
        dans l'appel _breaker.call() (fix hang 15s observé en half_open).
        Sans ce fix, la requête retombait sur le default AsyncClient (20s).
        """
        import inspect
        import services.gemini_shared as gs
        src = inspect.getsource(gs.enrich_analysis_base)
        assert "timeout=10.0" in src, (
            "enrich_analysis_base() must pass timeout=10.0 to _breaker.call() — "
            "missing causes fallback to AsyncClient default (20s hang)."
        )

    def test_gemini_stream_default_timeout_10(self):
        """V129.1 : stream_gemini_chat default timeout = 10.0s (était 15.0s)."""
        import inspect
        from services.gemini import stream_gemini_chat
        sig = inspect.signature(stream_gemini_chat)
        assert sig.parameters["timeout"].default == 10.0

    def test_handle_pitch_common_default_timeout_10(self):
        """V129.1 : handle_pitch_common default timeout_gemini = 10 (était 15)."""
        import inspect
        from services.chat_pipeline_gemini import handle_pitch_common
        sig = inspect.signature(handle_pitch_common)
        assert sig.parameters["timeout_gemini"].default == 10
