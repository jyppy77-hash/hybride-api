/**
 * SPONSOR POPUP EM - Logique et Animations EuroMillions
 * Phase de calcul sponsorisee avec timer algorithmique
 *
 * Copie adaptee de sponsor-popup.js (Loto FR)
 * - Console logs EuroMillions (etoiles, donnees europeennes)
 * - Matrix : 5 numeros (1-50) + 2 etoiles (1-12)
 * - Timer fixe 3s pour le simulateur
 *
 * @version 1.0-EM
 */

// ============================================
// ETOILES EM FLOTTANTES — Version fluide
// ============================================

var starIntervalId = null;
var MAX_STARS = 12;

function spawnFloatingStar(container) {
    var existing = container.querySelectorAll('.floating-star');
    if (existing.length >= MAX_STARS) return;

    var star = document.createElement('span');
    star.classList.add('floating-star');

    var rand = Math.random();
    if (rand < 0.35) {
        star.classList.add('star-small');
    } else if (rand < 0.75) {
        star.classList.add('star-medium');
    } else {
        star.classList.add('star-large');
    }

    star.textContent = '\u2605';

    var xPos = Math.random() * 80 + 10;
    star.style.setProperty('--star-x', xPos + '%');
    star.style.setProperty('--star-start-y', (Math.random() * 10 - 5) + '%');

    var consoleEl = container.querySelector('.console-container');
    if (consoleEl) {
        var modalRect = container.getBoundingClientRect();
        var consoleRect = consoleEl.getBoundingClientRect();
        var fallDistance = consoleRect.top - modalRect.top;
        star.style.setProperty('--star-fall-distance', fallDistance + 'px');
    } else {
        star.style.setProperty('--star-fall-distance', '50%');
    }

    var duration = 2.5 + Math.random() * 1.5;
    star.style.setProperty('--star-duration', duration + 's');

    container.appendChild(star);

    star.addEventListener('animationend', function() {
        if (star.parentNode) {
            star.parentNode.removeChild(star);
        }
    });
}

function startFloatingStars() {
    var modal = document.querySelector('.sponsor-popup-modal');
    if (!modal) return;

    setTimeout(function() {
        starIntervalId = setInterval(function() {
            spawnFloatingStar(modal);
        }, 1200);
    }, 2000);
}

function stopFloatingStars() {
    if (starIntervalId) {
        clearInterval(starIntervalId);
        starIntervalId = null;
    }
    document.querySelectorAll('.floating-star').forEach(function(star) { star.remove(); });
}

// ============================================
// CONFIGURATION DES SPONSORS
// ============================================

var SPONSORS_CONFIG_EM = [
    {
        id: 'emovisia',
        name: 'EmovisIA',
        url: 'https://www.emovisia.fr',
        icon: '\uD83C\uDFA8',
        description: 'Restauration photo artisanale',
        displayUrl: 'www.emovisia.fr',
        badge: 'Propuls\u00e9 par',
        badgeType: 'primary'
    },
    {
        id: 'annonceur',
        name: 'Votre marque ici',
        url: 'mailto:partenariats@lotoia.fr',
        icon: '\uD83D\uDCE3',
        description: 'Audience forte \u2022 trafic qualifi\u00e9',
        displayUrl: 'partenariats@lotoia.fr',
        badge: 'Avec le soutien de',
        badgeType: 'partner'
    }
];

// ============================================
// SEQUENCE DE LOGS CONSOLE EM
// ============================================

/**
 * Genere la sequence de logs pour la console EuroMillions
 * @param {number} gridCount - Nombre de grilles
 * @param {number} duration - Duree totale en secondes
 * @returns {Array} Tableau de logs avec timing
 */
function getConsoleLogsSimulateurEM(gridCount, duration) {
    var fixedPhaseSec = 2;
    var fixedSteps = 5;
    var totalSteps = 15;
    var variableSteps = totalSteps - fixedSteps;

    var variableDurationSec = Math.max(0, duration - fixedPhaseSec);
    var fixedStepSec = fixedPhaseSec / fixedSteps;
    var variableStepSec = variableSteps > 0 ? (variableDurationSec / variableSteps) : 0;

    var t = function(i) {
        if (i < fixedSteps) return i * fixedStepSec;
        return fixedPhaseSec + (i - fixedSteps) * variableStepSec;
    };

    var rowsCount = window.TOTAL_TIRAGES_EM || 729;
    var rowsFormatted = rowsCount.toLocaleString('fr-FR');

    return [
        { time: t(0),  text: "> Initialisation HYBRIDE_EM_V1...", type: "info" },
        { time: t(1),  text: "\u2713 Connexion moteur OK (142ms)", type: "success" },
        { time: t(2),  text: "> Chargement base de donn\u00e9es EuroMillions...", type: "info" },
        { time: t(3),  text: "\u2713 " + rowsFormatted + " tirages EuroMillions charg\u00e9s (387ms)", type: "success" },
        { time: t(4),  text: "> GET /api/euromillions/analyze?grids=" + gridCount + "&mode=balanced", type: "request" },
        { time: t(5),  text: "\uD83D\uDCCA Analyse fr\u00e9quences 5 num\u00e9ros + 2 \u00e9toiles... 18%", type: "progress" },
        { time: t(6),  text: "\uD83C\uDF0D Croisement donn\u00e9es europ\u00e9ennes... 34%", type: "progress" },
        { time: t(7),  text: "\u2B50 Optimisation \u00e9toiles... 51%", type: "progress" },
        { time: t(8),  text: "\u2696\uFE0F \u00c9quilibrage pair/impair... 67%", type: "progress" },
        { time: t(9),  text: "\uD83D\uDCCF Calcul dispersion multi-pays... 78%", type: "progress" },
        { time: t(10), text: "\u23F3 Application contraintes soft... 85%", type: "progress" },
        { time: t(11), text: "\u23F3 G\u00e9n\u00e9ration grilles optimis\u00e9es EM... 92%", type: "progress" },
        { time: t(12), text: "\u23F3 Validation scores finaux... 0%", type: "progress", bindToGlobalProgress: true },
        { time: t(13), text: "\u2713 " + gridCount + " grille" + (gridCount > 1 ? 's' : '') + " g\u00e9n\u00e9r\u00e9e" + (gridCount > 1 ? 's' : '') + " avec succ\u00e8s", type: "success", requires100: true },
        { time: t(14), text: "> Pr\u00e9paration affichage r\u00e9sultats...", type: "info", requires100: true },
        { time: t(14) + (variableStepSec * 0.5), text: "\u2713 Pr\u00eat \u00e0 afficher", type: "success", requires100: true }
    ];
}

// ============================================
// CALCUL DE LA DUREE DU TIMER
// ============================================

/**
 * Calcule la duree du timer selon le nombre de grilles
 * @param {number} gridCount - Nombre de grilles (1-5)
 * @returns {number} Duree en secondes
 */
function calculateTimerDurationSimulateurEM(gridCount) {
    var timings = { 1: 5, 2: 8, 3: 11, 4: 13, 5: 15 };
    return timings[gridCount] || 5;
}

// ============================================
// GENERATION DU HTML DU POPUP
// ============================================

/**
 * Genere le HTML du popup sponsor EuroMillions
 * @param {Object} config - Configuration
 * @returns {string} HTML du popup
 */
function generatePopupHTMLSimulateurEM(config) {
    var title = config.title;
    var duration = config.duration;

    var sponsorsHTML = SPONSORS_CONFIG_EM.map(function(sponsor) {
        return '<a href="' + sponsor.url + '" target="_blank" rel="noopener noreferrer"' +
           ' class="sponsor-card" data-sponsor="' + sponsor.id + '"' +
           ' onclick="trackSponsorClickSimulateurEM(\'' + sponsor.id + '\')">' +
            '<span class="sponsor-badge ' + sponsor.badgeType + '">' + sponsor.badge + '</span>' +
            '<div class="sponsor-logo">' +
                '<span class="sponsor-logo-icon">' + sponsor.icon + '</span>' +
                sponsor.name +
            '</div>' +
            '<div class="sponsor-description">' + sponsor.description + '</div>' +
            '<div class="sponsor-url">' +
                '<span>\u2192</span>' +
                '<span>' + sponsor.displayUrl + '</span>' +
            '</div>' +
        '</a>';
    }).join('');

    return '<div class="sponsor-popup-modal entering">' +
            '<h2 class="popup-title">' +
                '<span class="title-icon">\u2699\uFE0F</span>' +
                title +
            '</h2>' +
            '<div class="progress-bar-container">' +
                '<div class="progress-bar-fill" id="sponsor-progress"></div>' +
            '</div>' +
            '<div class="progress-percentage" id="progress-text">0%</div>' +
            '<div class="data-animation" id="data-animation"></div>' +
            '<div class="console-container">' +
                '<div class="console-header">' +
                    '<span class="console-title">\uD83D\uDDA5\uFE0F MOTEUR HYBRIDE EM</span>' +
                    '<span class="console-status" id="console-status">' +
                        '<span class="status-dot"></span>PROCESSING' +
                    '</span>' +
                '</div>' +
                '<div class="console-body" id="console-logs">' +
                    '<div class="console-line console-ready">' +
                        '<span class="console-prompt">$</span>' +
                        '<span class="console-text">Syst\u00e8me pr\u00eat</span>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div class="sponsors-header">Partenaires</div>' +
            '<div class="sponsors-container">' +
                sponsorsHTML +
            '</div>' +
            '<div class="timer-circle-container">' +
                '<div class="timer-circle">' +
                    '<div class="timer-circle-bg"></div>' +
                    '<div class="timer-circle-progress">' +
                        '<svg viewBox="0 0 100 100">' +
                            '<defs>' +
                                '<linearGradient id="timerGradientEM" x1="0%" y1="0%" x2="100%" y2="100%">' +
                                    '<stop offset="0%" stop-color="#FFD700"/>' +
                                    '<stop offset="50%" stop-color="#003399"/>' +
                                    '<stop offset="100%" stop-color="#1a4dbf"/>' +
                                '</linearGradient>' +
                            '</defs>' +
                            '<circle class="track" cx="50" cy="50" r="40"/>' +
                            '<circle class="fill" id="timer-circle-fill" cx="50" cy="50" r="40"/>' +
                        '</svg>' +
                    '</div>' +
                    '<span class="timer-value" id="timer-display">' + duration + '</span>' +
                '</div>' +
                '<span class="timer-label">secondes</span>' +
            '</div>' +
        '</div>';
}

// ============================================
// TRACKING (ANALYTICS)
// ============================================

/**
 * Track sponsor click for analytics
 * @param {string} sponsorId - ID du sponsor
 */
function trackSponsorClickSimulateurEM(sponsorId) {
    // Umami — sponsor click EM
    if (typeof umami !== 'undefined') umami.track('sponsor-click', { sponsor: sponsorId, module: 'euromillions' });
    if (window.LotoIAAnalytics && window.LotoIAAnalytics.business) {
        window.LotoIAAnalytics.business.sponsorClick({
            sponsor: sponsorId,
            sponsorId: sponsorId,
            placement: 'popup_console_simulateur_em'
        });
    }

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
        }).catch(function() {});
    }
    console.log('[Sponsor Simulateur EM] Click tracked: ' + sponsorId);
}

/**
 * Track impression for analytics
 * @param {Array} sponsorIds - IDs des sponsors affiches
 */
function trackImpressionSimulateurEM(sponsorIds) {
    if (window.LotoIAAnalytics && window.LotoIAAnalytics.business) {
        sponsorIds.forEach(function(sponsorId) {
            window.LotoIAAnalytics.business.sponsorImpression({
                sponsor: sponsorId,
                sponsorId: sponsorId,
                placement: 'popup_console_simulateur_em'
            });
        });
    }

    if (typeof fetch !== 'undefined' && window.LotoIAAnalytics?.utils?.hasConsent()) {
        fetch('/api/track-ad-impression', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ad_id: Array.isArray(sponsorIds) ? sponsorIds.join(',') : 'unknown',
                timestamp: Math.floor(Date.now() / 1000),
                session_id: sessionStorage.getItem('lotoia_session') || 'anonymous'
            })
        }).catch(function() {});
    }
    console.log('[Sponsor Simulateur EM] Impressions tracked: ' + sponsorIds.join(', '));
}

// ============================================
// ANIMATION MATRIX (CHIFFRES EUROMILLIONS)
// ============================================

/**
 * Genere une ligne de numeros EuroMillions aleatoires
 * 5 numeros (1-50) + separateur + 2 etoiles (1-12)
 * @returns {string}
 */
function generateMatrixLineSimulateurEM() {
    var segments = [];
    for (var i = 0; i < 5; i++) {
        var num = Math.floor(Math.random() * 50) + 1;
        segments.push(String(num).padStart(2, '0'));
    }
    segments.push('|');
    for (var j = 0; j < 2; j++) {
        var star = Math.floor(Math.random() * 12) + 1;
        segments.push('\u2605' + String(star).padStart(2, '0'));
    }
    return segments.join(' ');
}

// ============================================
// FONCTION PRINCIPALE DU POPUP
// ============================================

/**
 * Affiche le popup sponsor EM avec timer et animations
 * @param {Object} config - Configuration
 * @param {number} config.duration - Duree en secondes
 * @param {string} [config.title] - Titre du popup
 * @param {number} [config.gridCount] - Nombre de grilles (pour les logs)
 * @param {Function} [config.onComplete] - Callback a la fin
 * @returns {Promise} Promise resolue quand le popup se ferme
 */
function showSponsorPopupSimulateurEM(config) {
    return new Promise(function(resolve) {
        var duration = config.duration;
        var title = config.title || 'HYBRIDE EM - Analyse en cours...';
        var gridCount = config.gridCount || 5;
        var onComplete = config.onComplete;

        var overlay = document.createElement('div');
        overlay.className = 'sponsor-popup-overlay';
        overlay.innerHTML = generatePopupHTMLSimulateurEM({ title: title, duration: duration });

        var isCancelled = false;

        overlay.addEventListener('click', function(e) {
            e.stopPropagation();
        });

        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';
        document.body.classList.add('sponsor-popup-active');
        startFloatingStars();

        // Umami — sponsor popup shown EM
        if (typeof umami !== 'undefined') umami.track('sponsor-popup-shown', { module: 'euromillions' });

        // Bouton Annuler
        var modal = overlay.querySelector('.sponsor-popup-modal');
        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'sponsor-cancel-btn';
        cancelBtn.textContent = 'Annuler';

        var actions = document.createElement('div');
        actions.className = 'sponsor-popup-actions';
        actions.appendChild(cancelBtn);

        if (modal) {
            modal.appendChild(actions);
        } else {
            overlay.appendChild(actions);
        }

        cancelBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            isCancelled = true;
            closePopup();
        });

        // Track impressions
        trackImpressionSimulateurEM(SPONSORS_CONFIG_EM.map(function(s) { return s.id; }));

        // Elements d'animation
        var progressBar = document.getElementById('sponsor-progress');
        var progressText = document.getElementById('progress-text');
        var timerDisplay = document.getElementById('timer-display');
        var timerCircleFill = document.getElementById('timer-circle-fill');
        var dataAnimation = document.getElementById('data-animation');
        var consoleBody = document.getElementById('console-logs');
        var consoleStatus = document.getElementById('console-status');

        // Calculer la circonference du cercle
        var circumference = 2 * Math.PI * 40;

        // Variables d'animation
        var startTime = Date.now();
        var durationMs = duration * 1000;
        var animationFrameId;
        var dataInterval;
        var logTimeouts = [];
        var dynamicIntervals = [];
        var boundProgressLine = null;
        var lastLogDisplayed = false;

        function getGlobalPercent() {
            var elapsedMs = Date.now() - startTime;
            var raw = Math.round((elapsedMs / durationMs) * 100);
            return Math.max(0, Math.min(100, raw));
        }

        // Animation des chiffres Matrix EM
        dataInterval = setInterval(function() {
            dataAnimation.textContent = generateMatrixLineSimulateurEM();
        }, 80);

        // ============================================
        // ANIMATION CONSOLE - LOGS DYNAMIQUES
        // ============================================

        var logs = config.logs || getConsoleLogsSimulateurEM(gridCount, duration);

        function addConsoleLog(log, nextDelayMs) {
            var line = document.createElement('div');
            line.className = 'console-line console-' + log.type;

            var prompt = document.createElement('span');
            prompt.className = 'console-prompt';
            prompt.textContent = '$';

            var text = document.createElement('span');
            text.className = 'console-text';
            text.textContent = log.text;

            var isProgress = log.type === 'progress';

            if (isProgress) {
                var m = log.text.match(/(\d{1,3})\s*%\s*$/);
                var startPct = m ? Math.max(0, Math.min(100, parseInt(m[1], 10))) : 0;
                var baseText = log.text.replace(/\s*\d{1,3}\s*%\s*$/, '').trimEnd();
                text.textContent = baseText;

                line.setAttribute('data-pct', startPct + '%');

                var safeNextDelayMs = typeof nextDelayMs === 'number' ? nextDelayMs : 0;
                var animDurationMs = Math.max(120, Math.min(600, safeNextDelayMs - 50));
                var start = Date.now();

                var interval = setInterval(function() {
                    var elapsed = Date.now() - start;
                    var t = animDurationMs > 0 ? Math.min(elapsed / animDurationMs, 1) : 1;
                    var current = Math.max(startPct, Math.round(startPct + (100 - startPct) * t));

                    line.setAttribute('data-pct', current + '%');

                    if (t >= 1) {
                        line.setAttribute('data-pct', '100%');
                        clearInterval(interval);
                    }
                }, 33);

                dynamicIntervals.push(interval);
            }

            if (!isProgress && (
                log.dynamicPercent &&
                typeof log.dynamicPercent.from === 'number' &&
                typeof log.dynamicPercent.to === 'number'
            )) {
                var from = log.dynamicPercent.from;
                var to = log.dynamicPercent.to;
                var prefix = typeof log.dynamicPercent.prefix === 'string' ? log.dynamicPercent.prefix : '';
                var suffix = typeof log.dynamicPercent.suffix === 'string' ? log.dynamicPercent.suffix : '';

                var safeNext = typeof nextDelayMs === 'number' ? nextDelayMs : 0;
                var animDur = Math.max(150, Math.min(600, safeNext - 60));
                var startT = Date.now();

                var intv = setInterval(function() {
                    var el = Date.now() - startT;
                    var tt = animDur > 0 ? Math.min(el / animDur, 1) : 1;
                    var cur = Math.min(to, Math.max(from, Math.round(from + (to - from) * tt)));

                    text.textContent = prefix + cur + '%' + suffix;

                    if (tt >= 1) {
                        clearInterval(intv);
                    }
                }, 50);

                dynamicIntervals.push(intv);
            }

            line.appendChild(prompt);
            line.appendChild(text);
            consoleBody.appendChild(line);

            consoleBody.scrollTop = consoleBody.scrollHeight;
        }

        // Planifier l'affichage de chaque log
        logs.forEach(function(log, index) {
            var timeout = setTimeout(function() {
                var nextDelayMs = logs[index + 1]
                    ? (logs[index + 1].time - log.time) * 1000
                    : 0;

                var addNow = function() {
                    addConsoleLog(log, nextDelayMs);

                    if (index === logs.length - 1) {
                        lastLogDisplayed = true;

                        var markComplete = function() {
                            consoleStatus.innerHTML =
                                '<span class="status-dot status-complete"></span>COMPLETE';
                            consoleStatus.classList.add('complete');
                        };

                        if (getGlobalPercent() >= 100) {
                            markComplete();
                        } else {
                            var waitComplete = setInterval(function() {
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
                    var wait100 = setInterval(function() {
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
            var elapsed = Date.now() - startTime;
            var progress = Math.min(elapsed / durationMs, 1);
            var remaining = Math.max(0, duration - elapsed / 1000);
            var percent = getGlobalPercent();

            progressBar.style.width = percent + '%';
            progressText.textContent = percent + '%';

            if (boundProgressLine) {
                boundProgressLine.textContent = '\u23F3 Validation scores finaux... ' + percent + '%';
            }

            timerDisplay.textContent = percent >= 100 ? '0' : String(Math.ceil(remaining));

            var progressForCircle = percent / 100;
            var offset = circumference * (1 - progressForCircle);
            timerCircleFill.style.strokeDashoffset = offset;

            if (progress < 1 || !lastLogDisplayed) {
                animationFrameId = requestAnimationFrame(animate);
            } else {
                progressBar.style.width = '100%';
                progressText.textContent = '100%';
                if (boundProgressLine) {
                    boundProgressLine.textContent = '\u23F3 Validation scores finaux... 100%';
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
            logTimeouts.forEach(function(t) { clearTimeout(t); });
            dynamicIntervals.forEach(function(i) { clearInterval(i); });

            overlay.classList.add('closing');

            setTimeout(function() {
                stopFloatingStars();
                if (overlay.parentNode) {
                    document.body.removeChild(overlay);
                }
                document.body.style.overflow = '';
                document.body.classList.remove('sponsor-popup-active');

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
// FONCTION WRAPPER POUR GENERATION DE GRILLES EM
// ============================================

/**
 * Wrapper pour afficher le popup avant generation de grilles EM
 * @param {number} gridCount - Nombre de grilles
 * @param {Function} generateCallback - Fonction de generation a executer apres
 */
async function showPopupBeforeGenerationSimulateurEM(gridCount, generateCallback) {
    var duration = calculateTimerDurationSimulateurEM(gridCount);
    var plural = gridCount > 1 ? 's' : '';

    var result = await showSponsorPopupSimulateurEM({
        duration: duration,
        gridCount: gridCount,
        title: 'G\u00e9n\u00e9ration de ' + gridCount + ' grille' + plural + ' optimis\u00e9e' + plural + ' EM'
    });

    if (result && result.cancelled === true) return;

    if (generateCallback && typeof generateCallback === 'function') {
        generateCallback();
    }
}

// ============================================
// FONCTION WRAPPER POUR SIMULATEUR EM
// ============================================

/**
 * Wrapper pour afficher le popup avant simulation EM
 * Timer fixe a 3 secondes
 * @param {string} [title] - Titre personnalise
 * @param {Function} simulateCallback - Fonction de simulation a executer apres
 */
async function showPopupBeforeSimulationSimulateurEM(title, simulateCallback) {
    var result = await showSponsorPopupSimulateurEM({
        duration: 3,
        title: title || 'Analyse de votre grille EuroMillions en cours'
    });

    if (result && result.cancelled === true) return;

    if (simulateCallback && typeof simulateCallback === 'function') {
        simulateCallback();
    }
}

// ============================================
// EXPORTS (pour utilisation dans d'autres fichiers)
// ============================================

window.showSponsorPopupSimulateurEM = showSponsorPopupSimulateurEM;
window.showPopupBeforeGenerationSimulateurEM = showPopupBeforeGenerationSimulateurEM;
window.showPopupBeforeSimulationSimulateurEM = showPopupBeforeSimulationSimulateurEM;
window.calculateTimerDurationSimulateurEM = calculateTimerDurationSimulateurEM;

console.log('[Sponsor Popup Simulateur EM] Module loaded successfully');