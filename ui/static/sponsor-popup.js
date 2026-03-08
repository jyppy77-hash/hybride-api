/**
 * SPONSOR POPUP - Logique et Animations
 * Phase de calcul sponsorisée avec timer algorithmique
 *
 * @author Loto Analysis Team
 * @version 1.0
 */

// ============================================
// CONFIGURATION DES SPONSORS
// ============================================

const SPONSORS_CONFIG = [
    {
        id: 'LOTO_FR_A',
        name: 'Espace Premium',
        url: 'mailto:partenariats@lotoia.fr',
        icon: '⭐',
        description: 'Emplacement sponsor premium',
        displayUrl: 'partenariats@lotoia.fr',
        badge: 'Propulsé par',
        badgeType: 'primary'
    },
    {
        id: 'LOTO_FR_B',
        name: 'Votre marque ici',
        url: 'mailto:partenariats@lotoia.fr',
        icon: '📣',
        description: 'Audience forte • trafic qualifié',
        displayUrl: 'partenariats@lotoia.fr',
        badge: 'Avec le soutien de',
        badgeType: 'partner'
    }
];

// ============================================
// SÉQUENCE DE LOGS CONSOLE
// ============================================

/**
 * Génère la séquence de logs pour la console
 * @param {number} gridCount - Nombre de grilles
 * @param {number} duration - Durée totale en secondes
 * @returns {Array} Tableau de logs avec timing
 */
function getConsoleLogs(gridCount, duration) {
    // Phase 1 (connexions) : fixe ~2s, quelle que soit la durée totale
    // Phase 2 (calculs) : le reste du temps (variable selon 1→5 grilles)
    const fixedPhaseSec = 2;

    const fixedSteps = 5;   // index 0..4 = connexions
    const totalSteps = 15;  // index 0..14
    const variableSteps = totalSteps - fixedSteps;

    const variableDurationSec = Math.max(0, duration - fixedPhaseSec);
    const fixedStepSec = fixedPhaseSec / fixedSteps;
    const variableStepSec = variableSteps > 0 ? (variableDurationSec / variableSteps) : 0;

    const t = (i) => {
        if (i < fixedSteps) {
            return i * fixedStepSec;
        }
        return fixedPhaseSec + (i - fixedSteps) * variableStepSec;
    };

    return [
        { time: t(0), text: "> Initialisation HYBRIDE...", type: "info" },
        { time: t(1), text: "✓ Connexion moteur OK (127ms)", type: "success" },
        { time: t(2), text: "> Chargement base de données FDJ...", type: "info" },
        { time: t(3), text: `✓ ${(window.TOTAL_TIRAGES || 967).toLocaleString('fr-FR')} tirages chargés (342ms)`, type: "success" },
        { time: t(4), text: `> GET /api/analyze?grids=${gridCount}&mode=balanced`, type: "request" },
        { time: t(5), text: "⏳ Calcul fréquences historiques... 18%", type: "progress" },
        { time: t(6), text: "⏳ Détection patterns chauds... 34%", type: "progress" },
        { time: t(7), text: "⏳ Identification numéros froids... 51%", type: "progress" },
        { time: t(8), text: "⏳ Équilibrage pair/impair... 67%", type: "progress" },
        { time: t(9), text: "⏳ Calcul dispersion géographique... 78%", type: "progress" },
        { time: t(10), text: "⏳ Application contraintes soft... 85%", type: "progress" },
        { time: t(11), text: "⏳ Génération grilles optimisées... 92%", type: "progress" },
        { time: t(12), text: "⏳ Validation scores finaux... 0%", type: "progress", bindToGlobalProgress: true },
        { time: t(13), text: `✓ ${gridCount} grille${gridCount > 1 ? 's' : ''} générée${gridCount > 1 ? 's' : ''} avec succès`, type: "success", requires100: true },
        { time: t(14), text: "> Préparation affichage résultats...", type: "info", requires100: true },
        { time: t(14) + (variableStepSec * 0.5), text: "✓ Prêt à afficher", type: "success", requires100: true }
    ];
}

// ============================================
// CALCUL DE LA DURÉE DU TIMER
// ============================================

/**
 * Calcule la duree du timer selon le nombre de grilles
 * @param {number} gridCount - Nombre de grilles (1-5)
 * @returns {number} Duree en secondes
 */
function calculateTimerDuration(gridCount) {
    const timings = {
        1: 5,
        2: 8,
        3: 11,
        4: 13,
        5: 15
    };
    return timings[gridCount] || 5;
}

// ============================================
// GÉNÉRATION DU HTML DU POPUP
// ============================================

/**
 * Genere le HTML du popup sponsor
 * @param {Object} config - Configuration
 * @returns {string} HTML du popup
 */
function generatePopupHTML(config) {
    const { title, duration } = config;

    const sponsorsHTML = SPONSORS_CONFIG.map(sponsor => `
        <a href="${sponsor.url}" target="_blank" rel="noopener noreferrer nofollow sponsored"
           class="sponsor-card" data-sponsor="${sponsor.id}"
           onclick="trackSponsorClick('${sponsor.id}')">
            <span class="sponsor-badge ${sponsor.badgeType}">${sponsor.badge}</span>
            <div class="sponsor-logo">
                <span class="sponsor-logo-icon">${sponsor.icon}</span>
                ${sponsor.name}
            </div>
            <div class="sponsor-description">${sponsor.description}</div>
            <div class="sponsor-url">
                <span>→</span>
                <span>${sponsor.displayUrl}</span>
            </div>
        </a>
    `).join('');

    return `
        <div class="sponsor-popup-modal entering">
            <h2 class="popup-title">
                <span class="title-icon">⚙️</span>
                ${title}
            </h2>

            <div class="progress-bar-container">
                <div class="progress-bar-fill" id="sponsor-progress"></div>
            </div>
            <div class="progress-percentage" id="progress-text">0%</div>

            <div class="data-animation" id="data-animation"></div>

            <div class="console-container">
                <div class="console-header">
                    <span class="console-title">🖥️ MOTEUR HYBRIDE</span>
                    <span class="console-status" id="console-status">
                        <span class="status-dot"></span>PROCESSING
                    </span>
                </div>
                <div class="console-body" id="console-logs">
                    <div class="console-line console-ready">
                        <span class="console-prompt">$</span>
                        <span class="console-text">Système prêt</span>
                    </div>
                </div>
            </div>

            <div class="sponsors-header">Partenaires</div>
            <div class="sponsors-container">
                ${sponsorsHTML}
            </div>

            <div class="timer-circle-container">
                <div class="timer-circle">
                    <div class="timer-circle-bg"></div>
                    <div class="timer-circle-progress">
                        <svg viewBox="0 0 100 100">
                            <defs>
                                <linearGradient id="timerGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                    <stop offset="0%" stop-color="#10b981"/>
                                    <stop offset="50%" stop-color="#3b82f6"/>
                                    <stop offset="100%" stop-color="#8b5cf6"/>
                                </linearGradient>
                            </defs>
                            <circle class="track" cx="50" cy="50" r="40"/>
                            <circle class="fill" id="timer-circle-fill" cx="50" cy="50" r="40"/>
                        </svg>
                    </div>
                    <span class="timer-value" id="timer-display">${duration}</span>
                </div>
                <span class="timer-label">secondes</span>
            </div>
        </div>
    `;
}

// ============================================
// TRACKING (ANALYTICS)
// ============================================

/**
 * Track sponsor click for analytics
 * @param {string} sponsorId - ID du sponsor
 */
function trackSponsorClick(sponsorId) {
    // Umami — sponsor click
    if (typeof umami !== 'undefined') umami.track('sponsor-click', { sponsor: sponsorId, module: 'loto' });
    fetch('/api/sponsor/track', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ event_type: 'sponsor-click', sponsor_id: sponsorId, page: window.location.pathname, lang: document.documentElement.lang || 'fr', device: /Mobi|Android/i.test(navigator.userAgent) ? 'mobile' : 'desktop' }) }).catch(function() {});
    // GA4 Analytics - Track sponsor click
    if (window.LotoIAAnalytics && window.LotoIAAnalytics.business) {
        window.LotoIAAnalytics.business.sponsorClick({
            sponsor: sponsorId,
            sponsorId: sponsorId,
            placement: 'popup_console'
        });
    }

    // Tracking API call interne (avec vérification consentement RGPD)
    if (typeof fetch !== 'undefined' && window.LotoIAAnalytics?.utils?.hasConsent()) {
        fetch('/api/track-ad-click', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ad_id: sponsorId || 'unknown',
                partner_id: sponsorId || 'unknown',
                timestamp: Math.floor(Date.now() / 1000),
                session_id: sessionStorage.getItem('lotoia_session') || 'anonymous'
            })
        }).catch(() => {});
    }
    console.log(`[Sponsor] Click tracked: ${sponsorId}`);
}

/**
 * Track impression for analytics
 * @param {Array} sponsorIds - IDs des sponsors affiches
 */
function trackImpression(sponsorIds) {
    // GA4 Analytics - Track sponsor impressions
    if (window.LotoIAAnalytics && window.LotoIAAnalytics.business) {
        sponsorIds.forEach(sponsorId => {
            window.LotoIAAnalytics.business.sponsorImpression({
                sponsor: sponsorId,
                sponsorId: sponsorId,
                placement: 'popup_console'
            });
        });
    }

    // Tracking API call interne (avec vérification consentement RGPD)
    if (typeof fetch !== 'undefined' && window.LotoIAAnalytics?.utils?.hasConsent()) {
        fetch('/api/track-ad-impression', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ad_id: Array.isArray(sponsorIds) ? sponsorIds.join(',') : 'unknown',
                timestamp: Math.floor(Date.now() / 1000),
                session_id: sessionStorage.getItem('lotoia_session') || 'anonymous'
            })
        }).catch(() => {});
    }
    console.log(`[Sponsor] Impressions tracked: ${sponsorIds.join(', ')}`);
}

// ============================================
// ANIMATION MATRIX (CHIFFRES QUI DEFILENT)
// ============================================

/**
 * Genere une ligne de numeros Loto aleatoires (1-49)
 * @returns {string}
 */
function generateMatrixLine() {
    const segments = [];
    for (let i = 0; i < 8; i++) {
        // Numéros Loto valides : 1 à 49
        const num = Math.floor(Math.random() * 49) + 1;
        // Formatage sur 2 chiffres (01, 02, ... 49)
        segments.push(String(num).padStart(2, '0'));
    }
    return segments.join(' ');
}

// ============================================
// FONCTION PRINCIPALE DU POPUP
// ============================================

/**
 * Affiche le popup sponsor avec timer et animations
 * @param {Object} config - Configuration
 * @param {number} config.duration - Duree en secondes
 * @param {string} [config.title] - Titre du popup
 * @param {number} [config.gridCount] - Nombre de grilles (pour les logs)
 * @param {Function} [config.onComplete] - Callback a la fin
 * @returns {Promise} Promise resolue quand le popup se ferme
 */
function showSponsorPopup(config) {
    return new Promise((resolve) => {
        const {
            duration,
            title = 'HYBRIDE - Calcul en cours...',
            gridCount = 5,
            onComplete
        } = config;

        // Creer l'overlay
        const overlay = document.createElement('div');
        overlay.className = 'sponsor-popup-overlay';
        overlay.innerHTML = generatePopupHTML({ title, duration });

        // Flag d'annulation utilisateur (si true, on ne déclenche pas onComplete)
        let isCancelled = false;

        // Empecher la fermeture par clic sur l'overlay
        overlay.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';
        document.body.classList.add('sponsor-popup-active');

        // Umami — sponsor popup shown
        if (typeof umami !== 'undefined') umami.track('sponsor-popup-shown', { module: 'loto' });
        SPONSORS_CONFIG.forEach(function(s) {
            fetch('/api/sponsor/track', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ event_type: 'sponsor-popup-shown', sponsor_id: s.id, page: window.location.pathname, lang: document.documentElement.lang || 'fr', device: /Mobi|Android/i.test(navigator.userAgent) ? 'mobile' : 'desktop' }) }).catch(function() {});
        });

        // Bouton Annuler (style via CSS)
        const modal = overlay.querySelector('.sponsor-popup-modal');
        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'sponsor-cancel-btn';
        cancelBtn.textContent = 'Annuler';

        // Conteneur d'actions (positionnement bas/droite via CSS)
        const actions = document.createElement('div');
        actions.className = 'sponsor-popup-actions';
        actions.appendChild(cancelBtn);

        if (modal) {
            modal.appendChild(actions);
        } else {
            overlay.appendChild(actions);
        }

        cancelBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            isCancelled = true;
            closePopup();
        });

        // Track impressions
        trackImpression(SPONSORS_CONFIG.map(s => s.id));

        // Elements d'animation
        const progressBar = document.getElementById('sponsor-progress');
        const progressText = document.getElementById('progress-text');
        const timerDisplay = document.getElementById('timer-display');
        const timerCircleFill = document.getElementById('timer-circle-fill');
        const dataAnimation = document.getElementById('data-animation');
        const consoleBody = document.getElementById('console-logs');
        const consoleStatus = document.getElementById('console-status');

        // Calculer la circonference du cercle
        const circumference = 2 * Math.PI * 40; // r=40

        // Variables d'animation
        const startTime = Date.now();
        const durationMs = duration * 1000;
        let animationFrameId;
        let dataInterval;
        const logTimeouts = [];
        const dynamicIntervals = [];
        let boundProgressLine = null;
        let lastLogDisplayed = false;

        function getGlobalPercent() {
            const elapsedMs = Date.now() - startTime;
            const raw = Math.round((elapsedMs / durationMs) * 100);
            return Math.max(0, Math.min(100, raw));
        }

        // Animation des chiffres Matrix
        dataInterval = setInterval(() => {
            dataAnimation.textContent = generateMatrixLine();
        }, 80);

        // ============================================
        // ANIMATION CONSOLE - LOGS DYNAMIQUES
        // ============================================

        const logs = config.logs || getConsoleLogs(gridCount, duration);

        function addConsoleLog(log, nextDelayMs) {
            const line = document.createElement('div');
            line.className = `console-line console-${log.type}`;

            const prompt = document.createElement('span');
            prompt.className = 'console-prompt';
            prompt.textContent = '$';

            const text = document.createElement('span');
            text.className = 'console-text';
            text.textContent = log.text;

            const isProgress = log.type === 'progress';

            // Pour les lignes progress :
            // - on supprime le % du texte (sinon on voit 18/34/92% dans la console)
            // - on affiche le % dans la colonne CSS (data-pct) et on l’anime jusqu’à 100%
            if (isProgress) {
                const m = log.text.match(/(\d{1,3})\s*%\s*$/);
                const startPct = m ? Math.max(0, Math.min(100, parseInt(m[1], 10))) : 0;
                const baseText = log.text.replace(/\s*\d{1,3}\s*%\s*$/, '').trimEnd();
                text.textContent = baseText;

                line.setAttribute('data-pct', `${startPct}%`);

                const safeNextDelayMs = typeof nextDelayMs === 'number' ? nextDelayMs : 0;
                const animDurationMs = Math.max(120, Math.min(600, safeNextDelayMs - 50));
                const start = Date.now();

                const interval = setInterval(() => {
                    const elapsed = Date.now() - start;
                    const t = animDurationMs > 0 ? Math.min(elapsed / animDurationMs, 1) : 1;
                    const current = Math.max(startPct, Math.round(startPct + (100 - startPct) * t));

                    line.setAttribute('data-pct', `${current}%`);

                    if (t >= 1) {
                        line.setAttribute('data-pct', '100%');
                        clearInterval(interval);
                    }
                }, 33);

                dynamicIntervals.push(interval);
            }

            // Animation dynamique des % sur certaines lignes (hors "progress" CSS)
            if (!isProgress && (
                log.dynamicPercent &&
                typeof log.dynamicPercent.from === 'number' &&
                typeof log.dynamicPercent.to === 'number'
            )) {
                const from = log.dynamicPercent.from;
                const to = log.dynamicPercent.to;
                const prefix = typeof log.dynamicPercent.prefix === 'string' ? log.dynamicPercent.prefix : '';
                const suffix = typeof log.dynamicPercent.suffix === 'string' ? log.dynamicPercent.suffix : '';

                const safeNextDelayMs = typeof nextDelayMs === 'number' ? nextDelayMs : 0;
                const animDurationMs = Math.max(150, Math.min(600, safeNextDelayMs - 60));
                const start = Date.now();

                const interval = setInterval(() => {
                    const elapsed = Date.now() - start;
                    const t = animDurationMs > 0 ? Math.min(elapsed / animDurationMs, 1) : 1;
                    const current = Math.min(to, Math.max(from, Math.round(from + (to - from) * t)));

                    text.textContent = `${prefix}${current}%${suffix}`;

                    if (t >= 1) {
                        clearInterval(interval);
                    }
                }, 50);

                dynamicIntervals.push(interval);
            }

            line.appendChild(prompt);
            line.appendChild(text);
            consoleBody.appendChild(line);

            // Auto-scroll vers le bas
            consoleBody.scrollTop = consoleBody.scrollHeight;
        }

        // Planifier l'affichage de chaque log
        logs.forEach((log, index) => {
            const timeout = setTimeout(() => {
                const nextDelayMs = logs[index + 1]
                    ? (logs[index + 1].time - log.time) * 1000
                    : 0;

                const addNow = () => {
                    addConsoleLog(log, nextDelayMs);

                    if (index === logs.length - 1) {
                        lastLogDisplayed = true;

                        const markComplete = () => {
                            consoleStatus.innerHTML = `
                                <span class="status-dot status-complete"></span>COMPLETE
                            `;
                            consoleStatus.classList.add('complete');
                        };

                        if (getGlobalPercent() >= 100) {
                            markComplete();
                        } else {
                            const waitComplete = setInterval(() => {
                                if (getGlobalPercent() >= 100) {
                                    clearInterval(waitComplete);
                                    markComplete();
                                }
                            }, 30);
                            dynamicIntervals.push(waitComplete);
                        }
                    }
                };

                if (log.requires100 === true && getGlobalPercent() < 100) {
                    const wait100 = setInterval(() => {
                        if (getGlobalPercent() >= 100) {
                            clearInterval(wait100);
                            addNow();
                        }
                    }, 30);
                    dynamicIntervals.push(wait100);
                } else {
                    addNow();
                }
            }, log.time * 1000);
            logTimeouts.push(timeout);
        });

        // Fonction d'animation principale
        function animate() {
            const elapsed = Date.now() - startTime;
            const progress = Math.min(elapsed / durationMs, 1);
            const remaining = Math.max(0, duration - elapsed / 1000);
            const percent = getGlobalPercent();

            // Mettre a jour la barre de progression (100% partout)
            progressBar.style.width = `${percent}%`;
            progressText.textContent = `${percent}%`;

            // Synchroniser la ligne console finale au pourcentage global
            if (boundProgressLine) {
                boundProgressLine.textContent = `⏳ Validation scores finaux... ${percent}%`;
            }

            // Mettre a jour le timer
            timerDisplay.textContent = percent >= 100 ? '0' : String(Math.ceil(remaining));

            // Mettre a jour le cercle du timer
            const progressForCircle = percent / 100;
            const offset = circumference * (1 - progressForCircle);
            timerCircleFill.style.strokeDashoffset = offset;

            // Continuer ou terminer
            if (progress < 1 || !lastLogDisplayed) {
                animationFrameId = requestAnimationFrame(animate);
            } else {
                // Forcer visuellement 100% partout juste avant fermeture
                progressBar.style.width = '100%';
                progressText.textContent = '100%';
                if (boundProgressLine) {
                    boundProgressLine.textContent = '⏳ Validation scores finaux... 100%';
                }
                timerCircleFill.style.strokeDashoffset = 0;
                timerDisplay.textContent = '0';

                closePopup();
            }
        }

        // Fermer le popup
        function closePopup() {
            clearInterval(dataInterval);
            cancelAnimationFrame(animationFrameId);
            logTimeouts.forEach(t => clearTimeout(t));
            dynamicIntervals.forEach(i => clearInterval(i));

            overlay.classList.add('closing');

            setTimeout(() => {
                if (overlay.parentNode) {
                    document.body.removeChild(overlay);
                }
                document.body.style.overflow = '';
                document.body.classList.remove('sponsor-popup-active');

                // Callback (uniquement si pas annulé)
                if (!isCancelled && onComplete && typeof onComplete === 'function') {
                    onComplete();
                }

                resolve({ cancelled: isCancelled === true });
            }, 300);
        }

        // Demarrer l'animation
        animationFrameId = requestAnimationFrame(animate);
    });
}

// ============================================
// FONCTION WRAPPER POUR GÉNÉRATION DE GRILLES
// ============================================

/**
 * Wrapper pour afficher le popup avant generation de grilles
 * @param {number} gridCount - Nombre de grilles
 * @param {Function} generateCallback - Fonction de generation a executer apres
 */
async function showPopupBeforeGeneration(gridCount, generateCallback) {
    const duration = calculateTimerDuration(gridCount);
    const plural = gridCount > 1 ? 's' : '';

    const result = await showSponsorPopup({
        duration: duration,
        gridCount: gridCount,
        title: `Génération de ${gridCount} grille${plural} optimisée${plural}`
    });

    if (result && result.cancelled === true) {
        return;
    }

    if (generateCallback && typeof generateCallback === 'function') {
        generateCallback();
    }
}

// ============================================
// FONCTION WRAPPER POUR SIMULATEUR
// ============================================

/**
 * Wrapper pour afficher le popup avant simulation
 * @param {string} [title] - Titre personnalise
 * @param {Function} simulateCallback - Fonction de simulation a executer apres
 */
async function showPopupBeforeSimulation(title, simulateCallback) {
    const result = await showSponsorPopup({
        duration: 3, // Toujours 3 secondes pour le simulateur
        title: title || 'Analyse de votre grille en cours'
    });

    if (result && result.cancelled === true) {
        return;
    }

    if (simulateCallback && typeof simulateCallback === 'function') {
        simulateCallback();
    }
}

// ============================================
// EXPORTS (pour utilisation dans d'autres fichiers)
// ============================================

// Les fonctions sont disponibles globalement
window.showSponsorPopup = showSponsorPopup;
window.showPopupBeforeGeneration = showPopupBeforeGeneration;
window.showPopupBeforeSimulation = showPopupBeforeSimulation;
window.calculateTimerDuration = calculateTimerDuration;

console.log('[Sponsor Popup] Module loaded successfully');