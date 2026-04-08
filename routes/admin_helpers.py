"""
Admin helpers — shared constants, auth, validation sets, period/date helpers.
=============================================================================
Extracted from routes/admin.py (Phase 1 refacto V88).
All non-route utilities used across multiple admin endpoints.
"""

import json
import logging
import os
import secrets
from datetime import date, timedelta, datetime
from decimal import Decimal

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

logger = logging.getLogger(__name__)

__all__ = [
    # Auth config
    "ADMIN_TOKEN", "ADMIN_PASSWORD", "COOKIE_NAME",
    # Auth helpers
    "check_admin_ip", "is_authenticated", "require_auth", "require_auth_json",
    # Generic helpers
    "dec", "period_to_dates", "period_label",
    "next_invoice_number", "next_contrat_number",
    # Validation sets
    "VALID_EVENTS", "VALID_LANGS", "VALID_DEVICES", "VALID_SOURCES", "VALID_STATUTS",
    "VALID_SPONSORS", "VALID_CONTRAT_STATUTS", "VALID_TYPE_CONTRAT",
    "VALID_MODE_DEPASSEMENT", "VALID_PRODUCT_CODES", "VALID_TARIF_CODES",
    "VALID_MODULES", "VALID_CATEGORIES",
    # Realtime constants
    "PERIOD_SQL", "PERIOD_LABELS",
    # Chatbot monitor constants
    "CM_PERIOD_SQL",
    # Engagement constants
    "ENGAGEMENT_EVENTS", "EVENT_CATEGORIES",
    # Sponsor helpers
    "SPONSORS_JSON_PATH", "load_sponsor_names",
    # Tarifs constants
    "PALIERS_V9",
    # Where builders
    "build_impressions_where", "build_votes_where",
    "build_realtime_where", "build_engagement_where",
]


# ══════════════════════════════════════════════════════════════════════════════
# AUTH CONFIG — module-level, re-evaluated on importlib.reload()
# ══════════════════════════════════════════════════════════════════════════════

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
COOKIE_NAME = "lotoia_admin_token"


# ══════════════════════════════════════════════════════════════════════════════
# AUTH HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def check_admin_ip(request: Request) -> JSONResponse | None:
    """Restrict admin access to OWNER_IP only. Returns 403 response or None."""
    from middleware.ip_ban import _is_owner_or_loopback, _extract_client_ip
    real_ip = _extract_client_ip(request)
    if not real_ip or real_ip == "testclient":
        return None  # TestClient / empty → allow (dev)
    if _is_owner_or_loopback(real_ip):
        return None
    logger.warning("[ADMIN_AUDIT] action=admin_ip_blocked ip=%s path=%s", real_ip, request.url.path)
    return JSONResponse({"error": "Forbidden"}, status_code=403)


def is_authenticated(request: Request) -> bool:
    """Check admin cookie (timing-safe comparison)."""
    if not ADMIN_TOKEN:
        return False
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        return False
    return secrets.compare_digest(token, ADMIN_TOKEN)


def require_auth(request: Request):
    """HTML page auth guard. Returns redirect or 403, or None if OK."""
    ip_block = check_admin_ip(request)
    if ip_block:
        return ip_block
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)
    return None


def require_auth_json(request: Request):
    """JSON API auth guard. Returns 401/403, or None if OK."""
    ip_block = check_admin_ip(request)
    if ip_block:
        return ip_block
    if not is_authenticated(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# GENERIC HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def dec(v):
    """Convert Decimal to int/float for JSON serialization."""
    if isinstance(v, Decimal):
        return int(v) if v == int(v) else float(v)
    return v


def period_to_dates(period: str, date_start: str = "", date_end: str = ""):
    """Convert period string to (start, end) date/datetime tuple."""
    today = date.today()
    if period == "24h":
        now = datetime.now()
        return now - timedelta(hours=24), now + timedelta(minutes=5)
    if period == "today":
        return today, today + timedelta(days=1)
    if period == "7d":
        return today - timedelta(days=6), today + timedelta(days=1)
    if period == "30d":
        return today - timedelta(days=29), today + timedelta(days=1)
    if period == "month":
        return today.replace(day=1), today + timedelta(days=1)
    if period == "last_month":
        first_this = today.replace(day=1)
        last_month_end = first_this - timedelta(days=1)
        return last_month_end.replace(day=1), first_this
    if period == "custom" and date_start and date_end:
        try:
            ds = date.fromisoformat(date_start)
            de = date.fromisoformat(date_end) + timedelta(days=1)
            return ds, de
        except ValueError:
            pass
    if period == "all":
        return date(2020, 1, 1), today + timedelta(days=1)
    return today, today + timedelta(days=1)


def period_label(period: str, ds, de):
    """Human-readable label for a period."""
    labels = {"24h": "24 dernieres heures", "today": "Aujourd'hui", "7d": "7 derniers jours",
              "30d": "30 derniers jours", "month": "Ce mois", "last_month": "Mois dernier",
              "all": "Toute la periode"}
    return labels.get(period, f"{ds} — {de}")


def next_invoice_number(existing_count: int) -> str:
    """Generate next invoice number FIA-YYYYMM-NNNN."""
    today = date.today()
    return f"FIA-{today.strftime('%Y%m')}-{existing_count + 1:04d}"


def next_contrat_number(existing_count: int) -> str:
    """Generate next contract number CTR-YYYYMM-NNNN."""
    today = date.today()
    return f"CTR-{today.strftime('%Y%m')}-{existing_count + 1:04d}"


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION SETS
# ══════════════════════════════════════════════════════════════════════════════

VALID_EVENTS = {"sponsor-popup-shown", "sponsor-click", "sponsor-video-played", "sponsor-inline-shown", "sponsor-result-shown", "sponsor-pdf-downloaded"}
VALID_LANGS = {"fr", "en", "es", "pt", "de", "nl"}
VALID_DEVICES = {"mobile", "desktop", "tablet"}
VALID_SOURCES = {"chatbot_loto", "chatbot_em", "chatbot_em_en", "popup_accueil", "popup_em"}
VALID_STATUTS = {"brouillon", "envoyee", "payee"}

VALID_SPONSORS = frozenset([
    "LOTO_FR_A", "LOTO_FR_B", "EM_FR_A", "EM_FR_B",
    "EM_EN_A", "EM_EN_B", "EM_ES_A", "EM_ES_B",
    "EM_PT_A", "EM_PT_B", "EM_DE_A", "EM_DE_B",
    "EM_NL_A", "EM_NL_B",
])

VALID_CONTRAT_STATUTS = ("brouillon", "envoye", "signe", "actif", "expire", "resilie")
VALID_TYPE_CONTRAT = ("standard", "premium", "pack_regional", "exclusif")
VALID_MODE_DEPASSEMENT = ("CPC", "CPM", "HYBRIDE")

VALID_PRODUCT_CODES = frozenset([
    "LOTO_FR", "LOTO_FR_A", "LOTO_FR_B",
    "EM_FR", "EM_FR_A", "EM_FR_B", "EM_EN", "EM_EN_A", "EM_EN_B",
    "EM_ES", "EM_ES_A", "EM_ES_B", "EM_PT", "EM_PT_A", "EM_PT_B",
    "EM_DE", "EM_DE_A", "EM_DE_B", "EM_NL", "EM_NL_A", "EM_NL_B",
])

VALID_TARIF_CODES = frozenset([
    "LOTO_FR_A", "LOTO_FR_B", "EM_FR_A", "EM_FR_B",
    "EM_EN_A", "EM_EN_B", "EM_ES_A", "EM_ES_B",
    "EM_PT_A", "EM_PT_B", "EM_DE_A", "EM_DE_B",
    "EM_NL_A", "EM_NL_B",
])

VALID_MODULES = {"loto", "euromillions"}
VALID_CATEGORIES = {"chatbot", "rating", "simulateur", "sponsor"}


# ══════════════════════════════════════════════════════════════════════════════
# PERIOD / REALTIME CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

PERIOD_SQL = {
    "today": "DATE(CONVERT_TZ(created_at, '+00:00', 'Europe/Paris')) = DATE(CONVERT_TZ(NOW(), '+00:00', 'Europe/Paris'))",
    "24h": "created_at >= NOW() - INTERVAL 24 HOUR",
    "week": "created_at >= NOW() - INTERVAL 7 DAY",
    "month": "created_at >= NOW() - INTERVAL 30 DAY",
}
PERIOD_LABELS = {"today": "Aujourd'hui", "24h": "24 dernieres heures",
                 "week": "7 derniers jours", "month": "30 derniers jours"}

CM_PERIOD_SQL = {
    "1h": "created_at >= NOW() - INTERVAL 1 HOUR",
    "6h": "created_at >= NOW() - INTERVAL 6 HOUR",
    "24h": "created_at >= NOW() - INTERVAL 24 HOUR",
    "7d": "created_at >= NOW() - INTERVAL 7 DAY",
    "30d": "created_at >= NOW() - INTERVAL 30 DAY",
}


# ══════════════════════════════════════════════════════════════════════════════
# ENGAGEMENT CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

ENGAGEMENT_EVENTS = frozenset([
    "chatbot-open", "chatbot-close", "chatbot-message",
    "rating-submitted", "rating-popup-shown", "rating-dismissed",
    "simulateur-grille-generated", "simulateur-grille-audited",
    "meta75-launched", "meta75-pdf-download",
])

EVENT_CATEGORIES = {
    "chatbot-open": "chatbot", "chatbot-close": "chatbot", "chatbot-message": "chatbot",
    "rating-submitted": "rating", "rating-popup-shown": "rating", "rating-dismissed": "rating",
    "simulateur-grille-generated": "simulateur", "simulateur-grille-audited": "simulateur",
    "meta75-launched": "sponsor", "meta75-pdf-download": "sponsor",
}


# ══════════════════════════════════════════════════════════════════════════════
# SPONSOR NAME RESOLVER
# ══════════════════════════════════════════════════════════════════════════════

SPONSORS_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "sponsors.json")
_sponsor_name_cache: dict | None = None


def load_sponsor_names() -> dict:
    """Build product_code → sponsor name map from sponsors.json. Cached."""
    global _sponsor_name_cache
    if _sponsor_name_cache is not None:
        return _sponsor_name_cache
    result = {}
    try:
        with open(SPONSORS_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for _slot_group in data.get("slots", {}).values():
            for slot in _slot_group.values():
                if isinstance(slot, dict) and "id" in slot:
                    result[slot["id"]] = slot.get("name", "Vacant")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("[ADMIN] sponsors.json load failed: %s", e)
    _sponsor_name_cache = result
    return result


# ══════════════════════════════════════════════════════════════════════════════
# TARIFS CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

PALIERS_V9 = [
    {"name": "Lancement", "impressions": "0 - 10 000", "tarif": "650\u20ac (gel)", "hausse": "\u2014"},
    {"name": "Croissance", "impressions": "10 001 - 40 000", "tarif": "815\u20ac", "hausse": "+25% max"},
    {"name": "Traction", "impressions": "40 001 - 100 000", "tarif": "1 020\u20ac", "hausse": "+25% max"},
    {"name": "Scale", "impressions": "100 001+", "tarif": "Sur mesure", "hausse": "Negocie"},
]


# ══════════════════════════════════════════════════════════════════════════════
# WHERE BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def build_impressions_where(period, date_start, date_end, event_type, lang, device, sponsor_id="", tarif=""):
    """Build WHERE clause + params for sponsor_impressions queries."""
    ds, de = period_to_dates(period, date_start, date_end)
    where = ["created_at >= %s", "created_at < %s"]
    params = [ds.isoformat(), de.isoformat()]
    if event_type and event_type in VALID_EVENTS:
        where.append("event_type = %s")
        params.append(event_type)
    if lang and lang in VALID_LANGS:
        where.append("lang = %s")
        params.append(lang)
    if device and device in VALID_DEVICES:
        where.append("device = %s")
        params.append(device)
    if sponsor_id and sponsor_id in VALID_SPONSORS:
        where.append("sponsor_id = %s")
        params.append(sponsor_id)
    if tarif and tarif in ("A", "B"):
        where.append("sponsor_id LIKE %s")
        params.append(f"%_{tarif}")
    return " AND ".join(where), params, ds, de


def build_votes_where(period, source, rating):
    """Build WHERE clause + params for ratings queries."""
    ds, de = period_to_dates(period)
    where = ["created_at >= %s", "created_at < %s"]
    params = [ds.isoformat(), de.isoformat()]
    if source and source in VALID_SOURCES:
        where.append("source = %s")
        params.append(source)
    if rating and rating.isdigit() and 1 <= int(rating) <= 5:
        where.append("rating = %s")
        params.append(int(rating))
    return " AND ".join(where), params, ds, de


def build_realtime_where(event_type: str, period: str):
    """Build WHERE clause + params for event_log realtime queries."""
    clauses = []
    params: list = []
    p = PERIOD_SQL.get(period, PERIOD_SQL["today"])
    clauses.append(p)
    if event_type != "all":
        clauses.append("event_type = %s")
        params.append(event_type)
    where = "WHERE " + " AND ".join(clauses)
    return where, params


def build_engagement_where(period, date_start, date_end, event_type, module, lang, device, category="", product_code=""):
    """Build WHERE clause + params for event_log engagement queries."""
    ds, de = period_to_dates(period, date_start, date_end)
    where = ["created_at >= %s", "created_at < %s", "event_type NOT LIKE 'sponsor-%%'"]
    params = [ds.isoformat(), de.isoformat()]
    if category and category in VALID_CATEGORIES:
        cat_events = [ev for ev, c in EVENT_CATEGORIES.items() if c == category]
        if cat_events:
            placeholders = ",".join(["%s"] * len(cat_events))
            where.append(f"event_type IN ({placeholders})")
            params.extend(cat_events)
    if event_type and event_type in ENGAGEMENT_EVENTS:
        where.append("event_type = %s")
        params.append(event_type)
    if module and module in VALID_MODULES:
        where.append("module = %s")
        params.append(module)
    if lang and lang in VALID_LANGS:
        where.append("lang = %s")
        params.append(lang)
    if device and device in VALID_DEVICES:
        where.append("device = %s")
        params.append(device)
    if product_code and product_code in VALID_PRODUCT_CODES:
        where.append("product_code = %s")
        params.append(product_code)
    return " AND ".join(where), params, ds, de


