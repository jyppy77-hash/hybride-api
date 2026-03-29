"""
Chat utilities — EuroMillions thin wrapper.
Shared utilities in base_chat_utils.py.
EM-specific: tirage/stats/grille/generation formatting, session context, star pairs.
"""

from datetime import date

from services.chat_detectors_em import _detect_numero_em
from services.chat_detectors import _detect_tirage

# Re-export shared functions (consumers import from here)
from services.base_chat_utils import (  # noqa: F401
    _format_date_fr, _format_periode_fr,
    _format_pairs_context_base, _format_triplets_context_base,
    _format_complex_context_base,
    _format_stats_context_base, _format_grille_context_base,
    _build_session_context_base,
)

FALLBACK_RESPONSE_EM = (
    "\U0001f916 Je suis momentanément indisponible. "
    "Réessaie dans quelques secondes ou consulte la FAQ !"
)


# ────────────────────────────────────────────
# Formatage contexte pour Gemini — EM
# ────────────────────────────────────────────

def _format_tirage_context_em(tirage: dict) -> str:
    """Formate les resultats d'un tirage EM en bloc de contexte pour Gemini."""
    date_fr = _format_date_fr(str(tirage["date"]))
    boules = " - ".join(str(b) for b in tirage["boules"])
    etoiles = " - ".join(str(e) for e in tirage["etoiles"])
    return (
        f"[RÉSULTAT TIRAGE - {date_fr}]\n"
        f"Date du tirage : {date_fr}\n"
        f"Numéros principaux : {boules}\n"
        f"Étoiles : {etoiles}"
    )


def _format_stats_context_em(stats: dict) -> str:
    """Formate les stats d'un numero EM en bloc de contexte pour Gemini."""
    return _format_stats_context_base(stats, {"boule": "boule", "etoile": "étoile"}, 50)


def _format_grille_context_em(result: dict) -> str:
    """Formate l'analyse de grille EM en bloc de contexte pour Gemini."""
    return _format_grille_context_base(
        result, secondary_key="etoiles", secondary_label="étoiles",
        sum_range="75-175", low_threshold=25, high_label="26-50",
        match_key="etoiles_match", match_label=" + étoile(s) communes",
    )


def _format_complex_context_em(intent: dict, data) -> str:
    """Formate le resultat d'une requete complexe EM en contexte pour Gemini."""
    def _type_label(intent):
        return "étoiles" if intent["num_type"] == "etoile" else "boules"
    return _format_complex_context_base(intent, data, _type_label)


# ────────────────────────────────────────────
# Session context — EM
# ────────────────────────────────────────────

def _build_session_context_em(history, current_message: str) -> str:
    """Scanne l'historique EM pour extraire numeros/tirages. Retourne [SESSION] ou vide."""
    return _build_session_context_base(
        history, current_message,
        detect_numero_fn=_detect_numero_em, detect_tirage_fn=_detect_tirage,
        type_label_fn=lambda t: 'étoile' if t == 'etoile' else 'boule',
    )


# ────────────────────────────────────────────
# Pairs / Triplets / Star pairs — EM wrappers
# ────────────────────────────────────────────

def _format_pairs_context_em(pairs_data: dict) -> str:
    """Formate les correlations de paires EM en contexte pour Gemini."""
    return _format_pairs_context_base(pairs_data, "Boules EuroMillions")


def _format_star_pairs_context_em(star_data: dict) -> str:
    """Formate les paires d'etoiles EM en contexte pour Gemini."""
    lines = ["[CORRÉLATIONS DE PAIRES — Étoiles]"]
    lines.append(f"Total tirages analysés : {star_data['total_draws']}")
    for i, p in enumerate(star_data["pairs"], 1):
        lines.append(
            f"{i}. \u2b50{p['num_a']} + \u2b50{p['num_b']} "
            f"\u2192 {p['count']} fois ({p['percentage']}%)"
        )
    return "\n".join(lines)


def _format_triplets_context_em(triplets_data: dict) -> str:
    """Formate les correlations de triplets EM en contexte pour Gemini."""
    return _format_triplets_context_base(triplets_data, "Boules EuroMillions")


# ────────────────────────────────────────────
# Formatage generation de grille EM (Phase G)
# ────────────────────────────────────────────

def _format_generation_context_em(grid_data: dict) -> str:
    """Formate une grille EuroMillions generee en contexte pour Gemini."""
    nums = grid_data['nums']
    lines = ["[GRILLE GÉNÉRÉE PAR HYBRIDE]"]
    lines.append(f"Numéros : {nums}")
    if grid_data.get('etoiles'):
        lines.append(f"Étoiles : {grid_data['etoiles']}")
    if grid_data.get("forced_nums"):
        lines.append(f"Numéros imposés par l'utilisateur : {grid_data['forced_nums']}")
    if grid_data.get("forced_etoiles"):
        lines.append(f"Étoiles imposées par l'utilisateur : {grid_data['forced_etoiles']}")
    lines.append(f"Score de conformité : {grid_data['score']}/100")
    lines.append(f"Badges : {', '.join(grid_data.get('badges', []))}")
    lines.append(f"Mode : {grid_data.get('mode', 'balanced')}")

    # V43-bis: User exclusion constraints
    excl = grid_data.get("exclusions")
    if excl and any(excl.values()):
        lines.append("")
        lines.append("[CONTRAINTES UTILISATEUR]")
        for low, high in excl.get("exclude_ranges", []):
            if low == 1 and high == 31:
                lines.append(f"- Plage exclue : {low}-{high} (dates de naissance)")
            else:
                lines.append(f"- Plage exclue : {low}-{high}")
        for mult in excl.get("exclude_multiples", []):
            lines.append(f"- Multiples de {mult} exclus")
        for num in excl.get("exclude_nums", []):
            lines.append(f"- Numéro {num} exclu")
        lines.append("Tous les numéros générés respectent ces contraintes.")

    # Breakdown statistique par numero
    pairs = sum(1 for n in nums if n % 2 == 0)
    impairs = 5 - pairs
    bas = sum(1 for n in nums if n <= 25)
    hauts = 5 - bas
    somme = sum(nums)
    dispersion = max(nums) - min(nums)
    lines.append("")
    lines.append("[BREAKDOWN — Critères de sélection]")
    lines.append(f"Équilibre pair/impair : {pairs} pairs, {impairs} impairs")
    lines.append(f"Équilibre bas/haut (1-25 / 26-50) : {bas} bas, {hauts} hauts")
    lines.append(f"Somme des numéros : {somme} (cible optimale : 95-160)")
    lines.append(f"Dispersion (max - min) : {dispersion}")
    for n in nums:
        tags = []
        tags.append("pair" if n % 2 == 0 else "impair")
        tags.append("bas" if n <= 25 else "haut")
        if grid_data.get("forced_nums") and n in grid_data["forced_nums"]:
            tags.append("imposé par l'utilisateur")
        lines.append(f"  N°{n:02d} : {', '.join(tags)}")
    if grid_data.get('etoiles'):
        for e in grid_data['etoiles']:
            tags = []
            if grid_data.get("forced_etoiles") and e in grid_data["forced_etoiles"]:
                tags.append("imposée par l'utilisateur")
            lines.append(f"  \u2b50{e:02d} : {', '.join(tags) if tags else 'sélectionnée par le moteur'}")
    lines.append(
        "Ces critères sont STATISTIQUES et basés sur l'historique. "
        "L'EuroMillions reste un jeu de pur hasard, aucune grille ne garantit de gain."
    )

    lines.append("")
    lines.append(
        "IMPORTANT : Présente cette grille de manière engageante. "
        "Explique les critères (équilibre pair/impair, bas/haut, fréquences, retards). "
        "Si l'utilisateur demande pourquoi ces numéros, utilise le [BREAKDOWN] ci-dessus. "
        "Si des numéros ou étoiles ont été imposés, mentionne-le clairement. "
        "Rappelle que l'EuroMillions reste un jeu de pur hasard et qu'aucune grille ne garantit de gain."
    )
    lines.append(
        "DISCLAIMER SCORE : Quand tu mentionnes le score de conformité, TOUJOURS préciser que "
        "c'est un score interne basé sur les critères du moteur (équilibre, dispersion, fréquences) "
        "et que chaque combinaison a exactement la même probabilité mathématique de sortir au tirage. "
        "Le score NE mesure PAS une probabilité de gain."
    )
    return "\n".join(lines)
