"""
Tests — admin_helpers.py (Phase 1 refacto V88).
Pure function tests for extracted helpers, constants, and where builders.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from routes.admin_helpers import (
    dec,
    period_to_dates,
    period_label,
    next_invoice_number,
    next_contrat_number,
    build_impressions_where,
    build_votes_where,
    build_realtime_where,
    build_engagement_where,
    VALID_EVENTS,
    VALID_LANGS,
    VALID_DEVICES,
    VALID_SPONSORS,
    VALID_CONTRAT_STATUTS,
    VALID_TYPE_CONTRAT,
    VALID_MODE_DEPASSEMENT,
    VALID_PRODUCT_CODES,
    VALID_TARIF_CODES,
    PERIOD_SQL,
    CM_PERIOD_SQL,
    ENGAGEMENT_EVENTS,
    EVENT_CATEGORIES,
    PALIERS_V9,
)


# ══════════════════════════════════════════════════════════════════════════════
# dec()
# ══════════════════════════════════════════════════════════════════════════════

class TestDec:
    def test_decimal_int(self):
        assert dec(Decimal("42")) == 42
        assert isinstance(dec(Decimal("42")), int)

    def test_decimal_float(self):
        assert dec(Decimal("3.14")) == 3.14
        assert isinstance(dec(Decimal("3.14")), float)

    def test_non_decimal_passthrough(self):
        assert dec(99) == 99
        assert dec("hello") == "hello"
        assert dec(None) is None


# ══════════════════════════════════════════════════════════════════════════════
# period_to_dates()
# ══════════════════════════════════════════════════════════════════════════════

class TestPeriodToDates:
    def test_today(self):
        ds, de = period_to_dates("today")
        assert ds == date.today()
        assert de == date.today() + timedelta(days=1)

    def test_7d(self):
        ds, de = period_to_dates("7d")
        assert ds == date.today() - timedelta(days=6)

    def test_30d(self):
        ds, de = period_to_dates("30d")
        assert ds == date.today() - timedelta(days=29)

    def test_month(self):
        ds, de = period_to_dates("month")
        assert ds.day == 1

    def test_all(self):
        ds, de = period_to_dates("all")
        assert ds == date(2020, 1, 1)

    def test_24h_returns_datetime(self):
        ds, de = period_to_dates("24h")
        # 24h returns datetime objects, not date
        assert hasattr(ds, "hour")

    def test_custom_valid(self):
        ds, de = period_to_dates("custom", "2026-01-01", "2026-01-31")
        assert ds == date(2026, 1, 1)
        assert de == date(2026, 2, 1)  # +1 day

    def test_custom_invalid_falls_through(self):
        ds, de = period_to_dates("custom", "invalid", "also-invalid")
        # Falls through to default (today)
        assert ds == date.today()

    def test_unknown_period(self):
        ds, de = period_to_dates("unknown")
        assert ds == date.today()

    def test_last_month(self):
        ds, de = period_to_dates("last_month")
        assert ds.day == 1
        assert de.day == 1


# ══════════════════════════════════════════════════════════════════════════════
# period_label()
# ══════════════════════════════════════════════════════════════════════════════

class TestPeriodLabel:
    def test_known_periods(self):
        assert period_label("24h", None, None) == "24 dernieres heures"
        assert period_label("today", None, None) == "Aujourd'hui"
        assert period_label("all", None, None) == "Toute la periode"

    def test_unknown_period_shows_dates(self):
        result = period_label("custom", "2026-01-01", "2026-01-31")
        assert "2026-01-01" in result
        assert "2026-01-31" in result


# ══════════════════════════════════════════════════════════════════════════════
# next_invoice_number / next_contrat_number
# ══════════════════════════════════════════════════════════════════════════════

class TestNumberGenerators:
    def test_invoice_number_format(self):
        num = next_invoice_number(0)
        assert num.startswith("FIA-")
        assert num.endswith("-0001")

    def test_invoice_number_increment(self):
        num = next_invoice_number(5)
        assert num.endswith("-0006")

    def test_contrat_number_format(self):
        num = next_contrat_number(0)
        assert num.startswith("CTR-")
        assert num.endswith("-0001")

    def test_contrat_number_increment(self):
        num = next_contrat_number(9)
        assert num.endswith("-0010")


# ══════════════════════════════════════════════════════════════════════════════
# Validation sets — completeness
# ══════════════════════════════════════════════════════════════════════════════

class TestValidationSets:
    def test_valid_events_count(self):
        assert len(VALID_EVENTS) == 6

    def test_valid_langs_count(self):
        assert VALID_LANGS == {"fr", "en", "es", "pt", "de", "nl"}

    def test_valid_devices(self):
        assert VALID_DEVICES == {"mobile", "desktop", "tablet"}

    def test_valid_sponsors_14(self):
        assert len(VALID_SPONSORS) == 14
        assert "LOTO_FR_A" in VALID_SPONSORS

    def test_valid_contrat_statuts(self):
        assert "brouillon" in VALID_CONTRAT_STATUTS
        assert "actif" in VALID_CONTRAT_STATUTS

    def test_valid_type_contrat(self):
        assert "exclusif" in VALID_TYPE_CONTRAT

    def test_valid_mode_depassement(self):
        assert "CPC" in VALID_MODE_DEPASSEMENT

    def test_valid_product_codes(self):
        assert "LOTO_FR" in VALID_PRODUCT_CODES
        assert "EM_EN_A" in VALID_PRODUCT_CODES

    def test_valid_tarif_codes(self):
        assert len(VALID_TARIF_CODES) == 14


# ══════════════════════════════════════════════════════════════════════════════
# Constants — structure
# ══════════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_period_sql_keys(self):
        assert set(PERIOD_SQL.keys()) == {"24h", "today", "week", "month"}

    def test_period_sql_no_curdate(self):
        """V88: no PERIOD_SQL value may use CURDATE(). 'today' uses CONVERT_TZ, others use NOW()."""
        for key, sql in PERIOD_SQL.items():
            assert "CURDATE" not in sql, f"PERIOD_SQL['{key}'] still uses CURDATE()"

    def test_period_sql_today_uses_convert_tz(self):
        """V88: 'today' = midnight Paris via CONVERT_TZ, not 24h sliding window."""
        assert "CONVERT_TZ" in PERIOD_SQL["today"]
        assert "Europe/Paris" in PERIOD_SQL["today"]

    def test_period_sql_24h_is_sliding_window(self):
        assert "NOW() - INTERVAL 24 HOUR" in PERIOD_SQL["24h"]
        assert "CONVERT_TZ" not in PERIOD_SQL["24h"]

    def test_cm_period_sql_keys(self):
        assert set(CM_PERIOD_SQL.keys()) == {"1h", "6h", "24h", "7d", "30d"}

    def test_engagement_events_count(self):
        assert len(ENGAGEMENT_EVENTS) == 10

    def test_event_categories_maps_all_engagement(self):
        for ev in ENGAGEMENT_EVENTS:
            assert ev in EVENT_CATEGORIES

    def test_paliers_v9_count(self):
        assert len(PALIERS_V9) == 4
        assert PALIERS_V9[0]["name"] == "Lancement"


# ══════════════════════════════════════════════════════════════════════════════
# Where builders
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildImpressionsWhere:
    def test_basic(self):
        w, params, ds, de = build_impressions_where("today", "", "", "", "", "")
        assert "created_at >= %s" in w
        assert len(params) == 2

    def test_with_event_type(self):
        w, params, ds, de = build_impressions_where("today", "", "", "sponsor-click", "", "")
        assert "event_type = %s" in w
        assert "sponsor-click" in params

    def test_with_lang(self):
        w, params, ds, de = build_impressions_where("today", "", "", "", "fr", "")
        assert "lang = %s" in w

    def test_with_sponsor_id(self):
        w, params, ds, de = build_impressions_where("today", "", "", "", "", "", sponsor_id="LOTO_FR_A")
        assert "sponsor_id = %s" in w

    def test_with_tarif(self):
        w, params, ds, de = build_impressions_where("today", "", "", "", "", "", tarif="A")
        assert "sponsor_id LIKE %s" in w

    def test_invalid_event_type_ignored(self):
        w, params, ds, de = build_impressions_where("today", "", "", "invalid", "", "")
        assert "event_type" not in w


class TestBuildVotesWhere:
    def test_basic(self):
        w, params, ds, de = build_votes_where("all", "", "")
        assert "created_at >= %s" in w

    def test_with_source(self):
        w, params, ds, de = build_votes_where("all", "chatbot_loto", "")
        assert "source = %s" in w

    def test_with_rating(self):
        w, params, ds, de = build_votes_where("all", "", "5")
        assert "rating = %s" in w
        assert 5 in params

    def test_invalid_rating_ignored(self):
        w, params, ds, de = build_votes_where("all", "", "99")
        assert "rating" not in w


class TestBuildRealtimeWhere:
    def test_default(self):
        w, params = build_realtime_where("all", "24h")
        assert "WHERE" in w
        assert len(params) == 0

    def test_with_event_type(self):
        w, params = build_realtime_where("page-view", "24h")
        assert "event_type = %s" in w
        assert "page-view" in params

    def test_unknown_period_defaults_to_today(self):
        w, params = build_realtime_where("all", "unknown")
        assert PERIOD_SQL["today"] in w


class TestBuildEngagementWhere:
    def test_basic(self):
        w, params, ds, de = build_engagement_where("today", "", "", "", "", "", "")
        assert "event_type NOT LIKE" in w

    def test_with_category(self):
        w, params, ds, de = build_engagement_where("today", "", "", "", "", "", "", category="chatbot")
        assert "event_type IN" in w

    def test_with_product_code(self):
        w, params, ds, de = build_engagement_where("today", "", "", "", "", "", "", product_code="LOTO_FR")
        assert "product_code = %s" in w
