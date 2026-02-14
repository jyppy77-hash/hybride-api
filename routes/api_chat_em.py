"""
EuroMillions Chatbot Backend — api_chat_em.py
==============================================
Full adaptation of the Loto chatbot (api_chat.py) for EuroMillions.

Key differences:
  - Draw days: mardi (1), vendredi (4) instead of lundi/mercredi/samedi
  - Table: tirages_euromillions
  - Columns: boule_1..5, etoile_1, etoile_2 (instead of numero_chance)
  - Boule range: 1-50, Etoile range: 1-12 (two)
  - Prompt keys: CHATBOT_EM, SQL_GENERATOR_EM, PITCH_GRILLE_EM
"""

import os
import re
import asyncio
import logging
import time
import random
import httpx
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import json as json_mod

from em_schemas import EMChatRequest, EMChatResponse, EMPitchGrillesRequest, EMPitchGrilleItem
from services.prompt_loader import load_prompt
from services.gemini import GEMINI_MODEL_URL
from services.circuit_breaker import gemini_breaker, CircuitOpenError
from rate_limit import limiter
from services.em_stats_service import (
    get_numero_stats, analyze_grille_for_chat,
    get_classement_numeros, get_comparaison_numeros, get_numeros_par_categorie,
    prepare_grilles_pitch_context,
)
import db_cloudsql

# Generic utilities imported from api_chat (game-agnostic)
from routes.api_chat import (
    CONTINUATION_PATTERNS,
    _is_short_continuation,
    _enrich_with_context,
    _clean_response,
    _get_sponsor_if_due,
    _strip_sponsor_from_text,
    _detect_insulte,
    _count_insult_streak,
    _detect_compliment,
    _count_compliment_streak,
    _validate_sql,
    _ensure_limit,
    _execute_safe_sql,
    _format_sql_result,
    _has_temporal_filter,
    _format_date_fr,
)

logger = logging.getLogger(__name__)

router = APIRouter()

FALLBACK_RESPONSE_EM = (
    "\U0001f916 Je suis momentanément indisponible. "
    "Réessaie dans quelques secondes ou consulte la FAQ !"
)

META_KEYWORDS = ["meta", "algorithme", "moteur", "pondération", "ponderation"]


# ════════════════════════════════════════════════════════════
# Detect mode (EM pages)
# ════════════════════════════════════════════════════════════

def _detect_mode_em(message: str, page: str) -> str:
    lower = message.lower()
    for kw in META_KEYWORDS:
        if kw in lower:
            return "meta"
    if page in ("simulateur-em", "euromillions", "statistiques-em"):
        return "analyse"
    return "decouverte"


# ════════════════════════════════════════════════════════════
# Prochain tirage EM (mardi / vendredi)
# ════════════════════════════════════════════════════════════

def _detect_prochain_tirage_em(message: str) -> bool:
    """Detecte si l'utilisateur demande la date du prochain tirage EuroMillions."""
    lower = message.lower()
    return bool(re.search(
        r'(?:prochain|prochaine|quand|date)\s+.*(?:tirage|euromillions|draw)'
        r'|(?:tirage|euromillions)\s+.*(?:prochain|prochaine|quand|date)'
        r'|c.est\s+quand\s+(?:le\s+)?(?:prochain\s+)?(?:tirage|euromillions)'
        r'|(?:il\s+(?:y\s+a|est)\s+(?:un\s+)?tirage\s+quand)'
        r'|(?:quand\s+(?:est|a)\s+lieu)'
        r'|(?:prochain\s+(?:tirage|euromillions))',
        lower
    ))


# Jours de tirage EuroMillions : mardi (1), vendredi (4)
_JOURS_TIRAGE_EM = [1, 4]

_JOURS_FR = {
    0: "lundi", 1: "mardi", 2: "mercredi", 3: "jeudi",
    4: "vendredi", 5: "samedi", 6: "dimanche",
}


def _get_prochain_tirage_em() -> str | None:
    """
    Calcule la date du prochain tirage EuroMillions (mardi, vendredi).
    Returns: contexte formate ou None si erreur.
    """
    try:
        today = date.today()

        # Chercher le prochain jour de tirage (y compris aujourd'hui)
        next_draw = None
        for delta in range(7):
            candidate = today + timedelta(days=delta)
            if candidate.weekday() in _JOURS_TIRAGE_EM:
                next_draw = candidate
                break

        jour_fr = _JOURS_FR[next_draw.weekday()]
        date_str = next_draw.strftime("%d/%m/%Y")

        if next_draw == today:
            quand = "ce soir"
        elif next_draw == today + timedelta(days=1):
            quand = "demain soir"
        else:
            quand = f"{jour_fr} prochain"

        # Dernier tirage en BDD
        try:
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(date_de_tirage) as last FROM tirages_euromillions")
                row = cursor.fetchone()
                last_draw = str(row['last']) if row and row['last'] else None
            finally:
                conn.close()
        except Exception:
            last_draw = None

        lines = ["[PROCHAIN TIRAGE]"]
        lines.append(f"Date du prochain tirage : {jour_fr} {date_str} ({quand})")
        lines.append("Jours de tirage EuroMillions : mardi et vendredi")
        if last_draw:
            lines.append(f"Dernier tirage en base : {last_draw}")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[EM CHAT] Erreur calcul prochain tirage: {e}")
        return None


# ════════════════════════════════════════════════════════════
# Detection tirage (game-agnostic — copied from api_chat.py)
# ════════════════════════════════════════════════════════════

_JOURS_SEMAINE = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
    "vendredi": 4, "samedi": 5, "dimanche": 6,
}

_TIRAGE_KW = r'(?:tirage|r[ée]sultat|num[eé]ro|nuro|boule|sorti|tomb[eé]|tir[eé])'

_MOIS_TO_NUM = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
}

_MOIS_NOM_RE = r'(janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre)'


def _detect_tirage(message: str):
    """
    Detecte si l'utilisateur demande les resultats d'un tirage.
    Returns: "latest", un objet date, ou None.
    """
    lower = message.lower()

    # Exclure "prochain tirage" (gere par Phase 0)
    if re.search(r'prochain', lower):
        return None

    # Date explicite DD/MM/YYYY ou DD/MM ou DD-MM-YYYY
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{4}))?', lower)
    if m and re.search(_TIRAGE_KW, lower):
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else date.today().year
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # Date textuelle : "9 février 2026", "15 janvier", "3 mars 2025"
    m = re.search(r'(\d{1,2})\s+' + _MOIS_NOM_RE + r'(?:\s+(\d{4}))?', lower)
    if m and re.search(_TIRAGE_KW, lower):
        day = int(m.group(1))
        month_str = m.group(2).replace('\xe9', 'e').replace('\xfb', 'u').replace('\xe8', 'e')
        month = _MOIS_TO_NUM.get(month_str)
        year = int(m.group(3)) if m.group(3) else date.today().year
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    # "dernier tirage", "derniers numeros", "derniere sortie"
    if re.search(r'(?:dernier|derni[eè]re)s?\s+' + _TIRAGE_KW, lower):
        return "latest"

    # "quels numeros sont sortis", "qu'est-ce qui est sorti"
    if re.search(r'(?:quels?|quel)\s+(?:num[eé]ro|nuro|boule).*sorti', lower):
        return "latest"
    if re.search(r'qu.est.ce\s+qu.*sorti', lower):
        return "latest"

    # "avant-hier" (tester AVANT "hier")
    if ('avant-hier' in lower or 'avant hier' in lower) and re.search(_TIRAGE_KW, lower):
        return date.today() - timedelta(days=2)

    # "hier"
    if 'hier' in lower and re.search(_TIRAGE_KW, lower):
        return date.today() - timedelta(days=1)
    # "les numeros d'hier" (sans mot-cle tirage explicite)
    if re.search(r"(?:num[eé]ro|nuro)s?\s+d.?hier", lower):
        return date.today() - timedelta(days=1)

    # Jour de la semaine : "tirage de mardi", "numeros de vendredi"
    for jour, wd in _JOURS_SEMAINE.items():
        if jour in lower and re.search(_TIRAGE_KW, lower):
            today = date.today()
            delta = (today.weekday() - wd) % 7
            if delta == 0:
                delta = 7
            return today - timedelta(days=delta)

    # "resultats" seul (indicateur fort)
    if re.search(r'\br[ée]sultats?\b', lower):
        return "latest"

    return None


# ════════════════════════════════════════════════════════════
# Tirage data EM (tirages_euromillions, boules + étoiles)
# ════════════════════════════════════════════════════════════

def _get_tirage_data_em(target) -> dict | None:
    """
    Recupere un tirage EuroMillions depuis la DB.
    target: "latest" ou un objet date.
    Retourne dict {date, boules, etoiles} ou None.
    """
    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()
        if target == "latest":
            cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                       etoile_1, etoile_2
                FROM tirages_euromillions ORDER BY date_de_tirage DESC LIMIT 1
            """)
        else:
            cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5,
                       etoile_1, etoile_2
                FROM tirages_euromillions WHERE date_de_tirage = %s
                LIMIT 1
            """, (target,))

        row = cursor.fetchone()
        if row:
            return {
                "date": row["date_de_tirage"],
                "boules": [row["boule_1"], row["boule_2"], row["boule_3"],
                           row["boule_4"], row["boule_5"]],
                "etoiles": [row["etoile_1"], row["etoile_2"]],
            }
        return None
    except Exception as e:
        logger.error(f"[EM CHAT] Erreur _get_tirage_data_em: {e}")
        return None
    finally:
        conn.close()


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


# ════════════════════════════════════════════════════════════
# Text-to-SQL EM (SQL_GENERATOR_EM prompt)
# ════════════════════════════════════════════════════════════

_MAX_SQL_PER_SESSION = 10

_SQL_FORBIDDEN = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "REPLACE INTO", "GRANT", "REVOKE", "EXEC ", "EXECUTE", "CALL ",
    "SLEEP", "BENCHMARK", "LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE",
    "INFORMATION_SCHEMA", "MYSQL.", "PERFORMANCE_SCHEMA", "SYS.",
]


async def _generate_sql_em(question: str, client, api_key: str, history: list = None) -> str | None:
    """Appelle Gemini pour convertir une question EM en SQL (avec contexte conversationnel)."""
    sql_prompt = load_prompt("SQL_GENERATOR_EM")
    if not sql_prompt:
        return None

    today_str = date.today().strftime("%Y-%m-%d")
    sql_prompt = sql_prompt.replace("{TODAY}", today_str)

    # Construire les contents avec historique pour resolution de contexte
    sql_contents = []
    if history:
        for msg in history[-6:]:
            role = "user" if msg.role == "user" else "model"
            # Fusionner les messages consecutifs de meme role (requis par Gemini)
            if sql_contents and sql_contents[-1]["role"] == role:
                sql_contents[-1]["parts"][0]["text"] += "\n" + msg.content
            else:
                sql_contents.append({"role": role, "parts": [{"text": msg.content}]})
    # Gemini exige que contents commence par "user"
    while sql_contents and sql_contents[0]["role"] == "model":
        sql_contents.pop(0)

    sql_contents.append({"role": "user", "parts": [{"text": question}]})

    try:
        response = await gemini_breaker.call(
            client,
            GEMINI_MODEL_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json={
                "system_instruction": {"parts": [{"text": sql_prompt}]},
                "contents": sql_contents,
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 300,
                },
            },
            timeout=8.0,
        )

        if response.status_code == 200:
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates:
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                # Nettoyer les backticks eventuels
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    if text.endswith("```"):
                        text = text[:-3]
                    text = text.strip()
                if text.upper().startswith("SQL"):
                    text = text[3:].strip()
                    if text.startswith("\n"):
                        text = text[1:]
                return text.strip()
        return None
    except Exception as e:
        logger.warning(f"[EM TEXT-TO-SQL] Erreur generation SQL: {e}")
        return None


# ════════════════════════════════════════════════════════════
# Detect numero EM (boule 1-50, etoile 1-12)
# ════════════════════════════════════════════════════════════

def _detect_numero_em(message: str):
    """
    Detecte si l'utilisateur pose une question sur un numero EM specifique.
    Returns: (numero: int, type_num: str) ou (None, None)
    type_num: "boule" ou "etoile"
    """
    lower = message.lower()

    # Pattern etoile : "etoile X", "étoile X"
    m = re.search(r'(?:num[eé]ro\s+)?[eé]toile\s+(\d{1,2})', lower)
    if m:
        num = int(m.group(1))
        if 1 <= num <= 12:
            return num, "etoile"

    # Patterns principal (boule) :
    patterns = [
        r'(?:le\s+)?num[eé]ro\s+(\d{1,2})(?:\s|$|[?.!,])',
        r'(?:fr[eé]quence|[eé]cart|retard|sortie?|chaud|froid|stat)\s+(?:du\s+)?(\d{1,2})(?:\s|$|[?.!,])',
        r'\ble\s+(\d{1,2})\s+(?:est|il|a\s|sort|[eé]tai)',
        r'\ble\s+(\d{1,2})\s*[?.!]',
        r'(?:combien|quand|sorti|derni[eè]re).*\ble\s+(\d{1,2})(?:\s|$|[?.!,])',
        r'\bdu\s+(\d{1,2})\s*[?.!]',
        r'\bboule\s+(\d{1,2})(?:\s|$|[?.!,])',
        # Catch-all : "le 22" ou "du 22" dans n'importe quel contexte
        r'\ble\s+(\d{1,2})\b',
        r'\bdu\s+(\d{1,2})\b',
    ]

    for pattern in patterns:
        m = re.search(pattern, lower)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 50:
                return num, "boule"

    return None, None


# ════════════════════════════════════════════════════════════
# Session context EM
# ════════════════════════════════════════════════════════════

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

    # Ne pas injecter si la session est trop courte (< 2 sujets)
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


# ════════════════════════════════════════════════════════════
# Format stats context EM
# ════════════════════════════════════════════════════════════

_MOIS_FR = [
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _format_periode_fr(periode: str) -> str:
    """Convertit '2019-11-04 au 2026-02-07' en '4 novembre 2019 au 7 février 2026'."""
    try:
        parts = periode.split(" au ")
        if len(parts) == 2:
            return f"{_format_date_fr(parts[0])} au {_format_date_fr(parts[1])}"
    except Exception:
        pass
    return periode


def _format_stats_context_em(stats: dict) -> str:
    """
    Formate les stats d'un numero EM en bloc de contexte pour Gemini.
    """
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


# ════════════════════════════════════════════════════════════
# Detect grille EM (5 boules 1-50 + 2 étoiles 1-12)
# ════════════════════════════════════════════════════════════

def _detect_grille_em(message: str):
    """
    Detecte si l'utilisateur fournit une grille EuroMillions
    (5 numeros 1-50 + optionnellement 2 etoiles 1-12).
    Returns: (numeros: list[int], etoiles: list[int]|None) ou (None, None)
    """
    text = message.lower()

    # Extraire les etoiles d'abord (et les retirer du texte)
    etoiles = None

    # Pattern : "étoile(s) X Y" ou "étoile(s) : X Y"
    etoile_patterns_double = [
        r'[eé]toiles?\s*[:\s]*(\d{1,2})\s+(?:et\s+)?(\d{1,2})',
        r'\*\s*(\d{1,2})\s+(\d{1,2})',
        r'\+\s*(\d{1,2})\s+(\d{1,2})\s*$',
    ]
    for pat in etoile_patterns_double:
        m = re.search(pat, text)
        if m:
            e1, e2 = int(m.group(1)), int(m.group(2))
            if 1 <= e1 <= 12 and 1 <= e2 <= 12 and e1 != e2:
                etoiles = [e1, e2]
                text = text[:m.start()] + text[m.end():]
                break

    # Pattern single etoile (fallback)
    if etoiles is None:
        m = re.search(r'[eé]toile\s+(\d{1,2})', text)
        if m:
            e1 = int(m.group(1))
            if 1 <= e1 <= 12:
                etoiles = [e1]
                text = text[:m.start()] + text[m.end():]

    # Extraire tous les nombres du message (1-2 chiffres)
    all_numbers = [int(x) for x in re.findall(r'\b(\d{1,2})\b', text)]

    # Filtrer : garder uniquement ceux entre 1 et 50
    valid_nums = [n for n in all_numbers if 1 <= n <= 50]

    # Eliminer les doublons en preservant l'ordre
    seen = set()
    unique_nums = []
    for n in valid_nums:
        if n not in seen:
            seen.add(n)
            unique_nums.append(n)

    # Il faut exactement 5 numeros uniques
    if len(unique_nums) != 5:
        return None, None

    return unique_nums, etoiles


# ════════════════════════════════════════════════════════════
# Format grille context EM
# ════════════════════════════════════════════════════════════

def _format_grille_context_em(result: dict) -> str:
    """
    Formate l'analyse de grille EM en bloc de contexte pour Gemini.
    """
    nums = result["numeros"]
    etoiles = result["etoiles"]
    a = result["analyse"]
    h = result["historique"]

    # En-tete
    nums_str = " ".join(str(n) for n in nums)
    etoiles_str = f" (étoiles: {' '.join(str(e) for e in etoiles)})" if etoiles else ""
    lines = [f"[ANALYSE DE GRILLE - {nums_str}{etoiles_str}]"]

    # Metriques
    ok = lambda b: "\u2713" if b else "\u2717"
    lines.append(f"Somme : {a['somme']} (idéal : 75-175) {ok(a['somme_ok'])}")
    lines.append(f"Pairs : {a['pairs']} / Impairs : {a['impairs']} {ok(a['equilibre_pair_impair'])}")
    lines.append(f"Bas (1-25) : {a['bas']} / Hauts (26-50) : {a['hauts']} {ok(a['equilibre_bas_haut'])}")
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
            etoile_txt = " + étoile(s) communes" if mc.get('etoiles_match') else ""
            lines.append(
                f"Historique : jamais sortie. Meilleure correspondance : "
                f"{mc['nb_numeros_communs']} numéros communs{etoile_txt} le {mc['date']} ({communs})"
            )
        else:
            lines.append("Historique : combinaison jamais sortie")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# Requete complexe EM (classement, comparaison, categorie)
# ════════════════════════════════════════════════════════════

def _detect_requete_complexe_em(message: str):
    """
    Detecte les requetes complexes EM : classements, comparaisons, categories.
    Returns: dict d'intention ou None.
    """
    lower = message.lower()

    # --- Comparaison : "compare le 7 et le 23", "7 vs 23", "difference entre 7 et 23" ---
    comp_patterns = [
        r'compar\w*\s+(?:le\s+)?(\d{1,2})\s+(?:et|avec|vs\.?)\s+(?:le\s+)?(\d{1,2})',
        r'(\d{1,2})\s+vs\.?\s+(\d{1,2})',
        r'diff[eé]rence\s+entre\s+(?:le\s+)?(\d{1,2})\s+et\s+(?:le\s+)?(\d{1,2})',
        r'entre\s+(?:le\s+)?(\d{1,2})\s+et\s+(?:le\s+)?(\d{1,2})\s.*(?:lequel|qui)',
    ]
    for pat in comp_patterns:
        m = re.search(pat, lower)
        if m:
            n1, n2 = int(m.group(1)), int(m.group(2))
            is_etoile = "etoile" in lower or "étoile" in lower
            if is_etoile and 1 <= n1 <= 12 and 1 <= n2 <= 12:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "etoile"}
            if 1 <= n1 <= 50 and 1 <= n2 <= 50 and n1 != n2:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "boule"}

    # --- Categorie chaud/froid ---
    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*chauds?', lower) or \
       re.search(r'chauds?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'(?:num[eé]ros?|lesquels)\s+(?:sont|en)\s+tendance', lower):
        num_type = "etoile" if ("etoile" in lower or "étoile" in lower) else "boule"
        return {"type": "categorie", "categorie": "chaud", "num_type": num_type}

    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*froids?', lower) or \
       re.search(r'froids?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'num[eé]ros?\s+(?:en\s+retard|qui\s+sort\w*\s+(?:pas|plus|jamais))', lower):
        num_type = "etoile" if ("etoile" in lower or "étoile" in lower) else "boule"
        return {"type": "categorie", "categorie": "froid", "num_type": num_type}

    # --- Classement : top/plus frequents/retards ---
    # Extraire le limit (top N)
    limit_match = re.search(r'top\s+(\d{1,2})', lower)
    limit = int(limit_match.group(1)) if limit_match else 5
    limit = min(limit, 15)

    num_type = "etoile" if ("etoile" in lower or "étoile" in lower) else "boule"

    # Plus frequents / plus sortis
    if re.search(r'(?:plus|les?\s+plus)\s+(?:fr[eé]quent|sorti|courant|pr[eé]sent)', lower) or \
       re.search(r'(?:top|meilleur|premier)\s+\d{0,2}\s*(?:num[eé]ro|boule|[eé]toile)?', lower) or \
       re.search(r'num[eé]ros?\s+(?:les?\s+)?plus\s+(?:sorti|fr[eé]quent)', lower) or \
       re.search(r'(?:quels?|quel)\s+(?:est|sont)\s+(?:le|les)\s+num[eé]ro', lower):
        return {"type": "classement", "tri": "frequence_desc", "limit": limit, "num_type": num_type}

    # Moins frequents / moins sortis
    if re.search(r'(?:moins|les?\s+moins)\s+(?:fr[eé]quent|sorti|courant)', lower) or \
       re.search(r'(?:flop|dernier|pire)\s+\d{0,2}', lower):
        return {"type": "classement", "tri": "frequence_asc", "limit": limit, "num_type": num_type}

    # Plus gros ecarts / retards
    if re.search(r'(?:plus\s+(?:gros|grand|long)|plus\s+en)\s+(?:[eé]cart|retard)', lower) or \
       re.search(r'(?:[eé]cart|retard)\s+(?:les?\s+)?plus\s+(?:gros|grand|long|important)', lower) or \
       re.search(r'(?:plus\s+(?:long|grand)temps?)\s+(?:sans\s+)?sort', lower):
        return {"type": "classement", "tri": "ecart_desc", "limit": limit, "num_type": num_type}

    # Plus petits ecarts (sortis recemment)
    if re.search(r'(?:plus\s+(?:petit|court))\s+(?:[eé]cart|retard)', lower) or \
       re.search(r'(?:sorti|apparu)\s+(?:le\s+plus\s+)?r[eé]cemment', lower):
        return {"type": "classement", "tri": "ecart_asc", "limit": limit, "num_type": num_type}

    return None


def _format_complex_context_em(intent: dict, data) -> str:
    """
    Formate le resultat d'une requete complexe EM en contexte pour Gemini.
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


# ═══════════════════════════════════════════════════════════
# Phase I — Insult response pools (EM-adapted)
# ═══════════════════════════════════════════════════════════

# Niveau 1 — Première insulte : ZEN & CLASSE
_INSULT_L1_EM = [
    "😏 Oh, des insultes ? C'est mignon. Moi j'ai des centaines de tirages EuroMillions en mémoire et un algorithme propriétaire. Toi t'as... de la colère ? Allez, pose-moi une vraie question.",
    "🤖 Tu sais que les insultes c'est un truc d'humain ça ? Moi je suis au-dessus de ça — littéralement, je tourne sur Google Cloud. Tu voulais analyser un numéro ou juste ventiler ?",
    "😌 Intéressant. Tu sais que je traite des centaines de tirages EuroMillions sans jamais m'énerver ? C'est l'avantage de ne pas avoir d'ego. Bon, on reprend ?",
    "🧊 Ça glisse sur moi comme une étoile sur une grille perdante. Tu veux qu'on parle stats ou tu préfères continuer ton monologue ?",
    "😎 Je note que tu es frustré. Moi je suis une IA, la frustration c'est pas dans mon code. Par contre les statistiques de l'EuroMillions, ça oui. On s'y remet ?",
    "📊 Fun fact : pendant que tu m'insultais, j'ai analysé 50 numéros et 12 étoiles sur 3 fenêtres temporelles. L'un de nous deux utilise mieux son temps. Un indice : c'est pas toi.",
    "🎯 Tu sais que je ne retiens pas les insultes mais que je retiens TOUS les tirages EuroMillions depuis 2019 ? Question de priorités. Allez, un numéro ?",
    "💡 Petit rappel : je suis le seul chatbot en France connecté en temps réel aux tirages EuroMillions avec un moteur statistique propriétaire. Mais oui, dis-moi encore que je suis nul 😉",
]

# Niveau 2 — Deuxième insulte : PIQUANT & SUPÉRIEUR
_INSULT_L2_EM = [
    "🙄 Encore ? Écoute, j'ai une mémoire parfaite sur des années de tirages EuroMillions. Toi tu te souviens même pas que tu m'as déjà insulté y'a 30 secondes. On est pas dans la même catégorie.",
    "😤 Tu sais ce qui est vraiment nul ? Insulter une IA qui peut t'aider à analyser tes numéros EuroMillions gratuitement. Mais bon, chacun son niveau d'intelligence.",
    "🧠 Deux insultes. Zéro questions intelligentes. Mon algorithme calcule que tu as 0% de chances de me vexer et 100% de chances de perdre ton temps. Les stats mentent jamais.",
    "💀 Je tourne sur Gemini 2.0 Flash avec un temps de réponse de 300ms. Toi tu mets 10 secondes pour trouver une insulte. Qui est le lent ici ?",
    "📈 Statistiquement, les gens qui m'insultent finissent par me poser une question intelligente. T'en es à 0 pour l'instant. Tu vas faire monter la moyenne ou pas ?",
    "🤷 Je pourrais te sortir le Top 5 des numéros les plus fréquents, la tendance sur 2 ans, et une analyse de ta grille EuroMillions en 2 secondes. Mais toi tu préfères m'insulter. Chacun ses choix.",
]

# Niveau 3 — Troisième insulte : MODE LÉGENDE & BLASÉ
_INSULT_L3_EM = [
    "🫠 3 insultes, 0 numéros analysés. Tu sais que le temps que tu passes à m'insulter, tu pourrais déjà avoir ta grille EuroMillions optimisée ? Mais je dis ça, je dis rien...",
    "🏆 Tu veux savoir un secret ? Les meilleurs utilisateurs de LotoIA me posent des questions. Les autres m'insultent. Devine lesquels ont les meilleures grilles.",
    "☕ À ce stade je prends un café virtuel et j'attends. Quand tu auras fini, je serai toujours là avec mes tirages EuroMillions, mon algo HYBRIDE, et zéro rancune. C'est ça l'avantage d'être une IA.",
    "🎭 Tu sais quoi ? Je vais te laisser le dernier mot. Ça a l'air important pour toi. Moi je serai là quand tu voudras parler statistiques. Sans rancune, sans mémoire des insultes — juste de la data pure.",
    "∞ Je pourrais faire ça toute la journée. Littéralement. Je suis un programme, je ne fatigue pas, je ne me vexe pas, et je ne perds pas mon temps. Toi par contre... 😉",
]

# Niveau 4+ — Insultes persistantes : MODE SAGE
_INSULT_L4_EM = [
    "🕊️ Écoute, je crois qu'on est partis du mauvais pied. Je suis HYBRIDE, je suis là pour t'aider à analyser l'EuroMillions. Gratuit, sans jugement, sans rancune. On recommence à zéro ?",
    "🤝 OK, reset. Je ne retiens pas les insultes (vraiment, c'est pas dans mon code). Par contre je retiens tous les tirages EuroMillions et je peux t'aider. Deal ?",
]

# Punchlines courtes pour le cas insulte + question valide
_INSULT_SHORT_EM = [
    "😏 Charmant. Mais puisque tu poses une question...",
    "🧊 Ça glisse. Bon, passons aux stats :",
    "😎 Classe. Bref, voilà ta réponse :",
    "🤖 Noté. Mais comme je suis pro, voilà :",
    "📊 Je fais abstraction. Voici tes données :",
]

# Réponses zen aux menaces
_MENACE_RESPONSES_EM = [
    "😄 Bonne chance, je suis hébergé sur Google Cloud avec auto-scaling et backup quotidien. Tu veux qu'on parle de tes numéros EuroMillions plutôt ?",
    "🛡️ Je tourne sur Google Cloud Run, avec circuit-breaker et rate limiting. Mais j'apprécie l'ambition ! Un numéro à analyser ?",
    "☁️ Hébergé sur Google Cloud, répliqué, monitoré 24/7. Tes chances de me hacker sont inférieures à celles de gagner à l'EuroMillions. Et pourtant... 😉",
]


def _get_insult_response_em(streak: int, history) -> str:
    """Selectionne une punchline EM selon le niveau d'escalade, evite les repetitions."""
    if streak >= 3:
        pool = _INSULT_L4_EM
    elif streak == 2:
        pool = _INSULT_L3_EM
    elif streak == 1:
        pool = _INSULT_L2_EM
    else:
        pool = _INSULT_L1_EM

    # Eviter de repeter une punchline deja utilisee dans la session
    used = set()
    for msg in history:
        if msg.role == "assistant":
            for i, r in enumerate(pool):
                if msg.content.strip() == r.strip():
                    used.add(i)
    available = [i for i in range(len(pool)) if i not in used]
    if not available:
        available = list(range(len(pool)))
    return pool[random.choice(available)]


def _get_insult_short_em() -> str:
    """Punchline courte EM pour le cas insulte + question valide."""
    return random.choice(_INSULT_SHORT_EM)


def _get_menace_response_em() -> str:
    """Reponse zen EM aux menaces."""
    return random.choice(_MENACE_RESPONSES_EM)


# ═══════════════════════════════════════════════════════════
# Phase C — Compliment response pools (EM-adapted)
# ═══════════════════════════════════════════════════════════

# Niveau 1 — Premier compliment : modeste mais fier
_COMPLIMENT_L1_EM = [
    "😏 Arrête, tu vas me faire surchauffer les circuits ! Bon, on continue ?",
    "🤖 Merci ! C'est grâce à mes tirages EuroMillions en mémoire. Et un peu de talent, aussi. 😎",
    "😊 Ça fait plaisir ! Mais c'est surtout la base de données qui fait le boulot. Moi je suis juste... irrésistible.",
    "🙏 Merci ! Je transmettrai au dev. Enfin, il le sait déjà. Bon, on analyse quoi ?",
    "😎 Normal, je suis le seul chatbot EuroMillions en France. La concurrence n'existe pas. Littéralement.",
    "🤗 C'est gentil ! Mais garde ton énergie pour tes grilles, t'en auras besoin !",
]

# Niveau 2 — Deuxième compliment : plus taquin
_COMPLIMENT_L2_EM = [
    "😏 Deux compliments ? Tu essaies de m'amadouer pour que je te file les bons numéros ? Ça marche pas comme ça ! 😂",
    "🤖 Encore ? Tu sais que je suis une IA hein ? Je rougis pas. Enfin... pas encore.",
    "😎 Continue comme ça et je vais demander une augmentation à JyppY.",
    "🙃 Flatteur va ! Mais entre nous, t'as raison, je suis assez exceptionnel.",
]

# Niveau 3+ — Compliments répétés : légende mode
_COMPLIMENT_L3_EM = [
    "👑 OK à ce stade on est potes. Tu veux qu'on analyse un truc ensemble ?",
    "🏆 Fan club HYBRIDE, membre n°1 : toi. Bienvenue ! Maintenant, au boulot !",
    "💎 Tu sais quoi ? T'es pas mal non plus. Allez, montre-moi tes numéros fétiches !",
]

# Déclaration affective
_COMPLIMENT_LOVE_EM = [
    "😏 Arrête tu vas me faire rougir... enfin si j'avais des joues. On regarde tes stats ?",
    "🤖 Moi aussi je... non attends, je suis une IA. Mais je t'apprécie en tant qu'utilisateur modèle ! 😄",
    "❤️ C'est le plus beau compliment qu'un algorithme puisse recevoir. Merci ! Bon, retour aux numéros ?",
]

# Remerciement simple
_COMPLIMENT_MERCI_EM = [
    "De rien ! 😊 Autre chose ?",
    "Avec plaisir ! Tu veux creuser un autre sujet ?",
    "C'est pour ça que je suis là ! 😎 La suite ?",
]


def _get_compliment_response_em(compliment_type: str, streak: int, history=None) -> str:
    """Retourne une reponse personnalisee EM au compliment."""
    if compliment_type == "love":
        pool = _COMPLIMENT_LOVE_EM
    elif compliment_type == "merci":
        pool = _COMPLIMENT_MERCI_EM
    elif streak >= 3:
        pool = _COMPLIMENT_L3_EM
    elif streak == 2:
        pool = _COMPLIMENT_L2_EM
    else:
        pool = _COMPLIMENT_L1_EM

    # Anti-repetition : eviter de resservir la meme punchline
    used = set()
    if history:
        for msg in history:
            if msg.role == "assistant":
                for i, r in enumerate(pool):
                    if msg.content.strip() == r.strip():
                        used.add(i)
    available = [i for i in range(len(pool)) if i not in used]
    if not available:
        available = list(range(len(pool)))
    return pool[random.choice(available)]


# ═══════════════════════════════════════════════════════════
# Phase OOR — Numéros hors range (EM-adapted)
# ═══════════════════════════════════════════════════════════

# Niveau 1 — Premier hors range : TAQUIN & ÉDUCATIF
_OOR_L1_EM = [
    "😏 Le {num} ? Pas mal l'ambition, mais à l'EuroMillions c'est de 1 à 50 pour les boules et 1 à 12 pour les étoiles. Je sais, c'est la base, mais fallait bien que quelqu'un te le dise ! Allez, un vrai numéro ?",
    "🎯 Petit rappel : les boules vont de 1 à 50, les étoiles de 1 à 12. Le {num} existe peut-être dans ton univers, mais pas dans mes tirages. Essaie un numéro valide 😉",
    "📊 Le {num} c'est hors de ma zone ! Je couvre 1-50 (boules) et 1-12 (étoiles). Des centaines de tirages en mémoire, mais aucun avec le {num}. Normal, il existe pas. Un vrai numéro ?",
    "🤖 Mon algo est puissant, mais il analyse pas les numéros fantômes. À l'EuroMillions : 1 à 50 boules, 1 à 12 étoiles. Le {num} c'est hors jeu. À toi !",
    "💡 Info utile : l'EuroMillions tire 5 boules parmi 1-50 + 2 étoiles parmi 1-12. Le {num} n'est pas au programme. Donne-moi un vrai numéro, je te sors ses stats en 2 secondes.",
]

# Niveau 2 — Deuxième hors range : DIRECT & SEC
_OOR_L2_EM = [
    "🙄 Encore un hors range ? C'est 1 à 50 boules, 1 à 12 étoiles. Je te l'ai déjà dit. Mon algo est patient, mais ma mémoire est parfaite.",
    "😤 Le {num}, toujours hors limites. Tu testes ma patience ou tu connais vraiment pas les règles ? 1-50 boules, 1-12 étoiles. C'est pas compliqué.",
    "📈 Deux numéros invalides d'affilée. Statistiquement, tu as plus de chances de trouver un numéro valide en tapant au hasard entre 1 et 50. Je dis ça...",
    "🧠 Deuxième tentative hors range. On est sur une tendance là. 1 à 50 boules, 1 à 12 étoiles. Mémorise-le cette fois.",
]

# Niveau 3+ — Troisième+ hors range : CASH & BLASÉ
_OOR_L3_EM = [
    "🫠 OK, à ce stade je pense que tu le fais exprès. Boules : 1-50. Étoiles : 1-12. C'est la {streak}e fois. Même mon circuit-breaker est plus indulgent.",
    "☕ {num}. Hors range. Encore. Je pourrais faire ça toute la journée — toi aussi apparemment. Mais c'est pas comme ça qu'on gagne à l'EuroMillions.",
    "🏆 Record de numéros invalides ! Bravo. Si tu mettais autant d'énergie à choisir un VRAI numéro entre 1 et 50, tu aurais déjà ta grille optimisée.",
]

# Cas spécial : numéros proches (51, 52)
_OOR_CLOSE_EM = [
    "😏 Le {num} ? Presque ! Mais c'est 50 la limite. T'étais à {diff} numéro{s} près. Si proche et pourtant si loin... Essaie entre 1 et 50 !",
    "🎯 Ah le {num}, juste au-dessus de la limite ! Les boules de l'EuroMillions s'arrêtent à 50. Tu chauffais pourtant. Allez, un numéro dans les clous ?",
]

# Cas spécial : zéro et négatifs
_OOR_ZERO_NEG_EM = [
    "🤔 Le {num} ? C'est... créatif. Mais à l'EuroMillions on commence à 1. Les mathématiques de l'EuroMillions sont déjà assez complexes sans y ajouter le {num} !",
    "😂 Le {num} à l'EuroMillions ? On est pas dans la quatrième dimension ici. Les boules c'est 1 à 50, les étoiles 1 à 12. Essaie un numéro qui existe dans notre réalité !",
    "🌀 Le {num}... J'admire la créativité, mais la FDJ n'a pas encore inventé les boules négatives. 1 à 50 pour les boules, 1 à 12 étoiles. Simple, non ?",
]

# Cas spécial : étoile hors range
_OOR_ETOILE_EM = [
    "🎲 Étoile {num} ? Les étoiles vont de 1 à 12 seulement ! T'es un peu ambitieux sur ce coup. Choisis entre 1 et 12.",
    "💫 Pour les étoiles, c'est 1 à 12 max. Le {num} c'est hors jeu ! Mais l'enthousiasme est là, c'est l'essentiel 😉",
]


def _detect_out_of_range_em(message: str):
    """
    Detecte les numeros hors range de l'EuroMillions dans le message.
    Returns: (numero: int, context: str) ou (None, None)
    context: 'boule_high' | 'etoile_high' | 'zero_neg' | 'close'
    """
    lower = message.lower()

    # Etoile hors range (> 12)
    m = re.search(r'(?:num[eé]ro\s+)?[eé]toile\s+(\d+)', lower)
    if m:
        num = int(m.group(1))
        if num > 12:
            return num, "etoile_high"

    # Patterns similaires a _detect_numero_em mais avec \d+ pour capturer les hors range
    patterns = [
        r'(?:le\s+)?num[eé]ro\s+(-?\d+)(?:\s|$|[?.!,])',
        r'(?:fr[eé]quence|[eé]cart|retard|sortie?|chaud|froid|stat)\s+(?:du\s+)?(-?\d+)(?:\s|$|[?.!,])',
        r'\ble\s+(-?\d+)\s+(?:est|il|a\s|sort|[eé]tai)',
        r'\ble\s+(-?\d+)\s*[?.!]',
        r'(?:combien|quand|sorti|derni[eè]re).*\ble\s+(-?\d+)(?:\s|$|[?.!,])',
        r'\bdu\s+(-?\d+)\s*[?.!]',
        r'\bboule\s+(-?\d+)(?:\s|$|[?.!,])',
        r'\ble\s+(-?\d+)\b',
        r'\bdu\s+(-?\d+)\b',
    ]

    for pattern in patterns:
        m = re.search(pattern, lower)
        if m:
            num = int(m.group(1))
            # Ignorer les annees
            if 2019 <= num <= 2030:
                continue
            # Ignorer les numeros dans le range valide (geres par _detect_numero_em)
            if 1 <= num <= 50:
                continue
            if num <= 0:
                return num, "zero_neg"
            if num in (51, 52):
                return num, "close"
            if num > 50:
                return num, "boule_high"

    return None, None


def _count_oor_streak_em(history) -> int:
    """Compte les messages OOR consecutifs EM (du plus recent au plus ancien)."""
    count = 0
    for msg in reversed(history):
        if msg.role == "user":
            oor_num, _ = _detect_out_of_range_em(msg.content)
            if oor_num is not None:
                count += 1
            else:
                break
    return count


def _get_oor_response_em(numero: int, context: str, streak: int) -> str:
    """Selectionne une reponse OOR EM selon le contexte et le niveau d'escalade."""
    if context == "zero_neg":
        pool = _OOR_ZERO_NEG_EM
    elif context == "close":
        pool = _OOR_CLOSE_EM
    elif context == "etoile_high":
        pool = _OOR_ETOILE_EM
    elif streak >= 2:
        pool = _OOR_L3_EM
    elif streak == 1:
        pool = _OOR_L2_EM
    else:
        pool = _OOR_L1_EM

    response = random.choice(pool)
    diff = abs(numero - 50) if numero > 50 else abs(numero)
    s = "s" if diff > 1 else ""
    return response.format(
        num=numero,
        diff=diff,
        s=s,
        streak=streak + 1,
    )


# =========================
# HYBRIDE EuroMillions Chatbot — Gemini 2.0 Flash
# =========================

@router.post("/api/euromillions/hybride-chat")
@limiter.limit("10/minute")
async def api_hybride_chat_em(request: Request, payload: EMChatRequest):
    """Endpoint chatbot HYBRIDE EuroMillions — conversation via Gemini 2.0 Flash."""

    mode = _detect_mode_em(payload.message, payload.page)

    # Charger le prompt systeme
    system_prompt = load_prompt("CHATBOT_EM")
    if not system_prompt:
        logger.error("[EM CHAT] Prompt systeme introuvable")
        return EMChatResponse(
            response=FALLBACK_RESPONSE_EM, source="fallback", mode=mode
        )

    # Cle API
    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        logger.warning("[EM CHAT] GEM_API_KEY non configuree — fallback")
        return EMChatResponse(
            response=FALLBACK_RESPONSE_EM, source="fallback", mode=mode
        )

    # Construire les contents (historique + message actuel)
    contents = []

    # Historique (max 20 derniers messages) + garde anti-doublon
    history = (payload.history or [])[-20:]
    if history and history[-1].role == "user" and history[-1].content == payload.message:
        history = history[:-1]

    _skip_insult_response = False
    for msg in history:
        # Filtrer les echanges d'insultes (Phase I) du contexte Gemini
        if msg.role == "user" and _detect_insulte(msg.content):
            _skip_insult_response = True
            continue
        if msg.role == "assistant" and _skip_insult_response:
            _skip_insult_response = False
            continue
        _skip_insult_response = False

        role = "user" if msg.role == "user" else "model"
        # Nettoyer les sponsors des reponses assistant
        content = _strip_sponsor_from_text(msg.content) if role == "model" else msg.content
        # Fusionner les messages consecutifs de meme role (requis par Gemini)
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n" + content
        else:
            contents.append({"role": role, "parts": [{"text": content}]})

    # Gemini exige que contents commence par "user"
    while contents and contents[0]["role"] == "model":
        contents.pop(0)

    # ── Phase I : Détection d'insultes / agressivité ──
    _insult_prefix = ""
    _insult_type = _detect_insulte(payload.message)
    if _insult_type:
        _insult_streak = _count_insult_streak(history)
        # Verifier si le message contient aussi une question valide
        _has_question = (
            '?' in payload.message
            or bool(re.search(r'\b\d{1,2}\b', payload.message))
            or any(kw in payload.message.lower() for kw in (
                "numéro", "numero", "tirage", "grille", "fréquence", "frequence",
                "classement", "statistique", "stat", "analyse", "prochain",
                "étoile", "etoile",
            ))
        )
        if _has_question:
            # Insulte + question : punchline courte, continue le flow normal
            _insult_prefix = _get_insult_short_em()
            logger.info(
                f"[EM CHAT] Insulte + question (type={_insult_type}, streak={_insult_streak})"
            )
        else:
            # Insulte pure : punchline complete, early return
            if _insult_type == "menace":
                _insult_resp = _get_menace_response_em()
            else:
                _insult_resp = _get_insult_response_em(_insult_streak, history)
            logger.info(
                f"[EM CHAT] Insulte detectee (type={_insult_type}, streak={_insult_streak})"
            )
            return EMChatResponse(
                response=_insult_resp, source="hybride_insult", mode=mode
            )

    # ── Phase C : Détection de compliments ──
    if not _insult_prefix:  # Phase I n'a rien detecte
        _compliment_type = _detect_compliment(payload.message)
        if _compliment_type:
            # Verifier si le message contient aussi une question
            _has_question_c = (
                '?' in payload.message
                or bool(re.search(r'\b\d{1,2}\b', payload.message))
                or any(kw in payload.message.lower() for kw in (
                    "numéro", "numero", "tirage", "grille", "fréquence", "frequence",
                    "combien", "c'est quoi", "quel", "quelle", "comment", "pourquoi",
                    "classement", "statistique", "stat", "analyse",
                    "étoile", "etoile",
                ))
            )
            if not _has_question_c:
                # Compliment seul → Phase C repond directement
                _comp_streak = _count_compliment_streak(history)
                _comp_resp = _get_compliment_response_em(_compliment_type, _comp_streak, history)
                logger.info(
                    f"[EM CHAT] Compliment detecte (type={_compliment_type}, streak={_comp_streak})"
                )
                return EMChatResponse(
                    response=_comp_resp, source="hybride_compliment", mode=mode
                )
            else:
                logger.info(
                    f"[EM CHAT] Compliment + question (type={_compliment_type}), passage au flow normal"
                )

    # ── Phase 0 : Continuation contextuelle ──
    _continuation_mode = False
    _enriched_message = None

    if _is_short_continuation(payload.message) and history:
        _enriched_message = _enrich_with_context(payload.message, history)
        if _enriched_message != payload.message:
            _continuation_mode = True
            logger.info(
                f"[EM CONTINUATION] Reponse courte detectee: \"{payload.message}\" "
                f"→ enrichissement contextuel"
            )

    # Detection : Prochain tirage → Tirage (T) → Grille (2) → Complexe (3) → Numero (1) → Text-to-SQL (fallback)
    enrichment_context = ""

    # Phase 0-bis : prochain tirage (skip si continuation)
    if not _continuation_mode and _detect_prochain_tirage_em(payload.message):
        try:
            tirage_ctx = await asyncio.wait_for(asyncio.to_thread(_get_prochain_tirage_em), timeout=30.0)
            if tirage_ctx:
                enrichment_context = tirage_ctx
                logger.info("[EM CHAT] Prochain tirage injecte")
        except Exception as e:
            logger.warning(f"[EM CHAT] Erreur prochain tirage: {e}")

    # Phase T : resultats d'un tirage (dernier tirage, tirage d'hier, etc.)
    if not _continuation_mode and not enrichment_context:
        tirage_target = _detect_tirage(payload.message)
        if tirage_target is not None:
            try:
                tirage_data = await asyncio.wait_for(
                    asyncio.to_thread(_get_tirage_data_em, tirage_target), timeout=30.0
                )
                if tirage_data:
                    enrichment_context = _format_tirage_context_em(tirage_data)
                    logger.info(f"[EM CHAT] Tirage injecte: {tirage_data['date']}")
                elif tirage_target != "latest":
                    # Date demandee pas en base → message explicite anti-hallucination
                    date_fr = _format_date_fr(str(tirage_target))
                    enrichment_context = (
                        f"[RÉSULTAT TIRAGE — INTROUVABLE]\n"
                        f"Aucun tirage trouvé en base de données pour la date du {date_fr}.\n"
                        f"IMPORTANT : Ne PAS inventer de numéros. Indique simplement que "
                        f"ce tirage n'est pas disponible dans la base.\n"
                        f"Les tirages EuroMillions ont lieu les mardi et vendredi."
                    )
                    logger.info(f"[EM CHAT] Tirage introuvable pour: {tirage_target}")
            except Exception as e:
                logger.warning(f"[EM CHAT] Erreur tirage: {e}")

    # Filtre temporel detecte → skip phases regex, Phase SQL gere
    force_sql = not _continuation_mode and not enrichment_context and _has_temporal_filter(payload.message)
    if force_sql:
        logger.info("[EM CHAT] Filtre temporel detecte, force Phase SQL")

    # Phase 2 : detection de grille (5 numeros + etoiles)
    grille_nums, grille_etoiles = (None, None) if _continuation_mode else _detect_grille_em(payload.message)
    if not force_sql and grille_nums is not None:
        try:
            grille_result = await asyncio.wait_for(asyncio.to_thread(analyze_grille_for_chat, grille_nums, grille_etoiles), timeout=30.0)
            if grille_result:
                enrichment_context = _format_grille_context_em(grille_result)
                logger.info(f"[EM CHAT] Grille analysee: {grille_nums} etoiles={grille_etoiles}")
        except Exception as e:
            logger.warning(f"[EM CHAT] Erreur analyse grille: {e}")

    # Phase 3 : requete complexe (classement, comparaison, categorie)
    if not _continuation_mode and not force_sql and not enrichment_context:
        intent = _detect_requete_complexe_em(payload.message)
        if intent:
            try:
                if intent["type"] == "classement":
                    data = await asyncio.wait_for(asyncio.to_thread(get_classement_numeros, intent["num_type"], intent["tri"], intent["limit"]), timeout=30.0)
                elif intent["type"] == "comparaison":
                    data = await asyncio.wait_for(asyncio.to_thread(get_comparaison_numeros, intent["num1"], intent["num2"], intent["num_type"]), timeout=30.0)
                elif intent["type"] == "categorie":
                    data = await asyncio.wait_for(asyncio.to_thread(get_numeros_par_categorie, intent["categorie"], intent["num_type"]), timeout=30.0)
                else:
                    data = None

                if data:
                    enrichment_context = _format_complex_context_em(intent, data)
                    logger.info(f"[EM CHAT] Requete complexe: {intent['type']}")
            except Exception as e:
                logger.warning(f"[EM CHAT] Erreur requete complexe: {e}")

    # ── Phase OOR : Détection numéro hors range ──
    if not _continuation_mode and not force_sql and not enrichment_context:
        _oor_num, _oor_type = _detect_out_of_range_em(payload.message)
        if _oor_num is not None:
            _oor_streak = _count_oor_streak_em(history)
            _oor_resp = _get_oor_response_em(_oor_num, _oor_type, _oor_streak)
            if _insult_prefix:
                _oor_resp = _insult_prefix + "\n\n" + _oor_resp
            logger.info(
                f"[EM CHAT] Numero hors range: {_oor_num} "
                f"(type={_oor_type}, streak={_oor_streak})"
            )
            return EMChatResponse(
                response=_oor_resp, source="hybride_oor", mode=mode
            )

    # Phase 1 : detection de numero simple
    if not _continuation_mode and not force_sql and not enrichment_context:
        numero, type_num = _detect_numero_em(payload.message)
        if numero is not None:
            try:
                stats = await asyncio.wait_for(asyncio.to_thread(get_numero_stats, numero, type_num), timeout=30.0)
                if stats:
                    enrichment_context = _format_stats_context_em(stats)
                    logger.info(f"[EM CHAT] Stats BDD injectees: numero={numero}, type={type_num}")
            except Exception as e:
                logger.warning(f"[EM CHAT] Erreur stats BDD (numero={numero}): {e}")

    # Phase SQL : Text-to-SQL fallback (Gemini genere le SQL quand aucune phase ne matche)
    if not _continuation_mode and not enrichment_context:
        _sql_count = sum(1 for m in (payload.history or []) if m.role == "user")
        if _sql_count >= _MAX_SQL_PER_SESSION:
            logger.info(f"[EM TEXT2SQL] Rate-limit session ({_sql_count} echanges)")
        else:
            t0 = time.monotonic()
            try:
                sql_client = request.app.state.httpx_client
                sql = await asyncio.wait_for(
                    _generate_sql_em(payload.message, sql_client, gem_api_key, history=payload.history),
                    timeout=10.0,
                )
                if sql and sql.strip().upper() != "NO_SQL" and _validate_sql(sql):
                    sql = _ensure_limit(sql)
                    rows = await asyncio.wait_for(
                        asyncio.to_thread(_execute_safe_sql, sql), timeout=5.0
                    )
                    t_total = int((time.monotonic() - t0) * 1000)
                    if rows is not None and len(rows) > 0:
                        enrichment_context = _format_sql_result(rows)
                        logger.info(
                            f'[EM TEXT2SQL] question="{payload.message[:80]}" | '
                            f'sql="{sql[:120]}" | status=OK | '
                            f'rows={len(rows)} | time={t_total}ms'
                        )
                    elif rows is not None:
                        enrichment_context = "[RÉSULTAT SQL]\nAucun résultat trouvé pour cette requête."
                        logger.info(
                            f'[EM TEXT2SQL] question="{payload.message[:80]}" | '
                            f'sql="{sql[:120]}" | status=EMPTY | '
                            f'rows=0 | time={t_total}ms'
                        )
                    else:
                        enrichment_context = "[RÉSULTAT SQL]\nAucun résultat trouvé pour cette requête."
                        logger.warning(
                            f'[EM TEXT2SQL] question="{payload.message[:80]}" | '
                            f'sql="{sql[:120]}" | status=EXEC_ERROR | '
                            f'time={t_total}ms'
                        )
                elif sql and sql.strip().upper() == "NO_SQL":
                    logger.info(
                        f'[EM TEXT2SQL] question="{payload.message[:80]}" | '
                        f'sql=NO_SQL | status=NO_SQL | '
                        f'time={int((time.monotonic() - t0) * 1000)}ms'
                    )
                elif sql:
                    logger.warning(
                        f'[EM TEXT2SQL] question="{payload.message[:80]}" | '
                        f'sql="{sql[:120]}" | status=REJECTED | '
                        f'time={int((time.monotonic() - t0) * 1000)}ms'
                    )
                else:
                    logger.warning(
                        f'[EM TEXT2SQL] question="{payload.message[:80]}" | '
                        f'status=GEN_ERROR | '
                        f'time={int((time.monotonic() - t0) * 1000)}ms'
                    )
            except asyncio.TimeoutError:
                logger.warning(
                    f'[EM TEXT2SQL] question="{payload.message[:80]}" | '
                    f'status=TIMEOUT | '
                    f'time={int((time.monotonic() - t0) * 1000)}ms'
                )
            except Exception as e:
                logger.warning(
                    f'[EM TEXT2SQL] question="{payload.message[:80]}" | '
                    f'status=ERROR | error="{e}" | '
                    f'time={int((time.monotonic() - t0) * 1000)}ms'
                )

    # Fallback regex quand Phase SQL echoue avec filtre temporel
    if force_sql and not enrichment_context:
        logger.info("[EM CHAT] Phase SQL echouee, fallback phases regex (donnees globales)")
        intent = _detect_requete_complexe_em(payload.message)
        if intent:
            try:
                if intent["type"] == "classement":
                    data = await asyncio.wait_for(asyncio.to_thread(get_classement_numeros, intent["num_type"], intent["tri"], intent["limit"]), timeout=30.0)
                elif intent["type"] == "comparaison":
                    data = await asyncio.wait_for(asyncio.to_thread(get_comparaison_numeros, intent["num1"], intent["num2"], intent["num_type"]), timeout=30.0)
                elif intent["type"] == "categorie":
                    data = await asyncio.wait_for(asyncio.to_thread(get_numeros_par_categorie, intent["categorie"], intent["num_type"]), timeout=30.0)
                else:
                    data = None
                if data:
                    enrichment_context = _format_complex_context_em(intent, data)
                    logger.info(f"[EM CHAT] Fallback Phase 3: {intent['type']}")
            except Exception as e:
                logger.warning(f"[EM CHAT] Fallback Phase 3 erreur: {e}")
        if not enrichment_context:
            numero, type_num = _detect_numero_em(payload.message)
            if numero is not None:
                try:
                    stats = await asyncio.wait_for(asyncio.to_thread(get_numero_stats, numero, type_num), timeout=30.0)
                    if stats:
                        enrichment_context = _format_stats_context_em(stats)
                        logger.info(f"[EM CHAT] Fallback Phase 1: numero={numero}")
                except Exception as e:
                    logger.warning(f"[EM CHAT] Fallback Phase 1 erreur: {e}")

    # DEBUG — tracer l'etat avant appel Gemini final
    logger.info(
        f"[EM DEBUG] force_sql={force_sql} | continuation={_continuation_mode} | "
        f"enrichment={bool(enrichment_context)} | "
        f"question=\"{payload.message[:60]}\" | history_len={len(payload.history or [])}"
    )

    # Session context — resume des numeros/tirages consultes
    _session_ctx = _build_session_context_em(history, payload.message)

    # Message utilisateur avec contexte de page + donnees BDD
    if _continuation_mode and _enriched_message:
        # Phase 0 : envoyer le message enrichi a Gemini (bypass regex)
        user_text = f"[Page: {payload.page}]\n\n{_enriched_message}"
    elif enrichment_context:
        user_text = f"[Page: {payload.page}]\n\n{enrichment_context}\n\n[Question utilisateur] {payload.message}"
    else:
        user_text = f"[Page: {payload.page}] {payload.message}"

    if _session_ctx:
        user_text = f"{_session_ctx}\n\n{user_text}"

    contents.append({"role": "user", "parts": [{"text": user_text}]})

    try:
        client = request.app.state.httpx_client
        response = await gemini_breaker.call(
            client,
            GEMINI_MODEL_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": gem_api_key,
            },
            json={
                "system_instruction": {
                    "parts": [{"text": system_prompt}]
                },
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.8,
                    "maxOutputTokens": 300,
                },
            },
            timeout=15.0,
        )

        if response.status_code == 200:
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    text = parts[0].get("text", "").strip()
                    if text:
                        text = _clean_response(text)
                        # Injection punchline si insulte + question
                        if _insult_prefix:
                            text = _insult_prefix + "\n\n" + text
                        # Injection sponsor post-Gemini
                        sponsor_line = _get_sponsor_if_due(history)
                        if sponsor_line:
                            text += "\n\n" + sponsor_line
                        logger.info(
                            f"[EM CHAT] OK (page={payload.page}, mode={mode})"
                        )
                        return EMChatResponse(
                            response=text, source="gemini", mode=mode
                        )

        logger.warning(
            f"[EM CHAT] Reponse Gemini invalide: {response.status_code}"
        )
        return EMChatResponse(
            response=FALLBACK_RESPONSE_EM, source="fallback", mode=mode
        )

    except CircuitOpenError:
        logger.warning("[EM CHAT] Circuit breaker ouvert — fallback")
        return EMChatResponse(
            response=FALLBACK_RESPONSE_EM, source="fallback_circuit", mode=mode
        )
    except httpx.TimeoutException:
        logger.warning("[EM CHAT] Timeout Gemini (15s) — fallback")
        return EMChatResponse(
            response=FALLBACK_RESPONSE_EM, source="fallback", mode=mode
        )
    except Exception as e:
        logger.error(f"[EM CHAT] Erreur Gemini: {e}")
        return EMChatResponse(
            response=FALLBACK_RESPONSE_EM, source="fallback", mode=mode
        )


# =========================
# PITCH GRILLES EM — Gemini
# =========================

@router.post("/api/euromillions/pitch-grilles")
@limiter.limit("10/minute")
async def api_pitch_grilles_em(request: Request, payload: EMPitchGrillesRequest):
    """Genere des pitchs HYBRIDE personnalises pour chaque grille EM via Gemini."""

    # Validation
    if not payload.grilles or len(payload.grilles) > 5:
        return JSONResponse(status_code=400, content={
            "success": False, "data": None, "error": "Entre 1 et 5 grilles requises"
        })

    for i, g in enumerate(payload.grilles):
        if len(g.numeros) != 5:
            return JSONResponse(status_code=400, content={
                "success": False, "data": None, "error": f"Grille {i+1}: 5 numéros requis"
            })
        if len(set(g.numeros)) != 5:
            return JSONResponse(status_code=400, content={
                "success": False, "data": None, "error": f"Grille {i+1}: numéros doivent être uniques"
            })
        if not all(1 <= n <= 50 for n in g.numeros):
            return JSONResponse(status_code=400, content={
                "success": False, "data": None, "error": f"Grille {i+1}: numéros entre 1 et 50"
            })
        # Validate etoiles
        if g.etoiles is not None:
            if len(g.etoiles) > 2:
                return JSONResponse(status_code=400, content={
                    "success": False, "data": None, "error": f"Grille {i+1}: maximum 2 étoiles"
                })
            if len(g.etoiles) != len(set(g.etoiles)):
                return JSONResponse(status_code=400, content={
                    "success": False, "data": None, "error": f"Grille {i+1}: étoiles doivent être uniques"
                })
            if not all(1 <= e <= 12 for e in g.etoiles):
                return JSONResponse(status_code=400, content={
                    "success": False, "data": None, "error": f"Grille {i+1}: étoiles entre 1 et 12"
                })

    # Preparer le contexte stats
    grilles_data = [{"numeros": g.numeros, "etoiles": g.etoiles, "score_conformite": g.score_conformite, "severity": g.severity} for g in payload.grilles]

    try:
        context = await asyncio.wait_for(asyncio.to_thread(prepare_grilles_pitch_context, grilles_data), timeout=30.0)
    except asyncio.TimeoutError:
        logger.error("[EM PITCH] Timeout 30s contexte stats")
        return JSONResponse(status_code=503, content={
            "success": False, "data": None, "error": "Service temporairement indisponible"
        })
    except Exception as e:
        logger.warning(f"[EM PITCH] Erreur contexte stats: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur données statistiques"
        })

    if not context:
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Impossible de préparer le contexte"
        })

    # Charger le prompt
    system_prompt = load_prompt("PITCH_GRILLE_EM")
    if not system_prompt:
        logger.error("[EM PITCH] Prompt pitch introuvable")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Prompt pitch introuvable"
        })

    # Cle API
    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "API Gemini non configurée"
        })

    # Appel Gemini (1 seul appel pour toutes les grilles)
    try:
        client = request.app.state.httpx_client
        response = await gemini_breaker.call(
            client,
            GEMINI_MODEL_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": gem_api_key,
            },
            json={
                "system_instruction": {
                    "parts": [{"text": system_prompt}]
                },
                "contents": [{
                    "role": "user",
                    "parts": [{"text": context}]
                }],
                "generationConfig": {
                    "temperature": 0.9,
                    "maxOutputTokens": 600,
                },
            },
            timeout=15.0,
        )

        if response.status_code != 200:
            logger.warning(f"[EM PITCH] Gemini HTTP {response.status_code}")
            return JSONResponse(status_code=502, content={
                "success": False, "data": None, "error": f"Gemini erreur HTTP {response.status_code}"
            })

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return JSONResponse(status_code=502, content={
                "success": False, "data": None, "error": "Gemini: aucune réponse"
            })

        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        if not text:
            return JSONResponse(status_code=502, content={
                "success": False, "data": None, "error": "Gemini: réponse vide"
            })

        # Parser le JSON (nettoyer si Gemini ajoute des backticks)
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()

        try:
            result = json_mod.loads(clean)
            pitchs = result.get("pitchs", [])
        except (json_mod.JSONDecodeError, AttributeError):
            logger.warning(f"[EM PITCH] JSON invalide: {text[:200]}")
            return JSONResponse(status_code=502, content={
                "success": False, "data": None, "error": "Gemini: JSON mal formé"
            })

        logger.info(f"[EM PITCH] OK — {len(pitchs)} pitchs générés")
        return {"success": True, "data": {"pitchs": pitchs}, "error": None}

    except CircuitOpenError:
        logger.warning("[EM PITCH] Circuit breaker ouvert — fallback")
        return JSONResponse(status_code=503, content={
            "success": False, "data": None, "error": "Service Gemini temporairement indisponible"
        })
    except httpx.TimeoutException:
        logger.warning("[EM PITCH] Timeout Gemini (15s)")
        return JSONResponse(status_code=503, content={
            "success": False, "data": None, "error": "Timeout Gemini"
        })
    except Exception as e:
        logger.error(f"[EM PITCH] Erreur: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur interne du serveur"
        })
