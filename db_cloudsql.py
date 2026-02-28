"""
Module de connexion Cloud SQL pour LotoIA
========================================

Connexion centralisée vers MySQL (Google Cloud SQL) via aiomysql async pool.
Supporte automatiquement :
- LOCAL : TCP via Cloud SQL Proxy (127.0.0.1:DB_PORT)
- PROD  : Unix socket Cloud Run (/cloudsql/...)

Configuration via variables d'environnement (.env ou Cloud Run)
"""

import os
import logging
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

import aiomysql

# Charger .env si disponible (dev local)
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
DB_USER = os.getenv("DB_USER", "jyppy")
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
# ASYNC CONNECTION POOL (aiomysql)
# ============================================================================

_pool: aiomysql.Pool | None = None


async def init_pool():
    """Initialise le pool de connexions async aiomysql."""
    global _pool
    if _pool is not None:
        return

    if not DB_PASSWORD:
        logger.error("DB_PASSWORD non défini")
        raise ValueError("DB_PASSWORD requis (Secret Manager / .env)")

    kwargs = dict(
        minsize=5, maxsize=10,
        user=DB_USER, password=DB_PASSWORD, db=DB_NAME,
        charset="utf8mb4", cursorclass=aiomysql.DictCursor,
        autocommit=True, connect_timeout=5,
        pool_recycle=3600,
    )

    if is_production():
        kwargs["unix_socket"] = f"/cloudsql/{CLOUD_SQL_CONNECTION_NAME}"
    else:
        kwargs.update(host=DB_HOST, port=DB_PORT)

    _pool = await aiomysql.create_pool(**kwargs)
    logger.info(f"Pool aiomysql initialisé ({get_environment()}) — min=5, max=10")


async def close_pool():
    """Ferme le pool de connexions async."""
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        logger.info("Pool aiomysql fermé")


@asynccontextmanager
async def get_connection():
    """
    Async context manager qui retourne une connexion depuis le pool.
    Usage: async with get_connection() as conn:
    """
    if _pool is None:
        raise RuntimeError("Pool not initialized — call init_pool() first")
    async with _pool.acquire() as conn:
        yield conn


# ============================================================================
# FONCTIONS UTILITAIRES (async)
# ============================================================================

async def test_connection() -> dict:
    try:
        async with get_connection() as conn:
            cur = await conn.cursor()
            await cur.execute("SELECT VERSION() as version")
            version = (await cur.fetchone())["version"]

            await cur.execute("SELECT COUNT(*) as total FROM tirages")
            total = (await cur.fetchone())["total"]

            await cur.execute("""
                SELECT MIN(date_de_tirage) as date_min,
                       MAX(date_de_tirage) as date_max
                FROM tirages
            """)
            dates = await cur.fetchone()

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


async def get_tirages_count() -> int:
    async with get_connection() as conn:
        cur = await conn.cursor()
        await cur.execute("SELECT COUNT(*) as total FROM tirages")
        result = await cur.fetchone()
        return result["total"] if result else 0


async def get_em_tirages_count() -> int:
    async with get_connection() as conn:
        cur = await conn.cursor()
        await cur.execute("SELECT COUNT(*) as total FROM tirages_euromillions")
        result = await cur.fetchone()
        return result["total"] if result else 0


async def get_latest_tirage() -> Optional[dict]:
    async with get_connection() as conn:
        cur = await conn.cursor()
        await cur.execute("""
            SELECT *
            FROM tirages
            ORDER BY date_de_tirage DESC
            LIMIT 1
        """)
        result = await cur.fetchone()
        if result and result.get("date_de_tirage"):
            result["date_de_tirage"] = str(result["date_de_tirage"])
        return result


async def get_tirages_list(limit: int = 10, offset: int = 0) -> list:
    limit = min(max(1, limit), 100)
    offset = max(0, offset)

    async with get_connection() as conn:
        cur = await conn.cursor()
        await cur.execute("""
            SELECT *
            FROM tirages
            ORDER BY date_de_tirage DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        results = await cur.fetchall()

        for row in results:
            if row.get("date_de_tirage"):
                row["date_de_tirage"] = str(row["date_de_tirage"])

        return results


async def async_query(sql: str, params=None):
    """Execute INSERT/UPDATE/DELETE and commit."""
    async with get_connection() as conn:
        cur = await conn.cursor()
        await cur.execute(sql, params)


async def async_fetchone(sql: str, params=None) -> Optional[dict]:
    """Execute SELECT and return a single row as dict (or None)."""
    async with get_connection() as conn:
        cur = await conn.cursor()
        await cur.execute(sql, params)
        return await cur.fetchone()


# ============================================================================
# CLI TEST
# ============================================================================

if __name__ == "__main__":
    import asyncio

    async def _main():
        print("=" * 50)
        print("TEST CONNEXION CLOUD SQL (async)")
        print("=" * 50)

        await init_pool()
        result = await test_connection()

        if result["status"] == "ok":
            print(f"Environnement : {result['environment']}")
            print(f"Base : {result['database']}")
            print(f"MySQL : {result['mysql_version']}")
            print(f"Tirages : {result['total_tirages']}")
            print(f"Période : {result['date_min']} -> {result['date_max']}")
            print("CONNEXION OK")
        else:
            print(f"ERREUR : {result['error']}")
            exit(1)

        await close_pool()

    asyncio.run(_main())
