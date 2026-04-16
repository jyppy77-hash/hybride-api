"""
V121 keepalive guard — ensures all impression fetch calls include keepalive: true.
Scans JS files for fetch('/api/sponsor/track', ...) blocks with impression event_types
and verifies keepalive is present. Also guards V119 keepalive on pdf-downloaded.
"""

import os
import re

import pytest


# Base directory of the project
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 4 impression event_types that MUST have keepalive
_IMPRESSION_TYPES = {
    "sponsor-popup-shown",
    "sponsor-inline-shown",
    "sponsor-result-shown",
    "sponsor-pdf-mention",
}

# V119 regression guard
_V119_KEEPALIVE_TYPES = {"sponsor-pdf-downloaded"}

# All JS files that contain fetch('/api/sponsor/track', ...)
_JS_FILES = [
    "ui/static/sponsor-popup.js",
    "ui/static/em/sponsor-popup-em.js",
    "ui/static/sponsor-popup75.js",
    "ui/static/sponsor-popup75-em.js",
    "ui/static/hybride-chatbot.js",
    "ui/static/hybride-chatbot-em.js",
    "ui/en/euromillions/static/hybride-chatbot-em-en.js",
    "ui/static/hybride-chatbot-em-en.js",
    "ui/static/hybride-chatbot-em-de.js",
    "ui/static/hybride-chatbot-em-es.js",
    "ui/static/hybride-chatbot-em-pt.js",
    "ui/static/hybride-chatbot-em-nl.js",
    "ui/static/app.js",
    "ui/static/app-em.js",
    "ui/static/simulateur.js",
    "ui/static/simulateur-em.js",
]

# Regex to match fetch blocks: from fetch('/api/sponsor/track' to closing .catch or });
_FETCH_RE = re.compile(
    r"fetch\('/api/sponsor/track'[^)]*\{(.*?)\}\s*\)",
    re.DOTALL,
)
_EVENT_RE = re.compile(r"event_type:\s*'(sponsor-[^']+)'")


class TestV121KeepaliveGuard:
    """V121: all impression fetch calls must have keepalive: true."""

    def test_keepalive_present_on_all_impression_trackers(self):
        """Every fetch for impression event_types must include keepalive: true."""
        missing = []
        for rel_path in _JS_FILES:
            full = os.path.join(_BASE, rel_path)
            if not os.path.isfile(full):
                continue
            with open(full, encoding="utf-8") as f:
                content = f.read()
            for m in _FETCH_RE.finditer(content):
                block = m.group(0)
                ev_match = _EVENT_RE.search(block)
                if not ev_match:
                    continue
                ev_type = ev_match.group(1)
                needs_keepalive = ev_type in _IMPRESSION_TYPES or ev_type in _V119_KEEPALIVE_TYPES
                if needs_keepalive and "keepalive" not in block:
                    missing.append(f"{rel_path}: {ev_type}")

        assert not missing, (
            f"Missing keepalive: true on {len(missing)} impression fetch call(s):\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_v119_keepalive_still_present_on_pdf_downloaded(self):
        """V119 regression guard: pdf-downloaded must still have keepalive."""
        for fname in ("ui/static/sponsor-popup75.js", "ui/static/sponsor-popup75-em.js"):
            full = os.path.join(_BASE, fname)
            with open(full, encoding="utf-8") as f:
                content = f.read()
            idx = content.find("sponsor-pdf-downloaded")
            assert idx != -1, f"{fname}: sponsor-pdf-downloaded not found"
            fetch_start = content.rfind("fetch(", 0, idx)
            assert fetch_start != -1, f"{fname}: fetch( not found before pdf-downloaded"
            block = content[fetch_start:idx + 200]
            assert "keepalive" in block, f"{fname}: keepalive missing on sponsor-pdf-downloaded"
