"""
Configuration centralisée des versions LotoIA.
Tous les fichiers du projet DOIVENT importer depuis ce module.
"""
import os
from datetime import date

# V141 A.2 Bugs Parser Phase T (Release 1.6.027, 8/05/2026)
# A6.1 ordinaux numériques 1er/1st/1°/etc. ligne 211 _detect_tirage
# A6.2 restriction _MOIS_NOM_EN_RE ligne 227 (fix BUG #1 critique)
# A6.3 ordinaux lettres premier/first/primero/primeiro/ersten/eerste 6 langs
# A9 fix _parse_draw_date_multilang DD/MM/YYYY + ordinaux + bug latent `may`
APP_VERSION = "1.6.027"
APP_NAME = "LotoIA"
VERSION_DATE = "2026-05-08"

# Sitemap lastmod — auto-generated at import time (= deploy time on Cloud Run).
# Override via DEPLOY_DATE env var in CI/CD if needed.
LAST_DEPLOY_DATE = os.getenv("DEPLOY_DATE", date.today().isoformat())

# Alias pour compatibilité avec engine/version.py
__version__ = APP_VERSION
