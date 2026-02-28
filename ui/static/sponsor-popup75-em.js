/**
 * SPONSOR POPUP 75 - META ANALYSE EuroMillions
 * Phase de calcul sponsorisee avec timer algorithmique
 * Tunnel premium vers analyse 75 grilles EM
 *
 * Equivalent EM de sponsor-popup75.js (ZERO modification au fichier Loto)
 *
 * @version 2.0-EM
 */

var LI = window.LotoIA_i18n || {};

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
// CONFIGURATION META ANALYSE EM
// ============================================

const META_ANALYSE_TIMER_DURATION_EM = 30;

// ============================================
// CONFIGURATION DES SPONSORS (VIDEO UNIQUEMENT)
// ============================================

const SPONSOR_VIDEO_75_EM = {
    id: 'lotoia_video',
    url: 'mailto:partenariats@lotoia.fr',
    videoSrc: '/static/Sponsors_media/Sponsor75lotoia.mp4'
};

// ============================================
// SEQUENCE DE LOGS CONSOLE EM
// ============================================

function getConsoleLogsEM(gridCount, duration, options) {
    options = options || {};
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

    var rowsCount = options.rowsToAnalyze || window.TOTAL_TIRAGES_EM || 729;
    var rowsFormatted = rowsCount.toLocaleString(LI.locale);
    var tiragesText = options.isGlobal
        ? '\u2713 ' + rowsFormatted + LI.log75_draws_full
        : '\u2713 ' + rowsFormatted + LI.log75_draws;

    return [
        { time: t(0), text: LI.log75_init, type: "info" },
        { time: t(1), text: LI.log75_connection, type: "success" },
        { time: t(2), text: LI.log75_loading_db, type: "info" },
        { time: t(3), text: tiragesText, type: "success" },
        { time: t(4), text: "> GET /api/euromillions/analyze?grids=" + gridCount + "&mode=balanced", type: "request" },
        { time: t(5), text: LI.log75_freq_balls + "18%", type: "progress" },
        { time: t(6), text: LI.log75_freq_stars + "34%", type: "progress" },
        { time: t(7), text: LI.log75_hot + "51%", type: "progress" },
        { time: t(8), text: LI.log75_balance + "67%", type: "progress" },
        { time: t(9), text: LI.log75_geo + "78%", type: "progress" },
        { time: t(10), text: LI.log75_constraints + "85%", type: "progress" },
        { time: t(11), text: LI.log75_gen + "92%", type: "progress" },
        { time: t(12), text: LI.log75_validating + "0%", type: "progress", bindToGlobalProgress: true },
        { time: t(13), text: LI.log75_success.replace('{n}', gridCount).replace(/\{s\}/g, gridCount > 1 ? 's' : ''), type: "success", requires100: true },
        { time: t(14), text: LI.log75_preparing, type: "info", requires100: true },
        { time: t(14) + (variableStepSec * 0.5), text: LI.log75_ready, type: "success", requires100: true }
    ];
}

// ============================================
// CALCUL DE LA DUREE DU TIMER
// ============================================

function calculateTimerDurationEM(gridCount) {
    var timings = { 1: 5, 2: 8, 3: 11, 4: 13, 5: 15 };
    return timings[gridCount] || 5;
}

// ============================================
// GENERATION DU HTML DU POPUP
// ============================================

function generatePopupHTML75EM(config) {
    var title = config.title;
    var duration = config.duration;
    var isMetaAnalyse = config.isMetaAnalyse || false;

    var metaAnalyseBadge = isMetaAnalyse
        ? '<div class="meta-analyse-badge">' + LI.meta_window_badge + '</div>'
        : '';

    var sponsorVideoHTML =
        '<div class="sponsor-video-wrapper">' +
            '<a href="' + SPONSOR_VIDEO_75_EM.url + '" class="sponsor-video-card" onclick="trackSponsorClickEM(\'' + SPONSOR_VIDEO_75_EM.id + '\')">' +
                '<video' +
                    ' class="sponsor-video"' +
                    ' autoplay' +
                    ' loop' +
                    ' muted' +
                    ' playsinline' +
                    ' preload="auto"' +
                    ' src="' + SPONSOR_VIDEO_75_EM.videoSrc + '"' +
                '></video>' +
            '</a>' +
            '<p class="sponsor-video-cta">' + LI.video_cta + '</p>' +
        '</div>';

    return '<div class="sponsor-popup-modal entering' + (isMetaAnalyse ? ' meta-analyse-modal meta-popup-em' : '') + '">' +
            metaAnalyseBadge +
            '<h2 class="popup-title">' +
                '<span class="title-icon">\u2699\ufe0f</span>' +
                title +
            '</h2>' +
            '<div class="progress-bar-container">' +
                '<div class="progress-bar-fill" id="sponsor-progress"></div>' +
            '</div>' +
            '<div class="progress-percentage" id="progress-text">0%</div>' +
            '<div class="data-animation" id="data-animation"></div>' +
            '<div class="console-container">' +
                '<div class="console-header">' +
                    '<span class="console-title">\ud83d\udda5\ufe0f ' + LI.console_title + '</span>' +
                    '<span class="console-status" id="console-status">' +
                        '<span class="status-dot"></span>PROCESSING' +
                    '</span>' +
                '</div>' +
                '<div class="console-body" id="console-logs">' +
                    '<div class="console-line console-ready">' +
                        '<span class="console-prompt">$</span>' +
                        '<span class="console-text">' + LI.system_ready + '</span>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div class="sponsors-header">' + LI.sponsor_header_single + '</div>' +
            '<div class="sponsors-container sponsors-container-single">' +
                sponsorVideoHTML +
            '</div>' +
            '<div class="timer-circle-container">' +
                '<div class="timer-circle">' +
                    '<div class="timer-circle-bg"></div>' +
                    '<div class="timer-circle-progress">' +
                        '<svg viewBox="0 0 100 100">' +
                            '<defs>' +
                                '<linearGradient id="timerGradientEM" x1="0%" y1="0%" x2="100%" y2="100%">' +
                                    '<stop offset="0%" stop-color="#f59e0b"/>' +
                                    '<stop offset="50%" stop-color="#3b82f6"/>' +
                                    '<stop offset="100%" stop-color="#8b5cf6"/>' +
                                '</linearGradient>' +
                            '</defs>' +
                            '<circle class="track" cx="50" cy="50" r="40"/>' +
                            '<circle class="fill" id="timer-circle-fill" cx="50" cy="50" r="40"/>' +
                        '</svg>' +
                    '</div>' +
                    '<span class="timer-value" id="timer-display">' + duration + '</span>' +
                '</div>' +
                '<span class="timer-label">' + LI.timer_label + '</span>' +
            '</div>' +
        '</div>';
}

// ============================================
// TRACKING (ANALYTICS)
// ============================================

function trackSponsorClickEM(sponsorId) {
    // Umami — sponsor click EM
    if (typeof umami !== 'undefined') umami.track('sponsor-click', { sponsor: sponsorId, module: 'euromillions' });
    if (window.LotoIAAnalytics && window.LotoIAAnalytics.business) {
        window.LotoIAAnalytics.business.sponsorClick({
            sponsor: sponsorId,
            sponsorId: sponsorId,
            placement: 'popup_console_em'
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
    console.log('[Sponsor EM] Click tracked: ' + sponsorId);
}

function trackImpressionEM(sponsorIds) {
    if (window.LotoIAAnalytics && window.LotoIAAnalytics.business) {
        sponsorIds.forEach(function(sponsorId) {
            window.LotoIAAnalytics.business.sponsorImpression({
                sponsor: sponsorId,
                sponsorId: sponsorId,
                placement: 'popup_console_em'
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
    console.log('[Sponsor EM] Impressions tracked: ' + sponsorIds.join(', '));
}

// ============================================
// ANIMATION MATRIX (CHIFFRES EUROMILLIONS)
// ============================================

function generateMatrixLineEM() {
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

function showSponsorPopup75EM(config) {
    return new Promise(function(resolve) {
        var duration = config.duration;
        var title = config.title || LI.popup75_default;
        var gridCount = config.gridCount || 5;
        var onComplete = config.onComplete;
        var isMetaAnalyse = config.isMetaAnalyse || false;

        var overlay = document.createElement('div');
        overlay.className = 'sponsor-popup-overlay';
        overlay.innerHTML = generatePopupHTML75EM({ title: title, duration: duration, isMetaAnalyse: isMetaAnalyse });

        var isCancelled = false;

        overlay.addEventListener('click', function(e) { e.stopPropagation(); });

        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';
        document.body.classList.add('sponsor-popup-active');
        startFloatingStars();

        // Umami — sponsor popup shown EM
        if (typeof umami !== 'undefined') umami.track('sponsor-popup-shown', { module: 'euromillions' });

        // Umami — sponsor video played (autoplay) EM
        var sponsorVideo = overlay.querySelector('.sponsor-video');
        if (sponsorVideo) {
            sponsorVideo.addEventListener('play', function() {
                if (typeof umami !== 'undefined') umami.track('sponsor-video-played', { sponsor: SPONSOR_VIDEO_75_EM.id, module: 'euromillions' });
            }, { once: true });
        }

        // Bouton Annuler — injecte dans le timer-circle-container (meme ligne)
        var modal = overlay.querySelector('.sponsor-popup-modal');
        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'sponsor-cancel-btn';
        cancelBtn.textContent = LI.cancel_btn;

        var timerContainer = modal ? modal.querySelector('.timer-circle-container') : null;
        if (timerContainer) {
            timerContainer.appendChild(cancelBtn);
        } else if (modal) {
            modal.appendChild(cancelBtn);
        } else {
            overlay.appendChild(cancelBtn);
        }

        cancelBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            isCancelled = true;
            closePopup();
        });

        trackImpressionEM([SPONSOR_VIDEO_75_EM.id]);

        var progressBar = document.getElementById('sponsor-progress');
        var progressText = document.getElementById('progress-text');
        var timerDisplay = document.getElementById('timer-display');
        var timerCircleFill = document.getElementById('timer-circle-fill');
        var dataAnimation = document.getElementById('data-animation');
        var consoleBody = document.getElementById('console-logs');
        var consoleStatus = document.getElementById('console-status');

        var circumference = 2 * Math.PI * 40;
        var startTime = Date.now();
        var durationMs = duration * 1000;
        var animationFrameId;
        var dataInterval;
        var logTimeouts = [];
        var dynamicIntervals = [];
        var boundProgressLine = null;
        var lastLogDisplayed = false;

        var finalLogsTriggered = false;
        var finalMetaLogs = [
            { delay: 0,    text: LI.meta_log_analysing,    type: 'info' },
            { delay: 350,  text: LI.meta_log_charts,       type: 'info' },
            { delay: 700,  text: LI.meta_log_pdf,          type: 'info' },
            { delay: 1050, text: LI.meta_log_validation,   type: 'info' },
            { delay: 1400, text: LI.meta_log_ready,        type: 'success' }
        ];

        function triggerFinalMetaLogs() {
            if (finalLogsTriggered || !isMetaAnalyse) return;
            finalLogsTriggered = true;
            finalMetaLogs.forEach(function(log) {
                var timeout = setTimeout(function() {
                    addConsoleLog(log, 300);
                }, log.delay);
                logTimeouts.push(timeout);
            });
        }

        function getGlobalPercent() {
            var elapsedMs = Date.now() - startTime;
            var raw = Math.round((elapsedMs / durationMs) * 100);
            return Math.max(0, Math.min(100, raw));
        }

        dataInterval = setInterval(function() {
            dataAnimation.textContent = generateMatrixLineEM();
        }, 80);

        var logs = config.logs || getConsoleLogsEM(gridCount, duration);

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
                var animDurationMs = Math.max(100, safeNextDelayMs - 250);
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
                }, 25);
                dynamicIntervals.push(interval);
            }

            if (!isProgress && log.dynamicPercent &&
                typeof log.dynamicPercent.from === 'number' &&
                typeof log.dynamicPercent.to === 'number') {
                var from = log.dynamicPercent.from;
                var to = log.dynamicPercent.to;
                var prefix = typeof log.dynamicPercent.prefix === 'string' ? log.dynamicPercent.prefix : '';
                var suffix = typeof log.dynamicPercent.suffix === 'string' ? log.dynamicPercent.suffix : '';

                var safeNext = typeof nextDelayMs === 'number' ? nextDelayMs : 0;
                var animDur = Math.max(100, safeNext - 200);
                var startT = Date.now();

                var intv = setInterval(function() {
                    var el = Date.now() - startT;
                    var tt = animDur > 0 ? Math.min(el / animDur, 1) : 1;
                    var cur = Math.min(to, Math.max(from, Math.round(from + (to - from) * tt)));
                    text.textContent = prefix + cur + '%' + suffix;
                    if (tt >= 1) clearInterval(intv);
                }, 25);
                dynamicIntervals.push(intv);
            }

            line.appendChild(prompt);
            line.appendChild(text);
            consoleBody.appendChild(line);
            consoleBody.scrollTop = consoleBody.scrollHeight;
        }

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
                            consoleStatus.innerHTML = '<span class="status-dot status-complete"></span>COMPLETE';
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

        function animate() {
            var elapsed = Date.now() - startTime;
            var progress = Math.min(elapsed / durationMs, 1);
            var remaining = Math.max(0, duration - elapsed / 1000);
            var percent = getGlobalPercent();

            if (isMetaAnalyse && remaining <= 2 && !finalLogsTriggered) {
                triggerFinalMetaLogs();
            }

            progressBar.style.width = percent + '%';
            progressText.textContent = percent + '%';

            if (boundProgressLine) {
                boundProgressLine.textContent = LI.log75_validating + percent + '%';
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
                    boundProgressLine.textContent = LI.log75_validating + '100%';
                }
                timerCircleFill.style.strokeDashoffset = 0;
                timerDisplay.textContent = '0';
                closePopup();
            }
        }

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

        animationFrameId = requestAnimationFrame(animate);
    });
}

// ============================================
// WRAPPERS GENERATION / SIMULATION EM
// ============================================

async function showPopupBeforeGenerationEM(gridCount, generateCallback) {
    var duration = calculateTimerDurationEM(gridCount);
    var plural = gridCount > 1 ? 's' : '';

    var result = await showSponsorPopup75EM({
        duration: duration,
        gridCount: gridCount,
        title: LI.wrapper_gen_title.replace('{n}', gridCount).replace(/\{s\}/g, plural)
    });

    if (result && result.cancelled === true) return;
    if (generateCallback && typeof generateCallback === 'function') {
        generateCallback();
    }
}

async function showPopupBeforeSimulationEM(title, simulateCallback) {
    var result = await showSponsorPopup75EM({
        duration: 3,
        title: title || LI.wrapper_sim_title
    });

    if (result && result.cancelled === true) return;
    if (simulateCallback && typeof simulateCallback === 'function') {
        simulateCallback();
    }
}

// ============================================
// META ANALYSE EM - POINT D'ENTREE PRINCIPAL
// ============================================

function generateGraphBarsHTMLEM(graph, titlePrefix) {
    if (!graph || !graph.labels || !graph.values) {
        return '<p style="color:#6b7280;">' + LI.meta_chart_na + '</p>';
    }

    var maxValue = Math.max.apply(null, graph.values);
    var bars = graph.labels.map(function(label, i) {
        var value = graph.values[i] || 0;
        var heightPercent = maxValue > 0 ? (value / maxValue) * 100 : 0;
        return '<div class="meta-result-bar" style="height: ' + heightPercent + '%;">' +
                '<span class="meta-result-bar-value">' + value + '</span>' +
                '<span class="meta-result-bar-label">' + (titlePrefix || '') + label + '</span>' +
            '</div>';
    }).join('');

    return bars;
}

// ============================================
// PDF LABOR ILLUSION EM — micro-animation avant download
// ============================================

function showPdfLaborIllusionEM(modal) {
    var steps = [
        { text: LI.meta_anim_step1, at: 0 },
        { text: LI.meta_anim_step2, at: 1500 },
        { text: LI.meta_anim_step3, at: 3000 },
        { text: LI.meta_anim_step4, at: 5000 }
    ];

    var laborOverlay = document.createElement('div');
    laborOverlay.className = 'meta-pdf-labor';
    laborOverlay.innerHTML = '<div class="meta-pdf-spinner"></div><div class="meta-pdf-steps"></div>';

    var container = laborOverlay.querySelector('.meta-pdf-steps');
    steps.forEach(function(s) {
        var el = document.createElement('div');
        el.className = 'meta-pdf-step';
        el.textContent = s.text;
        container.appendChild(el);
    });

    modal.style.overflow = 'hidden';
    modal.appendChild(laborOverlay);

    var els = laborOverlay.querySelectorAll('.meta-pdf-step');
    var timers = [];

    steps.forEach(function(s, i) {
        timers.push(setTimeout(function() {
            if (i > 0) { els[i-1].classList.remove('active'); els[i-1].classList.add('done'); }
            els[i].classList.add('active');
        }, s.at));
    });

    return {
        promise: new Promise(function(resolve) { setTimeout(resolve, 5200); }),
        finish: function() {
            timers.forEach(clearTimeout);
            for (var j = 0; j < els.length; j++) {
                els[j].classList.remove('active');
                els[j].classList.add('done');
            }
            setTimeout(function() {
                laborOverlay.style.opacity = '0';
                laborOverlay.style.transition = 'opacity 0.3s ease';
                setTimeout(function() {
                    if (laborOverlay.parentNode) laborOverlay.parentNode.removeChild(laborOverlay);
                    modal.style.overflow = '';
                }, 300);
            }, 400);
        }
    };
}

function openMetaResultPopupEM(data) {
    console.log('[META ANALYSE EM] Ouverture pop-up r\u00e9sultat', data);

    var durationMs = META_ANALYSE_START_TIME_EM ? (Date.now() - META_ANALYSE_START_TIME_EM) : 0;
    if (window.LotoIAAnalytics?.productEngine?.track) {
        window.LotoIAAnalytics.productEngine.track('meta_analysis_complete_em', {
            version: 75,
            source: data.source || 'unknown',
            duration_ms: durationMs
        });
    }

    var graphBarsBoules = generateGraphBarsHTMLEM(data.graph_boules, 'N\u00b0');
    var graphBarsEtoiles = generateGraphBarsHTMLEM(data.graph_etoiles, '\u2605');
    var analysisText = finalAnalysisTextEM;
    var analysisSource = window._metaAnalysisSourceEM || 'unknown';

    var sourceLabel = analysisSource === 'gemini_enriched'
        ? '<span class="meta-source-badge gemini">' + LI.meta_src_gemini + '</span>'
        : '<span class="meta-source-badge local">' + LI.meta_src_local + '</span>';

    var overlay = document.createElement('div');
    overlay.className = 'meta-result-overlay';
    overlay.innerHTML =
        '<div class="meta-result-modal">' +
            '<div class="meta-result-header">' +
                '<h2 class="meta-result-title">' +
                    '<span class="meta-result-title-icon">\ud83d\udcca</span>' +
                    LI.meta_result_title +
                '</h2>' +
                '<p class="meta-result-subtitle">' + LI.meta_result_subtitle + '</p>' +
            '</div>' +

            '<div class="meta-result-graph">' +
                '<div class="meta-result-graph-title">' + LI.meta_graph_balls + '</div>' +
                '<div class="meta-result-bars">' +
                    graphBarsBoules +
                '</div>' +
            '</div>' +

            '<div class="meta-result-graph" style="margin-top: 16px;">' +
                '<div class="meta-result-graph-title">' + LI.meta_graph_stars + '</div>' +
                '<div class="meta-result-bars">' +
                    graphBarsEtoiles +
                '</div>' +
            '</div>' +

            '<div class="meta-result-analysis">' +
                '<div class="meta-result-analysis-title">' +
                    sourceLabel +
                '</div>' +
                '<p class="meta-result-analysis-text">' + analysisText + '</p>' +
            '</div>' +

            '<div class="meta-result-actions">' +
                '<button class="meta-result-btn meta-result-btn-close" id="meta-result-close-em">' +
                    LI.meta_close +
                '</button>' +
                '<button class="meta-result-btn meta-result-btn-pdf" id="meta-result-pdf-em">' +
                    '<span>\ud83d\udcc4</span>' +
                    LI.meta_download +
                '</button>' +
            '</div>' +
        '</div>';

    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';

    var closeBtn = overlay.querySelector('#meta-result-close-em');
    var pdfBtn = overlay.querySelector('#meta-result-pdf-em');

    function closePopup() {
        overlay.classList.add('closing');
        setTimeout(function() {
            if (overlay.parentNode) document.body.removeChild(overlay);
            document.body.style.overflow = '';
        }, 250);
    }

    closeBtn.addEventListener('click', closePopup);
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closePopup();
    });

    if (pdfBtn) {
        pdfBtn.addEventListener('click', function() {
            if (typeof umami !== 'undefined') umami.track('meta75-pdf-download', { module: 'euromillions' });
            if (window.LotoIAAnalytics?.productEngine?.track) {
                window.LotoIAAnalytics.productEngine.track('meta_pdf_export_em', { version: 75 });
            }

            if (!finalAnalysisTextEM) {
                console.warn('[PDF EM] finalAnalysisTextEM est null');
                alert(LI.meta_pending);
                return;
            }

            pdfBtn.disabled = true;
            var modal = overlay.querySelector('.meta-result-modal');
            var labor = showPdfLaborIllusionEM(modal);

            var fetchPromise = fetch('/api/euromillions/meta-pdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    analysis: finalAnalysisTextEM,
                    window: LI.meta_75_grids,
                    engine: 'HYBRIDE',
                    graph_data_boules: metaResultDataEM && metaResultDataEM.graph_boules ? metaResultDataEM.graph_boules : null,
                    graph_data_etoiles: metaResultDataEM && metaResultDataEM.graph_etoiles ? metaResultDataEM.graph_etoiles : null,
                    sponsor: LI.meta_sponsor_space,
                    lang: window.LotoIA_lang
                })
            })
            .then(function(res) { return res.blob(); });

            Promise.all([labor.promise, fetchPromise])
                .then(function(results) {
                    labor.finish();
                    setTimeout(function() {
                        var url = URL.createObjectURL(results[1]);
                        window.open(url, '_blank');
                        pdfBtn.disabled = false;
                    }, 700);
                })
                .catch(function(err) {
                    console.error('[PDF EM] Erreur generation:', err);
                    labor.finish();
                    pdfBtn.disabled = false;
                });
        });
    }
}

function openMetaResultPopupFallbackEM() {
    console.warn('[META ANALYSE EM] Fallback activ\u00e9');

    var overlay = document.createElement('div');
    overlay.className = 'meta-result-overlay';
    overlay.innerHTML =
        '<div class="meta-result-modal">' +
            '<div class="meta-result-fallback">' +
                '<div class="meta-result-fallback-icon">\u26a0\ufe0f</div>' +
                '<p class="meta-result-fallback-text">' +
                    LI.meta_fallback_text + '<br>' +
                    LI.meta_fallback_retry +
                '</p>' +
                '<button class="meta-result-btn meta-result-btn-close" id="meta-result-close-fallback-em">' +
                    LI.meta_close +
                '</button>' +
            '</div>' +
        '</div>';

    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';

    var closeBtn = overlay.querySelector('#meta-result-close-fallback-em');

    function closePopup() {
        overlay.classList.add('closing');
        setTimeout(function() {
            if (overlay.parentNode) document.body.removeChild(overlay);
            document.body.style.overflow = '';
        }, 250);
    }

    closeBtn.addEventListener('click', closePopup);
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closePopup();
    });
}

// ==============================================
// SOURCE DE VERITE UNIQUE — Analyse Gemini EM
// ==============================================

var finalAnalysisTextEM = null;
var metaResultDataEM = null;
var metaAnalysisPromiseEM = null;
window._metaAnalysisSourceEM = null;

function buildMetaLocalUrlEM() {
    var currentMode = (typeof metaCurrentModeEM !== 'undefined') ? metaCurrentModeEM : 'tirages';
    var apiUrl = '/api/euromillions/meta-analyse-local';

    if (currentMode === 'annees' && typeof metaYearsSizeEM !== 'undefined' && metaYearsSizeEM) {
        apiUrl += '?years=' + encodeURIComponent(metaYearsSizeEM);
    } else {
        var windowParam = (typeof metaWindowSizeEM !== 'undefined' && metaWindowSizeEM) ? metaWindowSizeEM : 'GLOBAL';
        apiUrl += '?window=' + encodeURIComponent(windowParam);
    }
    return apiUrl;
}

function triggerGeminiEarlyEM() {
    var t0 = Date.now();
    console.log('[GEM EM] START T=0');

    finalAnalysisTextEM = null;
    metaResultDataEM = null;
    window._metaAnalysisSourceEM = null;

    var apiUrl = buildMetaLocalUrlEM();

    var chainPromise = fetch(apiUrl)
        .then(function(response) {
            if (!response.ok) throw new Error('Local HTTP ' + response.status);
            return response.json();
        })
        .then(function(data) {
            if (!data.success) throw new Error('API local: success=false');

            var localText = data.analysis;
            console.log('[GEM EM] Local OK (' + (localText ? localText.length : 0) + ' chars) T+' + (Date.now() - t0) + 'ms');

            return fetch('/api/euromillions/meta-analyse-texte', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    analysis_local: data.analysis,
                    stats: { boules: data.graph_boules, etoiles: data.graph_etoiles },
                    window: (data.meta && data.meta.window_used) ? data.meta.window_used : 'GLOBAL',
                    lang: window.LotoIA_lang
                })
            })
            .then(function(r) {
                if (!r.ok) throw new Error('Gemini HTTP ' + r.status);
                return r.json();
            })
            .then(function(gem) {
                console.log('[GEM EM] Response T+' + (Date.now() - t0) + 'ms, source:', gem ? gem.source : 'N/A');
                var enriched = gem && gem.analysis_enriched;
                if (!enriched || typeof enriched !== 'string' || enriched.trim().length === 0) {
                    throw new Error('analysis_enriched manquant');
                }
                if (gem.source && gem.source !== 'gemini_enriched') {
                    throw new Error('Backend fallback local \u2014 source: ' + gem.source);
                }
                console.log('[GEM EM] ENRICHED OK (' + enriched.length + ' chars) T+' + (Date.now() - t0) + 'ms');
                finalAnalysisTextEM = enriched;
                window._metaAnalysisSourceEM = 'gemini_enriched';
                data.analysis = enriched;
                data.source = 'gemini_enriched';
                metaResultDataEM = data;
            })
            .catch(function(gemErr) {
                console.warn('[GEM EM] Gemini \u00e9chou\u00e9 T+' + (Date.now() - t0) + 'ms:', gemErr);
                window._metaAnalysisSourceEM = 'gemini_failed';
                data._localText = localText;
                data.source = 'gemini_failed';
                metaResultDataEM = data;
            });
        });

    var globalTimeout = new Promise(function(_, reject) {
        setTimeout(function() { reject('GLOBAL_TIMEOUT_28S'); }, 28000);
    });

    metaAnalysisPromiseEM = Promise.race([chainPromise, globalTimeout])
        .catch(function(err) {
            console.error('[GEM EM] TIMEOUT ou erreur fatale T+' + (Date.now() - t0) + 'ms:', err);
            if (err === 'GLOBAL_TIMEOUT_28S' && !finalAnalysisTextEM && metaResultDataEM && metaResultDataEM._localText) {
                console.warn('[GEM EM] Timeout 28s \u2014 fallback explicite vers analyse locale');
                finalAnalysisTextEM = metaResultDataEM._localText;
                window._metaAnalysisSourceEM = 'timeout_fallback_local';
                metaResultDataEM.source = 'timeout_fallback_local';
            }
        });

    return metaAnalysisPromiseEM;
}

function onMetaAnalyseCompleteEM() {
    console.log('[META ANALYSE EM] Timer termin\u00e9 \u2014 attente Promise Gemini...');

    if (!metaAnalysisPromiseEM) {
        console.error('[META ANALYSE EM] Aucune Promise \u2014 fallback UI');
        openMetaResultPopupFallbackEM();
        return;
    }

    metaAnalysisPromiseEM
        .then(function() {
            if (finalAnalysisTextEM && metaResultDataEM) {
                console.log('[META ANALYSE EM] finalAnalysisTextEM OK \u2014 source:', window._metaAnalysisSourceEM);
                openMetaResultPopupEM(metaResultDataEM);
            }
            else if (metaResultDataEM && metaResultDataEM._localText) {
                console.warn('[META ANALYSE EM] Gemini indisponible \u2014 fallback explicite local');
                finalAnalysisTextEM = metaResultDataEM._localText;
                window._metaAnalysisSourceEM = 'explicit_local_fallback';
                metaResultDataEM.source = 'explicit_local_fallback';
                openMetaResultPopupEM(metaResultDataEM);
            }
            else {
                console.error('[META ANALYSE EM] Aucune donn\u00e9e');
                openMetaResultPopupFallbackEM();
            }
        })
        .catch(function(err) {
            console.error('[META ANALYSE EM] Promise rejet\u00e9e:', err);
            openMetaResultPopupFallbackEM();
        });
}

var META_ANALYSE_START_TIME_EM = null;

async function showMetaAnalysePopupEM() {
    console.log('[META ANALYSE EM] Ouverture fen\u00eatre META ANALYSE 75 grilles EM');

    // Umami — meta75 lancee EM
    if (typeof umami !== 'undefined') umami.track('meta75-launched', { module: 'euromillions' });

    META_ANALYSE_START_TIME_EM = Date.now();
    if (window.LotoIAAnalytics?.productEngine?.track) {
        window.LotoIAAnalytics.productEngine.track('meta_tunnel_start_em', { version: 75 });
        window.LotoIAAnalytics.productEngine.track('meta_popup_open_em', { version: 75 });
    }

    var currentMode = (typeof metaCurrentModeEM !== 'undefined') ? metaCurrentModeEM : 'tirages';
    var totalTirages = window.TOTAL_TIRAGES_EM || 729;
    var rowsToAnalyze = totalTirages;
    var isGlobal = true;

    if (currentMode === 'annees' && typeof metaYearsSizeEM !== 'undefined' && metaYearsSizeEM && metaYearsSizeEM !== 'GLOBAL') {
        rowsToAnalyze = parseInt(metaYearsSizeEM, 10) * 104;
        isGlobal = false;
    } else if (currentMode === 'tirages' && typeof metaWindowSizeEM !== 'undefined' && metaWindowSizeEM && metaWindowSizeEM !== 'GLOBAL') {
        rowsToAnalyze = parseInt(metaWindowSizeEM, 10);
        isGlobal = false;
    }

    triggerGeminiEarlyEM();

    var metaAnalyseLogs = getConsoleLogsEM(75, META_ANALYSE_TIMER_DURATION_EM, {
        rowsToAnalyze: rowsToAnalyze,
        isGlobal: isGlobal
    });

    var result = await showSponsorPopup75EM({
        duration: META_ANALYSE_TIMER_DURATION_EM,
        gridCount: 75,
        title: LI.meta_popup_title,
        isMetaAnalyse: true,
        logs: metaAnalyseLogs,
        onComplete: onMetaAnalyseCompleteEM
    });

    if (result && result.cancelled === true) {
        console.log('[META ANALYSE EM] Annul\u00e9 par l\'utilisateur');
        return result;
    }

    return result;
}

// ============================================
// EXPORTS EM
// ============================================

window.showSponsorPopup75EM = showSponsorPopup75EM;
window.showPopupBeforeGenerationEM = showPopupBeforeGenerationEM;
window.showPopupBeforeSimulationEM = showPopupBeforeSimulationEM;
window.calculateTimerDurationEM = calculateTimerDurationEM;
window.showMetaAnalysePopupEM = showMetaAnalysePopupEM;
window.META_ANALYSE_TIMER_DURATION_EM = META_ANALYSE_TIMER_DURATION_EM;

// ============================================
// CSS BADGE SOURCE META ANALYSE EM (injection JS)
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

console.log('[Sponsor Popup 75 EM] Module META ANALYSE EuroMillions loaded successfully');
