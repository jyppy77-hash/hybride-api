"""
Engine Database Module
======================

Proxy vers le module central db_cloudsql.py
Centralise toutes les connexions DB du projet.

Usage dans engine/:
    from .db import get_connection
    conn = get_connection()
"""

import sys
from pathlib import Path

# Ajouter le repertoire parent au path pour import
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Import centralise depuis db_cloudsql
from db_cloudsql import get_connection, get_environment, is_production

# Re-export pour compatibilite
__all__ = ['get_connection', 'get_environment', 'is_production']
