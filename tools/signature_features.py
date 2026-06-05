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

────────────────────────────────────────────────────────────────────────
EXTENSION SECONDAIRE — LOT S1 (feature reine `*_in_T1` seule)
────────────────────────────────────────────────────────────────────────

Briques secondaire ADDITIVES, strictement séparées des briques boules
(registre / extraction / bins / baseline distincts — cf. audit Q7,
vigilance #2). Aucune des briques boules ci-dessus n'est touchée.

    - SECONDARY_FEATURE_NAMES (registre par jeu : loto/em)
    - extract_secondary_in_t1(grille_secondary, prev_secondary)
        Overlap secondaire grille ∩ T-1 (chance_in_T1 / etoiles_in_T1).
    - build_secondary_bins(feature_name)
        Bins entiers petit-univers (NE touche pas build_bins boules).
    - generate_secondary_in_t1_baseline(n, sec_min, sec_max, count, seed)
        Baseline SIMULATION APPARIÉE : overlap d'un secondaire random vs
        un T-1 random indépendant → distribution nulle empirique du
        recouvrement T-1 par pur hasard (arbitrage Jyppy #1).

compute_feature_jsd est réutilisé tel quel (universe-agnostique, audit Q8).
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

# ── Extension secondaire LOT S1 — registre séparé (ne PAS fusionner avec
# FEATURE_NAMES boules). Dict par jeu pour permettre l'enrichissement futur
# (features positionnelles basse/haute/value) sans refactor de cette structure.
# Pour CE lot : la feature reine `*_in_T1` seule.
SECONDARY_FEATURE_NAMES: dict[str, tuple[str, ...]] = {
    "loto": ("chance_in_T1",),
    "em": ("etoiles_in_T1",),
}

# ── Extension secondaire LOT S2 — features POSITIONNELLES (non-temporelles) :
# décrivent la grille seule (PAS d'overlap T-1) → baseline SIMPLE non appariée.
# Registre SÉPARÉ de SECONDARY_FEATURE_NAMES (*_in_T1) : c'est l'appartenance au
# registre qui pilote le routage de baseline (simple vs appariée) côté harness.
# Loto : chance_value seule (1 nombre, pas de basse/haute/écart).
# EM   : basse / haute / écart des 2 étoiles.
SECONDARY_POSITIONAL_NAMES: dict[str, tuple[str, ...]] = {
    "loto": ("chance_value",),
    "em": ("etoiles_basse", "etoiles_haute", "etoiles_ecart"),
}


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


# ════════════════════════════════════════════════════════════════════════
# EXTENSION SECONDAIRE — LOT S1 : feature reine `*_in_T1` (chance / etoiles)
# ════════════════════════════════════════════════════════════════════════

# Noms de features secondaire connus de ce lot (ensemble plat dérivé du
# registre par jeu) — utilisé pour les gardes de validation des bins.
_SECONDARY_IN_T1_NAMES: frozenset[str] = frozenset(
    name for names in SECONDARY_FEATURE_NAMES.values() for name in names
)

# LOT S2 — ensemble plat des noms positionnels (gardes / messages d'erreur).
_SECONDARY_POSITIONAL_NAMES: frozenset[str] = frozenset(
    name for names in SECONDARY_POSITIONAL_NAMES.values() for name in names
)


def _coerce_secondary_set(secondary) -> set[int]:
    """Normalise un secondaire en set[int], quelle que soit sa forme.

    Gère l'asymétrie Loto/EM (cf. backtest_hybride._compute_matches:456-463) :
        - int               → {int}            (Loto chance)
        - list/tuple/set     → set(...)         (EM étoiles, ou liste Loto)
        - None / autre       → set()            (défense)
    """
    if isinstance(secondary, bool):
        # bool est sous-classe de int — exclu explicitement (défense).
        return set()
    if isinstance(secondary, int):
        return {secondary}
    if isinstance(secondary, (list, tuple, set, frozenset)):
        return {int(x) for x in secondary}
    return set()


def extract_secondary_in_t1(grille_secondary, prev_secondary) -> dict[str, float]:
    """Calcule l'overlap secondaire de la grille avec le tirage T-1.

    Feature reine `*_in_T1` : nombre de numéros secondaire de la grille
    présents dans le secondaire du tirage chronologiquement précédent (T-1).

    Le NOM de la feature est dérivé de la cardinalité du secondaire de la
    GRILLE (invariant par jeu : Loto = 1 chance, EM = 2 étoiles) :
        - 1 élément  → "chance_in_T1"   (Loto)   ∈ {0, 1}
        - 2 éléments → "etoiles_in_T1"  (EM)     ∈ {0, 1, 2}

    Args:
        grille_secondary: secondaire de la grille générée — int (Loto) ou
                          list/tuple/set (EM). Normalisé en set.
        prev_secondary: secondaire du tirage T-1 (list[int] triée, cf. audit
                        Q4/Q6 — TirageRecord.secondary). Normalisé en set.

    Returns:
        dict 1-clé {feature_name: overlap_float}. Le caller (harness) accumule
        dans un dict parallèle indexé par feature_name.

    Note:
        Aucun garde sur idx=0 ici (responsabilité du caller — skip si pas de
        T-1, cf. audit vigilance #6). Si prev_secondary vide → overlap 0.0.
    """
    grille_set = _coerce_secondary_set(grille_secondary)
    prev_set = _coerce_secondary_set(prev_secondary)
    overlap = float(len(grille_set & prev_set))
    feature_name = "chance_in_T1" if len(grille_set) <= 1 else "etoiles_in_T1"
    return {feature_name: overlap}


def extract_secondary_positional(grille_secondary, game: str) -> dict[str, float]:
    """Features POSITIONNELLES (non-temporelles) du secondaire d'une grille.

    Décrivent la grille SEULE — aucun overlap T-1 (≠ extract_secondary_in_t1).
    Le jeu courant pilote l'ensemble des features (arbitrage Jyppy #2 : param
    `game` explicite, PAS d'inférence par cardinalité).

        game="loto" → {"chance_value": <valeur de la chance>}          ∈ [1, 10]
        game="em"   → {"etoiles_basse": min, "etoiles_haute": max,
                       "etoiles_ecart": max - min}    basse∈[1,11] haute∈[2,12]
                                                       ecart∈[1,11] (jamais 0)

    Args:
        grille_secondary: secondaire de la grille — int (Loto) / list/tuple/set
                          (EM). Normalisé via _coerce_secondary_set.
        game: "loto" ou "em".

    Returns:
        dict des features positionnelles. Dict VIDE en défense si le secondaire
        est mal formé (Loto vide / EM < 2 étoiles) — le caller l'ignore alors.
    """
    s = _coerce_secondary_set(grille_secondary)
    if game == "loto":
        if not s:
            return {}  # défense — chance manquante
        return {"chance_value": float(next(iter(s)))}
    # EM : besoin de 2 étoiles distinctes
    if len(s) < 2:
        return {}  # défense — étoiles manquantes/incomplètes
    basse, haute = float(min(s)), float(max(s))
    return {
        "etoiles_basse": basse,
        "etoiles_haute": haute,
        "etoiles_ecart": haute - basse,
    }


def build_secondary_bins(feature_name: str) -> np.ndarray:
    """Edges de bins entiers petit-univers pour les features secondaire.

    Distinct de build_bins (boules) — ne le touche pas, ne fusionne pas les
    registres (audit vigilance #2/#3). build_bins boules lève toujours
    ValueError sur un nom secondaire, et réciproquement.

    Choix figés LOT S1 (`*_in_T1`, temporelles) :
        chance_in_T1   : edges [0, 1, 2]      → 2 bins (valeurs 0/1)
        etoiles_in_T1  : edges [0, 1, 2, 3]   → 3 bins (valeurs 0/1/2)

    Choix figés LOT S2 (positionnelles, non-temporelles) :
        chance_value   : edges [1..11]        → 10 bins (valeurs 1..10)
        etoiles_basse  : edges [1..12]        → 11 bins (valeurs 1..11)
        etoiles_haute  : edges [2..13]        → 11 bins (valeurs 2..12)
        etoiles_ecart  : edges [1..12]        → 11 bins (valeurs 1..11, écart≥1)

    np.histogram place value v dans le bin [edge_i, edge_{i+1}) ; le dernier
    bin est fermé à droite. Avec ces edges entiers, chaque valeur tombe dans
    son propre bin. Les edges positionnelles sont calés sur le SUPPORT RÉEL
    (pas de bin 0 pour l'écart : 2 étoiles distinctes → écart ≥ 1).

    Args:
        feature_name: nom secondaire (`*_in_T1` LOT S1 ou positionnelle LOT S2).

    Returns:
        np.ndarray des edges (len = n_bins + 1).

    Raises:
        ValueError si feature_name inconnu des registres secondaire.
    """
    # ── LOT S1 — `*_in_T1` (intact) ──────────────────────────────────
    if feature_name == "chance_in_T1":
        return np.array([0.0, 1.0, 2.0], dtype=np.float64)
    if feature_name == "etoiles_in_T1":
        return np.array([0.0, 1.0, 2.0, 3.0], dtype=np.float64)
    # ── LOT S2 — positionnelles (additif) ────────────────────────────
    if feature_name == "chance_value":
        return np.arange(1, 12, 1, dtype=np.float64)   # [1..11] → valeurs 1..10
    if feature_name == "etoiles_basse":
        return np.arange(1, 13, 1, dtype=np.float64)   # [1..12] → valeurs 1..11
    if feature_name == "etoiles_haute":
        return np.arange(2, 14, 1, dtype=np.float64)   # [2..13] → valeurs 2..12
    if feature_name == "etoiles_ecart":
        return np.arange(1, 13, 1, dtype=np.float64)   # [1..12] → valeurs 1..11
    raise ValueError(
        f"build_secondary_bins: feature_name {feature_name!r} not in "
        f"secondary registries {sorted(_SECONDARY_IN_T1_NAMES | _SECONDARY_POSITIONAL_NAMES)}"
    )


@functools.lru_cache(maxsize=8)
def generate_secondary_in_t1_baseline(
    n: int = 100_000,
    sec_min: int = 1,
    sec_max: int = 10,
    count: int = 1,
    seed: int = DEFAULT_RANDOM_SEED,
) -> tuple[dict[str, float], ...]:
    """Baseline `*_in_T1` par SIMULATION APPARIÉE (arbitrage Jyppy #1).

    Modèle nul du recouvrement T-1 par PUR HASARD : pour chaque échantillon,
    on tire un secondaire random ET un T-1 random INDÉPENDANT, puis on calcule
    leur overlap. La distribution des overlaps est la baseline à laquelle
    HYBRIDE est comparé (JSD). Ce n'est PAS « secondaire random seul » — le
    T-1 random apparié est essentiel (cf. audit Q9, vigilance #4).

        Loto : 1 chance random ∈ [sec_min, sec_max] vs 1 T-1 chance random
               → overlap ∈ {0, 1}.
        EM   : 2 étoiles random distinctes vs 2 T-1 étoiles random distinctes
               → overlap ∈ {0, 1, 2}.

    Reproductible (random.Random(seed) LOCAL — pas de pollution du global).
    Cachée via lru_cache (clé = n, sec_min, sec_max, count, seed). Tuple
    immuable retourné — même pattern que generate_random_baseline.

    Args:
        n: nombre d'échantillons (default 100_000).
        sec_min/sec_max: bornes univers secondaire, inclus (Loto 1-10 / EM 1-12).
        count: nb de numéros secondaire (Loto 1 / EM 2).
        seed: graine reproductibilité (default 42).

    Returns:
        tuple[dict, ...] de n dicts {feature_name: overlap_float}.
    """
    rng = random.Random(seed)
    universe = list(range(sec_min, sec_max + 1))
    feature_name = "chance_in_T1" if count <= 1 else "etoiles_in_T1"
    out: list[dict[str, float]] = []
    for _ in range(n):
        grille_sec = rng.sample(universe, count)
        prev_sec = rng.sample(universe, count)
        overlap = float(len(set(grille_sec) & set(prev_sec)))
        out.append({feature_name: overlap})
    return tuple(out)


@functools.lru_cache(maxsize=8)
def generate_secondary_positional_baseline(
    n: int = 100_000,
    sec_min: int = 1,
    sec_max: int = 12,
    count: int = 2,
    seed: int = DEFAULT_RANDOM_SEED,
    game: str | None = None,
) -> tuple[dict[str, float], ...]:
    """Baseline SIMPLE NON appariée pour les features positionnelles (LOT S2).

    Modèle nul = tirage random uniforme du secondaire SEUL (PAS de T-1, PAS
    d'appariement — ≠ generate_secondary_in_t1_baseline). Pour chaque échantillon
    on tire `count` numéros secondaire DISTINCTS et on en extrait les features
    positionnelles via extract_secondary_positional (source unique de vérité, DRY).

        Loto : 1 chance random ∈ [sec_min, sec_max]      → {chance_value}
        EM   : 2 étoiles random distinctes ∈ [...]        → {basse, haute, ecart}

    Reproductible (random.Random(seed) LOCAL — pas de pollution du global).
    Cachée via lru_cache (clé = n, sec_min, sec_max, count, seed, game). Tuple
    immuable retourné — même pattern que les deux autres baselines.

    Args:
        n: nombre d'échantillons (default 100_000).
        sec_min/sec_max: bornes univers secondaire, inclus (Loto 1-10 / EM 1-12).
        count: nb de numéros secondaire (Loto 1 / EM 2).
        seed: graine reproductibilité (default 42).
        game: "loto" ou "em" — pilote les features extraites (arbitrage #2).
              OBLIGATOIRE (pas de défaut silencieux : un défaut produirait des
              features EM sur un run Loto = bug masqué → on plante clair).

    Returns:
        tuple[dict, ...] de n dicts de features positionnelles.

    Raises:
        ValueError si game non fourni / inconnu.
    """
    if game not in ("loto", "em"):
        raise ValueError(
            f"generate_secondary_positional_baseline: game must be 'loto' or 'em', "
            f"got {game!r} (defaut silencieux interdit — cf. revue Jyppy)"
        )
    rng = random.Random(seed)
    universe = list(range(sec_min, sec_max + 1))
    out: list[dict[str, float]] = []
    for _ in range(n):
        sample = rng.sample(universe, count)
        out.append(extract_secondary_positional(sample, game))
    return tuple(out)


# ════════════════════════════════════════════════════════════════════════
# MONTE CARLO NOISE FLOOR — plancher de bruit générique (LOT V_X.F)
# ════════════════════════════════════════════════════════════════════════
#
# Qualifie un JSD observé de « matériel » (significatif) vs « bruit
# d'échantillonnage ». Brique GÉNÉRIQUE pilotée par (values, bins) — donc
# réutilisable telle quelle pour les boules, le secondaire `*_in_T1` et toute
# feature future (positionnelle…) sans dispatch par feature_name.
#
# Modèle nul = OPTION B (audit 2026-06-05, double cross-review confirmée) :
#   - on rééchantillonne n_samples valeurs AVEC REMISE dans la baseline 100k
#     FIXE (= la même référence que le statistique observé),
#   - on calcule le JSD du rééchantillon vs cette MÊME réf 100k fixe,
#   - répété K fois → loi nulle empirique du JSD « aucune vraie différence ».
# Cela reproduit fidèlement l'asymétrie ~20k (HYBRIDE) / 100k (réf) du JSD
# réellement mesuré, en conditionnant sur la réf R fixe.


def _jsd_from_normalized(p: np.ndarray, q: np.ndarray, base: str = "e") -> float:
    """JSD entre 2 distributions DÉJÀ normalisées (somment à 1, smoothing > 0).

    Variante interne de compute_feature_jsd qui NE re-normalise PAS : dans la
    boucle Monte Carlo, q (la référence 100k) est normalisée une seule fois
    en amont (audit Q4 — ne pas re-histogrammer la réf K fois). Réutilise
    _kl_divergence et la même convention de base que compute_feature_jsd.
    """
    m = 0.5 * (p + q)
    jsd_nat = 0.5 * _kl_divergence(p, m) + 0.5 * _kl_divergence(q, m)
    # Floor numérique : roundoff KL peut produire ε négatif (idem compute_feature_jsd).
    jsd_nat = max(0.0, jsd_nat)
    if base == "2":
        return jsd_nat / float(np.log(2))
    return float(jsd_nat)


def compute_noise_floor(
    reference_values,
    bins,
    n_samples: int,
    observed_jsd: float,
    *,
    k: int = 1000,
    seed: int = DEFAULT_RANDOM_SEED,
    quantile: float = 0.95,
    base: str = "e",
) -> dict:
    """Plancher de bruit Monte Carlo (modèle nul Option B) pour 1 feature.

    Fonction PURE, générique (pilotée par values + bins), dash-ready (dict
    structuré, zéro print). Offline pur — aucune dépendance prod.

    Args:
        reference_values: population de référence = les valeurs de feature de
            la baseline 100k (ex. [b[fname] for b in generate_random_baseline()]).
            C'est dans CETTE population qu'on rééchantillonne (bootstrap).
        bins: edges des bins — DOIVENT être les MÊMES que ceux du JSD observé
            (build_bins / build_secondary_bins). Règle dure V_X.F.
        n_samples: taille réelle du run HYBRIDE pour CETTE feature
            (= len(hybride_vals)). Le plancher reflète le bruit À CETTE taille.
        observed_jsd: le JSD HYBRIDE vs baseline déjà calculé (feature_jsd[fname]) —
            sert à dériver la p-value (proportion de répliques nulles ≥ observé).

    Keyword Args:
        k: nombre de répliques Monte Carlo (1000 boules / 10000 secondaire).
        seed: graine reproductibilité. RNG LOCAL np.random.default_rng(seed) —
            JAMAIS le RNG global (ne pollue pas le lru_cache des baselines).
        quantile: niveau du plancher (0.95 → seuil 5%).
        base: "e" (default, aligné feature_jsd) ou "2".

    Returns:
        dict structuré (dash-ready) :
            noise_floor : quantile demandé de la loi nulle = LE plancher
            p99_null    : quantile 99% (seuil 1% optionnel, gratuit)
            mean_null   : moyenne des JSD nuls
            std_null    : écart-type échantillon des JSD nuls
            p_value     : proportion des JSD nuls ≥ observed_jsd (pour la FDR)
            k, n_samples, n_reference, quantile, base : métadonnées

    Raises:
        ValueError si base invalide, reference_values vide, n_samples ≤ 0, k ≤ 0.
    """
    if base not in ("e", "2"):
        raise ValueError(f"base must be 'e' or '2', got {base!r}")
    ref = np.asarray(reference_values, dtype=np.float64)
    n_ref = int(ref.shape[0]) if ref.ndim else 0
    if n_ref == 0:
        raise ValueError("compute_noise_floor: reference_values is empty")
    if n_samples <= 0:
        raise ValueError(
            f"compute_noise_floor: n_samples must be > 0, got {n_samples}"
        )
    if k <= 0:
        raise ValueError(f"compute_noise_floor: k must be > 0, got {k}")

    # Référence fixe q — normalisée UNE SEULE FOIS (Option B : on conditionne
    # sur la même réf que le statistique observé). PAS dans la boucle K.
    q = _histogram_normalize(ref, bins)

    # RNG LOCAL — pas de pollution du global ni du lru_cache des baselines.
    rng = np.random.default_rng(seed)
    jsd_null = np.empty(k, dtype=np.float64)
    for i in range(k):
        # Bootstrap : n_samples indices AVEC REMISE dans la réf 100k.
        idx = rng.integers(0, n_ref, n_samples)
        p = _histogram_normalize(ref[idx], bins)
        jsd_null[i] = _jsd_from_normalized(p, q, base=base)

    noise_floor = float(np.quantile(jsd_null, quantile))
    p99_null = float(np.quantile(jsd_null, 0.99))
    # p-value Monte Carlo avec convention ADD-ONE : (1 + #{nul ≥ observé}) / (K+1).
    # Une p-value MC de 0.0 strict est incorrecte (avec K répliques finies on ne
    # peut conclure que p < 1/K, jamais p=0) → l'add-one la borne à 1/(K+1).
    # Convention standard des tests Monte Carlo (Davison & Hinkley, North et al.).
    n_ge = int(np.count_nonzero(jsd_null >= observed_jsd))
    p_value = (1 + n_ge) / (k + 1)

    return {
        "noise_floor": round(noise_floor, 6),
        "p99_null": round(p99_null, 6),
        "mean_null": round(float(np.mean(jsd_null)), 6),
        "std_null": round(float(np.std(jsd_null, ddof=1)), 6) if k >= 2 else 0.0,
        "p_value": round(p_value, 6),
        "k": k,
        "n_samples": n_samples,
        "n_reference": n_ref,
        "quantile": quantile,
        "base": base,
    }


# ════════════════════════════════════════════════════════════════════════
# CORRECTION MULTI-FEATURES — Benjamini-Hochberg FDR (LOT V_X.F)
# ════════════════════════════════════════════════════════════════════════
#
# Tester K features simultanément gonfle les faux positifs (~30% sur 7 tests
# au seuil 5% sans correction — confirmé par les 2 cross-reviews). BH contrôle
# le False Discovery Rate (taux attendu de faux positifs PARMI les rejets) au
# niveau alpha, moins conservateur que Bonferroni (qui contrôle le FWER).
#
# Procédure BH standard :
#   1. trier les m p-values croissantes : p_(1) ≤ ... ≤ p_(m)
#   2. trouver le plus grand rang i tel que p_(i) ≤ (i/m)·alpha
#   3. rejeter H0 (= matériel) pour TOUS les rangs ≤ i (step-up), même si
#      certains p_(j<i) dépassent leur propre seuil (i/m)·alpha.
# Le "bh_threshold" rapporté par feature est son seuil de rang (i/m)·alpha.


def apply_fdr_correction(p_values: dict, alpha: float = 0.05) -> dict:
    """Correction Benjamini-Hochberg sur un ensemble de p-values multi-features.

    Fonction PURE, sans dépendance externe (pas de statsmodels). Contrôle le
    FDR au niveau alpha sur l'ensemble des features testées simultanément.

    Args:
        p_values: dict[str, float] — feature_name → p-value (typiquement la
            clé "p_value" retournée par compute_noise_floor).
        alpha: niveau FDR cible (default 0.05).

    Returns:
        dict[str, dict] — 1 entrée par feature :
            {
              "p_value": <p-value d'entrée>,
              "is_material_fdr": <bool : H0 rejetée par BH = signal matériel>,
              "bh_threshold": <seuil de rang (rank/m)·alpha pour cette feature>,
            }
        Cas dégénérés :
            - m = 0 (dict vide)  → {} (rien à corriger).
            - m = 1              → BH ≡ test simple : matériel si p ≤ alpha.

    Raises:
        ValueError si alpha ∉ ]0, 1].
    """
    if not (0.0 < alpha <= 1.0):
        raise ValueError(f"alpha must be in ]0, 1], got {alpha}")

    m = len(p_values)
    if m == 0:
        return {}

    # Tri croissant par p-value (stable sur le nom pour déterminisme des ex-aequo).
    items = sorted(p_values.items(), key=lambda kv: (kv[1], kv[0]))

    # Step-up : plus grand rang i (1-indexé) tel que p_(i) ≤ (i/m)·alpha.
    # Tout rang ≤ i_max est rejeté (matériel), y compris les p_(j<i_max) qui
    # ne satisfont pas individuellement leur seuil.
    max_rejected_rank = 0
    for rank, (_, p) in enumerate(items, start=1):
        if p <= (rank / m) * alpha:
            max_rejected_rank = rank

    out: dict[str, dict] = {}
    for rank, (name, p) in enumerate(items, start=1):
        bh_threshold = (rank / m) * alpha
        out[name] = {
            "p_value": round(float(p), 6),
            "is_material_fdr": rank <= max_rejected_rank,
            "bh_threshold": round(bh_threshold, 6),
        }
    return out
