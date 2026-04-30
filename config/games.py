"""
GameConfig registry — Phase 10 Unified Routes
===============================================
Centralise la configuration par jeu (loto / euromillions)
pour les routes unifiees /api/{game}/...
"""

from dataclasses import dataclass, field
from enum import Enum
import importlib
import logging
from functools import lru_cache

# V137.C: module-level logger — required for tests patching `config.games.logger`
logger = logging.getLogger(__name__)


class ValidGame(str, Enum):
    loto = "loto"
    euromillions = "euromillions"


@dataclass(frozen=True)
class RouteGameConfig:
    slug: str
    table: str
    stats_module: str
    engine_module: str
    engine_stats_module: str
    chat_pipeline_module: str
    num_range: tuple
    secondary_range: tuple
    secondary_name: str
    secondary_column: str
    num_count: int
    secondary_count: int
    draw_days: list = field(default_factory=list)


GAME_CONFIGS: dict[ValidGame, RouteGameConfig] = {
    ValidGame.loto: RouteGameConfig(
        slug="loto",
        table="tirages",
        stats_module="services.stats_service",
        engine_module="engine.hybride",
        engine_stats_module="engine.stats",
        chat_pipeline_module="services.chat_pipeline",
        num_range=(1, 49),
        secondary_range=(1, 10),
        secondary_name="chance",
        secondary_column="numero_chance",
        num_count=5,
        secondary_count=1,
        draw_days=["lundi", "mercredi", "samedi"],
    ),
    ValidGame.euromillions: RouteGameConfig(
        slug="euromillions",
        table="tirages_euromillions",
        stats_module="services.em_stats_service",
        engine_module="engine.hybride_em",
        engine_stats_module="engine.stats_em",
        chat_pipeline_module="services.chat_pipeline_em",
        num_range=(1, 50),
        secondary_range=(1, 12),
        secondary_name="etoile",
        secondary_column="etoile_1, etoile_2",
        num_count=5,
        secondary_count=2,
        draw_days=["mardi", "vendredi"],
    ),
}


def get_config(game: ValidGame) -> RouteGameConfig:
    return GAME_CONFIGS[game]


# ── Lazy-import helpers ──

@lru_cache(maxsize=8)
def _load(module_path: str):
    return importlib.import_module(module_path)


def get_stats_service(cfg: RouteGameConfig):
    return _load(cfg.stats_module)


def get_engine(cfg: RouteGameConfig):
    """Return the singleton HybrideEngine instance for the given game."""
    mod = _load(cfg.engine_module)
    return mod._engine


def get_engine_stats(cfg: RouteGameConfig):
    return _load(cfg.engine_stats_module)


def get_chat_pipeline(cfg: RouteGameConfig):
    return _load(cfg.chat_pipeline_module)


# ── V110: Next draw date helper ──

# Python weekday() mapping (Monday=0 ... Sunday=6)
_WEEKDAY_FR = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
    "vendredi": 4, "samedi": 5, "dimanche": 6,
}

# Draw cutoff hour (local time). After this hour on a draw day, the draw is
# considered done — next_draw_date advances to the following draw day.
# Real broadcast: Loto ~20h15, EuroMillions ~21h15. We use safety margins.
_DRAW_CUTOFF_HOUR = {
    "loto": 21,
    "euromillions": 22,
}


def get_next_draw_date(game: ValidGame, reference=None):
    """Return the next scheduled draw date on or after reference.

    V110 — addresses persistent saturation brake inter-draw rotation.

    Args:
        game: ValidGame.loto or ValidGame.euromillions
        reference: datetime.datetime (preferred) or datetime.date or None (=now).
                   If datetime with tzinfo aware, used as-is. If naive, treated as local.
                   If date (no time), midnight is assumed (no cutoff skip on today).

    Logic:
        - Determine candidate weekdays from cfg.draw_days
        - Iterate days from reference for up to 8 days
        - Skip today ONLY if reference is a datetime AND current hour >= cutoff
        - Return the first matching day

    Fallback: returns reference.date() if no draw day found in 8 days (unreachable).
    """
    from datetime import date as _date, datetime as _dt, timedelta
    if reference is None:
        reference = _dt.now()
    # Normalize to (date, hour) pair
    if isinstance(reference, _dt):
        today = reference.date()
        current_hour = reference.hour
    else:
        today = reference
        current_hour = 0  # pure date → assume midnight, do not skip
    cfg = get_config(game)
    target_weekdays = {_WEEKDAY_FR[d] for d in cfg.draw_days if d in _WEEKDAY_FR}
    cutoff = _DRAW_CUTOFF_HOUR.get(cfg.slug, 21)
    for i in range(8):
        candidate = today + timedelta(days=i)
        if candidate.weekday() not in target_weekdays:
            continue
        # Skip today if past the draw cutoff hour (draw is considered done)
        if i == 0 and current_hour >= cutoff:
            continue
        return candidate
    return today


# ── V137.C: BDD-aware next draw date helper (production source of truth) ──
#
# Issue : `get_next_draw_date` (V110, sync) calcule la prochaine date à partir
# du calendrier hebdomadaire + cutoff hour hardcodé (Loto 21h, EM 22h). Si le
# pipeline d'import est retardé (résultat officiel pas encore inséré en BDD à
# 22h), les visiteurs continuent à générer des grilles ciblant le tirage du
# jour suivant alors que celui du jour n'a pas encore été acté → désaccord
# logique stats/calendrier (cas observé 29/04/2026 : 55 grilles polluantes
# 21h12-22h27 ciblant un tirage déjà tombé à 20h50 mais inséré ~21h30).
#
# V137.C : utiliser la présence du résultat officiel en BDD comme source de
# vérité. Tant que le résultat du jour n'est pas inséré, on continue à
# cibler ce tirage (cohérent même si pipeline lent). Dès que la row apparaît
# en BDD, on avance vers le tirage suivant.

# Mapping table + colonne date par jeu — symétrie V99 F09
_GAME_DRAW_TABLE = {
    ValidGame.loto: ("tirages", "date_de_tirage"),
    ValidGame.euromillions: ("tirages_euromillions", "date_de_tirage"),
}


async def get_next_draw_date_db_aware(
    game: ValidGame,
    conn,
    reference=None,
):
    """V137.C — BDD-aware version of get_next_draw_date.

    Iterate calendar candidates and consult the official-results table. The
    first candidate without a row in BDD is the *next* draw the system should
    target. Falls back to the V110 sync helper if conn is unusable or if the
    query raises (defense in depth, V135 lesson).

    Args:
        game: ValidGame.loto or ValidGame.euromillions
        conn: aiomysql DictCursor connection. If None, falls back to sync.
        reference: datetime.datetime / datetime.date / None (= now()).

    Logic:
        For offset i in 0..7:
            candidate = today + i days
            if candidate.weekday() not in cfg.draw_days: continue
            row = SELECT 1 FROM <table> WHERE date_de_tirage = candidate LIMIT 1
            if row is None: return candidate           # next draw to target
            else: append candidate to skipped, continue
        Si aucun candidat libre en 8 jours → log warning + fallback sync.
        Log [NEXT_DRAW] auto-advance émis UNIQUEMENT si skipped non-vide.
    """
    from datetime import datetime as _dt

    if conn is None:
        return get_next_draw_date(game, reference=reference)

    if reference is None:
        reference = _dt.now()
    today = reference.date() if isinstance(reference, _dt) else reference

    cfg = get_config(game)
    target_weekdays = {_WEEKDAY_FR[d] for d in cfg.draw_days if d in _WEEKDAY_FR}
    table_info = _GAME_DRAW_TABLE.get(game)
    if table_info is None:
        return get_next_draw_date(game, reference=reference)
    table, date_col = table_info

    skipped: list = []
    try:
        from datetime import timedelta
        cur = await conn.cursor()
        for i in range(8):
            candidate = today + timedelta(days=i)
            if candidate.weekday() not in target_weekdays:
                continue
            sql = f"SELECT 1 AS found FROM {table} WHERE {date_col} = %s LIMIT 1"
            await cur.execute(sql, (candidate,))
            row = await cur.fetchone()
            if row is None:
                if skipped:
                    logger.info(
                        "[NEXT_DRAW] auto-advance game=%s skipped=%s next=%s "
                        "reason=result_already_in_db",
                        game.value, skipped, candidate.isoformat(),
                    )
                return candidate
            skipped.append(candidate.isoformat())
        # Aucun candidat libre dans 8 jours : ne devrait jamais arriver pour
        # Loto (3 tirages/sem) ni EM (2 tirages/sem). Defense in depth → fallback.
        logger.warning(
            "[NEXT_DRAW] no candidate without DB row in 8 days game=%s skipped=%s "
            "— falling back to sync helper",
            game.value, skipped,
        )
        return get_next_draw_date(game, reference=reference)
    except Exception:
        logger.warning(
            "[NEXT_DRAW] BDD-aware query failed game=%s — falling back to sync",
            game.value, exc_info=True,
        )
        return get_next_draw_date(game, reference=reference)
