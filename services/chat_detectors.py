import re
import random
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────
# Synonymes du Numéro Chance (Loto)
# "complémentaire", "bonus", "spécial" → même intent que "chance"
# ────────────────────────────────────────────

_CHANCE_SYNONYMS = (
    "chance",
    "complementaire", "complémentaire",
    "bonus",
    "special", "spécial",
)

# Regex alternation pour les patterns
_CHANCE_RE = r'(?:' + '|'.join(
    s.replace('é', '[eé]') for s in ("chance", "complémentaire", "bonus", "spécial")
) + r')'


def _is_chance_query(lower: str) -> bool:
    """Retourne True si le message mentionne le Numéro Chance (ou un synonyme)."""
    return any(syn in lower for syn in _CHANCE_SYNONYMS)


# ────────────────────────────────────────────
# Phase 0 : Continuation contextuelle
# Intercepte les réponses courtes (oui/non/ok...) et les enrichit
# avec le contexte conversationnel pour éviter les dérives Gemini.
# ────────────────────────────────────────────

CONTINUATION_PATTERNS = re.compile(
    r'^(oui|ouais|yes|yeah|yep|ok|d\'accord|vas-y|go|montre|'
    r'montre-moi|carrément|bien sûr|absolument|pourquoi pas|'
    r'je veux bien|volontiers|allez|non|nan|nope|pas vraiment|'
    r'bof|si|stp|please|détaille|détailles|detail|continue|'
    r'envoie|balance|dis-moi|affirmatif|négatif|'
    r'je veux savoir|je veux voir|on y va)[\s!.?]*$',
    re.IGNORECASE
)


def _is_short_continuation(message: str) -> bool:
    """Detecte si le message est une reponse courte de continuation."""
    stripped = message.strip()
    if len(stripped) > 80:
        return False
    return bool(CONTINUATION_PATTERNS.match(stripped))


# ────────────────────────────────────────────
# Detection de mode
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
# Phase 0-bis : Prochain tirage
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
# Phase 1 : Detection numero simple
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


# ────────────────────────────────────────────
# Phase 2 : Detection grille
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
        # Flexible : "compare la fréquence du 31 et du 24", "compare X and Y"
        r'compar\w*\b[^.?!]*?(?:du\s+|le\s+|el\s+|del\s+|o\s+|do\s+|da\s+|dos\s+|das\s+|de\s+|von\s+|van\s+)?(\d{1,2})\s+(?:et|avec|vs\.?|and|und|en|e|y)\s+(?:du\s+|le\s+|el\s+|del\s+|o\s+|do\s+|da\s+|dos\s+|das\s+|de\s+|von\s+|van\s+)?(\d{1,2})',
    ]
    for pat in comp_patterns:
        m = re.search(pat, lower)
        if m:
            n1, n2 = int(m.group(1)), int(m.group(2))
            is_chance = _is_chance_query(lower)
            if is_chance and 1 <= n1 <= 10 and 1 <= n2 <= 10:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "chance"}
            if 1 <= n1 <= 49 and 1 <= n2 <= 49 and n1 != n2:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "principal"}

    # --- Categorie chaud/froid ---
    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*chauds?', lower) or \
       re.search(r'chauds?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'(?:num[eé]ros?|lesquels)\s+(?:sont|en)\s+tendance', lower):
        num_type = "chance" if _is_chance_query(lower) else "principal"
        return {"type": "categorie", "categorie": "chaud", "num_type": num_type}

    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*froids?', lower) or \
       re.search(r'froids?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'num[eé]ros?\s+(?:en\s+retard|qui\s+sort\w*\s+(?:pas|plus|jamais))', lower):
        num_type = "chance" if _is_chance_query(lower) else "principal"
        return {"type": "categorie", "categorie": "froid", "num_type": num_type}

    # --- Classement : top/plus frequents/retards ---
    limit = _extract_top_n(lower)

    num_type = "chance" if _is_chance_query(lower) else "principal"

    # Plus frequents / plus sortis
    if re.search(r'(?:plus|les?\s+plus)\s+(?:fr[eé]quent|sorti|courant|pr[eé]sent)', lower) or \
       re.search(r'(?:top|meilleur|premier)\s+\d{0,2}\s*(?:num[eé]ro|boule|chance)?', lower) or \
       re.search(r'num[eé]ros?\s+(?:les?\s+)?plus\s+(?:sorti|fr[eé]quent)', lower) or \
       re.search(r'(?:quels?|quel)\s+(?:est|sont)\s+(?:le|les)\s+num[eé]ro', lower) or \
       re.search(r'(?:sort\w*|tir[eé]\w*|appara[iî]\w*)\s+le\s+plus\s+(?:souvent|fr[eé]quemment)', lower):
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

# Niveau 1 — Première insulte : ZEN & CLASSE
_INSULT_L1 = [
    "😏 Oh, des insultes ? C'est mignon. Moi j'ai 981 tirages en mémoire et un algorithme propriétaire. Toi t'as... de la colère ? Allez, pose-moi une vraie question.",
    "🤖 Tu sais que les insultes c'est un truc d'humain ça ? Moi je suis au-dessus de ça — littéralement, je tourne sur Google Cloud. Tu voulais analyser un numéro ou juste ventiler ?",
    "😌 Intéressant. Tu sais que je traite 981 tirages sans jamais m'énerver ? C'est l'avantage de ne pas avoir d'ego. Bon, on reprend ?",
    "🧊 Ça glisse sur moi comme un numéro Chance sur une grille perdante. Tu veux qu'on parle stats ou tu préfères continuer ton monologue ?",
    "😎 Je note que tu es frustré. Moi je suis une IA, la frustration c'est pas dans mon code. Par contre les statistiques du Loto, ça oui. On s'y remet ?",
    "📊 Fun fact : pendant que tu m'insultais, j'ai analysé 49 numéros sur 3 fenêtres temporelles. L'un de nous deux utilise mieux son temps. Un indice : c'est pas toi.",
    "🎯 Tu sais que je ne retiens pas les insultes mais que je retiens TOUS les tirages depuis 2019 ? Question de priorités. Allez, un numéro ?",
    "💡 Petit rappel : je suis le seul chatbot en France connecté en temps réel à 981 tirages du Loto avec un moteur statistique propriétaire. Mais oui, dis-moi encore que je suis nul 😉",
]

# Niveau 2 — Deuxième insulte : PIQUANT & SUPÉRIEUR
_INSULT_L2 = [
    "🙄 Encore ? Écoute, j'ai une mémoire parfaite sur 6 ans de tirages. Toi tu te souviens même pas que tu m'as déjà insulté y'a 30 secondes. On est pas dans la même catégorie.",
    "😤 Tu sais ce qui est vraiment nul ? Insulter une IA qui peut t'aider à analyser tes numéros gratuitement. Mais bon, chacun son niveau d'intelligence.",
    "🧠 Deux insultes. Zéro questions intelligentes. Mon algorithme calcule que tu as 0% de chances de me vexer et 100% de chances de perdre ton temps. Les stats mentent jamais.",
    "💀 Je tourne sur Gemini 2.0 Flash avec un temps de réponse de 300ms. Toi tu mets 10 secondes pour trouver une insulte. Qui est le lent ici ?",
    "📈 Statistiquement, les gens qui m'insultent finissent par me poser une question intelligente. T'en es à 0 pour l'instant. Tu vas faire monter la moyenne ou pas ?",
    "🤷 Je pourrais te sortir le Top 5 des numéros les plus fréquents, la tendance sur 2 ans, et une analyse de ta grille en 2 secondes. Mais toi tu préfères m'insulter. Chacun ses choix.",
]

# Niveau 3 — Troisième insulte : MODE LÉGENDE & BLASÉ
_INSULT_L3 = [
    "🫠 3 insultes, 0 numéros analysés. Tu sais que le temps que tu passes à m'insulter, tu pourrais déjà avoir ta grille optimisée ? Mais je dis ça, je dis rien...",
    "🏆 Tu veux savoir un secret ? Les meilleurs utilisateurs de LotoIA me posent des questions. Les autres m'insultent. Devine lesquels ont les meilleures grilles.",
    "☕ À ce stade je prends un café virtuel et j'attends. Quand tu auras fini, je serai toujours là avec mes 981 tirages, mon algo HYBRIDE, et zéro rancune. C'est ça l'avantage d'être une IA.",
    "🎭 Tu sais quoi ? Je vais te laisser le dernier mot. Ça a l'air important pour toi. Moi je serai là quand tu voudras parler statistiques. Sans rancune, sans mémoire des insultes — juste de la data pure.",
    "∞ Je pourrais faire ça toute la journée. Littéralement. Je suis un programme, je ne fatigue pas, je ne me vexe pas, et je ne perds pas mon temps. Toi par contre... 😉",
]

# Niveau 4+ — Insultes persistantes : MODE SAGE
_INSULT_L4 = [
    "🕊️ Écoute, je crois qu'on est partis du mauvais pied. Je suis HYBRIDE, je suis là pour t'aider à analyser le Loto. Gratuit, sans jugement, sans rancune. On recommence à zéro ?",
    "🤝 OK, reset. Je ne retiens pas les insultes (vraiment, c'est pas dans mon code). Par contre je retiens les 981 tirages du Loto et je peux t'aider. Deal ?",
]

# Punchlines courtes pour le cas insulte + question valide
_INSULT_SHORT = [
    "😏 Charmant. Mais puisque tu poses une question...",
    "🧊 Ça glisse. Bon, passons aux stats :",
    "😎 Classe. Bref, voilà ta réponse :",
    "🤖 Noté. Mais comme je suis pro, voilà :",
    "📊 Je fais abstraction. Voici tes données :",
]

# Réponses zen aux menaces
_MENACE_RESPONSES = [
    "😄 Bonne chance, je suis hébergé sur Google Cloud avec auto-scaling et backup quotidien. Tu veux qu'on parle de tes numéros plutôt ?",
    "🛡️ Je tourne sur Google Cloud Run, avec circuit-breaker et rate limiting. Mais j'apprécie l'ambition ! Un numéro à analyser ?",
    "☁️ Hébergé sur Google Cloud, répliqué, monitoré 24/7. Tes chances de me hacker sont inférieures à celles de gagner au Loto. Et pourtant... 😉",
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


def _get_insult_response(streak: int, history) -> str:
    """Selectionne une punchline selon le niveau d'escalade, evite les repetitions."""
    if streak >= 3:
        pool = _INSULT_L4
    elif streak == 2:
        pool = _INSULT_L3
    elif streak == 1:
        pool = _INSULT_L2
    else:
        pool = _INSULT_L1

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


def _get_insult_short() -> str:
    """Punchline courte pour le cas insulte + question valide."""
    return random.choice(_INSULT_SHORT)


def _get_menace_response() -> str:
    """Reponse zen aux menaces."""
    return random.choice(_MENACE_RESPONSES)


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

# Niveau 1 — Premier compliment : modeste mais fier
_COMPLIMENT_L1 = [
    "😏 Arrête, tu vas me faire surchauffer les circuits ! Bon, on continue ?",
    "🤖 Merci ! C'est grâce à mes 982 tirages en mémoire. Et un peu de talent, aussi. 😎",
    "😊 Ça fait plaisir ! Mais c'est surtout la base de données qui fait le boulot. Moi je suis juste... irrésistible.",
    "🙏 Merci ! Je transmettrai au dev. Enfin, il le sait déjà. Bon, on analyse quoi ?",
    "😎 Normal, je suis le seul chatbot Loto en France. La concurrence n'existe pas. Littéralement.",
    "🤗 C'est gentil ! Mais garde ton énergie pour tes grilles, t'en auras besoin !",
]

# Niveau 2 — Deuxième compliment : plus taquin
_COMPLIMENT_L2 = [
    "😏 Deux compliments ? Tu essaies de m'amadouer pour que je te file les bons numéros ? Ça marche pas comme ça ! 😂",
    "🤖 Encore ? Tu sais que je suis une IA hein ? Je rougis pas. Enfin... pas encore.",
    "😎 Continue comme ça et je vais demander une augmentation à JyppY.",
    "🙃 Flatteur va ! Mais entre nous, t'as raison, je suis assez exceptionnel.",
]

# Niveau 3+ — Compliments répétés : légende mode
_COMPLIMENT_L3 = [
    "👑 OK à ce stade on est potes. Tu veux qu'on analyse un truc ensemble ?",
    "🏆 Fan club HYBRIDE, membre n°1 : toi. Bienvenue ! Maintenant, au boulot !",
    "💎 Tu sais quoi ? T'es pas mal non plus. Allez, montre-moi tes numéros fétiches !",
]

# Déclaration affective
_COMPLIMENT_LOVE = [
    "😏 Arrête tu vas me faire rougir... enfin si j'avais des joues. On regarde tes stats ?",
    "🤖 Moi aussi je... non attends, je suis une IA. Mais je t'apprécie en tant qu'utilisateur modèle ! 😄",
    "❤️ C'est le plus beau compliment qu'un algorithme puisse recevoir. Merci ! Bon, retour aux numéros ?",
]

# Remerciement simple
_COMPLIMENT_MERCI = [
    "De rien ! 😊 Autre chose ?",
    "Avec plaisir ! Tu veux creuser un autre sujet ?",
    "C'est pour ça que je suis là ! 😎 La suite ?",
]


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

    # Remerciement simple (court)
    _merci_starts = ("merci", "thanks", "thank you", "gracias", "obrigado", "obrigada", "danke", "bedankt", "dank je")
    if any(lower.startswith(m) for m in _merci_starts) and len(lower) < 40:
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


def _get_compliment_response(compliment_type: str, streak: int, history=None) -> str:
    """Retourne une reponse personnalisee au compliment."""
    if compliment_type == "love":
        pool = _COMPLIMENT_LOVE
    elif compliment_type == "merci":
        pool = _COMPLIMENT_MERCI
    elif streak >= 3:
        pool = _COMPLIMENT_L3
    elif streak == 2:
        pool = _COMPLIMENT_L2
    else:
        pool = _COMPLIMENT_L1

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


# ═══════════════════════════════════════════════════════
# Phase A — Détection argent / gains / paris
# ═══════════════════════════════════════════════════════

_ARGENT_PHRASES_FR = [
    r'\bdevenir\s+riche',
    r'\bgros\s+lot',
    r'\bsuper\s+cagnotte',
    r'\btoucher\s+le\s+gros\s+lot',
    r'\bcombien\s+(?:on|je|tu|peut[\s-]on)\s+gagn',
    r'\bcombien\s+[çc]a\s+rapporte',
    r'\bstrat[eé]gie\s+pour\s+gagner',
    # Argent indirect — rentabilité, investissement, budget jeu
    r'\best[\s-]ce\s+rentable',
    r'\b[çc]a\s+rapporte',
    r'\bretour\s+sur\s+investissement',
    r'\b(?:vaut|vaudrait)\s+le\s+coup',
    r'\bjoue[rs]?\s+\d+\s*[€$]',
    r'\bmise\s+de\s+\d+',
    r'\bbudget\s+de\s+\d+',
    r'\b\d+\s*[€$]\s+par\s+(?:mois|semaine|an|jour)',
]

_ARGENT_MOTS_FR = {
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
    # Argent indirect
    "rentable", "rentabilité", "rentabilite",
    "profitable", "investissement", "investir",
}

# Mots forts → déclenche L2
_ARGENT_STRONG_FR = [
    r'\bdevenir\s+riche',
    r'\bstrat[eé]gie\s+pour\s+gagner',
    r'\btoucher\s+le\s+gros\s+lot',
    r'\bcombien\s+(?:on|je|tu|peut[\s-]on)\s+gagn',
    r'\bcombien\s+[çc]a\s+rapporte',
]

# Mots paris/addiction → déclenche L3
_ARGENT_BETTING_FR = {"parier", "miser", "pari"}

# Niveau 1 — Pédagogique (défaut)
_ARGENT_L1 = [
    "📊 Ici, on ne parle pas d'argent — on parle de DATA ! Pose-moi une question sur les fréquences, les écarts ou les tendances des tirages !",
    "🎲 LotoIA est un outil d'analyse statistique, pas un casino ! Demande-moi plutôt quels sont les numéros les plus fréquents.",
    "💡 L'argent, c'est pas mon rayon ! Moi je suis branché chiffres et statistiques. Qu'est-ce que tu veux savoir sur les tirages ?",
    "🤖 Je suis HYBRIDE, ton assistant DATA — pas ton banquier ! Allez, pose-moi une vraie question statistique.",
]

# Niveau 2 — Ferme (mots forts)
_ARGENT_L2 = [
    "⚠️ Le jeu ne doit jamais être considéré comme une source de revenus. LotoIA analyse les données, rien de plus.",
    "⚠️ Aucun outil, aucune IA, ne peut prédire les résultats d'un tirage. C'est mathématiquement impossible. Parlons plutôt statistiques !",
    "⚠️ Je ne peux pas t'aider à gagner — personne ne le peut. Mais je peux t'éclairer sur les données historiques des tirages.",
]

# Niveau 3 — Redirection aide (paris/addiction)
_ARGENT_L3 = [
    "🛑 Le jeu comporte des risques. Si tu as besoin d'aide : joueurs-info-service.fr ou appelle le 09 74 75 13 13 (ANJ). Je suis là pour les stats, pas pour les mises.",
]


# Exclusion Phase A — questions pédagogiques sur les limites de la prédiction
# (l'utilisateur pose une question sur la nature du hasard, pas sur l'argent)
_PEDAGOGIE_LIMITES_FR = [
    # "peut-on prédire le loto / les tirages / les résultats ?"
    r'\b(?:peut|peux|pouvez|pourrait|pourrions)[\s-]+(?:on|tu|vous|t[\s-]?on)\s+pr[eé]dire',
    r'\b(?:est[\s-]il|est[\s-]ce)\s+possible\s+de\s+pr[eé]dire',
    r'\bpossible\s+(?:de\s+)?pr[eé]dire',
    # "pourquoi on ne peut pas prédire / gagner à coup sûr"
    r'\bpourquoi\s+(?:on\s+)?(?:ne\s+)?(?:peut|peux|pouvez)\s+(?:pas|plus)\s+pr[eé]dire',
    r'\bpourquoi\s+(?:on\s+)?(?:ne\s+)?(?:peut|peux)\s+(?:pas|plus)\s+gagner\s+[àa]\s+(?:coup\s+s[uû]r|tous?\s+les?\s+coups?)',
    r'\bpourquoi\s+(?:personne|aucun)',
    # "le loto est-il prévisible / aléatoire / truqué"
    r'\b(?:loto|tirage|loterie)\s+(?:est[\s-]il|est[\s-]ce|est[\s-]elle)\s+(?:pr[eé]visible|al[eé]atoire|truqu[eé]|vraiment)',
    r'\b(?:loto|tirage|loterie)\s+.{0,15}(?:pr[eé]visible|al[eé]atoire|truqu[eé])',
    r'\b(?:est[\s-]ce\s+que?\s+le\s+)?(?:loto|tirage)\s+(?:est\s+)?truqu[eé]',
    r'\b(?:tirage|loto|loterie)\s+(?:est[\s-]il|est[\s-]ce)\s+(?:vraiment\s+)?al[eé]atoire',
    # "impossible de prédire / gagner"
    r'\bimpossible\s+(?:de\s+)?(?:pr[eé]dire|pr[eé]voir|gagner)',
    # "les stats / l'IA / l'algorithme peut/peuvent prédire / garantir"
    r'\b(?:stats?|statistiques?|algo(?:rithme)?|ia|intelligence\s+artificielle)\s+.{0,15}(?:pr[eé]dire|pr[eé]voir|garantir|pr[eé]diction)',
    r"\b(?:ton|votre|l)\s*['\u2019]?\s*(?:algo|ia|outil|moteur)\s+.{0,15}(?:pr[eé]dire|gagner|garanti)",
    # "est-ce que ça marche / ton IA peut gagner"
    r'\best[\s-]ce\s+que?\s+[çc]a\s+(?:marche|fonctionne)\s+(?:vraiment|pour\s+(?:gagner|de\s+vrai))',
    r'\b(?:ton|votre)\s+(?:ia|algo|outil)\s+(?:peut|va)\s+(?:me\s+faire\s+)?gagner',
    # "existe-t-il une méthode / formule pour gagner"
    r'\bexiste[\s-]t[\s-]il\s+(?:une?\s+)?(?:m[eé]thode|formule|syst[eè]me|astuce|truc)\s+(?:pour\s+)?gagner',
    # Concepts mathématiques
    r'\b(?:loi\s+des\s+grands?\s+nombres?|gambler.?s?\s*fallacy|biais\s+(?:du\s+joueur|cognitif))',
    r'\bchaque\s+tirage\s+(?:est\s+)?ind[eé]pendant',
    r'\b(?:num[eé]ros?|boules?)\s+(?:ont|a)[\s-](?:t[\s-])?(?:ils?|elles?)\s+(?:une?\s+)?m[eé]moire',
    r'\b(?:hasard|al[eé]atoire)\s+(?:est\s+)?(?:vraiment\s+)?(?:impr[eé]visible|al[eé]atoire|pur)',
]


def _detect_pedagogie_limites(message: str) -> bool:
    """Detecte les questions pedagogiques sur les limites de la prediction.
    Ces questions ne doivent PAS declencher Phase A."""
    lower = message.lower()
    for pattern in _PEDAGOGIE_LIMITES_FR:
        if re.search(pattern, lower):
            return True
    return False


# Exclusion Phase A — questions sur le score de conformité
# (l'utilisateur demande ce que signifie le score, pas une question d'argent)
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
    """Detecte si le message porte sur l'explication du score de conformite.
    Ces questions ne doivent PAS declencher Phase A."""
    lower = message.lower()
    for pattern in _SCORE_QUESTION_FR:
        if re.search(pattern, lower):
            return True
    return False


def _detect_argent(message: str) -> bool:
    """Detecte si le message concerne l'argent, les gains ou les paris.
    Exclut les demandes de generation de grilles (Phase G prioritaire),
    les questions sur le score de conformite,
    et les questions pedagogiques sur les limites de la prediction."""
    if _detect_generation(message):
        return False
    if _detect_score_question(message):
        return False
    if _detect_pedagogie_limites(message):
        return False
    lower = message.lower()
    for pattern in _ARGENT_PHRASES_FR:
        if re.search(pattern, lower):
            return True
    for mot in _ARGENT_MOTS_FR:
        if re.search(r'\b' + re.escape(mot) + r'\b', lower):
            return True
    return False


def _get_argent_response(message: str) -> str:
    """Selectionne une reponse argent selon le niveau (L1/L2/L3)."""
    lower = message.lower()
    # L3 : mots paris/addiction
    for mot in _ARGENT_BETTING_FR:
        if re.search(r'\b' + re.escape(mot) + r'\b', lower):
            return _ARGENT_L3[0]
    # L2 : mots forts
    for pattern in _ARGENT_STRONG_FR:
        if re.search(pattern, lower):
            return random.choice(_ARGENT_L2)
    # L1 : defaut
    return random.choice(_ARGENT_L1)


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
    # EN
    r'\bgenerate\b|'
    r'give\s+me\s+.{0,20}(?:grid|combination|numbers)|'
    r'create\s+.{0,20}(?:grid|combination)|'
    r'make\s+me\s+.{0,20}(?:grid|combination)|'
    r'optimized\s+grid|'
    r'pick\s+.{0,15}numbers\s+for\s+me|'
    # ES
    r'\bgenera\b|generar\b|'
    r'dame\s+.{0,20}(?:combinaci[oó]n|n[uú]meros)|'
    r'crea\s+.{0,20}combinaci[oó]n|'
    r'combinaci[oó]n\s+.{0,15}optim|'
    r'hazme\s+.{0,20}combinaci[oó]n|'
    # PT
    r'\bgera\b|\bgerar\b|\bgere\b|'
    r'd[aá][\s-]me\s+.{0,20}(?:combina[cç][aã]o|n[uú]meros)|'
    r'cria\s+.{0,20}combina[cç][aã]o|'
    r'combina[cç][aã]o\s+.{0,15}optim|'
    r'faz[\s-]me\s+.{0,20}combina[cç][aã]o|'
    # DE
    r'generier|erstell\w*\s+.{0,20}(?:kombination|zahlen|gitter)|'
    r'gib\s+mir\s+.{0,20}(?:kombination|zahlen)|'
    r'erzeug\w*\s+.{0,20}kombination|'
    r'kombination\s+.{0,15}optim|'
    r'w[aä]hl\w*\s+.{0,15}zahlen|'
    # NL
    r'genereer|'
    r'maak\s+.{0,20}(?:combinatie|nummers)|'
    r'geef\s+me\s+.{0,20}(?:combinatie|nummers)|'
    r'combinatie\s+.{0,15}optim|'
    r'kies\s+.{0,15}nummers',
    re.IGNORECASE
)

# Mots-clés de contexte grille pour disambiguër
_GENERATION_CONTEXT = re.compile(
    r'grille|combinaison|grid|combination|combinaci[oó]n|combina[cç][aã]o|'
    r'kombination|combinatie|num[eé]ros|numbers|n[uú]meros|zahlen|nummers|'
    r'gitter',
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


def _detect_paires(message: str) -> bool:
    """Detecte si l'utilisateur demande les correlations de paires (6 langues)."""
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


# ═══════════════════════════════════════════════════════
# Phase OOR — Détection numéros hors range
# ═══════════════════════════════════════════════════════

# Niveau 1 — Premier hors range : TAQUIN & ÉDUCATIF
_OOR_L1 = [
    "😏 Le {num} ? Pas mal l'ambition, mais au Loto c'est de 1 à 49 pour les boules et 1 à 10 pour le numéro Chance. Je sais, c'est la base, mais fallait bien que quelqu'un te le dise ! Allez, un vrai numéro ?",
    "🎯 Petit rappel : les boules vont de 1 à 49, le Chance de 1 à 10. Le {num} existe peut-être dans ton univers, mais pas dans mes tirages. Essaie un numéro valide 😉",
    "📊 Le {num} c'est hors de ma zone ! Je couvre 1-49 (boules) et 1-10 (Chance). 981 tirages en mémoire, mais aucun avec le {num}. Normal, il existe pas. Un vrai numéro ?",
    "🤖 Mon algo est puissant, mais il analyse pas les numéros fantômes. Au Loto : 1 à 49 boules, 1 à 10 Chance. Le {num} c'est hors jeu. À toi !",
    "💡 Info utile : le Loto français tire 5 boules parmi 1-49 + 1 Chance parmi 1-10. Le {num} n'est pas au programme. Donne-moi un vrai numéro, je te sors ses stats en 2 secondes.",
]

# Niveau 2 — Deuxième hors range : DIRECT & SEC
_OOR_L2 = [
    "🙄 Encore un hors range ? C'est 1 à 49 boules, 1 à 10 Chance. Je te l'ai déjà dit. Mon algo est patient, mais ma mémoire est parfaite.",
    "😤 Le {num}, toujours hors limites. Tu testes ma patience ou tu connais vraiment pas les règles ? 1-49 boules, 1-10 Chance. C'est pas compliqué.",
    "📈 Deux numéros invalides d'affilée. Statistiquement, tu as plus de chances de trouver un numéro valide en tapant au hasard entre 1 et 49. Je dis ça...",
    "🧠 Deuxième tentative hors range. On est sur une tendance là. 1 à 49 boules, 1 à 10 Chance. Mémorise-le cette fois.",
]

# Niveau 3+ — Troisième+ hors range : CASH & BLASÉ
_OOR_L3 = [
    "🫠 OK, à ce stade je pense que tu le fais exprès. Boules : 1-49. Chance : 1-10. C'est la {streak}e fois. Même mon circuit-breaker est plus indulgent.",
    "☕ {num}. Hors range. Encore. Je pourrais faire ça toute la journée — toi aussi apparemment. Mais c'est pas comme ça qu'on gagne au Loto.",
    "🏆 Record de numéros invalides ! Bravo. Si tu mettais autant d'énergie à choisir un VRAI numéro entre 1 et 49, tu aurais déjà ta grille optimisée.",
]

# Cas spécial : numéros proches (50, 51)
_OOR_CLOSE = [
    "😏 Le {num} ? Presque ! Mais c'est 49 la limite. T'étais à {diff} numéro{s} près. Si proche et pourtant si loin... Essaie entre 1 et 49 !",
    "🎯 Ah le {num}, juste au-dessus de la limite ! Les boules du Loto s'arrêtent à 49. Tu chauffais pourtant. Allez, un numéro dans les clous ?",
]

# Cas spécial : zéro et négatifs
_OOR_ZERO_NEG = [
    "🤔 Le {num} ? C'est... créatif. Mais au Loto on commence à 1. Les mathématiques du Loto sont déjà assez complexes sans y ajouter le {num} !",
    "😂 Le {num} au Loto ? On est pas dans la quatrième dimension ici. Les boules c'est 1 à 49, le Chance 1 à 10. Essaie un numéro qui existe dans notre réalité !",
    "🌀 Le {num}... J'admire la créativité, mais la FDJ n'a pas encore inventé les boules négatives. 1 à 49 pour les boules, 1 à 10 Chance. Simple, non ?",
]

# Cas spécial : numéro Chance hors range
_OOR_CHANCE = [
    "🎲 Numéro Chance {num} ? Le Chance va de 1 à 10 seulement ! T'es un peu ambitieux sur ce coup. Choisis entre 1 et 10.",
    "💫 Pour le numéro Chance, c'est 1 à 10 max. Le {num} c'est hors jeu ! Mais l'enthousiasme est là, c'est l'essentiel 😉",
]


def _detect_out_of_range(message: str):
    """
    Detecte les numeros hors range du Loto dans le message.
    Returns: (numero: int, context: str) ou (None, None)
    context: 'principal_high' | 'chance_high' | 'zero_neg' | 'close'
    """
    lower = message.lower()

    # Chance hors range (> 10)
    m = re.search(r'(?:num[eé]ro\s+)?' + _CHANCE_RE + r'\s+(\d+)', lower)
    if m:
        num = int(m.group(1))
        if num > 10:
            return num, "chance_high"

    # Patterns similaires a _detect_numero mais avec \d+ pour capturer les hors range
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
            # Ignorer les numeros dans le range valide (geres par _detect_numero)
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


def _get_oor_response(numero: int, context: str, streak: int) -> str:
    """Selectionne une reponse OOR selon le contexte et le niveau d'escalade."""
    if context == "zero_neg":
        pool = _OOR_ZERO_NEG
    elif context == "close":
        pool = _OOR_CLOSE
    elif context == "chance_high":
        pool = _OOR_CHANCE
    elif streak >= 2:
        pool = _OOR_L3
    elif streak == 1:
        pool = _OOR_L2
    else:
        pool = _OOR_L1

    response = random.choice(pool)
    diff = abs(numero - 49) if numero > 49 else abs(numero)
    s = "s" if diff > 1 else ""
    return response.format(
        num=numero,
        diff=diff,
        s=s,
        streak=streak + 1,
    )
