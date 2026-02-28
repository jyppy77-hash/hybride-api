"""
Tests P4 — Prompt loader EM (services/prompt_loader.py).
Covers:
  - load_prompt_em with FR, EN, fallback chain
  - get_em_prompt variable replacement
  - em_window_to_prompt mapping
  - All EM prompts exist in FR and EN
  - Placeholder consistency (same {variables} across langs)
  - LRU cache behaviour
  - Loto prompts untouched
  - Old Loto loader still works
"""

import os
import re

import pytest


# ═══════════════════════════════════════════════
# 1-3: load_prompt_em basics
# ═══════════════════════════════════════════════

def test_load_prompt_em_fr():
    """load_prompt_em('prompt_hybride_em', 'fr') returns FR content."""
    from services.prompt_loader import load_prompt_em
    text = load_prompt_em("prompt_hybride_em", "fr")
    assert len(text) > 100
    assert "HYBRIDE" in text
    assert "EuroMillions" in text


def test_load_prompt_em_en():
    """load_prompt_em('prompt_hybride_em', 'en') returns EN content (different from FR)."""
    from services.prompt_loader import load_prompt_em
    fr = load_prompt_em("prompt_hybride_em", "fr")
    en = load_prompt_em("prompt_hybride_em", "en")
    assert len(en) > 100
    assert en != fr
    assert "IDENTITY" in en or "You are" in en


def test_load_prompt_em_fallback_to_en():
    """Language 'de' loads prompt from EN (placeholder copy)."""
    from services.prompt_loader import load_prompt_em
    de = load_prompt_em("prompt_hybride_em", "de")
    en = load_prompt_em("prompt_hybride_em", "en")
    assert de == en
    assert len(de) > 100


def test_load_prompt_em_fallback_to_fr():
    """Unknown lang with no EN/FR file returns empty string (graceful)."""
    from services.prompt_loader import load_prompt_em
    result = load_prompt_em("nonexistent_prompt_xyz", "xx")
    assert result == ""


def test_load_prompt_em_not_found():
    """Nonexistent prompt returns empty string."""
    from services.prompt_loader import load_prompt_em
    result = load_prompt_em("this_does_not_exist", "fr")
    assert result == ""


# ═══════════════════════════════════════════════
# 4-5: get_em_prompt with variables
# ═══════════════════════════════════════════════

def test_get_em_prompt_with_variables():
    """get_em_prompt replaces {TODAY} in SQL prompt."""
    from services.prompt_loader import get_em_prompt
    text = get_em_prompt("prompt_sql_generator_em", "fr", TODAY="2026-02-27")
    assert "2026-02-27" in text
    assert "{TODAY}" not in text


def test_get_em_prompt_preserves_json_braces():
    """get_em_prompt does NOT break JSON braces in prompts (safe replace)."""
    from services.prompt_loader import get_em_prompt
    text = get_em_prompt("prompt_sql_generator_em", "fr", TODAY="2026-02-27")
    # SQL prompt contains JSON examples with {} — they must survive
    assert len(text) > 100
    # No KeyError, no crash — that's the test


# ═══════════════════════════════════════════════
# 6: EN prompts contain English instruction
# ═══════════════════════════════════════════════

def test_en_meta_prompt_contains_english_instruction():
    """EN tirages prompts contain 'English' language instruction."""
    from services.prompt_loader import load_prompt_em
    text = load_prompt_em("tirages/prompt_100", "en")
    assert "English" in text or "english" in text


def test_en_chatbot_prompt_is_english():
    """EN chatbot prompt uses English text."""
    from services.prompt_loader import load_prompt_em
    text = load_prompt_em("prompt_hybride_em", "en")
    assert "You are" in text
    # Should NOT contain French-specific markers
    assert "[IDENTITÉ]" not in text


# ═══════════════════════════════════════════════
# 7-8: All EM prompts exist in FR and EN
# ═══════════════════════════════════════════════

_EM_CHATBOT_PROMPTS = [
    "prompt_hybride_em",
    "prompt_pitch_grille_em",
    "prompt_sql_generator_em",
]

_EM_META_TIRAGES = [
    "tirages/prompt_100",
    "tirages/prompt_200",
    "tirages/prompt_300",
    "tirages/prompt_400",
    "tirages/prompt_500",
    "tirages/prompt_600",
    "tirages/prompt_700",
    "tirages/prompt_global",
]

_EM_META_ANNEES = [
    "annees/prompt_1a",
    "annees/prompt_2a",
    "annees/prompt_3a",
    "annees/prompt_4a",
    "annees/prompt_5a",
    "annees/prompt_6a",
    "annees/prompt_global",
]

_ALL_EM_PROMPTS = _EM_CHATBOT_PROMPTS + _EM_META_TIRAGES + _EM_META_ANNEES


@pytest.mark.parametrize("name", _ALL_EM_PROMPTS)
def test_all_em_prompts_exist_fr(name):
    """Every EM prompt exists in FR."""
    from services.prompt_loader import load_prompt_em
    text = load_prompt_em(name, "fr")
    assert len(text) > 20, f"FR prompt '{name}' is empty or too short"


@pytest.mark.parametrize("name", _ALL_EM_PROMPTS)
def test_all_em_prompts_exist_en(name):
    """Every EM prompt exists in EN."""
    from services.prompt_loader import load_prompt_em
    text = load_prompt_em(name, "en")
    assert len(text) > 20, f"EN prompt '{name}' is empty or too short"


# ═══════════════════════════════════════════════
# 9: Placeholder consistency across langs
# ═══════════════════════════════════════════════

def test_prompt_variables_consistent():
    """Same {VARIABLES} in FR and EN for all prompts."""
    from services.prompt_loader import load_prompt_em
    var_pattern = re.compile(r'\{[A-Z_]+\}')
    for name in _ALL_EM_PROMPTS:
        fr_text = load_prompt_em(name, "fr")
        en_text = load_prompt_em(name, "en")
        fr_vars = set(var_pattern.findall(fr_text))
        en_vars = set(var_pattern.findall(en_text))
        assert fr_vars == en_vars, (
            f"Variable mismatch in '{name}': FR={fr_vars}, EN={en_vars}"
        )


# ═══════════════════════════════════════════════
# 10: em_window_to_prompt mapping
# ═══════════════════════════════════════════════

def test_em_window_to_prompt_tirages():
    """Window '100' maps to 'tirages/prompt_100'."""
    from services.prompt_loader import em_window_to_prompt
    assert em_window_to_prompt("100") == "tirages/prompt_100"
    assert em_window_to_prompt("700") == "tirages/prompt_700"
    assert em_window_to_prompt("GLOBAL") == "tirages/prompt_global"


def test_em_window_to_prompt_annees():
    """Window '1A' maps to 'annees/prompt_1a'."""
    from services.prompt_loader import em_window_to_prompt
    assert em_window_to_prompt("1A") == "annees/prompt_1a"
    assert em_window_to_prompt("6A") == "annees/prompt_6a"
    assert em_window_to_prompt("GLOBAL_A") == "annees/prompt_global"


def test_em_window_to_prompt_strips_prefix():
    """Window with EM_ prefix or _EN suffix is cleaned."""
    from services.prompt_loader import em_window_to_prompt
    assert em_window_to_prompt("EM_100") == "tirages/prompt_100"
    assert em_window_to_prompt("EM_1A_EN") == "annees/prompt_1a"
    assert em_window_to_prompt("EM_GLOBAL_EN") == "tirages/prompt_global"


# ═══════════════════════════════════════════════
# 11: LRU cache
# ═══════════════════════════════════════════════

def test_lru_cache_prompts():
    """Same object returned for identical calls (LRU cache)."""
    from services.prompt_loader import load_prompt_em
    a = load_prompt_em("prompt_hybride_em", "fr")
    b = load_prompt_em("prompt_hybride_em", "fr")
    assert a is b  # Same cached object


# ═══════════════════════════════════════════════
# 12-13: Loto prompts untouched
# ═══════════════════════════════════════════════

def test_loto_prompts_untouched():
    """Loto prompt files in prompts/chatbot/ still exist."""
    assert os.path.isfile("prompts/chatbot/prompt_hybride.txt")
    assert os.path.isfile("prompts/chatbot/prompt_pitch_grille.txt")
    assert os.path.isfile("prompts/chatbot/prompt_sql_generator.txt")


def test_loto_loader_still_works():
    """load_prompt('CHATBOT') still returns Loto chatbot prompt."""
    from services.prompt_loader import load_prompt
    text = load_prompt("CHATBOT")
    assert len(text) > 100
    assert "HYBRIDE" in text


def test_loto_meta_loader_still_works():
    """load_prompt('100') still returns Loto META prompt."""
    from services.prompt_loader import load_prompt
    text = load_prompt("100")
    assert len(text) > 20


# ═══════════════════════════════════════════════
# 14: Fallback chain
# ═══════════════════════════════════════════════

def test_fallback_chain():
    """_fallback_chain returns deduplicated chain."""
    from services.prompt_loader import _fallback_chain
    assert _fallback_chain("pt") == ["pt", "en", "fr"]
    assert _fallback_chain("en") == ["en", "fr"]
    assert _fallback_chain("fr") == ["fr", "en"]


# ═══════════════════════════════════════════════
# 15: Placeholder langs have content
# ═══════════════════════════════════════════════

@pytest.mark.parametrize("lang", ["de", "nl"])
def test_placeholder_langs_load(lang):
    """Placeholder languages load prompts (EN copies)."""
    from services.prompt_loader import load_prompt_em
    text = load_prompt_em("prompt_hybride_em", lang)
    assert len(text) > 100
    en = load_prompt_em("prompt_hybride_em", "en")
    assert text == en


def test_es_has_own_prompts():
    """ES has its own translated prompts (not EN copies)."""
    from services.prompt_loader import load_prompt_em
    es = load_prompt_em("prompt_hybride_em", "es")
    assert len(es) > 100
    en = load_prompt_em("prompt_hybride_em", "en")
    assert es != en
    assert "REGLA OBLIGATORIA" in es or "HYBRIDE" in es


def test_pt_has_own_prompts():
    """PT has its own translated prompts (not EN copies)."""
    from services.prompt_loader import load_prompt_em
    pt = load_prompt_em("prompt_hybride_em", "pt")
    assert len(pt) > 100
    en = load_prompt_em("prompt_hybride_em", "en")
    assert pt != en
    assert "REGRA OBRIGATÓRIA" in pt or "HYBRIDE" in pt
