"""
V110 — Selection history persistence for HYBRIDE engine inter-draw brake.

Tracks the canonical grid numbers selected for a given draw_date_target.
Enables the "Persistent Saturation Brake" mechanism (audit 01.1 rev.2 — F01.1-01).

Table: hybride_selection_history
Pipeline position: READ-ONLY during scoring (step 4b, AFTER decay, BEFORE intra-batch saturation).
WRITE only on /api/{game}/generate (first canonical grid of the batch for the day).

Architecture (mirrors decay_state V94 pattern):
    - Scoring pipeline (API /generate) → WRITE canonical selection AFTER generation
    - Chatbot Phase G → READ-ONLY (never calls record_canonical_selection)
    - Idempotent via UNIQUE KEY (game, draw_date_target, number_value, number_type, source)
      → INSERT IGNORE, first caller wins, subsequent calls silently ignored

V136 — `source` column distinguishes generator (V110) vs PDF META top fréquences
(pdf_meta_global / pdf_meta_5a / pdf_meta_2a) for the admin performance calendar.
The persistent saturation brake reads only `source='generator'` rows: PDF META
tracking does not influence the brake.
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# WRITE — called from API /generate (never from chatbot)
# ─────────────────────────────────────────────────────────────────────

async def record_canonical_selection(
    conn,
    game: str,
    draw_date_target,
    selected_numbers: dict,
) -> dict:
    """Record the canonical grid selection for a target draw date.

    Idempotent: uses INSERT IGNORE with UNIQUE KEY
    (game, draw_date_target, number_value, number_type). The first /generate
    call of the day wins; subsequent calls with the same target date are no-ops.

    Args:
        conn: aiomysql async connection
        game: "loto" or "euromillions"
        draw_date_target: datetime.date — the date of the DRAW this grid targets
                          (not the generation date)
        selected_numbers: dict with keys in {"ball", "star", "chance"}
                          each value = list[int] of selected numbers.
                          Single-int values (legacy Loto chance) are wrapped to list.

    Returns:
        {"game": str, "draw_date_target": str, "inserted": int,
         "ignored": int, "error": bool (optional)}

    Graceful degradation: never raises — logs warning on DB error and returns error flag.
    """
    try:
        cursor = await conn.cursor()
        inserted = 0
        ignored = 0

        for ntype, values in (selected_numbers or {}).items():
            if ntype not in ("ball", "star", "chance"):
                continue
            # Normalize to list
            if values is None:
                continue
            if isinstance(values, int):
                values = [values]
            if not isinstance(values, (list, tuple, set)):
                continue
            for n in values:
                if n is None:
                    continue
                try:
                    n_int = int(n)
                except (TypeError, ValueError):
                    continue
                await cursor.execute(
                    "INSERT IGNORE INTO hybride_selection_history "
                    "(game, number_value, number_type, draw_date_target, source) "
                    "VALUES (%s, %s, %s, %s, 'generator')",
                    (game, n_int, ntype, draw_date_target),
                )
                if cursor.rowcount == 1:
                    inserted += 1
                else:
                    ignored += 1

        await conn.commit()
        logger.info(
            "record_canonical_selection OK for %s target=%s — %d inserted, %d ignored",
            game, draw_date_target, inserted, ignored,
        )
        return {
            "game": game,
            "draw_date_target": str(draw_date_target),
            "inserted": inserted,
            "ignored": ignored,
        }
    except Exception:
        logger.warning(
            "record_canonical_selection failed for %s target=%s — skipping",
            game, draw_date_target, exc_info=True,
        )
        return {
            "game": game,
            "draw_date_target": str(draw_date_target),
            "inserted": 0, "ignored": 0, "error": True,
        }


# ─────────────────────────────────────────────────────────────────────
# READ — called from API /generate AND chatbot Phase G
# ─────────────────────────────────────────────────────────────────────

async def get_persistent_brake_map(
    conn,
    game: str,
    current_draw_date,
    number_type: str,
    config,
) -> dict:
    """Return {number: multiplier} for numbers freined by persistent brake.

    V110 — inter-draw rotation.

    Reads the canonical selections from the last N draws BEFORE current_draw_date
    and builds a brake map:
        - Numbers in T-1 selection → multiplier = config.saturation_brake_persistent_t1 (default 0.20)
        - Numbers in T-2 selection → multiplier = config.saturation_brake_persistent_t2 (default 0.50)
        - If a number is in both T-1 and T-2 → min multiplier is applied (0.20)
        - N controlled by config.saturation_persistent_window (1 = T-1 only, 2 = T-1 + T-2)

    Numbers NOT in the brake map get implicit multiplier 1.0 (the caller uses .get(n, 1.0)).

    Args:
        conn: aiomysql async connection
        game: "loto" or "euromillions"
        current_draw_date: date of the draw being generated for (T)
        number_type: "ball", "star", or "chance"
        config: EngineConfig instance (reads saturation_persistent_* fields)

    Returns:
        dict[int, float] — {number: multiplier} or {} if brake disabled/empty/error.
    """
    # Early exit: feature disabled → no brake
    if not getattr(config, "saturation_persistent_enabled", False):
        return {}

    t1_mult = getattr(config, "saturation_brake_persistent_t1", 0.20)
    t2_mult = getattr(config, "saturation_brake_persistent_t2", 0.50)
    window = getattr(config, "saturation_persistent_window", 2)

    try:
        cursor = await conn.cursor()
        # Fetch distinct draw_date_target values before current_draw_date (DESC)
        # limited to window size. These are the "T-1, T-2, ..." canonical dates.
        # V136: filtre source='generator' — les rows pdf_meta_* du calendrier
        # admin performance ne contribuent pas au brake.
        await cursor.execute(
            "SELECT DISTINCT draw_date_target FROM hybride_selection_history "
            "WHERE game = %s AND number_type = %s AND source = 'generator' "
            "AND draw_date_target < %s "
            "ORDER BY draw_date_target DESC LIMIT %s",
            (game, number_type, current_draw_date, int(window)),
        )
        rows = await cursor.fetchall()
        if not rows:
            return {}
        target_dates = [row["draw_date_target"] for row in rows]
        # target_dates[0] = T-1 (most recent before current), target_dates[1] = T-2, ...

        # Fetch all numbers for these target dates in one query
        # V136: filtre source='generator' (idem ci-dessus).
        placeholders = ",".join(["%s"] * len(target_dates))
        await cursor.execute(
            f"SELECT number_value, draw_date_target FROM hybride_selection_history "
            f"WHERE game = %s AND number_type = %s AND source = 'generator' "
            f"AND draw_date_target IN ({placeholders})",
            (game, number_type, *target_dates),
        )
        selections = await cursor.fetchall()

        # Build brake map: iterate selections, apply min multiplier if collision
        brake: dict[int, float] = {}
        # Map target_date → tier index (0 = T-1, 1 = T-2, ...)
        date_to_tier = {d: i for i, d in enumerate(target_dates)}
        tier_multipliers = (t1_mult, t2_mult)
        for sel in selections:
            n = sel["number_value"]
            tier = date_to_tier.get(sel["draw_date_target"])
            if tier is None or tier >= len(tier_multipliers):
                continue
            mult = tier_multipliers[tier]
            # Collision (number in both T-1 and T-2): keep the MIN (stronger brake)
            if n in brake:
                brake[n] = min(brake[n], mult)
            else:
                brake[n] = mult

        return brake
    except Exception:
        logger.warning(
            "get_persistent_brake_map failed for %s/%s — returning empty map",
            game, number_type, exc_info=True,
        )
        return {}


# ─────────────────────────────────────────────────────────────────────
# MAINTENANCE — optional cleanup
# ─────────────────────────────────────────────────────────────────────

async def cleanup_old_selections(
    conn,
    game: str,
    keep_last_n_draws: int = 20,
) -> dict:
    """Purge entries beyond the last N distinct draw_date_target values.

    Called periodically (cron or admin endpoint). Keeps the table small
    — only ~20 draws × (5 balls + 1-2 secondary) = ~140 rows per game at most.

    Returns {"game": str, "deleted": int} or {"error": bool} on failure.
    """
    try:
        cursor = await conn.cursor()
        # Fetch the Nth most recent draw_date_target as threshold
        # V136: cleanup ne porte que sur les rows generator (les rows pdf_meta_*
        # du calendrier admin performance ont leur propre durée de vie).
        await cursor.execute(
            "SELECT DISTINCT draw_date_target FROM hybride_selection_history "
            "WHERE game = %s AND source = 'generator' "
            "ORDER BY draw_date_target DESC LIMIT %s",
            (game, int(keep_last_n_draws)),
        )
        rows = await cursor.fetchall()
        if not rows or len(rows) < keep_last_n_draws:
            # Nothing to prune (yet)
            return {"game": game, "deleted": 0}
        threshold = rows[-1]["draw_date_target"]
        await cursor.execute(
            "DELETE FROM hybride_selection_history "
            "WHERE game = %s AND source = 'generator' "
            "AND draw_date_target < %s",
            (game, threshold),
        )
        deleted = cursor.rowcount
        await conn.commit()
        logger.info(
            "cleanup_old_selections OK for %s — %d rows deleted (kept >=%s)",
            game, deleted, threshold,
        )
        return {"game": game, "deleted": deleted}
    except Exception:
        logger.warning("cleanup_old_selections failed for %s", game, exc_info=True)
        return {"game": game, "deleted": 0, "error": True}


# ─────────────────────────────────────────────────────────────────────
# INFO — non-critical helper for logging
# ─────────────────────────────────────────────────────────────────────

async def is_first_generation_of_target_draw(
    conn,
    game: str,
    draw_date_target,
) -> bool:
    """Return True if no selection exists yet for this target draw date.

    Used only for logging ("first canonical grid of the day"). The idempotence
    itself is enforced by UNIQUE KEY + INSERT IGNORE, so this function has
    no functional impact.

    Graceful degradation: returns False on error (safe default = assume not first).
    """
    try:
        cursor = await conn.cursor()
        # V136: ne considère que les rows generator (les rows pdf_meta_* ne sont
        # pas des grilles canoniques et ne doivent pas inhiber le log "first").
        await cursor.execute(
            "SELECT 1 FROM hybride_selection_history "
            "WHERE game = %s AND source = 'generator' "
            "AND draw_date_target = %s LIMIT 1",
            (game, draw_date_target),
        )
        row = await cursor.fetchone()
        return row is None
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────
# V136 — PDF META top frequencies tracking (admin performance calendar)
# ─────────────────────────────────────────────────────────────────────

_VALID_PDF_META_SOURCES = ("pdf_meta_global", "pdf_meta_5a", "pdf_meta_2a")


async def record_pdf_meta_top(
    conn,
    game: str,
    draw_date_target,
    source: str,
    balls_top5: list,
    secondary_top1=None,
) -> dict:
    """V136 — Record top frequencies from PDF META analysis (admin perf calendar).

    Distinct from `record_canonical_selection` (V110): this writer feeds the
    admin calendar /admin/calendar-perf — it does NOT participate in the
    persistent saturation brake (V110 reads only `source='generator'`).

    Idempotent: relies on UNIQUE KEY
    (game, draw_date_target, number_value, number_type, source). The first call
    for a given window/day wins; subsequent calls with the same top fréquences
    are silently ignored.

    Args:
        conn: aiomysql async connection
        game: "loto" or "euromillions"
        draw_date_target: datetime.date — the date of the upcoming DRAW
        source: one of "pdf_meta_global", "pdf_meta_5a", "pdf_meta_2a"
        balls_top5: list[int] — top 5 ball numbers (highest frequency)
        secondary_top1: int | None — top 1 chance/star number

    Returns:
        {"game": str, "source": str, "draw_date_target": str,
         "inserted": int, "ignored": int, "error": bool (optional)}

    Graceful degradation: never raises — logs warning on DB error.
    """
    if source not in _VALID_PDF_META_SOURCES:
        logger.warning("record_pdf_meta_top invalid source=%s", source)
        return {
            "game": game, "source": source,
            "draw_date_target": str(draw_date_target),
            "inserted": 0, "ignored": 0, "error": True,
        }
    secondary_type = "chance" if game == "loto" else "star"
    try:
        cursor = await conn.cursor()
        inserted = 0
        ignored = 0
        # Top 5 balls
        for n in (balls_top5 or [])[:5]:
            if n is None:
                continue
            try:
                n_int = int(n)
            except (TypeError, ValueError):
                continue
            await cursor.execute(
                "INSERT IGNORE INTO hybride_selection_history "
                "(game, number_value, number_type, draw_date_target, source) "
                "VALUES (%s, %s, 'ball', %s, %s)",
                (game, n_int, draw_date_target, source),
            )
            if cursor.rowcount == 1:
                inserted += 1
            else:
                ignored += 1
        # Top 1 secondary (chance for Loto, star for EM)
        if secondary_top1 is not None:
            try:
                s_int = int(secondary_top1)
                await cursor.execute(
                    "INSERT IGNORE INTO hybride_selection_history "
                    "(game, number_value, number_type, draw_date_target, source) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (game, s_int, secondary_type, draw_date_target, source),
                )
                if cursor.rowcount == 1:
                    inserted += 1
                else:
                    ignored += 1
            except (TypeError, ValueError):
                pass
        await conn.commit()
        logger.info(
            "[CALENDAR] record_pdf_meta_top OK game=%s source=%s target=%s "
            "%d inserted, %d ignored",
            game, source, draw_date_target, inserted, ignored,
        )
        return {
            "game": game, "source": source,
            "draw_date_target": str(draw_date_target),
            "inserted": inserted, "ignored": ignored,
        }
    except Exception:
        logger.warning(
            "record_pdf_meta_top failed for %s/%s target=%s",
            game, source, draw_date_target, exc_info=True,
        )
        return {
            "game": game, "source": source,
            "draw_date_target": str(draw_date_target),
            "inserted": 0, "ignored": 0, "error": True,
        }
