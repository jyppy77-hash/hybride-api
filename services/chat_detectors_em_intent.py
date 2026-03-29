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
# ════════════════════════════════════════════════════════════

def _detect_requete_complexe_em(message: str):
    """
    Detecte les requetes complexes EM : classements, comparaisons, categories.
    Returns: dict d'intention ou None.
    """
    lower = message.lower()

    # --- Comparaison ---
    comp_patterns = [
        r'compar\w*\s+(?:le\s+)?(\d{1,2})\s+(?:et|avec|vs\.?)\s+(?:le\s+)?(\d{1,2})',
        r'(\d{1,2})\s+vs\.?\s+(\d{1,2})',
        r'diff[eé]rence\s+entre\s+(?:le\s+)?(\d{1,2})\s+et\s+(?:le\s+)?(\d{1,2})',
        r'entre\s+(?:le\s+)?(\d{1,2})\s+et\s+(?:le\s+)?(\d{1,2})\s.*(?:lequel|qui)',
        # Multilang flexible : "compare la fréquence du 31 et du 24", "compare 12 and 45",
        # "compara o 31 e o 24", "vergleiche 31 und 24", "vergelijk 31 en 23"
        r'(?:compar|vergleich|vergelijk)\w*\b[^.?!]*?(?:du\s+|le\s+|el\s+|del\s+|o\s+|do\s+|da\s+|dos\s+|das\s+|de\s+|von\s+|van\s+)?(\d{1,2})\s+(?:et|avec|vs\.?|and|und|en|e|y)\s+(?:du\s+|le\s+|el\s+|del\s+|o\s+|do\s+|da\s+|dos\s+|das\s+|de\s+|von\s+|van\s+)?(\d{1,2})',
    ]
    for pat in comp_patterns:
        m = re.search(pat, lower)
        if m:
            n1, n2 = int(m.group(1)), int(m.group(2))
            is_etoile = _is_star_query(lower)
            if is_etoile and 1 <= n1 <= 12 and 1 <= n2 <= 12:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "etoile"}
            if 1 <= n1 <= 50 and 1 <= n2 <= 50 and n1 != n2:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "boule"}

    # --- Categorie chaud/froid ---
    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*chauds?', lower) or \
       re.search(r'chauds?\s+(?:en ce moment|actuellement|du moment)', lower) or \
       re.search(r'(?:num[eé]ros?|lesquels)\s+(?:sont|en)\s+tendance', lower) or \
       re.search(r'(?:num[eé]ros?|num[eé]ro\s*stars?)\s+du\s+moment', lower) or \
       re.search(r'\bdu\s+moment\b.*(?:num[eé]ro|boule|[eé]toile|star)', lower) or \
       re.search(r'(?:num[eé]ros?|num[eé]ro\s*stars?|boules?|[eé]toiles?)\s+(?:en\s+ce\s+moment|actuellement)', lower) or \
       re.search(r'\b(?:hot|hottest)\s+numbers?\b', lower) or \
       re.search(r'\bnumbers?\s+(?:on\s+a\s+)?(?:hot\s+streak|trending|right\s+now)\b', lower) or \
       re.search(r'\bn[uú]meros?\s+calientes?\b', lower) or \
       re.search(r'\bn[uú]meros?\s+(?:del\s+momento|de\s+moda)\b', lower) or \
       re.search(r'\bn[uú]meros?\s+quentes?\b', lower) or \
       re.search(r'\bn[uú]meros?\s+do\s+momento\b', lower) or \
       re.search(r'\bhei[sß]e\s+zahlen\b', lower) or \
       re.search(r'\baktuell\w*\s+zahlen\b', lower) or \
       re.search(r'\bhete\s+nummers\b', lower) or \
       re.search(r'\bnummers\s+van\s+(?:het\s+)?moment\b', lower):
        num_type = "etoile" if _is_star_query(lower) else "boule"
        return {"type": "categorie", "categorie": "chaud", "num_type": num_type}

    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*froids?', lower) or \
       re.search(r'froids?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'num[eé]ros?\s+(?:en\s+retard|qui\s+sort\w*\s+(?:pas|plus|jamais))', lower) or \
       re.search(r'\b(?:cold|coldest)\s+numbers?\b', lower) or \
       re.search(r'\bnumbers?\s+(?:overdue|not\s+drawn)\b', lower) or \
       re.search(r'\bn[uú]meros?\s+fr[ií]os?\b', lower) or \
       re.search(r'\bkalte\s+zahlen\b', lower) or \
       re.search(r'\bkoude\s+nummers\b', lower):
        num_type = "etoile" if _is_star_query(lower) else "boule"
        return {"type": "categorie", "categorie": "froid", "num_type": num_type}

    # --- Classement ---
    limit = _extract_top_n(lower)

    _star_kw = _is_star_query(lower)
    num_type = "etoile" if _star_kw else "boule"

    # --- Requêtes directes étoiles + fréquence (6 langues) ---
    if _star_kw and (
        re.search(r'(?:sort\w*|tir[eé]\w*|apparai)\w*\s+le\s+plus', lower) or
        re.search(r'(?:come|drawn|appear)\w*\s+(?:out\s+)?(?:the\s+)?most', lower) or
        re.search(r'(?:plus|most|m[aá]s|mais|meist|meest)\s+(?:fr[eé]quent|sorti|drawn|frecuent|frequent|getrokken|gezogen)', lower) or
        re.search(r'(?:sort\w*|sal\w*|saem|sair|gezogen|getrokken)\w*\s+(?:le\s+plus|the\s+most|m[aá]s|mais|am\s+meisten|het\s+meest)', lower) or
        re.search(r'(?:quell?e?s?|which|cu[aá]le?s?|quais|welche|welke)\b', lower) or
        re.search(r'(?:class\w+|rank|top|fr[eé]quenc|frequenc|h[aä]ufig|vaak)', lower)
    ):
        return {"type": "classement", "tri": "frequence_desc", "limit": limit, "num_type": "etoile"}

    if re.search(r'(?:plus|les?\s+plus)\s+(?:fr[eé]quent|sorti|courant|pr[eé]sent)', lower) or \
       re.search(r'(?:top|meilleur|premier)\s+\d{0,2}\s*(?:num[eé]ro|boule|[eé]toile)?', lower) or \
       re.search(r'num[eé]ros?\s+(?:les?\s+)?plus\s+(?:sorti|fr[eé]quent)', lower) or \
       re.search(r'(?:quels?|quel)\s+(?:est|sont)\s+(?:le|les)\s+num[eé]ro', lower) or \
       re.search(r'\b(?:most\s+(?:drawn|common|frequent)|most\s+often|hottest)\b', lower) or \
       re.search(r'\bm[aá]s\s+(?:sorteados?|frecuentes?|comunes?)\b', lower) or \
       re.search(r'\bmais\s+(?:sorteados?|frequentes?|comuns?)\b', lower) or \
       re.search(r'\b(?:am\s+h[aä]ufigsten|h[aä]ufigsten?\s+gezogen|meistgezogen)\b', lower) or \
       re.search(r'\b(?:meest\s+getrokken|meest\s+voorkomend|vaakst\s+getrokken|vaakst\s+voor)\b', lower) or \
       re.search(r'\branking\b|\brangliste\b|\branglijst\b|\bclasificaci[oó]n\b|\bclassifica[çc][aã]o\b', lower):
        return {"type": "classement", "tri": "frequence_desc", "limit": limit, "num_type": num_type}

    if re.search(r'(?:moins|les?\s+moins)\s+(?:fr[eé]quent|sorti|courant)', lower) or \
       re.search(r'(?:flop|dernier|pire)\s+\d{0,2}', lower) or \
       re.search(r'\b(?:least\s+(?:drawn|common|frequent)|coldest)\b', lower) or \
       re.search(r'\bmenos\s+(?:sorteados?|frecuentes?|comunes?)\b', lower) or \
       re.search(r'\bmenos\s+(?:sorteados?|frequentes?|comuns?)\b', lower) or \
       re.search(r'\b(?:am\s+seltensten|seltensten?\s+gezogen|wenigsten?\s+gezogen)\b', lower) or \
       re.search(r'\b(?:minst\s+getrokken|minst\s+voorkomend)\b', lower):
        return {"type": "classement", "tri": "frequence_asc", "limit": limit, "num_type": num_type}

    if re.search(r'(?:plus\s+(?:gros|grand|long)|plus\s+en)\s+(?:[eé]cart|retard)', lower) or \
       re.search(r'(?:[eé]cart|retard)\s+(?:les?\s+)?plus\s+(?:gros|grand|long|important)', lower) or \
       re.search(r'(?:plus\s+(?:long|grand)temps?)\s+(?:sans\s+)?sort', lower) or \
       re.search(r'\b(?:largest|biggest|longest)\s+(?:gap|delay)\b', lower) or \
       re.search(r'\bmayor\s+(?:retraso|intervalo)\b', lower) or \
       re.search(r'\bmaior\s+(?:atraso|intervalo)\b', lower) or \
       re.search(r'\bgr[oö][sß]te[rn]?\s+(?:abstand|verz[oö]gerung)\b', lower) or \
       re.search(r'\bl[aä]ngste[rn]?\s+(?:abstand|verz[oö]gerung)\b', lower) or \
       re.search(r'\bgrootste\s+(?:achterstand|vertraging)\b', lower) or \
       re.search(r'\blangste\s+(?:achterstand|vertraging)\b', lower):
        return {"type": "classement", "tri": "ecart_desc", "limit": limit, "num_type": num_type}

    if re.search(r'(?:plus\s+(?:petit|court))\s+(?:[eé]cart|retard)', lower) or \
       re.search(r'(?:sorti|apparu)\s+(?:le\s+plus\s+)?r[eé]cemment', lower) or \
       re.search(r'\b(?:smallest|shortest)\s+(?:gap|delay)\b', lower) or \
       re.search(r'\bmenor\s+(?:retraso|intervalo)\b', lower) or \
       re.search(r'\bmenor\s+(?:atraso|intervalo)\b', lower) or \
       re.search(r'\bkleinste[rn]?\s+(?:abstand|verz[oö]gerung)\b', lower) or \
       re.search(r'\bk[uü]rzeste[rn]?\s+(?:abstand|verz[oö]gerung)\b', lower) or \
       re.search(r'\bkleinste\s+(?:achterstand|vertraging)\b', lower) or \
       re.search(r'\bkortste\s+(?:achterstand|vertraging)\b', lower):
        return {"type": "classement", "tri": "ecart_asc", "limit": limit, "num_type": num_type}

    return None


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
