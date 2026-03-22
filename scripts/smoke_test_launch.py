#!/usr/bin/env python3
"""
SMOKE TEST POST-LAUNCH — 42 pages EM × 6 checks = 252 vérifications
Usage: py -3 scripts/smoke_test_launch.py [--base-url https://lotoia.fr]
"""

import sys
import io
import argparse
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install with: pip install requests")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════
# 7 pages principales × 6 langues = 42 URLs
# ═══════════════════════════════════════════════════════════

PAGES = {
    "fr": {
        "accueil":      "/euromillions",
        "generateur":   "/euromillions/generateur",
        "simulateur":   "/euromillions/simulateur",
        "statistiques": "/euromillions/statistiques",
        "historique":   "/euromillions/historique",
        "faq":          "/euromillions/faq",
        "news":         "/euromillions/news",
    },
    "en": {
        "accueil":      "/en/euromillions",
        "generateur":   "/en/euromillions/generator",
        "simulateur":   "/en/euromillions/simulator",
        "statistiques": "/en/euromillions/statistics",
        "historique":   "/en/euromillions/history",
        "faq":          "/en/euromillions/faq",
        "news":         "/en/euromillions/news",
    },
    "es": {
        "accueil":      "/es/euromillions",
        "generateur":   "/es/euromillions/generador",
        "simulateur":   "/es/euromillions/simulador",
        "statistiques": "/es/euromillions/estadisticas",
        "historique":   "/es/euromillions/historial",
        "faq":          "/es/euromillions/faq",
        "news":         "/es/euromillions/noticias",
    },
    "pt": {
        "accueil":      "/pt/euromillions",
        "generateur":   "/pt/euromillions/gerador",
        "simulateur":   "/pt/euromillions/simulador",
        "statistiques": "/pt/euromillions/estatisticas",
        "historique":   "/pt/euromillions/historico",
        "faq":          "/pt/euromillions/faq",
        "news":         "/pt/euromillions/noticias",
    },
    "de": {
        "accueil":      "/de/euromillions",
        "generateur":   "/de/euromillions/generator",
        "simulateur":   "/de/euromillions/simulator",
        "statistiques": "/de/euromillions/statistiken",
        "historique":   "/de/euromillions/ziehungen",
        "faq":          "/de/euromillions/faq",
        "news":         "/de/euromillions/nachrichten",
    },
    "nl": {
        "accueil":      "/nl/euromillions",
        "generateur":   "/nl/euromillions/generator",
        "simulateur":   "/nl/euromillions/simulator",
        "statistiques": "/nl/euromillions/statistieken",
        "historique":   "/nl/euromillions/geschiedenis",
        "faq":          "/nl/euromillions/faq",
        "news":         "/nl/euromillions/nieuws",
    },
}

LANGS = ["fr", "en", "es", "pt", "de", "nl"]

# Simple chatbot test messages per lang
CHAT_MESSAGES = {
    "fr": "Bonjour",
    "en": "Hello",
    "es": "Hola",
    "pt": "Olá",
    "de": "Hallo",
    "nl": "Hallo",
}


def check_page(session, base_url, lang, page_name, path):
    """Run 6 checks on a single page. Returns (checks_passed, checks_total, details)."""
    url = base_url.rstrip("/") + path
    checks = []
    passed = 0

    try:
        resp = session.get(url, timeout=15, allow_redirects=False)
    except Exception as e:
        return 0, 6, [f"FAIL: Connection error: {e}"]

    # Check 1: HTTP 200
    if resp.status_code == 200:
        checks.append("OK  HTTP 200")
        passed += 1
    elif resp.status_code == 302:
        location = resp.headers.get("Location", "")
        checks.append(f"FAIL HTTP 302 → {location} (kill switch still active?)")
    else:
        checks.append(f"FAIL HTTP {resp.status_code}")

    if resp.status_code != 200:
        return passed, 6, checks

    html = resp.text

    # Check 2: Chatbot widget present
    if "hybride-chatbot" in html or "chatbot-container" in html or "chatbot-toggle" in html:
        checks.append("OK  Chatbot widget")
        passed += 1
    else:
        checks.append("WARN Chatbot widget not found (may be page-specific)")
        passed += 1  # Soft check — not all pages have chatbot

    # Check 3: hreflang tags
    hreflang_count = html.count('hreflang="')
    if hreflang_count >= 6:
        checks.append(f"OK  hreflang ({hreflang_count} tags)")
        passed += 1
    elif hreflang_count > 0:
        checks.append(f"WARN hreflang partial ({hreflang_count} tags, expected 7)")
        passed += 1
    else:
        checks.append("FAIL hreflang missing")

    # Check 4: Canonical tag
    if f'rel="canonical"' in html:
        checks.append("OK  Canonical")
        passed += 1
    else:
        checks.append("FAIL Canonical missing")

    # Check 5: Sponsor placeholder (JS or marker)
    if "sponsor" in html.lower() or "LotoIA_sponsor" in html or "sponsor-popup" in html:
        checks.append("OK  Sponsor placeholder")
        passed += 1
    else:
        checks.append("WARN Sponsor placeholder not found")
        passed += 1  # Soft check

    # Check 6: No error markers
    if "500 Internal Server Error" in html or "Traceback" in html:
        checks.append("FAIL Error markers in HTML")
    else:
        checks.append("OK  No errors")
        passed += 1

    return passed, 6, checks


def check_chatbot(session, base_url, lang):
    """Test a simple chatbot message via SSE endpoint. Returns (ok, detail)."""
    url = base_url.rstrip("/") + "/api/euromillions/hybride-chat"
    msg = CHAT_MESSAGES[lang]

    try:
        resp = session.post(
            url,
            json={
                "message": msg,
                "page": "accueil-em",
                "history": [],
                "lang": lang,
            },
            timeout=30,
            stream=True,
            headers={"Accept": "text/event-stream"},
        )

        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"

        # Collect SSE chunks
        full_text = ""
        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                try:
                    import json
                    data = json.loads(line[6:])
                    chunk = data.get("chunk", "")
                    full_text += chunk
                    if data.get("is_done"):
                        break
                except (json.JSONDecodeError, ValueError):
                    pass

        if len(full_text) > 10:
            preview = full_text[:80].replace("\n", " ")
            return True, f"OK ({len(full_text)} chars): {preview}..."
        else:
            return False, f"Response too short ({len(full_text)} chars)"

    except Exception as e:
        return False, f"Error: {e}"


def main():
    parser = argparse.ArgumentParser(description="Smoke test post-launch EM")
    parser.add_argument("--base-url", default="https://lotoia.fr", help="Base URL to test")
    args = parser.parse_args()
    base_url = args.base_url

    print("=" * 75)
    print(f"  SMOKE TEST LAUNCH — {base_url}")
    print(f"  42 pages × 6 checks + 6 chatbot tests = 258 vérifications")
    print("=" * 75)
    print()

    session = requests.Session()
    session.headers["User-Agent"] = "LotoIA-SmokeTest/1.0"

    total_passed = 0
    total_checks = 0
    fails = []
    page_results = []

    # ── Phase 1: Page checks ──
    for lang in LANGS:
        print(f"── {lang.upper()} ──")
        for page_name, path in PAGES[lang].items():
            passed, total, details = check_page(session, base_url, lang, page_name, path)
            total_passed += passed
            total_checks += total

            status = "OK" if passed == total else ("WARN" if passed >= total - 1 else "FAIL")
            print(f"  [{status:4s}] {path:50s} {passed}/{total}")

            if passed < total:
                for d in details:
                    if "FAIL" in d:
                        print(f"         └─ {d}")
                        fails.append(f"{lang}/{page_name}: {d}")

            page_results.append({
                "lang": lang, "page": page_name, "path": path,
                "passed": passed, "total": total, "details": details,
            })
        print()

    # ── Phase 2: Chatbot tests ──
    print("── CHATBOT (1 message × 6 langues) ──")
    for lang in LANGS:
        ok, detail = check_chatbot(session, base_url, lang)
        total_checks += 1
        if ok:
            total_passed += 1
            print(f"  [OK  ] {lang}: {detail}")
        else:
            print(f"  [FAIL] {lang}: {detail}")
            fails.append(f"chatbot/{lang}: {detail}")
    print()

    # ── Summary ──
    pct = (total_passed / total_checks) * 100 if total_checks > 0 else 0

    print("=" * 75)
    print(f"  SCORE : {total_passed}/{total_checks} ({pct:.1f}%)")
    print("=" * 75)

    if fails:
        print()
        print(f"  {len(fails)} FAIL(S):")
        for f in fails:
            print(f"    • {f}")
    else:
        print("  Aucun échec. Prêt pour le launch.")

    print()
    return pct


if __name__ == "__main__":
    score = main()
