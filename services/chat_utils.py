import re
import json
import logging
from pathlib import Path
from datetime import date, datetime

from services.chat_detectors import _detect_numero, _detect_tirage

logger = logging.getLogger(__name__)


FALLBACK_RESPONSE = (
    "\U0001f916 Je suis momentanément indisponible. "
    "Réessaie dans quelques secondes ou consulte la FAQ !"
)

# Regex CJK + autres blocs non-latin indésirables (chinois, japonais, coréen, arabe, etc.)
_RE_NON_LATIN = re.compile(
    r'[\u4e00-\u9fff'          # CJK Unified Ideographs (chinois)
    r'\u3400-\u4dbf'           # CJK Extension A
    r'\u3000-\u303f'           # CJK Symbols
    r'\u3040-\u309f'           # Hiragana
    r'\u30a0-\u30ff'           # Katakana
    r'\uac00-\ud7af'           # Hangul (coréen)
    r'\u0600-\u06ff'           # Arabe
    r'\u0900-\u097f'           # Devanagari
    r'\U00020000-\U0002a6df'   # CJK Extension B
    r']+'
)


def _strip_non_latin(text: str) -> str:
    """Supprime les caractères CJK/arabe/devanagari indésirables des réponses Gemini."""
    return _RE_NON_LATIN.sub('', text)


# ────────────────────────────────────────────
# Phase 0 : Enrichissement contextuel
# ────────────────────────────────────────────

def _enrich_with_context(message: str, history: list) -> str:
    """Enrichit une reponse courte avec le contexte de la derniere interaction.

    Parcourt l'historique a l'envers pour trouver le dernier echange
    (derniere question user + derniere reponse assistant) et construit
    un message enrichi pour Gemini.
    """
    if not history or len(history) < 2:
        return message

    last_assistant = None
    last_user_question = None

    for msg in reversed(history):
        if msg.role == "assistant" and not last_assistant:
            last_assistant = msg.content
        elif msg.role == "user" and not last_user_question:
            last_user_question = msg.content
        if last_assistant and last_user_question:
            break

    if not last_assistant or not last_user_question:
        return message

    enriched = (
        f"[CONTEXTE CONTINUATION] L'utilisateur avait demandé : \"{last_user_question}\". "
        f"Tu avais répondu : \"{last_assistant[:300]}\". "
        f"L'utilisateur répond maintenant : \"{message}\". "
        f"Continue sur le même sujet en répondant à ta propre proposition."
    )
    return enriched


# ────────────────────────────────────────────
# Systeme sponsor — insertion post-Gemini
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
        _sponsors_config = {"enabled": False, "frequency": 3, "sponsors": []}
    return _sponsors_config


def _get_sponsor_if_due(history: list, lang: str = "fr") -> str | None:
    """Retourne le texte sponsor si c'est le moment, None sinon."""
    config = _load_sponsors_config()
    if not config.get("enabled"):
        return None

    frequency = config.get("frequency", 3)
    active = [s for s in config.get("sponsors", []) if s.get("active")]
    if not active:
        return None

    # Compter les reponses assistant dans l'historique
    bot_count = sum(1 for msg in history if msg.role == "assistant")
    # +1 car la reponse actuelle sera la suivante
    bot_count += 1

    if bot_count % frequency != 0:
        return None

    # Rotation parmi les sponsors actifs
    cycle = bot_count // frequency
    sponsor = active[(cycle - 1) % len(active)]

    # Alterner style A (naturel) / style B (encart)
    if lang == "en":
        if cycle % 2 == 1:
            return "\U0001f4e2 This space is reserved for our partners \u2014 Learn more: partenariats@lotoia.fr"
        else:
            return "\u2014 Partner space available | partenariats@lotoia.fr"
    else:
        if cycle % 2 == 1:
            return "\U0001f4e2 Cet espace est réservé à nos partenaires \u2014 Pour en savoir plus : partenariats@lotoia.fr"
        else:
            return "\u2014 Espace partenaire disponible | partenariats@lotoia.fr"


def _strip_sponsor_from_text(text: str) -> str:
    """Supprime les lignes sponsor d'un message (pour nettoyer l'historique avant Gemini)."""
    lines = text.split('\n')
    cleaned = [
        line for line in lines
        if 'partenaires' not in line
        and 'Espace partenaire' not in line
        and 'Partner space' not in line
        and 'partenariats@lotoia.fr' not in line
    ]
    return '\n'.join(cleaned).strip()


def _clean_response(text: str) -> str:
    """Supprime les tags internes qui ne doivent pas être vus par l'utilisateur."""
    internal_tags = [
        r'\[RÉSULTAT SQL\]',
        r'\[RESULTAT SQL\]',
        r'\[RÉSULTAT TIRAGE[^\]]*\]',
        r'\[RESULTAT TIRAGE[^\]]*\]',
        r'\[ANALYSE DE GRILLE[^\]]*\]',
        r'\[CLASSEMENT[^\]]*\]',
        r'\[COMPARAISON[^\]]*\]',
        r'\[NUMÉROS? (?:CHAUDS?|FROIDS?)[^\]]*\]',
        r'\[NUMEROS? (?:CHAUDS?|FROIDS?)[^\]]*\]',
        r'\[DONNÉES TEMPS RÉEL[^\]]*\]',
        r'\[DONNEES TEMPS REEL[^\]]*\]',
        r'\[PROCHAIN TIRAGE[^\]]*\]',
        r'\[Page:\s*[^\]]*\]',
        r'\[Question utilisateur[^\]]*\]',
        r'\[CONTEXTE CONTINUATION[^\]]*\]',
    ]
    for tag in internal_tags:
        text = re.sub(tag, '', text)
    # Supprimer les caractères CJK/non-latin injectés par Gemini
    text = _strip_non_latin(text)
    # Nettoyer les espaces multiples et lignes vides résultants
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


# ────────────────────────────────────────────
# Formatage dates
# ────────────────────────────────────────────

_MOIS_FR = [
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _format_date_fr(date_str: str) -> str:
    """Convertit une date ISO (2026-02-09) en format francais (9 février 2026)."""
    try:
        d = datetime.strptime(str(date_str), "%Y-%m-%d")
        return f"{d.day} {_MOIS_FR[d.month]} {d.year}"
    except (ValueError, TypeError):
        return str(date_str) if date_str else "inconnue"


def _format_periode_fr(periode: str) -> str:
    """Convertit '2019-11-04 au 2026-02-07' en '4 novembre 2019 au 7 février 2026'."""
    try:
        parts = periode.split(" au ")
        if len(parts) == 2:
            return f"{_format_date_fr(parts[0])} au {_format_date_fr(parts[1])}"
    except Exception:
        pass
    return periode


# ────────────────────────────────────────────
# Formatage contexte pour Gemini
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
    """
    Formate les stats d'un numero en bloc de contexte pour Gemini.
    """
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
    """
    Formate l'analyse de grille en bloc de contexte pour Gemini.
    """
    nums = result["numeros"]
    chance = result["chance"]
    a = result["analyse"]
    h = result["historique"]

    # En-tete
    nums_str = " ".join(str(n) for n in nums)
    chance_str = f" (chance: {chance})" if chance else ""
    lines = [f"[ANALYSE DE GRILLE - {nums_str}{chance_str}]"]

    # Metriques
    ok = lambda b: "\u2713" if b else "\u2717"
    lines.append(f"Somme : {a['somme']} (idéal : 100-140) {ok(a['somme_ok'])}")
    lines.append(f"Pairs : {a['pairs']} / Impairs : {a['impairs']} {ok(a['equilibre_pair_impair'])}")
    lines.append(f"Bas (1-24) : {a['bas']} / Hauts (25-49) : {a['hauts']} {ok(a['equilibre_bas_haut'])}")
    lines.append(f"Dispersion : {a['dispersion']} (idéal : >= 15) {ok(a['dispersion_ok'])}")
    lines.append(f"Consécutifs : {a['consecutifs']} {ok(a['consecutifs'] <= 2)}")

    # Chaud/froid
    if a['numeros_chauds']:
        lines.append(f"Numéros chauds : {', '.join(str(n) for n in a['numeros_chauds'])}")
    if a['numeros_froids']:
        lines.append(f"Numéros froids : {', '.join(str(n) for n in a['numeros_froids'])}")
    if a['numeros_neutres']:
        lines.append(f"Numéros neutres : {', '.join(str(n) for n in a['numeros_neutres'])}")

    lines.append(f"Conformité : {a['conformite_pct']}%")
    lines.append(f"Badges : {', '.join(a['badges'])}")

    # Historique
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
    """
    Formate le resultat d'une requete complexe en contexte pour Gemini.
    """
    if intent["type"] == "classement":
        tri_labels = {
            "frequence_desc": "les plus fréquents",
            "frequence_asc": "les moins fréquents",
            "ecart_desc": "les plus en retard",
            "ecart_asc": "sortis le plus récemment",
        }
        label = tri_labels.get(intent["tri"], intent["tri"])
        limit = intent["limit"]
        type_label = "chance" if intent["num_type"] == "chance" else "principaux"

        lines = [f"[CLASSEMENT - Top {limit} numéros {type_label} {label}]"]
        for i, item in enumerate(data["items"], 1):
            cat = item["categorie"].upper()
            lines.append(
                f"{i}. Numéro {item['numero']} : "
                f"{item['frequence']} apparitions "
                f"(écart actuel : {item['ecart_actuel']}) — {cat}"
            )
        lines.append(
            f"Total tirages analysés : {data['total_tirages']} | "
            f"Période : {data['periode']}"
        )
        return "\n".join(lines)

    elif intent["type"] == "comparaison":
        s1 = data["num1"]
        s2 = data["num2"]
        diff = data["diff_frequence"]
        sign = "+" if diff > 0 else ""

        lines = [f"[COMPARAISON - Numéro {s1['numero']} vs Numéro {s2['numero']}]"]
        lines.append(
            f"Numéro {s1['numero']} : {s1['frequence_totale']} apparitions "
            f"({s1['pourcentage_apparition']}) | Écart : {s1['ecart_actuel']} | "
            f"Catégorie : {s1['categorie'].upper()}"
        )
        lines.append(
            f"Numéro {s2['numero']} : {s2['frequence_totale']} apparitions "
            f"({s2['pourcentage_apparition']}) | Écart : {s2['ecart_actuel']} | "
            f"Catégorie : {s2['categorie'].upper()}"
        )
        if diff != 0:
            favori = data["favori_frequence"]
            lines.append(
                f"Différence de fréquence : {sign}{diff} apparitions "
                f"en faveur du {favori}"
            )
        else:
            lines.append("Fréquences identiques")
        return "\n".join(lines)

    elif intent["type"] == "categorie":
        cat = data["categorie"].upper()
        nums_list = [str(item["numero"]) for item in data["numeros"]]

        lines = [f"[NUMÉROS {cat}S - {data['count']} numéros sur {data['periode_analyse']}]"]
        lines.append(f"Numéros : {', '.join(nums_list)}")
        lines.append(f"Basé sur les tirages des {data['periode_analyse']}")
        return "\n".join(lines)

    return ""


# ────────────────────────────────────────────
# Session context
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

    # Ne pas injecter si la session est trop courte (< 2 sujets)
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
