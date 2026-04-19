"""
GameConfig registry — Phase 10 Unified Routes
===============================================
Centralise la configuration par jeu (loto / euromillions)
pour les routes unifiees /api/{game}/...
"""

from dataclasses import dataclass, field
from enum import Enum
import importlib
from functools import lru_cache


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
