// ================================================================
// APP-EM.JS - EuroMillions Analysis UI Logic
// ================================================================
var LI = window.LotoIA_i18n || {};

// State management
let currentResult = null;
let selectedGridCount = 3;
var nextDrawDate = null;

// DOM Elements
const btnAnalyze = document.getElementById('btn-analyze');
const btnCopy = document.getElementById('btn-copy');
const resultsSection = document.getElementById('results-section');
const successState = document.getElementById('success-state');
const errorState = document.getElementById('error-state');

// ================================================================
// API FETCH UTILITIES
// ================================================================

async function fetchTiragesEM(endpoint) {
    try {
        const response = await fetch(endpoint);
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        if (!data.success) throw new Error(data.error || LI.api_error);
        return data.data;
    } catch (error) {
        console.error('Erreur fetchTiragesEM(' + endpoint + '):', error.message);
        throw error;
    }
}

// ================================================================
// INITIALIZATION
// ================================================================

function init() {
    initNextDraw();
    if (btnAnalyze) btnAnalyze.addEventListener('click', handleAnalyze);
    if (btnCopy) btnCopy.addEventListener('click', handleCopyEM);
    initGridCountSelector();
    updateStatsDisplay();
    setInterval(updateStatsDisplay, 5 * 60 * 1000);
}

// ================================================================
// STATS HERO DISPLAY
// ================================================================

function formatMonthYear(dateStr) {
    if (!dateStr) return '';
    var date = new Date(dateStr);
    return new Intl.DateTimeFormat(LI.locale, { month: 'short', year: 'numeric' }).format(date);
}

function updateStatsDisplay() {
    fetch('/api/euromillions/database-info')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.total_draws != null) {
                var totalDraws = data.total_draws || 0;

                var tiragesEl = document.getElementById('stat-tirages');
                if (tiragesEl) tiragesEl.textContent = totalDraws.toLocaleString(LI.locale) + LI.draws_suffix;

                var tiragesInline = document.getElementById('stat-tirages-inline');
                if (tiragesInline) tiragesInline.textContent = totalDraws.toLocaleString(LI.locale);

                document.querySelectorAll('.dynamic-tirages').forEach(function(el) {
                    el.textContent = totalDraws.toLocaleString(LI.locale);
                });

                window.TOTAL_TIRAGES_EM = totalDraws;

                var dataDepthEl = document.querySelector('.data-depth');
                if (dataDepthEl && data.first_draw && data.last_draw) {
                    dataDepthEl.textContent = LI.data_depth_from + formatMonthYear(data.first_draw) + LI.data_depth_to + formatMonthYear(data.last_draw);
                }
            }
        })
        .catch(function(err) {
            console.error('Erreur stats EM:', err);
        });
}

// ================================================================
// NEXT DRAW — EuroMillions: Mardi (2) et Vendredi (5)
// ================================================================

/**
 * Calcule et affiche la date du prochain tirage EuroMillions.
 */
function initNextDraw() {
    nextDrawDate = getNextDrawDate();

    // Afficher la date formatee dans le texte informatif
    var el = document.getElementById('next-draw-date');
    if (el) {
        var dateObj = new Date(nextDrawDate + 'T00:00:00');
        el.textContent = dateObj.toLocaleDateString(LI.locale, {
            weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
        });
    }

    updateDaysUntilDraw();
}

/**
 * Met a jour le message "Prochain tirage dans X jours"
 */
function updateDaysUntilDraw() {
    if (!nextDrawDate) return;

    var today = new Date();
    today.setHours(0, 0, 0, 0);

    var drawDate = new Date(nextDrawDate + 'T00:00:00');
    drawDate.setHours(0, 0, 0, 0);

    var diffTime = drawDate - today;
    var daysUntil = Math.round(diffTime / (1000 * 60 * 60 * 24));

    var daysElement = document.getElementById('days-until-draw');
    var urgencyText = document.querySelector('.urgency-text');

    if (!urgencyText) return;

    if (daysUntil === 0) {
        if (daysElement) daysElement.textContent = '';
        urgencyText.innerHTML = LI.countdown_tonight || 'Prochain tirage <strong>ce soir</strong>';
    } else if (daysUntil === 1) {
        if (daysElement) daysElement.textContent = '';
        urgencyText.innerHTML = LI.countdown_tomorrow || 'Prochain tirage <strong>demain</strong>';
    } else if (daysUntil < 0) {
        if (daysElement) daysElement.textContent = '';
        urgencyText.innerHTML = LI.countdown_past || 'S\u00e9lectionnez une date de tirage \u00e0 venir';
    } else {
        if (daysElement) daysElement.textContent = daysUntil;
    }
}

/**
 * Trouve le prochain jour de tirage EuroMillions (mardi ou vendredi)
 */
function getNextDrawDate() {
    var today = new Date();
    var dayOfWeek = today.getDay(); // 0=Dim, 1=Lun, 2=Mar, 3=Mer, 4=Jeu, 5=Ven, 6=Sam

    var daysToAdd = 0;
    switch (dayOfWeek) {
        case 0: daysToAdd = 2; break; // Dimanche -> Mardi
        case 1: daysToAdd = 1; break; // Lundi -> Mardi
        case 2: daysToAdd = 0; break; // Mardi -> Mardi (aujourd'hui)
        case 3: daysToAdd = 2; break; // Mercredi -> Vendredi
        case 4: daysToAdd = 1; break; // Jeudi -> Vendredi
        case 5: daysToAdd = 0; break; // Vendredi -> Vendredi (aujourd'hui)
        case 6: daysToAdd = 3; break; // Samedi -> Mardi
    }

    // Si c'est un jour de tirage mais apres 21h, passer au suivant
    var now = new Date();
    if (daysToAdd === 0 && now.getHours() >= 21) {
        switch (dayOfWeek) {
            case 2: daysToAdd = 3; break; // Mardi soir -> Vendredi
            case 5: daysToAdd = 4; break; // Vendredi soir -> Mardi
        }
    }

    var nextDate = new Date(today);
    nextDate.setDate(nextDate.getDate() + daysToAdd);
    return nextDate.toISOString().split('T')[0];
}

// ================================================================
// GRID COUNT SELECTOR
// ================================================================

function initGridCountSelector() {
    var selector = document.getElementById('grid-count-selector');
    if (!selector) return;

    var buttons = selector.querySelectorAll('.count-btn');
    buttons.forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            buttons.forEach(function(b) { b.classList.remove('active'); });
            btn.classList.add('active');
            selectedGridCount = parseInt(btn.dataset.count);
        });
    });
}

// ================================================================
// GENERATE GRIDS
// ================================================================

async function handleAnalyze() {
    var date = nextDrawDate;

    setLoading(btnAnalyze, true);
    hideResults();

    // Calculer la duree du popup selon le nombre de grilles (proportionnel)
    var popupDuration = typeof calculateTimerDurationSimulateurEM === 'function'
        ? calculateTimerDurationSimulateurEM(selectedGridCount)
        : 3;
    var plural = selectedGridCount > 1 ? 's' : '';

    // Afficher le popup sponsor AVANT l'appel API
    if (typeof showSponsorPopupSimulateurEM === 'function') {
        var popupResult = await showSponsorPopupSimulateurEM({
            duration: popupDuration,
            gridCount: selectedGridCount,
            title: (selectedGridCount === 1 && LI.popup_gen_title_one ? LI.popup_gen_title_one : LI.popup_gen_title.replace('{n}', selectedGridCount).replace(/\{s\}/g, plural)),
            onComplete: function() {
                console.log('[App EM] Popup sponsor termin\u00e9, lancement de la g\u00e9n\u00e9ration');
            }
        });

        // Verifier si l'utilisateur a annule
        if (popupResult && popupResult.cancelled === true) {
            console.log('[App EM] G\u00e9n\u00e9ration annul\u00e9e par l\'utilisateur');
            setLoading(btnAnalyze, false);
            return;
        }
    }

    try {
        var response = await fetch('/api/euromillions/generate?n=' + selectedGridCount + '&lang=' + window.LotoIA_lang);
        if (!response.ok) throw new Error(LI.http_error + response.status);

        var data = await response.json();

        if (data.success && data.grids) {
            currentResult = data;
            displayGridsEM(data.grids, data.metadata, date);

            // Pitch HYBRIDE async (non-blocking)
            fetchAndDisplayPitchsEM(data.grids);
        } else {
            showError(data.message || LI.error_generating);
        }
    } catch (error) {
        showError(LI.unable_generate + error.message);
    } finally {
        setLoading(btnAnalyze, false);
    }
}

// ================================================================
// PARTNER CARD — EuroMillions
// ================================================================

function _getEmSponsorId() {
    var emLang = (LI.locale || 'fr-FR').split('-')[0].toLowerCase() || 'fr';
    return 'EM_' + emLang.toUpperCase() + '_A';
}

function trackAdImpressionEM(adId) {
    var sponsorId = _getEmSponsorId();
    var emLang = (LI.locale || 'fr-FR').split('-')[0].toLowerCase() || 'fr';
    // Couche 1 — sponsor_impressions (source facturation)
    fetch('/api/sponsor/track', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        keepalive: true,
        body: JSON.stringify({
            event_type: 'sponsor-result-shown',
            sponsor_id: sponsorId,
            page: window.location.pathname,
            lang: emLang,
            device: /Mobi|Android/i.test(navigator.userAgent) ? 'mobile' : 'desktop'
        })
    }).catch(function() {});
    // Couche 2 — event_log
    if (typeof LotoIA_track === 'function') LotoIA_track('sponsor-result-shown', { sponsor_id: sponsorId, product_code: sponsorId });
}

function trackAdClickEM(adId, partnerId) {
    var sponsorId = _getEmSponsorId();
    var emLang = (LI.locale || 'fr-FR').split('-')[0].toLowerCase() || 'fr';
    fetch('/api/sponsor/track', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            event_type: 'sponsor-click',
            sponsor_id: sponsorId,
            page: window.location.pathname,
            lang: emLang,
            device: /Mobi|Android/i.test(navigator.userAgent) ? 'mobile' : 'desktop'
        })
    }).catch(function() {});
    if (typeof LotoIA_track === 'function') LotoIA_track('sponsor-click', { sponsor_id: sponsorId, product_code: sponsorId });
}

function createPartnerCardEM(index) {
    var adId = 'ad_' + Date.now() + '_' + index;
    var partnerId = 'partner_demo';
    trackAdImpressionEM(adId);
    return '<div class="partner-card" data-ad-id="' + adId + '" data-partner-id="' + partnerId + '">' +
        '<div class="partner-content">' +
        '<div class="partner-badge">' + (LI.partner_label || 'Partenaire') + '</div>' +
        '<div class="partner-body">' +
        '<p class="partner-text">LotoIA.fr ' + (LI.partner_text || 'est propulsé par nos partenaires') + '</p>' +
        '<a href="#" class="partner-cta" onclick="trackAdClickEM(\'' + adId + '\',\'' + partnerId + '\');return false;">' +
        (LI.partner_cta || 'En savoir plus') + '</a>' +
        '</div></div></div>';
}

// ================================================================
// BALL DROP ANIMATION — EuroMillions
// ================================================================

function animateBallDropEM(container) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var cards = container.querySelectorAll('.grid-visual-card');
    function animateCard(card) {
        var mains = card.querySelectorAll('.grid-visual-numbers .visual-ball.main');
        mains.forEach(function(b, i) {
            setTimeout(function() { b.classList.add('ball-animate'); }, i * 150);
        });
        var sep = card.querySelector('.visual-ball.separator');
        if (sep) setTimeout(function() { sep.classList.add('ball-animate'); }, 900);
        var stars = card.querySelectorAll('.visual-ball.chance');
        stars.forEach(function(s, j) {
            setTimeout(function() { s.classList.add('ball-animate'); }, 900 + j * 150);
        });
        var badges = card.querySelectorAll('.visual-badge');
        badges.forEach(function(bg, j) {
            setTimeout(function() { bg.classList.add('ball-animate'); }, 1100 + j * 100);
        });
    }
    var obs = new IntersectionObserver(function(entries) {
        entries.forEach(function(e) {
            if (e.isIntersecting) {
                obs.unobserve(e.target);
                animateCard(e.target);
            }
        });
    }, { threshold: 0.3 });
    cards.forEach(function(card) { obs.observe(card); });
}

// ================================================================
// COPY GRIDS — EuroMillions
// ================================================================

function handleCopyEM() {
    if (!currentResult || !currentResult.grids) return;
    var text = currentResult.grids.map(function(grid, i) {
        var nums = grid.nums.slice().sort(function(a, b) { return a - b; })
            .map(function(n) { return String(n).padStart(2, '0'); }).join(' ');
        var stars = (grid.etoiles || []).slice().sort(function(a, b) { return a - b; })
            .map(function(s) { return String(s).padStart(2, '0'); }).join(' ');
        return (LI.grid_label || 'Grille') + ' ' + (i + 1) + ' : ' + nums + ' + ' + stars;
    }).join('\n');
    navigator.clipboard.writeText(text).then(function() {
        if (window.LotoIAAnalytics && window.LotoIAAnalytics.product) {
            window.LotoIAAnalytics.product.copyGrid({});
        }
        var orig = btnCopy.textContent;
        btnCopy.textContent = '\u2713';
        setTimeout(function() { btnCopy.textContent = orig; }, 1500);
    }).catch(function() {
        alert(LI.copy_error || 'Erreur lors de la copie');
    });
}

// ================================================================
// DISPLAY GRIDS — EuroMillions (5 nums + 2 etoiles)
// ================================================================

function displayGridsEM(grids, metadata, targetDate) {
    var dateObj = new Date(targetDate + 'T00:00:00');
    var dateFormatted = dateObj.toLocaleDateString(LI.locale, {
        weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
    });

    var html = '<div class="results-header">' +
        '<h2>' + LI.grids_for + dateFormatted + '</h2>' +
        '<div class="results-meta">' +
        '<span>' + grids.length + (grids.length === 1 && LI.grid_generated_one ? LI.grid_generated_one : LI.grids_generated) + '</span>' +
        '<span>' + new Date().toLocaleTimeString(LI.locale) + '</span>' +
        '</div></div>';

    grids.forEach(function(grid, index) {
        var badges = grid.badges || [];
        var convergenceLabel = LI.profile_balanced;
        var convergenceClass = 'convergence-elevated';

        if (badges.some(function(b) { var bl = b.toLowerCase(); return bl.indexOf('chaud') !== -1 || bl.indexOf('hot') !== -1; })) {
            convergenceLabel = LI.profile_hot;
        } else if (badges.some(function(b) { var bl = b.toLowerCase(); return bl.indexOf('retard') !== -1 || bl.indexOf('cart') !== -1 || bl.indexOf('overdue') !== -1; })) {
            convergenceLabel = LI.profile_mixed;
            convergenceClass = 'convergence-moderate';
        }

        html += '<div class="grid-visual-card" style="animation-delay: ' + (index * 0.15) + 's">' +
            '<div class="grid-visual-header">' +
            '<div class="grid-number"><span class="grid-number-label">' + LI.grid_label + '</span>' +
            '<span class="grid-number-value">#' + (index + 1) + '</span></div>' +
            '<div class="grid-convergence-indicator ' + convergenceClass + '">' +
            '<span class="convergence-label">' + LI.profile_label + '</span>' +
            '<span class="convergence-value">' + convergenceLabel + '</span></div></div>' +
            '<div class="grid-visual-numbers">';

        grid.nums.slice().sort(function(a, b) { return a - b; }).forEach(function(n) {
            html += '<div class="visual-ball main ball-drop">' + String(n).padStart(2, '0') + '</div>';
        });

        html += '<div class="visual-ball separator ball-drop">+</div>';

        (grid.etoiles || []).slice().sort(function(a, b) { return a - b; }).forEach(function(s) {
            html += '<div class="visual-ball chance ball-drop">' + String(s).padStart(2, '0') + '</div>';
        });

        html += '</div><div class="grid-visual-badges">';

        (grid.badges || []).forEach(function(badge) {
            var icon = '\u{1F3AF}';
            var badgeClass = 'badge-default';

            if (badge.toLowerCase().indexOf('chaud') !== -1 || badge.toLowerCase().indexOf('hot') !== -1) { icon = '\u{1F525}'; badgeClass = 'badge-hot'; }
            else if (badge.toLowerCase().indexOf('spectre') !== -1 || badge.toLowerCase().indexOf('spectrum') !== -1) { icon = '\u{1F4CF}'; badgeClass = 'badge-spectrum'; }
            else if (badge.toLowerCase().indexOf('quilibr') !== -1 || badge.toLowerCase().indexOf('balanced') !== -1) { icon = '\u2696\uFE0F'; badgeClass = 'badge-balanced'; }
            else if (badge.toLowerCase().indexOf('hybride') !== -1) { icon = '\u2699\uFE0F'; badgeClass = 'badge-hybrid'; }
            else if (badge.toLowerCase().indexOf('retard') !== -1 || badge.toLowerCase().indexOf('overdue') !== -1) { icon = '\u23F0'; badgeClass = 'badge-gap'; }

            html += '<span class="visual-badge ' + badgeClass + ' ball-drop">' + icon + ' ' + badge + '</span>';
        });

        html += '</div>' +
            '<div class="grille-pitch grille-pitch-loading" data-pitch-index="' + index + '">' +
                '<span class="pitch-icon">\u{1F916}</span> ' + LI.pitch_loading +
            '</div>' +
        '</div>';

        // Afficher card partenaire APRES chaque grille
        html += createPartnerCardEM(index);
    });

    html += '<div class="results-footer">' +
        '<p><strong>' + LI.reminder_title + '</strong> ' + LI.reminder_text + '</p>' +
        '<p>' + LI.play_responsible + '<a href="' + LI.gambling_url + '" target="_blank">' + LI.gambling_name + '</a></p></div>';

    var keyInfo = document.getElementById('key-info');
    var numbersGrid = document.getElementById('numbers-grid');
    var explanationsSection = document.getElementById('explanations-section');

    if (numbersGrid) numbersGrid.innerHTML = '';
    if (keyInfo) {
        keyInfo.innerHTML = html;
        keyInfo.style.background = 'transparent';
        keyInfo.style.borderLeft = 'none';
        keyInfo.style.padding = '0';
    }
    if (explanationsSection) explanationsSection.style.display = 'none';

    var resultTitle = document.getElementById('result-title');
    if (resultTitle) resultTitle.textContent = LI.result_title;
    showSuccess();
    if (keyInfo) animateBallDropEM(keyInfo);
}

// ================================================================
// UI HELPERS
// ================================================================

function showSuccess() {
    if (resultsSection) resultsSection.style.display = 'block';
    if (successState) successState.style.display = 'block';
    if (errorState) errorState.style.display = 'none';
    if (resultsSection) {
        resultsSection.classList.add('fade-in');
        setTimeout(function() {
            resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 300);
    }
}

function showError(message) {
    if (resultsSection) resultsSection.style.display = 'block';
    if (successState) successState.style.display = 'none';
    if (errorState) errorState.style.display = 'block';
    var errMsg = document.getElementById('error-message');
    if (errMsg) errMsg.textContent = message;
}

function hideResults() {
    if (resultsSection) resultsSection.style.display = 'none';
    if (successState) successState.style.display = 'none';
    if (errorState) errorState.style.display = 'none';
}

function setLoading(button, isLoading) {
    if (!button) return;
    var btnText = button.querySelector('.btn-text') || button.querySelector('.cta-text');
    var spinner = button.querySelector('.spinner');
    var ctaIcon = button.querySelector('.cta-icon');
    var ctaArrow = button.querySelector('.cta-arrow');

    if (isLoading) {
        button.disabled = true;
        if (btnText) btnText.style.display = 'none';
        if (ctaIcon) ctaIcon.style.display = 'none';
        if (ctaArrow) ctaArrow.style.display = 'none';
        if (spinner) spinner.style.display = 'block';
    } else {
        button.disabled = false;
        if (btnText) btnText.style.display = 'inline';
        if (ctaIcon) ctaIcon.style.display = 'inline';
        if (ctaArrow) ctaArrow.style.display = 'inline';
        if (spinner) spinner.style.display = 'none';
    }
}

// ================================================================
// PITCH HYBRIDE EM — Gemini async
// ================================================================

/**
 * Appelle /api/euromillions/pitch-grilles et affiche les pitchs sous chaque grille EM.
 * Non-bloquant : les grilles sont deja visibles, les pitchs arrivent apres.
 * @param {Array} grids - Tableau des grilles generees ({nums, etoiles})
 */
async function fetchAndDisplayPitchsEM(grids) {
    // V130: closure retry pattern — payload capturé, retryCount limité à 3.
    var payload = grids.map(function(g) {
        return { numeros: g.nums, etoiles: g.etoiles || [] };
    });
    var LI = window.LotoIA_i18n || {};
    var retryCount = 0;

    async function doFetch() {
        try {
            var response = await fetch('/api/euromillions/pitch-grilles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ grilles: payload, lang: window.LotoIA_lang })
            });

            if (response.ok) {
                var data = await response.json();
                if (data.success && data.data && data.data.pitchs) {
                    _removePitchFallbackGlobalEM();
                    data.data.pitchs.forEach(function(pitch, index) {
                        var el = document.querySelector('.grille-pitch[data-pitch-index="' + index + '"]');
                        if (el && pitch) {
                            el.innerHTML = '<span class="pitch-icon">\u{1F916}</span> ' + pitch;
                            el.classList.remove('grille-pitch-loading');
                        }
                    });
                    return;
                }
            }
            // V130: 502/503/data.success=false → fallback global
            _showPitchFallbackEM();
        } catch (e) {
            console.warn('[PITCH EM] Erreur:', e);
            _showPitchFallbackEM();
        }
    }

    function _showPitchFallbackEM() {
        document.querySelectorAll('.grille-pitch-loading').forEach(function(el) {
            el.classList.remove('grille-pitch-loading');
            el.innerHTML = '';
        });
        _insertPitchFallbackGlobalEM(retryCount >= 3);
    }

    function _insertPitchFallbackGlobalEM(isFinal) {
        _removePitchFallbackGlobalEM();
        var container = document.getElementById('results-section') || document.body;
        var block = document.createElement('div');
        block.id = 'pitch-fallback-global';
        block.className = 'pitch-fallback' + (isFinal ? ' pitch-fallback-final' : '');

        var icon = document.createElement('div');
        icon.className = 'pitch-fallback-icon';
        icon.textContent = '\u{1F916}';
        block.appendChild(icon);

        var msg = document.createElement('div');
        msg.className = 'pitch-fallback-message';
        if (isFinal) {
            msg.innerHTML = '<p>' + (LI.pitch_fallback_final || "L'analyse IA reste indisponible. Votre grille est valide, réessayez plus tard.") + '</p>';
        } else {
            msg.innerHTML =
                '<strong>' + (LI.pitch_fallback_title || "Analyse Hybride momentanément indisponible") + '</strong>' +
                '<p>' + (LI.pitch_fallback_message || "Votre grille est validée et optimisée. L'IA est en cours de surcharge, vous pouvez réessayer.") + '</p>';
        }
        block.appendChild(msg);

        if (!isFinal) {
            var btn = document.createElement('button');
            btn.className = 'pitch-fallback-retry';
            btn.type = 'button';
            btn.textContent = LI.pitch_fallback_retry || "Réessayer l'analyse IA";
            btn.addEventListener('click', function() {
                retryCount += 1;
                _removePitchFallbackGlobalEM();
                document.querySelectorAll('.grille-pitch[data-pitch-index]').forEach(function(el) {
                    el.classList.add('grille-pitch-loading');
                    el.innerHTML = '<span class="pitch-icon">\u{1F916}</span> ' + (LI.pitch_loading || 'HYBRIDE EM analyse ta grille\u2026');
                });
                doFetch();
            });
            block.appendChild(btn);
        }
        container.insertBefore(block, container.firstChild);
    }

    function _removePitchFallbackGlobalEM() {
        var existing = document.getElementById('pitch-fallback-global');
        if (existing) existing.remove();
    }

    await doFetch();
}

// ================================================================
// START APP
// ================================================================

document.addEventListener('DOMContentLoaded', init);
