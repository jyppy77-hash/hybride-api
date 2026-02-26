import os
import re
import logging
from datetime import date, timedelta

from services.prompt_loader import load_prompt
from services.gemini import GEMINI_MODEL_URL
from services.circuit_breaker import gemini_breaker
from services.chat_detectors import _JOURS_TIRAGE, _JOURS_FR
from services.chat_utils import _format_date_fr
import db_cloudsql

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────
# Prochain tirage (calcul date + dernier tirage BDD)
# ────────────────────────────────────────────

def _get_prochain_tirage() -> str | None:
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
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(date_de_tirage) as last FROM tirages")
                row = cursor.fetchone()
                last_draw = str(row['last']) if row and row['last'] else None
            finally:
                conn.close()
        except Exception:
            last_draw = None

        lines = [f"[PROCHAIN TIRAGE]"]
        lines.append(f"Date du prochain tirage : {jour_fr} {date_str} ({quand})")
        lines.append(f"Jours de tirage FDJ : lundi, mercredi et samedi")
        if last_draw:
            lines.append(f"Dernier tirage en base : {last_draw}")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[HYBRIDE CHAT] Erreur calcul prochain tirage: {e}")
        return None


# ────────────────────────────────────────────
# Recuperation tirage depuis la DB
# ────────────────────────────────────────────

def _get_tirage_data(target) -> dict | None:
    """
    Recupere un tirage depuis la DB.
    target: "latest" ou un objet date.
    Retourne dict {date, boules, chance} ou None.
    """
    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()
        if target == "latest":
            cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance
                FROM tirages ORDER BY date_de_tirage DESC LIMIT 1
            """)
        else:
            cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance
                FROM tirages WHERE date_de_tirage = %s
                LIMIT 1
            """, (target,))

        row = cursor.fetchone()
        if row:
            return {
                "date": row["date_de_tirage"],
                "boules": [row["boule_1"], row["boule_2"], row["boule_3"],
                           row["boule_4"], row["boule_5"]],
                "chance": row["numero_chance"],
            }
        return None
    except Exception as e:
        logger.error(f"[HYBRIDE CHAT] Erreur _get_tirage_data: {e}")
        return None
    finally:
        conn.close()


# ────────────────────────────────────────────
# Text-to-SQL : Gemini genere le SQL, Python l'execute
# ────────────────────────────────────────────

_MAX_SQL_PER_SESSION = 10

_SQL_FORBIDDEN = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "REPLACE INTO", "GRANT", "REVOKE", "EXEC ", "EXECUTE", "CALL ",
    "SLEEP", "BENCHMARK", "LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE",
    "INFORMATION_SCHEMA", "MYSQL.", "PERFORMANCE_SCHEMA", "SYS.",
]


async def _generate_sql(question: str, client, api_key: str, history: list = None) -> str | None:
    """Appelle Gemini pour convertir une question en SQL (avec contexte conversationnel)."""
    sql_prompt = load_prompt("SQL_GENERATOR")
    if not sql_prompt:
        return None

    today_str = date.today().strftime("%Y-%m-%d")
    sql_prompt = sql_prompt.replace("{TODAY}", today_str)

    # Construire les contents avec historique pour resolution de contexte
    sql_contents = []
    if history:
        for msg in history[-6:]:
            role = "user" if msg.role == "user" else "model"
            # Fusionner les messages consecutifs de meme role (requis par Gemini)
            if sql_contents and sql_contents[-1]["role"] == role:
                sql_contents[-1]["parts"][0]["text"] += "\n" + msg.content
            else:
                sql_contents.append({"role": role, "parts": [{"text": msg.content}]})
    # Gemini exige que contents commence par "user"
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
                # Nettoyer les backticks eventuels
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
        logger.warning(f"[TEXT-TO-SQL] Erreur generation SQL: {e}")
        return None


def _validate_sql(sql: str) -> bool:
    """Valide la securite du SQL genere (SELECT only, pas de mots interdits)."""
    if not sql:
        return False
    if len(sql) > 1000:
        return False
    upper = sql.strip().upper()
    if not upper.startswith("SELECT"):
        return False
    if ";" in sql:
        return False
    if "--" in sql or "/*" in sql:
        return False
    for kw in _SQL_FORBIDDEN:
        if kw in upper:
            return False
    return True


def _ensure_limit(sql: str, max_limit: int = 50) -> str:
    """Ajoute LIMIT si absent, plafonne a max_limit si present."""
    upper = sql.strip().upper()
    if "LIMIT" not in upper:
        return sql.rstrip() + f" LIMIT {max_limit}"
    return sql


def _execute_safe_sql(sql: str) -> list | None:
    """Execute le SQL valide avec connexion DB."""
    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return rows
    except Exception as e:
        logger.warning(f"[TEXT-TO-SQL] Erreur execution SQL: {e}")
        return None
    finally:
        conn.close()


def _format_sql_result(rows: list) -> str:
    """Formate les resultats SQL en bloc de contexte pour Gemini."""
    if not rows:
        return "[RÉSULTAT SQL]\nAucun résultat trouvé pour cette requête."

    lines = ["[RÉSULTAT SQL]"]

    for row in rows[:20]:
        parts = []
        for key, val in row.items():
            if hasattr(val, 'strftime'):
                val = _format_date_fr(str(val))
            elif isinstance(val, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', val):
                val = _format_date_fr(val)
            parts.append(f"{key}: {val}")
        lines.append(" | ".join(parts))

    if len(rows) > 20:
        lines.append(f"... ({len(rows)} résultats au total, 20 premiers affichés)")

    return "\n".join(lines)
