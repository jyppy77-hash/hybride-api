"""
Configuration centralisée des versions LotoIA.
Tous les fichiers du projet DOIVENT importer depuis ce module.
"""
import os
from datetime import date

# V141 A.4 Patch V131.G — 3 fixes Option B + re-toggle STRICT_HALLUCINATION_BLOCK (Release 1.6.030, 18/05/2026)
# Cible : éliminer faux positifs structurels Phase 2/3/3-bis post-V141 A.3 Item 7 + V131.G strict.
# Fix 1 : skip Check 2 `_recheck_phase0_draw_accuracy` sur Phase 2/3/3-bis si aucun `_DATA_TAG_RE`
#   présent dans `enrichment_context` — cas ID 2762 11/05 (grille USER capturée vs tirage DB de
#   comparaison) → faux positif structurel garanti par construction.
# Fix 2 : symétrisation `_DATA_TAG_RE` ↔ `_FACTUAL_TAGS` (3 → 15 tags) — élimine bruit log
#   `HALLUCINATION_ORPHAN_SEQUENCE` / `HALLUCINATION_ORPHAN_STAT_SINGLE` sur Phase 2/3/3-bis/
#   P/EVAL/0-bis/G qui injectent `[ANALYSE DE GRILLE]` / `[CLASSEMENT]` / etc.
# Fix 3 : skip Check 2 si `[CONTEXTE TIRAGE À VENIR]` ou `[CONTEXTE PAS DE TIRAGE CE JOUR]`
#   présent (Item 5 V141 A.3) — anti-faux positif `PHASE0_DATE_NOT_IN_DB` sur dates futures.
# Ref audit : `docs/Archives/AUDIT_V131G_VS_V141A3_2026-05-11.md`.
# Post-push : re-toggle prod `STRICT_HALLUCINATION_BLOCK=true` (Jyppy ÉTAPE 8 manuel).
#
# V141 A.4 UX Fixes (Release 1.6.029, 13/05/2026) — rappel :
#   Fix 1 rating popup 3 tiers (low 1-2 obligatoire / mid / high optionnels) sur 7 widgets +
#   Fix 2 Phase OUT_OF_SCOPE_LOTTERY 25 patterns + cross-sell EM↔Loto + defense-in-depth Phase A.
APP_VERSION = "1.6.030"
APP_NAME = "LotoIA"
VERSION_DATE = "2026-05-18"

# Sitemap lastmod — auto-generated at import time (= deploy time on Cloud Run).
# Override via DEPLOY_DATE env var in CI/CD if needed.
LAST_DEPLOY_DATE = os.getenv("DEPLOY_DATE", date.today().isoformat())

# Alias pour compatibilité avec engine/version.py
__version__ = APP_VERSION
