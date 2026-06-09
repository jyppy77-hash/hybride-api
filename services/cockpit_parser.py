"""
Cockpit Métrique V_X.F — parser stateless du JSON de run OOS.
=============================================================
Cœur testable du cockpit admin /admin/cockpit. Une seule fonction publique
pure : `normalize_run(raw)` qui transforme le JSON d'un run de backtest OOS
V_X.F (produit hors-ligne par tools/backtest_hybride.py) en un view-model
stable et défensif.

GARDE-FOU ABSOLU — MUR ÉTANCHE tools/ <-> runtime :
    Ce module n'importe JAMAIS tools.backtest_hybride, tools.signature_features
    ni aucun tools.*. Le JSON est l'unique objet-frontière. Seul `json` (stdlib)
    pourrait être nécessaire ; ici aucune I/O n'est faite (le caller fournit le
    dict déjà parsé). Voir tests/test_cockpit_wall.py (scan AST qui casse le
    build si un fichier runtime importe tools).

Principe défensif : les vieux runs ont un schéma réduit (pas de secondary, pas
de stratification, pas de effect_tier, pas de noise_floor, pas d'explicabilité
moteur). Chaque étage porte un flag `present: bool`. Tout est lu via .get(...) —
jamais de KeyError.

CONFINEMENT PDF : l'étage `explainability` (empreinte de génération par numéro)
est ajouté au view-model mais N'EST JAMAIS rendu par cockpit_pdf_generator.py
(liste blanche de clés explicite, comme `diff` déjà présent et non rendu). Le
panneau explicabilité reste donc ÉCRAN admin uniquement.

Read-only / stateless : aucune écriture, aucun état module, aucun I/O.
"""

_DEGRADED_ERROR = "schéma non reconnu"


def _f(value):
    """Coerce numérique en float, sinon None. Préserve None ; ignore les bool."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _degraded(error: str = _DEGRADED_ERROR) -> dict:
    """View-model dégradé : tous les étages present=False + champ error.

    Renvoyé quand le JSON n'a même pas un bloc results_config_actuelle
    exploitable. L'UI affiche un message propre, jamais un crash.
    """
    return {
        "meta": {
            "present": False,
            "game": None, "n_tirages": None, "n_grilles_per_tirage": None,
            "mode": None, "run_mode": None, "harness_version": None,
            "include_secondary": False, "noise_floor": False,
            "tirages_range": {"first": None, "last": None},
            "elapsed_seconds": None, "limitations_mvp": [],
        },
        "is_comparative": False,
        "signature": {"present": False, "rows": []},
        "conformity": {"present": False, "rows": []},
        "stratification": {"present": False, "jsd": None,
                           "hybride": {}, "baseline": {}, "real": {}},
        "secondary": {"present": False, "rows": [], "anj_disclaimer": None},
        "explainability": {"present": False},
        "diff": {"present": False, "delta_gagnantes_pct_global": None,
                 "delta_stratification": None, "config_actuelle": {}, "config_test": {}},
        "error": error,
    }


def _build_meta(raw: dict) -> dict:
    """ÉTAGE header — lu sous raw['metadata'] (présent vieux ET neuf schémas)."""
    md = raw.get("metadata") or {}
    rng = md.get("tirages_replayed_range") or {}   # clé source = tirages_replayed_range
    return {
        "present": bool(md),
        "game": md.get("game"),
        "n_tirages": md.get("n_tirages"),
        "n_grilles_per_tirage": md.get("n_grilles_per_tirage"),
        "mode": md.get("mode"),
        "run_mode": md.get("run_mode"),
        "harness_version": md.get("harness_version"),
        "include_secondary": bool(md.get("include_secondary", False)),
        "noise_floor": bool(md.get("noise_floor", False)),
        "tirages_range": {"first": rng.get("first"), "last": rng.get("last")},
        "elapsed_seconds": _f(md.get("elapsed_seconds")),
        "limitations_mvp": list(md.get("limitations_mvp") or []),
    }


def _signature_row(feat, jsd, family, eff, ism, nf) -> dict:
    """Une ligne de signature, jointures depuis les 3 dicts unifiés tier2.

    effect_tier / is_material / noise_floor sont indexés par TOUS les noms de
    features ensemble (primary + secondary chance_* + stratification).
    noise_floor[feat] est un sous-dict {noise_floor, p_value, ...}.
    """
    nfd = nf.get(feat) if isinstance(nf.get(feat), dict) else {}
    return {
        "feature": feat,
        "jsd": _f(jsd),
        "effect_tier": eff.get(feat),
        "noise_floor": _f(nfd.get("noise_floor")),
        "p_value": _f(nfd.get("p_value")),
        "is_material": ism.get(feat),
        "family": family,
    }


def _build_signature(t2: dict) -> dict:
    """ÉTAGE 1 — agrège primary + secondary + stratification, trié JSD décroissant."""
    eff = t2.get("effect_tier") or {}
    ism = t2.get("is_material") or {}
    nf = t2.get("noise_floor") or {}

    rows = []
    for feat, jsd in (t2.get("feature_jsd") or {}).items():
        rows.append(_signature_row(feat, jsd, "primary", eff, ism, nf))

    sec = t2.get("secondary") or {}
    for feat, jsd in (sec.get("feature_jsd") or {}).items():
        rows.append(_signature_row(feat, jsd, "secondary", eff, ism, nf))

    strat = t2.get("stratification") or {}
    strat_jsd = (strat.get("feature_jsd") or {}).get("stratification")
    if strat_jsd is not None:
        rows.append(_signature_row("stratification", strat_jsd, "stratification", eff, ism, nf))

    # Tri JSD décroissant, stable (None traité comme -inf → en queue)
    rows.sort(key=lambda r: r["jsd"] if r["jsd"] is not None else float("-inf"),
              reverse=True)
    return {"present": bool(rows), "rows": rows}


def _build_conformity(rca: dict) -> dict:
    """ÉTAGE 2 — Tier 1. pct normalisé : out_of_bounds | below_min | above_max."""
    t1 = rca.get("tier1") or {}
    rows = []
    for feat, d in t1.items():
        if not isinstance(d, dict):
            continue
        pct = d.get("pct_out_of_bounds")
        if pct is None:
            pct = d.get("pct_below_min")
        if pct is None:
            pct = d.get("pct_above_max")
        rows.append({
            "feature": feat,
            "mean": _f(d.get("mean")),
            "median": _f(d.get("median")),
            "std": _f(d.get("std")),
            "min": _f(d.get("min")),
            "max": _f(d.get("max")),
            "pct_out_of_bounds": _f(pct),
        })
    return {"present": bool(rows), "rows": rows}


def _build_stratification(t2: dict, raw: dict) -> dict:
    """ÉTAGE 4a — bloc dédié stratification (la visu de la décision produit)."""
    strat = t2.get("stratification") or {}
    real = strat.get("real_distribution")
    if not real:
        real = raw.get("stratification_distribution_real_empirical")
    return {
        "present": bool(strat),
        "jsd": _f((strat.get("feature_jsd") or {}).get("stratification")),
        "hybride": strat.get("hybride_distribution") or {},
        "baseline": strat.get("baseline_distribution") or {},
        "real": real or {},
    }


def _build_secondary(t2: dict) -> dict:
    """ÉTAGE 4b — secondaire (in_T1 + positionnelles EM) + disclaimer ANJ verbatim."""
    sec = t2.get("secondary") or {}
    eff = t2.get("effect_tier") or {}
    ism = t2.get("is_material") or {}
    rows = []
    for feat, jsd in (sec.get("feature_jsd") or {}).items():
        rows.append({
            "feature": feat,
            "jsd": _f(jsd),
            "effect_tier": eff.get(feat),
            "is_material": ism.get(feat),
        })
    return {
        "present": bool(sec),
        "rows": rows,
        "anj_disclaimer": sec.get("anj_disclaimer"),
    }


# ── ÉTAGE Empreinte — explicabilité moteur (palier 1, ÉCRAN admin uniquement) ──

def _int_keys(d: dict) -> list:
    """Clés '12' → 12, triées croissant. Ignore les clés non entières."""
    out = []
    for k in d or {}:
        try:
            out.append(int(k))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def _zone_position_label(zone_str, ordered_zones) -> str:
    """Position QUALITATIVE d'une zone, SANS chiffre (garde-fou ANJ encadré).

    L'encadré « Lecture rapide » ne doit jamais nommer un numéro ni contenir de
    chiffre — on décrit donc la zone par sa position relative dans la grille.
    """
    if zone_str not in ordered_zones:
        return "l'ensemble de la grille"
    k = len(ordered_zones)
    if k <= 1:
        return "l'ensemble de la grille"
    frac = ordered_zones.index(zone_str) / (k - 1)
    if frac < 0.34:
        return "le bas de la grille"
    if frac < 0.67:
        return "le centre de la grille"
    return "le haut de la grille"


def _qual_level(x, lo: float, hi: float):
    """Niveau qualitatif sans chiffre : faible / modéré / fort. None si non num."""
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return None
    if x < lo:
        return "faible"
    if x < hi:
        return "modéré"
    return "fort"


def _build_lecture_rapide(expl, ordered_zones, dev_iz, corr_hx, corr_brake) -> list:
    """Synthèse STRUCTURELLE — JAMAIS un numéro, JAMAIS un chiffre (ANJ §0.3).

    Décrit zones / leviers / dispersion en mots. Chaque ligne satisfait
    `not any(c.isdigit())` (testé). Réutilisable plus tard pour un PDF diffusable
    (mais hors de ce lot : écran admin uniquement).
    """
    zone_by = expl.get("correlation_with_zone") or {}
    lines = []

    # 1) Zone concentrant la surpondération (somme des déviations intra-zone > 0)
    zone_pos = {}
    for n_str, dev in (dev_iz or {}).items():
        z = zone_by.get(n_str)
        if (z and z != "none" and isinstance(dev, (int, float))
                and not isinstance(dev, bool) and dev > 0):
            zone_pos[z] = zone_pos.get(z, 0.0) + dev
    if zone_pos:
        top_zone = max(zone_pos, key=zone_pos.get)
        lines.append("La surpondération de génération se concentre vers "
                     + _zone_position_label(top_zone, ordered_zones) + ".")

    # 2) Dispersion intra-zone (amplitude max - min)
    vals = [v for v in (dev_iz or {}).values()
            if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if vals:
        lvl = _qual_level(max(vals) - min(vals), 0.15, 0.40)
        if lvl == "fort":
            lines.append("Dispersion intra-zone marquée : préférences structurelles nettes "
                         "au-delà de la contrainte d'un numéro par zone.")
        elif lvl == "modéré":
            lines.append("Dispersion intra-zone modérée au-delà de la contrainte "
                         "d'un numéro par zone.")
        elif lvl == "faible":
            lines.append("Dispersion intra-zone faible : génération proche de l'uniforme "
                         "intra-zone.")

    # 3) Levier d'exclusion du tirage précédent (hard-exclude T-1)
    hx = [v for v in (corr_hx or {}).values()
          if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if hx:
        lvl = _qual_level(sum(hx) / len(hx), 0.05, 0.20)
        if lvl:
            lines.append("Levier d'exclusion du tirage précédent actif à un niveau "
                         + lvl + ".")

    # 4) Frein persistant inter-tirages (V110)
    bk = [v for v in (corr_brake or {}).values()
          if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if bk and any(v > 0 for v in bk):
        lvl = _qual_level(sum(bk) / len(bk), 0.05, 0.20)
        if lvl:
            lines.append("Frein persistant inter-tirages actif à un niveau " + lvl + ".")
    elif bk:
        lines.append("Frein persistant inter-tirages inactif sur ce run.")

    return lines


def _build_explainability(rca: dict) -> dict:
    """ÉTAGE Empreinte — lit rca['engine_explainability'] (palier 1, offline).

    Frère de tier1/tier2 (PAS sous tier2). Game-agnostique : le secondaire EM
    (étoiles) / Loto (chance) est normalisé en clés neutres (secondary_label +
    secondary_rows fusionnées numéro|fréquence|déviation). Défensif : vieux run
    sans la clé → present=False (carte masquée, zéro crash).

    Aucun import tools.* : lit uniquement le dict déjà parsé (mur étanche).
    """
    expl = rca.get("engine_explainability") or {}
    if not expl:
        return {"present": False}

    dev_iz = expl.get("deviation_from_uniform_intra_zone") or {}
    dev_g = expl.get("deviation_from_uniform") or {}
    freq = expl.get("frequency_by_number") or {}
    zone_by = expl.get("correlation_with_zone") or {}

    numbers = _int_keys(dev_iz) or _int_keys(freq)

    # Ordre canonique des zones (tri par borne basse) — pour la position qualitative
    uniq = {z for z in zone_by.values() if z and z != "none"}

    def _zlo(z):
        try:
            return int(str(z).split("-")[0])
        except (ValueError, IndexError):
            return 1 << 30

    ordered_zones = sorted(uniq, key=_zlo)

    # Bloc B — top boules enrichi de la zone
    top_numbers = []
    for r in expl.get("top_numbers") or []:
        if not isinstance(r, dict):
            continue
        n = r.get("number")
        top_numbers.append({
            "number": n,
            "frequency": r.get("frequency"),
            "deviation_from_uniform": _f(r.get("deviation_from_uniform")),
            "deviation_from_uniform_intra_zone": _f(r.get("deviation_from_uniform_intra_zone")),
            "zone": zone_by.get(str(n)),
        })

    # Secondaire game-agnostique — UNE seule mini-table (numéro|fréquence|déviation)
    secondary_label = "star" if ("top_stars" in expl or "frequency_by_star" in expl) else "chance"
    freq_sec = expl.get("frequency_by_star" if secondary_label == "star" else "frequency_by_chance") or {}
    dev_sec = expl.get("deviation_from_uniform_secondary") or {}
    secondary_rows = [
        {
            "number": s,
            "frequency": freq_sec.get(str(s)),
            "deviation_from_uniform": _f(dev_sec.get(str(s))),
        }
        for s in (_int_keys(dev_sec) or _int_keys(freq_sec))
    ]

    lecture_rapide = _build_lecture_rapide(
        expl, ordered_zones, dev_iz,
        expl.get("correlation_with_hard_exclude"),
        expl.get("correlation_with_persistent_brake"),
    )

    return {
        "present": True,
        "total_grids": _f(expl.get("total_grids")),
        "uniform_expectation_per_number": _f(expl.get("uniform_expectation_per_number")),
        "ordered_zones": ordered_zones,
        "chart_numbers": numbers,
        "chart_deviation_intra_zone": [_f(dev_iz.get(str(n))) for n in numbers],
        "chart_deviation_global": [_f(dev_g.get(str(n))) for n in numbers],
        "chart_zones": [zone_by.get(str(n)) for n in numbers],
        "top_numbers": top_numbers,
        "secondary_label": secondary_label,
        "secondary_rows": secondary_rows,
        "notes": expl.get("notes") or {},
        "lecture_rapide": lecture_rapide,
    }


def normalize_run(raw: dict) -> dict:
    """Normalise un JSON de run OOS V_X.F en view-model stable, défensif aux
    schémas partiels.

    Ne connaît QUE la forme du JSON. N'importe JAMAIS tools/. Pur, sans I/O,
    sans état. Renvoie toujours un dict (jamais d'exception sur schéma partiel).
    """
    rca = raw.get("results_config_actuelle") if isinstance(raw, dict) else None
    if not isinstance(rca, dict) or not rca:
        return _degraded()

    t2 = rca.get("tier2") or {}

    run_mode = (raw.get("metadata") or {}).get("run_mode")
    cfg_a = raw.get("config_actuelle")
    cfg_t = raw.get("config_test")
    is_comparative = bool(run_mode and run_mode != "single_no_compare" and cfg_a != cfg_t)

    diff_raw = raw.get("diff") or {}
    diff = {
        "present": is_comparative and bool(diff_raw),
        "delta_gagnantes_pct_global": _f(diff_raw.get("delta_gagnantes_pct_global")),
        "delta_stratification": diff_raw.get("delta_stratification"),
        "config_actuelle": cfg_a or {},
        "config_test": cfg_t or {},
    }

    return {
        "meta": _build_meta(raw),
        "is_comparative": is_comparative,
        "signature": _build_signature(t2),
        "conformity": _build_conformity(rca),
        "stratification": _build_stratification(t2, raw),
        "secondary": _build_secondary(t2),
        "explainability": _build_explainability(rca),
        "diff": diff,
        "error": None,
    }
