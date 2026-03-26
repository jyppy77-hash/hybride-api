"""
Base chat detectors — shared regex, constants, and detection functions.
Game-agnostic detection logic used by both Loto and EuroMillions pipelines.
Game-specific detectors stay in wrappers (chat_detectors.py / chat_detectors_em.py).
"""

import re
import random
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────
# Phase 0 : Continuation contextuelle
# Intercepte les réponses courtes (oui/non/ok...) et les enrichit
# avec le contexte conversationnel pour éviter les dérives Gemini.
# ────────────────────────────────────────────

CONTINUATION_PATTERNS = re.compile(
    r'^(oui|ouais|yes|yeah|yep|ok|d\'accord|vas-y|vas\s*y|go|montre|'
    r'montre-moi|montre[\s-]?moi[\s-]?(?:les|ça|ca|tout)?|'
    r'montre[\s-]?les|vas[\s-]?y[\s-]?montre[\s-]?(?:les|moi)?|'
    r'carrément|bien sûr|absolument|pourquoi pas|'
    r'je veux bien|volontiers|allez|non|nan|nope|pas vraiment|'
    r'bof|si|stp|please|détaille|détailles|detail|continue|'
    r'envoie|balance|dis-moi|affirmatif|négatif|'
    r'je veux savoir|je veux voir|on y va|'
    r'show me|show them|go ahead|tell me|do it|'
    r'ja|nein|doch|natürlich|zeig|zeig mir|'
    r'sim|não|mostra|claro|'
    r'sí|no|muestra|dale|venga|'
    r'ja|nee|laat zien|toon)[\s!.?]*$',
    re.IGNORECASE
)

# Fuzzy continuation: catches typos like "vas ymontre les", "oui montre", etc.
_CONTINUATION_WORDS = {
    "oui", "ouais", "yes", "yeah", "yep", "ok", "go", "montre", "vas",
    "allez", "continue", "détaille", "detail", "envoie", "balance",
    "show", "tell", "ja", "sim", "sí", "si", "dale", "venga",
    "claro", "doch", "zeig", "mostra", "laat", "toon", "nee",
    "non", "nan", "nope", "nein", "não", "no",
}


def _is_short_continuation(message: str) -> bool:
    """Detecte si le message est une reponse courte de continuation.
    Uses exact regex first, then fuzzy word-level check for typos."""
    stripped = message.strip()
    if len(stripped) > 80:
        return False
    if CONTINUATION_PATTERNS.match(stripped):
        return True
    # Fuzzy: if short (≤5 words) and first word is a continuation word
    # V46: guard — messages containing digits are likely queries, not continuations
    words = stripped.lower().split()
    if 1 <= len(words) <= 5 and words[0] in _CONTINUATION_WORDS:
        if not any(c.isdigit() for c in stripped):
            return True
    return False


# ────────────────────────────────────────────
# Phase AFFIRMATION : réponses conversationnelles courtes (V51)
# Capte "Oui", "Ok", "Non", "Avec plaisir", "Oui je veux bien", etc.
# NE capte PAS les messages avec des chiffres (digit guard V46).
# ────────────────────────────────────────────

_AFFIRMATION_PATTERNS = re.compile(
    r'^('
    # FR
    r'oui|ouais|ouep|yep|ok|okay|d\'accord|bien s[uû]r|bien sur|'
    r'[çc]a marche|c\'est bon|entendu|parfait|super|'
    r'avec plaisir|volontiers|carr[eé]ment|'
    r'non|nan|pas vraiment|bof|'
    # EN
    r'yes|yeah|sure|no|nope|alright|sounds good|perfect|thanks|great|'
    # ES
    r's[ií]|vale|claro|por supuesto|perfecto|gracias|de acuerdo|'
    # PT
    r'sim|n[aã]o|perfeito|obrigado|obrigada|certo|com certeza|'
    # DE
    r'ja|nein|klar|nat[uü]rlich|perfekt|danke|einverstanden|'
    # NL
    r'nee|prima|natuurlijk|bedankt|akkoord|zeker'
    r')[\s!.?…]*$',
    re.IGNORECASE
)

# Strip emojis for clean word counting
_EMOJI_RE = re.compile(
    r'[\U00002600-\U000027BF\U0001F300-\U0001FAFF\U0000FE00-\U0000FE0F'
    r'\U0001F900-\U0001F9FF\U0000200D\U00002702-\U000027B0]+',
    re.UNICODE,
)


def _is_affirmation_simple(message: str) -> bool:
    """Detecte une affirmation/negation conversationnelle courte (6 langues).
    Exclut les messages contenant des chiffres (digit guard V46).
    Plus large que _is_short_continuation : capte les mots isolés
    sans exiger de contexte de continuation (vas-y, montre, etc.)."""
    stripped = message.strip()
    if len(stripped) > 80:
        return False
    # Strip emojis for word count and digit check
    text_only = _EMOJI_RE.sub('', stripped).strip()
    if not text_only:
        return False
    if any(c.isdigit() for c in text_only):
        return False
    words = text_only.split()
    if len(words) > 5:
        return False
    return bool(_AFFIRMATION_PATTERNS.match(text_only))


# Mot-clé jeu seul (V51 FIX 5)
_GAME_KEYWORD_ALONE = re.compile(
    r'^\s*(loto|euromillions?|euro\s*millions?)\s*[!?.]*\s*$',
    re.IGNORECASE,
)


def _detect_game_keyword_alone(message: str) -> bool:
    """Detecte si le message est uniquement un nom de jeu."""
    return bool(_GAME_KEYWORD_ALONE.match(message.strip()))


# ────────────────────────────────────────────
# Phase T : Detection tirage (date / dernier)
# ────────────────────────────────────────────

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


_STAT_NEUTRALIZE_RE = re.compile(
    # FR — statistical / frequency indicators
    r'\b[eé]cart\b|\bretard\b|\bfr[eé]quence\b|\bcombien\s+de\s+fois\b'
    r'|\bplus\s+grand\b|\bclassement\b'
    r'|\bsouvent\b|\bfr[eé]quemment\b|\brarement\b|\bjamais\b'
    r'|\ble\s+plus\b|\ble\s+moins\b|\br[eé]cemment\b'
    r'|\ben\s+moyenne\b|\bstatistique\b|\banalyse\b'
    # EN
    r'|\bgap\b|\bdelay\b|\bfrequency\b|\bhow\s+many\s+times\b'
    r'|\blargest\b|\branking\b'
    r'|\boften\b|\bfrequently\b|\brarely\b|\bnever\b'
    r'|\bthe\s+most\b|\bthe\s+least\b|\bmost\s+common\b'
    r'|\brecently\b|\bon\s+average\b'
    # ES
    r'|\bretraso\b|\bfrecuencia\b|\bcu[aá]ntas\s+veces\b'
    r'|\bmayor\b|\bclasificaci[oó]n\b'
    r'|\ba\s+menudo\b|\bfrecuentemente\b|\braramente\b|\bnunca\b'
    r'|\bel\s+m[aá]s\b|\bel\s+menos\b|\brecientemente\b'
    # PT
    r'|\batraso\b|\bfrequ[eê]ncia\b|\bquantas\s+vezes\b'
    r'|\bmaior\b|\bclassifica[çc][aã]o\b'
    r'|\bfrequentemente\b|\braramente\b|\bnunca\b'
    r'|\bo\s+mais\b|\bo\s+menos\b|\bcom\s+mais\b|\brecentemente\b'
    # DE
    r'|\babstand\b|\bverz[oö]gerung\b|\bh[aä]ufigkeit\b|\bwie\s+oft\b'
    r'|\bgr[oö][sß]te[rs]?\b|\brangliste\b'
    r'|\boft\b|\bh[aä]ufig\b|\bselten\b|\bnie\b'
    r'|\bam\s+meisten\b|\bam\s+wenigsten\b|\bk[uü]rzlich\b'
    # NL
    r'|\bachterstand\b|\bvertraging\b|\bfrequentie\b|\bhoe\s+vaak\b'
    r'|\bgrootste\b|\branglijst\b'
    r'|\bvaak\b|\bfrequent\b|\bzelden\b|\bnooit\b'
    r'|\bhet\s+meest\b|\bhet\s+minst\b|\brecentelijk\b',
    re.IGNORECASE,
)


def _detect_tirage(message: str):
    """
    Detecte si l'utilisateur demande les resultats d'un tirage.
    Returns: "latest", un objet date, ou None.
    """
    lower = message.lower()

    # Exclure "prochain tirage" (gere par Phase 0)
    if re.search(r'prochain', lower):
        return None

    # Neutralize Phase T if statistical analysis words are present
    # (e.g. "écart depuis son dernier tirage" → Phase 3/SQL, not Phase T)
    if _STAT_NEUTRALIZE_RE.search(lower):
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

_MOIS_FR = r'(?:janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre)'
_MOIS_RE = _MOIS_FR  # backward compat (re-exported by api_chat.py)
_MOIS_EN = r'(?:january|february|march|april|may|june|july|august|september|october|november|december)'
_MOIS_ES = r'(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)'
_MOIS_PT = r'(?:janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)'
_MOIS_DE = r'(?:januar|februar|m[aä]rz|april|mai|juni|juli|august|september|oktober|november|dezember)'
_MOIS_NL = r'(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)'

_TEMPORAL_PATTERNS = [
    # ── FR ──
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
    r'\ben\s+' + _MOIS_FR,                         # en janvier, en février...
    r'\bces\s+\d+\s+derniers?\s+mois\b',           # ces 6 derniers mois
    r'\bdepuis\s+le\s+d[eé]but\b',                # depuis le début
    r'\bdepuis\s+\d+\s+(?:mois|ans?|semaines?)\b', # depuis 3 mois
    r'(?:dans|pour|sur|pendant)\s+l[\'\u2019]?ann[ée]e\s+20\d{2}',
    r'\bau\s+cours\s+de\s+l[\'\u2019]?ann[ée]e\s+20\d{2}',
    r'\bl[\'\u2019]?ann[ée]e\s+20\d{2}\b',
    r'\bdepuis\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',
    r'\bavant\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',
    r'\bapr[eè]s\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',
    r'\bentre\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\s+et',
    r'\bde\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',
    r'\bdepuis\s+(?:le\s+)?\d+(?:er)?\s+' + _MOIS_FR + r'\s+20\d{2}',  # depuis le 1er janvier 2026
    r'\bdepuis\s+' + _MOIS_FR + r'\s+20\d{2}',  # depuis janvier 2026
    r'\b[àa]\s+partir\s+d[eu]\b',               # à partir de / à partir du
    r'\bles\s+\d+\s+derniers?\s+mois\b',         # les 3 derniers mois
    r'\bles\s+\d+\s+derni[eè]res?\s+ann[ée]es?\b', # les 3 dernières années
    r'\bces\s+\d+\s+derni[eè]res?\s+ann[ée]es?\b', # ces 3 dernières années
    r'\bsur\s+\d+\s+ans?\b',                       # sur 3 ans
    # ── EN ──
    r'\bin\s+20\d{2}\b',                           # in 2024
    r'\bsince\s+20\d{2}\b',                        # since 2023
    r'\bbefore\s+20\d{2}\b',                       # before 2024
    r'\bafter\s+20\d{2}\b',                        # after 2024
    r'\bbetween\s+20\d{2}\s+and\s+20\d{2}',       # between 2023 and 2024
    r'\bthis\s+year\b',                            # this year
    r'\blast\s+year\b',                            # last year
    r'\bthis\s+month\b',                           # this month
    r'\blast\s+month\b',                           # last month
    r'\bin\s+' + _MOIS_EN,                         # in January, in February...
    r'\blast\s+\d+\s+months?\b',                   # last 6 months
    r'\bsince\s+the\s+beginning\b',               # since the beginning
    r'\bsince\s+\d+\s+(?:months?|years?|weeks?)\b',  # since 3 months
    r'\bduring\s+(?:the\s+year\s+)?20\d{2}\b',    # during 2024 / during the year 2024
    r'\bsince\s+' + _MOIS_EN,                    # since January 2026
    r'\bfrom\s+' + _MOIS_EN,                     # from March 2025
    r'\b(?:the\s+)?(?:last|past)\s+\d+\s+months?\b',  # the last 3 months / past 6 months
    r'\b(?:the\s+)?(?:last|past)\s+\d+\s+years?\b',  # the last 3 years / past 5 years
    r'\bover\s+(?:the\s+)?(?:last|past)\s+\d+\s+years?\b',  # over the last 3 years
    # ── ES ──
    r'\bdesde\s+20\d{2}\b',                        # desde 2023
    r'\bantes\s+de\s+20\d{2}\b',                   # antes de 2024
    r'\bdespu[eé]s\s+de\s+20\d{2}\b',             # después de 2024
    r'\bentre\s+20\d{2}\s+y\s+20\d{2}',           # entre 2023 y 2024
    r'\beste\s+a[nñ]o\b',                          # este año
    r'\bel\s+a[nñ]o\s+pasado\b',                   # el año pasado
    r'\beste\s+mes\b',                              # este mes
    r'\bel\s+mes\s+pasado\b',                       # el mes pasado
    r'\ben\s+' + _MOIS_ES,                         # en enero, en febrero...
    r'\bdesde\s+\d+\s+(?:meses|a[nñ]os|semanas)\b',  # desde 3 meses
    r'\bdesde\s+(?:el\s+)?\d+\s+de\s+' + _MOIS_ES,  # desde el 1 de enero de 2026
    r'\bdesde\s+' + _MOIS_ES,                    # desde enero 2026
    r'\ba\s+partir\s+de\b',                      # a partir de (ES/PT shared)
    r'\blos\s+[úu]ltimos\s+\d+\s+meses\b',      # los últimos 3 meses
    r'\blos\s+[úu]ltimos\s+\d+\s+a[nñ]os\b',   # los últimos 3 años
    # ── PT ──
    r'\bem\s+20\d{2}\b',                           # em 2024
    r'\bdesde\s+20\d{2}\b',                        # desde 2023 (shared with ES)
    r'\bantes\s+de\s+20\d{2}\b',                   # antes de 2024 (shared with ES)
    r'\bdepois\s+de\s+20\d{2}\b',                  # depois de 2024
    r'\bentre\s+20\d{2}\s+e\s+20\d{2}',           # entre 2023 e 2024
    r'\beste\s+ano\b',                              # este ano
    r'\bo\s+ano\s+passado\b',                       # o ano passado
    r'\beste\s+m[eê]s\b',                           # este mês
    r'\bo\s+m[eê]s\s+passado\b',                    # o mês passado
    r'\bem\s+' + _MOIS_PT,                         # em janeiro, em fevereiro...
    r'\bdesde\s+\d+\s+(?:meses|anos|semanas)\b',  # desde 3 meses
    r'\bdesde\s+(?:\d+\s+de\s+)?' + _MOIS_PT,   # desde 1 de janeiro / desde janeiro
    r'\b[nd]?os\s+[úu]ltimos\s+\d+\s+meses\b',   # os/nos/dos últimos 3 meses
    r'\b[nd]?os\s+[úu]ltimos\s+\d+\s+anos\b',  # os/nos/dos últimos 3 anos
    # ── DE ── (patterns lowercase — _has_temporal_filter lowercases input)
    r'\bim\s+(?:jahr\s+)?20\d{2}\b',              # im 2024 / im Jahr 2024
    r'\bseit\s+20\d{2}\b',                         # seit 2023
    r'\bvor\s+20\d{2}\b',                          # vor 2024
    r'\bnach\s+20\d{2}\b',                         # nach 2024
    r'\bzwischen\s+20\d{2}\s+und\s+20\d{2}',      # zwischen 2023 und 2024
    r'\bdieses\s+jahr\b',                           # dieses Jahr
    r'\bletztes\s+jahr\b',                          # letztes Jahr
    r'\bdiesen\s+monat\b',                          # diesen Monat
    r'\bletzten\s+monat\b',                         # letzten Monat
    r'\bim\s+' + _MOIS_DE,                         # im Januar, im Februar...
    r'\bseit\s+\d+\s+(?:monaten?|jahren?|wochen?)\b',  # seit 3 Monaten
    r'\bseit\s+(?:dem\s+)?\d+\.\s*' + _MOIS_DE,  # seit dem 1. Januar 2026
    r'\bseit\s+' + _MOIS_DE,                     # seit Januar 2026
    r'\bab\s+' + _MOIS_DE,                       # ab März 2025
    r'\bdie\s+letzten\s+\d+\s+monate\b',         # die letzten 3 Monate
    r'\bdie\s+letzten\s+\d+\s+jahre\b',         # die letzten 3 Jahre
    # ── NL ──
    r'\bin\s+20\d{2}\b',                           # in 2024 (shared with EN)
    r'\bsinds\s+20\d{2}\b',                        # sinds 2023
    r'\bv[oó][oó]r\s+20\d{2}\b',                  # vóór 2024
    r'\bna\s+20\d{2}\b',                           # na 2024
    r'\btussen\s+20\d{2}\s+en\s+20\d{2}',         # tussen 2023 en 2024
    r'\bdit\s+jaar\b',                              # dit jaar
    r'\bvorig\s+jaar\b',                            # vorig jaar
    r'\bdeze\s+maand\b',                            # deze maand
    r'\bvorige\s+maand\b',                          # vorige maand
    r'\bin\s+' + _MOIS_NL,                         # in januari, in februari...
    r'\bsinds\s+\d+\s+(?:maanden?|jaren?|weken?)\b',  # sinds 3 maanden
    r'\bsinds\s+(?:\d+\s+)?' + _MOIS_NL,        # sinds 1 januari / sinds januari
    r'\bvanaf\s+' + _MOIS_NL,                    # vanaf maart 2025
    r'\bde\s+laatste\s+\d+\s+maanden?\b',        # de laatste 3 maanden
    r'\bde\s+laatste\s+\d+\s+jaar\b',           # de laatste 3 jaar
]


def _has_temporal_filter(message: str) -> bool:
    """Detecte si le message contient un filtre temporel (annee, mois, periode)."""
    lower = message.lower()
    return any(re.search(pat, lower) for pat in _TEMPORAL_PATTERNS)


# Patterns d'extraction temporelle (nombre + unite) — 6 langues
_TEMPORAL_EXTRACT_MONTHS = [
    r'(\d+)\s*(?:derniers?\s+mois|last\s+months?|[uú]ltimos?\s+mes(?:es)?|letzten?\s+monat(?:e|en)?|laatste\s+maand(?:en)?)',
    r'(?:derniers?|last|[uú]ltimos?|letzten?|laatste)\s+(\d+)\s*(?:mois|months?|mes(?:es)?|monat(?:e|en)?|maand(?:en)?)',
]
_TEMPORAL_EXTRACT_YEARS = [
    r'(\d+)\s*(?:derni[eè]res?\s+ann[eé]es?|last\s+years?|[uú]ltimos?\s+a[ñn]os?|[uú]ltimos?\s+anos?|letzten?\s+jahr(?:e|en)?|laatste\s+ja(?:a)?r(?:en)?)',
    r'(?:derni[eè]res?|last|[uú]ltimos?|letzten?|laatste)\s+(\d+)\s*(?:ann[eé]es?|years?|a[ñn]os?|anos?|jahr(?:e|en)?|ja(?:a)?r(?:en)?)',
]
_TEMPORAL_EXTRACT_WEEKS = [
    r'(\d+)\s*(?:derni[eè]res?\s+semaines?|last\s+weeks?|[uú]ltimas?\s+semanas?|letzten?\s+woch(?:e|en)?|laatste\s+we(?:e)?k(?:en)?)',
    r'(?:derni[eè]res?|last|[uú]ltimas?|letzten?|laatste)\s+(\d+)\s*(?:semaines?|weeks?|semanas?|woch(?:e|en)?|we(?:e)?k(?:en)?)',
]


def _extract_temporal_date(message: str):
    """Extrait une date de debut a partir d'une expression temporelle (6 langues).
    Returns: date ou None."""
    lower = message.lower()
    today = date.today()

    for pat in _TEMPORAL_EXTRACT_MONTHS:
        m = re.search(pat, lower)
        if m:
            n = int(m.group(1))
            return today - timedelta(days=n * 30)

    for pat in _TEMPORAL_EXTRACT_YEARS:
        m = re.search(pat, lower)
        if m:
            n = int(m.group(1))
            return today - timedelta(days=n * 365)

    for pat in _TEMPORAL_EXTRACT_WEEKS:
        m = re.search(pat, lower)
        if m:
            n = int(m.group(1))
            return today - timedelta(weeks=n)

    return None


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
# Phase I — Détection d'insultes / agressivité
# ═══════════════════════════════════════════════════════

_INSULTE_MOTS = {
    # FR
    "connard", "connards", "connasse", "connasses",
    "débile", "debile", "débiles", "debiles",
    "idiot", "idiote", "idiots", "idiotes",
    "stupide", "stupides",
    "merde", "merdes",
    "putain",
    "fdp", "ntm",
    "crétin", "cretin", "crétins", "cretins", "crétine", "cretine",
    "abruti", "abrutie", "abrutis", "abruties",
    "imbécile", "imbecile", "imbéciles", "imbeciles",
    "bouffon", "bouffons", "bouffonne",
    "tocard", "tocards", "tocarde",
    "enfoiré", "enfoire", "enfoirés", "enfoires",
    "bâtard", "batard", "bâtards", "batards",
    "pute", "putes",
    "salope", "salopes",
    "con", "cons",
    "nul", "nulle", "nuls", "nulles",
    # EN
    "useless", "stupid", "dumb", "trash", "garbage", "worthless",
    "pathetic", "rubbish", "crap", "terrible", "horrible", "awful",
    "moron", "morons", "shit", "fuck", "damn",
    # ES
    "inútil", "inutil", "tonto", "tonta", "estúpido", "estupido", "estúpida", "estupida",
    "basura", "mierda", "imbécil", "imbecil", "payaso", "ridículo", "ridiculo",
    "porquería", "porqueria", "asqueroso", "mediocre", "patético", "patetico",
    "gilipollas", "subnormal",
    # PT
    "inútil", "estúpido", "estupido", "burro", "burra",
    "lixo", "horrível", "horrivel", "terrível", "terrivel",
    "palhaço", "palhaco", "ridículo", "porcaria", "nojento",
    "medíocre", "otário", "otario", "besta", "incompetente",
    # DE
    "nutzlos", "dumm", "blöd", "blod", "müll", "mull", "schrott",
    "wertlos", "erbärmlich", "erbarmlich", "scheiße", "scheisse",
    "mist", "furchtbar", "schrecklich", "dämlich", "damlich",
    "bescheuert", "trottel", "depp", "vollidiot", "schwachsinn", "unfähig", "unfahig",
    # NL
    "nutteloos", "dom", "idioot", "stom", "waardeloos", "rommel",
    "slecht", "verschrikkelijk", "vreselijk", "belachelijk", "onzin",
    "achterlijk", "debiel", "klote", "kut", "sukkel", "eikel", "onbekwaam", "hopeloos",
}

_INSULTE_PHRASES = [
    # FR
    r"\bta\s+gueule\b",
    r"\bferme[\s-]la\b",
    r"\bcasse[\s-]toi\b",
    r"\bd[eé]gage\b",
    r"\btu\s+sers?\s+[àa]\s+rien",
    r"\bt['\u2019]es?\s+nul(?:le)?(?:\s|$|[?.!,])",
    r"\bt['\u2019]es?\s+inutile\b",
    r"\b(?:bot|chatbot|ia)\s+de\s+merde\b",
    r"\btu\s+comprends?\s+rien",
    r"\bt['\u2019]es?\s+con(?:ne)?(?:\s|$|[?.!,])",
    r"\btu\s+(?:me\s+)?fais?\s+chier",
    r"\bras\s+le\s+bol",
    r"\btu\s+(?:me\s+)?saoules?",
    r"\btu\s+(?:me\s+)?[eé]nerves?",
    r"\br[eé]ponse\s+de\s+merde\b",
    r"\bt['\u2019]es?\s+(?:une?\s+)?blague",
    r"\bt['\u2019]es?\s+b[eê]te",
    r"\btu\s+fais?\s+piti[eé]",
    r"\b(?:lol|mdr|ptdr)\s+t['\u2019]es?\s+(?:nul|b[eê]te|con)",
    # EN
    r"\byou['\u2019]?re\s+(?:useless|stupid|dumb|worthless|pathetic|terrible|horrible|awful)\b",
    r"\byou\s+(?:are|r)\s+(?:useless|stupid|dumb|worthless|pathetic|terrible)\b",
    r"\byou\s+suck\b",
    r"\bshut\s+up\b",
    r"\bgo\s+away\b",
    r"\bget\s+lost\b",
    r"\bwhat\s+a\s+(?:waste|joke|garbage)\b",
    r"\bthis\s+(?:bot|thing|ai)\s+(?:is\s+)?(?:useless|trash|garbage|crap|terrible|stupid)\b",
    # ES
    r"\beres\s+(?:in[uú]til|tonto|est[uú]pido|idiota|pat[eé]tico|rid[ií]culo)\b",
    r"\bt[uú]\s+eres\s+(?:in[uú]til|tonto|est[uú]pido|idiota)\b",
    r"\bcallate\b",
    r"\bc[aá]llate\b",
    r"\bvete\b",
    r"\bno\s+sirves?\s+para\s+nada\b",
    r"\beste\s+(?:bot|chatbot)\s+(?:es\s+)?(?:basura|in[uú]til|horrible)\b",
    # PT
    r"\b[eé]s\s+(?:in[uú]til|est[uú]pido|idiota|pat[eé]tico|rid[ií]culo)\b",
    r"\btu\s+[eé]s\s+(?:in[uú]til|est[uú]pido|idiota)\b",
    r"\bvoc[eê]\s+[eé]\s+(?:in[uú]til|est[uú]pido|idiota)\b",
    r"\bcala[\s-]te\b",
    r"\bvai[\s-]te\s+embora\b",
    r"\bn[aã]o\s+serves?\s+para\s+nada\b",
    r"\beste\s+(?:bot|chatbot)\s+[eé]\s+(?:lixo|in[uú]til|horr[ií]vel)\b",
    # DE
    r"\bdu\s+bist\s+(?:nutzlos|dumm|bl[oö]d|wertlos|erb[aä]rmlich|unf[aä]hig|bescheuert)\b",
    r"\bhalt[\s\']?s?\s+maul\b",
    r"\bverzieh\s+dich\b",
    r"\bverpiss\s+dich\b",
    r"\bdieser?\s+(?:bot|chatbot|ding)\s+(?:ist\s+)?(?:m[uü]ll|schrott|nutzlos|schrecklich)\b",
    # NL
    r"\bje\s+bent\s+(?:nutteloos|dom|stom|waardeloos|hopeloos|onbekwaam|belachelijk)\b",
    r"\bjij\s+bent\s+(?:nutteloos|dom|stom|waardeloos|hopeloos)\b",
    r"\bhou\s+(?:je\s+)?(?:mond|bek)\b",
    r"\bga\s+weg\b",
    r"\bophoepelen\b",
    r"\bdeze?\s+(?:bot|chatbot|ding)\s+(?:is\s+)?(?:waardeloos|nutteloos|rommel|slecht)\b",
]

_MENACE_PATTERNS = [
    # FR
    r"\bje\s+vais?\s+te\s+(?:hacker|pirater|casser|d[eé]truire|supprimer)",
    r"\bje\s+vais?\s+(?:hacker|pirater)\s",
    # EN
    r"\bi['\u2019]?(?:m\s+going\s+to|ll|will)\s+(?:hack|destroy|break|delete|kill)\b",
    # ES
    r"\bvoy\s+a\s+(?:hackear|destruir|romper|eliminar)\b",
    # PT
    r"\bvou\s+(?:hackear|destruir|partir|eliminar)\b",
    # DE
    r"\bich\s+werde?\s+(?:dich\s+)?(?:hacken|zerst[oö]ren|l[oö]schen|kaputt)\b",
    # NL
    r"\bik\s+(?:ga|zal)\s+(?:je\s+)?(?:hacken|vernietigen|verwijderen|kapot)\b",
]


def _insult_targets_bot(message: str) -> bool:
    """Verifie si l'insulte vise le bot (True) ou le Loto/FDJ (False)."""
    bot_words = (
        # FR
        "tu ", "t'", "\u2019", " toi", " te ", " ia ",
        # EN
        "you", "your", "this bot", "this thing", "this ai",
        # ES
        "eres", "este bot", "esta cosa", " tu ",
        # PT
        "voc\u00ea", "este bot", "esta coisa",
        # DE
        "du ", "du bist", "dieser bot", "dieses ding",
        # NL
        "je ", "je bent", "jij ", "deze bot", "dit ding",
        # Generic
        "bot", "chatbot", "hybride",
    )
    loto_words = ("loto", "fdj", "fran\u00e7aise des jeux", "tirage", "euromillion")
    has_bot = any(w in message for w in bot_words)
    has_loto = any(w in message for w in loto_words)
    if has_loto and not has_bot:
        return False
    return True


def _detect_insulte(message: str):
    """
    Detecte insultes/agressivite dans le message.
    Returns: 'directe' | 'menace' | None
    """
    lower = message.lower()
    # Normalisation basique leet speak
    normalized = lower.replace('0', 'o').replace('1', 'i').replace('3', 'e').replace('@', 'a')
    normalized = re.sub(r'(?<=\w)\.(?=\w)', '', normalized)
    # Normalisation apostrophe manquante : "tes nul" → "t'es nul"
    normalized = re.sub(r'\btes\b', "t'es", normalized)

    # Menaces en priorite
    for pattern in _MENACE_PATTERNS:
        if re.search(pattern, normalized):
            return "menace"

    # Phrases insultantes (plus specifiques, testees en premier)
    for pattern in _INSULTE_PHRASES:
        if re.search(pattern, normalized):
            if _insult_targets_bot(normalized):
                return "directe"

    # Mots insultes individuels (word boundary)
    for mot in _INSULTE_MOTS:
        if re.search(r'\b' + re.escape(mot) + r'\b', normalized):
            if _insult_targets_bot(normalized):
                return "directe"

    return None


def _count_insult_streak(history) -> int:
    """Compte les insultes consecutives dans l'historique (du plus recent au plus ancien)."""
    count = 0
    for msg in reversed(history):
        if msg.role == "user":
            if _detect_insulte(msg.content):
                count += 1
            else:
                break
    return count


# ═══════════════════════════════════════════════════════
# Phase C — Détection compliments
# ═══════════════════════════════════════════════════════

_COMPLIMENT_PHRASES = [
    # FR
    "t'es génial", "t'es genial", "tu es génial", "tu es genial",
    "t'es bon", "tu es bon",
    "t'es fort", "tu es fort", "t'es le meilleur", "tu es le meilleur",
    "t'es un amour", "tu es un amour", "t'es cool", "tu es cool",
    "t'es trop fort", "t'es super", "tu es super", "bien joué", "bien joue",
    "tu gères", "tu geres", "tu déchires", "tu dechires",
    "t'assures", "tu assures", "t'es intelligent", "tu es intelligent",
    "merci beaucoup",
    "vraiment génial", "vraiment genial", "vraiment bon", "vraiment fort",
    "vraiment super", "vraiment top", "trop fort",
    # EN
    "you're amazing", "you are amazing", "you're great", "you are great",
    "you're awesome", "you are awesome", "well done", "good job", "nice job",
    "you're the best", "you are the best", "you're brilliant", "you are brilliant",
    "you're smart", "you are smart", "really amazing", "really great",
    "really awesome", "really good", "so helpful", "very helpful",
    "thank you so much", "thanks a lot",
    # ES
    "eres genial", "eres increíble", "eres increible", "buen trabajo",
    "eres el mejor", "eres brillante", "realmente genial", "muy bueno",
    "eres asombroso", "que bueno eres", "eres la mejor",
    "muchas gracias",
    # PT
    "és incrível", "es incrivel", "és genial", "es genial",
    "és o melhor", "es o melhor", "bom trabalho", "muito bom",
    "realmente incrível", "realmente incrivel", "és brilhante", "es brilhante",
    "muito obrigado", "muito obrigada",
    # DE
    "du bist toll", "du bist super", "du bist klasse", "du bist genial",
    "du bist der beste", "du bist die beste", "du bist brilliant",
    "echt toll", "echt super", "echt gut", "wirklich toll", "wirklich gut",
    "gut gemacht", "sehr hilfreich", "vielen dank",
    # NL
    "je bent geweldig", "je bent super", "je bent de beste", "je bent geniaal",
    "je bent briljant", "echt geweldig", "echt super", "echt goed",
    "goed gedaan", "heel goed", "zeer behulpzaam",
    "heel erg bedankt",
]

_COMPLIMENT_LOVE_PHRASES = [
    # FR
    "je t'aime", "je t'adore", "t'es un amour", "tu es un amour",
    # EN
    "i love you", "you're adorable", "you are adorable",
    # ES
    "te quiero", "te adoro", "eres un amor",
    # PT
    "adoro-te", "és um amor", "es um amor",
    # DE
    "ich liebe dich", "du bist ein schatz",
    # NL
    "ik hou van je", "je bent een schat",
]

_COMPLIMENT_SOLO_WORDS = {
    # FR
    "génial", "genial", "bravo", "chapeau", "respect", "impressionnant",
    "incroyable", "excellent", "parfait", "formidable",
    "génialissime", "magnifique", "wahou", "wow", "classe", "top",
    # EN
    "amazing", "awesome", "brilliant", "fantastic", "wonderful",
    "impressive", "outstanding", "superb", "great", "incredible",
    "perfect", "excellent",
    # ES
    "genial", "increíble", "increible", "fantástico", "fantastico",
    "impresionante", "excelente", "perfecto", "brillante", "asombroso",
    # PT
    "incrível", "incrivel", "fantástico", "fantastico",
    "impressionante", "excelente", "perfeito", "brilhante",
    # DE
    "toll", "super", "klasse", "genial", "fantastisch",
    "beeindruckend", "ausgezeichnet", "perfekt", "brilliant",
    # NL
    "geweldig", "fantastisch", "geniaal", "briljant",
    "indrukwekkend", "uitstekend", "perfect",
}


def _compliment_targets_bot(message: str) -> bool:
    """Verifie si le compliment vise le bot (True) ou le Loto/FDJ (False)."""
    lower = message.lower()
    bot_words = (
        # FR
        "tu ", "t'", "\u2019", " toi", " te ", "bot", "chatbot", "hybride", " ia ",
        # EN
        "you ", "you'", " your",
        # ES
        "eres ", "tú ", " ti ",
        # PT
        "és ", "tu ",
        # DE
        "du ", "dich ", " dir ",
        # NL
        "je ", "jij ", " jou",
    )
    loto_words = ("loto", "fdj", "française des jeux", "tirage", "lottery", "lotería", "loteria")
    has_bot = any(w in lower for w in bot_words)
    has_loto = any(w in lower for w in loto_words)
    if has_loto and not has_bot:
        return False
    return True


def _detect_compliment(message: str):
    """
    Detecte un compliment dans le message.
    Returns: 'love' | 'merci' | 'compliment' | None
    """
    lower = message.lower().strip()
    # Normalisation apostrophe manquante : "tes génial" → "t'es génial"
    lower = re.sub(r'\btes\b', "t'es", lower)

    # Declaration affective
    for phrase in _COMPLIMENT_LOVE_PHRASES:
        if phrase in lower:
            return "love"

    # Remerciement simple (court ou phrase de remerciement)
    _merci_starts = ("merci", "thanks", "thank you", "gracias", "obrigado", "obrigada", "danke", "bedankt", "dank je")
    _merci_phrases = (
        "je vous remercie", "je te remercie", "je remercie",
        "i appreciate", "thank you very much", "thanks so much",
        "muchas gracias", "muito obrigado", "muito obrigada",
        "vielen dank", "heel erg bedankt", "hartelijk dank",
    )
    if any(lower.startswith(m) for m in _merci_starts) and len(lower) < 80:
        return "merci"
    if any(p in lower for p in _merci_phrases) and len(lower) < 80:
        return "merci"

    # Phrases complimentaires
    for phrase in _COMPLIMENT_PHRASES:
        if phrase in lower:
            if _compliment_targets_bot(lower):
                return "compliment"

    # Mots isolés (fallback)
    words = set(re.findall(r'\w+', lower))
    if words & _COMPLIMENT_SOLO_WORDS:
        if _compliment_targets_bot(lower):
            return "compliment"

    return None


def _count_compliment_streak(history) -> int:
    """Compte les compliments consecutifs recents (du plus recent au plus ancien)."""
    count = 0
    if not history:
        return 0
    for msg in reversed(history):
        if msg.role == "user":
            if _detect_compliment(msg.content):
                count += 1
            else:
                break
    return count


# ═══════════════════════════════════════════════════════
# Data signal heuristic — skip Phase SQL for pure conversational messages (V65)
# ═══════════════════════════════════════════════════════

_DATA_KEYWORDS = re.compile(
    # FR
    r'\b(?:fr[eé]quen|statistiqu|tirage|sortie?|retard|[eé]cart|classement|'
    r'top\s*\d|combien|moyenne|pourcentage|pairs?|impairs?|chaud|froid|'
    r'derni[eè]re?|premi[eè]re?|souvent|rarement|jamais|toujours|'
    r'fois|depuis|entre|pendant|ann[eé]e|mois|semaine|historique|archiv|'
    r'num[eé]ro|boule|chance|[eé]toile|jackpot|gagnant|rang|'
    # EN
    r'frequen|statistic|draw|lag|gap|ranking|how\s+many|average|percentage|'
    r'even|odd|hot|cold|last|first|most|least|often|rarely|never|always|'
    r'times|since|between|during|year|month|week|histor|number|star|ball|winner|'
    # ES
    r'frecuencia|estad[ií]stic|sorteo|retraso|brecha|clasificaci[oó]n|cu[aá]nto|'
    r'promedio|porcentaje|caliente|fr[ií]o|[uú]ltimo|primero|siempre|nunca|veces|'
    r'a[nñ]o|mes|semana|n[uú]mero|estrella|bola|ganador|'
    # PT
    r'frequ[eê]ncia|estat[ií]stic|sorteio|atraso|lacuna|classifica[cç][aã]o|quantas?|'
    r'percentagem|quente|frio|[uú]ltimo|primeiro|sempre|nunca|vezes|'
    r'grelha|n[uú]mero|estrela|bola|vencedor|'
    # DE
    r'h[aä]ufigkeit|statistik|ziehung|r[uü]ckstand|l[uü]cke|rangliste|wie\s+oft|'
    r'durchschnitt|prozent|hei[sß]|kalt|letzte|erste|immer|nie|mal|'
    r'seit|zwischen|jahr|monat|woche|nummer|zahl|stern|kugel|gewinner|'
    # NL
    r'frequentie|statistiek|trekking|achterstand|kloof|ranglijst|hoe\s+vaak|'
    r'gemiddelde|percentage|heet|koud|laatste|eerste|altijd|nooit|keer|'
    r'sinds|tussen|jaar|maand|week|nummer|ster|bal|winnaar)',
    re.IGNORECASE
)

_HAS_DIGIT = re.compile(r'\d')


def _has_data_signal(message: str) -> bool:
    """Heuristique rapide : le message contient-il un signal data (chiffre ou mot-cle statistique) ?
    Retourne False pour les messages purement conversationnels — permet de skip Phase SQL."""
    if _HAS_DIGIT.search(message):
        return True
    return bool(_DATA_KEYWORDS.search(message))


# ═══════════════════════════════════════════════════════
# Phase SALUTATION — Détection des salutations initiales (V65)
# Court-circuite le pipeline pour éviter un appel Gemini/SQL inutile.
# Condition : message court (< 8 mots) et historique vide ou ≤ 1 message.
# ═══════════════════════════════════════════════════════

_SALUTATION_PATTERN = re.compile(
    r'^\s*(?:'
    # FR
    r'salut|bonjour|bonsoir|coucou|yo+|yop|hey|slt|wesh|bjr|'
    r'bsr|cc|kikou|'
    # EN
    r'hello|hi|hey|howdy|what.?s\s+up|sup|hiya|'
    # ES
    r'hola|buenas|qu[eé]\s+tal|buenos?\s+d[ií]as?|buenas?\s+(?:tardes?|noches?)|'
    # PT
    r'ol[aá]|oi|bom\s+dia|boa\s+tarde|boa\s+noite|'
    # DE
    r'hallo|guten\s+(?:tag|morgen|abend)|moin|servus|'
    # NL
    r'hallo|hoi|goedendag|goedemorgen|goedenavond|goedemiddag'
    r')(?:\s+[\w\u00e0-\u00ff]{0,15}){0,3}[?!.\s]*$',
    re.IGNORECASE
)

_SALUTATION_MAX_WORDS = 8


def _detect_salutation(message: str) -> bool:
    """Detecte si le message est une salutation simple (< 8 mots, 6 langues).
    NE DOIT PAS matcher les messages longs comme 'salut genere moi une grille'."""
    words = message.split()
    if len(words) > _SALUTATION_MAX_WORDS:
        return False
    return bool(_SALUTATION_PATTERN.match(message.strip()))


# Réponses d'accueil directes — court-circuit (pas de Gemini)
_SALUTATION_RESPONSES = {
    "loto": {
        "fr": "Salut ! 👋 Je suis HYBRIDE, ton assistant IA spécialiste du Loto. Pose-moi une question sur les statistiques des tirages ou demande-moi de générer une grille !",
        "en": "Hey there! 👋 I'm HYBRIDE, your AI assistant for Loto analysis. Ask me about draw statistics or request a grid!",
        "es": "¡Hola! 👋 Soy HYBRIDE, tu asistente IA especialista en Loto. ¡Pregúntame sobre estadísticas de sorteos o pídeme una combinación!",
        "pt": "Olá! 👋 Sou o HYBRIDE, o teu assistente IA especialista em Loto. Pergunta-me sobre estatísticas dos sorteios ou pede-me uma grelha!",
        "de": "Hallo! 👋 Ich bin HYBRIDE, dein KI-Assistent für Loto-Analysen. Frag mich nach Ziehungsstatistiken oder lass dir eine Kombination generieren!",
        "nl": "Hallo! 👋 Ik ben HYBRIDE, je AI-assistent voor Loto-analyses. Vraag me naar trekkingsstatistieken of laat me een combinatie genereren!",
    },
    "em": {
        "fr": "Salut ! 👋 Je suis HYBRIDE, ton assistant IA spécialiste de l'EuroMillions. Pose-moi une question sur les statistiques des tirages ou demande-moi de générer une grille !",
        "en": "Hey there! 👋 I'm HYBRIDE, your AI assistant for EuroMillions analysis. Ask me about draw statistics or request a grid!",
        "es": "¡Hola! 👋 Soy HYBRIDE, tu asistente IA especialista en EuroMillions. ¡Pregúntame sobre estadísticas de sorteos o pídeme una combinación!",
        "pt": "Olá! 👋 Sou o HYBRIDE, o teu assistente IA especialista em EuroMillions. Pergunta-me sobre estatísticas dos sorteios ou pede-me uma grelha!",
        "de": "Hallo! 👋 Ich bin HYBRIDE, dein KI-Assistent für EuroMillions-Analysen. Frag mich nach Ziehungsstatistiken oder lass dir eine Kombination generieren!",
        "nl": "Hallo! 👋 Ik ben HYBRIDE, je AI-assistent voor EuroMillions-analyses. Vraag me naar trekkingsstatistieken of laat me een combinatie genereren!",
    },
}


def _get_salutation_response(module: str, lang: str) -> str:
    """Retourne la reponse d'accueil pour le module et la langue donnes."""
    pool = _SALUTATION_RESPONSES.get(module, _SALUTATION_RESPONSES["loto"])
    return pool.get(lang, pool["fr"])


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
    r'\bwelke\s+nummers?\s+.{0,15}spelen',
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


def _extract_exclusions(message: str) -> dict:
    """Extract exclusion constraints from generation request (6 languages).

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
        if 1 <= num <= 50:
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


# ────────────────────────────────────────────────────────────────────
# Phase R : Détection intention de noter le site (6 langues)
# ────────────────────────────────────────────────────────────────────

_SITE_RATING_RE = re.compile(
    r"(?:"
    # FR — "noter le site", "voter pour le site", "donner une note au site"
    r"(?:noter|voter\s+(?:pour\s+)?|[eé]valuer|mettre\s+une\s+note|donner\s+(?:une\s+)?note|donner\s+(?:mon\s+)?avis)"
    r"\s*(?:(?:le|ce|au|pour\s+le|pour\s+ce)\s+)?(?:site|lotoia|plateforme)"
    r"|"
    # EN — "rate the site", "rate lotoia", "give a rating"
    r"(?:rate|vote\s+(?:for\s+)?|review|give\s+(?:a\s+)?rating|leave\s+(?:a\s+)?review)"
    r"\s*(?:(?:the|this|for\s+the|for\s+this)\s+)?(?:site|website|lotoia|platform)"
    r"|"
    # ES — "votar por el sitio", "calificar el sitio"
    r"(?:votar\s+(?:por\s+)?|calificar|evaluar|dar\s+(?:una\s+)?nota)"
    r"\s*(?:(?:el|este|al)\s+)?(?:sitio|lotoia|plataforma)"
    r"|"
    # PT — "avaliar o site", "votar pelo site"
    r"(?:votar\s+(?:pel[oa]\s+)?|avaliar|dar\s+(?:uma\s+)?nota)"
    r"\s*(?:(?:o|este|ao)\s+)?(?:site|lotoia|plataforma)"
    r"|"
    # DE — "die Seite bewerten", "Seite bewerten", "bewerten die Seite"
    r"(?:(?:die|diese)\s+)?(?:seite|webseite|lotoia|plattform)\s+bewerten"
    r"|(?:bewerten|abstimmen|eine?\s+bewertung\s+geben)\s*(?:(?:die|diese|der|f[uü]r\s+die)\s+)?(?:seite|webseite|lotoia|plattform)"
    r"|"
    # NL — "de site beoordelen", "site beoordelen", "beoordelen de site"
    r"(?:(?:de|deze)\s+)?(?:site|website|lotoia|platform)\s+beoordelen"
    r"|(?:beoordelen|stemmen|een?\s+beoordeling\s+geven)\s*(?:(?:de|deze|het|voor\s+de)\s+)?(?:site|website|lotoia|platform)"
    r")",
    re.IGNORECASE,
)

_SITE_RATING_RESPONSES = {
    "fr": "Merci pour ton intérêt ! Tu peux noter LotoIA en cliquant sur les étoiles qui apparaissent en bas de page après 1 min 30 de navigation. Ton avis nous aide à nous améliorer !",
    "en": "Thanks for your interest! You can rate LotoIA by clicking the stars that appear at the bottom of the page after 1 min 30 of browsing. Your feedback helps us improve!",
    "es": "¡Gracias por tu interés! Puedes calificar LotoIA haciendo clic en las estrellas que aparecen en la parte inferior de la página después de 1 min 30 de navegación. ¡Tu opinión nos ayuda a mejorar!",
    "pt": "Obrigado pelo teu interesse! Podes avaliar o LotoIA clicando nas estrelas que aparecem no fundo da página após 1 min 30 de navegação. A tua opinião ajuda-nos a melhorar!",
    "de": "Danke für dein Interesse! Du kannst LotoIA bewerten, indem du auf die Sterne am unteren Rand der Seite klickst, die nach 1 Min. 30 erscheinen. Dein Feedback hilft uns, uns zu verbessern!",
    "nl": "Bedankt voor je interesse! Je kunt LotoIA beoordelen door op de sterren onderaan de pagina te klikken, die na 1 min 30 verschijnen. Je feedback helpt ons te verbeteren!",
}


def _detect_site_rating(message: str) -> bool:
    """Detect if user wants to rate/vote for the site (not a grid)."""
    return bool(_SITE_RATING_RE.search(message))


def get_site_rating_response(lang: str = "fr") -> str:
    """Return the site rating invitation response for the given language."""
    return _SITE_RATING_RESPONSES.get(lang, _SITE_RATING_RESPONSES["fr"])
