# LotoIA - Technical Overview

> Statistical analysis platform for the French Loto and EuroMillions, powered by the HYBRIDE engine.

---

## 1. Project Tree

```
hybride-api/
│
├── main.py                              # FastAPI orchestrator (~660L, 12 middlewares, 16 routers)
├── schemas.py                           # Pydantic models — Loto API payloads
├── em_schemas.py                        # Pydantic models — EuroMillions API payloads
├── db_cloudsql.py                       # aiomysql async pool manager (259L, Phase 5)
├── rate_limit.py                        # Shared slowapi rate limiter
├── test_db.py                           # Database connectivity test
├── requirements.txt                     # Python dependencies
├── pytest.ini                           # Pytest configuration (coverage)
├── Dockerfile                           # Container image (2 workers)
├── cloudbuild.yaml                      # Cloud Build: Build → Test → Deploy
├── BingSiteAuth.xml                     # Bing Webmaster verification
├── favicon.ico                          # Root favicon
├── .gitignore                           # Git ignore rules
├── .dockerignore                        # Docker build exclusions
├── seo.py                               # SEO helpers (JSON-LD structured data)
├── .env                                 # Local environment variables (excluded from git+Docker)
├── requirements-dev.txt                 # Dev/test dependencies (pytest, pytest-asyncio, pytest-cov)
├── SEO_CHECKLIST.md                     # SEO audit checklist
├── SEO_SNIPPETS.md                      # SEO code snippets reference
├── SEO_STRATEGY.md                      # SEO strategy document
│
├── routes/                              # API & page routers (APIRouter)
│   ├── __init__.py                      # Package init
│   ├── pages.py                         # 23 HTML page routes (SEO clean URLs)
│   ├── api_data_unified.py              # Unified data endpoints /api/{game}/... (Phase 10, ~400L)
│   ├── api_analyse_unified.py           # Unified analysis endpoints /api/{game}/... (Phase 10, ~720L)
│   ├── api_chat_unified.py              # Unified chat endpoints /api/{game}/... (Phase 10, ~70L)
│   ├── api_data.py                      # Loto data — thin wrapper → api_data_unified (Phase 10)
│   ├── api_analyse.py                   # Loto analysis — thin wrapper + /ask (Phase 10)
│   ├── api_gemini.py                    # Gemini AI text enrichment endpoint
│   ├── api_pdf.py                       # PDF generation endpoint (ReportLab)
│   ├── api_tracking.py                  # Analytics tracking endpoints (grid, ads)
│   ├── api_ratings.py                   # User rating endpoints (submit, global stats)
│   ├── api_chat.py                      # HYBRIDE chatbot Loto — thin wrapper + re-exports (Phase 10)
│   ├── api_chat_em.py                   # HYBRIDE chatbot EM — thin wrapper + re-exports (Phase 10)
│   ├── em_data.py                       # EM data — thin wrapper → api_data_unified (Phase 10)
│   ├── em_analyse.py                    # EM analysis — thin wrapper + /meta-analyse-texte, /meta-pdf (Phase 10)
│   ├── em_pages.py                      # EuroMillions HTML page routes (7 SEO clean URLs)
│   └── en_em_pages.py                   # EuroMillions EN page routes (7 SEO clean URLs, Phase 11)
│
├── services/                            # Business logic layer (21 modules, ~6200L)
│   ├── __init__.py                      # Package init
│   ├── base_stats.py                    # GameConfig-driven base class Loto/EM (770L, Phase 2)
│   ├── stats_service.py                 # Loto stats thin wrapper → base_stats (121L, Phase 2)
│   ├── em_stats_service.py              # EM stats thin wrapper → base_stats (87L, Phase 2)
│   ├── chat_pipeline.py                 # HYBRIDE chatbot orchestration — Loto (639L, Phase 1)
│   ├── chat_pipeline_em.py              # HYBRIDE chatbot orchestration — EM (653L, Phase 4)
│   ├── chat_detectors.py                # 12-phase detection: insults, numbers, grids — Loto (850L, Phase 1)
│   ├── chat_detectors_em.py             # 12-phase detection — EM variant (495L, Phase 4)
│   ├── chat_sql.py                      # Text-to-SQL generator + executor — Loto (247L, Phase 1)
│   ├── chat_sql_em.py                   # Text-to-SQL generator — EM (176L, Phase 4)
│   ├── chat_utils.py                    # Formatting, context, sponsor — Loto (396L, Phase 1)
│   ├── chat_utils_em.py                 # Formatting, context — EM (200L, Phase 4)
│   ├── cache.py                         # Redis async cache + in-memory fallback (116L, Phase 6)
│   ├── circuit_breaker.py               # Gemini circuit breaker (84L, 3 fails → 60s open)
│   ├── gemini.py                        # Gemini 2.0 Flash API client — Loto (130L)
│   ├── em_gemini.py                     # Gemini 2.0 Flash API client — EM (122L)
│   ├── pdf_generator.py                 # ReportLab PDF — Loto (361L, single graph)
│   ├── em_pdf_generator.py              # ReportLab PDF — EM (364L, dual graphs boules+etoiles)
│   ├── chat_responses_em_en.py          # English response pools for EM chatbot (Phase 11)
│   ├── penalization.py                  # Number penalization logic (65L)
│   └── prompt_loader.py                 # Dynamic prompt loader (101L, 36 keys: 18 Loto + 18 EM)
│
├── engine/                              # Core analysis engine
│   ├── __init__.py                      # Package init
│   ├── hybride.py                       # HYBRIDE algorithm (Loto)
│   ├── hybride_em.py                    # HYBRIDE algorithm (EuroMillions)
│   ├── stats.py                         # Statistical analysis module
│   ├── models.py                        # Pydantic data models
│   ├── db.py                            # Database connection proxy
│   └── version.py                       # Version constant (1.0.0)
│
├── prompts/                             # Gemini contextual prompts (38 files)
│   ├── prompt_hybride.txt               # Legacy HYBRIDE prompt (root level)
│   ├── chatbot/                         # HYBRIDE chatbot prompts
│   │   ├── prompt_hybride.txt           # Multi-section prompt — Loto (identity, FAQ, rules, BDD)
│   │   ├── prompt_pitch_grille.txt      # Pitch prompt — Loto (personalized grid commentary)
│   │   ├── prompt_sql_generator.txt     # SQL Generator prompt — Loto (Text-to-SQL, schema, few-shot examples)
│   │   ├── prompt_hybride_em.txt        # Multi-section prompt — EuroMillions (identity, FAQ, rules, BDD)
│   │   ├── prompt_pitch_grille_em.txt   # Pitch prompt — EuroMillions (5 nums + 2 étoiles commentary)
│   │   ├── prompt_sql_generator_em.txt  # SQL Generator prompt — EuroMillions (tirages_euromillions schema)
│   │   ├── prompt_hybride_em_en.txt     # Multi-section prompt — EM English (Phase 11)
│   │   ├── prompt_pitch_grille_em_en.txt # Pitch prompt — EM English (Phase 11)
│   │   └── prompt_sql_generator_em_en.txt # SQL Generator prompt — EM English (Phase 11)
│   ├── tirages/                         # Window-based prompts — Loto (by draw count)
│   │   ├── prompt_100.txt               # Prompt for 100-draw window
│   │   ├── prompt_200.txt               # Prompt for 200-draw window
│   │   ├── prompt_300.txt               # Prompt for 300-draw window
│   │   ├── prompt_400.txt               # Prompt for 400-draw window
│   │   ├── prompt_500.txt               # Prompt for 500-draw window
│   │   ├── prompt_600.txt               # Prompt for 600-draw window
│   │   ├── prompt_700.txt               # Prompt for 700-draw window
│   │   ├── prompt_800.txt               # Prompt for 800-draw window
│   │   └── prompt_global.txt            # Prompt for GLOBAL window (fallback)
│   ├── annees/                          # Year-based prompts — Loto
│   │   ├── prompt_1a.txt                # Prompt for 1-year window
│   │   ├── prompt_2a.txt                # Prompt for 2-year window
│   │   ├── prompt_3a.txt                # Prompt for 3-year window
│   │   ├── prompt_4a.txt                # Prompt for 4-year window
│   │   ├── prompt_5a.txt                # Prompt for 5-year window
│   │   ├── prompt_6a.txt                # Prompt for 6-year window
│   │   └── prompt_global.txt            # Prompt for GLOBAL window (annees fallback)
│   └── euromillions/                    # EuroMillions META ANALYSE prompts (15 files)
│       ├── tirages/                     # Window-based prompts — EM (100-700 + GLOBAL, no 800)
│       │   ├── prompt_100.txt           # EM 100-draw window (court terme)
│       │   ├── prompt_200.txt           # EM 200-draw window (court-moyen terme)
│       │   ├── prompt_300.txt           # EM 300-draw window (moyen terme)
│       │   ├── prompt_400.txt           # EM 400-draw window (moyen-long terme)
│       │   ├── prompt_500.txt           # EM 500-draw window (long terme)
│       │   ├── prompt_600.txt           # EM 600-draw window (long terme etendu)
│       │   ├── prompt_700.txt           # EM 700-draw window (quasi-integralite)
│       │   └── prompt_global.txt        # EM GLOBAL window (fallback EM)
│       └── annees/                      # Year-based prompts — EM
│           ├── prompt_1a.txt            # EM 1-year window
│           ├── prompt_2a.txt            # EM 2-year window
│           ├── prompt_3a.txt            # EM 3-year window
│           ├── prompt_4a.txt            # EM 4-year window
│           ├── prompt_5a.txt            # EM 5-year window
│           ├── prompt_6a.txt            # EM 6-year window
│           └── prompt_global.txt        # EM GLOBAL window (annees fallback EM)
│
├── ui/                                  # Frontend layer
│   ├── launcher.html                    # Entry page (route: /)
│   ├── index.html                       # Backup entry point
│   ├── accueil.html                     # Welcome page (/accueil)
│   ├── loto.html                        # Grid generator (/loto)
│   ├── loto-ia.html                     # IA pillar page (/loto/intelligence-artificielle)
│   ├── numeros-les-plus-sortis.html     # Top numbers page (/loto/numeros-les-plus-sortis)
│   ├── simulateur.html                  # Grid simulator (/loto/analyse)
│   ├── statistiques.html                # Statistics dashboard (/loto/statistiques)
│   ├── historique.html                  # Draw history (/historique)
│   ├── faq.html                         # FAQ (/faq)
│   ├── news.html                        # News & updates (/news)
│   ├── moteur.html                      # Engine documentation (/moteur)
│   ├── methodologie.html                # Methodology docs (/methodologie)
│   ├── hybride.html                     # HYBRIDE chatbot page (/hybride)
│   ├── a-propos.html                    # About page — E-E-A-T (/a-propos)
│   ├── 404.html                         # Custom 404 error page
│   ├── disclaimer.html                  # Legal disclaimer (/disclaimer)
│   ├── mentions-legales.html            # Legal notices (/mentions-legales)
│   ├── politique-confidentialite.html   # Privacy policy
│   ├── politique-cookies.html           # Cookie policy
│   ├── robots.txt                       # Search engine directives
│   ├── sitemap.xml                      # XML sitemap
│   ├── site.webmanifest                 # PWA manifest
│   ├── favicon.svg                      # SVG favicon
│   ├── favicon-simple.svg               # Simplified SVG favicon
│   │
│   ├── em/                              # EuroMillions HTML pages (FR)
│   │   ├── accueil-em.html              # EM welcome page (/euromillions/accueil)
│   │   ├── euromillions.html            # EM grid generator (/euromillions)
│   │   ├── simulateur-em.html           # EM grid simulator (/euromillions/simulateur)
│   │   ├── statistiques-em.html         # EM statistics dashboard (/euromillions/statistiques)
│   │   ├── historique-em.html           # EM draw history (/euromillions/historique)
│   │   ├── faq-em.html                  # EM FAQ (/euromillions/faq)
│   │   └── news-em.html                # EM news (/euromillions/news)
│   │
│   ├── en/                              # English (GB) pages (Phase 11)
│   │   └── euromillions/                # EuroMillions EN pages (7 pages)
│   │       ├── home.html                # EM EN home (/en/euromillions)
│   │       ├── generator.html           # EM EN generator (/en/euromillions/generator)
│   │       ├── simulator.html           # EM EN simulator (/en/euromillions/simulator)
│   │       ├── statistics.html          # EM EN statistics (/en/euromillions/statistics)
│   │       ├── history.html             # EM EN history (/en/euromillions/history)
│   │       ├── faq.html                 # EM EN FAQ (/en/euromillions/faq)
│   │       ├── news.html                # EM EN news (/en/euromillions/news)
│   │       └── static/                  # EN-specific JS files (6 translated modules)
│   │           ├── app-em-en.js          # EN application logic (months, dates, labels)
│   │           ├── simulateur-em-en.js   # EN simulator UI (convergence, details, history)
│   │           ├── sponsor-popup-em-en.js    # EN sponsor popup (config, console, labels)
│   │           ├── sponsor-popup75-em-en.js  # EN META ANALYSE popup (result, PDF, fallback)
│   │           ├── faq-em-en.js          # EN FAQ accordion (en-GB locale)
│   │           └── hybride-chatbot-em-en.js  # EN chatbot widget (hasSponsor EN, analytics)
│   │
│   └── static/                          # Static assets
│       ├── style.css                    # Main stylesheet (Loto)
│       ├── style-em.css                 # EuroMillions-specific stylesheet
│       ├── simulateur.css               # Simulator-specific styles
│       ├── legal.css                    # Legal pages styling
│       ├── sponsor-popup.css            # Sponsor popup styling
│       ├── sponsor-popup75.css          # META ANALYSE 75 popup styling
│       ├── meta-result.css              # META ANALYSE result popup styling
│       ├── hybride-chatbot.css          # HYBRIDE Chatbot widget styles
│       ├── rating-popup.css             # Rating popup styling
│       ├── app.js                       # Main application logic (Loto)
│       ├── app-em.js                    # EuroMillions application logic
│       ├── simulateur.js                # Simulator UI logic (Loto)
│       ├── simulateur-em.js             # Simulator UI logic (EuroMillions)
│       ├── sponsor-popup75.js           # META ANALYSE 75 popup — Loto (Gemini + PDF flow)
│       ├── sponsor-popup75-em.js        # META ANALYSE 75 popup — EuroMillions (dual graphs boules+etoiles, PDF flow)
│       ├── hybride-chatbot.js           # HYBRIDE Chatbot widget — Loto (IIFE, vanilla JS, sessionStorage, GA4 tracking)
│       ├── hybride-chatbot-em.js        # HYBRIDE Chatbot widget — EuroMillions (IIFE, /api/euromillions/hybride-chat, hybride-history-em)
│       ├── hybride-chatbot-em-en.js    # HYBRIDE Chatbot widget — EM English (Phase 11, EN sponsor detection, en-GB locale)
│       ├── theme.js                     # Dark/light mode toggle
│       ├── analytics.js                 # GDPR-compliant analytics
│       ├── cookie-consent.js            # Cookie consent management
│       ├── faq.js                       # FAQ accordion logic (Loto)
│       ├── faq-em.js                    # FAQ accordion logic (EuroMillions)
│       ├── scroll.js                    # Scroll-to-top button (all pages)
│       ├── nav-scroll.js                # Navigation scroll behavior
│       ├── version-inject.js            # Dynamic version injection from /api/version
│       ├── sponsor-popup.js             # Sponsor popup logic (grids)
│       ├── rating-popup.js              # Rating popup UI logic
│       ├── og-image.jpg                 # Open Graph image (1200x630)
│       ├── og-image.webp                # Open Graph image (WebP)
│       ├── hero-bg.jpg                  # Hero background image
│       ├── hero-bg.webp                 # Hero background (WebP)
│       ├── Hybride-audit.png            # HYBRIDE assistant image (simulator)
│       ├── Hybride-audit-horizontal.png # HYBRIDE assistant image (horizontal)
│       ├── hybride-chatbot-lotoia.jpg   # HYBRIDE chatbot branding (JPG)
│       ├── hybride-chatbot-lotoia.webp  # HYBRIDE chatbot branding (WebP)
│       ├── hybride-chatbot-lotoia.png   # HYBRIDE chatbot branding (PNG)
│       ├── hybride-moteur.png           # HYBRIDE mascot (generator page)
│       ├── hybride-stat.png             # HYBRIDE mascot (statistics page)
│       ├── favicon.ico                  # Favicon (static copy)
│       ├── favicon.svg                  # Favicon SVG (static copy)
│       ├── Sponsors_media/              # Sponsor media assets (videos)
│       └── em/                          # EuroMillions static sub-assets
│           ├── sponsor-popup-em.css     # EM sponsor popup styling
│           ├── sponsor-popup-em.js      # EM sponsor popup logic
│           └── sponsor-popup75-em.css   # EM META ANALYSE 75 popup styling
│
├── tests/                               # Unit tests (pytest) — 473 tests
│   ├── conftest.py                      # Shared fixtures (SmartMockCursor, cache clear)
│   ├── test_models.py                   # Pydantic models + CONFIG weights (10 tests)
│   ├── test_hybride.py                  # HYBRIDE engine tests (21 tests)
│   ├── test_stats.py                    # engine/stats.py tests (9 tests)
│   ├── test_services.py                 # cache + stats_service tests (11 tests)
│   ├── test_routes.py                   # FastAPI route tests (10 tests)
│   ├── test_circuit_breaker.py          # Circuit breaker tests (9 tests)
│   ├── test_insult_oor.py               # Insult detection + out-of-range number tests (141 tests)
│   ├── test_ratings.py                  # Rating system tests (27 tests)
│   ├── test_penalization.py             # Penalization logic tests (10 tests)
│   ├── test_unified_routes.py          # Unified /api/{game}/... route tests (17 tests, Phase 10)
│   └── test_en_routes.py              # EN EuroMillions route tests (18 tests, Phase 11)
│
├── config/                                # Runtime configuration
│   ├── __init__.py                      # Package init
│   ├── games.py                         # GameConfig registry — unified game definitions (Phase 10)
│   ├── languages.py                     # Language registry — LANG_CONFIGS, get_lang_config() (Phase 11)
│   ├── version.py                       # Centralized version constant (VERSION = "1.001")
│   └── sponsors.json                    # Sponsor system config (enabled, frequency, sponsors[])
│
├── migrations/                            # Database migrations (manual)
│   └── add_indexes.sql                  # Critical indexes (boule_1-5, date, chance)
│
├── data/
│   └── loto_db.sql                      # SQL dump (official FDJ Loto draws)
│
├── docs/bdd euromillions/
│   └── euromillions_import.sql           # SQL dump (729 EuroMillions draws, 2019-2026)
│
└── docs/                                # Documentation & audits
    ├── PROJECT_OVERVIEW.md              # This file
    ├── AUDIT_JURIDIQUE_old.md           # Legal audit (legacy)
    ├── RAPPORT D'AUDIT...md             # Independent audit (ManusAI)
    ├── Analyse de la Niche...md         # Niche analysis (ManusAI)
    └── *.pdf                            # External audit reports
```

---

## 2. Design Philosophy

The frontend is built entirely with vanilla JavaScript (ES5+), HTML5, and CSS3. There is no framework (React, Vue, Angular) and no build step (no Webpack, Vite, or Babel).

**Rationale:**

- **Performance** — No framework runtime overhead. Pages load with zero JS bundle parsing cost beyond the application scripts themselves.
- **Control** — Direct DOM manipulation without abstraction layers. Every interaction is explicit and traceable.
- **Minimal dependencies** — The chatbot widget (`hybride-chatbot.js`) is a self-contained IIFE with zero external imports. The same applies to all other JS modules.
- **Deployment simplicity** — Static files served directly by FastAPI. No node_modules, no build pipeline, no transpilation.

This approach trades developer convenience (no hot-reload, no component model) for a lighter, more predictable production artifact.

---

## 3. Key Features

### HYBRIDE Engine (Loto)

| Feature | Detail |
|---------|--------|
| **Dual Time Windows** | Primary (5 years, 60%) + Recent (2 years, 40%) |
| **Scoring Formula** | `Score = 0.7 * Frequency + 0.3 * Lag` |
| **Generation Modes** | Conservative (70/30), Balanced (60/40), Recent (40/60) |
| **Constraint Validation** | Even/Odd ratio, Low/High split, Sum range [70-150], Dispersion, Consecutive limit |
| **Star Rating** | 1-5 stars based on conformity score |
| **Badges** | Auto-generated labels (Equilibre, Chaud, Froid, etc.) |

### HYBRIDE Engine (EuroMillions)

| Feature | Detail |
|---------|--------|
| **Game** | EuroMillions — 5 boules [1-50] + 2 etoiles [1-12] |
| **Draw Days** | MARDI / VENDREDI |
| **Dual Time Windows** | Primary (5 years, 60%) + Recent (2 years, 40%) |
| **Scoring Formula** | `Score = 0.7 * Frequency + 0.3 * Lag` |
| **Constraint Validation** | Even/Odd ratio, Low/High split (seuil 25), Sum range [75-175], Dispersion, Consecutive limit |
| **Etoiles Generation** | 2 etoiles drawn from [1-12] without replacement (weighted random based on historical frequency) |
| **Star Rating** | 1-5 stars based on conformity score |
| **Badges** | Auto-generated labels (Equilibre, Chaud, Froid, etc.) |
| **Table** | `tirages_euromillions` (same DB `lotofrance`) |
| **Cache** | All keys prefixed `em:` to avoid collision with Loto |
| **Router** | Unified `/api/{game}/` (Phase 10) + backward compat `/api/euromillions/` prefix |

### META ANALYSE 75 Module (Loto)

| Feature | Detail |
|---------|--------|
| **Local Analysis** | Real-time stats computed on Cloud SQL (< 300ms) |
| **Window Modes** | By draw count (100-800, GLOBAL) or by years (1A-6A, GLOBAL) |
| **Gemini AI Enrichment** | Text reformulation via Gemini 2.0 Flash API (`enrich_analysis`) |
| **Dynamic Prompts** | 18 Loto keys in PROMPT_MAP (9 tirages + 6 annees + 3 chatbot) |
| **PDF Export** | Professional META75 report via ReportLab (A4, single graph) |
| **Sponsor Popup** | 30-second branded timer with animated console (`sponsor-popup75.js`) |
| **Race Condition Handling** | Promise.race with 28s global timeout from T=0 |

### META ANALYSE 75 Module (EuroMillions)

| Feature | Detail |
|---------|--------|
| **Local Analysis** | Real-time EM stats computed on Cloud SQL (boules 1-50 + etoiles 1-12) |
| **Window Modes** | By draw count (100-700, GLOBAL — no 800, only 729 draws) or by years (1A-6A, GLOBAL) |
| **Gemini AI Enrichment** | Text reformulation via Gemini 2.0 Flash API (`enrich_analysis_em`) |
| **Dynamic Prompts** | 14 EM keys in PROMPT_MAP (8 tirages + 7 annees, all prefixed `EM_`) |
| **PDF Export** | Professional META75 EM report via ReportLab (A4, dual graphs: boules bar+pie + etoiles bar+pie) |
| **Dual Graph Architecture** | `graph_data_boules` + `graph_data_etoiles` flow from local stats → frontend → PDF |
| **Sponsor Popup** | 30-second branded timer with animated console (`sponsor-popup75-em.js`) |
| **Race Condition Handling** | Promise.race with 28s global timeout from T=0 |
| **Frontend** | `sponsor-popup75-em.js` (~620 lines): `triggerGeminiEarlyEM()`, `showSponsorPopup75EM()`, `openMetaResultPopupEM()` |

### Statistics System

- Number-level analysis: frequency, first/last appearance, current gap
- Global stats: total draws, date range, average frequency
- Top/Flop rankings by frequency
- Heat classification: Hot (top 33%), Cold (bottom 33%), Neutral

### HYBRIDE Chatbot Widget (Loto)

| Feature | Detail |
|---------|--------|
| **Architecture** | Standalone IIFE (vanilla JS, ES5+), zero dependencies |
| **Auto-init** | Targets `#hybride-chatbot-root`, guard via `data-hybride-init` attribute |
| **Pages** | Integrated on 6 Loto pages: accueil, loto, simulateur, statistiques, news, faq |
| **UI** | Floating bubble (fixed, bottom-right) + chat window with header/messages/input |
| **Session persistence** | `chatHistory` saved in `sessionStorage` (max 50 messages). Survives navigation between pages. Cleared on tab close. |
| **History restore** | On init: restore from sessionStorage → re-render all bubbles. If no history: show welcome message. |
| **Clear button** | 🗑️ button in header (next to ✕). Clears history, sessionStorage, DOM. Re-shows welcome. |
| **Mobile** | Fullscreen chat via `.hybride-fullscreen` class toggle (only when open) |
| **Android keyboard** | `visualViewport` API sync + `--vvp-height` CSS variable + `interactive-widget=resizes-content` |
| **Typing indicator** | Animated 3-dot bounce |
| **Responses** | Gemini 2.0 Flash via `/api/hybride-chat` (multi-turn, system_instruction, 15s timeout, fallback) |
| **Sponsor system** | Post-Gemini injection via `_get_sponsor_if_due()`. Alternates style A (natural) / style B (banner) every N responses. Config in `config/sponsors.json`. Does not pollute conversational history. |
| **GA4 tracking** | 5 custom events via `LotoIAAnalytics.track()`: `hybride_chat_open` (page, has_history), `hybride_chat_message` (message_length, message_count), `hybride_chat_session` (duration, sponsor_views, message_count), `hybride_chat_sponsor_view` (sponsor_style A/B, message_position), `hybride_chat_clear` (message_count). Safe wrapper: analytics errors never break chat. |
| **History** | Last 20 messages sent as context (chatHistory array, trimmed by frontend) |
| **Page-aware** | `detectPage()` sends current page context to API for adapted tone |
| **z-index stack** | Bubble: 9999, Window: 9998, Mobile fullscreen: 10000, Cookie banner: 10001 |
| **Theme** | Dark palette aligned with LotoIA (navy `#0f172a`, blue `#1a73e8`) |

### HYBRIDE Chatbot Widget (EuroMillions)

| Feature | Detail |
|---------|--------|
| **Architecture** | Standalone IIFE (`hybride-chatbot-em.js`, vanilla JS, ES5+), zero dependencies |
| **Auto-init** | Same `#hybride-chatbot-root` div, guard via `data-hybride-init` attribute |
| **Pages** | Integrated on 7 EM pages: accueil-em, euromillions, simulateur-em, statistiques-em, historique-em, faq-em, news-em |
| **CSS** | Shared `hybride-chatbot.css` (same dark-mode palette) |
| **Endpoint** | `/api/euromillions/hybride-chat` (POST) |
| **Storage** | `hybride-history-em` (sessionStorage, isolated from Loto's `hybride-history`) |
| **Header** | `HYBRIDE — EuroMillions` |
| **Welcome** | `...assistant IA de LotoIA — module EuroMillions...` |
| **detectPage()** | accueil-em, euromillions, simulateur-em, statistiques-em, historique-em, faq-em, news-em |
| **Typing ID** | `hybride-typing-indicator-em` (no conflict with Loto widget) |
| **GA4 events** | Prefixed `hybride_em_chat_*` (open, message, session, sponsor_view, clear, error) |
| **Backend** | `api_chat_em.py` (thin wrapper) → `services/chat_pipeline_em.py`: 12-phase detection pipeline adapted for EuroMillions (boules 1-50, 2 étoiles 1-12, table tirages_euromillions, draw days mardi/vendredi) |
| **Prompts** | 3 dedicated EM prompts: `prompt_hybride_em.txt`, `prompt_sql_generator_em.txt`, `prompt_pitch_grille_em.txt` |
| **Pitch** | `POST /api/euromillions/pitch-grilles` (1-5 grids, JSON pitchs with étoiles support) |
| **Imports** | Generic utilities imported from `api_chat.py` (continuation, sponsor, insult/compliment detection, SQL validation, clean_response, format_date_fr, temporal filter). EM-specific functions and response pools defined locally. |
| **i18n (Phase 11)** | EN support via `lang` parameter: EN response pools (`chat_responses_em_en.py`), EN chatbot prompts (`prompt_hybride_em_en.txt`), EN sponsor text (`_get_sponsor_if_due(history, lang="en")`). Frontend widget: `hybride-chatbot-em-en.js` with EN sponsor detection. |

### HYBRIDE BDD Integration (Chatbot ↔ Live Database)

The chatbot is connected to Cloud SQL in real-time via a multi-phase detection pipeline:

| Phase | Detection | Data Source | Example Query |
|-------|-----------|-------------|---------------|
| **Phase 0 — Continuation** | Regex `_is_short_continuation()` | `_enrich_with_context()` (history) | "oui", "non", "vas-y", "détaille", "continue" |
| **Phase 0-bis — Next Draw** | Regex `_detect_prochain_tirage()` | `_get_prochain_tirage()` | "c'est quand le prochain tirage ?" |
| **Phase T — Draw Results** | Regex `_detect_tirage()` | `_get_tirage_data()` | "dernier tirage", "les numéros d'hier" |
| **Phase 2 — Grid Analysis** | Regex `_detect_grille()` (5 nums) | `analyze_grille_for_chat()` | "analyse 8 24 25 32 46 + 3" |
| **Phase 3 — Complex Queries** | Regex `_detect_requete_complexe()` | `get_classement_numeros()`, `get_comparaison_numeros()`, `get_numeros_par_categorie()` | "top 10 les plus fréquents", "compare le 7 et le 23" |
| **Phase 1 — Single Number** | Regex `_detect_numero()` | `get_numero_stats()` | "le 9 est sorti combien de fois ?" |
| **Phase SQL — Text-to-SQL** | Gemini SQL generation | `_generate_sql()` → `_execute_safe_sql()` | "combien de fois le 22 en 2025 ?", "quel numéro a le plus grand écart ?" |

**Detection priority**: Continuation → Next Draw → Draw Results → [Temporal filter check] → Grid → Complex → Single Number → Text-to-SQL

**Contextual continuation (Phase 0)**: Short replies ("oui", "non", "vas-y", "détaille", "go", etc.) are intercepted by `CONTINUATION_PATTERNS` regex before any other phase. When detected, the message is enriched with the last user question + last assistant response from history via `_enrich_with_context()`, then sent directly to Gemini (all regex/SQL phases are bypassed). This prevents short answers from being misrouted to the grid generator or Text-to-SQL. The enriched message is used only for the Gemini call — the original message is preserved in conversational history. Logged as `[CONTINUATION]`.

**Temporal filter bypass**: If the message contains a temporal filter ("en 2025", "dans l'année 2024", "pour l'année 2025", "cette année", "en janvier", etc.), Phases 2/3/1 are skipped via `_has_temporal_filter()` (22 regex patterns covering all French temporal formulations) and Phase SQL handles the query directly, since regex phases cannot filter by date.

**Conversational memory**: The last 20 messages of conversation history are sent by the frontend. The last 6 are passed to the SQL Generator, enabling follow-up questions like "et la première fois ?" after asking about a specific number.

**Text-to-SQL pipeline**: User question → Gemini generates SQL (temperature 0.0, dedicated prompt with schema + few-shot examples) → Python validates (SELECT only, no forbidden keywords, max 1000 chars, no SQL comments) → Executes on Cloud SQL (5s timeout) → Results injected as `[RÉSULTAT SQL]` block. Temporal resolution rules ensure "en janvier" maps to current year, not all Januarys.

**Context enrichment**: Stats are injected as tagged blocks (`[DONNÉES TEMPS RÉEL]`, `[RÉSULTAT TIRAGE]`, `[RÉSULTAT SQL]`, `[ANALYSE DE GRILLE]`, `[CLASSEMENT]`, `[COMPARAISON]`, `[NUMÉROS CHAUDS/FROIDS]`) into the Gemini user message. The system prompt contains rules to use these facts without making predictions.

**Rate limiting**: Phase SQL is limited to 10 queries per session (counted via history length).

**Monitoring**: All SQL queries are logged with structured format: `[TEXT2SQL] question="..." | sql="..." | status=OK|EMPTY|NO_SQL|REJECTED|ERROR | rows=N | time=Xms`.

**SQL optimization**: Phase 3 uses `UNION ALL` queries (`_get_all_frequencies()`) to fetch all 49 frequencies in 1 query instead of 49.

### HYBRIDE Pitch (Personalized Grid Commentary)

| Feature | Detail |
|---------|--------|
| **Endpoint** | `POST /api/pitch-grilles` (1-5 grids per call) |
| **Backend** | `prepare_grilles_pitch_context()` computes stats for all grids in 1 DB connection |
| **AI** | Single Gemini call with dedicated prompt (`prompt_pitch_grille.txt`) |
| **Output** | JSON `{"pitchs": ["pitch 1...", "pitch 2..."]}` |
| **Generator** | Pitch placeholder (pulse animation) shown under each grid card, replaced async |
| **Simulator** | Single pitch shown below history check, replaced async |
| **Fallback** | If Gemini fails, placeholders are silently removed (no crash, no error) |
| **Temperature** | 0.9 for varied, enthusiastic commentary |

### Custom Grid Simulator

- Interactive 49-number selection
- Real-time score calculation via `/api/analyze-custom-grid`
- Heat visualization (hot/cold coloring)
- Badges, star rating, and conformity feedback
- Historical match verification (exact + best partial match with chance number display)
- HYBRIDE pitch (async Gemini commentary below audit results)

### SEO System

- Per-page Open Graph + Twitter Card meta tags
- Structured data (JSON-LD: WebPage, FAQPage, Dataset, SoftwareApplication, TechArticle)
- Canonical redirect: `www.lotoia.fr` → `lotoia.fr` (301)
- Clean URL rewriting: `/ui/*.html` → `/page-name` (301)

### Analytics & GDPR

- Cookie consent management (consent-based activation)
- GA4 Consent Mode v2: baseline cookieless → enhanced after consent
- Grid generation tracking (session, grid_id, target_date)
- Ad impression/click tracking (CPA)
- Chatbot GA4 events (5 custom events: open, message, session, sponsor_view, clear)
- No tracking without explicit user consent
- CSP: img-src + connect-src whitelist GA4/GTM domains

---

## 4. Architecture Flow

```
USER BROWSER (HTML/CSS/Vanilla JS)
         |
         v
+--------------------------------------------------+
|              MIDDLEWARE STACK                      |
|  1. GZipMiddleware (>500 bytes) — outermost       |
|  2. UmamiOwnerFilterMiddleware (OWNER_IP filter)  |
|  3. HeadMethodMiddleware (HEAD → GET adapter)     |
|  4. trailing_slash_redirect (strip trailing /)     |
|  5. redirect_ui_html_to_seo (URL dedup 301)       |
|  6. add_cache_headers (by content type)           |
|  7. canonical_www_redirect (SEO 301)              |
|  8. redirect_http_to_https (HTTPS enforcement)    |
|  9. Security Headers (CSP, HSTS, X-Frame-Options) |
| 10. correlation_id_middleware (X-Request-ID)       |
| 11. CORSMiddleware (allowed origins)              |
| 12. Rate Limiting (slowapi, 10/min on chat)       |
+--------------------------------------------------+
         |
         v
+--------------------------------------------------+
|              FASTAPI ROUTES (APIRouter)           |
|                                                   |
|  ── Unified Routes (Phase 10) ──────────────     |
|  routes/api_data_unified.py    /api/{game}/data   |
|  routes/api_analyse_unified.py /api/{game}/analyse|
|  routes/api_chat_unified.py    /api/{game}/chat   |
|                                                   |
|  ── Legacy Thin Wrappers (backward compat) ──    |
|  routes/api_data.py      → unified (Loto)        |
|  routes/em_data.py       → unified (EM)          |
|  routes/api_analyse.py   → unified + /ask (Loto) |
|  routes/em_analyse.py    → unified + texte/pdf   |
|  routes/api_chat.py      HYBRIDE chatbot Loto     |
|  routes/api_chat_em.py   HYBRIDE chatbot EM       |
|                                                   |
|  ── Shared Routes ────────────────────────────   |
|  routes/pages.py         23 HTML/SEO pages        |
|  routes/em_pages.py      EM HTML page routes (FR) |
|  routes/en_em_pages.py   EM HTML page routes (EN) |
|  routes/api_gemini.py    Gemini AI enrichment     |
|  routes/api_pdf.py       PDF generation           |
|  routes/api_tracking.py  Analytics tracking       |
|  routes/api_ratings.py   User rating system       |
|  main.py                 health, SEO 301          |
+--------------------------------------------------+
         |
         v
+--------------------------------------------------+
|              SERVICES LAYER (21 modules, ~6200L)  |
|                                                   |
|  ── Chat Pipeline (Phase 1+4) ──────────────     |
|  chat_pipeline.py       Loto 12-phase orchestration|
|  chat_pipeline_em.py    EM 12-phase orchestration  |
|  chat_detectors.py      Regex detection + responses|
|  chat_detectors_em.py   EM-specific detectors      |
|  chat_sql.py            Text-to-SQL + executor     |
|  chat_sql_em.py         EM SQL generation          |
|  chat_utils.py          Context, formatting, sponsor|
|  chat_utils_em.py       EM utils                   |
|                                                   |
|  ── Stats (Phase 2) ────────────────────────     |
|  base_stats.py          GameConfig base class (770L)|
|  stats_service.py       Loto thin wrapper (121L)   |
|  em_stats_service.py    EM thin wrapper (87L)      |
|                                                   |
|  ── AI + Cache + PDF ───────────────────────     |
|  gemini.py              Gemini 2.0 Flash — Loto    |
|  em_gemini.py           Gemini 2.0 Flash — EM      |
|  cache.py               Redis async + fallback (P6)|
|  circuit_breaker.py     3 fails → 60s open         |
|  pdf_generator.py       ReportLab PDF — Loto       |
|  em_pdf_generator.py    ReportLab PDF — EM         |
|  penalization.py        Post-draw frequency filter  |
|  prompt_loader.py       36 keys dynamic loader     |
+--------------------------------------------------+
         |
         v
+--------------------------------------------------+
|              ENGINE LAYER                         |
|                                                   |
|  engine/hybride.py      HYBRIDE (Loto)             |
|  engine/hybride_em.py   HYBRIDE (EuroMillions)     |
|  engine/stats.py        Descriptive statistics     |
|  engine/models.py       Pydantic validation        |
+--------------------------------------------------+
         |
         v
+--------------------------------------------------+
|              CACHE LAYER (Phase 6)                |
|                                                   |
|  services/cache.py                                |
|    Primary: redis.asyncio (pickle serialization)  |
|    Fallback: in-memory dict + TTL (1h)            |
|    Lifecycle: init_cache/close_cache in lifespan  |
|    Env: REDIS_URL (optional, fallback if absent)  |
+--------------------------------------------------+
         |
         v
+--------------------------------------------------+
|              DATABASE LAYER (Phase 5: aiomysql)   |
|                                                   |
|  db_cloudsql.py (259 lines)                       |
|    Pool: aiomysql.create_pool (min=5, max=10)     |
|    Local: TCP via Cloud SQL Proxy (127.0.0.1)     |
|    Prod:  Unix socket (/cloudsql/...)             |
|    Native async: no asyncio.to_thread() wrappers  |
|    DictCursor: results as dicts                   |
|    Context manager: async with get_connection()   |
|    Pool recycle: 3600s                            |
|                                                   |
|  Google Cloud SQL (MariaDB)                       |
|    Database: lotofrance                           |
|    Table: tirages (date, boule_1..5, chance)      |
|    Table: tirages_euromillions                    |
|      (date, boule_1..5, etoile_1..2, jackpot,    |
|       nb_joueurs, nb_gagnants_rang1)              |
|    Indexes: date_de_tirage, boule_1-5, chance     |
|    Records: 967+ Loto + 729 EM draws (2019-2026) |
+--------------------------------------------------+
         |
         v
+--------------------------------------------------+
|              EXTERNAL APIs                        |
|                                                   |
|  Gemini 2.0 Flash (generativelanguage.googleapis) |
|    Text enrichment for META ANALYSE               |
|    HYBRIDE chatbot (multi-turn, system_instruction)|
|    httpx.AsyncClient (shared via lifespan)        |
|    Circuit breaker: 3 fails → 60s open → half-open|
|    Fallback: local text / fallback message         |
+--------------------------------------------------+
```

### Modular Architecture (Post-Audit Refactoring)

```
main.py (~640 lines) — Orchestrator
    ├── app = FastAPI() + lifespan (httpx.AsyncClient + aiomysql pool + Redis cache)
    ├── Middlewares (CORS, correlation ID, security headers, canonical, cache, SEO, Umami filter, HEAD, HTTPS)
    ├── Rate limiting (slowapi, 10/min on chat endpoints)
    ├── Static mounts (/ui, /static)
    ├── app.include_router() x16 (8 legacy Loto + 4 legacy EM + 3 unified Phase 10 + 1 EN EM Phase 11)
    ├── /health (native async + asyncio.wait_for 5s timeout)
    └── SEO 301 redirects

schemas.py — Pydantic Models (Loto)
    ├── AskPayload
    ├── GridData, TrackGridPayload
    ├── TrackAdImpressionPayload, TrackAdClickPayload
    ├── MetaAnalyseTextePayload
    ├── MetaPdfPayload
    ├── ChatMessage, HybrideChatRequest
    ├── HybrideChatResponse
    ├── PitchGrilleItem
    └── PitchGrillesRequest

em_schemas.py — Pydantic Models (EuroMillions)
    ├── EMGridData (nums + etoiles + score)
    ├── EMMetaAnalyseTextePayload
    ├── EMMetaPdfPayload (graph_data_boules + graph_data_etoiles)
    ├── EMPitchGrilleItem
    ├── EMPitchGrillesRequest
    ├── EMChatMessage (role + content)
    ├── EMChatRequest (message + page + history)
    └── EMChatResponse (response + source + mode)

rate_limit.py — Shared slowapi limiter instance

routes/ — 16 routers (3 unified + 8 legacy Loto + 4 legacy EM + 1 EN Phase 11)
    ── Unified Routes (Phase 10) ──
    ├── api_data_unified.py    (~400L)  /api/{game}/tirages/*, stats/*, numbers-heat, draw/*, etc.
    ├── api_analyse_unified.py (~720L)  /api/{game}/generate, meta-analyse-local, analyze-custom-grid
    ├── api_chat_unified.py     (~70L)  /api/{game}/hybride-chat, pitch-grilles
    ── Legacy Thin Wrappers (backward compat, Phase 10) ──
    ├── api_data.py       (~135L)  Loto thin wrapper → unified + /database-info, /stats legacy
    ├── em_data.py        (~100L)  EM thin wrapper → unified (prefix /api/euromillions)
    ├── api_analyse.py     (~60L)  Loto thin wrapper → unified + /ask (Loto-only)
    ├── em_analyse.py     (~100L)  EM thin wrapper → unified + /meta-analyse-texte, /meta-pdf (EM-only)
    ├── api_chat.py        (~85L)  Loto chatbot wrapper + re-exports (services.chat_detectors, chat_sql, chat_utils)
    ├── api_chat_em.py     (~75L)  EM chatbot wrapper + re-exports (services.chat_detectors_em, chat_sql_em, chat_utils_em)
    ── Shared Routes ──
    ├── pages.py          (236 lines)  23 HTML page routes
    ├── em_pages.py       (68 lines)   EuroMillions HTML page routes (7 SEO clean URLs, FR)
    ├── en_em_pages.py    (74 lines)   EuroMillions EN page routes (7 SEO clean URLs, Phase 11)
    ├── api_gemini.py      (19 lines)  meta-analyse-texte
    ├── api_pdf.py         (37 lines)  meta-pdf
    ├── api_tracking.py   (127 lines)  track-grid, track-ad-*
    └── api_ratings.py    (106 lines)  user rating submission + global stats

services/ — 21 modules, ~6200 lines
    ── Chat Pipeline (Phase 1 Loto, Phase 4 EM) ──
    ├── chat_pipeline.py     (639L)  12-phase orchestration — Loto
    ├── chat_pipeline_em.py  (653L)  12-phase orchestration — EuroMillions
    ├── chat_detectors.py    (850L)  Regex detectors, insult/OOR pools, streak — Loto
    ├── chat_detectors_em.py (495L)  EM-specific detectors + response pools
    ├── chat_sql.py          (247L)  Text-to-SQL generator + executor — Loto
    ├── chat_sql_em.py       (176L)  Text-to-SQL — EuroMillions
    ├── chat_utils.py        (396L)  Context building, formatting, sponsor — Loto
    ├── chat_utils_em.py     (200L)  Context building, formatting — EuroMillions
    ├── chat_responses_em_en.py (~250L) English response pools for EM chatbot (Phase 11)
    ── Stats Layer (Phase 2: base class refactoring) ──
    ├── base_stats.py        (770L)  GameConfig-driven base class (8 methods, 4 SQL hooks)
    ├── stats_service.py     (121L)  Loto thin wrapper → base_stats
    ├── em_stats_service.py   (87L)  EM thin wrapper → base_stats (em: cache prefix)
    ── AI, Cache, PDF ──
    ├── cache.py             (116L)  Redis async + in-memory fallback (Phase 6)
    ├── circuit_breaker.py    (84L)  Gemini circuit breaker (CLOSED/OPEN/HALF_OPEN)
    ├── gemini.py            (130L)  Gemini API client — Loto (via circuit breaker)
    ├── em_gemini.py         (122L)  Gemini API client — EuroMillions
    ├── pdf_generator.py     (361L)  ReportLab PDF engine — Loto (single graph)
    ├── em_pdf_generator.py  (364L)  ReportLab PDF engine — EM (dual graphs, 2x2 matplotlib)
    ├── penalization.py       (65L)  Post-draw frequency penalization filter
    └── prompt_loader.py     (101L)  Dynamic prompt loader (36 keys: 18 Loto + 18 EM)

tests/ — 473 tests, 20 files, ~5100 lines (pytest + pytest-cov)
    ├── conftest.py                (247L)  Fixtures (AsyncSmartMockCursor, cache clear)
    ── Foundation Tests ──
    ├── test_models.py             (92L)   Pydantic models + CONFIG weights
    ├── test_hybride.py           (255L)   HYBRIDE engine (pure + DB-mocked)
    ├── test_stats.py             (252L)   engine/stats.py functions
    ├── test_services.py          (328L)   cache + stats_service
    ├── test_circuit_breaker.py   (162L)   Circuit breaker state machine
    ├── test_penalization.py       (97L)   Penalization logic
    ── Route Tests ──
    ├── test_routes.py            (326L)   FastAPI TestClient (health, tirages, chat, correlation ID)
    ├── test_unified_routes.py    (362L)   Unified /api/{game}/... routes (Phase 10)
    ├── test_en_routes.py         (~220L)  EN EuroMillions pages + static JS (Phase 11)
    ├── test_ratings.py           (382L)   Rating system (submit, global stats, validation)
    ── Chat Pipeline Tests (Phase 3) ──
    ├── test_chat_sql.py          (186L)   SQL injection security, _validate_sql, _ensure_limit
    ├── test_chat_utils.py        (190L)   _clean_response, _enrich_with_context, _format_date_fr
    ├── test_chat_detectors_extra.py (159L) _detect_grille, _detect_mode, _detect_requete_complexe
    ├── test_base_stats.py        (219L)   BaseStatsService: categories, pitch, EM paths
    ── EM Chat Tests (Phase 4) ──
    ├── test_chat_detectors_em.py (319L)   EM detection pipeline
    ├── test_chat_pipeline_em.py  (231L)   EM orchestration
    ├── test_chat_utils_em.py     (232L)   EM context building
    ── Stress Tests ──
    └── test_insult_oor.py        (854L)   141 tests: insult detection + out-of-range numbers
```

### Unified Routing Architecture (Phase 10)

Phase 10 introduced a unified routing layer under `/api/{game}/...` with `game = loto | euromillions`.
This eliminated ~2600 lines of duplicated code across 6 route files, replacing them with:

```
config/games.py — GameConfig registry
    ├── ValidGame(str, Enum)              "loto" | "euromillions"
    ├── RouteGameConfig (frozen dataclass) table, ranges, modules, draw_days
    ├── GAME_CONFIGS dict                  per-game configuration
    └── Lazy import helpers               get_stats_service(), get_engine(), get_chat_pipeline()

routes/api_data_unified.py    (~400L)  12 data endpoints — /api/{game}/tirages/*, stats/*, draw/*, etc.
routes/api_analyse_unified.py (~720L)   3 analysis endpoints — /api/{game}/generate, meta-analyse-local, analyze-custom-grid
routes/api_chat_unified.py     (~70L)   2 chat endpoints — /api/{game}/hybride-chat, pitch-grilles
```

**Pattern**: Each unified handler starts with `cfg = get_config(game)` then uses `cfg.table`,
`cfg.num_range`, `cfg.secondary_name` etc. for SQL queries, validation, and response shaping.

**Backward compat**: Legacy route files (`api_data.py`, `em_data.py`, `api_analyse.py`, `em_analyse.py`,
`api_chat.py`, `api_chat_em.py`) are thin wrappers that call unified handlers with hardcoded
`game=ValidGame.loto` or `game=ValidGame.euromillions`. All existing URLs continue to work.

**Routing priority**: Legacy routers are registered before unified routers in `main.py`.
FastAPI's first-match routing ensures exact legacy paths match before the `{game}` parameter.

### Cache Strategy

| Content Type | Cache Duration | Header |
|--------------|----------------|--------|
| CSS / JS | 7 days | `Cache-Control: public, max-age=604800` |
| Images (jpg, webp, ico, svg) | 30 days | `Cache-Control: public, max-age=2592000` |
| HTML pages | 1 hour | `Cache-Control: public, max-age=3600` |
| XML / TXT (sitemap, robots) | 24 hours | `Cache-Control: public, max-age=86400` |
| API responses | No cache | None |

---

## 5. Frontend Architecture

Static HTML pages served by FastAPI. No templating engine. JavaScript modules handle dynamic behavior client-side.

| Module | Purpose |
|--------|---------|
| `app.js` | Grid generation, DB status, result rendering, engine controls (Loto) |
| `app-em.js` | EuroMillions application logic (grid generation, results, EM-specific UI) |
| `simulateur.js` | Interactive 49-number grid, real-time API scoring (Loto) |
| `simulateur-em.js` | Interactive EM grid, real-time API scoring (EuroMillions) |
| `sponsor-popup75.js` | META ANALYSE 75 Loto: Gemini chain, PDF export, sponsor timer |
| `sponsor-popup75-em.js` | META ANALYSE 75 EM: dual graphs (boules+etoiles), Gemini chain, PDF export, sponsor timer |
| `theme.js` | Dark/light mode toggle with `localStorage` persistence |
| `analytics.js` | GDPR-compliant analytics (GA4 Consent Mode v2, `LotoIAAnalytics.track()` API) |
| `cookie-consent.js` | Cookie consent banner and preference management |
| `faq.js` | FAQ accordion interactions (Loto) |
| `faq-em.js` | FAQ accordion interactions (EuroMillions) |
| `scroll.js` | Scroll-to-top button (shows after 300px scroll, all pages including legal) |
| `nav-scroll.js` | Navigation scroll behavior |
| `rating-popup.js` | Rating popup UI logic (user feedback submission) |
| `version-inject.js` | Dynamic version injection from `/api/version` into `.app-version` spans |
| `hybride-chatbot.js` | HYBRIDE chatbot widget — Loto (bubble, chat window, sessionStorage `hybride-history`, GA4 tracking, Gemini API via `/api/hybride-chat`) |
| `hybride-chatbot-em.js` | HYBRIDE chatbot widget — EuroMillions (sessionStorage `hybride-history-em`, Gemini API via `/api/euromillions/hybride-chat`, GA4 `hybride_em_chat_*` events) |
| `hybride-chatbot-em-en.js` | HYBRIDE chatbot widget — EM English (EN sponsor detection, en-GB locale, Phase 11) |
| `sponsor-popup.js` | Sponsor/ad popup for grid generation |

### Theme System

- Toggle via `theme.js` using CSS custom properties (`--theme-*`)
- Persisted in `localStorage`
- All pages include `theme.js` as first script (prevents flash)

### META ANALYSE 75 - Client Flow — Loto (sponsor-popup75.js)

```
T=0  showMetaAnalysePopup()
 ├── triggerGeminiEarly()                     # Fires immediately
 │     ├── fetch /api/meta-analyse-local      # Local analysis (~1-3s)
 │     └── fetch /api/meta-analyse-texte      # Gemini enrichment (~5-15s)
 │           ├── SUCCESS → finalAnalysisText = enriched
 │           └── FAIL    → finalAnalysisText = localText (fallback)
 │
 ├── Promise.race([chainPromise, 28s timeout])
 │
 └── showSponsorPopup75(30s timer)            # Sponsor popup with console
       └── onComplete → onMetaAnalyseComplete()
             ├── await metaAnalysisPromise
             ├── openMetaResultPopup()         # Graph + analysis text
             └── PDF button → fetch /api/meta-pdf (uses finalAnalysisText)
```

**Key variables:**
- `finalAnalysisText` — Single source of truth for analysis text (Gemini or local)
- `metaResultData` — Full API response data for the result popup
- `metaAnalysisPromise` — Promise resolved when text is ready

### META ANALYSE 75 - Client Flow — EuroMillions (sponsor-popup75-em.js)

```
T=0  showMetaAnalysePopupEM()
 ├── triggerGeminiEarlyEM()                          # Fires immediately
 │     ├── fetch /api/euromillions/meta-analyse-local # Local analysis (graph_boules + graph_etoiles)
 │     └── fetch /api/euromillions/meta-analyse-texte # Gemini enrichment (load_prompt_em)
 │           ├── SUCCESS → finalAnalysisTextEM = enriched
 │           └── FAIL    → finalAnalysisTextEM = localText (fallback)
 │
 ├── Promise.race([chainPromise, 28s timeout])
 │
 └── showSponsorPopup75EM(30s timer)                 # Sponsor popup with EM console
       └── onComplete → onMetaAnalyseCompleteEM()
             ├── await metaAnalysisPromiseEM
             ├── openMetaResultPopupEM()              # TWO graph sections + analysis text
             └── PDF button → fetch /api/euromillions/meta-pdf (graph_data_boules + graph_data_etoiles)
```

**Key variables (all EM-suffixed, no collision with Loto):**
- `finalAnalysisTextEM` — Single source of truth for EM analysis text
- `metaResultDataEM` — Full API response data (includes `graph_boules` + `graph_etoiles`)
- `metaAnalysisPromiseEM` — Promise resolved when EM text is ready

**EM-specific differences vs Loto:**
- Dual graphs: `graph_boules` (Top 5, colors blue/green) + `graph_etoiles` (Top 3, colors orange/teal)
- No 800-draw window (EM has only 729 tirages), slider max = 700
- ~104 tirages/year estimation (2 draws/week: mardi + vendredi)
- Console logs mention "HYBRIDE EM", "base EuroMillions", "fréquences boules (1-50)", "fréquences étoiles (1-12)"
- Matrix line format: "01 12 34 45 50 | ★03 ★11"

---

## 6. Tech Stack

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| FastAPI | 0.115.0 | Async web framework |
| Uvicorn | 0.32.0 | ASGI server (2 workers) |
| aiomysql | ≥0.2.0 | Native async MySQL/MariaDB driver (Phase 5) |
| redis[hiredis] | ≥5.0 | Async Redis cache + in-memory fallback (Phase 6) |
| httpx | ≥0.27 | Async HTTP client (shared via lifespan) |
| slowapi | ≥0.1.9 | Rate limiting (IP-based, 10/min on chat) |
| python-json-logger | ≥2.0.7 | JSON structured logging |
| ReportLab | 4.1.0 | PDF generation (META75 reports) |
| matplotlib | 3.9.2 | Charts for EM PDF (dual graphs boules+etoiles) |
| python-dotenv | 1.0.1 | Environment configuration |
| cryptography | 43.0.3 | SSL/TLS support |
| pytest | ≥8.0 | Unit testing framework |
| pytest-asyncio | ≥0.23 | Async test support |
| pytest-cov | ≥6.0 | Coverage reporting |

### External APIs

| Service | Model | Purpose |
|---------|-------|---------|
| Google Gemini | gemini-2.0-flash | AI text enrichment for META ANALYSE + HYBRIDE chatbot |

### Database

| Technology | Purpose |
|------------|---------|
| Google Cloud SQL | Managed MariaDB instance (europe-west1) |
| Cloud SQL Proxy | Local development TCP tunnel |

### Frontend

| Technology | Purpose |
|------------|---------|
| HTML5 | Semantic markup, no templating |
| CSS3 | Custom properties, Grid, Flexbox |
| Vanilla JavaScript | No framework dependency |

### Infrastructure

| Technology | Purpose |
|------------|---------|
| Google Cloud Run | Serverless container hosting (europe-west1) |
| Google Cloud Build | CI/CD pipeline: Build → Test → Push → Deploy |
| Docker | Container runtime (Python 3.13-slim, 2 Uvicorn workers) |
| Container Registry | Image storage (gcr.io) |

---

## 7. API Summary

### Page Routes (23) — routes/pages.py

| Route | Template |
|-------|----------|
| `GET /` | launcher.html |
| `GET /accueil` | accueil.html (dynamic JSON-LD ratings) |
| `GET /loto` | loto.html |
| `GET /loto/analyse` | simulateur.html (canonical: /loto/analyse) |
| `GET /loto/exploration` | loto.html (canonical: /loto) |
| `GET /loto/statistiques` | statistiques.html (canonical: /loto/statistiques) |
| `GET /loto/intelligence-artificielle` | loto-ia.html |
| `GET /loto/numeros-les-plus-sortis` | numeros-les-plus-sortis.html |
| `GET /historique` | historique.html |
| `GET /faq` | faq.html (dynamic via Cloud SQL) |
| `GET /news` | news.html |
| `GET /moteur` | moteur.html |
| `GET /methodologie` | methodologie.html |
| `GET /hybride` | hybride.html |
| `GET /a-propos` | a-propos.html |
| `GET /disclaimer` | disclaimer.html |
| `GET /mentions-legales` | mentions-legales.html |
| `GET /politique-confidentialite` | politique-confidentialite.html |
| `GET /politique-cookies` | politique-cookies.html |
| `GET /robots.txt` | robots.txt |
| `GET /sitemap.xml` | sitemap.xml |
| `GET /favicon.ico` | favicon.ico |
| `GET /BingSiteAuth.xml` | BingSiteAuth.xml |

### EN EuroMillions Page Routes (7) — routes/en_em_pages.py (Phase 11)

| Route | Template |
|-------|----------|
| `GET /en/euromillions` | en/euromillions/home.html |
| `GET /en/euromillions/generator` | en/euromillions/generator.html |
| `GET /en/euromillions/simulator` | en/euromillions/simulator.html |
| `GET /en/euromillions/statistics` | en/euromillions/statistics.html |
| `GET /en/euromillions/history` | en/euromillions/history.html |
| `GET /en/euromillions/faq` | en/euromillions/faq.html |
| `GET /en/euromillions/news` | en/euromillions/news.html |

All EN pages include `hreflang` alternate links (`fr`/`en`/`x-default`), lang-switch button (`FR/EN`), and load EN-specific JS from `/ui/en/euromillions/static/`.

### Unified Data Endpoints (Phase 10) — routes/api_data_unified.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/{game}/tirages/count` | GET | Total draw count (game = loto \| euromillions) |
| `/api/{game}/tirages/latest` | GET | Most recent draw |
| `/api/{game}/tirages/list` | GET | Paginated draw history (limit, offset) |
| `/api/{game}/database-info` | GET | Database status and metadata |
| `/api/{game}/meta-windows-info` | GET | Dynamic window info for META sliders |
| `/api/{game}/stats` | GET | Complete stats (frequencies, lags, heat) |
| `/api/{game}/numbers-heat` | GET | Hot/cold/neutral classification |
| `/api/{game}/draw/{date}` | GET | Draw by date (YYYY-MM-DD) |
| `/api/{game}/stats/number/{number}` | GET | Individual number analysis |
| `/api/{game}/stats/etoile/{number}` | GET | Individual etoile analysis (EM only, Loto → 404) |
| `/api/{game}/stats/top-flop` | GET | Top/bottom frequency rankings |
| `/api/{game}/hybride-stats` | GET | Single number stats for chatbot |

### Unified Analysis Endpoints (Phase 10) — routes/api_analyse_unified.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/{game}/generate` | GET | Generate N optimized grids (game-aware) |
| `/api/{game}/meta-analyse-local` | GET | META ANALYSE local (real Cloud SQL stats) |
| `/api/{game}/analyze-custom-grid` | POST | Analyze user-composed grid (game-aware ranges) |

### Unified Chat Endpoints (Phase 10) — routes/api_chat_unified.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/{game}/hybride-chat` | POST | HYBRIDE chatbot (game-aware pipeline) |
| `/api/{game}/pitch-grilles` | POST | Personalized Gemini pitch per grid |

### Legacy Data Endpoints — routes/api_data.py (thin wrapper)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/database-info` | GET | Full database status and metadata (Loto legacy) |
| `/api/database-info` | GET | Light database info (FAQ dynamic) |
| `/stats` | GET | Global statistics (Loto legacy via engine.stats) |
| `/api/stats` | GET | → unified (game=loto) |
| `/api/stats/number/{number}` | GET | → unified (game=loto) |
| `/api/stats/top-flop` | GET | → unified (game=loto) |
| `/api/numbers-heat` | GET | → unified (game=loto) |
| `/api/tirages/count` | GET | → unified (game=loto) |
| `/api/tirages/latest` | GET | → unified (game=loto) |
| `/api/tirages/list` | GET | → unified (game=loto) |
| `/draw/{date}` | GET | → unified (game=loto) |
| `/api/hybride-stats` | GET | → unified (game=loto) |
| `/api/meta-windows-info` | GET | → unified (game=loto) |

### Legacy Analysis Endpoints — routes/api_analyse.py (thin wrapper)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ask` | POST | Main engine prompt (Loto-only, kept in wrapper) |
| `/generate` | GET | → unified (game=loto) |
| `/api/meta-analyse-local` | GET | → unified (game=loto) |
| `/api/analyze-custom-grid` | POST | → unified (game=loto) |

### Gemini Endpoint — routes/api_gemini.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/meta-analyse-texte` | POST | AI text enrichment via Gemini 2.0 Flash |

### PDF Endpoint — routes/api_pdf.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/meta-pdf` | POST | Generate META75 PDF report (ReportLab) |

### Legacy Chat Endpoint — routes/api_chat.py (thin wrapper)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/hybride-chat` | POST | HYBRIDE chatbot Loto (delegates to chat_pipeline) |
| `/api/pitch-grilles` | POST | Personalized Gemini pitch per grid |

### Tracking Endpoints — routes/api_tracking.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/track-grid` | POST | Track generated grid |
| `/api/track-ad-impression` | POST | Track ad impression |
| `/api/track-ad-click` | POST | Track ad click (CPA) |

### Rating Endpoints — routes/api_ratings.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ratings/submit` | POST | Submit user rating (1-5 stars) |
| `/api/ratings/global` | GET | Get global rating stats (count, average) |

### Legacy EM Data Endpoints — routes/em_data.py (thin wrapper)

All endpoints below delegate to unified handlers (game=euromillions). Backward compat.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/euromillions/tirages/count` | GET | → unified (game=euromillions) |
| `/api/euromillions/tirages/latest` | GET | → unified (game=euromillions) |
| `/api/euromillions/tirages/list` | GET | → unified (game=euromillions) |
| `/api/euromillions/database-info` | GET | → unified (game=euromillions) |
| `/api/euromillions/meta-windows-info` | GET | → unified (game=euromillions) |
| `/api/euromillions/stats` | GET | → unified (game=euromillions) |
| `/api/euromillions/numbers-heat` | GET | → unified (game=euromillions) |
| `/api/euromillions/draw/{date}` | GET | → unified (game=euromillions) |
| `/api/euromillions/stats/number/{number}` | GET | → unified (game=euromillions) |
| `/api/euromillions/stats/etoile/{number}` | GET | → unified (game=euromillions) |
| `/api/euromillions/stats/top-flop` | GET | → unified (game=euromillions) |
| `/api/euromillions/hybride-stats` | GET | → unified (game=euromillions) |

### Legacy EM Analysis Endpoints — routes/em_analyse.py (thin wrapper)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/euromillions/generate` | GET | → unified (game=euromillions) |
| `/api/euromillions/meta-analyse-local` | GET | → unified (game=euromillions) |
| `/api/euromillions/meta-analyse-texte` | POST | AI text enrichment via Gemini (EM-only, kept in wrapper) |
| `/api/euromillions/meta-pdf` | POST | META75 EM PDF report (EM-only, kept in wrapper) |
| `/api/euromillions/analyze-custom-grid` | POST | → unified (game=euromillions) |

### Legacy EM Chat Endpoints — routes/api_chat_em.py (thin wrapper)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/euromillions/hybride-chat` | POST | HYBRIDE chatbot EM (delegates to chat_pipeline_em) |
| `/api/euromillions/pitch-grilles` | POST | Personalized Gemini pitch per EM grid |

### Core Endpoints — main.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (async, DB 5s timeout, Gemini circuit state, uptime, version) |
| `/api/version` | GET | Returns `{"version": "1.001"}` from `config/version.py` |
| `/analyse` | GET | SEO 301 redirect to /simulateur |
| `/exploration` | GET | SEO 301 redirect to /loto |

---

## 8. Services Layer

### services/cache.py — Redis Async Cache + In-Memory Fallback (Phase 6)

- **Primary**: `redis.asyncio` client with pickle serialization (binary-safe, handles complex objects)
- **Fallback**: In-memory dict with TTL if Redis unavailable (zero-config for CI/local)
- **Default TTL**: 3600s (1 hour)
- **Lifecycle**: `init_cache()` / `close_cache()` called in FastAPI lifespan
- **Functions**: `cache_get(key)`, `cache_set(key, value, ttl)`, `cache_clear()`
- **Env**: `REDIS_URL` (optional; falls back to in-memory if absent or unreachable)
- **Used by**: `base_stats.py` (Loto `stats:` prefix, EM `em:` prefix)

### services/circuit_breaker.py — Gemini Circuit Breaker

- **States**: CLOSED → OPEN → HALF_OPEN → CLOSED
- **Threshold**: 3 consecutive failures → circuit opens for 60s
- **Failures**: httpx.TimeoutException, ConnectError, OSError, HTTP 500+, HTTP 429
- **Half-open**: After timeout, one test request allowed — success closes, failure reopens
- **Error**: Raises `CircuitOpenError` when circuit is open (callers do fallback)
- **Used by**: `gemini.py`, `chat_pipeline.py`, `chat_pipeline_em.py`

### services/base_stats.py — GameConfig-Driven Base Class (Phase 2)

- **Purpose**: Consolidated stats logic for both Loto and EuroMillions (770L)
- **Before Phase 2**: `stats_service.py` (721L) + `em_stats_service.py` (697L) = 1401L of ~54% duplicated code
- **After Phase 2**: `base_stats.py` (770L) + 2 thin wrappers (121L + 87L) = 978L (-30%)
- **GameConfig dataclass**: Drives all game-specific SQL (table name, column names, ranges)
- **8 config-driven methods**: `get_frequency()`, `get_retard()`, `get_classement()`, `get_top_n()`, `get_numeros_par_categorie()`, `get_comparaison_numeros()`, `analyze_grille_for_chat()`, `prepare_grilles_pitch_context()`
- **4 SQL hooks**: Overridable for game-specific column queries (UNION ALL patterns)
- **Cache-aware**: `cache_prefix` parameter (Loto: `stats:`, EM: `em:`)

### services/stats_service.py — Loto Stats Wrapper (Phase 2)

- **Thin wrapper** (121L): Inherits from `BaseStatsService`, sets Loto GameConfig
- **Config**: table=`tirages`, num_range=(1,49), secondary=`numero_chance`
- **Used by**: `api_data_unified.py`, `chat_pipeline.py`

### services/em_stats_service.py — EuroMillions Stats Wrapper (Phase 2)

- **Thin wrapper** (87L): Inherits from `BaseStatsService`, sets EM GameConfig
- **Config**: table=`tirages_euromillions`, num_range=(1,50), secondary=`etoile_1, etoile_2`
- **Cache prefix**: `em:` (no collision with Loto)
- **Used by**: `api_data_unified.py`, `chat_pipeline_em.py`

### services/gemini.py — Gemini AI Client (Loto)

- **API**: Google Gemini 2.0 Flash (`generativelanguage.googleapis.com/v1beta`)
- **Transport**: httpx.AsyncClient (shared via app lifespan, circuit breaker wrapped)
- **Auth**: API key via `GEM_API_KEY` or `GEMINI_API_KEY` env var
- **Prompt**: Loaded dynamically from `prompts/tirages/` or `prompts/annees/` via `load_prompt()`
- **Fallback chain**: Gemini enriched → Local text (if API fails/timeout) → Circuit open fallback
- **Output**: `{"analysis_enriched": "...", "source": "gemini_enriched"|"hybride_local"|"fallback"|"fallback_circuit"}`
- **Shared by**: META ANALYSE (api_gemini.py) + HYBRIDE chatbot (chat_pipeline.py) via `GEMINI_MODEL_URL`

### services/em_gemini.py — Gemini AI Client (EuroMillions)

- **API**: Same Gemini 2.0 Flash endpoint
- **Prompt**: Loaded dynamically from `prompts/euromillions/` via `load_prompt_em()` (auto `EM_` prefix)
- **Function**: `enrich_analysis_em(analysis_local, window, *, http_client)` — mirrors `enrich_analysis()` for EM
- **Fallback chain**: Same as Loto (Gemini enriched → Local text → Circuit open fallback)
- **Logging**: `[META TEXTE EM]` prefix for all log entries
- **Zero coupling**: Does not import from `gemini.py` (independent module)

### Chat Pipeline — 8 Modules (Phase 1 Loto, Phase 4 EM)

Phase 1 split `api_chat.py` (2014L) into 4 service modules. Phase 4 applied the same pattern to `api_chat_em.py` (1668L).

**services/chat_pipeline.py** (639L) / **chat_pipeline_em.py** (653L):
- **12-phase orchestration**: Continuation → Next Draw → Draw Results → Grid → Complex → Single Number → Text-to-SQL → Gemini
- **Functions**: `handle_chat(message, history, page, httpx_client)` → `dict(response, source, mode)`
- **Pitch**: `handle_pitch(grilles, httpx_client)` → `dict(pitchs: list[str])`

**services/chat_detectors.py** (850L) / **chat_detectors_em.py** (495L):
- **Regex patterns**: `_detect_insulte()`, `_detect_numero()`, `_detect_grille()`, `_detect_requete_complexe()`, `_detect_prochain_tirage()`, `_detect_mode()`
- **Response pools**: Insult L1-L4, OOR L1-L3, Compliment L1-L3, Menace responses
- **Streak tracking**: `_count_oor_streak()`, `_count_insult_streak()` with escalating responses

**services/chat_sql.py** (247L) / **chat_sql_em.py** (176L):
- **Text-to-SQL**: Gemini generates SQL (temperature 0.0) → Python validates → executes on Cloud SQL
- **Security**: SELECT only, no forbidden keywords, max 1000 chars, no SQL comments, 5s timeout
- **Functions**: `_generate_sql()`, `_validate_sql()`, `_ensure_limit()`, `_execute_safe_sql()`, `_format_sql_result()`
- **Limit**: 10 SQL queries per session

**services/chat_utils.py** (396L) / **chat_utils_em.py** (200L):
- **Context building**: `_build_session_context()`, `_enrich_with_context()` (continuation)
- **Formatting**: `_format_tirage_context()`, `_format_stats_context()`, `_format_grille_context()`
- **Sponsor**: `_get_sponsor_if_due(history, lang)` — post-response injection, style A/B alternation, bilingual FR/EN (Phase 11)

### services/pdf_generator.py — ReportLab PDF Engine (Loto)

- **Format**: A4 portrait, professional layout
- **Font system**: DejaVuSans (Linux/Cloud Run) -> Vera (ReportLab fallback)
  - 3 variants: Regular, Bold, Oblique
  - Multi-path resolution: reportlab/fonts/ -> /usr/share/fonts/ -> Vera fallback
- **Content**: Title, analysis block, single graph image, info block, sponsor with mailto link, signature, disclaimer, footer
- **Text**: Full UTF-8 support (French accents via `_utf8_clean()`)
- **Output**: `io.BytesIO` containing the PDF

### services/em_pdf_generator.py — ReportLab PDF Engine (EuroMillions)

- **Format**: A4 portrait, same professional layout as Loto
- **Dual graphs**: `generate_em_graph_image()` produces a 2x2 matplotlib figure:
  - Row 1: Top 5 Boules (bar chart + pie chart, blue/green palette)
  - Row 2: Top 3 Etoiles (bar chart + pie chart, orange/teal palette)
- **Function**: `generate_em_meta_pdf(analysis, window, engine, graph, graph_data_boules, graph_data_etoiles, sponsor)`
- **Title**: "Rapport META DONNEE EM - 75 Grilles" / "Analyse HYBRIDE EuroMillions"
- **Text**: Full UTF-8 support (`_utf8_clean()` duplicated, not imported — zero coupling with Loto)
- **Output**: `io.BytesIO` containing the PDF

### services/penalization.py — Number Penalization

- **Purpose**: Frequency-based weight adjustment for number generation
- **Used by**: Engine layer for grid optimization

### services/prompt_loader.py — Dynamic Prompt System

- **36 keys** mapped via `PROMPT_MAP` dict (18 Loto + 18 EM)
- **Loto keys** (18): 100, 200, 300, 400, 500, 600, 700, 800, GLOBAL, 1A-6A, CHATBOT, PITCH_GRILLE, SQL_GENERATOR
- **EM keys** (18): CHATBOT_EM, PITCH_GRILLE_EM, SQL_GENERATOR_EM, EM_100-EM_700, EM_GLOBAL, EM_1A-EM_6A, EM_GLOBAL_A
- **Functions**: `load_prompt(window)` (Loto) + `load_prompt_em(window)` (EM, auto `EM_` prefix)
- **Fallback**: `prompt_global.txt` for Loto, `prompts/euromillions/tirages/prompt_global.txt` for EM
- **Anti-meta block**: Each prompt contains rules preventing Gemini from starting with meta-commentary ("Voici une reformulation...")

---

## 9. Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_USER` | Yes | `jyppy` | Database username |
| `DB_PASSWORD` | Yes | — | Database password |
| `DB_NAME` | Yes | `lotofrance` | Database name |
| `DB_HOST` | Local only | `127.0.0.1` | Database host (TCP) |
| `DB_PORT` | Local only | `3306` | Database port (TCP) |
| `CLOUD_SQL_CONNECTION_NAME` | Prod only | `gen-lang-client-...:europe-west1:lotostat-eu` | Cloud SQL instance path |
| `GEM_API_KEY` | Optional | — | Gemini API key (primary) |
| `GEMINI_API_KEY` | Optional | — | Gemini API key (fallback name) |
| `REDIS_URL` | Optional | — | Redis connection URL for async cache (Phase 6; fallback to in-memory if absent) |
| `K_SERVICE` | Auto | — | Set by Cloud Run (production detection) |
| `OWNER_IP` | Optional | — | Owner IPv4 address(es) for Umami analytics filtering (pipe-separated) |
| `OWNER_IPV6` | Optional | — | Owner IPv6 prefix for Umami analytics filtering |

### Environment Detection

- **Production**: `K_SERVICE` is set -> Unix socket connection (`/cloudsql/...`)
- **Local**: `K_SERVICE` absent -> TCP connection via Cloud SQL Proxy

---

## 10. Security Features

| Feature | Implementation |
|---------|---------------|
| SQL Injection | Parameterized queries via aiomysql |
| CORS | CORSMiddleware with explicit allowed origins |
| CSP | Content-Security-Policy header (script-src, style-src, img-src, worker-src, upgrade-insecure-requests) (Phase 7) |
| Security Headers | X-Content-Type-Options, X-Frame-Options, HSTS (+preload), COOP, Referrer-Policy, Permissions-Policy (Phase 7) |
| Rate Limiting | slowapi IP-based limiter (10/min on chat, X-Forwarded-For aware) |
| Correlation ID | X-Request-ID per request (generated or forwarded) for tracing |
| Circuit Breaker | Gemini API protection (3 fails → 60s open → graceful fallback) |
| Compression | GZipMiddleware (>500 bytes) |
| Scraper Blocking | robots.txt (AhrefsBot, SemrushBot, GPTBot, CCBot) |
| GDPR Compliance | Cookie consent system, no tracking without approval |
| URL Deduplication | 301 redirect `/ui/*.html` → clean routes |
| Canonical URLs | 301 redirect `www` → root domain |
| HTTPS | Enforced via Cloud Run + `og:image:secure_url` + redirect_http_to_https middleware |
| API Key Protection | Gemini key stored in env vars, never exposed to client |
| Owner IP Filtering | UmamiOwnerFilterMiddleware strips analytics for owner IPs (OWNER_IP + OWNER_IPV6) |
| HEAD Method Support | HeadMethodMiddleware converts HEAD to GET (SEO crawlers compatibility) |

---

## 11. Development Phases

### Pre-Phase: Modular Extraction (2026-02-06)

| Step | Description | Impact |
|------|-------------|--------|
| Refactor 1/3 | Extract HTML page routes | main.py 1920 → 1758 lines |
| Refactor 2/3 | Extract services (Gemini, PDF, prompts) | main.py 1758 → 1406 lines |
| Refactor 3/3 | Extract API routes + schemas.py | main.py 1406 → 184 lines |

### Phase 1 — Loto Chat Modularization (2026-02-26)

Split `api_chat.py` (2014L) into 4 service modules + thin router.

| File | Lines | Purpose |
|------|-------|---------|
| `services/chat_detectors.py` | 850 | Regex detection, insult/OOR/compliment pools, streak tracking |
| `services/chat_pipeline.py` | 639 | 12-phase orchestration + Gemini pitch |
| `services/chat_utils.py` | 396 | Context building, formatting, sponsor injection |
| `services/chat_sql.py` | 247 | Text-to-SQL pipeline + safe DB execution |
| `routes/api_chat.py` | 85 | Thin FastAPI wrapper + backward compat re-exports |

**Result**: 2014L monolith → 5 focused modules, 248 tests pass, zero regression.

### Phase 2 — Stats Base Class Refactoring (2026-02-26)

Consolidated Loto/EM duplicate stats logic into a GameConfig-driven base class.

| File | Before | After |
|------|--------|-------|
| `services/base_stats.py` | — | 770L (new) |
| `services/stats_service.py` | 721L | 121L (thin wrapper) |
| `services/em_stats_service.py` | 697L | 87L (thin wrapper) |

**Result**: 1401L duplicated → 978L total (-30%), 8 config-driven methods, 4 overridable SQL hooks.

### Phase 3 — Tests + Cloud Run Infrastructure (2026-02-26)

Added 110 new tests targeting chat pipeline, SQL security, stats base class.

| File | Tests | Focus |
|------|-------|-------|
| `test_chat_sql.py` | 43 | SQL injection security, `_validate_sql`, `_ensure_limit` |
| `test_chat_utils.py` | 26 | `_clean_response`, `_enrich_with_context`, `_format_date_fr` |
| `test_base_stats.py` | 15 | `get_numeros_par_categorie`, pitch context, EM paths |
| `test_chat_detectors_extra.py` | 26 | `_detect_grille`, `_detect_mode`, `_detect_requete_complexe` |

Cloud Run optimized: `--memory=1Gi --cpu=2 --concurrency=40 --max-instances=10 --cpu-boost`.

**Result**: 248 → 358 tests, 0 failures.

### Phase 4 — EuroMillions Chat Modularization (2026-02-26)

Applied Phase 1 pattern to `api_chat_em.py` (1668L) → 4 service modules + thin router + 80 tests.

| File | Lines | Purpose |
|------|-------|---------|
| `services/chat_detectors_em.py` | 495 | EM-specific regex + response pools |
| `services/chat_pipeline_em.py` | 653 | EM 12-phase orchestration |
| `services/chat_utils_em.py` | 200 | EM context formatting |
| `services/chat_sql_em.py` | 176 | EM Text-to-SQL (tirages_euromillions schema) |
| `routes/api_chat_em.py` | 73 | Thin wrapper + backward compat re-exports |

New test files: `test_chat_detectors_em.py` (319L), `test_chat_pipeline_em.py` (231L), `test_chat_utils_em.py` (232L).

**Result**: 358 → 438 tests, 0 failures.

### Phase 5 — Async Database Migration (2026-02-26)

Replaced PyMySQL (sync) + DBUtils.PooledDB with aiomysql native async pool.

| Change | Detail |
|--------|--------|
| `db_cloudsql.py` | Full rewrite: `aiomysql.create_pool(min=5, max=10)` + DictCursor |
| `main.py` lifespan | Added `init_pool()` / `close_pool()` |
| Services + routes | **-68 `asyncio.to_thread()` wrappers** removed across 26 files |
| `services/base_stats.py` | All 11 methods sync → native async |
| Tests | `AsyncSmartMockCursor` + `AsyncMock` fixtures |

**Result**: 28 files changed, 1804+(+) / 2021-(-), 438 tests pass, zero PyMySQL references remaining.

### Phase 6 — Redis Async Cache + PDF Off-Thread (2026-02-26)

Replaced in-memory dict cache with Redis async + graceful fallback.

| Change | Detail |
|--------|--------|
| `services/cache.py` (116L) | `redis.asyncio` with pickle serialization, in-memory fallback |
| Lifecycle | `init_cache()` / `close_cache()` in FastAPI lifespan |
| PDF threading | `generate_meta_pdf` + `generate_em_meta_pdf` via `asyncio.to_thread()` |
| Env var | `REDIS_URL` (optional — works without Redis) |

**Result**: 9 files changed, 438 tests pass (all pass in fallback mode without Redis).

### Phase 7 — Schema.org Dataset + CSP Hardening (2026-02-26)

Enriched JSON-LD for Google Dataset Search credibility + strengthened security headers.

| Change | Detail |
|--------|--------|
| JSON-LD enrichment | `variableMeasured` (4 PropertyValue), `distribution` (DataDownload PDF), `license` (Etalab), `temporalCoverage`, `spatialCoverage`, `keywords` |
| CSP hardening | `+worker-src 'none'`, `+upgrade-insecure-requests` |
| HSTS | `+preload` (eligible for preload list) |
| COOP | `+Cross-Origin-Opener-Policy: same-origin` |

**Target**: Google Dataset Search ranking → Data Science credibility positioning.

### Phase 8 — SEO Semantic Pivot: Bankability T4 (2026-02-26)

Pivoted public-facing vocabulary from gambling terminology to data science positioning.

| Before | After |
|--------|-------|
| Pronostics | Modélisation |
| Générateur | Simulateur |
| featureList (generic) | Monte-Carlo simulation reference |

10 HTML files updated (Loto + EM). 0 prompts touched — pure SEO messaging adjustment.

**Target**: Bankability score T4 on public HTML for search intent alignment.

### Phase 10 — Unified Routes /api/{game}/ (2026-02-26)

Deduplicated ~2600L of Loto/EM route code under unified `/api/{game}/...` handlers.

| File | Lines | Purpose |
|------|-------|---------|
| `config/games.py` | 94 | `ValidGame` enum + `RouteGameConfig` dataclass + lazy-import helpers |
| `routes/api_data_unified.py` | 636 | 12 unified data endpoints |
| `routes/api_analyse_unified.py` | 723 | 3 unified analyse endpoints |
| `routes/api_chat_unified.py` | 73 | 2 unified chat endpoints |

Legacy route files became thin wrappers (backward compat). All existing URLs preserved.

**Result**: 2057+(+) / 2296-(-) = net code reduction, 438 → 455 tests, 0 failures.

### Phase 11 — EuroMillions English Version / Multilang GB (2026-02-27)

Full English (GB) version of the EuroMillions module: 7 HTML pages, 6 translated JS files, EN chatbot pipeline, i18n infrastructure.

| File | Lines | Purpose |
|------|-------|---------|
| `config/languages.py` | ~50 | Language registry: `LANG_CONFIGS`, `get_lang_config()` |
| `routes/en_em_pages.py` | 74 | 7 EN page routes (`/en/euromillions/*`) |
| `services/chat_responses_em_en.py` | ~250 | English response pools for EM chatbot |
| `ui/en/euromillions/*.html` | 7 files | Full EN HTML pages (hreflang, lang-switch, EN meta tags) |
| `ui/en/euromillions/static/*.js` | 6 files | Translated JS: app, simulator, sponsor, meta75, faq, chatbot |
| `ui/static/hybride-chatbot-em-en.js` | ~450 | EN chatbot widget (hasSponsor EN, en-GB locale) |
| `prompts/chatbot/*_em_en.txt` | 3 files | EN chatbot prompts (hybride, pitch, SQL generator) |
| `tests/test_en_routes.py` | ~220 | 18 tests: EN pages + static JS serving |

Other changes:
- `main.py`: trailing slash redirect middleware, EN router registration
- `services/chat_utils.py`: `_get_sponsor_if_due(history, lang)` — bilingual sponsor text
- `services/chat_pipeline_em.py`: `lang=lang` passthrough to sponsor function
- All HTML pages: "Moteurs"/"Engines" → "Modules" (34 occurrences across 31 files)
- All EN pages: SEO meta tags (OG, Twitter Card, JSON-LD), canonical + hreflang alternates
- All FR EM pages: added hreflang `en` alternates + lang-switch button

**Result**: 38 files changed, +9368 lines, 455 → 473 tests, 0 failures.

### Cumulative Impact

| Metric | Before P1 | After P11 |
|--------|-----------|-----------|
| `api_chat.py` | 2014L monolith | 82L wrapper |
| `api_chat_em.py` | 1668L monolith | 73L wrapper |
| `stats_service.py` + `em_stats_service.py` | 1418L duplicated | 978L (base class + wrappers) |
| Route duplication (data+analyse) | ~2600L | ~1430L unified + ~400L wrappers |
| Database driver | PyMySQL (sync + 68 to_thread) | aiomysql (native async) |
| Cache | In-memory dict | Redis async + in-memory fallback |
| Security headers | Basic CSP | CSP + HSTS preload + COOP + Permissions-Policy |
| i18n | FR only | FR + EN (GB) for EuroMillions (Phase 11) |
| Tests | 248 | **473** |
| Services modules | 10 | **21** |
### Earlier Development History (Condensed)

| Period | Key Milestones |
|--------|----------------|
| 2026-02-06 | Modular extraction: main.py 1920 → 184 lines (3 refactor passes) |
| 2026-02-08-09 | Audit phases: code quality, UNION ALL, rate limiting, circuit breaker, security headers → Score 4.9 → 7.2 |
| 2026-02-10-11 | Chatbot Text-to-SQL (4 phases), temporal filters (22 patterns), sponsor system, session persistence, GA4 tracking, Phase 0 continuation |
| 2026-02-12 | UI harmonization: layout alignment, navigation buttons, scroll-to-top, chatbot on 6 pages |
| 2026-02-14 | EuroMillions (5 phases): DB import (729 draws), API layer (15 endpoints), frontend (7 pages), chatbot EM (1668L), META ANALYSE EM (dual graphs + 15 prompts + PDF) |
| 2026-02-14 | HYBRIDE rename: `HYBRIDE_OPTIMAL_V1` → `HYBRIDE` across 62 files |
| 2026-02-27 | Phase 11: EuroMillions English (GB) — 7 EN pages, 6 EN JS, EN chatbot, i18n infra, hreflang, 473 tests |

---

## 12. Project Status

| Area | Status | Notes |
|------|--------|-------|
| Backend (FastAPI + aiomysql) | Stable | ~660L orchestrator, 16 routers, native async DB (Phase 5), 12 middlewares |
| Unified Routes | Stable | `/api/{game}/...` with `game = loto \| euromillions` (Phase 10), backward compat preserved |
| HYBRIDE Engine (Loto) | Stable | Scoring, constraints, badges functional |
| HYBRIDE Engine (EuroMillions) | Stable | 5 boules [1-50] + 2 etoiles [1-12] |
| HYBRIDE Chatbot (Loto) | Stable | Modular: 4 service modules (Phase 1). 12-phase detection, Text-to-SQL, session persistence, GA4 tracking, sponsor system. 6 pages. |
| HYBRIDE Chatbot (EuroMillions) | Stable | Modular: 4 service modules (Phase 4). Same architecture as Loto. 7 FR + 7 EN pages (Phase 11). Isolated sessionStorage. EN response pools + EN prompts. |
| i18n / Multilang | Partial | EuroMillions EN (GB) version live (Phase 11). 7 EN pages, 6 EN JS, EN chatbot. Loto EN not yet implemented. Remaining FR residue: badges, pitch lang chain, META prompts, PDF, rating popup. |
| Stats Layer | Stable | Base class (Phase 2): 770L base + 2 thin wrappers, GameConfig-driven |
| META ANALYSE 75 (Loto) | Stable | Async Gemini enrichment + PDF export, circuit breaker fallback. 18 Loto prompt keys. |
| META ANALYSE 75 (EM) | Stable | Dual graphs, EM Gemini enrichment, EM PDF (2x2 matplotlib), 14 EM prompt keys. |
| Cache | Stable | Redis async + in-memory fallback (Phase 6). PDF off-thread. |
| Testing | Active | **473 tests** (pytest, 20 test files, ~5100L), CI integration |
| Security | Hardened | CSP+HSTS preload+COOP (Phase 7), aiomysql parameterized queries, rate limiting, correlation IDs |
| SEO | Stable | Schema.org Dataset (Phase 7), bankability T4 pivot (Phase 8), structured data, canonical redirects |
| Mobile responsive | Stable | Fullscreen chatbot, viewport sync, safe-area support |

---

## 13. Performance Metrics

Not formally benchmarked yet.

Observable characteristics based on development usage:

- `/api/meta-analyse-local` typically responds in < 300ms (Cloud SQL aggregate queries)
- Gemini API calls (`/api/meta-analyse-texte`, `/api/hybride-chat`) are bound by external latency (5-15s typical)
- Static assets benefit from cache headers (7-30 days depending on type)
- No client-side performance profiling has been conducted

---

## 14. Known Limitations

- **Two database tables** — Draw data split into `tirages` (Loto) and `tirages_euromillions` (EM) in same `lotofrance` database. No partitioning, no read replicas.
- **Redis optional** — `services/cache.py` falls back to per-process in-memory cache if `REDIS_URL` absent (not shared across 2 workers in fallback mode).
- **Gemini dependency** — META ANALYSE and chatbot depend on an external API. Mitigated by circuit breaker + fallback messages, but degraded experience when open.
- **Minimal monitoring** — Production observability relies on Cloud Run metrics + JSON structured logs with correlation IDs. No APM or alerting.
- **Test coverage** — 473 tests across 20 files. Core engine, chat pipeline, stats, insult/OOR detection well covered. Some route handlers and PDF have lower coverage.
- **i18n partial** — EuroMillions EN version live but 5 FR residue areas remain: badges (hardcoded FR in `generer_badges()`), pitch lang chain (schema missing `lang` field), META prompts (15 FR-only prompt files), PDF (26 hardcoded FR strings in `em_pdf_generator.py`), rating popup (5 FR strings in `rating-popup.js`).

---

## 15. Audit Score History

| Audit | Score | Delta | Key Changes |
|-------|-------|-------|-------------|
| V1 (initial) | 4.9 | -- | Baseline assessment |
| V2 | 5.3 | +0.4 | Code quality improvements |
| V3 | 6.3 | +1.0 | Major refactoring (3 phases) |
| V4 (quick wins) | 6.5 | +0.2 | Rate limiting, UNION ALL, .dockerignore |
| V5 (critique) | 6.7 | +0.2 | asyncio.to_thread all DB, SQL injection fix |
| V5b (securite) | 6.8 | +0.1 | X-Request-ID sanitized, prod/dev deps split |
| V5c (tests+infra) | 7.1 | +0.3 | Tests, CI pipeline, circuit breaker, 2 workers |
| **V6 (credentials)** | **7.2** | **+0.1** | **Credential verification confirmed, full 6-section audit** |

**Note**: Phases 1-11 were implemented post-audit. No formal re-audit has been conducted since V6.

### V6 Section Scores (10/02/2026)

| Section | Score /10 |
|---------|-----------|
| Architecture & Structure | 7.5 |
| Security & Credentials | 8.0 |
| Performance & Resilience | 7.0 |
| Tests & Quality | 6.5 |
| Maintainability & Documentation | 7.5 |
| Deployment & Infrastructure | 6.5 |
| **Global Average** | **7.2** |

### Priority axes to reach 8.0+

| Priority | Action | Estimated Impact |
|----------|--------|------------------|
| P0 | Raise test coverage to 60%+ (api_analyse, api_pdf, api_tracking) | +0.3 |
| P1 | Add monitoring/alerting (Cloud Monitoring or Datadog) | +0.2 |
| P1 | Add staging environment | +0.1 |
| P2 | Configure linting (ruff) + type checking (mypy) in CI | +0.1 |
| ~~P2~~ | ~~Extract chat detection regex into a dedicated service~~ | ✅ Done (Phase 1+4: chat_detectors.py) |
| ~~P3~~ | ~~Deduplicate analyze-custom-grid / analyze_grille_for_chat~~ | ✅ Done (Phase 10: unified routes) |
| P3 | Migrate gcr.io to Artifact Registry | +0.05 |

---

*Updated by JyppY & Claude Opus 4.6 — 27/02/2026 (v8.0: Phase 11 — EuroMillions English (GB) multilang: 7 EN pages, 6 EN JS, EN chatbot pipeline, i18n infra, hreflang, trailing slash middleware, "Moteurs"→"Modules" rename. 473 tests, 21 services, 16 routers. Previous: Phases 1-10 — chat modularization, stats base class, aiomysql async, Redis cache, Schema.org+CSP, SEO bankability, unified routes.)*
