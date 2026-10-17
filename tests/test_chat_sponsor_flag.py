"""1.6.055 — Point 7 : encadré sponsor du chat derrière CHAT_SPONSOR_INLINE (défaut OFF).

Popups / encadrés des pages et PDF non concernés. Aucun changement JS/CSS/template :
sans balise [SPONSOR:], le JS du chatbot ne déclenche aucun suivi.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from config.engine import _env_bool
from services.chat_utils import _get_sponsor_if_due

_LANGS = ["fr", "en", "es", "pt", "de", "nl"]

_CONFIG = {
    "enabled": True,
    "frequency": 3,
    "slots": {
        key: {
            "slot_a": {"id": f"{key.upper()}_A", "active": True,
                       "tagline": {lang: f"Partenaire {lang}" for lang in _LANGS},
                       "url": "mailto:partenariats@lotoia.fr"},
            "slot_b": {"id": f"{key.upper()}_B", "active": True,
                       "tagline": {lang: f"Partenaire {lang}" for lang in _LANGS},
                       "url": "mailto:partenariats@lotoia.fr"},
        }
        for key in ["loto_fr", *[f"em_{lang}" for lang in _LANGS]]
    },
}


def _history(n_bot):
    msgs = []
    for i in range(n_bot):
        msgs.append(SimpleNamespace(role="user", content=f"q{i}"))
        msgs.append(SimpleNamespace(role="assistant", content=f"r{i}"))
    return msgs


# ── Flag OFF (défaut) ──────────────────────────────────────────────────

@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("module", ["loto", "em"])
def test_flag_off_returns_none(module, lang):
    with patch("services.chat_utils.CHAT_SPONSOR_INLINE_ENABLED", False), \
         patch("services.chat_utils._load_sponsors_config", return_value=_CONFIG):
        assert _get_sponsor_if_due(_history(2), lang=lang, module=module) is None


def test_flag_off_does_not_even_load_config():
    with patch("services.chat_utils.CHAT_SPONSOR_INLINE_ENABLED", False), \
         patch("services.chat_utils._load_sponsors_config") as mock_load:
        assert _get_sponsor_if_due(_history(2)) is None
    mock_load.assert_not_called()


def test_module_default_is_off_when_env_absent():
    import config.engine as eng
    if os.environ.get("CHAT_SPONSOR_INLINE") is None:
        assert eng.CHAT_SPONSOR_INLINE_ENABLED is False


# ── Flag ON → comportement actuel ──────────────────────────────────────

@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("module", ["loto", "em"])
def test_flag_on_keeps_current_behaviour(module, lang):
    with patch("services.chat_utils.CHAT_SPONSOR_INLINE_ENABLED", True), \
         patch("services.chat_utils._load_sponsors_config", return_value=_CONFIG):
        out = _get_sponsor_if_due(_history(2), lang=lang, module=module)
        assert out is not None and out.startswith("[SPONSOR:")
        assert _get_sponsor_if_due(_history(1), lang=lang, module=module) is None  # pas la 3e réponse


# ── _env_bool ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("true", True), ("TRUE", True), ("yes ", True), ("1", True), ("on", True),
    ("tru", False), ("false", False), ("0", False), ("", False), ("off", False),
])
def test_env_bool_parsing(raw, expected, monkeypatch):
    monkeypatch.setenv("CHAT_SPONSOR_INLINE_TEST_155", raw)
    assert _env_bool("CHAT_SPONSOR_INLINE_TEST_155", False) is expected


def test_env_bool_absent_uses_default(monkeypatch):
    monkeypatch.delenv("CHAT_SPONSOR_INLINE_TEST_155", raising=False)
    assert _env_bool("CHAT_SPONSOR_INLINE_TEST_155", False) is False


# ── Flux complet, 3e réponse ───────────────────────────────────────────

async def _drain(gen):
    return [e async for e in gen]


def _ctx():
    return {
        "system_prompt": "sys", "contents": [], "mode": "chat", "insult_prefix": "",
        "history": _history(2), "lang": "fr", "_http_client": MagicMock(),
        "gem_api_key": "", "_chat_meta": None,
    }


async def _fake_stream(*args, **kwargs):
    yield "Le 7 est sorti 98 fois."


@pytest.mark.asyncio
@pytest.mark.parametrize("flag,expect_sponsor", [(False, False), (True, True)])
async def test_full_stream_third_answer(flag, expect_sponsor):
    from services.chat_pipeline_gemini import stream_and_respond
    with patch("services.chat_utils.CHAT_SPONSOR_INLINE_ENABLED", flag), \
         patch("services.chat_utils._load_sponsors_config", return_value=_CONFIG), \
         patch("services.chat_pipeline_gemini.log_from_meta"):
        events = await _drain(stream_and_respond(
            _ctx(), "FB", "[T]", "loto", "fr", "msg", "page", "chat", stream_fn=_fake_stream,
        ))
    joined = "".join(events)
    assert ("[SPONSOR:" in joined) is expect_sponsor
    assert "Le 7 est sorti 98 fois." in joined
