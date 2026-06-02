"""
Tests — Launcher SEO (V53 Phase 3/3).
hreflang, canonical, OG tags, sitemap, cleanup, version.
"""
import os
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ── Patches ─────────────────────────────────────────────────────────────

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})


def _get_client():
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def client():
    return _get_client()


BASE = "https://lotoia.fr"


# =========================================================================
# hreflang
# =========================================================================

class TestHreflang:
    """All 6 launcher pages must have 7 hreflang tags (6 langs + x-default)."""

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_hreflang_count(self, client, lang):
        resp = client.get(f"/{lang}")
        tags = re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', resp.text)
        assert len(tags) == 7, f"/{lang}: expected 7 hreflang tags, got {len(tags)}"

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_hreflang_all_langs_present(self, client, lang):
        resp = client.get(f"/{lang}")
        tags = re.findall(r'hreflang="([^"]+)"', resp.text)
        for expected in ["fr", "en", "es", "pt", "de", "nl", "x-default"]:
            assert expected in tags, f"/{lang}: missing hreflang={expected}"

    def test_x_default_points_to_en(self, client):
        resp = client.get("/fr")
        match = re.search(r'hreflang="x-default" href="([^"]+)"', resp.text)
        assert match, "x-default hreflang not found"
        assert match.group(1) == f"{BASE}/en"

    def test_hreflang_urls_absolute(self, client):
        resp = client.get("/en")
        hrefs = re.findall(r'hreflang="[^"]+" href="([^"]+)"', resp.text)
        for href in hrefs:
            assert href.startswith("https://"), f"hreflang not absolute: {href}"


# =========================================================================
# Canonical
# =========================================================================

class TestCanonical:
    """Each launcher page has its own canonical."""

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_canonical(self, client, lang):
        resp = client.get(f"/{lang}")
        match = re.search(r'<link rel="canonical" href="([^"]+)"', resp.text)
        assert match, f"/{lang}: canonical not found"
        assert match.group(1) == f"{BASE}/{lang}"


# =========================================================================
# OG tags
# =========================================================================

class TestOGTags:
    """OG url and locale are correct."""

    _OG_LOCALE = {
        "fr": "fr_FR", "en": "en_GB", "es": "es_ES",
        "pt": "pt_PT", "de": "de_DE", "nl": "nl_NL",
    }

    @pytest.mark.parametrize("lang", ["fr", "en", "de"])
    def test_og_locale(self, client, lang):
        resp = client.get(f"/{lang}")
        expected = self._OG_LOCALE[lang]
        assert f'og:locale" content="{expected}"' in resp.text

    @pytest.mark.parametrize("lang", ["fr", "en"])
    def test_og_url(self, client, lang):
        resp = client.get(f"/{lang}")
        assert f'og:url" content="{BASE}/{lang}"' in resp.text


# =========================================================================
# Sitemap
# =========================================================================

class TestSitemapLauncher:
    """Sitemap includes 6 launcher URLs with hreflang."""

    def test_sitemap_contains_launcher_urls(self, client):
        resp = client.get("/sitemap.xml")
        assert resp.status_code == 200
        for lang in ["fr", "en", "es", "pt", "de", "nl"]:
            assert f"{BASE}/{lang}</loc>" in resp.text

    def test_sitemap_launcher_hreflang(self, client):
        resp = client.get("/sitemap.xml")
        # Each launcher URL block should have x-default alternate
        assert resp.text.count('hreflang="x-default"') >= 6

    def test_sitemap_launcher_priority_fr(self, client):
        resp = client.get("/sitemap.xml")
        # Find the /fr block and check priority
        fr_block = resp.text.split(f"{BASE}/fr</loc>")[1].split("</url>")[0]
        assert "<priority>1.0</priority>" in fr_block

    def test_sitemap_launcher_priority_en(self, client):
        resp = client.get("/sitemap.xml")
        en_block = resp.text.split(f"{BASE}/en</loc>")[1].split("</url>")[0]
        assert "<priority>0.9</priority>" in en_block

    def test_sitemap_launcher_priority_es(self, client):
        resp = client.get("/sitemap.xml")
        es_block = resp.text.split(f"{BASE}/es</loc>")[1].split("</url>")[0]
        assert "<priority>0.8</priority>" in es_block

    def test_sitemap_no_old_root_slash(self, client):
        """The old '/' entry should no longer be in sitemap."""
        resp = client.get("/sitemap.xml")
        assert f"{BASE}/</loc>" not in resp.text


# =========================================================================
# Cleanup
# =========================================================================

class TestCleanup:
    """Old static launcher.html is deleted, redirect filet still works."""

    def test_static_launcher_deleted(self):
        assert not os.path.exists("ui/launcher.html"), "ui/launcher.html should be deleted"

    def test_ui_launcher_redirect(self, client):
        """GET /ui/launcher.html still redirects (filet de sécurité)."""
        resp = client.get("/ui/launcher.html", follow_redirects=False)
        assert resp.status_code in (301, 302)


# =========================================================================
# Version
# =========================================================================

class TestFooterLegalLinks:
    """Footer legal links are localized per language."""

    def test_fr_legal_links(self, client):
        resp = client.get("/fr")
        assert 'href="/mentions-legales"' in resp.text
        assert 'href="/politique-confidentialite"' in resp.text
        assert 'href="/politique-cookies"' in resp.text

    @pytest.mark.parametrize("lang", ["en", "es", "pt", "de", "nl"])
    def test_non_fr_no_hardcoded_fr_legal(self, client, lang):
        resp = client.get(f"/{lang}")
        assert 'href="/mentions-legales"' not in resp.text
        assert 'href="/politique-confidentialite"' not in resp.text
        assert 'href="/politique-cookies"' not in resp.text

    @pytest.mark.parametrize("lang", ["en", "es", "pt", "de", "nl"])
    def test_non_fr_legal_uses_lang_prefix(self, client, lang):
        resp = client.get(f"/{lang}")
        # All non-FR legal links should contain the lang prefix
        assert f'href="/{lang}/euromillions/' in resp.text


# =========================================================================
# Version
# =========================================================================

class TestVersion:
    """V53 version bump."""

    def test_app_version(self):
        # Sprint SEO P1a bump : 1.6.035 → 1.6.036 (01/06/2026 — breadcrumb visible QW4+QW9 : fil d'Ariane HTML aligné JSON-LD sur 12 pages Loto FR + 12 templates EM, msgid "Fil d'Ariane" 6 langues, pas de breadcrumb sur homes, paires JSON-LD Loto->Loto France, historique.html legacy exclu)
        # Sprint SEO P1b bump : 1.6.036 → 1.6.037 (01/06/2026 — meta descriptions EM recalées 120-160 codepoints : 5 msgid réécrits accueil/news/historique/paires/hybride + 6 traductions + statistiques EN ; édition .po ciblée + recompile .mo ; rendu vérifié 36 cellules)
        # Sprint SEO P1c bump : 1.6.037 → 1.6.038 (01/06/2026 — FAQ EM étoffée QW12 : 13/15 Q désync -> 33 Q cohérentes visible == JSON-LD, +16 nouvelles Q + fusion chaud/froid + resync, 34 msgid traduits 6 langues wording ANJ strict, striptags-reuse pour 5 visible-only)
        # Fix i18n numéros d'aide Jeu Responsable bump : 1.6.038 → 1.6.039 (01/06/2026, hors sprint SEO — phone+phone_note dans _GAMBLING_HELP, FAQ lit le dict, msgstr footer/disclaimer EN/PT/NL corrigés, chatbot js_i18n org/url alignés ; valeurs vérifiées GamCare/FEJAR/Linha Vida-SICAD/BIÖG/Open Over Gokken ; templates légaux multi-pays = backlog)
        # Fix i18n numéros d'aide CHATBOT bump : 1.6.039 → 1.6.040 (02/06/2026, complément — smoke staging 1.6.039 a révélé 2 sources chatbot non couvertes : prompts Gemini EM prompts/em/{en,es,pt,de,nl}/prompt_hybride_em.txt + Phase A L3 déterministe chat_detectors_em_guardrails.py/chat_responses_em_en.py ; valeurs alignées _GAMBLING_HELP ; legacy EN GambleAware->GamCare ; FR intact)
        from config.version import APP_VERSION
        assert APP_VERSION == "1.6.040"
