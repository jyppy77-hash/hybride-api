# CLAUDE.md — LotoIA HYBRIDE-API

> Auto-loaded by Claude Code at session start. Source of truth for project context.
> Last updated: 27/04/2026 (V133)

---

## Project Identity

- **Name**: LotoIA (lotoia.fr) — Statistical analysis platform for French Loto & EuroMillions
- **Stack**: FastAPI / Python 3.13 / MariaDB (Cloud SQL) / Vertex AI Gemini 2.5 Flash (google-genai SDK) / GCP Cloud Run (europe-west1)
- **Version**: V133.A — Release 1.6.021
- **Tests**: 5236 (129 files, coverage 78%)
- **Languages**: 6 (FR, EN, ES, PT, DE, NL) — all active
- **EuroMillions**: LIVE since 15/03/2026 (EM_PUBLIC_ACCESS=true)
- **Owner**: Jyppy (Jean-Philippe Godard), solo developer, auto-entrepreneur EmovisIA

---

## Critical Rules

### Workflow obligatoire
1. **Analyse** — lire les fichiers concernés
2. **Proposition AVANT/APRÈS** — montrer les changements
3. **Validation** — attendre le feu vert de Jyppy
4. **Livraison fichier complet** — MD5 + line count. JAMAIS de snippets.

### Interdictions absolues
- **JAMAIS de push** sans "feu vert" explicite de Jyppy
- **JAMAIS `--set-env-vars`** en Cloud Run → toujours `--update-env-vars`
- **JAMAIS de snippets** → toujours livrer le fichier complet
- **JAMAIS suggérer de dormir/arrêter/faire une pause** — Jyppy décide quand il s'arrête

### En fin de session
- Fournir un **récap de session** (tableau des fichiers modifiés, diagnostic, résolution)
- Mettre à jour `docs/MEMORY.md` et `docs/PROJECT_OVERVIEW.md` (gitignored)

---

## Commands

```bash
# Dev local (Windows)
py -3 -m uvicorn main:app --port 8099 --reload

# Tests
py -3 -m pytest tests/ -x -q
py -3 -m pytest tests/ -x -q --tb=line --no-header  # compact
py -3 -m pytest tests/test_specific.py -x -q         # single file

# Linter
py -3 -m ruff check .
py -3 -m ruff check --select F401 services/          # specific rule

# Deploy staging (manual submit)
gcloud builds submit --config=cloudbuild-staging.yaml --substitutions=_OWNER_IP="86.212.92.243",_OWNER_IPV6="2a01:cb05:8700:5900:"

# Deploy prod (trigger automatique via git push — NE PAS utiliser gcloud builds submit)
git push
# Le trigger Cloud Build prod se déclenche automatiquement sur git push
# $COMMIT_SHA est rempli automatiquement par le trigger (vide en submit manuel → build fail)
```

---

## Architecture Overview

```
hybride-api/
├── main.py                    # FastAPI orchestrator (~967L, 19 middlewares, 23 routers)
├── db_cloudsql.py             # aiomysql async pool (426L, auto-reconnect, pool_recycle 1800s)
├── config/                    # Games, killswitch, i18n, sponsors, bot IPs, version
├── routes/                    # 23 routers (launcher, pages, API data/analyse/chat, admin, sitemap)
├── services/                  # 42 modules (~14929L) — chatbot pipeline, AI, SQL, stats, PDF, cache
├── engine/                    # HYBRIDE engine (base class config-driven, Loto/EM wrappers, stats)
├── prompts/                   # Gemini prompts — Loto FR + EM 6 langs (115 files)
├── ui/                        # HTML pages, Jinja2 templates, static assets (JS/CSS)
├── tests/                     # 97 files pytest (4033+ tests)
├── translations/              # Babel/gettext i18n (749 entries × 6 langs, 0 empty/0 fuzzy)
├── migrations/                # MySQL migrations (001-022)
├── cloudbuild.yaml            # CI/CD: ruff → pytest --cov → deploy
└── cloudbuild-staging.yaml    # Staging deploy
```

---

## Chatbot HYBRIDE — 18 Phases Pipeline

```
Phase I          : Insult detection (L1-L4 escalation, 6 langs)
Phase C          : Compliment detection (L1-L3, 6 langs)
Phase R          : Site rating intent
Phase SALUTATION : Greeting short-circuit (history ≤ 1, < 8 words)
Phase G          : Grid generation (co-occ exclusion, decay V79)
Phase A          : Argent/money/gambling (L1-L3, helplines, euro game guard)
Phase GEO        : Country detection EM only (9 pays × 6 langs)
Phase 0          : Continuation mode (fuzzy + digit guard)
Phase AFFIRMATION: Simple affirmation (6 langs)
Phase GAME_KW    : Game keyword alone
Phase EVAL       : User grid evaluation
Phase 0-bis      : Next draw detection
Phase T          : Temporal/specific draw query
Phase 2          : Submitted grid detection
Phase 3          : Complex query (classement, comparaison, catégorie)
Phase 3-bis      : Temporal comparison (progression %)
Phase P+/P       : Co-occurrence / Pairs+Triplets
Phase OOR        : Out-of-range (L1-L3, 6 langs)
Phase 1          : Single number → enrichment
Phase SQL        : Text-to-SQL (Gemini → validate → execute, 7 defense layers)
→ Gemini         : Final response (streaming SSE)
```

Key files: `chat_pipeline_shared.py` (1301L orchestrator), `chat_pipeline.py` (Loto config), `chat_pipeline_em.py` (EM config).

---

## Engine HYBRIDE

- **Base class**: `engine/hybride_base.py` (~989L, config-driven)
- **Config**: `config/engine.py` (frozen dataclass, 188L)
- **Features V80**: noise gaussian, wildcard froid, z-score penalization, hard-reject 0/5-pairs, decay state
- **3 modes**: conservative, balanced, recent
- **Score**: ~9.8/10 after V80 audit

---

## Key Conventions

### Code
- `_UPPERCASE` for compiled regex and response pools
- `_detect_X()` for detectors, `_get_X_response()` for formatters
- Typing: `-> bool`, `-> str`, `-> dict | None`
- Line length: 120 (ruff config)
- Target: Python 3.13

### Tests
- Pattern `_get_client()` with patches StaticFiles + DB env vars
- No DB mocks in integration tests
- `pytest.ini` for coverage config
- Test naming: `test_<feature>_<scenario>`

### Prompts
- Loto: `load_prompt()` via `PROMPT_MAP` dict
- EM: `load_prompt_em(name, lang)` file-based, LRU cache, fallback [lang→en→fr]
- Internal tags always in French (code-matched)
- `[RAPPEL CRITIQUE]` anti-re-introduction injected unconditionally

### i18n
- Verify visually in local for EACH language (curl or browser), not just pytest
- gettext msgid must match exactly (character by character, punctuation included)
- Test all 6 languages (FR/EN/ES/PT/DE/NL) locally and report "ZERO FR string visible" per language

---

## Admin Back-Office

- **Route**: `/admin` (OWNER_IP restriction)
- **UI**: Glassmorphism dark mode
- **Pages**: dashboard, impressions, votes, engagement, realtime, monitoring, sponsors CRUD, factures CRUD, contrats CRUD, config, messages, tarifs
- **Tarifs V9**: mono-annonceur LOTOIA_EXCLU 650€/mois, 5 emplacements, pool 10K impressions
- **Config EI**: masquage RCS/Capital si EI, TVA 0% franchise 293B

---

## Sponsor System

- **Model**: mono-annonceur exclusif LOTOIA_EXCLU
- **Price**: 650€/mois (plancher négo 500€)
- **Paliers**: Lancement 0-10K gel, Croissance 10-40K 815€, Traction 40-100K 1020€
- **Engagement**: 3 mois min, 6 mois -10%
- **Pipeline**: grille → contrat → onboarding → tracking → facturation

---

## Database

- **Main**: `lotofrance` (Cloud SQL MariaDB)
- **Tables draws**: `tirages` (Loto), `tirages_euromillions` (EM)
- **Chatbot SQL**: readonly pool dedicated, ALLOWED_TABLES whitelist
- **Pools**: main (read-write) + readonly (chatbot SQL, fallback to main with logger.error)

---

## Deploy

- **Prod**: Cloud Run `hybride-api-eu` (europe-west1, min=1, max=10, 1Gi, 2 workers)
- **Staging**: Cloud Run `hybride-api-staging` (min=0, max=3, 512Mi, DB=lotofrance_staging)
- **CI/CD**: cloudbuild.yaml — ruff → pytest (--cov-fail-under=70) → build → deploy
- **Prod deploy**: via `git push` → trigger Cloud Build automatique (NE PAS utiliser `gcloud builds submit` pour la prod — `$COMMIT_SHA` vide en submit manuel)
- **Staging deploy**: via `gcloud builds submit --config=cloudbuild-staging.yaml` (submit manuel OK)
- **Registry**: Artifact Registry (migrated from gcr.io V49)
- **Costs**: GCP ~90€/month (Google for Startups credits)

---

## Roadmap Context

1. **EmovisIA 2.0** — Priority #1 (UX/UI Awwwards → backend PHP→FastAPI → Stripe/CRM → chat)
2. **Sprint SEO V85** — 13 failles corrigées (score 9.0→9.8/10), admin.js fix
3. **FAQ Phase 2+3** — translation 5 languages
4. **Sponsor contracts** — outreach 4 FR sponsors
5. **Business plan**: Phase 1 (EI, 4 FR sponsors) → Phase 2 (SASU) → Phase 3 (9 EU countries, neobanks)

---

## Known Pre-existing Bugs

- **contact-form.js/css manquants sur pages Loto FR** — le lien "Nous contacter" (footer) appelle `LotoIAContact.openModal()` mais les scripts ne sont jamais chargés. Guard `if(window.LotoIAContact)` empêche l'erreur JS mais le modal ne s'ouvre pas. À corriger.
- **Chevauchement CSS chatbot bubble / scroll-to-top** — les éléments `position: fixed` (bulle chatbot, bouton scroll) peuvent capturer des clicks destinés aux liens de navigation en dessous (z-index). À investiguer.

---

## Reference Documents

- `docs/MEMORY.md` — Full project memory (gitignored, updated at session end)
- `docs/PROJECT_OVERVIEW.md` — Technical overview 1780L (gitignored, updated at session end)
- `docs/Prompt AUDIT/` — Library of 7 specialized audit prompts
- `docs/AUDIT_360_CHATBOT_HYBRIDE.md` — Latest chatbot audit report
