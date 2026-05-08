"""
Configuration centralisée des versions LotoIA.
Tous les fichiers du projet DOIVENT importer depuis ce module.
"""
import os
from datetime import date

# V141 A.1 Quick wins anti-hallucination (Release 1.6.026, 8/05/2026)
# A2 fix _clean_response regex tags fermants `[/...]` (BUG #3)
# A3 extension _FACTUAL_TAGS 3 → 15 tags (HR6 confirmée Phase 2.5)
# A4 tag fermant systematique _format_generation_context Loto + EM
APP_VERSION = "1.6.026"
APP_NAME = "LotoIA"
VERSION_DATE = "2026-05-08"

# Sitemap lastmod — auto-generated at import time (= deploy time on Cloud Run).
# Override via DEPLOY_DATE env var in CI/CD if needed.
LAST_DEPLOY_DATE = os.getenv("DEPLOY_DATE", date.today().isoformat())

# Alias pour compatibilité avec engine/version.py
__version__ = APP_VERSION
