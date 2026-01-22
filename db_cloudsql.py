"""
Module de connexion Cloud SQL pour LotoIA
=========================================

Connexion centralisee vers MySQL (Google Cloud SQL)
Supporte automatiquement :
- LOCAL : TCP via Cloud SQL Proxy (127.0.0.1:3306)
- PROD  : Unix socket Cloud Run (/cloudsql/...)

Configuration via variables d'environnement (.env ou Cloud Run)
"""

import os
import logging
from typing import Optional

import pymysql
from pymysql.cursors import DictCursor

# Charger .env si disponible (dev local)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv non installe en prod

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

# Cloud SQL Connection Name (PROD uniquement)
CLOUD_SQL_CONNECTION_NAME = os.getenv(
    'CLOUD_SQL_CONNECTION_NAME',
    'gen-lang-client-0680927607:europe-west9:lotostat'
)

# Credentials (depuis .env ou Cloud Run env vars)
DB_USER = os.getenv('DB_USER', 'jyppy')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'lotofrance')

# Local config (Cloud SQL Proxy)
DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
DB_PORT = int(os.getenv('DB_PORT', '3306'))


# ============================================================================
# DETECTION ENVIRONNEMENT
# ============================================================================

def is_production() -> bool:
    """
    Detecte si on est en environnement Cloud Run (production)

    Returns:
        True si PROD (Cloud Run), False si LOCAL
    """
    # K_SERVICE est defini automatiquement par Cloud Run
    # CLOUD_SQL_CONNECTION_NAME peut aussi etre utilise comme indicateur
    return bool(os.getenv('K_SERVICE')) or bool(os.getenv('INSTANCE_CONNECTION_NAME'))


def get_environment() -> str:
    """
    Retourne le nom de l'environnement actuel

    Returns:
        'PROD' ou 'LOCAL'
    """
    return 'PROD' if is_production() else 'LOCAL'


# ============================================================================
# CONNEXION PRINCIPALE
# ============================================================================

def get_connection() -> pymysql.connections.Connection:
    """
    Retourne une connexion PyMySQL vers Cloud SQL.

    Detection automatique :
    - LOCAL : host 127.0.0.1:3306 via Cloud SQL Proxy
    - PROD  : unix_socket /cloudsql/...

    Returns:
        pymysql.connections.Connection

    Raises:
        pymysql.Error: Si la connexion echoue
        ValueError: Si le mot de passe n'est pas configure
    """
    env = get_environment()

    # Validation du mot de passe
    if not DB_PASSWORD:
        logger.error("DB_PASSWORD non defini dans les variables d'environnement")
        raise ValueError(
            "DB_PASSWORD requis. Configurez-le dans .env (local) ou "
            "dans les variables d'environnement Cloud Run (prod)."
        )

    try:
        if is_production():
            # =====================
            # MODE PROD (Cloud Run)
            # =====================
            unix_socket = f"/cloudsql/{CLOUD_SQL_CONNECTION_NAME}"

            logger.info(f"Connexion PROD via unix socket: /cloudsql/***")

            conn = pymysql.connect(
                unix_socket=unix_socket,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset='utf8mb4',
                cursorclass=DictCursor,
                autocommit=True
            )
        else:
            # ============================
            # MODE LOCAL (Cloud SQL Proxy)
            # ============================
            logger.info(f"Connexion LOCAL via TCP: {DB_HOST}:{DB_PORT}")

            conn = pymysql.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset='utf8mb4',
                cursorclass=DictCursor,
                autocommit=True
            )

        logger.info(f"Connexion reussie a {DB_NAME} (env: {env})")
        return conn

    except pymysql.Error as e:
        logger.error(f"Echec connexion MySQL ({env}): {e}")
        raise


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def test_connection() -> dict:
    """
    Teste la connexion et retourne les infos de base

    Returns:
        Dict avec status, environnement, nombre de tirages, etc.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Version MySQL
        cursor.execute("SELECT VERSION() as version")
        version = cursor.fetchone()['version']

        # Nombre de tirages
        cursor.execute("SELECT COUNT(*) as total FROM tirages")
        total = cursor.fetchone()['total']

        # Plage de dates
        cursor.execute("""
            SELECT
                MIN(date_de_tirage) as date_min,
                MAX(date_de_tirage) as date_max
            FROM tirages
        """)
        dates = cursor.fetchone()

        conn.close()

        return {
            'status': 'ok',
            'environment': get_environment(),
            'database': DB_NAME,
            'mysql_version': version,
            'total_tirages': total,
            'date_min': str(dates['date_min']) if dates['date_min'] else None,
            'date_max': str(dates['date_max']) if dates['date_max'] else None
        }

    except Exception as e:
        return {
            'status': 'error',
            'environment': get_environment(),
            'error': str(e)
        }


def get_tirages_count() -> int:
    """
    Retourne le nombre total de tirages

    Returns:
        Nombre de tirages (int)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM tirages")
        result = cursor.fetchone()
        return result['total'] if result else 0
    finally:
        conn.close()


def get_latest_tirage() -> Optional[dict]:
    """
    Retourne le tirage le plus recent

    Returns:
        Dict avec les donnees du tirage, ou None si table vide
    """
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

        if result:
            # Convertir date en string pour JSON
            if result.get('date_de_tirage'):
                result['date_de_tirage'] = str(result['date_de_tirage'])

        return result
    finally:
        conn.close()


def get_tirages_list(limit: int = 10, offset: int = 0) -> list:
    """
    Retourne une liste de tirages (du plus recent au plus ancien)

    Args:
        limit: Nombre max de tirages (defaut: 10, max: 100)
        offset: Decalage pour pagination (defaut: 0)

    Returns:
        Liste de dicts avec les tirages
    """
    # Securite : limiter a 100 max
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

        # Convertir dates en strings pour JSON
        for row in results:
            if row.get('date_de_tirage'):
                row['date_de_tirage'] = str(row['date_de_tirage'])

        return results
    finally:
        conn.close()


# ============================================================================
# POINT D'ENTREE CLI
# ============================================================================

if __name__ == "__main__":
    """Test rapide de la connexion"""
    print("=" * 50)
    print("TEST CONNEXION CLOUD SQL")
    print("=" * 50)

    result = test_connection()

    if result['status'] == 'ok':
        print(f"Environnement : {result['environment']}")
        print(f"Base de donnees : {result['database']}")
        print(f"Version MySQL : {result['mysql_version']}")
        print(f"Nombre de tirages : {result['total_tirages']}")
        print(f"Periode : {result['date_min']} -> {result['date_max']}")
        print("=" * 50)
        print("CONNEXION OK")
    else:
        print(f"Environnement : {result['environment']}")
        print(f"ERREUR : {result['error']}")
        print("=" * 50)
        print("CONNEXION ECHOUEE")
        exit(1)
