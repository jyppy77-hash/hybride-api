"""
Configuration centralisée des versions LotoIA.
Tous les fichiers du projet DOIVENT importer depuis ce module.
"""
import os
from datetime import date

# V142.E (Release 1.6.033, 20/05/2026) — Fix patch PDF EM 2 étoiles tracking calendar admin.
# Anomalie identifiée audit READ-ONLY 2026-05-20 §Axe 5
# (docs/AUDIT_ENGINE_HYBRIDE_PRE_V142_2026-05-20.md) : routes/api_analyse_unified.py:421
# passait `secondary_top[0]` singleton à record_pdf_meta_top → EM enregistrait 1 étoile
# au lieu de 2 dans hybride_selection_history (source='pdf_meta_*'). Impact : calendar
# admin /admin/calendar-perf sous-évaluait matches EM ~50% (_calc_match V137.D accepte
# déjà liste 2 stars). PDF visuel utilisateur NON impacté (services/em_pdf_generator.py OK).
# Fix : (1) signature record_pdf_meta_top `secondary_top: int | list[int] | None`
# rétrocompat singleton (4 tests V136/V137 préservés), (2) call site L421 calcule
# `_sec_count = 2 if game==EM else 1` + slice `secondary_top[:_sec_count]`. Isolation vs
# marinade V131.G-bis confirmée empiriquement (grep services/chat_*, engine/ → 0 match).
#
# V141 A.5 — Fix stats unified endpoint (Release 1.6.032, 18/05/2026, Option 3 hybride).
# Cause racine bug chronique 3/6 cards "-" page /euromillions/statistiques onglet
# "Analyse par numéro" (POURCENTAGE / ÉCART MOYEN / CLASSEMENT) tous numéros 1-50 +
# étoiles 1-12, 6 langues EM. Endpoint `unified_stats_number()` SQL inline minimal
# n'exposait pas ces 3 metrics dérivées que frontend lit sans fallback. Bug introduit
# avec refactor base class stats `dc9219e` (V45), silencieux (0 log warning/error 24h).
# Fix Option 3 : SQL inline PRESERVÉ (rétrocompat 100% 8 clés legacy) + délégation partielle
# `BaseStatsService.get_numero_stats()` pour 4 nouvelles clés (`pourcentage` float,
# `ecart_moyen`, `classement`, `classement_sur`). Anti-hallu strict : try/except → fallback
# 0.0/0/cfg.max_number (jamais None/'-'). Parité Loto FR : `ui/statistiques.html` 4→6 cards.
# +31 tests parametric. Voir diag : `docs/DIAG_STATS_FREQUENCE_AFFICHAGE_2026-05-18.md`.
#
# V141 A.4 Patch V131.G-bis — Fix B-bis Phase G court-circuite Phase T sur weekday relatif
# + Fix Hyp 3 propagation enrichment_context call site non-stream (Release 1.6.031, 18/05/2026).
# Cause racine cas terrain prod 18/05 11:34 (revision hybride-api-eu-00867-cpd) :
#   - User : "donne-moi une grille pour le tirage de mercredi" (Loto FR, SSE streaming).
#   - Phase G + Phase T combo : "mercredi" résolu vers 13/05 PASSÉ (handler weekday relatif)
#     → `[TIRAGE passé]` injecté + V131.G strip `[GRILLE GÉNÉRÉE]` → Gemini ne voit que
#     tirage passé + question gen → hallucine prédiction `10-18-27-36-41` → Check 1
#     `HALLUCINATION_INVENTED` bloque (block techniquement correct, faux positif UX).
# Fix B-bis : `_phase_g_attempted and _is_relative_weekday(message, lang)` → skip Phase T,
#   Phase G porte seule la réponse. Cas legitime "résultats du tirage de mercredi dernier"
#   préservé car `detect_generation` ne match pas.
# Fix Hyp 3 : call site non-stream `chat_pipeline_gemini.py:1036` propage `enrichment_context=`
#   à `_recheck_phase0_draw_accuracy` (gap dormant V131.G Fix 1+3 inactifs sur path non-stream).
# Helper `_is_relative_weekday(msg, lang)` créé dans `base_chat_detect_temporal.py` (6 langs).
# Post-push : re-toggle prod `STRICT_HALLUCINATION_BLOCK=true` (Jyppy ÉTAPE 8 manuel).
#
# V141 A.4 Patch V131.G (Release 1.6.030, 18/05/2026) — rappel :
#   Fix 1 skip Check 2 Phase 2/3/3-bis sans `_DATA_TAG_RE` + Fix 2 symétrie tags
#   (3→15) + Fix 3 skip Check 2 si `[CONTEXTE TIRAGE À VENIR]` présent.
# V141 A.4 UX Fixes (Release 1.6.029, 13/05/2026) — rappel :
#   Fix 1 rating popup 3 tiers (low 1-2 obligatoire / mid / high optionnels) sur 7 widgets +
#   Fix 2 Phase OUT_OF_SCOPE_LOTTERY 25 patterns + cross-sell EM↔Loto + defense-in-depth Phase A.
APP_VERSION = "1.6.033"
APP_NAME = "LotoIA"
VERSION_DATE = "2026-05-20"

# Sitemap lastmod — auto-generated at import time (= deploy time on Cloud Run).
# Override via DEPLOY_DATE env var in CI/CD if needed.
LAST_DEPLOY_DATE = os.getenv("DEPLOY_DATE", date.today().isoformat())

# Alias pour compatibilité avec engine/version.py
__version__ = APP_VERSION
