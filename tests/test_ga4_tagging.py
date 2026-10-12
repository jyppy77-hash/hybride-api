"""
Tests LOT GA4 (Release 1.6.054) — sessions GA4 orphelines « Unassigned ».

Contrôles statiques (pas d'infra de tests JS dans le repo) : le comportement réel est validé
dans GA4 DebugView après déploiement (plan de vérification de la livraison 1.6.054).

Couvre : A suppression session_end_lotoia, B marqueur appareil owner lotoia_internal,
C consent default depuis le choix stocké + page_view unique après acceptation, D file d'attente
avant config/page_view (C1 ordre baselineInit, C2 vidage sans envoi si gtag bloqué), E tampon
produit > 30 min jeté, F page_view bfcache, G rating-popup visible, H sponsor visible,
I cache-busters cohérents sur les pages servies, et la règle d'or /accueil (MD5 inchangés).
"""

import glob
import hashlib
import os
import re

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
_ANALYTICS_JS = os.path.join(_UI, "static", "analytics.js")
_RATING_JS = os.path.join(_UI, "static", "rating-popup.js")
_SP_POPUP_JS = os.path.join(_UI, "static", "sponsor-popup.js")
_SP75_JS = os.path.join(_UI, "static", "sponsor-popup75.js")
_SP75_EM_JS = os.path.join(_UI, "static", "sponsor-popup75-em.js")
_SP_POPUP_EM_JS = os.path.join(_UI, "static", "em", "sponsor-popup-em.js")

# Pages statiques LEGACY redirigées en 301 (main._UI_*_HTML_TO_CLEAN_URL) — jamais servies,
# volontairement NON modifiées par 1.6.054 (décision Jyppy 13/10) → exclues des contrôles.
_LEGACY_301 = [
    "ui/index.html",
    "ui/em/accueil-em.html",
    "ui/em/euromillions.html",
    "ui/em/faq-em.html",
    "ui/em/historique-em.html",
    "ui/em/news-em.html",
    "ui/em/simulateur-em.html",
    "ui/em/statistiques-em.html",
    "ui/en/euromillions/faq.html",
    "ui/en/euromillions/generator.html",
    "ui/en/euromillions/history.html",
    "ui/en/euromillions/home.html",
    "ui/en/euromillions/news.html",
    "ui/en/euromillions/simulator.html",
    "ui/en/euromillions/statistics.html",
]

# Cache-busters attendus (1.6.054) — une seule version partout sur les fichiers servis
_EXPECTED_VERSIONS = {
    "analytics.js": "4",
    "rating-popup.js": "10",
    "sponsor-popup.js": "11",
    "sponsor-popup75.js": "19",
    "sponsor-popup-em.js": "11",
    "sponsor-popup75-em.js": "14",
}

# Nombre minimal de références attendues (garde-fou contre un scan vide)
_EXPECTED_MIN_REFS = {
    "analytics.js": 21,
    "rating-popup.js": 19,
    "sponsor-popup.js": 2,
    "sponsor-popup75.js": 1,
    "sponsor-popup-em.js": 3,
    "sponsor-popup75-em.js": 2,
}

# /accueil — MD5 UTF-8 des balises complètes (title / meta description / 3 blocs JSON-LD) du
# TEMPLATE ui/accueil.html (HEAD 2fa2a84, avant 1.6.054). Règle d'or : ils ne bougent pas avec ce lot.
# Le JSON-LD n°0 est hashé avec ses marqueurs __RATING_VALUE__ / __RATING_COUNT__ : le rendu les
# remplace par les notes en base (routes/pages.py page_accueil) → MD5 rendu variable à chaque vote,
# contrôlé par script en rendu local, pas ici.
_ACCUEIL_TITLE_MD5 = "094f295af9f51122435e843b8b11578d"
_ACCUEIL_META_MD5 = "aec9d0400b333ea1b45b081afb6cd7cc"
_ACCUEIL_JSONLD_MD5 = [
    "19412361976aba529a7fff96682ae015",
    "14aea34a379c8eb9d47e2e0ddde8e953",
    "a322021daa041dab10550956622ed675",
]


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _rel(path: str) -> str:
    return os.path.relpath(path, _ROOT).replace(os.sep, "/")


def _served_files() -> list[str]:
    """Pages HTML servies + templates Jinja + config/routes Python (legacy 301 exclus)."""
    files = glob.glob(os.path.join(_UI, "*.html"))
    files += glob.glob(os.path.join(_UI, "templates", "**", "*.html"), recursive=True)
    files += glob.glob(os.path.join(_ROOT, "config", "*.py"))
    files += glob.glob(os.path.join(_ROOT, "routes", "*.py"))
    return sorted(f for f in files if _rel(f) not in _LEGACY_301)


def _body(src: str, start: str, end: str) -> str:
    """Extrait le texte entre deux marqueurs (corps de fonction approximatif)."""
    i = src.index(start)
    j = src.index(end, i + len(start))
    return src[i:j]


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


# ================================================================
# A — session_end_lotoia supprimé
# ================================================================

def test_ga4_session_end_event_absent_from_ui():
    hits = []
    for path in glob.glob(os.path.join(_UI, "**", "*"), recursive=True):
        if not os.path.isfile(path) or not path.endswith((".js", ".html", ".css", ".json")):
            continue
        if "session_end_lotoia" in _read(path):
            hits.append(_rel(path))
    assert hits == []


def test_ga4_session_tracking_removed_and_session_end_noop():
    src = _read(_ANALYTICS_JS)
    assert "setupSessionTracking" not in src
    assert "sessionEnd: function() {}" in src
    # Clé publique conservée (compat API) : ux = UXEvents
    assert "ux: UXEvents" in src


def test_ga4_pagehide_buffer_flush_kept():
    src = _read(_ANALYTICS_JS)
    assert "window.addEventListener('pagehide', safeFlush);" in src
    assert "window.addEventListener('beforeunload', safeFlush);" in src


# ================================================================
# B — marqueur d'appareil owner
# ================================================================

def test_ga4_internal_marker_read_before_gtag_load():
    src = _read(_ANALYTICS_JS)
    boot = _body(src, "function bootGtagImmediately()", "bootGtagImmediately();")
    assert "localStorage.setItem(INTERNAL_DEVICE_KEY, '1')" in boot
    i_guard = boot.index("window.__OWNER__ || window.__IS_AI_BOT__ || isInternalDevice()")
    i_datalayer = boot.index("window.dataLayer = window.dataLayer || []")
    i_script = boot.index("googletagmanager.com/gtag/js")
    assert i_guard < i_datalayer < i_script


def test_ga4_internal_marker_key_and_owner_set():
    src = _read(_ANALYTICS_JS)
    assert "const INTERNAL_DEVICE_KEY = 'lotoia_internal';" in src
    assert re.search(r"if \(window\.__OWNER__\) \{\s*try \{ localStorage\.setItem\(INTERNAL_DEVICE_KEY, '1'\);", src)


# ================================================================
# C — consentement initial depuis le choix stocké + page_view unique après acceptation
# ================================================================

def test_ga4_consent_default_from_stored_choice():
    src = _read(_ANALYTICS_JS)
    assert "state.consentAtBoot = readStoredAnalyticsConsent();" in src
    assert "'analytics_storage': state.consentAtBoot ? 'granted' : 'denied'," in src


def test_ga4_stored_consent_respects_expiry():
    src = _read(_ANALYTICS_JS)
    fn = _body(src, "function readStoredAnalyticsConsent()", "// ═══")
    assert "localStorage.getItem('lotoia_cookie_consent')" in fn
    assert "data.expires && new Date(data.expires) < new Date()" in fn
    has = _body(src, "function hasAnalyticsConsent()", "function onConsentChange")
    assert "return readStoredAnalyticsConsent();" in has


def test_ga4_single_page_view_on_mid_page_consent():
    src = _read(_ANALYTICS_JS)
    fn = _body(src, "function enableEnhanced()", "function initGA4")
    assert "!state.consentAtBoot && !state.consentPageViewSent && state.baselineReady" in fn
    assert fn.count("sendPageView(") == 1
    i_flag = fn.index("state.consentPageViewSent = true;")
    i_pv = fn.index("sendPageView('consent_granted');")
    assert i_flag < i_pv


# ================================================================
# D — file d'attente avant config + page_view (C1 ordre, C2 vidage sans envoi)
# ================================================================

def test_ga4_baseline_ready_precedes_queue_and_buffer_flush():
    """C1 : baselineReady = true AVANT processEventsQueue / flushProductBuffer (sinon jamais vidés)."""
    src = _read(_ANALYTICS_JS)
    fn = _body(src, "async function baselineInit()", "function enableEnhanced()")
    i_config = fn.index("gtag('config', CONFIG.GA4_ID")
    i_ready = fn.index("state.baselineReady = true;")
    i_pv = fn.index("sendPageView('baseline');")
    i_queue = fn.index("processEventsQueue();")
    i_buffer = fn.index("flushProductBuffer();")
    assert i_config < i_ready < i_pv < i_queue < i_buffer


def test_ga4_send_event_queued_until_baseline_ready():
    src = _read(_ANALYTICS_JS)
    fn = _body(src, "function sendGA4Event(", "function processEventsQueue()")
    i_blocked = fn.index("if (state.gtagLoadFailed)")
    i_queue = fn.index("if (!state.baselineReady || !window.gtag)")
    i_send = fn.index("gtag('event', eventName, enrichedParams)")
    assert i_blocked < i_queue < i_send
    assert "if (state.eventsQueue.length >= 50) state.eventsQueue.shift();" in fn


def test_ga4_queue_drained_without_send_when_gtag_blocked():
    """C2 (eventsQueue) : gtag bloqué → file vidée sans envoi."""
    src = _read(_ANALYTICS_JS)
    fn = _body(src, "function processEventsQueue()", "// ═══")
    assert re.search(r"if \(state\.gtagLoadFailed\) \{\s*state\.eventsQueue = \[\];\s*return;\s*\}", fn)
    assert fn.index("state.gtagLoadFailed") < fn.index("sendGA4Event(")


def test_ga4_product_buffer_drained_without_send_when_gtag_blocked():
    """C2 (tampon produit) : gtag bloqué → tampon vidé sans envoi, avant la garde baselineReady."""
    src = _read(_ANALYTICS_JS)
    fn = _body(src, "function flushProductBuffer()", "function normalizeEventName")
    assert re.search(r"if \(state\.gtagLoadFailed\) \{\s*state\.productBuffer = \[\];\s*return;\s*\}", fn)
    i_blocked = fn.index("if (state.gtagLoadFailed)")
    i_ready = fn.index("if (!state.baselineReady) return;")
    i_send = fn.index("sendProductEvent(")
    assert i_blocked < i_ready < i_send


# ================================================================
# E — tampon produit : events > 30 min jetés
# ================================================================

def test_ga4_product_buffer_drops_stale_events():
    src = _read(_ANALYTICS_JS)
    assert "const PRODUCT_EVENT_MAX_AGE_MS = 30 * 60 * 1000;" in src
    fn = _body(src, "function flushProductBuffer()", "function normalizeEventName")
    assert "events.filter(item => now - item.ts <= PRODUCT_EVENT_MAX_AGE_MS)" in fn
    assert "fresh.forEach(item => {" in fn
    # ts posé à la mise en tampon (champ existant)
    assert "state.productBuffer.push({ name, payload, ts: Date.now() });" in src


# ================================================================
# F — retour bfcache : page_view
# ================================================================

def test_ga4_pageshow_persisted_sends_page_view():
    src = _read(_ANALYTICS_JS)
    m = re.search(r"window\.addEventListener\('pageshow', function\(event\) \{(.*?)\n    \}\);", src, re.S)
    assert m, "listener pageshow absent"
    body = m.group(1)
    assert "if (!event.persisted) return;" in body
    assert "state.gtagLoadFailed" in body
    assert "isInternalDevice()" in body
    assert "!hasAnalyticsConsent()" in body
    assert "sendPageView('bfcache_restore');" in body


# ================================================================
# G — rating-popup : visible seulement
# ================================================================

def test_rating_popup_shown_only_when_visible():
    src = _read(_RATING_JS)
    assert "function whenVisible(fn)" in src
    assert "document.visibilityState === 'visible'" in src
    assert "onReady(function () { whenVisible(showBanner); });" in src
    assert "if (!hasAlreadyRated()) whenVisible(showBanner);" in src
    # Plus aucun appel direct de showBanner depuis les déclencheurs
    assert "onReady(showBanner)" not in src
    assert "if (!hasAlreadyRated()) showBanner();" not in src


# ================================================================
# H — sponsor : impressions page visible seulement
# ================================================================

@pytest.mark.parametrize("path,fn_name", [
    (_SP_POPUP_JS, "trackImpression"),
    (_SP75_JS, "trackImpression"),
    (_SP75_EM_JS, "trackImpressionEM"),
    (_SP_POPUP_EM_JS, "trackImpressionSimulateurEM"),
])
def test_sponsor_impression_guarded_by_visibility(path, fn_name):
    src = _read(path)
    pattern = (
        r"function " + fn_name + r"\(sponsorIds\) \{\s*// 1\.6\.054[^\n]*\n"
        r"\s*if \(document\.visibilityState !== 'visible'\) return;"
    )
    assert re.search(pattern, src), f"garde visibilityState absente en tête de {fn_name}"
    i_guard = src.index("if (document.visibilityState !== 'visible') return;")
    i_impr = src.index("sponsorImpression(")
    assert i_guard < i_impr


@pytest.mark.parametrize("path,helper", [
    (_SP75_JS, "runWhenVisible75"),
    (_SP75_EM_JS, "runWhenVisible75EM"),
])
@pytest.mark.parametrize("event_type", ["sponsor-result-shown", "sponsor-pdf-mention"])
def test_sponsor_meta75_result_tracking_deferred_until_visible(path, helper, event_type):
    src = _read(path)
    assert f"function {helper}(fn)" in src
    pattern = (
        helper + r"\(function\(\) \{\s*\n\s*fetch\('/api/sponsor/track'[^\n]*'" + event_type + r"'[^\n]*\n"
        r"\s*if \(typeof LotoIA_track === 'function'\) LotoIA_track\('" + event_type + r"'"
    )
    assert re.search(pattern, src), f"{event_type} non enveloppé par {helper}"
    # Une seule émission de chaque event (pas de doublon hors enveloppe)
    assert src.count(f"event_type: '{event_type}'") == 1


# ================================================================
# I — cache-busters cohérents (pages servies)
# ================================================================

@pytest.mark.parametrize("script,version", sorted(_EXPECTED_VERSIONS.items()))
def test_cache_buster_single_new_version(script, version):
    pat = re.compile(r"(?<![\w-])" + re.escape(script) + r"\?v=([0-9.]+)")
    found: dict[str, list[str]] = {}
    for path in _served_files():
        for v in pat.findall(_read(path)):
            found.setdefault(v, []).append(_rel(path))
    assert set(found) == {version}, f"{script} : versions trouvées {found}"
    assert len(found[version]) >= _EXPECTED_MIN_REFS[script]


def test_legacy_301_list_is_redirected():
    """Les fichiers exclus sont bien des legacy redirigés en 301 (jamais servis)."""
    main_src = _read(os.path.join(_ROOT, "main.py"))
    for rel in _LEGACY_301:
        assert os.path.isfile(os.path.join(_ROOT, rel)), rel
        assert f'"{os.path.basename(rel)}":' in main_src, f"{rel} absent des tables 301 de main.py"


def test_served_pages_load_analytics_once_without_inline_config():
    pages = [p for p in _served_files() if p.endswith(".html") and "analytics.js" in _read(p)]
    assert len(pages) >= 21
    for p in pages:
        src = _read(p)
        assert src.count("/ui/static/analytics.js?v=") == 1, _rel(p)
        assert "gtag('config'" not in src and 'gtag("config"' not in src, _rel(p)


# ================================================================
# Règle d'or /accueil — title / meta / JSON-LD inchangés
# ================================================================

def test_accueil_seo_head_md5_unchanged():
    src = _read(os.path.join(_UI, "accueil.html"))
    title = re.search(r"<title>.*?</title>", src, re.S).group(0)
    meta = re.search(r'<meta\s+name="description"[^>]*>', src).group(0)
    jsonld = re.findall(r'<script type="application/ld\+json">.*?</script>', src, re.S)
    assert _md5(title) == _ACCUEIL_TITLE_MD5
    assert _md5(meta) == _ACCUEIL_META_MD5
    assert [_md5(b) for b in jsonld] == _ACCUEIL_JSONLD_MD5
    # Seul le cache-buster analytics du head a changé
    assert '<script src="/ui/static/analytics.js?v=4" defer></script>' in src
