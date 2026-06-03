"""Compare 2 vecteurs feature_jsd (boules) de 2 JSON OOS. READ-ONLY, offline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FEATURES = ("somme", "dispersion", "std", "freq_1_31", "nb_pairs", "nb_consecutifs", "esi")


def _jsd(path: str) -> dict:
    d = json.load(open(path, encoding="utf-8"))
    return d["results_config_actuelle"]["tier2"]["feature_jsd"]


def main(argv: list[str]) -> int:
    path_a, path_b = argv[1], argv[2]
    label_a = argv[3] if len(argv) > 3 else "A"
    label_b = argv[4] if len(argv) > 4 else "B"
    a, b = _jsd(path_a), _jsd(path_b)
    print(f"{'feature':<16}{label_a:>18}{label_b:>18}{'delta':>12}")
    dmax = 0.0
    for f in FEATURES:
        delta = abs(a[f] - b[f])
        dmax = max(dmax, delta)
        print(f"{f:<16}{a[f]:>18.6f}{b[f]:>18.6f}{delta:>12.6f}")
    print(f"{'-- delta max':<16}{'':>36}{dmax:>12.6f}")
    print("Verdict :", "DANS LE BRUIT (<0.02)" if dmax < 0.02 else "ECART NOTABLE (>=0.02)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
