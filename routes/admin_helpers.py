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
from zoneinfo import ZoneInfo

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
    # Contrat form validation
    "validate_contrat_form",
    # V121 — Pool impressions
    "IMPRESSION_EVENT_TYPES",
    "get_contract_impressions_consumed",
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
    from middleware.ip_ban import _is_owner_or_loopback
    from utils import get_client_ip
    real_ip = get_client_ip(request)
    # S09 V94: "testclient" = pytest TestClient → allow. Empty IP = block.
    if real_ip == "testclient":
        return None
    if not real_ip:
        logger.warning("[ADMIN_AUDIT] action=admin_empty_ip_blocked path=%s", request.url.path)
        return JSONResponse({"error": "Forbidden"}, status_code=403)
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

VALID_EVENTS = {"sponsor-popup-shown", "sponsor-click", "sponsor-video-played", "sponsor-inline-shown", "sponsor-result-shown", "sponsor-pdf-downloaded", "sponsor-pdf-mention"}
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


# ══════════════════════════════════════════════════════════════════════════════
# SAFE CONVERSIONS
# ══════════════════════════════════════════════════════════════════════════════

def _safe_int(value, default: int) -> int:
    """Safe int conversion — fallback to default on invalid input."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value, default: float) -> float:
    """Safe float conversion — fallback to default on invalid input."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


# ══════════════════════════════════════════════════════════════════════════════
# CONTRAT FORM VALIDATION (F04 V117: DRY refacto)
# ══════════════════════════════════════════════════════════════════════════════

def validate_contrat_form(form: dict) -> tuple[dict | None, str | None]:
    """Validate contrat form fields shared between create and update.

    Returns (validated_data, None) on success or (None, error_message) on failure.
    """
    sponsor_id = form.get("sponsor_id")
    if not sponsor_id:
        return None, "Le sponsor est obligatoire."

    type_contrat = form.get("type_contrat", "exclusif")
    if type_contrat not in VALID_TYPE_CONTRAT:
        type_contrat = "exclusif"

    # V9: product_codes stored as JSON array for backward compat
    raw_pc = form.get("product_codes", "LOTOIA_EXCLU")
    product_codes = f'["{raw_pc}"]' if raw_pc and not raw_pc.startswith("[") else (raw_pc or None)

    engagement_mois = _safe_int(form.get("engagement_mois", 3), 3)
    pool_impressions = _safe_int(form.get("pool_impressions", 10000), 10000)

    mode_dep = form.get("mode_depassement", "CPC")
    if mode_dep not in VALID_MODE_DEPASSEMENT:
        mode_dep = "CPC"

    plafond_raw = form.get("plafond_mensuel", "")
    plafond_mensuel = _safe_float(plafond_raw, 0) if plafond_raw else None

    montant_mensuel_ht = _safe_float(form.get("montant_mensuel_ht", 0), 0)
    if montant_mensuel_ht < 0:
        return None, "Le montant mensuel HT ne peut pas être négatif"
    if plafond_mensuel is not None and plafond_mensuel < 0:
        return None, "Le plafond mensuel ne peut pas être négatif"

    # S04 V93: validate dates server-side
    date_debut_str = (form.get("date_debut") or "").strip()
    date_fin_str = (form.get("date_fin") or "").strip()
    try:
        date_debut_val = date.fromisoformat(date_debut_str) if date_debut_str else None
    except ValueError:
        return None, "Date de début invalide (format attendu : AAAA-MM-JJ)"
    try:
        date_fin_val = date.fromisoformat(date_fin_str) if date_fin_str else None
    except ValueError:
        return None, "Date de fin invalide (format attendu : AAAA-MM-JJ)"
    if date_debut_val and date_fin_val and date_fin_val <= date_debut_val:
        return None, "La date de fin doit être postérieure à la date de début"

    return {
        "sponsor_id": _safe_int(sponsor_id, 0),
        "type_contrat": type_contrat,
        "product_codes": product_codes,
        "engagement_mois": engagement_mois,
        "pool_impressions": pool_impressions,
        "mode_depassement": mode_dep,
        "plafond_mensuel": plafond_mensuel,
        "montant_mensuel_ht": montant_mensuel_ht,
        "date_debut": date_debut_str or None,
        "date_fin": date_fin_str or None,
        "conditions_particulieres": form.get("conditions_particulieres", "") or None,
    }, None


# ══════════════════════════════════════════════════════════════════════════════
# V121 — POOL IMPRESSIONS CONSUMPTION
# ══════════════════════════════════════════════════════════════════════════════

_TZ_PARIS = ZoneInfo("Europe/Paris")

# 4 impression event_types (V121 semantic alignment)
IMPRESSION_EVENT_TYPES = (
    "sponsor-popup-shown",
    "sponsor-inline-shown",
    "sponsor-result-shown",
    "sponsor-pdf-mention",
)

_MONTHS_FR = [
    "", "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
]


async def get_contract_impressions_consumed(contrat: dict) -> dict:
    """Calculate impression pool consumption for a contract on the current calendar cycle.

    V121 — 4 impression types (popup + inline + result + pdf-mention).
    Cycle: calendar month (1st to last day, Europe/Paris timezone).
    V121: LOTOIA_EXCLU mono-annonceur — no sponsor_id filter needed.
    TODO V122: add sponsor_id mapping for multi-sponsor support.
    """
    import db_cloudsql

    quota = contrat.get("pool_impressions") or 10000
    mode = contrat.get("mode_depassement") or "HYBRIDE"

    # Cycle calendaire Europe/Paris — aware datetime
    now_paris = datetime.now(_TZ_PARIS)
    cycle_start = now_paris.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now_paris.month == 12:
        cycle_end = cycle_start.replace(year=now_paris.year + 1, month=1)
    else:
        cycle_end = cycle_start.replace(month=now_paris.month + 1)

    last_day = (cycle_end - timedelta(days=1)).day
    cycle_label = (
        f"1er au {last_day} {_MONTHS_FR[now_paris.month]} {now_paris.year}"
        f" — reset le 1er {_MONTHS_FR[cycle_end.month]} {cycle_end.year}"
    )
    next_month_label = f"{_MONTHS_FR[cycle_end.month]} {cycle_end.year}"

    # Naive strings for MySQL CONVERT_TZ('...', 'Europe/Paris', '+00:00')
    cycle_start_str = cycle_start.strftime("%Y-%m-%d %H:%M:%S")
    cycle_end_str = cycle_end.strftime("%Y-%m-%d %H:%M:%S")

    result = {
        "popup": 0, "inline": 0, "result": 0, "pdf_mention": 0,
        "total": 0, "quota": quota, "percent": 0.0,
        "status": "ok", "mode_depassement": mode, "surplus": 0,
        "cycle_start": cycle_start, "cycle_end": cycle_end,
        "cycle_label": cycle_label,
        "next_month_label": next_month_label,
    }

    try:
        # V121: LOTOIA_EXCLU mono-annonceur — all events belong to the single sponsor
        # V122: add WHERE sponsor_id filtering for multi-sponsor
        row = await db_cloudsql.async_fetchone(
            "SELECT "
            "  SUM(CASE WHEN event_type = 'sponsor-popup-shown'  THEN 1 ELSE 0 END) AS popup, "
            "  SUM(CASE WHEN event_type = 'sponsor-inline-shown' THEN 1 ELSE 0 END) AS inline_shown, "
            "  SUM(CASE WHEN event_type = 'sponsor-result-shown' THEN 1 ELSE 0 END) AS result_shown, "
            "  SUM(CASE WHEN event_type = 'sponsor-pdf-mention'  THEN 1 ELSE 0 END) AS pdf_mention "
            "FROM sponsor_impressions "
            "WHERE event_type IN ("
            "  'sponsor-popup-shown','sponsor-inline-shown',"
            "  'sponsor-result-shown','sponsor-pdf-mention'"
            ") "
            "AND created_at >= CONVERT_TZ(%s, 'Europe/Paris', '+00:00') "
            "AND created_at <  CONVERT_TZ(%s, 'Europe/Paris', '+00:00')",
            (cycle_start_str, cycle_end_str),
        )
        if row:
            result["popup"] = int(row["popup"] or 0)
            result["inline"] = int(row["inline_shown"] or 0)
            result["result"] = int(row["result_shown"] or 0)
            result["pdf_mention"] = int(row["pdf_mention"] or 0)
    except Exception as e:
        logger.error("[ADMIN] pool consumption query failed: %s", e)

    total = result["popup"] + result["inline"] + result["result"] + result["pdf_mention"]
    result["total"] = total
    result["surplus"] = max(0, total - quota)

    if quota > 0:
        result["percent"] = round(total / quota * 100, 1)

    pct = result["percent"]
    if pct >= 100:
        result["status"] = "exceeded"
    elif pct >= 90:
        result["status"] = "critical"
    elif pct >= 70:
        result["status"] = "warn"

    return result


