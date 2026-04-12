"""
Backward-compatible re-exports — base chat detectors.
All detection functions are now split across:
- base_chat_detect_intent.py (intention detection, generation, temporal, pairs, grid eval)
- base_chat_detect_guardrails.py (insults, compliments, site rating)

V70 F10 — split for maintainability. All existing imports continue to work.
"""

from services.base_chat_detect_intent import (  # noqa: F401
    # Phase 0 — continuation + affirmation
    CONTINUATION_PATTERNS, _CONTINUATION_WORDS, _is_short_continuation,
    _AFFIRMATION_PATTERNS, _EMOJI_RE, _is_affirmation_simple,
    _GAME_KEYWORD_ALONE, _detect_game_keyword_alone,
    # Phase T — tirage detection
    _JOURS_SEMAINE, _TIRAGE_KW, _MOIS_TO_NUM, _MOIS_NOM_RE,
    _STAT_NEUTRALIZE_RE, _detect_tirage,
    # Temporal filter
    _MOIS_FR, _MOIS_RE, _MOIS_EN, _MOIS_ES, _MOIS_PT, _MOIS_DE, _MOIS_NL,
    _TEMPORAL_PATTERNS, _TEMPORAL_EXTRACT_MONTHS, _TEMPORAL_EXTRACT_YEARS,
    _TEMPORAL_EXTRACT_WEEKS, _has_temporal_filter, _extract_temporal_date,
    # Top-N extraction
    _TOP_N_PATTERNS, _extract_top_n,
    # Data signal + salutation
    _DATA_KEYWORDS, _HAS_DIGIT, _has_data_signal,
    _SALUTATION_PATTERN, _SALUTATION_MAX_WORDS, _SALUTATION_RESPONSES,
    _detect_salutation, _get_salutation_response,
    # Generation detection
    _GENERATION_PATTERN, _GENERATION_CONTEXT, _COOCCURRENCE_EXCLUSION,
    _detect_generation, _detect_generation_mode,
    _MODE_PATTERN_CONSERVATIVE, _MODE_PATTERN_RECENT,
    # Grid count + exclusions + forced numbers
    _GRID_COUNT_PATTERN, _extract_grid_count,
    _BIRTHDAY_PATTERN, _EXCLUDE_RANGE_PATTERN, _EXCLUDE_MULTIPLES_PATTERN,
    _EXCLUDE_NUMS_PATTERN, _EXCLUDE_NUMS_RANGE_PATTERN,
    _extract_exclusions, _extract_nums_from_text, _extract_forced_numbers,
    _CHANCE_PATTERN, _STAR_PATTERN, _WITH_PATTERN, _QUANTIFIER_PATTERN,
    # Pairs / triplets / co-occurrence
    _PAIRS_PATTERN, _EVEN_ODD_RE, _detect_paires,
    _TRIPLETS_PATTERN, _detect_triplets,
    _COOCCURRENCE_HIGH_N_PATTERN, _RANKING_EXCLUSION_PATTERN,
    _COOCCURRENCE_EXPLICIT_PATTERN, _COOCCURRENCE_HIGH_N_RESPONSES,
    _detect_cooccurrence_high_n, _get_cooccurrence_high_n_response,
    # Grid evaluation (V70)
    _GRID_EVAL_PATTERN, _GRID_EVAL_MIN_NUMS, _detect_grid_evaluation,
    # Phase 3 — base requête complexe (F06 V83)
    _detect_requete_complexe_base,
    # Phase REFUS (V98c)
    _REFUSAL_RE, _REFUSAL_RESPONSES, _is_refusal, _get_refusal_response,
)

from services.base_chat_detect_guardrails import (  # noqa: F401
    # Insult detection
    _INSULTE_MOTS, _INSULTE_PHRASES, _MENACE_PATTERNS,
    _insult_targets_bot, _detect_insulte, _count_insult_streak,
    # Compliment detection
    _COMPLIMENT_PHRASES, _COMPLIMENT_LOVE_PHRASES, _COMPLIMENT_SOLO_WORDS,
    _compliment_targets_bot, _detect_compliment, _count_compliment_streak,
    # Site rating
    _SITE_RATING_RE, _SITE_RATING_RESPONSES,
    _detect_site_rating, get_site_rating_response,
)
