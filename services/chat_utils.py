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
    """Formate les resultats d'un tirage en bloc de contexte pour Gemini."""
    date_fr = _format_date_fr(str(tirage["date"]))
    boules = " - ".join(str(b) for b in tirage["boules"])
    return (
        f"[RÉSULTAT TIRAGE - {date_fr}]\n"
        f"Date du tirage : {date_fr}\n"
        f"Numéros principaux : {boules}\n"
        f"Numéro Chance : {tirage['chance']}"
    )


def _format_stats_context(stats: dict) -> str:
    """Formate les stats d'un numero en bloc de contexte pour Gemini."""
    type_label = "principal" if stats["type"] == "principal" else "chance"
    cat = stats["categorie"].upper()
    classement_sur = stats.get("classement_sur", 49)
    derniere_sortie_fr = _format_date_fr(stats['derniere_sortie'])

    return (
        f"[DONNÉES TEMPS RÉEL - Numéro {type_label} {stats['numero']}]\n"
        f"Fréquence totale : {stats['frequence_totale']} apparitions "
        f"sur {stats['total_tirages']} tirages ({stats['pourcentage_apparition']})\n"
        f"Dernière sortie : {derniere_sortie_fr}\n"
        f"Écart actuel : {stats['ecart_actuel']} tirages\n"
        f"Écart moyen : {stats['ecart_moyen']} tirages\n"
        f"Classement fréquence : {stats['classement']}e sur {classement_sur}\n"
        f"Catégorie : {cat}\n"
        f"Période analysée : {_format_periode_fr(stats['periode'])}"
    )


def _format_grille_context(result: dict) -> str:
    """Formate l'analyse de grille en bloc de contexte pour Gemini."""
    nums = result["numeros"]
    chance = result["chance"]
    a = result["analyse"]
    h = result["historique"]

    nums_str = " ".join(str(n) for n in nums)
    chance_str = f" (chance: {chance})" if chance else ""
    lines = [f"[ANALYSE DE GRILLE - {nums_str}{chance_str}]"]

    ok = lambda b: "\u2713" if b else "\u2717"
    lines.append(f"Somme : {a['somme']} (idéal : 100-140) {ok(a['somme_ok'])}")
    lines.append(f"Pairs : {a['pairs']} / Impairs : {a['impairs']} {ok(a['equilibre_pair_impair'])}")
    lines.append(f"Bas (1-24) : {a['bas']} / Hauts (25-49) : {a['hauts']} {ok(a['equilibre_bas_haut'])}")
    lines.append(f"Dispersion : {a['dispersion']} (idéal : >= 15) {ok(a['dispersion_ok'])}")
    lines.append(f"Consécutifs : {a['consecutifs']} {ok(a['consecutifs'] <= 2)}")

    if a['numeros_chauds']:
        lines.append(f"Numéros chauds : {', '.join(str(n) for n in a['numeros_chauds'])}")
    if a['numeros_froids']:
        lines.append(f"Numéros froids : {', '.join(str(n) for n in a['numeros_froids'])}")
    if a['numeros_neutres']:
        lines.append(f"Numéros neutres : {', '.join(str(n) for n in a['numeros_neutres'])}")

    lines.append(f"Conformité : {a['conformite_pct']}%")
    lines.append(f"Badges : {', '.join(a['badges'])}")

    if h['deja_sortie']:
        lines.append(f"Historique : combinaison déjà sortie le {', '.join(h['exact_dates'])}")
    else:
        mc = h['meilleure_correspondance']
        if mc['nb_numeros_communs'] > 0:
            communs = ', '.join(str(n) for n in mc['numeros_communs'])
            chance_txt = " + chance" if mc.get('chance_match') else ""
            lines.append(
                f"Historique : jamais sortie. Meilleure correspondance : "
                f"{mc['nb_numeros_communs']} numéros communs{chance_txt} le {mc['date']} ({communs})"
            )
        else:
            lines.append("Historique : combinaison jamais sortie")

    return "\n".join(lines)


def _format_complex_context(intent: dict, data) -> str:
    """Formate le resultat d'une requete complexe en contexte pour Gemini."""
    def _type_label(intent):
        return "chance" if intent["num_type"] == "chance" else "principaux"
    return _format_complex_context_base(intent, data, _type_label)


# ────────────────────────────────────────────
# Session context — Loto
# ────────────────────────────────────────────

def _build_session_context(history, current_message: str) -> str:
    """
    Scanne l'historique + message courant pour extraire les numeros
    et tirages consultes. Retourne un bloc [SESSION] ou chaine vide.
    """
    numeros_vus = set()
    tirages_vus = set()

    messages_user = [msg.content for msg in (history or []) if msg.role == "user"]
    messages_user.append(current_message)

    for msg in messages_user:
        num, num_type = _detect_numero(msg)
        if num is not None:
            numeros_vus.add((num, num_type))

        tirage = _detect_tirage(msg)
        if tirage is not None:
            if tirage == "latest":
                tirages_vus.add("dernier")
            elif isinstance(tirage, date):
                tirages_vus.add(_format_date_fr(str(tirage)))

    if len(numeros_vus) + len(tirages_vus) < 2:
        return ""

    parts = []
    if numeros_vus:
        nums_str = ", ".join(
            f"{n} ({'chance' if t == 'chance' else 'principal'})"
            for n, t in sorted(numeros_vus)
        )
        parts.append(f"Numéros consultés : {nums_str}")
    if tirages_vus:
        tir_str = ", ".join(sorted(tirages_vus))
        parts.append(f"Tirages consultés : {tir_str}")

    return "[SESSION]\n" + "\n".join(parts)


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
