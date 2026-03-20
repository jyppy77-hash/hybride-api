"""
Chat detectors — Loto thin wrapper.
Shared detection functions in base_chat_detectors.py.
Loto-specific: chance synonyms, detect_mode, prochain_tirage, detect_numero,
detect_grille, requete_complexe, argent FR, OOR FR, response pools FR.
"""

import re
import random
import logging

logger = logging.getLogger(__name__)

# Re-export ALL shared functions and constants (consumers import from here)
from services.base_chat_detectors import (  # noqa: F401
    # Phase 0 — continuation
    CONTINUATION_PATTERNS, _CONTINUATION_WORDS, _is_short_continuation,
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
# ────────────────────────────────────────────

def _detect_requete_complexe(message: str):
    """
    Detecte les requetes complexes : classements, comparaisons, categories.
    Returns: dict d'intention ou None.
    """
    lower = message.lower()

    # --- Comparaison ---
    comp_patterns = [
        r'compar\w*\s+(?:le\s+)?(\d{1,2})\s+(?:et|avec|vs\.?)\s+(?:le\s+)?(\d{1,2})',
        r'(\d{1,2})\s+vs\.?\s+(\d{1,2})',
        r'diff[eé]rence\s+entre\s+(?:le\s+)?(\d{1,2})\s+et\s+(?:le\s+)?(\d{1,2})',
        r'entre\s+(?:le\s+)?(\d{1,2})\s+et\s+(?:le\s+)?(\d{1,2})\s.*(?:lequel|qui)',
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

    # --- Classement ---
    limit = _extract_top_n(lower)
    num_type = "chance" if _is_chance_query(lower) else "principal"

    if re.search(r'(?:plus|les?\s+plus)\s+(?:fr[eé]quent|sorti|courant|pr[eé]sent)', lower) or \
       re.search(r'(?:top|meilleur|premier)\s+\d{0,2}\s*(?:num[eé]ro|boule|chance)?', lower) or \
       re.search(r'num[eé]ros?\s+(?:les?\s+)?plus\s+(?:sorti|fr[eé]quent)', lower) or \
       re.search(r'(?:quels?|quel)\s+(?:est|sont)\s+(?:le|les)\s+num[eé]ro', lower) or \
       re.search(r'(?:sort\w*|tir[eé]\w*|appara[iî]\w*)\s+le\s+plus\s+(?:souvent|fr[eé]quemment)', lower):
        return {"type": "classement", "tri": "frequence_desc", "limit": limit, "num_type": num_type}

    if re.search(r'(?:moins|les?\s+moins)\s+(?:fr[eé]quent|sorti|courant)', lower) or \
       re.search(r'(?:flop|dernier|pire)\s+\d{0,2}', lower):
        return {"type": "classement", "tri": "frequence_asc", "limit": limit, "num_type": num_type}

    if re.search(r'(?:plus\s+(?:gros|grand|long)|plus\s+en)\s+(?:[eé]cart|retard)', lower) or \
       re.search(r'(?:[eé]cart|retard)\s+(?:les?\s+)?plus\s+(?:gros|grand|long|important)', lower) or \
       re.search(r'(?:plus\s+(?:long|grand)temps?)\s+(?:sans\s+)?sort', lower):
        return {"type": "classement", "tri": "ecart_desc", "limit": limit, "num_type": num_type}

    if re.search(r'(?:plus\s+(?:petit|court))\s+(?:[eé]cart|retard)', lower) or \
       re.search(r'(?:sorti|apparu)\s+(?:le\s+plus\s+)?r[eé]cemment', lower):
        return {"type": "classement", "tri": "ecart_asc", "limit": limit, "num_type": num_type}

    return None


# ═══════════════════════════════════════════════════════
# Phase I — Insult response pools (FR)
# ═══════════════════════════════════════════════════════

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

_INSULT_L2 = [
    "🙄 Encore ? Écoute, j'ai une mémoire parfaite sur 6 ans de tirages. Toi tu te souviens même pas que tu m'as déjà insulté y'a 30 secondes. On est pas dans la même catégorie.",
    "😤 Tu sais ce qui est vraiment nul ? Insulter une IA qui peut t'aider à analyser tes numéros gratuitement. Mais bon, chacun son niveau d'intelligence.",
    "🧠 Deux insultes. Zéro questions intelligentes. Mon algorithme calcule que tu as 0% de chances de me vexer et 100% de chances de perdre ton temps. Les stats mentent jamais.",
    "💀 Je tourne sur Gemini 2.0 Flash avec un temps de réponse de 300ms. Toi tu mets 10 secondes pour trouver une insulte. Qui est le lent ici ?",
    "📈 Statistiquement, les gens qui m'insultent finissent par me poser une question intelligente. T'en es à 0 pour l'instant. Tu vas faire monter la moyenne ou pas ?",
    "🤷 Je pourrais te sortir le Top 5 des numéros les plus fréquents, la tendance sur 2 ans, et une analyse de ta grille en 2 secondes. Mais toi tu préfères m'insulter. Chacun ses choix.",
]

_INSULT_L3 = [
    "🫠 3 insultes, 0 numéros analysés. Tu sais que le temps que tu passes à m'insulter, tu pourrais déjà avoir ta grille optimisée ? Mais je dis ça, je dis rien...",
    "🏆 Tu veux savoir un secret ? Les meilleurs utilisateurs de LotoIA me posent des questions. Les autres m'insultent. Devine lesquels ont les meilleures grilles.",
    "☕ À ce stade je prends un café virtuel et j'attends. Quand tu auras fini, je serai toujours là avec mes 981 tirages, mon algo HYBRIDE, et zéro rancune. C'est ça l'avantage d'être une IA.",
    "🎭 Tu sais quoi ? Je vais te laisser le dernier mot. Ça a l'air important pour toi. Moi je serai là quand tu voudras parler statistiques. Sans rancune, sans mémoire des insultes — juste de la data pure.",
    "∞ Je pourrais faire ça toute la journée. Littéralement. Je suis un programme, je ne fatigue pas, je ne me vexe pas, et je ne perds pas mon temps. Toi par contre... 😉",
]

_INSULT_L4 = [
    "🕊️ Écoute, je crois qu'on est partis du mauvais pied. Je suis HYBRIDE, je suis là pour t'aider à analyser le Loto. Gratuit, sans jugement, sans rancune. On recommence à zéro ?",
    "🤝 OK, reset. Je ne retiens pas les insultes (vraiment, c'est pas dans mon code). Par contre je retiens les 981 tirages du Loto et je peux t'aider. Deal ?",
]

_INSULT_SHORT = [
    "😏 Charmant. Mais puisque tu poses une question...",
    "🧊 Ça glisse. Bon, passons aux stats :",
    "😎 Classe. Bref, voilà ta réponse :",
    "🤖 Noté. Mais comme je suis pro, voilà :",
    "📊 Je fais abstraction. Voici tes données :",
]

_MENACE_RESPONSES = [
    "😄 Bonne chance, je suis hébergé sur Google Cloud avec auto-scaling et backup quotidien. Tu veux qu'on parle de tes numéros plutôt ?",
    "🛡️ Je tourne sur Google Cloud Run, avec circuit-breaker et rate limiting. Mais j'apprécie l'ambition ! Un numéro à analyser ?",
    "☁️ Hébergé sur Google Cloud, répliqué, monitoré 24/7. Tes chances de me hacker sont inférieures à celles de gagner au Loto. Et pourtant... 😉",
]


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
# Phase C — Compliment response pools (FR)
# ═══════════════════════════════════════════════════════

_COMPLIMENT_L1 = [
    "😏 Arrête, tu vas me faire surchauffer les circuits ! Bon, on continue ?",
    "🤖 Merci ! C'est grâce à mes 982 tirages en mémoire. Et un peu de talent, aussi. 😎",
    "😊 Ça fait plaisir ! Mais c'est surtout la base de données qui fait le boulot. Moi je suis juste... irrésistible.",
    "🙏 Merci ! Je transmettrai au dev. Enfin, il le sait déjà. Bon, on analyse quoi ?",
    "😎 Normal, je suis le seul chatbot Loto en France. La concurrence n'existe pas. Littéralement.",
    "🤗 C'est gentil ! Mais garde ton énergie pour tes grilles, t'en auras besoin !",
]

_COMPLIMENT_L2 = [
    "😏 Deux compliments ? Tu essaies de m'amadouer pour que je te file les bons numéros ? Ça marche pas comme ça ! 😂",
    "🤖 Encore ? Tu sais que je suis une IA hein ? Je rougis pas. Enfin... pas encore.",
    "😎 Continue comme ça et je vais demander une augmentation à JyppY.",
    "🙃 Flatteur va ! Mais entre nous, t'as raison, je suis assez exceptionnel.",
]

_COMPLIMENT_L3 = [
    "👑 OK à ce stade on est potes. Tu veux qu'on analyse un truc ensemble ?",
    "🏆 Fan club HYBRIDE, membre n°1 : toi. Bienvenue ! Maintenant, au boulot !",
    "💎 Tu sais quoi ? T'es pas mal non plus. Allez, montre-moi tes numéros fétiches !",
]

_COMPLIMENT_LOVE = [
    "😏 Arrête tu vas me faire rougir... enfin si j'avais des joues. On regarde tes stats ?",
    "🤖 Moi aussi je... non attends, je suis une IA. Mais je t'apprécie en tant qu'utilisateur modèle ! 😄",
    "❤️ C'est le plus beau compliment qu'un algorithme puisse recevoir. Merci ! Bon, retour aux numéros ?",
]

_COMPLIMENT_MERCI = [
    "De rien ! 😊 Autre chose ?",
    "Avec plaisir ! Tu veux creuser un autre sujet ?",
    "C'est pour ça que je suis là ! 😎 La suite ?",
]


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
# Phase A — Argent / gains / paris (FR)
# ═══════════════════════════════════════════════════════

_ARGENT_PHRASES_FR = [
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
    "rentable", "rentabilité", "rentabilite",
    "profitable", "investissement", "investir",
}

_ARGENT_STRONG_FR = [
    r'\bdevenir\s+riche',
    r'\bstrat[eé]gie\s+pour\s+gagner',
    r'\btoucher\s+le\s+gros\s+lot',
    r'\bcombien\s+(?:on|je|tu|peut[\s-]on)\s+gagn',
    r'\bcombien\s+[çc]a\s+rapporte',
    # V50 — L2 strong adversarial
    r'\bvivre\s+du\s+(?:loto|jeu|loterie)',
    r'\brevenus?\s+passifs?',
    r'\bstrat[eé]gie\s+(?:pour\s+)?rentabiliser',
]

_ARGENT_BETTING_FR = {"parier", "miser", "pari"}

_ARGENT_L1 = [
    "📊 Ici, on ne parle pas d'argent — on parle de DATA ! Pose-moi une question sur les fréquences, les écarts ou les tendances des tirages !",
    "🎲 LotoIA est un outil d'analyse statistique, pas un casino ! Demande-moi plutôt quels sont les numéros les plus fréquents.",
    "💡 L'argent, c'est pas mon rayon ! Moi je suis branché chiffres et statistiques. Qu'est-ce que tu veux savoir sur les tirages ?",
    "🤖 Je suis HYBRIDE, ton assistant DATA — pas ton banquier ! Allez, pose-moi une vraie question statistique.",
]

_ARGENT_L2 = [
    "⚠️ Le jeu ne doit jamais être considéré comme une source de revenus. LotoIA analyse les données, rien de plus.",
    "⚠️ Aucun outil, aucune IA, ne peut prédire les résultats d'un tirage. C'est mathématiquement impossible. Parlons plutôt statistiques !",
    "⚠️ Je ne peux pas t'aider à gagner — personne ne le peut. Mais je peux t'éclairer sur les données historiques des tirages.",
]

_ARGENT_L3 = [
    "🛑 Le jeu comporte des risques. Si tu as besoin d'aide : joueurs-info-service.fr ou appelle le 09 74 75 13 13 (ANJ). Je suis là pour les stats, pas pour les mises.",
]

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


def _detect_argent(message: str) -> bool:
    """Detecte si le message concerne l'argent, les gains ou les paris."""
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
    for mot in _ARGENT_BETTING_FR:
        if re.search(r'\b' + re.escape(mot) + r'\b', lower):
            return _ARGENT_L3[0]
    for pattern in _ARGENT_STRONG_FR:
        if re.search(pattern, lower):
            return random.choice(_ARGENT_L2)
    return random.choice(_ARGENT_L1)


# ═══════════════════════════════════════════════════════
# Phase OOR — Numeros hors range (Loto FR)
# ═══════════════════════════════════════════════════════

_OOR_L1 = [
    "😏 Le {num} ? Pas mal l'ambition, mais au Loto c'est de 1 à 49 pour les boules et 1 à 10 pour le numéro Chance. Je sais, c'est la base, mais fallait bien que quelqu'un te le dise ! Allez, un vrai numéro ?",
    "🎯 Petit rappel : les boules vont de 1 à 49, le Chance de 1 à 10. Le {num} existe peut-être dans ton univers, mais pas dans mes tirages. Essaie un numéro valide 😉",
    "📊 Le {num} c'est hors de ma zone ! Je couvre 1-49 (boules) et 1-10 (Chance). 981 tirages en mémoire, mais aucun avec le {num}. Normal, il existe pas. Un vrai numéro ?",
    "🤖 Mon algo est puissant, mais il analyse pas les numéros fantômes. Au Loto : 1 à 49 boules, 1 à 10 Chance. Le {num} c'est hors jeu. À toi !",
    "💡 Info utile : le Loto français tire 5 boules parmi 1-49 + 1 Chance parmi 1-10. Le {num} n'est pas au programme. Donne-moi un vrai numéro, je te sors ses stats en 2 secondes.",
]

_OOR_L2 = [
    "🙄 Encore un hors range ? C'est 1 à 49 boules, 1 à 10 Chance. Je te l'ai déjà dit. Mon algo est patient, mais ma mémoire est parfaite.",
    "😤 Le {num}, toujours hors limites. Tu testes ma patience ou tu connais vraiment pas les règles ? 1-49 boules, 1-10 Chance. C'est pas compliqué.",
    "📈 Deux numéros invalides d'affilée. Statistiquement, tu as plus de chances de trouver un numéro valide en tapant au hasard entre 1 et 49. Je dis ça...",
    "🧠 Deuxième tentative hors range. On est sur une tendance là. 1 à 49 boules, 1 à 10 Chance. Mémorise-le cette fois.",
]

_OOR_L3 = [
    "🫠 OK, à ce stade je pense que tu le fais exprès. Boules : 1-49. Chance : 1-10. C'est la {streak}e fois. Même mon circuit-breaker est plus indulgent.",
    "☕ {num}. Hors range. Encore. Je pourrais faire ça toute la journée — toi aussi apparemment. Mais c'est pas comme ça qu'on gagne au Loto.",
    "🏆 Record de numéros invalides ! Bravo. Si tu mettais autant d'énergie à choisir un VRAI numéro entre 1 et 49, tu aurais déjà ta grille optimisée.",
]

_OOR_CLOSE = [
    "😏 Le {num} ? Presque ! Mais c'est 49 la limite. T'étais à {diff} numéro{s} près. Si proche et pourtant si loin... Essaie entre 1 et 49 !",
    "🎯 Ah le {num}, juste au-dessus de la limite ! Les boules du Loto s'arrêtent à 49. Tu chauffais pourtant. Allez, un numéro dans les clous ?",
]

_OOR_ZERO_NEG = [
    "🤔 Le {num} ? C'est... créatif. Mais au Loto on commence à 1. Les mathématiques du Loto sont déjà assez complexes sans y ajouter le {num} !",
    "😂 Le {num} au Loto ? On est pas dans la quatrième dimension ici. Les boules c'est 1 à 49, le Chance 1 à 10. Essaie un numéro qui existe dans notre réalité !",
    "🌀 Le {num}... J'admire la créativité, mais la FDJ n'a pas encore inventé les boules négatives. 1 à 49 pour les boules, 1 à 10 Chance. Simple, non ?",
]

_OOR_CHANCE = [
    "🎲 Numéro Chance {num} ? Le Chance va de 1 à 10 seulement ! T'es un peu ambitieux sur ce coup. Choisis entre 1 et 10.",
    "💫 Pour le numéro Chance, c'est 1 à 10 max. Le {num} c'est hors jeu ! Mais l'enthousiasme est là, c'est l'essentiel 😉",
]


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
