"""
Text-to-SQL — Loto thin wrapper.
Shared validation/cleaning/execution/formatting in base_chat_sql.py.
Loto-specific: prochain tirage, tirage data, SQL generation (prompt Loto, table tirages).
"""

import asyncio
import logging
from datetime import date, timedelta

import aiomysql

from services.prompt_loader import load_prompt
from services.gemini import GEMINI_MODEL_URL
from services.circuit_breaker import gemini_breaker
from services.chat_detectors import _JOURS_TIRAGE
from services.base_chat_sql import (
    _JOURS_FR, _clean_gemini_sql, _build_gemini_sql_contents, _guard_non_sql,
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
    async with db_cloudsql.get_connection() as conn:
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
# Text-to-SQL : Gemini genere le SQL, Python l'execute
# ────────────────────────────────────────────

async def _generate_sql(question: str, client, api_key: str, history: list = None) -> str | None:
    """Appelle Gemini pour convertir une question en SQL (avec contexte conversationnel)."""
    sql_prompt = load_prompt("SQL_GENERATOR")
    if not sql_prompt:
        return None

    today_str = date.today().strftime("%Y-%m-%d")
    sql_prompt = sql_prompt.replace("{TODAY}", today_str)

    sql_contents = _build_gemini_sql_contents(question, history)

    try:
        response = await gemini_breaker.call(
            client,
            GEMINI_MODEL_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json={
                "system_instruction": {"parts": [{"text": sql_prompt}]},
                "contents": sql_contents,
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 300,
                },
            },
            timeout=8.0,
        )

        if response.status_code == 200:
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates:
                raw = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                text = _clean_gemini_sql(raw)
                return _guard_non_sql(text, "TEXT-TO-SQL")
        return None
    except (aiomysql.Error, asyncio.TimeoutError, ConnectionError, OSError) as e:
        logger.error("[TEXT-TO-SQL] SQL generation error (%s): %s", type(e).__name__, e)
        return None
    except Exception as e:
        logger.exception("[TEXT-TO-SQL] Unexpected SQL generation error: %s", e)
        return None
