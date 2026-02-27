"""
Middleware i18n — Détecte la langue de chaque requête.
Injecte request.state.lang accessible dans les routes et templates.
Synchronise le ContextVar ctx_lang pour les couches profondes (engine, services).
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from config.i18n import SUPPORTED_LANGS, DEFAULT_LANG, ctx_lang


class I18nMiddleware(BaseHTTPMiddleware):
    """Détecte la langue et l'injecte dans request.state.lang + ctx_lang."""

    async def dispatch(self, request: Request, call_next):
        lang = self._detect_lang(request)
        request.state.lang = lang
        token = ctx_lang.set(lang)
        try:
            response = await call_next(request)
        finally:
            ctx_lang.reset(token)
        return response

    def _detect_lang(self, request: Request) -> str:
        path = request.url.path

        # GARDE-FOU : Loto = toujours FR, court-circuit immédiat
        if path.startswith("/loto") or path.startswith("/api/loto"):
            return DEFAULT_LANG

        # 1. Query param ?lang=xx
        lang = request.query_params.get("lang")
        if lang and lang in SUPPORTED_LANGS:
            return lang

        # 2. Cookie lotoia_lang
        lang = request.cookies.get("lotoia_lang")
        if lang and lang in SUPPORTED_LANGS:
            return lang

        # 3. URL path /en/euromillions/...
        parts = path.strip("/").split("/")
        if len(parts) >= 1 and parts[0] in SUPPORTED_LANGS and parts[0] != "fr":
            return parts[0]

        # 4. Accept-Language header
        accept = request.headers.get("accept-language", "")
        for part in accept.split(","):
            code = part.split(";")[0].strip().lower()[:2]
            if code in SUPPORTED_LANGS:
                return code

        # 5. Default
        return DEFAULT_LANG
