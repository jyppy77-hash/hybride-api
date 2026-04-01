"""
Decay state persistence for HYBRIDE engine.
Tracks consecutive misses per number to enable score decay
and break kernel lock (same numbers selected N draws in a row).

Table: hybride_decay_state
Pipeline position: AFTER penalization, BEFORE anti-collision (step 4).
See audit 360° Engine HYBRIDE F04 — 01/04/2026.
"""

import logging
from datetime import date

logger = logging.getLogger(__name__)


# ── Pure function (no DB) ────────────────────────────────────────────

def calculate_decay_multiplier(
    consecutive_misses: int,
    decay_rate: float = 0.05,
    floor: float = 0.50,
) -> float:
    """Calculate decay multiplier for a number based on consecutive misses.

    Formula: max(floor, 1.0 - (consecutive_misses * decay_rate))

    Examples with decay_rate=0.05, floor=0.50:
        0 misses → 1.00 (no penalty)
        1 miss   → 0.95
        5 misses → 0.75
        10 misses → 0.50 (floor)
        20 misses → 0.50 (floor, does not go lower)
    """
    if consecutive_misses <= 0:
        return 1.0
    return max(floor, 1.0 - (consecutive_misses * decay_rate))


# ── Async DB access ──────────────────────────────────────────────────

async def get_decay_state(
    conn, game: str, number_type: str = "ball",
) -> dict[int, int]:
    """Return {number_value: consecutive_misses} for a game and type.

    Returns {} if the table is empty (first launch) or on error.
    Graceful degradation: never raises — returns empty dict on failure.
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


async def update_decay_after_generation(
    conn,
    game: str,
    generated_balls: list[int],
    generated_stars: list[int] | None = None,
) -> None:
    """Increment consecutive_misses for each generated number.

    Called AFTER each grid generation. For each generated number:
    consecutive_misses += 1, last_played = today.
    Numbers NOT generated are untouched.
    """
    today = date.today().isoformat()
    try:
        cursor = await conn.cursor()
        for num in generated_balls:
            await cursor.execute(
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
    """Reset consecutive_misses for drawn numbers.

    Called when a new real draw is inserted in DB.
    For each drawn number: consecutive_misses = 0, last_drawn = today.
    """
    today = date.today().isoformat()
    try:
        cursor = await conn.cursor()
        for num in drawn_balls:
            await cursor.execute(
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
