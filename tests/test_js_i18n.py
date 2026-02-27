"""
Tests P3 — JS i18n labels (config/js_i18n.py).
Covers:
  - Label dict structure (both langs have same keys)
  - get_js_labels returns correct lang
  - Fallback to FR on unknown lang
  - Placeholder patterns ({n}, {s}) consistent across langs
  - Injection in rendered HTML (window.LotoIA_i18n, window.LotoIA_lang)
  - Unified JS paths in render_template defaults
  - EN routes no longer reference EN-specific JS files
"""

import json
import os
from unittest.mock import patch, MagicMock

import pytest


# ── Patches ─────────────────────────────────────────────────────────
_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
})


def _make_request():
    r = MagicMock()
    r.url.path = "/euromillions"
    r.query_params = {}
    r.cookies = {}
    r.headers = {}
    return r


# ═══════════════════════════════════════════════
# 1-3: Label dict structure
# ═══════════════════════════════════════════════

def test_labels_has_fr_and_en():
    """_LABELS dict has 'fr' and 'en' keys."""
    from config.js_i18n import _LABELS
    assert "fr" in _LABELS
    assert "en" in _LABELS


def test_labels_same_keys():
    """FR and EN have exactly the same set of keys."""
    from config.js_i18n import _LABELS
    fr_keys = set(_LABELS["fr"].keys())
    en_keys = set(_LABELS["en"].keys())
    missing_in_en = fr_keys - en_keys
    missing_in_fr = en_keys - fr_keys
    assert not missing_in_en, f"Missing in EN: {missing_in_en}"
    assert not missing_in_fr, f"Missing in FR: {missing_in_fr}"


def test_labels_all_strings():
    """All label values are non-empty strings."""
    from config.js_i18n import _LABELS
    for lang in ("fr", "en"):
        for key, val in _LABELS[lang].items():
            assert isinstance(val, str), f"{lang}.{key} is {type(val)}"
            assert len(val) > 0, f"{lang}.{key} is empty"


# ═══════════════════════════════════════════════
# 4-5: get_js_labels
# ═══════════════════════════════════════════════

def test_get_js_labels_fr():
    """get_js_labels('fr') returns FR labels."""
    from config.js_i18n import get_js_labels
    labels = get_js_labels("fr")
    assert labels["locale"] == "fr-FR"
    assert "Erreur" in labels["api_error"]


def test_get_js_labels_en():
    """get_js_labels('en') returns EN labels."""
    from config.js_i18n import get_js_labels
    labels = get_js_labels("en")
    assert labels["locale"] == "en-GB"
    assert "Error" in labels["api_error"]


def test_get_js_labels_fallback():
    """Unknown lang falls back to FR."""
    from config.js_i18n import get_js_labels
    labels = get_js_labels("de")
    assert labels["locale"] == "fr-FR"


# ═══════════════════════════════════════════════
# 6-7: Placeholder consistency
# ═══════════════════════════════════════════════

def test_placeholder_consistency():
    """Keys with {n} or {s} in FR also have them in EN."""
    from config.js_i18n import _LABELS
    for key in _LABELS["fr"]:
        fr_val = _LABELS["fr"][key]
        en_val = _LABELS["en"][key]
        if "{n}" in fr_val:
            assert "{n}" in en_val, f"{key}: FR has {{n}} but EN does not"
        if "{s}" in fr_val:
            assert "{s}" in en_val, f"{key}: FR has {{s}} but EN does not"


def test_locale_values():
    """Locale keys are valid BCP-47 tags."""
    from config.js_i18n import _LABELS
    assert _LABELS["fr"]["locale"] == "fr-FR"
    assert _LABELS["en"]["locale"] == "en-GB"


# ═══════════════════════════════════════════════
# 8-9: Key count sanity
# ═══════════════════════════════════════════════

def test_minimum_key_count():
    """At least 100 i18n keys per language (audit found ~111)."""
    from config.js_i18n import _LABELS
    assert len(_LABELS["fr"]) >= 100
    assert len(_LABELS["en"]) >= 100


def test_key_naming_convention():
    """All keys are lowercase with underscores (snake_case) or digits."""
    import re
    from config.js_i18n import _LABELS
    pattern = re.compile(r'^[a-z][a-z0-9_]*$')
    for key in _LABELS["fr"]:
        assert pattern.match(key), f"Key '{key}' does not match snake_case"


# ═══════════════════════════════════════════════
# 10-11: Injection in rendered HTML
# ═══════════════════════════════════════════════

def test_js_labels_injected_in_html_fr():
    """FR rendered HTML contains window.LotoIA_i18n with FR labels."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="fr", page_key="historique")
    html = resp.body.decode("utf-8")
    assert "window.LotoIA_i18n=" in html
    assert 'window.LotoIA_lang="fr"' in html
    assert "fr-FR" in html  # locale value present


def test_js_labels_injected_in_html_en():
    """EN rendered HTML contains window.LotoIA_i18n with EN labels."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="en", page_key="historique")
    html = resp.body.decode("utf-8")
    assert "window.LotoIA_i18n=" in html
    assert 'window.LotoIA_lang="en"' in html
    assert "en-GB" in html  # locale value present


def test_js_labels_valid_json():
    """The injected LotoIA_i18n is valid JSON."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template("em/historique.html", request, lang="fr", page_key="historique")
    html = resp.body.decode("utf-8")
    # Extract JSON between window.LotoIA_i18n= and ;window.LotoIA_lang
    start = html.index("window.LotoIA_i18n=") + len("window.LotoIA_i18n=")
    end = html.index(";window.LotoIA_lang")
    json_str = html[start:end]
    labels = json.loads(json_str)
    assert isinstance(labels, dict)
    assert "locale" in labels


# ═══════════════════════════════════════════════
# 12-13: Unified JS paths
# ═══════════════════════════════════════════════

def test_en_html_uses_unified_js():
    """EN pages reference unified FR JS files (not EN-specific)."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template(
        "em/generateur.html", request, lang="en", page_key="generateur",
        body_class="loto-page em-page", include_nav_scroll=True,
        show_disclaimer_link=True, hero_icon="⭐",
        hero_title="Grid Explorer", hero_subtitle="Stats",
    )
    html = resp.body.decode("utf-8")
    # Should NOT reference EN-specific JS
    assert "/ui/en/euromillions/static/app-em-en.js" not in html
    assert "/ui/en/euromillions/static/sponsor-popup-em-en.js" not in html
    assert "/ui/en/euromillions/static/sponsor-popup75-em-en.js" not in html
    # Should reference unified paths
    assert "app-em.js" in html
    assert "sponsor-popup75-em.js" in html


def test_en_simulator_uses_unified_js():
    """EN simulator page references unified simulateur-em.js."""
    from config.templates import render_template
    request = _make_request()
    resp = render_template(
        "em/simulateur.html", request, lang="en", page_key="simulateur",
        body_class="simulator-page em-page", include_nav_scroll=True,
        hero_icon="⭐", hero_title="Grid Analysis", hero_subtitle="Audit",
    )
    html = resp.body.decode("utf-8")
    assert "/ui/en/euromillions/static/simulateur-em-en.js" not in html
    assert "simulateur-em.js" in html


# ═══════════════════════════════════════════════
# 14-15: Specific translation spot checks
# ═══════════════════════════════════════════════

def test_gambling_urls_match_lang():
    """Gambling help URLs in JS labels match the template context."""
    from config.js_i18n import get_js_labels
    fr = get_js_labels("fr")
    en = get_js_labels("en")
    assert "joueurs-info-service.fr" in fr["gambling_url"]
    assert "begambleaware.org" in en["gambling_url"]


def test_http_error_has_trailing_space():
    """http_error has trailing space for status code concatenation."""
    from config.js_i18n import get_js_labels
    for lang in ("fr", "en"):
        val = get_js_labels(lang)["http_error"]
        assert val.endswith(" "), f"{lang} http_error missing trailing space"


def test_rating_popup_keys_exist():
    """Rating popup keys exist in both languages."""
    from config.js_i18n import get_js_labels
    for lang in ("fr", "en"):
        labels = get_js_labels(lang)
        assert "rating_prompt" in labels
        assert "rating_close" in labels
        assert "rating_thanks" in labels
