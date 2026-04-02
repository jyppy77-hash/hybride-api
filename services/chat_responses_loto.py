"""
Response pools for Loto chatbot — FR uniquement.
Insult (L1-L4), compliment (L1-L3/love/merci), menace, argent (L1-L3), OOR (L1-L3).
Mirrors chat_responses_em_en.py / chat_responses_em_multilang.py architecture.

NOTE ARCHITECTURE: Ces pools sont exclusivement en français.
Le Loto est un produit FDJ disponible uniquement en France,
donc l'i18n n'est pas nécessaire pour ce module.
Si expansion multilingue du Loto envisagée à l'avenir,
migrer vers le pattern chat_responses_em_multilang.py (dispatch par langue).
Effort estimé: ~4h (362L à traduire × N langues).
Ref: Audit 360° Chatbot HYBRIDE V81, faille F11.

V70 F08 — extracted from chat_detectors.py for architecture consistency.
"""

import random

# ═══════════════════════════════════════════════════════════
# Phase I — Insult response pools (FR)
# ═══════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════
# Phase C — Compliment response pools (FR)
# ═══════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════
# Phase A — Argent response pools (FR)
# ═══════════════════════════════════════════════════════════

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


def _get_argent_response(message: str, _argent_strong, _argent_betting) -> str:
    """Selectionne une reponse argent selon le niveau (L1/L2/L3).

    Args:
        message: user message (lowercased by caller)
        _argent_strong: list of strong argent regex patterns
        _argent_betting: set of betting keywords
    """
    import re
    lower = message.lower()
    for mot in _argent_betting:
        if re.search(r'\b' + re.escape(mot) + r'\b', lower):
            return _ARGENT_L3[0]
    for pattern in _argent_strong:
        if re.search(pattern, lower):
            return random.choice(_ARGENT_L2)
    return random.choice(_ARGENT_L1)


# ═══════════════════════════════════════════════════════════
# Phase OOR — Numeros hors range (Loto FR)
# ═══════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════
# F05 V72 — Affirmation / Game keyword i18n (Loto)
# ═══════════════════════════════════════════════════════

_AFFIRMATION_INVITATION_LOTO = {
    "fr": (
        "Je suis pret a vous aider ! Que souhaitez-vous analyser ?\n\n"
        "- Statistiques d'un numero (ex: le 7)\n"
        "- Derniers tirages (ex: dernier tirage)\n"
        "- Generer une grille optimisee (ex: genere une grille)\n"
        "- Tendances chaud/froid (ex: numeros chauds)"
    ),
    "en": (
        "I'm ready to help! What would you like to analyse?\n\n"
        "- Number statistics (e.g. number 7)\n"
        "- Latest draws (e.g. last draw)\n"
        "- Generate an optimised grid (e.g. generate a grid)\n"
        "- Hot/cold trends (e.g. hot numbers)"
    ),
    "es": (
        "Estoy listo para ayudarte. Que deseas analizar?\n\n"
        "- Estadisticas de un numero (ej: el 7)\n"
        "- Ultimos sorteos (ej: ultimo sorteo)\n"
        "- Generar una combinacion optimizada (ej: genera una combinacion)\n"
        "- Tendencias caliente/frio (ej: numeros calientes)"
    ),
    "pt": (
        "Estou pronto para te ajudar! O que queres analisar?\n\n"
        "- Estatisticas de um numero (ex: o 7)\n"
        "- Ultimos sorteios (ex: ultimo sorteio)\n"
        "- Gerar uma grelha optimizada (ex: gera uma grelha)\n"
        "- Tendencias quente/frio (ex: numeros quentes)"
    ),
    "de": (
        "Ich bin bereit zu helfen! Was moechtest du analysieren?\n\n"
        "- Statistiken einer Zahl (z.B. die 7)\n"
        "- Letzte Ziehungen (z.B. letzte Ziehung)\n"
        "- Optimierte Kombination generieren (z.B. generiere eine Kombination)\n"
        "- Heiss/kalt Trends (z.B. heisse Zahlen)"
    ),
    "nl": (
        "Ik ben klaar om te helpen! Wat wil je analyseren?\n\n"
        "- Statistieken van een nummer (bv. nummer 7)\n"
        "- Laatste trekkingen (bv. laatste trekking)\n"
        "- Geoptimaliseerde combinatie genereren (bv. genereer een combinatie)\n"
        "- Warm/koud trends (bv. warme nummers)"
    ),
}

_GAME_KEYWORD_INVITATION_LOTO = {
    "fr": (
        "Bienvenue sur HYBRIDE ! Voici ce que je peux faire :\n\n"
        "- Statistiques d'un numero (ex: le 7)\n"
        "- Derniers tirages (ex: dernier tirage)\n"
        "- Generer une grille optimisee (ex: genere une grille)\n"
        "- Tendances chaud/froid (ex: numeros chauds)"
    ),
    "en": (
        "Welcome to HYBRIDE! Here's what I can do:\n\n"
        "- Number statistics (e.g. number 7)\n"
        "- Latest draws (e.g. last draw)\n"
        "- Generate an optimised grid (e.g. generate a grid)\n"
        "- Hot/cold trends (e.g. hot numbers)"
    ),
    "es": (
        "Bienvenido a HYBRIDE! Esto es lo que puedo hacer:\n\n"
        "- Estadisticas de un numero (ej: el 7)\n"
        "- Ultimos sorteos (ej: ultimo sorteo)\n"
        "- Generar una combinacion optimizada (ej: genera una combinacion)\n"
        "- Tendencias caliente/frio (ej: numeros calientes)"
    ),
    "pt": (
        "Bem-vindo ao HYBRIDE! Eis o que posso fazer:\n\n"
        "- Estatisticas de um numero (ex: o 7)\n"
        "- Ultimos sorteios (ex: ultimo sorteio)\n"
        "- Gerar uma grelha optimizada (ex: gera uma grelha)\n"
        "- Tendencias quente/frio (ex: numeros quentes)"
    ),
    "de": (
        "Willkommen bei HYBRIDE! Das kann ich fuer dich tun:\n\n"
        "- Statistiken einer Zahl (z.B. die 7)\n"
        "- Letzte Ziehungen (z.B. letzte Ziehung)\n"
        "- Optimierte Kombination generieren (z.B. generiere eine Kombination)\n"
        "- Heiss/kalt Trends (z.B. heisse Zahlen)"
    ),
    "nl": (
        "Welkom bij HYBRIDE! Dit kan ik voor je doen:\n\n"
        "- Statistieken van een nummer (bv. nummer 7)\n"
        "- Laatste trekkingen (bv. laatste trekking)\n"
        "- Geoptimaliseerde combinatie genereren (bv. genereer een combinatie)\n"
        "- Warm/koud trends (bv. warme nummers)"
    ),
}
