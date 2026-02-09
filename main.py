import time
import uuid
import contextvars
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
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
from engine.version import __version__
from services.circuit_breaker import gemini_breaker
from routes.pages import router as pages_router
from routes.api_data import router as data_router
from routes.api_analyse import router as analyse_router
from routes.api_gemini import router as gemini_router
from routes.api_pdf import router as pdf_router
from routes.api_tracking import router as tracking_router
from routes.api_chat import router as chat_router

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


@asynccontextmanager
async def lifespan(app):
    """Startup/shutdown : client HTTP partage."""
    app.state.httpx_client = httpx.AsyncClient(timeout=20.0)
    yield
    await app.state.httpx_client.aclose()


app = FastAPI(
    title="HYBRIDE API",
    description="Moteur HYBRIDE_OPTIMAL_V1 — API officielle",
    version=__version__,
    redirect_slashes=False,
    lifespan=lifespan
)

# Rate limiter (slowapi)
app.state.limiter = limiter


def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "Trop de requetes. Reessayez dans quelques instants."}
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# Compression GZip pour performance
app.add_middleware(GZipMiddleware, minimum_size=500)

# Rate limiting middleware
app.add_middleware(SlowAPIMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lotoia.fr",
        "https://www.lotoia.fr",
        "http://localhost:8080",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# =========================
# Correlation ID middleware
# =========================

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Genere un UUID par requete, l'injecte dans les logs et le header de reponse."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
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
    "img-src 'self' data: https://*.google-analytics.com; "
    "font-src 'self'; "
    "connect-src 'self' https://www.googletagmanager.com https://*.google-analytics.com https://analytics.google.com https://cloud.umami.is https://api-gateway.umami.dev; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Injecte les headers de securite sur toutes les reponses."""
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
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
    seo_routes = ["/", "/accueil", "/loto", "/loto/analyse", "/loto/exploration",
                  "/loto/statistiques", "/statistiques", "/simulateur", "/faq", "/news",
                  "/historique", "/methodologie", "/moteur", "/disclaimer",
                  "/mentions-legales", "/politique-confidentialite", "/politique-cookies"]
    if path.endswith(".html") or path in seo_routes:
        response.headers["Cache-Control"] = "public, max-age=3600"  # 1 heure

    return response


# =========================
# SEO: 301 redirect /ui/*.html → clean URL
# =========================

_UI_HTML_TO_CLEAN_URL = {
    "launcher.html": "/",
    "accueil.html": "/accueil",
    "loto.html": "/loto",
    "simulateur.html": "/simulateur",
    "statistiques.html": "/statistiques",
    "faq.html": "/faq",
    "news.html": "/news",
    "historique.html": "/historique",
    "methodologie.html": "/methodologie",
    "moteur.html": "/moteur",
    "disclaimer.html": "/disclaimer",
    "mentions-legales.html": "/mentions-legales",
    "politique-confidentialite.html": "/politique-confidentialite",
    "politique-cookies.html": "/politique-cookies",
}


@app.middleware("http")
async def redirect_ui_html_to_seo(request: Request, call_next):
    """301 redirect /ui/<page>.html → clean URL (SEO dedup)."""
    path = request.url.path
    if path.startswith("/ui/") and path.endswith(".html"):
        filename = path[len("/ui/"):]
        clean_url = _UI_HTML_TO_CLEAN_URL.get(filename)
        if clean_url:
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(url=f"{clean_url}{query}", status_code=301)
    return await call_next(request)



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


# =========================
# Health (ameliore R-28)
# =========================

@app.get("/health")
def health():
    """Endpoint healthcheck Cloud Run — BDD + Gemini + uptime."""
    db_status = "ok"
    try:
        conn = db_cloudsql.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
        finally:
            conn.close()
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
    return RedirectResponse(url="/simulateur", status_code=301)


@app.get("/exploration", include_in_schema=False)
async def redirect_exploration():
    return RedirectResponse(url="/loto", status_code=301)
