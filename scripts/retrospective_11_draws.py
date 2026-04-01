#!/usr/bin/env python3
"""
Retrospective test: simulate 11 EuroMillions draws (20/02 -> 31/03/2026)
with the new HYBRIDE engine (decay + noise + wildcard + somme [95,160]).

Compare against the old engine grids to measure diversification improvements.

Usage: py -3 scripts/retrospective_11_draws.py
NOT a pytest — standalone diagnostic script.
See audit 360° Engine HYBRIDE — 01/04/2026.
"""

import random
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.decay_state import calculate_decay_multiplier

# ── Historical data ──────────────────────────────────────────────────

HISTORICAL_DRAWS = [
    {"date": "2026-02-20", "balls": [13, 24, 28, 33, 35], "stars": [5, 9]},
    {"date": "2026-02-24", "balls": [10, 27, 40, 43, 47], "stars": [6, 10]},
    {"date": "2026-03-03", "balls": [6, 7, 24, 34, 50], "stars": [5, 7]},
    {"date": "2026-03-06", "balls": [15, 16, 19, 28, 37], "stars": [6, 9]},
    {"date": "2026-03-10", "balls": [12, 14, 27, 44, 50], "stars": [4, 12]},
    {"date": "2026-03-13", "balls": [13, 17, 26, 41, 48], "stars": [4, 10]},
    {"date": "2026-03-17", "balls": [5, 17, 28, 33, 41], "stars": [3, 9]},
    {"date": "2026-03-20", "balls": [5, 12, 16, 37, 46], "stars": [8, 10]},
    {"date": "2026-03-24", "balls": [12, 16, 17, 18, 27], "stars": [1, 3]},
    {"date": "2026-03-27", "balls": [4, 10, 43, 44, 48], "stars": [2, 4]},
    {"date": "2026-03-31", "balls": [5, 8, 10, 33, 38], "stars": [2, 7]},
]

OLD_ENGINE_GRIDS = [
    {"balls": [13, 29, 34, 35, 44], "stars": [5, 9]},
    {"balls": [7, 8, 29, 34, 44], "stars": [2, 10]},
    {"balls": [8, 21, 29, 34, 44], "stars": [5, 12]},
    {"balls": [8, 21, 29, 44, 48], "stars": [2, 12]},
    {"balls": [8, 21, 29, 44, 48], "stars": [2, 12]},
    {"balls": [8, 29, 42, 45, 48], "stars": [2, 8]},
    {"balls": [21, 29, 35, 42, 47], "stars": [2, 8]},
    {"balls": [21, 29, 34, 35, 42], "stars": [2, 7]},
    {"balls": [21, 29, 34, 35, 42], "stars": [6, 7]},
    {"balls": [21, 29, 34, 35, 42], "stars": [6, 12]},
    {"balls": [24, 29, 34, 35, 42], "stars": [6, 12]},
]


def count_matches(grid_balls, grid_stars, draw_balls, draw_stars):
    """Count ball + star matches."""
    b = len(set(grid_balls) & set(draw_balls))
    s = len(set(grid_stars) & set(draw_stars))
    return b + s


def simulate_new_engine(seed=42):
    """Simulate the new engine with decay, noise, wildcard.

    Since we can't call the real engine (needs DB), we simulate the key
    mechanisms: weighted random with decay penalties applied.
    """
    random.seed(seed)
    decay_state = {}  # {number: consecutive_misses}
    grids = []

    # Base frequencies: simulate roughly uniform with slight variations
    base_scores = {n: 0.5 + random.gauss(0, 0.05) for n in range(1, 51)}

    for draw_idx, draw in enumerate(HISTORICAL_DRAWS):
        # Apply decay to scores
        scores = {}
        for n, s in base_scores.items():
            misses = decay_state.get(n, 0)
            mult = calculate_decay_multiplier(misses, 0.05, 0.50)
            scores[n] = max(0.01, s * mult)

        # Add noise (balanced mode = 0.08)
        import statistics
        vals = list(scores.values())
        std = statistics.stdev(vals)
        noisy = {n: max(0.01, s + random.gauss(0, 0.08 * std)) for n, s in scores.items()}

        # Weighted sampling: 4 normal + 1 wildcard (bottom-15)
        items = sorted(noisy.items(), key=lambda x: x[1], reverse=True)
        weights = [s for _, s in items]
        nums = [n for n, _ in items]

        # Draw 4 from top pool
        drawn = []
        avail = list(zip(nums, weights))
        for _ in range(4):
            pool_nums = [n for n, _ in avail]
            pool_w = [w for _, w in avail]
            choice = random.choices(pool_nums, weights=pool_w, k=1)[0]
            drawn.append(choice)
            avail = [(n, w) for n, w in avail if n != choice]

        # 1 wildcard from bottom-15
        cold_pool = sorted(noisy.items(), key=lambda x: x[1])[:15]
        cold_pool = [(n, s) for n, s in cold_pool if n not in drawn]
        if cold_pool:
            cold_nums = [n for n, _ in cold_pool]
            cold_w = [max(0.01, s) for _, s in cold_pool]
            wc = random.choices(cold_nums, weights=cold_w, k=1)[0]
            drawn.append(wc)
        else:
            remaining = [n for n in range(1, 51) if n not in drawn]
            drawn.append(random.choice(remaining))

        balls = sorted(drawn)

        # Stars: simple weighted from 1-12
        star_scores = {s: 0.5 + random.gauss(0, 0.03) for s in range(1, 13)}
        star_items = sorted(star_scores.items(), key=lambda x: x[1], reverse=True)
        stars = sorted(random.sample([n for n, _ in star_items[:8]], 2))

        grids.append({"balls": balls, "stars": stars})

        # Update decay: increment misses for generated balls
        for b in balls:
            decay_state[b] = decay_state.get(b, 0) + 1

        # Reset decay for drawn balls (real draw)
        for b in draw["balls"]:
            decay_state[b] = 0

    return grids


def main():
    new_grids = simulate_new_engine(seed=42)

    print("=" * 90)
    print("Test Retrospectif — 11 Tirages EuroMillions (20/02 -> 31/03/2026)")
    print("=" * 90)
    print()
    print(f"{'#':>2} | {'Date':<10} | {'Ancien moteur':<22} | {'Sc':>3} | {'Nouveau moteur':<22} | {'Sc':>3} | {'Tirage reel':<22}")
    print("-" * 90)

    old_total = 0
    new_total = 0
    old_sums = []
    new_sums = []
    old_all_balls = set()
    new_all_balls = set()

    for i, draw in enumerate(HISTORICAL_DRAWS):
        old = OLD_ENGINE_GRIDS[i]
        new = new_grids[i]

        old_score = count_matches(old["balls"], old["stars"], draw["balls"], draw["stars"])
        new_score = count_matches(new["balls"], new["stars"], draw["balls"], draw["stars"])

        old_total += old_score
        new_total += new_score

        old_sum = sum(old["balls"])
        new_sum = sum(new["balls"])
        old_sums.append(old_sum)
        new_sums.append(new_sum)

        old_all_balls.update(old["balls"])
        new_all_balls.update(new["balls"])

        old_str = f"{'-'.join(str(b) for b in old['balls'])} *{'-'.join(str(s) for s in old['stars'])}"
        new_str = f"{'-'.join(str(b) for b in new['balls'])} *{'-'.join(str(s) for s in new['stars'])}"
        draw_str = f"{'-'.join(str(b) for b in draw['balls'])} *{'-'.join(str(s) for s in draw['stars'])}"

        print(f"{i+1:>2} | {draw['date']:<10} | {old_str:<22} | {old_score:>3} | {new_str:<22} | {new_score:>3} | {draw_str:<22}")

    print("-" * 90)
    print()
    print("MÉTRIQUES COMPARATIVES")
    print(f"  Score total         : ancien {old_total}/77, nouveau {new_total}/77")
    print(f"  Somme moyenne       : ancien {sum(old_sums)/len(old_sums):.0f}, nouveau {sum(new_sums)/len(new_sums):.0f}")
    print(f"  Somme moyenne reelle: {sum(sum(d['balls']) for d in HISTORICAL_DRAWS)/11:.0f}")
    print(f"  Numeros uniques     : ancien {len(old_all_balls)}, nouveau {len(new_all_balls)}")
    print(f"  Sommes dans [95-160]: ancien {sum(1 for s in old_sums if 95 <= s <= 160)}/11, "
          f"nouveau {sum(1 for s in new_sums if 95 <= s <= 160)}/11")

    # Kernel lock: count consecutive draws with >=4 same balls
    old_lock = 0
    new_lock = 0
    for i in range(1, 11):
        if len(set(OLD_ENGINE_GRIDS[i]["balls"]) & set(OLD_ENGINE_GRIDS[i-1]["balls"])) >= 4:
            old_lock += 1
        if len(set(new_grids[i]["balls"]) & set(new_grids[i-1]["balls"])) >= 4:
            new_lock += 1

    print(f"  Noyau fige (>=4 id.) : ancien {old_lock}/10, nouveau {new_lock}/10")
    print()


if __name__ == "__main__":
    main()
