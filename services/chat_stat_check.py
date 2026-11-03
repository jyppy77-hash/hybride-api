"""
Lot 1.6.065 — Contrôle 4 : statistiques par numéro, correspondances partielles, grilles + score.

Appelé par `chat_pipeline_gemini.stream_and_respond` dans le buffer strict, après le
contrôle 3 (et en journal seul après émission quand le buffer strict est inactif).

Principe : une réponse ne peut citer, pour un numéro, une fréquence, un écart, un rang ou
une étiquette chaud / froid / neutre que si ce chiffre figure dans un bloc posé par le
code AU TOUR COURANT (`enrichment_context`). Les tags présents dans l'historique ou dans la
réponse ne sont JAMAIS lus : Gemini écrit de faux blocs (cas 7318 « [NUMÉROS PRINCIPAUX] »).

Trois vérifications :
  (1) STAT_MISMATCH         — chiffre ou étiquette par numéro absent du bloc ou différent ;
  (2) PARTIAL_MATCH_MISMATCH — « K numéros (a-b-c) le JJ/MM/AAAA » différent de [ANALYSE DE GRILLE] ;
  (3) GRID_SCORE_ORPHAN     — grille de 5 numéros + score /100 ou badges sans bloc moteur.

Faux positifs neutralisés : nombre de tirages, pourcentages, décimales, dates (« le 22
octobre »), numéros du message utilisateur, phases P / P+ / 3-bis et blocs [RÉSULTAT SQL]
(comptes et résultats non structurés : (1) n'y est pas appliqué), score légitime d'une grille
du moteur (bloc du tour, ou rappel d'un tour de génération avec un score possible du moteur).

Flag `STRICT_STAT_CHECK` (config/engine.py, OFF par défaut) : OFF = journal seul, la réponse
n'est jamais modifiée ; ON = blocage (message strict existant). Aucune donnée personnelle
n'est journalisée (ni IP ni identifiant), seulement la ligne fautive de la réponse.
"""

import logging
import re

from services.base_chat_detect_temporal import _mask_dates

logger = logging.getLogger(__name__)

_LINE_LOG_MAX = 1000

# Scores que le moteur HYBRIDE peut produire (config/engine.py `_STAR_SCORES`) : tout autre
# score accolé à une grille sans bloc est une invention (82, 88, 98… cas 9402 / 9403).
try:
    from config.engine import LOTO_CONFIG as _LOTO_ENGINE_CFG
    ENGINE_SCORES = frozenset(_LOTO_ENGINE_CFG.star_to_legacy_score.values())
except Exception:  # pragma: no cover — défaut documenté
    ENGINE_SCORES = frozenset({95, 85, 75, 60, 50})

_CAT_NORMALIZE = {
    "chaud": "chaud", "chauds": "chaud", "chaude": "chaud", "hot": "chaud", "caliente": "chaud",
    "calientes": "chaud", "quente": "chaud", "quentes": "chaud", "heiß": "chaud", "heiss": "chaud",
    "heiße": "chaud", "heisse": "chaud", "heet": "chaud", "hete": "chaud",
    "froid": "froid", "froids": "froid", "froide": "froid", "cold": "froid", "frío": "froid",
    "frio": "froid", "fríos": "froid", "frios": "froid", "kalt": "froid", "kalte": "froid",
    "koud": "froid", "koude": "froid",
    "neutre": "neutre", "neutres": "neutre", "neutral": "neutre", "neutro": "neutre",
    "neutros": "neutre", "neutrale": "neutre", "neutraal": "neutre",
}
_CAT_WORDS = (r"chaud(?:e|s)?|froid(?:e|s)?|neutres?|hot|cold|neutral|calientes?|fr[ií]os?|neutros?|"
              r"quentes?|hei(?:ß|ss)e?|kalte?|neutrale|heet|hete|koude?|neutraal")

# ── Ancres « numéro N » (6 langues) ──────────────────────────────────────────
_SEC_WORDS = r"chance|[ée]toiles?|stars?|estrellas?|estrelas?|sterne?n?|ster(?:ren)?"
_ANCHOR_RE = re.compile(
    r"(?:(?P<sec>" + _SEC_WORDS + r")\s+(?:n[°o]\s*)?"
    r"|(?:num[ée]ros?|n°|number|n[uú]meros?|nummers?|zahl|boules?|ball|bola|kugel|bal)\s+(?P<sec2>chance\s+)?"
    r"|\b(?:le|el|o|der|die|het|the)\s+"
    r"|^\s*[-•*·]?\s*)"
    r"(?P<num>\d{1,2})\b(?!\s*(?:[/:h]\d|%|[.,]\d))",
    re.IGNORECASE | re.MULTILINE,
)

_FREQ_RES = (
    re.compile(r"(?:fr[ée]quence|frequency|frecuencia|frequ[êe]ncia|h[äa]ufigkeit|frequentie)"
               r"(?:\s+(?:observ[ée]e|totale|observed|total|observada|observada|gesamt|totaal))?"
               r"\s*(?:de\s+|of\s+|von\s+|van\s+)?:?\s*(\d{1,4})\b(?!\s*%)", re.IGNORECASE),
    re.compile(r"\b(\d{1,4})\s*(?:fois|sorties|apparitions?|times|appearances|veces|apariciones|vezes|"
               r"apari[çc][õo]es|mal\b|auftritte|keer|verschijningen)", re.IGNORECASE),
)
_GAP_EXCLUDE = r"(?!\s+(?:moyen|average|medio|m[ée]dio|durchschnittlich|gemiddeld))"
_GAP_RES = (
    re.compile(r"(?:[ée]cart|retard|gap|delay|retraso|atraso|r[üu]ckstand|abstand|achterstand)"
               + _GAP_EXCLUDE + r"(?:\s+(?:actuel|current|actual|atual|aktuell|huidig))?"
               r"\s*(?:de\s+|of\s+|von\s+|van\s+)?:?\s*(\d{1,3})\b(?![.,]\d)", re.IGNORECASE),
    re.compile(r"(?:il\s+y\s+a|depuis|à\s+peine|hace|h[áa]|vor|slechts)\s+(\d{1,3})\s+"
               r"(?:tirages?|draws?|sorteos?|sorteios?|ziehungen?|trekkingen?)", re.IGNORECASE),
    re.compile(r"\b(\d{1,3})\s+(?:draws?|trekkingen?|ziehungen?)\s+(?:ago|geleden|her)\b", re.IGNORECASE),
)
_RANK_RES = (
    re.compile(r"(?:rang|rank|classement|position|puesto|posi[çc][ãa]o|platz|plaats)\s*(?:n°|:)?\s*(\d{1,2})\b",
               re.IGNORECASE),
)
_CAT_RE = re.compile(r"\b(" + _CAT_WORDS + r")\b", re.IGNORECASE)
_CAT_LIST_RE = re.compile(
    r"(?:num[ée]ros?|numbers?|n[uú]meros?|zahlen|nummers?|boules?)\s+(" + _CAT_WORDS + r")"
    r"|(" + _CAT_WORDS + r")\s+(?:numbers?|zahlen|nummers?)",
    re.IGNORECASE,
)
_LIST_NUMS_RE = re.compile(r"\s*(?:\([^)]*\))?\s*:?\s*((?:\d{1,2}\s*(?:,|et|and|y|e|und|en|&)\s*)*\d{1,2})\b")

_SEQ_SEP = r'(?:\s*[-–—,/]\s*|\s+(?:et|and|y|und|en|e)\s+)'
_SEQ5_RE = re.compile(rf'(?<!\d)(\d{{1,2}}){_SEQ_SEP}(\d{{1,2}}){_SEQ_SEP}(\d{{1,2}}){_SEQ_SEP}(\d{{1,2}}){_SEQ_SEP}(\d{{1,2}})(?!\d)')
_SCORE_RES = (
    re.compile(r"(?<![\d.,])(\d{1,3})\s*/\s*100\b"),
    re.compile(r"(?:score|indice|puntuaci[óo]n|pontua[çc][ãa]o|konformit[äa]t\w*|conformiteit\w*)"
               r"[^\d\n]{0,25}(\d{1,3})\s*(?:%|/\s*100|\b)", re.IGNORECASE),
)
_BADGES_RE = re.compile(r"\bbadges?\b|\babzeichen\b|\binsignias?\b|\bemblemas?\b", re.IGNORECASE)

_PARTIAL_RE = re.compile(
    r"\b(\d)\s+(?:num[ée]ros?|numbers?|n[uú]meros?|zahlen|nummers?|boules?)\b[^\n]{0,60}?"
    r"\(?\s*(?<!\d)(\d{1,2}(?:\s*[-–—,/]\s*\d{1,2}(?!\d)|\s+(?:et|and|y|e|und|en)\s+\d{1,2}(?!\d)){1,3})\s*\)?",
    re.IGNORECASE,
)

# ── Lecture des blocs du tour courant (formats fixes posés par le code) ──────
_STATS_LINE_RE = re.compile(
    r"^(Numéro|Chance|Étoile) (\d{1,2}) : (\d+) sorties — (?:écart actuel (\d+) tirages[^—]*|jamais sorti) — "
    r"rang (\d+)/\d+ — (CHAUD|FROID|NEUTRE)$", re.MULTILINE)
_RT_HEADER_RE = re.compile(r"\[DONNÉES TEMPS RÉEL[^\]]*Numéro (principal|chance|boule|étoile) (\d{1,2})\]")
_RT_FREQ_RE = re.compile(r"Fréquence totale : (\d+) apparitions")
_RT_GAP_RE = re.compile(r"Écart actuel : (\d+) tirages")
_RT_GAP_MEAN_RE = re.compile(r"Écart moyen : ([\d.]+) tirages")
_RT_RANK_RE = re.compile(r"Classement fréquence : (\d+)e")
_RT_CAT_RE = re.compile(r"Catégorie : (\w+)")
_CLASS_HEADER_RE = re.compile(r"\[CLASSEMENT - Top \d+ numéros (\w+)")
_CLASS_LINE_RE = re.compile(r"^\d+\. Numéro (\d{1,2}) : (\d+) apparitions \(écart actuel : (\d+)\) — (\w+)", re.MULTILINE)
_COMP_LINE_RE = re.compile(r"^Numéro (\d{1,2}) : (\d+) apparitions \([^)]*\) \| Écart : (\d+) \| Catégorie : (\w+)",
                           re.MULTILINE)
_CAT_BLOCK_RE = re.compile(r"\[NUMÉROS (CHAUD|FROID|NEUTRE)S?[^\]]*\]\s*\nNuméros : ([\d,\s]+)")
_ANALYSE_CAT_RE = re.compile(r"^Numéros (chauds|froids|neutres)(?: \([^)]*\))? : ([\d,\s]+)$", re.MULTILINE)
_ANALYSE_HEADER_RE = re.compile(r"\[(?:ANALYSE DE GRILLE|ÉVALUATION GRILLE UTILISATEUR) - (\d{1,2}(?: \d{1,2}){4})")
_ANALYSE_CONF_RE = re.compile(r"^Conformité : (\d+)%", re.MULTILINE)
_ANALYSE_BEST_RE = re.compile(r"Meilleure correspondance : (\d) numéros communs[^\n]*? le (\d{4}-\d{2}-\d{2}) \(([\d,\s]+)\)")
_ANALYSE_TIE_RE = re.compile(r"le (\d{4}-\d{2}-\d{2}) \(([\d,\s]+)")
_ANALYSE_TIES_LINE_RE = re.compile(r"^Tirages à égalité \((\d) numéros communs\)[^\n]*$", re.MULTILINE)
_GEN_BLOCK_RE = re.compile(r"\[GRILLE GÉNÉRÉE PAR HYBRIDE\]\s*\nNuméros : \[([\d,\s]+)\][\s\S]*?"
                           r"Score de conformité : (\d+)/100")
_TOTAL_RE = re.compile(r"(\d{3,5}) tirages")

_SKIP_STAT_PHASES = frozenset({"P", "P+", "3-bis"})
_SKIP_STAT_TAGS = ("[RÉSULTAT SQL", "[CORRÉLATIONS", "[PAIRE DEMANDÉE", "[COMPARAISON SUR PÉRIODE")


def _ints(text: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d{1,2}", text or "")]


def _truth_from_context(ctx: str) -> dict:
    """Valeurs par numéro posées par le code au tour courant : {(kind, n): {champ: valeur}}."""
    truth: dict = {}
    if not ctx:
        return truth

    def put(kind, n, **fields):
        truth.setdefault((kind, int(n)), {}).update({k: v for k, v in fields.items() if v is not None})

    for m in _STATS_LINE_RE.finditer(ctx):
        kind = "main" if m.group(1) == "Numéro" else "sec"
        put(kind, m.group(2), freq={int(m.group(3))}, ecart={int(m.group(4))} if m.group(4) else None,
            rang={int(m.group(5))}, cat={m.group(6).lower()})
    for h in _RT_HEADER_RE.finditer(ctx):
        body = ctx[h.end():].split("[/DONNÉES TEMPS RÉEL]", 1)[0]
        kind = "sec" if h.group(1) in ("chance", "étoile") else "main"
        f, g, gm, r, c = (_RT_FREQ_RE.search(body), _RT_GAP_RE.search(body), _RT_GAP_MEAN_RE.search(body),
                          _RT_RANK_RE.search(body), _RT_CAT_RE.search(body))
        gaps = set()
        if g:
            gaps.add(int(g.group(1)))
        if gm:
            gaps.add(round(float(gm.group(1))))
        put(kind, h.group(2), freq={int(f.group(1))} if f else None, ecart=gaps or None,
            rang={int(r.group(1))} if r else None, cat={c.group(1).lower()} if c else None)
    for h in _CLASS_HEADER_RE.finditer(ctx):
        kind = "sec" if h.group(1).lower() in ("chance", "étoiles") else "main"
        body = ctx[h.end():].split("\n\n", 1)[0]
        for m in _CLASS_LINE_RE.finditer(body):
            put(kind, m.group(1), freq={int(m.group(2))}, ecart={int(m.group(3))}, cat={m.group(4).lower()})
    # [COMPARAISON] et [NUMÉROS CHAUDS/FROIDS] ne disent pas s'il s'agit de boules ou de numéros
    # secondaires (chance / étoiles) : la valeur vaut pour les deux lectures.
    for m in _COMP_LINE_RE.finditer(ctx):
        for kind in ("main", "sec"):
            put(kind, m.group(1), freq={int(m.group(2))}, ecart={int(m.group(3))}, cat={m.group(4).lower()})
    for m in _CAT_BLOCK_RE.finditer(ctx):
        for n in _ints(m.group(2)):
            for kind in ("main", "sec"):
                truth.setdefault((kind, n), {}).setdefault("cat", set()).add(m.group(1).lower())
    for m in _ANALYSE_CAT_RE.finditer(ctx):
        label = {"chauds": "chaud", "froids": "froid", "neutres": "neutre"}[m.group(1)]
        for n in _ints(m.group(2)):
            truth.setdefault(("main", n), {}).setdefault("cat", set()).add(label)
    return truth


def _ties_from_context(ctx: str):
    """Correspondances du bloc d'analyse : (K, {date_iso: frozenset(numéros communs)}) ou None."""
    best = _ANALYSE_BEST_RE.search(ctx or "")
    if not best:
        return None
    k = int(best.group(1))
    ties = {best.group(2): frozenset(_ints(best.group(3)))}
    line = _ANALYSE_TIES_LINE_RE.search(ctx)
    if line:
        for m in _ANALYSE_TIE_RE.finditer(line.group(0)):
            ties[m.group(1)] = frozenset(_ints(m.group(2)))
    return k, ties


def _engine_grids_from_context(ctx: str) -> dict:
    """Grilles posées par le code au tour courant : {frozenset(boules): {scores légitimes}}."""
    grids: dict = {}
    for m in _GEN_BLOCK_RE.finditer(ctx or ""):
        grids.setdefault(frozenset(_ints(m.group(1))), set()).add(int(m.group(2)))
    header = _ANALYSE_HEADER_RE.search(ctx or "")
    if header:
        conf = _ANALYSE_CONF_RE.search(ctx[header.start():])
        grids.setdefault(frozenset(_ints(header.group(1))), set()).update({int(conf.group(1))} if conf else set())
    return grids


def _segments(line: str):
    """Découpe une ligne en segments (kind, numéro, texte) à partir des ancres « numéro N »."""
    anchors = list(_ANCHOR_RE.finditer(line))
    for idx, a in enumerate(anchors):
        end = anchors[idx + 1].start() if idx + 1 < len(anchors) else len(line)
        kind = "sec" if (a.group("sec") or a.group("sec2")) else "main"
        yield kind, int(a.group("num")), line[a.end():end]


def _first(res, text):
    for r in res:
        m = r.search(text)
        if m:
            return int(m.group(1))
    return None


def _log(check: str, log_prefix: str, meta: dict, line: str, **fields):
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.warning("%s: %s phase=%s lang=%s game=%s %s | line=%s", check, log_prefix, meta.get("phase"),
                   meta.get("lang"), meta.get("game"), extra, line.strip()[:_LINE_LOG_MAX])


def check_number_stats(
    response: str, enrichment_context: str, *, phase: str, lang: str, game: str,
    user_message: str = "", draw_count: int | None = None, engine_turn_grids=None,
    log_prefix: str = "",
) -> list[dict]:
    """Contrôle 4. Retourne la liste des écarts (vide = rien à signaler) et les journalise.

    engine_turn_grids : [(frozenset(boules), score|None)] des grilles présentées par les tours
    de génération de l'historique (reconstruits côté serveur, cf. chat_pipeline_shared).
    """
    findings: list[dict] = []
    if not response:
        return findings
    ctx = enrichment_context or ""
    meta = {"phase": phase, "lang": lang, "game": game}
    user_vals = {int(x) for x in re.findall(r"\b\d{1,4}\b", user_message or "")}
    totals = {int(x) for x in _TOTAL_RE.findall(ctx)}
    if draw_count:
        totals.add(int(draw_count))
    truth = _truth_from_context(ctx)
    skip_stats = phase in _SKIP_STAT_PHASES or any(t in ctx for t in _SKIP_STAT_TAGS)
    lines = response.splitlines()

    # (1) statistiques par numéro
    if not skip_stats:
        for raw in lines:
            line = _mask_dates(raw)
            line = re.sub(r"\d+(?:[.,]\d+)?\s*%", " ", line)
            for kind, num, seg in _segments(line):
                t = truth.get((kind, num))
                # ancre générique (« le 7 ») : peut désigner un numéro chance / une étoile d'un
                # classement secondaire ; une ancre explicite (« chance 7 ») ne retombe jamais sur une boule
                if t is None and kind == "main":
                    t = truth.get(("sec", num))
                claims = {
                    "freq": _first(_FREQ_RES, seg),
                    "ecart": _first(_GAP_RES, seg),
                    "rang": _first(_RANK_RES, seg),
                }
                c = _CAT_RE.search(seg)
                claims["cat"] = _CAT_NORMALIZE.get(c.group(1).lower()) if c else None
                for field, cited in claims.items():
                    if cited is None:
                        continue
                    if field == "freq" and (cited in totals or cited > 400):
                        continue
                    if field != "cat" and cited in user_vals:
                        continue
                    expected = (t or {}).get(field)
                    if expected is not None and cited in expected:
                        continue
                    exp_txt = ("aucun bloc" if not truth else
                               "absent du bloc" if expected is None else "/".join(str(e) for e in sorted(expected)))
                    f = {"check": "STAT_MISMATCH", "num": num, "kind": kind, "field": field,
                         "cited": cited, "expected": exp_txt, "line": raw}
                    findings.append(f)
                    _log("STAT_MISMATCH", log_prefix, meta, raw, num=num, kind=kind, field=field,
                         cited=cited, expected=exp_txt)
            # listes « numéros chauds : 22, 24 »
            for lm in _CAT_LIST_RE.finditer(line):
                label = _CAT_NORMALIZE.get((lm.group(1) or lm.group(2)).lower())
                nums_m = _LIST_NUMS_RE.match(line, lm.end())
                if not label or not nums_m:
                    continue
                for num in _ints(nums_m.group(1)):
                    expected = (truth.get(("main", num)) or {}).get("cat")
                    if expected is not None and label in expected:
                        continue
                    exp_txt = ("aucun bloc" if not truth else
                               "absent du bloc" if expected is None else "/".join(sorted(expected)))
                    findings.append({"check": "STAT_MISMATCH", "num": num, "kind": "main", "field": "cat",
                                     "cited": label, "expected": exp_txt, "line": raw})
                    _log("STAT_MISMATCH", log_prefix, meta, raw, num=num, kind="main", field="cat",
                         cited=label, expected=exp_txt)

    # (2) correspondances partielles « K numéros (a-b-c) le <date> »
    from services.chat_pipeline_gemini import _find_draw_dates
    ties = _ties_from_context(ctx)
    for raw in lines:
        dates = _find_draw_dates(raw)
        pm = _PARTIAL_RE.search(_mask_dates(raw)) if dates else None
        if not pm or not dates:
            continue
        k_cited = int(pm.group(1))
        nums_cited = frozenset(_ints(pm.group(2)))
        for _, _, d in dates:
            iso = d.isoformat()
            if ties and k_cited == ties[0] and ties[1].get(iso) == nums_cited:
                continue
            exp = ("aucun bloc" if not ties else
                   f"{ties[0]} numéros : " + " ; ".join(f"{k} ({', '.join(str(n) for n in sorted(v))})"
                                                        for k, v in sorted(ties[1].items(), reverse=True)))
            findings.append({"check": "PARTIAL_MATCH_MISMATCH", "date": iso, "cited": sorted(nums_cited),
                             "k": k_cited, "expected": exp, "line": raw})
            _log("PARTIAL_MATCH_MISMATCH", log_prefix, meta, raw, date=iso, k=k_cited,
                 cited="-".join(str(n) for n in sorted(nums_cited)), expected=exp)

    # (3) C′ — grille de 5 numéros + score /100 ou badges sans bloc moteur
    engine_grids = _engine_grids_from_context(ctx)
    recall = {}
    for g, s in (engine_turn_grids or []):
        recall.setdefault(frozenset(g), set()).add(s)
    for i, raw in enumerate(lines):
        for sm in _SEQ5_RE.finditer(raw):
            nums = [int(x) for x in sm.groups()]
            if len(set(nums)) != 5:
                continue
            window = "\n".join(lines[max(0, i - 3):i + 5])
            score = _first(_SCORE_RES, window)
            has_badges = bool(_BADGES_RE.search(window))
            if score is None and not has_badges:
                continue
            grid = frozenset(nums)
            legit = engine_grids.get(grid)
            if legit is not None and (score is None or score in legit or not legit):
                continue
            rec = recall.get(grid)
            if rec is not None and (score is None or score in rec) and (score is None or score in ENGINE_SCORES):
                logger.info("GRID_SCORE_RECALL: %s phase=%s lang=%s game=%s grid=%s score=%s",
                            log_prefix, phase, lang, game, "-".join(str(n) for n in sorted(grid)), score)
                continue
            exp = ("aucun bloc moteur" if legit is None else "score du bloc " + "/".join(str(x) for x in sorted(legit)))
            findings.append({"check": "GRID_SCORE_ORPHAN", "grid": sorted(grid), "score": score,
                             "expected": exp, "line": raw})
            _log("GRID_SCORE_ORPHAN", log_prefix, meta, raw, grid="-".join(str(n) for n in sorted(grid)),
                 score=score, badges=has_badges, expected=exp)
    return findings
