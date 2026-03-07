"""
Tests Phase B SEO — Schema Organization + legal.css conditionnel.
Verifies:
  - Organization schema: founder Person, foundingDate 2025, disambiguatingDescription
  - seo.py and a-propos.html alignment
  - legal.css loaded on legal pages, absent on non-legal EM pages
"""

import json
import os
from contextlib import asynccontextmanager
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ── Patches (same pattern as test_en_routes.py) ─────────────────────────

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
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
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _make_request():
    r = MagicMock()
    r.url.path = "/euromillions/a-propos"
    r.query_params = {}
    r.cookies = {}
    r.headers = {}
    return r


# ═══════════════════════════════════════════════
# 1. Schema Organization in seo.py
# ═══════════════════════════════════════════════

class TestSeoOrganizationSchema:
    """seo.py generate_jsonld_organization() output."""

    def test_founder_is_person(self):
        """founder must be a Person (not Organization)."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert '"@type": "Person"' in html

    def test_founder_name(self):
        """founder name must be Jean-Philippe Godard."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert "Jean-Philippe Godard" in html
        assert "JyppY" in html  # alternateName

    def test_founding_date_2025(self):
        """foundingDate must be 2025."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert '"foundingDate": "2025"' in html

    def test_disambiguating_description(self):
        """disambiguatingDescription must be present."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert "disambiguatingDescription" in html
        assert "literie" in html

    def test_parent_organization(self):
        """parentOrganization EmovisIA must be present."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert "EmovisIA" in html
        assert "parentOrganization" in html

    def test_same_as(self):
        """sameAs must contain emovisia.fr."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert "emovisia.fr" in html

    def test_founder_job_title(self):
        """founder must have jobTitle."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert "jobTitle" in html
        assert "Fondateur" in html

    def test_founder_knows_about(self):
        """founder must have knowsAbout."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert "knowsAbout" in html
        assert "Data Science" in html

    def test_founder_same_as_linkedin(self):
        """founder must have sameAs LinkedIn."""
        from seo import generate_jsonld_organization
        html = generate_jsonld_organization()
        assert "linkedin.com/in/jpgodard" in html


# ═══════════════════════════════════════════════
# 2. Schema Organization in EM a-propos template
# ═══════════════════════════════════════════════

class TestEmAboutOrganizationSchema:
    """EM a-propos.html rendered Organization schema alignment."""

    def test_about_fr_has_disambiguating(self):
        """GET /euromillions/a-propos contains disambiguatingDescription."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/euromillions/a-propos")

        assert resp.status_code == 200
        assert "disambiguatingDescription" in resp.text

    def test_about_fr_founder_person(self):
        """GET /euromillions/a-propos has founder Person."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/euromillions/a-propos")

        assert "Jean-Philippe Godard" in resp.text


# ═══════════════════════════════════════════════
# 3. legal.css conditionnel
# ═══════════════════════════════════════════════

class TestLegalCssConditional:
    """legal.css only on legal pages, not on regular EM pages."""

    @pytest.mark.parametrize("path", [
        "/euromillions/mentions-legales",
        "/euromillions/confidentialite",
        "/euromillions/cookies",
        "/euromillions/avertissement",
    ])
    def test_legal_pages_have_legal_css(self, path):
        """Legal pages must load legal.css."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get(path)

        assert resp.status_code == 200
        assert "legal.css" in resp.text

    @pytest.mark.parametrize("path", [
        "/euromillions",
        "/euromillions/statistiques",
        "/euromillions/faq",
        "/euromillions/hybride",
    ])
    def test_non_legal_pages_also_have_legal_css(self, path):
        """All EM pages load legal.css via _base.html (hero overlap fix Phase 1.5)."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get(path)

        assert resp.status_code == 200
        assert "legal.css" in resp.text


# ═══════════════════════════════════════════════
# 4. Phase C — Bio, Editorial, CTA, Branding
# ═══════════════════════════════════════════════

class TestPhaseC_BioFounder:
    """Bio JyppY enrichment on about pages."""

    def test_em_about_has_founder_bio(self):
        """GET /euromillions/a-propos has founder bio paragraph."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/euromillions/a-propos")

        assert resp.status_code == 200
        assert "Google for Startups" in resp.text
        assert "EmovisIA" in resp.text

    def test_em_about_schema_job_title(self):
        """GET /euromillions/a-propos schema has jobTitle."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/euromillions/a-propos")

        assert "jobTitle" in resp.text
        assert "linkedin.com/in/jpgodard" in resp.text


class TestPhaseC_CtaHybride:
    """CTA HYBRIDE on EM tool pages."""

    @pytest.mark.parametrize("path", [
        "/euromillions/statistiques",
        "/euromillions/generateur",
        "/euromillions/simulateur",
    ])
    def test_em_tool_pages_have_cta_hybride(self, path):
        """EM tool pages must have CTA HYBRIDE."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get(path)

        assert resp.status_code == 200
        assert "cta-hybride" in resp.text
        assert "btn-cta-hybride" in resp.text


# ═══════════════════════════════════════════════
# 5. Phase D — Schema WebSite, WebP, CSS async, _EM_LANG_PREFIXES
# ═══════════════════════════════════════════════

class TestPhaseD_SchemaWebSite:
    """Schema WebSite on EM accueil."""

    def test_em_accueil_has_website_schema(self):
        """GET /euromillions contains WebSite schema."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
            client = _get_client()
            resp = client.get("/euromillions")

        assert resp.status_code == 200
        assert '"@type": "WebSite"' in resp.text or '"@type":"WebSite"' in resp.text

    def test_em_accueil_has_software_application(self):
        """GET /euromillions keeps SoftwareApplication schema."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
            client = _get_client()
            resp = client.get("/euromillions")

        assert resp.status_code == 200
        assert "SoftwareApplication" in resp.text


class TestPhaseD_CssAsync:
    """CSS loaded async on EM pages (non-blocking)."""

    def test_em_page_css_media_print(self):
        """EM pages load style.css with media=print onload pattern."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get("/euromillions/faq")

        assert resp.status_code == 200
        assert 'media="print"' in resp.text
        assert "onload=" in resp.text


class TestPhaseD_WebPImages:
    """WebP source in picture tags."""

    @pytest.mark.parametrize("path", [
        "/euromillions/generateur",
        "/euromillions/simulateur",
    ])
    def test_em_pages_have_webp_source(self, path):
        """EM tool pages have <source> with webp type."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)):
            client = _get_client()
            resp = client.get(path)

        assert resp.status_code == 200
        assert ".webp" in resp.text
        assert "<picture>" in resp.text


class TestPhaseD_AggregateRatingEM:
    """AggregateRating on EM accueil (smart: hidden if < 5)."""

    def test_em_accueil_no_rating_if_low_count(self):
        """GET /euromillions has NO AggregateRating if < 5 reviews."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value={"review_count": 3, "avg_rating": 4.5})):
            client = _get_client()
            resp = client.get("/euromillions")

        assert resp.status_code == 200
        assert "AggregateRating" not in resp.text

    def test_em_accueil_has_rating_if_enough(self):
        """GET /euromillions shows AggregateRating if >= 5 reviews."""
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.fetchall = AsyncMock(return_value=[])
        cursor.close = AsyncMock()

        with patch("db_cloudsql.get_connection", _async_cm_conn(cursor)), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value={"review_count": 12, "avg_rating": 4.7})):
            client = _get_client()
            resp = client.get("/euromillions")

        assert resp.status_code == 200
        assert "AggregateRating" in resp.text
        assert '"ratingValue": "4.7"' in resp.text
        assert '"ratingCount": "12"' in resp.text
