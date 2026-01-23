"""
Cloud SQL Connection Module - LotoIA
===================================

Support:
- LOCAL : TCP (Cloud SQL Proxy / MySQL local)
- PROD  : Unix socket (Google Cloud Run + Cloud SQL)

Env vars required (Cloud Run / .env):
- DB_USER
- DB_PASSWORD
- DB_NAME
- CLOUD_SQL_CONNECTION_NAME
"""

import os
import logging
from typing import Optional, List, Dict, Any

import pymysql
from pymysql.cursors import DictCursor
from pymysql.err import OperationalError

# ============================================================
# LOAD .env (LOCAL ONLY)
# ============================================================

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("cloudsql")

# ============================================================
# HELPERS (ENV)
# ============================================================

def _get_env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v if v is not None else default


def _get_db_user() -> str:
    return _get_env("DB_USER", "")


def _get_db_password() -> str:
    return _get_env("DB_PASSWORD", "")


def _get_db_name() -> str:
    return _get_env("DB_NAME", "lotofrance")


def _get_cloudsql_connection_name() -> str:
    return _get_env("CLOUD_SQL_CONNECTION_NAME", "")


def _get_db_host() -> str:
    return _get_env("DB_HOST", "127.0.0.1")


def _get_db_port() -> int:
    try:
        return int(_get_env("DB_PORT", "3306"))
    except ValueError:
        return 3306

# ============================================================
# ENV DETECTION
# ============================================================

def is_cloud_run() -> bool:
    """Detect Cloud Run environment."""
    return bool(os.getenv("K_SERVICE"))


def get_env() -> str:
    return "PROD" if is_cloud_run() else "LOCAL"

# ============================================================
# VALIDATION
# ============================================================

def validate_config() -> None:
    """
    Validate required env vars at runtime.
    IMPORTANT: Called only when opening a connection (not at import).
    """
    db_user = _get_db_user()
    db_password = _get_db_password()
    db_name = _get_db_name()
    cloudsql_name = _get_cloudsql_connection_name()

    if not db_user:
        raise RuntimeError("DB_USER manquant")

    if not db_password:
        raise RuntimeError("DB_PASSWORD manquant (Secret Manager / .env)")

    if not db_name:
        raise RuntimeError("DB_NAME manquant")

    if is_cloud_run() and not cloudsql_name:
        raise RuntimeError("CLOUD_SQL_CONNECTION_NAME manquant (Cloud Run)")

# ============================================================
# CONNECTION
# ============================================================

def get_connection() -> pymysql.connections.Connection:
    """
    Create MySQL connection (Cloud SQL / Local).
    Cloud Run uses unix socket /cloudsql/<connection_name>.
    Local uses TCP (Proxy) 127.0.0.1:3306 by default.
    """
    env = get_env()
    validate_config()

    # Read values "hot" (Cloud Run secrets runtime)
    db_user = _get_db_user()
    db_password = _get_db_password()
    db_name = _get_db_name()
    cloudsql_name = _get_cloudsql_connection_name()
    db_host = _get_db_host()
    db_port = _get_db_port()

    try:
        if is_cloud_run():
            unix_socket = f"/cloudsql/{cloudsql_name}"
            logger.info(f"[{env}] Connexion Cloud SQL via socket: {unix_socket}")

            # IMPORTANT: no host=localhost here (socket is enough)
            conn = pymysql.connect(
                unix_socket=unix_socket,
                user=db_user,
                password=db_password,
                database=db_name,
                charset="utf8mb4",
                cursorclass=DictCursor,
                autocommit=True,
                connect_timeout=10,
                read_timeout=30,
                write_timeout=30,
            )

        else:
            logger.info(f"[{env}] Connexion MySQL via TCP {db_host}:{db_port}")

            conn = pymysql.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=db_name,
                charset="utf8mb4",
                cursorclass=DictCursor,
                autocommit=True,
                connect_timeout=10,
                read_timeout=30,
                write_timeout=30,
            )

        logger.info(f"[{env}] Connexion MySQL OK")
        return conn

    except OperationalError as e:
        logger.error(f"[{env}] Erreur MySQL (OperationalError): {e}")
        raise
    except Exception as e:
        logger.error(f"[{env}] Erreur connexion MySQL: {e}")
        raise

# ============================================================
# TEST FUNCTIONS
# ============================================================

def test_connection() -> dict:
    """
    Returns diagnostic info (version, counts, min/max dates).
    Safe to expose on /database-info endpoint.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT VERSION() as version")
        row_ver = cursor.fetchone() or {}
        version = row_ver.get("version")

        cursor.execute("SELECT COUNT(*) as total FROM tirages")
        row_total = cursor.fetchone() or {}
        total = row_total.get("total", 0)

        cursor.execute("""
            SELECT MIN(date_de_tirage) as date_min,
                   MAX(date_de_tirage) as date_max
            FROM tirages
        """)
        dates = cursor.fetchone() or {}

        conn.close()

        return {
            "status": "success",
            "environment": get_env(),
            "database": _get_db_name(),
            "mysql_version": version,
            "total_tirages": int(total) if total is not None else 0,
            "date_min": str(dates.get("date_min")) if dates.get("date_min") else None,
            "date_max": str(dates.get("date_max")) if dates.get("date_max") else None
        }

    except Exception as e:
        return {
            "status": "error",
            "environment": get_env(),
            "error": str(e)
        }

# ============================================================
# SIMPLE QUERIES
# ============================================================

def get_tirages_count() -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as total FROM tirages")
            row = cursor.fetchone() or {}
            return int(row.get("total", 0))
    finally:
        conn.close()


def get_latest_tirage() -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT *
                FROM tirages
                ORDER BY date_de_tirage DESC
                LIMIT 1
            """)
            result = cursor.fetchone()
            if result and result.get("date_de_tirage"):
                result["date_de_tirage"] = str(result["date_de_tirage"])
            return result
    finally:
        conn.close()


def get_tirages_list(limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Returns a paginated list of tirages.
    limit capped between 1 and 100.
    """
    limit = min(max(1, int(limit)), 100)
    offset = max(0, int(offset))

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT *
                FROM tirages
                ORDER BY date_de_tirage DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            results = cursor.fetchall() or []

            for row in results:
                if row.get("date_de_tirage"):
                    row["date_de_tirage"] = str(row["date_de_tirage"])

            return results
    finally:
        conn.close()

# ============================================================
# CLI TEST
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST CLOUD SQL - LOTOIA")
    print("=" * 60)

    result = test_connection()

    if result["status"] == "success":
        print("✅ Connexion OK")
        print(f"Env : {result['environment']}")
        print(f"DB : {result['database']}")
        print(f"MySQL : {result['mysql_version']}")
        print(f"Tirages : {result['total_tirages']}")
        print(f"Période : {result['date_min']} → {result['date_max']}")
    else:
        print("❌ ERREUR :", result["error"])
        raise SystemExit(1)
