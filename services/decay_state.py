"""
Decay state persistence for HYBRIDE engine.
Tracks consecutive misses per number to enable score decay
and break kernel lock (same numbers selected N draws in a row).

Table: hybride_decay_state
Pipeline position: READ-ONLY during scoring (step 4, AFTER penalization, BEFORE anti-collision).
WRITE only on new real draw import (check_and_update_decay / update_decay_after_draw).

Architecture (V94 hotfix):
    - Scoring pipeline (generate_grids, chatbot Phase G, API /generate) → READ ONLY (get_decay_state)
    - New real draw detected → WRITE (check_and_update_decay auto-detects, or update_decay_after_draw manual)
    - Admin route /admin/api/decay/update → manual trigger

Note (V93 F07): Python API uses "consecutive_selections" in some comments — the SQL column
is "consecutive_misses" (no migration). This module always uses the SQL column name in queries.
"""

import logging
from datetime import date

logger = logging.getLogger(__name__)


# ── Pure function (no DB) ────────────────────────────────────────────

def calculate_decay_multiplier(
    consecutive_selections: int,
    decay_rate: float = 0.10,
    floor: float = 0.50,
    acceleration: float = 0.03,
) -> float:
    """Calculate accelerated decay multiplier based on consecutive selections.

    A "selection" is each time the engine picks a number without it appearing
    in a real draw. The more a number is selected consecutively, the more its
    score decays — forcing rotation.

    Formula: max(floor, 1.0 - (consecutive_selections * decay_rate * accel_factor))
    where accel_factor = 1.0 + (consecutive_selections * acceleration).

    V92 calibration — rate 0.05→0.10, acceleration 0.03 added.

    Examples with decay_rate=0.10, floor=0.50, acceleration=0.03:
        0 selections → 1.000 (no penalty)
        1 selection  → 0.897
        2 selections → 0.788
        3 selections → 0.673
        4 selections → 0.552
        5 selections → 0.500 (floor)
    """
    if consecutive_selections <= 0:
        return 1.0
    accel_factor = 1.0 + (consecutive_selections * acceleration)
    decay = 1.0 - (consecutive_selections * decay_rate * accel_factor)
    return max(floor, decay)


# ── Async DB access — READ (used by scoring pipeline) ───────────────

async def get_decay_state(
    conn, game: str, number_type: str = "ball",
) -> dict[int, int]:
    """Return {number_value: consecutive_misses} for a game and type.

    Returns {} if the table is empty (first launch) or on error.
    Graceful degradation: never raises — returns empty dict on failure.

    READ-ONLY — safe to call from scoring pipeline, API, chatbot.
    """
    try:
        cursor = await conn.cursor()
        await cursor.execute(
            "SELECT number_value, consecutive_misses "
            "FROM hybride_decay_state "
            "WHERE game = %s AND number_type = %s",
            (game, number_type),
        )
        rows = await cursor.fetchall()
        return {row["number_value"]: row["consecutive_misses"] for row in rows}
    except Exception:
        logger.warning("get_decay_state failed for %s/%s — returning empty", game, number_type)
        return {}


# ── Async DB access — WRITE (called on new real draw ONLY) ──────────

async def update_decay_after_draw(
    conn,
    game: str,
    drawn_balls: list[int],
    drawn_stars: list[int] | None = None,
) -> dict:
    """Update decay state after a real draw is imported.

    Called ONCE per real draw — NOT from the scoring pipeline.

    Logic:
    - Numbers that appeared in the draw → reset consecutive_misses=0, set last_drawn=draw date
    - ALL other numbers already tracked → consecutive_misses += 1 (they missed this draw)

    Returns summary dict {reset: int, incremented: int, game: str}.
    """
    today = date.today().isoformat()
    reset_count = 0
    incremented_count = 0
    try:
        cursor = await conn.cursor()

        # 1. Reset drawn balls: consecutive_misses=0, last_drawn=today
        for num in drawn_balls:
            await cursor.execute(
                "INSERT INTO hybride_decay_state "
                "(game, number_type, number_value, consecutive_misses, last_drawn, last_played) "
                "VALUES (%s, 'ball', %s, 0, %s, %s) "
                "ON DUPLICATE KEY UPDATE "
                "consecutive_misses = 0, last_drawn = %s, updated_at = NOW()",
                (game, num, today, today, today),
            )
            reset_count += 1

        # 2. Increment all OTHER tracked balls (they missed this draw)
        if drawn_balls:
            placeholders = ",".join(["%s"] * len(drawn_balls))
            await cursor.execute(
                "UPDATE hybride_decay_state "
                "SET consecutive_misses = consecutive_misses + 1, updated_at = NOW() "
                "WHERE game = %s AND number_type = 'ball' "
                f"AND number_value NOT IN ({placeholders})",
                (game, *drawn_balls),
            )
            incremented_count += cursor.rowcount

        # 3. Reset drawn stars/chance
        if drawn_stars:
            ntype = "star" if game == "euromillions" else "chance"
            for s in drawn_stars:
                await cursor.execute(
                    "INSERT INTO hybride_decay_state "
                    "(game, number_type, number_value, consecutive_misses, last_drawn, last_played) "
                    "VALUES (%s, %s, %s, 0, %s, %s) "
                    "ON DUPLICATE KEY UPDATE "
                    "consecutive_misses = 0, last_drawn = %s, updated_at = NOW()",
                    (game, ntype, s, today, today, today),
                )
                reset_count += 1

            # 4. Increment all OTHER tracked stars/chance
            star_placeholders = ",".join(["%s"] * len(drawn_stars))
            await cursor.execute(
                "UPDATE hybride_decay_state "
                "SET consecutive_misses = consecutive_misses + 1, updated_at = NOW() "
                "WHERE game = %s AND number_type = %s "
                f"AND number_value NOT IN ({star_placeholders})",
                (game, ntype, *drawn_stars),
            )
            incremented_count += cursor.rowcount

        await conn.commit()
        logger.info(
            "update_decay_after_draw OK for %s — %d reset, %d incremented",
            game, reset_count, incremented_count,
        )
        return {"game": game, "reset": reset_count, "incremented": incremented_count}
    except Exception:
        logger.warning("update_decay_after_draw failed for %s — skipping", game, exc_info=True)
        return {"game": game, "reset": 0, "incremented": 0, "error": True}


async def check_and_update_decay(conn, game: str, table_name: str) -> dict | None:
    """Auto-detect new real draw and update decay state if needed.

    Compares the latest draw date in the draws table vs the MAX(updated_at)
    in hybride_decay_state. If a newer draw exists, triggers update_decay_after_draw.

    Safe to call from the scoring path — it only WRITES when a genuinely new draw
    is detected (typically once per draw, ~3x/week for Loto, ~2x/week for EM).

    Returns update summary or None if no new draw detected.
    """
    try:
        cursor = await conn.cursor()

        # Get the most recent draw date from the draws table
        await cursor.execute(
            f"SELECT date_de_tirage FROM {table_name} "
            "ORDER BY date_de_tirage DESC LIMIT 1",
        )
        latest_draw_row = await cursor.fetchone()
        if not latest_draw_row:
            return None
        latest_draw_date = latest_draw_row["date_de_tirage"]

        # Get the most recent update in decay_state for this game
        await cursor.execute(
            "SELECT MAX(updated_at) AS last_update, MAX(last_drawn) AS last_drawn_date "
            "FROM hybride_decay_state WHERE game = %s",
            (game,),
        )
        decay_row = await cursor.fetchone()
        last_drawn_date = decay_row["last_drawn_date"] if decay_row else None

        # Guard: if the latest draw was already processed, skip
        if last_drawn_date is not None and str(last_drawn_date) >= str(latest_draw_date):
            return None

        # New draw detected — fetch drawn numbers
        if game == "euromillions":
            await cursor.execute(
                f"SELECT boule_1, boule_2, boule_3, boule_4, boule_5, etoile_1, etoile_2 "
                f"FROM {table_name} WHERE date_de_tirage = %s LIMIT 1",
                (latest_draw_date,),
            )
        else:
            await cursor.execute(
                f"SELECT boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance "
                f"FROM {table_name} WHERE date_de_tirage = %s LIMIT 1",
                (latest_draw_date,),
            )

        draw_row = await cursor.fetchone()
        if not draw_row:
            return None

        drawn_balls = [draw_row[f"boule_{i}"] for i in range(1, 6)]

        if game == "euromillions":
            drawn_stars = [draw_row["etoile_1"], draw_row["etoile_2"]]
        elif "numero_chance" in draw_row and draw_row["numero_chance"] is not None:
            drawn_stars = [draw_row["numero_chance"]]
        else:
            drawn_stars = None

        logger.info(
            "check_and_update_decay: new draw detected for %s (date=%s, balls=%s, stars=%s)",
            game, latest_draw_date, drawn_balls, drawn_stars,
        )

        return await update_decay_after_draw(conn, game, drawn_balls, drawn_stars)

    except Exception:
        logger.warning("check_and_update_decay failed for %s — skipping", game, exc_info=True)
        return None
