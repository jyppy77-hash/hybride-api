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
from typing import Optional

import pymysql
from pymysql.cursors import DictCursor

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
# CONFIG
# ============================================================

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "lotofrance")

CLOUD_SQL_CONNECTION_NAME = os.getenv(
    "CLOUD_SQL_CONNECTION_NAME"
)

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))

# ============================================================
# ENV DETECTION
# ============================================================

def is_cloud_run() -> bool:
    return bool(os.getenv("K_SERVICE"))


def get_env() -> str:
    return "PROD" if is_cloud_run() else "LOCAL"


# ============================================================
# VALIDATION
# ============================================================

def validate_config():
    if not DB_USER:
        raise RuntimeError("DB_USER manquant")

    if not DB_PASSWORD:
        raise RuntimeError("DB_PASSWORD manquant (Secret Manager)")

    if not DB_NAME:
        raise RuntimeError("DB_NAME manquant")

    if is_cloud_run() and not CLOUD_SQL_CONNECTION_NAME:
        raise RuntimeError("CLOUD_SQL_CONNECTION_NAME manquant")


# ============================================================
# CONNECTION
# ============================================================

def get_connection() -> pymysql.connections.Connection:
    """
    Create MySQL connection (Cloud SQL / Local)
    """
    validate_config()
    env = get_env()

    try:
        if is_cloud_run():
            # ==========================
            # CLOUD RUN (UNIX SOCKET)
            # ==========================
            unix_socket = f"/cloudsql/{CLOUD_SQL_CONNECTION_NAME}"

            logger.info(f"[{env}] Connexion Cloud SQL via socket")

            conn = pymysql.connect(
                unix_socket=unix_socket,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset="utf8mb4",
                cursorclass=DictCursor,
                autocommit=True,
                connect_timeout=5
            )

        else:
            # ==========================
            # LOCAL (TCP)
            # ==========================
            logger.info(f"[{env}] Connexion MySQL via TCP {DB_HOST}:{DB_PORT}")

            conn = pymysql.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset="utf8mb4",
                cursorclass=DictCursor,
                autocommit=True,
                connect_timeout=5
            )

        logger.info(f"[{env}] Connexion MySQL OK")
        return conn

    except Exception as e:
        logger.error(f"[{env}] Erreur connexion MySQL: {e}")
        raise


# ============================================================
# TEST FUNCTIONS
# ============================================================

def test_connection() -> dict:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT VERSION() as version")
        version = cursor.fetchone()["version"]

        cursor.execute("SELECT COUNT(*) as total FROM tirages")
        total = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT MIN(date_de_tirage) as date_min,
                   MAX(date_de_tirage) as date_max
            FROM tirages
        """)
        dates = cursor.fetchone()

        conn.close()

        return {
            "status": "success",
            "environment": get_env(),
            "database": DB_NAME,
            "mysql_version": version,
            "total_tirages": total,
            "date_min": str(dates["date_min"]) if dates["date_min"] else None,
            "date_max": str(dates["date_max"]) if dates["date_max"] else None
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
            return cursor.fetchone()["total"]
    finally:
        conn.close()


def get_latest_tirage() -> Optional[dict]:
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
        exit(1)
