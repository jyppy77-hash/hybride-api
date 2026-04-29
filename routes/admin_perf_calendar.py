"""
Admin performance calendar — V136 / V136.A / V136.B / V137
===========================================================
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

V137 — Multi-grilles via grid_id (UUID) :
- Détail tirage : retourne `data.grids: list[]` (chaque grille individuelle
  avec son grid_id, son timestamp, ses 5+1 numéros, ses matchs propres).
- Mois : `best_match_count` du jour = MAX(matches) parmi toutes les grilles.
- Rows legacy V136.A (grid_id=NULL) : agrégées par (date, source) en 1 grille
  fictive `grid_id = "_legacy_<game>_<date>_<source>"` avec flag `is_legacy=true`.

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

    # 2) HYBRIDE rows multi-grilles — V137
    # Récupérer toutes les rows du jour-cible et grouper par grid_id pour
    # reconstruire chaque grille individuelle.
    # Rows legacy (grid_id=NULL, ~200 rows pre-V137) : agrégées par source
    # avec grid_id virtuel "_legacy_<game>_<date>_<source>" + is_legacy=true.
    grids_list: list = []
    try:
        async with db_cloudsql.get_connection_readonly() as conn:
            cur = await conn.cursor()
            await cur.execute(
                "SELECT grid_id, source, number_value, number_type, "
                "DATE_FORMAT(selected_at, '%%Y-%%m-%%d %%H:%%i:%%s') AS first_seen "
                "FROM hybride_selection_history "
                "WHERE game = %s AND draw_date_target = %s "
                "ORDER BY selected_at ASC, grid_id, number_type, number_value",
                (game, target),
            )
            rows = await cur.fetchall()

        logger.info(
            "[CALENDAR] draw_detail game=%s date=%s rows=%d",
            game, date_str, len(rows),
        )

        # Pivot par (grid_id, source) — legacy rows fusionnées par (source) avec
        # grid_id synthétique stable.
        buckets: dict = {}
        for r in rows:
            gid = r["grid_id"]
            src = r["source"]
            is_legacy = gid is None
            if is_legacy:
                gid = f"_legacy_{game}_{date_str}_{src}"
            key = (gid, src)
            bucket = buckets.setdefault(key, {
                "grid_id": gid,
                "source": src,
                "balls": [],
                "secondary": None,
                "first_seen": r["first_seen"],
                "is_legacy": is_legacy,
            })
            if r["number_type"] == "ball":
                bucket["balls"].append(int(r["number_value"]))
            elif bucket["secondary"] is None:
                bucket["secondary"] = int(r["number_value"])
            # Conserver le first_seen le plus ancien
            if r["first_seen"] and (bucket["first_seen"] is None or r["first_seen"] < bucket["first_seen"]):
                bucket["first_seen"] = r["first_seen"]

        # Construire la liste finale : trier par (source generator first, first_seen ASC)
        for b in buckets.values():
            b["balls"] = sorted(b["balls"])
            if fdj["drawn"]:
                m = _calc_match(b["balls"], b["secondary"], fdj_balls_set, fdj_sec_set)
                b["matches_balls"] = m["matches_balls"]
                b["matches_secondary"] = m["matches_secondary"]
            else:
                b["matches_balls"] = None
                b["matches_secondary"] = None
            grids_list.append(b)

        grids_list.sort(key=lambda x: (
            x["source"] != "generator",
            x["first_seen"] or "",
            x["grid_id"] or "",
        ))
    except Exception:
        logger.error("[CALENDAR] hybride detail fetch failed %s %s", game, date_str, exc_info=True)

    # 3) Best match summary
    best_match_count = 0
    best_match_grid_id = None
    if fdj["drawn"]:
        for g in grids_list:
            if g["matches_balls"] is not None and g["matches_balls"] > best_match_count:
                best_match_count = g["matches_balls"]
                best_match_grid_id = g["grid_id"]

    return JSONResponse(
        {
            "game": game,
            "date": date_str,
            "fdj": fdj,
            "grids": grids_list,
            "summary": {
                "total_grids": len(grids_list),
                "best_match_count": best_match_count if fdj["drawn"] else None,
                "best_match_grid_id": best_match_grid_id,
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

    # 3) HYBRIDE : toutes les rows du mois — V137
    # Pivot par (date, grid_id, source) puis calc match par grille → best_match_count
    # du jour = MAX(matches) parmi toutes les grilles du jour. Les rows legacy
    # (grid_id=NULL) sont agrégées par (date, source) sous un grid_id synthétique.
    grids_by_day: dict = {}  # date → list of {"source", "balls": [], "secondary": int}
    try:
        async with db_cloudsql.get_connection_readonly() as conn:
            cur = await conn.cursor()
            await cur.execute(
                "SELECT draw_date_target, grid_id, source, number_value, number_type, "
                "DATE_FORMAT(selected_at, '%%Y-%%m-%%d %%H:%%i:%%s') AS first_seen "
                "FROM hybride_selection_history "
                "WHERE game = %s AND draw_date_target BETWEEN %s AND %s "
                "ORDER BY selected_at ASC",
                (game, month_start, month_end),
            )
            rows = await cur.fetchall()

        logger.info(
            "[CALENDAR] month_query game=%s month=%s rows=%d",
            game, f"{year}-{month:02d}", len(rows),
        )

        # Pivot : (date, grid_id, source) → grille
        buckets: dict = {}
        for r in rows:
            dt = r["draw_date_target"]
            if isinstance(dt, datetime):
                dt = dt.date()
            gid = r["grid_id"]
            src = r["source"]
            if gid is None:
                gid = f"_legacy_{game}_{dt.isoformat()}_{src}"
            key = (dt, gid, src)
            b = buckets.setdefault(key, {
                "date": dt, "source": src,
                "balls": [], "secondary": None,
            })
            if r["number_type"] == "ball":
                b["balls"].append(int(r["number_value"]))
            elif b["secondary"] is None:
                b["secondary"] = int(r["number_value"])

        for b in buckets.values():
            grids_by_day.setdefault(b["date"], []).append(b)
    except Exception:
        logger.error(
            "[CALENDAR] hybride history fetch failed game=%s %s/%s",
            game, year, month, exc_info=True,
        )

    # 4) Construire la liste des draws — best_match_count = MAX(matches) du jour
    draws: list[dict] = []
    for d in candidate_days:
        fdj = fdj_map.get(d)
        fdj_drawn = fdj is not None
        fdj_balls = fdj["balls"] if fdj_drawn else set()
        fdj_secondary = fdj["secondary"] if fdj_drawn else set()

        day_grids = grids_by_day.get(d, [])
        best_match = 0
        if fdj_drawn:
            for g in day_grids:
                m = _calc_match(sorted(g["balls"]), g["secondary"], fdj_balls, fdj_secondary)
                if m["matches_balls"] > best_match:
                    best_match = m["matches_balls"]

        draws.append({
            "date": d.isoformat(),
            "weekday": d.weekday(),
            "fdj_drawn": fdj_drawn,
            "fdj_balls": fdj["balls_list"] if fdj_drawn else None,
            "fdj_secondary": fdj["secondary_list"] if fdj_drawn else None,
            "total_grids": len(day_grids),
            "best_match_count": best_match if fdj_drawn else None,
        })

    return JSONResponse(
        {"year": year, "month": month, "game": game, "draws": draws},
        headers={"Cache-Control": "no-store"},
    )
