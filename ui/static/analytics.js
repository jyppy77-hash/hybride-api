/**
 * ═══════════════════════════════════════════════════════════════════════════════
 * LOTOIA ANALYTICS MODULE v2.0
 * ═══════════════════════════════════════════════════════════════════════════════
 *
 * Infrastructure analytics professionnelle pour SaaS LotoIA
 * - GA4 Integration avec gestion RGPD
 * - Events produit (moteur LotoIA)
 * - Events UX (parcours utilisateur)
 * - Events business (sponsors / monetisation)
 * - Architecture scalable multi-moteurs / multi-pays
 *
 * @author LotoIA Team
 * @version 2.0.0
 * @license Proprietary
 *
 * USAGE:
 * 1. Inclure ce script dans le <head> APRES cookie-consent.js
 * 2. Le module s'initialise automatiquement apres consentement
 * 3. Utiliser window.LotoIAAnalytics.track() pour les events custom
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
        defaultAlgorithm: 'HYBRIDE_OPTIMAL_V1',

        // Delai avant envoi pageview (ms)
        pageviewDelay: 100,

        // Activer le tracking automatique du scroll
        trackScroll: true,
        scrollThresholds: [25, 50, 75, 90, 100],

        // Futurs providers (Matomo, Plausible, Umami)
        providers: {
            ga4: { enabled: true, id: 'G-YYJ5LD1ZT3' },
            matomo: { enabled: false, url: null, siteId: null },
            plausible: { enabled: false, domain: null },
            umami: { enabled: false, websiteId: null }
        }
    };

    // ═══════════════════════════════════════════════════════════════════════════
    // ETAT INTERNE
    // ═══════════════════════════════════════════════════════════════════════════

    const state = {
        initialized: false,
        consentGiven: false,
        sessionId: null,
        pageLoadTime: Date.now(),
        scrollTracked: {},
        eventsQueue: []
    };

    // ═══════════════════════════════════════════════════════════════════════════
    // UTILITAIRES
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Logger conditionnel (mode debug)
     */
    function log(message, type = 'info', data = null) {
        if (!CONFIG.debug) return;

        const prefix = '[LotoIA Analytics]';
        const styles = {
            info: 'color: #2196F3',
            success: 'color: #4CAF50',
            warning: 'color: #FF9800',
            error: 'color: #F44336'
        };

        console.log(`%c${prefix} ${message}`, styles[type] || styles.info, data || '');
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
    // GA4 CORE
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Charge le script gtag.js de maniere asynchrone
     */
    function loadGtagScript(measurementId) {
        return new Promise((resolve, reject) => {
            // Verifier si deja charge
            if (window.gtag) {
                log('gtag already loaded', 'info');
                resolve();
                return;
            }

            const script = document.createElement('script');
            script.async = true;
            script.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;

            script.onload = () => {
                log('gtag script loaded', 'success');
                resolve();
            };

            script.onerror = () => {
                log('Failed to load gtag script', 'error');
                reject(new Error('gtag load failed'));
            };

            document.head.appendChild(script);
        });
    }

    /**
     * Initialise GA4 avec la configuration RGPD
     */
    function initGA4(measurementId) {
        // DataLayer
        window.dataLayer = window.dataLayer || [];

        function gtag() {
            dataLayer.push(arguments);
        }
        window.gtag = gtag;

        // Timestamp initial
        gtag('js', new Date());

        // Configuration GA4 avec options RGPD
        gtag('config', measurementId, {
            // Anonymisation IP (requis RGPD)
            'anonymize_ip': true,

            // Cookies securises
            'cookie_flags': 'SameSite=None;Secure',

            // Desactiver les signaux publicitaires (pas de remarketing)
            'allow_google_signals': false,
            'allow_ad_personalization_signals': false,

            // Desactiver le suivi de formulaires automatique
            'form_submit': false,

            // Desactiver le tracking de fichiers telecharges
            'file_download': false,

            // Page path personnalise
            'page_path': window.location.pathname,

            // Custom dimensions
            'custom_map': {
                'dimension1': 'engine',
                'dimension2': 'algorithm',
                'dimension3': 'session_id'
            }
        });

        log(`GA4 initialized with ID: ${measurementId}`, 'success');
    }

    /**
     * Envoie un event GA4
     */
    function sendGA4Event(eventName, params = {}) {
        if (!window.gtag) {
            log(`Event queued (gtag not ready): ${eventName}`, 'warning', params);
            state.eventsQueue.push({ eventName, params, timestamp: Date.now() });
            return false;
        }

        // Enrichir avec metadata standard
        const enrichedParams = {
            ...params,
            session_id: getSessionId(),
            page: getCurrentPage(),
            engine: params.engine || CONFIG.defaultEngine,
            timestamp: Date.now()
        };

        gtag('event', eventName, enrichedParams);
        log(`Event sent: ${eventName}`, 'success', enrichedParams);
        return true;
    }

    /**
     * Traite la queue d'events en attente
     */
    function processEventsQueue() {
        if (state.eventsQueue.length === 0) return;

        log(`Processing ${state.eventsQueue.length} queued events`, 'info');

        const queue = [...state.eventsQueue];
        state.eventsQueue = [];

        queue.forEach(item => {
            sendGA4Event(item.eventName, item.params);
        });
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
         * Track fin de session (beforeunload)
         */
        sessionEnd: function() {
            const sessionDuration = Math.round((Date.now() - state.pageLoadTime) / 1000);

            // Utiliser sendBeacon pour garantir l'envoi
            if (navigator.sendBeacon && window.gtag) {
                sendGA4Event('session_end_lotoia', {
                    event_category: 'session',
                    session_id: getSessionId(),
                    session_duration_seconds: sessionDuration,
                    exit_page: getCurrentPage()
                });
            }
        },

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
                page: getCurrentPage()
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
                page: getCurrentPage()
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

        /**
         * Track impression publicitaire
         */
        adImpression: function(params = {}) {
            sendGA4Event('ad_impression', {
                event_category: 'advertising',
                ad_id: params.adId || 'unknown',
                ad_placement: params.placement || 'inline',
                ad_format: params.format || 'banner',
                page: getCurrentPage()
            });
        },

        /**
         * Track clic publicitaire
         */
        adClick: function(params = {}) {
            sendGA4Event('ad_click', {
                event_category: 'advertising',
                ad_id: params.adId || 'unknown',
                ad_placement: params.placement || 'inline',
                partner_id: params.partnerId || 'unknown',
                page: getCurrentPage()
            });
        }
    };

    // ═══════════════════════════════════════════════════════════════════════════
    // TRACKING AUTOMATIQUE
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Configure le tracking automatique du scroll
     */
    function setupScrollTracking() {
        if (!CONFIG.trackScroll) return;

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

    /**
     * Configure le tracking de fin de session
     */
    function setupSessionTracking() {
        // Track session end on page unload
        window.addEventListener('beforeunload', function() {
            UXEvents.sessionEnd();
        });

        // Track visibility change (tab switch)
        document.addEventListener('visibilitychange', function() {
            if (document.visibilityState === 'hidden') {
                UXEvents.sessionEnd();
            }
        });

        log('Session tracking enabled', 'info');
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // INTEGRATION COOKIE CONSENT
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Verifie si le consentement analytics est donne
     */
    function hasAnalyticsConsent() {
        // Verifier via CookieConsent si disponible
        if (typeof CookieConsent !== 'undefined' && CookieConsent.isAccepted) {
            return CookieConsent.isAccepted('analytics');
        }

        // Fallback: verifier le localStorage
        try {
            const stored = localStorage.getItem('lotoia_cookie_consent');
            if (stored) {
                const data = JSON.parse(stored);
                return data.choices && data.choices.analytics === true;
            }
        } catch (e) {
            // Ignore
        }

        return false;
    }

    /**
     * Handler pour le changement de consentement
     */
    function onConsentChange(event) {
        const choices = event.detail || {};

        log('Consent changed', 'info', choices);

        if (choices.analytics === true && !state.initialized) {
            initialize();
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // INITIALISATION
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Initialise le module analytics
     */
    async function initialize() {
        if (state.initialized) {
            log('Already initialized', 'warning');
            return;
        }

        // Verifier le consentement
        if (!hasAnalyticsConsent()) {
            log('No analytics consent, waiting...', 'info');
            return;
        }

        state.consentGiven = true;

        try {
            // Charger gtag.js
            await loadGtagScript(CONFIG.GA4_ID);

            // Initialiser GA4
            initGA4(CONFIG.GA4_ID);

            // Marquer comme initialise
            state.initialized = true;

            // Traiter la queue d'events en attente
            processEventsQueue();

            // Configurer le tracking automatique
            setupScrollTracking();
            setupSessionTracking();

            // Envoyer le pageview initial avec delai
            setTimeout(() => {
                UXEvents.pageView();
                UXEvents.sessionStart();
            }, CONFIG.pageviewDelay);

            log('Analytics fully initialized', 'success');

        } catch (error) {
            log('Initialization failed: ' + error.message, 'error');
        }
    }

    /**
     * Point d'entree automatique
     */
    function autoInit() {
        // Ecouter les changements de consentement
        document.addEventListener('cookieConsentUpdated', onConsentChange);

        // Verifier si le consentement existe deja
        if (hasAnalyticsConsent()) {
            // Attendre que le DOM soit pret
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', initialize);
            } else {
                initialize();
            }
        } else {
            log('Waiting for analytics consent...', 'info');
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // API PUBLIQUE
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * API globale exposee sur window.LotoIAAnalytics
     */
    const PublicAPI = {
        // Version
        version: '2.0.0',

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

        // Events produit
        product: ProductEvents,

        // Events UX
        ux: UXEvents,

        // Events business
        business: BusinessEvents,

        // Utilitaires
        utils: {
            getSessionId: getSessionId,
            getCurrentPage: getCurrentPage,
            getPageMetadata: getPageMetadata,
            hasConsent: hasAnalyticsConsent
        },

        // Initialisation manuelle (si necessaire)
        init: initialize,

        // Debug mode
        setDebug: function(enabled) {
            CONFIG.debug = enabled;
            log(`Debug mode ${enabled ? 'enabled' : 'disabled'}`, 'info');
        },

        // Verifier l'etat
        isInitialized: function() {
            return state.initialized;
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

    // Log de chargement
    console.log('[LotoIA Analytics] Module v2.0 loaded - Waiting for consent');

})(window, document);
