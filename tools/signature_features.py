"""V_X.F LOT 1 — Briques de base pour la métrique de signature statistique.

Outillage offline isolé. Fournit 4 briques pures réutilisables par le
harness de backtest (`tools/backtest_hybride.py`) au LOT 2.

Briques publiques :
    - extract_features(grille, num_max) -> dict[str, float]
        Vecteur de 7 features pour 1 grille (somme, dispersion, std,
        freq_1_31, nb_pairs, nb_consecutifs, esi).
    - generate_random_baseline(n, num_max, k, seed) -> tuple[dict, ...]
        N grilles uniformes random + features, cacheable lru_cache.
    - compute_feature_jsd(values_a, values_b, bins, *, base) -> float
        Jensen-Shannon Divergence per-feature entre 2 échantillons.
    - build_bins(feature_name, num_max=49) -> np.ndarray
        Edges de bins par feature : log pour ESI, fixes ailleurs.

Conception figée V_X.F (validée Jyppy 2026-05-28) :
    - JSD per-feature, jamais joint multivarié.
    - Hasard pur simulé comme baseline.
    - Mêmes bins HYBRIDE et baseline (sinon JSD biaisée par granularité).
    - Pas de scipy ; JSD = numpy maison.

Périmètre LOT 1 : ZÉRO touche au harness ni à la prod. Fonctions pures,
testables unitairement.
"""

from __future__ import annotations

import functools
import random
import statistics

import numpy as np

from services.esi import calculate_esi


# ════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════════

FEATURE_NAMES: tuple[str, ...] = (
    "somme",
    "dispersion",
    "std",
    "freq_1_31",
    "nb_pairs",
    "nb_consecutifs",
    "esi",
)

DEFAULT_RANDOM_SEED: int = 42

# Cap supérieur partagé Loto+EM pour le binning ESI logarithmique.
# Max théorique 5/49 = 44² = 1936 ; max 5/50 = 45² = 2025.
_ESI_MAX_THEORIQUE: int = 2025


# ════════════════════════════════════════════════════════════════════════
# Brique 1 — extract_features
# ════════════════════════════════════════════════════════════════════════

def extract_features(grille: dict, num_max: int) -> dict[str, float]:
    """Extrait le vecteur de 7 features pour 1 grille.

    Args:
        grille: dict avec clé 'nums' = list[int] (5 numéros, triés ou non).
        num_max: univers (49 Loto / 50 EM) — propagé à calculate_esi pour
                 le wrap-around cyclique.

    Returns:
        dict avec clés FEATURE_NAMES, valeurs float :
            somme          = sum(nums)
            dispersion     = max - min
            std            = écart-type sample (statistics.stdev)
            freq_1_31      = nb de nums <= 31
            nb_pairs       = nb de nums pairs
            nb_consecutifs = nb de paires consécutives (gap=1) après tri
            esi            = Even Spacing Index via services.esi.calculate_esi

    Raises:
        KeyError: si 'nums' absent du dict.
        ValueError: si len(nums) != 5.
    """
    nums = grille["nums"]
    if len(nums) != 5:
        raise ValueError(
            f"extract_features: expected 5 nums, got {len(nums)} — "
            f"grille mal formée ({nums!r})"
        )

    nums_sorted = sorted(nums)
    somme = float(sum(nums_sorted))
    dispersion = float(nums_sorted[-1] - nums_sorted[0])
    std = float(statistics.stdev(nums_sorted))
    freq_1_31 = float(sum(1 for n in nums_sorted if n <= 31))
    nb_pairs = float(sum(1 for n in nums_sorted if n % 2 == 0))
    # Recopie volontaire de engine/hybride_base.py:684-685 (paires
    # adjacentes avec gap = 1 après tri).
    nb_consecutifs = float(
        sum(1 for i in range(len(nums_sorted) - 1)
            if nums_sorted[i + 1] - nums_sorted[i] == 1)
    )
    esi = float(calculate_esi(nums_sorted, num_max))

    return {
        "somme": somme,
        "dispersion": dispersion,
        "std": std,
        "freq_1_31": freq_1_31,
        "nb_pairs": nb_pairs,
        "nb_consecutifs": nb_consecutifs,
        "esi": esi,
    }


# ════════════════════════════════════════════════════════════════════════
# Brique 2 — generate_random_baseline (cached)
# ════════════════════════════════════════════════════════════════════════

@functools.lru_cache(maxsize=8)
def generate_random_baseline(
    n: int = 100_000,
    num_max: int = 49,
    k: int = 5,
    seed: int = DEFAULT_RANDOM_SEED,
) -> tuple[dict[str, float], ...]:
    """Génère n grilles uniformes random et extrait leurs features.

    Reproductible (random.Random(seed) local — pas de pollution du global).
    Caché via lru_cache (clé = n, num_max, k, seed). Tuple immuable
    retourné pour défense vs mutation par appelant.

    Args:
        n: nombre de grilles (default 100_000).
        num_max: borne sup univers, inclus (49 Loto / 50 EM).
        k: taille de chaque grille (default 5).
        seed: graine reproductibilité (default 42).

    Returns:
        tuple[dict, ...] de n dicts de features (cf. extract_features).
    """
    rng = random.Random(seed)
    universe = list(range(1, num_max + 1))
    grilles_features: list[dict[str, float]] = []
    for _ in range(n):
        sample = rng.sample(universe, k)
        grilles_features.append(extract_features({"nums": sample}, num_max=num_max))
    return tuple(grilles_features)


# ════════════════════════════════════════════════════════════════════════
# Brique 3 — compute_feature_jsd + helpers privés
# ════════════════════════════════════════════════════════════════════════

def _histogram_normalize(
    values,
    bins,
    epsilon: float = 1e-12,
) -> np.ndarray:
    """Convertit un échantillon en distribution de probabilité normalisée.

    Smoothing additif epsilon pour éviter log(0) dans la KL divergence.
    Fallback uniforme si l'échantillon est vide (pas de crash).
    """
    bins_arr = np.asarray(bins, dtype=np.float64)
    if len(bins_arr) < 2:
        raise ValueError("bins must have at least 2 edges (1 bin)")
    n_bins = len(bins_arr) - 1
    if values is None or (hasattr(values, "__len__") and len(values) == 0):
        return np.full(n_bins, 1.0 / n_bins)
    hist, _ = np.histogram(np.asarray(values, dtype=np.float64), bins=bins_arr)
    p = hist.astype(np.float64) + epsilon
    return p / p.sum()


def _kl_divergence(p: np.ndarray, q: np.ndarray) -> float:
    """KL(p || q). Suppose p, q déjà normalisées + smoothing > 0."""
    return float(np.sum(p * np.log(p / q)))


def compute_feature_jsd(
    values_a,
    values_b,
    bins,
    *,
    base: str = "e",
) -> float:
    """Jensen-Shannon Divergence entre 2 échantillons sur une même feature.

    Implémentation numpy maison (pas de scipy). Formule :
        JSD(P, Q) = 0.5 * KL(P || M) + 0.5 * KL(Q || M)
        avec M = 0.5 * (P + Q)

    Args:
        values_a: échantillon A (raw values d'une feature).
        values_b: échantillon B (raw values même feature).
        bins: edges des bins (MÊMES bins des 2 côtés — règle dure V_X.F).
        base: "e" (default) → ln, max log(2) ≈ 0.693
              "2" → log2, max 1.0

    Returns:
        float dans [0, log(2)] (base e) ou [0, 1] (base 2).

    Edge cases :
        - Échantillon vide → distribution uniforme fallback.
        - Distributions identiques → JSD ≈ 0 (epsilon-floored).
    """
    if base not in ("e", "2"):
        raise ValueError(f"base must be 'e' or '2', got {base!r}")
    p = _histogram_normalize(values_a, bins)
    q = _histogram_normalize(values_b, bins)
    m = 0.5 * (p + q)
    jsd_nat = 0.5 * _kl_divergence(p, m) + 0.5 * _kl_divergence(q, m)
    # Floor numérique : roundoff KL peut produire ε négatif.
    jsd_nat = max(0.0, jsd_nat)
    if base == "2":
        return jsd_nat / float(np.log(2))
    return float(jsd_nat)


# ════════════════════════════════════════════════════════════════════════
# Brique 4 — build_bins
# ════════════════════════════════════════════════════════════════════════

def build_bins(feature_name: str, num_max: int = 49) -> np.ndarray:
    """Retourne les edges de bins adaptés à une feature.

    Choix figés V_X.F (validés 2026-05-28) :
        somme          : edges [15..245] step 5         → 46 bins partagés Loto+EM
        dispersion     : edges [4..50]   step 1         → 46 bins
        std            : edges [0..30]   step 1.0       → 30 bins (couvre std max ~25.5)
        freq_1_31      : edges [0..6]    step 1         → 6 bins entiers
        nb_pairs       : edges [0..6]    step 1         → 6 bins
        nb_consecutifs : edges [0..5]    step 1         → 5 bins
        esi            : [0] ∪ geomspace(1, 2026, 30)   → 30 bins log, queue gérée

    Args:
        feature_name: nom dans FEATURE_NAMES.
        num_max: utilisé uniquement pour ESI (cap théorique).

    Returns:
        np.ndarray des edges (len = n_bins + 1).

    Raises:
        ValueError si feature_name inconnu.
    """
    if feature_name == "somme":
        return np.arange(15, 246, 5, dtype=np.float64)
    if feature_name == "dispersion":
        return np.arange(4, 51, 1, dtype=np.float64)
    if feature_name == "std":
        return np.arange(0, 31, 1.0, dtype=np.float64)
    if feature_name == "freq_1_31":
        return np.arange(0, 7, 1, dtype=np.float64)
    if feature_name == "nb_pairs":
        return np.arange(0, 7, 1, dtype=np.float64)
    if feature_name == "nb_consecutifs":
        return np.arange(0, 6, 1, dtype=np.float64)
    if feature_name == "esi":
        # Cap supérieur englobant Loto (1936) + EM (2025).
        esi_max = max(_ESI_MAX_THEORIQUE, (num_max - 5) ** 2)
        log_edges = np.geomspace(1.0, float(esi_max + 1), 30)
        return np.concatenate(([0.0], log_edges))
    raise ValueError(
        f"build_bins: feature_name {feature_name!r} not in FEATURE_NAMES "
        f"{FEATURE_NAMES}"
    )
