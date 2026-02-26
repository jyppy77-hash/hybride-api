"""
Service metier — formatage et utilitaires EuroMillions.
Formatage de contexte EM-specifique pour Gemini.
Reutilise les fonctions generiques de chat_utils.py.
"""

from datetime import date

from services.chat_utils import _format_date_fr, _format_periode_fr  # noqa: F401
from services.chat_detectors_em import _detect_numero_em
from services.chat_detectors import _detect_tirage

FALLBACK_RESPONSE_EM = (
    "\U0001f916 Je suis momentanément indisponible. "
    "Réessaie dans quelques secondes ou consulte la FAQ !"
)


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
    type_label = "boule" if stats["type"] == "boule" else "étoile"
    cat = stats["categorie"].upper()
    classement_sur = stats.get("classement_sur", 50)
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


def _format_grille_context_em(result: dict) -> str:
    """Formate l'analyse de grille EM en bloc de contexte pour Gemini."""
    nums = result["numeros"]
    etoiles = result["etoiles"]
    a = result["analyse"]
    h = result["historique"]

    nums_str = " ".join(str(n) for n in nums)
    etoiles_str = f" (étoiles: {' '.join(str(e) for e in etoiles)})" if etoiles else ""
    lines = [f"[ANALYSE DE GRILLE - {nums_str}{etoiles_str}]"]

    ok = lambda b: "\u2713" if b else "\u2717"
    lines.append(f"Somme : {a['somme']} (idéal : 75-175) {ok(a['somme_ok'])}")
    lines.append(f"Pairs : {a['pairs']} / Impairs : {a['impairs']} {ok(a['equilibre_pair_impair'])}")
    lines.append(f"Bas (1-25) : {a['bas']} / Hauts (26-50) : {a['hauts']} {ok(a['equilibre_bas_haut'])}")
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
            etoile_txt = " + étoile(s) communes" if mc.get('etoiles_match') else ""
            lines.append(
                f"Historique : jamais sortie. Meilleure correspondance : "
                f"{mc['nb_numeros_communs']} numéros communs{etoile_txt} le {mc['date']} ({communs})"
            )
        else:
            lines.append("Historique : combinaison jamais sortie")

    return "\n".join(lines)


def _format_complex_context_em(intent: dict, data) -> str:
    """Formate le resultat d'une requete complexe EM en contexte pour Gemini."""
    if intent["type"] == "classement":
        tri_labels = {
            "frequence_desc": "les plus fréquents",
            "frequence_asc": "les moins fréquents",
            "ecart_desc": "les plus en retard",
            "ecart_asc": "sortis le plus récemment",
        }
        label = tri_labels.get(intent["tri"], intent["tri"])
        limit = intent["limit"]
        type_label = "étoiles" if intent["num_type"] == "etoile" else "boules"

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


def _build_session_context_em(history, current_message: str) -> str:
    """
    Scanne l'historique + message courant pour extraire les numeros
    et tirages consultes. Retourne un bloc [SESSION] ou chaine vide.
    """
    numeros_vus = set()
    tirages_vus = set()

    messages_user = [msg.content for msg in (history or []) if msg.role == "user"]
    messages_user.append(current_message)

    for msg in messages_user:
        num, num_type = _detect_numero_em(msg)
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
            f"{n} ({'étoile' if t == 'etoile' else 'boule'})"
            for n, t in sorted(numeros_vus)
        )
        parts.append(f"Numéros consultés : {nums_str}")
    if tirages_vus:
        tir_str = ", ".join(sorted(tirages_vus))
        parts.append(f"Tirages consultés : {tir_str}")

    return "[SESSION]\n" + "\n".join(parts)
