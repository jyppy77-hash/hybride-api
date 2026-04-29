"""
Admin performance calendar — V136
==================================
Calendrier admin de tracking performance HYBRIDE vs FDJ.

À chaque tirage Loto/EuroMillions, visualiser les numéros proposés par le
moteur HYBRIDE (générateur V110 + top fréquences PDF META) et les comparer
avec le tirage officiel FDJ pour calibration et argument commercial sponsors.

Endpoints
---------
GET  /admin/calendar-perf                                    — page HTML
GET  /admin/api/calendar-perf/{game}/{year}/{month}          — calendrier mensuel
GET  /admin/api/calendar-perf/draw/{game}/{date_str}         — détail d'un tirage

Sources trackées (col `source` dans hybride_selection_history, V136 migration 026)
- generator      : grille canonique /api/{game}/generate (V110)
- pdf_meta_global: top 5 boules + top 1 secondary fenêtre Global (PDF META)
- pdf_meta_5a    : idem fenêtre 5 ans
- pdf_meta_2a    : idem fenêtre 2 ans

Auth: cookie session admin + IP whitelist (pattern V94 _require_auth*).
"""

import calendar
import logging
from datetime import date, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import db_cloudsql
from config.templates import env
from routes.admin_helpers import (
    require_auth as _require_auth,
    require_auth_json as _require_auth_json,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin", "calendar-perf"])


# Loto: lundi (0), mercredi (2), samedi (5)
# EM:   mardi  (1), vendredi  (4)
_DRAW_WEEKDAYS = {
    "loto": {0, 2, 5},
    "euromillions": {1, 4},
}
_GAME_TABLE = {
    "loto": "tirages",
    "euromillions": "tirages_euromillions",
}
_SOURCES = ("generator", "pdf_meta_global", "pdf_meta_5a", "pdf_meta_2a")


def _validate_game(game: str):
    if game not in ("loto", "euromillions"):
        return JSONResponse(
            {"error": "invalid_game", "expected": ["loto", "euromillions"]},
            status_code=400,
        )
    return None


def _calc_match(hybride_balls: list, hybride_secondary, fdj_balls: set, fdj_secondary: set) -> dict:
    """Compute matches between an HYBRIDE selection and the FDJ draw.

    Args:
        hybride_balls: list[int] — top 5 balls (or canonical 5 balls)
        hybride_secondary: int | None — chance (Loto) or star_top1 (EM) ; for EM
                           this is a single number even though FDJ draws 2 stars
        fdj_balls: set[int] — drawn balls
        fdj_secondary: set[int] — drawn chance/stars (Loto: {chance}, EM: {s1, s2})

    Returns:
        {"matches_balls": int, "matches_secondary": bool}
    """
    if not fdj_balls:
        return {"matches_balls": 0, "matches_secondary": False}
    matches_balls = len(set(int(n) for n in (hybride_balls or [])) & fdj_balls)
    matches_secondary = False
    if hybride_secondary is not None and fdj_secondary:
        matches_secondary = int(hybride_secondary) in fdj_secondary
    return {"matches_balls": matches_balls, "matches_secondary": matches_secondary}


# ──────────────────────────────────────────────────────────────────────
# Page HTML
# ──────────────────────────────────────────────────────────────────────


@router.get("/admin/calendar-perf", response_class=HTMLResponse, include_in_schema=False)
async def admin_perf_calendar_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/calendar_perf.html")
    resp = HTMLResponse(tpl.render(active="calendar-perf"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


# ──────────────────────────────────────────────────────────────────────
# API détail tirage — déclaré AVANT le mois pour éviter la collision de
# routes FastAPI : sans cette précaution, /draw/loto/2026-04-27 serait
# matché par /{game}/{year}/{month} avec game="draw" et echo 422 sur
# year=loto (int validation fail).
# ──────────────────────────────────────────────────────────────────────


@router.get("/admin/api/calendar-perf/draw/{game}/{date_str}", include_in_schema=False)
async def calendar_perf_draw_detail(request: Request, game: str, date_str: str):
    err = _require_auth_json(request)
    if err:
        return err
    invalid = _validate_game(game)
    if invalid:
        return invalid
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        return JSONResponse({"error": "invalid_date_format", "expected": "YYYY-MM-DD"}, status_code=400)

    table = _GAME_TABLE[game]

    # 1) FDJ
    fdj: dict = {"drawn": False, "balls": None, "secondary": None}
    try:
        async with db_cloudsql.get_connection_readonly() as conn:
            cur = await conn.cursor()
            if game == "loto":
                await cur.execute(
                    f"SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, "
                    f"numero_chance FROM {table} WHERE date_de_tirage = %s",
                    (target,),
                )
                row = await cur.fetchone()
                if row:
                    fdj = {
                        "drawn": True,
                        "balls": [row[f"boule_{i}"] for i in range(1, 6)],
                        "secondary": [row["numero_chance"]] if row["numero_chance"] is not None else [],
                        "drawn_at": str(row["date_de_tirage"]),
                    }
            else:
                await cur.execute(
                    f"SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, "
                    f"etoile_1, etoile_2 FROM {table} WHERE date_de_tirage = %s",
                    (target,),
                )
                row = await cur.fetchone()
                if row:
                    sec = sorted(x for x in (row["etoile_1"], row["etoile_2"]) if x is not None)
                    fdj = {
                        "drawn": True,
                        "balls": [row[f"boule_{i}"] for i in range(1, 6)],
                        "secondary": sec,
                        "drawn_at": str(row["date_de_tirage"]),
                    }
    except Exception:
        logger.error("[CALENDAR] FDJ detail fetch failed %s %s", game, date_str, exc_info=True)

    fdj_balls_set = set(fdj["balls"] or [])
    fdj_sec_set = set(fdj["secondary"] or [])

    # 2) HYBRIDE rows pour cette date — V136.A
    # Hotfix : pour source='generator', ne récupérer que les numéros enregistrés
    # à la même seconde que MIN(selected_at) — i.e. la 1ère grille canonique du
    # jour-cible. Cela évite l'union trompeuse de toutes les grilles générées
    # par tous les visiteurs (V136 affichait "42 boules cumulées EM" par exemple).
    # Pour les sources pdf_meta_*, l'agrégat top fréquences (V136 inchangé) est
    # sémantiquement correct car il s'agit déjà d'un top idempotent par jour.
    hybride: dict = {src: None for src in _SOURCES}
    rows: list = []
    first_ts = None
    try:
        async with db_cloudsql.get_connection_readonly() as conn:
            cur = await conn.cursor()
            # V136.A query 1 — timestamp de la 1ère génération canonique generator
            await cur.execute(
                "SELECT MIN(selected_at) AS first_ts "
                "FROM hybride_selection_history "
                "WHERE game = %s AND draw_date_target = %s AND source = 'generator'",
                (game, target),
            )
            first_row = await cur.fetchone()
            first_ts = first_row["first_ts"] if first_row else None

            # V136.A query 2 — rows filtrées
            if first_ts is not None:
                await cur.execute(
                    "SELECT source, number_value, number_type, "
                    "DATE_FORMAT(selected_at, '%%Y-%%m-%%d %%H:%%i:%%s') AS first_seen "
                    "FROM hybride_selection_history "
                    "WHERE game = %s AND draw_date_target = %s AND ("
                    "    (source = 'generator' AND selected_at >= %s "
                    "         AND selected_at < %s + INTERVAL 1 SECOND)"
                    "    OR source IN ('pdf_meta_global', 'pdf_meta_5a', 'pdf_meta_2a')"
                    ") "
                    "ORDER BY source, number_type, number_value",
                    (game, target, first_ts, first_ts),
                )
            else:
                # Pas de génération generator pour ce jour — pdf_meta_* uniquement
                await cur.execute(
                    "SELECT source, number_value, number_type, "
                    "DATE_FORMAT(selected_at, '%%Y-%%m-%%d %%H:%%i:%%s') AS first_seen "
                    "FROM hybride_selection_history "
                    "WHERE game = %s AND draw_date_target = %s "
                    "AND source IN ('pdf_meta_global', 'pdf_meta_5a', 'pdf_meta_2a') "
                    "ORDER BY source, number_type, number_value",
                    (game, target),
                )
            rows = await cur.fetchall()
        logger.info(
            "[CALENDAR] draw_detail game=%s date=%s first_ts=%s rows=%d",
            game, date_str, first_ts, len(rows),
        )

        buckets: dict = {}
        for r in rows:
            src = r["source"]
            bucket = buckets.setdefault(src, {"balls": [], "secondary": None, "first_seen": r["first_seen"]})
            if r["number_type"] == "ball":
                bucket["balls"].append(int(r["number_value"]))
            elif bucket["secondary"] is None:
                bucket["secondary"] = int(r["number_value"])
            # Conserver le first_seen le plus ancien
            if r["first_seen"] and (bucket["first_seen"] is None or r["first_seen"] < bucket["first_seen"]):
                bucket["first_seen"] = r["first_seen"]
        for src in _SOURCES:
            if src not in buckets:
                continue
            b = buckets[src]
            balls_sorted = sorted(b["balls"])
            m = _calc_match(balls_sorted, b["secondary"], fdj_balls_set, fdj_sec_set)
            hybride[src] = {
                "balls": balls_sorted,
                "secondary": b["secondary"],
                "matches_balls": m["matches_balls"] if fdj["drawn"] else None,
                "matches_secondary": m["matches_secondary"] if fdj["drawn"] else None,
                "first_seen": b["first_seen"],
            }
    except Exception:
        logger.error("[CALENDAR] hybride detail fetch failed %s %s", game, date_str, exc_info=True)

    # 3) Best match summary
    best_match_count = 0
    best_match_source = None
    if fdj["drawn"]:
        for src in _SOURCES:
            entry = hybride.get(src)
            if entry and entry["matches_balls"] is not None and entry["matches_balls"] > best_match_count:
                best_match_count = entry["matches_balls"]
                best_match_source = src

    return JSONResponse(
        {
            "game": game,
            "date": date_str,
            "fdj": fdj,
            "hybride": hybride,
            "summary": {
                "best_match_count": best_match_count if fdj["drawn"] else None,
                "best_match_source": best_match_source,
            },
        },
        headers={"Cache-Control": "no-store"},
    )


# ──────────────────────────────────────────────────────────────────────
# API mensuelle
# ──────────────────────────────────────────────────────────────────────


@router.get("/admin/api/calendar-perf/{game}/{year}/{month}", include_in_schema=False)
async def calendar_perf_month(request: Request, game: str, year: int, month: int):
    err = _require_auth_json(request)
    if err:
        return err
    invalid = _validate_game(game)
    if invalid:
        return invalid
    if year < 2025 or year > 2030:
        return JSONResponse({"error": "invalid_year"}, status_code=400)
    if month < 1 or month > 12:
        return JSONResponse({"error": "invalid_month"}, status_code=400)

    # Bornes du mois
    num_days = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, num_days)

    # 1) Jours de tirage candidats du mois
    draw_weekdays = _DRAW_WEEKDAYS[game]
    candidate_days: list[date] = []
    for d in range(1, num_days + 1):
        cur = date(year, month, d)
        if cur.weekday() in draw_weekdays:
            candidate_days.append(cur)

    if not candidate_days:
        return JSONResponse({
            "year": year, "month": month, "game": game, "draws": [],
        })

    # 2) FDJ : tirages réels du mois
    fdj_map: dict[date, dict] = {}
    table = _GAME_TABLE[game]
    try:
        async with db_cloudsql.get_connection_readonly() as conn:
            cur = await conn.cursor()
            if game == "loto":
                await cur.execute(
                    f"SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, "
                    f"numero_chance FROM {table} "
                    f"WHERE date_de_tirage BETWEEN %s AND %s",
                    (month_start, month_end),
                )
                rows = await cur.fetchall()
                for r in rows:
                    dt = r["date_de_tirage"]
                    if isinstance(dt, datetime):
                        dt = dt.date()
                    fdj_map[dt] = {
                        "balls": {r["boule_1"], r["boule_2"], r["boule_3"], r["boule_4"], r["boule_5"]},
                        "secondary": {r["numero_chance"]} if r["numero_chance"] is not None else set(),
                        "balls_list": [r[f"boule_{i}"] for i in range(1, 6)],
                        "secondary_list": [r["numero_chance"]] if r["numero_chance"] is not None else [],
                    }
            else:
                await cur.execute(
                    f"SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, "
                    f"etoile_1, etoile_2 FROM {table} "
                    f"WHERE date_de_tirage BETWEEN %s AND %s",
                    (month_start, month_end),
                )
                rows = await cur.fetchall()
                for r in rows:
                    dt = r["date_de_tirage"]
                    if isinstance(dt, datetime):
                        dt = dt.date()
                    sec = {x for x in (r["etoile_1"], r["etoile_2"]) if x is not None}
                    fdj_map[dt] = {
                        "balls": {r["boule_1"], r["boule_2"], r["boule_3"], r["boule_4"], r["boule_5"]},
                        "secondary": sec,
                        "balls_list": [r[f"boule_{i}"] for i in range(1, 6)],
                        "secondary_list": sorted(sec),
                    }
    except Exception:
        logger.error("[CALENDAR] FDJ fetch failed game=%s %s/%s", game, year, month, exc_info=True)

    # 3) HYBRIDE : rows hybride_selection_history pour le mois — V136.A
    # Hotfix : pour source='generator', filtrer par draw_date_target au timestamp
    # MIN(selected_at) (1ère grille canonique). Pour pdf_meta_*, agrégat
    # top fréquences inchangé (V136). Cf. calendar_perf_draw_detail pour la rationale.
    hybride_raw: dict[tuple, dict] = {}  # (date, source) → {"ball": [...], "secondary": int|None}
    rows_gen: list = []
    rows_pdf: list = []
    try:
        async with db_cloudsql.get_connection_readonly() as conn:
            cur = await conn.cursor()
            # V136.A query 1 — generator filtré par jour-cible au timestamp 1ère grille
            # (subquery JOIN : 1 MIN(selected_at) par draw_date_target).
            await cur.execute(
                "SELECT h.draw_date_target, h.source, h.number_value, h.number_type "
                "FROM hybride_selection_history h "
                "INNER JOIN ("
                "    SELECT draw_date_target, MIN(selected_at) AS first_ts "
                "    FROM hybride_selection_history "
                "    WHERE game = %s AND source = 'generator' "
                "    AND draw_date_target BETWEEN %s AND %s "
                "    GROUP BY draw_date_target"
                ") f ON h.draw_date_target = f.draw_date_target "
                "WHERE h.game = %s AND h.source = 'generator' "
                "AND h.selected_at >= f.first_ts "
                "AND h.selected_at < f.first_ts + INTERVAL 1 SECOND",
                (game, month_start, month_end, game),
            )
            rows_gen = await cur.fetchall()

            # V136.A query 2 — pdf_meta_* agrégat top fréquences (V136 inchangé)
            await cur.execute(
                "SELECT draw_date_target, source, number_value, number_type "
                "FROM hybride_selection_history "
                "WHERE game = %s "
                "AND source IN ('pdf_meta_global', 'pdf_meta_5a', 'pdf_meta_2a') "
                "AND draw_date_target BETWEEN %s AND %s",
                (game, month_start, month_end),
            )
            rows_pdf = await cur.fetchall()

        logger.info(
            "[CALENDAR] month_query game=%s month=%s rows_gen=%d rows_pdf=%d",
            game, f"{year}-{month:02d}", len(rows_gen), len(rows_pdf),
        )

        for r in list(rows_gen) + list(rows_pdf):
            dt = r["draw_date_target"]
            if isinstance(dt, datetime):
                dt = dt.date()
            key = (dt, r["source"])
            bucket = hybride_raw.setdefault(key, {"ball": [], "secondary": None})
            if r["number_type"] == "ball":
                bucket["ball"].append(int(r["number_value"]))
            else:
                # 'chance' (Loto) ou 'star' (EM) — top1 unique pour pdf_meta_*
                # ou single chance pour generator Loto / first star pour generator EM
                if bucket["secondary"] is None:
                    bucket["secondary"] = int(r["number_value"])
    except Exception:
        logger.error(
            "[CALENDAR] hybride history fetch failed game=%s %s/%s",
            game, year, month, exc_info=True,
        )

    # 4) Construire la liste des draws
    draws: list[dict] = []
    for d in candidate_days:
        fdj = fdj_map.get(d)
        fdj_drawn = fdj is not None
        fdj_balls = fdj["balls"] if fdj_drawn else set()
        fdj_secondary = fdj["secondary"] if fdj_drawn else set()

        stats: dict = {}
        best_match = 0
        for src in _SOURCES:
            sel = hybride_raw.get((d, src))
            if not sel or not sel["ball"]:
                stats[src] = None
                continue
            balls_sorted = sorted(sel["ball"])
            m = _calc_match(balls_sorted, sel["secondary"], fdj_balls, fdj_secondary)
            stats[src] = {
                "balls": balls_sorted,
                "secondary": sel["secondary"],
                "matches_balls": m["matches_balls"] if fdj_drawn else None,
                "matches_secondary": m["matches_secondary"] if fdj_drawn else None,
            }
            if fdj_drawn and m["matches_balls"] > best_match:
                best_match = m["matches_balls"]

        draws.append({
            "date": d.isoformat(),
            "weekday": d.weekday(),
            "fdj_drawn": fdj_drawn,
            "fdj_balls": fdj["balls_list"] if fdj_drawn else None,
            "fdj_secondary": fdj["secondary_list"] if fdj_drawn else None,
            "stats": stats,
            "best_match_count": best_match if fdj_drawn else None,
        })

    return JSONResponse(
        {"year": year, "month": month, "game": game, "draws": draws},
        headers={"Cache-Control": "no-store"},
    )
