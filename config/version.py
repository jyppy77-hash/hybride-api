"""
Configuration centralisée des versions LotoIA.
Tous les fichiers du projet DOIVENT importer depuis ce module.
"""
import os
from datetime import date

# V141 A.3 Audit V140 Phase 2.5 — 9 items packagés (Release 1.6.028, 9/05/2026)
# Item 2 : L5-F01 pattern lowercase ASCII + mixed case (BUG LATENT V141 A.1)
# Item 3 : L6-F01 invariant fonctionnel _FACTUAL_TAGS strippé (15 tests parametric)
# Item 4 : L5-F02 invariant structurel _FACTUAL_TAGS ↔ _INTERNAL_TAGS_PATTERNS + refactor
# Item 5 : NEW BUG #10 CTA grille HYBRIDE Phase T future + jour de tirage (cas terrain #1)
# Item 6 : BUG #7 orphan stat-single 1 num + N apparitions 6 langs (log-only)
# Item 7 : Extension _recheck_phase0_draw_accuracy à Phase 2/3/3-bis
# Item 8 : BUG #4 Phase G fallthrough silent failure fix (cas terrain #3 "Pru importe")
# Item 9 : BUG #6 Phase AFFIRMATION transitive anti-hallucination (cas terrain #2 "Oui")
APP_VERSION = "1.6.028"
APP_NAME = "LotoIA"
VERSION_DATE = "2026-05-09"

# Sitemap lastmod — auto-generated at import time (= deploy time on Cloud Run).
# Override via DEPLOY_DATE env var in CI/CD if needed.
LAST_DEPLOY_DATE = os.getenv("DEPLOY_DATE", date.today().isoformat())

# Alias pour compatibilité avec engine/version.py
__version__ = APP_VERSION
