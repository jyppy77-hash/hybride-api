"""
Tests for sponsor injection system (V70 F12).
Tests _get_sponsor_if_due() timing, rotation, and edge cases.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.chat_utils import _get_sponsor_if_due


def _history(n_bot: int):
    """Build a fake history with n_bot assistant messages."""
    msgs = []
    for i in range(n_bot):
        msgs.append(SimpleNamespace(role="user", content=f"question {i+1}"))
        msgs.append(SimpleNamespace(role="assistant", content=f"reponse {i+1}"))
    return msgs


_MOCK_CONFIG = {
    "enabled": True,
    "frequency": 3,
    "slots": {
        "loto_fr": {
            "slot_a": {
                "id": "LOTO_FR_A",
                "active": True,
                "tagline": {"fr": "Espace premium partenaire", "en": "Premium partner space"},
                "url": "mailto:partenariats@lotoia.fr",
            },
            "slot_b": {
                "id": "LOTO_FR_B",
                "active": True,
                "tagline": {"fr": "Espace standard partenaire", "en": "Standard partner space"},
                "url": "mailto:partenariats@lotoia.fr",
            },
        },
        "em_en": {
            "slot_a": {
                "id": "EM_EN_A",
                "active": True,
                "tagline": {"en": "EM premium partner"},
                "url": "mailto:partenariats@lotoia.fr",
            },
            "slot_b": {
                "id": "EM_EN_B",
                "active": True,
                "tagline": {"en": "EM standard partner"},
                "url": "mailto:partenariats@lotoia.fr",
            },
        },
    },
}


def _patch_config(config=None):
    """Patch _load_sponsors_config to return custom config."""
    return patch("services.chat_utils._load_sponsors_config",
                 return_value=config or _MOCK_CONFIG)


class TestSponsorTiming:

    def test_no_injection_1st_message(self):
        """No sponsor on 1st bot message (bot_count=1, 1%3!=0)."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(0))
        assert result is None

    def test_no_injection_2nd_message(self):
        """No sponsor on 2nd bot message (bot_count=2, 2%3!=0)."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(1))
        assert result is None

    def test_injection_3rd_message(self):
        """Sponsor injected on 3rd bot message (bot_count=3, 3%3==0)."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(2))
        assert result is not None
        assert "[SPONSOR:" in result

    def test_injection_6th_message(self):
        """Sponsor injected on 6th bot message."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(5))
        assert result is not None
        assert "[SPONSOR:" in result

    def test_no_injection_4th_message(self):
        """No sponsor on 4th bot message (4%3!=0)."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(3))
        assert result is None


class TestSponsorRotation:

    def test_3rd_message_uses_slot_a(self):
        """3rd message (cycle=1, odd) → slot_a."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(2))
        assert "LOTO_FR_A" in result

    def test_6th_message_uses_slot_b(self):
        """6th message (cycle=2, even) → slot_b."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(5))
        assert "LOTO_FR_B" in result

    def test_9th_message_uses_slot_a_again(self):
        """9th message (cycle=3, odd) → slot_a again."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(8))
        assert "LOTO_FR_A" in result


class TestSponsorInactive:

    def test_inactive_slot_a_falls_to_slot_b(self):
        """If slot_a is inactive, fallback to slot_b."""
        config = {
            "enabled": True, "frequency": 3,
            "slots": {
                "loto_fr": {
                    "slot_a": {"id": "LOTO_FR_A", "active": False,
                               "tagline": {"fr": "A"}, "url": "mailto:a@a.com"},
                    "slot_b": {"id": "LOTO_FR_B", "active": True,
                               "tagline": {"fr": "B"}, "url": "mailto:b@b.com"},
                },
            },
        }
        with _patch_config(config):
            result = _get_sponsor_if_due(_history(2))
        assert result is not None
        assert "LOTO_FR_B" in result

    def test_both_inactive_returns_none(self):
        """If both slots inactive → None."""
        config = {
            "enabled": True, "frequency": 3,
            "slots": {
                "loto_fr": {
                    "slot_a": {"id": "A", "active": False,
                               "tagline": {"fr": "A"}, "url": "mailto:a"},
                    "slot_b": {"id": "B", "active": False,
                               "tagline": {"fr": "B"}, "url": "mailto:b"},
                },
            },
        }
        with _patch_config(config):
            result = _get_sponsor_if_due(_history(2))
        assert result is None


class TestSponsorDisabled:

    def test_disabled_config_returns_none(self):
        """If enabled=false → None, no crash."""
        config = {"enabled": False, "frequency": 3, "slots": {}}
        with _patch_config(config):
            result = _get_sponsor_if_due(_history(2))
        assert result is None

    def test_no_slots_returns_none(self):
        """If no slots for the module → None."""
        config = {"enabled": True, "frequency": 3, "slots": {}}
        with _patch_config(config):
            result = _get_sponsor_if_due(_history(2))
        assert result is None


class TestSponsorLangFallback:

    def test_lang_fr_uses_fr_tagline(self):
        """FR tagline used when lang=fr."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(2), lang="fr")
        assert "premium partenaire" in result

    def test_lang_en_uses_en_tagline(self):
        """EN tagline used when lang=en."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(2), lang="en")
        assert "Premium partner space" in result

    def test_unknown_lang_falls_to_fr(self):
        """Unknown lang falls back to FR tagline."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(2), lang="ja")
        assert "premium partenaire" in result


class TestSponsorFormat:

    def test_contains_sponsor_tag(self):
        """Output contains [SPONSOR:ID] prefix."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(2))
        assert result.startswith("[SPONSOR:")

    def test_contains_email(self):
        """Output contains the contact email."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(2))
        assert "partenariats@lotoia.fr" in result

    def test_contains_tagline(self):
        """Output contains the tagline text."""
        with _patch_config():
            result = _get_sponsor_if_due(_history(2))
        assert "Espace premium partenaire" in result
