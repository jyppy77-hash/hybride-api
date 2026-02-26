"""
Service metier — fonctions SQL EuroMillions.
Requetes DB EM-specifiques + generation SQL via Gemini.
Reutilise les fonctions generiques de chat_sql.py.
"""

import logging
from datetime import date, timedelta

import db_cloudsql
from services.prompt_loader import load_prompt
from services.gemini import GEMINI_MODEL_URL
from services.circuit_breaker import gemini_breaker
from services.chat_utils import _format_date_fr

logger = logging.getLogger(__name__)

# Re-export constantes partagees (pour imports dans chat_pipeline_em)
from services.chat_sql import (  # noqa: F401
    _validate_sql, _ensure_limit, _execute_safe_sql, _format_sql_result,
    _MAX_SQL_PER_SESSION, _SQL_FORBIDDEN,
)

# Jours de tirage EuroMillions : mardi (1), vendredi (4)
_JOURS_TIRAGE_EM = [1, 4]

_JOURS_FR = {
    0: "lundi", 1: "mardi", 2: "mercredi", 3: "jeudi",
    4: "vendredi", 5: "samedi", 6: "dimanche",
}


async def _get_prochain_tirage_em() -> str | None:
    """
    Calcule la date du prochain tirage EuroMillions (mardi, vendredi).
    Returns: contexte formate ou None si erreur.
    """
    try:
        today = date.today()

        next_draw = None
        for delta in range(7):
            candidate = today + timedelta(days=delta)
            if candidate.weekday() in _JOURS_TIRAGE_EM:
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
            async with db_cloudsql.get_connection() as conn:
                cursor = await conn.cursor()
                await cursor.execute("SELECT MAX(date_de_tirage) as last FROM tirages_euromillions")
                row = await cursor.fetchone()
                last_draw = str(row['last']) if row and row['last'] else None
        except Exception:
            last_draw = None

        lines = ["[PROCHAIN TIRAGE]"]
        lines.append(f"Date du prochain tirage : {jour_fr} {date_str} ({quand})")
        lines.append("Jours de tirage EuroMillions : mardi et vendredi")
        if last_draw:
            lines.append(f"Dernier tirage en base : {last_draw}")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[EM CHAT] Erreur calcul prochain tirage: {e}")
        return None


async def _get_tirage_data_em(target) -> dict | None:
    """
    Recupere un tirage EuroMillions depuis la DB.
    target: "latest" ou un objet date.
    Retourne dict {date, boules, etoiles} ou None.
    """
    async with db_cloudsql.get_connection() as conn:
      try:
        cursor = await conn.cursor()
        if target == "latest":
            await cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                       etoile_1, etoile_2
                FROM tirages_euromillions ORDER BY date_de_tirage DESC LIMIT 1
            """)
        else:
            await cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                       etoile_1, etoile_2
                FROM tirages_euromillions WHERE date_de_tirage = %s
                LIMIT 1
            """, (target,))

        row = await cursor.fetchone()
        if row:
            return {
                "date": row["date_de_tirage"],
                "boules": [row["boule_1"], row["boule_2"], row["boule_3"],
                           row["boule_4"], row["boule_5"]],
                "etoiles": [row["etoile_1"], row["etoile_2"]],
            }
        return None
      except Exception as e:
        logger.error(f"[EM CHAT] Erreur _get_tirage_data_em: {e}")
        return None


async def _generate_sql_em(question: str, client, api_key: str, history: list = None) -> str | None:
    """Appelle Gemini pour convertir une question EM en SQL (avec contexte conversationnel)."""
    sql_prompt = load_prompt("SQL_GENERATOR_EM")
    if not sql_prompt:
        return None

    today_str = date.today().strftime("%Y-%m-%d")
    sql_prompt = sql_prompt.replace("{TODAY}", today_str)

    sql_contents = []
    if history:
        for msg in history[-6:]:
            role = "user" if msg.role == "user" else "model"
            if sql_contents and sql_contents[-1]["role"] == role:
                sql_contents[-1]["parts"][0]["text"] += "\n" + msg.content
            else:
                sql_contents.append({"role": role, "parts": [{"text": msg.content}]})
    while sql_contents and sql_contents[0]["role"] == "model":
        sql_contents.pop(0)

    sql_contents.append({"role": "user", "parts": [{"text": question}]})

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
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    if text.endswith("```"):
                        text = text[:-3]
                    text = text.strip()
                if text.upper().startswith("SQL"):
                    text = text[3:].strip()
                    if text.startswith("\n"):
                        text = text[1:]
                return text.strip()
        return None
    except Exception as e:
        logger.warning(f"[EM TEXT-TO-SQL] Erreur generation SQL: {e}")
        return None
