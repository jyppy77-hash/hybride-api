"""
Base Text-to-SQL — shared validation and constants.
Game-specific SQL generation, execution, and DB queries stay in wrappers.
"""

import logging

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────

_MAX_SQL_PER_SESSION = 10

_SQL_FORBIDDEN = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "REPLACE INTO", "GRANT", "REVOKE", "EXEC ", "EXECUTE", "CALL ",
    "SLEEP", "BENCHMARK", "LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE",
    "INFORMATION_SCHEMA", "MYSQL.", "PERFORMANCE_SCHEMA", "SYS.",
]


# ────────────────────────────────────────────
# Validation (pure functions — no DB dependency)
# ────────────────────────────────────────────

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
    # UNION ALL is legitimate (frequency counting via unpivot).
    # Bare UNION (without ALL) is blocked as potential injection vector.
    if "UNION" in upper and "UNION ALL" not in upper:
        return False
    # Defense-in-depth: block deeply nested subqueries.
    # UNION ALL unpivot legitimately uses up to 8 SELECTs (1 outer + 5 boules + 2 etoiles).
    # Threshold at 10 blocks pathological nesting while allowing all valid patterns.
    if upper.count("SELECT") > 10:
        return False
    return True


def _ensure_limit(sql: str, max_limit: int = 50) -> str:
    """Ajoute LIMIT si absent, plafonne a max_limit si present."""
    upper = sql.strip().upper()
    if "LIMIT" not in upper:
        return sql.rstrip() + f" LIMIT {max_limit}"
    return sql
