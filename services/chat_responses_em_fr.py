"""
Response pools for EuroMillions chatbot — FR.
Insult (L1-L4), compliment (L1-L3/love/merci), menace, OOR (L1-L3/close/zero_neg/etoile).
Mirrors chat_responses_loto.py architecture.

V73 F02 — extracted from chat_detectors_em_guardrails.py for architecture symmetry.
"""

import random

# ═══════════════════════════════════════════════════════════
# Phase I — Insult response pools (EM FR)
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
# Phase C — Compliment response pools (EM FR)
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

# F09 V84: L4 — redirect to features after 4+ compliments
_COMPLIMENT_L4_EM = [
    "🚀 Merci beaucoup ! Que dirais-tu d'explorer nos fonctionnalités ? Essaie de me poser une question sur les statistiques ou de générer une grille !",
    "🔍 T'es trop sympa ! Mais on a plein de choses à explorer — demande-moi un classement, une comparaison ou une grille optimisée !",
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
    elif streak >= 4:
        pool = _COMPLIMENT_L4_EM
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
# Phase OOR — Numeros hors range (EM FR)
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


# ═══════════════════════════════════════════════════════════
# Phase A — Argent response pools (EM FR)
# ═══════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════
# Phase OOR — Numeros hors range (EM FR)
# ═══════════════════════════════════════════════════════════


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
