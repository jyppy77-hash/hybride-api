"""
Service metier — pipeline chatbot EuroMillions.
Orchestre les 12 phases du chatbot EM (detection → enrichissement → Gemini).
Meme pattern que chat_pipeline.py (Loto) avec detecteurs/formatage EM.
"""

import os
import re
import asyncio
import logging
import time
import json
import httpx

from services.prompt_loader import load_prompt_em
from services.gemini import GEMINI_MODEL_URL, stream_gemini_chat
from services.circuit_breaker import gemini_breaker, CircuitOpenError
from services.em_stats_service import (
    get_numero_stats, analyze_grille_for_chat,
    get_classement_numeros, get_comparaison_numeros, get_comparaison_with_period,
    get_numeros_par_categorie,
    prepare_grilles_pitch_context, get_pair_correlations, get_triplet_correlations,
    get_star_pair_correlations,
)

from services.chat_detectors import (
    _detect_insulte, _count_insult_streak,
    _detect_compliment, _count_compliment_streak,
    _is_short_continuation, _detect_tirage, _has_temporal_filter, _extract_temporal_date,
    _detect_generation, _detect_generation_mode, _extract_forced_numbers, _extract_grid_count,
    _extract_exclusions,
    _detect_cooccurrence_high_n, _get_cooccurrence_high_n_response,
    _detect_site_rating, get_site_rating_response,
    _is_affirmation_simple, _detect_game_keyword_alone,  # V51
    _detect_salutation, _get_salutation_response,  # V65
    _has_data_signal,  # V65
    _detect_grid_evaluation,  # V70
)
from services.chat_detectors_em import (
    _detect_mode_em, _detect_prochain_tirage_em,
    _detect_numero_em, _detect_grille_em,
    _detect_requete_complexe_em, _detect_paires_em, _detect_triplets_em,
    _detect_out_of_range_em, _count_oor_streak_em,
    _detect_argent_em, _get_argent_response_em,
    _detect_country_em, _get_country_context_em,
    _wants_both_boules_and_stars,
)
from services.chat_responses_em_multilang import (
    get_insult_response, get_insult_short, get_menace_response,
    get_compliment_response, get_oor_response, get_fallback,
    _AFFIRMATION_INVITATION_EM, _GAME_KEYWORD_INVITATION_EM,  # V70 F05
)
from services.chat_sql_em import (
    _get_prochain_tirage_em, _get_tirage_data_em, _generate_sql_em,
    _validate_sql, _ensure_limit, _execute_safe_sql, _format_sql_result,
    _MAX_SQL_PER_SESSION,
)
from services.chat_utils import (
    _enrich_with_context, _clean_response, _strip_non_latin,
    _get_sponsor_if_due, _strip_sponsor_from_text, _format_date_fr,
    StreamBuffer,
)
from services.chat_utils_em import (
    _format_tirage_context_em, _format_stats_context_em,
    _format_grille_context_em, _format_complex_context_em,
    _format_pairs_context_em, _format_triplets_context_em,
    _format_star_pairs_context_em,
    _build_session_context_em,
    _format_generation_context_em,
)
from services.chat_logger import log_chat_exchange
from services.chat_pipeline import _get_draw_count  # F02: shared draw count helper
from services.chat_pipeline_shared import (
    sse_event as _sse_event_shared,
    log_from_meta as _log_from_meta_shared,
    build_gemini_contents,
    run_text_to_sql,
    call_gemini_and_respond,
    stream_and_respond,
    handle_pitch_common,
)

logger = logging.getLogger(__name__)


# =========================
# HYBRIDE EuroMillions Chatbot — Pipeline 12 phases
# =========================

async def _prepare_chat_context_em(message: str, history: list, page: str, http_client, lang: str = "fr"):
    """
    Phases I-SQL EM : prepare le contexte pour l'appel Gemini.
    Retourne (early_return_or_None, ctx_dict_or_None).
    """

    _t0 = time.monotonic()
    _fallback = get_fallback(lang)
    mode = _detect_mode_em(message, page)

    # ── Chat Monitor: phase tracking (V44) ──
    _phase = "Gemini"
    _sql_query = None
    _sql_status = "N/A"
    _grid_count = 0
    _has_exclusions = False

    system_prompt = load_prompt_em("prompt_hybride_em", lang=lang)
    if not system_prompt:
        logger.error(f"[EM CHAT] Prompt systeme introuvable (prompt_hybride_em/{lang})")
        return {"response": _fallback, "source": "fallback", "mode": mode}, None

    # F02: inject dynamic draw count
    draw_count = await _get_draw_count("euromillions")
    if draw_count and "{DRAW_COUNT}" in system_prompt:
        system_prompt = system_prompt.replace("{DRAW_COUNT}", str(draw_count))

    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        logger.warning("[EM CHAT] GEM_API_KEY non configuree — fallback")
        return {"response": _fallback, "source": "fallback", "mode": mode}, None

    contents, history = build_gemini_contents(history, message, _detect_insulte)

    # ── Anti-re-introduction : TOUJOURS injecté (le welcome JS a déjà fait la présentation) ──
    system_prompt += (
        "\n\n[RAPPEL CRITIQUE — ANTI-RE-PRÉSENTATION]\n"
        "Le message de bienvenue affiché côté interface a DÉJÀ présenté HYBRIDE à l'utilisateur. "
        "Tu t'es DÉJÀ présenté. NE TE RE-PRÉSENTE PAS. "
        "Ne dis PAS 'Je suis HYBRIDE', 'I'm HYBRIDE', 'Soy HYBRIDE', 'Eu sou HYBRIDE', "
        "'Ich bin HYBRIDE', 'Ik ben HYBRIDE', etc. "
        "Ne dis PAS 'Salut !', 'Hello !', 'Hi !', 'Hola !', 'Olá !', 'Hallo !' en début de réponse "
        "s'il ne t'a pas salué. "
        "Va DIRECTEMENT à la réponse à sa question."
    )

    # ── Contexte pédagogique : injecté quand la question porte sur les fréquences/tendances ──
    from services.stats_analysis import should_inject_pedagogical_context, PEDAGOGICAL_CONTEXT
    if should_inject_pedagogical_context(message):
        system_prompt += PEDAGOGICAL_CONTEXT

    # ── Phase I : Détection d'insultes / agressivité ──
    _insult_prefix = ""
    _insult_type = _detect_insulte(message)
    if _insult_type:
        _insult_streak = _count_insult_streak(history)
        _has_question = (
            '?' in message
            or bool(re.search(r'\b\d{1,2}\b', message))
            or any(kw in message.lower() for kw in (
                "numéro", "numero", "tirage", "grille", "fréquence", "frequence",
                "classement", "statistique", "stat", "analyse", "prochain",
                "étoile", "etoile",
                "number", "draw", "grid", "frequency", "ranking", "statistic",
                "analysis", "next", "star",
            ))
        )
        if _has_question:
            _insult_prefix = get_insult_short(lang)
            logger.info(
                f"[EM CHAT] Insulte + question (type={_insult_type}, streak={_insult_streak})"
            )
        else:
            _phase = "I"
            if _insult_type == "menace":
                _insult_resp = get_menace_response(lang)
            else:
                _insult_resp = get_insult_response(lang, _insult_streak, history)
            logger.info(
                f"[EM CHAT] Insulte detectee (type={_insult_type}, streak={_insult_streak})"
            )
            return {"response": _insult_resp, "source": "hybride_insult", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0, "lang": lang}}, None

    # ── Phase C : Détection de compliments ──
    if not _insult_prefix:
        _compliment_type = _detect_compliment(message)
        if _compliment_type:
            _has_question_c = (
                '?' in message
                or bool(re.search(r'\b\d{1,2}\b', message))
                or any(kw in message.lower() for kw in (
                    # FR
                    "numéro", "numero", "tirage", "grille", "fréquence", "frequence",
                    "combien", "c'est quoi", "quel", "quelle", "comment", "pourquoi",
                    "classement", "statistique", "stat", "analyse",
                    "étoile", "etoile",
                    # EN
                    "number", "draw", "grid", "frequency", "ranking", "how",
                    "what", "which", "why", "star",
                    # ES
                    "número", "sorteo", "estrella", "cuánto", "cuál",
                    # PT
                    "sorteio", "estrela", "quanto", "qual",
                    # DE
                    "ziehung", "zahlen", "stern", "wie", "welche",
                    # NL
                    "trekking", "nummers", "ster", "hoeveel", "welke",
                ))
            )
            if not _has_question_c:
                _phase = "C"
                _comp_streak = _count_compliment_streak(history)
                _comp_resp = get_compliment_response(lang, _compliment_type, _comp_streak, history)
                logger.info(
                    f"[EM CHAT] Compliment detecte (type={_compliment_type}, streak={_comp_streak})"
                )
                return {"response": _comp_resp, "source": "hybride_compliment", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0, "lang": lang}}, None
            else:
                logger.info(
                    f"[EM CHAT] Compliment + question (type={_compliment_type}), passage au flow normal"
                )

    # ── Phase R : Détection intention de noter le site ──
    if _detect_site_rating(message):
        _phase = "R"
        logger.info("[EM CHAT] Site rating intent detected (lang=%s)", lang)
        return {"response": get_site_rating_response(lang), "source": "hybride_rating_invite", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0, "lang": lang}}, None

    # ── Phase SALUTATION : Salutation initiale sans historique (V65) ──
    if not history or len(history) <= 1:
        if _detect_salutation(message):
            _phase = "SALUTATION"
            _sal_resp = _get_salutation_response("em", lang)
            logger.info(f"[EM CHAT] Salutation detectee — court-circuit Phase SALUTATION (lang={lang})")
            return {"response": _sal_resp, "source": "hybride_salutation", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0, "lang": lang}}, None

    # ── Phase G : Détection génération de grille ──
    _generation_context = ""
    if _detect_generation(message):
        _phase = "G"
        try:
            from engine.hybride_em import generate_grids as _gen_em
            _gen_mode = _detect_generation_mode(message)
            _grid_count = _extract_grid_count(message)
            _forced = _extract_forced_numbers(message, game="em")
            _exclusions = _extract_exclusions(message)
            _has_exclusions = bool(_exclusions and any(_exclusions.values()))
            if _forced.get("error"):
                _generation_context = f"[ERREUR GÉNÉRATION] {_forced['error']}"
                logger.info(f"[EM CHAT] Phase G — erreur contrainte: {_forced['error']}")
            else:
                _gen_result = await asyncio.wait_for(
                    _gen_em(
                        n=_grid_count, mode=_gen_mode, lang=lang,
                        forced_nums=_forced["forced_nums"] or None,
                        forced_etoiles=_forced["forced_etoiles"] or None,
                        exclusions=_exclusions if any(_exclusions.values()) else None,
                        anti_collision=True,
                    ),
                    timeout=30.0,
                )
                if _gen_result and _gen_result.get("grids"):
                    _grids = _gen_result["grids"][:_grid_count]
                    _active_excl = _exclusions if any(_exclusions.values()) else None
                    if len(_grids) == 1:
                        _grids[0]["mode"] = _gen_mode
                        if _active_excl:
                            _grids[0]["exclusions"] = _active_excl
                        _generation_context = _format_generation_context_em(_grids[0])
                    else:
                        _parts = []
                        for idx, _grid in enumerate(_grids, 1):
                            _grid["mode"] = _gen_mode
                            if _active_excl:
                                _grid["exclusions"] = _active_excl
                            _parts.append(f"--- Grille {idx}/{len(_grids)} ---\n" + _format_generation_context_em(_grid))
                        _generation_context = "\n\n".join(_parts)
                    logger.info(
                        f"[EM CHAT] Phase G — {len(_grids)} grille(s) EM generee(s) mode={_gen_mode} "
                        f"forced={_forced['forced_nums']} etoiles={_forced['forced_etoiles']} "
                        f"exclusions={bool(_active_excl)}"
                    )
        except Exception as e:
            logger.warning(f"[EM CHAT] Phase G erreur: {e}")

    # ── Phase A : Détection argent / gains / paris ──
    if _detect_argent_em(message, lang):
        _phase = "A"
        _argent_resp = _get_argent_response_em(message, lang)
        if _insult_prefix:
            _argent_resp = _insult_prefix + "\n\n" + _argent_resp
        logger.info(f"[EM CHAT] Argent detecte — court-circuit Phase A (lang={lang})")
        return {"response": _argent_resp, "source": "hybride_argent", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0, "lang": lang}}, None

    # ── Phase GEO : Détection pays participants EM ──
    # Injecte le contexte "tirages communs" comme préfixe — ne bloque PAS le pipeline,
    # les phases suivantes ajoutent les stats demandées.
    _country_context = ""
    if _detect_country_em(message):
        _phase = "GEO"
        _country_context = _get_country_context_em(lang)
        logger.info(f"[EM CHAT] Phase GEO — pays detecte, contexte injecte (lang={lang})")

    # ── Phase 0 : Continuation contextuelle ──
    _continuation_mode = False
    _enriched_message = None

    if _is_short_continuation(message) and history:
        _enriched_message = _enrich_with_context(message, history)
        if _enriched_message != message:
            _continuation_mode = True
            _phase = "0"
            logger.info(
                f"[EM CONTINUATION] Reponse courte detectee: \"{message}\" "
                f"→ enrichissement contextuel"
            )

    # ── Phase AFFIRMATION : affirmation simple Oui/Ok/Non (V51) ──
    if not _continuation_mode and _is_affirmation_simple(message):
        if history and len(history) >= 2:
            _enriched_message = _enrich_with_context(message, history)
            if _enriched_message != message:
                _continuation_mode = True
                _phase = "AFFIRMATION"
                logger.info(
                    f"[EM AFFIRMATION] Affirmation simple avec contexte: \"{message}\" "
                    f"→ enrichissement contextuel (lang={lang})"
                )
        if not _continuation_mode:
            _phase = "AFFIRMATION_SANS_CONTEXTE"
            _resp = _AFFIRMATION_INVITATION_EM.get(lang, _AFFIRMATION_INVITATION_EM["fr"])
            if _insult_prefix:
                _resp = _insult_prefix + "\n\n" + _resp
            logger.info(f"[EM AFFIRMATION_SANS_CONTEXTE] \"{message}\" (lang={lang})")
            return {"response": _resp, "source": "hybride_affirmation",
                    "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0, "lang": lang}}, None

    # ── Phase GAME_KEYWORD : mot-clé jeu seul "Euromillions" (V51) ──
    if not _continuation_mode and _detect_game_keyword_alone(message):
        _phase = "GAME_KEYWORD"
        _resp = _GAME_KEYWORD_INVITATION_EM.get(lang, _GAME_KEYWORD_INVITATION_EM["fr"])
        if _insult_prefix:
            _resp = _insult_prefix + "\n\n" + _resp
        logger.info(f"[EM GAME_KEYWORD] Mot-cle jeu seul: \"{message}\" (lang={lang})")
        return {"response": _resp, "source": "hybride_game_keyword",
                "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0, "lang": lang}}, None

    # _generation_context is kept separate — stats phases below must still
    # run even when a grid was generated (multi-action: "compare X vs Y + generate")
    enrichment_context = ""

    # ── Phase EVAL : Évaluation grille soumise par l'utilisateur (V70) ──
    # Placed after enrichment_context init, before stats phases.
    # Skipped if Phase G already produced generation context (not an evaluation).
    if not _generation_context:
        _eval_result = _detect_grid_evaluation(message, game="em")
        if _eval_result:
            _phase = "EVAL"
            try:
                _eval_nums = _eval_result["numeros"]
                _eval_etoiles = _eval_result.get("etoiles")
                grille_analysis = await asyncio.wait_for(
                    analyze_grille_for_chat(_eval_nums, _eval_etoiles, lang=lang), timeout=30.0,
                )
                if grille_analysis:
                    enrichment_context = _format_grille_context_em(grille_analysis)
                    enrichment_context = enrichment_context.replace(
                        "[ANALYSE DE GRILLE",
                        "[ÉVALUATION GRILLE UTILISATEUR",
                    )
                    logger.info(
                        f"[EM CHAT] Phase EVAL — grille utilisateur evaluee: "
                        f"{_eval_nums} etoiles={_eval_etoiles} (lang={lang})"
                    )
            except Exception as e:
                logger.warning(f"[EM CHAT] Phase EVAL erreur: {e}")

    # Phase 0-bis : prochain tirage
    if not _continuation_mode and _detect_prochain_tirage_em(message):
        _phase = "0-bis"
        try:
            tirage_ctx = await asyncio.wait_for(_get_prochain_tirage_em(), timeout=30.0)
            if tirage_ctx:
                enrichment_context = tirage_ctx
                logger.info("[EM CHAT] Prochain tirage injecte")
        except Exception as e:
            logger.warning(f"[EM CHAT] Erreur prochain tirage: {e}")

    # Phase T : resultats d'un tirage
    if not _continuation_mode and not enrichment_context:
        tirage_target = _detect_tirage(message)
        if tirage_target is not None:
            _phase = "T"
            try:
                tirage_data = await asyncio.wait_for(
                    _get_tirage_data_em(tirage_target), timeout=30.0
                )
                if tirage_data:
                    enrichment_context = _format_tirage_context_em(tirage_data)
                    logger.info(f"[EM CHAT] Tirage injecte: {tirage_data['date']}")
                elif tirage_target != "latest":
                    date_fr = _format_date_fr(str(tirage_target))
                    enrichment_context = (
                        f"[RÉSULTAT TIRAGE — INTROUVABLE]\n"
                        f"Aucun tirage trouvé en base de données pour la date du {date_fr}.\n"
                        f"IMPORTANT : Ne PAS inventer de numéros. Indique simplement que "
                        f"ce tirage n'est pas disponible dans la base.\n"
                        f"Les tirages EuroMillions ont lieu les mardi et vendredi."
                    )
                    logger.info(f"[EM CHAT] Tirage introuvable pour: {tirage_target}")
            except Exception as e:
                logger.warning(f"[EM CHAT] Erreur tirage: {e}")

    force_sql = not _continuation_mode and not enrichment_context and _has_temporal_filter(message)
    if force_sql:
        logger.info("[EM CHAT] Filtre temporel detecte, force Phase SQL")

    # Phase 2 : detection de grille (5 numeros + etoiles)
    # Skip if Phase EVAL already analyzed the grid (enrichment_context already set)
    grille_nums, grille_etoiles = (None, None) if _continuation_mode else _detect_grille_em(message)
    if not force_sql and not enrichment_context and grille_nums is not None:
        _phase = "2"
        try:
            grille_result = await asyncio.wait_for(analyze_grille_for_chat(grille_nums, grille_etoiles, lang=lang), timeout=30.0)
            if grille_result:
                enrichment_context = _format_grille_context_em(grille_result)
                logger.info(f"[EM CHAT] Grille analysee: {grille_nums} etoiles={grille_etoiles}")
        except Exception as e:
            logger.warning(f"[EM CHAT] Erreur analyse grille: {e}")

    # Phase 3 : requete complexe — skipped when force_sql=True (temporal query routed to SQL)
    # V46: get_classement_numeros() has no date_from param, so temporal queries must go through Phase SQL.
    if not _continuation_mode and not force_sql and not enrichment_context:
        intent = _detect_requete_complexe_em(message)
        if intent:
            _phase = "3"
            try:
                if intent["type"] == "classement":
                    data = await asyncio.wait_for(get_classement_numeros(intent["num_type"], intent["tri"], intent["limit"]), timeout=30.0)
                    # V43: if user asks for both boules AND étoiles, fetch étoiles too
                    if data and intent["num_type"] == "boule" and _wants_both_boules_and_stars(message):
                        try:
                            star_data = await asyncio.wait_for(get_classement_numeros("etoile", intent["tri"], intent["limit"]), timeout=30.0)
                            if star_data:
                                star_intent = {**intent, "num_type": "etoile"}
                                enrichment_context = (
                                    _format_complex_context_em(intent, data)
                                    + "\n\n"
                                    + _format_complex_context_em(star_intent, star_data)
                                )
                                logger.info(f"[EM CHAT] Requete complexe: classement boules + étoiles")
                                data = None  # skip default formatting below
                        except Exception:
                            pass  # fallback to boules only
                elif intent["type"] == "comparaison":
                    data = await asyncio.wait_for(get_comparaison_numeros(intent["num1"], intent["num2"], intent["num_type"]), timeout=30.0)
                elif intent["type"] == "categorie":
                    data = await asyncio.wait_for(get_numeros_par_categorie(intent["categorie"], intent["num_type"]), timeout=30.0)
                else:
                    data = None

                if data:
                    enrichment_context = _format_complex_context_em(intent, data)
                    logger.info(f"[EM CHAT] Requete complexe: {intent['type']}")
            except Exception as e:
                logger.warning(f"[EM CHAT] Erreur requete complexe: {e}")

    # Phase 3-bis : comparaison avec filtre temporel
    # Comme Phase P, les comparaisons sont des requêtes structurées —
    # le filtre temporel ne doit pas les bloquer.
    if not _continuation_mode and force_sql and not enrichment_context:
        intent = _detect_requete_complexe_em(message)
        if intent and intent["type"] == "comparaison":
            _phase = "3-bis"
            try:
                _date_from = _extract_temporal_date(message)
                data = await asyncio.wait_for(
                    get_comparaison_with_period(
                        intent["num1"], intent["num2"], intent["num_type"], _date_from
                    ),
                    timeout=30.0,
                )
                if data:
                    enrichment_context = _format_complex_context_em(intent, data)
                    force_sql = False
                    logger.info(
                        f"[EM CHAT] Phase 3-bis — comparaison temporelle "
                        f"{intent['num1']} vs {intent['num2']} (date_from={_date_from})"
                    )
            except Exception as e:
                logger.warning(f"[EM CHAT] Erreur comparaison temporelle: {e}")

    # Phase P+ : co-occurrences N>3 — réponse honnête "pas implémenté"
    if not _continuation_mode and not enrichment_context:
        if _detect_cooccurrence_high_n(message):
            _phase = "P+"
            _high_n_resp = _get_cooccurrence_high_n_response(message, lang=lang)
            if _insult_prefix:
                _high_n_resp = _insult_prefix + "\n\n" + _high_n_resp
            logger.info(f"[EM CHAT] Co-occurrence N>3 — redirection paires/triplets (lang={lang})")
            return {"response": _high_n_resp, "source": "hybride_cooccurrence", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0, "lang": lang}}, None

    # Phase P : triplets de numéros (testé avant paires)
    # Note: pas de guard force_sql — triplets sont des requêtes structurées,
    # pas du text-to-SQL. Le filtre temporel ne doit pas les bloquer.
    if not _continuation_mode and not enrichment_context:
        if _detect_triplets_em(message):
            _phase = "P"
            try:
                triplets_data = await asyncio.wait_for(
                    get_triplet_correlations(top_n=5), timeout=30.0
                )
                if triplets_data:
                    enrichment_context = _format_triplets_context_em(triplets_data)
                    logger.info("[EM CHAT] Triplets injectes")
            except Exception as e:
                logger.warning(f"[EM CHAT] Erreur triplets: {e}")

    # Phase P : paires de numéros
    if not _continuation_mode and not enrichment_context:
        if _detect_paires_em(message):
            _phase = "P"
            try:
                pairs_data = await asyncio.wait_for(
                    get_pair_correlations(top_n=5), timeout=30.0
                )
                if pairs_data:
                    enrichment_context = _format_pairs_context_em(pairs_data)
                    star_data = await asyncio.wait_for(
                        get_star_pair_correlations(top_n=5), timeout=30.0
                    )
                    if star_data:
                        enrichment_context += "\n\n" + _format_star_pairs_context_em(star_data)
                    logger.info("[EM CHAT] Paires injectees")
            except Exception as e:
                logger.warning(f"[EM CHAT] Erreur paires: {e}")

    # ── Phase OOR : Détection numéro hors range ──
    if not _continuation_mode and not force_sql and not enrichment_context:
        _oor_num, _oor_type = _detect_out_of_range_em(message)
        if _oor_num is not None:
            _phase = "OOR"
            _oor_streak = _count_oor_streak_em(history)
            _oor_resp = get_oor_response(lang, _oor_num, _oor_type, _oor_streak)
            if _insult_prefix:
                _oor_resp = _insult_prefix + "\n\n" + _oor_resp
            logger.info(
                f"[EM CHAT] Numero hors range: {_oor_num} "
                f"(type={_oor_type}, streak={_oor_streak})"
            )
            return {"response": _oor_resp, "source": "hybride_oor", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0, "lang": lang}}, None

    # Phase 1 : detection de numero simple
    if not _continuation_mode and not force_sql and not enrichment_context:
        numero, type_num = _detect_numero_em(message)
        if numero is not None:
            _phase = "1"
            try:
                stats = await asyncio.wait_for(get_numero_stats(numero, type_num), timeout=30.0)
                if stats:
                    enrichment_context = _format_stats_context_em(stats)
                    logger.info(f"[EM CHAT] Stats BDD injectees: numero={numero}, type={type_num}")
            except Exception as e:
                logger.warning(f"[EM CHAT] Erreur stats BDD (numero={numero}): {e}")

    # Phase SQL : Text-to-SQL fallback (shared helper)
    enrichment_context, _sql_query, _sql_status = await run_text_to_sql(
        message, http_client, gem_api_key, history,
        generate_sql_fn=_generate_sql_em, validate_sql_fn=_validate_sql,
        ensure_limit_fn=_ensure_limit, execute_sql_fn=_execute_safe_sql,
        format_result_fn=_format_sql_result, max_per_session=_MAX_SQL_PER_SESSION,
        log_prefix="[EM TEXT2SQL]", force_sql=force_sql,
        has_data_signal_fn=_has_data_signal,
        continuation_mode=_continuation_mode, enrichment_context=enrichment_context,
        sql_gen_kwargs={"lang": lang},
    )
    if _sql_query or _sql_status != "N/A":
        _phase = "SQL"

    # Quand force_sql=True et Phase SQL echoue, NE PAS fallback vers
    # Phase 3 (donnees globales sans filtre date) — cela retournerait
    # des stats all-time alors que l'utilisateur demande une periode.
    if force_sql and not enrichment_context:
        logger.warning(
            f"[EM CHAT] Phase SQL echouee avec filtre temporel, "
            f"PAS de fallback Phase 3 (evite stats all-time incorrectes) | "
            f'question="{message[:80]}"'
        )

    # ── Combine generation context + stats context (multi-action support) ──
    if _generation_context and enrichment_context:
        enrichment_context = f"{enrichment_context}\n\n{_generation_context}"
        logger.info("[EM CHAT] Multi-action: stats + generation combines")
    elif _generation_context:
        enrichment_context = _generation_context

    logger.info(
        f"[EM DEBUG] force_sql={force_sql} | continuation={_continuation_mode} | "
        f"enrichment={bool(enrichment_context)} | generation={bool(_generation_context)} | "
        f"question=\"{message[:60]}\" | history_len={len(history or [])}"
    )

    _session_ctx = _build_session_context_em(history, message)

    # Prepend country context (Phase GEO) if detected
    if _country_context:
        if enrichment_context:
            enrichment_context = _country_context + "\n\n" + enrichment_context
        else:
            enrichment_context = _country_context

    if _continuation_mode and _enriched_message:
        user_text = f"[Page: {page}]\n\n{_enriched_message}"
    elif enrichment_context:
        user_text = f"[Page: {page}]\n\n{enrichment_context}\n\n[Question utilisateur] {message}"
    else:
        user_text = f"[Page: {page}] {message}"

    if _session_ctx:
        user_text = f"{_session_ctx}\n\n{user_text}"

    contents.append({"role": "user", "parts": [{"text": user_text}]})

    return None, {
        "system_prompt": system_prompt,
        "gem_api_key": gem_api_key,
        "contents": contents,
        "mode": mode,
        "insult_prefix": _insult_prefix,
        "history": history,
        "lang": lang,
        "fallback": _fallback,
        "_chat_meta": {
            "phase": _phase, "t0": _t0, "lang": lang,
            "sql_query": _sql_query, "sql_status": _sql_status,
            "grid_count": _grid_count, "has_exclusions": _has_exclusions,
        },
    }


def _log_from_meta_em(meta, message, response_preview="",
                      is_error=False, error_detail=None):
    """Helper: call log_chat_exchange from _chat_meta dict (EM, delegates to shared)."""
    _log_from_meta_shared(meta, "em", meta.get("lang", "fr") if meta else "fr",
                          message, response_preview, is_error=is_error, error_detail=error_detail)


async def handle_chat_em(message: str, history: list, page: str, http_client, lang: str = "fr") -> dict:
    """Pipeline 12 phases du chatbot HYBRIDE EuroMillions. Retourne dict(response, source, mode)."""
    early, ctx = await _prepare_chat_context_em(message, history, page, http_client, lang)
    if early:
        _log_from_meta_em(early.get("_chat_meta"), message, early.get("response", ""))
        return early
    ctx["_http_client"] = http_client
    return await call_gemini_and_respond(
        ctx, ctx["fallback"], "[EM CHAT]", "em", lang, message, page,
        sponsor_kwargs={"lang": ctx["lang"], "module": "em"},
        breaker=gemini_breaker,
    )


def _sse_event_em(data):
    """Format dict as SSE event line (delegates to shared)."""
    return _sse_event_shared(data)


async def handle_chat_stream_em(message: str, history: list, page: str, http_client, lang: str = "fr"):
    """Async generator — SSE streaming du chatbot HYBRIDE EuroMillions. Yields SSE event strings."""
    early, ctx = await _prepare_chat_context_em(message, history, page, http_client, lang)
    if early:
        _log_from_meta_em(early.get("_chat_meta"), message, early.get("response", ""))
        yield _sse_event_em({
            "chunk": early["response"],
            "source": early["source"],
            "mode": early["mode"],
            "is_done": True,
        })
        return

    ctx["_http_client"] = http_client
    async for event in stream_and_respond(
        ctx, ctx["fallback"], "[EM CHAT]", "em", lang,
        message, page, call_type="chat_em",
        sponsor_kwargs={"lang": ctx["lang"], "module": "em"},
        stream_fn=stream_gemini_chat,
    ):
        yield event


# =========================
# PITCH GRILLES EM — Gemini
# =========================

async def handle_pitch_em(grilles: list, http_client, lang: str = "fr") -> dict:
    """Genere des pitchs HYBRIDE personnalises pour chaque grille EM via Gemini."""
    # Validation EM
    if not grilles or len(grilles) > 5:
        return {"success": False, "data": None, "error": "Entre 1 et 5 grilles requises", "status_code": 400}
    for i, g in enumerate(grilles):
        if len(g.numeros) != 5:
            return {"success": False, "data": None, "error": f"Grille {i+1}: 5 numéros requis", "status_code": 400}
        if len(set(g.numeros)) != 5:
            return {"success": False, "data": None, "error": f"Grille {i+1}: numéros doivent être uniques", "status_code": 400}
        if not all(1 <= n <= 50 for n in g.numeros):
            return {"success": False, "data": None, "error": f"Grille {i+1}: numéros entre 1 et 50", "status_code": 400}
        if g.etoiles is not None:
            if len(g.etoiles) > 2:
                return {"success": False, "data": None, "error": f"Grille {i+1}: maximum 2 étoiles", "status_code": 400}
            if len(g.etoiles) != len(set(g.etoiles)):
                return {"success": False, "data": None, "error": f"Grille {i+1}: étoiles doivent être uniques", "status_code": 400}
            if not all(1 <= e <= 12 for e in g.etoiles):
                return {"success": False, "data": None, "error": f"Grille {i+1}: étoiles entre 1 et 12", "status_code": 400}

    grilles_data = [{"numeros": g.numeros, "etoiles": g.etoiles, "score_conformite": g.score_conformite, "severity": g.severity} for g in grilles]
    return await handle_pitch_common(
        grilles_data, http_client, lang,
        context_coro=prepare_grilles_pitch_context(grilles_data, lang=lang),
        load_prompt_fn=lambda name: load_prompt_em(name, lang=lang),
        prompt_name="prompt_pitch_grille_em",
        log_prefix="[EM PITCH]", breaker=gemini_breaker,
    )
