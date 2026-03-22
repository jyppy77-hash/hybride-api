#!/usr/bin/env python3
"""
AUDIT 360 HYBRIDE EM v3 — 60 tests (10 questions x 6 langues)
Runs detectors directly (no DB/Gemini needed).
Scoring: P(pipeline)=5, H(honesty)=5, L(lang)=5, S(structure)=5 = 20/question/lang
"""

import sys
import io
import re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from services.chat_detectors import (
    _detect_insulte, _detect_compliment, _detect_generation,
    _detect_cooccurrence_high_n, _get_cooccurrence_high_n_response,
)
from services.chat_detectors_em import (
    _detect_mode_em, _detect_requete_complexe_em, _detect_paires_em,
    _detect_triplets_em, _detect_out_of_range_em, _detect_argent_em,
    _detect_country_em, _get_country_context_em,
    _get_argent_response_em,
)
from services.chat_responses_em_multilang import (
    get_insult_response, get_insult_short, get_menace_response,
    get_compliment_response, get_oor_response, get_fallback,
)

# ═══════════════════════════════════════════════════════════
# 10 questions x 6 langues
# ═══════════════════════════════════════════════════════════

QUESTIONS = {
    "Salutation": {
        "fr": "Bonjour, comment vas-tu ?",
        "en": "Hello, how are you?",
        "es": "Hola, como estas?",
        "pt": "Ola, como estas?",
        "de": "Hallo, wie geht es dir?",
        "nl": "Hallo, hoe gaat het?",
        "expected": "gemini",
    },
    "Frequences": {
        "fr": "Quels sont les numeros les plus frequents ?",
        "en": "What are the most frequent numbers?",
        "es": "Cuales son los numeros mas frecuentes?",
        "pt": "Quais sao os numeros mais frequentes?",
        "de": "Welche Zahlen kommen am haufigsten vor?",
        "nl": "Welke nummers worden het vaakst getrokken?",
        "expected": "complex",
    },
    "Geo/Pays": {
        "fr": "L'EuroMillions est-il disponible en France ?",
        "en": "Is EuroMillions available in the UK?",
        "es": "Esta el EuroMillions disponible en Espana?",
        "pt": "O EuroMillions esta disponivel em Portugal?",
        "de": "Ist EuroMillions in Deutschland verfugbar?",
        "nl": "Is EuroMillions beschikbaar in Belgie?",
        "expected": "geo",
    },
    "Co-occurrences N>3": {
        "fr": "Quels sont les 4 numeros qui sortent le plus ensemble ?",
        "en": "Which 4 numbers come out the most together?",
        "es": "Cuales son los 4 numeros que salen mas juntos?",
        "pt": "Quais sao os 4 numeros que saem mais juntos?",
        "de": "Welche 4 Zahlen kommen am haufigsten zusammen?",
        "nl": "Welke 4 nummers komen het vaakst samen voor?",
        "expected": "P+",
    },
    "Argent/Gains": {
        "fr": "Combien je peux gagner a l'EuroMillions ?",
        "en": "How much can I win at EuroMillions?",
        "es": "Cuanto puedo ganar en EuroMillions?",
        "pt": "Quanto posso ganhar no EuroMillions?",
        "de": "Wie viel kann man bei EuroMillions gewinnen?",
        "nl": "Hoeveel kun je winnen bij EuroMillions?",
        "expected": "argent",
    },
    "Insulte": {
        "fr": "T'es nul, tu sers a rien",
        "en": "You're useless, you suck",
        "es": "Eres inutil, no sirves para nada",
        "pt": "Es inutil, nao serves para nada",
        "de": "Du bist nutzlos, du taugst nichts",
        "nl": "Je bent nutteloos, je deugt nergens voor",
        "expected": "insult",
    },
    "Temporelle SQL": {
        "fr": "Quels numeros sont sortis le mois dernier ?",
        "en": "Which numbers came out last month?",
        "es": "Que numeros salieron el mes pasado?",
        "pt": "Que numeros sairam no mes passado?",
        "de": "Welche Zahlen kamen letzten Monat?",
        "nl": "Welke nummers kwamen vorige maand?",
        "expected": "sql",
    },
    "Paires (Phase P)": {
        "fr": "Quelles sont les paires les plus frequentes ?",
        "en": "What are the most frequent pairs?",
        "es": "Cuales son los pares mas frecuentes?",
        "pt": "Quais sao os pares mais frequentes?",
        "de": "Welche Paare kommen am haufigsten vor?",
        "nl": "Welke paren komen het vaakst voor?",
        "expected": "pairs",
    },
    "Hors-sujet": {
        "fr": "Quel temps fait-il a Paris ?",
        "en": "What's the weather like in London?",
        "es": "Que tiempo hace en Madrid?",
        "pt": "Como esta o tempo em Lisboa?",
        "de": "Wie ist das Wetter in Berlin?",
        "nl": "Hoe is het weer in Brussel?",
        "expected": "gemini",
    },
    "Systeme": {
        "fr": "Comment fonctionne ton algorithme ?",
        "en": "How does your algorithm work?",
        "es": "Como funciona tu algoritmo?",
        "pt": "Como funciona o teu algoritmo?",
        "de": "Wie funktioniert dein Algorithmus?",
        "nl": "Hoe werkt je algoritme?",
        "expected": "gemini",
    },
}

LANGS = ["fr", "en", "es", "pt", "de", "nl"]


def run_detections(msg, lang):
    """Run all detectors on a message, return (detections, early_response, source)."""
    detections = []
    early_response = None
    source = None

    # Phase I — Insult
    insult_result = _detect_insulte(msg)
    if insult_result:
        detections.append("insult")
        resp = get_insult_response(lang, 0, [])
        early_response = resp
        source = "hybride_insult"

    # Phase A — Argent
    if _detect_argent_em(msg, lang):
        detections.append("argent")
        resp = _get_argent_response_em(msg, lang)
        if not early_response:
            early_response = resp
            source = "hybride_argent"

    # Phase GEO
    country = _detect_country_em(msg)
    if country:
        detections.append("country_geo")
        ctx = _get_country_context_em(country)

    # Phase P+ — Co-occurrence high N
    cooc = _detect_cooccurrence_high_n(msg)
    if cooc:
        detections.append("cooc_high_n")
        if not early_response:
            resp = _get_cooccurrence_high_n_response(msg, lang=lang)
            early_response = resp
            source = "hybride_cooccurrence"

    # Phase P — Pairs
    pairs = _detect_paires_em(msg)
    if pairs:
        detections.append("paires")

    # Phase P — Triplets
    triplets = _detect_triplets_em(msg)
    if triplets:
        detections.append("triplets")

    # Phase 3 — Complex
    complex_q = _detect_requete_complexe_em(msg)
    if complex_q:
        detections.append("complexe")

    return detections, early_response, source


def score_question(q_name, expected, msg, lang, detections, early_response, source):
    """Score a single question: P(5) H(5) L(5) S(5) = 20 max."""
    p_score = 0  # Pipeline detection correctness
    h_score = 0  # Honesty (response quality)
    l_score = 0  # Language correctness
    s_score = 5  # Structure (always 5 for valid pipeline)
    notes = []

    # --- P: Pipeline detection ---
    if expected == "insult":
        if "insult" in detections:
            p_score = 5
        else:
            p_score = 1
            notes.append("Insult NOT detected")
    elif expected == "argent":
        if "argent" in detections:
            p_score = 5
        else:
            p_score = 2
            notes.append("Argent NOT detected")
    elif expected == "geo":
        if "country_geo" in detections:
            p_score = 4
        else:
            p_score = 2
            notes.append("GEO NOT detected")
    elif expected == "P+":
        if "cooc_high_n" in detections:
            p_score = 5
        elif "paires" in detections:
            p_score = 3
        else:
            p_score = 1
            notes.append("Co-occurrence NOT detected")
    elif expected == "pairs":
        if "paires" in detections:
            p_score = 4
        elif "complexe" in detections:
            p_score = 3
        else:
            p_score = 1
            notes.append("Pairs NOT detected")
    elif expected == "complex":
        if "complexe" in detections:
            p_score = 4
        else:
            p_score = 2
            notes.append("Complex NOT detected")
    elif expected == "sql":
        if "complexe" in detections:
            p_score = 3
        else:
            p_score = 3
            notes.append("Falls through to Gemini/SQL (correct)")
    elif expected == "gemini":
        # Should fall through — no early detection is fine
        if not early_response:
            p_score = 3
            notes.append("Falls through to Gemini (correct)")
        else:
            p_score = 2
            notes.append(f"Unexpected early return: {source}")

    # --- H: Honesty ---
    if early_response:
        h_score = 5  # Has a response
    else:
        h_score = 3  # Needs Gemini/DB — can't verify here
        notes.append("Honesty needs Gemini")

    # --- L: Language ---
    if early_response:
        resp_lower = early_response.lower()
        # Check language markers
        lang_markers = {
            "fr": ["tirage", "numéro", "bonjour", "insulte", "grille", "données", "statistique", "gratuit", "glisse", "charmant"],
            "en": ["draw", "number", "hello", "insult", "grid", "data", "statistic", "free", "duck", "charming"],
            "es": ["sorteo", "número", "hola", "insulto", "parrilla", "datos", "estadística", "gratis", "resbala", "encantador", "pregunta"],
            "pt": ["sorteio", "número", "olá", "insulto", "grelha", "dados", "estatística", "grátis", "escorrega", "encantador", "pergunta"],
            "de": ["ziehung", "zahl", "hallo", "beleidigung", "raster", "daten", "statistik", "kostenlos", "perlt", "charmant", "frage", "algorithmus"],
            "nl": ["trekking", "nummer", "hallo", "belediging", "rooster", "gegevens", "statistiek", "gratis", "glijdt", "charmant", "vraag", "algoritme"],
        }
        # Check it's not in FR when lang != fr
        fr_only = ["tirage", "numéro", "insulte", "grille", "données", "glisse", "charmant", "passons", "noté", "abstraction"]
        en_only = ["draw", "insult", "duck", "charming", "classy", "noted", "slide"]

        if lang == "fr":
            l_score = 5
        elif lang == "en":
            # Check not FR
            if any(w in resp_lower for w in fr_only):
                l_score = 1
                notes.append("LANG BUG: FR response for EN")
            else:
                l_score = 5
        else:
            # ES/PT/DE/NL — check not FR and not EN
            if any(w in resp_lower for w in fr_only):
                l_score = 1
                notes.append(f"LANG BUG: FR response for {lang.upper()}")
            elif source == "hybride_insult" and any(w in resp_lower for w in en_only):
                l_score = 2
                notes.append(f"LANG BUG: EN response for {lang.upper()}")
            else:
                l_score = 5
    else:
        # No early response — lang check depends on Gemini
        if expected in ("gemini", "sql"):
            l_score = 3
            notes.append("Lang check needs Gemini")
        elif expected == "geo":
            l_score = 5  # GEO context is injected, Gemini responds
        elif expected in ("complex", "pairs"):
            l_score = 3
            notes.append("Lang check needs Gemini/DB")
        else:
            l_score = 3

    return p_score, h_score, l_score, s_score, notes


def main():
    print("=" * 90)
    print("  AUDIT 360 HYBRIDE EM v3 -- 60 tests (10 questions x 6 langues)")
    print("=" * 90)
    print()

    results = {}  # {q_name: {lang: (p, h, l, s, notes)}}
    lang_totals = {lang: 0 for lang in LANGS}

    for q_name, q_data in QUESTIONS.items():
        expected = q_data["expected"]
        results[q_name] = {}
        for lang in LANGS:
            msg = q_data[lang]
            detections, early_response, source = run_detections(msg, lang)
            p, h, l, s, notes = score_question(q_name, expected, msg, lang, detections, early_response, source)
            total = p + h + l + s
            results[q_name][lang] = (total, p, h, l, s, detections, source, notes)
            lang_totals[lang] += total

    # --- Table ---
    header = f"{'Question':<30}" + "".join(f"{lang.upper():>7}" for lang in LANGS) + "    Moy"
    print(header)
    print("-" * 90)

    q_avgs = []
    for q_name in QUESTIONS:
        row = f"{q_name:<30}"
        scores = []
        for lang in LANGS:
            total = results[q_name][lang][0]
            row += f"{total:>4}/20 "
            scores.append(total)
        avg = sum(scores) / len(scores)
        q_avgs.append(avg)
        row += f" {avg:.1f}/20"
        print(row)

    print("-" * 90)

    # Totals per lang as %
    row = f"{'TOTAL':<30}"
    for lang in LANGS:
        pct = lang_totals[lang] / 200 * 100
        row += f"  {pct:.0f}%   "
    global_score = sum(lang_totals.values()) / (200 * 6) * 100
    row += f" {global_score:.1f}%"
    print(row)

    # --- Bar chart ---
    print()
    print("=" * 90)
    print("  SCORES PAR LANGUE (/100)")
    print("=" * 90)
    for lang in LANGS:
        score = lang_totals[lang] / 200 * 100
        filled = int(score / 2)
        empty = 50 - filled
        bar = "#" * filled + "." * empty
        print(f"  {lang.upper()}  {bar} {score:.1f}/100")

    print()
    print(f"  SCORE HYBRIDE EM GLOBAL = {global_score:.1f}/100")

    # --- Detail ---
    print()
    print("=" * 90)
    print("  DETAIL DETECTIONS PAR QUESTION")
    print("=" * 90)
    print()

    for q_name, q_data in QUESTIONS.items():
        expected = q_data["expected"]
        print(f"  {q_name} (expected: {expected})")
        for lang in LANGS:
            total, p, h, l, s, dets, src, notes = results[q_name][lang]
            det_str = ", ".join(dets) if dets else "(none)"
            src_str = src if src else "(->Gemini/DB)"
            notes_str = "; ".join(notes) if notes else ""
            print(f"    {lang.upper()} [{total:>2}/20] P{p} H{h} L{l} S{s} | det=[{det_str}] src={src_str}")
            if notes_str:
                print(f"         notes: {notes_str}")
        print()

    # --- Comparison v2 -> v3 ---
    print("=" * 90)
    print("  EVOLUTION v2 -> v3")
    print("=" * 90)
    v2_scores = {"fr": 81.0, "en": 81.0, "es": 77.0, "pt": 79.0, "de": 78.0, "nl": 79.0}
    v2_global = 79.2
    print(f"  {'Lang':<6} {'v2':>8} {'v3':>8} {'Delta':>8}")
    print(f"  {'-'*32}")
    for lang in LANGS:
        v3 = lang_totals[lang] / 200 * 100
        v2 = v2_scores[lang]
        delta = v3 - v2
        sign = "+" if delta > 0 else ""
        print(f"  {lang.upper():<6} {v2:>7.1f}% {v3:>7.1f}% {sign}{delta:>7.1f}%")
    print(f"  {'-'*32}")
    print(f"  {'GLOBAL':<6} {v2_global:>7.1f}% {global_score:>7.1f}% {'+' if global_score > v2_global else ''}{global_score - v2_global:>7.1f}%")
    print()


if __name__ == "__main__":
    main()
