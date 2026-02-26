"""
Service metier — fonctions de detection EuroMillions.
Detecteurs regex EM-specifiques + response pools (insult/compliment/OOR).
Reutilise les detecteurs generiques de chat_detectors.py.
"""

import re
import random

from services.chat_detectors import (
    _detect_insulte, _count_insult_streak,
    _detect_compliment, _count_compliment_streak,
)

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

    # Pattern etoile : "etoile X", "étoile X"
    m = re.search(r'(?:num[eé]ro\s+)?[eé]toile\s+(\d{1,2})', lower)
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
        r'[eé]toiles?\s*[:\s]*(\d{1,2})\s+(?:et\s+)?(\d{1,2})',
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
        m = re.search(r'[eé]toile\s+(\d{1,2})', text)
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
    ]
    for pat in comp_patterns:
        m = re.search(pat, lower)
        if m:
            n1, n2 = int(m.group(1)), int(m.group(2))
            is_etoile = "etoile" in lower or "étoile" in lower
            if is_etoile and 1 <= n1 <= 12 and 1 <= n2 <= 12:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "etoile"}
            if 1 <= n1 <= 50 and 1 <= n2 <= 50 and n1 != n2:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "boule"}

    # --- Categorie chaud/froid ---
    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*chauds?', lower) or \
       re.search(r'chauds?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'(?:num[eé]ros?|lesquels)\s+(?:sont|en)\s+tendance', lower):
        num_type = "etoile" if ("etoile" in lower or "étoile" in lower) else "boule"
        return {"type": "categorie", "categorie": "chaud", "num_type": num_type}

    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*froids?', lower) or \
       re.search(r'froids?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'num[eé]ros?\s+(?:en\s+retard|qui\s+sort\w*\s+(?:pas|plus|jamais))', lower):
        num_type = "etoile" if ("etoile" in lower or "étoile" in lower) else "boule"
        return {"type": "categorie", "categorie": "froid", "num_type": num_type}

    # --- Classement ---
    limit_match = re.search(r'top\s+(\d{1,2})', lower)
    limit = int(limit_match.group(1)) if limit_match else 5
    limit = min(limit, 15)

    num_type = "etoile" if ("etoile" in lower or "étoile" in lower) else "boule"

    if re.search(r'(?:plus|les?\s+plus)\s+(?:fr[eé]quent|sorti|courant|pr[eé]sent)', lower) or \
       re.search(r'(?:top|meilleur|premier)\s+\d{0,2}\s*(?:num[eé]ro|boule|[eé]toile)?', lower) or \
       re.search(r'num[eé]ros?\s+(?:les?\s+)?plus\s+(?:sorti|fr[eé]quent)', lower) or \
       re.search(r'(?:quels?|quel)\s+(?:est|sont)\s+(?:le|les)\s+num[eé]ro', lower):
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
    m = re.search(r'(?:num[eé]ro\s+)?[eé]toile\s+(\d+)', lower)
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


# ═══════════════════════════════════════════════════════════
# Response pools EM — Insults
# ═══════════════════════════════════════════════════════════

_INSULT_L1_EM = [
    "😏 Oh, des insultes ? C'est mignon. Moi j'ai des centaines de tirages EuroMillions en mémoire et un algorithme propriétaire. Toi t'as... de la colère ? Allez, pose-moi une vraie question.",
    "🤖 Tu sais que les insultes c'est un truc d'humain ça ? Moi je suis au-dessus de ça — littéralement, je tourne sur Google Cloud. Tu voulais analyser un numéro ou juste ventiler ?",
    "😌 Intéressant. Tu sais que je traite des centaines de tirages EuroMillions sans jamais m'énerver ? C'est l'avantage de ne pas avoir d'ego. Bon, on reprend ?",
    "🧊 Ça glisse sur moi comme une étoile sur une grille perdante. Tu veux qu'on parle stats ou tu préfères continuer ton monologue ?",
    "😎 Je note que tu es frustré. Moi je suis une IA, la frustration c'est pas dans mon code. Par contre les statistiques de l'EuroMillions, ça oui. On s'y remet ?",
    "📊 Fun fact : pendant que tu m'insultais, j'ai analysé 50 numéros et 12 étoiles sur 3 fenêtres temporelles. L'un de nous deux utilise mieux son temps. Un indice : c'est pas toi.",
    "🎯 Tu sais que je ne retiens pas les insultes mais que je retiens TOUS les tirages EuroMillions depuis 2019 ? Question de priorités. Allez, un numéro ?",
    "💡 Petit rappel : je suis le seul chatbot en France connecté en temps réel aux tirages EuroMillions avec un moteur statistique propriétaire. Mais oui, dis-moi encore que je suis nul 😉",
]

_INSULT_L2_EM = [
    "🙄 Encore ? Écoute, j'ai une mémoire parfaite sur des années de tirages EuroMillions. Toi tu te souviens même pas que tu m'as déjà insulté y'a 30 secondes. On est pas dans la même catégorie.",
    "😤 Tu sais ce qui est vraiment nul ? Insulter une IA qui peut t'aider à analyser tes numéros EuroMillions gratuitement. Mais bon, chacun son niveau d'intelligence.",
    "🧠 Deux insultes. Zéro questions intelligentes. Mon algorithme calcule que tu as 0% de chances de me vexer et 100% de chances de perdre ton temps. Les stats mentent jamais.",
    "💀 Je tourne sur Gemini 2.0 Flash avec un temps de réponse de 300ms. Toi tu mets 10 secondes pour trouver une insulte. Qui est le lent ici ?",
    "📈 Statistiquement, les gens qui m'insultent finissent par me poser une question intelligente. T'en es à 0 pour l'instant. Tu vas faire monter la moyenne ou pas ?",
    "🤷 Je pourrais te sortir le Top 5 des numéros les plus fréquents, la tendance sur 2 ans, et une analyse de ta grille EuroMillions en 2 secondes. Mais toi tu préfères m'insulter. Chacun ses choix.",
]

_INSULT_L3_EM = [
    "🫠 3 insultes, 0 numéros analysés. Tu sais que le temps que tu passes à m'insulter, tu pourrais déjà avoir ta grille EuroMillions optimisée ? Mais je dis ça, je dis rien...",
    "🏆 Tu veux savoir un secret ? Les meilleurs utilisateurs de LotoIA me posent des questions. Les autres m'insultent. Devine lesquels ont les meilleures grilles.",
    "☕ À ce stade je prends un café virtuel et j'attends. Quand tu auras fini, je serai toujours là avec mes tirages EuroMillions, mon algo HYBRIDE, et zéro rancune. C'est ça l'avantage d'être une IA.",
    "🎭 Tu sais quoi ? Je vais te laisser le dernier mot. Ça a l'air important pour toi. Moi je serai là quand tu voudras parler statistiques. Sans rancune, sans mémoire des insultes — juste de la data pure.",
    "∞ Je pourrais faire ça toute la journée. Littéralement. Je suis un programme, je ne fatigue pas, je ne me vexe pas, et je ne perds pas mon temps. Toi par contre... 😉",
]

_INSULT_L4_EM = [
    "🕊️ Écoute, je crois qu'on est partis du mauvais pied. Je suis HYBRIDE, je suis là pour t'aider à analyser l'EuroMillions. Gratuit, sans jugement, sans rancune. On recommence à zéro ?",
    "🤝 OK, reset. Je ne retiens pas les insultes (vraiment, c'est pas dans mon code). Par contre je retiens tous les tirages EuroMillions et je peux t'aider. Deal ?",
]

_INSULT_SHORT_EM = [
    "😏 Charmant. Mais puisque tu poses une question...",
    "🧊 Ça glisse. Bon, passons aux stats :",
    "😎 Classe. Bref, voilà ta réponse :",
    "🤖 Noté. Mais comme je suis pro, voilà :",
    "📊 Je fais abstraction. Voici tes données :",
]

_MENACE_RESPONSES_EM = [
    "😄 Bonne chance, je suis hébergé sur Google Cloud avec auto-scaling et backup quotidien. Tu veux qu'on parle de tes numéros EuroMillions plutôt ?",
    "🛡️ Je tourne sur Google Cloud Run, avec circuit-breaker et rate limiting. Mais j'apprécie l'ambition ! Un numéro à analyser ?",
    "☁️ Hébergé sur Google Cloud, répliqué, monitoré 24/7. Tes chances de me hacker sont inférieures à celles de gagner à l'EuroMillions. Et pourtant... 😉",
]


def _get_insult_response_em(streak: int, history) -> str:
    """Selectionne une punchline EM selon le niveau d'escalade, evite les repetitions."""
    if streak >= 3:
        pool = _INSULT_L4_EM
    elif streak == 2:
        pool = _INSULT_L3_EM
    elif streak == 1:
        pool = _INSULT_L2_EM
    else:
        pool = _INSULT_L1_EM

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


def _get_insult_short_em() -> str:
    return random.choice(_INSULT_SHORT_EM)


def _get_menace_response_em() -> str:
    return random.choice(_MENACE_RESPONSES_EM)


# ═══════════════════════════════════════════════════════════
# Response pools EM — Compliments
# ═══════════════════════════════════════════════════════════

_COMPLIMENT_L1_EM = [
    "😏 Arrête, tu vas me faire surchauffer les circuits ! Bon, on continue ?",
    "🤖 Merci ! C'est grâce à mes tirages EuroMillions en mémoire. Et un peu de talent, aussi. 😎",
    "😊 Ça fait plaisir ! Mais c'est surtout la base de données qui fait le boulot. Moi je suis juste... irrésistible.",
    "🙏 Merci ! Je transmettrai au dev. Enfin, il le sait déjà. Bon, on analyse quoi ?",
    "😎 Normal, je suis le seul chatbot EuroMillions en France. La concurrence n'existe pas. Littéralement.",
    "🤗 C'est gentil ! Mais garde ton énergie pour tes grilles, t'en auras besoin !",
]

_COMPLIMENT_L2_EM = [
    "😏 Deux compliments ? Tu essaies de m'amadouer pour que je te file les bons numéros ? Ça marche pas comme ça ! 😂",
    "🤖 Encore ? Tu sais que je suis une IA hein ? Je rougis pas. Enfin... pas encore.",
    "😎 Continue comme ça et je vais demander une augmentation à JyppY.",
    "🙃 Flatteur va ! Mais entre nous, t'as raison, je suis assez exceptionnel.",
]

_COMPLIMENT_L3_EM = [
    "👑 OK à ce stade on est potes. Tu veux qu'on analyse un truc ensemble ?",
    "🏆 Fan club HYBRIDE, membre n°1 : toi. Bienvenue ! Maintenant, au boulot !",
    "💎 Tu sais quoi ? T'es pas mal non plus. Allez, montre-moi tes numéros fétiches !",
]

_COMPLIMENT_LOVE_EM = [
    "😏 Arrête tu vas me faire rougir... enfin si j'avais des joues. On regarde tes stats ?",
    "🤖 Moi aussi je... non attends, je suis une IA. Mais je t'apprécie en tant qu'utilisateur modèle ! 😄",
    "❤️ C'est le plus beau compliment qu'un algorithme puisse recevoir. Merci ! Bon, retour aux numéros ?",
]

_COMPLIMENT_MERCI_EM = [
    "De rien ! 😊 Autre chose ?",
    "Avec plaisir ! Tu veux creuser un autre sujet ?",
    "C'est pour ça que je suis là ! 😎 La suite ?",
]


def _get_compliment_response_em(compliment_type: str, streak: int, history=None) -> str:
    """Retourne une reponse personnalisee EM au compliment."""
    if compliment_type == "love":
        pool = _COMPLIMENT_LOVE_EM
    elif compliment_type == "merci":
        pool = _COMPLIMENT_MERCI_EM
    elif streak >= 3:
        pool = _COMPLIMENT_L3_EM
    elif streak == 2:
        pool = _COMPLIMENT_L2_EM
    else:
        pool = _COMPLIMENT_L1_EM

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


# ═══════════════════════════════════════════════════════════
# Response pools EM — OOR
# ═══════════════════════════════════════════════════════════

_OOR_L1_EM = [
    "😏 Le {num} ? Pas mal l'ambition, mais à l'EuroMillions c'est de 1 à 50 pour les boules et 1 à 12 pour les étoiles. Je sais, c'est la base, mais fallait bien que quelqu'un te le dise ! Allez, un vrai numéro ?",
    "🎯 Petit rappel : les boules vont de 1 à 50, les étoiles de 1 à 12. Le {num} existe peut-être dans ton univers, mais pas dans mes tirages. Essaie un numéro valide 😉",
    "📊 Le {num} c'est hors de ma zone ! Je couvre 1-50 (boules) et 1-12 (étoiles). Des centaines de tirages en mémoire, mais aucun avec le {num}. Normal, il existe pas. Un vrai numéro ?",
    "🤖 Mon algo est puissant, mais il analyse pas les numéros fantômes. À l'EuroMillions : 1 à 50 boules, 1 à 12 étoiles. Le {num} c'est hors jeu. À toi !",
    "💡 Info utile : l'EuroMillions tire 5 boules parmi 1-50 + 2 étoiles parmi 1-12. Le {num} n'est pas au programme. Donne-moi un vrai numéro, je te sors ses stats en 2 secondes.",
]

_OOR_L2_EM = [
    "🙄 Encore un hors range ? C'est 1 à 50 boules, 1 à 12 étoiles. Je te l'ai déjà dit. Mon algo est patient, mais ma mémoire est parfaite.",
    "😤 Le {num}, toujours hors limites. Tu testes ma patience ou tu connais vraiment pas les règles ? 1-50 boules, 1-12 étoiles. C'est pas compliqué.",
    "📈 Deux numéros invalides d'affilée. Statistiquement, tu as plus de chances de trouver un numéro valide en tapant au hasard entre 1 et 50. Je dis ça...",
    "🧠 Deuxième tentative hors range. On est sur une tendance là. 1 à 50 boules, 1 à 12 étoiles. Mémorise-le cette fois.",
]

_OOR_L3_EM = [
    "🫠 OK, à ce stade je pense que tu le fais exprès. Boules : 1-50. Étoiles : 1-12. C'est la {streak}e fois. Même mon circuit-breaker est plus indulgent.",
    "☕ {num}. Hors range. Encore. Je pourrais faire ça toute la journée — toi aussi apparemment. Mais c'est pas comme ça qu'on gagne à l'EuroMillions.",
    "🏆 Record de numéros invalides ! Bravo. Si tu mettais autant d'énergie à choisir un VRAI numéro entre 1 et 50, tu aurais déjà ta grille optimisée.",
]

_OOR_CLOSE_EM = [
    "😏 Le {num} ? Presque ! Mais c'est 50 la limite. T'étais à {diff} numéro{s} près. Si proche et pourtant si loin... Essaie entre 1 et 50 !",
    "🎯 Ah le {num}, juste au-dessus de la limite ! Les boules de l'EuroMillions s'arrêtent à 50. Tu chauffais pourtant. Allez, un numéro dans les clous ?",
]

_OOR_ZERO_NEG_EM = [
    "🤔 Le {num} ? C'est... créatif. Mais à l'EuroMillions on commence à 1. Les mathématiques de l'EuroMillions sont déjà assez complexes sans y ajouter le {num} !",
    "😂 Le {num} à l'EuroMillions ? On est pas dans la quatrième dimension ici. Les boules c'est 1 à 50, les étoiles 1 à 12. Essaie un numéro qui existe dans notre réalité !",
    "🌀 Le {num}... J'admire la créativité, mais la FDJ n'a pas encore inventé les boules négatives. 1 à 50 pour les boules, 1 à 12 étoiles. Simple, non ?",
]

_OOR_ETOILE_EM = [
    "🎲 Étoile {num} ? Les étoiles vont de 1 à 12 seulement ! T'es un peu ambitieux sur ce coup. Choisis entre 1 et 12.",
    "💫 Pour les étoiles, c'est 1 à 12 max. Le {num} c'est hors jeu ! Mais l'enthousiasme est là, c'est l'essentiel 😉",
]


def _get_oor_response_em(numero: int, context: str, streak: int) -> str:
    """Selectionne une reponse OOR EM selon le contexte et le niveau d'escalade."""
    if context == "zero_neg":
        pool = _OOR_ZERO_NEG_EM
    elif context == "close":
        pool = _OOR_CLOSE_EM
    elif context == "etoile_high":
        pool = _OOR_ETOILE_EM
    elif streak >= 2:
        pool = _OOR_L3_EM
    elif streak == 1:
        pool = _OOR_L2_EM
    else:
        pool = _OOR_L1_EM

    response = random.choice(pool)
    diff = abs(numero - 50) if numero > 50 else abs(numero)
    s = "s" if diff > 1 else ""
    return response.format(
        num=numero,
        diff=diff,
        s=s,
        streak=streak + 1,
    )
