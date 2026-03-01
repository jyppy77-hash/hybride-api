/**
 * LotoIA Cookie Consent Manager
 * Conforme aux recommandations CNIL (délibération n°2020-091)
 * Multilingue : FR / EN / ES / PT / DE / NL
 *
 * @version 2.0.0
 * @author JyppY
 */

const CookieConsent = (function() {
    'use strict';

    // ═══════════════════════════════════════════════════════════════════════
    // I18N LABELS
    // ═══════════════════════════════════════════════════════════════════════

    const CONSENT_LABELS = {
        fr: {
            banner_title: 'Gestion des cookies',
            banner_text: 'LotoIA.fr utilise des technologies de stockage local pour améliorer votre expérience. Ces données restent sur votre appareil et ne sont pas partagées avec des tiers.',
            more: 'En savoir plus',
            accept_all: 'Tout accepter',
            reject_all: 'Tout refuser',
            customize: 'Personnaliser',
            settings_title: 'Paramètres des cookies',
            settings_close: 'Fermer',
            settings_intro: 'Vous pouvez choisir les catégories de cookies que vous souhaitez autoriser. Les cookies strictement nécessaires ne peuvent pas être désactivés.',
            settings_save: 'Enregistrer mes choix',
            required: 'Requis',
            see_cookies: 'Voir les cookies',
            cat_necessary: 'Strictement nécessaires',
            cat_necessary_desc: 'Ces cookies sont indispensables au fonctionnement du site. Ils ne peuvent pas être désactivés.',
            cat_analytics: "Mesure d'audience",
            cat_analytics_desc: "Ces cookies nous permettent de mesurer l'audience du site et d'améliorer nos services.",
            cat_advertising: 'Publicité et partenaires',
            cat_advertising_desc: "Ces cookies permettent d'afficher des publicités personnalisées et de mesurer leur efficacité."
        },
        en: {
            banner_title: 'Cookie management',
            banner_text: 'LotoIA.fr uses local storage technologies to improve your experience. This data stays on your device and is not shared with third parties.',
            more: 'Learn more',
            accept_all: 'Accept all',
            reject_all: 'Decline all',
            customize: 'Customize',
            settings_title: 'Cookie settings',
            settings_close: 'Close',
            settings_intro: 'You can choose which cookie categories you wish to allow. Strictly necessary cookies cannot be disabled.',
            settings_save: 'Save my choices',
            required: 'Required',
            see_cookies: 'View cookies',
            cat_necessary: 'Strictly necessary',
            cat_necessary_desc: 'These cookies are essential for the website to function. They cannot be disabled.',
            cat_analytics: 'Audience measurement',
            cat_analytics_desc: 'These cookies allow us to measure website traffic and improve our services.',
            cat_advertising: 'Advertising and partners',
            cat_advertising_desc: 'These cookies enable personalised advertising and measure its effectiveness.'
        },
        es: {
            banner_title: 'Gestión de cookies',
            banner_text: 'LotoIA.fr utiliza tecnologías de almacenamiento local para mejorar su experiencia. Estos datos permanecen en su dispositivo y no se comparten con terceros.',
            more: 'Más información',
            accept_all: 'Aceptar todo',
            reject_all: 'Rechazar todo',
            customize: 'Personalizar',
            settings_title: 'Configuración de cookies',
            settings_close: 'Cerrar',
            settings_intro: 'Puede elegir las categorías de cookies que desea permitir. Las cookies estrictamente necesarias no se pueden desactivar.',
            settings_save: 'Guardar mis opciones',
            required: 'Obligatorio',
            see_cookies: 'Ver cookies',
            cat_necessary: 'Estrictamente necesarias',
            cat_necessary_desc: 'Estas cookies son indispensables para el funcionamiento del sitio. No se pueden desactivar.',
            cat_analytics: 'Medición de audiencia',
            cat_analytics_desc: 'Estas cookies nos permiten medir el tráfico del sitio y mejorar nuestros servicios.',
            cat_advertising: 'Publicidad y socios',
            cat_advertising_desc: 'Estas cookies permiten mostrar publicidad personalizada y medir su eficacia.'
        },
        pt: {
            banner_title: 'Gestão de cookies',
            banner_text: 'O LotoIA.fr utiliza tecnologias de armazenamento local para melhorar a sua experiência. Estes dados permanecem no seu dispositivo e não são partilhados com terceiros.',
            more: 'Saber mais',
            accept_all: 'Aceitar tudo',
            reject_all: 'Recusar tudo',
            customize: 'Personalizar',
            settings_title: 'Definições de cookies',
            settings_close: 'Fechar',
            settings_intro: 'Pode escolher as categorias de cookies que pretende permitir. Os cookies estritamente necessários não podem ser desativados.',
            settings_save: 'Guardar as minhas escolhas',
            required: 'Obrigatório',
            see_cookies: 'Ver cookies',
            cat_necessary: 'Estritamente necessários',
            cat_necessary_desc: 'Estes cookies são indispensáveis para o funcionamento do site. Não podem ser desativados.',
            cat_analytics: 'Medição de audiência',
            cat_analytics_desc: 'Estes cookies permitem-nos medir o tráfego do site e melhorar os nossos serviços.',
            cat_advertising: 'Publicidade e parceiros',
            cat_advertising_desc: 'Estes cookies permitem apresentar publicidade personalizada e medir a sua eficácia.'
        },
        de: {
            banner_title: 'Cookie-Verwaltung',
            banner_text: 'LotoIA.fr verwendet lokale Speichertechnologien, um Ihre Erfahrung zu verbessern. Diese Daten verbleiben auf Ihrem Gerät und werden nicht an Dritte weitergegeben.',
            more: 'Mehr erfahren',
            accept_all: 'Alle akzeptieren',
            reject_all: 'Alle ablehnen',
            customize: 'Anpassen',
            settings_title: 'Cookie-Einstellungen',
            settings_close: 'Schließen',
            settings_intro: 'Sie können die Cookie-Kategorien auswählen, die Sie zulassen möchten. Unbedingt erforderliche Cookies können nicht deaktiviert werden.',
            settings_save: 'Meine Auswahl speichern',
            required: 'Erforderlich',
            see_cookies: 'Cookies anzeigen',
            cat_necessary: 'Unbedingt erforderlich',
            cat_necessary_desc: 'Diese Cookies sind für die Funktion der Website unerlässlich. Sie können nicht deaktiviert werden.',
            cat_analytics: 'Reichweitenmessung',
            cat_analytics_desc: 'Diese Cookies ermöglichen es uns, den Datenverkehr der Website zu messen und unsere Dienste zu verbessern.',
            cat_advertising: 'Werbung und Partner',
            cat_advertising_desc: 'Diese Cookies ermöglichen personalisierte Werbung und die Messung ihrer Wirksamkeit.'
        },
        nl: {
            banner_title: 'Cookiebeheer',
            banner_text: 'LotoIA.fr gebruikt lokale opslagtechnologieën om uw ervaring te verbeteren. Deze gegevens blijven op uw apparaat en worden niet gedeeld met derden.',
            more: 'Meer informatie',
            accept_all: 'Alles accepteren',
            reject_all: 'Alles weigeren',
            customize: 'Aanpassen',
            settings_title: 'Cookie-instellingen',
            settings_close: 'Sluiten',
            settings_intro: 'U kunt kiezen welke cookiecategorieën u wilt toestaan. Strikt noodzakelijke cookies kunnen niet worden uitgeschakeld.',
            settings_save: 'Mijn keuzes opslaan',
            required: 'Vereist',
            see_cookies: 'Cookies bekijken',
            cat_necessary: 'Strikt noodzakelijk',
            cat_necessary_desc: 'Deze cookies zijn onmisbaar voor de werking van de website. Ze kunnen niet worden uitgeschakeld.',
            cat_analytics: 'Publieksmeting',
            cat_analytics_desc: 'Deze cookies stellen ons in staat het websiteverkeer te meten en onze diensten te verbeteren.',
            cat_advertising: 'Reclame en partners',
            cat_advertising_desc: 'Deze cookies maken gepersonaliseerde reclame mogelijk en meten de doeltreffendheid ervan.'
        }
    };

    /**
     * Detect current page language
     */
    function getLang() {
        var lang = window.LotoIA_lang || document.documentElement.lang || 'fr';
        return CONSENT_LABELS[lang] ? lang : 'fr';
    }

    /**
     * Get labels for current language
     */
    function getLabels() {
        return CONSENT_LABELS[getLang()];
    }

    /**
     * Get cookie policy URL for current page context
     */
    function getCookiePolicyUrl() {
        var lang = getLang();
        var path = window.location.pathname;
        var isEM = path.indexOf('/euromillions') !== -1;

        if (!isEM) return '/politique-cookies';
        if (lang === 'fr') return '/euromillions/cookies';
        return '/' + lang + '/euromillions/cookies';
    }

    // ═══════════════════════════════════════════════════════════════════════
    // CONFIGURATION
    // ═══════════════════════════════════════════════════════════════════════

    const CONFIG = {
        // Clé de stockage du consentement
        storageKey: 'lotoia_cookie_consent',

        // Durée de validité du consentement (13 mois en jours)
        consentDuration: 395,

        // Catégories de cookies (id, required, cookies list)
        categories: {
            necessary: {
                id: 'necessary',
                required: true,
                cookies: ['lotoia_session', 'lotoia-theme', 'lotoia_cookie_consent']
            },
            analytics: {
                id: 'analytics',
                required: false,
                cookies: []
            },
            advertising: {
                id: 'advertising',
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
        const L = getLabels();
        const cookieUrl = getCookiePolicyUrl();

        const banner = document.createElement('div');
        banner.id = 'cookie-consent-banner';
        banner.className = 'cookie-banner';
        banner.setAttribute('role', 'dialog');
        banner.setAttribute('aria-labelledby', 'cookie-banner-title');
        banner.setAttribute('aria-describedby', 'cookie-banner-desc');

        banner.innerHTML = `
            <div class="cookie-banner-content">
                <div class="cookie-banner-text">
                    <h2 id="cookie-banner-title">${L.banner_title}</h2>
                    <p id="cookie-banner-desc">
                        ${L.banner_text}
                        <a href="${cookieUrl}">${L.more}</a>
                    </p>
                </div>
                <div class="cookie-banner-actions">
                    <button type="button" class="cookie-btn cookie-btn-reject" id="cookie-reject-all">
                        ${L.reject_all}
                    </button>
                    <button type="button" class="cookie-btn cookie-btn-settings" id="cookie-settings">
                        ${L.customize}
                    </button>
                    <button type="button" class="cookie-btn cookie-btn-accept" id="cookie-accept-all">
                        ${L.accept_all}
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
        const L = getLabels();

        const CAT_LABELS = {
            necessary:   { name: L.cat_necessary,   desc: L.cat_necessary_desc },
            analytics:   { name: L.cat_analytics,   desc: L.cat_analytics_desc },
            advertising: { name: L.cat_advertising, desc: L.cat_advertising_desc }
        };

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
            const cl = CAT_LABELS[key] || { name: key, desc: '' };

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
                            <h4>${cl.name}</h4>
                            ${isRequired ? '<span class="cookie-required">' + L.required + '</span>' : ''}
                        </div>
                    </div>
                    <p class="cookie-category-desc">${cl.desc}</p>
                    ${cat.cookies.length > 0 ? `
                        <details class="cookie-details">
                            <summary>${L.see_cookies} (${cat.cookies.length})</summary>
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
                    <h3 id="cookie-settings-title">${L.settings_title}</h3>
                    <button type="button" class="cookie-close" id="cookie-close-settings" aria-label="${L.settings_close}">
                        &times;
                    </button>
                </div>
                <div class="cookie-settings-body">
                    <p class="cookie-settings-intro">
                        ${L.settings_intro}
                    </p>
                    <div class="cookie-categories">
                        ${categoriesHTML}
                    </div>
                </div>
                <div class="cookie-settings-footer">
                    <button type="button" class="cookie-btn cookie-btn-reject" id="cookie-settings-reject">
                        ${L.reject_all}
                    </button>
                    <button type="button" class="cookie-btn cookie-btn-save" id="cookie-settings-save">
                        ${L.settings_save}
                    </button>
                    <button type="button" class="cookie-btn cookie-btn-accept" id="cookie-settings-accept">
                        ${L.accept_all}
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
