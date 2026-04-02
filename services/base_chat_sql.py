"""
Base Text-to-SQL — shared validation, constants, cleaning, execution, formatting.
Game-specific SQL generation, DB queries, and prompts stay in wrappers.
"""

import asyncio
import re
import logging

import aiomysql

import db_cloudsql
from services.base_chat_utils import _format_date_fr

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────

_MAX_SQL_PER_SESSION = 10
_MAX_SQL_INPUT_LENGTH = 500

# F01 V83: i18n messages when SQL session limit is reached
_SQL_LIMIT_MESSAGES = {
    "fr": "Vous avez atteint la limite de requêtes pour cette session. Rechargez la page pour continuer.",
    "en": "You have reached the query limit for this session. Reload the page to continue.",
    "es": "Ha alcanzado el límite de consultas para esta sesión. Recargue la página para continuar.",
    "pt": "Você atingiu o limite de consultas para esta sessão. Recarregue a página para continuar.",
    "de": "Sie haben das Abfragelimit für diese Sitzung erreicht. Laden Sie die Seite neu, um fortzufahren.",
    "nl": "U heeft de limiet voor zoekopdrachten in deze sessie bereikt. Herlaad de pagina om verder te gaan.",
}

_SQL_FORBIDDEN = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "REPLACE INTO", "GRANT", "REVOKE", "EXEC ", "EXECUTE", "CALL ",
    "SLEEP", "BENCHMARK", "LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE",
    "INFORMATION_SCHEMA", "MYSQL.", "PERFORMANCE_SCHEMA", "SYS.",
]

# F01 V82: Whitelist tables autorisees par game (defense semantique Gemini)
ALLOWED_TABLES_LOTO = frozenset({"tirages"})
ALLOWED_TABLES_EM = frozenset({"tirages_euromillions"})
_TABLE_RE = re.compile(r"(?:FROM|JOIN)\s+(\w+)", re.IGNORECASE)

# F04: single source of truth for French weekday names (shared Loto + EM)
_JOURS_FR = {
    0: "lundi", 1: "mardi", 2: "mercredi", 3: "jeudi",
    4: "vendredi", 5: "samedi", 6: "dimanche",
}


# ────────────────────────────────────────────
# Validation (pure functions — no DB dependency)
# ────────────────────────────────────────────

def _validate_sql(sql: str, *, allowed_tables: frozenset[str]) -> bool:
    """Valide la securite du SQL genere (SELECT only, pas de mots interdits).

    Args:
        sql: SQL string to validate.
        allowed_tables: only these table names are permitted after FROM/JOIN (required).
    """
    if not sql:
        return False
    if len(sql) > 1000:
        return False

    # F03 V82: guard multi-statement par newline (defense-in-depth)
    lines = [ln.strip() for ln in sql.strip().splitlines() if ln.strip()]
    if len(lines) > 1:
        joined = " ".join(lines)
        if not re.search(r"\bUNION\s+ALL\b", joined, re.IGNORECASE):
            logger.warning("[TEXT2SQL] Multi-statement SQL detected (newline): %s", sql[:200])
            return False
        sql = joined  # normalise en une seule ligne pour la suite

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
    # UNION ALL is legitimate (frequency counting via unpivot).
    # Bare UNION (without ALL) is blocked as potential injection vector.
    if "UNION" in upper and "UNION ALL" not in upper:
        return False
    # Defense-in-depth: block deeply nested subqueries.
    # UNION ALL unpivot legitimately uses up to 8 SELECTs (1 outer + 5 boules + 2 etoiles).
    # Threshold at 10 blocks pathological nesting while allowing all valid patterns.
    if upper.count("SELECT") > 10:
        return False

    # F01 V82: whitelist tables — reject if SQL references unauthorized tables
    tables_found = _TABLE_RE.findall(sql)
    if not tables_found:
        logger.warning("[TEXT2SQL] No FROM clause found in SQL: %s", sql[:200])
        return False
    for tbl in tables_found:
        if tbl.lower() not in {t.lower() for t in allowed_tables}:
            logger.warning("[TEXT2SQL] Unauthorized table '%s' in SQL: %s", tbl, sql[:200])
            return False

    return True


def _ensure_limit(sql: str, max_limit: int = 50) -> str:
    """Ajoute LIMIT si absent, plafonne a max_limit si present."""
    upper = sql.strip().upper()
    if "LIMIT" not in upper:
        return sql.rstrip() + f" LIMIT {max_limit}"
    return sql


# ────────────────────────────────────────────
# SQL cleaning — F14: deduplicated from chat_sql + chat_sql_em
# ────────────────────────────────────────────

def _clean_gemini_sql(raw: str) -> str:
    """Nettoie le SQL brut retourne par Gemini (backticks, markdown, prefix 'sql')."""
    text = raw.strip()
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


# ────────────────────────────────────────────
# Gemini contents builder (shared Loto + EM)
# ────────────────────────────────────────────

def _build_gemini_sql_contents(question: str, history: list = None) -> list:
    """Construit les contents Gemini avec historique pour resolution de contexte."""
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
    return sql_contents


# ────────────────────────────────────────────
# Gemini call for SQL generation (shared Loto + EM)
# ────────────────────────────────────────────

def _guard_non_sql(text: str, log_prefix: str) -> str | None:
    """Reject if Gemini returned natural language instead of SQL. Returns cleaned text or 'NO_SQL'."""
    if text and text.upper() != "NO_SQL" and not text.upper().startswith("SELECT"):
        logger.warning("[%s] Non-SQL output rejected: %s", log_prefix, text[:100])
        return "NO_SQL"
    return text


# ────────────────────────────────────────────
# Execution + formatting (shared Loto + EM)
# ────────────────────────────────────────────

async def _execute_safe_sql(sql: str, *, allowed_tables: frozenset[str]) -> list | None:
    """Execute le SQL valide avec connexion DB readonly. Defense-in-depth: re-validates + ensure LIMIT."""
    if not _validate_sql(sql, allowed_tables=allowed_tables):
        logger.warning("[TEXT2SQL] _execute_safe_sql rejected unvalidated SQL: %s", sql[:100])
        return None
    sql = _ensure_limit(sql)  # F02 V74: defense-in-depth — cap LIMIT even if caller forgot
    try:
        async with db_cloudsql.get_connection_readonly() as conn:
            cursor = await conn.cursor()
            await cursor.execute(sql)
            rows = await cursor.fetchall()
            return rows
    except (aiomysql.Error, asyncio.TimeoutError, ConnectionError, OSError) as e:
        logger.error("[TEXT-TO-SQL] SQL execution error (%s): %s", type(e).__name__, e)
        return None
    except Exception as e:
        logger.exception("[TEXT-TO-SQL] Unexpected SQL execution error: %s", e)
        return None


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
