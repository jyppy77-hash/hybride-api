"""
Configuration centralisée des versions LotoIA.
Tous les fichiers du projet DOIVENT importer depuis ce module.
"""
import os
from datetime import date

APP_VERSION = "1.6.003"
APP_NAME = "LotoIA"
VERSION_DATE = "2026-04-15"

# Sitemap lastmod — auto-generated at import time (= deploy time on Cloud Run).
# Override via DEPLOY_DATE env var in CI/CD if needed.
LAST_DEPLOY_DATE = os.getenv("DEPLOY_DATE", date.today().isoformat())

# Alias pour compatibilité avec engine/version.py
__version__ = APP_VERSION
