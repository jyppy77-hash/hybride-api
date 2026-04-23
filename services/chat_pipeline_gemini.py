"""
Gemini interaction helpers for chat pipelines — F15 V83.

Extracted from chat_pipeline_shared.py to reduce cognitive complexity.
Contains: SSE formatting, chat logging, Gemini contents building,
non-streaming and streaming Gemini calls, pitch pipeline, JSON parsing.

Direction: chat_pipeline_shared.py imports FROM this module (not the reverse).

V131.A — Migration AI Studio httpx → Google Gen AI SDK (vertex AI target).
"""

import re
import json
import random
import asyncio
import logging
import time
from datetime import date

import httpx  # V131.A: conservé pour signature rétrocompat (ctx["_http_client"] typé)

from google.genai import errors as genai_errors, types

from services.circuit_breaker import gemini_breaker, CircuitOpenError
from services.gemini import stream_gemini_chat, _GEMINI_CHAT_TEMPERATURE
from services.gemini_shared import (
    _get_client,
    _is_rate_limit_error,
    _VERTEX_MODEL_NAME,
)
from services.gemini_cache import pitch_cache
from services.chat_utils import (
    _clean_response, _strip_non_latin, _get_sponsor_if_due,
    _strip_sponsor_from_text, StreamBuffer,
)
from services.base_chat_utils import _format_last_draw_context
from services.chat_logger import log_chat_exchange

logger = logging.getLogger(__name__)

_MAX_HISTORY_MESSAGES = 20

# Timeout constants are defined in chat_pipeline_shared.py and passed as parameters.

# V99 F05: Factual data tags — when present, lower temperature to reduce hallucination
_FACTUAL_TAGS = ("[RÉSULTAT SQL", "[RÉSULTAT TIRAGE", "[DONNÉES TEMPS RÉEL")
_TEMPERATURE_FACTUAL = 0.2
_TEMPERATURE_CONVERSATIONAL = _GEMINI_CHAT_TEMPERATURE  # 0.6
# V126 3/5 : température intermédiaire pour Phase 0 dont l'historique récent
# contient un keyword SQL-évocateur (ex: "historique complet ?"). Réduit la
# créativité hallucinante sur "oui" qui suit une proposition data-oriented.
_TEMPERATURE_PHASE0_SQL_EVOCATIVE = 0.4


def _history_has_sql_evocative_tail(history: list | None, lang: str) -> bool:
    """V126 3/5 : dernier message assistant contient-il un keyword SQL-évocateur ?

    Réutilise `_is_sql_continuation` V125 comme source unique de vérité.
    Retourne False sur history vide / aucun assistant / keyword absent.
    """
    if not history:
        return False
    from services.base_chat_detect_intent import _is_sql_continuation
    for msg in reversed(history):
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", None)
        if role is None and isinstance(msg, dict):
            role = msg.get("role")
            content = msg.get("content")
        if role == "assistant" and content:
            return _is_sql_continuation(content, lang)
    return False


def _get_temperature(ctx: dict) -> float:
    """Adaptive temperature.

    - V99 F05 : T=0.2 si contexte factuel (tag [RÉSULTAT SQL/TIRAGE/DONNÉES]).
    - V126 3/5 : T=0.4 si Phase 0 ET dernier assistant contient un keyword
      SQL-évocateur (historique / détail / liste complète…). Évite la
      génération créative d'un tirage inventé sur un "oui" enchaîné.
    - Sinon : T=0.6 conversationnel.
    """
    meta = ctx.get("_chat_meta") or {}
    enrichment = meta.get("enrichment_context", "")
    if any(tag in enrichment for tag in _FACTUAL_TAGS):
        return _TEMPERATURE_FACTUAL

    # V126 3/5 : Phase 0 + historique SQL-évocateur → T=0.4
    phase = meta.get("phase", "")
    if phase == "0":
        lang = meta.get("lang", "fr")
        if _history_has_sql_evocative_tail(ctx.get("history"), lang):
            return _TEMPERATURE_PHASE0_SQL_EVOCATIVE

    return _TEMPERATURE_CONVERSATIONAL

# V96+V99: Anti-hallucination — extract numbers from context and verify Gemini response
# V99 F03: broadened to match [RÉSULTAT TIRAGE] and [DONNÉES TEMPS RÉEL] in addition to [RÉSULTAT SQL]
_DATA_TAG_RE = re.compile(
    r'\[(?:RÉSULTAT SQL|RÉSULTAT TIRAGE|DONNÉES TEMPS RÉEL)[^\]]*\](.*?)(?:\[/(?:RÉSULTAT SQL|RÉSULTAT TIRAGE)\]|$)',
    re.DOTALL,
)

# V99 F08: detect draw-like number sequences in Gemini response (e.g. "12 - 14 - 22 - 31 - 44")
# V100 R04: extended to support multilang conjunctions (et/and/y/und/en/e)
_DRAW_SEP = r'(?:\s*[-–—,]\s*|\s+(?:et|and|y|und|en|e)\s+)'
_DRAW_SEQUENCE_RE = re.compile(
    rf'(\d{{1,2}}){_DRAW_SEP}(\d{{1,2}}){_DRAW_SEP}(\d{{1,2}}){_DRAW_SEP}(\d{{1,2}}){_DRAW_SEP}(\d{{1,2}})',
)


_STRICT_HALLUCINATION_MESSAGES = {
    "fr": "Voici les données exactes issues de notre base :\n\n{data}",
    "en": "Here are the exact data from our database:\n\n{data}",
    "es": "Aquí están los datos exactos de nuestra base de datos:\n\n{data}",
    "pt": "Aqui estão os dados exatos da nossa base de dados:\n\n{data}",
    "de": "Hier sind die genauen Daten aus unserer Datenbank:\n\n{data}",
    "nl": "Hier zijn de exacte gegevens uit onze database:\n\n{data}",
}


def _extract_last_factual_context(history: list | None) -> str | None:
    """V125 A2: récupère le dernier message assistant SI contient un tag factuel.

    Utilisé pour activer un check transitif hallucination sur Phase 0 (continuation)
    quand l'historique récent contient encore [RÉSULTAT TIRAGE], [RÉSULTAT SQL]
    ou [DONNÉES TEMPS RÉEL]. Retourne None si aucun tag factuel.
    """
    if not history:
        return None
    for msg in reversed(history):
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", None)
        if role is None and isinstance(msg, dict):
            role = msg.get("role")
            content = msg.get("content")
        if role == "assistant" and content:
            if _DATA_TAG_RE.search(content):
                return content
            return None
    return None


def _check_sql_number_hallucination(
    enrichment_context: str, gemini_response: str, phase: str, log_prefix: str,
    lang: str = "fr", history: list | None = None,
) -> str | None:
    """Check Gemini response for hallucinated draw numbers.

    Returns None when the response is OK, or a safe replacement message
    when invented numbers are detected (V101 strict mode).

    V99 F03: HALLUCINATION_RISK (missing numbers) → log-only, returns None.
    V99 F08: HALLUCINATION_INVENTED (invented numbers) → log + returns safe
    replacement message containing the real data from enrichment context.
    V125 A2: scope Phase 0 transitif — check activé si l'historique récent
    contient un tag factuel (défense contre fuite résiduelle via history).
    V125 A3: détection orpheline inconditionnelle — log warning si séquence
    5-nums draw-like apparaît dans réponse sans aucun contexte factuel.
    """
    # V125 A3: orphan sequence detection (inconditional, log-only, any phase)
    if gemini_response:
        _seq_orphan = _DRAW_SEQUENCE_RE.search(gemini_response)
        if _seq_orphan and not _DATA_TAG_RE.search(enrichment_context or ""):
            logger.warning(
                "HALLUCINATION_ORPHAN_SEQUENCE: %s sequence '%s' in response "
                "but NO factual context tag. Phase=%s | excerpt=%.200s",
                log_prefix, _seq_orphan.group(0), phase, gemini_response[:200],
            )

    # V125 A2: Phase 0 transitif — active check si historique récent factuel
    if phase == "0":
        transitive = _extract_last_factual_context(history)
        if not transitive:
            return None
        enrichment_context = transitive
    elif phase not in ("1", "T", "SQL"):
        return None
    m = _DATA_TAG_RE.search(enrichment_context or "")
    if not m:
        return None
    data_body = m.group(1)
    if "aucun résultat" in data_body.lower():
        return None
    context_numbers = set(re.findall(r'\b(\d{1,2})\b', data_body))
    if not context_numbers:
        return None
    response_numbers = set(re.findall(r'\b(\d{1,2})\b', gemini_response))
    # Check 1: numbers from context missing in response — log-only (incomplete ≠ false)
    missing = context_numbers - response_numbers
    if missing:
        logger.warning(
            "HALLUCINATION_RISK: %s context numbers %s missing from Gemini response. "
            "Phase=%s | data_excerpt=%.200s",
            log_prefix, sorted(missing, key=int), phase, data_body.strip(),
        )
    # V99 F08 + V101 strict: invented numbers in draw-like sequences → BLOCK
    seq_match = _DRAW_SEQUENCE_RE.search(gemini_response)
    if seq_match:
        seq_nums = set(seq_match.groups())
        invented = seq_nums - context_numbers
        if invented:
            logger.warning(
                "HALLUCINATION_INVENTED: %s numbers %s in response draw sequence "
                "but ABSENT from context. Phase=%s | sequence=%s",
                log_prefix, sorted(invented, key=int), phase,
                seq_match.group(0),
            )
            # V101: strict mode — return safe replacement with real data
            tpl = _STRICT_HALLUCINATION_MESSAGES.get(lang, _STRICT_HALLUCINATION_MESSAGES["fr"])
            return tpl.format(data=data_body.strip())
    return None
# This module does NOT import from shared (avoids circular dependency).


# ═══════════════════════════════════════════════════════
# V126 4/5 — DB schema whitelist + hallucinated identifier guard (option 4-Y)
# ═══════════════════════════════════════════════════════

# A2 — Fallback cache statique (colonnes réelles lues dans code V124 +
# migrations/add_indexes.sql + services/chat_sql.py + chat_sql_em.py).
# Utilisé si `_build_schema_whitelist` ne peut pas DESCRIBE la DB au boot
# (DB down, rolling upgrade…). Le service démarre quand même, logger.error
# signale l'usage du fallback. Test CI `test_fallback_matches_current_schema`
# compare cette liste à la vraie DB pour détecter un drift silencieux.
_SCHEMA_WHITELIST_FALLBACK: frozenset[str] = frozenset({
    # Loto `tirages`
    "id", "date_de_tirage", "jour_de_tirage",
    "boule_1", "boule_2", "boule_3", "boule_4", "boule_5",
    "numero_chance",
    "nombre_de_gagnant_au_rang1", "rapport_du_rang1",
    "created_at",
    # EM `tirages_euromillions`
    "etoile_1", "etoile_2",
})

# Whitelist globale populée au boot via DESCRIBE. Vide jusqu'à _build_schema_whitelist.
_SCHEMA_WHITELIST: set[str] = set()

# A1 — Regex resserrée : UNIQUEMENT pattern `lettres_chiffres` pur d'ID SQL.
# La variante `[a-z]+_[a-z]+` a été retirée car elle match du français naturel
# avec underscore (ex: `base_de_donnees`). Le pattern conservé (`boule_N`,
# `num_5`, etc.) est discriminant.
_SUSPICIOUS_IDENT_RE = re.compile(r'\b[a-z]{3,}_\d{1,2}\b')

# A1 — Liste noire explicite : hallucinations récurrentes NON-captées par la
# regex (car pas de chiffre suffixé). CC Max peut l'étendre selon patterns réels.
_KNOWN_HALLUCINATED_IDENTIFIERS: frozenset[str] = frozenset({
    "num_chance",       # vrai : numero_chance
    "date_tirage",      # vrai : date_de_tirage
    "draw_date",        # EN inventé
    "lucky_num",        # invention pure
    "ball_id",          # invention pure
    "star_id",          # EN inventé (vrai : etoile_1, etoile_2)
    "draw_id",          # EN inventé
    "number_chance",    # pseudo-anglais
    "chance_number",    # pseudo-anglais
})


async def _build_schema_whitelist() -> set[str]:
    """V126 4/5 (option Y) : construit la whitelist schéma DB au boot.

    DESCRIBE `tirages` + `tirages_euromillions` → populate `_SCHEMA_WHITELIST`.
    Fallback sur `_SCHEMA_WHITELIST_FALLBACK` si DB down (logger.error).

    Appelée depuis `main.py::lifespan` après init_pool_readonly.
    """
    global _SCHEMA_WHITELIST
    columns: set[str] = set()
    try:
        import db_cloudsql
        async with db_cloudsql.get_connection_readonly() as conn:
            cursor = await conn.cursor()
            for table in ("tirages", "tirages_euromillions"):
                try:
                    await cursor.execute(f"DESCRIBE {table}")
                    rows = await cursor.fetchall()
                    for r in rows:
                        col = r.get("Field") if isinstance(r, dict) else (r[0] if r else None)
                        if col:
                            columns.add(col.lower())
                except Exception as _e:
                    logger.warning(
                        "V126 4/5 DESCRIBE %s failed: %s — continuing",
                        table, _e,
                    )
        if columns:
            _SCHEMA_WHITELIST = columns
            logger.info(
                "V126 4/5 schema whitelist built from DB: %d columns (%s)",
                len(columns), sorted(columns)[:10],
            )
            return columns
    except Exception as e:
        logger.error(
            "V126 4/5 DESCRIBE failed entirely, falling back to static list: %s",
            e,
        )
    _SCHEMA_WHITELIST = set(_SCHEMA_WHITELIST_FALLBACK)
    logger.info(
        "V126 4/5 schema whitelist using STATIC FALLBACK: %d columns",
        len(_SCHEMA_WHITELIST),
    )
    return _SCHEMA_WHITELIST


def _check_sql_schema_hallucination(
    response: str, log_prefix: str, lang: str = "fr",
) -> str | None:
    """V126 4/5 : détecte des identifiants DB-like hallucinés dans la réponse.

    Deux couches combinées :
      - regex `_SUSPICIOUS_IDENT_RE` (lettres_chiffres) → ex `num_1`, `ball_5`
      - liste noire `_KNOWN_HALLUCINATED_IDENTIFIERS` pour patterns sans chiffre

    Tokens flagged = suspects non présents dans `_SCHEMA_WHITELIST`.
    Retourne un message safe si ≥ 1 suspect, None sinon.

    Garde-fou : si `_SCHEMA_WHITELIST` vide (boot DESCRIBE pas encore exécuté,
    ex. en tests sans startup), retourne None — évite FP sur init incomplète.
    """
    if not response or not _SCHEMA_WHITELIST:
        return None
    response_lower = response.lower()
    suspects: list[str] = []
    # Regex scan
    for match in _SUSPICIOUS_IDENT_RE.finditer(response_lower):
        tok = match.group(0)
        if tok not in _SCHEMA_WHITELIST:
            suspects.append(tok)
    # Liste noire
    for known in _KNOWN_HALLUCINATED_IDENTIFIERS:
        if known not in _SCHEMA_WHITELIST and re.search(
            r'\b' + re.escape(known) + r'\b', response_lower,
        ):
            if known not in suspects:
                suspects.append(known)
    if not suspects:
        return None
    logger.warning(
        "%s V126 4/5 SCHEMA_HALLUCINATION_DETECTED: %s | excerpt=%.200s",
        log_prefix, suspects[:5], response[:200],
    )
    return _STRICT_HALLUCINATION_MESSAGES.get(
        lang, _STRICT_HALLUCINATION_MESSAGES["fr"],
    ).format(data="(détails techniques retirés — reformule ta question sans jargon SQL)")


# ═══════════════════════════════════════════════════════
# V126 3.5-A — Phase 0 draw-date post-hoc verification (option A stricte)
# ═══════════════════════════════════════════════════════

# Multi-lang month names → number map. Couvre FR/EN/ES/PT/DE/NL + abrévs EN.
# Construit via boucle pour lisibilité — résultat : dict statique.
_MONTH_NAME_TO_NUM: dict[str, int] = {}
for _names, _n in (
    # FR
    (("janvier",), 1), (("février", "fevrier"), 2), (("mars",), 3),
    (("avril",), 4), (("mai",), 5), (("juin",), 6), (("juillet",), 7),
    (("août", "aout"), 8), (("septembre",), 9), (("octobre",), 10),
    (("novembre",), 11), (("décembre", "decembre"), 12),
    # EN (short forms included for "Jan 28, 2026" style)
    (("january", "jan"), 1), (("february", "feb"), 2), (("march", "mar"), 3),
    (("april", "apr"), 4), (("june", "jun"), 6), (("july", "jul"), 7),
    (("august", "aug"), 8), (("september", "sep", "sept"), 9),
    (("october", "oct"), 10), (("november", "nov"), 11),
    (("december", "dec"), 12),
    # ES (duplicates with FR/EN ignored by dict update)
    (("enero",), 1), (("febrero",), 2), (("marzo",), 3),
    (("mayo",), 5), (("agosto",), 8), (("septiembre", "setiembre"), 9),
    (("octubre",), 10), (("noviembre",), 11), (("diciembre",), 12),
    # PT
    (("janeiro",), 1), (("fevereiro",), 2), (("março", "marco"), 3),
    (("maio",), 5), (("junho",), 6), (("julho",), 7),
    (("setembro",), 9), (("outubro",), 10), (("dezembro",), 12),
    # DE
    (("januar",), 1), (("februar",), 2), (("märz", "maerz"), 3),
    (("oktober",), 10), (("dezember",), 12),
    # NL
    (("januari",), 1), (("februari",), 2), (("maart",), 3),
    (("mei",), 5), (("augustus",), 8),
):
    for _name in _names:
        _MONTH_NAME_TO_NUM.setdefault(_name, _n)

# Pattern union sorted longest-first to avoid partial matches (ex: "jan" before "january")
_MONTH_RE = "(?:" + "|".join(
    sorted(set(_MONTH_NAME_TO_NUM), key=len, reverse=True)
) + ")"

# Pattern D Month YYYY (FR/EN/DE/NL/PT/ES with optional "de") — the common form.
# V126.1 F1-bis : `\.?` ajouté après le jour pour accepter le format allemand
# `12. Dezember 2025` (point ordinal). Rétrocompat V126 `12 Dezember 2025` OK.
_DATE_RE_DMY = re.compile(
    rf"\b(\d{{1,2}})\.?\s*(?:de\s+)?({_MONTH_RE})\s+(?:de\s+)?(\d{{4}})\b",
    re.IGNORECASE,
)
# Pattern Month D, YYYY (EN US style)
_DATE_RE_MDY = re.compile(
    rf"\b({_MONTH_RE})\s+(\d{{1,2}}),?\s+(\d{{4}})\b",
    re.IGNORECASE,
)
# Pattern ISO YYYY-MM-DD — universal, tried first
_DATE_RE_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")

# V126.1 F3 — Extraction des 2 étoiles EM (6 langs + Unicode ★/☆/⭐).
# Formats observés prod / prompts Gemini :
#   FR : "étoiles 3 et 8", "étoile 3, étoile 8", "3 et 8 étoiles"
#   EN : "stars: 3 - 8", "stars 3 and 8", "star 3, star 8"
#   ES : "estrellas 3 y 8"     PT : "estrelas 3 e 8"
#   DE : "Sterne 3 und 8"      NL : "sterren 3 en 8"
# Le mot-clé étoile peut être répété entre les 2 chiffres ("star 3, star 8").
_STAR_WORDS = r'(?:[ée]toiles?|stars?|estrellas?|estrelas?|sterne?n?|sterren|[★☆⭐])'
_EM_STARS_RE = re.compile(
    _STAR_WORDS + r'\s*[:\-]?\s*(\d{1,2})\s*[-–—,]?\s*'
    r'(?:(?:et|and|y|e|und|en)\s+)?'
    + _STAR_WORDS + r'?\s*(\d{1,2})',
    re.IGNORECASE,
)


def _parse_draw_date_multilang(text: str) -> date | None:
    """V126 3.5-A : parse une date dans la réponse (6 langues + ISO).
    Retourne un objet `date` ou None si aucun pattern ne match.

    Ordre de tentative : ISO > D Month YYYY > Month D, YYYY.
    Les erreurs ValueError (jour invalide) sont silencieuses → None.
    """
    m = _DATE_RE_ISO.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = _DATE_RE_DMY.search(text)
    if m:
        try:
            day = int(m.group(1))
            month = _MONTH_NAME_TO_NUM[m.group(2).lower()]
            year = int(m.group(3))
            return date(year, month, day)
        except (ValueError, KeyError):
            pass
    m = _DATE_RE_MDY.search(text)
    if m:
        try:
            month = _MONTH_NAME_TO_NUM[m.group(1).lower()]
            day = int(m.group(2))
            year = int(m.group(3))
            return date(year, month, day)
        except (ValueError, KeyError):
            pass
    return None


async def _recheck_phase0_draw_accuracy(
    response: str, phase: str, lang: str, log_prefix: str,
    get_tirage_fn,
    game: str = "loto",
) -> str | None:
    """V126 3.5-A + V126.1 F3 : Phase 0 post-hoc — si la réponse Gemini cite
    un tirage (date + séquence 5-numéros), vérifier que les numéros
    correspondent au vrai tirage en base.

    V126.1 F3 : si `game == "em"` et le tirage a des étoiles, extraire aussi
    les 2 étoiles citées dans la réponse via `_EM_STARS_RE` et les comparer
    au vrai tirage. Mismatch sur boules OU étoiles → replacement.

    Args:
        response: texte Gemini post-clean
        phase: phase détectée ("0" requis sinon early return)
        lang: code langue 6 langs (fr/en/es/pt/de/nl)
        log_prefix: préfixe pour warnings
        get_tirage_fn: async (date) -> dict|None game-specific
        game: "loto" (défaut rétrocompat V126) ou "em"

    Returns :
      - message safe (str) si mismatch détecté → utiliser côté non-stream
        pour remplacer la réponse. Sur stream : log-only (stream déjà émis).
      - None si phase != "0", pas de séquence, pas de date, ou numéros OK.

    Budget DB : 1 appel `get_tirage_fn(date)` avec timeout 3s. Échec DB
    (timeout/erreur) → warning + return None, ne bloque jamais.
    """
    if phase != "0" or not response:
        return None
    if not get_tirage_fn:
        return None
    seq_match = _DRAW_SEQUENCE_RE.search(response)
    if not seq_match:
        return None
    parsed_date = _parse_draw_date_multilang(response)
    if not parsed_date:
        return None
    # V127 — timeout réduit 3s → 1s (audit V126.1 décision 4 Option C).
    # Garde le bloquant pour préserver la défense anti-hallucination V126,
    # mais limite l'impact latence non-streaming à +1s pire cas (vs +3s avant).
    # DB readonly p95 < 100ms en charge normale → 0 dégradation observable.
    try:
        tirage = await asyncio.wait_for(get_tirage_fn(parsed_date), timeout=1.0)
    except asyncio.TimeoutError:
        logger.warning(
            "%s V127 reapply TIMEOUT (1s) on DB lookup for %s — log-only fallback",
            log_prefix, parsed_date,
        )
        return None
    except Exception as e:
        logger.warning(
            "%s V126 3.5-A reapply DB lookup error for %s: %s",
            log_prefix, parsed_date, e,
        )
        return None
    if not tirage:
        logger.warning(
            "%s V126 3.5-A PHASE0_DATE_NOT_IN_DB: date=%s cited but absent | "
            "cited_seq=%s",
            log_prefix, parsed_date, seq_match.group(0),
        )
        return _STRICT_HALLUCINATION_MESSAGES.get(
            lang, _STRICT_HALLUCINATION_MESSAGES["fr"],
        ).format(data=f"(aucune donnée disponible pour le {parsed_date})")
    real_nums = set(str(n) for n in tirage["boules"])
    cited_nums = set(seq_match.groups())
    boules_mismatch = cited_nums != real_nums

    # V126.1 F3 : check étoiles EM (5 boules correctes mais étoiles fausses
    # possible → défense-en-profondeur).
    stars_mismatch = False
    cited_stars: set[str] = set()
    real_stars: set[str] = set()
    if game == "em" and tirage.get("etoiles"):
        stars_match = _EM_STARS_RE.search(response)
        if stars_match:
            cited_stars = {stars_match.group(1), stars_match.group(2)}
            real_stars = {str(s) for s in tirage["etoiles"]}
            if cited_stars != real_stars:
                stars_mismatch = True

    if boules_mismatch or stars_mismatch:
        logger.warning(
            "%s V126.1 PHASE0_DRAW_MISMATCH: date=%s boules_real=%s boules_cited=%s "
            "stars_mismatch=%s stars_real=%s stars_cited=%s",
            log_prefix, parsed_date,
            sorted(real_nums, key=int),
            sorted(cited_nums, key=int),
            stars_mismatch,
            sorted(real_stars, key=int) if real_stars else [],
            sorted(cited_stars, key=int) if cited_stars else [],
        )
        safe_data = _format_last_draw_context(tirage)
        return _STRICT_HALLUCINATION_MESSAGES.get(
            lang, _STRICT_HALLUCINATION_MESSAGES["fr"],
        ).format(data=safe_data)
    return None


# ═══════════════════════════════════════════════════════
# SSE event formatter
# ═══════════════════════════════════════════════════════

def sse_event(data: dict) -> str:
    """Format dict as SSE event line: data: {...}\\n\\n"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ═══════════════════════════════════════════════════════
# Chat logger wrapper
# ═══════════════════════════════════════════════════════

def log_from_meta(meta, module, lang, message, response_preview="",
                  is_error=False, error_detail=None):
    """Call log_chat_exchange from _chat_meta dict."""
    if not meta:
        return
    log_chat_exchange(
        module=module, lang=meta.get("lang", lang), question=message,
        response_preview=response_preview,
        phase_detected=meta.get("phase", "unknown"),
        sql_generated=meta.get("sql_query"),
        sql_status=meta.get("sql_status", "N/A"),
        duration_ms=int((time.monotonic() - meta["t0"]) * 1000),
        grid_count=meta.get("grid_count", 0),
        has_exclusions=meta.get("has_exclusions", False),
        is_error=is_error, error_detail=error_detail,
    )


# ═══════════════════════════════════════════════════════
# History processing — build Gemini contents array
# ═══════════════════════════════════════════════════════

def build_gemini_contents(history, message, detect_insulte_fn):
    """
    Process chat history into Gemini contents array.
    Strips insult exchanges, maps roles, deduplicates consecutive same-role messages.
    Returns the processed contents list and the (possibly trimmed) history.
    """
    history = history or []
    if len(history) > _MAX_HISTORY_MESSAGES:
        logger.info("Gemini history truncated: %d → %d messages", len(history), _MAX_HISTORY_MESSAGES)
        history = history[-_MAX_HISTORY_MESSAGES:]
    if history and history[-1].role == "user" and history[-1].content == message:
        history = history[:-1]

    contents = []
    _skip_insult_response = False
    for msg in history:
        if msg.role == "user" and detect_insulte_fn(msg.content):
            _skip_insult_response = True
            continue
        if msg.role == "assistant" and _skip_insult_response:
            _skip_insult_response = False
            continue
        _skip_insult_response = False

        role = "user" if msg.role == "user" else "model"
        content = _strip_sponsor_from_text(msg.content) if role == "model" else msg.content
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n" + content
        else:
            contents.append({"role": role, "parts": [{"text": content}]})

    while contents and contents[0]["role"] == "model":
        contents.pop(0)

    return contents, history


# ═══════════════════════════════════════════════════════
# handle_chat — Gemini call + response extraction
# ═══════════════════════════════════════════════════════

async def call_gemini_and_respond(ctx, fallback, log_prefix, module, lang,
                                  message, page, sponsor_kwargs=None,
                                  breaker=None):
    """
    Gemini non-streaming call: send contents, extract text, handle errors.
    breaker: circuit breaker instance (pass module-level ref for test compat).
    Returns response dict.

    V131.A — Migration AI Studio httpx → google-genai SDK. ADC auth (pas de key).
    Try/except inline remplace _gemini_call_with_fallback (supprimé V131.A).
    """
    mode = ctx["mode"]
    _breaker = breaker or gemini_breaker

    def _fallback_dict(error_type):
        detail = {"circuit_open": "CircuitOpen", "timeout": "Timeout"}.get(error_type, error_type)
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail=detail)
        source = "fallback_circuit" if error_type == "circuit_open" else "fallback"
        return {"response": fallback, "source": source, "mode": mode}

    # V131.A — breaker state check avant appel (ex-_breaker.call wrappait httpx.post)
    if _breaker.state == _breaker.OPEN:
        logger.warning(f"{log_prefix} Circuit breaker ouvert — fallback")
        return _fallback_dict("circuit_open")

    timeout = ctx.get("_timeout_gemini_chat", 10)  # V129.1: default 15→10
    config = types.GenerateContentConfig(
        system_instruction=ctx["system_prompt"],
        temperature=_get_temperature(ctx),
        max_output_tokens=300,
    )

    try:
        client = _get_client()
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=_VERTEX_MODEL_NAME,
                contents=ctx["contents"],
                config=config,
            ),
            timeout=timeout,
        )
    except CircuitOpenError:
        return _fallback_dict("circuit_open")
    except asyncio.TimeoutError:
        logger.warning(f"{log_prefix} Timeout Gemini Vertex ({timeout}s) — fallback")
        _breaker._record_failure()
        return _fallback_dict("timeout")
    except genai_errors.ClientError as e:
        if _is_rate_limit_error(e):
            logger.warning(f"{log_prefix} Vertex 429 ResourceExhausted — fallback")
        else:
            logger.warning(f"{log_prefix} Vertex ClientError {getattr(e, 'code', '?')}: {e}")
        _breaker._record_failure()
        return _fallback_dict("error")
    except genai_errors.ServerError as e:
        logger.warning(f"{log_prefix} Vertex ServerError {getattr(e, 'code', '?')}: {e}")
        _breaker._record_failure()
        return _fallback_dict("error")
    except genai_errors.APIError as e:
        logger.error(f"{log_prefix} Vertex APIError SDK: {type(e).__name__}: {e}")
        _breaker._record_failure()
        return _fallback_dict("error")
    except Exception as e:
        logger.error(f"{log_prefix} Exception inattendue Vertex: {type(e).__name__}: {e}")
        return _fallback_dict("error")

    # Parse réponse SDK B
    try:
        text = (response.text or "").strip()
    except (ValueError, AttributeError):
        # SAFETY/RECITATION block : .text lève ValueError
        # SAFETY = pas un vrai succès métier, PAS de record_success
        logger.warning(f"{log_prefix} Vertex response blocked (SAFETY/RECITATION) — fallback")
        return _fallback_dict("error")

    # V131.A FIX — record_success dès que round-trip OK (indépendant contenu).
    # Correction Jyppy CC Max : un round-trip réussi n'est pas une failure
    # infrastructure si le contenu est vide. Sémantique préservée vs AVANT.
    _breaker._record_success()

    if not text:
        logger.warning(f"{log_prefix} Reponse Gemini vide — fallback")
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail="EmptyResponse")
        return {"response": fallback, "source": "fallback", "mode": mode}

    text = _clean_response(text)
    if ctx["insult_prefix"]:
        text = ctx["insult_prefix"] + "\n\n" + text
    s_kwargs = sponsor_kwargs or {}
    sponsor_line = _get_sponsor_if_due(ctx["history"], **s_kwargs)
    if sponsor_line:
        text += "\n\n" + sponsor_line
    logger.info(f"{log_prefix} OK (page={page}, mode={mode})")
    log_from_meta(ctx.get("_chat_meta"), module, lang, message, text)

    # V100 R01 + V101 strict + V125 A2/A3: Anti-hallucination check
    _meta = ctx.get("_chat_meta") or {}
    _safe_replacement = _check_sql_number_hallucination(
        _meta.get("enrichment_context", ""), text,
        _meta.get("phase", ""), log_prefix,
        lang=_meta.get("lang", lang),
        history=ctx.get("history"),
    )
    if _safe_replacement:
        text = _safe_replacement
    # V126 3.5-A + V126.1 F3: Phase 0 post-hoc draw-date verification
    # (remplacement effectif sur path non-streaming, étoiles EM si game=em)
    _phase0_replace = await _recheck_phase0_draw_accuracy(
        text, _meta.get("phase", ""),
        _meta.get("lang", lang), log_prefix,
        get_tirage_fn=ctx.get("_get_tirage_fn"),
        game=ctx.get("_game", "loto"),
    )
    if _phase0_replace:
        text = _phase0_replace
    # V126 4/5: Schema hallucination check — remplacement non-stream
    _schema_replace = _check_sql_schema_hallucination(
        text, log_prefix, lang=_meta.get("lang", lang),
    )
    if _schema_replace:
        text = _schema_replace
    return {"response": text, "source": "gemini", "mode": mode}


# ═══════════════════════════════════════════════════════
# handle_chat_stream — SSE streaming loop
# ═══════════════════════════════════════════════════════

async def stream_and_respond(ctx, fallback, log_prefix, module, lang,
                             message, page, call_type, sponsor_kwargs=None,
                             stream_fn=None):
    """
    Async generator — SSE streaming loop with fallback handling.
    stream_fn: streaming function (pass module-level ref for test compat).
    Yields SSE event strings.
    """
    mode = ctx["mode"]
    _stream_chunks = []
    _stream = stream_fn or stream_gemini_chat

    try:
        if ctx["insult_prefix"]:
            yield sse_event({
                "chunk": ctx["insult_prefix"] + "\n\n",
                "source": "gemini", "mode": mode, "is_done": False,
            })

        has_chunks = False
        _buf = StreamBuffer()
        async for chunk in _stream(
            ctx["_http_client"], ctx["gem_api_key"], ctx["system_prompt"],
            ctx["contents"], timeout=ctx.get("_timeout_gemini_stream", 10),  # V129.1
            call_type=call_type, lang=lang,
            temperature=_get_temperature(ctx),
        ):
            safe = _buf.add_chunk(chunk)
            if not safe:
                continue
            has_chunks = True
            _stream_chunks.append(safe)
            yield sse_event({
                "chunk": safe, "source": "gemini", "mode": mode, "is_done": False,
            })

        _remaining = _buf.flush()
        if _remaining:
            has_chunks = True
            _stream_chunks.append(_remaining)
            yield sse_event({
                "chunk": _remaining, "source": "gemini", "mode": mode, "is_done": False,
            })

        if not has_chunks:
            log_from_meta(ctx.get("_chat_meta"), module, lang, message, fallback, is_error=True, error_detail="NoChunks")
            yield sse_event({
                "chunk": fallback,
                "source": "fallback", "mode": mode, "is_done": True,
            })
            return

        s_kwargs = sponsor_kwargs or {}
        sponsor_line = _get_sponsor_if_due(ctx["history"], **s_kwargs)
        if sponsor_line:
            yield sse_event({
                "chunk": "\n\n" + sponsor_line,
                "source": "gemini", "mode": mode, "is_done": False,
            })

        yield sse_event({
            "chunk": "", "source": "gemini", "mode": mode, "is_done": True,
        })
        _full_response = "".join(_stream_chunks)
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, _full_response)
        # V96+V101+V125 A2/A3: Anti-hallucination check — log-only on streaming path
        # (stream already sent to client, cannot be replaced)
        _meta = ctx.get("_chat_meta") or {}
        _check_sql_number_hallucination(
            _meta.get("enrichment_context", ""), _full_response,
            _meta.get("phase", ""), log_prefix,
            lang=_meta.get("lang", lang),
            history=ctx.get("history"),
        )
        # V126 3.5-A + V126.1 F3: Phase 0 post-hoc draw-date verification —
        # LOG-ONLY on stream (stream déjà émis, cannot replace).
        try:
            await _recheck_phase0_draw_accuracy(
                _full_response, _meta.get("phase", ""),
                _meta.get("lang", lang), log_prefix,
                get_tirage_fn=ctx.get("_get_tirage_fn"),
                game=ctx.get("_game", "loto"),
            )
        except Exception as _e:
            logger.warning("%s V126 3.5-A stream recheck failed: %s", log_prefix, _e)
        # V126 4/5: Schema hallucination check — LOG-ONLY sur stream (déjà émis)
        _check_sql_schema_hallucination(
            _full_response, log_prefix, lang=_meta.get("lang", lang),
        )
        logger.info(f"{log_prefix} Stream OK (page={page}, mode={mode})")

    except CircuitOpenError:
        logger.warning(f"{log_prefix} Circuit breaker ouvert — fallback")
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail="CircuitOpen")
        yield sse_event({
            "chunk": fallback,
            "source": "fallback_circuit", "mode": mode, "is_done": True,
        })
    except (asyncio.TimeoutError, httpx.TimeoutException):
        # V131.A : stream_gemini_chat lève asyncio.TimeoutError (ex-httpx.TimeoutException).
        # Catch les 2 pour defense-in-depth (httpx conservé si re-régression future).
        logger.warning(f"{log_prefix} Timeout Gemini (stream) — fallback")
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail="Timeout")
        yield sse_event({
            "chunk": fallback,
            "source": "fallback", "mode": mode, "is_done": True,
        })
    except Exception as e:
        logger.error(f"{log_prefix} Erreur streaming: {e}")
        log_from_meta(ctx.get("_chat_meta"), module, lang, message, is_error=True, error_detail=str(e)[:255])
        yield sse_event({
            "chunk": fallback,
            "source": "fallback", "mode": mode, "is_done": True,
        })


# ═══════════════════════════════════════════════════════
# Pitch JSON parsing
# ═══════════════════════════════════════════════════════

def parse_pitch_json(text):
    """
    Clean backticks and parse pitch JSON from Gemini.
    Returns (pitchs_list, error_dict_or_None).
    """
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

    try:
        result = json.loads(clean)
        pitchs = result.get("pitchs", [])
    except (json.JSONDecodeError, AttributeError):
        return None, {
            "success": False, "data": None,
            "error": "Gemini: JSON mal formé",
            "status_code": 502,
        }

    pitchs = [_strip_non_latin(p) if isinstance(p, str) else p for p in pitchs]
    return pitchs, None


# ═══════════════════════════════════════════════════════
# handle_pitch — common pipeline
# ═══════════════════════════════════════════════════════

# V131.A — Retry calibration préservée V129.1 (réimplémentée inline car
# circuit_breaker.call(max_retries) applicable uniquement sur httpx.post).
_V129_PITCH_RETRY_BACKOFF_BASE = 2.0   # seconds (V129.1)
_V129_PITCH_RETRY_CAP_TOTAL = 14.0     # seconds (V129.1)
_V129_PITCH_RETRY_JITTER_MAX = 1.0     # seconds (V129.1 equal jitter)


async def handle_pitch_common(grilles_data, http_client, lang,
                              context_coro,
                              load_prompt_fn, prompt_name,
                              log_prefix, breaker=None,
                              timeout_context=30,
                              # V131.A.3 — default 10s conservé (test_v129_1_calibration.py:181).
                              # Call sites pitch DOIVENT override à 45s (V131.A.2 max_output_tokens=8000
                              # dépasse 10s avec gemini-2.5-flash → timeout Vertex → 503).
                              # Cf. docs/DIAGNOSTIC_V131_A_2_503_PITCH.md
                              timeout_gemini=10,  # V129.1: 15→10
                              max_retries: int = 0):
    """
    Common pitch pipeline after validation.
    context_coro: awaitable that returns the stats context string.
    Calls context_coro → load_prompt → Gemini Vertex → parse JSON.
    Returns result dict.

    V127 — Cache hit short-circuit : si grilles_data + lang + prompt_name déjà
    vus dans les 24h, retourne le payload caché (skip context_coro + Gemini).
    Marqué `from_cache: True` pour observabilité admin/tests. Ne cache QUE
    les succès.

    V131.A — Migration google-genai SDK + retry V129.1 inline (2/4/8s +
    jitter [0,1s] + cap total 14s + CB check per-iter), remplace
    circuit_breaker.call(max_retries). Le paramètre `http_client` est ignoré
    (ADC auth).
    """
    _ = http_client  # noqa: F841  # V131.A DEPRECATED — paramètre ignoré (signature rétrocompat)

    # V127 — Cache hit short-circuit
    _cached = pitch_cache.get(grilles_data, lang, prompt_name)
    if _cached:
        return {**_cached, "from_cache": True}

    try:
        context = await asyncio.wait_for(context_coro, timeout=timeout_context)
    except asyncio.TimeoutError:
        logger.error(f"{log_prefix} Timeout {timeout_context}s contexte stats")
        return {"success": False, "data": None, "error": "Service temporairement indisponible", "status_code": 503}
    except Exception as e:
        logger.warning(f"{log_prefix} Erreur contexte stats: {e}")
        return {"success": False, "data": None, "error": "Erreur données statistiques", "status_code": 500}

    if not context:
        return {"success": False, "data": None, "error": "Impossible de préparer le contexte", "status_code": 500}

    system_prompt = load_prompt_fn(prompt_name)
    if not system_prompt:
        logger.error(f"{log_prefix} Prompt pitch introuvable")
        return {"success": False, "data": None, "error": "Prompt pitch introuvable", "status_code": 500}

    _breaker = breaker or gemini_breaker
    # V131.A.2 HOTFIX — max_output_tokens 1500 → 8000 : bug prod déterministe
    # confirmé 1h14 post-deploy V131 Release 1.6.017 (13:43 local / 11:43 UTC).
    # Pitch-grilles 502 systématique n=1 ET n=3 grilles, JSON tronqué
    # finish_reason=MAX_TOKENS. V131.A.1 (1500) validé en TEST LOCAL n=1
    # uniquement — prompts prod EM + pattern multi-grilles non testés =
    # bug latent découvert en prod.
    # Nouveau budget : ~1500 tokens/grille × 5 grilles (max générateur EM)
    # + ~500 tokens JSON header/footer = 8000 tokens cible.
    # Plafond gemini-2.5-flash = 8192 → marge sécurité 192 tokens.
    # Coût identique (Vertex AI facture au token effectif, pas à
    # max_output_tokens). Couvre la totalité gamme n=1 à n=5 sans risque
    # troncature. V131.D refactorera en calcul dynamique 1500 × nb_grilles
    # si besoin d'aller au-delà de 5 grilles ou optimiser latence.
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.9,
        max_output_tokens=8000,
    )

    # V131.A — retry V129.1 inline : 2/4/8s backoff + jitter [0,1s] + cap 14s
    # + CB check per-iter. Retry UNIQUEMENT sur ClientError 429. Autres
    # erreurs = 1 attempt (timeout/5xx/APIError = différent failure mode).
    _retry_start = time.monotonic()
    response_vertex = None
    last_error = "error"

    for attempt in range(max_retries + 1):
        # CB state check — respect OPEN set by concurrent failures
        if _breaker.state == _breaker.OPEN:
            logger.warning(f"{log_prefix} Circuit breaker ouvert — fallback")
            return {"success": False, "data": None, "error": "Service Gemini temporairement indisponible", "status_code": 503}

        # V129.1 cap total 14s
        if attempt > 0 and time.monotonic() - _retry_start >= _V129_PITCH_RETRY_CAP_TOTAL:
            logger.info(f"{log_prefix} [V129_1_RETRY] cap total=14s exhausted before attempt={attempt}")
            break

        try:
            client = _get_client()
            response_vertex = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=_VERTEX_MODEL_NAME,
                    contents=[{"role": "user", "parts": [{"text": context}]}],
                    config=config,
                ),
                timeout=timeout_gemini,
            )
            # Succès — sortie boucle
            _breaker._record_success()
            break
        except CircuitOpenError:
            return {"success": False, "data": None, "error": "Service Gemini temporairement indisponible", "status_code": 503}
        except genai_errors.ClientError as e:
            if _is_rate_limit_error(e) and attempt < max_retries:
                # V128→V129.1 : retry on 429 if budget remaining. Backoff 2/4/8s + jitter.
                backoff = (
                    _V129_PITCH_RETRY_BACKOFF_BASE * (2 ** attempt)
                    + random.uniform(0, _V129_PITCH_RETRY_JITTER_MAX)
                )
                remaining = _V129_PITCH_RETRY_CAP_TOTAL - (time.monotonic() - _retry_start)
                if remaining <= 0:
                    logger.info(f"{log_prefix} [V129_1_RETRY] no budget left at attempt={attempt}")
                    _breaker._record_failure()
                    last_error = "timeout"
                    break
                backoff = min(backoff, remaining)
                logger.info(
                    "%s [V129_1_RETRY] attempt=%d/%d 429, backoff=%.1fs",
                    log_prefix, attempt + 1, max_retries, backoff,
                )
                await asyncio.sleep(backoff)
                continue
            # Non-429 ClientError OR 429 retry exhausted
            if _is_rate_limit_error(e):
                logger.warning(f"{log_prefix} Vertex 429 ResourceExhausted (retry exhausted) — fallback")
                last_error = "timeout"
            else:
                logger.warning(f"{log_prefix} Vertex ClientError {getattr(e, 'code', '?')}: {e}")
                last_error = "error"
            _breaker._record_failure()
            break
        except asyncio.TimeoutError:
            logger.warning(f"{log_prefix} Timeout Gemini Vertex ({timeout_gemini}s) — fallback")
            _breaker._record_failure()
            last_error = "timeout"
            break
        except genai_errors.ServerError as e:
            logger.warning(f"{log_prefix} Vertex ServerError {getattr(e, 'code', '?')}: {e}")
            _breaker._record_failure()
            last_error = "error"
            break
        except genai_errors.APIError as e:
            logger.error(f"{log_prefix} Vertex APIError SDK: {type(e).__name__}: {e}")
            _breaker._record_failure()
            last_error = "error"
            break
        except Exception as e:
            logger.error(f"{log_prefix} Exception inattendue Vertex: {type(e).__name__}: {e}")
            last_error = "error"
            break

    # Si pas de response (exception ou cap retry) → fallback mapping
    if response_vertex is None:
        if last_error == "timeout":
            return {"success": False, "data": None, "error": "Timeout Gemini", "status_code": 503}
        return {"success": False, "data": None, "error": "Erreur interne du serveur", "status_code": 500}

    # Parse réponse SDK B
    try:
        text = (response_vertex.text or "").strip()
    except (ValueError, AttributeError):
        logger.warning(f"{log_prefix} Vertex response blocked (SAFETY/RECITATION)")
        return {"success": False, "data": None, "error": "Gemini: réponse bloquée", "status_code": 502}

    if not text:
        return {"success": False, "data": None, "error": "Gemini: réponse vide", "status_code": 502}

    pitchs, error = parse_pitch_json(text)
    if error:
        logger.warning(f"{log_prefix} JSON invalide: {text[:200]}")
        return error

    logger.info(f"{log_prefix} OK — {len(pitchs)} pitchs générés")
    result = {"success": True, "data": {"pitchs": pitchs}, "error": None, "status_code": 200}
    # V127 — cache succès (grilles_data + lang + prompt_name pour 24h)
    pitch_cache.set(grilles_data, lang, prompt_name, result)
    return result
