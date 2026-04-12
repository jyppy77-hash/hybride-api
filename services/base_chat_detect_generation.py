"""Base chat detectors — Generation detection (game-agnostic).

Phase G (generation, mode, grid count, exclusions, forced numbers).
Split from base_chat_detect_intent.py (F05 V84).
"""

import re


# ═══════════════════════════════════════════════════════
# Phase G — Détection génération de grilles (6 langues)
# ═══════════════════════════════════════════════════════

_GENERATION_PATTERN = re.compile(
    # FR
    r'g[eé]n[eè]re|g[eé]n[eé]rer|'
    r'donne[\s-]moi\s+.{0,20}(?:grille|combinaison|num[eé]ros)|'
    r'propose[\s-]moi\s+.{0,20}(?:grille|combinaison|num[eé]ros)|'
    r'cr[eé]e[\s-]moi\s+.{0,20}(?:grille|combinaison)|'
    r'fais[\s-]moi\s+.{0,20}(?:grille|combinaison)|'
    r'grille\s+.{0,15}optim|combinaison\s+.{0,15}optim|'
    r'choisis[\s-]moi\s+.{0,15}num[eé]ros|'
    r'tire[\s-]moi\s+.{0,15}num[eé]ros|'
    # FR conseil/recommandation → génération (V51)
    r'(?:que?\s+(?:me|nous)\s+)?(?:conseill|recommand)\w*.{1,30}(?:grille|num[eé]ros|euromillions?|loto)|'
    # V65 — FR donne/propose/suggère (sans -moi) + grille/numéros
    r'\bdonne\w*\s+(?:la|les|une?|des|\d+)\s+.{0,15}(?:grille|combinaison|num[eé]ros)|'
    r'\bpropose\w*\s+(?:la|les|une?|des|\d+)\s+.{0,15}(?:grille|combinaison|num[eé]ros)|'
    r'\bsugg[eè]re\w*\s+(?:la|les|une?|des|\d+)\s+.{0,15}(?:grille|combinaison|num[eé]ros)|'
    # V65 — FR vouloir/aimerais + grille/numéros
    r'\b(?:veu[xt]|voudr\w+|aimerais?)\s+.{0,30}(?:grille|num[eé]ros|combinaison)|'
    # V65 — FR bare "(une/N) grille(s)" at start of message
    r'^\s*(?:une?|\d+)\s+grilles?\b|'
    # V65 — FR "N numéros pour" (implicit demand)
    r'\b\d+\s+num[eé]ros?\s+pour\b|'
    # V65 — FR "généré" alone (participe passé, mot seul)
    r'^\s*g[eé]n[eé]r[eé]\w*[\s!.?]*$|'
    # V65 — FR quels/lequel/quoi + jouer/choisir
    r'\b(?:quels?|lequel|lesquels?|quoi)\s+(?:num[eé]ros?\s+)?(?:[àa]\s+)?(?:jouer|choisir|prendre)\b|'
    # V65 — FR jouer + grille / numéros à jouer
    r'\bjouer\b.{0,20}\bgrilles?\b|'
    r'\bnum[eé]ros?\s+(?:[àa]\s+)?jouer\b|'
    # V65 — FR "N numéro(s) et N étoile(s)" (implicit EM demand)
    r'\b\d+\s+num[eé]ros?\s+et\s+(?:\d+|une?|deux|trois)\s+[eé]toiles?\b|'
    # EN
    r'\bgenerate\b|'
    r'give\s+me\s+.{0,20}(?:grid|combination|numbers)|'
    r'create\s+.{0,20}(?:grid|combination)|'
    r'make\s+me\s+.{0,20}(?:grid|combination)|'
    r'optimized\s+grid|'
    r'pick\s+.{0,15}numbers\s+for\s+me|'
    # EN conseil (V51)
    r'what\s+(?:do\s+you\s+)?(?:recommend|suggest)|'
    # V65 — EN want/would like + grid/numbers
    r'\b(?:want|(?:would|i.?d)\s+like)\s+.{0,30}(?:grid|numbers?|combination)|'
    # V65 — EN suggest/propose (without me)
    r'\b(?:suggest|propose)\w*\s+.{0,25}(?:grid|numbers?|combination)|'
    # V65 — EN bare "a/N grid(s)" at start
    r'^\s*(?:an?|\d+)\s+grids?\b|'
    # V65 — EN N numbers for
    r'\b\d+\s+numbers?\s+for\b|'
    # V65 — EN which/what numbers to play
    r'\b(?:which|what)\s+numbers?\s+.{0,15}(?:play|pick|choose)|'
    # ES
    r'\bgenera\b|generar\b|'
    r'dame\s+.{0,20}(?:combinaci[oó]n|n[uú]meros)|'
    r'crea\s+.{0,20}combinaci[oó]n|'
    r'combinaci[oó]n\s+.{0,15}optim|'
    r'hazme\s+.{0,20}combinaci[oó]n|'
    # ES conseil (V51)
    r'(?:qu[eé]\s+(?:me\s+)?)?(?:recomiend|sugier)\w*.{1,30}(?:combinaci[oó]n|n[uú]meros|euromillions?|loto)|'
    # V65 — ES querer + combinación/números
    r'\bquier\w+\s+.{0,30}(?:combinaci[oó]n|n[uú]meros|grilla)|'
    # V65 — ES proponer/sugerir (without me)
    r'\b(?:prop[oó]n|sugier)\w*\s+.{0,25}(?:combinaci[oó]n|n[uú]meros)|'
    # V65 — ES bare combinación at start
    r'^\s*(?:una?|\d+)\s+(?:combinaci[oó]ne?s?|grillas?)\b|'
    # V65 — ES qué números jugar
    r'\bqu[eé]\s+n[uú]meros?\s+.{0,15}jugar|'
    # PT
    r'\bgera\b|\bgerar\b|\bgere\b|'
    r'd[aá][\s-]me\s+.{0,20}(?:grelhas?|combina[cç][aã]o|n[uú]meros)|'
    r'cria\s+.{0,20}(?:grelhas?|combina[cç][aã]o)|'
    r'(?:grelhas?|combina[cç][aã]o)\s+.{0,15}optim|'
    r'faz[\s-]me\s+.{0,20}(?:grelhas?|combina[cç][aã]o)|'
    # PT conseil (V51)
    r'(?:o\s+que\s+)?(?:recomend|suger)\w*.{1,30}(?:grelhas?|n[uú]meros|euromillions?|loto)|'
    # V65 — PT querer + grelha/números
    r'\bquer\w+\s+.{0,30}(?:grelha|n[uú]meros|combina[cç][aã]o)|'
    # V65 — PT propor/sugerir (without me)
    r'\b(?:prop[oõ]e?|suger)\w*\s+.{0,25}(?:grelha|n[uú]meros|combina[cç][aã]o)|'
    # V65 — PT bare grelha at start
    r'^\s*(?:uma?|\d+)\s+grelhas?\b|'
    # V65 — PT quais números jogar
    r'\bquais?\s+n[uú]meros?\s+.{0,15}jogar|'
    # DE
    r'generier|erstell\w*\s+.{0,20}(?:kombination|zahlen|gitter)|'
    r'gib\s+mir\s+.{0,20}(?:kombination|zahlen)|'
    r'erzeug\w*\s+.{0,20}kombination|'
    r'kombination\s+.{0,15}optim|'
    r'w[aä]hl\w*\s+.{0,15}zahlen|'
    # DE conseil (V51)
    r'was\s+(?:empfiehlst|empfehlen|schl[aä]gst).{1,30}(?:kombination|zahlen|euromillions?|loto)|'
    # V65 — DE möchte/hätte + Kombination/Zahlen
    r'\b(?:m[oö]chte|h[aä]tte\s+gerne?)\s+.{0,30}(?:kombination|zahlen|tippfeld)|'
    # V65 — DE bare Kombination at start
    r'^\s*(?:eine?|\d+)\s+kombination\w*\b|'
    # V65 — DE welche Zahlen spielen
    r'\bwelche\s+zahlen\s+.{0,15}spielen|'
    # NL
    r'genereer|'
    r'maak\s+.{0,20}(?:combinatie|nummers)|'
    r'geef\s+me\s+.{0,20}(?:combinatie|nummers)|'
    r'combinatie\s+.{0,15}optim|'
    r'kies\s+.{0,15}nummers|'
    # NL conseil (V51)
    r'wat\s+(?:raad|beveel)\s+je\s+aan.{1,30}(?:combinatie|nummers|euromillions?|loto)|'
    # V65 — NL wil/zou graag + combinatie/nummers
    r'\b(?:wil|zou\s+graag)\s+.{0,30}(?:combinatie|nummers)|'
    # V65 — NL bare combinatie at start
    r'^\s*(?:een|\d+)\s+combinaties?\b|'
    # V65 — NL welke nummers spelen
    r'\bwelke\s+nummers?\s+.{0,15}spelen|'
    # ────────────────────────────────────────────────────────────────────
    # V96 — "verb + (pronoun)? + digit + number keyword" (6 langs)
    # Catches: "sélectionne 5 numéros", "select 5 numbers", "pick me 5
    # numbers", "donne nous 5 numéros", "elige 5 números", etc.
    # ────────────────────────────────────────────────────────────────────
    r'\b(?:s[eé]lectionne|choisis|donne|propose|tire|fais|'
    r'select|pick|choose|give|make|'
    r'dame|elige|selecciona|haz|'
    r'd[aá]|escolhe|seleciona|faz|'
    r'gib|w[aä]hl|erstell|'
    r'geef|kies|maak)\w*'
    r'\s+(?:moi|me|nous|us|mir|uns|me)?\s*'
    r'\d+\s+(?:\w+\s+){0,3}'
    r'(?:num[eé]ros?|numbers?|n[uú]meros?|zahlen|nummers?)\b|'
    # ────────────────────────────────────────────────────────────────────
    # V96 — "the N best numbers" / "les N meilleurs numéros" (6 langs)
    # Catches: "les 5 meilleurs numéros", "the best 5 numbers",
    # "los 5 mejores números", "die 5 besten Zahlen", etc.
    # ────────────────────────────────────────────────────────────────────
    r'\b(?:les?|the|los?|os?|die|de)\s+'
    r'(?:'
    r'\d+\s+(?:\w+\s+){0,2}(?:meilleurs?|best|mejores?|melhores?|besten?|beste)\s+|'
    r'(?:meilleurs?|best|mejores?|melhores?|besten?|beste)\s+(?:\w+\s+){0,2}\d+\s+'
    r')'
    r'(?:num[eé]ros?|numbers?|n[uú]meros?|zahlen|nummers?)\b',
    re.IGNORECASE
)

# Mots-clés de contexte grille pour disambiguër
_GENERATION_CONTEXT = re.compile(
    r'grille|combinaison|grid|combination|combinaci[oó]n|combina[cç][aã]o|grelha|'
    r'kombination|combinatie|num[eé]ros|numbers|n[uú]meros|zahlen|nummers|'
    r'gitter|rooster',
    re.IGNORECASE
)

# Mots-clés de co-occurrence — excluent la detection generation (Phase P prioritaire)
_COOCCURRENCE_EXCLUSION = re.compile(
    # FR
    r'ensemble|paire|duo|associ[eé]|co.?occurrence|corr[eé]lation|accompagn|'
    # EN
    r'\btogether\b|co.?occurrence|correlation|alongside|'
    # ES
    r'\bjuntos\b|pareja|asociados|'
    # PT
    r'\bjuntos\b|dupla|associados|'
    # DE
    r'\bzusammen\b|\bpaar\b|verbunden|'
    # NL
    r'\bsamen\b|verbonden',
    re.IGNORECASE
)


def _detect_generation(message: str) -> bool:
    """Detecte si le message est une demande de generation de grille (6 langues)."""
    lower = message.lower()
    # V65 — normalize Unicode dashes (NON-BREAKING HYPHEN, EN DASH, EM DASH)
    lower = lower.replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '-').replace('\u2010', '-')
    if not _GENERATION_PATTERN.search(lower):
        return False
    # Pour les verbes courts (genera, gera, gere), exiger un contexte grille
    if re.search(r'\b(?:genera|gera|gere)\b', lower) and not _GENERATION_CONTEXT.search(lower):
        return False
    # Co-occurrence keywords → NOT generation (Phase P handles these)
    if _COOCCURRENCE_EXCLUSION.search(lower):
        return False
    return True


_MODE_PATTERN_CONSERVATIVE = re.compile(
    r'\bconservat\w+|\bprudent\w*|\bs[ûü]re?\b|\bsafe\b|\bseguro\b|\bsicher\b|\bveilig\b|\bconservador\b',
    re.IGNORECASE
)
_MODE_PATTERN_RECENT = re.compile(
    r'r[eé]cent\w*|tendance|trend|reciente|tendencia|tendência|aktuell',
    re.IGNORECASE
)


def _detect_generation_mode(message: str) -> str:
    """Extrait le mode de generation depuis le message. Retourne conservative/recent/balanced."""
    if _MODE_PATTERN_CONSERVATIVE.search(message):
        return "conservative"
    if _MODE_PATTERN_RECENT.search(message):
        return "recent"
    return "balanced"


# ── Extraction du nombre de grilles demandées (6 langues) ─────────────────

_GRID_COUNT_PATTERN = re.compile(
    r'(?:'
    # FR: "3 grilles", "donne-moi 3 grilles", "3 EuroMillions grilles"
    r'(\d+)\s+(?:\w+\s+){0,3}(?:grilles?|combinaisons?)|'
    # EN: "3 grids", "3 EuroMillions grids", "3 combinations"
    r'(\d+)\s+(?:\w+\s+){0,3}(?:grids?|combinations?)|'
    # ES: "3 cuadrículas", "3 combinaciones"
    r'(\d+)\s+(?:\w+\s+){0,3}(?:cuadr[ií]culas?|combinacion[eé]s?)|'
    # PT: "3 grelhas", "3 combinações"
    r'(\d+)\s+(?:\w+\s+){0,3}(?:grelhas?|combina[çc][õo][eé]?s?)|'
    # DE: "3 Kombinationen", "3 Gitter"
    r'(\d+)\s+(?:\w+\s+){0,3}(?:kombinationen?|gitter|raster)|'
    # NL: "3 combinaties", "3 roosters"
    r'(\d+)\s+(?:\w+\s+){0,3}(?:combinaties?|roosters?)'
    r')',
    re.IGNORECASE
)


def _extract_grid_count(message: str) -> int:
    """Extract requested number of grids from message. Default=1, cap=5."""
    m = _GRID_COUNT_PATTERN.search(message)
    if m:
        for g in m.groups():
            if g:
                count = int(g)
                return max(1, min(count, 5))
    return 1


# ── Extraction des contraintes d'exclusion (6 langues) ────────────────────

# "dates de naissance" / "birthdays" → exclude 1-31
_BIRTHDAY_PATTERN = re.compile(
    r'(?:'
    r'dates?\s+de\s+naissance|'          # FR
    r'birthdays?|birth\s+dates?|'        # EN
    r'fechas?\s+de\s+nacimiento|'        # ES
    r'datas?\s+de\s+nascimento|'         # PT
    r'geburtstag|geburtsdaten?|'         # DE
    r'verjaardag|geboortedatum'          # NL
    r')',
    re.IGNORECASE
)

# "rien entre X et Y" / "nothing between X and Y" / "nada entre X y Y" etc.
_EXCLUDE_RANGE_PATTERN = re.compile(
    r'(?:'
    r'(?:rien|pas|sans|nothing|no|not|nada|sin|sem|nichts|keine?|geen|niets)\b'
    r'[^.]{0,30}?'
    r'(?:entre|between|zwischen|tussen)\s+'
    r'(\d{1,2})\s+(?:et|and|und|en|[ey])\s+(\d{1,2})'
    r')',
    re.IGNORECASE
)

# "pas de multiples de 5" / "no multiples of 5" etc.
_EXCLUDE_MULTIPLES_PATTERN = re.compile(
    r'(?:'
    r'(?:pas\s+de|sans|no|without|sin|sem|keine?|ohne|geen|zonder)\s+'
    r'(?:multiples?\s+(?:de|of|von|van)|vielfache[n]?\s+von|veelvouden?\s+van)\s+'
    r'(\d{1,2})'
    r'(?:\s+(?:ou|or|o|e|und|of|en|ni)\s+(?:de\s+)?(\d{1,2}))?'
    r')',
    re.IGNORECASE
)

# "sans le 13" / "without 13" / "pas de 7" etc.
_EXCLUDE_NUMS_PATTERN = re.compile(
    r'(?:'
    r'pas\s+(?:de|le|la)\s+|sans\s+(?:le\s+|la\s+)?|'
    r'without\s+|no\s+|not\s+|'
    r'sin\s+(?:el\s+)?|sem\s+(?:o\s+)?|'
    r'ohne\s+(?:die\s+)?|kein\s+|'
    r'zonder\s+(?:de\s+)?|geen\s+'
    r')(\d{1,2})\b',
    re.IGNORECASE
)

# "pas de numéros entre 1 et 31" / "no numbers between 1 and 31"
_EXCLUDE_NUMS_RANGE_PATTERN = re.compile(
    r'(?:'
    r'(?:pas\s+de|sans|no|without|sin|sem|keine?|ohne|geen|zonder)\s+'
    r'(?:num[eé]ros?|numbers?|n[uú]meros?|zahlen|nummers?|boules?|balls?)\s+'
    r'(?:entre|between|zwischen|tussen)\s+'
    r'(\d{1,2})\s+(?:et|and|und|en|[ey])\s+(\d{1,2})'
    r')',
    re.IGNORECASE
)


def _extract_exclusions(message: str, max_num: int = 49) -> dict:
    """Extract exclusion constraints from generation request (6 languages).

    Args:
        message: user message to parse.
        max_num: upper bound for valid numbers (Loto=49, EM=50).

    Returns dict with:
        exclude_ranges: list of (low, high) tuples
        exclude_multiples: list of ints
        exclude_nums: list of ints
    """
    result = {"exclude_ranges": [], "exclude_multiples": [], "exclude_nums": []}

    # Birthday shortcut → exclude 1-31
    if _BIRTHDAY_PATTERN.search(message):
        result["exclude_ranges"].append((1, 31))

    # Explicit range exclusion: "rien entre X et Y"
    for m in _EXCLUDE_RANGE_PATTERN.finditer(message):
        low, high = int(m.group(1)), int(m.group(2))
        if low > high:
            low, high = high, low
        result["exclude_ranges"].append((low, high))

    # Explicit number-range exclusion: "pas de numéros entre X et Y"
    for m in _EXCLUDE_NUMS_RANGE_PATTERN.finditer(message):
        low, high = int(m.group(1)), int(m.group(2))
        if low > high:
            low, high = high, low
        result["exclude_ranges"].append((low, high))

    # Multiples exclusion: "pas de multiples de 5 ou 10"
    for m in _EXCLUDE_MULTIPLES_PATTERN.finditer(message):
        result["exclude_multiples"].append(int(m.group(1)))
        if m.group(2):
            result["exclude_multiples"].append(int(m.group(2)))

    # Specific number exclusion: "sans le 13"
    for m in _EXCLUDE_NUMS_PATTERN.finditer(message):
        num = int(m.group(1))
        if 1 <= num <= max_num:
            result["exclude_nums"].append(num)

    # Deduplicate
    result["exclude_ranges"] = list(set(result["exclude_ranges"]))
    result["exclude_multiples"] = list(set(result["exclude_multiples"]))
    result["exclude_nums"] = list(set(result["exclude_nums"]))

    return result


# ── Extraction des numéros imposés (6 langues) ────────────────────────────

# Patterns pour "numéro chance" / "lucky number" / etc. (before main number extraction)
_CHANCE_PATTERN = re.compile(
    r'(?:'
    # FR
    r'(?:num[eé]ro\s+)?chance\s*[=:]*\s*(\d{1,2})|'
    r'(\d{1,2})\s+en\s+chance|'
    # EN
    r'lucky\s+(?:number\s+)?(\d{1,2})|'
    r'(\d{1,2})\s+(?:as\s+)?lucky|'
    # ES
    r'(?:n[uú]mero\s+)?suerte\s*[=:]*\s*(\d{1,2})|'
    r'(\d{1,2})\s+de\s+suerte|'
    # PT
    r'(?:n[uú]mero\s+)?sorte\s*[=:]*\s*(\d{1,2})|'
    r'(\d{1,2})\s+de\s+sorte|'
    # DE
    r'gl[üu]cks(?:zahl)?\s*[=:]*\s*(\d{1,2})|'
    r'(\d{1,2})\s+als\s+gl[üu]cks|'
    # NL
    r'geluk(?:snummer)?\s*[=:]*\s*(\d{1,2})|'
    r'(\d{1,2})\s+als\s+geluk'
    r')',
    re.IGNORECASE
)

# Patterns for "étoile" / "star" / "estrella" / "Stern" / "ster"
# Captures everything after the keyword to extract all numbers
_STAR_PATTERN = re.compile(
    r'(?:[eé]toiles?|stars?|estrellas?|estrelas?|stern[e]?|ster(?:ren)?)'
    r'\s*[=:]*\s*'
    r'([\d\s,et&\+andyeundnl]+)',
    re.IGNORECASE
)

# "avec" / "with" / "con" / "com" / "mit" / "met" — triggers forced-number extraction
_WITH_PATTERN = re.compile(
    r'\b(?:avec|with|con\b|com\b|mit\b|met\b|incluant|including|contenant|contendo|'
    r'f[eé]tiche|favoris?|lucky|preferidos?|lieblings|favoriet)',
    re.IGNORECASE
)

# Quantifier patterns that look like forced numbers but are actually counts
# e.g. "les 2 dedans" = "both of them inside", NOT "force number 2"
_QUANTIFIER_PATTERN = re.compile(
    r'\b(?:les|los|os|die|de|the|those|ces)\s+(\d{1,2})\s+'
    r'(?:dedans|inclus|inside|included|dentro|incluidos?|incluídos?|'
    r'drin|dabei|drinnen|erin|inbegrepen|mee)\b',
    re.IGNORECASE
)


def _extract_nums_from_text(text: str) -> list[int]:
    """Extract all integers from a text fragment."""
    return [int(x) for x in re.findall(r'\b(\d{1,2})\b', text)]


def _extract_forced_numbers(message: str, game: str = "loto") -> dict:
    """Extract forced numbers from a generation request (6 languages).

    Args:
        message: User message
        game: "loto" or "em"

    Returns:
        dict with keys:
            forced_nums: list[int] — main numbers to force
            forced_chance: int|None — forced chance number (Loto only)
            forced_etoiles: list[int] — forced stars (EM only)
            error: str|None — error message if validation fails
    """
    result = {"forced_nums": [], "forced_chance": None, "forced_etoiles": [], "error": None}

    # Must contain a "with" keyword to trigger forced-number extraction
    if not _WITH_PATTERN.search(message):
        return result

    lower = message.lower()

    # ── Step 1: Extract chance number (Loto) ──
    if game == "loto":
        m = _CHANCE_PATTERN.search(lower)
        if m:
            # First non-None group is the chance number
            chance_str = next((g for g in m.groups() if g is not None), None)
            if chance_str:
                chance_val = int(chance_str)
                if 1 <= chance_val <= 10:
                    result["forced_chance"] = chance_val
                else:
                    result["error"] = f"Numéro chance hors plage (1-10) : {chance_val}"
                    return result

    # ── Step 2: Extract star numbers (EM) ──
    if game == "em":
        m = _STAR_PATTERN.search(lower)
        if m:
            star_str = next((g for g in m.groups() if g is not None), None)
            if star_str:
                star_nums = _extract_nums_from_text(star_str)
                for s in star_nums:
                    if s < 1 or s > 12:
                        result["error"] = f"Étoile hors plage (1-12) : {s}"
                        return result
                if len(star_nums) > 2:
                    result["error"] = f"Maximum 2 étoiles imposées, {len(star_nums)} demandées"
                    return result
                result["forced_etoiles"] = star_nums

    # ── Step 3: Extract main numbers ──
    # Remove chance/star segments to avoid double-counting
    cleaned = lower
    for pattern in (_CHANCE_PATTERN, _STAR_PATTERN):
        cleaned = pattern.sub(' ', cleaned)

    # Detect quantifier patterns ("les 2 dedans", "those 3 included")
    # and resolve anaphoric references to numbers mentioned earlier
    _quant_match = _QUANTIFIER_PATTERN.search(cleaned)
    _quant_n = int(_quant_match.group(1)) if _quant_match else 0
    cleaned = _QUANTIFIER_PATTERN.sub(' ', cleaned)

    # Find the "with" keyword position and extract numbers after it
    with_match = _WITH_PATTERN.search(cleaned)
    if with_match:
        after_with = cleaned[with_match.start():]
        forced = _extract_nums_from_text(after_with)
    else:
        forced = []

    # ── Anaphora resolution ──
    # If a quantifier was detected ("les 2 dedans") but no explicit numbers
    # found after "avec", scan the FULL message for numbers mentioned earlier
    # and use up to N of them (N = the quantifier count).
    if _quant_n > 0 and not forced:
        all_nums = _extract_nums_from_text(cleaned)
        # Filter to valid game range to avoid picking up years, counts, etc.
        if game == "loto":
            candidates = [n for n in all_nums if 1 <= n <= 49]
        else:
            candidates = [n for n in all_nums if 1 <= n <= 50]
        # Deduplicate preserving order
        seen = set()
        unique = []
        for n in candidates:
            if n not in seen:
                seen.add(n)
                unique.append(n)
        forced = unique[:_quant_n]

    # Validate range
    if game == "loto":
        max_num, max_count = 49, 5
    else:
        max_num, max_count = 50, 5

    valid_forced = []
    for n in forced:
        if n < 1 or n > max_num:
            result["error"] = f"Numéro hors plage (1-{max_num}) : {n}"
            return result
        if n not in valid_forced:
            valid_forced.append(n)

    if len(valid_forced) > max_count:
        result["error"] = (
            f"Maximum {max_count} numéros imposés, {len(valid_forced)} demandés"
        )
        return result

    # For Loto: if a forced chance number was extracted, don't include it in main nums
    if game == "loto" and result["forced_chance"] and result["forced_chance"] in valid_forced:
        valid_forced.remove(result["forced_chance"])

    result["forced_nums"] = valid_forced
    return result
