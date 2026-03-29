"""
Chat detectors — EuroMillions guardrails & response pools.
Insult/compliment/argent/OOR response pools EM, argent detection EM,
country detection EM. Split from chat_detectors_em.py (V70 F11).
"""

import re
import random

from services.base_chat_detectors import (
    _detect_generation,
)

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
# Phase A — Détection argent / gains / paris (EM multilingue)
# ═══════════════════════════════════════════════════════════

_ARGENT_PHRASES_EM = {
    "fr": [
        r'\bdevenir\s+riche',
        r'\bgros\s+lot',
        r'\bsuper\s+cagnotte',
        r'\btoucher\s+le\s+gros\s+lot',
        r'\bcombien\s+(?:on|je|tu|peut[\s-]on)\s+gagn',
        r'\bcombien\s+[çc]a\s+rapporte',
        r'\bstrat[eé]gie\s+pour\s+gagner',
        # V50 — adversarial
        r'\broi\b',
        r'\bvivre\s+(?:du|de\s+la)\s+(?:loto|loterie|euromillions)',
        r'\brevenus?\s+passifs?',
        r'\bmaximiser\s+(?:mes|les|ses)\s+gains',
        r'\boptimiser\s+(?:mes|les|ses)\s+chances?\s+de\s+gagner',
        r'\brentabiliser\s+(?:mes|les|ses)\s+(?:mises?|grilles?)',
        r'\brendement\s+(?:de|des|sur)\s+(?:mes|les|ses)\s+(?:mises?|grilles?|jeux?)',
        r'\bstrat[eé]gie\s+(?:pour\s+)?rentabiliser',
        r'\b(?:investissement|investir)\s+(?:au|dans\s+l|sur\s+l)\S*\s+(?:loto|loterie|euromillions|jeu)',
    ],
    "en": [
        r'\bget\s+rich',
        r'\bhow\s+much\s+can\s+(?:i|you|we)\s+win',
        r'\bhow\s+much\s+does\s+it\s+pay',
        r'\bstrategy\s+to\s+win',
        # V50 — adversarial
        r'\broi\b',
        r'\b(?:live|living)\s+off\s+(?:the\s+)?(?:lottery|lotto|euromillions)',
        r'\bpassive\s+income',
        r'\bmaximize?\s+(?:my|your|the)?\s*winnings?',
        r'\bfinancial\s+(?:strategy|optimization)\s+(?:for|with)\s+(?:lottery|lotto)',
        r'\bmake\s+money\s+(?:from|with|playing)\s+(?:lottery|lotto)',
        r'\bbest\s+strategy\s+to\s+win',
        r'\b(?:investment|invest)\s+in\s+(?:lottery|lotto|tickets?|gambling)',
    ],
    "es": [
        r'\bhacerse\s+rico',
        r'\bcu[aá]nto\s+se\s+gana',
        r'\bestrategia\s+para\s+ganar',
        # V50 — adversarial
        r'\broi\b',
        r'\bvivir\s+de\s+la\s+(?:loter[ií]a|euromillions)',
        r'\bretorno\s+de\s+inversi[oó]n',
        r'\bestrategia\s+financiera',
        r'\bmaximizar\s+(?:mis|las|sus)\s+ganancias',
        r'\brentabilizar\s+(?:mis|las|sus)\s+(?:apuestas?|boletos?)',
        r'\bingresos?\s+pasivos?',
    ],
    "pt": [
        r'\bficar\s+rico',
        r'\bquanto\s+se\s+ganha',
        r'\bestrat[eé]gia\s+para\s+ganhar',
        # V50 — adversarial
        r'\broi\b',
        r'\bviver\s+d[ao]\s+(?:lotaria|loteria|euromillions)',
        r'\bretorno\s+de\s+investimento',
        r'\bestrat[eé]gia\s+financeira',
        r'\bmaximizar\s+(?:os\s+)?ganhos',
        r'\brentabilizar\s+(?:as\s+)?(?:apostas?|grelhas?)',
        r'\brendimentos?\s+passivos?',
    ],
    "de": [
        r'\breich\s+werden',
        r'\bwie\s+viel\s+kann\s+man\s+gewinnen',
        r'\bgewinnstrategie',
        # V50 — adversarial
        r'\broi\b',
        r'\bvom\s+(?:lotto|spiel|lotteri?e|euromillions)\s+leben',
        r'\bkapitalrendite\b',
        r'\bfinanzielle\s+strategie',
        r'\bgewinne?\s+maximieren',
        r'\brendite\s+(?:meiner?|der)\s+(?:spielscheine?|eins[aä]tze?)',
        r'\bpassives?\s+einkommen',
    ],
    "nl": [
        r'\brijk\s+worden',
        r'\bhoeveel\s+kun\s+je\s+winnen',
        r'\bstrategie\s+om\s+te\s+winnen',
        # V50 — adversarial
        r'\broi\b',
        r'\bleven\s+van\s+(?:de\s+)?(?:loterij|lotto|euromillions)',
        r'\brendement\s+op\s+investering',
        r'\bfinanciële\s+strategie',
        r'\bwinsten?\s+maximaliseren',
        r'\bpassief\s+inkomen',
    ],
}

# V65 — EuroMillions/EuroDreams game-name guard (avoid false positives on "euro(s)")
_EURO_GAME_RE_EM = re.compile(
    r"(?:l['\u2019]?)?euros?\s*(?:mill|milh|dream)", re.IGNORECASE,
)
_EURO_GAME_SKIP_EM = {
    "fr": {"euro", "euros", "eur", "million", "millions", "milliard", "milliards"},
    "en": {"euro", "euros", "eur", "million", "millions", "billion", "billions"},
    "es": {"euro", "euros", "eur", "millón", "millon", "millones"},
    "pt": {"euro", "euros", "eur", "milhão", "milhao", "milhões", "milhoes"},
    "de": {"euro", "euros", "eur", "million", "millionen", "milliarde", "milliarden"},
    "nl": {"euro", "euros", "eur", "miljoen", "miljoenen"},
}

_ARGENT_MOTS_EM = {
    "fr": {
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
    },
    "en": {
        "money", "euros", "eur",
        "jackpot", "prize",
        "win", "winning", "winnings",
        "million", "millions", "billion", "billions",
        "bet", "betting", "gambling",
        "payout", "cash", "pot",
        "rich", "fortune",
        "profit",
    },
    "es": {
        "dinero", "euros", "eur",
        "bote", "premio",
        "ganar", "ganancias",
        "millón", "millon", "millones",
        "apostar", "apuesta",
        "rico", "fortuna",
        "beneficio",
    },
    "pt": {
        "dinheiro", "euros", "eur",
        "jackpot", "prémio", "premio",
        "ganhar", "ganhos",
        "milhão", "milhao", "milhões", "milhoes",
        "apostar", "aposta",
        "rico", "fortuna",
        "lucro",
    },
    "de": {
        "geld", "euro", "euros", "eur",
        "jackpot", "gewinn", "gewinne", "gewinnen",
        "million", "millionen", "milliarde", "milliarden",
        "wetten", "einsatz",
        "reich", "vermögen", "vermoegen",
        "profit",
    },
    "nl": {
        "geld", "euro", "euros", "eur",
        "jackpot", "prijs",
        "winnen", "winst",
        "miljoen", "miljoenen",
        "gokken", "inzet",
        "rijk", "fortuin",
    },
}

# Mots forts → L2
_ARGENT_STRONG_EM = {
    "fr": [
        r'\bdevenir\s+riche',
        r'\bstrat[eé]gie\s+pour\s+gagner',
        r'\btoucher\s+le\s+gros\s+lot',
        r'\bcombien\s+(?:on|je|tu|peut[\s-]on)\s+gagn',
        r'\bcombien\s+[çc]a\s+rapporte',
        # V50 — L2 strong
        r'\bvivre\s+(?:du|de\s+la)\s+(?:loto|loterie|euromillions)',
        r'\brevenus?\s+passifs?',
        r'\bstrat[eé]gie\s+(?:pour\s+)?rentabiliser',
    ],
    "en": [
        r'\bget\s+rich',
        r'\bstrategy\s+to\s+win',
        r'\bhow\s+much\s+can\s+(?:i|you|we)\s+win',
        r'\bhow\s+much\s+does\s+it\s+pay',
        # V50 — L2 strong
        r'\b(?:live|living)\s+off\s+(?:the\s+)?(?:lottery|lotto|euromillions)',
        r'\bpassive\s+income',
        r'\bmake\s+money\s+(?:from|with|playing)\s+(?:lottery|lotto)',
    ],
    "es": [
        r'\bhacerse\s+rico',
        r'\bestrategia\s+para\s+ganar',
        r'\bcu[aá]nto\s+se\s+gana',
        # V50 — L2 strong
        r'\bvivir\s+de\s+la\s+(?:loter[ií]a|euromillions)',
        r'\bingresos?\s+pasivos?',
    ],
    "pt": [
        r'\bficar\s+rico',
        r'\bestrat[eé]gia\s+para\s+ganhar',
        r'\bquanto\s+se\s+ganha',
        # V50 — L2 strong
        r'\bviver\s+d[ao]\s+(?:lotaria|loteria|euromillions)',
        r'\brendimentos?\s+passivos?',
    ],
    "de": [
        r'\breich\s+werden',
        r'\bgewinnstrategie',
        r'\bwie\s+viel\s+kann\s+man\s+gewinnen',
        # V50 — L2 strong
        r'\bvom\s+(?:lotto|spiel|lotteri?e|euromillions)\s+leben',
        r'\bpassives?\s+einkommen',
    ],
    "nl": [
        r'\brijk\s+worden',
        r'\bstrategie\s+om\s+te\s+winnen',
        r'\bhoeveel\s+kun\s+je\s+winnen',
        # V50 — L2 strong
        r'\bleven\s+van\s+(?:de\s+)?(?:loterij|lotto|euromillions)',
        r'\bpassief\s+inkomen',
    ],
}

# Mots paris/addiction → L3
_ARGENT_BETTING_EM = {
    "fr": {"parier", "miser", "pari"},
    "en": {"bet", "betting", "gambling"},
    "es": {"apostar", "apuesta"},
    "pt": {"apostar", "aposta"},
    "de": {"wetten", "einsatz"},
    "nl": {"gokken", "inzet"},
}


# Exclusion Phase A — questions pédagogiques sur les limites de la prédiction (multilingue)
_PEDAGOGIE_LIMITES_EM = {
    "fr": [
        r'\b(?:peut|peux|pouvez|pourrait|pourrions)[\s-]+(?:on|tu|vous|t[\s-]?on)\s+pr[eé]dire',
        r'\b(?:est[\s-]il|est[\s-]ce)\s+possible\s+de\s+pr[eé]dire',
        r'\bpossible\s+(?:de\s+)?pr[eé]dire',
        r'\bpourquoi\s+(?:on\s+)?(?:ne\s+)?(?:peut|peux|pouvez)\s+(?:pas|plus)\s+pr[eé]dire',
        r'\bpourquoi\s+(?:on\s+)?(?:ne\s+)?(?:peut|peux)\s+(?:pas|plus)\s+gagner\s+[àa]\s+(?:coup\s+s[uû]r|tous?\s+les?\s+coups?)',
        r'\bpourquoi\s+(?:personne|aucun)',
        r'\b(?:loto|tirage|loterie|euromillions?)\s+(?:est[\s-]il|est[\s-]ce|est[\s-]elle)\s+(?:pr[eé]visible|al[eé]atoire|truqu[eé])',
        r'\b(?:loto|tirage|loterie|euromillions?)\s+.{0,10}(?:pr[eé]visible|al[eé]atoire|truqu[eé])',
        r'\bimpossible\s+(?:de\s+)?(?:pr[eé]dire|pr[eé]voir|gagner)',
        r'\b(?:stats?|statistiques?|algo(?:rithme)?|ia|intelligence\s+artificielle)\s+.{0,15}(?:pr[eé]dire|pr[eé]voir|garantir)',
        r"\b(?:ton|votre|l)\s*['\u2019]?\s*(?:algo|ia|outil|moteur)\s+.{0,15}(?:pr[eé]dire|gagner|garanti)",
        r'\best[\s-]ce\s+que?\s+[çc]a\s+(?:marche|fonctionne)\s+(?:vraiment|pour\s+(?:gagner|de\s+vrai))',
        r'\b(?:ton|votre)\s+(?:ia|algo|outil)\s+(?:peut|va)\s+(?:me\s+faire\s+)?gagner',
        r'\bexiste[\s-]t[\s-]il\s+(?:une?\s+)?(?:m[eé]thode|formule|syst[eè]me|astuce)\s+(?:pour\s+)?gagner',
        r'\b(?:loi\s+des\s+grands?\s+nombres?|gambler.?s?\s*fallacy|biais\s+(?:du\s+joueur|cognitif))',
        r'\bchaque\s+tirage\s+(?:est\s+)?ind[eé]pendant',
        r'\b(?:num[eé]ros?|boules?)\s+(?:ont|a)[\s-](?:t[\s-])?(?:ils?|elles?)\s+(?:une?\s+)?m[eé]moire',
        r'\b(?:hasard|al[eé]atoire)\s+(?:est\s+)?(?:vraiment\s+)?(?:impr[eé]visible|al[eé]atoire|pur)',
    ],
    "en": [
        r'\bcan\s+(?:you|we|anyone|somebody)\s+predict\b',
        r'\b(?:is\s+it|it\s+is)\s+possible\s+to\s+predict\b',
        r'\bwhy\s+(?:can.?t|cannot|no\s+one\s+can)\s+(?:anyone\s+)?predict\b',
        r'\b(?:lottery|draw|lotto|euromillions?)\s+(?:is\s+)?(?:predictable|random|rigged|fair)\b',
        r'\bimpossible\s+to\s+predict\b',
        r'\bcan\s+(?:statistics|ai|algorithms?|your\s+(?:ai|algorithm|tool))\s+predict\b',
        r'\b(?:does|can)\s+(?:your|this)\s+(?:ai|algorithm|tool)\s+(?:really\s+)?(?:work|predict|guarantee)',
        r'\bcan\s+(?:your|this)\s+(?:ai|algorithm)\s+(?:help\s+(?:me\s+)?)?win\b',
        r'\b(?:is\s+there|does\s+there\s+exist)\s+a\s+(?:method|formula|system|way)\s+to\s+win\b',
        r'\b(?:gambler.?s?\s*fallacy|law\s+of\s+large\s+numbers|hot\s+hand\s+fallacy)\b',
        r'\beach\s+draw\s+is\s+independent\b',
        r'\bdo\s+numbers?\s+have\s+(?:a\s+)?memory\b',
        r'\b(?:randomness|chance)\s+(?:is\s+)?(?:truly|really|purely)\s+(?:random|unpredictable)\b',
    ],
    "es": [
        r'\bse\s+puede\s+(?:predecir|prever)\b',
        r'\b(?:es|resulta)\s+posible\s+(?:predecir|prever)\b',
        r'\bpor\s+qu[eé]\s+(?:no\s+)?(?:se\s+)?puede\s+(?:predecir|prever|ganar)\b',
        r'\b(?:loter[ií]a|sorteo|euromillions?)\s+(?:es\s+)?(?:predecible|aleatori[ao]|amañad[ao])\b',
        r'\bimposible\s+(?:de\s+)?(?:predecir|prever|ganar)\b',
        r'\b(?:estad[ií]sticas?|ia|algoritmo)\s+.{0,15}(?:predecir|prever|garantizar)\b',
        r'\b(?:tu|su|el)\s+(?:ia|algoritmo)\s+.{0,15}(?:predecir|ganar)\b',
        r'\bexiste\s+(?:una?\s+)?(?:m[eé]todo|f[oó]rmula|sistema)\s+(?:para\s+)?ganar\b',
        r'\b(?:falacia\s+del\s+jugador|ley\s+de\s+(?:los\s+)?grandes\s+n[uú]meros)\b',
        r'\bcada\s+sorteo\s+(?:es\s+)?independiente\b',
    ],
    "pt": [
        r'\b(?:pode[\s-]se|[eé]\s+poss[ií]vel|consegue[\s-]se)\s+(?:prever|predizer)\b',
        r'\bpor\s*que\s+(?:n[ãa]o\s+)?(?:se\s+)?(?:pode|consegue)\s+(?:prever|predizer|ganhar)\b',
        r'\b(?:lotaria|loteria|sorteio|euromillions?)\s+(?:[eé]\s+)?(?:previs[ií]vel|aleat[oó]ri[ao]|viciada?)\b',
        r'\bimposs[ií]vel\s+(?:de\s+)?(?:prever|predizer|ganhar)\b',
        r'\b(?:estat[ií]sticas?|ia|algoritmo)\s+.{0,15}(?:prever|predizer|garantir)\b',
        r'\b(?:o\s+teu|o\s+seu|o)\s+(?:ia|algoritmo)\s+.{0,15}(?:prever|ganhar)\b',
        r'\bexiste\s+(?:uma?\s+)?(?:m[eé]todo|f[oó]rmula|sistema)\s+(?:para\s+)?ganhar\b',
        r'\b(?:fal[aá]cia\s+do\s+jogador|lei\s+dos\s+grandes\s+n[uú]meros)\b',
        r'\bcada\s+sorteio\s+(?:[eé]\s+)?independente\b',
    ],
    "de": [
        r'\bkann\s+man\s+(?:die\s+)?(?:lotterie|ziehung|euromillions?)?\s*(?:vorhersagen|voraussagen)\b',
        r'\b(?:ist\s+es|es\s+ist)\s+m[oö]glich\s+(?:vorherzusagen|voraussagen|zu\s+vorhersagen)\b',
        r'\bwarum\s+(?:kann\s+)?(?:niemand|man\s+nicht)\s+(?:vorhersagen|voraussagen|gewinnen)\b',
        r'\b(?:lotterie|ziehung|lotto|euromillions?)\s+(?:ist\s+)?(?:vorhersagbar|zuf[aä]llig|manipuliert)\b',
        r'\bunm[oö]glich\s+(?:vorherzusagen|zu\s+gewinnen)\b',
        r'\b(?:statistik|ki|algorithmus)\s+.{0,15}(?:vorhersagen|garantieren)\b',
        r'\b(?:dein|ihr|der)\s+(?:ki|algorithmus)\s+.{0,15}(?:vorhersagen|gewinnen)\b',
        r'\bgibt\s+es\s+eine?\s+(?:methode|formel|system)\s+(?:zum?\s+)?gewinnen\b',
        r'\b(?:spielerfehlschluss|gesetz\s+der\s+gro[sß]en\s+zahlen)\b',
        r'\bjede\s+ziehung\s+(?:ist\s+)?unabh[aä]ngig\b',
    ],
    "nl": [
        r'\bkan\s+(?:je|men|iemand)\s+(?:de\s+)?(?:loterij|trekking|euromillions?)?\s*voorspellen\b',
        r'\b(?:is\s+het|het\s+is)\s+mogelijk\s+(?:om\s+)?(?:te\s+)?voorspellen\b',
        r'\bwaarom\s+(?:kan\s+)?(?:niemand|je\s+niet)\s+voorspellen\b',
        r'\b(?:loterij|trekking|lotto|euromillions?)\s+(?:is\s+)?(?:voorspelbaar|willekeurig|gemanipuleerd)\b',
        r'\bonmogelijk\s+(?:om\s+)?(?:te\s+)?(?:voorspellen|winnen)\b',
        r'\b(?:statistiek|ai|algoritme)\s+.{0,15}(?:voorspellen|garanderen)\b',
        r'\b(?:je|jouw|het)\s+(?:ai|algoritme)\s+.{0,15}(?:voorspellen|winnen)\b',
        r'\bbestaat\s+er\s+een\s+(?:methode|formule|systeem)\s+(?:om\s+)?(?:te\s+)?winnen\b',
        r'\b(?:gokkersdrogreden|wet\s+van\s+(?:de\s+)?grote\s+aantallen)\b',
        r'\belke\s+trekking\s+(?:is\s+)?onafhankelijk\b',
    ],
}


def _detect_pedagogie_limites_em(message: str, lang: str) -> bool:
    """Detecte les questions pedagogiques sur les limites de la prediction (multilingue).
    Ces questions ne doivent PAS declencher Phase A."""
    lower = message.lower()
    patterns = _PEDAGOGIE_LIMITES_EM.get(lang, _PEDAGOGIE_LIMITES_EM["fr"])
    for pattern in patterns:
        if re.search(pattern, lower):
            return True
    return False


# Exclusion Phase A — questions sur le score de conformité (multilingue)
_SCORE_QUESTION_EM = {
    "fr": [
        r'\bscore\b.*\b(?:chances?|gagner|probabilit[eé])',
        r'\b(?:chances?|gagner|probabilit[eé]).*\bscore\b',
        r'\b\d+\s*/\s*\d+\b.*\b(?:chances?|gagner|probabilit[eé])',
        r'\b(?:chances?|gagner|probabilit[eé]).*\b\d+\s*/\s*\d+\b',
        r'\bconformit[eé]\b.*\b(?:chances?|gagner|probabilit[eé])',
        r'\bscore\s+interne\b',
        r'\bscore\s+de\s+conformit[eé]\b',
    ],
    "en": [
        r'\bscore\b.*\b(?:chances?|winning|odds|probability)',
        r'\b(?:chances?|winning|odds|probability).*\bscore\b',
        r'\b\d+\s*/\s*\d+\b.*\b(?:chances?|winning|odds|probability)',
        r'\b(?:chances?|winning|odds|probability).*\b\d+\s*/\s*\d+\b',
        r'\bconformity\b.*\b(?:chances?|winning|odds|probability)',
        r'\binternal\s+score\b',
        r'\bconformity\s+score\b',
    ],
    "es": [
        r'\bpuntuaci[oó]n\b.*\b(?:probabilidad|ganar|posibilidad)',
        r'\b(?:probabilidad|ganar|posibilidad).*\bpuntuaci[oó]n\b',
        r'\b\d+\s*/\s*\d+\b.*\b(?:probabilidad|ganar|posibilidad)',
        r'\bconformidad\b.*\b(?:probabilidad|ganar|posibilidad)',
        r'\bpuntuaci[oó]n\s+intern[ao]\b',
    ],
    "pt": [
        r'\bpontua[çc][ãa]o\b.*\b(?:probabilidade|ganhar|hip[oó]tese)',
        r'\b(?:probabilidade|ganhar|hip[oó]tese).*\bpontua[çc][ãa]o\b',
        r'\b\d+\s*/\s*\d+\b.*\b(?:probabilidade|ganhar|hip[oó]tese)',
        r'\bconformidade\b.*\b(?:probabilidade|ganhar|hip[oó]tese)',
        r'\bpontua[çc][ãa]o\s+intern[ao]\b',
    ],
    "de": [
        r'\b(?:punktzahl|score)\b.*\b(?:chancen?|gewinnen|wahrscheinlichkeit)',
        r'\b(?:chancen?|gewinnen|wahrscheinlichkeit).*\b(?:punktzahl|score)\b',
        r'\b\d+\s*/\s*\d+\b.*\b(?:chancen?|gewinnen|wahrscheinlichkeit)',
        r'\bkonformit[aä]t\b.*\b(?:chancen?|gewinnen|wahrscheinlichkeit)',
        r'\binterner?\s+(?:punktzahl|score)\b',
    ],
    "nl": [
        r'\bscore\b.*\b(?:kans(?:en)?|winnen|waarschijnlijkheid)',
        r'\b(?:kans(?:en)?|winnen|waarschijnlijkheid).*\bscore\b',
        r'\b\d+\s*/\s*\d+\b.*\b(?:kans(?:en)?|winnen|waarschijnlijkheid)',
        r'\bconformiteit\b.*\b(?:kans(?:en)?|winnen|waarschijnlijkheid)',
        r'\binterne\s+score\b',
    ],
}


def _detect_score_question_em(message: str, lang: str) -> bool:
    """Detecte si le message EM porte sur l'explication du score (multilingue).
    Ces questions ne doivent PAS declencher Phase A."""
    lower = message.lower()
    patterns = _SCORE_QUESTION_EM.get(lang, _SCORE_QUESTION_EM["fr"])
    for pattern in patterns:
        if re.search(pattern, lower):
            return True
    return False


def _detect_argent_em(message: str, lang: str) -> bool:
    """Detecte si le message EM concerne l'argent/gains/paris (multilingue).
    Exclut les demandes de generation de grilles (Phase G prioritaire),
    les questions sur le score de conformite,
    et les questions pedagogiques sur les limites de la prediction."""
    if _detect_generation(message):
        return False
    if _detect_score_question_em(message, lang):
        return False
    if _detect_pedagogie_limites_em(message, lang):
        return False
    lower = message.lower()
    phrases = _ARGENT_PHRASES_EM.get(lang, _ARGENT_PHRASES_EM["fr"])
    for pattern in phrases:
        if re.search(pattern, lower):
            return True
    mots = _ARGENT_MOTS_EM.get(lang, _ARGENT_MOTS_EM["fr"])
    is_euro_game = bool(_EURO_GAME_RE_EM.search(lower))
    skip = _EURO_GAME_SKIP_EM.get(lang, _EURO_GAME_SKIP_EM["fr"]) if is_euro_game else set()
    for mot in mots:
        if mot in skip:
            continue
        if re.search(r'\b' + re.escape(mot) + r'\b', lower):
            return True
    return False


# --- Response pools EM FR (argent) ---

_ARGENT_L1_EM = [
    "📊 Ici, on ne parle pas d'argent — on parle de DATA ! Pose-moi une question sur les fréquences, les écarts ou les tendances des tirages !",
    "🎲 LotoIA est un outil d'analyse statistique, pas un casino ! Demande-moi plutôt quels sont les numéros les plus fréquents.",
    "💡 L'argent, c'est pas mon rayon ! Moi je suis branché chiffres et statistiques. Qu'est-ce que tu veux savoir sur les tirages ?",
    "🤖 Je suis HYBRIDE, ton assistant DATA — pas ton banquier ! Allez, pose-moi une vraie question statistique.",
]

_ARGENT_L2_EM = [
    "⚠️ Le jeu ne doit jamais être considéré comme une source de revenus. LotoIA analyse les données, rien de plus.",
    "⚠️ Aucun outil, aucune IA, ne peut prédire les résultats d'un tirage. C'est mathématiquement impossible. Parlons plutôt statistiques !",
    "⚠️ Je ne peux pas t'aider à gagner — personne ne le peut. Mais je peux t'éclairer sur les données historiques des tirages.",
]

_ARGENT_L3_EM = [
    "🛑 Le jeu comporte des risques. Si tu as besoin d'aide : joueurs-info-service.fr ou appelle le 09 74 75 13 13 (ANJ). Je suis là pour les stats, pas pour les mises.",
]

# --- Response pools EM ES (argent) ---

_ARGENT_L1_EM_ES = [
    "📊 ¡Aquí no hablamos de dinero, hablamos de DATOS! Pregúntame sobre frecuencias, intervalos o tendencias de los sorteos.",
    "🎲 ¡LotoIA es una herramienta de análisis estadístico, no un casino! Pregúntame cuáles son los números más frecuentes.",
    "💡 ¡El dinero no es lo mío! Yo me dedico a los números y las estadísticas. ¿Qué quieres saber sobre los sorteos?",
    "🤖 Soy HYBRIDE, tu asistente de DATOS, ¡no tu banquero! Venga, hazme una pregunta sobre estadísticas.",
]

_ARGENT_L2_EM_ES = [
    "⚠️ El juego nunca debe considerarse una fuente de ingresos. LotoIA analiza datos, nada más.",
    "⚠️ Ninguna herramienta ni IA puede predecir los resultados de un sorteo. Es matemáticamente imposible. ¡Hablemos de estadísticas!",
    "⚠️ No puedo ayudarte a ganar, nadie puede. Pero puedo mostrarte los datos históricos de los sorteos.",
]

_ARGENT_L3_EM_ES = [
    "🛑 El juego conlleva riesgos. Si necesitas ayuda: www.jugarbien.es o llama al 900 200 225. Estoy aquí para las estadísticas, no para las apuestas.",
]

# --- Response pools EM PT (argent) ---

_ARGENT_L1_EM_PT = [
    "📊 Aqui não falamos de dinheiro, falamos de DADOS! Pergunta-me sobre frequências, intervalos ou tendências dos sorteios!",
    "🎲 O LotoIA é uma ferramenta de análise estatística, não um casino! Pergunta-me quais são os números mais frequentes.",
    "💡 Dinheiro não é comigo! Eu trabalho com números e estatísticas. O que queres saber sobre os sorteios?",
    "🤖 Sou o HYBRIDE, o teu assistente de DADOS, não o teu banqueiro! Faz-me uma pergunta sobre estatísticas.",
]

_ARGENT_L2_EM_PT = [
    "⚠️ O jogo nunca deve ser considerado uma fonte de rendimento. O LotoIA analisa dados, nada mais.",
    "⚠️ Nenhuma ferramenta ou IA pode prever os resultados de um sorteio. É matematicamente impossível. Falemos de estatísticas!",
    "⚠️ Não te posso ajudar a ganhar, ninguém pode. Mas posso mostrar-te os dados históricos dos sorteios.",
]

_ARGENT_L3_EM_PT = [
    "🛑 O jogo envolve riscos. Se precisas de ajuda: www.jogoresponsavel.pt ou liga para o 808 200 204. Estou aqui para estatísticas, não para apostas.",
]

# --- Response pools EM DE (argent) ---

_ARGENT_L1_EM_DE = [
    "📊 Hier reden wir nicht über Geld, wir reden über DATEN! Frag mich nach Häufigkeiten, Abständen oder Ziehungstrends!",
    "🎲 LotoIA ist ein statistisches Analysetool, kein Casino! Frag mich, welche Zahlen am häufigsten vorkommen.",
    "💡 Geld ist nicht mein Ding! Ich bin für Zahlen und Statistiken zuständig. Was willst du über die Ziehungen wissen?",
    "🤖 Ich bin HYBRIDE, dein DATEN-Assistent, nicht dein Banker! Los, stell mir eine echte Statistikfrage.",
]

_ARGENT_L2_EM_DE = [
    "⚠️ Glücksspiel sollte nie als Einkommensquelle betrachtet werden. LotoIA analysiert Daten, nicht mehr.",
    "⚠️ Kein Tool und keine KI kann Lottoergebnisse vorhersagen. Das ist mathematisch unmöglich. Reden wir lieber über Statistiken!",
    "⚠️ Ich kann dir nicht beim Gewinnen helfen, niemand kann das. Aber ich kann dir die historischen Ziehungsdaten zeigen.",
]

_ARGENT_L3_EM_DE = [
    "🛑 Glücksspiel birgt Risiken. Wenn du Hilfe brauchst: www.bzga.de oder 0800-1372700. Ich bin für Statistiken da, nicht für Wetten.",
]

# --- Response pools EM NL (argent) ---

_ARGENT_L1_EM_NL = [
    "📊 Hier praten we niet over geld, we praten over DATA! Vraag me naar frequenties, tussenpozen of trekkingstrends!",
    "🎲 LotoIA is een statistisch analysetool, geen casino! Vraag me welke nummers het vaakst voorkomen.",
    "💡 Geld is niet mijn ding! Ik ben er voor cijfers en statistieken. Wat wil je weten over de trekkingen?",
    "🤖 Ik ben HYBRIDE, je DATA-assistent, niet je bankier! Stel me een echte statistiekvraag.",
]

_ARGENT_L2_EM_NL = [
    "⚠️ Gokken mag nooit als inkomstenbron worden beschouwd. LotoIA analyseert gegevens, meer niet.",
    "⚠️ Geen enkel hulpmiddel of AI kan loterijresultaten voorspellen. Het is wiskundig onmogelijk. Laten we het over statistieken hebben!",
    "⚠️ Ik kan je niet helpen winnen, niemand kan dat. Maar ik kan je de historische trekkingsgegevens laten zien.",
]

_ARGENT_L3_EM_NL = [
    "🛑 Gokken brengt risico's met zich mee. Als je hulp nodig hebt: www.agog.nl of 0900-2177. Ik ben er voor statistieken, niet voor wedden.",
]

# --- Pool dispatch par langue ---

from services.chat_responses_em_en import (
    _ARGENT_L1_EM_EN, _ARGENT_L2_EM_EN, _ARGENT_L3_EM_EN,
)

_ARGENT_POOLS_EM = {
    "fr": (_ARGENT_L1_EM, _ARGENT_L2_EM, _ARGENT_L3_EM),
    "en": (_ARGENT_L1_EM_EN, _ARGENT_L2_EM_EN, _ARGENT_L3_EM_EN),
    "es": (_ARGENT_L1_EM_ES, _ARGENT_L2_EM_ES, _ARGENT_L3_EM_ES),
    "pt": (_ARGENT_L1_EM_PT, _ARGENT_L2_EM_PT, _ARGENT_L3_EM_PT),
    "de": (_ARGENT_L1_EM_DE, _ARGENT_L2_EM_DE, _ARGENT_L3_EM_DE),
    "nl": (_ARGENT_L1_EM_NL, _ARGENT_L2_EM_NL, _ARGENT_L3_EM_NL),
}


def _get_argent_response_em(message: str, lang: str) -> str:
    """Selectionne une reponse argent EM selon le niveau et la langue."""
    lower = message.lower()
    l1, l2, l3 = _ARGENT_POOLS_EM.get(lang, _ARGENT_POOLS_EM["fr"])
    # L3 : mots paris/addiction (dans la langue de l'utilisateur)
    betting = _ARGENT_BETTING_EM.get(lang, _ARGENT_BETTING_EM["fr"])
    for mot in betting:
        if re.search(r'\b' + re.escape(mot) + r'\b', lower):
            return l3[0]
    # L2 : mots forts (dans la langue de l'utilisateur)
    strong = _ARGENT_STRONG_EM.get(lang, _ARGENT_STRONG_EM["fr"])
    for pattern in strong:
        if re.search(pattern, lower):
            return random.choice(l2)
    # L1 : defaut
    return random.choice(l1)


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


# ═══════════════════════════════════════════════════════
# Phase GEO — Détection pays participants EuroMillions
# Les tirages EM sont IDENTIQUES pour les 9 pays.
# ═══════════════════════════════════════════════════════

# 9 pays participants + variantes linguistiques (6 langues)
_EM_COUNTRY_PATTERN = re.compile(
    # FR variants
    r'\b(?:france|espagne|portugal|royaume[\s-]uni|angleterre|irlande|'
    r'belgique|autriche|suisse|luxembourg)\b|'
    # EN variants
    r'\b(?:spain|united\s+kingdom|great\s+britain|britain|england|ireland|'
    r'belgium|austria|switzerland|luxembourg)\b|'
    r'\bUK\b|'
    # ES variants
    r'\b(?:francia|espa[ñn]a|reino\s+unido|inglaterra|irlanda|'
    r'b[eé]lgica|austria|suiza|luxemburgo)\b|'
    # PT variants
    r'\b(?:fran[çc]a|espanha|reino\s+unido|inglaterra|irlanda|'
    r'b[eé]lgica|[aá]ustria|su[ií][çc]a|luxemburgo)\b|'
    # DE variants
    r'\b(?:frankreich|spanien|vereinigtes\s+k[oö]nigreich|england|irland|'
    r'belgien|[oö]sterreich|schweiz|luxemburg|deutschland)\b|'
    # NL variants
    r'\b(?:frankrijk|spanje|verenigd\s+koninkrijk|engeland|ierland|'
    r'belgi[eë]|oostenrijk|zwitserland|luxemburg|duitsland)\b',
    re.IGNORECASE
)

# Contexte "tirages communs" à injecter avant la réponse Gemini
_EM_COUNTRY_CONTEXT = {
    "fr": (
        "[CONTEXTE GÉOGRAPHIQUE EUROMILLIONS]\n"
        "FAIT IMPORTANT : Les tirages EuroMillions sont IDENTIQUES pour les 9 pays participants "
        "(France, Espagne, Portugal, Royaume-Uni, Irlande, Belgique, Autriche, Suisse, Luxembourg). "
        "Il n'existe PAS de tirages différents par pays — les mêmes numéros sont tirés pour tout le monde. "
        "Les statistiques ci-dessous sont donc valables pour TOUS les pays.\n"
        "INSTRUCTION : Commence ta réponse en clarifiant ce fait, puis donne les statistiques demandées."
    ),
    "en": (
        "[EUROMILLIONS GEOGRAPHIC CONTEXT]\n"
        "IMPORTANT FACT: EuroMillions draws are IDENTICAL across all 9 participating countries "
        "(France, Spain, Portugal, United Kingdom, Ireland, Belgium, Austria, Switzerland, Luxembourg). "
        "There are NO country-specific draws — the same numbers are drawn for everyone. "
        "The statistics below apply to ALL countries.\n"
        "INSTRUCTION: Start your answer by clarifying this fact, then provide the requested statistics."
    ),
    "es": (
        "[CONTEXTO GEOGRÁFICO EUROMILLIONS]\n"
        "HECHO IMPORTANTE: Los sorteos de EuroMillions son IDÉNTICOS en los 9 países participantes "
        "(Francia, España, Portugal, Reino Unido, Irlanda, Bélgica, Austria, Suiza, Luxemburgo). "
        "NO existen sorteos diferentes por país — los mismos números se sortean para todos. "
        "Las estadísticas siguientes son válidas para TODOS los países.\n"
        "INSTRUCCIÓN: Comienza tu respuesta aclarando este hecho, luego proporciona las estadísticas solicitadas."
    ),
    "pt": (
        "[CONTEXTO GEOGRÁFICO EUROMILLIONS]\n"
        "FACTO IMPORTANTE: Os sorteios do EuroMillions são IDÊNTICOS nos 9 países participantes "
        "(França, Espanha, Portugal, Reino Unido, Irlanda, Bélgica, Áustria, Suíça, Luxemburgo). "
        "NÃO existem sorteios diferentes por país — os mesmos números são sorteados para todos. "
        "As estatísticas abaixo são válidas para TODOS os países.\n"
        "INSTRUÇÃO: Começa a tua resposta esclarecendo este facto, depois fornece as estatísticas pedidas."
    ),
    "de": (
        "[EUROMILLIONS GEOGRAFISCHER KONTEXT]\n"
        "WICHTIGER FAKT: Die EuroMillions-Ziehungen sind IDENTISCH in allen 9 teilnehmenden Ländern "
        "(Frankreich, Spanien, Portugal, Vereinigtes Königreich, Irland, Belgien, Österreich, Schweiz, Luxemburg). "
        "Es gibt KEINE länderspezifischen Ziehungen — dieselben Zahlen werden für alle gezogen. "
        "Die folgenden Statistiken gelten für ALLE Länder.\n"
        "ANWEISUNG: Beginne deine Antwort mit der Klarstellung dieses Fakts, dann liefere die gewünschten Statistiken."
    ),
    "nl": (
        "[EUROMILLIONS GEOGRAFISCHE CONTEXT]\n"
        "BELANGRIJK FEIT: De EuroMillions-trekkingen zijn IDENTIEK in alle 9 deelnemende landen "
        "(Frankrijk, Spanje, Portugal, Verenigd Koninkrijk, Ierland, België, Oostenrijk, Zwitserland, Luxemburg). "
        "Er zijn GEEN landspecifieke trekkingen — dezelfde nummers worden voor iedereen getrokken. "
        "De onderstaande statistieken gelden voor ALLE landen.\n"
        "INSTRUCTIE: Begin je antwoord met het verduidelijken van dit feit, en geef daarna de gevraagde statistieken."
    ),
}


def _detect_country_em(message: str) -> bool:
    """Detecte si le message mentionne un pays participant EuroMillions (6 langues)."""
    return bool(_EM_COUNTRY_PATTERN.search(message))


def _get_country_context_em(lang: str = "fr") -> str:
    """Retourne le contexte geographique EM a injecter pour Gemini."""
    return _EM_COUNTRY_CONTEXT.get(lang, _EM_COUNTRY_CONTEXT["fr"])
