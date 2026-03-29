"""
Backward-compatible re-exports — EuroMillions chat detectors.
All EM detection functions are now split across:
- chat_detectors_em_intent.py (EM-specific intent detection)
- chat_detectors_em_guardrails.py (EM-specific guardrails & response pools)

V70 F11 — split for maintainability. All existing imports continue to work.
"""

from services.chat_detectors_em_intent import (  # noqa: F401
    # Star/boule detection
    _STAR_RE, _STAR_QUERY_RE, _is_star_query,
    _BOULE_QUERY_RE, _wants_both_boules_and_stars,
    # Pairs/triplets wrappers
    _detect_paires_em, _detect_triplets_em,
    # Mode + prochain tirage
    META_KEYWORDS, _detect_mode_em, _detect_prochain_tirage_em,
    # Numero + grille + requete complexe
    _detect_numero_em, _detect_grille_em, _detect_requete_complexe_em,
    # Out-of-range
    _detect_out_of_range_em, _count_oor_streak_em,
    # Re-exports from base (used by pipeline_em)
    _detect_insulte, _count_insult_streak,
    _detect_compliment, _count_compliment_streak,
    _extract_top_n,
    _detect_paires, _detect_triplets,
    _detect_generation, _detect_generation_mode,
    _is_affirmation_simple, _detect_game_keyword_alone,
    _detect_grid_evaluation,
)

from services.chat_detectors_em_guardrails import (  # noqa: F401
    # Insult response pools + functions
    _INSULT_L1_EM, _INSULT_L2_EM, _INSULT_L3_EM, _INSULT_L4_EM,
    _INSULT_SHORT_EM, _MENACE_RESPONSES_EM,
    _get_insult_response_em, _get_insult_short_em, _get_menace_response_em,
    # Compliment response pools + functions
    _COMPLIMENT_L1_EM, _COMPLIMENT_L2_EM, _COMPLIMENT_L3_EM,
    _COMPLIMENT_LOVE_EM, _COMPLIMENT_MERCI_EM,
    _get_compliment_response_em,
    # Argent detection + response (FR + per-lang pools)
    _ARGENT_PHRASES_EM, _ARGENT_MOTS_EM, _ARGENT_STRONG_EM, _ARGENT_BETTING_EM,
    _EURO_GAME_RE_EM, _EURO_GAME_SKIP_EM,
    _PEDAGOGIE_LIMITES_EM, _SCORE_QUESTION_EM,
    _detect_pedagogie_limites_em, _detect_score_question_em,
    _detect_argent_em, _ARGENT_POOLS_EM, _get_argent_response_em,
    _ARGENT_L1_EM, _ARGENT_L2_EM, _ARGENT_L3_EM,
    _ARGENT_L1_EM_ES, _ARGENT_L2_EM_ES, _ARGENT_L3_EM_ES,
    _ARGENT_L1_EM_PT, _ARGENT_L2_EM_PT, _ARGENT_L3_EM_PT,
    _ARGENT_L1_EM_DE, _ARGENT_L2_EM_DE, _ARGENT_L3_EM_DE,
    _ARGENT_L1_EM_NL, _ARGENT_L2_EM_NL, _ARGENT_L3_EM_NL,
    # OOR response pools
    _OOR_L1_EM, _OOR_L2_EM, _OOR_L3_EM,
    _OOR_CLOSE_EM, _OOR_ZERO_NEG_EM, _OOR_ETOILE_EM,
    _get_oor_response_em,
    # Country detection
    _EM_COUNTRY_PATTERN, _EM_COUNTRY_CONTEXT,
    _detect_country_em, _get_country_context_em,
)
