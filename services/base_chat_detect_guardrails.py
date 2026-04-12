"""
Base chat detectors — Guardrails (game-agnostic).
Insult detection (L1-L4 escalation), compliment detection (L1-L3),
site rating detection. Split from base_chat_detectors.py (V70 F10).
"""

import re
import random

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
