"""
Tests for sponsor banner injection in grid results and META 75 result screens.
V118 Phase 1bis — verifies N banners for N grids (not N-1) and META 75 partner card.

These are grep-based tests: they verify that JS source files contain the expected
patterns for correct banner injection. Frontend rendering is validated visually.
"""

import os

import pytest

# ================================================================
# PATHS
# ================================================================

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_JS = os.path.join(_ROOT, "ui", "static", "app.js")
_APP_EM_JS = os.path.join(_ROOT, "ui", "static", "app-em.js")
_SP75_JS = os.path.join(_ROOT, "ui", "static", "sponsor-popup75.js")
_SP75_EM_JS = os.path.join(_ROOT, "ui", "static", "sponsor-popup75-em.js")
_SP_POPUP_JS = os.path.join(_ROOT, "ui", "static", "sponsor-popup.js")
_SP_POPUP_EM_JS = os.path.join(_ROOT, "ui", "static", "em", "sponsor-popup-em.js")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ================================================================
# GENERATOR BANNERS — app.js (Loto FR)
# ================================================================

class TestGeneratorBannersLoto:
    """Verify app.js injects a partner card after EVERY grid (not N-1)."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = _read(_APP_JS)

    def test_no_length_minus_one_condition(self):
        """The old N-1 condition must be removed."""
        assert "index < grids.length - 1" not in self.src

    def test_partner_card_called_unconditionally(self):
        """createPartnerCard must be called without conditional guard."""
        lines = self.src.splitlines()
        for i, line in enumerate(lines):
            if "createPartnerCard(index)" in line:
                # The previous non-blank line should NOT be an if condition
                prev = lines[i - 1].strip() if i > 0 else ""
                assert "if " not in prev or "length" not in prev
                break
        else:
            pytest.fail("createPartnerCard(index) not found in app.js")

    def test_create_partner_card_function_exists(self):
        """createPartnerCard function must exist."""
        assert "function createPartnerCard(" in self.src

    def test_partner_card_contains_partner_badge(self):
        """The partner card must contain the 'Partenaire' badge."""
        assert "partner-badge" in self.src
        assert "Partenaire" in self.src

    def test_partner_card_contains_cta(self):
        """The partner card must contain a CTA link."""
        assert "partner-cta" in self.src
        assert "En savoir plus" in self.src


# ================================================================
# GENERATOR BANNERS — app-em.js (EuroMillions)
# ================================================================

class TestGeneratorBannersEM:
    """Verify app-em.js injects a partner card after EVERY grid (not N-1)."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = _read(_APP_EM_JS)

    def test_no_length_minus_one_condition(self):
        """The old N-1 condition must be removed."""
        assert "index < grids.length - 1" not in self.src

    def test_partner_card_called_unconditionally(self):
        """createPartnerCardEM must be called without conditional guard."""
        lines = self.src.splitlines()
        for i, line in enumerate(lines):
            if "createPartnerCardEM(index)" in line:
                prev = lines[i - 1].strip() if i > 0 else ""
                assert "if " not in prev or "length" not in prev
                break
        else:
            pytest.fail("createPartnerCardEM(index) not found in app-em.js")

    def test_create_partner_card_em_function_exists(self):
        """createPartnerCardEM function must exist."""
        assert "function createPartnerCardEM(" in self.src

    def test_partner_card_contains_i18n_badge(self):
        """The partner card must use i18n label."""
        assert "LI.partner_label" in self.src

    def test_partner_card_contains_i18n_cta(self):
        """The partner card must use i18n CTA."""
        assert "LI.partner_cta" in self.src


# ================================================================
# META 75 RESULT BANNER — sponsor-popup75.js (Loto FR)
# ================================================================

class TestMeta75BannerLoto:
    """Verify META 75 result popup contains a partner card before action buttons."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = _read(_SP75_JS)

    def test_meta_result_contains_partner_banner(self):
        """META 75 result must contain a meta-result-partner div."""
        assert "meta-result-partner" in self.src

    def test_meta_result_partner_before_actions(self):
        """Partner banner must appear before meta-result-actions in the HTML."""
        pos_partner = self.src.index("meta-result-partner")
        pos_actions = self.src.index("meta-result-actions")
        assert pos_partner < pos_actions

    def test_meta_result_partner_after_analysis(self):
        """Partner banner must appear after meta-result-analysis in the HTML."""
        pos_analysis = self.src.index("meta-result-analysis-text")
        pos_partner = self.src.index("meta-result-partner")
        assert pos_analysis < pos_partner

    def test_meta_result_partner_not_clickable(self):
        """Partner banner must NOT contain any href or mailto link."""
        # Find the meta-result-partner block
        start = self.src.index("meta-result-partner")
        # Look in the next 500 chars for the closing div
        block = self.src[start:start + 500]
        assert "href" not in block
        assert "mailto" not in block
        assert "onclick" not in block

    def test_meta_result_partner_compact_inline(self):
        """Partner banner must use inline styles for compact layout."""
        start = self.src.index("meta-result-partner")
        block = self.src[start:start + 300]
        assert "max-height: 60px" in block

    def test_meta_result_partner_text_visible(self):
        """Partner banner must display PARTENAIRE label and partner text."""
        assert "PARTENAIRE" in self.src
        assert "propulsé par nos partenaires" in self.src


# ================================================================
# META 75 RESULT BANNER — sponsor-popup75-em.js (EuroMillions)
# ================================================================

class TestMeta75BannerEM:
    """Verify META 75 EM result popup contains a partner banner before action buttons."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = _read(_SP75_EM_JS)

    def test_meta_result_contains_partner_banner(self):
        """META 75 EM result must contain a meta-result-partner div."""
        assert "meta-result-partner" in self.src

    def test_meta_result_partner_before_actions(self):
        """Partner banner must appear before meta-result-actions in the HTML."""
        pos_partner = self.src.index("meta-result-partner")
        pos_actions = self.src.index("meta-result-actions")
        assert pos_partner < pos_actions

    def test_meta_result_partner_after_analysis(self):
        """Partner banner must appear after meta-result-analysis in the HTML."""
        pos_analysis = self.src.index("meta-result-analysis-text")
        pos_partner = self.src.index("meta-result-partner")
        assert pos_analysis < pos_partner

    def test_meta_result_partner_not_clickable(self):
        """Partner banner must NOT contain any href or mailto link."""
        start = self.src.index("meta-result-partner")
        block = self.src[start:start + 500]
        assert "href" not in block
        assert "mailto" not in block
        assert "onclick" not in block

    def test_meta_result_partner_compact_inline(self):
        """Partner banner must use inline styles for compact layout."""
        start = self.src.index("meta-result-partner")
        block = self.src[start:start + 300]
        assert "max-height: 60px" in block

    def test_meta_result_partner_uses_i18n(self):
        """EM partner banner must use i18n labels from LI."""
        assert "LI.meta_partner_label" in self.src
        assert "LI.meta_partner_text" in self.src


# ================================================================
# I18N KEYS — js_i18n.py
# ================================================================

class TestMeta75PartnerI18n:
    """Verify meta_partner_label and meta_partner_text keys exist in all 6 languages."""

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_meta_partner_label_exists(self, lang):
        from config.js_i18n import get_js_labels
        labels = get_js_labels(lang)
        assert "meta_partner_label" in labels
        assert len(labels["meta_partner_label"]) > 0

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_meta_partner_text_exists(self, lang):
        from config.js_i18n import get_js_labels
        labels = get_js_labels(lang)
        assert "meta_partner_text" in labels
        assert len(labels["meta_partner_text"]) > 0


# ================================================================
# TRACKING 3 COUCHES — app.js (Loto FR)
# ================================================================

class TestTrackingLoto:
    """Verify app.js trackAdImpression sends couche 1 + couche 2."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = _read(_APP_JS)

    def test_track_ad_impression_not_empty(self):
        """trackAdImpression must NOT be an empty function."""
        # Find the function body — should contain fetch
        idx = self.src.index("function trackAdImpression(")
        block = self.src[idx:idx + 800]
        assert "fetch('/api/sponsor/track'" in block

    def test_track_ad_impression_couche1_result_shown(self):
        """trackAdImpression must send event_type sponsor-result-shown."""
        idx = self.src.index("function trackAdImpression(")
        block = self.src[idx:idx + 800]
        assert "sponsor-result-shown" in block

    def test_track_ad_impression_couche2_lotoia_track(self):
        """trackAdImpression must call LotoIA_track."""
        idx = self.src.index("function trackAdImpression(")
        block = self.src[idx:idx + 800]
        assert "LotoIA_track" in block

    def test_track_ad_click_not_empty(self):
        """trackAdClick must NOT be an empty function."""
        idx = self.src.index("function trackAdClick(")
        block = self.src[idx:idx + 800]
        assert "fetch('/api/sponsor/track'" in block


# ================================================================
# TRACKING 3 COUCHES — app-em.js (EuroMillions)
# ================================================================

class TestTrackingEM:
    """Verify app-em.js trackAdImpressionEM sends couche 1 + couche 2."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = _read(_APP_EM_JS)

    def test_track_ad_impression_em_not_empty(self):
        """trackAdImpressionEM must NOT be an empty function."""
        idx = self.src.index("function trackAdImpressionEM(")
        block = self.src[idx:idx + 800]
        assert "fetch('/api/sponsor/track'" in block

    def test_track_ad_impression_em_couche1_result_shown(self):
        """trackAdImpressionEM must send event_type sponsor-result-shown."""
        idx = self.src.index("function trackAdImpressionEM(")
        block = self.src[idx:idx + 800]
        assert "sponsor-result-shown" in block

    def test_track_ad_impression_em_couche2_lotoia_track(self):
        """trackAdImpressionEM must call LotoIA_track."""
        idx = self.src.index("function trackAdImpressionEM(")
        block = self.src[idx:idx + 800]
        assert "LotoIA_track" in block

    def test_track_ad_impression_em_dynamic_sponsor_id(self):
        """EM sponsor_id must be dynamically built from locale via helper."""
        # Helper function builds EM_{LANG}_A
        assert "function _getEmSponsorId()" in self.src
        idx = self.src.index("function _getEmSponsorId()")
        block = self.src[idx:idx + 200]
        assert "EM_" in block
        assert "_A" in block

    def test_track_ad_click_em_not_empty(self):
        """trackAdClickEM must NOT be an empty function."""
        idx = self.src.index("function trackAdClickEM(")
        block = self.src[idx:idx + 800]
        assert "fetch('/api/sponsor/track'" in block


# ================================================================
# TRACKING META 75 RESULT — sponsor-popup75.js + sponsor-popup75-em.js
# ================================================================

class TestTrackingMeta75Result:
    """Verify META 75 result popup sends result-shown tracking."""

    def test_meta75_loto_result_shown_couche1(self):
        src = _read(_SP75_JS)
        # Find openMetaResultPopup function and check for result-shown after DOM append
        idx = src.index("function openMetaResultPopup(")
        block = src[idx:idx + 6000]
        assert "sponsor-result-shown" in block

    def test_meta75_em_result_shown_couche1(self):
        src = _read(_SP75_EM_JS)
        idx = src.index("function openMetaResultPopupEM(")
        block = src[idx:idx + 6000]
        assert "sponsor-result-shown" in block

    def test_meta75_loto_result_shown_couche2(self):
        src = _read(_SP75_JS)
        idx = src.index("function openMetaResultPopup(")
        block = src[idx:idx + 6000]
        # Count occurrences of LotoIA_track with result-shown
        assert block.count("LotoIA_track") >= 1
        assert "sponsor-result-shown" in block

    def test_meta75_em_result_shown_couche2(self):
        src = _read(_SP75_EM_JS)
        idx = src.index("function openMetaResultPopupEM(")
        block = src[idx:idx + 6000]
        assert block.count("LotoIA_track") >= 1
        assert "sponsor-result-shown" in block


# ================================================================
# REGRESSION F05 — Popup mono-sponsor : 1 fetch popup-shown, pas 2
# ================================================================

class TestPopupMonoSponsorLoto:
    """V119 F05: popup must send exactly 1 popup-shown fetch, not forEach on 2 cards."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = _read(_SP_POPUP_JS)

    def test_no_foreach_sponsors_config(self):
        """SPONSORS_CONFIG.forEach must NOT be used for tracking (double-count bug)."""
        assert "SPONSORS_CONFIG.forEach" not in self.src

    def test_single_popup_shown_fetch(self):
        """Only 1 fetch with popup-shown must exist in the popup tracking block."""
        # Find the mono-sponsor tracking block
        assert "mainSponsor = SPONSORS_CONFIG[0]" in self.src
        # Count popup-shown occurrences in fetch calls
        count = self.src.count("event_type: 'sponsor-popup-shown'")
        assert count == 1, f"Expected 1 popup-shown fetch, found {count}"

    def test_single_lotoia_track_popup_shown(self):
        """Only 1 LotoIA_track('sponsor-popup-shown') call must exist."""
        count = self.src.count("LotoIA_track('sponsor-popup-shown'")
        assert count == 1, f"Expected 1 LotoIA_track popup-shown, found {count}"

    def test_main_sponsor_uses_config_zero(self):
        """mainSponsor must reference SPONSORS_CONFIG[0] (card A = sponsor principal)."""
        assert "SPONSORS_CONFIG[0]" in self.src

    def test_track_impression_ga4_single_id(self):
        """trackImpression must be called with [mainSponsor.id], not full array."""
        assert "trackImpression([mainSponsor.id])" in self.src


class TestPopupMonoSponsorEM:
    """V119 F05: EM popup must send exactly 1 popup-shown fetch, not forEach on 2 cards."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = _read(_SP_POPUP_EM_JS)

    def test_no_foreach_sponsors_config_em(self):
        """SPONSORS_CONFIG_EM.forEach must NOT be used for tracking (double-count bug)."""
        assert "SPONSORS_CONFIG_EM.forEach" not in self.src

    def test_single_popup_shown_fetch(self):
        """Only 1 fetch with popup-shown must exist in the popup tracking block."""
        assert "mainSponsor = SPONSORS_CONFIG_EM[0]" in self.src
        count = self.src.count("event_type: 'sponsor-popup-shown'")
        assert count == 1, f"Expected 1 popup-shown fetch, found {count}"

    def test_single_lotoia_track_popup_shown(self):
        """Only 1 LotoIA_track('sponsor-popup-shown') call must exist."""
        count = self.src.count("LotoIA_track('sponsor-popup-shown'")
        assert count == 1, f"Expected 1 LotoIA_track popup-shown, found {count}"

    def test_main_sponsor_uses_config_zero(self):
        """mainSponsor must reference SPONSORS_CONFIG_EM[0] (card A = sponsor principal)."""
        assert "SPONSORS_CONFIG_EM[0]" in self.src

    def test_track_impression_ga4_single_id(self):
        """trackImpressionSimulateurEM must be called with [mainSponsor.id], not full array."""
        assert "trackImpressionSimulateurEM([mainSponsor.id])" in self.src
