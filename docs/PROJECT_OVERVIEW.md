# LotoIA - Technical Overview

> Statistical analysis platform for the French Loto and EuroMillions, powered by the HYBRIDE_OPTIMAL_V1 engine.

---

## 1. Project Tree

```
hybride-api/
│
├── main.py                              # FastAPI orchestrator (~340 lines)
├── schemas.py                           # Pydantic models — Loto API payloads
├── em_schemas.py                        # Pydantic models — EuroMillions API payloads
├── db_cloudsql.py                       # Cloud SQL connection manager + async helpers
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
├── .env                                 # Local environment variables (excluded from git+Docker)
├── requirements-dev.txt                 # Dev/test dependencies (pytest, pytest-asyncio, pytest-cov)
├── SEO_CHECKLIST.md                     # SEO audit checklist
├── SEO_SNIPPETS.md                      # SEO code snippets reference
├── SEO_STRATEGY.md                      # SEO strategy document
│
├── routes/                              # API & page routers (APIRouter)
│   ├── __init__.py                      # Package init
│   ├── pages.py                         # 21 HTML page routes (SEO clean URLs)
│   ├── api_data.py                      # Data endpoints (tirages, stats, heat)
│   ├── api_analyse.py                   # Analysis endpoints (generate, meta-analyse)
│   ├── api_gemini.py                    # Gemini AI text enrichment endpoint
│   ├── api_pdf.py                       # PDF generation endpoint (ReportLab)
│   ├── api_tracking.py                  # Analytics tracking endpoints (grid, ads)
│   ├── api_chat.py                      # HYBRIDE chatbot endpoint — Loto (12-phase detection + Text-to-SQL)
│   ├── api_chat_em.py                   # HYBRIDE chatbot endpoint — EuroMillions (12-phase detection + Text-to-SQL)
│   ├── em_data.py                       # EuroMillions data endpoints (tirages, stats, heat)
│   └── em_analyse.py                    # EuroMillions analysis endpoints (generate, meta-analyse, custom grid)
│
├── services/                            # Business logic layer
│   ├── __init__.py                      # Package init
│   ├── cache.py                         # In-memory TTL cache (1h, thread-safe)
│   ├── circuit_breaker.py               # Gemini circuit breaker (3 fails → 60s open)
│   ├── gemini.py                        # Gemini 2.0 Flash API client (httpx async)
│   ├── stats_service.py                 # Stats business logic — Loto (extracted from routes)
│   ├── em_stats_service.py              # Stats business logic — EuroMillions (em: cache prefix + chatbot grille/pitch)
│   ├── pdf_generator.py                 # ReportLab PDF generation (META75 report)
│   └── prompt_loader.py                 # Dynamic prompt loader (22 keys, 23 prompt files)
│
├── engine/                              # Core analysis engine
│   ├── __init__.py                      # Package init
│   ├── hybride.py                       # HYBRIDE_OPTIMAL_V1 algorithm (Loto)
│   ├── hybride_em.py                    # HYBRIDE_OPTIMAL_V1_EM algorithm (EuroMillions)
│   ├── stats.py                         # Statistical analysis module
│   ├── models.py                        # Pydantic data models
│   ├── db.py                            # Database connection proxy
│   └── version.py                       # Version constant (1.0.0)
│
├── prompts/                             # Gemini contextual prompts (20 files)
│   ├── chatbot/                         # HYBRIDE chatbot prompts
│   │   ├── prompt_hybride.txt           # Multi-section prompt — Loto (identity, FAQ, rules, BDD)
│   │   ├── prompt_pitch_grille.txt      # Pitch prompt — Loto (personalized grid commentary)
│   │   ├── prompt_sql_generator.txt     # SQL Generator prompt — Loto (Text-to-SQL, schema, few-shot examples)
│   │   ├── prompt_hybride_em.txt        # Multi-section prompt — EuroMillions (identity, FAQ, rules, BDD)
│   │   ├── prompt_pitch_grille_em.txt   # Pitch prompt — EuroMillions (5 nums + 2 étoiles commentary)
│   │   └── prompt_sql_generator_em.txt  # SQL Generator prompt — EuroMillions (tirages_euromillions schema)
│   ├── tirages/                         # Window-based prompts (by draw count)
│   │   ├── prompt_100.txt               # Prompt for 100-draw window
│   │   ├── prompt_200.txt               # Prompt for 200-draw window
│   │   ├── prompt_300.txt               # Prompt for 300-draw window
│   │   ├── prompt_400.txt               # Prompt for 400-draw window
│   │   ├── prompt_500.txt               # Prompt for 500-draw window
│   │   ├── prompt_600.txt               # Prompt for 600-draw window
│   │   ├── prompt_700.txt               # Prompt for 700-draw window
│   │   ├── prompt_800.txt               # Prompt for 800-draw window
│   │   └── prompt_global.txt            # Prompt for GLOBAL window (fallback)
│   └── annees/                          # Year-based prompts
│       ├── prompt_1a.txt                # Prompt for 1-year window
│       ├── prompt_2a.txt                # Prompt for 2-year window
│       ├── prompt_3a.txt                # Prompt for 3-year window
│       ├── prompt_4a.txt                # Prompt for 4-year window
│       ├── prompt_5a.txt                # Prompt for 5-year window
│       ├── prompt_6a.txt                # Prompt for 6-year window
│       └── prompt_global.txt            # Prompt for GLOBAL window (annees fallback)
│
├── ui/                                  # Frontend layer
│   ├── launcher.html                    # Entry page (route: /)
│   ├── accueil.html                     # Welcome page (/accueil)
│   ├── loto.html                        # Grid generator (/loto)
│   ├── simulateur.html                  # Grid simulator (/simulateur)
│   ├── statistiques.html                # Statistics dashboard (/statistiques)
│   ├── historique.html                  # Draw history (/historique)
│   ├── faq.html                         # FAQ (/faq)
│   ├── news.html                        # News & updates (/news)
│   ├── moteur.html                      # Engine documentation (/moteur)
│   ├── methodologie.html                # Methodology docs (/methodologie)
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
│   └── static/                          # Static assets
│       ├── style.css                    # Main stylesheet
│       ├── simulateur.css               # Simulator-specific styles
│       ├── legal.css                    # Legal pages styling
│       ├── sponsor-popup.css            # Sponsor popup styling
│       ├── sponsor-popup75.css          # META ANALYSE 75 popup styling
│       ├── meta-result.css              # META ANALYSE result popup styling
│       ├── hybride-chatbot.css          # HYBRIDE Chatbot widget styles
│       ├── app.js                       # Main application logic
│       ├── simulateur.js                # Simulator UI logic
│       ├── sponsor-popup75.js           # META ANALYSE 75 popup (Gemini + PDF flow)
│       ├── hybride-chatbot.js           # HYBRIDE Chatbot widget — Loto (IIFE, vanilla JS, sessionStorage, GA4 tracking)
│       ├── hybride-chatbot-em.js       # HYBRIDE Chatbot widget — EuroMillions (IIFE, /api/euromillions/hybride-chat, hybride-history-em)
│       ├── theme.js                     # Dark/light mode toggle
│       ├── analytics.js                 # GDPR-compliant analytics
│       ├── cookie-consent.js            # Cookie consent management
│       ├── faq.js                       # FAQ accordion logic
│       ├── scroll.js                    # Scroll-to-top button (all pages)
│       ├── version-inject.js            # Dynamic version injection from /api/version
│       ├── sponsor-popup.js             # Sponsor popup logic (grids)
│       ├── og-image.jpg                 # Open Graph image (1200x630)
│       ├── og-image.webp                # Open Graph image (WebP)
│       ├── hero-bg.jpg                  # Hero background image
│       ├── hero-bg.webp                 # Hero background (WebP)
│       ├── Hybride-audit.png            # HYBRIDE assistant image (simulator)
│       ├── Hybride-audit-horizontal.png # HYBRIDE assistant image (horizontal)
│       ├── hybride-chatbot-lotoia.jpg   # HYBRIDE chatbot branding (JPG)
│       ├── hybride-chatbot-lotoia.webp  # HYBRIDE chatbot branding (WebP)
│       ├── hybride-chatbot-lotoia.png   # HYBRIDE chatbot branding (PNG)
│       ├── hybride-moteur.png            # HYBRIDE mascot (generator page)
│       ├── hybride-stat.png             # HYBRIDE mascot (statistics page)
│       ├── favicon.ico                  # Favicon (static copy)
│       └── favicon.svg                  # Favicon SVG (static copy)
│
├── tests/                               # Unit tests (pytest)
│   ├── conftest.py                      # Shared fixtures (SmartMockCursor, cache clear)
│   ├── test_models.py                   # Pydantic models + CONFIG weights (11 tests)
│   ├── test_hybride.py                  # HYBRIDE engine tests (21 tests)
│   ├── test_stats.py                    # engine/stats.py tests (9 tests)
│   ├── test_services.py                 # cache + stats_service tests (11 tests)
│   ├── test_routes.py                   # FastAPI route tests (10 tests)
│   └── test_circuit_breaker.py          # Circuit breaker tests (9 tests)
│
├── config/                                # Runtime configuration
│   ├── __init__.py                      # Package init
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

### HYBRIDE_OPTIMAL_V1 Engine

| Feature | Detail |
|---------|--------|
| **Dual Time Windows** | Primary (5 years, 60%) + Recent (2 years, 40%) |
| **Scoring Formula** | `Score = 0.7 * Frequency + 0.3 * Lag` |
| **Generation Modes** | Conservative (70/30), Balanced (60/40), Recent (40/60) |
| **Constraint Validation** | Even/Odd ratio, Low/High split, Sum range [70-150], Dispersion, Consecutive limit |
| **Star Rating** | 1-5 stars based on conformity score |
| **Badges** | Auto-generated labels (Equilibre, Chaud, Froid, etc.) |

### HYBRIDE_OPTIMAL_V1_EM Engine (EuroMillions)

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
| **Router** | `/api/euromillions` prefix, 15 endpoints (12 data + 3 analysis) |

### META ANALYSE 75 Module

| Feature | Detail |
|---------|--------|
| **Local Analysis** | Real-time stats computed on Cloud SQL (< 300ms) |
| **Window Modes** | By draw count (100-800, GLOBAL) or by years (1A-6A, GLOBAL) |
| **Gemini AI Enrichment** | Text reformulation via Gemini 2.0 Flash API |
| **Dynamic Prompts** | 20 contextual prompt files (9 tirages + 8 annees + 3 chatbot incl. SQL Generator) |
| **PDF Export** | Professional META75 report via ReportLab (A4, DejaVuSans fonts) |
| **Sponsor Popup** | 30-second branded timer with animated console |
| **Race Condition Handling** | Promise.race with 28s global timeout from T=0 |

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
| **Backend** | `api_chat_em.py` (1668 lines): 12-phase detection pipeline identical to Loto chatbot, fully adapted for EuroMillions (boules 1-50, 2 étoiles 1-12, table tirages_euromillions, draw days mardi/vendredi) |
| **Prompts** | 3 dedicated EM prompts: `prompt_hybride_em.txt`, `prompt_sql_generator_em.txt`, `prompt_pitch_grille_em.txt` |
| **Pitch** | `POST /api/euromillions/pitch-grilles` (1-5 grids, JSON pitchs with étoiles support) |
| **Imports** | Generic utilities imported from `api_chat.py` (continuation, sponsor, insult/compliment detection, SQL validation, clean_response, format_date_fr, temporal filter). EM-specific functions and response pools defined locally. |

### HYBRIDE BDD Integration (Chatbot ↔ Live Database)

The chatbot is connected to Cloud SQL in real-time via a 7-phase detection pipeline:

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
|  1. CORSMiddleware (allowed origins)              |
|  2. GZipMiddleware (>500 bytes)                   |
|  3. correlation_id_middleware (X-Request-ID)       |
|  4. Rate Limiting (slowapi, 10/min on chat)       |
|  5. Security Headers (CSP, HSTS, X-Frame-Options) |
|  6. canonical_www_redirect (SEO 301)              |
|  7. add_cache_headers (by content type)           |
|  8. redirect_ui_html_to_seo (URL dedup 301)       |
+--------------------------------------------------+
         |
         v
+--------------------------------------------------+
|              FASTAPI ROUTES (APIRouter)           |
|                                                   |
|  routes/pages.py         21 HTML/SEO pages        |
|  routes/api_data.py      DB & stats endpoints     |
|  routes/api_analyse.py   Engine & META analyse    |
|  routes/api_gemini.py    Gemini AI enrichment     |
|  routes/api_pdf.py       PDF generation           |
|  routes/api_tracking.py  Analytics tracking       |
|  routes/api_chat.py      HYBRIDE chatbot Loto      |
|  routes/api_chat_em.py   HYBRIDE chatbot EM        |
|  routes/em_data.py       EM data & stats endpoints |
|  routes/em_analyse.py    EM engine & analysis      |
|  main.py                 health, SEO 301           |
+--------------------------------------------------+
         |
         v
+--------------------------------------------------+
|              SERVICES LAYER                       |
|                                                   |
|  services/gemini.py          Gemini 2.0 Flash API |
|  services/cache.py           In-memory TTL cache  |
|  services/circuit_breaker.py Gemini circuit breaker|
|  services/stats_service.py   Stats business logic  |
|  services/em_stats_service.py EM stats (em: cache) |
|  services/pdf_generator.py   ReportLab PDF engine  |
|  services/prompt_loader.py   Dynamic prompt loader|
+--------------------------------------------------+
         |
         v
+--------------------------------------------------+
|              ENGINE LAYER                         |
|                                                   |
|  engine/hybride.py      HYBRIDE_OPTIMAL_V1 (Loto) |
|  engine/hybride_em.py   HYBRIDE_OPTIMAL_V1_EM (EM)|
|  engine/stats.py        Descriptive statistics     |
|  engine/models.py       Pydantic validation        |
+--------------------------------------------------+
         |
         v
+--------------------------------------------------+
|              DATABASE LAYER                       |
|                                                   |
|  db_cloudsql.py                                   |
|    Local: TCP via Cloud SQL Proxy (127.0.0.1)     |
|    Prod:  Unix socket (/cloudsql/...)             |
|    Async: asyncio.to_thread() on ALL DB calls     |
|    Helpers: async_query, async_fetchone, async_call|
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
main.py (~340 lines) — Orchestrator
    ├── app = FastAPI() + lifespan (shared httpx.AsyncClient)
    ├── Middlewares (CORS, correlation ID, security headers, canonical, cache, SEO)
    ├── Rate limiting (slowapi, 10/min on chat endpoints)
    ├── Static mounts (/ui, /static)
    ├── app.include_router() x10 (7 Loto + 3 EuroMillions)
    ├── /health (async + asyncio.wait_for 5s timeout + to_thread)
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
    ├── EMPitchGrilleItem
    ├── EMPitchGrillesRequest
    ├── EMChatMessage (role + content)
    ├── EMChatRequest (message + page + history)
    └── EMChatResponse (response + source + mode)

rate_limit.py — Shared slowapi limiter instance

routes/ — 10 routers (7 Loto + 3 EuroMillions)
    ├── pages.py          (171 lines)  21 HTML page routes
    ├── api_data.py      (~1340 lines)  tirages, stats, heat, draw, hybride-stats, pitch context
    ├── api_analyse.py    (498 lines)  generate, ask, meta-analyse-local
    ├── api_gemini.py      (19 lines)  meta-analyse-texte
    ├── api_pdf.py         (37 lines)  meta-pdf
    ├── api_tracking.py   (127 lines)  track-grid, track-ad-*
    ├── api_chat.py     (~1340 lines)  hybride-chat (7-phase detection + contextual continuation + Text-to-SQL + sponsor system), pitch-grilles
    ├── em_data.py        (716 lines)  EuroMillions data endpoints (12 endpoints, prefix /api/euromillions)
    ├── em_analyse.py     (583 lines)  EuroMillions analysis endpoints (3 endpoints, prefix /api/euromillions)
    └── api_chat_em.py  (1668 lines)  EM chatbot (12-phase detection + Text-to-SQL + pitch), prefix /api/euromillions

services/ — 7 services
    ├── cache.py           (~40 lines)  In-memory TTL cache (1h, thread-safe)
    ├── circuit_breaker.py (~80 lines)  Gemini circuit breaker (CLOSED/OPEN/HALF_OPEN)
    ├── gemini.py         (119 lines)  Gemini API client (via circuit breaker)
    ├── stats_service.py  (~200 lines)  Stats business logic — Loto (extracted from routes)
    ├── em_stats_service.py(590 lines)  Stats business logic — EuroMillions (em: cache + chatbot grille/pitch)
    ├── pdf_generator.py  (232 lines)  ReportLab PDF engine
    └── prompt_loader.py   (60 lines)  Prompt file loader (22 keys incl. SQL_GENERATOR + 3 EM chatbot keys)

tests/ — 70 tests (pytest + pytest-cov)
    ├── conftest.py                    Fixtures (SmartMockCursor, cache clear)
    ├── test_models.py     (11 tests)  Pydantic models + CONFIG weights
    ├── test_hybride.py    (21 tests)  HYBRIDE engine (pure + DB-mocked)
    ├── test_stats.py       (9 tests)  engine/stats.py functions
    ├── test_services.py   (11 tests)  cache + stats_service
    ├── test_routes.py     (10 tests)  FastAPI TestClient (health, tirages, chat, correlation ID)
    └── test_circuit_breaker.py (9 tests)  Circuit breaker state machine
```

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
| `app.js` | Grid generation, DB status, result rendering, engine controls |
| `simulateur.js` | Interactive 49-number grid, real-time API scoring |
| `sponsor-popup75.js` | META ANALYSE 75: Gemini chain, PDF export, sponsor timer |
| `theme.js` | Dark/light mode toggle with `localStorage` persistence |
| `analytics.js` | GDPR-compliant analytics (GA4 Consent Mode v2, `LotoIAAnalytics.track()` API) |
| `cookie-consent.js` | Cookie consent banner and preference management |
| `faq.js` | FAQ accordion interactions |
| `scroll.js` | Scroll-to-top button (shows after 300px scroll, all pages including legal) |
| `version-inject.js` | Dynamic version injection from `/api/version` into `.app-version` spans |
| `hybride-chatbot.js` | HYBRIDE chatbot widget — Loto (bubble, chat window, sessionStorage `hybride-history`, GA4 tracking, Gemini API via `/api/hybride-chat`) |
| `hybride-chatbot-em.js` | HYBRIDE chatbot widget — EuroMillions (sessionStorage `hybride-history-em`, Gemini API via `/api/euromillions/hybride-chat`, GA4 `hybride_em_chat_*` events) |
| `sponsor-popup.js` | Sponsor/ad popup for grid generation |

### Theme System

- Toggle via `theme.js` using CSS custom properties (`--theme-*`)
- Persisted in `localStorage`
- All pages include `theme.js` as first script (prevents flash)

### META ANALYSE 75 - Client Flow (sponsor-popup75.js)

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

---

## 6. Tech Stack

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| FastAPI | 0.115.0 | Async web framework |
| Uvicorn | 0.32.0 | ASGI server (2 workers) |
| PyMySQL | 1.1.1 | MySQL/MariaDB driver (sync) |
| httpx | ≥0.27 | Async HTTP client (shared via lifespan) |
| slowapi | ≥0.1.9 | Rate limiting (IP-based, 10/min on chat) |
| tenacity | ≥8.2 | Retry / circuit breaker support |
| python-json-logger | ≥2.0.7 | JSON structured logging |
| ReportLab | 4.1.0 | PDF generation (META75 reports) |
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
| Docker | Container runtime (Python 3.11-slim, 2 Uvicorn workers) |
| Container Registry | Image storage (gcr.io) |

---

## 7. API Summary

### Page Routes (21) — routes/pages.py

| Route | Template |
|-------|----------|
| `GET /` | launcher.html |
| `GET /accueil` | accueil.html |
| `GET /loto` | loto.html |
| `GET /loto/analyse` | loto.html |
| `GET /loto/exploration` | loto.html |
| `GET /loto/statistiques` | statistiques.html |
| `GET /simulateur` | simulateur.html |
| `GET /statistiques` | statistiques.html |
| `GET /historique` | historique.html |
| `GET /faq` | faq.html (dynamic via Cloud SQL) |
| `GET /news` | news.html |
| `GET /moteur` | moteur.html |
| `GET /methodologie` | methodologie.html |
| `GET /disclaimer` | disclaimer.html |
| `GET /mentions-legales` | mentions-legales.html |
| `GET /politique-confidentialite` | politique-confidentialite.html |
| `GET /politique-cookies` | politique-cookies.html |
| `GET /robots.txt` | robots.txt |
| `GET /sitemap.xml` | sitemap.xml |
| `GET /favicon.ico` | favicon.ico |
| `GET /BingSiteAuth.xml` | BingSiteAuth.xml |

### Data Endpoints — routes/api_data.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/database-info` | GET | Full database status and metadata |
| `/api/database-info` | GET | Light database info (FAQ dynamic) |
| `/stats` | GET | Global statistics |
| `/api/stats` | GET | Complete stats (frequencies, lags, heat) |
| `/api/stats/number/{number}` | GET | Individual number analysis (1-49) |
| `/api/stats/top-flop` | GET | Top/bottom frequency rankings |
| `/api/numbers-heat` | GET | Hot/cold/neutral classification |
| `/api/tirages/count` | GET | Total draw count |
| `/api/tirages/latest` | GET | Most recent draw |
| `/api/tirages/list` | GET | Paginated draw history (limit, offset) |
| `/draw/{date}` | GET | Get draw by date (YYYY-MM-DD) |
| `/api/hybride-stats` | GET | Single number stats for chatbot (numero, type) |
| `/api/meta-windows-info` | GET | Dynamic window info (tirages + annees counts & dates) for META sliders |

### Analysis Endpoints — routes/api_analyse.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ask` | POST | Main engine prompt |
| `/generate` | GET | Generate N optimized grids (n, mode) |
| `/api/meta-analyse-mock` | GET | META ANALYSE mock (static test data) |
| `/api/meta-analyse-local` | GET | META ANALYSE local (real Cloud SQL stats) |
| `/api/analyze-custom-grid` | POST | Analyze user-composed grid |

### Gemini Endpoint — routes/api_gemini.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/meta-analyse-texte` | POST | AI text enrichment via Gemini 2.0 Flash |

### PDF Endpoint — routes/api_pdf.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/meta-pdf` | POST | Generate META75 PDF report (ReportLab) |

### Chat Endpoint — routes/api_chat.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/hybride-chat` | POST | HYBRIDE chatbot (7-phase detection incl. contextual continuation, Text-to-SQL, conversational memory, 15s timeout) |
| `/api/pitch-grilles` | POST | Personalized Gemini pitch per grid (1-5 grids, JSON pitchs) |

### Tracking Endpoints — routes/api_tracking.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/track-grid` | POST | Track generated grid |
| `/api/track-ad-impression` | POST | Track ad impression |
| `/api/track-ad-click` | POST | Track ad click (CPA) |

### EuroMillions Data Endpoints (12) — routes/em_data.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/euromillions/tirages/count` | GET | Total EM draw count |
| `/api/euromillions/tirages/latest` | GET | Most recent EM draw |
| `/api/euromillions/tirages/list` | GET | Paginated EM draw history (limit, offset) |
| `/api/euromillions/database-info` | GET | Full EM database status and metadata |
| `/api/euromillions/meta-windows-info` | GET | Dynamic window info for META sliders |
| `/api/euromillions/stats` | GET | Complete EM stats (boules 1-50 + etoiles 1-12 frequencies/lags) |
| `/api/euromillions/numbers-heat` | GET | Hot/cold/neutral classification (boules + etoiles) |
| `/api/euromillions/draw/{date}` | GET | EM draw by date (includes jackpot, nb_joueurs, nb_gagnants_rang1) |
| `/api/euromillions/stats/number/{number}` | GET | Individual boule analysis (1-50) |
| `/api/euromillions/stats/etoile/{number}` | GET | Individual etoile analysis (1-12) |
| `/api/euromillions/stats/top-flop` | GET | Top/bottom frequency rankings (boules + etoiles) |
| `/api/euromillions/hybride-stats` | GET | Single number/etoile stats (numero, type) |

### EuroMillions Analysis Endpoints (3) — routes/em_analyse.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/euromillions/generate` | GET | Generate N optimized EM grids (5 boules + 2 etoiles) |
| `/api/euromillions/meta-analyse-local` | GET | META ANALYSE local for EM (real Cloud SQL stats) |
| `/api/euromillions/analyze-custom-grid` | POST | Analyze user-composed EM grid (nums + etoile1 + etoile2) |

### EuroMillions Chat Endpoints (2) — routes/api_chat_em.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/euromillions/hybride-chat` | POST | HYBRIDE chatbot EM (12-phase detection, Text-to-SQL on tirages_euromillions, grille analysis 5 boules + 2 étoiles, conversational memory, 15s timeout) |
| `/api/euromillions/pitch-grilles` | POST | Personalized Gemini pitch per EM grid (1-5 grids, JSON pitchs with étoiles) |

### Core Endpoints — main.py

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (async, DB 5s timeout, Gemini circuit state, uptime, version) |
| `/api/version` | GET | Returns `{"version": "1.001"}` from `config/version.py` |
| `/analyse` | GET | SEO 301 redirect to /simulateur |
| `/exploration` | GET | SEO 301 redirect to /loto |

---

## 8. Services Layer

### services/cache.py — In-Memory TTL Cache

- **Type**: Dict-based in-memory cache with TTL (default 1h)
- **Thread-safe**: Uses `time.monotonic()` for expiry checks
- **Functions**: `get(key)`, `set(key, value, ttl)`, `clear()`
- **Used by**: `stats_service.py` (Loto) and `em_stats_service.py` (EuroMillions, `em:` prefix) to cache frequency/ecart data from DB

### services/circuit_breaker.py — Gemini Circuit Breaker

- **States**: CLOSED → OPEN → HALF_OPEN → CLOSED
- **Threshold**: 3 consecutive failures → circuit opens for 60s
- **Failures**: httpx.TimeoutException, ConnectError, OSError, HTTP 500+, HTTP 429
- **Half-open**: After timeout, one test request allowed — success closes, failure reopens
- **Error**: Raises `CircuitOpenError` when circuit is open (callers do fallback)
- **Used by**: `gemini.py`, `api_chat.py` (both hybride-chat and pitch-grilles endpoints)

### services/stats_service.py — Stats Business Logic

- **Extracted from**: `routes/api_data.py` (separation of concerns)
- **Functions**: `get_numero_stats()`, `get_classement_numeros()`, `get_comparaison_numeros()`, `get_numeros_par_categorie()`, `analyze_grille_for_chat()`
- **Caching**: Uses `services/cache.py` for frequency/ecart data (1h TTL)
- **SQL optimization**: `UNION ALL` queries for batch frequency/ecart calculations

### services/em_stats_service.py — EuroMillions Stats Business Logic

- **Mirrors**: `stats_service.py` structure, adapted for EuroMillions ranges
- **Type system**: `"boule"` (1-50) and `"etoile"` (1-12) — distinct from Loto's `"principal"` / `"chance"`
- **Cache prefix**: All keys prefixed `em:` (e.g., `em:freq:boule:None`, `em:ecarts:etoile`)
- **Functions**: `get_numero_stats()`, `get_classement_numeros()`, `get_comparaison_numeros()`, `get_numeros_par_categorie()`, `analyze_grille_for_chat()`, `prepare_grilles_pitch_context()`
- **SQL**: `UNION ALL` of 5 boule columns or 2 etoile columns for frequency calculations
- **Chatbot**: `analyze_grille_for_chat(nums, etoiles)` — full grille analysis (somme ideal 75-175, bas=1-25, dispersion, conformité, badges). `prepare_grilles_pitch_context(grilles)` — multi-grille stats for Gemini pitch.
- **Table**: `tirages_euromillions` (same DB `lotofrance`)

### services/gemini.py — Gemini AI Client

- **API**: Google Gemini 2.0 Flash (`generativelanguage.googleapis.com/v1beta`)
- **Transport**: httpx.AsyncClient (shared via app lifespan, circuit breaker wrapped)
- **Auth**: API key via `GEM_API_KEY` or `GEMINI_API_KEY` env var
- **Prompt**: Loaded dynamically from `prompts/` via prompt_loader
- **Fallback chain**: Gemini enriched → Local text (if API fails/timeout) → Circuit open fallback
- **Output**: `{"analysis_enriched": "...", "source": "gemini_enriched"|"hybride_local"|"fallback"|"fallback_circuit"}`
- **Shared by**: META ANALYSE (api_gemini.py) + HYBRIDE chatbot (api_chat.py) via `GEMINI_MODEL_URL`

### services/pdf_generator.py — ReportLab PDF Engine

- **Format**: A4 portrait, professional layout
- **Font system**: DejaVuSans (Linux/Cloud Run) -> Vera (ReportLab fallback)
  - 3 variants: Regular, Bold, Oblique
  - Multi-path resolution: reportlab/fonts/ -> /usr/share/fonts/ -> Vera fallback
- **Content**: Title, analysis block, graph image, info block, sponsor with mailto link, signature, disclaimer, footer
- **Text**: Full UTF-8 support (French accents via `_utf8_clean()`)
- **Output**: `io.BytesIO` containing the PDF

### services/prompt_loader.py — Dynamic Prompt System

- **23 prompt files** mapped via `PROMPT_MAP` dict (22 keys + 1 annees fallback)
- **Keys**: 100, 200, 300, 400, 500, 600, 700, 800, GLOBAL, 1A, 2A, 3A, 4A, 5A, 6A, CHATBOT, PITCH_GRILLE, SQL_GENERATOR, CHATBOT_EM, PITCH_GRILLE_EM, SQL_GENERATOR_EM
- **Fallback**: `prompt_global.txt` if specific file missing
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
| `K_SERVICE` | Auto | — | Set by Cloud Run (production detection) |

### Environment Detection

- **Production**: `K_SERVICE` is set -> Unix socket connection (`/cloudsql/...`)
- **Local**: `K_SERVICE` absent -> TCP connection via Cloud SQL Proxy

---

## 10. Security Features

| Feature | Implementation |
|---------|---------------|
| SQL Injection | Parameterized queries via PyMySQL |
| CORS | CORSMiddleware with explicit allowed origins |
| CSP | Content-Security-Policy header (script-src, style-src, img-src) |
| Security Headers | X-Content-Type-Options, X-Frame-Options, Strict-Transport-Security |
| Rate Limiting | slowapi IP-based limiter (10/min on chat, X-Forwarded-For aware) |
| Correlation ID | X-Request-ID per request (generated or forwarded) for tracing |
| Circuit Breaker | Gemini API protection (3 fails → 60s open → graceful fallback) |
| Compression | GZipMiddleware (>500 bytes) |
| Scraper Blocking | robots.txt (AhrefsBot, SemrushBot, GPTBot, CCBot) |
| GDPR Compliance | Cookie consent system, no tracking without approval |
| URL Deduplication | 301 redirect `/ui/*.html` → clean routes |
| Canonical URLs | 301 redirect `www` → root domain |
| HTTPS | Enforced via Cloud Run + `og:image:secure_url` |
| API Key Protection | Gemini key stored in env vars, never exposed to client |

---

## 11. Refactoring History

| Phase | Date | Description | Impact |
|-------|------|-------------|--------|
| Refactor 1/3 | 2026-02-06 | Extract HTML page routes | main.py 1920 → 1758 lines |
| Refactor 2/3 | 2026-02-06 | Extract services (Gemini, PDF, prompts) | main.py 1758 → 1406 lines |
| Refactor 3/3 | 2026-02-06 | Extract API routes + schemas.py | main.py 1406 → 184 lines |
| Audit Phase 1 | 2026-02-08 | R-1→R-10: Code quality (type hints, docstrings, error handling) | Score 5.3 → 6.2 |
| Audit Phase 2a | 2026-02-08 | R-12,R-13,R-16: Rate limiting, shared httpx, CORS | Score 6.2 → 6.8 |
| Audit Phase 2b | 2026-02-08 | R-11: N+1 query rewrites (UNION ALL pattern) | Score 6.8 → 7.4 |
| Audit Phase 2c | 2026-02-08 | R-14,R-15,R-17: TTL cache, service extraction, JSON logging | Score 7.4 → 7.8 |
| Audit Phase 3a | 2026-02-09 | R-18: pytest setup + engine unit tests (40 tests) | Test coverage established |
| Audit Phase 3b | 2026-02-09 | R-19,R-20: Service + route tests (21 tests) | 70 tests total, 0 failures |
| Audit Phase 3c | 2026-02-09 | R-21,R-22: CI test step + pytest-cov (42% coverage) | CI pipeline: Build → Test → Deploy |
| Audit Phase 4a | 2026-02-09 | R-24,R-27: Multi-workers + circuit breaker | 2 Uvicorn workers, Gemini resilience |
| Audit Phase 4b | 2026-02-09 | R-26,R-28: Correlation ID, improved /health, cleanup | main.py ~320 lines, seo.py removed |
| Quick Wins | 2026-02-09 | Rate limiting, N+1 UNION ALL, contextvars, tenacity removal, .dockerignore | Score 6.3 → 6.5 |
| Phase Critique | 2026-02-09 | asyncio.to_thread() ALL DB calls, /health async+timeout 5s, LIMIT parameterized, SQL indexes, logs debug | Event loop unblocked, SQL injection fix |
| Phase Securite | 2026-02-09 | Split requirements prod/dev, /ask async, _get_all_ecarts SQL, X-Request-ID sanitized, .dockerignore dev deps | Score 6.8 → 7.0, attack surface reduced |
| **Audit V6** | 2026-02-10 | Credential verification (.env never in git, excluded from Docker, injected by Cloud Run). Full 6-section audit. | **Score 7.1 → 7.2**, security posture confirmed |
| **Chatbot Phase 1** | 2026-02-10 | Text-to-SQL fallback: Gemini generates SQL from natural language, Python validates & executes | Phase SQL added as 6th detection phase |
| **Chatbot Phase 2** | 2026-02-10 | Conversational memory: history passed to SQL Generator for implicit reference resolution | Follow-up questions ("et la première fois ?") now work |
| **Chatbot Phase 3** | 2026-02-10 | Temporal filter bypass (`_has_temporal_filter`), structured monitoring `[TEXT2SQL]`, rate-limiting (10/session), SQL validation hardening (comments, length) | Priority bug fixed, production-ready |
| **Chatbot Temporal** | 2026-02-10 | Temporal resolution rules in SQL prompt: month without year defaults to current year | "en janvier" = janvier 2026, not all Januarys |
| **Chatbot v4.1** | 2026-02-11 | Expanded `_has_temporal_filter()` (22 patterns: "dans/pour/sur/de l'année", etc.), multi-numéros SQL few-shot, simulator redirect fallback | All French temporal formulations detected at first attempt |
| **Sponsor System** | 2026-02-11 | Post-Gemini sponsor injection (`config/sponsors.json`), 2 alternating styles, configurable frequency, does not pollute history | Monetization-ready, toggleable via `enabled: false` |
| **Session Persistence** | 2026-02-11 | `sessionStorage` for chatHistory (max 50 msgs), restore on page navigation, 🗑️ clear button, cache buster `?v=4.2` | Conversation survives page changes within same tab |
| **CSP Fix** | 2026-02-11 | Added `*.googletagmanager.com`, `*.google.com` to img-src; `*.analytics.google.com` to connect-src in main.py | GA4/GTM pixels no longer blocked by CSP |
| **GA4 Chatbot Tracking** | 2026-02-11 | 5 custom events in `hybride-chatbot.js` via `LotoIAAnalytics.track()`: open, message, session, sponsor_view, clear. Safe wrapper. Cache buster `?v=4.3` | Sponsor engagement + session metrics measurable in GA4 |
| **Chatbot Phase 0 — Continuation** | 2026-02-11 | Short replies ("oui", "non", "vas-y", "détaille"...) now enriched with conversational context before Gemini call. All regex/SQL phases bypassed. `CONTINUATION_PATTERNS` regex + `_enrich_with_context()`. `[CONTEXTE CONTINUATION]` tag cleaned from responses. | Fixes bug where "oui" after "Tu veux creuser ?" was misrouted to grid generator |
| **UI — Chatbot & Scroll** | 2026-02-12 | HYBRIDE chatbot deployed on news.html + faq.html (6 pages total). Scroll-to-top added to all pages (news, faq, mentions-legales, confidentialité, cookies, disclaimer). Legal pages: scroll button at `bottom: 20px`; other pages: `bottom: 80px` (above chatbot). | Chatbot coverage: 4 → 6 pages. Scroll-to-top: all pages |
| **UI — Navigation Buttons** | 2026-02-12 | 4-button navigation system (Auditer, Explorer, Statistiques, Actualités) harmonized across all main pages. Accueil uses inline CSS (`hero-actions`/`hero-btn`); other pages use `style.css` (`loto-hero-actions`/`loto-hero-btn`). `flex-wrap: nowrap` enforces single-line desktop. Mobile < 599px: horizontal scroll with hint text. | Consistent nav UX across all pages |
| **UI — News Harmonization** | 2026-02-12 | news.html aligned with /loto layout: `loto-hero-header` nav buttons, Google gradient bar on first `.news-post` via `::before`, jointure visuelle (header `padding-bottom: 80px` + container `margin-top: -50px; padding-top: 0`). | news.html matches /loto visual pattern |
| **UI — Layout Alignment** | 2026-02-12 | All main pages aligned on /loto jointure model: `margin-top: -50px; padding-top: 0`. Fixed news.html (+40px parasitic padding from `.container`), simulateur.css (`-30px` → `-50px`). Statistiques already aligned. Accueil uses own layout (flush jointure). | Uniform 30px gap buttons → gradient bar → content |
| **EuroMillions Phase 1** | 2026-02-14 | CSV import: 729 EuroMillions draws (2019-02-15 → 2026-02-06) exported to `euromillions_import.sql` (CREATE TABLE + batched INSERTs) | BDD `tirages_euromillions` operational |
| **EuroMillions Phase 2** | 2026-02-14 | Full EM API layer: `em_schemas.py` (47 lines), `engine/hybride_em.py` (440 lines), `services/em_stats_service.py` (390 lines), `routes/em_data.py` (716 lines, 12 endpoints), `routes/em_analyse.py` (583 lines, 3 endpoints). Zero modification to existing Loto files (except main.py +2 router mounts). | 15 EM endpoints operational, 31/31 local tests passed |
| **EuroMillions Phase 3** | 2026-02-14 | Full EM frontend: 7 HTML pages (accueil-em, euromillions, simulateur-em, statistiques-em, historique-em, faq-em, news-em), `routes/em_pages.py`, SEO (clean URLs, sitemap, JSON-LD, OG tags), launcher activation | 7 EM pages + 7 SEO routes operational |
| **EuroMillions Phase 4** | 2026-02-14 | Chatbot HYBRIDE EM: `routes/api_chat_em.py` (1668 lines, 12-phase detection + Text-to-SQL on tirages_euromillions), `hybride-chatbot-em.js` (277 lines, isolated storage `hybride-history-em`), 3 EM prompts (hybride, sql_generator, pitch_grille), `em_stats_service.py` +2 functions (analyze_grille_for_chat, prepare_grilles_pitch_context), `em_schemas.py` +3 schemas (EMChatMessage/Request/Response), widget integrated on 7 EM pages, main.py wired. Generic utilities imported from api_chat.py. | 2 EM chat endpoints operational, 8/8 tests passed (pitch requires MySQL) |

---

## 12. Project Status

| Area | Status | Notes |
|------|--------|-------|
| Backend (FastAPI + Cloud SQL) | Stable | All endpoints operational (Loto + EuroMillions), audit refactoring complete (12 phases) |
| HYBRIDE_OPTIMAL_V1 Engine (Loto) | Stable | Scoring, constraints, badges functional |
| HYBRIDE_OPTIMAL_V1_EM Engine (EuroMillions) | Stable | 5 boules [1-50] + 2 etoiles [1-12], 15 endpoints, 31/31 tests passed. No Loto regression. |
| HYBRIDE Chatbot (Loto) | Stable | 12-phase detection (Phase 0 contextual continuation + regex + Text-to-SQL), 22 temporal patterns, session persistence (sessionStorage), sponsor system, GA4 tracking (5 events), multi-numéros SQL, simulator redirect fallback. Deployed on 6 Loto pages (accueil, loto, simulateur, statistiques, news, faq) |
| HYBRIDE Chatbot (EuroMillions) | Stable | Full EM adaptation of Loto chatbot: 12-phase detection, Text-to-SQL on tirages_euromillions, grille analysis (5 boules 1-50 + 2 étoiles 1-12), pitch grilles, isolated sessionStorage (`hybride-history-em`), GA4 `hybride_em_chat_*` events. Deployed on 7 EM pages. 3 dedicated EM prompts. Generic utilities shared from api_chat.py. |
| META ANALYSE 75 | Stable | Async Gemini enrichment + PDF export, circuit breaker fallback |
| Testing | Active | 70 unit tests (pytest), 43% coverage, CI integration |
| Security | Hardened | CORS, CSP (GA4/GTM whitelisted), rate limiting, sanitized correlation IDs, security headers, prod/dev deps split. Credential audit V6: .env never in git, excluded from Docker, injected by Cloud Run in prod (risk: LOW) |
| SEO | Ongoing | Structured data, sitemap, canonical redirects in place |
| Mobile responsive | Stable | Fullscreen chatbot, viewport sync, safe-area support, 4-button nav with horizontal scroll (< 599px) |
| UI Harmonization | Stable | All main pages aligned on /loto layout model (jointure, gradient bar, 4-button nav). Scroll-to-top on all pages. Version injection via `/api/version` |

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

- **Synchronous DB driver** — PyMySQL is synchronous; mitigated by `asyncio.to_thread()` on ALL async route DB calls (event loop no longer blocked). Not truly async I/O (aiomysql) but functionally non-blocking.
- **Connection pooling (DBUtils.PooledDB)** — min=5, max=10 connections. `conn.close()` returns to pool, not real close. read_timeout=30, write_timeout=30.
- **Two database tables** — Draw data split into `tirages` (Loto) and `tirages_euromillions` (EM) in same `lotofrance` database. No partitioning, no read replicas.
- **In-memory cache only** — `services/cache.py` is per-process (not shared across workers). No Redis.
- **Gemini dependency** — META ANALYSE and chatbot depend on an external API. Mitigated by circuit breaker + fallback messages, but degraded experience when open.
- **Minimal monitoring** — Production observability relies on Cloud Run metrics + JSON structured logs with correlation IDs. No APM or alerting.
- **Test coverage at 43%** — Core engine and services well covered (59-100%), but route handlers and pages have lower coverage.

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
| V5c (tests+infra) | 7.1 | +0.3 | 70 tests, CI pipeline, circuit breaker, 2 workers |
| **V6 (credentials)** | **7.2** | **+0.1** | **Credential verification confirmed, full 6-section audit** |

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
| P2 | Extract chat detection regex into a dedicated service | +0.1 |
| P3 | Deduplicate analyze-custom-grid / analyze_grille_for_chat | +0.1 |
| P3 | Migrate gcr.io to Artifact Registry | +0.05 |

---

*Updated by JyppY & Claude Opus 4.6 — 14/02/2026 (v6.0: Phase 4 — Chatbot HYBRIDE EuroMillions. api_chat_em.py 1668 lines, hybride-chatbot-em.js 277 lines, 3 EM prompts, em_schemas +3 chat schemas, em_stats_service +2 functions, widget on 7 EM pages, 17 EM endpoints total, 10 routers)*
