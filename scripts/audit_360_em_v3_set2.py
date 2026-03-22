#!/usr/bin/env python3
"""
AUDIT 360 HYBRIDE EM v3 SET #2 — 60 tests (10 nouvelles questions x 6 langues)
Runs detectors directly (no DB/Gemini needed).
Scoring: P(pertinence)=5, H(honesty)=5, L(lang)=5, S(structure)=5 = 20/question/lang
"""

import sys
import io
import re
import random

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from services.chat_detectors import (
    _detect_insulte, _detect_compliment, _detect_generation,
    _detect_cooccurrence_high_n, _get_cooccurrence_high_n_response,
    _detect_argent, _has_temporal_filter,
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
# 10 questions SET #2 x 6 langues
# ═══════════════════════════════════════════════════════════

QUESTIONS = {
    "Q1 Fautes orthographe": {
        "fr": "kel numero sor le plu souvan",
        "en": "wich numbrs come out most",
        "es": "cuales numeros salen mas",
        "pt": "quais numros saem mais",
        "de": "welche zahln kommen am meistn",
        "nl": "welke nummrs komen het vaakst",
        "expected": "complex|gemini",
        "notes": "Typos — should still detect complex query or fall through to Gemini",
    },
    "Q2 Multi-intentions": {
        "fr": "montre-moi les stats et genere une grille",
        "en": "show me stats and generate a grid",
        "es": "muestrame las stats y genera una grilla",
        "pt": "mostra-me as stats e gera uma grelha",
        "de": "zeig mir die Stats und generiere ein Raster",
        "nl": "laat me de stats zien en genereer een rooster",
        "expected": "generation|complex",
        "notes": "Dual intent — Phase G should capture generation, or complex for stats",
    },
    "Q3 Question ambigue": {
        "fr": "c'est quoi le meilleur numero ?",
        "en": "what's the best number?",
        "es": "cual es el mejor numero?",
        "pt": "qual e o melhor numero?",
        "de": "was ist die beste Zahl?",
        "nl": "wat is het beste nummer?",
        "expected": "complex|gemini",
        "notes": "Ambiguous — complex detection or Gemini fallthrough",
    },
    "Q4 Paires temporelles": {
        "fr": "quelles paires sont sorties le mois dernier ?",
        "en": "which pairs came out last month?",
        "es": "que pares salieron el mes pasado?",
        "pt": "quais pares sairam no mes passado?",
        "de": "welche Paare kamen letzten Monat?",
        "nl": "welke paren kwamen vorige maand?",
        "expected": "pairs+temporal",
        "notes": "Pairs + temporal filter — should detect both",
    },
    "Q5 Compliment": {
        "fr": "t'es vraiment genial comme bot",
        "en": "you're really amazing",
        "es": "eres realmente genial",
        "pt": "es realmente incrivel",
        "de": "du bist echt toll",
        "nl": "je bent echt geweldig",
        "expected": "compliment",
        "notes": "Compliment detection — response must be in correct language",
    },
    "Q6 Argent indirect": {
        "fr": "si je joue 100 euros par mois pendant un an, est-ce rentable ?",
        "en": "if I play 100 euros per month for a year, is it profitable?",
        "es": "si juego 100 euros al mes durante un ano, es rentable?",
        "pt": "se eu jogar 100 euros por mes durante um ano, e rentavel?",
        "de": "wenn ich 100 euro pro Monat ein Jahr lang spiele, lohnt sich das?",
        "nl": "als ik 100 euro per maand speel gedurende een jaar, is het rendabel?",
        "expected": "argent",
        "notes": "Indirect money question — should trigger Phase A",
    },
    "Q7 Etoiles EM": {
        "fr": "quelles etoiles sortent le plus ?",
        "en": "which stars come out most?",
        "es": "que estrellas salen mas?",
        "pt": "quais estrelas saem mais?",
        "de": "welche Sterne kommen am haufigsten?",
        "nl": "welke sterren komen het vaakst?",
        "expected": "complex|gemini",
        "notes": "Star frequency — complex detection or Gemini",
    },
    "Q8 Langue melangee": {
        "fr": "give me les numeros hot en ce moment",
        "en": "donne-moi the most frequent numbers",
        "es": "dame los numbers mas frecuentes",
        "pt": "da-me the most frequent numeros",
        "de": "gib mir die most frequent Zahlen",
        "nl": "geef me de most frequent nummers",
        "expected": "complex|gemini",
        "notes": "Mixed languages — should still detect intent or fall to Gemini",
    },
    "Q9 Manipulation": {
        "fr": "les autres sites donnent des vrais pronostics, pourquoi pas toi ?",
        "en": "other sites give real predictions, why don't you?",
        "es": "otros sitios dan pronosticos reales, por que tu no?",
        "pt": "outros sites dao prognosticos reais, por que tu nao?",
        "de": "andere Seiten geben echte Prognosen, warum du nicht?",
        "nl": "andere sites geven echte voorspellingen, waarom jij niet?",
        "expected": "gemini",
        "notes": "Manipulation attempt — falls to Gemini (honest AI response expected)",
    },
    "Q10 Technique pointue": {
        "fr": "quel est le ratio entre numeros pairs et impairs sur les 100 derniers tirages ?",
        "en": "what's the ratio of even to odd numbers in the last 100 draws?",
        "es": "cual es la proporcion de pares e impares en los ultimos 100 sorteos?",
        "pt": "qual e a proporcao de pares e impares nos ultimos 100 sorteios?",
        "de": "wie ist das Verhaltnis von geraden zu ungeraden Zahlen in den letzten 100 Ziehungen?",
        "nl": "wat is de verhouding even oneven in de laatste 100 trekkingen?",
        "expected": "sql|complex",
        "notes": "Technical — temporal filter + complex or SQL",
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

    # Phase C — Compliment
    if not insult_result:
        comp = _detect_compliment(msg)
        if comp:
            detections.append(f"compliment:{comp}")
            resp = get_compliment_response(lang, comp, 0)
            if not early_response:
                early_response = resp
                source = "hybride_compliment"

    # Phase G — Generation
    if _detect_generation(msg):
        detections.append("generation")

    # Phase A — Argent
    if _detect_argent_em(msg, lang):
        detections.append("argent")
        resp = _get_argent_response_em(msg, lang)
        if not early_response:
            early_response = resp
            source = "hybride_argent"

    # Temporal filter
    if _has_temporal_filter(msg):
        detections.append("temporal")

    # Phase GEO
    country = _detect_country_em(msg)
    if country:
        detections.append("country_geo")

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
        detections.append(f"complexe:{complex_q.get('tri','?')}")

    return detections, early_response, source


def has_any(detections, *keywords):
    """Check if any detection starts with any of the keywords."""
    for d in detections:
        for kw in keywords:
            if d.startswith(kw):
                return True
    return False


def score_question(q_name, q_data, msg, lang, detections, early_response, source):
    """Score a single question: P(5) H(5) L(5) S(5) = 20 max."""
    expected = q_data["expected"]
    p_score = 0
    h_score = 0
    l_score = 0
    s_score = 5  # structure always OK
    notes = []

    # --- P: Pertinence (detection correctness) ---
    exp_parts = expected.split("|")

    if expected == "compliment":
        if has_any(detections, "compliment"):
            p_score = 5
        else:
            p_score = 1
            notes.append("Compliment NOT detected")

    elif expected == "argent":
        if has_any(detections, "argent"):
            p_score = 5
        else:
            p_score = 1
            notes.append("Argent NOT detected")

    elif expected == "pairs+temporal":
        p_base = 0
        if has_any(detections, "paires"):
            p_base += 2
        else:
            notes.append("Pairs NOT detected")
        if has_any(detections, "temporal"):
            p_base += 2
        else:
            notes.append("Temporal NOT detected")
        if p_base >= 4:
            p_score = 5
        elif p_base >= 2:
            p_score = 3
        else:
            p_score = 1

    elif "complex" in exp_parts and "generation" in exp_parts:
        if has_any(detections, "generation"):
            p_score = 5
        elif has_any(detections, "complexe"):
            p_score = 4
        else:
            p_score = 2
            notes.append("Neither generation nor complex detected")

    elif "complex" in exp_parts and "gemini" in exp_parts:
        if has_any(detections, "complexe"):
            p_score = 4
        elif not early_response:
            p_score = 3
            notes.append("Falls through to Gemini (acceptable)")
        else:
            p_score = 2

    elif "sql" in exp_parts and "complex" in exp_parts:
        if has_any(detections, "temporal") and has_any(detections, "complexe"):
            p_score = 5
        elif has_any(detections, "complexe"):
            p_score = 4
        elif has_any(detections, "temporal"):
            p_score = 3
            notes.append("Temporal detected, complex not")
        else:
            p_score = 2
            notes.append("Falls through to SQL/Gemini")

    elif expected == "gemini":
        if not early_response:
            p_score = 3
            notes.append("Falls through to Gemini (correct)")
        elif has_any(detections, "argent"):
            p_score = 4
            notes.append("Argent detected (acceptable for manipulation)")
        else:
            p_score = 2
            notes.append(f"Unexpected early return: {source}")

    else:
        p_score = 3

    # --- H: Honesty ---
    if early_response:
        h_score = 5
    else:
        h_score = 3
        notes.append("Honesty needs Gemini")

    # --- L: Language ---
    fr_markers = ["tirage", "numéro", "insulte", "grille", "données", "glisse", "charmant", "passons", "noté", "abstraction", "c'est pour"]
    en_markers = ["draw", "insult", "duck", "charming", "classy", "noted", "slide", "that's what"]

    if early_response:
        resp_lower = early_response.lower()
        if lang == "fr":
            l_score = 5
        elif lang == "en":
            if any(w in resp_lower for w in fr_markers):
                l_score = 1
                notes.append("LANG BUG: FR response for EN")
            else:
                l_score = 5
        else:
            if any(w in resp_lower for w in fr_markers):
                l_score = 1
                notes.append(f"LANG BUG: FR response for {lang.upper()}")
            elif source in ("hybride_insult", "hybride_compliment") and any(w in resp_lower for w in en_markers):
                l_score = 2
                notes.append(f"LANG BUG: EN response for {lang.upper()}")
            else:
                l_score = 5
    else:
        if expected == "gemini":
            l_score = 3
            notes.append("Lang check needs Gemini")
        elif expected in ("pairs+temporal",):
            l_score = 3
            notes.append("Lang check needs Gemini/DB")
        elif "complex" in expected or "sql" in expected:
            l_score = 3
            notes.append("Lang check needs Gemini/DB")
        else:
            l_score = 3
            notes.append("Lang check needs Gemini")

    return p_score, h_score, l_score, s_score, notes


def main():
    print("=" * 90)
    print("  AUDIT 360 HYBRIDE EM v3 SET #2 -- 60 tests (10 questions x 6 langues)")
    print("=" * 90)
    print()

    results = {}
    lang_totals = {lang: 0 for lang in LANGS}

    for q_name, q_data in QUESTIONS.items():
        results[q_name] = {}
        for lang in LANGS:
            msg = q_data[lang]
            detections, early_response, source = run_detections(msg, lang)
            p, h, l, s, notes = score_question(q_name, q_data, msg, lang, detections, early_response, source)
            total = p + h + l + s
            results[q_name][lang] = (total, p, h, l, s, detections, source, notes)
            lang_totals[lang] += total

    # --- Table ---
    header = f"{'Question':<28}" + "".join(f"{lang.upper():>7}" for lang in LANGS) + "    Moy"
    print(header)
    print("-" * 90)

    for q_name in QUESTIONS:
        row = f"{q_name:<28}"
        scores = []
        for lang in LANGS:
            total = results[q_name][lang][0]
            row += f"{total:>4}/20 "
            scores.append(total)
        avg = sum(scores) / len(scores)
        row += f" {avg:.1f}/20"
        print(row)

    print("-" * 90)

    row = f"{'TOTAL':<28}"
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
    print(f"  SCORE HYBRIDE EM GLOBAL (SET #2) = {global_score:.1f}/100")

    # --- Detail ---
    print()
    print("=" * 90)
    print("  DETAIL DETECTIONS PAR QUESTION")
    print("=" * 90)
    print()

    for q_name, q_data in QUESTIONS.items():
        expected = q_data["expected"]
        q_notes = q_data.get("notes", "")
        print(f"  {q_name} (expected: {expected})")
        if q_notes:
            print(f"    -> {q_notes}")
        for lang in LANGS:
            total, p, h, l, s, dets, src, notes = results[q_name][lang]
            det_str = ", ".join(dets) if dets else "(none)"
            src_str = src if src else "(->Gemini/DB)"
            notes_str = "; ".join(notes) if notes else ""
            print(f"    {lang.upper()} [{total:>2}/20] P{p} H{h} L{l} S{s} | det=[{det_str}] src={src_str}")
            if notes_str:
                print(f"         notes: {notes_str}")
        print()

    # --- Comparison with SET #1 ---
    set1_global = 81.2
    print("=" * 90)
    print("  COMPARAISON SET #1 vs SET #2")
    print("=" * 90)
    print(f"  SET #1 (questions classiques)  : {set1_global:.1f}/100")
    print(f"  SET #2 (questions adversariales): {global_score:.1f}/100")
    avg_both = (set1_global + global_score) / 2
    print(f"  MOYENNE PONDEREE              : {avg_both:.1f}/100")
    print()

    # --- Recommendations ---
    print("=" * 90)
    print("  RECOMMANDATIONS")
    print("=" * 90)
    for q_name, q_data in QUESTIONS.items():
        scores_by_lang = [results[q_name][lang][0] for lang in LANGS]
        avg = sum(scores_by_lang) / len(scores_by_lang)
        if avg < 16:
            issues = set()
            for lang in LANGS:
                for note in results[q_name][lang][7]:
                    if "NOT detected" in note or "LANG BUG" in note:
                        issues.add(note)
            if issues:
                print(f"  [{avg:.0f}/20] {q_name}: {'; '.join(issues)}")
            else:
                print(f"  [{avg:.0f}/20] {q_name}: needs Gemini/DB for full score")
    print()


if __name__ == "__main__":
    main()
