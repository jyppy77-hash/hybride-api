"""Base chat detectors — Correlation & ranking detection (game-agnostic).
Phase 3 (complex queries), Phase P (pairs/triplets), Phase P+ (co-occurrence N>3).
Split from base_chat_detect_intent.py (F05 V84)."""

import re
import random


# ────────────────────────────────────────────
# Phase 3 : Detection requete complexe
# ────────────────────────────────────────────

_TOP_N_PATTERNS = [
    r'\btop\s+(\d{1,2})\b',
    # FR: "les 10 plus", "les 10 premiers"
    r'\bles\s+(\d{1,2})\s+(?:plus|premiers?|derniers?|num[eé]ros?)\b',
    # EN: "the 10 most", "the 10 least"
    r'\bthe\s+(\d{1,2})\s+(?:most|least|numbers?)\b',
    # ES: "los 10 más", "los 10 números"
    r'\blos\s+(\d{1,2})\s+(?:m[aá]s|menos|n[uú]meros?)\b',
    # PT: "os 10 mais", "os 10 números"
    r'\bos\s+(\d{1,2})\s+(?:mais|menos|n[uú]meros?)\b',
    # DE: "die 10 häufigsten", "die 10 Zahlen"
    r'\bdie\s+(\d{1,2})\s+(?:h[aä]ufigsten|meisten|gr[oö][sß]ten|kleinsten|Zahlen)\b',
    # NL: "de 10 meest", "de 10 nummers"
    r'\bde\s+(\d{1,2})\s+(?:meest|minst|grootste|kleinste|nummers?)\b',
    # "donne-moi 10" / "give me 10" / "dame 10" / "dá-me 10" / "gib mir 10" / "geef me 10"
    r'\b(?:donne|give|dame|d[aá][\s-]me|gib|geef)[\w\s-]{0,10}?(\d{1,2})\b',
    # "10 numéros" / "10 numbers" / "10 números" / "10 Zahlen" / "10 nummers"
    r'\b(\d{1,2})\s+(?:num[eé]ros?|numbers?|n[uú]meros?|Zahlen|nummers?)\b',
]


def _extract_top_n(message: str, default: int = 5, max_n: int = 20) -> int:
    """Extract the requested top N from a message (multilingual). Default 5, max 20."""
    for pat in _TOP_N_PATTERNS:
        m = re.search(pat, message, re.IGNORECASE)
        if m:
            n = int(m.group(1))
            if 1 <= n <= max_n:
                return n
    return default


# ═══════════════════════════════════════════════════════
# Phase 3 — Base requête complexe (shared Loto + EM)
# F06 V83: factorised from chat_detectors + chat_detectors_em_intent
# ═══════════════════════════════════════════════════════

def _detect_requete_complexe_base(
    message: str, *,
    comp_re: list,
    cat_chaud_re: list,
    cat_froid_re: list,
    freq_desc_re: list,
    freq_asc_re: list,
    ecart_desc_re: list,
    ecart_asc_re: list,
    secondary_query_fn,
    secondary_type: str,
    primary_type: str,
    max_primary: int,
    max_secondary: int,
    star_freq_re: list | None = None,
) -> dict | None:
    """Detect complex queries: rankings, comparisons, hot/cold categories.

    Args:
        comp_re: compiled comparison patterns (each must capture 2 groups: num1, num2).
        cat_chaud_re / cat_froid_re: compiled hot/cold category patterns.
        freq_desc_re / freq_asc_re: compiled frequency ranking patterns.
        ecart_desc_re / ecart_asc_re: compiled gap ranking patterns.
        secondary_query_fn: callable(lower) → bool (e.g. _is_chance_query, _is_star_query).
        secondary_type: num_type for secondary numbers ("chance" or "etoile").
        primary_type: num_type for primary numbers ("principal" or "boule").
        max_primary: upper bound for primary numbers (49 Loto, 50 EM).
        max_secondary: upper bound for secondary numbers (10 Loto chance, 12 EM stars).
        star_freq_re: optional extra patterns for star-specific frequency (EM only).
    """
    lower = message.lower()

    # --- Comparaison ---
    for pat in comp_re:
        m = pat.search(lower)
        if m:
            n1, n2 = int(m.group(1)), int(m.group(2))
            is_secondary = secondary_query_fn(lower)
            if is_secondary and 1 <= n1 <= max_secondary and 1 <= n2 <= max_secondary:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": secondary_type}
            if 1 <= n1 <= max_primary and 1 <= n2 <= max_primary and n1 != n2:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": primary_type}

    # --- Catégorie chaud/froid ---
    if any(p.search(lower) for p in cat_chaud_re):
        num_type = secondary_type if secondary_query_fn(lower) else primary_type
        return {"type": "categorie", "categorie": "chaud", "num_type": num_type}

    if any(p.search(lower) for p in cat_froid_re):
        num_type = secondary_type if secondary_query_fn(lower) else primary_type
        return {"type": "categorie", "categorie": "froid", "num_type": num_type}

    # --- Classement ---
    limit = _extract_top_n(lower)
    is_secondary = secondary_query_fn(lower)
    num_type = secondary_type if is_secondary else primary_type

    # Star-specific frequency shortcut (EM only)
    if star_freq_re and is_secondary and any(p.search(lower) for p in star_freq_re):
        return {"type": "classement", "tri": "frequence_desc", "limit": limit, "num_type": secondary_type}

    if any(p.search(lower) for p in freq_desc_re):
        return {"type": "classement", "tri": "frequence_desc", "limit": limit, "num_type": num_type}

    if any(p.search(lower) for p in freq_asc_re):
        return {"type": "classement", "tri": "frequence_asc", "limit": limit, "num_type": num_type}

    if any(p.search(lower) for p in ecart_desc_re):
        return {"type": "classement", "tri": "ecart_desc", "limit": limit, "num_type": num_type}

    if any(p.search(lower) for p in ecart_asc_re):
        return {"type": "classement", "tri": "ecart_asc", "limit": limit, "num_type": num_type}

    return None


# ═══════════════════════════════════════════════════════
# Phase P — Détection paires / corrélations (6 langues)
# ═══════════════════════════════════════════════════════

_PAIRS_PATTERN = re.compile(
    # FR — termes techniques
    r'paires?|duo|ensemble|associ[eé]|combinaison.*fr[eé]quent|sortent.*ensemble|'
    r'num[eé]ros.*li[eé]s|co.?occurrence|corr[eé]lation|'
    # FR — formulations naturelles
    r'sort\w*\s+.*avec|avec\s+le\s+\d|accompagn|v(?:a|ont)\s+avec|[àa]\s+c[oô]t[eé]\s+du?\s+\d|'
    # EN — termes techniques
    r'\bpairs?\b|together|associated|combination.*frequent|numbers.*linked|co.?occurrence|correlation|'
    # EN — formulations naturelles
    r'comes?\s+with|goes?\s+with|alongside|appears?\s+next\s+to|'
    # ES — termes techniques + naturels
    r'parejas?|pares|juntos|asociados|combinaci[oó]n.*frecuente|'
    r'sale[ns]?\s+con|junto\s+(?:con|al)|acompa[ñn]a|'
    # PT — termes techniques + naturels
    r'duplas?|pares|associados|combina[çc][aã]o.*frequente|'
    r'sa(?:i|em)\s+com|junto\s+(?:com|ao)|acompanha|'
    # DE — termes techniques + naturels
    r'\bpaare?\b|zusammen|verbunden|kombination.*h[aä]ufig|'
    r'kommt?\s+.*\bmit\b|zusammen\s+mit|neben\s+de[rn]?\s+\d|begleitet|'
    # NL — termes techniques + naturels
    r'\bparen\b|\bsamen\b|verbonden|combinatie.*frequent|'
    r'komt?\s+.*\bmet\b|samen\s+met|naast\s+de?\s+\d|begeleidt',
    re.IGNORECASE
)


_EVEN_ODD_RE = re.compile(
    r'pairs?\s*(?:et|ou|/|)\s*impairs?|impairs?\s*(?:et|ou|/|)\s*pairs?'  # FR: "pairs et impairs", "pair/impair", "pairs impairs"
    r'|even\s+(?:and|or|/)\s+odd|odd\s+(?:and|or|/)\s+even'              # EN
    r'|pares?\s*(?:[ey]\s+)?[ií]mpares?|[ií]mpares?\s*(?:[ey]\s+)?pares?'  # ES/PT
    r'|gerade\s+(?:und|oder|/)\s+ungerade|ungerade\s+(?:und|oder|/)\s+gerade'  # DE
    r'|even\s+(?:en|of|/)\s+oneven|oneven\s+(?:en|of|/)\s+even',        # NL
    re.IGNORECASE,
)


def _detect_paires(message: str) -> bool:
    """Detecte si l'utilisateur demande les correlations de paires (6 langues)."""
    if _EVEN_ODD_RE.search(message):
        return False
    return bool(_PAIRS_PATTERN.search(message))


# ═══════════════════════════════════════════════════════
# Phase P — Détection triplets / corrélations de 3 (6 langues)
# ═══════════════════════════════════════════════════════

_TRIPLETS_PATTERN = re.compile(
    # FR — triplet, trio(s), combinaison de 3, 3 numéros ensemble
    r'triplet|trio(?:s|\b)|combinaison\s+de\s+3|3\s+num[eé]ros\s+ensemble|'
    r'sortent\s+ensemble.*\b3\b|group(?:e|ement)\s+de\s+3|'
    r'3\s+boules?\s+ensemble|trois\s+num[eé]ros|'
    # EN — triplet, combination of 3, 3 numbers together
    r'triplet|combination\s+of\s+3|3\s+numbers?\s+together|'
    r'group\s+of\s+3|three\s+numbers?|'
    # ES — triplete, trío(s), combinación de 3
    r'triplete|tr[ií]o(?:s|\b)|combinaci[oó]n\s+de\s+3|3\s+n[uú]meros?\s+juntos|'
    r'tres\s+n[uú]meros|'
    # PT — tripleto, trio, combinação de 3
    r'tripleto|combina[çc][aã]o\s+de\s+3|3\s+n[uú]meros?\s+juntos|'
    r'tr[eê]s\s+n[uú]meros|'
    # DE — Triplett, Dreiergruppe, Kombination von 3
    r'triplett|dreiergruppe|kombination\s+von\s+3|3\s+zahlen\s+zusammen|'
    r'drei\s+zahlen|'
    # NL — triplet, drietal, combinatie van 3
    r'drietal|combinatie\s+van\s+3|3\s+nummers?\s+samen|'
    r'drie\s+nummers',
    re.IGNORECASE
)


def _detect_triplets(message: str) -> bool:
    """Detecte si l'utilisateur demande les correlations de triplets (6 langues)."""
    return bool(_TRIPLETS_PATTERN.search(message))


# ═══════════════════════════════════════════════════════
# Phase P+ — Détection co-occurrences N>3 (4+, 5+ numéros ensemble)
# Redirige vers paires/triplets avec réponse honnête
# ═══════════════════════════════════════════════════════

_COOCCURRENCE_HIGH_N_PATTERN = re.compile(
    # FR — "4/5/6/7 numéros ensemble", "4 numéros qui sortent ensemble", "quadruplet"
    r'(?:[4-9]|1[0-9])\s+num[eé]ros?\s+(?:ensemble|qui\s+sort)|'
    r'(?:[4-9]|1[0-9])\s+num[eé]ros?\s+.{0,30}ensemble|'
    r'(?:[4-9]|1[0-9])\s+boules?\s+(?:ensemble|qui\s+sort)|'
    r'(?:[4-9]|1[0-9])\s+boules?\s+.{0,30}ensemble|'
    r'quadruplet|quintuplet|'
    r'combinaison\s+de\s+(?:[4-9]|1[0-9])|'
    r'group(?:e|ement)\s+de\s+(?:[4-9]|1[0-9])|'
    # EN — "4/5 numbers together", "5 numbers that come together", "quadruplet"
    r'(?:[4-9]|1[0-9])\s+numbers?\s+(?:together|that\s+c(?:o|a)me)|'
    r'(?:[4-9]|1[0-9])\s+numbers?\s+.{0,30}together|'
    r'combination\s+of\s+(?:[4-9]|1[0-9])|'
    r'group\s+of\s+(?:[4-9]|1[0-9])|'
    # ES — "4/5 números juntos"
    r'(?:[4-9]|1[0-9])\s+n[uú]meros?\s+(?:juntos|.{0,30}juntos)|'
    r'combinaci[oó]n\s+de\s+(?:[4-9]|1[0-9])|'
    # PT — "4/5 números juntos"
    r'(?:[4-9]|1[0-9])\s+n[uú]meros?\s+(?:juntos|.{0,30}juntos)|'
    r'combina[çc][aã]o\s+de\s+(?:[4-9]|1[0-9])|'
    # DE — "4/5 Zahlen zusammen"
    r'(?:[4-9]|1[0-9])\s+zahlen\s+(?:zusammen|.{0,30}zusammen)|'
    r'kombination\s+von\s+(?:[4-9]|1[0-9])|'
    # NL — "4/5 nummers samen"
    r'(?:[4-9]|1[0-9])\s+nummers?\s+(?:samen|.{0,30}samen)|'
    r'combinatie\s+van\s+(?:[4-9]|1[0-9])',
    re.IGNORECASE
)


# Pattern de classement/ranking — exclut les faux positifs co-occurrence
_RANKING_EXCLUSION_PATTERN = re.compile(
    r'(?:top|meilleur|premier|classement|ranking|'
    r'plus\s+fr[eé]quent\w*|plus\s+sorti\w*|plus\s+souvent|'
    r'moins\s+fr[eé]quent\w*|moins\s+sorti\w*|'
    r'les?\s+plus\s+(?:sorti\w*|fr[eé]quent\w*)|les?\s+moins\s+(?:sorti\w*|fr[eé]quent\w*)|'
    r'most\s+(?:drawn|common|frequent\w*|often)|least\s+(?:drawn|common|frequent\w*)|'
    r'm[aá]s\s+(?:frecuent\w*|sorteado\w*|comun\w*)|menos\s+(?:frecuent\w*|sorteado\w*)|'
    r'mais\s+(?:frequent\w*|sorteado\w*|comun\w*)|menos\s+(?:frequent\w*|sorteado\w*)|'
    r'h[aä]ufigst\w*|seltenst\w*|meistgezogen|'
    r'meest\s+(?:getrokken|voorkomend\w*)|minst\s+(?:getrokken|voorkomend\w*)|'
    r'vaakst\s+(?:getrokken|voor))',
    re.IGNORECASE
)


# Mots explicites de co-occurrence (ensemble/together/quadruplet...)
_COOCCURRENCE_EXPLICIT_PATTERN = re.compile(
    r'\b(?:ensemble|together|juntos|zusammen|samen|'
    r'quadruplets?|quintuplets?|groupements?)\b',
    re.IGNORECASE
)


def _detect_cooccurrence_high_n(message: str) -> bool:
    """Detecte les demandes de co-occurrences N>3 (quadruplets, quintuplets, etc.).
    Exclut les demandes de classement/ranking (ex: 'top 5 numéros les plus fréquents')
    qui doivent être traitées par Phase 3, SAUF si le message contient un mot
    explicite de co-occurrence (ensemble/together/quadruplet...)."""
    if not _COOCCURRENCE_HIGH_N_PATTERN.search(message):
        return False
    # Si ranking keywords SANS mots explicites de co-occurrence → Phase 3
    if _RANKING_EXCLUSION_PATTERN.search(message) and not _COOCCURRENCE_EXPLICIT_PATTERN.search(message):
        return False
    return True


# Réponses honnêtes "pas encore implémenté" — redirige vers paires/triplets
_COOCCURRENCE_HIGH_N_RESPONSES = {
    "fr": [
        "📊 Je n'ai pas encore l'analyse des combinaisons de {n} numéros, mais je peux te montrer les **paires** (2 numéros) ou les **triplets** (3 numéros) les plus fréquents ! Tu veux voir ?",
        "🔢 Les co-occurrences de {n} numéros ne sont pas disponibles pour le moment. Par contre, j'ai les **paires** et les **triplets** les plus fréquents dans la base — ça t'intéresse ?",
    ],
    "en": [
        "📊 I don't have {n}-number combination analysis yet, but I can show you the most frequent **pairs** (2 numbers) or **triplets** (3 numbers)! Want to see?",
        "🔢 Co-occurrences of {n} numbers aren't available yet. However, I do have the most frequent **pairs** and **triplets** from the database — interested?",
    ],
    "es": [
        "📊 Aún no tengo el análisis de combinaciones de {n} números, pero puedo mostrarte los **pares** (2 números) o **tripletes** (3 números) más frecuentes. ¿Te interesa?",
        "🔢 Las co-ocurrencias de {n} números no están disponibles de momento. Pero tengo los **pares** y **tripletes** más frecuentes en la base de datos. ¿Quieres ver?",
    ],
    "pt": [
        "📊 Ainda não tenho a análise de combinações de {n} números, mas posso mostrar-te os **pares** (2 números) ou **tripletos** (3 números) mais frequentes! Queres ver?",
        "🔢 As co-ocorrências de {n} números ainda não estão disponíveis. Mas tenho os **pares** e **tripletos** mais frequentes na base de dados — interessa-te?",
    ],
    "de": [
        "📊 Die Analyse von {n}-Zahlen-Kombinationen habe ich noch nicht, aber ich kann dir die häufigsten **Paare** (2 Zahlen) oder **Drillinge** (3 Zahlen) zeigen! Interesse?",
        "🔢 Co-Vorkommen von {n} Zahlen sind derzeit nicht verfügbar. Aber ich habe die häufigsten **Paare** und **Drillinge** in der Datenbank — interessiert?",
    ],
    "nl": [
        "📊 Ik heb nog geen analyse van combinaties van {n} nummers, maar ik kan je de meest voorkomende **paren** (2 nummers) of **drietallen** (3 nummers) tonen! Interesse?",
        "🔢 Co-voorkomens van {n} nummers zijn momenteel niet beschikbaar. Maar ik heb de meest voorkomende **paren** en **drietallen** in de database — interesse?",
    ],
}


def _get_cooccurrence_high_n_response(message: str, lang: str = "fr") -> str:
    """Retourne une reponse honnete pour les co-occurrences N>3."""
    # Extraire N du message
    m = re.search(r'(\d+)\s+(?:num[eé]ros?|numbers?|n[uú]meros?|zahlen|nummers?|boules?)', message, re.IGNORECASE)
    n = int(m.group(1)) if m else 5
    pool = _COOCCURRENCE_HIGH_N_RESPONSES.get(lang, _COOCCURRENCE_HIGH_N_RESPONSES["fr"])
    return random.choice(pool).format(n=n)
