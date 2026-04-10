"""
Decay state persistence for HYBRIDE engine.
Tracks consecutive selections per number to enable score decay
and break kernel lock (same numbers selected N draws in a row).

Table: hybride_decay_state
Pipeline position: AFTER penalization, BEFORE anti-collision (step 4).
See audit 360° Engine HYBRIDE F04 — 01/04/2026.

Note (V93 F07): Python API uses "consecutive_selections" — the number of times
the engine selected a number without it appearing in a real draw. The SQL column
is still named "consecutive_misses" (no migration). Mapping is done in this module.
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


# ── Async DB access ──────────────────────────────────────────────────

async def get_decay_state(
    conn, game: str, number_type: str = "ball",
) -> dict[int, int]:
    """Return {number_value: consecutive_selections} for a game and type.

    Returns {} if the table is empty (first launch) or on error.
    Graceful degradation: never raises — returns empty dict on failure.

    Note: SQL column is "consecutive_misses" (legacy name, no migration).
    Python API returns values as consecutive_selections.
    """
    try:
        cursor = await conn.cursor()
        await cursor.execute(
            # SQL column "consecutive_misses" = consecutive_selections in Python API (V93 F07)
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


async def update_decay_after_generation(
    conn,
    game: str,
    generated_balls: list[int],
    generated_stars: list[int] | None = None,
) -> None:
    """Increment consecutive_selections for each generated number.

    Called AFTER each grid generation. For each generated number:
    consecutive_selections += 1, last_played = today.
    Numbers NOT generated are untouched.

    Note: SQL column is "consecutive_misses" (legacy name, no migration).
    """
    today = date.today().isoformat()
    try:
        cursor = await conn.cursor()
        for num in generated_balls:
            await cursor.execute(
                # SQL column "consecutive_misses" = consecutive_selections (V93 F07)
                "INSERT INTO hybride_decay_state "
                "(game, number_type, number_value, consecutive_misses, last_played) "
                "VALUES (%s, 'ball', %s, 1, %s) "
                "ON DUPLICATE KEY UPDATE "
                "consecutive_misses = consecutive_misses + 1, last_played = %s",
                (game, num, today, today),
            )
        if generated_stars:
            ntype = "star" if game == "euromillions" else "chance"
            for s in generated_stars:
                await cursor.execute(
                    "INSERT INTO hybride_decay_state "
                    "(game, number_type, number_value, consecutive_misses, last_played) "
                    "VALUES (%s, %s, %s, 1, %s) "
                    "ON DUPLICATE KEY UPDATE "
                    "consecutive_misses = consecutive_misses + 1, last_played = %s",
                    (game, ntype, s, today, today),
                )
        await conn.commit()
    except Exception:
        logger.warning("update_decay_after_generation failed for %s — skipping", game)


async def update_decay_after_draw(
    conn,
    game: str,
    drawn_balls: list[int],
    drawn_stars: list[int] | None = None,
) -> None:
    """Reset consecutive_selections for drawn numbers.

    Called when a new real draw is inserted in DB.
    For each drawn number: consecutive_selections = 0, last_drawn = today.

    Note: SQL column is "consecutive_misses" (legacy name, no migration).
    """
    today = date.today().isoformat()
    try:
        cursor = await conn.cursor()
        for num in drawn_balls:
            await cursor.execute(
                # SQL column "consecutive_misses" = consecutive_selections (V93 F07)
                "INSERT INTO hybride_decay_state "
                "(game, number_type, number_value, consecutive_misses, last_drawn) "
                "VALUES (%s, 'ball', %s, 0, %s) "
                "ON DUPLICATE KEY UPDATE "
                "consecutive_misses = 0, last_drawn = %s",
                (game, num, today, today),
            )
        if drawn_stars:
            ntype = "star" if game == "euromillions" else "chance"
            for s in drawn_stars:
                await cursor.execute(
                    "INSERT INTO hybride_decay_state "
                    "(game, number_type, number_value, consecutive_misses, last_drawn) "
                    "VALUES (%s, %s, %s, 0, %s) "
                    "ON DUPLICATE KEY UPDATE "
                    "consecutive_misses = 0, last_drawn = %s",
                    (game, ntype, s, today, today),
                )
        await conn.commit()
    except Exception:
        logger.warning("update_decay_after_draw failed for %s — skipping", game)
