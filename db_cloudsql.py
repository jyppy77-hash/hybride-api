"""
Module de connexion Cloud SQL pour LotoIA
========================================

Connexion centralisée vers MySQL (Google Cloud SQL)
Supporte automatiquement :
- LOCAL : TCP via Cloud SQL Proxy (127.0.0.1:DB_PORT)
- PROD  : Unix socket Cloud Run (/cloudsql/...)

Configuration via variables d'environnement (.env ou Cloud Run)
"""

import os
import logging
from pathlib import Path
from typing import Optional
import asyncio

import pymysql
from pymysql.cursors import DictCursor

# Charger .env si disponible (dev local)
# Utilise un chemin absolu basé sur l'emplacement de CE fichier
# pour éviter les problèmes de working directory
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Cloud SQL Connection Name (PROD)
CLOUD_SQL_CONNECTION_NAME = os.getenv(
    "CLOUD_SQL_CONNECTION_NAME",
    "gen-lang-client-0680927607:europe-west1:lotostat-eu"
)

# Credentials (Cloud Run / .env)
DB_USER = os.getenv("DB_USER", "jyppy")   # 🔥 default corrigé
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "lotofrance")

# Local config (Cloud SQL Proxy)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))

# ============================================================================
# DETECTION ENVIRONNEMENT
# ============================================================================

def is_production() -> bool:
    """
    Détecte si on est en environnement Cloud Run
    via la variable K_SERVICE (injectée automatiquement par Cloud Run).
    """
    return bool(os.getenv("K_SERVICE"))


def get_environment() -> str:
    return "PROD" if is_production() else "LOCAL"


# Log de démarrage (une seule fois à l'import du module)
logger.info(
    f"db_cloudsql chargé | ENV={get_environment()} | "
    f"DB_HOST={DB_HOST} | DB_PORT={DB_PORT} | DB_NAME={DB_NAME} | "
    f"DB_USER={DB_USER} | "
    f"CLOUD_SQL={CLOUD_SQL_CONNECTION_NAME if is_production() else 'N/A (local)'}"
)


# ============================================================================
# CONNEXION PRINCIPALE
# ============================================================================

def get_connection() -> pymysql.connections.Connection:
    """
    Retourne une connexion PyMySQL vers Cloud SQL.
    """
    env = get_environment()

    # Vérification password
    if not DB_PASSWORD:
        logger.error("DB_PASSWORD non défini")
        raise ValueError("DB_PASSWORD requis (Secret Manager / .env)")

    try:
        if is_production():
            # =====================
            # MODE PROD (Cloud Run)
            # =====================
            unix_socket = f"/cloudsql/{CLOUD_SQL_CONNECTION_NAME}"

            logger.debug("Connexion PROD via Cloud SQL unix socket")

            conn = pymysql.connect(
                host="localhost",  # 🔥 CRITIQUE POUR CLOUD RUN
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
            # =====================
            # MODE LOCAL (Proxy)
            # =====================
            logger.debug(f"Connexion LOCAL via TCP {DB_HOST}:{DB_PORT}")

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

        logger.debug(f"Connexion MySQL OK ({env})")
        return conn

    except pymysql.Error as e:
        logger.error(f"Echec connexion MySQL ({env}) : {e}")
        raise


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def test_connection() -> dict:
    try:
        conn = get_connection()
        try:
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
        finally:
            conn.close()

        return {
            "status": "ok",
            "environment": get_environment(),
            "database": DB_NAME,
            "mysql_version": version,
            "total_tirages": total,
            "date_min": str(dates["date_min"]) if dates["date_min"] else None,
            "date_max": str(dates["date_max"]) if dates["date_max"] else None
        }

    except Exception as e:
        return {
            "status": "error",
            "environment": get_environment(),
            "error": str(e)
        }


def get_tirages_count() -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM tirages")
        result = cursor.fetchone()
        return result["total"] if result else 0
    finally:
        conn.close()


def get_latest_tirage() -> Optional[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
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


def get_tirages_list(limit: int = 10, offset: int = 0) -> list:
    limit = min(max(1, limit), 100)
    offset = max(0, offset)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT *
            FROM tirages
            ORDER BY date_de_tirage DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        results = cursor.fetchall()

        for row in results:
            if row.get("date_de_tirage"):
                row["date_de_tirage"] = str(row["date_de_tirage"])

        return results
    finally:
        conn.close()


# ============================================================================
# ASYNC HELPERS (asyncio.to_thread)
# ============================================================================

async def async_query(sql, params=None):
    """Execute SQL and return fetchall() via asyncio.to_thread()."""
    def _run():
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchall()
        finally:
            conn.close()
    return await asyncio.to_thread(_run)


async def async_fetchone(sql, params=None):
    """Execute SQL and return fetchone() via asyncio.to_thread()."""
    def _run():
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchone()
        finally:
            conn.close()
    return await asyncio.to_thread(_run)


async def async_call(func, *args, **kwargs):
    """Run any sync function via asyncio.to_thread()."""
    return await asyncio.to_thread(func, *args, **kwargs)


# ============================================================================
# CLI TEST
# ============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("TEST CONNEXION CLOUD SQL")
    print("=" * 50)

    result = test_connection()

    if result["status"] == "ok":
        print(f"Environnement : {result['environment']}")
        print(f"Base : {result['database']}")
        print(f"MySQL : {result['mysql_version']}")
        print(f"Tirages : {result['total_tirages']}")
        print(f"Période : {result['date_min']} -> {result['date_max']}")
        print("✅ CONNEXION OK")
    else:
        print(f"❌ ERREUR : {result['error']}")
        exit(1)
