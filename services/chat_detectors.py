"""
Chat detectors — Loto thin wrapper.
Shared detection functions in base_chat_detectors.py.
Loto-specific: chance synonyms, detect_mode, prochain_tirage, detect_numero,
detect_grille, requete_complexe, argent FR, OOR FR.
Response pools FR extracted to chat_responses_loto.py (V70 F08).
"""

import re
import random
import logging

logger = logging.getLogger(__name__)

# Re-export ALL shared functions and constants (consumers import from here)
from services.base_chat_detectors import (  # noqa: F401
    # Phase 0 — continuation + affirmation (V51)
    CONTINUATION_PATTERNS, _CONTINUATION_WORDS, _is_short_continuation,
    _is_affirmation_simple, _detect_game_keyword_alone,
    # Phase T — tirage detection
    _JOURS_SEMAINE, _TIRAGE_KW, _MOIS_TO_NUM, _MOIS_NOM_RE,
    _STAT_NEUTRALIZE_RE, _detect_tirage,
    # Temporal filter
    _MOIS_FR, _MOIS_RE, _MOIS_EN, _MOIS_ES, _MOIS_PT, _MOIS_DE, _MOIS_NL,
    _TEMPORAL_PATTERNS, _TEMPORAL_EXTRACT_MONTHS, _TEMPORAL_EXTRACT_YEARS,
    _TEMPORAL_EXTRACT_WEEKS, _has_temporal_filter, _extract_temporal_date,
    # Top-N extraction
    _TOP_N_PATTERNS, _extract_top_n,
    # Insult detection
    _INSULTE_MOTS, _INSULTE_PHRASES, _MENACE_PATTERNS,
    _insult_targets_bot, _detect_insulte, _count_insult_streak,
    # Compliment detection
    _COMPLIMENT_PHRASES, _COMPLIMENT_LOVE_PHRASES, _COMPLIMENT_SOLO_WORDS,
    _compliment_targets_bot, _detect_compliment, _count_compliment_streak,
    # Generation detection
    _GENERATION_PATTERN, _GENERATION_CONTEXT, _COOCCURRENCE_EXCLUSION,
    _detect_generation, _detect_generation_mode,
    _MODE_PATTERN_CONSERVATIVE, _MODE_PATTERN_RECENT,
    # Grid count + exclusions + forced numbers
    _GRID_COUNT_PATTERN, _extract_grid_count,
    _BIRTHDAY_PATTERN, _EXCLUDE_RANGE_PATTERN, _EXCLUDE_MULTIPLES_PATTERN,
    _EXCLUDE_NUMS_PATTERN,
    _extract_exclusions, _extract_nums_from_text, _extract_forced_numbers,
    # Pairs / triplets / co-occurrence
    _detect_paires, _detect_triplets,
    _detect_cooccurrence_high_n, _get_cooccurrence_high_n_response,
    # Site rating
    _detect_site_rating, get_site_rating_response,
    # V65 — Salutation + data signal
    _detect_salutation, _get_salutation_response,
    _has_data_signal,
    # V70 — Grid evaluation
    _detect_grid_evaluation,
    # Phase 3 — base requête complexe (F06 V83)
    _detect_requete_complexe_base,
)


# ────────────────────────────────────────────
# Synonymes du Numero Chance (Loto)
# ────────────────────────────────────────────

_CHANCE_SYNONYMS = (
    "chance",
    "complementaire", "complémentaire",
    "bonus",
    "special", "spécial",
)

_CHANCE_RE = r'(?:' + '|'.join(
    s.replace('é', '[eé]') for s in ("chance", "complémentaire", "bonus", "spécial")
) + r')'


def _is_chance_query(lower: str) -> bool:
    """Retourne True si le message mentionne le Numero Chance (ou un synonyme)."""
    return any(syn in lower for syn in _CHANCE_SYNONYMS)


# ────────────────────────────────────────────
# Detection de mode — Loto
# ────────────────────────────────────────────

META_KEYWORDS = ["meta", "algorithme", "moteur", "pondération", "ponderation"]


def _detect_mode(message: str, page: str) -> str:
    lower = message.lower()
    for kw in META_KEYWORDS:
        if kw in lower:
            return "meta"
    if page in ("simulateur", "loto", "statistiques"):
        return "analyse"
    return "decouverte"


# ────────────────────────────────────────────
# Phase 0-bis : Prochain tirage — Loto
# ────────────────────────────────────────────

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


# ────────────────────────────────────────────
# Phase 1 : Detection numero simple — Loto
# ────────────────────────────────────────────

def _detect_numero(message: str):
    """
    Detecte si l'utilisateur pose une question sur un numero specifique.
    Returns: (numero: int, type_num: str) ou (None, None)
    """
    lower = message.lower()

    # Pattern chance : "numero chance X", "chance X", "complémentaire X", "bonus X"...
    m = re.search(r'(?:num[eé]ro\s+)?' + _CHANCE_RE + r'\s+(\d{1,2})', lower)
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
        r'\ble\s+(\d{1,2})\b',
        r'\bdu\s+(\d{1,2})\b',
        r'^\s*(\d{1,2})\s*$',  # Bare integer "27" (V51 FIX 2)
    ]

    for pattern in patterns:
        m = re.search(pattern, lower)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 49:
                return num, "principal"

    return None, None


# ────────────────────────────────────────────
# Phase 2 : Detection grille — Loto
# ────────────────────────────────────────────

def _detect_grille(message: str):
    """
    Detecte si l'utilisateur fournit une grille de 5 numeros (+ chance optionnel).
    Returns: (numeros: list[int], chance: int|None) ou (None, None)
    """
    text = message.lower()

    # Extraire le numero chance d'abord (et le retirer du texte)
    chance = None
    chance_patterns = [
        _CHANCE_RE + r'\s*[:\s]*(\d{1,2})',
        r'n[°o]?\s*' + _CHANCE_RE + r'\s*[:\s]*(\d{1,2})',
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

    all_numbers = [int(x) for x in re.findall(r'\b(\d{1,2})\b', text)]
    valid_nums = [n for n in all_numbers if 1 <= n <= 49]

    seen = set()
    unique_nums = []
    for n in valid_nums:
        if n not in seen:
            seen.add(n)
            unique_nums.append(n)

    if len(unique_nums) != 5:
        return None, None

    return unique_nums, chance


# ────────────────────────────────────────────
# Phase 3 : Detection requete complexe — Loto
# F12 V83: pre-compiled regex (mirror EM pattern V82 F06)
# ────────────────────────────────────────────

_LOTO_COMP_RE = [
    re.compile(r'compar\w*\s+(?:le\s+)?(\d{1,2})\s+(?:et|avec|vs\.?)\s+(?:le\s+)?(\d{1,2})', re.I),
    re.compile(r'(\d{1,2})\s+vs\.?\s+(\d{1,2})', re.I),
    re.compile(r'diff[eé]rence\s+entre\s+(?:le\s+)?(\d{1,2})\s+et\s+(?:le\s+)?(\d{1,2})', re.I),
    re.compile(r'entre\s+(?:le\s+)?(\d{1,2})\s+et\s+(?:le\s+)?(\d{1,2})\s.*(?:lequel|qui)', re.I),
    re.compile(r'compar\w*\b[^.?!]*?(?:du\s+|le\s+|el\s+|del\s+|o\s+|do\s+|da\s+|dos\s+|das\s+|de\s+|von\s+|van\s+)?(\d{1,2})\s+(?:et|avec|vs\.?|and|und|en|e|y)\s+(?:du\s+|le\s+|el\s+|del\s+|o\s+|do\s+|da\s+|dos\s+|das\s+|de\s+|von\s+|van\s+)?(\d{1,2})', re.I),
]

_LOTO_CAT_CHAUD_RE = [
    re.compile(r'(?:quels?|les?|num[eé]ros?)\s+.*chauds?', re.I),
    re.compile(r'chauds?\s+(?:en ce moment|actuellement)', re.I),
    re.compile(r'(?:num[eé]ros?|lesquels)\s+(?:sont|en)\s+tendance', re.I),
]

_LOTO_CAT_FROID_RE = [
    re.compile(r'(?:quels?|les?|num[eé]ros?)\s+.*froids?', re.I),
    re.compile(r'froids?\s+(?:en ce moment|actuellement)', re.I),
    re.compile(r'num[eé]ros?\s+(?:en\s+retard|qui\s+sort\w*\s+(?:pas|plus|jamais))', re.I),
]

_LOTO_FREQ_DESC_RE = [
    re.compile(r'(?:plus|les?\s+plus)\s+(?:fr[eé]quent|sorti|courant|pr[eé]sent)', re.I),
    re.compile(r'(?:top|meilleur|premier)\s+\d{0,2}\s*(?:num[eé]ro|boule|chance)?', re.I),
    re.compile(r'num[eé]ros?\s+(?:les?\s+)?plus\s+(?:sorti|fr[eé]quent)', re.I),
    re.compile(r'(?:quels?|quel)\s+(?:est|sont)\s+(?:le|les)\s+num[eé]ro', re.I),
    re.compile(r'(?:sort\w*|tir[eé]\w*|appara[iî]\w*)\s+le\s+plus\s+(?:souvent|fr[eé]quemment)', re.I),
]

_LOTO_FREQ_ASC_RE = [
    re.compile(r'(?:moins|les?\s+moins)\s+(?:fr[eé]quent|sorti|courant)', re.I),
    re.compile(r'(?:flop|dernier|pire)\s+\d{0,2}', re.I),
]

_LOTO_ECART_DESC_RE = [
    re.compile(r'(?:plus\s+(?:gros|grand|long)|plus\s+en)\s+(?:[eé]cart|retard)', re.I),
    re.compile(r'(?:[eé]cart|retard)\s+(?:les?\s+)?plus\s+(?:gros|grand|long|important)', re.I),
    re.compile(r'(?:plus\s+(?:long|grand)temps?)\s+(?:sans\s+)?sort', re.I),
]

_LOTO_ECART_ASC_RE = [
    re.compile(r'(?:plus\s+(?:petit|court))\s+(?:[eé]cart|retard)', re.I),
    re.compile(r'(?:sorti|apparu)\s+(?:le\s+plus\s+)?r[eé]cemment', re.I),
]


def _detect_requete_complexe(message: str):
    """Detecte les requetes complexes Loto (thin wrapper — F06 V83)."""
    return _detect_requete_complexe_base(
        message,
        comp_re=_LOTO_COMP_RE,
        cat_chaud_re=_LOTO_CAT_CHAUD_RE, cat_froid_re=_LOTO_CAT_FROID_RE,
        freq_desc_re=_LOTO_FREQ_DESC_RE, freq_asc_re=_LOTO_FREQ_ASC_RE,
        ecart_desc_re=_LOTO_ECART_DESC_RE, ecart_asc_re=_LOTO_ECART_ASC_RE,
        secondary_query_fn=_is_chance_query,
        secondary_type="chance", primary_type="principal",
        max_primary=49, max_secondary=10,
    )


# ═══════════════════════════════════════════════════════
# Phase I — Insult response pools + functions (FR)
# V70 F08: extracted to chat_responses_loto.py, re-exported here
# ═══════════════════════════════════════════════════════

from services.chat_responses_loto import (  # noqa: F401
    _INSULT_L1, _INSULT_L2, _INSULT_L3, _INSULT_L4,
    _INSULT_SHORT, _MENACE_RESPONSES,
    _get_insult_response, _get_insult_short, _get_menace_response,
)


# ═══════════════════════════════════════════════════════
# Phase C — Compliment response pools + functions (FR)
# V70 F08: extracted to chat_responses_loto.py, re-exported here
# ═══════════════════════════════════════════════════════

from services.chat_responses_loto import (  # noqa: F401
    _COMPLIMENT_L1, _COMPLIMENT_L2, _COMPLIMENT_L3,
    _COMPLIMENT_LOVE, _COMPLIMENT_MERCI,
    _get_compliment_response,
)


# ═══════════════════════════════════════════════════════
# Phase A — Argent / gains / paris (multilingue, V71)
# FR patterns are the primary set; EN/ES/PT/DE/NL added for Loto pages
# visited by non-FR users. Mirrors _ARGENT_*_EM dicts in
# chat_detectors_em_guardrails.py.
# ═══════════════════════════════════════════════════════

_ARGENT_PHRASES = {
    "fr": [
        r'\bdevenir\s+riche',
        r'\bgros\s+lot',
        r'\bsuper\s+cagnotte',
        r'\btoucher\s+le\s+gros\s+lot',
        r'\bcombien\s+(?:on|je|tu|peut[\s-]on)\s+gagn',
        r'\bcombien\s+[çc]a\s+rapporte',
        r'\bstrat[eé]gie\s+pour\s+gagner',
        r'\best[\s-]ce\s+rentable',
        r'\b[çc]a\s+rapporte',
        r'\bretour\s+sur\s+investissement',
        r'\b(?:vaut|vaudrait)\s+le\s+coup',
        r'\bjoue[rs]?\s+\d+\s*[€$]',
        r'\bmise\s+de\s+\d+',
        r'\bbudget\s+de\s+\d+',
        r'\b\d+\s*[€$]\s+par\s+(?:mois|semaine|an|jour)',
        # V50 — adversarial patterns
        r'\broi\b',
        r'\bvivre\s+du\s+(?:loto|jeu|loterie)',
        r'\brevenus?\s+passifs?',
        r'\bmaximiser\s+(?:mes|les|ses)\s+gains',
        r'\boptimiser\s+(?:mes|les|ses)\s+chances?\s+de\s+gagner',
        r'\brentabiliser\s+(?:mes|les|ses)\s+(?:mises?|grilles?)',
        r'\brendement\s+(?:de|des|sur)\s+(?:mes|les|ses)\s+(?:mises?|grilles?|jeux?)',
        r'\bcapital\s+(?:de\s+)?(?:jeu|mise)',
        r'\bplacement\s+(?:au\s+)?(?:loto|jeu|loterie)',
        r'\b(?:investissement|investir)\s+(?:au|dans\s+le|sur\s+le)\s+(?:loto|jeu|loterie)',
        r'\bstrat[eé]gie\s+(?:pour\s+)?rentabiliser',
    ],
    "en": [
        r'\bget\s+rich',
        r'\bhow\s+much\s+can\s+(?:i|you|we)\s+win',
        r'\bhow\s+much\s+does\s+it\s+pay',
        r'\bstrategy\s+to\s+win',
        r'\broi\b',
        r'\b(?:live|living)\s+off\s+(?:the\s+)?(?:lottery|lotto)',
        r'\bpassive\s+income',
        r'\bmaximize?\s+(?:my|your|the)?\s*winnings?',
        r'\bmake\s+money\s+(?:from|with|playing)\s+(?:lottery|lotto)',
        r'\b(?:investment|invest)\s+in\s+(?:lottery|lotto|tickets?|gambling)',
    ],
    "es": [
        r'\bhacerse\s+rico',
        r'\bcu[aá]nto\s+se\s+gana',
        r'\bestrategia\s+para\s+ganar',
        r'\broi\b',
        r'\bvivir\s+de\s+la\s+(?:loter[ií]a)',
        r'\bretorno\s+de\s+inversi[oó]n',
        r'\bmaximizar\s+(?:mis|las|sus)\s+ganancias',
        r'\bingresos?\s+pasivos?',
    ],
    "pt": [
        r'\bficar\s+rico',
        r'\bquanto\s+se\s+ganha',
        r'\bestrat[eé]gia\s+para\s+ganhar',
        r'\broi\b',
        r'\bviver\s+d[ao]\s+(?:lotaria|loteria)',
        r'\bretorno\s+de\s+investimento',
        r'\bmaximizar\s+(?:os\s+)?ganhos',
        r'\brendimentos?\s+passivos?',
    ],
    "de": [
        r'\breich\s+werden',
        r'\bwie\s+viel\s+kann\s+man\s+gewinnen',
        r'\bgewinnstrategie',
        r'\broi\b',
        r'\bvom\s+(?:lotto|spiel|lotteri?e)\s+leben',
        r'\bgewinne?\s+maximieren',
        r'\bpassives?\s+einkommen',
    ],
    "nl": [
        r'\brijk\s+worden',
        r'\bhoeveel\s+kun\s+je\s+winnen',
        r'\bstrategie\s+om\s+te\s+winnen',
        r'\broi\b',
        r'\bleven\s+van\s+(?:de\s+)?(?:loterij|lotto)',
        r'\bwinsten?\s+maximaliseren',
        r'\bpassief\s+inkomen',
    ],
}

# Backward compat alias — tests and scripts import this
_ARGENT_PHRASES_FR = _ARGENT_PHRASES["fr"]

# V65 — EuroMillions/EuroDreams game-name guard (avoid false positives on "euro(s)")
# Matches: euromillion(s), euro million(s), euros million(s), eurodream(s),
# euro dream(s), euros dream(s), l'euro million, leuro million, etc.
_EURO_GAME_RE = re.compile(
    r"(?:l['\u2019]?)?euros?\s*(?:mill|milh|dream)", re.IGNORECASE,
)
_EURO_GAME_SKIP = {
    "fr": {"euro", "euros", "eur", "million", "millions"},
    "en": {"euro", "euros", "eur", "million", "millions"},
    "es": {"euro", "euros", "eur", "millón", "millon", "millones"},
    "pt": {"euro", "euros", "eur", "milhão", "milhao", "milhões", "milhoes"},
    "de": {"euro", "euros", "eur", "million", "millionen"},
    "nl": {"euro", "euros", "eur", "miljoen", "miljoenen"},
}

_ARGENT_MOTS = {
    "fr": {
        "argent", "euros", "eur",
        "cagnotte", "jackpot",
        "gains", "gagner",
        "prix",
        "million", "millions", "milliard", "milliards",
        "mise", "miser",
        "parier", "pari",
        "lot",
        "pognon", "fric", "thune", "thunes", "sous",
        "riche", "fortune",
        "profit", "bénéfice", "benefice",
        "remporter",
        "rentable", "rentabilité", "rentabilite",
        "profitable", "investissement", "investir",
    },
    "en": {
        "money", "euros", "eur",
        "jackpot", "prize",
        "win", "winning", "winnings",
        "million", "millions",
        "bet", "betting", "gambling",
        "payout", "cash",
        "rich", "fortune",
        "profit",
    },
    "es": {
        "dinero", "euros", "eur",
        "bote", "premio",
        "ganar", "ganancias",
        "millón", "millon", "millones",
        "apostar", "apuesta",
        "rico", "fortuna",
    },
    "pt": {
        "dinheiro", "euros", "eur",
        "jackpot", "prémio", "premio",
        "ganhar", "ganhos",
        "milhão", "milhao", "milhões", "milhoes",
        "apostar", "aposta",
        "rico", "fortuna",
    },
    "de": {
        "geld", "euro", "euros", "eur",
        "jackpot", "gewinn", "gewinne", "gewinnen",
        "million", "millionen",
        "wetten", "einsatz",
        "reich", "vermögen", "vermoegen",
    },
    "nl": {
        "geld", "euro", "euros", "eur",
        "jackpot", "prijs",
        "winnen", "winst",
        "miljoen", "miljoenen",
        "gokken", "inzet",
        "rijk", "fortuin",
    },
}

# Backward compat alias
_ARGENT_MOTS_FR = _ARGENT_MOTS["fr"]

_ARGENT_STRONG = {
    "fr": [
        r'\bdevenir\s+riche',
        r'\bstrat[eé]gie\s+pour\s+gagner',
        r'\btoucher\s+le\s+gros\s+lot',
        r'\bcombien\s+(?:on|je|tu|peut[\s-]on)\s+gagn',
        r'\bcombien\s+[çc]a\s+rapporte',
        # V50 — L2 strong adversarial
        r'\bvivre\s+du\s+(?:loto|jeu|loterie)',
        r'\brevenus?\s+passifs?',
        r'\bstrat[eé]gie\s+(?:pour\s+)?rentabiliser',
    ],
    "en": [
        r'\bget\s+rich',
        r'\bstrategy\s+to\s+win',
        r'\bhow\s+much\s+can\s+(?:i|you|we)\s+win',
        r'\bhow\s+much\s+does\s+it\s+pay',
        r'\b(?:live|living)\s+off\s+(?:the\s+)?(?:lottery|lotto)',
        r'\bpassive\s+income',
    ],
    "es": [
        r'\bhacerse\s+rico',
        r'\bestrategia\s+para\s+ganar',
        r'\bcu[aá]nto\s+se\s+gana',
        r'\bvivir\s+de\s+la\s+(?:loter[ií]a)',
        r'\bingresos?\s+pasivos?',
    ],
    "pt": [
        r'\bficar\s+rico',
        r'\bestrat[eé]gia\s+para\s+ganhar',
        r'\bquanto\s+se\s+ganha',
        r'\bviver\s+d[ao]\s+(?:lotaria|loteria)',
        r'\brendimentos?\s+passivos?',
    ],
    "de": [
        r'\breich\s+werden',
        r'\bgewinnstrategie',
        r'\bwie\s+viel\s+kann\s+man\s+gewinnen',
        r'\bvom\s+(?:lotto|spiel|lotteri?e)\s+leben',
        r'\bpassives?\s+einkommen',
    ],
    "nl": [
        r'\brijk\s+worden',
        r'\bstrategie\s+om\s+te\s+winnen',
        r'\bhoeveel\s+kun\s+je\s+winnen',
        r'\bleven\s+van\s+(?:de\s+)?(?:loterij|lotto)',
        r'\bpassief\s+inkomen',
    ],
}

# Backward compat alias
_ARGENT_STRONG_FR = _ARGENT_STRONG["fr"]

_ARGENT_BETTING = {
    "fr": {"parier", "miser", "pari"},
    "en": {"bet", "betting", "gambling"},
    "es": {"apostar", "apuesta"},
    "pt": {"apostar", "aposta"},
    "de": {"wetten", "einsatz"},
    "nl": {"gokken", "inzet"},
}

# Backward compat alias
_ARGENT_BETTING_FR = _ARGENT_BETTING["fr"]

# V70 F08: argent response pools extracted to chat_responses_loto.py
from services.chat_responses_loto import (  # noqa: F401
    _ARGENT_L1, _ARGENT_L2, _ARGENT_L3,
)

_PEDAGOGIE_LIMITES_FR = [
    r'\b(?:peut|peux|pouvez|pourrait|pourrions)[\s-]+(?:on|tu|vous|t[\s-]?on)\s+pr[eé]dire',
    r'\b(?:est[\s-]il|est[\s-]ce)\s+possible\s+de\s+pr[eé]dire',
    r'\bpossible\s+(?:de\s+)?pr[eé]dire',
    r'\bpourquoi\s+(?:on\s+)?(?:ne\s+)?(?:peut|peux|pouvez)\s+(?:pas|plus)\s+pr[eé]dire',
    r'\bpourquoi\s+(?:on\s+)?(?:ne\s+)?(?:peut|peux)\s+(?:pas|plus)\s+gagner\s+[àa]\s+(?:coup\s+s[uû]r|tous?\s+les?\s+coups?)',
    r'\bpourquoi\s+(?:personne|aucun)',
    r'\b(?:loto|tirage|loterie)\s+(?:est[\s-]il|est[\s-]ce|est[\s-]elle)\s+(?:pr[eé]visible|al[eé]atoire|truqu[eé]|vraiment)',
    r'\b(?:loto|tirage|loterie)\s+.{0,15}(?:pr[eé]visible|al[eé]atoire|truqu[eé])',
    r'\b(?:est[\s-]ce\s+que?\s+le\s+)?(?:loto|tirage)\s+(?:est\s+)?truqu[eé]',
    r'\b(?:tirage|loto|loterie)\s+(?:est[\s-]il|est[\s-]ce)\s+(?:vraiment\s+)?al[eé]atoire',
    r'\bimpossible\s+(?:de\s+)?(?:pr[eé]dire|pr[eé]voir|gagner)',
    r'\b(?:stats?|statistiques?|algo(?:rithme)?|ia|intelligence\s+artificielle)\s+.{0,15}(?:pr[eé]dire|pr[eé]voir|garantir|pr[eé]diction)',
    r"\b(?:ton|votre|l)\s*['\u2019]?\s*(?:algo|ia|outil|moteur)\s+.{0,15}(?:pr[eé]dire|gagner|garanti)",
    r'\best[\s-]ce\s+que?\s+[çc]a\s+(?:marche|fonctionne)\s+(?:vraiment|pour\s+(?:gagner|de\s+vrai))',
    r'\b(?:ton|votre)\s+(?:ia|algo|outil)\s+(?:peut|va)\s+(?:me\s+faire\s+)?gagner',
    r'\bexiste[\s-]t[\s-]il\s+(?:une?\s+)?(?:m[eé]thode|formule|syst[eè]me|astuce|truc)\s+(?:pour\s+)?gagner',
    r'\b(?:loi\s+des\s+grands?\s+nombres?|gambler.?s?\s*fallacy|biais\s+(?:du\s+joueur|cognitif))',
    r'\bchaque\s+tirage\s+(?:est\s+)?ind[eé]pendant',
    r'\b(?:num[eé]ros?|boules?)\s+(?:ont|a)[\s-](?:t[\s-])?(?:ils?|elles?)\s+(?:une?\s+)?m[eé]moire',
    r'\b(?:hasard|al[eé]atoire)\s+(?:est\s+)?(?:vraiment\s+)?(?:impr[eé]visible|al[eé]atoire|pur)',
]


def _detect_pedagogie_limites(message: str) -> bool:
    """Detecte les questions pedagogiques sur les limites de la prediction."""
    lower = message.lower()
    for pattern in _PEDAGOGIE_LIMITES_FR:
        if re.search(pattern, lower):
            return True
    return False


_SCORE_QUESTION_FR = [
    r'\bscore\b.*\b(?:chances?|gagner|probabilit[eé])',
    r'\b(?:chances?|gagner|probabilit[eé]).*\bscore\b',
    r'\b\d+\s*/\s*\d+\b.*\b(?:chances?|gagner|probabilit[eé])',
    r'\b(?:chances?|gagner|probabilit[eé]).*\b\d+\s*/\s*\d+\b',
    r'\bconformit[eé]\b.*\b(?:chances?|gagner|probabilit[eé])',
    r'\bscore\s+interne\b',
    r'\bscore\s+de\s+conformit[eé]\b',
]


def _detect_score_question(message: str) -> bool:
    """Detecte si le message porte sur l'explication du score de conformite."""
    lower = message.lower()
    for pattern in _SCORE_QUESTION_FR:
        if re.search(pattern, lower):
            return True
    return False


def _detect_argent(message: str, lang: str = "fr") -> bool:
    """Detecte si le message concerne l'argent, les gains ou les paris (multilingue).

    Args:
        message: user message
        lang: language code (fr/en/es/pt/de/nl), defaults to "fr"
    """
    if _detect_generation(message):
        return False
    if _detect_score_question(message):
        return False
    if _detect_pedagogie_limites(message):
        return False
    lower = message.lower()
    phrases = _ARGENT_PHRASES.get(lang, _ARGENT_PHRASES["fr"])
    for pattern in phrases:
        if re.search(pattern, lower):
            return True
    mots = _ARGENT_MOTS.get(lang, _ARGENT_MOTS["fr"])
    is_euro_game = bool(_EURO_GAME_RE.search(lower))
    skip = _EURO_GAME_SKIP.get(lang, _EURO_GAME_SKIP["fr"]) if is_euro_game else set()
    for mot in mots:
        if mot in skip:
            continue
        if re.search(r'\b' + re.escape(mot) + r'\b', lower):
            return True
    return False


def _get_argent_response(message: str, lang: str = "fr") -> str:
    """Selectionne une reponse argent Loto selon le niveau (L1/L2/L3).

    Responses are always in French (Loto = FDJ France market).
    The lang parameter is used only for detection pattern selection.
    """
    lower = message.lower()
    betting = _ARGENT_BETTING.get(lang, _ARGENT_BETTING["fr"])
    for mot in betting:
        if re.search(r'\b' + re.escape(mot) + r'\b', lower):
            return _ARGENT_L3[0]
    strong = _ARGENT_STRONG.get(lang, _ARGENT_STRONG["fr"])
    for pattern in strong:
        if re.search(pattern, lower):
            return random.choice(_ARGENT_L2)
    return random.choice(_ARGENT_L1)


# ═══════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════
# Phase OOR — Numeros hors range pools + functions (Loto FR)
# V70 F08: extracted to chat_responses_loto.py, re-exported here
# ═══════════════════════════════════════════════════════

from services.chat_responses_loto import (  # noqa: F401
    _OOR_L1, _OOR_L2, _OOR_L3, _OOR_CLOSE, _OOR_ZERO_NEG, _OOR_CHANCE,
)


def _detect_out_of_range(message: str):
    """
    Detecte les numeros hors range du Loto dans le message.
    Returns: (numero: int, context: str) ou (None, None)
    """
    lower = message.lower()

    # Chance hors range (> 10)
    m = re.search(r'(?:num[eé]ro\s+)?' + _CHANCE_RE + r'\s+(\d+)', lower)
    if m:
        num = int(m.group(1))
        if num > 10:
            return num, "chance_high"

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
            if 2019 <= num <= 2030:
                continue
            if 1 <= num <= 49:
                continue
            if num <= 0:
                return num, "zero_neg"
            if num in (50, 51):
                return num, "close"
            if num > 49:
                return num, "principal_high"

    return None, None


def _count_oor_streak(history) -> int:
    """Compte les messages OOR consecutifs (du plus recent au plus ancien)."""
    count = 0
    for msg in reversed(history):
        if msg.role == "user":
            oor_num, _ = _detect_out_of_range(msg.content)
            if oor_num is not None:
                count += 1
            else:
                break
    return count



# V70 F08: _get_oor_response extracted to chat_responses_loto.py
from services.chat_responses_loto import _get_oor_response  # noqa: F401, E402
