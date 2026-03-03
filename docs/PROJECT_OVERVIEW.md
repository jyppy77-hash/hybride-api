# LotoIA - Technical Overview

> Statistical analysis platform for the French Loto and EuroMillions, powered by the HYBRIDE engine.

---

## 1. Project Tree

```
hybride-api/
│
├── main.py                              # FastAPI orchestrator (~688L, 12 middlewares, 18 routers)
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
├── AUDIT_GA4_REPORT.md                  # GA4 analytics audit report (Phase 1+2 fixes applied)
│
├── routes/                              # API & page routers (APIRouter)
│   ├── __init__.py                      # Package init
│   ├── pages.py                         # 22 HTML page routes (SEO clean URLs, sitemap removed P5/5)
│   ├── api_data_unified.py              # Unified data endpoints /api/{game}/... (Phase 10, ~400L)
│   ├── api_analyse_unified.py           # Unified analysis endpoints /api/{game}/... (Phase 10, ~720L)
│   ├── api_chat_unified.py              # Unified chat endpoints /api/{game}/... (Phase 10, ~70L)
│   ├── api_data.py                      # Loto data — thin wrapper → api_data_unified (Phase 10)
│   ├── api_analyse.py                   # Loto analysis — thin wrapper + /ask (Phase 10)
│   ├── api_gemini.py                    # Gemini AI text enrichment endpoint
│   ├── api_pdf.py                       # PDF generation endpoint (ReportLab)
│   ├── api_tracking.py                  # Analytics tracking endpoints (grid, ads)
│   ├── api_ratings.py                   # User rating endpoints (submit, global stats)
│   ├── api_chat.py                      # HYBRIDE chatbot Loto — SSE StreamingResponse + re-exports (Phase 10, P9)
│   ├── api_chat_em.py                   # HYBRIDE chatbot EM — SSE StreamingResponse + re-exports (Phase 10, P9)
│   ├── em_data.py                       # EM data — thin wrapper → api_data_unified (Phase 10)
│   ├── em_analyse.py                    # EM analysis — thin wrapper + /meta-analyse-texte, /meta-pdf (Phase 10)
│   ├── em_pages.py                      # EuroMillions HTML page routes (11 SEO clean URLs: 7 pages + 4 legal)
│   ├── en_em_pages.py                   # EuroMillions EN page routes (11 SEO clean URLs, Phase 11)
│   ├── multilang_em_pages.py            # EuroMillions PT/ES/DE/NL page routes (44 factory routes: 11 pages x 4 langs, P5/5)
│   └── sitemap.py                       # Dynamic XML sitemap — Loto FR + EM multilang (P5/5)
│
├── services/                            # Business logic layer (21 modules, ~7600L)
│   ├── __init__.py                      # Package init
│   ├── base_stats.py                    # GameConfig-driven base class Loto/EM (770L, Phase 2)
│   ├── stats_service.py                 # Loto stats thin wrapper → base_stats (121L, Phase 2)
│   ├── em_stats_service.py              # EM stats thin wrapper → base_stats (87L, Phase 2)
│   ├── chat_pipeline.py                 # HYBRIDE chatbot orchestration — Loto (723L, Phase 1+P9 SSE+Phase A)
│   ├── chat_pipeline_em.py              # HYBRIDE chatbot orchestration — EM (771L, Phase 4+P9 SSE+Phase A)
│   ├── chat_detectors.py                # 13-phase detection: insults, argent, numbers, grids — Loto (939L, Phase 1+Phase A)
│   ├── chat_detectors_em.py             # 13-phase detection — EM variant (784L, Phase 4+Phase A)
│   ├── chat_sql.py                      # Text-to-SQL generator + executor — Loto (247L, Phase 1)
│   ├── chat_sql_em.py                   # Text-to-SQL generator — EM (176L, Phase 4)
│   ├── chat_utils.py                    # Formatting, context, sponsor — Loto (396L, Phase 1)
│   ├── chat_utils_em.py                 # Formatting, context — EM (200L, Phase 4)
│   ├── cache.py                         # Redis async cache + in-memory fallback (116L, Phase 6)
│   ├── circuit_breaker.py               # Gemini circuit breaker (84L, 3 fails → 60s open)
│   ├── gemini.py                        # Gemini 2.0 Flash API client — Loto (192L, +streaming P9)
│   ├── em_gemini.py                     # Gemini 2.0 Flash API client — EM (122L)
│   ├── pdf_generator.py                 # ReportLab PDF — Loto (576L, graph + heatmap page 2, i18n 6 langs)
│   ├── em_pdf_generator.py              # ReportLab PDF — EM (621L, dual graphs + heatmap page 2, i18n 6 langs)
│   ├── pdf_heatmap.py                   # Shared heatmap module (134L, Google 4-color gradient grid + legend)
│   ├── chat_responses_em_en.py          # English response pools for EM chatbot (277L, Phase 11+Phase A)
│   ├── penalization.py                  # Number penalization logic (65L)
│   └── prompt_loader.py                 # Dynamic prompt loader (143L, Loto PROMPT_MAP + file-based load_prompt_em with lang fallback, P4/5)
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
├── prompts/                             # Gemini contextual prompts (146 files)
│   ├── prompt_hybride.txt               # Legacy HYBRIDE prompt (root level)
│   ├── chatbot/                         # HYBRIDE chatbot prompts (Loto + legacy EM EN)
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
│   │   ├── prompt_100.txt ... prompt_800.txt   # 100-800 draw windows
│   │   └── prompt_global.txt            # Prompt for GLOBAL window (fallback)
│   ├── annees/                          # Year-based prompts — Loto
│   │   ├── prompt_1a.txt ... prompt_6a.txt     # 1-6 year windows
│   │   └── prompt_global.txt            # Prompt for GLOBAL window (annees fallback)
│   ├── euromillions/                    # Legacy EM META ANALYSE prompts (FR + EN, 30 files)
│   │   ├── tirages/                     # Window-based prompts — EM FR (100-700 + GLOBAL)
│   │   ├── annees/                      # Year-based prompts — EM FR (1A-6A + GLOBAL)
│   │   └── en/                          # EM EN prompts (tirages + annees, Phase 11)
│   └── em/                              # Multilingual EM prompts (P4/5, 108 files)
│       ├── fr/                          # FR: 3 chatbot + 8 tirages + 7 annees = 18 files
│       ├── en/                          # EN: 3 chatbot + 8 tirages + 7 annees = 18 files
│       ├── pt/                          # PT: same structure (18 files, fully translated, Sprint PT)
│       ├── es/                          # ES: same structure (18 files, fully translated, Sprint ES)
│       ├── de/                          # DE: same structure (18 files, fully translated, Sprint DE)
│       └── nl/                          # NL: same structure (18 files, fully translated, Sprint NL)
│
├── translations/                          # Babel/gettext i18n catalogs (P1/5)
│   ├── messages.pot                     # Extracted message template (Babel)
│   ├── fr/LC_MESSAGES/messages.po/.mo   # French catalog (reference)
│   ├── en/LC_MESSAGES/messages.po/.mo   # English (GB) catalog
│   ├── pt/LC_MESSAGES/messages.po/.mo   # Portuguese catalog (complete, 384 entries, Sprint PT)
│   ├── es/LC_MESSAGES/messages.po/.mo   # Spanish catalog (complete, 384 entries, Sprint ES)
│   ├── de/LC_MESSAGES/messages.po/.mo   # German catalog (complete, 384 entries, Sprint DE)
│   └── nl/LC_MESSAGES/messages.po/.mo   # Dutch catalog (complete, 384 entries, Sprint NL)
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
│   ├── sitemap.xml                      # Legacy static XML sitemap (replaced by dynamic routes/sitemap.py, P5/5)
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
│   ├── templates/em/                    # Jinja2 templates — EuroMillions (P2/5, replaces static HTML serving)
│   │   ├── _base.html                  # Base layout (head, nav, footer, hreflang, OG, chatbot, rating, mobile globe selector)
│   │   ├── _footer.html                # Footer partial (nav links, dynamic legal URLs per lang, gambling help)
│   │   ├── _hero.html                  # Hero partial (icon, title, subtitle, action buttons)
│   │   ├── accueil.html                # EM home page template
│   │   ├── generateur.html             # EM generator template (META slider, sponsor popups, app.js)
│   │   ├── simulateur.html             # EM simulator template (grid selector, sponsor popup)
│   │   ├── statistiques.html           # EM statistics template (frequencies, heatmap, charts)
│   │   ├── historique.html             # EM history template (date picker, draw display)
│   │   ├── faq.html                    # EM FAQ template (accordion, dynamic DB total)
│   │   ├── news.html                   # EM news template (timeline, releases)
│   │   ├── mentions-legales.html       # EM legal notices (6 langs: publisher, hosting, IP, liability, data, cookies, links, law, contact)
│   │   ├── confidentialite.html        # EM privacy policy (6 langs: 12 GDPR/RGPD sections, per-lang supervisory authorities)
│   │   ├── cookies.html                # EM cookie policy (6 langs: 8 sections, JS settings buttons)
│   │   └── disclaimer.html             # EM disclaimer (6 langs: gambling warning, AI warning, liability limitation)
│   │
│   ├── en/                              # English (GB) pages (Phase 11)
│   │   └── euromillions/                # EuroMillions EN pages (7 pages, rendered by Jinja2 P2/5)
│   │       ├── home.html ... news.html  # 7 EN HTML pages (legacy, now served via templates)
│   │       └── static/                  # EN-specific JS (chatbot only, other JS via P3/5 i18n)
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
│       ├── hybride-chatbot-em-en.js    # HYBRIDE Chatbot widget — EM English (Phase 11, now in ui/en/euromillions/static/)
│       ├── theme.js                     # Dark/light mode toggle
│       ├── analytics.js                 # GA4 analytics v2.5.2 (Consent Mode v2, owner IP filter, 32+ events)
│       ├── cookie-consent.js            # Cookie consent banner v2.0.0 (CNIL, i18n 6 langs)
│       ├── faq.js                       # FAQ accordion logic (Loto)
│       ├── faq-em.js                    # FAQ accordion logic (EuroMillions)
│       ├── scroll.js                    # Scroll-to-top button (all pages)
│       ├── nav-scroll.js                # Navigation scroll behavior
│       ├── version-inject.js            # Dynamic version injection from /api/version
│       ├── sponsor-popup.js             # Sponsor popup logic (grids)
│       ├── rating-popup.js              # Rating popup UI logic (GA4 + Umami dual tracking)
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
├── tests/                               # Unit tests (pytest) — 972 tests
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
│   ├── test_en_routes.py              # EN EuroMillions route tests (18 tests, Phase 11)
│   ├── test_i18n.py                   # i18n gettext tests (30 tests, P1/5)
│   ├── test_templates.py             # Jinja2 templates + render_template + legal pages tests (83 tests, P2/5 + legal)
│   ├── test_js_i18n.py              # JS i18n labels tests (21 tests, P3/5 + chatbot welcome)
│   ├── test_prompts.py              # Prompt system tests (59 tests, P4/5 + Sprint ES)
│   ├── test_multilang_routes.py     # Multilang routes + SEO tests (66 tests, P5/5 + legal routes)
│   └── test_argent.py               # Argent/money detection + response tests (84 tests, Phase A)
│
├── config/                                # Runtime configuration
│   ├── __init__.py                      # Package init
│   ├── games.py                         # GameConfig registry — unified game definitions (Phase 10)
│   ├── languages.py                     # Language registry — ValidLang enum, PAGE_SLUGS (6 langs), PROMPT_KEYS (Phase 11+P5/5)
│   ├── i18n.py                          # i18n module — gettext + Babel, 6 languages, badges + analysis strings (P1/5)
│   ├── js_i18n.py                       # JS i18n labels — window.LotoIA_i18n, 6 langs (FR/EN/ES/PT/DE/NL), 160+ keys per lang (P3/5 + Sprints)
│   ├── templates.py                     # Jinja2 template engine — EM_URLS (6 langs), hreflang (killswitch-filtered), lang switch (P2-P5/5)
│   ├── killswitch.py                    # Multilingual kill switch — ENABLED_LANGS = ["fr", "en", "es", "pt", "de", "nl"] (P5/5, all 6 ON)
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

The frontend is built with vanilla JavaScript (ES5+), HTML5, and CSS3. There is no JS framework (React, Vue, Angular) and no build step (no Webpack, Vite, or Babel).

**Templating (P2/5):** EuroMillions pages use **Jinja2** server-side templates with i18n extension (`_()` / `ngettext()`). A single set of 14 templates (`ui/templates/em/`: 7 main + 4 legal + 3 partials) renders all 6 languages via `render_template(lang="fr"|"en"|"pt"|...)`. Loto pages remain static HTML.

**JS i18n (P3/5):** All JS-rendered strings (160+ keys per language, 6 languages) are centralized in `config/js_i18n.py` and injected as `window.LotoIA_i18n` via Jinja2. Frontend JS reads labels at runtime — no per-language JS files needed.

**Multilang routing (P5/5):** PT/ES/DE/NL routes are factory-generated (`routes/multilang_em_pages.py`) with a **kill switch** (`config/killswitch.py`). Disabled languages return 302 redirects to the FR equivalent. `hreflang_tags()` and the dynamic sitemap only include enabled languages.

**Rationale:**

- **Performance** — No framework runtime overhead. Pages load with zero JS bundle parsing cost beyond the application scripts themselves.
- **Control** — Direct DOM manipulation without abstraction layers. Every interaction is explicit and traceable.
- **Minimal dependencies** — The chatbot widget (`hybride-chatbot.js`) is a self-contained IIFE with zero external imports. The same applies to all other JS modules.
- **Deployment simplicity** — Static files served directly by FastAPI. No node_modules, no build pipeline, no transpilation.
- **i18n (P1-P5/5)** — Babel/gettext `.po` catalogs for 6 languages. Thread-safe `ContextVar` ensures async-safe translations. JS labels via `window.LotoIA_i18n` (P3/5). File-based prompts with lang fallback chain (P4/5). Kill switch + dynamic sitemap (P5/5).

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
| **SSE Streaming (P9)** | Real-time word-by-word rendering via `fetch()` + `getReader()` + `TextDecoder`. SSE events: `data: {"chunk", "source", "mode", "is_done"}`. Anti-buffering headers: `Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`, `Content-Encoding: identity` (bypasses GZipMiddleware). 30s timeout. |
| **Responses** | Gemini 2.0 Flash via `/api/hybride-chat` SSE stream (multi-turn, system_instruction, circuit breaker, fallback) |
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
| **SSE Streaming (P9)** | Same real-time streaming as Loto widget (SSE events, `getReader()`, anti-buffering headers) |
| **Endpoint** | `/api/euromillions/hybride-chat` (POST, SSE stream) |
| **Storage** | `hybride-history-em` + lang suffix (sessionStorage, per-language isolation: `hybride-history-em-es`, `-pt`, `-de`, `-nl`; FR uses base key) |
| **Header** | `HYBRIDE — EuroMillions` |
| **Welcome** | `...assistant IA de LotoIA — module EuroMillions...` |
| **detectPage()** | accueil-em, euromillions, simulateur-em, statistiques-em, historique-em, faq-em, news-em |
| **Typing ID** | `hybride-typing-indicator-em` (no conflict with Loto widget) |
| **GA4 events** | Prefixed `hybride_em_chat_*` (open, message, session, sponsor_view, clear, error) |
| **Backend** | `api_chat_em.py` (thin wrapper) → `services/chat_pipeline_em.py`: 13-phase detection pipeline adapted for EuroMillions (boules 1-50, 2 étoiles 1-12, table tirages_euromillions, draw days mardi/vendredi) |
| **Prompts** | 3 dedicated EM prompts: `prompt_hybride_em.txt`, `prompt_sql_generator_em.txt`, `prompt_pitch_grille_em.txt` |
| **Pitch** | `POST /api/euromillions/pitch-grilles` (1-5 grids, JSON pitchs with étoiles support) |
| **Imports** | Generic utilities imported from `api_chat.py` (continuation, sponsor, insult/compliment detection, SQL validation, clean_response, format_date_fr, temporal filter). EM-specific functions and response pools defined locally. |
| **i18n (Phase 11)** | EN support via `lang` parameter: EN response pools (`chat_responses_em_en.py`), EN chatbot prompts (`prompt_hybride_em_en.txt`), EN sponsor text (`_get_sponsor_if_due(history, lang="en")`). Frontend widget: `hybride-chatbot-em-en.js` with EN sponsor detection. |

### HYBRIDE BDD Integration (Chatbot ↔ Live Database)

The chatbot is connected to Cloud SQL in real-time via a multi-phase detection pipeline:

| Phase | Detection | Data Source | Example Query |
|-------|-----------|-------------|---------------|
| **Phase A — Money/Gambling** | Regex `_detect_argent()` / `_detect_argent_em()` | Court-circuit (no Gemini) — L1/L2/L3 response pools | "combien vaut le jackpot", "I want to get rich", "quiero apostar" |
| **Phase 0 — Continuation** | Regex `_is_short_continuation()` | `_enrich_with_context()` (history) | "oui", "non", "vas-y", "détaille", "continue" |
| **Phase 0-bis — Next Draw** | Regex `_detect_prochain_tirage()` | `_get_prochain_tirage()` | "c'est quand le prochain tirage ?" |
| **Phase T — Draw Results** | Regex `_detect_tirage()` | `_get_tirage_data()` | "dernier tirage", "les numéros d'hier" |
| **Phase 2 — Grid Analysis** | Regex `_detect_grille()` (5 nums) | `analyze_grille_for_chat()` | "analyse 8 24 25 32 46 + 3" |
| **Phase 3 — Complex Queries** | Regex `_detect_requete_complexe()` | `get_classement_numeros()`, `get_comparaison_numeros()`, `get_numeros_par_categorie()` | "top 10 les plus fréquents", "compare le 7 et le 23" |
| **Phase 1 — Single Number** | Regex `_detect_numero()` | `get_numero_stats()` | "le 9 est sorti combien de fois ?" |
| **Phase SQL — Text-to-SQL** | Gemini SQL generation | `_generate_sql()` → `_execute_safe_sql()` | "combien de fois le 22 en 2025 ?", "quel numéro a le plus grand écart ?" |

**Detection priority**: Insult → Compliment → **Argent** → Continuation → Next Draw → Draw Results → [Temporal filter check] → Grid → Complex → Single Number → Text-to-SQL

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

- **Dual analytics**: GA4 (`G-YYJ5LD1ZT3`) + Umami (self-hosted, cookieless)
- GA4 Consent Mode v2: baseline cookieless → enhanced after consent
- Cookie consent banner i18n: 6 languages (FR/EN/ES/PT/DE/NL), auto-detect via `window.LotoIA_lang`
- Owner IP filtering: `window.__OWNER__` blocks both GA4 and Umami for admin visits
- 32+ GA4 events: UX (scroll, page_view, session), Product (generate_grid, simulate_grid), Business (sponsor_impression, sponsor_click, sponsor_video_played), Chatbot (8 events), Meta (meta75_launched, meta_pdf_export)
- 13 Umami events: full parity with GA4 for key actions
- CSP: img-src + connect-src whitelist GA4/GTM + Umami domains
- Graceful adblock degradation: `gtagLoadFailed` flag, no JS errors

---

## 4. Architecture Flow

```
USER BROWSER (HTML/CSS/Vanilla JS)
         |
         v
+--------------------------------------------------+
|              MIDDLEWARE STACK                      |
|  1. GZipMiddleware (>500 bytes, bypassed for SSE via Content-Encoding: identity) |
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
|  routes/pages.py         22 HTML/SEO pages        |
|  routes/em_pages.py      EM HTML page routes (FR) |
|  routes/en_em_pages.py   EM HTML page routes (EN) |
|  routes/multilang_em_pages.py  EM PT/ES/DE/NL (44)|
|  routes/sitemap.py       Dynamic XML sitemap      |
|  routes/api_gemini.py    Gemini AI enrichment     |
|  routes/api_pdf.py       PDF generation           |
|  routes/api_tracking.py  Analytics tracking       |
|  routes/api_ratings.py   User rating system       |
|  main.py                 health, SEO 301          |
+--------------------------------------------------+
         |
         v
+--------------------------------------------------+
|              SERVICES LAYER (21 modules, ~7600L)  |
|                                                   |
|  ── Chat Pipeline (Phase 1+4+A) ────────────     |
|  chat_pipeline.py       Loto 13-phase orchestration|
|  chat_pipeline_em.py    EM 13-phase orchestration  |
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
|  pdf_generator.py       ReportLab PDF — Loto (i18n) |
|  em_pdf_generator.py    ReportLab PDF — EM (i18n)  |
|  pdf_heatmap.py         Shared heatmap grid+legend  |
|  penalization.py        Post-draw frequency filter  |
|  prompt_loader.py       Loto PROMPT_MAP + EM multilang|
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
main.py (~688 lines) — Orchestrator
    ├── app = FastAPI() + lifespan (httpx.AsyncClient + aiomysql pool + Redis cache)
    ├── Middlewares (CORS, correlation ID, security headers, canonical, cache, SEO, Umami filter, HEAD, HTTPS)
    ├── Rate limiting (slowapi, 10/min on chat endpoints)
    ├── Static mounts (/ui, /static)
    ├── _SEO_ROUTES frozenset (auto-built from EM_URLS, all langs, P5/5)
    ├── app.include_router() x18 (8 legacy Loto + 4 legacy EM + 3 unified P10 + 1 EN P11 + 1 multilang P5/5 + 1 sitemap P5/5)
    ├── /health (native async + asyncio.wait_for 5s timeout)
    └── SEO 301 redirects

schemas.py — Pydantic Models (Loto)
    ├── AskPayload
    ├── GridData, TrackGridPayload
    ├── TrackAdImpressionPayload, TrackAdClickPayload
    ├── MetaAnalyseTextePayload
    ├── MetaPdfPayload (lang, all_freq_boules, all_freq_secondary)
    ├── ChatMessage, HybrideChatRequest
    ├── HybrideChatResponse
    ├── PitchGrilleItem
    └── PitchGrillesRequest

em_schemas.py — Pydantic Models (EuroMillions)
    ├── EMGridData (nums + etoiles + score)
    ├── EMMetaAnalyseTextePayload
    ├── EMMetaPdfPayload (graph_data_boules + graph_data_etoiles + all_freq_boules + all_freq_secondary)
    ├── EMPitchGrilleItem
    ├── EMPitchGrillesRequest
    ├── EMChatMessage (role + content)
    ├── EMChatRequest (message + page + history)
    └── EMChatResponse (response + source + mode)

rate_limit.py — Shared slowapi limiter instance

routes/ — 18 routers (3 unified + 8 legacy Loto + 4 legacy EM + 1 EN Phase 11 + 1 multilang P5/5 + 1 sitemap P5/5)
    ── Unified Routes (Phase 10) ──
    ├── api_data_unified.py    (~400L)  /api/{game}/tirages/*, stats/*, numbers-heat, draw/*, etc.
    ├── api_analyse_unified.py (~720L)  /api/{game}/generate, meta-analyse-local, analyze-custom-grid
    ├── api_chat_unified.py     (~70L)  /api/{game}/hybride-chat, pitch-grilles
    ── Legacy Thin Wrappers (backward compat, Phase 10) ──
    ├── api_data.py       (~135L)  Loto thin wrapper → unified + /database-info, /stats legacy
    ├── em_data.py        (~100L)  EM thin wrapper → unified (prefix /api/euromillions)
    ├── api_analyse.py     (~60L)  Loto thin wrapper → unified + /ask (Loto-only)
    ├── em_analyse.py     (~100L)  EM thin wrapper → unified + /meta-analyse-texte, /meta-pdf (EM-only)
    ├── api_chat.py        (~92L)  Loto chatbot SSE StreamingResponse + re-exports (P9)
    ├── api_chat_em.py     (~85L)  EM chatbot SSE StreamingResponse + re-exports (P9)
    ── Shared Routes ──
    ├── pages.py          (230 lines)  22 HTML page routes (sitemap removed P5/5)
    ├── em_pages.py       (~150L)      EuroMillions HTML page routes (11 SEO clean URLs: 7 pages + 4 legal, FR)
    ├── en_em_pages.py    (~150L)      EuroMillions EN page routes (11 SEO clean URLs, Phase 11)
    ├── multilang_em_pages.py (~190L)  EuroMillions PT/ES/DE/NL factory routes (44 routes: 11 pages x 4 langs, P5/5)
    ├── sitemap.py         (86 lines)  Dynamic XML sitemap — Loto FR + EM multilang (P5/5)
    ├── api_gemini.py      (19 lines)  meta-analyse-texte
    ├── api_pdf.py         (37 lines)  meta-pdf
    ├── api_tracking.py   (127 lines)  track-grid, track-ad-*
    └── api_ratings.py    (106 lines)  user rating submission + global stats

services/ — 21 modules, ~7600 lines
    ── Chat Pipeline (Phase 1 Loto, Phase 4 EM, Phase A) ──
    ├── chat_pipeline.py     (723L)  13-phase orchestration + SSE streaming — Loto (P9+Phase A)
    ├── chat_pipeline_em.py  (771L)  13-phase orchestration + SSE streaming — EM (P9+Phase A)
    ├── chat_detectors.py    (939L)  Regex detectors, insult/OOR/argent pools, streak — Loto
    ├── chat_detectors_em.py (784L)  EM-specific detectors + response pools (6 langs)
    ├── chat_sql.py          (247L)  Text-to-SQL generator + executor — Loto
    ├── chat_sql_em.py       (176L)  Text-to-SQL — EuroMillions
    ├── chat_utils.py        (396L)  Context building, formatting, sponsor — Loto
    ├── chat_utils_em.py     (200L)  Context building, formatting — EuroMillions
    ├── chat_responses_em_en.py (277L)  EN response pools for EM chatbot (Phase 11+Phase A)
    ── Stats Layer (Phase 2: base class refactoring) ──
    ├── base_stats.py        (770L)  GameConfig-driven base class (8 methods, 4 SQL hooks)
    ├── stats_service.py     (121L)  Loto thin wrapper → base_stats
    ├── em_stats_service.py   (87L)  EM thin wrapper → base_stats (em: cache prefix)
    ── AI, Cache, PDF ──
    ├── cache.py             (116L)  Redis async + in-memory fallback (Phase 6)
    ├── circuit_breaker.py    (84L)  Gemini circuit breaker (CLOSED/OPEN/HALF_OPEN)
    ├── gemini.py            (192L)  Gemini API client — Loto (batch + streaming, circuit breaker, P9)
    ├── em_gemini.py         (122L)  Gemini API client — EuroMillions
    ├── pdf_generator.py     (576L)  ReportLab PDF engine — Loto (graph + heatmap page 2, PDF_LABELS 6 langs)
    ├── em_pdf_generator.py  (621L)  ReportLab PDF engine — EM (dual graphs + heatmap page 2, PDF_LABELS 6 langs)
    ├── pdf_heatmap.py       (134L)  Shared heatmap module (Google 4-color gradient grid + legend bar)
    ├── penalization.py       (65L)  Post-draw frequency penalization filter
    └── prompt_loader.py     (143L)  Loto PROMPT_MAP (18 keys) + EM file-based multilang loader (P4/5)

tests/ — 972 tests, 25 files (pytest + pytest-cov)
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
    ── Argent/Money Detection Tests (Phase A) ──
    ├── test_argent.py            (373L)   84 tests: FR/EN/ES/PT/DE/NL detection, L1/L2/L3 levels, response language, non-regression
    ── i18n / Multilang Tests (P1-P5/5) ──
    ├── test_i18n.py             (30 tests)  gettext, Babel catalogs, plurals, badges
    ├── test_templates.py        (83 tests)  Jinja2 env, EM_URLS, render_template FR/EN, legal pages 6 langs, footer links
    ├── test_js_i18n.py          (21 tests)  JS i18n labels FR/EN, key coverage, chatbot welcome per lang
    ├── test_prompts.py          (58 tests)  Loto+EM prompts, lang fallback, variable substitution
    ├── test_multilang_routes.py (66 tests)  Kill switch, hreflang, sitemap, routes (44), PAGE_SLUGS, legal URLs
    ── PDF Heatmap Tests ──
    ├── test_pdf_heatmap.py     (37 tests)  Google gradient, text color, grid rendering, legend, full PDF 2-page count, PDF_LABELS, schemas
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

Loto pages are static HTML served by FastAPI. EuroMillions pages use **Jinja2 templates** (P2/5) with i18n extension for multilingual rendering (6 languages). JS labels are centralized in `config/js_i18n.py` and injected as `window.LotoIA_i18n` (P3/5) — no per-language JS files needed.

| Module | Purpose |
|--------|---------|
| `app.js` | Grid generation, DB status, result rendering, engine controls (Loto) |
| `app-em.js` | EuroMillions application logic (grid generation, results, EM-specific UI) |
| `simulateur.js` | Interactive 49-number grid, real-time API scoring (Loto) |
| `simulateur-em.js` | Interactive EM grid, real-time API scoring (EuroMillions) |
| `sponsor-popup75.js` | META ANALYSE 75 Loto: Gemini chain, PDF export, sponsor timer |
| `sponsor-popup75-em.js` | META ANALYSE 75 EM: dual graphs (boules+etoiles), Gemini chain, PDF export, sponsor timer |
| `theme.js` | Dark/light mode toggle with `localStorage` persistence |
| `analytics.js` | GA4 analytics v2.5.2: Consent Mode v2, owner IP filter (`window.__OWNER__`), 32+ events (UX/Product/Business/Chatbot), ProductEngine with RGPD sanitizer + buffer, graceful adblock degradation |
| `cookie-consent.js` | Cookie consent banner v2.0.0: CNIL-compliant, i18n 6 languages (CONSENT_LABELS dict), auto-detect lang, contextual cookie policy URL |
| `faq.js` | FAQ accordion interactions (Loto) |
| `faq-em.js` | FAQ accordion interactions (EuroMillions) |
| `scroll.js` | Scroll-to-top button (shows after 300px scroll, all pages including legal) |
| `nav-scroll.js` | Navigation scroll behavior |
| `rating-popup.js` | Rating popup UI logic: GA4 + Umami dual tracking (rating_popup_shown, rating_dismissed, rating-submitted) |
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
| Jinja2 | ≥3.1 | Server-side templates for EM pages (i18n extension, P2/5) |
| Babel | ≥2.16 | i18n catalog extraction + compilation (.po/.mo, P1/5) |
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
| HTML5 | Semantic markup |
| Jinja2 | Server-side templates for EM pages (P2/5), i18n extension, thread-safe ContextVar, JS i18n injection (P3/5) |
| Babel / gettext | i18n catalogs for 6 languages (P1/5). JS labels via `window.LotoIA_i18n` (P3/5) |
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

### Page Routes (22) — routes/pages.py

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
| `GET /favicon.ico` | favicon.ico |
| `GET /BingSiteAuth.xml` | BingSiteAuth.xml |

### EN EuroMillions Page Routes (11) — routes/en_em_pages.py (P2/5 — Jinja2)

| Route | Jinja2 Template | lang |
|-------|-----------------|------|
| `GET /en/euromillions` | em/accueil.html | en |
| `GET /en/euromillions/generator` | em/generateur.html | en |
| `GET /en/euromillions/simulator` | em/simulateur.html | en |
| `GET /en/euromillions/statistics` | em/statistiques.html | en |
| `GET /en/euromillions/history` | em/historique.html | en |
| `GET /en/euromillions/faq` | em/faq.html | en |
| `GET /en/euromillions/news` | em/news.html | en |
| `GET /en/euromillions/legal-notices` | em/mentions-legales.html | en |
| `GET /en/euromillions/privacy` | em/confidentialite.html | en |
| `GET /en/euromillions/cookies` | em/cookies.html | en |
| `GET /en/euromillions/disclaimer` | em/disclaimer.html | en |

All EN pages use the **same Jinja2 templates** as FR with `lang="en"`. `render_template()` injects: EN URLs, `date_locale="en-GB"`, EN chatbot JS, EN sponsor popup JS, `hreflang` tags (`fr`/`en`/`x-default`), lang-switch button, OG locale `en_GB`, BeGambleAware help link.

### Multilang EuroMillions Page Routes (44) — routes/multilang_em_pages.py (P5/5)

Factory-generated routes for PT/ES/DE/NL (11 pages x 4 languages = 44 routes). All use the same Jinja2 templates as FR/EN.

| Route Pattern | Pages | Notes |
|---------------|-------|-------|
| `GET /pt/euromillions/*` | 11 | Portuguese (gerador, simulador, estatisticas, historico, noticias, faq + avisos-legais, privacidade, cookies, aviso) |
| `GET /es/euromillions/*` | 11 | Spanish (generador, simulador, estadisticas, historial, noticias, faq + aviso-legal, privacidad, cookies, aviso) |
| `GET /de/euromillions/*` | 11 | German (generator, simulator, statistiken, ziehungen, nachrichten, faq + impressum, datenschutz, cookies, haftungsausschluss) |
| `GET /nl/euromillions/*` | 11 | Dutch (generator, simulator, statistieken, geschiedenis, nieuws, faq + juridische-kennisgeving, privacy, cookies, disclaimer) |

**Kill switch**: If `lang` not in `killswitch.ENABLED_LANGS` → 302 redirect to FR equivalent. Routes are always registered (SEO crawl-safe), check is at request time. All 6 languages activated (ES/PT/DE/NL sprints 2026-02-28).

### Dynamic Sitemap — routes/sitemap.py (P5/5)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /sitemap.xml` | GET | Dynamic XML sitemap — Loto FR + EM pages for all ENABLED_LANGS |

Includes `<priority>`, `<lastmod>`, `<changefreq>` per URL. Only enabled languages appear in the sitemap.

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

### services/gemini.py — Gemini AI Client (Loto, 192L)

- **API**: Google Gemini 2.0 Flash (`generativelanguage.googleapis.com/v1beta`)
- **Transport**: httpx.AsyncClient (shared via app lifespan, circuit breaker wrapped)
- **Auth**: API key via `GEM_API_KEY` or `GEMINI_API_KEY` env var
- **Prompt**: Loaded dynamically from `prompts/tirages/` or `prompts/annees/` via `load_prompt()`
- **Batch mode**: `enrich_analysis()` for META ANALYSE — single request/response via `GEMINI_MODEL_URL`
- **Streaming mode (P9)**: `stream_gemini_chat()` async generator via `GEMINI_STREAM_URL` (`streamGenerateContent?alt=sse`). Uses `httpx.AsyncClient.stream("POST", ...)` with manual circuit breaker management (`_record_success`/`_record_failure`). Yields text chunks progressively.
- **Fallback chain**: Gemini enriched → Local text (if API fails/timeout) → Circuit open fallback
- **Output**: Batch: `{"analysis_enriched": "...", "source": "..."}`. Stream: yields `str` chunks.
- **Shared by**: META ANALYSE (api_gemini.py) via `GEMINI_MODEL_URL` + HYBRIDE chatbot (chat_pipeline.py) via `stream_gemini_chat()`

### services/em_gemini.py — Gemini AI Client (EuroMillions)

- **API**: Same Gemini 2.0 Flash endpoint
- **Prompt**: Loaded dynamically from `prompts/euromillions/` via `load_prompt_em()` (auto `EM_` prefix)
- **Function**: `enrich_analysis_em(analysis_local, window, *, http_client)` — mirrors `enrich_analysis()` for EM
- **Fallback chain**: Same as Loto (Gemini enriched → Local text → Circuit open fallback)
- **Logging**: `[META TEXTE EM]` prefix for all log entries
- **Zero coupling**: Does not import from `gemini.py` (independent module)

### Chat Pipeline — 8 Modules (Phase 1 Loto, Phase 4 EM, Phase A Argent)

Phase 1 split `api_chat.py` (2014L) into 4 service modules. Phase 4 applied the same pattern to `api_chat_em.py` (1668L). Phase A added money/gambling detection (court-circuit, no Gemini).

**services/chat_pipeline.py** (723L) / **chat_pipeline_em.py** (771L):
- **13-phase orchestration**: Insult → Compliment → **Argent** → Continuation → Next Draw → Draw Results → Grid → Complex → Single Number → Text-to-SQL → Gemini
- **Refactored (P9)**: `_prepare_chat_context()` extracts all 13 detection phases → returns `(early_return, ctx_dict)`. Shared by batch and streaming modes.
- **Batch mode**: `handle_chat(message, history, page, httpx_client)` → `dict(response, source, mode)` (preserved for backward compat)
- **SSE Streaming (P9)**: `handle_chat_stream()` async generator yields SSE events (`data: {"chunk", "source", "mode", "is_done"}\n\n`). Early returns (insult, compliment, OOR) yield single event. Gemini responses stream progressively. Sponsor injected as final chunk before done event. Fallback on exception.
- **Pitch**: `handle_pitch(grilles, httpx_client)` → `dict(pitchs: list[str])`

**services/chat_detectors.py** (939L) / **chat_detectors_em.py** (784L):
- **Regex patterns**: `_detect_insulte()`, `_detect_argent()` / `_detect_argent_em()`, `_detect_numero()`, `_detect_grille()`, `_detect_requete_complexe()`, `_detect_prochain_tirage()`, `_detect_mode()`
- **Response pools**: Insult L1-L4, OOR L1-L3, Compliment L1-L3, Argent L1-L3 (6 langs), Menace responses
- **Argent detection (Phase A)**: 3-level escalation — L1 pedagogical (default), L2 firm (strong money words like "devenir riche"/"get rich"), L3 help redirection (betting/gambling words → country-specific support links). FR/EN/ES/PT/DE/NL each have dedicated response pools and word lists.
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

- **Format**: A4 portrait, 2-page layout (page 1: analysis, page 2: heatmap)
- **i18n**: `PDF_LABELS` dict with 22 keys x 6 languages (FR/EN/ES/PT/DE/NL)
- **Font system**: DejaVuSans (Linux/Cloud Run) -> Vera (ReportLab fallback)
  - 3 variants: Regular, Bold, Oblique
  - Multi-path resolution: reportlab/fonts/ -> /usr/share/fonts/ -> Vera fallback
- **Page 1**: Title, analysis block, single graph image, chance data, info block, sponsor with mailto link
- **Page 2**: Heatmap grid numbers 1-49 (7x7) + chance 1-10 (5x2) + Google gradient legend + footer
- **Heatmap**: Google Material Design 4-color gradient (Blue #4285F4 -> Green #34A853 -> Yellow #FBBC05 -> Red #EA4335)
- **Retro-compatible**: Without `all_freq_boules` data, produces 1-page PDF with footer on page 1
- **Output**: `io.BytesIO` containing the PDF

### services/em_pdf_generator.py — ReportLab PDF Engine (EuroMillions)

- **Format**: A4 portrait, 2-page layout (page 1: analysis, page 2: heatmap)
- **i18n**: `PDF_LABELS` dict with 26 keys x 6 languages (FR/EN/ES/PT/DE/NL)
- **Dual graphs**: `generate_em_graph_image()` produces a 2x2 matplotlib figure:
  - Row 1: Top 5 Boules (bar chart + pie chart, blue/green palette)
  - Row 2: Top 3 Etoiles (bar chart + pie chart, orange/teal palette)
- **Page 2**: Heatmap grid boules 1-50 (10x5) + etoiles 1-12 (6x2) + Google gradient legend + footer
- **Retro-compatible**: Without `all_freq_boules` data, produces 1-page PDF with footer on page 1
- **Output**: `io.BytesIO` containing the PDF

### services/pdf_heatmap.py — Shared Heatmap Module

- **Gradient**: `_freq_to_color()` — Google Material 4-color gradient (Blue -> Green -> Yellow -> Red)
- **Text contrast**: `_text_color_for_bg()` — white text on dark backgrounds (blue/green/red), black on bright (yellow)
- **Grid**: `draw_heatmap_grid()` — draws numbered cells with frequency, color-coded by value
- **Legend**: `draw_legend_bar()` — horizontal gradient bar with "cold/rare" and "hot/frequent" labels
- **Used by**: Both `pdf_generator.py` (Loto) and `em_pdf_generator.py` (EM)

### services/penalization.py — Number Penalization

- **Purpose**: Frequency-based weight adjustment for number generation
- **Used by**: Engine layer for grid optimization

### services/prompt_loader.py — Dynamic Prompt System (P4/5 Refactored)

- **Loto**: 18 keys via `PROMPT_MAP` dict (100-800, GLOBAL, 1A-6A, CHATBOT, PITCH_GRILLE, SQL_GENERATOR)
- **EM**: File-based multilingual loader `load_prompt_em(name, lang)` with **fallback chain** `[lang → en → fr]`
- **Prompt directory**: `prompts/em/{lang}/` — 108 files (18 per language x 6 languages: fr, en, pt, es, de, nl)
- **Functions**: `load_prompt(window)` (Loto), `load_prompt_em(name, lang)` (EM, `@lru_cache`), `get_em_prompt(name, lang, **kwargs)` (safe variable substitution), `em_window_to_prompt(window)` (window key → file path)
- **Fallback**: `prompt_global.txt` for Loto. EM: lang → en → fr chain (always finds FR as ultimate fallback)
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
| `OWNER_IP` | Optional | — | Owner IPv4 address(es) for GA4 + Umami analytics filtering (pipe-separated) |
| `OWNER_IPV6` | Optional | — | Owner IPv6 prefix for GA4 + Umami analytics filtering |

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
| Compression | GZipMiddleware (>500 bytes, bypassed for SSE via `Content-Encoding: identity`) |
| Scraper Blocking | robots.txt (AhrefsBot, SemrushBot, GPTBot, CCBot) |
| GDPR Compliance | Cookie consent system, no tracking without approval |
| URL Deduplication | 301 redirect `/ui/*.html` → clean routes |
| Canonical URLs | 301 redirect `www` → root domain |
| HTTPS | Enforced via Cloud Run + `og:image:secure_url` + redirect_http_to_https middleware |
| API Key Protection | Gemini key stored in env vars, never exposed to client |
| Owner IP Filtering | UmamiOwnerFilterMiddleware injects `window.__OWNER__=true` for owner IPs → blocks both Umami (via `umamiBeforeSend`) and GA4 (via `bootGtagImmediately` early return) |
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
| `services/chat_detectors.py` | 939 | Regex detection, insult/OOR/compliment/argent pools, streak tracking |
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
| `services/chat_detectors_em.py` | 784 | EM-specific regex + response pools (6 langs, Phase A argent) |
| `services/chat_pipeline_em.py` | 771 | EM 13-phase orchestration (Phase A argent) |
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
| `services/chat_responses_em_en.py` | 277 | English response pools for EM chatbot (+ Phase A argent EN) |
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

### Phase 11 — Post-Release Fix: FR Residuals in EN API (2026-02-27)

Fixed 30 hardcoded French suggestion/comparison strings visible on `/en/euromillions/simulator` analysis results.

| Change | Detail |
|--------|--------|
| `config/i18n.py` | Added `_analysis_strings(lang)` function — 34 FR/EN string pairs (severity 0-3, comparison, direction words) |
| `routes/api_analyse_unified.py` | Refactored 30 f-strings → `s = _analysis_strings(lang); s[key].format(...)` |
| `translations/en/.../messages.po` | Added 4 active entries (`Numéros chauds`, `Équilibre`, plural `tirages`, `{count} tirages analysés`) |

**Result**: 473 → 540 tests (including P1-P2/5 tests added in same session), 0 failures.

### P1/5 — gettext + Babel i18n Infrastructure (2026-02-27)

Babel/gettext catalog system for multilingual EuroMillions pages.

| Change | Detail |
|--------|--------|
| `config/i18n.py` (221L) | Central i18n module: `gettext_func(lang)`, `ngettext_func(lang)`, `_global()` via ContextVar, `get_translator(request)`, `_badges(lang)`, `_analysis_strings(lang)` |
| `translations/messages.pot` | Extracted 250+ msgids from Jinja2 templates via Babel |
| `translations/{fr,en,pt,es,de,nl}/` | 6-language `.po` catalogs with compiled `.mo` files. All 6 complete (384 entries each). FR=reference. |
| `tests/test_i18n.py` (30 tests) | gettext loading, FR/EN translations, plurals, named placeholders, fallback, badge translations |

**Result**: Production-ready gettext infrastructure. 6 supported languages. All 6 now complete (FR+EN initially, ES/PT/DE/NL via subsequent sprints).

### P2/5 — Jinja2 Templates + Sponsor Popup Fix (2026-02-27)

Server-side Jinja2 templates replace static HTML serving for all EuroMillions pages (FR + EN).

| Change | Detail |
|--------|--------|
| `config/templates.py` (180L) | Jinja2 Environment with i18n extension, `newstyle=False`, thread-safe `ctx_lang` ContextVar. `render_template()` injects full i18n context: URLs, hreflang, OG locale, date_locale, gambling help, lang switch, chatbot/rating JS paths |
| `ui/templates/em/` (10 files) | 3 partials (`_base.html`, `_footer.html`, `_hero.html`) + 7 page templates. All `_()` translated strings, `{{ sponsor_js }}` / `{{ app_js }}` template variables |
| `routes/em_pages.py` | FR routes → `render_template("em/*.html", lang="fr")` |
| `routes/en_em_pages.py` | EN routes → `render_template("em/*.html", lang="en")` — same templates, different lang |
| Sponsor popup fix | `MOTEUR HYBRIDE EM` → `HYBRID ENGINE EM` in `sponsor-popup-em-en.js` + `sponsor-popup75-em-en.js`. `75 grilles` → `75 grids`. Added `date_locale` context var (`en-GB` / `fr-FR`) |
| `tests/test_templates.py` (37 tests) | Jinja2 env, EM_URLS, hreflang_tags, render_template FR/EN, all 7 pages x 2 langs, ContextVar isolation, gambling help, chatbot JS paths |

**Key design decision**: `newstyle=False` avoids Jinja2's `_make_new_gettext` auto-formatting (`rv % variables`) which breaks any `%` character in translated strings (CSS `60%`, `100%`, `%(total)s` placeholders).

**Result**: 10 Jinja2 templates serve 14 pages (7 FR + 7 EN). 37 new tests. 540 total, 0 failures. Later extended to 14 templates (+ 4 legal pages).

### P3/5 — JS i18n Centralisation (2026-02-27)

Centralized all JS-rendered strings into a single Python dict, injected via Jinja2 as `window.LotoIA_i18n`.

| Change | Detail |
|--------|--------|
| `config/js_i18n.py` (~1600L) | `_LABELS` dict: 6 langs (FR/EN/ES/PT/DE/NL), 160+ keys per lang (app-em, simulateur-em, sponsor-popup, meta75, rating, chatbot) |
| `ui/templates/em/_base.html` | Added `<script>window.LotoIA_i18n = {{ js_labels\|tojson }};</script>` |
| `config/templates.py` | `render_template()` injects `js_labels=get_js_labels(lang)` |
| EN static JS files | Deleted 5 of 6 EN-specific JS files (`app-em-en.js`, `simulateur-em-en.js`, `sponsor-popup-em-en.js`, `sponsor-popup75-em-en.js`, `faq-em-en.js`) — frontend now reads `window.LotoIA_i18n` |
| FR JS files | Refactored to read `window.LotoIA_i18n` labels instead of hardcoded French strings |
| `tests/test_js_i18n.py` (18 tests) | Label coverage, key parity FR/EN, rating keys, locale format |

**Result**: 5 duplicated JS files eliminated. Single source of truth for all JS strings. 540 → 558 tests, 0 failures.

### P4/5 — Prompts localisés + file-based loader (2026-02-27)

Refactored EM prompt system from PROMPT_MAP dict to file-based multilingual loader with lang fallback.

| Change | Detail |
|--------|--------|
| `services/prompt_loader.py` (143L) | New `load_prompt_em(name, lang)` with `@lru_cache`, fallback chain `[lang → en → fr]`. New `get_em_prompt(name, lang, **kwargs)` for safe variable substitution. New `em_window_to_prompt(window)` path resolver. Loto PROMPT_MAP unchanged. |
| `prompts/em/` (108 files) | 6 language directories (fr, en, pt, es, de, nl) x 18 files each (3 chatbot + 8 tirages + 7 annees) |
| `services/em_gemini.py` | Uses `load_prompt_em(em_window_to_prompt(window), lang)` instead of `PROMPT_MAP[f"EM_{window}"]` |
| `services/chat_pipeline_em.py` | Uses `load_prompt_em("prompt_hybride_em", lang)` for chatbot system prompt |
| `services/chat_sql_em.py` | Uses `load_prompt_em("prompt_sql_generator_em", lang)` for SQL generator |
| `config/languages.py` (96L) | Extended PROMPT_KEYS for chatbot/pitch/sql per language |
| `tests/test_prompts.py` (58 tests) | Loto PROMPT_MAP, EM load_prompt_em, lang fallback chain, variable substitution, em_window_to_prompt |

**Result**: EM prompts fully multilingual with graceful fallback. 558 → 616 tests, 0 failures.

### P5/5 — Routes multilingues + SEO (2026-02-27)

Factory-generated routes for PT/ES/DE/NL with kill switch, dynamic sitemap, and hreflang filtering.

| Change | Detail |
|--------|--------|
| `config/killswitch.py` (7L) | `ENABLED_LANGS = ["fr", "en", "es", "pt", "de", "nl"]` — all 6 languages active |
| `config/templates.py` (256L) | Extended `EM_URLS` for 6 languages with localized URL slugs. Dynamic `_LANG_SWITCH` (FR→EN, others→FR). `hreflang_tags()` reads `killswitch.ENABLED_LANGS`. Extended `_GAMBLING_HELP`, `_OG_LOCALE`, `_DATE_LOCALE` for all 6 langs. |
| `config/languages.py` (96L) | Extended `PAGE_SLUGS` for PT/ES/DE/NL (7 page types x 4 langs) |
| `routes/multilang_em_pages.py` (175L) | Factory routes: `_HERO_TEXTS` per lang, `_PAGE_DEFS` for 7 pages, `_make_handler()`/`_make_faq_handler()` closures. Kill switch check → 302 to FR if disabled. 28 routes = 7 pages x 4 langs |
| `routes/sitemap.py` (86L) | Dynamic `/sitemap.xml`: `_LOTO_PAGES` (14 static) + EM pages for `killswitch.ENABLED_LANGS`. Replaces static `ui/sitemap.xml` |
| `routes/pages.py` (230L) | Removed static sitemap route (was shadowing dynamic endpoint) |
| `main.py` (688L) | `_SEO_ROUTES` frozenset auto-built from `EM_URLS`. New router registrations: `multilang_em_router`, `sitemap_router` |
| `tests/test_multilang_routes.py` (67 tests) | Kill switch defaults, EM_URLS coverage (6 langs), hreflang filtering, route registration (28 routes), kill switch redirect, dynamic sitemap (structure, content, enabled/disabled langs), _LANG_SWITCH, gambling help, OG/date locale, PAGE_SLUGS |

**Localized URL slugs**:
- PT: gerador, simulador, estatisticas, historico, noticias
- ES: generador, simulador, estadisticas, historial, noticias
- DE: generator, simulator, statistiken, ziehungen, nachrichten
- NL: generator, simulator, statistieken, geschiedenis, nieuws

**Result**: 4 new languages route-ready with kill switch. Dynamic sitemap respects enabled langs. 616 → 683 tests, 0 failures.

### Phase 9 — SSE Streaming Chatbot (2026-02-28)

Real-time Server-Sent Events streaming for the HYBRIDE chatbot. Responses appear word-by-word in the browser instead of arriving as a single block.

| File | Lines | Purpose |
|------|-------|---------|
| `services/gemini.py` | 130→192 | `stream_gemini_chat()` async generator via `streamGenerateContent?alt=sse`, manual circuit breaker |
| `services/chat_pipeline.py` | 639→715 | Extracted `_prepare_chat_context()`, added `_sse_event()` + `handle_chat_stream()` |
| `services/chat_pipeline_em.py` | 653→760 | Same pattern: `_prepare_chat_context_em()` + `handle_chat_stream_em()` with `lang` support |
| `routes/api_chat.py` | 85→92 | `StreamingResponse` + `_SSE_HEADERS` (anti-buffering) |
| `routes/api_chat_em.py` | 73→85 | Same SSE StreamingResponse pattern |
| `routes/api_chat_unified.py` | 73→88 | Same SSE StreamingResponse for both game variants |
| `ui/static/hybride-chatbot.js` | ~500 | `fetch()` + `getReader()` + `TextDecoder` SSE parsing, `createBotBubble()` + `updateBubbleText()` |
| `ui/static/hybride-chatbot-em.js` | ~500 | Same streaming frontend for EuroMillions |
| `tests/test_routes.py` | +20 | Mock `stream_gemini_chat`, parse SSE events, verify `is_done` + `source` |

**Anti-buffering headers** (3 iterations to solve Cloud Run + GZipMiddleware buffering):
1. Initial deploy: responses buffered by GZipMiddleware
2. Added `Cache-Control: no-cache, no-transform` + `X-Accel-Buffering: no` — GZip still compresses
3. Added `Content-Encoding: identity` — forces GZipMiddleware to skip compression. Streaming confirmed.

**SSE event format**: `data: {"chunk": "text", "source": "gemini", "mode": "decouverte", "is_done": false}\n\n`

**Result**: 9 files changed, 683 → 684 tests, 0 failures. Real-time streaming confirmed on Cloud Run.

### Sprint ES — Complete Spanish Translation + Kill Switch Activation (2026-02-28)

Full Spanish (castillan) translation of the EuroMillions module: UI, backend labels, AI prompts, and kill switch activation.

**Sprint 1/2 — UI & Backend:**

| Change | Detail |
|--------|--------|
| `translations/es/LC_MESSAGES/messages.po` | 384 `msgstr` entries translated (from empty stubs). Cultural adaptations: Jugar Bien (gambling help), 900 200 225 (phone), Spanish legal references |
| `config/js_i18n.py` (+155 keys) | Full `"es"` section: locale `es-ES`, all 155 JS labels translated |
| `services/em_pdf_generator.py` (+25 keys) | `PDF_LABELS["es"]` block for META ANALYSE PDF reports |
| `em_schemas.py` (4 regex) | `^(fr\|en)$` → `^(fr\|en\|es)$` on 4 Pydantic schema `lang` fields |

**Sprint 2/2 — AI Prompts (18 files):**

| File | Lines | Description |
|------|-------|-------------|
| `prompts/em/es/prompt_hybride_em.txt` | ~453 | Main chatbot system prompt (identity, FAQ, rules, BDD) |
| `prompts/em/es/prompt_pitch_grille_em.txt` | ~65 | Grid pitch generator (conformity tiers) |
| `prompts/em/es/prompt_sql_generator_em.txt` | ~184 | SQL generator ({TODAY} preserved, Spanish question examples) |
| `prompts/em/es/annees/prompt_1a..6a.txt + global` | 7 | Year-based analysis horizons (corto→largo plazo) |
| `prompts/em/es/tirages/prompt_100..700.txt + global` | 8 | Draw-based analysis horizons (100-700 + global) |

**Translation choices**: Data Science tone — "combinación" (not "boleto"), "modelado de probabilidades", "análisis estadístico". No lottery jargon ("ganar", "apostar", "suerte"). Internal tags kept in French (`[DONNÉES TEMPS RÉEL]`, `[RÉSULTAT SQL]` — code-matched). Gambling help: Jugar Bien / www.jugarbien.es / 900 200 225.

**Kill switch activation**: `ENABLED_LANGS` updated to include `"es"`. Tests updated: kill switch default, hreflang (4 tags), sitemap includes ES, ES pages return 200.

**Result**: 26 files changed, +1621/-1412 lines. 684 → 685 tests, 0 failures. Deployed revision `hybride-api-00018-qm9`, 7 ES pages live at `lotoia.fr/es/euromillions/*`.

### Sprint PT — Complete Portuguese Translation + Kill Switch Activation (2026-02-28)

Full European Portuguese (PT-PT) translation of the EuroMillions module: UI, backend labels, AI prompts, and kill switch activation.

| Change | Detail |
|--------|--------|
| `translations/pt/LC_MESSAGES/messages.po` | 384 `msgstr` entries translated. Cultural adaptations: Jogo Responsável (gambling help), 808 200 204 (phone), European Portuguese (not Brazilian) |
| `config/js_i18n.py` (+160 keys) | Full `"pt"` section: locale `pt-PT`, all JS labels translated |
| `services/em_pdf_generator.py` (+25 keys) | `PDF_LABELS["pt"]` block for META ANALYSE PDF reports |
| `config/i18n.py` | `_badges("pt")` (8 keys) + `_analysis_strings("pt")` (30 keys) |
| `em_schemas.py` (4 regex) | `^(fr|en|es)$` → `^(fr|en|pt|es)$` |
| `prompts/em/pt/` (18 files) | All 18 prompts translated (PT-PT). Language header: `[IDIOMA — REGRA OBRIGATÓRIA]` |

**Result**: 685 → 689 tests, 0 failures. 7 PT pages live at `lotoia.fr/pt/euromillions/*`.

### Sprint DE — Complete German Translation + Kill Switch Activation (2026-02-28)

Full German (Hochdeutsch) translation of the EuroMillions module: UI, backend labels, AI prompts, and kill switch activation.

| Change | Detail |
|--------|--------|
| `translations/de/LC_MESSAGES/messages.po` | 384 `msgstr` entries translated. Cultural adaptations: Spielerschutz (gambling help). `100% gratis` pattern to avoid Babel `%g` format spec conflict |
| `config/js_i18n.py` (+160 keys) | Full `"de"` section: locale `de-DE`, all JS labels translated |
| `services/em_pdf_generator.py` (+25 keys) | `PDF_LABELS["de"]` block for META ANALYSE PDF reports |
| `config/i18n.py` | `_badges("de")` (8 keys) + `_analysis_strings("de")` (30 keys) |
| `em_schemas.py` (4 regex) | `^(fr|en|pt|es)$` → `^(fr|en|pt|es|de)$` |
| `prompts/em/de/` (18 files) | All 18 prompts translated. Language header: `[SPRACHE — PFLICHT]` |

**Babel `%g` bug fix**: `100% gratuit` → Babel auto-detects `%g` as Python format spec. DE `100% kostenlos` produces `%k` (mismatch → build failure). Fix: `100% gratis` keeps `%g` compatible.

**Result**: 689 → 691 tests, 0 failures. 7 DE pages live at `lotoia.fr/de/euromillions/*`.

### Sprint NL — Complete Dutch Translation + Kill Switch Activation (2026-02-28)

Full Dutch (Belgian standard Nederlands) translation of the EuroMillions module — **final language, completing 6/6**.

| Change | Detail |
|--------|--------|
| `translations/nl/LC_MESSAGES/messages.po` | 384 `msgstr` entries translated. Belgian cultural references: Gokkliniek (gambling help), 078 15 13 14 (phone). `100% gratis` pattern |
| `config/js_i18n.py` (+160 keys) | Full `"nl"` section: locale `nl-BE`, all JS labels translated |
| `services/em_pdf_generator.py` (+25 keys) | `PDF_LABELS["nl"]` block for META ANALYSE PDF reports |
| `config/i18n.py` | `_badges("nl")` (8 keys) + `_analysis_strings("nl")` (30 keys) |
| `services/em_gemini.py` | NL system instruction: `"VERPLICHT: Je schrijft ALTIJD in correct Nederlands."` |
| `services/chat_utils.py` | NL sponsor messages + NL strip filter keywords |
| `em_schemas.py` (4 regex) | `^(fr|en|pt|es|de)$` → `^(fr|en|pt|es|de|nl)$` |
| `config/killswitch.py` | `ENABLED_LANGS = ["fr", "en", "es", "pt", "de", "nl"]` — all 6 ON |
| `prompts/em/nl/` (18 files) | All 18 prompts translated. Language header: `[TAAL — VERPLICHTE REGEL]` |

**Result**: 691 → 688 tests (NL-disabled tests removed, no more disabled languages), 0 failures. 7 NL pages live at `lotoia.fr/nl/euromillions/*`. **i18n 6/6 COMPLETE.**

### Fix — Chatbot EM Welcome Message Per-Language (2026-03-01)

Fixed bug where the EuroMillions chatbot welcome message always displayed in French for ES/PT/DE/NL pages.

| Change | Detail |
|--------|--------|
| `ui/static/hybride-chatbot-em.js` | `STORAGE_KEY` made per-language: `hybride-history-em` + lang suffix (`-es`, `-pt`, `-de`, `-nl`). FR keeps base key. Prevents cross-language sessionStorage contamination |
| `config/js_i18n.py` | Updated `chatbot_welcome` for ES/PT/DE/NL with correct translations |
| `tests/test_js_i18n.py` (+3 tests) | `test_chatbot_welcome_not_french_for_other_langs`, `test_chatbot_welcome_language_markers`, `test_chatbot_welcome_injected_per_lang` |

**Root cause**: All non-EN languages shared the same sessionStorage key `hybride-history-em`. When FR was visited first, the French welcome was cached and restored on other language pages.

**Result**: 688 → 691 tests, 0 failures.

### Feature — Mobile Globe Language Selector (2026-03-01)

Added a globe button (🌐) on mobile (≤768px) replacing inline lang-switch buttons, with dropdown showing all 6 languages with flags.

| Change | Detail |
|--------|--------|
| `config/templates.py` | Added `_build_all_lang_switches()` returning all enabled langs with flags + current marker. Added `all_lang_switches` and `lang_flag` to render context |
| `ui/templates/em/_base.html` | Added `.lang-globe-wrap` with globe button + dropdown (`role="menu"`, `aria-expanded`) |
| `ui/static/style.css` | +90 lines: `.lang-globe-*` styles. Desktop: `display: none`. Mobile `@media (max-width: 768px)`: globe visible, inline `.lang-switch` hidden |
| `tests/test_templates.py` (+7 tests) | Globe in HTML, current lang highlighted, all 6 langs in dropdown, URLs match page, desktop switches preserved, `_build_all_lang_switches` unit test |

**Design**: Desktop unchanged (inline buttons). Mobile: single globe button shows current lang code, opens dropdown with flags, active lang highlighted, click outside closes.

**Result**: 691 → 698 tests, 0 failures.

### Feature — Legal Pages EM Multilingues + Footer Corrigé (2026-03-01)

Added 4 multilingual legal pages for EuroMillions (6 languages each) and updated the EM footer to use dynamic per-language legal URLs.

| Change | Detail |
|--------|--------|
| `ui/templates/em/mentions-legales.html` (new, ~500L) | Legal notices: publisher, hosting (GCP), IP, liability, personal data, cookies, external links, applicable law, contact. All 6 langs |
| `ui/templates/em/confidentialite.html` (new, ~800L) | Privacy policy: 12 GDPR/RGPD sections. Per-lang supervisory authorities (CNIL, ICO, AEPD, CNPD, BfDI, AP) |
| `ui/templates/em/cookies.html` (new, ~1260L) | Cookie policy: 8 sections, JS cookie settings and data clearing buttons |
| `ui/templates/em/disclaimer.html` (new, ~710L) | Disclaimer: gambling warning 18+, AI warning, liability limitation. Per-lang gambling help resources |
| `config/templates.py` | 24 new legal URLs in `EM_URLS` (4 pages x 6 languages with localized slugs) |
| `ui/templates/em/_footer.html` | Dynamic legal URLs: `{{ urls.mentions }}`, `{{ urls.confidentialite }}`, `{{ urls.cookies }}`, `{{ urls.disclaimer }}` (was hardcoded FR) |
| `routes/em_pages.py` (+4 routes) | FR legal: `/euromillions/mentions-legales`, `/euromillions/confidentialite`, `/euromillions/cookies`, `/euromillions/avertissement` |
| `routes/en_em_pages.py` (+4 routes) | EN legal: `/en/euromillions/legal-notices`, `/en/euromillions/privacy`, `/en/euromillions/cookies`, `/en/euromillions/disclaimer` |
| `routes/multilang_em_pages.py` (+4 `_PAGE_DEFS`) | Legal pages added to factory: 16 new routes (4 pages x 4 langs) |
| `tests/test_templates.py` (+39 tests) | Legal page rendering (4 pages x 6 langs), noindex, canonical, `EM_URLS` legal keys, footer links per lang |
| `tests/test_multilang_routes.py` (updated) | Route count 7→11 per lang, route match includes legal keys |

**Localized legal URL slugs**:
- FR: mentions-legales, confidentialite, cookies, avertissement
- EN: legal-notices, privacy, cookies, disclaimer
- PT: avisos-legais, privacidade, cookies, aviso
- ES: aviso-legal, privacidad, cookies, aviso
- DE: impressum, datenschutz, cookies, haftungsausschluss
- NL: juridische-kennisgeving, privacy, cookies, disclaimer

**Result**: 698 → 737 tests, 0 failures. 66 EM routes total (11 pages x 6 langs). All legal pages have `noindex, follow` meta.

### Phase A — Argent / Money / Gambling Detection (2026-03-03)

13th detection phase in both Loto FR and EuroMillions pipelines. Court-circuit (no Gemini call) — detects money, gambling, and addiction keywords and returns a pre-written response with escalating severity.

**Pipeline position**: I (Insult) → C (Compliment) → **A (Argent)** → 0 (Continuation) → ...

| Level | Trigger | Response Tone | Example |
|-------|---------|---------------|---------|
| **L1 — Pedagogical** | Default (jackpot, money, gains...) | Redirect to stats | "Ici, on ne parle pas d'argent — on parle de DATA !" |
| **L2 — Firm** | Strong words (devenir riche, stratégie pour gagner...) | Warning | "⚠️ Le jeu ne doit jamais être considéré comme un revenu." |
| **L3 — Help Redirection** | Betting/addiction words (parier, miser, gambling...) | 🛑 + help link | "🛑 Le jeu comporte des risques. Si besoin: joueurs-info-service.fr" |

| File | Lines | Changes |
|------|-------|---------|
| `services/chat_detectors.py` | 850→939 | `_detect_argent()`, `_get_argent_response()`, FR word lists + response pools L1/L2/L3 |
| `services/chat_detectors_em.py` | 495→784 | `_detect_argent_em(msg, lang)`, 6-lang word lists (phrases + mots + strong + betting), response pools FR/ES/PT/DE/NL, `_ARGENT_POOLS_EM` dispatch dict |
| `services/chat_responses_em_en.py` | ~250→277 | EN pools L1/L2/L3, `_get_argent_response_em_en()`, strong/betting EN patterns |
| `services/chat_pipeline.py` | 715→723 | Phase A block after Phase C (Loto FR) |
| `services/chat_pipeline_em.py` | 760→771 | Phase A block after Phase C (EM, lang-aware dispatch EN vs other) |
| `tests/test_argent.py` | 373 (new) | 84 tests: detection FR/EN/ES/PT/DE/NL, L1/L2/L3 levels, response language, L3 help links, non-regression |

**L3 help links by language**:
- FR: joueurs-info-service.fr (ANJ)
- EN: begambleaware.org / ncpgambling.org
- ES: jugarbien.es / 900 200 225
- PT: jogoresponsavel.pt / 808 200 204
- DE: bzga.de / 0800-1372700
- NL: agog.nl / 0900-2177

**Result**: 888 → 972 tests (+84), 0 failures. `source: "hybride_argent"` in analytics.

### Cumulative Impact

| Metric | Before P1 | After P5/5 |
|--------|-----------|------------|
| `api_chat.py` | 2014L monolith | 82L wrapper |
| `api_chat_em.py` | 1668L monolith | 73L wrapper |
| `stats_service.py` + `em_stats_service.py` | 1418L duplicated | 978L (base class + wrappers) |
| Route duplication (data+analyse) | ~2600L | ~1430L unified + ~400L wrappers |
| Database driver | PyMySQL (sync + 68 to_thread) | aiomysql (native async) |
| Cache | In-memory dict | Redis async + in-memory fallback |
| Security headers | Basic CSP | CSP + HSTS preload + COOP + Permissions-Policy |
| EM page serving | Static HTML (duplicated FR/EN) | Jinja2 templates (14 templates shared 6 langs, P2/5 + legal pages) |
| JS i18n | Hardcoded FR + 6 EN-specific JS files | `window.LotoIA_i18n` centralized, 6 langs (P3/5 + Sprints ES/PT/DE/NL) |
| EM prompts | PROMPT_MAP dict (FR-only) | File-based multilang (6 langs, fallback chain, P4/5). All 6 fully translated |
| Multilang routes | FR + EN only | 6 langs (66 EM routes: 11 pages x 6 langs), kill switch, dynamic sitemap (P5/5). All 6 activated |
| i18n | FR only | Babel/gettext 6 langs + Jinja2 + JS labels + prompts + routes (P1-P5/5). **All 6 complete** |
| Chatbot delivery | Batch (single block response) | SSE streaming (word-by-word, P9) |
| Legal pages | None | 4 multilingual legal pages (mentions, privacy, cookies, disclaimer) x 6 langs = 24 URLs |
| Mobile UX | Inline lang buttons (all sizes) | Globe selector on mobile (≤768px), inline buttons on desktop |
| Chatbot detection | 12 phases | **13 phases** (+ Phase A: argent/money/gambling) |
| Tests | 248 | **972** |
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
| 2026-02-27 | P1/5: gettext + Babel infrastructure — 6-language .po catalogs, config/i18n.py, 30 i18n tests |
| 2026-02-27 | P2/5: Jinja2 templates — 10 templates (shared FR/EN), render_template(), sponsor popup EN fix, 37 template tests |
| 2026-02-27 | P3/5: JS i18n — `config/js_i18n.py` (130+ keys FR/EN), `window.LotoIA_i18n`, deleted 5 EN JS files, 18 tests |
| 2026-02-27 | P4/5: Prompts localisés — file-based `load_prompt_em(name, lang)` with fallback chain, `prompts/em/` (108 files, 6 langs), 58 tests |
| 2026-02-27 | P5/5: Routes multilingues + SEO — kill switch, 28 factory routes (PT/ES/DE/NL), dynamic sitemap, hreflang filtering, 67 tests. 683 tests. |
| 2026-02-28 | P9: SSE Streaming — real-time word-by-word chatbot responses via `stream_gemini_chat()`, `handle_chat_stream()`, `getReader()` frontend. Anti-buffering headers (`Content-Encoding: identity`). 684 tests. |
| 2026-02-28 | Sprint ES: Complete Spanish translation — 384 .po entries, 155 JS keys, 25 PDF labels, 18 AI prompts (Data Science tone), 4 schema regex. Kill switch activated. 7 ES pages live. **685 tests.** |
| 2026-02-28 | Sprint PT: Complete Portuguese (PT-PT) translation — 384 .po, 160+ JS, 25 PDF, 18 prompts, badges, analysis strings. Kill switch activated. 7 PT pages live. **689 tests.** |
| 2026-02-28 | Sprint DE: Complete German (Hochdeutsch) translation — 384 .po, 160+ JS, 25 PDF, 18 prompts. Babel `%g` bug fix (`gratis` pattern). 7 DE pages live. **691 tests.** |
| 2026-02-28 | Sprint NL: Complete Dutch (Belgian Nederlands) translation — FINAL language. 384 .po, 160+ JS, 25 PDF, 18 prompts. `ENABLED_LANGS` = all 6. **i18n 6/6 COMPLETE. 688 tests.** |
| 2026-03-01 | Fix: Chatbot EM welcome per-language sessionStorage key. Per-lang `STORAGE_KEY` in `hybride-chatbot-em.js`. **691 tests.** |
| 2026-03-01 | Feature: Mobile globe language selector (🌐). Globe button + dropdown on mobile ≤768px, desktop unchanged. **698 tests.** |
| 2026-03-01 | Feature: Legal pages EM multilingues (4 pages x 6 langs = 24 URLs). mentions-legales, confidentialite, cookies, disclaimer. Footer dynamic URLs. 66 EM routes total. **737 tests.** |
| 2026-03-03 | Phase A: Argent/money/gambling detection — 13th pipeline phase. Court-circuit (no Gemini). 3-level escalation (L1 pedagogical, L2 firm, L3 help redirection). 6-lang response pools + word lists (FR/EN/ES/PT/DE/NL). Country-specific gambling support links. **972 tests.** |

---

## 12. Project Status

| Area | Status | Notes |
|------|--------|-------|
| Backend (FastAPI + aiomysql) | Stable | ~688L orchestrator, 18 routers, native async DB (Phase 5), 12 middlewares |
| Unified Routes | Stable | `/api/{game}/...` with `game = loto \| euromillions` (Phase 10), backward compat preserved |
| HYBRIDE Engine (Loto) | Stable | Scoring, constraints, badges functional |
| HYBRIDE Engine (EuroMillions) | Stable | 5 boules [1-50] + 2 etoiles [1-12] |
| HYBRIDE Chatbot (Loto) | Stable | Modular: 4 service modules (Phase 1). 13-phase detection (Phase A: argent), Text-to-SQL, SSE streaming (P9), session persistence, GA4 tracking, sponsor system. 6 pages. |
| HYBRIDE Chatbot (EuroMillions) | Stable | Modular: 4 service modules (Phase 4). 13-phase detection (Phase A: argent, 6 langs). SSE streaming (P9). Same architecture as Loto. 7 FR + 7 EN pages (Phase 11). Isolated sessionStorage. EN response pools + EN prompts. |
| i18n / Multilang | **Complete (P1-P5/5 + Sprints ES/PT/DE/NL)** | Babel/gettext (P1/5), Jinja2 templates (P2/5), JS i18n (P3/5), multilang prompts (P4/5), routes+sitemap+killswitch (P5/5). **All 6 languages fully translated and live**: FR, EN, ES, PT, DE, NL. 66 EM routes (11 pages x 6 langs). 384 .po entries, 160+ JS keys, 25 PDF labels, 18 AI prompts per lang. `ENABLED_LANGS = ["fr", "en", "es", "pt", "de", "nl"]`. 4 multilingual legal pages. Mobile globe lang selector. Remaining: rating popup (5 FR strings). Loto EN not yet planned. |
| Stats Layer | Stable | Base class (Phase 2): 770L base + 2 thin wrappers, GameConfig-driven |
| META ANALYSE 75 (Loto) | Stable | Async Gemini enrichment + PDF export, circuit breaker fallback. 18 Loto prompt keys. |
| META ANALYSE 75 (EM) | Stable | Dual graphs, EM Gemini enrichment, EM PDF (2x2 matplotlib), 14 EM prompt keys. |
| Cache | Stable | Redis async + in-memory fallback (Phase 6). PDF off-thread. |
| Testing | Active | **972 tests** (pytest, 25 test files), CI integration |
| Security | Hardened | CSP+HSTS preload+COOP (Phase 7), aiomysql parameterized queries, rate limiting, correlation IDs |
| SEO | Stable | Schema.org Dataset (Phase 7), bankability T4 pivot (Phase 8), dynamic sitemap (P5/5), hreflang multilang (P5/5), structured data, canonical redirects |
| Mobile responsive | Stable | Fullscreen chatbot, viewport sync, safe-area support |

---

## 13. Performance Metrics

Not formally benchmarked yet.

Observable characteristics based on development usage:

- `/api/meta-analyse-local` typically responds in < 300ms (Cloud SQL aggregate queries)
- Gemini API calls (`/api/meta-analyse-texte`) are bound by external latency (5-15s typical)
- `/api/hybride-chat` uses SSE streaming (P9): first token appears in ~500ms, full response streams progressively over 3-8s
- Static assets benefit from cache headers (7-30 days depending on type)
- No client-side performance profiling has been conducted

---

## 14. Known Limitations

- **Two database tables** — Draw data split into `tirages` (Loto) and `tirages_euromillions` (EM) in same `lotofrance` database. No partitioning, no read replicas.
- **Redis optional** — `services/cache.py` falls back to per-process in-memory cache if `REDIS_URL` absent (not shared across 2 workers in fallback mode).
- **Gemini dependency** — META ANALYSE and chatbot depend on an external API. Mitigated by circuit breaker + fallback messages, but degraded experience when open.
- **Minimal monitoring** — Production observability relies on Cloud Run metrics + JSON structured logs with correlation IDs. No APM or alerting.
- **Test coverage** — 972 tests across 25 files. Core engine, chat pipeline, stats, insult/OOR/argent detection, templates, legal pages, i18n, JS labels, prompts, multilang routes, PDF heatmap well covered. Some route handlers have lower coverage.
- **i18n residue** — Full i18n pipeline complete (P1-P5/5 + Sprints ES/PT/DE/NL): gettext, Jinja2, JS labels, prompts, routes, sitemap, kill switch. **All 6 languages fully translated and live.** 4 legal pages translated. Cookie consent banner translated (6 langs). 1 minor FR residue: rating popup labels (5 FR strings in `rating-popup.js`). Loto EN not yet planned.

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

*Updated by JyppY & Claude Opus 4.6 — 03/03/2026 (v19.0: Phase A — Argent/money/gambling detection. 13th pipeline phase, court-circuit, 3-level escalation L1/L2/L3, 6-lang response pools FR/EN/ES/PT/DE/NL, country-specific gambling help links. 972 tests, 0 failures. Previous: v18.0 GA4 audit, v17.0 PDF heatmap, v16.0 legal pages, globe selector, chatbot fix. i18n 6/6 COMPLETE, P9 (SSE streaming), P1-P5/5 (i18n infrastructure), Phase 11 (EN multilang), Phases 1-10.)*
