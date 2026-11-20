"""
Tests LOT 1.6.072 (A3) — phase B1 : GA4 en Consent Mode « de base ».

GA4 n'est ni chargé ni appelé, et window.gtag / window.dataLayer n'existent pas, tant que le visiteur
n'a pas accepté la mesure d'audience (choices.analytics === true : « Tout accepter » ou « Personnaliser »
avec la case cochée). Umami inchangé.

Contrôles statiques sur le source (pas d'infra de tests JS dans le dépôt) ; le comportement réel est
validé par le smoke D5 (profil neuf, 4G, onglet Réseau).

Cas (rapport de phase A §3.5) : 1 aucun chargement hors loadGA4IfConsented, 2 exclusion avant
consentement, 3 acceptation → loadGA4IfConsented, 4 consent default granted / ad_* denied, 5 page_view
unique par chemin, 6 retrait, 7 purgeGaCookies, 8 purge au boot, 9 debug owner, 10 events avant
consentement jetés, 11 code mort supprimé, 13 bouton « Effacer mes données » ; plus cookie_expires,
aucune nouvelle télémétrie, ré-acceptation dans la même page.

Phase B2, bloc a (bandeau cookies) : 12 cache-buster cookie-consent.js?v=8 (pages servies) / legacy
intacts, 14 partie bandeau (3 libellés de CONSENT_LABELS × 6 langues). Le cas 14 côté pages HTML
viendra avec les blocs suivants.

Phase B2, bloc b (pages cookies Loto + EM 6 langues) : 14 partie pages cookies — anciennes affirmations
absentes, nouveaux titres 2.1-2.4, Umami, GA4 (_ga_YYJ5LD1ZT3), date du 16/11/2026, contact@lotoia.fr,
lien vers la politique de confidentialité, exemption CNIL, zéro texte FR dans les 5 autres langues.
"""

import html
import json
import os
import re
from unittest.mock import MagicMock

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
_ANALYTICS_JS = os.path.join(_UI, "static", "analytics.js")
_COOKIES_LOTO = os.path.join(_UI, "politique-cookies.html")
_COOKIES_EM = os.path.join(_UI, "templates", "em", "cookies.html")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _body(src: str, start: str, end: str) -> str:
    """Texte entre deux marqueurs (corps de fonction approximatif)."""
    i = src.index(start)
    j = src.index(end, i + len(start))
    return src[i:j]


def _code(src: str) -> str:
    """Source sans commentaires (/* */ et //) pour les recherches de motifs de code."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|(?<=[;{}),])\s*//[^\n]*", "", src)


@pytest.fixture(scope="module")
def src() -> str:
    return _read(_ANALYTICS_JS)


@pytest.fixture(scope="module")
def load_fn(src) -> str:
    return _body(src, "function loadGA4IfConsented(origin)", "function reenableGA4()")


# ================================================================
# 1 — aucun chargement ni appel gtag hors de loadGA4IfConsented
# ================================================================

def test_lot_1_6_072_gtag_created_only_in_load_function(src, load_fn):
    code = _code(src)
    assert code.count("googletagmanager.com/gtag/js") == 1
    assert code.count("window.gtag = function") == 1
    assert code.count("window.dataLayer = window.dataLayer || []") == 1
    for needle in ("googletagmanager.com/gtag/js", "window.gtag = function",
                   "window.dataLayer = window.dataLayer || []"):
        assert needle in load_fn, needle


def test_lot_1_6_072_no_unconditional_boot(src):
    code = _code(src)
    assert "bootGtagImmediately" not in code
    # Seul appel au démarrage : loadGA4IfConsented('boot') (gardé par exclusion + consentement) ;
    # l'autre occurrence est l'API legacy initialize() (return loadGA4IfConsented('boot');)
    assert len(re.findall(r"(?m)^\s*loadGA4IfConsented\('boot'\);", code)) == 1
    assert "return loadGA4IfConsented('boot');" in _body(src, "function initialize()", "function autoInit()")
    assert "baselineInit();" in _body(src, "function loadGA4IfConsented(origin)", "function reenableGA4()")
    # baselineInit n'est appelé nulle part ailleurs
    assert len(re.findall(r"\bbaselineInit\(\)", code)) == 2  # appel + déclaration
    assert "async function baselineInit()" in code


def test_lot_1_6_072_baseline_requires_consented_load(src):
    base = _body(src, "async function baselineInit()", "function sendGA4Event(")
    assert "if (!state.gtagBooted || !window.gtag)" in base


# ================================================================
# 2 — exclusion owner / bot IA / appareil marqué AVANT le consentement
# ================================================================

def test_lot_1_6_072_is_excluded_definition(src):
    fn = _body(src, "function isExcluded()", "function isDebugAllowed()")
    assert "window.__OWNER__ || window.__IS_AI_BOT__ || isInternalDevice()" in fn


def test_lot_1_6_072_exclusion_before_consent_read(load_fn):
    i_excl = load_fn.index("if (isExcluded())")
    i_consent = load_fn.index("readStoredAnalyticsConsent()")
    i_has = load_fn.index("hasAnalyticsConsent()")
    i_booted = load_fn.index("if (state.gtagBooted)")
    assert i_excl < i_consent and i_excl < i_has and i_excl < i_booted


def test_lot_1_6_072_owner_marker_kept_verbatim(src):
    assert "const INTERNAL_DEVICE_KEY = 'lotoia_internal';" in src
    assert re.search(
        r"if \(window\.__OWNER__\) \{\s*try \{ localStorage\.setItem\(INTERNAL_DEVICE_KEY, '1'\); \} "
        r"catch \(e\) \{ /\* ignore \*/ \}\s*\}", src)


# ================================================================
# 3 — acceptation (Tout accepter / Personnaliser coché) → loadGA4IfConsented
# ================================================================

def test_lot_1_6_072_consent_change_accept_goes_through_load(src):
    fn = _body(src, "function onConsentChange(event)", "function setupConsentListeners()")
    i_accept = fn.index("if (choices.analytics === true)")
    i_load = fn.index("loadGA4IfConsented('consent');")
    assert i_accept < i_load
    assert "enableEnhanced" not in fn
    listen = _body(src, "function setupConsentListeners()", "function initialize()")
    assert "document.addEventListener('cookieConsentUpdated', onConsentChange);" in listen
    auto = _body(src, "function autoInit()", "// ═══")
    assert "setupConsentListeners();" in auto


# ================================================================
# 4 — consent default : analytics granted (chargé = accepté), ad_* toujours denied
# ================================================================

def test_lot_1_6_072_consent_default_granted_ads_denied(load_fn):
    m = re.search(r"gtag\('consent', 'default', \{(.*?)\}\);", load_fn, re.S)
    assert m
    block = m.group(1)
    assert "'analytics_storage': 'granted'" in block
    assert "denied'" not in block.split("'analytics_storage'")[1].split(",")[0]
    for key in ("ad_storage", "ad_user_data", "ad_personalization"):
        assert f"'{key}': 'denied'" in block, key


# ================================================================
# 5 — un seul page_view par chemin
# ================================================================

def test_lot_1_6_072_single_page_view_per_path(src, load_fn):
    assert "state.pageViewCategory = origin === 'boot' ? 'baseline' : 'consent_granted';" in load_fn
    once = _body(src, "function sendPageViewOnce()", "function sendConsentGrantedEvent()")
    assert "if (state.pageViewSent) return;" in once
    code = _code(src)
    # sendPageView n'est appelé que par sendPageViewOnce et le retour bfcache
    calls = re.findall(r"\bsendPageView\(([^)]*)\)", code)
    assert sorted(calls) == sorted(["category", "state.pageViewCategory", "'bfcache_restore'"]), calls


# ================================================================
# 6 — retrait : denied + ga-disable + purge ; flag page_view réarmé
# ================================================================

def test_lot_1_6_072_withdraw(src):
    assert "const GA_DISABLE_KEY = 'ga-disable-' + CONFIG.GA4_ID;" in src
    assert "GA4_ID: 'G-YYJ5LD1ZT3'," in src
    dis = _body(src, "function disableGA4()", "// ═══")
    m = re.search(r"gtag\('consent', 'update', \{(.*?)\}\);", dis, re.S)
    assert m
    for key in ("analytics_storage", "ad_storage", "ad_user_data", "ad_personalization"):
        assert f"'{key}': 'denied'" in m.group(1), key
    assert "window[GA_DISABLE_KEY] = true;" in dis
    assert "state.pageViewSent = false;" in dis
    assert "state.eventsQueue = [];" in dis and "state.productBuffer = [];" in dis
    fn = _body(src, "function onConsentChange(event)", "function setupConsentListeners()")
    refuse = fn[fn.index("if (choices.analytics === false)"):]
    assert refuse.index("disableGA4();") < refuse.index("purgeGaCookies();")


# ================================================================
# 7 — purgeGaCookies : _ga / _ga_*, 3 variantes de domaine, relecture
# ================================================================

def test_lot_1_6_072_purge_cookie_domains_and_names(src):
    assert "const GA_COOKIE_NAME_RE = /^_ga(_[A-Za-z0-9]+)?$/;" in src
    assert "const GA_COOKIE_DOMAINS = ['; domain=.lotoia.fr', '; domain=lotoia.fr', ''];" in src
    fn = _body(src, "function purgeGaCookies()", "// ═══")
    assert "document.cookie = name + '=; Max-Age=0; path=/' + domain;" in fn
    i_write = fn.index("Max-Age=0")
    i_reread = fn.index("const left = listGaCookies();")
    assert i_write < i_reread


def test_lot_1_6_072_purge_regex_matches_expected_names():
    pat = re.compile(r"^_ga(_[A-Za-z0-9]+)?$")
    assert pat.match("_ga") and pat.match("_ga_YYJ5LD1ZT3")
    assert not pat.match("_gat") and not pat.match("_gid") and not pat.match("lotoia_ga")


def test_lot_1_6_072_purge_failure_no_telemetry(src):
    fn = _body(src, "function purgeGaCookies()", "// ═══")
    assert "getDebugLevel() >= 1" in fn
    assert fn.index("getDebugLevel() >= 1") < fn.index("console.warn(")
    for forbidden in ("LotoIA_track", "fetch(", "sendBeacon", "gtag(", "umami", "sendGA4Event"):
        assert forbidden not in fn, forbidden
    assert "ga_purge_failed" not in src


# ================================================================
# 8 — purge au boot si consentement négatif / expiré / absent et _ga* présent
# ================================================================

def test_lot_1_6_072_boot_purge_before_load(src):
    i_purge = src.index("if (!readStoredAnalyticsConsent() && listGaCookies().length > 0) {")
    i_boot = src.index("loadGA4IfConsented('boot');")
    assert i_purge < i_boot
    fn = _body(src, "function readStoredAnalyticsConsent()", "// ═══")
    assert "data.expires && new Date(data.expires) < new Date()" in fn
    assert "data.choices.analytics === true" in fn


# ================================================================
# 9 — debug_ga4 réservé à l'owner
# ================================================================

def test_lot_1_6_072_debug_owner_only(src):
    allowed = _body(src, "function isDebugAllowed()", "function readStoredAnalyticsConsent()")
    assert "window.__OWNER__ || isInternalDevice()" in allowed
    dbg = _body(src, "function getDebugLevel()", "function log(")
    assert dbg.index("if (!isDebugAllowed()) return 0;") < dbg.index("localStorage.getItem('debug_ga4')")
    setdbg = _body(src, "setDebug: function(level) {", "isInitialized:")
    assert setdbg.index("if (!isDebugAllowed()) return;") < setdbg.index("localStorage.setItem('debug_ga4'")
    # Plus aucune lecture directe de debug_ga4 hors getDebugLevel / setDebug
    assert _code(src).count("'debug_ga4'") == 2


# ================================================================
# 10 — events avant consentement jetés (Q8), ni file ni tampon
# ================================================================

def test_lot_1_6_072_events_dropped_before_consent(src):
    send = _body(src, "function sendGA4Event(", "function processEventsQueue()")
    i_guard = send.index("if (!state.gtagBooted || !state.isEnhanced) {")
    i_queue = send.index("state.eventsQueue.push(")
    assert i_guard < i_queue
    buf = _body(src, "function bufferProductEvent(name, payload)", "const ProductEngine")
    i_guard = buf.index("if (!state.gtagBooted || !state.isEnhanced) {")
    i_push = buf.index("state.productBuffer.push(")
    assert i_guard < i_push
    track = _body(src, "track: function(eventName, params = {}) {\n            // Normaliser",
                  "flush: function()")
    assert "if (state.isEnhanced && state.baselineReady) {" in track


# ================================================================
# 11 — code mort supprimé, version
# ================================================================

def test_lot_1_6_072_dead_code_removed(src):
    code = _code(src)
    for name in ("loadGtagScript", "initDataLayer", "initGA4", "enableEnhanced",
                 "detectCookieConsentBlocked", "cookieConsentBlocked", "consentAtBoot"):
        assert name not in code, name
    assert "baselineInit: baselineInit" not in code
    assert "version: '2.6.0'," in src
    assert "LOTOIA ANALYTICS MODULE v2.6.0" in src
    assert "AU BOOT (indépendant consent)" not in src


# ================================================================
# 13 — bouton « Effacer mes données LotoIA » : purge _ga*
# ================================================================

def test_lot_1_6_072_public_api_exposes_purge(src):
    api = _body(src, "const PublicAPI = {", "window.LotoIAAnalytics = PublicAPI;")
    assert "purgeGaCookies: purgeGaCookies," in api


@pytest.mark.parametrize("path", [_COOKIES_LOTO, _COOKIES_EM])
def test_lot_1_6_072_clear_data_button_purges_ga(path):
    page = _read(path)
    fn = page[page.index("getElementById('clear-lotoia-data')"):]
    fn = fn[:fn.index("</script>")]
    guard = ("if (window.LotoIAAnalytics && typeof window.LotoIAAnalytics.purgeGaCookies === 'function') {")
    assert guard in fn
    assert fn.index("localStorage.removeItem('lotoia_cookie_consent');") < fn.index(guard)
    assert fn.index("window.LotoIAAnalytics.purgeGaCookies();") < fn.index("location.reload();")


# ================================================================
# Q10 — durée des cookies _ga = 395 jours
# ================================================================

def test_lot_1_6_072_cookie_expires_395_days(src):
    base = _body(src, "async function baselineInit()", "function sendGA4Event(")
    m = re.search(r"gtag\('config', CONFIG\.GA4_ID, \{(.*?)\n            \}\);", base, re.S)
    assert m
    assert "'cookie_expires': 34128000," in m.group(1)
    assert 34128000 == 395 * 24 * 3600


# ================================================================
# Ré-acceptation dans la même page (avis Muse)
# ================================================================

def test_lot_1_6_072_reaccept_same_page(src, load_fn):
    # loadGA4IfConsented : déjà chargé + retiré → reenableGA4, avant toute (ré)injection
    i_booted = load_fn.index("if (state.gtagBooted) {")
    i_reenable = load_fn.index("reenableGA4();")
    i_inject = load_fn.index("document.createElement('script')")
    assert i_booted < i_reenable < i_inject
    re_fn = _body(src, "function reenableGA4()", "function disableGA4()")
    assert "window[GA_DISABLE_KEY] = false;" in re_fn
    m = re.search(r"gtag\('consent', 'update', \{(.*?)\}\);", re_fn, re.S)
    assert m and "'analytics_storage': 'granted'" in m.group(1)
    for key in ("ad_storage", "ad_user_data", "ad_personalization"):
        assert f"'{key}': 'denied'" in m.group(1), key
    assert "createElement" not in re_fn and "googletagmanager" not in re_fn
    assert "state.pageViewCategory = 'consent_granted';" in re_fn
    assert "sendPageViewOnce();" in re_fn


# ================================================================
# B1 bis — retrait respecté au retour bfcache et entre onglets
# ================================================================

def test_lot_1_6_072_resync_consent_from_storage(src):
    fn = _body(src, "function resyncConsentFromStorage()", "// ═══")
    cond = "if (!isExcluded() && state.gtagBooted && state.isEnhanced && !readStoredAnalyticsConsent()) {"
    assert cond in fn
    assert "hasAnalyticsConsent" not in fn and "CookieConsent" not in _code(fn)
    i_cond = fn.index(cond)
    assert i_cond < fn.index("disableGA4();") < fn.index("purgeGaCookies();") < fn.index("return true;")
    assert "loadGA4IfConsented" not in fn


def test_lot_1_6_072_pageshow_resyncs_before_page_view(src):
    m = re.search(r"window\.addEventListener\('pageshow', function\(event\) \{(.*?)\n    \}\);", src, re.S)
    assert m
    body = m.group(1)
    assert "if (resyncConsentFromStorage()) return;" in body
    i_excl = body.index("if (isExcluded()) return;")
    i_resync = body.index("resyncConsentFromStorage()")
    i_pv = body.index("sendPageView('bfcache_restore');")
    assert i_excl < i_resync < i_pv
    assert body.index("!readStoredAnalyticsConsent()") < i_pv
    assert "hasAnalyticsConsent" not in body


def test_lot_1_6_072_storage_listener_propagates_withdrawal_only(src):
    m = re.search(r"window\.addEventListener\('storage', function\(event\) \{(.*?)\n    \}\);", src, re.S)
    assert m
    body = m.group(1)
    assert "event.key !== 'lotoia_cookie_consent' && event.key !== null" in body
    assert "resyncConsentFromStorage();" in body
    assert "loadGA4IfConsented" not in body
    assert body.index("event.key") < body.index("resyncConsentFromStorage();")
    assert _code(src).count("window.addEventListener('storage'") == 1


# ================================================================
# Umami inchangé (hors analytics.js)
# ================================================================

def test_lot_1_6_072_umami_untouched(src):
    assert "umami" not in _code(src).lower()
    base = _read(os.path.join(_UI, "templates", "em", "_base.html"))
    assert ('<script>function umamiBeforeSend(type,payload){if(window.__OWNER__||window.__IS_AI_BOT__)'
            'return false;return payload;}</script>') in base


# ================================================================
# B2 bloc a — 12 : cache-buster cookie-consent.js?v=8 (21 fichiers servis), legacy intacts
# ================================================================

_COOKIE_CONSENT_JS = os.path.join(_UI, "static", "cookie-consent.js")

_SERVED_WITH_CONSENT = [
    "404.html", "a-propos.html", "accueil.html", "disclaimer.html", "faq.html", "historique.html",
    "hybride.html", "loto-ia.html", "loto.html", "mentions-legales.html", "methodologie.html",
    "moteur.html", "news.html", "numeros-les-plus-sortis.html", "paires.html",
    "politique-confidentialite.html", "politique-cookies.html", "simulateur.html", "statistiques.html",
    os.path.join("templates", "em", "_base.html"), os.path.join("templates", "launcher.html"),
]

# Legacy non servis (redirigés en 301) : volontairement non modifiés, restent en ?v=7
_LEGACY_NOT_SERVED = [
    "index.html",
    os.path.join("em", "accueil-em.html"), os.path.join("em", "euromillions.html"),
    os.path.join("em", "faq-em.html"), os.path.join("em", "historique-em.html"),
    os.path.join("em", "news-em.html"), os.path.join("em", "simulateur-em.html"),
    os.path.join("em", "statistiques-em.html"),
    os.path.join("en", "euromillions", "faq.html"), os.path.join("en", "euromillions", "generator.html"),
    os.path.join("en", "euromillions", "history.html"), os.path.join("en", "euromillions", "home.html"),
    os.path.join("en", "euromillions", "news.html"), os.path.join("en", "euromillions", "simulator.html"),
    os.path.join("en", "euromillions", "statistics.html"),
]


@pytest.mark.parametrize("rel", _SERVED_WITH_CONSENT)
def test_lot_1_6_072_cookie_consent_v8_once_per_served_file(rel):
    page = _read(os.path.join(_UI, rel))
    assert page.count("cookie-consent.js?v=8") == 1, rel
    assert "cookie-consent.js?v=7" not in page, rel


def test_lot_1_6_072_cookie_consent_v8_total():
    total = sum(_read(os.path.join(_UI, rel)).count("cookie-consent.js?v=8") for rel in _SERVED_WITH_CONSENT)
    assert len(_SERVED_WITH_CONSENT) == 21
    assert total >= 21


@pytest.mark.parametrize("rel", _LEGACY_NOT_SERVED)
def test_lot_1_6_072_cookie_consent_legacy_untouched(rel):
    page = _read(os.path.join(_UI, rel))
    assert page.count("cookie-consent.js?v=7") == 1, rel
    assert "cookie-consent.js?v=8" not in page, rel


# ================================================================
# B2 bloc a — 14 (partie bandeau) : CONSENT_LABELS × 6 langues
# ================================================================

_LANGS = ("fr", "en", "es", "pt", "de", "nl")
_BLOC_A_KEYS = ("banner_text", "cat_analytics_desc", "cat_advertising_desc")

# Anciennes valeurs, relevées telles quelles dans cookie-consent.js avant B2 (MD5 LF 0c8fe0c0…)
_OLD_LABELS = {
    "fr": (
        "LotoIA.fr utilise des technologies de stockage local pour améliorer votre expérience. "
        "Ces données restent sur votre appareil et ne sont pas partagées avec des tiers.",
        "Ces cookies nous permettent de mesurer l'audience du site et d'améliorer nos services.",
        "Ces cookies permettent d'afficher des publicités personnalisées et de mesurer leur efficacité.",
    ),
    "en": (
        "LotoIA.fr uses local storage technologies to improve your experience. "
        "This data stays on your device and is not shared with third parties.",
        "These cookies allow us to measure website traffic and improve our services.",
        "These cookies enable personalised advertising and measure its effectiveness.",
    ),
    "es": (
        "LotoIA.fr utiliza tecnologías de almacenamiento local para mejorar su experiencia. "
        "Estos datos permanecen en su dispositivo y no se comparten con terceros.",
        "Estas cookies nos permiten medir el tráfico del sitio y mejorar nuestros servicios.",
        "Estas cookies permiten mostrar publicidad personalizada y medir su eficacia.",
    ),
    "pt": (
        "O LotoIA.fr utiliza tecnologias de armazenamento local para melhorar a sua experiência. "
        "Estes dados permanecem no seu dispositivo e não são partilhados com terceiros.",
        "Estes cookies permitem-nos medir o tráfego do site e melhorar os nossos serviços.",
        "Estes cookies permitem apresentar publicidade personalizada e medir a sua eficácia.",
    ),
    "de": (
        "LotoIA.fr verwendet lokale Speichertechnologien, um Ihre Erfahrung zu verbessern. "
        "Diese Daten verbleiben auf Ihrem Gerät und werden nicht an Dritte weitergegeben.",
        "Diese Cookies ermöglichen es uns, den Datenverkehr der Website zu messen und unsere Dienste "
        "zu verbessern.",
        "Diese Cookies ermöglichen personalisierte Werbung und die Messung ihrer Wirksamkeit.",
    ),
    "nl": (
        "LotoIA.fr gebruikt lokale opslagtechnologieën om uw ervaring te verbeteren. "
        "Deze gegevens blijven op uw apparaat en worden niet gedeeld met derden.",
        "Deze cookies stellen ons in staat het websiteverkeer te meten en onze diensten te verbeteren.",
        "Deze cookies maken gepersonaliseerde reclame mogelijk en meten de doeltreffendheid ervan.",
    ),
}

_LABEL_RE = re.compile(r"""^\s*(\w+):\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"),?\s*$""", re.M)


def _consent_labels() -> dict[str, dict[str, str]]:
    """CONSENT_LABELS de cookie-consent.js → {langue: {clé: valeur}} (valeurs sans échappement)."""
    src = _read(_COOKIE_CONSENT_JS)
    block = _body(src, "const CONSENT_LABELS = {", "\n    };")
    out: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"(?m)^        (\w\w): \{\n(.*?)\n        \}", block, re.S):
        out[m.group(1)] = {k: (a if a else b) for k, a, b in _LABEL_RE.findall(m.group(2))}
    return out


@pytest.fixture(scope="module")
def labels() -> dict[str, dict[str, str]]:
    return _consent_labels()


def test_lot_1_6_072_consent_labels_parsed_six_langs(labels):
    assert tuple(labels) == _LANGS
    # parité : mêmes clés dans les 6 langues
    ref = set(labels["fr"])
    assert len(ref) >= 18
    for lang in _LANGS:
        assert set(labels[lang]) == ref, lang


def test_lot_1_6_072_bloc_a_keys_present_18(labels):
    count = 0
    for lang in _LANGS:
        for key in _BLOC_A_KEYS:
            assert labels[lang].get(key, "").strip(), (lang, key)
            count += 1
    assert count == 18


@pytest.mark.parametrize("lang", _LANGS)
def test_lot_1_6_072_old_banner_labels_absent(lang, labels):
    src = _read(_COOKIE_CONSENT_JS)
    for key, old in zip(_BLOC_A_KEYS, _OLD_LABELS[lang]):
        assert old not in src, (lang, key)
        assert labels[lang][key] != old, (lang, key)


@pytest.mark.parametrize("lang", _LANGS)
def test_lot_1_6_072_banner_text_names_ga_and_umami(lang, labels):
    text = labels[lang]["banner_text"]
    assert "Google Analytics" in text, lang
    assert "Umami" in text, lang


@pytest.mark.parametrize("lang", _LANGS)
def test_lot_1_6_072_analytics_desc_ga_13_14(lang, labels):
    text = labels[lang]["cat_analytics_desc"]
    assert "Google Analytics" in text, lang
    assert re.search(r"\b13\b", text), lang
    assert re.search(r"\b14\b", text), lang


def test_lot_1_6_072_fr_banner_d5_sentence(labels):
    assert "Google Analytics n'est activé que si vous l'acceptez" in labels["fr"]["banner_text"]


# ================================================================
# B2 bloc b — 14 (pages cookies) : politique-cookies.html (Loto FR) + em/cookies.html (6 langues)
# ================================================================

_EM_COOKIES = os.path.join(_UI, "templates", "em", "cookies.html")

# Anciennes valeurs, relevées telles quelles dans les fichiers AVANT B2b (MD5 LF 5e568725… / 508b363f…)
_OLD_COOKIE_PAGE_LOTO = (
    # highlight
    ("<strong>Bonne nouvelle :</strong> LotoIA.fr n'utilise PAS de cookies HTTP traditionnels. Nous "
     'utilisons uniquement des technologies de stockage local (sessionStorage et localStorage) qui restent '
     'dans votre navigateur et ne sont pas transmises à des serveurs tiers.'),
    # cell_analytics_1
    "<em>Aucun cookie d'analyse tiers n'est actuellement utilisé.</em><br>",
    # cell_analytics_2
    "LotoIA.fr réalise des mesures d'audience via des logs serveur internes uniquement.",
    # bullet_3_2
    "<li>Cookies de mesure d'audience respectant les conditions de la CNIL</li>",
    # rgpd
    'rgpd@lotoia.fr',
    # date
    'Dernière mise à jour : 23 janvier 2026',
    # confirm
    'Voulez-vous vraiment effacer toutes vos données LotoIA ?',
    # alert
    'Toutes vos données LotoIA ont été effacées.',
)

_OLD_COOKIE_PAGE_EM = {
    "fr": (
        # highlight
        ("<strong>Bonne nouvelle :</strong> LotoIA.fr n'utilise PAS de cookies HTTP traditionnels. Nous "
         'utilisons uniquement des technologies de stockage local (sessionStorage et localStorage) qui '
         'restent dans votre navigateur et ne sont pas transmises à des serveurs tiers.'),
        # cell_analytics_1
        "<em>Aucun cookie d'analyse tiers n'est actuellement utilisé.</em><br>",
        # cell_analytics_2
        "LotoIA.fr réalise des mesures d'audience via des logs serveur internes uniquement.",
        # bullet_3_2
        "<li>Cookies de mesure d'audience respectant les conditions de la CNIL</li>",
        # date
        'Dernière mise à jour : 1 mars 2026',
        # confirm
        'Voulez-vous vraiment effacer toutes vos données LotoIA ?',
    ),
    "en": (
        # highlight
        ('<strong>Good news:</strong> LotoIA.fr does NOT use traditional HTTP cookies. We only use local '
         'storage technologies (sessionStorage and localStorage) that remain in your browser and are not '
         'transmitted to third-party servers.'),
        # cell_analytics_1
        '<em>No third-party analytics cookies are currently used.</em><br>',
        # cell_analytics_2
        'LotoIA.fr performs audience measurement through internal server logs only.',
        # bullet_3_2
        '<li>Audience measurement cookies meeting GDPR conditions</li>',
        # date
        'Last updated: 1 March 2026',
        # confirm
        'Do you really want to delete all your LotoIA data?',
    ),
    "es": (
        # highlight
        ('<strong>Buenas noticias:</strong> LotoIA.fr NO utiliza cookies HTTP tradicionales. Solo '
         'utilizamos tecnologias de almacenamiento local (sessionStorage y localStorage) que permanecen en '
         'su navegador y no se transmiten a servidores de terceros.'),
        # cell_analytics_1
        '<em>Actualmente no se utiliza ninguna cookie de analisis de terceros.</em><br>',
        # cell_analytics_2
        'LotoIA.fr realiza mediciones de audiencia unicamente a traves de registros internos del servidor.',
        # bullet_3_2
        '<li>Cookies de medicion de audiencia que cumplan las condiciones del RGPD</li>',
        # date
        'Ultima actualizacion: 1 de marzo de 2026',
        # confirm
        'Realmente desea eliminar todos sus datos de LotoIA?',
    ),
    "pt": (
        # highlight
        ('<strong>Boas noticias:</strong> O LotoIA.fr NAO utiliza cookies HTTP tradicionais. Utilizamos '
         'apenas tecnologias de armazenamento local (sessionStorage e localStorage) que permanecem no teu '
         'navegador e nao sao transmitidas a servidores de terceiros.'),
        # cell_analytics_1
        '<em>Atualmente nao e utilizado nenhum cookie de analise de terceiros.</em><br>',
        # cell_analytics_2
        'O LotoIA.fr realiza medicoes de audiencia unicamente atraves de registos internos do servidor.',
        # bullet_3_2
        '<li>Cookies de medicao de audiencia que cumpram as condicoes do RGPD</li>',
        # date
        'Ultima atualizacao: 1 de marco de 2026',
        # confirm
        'Queres mesmo eliminar todos os teus dados LotoIA?',
    ),
    "de": (
        # highlight
        ('<strong>Gute Nachricht:</strong> LotoIA.fr verwendet KEINE traditionellen HTTP-Cookies. Wir '
         'nutzen ausschliesslich lokale Speichertechnologien (sessionStorage und localStorage), die in '
         'Ihrem Browser verbleiben und nicht an Drittanbieter-Server uebermittelt werden.'),
        # cell_analytics_1
        '<em>Derzeit werden keine Analyse-Cookies von Drittanbietern verwendet.</em><br>',
        # cell_analytics_2
        'LotoIA.fr fuehrt Reichweitenmessungen ausschliesslich ueber interne Server-Protokolle durch.',
        # bullet_3_2
        '<li>Cookies zur Reichweitenmessung, die den DSGVO-Bedingungen entsprechen</li>',
        # date
        'Letzte Aktualisierung: 1. Maerz 2026',
        # confirm
        'Moechten Sie wirklich alle Ihre LotoIA-Daten loeschen?',
    ),
    "nl": (
        # highlight
        ('<strong>Goed nieuws:</strong> LotoIA.fr gebruikt GEEN traditionele HTTP-cookies. Wij gebruiken '
         'uitsluitend lokale opslagtechnologieen (sessionStorage en localStorage) die in uw browser blijven '
         'en niet worden doorgestuurd naar servers van derden.'),
        # cell_analytics_1
        '<em>Er worden momenteel geen analysecookies van derden gebruikt.</em><br>',
        # cell_analytics_2
        'LotoIA.fr voert publieksmetingen uitsluitend uit via interne serverlogboeken.',
        # bullet_3_2
        '<li>Cookies voor publieksmeting die voldoen aan de AVG-voorwaarden</li>',
        # date
        'Laatst bijgewerkt: 1 maart 2026',
        # confirm
        'Wilt u echt al uw LotoIA-gegevens verwijderen?',
    ),
}

# Nouveaux textes attendus : date, titres 2.1 à 2.4, mention de l'exemption CNIL
_NEW_COOKIE_PAGE = {
    "fr": ("Dernière mise à jour : 16 novembre 2026",
           ("2.1 Stockage nécessaire au fonctionnement du site",
            "2.2 Mesure d'audience sans cookie (Umami)",
            "2.3 Cookies de mesure d'audience Google Analytics (optionnels)",
            "2.4 Cookies publicitaires (optionnels)"),
           "(exemption CNIL)"),
    "en": ("Last updated: 16 November 2026",
           ("2.1 Storage necessary for the site to work",
            "2.2 Cookie-free audience measurement (Umami)",
            "2.3 Google Analytics audience measurement cookies (optional)",
            "2.4 Advertising cookies (optional)"),
           "(CNIL exemption)"),
    "es": ("Última actualización: 16 de noviembre de 2026",
           ("2.1 Almacenamiento necesario para el funcionamiento del sitio",
            "2.2 Medición de audiencia sin cookies (Umami)",
            "2.3 Cookies de medición de audiencia de Google Analytics (opcionales)",
            "2.4 Cookies publicitarias (opcionales)"),
           "(exención CNIL)"),
    "pt": ("Última atualização: 16 de novembro de 2026",
           ("2.1 Armazenamento necessário ao funcionamento do sítio",
            "2.2 Medição de audiência sem cookies (Umami)",
            "2.3 Cookies de medição de audiência do Google Analytics (opcionais)",
            "2.4 Cookies publicitários (opcionais)"),
           "(isenção CNIL)"),
    "de": ("Letzte Aktualisierung: 16. November 2026",
           ("2.1 Für den Betrieb der Website erforderlicher Speicher",
            "2.2 Reichweitenmessung ohne Cookies (Umami)",
            "2.3 Google-Analytics-Cookies zur Reichweitenmessung (optional)",
            "2.4 Werbe-Cookies (optional)"),
           "(CNIL-Ausnahme)"),
    "nl": ("Laatst bijgewerkt: 16 november 2026",
           ("2.1 Opslag die nodig is voor de werking van de website",
            "2.2 Publieksmeting zonder cookies (Umami)",
            "2.3 Google Analytics-cookies voor publieksmeting (optioneel)",
            "2.4 Advertentiecookies (optioneel)"),
           "(CNIL-vrijstelling)"),
}

_COMMON_CODES = ("<code>_ga_YYJ5LD1ZT3</code>", "<code>lotoia_session</code>", "<code>lotoia-theme</code>",
                 "<code>lotoia_cookie_consent</code>")

# Marqueurs FR des nouveaux textes : interdits dans le texte visible des blocs EN/ES/PT/DE/NL
_FR_MARKERS = ("En résumé", "Mesure d'audience", "consentement", "navigateur", "onglet", "Effacer",
               "éditeur du site")


def _article(page: str) -> str:
    return page[page.index('<article class="legal-content">'):page.index("</article>")]


def _visible(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment))


def _render_em_cookies(lang: str) -> str:
    """Rendu de em/cookies.html, même mécanisme que tests/test_templates.py (_LEGAL_PAGES)."""
    from config.templates import render_template
    request = MagicMock()
    request.url.path = "/euromillions"
    request.query_params = {}
    request.cookies = {}
    request.headers = {}
    resp = render_template("em/cookies.html", request, lang=lang, page_key="cookies",
                           body_class="subpage legal-page em-page")
    assert resp.status_code == 200
    return resp.body.decode("utf-8")


@pytest.fixture(scope="module")
def em_cookies_pages() -> dict[str, str]:
    return {lang: _render_em_cookies(lang) for lang in _LANGS}


def test_lot_1_6_072_cookie_page_loto_old_strings_absent():
    page = _read(_COOKIES_LOTO)
    for old in _OLD_COOKIE_PAGE_LOTO:
        assert old not in page, old


@pytest.mark.parametrize("lang", _LANGS)
def test_lot_1_6_072_cookie_page_em_old_strings_absent(lang):
    src = _read(_EM_COOKIES)
    for old in _OLD_COOKIE_PAGE_EM[lang]:
        assert old not in src, (lang, old)


def test_lot_1_6_072_cookie_pages_no_rgpd_address():
    assert "rgpd@lotoia.fr" not in _read(_COOKIES_LOTO)
    assert "rgpd@lotoia.fr" not in _read(_EM_COOKIES)


def test_lot_1_6_072_cookie_page_loto_new_content():
    page = _read(_COOKIES_LOTO)
    art = _article(page)
    text = html.unescape(art)
    date, titles, cnil = _NEW_COOKIE_PAGE["fr"]
    assert date in html.unescape(page)
    for title in titles:
        assert f"<h3>{title}</h3>" in text, title
    assert cnil in text
    for code in _COMMON_CODES:
        assert code in art, code
    assert "Umami" in text and "contact@lotoia.fr" in text
    assert 'href="/politique-confidentialite"' in art


@pytest.mark.parametrize("lang", _LANGS)
def test_lot_1_6_072_cookie_page_em_new_content(lang, em_cookies_pages):
    from config.templates import EM_URLS
    page = em_cookies_pages[lang]
    art = _article(page)
    text = html.unescape(art)
    date, titles, cnil = _NEW_COOKIE_PAGE[lang]
    assert date in html.unescape(page), lang
    for title in titles:
        assert f"<h3>{title}</h3>" in text, (lang, title)
    assert cnil in text, lang
    for code in _COMMON_CODES:
        assert code in art, (lang, code)
    assert "Umami" in text and "contact@lotoia.fr" in text, lang
    assert f'href="{EM_URLS[lang]["confidentialite"]}"' in art, lang


@pytest.mark.parametrize("lang", [x for x in _LANGS if x != "fr"])
def test_lot_1_6_072_cookie_page_em_zero_fr_string(lang, em_cookies_pages):
    visible = _visible(_article(em_cookies_pages[lang]))
    for marker in _FR_MARKERS:
        assert marker not in visible, (lang, marker)
    # le bloc rendu est bien celui de la langue (pas un repli FR)
    assert _NEW_COOKIE_PAGE[lang][0] in html.unescape(em_cookies_pages[lang])


# ================================================================
# B2 version du consentement — '2.0', toute autre version rejetée (décision 1, option a)
# ================================================================

_VERSION_1_0_RE = re.compile(r"""version:\s*['"]1\.0['"]""")
_CC_VERSION_RE = re.compile(r"^\s*consentVersion:\s*'([^']+)',\s*$", re.M)
_AN_VERSION_RE = re.compile(r"^\s*const CONSENT_VERSION = '([^']+)';\s*$", re.M)


@pytest.fixture(scope="module")
def cc_src() -> str:
    return _read(_COOKIE_CONSENT_JS)


def test_lot_1_6_072_consent_version_in_config(cc_src):
    config = _body(cc_src, "const CONFIG = {", "};")
    assert "consentVersion: '2.0'," in config
    assert len(_CC_VERSION_RE.findall(cc_src)) == 1


def test_lot_1_6_072_save_consent_writes_config_version(cc_src):
    save = _body(cc_src, "function saveConsent(choices)", "function isAccepted(")
    assert "version: CONFIG.consentVersion," in save
    assert not _VERSION_1_0_RE.search(cc_src)
    assert cc_src.count("localStorage.setItem(CONFIG.storageKey") == 1


def test_lot_1_6_072_get_stored_consent_rejects_other_version(cc_src):
    fn = _body(cc_src, "function getStoredConsent()", "function saveConsent(")
    guard = "if (!data || data.version !== CONFIG.consentVersion) {"
    assert guard in fn
    i_parse = fn.index("const data = JSON.parse(stored);")
    i_guard = fn.index(guard)
    block = fn[i_guard:fn.index("}", i_guard)]
    assert block.index("localStorage.removeItem(CONFIG.storageKey);") < block.index("return null;")
    i_expires = fn.index("data.expires && new Date(data.expires) < new Date()")
    assert i_parse < i_guard < i_expires


def test_lot_1_6_072_read_stored_analytics_consent_rejects_other_version(src):
    assert "const CONSENT_VERSION = '2.0';" in src
    assert len(_AN_VERSION_RE.findall(src)) == 1
    fn = _body(src, "function readStoredAnalyticsConsent()", "// ═══")
    guard = "if (!data || data.version !== CONSENT_VERSION) return false;"
    assert guard in fn
    assert "removeItem" not in fn
    i_parse = fn.index("const data = JSON.parse(stored);")
    i_guard = fn.index(guard)
    i_expires = fn.index("data.expires && new Date(data.expires) < new Date()")
    i_choice = fn.index("data.choices.analytics === true")
    assert i_parse < i_guard < i_expires < i_choice


def test_lot_1_6_072_consent_version_parity(cc_src, src):
    cc_version = _CC_VERSION_RE.search(cc_src)
    an_version = _AN_VERSION_RE.search(src)
    assert cc_version and an_version
    assert cc_version.group(1) == an_version.group(1)


def test_lot_1_6_072_single_raw_reader_of_stored_consent(src):
    # analytics.js ne lit la clé qu'à un seul endroit : readStoredAnalyticsConsent (règle de version comprise)
    code = _code(src)
    assert code.count("localStorage.getItem('lotoia_cookie_consent')") == 1
    reader = _body(src, "function readStoredAnalyticsConsent()", "// ═══")
    assert "localStorage.getItem('lotoia_cookie_consent')" in reader
    resync = _body(src, "function resyncConsentFromStorage()", "// ═══")
    assert "lotoia_cookie_consent" not in resync and "localStorage" not in resync
    assert "readStoredAnalyticsConsent()" in resync


_CONSENT_PAGE_PINS = {
    "loto": (
        "Google Analytics ne fait pas partie de ces exceptions : il n'est activé qu'avec votre accord.",
        ("En cas d'ajout d'un nouveau cookie ou traceur soumis à consentement, votre choix vous sera redemandé. "
         "C'est le cas avec la mise à jour du 16 novembre 2026 : votre choix vous est redemandé une fois."),
    ),
    "fr": (
        "Google Analytics ne fait pas partie de ces exceptions : il n'est activé qu'avec votre accord.",
        ("En cas d'ajout d'un nouveau cookie ou traceur soumis à consentement, votre choix vous sera redemandé. "
         "C'est le cas avec la mise à jour du 16 novembre 2026 : votre choix vous est redemandé une fois."),
    ),
    "en": (
        'Google Analytics is not one of these exceptions: it is only activated with your consent.',
        ('If a new cookie or tracker requiring consent is added, you will be asked for your choice again. This is '
         'the case with the update of 16 November 2026: you are asked for your choice once more.'),
    ),
    "es": (
        'Google Analytics no forma parte de estas excepciones: solo se activa con su consentimiento.',
        ('Si se añade una nueva cookie o un nuevo rastreador sujeto a consentimiento, se le volverá a pedir su '
         'elección. Es el caso con la actualización del 16 de noviembre de 2026: se le pide su elección una vez '
         'más.'),
    ),
    "pt": (
        'O Google Analytics não faz parte destas exceções: só é ativado com o teu consentimento.',
        ('Se for adicionado um novo cookie ou rastreador sujeito a consentimento, a tua escolha ser-te-á pedida '
         'novamente. É o caso com a atualização de 16 de novembro de 2026: a tua escolha é-te pedida uma vez '
         'mais.'),
    ),
    "de": (
        'Google Analytics gehört nicht zu diesen Ausnahmen: Es wird nur mit Ihrer Einwilligung aktiviert.',
        ('Wenn ein neues einwilligungspflichtiges Cookie oder ein neuer Tracker hinzugefügt wird, werden Sie '
         'erneut um Ihre Auswahl gebeten. Dies ist bei der Aktualisierung vom 16. November 2026 der Fall: Sie '
         'werden einmal erneut um Ihre Auswahl gebeten.'),
    ),
    "nl": (
        'Google Analytics valt niet onder deze uitzonderingen: het wordt alleen met uw toestemming geactiveerd.',
        ('Als er een nieuwe cookie of tracker wordt toegevoegd waarvoor toestemming nodig is, wordt u opnieuw om '
         'uw keuze gevraagd. Dat is het geval bij de update van 16 november 2026: u wordt eenmaal opnieuw om uw '
         'keuze gevraagd.'),
    ),
}


def _flat_text(fragment: str) -> str:
    return " ".join(_visible(fragment).split())


def _section_3_2(art: str) -> str:
    return art[art.index("<h3>3.2"):art.index("<h3>3.3")]


def test_lot_1_6_072_cookie_page_loto_consent_pins():
    art = _article(_read(_COOKIES_LOTO))
    ga, s7 = _CONSENT_PAGE_PINS["loto"]
    assert ga in _flat_text(_section_3_2(art))
    assert s7 in _flat_text(art)


@pytest.mark.parametrize("lang", _LANGS)
def test_lot_1_6_072_cookie_page_em_consent_pins(lang, em_cookies_pages):
    art = _article(em_cookies_pages[lang])
    ga, s7 = _CONSENT_PAGE_PINS[lang]
    assert ga in _flat_text(_section_3_2(art)), lang
    assert s7 in _flat_text(art), lang


# ================================================================
# B2c — politique de confidentialité Loto (FR) + EM (6 langues), mise à jour du 16 novembre 2026
# ================================================================

_PRIVACY_LOTO = os.path.join(_UI, "politique-confidentialite.html")

# Chaînes retirées : relevées dans le rendu HTTP AVANT édition (toutes présentes au moins une fois),
# comparées après html.unescape, espaces insécables et blancs multiples ramenés à une espace.
# « ICO » : mot entier, dans l'<article> seulement ; toutes les autres : page entière.
_B2C_ABSENT = {
    "loto": (
        "rgpd@lotoia.fr", "supprimées ou anonymisées de manière irréversible", "Authentification forte",
        "UUID v4 généré aléatoirement", "Clauses contractuelles types, ISO 27001", "communications marketing",
        "obligations fiscales", "Sensibilisation à la protection des données", "avis visible sur le site",
        "Ne transmettent pas de données à des serveurs tiers", "Email RGPD", "conforme au RGPD",
        "Dernière mise à jour : 2 novembre 2026", "Mesures supplémentaires de sécurité", "UUID",
        "personnes habilitées", "Analyse agrégée et anonymisée", "l'absence de données sensibles",
        "Pseudonymisation des identifiants de session", "Clauses Contractuelles Types (CCT)",
        "EU-US Data Privacy Framework", "décision d'adéquation du 10 juillet 2023",
        "Une pièce d'identité pourra être demandée", "Email général", "1 mois maximum",
        "Logs serveur - 30 jours maximum", "privilégie l'hébergement des données",
    ),
    "fr": (
        "rgpd@lotoia.fr", "SHA-256", "2 novembre 2026", "exclusivement en interne et par notre hébergeur",
        "nombre très limité de cookies", "UUID", "enregistrés de manière anonyme", "90 jours",
        "analyse agrégée et anonymisée", "hébergées principalement dans l'Union européenne",
        "EU-US Data Privacy Framework", "Données personnelles (RGPD)", "un avis sera publié sur le site",
        "Le profilage comportemental", "Cookies non essentiels",
    ),
    "en": (
        "rgpd@lotoia.fr", "SHA-256", "2 November 2026", "processed exclusively internally and by our hosting provider",
        "very limited number of cookies", "ICO", "Information Commissioner", "UUID", "recorded anonymously",
        "90 days", "aggregated and anonymised traffic analysis", "primarily hosted within the European Union",
        "EU-US Data Privacy Framework", "Personal data (GDPR)", "a notice will be published on the site",
        "Behavioural profiling", "Non-essential cookies",
    ),
    "es": (
        "rgpd@lotoia.fr", "SHA-256", "2 de noviembre de 2026",
        "exclusivamente de forma interna y por nuestro proveedor de alojamiento", "número muy limitado de cookies",
        "AEPD", "Agencia Española de Protección de Datos", "UUID", "se registran de forma anónima", "90 días",
        "análisis agregado y anonimizado", "se alojan principalmente en la Unión Europea",
        "EU-US Data Privacy Framework", "Datos personales (RGPD)", "se publicará un aviso en el sitio",
        "Perfilado comportamental", "Cookies no esenciales",
    ),
    "pt": (
        "rgpd@lotoia.fr", "SHA-256", "2 de novembro de 2026",
        "exclusivamente internamente e pelo nosso fornecedor de alojamento", "número muito limitado de cookies",
        "CNPD", "Comissão Nacional de Proteção de Dados", "UUID", "registadas de forma anónima", "90 dias",
        "análise agregada e anonimizada", "alojados principalmente na União Europeia",
        "EU-US Data Privacy Framework", "Dados pessoais (RGPD)", "será publicado um aviso no site",
        "Perfis comportamentais", "Cookies não essenciais",
    ),
    "de": (
        "rgpd@lotoia.fr", "SHA-256", "2. November 2026",
        "ausschließlich intern und von unserem Hosting-Anbieter verarbeitet", "sehr begrenzte Anzahl von Cookies",
        "BfDI", "Der Bundesbeauftragte für den Datenschutz", "UUID", "anonym aufgezeichnet", "90 Tage",
        "aggregierte und anonymisierte Besucheranalyse", "hauptsächlich in der Europäischen Union gehostet",
        "EU-US Data Privacy Framework", "Personenbezogene Daten (DSGVO)",
        "wird ein Hinweis auf der Website veröffentlicht", "Verhaltensbasiertes Profiling", "Nicht notwendige Cookies",
    ),
    "nl": (
        "rgpd@lotoia.fr", "SHA-256", "2 november 2026", "uitsluitend intern en door onze hostingprovider verwerkt",
        "zeer beperkt aantal cookies", "Autoriteit Persoonsgegevens", "UUID", "anoniem geregistreerd", "90 dagen",
        "geaggregeerde en geanonimiseerde verkeersanalyse", "voornamelijk in de Europese Unie gehost",
        "EU-US Data Privacy Framework", "Persoonsgegevens (AVG)", "wordt een kennisgeving op de site gepubliceerd",
        "Gedragsprofilering", "Niet-essentiële cookies",
    ),
}

# Chaînes nouvelles : relevées dans le rendu APRÈS édition.
# (date, ~3 mois, historique récent, formule CNIL + pays de résidence, stockage mondial, ligne Umami, relecture)
_B2C_PRESENT = {
    "fr": (
        "Dernière mise à jour : 16 novembre 2026", "environ trois mois", "historique récent de la conversation",
        ("auprès de la CNIL (Commission nationale de l'informatique et des libertés), ou auprès de l'autorité de "
         "protection des données de votre pays de résidence dans l'Union européenne"),
        "stockage mondial", "Umami 2 ans la collecte",
        ("Les questions enregistrées peuvent être relues par l'éditeur afin d'améliorer la qualité des "
         "réponses."),
    ),
    "en": (
        "Last updated: 16 November 2026", "about three months", "recent history of the conversation",
        ("with the CNIL (Commission nationale de l'informatique et des libertés, the French data protection "
         "authority), or with the data protection authority of your country of residence in the European Union"),
        "global storage", "Umami 2 years collection",
        "Recorded questions may be reviewed by the publisher in order to improve the quality of the answers.",
    ),
    "es": (
        "Última actualización: 16 de noviembre de 2026", "unos tres meses", "historial reciente de la conversación",
        ("ante la CNIL (Commission nationale de l'informatique et des libertés, la autoridad francesa de "
         "protección de datos), o ante la autoridad de protección de datos de su país de residencia en la Unión "
         "Europea"),
        "almacenamiento mundial", "Umami 2 años la recogida",
        ("Las preguntas registradas pueden ser revisadas por el editor con el fin de mejorar la calidad de las "
         "respuestas."),
    ),
    "pt": (
        "Última atualização: 16 de novembro de 2026", "cerca de três meses", "histórico recente da conversa",
        ("junto da CNIL (Commission nationale de l'informatique et des libertés, a autoridade francesa de "
         "proteção de dados), ou junto da autoridade de proteção de dados do seu país de residência na União "
         "Europeia"),
        "armazenamento mundial", "Umami 2 anos a recolha",
        "As perguntas registadas podem ser relidas pelo editor a fim de melhorar a qualidade das respostas.",
    ),
    "de": (
        "Letzte Aktualisierung: 16. November 2026", "etwa drei Monate", "jüngste Gesprächsverlauf",
        ("bei der CNIL (Commission nationale de l'informatique et des libertés, die französische "
         "Datenschutzaufsichtsbehörde) oder bei der Datenschutzaufsichtsbehörde Ihres Wohnsitzlandes in der "
         "Europäischen Union"),
        "weltweite Speicherung", "Umami 2 Jahre der Erhebung",
        ("Die gespeicherten Fragen können vom Herausgeber gelesen werden, um die Qualität der Antworten zu "
         "verbessern."),
    ),
    "nl": (
        "Laatst bijgewerkt: 16 november 2026", "ongeveer drie maanden", "recente gespreksgeschiedenis",
        ("bij de CNIL (Commission nationale de l'informatique et des libertés, de Franse toezichthouder voor "
         "gegevensbescherming), of bij de gegevensbeschermingsautoriteit van uw land van verblijf in de Europese "
         "Unie"),
        "wereldwijde opslag", "Umami 2 jaar de verzameling",
        ("De opgeslagen vragen kunnen door de uitgever worden nagelezen om de kwaliteit van de antwoorden te "
         "verbeteren."),
    ),
}

# Phrases FR du texte publié, interdites dans le texte visible EN/ES/PT/DE/NL (nom et adresse de la CNIL exclus)
_B2C_FR_PHRASES = (
    "En résumé", "Lors de votre visite", "Ce que vous nous transmettez", "Journaux techniques du serveur",
    "Mesure d'audience interne", "environ trois mois", "historique récent de la conversation", "pays de résidence",
    "stockage mondial", "relues par l'éditeur", "Espaces partenaires", "n'est activé que si vous l'acceptez",
    "Préférence de thème", "Pour que nous puissions retrouver vos données", "Absence de revente",
)

_B2C_IDS_LOTO = ("responsable", "donnees-collectees", "finalites", "base-juridique", "durees", "destinataires",
                 "transferts", "droits", "cookies", "securite", "modifications", "contact")
_B2C_IDS_EM = ("responsable", "donnees-collectees", "finalites", "base-legale", "conservation", "destinataires",
               "transferts", "droits", "cookies", "securite", "modifications", "contact")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def _norm(fragment: str) -> str:
    return " ".join(html.unescape(fragment).replace(" ", " ").split())


def _render_em_privacy(lang: str) -> str:
    """Rendu de em/confidentialite.html, même appel que les routes EM (page_key « confidentialite »)."""
    from config.templates import render_template
    request = MagicMock()
    request.url.path = "/euromillions"
    request.query_params = {}
    request.cookies = {}
    request.headers = {}
    resp = render_template("em/confidentialite.html", request, lang=lang, page_key="confidentialite",
                           body_class="subpage legal-page em-page")
    assert resp.status_code == 200, lang
    return resp.body.decode("utf-8")


@pytest.fixture(scope="module")
def privacy_pages() -> dict[str, str]:
    pages = {lang: _render_em_privacy(lang) for lang in _LANGS}
    pages["loto"] = _read(_PRIVACY_LOTO)
    return pages


def _summary(art: str) -> str:
    return art[:art.index('<nav class="legal-toc">')]


def _section(art: str, anchor: str, next_anchor: str) -> str:
    return art[art.index(f'id="{anchor}"'):art.index(f'id="{next_anchor}"')]


def _banner_ga_sentence(labels: dict[str, dict[str, str]], lang: str) -> str:
    m = re.search(r"(?:O )?Google Analytics [^.]*\.", labels[lang]["banner_text"])
    assert m, lang
    return m.group(0)


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_privacy_old_strings_absent(key, privacy_pages):
    page = privacy_pages[key]
    text = _norm(page)
    art = _norm(_article(page))
    for old in _B2C_ABSENT[key]:
        if old == "ICO":
            assert not re.search(r"\bICO\b", art), (key, old)
        else:
            assert old not in text, (key, old)


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_privacy_new_content(key, privacy_pages):
    page = privacy_pages[key]
    text = _norm(_visible(page))
    for s in _B2C_PRESENT["fr" if key == "loto" else key]:
        assert s in text, (key, s)
    assert "contact@lotoia.fr" in text, key
    assert set(_EMAIL_RE.findall(html.unescape(_article(page)))) == {"contact@lotoia.fr"}, key


def test_lot_1_6_072_privacy_loto_single_address():
    assert set(_EMAIL_RE.findall(html.unescape(_read(_PRIVACY_LOTO)))) == {"contact@lotoia.fr"}


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_privacy_rights_mailto_and_cnil_link(key, privacy_pages):
    art = _article(privacy_pages[key])
    rights = _section(art, "droits", "cookies")
    assert 'href="mailto:contact@lotoia.fr"' in rights, key
    cnil = "https://www.cnil.fr/fr/plaintes" if key in ("loto", "fr") else "https://www.cnil.fr"
    assert f'href="{cnil}"' in rights, key
    assert "CNIL - 3 Place de Fontenoy - TSA 80715 - 75334 PARIS CEDEX 07" in rights, key


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_privacy_banner_wording(key, privacy_pages, labels):
    lang = "fr" if key == "loto" else key
    sentence = _banner_ga_sentence(labels, lang)
    clause = sentence.split(":")[0].rstrip()
    art = _article(privacy_pages[key])
    assert f"{clause}." in _norm(_visible(_summary(art))), (key, clause)
    assert sentence in _norm(_visible(_section(art, "cookies", "securite"))), (key, sentence)


@pytest.mark.parametrize("lang", [x for x in _LANGS if x != "fr"])
def test_lot_1_6_072_privacy_em_zero_fr_string(lang, privacy_pages):
    visible = _norm(_visible(_article(privacy_pages[lang])))
    for phrase in _B2C_FR_PHRASES:
        assert phrase not in visible, (lang, phrase)
    assert _B2C_PRESENT[lang][0] in _norm(_visible(privacy_pages[lang])), lang


def test_lot_1_6_072_privacy_fr_phrases_really_published(privacy_pages):
    # les phrases du test « zéro FR » existent bien dans le FR publié (Loto et EM)
    for key in ("loto", "fr"):
        visible = _norm(_visible(_article(privacy_pages[key])))
        for phrase in _B2C_FR_PHRASES:
            assert phrase in visible, (key, phrase)


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_privacy_section_anchors(key, privacy_pages):
    art = _article(privacy_pages[key])
    ids = re.findall(r'<section class="legal-section" id="([^"]+)"', art)
    assert tuple(ids) == (_B2C_IDS_LOTO if key == "loto" else _B2C_IDS_EM), key


# ================================================================
# QM14 — page cookies § 2.2, mesure interne
# ================================================================

# Paragraphe publié (texte visible normalisé), juste après le paragraphe Umami du § 2.2, avant « 2.3 »
_QM14_PARAGRAPH = {
    "fr": (
        "LotoIA.fr utilise aussi une mesure interne, qui ne dépose rien sur votre appareil et n'utilise pas le "
        "stockage de votre navigateur. Elle est active sans acceptation de votre part. Elle enregistre l'utilisation "
        "des fonctions du site (par exemple : ouverture du chatbot, grille générée, vote envoyé), avec la page "
        "(chemin, sans paramètres), la langue de la page, le type d'appareil, le module concerné (Loto ou "
        "EuroMillions) et le pays déduit de la langue de votre navigateur. Ces données sont associées à un identifiant "
        "quotidien haché (pseudonymisé), calculé à partir de l'adresse IP, du navigateur et de la date, qui change "
        "chaque jour. Elles sont conservées environ trois mois dans notre base de données, hébergée dans l'Union "
        "européenne. Certains événements sont aussi transmis à Umami. Le détail figure dans notre politique de "
        "confidentialité."
    ),
    "en": (
        "LotoIA.fr also uses an internal measurement, which stores nothing on your device and does not use your "
        "browser's storage. It is active without your acceptance. It records the use of the site's features (for "
        "example: chatbot opened, combination generated, rating sent), with the page (path, without parameters), "
        "the page language, the device type, the module concerned (Loto or EuroMillions) and the country inferred from "
        "your browser's language. This data is associated with a hashed daily identifier (pseudonymised), calculated "
        "from the IP address, the browser and the date, which changes every day. It is kept for about three months in "
        "our database, hosted in the European Union. Some events are also sent to Umami. Details are given in our "
        "privacy policy."
    ),
    "es": (
        "LotoIA.fr utiliza también una medición interna, que no almacena nada en su dispositivo y no utiliza el "
        "almacenamiento de su navegador. Está activa sin su aceptación. Registra el uso de las funciones del sitio "
        "(por ejemplo: apertura del chatbot, combinación generada, valoración enviada), con la página (ruta, sin "
        "parámetros), el idioma de la página, el tipo de dispositivo, el módulo correspondiente (Loto o "
        "EuroMillions) y el país deducido del idioma de su navegador. Estos datos se asocian a un identificador diario "
        "con hash (seudonimizado), calculado a partir de la dirección IP, del navegador y de la fecha, que cambia cada "
        "día. Se conservan unos tres meses en nuestra base de datos, alojada en la Unión Europea. Algunos eventos "
        "también se transmiten a Umami. El detalle figura en nuestra política de privacidad."
    ),
    "pt": (
        "O LotoIA.fr utiliza também uma medição interna, que não armazena nada no teu dispositivo e não utiliza o "
        "armazenamento do teu navegador. Está ativa sem a tua aceitação. Regista a utilização das funcionalidades "
        "do sítio (por exemplo: abertura do chatbot, grelha gerada, avaliação enviada), com a página (caminho, sem "
        "parâmetros), a língua da página, o tipo de dispositivo, o módulo em causa (Loto ou EuroMillions) e o país "
        "deduzido da língua do teu navegador. Estes dados são associados a um identificador diário com hash "
        "(pseudonimizado), calculado a partir do endereço IP, do navegador e da data, que muda todos os dias. São "
        "conservados cerca de três meses na nossa base de dados, alojada na União Europeia. Alguns eventos são também "
        "transmitidos ao Umami. O detalhe consta da nossa política de privacidade."
    ),
    "de": (
        "LotoIA.fr nutzt außerdem eine interne Messung, die nichts auf Ihrem Gerät speichert und nicht den Speicher "
        "Ihres Browsers nutzt. Sie ist ohne Ihre Zustimmung aktiv. Sie erfasst die Nutzung der Funktionen der "
        "Website (zum Beispiel: Öffnen des Chatbots, generierte Kombination, gesendete Bewertung) mit der Seite "
        "(Pfad, ohne Parameter), der Sprache der Seite, dem Gerätetyp, dem betroffenen Modul (Loto oder "
        "EuroMillions) und dem aus der Sprache Ihres Browsers abgeleiteten Land. Diese Daten sind mit einer gehashten "
        "täglichen Kennung (pseudonymisiert) verknüpft, die aus IP-Adresse, Browser und Datum berechnet wird und sich "
        "täglich ändert. Sie werden etwa drei Monate in unserer Datenbank gespeichert, die in der Europäischen Union "
        "gehostet wird. Einige Ereignisse werden außerdem an Umami übermittelt. Einzelheiten finden Sie in unserer "
        "Datenschutzerklärung."
    ),
    "nl": (
        "LotoIA.fr gebruikt ook een interne meting, die niets op uw apparaat plaatst en de opslag van uw browser "
        "niet gebruikt. Deze is actief zonder uw acceptatie. Ze registreert het gebruik van de functies van de "
        "website (bijvoorbeeld: chatbot geopend, combinatie gegenereerd, beoordeling verzonden), met de pagina "
        "(pad, zonder parameters), de taal van de pagina, het type apparaat, de betrokken module (Loto of "
        "EuroMillions) en het land afgeleid uit de taal van uw browser. Deze gegevens worden gekoppeld aan een "
        "gehashte dagelijkse identificatie (gepseudonimiseerd), berekend op basis van het IP-adres, de browser en de "
        "datum, die elke dag verandert. Ze worden ongeveer drie maanden bewaard in onze database, die in de Europese "
        "Unie wordt gehost. Sommige gebeurtenissen worden ook aan Umami doorgegeven. De details staan in ons "
        "privacybeleid."
    ),
}
_QM14_FR_PHRASES = ("mesure interne", "identifiant quotidien haché (pseudonymisé)",
                    "ne dépose rien sur votre appareil", "Certains événements sont aussi transmis",
                    "environ trois mois")


def _qm14_pages(em_cookies_pages) -> dict[str, str]:
    return {"loto": _read(_COOKIES_LOTO), **em_cookies_pages}


def _qm14_section_2_2(art: str) -> str:
    return art[art.index("<h3>2.2"):art.index("<h3>2.3")]


def _qm14_paragraphs(fragment: str) -> list[str]:
    return re.findall(r"<p>(.*?)</p>", fragment, re.S)


def _qm14_text(fragment: str) -> str:
    # balises retirées sans espace ajoutée (le point suit directement le lien), puis même normalisation que B2c
    return _norm(re.sub(r"<[^>]+>", "", fragment))


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_qm14_paragraph_published(key, em_cookies_pages):
    art = _article(_qm14_pages(em_cookies_pages)[key])
    expected = _QM14_PARAGRAPH["fr" if key == "loto" else key]
    assert _qm14_text(art).count(expected) == 1, key


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_qm14_paragraph_position(key, em_cookies_pages):
    art = _article(_qm14_pages(em_cookies_pages)[key])
    paras = _qm14_paragraphs(_qm14_section_2_2(art))
    assert len(paras) == 2, (key, len(paras))
    assert "Umami Cloud" in paras[0], key
    assert _qm14_text(paras[1]) == _QM14_PARAGRAPH["fr" if key == "loto" else key], key


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_qm14_paragraph_link(key, em_cookies_pages):
    from config.templates import EM_URLS
    umami, internal = _qm14_paragraphs(_qm14_section_2_2(_article(_qm14_pages(em_cookies_pages)[key])))
    target = "/politique-confidentialite" if key == "loto" else EM_URLS[key]["confidentialite"]
    assert re.findall(r'href="([^"]+)"', internal) == [target], key
    assert re.findall(r'href="([^"]+)"', umami) == [target], key


@pytest.mark.parametrize("lang", [x for x in _LANGS if x != "fr"])
def test_lot_1_6_072_qm14_em_zero_fr_string(lang, em_cookies_pages):
    visible = _norm(_visible(_article(em_cookies_pages[lang])))
    for phrase in _QM14_FR_PHRASES:
        assert phrase not in visible, (lang, phrase)


def test_lot_1_6_072_qm14_fr_phrases_really_published(em_cookies_pages):
    for key, page in (("loto", _read(_COOKIES_LOTO)), ("fr", em_cookies_pages["fr"])):
        visible = _norm(_visible(_article(page)))
        for phrase in _QM14_FR_PHRASES:
            assert phrase in visible, (key, phrase)


# ================================================================
# B2d — mentions légales Loto (FR) + EM (6 langues), mise à jour du 16 novembre 2026
# ================================================================

_MENTIONS_LOTO = os.path.join(_UI, "mentions-legales.html")

# Chaînes retirées : relevées sur le rendu HTTP AVANT édition (toutes présentes au moins une fois), page entière,
# html.unescape, balises remplacées par une espace, blancs ramenés à une espace.
_B2D_ABSENT = {
    "loto": (
        "Raison sociale : Google Cloud Platform", "Entité juridique : Google Ireland Limited",
        "Google Cloud Run — Union européenne", "risque minimal", "API Google Gemini",
        "strictement techniques et fonctionnelles", "rgpd@lotoia.fr", "Dernière mise à jour : 2 novembre 2026",
        "classifié comme présentant", "Politique de gestion des cookies",
        "Les données sont hébergées sur des serveurs situés au sein de l'Union européenne",
        "Protection des données (RGPD)",
    ),
    "fr": (
        "Hébergeur : Google Cloud Platform (Cloud Run)", "Cloud Run EU", "risque minimal", "API Gemini",
        "cookies strictement nécessaires", "2 novembre 2026", "Société : Google Ireland Limited", "Google Gemini API",
        "Les données sont hébergées au sein de l'Union européenne",
    ),
    "en": (
        "Host: Google Cloud Platform (Cloud Run)", "Cloud Run EU", "minimal risk", "Gemini API",
        "cookies that are strictly necessary", "2 November 2026", "Company: Google Ireland Limited",
        "Data is hosted within the European Union",
    ),
    "es": (
        "Proveedor de alojamiento: Google Cloud Platform (Cloud Run)", "Cloud Run EU", "riesgo mínimo", "API Gemini",
        "cookies estrictamente necesarias", "2 de noviembre de 2026", "Sociedad: Google Ireland Limited",
        "Google Gemini API",
    ),
    "pt": (
        "Fornecedor de alojamento: Google Cloud Platform (Cloud Run)", "Cloud Run EU", "risco mínimo", "API Gemini",
        "cookies estritamente necessários", "2 de novembro de 2026", "Sociedade: Google Ireland Limited",
        "Google Gemini API",
    ),
    "de": (
        "Hoster: Google Cloud Platform (Cloud Run)", "Cloud Run EU", "minimales Risiko", "Gemini API",
        "unbedingt erforderliche Cookies", "2. November 2026", "Unternehmen: Google Ireland Limited",
    ),
    "nl": (
        "Hostingprovider: Google Cloud Platform (Cloud Run)", "Cloud Run EU", "minimaal risico", "Gemini API",
        "cookies die strikt noodzakelijk zijn", "2 november 2026", "Onderneming: Google Ireland Limited",
    ),
}

# Textes nouveaux (rendu APRÈS) : (date, journaux techniques, article 50) ; « Vertex AI » et « Cloud SQL » partout
_B2D_PRESENT = {
    "fr": (
        "Dernière mise à jour : 16 novembre 2026",
        ("Seuls les journaux techniques du serveur (conservés 30 jours) sont stockés par Google Cloud sans garantie "
         "de localisation dans l'Union européenne."),
        "vous êtes informé que vous échangez avec une intelligence artificielle, et non avec une personne.",
    ),
    "en": (
        "Last updated: 16 November 2026",
        ("Only the server technical logs (kept for 30 days) are stored by Google Cloud with no guarantee of location "
         "in the European Union."),
        "you are informed that you are interacting with an artificial intelligence, not with a person.",
    ),
    "es": (
        "Última actualización: 16 de noviembre de 2026",
        ("Solo los registros técnicos del servidor (conservados 30 días) son almacenados por Google Cloud sin "
         "garantía de ubicación en la Unión Europea."),
        "se le informa de que está interactuando con una inteligencia artificial, y no con una persona.",
    ),
    "pt": (
        "Última atualização: 16 de novembro de 2026",
        ("Apenas os registos técnicos do servidor (conservados durante 30 dias) são armazenados pela Google Cloud "
         "sem garantia de localização na União Europeia."),
        "ficas informado de que estás a interagir com uma inteligência artificial, e não com uma pessoa.",
    ),
    "de": (
        "Letzte Aktualisierung: 16. November 2026",
        ("Nur die technischen Server-Protokolle (30 Tage aufbewahrt) werden von Google Cloud ohne Garantie eines "
         "Standorts in der Europäischen Union gespeichert."),
        ("werden Sie darauf hingewiesen, dass Sie mit einer künstlichen Intelligenz und nicht mit einem Menschen "
         "interagieren."),
    ),
    "nl": (
        "Laatst bijgewerkt: 16 november 2026",
        ("Alleen de technische serverlogboeken (30 dagen bewaard) worden door Google Cloud opgeslagen zonder "
         "garantie van locatie in de Europese Unie."),
        "wordt u ervan in kennis gesteld dat u communiceert met een kunstmatige intelligentie, en niet met een persoon.",
    ),
}

# Phrases FR du texte publié, interdites dans le texte visible EN/ES/PT/DE/NL
_B2D_FR_PHRASES = (
    "Seuls les journaux techniques", "vous êtes informé que vous échangez", "et non avec une personne",
    "mesure d'audience sans cookie", "Services utilisés", "modèle Gemini de Google",
    "n'est activé que si vous l'acceptez",
)
_B2D_IDS_EM = ("editeur", "hebergement", "nature-service", "intelligence-artificielle", "propriete-intellectuelle",
               "donnees-personnelles", "cookies", "responsabilite", "jeu-responsable", "droit-applicable", "credits",
               "contact")


def _render_em_mentions(lang: str) -> str:
    """Rendu de em/mentions-legales.html, même appel que les routes EM (page_key « mentions »)."""
    from config.templates import render_template
    request = MagicMock()
    request.url.path = "/euromillions"
    request.query_params = {}
    request.cookies = {}
    request.headers = {}
    resp = render_template("em/mentions-legales.html", request, lang=lang, page_key="mentions",
                           body_class="subpage legal-page em-page")
    assert resp.status_code == 200, lang
    return resp.body.decode("utf-8")


@pytest.fixture(scope="module")
def mentions_pages() -> dict[str, str]:
    pages = {lang: _render_em_mentions(lang) for lang in _LANGS}
    pages["loto"] = _read(_MENTIONS_LOTO)
    return pages


def _b2d_section_7(art: str) -> str:
    return art[art.index("<h2>7."):art.index("<h2>8.")]


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_mentions_old_strings_absent(key, mentions_pages):
    text = _norm(_visible(mentions_pages[key]))
    for old in _B2D_ABSENT[key]:
        assert old not in text, (key, old)


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_mentions_new_content(key, mentions_pages):
    page = mentions_pages[key]
    text = _qm14_text(page)
    for s in _B2D_PRESENT["fr" if key == "loto" else key]:
        assert s in text, (key, s)
    art = _qm14_text(_article(page))
    assert "Vertex AI" in art and "Cloud SQL" in art, key


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_mentions_banner_wording(key, mentions_pages, labels):
    lang = "fr" if key == "loto" else key
    clause = _banner_ga_sentence(labels, lang).split(":")[0].rstrip() + "."
    assert clause in _norm(_visible(_b2d_section_7(_article(mentions_pages[key])))), (key, clause)


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_mentions_email_addresses(key, mentions_pages):
    found = set(_EMAIL_RE.findall(html.unescape(_article(mentions_pages[key]))))
    assert found == {"contact@lotoia.fr", "partenariats@lotoia.fr"}, (key, found)


@pytest.mark.parametrize("lang", [x for x in _LANGS if x != "fr"])
def test_lot_1_6_072_mentions_em_zero_fr_string(lang, mentions_pages):
    visible = _norm(_visible(_article(mentions_pages[lang])))
    for phrase in _B2D_FR_PHRASES:
        assert phrase not in visible, (lang, phrase)


def test_lot_1_6_072_mentions_fr_phrases_really_published(mentions_pages):
    for key in ("loto", "fr"):
        visible = _norm(_visible(_article(mentions_pages[key])))
        for phrase in _B2D_FR_PHRASES:
            assert phrase in visible, (key, phrase)


@pytest.mark.parametrize("lang", _LANGS)
def test_lot_1_6_072_mentions_em_section_anchors(lang, mentions_pages):
    ids = re.findall(r'<section class="legal-section" id="([^"]+)"', _article(mentions_pages[lang]))
    assert tuple(ids) == _B2D_IDS_EM, lang


# ================================================================
# B2d-bis — § 4.1 des mentions Loto + ligne AI Act et date des pages Avertissements (Loto + EM 6 langues)
# ================================================================

_DISCLAIMER_LOTO = os.path.join(_UI, "disclaimer.html")

# Chaînes retirées : relevées sur les rendus HTTP de la copie d'AVANT (toutes présentes une fois)
_B2DBIS_ABSENT_MENTIONS = ("ne fournit en aucun cas des numéros",)
_B2DBIS_ABSENT = {
    "loto": ("Classification AI Act", "risque minimal", "Système à risque minimal (Article 6)",
             "Dernière mise à jour : 23 janvier 2026"),
    "fr": ("Classification AI Act", "risque minimal", "Système à risque minimal (Article 6)",
           "Dernière mise à jour : 1 mars 2026"),
    "en": ("AI Act classification", "Minimal risk system", "Last updated: 1 March 2026"),
    "es": ("Clasificacion AI Act", "riesgo minimo", "1 de marzo de 2026"),
    "pt": ("Classificacao AI Act", "risco minimo", "1 de marco de 2026"),
    "de": ("AI-Act-Klassifizierung", "minimalem Risiko", "1. Marz 2026"),
    "nl": ("AI Act-classificatie", "minimaal risico", "1 maart 2026"),
}
_B2DBIS_MENTIONS_PHRASE = ("Lorsqu'il présente une combinaison de numéros, celle-ci est générée par le moteur "
                           "statistique HYBRIDE, à titre informatif et sans aucune valeur prédictive ;")
# (ligne AI Act, date) — texte visible normalisé, relevé sur les rendus APRÈS
_B2DBIS_PRESENT = {
    "fr": ("Transparence AI Act : le chatbot HYBRIDE est un système d'intelligence artificielle ; vous en êtes "
           "informé dès l'ouverture du chat (article 50).", "Dernière mise à jour : 16 novembre 2026"),
    "en": ("AI Act transparency: the HYBRIDE chatbot is an artificial intelligence system; you are informed of this "
           "as soon as you open the chat (Article 50).", "Last updated: 16 November 2026"),
    "es": ("Transparencia AI Act: el chatbot HYBRIDE es un sistema de inteligencia artificial; se le informa de ello "
           "desde la apertura del chat (artículo 50).", "Ultima actualizacion: 16 de noviembre de 2026"),
    "pt": ("Transparência AI Act: o chatbot HYBRIDE é um sistema de inteligência artificial; és informado disso logo "
           "na abertura do chat (artigo 50.º).", "Ultima atualizacao: 16 de novembro de 2026"),
    "de": ("AI-Act-Transparenz: Der HYBRIDE-Chatbot ist ein System der künstlichen Intelligenz; Sie werden darauf "
           "bereits beim Öffnen des Chats hingewiesen (Artikel 50).", "Letzte Aktualisierung: 16. November 2026"),
    "nl": ("AI Act-transparantie: de HYBRIDE-chatbot is een systeem van kunstmatige intelligentie; u wordt hierover "
           "geïnformeerd zodra u de chat opent (artikel 50).", "Laatst bijgewerkt: 16 november 2026"),
}
_B2DBIS_FR_PHRASES = ("Transparence AI Act", "le chatbot HYBRIDE est un système d'intelligence artificielle",
                      "vous en êtes informé dès l'ouverture du chat")


def _render_em_disclaimer(lang: str) -> str:
    """Rendu de em/disclaimer.html, même appel que les routes EM (page_key « disclaimer »)."""
    from config.templates import render_template
    request = MagicMock()
    request.url.path = "/euromillions"
    request.query_params = {}
    request.cookies = {}
    request.headers = {}
    resp = render_template("em/disclaimer.html", request, lang=lang, page_key="disclaimer",
                           body_class="subpage legal-page em-page")
    assert resp.status_code == 200, lang
    return resp.body.decode("utf-8")


@pytest.fixture(scope="module")
def disclaimer_pages() -> dict[str, str]:
    pages = {lang: _render_em_disclaimer(lang) for lang in _LANGS}
    pages["loto"] = _read(_DISCLAIMER_LOTO)
    return pages


def test_lot_1_6_072_dbis_mentions_paragraph(mentions_pages):
    text = _norm(_visible(mentions_pages["loto"]))
    for old in _B2DBIS_ABSENT_MENTIONS:
        assert old not in text, old
    assert text.count(_B2DBIS_MENTIONS_PHRASE) == 1


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_dbis_disclaimer_old_strings_absent(key, disclaimer_pages):
    text = _norm(_visible(disclaimer_pages[key]))
    for old in _B2DBIS_ABSENT[key]:
        assert old not in text, (key, old)


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_dbis_disclaimer_ai_act_line(key, disclaimer_pages):
    line, _date = _B2DBIS_PRESENT["fr" if key == "loto" else key]
    assert _norm(_visible(_article(disclaimer_pages[key]))).count(line) == 1, key


@pytest.mark.parametrize("key", ["loto"] + list(_LANGS))
def test_lot_1_6_072_dbis_disclaimer_date(key, disclaimer_pages):
    _line, date = _B2DBIS_PRESENT["fr" if key == "loto" else key]
    assert date in _norm(_visible(disclaimer_pages[key])), (key, date)


@pytest.mark.parametrize("lang", [x for x in _LANGS if x != "fr"])
def test_lot_1_6_072_dbis_disclaimer_em_zero_fr_string(lang, disclaimer_pages):
    visible = _norm(_visible(_article(disclaimer_pages[lang])))
    for phrase in _B2DBIS_FR_PHRASES:
        assert phrase not in visible, (lang, phrase)


def test_lot_1_6_072_dbis_fr_phrases_really_published(disclaimer_pages):
    for key in ("loto", "fr"):
        visible = _norm(_visible(_article(disclaimer_pages[key])))
        for phrase in _B2DBIS_FR_PHRASES:
            assert phrase in visible, (key, phrase)


# ================================================================
# B2e — FAQ /hybride (D4), /faq (D8 + données), accroche /fr, À propos Loto + EM, prompts du chatbot (D8 + Q/R)
# ================================================================

_HYBRIDE = os.path.join(_UI, "hybride.html")
_FAQ = os.path.join(_UI, "faq.html")
_APROPOS = os.path.join(_UI, "a-propos.html")
_PROMPTS = {"loto": os.path.join(_ROOT, "prompts", "chatbot", "prompt_hybride.txt"),
            **{lg: os.path.join(_ROOT, "prompts", "em", lg, "prompt_hybride_em.txt")
               for lg in ("fr", "en", "es", "pt", "de", "nl")}}
_JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)

_E1_QUESTION = "Mes conversations sont-elles enregistrées ?"
_E1_ANSWER = (
    "Vos questions et le début des réponses du chatbot sont enregistrés sans identifiant (ni adresse IP, ni compte), "
    "afin d'analyser et d'améliorer la qualité des réponses. Ils sont supprimés au bout d'environ trois mois. Pour "
    "produire une réponse, vos questions et l'historique récent de la conversation peuvent être transmis à Google "
    "(Vertex AI), dans l'Union européenne (Belgique). Comme tout site web, nos journaux techniques, conservés 30 jours, "
    "enregistrent l'adresse IP des visiteurs et peuvent contenir des extraits de messages. Évitez d'y saisir des "
    "informations personnelles. Plus de détails dans notre politique de confidentialité."
)
_E2_NEW = ("Nos données sont les résultats officiels publiés par la Française des Jeux (FDJ), saisis manuellement après "
           "chaque tirage.")
_E3_JSONLD = (
    "LotoIA respecte le RGPD : les questions posées au chatbot sont conservées environ trois mois sans identifiant, la "
    "mesure d'audience interne utilise un identifiant quotidien haché (pseudonymisé), aucun cookie publicitaire n'est "
    "utilisé et Google Analytics n'est activé que si vous l'acceptez. LotoIA ne vend pas vos données ; certaines sont "
    "traitées par nos prestataires (Google Cloud, Umami). Détails dans notre politique de confidentialité."
)
_E3_VISIBLE = (
    "Les questions posées au chatbot et le début de ses réponses sont conservés environ trois mois, sans identifiant, "
    "puis supprimés",
    "La mesure d'audience interne utilise un identifiant quotidien haché (pseudonymisé), qui change chaque jour",
    "Nous n'utilisons aucun cookie publicitaire. Google Analytics n'est activé que si vous l'acceptez",
    "Umami Cloud mesure l'audience sans cookie",
    ("Vous pouvez demander la suppression de vos données à contact@lotoia.fr (les conversations, enregistrées sans "
     "identifiant, ne sont pas retrouvables)"),
    ("LotoIA ne vend pas vos données. Certaines sont traitées par nos prestataires (Google Cloud, Umami) pour faire "
     "fonctionner et mesurer le site : le détail figure dans notre politique de confidentialité."),
)
_E3_OLD = ("ne stockons jamais votre IP en clair", "anonymisée", "ne vend ni ne partage", "90 jours maximum")
_E4_OLD_FR = "IA connectée en temps réel aux tirages officiels"
_E4_NEW = {
    "fr": "IA connectée aux résultats officiels, mis à jour après chaque tirage",
    "en": "AI connected to official results, updated after each draw",
    "es": "IA conectada a los resultados oficiales, actualizados después de cada sorteo",
    "pt": "IA ligada aos resultados oficiais, atualizados após cada sorteio",
    "de": "KI mit den offiziellen Ergebnissen verbunden, nach jeder Ziehung aktualisiert",
    "nl": "AI verbonden met de officiële resultaten, bijgewerkt na elke trekking",
}
_E4_OLD = {
    "en": "AI connected in real time to official draws", "es": "IA conectada en tiempo real a los sorteos oficiales",
    "pt": "IA ligada em tempo real aos sorteios oficiais", "de": "KI in Echtzeit mit offiziellen Ziehungen verbunden",
    "nl": "AI in realtime verbonden met officiële trekkingen",
}
_E51_NEW = (
    ("Toutes les données utilisées par LotoIA sont les résultats officiels publiés par la Française des Jeux, saisis "
     "manuellement après chaque tirage."),
    ("Les données sont mises à jour après chaque tirage officiel (lundi, mercredi, samedi). Aucune donnée n'est "
     "inventée ou approximée."),
    "Cette architecture garantit la disponibilité et la sécurité du site. Les données sont mises à jour après chaque "
    "tirage officiel.",
)
_E51_OLD = ("l'API officielle de la Française des Jeux", "mises à jour automatiquement",
            "mise à jour automatique des données")
_E8_NEW, _E8_OLD = "Mise à jour après chaque tirage officiel (lundi, mercredi, samedi)", "Synchronisation automatique"
_E52_NEW = {
    "fr": ("Cette architecture garantit la disponibilité et la sécurité du site. Les données sont mises à jour après "
           "chaque tirage officiel.", "Elles sont saisies manuellement après chaque tirage."),
    "en": ("This architecture ensures the availability and security of the site. Data is updated after each official "
           "draw.", "It is entered manually after each draw."),
    "es": ("Esta arquitectura garantiza la disponibilidad y la seguridad del sitio. Los datos se actualizan después de "
           "cada sorteo oficial.", "Se introducen manualmente después de cada sorteo."),
    "pt": ("Esta arquitetura garante a disponibilidade e a segurança do site. Os dados são atualizados após cada "
           "sorteio oficial.", "São introduzidos manualmente após cada sorteio."),
    "de": ("Diese Architektur gewährleistet die Verfügbarkeit und Sicherheit der Website. Die Daten werden nach jeder "
           "offiziellen Ziehung aktualisiert.", "Sie werden nach jeder Ziehung manuell erfasst."),
    "nl": ("Deze architectuur garandeert de beschikbaarheid en de veiligheid van de website. De gegevens worden na elke "
           "officiële trekking bijgewerkt.", "Ze worden na elke trekking handmatig ingevoerd."),
}
_E52_OLD = {
    "fr": ("mise à jour automatique des données", "mises à jour automatiquement"),
    "en": ("automatic data updates", "updated automatically"),
    "es": ("actualización automática de los datos", "Se actualizan automáticamente"),
    "pt": ("atualização automática dos dados", "atualizados automaticamente"),
    "de": ("automatische Aktualisierung der Daten", "automatisch aktualisiert"),
    "nl": ("automatische bijwerking", "automatisch bijgewerkt"),
}
_E52_FR_PHRASES = ("Cette architecture garantit", "saisies manuellement", "Les données sont mises à jour")
# (Q/R e6 — début de la réponse imposée, D8 nouveau) et D8 retiré, par prompt
_E6_PROMPT = {
    "loto": ("Tes questions et le début de mes réponses sont enregistrés sans identifiant (ni adresse IP, ni compte)",
             "Des résultats officiels publiés par la Française des Jeux (FDJ), saisis manuellement après chaque tirage."),
    "fr": ("Tes questions et le début de mes réponses sont enregistrés sans identifiant (ni adresse IP, ni compte)",
           "Des résultats officiels publiés par la Française des Jeux (FDJ), saisis manuellement après chaque tirage."),
    "en": ("Your questions and the beginning of my answers are recorded without any identifier (neither IP address nor "
           "account)", "From the official results published by the Française des Jeux (FDJ), entered manually after "
           "each draw."),
    "es": ("Tus preguntas y el comienzo de mis respuestas se registran sin ningún identificador (ni dirección IP, ni "
           "cuenta)", "De los resultados oficiales publicados por la Française des Jeux (FDJ), introducidos "
           "manualmente después de cada sorteo."),
    "pt": ("As tuas perguntas e o início das minhas respostas são registados sem qualquer identificador (nem endereço "
           "IP, nem conta)", "Dos resultados oficiais publicados pela Française des Jeux (FDJ), introduzidos "
           "manualmente após cada sorteio."),
    "de": ("Deine Fragen und der Anfang meiner Antworten werden ohne Kennung (weder IP-Adresse noch Konto) gespeichert",
           "Aus den offiziellen Ergebnissen, die von der Française des Jeux (FDJ) veröffentlicht werden, manuell nach "
           "jeder Ziehung erfasst."),
    "nl": ("Je vragen en het begin van mijn antwoorden worden opgeslagen zonder identificatie (geen IP-adres en geen "
           "account)", "Van de officiele resultaten die door de Francaise des Jeux (FDJ) worden gepubliceerd, "
           "handmatig ingevoerd na elke trekking."),
}
_E6_PROMPT_OLD = {
    "loto": ("De l'API officielle de la Française des Jeux (FDJ)", "Base mise à jour régulièrement"),
    "fr": ("De l'API officielle de la Française des Jeux (FDJ)", "Base mise à jour régulièrement"),
    "en": ("official Française des Jeux (FDJ) API", "Database updated regularly"),
    "es": ("De la API oficial", "actualizada periódicamente"),
    "pt": ("Da API oficial", "atualizada regularmente"),
    "de": ("offiziellen API der Française des Jeux", "Datenbank wird regelmäßig"),
    "nl": ("officiele API van de Francaise des Jeux", "wordt regelmatig bijgewerkt"),
}


def _jsonld_blocks(page: str) -> list:
    return [json.loads(b) for b in _JSONLD_RE.findall(page)]


def _faq_answers(page: str) -> dict[str, str]:
    out = {}
    for block in _jsonld_blocks(page):
        if block.get("@type") == "FAQPage":
            for q in block.get("mainEntity", []):
                out[q["name"]] = q["acceptedAnswer"]["text"]
    return out


def _visible_answer(page: str, question: str) -> str:
    start = page.index(f"<h3>{question}</h3>")
    return _qm14_text(re.search(r"<p>(.*?)</p>", page[start:], re.S).group(1))


@pytest.fixture(scope="module")
def launcher_pages() -> dict[str, str]:
    from routes.launcher import _render_launcher
    return {lang: _render_launcher(lang, MagicMock()).body.decode("utf-8") for lang in _LANGS}


def _render_em_apropos(lang: str) -> str:
    from config.templates import render_template
    request = MagicMock()
    request.url.path = "/euromillions"
    request.query_params = {}
    request.cookies = {}
    request.headers = {}
    resp = render_template("em/a-propos.html", request, lang=lang, page_key="a_propos", body_class="subpage em-page",
                           include_nav_scroll=True)
    assert resp.status_code == 200, lang
    return resp.body.decode("utf-8")


@pytest.fixture(scope="module")
def em_apropos_pages() -> dict[str, str]:
    return {lang: _render_em_apropos(lang) for lang in _LANGS}


@pytest.mark.parametrize("path", [_HYBRIDE, _FAQ])
def test_lot_1_6_072_e_jsonld_valid(path):
    blocks = _JSONLD_RE.findall(_read(path))
    assert blocks, path
    for b in blocks:
        json.loads(b)


def test_lot_1_6_072_e1_hybride_d4_answer():
    page = _read(_HYBRIDE)
    answers = _faq_answers(page)
    assert answers.get(_E1_QUESTION) == _E1_ANSWER
    assert list(answers.values()).count(_E1_ANSWER) == 1
    assert _visible_answer(page, _E1_QUESTION) == _E1_ANSWER
    without_scripts = re.sub(r"<script\b.*?</script>", " ", page, flags=re.S)
    assert _qm14_text(without_scripts).count(_E1_ANSWER) == 1
    text = _norm(_visible(page))
    for old in ("Aucune donnée personnelle n'est stockée", "ni enregistrées",
                "Mes conversations avec HYBRIDE sont-elles enregistrées ?"):
        assert old not in text, old
    i = page.index(f"<h3>{_E1_QUESTION}</h3>")
    assert 'href="/politique-confidentialite"' in page[i:page.index("</p>", i)]


def test_lot_1_6_072_e2_faq_data_source():
    text = _qm14_text(_read(_FAQ))
    assert _E2_NEW in text
    assert "API officielle de la Française des Jeux" not in text


def test_lot_1_6_072_e3_faq_data_protection():
    page = _read(_FAQ)
    answers = _faq_answers(page)
    assert answers.get("Comment mes données sont-elles protégées ?") == _E3_JSONLD
    for jsonld_text in answers.values():
        for old in _E3_OLD:
            assert old not in jsonld_text, old
    text = _qm14_text(page)
    for s in _E3_VISIBLE:
        assert s in text, s
    visible = _norm(_visible(page))
    for old in _E3_OLD:
        assert old not in visible, old
    assert 'href="mailto:contact@lotoia.fr"' in page


@pytest.mark.parametrize("lang", _LANGS)
def test_lot_1_6_072_e4_launcher_tagline(lang, launcher_pages):
    text = _norm(_visible(launcher_pages[lang]))
    assert _E4_NEW[lang] in text, lang
    assert _E4_OLD_FR not in text, lang
    if lang != "fr":
        assert _E4_OLD[lang] not in text, lang
        assert _E4_NEW["fr"] not in text, lang


def test_lot_1_6_072_e51_e8_loto_pages():
    apropos = _qm14_text(_read(_APROPOS))
    for s in _E51_NEW:
        assert s in apropos, s
    for old in _E51_OLD:
        assert old not in apropos, old
    hybride = _qm14_text(_read(_HYBRIDE))
    assert _E8_NEW in hybride
    assert _E8_OLD not in hybride


@pytest.mark.parametrize("lang", _LANGS)
def test_lot_1_6_072_e52_em_apropos(lang, em_apropos_pages):
    text = _norm(_visible(em_apropos_pages[lang]))
    for s in _E52_NEW[lang]:
        assert s in text, (lang, s)
    for old in _E52_OLD[lang]:
        assert old not in text, (lang, old)
    if lang != "fr":
        for phrase in _E52_FR_PHRASES:
            assert phrase not in text, (lang, phrase)


@pytest.mark.parametrize("key", list(_PROMPTS))
def test_lot_1_6_072_e53_e6_prompts(key):
    text = " ".join(_read(_PROMPTS[key]).split())
    for s in _E6_PROMPT[key]:
        assert s in text, (key, s)
    for old in _E6_PROMPT_OLD[key]:
        assert old not in text, (key, old)


# ================================================================
# B2e-bis — « automatique » retiré : puce /hybride EM (6 langues) et page Numéros les plus sortis
# ================================================================

_NUMEROS = os.path.join(_UI, "numeros-les-plus-sortis.html")
# Puce publiée (texte visible normalisé) et ancien msgstr de chaque langue (relevé sur le rendu de la copie d'AVANT)
_EBIS_BULLET = {
    "fr": "Mise à jour après chaque tirage officiel (mardi et vendredi)",
    "en": "Update after each official draw (Tuesday and Friday)",
    "es": "Actualización después de cada sorteo oficial (martes y viernes)",
    "pt": "Atualização após cada sorteio oficial (terça-feira e sexta-feira)",
    "de": "Aktualisierung nach jeder offiziellen Ziehung (Dienstag und Freitag)",
    "nl": "Bijgewerkt na elke officiële trekking (dinsdag en vrijdag)",
}
_EBIS_OLD = {
    "fr": "Synchronisation automatique après chaque tirage officiel (mardi et vendredi)",
    "en": "Automatic synchronisation after each official draw (Tuesday and Friday)",
    "es": "Sincronización automática después de cada sorteo oficial (martes y viernes)",
    "pt": "Sincronização automática após cada sorteio oficial (terça-feira e sexta-feira)",
    "de": "Automatische Synchronisation nach jeder offiziellen Ziehung (Dienstag und Freitag)",
    "nl": "Automatische synchronisatie na elke officiële trekking (dinsdag en vrijdag)",
}
_EBIS_NUMEROS_NEW = "Les données sont mises à jour après chaque tirage (lundi, mercredi, samedi)."


def _render_em_hybride(lang: str) -> str:
    from config.templates import render_template
    request = MagicMock()
    request.url.path = "/euromillions"
    request.query_params = {}
    request.cookies = {}
    request.headers = {}
    resp = render_template("em/hybride.html", request, lang=lang, page_key="hybride_page", body_class="subpage em-page",
                           include_nav_scroll=True, hero_icon="\U0001f916")
    assert resp.status_code == 200, lang
    return resp.body.decode("utf-8")


@pytest.fixture(scope="module")
def em_hybride_pages() -> dict[str, str]:
    return {lang: _render_em_hybride(lang) for lang in _LANGS}


@pytest.mark.parametrize("lang", _LANGS)
def test_lot_1_6_072_ebis_em_hybride_bullet(lang, em_hybride_pages):
    text = _norm(_visible(em_hybride_pages[lang]))
    assert text.count(_EBIS_BULLET[lang]) == 1, lang
    assert _EBIS_OLD[lang] not in text, lang
    assert "Synchronisation automatique" not in text, lang


@pytest.mark.parametrize("lang", [x for x in _LANGS if x != "fr"])
def test_lot_1_6_072_ebis_em_hybride_zero_fr(lang, em_hybride_pages):
    text = _norm(_visible(em_hybride_pages[lang]))
    assert _EBIS_BULLET["fr"] not in text, lang
    assert "Mise à jour après chaque tirage officiel" not in text, lang


def test_lot_1_6_072_ebis_em_hybride_fr_witness(em_hybride_pages):
    assert "Mise à jour après chaque tirage officiel" in _norm(_visible(em_hybride_pages["fr"]))


def test_lot_1_6_072_ebis_numeros_sentence():
    text = _qm14_text(_read(_NUMEROS))
    assert _EBIS_NUMEROS_NEW in text
    assert "mises à jour automatiquement" not in text


# ================================================================
# Bump 1.6.071 → 1.6.072 : version, date, cache-busters (fichiers servis uniquement)
# ================================================================

_CB_REF = re.compile(r"(cookie-consent|analytics)\.js(?:\?v=([0-9A-Za-z._-]+))?")


def test_lot_1_6_072_bump_version():
    from config.version import APP_VERSION, LAST_NEWS_DATE, VERSION_DATE
    assert tuple(int(p) for p in APP_VERSION.split(".")) >= (1, 6, 72)  # plancher (lot 1.6.073)
    assert VERSION_DATE >= "2026-11-16"
    assert LAST_NEWS_DATE >= "2026-11-14"  # plancher (lot 1.6.075 : LAST_NEWS_DATE 2026-11-21)


def test_lot_1_6_072_bump_cache_busters_served():
    found = {"cookie-consent": [], "analytics": []}
    for rel in _SERVED_WITH_CONSENT:
        for m in _CB_REF.finditer(_read(os.path.join(_UI, rel))):
            found[m.group(1)].append((rel, m.group(2)))
    assert len(found["cookie-consent"]) >= 21
    assert len(found["analytics"]) >= 21
    assert {v for _, v in found["cookie-consent"]} == {"8"}, found["cookie-consent"]
    assert {v for _, v in found["analytics"]} == {"5"}, found["analytics"]


@pytest.mark.parametrize("rel", _SERVED_WITH_CONSENT)
def test_lot_1_6_072_bump_analytics_v5_per_served_file(rel):
    page = _read(os.path.join(_UI, rel))
    assert page.count("analytics.js?v=5") >= 1, rel
    assert "analytics.js?v=4" not in page, rel


# ================================================================
# B2-nuit : mode nuit /hybride (questions d'exemple N1, CTA N2), --legal-link-color nuit (N3), style.css?v=16 (N4)
# ================================================================

_NUIT_HYBRIDE = {"loto": os.path.join(_UI, "hybride.html"), "em": os.path.join(_UI, "templates", "em", "hybride.html")}
_STYLE_CSS = os.path.join(_UI, "static", "style.css")
_LEGAL_CSS = os.path.join(_UI, "static", "legal.css")

_NUIT_RULES = [
    # N1
    "body.theme-night .example-box code { color: #fcd34d; }",
    # N2 a — correctif de cascade, les 2 thèmes
    ".subpage .legal-content .cta-try-links a.btn-white { color: #059669; }",
    ".subpage .legal-content .cta-try-links a.btn-outline, "
    ".subpage .legal-content .cta-try-links a.btn-outline-w { color: #fff; }",
    # N2 b — nuit
    "body.theme-night .cta-try { background: linear-gradient(135deg, #2563eb, #1d4ed8); "
    "border: 1px solid rgba(147, 197, 253, 0.4); }",
    "body.theme-night.subpage .legal-content .cta-try h3 { color: #fff; }",
    "body.theme-night.subpage .legal-content .cta-try p { color: rgba(255, 255, 255, 0.92); }",
    "body.theme-night.subpage .legal-content .cta-try-links a.btn-white { color: #1d4ed8; }",
    "body.theme-night.subpage .legal-content .cta-try-links a.btn-white:hover { background: #eff6ff; color: #1d4ed8; }",
    "body.theme-night.subpage .legal-content .cta-try-links a.btn-outline, "
    "body.theme-night.subpage .legal-content .cta-try-links a.btn-outline-w "
    "{ color: #fff; border-color: rgba(255, 255, 255, 0.6); }",
    "body.theme-night.subpage .legal-content .cta-try-links a.btn-outline:hover, "
    "body.theme-night.subpage .legal-content .cta-try-links a.btn-outline-w:hover "
    "{ color: #fff; border-color: #fff; background: transparent; }",
]

# Fichiers servis qui chargent style.css (2 références chacun : <link> + <noscript>)
_STYLE_CSS_SERVED = [
    "a-propos.html", "accueil.html", "disclaimer.html", "faq.html", "hybride.html", "loto-ia.html", "loto.html",
    "mentions-legales.html", "methodologie.html", "moteur.html", "news.html", "numeros-les-plus-sortis.html",
    "paires.html", "politique-confidentialite.html", "politique-cookies.html", "simulateur.html", "statistiques.html",
    os.path.join("templates", "em", "_base.html"),
]


def _ws(s: str) -> str:
    return " ".join(s.split())


def _inline_css(page: str) -> str:
    return _ws(" ".join(re.findall(r"<style[^>]*>(.*?)</style>", page, flags=re.S)))


def _css_block(css: str, selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


@pytest.mark.parametrize("page", sorted(_NUIT_HYBRIDE))
@pytest.mark.parametrize("rule", _NUIT_RULES)
def test_lot_1_6_072_nuit_inline_rules(page, rule):
    assert _ws(rule) in _inline_css(_read(_NUIT_HYBRIDE[page])), (page, rule)


@pytest.mark.parametrize("page", sorted(_NUIT_HYBRIDE))
def test_lot_1_6_072_nuit_day_rules_unchanged(page):
    css = _inline_css(_read(_NUIT_HYBRIDE[page]))
    assert "color: var(--primary, #667eea);" in css
    assert "background: linear-gradient(135deg, #10b981, #059669);" in css


@pytest.mark.parametrize("selector", ["body.theme-night.legal-page", "body.theme-night.subpage"])
def test_lot_1_6_072_nuit_legal_link_color_style_css(selector):
    block = _css_block(_read(_STYLE_CSS), selector)
    assert "--legal-link-color: #fbbf24;" in block
    assert "#60a5fa" not in block


def test_lot_1_6_072_nuit_legal_link_color_no_old_value():
    css = _read(_STYLE_CSS)
    assert not re.search(r"--legal-link-color:\s*#60a5fa", css)
    assert len(re.findall(r"--legal-link-color:\s*#fbbf24;", css)) == 2


def test_lot_1_6_072_nuit_legal_css_day_value_unchanged():
    root = _css_block(_read(_LEGAL_CSS), ":root")
    assert "--legal-link-color: #2563eb;" in root


@pytest.mark.parametrize("rel", _STYLE_CSS_SERVED)
def test_lot_1_6_072_nuit_style_css_v16_per_file(rel):
    page = _read(os.path.join(_UI, rel))
    assert page.count("/ui/static/style.css?v=16") == 2, rel
    assert "style.css?v=15" not in page, rel


def test_lot_1_6_072_nuit_style_css_v16_total():
    served = [os.path.join(_UI, f) for f in os.listdir(_UI) if f.endswith(".html") and f != "index.html"]
    for d, _, files in os.walk(os.path.join(_UI, "templates")):
        served += [os.path.join(d, f) for f in files if f.endswith(".html")]
    pages = [_read(p) for p in served]
    assert sum(p.count("style.css?v=16") for p in pages) == 36
    assert sum(p.count("style.css?v=15") for p in pages) == 0


@pytest.mark.parametrize("rel", _LEGACY_NOT_SERVED)
def test_lot_1_6_072_nuit_style_css_legacy_untouched(rel):
    assert "style.css?v=16" not in _read(os.path.join(_UI, rel)), rel


# ================================================================
# e4-i18n : garde-fous de non-régression (rendus HTTP des vraies routes, catalogues compilés par pybabel compile)
# Lanceur /fr … /nl (+ / avec Accept-Language) : sous-titre exact, zéro FR ; À propos EM : 2 phrases e5.2 traduites.
# Diagnostic du 15/11 : le FR vu au smoke venait des .mo locaux périmés ; code et .po corrects, rien de modifié.
# (La puce e-bis de /hybride EM est couverte par la section e-bis.)
# ================================================================

_E4I_SUB_RE = re.compile(r'<div class="grounded-sub">(.*?)</div>', re.S)
_E4I_E52_MSGIDS = (
    "LotoIA est hébergé sur <strong>Google Cloud Run</strong> avec une base de données <strong>Cloud SQL</strong>. "
    "Cette architecture garantit la disponibilité et la sécurité du site. Les données sont mises à jour après chaque "
    "tirage officiel.",
    "Toutes les données proviennent des sources officielles. Elles sont saisies manuellement après chaque tirage. "
    "Aucune donnée n'est inventée ou approximée.",
)
_E4I_MSGIDS = (_E4_NEW["fr"],) + _E4I_E52_MSGIDS
_E4I_NON_FR = [lg for lg in _LANGS if lg != "fr"]


def _e4i_catalog(lang: str):
    from babel.messages.pofile import read_po
    with open(os.path.join(_ROOT, "translations", lang, "LC_MESSAGES", "messages.po"), "rb") as f:
        return read_po(f)


@pytest.fixture(scope="module")
def e4i_pages() -> dict:
    """Rendus HTTP (TestClient, DB simulée), même mécanisme que tests/test_contraste_dark.py."""
    import importlib
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, patch

    from fastapi.testclient import TestClient

    from config.templates import EM_URLS

    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=None)
    cursor.fetchall = AsyncMock(return_value=[])
    cursor.close = AsyncMock()

    @asynccontextmanager
    async def _conn():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn

    env = {"DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb", "EM_PUBLIC_ACCESS": "true"}
    pages = {}
    with patch.dict(os.environ, env), \
            patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None), \
            patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None):
        import middleware.em_access_control as em_ac
        importlib.reload(em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        with patch("db_cloudsql.get_connection", _conn):
            for lang in _LANGS:
                pages[("launcher", lang)] = client.get(f"/{lang}")
                pages[("root", lang)] = client.get("/", headers={"accept-language": lang})
                pages[("apropos", lang)] = client.get(EM_URLS[lang]["a_propos"])
    return pages


@pytest.mark.parametrize("route", ["launcher", "root"])
@pytest.mark.parametrize("lang", _LANGS)
def test_lot_1_6_072_e4i_launcher_subtitle_exact(lang, route, e4i_pages):
    resp = e4i_pages[(route, lang)]
    assert resp.status_code == 200, (route, lang)
    subs = _E4I_SUB_RE.findall(resp.text)
    assert len(subs) == 1, (route, lang)
    assert _norm(_visible(subs[0])) == _E4_NEW[lang], (route, lang)


@pytest.mark.parametrize("lang", _E4I_NON_FR)
def test_lot_1_6_072_e4i_launcher_zero_fr(lang, e4i_pages):
    for route in ("launcher", "root"):
        text = _norm(_visible(e4i_pages[(route, lang)].text))
        assert _E4_NEW["fr"] not in text, (route, lang)


@pytest.mark.parametrize("lang", _E4I_NON_FR)
def test_lot_1_6_072_e4i_em_apropos_not_fr(lang, e4i_pages):
    resp = e4i_pages[("apropos", lang)]
    assert resp.status_code == 200, lang
    text = _norm(_visible(resp.text))
    catalog = _e4i_catalog(lang)
    for msgid in _E4I_E52_MSGIDS:
        assert _norm(_visible(msgid)) not in text, (lang, msgid[:40])
        assert _norm(_visible(catalog.get(msgid).string)) in text, (lang, msgid[:40])


@pytest.mark.parametrize("msgid", _E4I_MSGIDS, ids=["e4", "e52_hebergement", "e52_donnees"])
@pytest.mark.parametrize("lang", _E4I_NON_FR)
def test_lot_1_6_072_e4i_catalog_entries(lang, msgid):
    entry = _e4i_catalog(lang).get(msgid)
    assert entry is not None, (lang, msgid[:40])
    assert not entry.fuzzy, (lang, msgid[:40])
    assert entry.string and entry.string != msgid, (lang, msgid[:40])


def test_lot_1_6_072_e4i_fr_witness(e4i_pages):
    assert _norm(_visible(_E4I_SUB_RE.findall(e4i_pages[("launcher", "fr")].text)[0])) == _E4_NEW["fr"]
    text = _norm(_visible(e4i_pages[("apropos", "fr")].text))
    for msgid in _E4I_E52_MSGIDS:
        assert _norm(_visible(msgid)) in text, msgid[:40]
