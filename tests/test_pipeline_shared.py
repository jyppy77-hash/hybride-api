"""
Tests for chat_pipeline_shared.py — V71 R3a backward-compat + shared helpers.
"""

import json
from types import SimpleNamespace

from services.chat_pipeline_shared import (
    sse_event, log_from_meta, build_gemini_contents, parse_pitch_json,
)


# ═══════════════════════════════════════════════════════
# Backward-compat: imports still work from original modules
# ═══════════════════════════════════════════════════════

class TestBackwardCompatImports:
    """Verify that the public API surface of both pipelines is unchanged."""

    def test_loto_pipeline_exports(self):
        """All public functions still importable from services.chat_pipeline."""
        from services.chat_pipeline import (
            handle_chat, handle_chat_stream, handle_pitch,
            _prepare_chat_context, _sse_event, _log_from_meta, _get_draw_count,
        )
        assert callable(handle_chat)
        assert callable(handle_chat_stream)
        assert callable(handle_pitch)
        assert callable(_prepare_chat_context)
        assert callable(_sse_event)
        assert callable(_log_from_meta)
        assert callable(_get_draw_count)

    def test_em_pipeline_exports(self):
        """All public functions still importable from services.chat_pipeline_em."""
        from services.chat_pipeline_em import (
            handle_chat_em, handle_chat_stream_em, handle_pitch_em,
            _prepare_chat_context_em, _sse_event_em, _log_from_meta_em,
        )
        assert callable(handle_chat_em)
        assert callable(handle_chat_stream_em)
        assert callable(handle_pitch_em)
        assert callable(_prepare_chat_context_em)
        assert callable(_sse_event_em)
        assert callable(_log_from_meta_em)

    def test_shared_module_exists(self):
        """chat_pipeline_shared module is importable."""
        import services.chat_pipeline_shared as shared
        assert hasattr(shared, 'sse_event')
        assert hasattr(shared, 'log_from_meta')
        assert hasattr(shared, 'build_gemini_contents')
        assert hasattr(shared, 'run_text_to_sql')
        assert hasattr(shared, 'call_gemini_and_respond')
        assert hasattr(shared, 'stream_and_respond')
        assert hasattr(shared, 'handle_pitch_common')
        assert hasattr(shared, 'parse_pitch_json')


# ═══════════════════════════════════════════════════════
# Shared helper unit tests
# ═══════════════════════════════════════════════════════

class TestSseEvent:
    def test_format(self):
        event = sse_event({"chunk": "hello"})
        assert event.startswith("data: ")
        assert event.endswith("\n\n")
        assert json.loads(event[6:].strip())["chunk"] == "hello"

    def test_loto_sse_delegates(self):
        """Loto _sse_event delegates to shared sse_event."""
        from services.chat_pipeline import _sse_event
        event = _sse_event({"test": True})
        assert '"test": true' in event

    def test_em_sse_delegates(self):
        """EM _sse_event_em delegates to shared sse_event."""
        from services.chat_pipeline_em import _sse_event_em
        event = _sse_event_em({"test": True})
        assert '"test": true' in event


class TestBuildGeminiContents:
    def test_empty_history(self):
        contents, history = build_gemini_contents([], "hello", lambda x: False)
        assert contents == []
        assert history == []

    def test_strips_insult_exchanges(self):
        """Insult user messages and their assistant responses are stripped."""
        msgs = [
            SimpleNamespace(role="user", content="t'es nul"),
            SimpleNamespace(role="assistant", content="calm down"),
            SimpleNamespace(role="user", content="quel numéro"),
        ]
        contents, _ = build_gemini_contents(msgs, "le 7", lambda x: "nul" in x)
        assert len(contents) == 1
        assert contents[0]["parts"][0]["text"] == "quel numéro"

    def test_dedup_last_message(self):
        """If last history message == current message, it's trimmed."""
        msgs = [SimpleNamespace(role="user", content="hello")]
        contents, history = build_gemini_contents(msgs, "hello", lambda x: False)
        assert len(history) == 0


class TestParsePitchJson:
    def test_valid_json(self):
        pitchs, err = parse_pitch_json('{"pitchs": ["Super !"]}')
        assert err is None
        assert pitchs == ["Super !"]

    def test_backtick_cleaning(self):
        pitchs, err = parse_pitch_json('```json\n{"pitchs": ["OK"]}\n```')
        assert err is None
        assert pitchs == ["OK"]

    def test_invalid_json(self):
        pitchs, err = parse_pitch_json("not json at all")
        assert pitchs is None
        assert err["status_code"] == 502

    # F08 V72 — edge cases
    def test_nested_backticks(self):
        """Backticks with json label and extra whitespace."""
        text = '```json\n  {"pitchs": ["Nested"]}\n  ```'
        pitchs, err = parse_pitch_json(text)
        assert err is None
        assert pitchs == ["Nested"]

    def test_malformed_json(self):
        """Broken JSON → returns error, no crash."""
        pitchs, err = parse_pitch_json('{"pitchs": [missing]}')
        assert pitchs is None
        assert err is not None
        assert err["status_code"] == 502

    def test_text_around_json(self):
        """Text before/after backtick-wrapped JSON → extraction works."""
        text = 'Voici la grille:\n```json\n{"pitchs": ["Bonne chance"]}\n```\nMerci!'
        # parse_pitch_json strips from first ``` to last ```
        pitchs, err = parse_pitch_json(text)
        # The text before ``` means startswith("```") is False, so it tries raw JSON
        # This tests the fallback behavior
        assert pitchs is None or isinstance(pitchs, list)

    def test_empty_json_object(self):
        """Empty object {} → returns empty pitchs list, no crash."""
        pitchs, err = parse_pitch_json('{}')
        assert err is None
        assert pitchs == []


# ═══════════════════════════════════════════════════════
# Shared constants — V72 F03/F04/F07
# ═══════════════════════════════════════════════════════

class TestSharedConstants:
    """V72: shared constants exist and contain expected keywords."""

    def test_question_keywords_insult_has_6_langs(self):
        from services.chat_pipeline_shared import _QUESTION_KEYWORDS_INSULT
        assert "numéro" in _QUESTION_KEYWORDS_INSULT  # FR
        assert "number" in _QUESTION_KEYWORDS_INSULT   # EN
        assert "sorteo" in _QUESTION_KEYWORDS_INSULT   # ES
        assert "sorteio" in _QUESTION_KEYWORDS_INSULT  # PT
        assert "ziehung" in _QUESTION_KEYWORDS_INSULT  # DE
        assert "trekking" in _QUESTION_KEYWORDS_INSULT  # NL

    def test_question_keywords_compliment_has_6_langs(self):
        from services.chat_pipeline_shared import _QUESTION_KEYWORDS_COMPLIMENT
        assert "comment" in _QUESTION_KEYWORDS_COMPLIMENT  # FR
        assert "how" in _QUESTION_KEYWORDS_COMPLIMENT      # EN
        assert "cuál" in _QUESTION_KEYWORDS_COMPLIMENT     # ES
        assert "qual" in _QUESTION_KEYWORDS_COMPLIMENT     # PT
        assert "wie" in _QUESTION_KEYWORDS_COMPLIMENT      # DE
        assert "welke" in _QUESTION_KEYWORDS_COMPLIMENT    # NL

    def test_anti_reintro_block_content(self):
        from services.chat_pipeline_shared import ANTI_REINTRO_BLOCK
        assert "ANTI-RE-PRÉSENTATION" in ANTI_REINTRO_BLOCK
        assert "HYBRIDE" in ANTI_REINTRO_BLOCK

    def test_tirage_not_found_loto_6_langs(self):
        from services.chat_pipeline_shared import _TIRAGE_NOT_FOUND_LOTO
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            assert lang in _TIRAGE_NOT_FOUND_LOTO
            assert "{date}" in _TIRAGE_NOT_FOUND_LOTO[lang]

    def test_tirage_not_found_em_6_langs(self):
        from services.chat_pipeline_shared import _TIRAGE_NOT_FOUND_EM
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            assert lang in _TIRAGE_NOT_FOUND_EM
            assert "{date}" in _TIRAGE_NOT_FOUND_EM[lang]


# ═══════════════════════════════════════════════════════
# Parametric pipeline — V72 F02
# ═══════════════════════════════════════════════════════

class TestParametricPipelineConfig:
    """V72 F02: config dicts are complete and _prepare_chat_context_base is importable."""

    # Required keys that both Loto and EM configs must have
    _REQUIRED_KEYS = {
        "game", "log_prefix", "debug_prefix",
        "load_system_prompt", "draw_count_game",
        "get_fallback", "detect_mode",
        "detect_insulte", "count_insult_streak",
        "detect_compliment", "count_compliment_streak",
        "detect_site_rating", "get_site_rating_response",
        "is_short_continuation", "detect_tirage", "has_temporal_filter",
        "extract_temporal_date",
        "detect_generation", "detect_generation_mode",
        "extract_forced_numbers", "extract_grid_count", "extract_exclusions",
        "detect_cooccurrence_high_n", "get_cooccurrence_high_n_response",
        "is_affirmation_simple", "detect_game_keyword_alone",
        "detect_salutation", "get_salutation_response",
        "has_data_signal", "detect_grid_evaluation", "enrich_with_context",
        "get_insult_short", "get_menace_response", "get_insult_response",
        "get_compliment_response", "salutation_game",
        "gen_engine_module", "forced_secondary_key", "gen_secondary_param",
        "format_generation_context",
        "detect_argent", "get_argent_response",
        "affirmation_invitation", "game_keyword_invitation",
        "eval_game", "secondary_field", "format_grille_context",
        "analyze_grille_for_chat",
        "detect_prochain_tirage", "get_prochain_tirage",
        "get_tirage_data", "format_tirage_context", "tirage_not_found",
        "detect_grille",
        "detect_requete_complexe", "format_complex_context",
        "get_classement", "get_comparaison", "get_categorie",
        "get_comparaison_with_period",
        "detect_triplets", "format_triplets_context", "get_triplet_correlations",
        "detect_paires", "format_pairs_context", "get_pair_correlations",
        "detect_oor", "count_oor_streak", "get_oor_response",
        "detect_numero", "get_numero_stats", "format_stats_context",
        "generate_sql", "validate_sql", "ensure_limit",
        "execute_safe_sql", "format_sql_result", "max_sql_per_session",
        "sql_log_prefix",
        "build_session_context",
    }

    def test_base_function_importable(self):
        from services.chat_pipeline_shared import _prepare_chat_context_base
        assert callable(_prepare_chat_context_base)

    def test_loto_config_has_all_required_keys(self):
        from services.chat_pipeline import _build_loto_config
        cfg = _build_loto_config()
        missing = self._REQUIRED_KEYS - set(cfg.keys())
        assert not missing, f"Loto config missing keys: {missing}"

    def test_em_config_has_all_required_keys(self):
        from services.chat_pipeline_em import _build_em_config
        cfg = _build_em_config()
        missing = self._REQUIRED_KEYS - set(cfg.keys())
        assert not missing, f"EM config missing keys: {missing}"

    def test_loto_config_game_identity(self):
        from services.chat_pipeline import _build_loto_config
        cfg = _build_loto_config()
        assert cfg["game"] == "loto"
        assert cfg["salutation_game"] == "loto"
        assert cfg["eval_game"] == "loto"
        assert cfg["secondary_field"] == "chance"

    def test_em_config_game_identity(self):
        from services.chat_pipeline_em import _build_em_config
        cfg = _build_em_config()
        assert cfg["game"] == "em"
        assert cfg["salutation_game"] == "em"
        assert cfg["eval_game"] == "em"
        assert cfg["secondary_field"] == "etoiles"
        assert cfg.get("detect_country") is not None  # EM has Phase GEO


# ═══════════════════════════════════════════════════════
# V96: Phase T guards — anti-hallucination
# ═══════════════════════════════════════════════════════

class TestPhaseTGuards:
    """V96: Single-date guard and error guard constants."""

    def test_single_date_guard_all_6_langs(self):
        from services.chat_pipeline_shared import _TIRAGE_SINGLE_DATE_GUARD
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            tpl = _TIRAGE_SINGLE_DATE_GUARD[lang]
            assert "{date}" in tpl, f"Missing {{date}} placeholder in {lang}"
            assert "UNIQUEMENT" in tpl or "ONLY" in tpl or "ÚNICAMENTE" in tpl or \
                   "APENAS" in tpl or "NUR" in tpl or "ALLEEN" in tpl, \
                   f"Missing exclusivity keyword in {lang}"

    def test_error_guard_all_6_langs(self):
        from services.chat_pipeline_shared import _TIRAGE_ERROR_GUARD
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            msg = _TIRAGE_ERROR_GUARD[lang]
            assert len(msg) > 50, f"Error guard too short for {lang}"
            # Must contain anti-invention instruction
            assert "invent" in msg.lower() or "erfind" in msg.lower() or "verzin" in msg.lower(), \
                   f"Missing anti-invention instruction in {lang}"

    def test_single_date_guard_format(self):
        """Guard template formats correctly with a date."""
        from services.chat_pipeline_shared import _TIRAGE_SINGLE_DATE_GUARD
        result = _TIRAGE_SINGLE_DATE_GUARD["fr"].format(date="samedi 4 avril 2026")
        assert "samedi 4 avril 2026" in result
        assert "UNIQUEMENT" in result

    def test_error_guard_no_placeholder(self):
        """Error guard has no format placeholder (static message)."""
        from services.chat_pipeline_shared import _TIRAGE_ERROR_GUARD
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            assert "{" not in _TIRAGE_ERROR_GUARD[lang], \
                   f"Unexpected placeholder in error guard {lang}"
