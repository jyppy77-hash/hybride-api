"""
Tests for Phase 2 audit fixes S01, S02, S09.
S01 — E4 chatbot EM ES/PT/DE/NL files
S02 — Loto chatbot i18n-aware
S09 — Sponsor popup i18n
"""

import json
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


# ══════════════════════════════════════════════════════════════════════════════
# S01 — New chatbot EM files exist and are valid
# ══════════════════════════════════════════════════════════════════════════════

class TestS01ChatbotEMFiles:
    """Verify 4 new chatbot EM files exist with correct content."""

    LANGS = ["es", "pt", "de", "nl"]

    @pytest.mark.parametrize("lang", LANGS)
    def test_chatbot_file_exists(self, lang):
        path = ROOT / "ui" / "static" / f"hybride-chatbot-em-{lang}.js"
        assert path.exists(), f"Missing chatbot file for {lang}"

    @pytest.mark.parametrize("lang", LANGS)
    def test_chatbot_has_sponsor_parsing(self, lang):
        """Each chatbot file must parse [SPONSOR:ID] markers."""
        path = ROOT / "ui" / "static" / f"hybride-chatbot-em-{lang}.js"
        content = path.read_text(encoding="utf-8")
        assert "extractSponsorId" in content
        assert "[SPONSOR:" in content
        assert "sponsor-inline-shown" in content

    @pytest.mark.parametrize("lang", LANGS)
    def test_chatbot_has_lotoia_track_mirror(self, lang):
        """Each chatbot must have the LotoIA_track mirror (S04/P1)."""
        path = ROOT / "ui" / "static" / f"hybride-chatbot-em-{lang}.js"
        content = path.read_text(encoding="utf-8")
        assert "LotoIA_track('sponsor-inline-shown'" in content

    @pytest.mark.parametrize("lang", LANGS)
    def test_chatbot_no_umami(self, lang):
        """No umami references in new files."""
        path = ROOT / "ui" / "static" / f"hybride-chatbot-em-{lang}.js"
        content = path.read_text(encoding="utf-8")
        assert "umami" not in content.lower()

    @pytest.mark.parametrize("lang", LANGS)
    def test_chatbot_uses_i18n(self, lang):
        """New chatbot files must use window.LotoIA_i18n for labels."""
        path = ROOT / "ui" / "static" / f"hybride-chatbot-em-{lang}.js"
        content = path.read_text(encoding="utf-8")
        assert "LotoIA_i18n" in content
        assert "LI.chatbot_welcome" in content or "LI.chatbot_placeholder" in content

    @pytest.mark.parametrize("lang", LANGS)
    def test_chatbot_correct_lang_param(self, lang):
        """API call must use correct lang parameter."""
        path = ROOT / "ui" / "static" / f"hybride-chatbot-em-{lang}.js"
        content = path.read_text(encoding="utf-8")
        assert f"lang: '{lang}'" in content

    @pytest.mark.parametrize("lang", LANGS)
    def test_chatbot_correct_storage_key(self, lang):
        """Storage key must be unique per language."""
        path = ROOT / "ui" / "static" / f"hybride-chatbot-em-{lang}.js"
        content = path.read_text(encoding="utf-8")
        assert f"hybride-history-em-{lang}" in content

    @pytest.mark.parametrize("lang", LANGS)
    def test_chatbot_no_orphan_routes(self, lang):
        """No calls to deleted /api/track-grid, /api/track-ad-*."""
        path = ROOT / "ui" / "static" / f"hybride-chatbot-em-{lang}.js"
        content = path.read_text(encoding="utf-8")
        assert "/api/track-grid" not in content
        assert "/api/track-ad-impression" not in content
        assert "/api/track-ad-click" not in content


class TestS01TemplateRouting:
    """Verify config/templates.py routes chatbot JS per language."""

    def test_templates_has_lang_based_chatbot_js(self):
        path = ROOT / "config" / "templates.py"
        content = path.read_text(encoding="utf-8")
        assert "hybride-chatbot-em-es.js" in content
        assert "hybride-chatbot-em-pt.js" in content
        assert "hybride-chatbot-em-de.js" in content
        assert "hybride-chatbot-em-nl.js" in content


# ══════════════════════════════════════════════════════════════════════════════
# S02 — Loto chatbot i18n-aware
# ══════════════════════════════════════════════════════════════════════════════

class TestS02LotoChatbotI18n:
    """Verify hybride-chatbot.js uses i18n labels."""

    def test_uses_lotoia_i18n(self):
        path = ROOT / "ui" / "static" / "hybride-chatbot.js"
        content = path.read_text(encoding="utf-8")
        assert "LotoIA_i18n" in content
        assert "var LI = window.LotoIA_i18n" in content

    def test_welcome_text_from_i18n(self):
        path = ROOT / "ui" / "static" / "hybride-chatbot.js"
        content = path.read_text(encoding="utf-8")
        assert "LI.chatbot_loto_welcome" in content

    def test_placeholder_from_i18n(self):
        path = ROOT / "ui" / "static" / "hybride-chatbot.js"
        content = path.read_text(encoding="utf-8")
        assert "LI.chatbot_loto_placeholder" in content

    def test_error_messages_from_i18n(self):
        path = ROOT / "ui" / "static" / "hybride-chatbot.js"
        content = path.read_text(encoding="utf-8")
        assert "LI.chatbot_error_empty" in content
        assert "LI.chatbot_error_connection" in content

    def test_rating_from_i18n(self):
        path = ROOT / "ui" / "static" / "hybride-chatbot.js"
        content = path.read_text(encoding="utf-8")
        assert "LI.chatbot_rating_low" in content
        assert "LI.chatbot_rating_high" in content
        assert "LI.chatbot_rating_5" in content
        assert "LI.chatbot_rating_done" in content

    def test_sponsor_mirror_still_present(self):
        """LotoIA_track sponsor mirror from P1/S04 must still be there."""
        path = ROOT / "ui" / "static" / "hybride-chatbot.js"
        content = path.read_text(encoding="utf-8")
        assert "LotoIA_track('sponsor-inline-shown'" in content

    def test_no_umami(self):
        path = ROOT / "ui" / "static" / "hybride-chatbot.js"
        content = path.read_text(encoding="utf-8")
        assert "umami" not in content.lower()


class TestS02LotoI18nKeys:
    """Verify Loto-specific i18n keys exist in js_i18n.py for all 6 langs."""

    KEYS = ["chatbot_loto_welcome", "chatbot_loto_placeholder",
            "chatbot_loto_bubble_label", "chatbot_loto_rating_question"]

    def test_loto_keys_in_js_i18n(self):
        path = ROOT / "config" / "js_i18n.py"
        content = path.read_text(encoding="utf-8")
        for key in self.KEYS:
            count = content.count(f'"{key}"')
            assert count >= 6, f"Key {key} found only {count} times (need 6 langs)"


# ══════════════════════════════════════════════════════════════════════════════
# S09 — Sponsor popup i18n
# ══════════════════════════════════════════════════════════════════════════════

class TestS09SponsorPopupI18n:
    """Verify sponsor-popup.js uses i18n labels for sponsor config."""

    def test_uses_lotoia_i18n(self):
        path = ROOT / "ui" / "static" / "sponsor-popup.js"
        content = path.read_text(encoding="utf-8")
        assert "LotoIA_i18n" in content
        assert "var LI = window.LotoIA_i18n" in content

    def test_sponsor_names_from_i18n(self):
        path = ROOT / "ui" / "static" / "sponsor-popup.js"
        content = path.read_text(encoding="utf-8")
        assert "LI.sponsor1_name" in content
        assert "LI.sponsor2_name" in content

    def test_sponsor_badges_from_i18n(self):
        path = ROOT / "ui" / "static" / "sponsor-popup.js"
        content = path.read_text(encoding="utf-8")
        assert "LI.sponsor1_badge" in content
        assert "LI.sponsor2_badge" in content

    def test_sponsor_descriptions_from_i18n(self):
        path = ROOT / "ui" / "static" / "sponsor-popup.js"
        content = path.read_text(encoding="utf-8")
        assert "LI.sponsor1_desc" in content
        assert "LI.sponsor2_desc" in content

    def test_no_umami(self):
        path = ROOT / "ui" / "static" / "sponsor-popup.js"
        content = path.read_text(encoding="utf-8")
        assert "umami" not in content.lower()

    def test_lotoia_track_mirror_still_present(self):
        path = ROOT / "ui" / "static" / "sponsor-popup.js"
        content = path.read_text(encoding="utf-8")
        assert "LotoIA_track('sponsor-click'" in content
        assert "LotoIA_track('sponsor-popup-shown'" in content
