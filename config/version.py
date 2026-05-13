"""
Configuration centralisée des versions LotoIA.
Tous les fichiers du projet DOIVENT importer depuis ce module.
"""
import os
from datetime import date

# V141 A.4 UX Fixes — Rating popup 3 tiers + Hors-périmètre loteries étrangères (Release 1.6.029, 13/05/2026)
# Fix 1 : Rating popup chatbot 7 widgets + banner — 3 tiers low/mid/high
#   - LOW (1-2) : popup obligatoire 20 chars + compteur évolutif rouge/orange/vert + X dismiss
#   - MID (3)   : popup optionnel [Passer] + [Envoyer]
#   - HIGH (4-5): popup optionnel [Passer] + [Envoyer] (prompt positif)
#   - Bug fixé : rating-popup.js banner "Envoyer sans texte = vote vide" → validation 20 chars LOW
# Fix 2 : Phase OUT_OF_SCOPE_LOTTERY (pre-empt Phase A argent)
#   - 25 patterns loteries étrangères (Afrique francophone + US/UK/AUS + Europe + Amériques)
#   - Cross-sell module-aware EM↔Loto (links /euromillions /loto)
#   - Defense-in-depth Phase A skip si real foreign détecté
#   - Cas terrain reproduit 12/05/2026 22:33-22:35 user sénégalais (vote 1*)
APP_VERSION = "1.6.029"
APP_NAME = "LotoIA"
VERSION_DATE = "2026-05-13"

# Sitemap lastmod — auto-generated at import time (= deploy time on Cloud Run).
# Override via DEPLOY_DATE env var in CI/CD if needed.
LAST_DEPLOY_DATE = os.getenv("DEPLOY_DATE", date.today().isoformat())

# Alias pour compatibilité avec engine/version.py
__version__ = APP_VERSION
