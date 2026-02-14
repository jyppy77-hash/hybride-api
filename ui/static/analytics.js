/**
 * ═══════════════════════════════════════════════════════════════════════════════
 * LOTOIA ANALYTICS MODULE v2.5.2 - PRODUCT ANALYTICS PREMIUM
 * ═══════════════════════════════════════════════════════════════════════════════
 *
 * Infrastructure analytics professionnelle pour SaaS LotoIA
 * - GA4 Integration avec Consent Mode v2 (RGPD/CNIL compliant)
 * - Baseline cookieless pour 100% des visiteurs
 * - Events enrichis après consentement analytics
 * - Product Analytics Engine (v2.5+) pour tracking métier
 * - Events produit (moteur LotoIA)
 * - Events UX (parcours utilisateur)
 * - Events business (sponsors / monetisation)
 * - Architecture scalable multi-moteurs / multi-pays
 *
 * @author LotoIA Team
 * @version 2.5.2
 * @license Proprietary
 *
 * ARCHITECTURE CONSENT MODE v2 (CNIL/RGPD):
 * ┌─────────────────────────────────────────────────────────────────────────────┐
 * │ 0. bootGtagImmediately() - Charge gtag.js AU BOOT (indépendant consent)    │
 * │    → dataLayer + gtag() + consent:default denied + script injection        │
 * │ 1. baselineInit() - Configure GA4 + envoie 1 page_view baseline            │
 * │    → 1 page_view anonyme pour TOUS (cookieless, IP anonymisée)             │
 * │ 2. enableEnhanced() - Après consentement analytics                         │
 * │    → consent:update granted + event consent_granted (PAS de 2e page_view)  │
 * └─────────────────────────────────────────────────────────────────────────────┘
 *
 * DEBUG: localStorage.setItem('debug_ga4', '1') pour logs basiques
 *        localStorage.setItem('debug_ga4', '2') pour logs détaillés
 *
 * USAGE:
 * 1. Inclure ce script dans le <head>
 * 2. Le baseline s'initialise automatiquement (cookieless)
 * 3. Après consentement, le mode enrichi s'active automatiquement
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
        gtagBooted: false,            // Flag gtag.js boot immédiat (étape 0)
        baselineReady: false,         // Flag anti-double baseline init
        isEnhanced: false,            // Flag anti-double enhanced init
        gtagLoadFailed: false,        // Flag adblock/network error (gtag.js)
        gtagScriptReady: false,       // Flag gtag.js script loaded and ready
        cookieConsentBlocked: false,  // Flag adblock/network error (cookie-consent.js)
        scrollTrackingEnabled: false, // Flag anti-double scroll listener
        sessionId: null,
        pageLoadTime: Date.now(),
        scrollTracked: {},
        eventsQueue: [],

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
     */
    function getDebugLevel() {
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
    // BOOT GTAG IMMÉDIAT (INDÉPENDANT DU CONSENTEMENT)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Boot gtag.js IMMÉDIATEMENT au chargement du module.
     * CRITIQUE: Cette fonction est appelée au tout début, AVANT toute logique consent.
     * Elle garantit que gtag() est disponible même si CookieConsent est bloqué.
     *
     * Étapes:
     * 1. Initialise dataLayer + window.gtag
     * 2. Applique Consent Mode v2 par défaut (tous denied)
     * 3. Injecte le script gtag.js (fire-and-forget)
     */
    function bootGtagImmediately() {
        // Anti-double boot
        if (state.gtagBooted) return;

        try {
            // 1. Initialiser dataLayer et gtag() SYNCHRONE
            window.dataLayer = window.dataLayer || [];
            window.gtag = function() {
                dataLayer.push(arguments);
            };

            // 2. Consent Mode v2 - DEFAULT DENIED (CNIL/RGPD)
            // CRITIQUE: Doit être appelé AVANT l'injection du script
            gtag('consent', 'default', {
                'ad_storage': 'denied',
                'analytics_storage': 'denied',
                'ad_user_data': 'denied',
                'ad_personalization': 'denied'
            });

            // 3. Injecter gtag.js avec callback ready
            const script = document.createElement('script');
            script.async = true;
            script.src = 'https://www.googletagmanager.com/gtag/js?id=' + CONFIG.GA4_ID;
            script.onload = function() {
                state.gtagScriptReady = true;
                // Log uniquement si debug activé
                try {
                    if (parseInt(localStorage.getItem('debug_ga4') || '0', 10) >= 2) {
                        console.log('%c[LotoIA GA4] gtag.js script loaded', 'color: #4CAF50');
                    }
                } catch (e) { /* ignore */ }
            };
            script.onerror = function() {
                state.gtagLoadFailed = true;
                state.gtagScriptReady = true; // Marquer ready même en erreur pour débloquer
                console.warn('[LotoIA GA4] gtag.js blocked (adblock/network)');
            };
            document.head.appendChild(script);

            state.gtagBooted = true;
            // Log uniquement si debug activé (getDebugLevel pas encore dispo à ce stade)
            try {
                if (parseInt(localStorage.getItem('debug_ga4') || '0', 10) >= 1) {
                    console.log('%c[LotoIA GA4] gtag booted immediately (consent-independent)', 'color: #4CAF50');
                }
            } catch (e) { /* ignore */ }

        } catch (e) {
            console.warn('[LotoIA GA4] Boot failed:', e.message);
        }
    }

    // ══════════════════════════════════════════════════════════════════════════
    // BOOT IMMÉDIAT - Exécuté maintenant, avant toute autre logique
    // ══════════════════════════════════════════════════════════════════════════
    bootGtagImmediately();

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
     * Charge le script gtag.js de maniere asynchrone
     * Gère gracieusement les adblockers et erreurs réseau
     * @deprecated Utilisé en fallback, gtag.js est déjà chargé par bootGtagImmediately()
     */
    function loadGtagScript(measurementId) {
        return new Promise((resolve, reject) => {
            // Verifier si deja charge
            if (window.gtag) {
                log('gtag already loaded', 'info');
                resolve();
                return;
            }

            // Si échec précédent (adblock), ne pas réessayer
            if (state.gtagLoadFailed) {
                reject(new Error('gtag blocked (cached)'));
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
                state.gtagLoadFailed = true;
                // Warning unique (pas de boucle)
                console.warn('[LotoIA GA4] gtag.js blocked (adblock/network) - analytics disabled');
                reject(new Error('gtag load failed'));
            };

            document.head.appendChild(script);
        });
    }

    /**
     * Initialise le dataLayer et la fonction gtag
     * (séparé de la config pour Consent Mode v2)
     */
    function initDataLayer() {
        if (window.gtag) return; // Déjà initialisé

        window.dataLayer = window.dataLayer || [];
        function gtag() {
            dataLayer.push(arguments);
        }
        window.gtag = gtag;
    }

    /**
     * ═══════════════════════════════════════════════════════════════════════════
     * BASELINE INIT - Consent Mode v2 (CNIL/RGPD)
     * ═══════════════════════════════════════════════════════════════════════════
     * Configure GA4 et envoie 1 page_view baseline cookieless.
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

        // Vérifier que gtag a bien été booté
        if (!window.gtag) {
            log('gtag not available (boot failed?)', 'error');
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

                // Custom dimensions
                'custom_map': {
                    'dimension1': 'engine',
                    'dimension2': 'algorithm',
                    'dimension3': 'session_id'
                }
            });

            // 3. Marquer baseline ready AVANT d'envoyer le page_view (anti-double)
            state.baselineReady = true;

            // 4. Envoyer UN SEUL page_view baseline (cookieless, Consent Mode v2)
            gtag('event', 'page_view', {
                'page_title': document.title,
                'page_location': window.location.href,
                'page_path': window.location.pathname,
                'event_category': 'baseline',
                'non_interaction': true
            });

            // Log explicite du statut pour diagnostic
            const consentStatus = hasAnalyticsConsent() ? 'granted' : 'denied';
            log(`Baseline page_view sent (analytics_storage: ${consentStatus}, gtag_ready: ${gtagReady})`, 'success');

            return true;

        } catch (error) {
            log('Baseline init failed: ' + error.message, 'error');
            return false;
        }
    }

    /**
     * ═══════════════════════════════════════════════════════════════════════════
     * ENABLE ENHANCED - Après consentement analytics
     * ═══════════════════════════════════════════════════════════════════════════
     * Active le mode enrichi après consentement utilisateur.
     * Met à jour le Consent Mode v2 avec analytics_storage:granted.
     * N'ENVOIE PAS de 2e page_view (déjà envoyé en baseline).
     *
     * @returns {boolean} true si enhanced activé, false sinon
     */
    function enableEnhanced() {
        // Anti-double init
        if (state.isEnhanced) {
            log('Enhanced already enabled', 'warning');
            return true;
        }

        // Vérifier le consentement (CRITIQUE: enhanced uniquement si accepté)
        if (!hasAnalyticsConsent()) {
            log('Enhanced skipped (analytics consent: denied)', 'info');
            return false;
        }

        // Vérifier que gtag est disponible
        if (!window.gtag) {
            log('gtag not available for enhanced mode', 'error');
            return false;
        }

        // 1. Consent Mode v2 - UPDATE GRANTED (analytics only)
        // Note: ad_storage reste denied (pas de remarketing)
        gtag('consent', 'update', {
            'analytics_storage': 'granted',
            'ad_storage': 'denied',
            'ad_user_data': 'denied',
            'ad_personalization': 'denied'
        });

        // 2. Marquer comme enhanced
        state.isEnhanced = true;
        state.consentGiven = true;
        state.initialized = true; // Compatibilité avec l'ancien état

        // 3. Envoyer event consent_granted (PAS de page_view!)
        gtag('event', 'consent_granted', {
            'event_category': 'consent',
            'analytics_storage': 'granted',
            'timestamp': Date.now()
        });

        // 4. Traiter la queue d'events en attente
        processEventsQueue();

        // 5. Activer le tracking avancé
        setupScrollTracking();
        setupSessionTracking();

        log('Enhanced mode enabled (consent granted)', 'success');
        return true;
    }

    /**
     * Initialise GA4 avec la configuration RGPD (legacy - appelé par enableEnhanced indirectement)
     * @deprecated Utiliser baselineInit() + enableEnhanced()
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
            // CRITIQUE: Désactiver le page_view automatique (anti-double)
            'send_page_view': false,

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
     * Gère gracieusement l'absence de gtag (adblock)
     */
    function sendGA4Event(eventName, params = {}) {
        // Si gtag bloqué définitivement, no-op silencieux
        if (state.gtagLoadFailed) {
            log(`Event dropped (gtag blocked): ${eventName}`, 'warning', params, 2);
            return false;
        }

        if (!window.gtag) {
            log(`Event queued (gtag not ready): ${eventName}`, 'warning', params, 2);
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
        log(`Event sent: ${eventName}`, 'success', enrichedParams, 2);
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
         * Track fin de session (beforeunload)
         */
        sessionEnd: function() {
            updateEngagementState('exit');
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

    /**
     * Flush le buffer d'events produit
     */
    function flushProductBuffer() {
        if (state.productBuffer.length === 0) return;

        const events = [...state.productBuffer];
        state.productBuffer = [];

        log(`Flushing ${events.length} product events`, 'info', null, 2);

        events.forEach(item => {
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

            // Mode enhanced : envoi direct
            // Mode baseline : buffer
            if (state.isEnhanced) {
                sendProductEvent(name, payload);
            } else {
                bufferProductEvent(name, payload);
            }
        },

        /**
         * Track une vue sponsor
         * @param {string} slot - Emplacement (sidebar_top, footer, etc.)
         */
        sponsorView: function(slot) {
            this.track('lotoia_sponsor_view', {
                slot: slot || 'unknown',
                event_category: 'monetization'
            });
        },

        /**
         * Track un clic sponsor
         * @param {string} slot - Emplacement
         */
        sponsorClick: function(slot) {
            this.track('lotoia_sponsor_click', {
                slot: slot || 'unknown',
                event_category: 'monetization'
            });
        },

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
        // Si CookieConsent bloqué, TOUJOURS retourner false (baseline only)
        if (state.cookieConsentBlocked) {
            return false;
        }

        // Verifier via CookieConsent si disponible
        try {
            if (isCookieConsentAvailable()) {
                return CookieConsent.isAccepted('analytics');
            }
        } catch (e) {
            // CookieConsent existe mais erreur d'appel
            log('CookieConsent.isAccepted() error', 'warning', e.message, 2);
        }

        // Fallback: verifier le localStorage (consentement sauvegardé)
        try {
            const stored = localStorage.getItem('lotoia_cookie_consent');
            if (stored) {
                const data = JSON.parse(stored);
                return data.choices && data.choices.analytics === true;
            }
        } catch (e) {
            // Ignore localStorage errors
        }

        return false;
    }

    /**
     * Handler pour le changement de consentement (Consent Mode v2)
     * Appelé lors des events cookieConsentUpdated / CookieConsentUpdated
     */
    function onConsentChange(event) {
        const choices = event.detail || {};

        log('Consent changed', 'info', choices);

        // Cas 1: Analytics ACCEPTÉ → activer enhanced
        if (choices.analytics === true && !state.isEnhanced) {
            enableEnhanced();
            return;
        }

        // Cas 2: Analytics REFUSÉ → rester en baseline (log diagnostic)
        if (choices.analytics === false) {
            log('Analytics refused → baseline only (no cookies)', 'info');
            // S'assurer que consent est bien denied (au cas où il était granted avant)
            if (window.gtag && state.isEnhanced) {
                gtag('consent', 'update', {
                    'analytics_storage': 'denied',
                    'ad_storage': 'denied',
                    'ad_user_data': 'denied',
                    'ad_personalization': 'denied'
                });
                log('Consent revoked → analytics_storage: denied', 'warning');
            }
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
     * Redirige vers enableEnhanced() si consentement présent
     */
    async function initialize() {
        // Si baseline pas encore prêt, l'initialiser d'abord
        if (!state.baselineReady) {
            await baselineInit();
        }

        // Si consentement présent, activer enhanced
        if (hasAnalyticsConsent() && !state.isEnhanced) {
            enableEnhanced();
        }
    }

    /**
     * Détecte si CookieConsent est bloqué par un adblock
     * Marque le flag state.cookieConsentBlocked si nécessaire
     */
    function detectCookieConsentBlocked() {
        if (!isCookieConsentAvailable()) {
            state.cookieConsentBlocked = true;
            log('CookieConsent missing or blocked (adblock?) → baseline only mode', 'warning');
            return true;
        }
        return false;
    }

    /**
     * Point d'entrée automatique - Architecture Consent Mode v2
     * 1. Lance le baseline immédiatement (cookieless)
     * 2. Détecte si CookieConsent est bloqué
     * 3. Configure les listeners pour le consentement
     * 4. Active enhanced si consentement déjà présent
     * 5. Fallback: vérifie le consentement après 500ms
     */
    async function autoInit() {
        // 1. Baseline immédiat pour TOUS les visiteurs (TOUJOURS)
        const baselineOk = await baselineInit();

        if (!baselineOk) {
            // gtag bloqué (adblock) - dégradation gracieuse
            log('Running in degraded mode (no analytics)', 'warning');
            return; // Rien à faire de plus si gtag est bloqué
        }

        // 2. Détecter si CookieConsent est bloqué
        const consentBlocked = detectCookieConsentBlocked();

        // 3. Configurer les listeners de consentement (même si bloqué, pour le cas où il charge tard)
        setupConsentListeners();

        // 4. Si CookieConsent bloqué → rester en baseline only (RGPD safe)
        if (consentBlocked) {
            log('Baseline analytics forced (no consent module)', 'info');
            return;
        }

        // 5. Vérifier si consentement déjà présent
        if (hasAnalyticsConsent()) {
            enableEnhanced();
        } else {
            // 6. Fallback: vérification unique après 500ms
            // (pour les cas où l'event consent n'est pas dispatché)
            setTimeout(() => {
                // Re-vérifier si CookieConsent est apparu entre temps
                if (detectCookieConsentBlocked()) {
                    return; // Toujours bloqué
                }
                if (hasAnalyticsConsent() && !state.isEnhanced) {
                    log('Consent detected via fallback check', 'info');
                    enableEnhanced();
                }
            }, 500);
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
        version: '2.5.2',

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

        // Nouvelles méthodes Consent Mode v2
        baselineInit: baselineInit,
        enableEnhanced: enableEnhanced,

        // Debug mode (via localStorage)
        setDebug: function(level) {
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

        // État CookieConsent bloqué (adblock)
        isCookieConsentBlocked: function() {
            return state.cookieConsentBlocked;
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
        console.log('[LotoIA GA4] Module v2.5.2 loaded - Baseline timing fix');
    }

})(window, document);

