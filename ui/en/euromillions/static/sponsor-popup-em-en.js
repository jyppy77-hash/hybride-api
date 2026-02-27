/**
 * SPONSOR POPUP EM - EuroMillions Logic and Animations
 * Sponsored computation phase with algorithmic timer
 *
 * Adapted copy of sponsor-popup.js (Loto FR)
 * - EuroMillions console logs (stars, European data)
 * - Matrix: 5 numbers (1-50) + 2 stars (1-12)
 * - Fixed 3s timer for the simulator
 *
 * @version 1.0-EM
 */

// ============================================
// FLOATING EM STARS — Smooth version
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
// SPONSORS CONFIGURATION
// ============================================

var SPONSORS_CONFIG_EM = [
    {
        id: 'emovisia',
        name: 'EmovisIA',
        url: 'https://www.emovisia.fr',
        icon: '\uD83C\uDFA8',
        description: 'Artisan photo restoration',
        displayUrl: 'www.emovisia.fr',
        badge: 'Powered by',
        badgeType: 'primary'
    },
    {
        id: 'annonceur',
        name: 'Your brand here',
        url: 'mailto:partenariats@lotoia.fr',
        icon: '\uD83D\uDCE3',
        description: 'High audience \u2022 qualified traffic',
        displayUrl: 'partenariats@lotoia.fr',
        badge: 'Supported by',
        badgeType: 'partner'
    }
];

// ============================================
// EM CONSOLE LOG SEQUENCE
// ============================================

/**
 * Generates the log sequence for the EuroMillions console
 * @param {number} gridCount - Number of grids
 * @param {number} duration - Total duration in seconds
 * @returns {Array} Array of logs with timing
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
    var rowsFormatted = rowsCount.toLocaleString('en-GB');

    return [
        { time: t(0),  text: "> Initialising HYBRIDE_EM_V1...", type: "info" },
        { time: t(1),  text: "\u2713 Engine connection OK (142ms)", type: "success" },
        { time: t(2),  text: "> Loading EuroMillions database...", type: "info" },
        { time: t(3),  text: "\u2713 " + rowsFormatted + " EuroMillions draws loaded (387ms)", type: "success" },
        { time: t(4),  text: "> GET /api/euromillions/analyze?grids=" + gridCount + "&mode=balanced", type: "request" },
        { time: t(5),  text: "\uD83D\uDCCA Analysing frequencies 5 numbers + 2 stars... 18%", type: "progress" },
        { time: t(6),  text: "\uD83C\uDF0D Cross-referencing European data... 34%", type: "progress" },
        { time: t(7),  text: "\u2B50 Optimising stars... 51%", type: "progress" },
        { time: t(8),  text: "\u2696\uFE0F Balancing odd/even... 67%", type: "progress" },
        { time: t(9),  text: "\uD83D\uDCCF Computing multi-country spread... 78%", type: "progress" },
        { time: t(10), text: "\u23F3 Applying soft constraints... 85%", type: "progress" },
        { time: t(11), text: "\u23F3 Generating optimised EM grids... 92%", type: "progress" },
        { time: t(12), text: "\u23F3 Validating final scores... 0%", type: "progress", bindToGlobalProgress: true },
        { time: t(13), text: "\u2713 " + gridCount + " grid" + (gridCount > 1 ? 's' : '') + " generated successfully", type: "success", requires100: true },
        { time: t(14), text: "> Preparing results display...", type: "info", requires100: true },
        { time: t(14) + (variableStepSec * 0.5), text: "\u2713 Ready to display", type: "success", requires100: true }
    ];
}

// ============================================
// TIMER DURATION CALCULATION
// ============================================

/**
 * Calculates the timer duration based on the number of grids
 * @param {number} gridCount - Number of grids (1-5)
 * @returns {number} Duration in seconds
 */
function calculateTimerDurationSimulateurEM(gridCount) {
    var timings = { 1: 5, 2: 8, 3: 11, 4: 13, 5: 15 };
    return timings[gridCount] || 5;
}

// ============================================
// POPUP HTML GENERATION
// ============================================

/**
 * Generates the EuroMillions sponsor popup HTML
 * @param {Object} config - Configuration
 * @returns {string} Popup HTML
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
                        '<span class="console-text">System ready</span>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div class="sponsors-header">Partners</div>' +
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
                '<span class="timer-label">seconds</span>' +
            '</div>' +
        '</div>';
}

// ============================================
// TRACKING (ANALYTICS)
// ============================================

/**
 * Track sponsor click for analytics
 * @param {string} sponsorId - Sponsor ID
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
 * @param {Array} sponsorIds - IDs of displayed sponsors
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
// MATRIX ANIMATION (EUROMILLIONS NUMBERS)
// ============================================

/**
 * Generates a line of random EuroMillions numbers
 * 5 numbers (1-50) + separator + 2 stars (1-12)
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
// MAIN POPUP FUNCTION
// ============================================

/**
 * Displays the EM sponsor popup with timer and animations
 * @param {Object} config - Configuration
 * @param {number} config.duration - Duration in seconds
 * @param {string} [config.title] - Popup title
 * @param {number} [config.gridCount] - Number of grids (for logs)
 * @param {Function} [config.onComplete] - Callback on completion
 * @returns {Promise} Promise resolved when the popup closes
 */
function showSponsorPopupSimulateurEM(config) {
    return new Promise(function(resolve) {
        var duration = config.duration;
        var title = config.title || 'HYBRIDE EM - Analysis in progress...';
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

        // Cancel button
        var modal = overlay.querySelector('.sponsor-popup-modal');
        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'sponsor-cancel-btn';
        cancelBtn.textContent = 'Cancel';

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

        // Animation elements
        var progressBar = document.getElementById('sponsor-progress');
        var progressText = document.getElementById('progress-text');
        var timerDisplay = document.getElementById('timer-display');
        var timerCircleFill = document.getElementById('timer-circle-fill');
        var dataAnimation = document.getElementById('data-animation');
        var consoleBody = document.getElementById('console-logs');
        var consoleStatus = document.getElementById('console-status');

        // Calculate circle circumference
        var circumference = 2 * Math.PI * 40;

        // Animation variables
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

        // Matrix EM number animation
        dataInterval = setInterval(function() {
            dataAnimation.textContent = generateMatrixLineSimulateurEM();
        }, 80);

        // ============================================
        // CONSOLE ANIMATION - DYNAMIC LOGS
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

        // Schedule display of each log
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

        // Main animation function
        function animate() {
            var elapsed = Date.now() - startTime;
            var progress = Math.min(elapsed / durationMs, 1);
            var remaining = Math.max(0, duration - elapsed / 1000);
            var percent = getGlobalPercent();

            progressBar.style.width = percent + '%';
            progressText.textContent = percent + '%';

            if (boundProgressLine) {
                boundProgressLine.textContent = '\u23F3 Validating final scores... ' + percent + '%';
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
                    boundProgressLine.textContent = '\u23F3 Validating final scores... 100%';
                }
                timerCircleFill.style.strokeDashoffset = 0;
                timerDisplay.textContent = '0';

                closePopup();
            }
        }

        // Close the popup
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

        // Start animation
        animationFrameId = requestAnimationFrame(animate);
    });
}

// ============================================
// WRAPPER FUNCTION FOR EM GRID GENERATION
// ============================================

/**
 * Wrapper to display the popup before EM grid generation
 * @param {number} gridCount - Number of grids
 * @param {Function} generateCallback - Generation function to execute afterwards
 */
async function showPopupBeforeGenerationSimulateurEM(gridCount, generateCallback) {
    var duration = calculateTimerDurationSimulateurEM(gridCount);
    var plural = gridCount > 1 ? 's' : '';

    var result = await showSponsorPopupSimulateurEM({
        duration: duration,
        gridCount: gridCount,
        title: 'Generating ' + gridCount + ' optimised EM grid' + plural
    });

    if (result && result.cancelled === true) return;

    if (generateCallback && typeof generateCallback === 'function') {
        generateCallback();
    }
}

// ============================================
// WRAPPER FUNCTION FOR EM SIMULATOR
// ============================================

/**
 * Wrapper to display the popup before EM simulation
 * Fixed timer at 3 seconds
 * @param {string} [title] - Custom title
 * @param {Function} simulateCallback - Simulation function to execute afterwards
 */
async function showPopupBeforeSimulationSimulateurEM(title, simulateCallback) {
    var result = await showSponsorPopupSimulateurEM({
        duration: 3,
        title: title || 'Analysing your EuroMillions grid'
    });

    if (result && result.cancelled === true) return;

    if (simulateCallback && typeof simulateCallback === 'function') {
        simulateCallback();
    }
}

// ============================================
// EXPORTS (for use in other files)
// ============================================

window.showSponsorPopupSimulateurEM = showSponsorPopupSimulateurEM;
window.showPopupBeforeGenerationSimulateurEM = showPopupBeforeGenerationSimulateurEM;
window.showPopupBeforeSimulationSimulateurEM = showPopupBeforeSimulationSimulateurEM;
window.calculateTimerDurationSimulateurEM = calculateTimerDurationSimulateurEM;

console.log('[Sponsor Popup Simulateur EM] Module loaded successfully');
