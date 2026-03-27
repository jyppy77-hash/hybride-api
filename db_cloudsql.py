"""
Module de connexion Cloud SQL pour LotoIA
========================================

Connexion centralisée vers MySQL (Google Cloud SQL) via aiomysql async pool.
Supporte automatiquement :
- LOCAL : TCP via Cloud SQL Proxy (127.0.0.1:DB_PORT)
- PROD  : Unix socket Cloud Run (/cloudsql/...)

Configuration via variables d'environnement (.env ou Cloud Run)
"""

import asyncio
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
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "lotofrance")

# Local config (Cloud SQL Proxy)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))

# Read-only credentials for chatbot Text-to-SQL isolation (S04)
DB_USER_READONLY = os.environ.get("DB_USER_READONLY", "")
DB_PASSWORD_READONLY = os.environ.get("DB_PASSWORD_READONLY", "")

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

# I01 V66: Lock to prevent concurrent pool recreation storms
_pool_lock = asyncio.Lock()
_pool_readonly_lock = asyncio.Lock()

# I01 V66: Shared pool kwargs builders (DRY for init + recreate)
_POOL_RECYCLE = 1800  # 30 min (was 3600 — faster stale connection eviction)


def _build_pool_kwargs(user: str, password: str, minsize: int, maxsize: int) -> dict:
    """Build common aiomysql pool kwargs."""
    kwargs = dict(
        minsize=minsize, maxsize=maxsize,
        user=user, password=password, db=DB_NAME,
        charset="utf8mb4", cursorclass=aiomysql.DictCursor,
        autocommit=True, connect_timeout=5,
        pool_recycle=_POOL_RECYCLE,
    )
    if is_production():
        kwargs["unix_socket"] = f"/cloudsql/{CLOUD_SQL_CONNECTION_NAME}"
    else:
        kwargs.update(host=DB_HOST, port=DB_PORT)
    return kwargs


async def init_pool():
    """Initialise le pool de connexions async aiomysql."""
    global _pool
    if _pool is not None:
        return

    if not DB_PASSWORD:
        logger.error("DB_PASSWORD non défini")
        raise ValueError("DB_PASSWORD requis (Secret Manager / .env)")

    _pool = await aiomysql.create_pool(**_build_pool_kwargs(DB_USER, DB_PASSWORD, 5, 10))
    logger.info(f"Pool aiomysql initialisé ({get_environment()}) — min=5, max=10, recycle={_POOL_RECYCLE}s")


async def close_pool():
    """Ferme le pool de connexions async."""
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        logger.info("Pool aiomysql fermé")


async def _recreate_pool():
    """I01 V66: Recreate main pool after connection failure (called under lock)."""
    global _pool
    async with _pool_lock:
        # Double-check: another coroutine may have recreated while we waited for the lock
        if _pool is not None:
            try:
                async with _pool.acquire() as conn:
                    cur = await conn.cursor()
                    await cur.execute("SELECT 1")
                    return  # Pool is actually healthy — skip recreation
            except Exception:
                pass  # Pool is dead — proceed with recreation
        # Close dead pool
        if _pool is not None:
            try:
                _pool.close()
                await _pool.wait_closed()
            except Exception:
                pass
            _pool = None
        # Create fresh pool
        _pool = await aiomysql.create_pool(**_build_pool_kwargs(DB_USER, DB_PASSWORD, 5, 10))
        logger.warning("[DB] Pool reconnection triggered — new pool created")


@asynccontextmanager
async def get_connection():
    """
    Async context manager qui retourne une connexion depuis le pool.
    I01 V66: If acquire() fails, recreate pool once and retry.
    Usage: async with get_connection() as conn:
    """
    if _pool is None:
        raise RuntimeError("Pool not initialized — call init_pool() first")
    try:
        async with _pool.acquire() as conn:
            yield conn
    except Exception as first_err:
        # Retry once after pool recreation
        try:
            await _recreate_pool()
        except Exception as recreate_err:
            logger.error("[DB] Pool recreation failed: %s", recreate_err)
            raise first_err from recreate_err
        if _pool is None:
            raise first_err
        async with _pool.acquire() as conn:
            yield conn


# ============================================================================
# ASYNC READ-ONLY POOL — chatbot Text-to-SQL isolation (S04)
# ============================================================================

_pool_readonly: aiomysql.Pool | None = None


async def init_pool_readonly():
    """Initialize read-only pool for chatbot SQL. Fallback to main pool if not configured."""
    global _pool_readonly
    if _pool_readonly is not None:
        return
    if not DB_USER_READONLY or not DB_PASSWORD_READONLY:
        logger.warning("[DB] DB_USER_READONLY not set — chatbot SQL uses main pool (no isolation)")
        return

    _pool_readonly = await aiomysql.create_pool(
        **_build_pool_kwargs(DB_USER_READONLY, DB_PASSWORD_READONLY, 2, 5)
    )
    logger.info(f"Pool aiomysql readonly initialisé ({get_environment()}) — min=2, max=5, recycle={_POOL_RECYCLE}s")


async def close_pool_readonly():
    """Close read-only pool."""
    global _pool_readonly
    if _pool_readonly:
        _pool_readonly.close()
        await _pool_readonly.wait_closed()
        _pool_readonly = None
        logger.info("Pool aiomysql readonly fermé")


async def _recreate_pool_readonly():
    """I01 V66: Recreate readonly pool after connection failure (called under lock)."""
    global _pool_readonly
    async with _pool_readonly_lock:
        if _pool_readonly is not None:
            try:
                async with _pool_readonly.acquire() as conn:
                    cur = await conn.cursor()
                    await cur.execute("SELECT 1")
                    return
            except Exception:
                pass
        if _pool_readonly is not None:
            try:
                _pool_readonly.close()
                await _pool_readonly.wait_closed()
            except Exception:
                pass
            _pool_readonly = None
        if not DB_USER_READONLY or not DB_PASSWORD_READONLY:
            return  # Cannot recreate — will fallback to main pool
        _pool_readonly = await aiomysql.create_pool(
            **_build_pool_kwargs(DB_USER_READONLY, DB_PASSWORD_READONLY, 2, 5)
        )
        logger.warning("[DB] Readonly pool reconnection triggered — new pool created")


@asynccontextmanager
async def get_connection_readonly():
    """Read-only connection for chatbot SQL. Falls back to main pool if not configured.
    I01 V66: If acquire() fails on readonly pool, recreate once and retry.
    Falls back to main pool via get_connection() if readonly pool cannot be recreated.
    """
    pool = _pool_readonly if _pool_readonly is not None else _pool
    if pool is None:
        raise RuntimeError("Pool not initialized — call init_pool() first")
    try:
        async with pool.acquire() as conn:
            yield conn
    except Exception as first_err:
        # If using readonly pool, try to recreate it
        if pool is _pool_readonly:
            try:
                await _recreate_pool_readonly()
            except Exception as recreate_err:
                logger.error("[DB] Readonly pool recreation failed: %s", recreate_err)
                raise first_err from recreate_err
            fallback_pool = _pool_readonly if _pool_readonly is not None else _pool
            if fallback_pool is None:
                raise first_err
            async with fallback_pool.acquire() as conn:
                yield conn
        else:
            # Using main pool — delegate to get_connection retry logic
            async with get_connection() as conn:
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


async def async_fetchall(sql: str, params=None) -> list[dict]:
    """Execute SELECT and return all rows as list of dicts."""
    async with get_connection() as conn:
        cur = await conn.cursor()
        await cur.execute(sql, params)
        return await cur.fetchall()


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
