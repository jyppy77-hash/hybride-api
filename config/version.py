"""
Configuration centralisée des versions LotoIA.
Tous les fichiers du projet DOIVENT importer depuis ce module.
"""
import os
from datetime import date

# Export PDF cockpit + lien nav (Release 1.6.044, 08/06/2026) — lot UI.
# (a) Bouton « Exporter en PDF » sur /admin/cockpit : re-POST du JSON brut → POST /admin/cockpit/pdf
# (owner-only, gardes 25 Mo dupliquées de /analyze qui reste byte-identique) → normalize_run →
# services/cockpit_pdf_generator.py::generate_cockpit_pdf (Platypus A4, FR-only). PDF diffusion-grade :
# 4 étages (signature triée JSD / conformité Tier 1 / histogramme stratification 3 séries matplotlib
# Agg → io.BytesIO SANS temp file disque → platypus.Image / secondaire), framing neutre strict,
# disclaimer ANJ de repli TOUJOURS en pied + disclaimer secondaire verbatim si présent, limitations
# du run affichées. Run dégradé (error) → 400, jamais de PDF vide. Stateless/RAM, rien sur disque/DB.
# MUR ÉTANCHE : cockpit_pdf_generator ne consomme que le view-model, 0 import tools.* (scan AST
# test_cockpit_wall.py couvre services/**). (b) Lien « Cockpit » ajouté à la topnav admin (_base.html).
# Zéro nouvelle dépendance (matplotlib 3.9.2 + reportlab 4.1.0 déjà présents).
#
# Cockpit Métrique V_X.F (Release 1.6.043, 08/06/2026) — page admin read-only /admin/cockpit.
# Lit un JSON de run OOS V_X.F uploadé (drag-drop), le normalise en view-model stateless
# (services/cockpit_parser.py::normalize_run, pur, sans I/O, sans DB), affiche 4 étages
# (signature triée JSD / conformité Tier 1 / histogramme stratification 3 séries / secondaire +
# disclaimer ANJ verbatim). MUR ÉTANCHE : aucun fichier runtime (main/routes/services/engine/
# middleware/config) n'importe tools.* — test AST tests/test_cockpit_wall.py casse le build sinon.
# Aucune écriture disque/DB. Owner-only (OWNER_IP), noindex. Outillage tools/ inchangé.
#
# Fix CSP connect-src gateway.umami.is (Release 1.6.042, 07/06/2026) — Umami a basculé son
# endpoint de collecte POST /api/send sur gateway.umami.is ; notre connect-src ne whitelistait
# que cloud.umami.is + api-gateway.umami.dev (anciens) → collecte cassée silencieusement
# ~05/06 SANS push (falaise trafic jour record). Fix : ajout gateway.umami.is dans connect-src
# (main.py), anciens domaines conservés. Push GROUPÉ : ce bump embarque aussi les 5 commits R&D
# offline V_X.F (signature secondaire *_in_T1, plancher Monte Carlo + FDR, positionnelles
# secondaire, verdict effect_tier 3 niveaux, stratification dimension de signature) — outillage
# tools/ pur, AUCUN import depuis main.py/routes/services/engine (inertes pour le runtime web).
#
# Backtest fidélité + perf (Release 1.6.041, 04/06/2026) — behavior-preserving, rien de
# visible users (patch). T-1 hard-exclude relatif (anti future-leak recent_draws) + leviers
# runtime A+B sur le backtest signature statistique. Golden test bit-identique + smoke local
# vert + perf ~81x. Outillage offline tools/ (backtest_hybride.py, ab_futureleak.py,
# cmp_oos_vectors.py) + engine/hybride_base.py. Commit base 9ca87ce.
#
# Fix i18n numéros d'aide CHATBOT — complément 1.6.039 (Release 1.6.040, 02/06/2026).
# Le smoke staging 1.6.039 a révélé que le CHATBOT servait encore les ANCIENS organismes/
# numéros (PT « Linha Vida SOS Jogo 808 200 204 », NL « Gokkliniek 0800 35 777 »…) : 2 sources
# non couvertes par 1.6.039 (qui avait traité _GAMBLING_HELP, FAQ, footer/disclaimer .po, js_i18n).
# Source 6 — prompts Gemini chatbot EM `prompts/em/{en,es,pt,de,nl}/prompt_hybride_em.txt`
# (bloc [RESPONSIBLE GAMBLING] + FAQ « où trouver de l'aide », 2 lignes/langue, hard-codé,
# chargé brut par load_prompt_em → PAS lang-aware via dict). Source 7 — Phase A L3 (réponses
# DÉTERMINISTES avant Gemini, canal « j'ai besoin d'aide ») : `chat_detectors_em_guardrails.py`
# (ES/PT/DE/NL _ARGENT_L3_EM_*) + `chat_responses_em_en.py` (EN, retrait ncpgambling US non
# vérifié + ajout 0808 8020 133). FR (prompt + L3) déjà conforme, intact. Legacy EN aligné
# (prompts/chatbot/prompt_hybride_em_en.txt GambleAware→GamCare, mort-code runtime). Valeurs
# identiques au dict _GAMBLING_HELP. test_argent.py MAJ 6 assertions (begambleaware→gamcare,
# jugarbien→fejar, jogoresponsavel→sicad, bzga.de→check-dein-spiel.de, agog.nl→openovergokken).
# Approche : correction en dur (pas de centralisation prompts/L3 sur _GAMBLING_HELP = trop
# invasif pour hotfix → BACKLOG). 5779 tests passed. Re-smoke chatbot PT/NL à faire post-staging.
#
# Fix i18n numéros d'aide Jeu Responsable (Release 1.6.039, 01/06/2026) — hors sprint SEO.
# Bug pré-existant : le numéro/organisme d'aide au jeu était dupliqué et désynchronisé sur
# plusieurs sources (FAQ EM EN affichait le n° FR sous BeGambleAware ; PT/NL n° obsolètes).
# Numéros vérifiés double source officielle. Approche : (1) ROBUSTE — ajout de phone+phone_note
# à config/templates.py::_GAMBLING_HELP[lang] (numéro centralisé, fini le hard-code dans les
# msgid) + FAQ « Aide » (visible + JSON-LD) lit le dict ; (2) PRAGMATIQUE — correction des
# msgstr footer/disclaimer (.po) : EN url→gamcare, PT 808→1414 + Linha Vida + chamada gratuita,
# NL → Open Over Gokken 0800 24 000 22 ; (3) chatbot config/js_i18n.py org/url alignés (5 langs).
# Valeurs : FR Joueurs Info Service · EN GamCare/gamcare.org.uk/0808 8020 133 · ES FEJAR/fejar.org/
# 900 200 225 · PT Linha Vida (SICAD)/sicad.pt/1414 · DE BIÖG/check-dein-spiel.de/0800 1 372 700 ·
# NL Open Over Gokken/openovergokken.nl/0800 24 000 22. Vérif rendu 6 langues (FAQ+home+chatbot).
# BACKLOG : (1) templates légaux mentions-legales.html + disclaimer.html (annuaire multi-pays,
# audit contenu IE/BE/LU/AT/CH à valider) ; (2) centraliser js_i18n + légaux sur _GAMBLING_HELP.
#
# Sprint SEO P1c (Release 1.6.038, 01/06/2026) — FAQ EM étoffée (QW12, parité Loto ~30 Q).
# Source : docs/AUDIT_SEO_360_2026-05-30.md. FAQ EuroMillions (ui/templates/em/faq.html)
# passée de 13 (JSON-LD) / 15 (visible) désynchronisées à 33 Q cohérentes visible == JSON-LD.
# +16 nouvelles Q (équivalents Loto adaptés EM + longue traîne SEO : IA Grounded, IA prédire,
# moteur HYBRIDE 5+2, modes, indice convergence, combien tirages, chatbot, vs assistant
# généraliste, RGPD, site de jeu, en retard, numéros/étoiles les plus tirés, historique,
# multi-pays, écart) + fusion du doublon chaud/froid. Resync : 3 Q paires → visible (réutil.
# msgid), 5 Q visible-only → JSON-LD via striptags-reuse (zéro nouvelle traduction). 34 nouveaux
# msgid (17 Q + 17 R) traduits 6 langues (qualité éditoriale, style maison, wording ANJ strict :
# recadrage prédiction/site de jeu/en retard/numéros tirés, zéro promesse de gain). Édition .po
# ciblée par bloc + recompile 6 .mo. Rendu vérifié TestClient 6 langues (visible == JSON-LD == 33,
# zéro fuite FR). Aucun backend Python/JS.
#
# Sprint SEO P1b (Release 1.6.037, 01/06/2026) — Meta descriptions EM hors plage (QW3 volet EM).
# Source : docs/AUDIT_SEO_360_2026-05-30.md. Recalage des descriptions EM live (templates
# Jinja gettext) dans la plage SEO 120-160 codepoints. 5 pages hors-plage en FR (l'audit
# n'en citait que 3 : accueil 200, news 186, historique 105 ; détectés en plus : paires 180,
# hybride 184) → réécriture du msgid source + 6 traductions de qualité (FR/EN/ES/PT/DE/NL,
# style maison, zéro promesse de gain ANJ). + Tier2 statistiques EN (106→128, msgstr seul).
# 3 outliers DE marginaux (a-propos/euromillions-ia/simulateur >160) → backlog. Édition .po
# ciblée par bloc (diff propre, msgid/msgstr en ligne unique) + recompile 6 .mo. Rendu vérifié
# TestClient 36 cellules (6 pages × 6 langues) toutes ∈[120-160], zéro fuite FR. 18 fichiers
# (5 templates + 6 .po + 5 .mo + version). Aucun backend Python/JS.
#
# Sprint SEO P1a (Release 1.6.036, 01/06/2026) — Breadcrumb visible (QW4 + QW9).
# Source : docs/AUDIT_SEO_360_2026-05-30.md. Fil d'Ariane HTML visible aligné sur le
# BreadcrumbList JSON-LD existant. 12 pages Loto FR statiques (insertion <nav breadcrumb>
# après engine-nav + CSS inline avant </head>) + 12 templates EM Jinja (bloc {% block
# breadcrumb %} surchargeant em/_base.html, labels réutilisant les msgid gettext déjà
# traduits) + CSS inline dans em/_base.html. Style : barre couleur nav (sombre 2 thèmes).
# QW9 : pas de breadcrumb sur les 2 homes (Loto /accueil + EM home) = racines. paires.html
# JSON-LD normalisé « Loto » → « Loto France ». 1 seul msgid i18n nouveau : "Fil d'Ariane"
# (aria-label) traduit 6 langues + .mo recompilés. historique.html (Loto statique, legacy
# light sans design system) EXCLU → chantier réalignement séparé. Aucun backend Python/JS.
#
# Sprint SEO Commit 1 (Release 1.6.035, 01/06/2026) — Quick wins SEO Loto FR statique.
# Source : docs/AUDIT_SEO_360_2026-05-30.md. Périmètre 100% frontend, zéro i18n :
# QW1 lien "Paires" (/loto/paires) ajouté au footer Loto partagé (18 pages statiques).
# QW2 6 titres <title> Loto FR ramenés <=60 car. (numeros-les-plus-sortis, news, loto-ia,
# historique, paires, simulateur) en préservant les mots-clés. QW3 meta description paires.html
# recalée 120-160 (170→136 car.). QW5 2 <img> accueil (mascotte PNG + héros JPG) passées en
# <picture> + <source webp> (og-image.webp / hybride-chatbot-lotoia.webp déjà sur disque,
# gain LCP, anti-CLS width/height préservés). Balises meta og:image NON touchées (restent JPG
# pour crawlers sociaux). QW8 rayé = faux positif (résidus "Analyse" uniquement dans fichiers
# legacy non servis ; pages EN live via gettext OK). Descriptions EM live (templates/em) =
# backlog commit i18n dédié (impact 6 langues). Aucun changement Python/JS backend.
#
# V142.F (Release 1.6.034, 26/05/2026) — Fix bug d'ancrage temporel du chatbot.
# Diagnostic READ-ONLY 2026-05-26. Cause A (Loto + EM) : le chemin Gemini
# générique n'injectait aucune date courante dans le system_prompt → le modèle
# hallucinait la date (« 9 février 2026 », « 10 mai 2026 », bloc « Date:/Jour: »
# fabriqué, jour↔date incohérent). Fix : helper _build_temporal_anchor()
# (services/chat_pipeline_shared.py) injecte la date réelle dynamique
# (date.today() + _JOURS_FR + _format_date_fr) dans le system_prompt, bloc balisé
# "NE JAMAIS AFFICHER" (anti-fuite). Cause B (Loto) : dates en dur des exemples
# prompts/chatbot/prompt_hybride.txt (L309/333/447/619) → placeholders descriptifs.
# Prompts EM (mêmes dates) = backlog i18n séparé (Cause A les neutralise).
#
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
APP_VERSION = "1.6.044"
APP_NAME = "LotoIA"
VERSION_DATE = "2026-06-08"

# Sitemap lastmod — auto-generated at import time (= deploy time on Cloud Run).
# Override via DEPLOY_DATE env var in CI/CD if needed.
LAST_DEPLOY_DATE = os.getenv("DEPLOY_DATE", date.today().isoformat())

# Alias pour compatibilité avec engine/version.py
__version__ = APP_VERSION
