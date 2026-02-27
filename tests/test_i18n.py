"""
Tests P1 i18n — gettext infrastructure, middleware, ContextVar.
19 tests covering:
  - Translation loading (FR, EN, fallback)
  - gettext_func / ngettext_func
  - ContextVar (_global)
  - I18nMiddleware (query, cookie, URL, Accept-Language, default, priority)
  - Loto isolation
  - Named placeholders
  - SUPPORTED_LANGS ↔ ValidLang sync
  - LRU cache
  - get_translator helper
"""

import os
from contextlib import asynccontextmanager
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient


# ── Patches (same pattern as test_routes.py) ─────────────────────────

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
})


def _get_client():
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False), main_mod


# ═══════════════════════════════════════════════
# 1-3: Translation loading
# ═══════════════════════════════════════════════

def test_get_translations_fr():
    """FR translations load — known string returns msgid (source lang)."""
    from config.i18n import get_translations
    trans = get_translations("fr")
    # FR .po has empty msgstr → gettext returns msgid
    result = trans.gettext("Numéros chauds")
    assert result == "Numéros chauds"


def test_get_translations_en():
    """EN translations load — known string returns English translation."""
    from config.i18n import get_translations
    trans = get_translations("en")
    result = trans.gettext("Numéros chauds")
    assert result == "Hot Numbers"


def test_get_translations_fallback():
    """Unknown language falls back to FR."""
    from config.i18n import get_translations
    trans = get_translations("xx")
    result = trans.gettext("Numéros chauds")
    assert result == "Numéros chauds"


# ═══════════════════════════════════════════════
# 4-5: gettext_func / ngettext_func
# ═══════════════════════════════════════════════

def test_gettext_func_returns_callable():
    """gettext_func() returns a callable that translates."""
    from config.i18n import gettext_func
    _ = gettext_func("en")
    assert callable(_)
    assert _("Équilibre") == "Balanced"


def test_ngettext_func_plurals():
    """ngettext_func handles EN plurals correctly."""
    from config.i18n import ngettext_func
    ng = ngettext_func("en")
    assert ng("1 tirage", "{count} tirages", 1) == "1 draw"
    assert ng("1 tirage", "{count} tirages", 2) == "{count} draws"


# ═══════════════════════════════════════════════
# 6-11: Middleware tests
# ═══════════════════════════════════════════════

def test_middleware_query_param():
    """?lang=en → request.state.lang == 'en'."""
    from middleware.i18n_middleware import I18nMiddleware
    mw = I18nMiddleware(app=None)
    request = MagicMock()
    request.query_params = {"lang": "en"}
    request.cookies = {}
    request.url.path = "/api/euromillions/generate"
    request.headers = {}
    assert mw._detect_lang(request) == "en"


def test_middleware_cookie():
    """Cookie lotoia_lang=en → 'en'."""
    from middleware.i18n_middleware import I18nMiddleware
    mw = I18nMiddleware(app=None)
    request = MagicMock()
    request.query_params = {}
    request.cookies = {"lotoia_lang": "en"}
    request.url.path = "/euromillions"
    request.headers = {}
    assert mw._detect_lang(request) == "en"


def test_middleware_url_path():
    """Path /en/euromillions/ → 'en'."""
    from middleware.i18n_middleware import I18nMiddleware
    mw = I18nMiddleware(app=None)
    request = MagicMock()
    request.query_params = {}
    request.cookies = {}
    request.url.path = "/en/euromillions/generator"
    request.headers = {}
    assert mw._detect_lang(request) == "en"


def test_middleware_accept_language():
    """Accept-Language: pt → 'pt'."""
    from middleware.i18n_middleware import I18nMiddleware
    mw = I18nMiddleware(app=None)
    request = MagicMock()
    request.query_params = {}
    request.cookies = {}
    request.url.path = "/euromillions"
    request.headers = {"accept-language": "pt-BR,pt;q=0.9,en;q=0.8"}
    assert mw._detect_lang(request) == "pt"


def test_middleware_default():
    """No language hint → 'fr'."""
    from middleware.i18n_middleware import I18nMiddleware
    mw = I18nMiddleware(app=None)
    request = MagicMock()
    request.query_params = {}
    request.cookies = {}
    request.url.path = "/euromillions"
    request.headers = {}
    assert mw._detect_lang(request) == "fr"


def test_middleware_priority():
    """Query param beats cookie beats URL beats header."""
    from middleware.i18n_middleware import I18nMiddleware
    mw = I18nMiddleware(app=None)
    request = MagicMock()
    # All signals present but conflicting
    request.query_params = {"lang": "de"}
    request.cookies = {"lotoia_lang": "es"}
    request.url.path = "/en/euromillions"
    request.headers = {"accept-language": "pt"}
    assert mw._detect_lang(request) == "de"

    # Remove query param — cookie wins
    request.query_params = {}
    assert mw._detect_lang(request) == "es"

    # Remove cookie — URL path wins
    request.cookies = {}
    assert mw._detect_lang(request) == "en"

    # Remove URL path — header wins
    request.url.path = "/euromillions"
    assert mw._detect_lang(request) == "pt"


# ═══════════════════════════════════════════════
# 12: SUPPORTED_LANGS matches ValidLang
# ═══════════════════════════════════════════════

def test_supported_langs_match_valid_lang():
    """SUPPORTED_LANGS values match ValidLang enum members."""
    from config.i18n import SUPPORTED_LANGS
    from config.languages import ValidLang
    valid_values = [v.value for v in ValidLang]
    assert sorted(SUPPORTED_LANGS) == sorted(valid_values)


# ═══════════════════════════════════════════════
# 13: LRU cache
# ═══════════════════════════════════════════════

def test_lru_cache_translations():
    """Same object returned for two calls with same lang."""
    from config.i18n import get_translations
    # Clear cache to start fresh
    get_translations.cache_clear()
    t1 = get_translations("en")
    t2 = get_translations("en")
    assert t1 is t2
    get_translations.cache_clear()


# ═══════════════════════════════════════════════
# 14: get_translator helper
# ═══════════════════════════════════════════════

def test_get_translator_helper():
    """get_translator(request) returns a working _ callable."""
    from config.i18n import get_translator
    request = MagicMock()
    request.state.lang = "en"
    _ = get_translator(request)
    assert callable(_)
    assert _("Fréquence") == "Frequency"


# ═══════════════════════════════════════════════
# 15-16: ContextVar
# ═══════════════════════════════════════════════

def test_contextvar_default():
    """ctx_lang defaults to 'fr'."""
    from config.i18n import ctx_lang
    assert ctx_lang.get() == "fr"


def test_contextvar_set_get():
    """ctx_lang.set('en') then _global() returns EN translation."""
    from config.i18n import ctx_lang, _global
    token = ctx_lang.set("en")
    try:
        result = _global("Numéros chauds")
        assert result == "Hot Numbers"
    finally:
        ctx_lang.reset(token)


# ═══════════════════════════════════════════════
# 17-18: Loto isolation
# ═══════════════════════════════════════════════

def test_loto_isolation_ignores_cookie():
    """Path /loto + cookie lang=en → returns 'fr'."""
    from middleware.i18n_middleware import I18nMiddleware
    mw = I18nMiddleware(app=None)
    request = MagicMock()
    request.query_params = {}
    request.cookies = {"lotoia_lang": "en"}
    request.url.path = "/loto"
    request.headers = {"accept-language": "en"}
    assert mw._detect_lang(request) == "fr"


def test_loto_isolation_ignores_query():
    """Path /api/loto/generate?lang=en → returns 'fr'."""
    from middleware.i18n_middleware import I18nMiddleware
    mw = I18nMiddleware(app=None)
    request = MagicMock()
    request.query_params = {"lang": "en"}
    request.cookies = {}
    request.url.path = "/api/loto/generate"
    request.headers = {}
    assert mw._detect_lang(request) == "fr"


# ═══════════════════════════════════════════════
# 19: Named placeholders
# ═══════════════════════════════════════════════

def test_named_placeholders_format():
    """Translated string with {name} placeholders resolves with .format()."""
    from config.i18n import gettext_func
    _ = gettext_func("en")
    result = _("{count} tirages analysés").format(count=5)
    assert result == "5 draws analysed"

    _ = gettext_func("fr")
    result = _("{count} tirages analysés").format(count=5)
    assert result == "5 tirages analysés"
