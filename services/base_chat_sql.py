"""
Base Text-to-SQL — shared validation, constants, cleaning, execution, formatting.
Game-specific SQL generation, DB queries, and prompts stay in wrappers.
"""

import asyncio
import re
import logging

import aiomysql

import db_cloudsql
from db_cloudsql import ReadonlyPoolUnavailable
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

# 1.6.055: SQL genere refuse quand le pool lecture seule est indisponible (6 langues).
# Consigne interne en FR (code-matched), message transmis dans la langue de l'utilisateur.
_SQL_UNAVAILABLE_GUARD = (
    "[RÉSULTAT SQL]\nDonnées momentanément indisponibles : ne cite AUCUN chiffre, "
    "date ni numéro. Transmets ce message : "
)
_SQL_UNAVAILABLE_MESSAGES = {
    "fr": "Les statistiques détaillées sont momentanément indisponibles. Réessaie dans quelques minutes.",
    "en": "Detailed statistics are temporarily unavailable. Please try again in a few minutes.",
    "es": "Las estadísticas detalladas no están disponibles en este momento. "
          "Vuelve a intentarlo en unos minutos.",
    "pt": "As estatísticas detalhadas estão temporariamente indisponíveis. "
          "Tenta novamente daqui a alguns minutos.",
    "de": "Die detaillierten Statistiken sind vorübergehend nicht verfügbar. "
          "Versuche es in ein paar Minuten erneut.",
    "nl": "De gedetailleerde statistieken zijn tijdelijk niet beschikbaar. "
          "Probeer het over een paar minuten opnieuw.",
}

# F01 V82: Whitelist tables autorisees par game (defense semantique Gemini)
ALLOWED_TABLES_LOTO = frozenset({"tirages"})
ALLOWED_TABLES_EM = frozenset({"tirages_euromillions"})

# 1.6.055: extraction complete des tables (virgules, JOIN, alias, parentheses), fail-closed.
# Remplace _TABLE_RE (S13 V94) qui ne lisait que le 1er nom apres FROM/JOIN.
_STRING_LIT_RE = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_SCHEMA_REF_RE = re.compile(
    r"\b(?:information_schema|mysql|performance_schema|sys|lotofrance|lotofrance_staging)\s*`?\s*\.",
    re.IGNORECASE,
)
# MySQL 8 : `TABLE t` lit une table sans FROM (ex. ... UNION ALL TABLE chat_log)
_TABLE_STMT_RE = re.compile(r"\bTABLE\b", re.IGNORECASE)
_FROM_RE = re.compile(r"\bFROM\b", re.IGNORECASE)
_FROM_END_RE = re.compile(
    r"\b(?:WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|UNION|WINDOW|FOR|LOCK|INTO)\b", re.IGNORECASE,
)
_JOIN_RE = re.compile(
    r"\b(?:NATURAL\s+|CROSS\s+|INNER\s+|STRAIGHT_|(?:LEFT|RIGHT)\s+(?:OUTER\s+)?)?JOIN\b", re.IGNORECASE,
)
_JOIN_COND_RE = re.compile(r"\b(?:ON|USING)\b", re.IGNORECASE)
_TABLE_ITEM_RE = re.compile(r"^`?(\w+)`?(?:\s+(?:AS\s+)?`?\w+`?)?$", re.IGNORECASE)
# Fonctions dont la syntaxe contient FROM sans lire de table : EXTRACT(YEAR FROM d), TRIM(x FROM y)...
_FROM_FUNCS = frozenset({"EXTRACT", "TRIM", "SUBSTRING", "SUBSTR", "POSITION"})
_SELECT_START_RE = re.compile(r"[\s(]*SELECT\b", re.IGNORECASE)  # via .match() : ancre a la position


def _depths(s: str) -> list[int]:
    """Profondeur de parentheses AVANT chaque caractere de s."""
    out, depth = [], 0
    for ch in s:
        out.append(depth)
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
    return out


def _read_from_clause(s: str, start: int) -> str:
    """Clause FROM : de start jusqu'a un mot-cle de fin (niveau 0) ou la ')' qui ferme le bloc."""
    depth = 0
    i = start
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_")) and _FROM_END_RE.match(s, i):
            break
        i += 1
    return s[start:i]


def _split_top_level(clause: str) -> list[str]:
    """Decoupe la clause FROM sur virgules et JOIN de niveau 0, coupe les conditions ON/USING."""
    depth = _depths(clause)
    cuts = [(m.start(), m.end()) for m in re.finditer(r",", clause) if depth[m.start()] == 0]
    cuts += [(m.start(), m.end()) for m in _JOIN_RE.finditer(clause) if depth[m.start()] == 0]
    items, pos = [], 0
    for a, b in sorted(cuts):
        items.append(clause[pos:a])
        pos = b
    items.append(clause[pos:])
    out = []
    for item in items:
        d = _depths(item)
        cond = next((m.start() for m in _JOIN_COND_RE.finditer(item) if d[m.start()] == 0), None)
        out.append(item[:cond] if cond is not None else item)
    return out


def _from_context(s: str, pos: int) -> str:
    """Nature du FROM en position pos : 'table' (niveau 0 ou sous-requete), 'func' (EXTRACT...), 'unknown'."""
    stack = []
    for i in range(pos):
        if s[i] == "(":
            stack.append(i)
        elif s[i] == ")" and stack:
            stack.pop()
    if not stack:
        return "table"
    opener = stack[-1]
    if _SELECT_START_RE.match(s, opener + 1):
        return "table"
    m = re.search(r"(\w+)\s*$", s[:opener])
    if m and m.group(1).upper() in _FROM_FUNCS:
        return "func"
    return "unknown"


def _extract_tables(sql: str) -> list[str] | None:
    """1.6.055 — Toutes les tables apres FROM / JOIN / virgule. None = forme non reconnue → rejet."""
    s = _STRING_LIT_RE.sub("''", sql)
    tables = []
    for m in _FROM_RE.finditer(s):
        ctx = _from_context(s, m.start())
        if ctx == "func":
            continue
        if ctx == "unknown":
            return None                              # FROM dans une parenthese non reconnue → rejet
        for item in _split_top_level(_read_from_clause(s, m.end())):
            item = item.strip()
            if item.startswith("("):
                if _SELECT_START_RE.match(item):
                    continue                         # sous-requete / table derivee : son FROM est lu par la boucle
                return None                          # (table) entre parentheses → rejet
            mt = _TABLE_ITEM_RE.match(item)
            if not mt:
                return None                          # schema.table, fonction, index hint, vide... → rejet
            tables.append(mt.group(1))
    return tables

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
    # F01 V84: MySQL-style # comment (defense-in-depth — mitigated by readonly pool)
    if "#" in sql:
        logger.warning("[TEXT2SQL] SQL comment # detected: %s", sql[:200])
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
    # 1.6.055: toutes les tables (virgules, JOIN, sous-requetes), fail-closed
    no_literals = _STRING_LIT_RE.sub("''", sql)
    if _SCHEMA_REF_RE.search(no_literals):
        logger.warning("[TEXT2SQL] Schema-qualified reference: %s", sql[:200])
        return False
    if _TABLE_STMT_RE.search(no_literals):
        logger.warning("[TEXT2SQL] TABLE statement rejected: %s", sql[:200])
        return False
    tables_found = _extract_tables(sql)
    if tables_found is None:
        logger.warning("[TEXT2SQL] Unparseable FROM clause: %s", sql[:200])
        return False
    if not tables_found:
        logger.warning("[TEXT2SQL] No FROM clause found in SQL: %s", sql[:200])
        return False
    for tbl in tables_found:
        if tbl.lower() not in {t.lower() for t in allowed_tables}:
            logger.warning("[TEXT2SQL] Unauthorized table '%s' in SQL: %s", tbl, sql[:200])
            return False

    return True


# S03 V94: regex to extract and cap existing LIMIT value
_LIMIT_RE = re.compile(
    r"\bLIMIT\s+(\d+)\s*(?:,\s*(\d+))?(?:\s+OFFSET\s+\d+)?",
    re.IGNORECASE,
)


def _ensure_limit(sql: str, max_limit: int = 20) -> str:
    """Ajoute LIMIT si absent, plafonne a max_limit si present."""
    m = _LIMIT_RE.search(sql)
    if not m:
        return sql.rstrip() + f" LIMIT {max_limit}"
    # LIMIT offset, count (MySQL syntax) → cap count (group 2)
    if m.group(2) is not None:
        count = int(m.group(2))
        if count > max_limit:
            return sql[:m.start(2)] + str(max_limit) + sql[m.end(2):]
    else:
        # LIMIT N  or  LIMIT N OFFSET M → cap N
        count = int(m.group(1))
        if count > max_limit:
            return sql[:m.start(1)] + str(max_limit) + sql[m.end(1):]
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
        # 1.6.055: pool lecture seule strict, jamais de repli sur le pool principal
        async with db_cloudsql.get_connection_chatbot_sql() as conn:
            cursor = await conn.cursor()
            await cursor.execute(sql)
            rows = await cursor.fetchall()
            return rows
    except ReadonlyPoolUnavailable:
        raise  # remonte a run_text_to_sql (reponse propre 6 langues)
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

    lines = ["[RÉSULTAT SQL — CHIFFRES EXACTS, NE PAS MODIFIER]"]

    for row in rows[:20]:
        parts = []
        for key, val in row.items():
            if hasattr(val, 'strftime'):
                val = _format_date_fr(str(val))
            elif isinstance(val, str) and re.match(r'^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$', val):  # 1.6.055
                val = _format_date_fr(val)
            parts.append(f"{key}: {val}")
        lines.append(" | ".join(parts))

    # V111: force explicit newline separators when listing multiple draws
    # to prevent Gemini from collapsing rows into a single line in SSE output
    if len(rows) > 3:
        lines.insert(1, "(UN tirage par ligne — ne JAMAIS coller deux tirages sur la même ligne)")

    if len(rows) > 20:
        lines.append(f"... ({len(rows)} résultats au total, 20 premiers affichés)")

    lines.append("[/RÉSULTAT SQL]")

    return "\n".join(lines)
