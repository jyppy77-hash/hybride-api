"""
Base chat utilities — shared context, formatting, sponsor system, StreamBuffer.
Game-specific formatting stays in wrappers (chat_utils.py / chat_utils_em.py).
"""

import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────
# Fallback response
# ────────────────────────────────────────────

FALLBACK_RESPONSE = (
    "\U0001f916 Je suis momentanément indisponible. "
    "Réessaie dans quelques secondes ou consulte la FAQ !"
)


# ────────────────────────────────────────────
# Non-latin character stripping
# ────────────────────────────────────────────

# Regex CJK + autres blocs non-latin indesirables (chinois, japonais, coreen, arabe, etc.)
_RE_NON_LATIN = re.compile(
    r'[\u4e00-\u9fff'          # CJK Unified Ideographs (chinois)
    r'\u3400-\u4dbf'           # CJK Extension A
    r'\u3000-\u303f'           # CJK Symbols
    r'\u3040-\u309f'           # Hiragana
    r'\u30a0-\u30ff'           # Katakana
    r'\uac00-\ud7af'           # Hangul (coreen)
    r'\u0600-\u06ff'           # Arabe
    r'\u0900-\u097f'           # Devanagari
    r'\U00020000-\U0002a6df'   # CJK Extension B
    r']+'
)


def _strip_non_latin(text: str) -> str:
    """Supprime les caracteres CJK/arabe/devanagari indesirables des reponses Gemini."""
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
# Response cleaning
# ────────────────────────────────────────────

def _clean_response(text: str) -> str:
    """Supprime les tags internes qui ne doivent pas etre vus par l'utilisateur."""
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
        r'\[CORR[EÉ]LATIONS? DE PAIRES[^\]]*\]',
        r'\[CORRELATIONS? DE PAIRES[^\]]*\]',
        r'\[GRILLE G[EÉ]N[EÉ]R[EÉ]E PAR HYBRIDE[^\]]*\]',
        r'\[GRILLE GENEREE PAR HYBRIDE[^\]]*\]',
        r'\[Page:\s*[^\]]*\]',
        r'\[Question utilisateur[^\]]*\]',
        r'\[CONTEXTE CONTINUATION[^\]]*\]',
        r'\[FR[EÉ]QUENCE SUR LA P[EÉ]RIODE[^\]]*\]',
        r'\[FREQUENCE SUR LA PERIODE[^\]]*\]',
        r'\[PROGRESSION[^\]]*\]',
        r'\[R[EÉ]F[EÉ]RENCE[^\]]*\]',
        r'\[REFERENCE[^\]]*\]',
        r'\[BREAKDOWN[^\]]*\]',
        r'\[MESSAGE A ADAPTER[^\]]*\]',
    ]
    for tag in internal_tags:
        text = re.sub(tag, '', text)
    # Supprimer les caracteres CJK/non-latin injectes par Gemini
    text = _strip_non_latin(text)
    # Nettoyer les espaces multiples et lignes vides resultants
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)
    # strip(\n\r) only — preserver les espaces aux bords des chunks SSE
    # pour eviter le collage de mots ("Jene peux pas") lors de la concatenation JS
    return text.strip('\n\r')


# ────────────────────────────────────────────
# StreamBuffer — nettoyage anti-fuite SSE
# ────────────────────────────────────────────

class StreamBuffer:
    """Buffer SSE qui accumule les chunks et nettoie les tags fragmentes.

    Les tags internes comme [COMPARAISON SUR PÉRIODE] peuvent arriver
    decoupes sur plusieurs chunks SSE. Ce buffer retient le texte quand
    un '[' est detecte sans ']' correspondant, puis nettoie le tag complet
    avant de flusher.
    """

    def __init__(self):
        self.buffer = ""

    def add_chunk(self, chunk: str) -> str:
        """Ajoute un chunk. Retourne le texte safe a envoyer (peut etre vide)."""
        self.buffer += chunk

        # Si le buffer contient un '[' non ferme, on attend le ']'
        last_open = self.buffer.rfind("[")
        if last_open != -1 and "]" not in self.buffer[last_open:]:
            # Tag potentiellement en cours — envoyer tout AVANT le '['
            safe = self.buffer[:last_open]
            self.buffer = self.buffer[last_open:]
            if safe:
                return _clean_response(safe)
            return ""

        # Pas de '[' pendant ou tout est ferme — nettoyer et envoyer
        cleaned = _clean_response(self.buffer)
        self.buffer = ""
        return cleaned

    def flush(self) -> str:
        """Flush le reste du buffer a la fin du stream."""
        if not self.buffer:
            return ""
        cleaned = _clean_response(self.buffer)
        self.buffer = ""
        return cleaned


# ────────────────────────────────────────────
# Formatage dates
# ────────────────────────────────────────────

_MOIS_FR = [
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _format_date_fr(date_str: str) -> str:
    """Convertit une date ISO (2026-02-09) en format francais (9 fevrier 2026)."""
    try:
        d = datetime.strptime(str(date_str), "%Y-%m-%d")
        return f"{d.day} {_MOIS_FR[d.month]} {d.year}"
    except (ValueError, TypeError):
        return str(date_str) if date_str else "inconnue"


def _format_periode_fr(periode: str) -> str:
    """Convertit '2019-11-04 au 2026-02-07' en '4 novembre 2019 au 7 fevrier 2026'."""
    try:
        parts = periode.split(" au ")
        if len(parts) == 2:
            return f"{_format_date_fr(parts[0])} au {_format_date_fr(parts[1])}"
    except Exception:
        pass
    return periode


# ────────────────────────────────────────────
# Shared formatting — pairs / triplets / complex
# ────────────────────────────────────────────

def _format_pairs_context_base(pairs_data: dict, header: str) -> str:
    """Formate les correlations de paires en contexte pour Gemini."""
    lines = [f"[CORRÉLATIONS DE PAIRES — {header}]"]
    lines.append(f"Total tirages analysés : {pairs_data['total_draws']}")
    if pairs_data.get("window"):
        lines.append(f"Fenêtre : {pairs_data['window']}")
    for i, p in enumerate(pairs_data["pairs"], 1):
        lines.append(
            f"{i}. {p['num_a']} + {p['num_b']} "
            f"\u2192 {p['count']} fois ({p['percentage']}%)"
        )
    lines.append(
        "IMPORTANT : Le hasard reste souverain. "
        "Ces corrélations sont purement statistiques."
    )
    return "\n".join(lines)


def _format_triplets_context_base(triplets_data: dict, header: str) -> str:
    """Formate les correlations de triplets en contexte pour Gemini."""
    lines = [f"[CORRÉLATIONS DE TRIPLETS — {header}]"]
    lines.append(f"Total tirages analysés : {triplets_data['total_draws']}")
    if triplets_data.get("window"):
        lines.append(f"Fenêtre : {triplets_data['window']}")
    for i, t in enumerate(triplets_data["triplets"], 1):
        lines.append(
            f"{i}. {t['num_a']} + {t['num_b']} + {t['num_c']} "
            f"\u2192 {t['count']} fois ({t['percentage']}%)"
        )
    lines.append(
        "IMPORTANT : Le hasard reste souverain. "
        "Ces corrélations sont purement statistiques."
    )
    return "\n".join(lines)


def _format_stats_context_base(stats: dict, type_map: dict, default_classement: int) -> str:
    """Formate les stats d'un numero en bloc de contexte pour Gemini.

    type_map: mapping stats['type'] → display label (e.g. {"principal": "principal", "chance": "chance"}).
    default_classement: classement_sur default (49 for Loto, 50 for EM).
    """
    type_label = type_map.get(stats["type"], stats["type"])
    cat = stats["categorie"].upper()
    classement_sur = stats.get("classement_sur", default_classement)
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


def _format_grille_context_base(result: dict, secondary_key: str, secondary_label: str,
                                sum_range: str, low_threshold: int, high_label: str,
                                match_key: str = "chance_match", match_label: str = " + chance") -> str:
    """Formate l'analyse de grille en bloc de contexte pour Gemini.

    secondary_key: key in result for secondary number(s) ("chance" or "etoiles").
    secondary_label: display label ("chance" or "étoiles").
    sum_range: ideal sum range string (e.g. "100-140" or "75-175").
    low_threshold: boundary for bas/haut split (24 for Loto, 25 for EM).
    high_label: label for high numbers (e.g. "25-49" or "26-50").
    match_key: key in meilleure_correspondance for secondary match.
    match_label: label for match suffix.
    """
    nums = result["numeros"]
    secondary = result.get(secondary_key)
    a = result["analyse"]
    h = result["historique"]

    nums_str = " ".join(str(n) for n in nums)
    if secondary:
        if isinstance(secondary, list):
            sec_str = f" ({secondary_label}: {' '.join(str(e) for e in secondary)})"
        else:
            sec_str = f" ({secondary_label}: {secondary})"
    else:
        sec_str = ""
    lines = [f"[ANALYSE DE GRILLE - {nums_str}{sec_str}]"]

    ok = lambda b: "\u2713" if b else "\u2717"
    lines.append(f"Somme : {a['somme']} (idéal : {sum_range}) {ok(a['somme_ok'])}")
    lines.append(f"Pairs : {a['pairs']} / Impairs : {a['impairs']} {ok(a['equilibre_pair_impair'])}")
    lines.append(f"Bas (1-{low_threshold}) : {a['bas']} / Hauts ({high_label}) : {a['hauts']} {ok(a['equilibre_bas_haut'])}")
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
            sec_txt = match_label if mc.get(match_key) else ""
            lines.append(
                f"Historique : jamais sortie. Meilleure correspondance : "
                f"{mc['nb_numeros_communs']} numéros communs{sec_txt} le {mc['date']} ({communs})"
            )
        else:
            lines.append("Historique : combinaison jamais sortie")

    return "\n".join(lines)


def _build_session_context_base(history, current_message: str,
                                detect_numero_fn, detect_tirage_fn,
                                type_label_fn) -> str:
    """Scanne l'historique + message courant pour extraire les numeros et tirages.

    detect_numero_fn: (msg) -> (num, type) or (None, None)
    detect_tirage_fn: (msg) -> target or None
    type_label_fn: (num_type) -> display label
    Returns a [SESSION] block or empty string.
    """
    from datetime import date as _date
    numeros_vus = set()
    tirages_vus = set()

    messages_user = [msg.content for msg in (history or []) if msg.role == "user"]
    messages_user.append(current_message)

    for msg in messages_user:
        num, num_type = detect_numero_fn(msg)
        if num is not None:
            numeros_vus.add((num, num_type))

        tirage = detect_tirage_fn(msg)
        if tirage is not None:
            if tirage == "latest":
                tirages_vus.add("dernier")
            elif isinstance(tirage, _date):
                tirages_vus.add(_format_date_fr(str(tirage)))

    if len(numeros_vus) + len(tirages_vus) < 2:
        return ""

    parts = []
    if numeros_vus:
        nums_str = ", ".join(
            f"{n} ({type_label_fn(t)})"
            for n, t in sorted(numeros_vus)
        )
        parts.append(f"Numéros consultés : {nums_str}")
    if tirages_vus:
        tir_str = ", ".join(sorted(tirages_vus))
        parts.append(f"Tirages consultés : {tir_str}")

    return "[SESSION]\n" + "\n".join(parts)


def _format_complex_context_base(intent: dict, data, type_label_fn) -> str:
    """Formate le resultat d'une requete complexe en contexte pour Gemini.

    type_label_fn(intent) -> str : returns the type label for classement
    (e.g. "chance"/"principaux" for Loto, "étoiles"/"boules" for EM).
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
        type_label = type_label_fn(intent)

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

        if data.get("period"):
            p = data["period"]
            _s1 = "+" if p["num1_progression_pct"] > 0 else ""
            _s2 = "+" if p["num2_progression_pct"] > 0 else ""

            lines = [f"[COMPARAISON SUR PÉRIODE - Numéro {s1['numero']} vs Numéro {s2['numero']}]"]
            lines.append(f"Période analysée : depuis {p['date_from']} ({p['total_tirages_period']} tirages)")
            lines.append("")
            lines.append(f"[FRÉQUENCE SUR LA PÉRIODE — C'EST CE CHIFFRE QUE TU DOIS CITER]")
            lines.append(f"Numéro {s1['numero']} sur la période : {p['num1_freq_period']} apparitions")
            lines.append(f"Numéro {s2['numero']} sur la période : {p['num2_freq_period']} apparitions")
            lines.append("")
            lines.append(f"[PROGRESSION PAR RAPPORT À LA MOYENNE HISTORIQUE]")
            lines.append(
                f"Numéro {s1['numero']} : attendu {p['num1_expected']} → observé {p['num1_freq_period']} "
                f"→ progression {_s1}{p['num1_progression_pct']}%"
            )
            lines.append(
                f"Numéro {s2['numero']} : attendu {p['num2_expected']} → observé {p['num2_freq_period']} "
                f"→ progression {_s2}{p['num2_progression_pct']}%"
            )
            if p["plus_progresse"]:
                lines.append(
                    f"Le numéro {p['plus_progresse']} a le plus progressé par rapport à sa moyenne historique."
                )
            else:
                lines.append("Progressions identiques.")
            lines.append("")
            lines.append(f"[RÉFÉRENCE — fréquence totale historique (ne PAS citer en premier)]")
            lines.append(
                f"Numéro {s1['numero']} historique total : {s1['frequence_totale']} apparitions "
                f"({s1['pourcentage_apparition']}) | Catégorie : {s1['categorie'].upper()}"
            )
            lines.append(
                f"Numéro {s2['numero']} historique total : {s2['frequence_totale']} apparitions "
                f"({s2['pourcentage_apparition']}) | Catégorie : {s2['categorie'].upper()}"
            )
            lines.append("")
            lines.append(
                "IMPORTANT : L'utilisateur a demandé une comparaison SUR UNE PÉRIODE. "
                "Cite en PREMIER la fréquence sur la période demandée (section [FRÉQUENCE SUR LA PÉRIODE]). "
                "La fréquence totale historique est une RÉFÉRENCE secondaire, ne la cite PAS comme chiffre principal."
            )
        else:
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
