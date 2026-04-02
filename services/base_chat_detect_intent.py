"""
Base chat detectors — Intent detection (game-agnostic).
Continuation, affirmation, game keyword, data signal, salutation, grid evaluation.

F05 V84: Split into 4 modules for maintainability:
- base_chat_detect_temporal.py  — Phase T (tirage, dates, temporal filters)
- base_chat_detect_generation.py — Phase G (generation, exclusions, forced numbers)
- base_chat_detect_correlation.py — Phase 3/P/P+ (rankings, pairs, triplets, co-occurrence)
- base_chat_detect_intent.py (this file) — remaining phases + re-exports

All existing imports from this module continue to work (backward compatibility).
"""

import re
import logging
from datetime import date  # noqa: F401 — re-exported

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
# Re-exports — backward compatibility (F05 V84)
# Consumers import from this module; actual code lives in sub-modules.
# ═══════════════════════════════════════════════════════

from services.base_chat_detect_temporal import (  # noqa: F401
    _JOURS_SEMAINE, _TIRAGE_KW, _MOIS_TO_NUM, _MOIS_NOM_RE,
    _STAT_NEUTRALIZE_RE, _detect_tirage,
    _MOIS_FR, _MOIS_RE, _MOIS_EN, _MOIS_ES, _MOIS_PT, _MOIS_DE, _MOIS_NL,
    _TEMPORAL_PATTERNS, _TEMPORAL_EXTRACT_MONTHS, _TEMPORAL_EXTRACT_YEARS,
    _TEMPORAL_EXTRACT_WEEKS, _has_temporal_filter, _extract_temporal_date,
    _NEXT_KW_RE, _LATEST_KW_RE, _WHICH_DRAWN_RE,
    _DAY_BEFORE_YESTERDAY_RE, _YESTERDAY_RE, _RESULTS_STANDALONE_RE, _DE_DATE_RE,
)

from services.base_chat_detect_generation import (  # noqa: F401
    _GENERATION_PATTERN, _GENERATION_CONTEXT, _COOCCURRENCE_EXCLUSION,
    _detect_generation, _detect_generation_mode,
    _MODE_PATTERN_CONSERVATIVE, _MODE_PATTERN_RECENT,
    _GRID_COUNT_PATTERN, _extract_grid_count,
    _BIRTHDAY_PATTERN, _EXCLUDE_RANGE_PATTERN, _EXCLUDE_MULTIPLES_PATTERN,
    _EXCLUDE_NUMS_PATTERN, _EXCLUDE_NUMS_RANGE_PATTERN,
    _extract_exclusions, _extract_nums_from_text, _extract_forced_numbers,
    _CHANCE_PATTERN, _STAR_PATTERN, _WITH_PATTERN, _QUANTIFIER_PATTERN,
)

from services.base_chat_detect_correlation import (  # noqa: F401
    _TOP_N_PATTERNS, _extract_top_n,
    _detect_requete_complexe_base,
    _PAIRS_PATTERN, _EVEN_ODD_RE, _detect_paires,
    _TRIPLETS_PATTERN, _detect_triplets,
    _COOCCURRENCE_HIGH_N_PATTERN, _RANKING_EXCLUSION_PATTERN,
    _COOCCURRENCE_EXPLICIT_PATTERN, _COOCCURRENCE_HIGH_N_RESPONSES,
    _detect_cooccurrence_high_n, _get_cooccurrence_high_n_response,
)


# ────────────────────────────────────────────
# Phase 0 : Continuation contextuelle
# Intercepte les réponses courtes (oui/non/ok...) et les enrichit
# avec le contexte conversationnel pour éviter les dérives Gemini.
# ────────────────────────────────────────────

CONTINUATION_PATTERNS = re.compile(
    r'^(oui|ouais|yes|yeah|yep|ok|d\'accord|vas-y|vas\s*y|go|montre|'
    r'montre-moi|montre[\s-]?moi[\s-]?(?:les|ça|ca|tout)?|'
    r'montre[\s-]?les|vas[\s-]?y[\s-]?montre[\s-]?(?:les|moi)?|'
    r'carrément|bien sûr|absolument|pourquoi pas|'
    r'je veux bien|volontiers|allez|non|nan|nope|pas vraiment|'
    r'bof|si|stp|please|détaille|détailles|detail|continue|'
    r'envoie|balance|dis-moi|affirmatif|négatif|'
    r'je veux savoir|je veux voir|on y va|'
    r'show me|show them|go ahead|tell me|do it|'
    r'ja|nein|doch|natürlich|zeig|zeig mir|'
    r'sim|não|mostra|claro|'
    r'sí|no|muestra|dale|venga|'
    r'ja|nee|laat zien|toon)[\s!.?]*$',
    re.IGNORECASE
)

# Fuzzy continuation: catches typos like "vas ymontre les", "oui montre", etc.
_CONTINUATION_WORDS = {
    "oui", "ouais", "yes", "yeah", "yep", "ok", "go", "montre", "vas",
    "allez", "continue", "détaille", "detail", "envoie", "balance",
    "show", "tell", "ja", "sim", "sí", "si", "dale", "venga",
    "claro", "doch", "zeig", "mostra", "laat", "toon", "nee",
    "non", "nan", "nope", "nein", "não", "no",
}


def _is_short_continuation(message: str) -> bool:
    """Detecte si le message est une reponse courte de continuation.
    Uses exact regex first, then fuzzy word-level check for typos."""
    stripped = message.strip()
    if len(stripped) > 80:
        return False
    if CONTINUATION_PATTERNS.match(stripped):
        return True
    # Fuzzy: if short (≤5 words) and first word is a continuation word
    # V46: guard — messages containing digits are likely queries, not continuations
    words = stripped.lower().split()
    if 1 <= len(words) <= 5 and words[0] in _CONTINUATION_WORDS:
        if not any(c.isdigit() for c in stripped):
            return True
    return False


# ────────────────────────────────────────────
# Phase AFFIRMATION : réponses conversationnelles courtes (V51)
# Capte "Oui", "Ok", "Non", "Avec plaisir", "Oui je veux bien", etc.
# NE capte PAS les messages avec des chiffres (digit guard V46).
# ────────────────────────────────────────────

_AFFIRMATION_PATTERNS = re.compile(
    r'^('
    # FR
    r'oui|ouais|ouep|yep|ok|okay|d\'accord|bien s[uû]r|bien sur|'
    r'[çc]a marche|c\'est bon|entendu|parfait|super|'
    r'avec plaisir|volontiers|carr[eé]ment|'
    r'non|nan|pas vraiment|bof|'
    # EN
    r'yes|yeah|sure|no|nope|alright|sounds good|perfect|thanks|great|'
    # ES
    r's[ií]|vale|claro|por supuesto|perfecto|gracias|de acuerdo|'
    # PT
    r'sim|n[aã]o|perfeito|obrigado|obrigada|certo|com certeza|'
    # DE
    r'ja|nein|klar|nat[uü]rlich|perfekt|danke|einverstanden|'
    # NL
    r'nee|prima|natuurlijk|bedankt|akkoord|zeker'
    r')[\s!.?…]*$',
    re.IGNORECASE
)

# Strip emojis for clean word counting
_EMOJI_RE = re.compile(
    r'[\U00002600-\U000027BF\U0001F300-\U0001FAFF\U0000FE00-\U0000FE0F'
    r'\U0001F900-\U0001F9FF\U0000200D\U00002702-\U000027B0]+',
    re.UNICODE,
)


def _is_affirmation_simple(message: str) -> bool:
    """Detecte une affirmation/negation conversationnelle courte (6 langues).
    Exclut les messages contenant des chiffres (digit guard V46).
    Plus large que _is_short_continuation : capte les mots isolés
    sans exiger de contexte de continuation (vas-y, montre, etc.)."""
    stripped = message.strip()
    if len(stripped) > 80:
        return False
    # Strip emojis for word count and digit check
    text_only = _EMOJI_RE.sub('', stripped).strip()
    if not text_only:
        return False
    if any(c.isdigit() for c in text_only):
        return False
    words = text_only.split()
    if len(words) > 5:
        return False
    return bool(_AFFIRMATION_PATTERNS.match(text_only))


# Mot-clé jeu seul (V51 FIX 5)
_GAME_KEYWORD_ALONE = re.compile(
    r'^\s*(loto|euromillions?|euro\s*millions?)\s*[!?.]*\s*$',
    re.IGNORECASE,
)


def _detect_game_keyword_alone(message: str) -> bool:
    """Detecte si le message est uniquement un nom de jeu."""
    return bool(_GAME_KEYWORD_ALONE.match(message.strip()))


# ═══════════════════════════════════════════════════════
# Phase I — Data signal heuristic (V65)
# ═══════════════════════════════════════════════════════

_DATA_KEYWORDS = re.compile(
    # FR
    r'\b(?:fr[eé]quen|statistiqu|tirage|sortie?|retard|[eé]cart|classement|'
    r'top\s*\d|combien|moyenne|pourcentage|pairs?|impairs?|chaud|froid|'
    r'derni[eè]re?|premi[eè]re?|souvent|rarement|jamais|toujours|'
    r'fois|depuis|entre|pendant|ann[eé]e|mois|semaine|historique|archiv|'
    r'num[eé]ro|boule|chance|[eé]toile|jackpot|gagnant|rang|'
    # EN
    r'frequen|statistic|draw|lag|gap|ranking|how\s+many|average|percentage|'
    r'even|odd|hot|cold|last|first|most|least|often|rarely|never|always|'
    r'times|since|between|during|year|month|week|histor|number|star|ball|winner|'
    # ES
    r'frecuencia|estad[ií]stic|sorteo|retraso|brecha|clasificaci[oó]n|cu[aá]nto|'
    r'promedio|porcentaje|caliente|fr[ií]o|[uú]ltimo|primero|siempre|nunca|veces|'
    r'a[nñ]o|mes|semana|n[uú]mero|estrella|bola|ganador|'
    # PT
    r'frequ[eê]ncia|estat[ií]stic|sorteio|atraso|lacuna|classifica[cç][aã]o|quantas?|'
    r'percentagem|quente|frio|[uú]ltimo|primeiro|sempre|nunca|vezes|'
    r'grelha|n[uú]mero|estrela|bola|vencedor|'
    # DE
    r'h[aä]ufigkeit|statistik|ziehung|r[uü]ckstand|l[uü]cke|rangliste|wie\s+oft|'
    r'durchschnitt|prozent|hei[sß]|kalt|letzte|erste|immer|nie|mal|'
    r'seit|zwischen|jahr|monat|woche|nummer|zahl|stern|kugel|gewinner|'
    # NL
    r'frequentie|statistiek|trekking|achterstand|kloof|ranglijst|hoe\s+vaak|'
    r'gemiddelde|percentage|heet|koud|laatste|eerste|altijd|nooit|keer|'
    r'sinds|tussen|jaar|maand|week|nummer|ster|bal|winnaar)',
    re.IGNORECASE
)

_HAS_DIGIT = re.compile(r'\d')


def _has_data_signal(message: str) -> bool:
    """Heuristique rapide : le message contient-il un signal data (chiffre ou mot-cle statistique) ?
    Retourne False pour les messages purement conversationnels — permet de skip Phase SQL."""
    if _HAS_DIGIT.search(message):
        return True
    return bool(_DATA_KEYWORDS.search(message))


# ═══════════════════════════════════════════════════════
# Phase SALUTATION — Détection des salutations initiales (V65)
# Court-circuite le pipeline pour éviter un appel Gemini/SQL inutile.
# Condition : message court (< 8 mots) et historique vide ou ≤ 1 message.
# ═══════════════════════════════════════════════════════

_SALUTATION_PATTERN = re.compile(
    r'^\s*(?:'
    # FR
    r'salut|bonjour|bonsoir|coucou|yo+|yop|hey|slt|wesh|bjr|'
    r'bsr|cc|kikou|'
    # EN
    r'hello|hi|hey|howdy|what.?s\s+up|sup|hiya|'
    # ES
    r'hola|buenas|qu[eé]\s+tal|buenos?\s+d[ií]as?|buenas?\s+(?:tardes?|noches?)|'
    # PT
    r'ol[aá]|oi|bom\s+dia|boa\s+tarde|boa\s+noite|'
    # DE
    r'hallo|guten\s+(?:tag|morgen|abend)|moin|servus|'
    # NL
    r'hallo|hoi|goedendag|goedemorgen|goedenavond|goedemiddag'
    r')(?:\s+[\w\u00e0-\u00ff]{0,15}){0,3}[?!.\s]*$',
    re.IGNORECASE
)

_SALUTATION_MAX_WORDS = 8


def _detect_salutation(message: str) -> bool:
    """Detecte si le message est une salutation simple (< 8 mots, 6 langues).
    NE DOIT PAS matcher les messages longs comme 'salut genere moi une grille'."""
    words = message.split()
    if len(words) > _SALUTATION_MAX_WORDS:
        return False
    return bool(_SALUTATION_PATTERN.match(message.strip()))


# Réponses d'accueil directes — court-circuit (pas de Gemini)
_SALUTATION_RESPONSES = {
    "loto": {
        "fr": "Salut ! 👋 Je suis HYBRIDE, ton assistant IA spécialiste du Loto. Pose-moi une question sur les statistiques des tirages ou demande-moi de générer une grille !",
        "en": "Hey there! 👋 I'm HYBRIDE, your AI assistant for Loto analysis. Ask me about draw statistics or request a grid!",
        "es": "¡Hola! 👋 Soy HYBRIDE, tu asistente IA especialista en Loto. ¡Pregúntame sobre estadísticas de sorteos o pídeme una combinación!",
        "pt": "Olá! 👋 Sou o HYBRIDE, o teu assistente IA especialista em Loto. Pergunta-me sobre estatísticas dos sorteios ou pede-me uma grelha!",
        "de": "Hallo! 👋 Ich bin HYBRIDE, dein KI-Assistent für Loto-Analysen. Frag mich nach Ziehungsstatistiken oder lass dir eine Kombination generieren!",
        "nl": "Hallo! 👋 Ik ben HYBRIDE, je AI-assistent voor Loto-analyses. Vraag me naar trekkingsstatistieken of laat me een combinatie genereren!",
    },
    "em": {
        "fr": "Salut ! 👋 Je suis HYBRIDE, ton assistant IA spécialiste de l'EuroMillions. Pose-moi une question sur les statistiques des tirages ou demande-moi de générer une grille !",
        "en": "Hey there! 👋 I'm HYBRIDE, your AI assistant for EuroMillions analysis. Ask me about draw statistics or request a grid!",
        "es": "¡Hola! 👋 Soy HYBRIDE, tu asistente IA especialista en EuroMillions. ¡Pregúntame sobre estadísticas de sorteos o pídeme una combinación!",
        "pt": "Olá! 👋 Sou o HYBRIDE, o teu assistente IA especialista em EuroMillions. Pergunta-me sobre estatísticas dos sorteios ou pede-me uma grelha!",
        "de": "Hallo! 👋 Ich bin HYBRIDE, dein KI-Assistent für EuroMillions-Analysen. Frag mich nach Ziehungsstatistiken oder lass dir eine Kombination generieren!",
        "nl": "Hallo! 👋 Ik ben HYBRIDE, je AI-assistent voor EuroMillions-analyses. Vraag me naar trekkingsstatistieken of laat me een combinatie genereren!",
    },
}


def _get_salutation_response(module: str, lang: str) -> str:
    """Retourne la reponse d'accueil pour le module et la langue donnes."""
    pool = _SALUTATION_RESPONSES.get(module, _SALUTATION_RESPONSES["loto"])
    return pool.get(lang, pool["fr"])


# ────────────────────────────────────────────
# Phase EVAL : Detection grille soumise pour evaluation (V70)
# ────────────────────────────────────────────

_GRID_EVAL_PATTERN = re.compile(
    # FR
    r'que?\s+(?:pensez|penses|pense[sz]?[\s-](?:tu|vous))\s+(?:de|d[\'ʼ])'
    r'|(?:votre|ton)\s+avis\s+(?:sur|pour)'
    r'|analy(?:ser?|se)\s+(?:ces|mes|les)\s+num[eé]ro'
    r'|[eé]valu(?:er?|e)\s+(?:ma|cette|la|mes)\s+(?:grille|combinaison)'
    r'|(?:ces|mes|les)\s+num[eé]ros?\s+(?:sont|est)\s+(?:bien|bon|bons|correct|valable|viable)'
    r'|que?\s+(?:vaut|valent)\s+(?:cette|ma|ces|mes)\s+(?:grille|combinaison|num[eé]ro)'
    r'|v[eé]rifi(?:er?|e)\s+(?:ma|mes|cette)\s+(?:grille|combinaison|num[eé]ro)'
    r'|(?:donne|donner?|donnez?)\s+(?:(?:moi|nous)\s+)?(?:votre|ton|un)\s+avis'
    r'|(?:comment\s+(?:est|sont)|c[\'ʼ]est\s+(?:bien|bon|correct))\s.*?\b(?:grille|num[eé]ro|combinaison)'
    # EN
    r'|what\s+do\s+you\s+think\s+(?:of|about)'
    r'|(?:your|an?)\s+opinion\s+(?:on|about)'
    r'|analy[sz]e\s+(?:these|my|the)\s+number'
    r'|evaluate\s+(?:my|this|the)\s+(?:grid|combination|numbers?)'
    r'|(?:are\s+)?(?:these|my)\s+numbers?\s+(?:good|ok|correct|valid|viable)'
    r'|check\s+(?:my|these|the)\s+(?:numbers?|grid|combination)'
    r'|(?:how\s+(?:is|are)|is\s+(?:this|it)\s+(?:good|ok))\s.*?\b(?:grid|number|combination)'
    r'|rate\s+(?:my|this|these)\s+(?:numbers?|grid|combination)'
    # ES
    r'|qu[eé]\s+(?:opinas?|piensas?|te\s+parece[ns]?)\s+(?:de|sobre)'
    r'|anali[zs]ar?\s+(?:estos?|mis?|las?)\s+n[uú]mero'
    r'|evaluar?\s+(?:mi|esta|la)\s+(?:combinaci[oó]n|cuadr[ií]cula)'
    r'|(?:son|est[aá]n?)\s+(?:bien|buenos?|correctos?)\s+(?:estos?|mis?)\s+n[uú]mero'
    # PT
    r'|o\s+que\s+acha(?:s|m)?\s+(?:de|d[eio]s?)'
    r'|analisar?\s+(?:estes?|os\s+meus|os)\s+n[uú]mero'
    r'|avaliar?\s+(?:a\s+minha|esta|os\s+meus)\s+(?:grelha|combina[cç][aã]o|n[uú]mero)'
    # DE
    r'|was\s+(?:h[aä]ltst|denkst|meinst)\s+(?:du|ihr|Sie)\s+(?:von|[uü]ber|zu|da(?:von|zu))'
    r'|(?:diese|meine)\s+Zahlen\s+(?:analysi|bewerst|pr[uü]f)'
    r'|(?:meine|diese)\s+(?:Zahlen|Kombination)\s+(?:gut|korrekt|in Ordnung)'
    # NL
    r'|wat\s+(?:vind|denk)\s+(?:je|jij|u)\s+(?:van|over|ervan)'
    r'|(?:deze|mijn)\s+nummers?\s+analy[sz]'
    r'|(?:mijn|deze)\s+(?:combinatie|nummers?)\s+(?:beoordel|check|controleer)'
    r'|(?:zijn|is)\s+(?:deze|mijn)\s+(?:nummers?|combinatie)\s+(?:goed|correct|ok)',
    re.IGNORECASE,
)

# Minimum numbers required for grid evaluation (partial grids accepted)
_GRID_EVAL_MIN_NUMS = 3


def _detect_grid_evaluation(message: str, game: str = "loto") -> dict | None:
    """
    Detect if user submits a grid for evaluation/analysis (6 langs).
    Returns dict with extracted numbers or None if not an evaluation request.

    Args:
        message: user message
        game: "loto" or "em" (determines number ranges)

    Returns:
        dict(numeros=list[int], chance=int|None, etoiles=list[int]|None) or None
    """
    if not _GRID_EVAL_PATTERN.search(message):
        return None

    # Extract all numbers from the message
    text = message.lower()

    max_boule = 49 if game == "loto" else 50
    max_secondary = 10 if game == "loto" else 12

    # Extract chance/etoiles first (secondary numbers)
    chance = None
    etoiles = None

    if game == "loto":
        # Detect chance number patterns
        chance_re = re.compile(
            r'(?:chance|compl[eé]mentaire|bonus|sp[eé]cial|n[°o]?\s*chance)\s*[:\s-]*(\d{1,2})'
            r'|(?:et\s+le\s+|le\s+)(\d{1,2})\s+en\s+chance',
            re.IGNORECASE,
        )
        for m in chance_re.finditer(text):
            val = int(m.group(1) or m.group(2))
            if 1 <= val <= max_secondary:
                chance = val
                text = text[:m.start()] + " " + text[m.end():]
                break
    else:
        # Detect star patterns for EM
        star_re = re.compile(
            r'(?:[eé]toiles?|stars?|estrellas?|estrelas?|stern[e]?|sterren?)\s*[:\s-]*(\d{1,2})\s*(?:et|and|y|e|und|en|-)\s*(\d{1,2})'
            r'|[☆★⭐]\s*(\d{1,2})\s*(?:et|and|y|e|und|en|-)\s*(\d{1,2})'
            r'|\+\s*(\d{1,2})\s*(?:et|and|y|e|und|en|-)\s*(\d{1,2})\s*$',
            re.IGNORECASE,
        )
        m = star_re.search(text)
        if m:
            groups = m.groups()
            e1, e2 = None, None
            for i in range(0, len(groups), 2):
                if groups[i] is not None:
                    e1, e2 = int(groups[i]), int(groups[i + 1])
                    break
            if e1 and e2 and 1 <= e1 <= max_secondary and 1 <= e2 <= max_secondary and e1 != e2:
                etoiles = sorted([e1, e2])
                text = text[:m.start()] + " " + text[m.end():]

    # Extract main numbers
    all_numbers = [int(x) for x in re.findall(r'\b(\d{1,2})\b', text)]
    valid_nums = [n for n in all_numbers if 1 <= n <= max_boule]

    # Deduplicate preserving order
    seen = set()
    unique_nums = []
    for n in valid_nums:
        if n not in seen:
            seen.add(n)
            unique_nums.append(n)

    if len(unique_nums) < _GRID_EVAL_MIN_NUMS:
        return None

    result = {"numeros": unique_nums[:5]}
    if game == "loto":
        result["chance"] = chance
    else:
        result["etoiles"] = etoiles

    return result
