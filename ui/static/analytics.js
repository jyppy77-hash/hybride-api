/**
 * LotoIA Analytics Module
 * GA4 Integration avec gestion du consentement RGPD
 *
 * USAGE:
 * 1. Definir window.GA4_MEASUREMENT_ID avant de charger ce script
 * 2. Appeler LotoIA.Analytics.init() apres consentement utilisateur
 * 3. Utiliser LotoIA.Analytics.track() pour les events personnalises
 */

window.LotoIA = window.LotoIA || {};

LotoIA.Analytics = {

    // Configuration
    config: {
        measurementId: null,
        debug: false,
        initialized: false
    },

    /**
     * Initialise GA4 apres consentement utilisateur
     * @param {string} measurementId - GA4 Measurement ID (G-XXXXXXXXXX)
     */
    init: function(measurementId) {
        if (this.config.initialized) {
            console.warn('[LotoIA Analytics] Already initialized');
            return;
        }

        if (!measurementId) {
            console.error('[LotoIA Analytics] Missing measurementId');
            return;
        }

        this.config.measurementId = measurementId;

        // Charger gtag.js dynamiquement
        var script = document.createElement('script');
        script.async = true;
        script.src = 'https://www.googletagmanager.com/gtag/js?id=' + measurementId;
        document.head.appendChild(script);

        // Initialiser dataLayer
        window.dataLayer = window.dataLayer || [];
        function gtag() { dataLayer.push(arguments); }
        window.gtag = gtag;

        gtag('js', new Date());
        gtag('config', measurementId, {
            'anonymize_ip': true,
            'cookie_flags': 'SameSite=None;Secure'
        });

        this.config.initialized = true;
        console.log('[LotoIA Analytics] Initialized with ID:', measurementId);
    },

    /**
     * Envoie un event GA4
     * @param {string} eventName - Nom de l'event
     * @param {object} params - Parametres additionnels
     */
    track: function(eventName, params) {
        if (!this.config.initialized) {
            if (this.config.debug) {
                console.log('[LotoIA Analytics] Not initialized, event queued:', eventName);
            }
            return;
        }

        params = params || {};
        gtag('event', eventName, params);

        if (this.config.debug) {
            console.log('[LotoIA Analytics] Event:', eventName, params);
        }
    },

    // ========================================
    // EVENTS METIER LOTOIA
    // ========================================

    /**
     * Track generation de grilles
     * @param {number} count - Nombre de grilles generees
     * @param {string} mode - Mode de generation (balanced, conservative, recent)
     */
    trackGenerateGrid: function(count, mode) {
        this.track('generate_grid', {
            'event_category': 'engagement',
            'event_label': mode || 'balanced',
            'value': count || 1,
            'grid_count': count,
            'generation_mode': mode
        });
    },

    /**
     * Track simulation de grille personnalisee
     * @param {number} score - Score de la grille
     */
    trackSimulateGrid: function(score) {
        this.track('simulate_grid', {
            'event_category': 'engagement',
            'event_label': 'custom_grid',
            'value': score || 0,
            'grid_score': score
        });
    },

    /**
     * Track consultation des statistiques
     * @param {string} section - Section consultee (frequences, retards, top-flop)
     */
    trackViewStats: function(section) {
        this.track('view_stats', {
            'event_category': 'content',
            'event_label': section || 'general',
            'stats_section': section
        });
    },

    /**
     * Track recherche dans l'historique
     * @param {string} date - Date recherchee
     * @param {boolean} found - Tirage trouve ou non
     */
    trackSearchHistory: function(date, found) {
        this.track('search_history', {
            'event_category': 'search',
            'event_label': date,
            'search_date': date,
            'result_found': found
        });
    },

    /**
     * Track copie de grille
     * @param {string} gridId - ID de la grille copiee
     */
    trackCopyGrid: function(gridId) {
        this.track('copy_grid', {
            'event_category': 'engagement',
            'event_label': gridId,
            'grid_id': gridId
        });
    },

    /**
     * Track changement de theme (dark/light)
     * @param {string} theme - Theme selectionne
     */
    trackThemeChange: function(theme) {
        this.track('theme_change', {
            'event_category': 'preferences',
            'event_label': theme,
            'theme': theme
        });
    },

    /**
     * Track ouverture FAQ
     * @param {string} question - Question ouverte
     */
    trackFaqOpen: function(question) {
        this.track('faq_open', {
            'event_category': 'content',
            'event_label': question,
            'faq_question': question
        });
    }
};

// Export pour usage module
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LotoIA.Analytics;
}
