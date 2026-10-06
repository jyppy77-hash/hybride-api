"""
Cycle 2A Phase 1B — bloc « Statistiques du Loto : les chiffres clés » rendu serveur
sur /loto/statistiques (top 5 / flop 5, total tirages, dernier tirage, dateModified).

Source unique : services.stats_service.get_frequency_snapshot (même fonction que
/api/stats/top-flop). Jamais d'exception vers la route : snapshot indisponible → None
→ bloc retiré, dateModified retiré, ETag/Last-Modified identiques au middleware.
"""

import asyncio
import calendar
import hashlib
import html
import logging
import re
import time
from datetime import date, datetime
from email.utils import formatdate

from babel.dates import format_date
from babel.numbers import format_decimal

from config.version import APP_VERSION, LAST_DEPLOY_DATE
from services.stats_service import get_frequency_snapshot

logger = logging.getLogger(__name__)

PAGE_PATH = "/loto/statistiques"
KEY_FIGURES_MARKER = "<!--__KEY_FIGURES__-->"
DATE_MODIFIED_PLACEHOLDER = "__DATA_DATE_MODIFIED__"
CACHE_CONTROL = "private, max-age=3600"  # identique au middleware (V123.1)

# Valeur statique du fichier = fallback (snapshot None) ; remplacée par "{first}/{last}" sinon.
TEMPORAL_COVERAGE_FALLBACK = '"temporalCoverage": "2019-11-06/.."'

_RE_DATE_MODIFIED_LINE = re.compile(r'^[ \t]*"dateModified": "__DATA_DATE_MODIFIED__",\r?\n', re.M)

_SNAPSHOT_TIMEOUT_S = 2.0
_NEGATIVE_TTL_S = 30.0
_TABLE_SIZE = 5
_MAX_NAMED_TIES = 3
_DEFAULT_LOCALE = "fr_FR"

_unavailable_until = 0.0  # cache négatif in-process (DB down → pas 2 s d'attente par hit)


# ──────────────────────────────────────
# Snapshot (jamais d'exception)
# ──────────────────────────────────────

async def get_key_figures_snapshot() -> dict | None:
    """Snapshot fréquences avec timeout 2 s + cache négatif 30 s. None si indisponible."""
    global _unavailable_until
    if time.monotonic() < _unavailable_until:
        return None
    try:
        return await asyncio.wait_for(get_frequency_snapshot(), timeout=_SNAPSHOT_TIMEOUT_S)
    except Exception as e:
        _unavailable_until = time.monotonic() + _NEGATIVE_TTL_S
        logger.warning("[KEY-FIGURES] snapshot indisponible (%s: %s) — bloc masqué",
                       type(e).__name__, e)
        return None


# ──────────────────────────────────────
# Formatage (locale paramétrable)
# ──────────────────────────────────────

def _fmt_int(n: int, locale: str) -> str:
    return format_decimal(n, locale=locale)


def _fmt_pct(count: int, total: int, locale: str) -> str:
    return format_decimal(100 * count / total, format="#,##0.0", locale=locale) + " %"


def _fmt_date_full(iso: str, locale: str) -> str:
    """Avec jour de la semaine : « lundi 5 octobre 2026 »."""
    return format_date(date.fromisoformat(iso), format="full", locale=locale)


def _fmt_date_long(iso: str, locale: str) -> str:
    """Sans jour de la semaine : « 6 novembre 2019 »."""
    return format_date(date.fromisoformat(iso), format="long", locale=locale)


def _join_numbers(numbers: list[int]) -> str:
    """[7] → '7' ; [7, 34] → '7 et 34' ; [7, 34, 3] → '7, 34 et 3'."""
    parts = [str(n) for n in numbers]
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " et " + parts[-1]


def _leaders(ranking: list[dict]) -> tuple[list[int], int]:
    """Numéros à égalité en tête du classement fourni (déjà trié) + leur nombre de sorties."""
    head = ranking[0]["count"]
    return [d["number"] for d in ranking if d["count"] == head], head


def _ties_beyond_fifth(ranking: list[dict]) -> tuple[list[int], int]:
    """Numéros hors tableau (rang > 5) à égalité avec la 5e ligne."""
    fifth = ranking[_TABLE_SIZE - 1]["count"]
    return [d["number"] for d in ranking[_TABLE_SIZE:] if d["count"] == fifth], fifth


# ──────────────────────────────────────
# Textes FR
# ──────────────────────────────────────

def _top_clause(numbers: list[int], count: str) -> str:
    if len(numbers) == 1:
        return f"le numéro {numbers[0]} est le plus sorti ({count} fois)"
    if len(numbers) <= _MAX_NAMED_TIES:
        return f"les numéros {_join_numbers(numbers)} sont les plus sortis ({count} fois chacun)"
    return f"plusieurs numéros sont à égalité en tête ({count} fois)"


def _flop_clause(numbers: list[int], count: str) -> str:
    if len(numbers) == 1:
        return f"le numéro {numbers[0]} le moins sorti ({count} fois)"
    if len(numbers) <= _MAX_NAMED_TIES:
        return f"les numéros {_join_numbers(numbers)} sont les moins sortis ({count} fois chacun)"
    return f"plusieurs numéros sont à égalité en queue ({count} fois)"


def build_intro(snap: dict, locale: str = _DEFAULT_LOCALE) -> str:
    """Intro dynamique (texte brut, non échappé)."""
    top_nums, top_count = _leaders(snap["top"])
    flop_nums, flop_count = _leaders(snap["flop"])
    return (
        f"Ces statistiques portent sur {_fmt_int(snap['total_draws'], locale)} tirages du Loto "
        f"analysés depuis le {_fmt_date_long(snap['first_draw'], locale)} : "
        f"{_top_clause(top_nums, _fmt_int(top_count, locale))} et "
        f"{_flop_clause(flop_nums, _fmt_int(flop_count, locale))}. "
        f"Données mises à jour après le tirage du {_fmt_date_full(snap['last_draw'], locale)}."
    )


def build_tie_note(ranking: list[dict], locale: str = _DEFAULT_LOCALE) -> str | None:
    """Mention d'égalité à la 5e place (texte brut) ou None si aucune égalité ne la traverse."""
    extra, fifth = _ties_beyond_fifth(ranking)
    if not extra:
        return None
    label = "numéro" if len(extra) == 1 else "numéros"
    nums = ", ".join(str(n) for n in extra)
    return f"À égalité avec le 5e ({_fmt_int(fifth, locale)} sorties) : {label} {nums}."


# ──────────────────────────────────────
# HTML
# ──────────────────────────────────────

def _table_html(caption: str, ranking: list[dict], css: str, total: int, locale: str) -> str:
    rows = "\n".join(
        f'                        <tr><td class="rank">{rank}</td>'
        f'<th scope="row" class="num {css}">{d["number"]}</th>'
        f'<td>{_fmt_int(d["count"], locale)}</td>'
        f'<td>{_fmt_pct(d["count"], total, locale)}</td></tr>'
        for rank, d in enumerate(ranking[:_TABLE_SIZE], start=1)
    )
    tie = build_tie_note(ranking, locale)
    tie_html = f'\n                <p class="key-figures-tie">{html.escape(tie)}</p>' if tie else ""
    return (
        '            <div class="key-figures-col">\n'
        '                <table class="freq-table">\n'
        f'                    <caption>{html.escape(caption)}</caption>\n'
        '                    <thead><tr><th scope="col">Rang</th><th scope="col">Numéro</th>'
        '<th scope="col">Sorties</th><th scope="col">Fréquence</th></tr></thead>\n'
        '                    <tbody>\n'
        f'{rows}\n'
        '                    </tbody>\n'
        '                </table>'
        f'{tie_html}\n'
        '            </div>'
    )


def build_key_figures_html(snap: dict, locale: str = _DEFAULT_LOCALE) -> str:
    """Section HTML complète du bloc « chiffres clés »."""
    total = snap["total_draws"]
    last_iso = html.escape(snap["last_draw"])
    return (
        '<section class="key-figures" aria-labelledby="key-figures-title">\n'
        '            <h2 id="key-figures-title">Statistiques du Loto : les chiffres clés</h2>\n'
        f'            <p class="key-figures-intro">{html.escape(build_intro(snap, locale))}</p>\n'
        '            <dl class="key-figures-meta">\n'
        f'                <div><dt>Tirages analysés</dt><dd>{_fmt_int(total, locale)}</dd></div>\n'
        f'                <div><dt>Dernier tirage</dt><dd><time datetime="{last_iso}">'
        f'{html.escape(_fmt_date_full(snap["last_draw"], locale))}</time></dd></div>\n'
        f'                <div><dt>Période</dt><dd>depuis le <time datetime="{html.escape(snap["first_draw"])}">'
        f'{html.escape(_fmt_date_long(snap["first_draw"], locale))}</time></dd></div>\n'
        '            </dl>\n'
        '            <div class="key-figures-tables">\n'
        f'{_table_html("Top 5 des numéros les plus sortis", snap["top"], "hot", total, locale)}\n'
        f'{_table_html("Flop 5 des numéros les moins sortis", snap["flop"], "cold", total, locale)}\n'
        '            </div>\n'
        '            <p class="key-figures-note">Fréquence = sorties ÷ tirages. Fréquence théorique : '
        f'{_fmt_pct(5, 49, locale)} (5/49). Données descriptives, sans valeur prédictive. '
        '<a href="/loto/numeros-les-plus-sortis">Voir le classement complet des 49 numéros</a></p>\n'
        '        </section>'
    )


def render_key_figures(page_html: str, snap: dict | None, locale: str = _DEFAULT_LOCALE) -> str:
    """Injecte bloc + dateModified + temporalCoverage ; fallback (snap None) : retire marqueur et
    ligne dateModified, temporalCoverage statique conservé."""
    if snap:
        page_html = page_html.replace(KEY_FIGURES_MARKER, build_key_figures_html(snap, locale), 1)
        page_html = page_html.replace(
            TEMPORAL_COVERAGE_FALLBACK,
            f'"temporalCoverage": "{snap["first_draw"]}/{snap["last_draw"]}"', 1,
        )
        return page_html.replace(DATE_MODIFIED_PLACEHOLDER, snap["last_draw"], 1)
    page_html = page_html.replace(KEY_FIGURES_MARKER, "", 1)
    return _RE_DATE_MODIFIED_LINE.sub("", page_html, count=1)


# ──────────────────────────────────────
# En-têtes HTTP (ETag / Last-Modified / If-None-Match)
# ──────────────────────────────────────

def page_etag(snap: dict | None) -> str:
    """Snapshot : ETag lié aux données. Fallback : ETag par version, identique au middleware."""
    base = f"{APP_VERSION}:{PAGE_PATH}"
    if snap:
        base += f":{snap['first_draw']}:{snap['last_draw']}:{snap['total_draws']}"
    return f'"{hashlib.md5(base.encode()).hexdigest()}"'


def page_last_modified(snap: dict | None) -> str:
    """HTTP-date GMT. Snapshot : date du dernier tirage (minuit UTC). Fallback : calcul du middleware."""
    if snap:
        stamp = calendar.timegm(date.fromisoformat(snap["last_draw"]).timetuple())
    else:
        stamp = time.mktime(datetime.strptime(LAST_DEPLOY_DATE, "%Y-%m-%d").timetuple())
    return formatdate(timeval=stamp, localtime=False, usegmt=True)


def if_none_match_hit(header: str | None, etag: str) -> bool:
    """If-None-Match : liste séparée par virgules, préfixe faible W/ ignoré, '*' accepté."""
    if not header:
        return False
    for token in header.split(","):
        token = token.strip()
        if token == "*":
            return True
        if token.startswith("W/"):
            token = token[2:]
        if token == etag:
            return True
    return False
