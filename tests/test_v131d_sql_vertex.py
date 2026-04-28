"""
V131.D — Tests de migration Vertex AI sur chat_sql.py + chat_sql_em.py.

Cible : asserter que _generate_sql() (Loto) et _generate_sql_em() (EM) utilisent
google-genai SDK B (Vertex AI gemini-2.5-flash) au lieu d'httpx AI Studio
gemini-2.0-flash, avec gestion d'erreurs identique au pattern V131.A
(enrich_analysis_base / call_gemini_and_respond / handle_pitch_common).

Réutilise la fixture mock_vertex_client de tests/conftest.py:251-385.
"""

from unittest.mock import patch

import pytest

from google.genai import errors as genai_errors

from services.chat_sql import _generate_sql
from services.chat_sql_em import _generate_sql_em
from services.circuit_breaker import gemini_breaker_sql


@pytest.fixture(autouse=True)
def _reset_breaker_sql():
    """V131.D — Reset gemini_breaker_sql state avant/après chaque test."""
    gemini_breaker_sql.force_close()
    yield
    gemini_breaker_sql.force_close()


class TestGenerateSqlVertexMigration:
    """V131.D — migration AI Studio → Vertex AI sur _generate_sql / _generate_sql_em."""

    @pytest.mark.asyncio
    async def test_generate_sql_loto_calls_vertex_with_gemini_2_5_flash(
        self, mock_vertex_client,
    ):
        """V131.D — _generate_sql appelle Vertex SDK B avec gemini-2.5-flash + config V131.E."""
        with mock_vertex_client() as vc, \
             patch("services.chat_sql.load_prompt", return_value="SELECT prompt {TODAY}"):
            vc.set_response(text="SELECT * FROM tirages LIMIT 10")
            result = await _generate_sql("freq numero 13", None, None, None)

        assert result == "SELECT * FROM tirages LIMIT 10"
        # Asserter que client.aio.models.generate_content a été appelé exactement 1 fois
        vc.client.aio.models.generate_content.assert_called_once()
        kwargs = vc.client.aio.models.generate_content.call_args.kwargs
        assert kwargs["model"] == "gemini-2.5-flash"
        cfg = kwargs["config"]
        assert cfg.temperature == 0.0
        assert cfg.max_output_tokens == 300
        assert cfg.thinking_config.thinking_budget == 0
        # Asserter system_instruction = prompt avec {TODAY} remplacé
        assert "SELECT prompt" in cfg.system_instruction
        assert "{TODAY}" not in cfg.system_instruction  # remplacé par date.today()

    @pytest.mark.asyncio
    async def test_generate_sql_em_calls_vertex_with_gemini_2_5_flash(
        self, mock_vertex_client,
    ):
        """V131.D — _generate_sql_em appelle Vertex SDK B avec gemini-2.5-flash + lang."""
        with mock_vertex_client() as vc, \
             patch("services.chat_sql_em.load_prompt_em", return_value="EM SQL prompt {TODAY}"):
            vc.set_response(text="SELECT * FROM tirages_euromillions LIMIT 10")
            result = await _generate_sql_em("freq star 5", None, None, None, lang="fr")

        assert result == "SELECT * FROM tirages_euromillions LIMIT 10"
        vc.client.aio.models.generate_content.assert_called_once()
        kwargs = vc.client.aio.models.generate_content.call_args.kwargs
        assert kwargs["model"] == "gemini-2.5-flash"
        cfg = kwargs["config"]
        assert cfg.temperature == 0.0
        assert cfg.max_output_tokens == 300
        assert cfg.thinking_config.thinking_budget == 0
        # Asserter prompt EM utilisé
        assert "EM SQL prompt" in cfg.system_instruction

    @pytest.mark.asyncio
    async def test_generate_sql_429_records_failure_and_returns_none(
        self, mock_vertex_client, make_client_error, caplog,
    ):
        """V131.D — 429 ResourceExhausted → _record_failure + retour None + log warning."""
        before = gemini_breaker_sql._failure_count

        with mock_vertex_client() as vc, \
             patch("services.chat_sql.load_prompt", return_value="prompt"):
            vc.set_error(make_client_error(429, "RESOURCE_EXHAUSTED"))
            with caplog.at_level("WARNING"):
                result = await _generate_sql("question", None, None, None)

        assert result is None
        assert gemini_breaker_sql._failure_count == before + 1
        # Vérifier log warning explicite 429
        assert any(
            "Vertex 429 ResourceExhausted" in rec.getMessage()
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_generate_sql_circuit_open_returns_none_without_network_call(
        self, mock_vertex_client,
    ):
        """V131.D — Circuit OPEN → retour None SANS appel à generate_content."""
        # Préparer breaker en état OPEN
        gemini_breaker_sql._failure_count = 3
        gemini_breaker_sql._set_state(gemini_breaker_sql.OPEN)
        # _opened_at = now → state stays OPEN (pas de transition vers half_open)
        import time
        gemini_breaker_sql._opened_at = time.monotonic()

        with mock_vertex_client() as vc, \
             patch("services.chat_sql.load_prompt", return_value="prompt"):
            result = await _generate_sql("question", None, None, None)

        assert result is None
        # Asserter qu'aucun appel réseau n'a été fait
        vc.client.aio.models.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_sql_parses_clean_text(self, mock_vertex_client):
        """V131.D — réponse SQL propre passe à travers _clean_gemini_sql + _guard_non_sql."""
        with mock_vertex_client() as vc, \
             patch("services.chat_sql.load_prompt", return_value="prompt"):
            vc.set_response(text="SELECT * FROM tirages LIMIT 10")
            result = await _generate_sql("question", None, None, None)

        assert result == "SELECT * FROM tirages LIMIT 10"

    @pytest.mark.asyncio
    async def test_generate_sql_parses_markdown_wrapped_text(self, mock_vertex_client):
        """V131.D — réponse SQL wrappée en markdown ```sql → wrapper enlevé."""
        with mock_vertex_client() as vc, \
             patch("services.chat_sql.load_prompt", return_value="prompt"):
            vc.set_response(text="```sql\nSELECT * FROM tirages LIMIT 10\n```")
            result = await _generate_sql("question", None, None, None)

        assert result == "SELECT * FROM tirages LIMIT 10"

    @pytest.mark.asyncio
    async def test_generate_sql_timeout_records_failure(
        self, mock_vertex_client, caplog,
    ):
        """V131.D — TimeoutError → _record_failure + retour None + log warning."""
        before = gemini_breaker_sql._failure_count

        with mock_vertex_client() as vc, \
             patch("services.chat_sql.load_prompt", return_value="prompt"):
            vc.set_timeout()
            with caplog.at_level("WARNING"):
                result = await _generate_sql("question", None, None, None)

        assert result is None
        assert gemini_breaker_sql._failure_count == before + 1
        # Vérifier log warning explicite Timeout
        assert any(
            "Timeout Gemini Vertex" in rec.getMessage()
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_generate_sql_safety_blocked_returns_none(
        self, mock_vertex_client, caplog,
    ):
        """V131.D bonus — SAFETY/RECITATION block → retour None, PAS de _record_success."""
        before_success = gemini_breaker_sql._failure_count

        with mock_vertex_client() as vc, \
             patch("services.chat_sql.load_prompt", return_value="prompt"):
            vc.set_blocked_safety()
            with caplog.at_level("WARNING"):
                result = await _generate_sql("question", None, None, None)

        assert result is None
        # SAFETY ≠ failure infrastructure (pas d'incrément failure_count non plus)
        assert gemini_breaker_sql._failure_count == before_success
        # Vérifier log warning explicite SAFETY
        assert any(
            "SAFETY/RECITATION" in rec.getMessage()
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_generate_sql_server_error_503_records_failure(
        self, mock_vertex_client, caplog,
    ):
        """V131.D bonus — ServerError 503 → _record_failure + retour None."""
        before = gemini_breaker_sql._failure_count

        with mock_vertex_client() as vc, \
             patch("services.chat_sql.load_prompt", return_value="prompt"):
            error_503 = genai_errors.ServerError(
                503,
                {"error": {"code": 503, "message": "Service Unavailable", "status": "UNAVAILABLE"}},
            )
            vc.set_error(error_503)
            with caplog.at_level("WARNING"):
                result = await _generate_sql("question", None, None, None)

        assert result is None
        assert gemini_breaker_sql._failure_count == before + 1
        # Vérifier log warning explicite ServerError
        assert any(
            "Vertex ServerError" in rec.getMessage()
            for rec in caplog.records
        )


class TestGenerateSqlEmErrorBranches:
    """V131.D — Tests symétriques EM pour les 5 branches d'erreur (boost coverage chat_sql_em.py)."""

    @pytest.mark.asyncio
    async def test_generate_sql_em_429_records_failure_and_returns_none(
        self, mock_vertex_client, make_client_error, caplog,
    ):
        """V131.D — _generate_sql_em : 429 → _record_failure + None."""
        before = gemini_breaker_sql._failure_count

        with mock_vertex_client() as vc, \
             patch("services.chat_sql_em.load_prompt_em", return_value="prompt"):
            vc.set_error(make_client_error(429, "RESOURCE_EXHAUSTED"))
            with caplog.at_level("WARNING"):
                result = await _generate_sql_em("question", None, None, None, lang="fr")

        assert result is None
        assert gemini_breaker_sql._failure_count == before + 1
        assert any(
            "[EM TEXT-TO-SQL] Vertex 429 ResourceExhausted" in rec.getMessage()
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_generate_sql_em_timeout_records_failure(
        self, mock_vertex_client, caplog,
    ):
        """V131.D — _generate_sql_em : TimeoutError → _record_failure + None."""
        before = gemini_breaker_sql._failure_count

        with mock_vertex_client() as vc, \
             patch("services.chat_sql_em.load_prompt_em", return_value="prompt"):
            vc.set_timeout()
            with caplog.at_level("WARNING"):
                result = await _generate_sql_em("question", None, None, None, lang="en")

        assert result is None
        assert gemini_breaker_sql._failure_count == before + 1
        assert any(
            "[EM TEXT-TO-SQL] Timeout Gemini Vertex" in rec.getMessage()
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_generate_sql_em_safety_blocked_returns_none(
        self, mock_vertex_client, caplog,
    ):
        """V131.D — _generate_sql_em : SAFETY blocked → None, pas de _record_*."""
        before = gemini_breaker_sql._failure_count

        with mock_vertex_client() as vc, \
             patch("services.chat_sql_em.load_prompt_em", return_value="prompt"):
            vc.set_blocked_safety()
            with caplog.at_level("WARNING"):
                result = await _generate_sql_em("question", None, None, None, lang="es")

        assert result is None
        assert gemini_breaker_sql._failure_count == before  # SAFETY ≠ failure
        assert any(
            "[EM TEXT-TO-SQL] Vertex response blocked (SAFETY/RECITATION)" in rec.getMessage()
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_generate_sql_em_server_error_503_records_failure(
        self, mock_vertex_client, caplog,
    ):
        """V131.D — _generate_sql_em : ServerError 503 → _record_failure + None."""
        before = gemini_breaker_sql._failure_count

        with mock_vertex_client() as vc, \
             patch("services.chat_sql_em.load_prompt_em", return_value="prompt"):
            error_503 = genai_errors.ServerError(
                503,
                {"error": {"code": 503, "message": "Service Unavailable", "status": "UNAVAILABLE"}},
            )
            vc.set_error(error_503)
            with caplog.at_level("WARNING"):
                result = await _generate_sql_em("question", None, None, None, lang="pt")

        assert result is None
        assert gemini_breaker_sql._failure_count == before + 1
        assert any(
            "[EM TEXT-TO-SQL] Vertex ServerError" in rec.getMessage()
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_generate_sql_em_circuit_open_returns_none_without_network_call(
        self, mock_vertex_client,
    ):
        """V131.D — _generate_sql_em : Circuit OPEN → None SANS appel à generate_content."""
        # Préparer breaker en état OPEN
        gemini_breaker_sql._failure_count = 3
        gemini_breaker_sql._set_state(gemini_breaker_sql.OPEN)
        import time
        gemini_breaker_sql._opened_at = time.monotonic()

        with mock_vertex_client() as vc, \
             patch("services.chat_sql_em.load_prompt_em", return_value="prompt"):
            result = await _generate_sql_em("question", None, None, None, lang="de")

        assert result is None
        vc.client.aio.models.generate_content.assert_not_called()


class TestGenerateSqlDefensiveBranches:
    """V131.D — Tests défensifs (prompt None, APIError SDK B, Exception générique)."""

    @pytest.mark.asyncio
    async def test_generate_sql_returns_none_when_prompt_missing(self, mock_vertex_client):
        """V131.D — _generate_sql : prompt loader retourne None → return None sans appel Vertex."""
        with mock_vertex_client() as vc, \
             patch("services.chat_sql.load_prompt", return_value=None):
            result = await _generate_sql("question", None, None, None)

        assert result is None
        # Pas d'appel à generate_content si pas de prompt
        vc.client.aio.models.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_sql_em_returns_none_when_prompt_missing(self, mock_vertex_client):
        """V131.D — _generate_sql_em : prompt loader retourne None → return None sans appel Vertex."""
        with mock_vertex_client() as vc, \
             patch("services.chat_sql_em.load_prompt_em", return_value=None):
            result = await _generate_sql_em("question", None, None, None, lang="nl")

        assert result is None
        vc.client.aio.models.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_sql_api_error_records_failure(
        self, mock_vertex_client, caplog,
    ):
        """V131.D — _generate_sql : APIError SDK B générique (ni Client ni Server) → _record_failure + None.

        Note : on lève directement APIError (parent de ClientError/ServerError) avec
        un code non-429 pour capturer la branche `except genai_errors.APIError`.
        """
        before = gemini_breaker_sql._failure_count

        with mock_vertex_client() as vc, \
             patch("services.chat_sql.load_prompt", return_value="prompt"):
            api_error = genai_errors.APIError(
                400,
                {"error": {"code": 400, "message": "test", "status": "INVALID_ARGUMENT"}},
            )
            vc.set_error(api_error)
            with caplog.at_level("ERROR"):
                result = await _generate_sql("question", None, None, None)

        assert result is None
        assert gemini_breaker_sql._failure_count == before + 1

    @pytest.mark.asyncio
    async def test_generate_sql_unexpected_exception_returns_none(
        self, mock_vertex_client, caplog,
    ):
        """V131.D — _generate_sql : Exception générique inattendue → return None (catch-all).

        Sémantique V131.A : Exception générique = log mais PAS de _record_failure
        (failure SDK B explicites uniquement).
        """
        before = gemini_breaker_sql._failure_count

        with mock_vertex_client() as vc, \
             patch("services.chat_sql.load_prompt", return_value="prompt"):
            vc.set_error(RuntimeError("totalement inattendu"))
            with caplog.at_level("ERROR"):
                result = await _generate_sql("question", None, None, None)

        assert result is None
        # Catch-all Exception ne fait pas _record_failure (cf pattern V131.A)
        assert gemini_breaker_sql._failure_count == before

    @pytest.mark.asyncio
    async def test_generate_sql_em_api_error_records_failure(self, mock_vertex_client):
        """V131.D — _generate_sql_em : APIError SDK B → _record_failure + None (symétrie EM)."""
        before = gemini_breaker_sql._failure_count

        with mock_vertex_client() as vc, \
             patch("services.chat_sql_em.load_prompt_em", return_value="prompt"):
            api_error = genai_errors.APIError(
                400,
                {"error": {"code": 400, "message": "test", "status": "INVALID_ARGUMENT"}},
            )
            vc.set_error(api_error)
            result = await _generate_sql_em("question", None, None, None, lang="fr")

        assert result is None
        assert gemini_breaker_sql._failure_count == before + 1

    @pytest.mark.asyncio
    async def test_generate_sql_em_unexpected_exception_returns_none(self, mock_vertex_client):
        """V131.D — _generate_sql_em : Exception générique → return None (catch-all, symétrie EM)."""
        before = gemini_breaker_sql._failure_count

        with mock_vertex_client() as vc, \
             patch("services.chat_sql_em.load_prompt_em", return_value="prompt"):
            vc.set_error(RuntimeError("totalement inattendu"))
            result = await _generate_sql_em("question", None, None, None, lang="fr")

        assert result is None
        assert gemini_breaker_sql._failure_count == before
