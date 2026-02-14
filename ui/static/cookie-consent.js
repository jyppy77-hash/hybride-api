/**
 * LotoIA Cookie Consent Manager
 * Conforme aux recommandations CNIL (délibération n°2020-091)
 *
 * @version 1.0.0
 * @author JyppY
 */

const CookieConsent = (function() {
    'use strict';

    // ═══════════════════════════════════════════════════════════════════════
    // CONFIGURATION
    // ═══════════════════════════════════════════════════════════════════════

    const CONFIG = {
        // Clé de stockage du consentement
        storageKey: 'lotoia_cookie_consent',

        // Durée de validité du consentement (13 mois en jours)
        consentDuration: 395,

        // Catégories de cookies
        categories: {
            necessary: {
                id: 'necessary',
                name: 'Strictement nécessaires',
                description: 'Ces cookies sont indispensables au fonctionnement du site. Ils ne peuvent pas être désactivés.',
                required: true,
                cookies: ['lotoia_session', 'lotoia-theme', 'lotoia_cookie_consent']
            },
            analytics: {
                id: 'analytics',
                name: 'Mesure d\'audience',
                description: 'Ces cookies nous permettent de mesurer l\'audience du site et d\'améliorer nos services.',
                required: false,
                cookies: []
            },
            advertising: {
                id: 'advertising',
                name: 'Publicité et partenaires',
                description: 'Ces cookies permettent d\'afficher des publicités personnalisées et de mesurer leur efficacité.',
                required: false,
                cookies: []
            }
        }
    };

    // ═══════════════════════════════════════════════════════════════════════
    // ÉTAT
    // ═══════════════════════════════════════════════════════════════════════

    let consent = null;
    let bannerElement = null;
    let settingsElement = null;

    // ═══════════════════════════════════════════════════════════════════════
    // UTILITAIRES
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * Récupère le consentement stocké
     */
    function getStoredConsent() {
        try {
            const stored = localStorage.getItem(CONFIG.storageKey);
            if (!stored) return null;

            const data = JSON.parse(stored);

            // Vérifier l'expiration
            if (data.expires && new Date(data.expires) < new Date()) {
                localStorage.removeItem(CONFIG.storageKey);
                return null;
            }

            return data;
        } catch (e) {
            console.error('Erreur lecture consentement:', e);
            return null;
        }
    }

    /**
     * Sauvegarde le consentement
     */
    function saveConsent(choices) {
        const expires = new Date();
        expires.setDate(expires.getDate() + CONFIG.consentDuration);

        const data = {
            version: '1.0',
            date: new Date().toISOString(),
            expires: expires.toISOString(),
            choices: choices
        };

        try {
            localStorage.setItem(CONFIG.storageKey, JSON.stringify(data));
            consent = data;
        } catch (e) {
            console.error('Erreur sauvegarde consentement:', e);
        }
    }

    /**
     * Vérifie si une catégorie est acceptée
     */
    function isAccepted(category) {
        if (!consent || !consent.choices) return false;
        if (CONFIG.categories[category]?.required) return true;
        return consent.choices[category] === true;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INTERFACE UTILISATEUR
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * Crée le bandeau de consentement
     */
    function createBanner() {
        const banner = document.createElement('div');
        banner.id = 'cookie-consent-banner';
        banner.className = 'cookie-banner';
        banner.setAttribute('role', 'dialog');
        banner.setAttribute('aria-labelledby', 'cookie-banner-title');
        banner.setAttribute('aria-describedby', 'cookie-banner-desc');

        banner.innerHTML = `
            <div class="cookie-banner-content">
                <div class="cookie-banner-text">
                    <h2 id="cookie-banner-title">Gestion des cookies</h2>
                    <p id="cookie-banner-desc">
                        LotoIA.fr utilise des technologies de stockage local pour améliorer votre expérience.
                        Ces données restent sur votre appareil et ne sont pas partagées avec des tiers.
                        <a href="/politique-cookies">En savoir plus</a>
                    </p>
                </div>
                <div class="cookie-banner-actions">
                    <button type="button" class="cookie-btn cookie-btn-reject" id="cookie-reject-all">
                        Tout refuser
                    </button>
                    <button type="button" class="cookie-btn cookie-btn-settings" id="cookie-settings">
                        Personnaliser
                    </button>
                    <button type="button" class="cookie-btn cookie-btn-accept" id="cookie-accept-all">
                        Tout accepter
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(banner);
        bannerElement = banner;

        // Événements
        document.getElementById('cookie-accept-all').addEventListener('click', acceptAll);
        document.getElementById('cookie-reject-all').addEventListener('click', rejectAll);
        document.getElementById('cookie-settings').addEventListener('click', showSettings);

        // Animation d'entrée
        requestAnimationFrame(() => {
            banner.classList.add('cookie-banner-visible');
        });
    }

    /**
     * Crée le panneau de paramètres
     */
    function createSettings() {
        const settings = document.createElement('div');
        settings.id = 'cookie-consent-settings';
        settings.className = 'cookie-settings-overlay';
        settings.setAttribute('role', 'dialog');
        settings.setAttribute('aria-labelledby', 'cookie-settings-title');
        settings.setAttribute('aria-modal', 'true');

        let categoriesHTML = '';
        for (const [key, cat] of Object.entries(CONFIG.categories)) {
            const isRequired = cat.required;
            const isChecked = isRequired || (consent?.choices?.[key] === true);

            categoriesHTML += `
                <div class="cookie-category">
                    <div class="cookie-category-header">
                        <label class="cookie-toggle">
                            <input type="checkbox"
                                   name="cookie-${key}"
                                   ${isChecked ? 'checked' : ''}
                                   ${isRequired ? 'disabled' : ''}>
                            <span class="cookie-toggle-slider"></span>
                        </label>
                        <div class="cookie-category-info">
                            <h4>${cat.name}</h4>
                            ${isRequired ? '<span class="cookie-required">Requis</span>' : ''}
                        </div>
                    </div>
                    <p class="cookie-category-desc">${cat.description}</p>
                    ${cat.cookies.length > 0 ? `
                        <details class="cookie-details">
                            <summary>Voir les cookies (${cat.cookies.length})</summary>
                            <ul class="cookie-list">
                                ${cat.cookies.map(c => `<li><code>${c}</code></li>`).join('')}
                            </ul>
                        </details>
                    ` : ''}
                </div>
            `;
        }

        settings.innerHTML = `
            <div class="cookie-settings-panel">
                <div class="cookie-settings-header">
                    <h3 id="cookie-settings-title">Paramètres des cookies</h3>
                    <button type="button" class="cookie-close" id="cookie-close-settings" aria-label="Fermer">
                        &times;
                    </button>
                </div>
                <div class="cookie-settings-body">
                    <p class="cookie-settings-intro">
                        Vous pouvez choisir les catégories de cookies que vous souhaitez autoriser.
                        Les cookies strictement nécessaires ne peuvent pas être désactivés.
                    </p>
                    <div class="cookie-categories">
                        ${categoriesHTML}
                    </div>
                </div>
                <div class="cookie-settings-footer">
                    <button type="button" class="cookie-btn cookie-btn-reject" id="cookie-settings-reject">
                        Tout refuser
                    </button>
                    <button type="button" class="cookie-btn cookie-btn-save" id="cookie-settings-save">
                        Enregistrer mes choix
                    </button>
                    <button type="button" class="cookie-btn cookie-btn-accept" id="cookie-settings-accept">
                        Tout accepter
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(settings);
        settingsElement = settings;

        // Événements
        document.getElementById('cookie-close-settings').addEventListener('click', hideSettings);
        document.getElementById('cookie-settings-reject').addEventListener('click', () => {
            rejectAll();
            hideSettings();
        });
        document.getElementById('cookie-settings-save').addEventListener('click', saveSettings);
        document.getElementById('cookie-settings-accept').addEventListener('click', () => {
            acceptAll();
            hideSettings();
        });

        // Fermer en cliquant à l'extérieur
        settings.addEventListener('click', (e) => {
            if (e.target === settings) {
                hideSettings();
            }
        });

        // Fermer avec Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && settings.classList.contains('cookie-settings-visible')) {
                hideSettings();
            }
        });
    }

    /**
     * Affiche le panneau de paramètres
     */
    function showSettings() {
        if (!settingsElement) {
            createSettings();
        }
        settingsElement.classList.add('cookie-settings-visible');
        document.body.style.overflow = 'hidden';

        // Focus sur le premier élément interactif
        const firstInput = settingsElement.querySelector('input:not([disabled])');
        if (firstInput) firstInput.focus();
    }

    /**
     * Cache le panneau de paramètres
     */
    function hideSettings() {
        if (settingsElement) {
            settingsElement.classList.remove('cookie-settings-visible');
            document.body.style.overflow = '';
        }
    }

    /**
     * Cache le bandeau
     */
    function hideBanner() {
        if (bannerElement) {
            bannerElement.classList.remove('cookie-banner-visible');
            setTimeout(() => {
                bannerElement.remove();
                bannerElement = null;
            }, 300);
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ACTIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * Accepte tous les cookies
     */
    function acceptAll() {
        const choices = {};
        for (const key of Object.keys(CONFIG.categories)) {
            choices[key] = true;
        }
        saveConsent(choices);
        hideBanner();
        hideSettings();
        applyConsent();
    }

    /**
     * Refuse tous les cookies non essentiels
     */
    function rejectAll() {
        const choices = {};
        for (const [key, cat] of Object.entries(CONFIG.categories)) {
            choices[key] = cat.required;
        }
        saveConsent(choices);
        hideBanner();
        hideSettings();
        applyConsent();
    }

    /**
     * Sauvegarde les paramètres personnalisés
     */
    function saveSettings() {
        const choices = {};
        for (const [key, cat] of Object.entries(CONFIG.categories)) {
            if (cat.required) {
                choices[key] = true;
            } else {
                const checkbox = document.querySelector(`input[name="cookie-${key}"]`);
                choices[key] = checkbox ? checkbox.checked : false;
            }
        }
        saveConsent(choices);
        hideBanner();
        hideSettings();
        applyConsent();
    }

    /**
     * Applique le consentement (charge/bloque les scripts)
     */
    function applyConsent() {
        // Ici, vous pouvez charger des scripts tiers si l'utilisateur a consenti
        // Exemple: if (isAccepted('analytics')) { loadGoogleAnalytics(); }

        // Dispatch un événement pour que d'autres scripts puissent réagir
        document.dispatchEvent(new CustomEvent('cookieConsentUpdated', {
            detail: consent?.choices || {}
        }));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INITIALISATION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * Initialise le gestionnaire de consentement
     */
    function init() {
        // Récupérer le consentement existant
        consent = getStoredConsent();

        // Si pas de consentement, afficher le bandeau
        if (!consent) {
            // Attendre que le DOM soit prêt
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', createBanner);
            } else {
                createBanner();
            }
        } else {
            // Appliquer le consentement existant
            applyConsent();
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // API PUBLIQUE
    // ═══════════════════════════════════════════════════════════════════════

    return {
        init: init,
        showSettings: showSettings,
        hideSettings: hideSettings,
        acceptAll: acceptAll,
        rejectAll: rejectAll,
        isAccepted: isAccepted,
        getConsent: () => consent
    };

})();

// Initialisation automatique
CookieConsent.init();
