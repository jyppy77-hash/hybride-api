"""
Shared helpers for Loto and EM chat pipelines — V71 R3a.

Extracts mechanically identical blocks from chat_pipeline.py and chat_pipeline_em.py.
Callables are passed as parameters so that test patches on module-level bindings
in the pipeline files continue to work.

Extracted blocks:
- sse_event: SSE event formatter (was duplicated as _sse_event / _sse_event_em)
- log_from_meta: chat_logger wrapper (was _log_from_meta / _log_from_meta_em)
- build_gemini_contents: history processing loop (insult-stripping, role mapping)
- run_text_to_sql: Phase SQL block (~80 lines)
- call_gemini_and_respond: handle_chat Gemini call + response extraction + fallback
- stream_and_respond: handle_chat_stream SSE streaming loop + fallback
- handle_pitch_common: pitch validation + Gemini call + JSON parsing
- parse_pitch_json: backtick cleaning + JSON parse + sanitize

Shared constants (V72):
- _QUESTION_KEYWORDS_INSULT: Phase I keyword detection (6 langs)
- _QUESTION_KEYWORDS_COMPLIMENT: Phase C keyword detection (6 langs)
- ANTI_REINTRO_BLOCK: anti-re-introduction system prompt block
- _TIRAGE_NOT_FOUND_LOTO / _TIRAGE_NOT_FOUND_EM: tirage introuvable i18n messages
"""

import os
import re
import asyncio
import logging
import time
import importlib
from collections.abc import AsyncGenerator

from datetime import date as _date_cls

from services.base_chat_sql import _SQL_LIMIT_MESSAGES, _MAX_SQL_INPUT_LENGTH
from services.chat_utils import _format_date_fr
from services.base_chat_utils import _format_last_draw_context
from services.stats_analysis import should_inject_pedagogical_context, PEDAGOGICAL_CONTEXT
from services.decay_state import get_decay_state

# F15 V83: Gemini interaction helpers extracted to chat_pipeline_gemini.py
from services.chat_pipeline_gemini import (  # noqa: F401 — re-exported for backward compat
    sse_event, log_from_meta, build_gemini_contents,
    call_gemini_and_respond, stream_and_respond,
    parse_pitch_json, handle_pitch_common,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# Shared constants — V72 F01/F03/F04/F07
# ═══════════════════════════════════════════════════════

# F01 V74: language names for system prompt injection when lang != "fr"
_LANG_NAMES = {
    "en": "anglais",
    "es": "espagnol",
    "pt": "portugais",
    "de": "allemand",
    "nl": "néerlandais",
}

# F03: _has_question keywords — shared across Phase I (Loto+EM)
# Used to detect if an insult/compliment message also contains a real question.
_QUESTION_KEYWORDS_INSULT = (
    # FR
    "numéro", "numero", "tirage", "grille", "fréquence", "frequence",
    "classement", "statistique", "stat", "analyse", "prochain",
    "étoile", "etoile",
    # EN
    "number", "draw", "grid", "frequency", "ranking", "statistic",
    "analysis", "next", "star",
    # ES (F01: was missing in EM)
    "número", "sorteo", "resultado", "cuadrícula", "combinación", "estrella",
    # PT
    "sorteio", "grelha",
    # DE
    "ziehung", "zahlen", "ergebnis", "kombination", "stern",
    # NL
    "trekking", "nummers", "resultaat", "combinatie", "ster",
)

# F03: _has_question_c keywords — shared across Phase C (Loto+EM)
_QUESTION_KEYWORDS_COMPLIMENT = (
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
)

# F04: Anti-re-introduction block — injected into system prompt (both pipelines)
ANTI_REINTRO_BLOCK = (
    "\n\n[RAPPEL CRITIQUE — ANTI-RE-PRÉSENTATION]\n"
    "Le message de bienvenue affiché côté interface a DÉJÀ présenté HYBRIDE à l'utilisateur. "
    "Tu t'es DÉJÀ présenté. NE TE RE-PRÉSENTE PAS. "
    "Ne dis PAS 'Je suis HYBRIDE', 'I'm HYBRIDE', 'Soy HYBRIDE', 'Eu sou HYBRIDE', "
    "'Ich bin HYBRIDE', 'Ik ben HYBRIDE', etc. "
    "Ne dis PAS 'Salut !', 'Hello !', 'Hi !', 'Hola !', 'Olá !', 'Hallo !' en début de réponse "
    "s'il ne t'a pas salué. "
    "Va DIRECTEMENT à la réponse à sa question."
)

# F07: Tirage not found messages — i18n 6 langs
_TIRAGE_NOT_FOUND_LOTO = {
    "fr": (
        "[RÉSULTAT TIRAGE — INTROUVABLE]\n"
        "Aucun tirage trouvé en base de données pour la date du {date}.\n"
        "IMPORTANT : Ne PAS inventer de numéros. Indique simplement que "
        "ce tirage n'est pas disponible dans la base.\n"
        "Les tirages du Loto ont lieu les lundi, mercredi et samedi."
    ),
    "en": (
        "[DRAW RESULT — NOT FOUND]\n"
        "No draw found in the database for the date {date}.\n"
        "IMPORTANT: Do NOT invent numbers. Simply state that "
        "this draw is not available in the database.\n"
        "Loto draws take place on Monday, Wednesday and Saturday."
    ),
    "es": (
        "[RESULTADO SORTEO — NO ENCONTRADO]\n"
        "No se ha encontrado ningún sorteo en la base de datos para la fecha {date}.\n"
        "IMPORTANTE: NO inventes números. Indica simplemente que "
        "este sorteo no está disponible en la base de datos.\n"
        "Los sorteos del Loto tienen lugar los lunes, miércoles y sábados."
    ),
    "pt": (
        "[RESULTADO SORTEIO — NÃO ENCONTRADO]\n"
        "Nenhum sorteio encontrado na base de dados para a data {date}.\n"
        "IMPORTANTE: NÃO inventes números. Indica simplesmente que "
        "este sorteio não está disponível na base de dados.\n"
        "Os sorteios do Loto realizam-se às segundas, quartas e sábados."
    ),
    "de": (
        "[ZIEHUNGSERGEBNIS — NICHT GEFUNDEN]\n"
        "Keine Ziehung in der Datenbank für das Datum {date} gefunden.\n"
        "WICHTIG: Erfinde KEINE Zahlen. Gib einfach an, dass "
        "diese Ziehung nicht in der Datenbank verfügbar ist.\n"
        "Die Loto-Ziehungen finden montags, mittwochs und samstags statt."
    ),
    "nl": (
        "[TREKKINGSRESULTAAT — NIET GEVONDEN]\n"
        "Geen trekking gevonden in de database voor de datum {date}.\n"
        "BELANGRIJK: Verzin GEEN nummers. Geef gewoon aan dat "
        "deze trekking niet beschikbaar is in de database.\n"
        "De Loto-trekkingen vinden plaats op maandag, woensdag en zaterdag."
    ),
}

_TIRAGE_NOT_FOUND_EM = {
    "fr": (
        "[RÉSULTAT TIRAGE — INTROUVABLE]\n"
        "Aucun tirage trouvé en base de données pour la date du {date}.\n"
        "IMPORTANT : Ne PAS inventer de numéros. Indique simplement que "
        "ce tirage n'est pas disponible dans la base.\n"
        "Les tirages EuroMillions ont lieu les mardi et vendredi."
    ),
    "en": (
        "[DRAW RESULT — NOT FOUND]\n"
        "No draw found in the database for the date {date}.\n"
        "IMPORTANT: Do NOT invent numbers. Simply state that "
        "this draw is not available in the database.\n"
        "EuroMillions draws take place on Tuesday and Friday."
    ),
    "es": (
        "[RESULTADO SORTEO — NO ENCONTRADO]\n"
        "No se ha encontrado ningún sorteo en la base de datos para la fecha {date}.\n"
        "IMPORTANTE: NO inventes números. Indica simplemente que "
        "este sorteo no está disponible en la base de datos.\n"
        "Los sorteos de EuroMillions tienen lugar los martes y viernes."
    ),
    "pt": (
        "[RESULTADO SORTEIO — NÃO ENCONTRADO]\n"
        "Nenhum sorteio encontrado na base de dados para a data {date}.\n"
        "IMPORTANTE: NÃO inventes números. Indica simplesmente que "
        "este sorteio não está disponível na base de dados.\n"
        "Os sorteios do EuroMillions realizam-se às terças e sextas."
    ),
    "de": (
        "[ZIEHUNGSERGEBNIS — NICHT GEFUNDEN]\n"
        "Keine Ziehung in der Datenbank für das Datum {date} gefunden.\n"
        "WICHTIG: Erfinde KEINE Zahlen. Gib einfach an, dass "
        "diese Ziehung nicht in der Datenbank verfügbar ist.\n"
        "Die EuroMillions-Ziehungen finden dienstags und freitags statt."
    ),
    "nl": (
        "[TREKKINGSRESULTAAT — NIET GEVONDEN]\n"
        "Geen trekking gevonden in de database voor de datum {date}.\n"
        "BELANGRIJK: Verzin GEEN nummers. Geef gewoon aan dat "
        "deze trekking niet beschikbaar is in de database.\n"
        "De EuroMillions-trekkingen vinden plaats op dinsdag en vrijdag."
    ),
}

# V96: Guard — Phase T found data for ONE date, warn Gemini not to invent others
_TIRAGE_SINGLE_DATE_GUARD = {
    "fr": (
        "\n[AVERTISSEMENT — DONNÉE UNIQUE]\n"
        "Les données ci-dessus concernent UNIQUEMENT le tirage du {date}. "
        "Tu N'AS PAS de données pour d'autres tirages mentionnés dans la question. "
        "Pour tout autre tirage non fourni ci-dessus, réponds que tu n'as pas cette donnée "
        "et propose de chercher une date à la fois. Ne JAMAIS inventer de numéros."
    ),
    "en": (
        "\n[WARNING — SINGLE DATA POINT]\n"
        "The data above covers ONLY the draw on {date}. "
        "You do NOT have data for any other draws mentioned in the question. "
        "For any other draw not provided above, respond that you don't have that data "
        "and offer to look up one date at a time. NEVER invent numbers."
    ),
    "es": (
        "\n[ADVERTENCIA — DATO ÚNICO]\n"
        "Los datos anteriores cubren ÚNICAMENTE el sorteo del {date}. "
        "NO tienes datos de otros sorteos mencionados en la pregunta. "
        "Para cualquier otro sorteo no proporcionado, responde que no tienes ese dato. "
        "NUNCA inventes números."
    ),
    "pt": (
        "\n[AVISO — DADO ÚNICO]\n"
        "Os dados acima cobrem APENAS o sorteio de {date}. "
        "NÃO tens dados de outros sorteios mencionados na pergunta. "
        "Para qualquer outro sorteio não fornecido, responde que não tens esse dado. "
        "NUNCA inventes números."
    ),
    "de": (
        "\n[WARNUNG — EINZELNE DATEN]\n"
        "Die obigen Daten betreffen NUR die Ziehung vom {date}. "
        "Du hast KEINE Daten für andere in der Frage erwähnte Ziehungen. "
        "Für jede andere nicht bereitgestellte Ziehung antworte, dass du diese Daten nicht hast. "
        "NIEMALS Zahlen erfinden."
    ),
    "nl": (
        "\n[WAARSCHUWING — ENKEL GEGEVEN]\n"
        "De bovenstaande gegevens betreffen ALLEEN de trekking van {date}. "
        "Je hebt GEEN gegevens voor andere trekkingen in de vraag. "
        "Voor elke andere niet verstrekte trekking, antwoord dat je die gegevens niet hebt. "
        "NOOIT nummers verzinnen."
    ),
}

# V96: Guard — Phase T detected but exception occurred, no data available
_TIRAGE_ERROR_GUARD = {
    "fr": (
        "[RÉSULTAT TIRAGE — ERREUR]\n"
        "Une erreur s'est produite lors de la recherche du tirage demandé.\n"
        "IMPORTANT : Ne PAS inventer de numéros. Indique simplement qu'une "
        "erreur technique empêche de retrouver ce tirage pour le moment."
    ),
    "en": (
        "[DRAW RESULT — ERROR]\n"
        "An error occurred while looking up the requested draw.\n"
        "IMPORTANT: Do NOT invent numbers. Simply state that a "
        "technical error prevents retrieving this draw at the moment."
    ),
    "es": (
        "[RESULTADO SORTEO — ERROR]\n"
        "Se produjo un error al buscar el sorteo solicitado.\n"
        "IMPORTANTE: NO inventes números. Indica simplemente que un "
        "error técnico impide recuperar este sorteo en este momento."
    ),
    "pt": (
        "[RESULTADO SORTEIO — ERRO]\n"
        "Ocorreu um erro ao procurar o sorteio solicitado.\n"
        "IMPORTANTE: NÃO inventes números. Indica simplesmente que um "
        "erro técnico impede a recuperação deste sorteio neste momento."
    ),
    "de": (
        "[ZIEHUNGSERGEBNIS — FEHLER]\n"
        "Bei der Suche nach der angeforderten Ziehung ist ein Fehler aufgetreten.\n"
        "WICHTIG: Erfinde KEINE Zahlen. Gib einfach an, dass ein "
        "technischer Fehler das Abrufen dieser Ziehung derzeit verhindert."
    ),
    "nl": (
        "[TREKKINGSRESULTAAT — FOUT]\n"
        "Er is een fout opgetreden bij het opzoeken van de gevraagde trekking.\n"
        "BELANGRIJK: Verzin GEEN nummers. Geef gewoon aan dat een "
        "technische fout het ophalen van deze trekking momenteel verhindert."
    ),
}


# ═══════════════════════════════════════════════════════
# F05: Centralized timeout constants (seconds)
# ═══════════════════════════════════════════════════════

MAX_MESSAGE_LENGTH = 2000  # F12 V82: truncate user messages to limit Gemini token usage + regex cost

_TIMEOUTS = {
    "sql_generate": 10,
    "sql_execute": 5,
    "gemini_chat": 15,
    "gemini_stream": 15,
    "pitch_context": 30,
    "pitch_gemini": 15,
    "stats_analysis": 30,
    "enrichment": 20,
}


# ═══════════════════════════════════════════════════════
# F03 V74: shared config base — DRY for _build_loto_config / _build_em_config
# ═══════════════════════════════════════════════════════

def _build_config_base(overrides: dict) -> dict:
    """Build config from game-specific overrides.

    Game-agnostic detectors (24 functions: _detect_insulte, _detect_compliment, etc.)
    are intentionally listed in each pipeline's overrides — NOT in this base dict —
    because existing tests patch them on the pipeline module (e.g.
    ``patch("services.chat_pipeline._detect_insulte")``).  Those patches only work
    when the config dict holds a reference to the pipeline-module binding, not
    to chat_pipeline_shared's copy.

    This function centralises the construction pattern and can hold truly shared
    non-callable defaults in the future.
    """
    return dict(overrides)


# ═══════════════════════════════════════════════════════
# F07 V98: Shared chat/stream handlers (DRY Loto/EM)
# ═══════════════════════════════════════════════════════


async def handle_chat_common(
    message: str, history: list, page: str, http_client, lang: str,
    prepare_context_fn, default_fallback: str, log_prefix: str, module: str,
    breaker, sponsor_kwargs: dict | None = None,
) -> dict:
    """Shared handler for Loto and EM chat — returns dict(response, source, mode).

    F07 V98: factorises handle_chat / handle_chat_em into a single function.
    ``prepare_context_fn`` must accept (message, history, page, http_client, lang=lang).
    Fallback is taken from ctx["fallback"] if present, else *default_fallback*.
    ``breaker`` is the circuit breaker instance (passed from caller for test patching).
    """
    early, ctx = await prepare_context_fn(message, history, page, http_client, lang=lang)
    if early:
        log_from_meta(early.get("_chat_meta"), module, lang, message,
                      early.get("response", ""))
        return early
    ctx["_http_client"] = http_client
    fallback = ctx.get("fallback", default_fallback)
    return await call_gemini_and_respond(
        ctx, fallback, log_prefix, module, lang, message, page,
        sponsor_kwargs=sponsor_kwargs, breaker=breaker,
    )


async def handle_stream_common(
    message: str, history: list, page: str, http_client, lang: str,
    prepare_context_fn, default_fallback: str, log_prefix: str, module: str,
    call_type: str, stream_fn, breaker, sponsor_kwargs: dict | None = None,
) -> AsyncGenerator[str, None]:
    """Shared SSE streaming handler for Loto and EM chat — yields SSE event strings.

    F07 V98: factorises handle_chat_stream / handle_chat_stream_em.
    ``stream_fn`` and ``breaker`` are passed from caller for test patching.
    """
    early, ctx = await prepare_context_fn(message, history, page, http_client, lang=lang)
    if early:
        log_from_meta(early.get("_chat_meta"), module, lang, message,
                      early.get("response", ""))
        yield sse_event({
            "chunk": early["response"], "source": early["source"],
            "mode": early["mode"], "is_done": True,
        })
        return
    ctx["_http_client"] = http_client
    fallback = ctx.get("fallback", default_fallback)
    async for event in stream_and_respond(
        ctx, fallback, log_prefix, module, lang,
        message, page, call_type=call_type,
        sponsor_kwargs=sponsor_kwargs,
        stream_fn=stream_fn,
    ):
        yield event


# ═══════════════════════════════════════════════════════
# Phase SQL — Text-to-SQL block
# ═══════════════════════════════════════════════════════

async def run_text_to_sql(message, http_client, gem_api_key, history,
                          generate_sql_fn, validate_sql_fn, ensure_limit_fn,
                          execute_sql_fn, format_result_fn, max_per_session,
                          log_prefix, force_sql, has_data_signal_fn,
                          continuation_mode, enrichment_context,
                          lang="fr", sql_gen_kwargs=None) -> tuple[str, str | None, str]:
    """
    Phase SQL block. Returns (enrichment_context, sql_query, sql_status).
    sql_gen_kwargs: extra kwargs for generate_sql_fn (e.g. lang for EM).
    """
    _sql_query = None
    _sql_status = "N/A"

    _skip_sql = not force_sql and not has_data_signal_fn(message)
    if _skip_sql:
        logger.info(f'{log_prefix} Skip Phase SQL — no data signal | question="{message[:60]}"')
    if continuation_mode or enrichment_context or _skip_sql:
        return enrichment_context, _sql_query, _sql_status

    # F02 V82: count actual SQL executions (not user messages) for rate-limit
    _sql_count = sum(
        1 for m in (history or [])
        if m.role == "assistant" and "[RÉSULTAT SQL]" in (m.content or "")
    )
    if _sql_count >= max_per_session:
        logger.warning("SQL limit reached: %d/%d for session", _sql_count, max_per_session)
        enrichment_context = _SQL_LIMIT_MESSAGES.get(lang, _SQL_LIMIT_MESSAGES["en"])
        return enrichment_context, _sql_query, "LIMIT"

    t0 = time.monotonic()
    try:
        kwargs = {"history": history}
        if sql_gen_kwargs:
            kwargs.update(sql_gen_kwargs)
        sql_input = message[:_MAX_SQL_INPUT_LENGTH]
        sql = await asyncio.wait_for(
            generate_sql_fn(sql_input, http_client, gem_api_key, **kwargs),
            timeout=_TIMEOUTS["sql_generate"],
        )
        if sql and sql.strip().upper() != "NO_SQL" and validate_sql_fn(sql):
            _sql_query = sql
            sql = ensure_limit_fn(sql)
            rows = await asyncio.wait_for(execute_sql_fn(sql), timeout=_TIMEOUTS["sql_execute"])
            t_total = int((time.monotonic() - t0) * 1000)
            if rows is not None and len(rows) > 0:
                _sql_status = "OK"
                enrichment_context = format_result_fn(rows)
                logger.info(
                    f'{log_prefix} question="{message[:80]}" | '
                    f'sql="{sql[:120]}" | status=OK | '
                    f'rows={len(rows)} | time={t_total}ms'
                )
            elif rows is not None:
                _sql_status = "EMPTY"
                enrichment_context = "[RÉSULTAT SQL]\nAucun résultat trouvé pour cette requête."
                logger.info(
                    f'{log_prefix} question="{message[:80]}" | '
                    f'sql="{sql[:120]}" | status=EMPTY | '
                    f'rows=0 | time={t_total}ms'
                )
            else:
                _sql_status = "ERROR"
                enrichment_context = "[RÉSULTAT SQL]\nAucun résultat trouvé pour cette requête."
                logger.warning(
                    f'{log_prefix} question="{message[:80]}" | '
                    f'sql="{sql[:120]}" | status=EXEC_ERROR | '
                    f'time={t_total}ms'
                )
        elif sql and sql.strip().upper() == "NO_SQL":
            _sql_status = "NO_SQL"
            logger.info(
                f'{log_prefix} question="{message[:80]}" | '
                f'sql=NO_SQL | status=NO_SQL | '
                f'time={int((time.monotonic() - t0) * 1000)}ms'
            )
        elif sql:
            _sql_query = sql
            _sql_status = "REJECTED"
            logger.warning(
                f'{log_prefix} question="{message[:80]}" | '
                f'sql="{sql[:120]}" | status=REJECTED | '
                f'time={int((time.monotonic() - t0) * 1000)}ms'
            )
        else:
            _sql_status = "ERROR"
            logger.warning(
                f'{log_prefix} question="{message[:80]}" | '
                f'status=GEN_ERROR | '
                f'time={int((time.monotonic() - t0) * 1000)}ms'
            )
    except asyncio.TimeoutError:
        _sql_status = "ERROR"
        logger.warning(
            f'{log_prefix} question="{message[:80]}" | '
            f'status=TIMEOUT | '
            f'time={int((time.monotonic() - t0) * 1000)}ms'
        )
    except Exception as e:
        _sql_status = "ERROR"
        logger.warning(
            f'{log_prefix} question="{message[:80]}" | '
            f'status=ERROR | error="{e}" | '
            f'time={int((time.monotonic() - t0) * 1000)}ms'
        )

    return enrichment_context, _sql_query, _sql_status


# ═══════════════════════════════════════════════════════
# Parametric pipeline orchestration — V72 F02
# ═══════════════════════════════════════════════════════

# Pipeline 21 étapes fonctionnelles (18 phases conceptuelles) :
# 1. Phase I (Insulte) — 2. Phase C (Compliment) — 3. Phase R (Rating)
# 4. Phase SALUTATION — 5. Phase G (Génération) — 6. Phase A (Argent)
# 7. Phase GEO (EM only) — 8. Phase 0 (Continuation) — 9. Phase AFFIRMATION
# 10. Phase GAME_KEYWORD — 11. Phase EVAL — 12. Phase 0-bis (Prochain tirage)
# 13. Phase T (Tirage/Temporel) — 14. Phase 2 (Grille soumise)
# 15. Phase 3 (Requête complexe) — 16. Phase 3-bis (Comparaison temporelle)
# 17. Phase P+ (Co-occurrence N>3) — 18. Phase P (Paires/Triplets)
# 19. Phase OOR (Hors limites) — 20. Phase 1 (Numéro unique) — 21. Phase SQL


async def _prepare_chat_context_base(
    message: str, history: list, page: str, http_client, lang: str, cfg: dict,
) -> tuple[dict, dict | None]:
    """
    Orchestration paramétrique des 21 phases chatbot.

    cfg dict keys (all required unless noted):
      Identity: game, log_prefix, debug_prefix
      Prompt: load_system_prompt(lang) -> str|None, draw_count_game
      Fallback: get_fallback(lang) -> str
      Mode: detect_mode(message, page) -> str
      Phase I: get_insult_short(lang), get_menace_response(lang),
               get_insult_response(lang, streak, history)
      Phase C: get_compliment_response(lang, type, streak, history)
      Phase SALUTATION: salutation_game ("loto"|"em")
      Phase G: gen_engine_module (str), forced_secondary_key,
               gen_secondary_param, store_exclusions, format_generation_context(grid)
      Phase A: detect_argent(msg, lang), get_argent_response(msg, lang)
      Phase GEO (optional): detect_country(msg), get_country_context(lang)
      Phase AFFIRMATION: affirmation_invitation (dict), game_keyword_invitation (dict)
      Phase EVAL: eval_game, secondary_field, format_grille_context(data),
                  analyze_grille_for_chat(nums, secondary, **kw), analyze_passes_lang
      Phase 0-bis: detect_prochain_tirage(msg), get_prochain_tirage() async
      Phase T: get_tirage_data(target) async, format_tirage_context(data),
               tirage_not_found (dict)
      Phase 2: detect_grille(msg), (reuses analyze_grille_for_chat + format_grille_context)
      Phase 3: detect_requete_complexe(msg), format_complex_context(intent, data),
               get_classement(type, tri, limit) async, get_comparaison(n1, n2, type) async,
               get_categorie(cat, type) async, get_comparaison_with_period(n1,n2,type,date) async,
               wants_both_fn(msg) (optional, EM only)
      Phase P: detect_triplets(msg), format_triplets_context(data),
               get_triplet_correlations(top_n) async,
               detect_paires(msg), format_pairs_context(data),
               get_pair_correlations(top_n) async,
               get_star_pair_correlations(top_n) async (optional),
               format_star_pairs_context(data) (optional)
      Phase OOR: detect_oor(msg), count_oor_streak(history),
                 get_oor_response(lang, num, type, streak)
      Phase 1: detect_numero(msg), get_numero_stats(num, type) async,
               format_stats_context(stats)
      Phase SQL: generate_sql, sql_log_prefix, sql_gen_kwargs(lang) (optional),
                 validate_sql, ensure_limit, execute_safe_sql, format_sql_result,
                 max_sql_per_session
      Final: build_session_context(history, message)
    """
    _t0 = time.monotonic()
    _lp = cfg["log_prefix"]

    # F12 V82: truncate oversized messages before detection (protects 186 regex + Gemini tokens)
    if len(message) > MAX_MESSAGE_LENGTH:
        logger.warning("%s Message truncated: %d chars → %d", _lp, len(message), MAX_MESSAGE_LENGTH)
        message = message[:MAX_MESSAGE_LENGTH]

    _fallback = cfg["get_fallback"](lang)
    mode = cfg["detect_mode"](message, page)

    # ── Chat Monitor: phase tracking ──
    _phase = "Gemini"
    _sql_query = None
    _sql_status = "N/A"
    _grid_count = 0
    _has_exclusions = False

    system_prompt = cfg["load_system_prompt"](lang)
    if not system_prompt:
        logger.error(f"{_lp} Prompt systeme introuvable")
        return {"response": _fallback, "source": "fallback", "mode": mode}, None

    # F02: inject dynamic draw count
    from services.chat_pipeline import _get_draw_count
    draw_count = await _get_draw_count(cfg["draw_count_game"])
    if draw_count and "{DRAW_COUNT}" in system_prompt:
        system_prompt = system_prompt.replace("{DRAW_COUNT}", str(draw_count))

    # ── F01 V74: Force language when lang != "fr" (Loto prompt is FR-only) ──
    if lang != "fr" and lang in _LANG_NAMES:
        system_prompt += (
            f"\n\n[LANGUE — RÈGLE OBLIGATOIRE]\n"
            f"Tu DOIS répondre UNIQUEMENT en {_LANG_NAMES[lang]}. "
            f"L'utilisateur parle {_LANG_NAMES[lang]}. "
            f"Ne réponds JAMAIS dans une autre langue."
        )

    # ── Anti-re-introduction ──
    system_prompt += ANTI_REINTRO_BLOCK

    # ── Contexte pédagogique ──
    if should_inject_pedagogical_context(message):
        system_prompt += PEDAGOGICAL_CONTEXT

    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        logger.warning(f"{_lp} GEM_API_KEY non configuree — fallback")
        return {"response": _fallback, "source": "fallback", "mode": mode}, None

    contents, history = build_gemini_contents(history, message, cfg["detect_insulte"])

    def _meta(**extra):
        return {"phase": _phase, "t0": _t0, "lang": lang, **extra}

    def _early(response, source, **extra_meta):
        return {"response": response, "source": source, "mode": mode,
                "_chat_meta": _meta(**extra_meta)}, None

    # ── Phase I : Détection d'insultes / agressivité ──
    _insult_prefix = ""
    _insult_type = cfg["detect_insulte"](message)
    if _insult_type:
        _insult_streak = cfg["count_insult_streak"](history)
        _has_question = (
            '?' in message
            or bool(re.search(r'\b\d{1,2}\b', message))
            or any(kw in message.lower() for kw in _QUESTION_KEYWORDS_INSULT)
        )
        if _has_question:
            _insult_prefix = cfg["get_insult_short"](lang)
            logger.info(f"{_lp} Insulte + question (type={_insult_type}, streak={_insult_streak})")
        else:
            _phase = "I"
            if _insult_type == "menace":
                _insult_resp = cfg["get_menace_response"](lang)
            else:
                _insult_resp = cfg["get_insult_response"](lang, _insult_streak, history)
            logger.info(f"{_lp} Insulte detectee (type={_insult_type}, streak={_insult_streak})")
            return _early(_insult_resp, "hybride_insult")

    # ── Phase C : Détection de compliments ──
    if not _insult_prefix:
        _compliment_type = cfg["detect_compliment"](message)
        if _compliment_type:
            _has_question_c = (
                '?' in message
                or bool(re.search(r'\b\d{1,2}\b', message))
                or any(kw in message.lower() for kw in _QUESTION_KEYWORDS_COMPLIMENT)
            )
            if not _has_question_c:
                _phase = "C"
                _comp_streak = cfg["count_compliment_streak"](history)
                _comp_resp = cfg["get_compliment_response"](lang, _compliment_type, _comp_streak, history)
                logger.info(f"{_lp} Compliment detecte (type={_compliment_type}, streak={_comp_streak})")
                return _early(_comp_resp, "hybride_compliment")
            else:
                logger.info(f"{_lp} Compliment + question (type={_compliment_type}), passage au flow normal")

    # ── Phase R : Détection intention de noter le site ──
    if cfg["detect_site_rating"](message):
        _phase = "R"
        logger.info(f"{_lp} Site rating intent detected (lang={lang})")
        return _early(cfg["get_site_rating_response"](lang), "hybride_rating_invite")

    # ── Phase SALUTATION : Salutation initiale sans historique ──
    if not history or len(history) <= 1:
        if cfg["detect_salutation"](message):
            _phase = "SALUTATION"
            _sal_resp = cfg["get_salutation_response"](cfg["salutation_game"], lang)
            logger.info(f"{_lp} Salutation detectee — court-circuit Phase SALUTATION (lang={lang})")
            return _early(_sal_resp, "hybride_salutation")

    # ── Phase G : Détection génération de grille ──
    _generation_context = ""
    if cfg["detect_generation"](message):
        _phase = "G"
        try:
            _gen_mod = importlib.import_module(cfg["gen_engine_module"])
            _gen_fn = _gen_mod.generate_grids
            _gen_mode = cfg["detect_generation_mode"](message)
            _grid_count = cfg["extract_grid_count"](message)
            _forced = cfg["extract_forced_numbers"](message, game=cfg["game"])
            _exclusions = cfg["extract_exclusions"](message)
            _has_exclusions = bool(_exclusions and any(_exclusions.values()))
            if _forced.get("error"):
                _generation_context = f"[ERREUR GÉNÉRATION] {_forced['error']}"
                logger.info(f"{_lp} Phase G — erreur contrainte: {_forced['error']}")
            else:
                # Decay state: load before generation (best-effort)
                _decay = None
                _brake_balls = None
                _brake_secondary = None
                _game_name = "euromillions" if cfg.get("game") == "em" else "loto"
                try:
                    import db_cloudsql as _db
                    async with _db.get_connection() as _dconn:
                        _decay = await get_decay_state(_dconn, _game_name, "ball")
                        # V110: load persistent brake maps READ-ONLY (invariant V94 extended).
                        # Chatbot NEVER writes to hybride_selection_history.
                        try:
                            _gen_mod_for_cfg = importlib.import_module(cfg["gen_engine_module"])
                            _engine_cfg = _gen_mod_for_cfg._engine.cfg
                            if getattr(_engine_cfg, "saturation_persistent_enabled", False):
                                from services.selection_history import get_persistent_brake_map
                                from config.games import get_next_draw_date, ValidGame
                                _game_enum = (ValidGame.euromillions if _game_name == "euromillions"
                                              else ValidGame.loto)
                                _next_date = get_next_draw_date(_game_enum)
                                _sec_type = "star" if _game_name == "euromillions" else "chance"
                                _brake_balls = await get_persistent_brake_map(
                                    _dconn, _game_name, _next_date, "ball", _engine_cfg,
                                )
                                _brake_secondary = await get_persistent_brake_map(
                                    _dconn, _game_name, _next_date, _sec_type, _engine_cfg,
                                )
                        except Exception:
                            logger.debug(f"{_lp} persistent brake load failed — generating without")
                except Exception:
                    logger.warning(f"{_lp} Decay state load failed — generating without decay", exc_info=True)

                _gen_kwargs = {
                    "n": _grid_count, "mode": _gen_mode, "lang": lang,
                    "forced_nums": _forced["forced_nums"] or None,
                    cfg["gen_secondary_param"]: _forced[cfg["forced_secondary_key"]] or None,
                    # DESIGN DECISION: anti_collision=True hardcode pour le chatbot.
                    # Le chatbot optimise l'UX (eviter les numeros superstitieux partages).
                    # L'API laisse le choix a l'utilisateur (default=False, opt-in via query param).
                    # Voir audit 360° Engine HYBRIDE F03 — 01/04/2026.
                    "anti_collision": True,
                    "decay_state": _decay,
                    # V110: persistent brake (read-only, no write from chatbot)
                    "persistent_brake_map": _brake_balls or None,
                    "persistent_brake_map_secondary": _brake_secondary or None,
                }
                if any((_exclusions or {}).values()):
                    _gen_kwargs["exclusions"] = _exclusions
                _gen_result = await asyncio.wait_for(_gen_fn(**_gen_kwargs), timeout=_TIMEOUTS["stats_analysis"])
                if _gen_result and _gen_result.get("grids"):
                    _grids = _gen_result["grids"][:_grid_count]
                    _active_excl = _exclusions if any((_exclusions or {}).values()) else None
                    if len(_grids) == 1:
                        _grids[0]["mode"] = _gen_mode
                        if cfg.get("store_exclusions") and _active_excl:
                            _grids[0]["exclusions"] = _active_excl
                        _generation_context = cfg["format_generation_context"](_grids[0])
                    else:
                        _parts = []
                        for idx, _grid in enumerate(_grids, 1):
                            _grid["mode"] = _gen_mode
                            if cfg.get("store_exclusions") and _active_excl:
                                _grid["exclusions"] = _active_excl
                            _parts.append(f"--- Grille {idx}/{len(_grids)} ---\n" + cfg["format_generation_context"](_grid))
                        _generation_context = "\n\n".join(_parts)
                    _sec_val = _forced[cfg["forced_secondary_key"]]
                    logger.info(
                        f"{_lp} Phase G — {len(_grids)} grille(s) generee(s) mode={_gen_mode} "
                        f"forced={_forced['forced_nums']} {cfg['forced_secondary_key']}={_sec_val}"
                    )
                    # V94 hotfix: decay write removed from chatbot pipeline.
                    # Decay state is now updated ONLY when a new real draw is imported
                    # (via check_and_update_decay or admin route). Chatbot is READ-ONLY.
        except Exception as e:
            logger.warning(f"{_lp} Phase G erreur: {e}")

    # ── Phase A : Détection argent / gains / paris ──
    # F02 V84: skip Phase A if message contains a user grid — Phase EVAL handles it
    _has_grid_eval = cfg["detect_grid_evaluation"](message, game=cfg["eval_game"])
    if cfg["detect_argent"](message, lang) and not _has_grid_eval:
        _phase = "A"
        _argent_resp = cfg["get_argent_response"](message, lang)
        if _insult_prefix:
            _argent_resp = _insult_prefix + "\n\n" + _argent_resp
        logger.info(f"{_lp} Argent detecte — court-circuit Phase A (lang={lang})")
        return _early(_argent_resp, "hybride_argent")

    # ── Phase GEO : Détection pays (EM only) ──
    _country_context = ""
    _detect_country_fn = cfg.get("detect_country")
    if _detect_country_fn and _detect_country_fn(message):
        _phase = "GEO"
        _country_context = cfg["get_country_context"](lang)
        logger.info(f"{_lp} Phase GEO — pays detecte, contexte injecte (lang={lang})")

    # ── Phase 0 : Continuation contextuelle ──
    _continuation_mode = False
    _enriched_message = None
    _sql_reroute_applied = False  # V125 Sous-phase 2 Volet B

    if cfg["is_short_continuation"](message) and history:
        # V125 Sous-phase 2 Volet B: avant d'activer continuation_mode, tester
        # si le dernier message assistant propose une action SQL-évocatrice
        # (cas log #2093 : "Tu veux connaître son historique complet ?").
        # Si oui, reformuler message en requête explicite et laisser le
        # pipeline normal activer Phase SQL via `_sql_reroute_applied → force_sql`.
        _reroute_fn = cfg.get("sql_continuation_reroute")
        _reroute = _reroute_fn(history, lang) if _reroute_fn else None
        if _reroute:
            _old_message = message
            message = _reroute
            _sql_reroute_applied = True
            logger.info(
                f"{_lp} V125 SQL-continuation reroute: \"{_old_message}\" → "
                f"\"{message}\" (lang={lang})"
            )
        else:
            _enriched_message = cfg["enrich_with_context"](message, history)
            if _enriched_message != message:
                _continuation_mode = True
                _phase = "0"
                logger.info(
                    f"{_lp} Reponse courte detectee: \"{message}\" → enrichissement contextuel"
                )

    # ── Phase REFUS : refus simple → court-circuit Python (V98c) ──
    # Conditions : (1) pas déjà en continuation, (2) refus simple, (3) historique ≥ 2
    if not _continuation_mode and cfg["is_refusal"](message) and len(history) >= 2:
        _phase = "REFUS"
        _resp = cfg["get_refusal_response"](lang)
        if _insult_prefix:
            _resp = _insult_prefix + "\n\n" + _resp
        logger.info(f"{_lp} Phase REFUS — refus simple detecte: \"{message}\" (lang={lang})")
        return _early(_resp, "hybride_refusal")

    # ── Phase AFFIRMATION : affirmation simple ──
    if not _continuation_mode and cfg["is_affirmation_simple"](message):
        if history and len(history) >= 2:
            _enriched_message = cfg["enrich_with_context"](message, history)
            if _enriched_message != message:
                _continuation_mode = True
                _phase = "AFFIRMATION"
                logger.info(
                    f"{_lp} Affirmation simple avec contexte: \"{message}\" "
                    f"→ enrichissement contextuel (lang={lang})"
                )
        if not _continuation_mode:
            _phase = "AFFIRMATION_SANS_CONTEXTE"
            _resp = cfg["affirmation_invitation"].get(lang, cfg["affirmation_invitation"]["fr"])
            if _insult_prefix:
                _resp = _insult_prefix + "\n\n" + _resp
            logger.info(f"{_lp} AFFIRMATION_SANS_CONTEXTE \"{message}\" (lang={lang})")
            return _early(_resp, "hybride_affirmation")

    # ── Phase GAME_KEYWORD : mot-clé jeu seul ──
    if not _continuation_mode and cfg["detect_game_keyword_alone"](message):
        _phase = "GAME_KEYWORD"
        _resp = cfg["game_keyword_invitation"].get(lang, cfg["game_keyword_invitation"]["fr"])
        if _insult_prefix:
            _resp = _insult_prefix + "\n\n" + _resp
        logger.info(f"{_lp} GAME_KEYWORD Mot-cle jeu seul: \"{message}\" (lang={lang})")
        return _early(_resp, "hybride_game_keyword")

    enrichment_context = ""

    # ── Phase EVAL : Évaluation grille soumise ──
    if not _generation_context:
        _eval_result = cfg["detect_grid_evaluation"](message, game=cfg["eval_game"])
        if _eval_result:
            _phase = "EVAL"
            try:
                _eval_nums = _eval_result["numeros"]
                _eval_secondary = _eval_result.get(cfg["secondary_field"])
                _analyze_kw = {}
                if cfg.get("analyze_passes_lang"):
                    _analyze_kw["lang"] = lang
                grille_analysis = await asyncio.wait_for(
                    cfg["analyze_grille_for_chat"](_eval_nums, _eval_secondary, **_analyze_kw),
                    timeout=_TIMEOUTS["stats_analysis"],
                )
                if grille_analysis:
                    enrichment_context = cfg["format_grille_context"](grille_analysis)
                    enrichment_context = enrichment_context.replace(
                        "[ANALYSE DE GRILLE",
                        "[ÉVALUATION GRILLE UTILISATEUR",
                    )
                    logger.info(
                        f"{_lp} Phase EVAL — grille utilisateur evaluee: "
                        f"{_eval_nums} {cfg['secondary_field']}={_eval_secondary}"
                    )
            except Exception as e:
                logger.warning(f"{_lp} Phase EVAL erreur: {e}")

    # Phase 0-bis : prochain tirage
    if not _continuation_mode and cfg["detect_prochain_tirage"](message):
        _phase = "0-bis"
        try:
            tirage_ctx = await asyncio.wait_for(cfg["get_prochain_tirage"](), timeout=_TIMEOUTS["stats_analysis"])
            if tirage_ctx:
                enrichment_context = tirage_ctx
                logger.info(f"{_lp} Prochain tirage injecte")
        except Exception as e:
            logger.warning(f"{_lp} Erreur prochain tirage: {e}")

    # Phase T — Tirage spécifique / requête temporelle complexe
    if not _continuation_mode and not enrichment_context:
        tirage_target = cfg["detect_tirage"](message)
        if tirage_target is not None:
            _phase = "T"
            try:
                tirage_data = await asyncio.wait_for(
                    cfg["get_tirage_data"](tirage_target), timeout=_TIMEOUTS["stats_analysis"]
                )
                if tirage_data:
                    enrichment_context = cfg["format_tirage_context"](tirage_data)
                    # V96: Append single-date guard if message may contain other dates
                    _tirage_date_fr = _format_date_fr(str(tirage_data['date']))
                    _guard_tpl = _TIRAGE_SINGLE_DATE_GUARD.get(lang, _TIRAGE_SINGLE_DATE_GUARD["fr"])
                    enrichment_context += _guard_tpl.format(date=_tirage_date_fr)
                    logger.info(f"{_lp} Tirage injecte: {tirage_data['date']}")
                elif tirage_target != "latest":
                    date_fr = _format_date_fr(str(tirage_target))
                    _tpl = cfg["tirage_not_found"].get(lang, cfg["tirage_not_found"]["fr"])
                    enrichment_context = _tpl.format(date=date_fr)
                    logger.info(f"{_lp} Tirage introuvable pour: {tirage_target}")
            except Exception as e:
                logger.warning(f"{_lp} Erreur tirage: {e}")
                # V96: Inject error guard to prevent Gemini from inventing numbers
                if not enrichment_context:
                    enrichment_context = _TIRAGE_ERROR_GUARD.get(lang, _TIRAGE_ERROR_GUARD["fr"])

    # V125 Sous-phase 2 Volet B: reroute SQL-continuation force Phase SQL
    # (contourne Phase 1 qui capturerait le numéro inclus dans la reformulation).
    force_sql = _sql_reroute_applied or (
        not _continuation_mode and not enrichment_context and cfg["has_temporal_filter"](message)
    )
    if force_sql:
        if _sql_reroute_applied:
            logger.info(f"{_lp} V125 SQL-reroute force Phase SQL (bypass Phase 1)")
        else:
            logger.info(f"{_lp} Filtre temporel detecte, force Phase SQL")

    # Phase 2 : detection de grille
    grille_nums, grille_secondary = (None, None) if _continuation_mode else cfg["detect_grille"](message)
    if not force_sql and not enrichment_context and grille_nums is not None:
        _phase = "2"
        try:
            _analyze_kw = {}
            if cfg.get("analyze_passes_lang"):
                _analyze_kw["lang"] = lang
            grille_result = await asyncio.wait_for(
                cfg["analyze_grille_for_chat"](grille_nums, grille_secondary, **_analyze_kw),
                timeout=_TIMEOUTS["stats_analysis"],
            )
            if grille_result:
                enrichment_context = cfg["format_grille_context"](grille_result)
                logger.info(f"{_lp} Grille analysee: {grille_nums} {cfg['secondary_field']}={grille_secondary}")
        except Exception as e:
            logger.warning(f"{_lp} Erreur analyse grille: {e}")

    # Phase 3 : requete complexe
    if not _continuation_mode and not force_sql and not enrichment_context:
        intent = cfg["detect_requete_complexe"](message)
        if intent:
            _phase = "3"
            try:
                data = None
                if intent["type"] == "classement":
                    data = await asyncio.wait_for(
                        cfg["get_classement"](intent["num_type"], intent["tri"], intent["limit"]),
                        timeout=_TIMEOUTS["stats_analysis"],
                    )
                    # EM: if user asks for both boules AND étoiles
                    _wants_both = cfg.get("wants_both_fn")
                    if data and _wants_both and intent["num_type"] == "boule" and _wants_both(message):
                        try:
                            star_data = await asyncio.wait_for(
                                cfg["get_classement"]("etoile", intent["tri"], intent["limit"]),
                                timeout=_TIMEOUTS["stats_analysis"],
                            )
                            if star_data:
                                star_intent = {**intent, "num_type": "etoile"}
                                enrichment_context = (
                                    cfg["format_complex_context"](intent, data)
                                    + "\n\n"
                                    + cfg["format_complex_context"](star_intent, star_data)
                                )
                                logger.info(f"{_lp} Requete complexe: classement boules + étoiles")
                                data = None
                        except Exception:
                            pass
                elif intent["type"] == "comparaison":
                    data = await asyncio.wait_for(
                        cfg["get_comparaison"](intent["num1"], intent["num2"], intent["num_type"]),
                        timeout=_TIMEOUTS["stats_analysis"],
                    )
                elif intent["type"] == "categorie":
                    data = await asyncio.wait_for(
                        cfg["get_categorie"](intent["categorie"], intent["num_type"]),
                        timeout=_TIMEOUTS["stats_analysis"],
                    )

                if data:
                    enrichment_context = cfg["format_complex_context"](intent, data)
                    logger.info(f"{_lp} Requete complexe: {intent['type']}")
            except Exception as e:
                logger.warning(f"{_lp} Erreur requete complexe: {e}")

    # Phase 3-bis : comparaison avec filtre temporel
    if not _continuation_mode and force_sql and not enrichment_context:
        intent = cfg["detect_requete_complexe"](message)
        if intent and intent["type"] == "comparaison":
            _phase = "3-bis"
            try:
                _date_from = cfg["extract_temporal_date"](message)
                data = await asyncio.wait_for(
                    cfg["get_comparaison_with_period"](
                        intent["num1"], intent["num2"], intent["num_type"], _date_from
                    ),
                    timeout=_TIMEOUTS["stats_analysis"],
                )
                if data:
                    enrichment_context = cfg["format_complex_context"](intent, data)
                    force_sql = False
                    logger.info(
                        f"{_lp} Phase 3-bis — comparaison temporelle "
                        f"{intent['num1']} vs {intent['num2']} (date_from={_date_from})"
                    )
            except Exception as e:
                logger.warning(f"{_lp} Erreur comparaison temporelle: {e}")

    # Phase P+ : co-occurrences N>3
    if not _continuation_mode and not enrichment_context:
        if cfg["detect_cooccurrence_high_n"](message):
            _phase = "P+"
            _high_n_resp = cfg["get_cooccurrence_high_n_response"](message, lang=lang)
            if _insult_prefix:
                _high_n_resp = _insult_prefix + "\n\n" + _high_n_resp
            logger.info(f"{_lp} Co-occurrence N>3 — redirection paires/triplets (lang={lang})")
            return _early(_high_n_resp, "hybride_cooccurrence")

    # Phase P : triplets
    if not _continuation_mode and not enrichment_context:
        if cfg["detect_triplets"](message):
            _phase = "P"
            try:
                triplets_data = await asyncio.wait_for(
                    cfg["get_triplet_correlations"](top_n=5), timeout=_TIMEOUTS["stats_analysis"]
                )
                if triplets_data:
                    enrichment_context = cfg["format_triplets_context"](triplets_data)
                    logger.info(f"{_lp} Triplets injectes")
            except Exception as e:
                logger.warning(f"{_lp} Erreur triplets: {e}")

    # Phase P : paires
    if not _continuation_mode and not enrichment_context:
        if cfg["detect_paires"](message):
            _phase = "P"
            try:
                pairs_data = await asyncio.wait_for(
                    cfg["get_pair_correlations"](top_n=5), timeout=_TIMEOUTS["stats_analysis"]
                )
                if pairs_data:
                    enrichment_context = cfg["format_pairs_context"](pairs_data)
                    # EM: star pairs
                    _get_star_pairs = cfg.get("get_star_pair_correlations")
                    if _get_star_pairs:
                        star_data = await asyncio.wait_for(_get_star_pairs(top_n=5), timeout=_TIMEOUTS["stats_analysis"])
                        if star_data:
                            enrichment_context += "\n\n" + cfg["format_star_pairs_context"](star_data)
                    logger.info(f"{_lp} Paires injectees")
            except Exception as e:
                logger.warning(f"{_lp} Erreur paires: {e}")

    # ── Phase OOR : Détection numéro hors range ──
    if not _continuation_mode and not force_sql and not enrichment_context:
        _oor_num, _oor_type = cfg["detect_oor"](message)
        if _oor_num is not None:
            _phase = "OOR"
            _oor_streak = cfg["count_oor_streak"](history)
            _oor_resp = cfg["get_oor_response"](lang, _oor_num, _oor_type, _oor_streak)
            if _insult_prefix:
                _oor_resp = _insult_prefix + "\n\n" + _oor_resp
            logger.info(
                f"{_lp} Numero hors range: {_oor_num} "
                f"(type={_oor_type}, streak={_oor_streak})"
            )
            return _early(_oor_resp, "hybride_oor")

    # Phase 1 : detection de numero simple
    if not _continuation_mode and not force_sql and not enrichment_context:
        numero, type_num = cfg["detect_numero"](message)
        if numero is not None:
            _phase = "1"
            try:
                stats = await asyncio.wait_for(
                    cfg["get_numero_stats"](numero, type_num), timeout=_TIMEOUTS["stats_analysis"]
                )
                if stats:
                    enrichment_context = cfg["format_stats_context"](stats)
                    logger.info(f"{_lp} Stats BDD injectees: numero={numero}, type={type_num}")
                    # V99 F01: enrich with last draw numbers to prevent hallucination
                    _derniere = stats.get("derniere_sortie")
                    if _derniere:
                        _tirage_enriched = False
                        try:
                            _target = (
                                _date_cls.fromisoformat(_derniere)
                                if isinstance(_derniere, str) else _derniere
                            )
                            _tirage = await asyncio.wait_for(
                                cfg["get_tirage_data"](_target),
                                timeout=_TIMEOUTS["stats_analysis"],
                            )
                            if _tirage:
                                enrichment_context += "\n\n" + _format_last_draw_context(_tirage)
                                _tirage_enriched = True
                                logger.info(f"{_lp} Phase 1 enriched with last draw: {_target}")
                        except Exception as e:
                            logger.warning(f"{_lp} Phase 1 last draw enrichment error: {e}")
                        # V99 F04: guard when tirage numbers unavailable
                        if not _tirage_enriched:
                            _date_fr = _format_date_fr(str(_derniere))
                            enrichment_context += (
                                f"\n\n[AVERTISSEMENT : les numéros du tirage du {_date_fr} "
                                f"ne sont pas disponibles. NE PAS inventer de numéros.]"
                            )
            except Exception as e:
                logger.warning(f"{_lp} Erreur stats BDD (numero={numero}): {e}")

    # Phase SQL : Text-to-SQL fallback
    _sql_gen_kwargs_fn = cfg.get("sql_gen_kwargs")
    _sql_kw = {}
    if _sql_gen_kwargs_fn:
        _sql_kw["sql_gen_kwargs"] = _sql_gen_kwargs_fn(lang)
    enrichment_context, _sql_query, _sql_status = await run_text_to_sql(
        message, http_client, gem_api_key, history,
        generate_sql_fn=cfg["generate_sql"], validate_sql_fn=cfg["validate_sql"],
        ensure_limit_fn=cfg["ensure_limit"], execute_sql_fn=cfg["execute_safe_sql"],
        format_result_fn=cfg["format_sql_result"], max_per_session=cfg["max_sql_per_session"],
        log_prefix=cfg["sql_log_prefix"], force_sql=force_sql,
        has_data_signal_fn=cfg["has_data_signal"],
        continuation_mode=_continuation_mode, enrichment_context=enrichment_context,
        lang=lang, **_sql_kw,
    )
    if _sql_query or _sql_status != "N/A":
        _phase = "SQL"

    if force_sql and not enrichment_context:
        logger.warning(
            f"{_lp} Phase SQL echouee avec filtre temporel, "
            f"PAS de fallback Phase 3 (evite stats all-time incorrectes) | "
            f'question="{message[:80]}"'
        )

    # ── Combine generation context + stats context ──
    if _generation_context and enrichment_context:
        enrichment_context = f"{enrichment_context}\n\n{_generation_context}"
        logger.info(f"{_lp} Multi-action: stats + generation combines")
    elif _generation_context:
        enrichment_context = _generation_context

    logger.info(
        f"{cfg['debug_prefix']} force_sql={force_sql} | continuation={_continuation_mode} | "
        f"enrichment={bool(enrichment_context)} | generation={bool(_generation_context)} | "
        f"question=\"{message[:60]}\" | history_len={len(history or [])}"
    )

    _session_ctx = cfg["build_session_context"](history, message)

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
            "enrichment_context": enrichment_context,
        },
    }
