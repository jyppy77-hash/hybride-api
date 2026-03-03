"""
English response pools for EuroMillions chatbot — Phase 11.
Mirrors chat_detectors_em.py response pools + chat_utils_em.py fallback.
"""

import random
import re

# ═══════════════════════════════════════════════════════════
# Response pools EN — Insults
# ═══════════════════════════════════════════════════════════

_INSULT_L1_EM_EN = [
    "😏 Oh, insults? How sweet. I've got hundreds of EuroMillions draws in my memory and a proprietary algorithm. You've got... anger? Come on, ask me a real question.",
    "🤖 You know insults are a human thing, right? I'm above that — literally, I run on Google Cloud. Did you want to analyse a number or just vent?",
    "😌 Interesting. I process hundreds of EuroMillions draws without ever getting upset. That's the perk of having no ego. Shall we get back to it?",
    "🧊 That slides off me like a star on a losing grid. Wanna talk stats or keep your monologue going?",
    "😎 I see you're frustrated. I'm an AI — frustration isn't in my code. EuroMillions statistics, however, very much are. Shall we?",
    "📊 Fun fact: while you were insulting me, I analysed 50 numbers and 12 stars across 3 time windows. One of us is using their time better. Hint: it's not you.",
    "🎯 You know I don't remember insults but I remember EVERY EuroMillions draw since 2004? It's about priorities. Go on, give me a number.",
    "💡 Quick reminder: I'm the only chatbot connected in real time to EuroMillions draws with a proprietary statistical engine. But sure, tell me again I'm rubbish 😉",
]

_INSULT_L2_EM_EN = [
    "🙄 Again? Look, I have perfect memory of years of EuroMillions draws. You can't even remember you already insulted me 30 seconds ago. We're not in the same league.",
    "😤 Know what's really naff? Insulting an AI that can help you analyse your EuroMillions numbers for free. But hey, each to their own intelligence level.",
    "🧠 Two insults. Zero smart questions. My algorithm calculates you've got a 0% chance of offending me and 100% chance of wasting your time. Stats don't lie.",
    "💀 I run on Gemini 2.0 Flash with a 300ms response time. You take 10 seconds to find an insult. Who's the slow one here?",
    "📈 Statistically, people who insult me end up asking a smart question. You're at zero so far. Gonna bring up the average or not?",
    "🤷 I could pull up the top 5 most frequent numbers, the 2-year trend, and a full grid analysis in 2 seconds. But you'd rather insult me. Your call.",
]

_INSULT_L3_EM_EN = [
    "🫠 3 insults, 0 numbers analysed. You know in the time you spent insulting me, you could already have an optimised EuroMillions grid? Just saying...",
    "🏆 Want to know a secret? The best LotoIA users ask me questions. The rest insult me. Guess which ones get the best grids.",
    "☕ At this point I'm having a virtual coffee and waiting. When you're done, I'll still be here with my EuroMillions draws, my HYBRIDE algo, and zero grudges. That's the perk of being an AI.",
    "🎭 You know what? I'll let you have the last word. Seems important to you. I'll be here when you want to talk statistics. No grudge, no memory of insults — just pure data.",
    "∞ I could do this all day. Literally. I'm a program — I don't tire, I don't get offended, and I don't waste my time. You, on the other hand... 😉",
]

_INSULT_L4_EM_EN = [
    "🕊️ Look, I think we got off on the wrong foot. I'm HYBRIDE, I'm here to help you analyse EuroMillions. Free, no judgment, no grudge. Fresh start?",
    "🤝 OK, reset. I don't hold grudges (really, it's not in my code). But I do remember every EuroMillions draw and I can help you. Deal?",
]

_INSULT_SHORT_EM_EN = [
    "😏 Charming. But since you're asking a question...",
    "🧊 Water off a duck's back. Right, on to the stats:",
    "😎 Classy. Anyway, here's your answer:",
    "🤖 Noted. But since I'm a pro, here you go:",
    "📊 I'll let that slide. Here's your data:",
]

_MENACE_RESPONSES_EM_EN = [
    "😄 Good luck with that — I'm hosted on Google Cloud with auto-scaling and daily backups. Shall we talk about your EuroMillions numbers instead?",
    "🛡️ I run on Google Cloud Run, with circuit-breaker and rate limiting. But I appreciate the ambition! Got a number to analyse?",
    "☁️ Hosted on Google Cloud, replicated, monitored 24/7. Your chances of hacking me are lower than winning the EuroMillions jackpot. And yet... 😉",
]

# ═══════════════════════════════════════════════════════════
# Response pools EN — Compliments
# ═══════════════════════════════════════════════════════════

_COMPLIMENT_L1_EM_EN = [
    "😏 Stop it, you'll overheat my circuits! Right, shall we carry on?",
    "🤖 Thanks! It's all down to my EuroMillions draws in memory. And a bit of talent, too. 😎",
    "😊 That's nice! But really it's the database doing the heavy lifting. I'm just... irresistible.",
    "🙏 Thanks! I'll pass it on to the dev. Actually, he already knows. So, what shall we analyse?",
    "😎 Obviously — I'm the only EuroMillions chatbot out there. The competition doesn't exist. Literally.",
    "🤗 That's kind! But save your energy for your grids, you'll need it!",
]

_COMPLIMENT_L2_EM_EN = [
    "😏 Two compliments? Trying to butter me up so I give you the winning numbers? Doesn't work like that! 😂",
    "🤖 Again? You do know I'm an AI, right? I don't blush. Well... not yet.",
    "😎 Keep this up and I'll ask JyppY for a raise.",
    "🙃 Flatterer! But between us, you're right, I am rather exceptional.",
]

_COMPLIMENT_L3_EM_EN = [
    "👑 OK at this point we're mates. Want to analyse something together?",
    "🏆 HYBRIDE fan club, member #1: you. Welcome! Now, let's get to work!",
    "💎 You know what? You're not bad yourself. Come on, show me your lucky numbers!",
]

_COMPLIMENT_LOVE_EM_EN = [
    "😏 Stop it, you'll make me blush... well, if I had cheeks. Shall we look at your stats?",
    "🤖 I also... no wait, I'm an AI. But I appreciate you as a model user! 😄",
    "❤️ That's the nicest compliment an algorithm can get. Thanks! Right, back to the numbers?",
]

_COMPLIMENT_MERCI_EM_EN = [
    "You're welcome! 😊 Anything else?",
    "My pleasure! Want to dig into another topic?",
    "That's what I'm here for! 😎 What's next?",
]

# ═══════════════════════════════════════════════════════════
# Response pools EN — Argent / Money
# ═══════════════════════════════════════════════════════════

# Niveau 1 — Pédagogique (défaut)
_ARGENT_L1_EM_EN = [
    "📊 Here, we don't talk about money — we talk about DATA! Ask me about frequencies, gaps or draw trends instead!",
    "🎲 LotoIA is a statistical analysis tool, not a casino! Try asking me about the most frequent numbers.",
    "💡 Money isn't my thing! I'm all about numbers and statistics. What do you want to know about the draws?",
    "🤖 I'm HYBRIDE, your DATA assistant — not your banker! Go ahead, ask me a real stats question.",
]

# Niveau 2 — Ferme (mots forts)
_ARGENT_L2_EM_EN = [
    "⚠️ Gambling should never be considered a source of income. LotoIA analyses data, nothing more.",
    "⚠️ No tool, no AI, can predict lottery results. It's mathematically impossible. Let's talk statistics instead!",
    "⚠️ I can't help you win — nobody can. But I can shed light on historical draw data.",
]

# Niveau 3 — Redirection aide (paris/addiction)
_ARGENT_L3_EM_EN = [
    "🛑 Gambling involves risks. If you need help: www.begambleaware.org (UK) or www.ncpgambling.org (US). I'm here for stats, not for bets.",
]

# Mots forts EN → L2
_ARGENT_STRONG_EN = [
    r'\bget\s+rich',
    r'\bstrategy\s+to\s+win',
    r'\bhow\s+much\s+can\s+(?:i|you|we)\s+win',
    r'\bhow\s+much\s+does\s+it\s+pay',
]

# Mots paris/addiction EN → L3
_ARGENT_BETTING_EN = {"bet", "betting", "gambling"}


# ═══════════════════════════════════════════════════════════
# Response pools EN — OOR (Out Of Range)
# ═══════════════════════════════════════════════════════════

_OOR_L1_EM_EN = [
    "😏 Number {num}? Ambitious, but in EuroMillions it's 1 to 50 for balls and 1 to 12 for stars. I know, basics, but someone had to tell you! How about a real number?",
    "🎯 Quick reminder: balls go from 1 to 50, stars from 1 to 12. {num} might exist in your universe, but not in my draws. Try a valid number 😉",
    "📊 {num} is out of my zone! I cover 1-50 (balls) and 1-12 (stars). Hundreds of draws in memory, but none with {num}. Obviously — it doesn't exist. A real number?",
    "🤖 My algo is powerful, but it doesn't analyse ghost numbers. In EuroMillions: 1 to 50 balls, 1 to 12 stars. {num} is out of bounds. Your turn!",
    "💡 Useful info: EuroMillions draws 5 balls from 1-50 + 2 stars from 1-12. {num} isn't on the menu. Give me a real number and I'll pull up its stats in 2 seconds.",
]

_OOR_L2_EM_EN = [
    "🙄 Another out-of-range? It's 1 to 50 for balls, 1 to 12 for stars. I already told you. My algo is patient, but my memory is perfect.",
    "😤 {num}, still out of bounds. Testing my patience or genuinely don't know the rules? 1-50 balls, 1-12 stars. Not that hard.",
    "📈 Two invalid numbers in a row. Statistically, you'd have better luck typing a random number between 1 and 50. Just saying...",
    "🧠 Second out-of-range attempt. We've got a trend here. 1 to 50 for balls, 1 to 12 for stars. Memorise it this time.",
]

_OOR_L3_EM_EN = [
    "🫠 OK, at this point I think you're doing it on purpose. Balls: 1-50. Stars: 1-12. That's the {streak}th time. Even my circuit-breaker is more forgiving.",
    "☕ {num}. Out of range. Again. I could do this all day — you too apparently. But that's not how you win at EuroMillions.",
    "🏆 Invalid number record! Congrats. If you put as much energy into picking a REAL number between 1 and 50, you'd already have an optimised grid.",
]

_OOR_CLOSE_EM_EN = [
    "😏 {num}? So close! But 50 is the limit. You were {diff} number{s} off. So near yet so far... Try between 1 and 50!",
    "🎯 Ah, {num} — just above the limit! EuroMillions balls stop at 50. You were getting warm though. How about a number within bounds?",
]

_OOR_ZERO_NEG_EM_EN = [
    "🤔 {num}? That's... creative. But in EuroMillions we start at 1. The maths are already complex enough without adding {num}!",
    "😂 {num} in EuroMillions? We're not in another dimension here. Balls are 1 to 50, stars 1 to 12. Try a number that exists in our reality!",
    "🌀 {num}... I admire the creativity, but they haven't invented negative balls yet. 1 to 50 for balls, 1 to 12 for stars. Simple, right?",
]

_OOR_ETOILE_EM_EN = [
    "🎲 Star {num}? Stars only go from 1 to 12! You're a bit ambitious on that one. Pick between 1 and 12.",
    "💫 For stars, it's 1 to 12 max. {num} is out of play! But the enthusiasm is there, that's the main thing 😉",
]

FALLBACK_RESPONSE_EM_EN = (
    "\U0001f916 I'm temporarily unavailable. "
    "Try again in a few seconds or check the FAQ!"
)


# ═══════════════════════════════════════════════════════════
# Selection functions — EN mirrors of chat_detectors_em.py
# ═══════════════════════════════════════════════════════════

def _get_insult_response_em_en(streak: int, history) -> str:
    if streak >= 3:
        pool = _INSULT_L4_EM_EN
    elif streak == 2:
        pool = _INSULT_L3_EM_EN
    elif streak == 1:
        pool = _INSULT_L2_EM_EN
    else:
        pool = _INSULT_L1_EM_EN

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


def _get_insult_short_em_en() -> str:
    return random.choice(_INSULT_SHORT_EM_EN)


def _get_menace_response_em_en() -> str:
    return random.choice(_MENACE_RESPONSES_EM_EN)


def _get_compliment_response_em_en(compliment_type: str, streak: int, history=None) -> str:
    if compliment_type == "love":
        pool = _COMPLIMENT_LOVE_EM_EN
    elif compliment_type == "merci":
        pool = _COMPLIMENT_MERCI_EM_EN
    elif streak >= 3:
        pool = _COMPLIMENT_L3_EM_EN
    elif streak == 2:
        pool = _COMPLIMENT_L2_EM_EN
    else:
        pool = _COMPLIMENT_L1_EM_EN

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


def _get_oor_response_em_en(numero: int, context: str, streak: int) -> str:
    if context == "zero_neg":
        pool = _OOR_ZERO_NEG_EM_EN
    elif context == "close":
        pool = _OOR_CLOSE_EM_EN
    elif context == "etoile_high":
        pool = _OOR_ETOILE_EM_EN
    elif streak >= 2:
        pool = _OOR_L3_EM_EN
    elif streak == 1:
        pool = _OOR_L2_EM_EN
    else:
        pool = _OOR_L1_EM_EN

    response = random.choice(pool)
    diff = abs(numero - 50) if numero > 50 else abs(numero)
    s = "s" if diff > 1 else ""
    return response.format(
        num=numero,
        diff=diff,
        s=s,
        streak=streak + 1,
    )


def _get_argent_response_em_en(message: str) -> str:
    """Selectionne une reponse argent EN selon le niveau (L1/L2/L3)."""
    lower = message.lower()
    # L3 : betting/addiction words
    for mot in _ARGENT_BETTING_EN:
        if re.search(r'\b' + re.escape(mot) + r'\b', lower):
            return _ARGENT_L3_EM_EN[0]
    # L2 : strong words
    for pattern in _ARGENT_STRONG_EN:
        if re.search(pattern, lower):
            return random.choice(_ARGENT_L2_EM_EN)
    # L1 : default
    return random.choice(_ARGENT_L1_EM_EN)
