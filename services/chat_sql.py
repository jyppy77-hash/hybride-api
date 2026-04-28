"""
Text-to-SQL — Loto thin wrapper.
Shared validation/cleaning/execution/formatting in base_chat_sql.py.
Loto-specific: prochain tirage, tirage data, SQL generation (prompt Loto, table tirages).

V131.D — Migration AI Studio httpx → google-genai SDK (Vertex AI).
ADC auth, modèle gemini-2.5-flash région europe-west1. Pattern V131.A
identique à enrich_analysis_base / call_gemini_and_respond / handle_pitch_common.
"""

import asyncio
import logging
from datetime import date, timedelta

import aiomysql

from google.genai import errors as genai_errors, types

from services.prompt_loader import load_prompt
from services.circuit_breaker import gemini_breaker_sql, CircuitOpenError
from services.chat_detectors import _JOURS_TIRAGE
from services.base_chat_sql import (
    _JOURS_FR, _clean_gemini_sql, _build_gemini_sql_contents, _guard_non_sql,
)
from services.gemini_shared import (
    _get_client, _is_rate_limit_error,
    _VERTEX_MODEL_NAME, _V131_E_SAFETY_SETTINGS_RELAX,
)
import db_cloudsql

# Re-export shared functions (consumers import from here)
from services.base_chat_sql import (  # noqa: F401
    _validate_sql, _ensure_limit, _execute_safe_sql, _format_sql_result,
    _MAX_SQL_PER_SESSION, _MAX_SQL_INPUT_LENGTH, _SQL_FORBIDDEN,
    _SQL_LIMIT_MESSAGES, ALLOWED_TABLES_LOTO, ALLOWED_TABLES_EM,
)

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────
# Prochain tirage (calcul date + dernier tirage BDD)
# ────────────────────────────────────────────

async def _get_prochain_tirage() -> str | None:
    """
    Calcule la date du prochain tirage a partir de la date du jour
    et des jours de tirage FDJ (lundi, mercredi, samedi).
    Returns: contexte formate ou None si erreur.
    """
    try:
        today = date.today()

        # Chercher le prochain jour de tirage (y compris aujourd'hui)
        for delta in range(7):
            candidate = today + timedelta(days=delta)
            if candidate.weekday() in _JOURS_TIRAGE:
                next_draw = candidate
                break

        jour_fr = _JOURS_FR[next_draw.weekday()]
        date_str = next_draw.strftime("%d/%m/%Y")

        if next_draw == today:
            quand = "ce soir"
        elif next_draw == today + timedelta(days=1):
            quand = "demain soir"
        else:
            quand = f"{jour_fr} prochain"

        # Dernier tirage en BDD
        try:
            async with db_cloudsql.get_connection_readonly() as conn:
                cursor = await conn.cursor()
                await cursor.execute("SELECT MAX(date_de_tirage) as last FROM tirages")
                row = await cursor.fetchone()
                last_draw = str(row['last']) if row and row['last'] else None
        except (aiomysql.Error, asyncio.TimeoutError, ConnectionError, OSError) as e:
            logger.error("[HYBRIDE CHAT] DB error prochain tirage (%s): %s", type(e).__name__, e)
            last_draw = None
        except Exception as e:
            logger.exception("[HYBRIDE CHAT] Unexpected error prochain tirage: %s", e)
            last_draw = None

        lines = [f"[PROCHAIN TIRAGE]"]
        lines.append(f"Date du prochain tirage : {jour_fr} {date_str} ({quand})")
        lines.append(f"Jours de tirage FDJ : lundi, mercredi et samedi")
        if last_draw:
            lines.append(f"Dernier tirage en base : {last_draw}")

        return "\n".join(lines)
    except (aiomysql.Error, asyncio.TimeoutError, ConnectionError, OSError) as e:
        logger.error("[HYBRIDE CHAT] Prochain tirage error (%s): %s", type(e).__name__, e)
        return None
    except Exception as e:
        logger.exception("[HYBRIDE CHAT] Unexpected prochain tirage error: %s", e)
        return None


# ────────────────────────────────────────────
# Recuperation tirage depuis la DB
# ────────────────────────────────────────────

async def _get_tirage_data(target) -> dict | None:
    """
    Recupere un tirage depuis la DB.
    target: "latest" ou un objet date.
    Retourne dict {date, boules, chance} ou None.
    """
    async with db_cloudsql.get_connection_readonly() as conn:
      try:
        cursor = await conn.cursor()
        if target == "latest":
            await cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance
                FROM tirages ORDER BY date_de_tirage DESC LIMIT 1
            """)
        else:
            await cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance
                FROM tirages WHERE date_de_tirage = %s
                LIMIT 1
            """, (target,))

        row = await cursor.fetchone()
        if row:
            return {
                "date": row["date_de_tirage"],
                "boules": [row["boule_1"], row["boule_2"], row["boule_3"],
                           row["boule_4"], row["boule_5"]],
                "chance": row["numero_chance"],
            }
        return None
      except (aiomysql.Error, asyncio.TimeoutError, ConnectionError, OSError) as e:
        logger.error("[HYBRIDE CHAT] _get_tirage_data error (%s): %s", type(e).__name__, e)
        return None
      except Exception as e:
        logger.exception("[HYBRIDE CHAT] Unexpected _get_tirage_data error: %s", e)
        return None


# ────────────────────────────────────────────
# Text-to-SQL : Gemini Vertex genere le SQL, Python l'execute
# ────────────────────────────────────────────

async def _generate_sql(question: str, client, api_key: str, history: list = None) -> str | None:
    """Appelle Gemini Vertex AI pour convertir une question en SQL (avec contexte conversationnel).

    V131.D — Migration AI Studio httpx → google-genai SDK (Vertex AI). ADC auth.
    Les paramètres `client` et `api_key` sont conservés pour rétrocompat
    signature (appelant `chat_pipeline_shared.py:432` via
    `generate_sql_fn(sql_input, http_client, gem_api_key, **kwargs)`)
    mais IGNORÉS côté implémentation.
    """
    _ = client, api_key  # noqa: F841  # V131.D DEPRECATED — paramètres ignorés

    sql_prompt = load_prompt("SQL_GENERATOR")
    if not sql_prompt:
        return None

    today_str = date.today().strftime("%Y-%m-%d")
    sql_prompt = sql_prompt.replace("{TODAY}", today_str)

    sql_contents = _build_gemini_sql_contents(question, history)

    # V131.D — breaker state check avant appel (ex-`gemini_breaker_sql.call`
    # qui wrappait httpx.post). Pattern V131.A enrich_analysis_base.
    if gemini_breaker_sql.state == gemini_breaker_sql.OPEN:
        logger.warning("[TEXT-TO-SQL] Circuit breaker ouvert — fallback")
        return None

    config = types.GenerateContentConfig(
        system_instruction=sql_prompt,
        temperature=0.0,
        max_output_tokens=300,
        # V131.E — safety_settings BLOCK_ONLY_HIGH (réduit faux positifs SAFETY)
        safety_settings=_V131_E_SAFETY_SETTINGS_RELAX,
        # V131.E — thinking_budget=0 désactive le raisonnement interne gemini-2.5-flash
        # (déterministe T=0, pas de raisonnement utile pour génération SQL)
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    try:
        vertex_client = _get_client()
        response = await asyncio.wait_for(
            vertex_client.aio.models.generate_content(
                model=_VERTEX_MODEL_NAME,
                contents=sql_contents,
                config=config,
            ),
            timeout=8.0,
        )
    except CircuitOpenError:
        # Race : state flipped entre check et appel — fallback
        return None
    except asyncio.TimeoutError:
        logger.warning("[TEXT-TO-SQL] Timeout Gemini Vertex (8s) — fallback")
        gemini_breaker_sql._record_failure()
        return None
    except genai_errors.ClientError as e:
        if _is_rate_limit_error(e):
            logger.warning("[TEXT-TO-SQL] Vertex 429 ResourceExhausted — fallback")
        else:
            logger.warning("[TEXT-TO-SQL] Vertex ClientError %s: %s", getattr(e, 'code', '?'), e)
        gemini_breaker_sql._record_failure()
        return None
    except genai_errors.ServerError as e:
        logger.warning("[TEXT-TO-SQL] Vertex ServerError %s: %s", getattr(e, 'code', '?'), e)
        gemini_breaker_sql._record_failure()
        return None
    except genai_errors.APIError as e:
        logger.error("[TEXT-TO-SQL] Vertex APIError SDK: %s: %s", type(e).__name__, e)
        gemini_breaker_sql._record_failure()
        return None
    except Exception as e:
        logger.exception("[TEXT-TO-SQL] Unexpected SQL generation error: %s", e)
        return None

    # Parse réponse SDK B
    try:
        raw = (response.text or "").strip()
    except (ValueError, AttributeError):
        # SAFETY/RECITATION block : .text lève ValueError — pas de _record_success
        logger.warning("[TEXT-TO-SQL] Vertex response blocked (SAFETY/RECITATION)")
        return None

    # V131.A FIX — record_success dès que round-trip OK (indépendant contenu)
    gemini_breaker_sql._record_success()

    text = _clean_gemini_sql(raw)
    return _guard_non_sql(text, "TEXT-TO-SQL")
