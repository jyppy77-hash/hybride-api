// ================================================================
// APP-EM.JS - EuroMillions Analysis UI Logic
// ================================================================
var LI = window.LotoIA_i18n || {};

// State management
let currentResult = null;
let selectedGridCount = 3;

// DOM Elements
const drawDateInput = document.getElementById('draw-date');
const btnAnalyze = document.getElementById('btn-analyze');
const resultsSection = document.getElementById('results-section');
const successState = document.getElementById('success-state');
const errorState = document.getElementById('error-state');
const dateError = document.getElementById('date-error');

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
    configureDatePicker();
    if (drawDateInput) drawDateInput.addEventListener('change', validateDateInput);
    if (btnAnalyze) btnAnalyze.addEventListener('click', handleAnalyze);
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
            if (data.exists) {
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
// DATE PICKER — EuroMillions: Mardi (2) et Vendredi (5)
// ================================================================

function configureDatePicker() {
    if (!drawDateInput) return;

    var nextDrawDate = getNextDrawDate();
    drawDateInput.value = nextDrawDate;

    var today = new Date();
    drawDateInput.min = today.toISOString().split('T')[0];

    var maxDate = new Date();
    maxDate.setMonth(maxDate.getMonth() + 3);
    drawDateInput.max = maxDate.toISOString().split('T')[0];

    validateDateInput();
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

/**
 * Verifie si jour de tirage EM (Mardi=2, Vendredi=5)
 */
function isDrawDay(date) {
    var day = date.getDay();
    return day === 2 || day === 5;
}

function findNextDrawDate(fromDate) {
    var date = new Date(fromDate);
    var dayOfWeek = date.getDay();

    if (dayOfWeek === 2 || dayOfWeek === 5) {
        return date.toISOString().split('T')[0];
    }

    var daysToAdd = 0;
    switch (dayOfWeek) {
        case 0: daysToAdd = 2; break;
        case 1: daysToAdd = 1; break;
        case 3: daysToAdd = 2; break;
        case 4: daysToAdd = 1; break;
        case 6: daysToAdd = 3; break;
    }

    date.setDate(date.getDate() + daysToAdd);
    return date.toISOString().split('T')[0];
}

function validateDateInput() {
    if (!drawDateInput) return;
    var dateValue = drawDateInput.value;
    if (!dateValue) {
        hideDateError();
        disableActionButtons(false);
        return;
    }

    var selectedDate = new Date(dateValue + 'T00:00:00');

    if (!isDrawDay(selectedDate)) {
        var nextValidDate = findNextDrawDate(selectedDate);
        var nextDateFormatted = new Date(nextValidDate + 'T00:00:00').toLocaleDateString(LI.locale, {
            weekday: 'long', day: 'numeric', month: 'long'
        });

        showDateError(LI.no_draw_msg + nextDateFormatted);
        disableActionButtons(true);

        setTimeout(function() {
            if (drawDateInput.value === dateValue) {
                drawDateInput.value = nextValidDate;
                hideDateError();
                disableActionButtons(false);
            }
        }, 1500);
    } else {
        hideDateError();
        disableActionButtons(false);
    }
}

function showDateError(message) {
    if (!dateError) return;
    dateError.textContent = message;
    dateError.style.display = 'block';
    drawDateInput.style.borderColor = '#d32f2f';
}

function hideDateError() {
    if (!dateError) return;
    dateError.style.display = 'none';
    drawDateInput.style.borderColor = '';
}

function disableActionButtons(disable) {
    if (!btnAnalyze) return;
    btnAnalyze.disabled = disable;
    btnAnalyze.style.opacity = disable ? '0.5' : '1';
    btnAnalyze.style.cursor = disable ? 'not-allowed' : 'pointer';
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
    if (!drawDateInput) return;
    var date = drawDateInput.value;
    if (!date) {
        showError(LI.select_date);
        return;
    }

    var selectedDate = new Date(date + 'T00:00:00');
    if (!isDrawDay(selectedDate)) {
        showError(LI.draw_days_only);
        return;
    }

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
            title: LI.popup_gen_title.replace('{n}', selectedGridCount).replace(/\{s\}/g, plural),
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
        '<span>' + grids.length + LI.grids_generated + '</span>' +
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
            html += '<div class="visual-ball main">' + String(n).padStart(2, '0') + '</div>';
        });

        html += '<div class="visual-ball separator">+</div>';

        (grid.etoiles || []).slice().sort(function(a, b) { return a - b; }).forEach(function(s) {
            html += '<div class="visual-ball chance">' + String(s).padStart(2, '0') + '</div>';
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

            html += '<span class="visual-badge ' + badgeClass + '">' + icon + ' ' + badge + '</span>';
        });

        html += '</div>' +
            '<div class="grille-pitch grille-pitch-loading" data-pitch-index="' + index + '">' +
                '<span class="pitch-icon">\u{1F916}</span> ' + LI.pitch_loading +
            '</div>' +
        '</div>';
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
    var payload = grids.map(function(g) {
        return {
            numeros: g.nums,
            etoiles: g.etoiles || []
        };
    });

    try {
        var response = await fetch('/api/euromillions/pitch-grilles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ grilles: payload, lang: window.LotoIA_lang })
        });
        var data = await response.json();

        if (data.success && data.data && data.data.pitchs) {
            data.data.pitchs.forEach(function(pitch, index) {
                var el = document.querySelector('.grille-pitch[data-pitch-index="' + index + '"]');
                if (el && pitch) {
                    el.innerHTML = '<span class="pitch-icon">\u{1F916}</span> ' + pitch;
                    el.classList.remove('grille-pitch-loading');
                }
            });
        } else {
            // Pas de pitchs — retirer les placeholders
            document.querySelectorAll('.grille-pitch-loading').forEach(function(el) { el.remove(); });
        }
    } catch (e) {
        console.warn('[PITCH EM] Erreur:', e);
        document.querySelectorAll('.grille-pitch-loading').forEach(function(el) { el.remove(); });
    }
}

// ================================================================
// START APP
// ================================================================

document.addEventListener('DOMContentLoaded', init);
