"""
V107: Even Spacing Index (ESI) — post-generation grid filter.

Rejects grids that are too evenly spaced (over-played by public, high collision
risk) or too clustered (statistically atypical).

ESI formula for k sorted numbers {r1..rk} in universe [1, n]:
    ESI = sum((r[i+1] - r[i] - 1)^2 for i in 1..k-1) + (r1 - 1 + n - rk)^2

The last term is the cyclic wrap-around gap.

Low ESI → regular spacing (e.g. 10-20-30-40-50 → ESI=0). Over-played.
High ESI → clusters or big gaps (e.g. 1-2-3-4-5 → ESI=2025). Atypical.
Medium ESI → natural distribution. Sweet spot.
"""


def calculate_esi(numbers: list[int], universe_size: int) -> int:
    """Calculate Even Spacing Index for a set of numbers.

    Args:
        numbers: list of drawn numbers (unsorted OK, will be sorted).
        universe_size: total numbers in the universe (49 for Loto, 50 for EM).

    Returns:
        ESI value (integer, 0 = perfectly spaced).
    """
    sorted_nums = sorted(numbers)
    k = len(sorted_nums)
    if k < 2:
        return 0
    esi = 0
    for i in range(1, k):
        esi += (sorted_nums[i] - sorted_nums[i - 1] - 1) ** 2
    # Cyclic wrap-around gap
    esi += (sorted_nums[0] - 1 + universe_size - sorted_nums[-1]) ** 2
    return esi


def validate_esi(numbers: list[int], universe_size: int,
                 esi_min: int, esi_max: int) -> bool:
    """Check if a grid's ESI falls within acceptable bounds.

    Returns True if esi_min <= ESI <= esi_max, False otherwise.
    """
    esi = calculate_esi(numbers, universe_size)
    return esi_min <= esi <= esi_max
