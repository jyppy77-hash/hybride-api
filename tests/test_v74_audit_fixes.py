"""Tests for V74 audit fixes — F01 (lang injection), F02 (ensure_limit), F03 (config base)."""

import pytest
import asyncio
from contextlib import ExitStack
from unittest.mock import patch, AsyncMock, MagicMock


def _get_client():
    return MagicMock()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# Shared patch set for pipeline tests — neutralises all detectors
_PIPELINE_PATCHES = {
    "services.chat_pipeline._detect_insulte": None,
    "services.chat_pipeline._detect_compliment": None,
    "services.chat_pipeline._detect_salutation": False,
    "services.chat_pipeline._detect_generation": False,
    "services.chat_pipeline._detect_grid_evaluation": None,
    "services.chat_pipeline._detect_argent": False,
    "services.chat_pipeline._is_short_continuation": False,
    "services.chat_pipeline._detect_prochain_tirage": False,
    "services.chat_pipeline._detect_tirage": None,
    "services.chat_pipeline._has_temporal_filter": False,
    "services.chat_pipeline._detect_grille": (None, None),
    "services.chat_pipeline._detect_requete_complexe": None,
    "services.chat_pipeline._detect_out_of_range": (None, None),
    "services.chat_pipeline._detect_numero": (None, None),
    "services.chat_pipeline._detect_paires": False,
    "services.chat_pipeline._detect_triplets": False,
    "services.chat_pipeline._detect_cooccurrence_high_n": None,
    "services.chat_pipeline._has_data_signal": False,
}


def _apply_pipeline_patches(stack, extra=None):
    """Apply all detector patches + extras via ExitStack."""
    stack.enter_context(patch("services.chat_pipeline.load_prompt", return_value="Prompt"))
    stack.enter_context(patch.dict("os.environ", {"GEM_API_KEY": "fake"}))
    stack.enter_context(patch("services.chat_pipeline._generate_sql", new_callable=AsyncMock, return_value=None))
    stack.enter_context(patch("services.chat_pipeline._get_draw_count", new_callable=AsyncMock, return_value=500))
    for target, rv in _PIPELINE_PATCHES.items():
        stack.enter_context(patch(target, return_value=rv))
    if extra:
        for target, rv in extra.items():
            stack.enter_context(patch(target, return_value=rv))


# ═══════════════════════════════════════════════════════════
# F01 — Prompt Loto: lang injection when lang != "fr"
# ═══════════════════════════════════════════════════════════

class TestF01LangInjection:

    def test_loto_lang_fr_no_injection(self):
        """lang='fr' => no [LANGUE] block injected."""
        with ExitStack() as stack:
            _apply_pipeline_patches(stack)
            from services.chat_pipeline import _prepare_chat_context
            early, ctx = _run(_prepare_chat_context("bonjour", [], "/", _get_client(), lang="fr"))
            assert ctx is not None
            assert "[LANGUE" not in ctx["system_prompt"]

    def test_loto_lang_en_injection(self):
        """lang='en' => [LANGUE] block with 'anglais'."""
        with ExitStack() as stack:
            _apply_pipeline_patches(stack)
            from services.chat_pipeline import _prepare_chat_context
            early, ctx = _run(_prepare_chat_context("hello", [], "/", _get_client(), lang="en"))
            assert ctx is not None
            prompt = ctx["system_prompt"]
            assert "[LANGUE" in prompt
            assert "anglais" in prompt
            assert "JAMAIS dans une autre langue" in prompt

    def test_loto_lang_es_injection(self):
        """lang='es' => [LANGUE] block with 'espagnol'."""
        with ExitStack() as stack:
            _apply_pipeline_patches(stack)
            from services.chat_pipeline import _prepare_chat_context
            _, ctx = _run(_prepare_chat_context("hola", [], "/", _get_client(), lang="es"))
            assert "espagnol" in ctx["system_prompt"]

    def test_loto_lang_pt_injection(self):
        """lang='pt' => [LANGUE] block with 'portugais'."""
        with ExitStack() as stack:
            _apply_pipeline_patches(stack)
            from services.chat_pipeline import _prepare_chat_context
            _, ctx = _run(_prepare_chat_context("ola", [], "/", _get_client(), lang="pt"))
            assert "portugais" in ctx["system_prompt"]

    def test_loto_lang_de_injection(self):
        """lang='de' => [LANGUE] block with 'allemand'."""
        with ExitStack() as stack:
            _apply_pipeline_patches(stack)
            from services.chat_pipeline import _prepare_chat_context
            _, ctx = _run(_prepare_chat_context("hallo", [], "/", _get_client(), lang="de"))
            assert "allemand" in ctx["system_prompt"]

    def test_loto_lang_nl_injection(self):
        """lang='nl' => [LANGUE] block with 'néerlandais'."""
        with ExitStack() as stack:
            _apply_pipeline_patches(stack)
            from services.chat_pipeline import _prepare_chat_context
            _, ctx = _run(_prepare_chat_context("hallo", [], "/", _get_client(), lang="nl"))
            assert "néerlandais" in ctx["system_prompt"]

    def test_all_5_langs_in_lang_names(self):
        """All 5 non-FR langs have a _LANG_NAMES entry."""
        from services.chat_pipeline_shared import _LANG_NAMES
        assert set(_LANG_NAMES.keys()) == {"en", "es", "pt", "de", "nl"}


# ═══════════════════════════════════════════════════════════
# F02 — _ensure_limit() called inside _execute_safe_sql()
# ═══════════════════════════════════════════════════════════

class TestF02EnsureLimit:

    def test_sql_without_limit_gets_limit_added(self):
        """SQL without LIMIT => _execute_safe_sql adds LIMIT 50 before execution."""
        sql_no_limit = "SELECT boule_1 FROM tirages"
        executed_sql = []

        mock_cursor = AsyncMock()
        mock_cursor.execute = AsyncMock(side_effect=lambda sql: executed_sql.append(sql))
        mock_cursor.fetchall = AsyncMock(return_value=[{"boule_1": 7}])

        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch("services.base_chat_sql.db_cloudsql") as mock_db:
            mock_db.get_connection_readonly.return_value = mock_conn
            from services.base_chat_sql import _execute_safe_sql
            result = _run(_execute_safe_sql(sql_no_limit))

        assert len(executed_sql) == 1
        assert "LIMIT 50" in executed_sql[0]

    def test_sql_with_existing_limit_not_doubled(self):
        """SQL with LIMIT already present => no second LIMIT added."""
        sql_with_limit = "SELECT boule_1 FROM tirages LIMIT 20"
        executed_sql = []

        mock_cursor = AsyncMock()
        mock_cursor.execute = AsyncMock(side_effect=lambda sql: executed_sql.append(sql))
        mock_cursor.fetchall = AsyncMock(return_value=[{"boule_1": 7}])

        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch("services.base_chat_sql.db_cloudsql") as mock_db:
            mock_db.get_connection_readonly.return_value = mock_conn
            from services.base_chat_sql import _execute_safe_sql
            result = _run(_execute_safe_sql(sql_with_limit))

        assert len(executed_sql) == 1
        assert executed_sql[0].count("LIMIT") == 1

    def test_ensure_limit_idempotent(self):
        """_ensure_limit is idempotent — calling twice doesn't double LIMIT."""
        from services.base_chat_sql import _ensure_limit
        sql = "SELECT boule_1 FROM tirages"
        once = _ensure_limit(sql)
        twice = _ensure_limit(once)
        assert once == twice
        assert once.endswith("LIMIT 50")


# ═══════════════════════════════════════════════════════════
# F03 — _build_config_base() DRY pattern
# ═══════════════════════════════════════════════════════════

class TestF03ConfigBase:

    def test_build_config_base_returns_overrides(self):
        from services.chat_pipeline_shared import _build_config_base
        cfg = _build_config_base({"game": "test", "x": 42})
        assert cfg["game"] == "test"
        assert cfg["x"] == 42

    def test_loto_config_has_all_required_keys(self):
        from services.chat_pipeline import _build_loto_config
        cfg = _build_loto_config()
        required = [
            "game", "log_prefix", "debug_prefix",
            "load_system_prompt", "draw_count_game", "get_fallback", "detect_mode",
            "detect_insulte", "count_insult_streak", "detect_compliment", "count_compliment_streak",
            "detect_site_rating", "get_site_rating_response",
            "is_short_continuation", "detect_tirage", "has_temporal_filter", "extract_temporal_date",
            "detect_generation", "detect_generation_mode", "extract_forced_numbers",
            "extract_grid_count", "extract_exclusions",
            "detect_cooccurrence_high_n", "get_cooccurrence_high_n_response",
            "is_affirmation_simple", "detect_game_keyword_alone",
            "detect_salutation", "get_salutation_response", "has_data_signal",
            "detect_grid_evaluation", "enrich_with_context",
            "get_insult_short", "get_menace_response", "get_insult_response",
            "get_compliment_response", "salutation_game",
            "gen_engine_module", "forced_secondary_key", "gen_secondary_param",
            "store_exclusions", "format_generation_context",
            "detect_argent", "get_argent_response",
            "affirmation_invitation", "game_keyword_invitation",
            "eval_game", "secondary_field", "format_grille_context",
            "analyze_grille_for_chat", "analyze_passes_lang",
            "detect_prochain_tirage", "get_prochain_tirage",
            "get_tirage_data", "format_tirage_context", "tirage_not_found",
            "detect_grille",
            "detect_requete_complexe", "format_complex_context",
            "get_classement", "get_comparaison", "get_categorie", "get_comparaison_with_period",
            "detect_triplets", "format_triplets_context", "get_triplet_correlations",
            "detect_paires", "format_pairs_context", "get_pair_correlations",
            "detect_oor", "count_oor_streak", "get_oor_response",
            "detect_numero", "get_numero_stats", "format_stats_context",
            "generate_sql", "validate_sql", "ensure_limit",
            "execute_safe_sql", "format_sql_result", "max_sql_per_session", "sql_log_prefix",
            "build_session_context",
        ]
        for key in required:
            assert key in cfg, f"Missing key in Loto config: {key}"
        assert cfg["game"] == "loto"

    def test_em_config_has_all_required_keys_plus_em_specific(self):
        from services.chat_pipeline_em import _build_em_config
        cfg = _build_em_config()
        assert cfg["game"] == "em"
        em_specific = [
            "detect_country", "get_country_context", "wants_both_fn",
            "get_star_pair_correlations", "format_star_pairs_context", "sql_gen_kwargs",
        ]
        for key in em_specific:
            assert key in cfg, f"Missing EM-specific key: {key}"
        # Shared detectors also present
        assert "detect_insulte" in cfg
        assert "detect_generation" in cfg

    def test_config_base_does_not_mutate_input(self):
        from services.chat_pipeline_shared import _build_config_base
        overrides = {"game": "test"}
        original_len = len(overrides)
        _build_config_base(overrides)
        assert len(overrides) == original_len
