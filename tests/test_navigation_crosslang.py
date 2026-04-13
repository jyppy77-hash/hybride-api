"""
Tests navigation cross-module / cross-langue — P0+P1+P2.
Verifies:
  - P0 #1  : accueil EM methodologie link uses {{ urls.methodologie }} (not hardcoded)
  - P0 #1b : middleware access control regex matches /de/euromillions (not /de/euromillionen)
  - P1 #2-6: prompt URLs match actual EM_URLS routes per language
  - P2 #8  : JSON-LD license in statistiques.html is dynamic (not hardcoded)
  - P2 #9  : chatbot EM JS uses i18n keys instead of hardcoded FR text
  - Regression: no hardcoded href="/methodologie" in EM templates
"""

import os
import re
import glob

import pytest

from config.templates import EM_URLS


# ═══════════════════════════════════════════════════════════════════════════════
# P0 #1b — Middleware access control DE regex
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccessControlDE:
    """Verify /de/euromillions/* routes are matched by the middleware regex."""

    def test_de_euromillions_matched(self):
        """Regex must match /de/euromillions (not /de/euromillionen)."""
        from middleware.em_access_control import is_em_route
        assert is_em_route("/de/euromillions") is True

    def test_de_euromillions_subpage_matched(self):
        from middleware.em_access_control import is_em_route
        assert is_em_route("/de/euromillions/simulator") is True

    def test_de_euromillions_statistiken_matched(self):
        from middleware.em_access_control import is_em_route
        assert is_em_route("/de/euromillions/statistiken") is True

    def test_de_euromillionen_typo_not_matched(self):
        """Old typo /de/euromillionen must NOT be matched anymore."""
        from middleware.em_access_control import is_em_route
        assert is_em_route("/de/euromillionen") is False

    def test_de_euromillionen_subpage_not_matched(self):
        from middleware.em_access_control import is_em_route
        assert is_em_route("/de/euromillionen/generator") is False


# ═══════════════════════════════════════════════════════════════════════════════
# P0 #1 — No hardcoded href="/methodologie" in EM templates
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoHardcodedMethodologieLink:
    """Verify no EM template contains href="/methodologie" (cross-module bug)."""

    def test_no_hardcoded_methodologie_in_em_templates(self):
        """Scan all EM templates: href="/methodologie" must not appear."""
        em_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "ui", "templates", "em",
        )
        pattern = re.compile(r'href="/methodologie"')
        hits = []
        for filepath in glob.glob(os.path.join(em_dir, "**", "*.html"), recursive=True):
            with open(filepath, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if pattern.search(line):
                        hits.append(f"{os.path.basename(filepath)}:{i}")
        assert hits == [], f"Hardcoded href=\"/methodologie\" found in: {hits}"


# ═══════════════════════════════════════════════════════════════════════════════
# P1 #2-6 — Prompt URLs match actual EM_URLS routes
# ═══════════════════════════════════════════════════════════════════════════════

def _load_prompt(lang: str) -> str:
    """Load the EM HYBRIDE prompt for a given language."""
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "prompts", "em", lang, "prompt_hybride_em.txt",
    )
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()


class TestPromptURLsFR:
    """P1 #2 — FR prompt must use current EM route paths."""

    def test_no_simulateur_em_obsolete(self):
        """Old /simulateur-em route must not appear."""
        text = _load_prompt("fr")
        assert "/simulateur-em" not in text

    def test_no_statistiques_em_obsolete(self):
        """Old /statistiques-em route must not appear."""
        text = _load_prompt("fr")
        assert "/statistiques-em" not in text

    def test_has_euromillions_simulateur(self):
        text = _load_prompt("fr")
        assert "/euromillions/simulateur" in text

    def test_has_euromillions_generateur(self):
        text = _load_prompt("fr")
        assert "/euromillions/generateur" in text

    def test_has_euromillions_statistiques(self):
        text = _load_prompt("fr")
        assert "/euromillions/statistiques" in text


class TestPromptURLsPT:
    """P1 #3 — PT prompt must use PT route slugs, not EN."""

    def test_no_english_generator(self):
        text = _load_prompt("pt")
        assert "/pt/euromillions/generator" not in text

    def test_no_english_simulator(self):
        text = _load_prompt("pt")
        assert "/pt/euromillions/simulator" not in text

    def test_no_english_statistics(self):
        text = _load_prompt("pt")
        assert "/pt/euromillions/statistics" not in text

    def test_has_correct_gerador(self):
        text = _load_prompt("pt")
        assert EM_URLS["pt"]["generateur"] in text  # /pt/euromillions/gerador

    def test_has_correct_simulador(self):
        text = _load_prompt("pt")
        assert EM_URLS["pt"]["simulateur"] in text  # /pt/euromillions/simulador

    def test_has_correct_estatisticas(self):
        text = _load_prompt("pt")
        assert EM_URLS["pt"]["statistiques"] in text  # /pt/euromillions/estatisticas


class TestPromptURLsES:
    """P1 #4 — ES prompt must use ES route slugs, not EN."""

    def test_no_english_generator(self):
        text = _load_prompt("es")
        assert "/es/euromillions/generator" not in text

    def test_no_english_simulator(self):
        text = _load_prompt("es")
        assert "/es/euromillions/simulator" not in text

    def test_no_english_statistics(self):
        text = _load_prompt("es")
        assert "/es/euromillions/statistics" not in text

    def test_has_correct_generador(self):
        text = _load_prompt("es")
        assert EM_URLS["es"]["generateur"] in text  # /es/euromillions/generador

    def test_has_correct_simulador(self):
        text = _load_prompt("es")
        assert EM_URLS["es"]["simulateur"] in text  # /es/euromillions/simulador

    def test_has_correct_estadisticas(self):
        text = _load_prompt("es")
        assert EM_URLS["es"]["statistiques"] in text  # /es/euromillions/estadisticas


class TestPromptURLsDE:
    """P1 #5 — DE prompt must use DE route slugs where they differ."""

    def test_no_english_statistics(self):
        text = _load_prompt("de")
        assert "/de/euromillions/statistics" not in text

    def test_has_correct_statistiken(self):
        text = _load_prompt("de")
        assert EM_URLS["de"]["statistiques"] in text  # /de/euromillions/statistiken


class TestPromptURLsNL:
    """P1 #6 — NL prompt must use NL route slugs where they differ."""

    def test_no_english_statistics(self):
        text = _load_prompt("nl")
        assert "/nl/euromillions/statistics" not in text

    def test_has_correct_statistieken(self):
        text = _load_prompt("nl")
        assert EM_URLS["nl"]["statistiques"] in text  # /nl/euromillions/statistieken


class TestPromptURLsEN:
    """EN prompt must use EN route slugs (baseline — should pass)."""

    def test_has_correct_generator(self):
        text = _load_prompt("en")
        assert EM_URLS["en"]["generateur"] in text  # /en/euromillions/generator

    def test_has_correct_simulator(self):
        text = _load_prompt("en")
        assert EM_URLS["en"]["simulateur"] in text  # /en/euromillions/simulator

    def test_has_correct_statistics(self):
        text = _load_prompt("en")
        assert EM_URLS["en"]["statistiques"] in text  # /en/euromillions/statistics


# ═══════════════════════════════════════════════════════════════════════════════
# P2 #8 — JSON-LD license not hardcoded in statistiques.html
# ═══════════════════════════════════════════════════════════════════════════════

class TestJsonLdLicense:
    """Verify JSON-LD license in statistiques EM uses dynamic URL."""

    def test_no_hardcoded_license_url(self):
        """lotoia.fr/mentions-legales must not be hardcoded in template."""
        filepath = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "ui", "templates", "em", "statistiques.html",
        )
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        assert '"license": "https://lotoia.fr/mentions-legales"' not in content

    def test_license_uses_cc_url(self):
        """License field should use Creative Commons BY-NC-ND 4.0 URL."""
        filepath = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "ui", "templates", "em", "statistiques.html",
        )
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        assert "https://creativecommons.org/licenses/by-nc-nd/4.0/" in content


# ═══════════════════════════════════════════════════════════════════════════════
# P2 #9 — Chatbot EM JS uses i18n keys (no hardcoded FR strings)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_chatbot_js() -> str:
    filepath = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "ui", "static", "hybride-chatbot-em.js",
    )
    with open(filepath, encoding="utf-8") as f:
        return f.read()


class TestChatbotEMi18n:
    """Verify chatbot EM JS uses LotoIA_i18n instead of hardcoded FR text."""

    def test_no_hardcoded_rating_question(self):
        js = _load_chatbot_js()
        # Must use LI.chatbot_rating_question, not bare string
        assert "LI.chatbot_rating_question" in js

    def test_no_hardcoded_bof(self):
        js = _load_chatbot_js()
        assert "LI.chatbot_rating_low" in js

    def test_no_hardcoded_top(self):
        js = _load_chatbot_js()
        assert "LI.chatbot_rating_high" in js

    def test_no_hardcoded_error_empty(self):
        js = _load_chatbot_js()
        assert "LI.chatbot_error_empty" in js

    def test_no_hardcoded_error_connection(self):
        js = _load_chatbot_js()
        assert "LI.chatbot_error_connection" in js

    def test_no_hardcoded_rating_done(self):
        js = _load_chatbot_js()
        assert "LI.chatbot_rating_done" in js

    def test_rating_messages_use_i18n(self):
        js = _load_chatbot_js()
        for n in range(1, 6):
            assert f"LI.chatbot_rating_{n}" in js


class TestJsI18nChatbotKeys:
    """Verify all chatbot i18n keys exist in all 6 languages."""

    _CHATBOT_KEYS = [
        "chatbot_error_empty",
        "chatbot_error_connection",
        "chatbot_rating_question",
        "chatbot_rating_low",
        "chatbot_rating_high",
        "chatbot_rating_5",
        "chatbot_rating_4",
        "chatbot_rating_3",
        "chatbot_rating_2",
        "chatbot_rating_1",
        "chatbot_rating_default",
        "chatbot_rating_done",
    ]

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_all_chatbot_keys_present(self, lang):
        from config.js_i18n import get_js_labels
        labels = get_js_labels(lang)
        missing = [k for k in self._CHATBOT_KEYS if k not in labels]
        assert missing == [], f"Missing keys in {lang}: {missing}"

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_no_empty_chatbot_labels(self, lang):
        from config.js_i18n import get_js_labels
        labels = get_js_labels(lang)
        empty = [k for k in self._CHATBOT_KEYS if not labels.get(k, "").strip()]
        assert empty == [], f"Empty keys in {lang}: {empty}"
