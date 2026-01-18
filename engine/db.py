"""
Connexion à la base de données MariaDB
Utilise la configuration depuis config_db.py
"""

# Import depuis la racine du projet
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config_db import get_connection
