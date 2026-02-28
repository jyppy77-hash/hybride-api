import os
import re
import time
import uuid
import asyncio
import contextvars
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import httpx
import logging
import sys
from pythonjsonlogger import jsonlogger

import db_cloudsql
from rate_limit import limiter
from config.version import __version__, APP_VERSION, APP_NAME, VERSION_DATE
from services.circuit_breaker import gemini_breaker
from routes.pages import router as pages_router
from routes.api_data import router as data_router
from routes.api_analyse import router as analyse_router
from routes.api_gemini import router as gemini_router
from routes.api_pdf import router as pdf_router
from routes.api_tracking import router as tracking_router
from routes.api_chat import router as chat_router
from routes.em_data import router as em_data_router
from routes.em_analyse import router as em_analyse_router
from routes.em_pages import router as em_pages_router
from routes.api_chat_em import router as em_chat_router  # Phase 4 — Chatbot EM
from routes.api_ratings import router as ratings_router
from routes.api_data_unified import router as unified_data_router      # Phase 10
from routes.api_analyse_unified import router as unified_analyse_router  # Phase 10
from routes.api_chat_unified import router as unified_chat_router      # Phase 10
from routes.en_em_pages import router as en_em_pages_router            # Phase 11 — EN EuroMillions
from routes.multilang_em_pages import router as multilang_em_router    # P5/5 — PT/ES/DE/NL
from routes.sitemap import router as sitemap_router                    # P5/5 — Dynamic sitemap

# ── JSON structured logging ──
_log_handler = logging.StreamHandler(sys.stdout)
_log_handler.setFormatter(
    jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
        rename_fields={"asctime": "timestamp", "levelname": "severity"},
    )
)
logging.root.handlers = [_log_handler]
logging.root.setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# ── Uptime tracking ──
_STARTED_AT = time.monotonic()


# ── Correlation ID via contextvars (thread-safe / async-safe) ──

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


class RequestIdFilter(logging.Filter):
    """Injecte request_id depuis le ContextVar dans chaque LogRecord."""

    def filter(self, record):
        record.request_id = _request_id_ctx.get("")
        return True


logging.root.addFilter(RequestIdFilter())

# ── SEO routes set (computed once at import from EM_URLS) ──
from config.templates import EM_URLS as _EM_URLS
_SEO_ROUTES = {
    "/", "/accueil", "/loto", "/loto/analyse", "/loto/exploration",
    "/loto/statistiques", "/faq", "/news",
    "/historique", "/methodologie", "/moteur", "/disclaimer",
    "/mentions-legales", "/politique-confidentialite", "/politique-cookies",
}
for _lu in _EM_URLS.values():
    _SEO_ROUTES.update(_lu.values())


@asynccontextmanager
async def lifespan(app):
    """Startup/shutdown : client HTTP partage + pool DB + cache."""
    from services.cache import init_cache, close_cache
    app.state.httpx_client = httpx.AsyncClient(timeout=20.0)
    await db_cloudsql.init_pool()
    await init_cache()
    yield
    await close_cache()
    await db_cloudsql.close_pool()
    await app.state.httpx_client.aclose()


app = FastAPI(
    title="HYBRIDE API",
    description="Moteur HYBRIDE_OPTIMAL_V1 — API officielle",
    version=__version__,
    redirect_slashes=False,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Rate limiter (slowapi)
app.state.limiter = limiter


def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "Trop de requetes. Reessayez dans quelques instants."}
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)


# Page 404 HTML personnalisée (SEO + UX)
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        with open("ui/404.html", "r", encoding="utf-8") as f:
            html_404 = f.read()
        return HTMLResponse(content=html_404, status_code=404)
    return JSONResponse(content={"detail": exc.detail}, status_code=exc.status_code)

# Rate limiting middleware
app.add_middleware(SlowAPIMiddleware)

# CORS
_cors_origins = [
    "https://lotoia.fr",
    "https://www.lotoia.fr",
]
if not os.getenv("K_SERVICE"):  # localhost uniquement en dev local
    _cors_origins.append("http://localhost:8080")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# =========================
# Correlation ID middleware
# =========================

_VALID_REQUEST_ID = re.compile(r'^[a-zA-Z0-9\-_]{1,64}$')


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Genere un UUID par requete, l'injecte dans les logs et le header de reponse."""
    raw_id = request.headers.get("x-request-id", "")
    request_id = raw_id if _VALID_REQUEST_ID.match(raw_id) else uuid.uuid4().hex[:16]
    request.state.request_id = request_id

    # Injecter via contextvars (async-safe, pas de race condition)
    token = _request_id_ctx.set(request_id)
    try:
        response = await call_next(request)
    finally:
        _request_id_ctx.reset(token)

    response.headers["X-Request-ID"] = request_id
    return response


# =========================
# Security Headers
# =========================

_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://cloud.umami.is; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https://*.google-analytics.com https://*.googletagmanager.com https://*.google.com; "
    "font-src 'self'; "
    "connect-src 'self' https://www.googletagmanager.com https://*.google-analytics.com https://analytics.google.com https://*.analytics.google.com https://cloud.umami.is https://api-gateway.umami.dev; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "worker-src 'none'; "
    "upgrade-insecure-requests"
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Injecte les headers de securite sur toutes les reponses."""
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


# =========================
# Canonical Domain (SEO only: www → root)
# =========================
@app.middleware("http")
async def canonical_www_redirect(request: Request, call_next):
    """Redirige UNIQUEMENT www.lotoia.fr → lotoia.fr (SEO canonical)."""
    host = request.headers.get("host", "").split(":")[0].lower()

    # Seul www.lotoia.fr est redirigé vers lotoia.fr
    if host == "www.lotoia.fr":
        proto = request.headers.get("x-forwarded-proto", "https")
        path = request.url.path
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(url=f"{proto}://lotoia.fr{path}{query}", status_code=301)

    # Tous les autres hosts passent sans modification
    return await call_next(request)


# =========================
# SEO: force 301 HTTP → HTTPS (filet de sécurité)
# Le 302 principal vient du GFE Cloud Run (hors contrôle applicatif).
# Ce middleware intercepte les requêtes HTTP qui atteindraient l'app.
# =========================
@app.middleware("http")
async def redirect_http_to_https(request: Request, call_next):
    """301 redirect si x-forwarded-proto indique HTTP."""
    if request.headers.get("x-forwarded-proto") == "http":
        url = str(request.url).replace("http://", "https://", 1)
        return RedirectResponse(url=url, status_code=301)
    return await call_next(request)


# =========================
# SEO: strip trailing slash → 301 redirect (redirect_slashes=False)
# =========================
@app.middleware("http")
async def strip_trailing_slash(request: Request, call_next):
    """301 redirect /foo/ → /foo (sauf racine /)."""
    path = request.url.path
    if path != "/" and path.endswith("/"):
        clean = path.rstrip("/")
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(url=f"{clean}{query}", status_code=301)
    return await call_next(request)


# Middleware cache headers SEO
@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path

    # Cache long pour assets statiques
    if path.startswith("/static/") or path.startswith("/ui/static/"):
        if path.endswith((".css", ".js")):
            response.headers["Cache-Control"] = "public, max-age=604800"  # 7 jours
        elif path.endswith((".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp")):
            response.headers["Cache-Control"] = "public, max-age=2592000"  # 30 jours

    # Cache court pour pages HTML (SEO routes)
    if path.endswith(".html") or path in _SEO_ROUTES:
        response.headers["Cache-Control"] = "public, max-age=3600"  # 1 heure

    return response


# =========================
# SEO: 301 redirect /ui/*.html → clean URL
# =========================

_UI_HTML_TO_CLEAN_URL = {
    "index.html": "/accueil",
    "launcher.html": "/",
    "accueil.html": "/accueil",
    "loto.html": "/loto",
    "simulateur.html": "/loto/analyse",
    "statistiques.html": "/loto/statistiques",
    "faq.html": "/faq",
    "news.html": "/news",
    "historique.html": "/historique",
    "methodologie.html": "/methodologie",
    "moteur.html": "/moteur",
    "disclaimer.html": "/disclaimer",
    "mentions-legales.html": "/mentions-legales",
    "politique-confidentialite.html": "/politique-confidentialite",
    "politique-cookies.html": "/politique-cookies",
    "pronostics.html": "/loto",
    "chatbot.html": "/loto",
    # Sprint 3-3.5 (22/02/2026)
    "loto-ia.html": "/loto/intelligence-artificielle",
    "a-propos.html": "/a-propos",
    "hybride.html": "/hybride",
    "numeros-plus-sortis.html": "/loto/numeros-les-plus-sortis",
}

_UI_EM_HTML_TO_CLEAN_URL = {
    "accueil-em.html": "/euromillions",
    "euromillions.html": "/euromillions/generateur",
    "simulateur-em.html": "/euromillions/simulateur",
    "statistiques-em.html": "/euromillions/statistiques",
    "historique-em.html": "/euromillions/historique",
    "faq-em.html": "/euromillions/faq",
    "news-em.html": "/euromillions/news",
}

_UI_EN_EM_HTML_TO_CLEAN_URL = {
    "home.html": "/en/euromillions",
    "generator.html": "/en/euromillions/generator",
    "simulator.html": "/en/euromillions/simulator",
    "statistics.html": "/en/euromillions/statistics",
    "history.html": "/en/euromillions/history",
    "faq.html": "/en/euromillions/faq",
    "news.html": "/en/euromillions/news",
}


@app.middleware("http")
async def redirect_ui_html_to_seo(request: Request, call_next):
    """301 redirect /ui/<page>.html and /ui/em/<page>.html → clean URL (SEO dedup)."""
    path = request.url.path
    if path.startswith("/ui/") and path.endswith(".html"):
        filename = path[len("/ui/"):]
        clean_url = _UI_HTML_TO_CLEAN_URL.get(filename)
        if not clean_url and filename.startswith("em/"):
            em_filename = filename[len("em/"):]
            clean_url = _UI_EM_HTML_TO_CLEAN_URL.get(em_filename)
        if not clean_url and filename.startswith("en/euromillions/"):
            en_filename = filename[len("en/euromillions/"):]
            clean_url = _UI_EN_EM_HTML_TO_CLEAN_URL.get(en_filename)
        if clean_url:
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(url=f"{clean_url}{query}", status_code=301)
    return await call_next(request)


# =========================
# HEAD method support — Pure ASGI middleware (SEO crawlers / monitoring)
# BaseHTTPMiddleware has known issues with FileResponse; raw ASGI is reliable.
# =========================

class HeadMethodMiddleware:
    """Convert HEAD → GET at the ASGI level, then strip the response body."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "HEAD":
            await self.app(scope, receive, send)
            return

        # Switch method so downstream routes match GET handlers
        scope["method"] = "GET"
        body_sent = False

        async def send_wrapper(message):
            nonlocal body_sent
            if message["type"] == "http.response.start":
                # Strip Content-Length (body will be empty)
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() != b"content-length"
                ]
                await send({**message, "headers": headers})
            elif message["type"] == "http.response.body":
                if not body_sent:
                    body_sent = True
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                # Ignore subsequent body chunks (streaming responses)
            else:
                await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(HeadMethodMiddleware)

# P1 i18n — Language detection (sets request.state.lang + ctx_lang ContextVar)
from middleware.i18n_middleware import I18nMiddleware
app.add_middleware(I18nMiddleware)


# =========================
# Umami owner-IP filter — Pure ASGI middleware
# Injects <script>window.__OWNER__=true;</script> before </head> when the
# visitor is the site owner. Combined with data-before-send="umamiBeforeSend"
# on the Umami script tag, this silently blocks analytics for the owner.
# =========================

_OWNER_IP = os.environ.get("OWNER_IP", "").strip()
_OWNER_IPV6 = os.environ.get("OWNER_IPV6", "").strip()

_OWNER_EXACT = {"127.0.0.1", "::1"}  # localhost toujours exclu (dev)
_OWNER_PREFIXES = []  # IPv6 prefix match (privacy extensions)

if _OWNER_IP:
    _OWNER_EXACT.add(_OWNER_IP)
if _OWNER_IPV6:
    _OWNER_PREFIXES.append(_OWNER_IPV6)

logger.info("UmamiOwnerFilter: raw OWNER_IP=%r OWNER_IPV6=%r", _OWNER_IP, _OWNER_IPV6)
logger.info("UmamiOwnerFilter: exact=%s prefixes=%s", _OWNER_EXACT, _OWNER_PREFIXES)


def _is_owner_ip(ip: str) -> bool:
    if ip in _OWNER_EXACT:
        return True
    return any(ip.startswith(p) for p in _OWNER_PREFIXES)

_OWNER_INJECT = b'<script>window.__OWNER__=true;</script>\n</head>'


class UmamiOwnerFilterMiddleware:
    """Inject window.__OWNER__=true into HTML responses for the owner IP."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract client IP from x-forwarded-for (Cloud Run proxy)
        headers_raw = dict(scope.get("headers", []))
        forwarded = headers_raw.get(b"x-forwarded-for", b"").decode()
        client_ip = forwarded.split(",")[0].strip() if forwarded else ""
        if not client_ip:
            client_addr = scope.get("client")
            client_ip = client_addr[0] if client_addr else ""

        path = scope.get("path", "")
        is_owner = _is_owner_ip(client_ip)

        if not is_owner:
            await self.app(scope, receive, send)
            return

        logger.info("UmamiOwnerFilter: INJECT __OWNER__ | ip=%s path=%s", client_ip, path)

        # Owner IP detected — check if response is HTML, then inject flag
        is_html = False
        body_chunks = []

        async def send_wrapper(message):
            nonlocal is_html, body_chunks

            if message["type"] == "http.response.start":
                hdrs = dict(message.get("headers", []))
                ct = hdrs.get(b"content-type", b"").decode().lower()
                ce = hdrs.get(b"content-encoding", b"").decode().lower()
                is_html = "text/html" in ct
                if not is_html:
                    await send(message)
                else:
                    body_chunks.append(("start", message))
                return

            if message["type"] == "http.response.body":
                if not is_html:
                    await send(message)
                    return

                body_chunks.append(("body", message.get("body", b"")))
                more = message.get("more_body", False)
                if not more:
                    full_body = b"".join(
                        chunk for tag, chunk in body_chunks if tag == "body"
                    )
                    full_body = full_body.replace(b"</head>", _OWNER_INJECT, 1)

                    start_msg = body_chunks[0][1]
                    new_headers = [
                        (k, v) for k, v in start_msg.get("headers", [])
                        if k.lower() != b"content-length"
                    ]
                    new_headers.append(
                        (b"content-length", str(len(full_body)).encode())
                    )
                    await send({**start_msg, "headers": new_headers})
                    await send({
                        "type": "http.response.body",
                        "body": full_body,
                        "more_body": False,
                    })
                return

            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(UmamiOwnerFilterMiddleware)

# GZip APRÈS UmamiOwnerFilter — le filtre doit voir le HTML non compressé
app.add_middleware(GZipMiddleware, minimum_size=500)


# =========================
# Block sensitive static paths
# =========================

@app.get("/ui/templates/{rest:path}", include_in_schema=False)
async def block_templates_access(rest: str):
    """Block direct access to Jinja2 template sources."""
    return HTMLResponse(status_code=404, content="Not Found")


# =========================
# Static UI
# =========================

# Sert les fichiers CSS / JS / IMAGES
app.mount("/ui/static", StaticFiles(directory="ui/static"), name="ui-static")

# Compatibilité Claude / Laragon : chemins /static/...
app.mount("/static", StaticFiles(directory="ui/static"), name="static")

# Sert les pages HTML
app.mount("/ui", StaticFiles(directory="ui"), name="ui")


# =========================
# Routes (incluses via APIRouter)
# =========================

app.include_router(pages_router)
app.include_router(data_router)
app.include_router(analyse_router)
app.include_router(gemini_router)
app.include_router(pdf_router)
app.include_router(tracking_router)
app.include_router(chat_router)
app.include_router(em_data_router)
app.include_router(em_analyse_router)
app.include_router(em_pages_router)
app.include_router(em_chat_router)
app.include_router(ratings_router)
# Phase 10 — Unified routes /api/{game}/...
app.include_router(unified_data_router)
app.include_router(unified_analyse_router)
app.include_router(unified_chat_router)
# Phase 11 — English EuroMillions pages
app.include_router(en_em_pages_router)
# P5/5 — Multilingual EM pages (PT/ES/DE/NL) + dynamic sitemap
app.include_router(multilang_em_router)
app.include_router(sitemap_router)


# =========================
# Version API (centralisation frontend)
# =========================

@app.get("/api/version")
async def api_version():
    """Retourne la version centralisee pour injection frontend."""
    return {
        "version": APP_VERSION,
        "name": APP_NAME,
        "date": VERSION_DATE,
    }


# =========================
# Health (ameliore R-28)
# =========================

@app.get("/health")
async def health():
    """Endpoint healthcheck Cloud Run — BDD + Gemini + uptime."""
    db_status = "ok"
    try:
        async with db_cloudsql.get_connection() as conn:
            cur = await conn.cursor()
            await cur.execute("SELECT 1")
    except Exception:
        db_status = "unreachable"

    gemini_state = gemini_breaker.state
    gemini_status = "ok" if gemini_state == "closed" else "circuit_open"

    overall = "ok"
    if db_status != "ok":
        overall = "degraded"

    return {
        "status": overall,
        "engine": "HYBRIDE_OPTIMAL_V1",
        "version": __version__,
        "database": db_status,
        "gemini": gemini_status,
        "uptime_seconds": round(time.monotonic() - _STARTED_AT),
    }


# =========================
# SEO Redirections 301
# =========================

@app.get("/analyse", include_in_schema=False)
async def redirect_analyse():
    return RedirectResponse(url="/loto/analyse", status_code=301)


# Doublons de contenu → 301 vers la version canonique /loto/*
@app.get("/statistiques", include_in_schema=False)
async def redirect_statistiques():
    return RedirectResponse(url="/loto/statistiques", status_code=301)


@app.get("/simulateur", include_in_schema=False)
async def redirect_simulateur():
    return RedirectResponse(url="/loto/analyse", status_code=301)


@app.get("/exploration", include_in_schema=False)
async def redirect_exploration():
    return RedirectResponse(url="/loto", status_code=301)


# Anciennes URLs /ui/*.html → routes propres
@app.get("/ui/launcher.html", include_in_schema=False)
async def redirect_ui_launcher():
    return RedirectResponse(url="/accueil", status_code=301)


@app.get("/ui/loto.html", include_in_schema=False)
async def redirect_ui_loto():
    return RedirectResponse(url="/loto", status_code=301)


@app.get("/ui/simulateur.html", include_in_schema=False)
async def redirect_ui_simulateur():
    return RedirectResponse(url="/loto/analyse", status_code=301)


@app.get("/ui/statistiques.html", include_in_schema=False)
async def redirect_ui_statistiques():
    return RedirectResponse(url="/loto/statistiques", status_code=301)


# Anciennes URLs internes → redirections 301 (SEO: éviter les 404)
@app.get("/loto/accueil", include_in_schema=False)
async def redirect_loto_accueil():
    return RedirectResponse(url="/accueil", status_code=301)


@app.get("/loto/historique", include_in_schema=False)
async def redirect_loto_historique():
    return RedirectResponse(url="/historique", status_code=301)


@app.get("/loto/chatbot", include_in_schema=False)
async def redirect_loto_chatbot():
    return RedirectResponse(url="/loto", status_code=301)


@app.get("/loto/pronostics", include_in_schema=False)
async def redirect_loto_pronostics():
    return RedirectResponse(url="/loto", status_code=301)


@app.get("/euromillions/accueil", include_in_schema=False)
async def redirect_em_accueil():
    return RedirectResponse(url="/euromillions", status_code=301)


@app.get("/euromillions/chatbot", include_in_schema=False)
async def redirect_em_chatbot():
    return RedirectResponse(url="/euromillions", status_code=301)
