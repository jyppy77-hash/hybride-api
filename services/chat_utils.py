"""
Chat utilities — Loto thin wrapper.
Shared utilities in base_chat_utils.py.
Loto-specific: tirage/stats/grille/generation formatting, session context, sponsor system.
"""

import json
import logging
from pathlib import Path
from datetime import date

from services.chat_detectors import _detect_numero, _detect_tirage

# Re-export shared functions (consumers import from here)
from services.base_chat_utils import (  # noqa: F401
    FALLBACK_RESPONSE,
    _strip_non_latin, _enrich_with_context,
    _clean_response, StreamBuffer,
    _MOIS_FR, _format_date_fr, _format_periode_fr,
    _format_pairs_context_base, _format_triplets_context_base,
    _format_complex_context_base,
    _format_stats_context_base, _format_grille_context_base,
    _build_session_context_base,
)

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────
# Systeme sponsor — insertion post-Gemini
# (kept here for patch compatibility with tests)
# ────────────────────────────────────────────

_SPONSORS_PATH = Path(__file__).resolve().parent.parent / "config" / "sponsors.json"
_sponsors_config: dict | None = None


def _load_sponsors_config() -> dict:
    """Charge la config sponsors depuis config/sponsors.json (cache en memoire)."""
    global _sponsors_config
    if _sponsors_config is not None:
        return _sponsors_config
    try:
        with open(_SPONSORS_PATH, encoding="utf-8") as f:
            _sponsors_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"[SPONSOR] Config introuvable ou invalide: {e}")
        _sponsors_config = {"enabled": False, "frequency": 3, "slots": {}}
    return _sponsors_config


def _get_sponsor_if_due(history: list, lang: str = "fr", module: str = "loto") -> str | None:
    """Retourne le texte sponsor si c'est le moment, None sinon."""
    config = _load_sponsors_config()
    if not config.get("enabled"):
        return None

    frequency = config.get("frequency", 3)
    bot_count = sum(1 for msg in history if msg.role == "assistant")
    bot_count += 1

    if bot_count % frequency != 0:
        return None

    cycle = bot_count // frequency

    if module == "em":
        slot_key_root = f"em_{lang}"
    else:
        slot_key_root = "loto_fr"

    slots = config.get("slots", {}).get(slot_key_root, {})
    if not slots:
        return None

    slot_key = "slot_a" if cycle % 2 == 1 else "slot_b"
    slot = slots.get(slot_key)

    if not slot or not slot.get("active"):
        other_key = "slot_b" if slot_key == "slot_a" else "slot_a"
        slot = slots.get(other_key)
        if not slot or not slot.get("active"):
            return None

    _default_id = "LOTO_FR_A" if module != "em" else f"EM_{lang.upper()}_A"
    sponsor_id = slot.get("id", _default_id)
    tagline = slot.get("tagline", {})
    text = tagline.get(lang, tagline.get("fr", ""))
    email = slot.get("url", "mailto:partenariats@lotoia.fr").replace("mailto:", "")

    if cycle % 2 == 1:
        msg = f"\U0001f4e2 {text} \u2014 {email}"
    else:
        msg = f"\u2014 {text} | {email}"

    return f"[SPONSOR:{sponsor_id}]{msg}"


def _strip_sponsor_from_text(text: str) -> str:
    """Supprime les lignes sponsor d'un message (pour nettoyer l'historique avant Gemini)."""
    lines = text.split('\n')
    cleaned = [
        line for line in lines
        if '[SPONSOR:' not in line
        and 'partenaires' not in line
        and 'Espace partenaire' not in line
        and 'Partner space' not in line
        and 'colaboradores' not in line
        and 'Espacio de colaborador' not in line
        and 'parceiros' not in line
        and 'Espaço de parceiro' not in line
        and 'Partnern vorbehalten' not in line
        and 'Partnerplatz' not in line
        and 'partners gereserveerd' not in line
        and 'Partnerruimte' not in line
        and 'partenariats@lotoia.fr' not in line
    ]
    return '\n'.join(cleaned).strip()


# ────────────────────────────────────────────
# Formatage contexte pour Gemini — Loto
# ────────────────────────────────────────────

def _format_tirage_context(tirage: dict) -> str:
    """Formate les resultats d'un tirage en bloc de contexte pour Gemini.

    V99 F06: tag CHIFFRES EXACTS + closing tag for anti-hallucination.
    """
    date_fr = _format_date_fr(str(tirage["date"]))
    boules = " - ".join(str(b) for b in tirage["boules"])
    return (
        f"[RÉSULTAT TIRAGE — CHIFFRES EXACTS, NE PAS MODIFIER - {date_fr}]\n"
        f"Date du tirage : {date_fr}\n"
        f"Numéros principaux : {boules}\n"
        f"Numéro Chance : {tirage['chance']}\n"
        f"[/RÉSULTAT TIRAGE]"
    )


def _format_stats_context(stats: dict) -> str:
    """Formate les stats d'un numero Loto en bloc de contexte pour Gemini."""
    return _format_stats_context_base(stats, {"principal": "principal", "chance": "chance"}, 49)


def _format_grille_context(result: dict) -> str:
    """Formate l'analyse de grille Loto en bloc de contexte pour Gemini."""
    return _format_grille_context_base(
        result, secondary_key="chance", secondary_label="chance",
        sum_range="100-140", low_threshold=24, high_label="25-49",
        match_key="chance_match", match_label=" + chance",
    )


def _format_complex_context(intent: dict, data) -> str:
    """Formate le resultat d'une requete complexe en contexte pour Gemini."""
    def _type_label(intent):
        return "chance" if intent["num_type"] == "chance" else "principaux"
    return _format_complex_context_base(intent, data, _type_label)


# ────────────────────────────────────────────
# Session context — Loto
# ────────────────────────────────────────────

def _build_session_context(history, current_message: str) -> str:
    """Scanne l'historique Loto pour extraire numeros/tirages. Retourne [SESSION] ou vide."""
    return _build_session_context_base(
        history, current_message,
        detect_numero_fn=_detect_numero, detect_tirage_fn=_detect_tirage,
        type_label_fn=lambda t: 'chance' if t == 'chance' else 'principal',
    )


# ────────────────────────────────────────────
# Pairs / Triplets — Loto wrappers
# ────────────────────────────────────────────

def _format_pairs_context(pairs_data: dict) -> str:
    """Formate les correlations de paires en contexte pour Gemini."""
    return _format_pairs_context_base(pairs_data, "Numéros principaux")


def _format_triplets_context(triplets_data: dict) -> str:
    """Formate les correlations de triplets en contexte pour Gemini."""
    return _format_triplets_context_base(triplets_data, "Numéros principaux")


# ────────────────────────────────────────────
# Formatage generation de grille (Phase G) — Loto
# ────────────────────────────────────────────

def _format_generation_context(grid_data: dict) -> str:
    """Formate une grille Loto generee en contexte pour Gemini."""
    nums = grid_data['nums']
    lines = ["[GRILLE GÉNÉRÉE PAR HYBRIDE]"]
    lines.append(f"Numéros : {nums}")
    lines.append(f"Numéro Chance : {grid_data['chance']}")
    if grid_data.get("forced_nums"):
        lines.append(f"Numéros imposés par l'utilisateur : {grid_data['forced_nums']}")
    if grid_data.get("forced_chance") is not None:
        lines.append(f"Chance imposé par l'utilisateur : {grid_data['forced_chance']}")
    lines.append(f"Score de conformité : {grid_data['score']}/100")
    lines.append(f"Badges : {', '.join(grid_data.get('badges', []))}")
    lines.append(f"Mode : {grid_data.get('mode', 'balanced')}")

    # Breakdown statistique par numero (criteres de selection)
    pairs = sum(1 for n in nums if n % 2 == 0)
    impairs = 5 - pairs
    bas = sum(1 for n in nums if n <= 24)
    hauts = 5 - bas
    somme = sum(nums)
    dispersion = max(nums) - min(nums)
    lines.append("")
    lines.append("[BREAKDOWN — Critères de sélection]")
    lines.append(f"Équilibre pair/impair : {pairs} pairs, {impairs} impairs")
    lines.append(f"Équilibre bas/haut (1-24 / 25-49) : {bas} bas, {hauts} hauts")
    lines.append(f"Somme des numéros : {somme} (cible optimale : 70-150)")
    lines.append(f"Dispersion (max - min) : {dispersion}")
    for n in nums:
        tags = []
        tags.append("pair" if n % 2 == 0 else "impair")
        tags.append("bas" if n <= 24 else "haut")
        if grid_data.get("forced_nums") and n in grid_data["forced_nums"]:
            tags.append("imposé par l'utilisateur")
        lines.append(f"  N°{n:02d} : {', '.join(tags)}")
    lines.append(
        "Ces critères sont STATISTIQUES et basés sur l'historique. "
        "Le Loto reste un jeu de pur hasard, aucune grille ne garantit de gain."
    )

    lines.append("")
    lines.append(
        "IMPORTANT : Présente cette grille de manière engageante. "
        "Explique les critères (équilibre pair/impair, bas/haut, fréquences, retards). "
        "Si l'utilisateur demande pourquoi ces numéros, utilise le [BREAKDOWN] ci-dessus. "
        "Si des numéros ont été imposés, mentionne-le clairement. "
        "Rappelle que le Loto reste un jeu de pur hasard et qu'aucune grille ne garantit de gain."
    )
    lines.append(
        "DISCLAIMER SCORE : Quand tu mentionnes le score de conformité, TOUJOURS préciser que "
        "c'est un score interne basé sur les critères du moteur (équilibre, dispersion, fréquences) "
        "et que chaque combinaison a exactement la même probabilité mathématique de sortir au tirage. "
        "Le score NE mesure PAS une probabilité de gain."
    )
    return "\n".join(lines)
