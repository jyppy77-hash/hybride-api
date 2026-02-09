from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import logging

from engine.version import __version__
from routes.pages import router as pages_router
from routes.api_data import router as data_router
from routes.api_analyse import router as analyse_router
from routes.api_gemini import router as gemini_router
from routes.api_pdf import router as pdf_router
from routes.api_tracking import router as tracking_router
from routes.api_chat import router as chat_router

# Logging
logger = logging.getLogger(__name__)

app = FastAPI(
    title="HYBRIDE API",
    description="Moteur HYBRIDE_OPTIMAL_V1 — API officielle",
    version=__version__,
    redirect_slashes=False
)

# TrustedHostMiddleware: accepte tous les hosts (filtrage géré par enforce_canonical_host)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

# Compression GZip pour performance
app.add_middleware(GZipMiddleware, minimum_size=500)


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
# Health
# =========================

@app.get("/health")
def health():
    """Endpoint healthcheck Cloud Run"""
    return {
        "status": "ok",
        "engine": "HYBRIDE_OPTIMAL_V1",
        "version": __version__
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
