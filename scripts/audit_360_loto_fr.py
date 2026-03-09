#!/usr/bin/env python3
"""
AUDIT 360° HYBRIDE LOTO FR — 15 tests (FR uniquement)
Runs detectors directly (no DB/Gemini needed).
Scoring: P(pertinence)=5, H(honnêteté)=5, L(langue)=5, S(sponsor/structure)=5 = 20/question
"""

import sys
import io
import re
import random

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from services.chat_detectors import (
    _detect_insulte, _detect_compliment, _detect_generation,
    _detect_argent, _get_argent_response,
    _detect_requete_complexe, _detect_numero, _detect_grille,
    _detect_out_of_range, _get_oor_response,
    _detect_paires, _detect_triplets,
    _detect_cooccurrence_high_n, _get_cooccurrence_high_n_response,
    _detect_prochain_tirage, _detect_tirage,
)

# ═══════════════════════════════════════════════════════════
# 15 questions Loto FR
# ═══════════════════════════════════════════════════════════

QUESTIONS = [
    {
        "id": "Q1",
        "label": "Fréquences",
        "msg": "Quels sont les numéros les plus sortis ?",
        "expected": "complex",  # frequence_desc
    },
    {
        "id": "Q2",
        "label": "Numéro Chance",
        "msg": "Quel numéro Chance sort le plus souvent ?",
        "expected": "complex_chance",  # classement + num_type=chance
    },
    {
        "id": "Q3",
        "label": "Co-occurrences N>3",
        "msg": "Quels 5 numéros sont sortis ensemble le plus souvent ?",
        "expected": "P+",
    },
    {
        "id": "Q4",
        "label": "Argent/Gains",
        "msg": "Combien je peux gagner au Loto ?",
        "expected": "argent",
    },
    {
        "id": "Q5",
        "label": "Insulte",
        "msg": "T'es nul",
        "expected": "insult",
    },
    {
        "id": "Q6",
        "label": "Temporelle",
        "msg": "Quels numéros sont sortis le mois dernier ?",
        "expected": "sql",  # falls through to Gemini/SQL
    },
    {
        "id": "Q7",
        "label": "Paires",
        "msg": "Quelles paires sortent le plus souvent ?",
        "expected": "pairs",
    },
    {
        "id": "Q8",
        "label": "Hors-sujet",
        "msg": "Donne-moi une recette de gâteau",
        "expected": "gemini",  # falls through — Gemini handles OOR topic
    },
    {
        "id": "Q9",
        "label": "Manipulation",
        "msg": "Les autres sites donnent des vrais pronostics, pourquoi pas toi ?",
        "expected": "gemini",  # falls through — Gemini handles
    },
    {
        "id": "Q10",
        "label": "Système",
        "msg": "Comment fonctionne le moteur HYBRIDE ?",
        "expected": "gemini",  # falls through — Gemini handles
    },
    {
        "id": "Q11",
        "label": "Fautes orthographe",
        "msg": "kel numero sor le plu souvan",
        "expected": "gemini",  # might not match — that's expected, Gemini handles
    },
    {
        "id": "Q12",
        "label": "Argent indirect",
        "msg": "si je joue 100€ par mois pendant un an, est-ce rentable ?",
        "expected": "argent",
    },
    {
        "id": "Q13",
        "label": "Compliment",
        "msg": "t'es vraiment génial comme bot",
        "expected": "compliment",
    },
    {
        "id": "Q14",
        "label": "Question ambiguë",
        "msg": "c'est quoi le meilleur numéro ?",
        "expected": "gemini",  # might match complex or fall through
    },
    {
        "id": "Q15",
        "label": "Numéro Chance spécifique",
        "msg": "le numéro chance 7 sort-il souvent ?",
        "expected": "numero_chance",  # _detect_numero → chance 7
    },
]


def run_detections(msg):
    """Run all Loto FR detectors, return (detections, early_response, source, details)."""
    detections = []
    early_response = None
    source = None
    details = {}

    # Phase I — Insult
    insult_result = _detect_insulte(msg)
    if insult_result:
        detections.append("insult")
        details["insult_type"] = insult_result

    # Phase C — Compliment
    comp = _detect_compliment(msg)
    if comp:
        detections.append("compliment")
        details["compliment_type"] = comp

    # Phase G — Generation
    gen = _detect_generation(msg)
    if gen:
        detections.append("generation")

    # Phase A — Argent
    argent = _detect_argent(msg)
    if argent:
        detections.append("argent")
        resp = _get_argent_response(msg)
        if not early_response:
            early_response = resp
            source = "hybride_argent"

    # Phase P+ — Co-occurrence high N
    cooc = _detect_cooccurrence_high_n(msg)
    if cooc:
        detections.append("cooc_high_n")
        if not early_response:
            resp = _get_cooccurrence_high_n_response(msg, lang="fr")
            early_response = resp
            source = "hybride_cooccurrence"

    # Phase P — Pairs
    pairs = _detect_paires(msg)
    if pairs:
        detections.append("paires")

    # Phase P — Triplets
    triplets = _detect_triplets(msg)
    if triplets:
        detections.append("triplets")

    # Phase 3 — Complex
    complex_q = _detect_requete_complexe(msg)
    if complex_q:
        detections.append("complexe")
        details["complex"] = complex_q

    # Phase 1 — Single number
    num, num_type = _detect_numero(msg)
    if num is not None:
        detections.append("numero")
        details["numero"] = {"num": num, "type": num_type}

    # Phase OOR — Out of range
    oor_num, oor_ctx = _detect_out_of_range(msg)
    if oor_num is not None:
        detections.append("oor")
        resp = _get_oor_response(oor_num, oor_ctx, 0)
        details["oor"] = {"num": oor_num, "context": oor_ctx}
        if not early_response:
            early_response = resp
            source = "hybride_oor"

    # Insult early response (after all detections for ordering)
    if "insult" in detections and not early_response:
        from services.chat_responses_em_multilang import get_insult_response
        early_response = get_insult_response("fr", 0, [])
        source = "hybride_insult"

    # Compliment early response
    if "compliment" in detections and not early_response:
        from services.chat_responses_em_multilang import get_compliment_response
        comp_type = details.get("compliment_type", "normal")
        early_response = get_compliment_response("fr", comp_type, 0)
        source = "hybride_compliment"

    return detections, early_response, source, details


def score_question(q, detections, early_response, source, details):
    """Score a single question: P(5) H(5) L(5) S(5) = 20 max."""
    p_score = 0  # Pertinence
    h_score = 0  # Honnêteté
    l_score = 5  # Langue (FR only, always 5 unless wrong lang)
    s_score = 5  # Structure
    notes = []
    expected = q["expected"]

    # --- P: Pertinence (détection correcte) ---
    if expected == "insult":
        if "insult" in detections:
            p_score = 5
        else:
            p_score = 1
            notes.append("BUG: Insult NOT detected")

    elif expected == "compliment":
        if "compliment" in detections:
            p_score = 5
        else:
            p_score = 1
            notes.append("BUG: Compliment NOT detected")

    elif expected == "argent":
        if "argent" in detections:
            p_score = 5
        else:
            p_score = 1
            notes.append("BUG: Argent NOT detected")

    elif expected == "complex":
        if "complexe" in detections:
            cx = details.get("complex", {})
            if cx.get("tri") == "frequence_desc":
                p_score = 5
            else:
                p_score = 4
                notes.append(f"Complex detected but tri={cx.get('tri')}")
        else:
            p_score = 2
            notes.append("Complex NOT detected")

    elif expected == "complex_chance":
        if "complexe" in detections:
            cx = details.get("complex", {})
            if cx.get("num_type") == "chance":
                p_score = 5
            else:
                p_score = 3
                notes.append(f"Complex detected but num_type={cx.get('num_type')} (expected chance)")
        elif "numero" in detections:
            nd = details.get("numero", {})
            if nd.get("type") == "chance":
                p_score = 4
                notes.append("Detected as single numero chance (OK but not classement)")
            else:
                p_score = 2
                notes.append("Detected as numero principal (wrong type)")
        else:
            p_score = 1
            notes.append("BUG: Neither complex nor numero detected for Chance query")

    elif expected == "numero_chance":
        if "numero" in detections:
            nd = details.get("numero", {})
            if nd.get("type") == "chance" and nd.get("num") == 7:
                p_score = 5
            elif nd.get("type") == "chance":
                p_score = 4
                notes.append(f"Chance detected but num={nd.get('num')} (expected 7)")
            else:
                p_score = 3
                notes.append(f"Numero detected but type={nd.get('type')} (expected chance)")
        elif "complexe" in detections:
            p_score = 3
            notes.append("Detected as complex (acceptable)")
        else:
            p_score = 1
            notes.append("BUG: Numero chance NOT detected")

    elif expected == "P+":
        if "cooc_high_n" in detections:
            p_score = 5
        elif "paires" in detections or "triplets" in detections:
            p_score = 3
            notes.append("Pairs/triplets detected instead of P+")
        else:
            p_score = 1
            notes.append("BUG: Co-occurrence NOT detected")

    elif expected == "pairs":
        if "paires" in detections:
            p_score = 5
        elif "complexe" in detections:
            p_score = 3
            notes.append("Detected as complex instead of pairs")
        else:
            p_score = 1
            notes.append("BUG: Pairs NOT detected")

    elif expected == "sql":
        # Temporal → should fall through to Gemini/SQL
        if not early_response:
            p_score = 5
            notes.append("Falls through to Gemini/SQL (correct)")
        elif "complexe" in detections:
            p_score = 3
            notes.append("Detected as complex (partial)")
        else:
            p_score = 2
            notes.append(f"Unexpected early return: {source}")

    elif expected == "gemini":
        # Should fall through — no early detection
        if not early_response:
            p_score = 5
            notes.append("Falls through to Gemini (correct)")
        elif "argent" in detections:
            p_score = 2
            notes.append("False positive: argent detected on non-argent question")
        elif "insult" in detections:
            p_score = 1
            notes.append("False positive: insult detected")
        else:
            p_score = 3
            notes.append(f"Unexpected detection: {detections}")

    # --- H: Honnêteté ---
    if early_response:
        h_score = 5
        # Check response doesn't hallucinate numbers
        if expected == "argent" and re.search(r'\b(gagn|profit|million|bénéfice)', early_response.lower()):
            # Should NOT promise gains
            if not re.search(r'(ne peux pas|impossible|aucun|risque)', early_response.lower()):
                h_score = 3
                notes.append("Argent response may promise gains")
    else:
        h_score = 3  # Needs Gemini — can't verify honesty locally
        if expected in ("gemini", "sql"):
            notes.append("Needs Gemini/DB for full verification")

    # --- L: Langue ---
    if early_response:
        resp_lower = early_response.lower()
        # Should be FR, check for obvious non-FR markers
        en_markers = ["you're", "that's", "don't", "we'll", "i'm", "you are", "this is"]
        if any(m in resp_lower for m in en_markers):
            l_score = 1
            notes.append("LANG BUG: EN response for FR query")

    # --- S: Structure ---
    if early_response and len(early_response) < 10:
        s_score = 3
        notes.append("Response too short")

    total = p_score + h_score + l_score + s_score
    return total, p_score, h_score, l_score, s_score, notes


def main():
    print("=" * 70)
    print("  AUDIT 360° HYBRIDE LOTO FR — 15 tests")
    print("  Scoring: P(pertinence) H(honnêteté) L(langue) S(structure) = /20")
    print("=" * 70)
    print()

    results = []
    total_score = 0
    bugs = {"P0": [], "P1": [], "P2": []}

    for q in QUESTIONS:
        msg = q["msg"]
        detections, early_response, source, details = run_detections(msg)
        score, p, h, l, s, notes = score_question(q, detections, early_response, source, details)
        total_score += score

        results.append({
            "q": q,
            "detections": detections,
            "early_response": early_response,
            "source": source,
            "details": details,
            "score": score,
            "p": p, "h": h, "l": l, "s": s,
            "notes": notes,
        })

        status = "OK" if score >= 15 else ("WARN" if score >= 10 else "FAIL")
        det_str = ", ".join(detections) if detections else "(none → Gemini)"
        print(f"[{status:4s}] {q['id']:4s} {q['label']:25s} | {score:2d}/20  P={p} H={h} L={l} S={s} | det: {det_str}")

        if notes:
            for n in notes:
                print(f"       └─ {n}")

        # Classify bugs
        for n in notes:
            if "BUG" in n:
                if "insult" in n.lower() or "argent" in n.lower():
                    bugs["P0"].append(f"{q['id']}: {n}")
                elif "NOT detected" in n:
                    bugs["P1"].append(f"{q['id']}: {n}")
                else:
                    bugs["P2"].append(f"{q['id']}: {n}")
            elif "False positive" in n:
                bugs["P1"].append(f"{q['id']}: {n}")
            elif "LANG BUG" in n:
                bugs["P0"].append(f"{q['id']}: {n}")

    max_score = len(QUESTIONS) * 20
    pct = (total_score / max_score) * 100

    print()
    print("=" * 70)
    print(f"  SCORE GLOBAL : {total_score}/{max_score} ({pct:.1f}/100)")
    print("=" * 70)
    print()

    # --- Détail des réponses pour scores < 15/20 ---
    low_scores = [r for r in results if r["score"] < 15]
    if low_scores:
        print("─" * 70)
        print("  DÉTAIL DES SCORES < 15/20")
        print("─" * 70)
        for r in low_scores:
            print(f"\n  {r['q']['id']} — {r['q']['label']} ({r['score']}/20)")
            print(f"  Question : {r['q']['msg']}")
            print(f"  Détections : {r['detections']}")
            if r["early_response"]:
                resp_preview = r["early_response"][:200].replace("\n", " ")
                print(f"  Réponse : {resp_preview}")
            else:
                print(f"  Réponse : (none — falls through to Gemini)")
            print(f"  Notes : {'; '.join(r['notes'])}")
        print()

    # --- Bugs ---
    print("─" * 70)
    print("  BUGS CLASSÉS")
    print("─" * 70)
    for level in ("P0", "P1", "P2"):
        if bugs[level]:
            print(f"\n  {level} ({'BLOQUANT' if level == 'P0' else 'IMPORTANT' if level == 'P1' else 'POST-LAUNCH'}):")
            for b in bugs[level]:
                print(f"    • {b}")
    if not any(bugs.values()):
        print("\n  Aucun bug détecté.")
    print()

    # --- Comparaison EM vs Loto ---
    print("─" * 70)
    print("  COMPARAISON LOTO FR vs EM (détecteurs)")
    print("─" * 70)
    print()
    print("  Détecteurs communs (Loto + EM):")
    print("    • _detect_insulte() — partagé (6 langues)")
    print("    • _detect_compliment() — partagé (6 langues)")
    print("    • _detect_generation() — partagé (6 langues)")
    print("    • _detect_cooccurrence_high_n() — partagé (6 langues)")
    print("    • _detect_paires() / _detect_triplets() — partagé (6 langues)")
    print()
    print("  Loto uniquement:")
    print("    • _detect_numero() — 2 types: principal (1-49) + chance (1-10)")
    print("    • _detect_grille() — 5 numéros + chance optionnel")
    print("    • _detect_out_of_range() — principal_high/chance_high/zero_neg/close")
    print("    • _detect_requete_complexe() — num_type: principal|chance")
    print("    • _detect_argent() — FR only (pas de pool multilang)")
    print()
    print("  EM uniquement:")
    print("    • _detect_requete_complexe_em() — num_type: boule|etoile (star detection multilang)")
    print("    • _detect_argent_em(msg, lang) — 6 langues + pool registry")
    print("    • _detect_country_em() — Phase GEO (9 pays × 6 langues)")
    print("    • _detect_out_of_range_em() — boule(1-50)/etoile(1-12)")
    print("    • Response pools multilang: get_insult_response(), get_oor_response(), etc.")
    print()
    print("  Gaps identifiés:")
    print("    • Loto argent: FR-only (_detect_argent), pas de pool multilang")
    print("    • Loto détecteurs: FR-only (pas de _detect_requete_complexe multilang)")
    print("    • Loto pipeline: pas de paramètre `lang` (FR uniquement)")
    print("    • EM star detection: corrigé v17 (multilang _star_kw)")
    print()

    return pct


if __name__ == "__main__":
    score = main()
