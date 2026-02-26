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
    return _load(cfg.engine_module)


def get_engine_stats(cfg: RouteGameConfig):
    return _load(cfg.engine_stats_module)


def get_chat_pipeline(cfg: RouteGameConfig):
    return _load(cfg.chat_pipeline_module)
