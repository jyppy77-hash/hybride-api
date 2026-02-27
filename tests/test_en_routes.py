"""
Tests Phase 11 — English EuroMillions routes + chatbot lang support.
Verifies:
  - /en/euromillions/* HTML page routes return 200
  - hreflang tags present on both FR and EN pages
  - lang-switch links present on both FR and EN pages
  - EMChatRequest accepts lang="en"
  - English response pools are importable and non-empty
  - config/languages.py ValidLang + helpers
"""

import os
from contextlib import asynccontextmanager
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ── Patches (same pattern as test_routes.py) ─────────────────────────

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
})


def _async_cm_conn(cursor):
    @asynccontextmanager
    async def _cm():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn
    return _cm


def _get_client():
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False), main_mod


# ═══════════════════════════════════════════════
# config/languages.py
# ═══════════════════════════════════════════════

def test_valid_lang_enum():
    """ValidLang has fr and en members."""
    from config.languages import ValidLang
    assert ValidLang.fr.value == "fr"
    assert ValidLang.en.value == "en"


def test_get_prompt_key():
    """get_prompt_key returns correct keys for each lang."""
    from config.languages import ValidLang, get_prompt_key
    assert get_prompt_key(ValidLang.fr, "chatbot") == "CHATBOT_EM"
    assert get_prompt_key(ValidLang.en, "chatbot") == "CHATBOT_EM_EN"
    assert get_prompt_key(ValidLang.en, "pitch") == "PITCH_GRILLE_EM_EN"
    assert get_prompt_key(ValidLang.en, "sql") == "SQL_GENERATOR_EM_EN"


def test_page_slugs():
    """PAGE_SLUGS maps lang to correct slug sets."""
    from config.languages import ValidLang, PAGE_SLUGS
    fr_slugs = PAGE_SLUGS[ValidLang.fr]
    en_slugs = PAGE_SLUGS[ValidLang.en]
    assert "accueil-em" in fr_slugs.values()
    assert "home-em-en" in en_slugs.values()


# ═══════════════════════════════════════════════
# English prompt loading
# ═══════════════════════════════════════════════

def test_english_prompts_loadable():
    """All 3 English prompts load without error."""
    from services.prompt_loader import load_prompt
    for key in ("CHATBOT_EM_EN", "PITCH_GRILLE_EM_EN", "SQL_GENERATOR_EM_EN"):
        prompt = load_prompt(key)
        assert prompt is not None, f"Prompt {key} failed to load"
        assert len(prompt) > 100, f"Prompt {key} too short"


# ═══════════════════════════════════════════════
# English response pools
# ═══════════════════════════════════════════════

def test_english_response_pools_non_empty():
    """All EN response pools are non-empty lists."""
    from services.chat_responses_em_en import (
        _INSULT_L1_EM_EN, _INSULT_L2_EM_EN, _INSULT_L3_EM_EN, _INSULT_L4_EM_EN,
        _INSULT_SHORT_EM_EN, _MENACE_RESPONSES_EM_EN,
        _COMPLIMENT_L1_EM_EN, _COMPLIMENT_L2_EM_EN, _COMPLIMENT_L3_EM_EN,
        _COMPLIMENT_LOVE_EM_EN, _COMPLIMENT_MERCI_EM_EN,
        _OOR_L1_EM_EN, _OOR_L2_EM_EN, _OOR_L3_EM_EN,
        _OOR_CLOSE_EM_EN, _OOR_ZERO_NEG_EM_EN, _OOR_ETOILE_EM_EN,
        FALLBACK_RESPONSE_EM_EN,
    )
    pools = [
        _INSULT_L1_EM_EN, _INSULT_L2_EM_EN, _INSULT_L3_EM_EN, _INSULT_L4_EM_EN,
        _INSULT_SHORT_EM_EN, _MENACE_RESPONSES_EM_EN,
        _COMPLIMENT_L1_EM_EN, _COMPLIMENT_L2_EM_EN, _COMPLIMENT_L3_EM_EN,
        _COMPLIMENT_LOVE_EM_EN, _COMPLIMENT_MERCI_EM_EN,
        _OOR_L1_EM_EN, _OOR_L2_EM_EN, _OOR_L3_EM_EN,
        _OOR_CLOSE_EM_EN, _OOR_ZERO_NEG_EM_EN, _OOR_ETOILE_EM_EN,
    ]
    for pool in pools:
        assert isinstance(pool, list), f"Pool is not a list: {type(pool)}"
        assert len(pool) >= 2, f"Pool too small: {pool}"
    assert isinstance(FALLBACK_RESPONSE_EM_EN, str)
    assert len(FALLBACK_RESPONSE_EM_EN) > 10


def test_english_response_functions():
    """EN response functions return strings."""
    from services.chat_responses_em_en import (
        _get_insult_response_em_en,
        _get_insult_short_em_en,
        _get_menace_response_em_en,
        _get_compliment_response_em_en,
        _get_oor_response_em_en,
    )
    assert isinstance(_get_insult_response_em_en(1, []), str)
    assert isinstance(_get_insult_short_em_en(), str)
    assert isinstance(_get_menace_response_em_en(), str)
    assert isinstance(_get_compliment_response_em_en("merci", 1, []), str)
    assert isinstance(_get_oor_response_em_en(55, "high", 1), str)


# ═══════════════════════════════════════════════
# EMChatRequest schema — lang field
# ═══════════════════════════════════════════════

def test_em_chat_request_lang_default():
    """EMChatRequest defaults lang to 'fr'."""
    from em_schemas import EMChatRequest
    req = EMChatRequest(message="hello")
    assert req.lang == "fr"


def test_em_chat_request_lang_en():
    """EMChatRequest accepts lang='en'."""
    from em_schemas import EMChatRequest
    req = EMChatRequest(message="hello", lang="en")
    assert req.lang == "en"


def test_em_chat_request_lang_invalid():
    """EMChatRequest rejects invalid lang values."""
    from em_schemas import EMChatRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        EMChatRequest(message="hello", lang="de")


# ═══════════════════════════════════════════════
# EN page routes — /en/euromillions/*
# ═══════════════════════════════════════════════

_EN_PAGES = [
    "/en/euromillions",
    "/en/euromillions/generator",
    "/en/euromillions/simulator",
    "/en/euromillions/statistics",
    "/en/euromillions/history",
    "/en/euromillions/news",
]


@patch("routes.en_em_pages.db_cloudsql")
def test_en_em_pages_200(mock_db):
    """All EN EuroMillions page routes return 200."""
    mock_db.get_em_tirages_count = AsyncMock(return_value=1500)
    client, main_mod = _get_client()
    main_mod.db_cloudsql = mock_db

    # Patch the module-level db_cloudsql in en_em_pages too
    import routes.en_em_pages as en_mod
    en_mod.db_cloudsql = mock_db

    for path in _EN_PAGES:
        resp = client.get(path)
        assert resp.status_code == 200, f"GET {path} returned {resp.status_code}"

    # FAQ needs special handling (reads file + replaces __EM_DB_TOTAL__)
    resp = client.get("/en/euromillions/faq")
    assert resp.status_code == 200


@patch("routes.en_em_pages.db_cloudsql")
def test_en_em_faq_injects_total(mock_db):
    """EN FAQ page replaces __EM_DB_TOTAL__ with actual count."""
    mock_db.get_em_tirages_count = AsyncMock(return_value=1842)
    client, main_mod = _get_client()
    import routes.en_em_pages as en_mod
    en_mod.db_cloudsql = mock_db

    resp = client.get("/en/euromillions/faq")
    assert resp.status_code == 200
    assert "1842" in resp.text or "__EM_DB_TOTAL__" not in resp.text


# ═══════════════════════════════════════════════
# EN pages — hreflang tags present
# ═══════════════════════════════════════════════

@patch("routes.en_em_pages.db_cloudsql")
def test_en_pages_have_hreflang(mock_db):
    """EN pages include hreflang tags for fr, en, x-default."""
    mock_db.get_em_tirages_count = AsyncMock(return_value=1500)
    client, main_mod = _get_client()
    import routes.en_em_pages as en_mod
    en_mod.db_cloudsql = mock_db

    for path in _EN_PAGES:
        resp = client.get(path)
        html = resp.text
        assert 'hreflang="fr"' in html, f"Missing FR hreflang on {path}"
        assert 'hreflang="en"' in html, f"Missing EN hreflang on {path}"
        assert 'hreflang="x-default"' in html, f"Missing x-default hreflang on {path}"


# ═══════════════════════════════════════════════
# EN pages — lang-switch link present
# ═══════════════════════════════════════════════

@patch("routes.en_em_pages.db_cloudsql")
def test_en_pages_have_lang_switch(mock_db):
    """EN pages include a lang-switch link to FR version."""
    mock_db.get_em_tirages_count = AsyncMock(return_value=1500)
    client, main_mod = _get_client()
    import routes.en_em_pages as en_mod
    en_mod.db_cloudsql = mock_db

    for path in _EN_PAGES:
        resp = client.get(path)
        assert "lang-switch" in resp.text, f"Missing lang-switch on {path}"


# ═══════════════════════════════════════════════
# EN pages — chatbot widget uses EN JS
# ═══════════════════════════════════════════════

@patch("routes.en_em_pages.db_cloudsql")
def test_en_pages_use_en_chatbot_js(mock_db):
    """EN pages load hybride-chatbot-em-en.js (not the FR version)."""
    mock_db.get_em_tirages_count = AsyncMock(return_value=1500)
    client, main_mod = _get_client()
    import routes.en_em_pages as en_mod
    en_mod.db_cloudsql = mock_db

    for path in _EN_PAGES:
        resp = client.get(path)
        assert "hybride-chatbot-em-en.js" in resp.text, f"Missing EN chatbot JS on {path}"


# ═══════════════════════════════════════════════
# Cache middleware — EN routes in seo_routes
# ═══════════════════════════════════════════════

def test_seo_routes_include_en():
    """Verify EN routes are listed in main.py seo_routes for cache headers."""
    import main as main_mod
    # Read the source to check seo_routes list
    import inspect
    source = inspect.getsource(main_mod)
    assert "/en/euromillions" in source
    assert "/en/euromillions/generator" in source
    assert "/en/euromillions/statistics" in source


# ═══════════════════════════════════════════════
# HTML redirect middleware — /ui/en/euromillions/*.html → clean URLs
# ═══════════════════════════════════════════════

def test_en_html_redirects():
    """Verify /ui/en/euromillions/*.html redirects to clean URLs."""
    client, _ = _get_client()

    redirects = {
        "/ui/en/euromillions/home.html": "/en/euromillions",
        "/ui/en/euromillions/generator.html": "/en/euromillions/generator",
        "/ui/en/euromillions/simulator.html": "/en/euromillions/simulator",
        "/ui/en/euromillions/statistics.html": "/en/euromillions/statistics",
        "/ui/en/euromillions/history.html": "/en/euromillions/history",
        "/ui/en/euromillions/faq.html": "/en/euromillions/faq",
        "/ui/en/euromillions/news.html": "/en/euromillions/news",
    }
    for html_path, expected_url in redirects.items():
        resp = client.get(html_path, follow_redirects=False)
        assert resp.status_code == 301, f"GET {html_path} expected 301, got {resp.status_code}"
        location = resp.headers.get("location", "")
        assert location == expected_url, f"GET {html_path} redirected to {location}, expected {expected_url}"


# ═══════════════════════════════════════════════
# Trailing slash → 301 redirect (strip_trailing_slash middleware)
# ═══════════════════════════════════════════════

def test_trailing_slash_redirects_en():
    """Verify /en/euromillions/foo/ → 301 to /en/euromillions/foo."""
    client, _ = _get_client()

    trailing = {
        "/en/euromillions/": "/en/euromillions",
        "/en/euromillions/generator/": "/en/euromillions/generator",
        "/en/euromillions/statistics/": "/en/euromillions/statistics",
    }
    for path_slash, expected in trailing.items():
        resp = client.get(path_slash, follow_redirects=False)
        assert resp.status_code == 301, f"GET {path_slash} expected 301, got {resp.status_code}"
        location = resp.headers.get("location", "")
        assert location == expected, f"GET {path_slash} → {location}, expected {expected}"


def test_trailing_slash_redirects_fr():
    """Verify /euromillions/foo/ → 301 to /euromillions/foo (existing FR routes too)."""
    client, _ = _get_client()

    trailing = {
        "/euromillions/": "/euromillions",
        "/euromillions/generateur/": "/euromillions/generateur",
    }
    for path_slash, expected in trailing.items():
        resp = client.get(path_slash, follow_redirects=False)
        assert resp.status_code == 301, f"GET {path_slash} expected 301, got {resp.status_code}"
        location = resp.headers.get("location", "")
        assert location == expected, f"GET {path_slash} → {location}, expected {expected}"


# ═══════════════════════════════════════════════
# EN META prompts — load_prompt_em with EN keys
# ═══════════════════════════════════════════════

_EN_TIRAGES_KEYS = [
    "EM_100_EN", "EM_200_EN", "EM_300_EN", "EM_400_EN",
    "EM_500_EN", "EM_600_EN", "EM_700_EN", "EM_GLOBAL_EN",
]

_EN_ANNEES_KEYS = [
    "EM_1A_EN", "EM_2A_EN", "EM_3A_EN", "EM_4A_EN",
    "EM_5A_EN", "EM_6A_EN", "EM_GLOBAL_A_EN",
]


def test_en_meta_prompts_tirages_loadable():
    """All 8 EN tirages prompts load and contain English markers."""
    from services.prompt_loader import load_prompt_em
    for key in _EN_TIRAGES_KEYS:
        prompt = load_prompt_em(key)
        assert prompt, f"Prompt {key} is empty"
        assert "ALWAYS reply in correct, fluent English" in prompt, f"Prompt {key} missing English marker"


def test_en_meta_prompts_annees_loadable():
    """All 7 EN annees prompts load and contain English markers."""
    from services.prompt_loader import load_prompt_em
    for key in _EN_ANNEES_KEYS:
        prompt = load_prompt_em(key)
        assert prompt, f"Prompt {key} is empty"
        assert "ALWAYS reply in correct, fluent English" in prompt, f"Prompt {key} missing English marker"


def test_en_meta_prompt_not_french():
    """EN prompts do not contain the FR language rule."""
    from services.prompt_loader import load_prompt_em
    for key in _EN_TIRAGES_KEYS + _EN_ANNEES_KEYS:
        prompt = load_prompt_em(key)
        assert "français" not in prompt.lower(), f"Prompt {key} contains French text"


# ═══════════════════════════════════════════════
# Badges i18n — _badges function
# ═══════════════════════════════════════════════

def test_badges_fr_returns_french():
    """_badges('fr') returns French labels."""
    from config.i18n import _badges
    b = _badges("fr")
    assert b["hot"] == "Numéros chauds"
    assert b["balanced"] == "Équilibre"
    assert b["even_odd"] == "Pair/Impair OK"


def test_badges_en_returns_english():
    """_badges('en') returns English labels."""
    from config.i18n import _badges
    b = _badges("en")
    assert b["hot"] == "Hot Numbers"
    assert b["balanced"] == "Balanced"
    assert b["even_odd"] == "Even/Odd OK"
    assert b["wide_spectrum"] == "Wide Spectrum"


def test_badges_default_is_french():
    """_badges() with no arg defaults to French."""
    from config.i18n import _badges
    b = _badges()
    assert b["hot"] == "Numéros chauds"


# ═══════════════════════════════════════════════
# EN schemas — lang field on META payloads
# ═══════════════════════════════════════════════

def test_em_meta_analyse_texte_lang_default():
    """EMMetaAnalyseTextePayload defaults lang to 'fr'."""
    from em_schemas import EMMetaAnalyseTextePayload
    p = EMMetaAnalyseTextePayload(analysis_local="test text")
    assert p.lang == "fr"


def test_em_meta_analyse_texte_lang_en():
    """EMMetaAnalyseTextePayload accepts lang='en'."""
    from em_schemas import EMMetaAnalyseTextePayload
    p = EMMetaAnalyseTextePayload(analysis_local="test text", lang="en")
    assert p.lang == "en"


def test_em_pitch_grilles_lang_field():
    """EMPitchGrillesRequest accepts lang='en'."""
    from em_schemas import EMPitchGrillesRequest, EMPitchGrilleItem
    grille = EMPitchGrilleItem(numeros=[1, 2, 3, 4, 5], etoiles=[1, 2], score_conformite=80)
    p = EMPitchGrillesRequest(grilles=[grille], lang="en")
    assert p.lang == "en"


def test_em_meta_pdf_lang_field():
    """EMMetaPdfPayload accepts lang='en'."""
    from em_schemas import EMMetaPdfPayload
    p = EMMetaPdfPayload(lang="en")
    assert p.lang == "en"


def test_em_meta_pdf_lang_default():
    """EMMetaPdfPayload defaults lang to 'fr'."""
    from em_schemas import EMMetaPdfPayload
    p = EMMetaPdfPayload()
    assert p.lang == "fr"
