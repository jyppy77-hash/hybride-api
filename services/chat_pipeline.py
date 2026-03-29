import os
import re
import asyncio
import logging
import time
import json
import httpx

from services.prompt_loader import load_prompt
from services.gemini import GEMINI_MODEL_URL, stream_gemini_chat
from services.circuit_breaker import gemini_breaker, CircuitOpenError
from services.stats_service import (
    get_numero_stats, analyze_grille_for_chat,
    get_classement_numeros, get_comparaison_numeros, get_comparaison_with_period,
    get_numeros_par_categorie,
    prepare_grilles_pitch_context, get_pair_correlations, get_triplet_correlations,
)

from services.chat_detectors import (
    _detect_mode, _is_short_continuation, _detect_prochain_tirage,
    _detect_tirage, _has_temporal_filter, _extract_temporal_date,
    _detect_numero, _detect_grille,
    _detect_requete_complexe, _detect_paires, _detect_triplets, _detect_insulte,
    _count_insult_streak, _get_insult_response, _get_insult_short,
    _get_menace_response, _detect_compliment, _count_compliment_streak,
    _get_compliment_response, _detect_out_of_range, _count_oor_streak,
    _get_oor_response, _detect_argent, _get_argent_response,
    _detect_generation, _detect_generation_mode, _extract_forced_numbers, _extract_grid_count,
    _extract_exclusions,
    _detect_cooccurrence_high_n, _get_cooccurrence_high_n_response,
    _detect_site_rating, get_site_rating_response,
    _is_affirmation_simple, _detect_game_keyword_alone,  # V51
    _detect_salutation, _get_salutation_response,  # V65
    _has_data_signal,  # V65
    _detect_grid_evaluation,  # V70
)
from services.chat_sql import (
    _get_prochain_tirage, _get_tirage_data, _generate_sql, _validate_sql,
    _ensure_limit, _execute_safe_sql, _format_sql_result, _MAX_SQL_PER_SESSION,
)
from services.chat_utils import (
    FALLBACK_RESPONSE, _enrich_with_context, _clean_response, _strip_non_latin,
    _strip_sponsor_from_text, _get_sponsor_if_due, _format_date_fr, StreamBuffer,
    _format_tirage_context, _format_stats_context, _format_grille_context,
    _format_complex_context, _format_pairs_context, _format_triplets_context,
    _build_session_context, _format_generation_context,
)
from services.chat_logger import log_chat_exchange
from services.chat_pipeline_shared import (
    sse_event as _sse_event_shared,
    log_from_meta as _log_from_meta_shared,
    build_gemini_contents,
    run_text_to_sql,
    call_gemini_and_respond,
    stream_and_respond,
    handle_pitch_common,
)
import db_cloudsql

logger = logging.getLogger(__name__)

# F02: cached draw count for {DRAW_COUNT} placeholder injection
_draw_count_cache: dict[str, tuple[float, int]] = {}  # game -> (timestamp, count)
_DRAW_COUNT_TTL = 3600  # 1h


async def _get_draw_count(game: str = "loto") -> int:
    """Return draw count from DB with 1h cache. Returns 0 on error.

    TTL 1h: after a new draw, count may be stale by 1 for up to 60min.
    This is intentional — cosmetic impact only ("~980 tirages" vs "~981").
    """
    now = time.monotonic()
    cached = _draw_count_cache.get(game)
    if cached and (now - cached[0]) < _DRAW_COUNT_TTL:
        return cached[1]
    table = "tirages" if game == "loto" else "tirages_euromillions"
    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            row = await cursor.fetchone()
            count = row["cnt"] if row else 0
            _draw_count_cache[game] = (now, count)
            return count
    except Exception as e:
        logger.warning("[DRAW_COUNT] Error fetching count for %s: %s", game, e)
        return cached[1] if cached else 0


# =========================
# HYBRIDE Chatbot — Pipeline 12 phases
# =========================

async def _prepare_chat_context(message: str, history: list, page: str, http_client, lang: str = "fr"):
    """
    Phases I-SQL : prepare le contexte pour l'appel Gemini.
    Retourne (early_return_or_None, ctx_dict_or_None).
    Si early_return n'est pas None, c'est une reponse complete (insult/compliment/OOR).
    Sinon, ctx_dict contient les cles pour l'appel Gemini.
    """
    _t0 = time.monotonic()
    mode = _detect_mode(message, page)

    # ── Chat Monitor: phase tracking (V44) ──
    _phase = "Gemini"         # default fallthrough
    _sql_query = None
    _sql_status = "N/A"
    _grid_count = 0
    _has_exclusions = False
    _is_error = False
    _error_detail = None

    system_prompt = load_prompt("CHATBOT")
    if not system_prompt:
        logger.error("[HYBRIDE CHAT] Prompt systeme introuvable")
        return {"response": FALLBACK_RESPONSE, "source": "fallback", "mode": mode}, None

    # F02: inject dynamic draw count
    draw_count = await _get_draw_count("loto")
    if draw_count and "{DRAW_COUNT}" in system_prompt:
        system_prompt = system_prompt.replace("{DRAW_COUNT}", str(draw_count))

    # ── Anti-re-introduction : TOUJOURS injecté (le welcome JS a déjà fait la présentation) ──
    system_prompt += (
        "\n\n[RAPPEL CRITIQUE — ANTI-RE-PRÉSENTATION]\n"
        "Le message de bienvenue affiché côté interface a DÉJÀ présenté HYBRIDE à l'utilisateur. "
        "Tu t'es DÉJÀ présenté. NE TE RE-PRÉSENTE PAS. "
        "Ne dis PAS 'Je suis HYBRIDE', 'je m'appelle HYBRIDE', etc. "
        "Ne dis PAS 'Salut !' en début de réponse s'il ne t'a pas salué. "
        "Va DIRECTEMENT à la réponse à sa question."
    )

    # ── Contexte pédagogique : injecté quand la question porte sur les fréquences/tendances ──
    from services.stats_analysis import should_inject_pedagogical_context, PEDAGOGICAL_CONTEXT
    if should_inject_pedagogical_context(message):
        system_prompt += PEDAGOGICAL_CONTEXT

    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        logger.warning("[HYBRIDE CHAT] GEM_API_KEY non configuree — fallback")
        return {"response": FALLBACK_RESPONSE, "source": "fallback", "mode": mode}, None

    contents, history = build_gemini_contents(history, message, _detect_insulte)

    # ── Phase I : Détection d'insultes / agressivité ──
    _insult_prefix = ""
    _insult_type = _detect_insulte(message)
    if _insult_type:
        _insult_streak = _count_insult_streak(history)
        _has_question = (
            '?' in message
            or bool(re.search(r'\b\d{1,2}\b', message))
            or any(kw in message.lower() for kw in (
                # FR
                "numéro", "numero", "tirage", "grille", "fréquence", "frequence",
                "classement", "statistique", "stat", "analyse", "prochain",
                # EN
                "number", "draw", "grid", "frequency", "ranking", "statistic",
                "analysis", "next",
                # ES
                "número", "sorteo", "resultado", "cuadrícula",
                # PT
                "sorteio", "grelha",
                # DE
                "ziehung", "zahlen", "ergebnis",
                # NL
                "trekking", "nummers", "resultaat",
            ))
        )
        if _has_question:
            _insult_prefix = _get_insult_short()
            logger.info(
                f"[HYBRIDE CHAT] Insulte + question (type={_insult_type}, streak={_insult_streak})"
            )
        else:
            _phase = "I"
            if _insult_type == "menace":
                _insult_resp = _get_menace_response()
            else:
                _insult_resp = _get_insult_response(_insult_streak, history)
            logger.info(
                f"[HYBRIDE CHAT] Insulte detectee (type={_insult_type}, streak={_insult_streak})"
            )
            return {"response": _insult_resp, "source": "hybride_insult", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0}}, None

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
                    # EN
                    "number", "draw", "grid", "frequency", "ranking", "how",
                    "what", "which", "why",
                    # ES
                    "número", "sorteo", "cuánto", "cuál",
                    # PT
                    "sorteio", "quanto", "qual",
                    # DE
                    "ziehung", "zahlen", "wie", "welche",
                    # NL
                    "trekking", "nummers", "hoeveel", "welke",
                ))
            )
            if not _has_question_c:
                _phase = "C"
                _comp_streak = _count_compliment_streak(history)
                _comp_resp = _get_compliment_response(_compliment_type, _comp_streak, history)
                logger.info(
                    f"[HYBRIDE CHAT] Compliment detecte (type={_compliment_type}, streak={_comp_streak})"
                )
                return {"response": _comp_resp, "source": "hybride_compliment", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0}}, None
            else:
                logger.info(
                    f"[HYBRIDE CHAT] Compliment + question (type={_compliment_type}), passage au flow normal"
                )

    # ── Phase R : Détection intention de noter le site ──
    if _detect_site_rating(message):
        _phase = "R"
        logger.info("[HYBRIDE CHAT] Site rating intent detected")
        return {"response": get_site_rating_response(lang), "source": "hybride_rating_invite", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0}}, None

    # ── Phase SALUTATION : Salutation initiale sans historique (V65) ──
    if not history or len(history) <= 1:
        if _detect_salutation(message):
            _phase = "SALUTATION"
            _sal_resp = _get_salutation_response("loto", lang)
            logger.info("[HYBRIDE CHAT] Salutation detectee — court-circuit Phase SALUTATION")
            return {"response": _sal_resp, "source": "hybride_salutation", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0}}, None

    # ── Phase G : Détection génération de grille ──
    _generation_context = ""
    if _detect_generation(message):
        _phase = "G"
        try:
            from engine.hybride import generate_grids as _gen_loto
            _gen_mode = _detect_generation_mode(message)
            _grid_count = _extract_grid_count(message)
            _forced = _extract_forced_numbers(message, game="loto")
            _exclusions = _extract_exclusions(message)
            _has_exclusions = bool(_exclusions and any(_exclusions.values()))
            if _forced.get("error"):
                _generation_context = f"[ERREUR GÉNÉRATION] {_forced['error']}"
                logger.info(f"[HYBRIDE CHAT] Phase G — erreur contrainte: {_forced['error']}")
            else:
                _gen_result = await asyncio.wait_for(
                    _gen_loto(
                        n=_grid_count, mode=_gen_mode, lang=lang,
                        forced_nums=_forced["forced_nums"] or None,
                        forced_chance=_forced["forced_chance"],
                        exclusions=_exclusions if any(_exclusions.values()) else None,
                        anti_collision=True,
                    ),
                    timeout=30.0,
                )
                if _gen_result and _gen_result.get("grids"):
                    _grids = _gen_result["grids"][:_grid_count]
                    if len(_grids) == 1:
                        _grids[0]["mode"] = _gen_mode
                        _generation_context = _format_generation_context(_grids[0])
                    else:
                        _parts = []
                        for idx, _grid in enumerate(_grids, 1):
                            _grid["mode"] = _gen_mode
                            _parts.append(f"--- Grille {idx}/{len(_grids)} ---\n" + _format_generation_context(_grid))
                        _generation_context = "\n\n".join(_parts)
                    logger.info(
                        f"[HYBRIDE CHAT] Phase G — {len(_grids)} grille(s) Loto generee(s) mode={_gen_mode} "
                        f"forced={_forced['forced_nums']} chance={_forced['forced_chance']}"
                    )
        except Exception as e:
            logger.warning(f"[HYBRIDE CHAT] Phase G erreur: {e}")

    # ── Phase A : Détection argent / gains / paris (multilingue V71) ──
    if _detect_argent(message, lang):
        _phase = "A"
        _argent_resp = _get_argent_response(message, lang)
        if _insult_prefix:
            _argent_resp = _insult_prefix + "\n\n" + _argent_resp
        logger.info("[HYBRIDE CHAT] Argent detecte — court-circuit Phase A")
        return {"response": _argent_resp, "source": "hybride_argent", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0}}, None

    # Phase GEO — EM-only (Loto = France-only, pas de détection pays)
    # Voir chat_pipeline_em.py pour l'implémentation EM

    # ── Phase 0 : Continuation contextuelle ──
    _continuation_mode = False
    _enriched_message = None

    if _is_short_continuation(message) and history:
        _enriched_message = _enrich_with_context(message, history)
        if _enriched_message != message:
            _continuation_mode = True
            _phase = "0"
            logger.info(
                f"[CONTINUATION] Reponse courte detectee: \"{message}\" "
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
                    f"[AFFIRMATION] Affirmation simple avec contexte: \"{message}\" "
                    f"→ enrichissement contextuel"
                )
        if not _continuation_mode:
            _phase = "AFFIRMATION_SANS_CONTEXTE"
            _resp = (
                "Je suis pret a vous aider ! Que souhaitez-vous analyser ?\n\n"
                "- Statistiques d'un numero (ex: le 7)\n"
                "- Derniers tirages (ex: dernier tirage)\n"
                "- Generer une grille optimisee (ex: genere une grille)\n"
                "- Tendances chaud/froid (ex: numeros chauds)"
            )
            if _insult_prefix:
                _resp = _insult_prefix + "\n\n" + _resp
            logger.info(f"[AFFIRMATION_SANS_CONTEXTE] \"{message}\" — pas d'historique suffisant")
            return {"response": _resp, "source": "hybride_affirmation",
                    "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0}}, None

    # ── Phase GAME_KEYWORD : mot-clé jeu seul "Loto" (V51) ──
    if not _continuation_mode and _detect_game_keyword_alone(message):
        _phase = "GAME_KEYWORD"
        _resp = (
            "Bienvenue sur HYBRIDE ! Voici ce que je peux faire :\n\n"
            "- Statistiques d'un numero (ex: le 7)\n"
            "- Derniers tirages (ex: dernier tirage)\n"
            "- Generer une grille optimisee (ex: genere une grille)\n"
            "- Tendances chaud/froid (ex: numeros chauds)"
        )
        if _insult_prefix:
            _resp = _insult_prefix + "\n\n" + _resp
        logger.info(f"[GAME_KEYWORD] Mot-cle jeu seul: \"{message}\"")
        return {"response": _resp, "source": "hybride_game_keyword",
                "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0}}, None

    # _generation_context is kept separate — stats phases below must still
    # run even when a grid was generated (multi-action: "compare X vs Y + generate")
    enrichment_context = ""

    # ── Phase EVAL : Évaluation grille soumise par l'utilisateur (V70) ──
    # Placed after enrichment_context init, before stats phases.
    # Skipped if Phase G already produced generation context (not an evaluation).
    if not _generation_context:
        _eval_result = _detect_grid_evaluation(message, game="loto")
        if _eval_result:
            _phase = "EVAL"
            try:
                _eval_nums = _eval_result["numeros"]
                _eval_chance = _eval_result.get("chance")
                grille_analysis = await asyncio.wait_for(
                    analyze_grille_for_chat(_eval_nums, _eval_chance), timeout=30.0,
                )
                if grille_analysis:
                    enrichment_context = _format_grille_context(grille_analysis)
                    enrichment_context = enrichment_context.replace(
                        "[ANALYSE DE GRILLE",
                        "[ÉVALUATION GRILLE UTILISATEUR",
                    )
                    logger.info(
                        f"[HYBRIDE CHAT] Phase EVAL — grille utilisateur evaluee: "
                        f"{_eval_nums} chance={_eval_chance}"
                    )
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Phase EVAL erreur: {e}")

    # Phase 0-bis : prochain tirage
    if not _continuation_mode and _detect_prochain_tirage(message):
        _phase = "0-bis"
        try:
            tirage_ctx = await asyncio.wait_for(_get_prochain_tirage(), timeout=30.0)
            if tirage_ctx:
                enrichment_context = tirage_ctx
                logger.info("[HYBRIDE CHAT] Prochain tirage injecte")
        except Exception as e:
            logger.warning(f"[HYBRIDE CHAT] Erreur prochain tirage: {e}")

    # Phase T : resultats d'un tirage
    if not _continuation_mode and not enrichment_context:
        tirage_target = _detect_tirage(message)
        if tirage_target is not None:
            _phase = "T"
            try:
                tirage_data = await asyncio.wait_for(
                    _get_tirage_data(tirage_target), timeout=30.0
                )
                if tirage_data:
                    enrichment_context = _format_tirage_context(tirage_data)
                    logger.info(f"[HYBRIDE CHAT] Tirage injecte: {tirage_data['date']}")
                elif tirage_target != "latest":
                    date_fr = _format_date_fr(str(tirage_target))
                    enrichment_context = (
                        f"[RÉSULTAT TIRAGE \u2014 INTROUVABLE]\n"
                        f"Aucun tirage trouvé en base de données pour la date du {date_fr}.\n"
                        f"IMPORTANT : Ne PAS inventer de numéros. Indique simplement que "
                        f"ce tirage n'est pas disponible dans la base.\n"
                        f"Les tirages du Loto ont lieu les lundi, mercredi et samedi."
                    )
                    logger.info(f"[HYBRIDE CHAT] Tirage introuvable pour: {tirage_target}")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Erreur tirage: {e}")

    force_sql = not _continuation_mode and not enrichment_context and _has_temporal_filter(message)
    if force_sql:
        logger.info("[HYBRIDE CHAT] Filtre temporel detecte, force Phase SQL")

    # Phase 2 : detection de grille (5 numeros)
    # Skip if Phase EVAL already analyzed the grid (enrichment_context already set)
    grille_nums, grille_chance = (None, None) if _continuation_mode else _detect_grille(message)
    if not force_sql and not enrichment_context and grille_nums is not None:
        _phase = "2"
        try:
            grille_result = await asyncio.wait_for(analyze_grille_for_chat(grille_nums, grille_chance), timeout=30.0)
            if grille_result:
                enrichment_context = _format_grille_context(grille_result)
                logger.info(f"[HYBRIDE CHAT] Grille analysee: {grille_nums} chance={grille_chance}")
        except Exception as e:
            logger.warning(f"[HYBRIDE CHAT] Erreur analyse grille: {e}")

    # Phase 3 : requete complexe — skipped when force_sql=True (temporal query routed to SQL)
    # V46: get_classement_numeros() has no date_from param, so temporal queries must go through Phase SQL.
    if not _continuation_mode and not force_sql and not enrichment_context:
        intent = _detect_requete_complexe(message)
        if intent:
            _phase = "3"
            try:
                if intent["type"] == "classement":
                    data = await asyncio.wait_for(get_classement_numeros(intent["num_type"], intent["tri"], intent["limit"]), timeout=30.0)
                elif intent["type"] == "comparaison":
                    data = await asyncio.wait_for(get_comparaison_numeros(intent["num1"], intent["num2"], intent["num_type"]), timeout=30.0)
                elif intent["type"] == "categorie":
                    data = await asyncio.wait_for(get_numeros_par_categorie(intent["categorie"], intent["num_type"]), timeout=30.0)
                else:
                    data = None

                if data:
                    enrichment_context = _format_complex_context(intent, data)
                    logger.info(f"[HYBRIDE CHAT] Requete complexe: {intent['type']}")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Erreur requete complexe: {e}")

    # Phase 3-bis : comparaison avec filtre temporel
    # Comme Phase P, les comparaisons sont des requêtes structurées —
    # le filtre temporel ne doit pas les bloquer.
    if not _continuation_mode and force_sql and not enrichment_context:
        intent = _detect_requete_complexe(message)
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
                    enrichment_context = _format_complex_context(intent, data)
                    force_sql = False
                    logger.info(
                        f"[HYBRIDE CHAT] Phase 3-bis — comparaison temporelle "
                        f"{intent['num1']} vs {intent['num2']} (date_from={_date_from})"
                    )
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Erreur comparaison temporelle: {e}")

    # Phase P+ : co-occurrences N>3 — réponse honnête "pas implémenté"
    if not _continuation_mode and not enrichment_context:
        if _detect_cooccurrence_high_n(message):
            _phase = "P+"
            _high_n_resp = _get_cooccurrence_high_n_response(message, lang=lang)
            if _insult_prefix:
                _high_n_resp = _insult_prefix + "\n\n" + _high_n_resp
            logger.info("[HYBRIDE CHAT] Co-occurrence N>3 — redirection paires/triplets")
            return {"response": _high_n_resp, "source": "hybride_cooccurrence", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0}}, None

    # Phase P : triplets de numéros (testé avant paires)
    # Note: pas de guard force_sql — triplets sont des requêtes structurées,
    # pas du text-to-SQL. Le filtre temporel ne doit pas les bloquer.
    if not _continuation_mode and not enrichment_context:
        if _detect_triplets(message):
            _phase = "P"
            try:
                triplets_data = await asyncio.wait_for(
                    get_triplet_correlations(top_n=5), timeout=30.0
                )
                if triplets_data:
                    enrichment_context = _format_triplets_context(triplets_data)
                    logger.info("[HYBRIDE CHAT] Triplets injectes")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Erreur triplets: {e}")

    # Phase P : paires de numéros
    if not _continuation_mode and not enrichment_context:
        if _detect_paires(message):
            _phase = "P"
            try:
                pairs_data = await asyncio.wait_for(
                    get_pair_correlations(top_n=5), timeout=30.0
                )
                if pairs_data:
                    enrichment_context = _format_pairs_context(pairs_data)
                    logger.info("[HYBRIDE CHAT] Paires injectees")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Erreur paires: {e}")

    # ── Phase OOR : Détection numéro hors range ──
    if not _continuation_mode and not force_sql and not enrichment_context:
        _oor_num, _oor_type = _detect_out_of_range(message)
        if _oor_num is not None:
            _phase = "OOR"
            _oor_streak = _count_oor_streak(history)
            _oor_resp = _get_oor_response(_oor_num, _oor_type, _oor_streak)
            if _insult_prefix:
                _oor_resp = _insult_prefix + "\n\n" + _oor_resp
            logger.info(
                f"[HYBRIDE CHAT] Numero hors range: {_oor_num} "
                f"(type={_oor_type}, streak={_oor_streak})"
            )
            return {"response": _oor_resp, "source": "hybride_oor", "mode": mode, "_chat_meta": {"phase": _phase, "t0": _t0}}, None

    # Phase 1 : detection de numero simple
    if not _continuation_mode and not force_sql and not enrichment_context:
        numero, type_num = _detect_numero(message)
        if numero is not None:
            _phase = "1"
            try:
                stats = await asyncio.wait_for(get_numero_stats(numero, type_num), timeout=30.0)
                if stats:
                    enrichment_context = _format_stats_context(stats)
                    logger.info(f"[HYBRIDE CHAT] Stats BDD injectees: numero={numero}, type={type_num}")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Erreur stats BDD (numero={numero}): {e}")

    # Phase SQL : Text-to-SQL fallback (shared helper)
    enrichment_context, _sql_query, _sql_status = await run_text_to_sql(
        message, http_client, gem_api_key, history,
        generate_sql_fn=_generate_sql, validate_sql_fn=_validate_sql,
        ensure_limit_fn=_ensure_limit, execute_sql_fn=_execute_safe_sql,
        format_result_fn=_format_sql_result, max_per_session=_MAX_SQL_PER_SESSION,
        log_prefix="[TEXT2SQL]", force_sql=force_sql,
        has_data_signal_fn=_has_data_signal,
        continuation_mode=_continuation_mode, enrichment_context=enrichment_context,
    )
    if _sql_query or _sql_status != "N/A":
        _phase = "SQL"

    # Quand force_sql=True et Phase SQL echoue, NE PAS fallback vers
    # Phase 3 (donnees globales sans filtre date) — cela retournerait
    # des stats all-time alors que l'utilisateur demande une periode.
    if force_sql and not enrichment_context:
        logger.warning(
            f"[HYBRIDE CHAT] Phase SQL echouee avec filtre temporel, "
            f"PAS de fallback Phase 3 (evite stats all-time incorrectes) | "
            f'question="{message[:80]}"'
        )

    # ── Combine generation context + stats context (multi-action support) ──
    if _generation_context and enrichment_context:
        enrichment_context = f"{enrichment_context}\n\n{_generation_context}"
        logger.info("[HYBRIDE CHAT] Multi-action: stats + generation combines")
    elif _generation_context:
        enrichment_context = _generation_context

    logger.info(
        f"[DEBUG] force_sql={force_sql} | continuation={_continuation_mode} | "
        f"enrichment={bool(enrichment_context)} | generation={bool(_generation_context)} | "
        f"question=\"{message[:60]}\" | history_len={len(history or [])}"
    )

    _session_ctx = _build_session_context(history, message)

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
        "_chat_meta": {
            "phase": _phase, "t0": _t0,
            "sql_query": _sql_query, "sql_status": _sql_status,
            "grid_count": _grid_count, "has_exclusions": _has_exclusions,
        },
    }


def _log_from_meta(meta, module, lang, message, response_preview="",
                    is_error=False, error_detail=None):
    """Helper: call log_chat_exchange from _chat_meta dict (delegates to shared)."""
    _log_from_meta_shared(meta, module, lang, message, response_preview,
                          is_error=is_error, error_detail=error_detail)


async def handle_chat(message: str, history: list, page: str, http_client, lang: str = "fr") -> dict:
    """Pipeline 12 phases du chatbot HYBRIDE. Retourne dict(response, source, mode)."""
    early, ctx = await _prepare_chat_context(message, history, page, http_client, lang=lang)
    if early:
        _log_from_meta(early.get("_chat_meta"), "loto", lang, message, early.get("response", ""))
        return early
    ctx["_http_client"] = http_client
    return await call_gemini_and_respond(
        ctx, FALLBACK_RESPONSE, "[HYBRIDE CHAT]", "loto", lang, message, page,
        breaker=gemini_breaker,
    )


def _sse_event(data):
    """Format dict as SSE event line (delegates to shared)."""
    return _sse_event_shared(data)


async def handle_chat_stream(message: str, history: list, page: str, http_client, lang: str = "fr"):
    """Async generator — SSE streaming du chatbot HYBRIDE. Yields SSE event strings."""
    early, ctx = await _prepare_chat_context(message, history, page, http_client, lang=lang)
    if early:
        _log_from_meta(early.get("_chat_meta"), "loto", lang, message, early.get("response", ""))
        yield _sse_event({
            "chunk": early["response"],
            "source": early["source"],
            "mode": early["mode"],
            "is_done": True,
        })
        return

    ctx["_http_client"] = http_client
    async for event in stream_and_respond(
        ctx, FALLBACK_RESPONSE, "[HYBRIDE CHAT]", "loto", lang,
        message, page, call_type="chat_loto",
        stream_fn=stream_gemini_chat,
    ):
        yield event


# =========================
# PITCH GRILLES — Gemini
# =========================

async def handle_pitch(grilles: list, http_client, lang: str = "fr") -> dict:
    """Genere des pitchs HYBRIDE personnalises pour chaque grille via Gemini."""
    # Validation Loto
    if not grilles or len(grilles) > 5:
        return {"success": False, "data": None, "error": "Entre 1 et 5 grilles requises", "status_code": 400}
    for i, g in enumerate(grilles):
        if len(g.numeros) != 5:
            return {"success": False, "data": None, "error": f"Grille {i+1}: 5 numéros requis", "status_code": 400}
        if len(set(g.numeros)) != 5:
            return {"success": False, "data": None, "error": f"Grille {i+1}: numéros doivent être uniques", "status_code": 400}
        if not all(1 <= n <= 49 for n in g.numeros):
            return {"success": False, "data": None, "error": f"Grille {i+1}: numéros entre 1 et 49", "status_code": 400}
        if g.chance is not None and not 1 <= g.chance <= 10:
            return {"success": False, "data": None, "error": f"Grille {i+1}: chance entre 1 et 10", "status_code": 400}

    grilles_data = [{"numeros": g.numeros, "chance": g.chance, "score_conformite": g.score_conformite, "severity": g.severity} for g in grilles]
    return await handle_pitch_common(
        grilles_data, http_client, lang,
        context_coro=prepare_grilles_pitch_context(grilles_data),
        load_prompt_fn=load_prompt, prompt_name="PITCH_GRILLE",
        log_prefix="[PITCH]", breaker=gemini_breaker,
    )
