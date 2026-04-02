"""
Chat detectors — EuroMillions intent detection.
Star queries, mode, prochain tirage, numero/grille/requete complexe EM,
out-of-range EM. Split from chat_detectors_em.py (V70 F11).
"""

import re
import random

from services.base_chat_detectors import (
    _detect_insulte, _count_insult_streak,
    _detect_compliment, _count_compliment_streak,
    _extract_top_n,
    _detect_paires, _detect_triplets,
    _detect_generation, _detect_generation_mode,
    _is_affirmation_simple, _detect_game_keyword_alone,  # V51
    _detect_grid_evaluation,  # V70
    _detect_requete_complexe_base,  # F06 V83
)


# ────────────────────────────────────────────
# Synonymes des étoiles (EuroMillions) — 6 langues
# "complémentaire", "bonus", "star", "estrella"… → même intent que "étoile"
# ────────────────────────────────────────────

# Regex alternation pour les patterns étoile (6 langues)
_STAR_RE = r'(?:' + '|'.join(
    s.replace('é', '[eé]') for s in (
        "étoile", "complémentaire", "bonus", "spécial",
        "star", "lucky\\s+star", "complementary",
        "estrella", "complementari[oa]",
        "estrela", "complementar",
        "stern", "erg[aä]nzungszahl",
        "ster",
    )
) + r')'

# Word-boundary regex for _is_star_query (avoids "ster" matching "master")
_STAR_QUERY_RE = re.compile(
    r'\b(?:'
    + '|'.join(
        s.replace('é', '[eé]').replace('ä', '[aä]')
        for s in (
            "étoile", "étoiles",
            "complémentaire", "complémentaires",
            "bonus",
            "spécial", "spéciale",
            "star", "stars", "lucky star",
            "complementary",
            "estrella", "estrellas",
            "complementario", "complementaria",
            "estrela", "estrelas",
            "complementar",
            "stern", "sterne",
            "ergänzungszahl",
            "ster", "sterren",
        )
    )
    + r')s?\b'
)


def _is_star_query(lower: str) -> bool:
    """Retourne True si le message mentionne les étoiles EM (ou un synonyme, 6 langs)."""
    return bool(_STAR_QUERY_RE.search(lower))


# Patterns for "numéros" / "numbers" / "boules" — indicates explicit main number mention
_BOULE_QUERY_RE = re.compile(
    r'\b(?:'
    r'num[eé]ros?|boules?|'           # FR
    r'numbers?|balls?|'               # EN
    r'n[uú]meros?|bolas?|'           # ES/PT
    r'zahlen|kugeln?|'               # DE
    r'nummers|ballen?'               # NL
    r')\b',
    re.IGNORECASE
)


def _wants_both_boules_and_stars(message: str) -> bool:
    """Detecte si le message demande à la fois les numéros ET les étoiles."""
    lower = message.lower()
    return bool(_BOULE_QUERY_RE.search(lower)) and _is_star_query(lower)


def _detect_paires_em(message: str) -> bool:
    """Detecte les questions sur les paires EM (meme regex multilingue que Loto)."""
    return _detect_paires(message)


def _detect_triplets_em(message: str) -> bool:
    """Detecte les questions sur les triplets EM (meme regex multilingue que Loto)."""
    return _detect_triplets(message)

META_KEYWORDS = ["meta", "algorithme", "moteur", "pondération", "ponderation"]

# ────────────────────────────────────────────
# F06 V82: compiled regex for _detect_requete_complexe_em
# Catégorie chaud (16 patterns, 6 langues)
# ────────────────────────────────────────────
_CAT_CHAUD_RE = [
    re.compile(r'(?:quels?|les?|num[eé]ros?)\s+.*chauds?', re.I),
    re.compile(r'chauds?\s+(?:en ce moment|actuellement|du moment)', re.I),
    re.compile(r'(?:num[eé]ros?|lesquels)\s+(?:sont|en)\s+tendance', re.I),
    re.compile(r'(?:num[eé]ros?|num[eé]ro\s*stars?)\s+du\s+moment', re.I),
    re.compile(r'\bdu\s+moment\b.*(?:num[eé]ro|boule|[eé]toile|star)', re.I),
    re.compile(r'(?:num[eé]ros?|num[eé]ro\s*stars?|boules?|[eé]toiles?)\s+(?:en\s+ce\s+moment|actuellement)', re.I),
    re.compile(r'\b(?:hot|hottest)\s+numbers?\b', re.I),
    re.compile(r'\bnumbers?\s+(?:on\s+a\s+)?(?:hot\s+streak|trending|right\s+now)\b', re.I),
    re.compile(r'\bn[uú]meros?\s+calientes?\b', re.I),
    re.compile(r'\bn[uú]meros?\s+(?:del\s+momento|de\s+moda)\b', re.I),
    re.compile(r'\bn[uú]meros?\s+quentes?\b', re.I),
    re.compile(r'\bn[uú]meros?\s+do\s+momento\b', re.I),
    re.compile(r'\bhei[sß]e\s+zahlen\b', re.I),
    re.compile(r'\baktuell\w*\s+zahlen\b', re.I),
    re.compile(r'\bhete\s+nummers\b', re.I),
    re.compile(r'\bnummers\s+van\s+(?:het\s+)?moment\b', re.I),
]

# Catégorie froid (8 patterns, 6 langues)
_CAT_FROID_RE = [
    re.compile(r'(?:quels?|les?|num[eé]ros?)\s+.*froids?', re.I),
    re.compile(r'froids?\s+(?:en ce moment|actuellement)', re.I),
    re.compile(r'num[eé]ros?\s+(?:en\s+retard|qui\s+sort\w*\s+(?:pas|plus|jamais))', re.I),
    re.compile(r'\b(?:cold|coldest)\s+numbers?\b', re.I),
    re.compile(r'\bnumbers?\s+(?:overdue|not\s+drawn)\b', re.I),
    re.compile(r'\bn[uú]meros?\s+fr[ií]os?\b', re.I),
    re.compile(r'\bkalte\s+zahlen\b', re.I),
    re.compile(r'\bkoude\s+nummers\b', re.I),
]

# Classement étoiles fréquence (6 patterns, 6 langues)
_STAR_FREQ_RE = [
    re.compile(r'(?:sort\w*|tir[eé]\w*|apparai)\w*\s+le\s+plus', re.I),
    re.compile(r'(?:come|drawn|appear)\w*\s+(?:out\s+)?(?:the\s+)?most', re.I),
    re.compile(r'(?:plus|most|m[aá]s|mais|meist|meest)\s+(?:fr[eé]quent|sorti|drawn|frecuent|frequent|getrokken|gezogen)', re.I),
    re.compile(r'(?:sort\w*|sal\w*|saem|sair|gezogen|getrokken)\w*\s+(?:le\s+plus|the\s+most|m[aá]s|mais|am\s+meisten|het\s+meest)', re.I),
    re.compile(r'(?:quell?e?s?|which|cu[aá]le?s?|quais|welche|welke)\b', re.I),
    re.compile(r'(?:class\w+|rank|top|fr[eé]quenc|frequenc|h[aä]ufig|vaak)', re.I),
]

# Classement fréquence desc (10 patterns, 6 langues)
_FREQ_DESC_RE = [
    re.compile(r'(?:plus|les?\s+plus)\s+(?:fr[eé]quent|sorti|courant|pr[eé]sent)', re.I),
    re.compile(r'(?:top|meilleur|premier)\s+\d{0,2}\s*(?:num[eé]ro|boule|[eé]toile)?', re.I),
    re.compile(r'num[eé]ros?\s+(?:les?\s+)?plus\s+(?:sorti|fr[eé]quent)', re.I),
    re.compile(r'(?:quels?|quel)\s+(?:est|sont)\s+(?:le|les)\s+num[eé]ro', re.I),
    re.compile(r'\b(?:most\s+(?:drawn|common|frequent)|most\s+often|hottest)\b', re.I),
    re.compile(r'\bm[aá]s\s+(?:sorteados?|frecuentes?|comunes?)\b', re.I),
    re.compile(r'\bmais\s+(?:sorteados?|frequentes?|comuns?)\b', re.I),
    re.compile(r'\b(?:am\s+h[aä]ufigsten|h[aä]ufigsten?\s+gezogen|meistgezogen)\b', re.I),
    re.compile(r'\b(?:meest\s+getrokken|meest\s+voorkomend|vaakst\s+getrokken|vaakst\s+voor)\b', re.I),
    re.compile(r'\branking\b|\brangliste\b|\branglijst\b|\bclasificaci[oó]n\b|\bclassifica[çc][aã]o\b', re.I),
]

# Classement fréquence asc (7 patterns, 6 langues)
_FREQ_ASC_RE = [
    re.compile(r'(?:moins|les?\s+moins)\s+(?:fr[eé]quent|sorti|courant)', re.I),
    re.compile(r'(?:flop|dernier|pire)\s+\d{0,2}', re.I),
    re.compile(r'\b(?:least\s+(?:drawn|common|frequent)|coldest)\b', re.I),
    re.compile(r'\bmenos\s+(?:sorteados?|frecuentes?|comunes?)\b', re.I),
    re.compile(r'\bmenos\s+(?:sorteados?|frequentes?|comuns?)\b', re.I),
    re.compile(r'\b(?:am\s+seltensten|seltensten?\s+gezogen|wenigsten?\s+gezogen)\b', re.I),
    re.compile(r'\b(?:minst\s+getrokken|minst\s+voorkomend)\b', re.I),
]

# Classement écart desc (10 patterns, 6 langues)
_ECART_DESC_RE = [
    re.compile(r'(?:plus\s+(?:gros|grand|long)|plus\s+en)\s+(?:[eé]cart|retard)', re.I),
    re.compile(r'(?:[eé]cart|retard)\s+(?:les?\s+)?plus\s+(?:gros|grand|long|important)', re.I),
    re.compile(r'(?:plus\s+(?:long|grand)temps?)\s+(?:sans\s+)?sort', re.I),
    re.compile(r'\b(?:largest|biggest|longest)\s+(?:gap|delay)\b', re.I),
    re.compile(r'\bmayor\s+(?:retraso|intervalo)\b', re.I),
    re.compile(r'\bmaior\s+(?:atraso|intervalo)\b', re.I),
    re.compile(r'\bgr[oö][sß]te[rn]?\s+(?:abstand|verz[oö]gerung)\b', re.I),
    re.compile(r'\bl[aä]ngste[rn]?\s+(?:abstand|verz[oö]gerung)\b', re.I),
    re.compile(r'\bgrootste\s+(?:achterstand|vertraging)\b', re.I),
    re.compile(r'\blangste\s+(?:achterstand|vertraging)\b', re.I),
]

# Classement écart asc (9 patterns, 6 langues)
_ECART_ASC_RE = [
    re.compile(r'(?:plus\s+(?:petit|court))\s+(?:[eé]cart|retard)', re.I),
    re.compile(r'(?:sorti|apparu)\s+(?:le\s+plus\s+)?r[eé]cemment', re.I),
    re.compile(r'\b(?:smallest|shortest)\s+(?:gap|delay)\b', re.I),
    re.compile(r'\bmenor\s+(?:retraso|intervalo)\b', re.I),
    re.compile(r'\bmenor\s+(?:atraso|intervalo)\b', re.I),
    re.compile(r'\bkleinste[rn]?\s+(?:abstand|verz[oö]gerung)\b', re.I),
    re.compile(r'\bk[uü]rzeste[rn]?\s+(?:abstand|verz[oö]gerung)\b', re.I),
    re.compile(r'\bkleinste\s+(?:achterstand|vertraging)\b', re.I),
    re.compile(r'\bkortste\s+(?:achterstand|vertraging)\b', re.I),
]

# Prochain tirage EM
_PROCHAIN_TIRAGE_EM_RE = re.compile(
    r'(?:prochain|prochaine|quand|date)\s+.*(?:tirage|euromillions|draw)'
    r'|(?:tirage|euromillions)\s+.*(?:prochain|prochaine|quand|date)'
    r'|c.est\s+quand\s+(?:le\s+)?(?:prochain\s+)?(?:tirage|euromillions)'
    r'|(?:il\s+(?:y\s+a|est)\s+(?:un\s+)?tirage\s+quand)'
    r'|(?:quand\s+(?:est|a)\s+lieu)'
    r'|(?:prochain\s+(?:tirage|euromillions))',
    re.I,
)


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
    return bool(_PROCHAIN_TIRAGE_EM_RE.search(message.lower()))


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

    # Pattern etoile : "etoile X", "étoile X", "star X", "complémentaire X"...
    m = re.search(r'(?:num[eé]ro\s+)?' + _STAR_RE + r'\s+(\d{1,2})', lower)
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
        r'\ble\s+(\d{1,2})\b',
        r'\bdu\s+(\d{1,2})\b',
        r'^\s*(\d{1,2})\s*$',  # Bare integer "27" (V51 FIX 2)
    ]

    for pattern in patterns:
        m = re.search(pattern, lower)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 50:
                return num, "boule"

    return None, None


# ════════════════════════════════════════════════════════════
# Detect grille EM (5 boules 1-50 + 2 etoiles 1-12)
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

    etoile_patterns_double = [
        _STAR_RE + r's?\s*[:\s]*(\d{1,2})\s+(?:et\s+|and\s+|y\s+|e\s+|und\s+|en\s+)?(\d{1,2})',
        _STAR_RE + r's?\s*[:\s]*(\d{1,2})[-–]\s*(\d{1,2})',  # "étoiles 11-12" (V51 FIX 3)
        r'[☆★⭐]\s*(\d{1,2})[-–\s]+(\d{1,2})\s*[☆★⭐]?',  # Unicode stars "☆11-12☆" (V51 FIX 3)
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
        m = re.search(_STAR_RE + r'\s+(\d{1,2})', text)
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

    if len(unique_nums) != 5:
        return None, None

    return unique_nums, etoiles


# ════════════════════════════════════════════════════════════
# Requete complexe EM (classement, comparaison, categorie)
# F06 V83: thin wrapper — compiled comp patterns + base function
# ════════════════════════════════════════════════════════════

_EM_COMP_RE = [
    re.compile(r'compar\w*\s+(?:le\s+)?(\d{1,2})\s+(?:et|avec|vs\.?)\s+(?:le\s+)?(\d{1,2})', re.I),
    re.compile(r'(\d{1,2})\s+vs\.?\s+(\d{1,2})', re.I),
    re.compile(r'diff[eé]rence\s+entre\s+(?:le\s+)?(\d{1,2})\s+et\s+(?:le\s+)?(\d{1,2})', re.I),
    re.compile(r'entre\s+(?:le\s+)?(\d{1,2})\s+et\s+(?:le\s+)?(\d{1,2})\s.*(?:lequel|qui)', re.I),
    re.compile(r'(?:compar|vergleich|vergelijk)\w*\b[^.?!]*?(?:du\s+|le\s+|el\s+|del\s+|o\s+|do\s+|da\s+|dos\s+|das\s+|de\s+|von\s+|van\s+)?(\d{1,2})\s+(?:et|avec|vs\.?|and|und|en|e|y)\s+(?:du\s+|le\s+|el\s+|del\s+|o\s+|do\s+|da\s+|dos\s+|das\s+|de\s+|von\s+|van\s+)?(\d{1,2})', re.I),
]


def _detect_requete_complexe_em(message: str):
    """Detecte les requetes complexes EM (thin wrapper — F06 V83)."""
    return _detect_requete_complexe_base(
        message,
        comp_re=_EM_COMP_RE,
        cat_chaud_re=_CAT_CHAUD_RE, cat_froid_re=_CAT_FROID_RE,
        freq_desc_re=_FREQ_DESC_RE, freq_asc_re=_FREQ_ASC_RE,
        ecart_desc_re=_ECART_DESC_RE, ecart_asc_re=_ECART_ASC_RE,
        secondary_query_fn=_is_star_query,
        secondary_type="etoile", primary_type="boule",
        max_primary=50, max_secondary=12,
        star_freq_re=_STAR_FREQ_RE,
    )


# ════════════════════════════════════════════════════════════
# Detect OOR EM (boule >50, etoile >12)
# ════════════════════════════════════════════════════════════

def _detect_out_of_range_em(message: str):
    """
    Detecte les numeros hors range de l'EuroMillions dans le message.
    Returns: (numero: int, context: str) ou (None, None)
    context: 'boule_high' | 'etoile_high' | 'zero_neg' | 'close'
    """
    lower = message.lower()

    # Etoile hors range (> 12)
    m = re.search(r'(?:num[eé]ro\s+)?' + _STAR_RE + r'\s+(\d+)', lower)
    if m:
        num = int(m.group(1))
        if num > 12:
            return num, "etoile_high"

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
