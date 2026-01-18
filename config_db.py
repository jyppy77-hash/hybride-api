"""
Configuration connexion MariaDB - Loto App
Supporte Laragon (local) et Cloud Run (prod)
"""
import os
import pymysql
from typing import Optional

# ============================================================================
# CONFIGURATION MARIADB
# ============================================================================

def get_db_config():
    """
    Retourne la config DB selon l'environnement
    Local (Laragon) ou Cloud Run (prod)
    """
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '3306')),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'loto_stats'),
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }

# ============================================================================
# CONNEXION
# ============================================================================

def get_connection():
    """
    Retourne une connexion MariaDB
    
    Returns:
        pymysql.Connection
        
    Raises:
        pymysql.Error si connexion échoue
    """
    try:
        DB_CONFIG = get_db_config()
        conn = pymysql.connect(**DB_CONFIG)
        return conn
    except pymysql.Error as e:
        print(f"❌ Erreur connexion MariaDB : {e}")
        raise

if __name__ == "__main__":
    # Test de connexion
    print("Test connexion MariaDB...")
    try:
        conn = get_connection()
        print("✅ Connexion réussie !")
        
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()
        print(f"Version MariaDB : {version}")
        
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print(f"Tables disponibles : {[t['Tables_in_loto_stats'] for t in tables]}")
        
        conn.close()
    except Exception as e:
        print(f"❌ Erreur : {e}")