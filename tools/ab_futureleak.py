"""A/B quantification du future-leak recent_draws (ÉTAPE 4, offline, READ-ONLY DB).

Run B (fidèle)  : recent_draws RELATIF au target rejoué (post-fix, harness tel quel).
Run A (leak ON) : recent_draws=None forcé → get_recent_draws ABSOLU (comportement pré-fix).

Même fenêtre, même seed RNG global, même baseline (lru_cache seed=42) →
    Δ_feature = |JSD_B − JSD_A|  par feature (7 boules).

Interprétation :
    Δ max < ~0.02  → leak MARGINAL sur les boules (ancien OOS ~moralement valide).
    Δ max ≥ ~0.02  → leak MATÉRIEL/structurant (ancien OOS trompeur).

Caveat : A et B consomment le RNG différemment (le hard-exclude diffère) → un résidu
de bruit de sondage subsiste malgré le seed commun ; sur 1500 grilles il est petit
devant un effet structurant. Run A = comportement pré-fix par construction (preuve
que le chemin recent_draws=None est intact).

Usage :
    python tools/ab_futureleak.py --game loto --n-tirages 50 --n-grilles 30 --date-max 2026-05-27
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.backtest_hybride import BacktestConfig, BacktestHarness, FEATURE_NAMES
from db_cloudsql import init_pool, close_pool

SEED = 42


async def _run_ab(game: str, n_tirages: int, n_grilles: int, date_max: str | None):
    harness = BacktestHarness(
        game=game, n_tirages=n_tirages, n_grilles_per_tirage=n_grilles,
        mode="balanced", date_max=date_max,
    )
    cfg = BacktestConfig()

    # Run B (fidèle) — harness tel quel (recent_draws relatif au target)
    random.seed(SEED)
    res_b = await harness.run_config(cfg)

    # Run A (leak ON) — force recent_draws=None → get_recent_draws absolu (pré-fix)
    orig_generate = harness._generate_grilles

    async def _gen_leak_on(engine, bb, bs, recent_draws=None):
        return await orig_generate(engine, bb, bs, recent_draws=None)

    harness._generate_grilles = _gen_leak_on
    random.seed(SEED)
    res_a = await harness.run_config(cfg)

    jsd_a = res_a["tier2"]["feature_jsd"]
    jsd_b = res_b["tier2"]["feature_jsd"]
    deltas = {f: round(abs(jsd_b[f] - jsd_a[f]), 6) for f in FEATURE_NAMES}
    return jsd_a, jsd_b, deltas, harness


def _print_table(game, jsd_a, jsd_b, deltas):
    print(f"\n=== A/B future-leak — {game.upper()} ===")
    print(f"{'feature':<16}{'JSD_A(leak)':>14}{'JSD_B(fidele)':>16}{'delta':>12}")
    for f in FEATURE_NAMES:
        print(f"{f:<16}{jsd_a[f]:>14.6f}{jsd_b[f]:>16.6f}{deltas[f]:>12.6f}")
    dmax = max(deltas.values())
    verdict = "MARGINAL (<0.02)" if dmax < 0.02 else "MATERIEL (>=0.02)"
    print(f"{'-- delta max':<16}{'':>30}{dmax:>12.6f}  -> {verdict}")


async def _main(args):
    await init_pool()
    try:
        jsd_a, jsd_b, deltas, harness = await _run_ab(
            args.game, args.n_tirages, args.n_grilles, args.date_max,
        )
    finally:
        await close_pool()

    _print_table(args.game, jsd_a, jsd_b, deltas)

    out = {
        "game": args.game, "n_tirages": args.n_tirages, "n_grilles": args.n_grilles,
        "date_max": args.date_max, "seed": SEED,
        "jsd_leak_on": jsd_a, "jsd_fidele": jsd_b, "delta_abs": deltas,
        "delta_max": max(deltas.values()),
        "tirages_range": {
            "first": str(harness._tirages_cache[0].draw_date) if harness._tirages_cache else None,
            "last": str(harness._tirages_cache[-1].draw_date) if harness._tirages_cache else None,
            "n": len(harness._tirages_cache or []),
        },
    }
    outdir = _PROJECT_ROOT / "docs" / "run OOS" / "ab_futureleak"
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / f"ab_{args.game}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    print(f"JSON ecrit : {p}")
    return 0


def _parse(argv=None):
    p = argparse.ArgumentParser(prog="ab_futureleak")
    p.add_argument("--game", choices=["loto", "em"], default="loto")
    p.add_argument("--n-tirages", type=int, default=50)
    p.add_argument("--n-grilles", type=int, default=30)
    p.add_argument("--date-max", type=str, default="2026-05-27")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(_parse())))
