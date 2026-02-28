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
    get_classement_numeros, get_comparaison_numeros, get_numeros_par_categorie,
    prepare_grilles_pitch_context,
)

from services.chat_detectors import (
    _detect_mode, _is_short_continuation, _detect_prochain_tirage,
    _detect_tirage, _has_temporal_filter, _detect_numero, _detect_grille,
    _detect_requete_complexe, _detect_insulte,
    _count_insult_streak, _get_insult_response, _get_insult_short,
    _get_menace_response, _detect_compliment, _count_compliment_streak,
    _get_compliment_response, _detect_out_of_range, _count_oor_streak,
    _get_oor_response,
)
from services.chat_sql import (
    _get_prochain_tirage, _get_tirage_data, _generate_sql, _validate_sql,
    _ensure_limit, _execute_safe_sql, _format_sql_result, _MAX_SQL_PER_SESSION,
)
from services.chat_utils import (
    FALLBACK_RESPONSE, _enrich_with_context, _clean_response, _strip_non_latin,
    _strip_sponsor_from_text, _get_sponsor_if_due, _format_date_fr,
    _format_tirage_context, _format_stats_context, _format_grille_context,
    _format_complex_context, _build_session_context,
)

logger = logging.getLogger(__name__)


# =========================
# HYBRIDE Chatbot — Pipeline 12 phases
# =========================

async def _prepare_chat_context(message: str, history: list, page: str, http_client):
    """
    Phases I-SQL : prepare le contexte pour l'appel Gemini.
    Retourne (early_return_or_None, ctx_dict_or_None).
    Si early_return n'est pas None, c'est une reponse complete (insult/compliment/OOR).
    Sinon, ctx_dict contient les cles pour l'appel Gemini.
    """
    mode = _detect_mode(message, page)

    system_prompt = load_prompt("CHATBOT")
    if not system_prompt:
        logger.error("[HYBRIDE CHAT] Prompt systeme introuvable")
        return {"response": FALLBACK_RESPONSE, "source": "fallback", "mode": mode}, None

    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        logger.warning("[HYBRIDE CHAT] GEM_API_KEY non configuree — fallback")
        return {"response": FALLBACK_RESPONSE, "source": "fallback", "mode": mode}, None

    contents = []

    history = (history or [])[-20:]
    if history and history[-1].role == "user" and history[-1].content == message:
        history = history[:-1]

    _skip_insult_response = False
    for msg in history:
        if msg.role == "user" and _detect_insulte(msg.content):
            _skip_insult_response = True
            continue
        if msg.role == "assistant" and _skip_insult_response:
            _skip_insult_response = False
            continue
        _skip_insult_response = False

        role = "user" if msg.role == "user" else "model"
        content = _strip_sponsor_from_text(msg.content) if role == "model" else msg.content
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n" + content
        else:
            contents.append({"role": role, "parts": [{"text": content}]})

    while contents and contents[0]["role"] == "model":
        contents.pop(0)

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
            ))
        )
        if _has_question:
            _insult_prefix = _get_insult_short()
            logger.info(
                f"[HYBRIDE CHAT] Insulte + question (type={_insult_type}, streak={_insult_streak})"
            )
        else:
            if _insult_type == "menace":
                _insult_resp = _get_menace_response()
            else:
                _insult_resp = _get_insult_response(_insult_streak, history)
            logger.info(
                f"[HYBRIDE CHAT] Insulte detectee (type={_insult_type}, streak={_insult_streak})"
            )
            return {"response": _insult_resp, "source": "hybride_insult", "mode": mode}, None

    # ── Phase C : Détection de compliments ──
    if not _insult_prefix:
        _compliment_type = _detect_compliment(message)
        if _compliment_type:
            _has_question_c = (
                '?' in message
                or bool(re.search(r'\b\d{1,2}\b', message))
                or any(kw in message.lower() for kw in (
                    "numéro", "numero", "tirage", "grille", "fréquence", "frequence",
                    "combien", "c'est quoi", "quel", "quelle", "comment", "pourquoi",
                    "classement", "statistique", "stat", "analyse",
                ))
            )
            if not _has_question_c:
                _comp_streak = _count_compliment_streak(history)
                _comp_resp = _get_compliment_response(_compliment_type, _comp_streak, history)
                logger.info(
                    f"[HYBRIDE CHAT] Compliment detecte (type={_compliment_type}, streak={_comp_streak})"
                )
                return {"response": _comp_resp, "source": "hybride_compliment", "mode": mode}, None
            else:
                logger.info(
                    f"[HYBRIDE CHAT] Compliment + question (type={_compliment_type}), passage au flow normal"
                )

    # ── Phase 0 : Continuation contextuelle ──
    _continuation_mode = False
    _enriched_message = None

    if _is_short_continuation(message) and history:
        _enriched_message = _enrich_with_context(message, history)
        if _enriched_message != message:
            _continuation_mode = True
            logger.info(
                f"[CONTINUATION] Reponse courte detectee: \"{message}\" "
                f"→ enrichissement contextuel"
            )

    enrichment_context = ""

    # Phase 0-bis : prochain tirage
    if not _continuation_mode and _detect_prochain_tirage(message):
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
    grille_nums, grille_chance = (None, None) if _continuation_mode else _detect_grille(message)
    if not force_sql and grille_nums is not None:
        try:
            grille_result = await asyncio.wait_for(analyze_grille_for_chat(grille_nums, grille_chance), timeout=30.0)
            if grille_result:
                enrichment_context = _format_grille_context(grille_result)
                logger.info(f"[HYBRIDE CHAT] Grille analysee: {grille_nums} chance={grille_chance}")
        except Exception as e:
            logger.warning(f"[HYBRIDE CHAT] Erreur analyse grille: {e}")

    # Phase 3 : requete complexe
    if not _continuation_mode and not force_sql and not enrichment_context:
        intent = _detect_requete_complexe(message)
        if intent:
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

    # ── Phase OOR : Détection numéro hors range ──
    if not _continuation_mode and not force_sql and not enrichment_context:
        _oor_num, _oor_type = _detect_out_of_range(message)
        if _oor_num is not None:
            _oor_streak = _count_oor_streak(history)
            _oor_resp = _get_oor_response(_oor_num, _oor_type, _oor_streak)
            if _insult_prefix:
                _oor_resp = _insult_prefix + "\n\n" + _oor_resp
            logger.info(
                f"[HYBRIDE CHAT] Numero hors range: {_oor_num} "
                f"(type={_oor_type}, streak={_oor_streak})"
            )
            return {"response": _oor_resp, "source": "hybride_oor", "mode": mode}, None

    # Phase 1 : detection de numero simple
    if not _continuation_mode and not force_sql and not enrichment_context:
        numero, type_num = _detect_numero(message)
        if numero is not None:
            try:
                stats = await asyncio.wait_for(get_numero_stats(numero, type_num), timeout=30.0)
                if stats:
                    enrichment_context = _format_stats_context(stats)
                    logger.info(f"[HYBRIDE CHAT] Stats BDD injectees: numero={numero}, type={type_num}")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Erreur stats BDD (numero={numero}): {e}")

    # Phase SQL : Text-to-SQL fallback
    if not _continuation_mode and not enrichment_context:
        _sql_count = sum(1 for m in (history or []) if m.role == "user")
        if _sql_count >= _MAX_SQL_PER_SESSION:
            logger.info(f"[TEXT2SQL] Rate-limit session ({_sql_count} echanges)")
        else:
            t0 = time.monotonic()
            try:
                sql = await asyncio.wait_for(
                    _generate_sql(message, http_client, gem_api_key, history=history),
                    timeout=10.0,
                )
                if sql and sql.strip().upper() != "NO_SQL" and _validate_sql(sql):
                    sql = _ensure_limit(sql)
                    rows = await asyncio.wait_for(
                        _execute_safe_sql(sql), timeout=5.0
                    )
                    t_total = int((time.monotonic() - t0) * 1000)
                    if rows is not None and len(rows) > 0:
                        enrichment_context = _format_sql_result(rows)
                        logger.info(
                            f'[TEXT2SQL] question="{message[:80]}" | '
                            f'sql="{sql[:120]}" | status=OK | '
                            f'rows={len(rows)} | time={t_total}ms'
                        )
                    elif rows is not None:
                        enrichment_context = "[RÉSULTAT SQL]\nAucun résultat trouvé pour cette requête."
                        logger.info(
                            f'[TEXT2SQL] question="{message[:80]}" | '
                            f'sql="{sql[:120]}" | status=EMPTY | '
                            f'rows=0 | time={t_total}ms'
                        )
                    else:
                        enrichment_context = "[RÉSULTAT SQL]\nAucun résultat trouvé pour cette requête."
                        logger.warning(
                            f'[TEXT2SQL] question="{message[:80]}" | '
                            f'sql="{sql[:120]}" | status=EXEC_ERROR | '
                            f'time={t_total}ms'
                        )
                elif sql and sql.strip().upper() == "NO_SQL":
                    logger.info(
                        f'[TEXT2SQL] question="{message[:80]}" | '
                        f'sql=NO_SQL | status=NO_SQL | '
                        f'time={int((time.monotonic() - t0) * 1000)}ms'
                    )
                elif sql:
                    logger.warning(
                        f'[TEXT2SQL] question="{message[:80]}" | '
                        f'sql="{sql[:120]}" | status=REJECTED | '
                        f'time={int((time.monotonic() - t0) * 1000)}ms'
                    )
                else:
                    logger.warning(
                        f'[TEXT2SQL] question="{message[:80]}" | '
                        f'status=GEN_ERROR | '
                        f'time={int((time.monotonic() - t0) * 1000)}ms'
                    )
            except asyncio.TimeoutError:
                logger.warning(
                    f'[TEXT2SQL] question="{message[:80]}" | '
                    f'status=TIMEOUT | '
                    f'time={int((time.monotonic() - t0) * 1000)}ms'
                )
            except Exception as e:
                logger.warning(
                    f'[TEXT2SQL] question="{message[:80]}" | '
                    f'status=ERROR | error="{e}" | '
                    f'time={int((time.monotonic() - t0) * 1000)}ms'
                )

    # Fallback regex quand Phase SQL echoue avec filtre temporel
    if force_sql and not enrichment_context:
        logger.info("[HYBRIDE CHAT] Phase SQL echouee, fallback phases regex (donnees globales)")
        intent = _detect_requete_complexe(message)
        if intent:
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
                    logger.info(f"[HYBRIDE CHAT] Fallback Phase 3: {intent['type']}")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Fallback Phase 3 erreur: {e}")
        if not enrichment_context:
            numero, type_num = _detect_numero(message)
            if numero is not None:
                try:
                    stats = await asyncio.wait_for(get_numero_stats(numero, type_num), timeout=30.0)
                    if stats:
                        enrichment_context = _format_stats_context(stats)
                        logger.info(f"[HYBRIDE CHAT] Fallback Phase 1: numero={numero}")
                except Exception as e:
                    logger.warning(f"[HYBRIDE CHAT] Fallback Phase 1 erreur: {e}")

    logger.info(
        f"[DEBUG] force_sql={force_sql} | continuation={_continuation_mode} | "
        f"enrichment={bool(enrichment_context)} | "
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
    }


async def handle_chat(message: str, history: list, page: str, http_client) -> dict:
    """
    Pipeline 12 phases du chatbot HYBRIDE.
    Retourne dict(response=str, source=str, mode=str).
    """
    early, ctx = await _prepare_chat_context(message, history, page, http_client)
    if early:
        return early

    mode = ctx["mode"]

    try:
        response = await gemini_breaker.call(
            http_client,
            GEMINI_MODEL_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": ctx["gem_api_key"],
            },
            json={
                "system_instruction": {
                    "parts": [{"text": ctx["system_prompt"]}]
                },
                "contents": ctx["contents"],
                "generationConfig": {
                    "temperature": 0.8,
                    "maxOutputTokens": 300,
                },
            },
            timeout=15.0,
        )

        if response.status_code == 200:
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    text = parts[0].get("text", "").strip()
                    if text:
                        text = _clean_response(text)
                        if ctx["insult_prefix"]:
                            text = ctx["insult_prefix"] + "\n\n" + text
                        sponsor_line = _get_sponsor_if_due(ctx["history"])
                        if sponsor_line:
                            text += "\n\n" + sponsor_line
                        logger.info(
                            f"[HYBRIDE CHAT] OK (page={page}, mode={mode})"
                        )
                        return {"response": text, "source": "gemini", "mode": mode}

        logger.warning(
            f"[HYBRIDE CHAT] Reponse Gemini invalide: {response.status_code}"
        )
        return {"response": FALLBACK_RESPONSE, "source": "fallback", "mode": mode}

    except CircuitOpenError:
        logger.warning("[HYBRIDE CHAT] Circuit breaker ouvert — fallback")
        return {"response": FALLBACK_RESPONSE, "source": "fallback_circuit", "mode": mode}
    except httpx.TimeoutException:
        logger.warning("[HYBRIDE CHAT] Timeout Gemini (15s) — fallback")
        return {"response": FALLBACK_RESPONSE, "source": "fallback", "mode": mode}
    except Exception as e:
        logger.error(f"[HYBRIDE CHAT] Erreur Gemini: {e}")
        return {"response": FALLBACK_RESPONSE, "source": "fallback", "mode": mode}


def _sse_event(data):
    """Format dict as SSE event line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def handle_chat_stream(message: str, history: list, page: str, http_client):
    """
    Async generator — SSE streaming du chatbot HYBRIDE.
    Yields SSE event strings: data: {...}\n\n
    """
    early, ctx = await _prepare_chat_context(message, history, page, http_client)
    if early:
        yield _sse_event({
            "chunk": early["response"],
            "source": early["source"],
            "mode": early["mode"],
            "is_done": True,
        })
        return

    mode = ctx["mode"]

    try:
        if ctx["insult_prefix"]:
            yield _sse_event({
                "chunk": ctx["insult_prefix"] + "\n\n",
                "source": "gemini", "mode": mode, "is_done": False,
            })

        has_chunks = False
        async for chunk in stream_gemini_chat(
            http_client, ctx["gem_api_key"], ctx["system_prompt"],
            ctx["contents"], timeout=15.0,
        ):
            has_chunks = True
            yield _sse_event({
                "chunk": chunk, "source": "gemini", "mode": mode, "is_done": False,
            })

        if not has_chunks:
            yield _sse_event({
                "chunk": FALLBACK_RESPONSE,
                "source": "fallback", "mode": mode, "is_done": True,
            })
            return

        sponsor_line = _get_sponsor_if_due(ctx["history"])
        if sponsor_line:
            yield _sse_event({
                "chunk": "\n\n" + sponsor_line,
                "source": "gemini", "mode": mode, "is_done": False,
            })

        yield _sse_event({
            "chunk": "", "source": "gemini", "mode": mode, "is_done": True,
        })
        logger.info(f"[HYBRIDE CHAT] Stream OK (page={page}, mode={mode})")

    except CircuitOpenError:
        logger.warning("[HYBRIDE CHAT] Circuit breaker ouvert — fallback")
        yield _sse_event({
            "chunk": FALLBACK_RESPONSE,
            "source": "fallback_circuit", "mode": mode, "is_done": True,
        })
    except httpx.TimeoutException:
        logger.warning("[HYBRIDE CHAT] Timeout Gemini (15s) — fallback")
        yield _sse_event({
            "chunk": FALLBACK_RESPONSE,
            "source": "fallback", "mode": mode, "is_done": True,
        })
    except Exception as e:
        logger.error(f"[HYBRIDE CHAT] Erreur streaming: {e}")
        yield _sse_event({
            "chunk": FALLBACK_RESPONSE,
            "source": "fallback", "mode": mode, "is_done": True,
        })


# =========================
# PITCH GRILLES — Gemini
# =========================

async def handle_pitch(grilles: list, http_client) -> dict:
    """
    Genere des pitchs HYBRIDE personnalises pour chaque grille via Gemini.
    Retourne dict(success, data, error, status_code).
    """
    # Validation
    if not grilles or len(grilles) > 5:
        return {
            "success": False, "data": None,
            "error": "Entre 1 et 5 grilles requises",
            "status_code": 400,
        }

    for i, g in enumerate(grilles):
        if len(g.numeros) != 5:
            return {
                "success": False, "data": None,
                "error": f"Grille {i+1}: 5 numéros requis",
                "status_code": 400,
            }
        if len(set(g.numeros)) != 5:
            return {
                "success": False, "data": None,
                "error": f"Grille {i+1}: numéros doivent être uniques",
                "status_code": 400,
            }
        if not all(1 <= n <= 49 for n in g.numeros):
            return {
                "success": False, "data": None,
                "error": f"Grille {i+1}: numéros entre 1 et 49",
                "status_code": 400,
            }
        if g.chance is not None and not 1 <= g.chance <= 10:
            return {
                "success": False, "data": None,
                "error": f"Grille {i+1}: chance entre 1 et 10",
                "status_code": 400,
            }

    # Preparer le contexte stats
    grilles_data = [{"numeros": g.numeros, "chance": g.chance, "score_conformite": g.score_conformite, "severity": g.severity} for g in grilles]

    try:
        context = await asyncio.wait_for(prepare_grilles_pitch_context(grilles_data), timeout=30.0)
    except asyncio.TimeoutError:
        logger.error("[PITCH] Timeout 30s contexte stats")
        return {
            "success": False, "data": None,
            "error": "Service temporairement indisponible",
            "status_code": 503,
        }
    except Exception as e:
        logger.warning(f"[PITCH] Erreur contexte stats: {e}")
        return {
            "success": False, "data": None,
            "error": "Erreur données statistiques",
            "status_code": 500,
        }

    if not context:
        return {
            "success": False, "data": None,
            "error": "Impossible de préparer le contexte",
            "status_code": 500,
        }

    # Charger le prompt
    system_prompt = load_prompt("PITCH_GRILLE")
    if not system_prompt:
        logger.error("[PITCH] Prompt pitch introuvable")
        return {
            "success": False, "data": None,
            "error": "Prompt pitch introuvable",
            "status_code": 500,
        }

    # Cle API
    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        return {
            "success": False, "data": None,
            "error": "API Gemini non configurée",
            "status_code": 500,
        }

    # Appel Gemini (1 seul appel pour toutes les grilles)
    try:
        response = await gemini_breaker.call(
            http_client,
            GEMINI_MODEL_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": gem_api_key,
            },
            json={
                "system_instruction": {
                    "parts": [{"text": system_prompt}]
                },
                "contents": [{
                    "role": "user",
                    "parts": [{"text": context}]
                }],
                "generationConfig": {
                    "temperature": 0.9,
                    "maxOutputTokens": 600,
                },
            },
            timeout=15.0,
        )

        if response.status_code != 200:
            logger.warning(f"[PITCH] Gemini HTTP {response.status_code}")
            return {
                "success": False, "data": None,
                "error": f"Gemini erreur HTTP {response.status_code}",
                "status_code": 502,
            }

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return {
                "success": False, "data": None,
                "error": "Gemini: aucune réponse",
                "status_code": 502,
            }

        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        if not text:
            return {
                "success": False, "data": None,
                "error": "Gemini: réponse vide",
                "status_code": 502,
            }

        # Parser le JSON (nettoyer si Gemini ajoute des backticks)
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()

        try:
            result = json.loads(clean)
            pitchs = result.get("pitchs", [])
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f"[PITCH] JSON invalide: {text[:200]}")
            return {
                "success": False, "data": None,
                "error": "Gemini: JSON mal formé",
                "status_code": 502,
            }

        # Sanitize : supprimer les caractères CJK/non-latin injectés par Gemini
        pitchs = [_strip_non_latin(p) if isinstance(p, str) else p for p in pitchs]

        logger.info(f"[PITCH] OK \u2014 {len(pitchs)} pitchs générés")
        return {
            "success": True, "data": {"pitchs": pitchs}, "error": None,
            "status_code": 200,
        }

    except CircuitOpenError:
        logger.warning("[PITCH] Circuit breaker ouvert — fallback")
        return {
            "success": False, "data": None,
            "error": "Service Gemini temporairement indisponible",
            "status_code": 503,
        }
    except httpx.TimeoutException:
        logger.warning("[PITCH] Timeout Gemini (15s)")
        return {
            "success": False, "data": None,
            "error": "Timeout Gemini",
            "status_code": 503,
        }
    except Exception as e:
        logger.error(f"[PITCH] Erreur: {e}")
        return {
            "success": False, "data": None,
            "error": "Erreur interne du serveur",
            "status_code": 500,
        }
