/**
 * ═══════════════════════════════════════════════════════════════════════════════
 * LOTOIA ANALYTICS MODULE v2.6.0 - PRODUCT ANALYTICS PREMIUM
 * ═══════════════════════════════════════════════════════════════════════════════
 *
 * Infrastructure analytics professionnelle pour SaaS LotoIA
 * - GA4 en Consent Mode « de base » (1.6.072) : rien n'est chargé sans consentement
 * - GA4 chargé uniquement après acceptation de la mesure d'audience
 * - Umami Cloud (sans cookie) géré hors de ce module, inchangé
 * - Product Analytics Engine (v2.5+) pour tracking métier
 * - Events produit (moteur LotoIA)
 * - Events UX (parcours utilisateur)
 * - Events business (sponsors / monetisation)
 * - Architecture scalable multi-moteurs / multi-pays
 *
 * @author LotoIA Team
 * @version 2.6.0
 * @license Proprietary
 *
 * CONSENT MODE « DE BASE » (1.6.072, CNIL/RGPD):
 * ┌─────────────────────────────────────────────────────────────────────────────┐
 * │ Tant que la mesure d'audience n'est pas acceptée (choices.analytics true) : │
 * │   aucun script gtag.js, pas de window.gtag, pas de window.dataLayer,        │
 * │   aucun event GA4 (les events émis avant le consentement sont jetés).       │
 * │ 0. isExcluded() - owner / bot IA / appareil marqué : testé AVANT le         │
 * │    consentement, sur tous les chemins → GA4 jamais chargé.                  │
 * │ 1. loadGA4IfConsented('boot') - acceptant connu : chargement au démarrage  │
 * │    → consent default granted (ad_* denied) + script + config + 1 page_view │
 * │ 2. loadGA4IfConsented('consent') - acceptation en cours de page            │
 * │    → même chargement + 1 page_view de la page où l'on accepte              │
 * │    → ré-acceptation après retrait : ga-disable false + consent update     │
 * │      granted, pas de réinjection, 1 page_view                              │
 * │ 3. Retrait / refus : consent update denied + ga-disable true + purge des   │
 * │    cookies _ga / _ga_* (aussi au démarrage si un _ga* hérité subsiste)     │
 * └─────────────────────────────────────────────────────────────────────────────┘
 *
 * DEBUG (owner uniquement : __OWNER__ ou appareil marqué lotoia_internal) :
 *        localStorage.setItem('debug_ga4', '1') pour logs basiques
 *        localStorage.setItem('debug_ga4', '2') pour logs détaillés
 *
 * USAGE:
 * 1. Inclure ce script dans le <head> (avant cookie-consent.js)
 * 2. Rien n'est chargé tant que le visiteur n'a pas accepté la mesure d'audience
 * 3. Après acceptation (Tout accepter, ou Personnaliser avec la case cochée), GA4 se charge
 * 4. Utiliser window.LotoIAAnalytics.track() pour les events custom
 *
 * PRODUCT ANALYTICS (v2.5+):
 * ┌─────────────────────────────────────────────────────────────────────────────┐
 * │ // Définir le contexte métier (optionnel, une fois par page)               │
 * │ LotoIAAnalytics.product.setFeature('simulateur');                          │
 * │ LotoIAAnalytics.product.setEngine('hybride');                              │
 * │                                                                             │
 * │ // Tracker une action métier                                                │
 * │ LotoIAAnalytics.product.track('lotoia_generate_grid', { count: 3 });       │
 * │ LotoIAAnalytics.product.track('lotoia_run_engine', { mode: 'balanced' });  │
 * │                                                                             │
 * │ // Tracker sponsors                                                         │
 * │ LotoIAAnalytics.product.sponsorView('sidebar_top');                        │
 * │ LotoIAAnalytics.product.sponsorClick('sidebar_top');                       │
 * └─────────────────────────────────────────────────────────────────────────────┘
 *
 * ═══════════════════════════════════════════════════════════════════════════════
 */

(function(window, document) {
    'use strict';

    // ═══════════════════════════════════════════════════════════════════════════
    // CONFIGURATION GLOBALE
    // ═══════════════════════════════════════════════════════════════════════════

    const CONFIG = {
        // GA4 Measurement ID (production)
        GA4_ID: 'G-YYJ5LD1ZT3',

        // Mode debug (console logs)
        debug: false,

        // Version du schema d'events
        schemaVersion: '2.0',

        // Configuration moteur par defaut
        defaultEngine: 'loto_fr',
        defaultAlgorithm: 'HYBRIDE',

        // Delai avant envoi pageview (ms)
        pageviewDelay: 100,

        // Activer le tracking automatique du scroll
        trackScroll: true,
        scrollThresholds: [25, 50, 75, 90, 100],

        // Futurs providers (Matomo, Plausible)
        providers: {
            ga4: { enabled: true, id: 'G-YYJ5LD1ZT3' },
            matomo: { enabled: false, url: null, siteId: null },
            plausible: { enabled: false, domain: null }
        }
    };

    // ═══════════════════════════════════════════════════════════════════════════
    // ETAT INTERNE
    // ═══════════════════════════════════════════════════════════════════════════

    const state = {
        initialized: false,
        consentGiven: false,
        gtagBooted: false,            // 1.6.072 : chargement GA4 commencé (après consentement uniquement)
        baselineReady: false,         // Flag config + page_view partis (anti-double)
        isEnhanced: false,            // 1.6.072 : consentement mesure d'audience actif sur la page
        gtagLoadFailed: false,        // Flag adblock/network error (gtag.js)
        gtagScriptReady: false,       // Flag gtag.js script loaded and ready
        scrollTrackingEnabled: false, // Flag anti-double scroll listener
        sessionId: null,
        pageLoadTime: Date.now(),
        scrollTracked: {},
        eventsQueue: [],
        pageViewCategory: 'baseline', // 1.6.072 : baseline (boot) | consent_granted (acceptation en cours de page)
        pageViewSent: false,          // 1.6.072 : page_view unique de la page, réarmé au retrait

        // Product Analytics (v2.5+)
        productContext: {
            engine: 'unknown',        // hybride | random | manual | unknown
            feature: 'unknown'        // simulateur | stats | home | faq | etc.
        },
        productBuffer: [],            // Buffer d'events produit
        productBufferTimer: null,     // Timer flush buffer
        productWarnShown: false,      // Flag warning gtag bloqué (unique)

        // Sponsor analytics v2.5.2 — Engagement state & monetisation
        engagementState: 'idle',      // idle | exploration | analysis | decision | exit
        lastProductActionTime: 0      // Timestamp dernière action produit (pour impression_type)
    };

    // ═══════════════════════════════════════════════════════════════════════════
    // UTILITAIRES
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Niveau de debug (0=silence, 1=basique, 2=détaillé)
     * Configurable via: localStorage.setItem('debug_ga4', '1')
     * 1.6.072 : effectif uniquement pour l'owner (__OWNER__ ou appareil marqué), sinon 0.
     */
    function getDebugLevel() {
        if (!isDebugAllowed()) return 0;
        try {
            const level = parseInt(localStorage.getItem('debug_ga4') || '0', 10);
            return isNaN(level) ? 0 : Math.min(Math.max(level, 0), 2);
        } catch (e) {
            return 0;
        }
    }

    /**
     * Logger conditionnel (mode debug via localStorage)
     * @param {string} message - Message à logger
     * @param {string} type - Type: info, success, warning, error
     * @param {*} data - Données additionnelles (niveau 2 uniquement)
     * @param {number} minLevel - Niveau minimum requis (1 ou 2)
     */
    function log(message, type = 'info', data = null, minLevel = 1) {
        const debugLevel = getDebugLevel();
        if (debugLevel < minLevel) return;

        const prefix = '[LotoIA GA4]';
        const styles = {
            info: 'color: #2196F3',
            success: 'color: #4CAF50',
            warning: 'color: #FF9800',
            error: 'color: #F44336'
        };

        if (data && debugLevel >= 2) {
            console.log(`%c${prefix} ${message}`, styles[type] || styles.info, data);
        } else {
            console.log(`%c${prefix} ${message}`, styles[type] || styles.info);
        }
    }

    /**
     * Genere ou recupere l'ID de session
     */
    function getSessionId() {
        if (state.sessionId) return state.sessionId;

        let sessionId = sessionStorage.getItem('lotoia_session');
        if (!sessionId) {
            sessionId = 'ses_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
            sessionStorage.setItem('lotoia_session', sessionId);
        }
        state.sessionId = sessionId;
        return sessionId;
    }

    /**
     * Detecte la page courante
     */
    function getCurrentPage() {
        const path = window.location.pathname;

        if (path.includes('index.html') || path === '/' || path === '/ui/' || path === '/ui') {
            return 'index';
        }
        if (path.includes('loto.html')) return 'loto';
        if (path.includes('news.html')) return 'news';
        if (path.includes('simulateur.html')) return 'simulateur';
        if (path.includes('statistiques.html')) return 'statistiques';
        if (path.includes('faq.html')) return 'faq';
        if (path.includes('historique.html')) return 'historique';
        if (path.includes('methodologie.html')) return 'methodologie';
        if (path.includes('launcher.html')) return 'launcher';

        // Pages legales
        if (path.includes('mentions-legales')) return 'mentions_legales';
        if (path.includes('politique-confidentialite')) return 'confidentialite';
        if (path.includes('politique-cookies')) return 'cookies';
        if (path.includes('disclaimer')) return 'disclaimer';

        return 'unknown';
    }

    /**
     * Deduit le code produit depuis le contexte de la page.
     * Logique identique a tracker.js getProductCode().
     * @param {Object} params - Params de l'event (peut contenir product_code explicite)
     * @returns {string} Code produit (ex: LOTO_FR, EM_EN, LOTO_FR_A)
     */
    function getProductCode(params) {
        if (params && params.product_code) return params.product_code;
        const path = window.location.pathname;
        const lang = (window.LotoIA_lang || document.documentElement.lang || 'fr').substring(0, 2).toUpperCase();
        if (path.includes('/euromillions')) return 'EM_' + lang;
        return 'LOTO_FR';
    }

    /**
     * Recupere les metadata de la page
     */
    function getPageMetadata() {
        return {
            page: getCurrentPage(),
            path: window.location.pathname,
            referrer: document.referrer || 'direct',
            title: document.title,
            session_id: getSessionId(),
            timestamp: Date.now(),
            schema_version: CONFIG.schemaVersion
        };
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // MARQUEUR APPAREIL OWNER + CONSENTEMENT STOCKÉ (1.6.054)
    // ═══════════════════════════════════════════════════════════════════════════

    // 1.6.054 — Marqueur d'appareil owner (posé au 1er passage avec __OWNER__)
    const INTERNAL_DEVICE_KEY = 'lotoia_internal';

    // 1.6.072 — Version du consentement attendue. Doit rester égale à CONFIG.consentVersion
    // de cookie-consent.js : la même règle de version est appliquée par les deux lecteurs.
    const CONSENT_VERSION = '2.0';

    function isInternalDevice() {
        try { return localStorage.getItem(INTERNAL_DEVICE_KEY) === '1'; } catch (e) { return false; }
    }

    // 1.6.072 — Exclusion owner / bot IA / appareil marqué. Testée AVANT toute lecture du consentement,
    // sur tous les chemins (boot, onConsentChange, pageshow) : un owner qui accepte ne charge jamais GA4.
    function isExcluded() {
        return !!(window.__OWNER__ || window.__IS_AI_BOT__ || isInternalDevice());
    }

    // 1.6.072 — Debug GA4 réservé à l'owner (aucun log console pour les visiteurs).
    function isDebugAllowed() {
        return !!(window.__OWNER__ || isInternalDevice());
    }

    // 1.6.054 — Consentement analytics stocké (même règle d'expiration que cookie-consent.js).
    // 1.6.072 — Même règle de version : un consentement d'une autre version (dont '1.0') vaut absence.
    // Lu au boot : cookie-consent.js (defer) n'est pas encore chargé à ce stade.
    function readStoredAnalyticsConsent() {
        try {
            const stored = localStorage.getItem('lotoia_cookie_consent');
            if (!stored) return false;
            const data = JSON.parse(stored);
            if (!data || data.version !== CONSENT_VERSION) return false;
            if (data.expires && new Date(data.expires) < new Date()) return false;
            return !!(data.choices && data.choices.analytics === true);
        } catch (e) {
            return false;
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // COOKIES GA4 : PURGE (1.6.072)
    // ═══════════════════════════════════════════════════════════════════════════

    // Cookies posés par gtag.js : _ga et _ga_<conteneur> (ex. _ga_YYJ5LD1ZT3)
    const GA_COOKIE_NAME_RE = /^_ga(_[A-Za-z0-9]+)?$/;

    // gtag pose ses cookies sur le domaine racine (cookie_domain 'auto' → .lotoia.fr) ;
    // la variante sans domain couvre un cookie hôte (www., staging).
    const GA_COOKIE_DOMAINS = ['; domain=.lotoia.fr', '; domain=lotoia.fr', ''];

    // Clé officielle de désactivation gtag pour la propriété (bloque tout hit de la page)
    const GA_DISABLE_KEY = 'ga-disable-' + CONFIG.GA4_ID;

    /**
     * Liste les noms de cookies _ga / _ga_* visibles par la page.
     * @returns {string[]}
     */
    function listGaCookies() {
        try {
            return document.cookie
                .split(';')
                .map(c => c.split('=')[0].trim())
                .filter(name => GA_COOKIE_NAME_RE.test(name));
        } catch (e) {
            return [];
        }
    }

    /**
     * Efface les cookies _ga / _ga_* (Max-Age=0, path=/, 3 variantes de domaine),
     * puis relit document.cookie pour vérifier l'effacement réel.
     * Échec : console.warn uniquement si le debug owner est actif (aucune télémétrie).
     * @returns {boolean} true si plus aucun _ga* n'est visible
     */
    function purgeGaCookies() {
        const names = listGaCookies();
        if (names.length === 0) return true;

        names.forEach(name => {
            GA_COOKIE_DOMAINS.forEach(domain => {
                try {
                    document.cookie = name + '=; Max-Age=0; path=/' + domain;
                } catch (e) { /* ignore */ }
            });
        });

        const left = listGaCookies();
        if (left.length > 0) {
            if (getDebugLevel() >= 1) {
                console.warn('[LotoIA GA4] _ga cookies still present after purge: ' + left.join(', '));
            }
            return false;
        }
        log('GA cookies purged: ' + names.join(', '), 'info');
        return true;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // CHARGEMENT GA4 APRÈS CONSENTEMENT UNIQUEMENT (1.6.072)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Charge GA4 si — et seulement si — le visiteur n'est pas exclu ET a accepté la mesure d'audience
     * (« Tout accepter » ou « Personnaliser » avec la case cochée : choices.analytics === true).
     * Seul endroit du module qui crée window.dataLayer / window.gtag et injecte gtag.js.
     *
     * @param {string} origin - 'boot' (acceptant connu, au démarrage) | 'consent' (acceptation en cours de page)
     * @returns {boolean} true si GA4 est (ou reste) actif
     */
    function loadGA4IfConsented(origin) {
        // 1. Exclusion AVANT toute lecture du consentement
        if (isExcluded()) {
            log('GA4 not loaded (excluded: owner / AI bot / internal device)', 'info');
            return false;
        }

        // 2. Consentement mesure d'audience (au boot, cookie-consent.js n'est pas encore chargé)
        const consented = origin === 'boot' ? readStoredAnalyticsConsent() : hasAnalyticsConsent();
        if (!consented) {
            log('GA4 not loaded (no analytics consent)', 'info');
            return false;
        }

        // 3. Déjà chargé : anti-double, ou ré-acceptation après un retrait dans la même page
        if (state.gtagBooted) {
            if (state.isEnhanced) return true;
            reenableGA4();
            return true;
        }

        // 4. Premier chargement
        state.gtagBooted = true;
        state.isEnhanced = true;
        state.consentGiven = true;
        state.initialized = true; // Compatibilité avec l'ancien état
        state.pageViewCategory = origin === 'boot' ? 'baseline' : 'consent_granted';

        try {
            window[GA_DISABLE_KEY] = false;
            window.dataLayer = window.dataLayer || [];
            window.gtag = function() {
                dataLayer.push(arguments);
            };

            // Consent Mode : analytics accepté, publicité toujours refusée (pas de remarketing)
            gtag('consent', 'default', {
                'ad_storage': 'denied',
                'analytics_storage': 'granted',
                'ad_user_data': 'denied',
                'ad_personalization': 'denied'
            });

            const script = document.createElement('script');
            script.async = true;
            script.src = 'https://www.googletagmanager.com/gtag/js?id=' + CONFIG.GA4_ID;
            script.onload = function() {
                state.gtagScriptReady = true;
                log('gtag.js script loaded', 'success', null, 2);
            };
            script.onerror = function() {
                state.gtagLoadFailed = true;
                state.gtagScriptReady = true; // Marquer ready même en erreur pour débloquer
                console.warn('[LotoIA GA4] gtag.js blocked (adblock/network)');
            };
            document.head.appendChild(script);
            log(`GA4 loading after consent (origin: ${origin})`, 'success');
        } catch (e) {
            state.gtagLoadFailed = true;
            state.gtagScriptReady = true;
            console.warn('[LotoIA GA4] Load failed:', e.message);
            return false;
        }

        // 5. Config + page_view unique (asynchrone : attend gtag.js, 3 s max)
        baselineInit();
        return true;
    }

    /**
     * Ré-acceptation dans la même page après un retrait : pas de réinjection du script.
     * ga-disable remis à false, consent update granted (ad_* denied), 1 page_view consent_granted.
     */
    function reenableGA4() {
        window[GA_DISABLE_KEY] = false;
        if (typeof window.gtag === 'function') {
            gtag('consent', 'update', {
                'analytics_storage': 'granted',
                'ad_storage': 'denied',
                'ad_user_data': 'denied',
                'ad_personalization': 'denied'
            });
        }
        state.isEnhanced = true;
        state.consentGiven = true;
        state.pageViewCategory = 'consent_granted';

        // Config déjà partie : page_view maintenant ; sinon baselineInit() l'enverra (flag non consommé)
        if (state.baselineReady) {
            sendPageViewOnce();
            sendConsentGrantedEvent();
        }
        log('GA4 re-enabled (consent granted again, no script reinjection)', 'success');
    }

    /**
     * Retrait / refus : consent update denied + ga-disable + réarmement du page_view unique.
     * Les events en file ou en tampon (non envoyés) sont jetés.
     */
    function disableGA4() {
        if (state.gtagBooted && typeof window.gtag === 'function') {
            gtag('consent', 'update', {
                'analytics_storage': 'denied',
                'ad_storage': 'denied',
                'ad_user_data': 'denied',
                'ad_personalization': 'denied'
            });
            window[GA_DISABLE_KEY] = true;
            log('Consent revoked → analytics_storage: denied + ga-disable', 'warning');
        }
        state.isEnhanced = false;
        state.consentGiven = false;
        state.pageViewSent = false; // réarmé : une ré-acceptation renverra 1 page_view
        state.eventsQueue = [];
        state.productBuffer = [];
    }

    /**
     * 1.6.072 (B1 bis) — Resynchronise un retrait fait ailleurs (autre page puis retour bfcache, autre onglet).
     * Source fraîche uniquement : le consentement stocké (localStorage), jamais l'état mémoire de CookieConsent
     * (périmé sur une page restaurée depuis le bfcache).
     * Ne propage que le retrait : aucun chargement de GA4 ici.
     * @returns {boolean} true si GA4 a été désactivé
     */
    function resyncConsentFromStorage() {
        if (!isExcluded() && state.gtagBooted && state.isEnhanced && !readStoredAnalyticsConsent()) {
            log('Consent withdrawn elsewhere (stored choice) → GA4 disabled, _ga cookies purged', 'info');
            disableGA4();
            purgeGaCookies();
            return true;
        }
        return false;
    }

    // ══════════════════════════════════════════════════════════════════════════
    // DÉMARRAGE - Exécuté maintenant
    // ══════════════════════════════════════════════════════════════════════════

    // Owner IP filter (window.__OWNER__) + V123 AI bot filter (window.__IS_AI_BOT__)
    // Injected by OwnerFilterMiddleware in main.py (Extension A anti-pollution)
    // 1.6.054 : marqueur d'appareil persistant → GA4 jamais chargé ensuite sur cet appareil,
    // quel que soit le réseau (4G, IP inconnue). Pas de script, pas de dataLayer, aucun hit.
    if (window.__OWNER__) {
        try { localStorage.setItem(INTERNAL_DEVICE_KEY, '1'); } catch (e) { /* ignore */ }
    }

    // 1.6.072 : décision négative, expirée, absente ou d'une autre version + _ga* hérité → purge
    if (!readStoredAnalyticsConsent() && listGaCookies().length > 0) {
        purgeGaCookies();
    }

    // 1.6.072 : acceptant connu → chargement immédiat ; sinon rien (ni script, ni gtag, ni dataLayer)
    loadGA4IfConsented('boot');

    // ══════════════════════════════════════════════════════════════════════════
    // ATTENTE GTAG.JS READY
    // ══════════════════════════════════════════════════════════════════════════

    /**
     * Attend que gtag.js soit chargé (max 3s, puis continue en dégradé)
     * @returns {Promise<boolean>} true si gtag.js ready, false si timeout/erreur
     */
    function waitForGtagReady() {
        return new Promise((resolve) => {
            // Déjà prêt ?
            if (state.gtagScriptReady) {
                resolve(!state.gtagLoadFailed);
                return;
            }

            // Polling avec timeout
            const maxWait = 3000; // 3 secondes max
            const interval = 50;  // Check toutes les 50ms
            let elapsed = 0;

            const check = setInterval(() => {
                elapsed += interval;

                if (state.gtagScriptReady) {
                    clearInterval(check);
                    resolve(!state.gtagLoadFailed);
                    return;
                }

                if (elapsed >= maxWait) {
                    clearInterval(check);
                    log('gtag.js load timeout - continuing in degraded mode', 'warning');
                    resolve(false);
                }
            }, interval);
        });
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // GA4 CORE
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Envoie un page_view GA4 (1.6.054 : baseline, acceptation en cours de page, retour bfcache)
     * @param {string} category - baseline | consent_granted | bfcache_restore
     */
    function sendPageView(category) {
        gtag('event', 'page_view', {
            'page_title': document.title,
            'page_location': window.location.href,
            'page_path': window.location.pathname,
            'event_category': category,
            'non_interaction': true
        });
    }

    /**
     * 1.6.072 : page_view unique de la page (anti-doublon par flag, réarmé au retrait).
     * Catégorie : baseline (acceptant connu au boot) | consent_granted (acceptation en cours de page).
     */
    function sendPageViewOnce() {
        if (state.pageViewSent) return;
        state.pageViewSent = true;
        sendPageView(state.pageViewCategory);
    }

    /**
     * Event consent_granted (comportement 1.6.054 conservé : émis à chaque activation de GA4).
     */
    function sendConsentGrantedEvent() {
        gtag('event', 'consent_granted', {
            'event_category': 'consent',
            'analytics_storage': 'granted',
            'timestamp': Date.now()
        });
    }

    /**
     * ═══════════════════════════════════════════════════════════════════════════
     * BASELINE INIT - appelé uniquement par loadGA4IfConsented() (1.6.072)
     * ═══════════════════════════════════════════════════════════════════════════
     * Configure GA4 et envoie 1 page_view (consentement déjà accepté).
     * ATTEND que gtag.js soit chargé pour garantir le traitement correct.
     *
     * @returns {Promise<boolean>} true si baseline OK, false si bloqué
     */
    async function baselineInit() {
        // Anti-double init
        if (state.baselineReady) {
            log('Baseline already initialized', 'warning');
            return true;
        }

        // 1.6.072 : jamais sans chargement consenti (garde-fou)
        if (!state.gtagBooted || !window.gtag) {
            log('gtag not available (no consent / load failed)', 'error');
            return false;
        }

        // ATTENDRE que gtag.js soit réellement chargé (max 3s)
        const gtagReady = await waitForGtagReady();

        if (!gtagReady) {
            log('gtag.js not ready - baseline in degraded mode', 'warning');
            // On continue quand même pour éviter de bloquer le reste
        }

        try {
            // 1. Timestamp initial
            gtag('js', new Date());

            // 2. Configuration GA4 privacy-first (SANS page_view auto)
            gtag('config', CONFIG.GA4_ID, {
                // CRITIQUE: Désactiver le page_view automatique
                'send_page_view': false,

                // Anonymisation IP (requis RGPD)
                'anonymize_ip': true,

                // Désactiver tous les signaux publicitaires
                'allow_google_signals': false,
                'allow_ad_personalization_signals': false,

                // Désactiver le suivi automatique
                'form_submit': false,
                'file_download': false,

                // 1.6.072 : durée des cookies _ga = 395 jours (alignée sur la durée du consentement)
                'cookie_expires': 34128000,

                // Custom dimensions
                'custom_map': {
                    'dimension1': 'engine',
                    'dimension2': 'algorithm',
                    'dimension3': 'session_id'
                }
            });

            // 3. Marquer baseline ready AVANT d'envoyer le page_view (anti-double)
            // 1.6.054 : DOIT précéder processEventsQueue() / flushProductBuffer() ci-dessous
            // (gardes !baselineReady dans sendGA4Event et flushProductBuffer)
            state.baselineReady = true;

            // 1.6.072 : retrait survenu pendant le chargement → ni page_view ni events
            if (!state.isEnhanced) {
                log('Consent withdrawn during load → no page_view', 'info');
                return true;
            }

            // 4. Envoyer UN SEUL page_view (baseline au boot, consent_granted en cours de page)
            sendPageViewOnce();

            // 5. 1.6.054 : vider dans l'ordre les events mis en file avant config + page_view
            processEventsQueue();
            flushProductBuffer();

            // 6. Event consent_granted + tracking avancé (ex-enableEnhanced)
            sendConsentGrantedEvent();
            setupScrollTracking();

            log(`GA4 page_view sent (${state.pageViewCategory}, gtag_ready: ${gtagReady})`, 'success');

            return true;

        } catch (error) {
            log('Baseline init failed: ' + error.message, 'error');
            return false;
        }
    }

    /**
     * Envoie un event GA4
     * Gère gracieusement l'absence de gtag (adblock)
     */
    function sendGA4Event(eventName, params = {}) {
        // 1.6.072 (Q8) : avant consentement (ou après retrait) → event jeté, ni file ni tampon
        if (!state.gtagBooted || !state.isEnhanced) {
            log(`Event dropped (no analytics consent): ${eventName}`, 'info', params, 2);
            return false;
        }

        // Si gtag bloqué définitivement, no-op silencieux
        if (state.gtagLoadFailed) {
            log(`Event dropped (gtag blocked): ${eventName}`, 'warning', params, 2);
            return false;
        }

        // 1.6.054 : file d'attente tant que config + page_view baseline ne sont pas partis
        // (aucun event avant gtag('config') ni avant le page_view → pas de session sans page d'entrée)
        // 1.6.072 : ne couvre que le délai entre l'injection du script (après consentement) et baselineReady
        if (!state.baselineReady || !window.gtag) {
            log(`Event queued (baseline not ready): ${eventName}`, 'warning', params, 2);
            if (state.eventsQueue.length >= 50) state.eventsQueue.shift();
            state.eventsQueue.push({ eventName, params, timestamp: Date.now() });
            return false;
        }

        // Enrichir avec metadata standard
        const enrichedParams = {
            ...params,
            session_id: getSessionId(),
            page: getCurrentPage(),
            engine: params.engine || CONFIG.defaultEngine,
            product_code: getProductCode(params),
            timestamp: Date.now()
        };

        gtag('event', eventName, enrichedParams);
        log(`Event sent: ${eventName}`, 'success', enrichedParams, 2);
        return true;
    }

    /**
     * Traite la queue d'events en attente
     */
    function processEventsQueue() {
        if (state.eventsQueue.length === 0) return;

        // 1.6.054 : gtag bloqué (owner, appareil marqué, bot IA, bloqueur) → vider sans envoyer
        if (state.gtagLoadFailed) {
            state.eventsQueue = [];
            return;
        }

        log(`Processing ${state.eventsQueue.length} queued events`, 'info');

        const queue = [...state.eventsQueue];
        state.eventsQueue = [];

        queue.forEach(item => {
            sendGA4Event(item.eventName, item.params);
        });
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ENGAGEMENT STATE & SPONSOR METRICS (v2.5.2)
    // ═══════════════════════════════════════════════════════════════════════════
    // État d'engagement utilisateur pour enrichissement sponsor CTR/CPC/CPM.
    // - engagement_state : contexte intentionnel (idle→exploration→analysis→decision→exit)
    // - click_value : CPC pondéré par intention (decision=3, analysis=2, autre=1)
    // - impression_type : CPM actif (action produit < 10s) / passif (aucune action récente)

    /**
     * Met à jour l'état d'engagement utilisateur.
     * Appelé automatiquement par les events produit (generate_grid, simulate_grid, etc.)
     * @param {string} newState - idle | exploration | analysis | decision | exit
     */
    function updateEngagementState(newState) {
        const valid = ['idle', 'exploration', 'analysis', 'decision', 'exit'];
        if (valid.includes(newState)) {
            state.engagementState = newState;
            log('Engagement state → ' + newState, 'info', null, 2);
        }
    }

    /**
     * Enregistre le timestamp de la dernière action produit.
     * Utilisé pour déterminer impression_type (active si < 10s).
     */
    function recordProductAction() {
        state.lastProductActionTime = Date.now();
    }

    /**
     * Retourne le click_value pondéré selon l'engagement_state.
     * Permet un CPC différencié par intention utilisateur.
     * @returns {number} 1 (exploration/autre) | 2 (analysis) | 3 (decision)
     */
    function getClickValue() {
        switch (state.engagementState) {
            case 'decision': return 3;
            case 'analysis': return 2;
            case 'exploration': return 1;
            default: return 1;
        }
    }

    /**
     * Retourne le type d'impression (active/passive).
     * active = une action produit a eu lieu dans les 10 dernières secondes.
     * passive = aucune action récente → impression moins qualifiée.
     * @returns {string} 'active' | 'passive'
     */
    function getImpressionType() {
        if (state.lastProductActionTime === 0) return 'passive';
        return (Date.now() - state.lastProductActionTime) <= 10000 ? 'active' : 'passive';
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // EVENTS PRODUIT (CORE LOTOIA)
    // ═══════════════════════════════════════════════════════════════════════════

    const ProductEvents = {
        /**
         * Track generation de grilles
         * @param {Object} params
         * @param {number} params.count - Nombre de grilles generees
         * @param {string} params.mode - Mode de generation (balanced, conservative, recent)
         * @param {string} params.engine - Moteur utilise
         * @param {string} params.algorithm - Algorithme utilise
         * @param {string} params.targetDate - Date cible du tirage
         */
        generateGrid: function(params = {}) {
            updateEngagementState('exploration');
            recordProductAction();
            sendGA4Event('generate_grid', {
                event_category: 'engagement',
                engine: params.engine || CONFIG.defaultEngine,
                algorithm: params.algorithm || CONFIG.defaultAlgorithm,
                source: 'ui',
                grid_count: params.count || 1,
                generation_mode: params.mode || 'balanced',
                target_date: params.targetDate || null,
                value: params.count || 1
            });
        },

        /**
         * Track rafraichissement du moteur
         */
        refreshEngine: function(params = {}) {
            recordProductAction();
            sendGA4Event('refresh_engine', {
                event_category: 'engagement',
                engine: params.engine || CONFIG.defaultEngine,
                refresh_type: params.type || 'manual'
            });
        },

        /**
         * Track consultation des resultats
         */
        viewResults: function(params = {}) {
            updateEngagementState('analysis');
            recordProductAction();
            sendGA4Event('view_results', {
                event_category: 'engagement',
                engine: params.engine || CONFIG.defaultEngine,
                result_type: params.type || 'grids',
                grid_count: params.count || 0
            });
        },

        /**
         * Track appel API
         */
        apiCall: function(params = {}) {
            sendGA4Event('api_call', {
                event_category: 'technical',
                endpoint: params.endpoint || 'unknown',
                method: params.method || 'GET',
                status: params.status || 'success',
                response_time_ms: params.responseTime || 0
            });
        },

        /**
         * Track simulation de grille personnalisee
         */
        simulateGrid: function(params = {}) {
            updateEngagementState('analysis');
            recordProductAction();
            sendGA4Event('simulate_grid', {
                event_category: 'engagement',
                engine: params.engine || CONFIG.defaultEngine,
                grid_score: params.score || 0,
                numbers: params.numbers ? params.numbers.join('-') : null
            });
        },

        /**
         * Track consultation statistiques
         */
        viewStats: function(params = {}) {
            recordProductAction();
            sendGA4Event('view_stats', {
                event_category: 'content',
                stats_section: params.section || 'general',
                engine: params.engine || CONFIG.defaultEngine
            });
        },

        /**
         * Track recherche historique
         */
        searchHistory: function(params = {}) {
            recordProductAction();
            sendGA4Event('search_history', {
                event_category: 'search',
                search_date: params.date || null,
                result_found: params.found || false
            });
        },

        /**
         * Track copie de grille
         */
        copyGrid: function(params = {}) {
            updateEngagementState('decision');
            recordProductAction();
            sendGA4Event('copy_grid', {
                event_category: 'engagement',
                grid_id: params.gridId || 'unknown',
                grid_number: params.gridNumber || 1
            });
        }
    };

    // ═══════════════════════════════════════════════════════════════════════════
    // EVENTS UX (PARCOURS UTILISATEUR)
    // ═══════════════════════════════════════════════════════════════════════════

    const UXEvents = {
        /**
         * Track page view
         */
        pageView: function(pageName = null) {
            const page = pageName || getCurrentPage();

            sendGA4Event('page_view_lotoia', {
                event_category: 'navigation',
                page: page,
                page_title: document.title,
                page_path: window.location.pathname,
                referrer: document.referrer || 'direct'
            });
        },

        /**
         * Track scroll depth
         */
        scrollDepth: function(percentage) {
            // Eviter les doublons
            if (state.scrollTracked[percentage]) return;
            state.scrollTracked[percentage] = true;

            sendGA4Event('scroll_depth', {
                event_category: 'engagement',
                page: getCurrentPage(),
                depth_percentage: percentage,
                depth_threshold: percentage
            });
        },

        /**
         * Track debut de session
         */
        sessionStart: function() {
            sendGA4Event('session_start_lotoia', {
                event_category: 'session',
                session_id: getSessionId(),
                entry_page: getCurrentPage(),
                referrer: document.referrer || 'direct'
            });
        },

        /**
         * 1.6.054 : no-op conservé pour compat API publique (LotoIAAnalytics.ux.sessionEnd).
         * L'event de fin de session, émis sur visibilitychange/beforeunload sans contrôle
         * d'ancienneté, ouvrait des sessions GA4 orphelines (Unassigned) — supprimé.
         */
        sessionEnd: function() {},

        /**
         * Track changement de theme
         */
        themeChange: function(theme) {
            sendGA4Event('theme_change', {
                event_category: 'preferences',
                theme: theme,
                page: getCurrentPage()
            });
        },

        /**
         * Track ouverture FAQ
         */
        faqOpen: function(question) {
            sendGA4Event('faq_open', {
                event_category: 'content',
                faq_question: question,
                page: getCurrentPage()
            });
        },

        /**
         * Track erreur utilisateur
         */
        userError: function(params = {}) {
            sendGA4Event('user_error', {
                event_category: 'error',
                error_type: params.type || 'unknown',
                error_message: params.message || '',
                page: getCurrentPage()
            });
        }
    };

    // ═══════════════════════════════════════════════════════════════════════════
    // EVENTS BUSINESS (SPONSORS / MONETISATION)
    // ═══════════════════════════════════════════════════════════════════════════

    const BusinessEvents = {
        /**
         * Track impression sponsor
         */
        sponsorImpression: function(params = {}) {
            sendGA4Event('sponsor_impression', {
                event_category: 'monetization',
                sponsor: params.sponsor || 'default',
                sponsor_id: params.sponsorId || 'unknown',
                engine: params.engine || CONFIG.defaultEngine,
                placement: params.placement || 'popup_console',
                page: getCurrentPage(),
                // v2.5.2 — Engagement state + CPM actif/passif
                engagement_state: state.engagementState,
                impression_type: getImpressionType()
            });
        },

        /**
         * Track clic sponsor
         */
        sponsorClick: function(params = {}) {
            sendGA4Event('sponsor_click', {
                event_category: 'monetization',
                sponsor: params.sponsor || 'default',
                sponsor_id: params.sponsorId || 'unknown',
                engine: params.engine || CONFIG.defaultEngine,
                placement: params.placement || 'popup_console',
                destination_url: params.url || null,
                page: getCurrentPage(),
                // v2.5.2 — Engagement state + CPC pondéré
                engagement_state: state.engagementState,
                click_value: getClickValue()
            });
        },

        /**
         * Track conversion sponsor (prepare pour futur)
         */
        sponsorConversion: function(params = {}) {
            sendGA4Event('sponsor_conversion', {
                event_category: 'monetization',
                sponsor: params.sponsor || 'default',
                sponsor_id: params.sponsorId || 'unknown',
                conversion_type: params.type || 'signup',
                conversion_value: params.value || 0,
                currency: params.currency || 'EUR'
            });
        },

        // NOTE: adImpression / adClick removed (dead code, never called).
        // Sponsor tracking uses sponsorImpression / sponsorClick above.
    };

    // ═══════════════════════════════════════════════════════════════════════════
    // PRODUCT ANALYTICS ENGINE (v2.5+)
    // ═══════════════════════════════════════════════════════════════════════════
    // Module de tracking métier LotoIA - RGPD-safe, manuel, bufferisé
    // Baseline (denied): events anonymes cookieless autorisés
    // Enhanced (granted): events enrichis avec cookies GA4

    /**
     * Liste des clés PII interdites (RGPD)
     * Ces clés seront automatiquement supprimées des payloads
     */
    const PII_BLACKLIST = [
        'email', 'mail', 'e-mail',
        'phone', 'tel', 'telephone', 'mobile',
        'name', 'nom', 'prenom', 'firstname', 'lastname', 'fullname',
        'address', 'adresse', 'street', 'rue', 'city', 'ville', 'zip', 'postal',
        'ip', 'ip_address', 'ipaddress',
        'user_agent', 'useragent', 'ua',
        'password', 'pwd', 'pass', 'mot_de_passe',
        'credit_card', 'card_number', 'cvv', 'expiry',
        'ssn', 'social_security', 'national_id',
        'birth', 'birthday', 'dob', 'date_of_birth',
        'fingerprint', 'device_id', 'deviceid'
    ];

    /**
     * Sanitize un objet de paramètres pour RGPD compliance
     * - Supprime les clés PII
     * - Tronque les strings longues (>120 chars)
     * - Limite le nombre de clés (max 25)
     * @param {Object} params - Paramètres bruts
     * @returns {Object} Paramètres sanitisés
     */
    function sanitizeParams(params) {
        if (!params || typeof params !== 'object') return {};

        const sanitized = {};
        const keys = Object.keys(params);
        let keyCount = 0;

        for (const key of keys) {
            // Limite max 25 clés
            if (keyCount >= 25) {
                log('Params truncated (max 25 keys)', 'warning', null, 2);
                break;
            }

            // Ignorer les clés PII
            const keyLower = key.toLowerCase();
            if (PII_BLACKLIST.some(pii => keyLower.includes(pii))) {
                log(`PII key removed: ${key}`, 'warning', null, 2);
                continue;
            }

            let value = params[key];

            // Ignorer null/undefined
            if (value === null || value === undefined) continue;

            // Tronquer les strings longues
            if (typeof value === 'string' && value.length > 120) {
                value = value.substring(0, 117) + '...';
            }

            // Convertir les objets en string (éviter les structures complexes)
            if (typeof value === 'object') {
                try {
                    value = JSON.stringify(value).substring(0, 120);
                } catch (e) {
                    value = '[object]';
                }
            }

            sanitized[key] = value;
            keyCount++;
        }

        return sanitized;
    }

    /**
     * Construit le contexte complet pour un event produit
     * @returns {Object} Contexte minimal RGPD-safe
     */
    function buildProductContext() {
        return {
            traffic_mode: state.isEnhanced ? 'enhanced_consent' : 'baseline_cookieless',
            consent_analytics: state.isEnhanced,
            engine: state.productContext.engine,
            feature: state.productContext.feature,
            product_code: getProductCode(),
            page_path: window.location.pathname,
            ts: Date.now()
        };
    }

    /**
     * Envoie un event produit à GA4
     * @param {string} eventName - Nom de l'event (doit commencer par lotoia_)
     * @param {Object} payload - Données de l'event
     */
    function sendProductEvent(eventName, payload) {
        // Vérifier gtag disponible
        if (typeof window.gtag !== 'function') {
            if (!state.productWarnShown) {
                console.warn('[LotoIA Product] gtag not available - events dropped');
                state.productWarnShown = true;
            }
            return false;
        }

        // Vérifier si gtag.js est bloqué
        if (state.gtagLoadFailed) {
            log(`Product event dropped (gtag blocked): ${eventName}`, 'warning', null, 2);
            return false;
        }

        // Envoyer à GA4
        gtag('event', eventName, payload);
        log(`Product event: ${eventName}`, 'success', payload, 2);
        return true;
    }

    // 1.6.054 : âge max d'un event produit au vidage (= timeout de session GA4)
    const PRODUCT_EVENT_MAX_AGE_MS = 30 * 60 * 1000;

    /**
     * Flush le buffer d'events produit
     */
    function flushProductBuffer() {
        if (state.productBuffer.length === 0) return;

        // 1.6.054 : gtag bloqué (owner, appareil marqué, bot IA, bloqueur) → vider sans envoyer
        if (state.gtagLoadFailed) {
            state.productBuffer = [];
            return;
        }

        // 1.6.054 : rien avant config + page_view baseline (les events restent en tampon)
        if (!state.baselineReady) return;

        const events = [...state.productBuffer];
        state.productBuffer = [];

        // 1.6.054 : jeter les events > 30 min (onglet gelé en arrière-plan puis repris ou fermé)
        const now = Date.now();
        const fresh = events.filter(item => now - item.ts <= PRODUCT_EVENT_MAX_AGE_MS);

        log(`Flushing ${fresh.length} product events (${events.length - fresh.length} stale dropped)`, 'info', null, 2);

        fresh.forEach(item => {
            sendProductEvent(item.name, item.payload);
        });
    }

    /**
     * Normalise un nom d'event (anti-double préfixe)
     * - Trim + lowercase
     * - Retire les préfixes "lotoia_" répétés
     * - Ajoute "lotoia_" si absent
     * @param {string} name - Nom brut
     * @returns {string} Nom normalisé
     */
    function normalizeEventName(name) {
        if (!name || typeof name !== 'string') return 'lotoia_unknown';

        // Trim et lowercase
        let normalized = name.trim().toLowerCase();

        // Retirer tous les préfixes "lotoia_" répétés
        while (normalized.startsWith('lotoia_lotoia_')) {
            normalized = normalized.replace('lotoia_lotoia_', 'lotoia_');
        }

        // Ajouter le préfixe si absent
        if (!normalized.startsWith('lotoia_')) {
            normalized = 'lotoia_' + normalized;
        }

        return normalized;
    }

    /**
     * Ajoute un event au buffer et flush si nécessaire
     * @param {string} name - Nom de l'event
     * @param {Object} payload - Données de l'event
     */
    function bufferProductEvent(name, payload) {
        // 1.6.072 (Q8) : avant consentement (ou après retrait) → event jeté, aucun tampon
        if (!state.gtagBooted || !state.isEnhanced) {
            log(`Product event dropped (no analytics consent): ${name}`, 'info', null, 2);
            return;
        }

        // Limite max 50 events en buffer
        if (state.productBuffer.length >= 50) {
            log('Product buffer full - dropping oldest event', 'warning');
            state.productBuffer.shift();
        }

        state.productBuffer.push({ name, payload, ts: Date.now() });

        // Flush si 5 events ou plus
        if (state.productBuffer.length >= 5) {
            flushProductBuffer();
            return;
        }

        // Timer pour flush après 2s
        if (!state.productBufferTimer) {
            state.productBufferTimer = setTimeout(() => {
                state.productBufferTimer = null;
                flushProductBuffer();
            }, 2000);
        }
    }

    /**
     * Product Analytics Engine - API interne
     */
    const ProductEngine = {
        /**
         * Définit le moteur actif
         * @param {string} engineName - hybride | random | manual | unknown
         */
        setEngine: function(engineName) {
            const valid = ['hybride', 'random', 'manual', 'unknown'];
            state.productContext.engine = valid.includes(engineName) ? engineName : 'unknown';
            log(`Product engine set: ${state.productContext.engine}`, 'info', null, 2);
        },

        /**
         * Définit la feature/page active
         * @param {string} featureName - simulateur | stats | home | faq | etc.
         */
        setFeature: function(featureName) {
            state.productContext.feature = featureName || 'unknown';
            log(`Product feature set: ${state.productContext.feature}`, 'info', null, 2);
        },

        /**
         * Définit le contexte complet (merge)
         * @param {Object} ctx - { engine?, feature? }
         */
        setContext: function(ctx) {
            if (ctx && typeof ctx === 'object') {
                if (ctx.engine) this.setEngine(ctx.engine);
                if (ctx.feature) this.setFeature(ctx.feature);
            }
        },

        /**
         * Retourne le contexte actuel
         * @returns {Object} Contexte produit
         */
        getContext: function() {
            return { ...state.productContext };
        },

        /**
         * Track un event produit
         * @param {string} eventName - Nom (sera normalisé avec préfixe lotoia_)
         * @param {Object} params - Paramètres (seront sanitisés)
         */
        track: function(eventName, params = {}) {
            // Normaliser le nom (anti-double préfixe, lowercase, trim)
            const name = normalizeEventName(eventName);

            // Sanitiser les params (RGPD)
            const sanitized = sanitizeParams(params);

            // Construire le payload complet
            // Respecter event_category si fourni dans params, sinon 'product'
            const payload = {
                ...buildProductContext(),
                event_category: sanitized.event_category || 'product',
                ...sanitized
            };

            // GA4 prêt (config + page_view partis) : envoi direct
            // Chargement en cours : tampon ; sans consentement : jeté (bufferProductEvent, Q8)
            if (state.isEnhanced && state.baselineReady) {
                sendProductEvent(name, payload);
            } else {
                bufferProductEvent(name, payload);
            }
        },

        // NOTE: sponsorView / sponsorClick removed (dead code, never called).
        // Sponsor tracking uses BusinessEvents.sponsorImpression / sponsorClick.

        /**
         * Flush manuel du buffer
         */
        flush: function() {
            flushProductBuffer();
        }
    };

    // Flush automatique du buffer produit à la sortie de page (v2.5.1)
    // Évite la perte d'events en baseline si l'utilisateur quitte rapidement
    (function setupProductBufferFlushOnExit() {
        function safeFlush() {
            try {
                // v2.5.2 — Marquer engagement 'exit' avant flush final
                state.engagementState = 'exit';
                if (state.productBuffer && state.productBuffer.length > 0) {
                    flushProductBuffer();
                }
            } catch (e) {
                // Silencieux - pas de crash sur unload
            }
        }

        // pagehide (mobile Safari / bfcache)
        window.addEventListener('pagehide', safeFlush);

        // beforeunload (fallback desktop)
        window.addEventListener('beforeunload', safeFlush);
    })();

    // 1.6.054 : retour arrière depuis le bfcache → la page restaurée ne rejoue pas son page_view ;
    // sans lui, les events suivants ouvrent une session sans page d'entrée (Unassigned).
    window.addEventListener('pageshow', function(event) {
        if (!event.persisted) return;
        // 1.6.072 : exclusion testée avant le consentement
        if (isExcluded()) return;
        // 1.6.072 (B1 bis) : retrait fait sur une autre page pendant que celle-ci dormait dans le bfcache
        if (resyncConsentFromStorage()) return;
        if (!state.gtagBooted || !state.baselineReady || state.gtagLoadFailed || typeof window.gtag !== 'function') return;
        if (!state.isEnhanced || !readStoredAnalyticsConsent()) return;
        sendPageView('bfcache_restore');
    });

    // 1.6.072 (B1 bis) : retrait fait dans un autre onglet → propagé ici (désactivation + purge).
    // key null = localStorage.clear(). Une acceptation dans un autre onglet ne charge PAS GA4 ici.
    window.addEventListener('storage', function(event) {
        if (event.key !== 'lotoia_cookie_consent' && event.key !== null) return;
        resyncConsentFromStorage();
    });

    // ═══════════════════════════════════════════════════════════════════════════
    // TRACKING AUTOMATIQUE
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Configure le tracking automatique du scroll
     * Guard anti-double listener via state.scrollTrackingEnabled
     */
    function setupScrollTracking() {
        if (!CONFIG.trackScroll) return;
        if (state.scrollTrackingEnabled) return; // Anti-double listener
        state.scrollTrackingEnabled = true;

        let ticking = false;

        function checkScroll() {
            const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
            if (scrollHeight <= 0) return;

            const scrolled = window.scrollY;
            const percentage = Math.round((scrolled / scrollHeight) * 100);

            CONFIG.scrollThresholds.forEach(threshold => {
                if (percentage >= threshold && !state.scrollTracked[threshold]) {
                    UXEvents.scrollDepth(threshold);
                }
            });

            ticking = false;
        }

        window.addEventListener('scroll', function() {
            if (!ticking) {
                requestAnimationFrame(checkScroll);
                ticking = true;
            }
        }, { passive: true });

        log('Scroll tracking enabled', 'info');
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // INTEGRATION COOKIE CONSENT
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Vérifie si CookieConsent est disponible (non bloqué par adblock)
     * @returns {boolean} true si CookieConsent est chargé et fonctionnel
     */
    function isCookieConsentAvailable() {
        return typeof CookieConsent !== 'undefined' &&
               CookieConsent !== null &&
               typeof CookieConsent.isAccepted === 'function';
    }

    /**
     * Verifie si le consentement analytics est donne
     * Robuste face aux adblockers qui bloquent cookie-consent.js
     * @returns {boolean} true si consentement explicite, false sinon
     */
    function hasAnalyticsConsent() {
        // Verifier via CookieConsent si disponible
        try {
            if (isCookieConsentAvailable()) {
                return CookieConsent.isAccepted('analytics');
            }
        } catch (e) {
            // CookieConsent existe mais erreur d'appel
            log('CookieConsent.isAccepted() error', 'warning', e.message, 2);
        }

        // Fallback: consentement sauvegardé (1.6.054 : expiration 13 mois respectée)
        return readStoredAnalyticsConsent();
    }

    /**
     * Handler pour le changement de consentement (Consent Mode v2)
     * Appelé lors des events cookieConsentUpdated / CookieConsentUpdated
     */
    function onConsentChange(event) {
        const choices = (event && event.detail) || {};

        log('Consent changed', 'info', choices);

        // Cas 1: Analytics ACCEPTÉ (Tout accepter, ou Personnaliser coché) → chargement GA4
        // (exclusion owner testée en premier dans loadGA4IfConsented ; gère aussi la ré-acceptation)
        if (choices.analytics === true) {
            loadGA4IfConsented('consent');
            return;
        }

        // Cas 2: Analytics REFUSÉ / RETIRÉ → denied + ga-disable si chargé, purge des _ga* dans tous les cas
        if (choices.analytics === false) {
            log('Analytics refused → GA4 disabled, _ga cookies purged', 'info');
            disableGA4();
            purgeGaCookies();
        }
    }

    /**
     * Configure les listeners de consentement
     * Écoute les deux variantes de casse de l'event
     */
    function setupConsentListeners() {
        // Event principal (minuscule)
        document.addEventListener('cookieConsentUpdated', onConsentChange);

        // Event alternatif (CamelCase) - certaines versions du module
        document.addEventListener('CookieConsentUpdated', onConsentChange);

        log('Consent listeners configured', 'info', null, 2);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // INITIALISATION
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Initialise le module analytics (legacy - pour compatibilité API)
     * 1.6.072 : charge GA4 seulement si non exclu ET consentement stocké (sinon rien)
     */
    function initialize() {
        return loadGA4IfConsented('boot');
    }

    /**
     * Point d'entrée automatique - Consent Mode « de base » (1.6.072)
     * Le chargement d'un acceptant connu est déjà fait au démarrage (loadGA4IfConsented('boot')).
     * Ici : listeners de consentement posés dans tous les cas (acceptation, retrait, ré-acceptation).
     * Plus de repli « CookieConsent bloqué → baseline » : sans consentement, rien n'est chargé.
     */
    function autoInit() {
        setupConsentListeners();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // API PUBLIQUE
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * API globale exposee sur window.LotoIAAnalytics
     */
    const PublicAPI = {
        // Version
        version: '2.6.0',

        // Configuration (lecture seule)
        config: Object.freeze({ ...CONFIG }),

        // Methode generique de tracking
        track: function(eventName, params = {}) {
            return sendGA4Event(eventName, params);
        },

        // Tracking page
        trackPage: function(pageName) {
            UXEvents.pageView(pageName);
        },

        // Tracking moteur
        trackEngine: function(engineName, action = 'use') {
            sendGA4Event('engine_interaction', {
                event_category: 'engagement',
                engine: engineName,
                action: action
            });
        },

        // Tracking sponsor
        trackSponsor: function(type, sponsorName, params = {}) {
            if (type === 'impression') {
                BusinessEvents.sponsorImpression({ sponsor: sponsorName, ...params });
            } else if (type === 'click') {
                BusinessEvents.sponsorClick({ sponsor: sponsorName, ...params });
            } else if (type === 'conversion') {
                BusinessEvents.sponsorConversion({ sponsor: sponsorName, ...params });
            }
        },

        // Events produit legacy (rétrocompatibilité API historique)
        product: ProductEvents,

        // Product Analytics Engine (v2.5+) - nouveau moteur premium
        productEngine: ProductEngine,

        // Alias legacy (compatibilité, si besoin explicite)
        productLegacy: ProductEvents,

        // Events UX
        ux: UXEvents,

        // Events business
        business: BusinessEvents,

        // Utilitaires
        utils: {
            getSessionId: getSessionId,
            getCurrentPage: getCurrentPage,
            getPageMetadata: getPageMetadata,
            hasConsent: hasAnalyticsConsent,
            isCookieConsentAvailable: isCookieConsentAvailable
        },

        // Initialisation manuelle (si necessaire)
        init: initialize,

        // 1.6.072 : purge des cookies _ga / _ga_* (bouton « Effacer mes données LotoIA » des pages cookies)
        purgeGaCookies: purgeGaCookies,

        // Debug mode (via localStorage) — 1.6.072 : owner uniquement
        setDebug: function(level) {
            if (!isDebugAllowed()) return;
            try {
                localStorage.setItem('debug_ga4', String(level ? (level === true ? 1 : level) : 0));
                log(`Debug level set to ${level}`, 'info');
            } catch (e) {
                console.warn('[LotoIA GA4] Cannot set debug level:', e.message);
            }
        },

        // Verifier l'etat
        isInitialized: function() {
            return state.initialized;
        },

        // Nouveaux états Consent Mode v2
        isGtagBooted: function() {
            return state.gtagBooted;
        },

        isGtagBlocked: function() {
            return state.gtagLoadFailed;
        },

        isGtagScriptReady: function() {
            return state.gtagScriptReady;
        },

        isBaselineReady: function() {
            return state.baselineReady;
        },

        isEnhanced: function() {
            return state.isEnhanced;
        },

        // État CookieConsent bloqué (adblock) — 1.6.072 : calculé (plus de mode « baseline » de repli)
        isCookieConsentBlocked: function() {
            return !isCookieConsentAvailable();
        },

        // Forcer l'envoi d'un pageview
        sendPageView: function() {
            UXEvents.pageView();
        }
    };

    // ═══════════════════════════════════════════════════════════════════════════
    // EXPORT & AUTO-INIT
    // ═══════════════════════════════════════════════════════════════════════════

    // Exposer l'API globale
    window.LotoIAAnalytics = PublicAPI;

    // Alias de compatibilité (legacy → engine) : ne jamais écraser les fonctions legacy.
    // Si, pour une raison quelconque, ProductEvents n'est pas exposé, on bridge vers ProductEngine.
    if (window.LotoIAAnalytics &&
        window.LotoIAAnalytics.productEngine &&
        window.LotoIAAnalytics.product &&
        typeof window.LotoIAAnalytics.product.generateGrid !== 'function') {

        window.LotoIAAnalytics.product.generateGrid = function(params) {
            window.LotoIAAnalytics.productEngine.track('lotoia_generate_grid', params || {});
        };
    }

    // Retrocompatibilite avec l'ancienne API
    window.LotoIA = window.LotoIA || {};
    window.LotoIA.Analytics = {
        init: function(measurementId) {
            if (measurementId) CONFIG.GA4_ID = measurementId;
            initialize();
        },
        track: PublicAPI.track,
        trackGenerateGrid: ProductEvents.generateGrid,
        trackSimulateGrid: ProductEvents.simulateGrid,
        trackViewStats: ProductEvents.viewStats,
        trackSearchHistory: ProductEvents.searchHistory,
        trackCopyGrid: ProductEvents.copyGrid,
        trackThemeChange: UXEvents.themeChange,
        trackFaqOpen: UXEvents.faqOpen
    };

    // Auto-initialisation
    autoInit();

    // Log de chargement (silencieux par défaut, sauf debug)
    if (getDebugLevel() >= 1) {
        console.log('[LotoIA GA4] Module v2.6.0 loaded - Consent Mode basic (GA4 after consent only)');
    }

})(window, document);

