"""
Cycle 2A lot (b) — /loto/numeros-les-plus-sortis : valeurs rendues serveur (Release 1.6.053).

Structure HTML strictement intacte : seules les VALEURS du fichier source sont des marqueurs
__NPS_*__ (top 10, flop 10, top 5 Chance, total de tirages, année / mois de début, mentions
d'égalité dans les <p> existants). Aucun élément DOM ajouté ou retiré.

Sources : boules = services.stats_service.get_frequency_snapshot (même fonction, même tri et
même départage que /loto/statistiques et /api/stats/top-flop, via get_key_figures_snapshot) ;
Chance = get_secondary_snapshot (tirages au Chance NULL exclus, `pending` dans le cache et l'ETag).

Fallback (jamais d'exception vers la route, jamais de 500, jamais les anciennes valeurs) :
dernier jeu de données valide en mémoire du process (< 7 jours), sinon valeurs neutres « — ».
"""

import asyncio
import hashlib
import logging
import re
import time
from datetime import date

from babel.dates import format_date
from babel.numbers import format_decimal

from config.version import APP_VERSION
from services.loto_key_figures import (
    _fmt_date_long, _fmt_int, get_key_figures_snapshot, page_last_modified,
)
from services.stats_service import get_secondary_snapshot

logger = logging.getLogger(__name__)

PAGE_PATH = "/loto/numeros-les-plus-sortis"
DATE_MODIFIED_PLACEHOLDER = "__DATE_MODIFIED__"

TOP_SIZE = 10
CHANCE_SIZE = 5
FALLBACK_VALUE = "—"
FALLBACK_TOTAL = "plus de 1&nbsp;000"   # formulation d'avant le lot (Chantier A, 1.6.050)
FALLBACK_FIRST_YEAR = "2019"
FALLBACK_FIRST_MONTH_YEAR = "novembre 2019"

_LAST_GOOD_MAX_AGE_S = 7 * 24 * 3600
_SNAPSHOT_TIMEOUT_S = 2.0
_NEGATIVE_TTL_S = 30.0
_DEFAULT_LOCALE = "fr_FR"

_RE_TOKEN = re.compile(r"__NPS_[A-Z0-9_]+__")
# Ligne dateModified (dernière propriété de l'objet Article) retirée AVEC la virgule qui la précède.
_RE_DATE_MODIFIED_LINE = re.compile(r',\r?\n[ \t]*"dateModified": "__DATE_MODIFIED__"')

_chance_unavailable_until = 0.0
_last_good: dict[str, tuple[dict, float]] = {}   # "main" | "chance" → (snapshot, time.monotonic())


# ──────────────────────────────────────
# Données (jamais d'exception)
# ──────────────────────────────────────

async def _get_chance_snapshot() -> dict | None:
    """Snapshot Chance avec timeout 2 s + cache négatif 30 s. None si indisponible."""
    global _chance_unavailable_until
    if time.monotonic() < _chance_unavailable_until:
        return None
    try:
        return await asyncio.wait_for(get_secondary_snapshot(), timeout=_SNAPSHOT_TIMEOUT_S)
    except Exception as e:
        _chance_unavailable_until = time.monotonic() + _NEGATIVE_TTL_S
        logger.warning("[TOP-NUMBERS] snapshot Chance indisponible (%s: %s)", type(e).__name__, e)
        return None


def _with_last_good(kind: str, snap: dict | None) -> dict | None:
    """Mémorise le dernier snapshot valide ; le ressert (< 7 jours) si le snapshot du moment manque."""
    now = time.monotonic()
    if snap:
        _last_good[kind] = (snap, now)
        return snap
    kept = _last_good.get(kind)
    if kept and now - kept[1] < _LAST_GOOD_MAX_AGE_S:
        logger.warning("[TOP-NUMBERS] %s : dernier snapshot valide resservi (tirage du %s)",
                       kind, kept[0].get("last_draw"))
        return kept[0]
    return None


async def get_top_numbers_data() -> dict:
    """{"main": snapshot boules | None, "chance": snapshot Chance | None}."""
    main = await get_key_figures_snapshot()
    chance = await _get_chance_snapshot()
    return {"main": _with_last_good("main", main), "chance": _with_last_good("chance", chance)}


# ──────────────────────────────────────
# Formatage (formats de la page : « 12,2% » sans espace)
# ──────────────────────────────────────

def _fmt_pct_page(count: int, total: int, locale: str) -> str:
    return format_decimal(100 * count / total, format="#,##0.0", locale=locale) + "%"


def _fmt_month_year(iso: str, locale: str) -> str:
    """« novembre 2019 »."""
    return format_date(date.fromisoformat(iso), format="MMMM y", locale=locale)


def build_tie_note(ranking: list[dict], size: int, locale: str = _DEFAULT_LOCALE) -> str:
    """Mention d'égalité à la dernière place du tableau, préfixée d'une espace ; '' si aucune."""
    last = ranking[size - 1]["count"]
    extra = [d["number"] for d in ranking[size:] if d["count"] == last]
    if not extra:
        return ""
    label = "numéro" if len(extra) == 1 else "numéros"
    nums = ", ".join(str(n) for n in extra)
    return f" À égalité avec le {size}e ({_fmt_int(last, locale)} sorties) : {label} {nums}."


def _table_values(prefix: str, ranking: list[dict], size: int, total: int, locale: str) -> dict:
    values = {}
    for rank, d in enumerate(ranking[:size], start=1):
        values[f"__NPS_{prefix}_{rank}_N__"] = str(d["number"])
        values[f"__NPS_{prefix}_{rank}_C__"] = _fmt_int(d["count"], locale)
        values[f"__NPS_{prefix}_{rank}_P__"] = _fmt_pct_page(d["count"], total, locale)
    values[f"__NPS_{prefix}_TIE__"] = build_tie_note(ranking, size, locale)
    return values


def build_values(data: dict, locale: str = _DEFAULT_LOCALE) -> dict:
    """Marqueur → valeur. Les marqueurs absents (données indisponibles) prennent la valeur neutre."""
    values = {}
    main, chance = data.get("main"), data.get("chance")
    if main:
        total = main["total_draws"]
        values["__NPS_TOTAL__"] = _fmt_int(total, locale)
        values["__NPS_FIRST_YEAR__"] = main["first_draw"][:4]
        values["__NPS_FIRST_MONTH_YEAR__"] = _fmt_month_year(main["first_draw"], locale)
        values.update(_table_values("TOP", main["top"], TOP_SIZE, total, locale))
        values.update(_table_values("FLOP", main["flop"], TOP_SIZE, total, locale))
    if chance and chance.get("draws"):
        values.update(_table_values("CH", chance["ranking"], CHANCE_SIZE, chance["draws"], locale))
    return values


def _fallback_value(token: str) -> str:
    if token == "__NPS_TOTAL__":
        return FALLBACK_TOTAL
    if token == "__NPS_FIRST_YEAR__":
        return FALLBACK_FIRST_YEAR
    if token == "__NPS_FIRST_MONTH_YEAR__":
        return FALLBACK_FIRST_MONTH_YEAR
    if token.endswith("_TIE__"):
        return ""
    return FALLBACK_VALUE


def render_top_numbers(page_html: str, data: dict, locale: str = _DEFAULT_LOCALE) -> str:
    """Remplace chaque marqueur par sa valeur (ou la valeur neutre) + dateModified = dernier tirage
    (ligne retirée si aucune donnée). Aucun marqueur ne peut survivre au rendu."""
    values = build_values(data, locale)
    page_html = _RE_TOKEN.sub(lambda m: values.get(m.group(0), _fallback_value(m.group(0))), page_html)
    main = data.get("main")
    if main:
        return page_html.replace(DATE_MODIFIED_PLACEHOLDER, main["last_draw"], 1)
    return _RE_DATE_MODIFIED_LINE.sub("", page_html, count=1)


# ──────────────────────────────────────
# En-têtes HTTP (ETag / Last-Modified)
# ──────────────────────────────────────

def page_etag(data: dict) -> str:
    """ETag lié aux données servies (période, total, `pending` Chance). Sans aucune donnée :
    ETag par version, identique au middleware."""
    base = f"{APP_VERSION}:{PAGE_PATH}"
    main, chance = data.get("main"), data.get("chance")
    if main:
        base += f":{main['first_draw']}:{main['last_draw']}:{main['total_draws']}"
    if chance:
        base += f":chance:{chance['last_draw']}:{chance['total_draws']}:{chance['pending']}"
    elif main:
        base += ":chance:none"
    return f'"{hashlib.md5(base.encode()).hexdigest()}"'


def page_last_modified_for(data: dict) -> str:
    """Date du dernier tirage servi (boules, sinon Chance) ; sans donnée : calcul du middleware."""
    return page_last_modified(data.get("main") or data.get("chance"))
