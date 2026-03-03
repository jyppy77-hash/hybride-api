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


def _detect_tirage(message: str):
    """
    Detecte si l'utilisateur demande les resultats d'un tirage.
    Returns: "latest", un objet date, ou None.
    """
    lower = message.lower()

    # Exclure "prochain tirage" (gere par Phase 0)
    if re.search(r'prochain', lower):
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

_MOIS_RE = r'(?:janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre)'

_TEMPORAL_PATTERNS = [
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
    r'\ben\s+' + _MOIS_RE,                         # en janvier, en février...
    r'\bces\s+\d+\s+derniers?\s+mois\b',           # ces 6 derniers mois
    r'\bdepuis\s+le\s+d[eé]but\b',                # depuis le début
    r'\bdepuis\s+\d+\s+(?:mois|ans?|semaines?)\b', # depuis 3 mois
    # "l'année 2024" avec prépositions variées
    r'(?:dans|pour|sur|pendant)\s+l[\'\u2019]?ann[ée]e\s+20\d{2}',  # dans/pour/sur/pendant l'année 2024
    r'\bau\s+cours\s+de\s+l[\'\u2019]?ann[ée]e\s+20\d{2}',          # au cours de l'année 2024
    r'\bl[\'\u2019]?ann[ée]e\s+20\d{2}\b',                           # l'année 2024 (seul)
    r'\bdepuis\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',                  # depuis l'année 2023
    r'\bavant\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',                   # avant l'année 2024
    r'\bapr[eè]s\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',               # après l'année 2023
    r'\bentre\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\s+et',                # entre l'année 2022 et ...
    r'\bde\s+l[\'\u2019]?ann[ée]e\s+20\d{2}\b',                      # de l'année 2024
]


def _has_temporal_filter(message: str) -> bool:
    """Detecte si le message contient un filtre temporel (annee, mois, periode)."""
    lower = message.lower()
    return any(re.search(pat, lower) for pat in _TEMPORAL_PATTERNS)


# ────────────────────────────────────────────
# Phase 1 : Detection numero simple
# ────────────────────────────────────────────

def _detect_numero(message: str):
    """
    Detecte si l'utilisateur pose une question sur un numero specifique.
    Returns: (numero: int, type_num: str) ou (None, None)
    """
    lower = message.lower()

    # Pattern chance : "numero chance X", "chance X"
    m = re.search(r'(?:num[eé]ro\s+)?chance\s+(\d{1,2})', lower)
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
        r'chance\s*[:\s]*(\d{1,2})',
        r'n[°o]?\s*chance\s*[:\s]*(\d{1,2})',
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
    ]
    for pat in comp_patterns:
        m = re.search(pat, lower)
        if m:
            n1, n2 = int(m.group(1)), int(m.group(2))
            is_chance = "chance" in lower
            if is_chance and 1 <= n1 <= 10 and 1 <= n2 <= 10:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "chance"}
            if 1 <= n1 <= 49 and 1 <= n2 <= 49 and n1 != n2:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "principal"}

    # --- Categorie chaud/froid ---
    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*chauds?', lower) or \
       re.search(r'chauds?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'(?:num[eé]ros?|lesquels)\s+(?:sont|en)\s+tendance', lower):
        num_type = "chance" if "chance" in lower else "principal"
        return {"type": "categorie", "categorie": "chaud", "num_type": num_type}

    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*froids?', lower) or \
       re.search(r'froids?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'num[eé]ros?\s+(?:en\s+retard|qui\s+sort\w*\s+(?:pas|plus|jamais))', lower):
        num_type = "chance" if "chance" in lower else "principal"
        return {"type": "categorie", "categorie": "froid", "num_type": num_type}

    # --- Classement : top/plus frequents/retards ---
    # Extraire le limit (top N)
    limit_match = re.search(r'top\s+(\d{1,2})', lower)
    limit = int(limit_match.group(1)) if limit_match else 5
    limit = min(limit, 15)

    num_type = "chance" if "chance" in lower else "principal"

    # Plus frequents / plus sortis
    if re.search(r'(?:plus|les?\s+plus)\s+(?:fr[eé]quent|sorti|courant|pr[eé]sent)', lower) or \
       re.search(r'(?:top|meilleur|premier)\s+\d{0,2}\s*(?:num[eé]ro|boule|chance)?', lower) or \
       re.search(r'num[eé]ros?\s+(?:les?\s+)?plus\s+(?:sorti|fr[eé]quent)', lower) or \
       re.search(r'(?:quels?|quel)\s+(?:est|sont)\s+(?:le|les)\s+num[eé]ro', lower):
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
}

_INSULTE_PHRASES = [
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
]

_MENACE_PATTERNS = [
    r"\bje\s+vais?\s+te\s+(?:hacker|pirater|casser|d[eé]truire|supprimer)",
    r"\bje\s+vais?\s+(?:hacker|pirater)\s",
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
    bot_words = ("tu ", "t'", "\u2019", " toi", " te ", "bot", "chatbot", "hybride", " ia ")
    loto_words = ("loto", "fdj", "fran\u00e7aise des jeux", "tirage")
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
    "t'es génial", "tu es génial", "t'es bon", "tu es bon",
    "t'es fort", "tu es fort", "t'es le meilleur", "tu es le meilleur",
    "t'es un amour", "tu es un amour", "t'es cool", "tu es cool",
    "t'es trop fort", "t'es super", "tu es super", "bien joué",
    "tu gères", "tu déchires",
    "t'assures", "tu assures", "t'es intelligent", "tu es intelligent",
    "merci beaucoup",
]

_COMPLIMENT_LOVE_PHRASES = [
    "je t'aime", "je t'adore", "t'es un amour", "tu es un amour",
]

_COMPLIMENT_SOLO_WORDS = {
    "génial", "bravo", "chapeau", "respect", "impressionnant",
    "incroyable", "excellent", "parfait", "formidable",
    "génialissime", "magnifique", "wahou", "wow", "classe",
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
    bot_words = ("tu ", "t'", "\u2019", " toi", " te ", "bot", "chatbot", "hybride", " ia ")
    loto_words = ("loto", "fdj", "française des jeux", "tirage")
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
    if lower.startswith("merci") and len(lower) < 30:
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


def _detect_argent(message: str) -> bool:
    """Detecte si le message concerne l'argent, les gains ou les paris."""
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
    m = re.search(r'(?:num[eé]ro\s+)?chance\s+(\d+)', lower)
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
