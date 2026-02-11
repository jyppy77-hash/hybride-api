import os
import re
import asyncio
import logging
import time
import httpx
from pathlib import Path
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import json as json_mod

from schemas import HybrideChatRequest, HybrideChatResponse, PitchGrillesRequest
from services.prompt_loader import load_prompt
from services.gemini import GEMINI_MODEL_URL
from services.circuit_breaker import gemini_breaker, CircuitOpenError
from rate_limit import limiter
from services.stats_service import (
    get_numero_stats, analyze_grille_for_chat,
    get_classement_numeros, get_comparaison_numeros, get_numeros_par_categorie,
    prepare_grilles_pitch_context,
)
import db_cloudsql

logger = logging.getLogger(__name__)

router = APIRouter()

FALLBACK_RESPONSE = (
    "\U0001f916 Je suis momentan\u00e9ment indisponible. "
    "R\u00e9essaie dans quelques secondes ou consulte la FAQ !"
)

META_KEYWORDS = ["meta", "algorithme", "moteur", "pond\u00e9ration", "ponderation"]

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
            _sponsors_config = json_mod.load(f)
    except (FileNotFoundError, json_mod.JSONDecodeError) as e:
        logger.warning(f"[SPONSOR] Config introuvable ou invalide: {e}")
        _sponsors_config = {"enabled": False, "frequency": 3, "sponsors": []}
    return _sponsors_config


def _get_sponsor_if_due(history: list) -> str | None:
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
    if cycle % 2 == 1:
        return "\U0001f4e2 Cet espace est r\u00e9serv\u00e9 \u00e0 nos partenaires \u2014 Pour en savoir plus : partenariats@lotoia.fr"
    else:
        return "\u2014 Espace partenaire disponible | partenariats@lotoia.fr"


def _clean_response(text: str) -> str:
    """Supprime les tags internes qui ne doivent pas \u00eatre vus par l'utilisateur."""
    internal_tags = [
        r'\[R\u00c9SULTAT SQL\]',
        r'\[RESULTAT SQL\]',
        r'\[R\u00c9SULTAT TIRAGE[^\]]*\]',
        r'\[RESULTAT TIRAGE[^\]]*\]',
        r'\[ANALYSE DE GRILLE[^\]]*\]',
        r'\[CLASSEMENT[^\]]*\]',
        r'\[COMPARAISON[^\]]*\]',
        r'\[NUM\u00c9ROS? (?:CHAUDS?|FROIDS?)[^\]]*\]',
        r'\[NUMEROS? (?:CHAUDS?|FROIDS?)[^\]]*\]',
        r'\[DONN\u00c9ES TEMPS R\u00c9EL[^\]]*\]',
        r'\[DONNEES TEMPS REEL[^\]]*\]',
        r'\[PROCHAIN TIRAGE[^\]]*\]',
        r'\[Page:\s*[^\]]*\]',
        r'\[Question utilisateur[^\]]*\]',
    ]
    for tag in internal_tags:
        text = re.sub(tag, '', text)
    # Nettoyer les espaces multiples et lignes vides r\u00e9sultants
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def _detect_mode(message: str, page: str) -> str:
    lower = message.lower()
    for kw in META_KEYWORDS:
        if kw in lower:
            return "meta"
    if page in ("simulateur", "loto", "statistiques"):
        return "analyse"
    return "decouverte"


def _detect_prochain_tirage(message: str) -> bool:
    """Detecte si l'utilisateur demande la date du prochain tirage."""
    lower = message.lower()
    return bool(re.search(
        r'(?:prochain|prochaine|quand|date)\s+.*(?:tirage|loto|draw)'
        r'|(?:tirage|loto)\s+.*(?:prochain|prochaine|quand|date)'
        r'|c.est\s+quand\s+(?:le\s+)?(?:prochain\s+)?(?:tirage|loto)'
        r'|(?:il\s+(?:y\s+a|est)\s+(?:un\s+)?tirage\s+quand)'
        r'|(?:quand\s+(?:est|a)\s+lieu)'
        r'|(?:prochain\s+(?:tirage|loto))',
        lower
    ))


# Jours de tirage FDJ : lundi (0), mercredi (2), samedi (5)
_JOURS_TIRAGE = [0, 2, 5]

_JOURS_FR = {
    0: "lundi", 1: "mardi", 2: "mercredi", 3: "jeudi",
    4: "vendredi", 5: "samedi", 6: "dimanche",
}


def _get_prochain_tirage() -> str | None:
    """
    Calcule la date du prochain tirage a partir de la date du jour
    et des jours de tirage FDJ (lundi, mercredi, samedi).
    Returns: contexte formate ou None si erreur.
    """
    try:
        today = date.today()

        # Chercher le prochain jour de tirage (y compris aujourd'hui)
        for delta in range(7):
            candidate = today + timedelta(days=delta)
            if candidate.weekday() in _JOURS_TIRAGE:
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
                cursor.execute("SELECT MAX(date_de_tirage) as last FROM tirages")
                row = cursor.fetchone()
                last_draw = str(row['last']) if row and row['last'] else None
            finally:
                conn.close()
        except Exception:
            last_draw = None

        lines = [f"[PROCHAIN TIRAGE]"]
        lines.append(f"Date du prochain tirage : {jour_fr} {date_str} ({quand})")
        lines.append(f"Jours de tirage FDJ : lundi, mercredi et samedi")
        if last_draw:
            lines.append(f"Dernier tirage en base : {last_draw}")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[HYBRIDE CHAT] Erreur calcul prochain tirage: {e}")
        return None


_JOURS_SEMAINE = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
    "vendredi": 4, "samedi": 5, "dimanche": 6,
}

_TIRAGE_KW = r'(?:tirage|r[ée]sultat|num[eé]ro|nuro|boule|sorti|tomb[eé]|tir[eé])'


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

    # Jour de la semaine : "tirage de samedi", "numeros de lundi"
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


# ────────────────────────────────────────────
# Detection filtre temporel → court-circuite les phases regex
# ────────────────────────────────────────────

_MOIS_RE = r'(?:janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre)'

_TEMPORAL_PATTERNS = [
    r'\ben\s+20\d{2}\b',                          # en 2025
    r'\bdepuis\s+20\d{2}\b',                       # depuis 2023
    r'\bavant\s+20\d{2}\b',                        # avant 2025
    r'\bapr[eè]s\s+20\d{2}\b',                    # après 2024
    r'\bentre\s+20\d{2}\s+et\s+20\d{2}',          # entre 2024 et 2025
    r'\bcette\s+ann[ée]e\b',                       # cette année
    r'\bl.ann[ée]e\s+derni[eè]re\b',              # l'année dernière
    r'\bl.an\s+dernier\b',                         # l'an dernier
    r'\bce\s+mois\b',                              # ce mois
    r'\ble\s+mois\s+dernier\b',                    # le mois dernier
    r'\ben\s+' + _MOIS_RE,                         # en janvier, en février...
    r'\bces\s+\d+\s+derniers?\s+mois\b',           # ces 6 derniers mois
    r'\bdepuis\s+le\s+d[eé]but\b',                # depuis le début
    r'\bdepuis\s+\d+\s+(?:mois|ans?|semaines?)\b', # depuis 3 mois
    # "l'année 2024" avec prépositions variées
    r'(?:dans|pour|sur|pendant)\s+l[\'\u2019]?ann[ée]e\s+20\d{2}',  # dans/pour/sur/pendant l'année 2024
    r'\bau\s+cours\s+de\s+l[\'\u2019]?ann[ée]e\s+20\d{2}',          # au cours de l'année 2024
    r'\bl[\'\u2019]?ann[ée]e\s+20\d{2}\b',                           # l'année 2024 (seul)
    r'\bdepuis\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',                  # depuis l'année 2023
    r'\bavant\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',                   # avant l'année 2024
    r'\bapr[eè]s\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',               # après l'année 2023
    r'\bentre\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\s+et',                # entre l'année 2022 et ...
    r'\bde\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',                      # de l'année 2024
]


def _has_temporal_filter(message: str) -> bool:
    """Detecte si le message contient un filtre temporel (annee, mois, periode)."""
    lower = message.lower()
    return any(re.search(pat, lower) for pat in _TEMPORAL_PATTERNS)


def _get_tirage_data(target) -> dict | None:
    """
    Recupere un tirage depuis la DB.
    target: "latest" ou un objet date.
    Retourne dict {date, boules, chance} ou None.
    """
    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()
        if target == "latest":
            cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance
                FROM tirages ORDER BY date_de_tirage DESC LIMIT 1
            """)
        else:
            cursor.execute("""
                SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance
                FROM tirages WHERE date_de_tirage <= %s
                ORDER BY date_de_tirage DESC LIMIT 1
            """, (target,))

        row = cursor.fetchone()
        if row:
            return {
                "date": row["date_de_tirage"],
                "boules": [row["boule_1"], row["boule_2"], row["boule_3"],
                           row["boule_4"], row["boule_5"]],
                "chance": row["numero_chance"],
            }
        return None
    except Exception as e:
        logger.error(f"[HYBRIDE CHAT] Erreur _get_tirage_data: {e}")
        return None
    finally:
        conn.close()


def _format_tirage_context(tirage: dict) -> str:
    """Formate les resultats d'un tirage en bloc de contexte pour Gemini."""
    date_fr = _format_date_fr(str(tirage["date"]))
    boules = " - ".join(str(b) for b in tirage["boules"])
    return (
        f"[R\u00c9SULTAT TIRAGE - {date_fr}]\n"
        f"Date du tirage : {date_fr}\n"
        f"Num\u00e9ros principaux : {boules}\n"
        f"Num\u00e9ro Chance : {tirage['chance']}"
    )


# ────────────────────────────────────────────
# Text-to-SQL : Gemini genere le SQL, Python l'execute
# ────────────────────────────────────────────

_MAX_SQL_PER_SESSION = 10

_SQL_FORBIDDEN = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "REPLACE INTO", "GRANT", "REVOKE", "EXEC ", "EXECUTE", "CALL ",
    "SLEEP", "BENCHMARK", "LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE",
    "INFORMATION_SCHEMA", "MYSQL.", "PERFORMANCE_SCHEMA", "SYS.",
]


async def _generate_sql(question: str, client, api_key: str, history: list = None) -> str | None:
    """Appelle Gemini pour convertir une question en SQL (avec contexte conversationnel)."""
    sql_prompt = load_prompt("SQL_GENERATOR")
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
        logger.warning(f"[TEXT-TO-SQL] Erreur generation SQL: {e}")
        return None


def _validate_sql(sql: str) -> bool:
    """Valide la securite du SQL genere (SELECT only, pas de mots interdits)."""
    if not sql:
        return False
    if len(sql) > 1000:
        return False
    upper = sql.strip().upper()
    if not upper.startswith("SELECT"):
        return False
    if ";" in sql:
        return False
    if "--" in sql or "/*" in sql:
        return False
    for kw in _SQL_FORBIDDEN:
        if kw in upper:
            return False
    return True


def _ensure_limit(sql: str, max_limit: int = 50) -> str:
    """Ajoute LIMIT si absent, plafonne a max_limit si present."""
    upper = sql.strip().upper()
    if "LIMIT" not in upper:
        return sql.rstrip() + f" LIMIT {max_limit}"
    return sql


def _execute_safe_sql(sql: str) -> list | None:
    """Execute le SQL valide avec connexion DB."""
    conn = db_cloudsql.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return rows
    except Exception as e:
        logger.warning(f"[TEXT-TO-SQL] Erreur execution SQL: {e}")
        return None
    finally:
        conn.close()


def _format_sql_result(rows: list) -> str:
    """Formate les resultats SQL en bloc de contexte pour Gemini."""
    if not rows:
        return "[R\u00c9SULTAT SQL]\nAucun r\u00e9sultat trouv\u00e9 pour cette requ\u00eate."

    lines = ["[R\u00c9SULTAT SQL]"]

    for row in rows[:20]:
        parts = []
        for key, val in row.items():
            if hasattr(val, 'strftime'):
                val = _format_date_fr(str(val))
            elif isinstance(val, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', val):
                val = _format_date_fr(val)
            parts.append(f"{key}: {val}")
        lines.append(" | ".join(parts))

    if len(rows) > 20:
        lines.append(f"... ({len(rows)} r\u00e9sultats au total, 20 premiers affich\u00e9s)")

    return "\n".join(lines)


def _detect_numero(message: str):
    """
    Detecte si l'utilisateur pose une question sur un numero specifique.
    Returns: (numero: int, type_num: str) ou (None, None)
    """
    lower = message.lower()

    # Pattern chance : "numero chance X", "chance X"
    m = re.search(r'(?:num[eé]ro\s+)?chance\s+(\d{1,2})', lower)
    if m:
        num = int(m.group(1))
        if 1 <= num <= 10:
            return num, "chance"

    # Patterns principal :
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
            if 1 <= num <= 49:
                return num, "principal"

    return None, None


_MOIS_FR = [
    "", "janvier", "f\u00e9vrier", "mars", "avril", "mai", "juin",
    "juillet", "ao\u00fbt", "septembre", "octobre", "novembre", "d\u00e9cembre",
]


def _format_date_fr(date_str: str) -> str:
    """Convertit une date ISO (2026-02-09) en format francais (9 f\u00e9vrier 2026)."""
    try:
        d = datetime.strptime(str(date_str), "%Y-%m-%d")
        return f"{d.day} {_MOIS_FR[d.month]} {d.year}"
    except (ValueError, TypeError):
        return str(date_str) if date_str else "inconnue"


def _format_stats_context(stats: dict) -> str:
    """
    Formate les stats d'un numero en bloc de contexte pour Gemini.
    """
    type_label = "principal" if stats["type"] == "principal" else "chance"
    cat = stats["categorie"].upper()
    classement_sur = stats.get("classement_sur", 49)
    derniere_sortie_fr = _format_date_fr(stats['derniere_sortie'])

    return (
        f"[DONN\u00c9ES TEMPS R\u00c9EL - Num\u00e9ro {type_label} {stats['numero']}]\n"
        f"Fr\u00e9quence totale : {stats['frequence_totale']} apparitions "
        f"sur {stats['total_tirages']} tirages ({stats['pourcentage_apparition']})\n"
        f"Derni\u00e8re sortie : {derniere_sortie_fr}\n"
        f"\u00c9cart actuel : {stats['ecart_actuel']} tirages\n"
        f"\u00c9cart moyen : {stats['ecart_moyen']} tirages\n"
        f"Classement fr\u00e9quence : {stats['classement']}e sur {classement_sur}\n"
        f"Cat\u00e9gorie : {cat}\n"
        f"P\u00e9riode analys\u00e9e : {_format_periode_fr(stats['periode'])}"
    )


def _format_periode_fr(periode: str) -> str:
    """Convertit '2019-11-04 au 2026-02-07' en '4 novembre 2019 au 7 f\u00e9vrier 2026'."""
    try:
        parts = periode.split(" au ")
        if len(parts) == 2:
            return f"{_format_date_fr(parts[0])} au {_format_date_fr(parts[1])}"
    except Exception:
        pass
    return periode


def _detect_grille(message: str):
    """
    Detecte si l'utilisateur fournit une grille de 5 numeros (+ chance optionnel).
    Returns: (numeros: list[int], chance: int|None) ou (None, None)
    """
    text = message.lower()

    # Extraire le numero chance d'abord (et le retirer du texte)
    chance = None
    chance_patterns = [
        r'chance\s*[:\s]*(\d{1,2})',
        r'n[°o]?\s*chance\s*[:\s]*(\d{1,2})',
        r'\+\s*(\d{1,2})\s*$',
    ]
    for pat in chance_patterns:
        m = re.search(pat, text)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 10:
                chance = val
                text = text[:m.start()] + text[m.end():]
                break

    # Extraire tous les nombres du message (1-2 chiffres)
    all_numbers = [int(x) for x in re.findall(r'\b(\d{1,2})\b', text)]

    # Filtrer : garder uniquement ceux entre 1 et 49
    valid_nums = [n for n in all_numbers if 1 <= n <= 49]

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

    return unique_nums, chance


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
    lines.append(f"Somme : {a['somme']} (id\u00e9al : 100-140) {ok(a['somme_ok'])}")
    lines.append(f"Pairs : {a['pairs']} / Impairs : {a['impairs']} {ok(a['equilibre_pair_impair'])}")
    lines.append(f"Bas (1-24) : {a['bas']} / Hauts (25-49) : {a['hauts']} {ok(a['equilibre_bas_haut'])}")
    lines.append(f"Dispersion : {a['dispersion']} (id\u00e9al : >= 15) {ok(a['dispersion_ok'])}")
    lines.append(f"Cons\u00e9cutifs : {a['consecutifs']} {ok(a['consecutifs'] <= 2)}")

    # Chaud/froid
    if a['numeros_chauds']:
        lines.append(f"Num\u00e9ros chauds : {', '.join(str(n) for n in a['numeros_chauds'])}")
    if a['numeros_froids']:
        lines.append(f"Num\u00e9ros froids : {', '.join(str(n) for n in a['numeros_froids'])}")
    if a['numeros_neutres']:
        lines.append(f"Num\u00e9ros neutres : {', '.join(str(n) for n in a['numeros_neutres'])}")

    lines.append(f"Conformit\u00e9 : {a['conformite_pct']}%")
    lines.append(f"Badges : {', '.join(a['badges'])}")

    # Historique
    if h['deja_sortie']:
        lines.append(f"Historique : combinaison d\u00e9j\u00e0 sortie le {', '.join(h['exact_dates'])}")
    else:
        mc = h['meilleure_correspondance']
        if mc['nb_numeros_communs'] > 0:
            communs = ', '.join(str(n) for n in mc['numeros_communs'])
            lines.append(
                f"Historique : jamais sortie. Meilleure correspondance : "
                f"{mc['nb_numeros_communs']} num\u00e9ros communs le {mc['date']} ({communs})"
            )
        else:
            lines.append("Historique : combinaison jamais sortie")

    return "\n".join(lines)


def _detect_requete_complexe(message: str):
    """
    Detecte les requetes complexes : classements, comparaisons, categories.
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
            is_chance = "chance" in lower
            if is_chance and 1 <= n1 <= 10 and 1 <= n2 <= 10:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "chance"}
            if 1 <= n1 <= 49 and 1 <= n2 <= 49 and n1 != n2:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "principal"}

    # --- Categorie chaud/froid ---
    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*chauds?', lower) or \
       re.search(r'chauds?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'(?:num[eé]ros?|lesquels)\s+(?:sont|en)\s+tendance', lower):
        num_type = "chance" if "chance" in lower else "principal"
        return {"type": "categorie", "categorie": "chaud", "num_type": num_type}

    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*froids?', lower) or \
       re.search(r'froids?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'num[eé]ros?\s+(?:en\s+retard|qui\s+sort\w*\s+(?:pas|plus|jamais))', lower):
        num_type = "chance" if "chance" in lower else "principal"
        return {"type": "categorie", "categorie": "froid", "num_type": num_type}

    # --- Classement : top/plus frequents/retards ---
    # Extraire le limit (top N)
    limit_match = re.search(r'top\s+(\d{1,2})', lower)
    limit = int(limit_match.group(1)) if limit_match else 5
    limit = min(limit, 15)

    num_type = "chance" if "chance" in lower else "principal"

    # Plus frequents / plus sortis
    if re.search(r'(?:plus|les?\s+plus)\s+(?:fr[eé]quent|sorti|courant|pr[eé]sent)', lower) or \
       re.search(r'(?:top|meilleur|premier)\s+\d{0,2}\s*(?:num[eé]ro|boule|chance)?', lower) or \
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


def _format_complex_context(intent: dict, data) -> str:
    """
    Formate le resultat d'une requete complexe en contexte pour Gemini.
    """
    if intent["type"] == "classement":
        tri_labels = {
            "frequence_desc": "les plus fr\u00e9quents",
            "frequence_asc": "les moins fr\u00e9quents",
            "ecart_desc": "les plus en retard",
            "ecart_asc": "sortis le plus r\u00e9cemment",
        }
        label = tri_labels.get(intent["tri"], intent["tri"])
        limit = intent["limit"]
        type_label = "chance" if intent["num_type"] == "chance" else "principaux"

        lines = [f"[CLASSEMENT - Top {limit} num\u00e9ros {type_label} {label}]"]
        for i, item in enumerate(data["items"], 1):
            cat = item["categorie"].upper()
            lines.append(
                f"{i}. Num\u00e9ro {item['numero']} : "
                f"{item['frequence']} apparitions "
                f"(\u00e9cart actuel : {item['ecart_actuel']}) — {cat}"
            )
        lines.append(
            f"Total tirages analys\u00e9s : {data['total_tirages']} | "
            f"P\u00e9riode : {data['periode']}"
        )
        return "\n".join(lines)

    elif intent["type"] == "comparaison":
        s1 = data["num1"]
        s2 = data["num2"]
        diff = data["diff_frequence"]
        sign = "+" if diff > 0 else ""

        lines = [f"[COMPARAISON - Num\u00e9ro {s1['numero']} vs Num\u00e9ro {s2['numero']}]"]
        lines.append(
            f"Num\u00e9ro {s1['numero']} : {s1['frequence_totale']} apparitions "
            f"({s1['pourcentage_apparition']}) | \u00c9cart : {s1['ecart_actuel']} | "
            f"Cat\u00e9gorie : {s1['categorie'].upper()}"
        )
        lines.append(
            f"Num\u00e9ro {s2['numero']} : {s2['frequence_totale']} apparitions "
            f"({s2['pourcentage_apparition']}) | \u00c9cart : {s2['ecart_actuel']} | "
            f"Cat\u00e9gorie : {s2['categorie'].upper()}"
        )
        if diff != 0:
            favori = data["favori_frequence"]
            lines.append(
                f"Diff\u00e9rence de fr\u00e9quence : {sign}{diff} apparitions "
                f"en faveur du {favori}"
            )
        else:
            lines.append("Fr\u00e9quences identiques")
        return "\n".join(lines)

    elif intent["type"] == "categorie":
        cat = data["categorie"].upper()
        nums_list = [str(item["numero"]) for item in data["numeros"]]

        lines = [f"[NUM\u00c9ROS {cat}S - {data['count']} num\u00e9ros sur {data['periode_analyse']}]"]
        lines.append(f"Num\u00e9ros : {', '.join(nums_list)}")
        lines.append(f"Bas\u00e9 sur les tirages des {data['periode_analyse']}")
        return "\n".join(lines)

    return ""


# =========================
# HYBRIDE Chatbot — Gemini 2.0 Flash
# =========================

@router.post("/api/hybride-chat")
@limiter.limit("10/minute")
async def api_hybride_chat(request: Request, payload: HybrideChatRequest):
    """Endpoint chatbot HYBRIDE — conversation via Gemini 2.0 Flash."""

    mode = _detect_mode(payload.message, payload.page)

    # Charger le prompt systeme
    system_prompt = load_prompt("CHATBOT")
    if not system_prompt:
        logger.error("[HYBRIDE CHAT] Prompt systeme introuvable")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )

    # Cle API
    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        logger.warning("[HYBRIDE CHAT] GEM_API_KEY non configuree — fallback")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )

    # Construire les contents (historique + message actuel)
    contents = []

    # Historique (max 20 derniers messages) + garde anti-doublon
    history = (payload.history or [])[-20:]
    if history and history[-1].role == "user" and history[-1].content == payload.message:
        history = history[:-1]

    for msg in history:
        role = "user" if msg.role == "user" else "model"
        # Fusionner les messages consecutifs de meme role (requis par Gemini)
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n" + msg.content
        else:
            contents.append({"role": role, "parts": [{"text": msg.content}]})

    # Gemini exige que contents commence par "user"
    while contents and contents[0]["role"] == "model":
        contents.pop(0)

    # Detection : Prochain tirage → Tirage (T) → Grille (2) → Complexe (3) → Numero (1) → Text-to-SQL (fallback)
    enrichment_context = ""

    # Phase 0 : prochain tirage
    if _detect_prochain_tirage(payload.message):
        try:
            tirage_ctx = await asyncio.wait_for(asyncio.to_thread(_get_prochain_tirage), timeout=30.0)
            if tirage_ctx:
                enrichment_context = tirage_ctx
                logger.info("[HYBRIDE CHAT] Prochain tirage injecte")
        except Exception as e:
            logger.warning(f"[HYBRIDE CHAT] Erreur prochain tirage: {e}")

    # Phase T : resultats d'un tirage (dernier tirage, tirage d'hier, etc.)
    if not enrichment_context:
        tirage_target = _detect_tirage(payload.message)
        if tirage_target is not None:
            try:
                tirage_data = await asyncio.wait_for(
                    asyncio.to_thread(_get_tirage_data, tirage_target), timeout=30.0
                )
                if tirage_data:
                    enrichment_context = _format_tirage_context(tirage_data)
                    logger.info(f"[HYBRIDE CHAT] Tirage injecte: {tirage_data['date']}")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Erreur tirage: {e}")

    # Filtre temporel detecte → skip phases regex, Phase SQL gere
    force_sql = not enrichment_context and _has_temporal_filter(payload.message)
    if force_sql:
        logger.info("[HYBRIDE CHAT] Filtre temporel detecte, force Phase SQL")

    # Phase 2 : detection de grille (5 numeros)
    grille_nums, grille_chance = _detect_grille(payload.message)
    if not force_sql and grille_nums is not None:
        try:
            grille_result = await asyncio.wait_for(asyncio.to_thread(analyze_grille_for_chat, grille_nums, grille_chance), timeout=30.0)
            if grille_result:
                enrichment_context = _format_grille_context(grille_result)
                logger.info(f"[HYBRIDE CHAT] Grille analysee: {grille_nums} chance={grille_chance}")
        except Exception as e:
            logger.warning(f"[HYBRIDE CHAT] Erreur analyse grille: {e}")

    # Phase 3 : requete complexe (classement, comparaison, categorie)
    if not force_sql and not enrichment_context:
        intent = _detect_requete_complexe(payload.message)
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
                    enrichment_context = _format_complex_context(intent, data)
                    logger.info(f"[HYBRIDE CHAT] Requete complexe: {intent['type']}")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Erreur requete complexe: {e}")

    # Phase 1 : detection de numero simple
    if not force_sql and not enrichment_context:
        numero, type_num = _detect_numero(payload.message)
        if numero is not None:
            try:
                stats = await asyncio.wait_for(asyncio.to_thread(get_numero_stats, numero, type_num), timeout=30.0)
                if stats:
                    enrichment_context = _format_stats_context(stats)
                    logger.info(f"[HYBRIDE CHAT] Stats BDD injectees: numero={numero}, type={type_num}")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Erreur stats BDD (numero={numero}): {e}")

    # Phase SQL : Text-to-SQL fallback (Gemini genere le SQL quand aucune phase ne matche)
    if not enrichment_context:
        _sql_count = sum(1 for m in (payload.history or []) if m.role == "user")
        if _sql_count >= _MAX_SQL_PER_SESSION:
            logger.info(f"[TEXT2SQL] Rate-limit session ({_sql_count} echanges)")
        else:
            t0 = time.monotonic()
            try:
                sql_client = request.app.state.httpx_client
                sql = await asyncio.wait_for(
                    _generate_sql(payload.message, sql_client, gem_api_key, history=payload.history),
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
                            f'[TEXT2SQL] question="{payload.message[:80]}" | '
                            f'sql="{sql[:120]}" | status=OK | '
                            f'rows={len(rows)} | time={t_total}ms'
                        )
                    elif rows is not None:
                        enrichment_context = "[R\u00c9SULTAT SQL]\nAucun r\u00e9sultat trouv\u00e9 pour cette requ\u00eate."
                        logger.info(
                            f'[TEXT2SQL] question="{payload.message[:80]}" | '
                            f'sql="{sql[:120]}" | status=EMPTY | '
                            f'rows=0 | time={t_total}ms'
                        )
                    else:
                        enrichment_context = "[R\u00c9SULTAT SQL]\nAucun r\u00e9sultat trouv\u00e9 pour cette requ\u00eate."
                        logger.warning(
                            f'[TEXT2SQL] question="{payload.message[:80]}" | '
                            f'sql="{sql[:120]}" | status=EXEC_ERROR | '
                            f'time={t_total}ms'
                        )
                elif sql and sql.strip().upper() == "NO_SQL":
                    logger.info(
                        f'[TEXT2SQL] question="{payload.message[:80]}" | '
                        f'sql=NO_SQL | status=NO_SQL | '
                        f'time={int((time.monotonic() - t0) * 1000)}ms'
                    )
                elif sql:
                    logger.warning(
                        f'[TEXT2SQL] question="{payload.message[:80]}" | '
                        f'sql="{sql[:120]}" | status=REJECTED | '
                        f'time={int((time.monotonic() - t0) * 1000)}ms'
                    )
                else:
                    logger.warning(
                        f'[TEXT2SQL] question="{payload.message[:80]}" | '
                        f'status=GEN_ERROR | '
                        f'time={int((time.monotonic() - t0) * 1000)}ms'
                    )
            except asyncio.TimeoutError:
                logger.warning(
                    f'[TEXT2SQL] question="{payload.message[:80]}" | '
                    f'status=TIMEOUT | '
                    f'time={int((time.monotonic() - t0) * 1000)}ms'
                )
            except Exception as e:
                logger.warning(
                    f'[TEXT2SQL] question="{payload.message[:80]}" | '
                    f'status=ERROR | error="{e}" | '
                    f'time={int((time.monotonic() - t0) * 1000)}ms'
                )

    # Fallback regex quand Phase SQL echoue avec filtre temporel
    # (donnees globales, mieux que la reponse generique)
    if force_sql and not enrichment_context:
        logger.info("[HYBRIDE CHAT] Phase SQL echouee, fallback phases regex (donnees globales)")
        intent = _detect_requete_complexe(payload.message)
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
                    enrichment_context = _format_complex_context(intent, data)
                    logger.info(f"[HYBRIDE CHAT] Fallback Phase 3: {intent['type']}")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Fallback Phase 3 erreur: {e}")
        if not enrichment_context:
            numero, type_num = _detect_numero(payload.message)
            if numero is not None:
                try:
                    stats = await asyncio.wait_for(asyncio.to_thread(get_numero_stats, numero, type_num), timeout=30.0)
                    if stats:
                        enrichment_context = _format_stats_context(stats)
                        logger.info(f"[HYBRIDE CHAT] Fallback Phase 1: numero={numero}")
                except Exception as e:
                    logger.warning(f"[HYBRIDE CHAT] Fallback Phase 1 erreur: {e}")

    # DEBUG — tracer l'etat avant appel Gemini final (a retirer apres validation prod)
    logger.info(
        f"[DEBUG] force_sql={force_sql} | enrichment={bool(enrichment_context)} | "
        f"question=\"{payload.message[:60]}\" | history_len={len(payload.history or [])}"
    )

    # Message utilisateur avec contexte de page + donnees BDD
    if enrichment_context:
        user_text = f"[Page: {payload.page}]\n\n{enrichment_context}\n\n[Question utilisateur] {payload.message}"
    else:
        user_text = f"[Page: {payload.page}] {payload.message}"
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
                        # Injection sponsor post-Gemini (n'affecte pas l'historique)
                        sponsor_line = _get_sponsor_if_due(history)
                        if sponsor_line:
                            text += "\n\n" + sponsor_line
                        logger.info(
                            f"[HYBRIDE CHAT] OK (page={payload.page}, mode={mode})"
                        )
                        return HybrideChatResponse(
                            response=text, source="gemini", mode=mode
                        )

        logger.warning(
            f"[HYBRIDE CHAT] Reponse Gemini invalide: {response.status_code}"
        )
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )

    except CircuitOpenError:
        logger.warning("[HYBRIDE CHAT] Circuit breaker ouvert — fallback")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback_circuit", mode=mode
        )
    except httpx.TimeoutException:
        logger.warning("[HYBRIDE CHAT] Timeout Gemini (15s) — fallback")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )
    except Exception as e:
        logger.error(f"[HYBRIDE CHAT] Erreur Gemini: {e}")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )


# =========================
# PITCH GRILLES — Gemini
# =========================

@router.post("/api/pitch-grilles")
@limiter.limit("10/minute")
async def api_pitch_grilles(request: Request, payload: PitchGrillesRequest):
    """Genere des pitchs HYBRIDE personnalises pour chaque grille via Gemini."""

    # Validation
    if not payload.grilles or len(payload.grilles) > 5:
        return JSONResponse(status_code=400, content={
            "success": False, "data": None, "error": "Entre 1 et 5 grilles requises"
        })

    for i, g in enumerate(payload.grilles):
        if len(g.numeros) != 5:
            return JSONResponse(status_code=400, content={
                "success": False, "data": None, "error": f"Grille {i+1}: 5 num\u00e9ros requis"
            })
        if len(set(g.numeros)) != 5:
            return JSONResponse(status_code=400, content={
                "success": False, "data": None, "error": f"Grille {i+1}: num\u00e9ros doivent \u00eatre uniques"
            })
        if not all(1 <= n <= 49 for n in g.numeros):
            return JSONResponse(status_code=400, content={
                "success": False, "data": None, "error": f"Grille {i+1}: num\u00e9ros entre 1 et 49"
            })
        if g.chance is not None and not 1 <= g.chance <= 10:
            return JSONResponse(status_code=400, content={
                "success": False, "data": None, "error": f"Grille {i+1}: chance entre 1 et 10"
            })

    # Preparer le contexte stats
    grilles_data = [{"numeros": g.numeros, "chance": g.chance} for g in payload.grilles]

    try:
        context = await asyncio.wait_for(asyncio.to_thread(prepare_grilles_pitch_context, grilles_data), timeout=30.0)
    except asyncio.TimeoutError:
        logger.error("[PITCH] Timeout 30s contexte stats")
        return JSONResponse(status_code=503, content={
            "success": False, "data": None, "error": "Service temporairement indisponible"
        })
    except Exception as e:
        logger.warning(f"[PITCH] Erreur contexte stats: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur donn\u00e9es statistiques"
        })

    if not context:
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Impossible de pr\u00e9parer le contexte"
        })

    # Charger le prompt
    system_prompt = load_prompt("PITCH_GRILLE")
    if not system_prompt:
        logger.error("[PITCH] Prompt pitch introuvable")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Prompt pitch introuvable"
        })

    # Cle API
    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "API Gemini non configur\u00e9e"
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
            logger.warning(f"[PITCH] Gemini HTTP {response.status_code}")
            return JSONResponse(status_code=502, content={
                "success": False, "data": None, "error": f"Gemini erreur HTTP {response.status_code}"
            })

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return JSONResponse(status_code=502, content={
                "success": False, "data": None, "error": "Gemini: aucune r\u00e9ponse"
            })

        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        if not text:
            return JSONResponse(status_code=502, content={
                "success": False, "data": None, "error": "Gemini: r\u00e9ponse vide"
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
            logger.warning(f"[PITCH] JSON invalide: {text[:200]}")
            return JSONResponse(status_code=502, content={
                "success": False, "data": None, "error": "Gemini: JSON mal form\u00e9"
            })

        logger.info(f"[PITCH] OK \u2014 {len(pitchs)} pitchs g\u00e9n\u00e9r\u00e9s")
        return {"success": True, "data": {"pitchs": pitchs}, "error": None}

    except CircuitOpenError:
        logger.warning("[PITCH] Circuit breaker ouvert — fallback")
        return JSONResponse(status_code=503, content={
            "success": False, "data": None, "error": "Service Gemini temporairement indisponible"
        })
    except httpx.TimeoutException:
        logger.warning("[PITCH] Timeout Gemini (15s)")
        return JSONResponse(status_code=503, content={
            "success": False, "data": None, "error": "Timeout Gemini"
        })
    except Exception as e:
        logger.error(f"[PITCH] Erreur: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur interne du serveur"
        })
