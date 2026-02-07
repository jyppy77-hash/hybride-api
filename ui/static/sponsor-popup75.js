/**
 * SPONSOR POPUP 75 - META ANALYSE
 * Phase de calcul sponsorisée avec timer algorithmique
 * Tunnel premium vers analyse 75 grilles
 *
 * @author Loto Analysis Team
 * @version 2.0
 */

// ============================================
// CONFIGURATION META ANALYSE
// ============================================

/**
 * Durée du timer sponsor META ANALYSE (en secondes)
 * Modifiable via cette variable unique
 */
const META_ANALYSE_TIMER_DURATION = 30;

// ============================================
// CONFIGURATION DES SPONSORS (UN SEUL SPONSOR CENTRÉ)
// ============================================

const SPONSORS_CONFIG_75 = [
    {
        id: 'annonceur',
        name: 'Votre marque ici',
        url: 'mailto:partenariats@lotoia.fr',
        icon: '📣',
        description: 'Audience forte • trafic qualifié',
        displayUrl: 'partenariats@lotoia.fr',
        badge: 'Espace partenaire',
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
 * @param {Object} options - Options supplémentaires
 * @param {number} options.rowsToAnalyze - Nombre de tirages à analyser
 * @param {boolean} options.isGlobal - True si analyse sur base complète
 * @returns {Array} Tableau de logs avec timing
 */
function getConsoleLogs(gridCount, duration, options = {}) {
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

    // Texte pour le nombre de tirages analysés
    const rowsCount = options.rowsToAnalyze || window.TOTAL_TIRAGES || 967;
    const rowsFormatted = rowsCount.toLocaleString('fr-FR');
    const tiragesText = options.isGlobal
        ? `✓ ${rowsFormatted} tirages analysés (base complète)`
        : `✓ ${rowsFormatted} tirages analysés`;

    return [
        { time: t(0), text: "> Initialisation HYBRIDE_OPTIMAL_V1...", type: "info" },
        { time: t(1), text: "✓ Connexion moteur OK (127ms)", type: "success" },
        { time: t(2), text: "> Chargement base de données FDJ...", type: "info" },
        { time: t(3), text: tiragesText, type: "success" },
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
function generatePopupHTML75(config) {
    const { title, duration, isMetaAnalyse = false } = config;

    // Badge META ANALYSE si activé
    const metaAnalyseBadge = isMetaAnalyse
        ? `<div class="meta-analyse-badge">Fenêtre META ANALYSE</div>`
        : '';

    // Sponsor unique centré avec ratio 16:9
    const sponsorsHTML = SPONSORS_CONFIG_75.map(sponsor => `
        <a href="${sponsor.url}" target="_blank" rel="noopener noreferrer"
           class="sponsor-card sponsor-card-single sponsor-card-16x9" data-sponsor="${sponsor.id}"
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
        <div class="sponsor-popup-modal entering${isMetaAnalyse ? ' meta-analyse-modal' : ''}">
            ${metaAnalyseBadge}
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
                    <span class="console-title">🖥️ MOTEUR HYBRIDE_OPTIMAL_V1</span>
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

            <div class="sponsors-header">Partenaire</div>
            <div class="sponsors-container sponsors-container-single">
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
    // GA4 Analytics - Track sponsor click
    if (window.LotoIAAnalytics && window.LotoIAAnalytics.business) {
        window.LotoIAAnalytics.business.sponsorClick({
            sponsor: sponsorId,
            sponsorId: sponsorId,
            placement: 'popup_console'
        });
    }

    // Tracking API call interne (si disponible)
    if (typeof fetch !== 'undefined') {
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

    // Tracking API call interne (si disponible)
    if (typeof fetch !== 'undefined') {
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
function showSponsorPopup75(config) {
    return new Promise((resolve) => {
        const {
            duration,
            title = 'HYBRIDE_OPTIMAL_V1 - Calcul en cours...',
            gridCount = 5,
            onComplete,
            isMetaAnalyse = false
        } = config;

        // Creer l'overlay
        const overlay = document.createElement('div');
        overlay.className = 'sponsor-popup-overlay';
        overlay.innerHTML = generatePopupHTML75({ title, duration });

        // Flag d'annulation utilisateur (si true, on ne déclenche pas onComplete)
        let isCancelled = false;

        // Empecher la fermeture par clic sur l'overlay
        overlay.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';
        document.body.classList.add('sponsor-popup-active');

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
        trackImpression(SPONSORS_CONFIG_75.map(s => s.id));

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

        // META ANALYSE : logs finaux dans les 2 dernières secondes
        let finalLogsTriggered = false;
        const finalMetaLogs = [
            { delay: 0,    text: 'Analyse 75 grilles...',        type: 'info' },
            { delay: 350,  text: 'Création graphique...',        type: 'info' },
            { delay: 700,  text: 'Rapport PDF...',               type: 'info' },
            { delay: 1050, text: 'Validation finale...',         type: 'info' },
            { delay: 1400, text: 'Analyse prête.',               type: 'success' }
        ];

        function triggerFinalMetaLogs() {
            if (finalLogsTriggered || !isMetaAnalyse) return;
            finalLogsTriggered = true;

            finalMetaLogs.forEach(log => {
                const timeout = setTimeout(() => {
                    addConsoleLog(log, 300);
                }, log.delay);
                logTimeouts.push(timeout);
            });
        }

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
            // - on affiche le % dans la colonne CSS (data-pct) et on l'anime jusqu'à 100%
            // - l'animation se termine 200-300ms AVANT la ligne suivante (pas de pause à 100%)
            if (isProgress) {
                const m = log.text.match(/(\d{1,3})\s*%\s*$/);
                const startPct = m ? Math.max(0, Math.min(100, parseInt(m[1], 10))) : 0;
                const baseText = log.text.replace(/\s*\d{1,3}\s*%\s*$/, '').trimEnd();
                text.textContent = baseText;

                line.setAttribute('data-pct', `${startPct}%`);

                const safeNextDelayMs = typeof nextDelayMs === 'number' ? nextDelayMs : 0;
                // Animation se termine 250ms avant la ligne suivante (pause max après 100%)
                const animDurationMs = Math.max(100, safeNextDelayMs - 250);
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
                }, 25); // Intervalle réduit pour animation plus fluide

                dynamicIntervals.push(interval);
            }

            // Animation dynamique des % sur certaines lignes (hors "progress" CSS)
            // Animation se termine 200ms avant la ligne suivante (pas de pause visible)
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
                // Animation se termine 200ms avant la ligne suivante
                const animDurationMs = Math.max(100, safeNextDelayMs - 200);
                const start = Date.now();

                const interval = setInterval(() => {
                    const elapsed = Date.now() - start;
                    const t = animDurationMs > 0 ? Math.min(elapsed / animDurationMs, 1) : 1;
                    const current = Math.min(to, Math.max(from, Math.round(from + (to - from) * t)));

                    text.textContent = `${prefix}${current}%${suffix}`;

                    if (t >= 1) {
                        clearInterval(interval);
                    }
                }, 25); // Intervalle réduit pour animation plus fluide

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

            // META ANALYSE : déclencher logs finaux à 2 secondes restantes
            if (isMetaAnalyse && remaining <= 2 && !finalLogsTriggered) {
                triggerFinalMetaLogs();
            }

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

    const result = await showSponsorPopup75({
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
    const result = await showSponsorPopup75({
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
// FONCTION META ANALYSE - POINT D'ENTRÉE PRINCIPAL
// ============================================

/**
 * Génère le HTML du graphique à barres
 * @param {Object} graph - Données du graphique {labels, values}
 * @returns {string} HTML du graphique
 */
function generateGraphBarsHTML(graph) {
    if (!graph || !graph.labels || !graph.values) {
        return '<p style="color:#6b7280;">Graphique non disponible</p>';
    }

    const maxValue = Math.max(...graph.values);
    const bars = graph.labels.map((label, i) => {
        const value = graph.values[i] || 0;
        const heightPercent = maxValue > 0 ? (value / maxValue) * 100 : 0;
        return `
            <div class="meta-result-bar" style="height: ${heightPercent}%;">
                <span class="meta-result-bar-value">${value}</span>
                <span class="meta-result-bar-label">${label}</span>
            </div>
        `;
    }).join('');

    return bars;
}

/**
 * Ouvre le pop-up de résultats META ANALYSE
 * @param {Object} data - Données de l'API mock
 */
function openMetaResultPopup(data) {
    console.log('[META ANALYSE] Ouverture pop-up résultat', data);

    // EVENT 3 - Analyse terminée
    var durationMs = META_ANALYSE_START_TIME ? (Date.now() - META_ANALYSE_START_TIME) : 0;
    if (window.LotoIAAnalytics?.productEngine?.track) {
        window.LotoIAAnalytics.productEngine.track('meta_analysis_complete', {
            version: 75,
            source: data.source || 'unknown',
            duration_ms: durationMs
        });
    }

    const graphBars = generateGraphBarsHTML(data.graph);
    const analysisText = finalAnalysisText;
    const analysisSource = window._metaAnalysisSource || 'unknown';
    console.log('[UI] analysisText source:', analysisSource, '— length:', analysisText ? analysisText.length : 0);

    // Badge source visible — transparence utilisateur
    const sourceLabel = analysisSource === 'gemini_enriched'
        ? '<span class="meta-source-badge gemini">🧠 Analyse Gemini enrichie</span>'
        : '<span class="meta-source-badge local">⚠️ Analyse locale (Gemini indisponible)</span>';

    const pdfEnabled = true;

    const overlay = document.createElement('div');
    overlay.className = 'meta-result-overlay';
    overlay.innerHTML = `
        <div class="meta-result-modal">
            <div class="meta-result-header">
                <h2 class="meta-result-title">
                    <span class="meta-result-title-icon">📊</span>
                    Résultat META ANALYSE
                </h2>
                <p class="meta-result-subtitle">Analyse basée sur 75 grilles simulées</p>
            </div>

            <div class="meta-result-graph">
                <div class="meta-result-graph-title">Convergence statistique</div>
                <div class="meta-result-bars">
                    ${graphBars}
                </div>
            </div>

            <div class="meta-result-analysis">
                <div class="meta-result-analysis-title">
                    ${sourceLabel}
                </div>
                <p class="meta-result-analysis-text">${analysisText}</p>
            </div>

            <div class="meta-result-actions">
                <button class="meta-result-btn meta-result-btn-close" id="meta-result-close">
                    Fermer
                </button>
                <button class="meta-result-btn meta-result-btn-pdf" id="meta-result-pdf" ${pdfEnabled ? '' : 'disabled'}>
                    <span>📄</span>
                    ${pdfEnabled ? 'Télécharger le rapport META' : 'Exporter PDF'}
                    ${pdfEnabled ? '' : '<span class="meta-result-btn-pdf-badge">Bientôt</span>'}
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';

    // Event listeners
    const closeBtn = overlay.querySelector('#meta-result-close');
    const pdfBtn = overlay.querySelector('#meta-result-pdf');

    function closePopup() {
        overlay.classList.add('closing');
        setTimeout(() => {
            if (overlay.parentNode) {
                document.body.removeChild(overlay);
            }
            document.body.style.overflow = '';
        }, 250);
    }

    closeBtn.addEventListener('click', closePopup);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closePopup();
    });

    // EVENT 4 - Export PDF — source unique : finalAnalysisText
    if (pdfBtn) {
        pdfBtn.addEventListener('click', () => {
            if (window.LotoIAAnalytics?.productEngine?.track) {
                window.LotoIAAnalytics.productEngine.track('meta_pdf_export', { version: 75 });
            }

            if (!finalAnalysisText) {
                console.warn('[PDF] finalAnalysisText est null — blocage');
                alert('Analyse avancée encore en cours...');
                return;
            }

            console.log('[PDF] finalAnalysisText:', finalAnalysisText.substring(0, 120));
            console.log('[META PDF] graph_data sent:', metaResultData && metaResultData.graph ? metaResultData.graph : null);

            fetch('/api/meta-pdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    analysis: finalAnalysisText,
                    window: '75 tirages',
                    engine: 'HYBRIDE_OPTIMAL_V1',
                    graph_data: metaResultData && metaResultData.graph ? metaResultData.graph : null,
                    sponsor: 'Espace disponible'
                })
            })
            .then(function(res) { return res.blob(); })
            .then(function(blob) {
                var url = URL.createObjectURL(blob);
                window.open(url, '_blank');
            })
            .catch(function(err) {
                console.error('[PDF] Erreur generation:', err);
            });
        });
    }
}

/**
 * Ouvre le pop-up de fallback en cas d'erreur
 */
function openMetaResultPopupFallback() {
    console.warn('[META ANALYSE] Fallback activé - données non disponibles');

    const overlay = document.createElement('div');
    overlay.className = 'meta-result-overlay';
    overlay.innerHTML = `
        <div class="meta-result-modal">
            <div class="meta-result-fallback">
                <div class="meta-result-fallback-icon">⚠️</div>
                <p class="meta-result-fallback-text">
                    Résultat temporairement indisponible.<br>
                    Veuillez réessayer dans quelques instants.
                </p>
                <button class="meta-result-btn meta-result-btn-close" id="meta-result-close-fallback">
                    Fermer
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';

    const closeBtn = overlay.querySelector('#meta-result-close-fallback');

    function closePopup() {
        overlay.classList.add('closing');
        setTimeout(() => {
            if (overlay.parentNode) {
                document.body.removeChild(overlay);
            }
            document.body.style.overflow = '';
        }, 250);
    }

    closeBtn.addEventListener('click', closePopup);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closePopup();
    });
}

// ==============================================
// SOURCE DE VÉRITÉ UNIQUE — Analyse Gemini
// ==============================================

var finalAnalysisText = null;
var metaResultData = null;
var metaAnalysisPromise = null;
window._metaAnalysisSource = null;

/**
 * Construit l'URL de l'API locale selon le mode slider.
 * @returns {string}
 */
function buildMetaLocalUrl() {
    var currentMode = (typeof metaCurrentMode !== 'undefined') ? metaCurrentMode : 'tirages';
    var apiUrl = '/api/meta-analyse-local';

    if (currentMode === 'annees' && typeof metaYearsSize !== 'undefined' && metaYearsSize) {
        apiUrl += '?years=' + encodeURIComponent(metaYearsSize);
    } else {
        var windowParam = (typeof metaWindowSize !== 'undefined' && metaWindowSize) ? metaWindowSize : 'GLOBAL';
        apiUrl += '?window=' + encodeURIComponent(windowParam);
    }
    return apiUrl;
}

/**
 * Lance fetch local + Gemini à T=0.
 * Retourne une Promise qui se résout quand finalAnalysisText est prêt.
 * Timeout Gemini : 25 secondes.
 * @returns {Promise}
 */
function triggerGeminiEarly() {
    var t0 = Date.now();
    console.log('[GEM] START T=0');

    finalAnalysisText = null;
    metaResultData = null;
    window._metaAnalysisSource = null;

    var apiUrl = buildMetaLocalUrl();

    // Chaîne complète : local fetch → Gemini fetch
    var chainPromise = fetch(apiUrl)
        .then(function(response) {
            if (!response.ok) throw new Error('Local HTTP ' + response.status);
            return response.json();
        })
        .then(function(data) {
            if (!data.success) throw new Error('API local: success=false');

            var localText = data.analysis;
            console.log('[GEM] Local OK (' + (localText ? localText.length : 0) + ' chars) T+' + (Date.now() - t0) + 'ms');

            return fetch('/api/meta-analyse-texte', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    analysis_local: data.analysis,
                    stats: data.graph,
                    window: (data.meta && data.meta.window_used) ? data.meta.window_used : 'GLOBAL'
                })
            })
            .then(function(r) {
                if (!r.ok) throw new Error('Gemini HTTP ' + r.status);
                return r.json();
            })
            .then(function(gem) {
                console.log('[GEM] Response T+' + (Date.now() - t0) + 'ms, source:', gem ? gem.source : 'N/A');
                var enriched = gem && gem.analysis_enriched;
                if (!enriched || typeof enriched !== 'string' || enriched.trim().length === 0) {
                    throw new Error('analysis_enriched manquant — keys: ' + (gem ? Object.keys(gem).join(',') : 'NULL'));
                }
                if (gem.source && gem.source !== 'gemini_enriched') {
                    throw new Error('Backend fallback local — source: ' + gem.source);
                }
                console.log('[GEM] ENRICHED OK (' + enriched.length + ' chars) T+' + (Date.now() - t0) + 'ms');
                finalAnalysisText = enriched;
                window._metaAnalysisSource = 'gemini_enriched';
                data.analysis = enriched;
                data.source = 'gemini_enriched';
                metaResultData = data;
            })
            .catch(function(gemErr) {
                console.warn('[GEM] Gemini échoué T+' + (Date.now() - t0) + 'ms:', gemErr);
                // finalAnalysisText reste null — PAS de fallback silencieux
                window._metaAnalysisSource = 'gemini_failed';
                data._localText = localText;
                data.source = 'gemini_failed';
                metaResultData = data;
            });
        });

    // Timeout GLOBAL depuis T=0 — 28s (avant le timer 30s)
    var globalTimeout = new Promise(function(_, reject) {
        setTimeout(function() { reject('GLOBAL_TIMEOUT_28S'); }, 28000);
    });

    metaAnalysisPromise = Promise.race([chainPromise, globalTimeout])
        .catch(function(err) {
            console.error('[GEM] TIMEOUT ou erreur fatale T+' + (Date.now() - t0) + 'ms:', err);
            // Fallback local UNIQUEMENT sur timeout global explicite
            if (err === 'GLOBAL_TIMEOUT_28S' && !finalAnalysisText && metaResultData && metaResultData._localText) {
                console.warn('[GEM] Timeout 28s — fallback explicite vers analyse locale');
                finalAnalysisText = metaResultData._localText;
                window._metaAnalysisSource = 'timeout_fallback_local';
                metaResultData.source = 'timeout_fallback_local';
            }
        });

    return metaAnalysisPromise;
}

/**
 * Callback de fin du timer sponsor.
 * Attend la Promise Gemini puis ouvre le résultat.
 * Aucun polling, aucun setInterval.
 * @private
 */
function onMetaAnalyseComplete() {
    console.log('[META ANALYSE] Timer terminé — attente Promise Gemini...');

    if (!metaAnalysisPromise) {
        console.error('[META ANALYSE] Aucune Promise — fallback UI');
        openMetaResultPopupFallback();
        return;
    }

    metaAnalysisPromise
        .then(function() {
            // CAS 1 — Gemini enrichi OK (ou timeout fallback déjà assigné)
            if (finalAnalysisText && metaResultData) {
                console.log('[META ANALYSE] finalAnalysisText OK — source:', window._metaAnalysisSource);
                openMetaResultPopup(metaResultData);
            }
            // CAS 2 — Gemini échoué, local disponible → fallback EXPLICITE
            else if (metaResultData && metaResultData._localText) {
                console.warn('[META ANALYSE] Gemini indisponible — fallback explicite local');
                finalAnalysisText = metaResultData._localText;
                window._metaAnalysisSource = 'explicit_local_fallback';
                metaResultData.source = 'explicit_local_fallback';
                openMetaResultPopup(metaResultData);
            }
            // CAS 3 — Aucune donnée exploitable
            else {
                console.error('[META ANALYSE] Aucune donnée — ni Gemini ni local');
                openMetaResultPopupFallback();
            }
        })
        .catch(function(err) {
            console.error('[META ANALYSE] Promise rejetée:', err);
            openMetaResultPopupFallback();
        });
}

// Variable globale pour tracking durée META ANALYSE
var META_ANALYSE_START_TIME = null;

/**
 * Point d'entrée pour le bouton "Meta Data 75 Grilles"
 * Ouvre la fenêtre META ANALYSE sponsorisée avec timer 30 secondes
 * Ne déclenche JAMAIS directement le moteur HYBRIDE
 *
 * @returns {Promise} Promise résolue quand le popup se ferme
 */
async function showMetaAnalysePopup() {
    console.log('[META ANALYSE] Ouverture fenêtre META ANALYSE 75 grilles');

    // EVENT 2 - Début tunnel sponsor
    META_ANALYSE_START_TIME = Date.now();
    if (window.LotoIAAnalytics?.productEngine?.track) {
        window.LotoIAAnalytics.productEngine.track('meta_tunnel_start', { version: 75 });
    }

    // Déterminer le nombre de tirages à analyser selon le mode sélectionné
    const currentMode = (typeof metaCurrentMode !== 'undefined') ? metaCurrentMode : 'tirages';
    const totalTirages = window.TOTAL_TIRAGES || 967;
    let rowsToAnalyze = totalTirages;
    let isGlobal = true;

    if (currentMode === 'annees' && typeof metaYearsSize !== 'undefined' && metaYearsSize && metaYearsSize !== 'GLOBAL') {
        // Mode années : estimation ~150 tirages/an
        rowsToAnalyze = parseInt(metaYearsSize, 10) * 150;
        isGlobal = false;
    } else if (currentMode === 'tirages' && typeof metaWindowSize !== 'undefined' && metaWindowSize && metaWindowSize !== 'GLOBAL') {
        // Mode tirages : valeur exacte
        rowsToAnalyze = parseInt(metaWindowSize, 10);
        isGlobal = false;
    }

    // T=0 : déclencher Gemini immédiatement (travaille pendant le timer)
    triggerGeminiEarly();

    // Logs spécifiques META ANALYSE (75 grilles)
    const metaAnalyseLogs = getConsoleLogs(75, META_ANALYSE_TIMER_DURATION, {
        rowsToAnalyze: rowsToAnalyze,
        isGlobal: isGlobal
    });

    const result = await showSponsorPopup75({
        duration: META_ANALYSE_TIMER_DURATION,
        gridCount: 75,
        title: 'META ANALYSE - Traitement 75 grilles',
        isMetaAnalyse: true,
        logs: metaAnalyseLogs,
        onComplete: onMetaAnalyseComplete
    });

    // Si annulé par l'utilisateur, ne pas déclencher le callback
    if (result && result.cancelled === true) {
        console.log('[META ANALYSE] Annulé par l\'utilisateur');
        return result;
    }

    return result;
}

// ============================================
// EXPORTS (pour utilisation dans d'autres fichiers)
// ============================================

// Les fonctions sont disponibles globalement
window.showSponsorPopup75 = showSponsorPopup75;
window.showPopupBeforeGeneration = showPopupBeforeGeneration;
window.showPopupBeforeSimulation = showPopupBeforeSimulation;
window.calculateTimerDuration = calculateTimerDuration;

// Export META ANALYSE
window.showMetaAnalysePopup = showMetaAnalysePopup;
window.META_ANALYSE_TIMER_DURATION = META_ANALYSE_TIMER_DURATION;

// ============================================
// CSS BADGE SOURCE META ANALYSE (injection JS)
// ============================================
(function() {
    var style = document.createElement('style');
    style.textContent = [
        '.meta-source-badge {',
        '  font-size: 12px;',
        '  padding: 4px 8px;',
        '  border-radius: 6px;',
        '  font-weight: 600;',
        '  display: inline-block;',
        '}',
        '.meta-source-badge.gemini {',
        '  background: #0f5132;',
        '  color: #d1e7dd;',
        '}',
        '.meta-source-badge.local {',
        '  background: #664d03;',
        '  color: #fff3cd;',
        '}'
    ].join('\n');
    document.head.appendChild(style);
})();

console.log('[Sponsor Popup 75] Module META ANALYSE loaded successfully');