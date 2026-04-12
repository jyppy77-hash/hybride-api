"""
Base chat detectors — Temporal detection (game-agnostic).
Phase T (tirage date detection), temporal filters, temporal date extraction.
Split from base_chat_detect_intent.py (F05 V84).
"""

import re
from datetime import date, timedelta

# ────────────────────────────────────────────
# Phase T : Detection tirage (date / dernier)
# ────────────────────────────────────────────

_JOURS_SEMAINE = {
    # FR
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
    "vendredi": 4, "samedi": 5, "dimanche": 6,
    # EN
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    # ES
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
    # PT (sábado/domingo shared with ES)
    "segunda": 0, "terça": 1, "terca": 1, "quarta": 2, "quinta": 3,
    "sexta": 4,
    # DE
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5, "sonntag": 6,
    # NL
    "maandag": 0, "dinsdag": 1, "woensdag": 2, "donderdag": 3,
    "vrijdag": 4, "zaterdag": 5, "zondag": 6,
}

_TIRAGE_KW = (
    r'(?:'
    r'tirage|r[ée]sultat|num[eé]ro|nuro|boule|sorti|tomb[eé]|tir[eé]'   # FR
    r'|draw|result|number|drawn|ball'                                     # EN
    r'|sorteo|resultado|n[uú]mero|bola'                                   # ES
    r'|sorteio|resultado|n[uú]mero|bola'                                  # PT
    r'|ziehung|ergebnis|zahlen|kugel|gezogen'                             # DE
    r'|trekking|resultaat|uitslag|nummer|getrokken'                       # NL
    r')'
)

_MOIS_TO_NUM = {
    # FR
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
    # EN
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    # ES
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    # PT (abril/agosto shared with ES)
    "janeiro": 1, "fevereiro": 2, "marco": 3,
    "maio": 5, "junho": 6, "julho": 7,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    # DE (april/august shared with EN)
    "januar": 1, "februar": 2, "marz": 3, "maerz": 3,
    "juni": 6, "juli": 7,
    "oktober": 10, "dezember": 12,
    # NL
    "januari": 1, "februari": 2, "maart": 3,
    "mei": 5, "augustus": 8,
}

_MOIS_NOM_RE = (
    r'('
    # FR
    r'janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre'
    # EN
    r'|january|february|march|april|may|june|july|august|september|october|november|december'
    # ES
    r'|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre'
    # PT
    r'|janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|setembro|outubro|novembro|dezembro'
    # DE
    r'|januar|februar|m[aä]rz|juni|juli|oktober|dezember'
    # NL
    r'|januari|februari|maart|mei|augustus'
    r')'
)


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


_NEXT_KW_RE = re.compile(
    r'\b(?:prochain|next|pr[oó]ximo|n[aä]chste|volgende)\b', re.IGNORECASE
)

_LATEST_KW_RE = re.compile(
    r'(?:'
    # FR: "dernier tirage", "dernière sortie"
    r'(?:dernier|derni[eè]re)s?\s+' + _TIRAGE_KW + r'|'
    # EN: "last draw", "latest result"
    r'(?:last|latest|most\s+recent)\s+' + _TIRAGE_KW + r'|'
    # ES: "último sorteo", "último resultado"
    r'[uú]ltimo\s+' + _TIRAGE_KW + r'|'
    # PT: "último sorteio", "último resultado"
    r'[uú]ltimo\s+' + _TIRAGE_KW + r'|'
    # DE: "letzte Ziehung", "letztes Ergebnis"
    r'letzte[nrs]?\s+' + _TIRAGE_KW + r'|'
    # NL: "laatste trekking", "laatste resultaat"
    r'laatste\s+' + _TIRAGE_KW +
    r')', re.IGNORECASE
)

# "quels numéros sont sortis" / "which numbers were drawn" / etc.
_WHICH_DRAWN_RE = re.compile(
    r'(?:'
    r'(?:quels?|quel)\s+(?:num[eé]ro|nuro|boule).*sorti|'            # FR
    r'qu.est.ce\s+qu.*sorti|'                                         # FR
    r'(?:which|what)\s+(?:numbers?|balls?).*(?:drawn|came\s+out)|'    # EN
    r'(?:qu[eé]|cu[aá]le?s?)\s+(?:n[uú]mero|bola).*(?:sali[oó]|result)|'  # ES
    r'(?:quais|que)\s+(?:n[uú]mero|bola).*(?:sa[ií]r|result)|'       # PT
    r'(?:welche)\s+(?:zahlen|kugel).*(?:gezogen|gekommen)|'           # DE
    r'(?:welke)\s+(?:nummers?|ballen?).*(?:getrokken|gekomen)'        # NL
    r')', re.IGNORECASE
)

# "avant-hier" / "day before yesterday" / "anteayer" / "anteontem" / "vorgestern" / "eergisteren"
_DAY_BEFORE_YESTERDAY_RE = re.compile(
    r'\b(?:avant[- ]hier|day\s+before\s+yesterday|anteayer|anteontem|vorgestern|eergisteren)\b',
    re.IGNORECASE,
)

# "hier" / "yesterday" / "ayer" / "ontem" / "gestern" / "gisteren"
_YESTERDAY_RE = re.compile(
    r'\b(?:hier|yesterday|ayer|ontem|gestern|gisteren)\b', re.IGNORECASE
)

# "résultats" / "results" / "resultados" / "Ergebnisse" / "resultaten" (strong standalone)
_RESULTS_STANDALONE_RE = re.compile(
    r'\b(?:r[ée]sultats?|results?|resultados?|ergebnisse?|resultaten?|uitslagen?)\b',
    re.IGNORECASE,
)

# DE date format: "15. März 2026" (dot after day number)
_DE_DATE_RE = re.compile(
    r'(\d{1,2})\.\s*' + _MOIS_NOM_RE + r'(?:\s+(\d{4}))?', re.IGNORECASE
)


def _detect_tirage(message: str) -> date | str | None:
    """
    Detecte si l'utilisateur demande les resultats d'un tirage (6 langues).
    Returns: "latest", un objet date, ou None.
    """
    lower = message.lower()

    # Exclure "prochain tirage" / "next draw" (gere par Phase 0)
    if _NEXT_KW_RE.search(lower):
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

    # Date textuelle : "9 février 2026", "15 January", "3 marzo 2025"
    m = re.search(r'(\d{1,2})\s+' + _MOIS_NOM_RE + r'(?:\s+(\d{4}))?', lower)
    if m and re.search(_TIRAGE_KW, lower):
        day = int(m.group(1))
        month_str = (m.group(2)
                     .replace('\xe9', 'e').replace('\xfb', 'u')
                     .replace('\xe8', 'e').replace('\xe7', 'c')
                     .replace('\xe4', 'a'))
        month = _MOIS_TO_NUM.get(month_str)
        year = int(m.group(3)) if m.group(3) else date.today().year
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    # EN date format: "March 15 2026" / "March 15, 2026" (month before day)
    m = re.search(_MOIS_NOM_RE + r'\s+(\d{1,2})(?:[,.]?\s+(\d{4}))?', lower)
    if m and re.search(_TIRAGE_KW, lower):
        month_str = (m.group(1)
                     .replace('\xe9', 'e').replace('\xfb', 'u')
                     .replace('\xe8', 'e').replace('\xe7', 'c')
                     .replace('\xe4', 'a'))
        month = _MOIS_TO_NUM.get(month_str)
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else date.today().year
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    # DE date format: "15. März 2026"
    m = _DE_DATE_RE.search(lower)
    if m and re.search(_TIRAGE_KW, lower):
        day = int(m.group(1))
        month_str = m.group(2).replace('\xe4', 'a')
        month = _MOIS_TO_NUM.get(month_str)
        year = int(m.group(3)) if m.group(3) else date.today().year
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    # "dernier tirage" / "last draw" / "último sorteo" etc.
    if _LATEST_KW_RE.search(lower):
        return "latest"

    # "quels numéros sont sortis" / "which numbers were drawn" etc.
    if _WHICH_DRAWN_RE.search(lower):
        return "latest"

    # "avant-hier" / "day before yesterday" (tester AVANT "hier")
    if _DAY_BEFORE_YESTERDAY_RE.search(lower) and re.search(_TIRAGE_KW, lower):
        return date.today() - timedelta(days=2)

    # "hier" / "yesterday" / "ayer" / "ontem" / "gestern" / "gisteren"
    if _YESTERDAY_RE.search(lower) and re.search(_TIRAGE_KW, lower):
        return date.today() - timedelta(days=1)
    # "les numeros d'hier" (sans mot-cle tirage explicite)
    if re.search(r"(?:num[eé]ro|nuro)s?\s+d.?hier", lower):
        return date.today() - timedelta(days=1)

    # Jour de la semaine : "tirage de samedi", "draw from Saturday", etc.
    for jour, wd in _JOURS_SEMAINE.items():
        if jour in lower and re.search(_TIRAGE_KW, lower):
            today = date.today()
            delta = (today.weekday() - wd) % 7
            if delta == 0:
                delta = 7
            return today - timedelta(days=delta)

    # "résultats" / "results" / "resultados" seul (indicateur fort)
    if _RESULTS_STANDALONE_RE.search(lower):
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
    r'\ben\s+20\d{2}\b',
    r'\bdepuis\s+20\d{2}\b',
    r'\bavant\s+20\d{2}\b',
    r'\bapr[eè]s\s+20\d{2}\b',
    r'\bentre\s+20\d{2}\s+et\s+20\d{2}',
    r'\bcette\s+ann[ée]e\b',
    r'\bl.ann[ée]e\s+derni[eè]re\b',
    r'\bl.an\s+dernier\b',
    r'\bce\s+mois\b',
    r'\ble\s+mois\s+dernier\b',
    r'\ben\s+' + _MOIS_FR,
    r'\bces\s+\d+\s+derniers?\s+mois\b',
    r'\bdepuis\s+le\s+d[eé]but\b',
    r'\bdepuis\s+\d+\s+(?:mois|ans?|semaines?)\b',
    r'(?:dans|pour|sur|pendant)\s+l[\'\u2019]?ann[ée]e\s+20\d{2}',
    r'\bau\s+cours\s+de\s+l[\'\u2019]?ann[ée]e\s+20\d{2}',
    r'\bl[\'\u2019]?ann[ée]e\s+20\d{2}\b',
    r'\bdepuis\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',
    r'\bavant\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',
    r'\bapr[eè]s\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',
    r'\bentre\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\s+et',
    r'\bde\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',
    r'\bdepuis\s+(?:le\s+)?\d+(?:er)?\s+' + _MOIS_FR + r'\s+20\d{2}',
    r'\bdepuis\s+' + _MOIS_FR + r'\s+20\d{2}',
    r'\b[àa]\s+partir\s+d[eu]\b',
    r'\bles\s+\d+\s+derniers?\s+mois\b',
    r'\bles\s+\d+\s+derni[eè]res?\s+ann[ée]es?\b',
    r'\bces\s+\d+\s+derni[eè]res?\s+ann[ée]es?\b',
    r'\bsur\s+\d+\s+ans?\b',
    # ── EN ──
    r'\bin\s+20\d{2}\b',
    r'\bsince\s+20\d{2}\b',
    r'\bbefore\s+20\d{2}\b',
    r'\bafter\s+20\d{2}\b',
    r'\bbetween\s+20\d{2}\s+and\s+20\d{2}',
    r'\bthis\s+year\b',
    r'\blast\s+year\b',
    r'\bthis\s+month\b',
    r'\blast\s+month\b',
    r'\bin\s+' + _MOIS_EN,
    r'\blast\s+\d+\s+months?\b',
    r'\bsince\s+the\s+beginning\b',
    r'\bsince\s+\d+\s+(?:months?|years?|weeks?)\b',
    r'\bduring\s+(?:the\s+year\s+)?20\d{2}\b',
    r'\bsince\s+' + _MOIS_EN,
    r'\bfrom\s+' + _MOIS_EN,
    r'\b(?:the\s+)?(?:last|past)\s+\d+\s+months?\b',
    r'\b(?:the\s+)?(?:last|past)\s+\d+\s+years?\b',
    r'\bover\s+(?:the\s+)?(?:last|past)\s+\d+\s+years?\b',
    # ── ES ──
    r'\bdesde\s+20\d{2}\b',
    r'\bantes\s+de\s+20\d{2}\b',
    r'\bdespu[eé]s\s+de\s+20\d{2}\b',
    r'\bentre\s+20\d{2}\s+y\s+20\d{2}',
    r'\beste\s+a[nñ]o\b',
    r'\bel\s+a[nñ]o\s+pasado\b',
    r'\beste\s+mes\b',
    r'\bel\s+mes\s+pasado\b',
    r'\ben\s+' + _MOIS_ES,
    r'\bdesde\s+\d+\s+(?:meses|a[nñ]os|semanas)\b',
    r'\bdesde\s+(?:el\s+)?\d+\s+de\s+' + _MOIS_ES,
    r'\bdesde\s+' + _MOIS_ES,
    r'\ba\s+partir\s+de\b',
    r'\blos\s+[úu]ltimos\s+\d+\s+meses\b',
    r'\blos\s+[úu]ltimos\s+\d+\s+a[nñ]os\b',
    # ── PT ──
    r'\bem\s+20\d{2}\b',
    r'\bdesde\s+20\d{2}\b',
    r'\bantes\s+de\s+20\d{2}\b',
    r'\bdepois\s+de\s+20\d{2}\b',
    r'\bentre\s+20\d{2}\s+e\s+20\d{2}',
    r'\beste\s+ano\b',
    r'\bo\s+ano\s+passado\b',
    r'\beste\s+m[eê]s\b',
    r'\bo\s+m[eê]s\s+passado\b',
    r'\bem\s+' + _MOIS_PT,
    r'\bdesde\s+\d+\s+(?:meses|anos|semanas)\b',
    r'\bdesde\s+(?:\d+\s+de\s+)?' + _MOIS_PT,
    r'\b[nd]?os\s+[úu]ltimos\s+\d+\s+meses\b',
    r'\b[nd]?os\s+[úu]ltimos\s+\d+\s+anos\b',
    # ── DE ──
    r'\bim\s+(?:jahr\s+)?20\d{2}\b',
    r'\bseit\s+20\d{2}\b',
    r'\bvor\s+20\d{2}\b',
    r'\bnach\s+20\d{2}\b',
    r'\bzwischen\s+20\d{2}\s+und\s+20\d{2}',
    r'\bdieses\s+jahr\b',
    r'\bletztes\s+jahr\b',
    r'\bdiesen\s+monat\b',
    r'\bletzten\s+monat\b',
    r'\bim\s+' + _MOIS_DE,
    r'\bseit\s+\d+\s+(?:monaten?|jahren?|wochen?)\b',
    r'\bseit\s+(?:dem\s+)?\d+\.\s*' + _MOIS_DE,
    r'\bseit\s+' + _MOIS_DE,
    r'\bab\s+' + _MOIS_DE,
    r'\bdie\s+letzten\s+\d+\s+monate\b',
    r'\bdie\s+letzten\s+\d+\s+jahre\b',
    # ── NL ──
    r'\bin\s+20\d{2}\b',
    r'\bsinds\s+20\d{2}\b',
    r'\bv[oó][oó]r\s+20\d{2}\b',
    r'\bna\s+20\d{2}\b',
    r'\btussen\s+20\d{2}\s+en\s+20\d{2}',
    r'\bdit\s+jaar\b',
    r'\bvorig\s+jaar\b',
    r'\bdeze\s+maand\b',
    r'\bvorige\s+maand\b',
    r'\bin\s+' + _MOIS_NL,
    r'\bsinds\s+\d+\s+(?:maanden?|jaren?|weken?)\b',
    r'\bsinds\s+(?:\d+\s+)?' + _MOIS_NL,
    r'\bvanaf\s+' + _MOIS_NL,
    r'\bde\s+laatste\s+\d+\s+maanden?\b',
    r'\bde\s+laatste\s+\d+\s+jaar\b',
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
