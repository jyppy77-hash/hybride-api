/**
 * Simulateur de Grille EuroMillions
 * Interface interactive pour composer et analyser des grilles EM
 * 5 numeros (1-50) + 2 etoiles (1-12)
 */

var LI = window.LotoIA_i18n || {};

// State
const state = {
    selectedNumbers: new Set(),
    selectedStars: new Set(),
    numbersHeat: {},
    debounceTimer: null,
    popupShownForCurrentGrid: false,
    statsLoaded: false,
    totalTirages: 0
};

// DOM Elements
const elements = {
    mainGrid: document.getElementById('main-grid'),
    starGrid: document.getElementById('star-grid'),
    countMain: document.getElementById('count-main'),
    countStar: document.getElementById('count-star'),
    resultsSection: document.getElementById('results-section'),
    loadingOverlay: document.getElementById('loading-overlay'),
    btnReset: document.getElementById('btn-reset'),
    btnAuto: document.getElementById('btn-auto')
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadNumbersHeat();
    initStarGrid();
    bindEvents();
});

/**
 * Load heat data for numbers (hot/cold/neutral)
 * Connecte au Cloud SQL via /api/euromillions/numbers-heat
 */
async function loadNumbersHeat() {
    try {
        const response = await fetch('/api/euromillions/numbers-heat');
        const data = await response.json();

        if (data.success) {
            state.numbersHeat = data.boules || {};
            state.totalTirages = data.total_tirages || 0;
            state.statsLoaded = true;
            updateTiragesDisplay();
        } else {
            generateFallbackHeat();
        }
    } catch (error) {
        console.error('[Simulateur EM] Erreur chargement heat:', error);
        generateFallbackHeat();
    }

    initMainGrid();
}

/**
 * Fallback si l'API n'est pas disponible
 */
function generateFallbackHeat() {
    for (let i = 1; i <= 50; i++) {
        state.numbersHeat[i] = {
            category: 'neutral',
            frequency: 0,
            last_draw: null
        };
    }
    state.statsLoaded = false;
}

/**
 * Met a jour l'affichage du nombre de tirages
 */
function updateTiragesDisplay() {
    window.TOTAL_TIRAGES_EM = state.totalTirages;

    const tiragesElement = document.getElementById('stats-tirages');
    if (tiragesElement) {
        tiragesElement.textContent = LI.based_on_draws.replace('{n}', state.totalTirages.toLocaleString(LI.locale));
    }

    document.querySelectorAll('.dynamic-tirages').forEach(function(el) {
        el.textContent = state.totalTirages.toLocaleString(LI.locale);
    });
}

/**
 * Initialize main grid (1-50)
 */
function initMainGrid() {
    elements.mainGrid.innerHTML = '';

    for (let i = 1; i <= 50; i++) {
        const btn = document.createElement('button');
        btn.className = 'grid-number';
        btn.textContent = i;
        btn.dataset.number = i;

        const heat = state.numbersHeat[i] || state.numbersHeat[String(i)];
        if (heat) {
            btn.classList.add(heat.category);
            btn.title = LI.heat_title_freq + heat.frequency + LI.heat_title_last + (heat.last_draw || 'N/A');
        } else {
            btn.classList.add('neutral');
        }

        btn.addEventListener('click', function() { toggleNumber(i); });
        elements.mainGrid.appendChild(btn);
    }
}

/**
 * Initialize star grid (1-12) — 2 selections
 */
function initStarGrid() {
    elements.starGrid.innerHTML = '';

    for (let i = 1; i <= 12; i++) {
        const btn = document.createElement('button');
        btn.className = 'chance-number';
        btn.textContent = i;
        btn.dataset.star = i;
        btn.addEventListener('click', function() { toggleStar(i); });
        elements.starGrid.appendChild(btn);
    }
}

/**
 * Toggle number selection (max 5)
 */
function toggleNumber(num) {
    const btn = elements.mainGrid.querySelector('[data-number="' + num + '"]');

    if (state.selectedNumbers.has(num)) {
        state.selectedNumbers.delete(num);
        btn.classList.remove('selected');
    } else {
        if (state.selectedNumbers.size >= 5) return;
        state.selectedNumbers.add(num);
        btn.classList.add('selected');
    }

    updateMainGridState();
    updateCountBadge();
    triggerAnalysis();
}

/**
 * Toggle star selection (max 2)
 */
function toggleStar(num) {
    const btn = elements.starGrid.querySelector('[data-star="' + num + '"]');

    if (state.selectedStars.has(num)) {
        state.selectedStars.delete(num);
        btn.classList.remove('selected');
    } else {
        if (state.selectedStars.size >= 2) return;
        state.selectedStars.add(num);
        btn.classList.add('selected');
    }

    updateStarGridState();
    updateCountBadge();
    triggerAnalysis();
}

/**
 * Update main grid state (disable unselected when 5 selected)
 */
function updateMainGridState() {
    const btns = elements.mainGrid.querySelectorAll('.grid-number');
    const maxReached = state.selectedNumbers.size >= 5;

    btns.forEach(function(btn) {
        if (maxReached) {
            btn.classList.toggle('disabled', !btn.classList.contains('selected'));
        } else {
            btn.classList.remove('disabled');
        }
    });
}

/**
 * Update star grid state (disable unselected when 2 selected)
 */
function updateStarGridState() {
    const btns = elements.starGrid.querySelectorAll('.chance-number');
    const maxReached = state.selectedStars.size >= 2;

    btns.forEach(function(btn) {
        if (maxReached) {
            btn.classList.toggle('disabled', !btn.classList.contains('selected'));
        } else {
            btn.classList.remove('disabled');
        }
    });
}

/**
 * Update count badges
 */
function updateCountBadge() {
    const mainCount = state.selectedNumbers.size;
    elements.countMain.textContent = mainCount + '/5';
    elements.countMain.classList.toggle('complete', mainCount === 5);

    const starCount = state.selectedStars.size;
    elements.countStar.textContent = starCount + '/2';
    elements.countStar.classList.toggle('complete', starCount === 2);
}

/**
 * Trigger analysis with debounce
 */
function triggerAnalysis() {
    if (state.debounceTimer) {
        clearTimeout(state.debounceTimer);
    }

    // Check if grid is complete: 5 numbers + 2 stars
    if (state.selectedNumbers.size !== 5 || state.selectedStars.size !== 2) {
        elements.resultsSection.style.display = 'none';
        // Reset popup flag si grille incomplete (user modifie sa selection)
        state.popupShownForCurrentGrid = false;
        return;
    }

    // Debounce 300ms
    state.debounceTimer = setTimeout(function() {
        // Afficher le popup sponsor seulement la 1ere fois que cette grille est completee
        var showPopup = !state.popupShownForCurrentGrid;
        if (showPopup) {
            state.popupShownForCurrentGrid = true;
        }
        analyzeGrid(showPopup);
    }, 300);
}

/**
 * Analyze the current grid via EM API
 * @param {boolean} withPopup - Afficher le pop-up sponsor (true pour premiere analyse)
 */
async function analyzeGrid(withPopup) {
    if (withPopup === undefined) withPopup = false;

    const nums = Array.from(state.selectedNumbers);
    const stars = Array.from(state.selectedStars).sort(function(a, b) { return a - b; });

    // Afficher le pop-up sponsor si demande (premiere completion de grille)
    if (withPopup && typeof showSponsorPopupSimulateurEM === 'function') {
        var popupResult = await showSponsorPopupSimulateurEM({
            duration: 3,
            gridCount: 1,
            title: LI.analyzing_grid,
            onComplete: function() {
                console.log('[Simulateur EM] Popup sponsor termin\u00e9, lancement analyse');
            }
        });

        // Verifier si l'utilisateur a annule
        if (popupResult && popupResult.cancelled === true) {
            console.log('[Simulateur EM] Analyse annul\u00e9e par l\'utilisateur');
            state.popupShownForCurrentGrid = false;
            return;
        }
    }

    elements.loadingOverlay.style.display = 'flex';

    try {
        const params = new URLSearchParams();
        nums.forEach(function(n) { params.append('nums', n); });
        params.append('etoile1', stars[0]);
        params.append('etoile2', stars[1]);
        params.append('lang', window.LotoIA_lang);

        const response = await fetch('/api/euromillions/analyze-custom-grid?' + params.toString(), {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            displayResults(data);
        } else {
            console.error('Erreur analyse EM:', data.error);
        }
    } catch (error) {
        console.error('Erreur fetch EM:', error);
    } finally {
        elements.loadingOverlay.style.display = 'none';
    }
}

/**
 * Display analysis results
 */
function displayResults(data) {
    elements.resultsSection.style.display = 'block';

    displayConvergenceLevel(data.score);

    var comparaisonEl = document.getElementById('comparaison-text');
    if (comparaisonEl) comparaisonEl.textContent = data.comparaison || '';

    displayBadges(data.badges || []);
    displayDetails(data.details || {});
    displaySuggestions(data.suggestions || [], data.severity, data.alert_message);
    var etoiles = data.etoiles || Array.from(state.selectedStars).sort(function(a, b) { return a - b; });
    displaySelectedGrid(data.nums || Array.from(state.selectedNumbers), etoiles[0], etoiles[1]);
    displayHistoryCheck(data.history_check);

    // Umami — audit de grille EM
    if (typeof umami !== 'undefined') umami.track('simulateur-grille-audited', { module: 'euromillions' });

    // Pitch HYBRIDE async (non-blocking) — transmet score conformite + severite
    fetchAndDisplaySimulateurPitchEM(
        Array.from(state.selectedNumbers),
        Array.from(state.selectedStars).sort(function(a, b) { return a - b; }),
        data.details ? data.details.score_conformite : undefined,
        data.severity
    );

    setTimeout(function() {
        var target = document.getElementById('selected-numbers') || document.querySelector('.selected-grid');
        if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }, 150);
}

/**
 * Affiche le niveau de convergence
 */
function displayConvergenceLevel(score) {
    var levelEl = document.getElementById('convergence-level');
    var container = document.querySelector('.convergence-display');

    var label, levelClass;
    if (score >= 80) {
        label = LI.convergence_strong;
        levelClass = 'convergence-elevated';
    } else if (score >= 60) {
        label = LI.convergence_moderate;
        levelClass = 'convergence-moderate';
    } else if (score >= 40) {
        label = LI.convergence_intermediate;
        levelClass = 'convergence-intermediate';
    } else {
        label = LI.convergence_partial;
        levelClass = 'convergence-partial';
    }

    container.className = 'convergence-display ' + levelClass;

    levelEl.style.opacity = '0';
    levelEl.style.transform = 'translateY(8px)';
    setTimeout(function() {
        levelEl.textContent = label;
        levelEl.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        levelEl.style.opacity = '1';
        levelEl.style.transform = 'translateY(0)';
    }, 150);
}

/**
 * Display badges
 */
function displayBadges(badges) {
    var container = document.getElementById('badges-container');
    container.innerHTML = '';

    var iconMap = {
        'chaud': '\u{1F525}', 'hot': '\u{1F525}',
        'spectre': '\u{1F4CF}', 'spectrum': '\u{1F4CF}',
        'quilibr': '\u2696\uFE0F', 'balanced': '\u2696\uFE0F',
        'Pair': '\u2705', 'Even': '\u2705',
        'Hybride': '\u2699\uFE0F',
        'retard': '\u23F0', 'overdue': '\u23F0',
        'froid': '\u2744\uFE0F', 'cold': '\u2744\uFE0F',
        'Mix': '\u{1F3B0}'
    };

    badges.forEach(function(badge, index) {
        var el = document.createElement('span');
        el.className = 'badge';
        el.style.animationDelay = (index * 0.1) + 's';

        var icon = '\u{1F3AF}';
        for (var key in iconMap) {
            if (badge.toLowerCase().indexOf(key.toLowerCase()) !== -1) {
                icon = iconMap[key];
                break;
            }
        }

        if (badge.toLowerCase().indexOf('chaud') !== -1 || badge.toLowerCase().indexOf('hot') !== -1) el.classList.add('hot');
        else if (badge.indexOf('quilibr') !== -1 || badge.indexOf('Pair') !== -1 || badge.toLowerCase().indexOf('balanced') !== -1 || badge.indexOf('Even') !== -1) el.classList.add('balance');
        else if (badge.toLowerCase().indexOf('spectre') !== -1 || badge.toLowerCase().indexOf('spectrum') !== -1) el.classList.add('spectre');
        else if (badge.indexOf('Hybride') !== -1) el.classList.add('model');
        else if (badge.toLowerCase().indexOf('froid') !== -1) el.classList.add('cold');

        el.innerHTML = '<span>' + icon + '</span><span>' + badge + '</span>';
        container.appendChild(el);
    });
}

/**
 * Display details grid
 */
function displayDetails(details) {
    var container = document.getElementById('details-grid');
    container.innerHTML = '';

    var config = [
        { key: 'pairs_impairs', label: LI.detail_even_odd, icon: '\u2696\uFE0F',
          evaluate: function(v) { var p = parseInt(v.split('/')[0]); return (p>=2&&p<=3)?'good':(p>=1&&p<=4)?'warning':'bad'; }},
        { key: 'bas_haut', label: LI.detail_low_high, icon: '\u{1F4CA}',
          evaluate: function(v) { var b = parseInt(v.split('/')[0]); return (b>=2&&b<=3)?'good':(b>=1&&b<=4)?'warning':'bad'; }},
        { key: 'somme', label: LI.detail_sum, icon: '\u2795',
          evaluate: function(v) { var n = parseInt(v); return (n>=105&&n<=150)?'good':(n>=75&&n<=180)?'warning':'bad'; }},
        { key: 'dispersion', label: LI.detail_spread, icon: '\u2194\uFE0F',
          evaluate: function(v) { var n = parseInt(v); return (n>=20&&n<=42)?'good':(n>=15&&n<=47)?'warning':'bad'; }},
        { key: 'suites_consecutives', label: LI.detail_runs, icon: '\u{1F517}',
          evaluate: function(v) { var n = parseInt(v); return (n<=1)?'good':(n===2)?'warning':'bad'; }},
        { key: 'score_conformite', label: LI.detail_compliance, icon: '\u2713',
          evaluate: function(v) { var n = parseFloat(v); return (n>=80)?'good':(n>=50)?'warning':'bad'; }}
    ];

    config.forEach(function(c) {
        if (details[c.key] !== undefined) {
            var item = document.createElement('div');
            item.className = 'detail-item ' + c.evaluate(String(details[c.key]));
            item.innerHTML = '<div class="detail-icon">' + c.icon + '</div>' +
                '<div class="detail-label">' + c.label + '</div>' +
                '<div class="detail-value">' + details[c.key] + '</div>';
            container.appendChild(item);
        }
    });
}

/**
 * Display suggestions with severity
 */
function displaySuggestions(suggestions, severity, alertMessage) {
    var list = document.getElementById('suggestions-list');
    list.innerHTML = '';

    var oldAlert = list.parentElement.querySelector('.severity-alert');
    if (oldAlert) oldAlert.remove();

    if (severity === 3 && alertMessage) {
        var alertDiv = document.createElement('div');
        alertDiv.className = 'severity-alert severity-alert-critical';
        alertDiv.innerHTML = '<span class="severity-alert-icon">\u{1F6A8}</span> <strong>' + alertMessage + '</strong>';
        list.parentElement.insertBefore(alertDiv, list);
    }

    suggestions.forEach(function(suggestion, index) {
        var li = document.createElement('li');
        li.textContent = suggestion;
        li.style.animationDelay = (index * 0.1) + 's';

        if (severity === 3) {
            li.classList.add('critical');
            li.setAttribute('data-icon', '\u{1F534}');
        } else if (severity === 2) {
            li.classList.add('negative');
            li.setAttribute('data-icon', '\u26A0\uFE0F');
        } else if (suggestion.indexOf('Excellent') !== -1 || suggestion.indexOf('bien') !== -1 || suggestion.indexOf('Good') !== -1 || suggestion.indexOf('good') !== -1) {
            li.classList.add('positive');
            li.setAttribute('data-icon', '\u2705');
        } else if (suggestion.indexOf('Attention') !== -1 || suggestion.indexOf('Elargir') !== -1 || suggestion.indexOf('Warning') !== -1 || suggestion.indexOf('Widen') !== -1 || suggestion.indexOf('Broaden') !== -1) {
            li.classList.add('neutral');
            li.setAttribute('data-icon', '\u{1F4A1}');
        } else {
            li.classList.add('positive');
            li.setAttribute('data-icon', '\u2705');
        }

        list.appendChild(li);
    });
}

/**
 * Display selected grid — 5 numbers + 2 stars
 */
function displaySelectedGrid(nums, etoile1, etoile2) {
    var container = document.getElementById('selected-numbers');
    container.innerHTML = '';

    var sorted = nums.slice().sort(function(a, b) { return a - b; });
    sorted.forEach(function(n, index) {
        var ball = document.createElement('div');
        ball.className = 'selected-ball main';
        ball.textContent = n;
        ball.style.animationDelay = (index * 0.1) + 's';
        container.appendChild(ball);
    });

    var sep = document.createElement('div');
    sep.className = 'selected-ball separator';
    sep.textContent = '+';
    sep.style.animationDelay = '0.5s';
    container.appendChild(sep);

    var stars = [etoile1, etoile2].filter(Boolean).sort(function(a, b) { return a - b; });
    if (stars.length === 0) stars = Array.from(state.selectedStars).sort(function(a, b) { return a - b; });

    stars.forEach(function(s, index) {
        var starBall = document.createElement('div');
        starBall.className = 'selected-ball chance';
        starBall.textContent = s;
        starBall.style.animationDelay = (0.6 + index * 0.1) + 's';
        container.appendChild(starBall);
    });
}

/**
 * Display history check
 */
function displayHistoryCheck(historyCheck) {
    var historyDiv = document.getElementById('history-check');
    if (!historyDiv) return;
    if (!historyCheck || typeof historyCheck !== 'object') {
        historyDiv.style.display = 'none';
        return;
    }

    var text = '';

    if (historyCheck.exact_match === true && Array.isArray(historyCheck.exact_dates) && historyCheck.exact_dates.length > 0) {
        var count = historyCheck.exact_dates.length;
        text = LI.history_appeared.replace('{n}', count).replace(/\{s\}/g, count > 1 ? 's' : '');
    } else if (historyCheck.exact_match === false) {
        text = LI.history_never;
    }

    var matchCount = parseInt(historyCheck.best_match_count, 10);
    if (matchCount > 0 && historyCheck.best_match_date) {
        text += '<br>' + LI.history_best.replace('{n}', matchCount).replace(/\{s\}/g, matchCount > 1 ? 's' : '') + ' (' + historyCheck.best_match_date + ')';
    }

    if (text.trim()) {
        historyDiv.innerHTML = text;
        historyDiv.style.display = 'block';
    } else {
        historyDiv.style.display = 'none';
    }
}

// ================================================================
// PITCH HYBRIDE EM — Gemini async (simulateur)
// ================================================================

/**
 * Appelle /api/euromillions/pitch-grilles pour 1 grille et affiche le pitch
 * apres la section history-check du simulateur EM.
 * @param {Array} nums - 5 numeros selectionnes
 * @param {Array} etoiles - 2 etoiles selectionnees
 * @param {string|undefined} scoreConformite - score conformite (ex: "52%")
 * @param {number|undefined} severity - palier de severite (1, 2 ou 3)
 */
async function fetchAndDisplaySimulateurPitchEM(nums, etoiles, scoreConformite, severity) {
    var anchor = document.getElementById('history-check');
    if (!anchor) return;

    // Supprimer un pitch precedent
    var existing = anchor.parentElement.querySelector('.grille-pitch');
    if (existing) existing.remove();

    // Placeholder loading
    var pitchDiv = document.createElement('div');
    pitchDiv.className = 'grille-pitch grille-pitch-loading';
    pitchDiv.innerHTML = '<span class="pitch-icon">\u{1F916}</span> ' + LI.pitch_loading;
    anchor.insertAdjacentElement('afterend', pitchDiv);

    try {
        var response = await fetch('/api/euromillions/pitch-grilles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                grilles: [{
                    numeros: nums,
                    etoiles: etoiles,
                    score_conformite: scoreConformite ? parseInt(scoreConformite) : null,
                    severity: severity || null
                }],
                lang: window.LotoIA_lang
            })
        });
        var data = await response.json();

        if (data.success && data.data && data.data.pitchs && data.data.pitchs[0]) {
            pitchDiv.innerHTML = '<span class="pitch-icon">\u{1F916}</span> ' + data.data.pitchs[0];
            pitchDiv.classList.remove('grille-pitch-loading');
        } else {
            pitchDiv.remove();
        }
    } catch (e) {
        console.warn('[PITCH SIMULATEUR EM] Erreur:', e);
        pitchDiv.remove();
    }
}

/**
 * Reset selection
 */
function resetSelection() {
    state.selectedNumbers.clear();
    state.selectedStars.clear();
    state.popupShownForCurrentGrid = false;

    elements.mainGrid.querySelectorAll('.grid-number').forEach(function(btn) {
        btn.classList.remove('selected', 'disabled');
    });

    elements.starGrid.querySelectorAll('.chance-number').forEach(function(btn) {
        btn.classList.remove('selected', 'disabled');
    });

    elements.resultsSection.style.display = 'none';

    var historyDiv = document.getElementById('history-check');
    if (historyDiv) historyDiv.style.display = 'none';

    updateCountBadge();
}

/**
 * Auto-generate grid using API
 */
async function autoGenerate() {
    try {
        // Afficher le popup sponsor AVANT la generation (3 secondes fixe)
        if (typeof showSponsorPopupSimulateurEM === 'function') {
            var popupResult = await showSponsorPopupSimulateurEM({
                duration: 3,
                title: LI.generating_one,
                onComplete: function() {
                    console.log('[Simulateur EM] Popup sponsor termin\u00e9');
                }
            });

            if (popupResult && popupResult.cancelled === true) {
                console.log('[Simulateur EM] G\u00e9n\u00e9ration annul\u00e9e par l\'utilisateur');
                return;
            }
        }

        elements.loadingOverlay.style.display = 'flex';

        var response = await fetch('/api/euromillions/generate?n=1&lang=' + window.LotoIA_lang);
        var data = await response.json();

        if (data.success && data.grids && data.grids.length > 0) {
            var grid = data.grids[0];

            // Umami — grille generee EM
            if (typeof umami !== 'undefined') umami.track('simulateur-grille-generated', { module: 'euromillions' });

            resetSelection();

            grid.nums.forEach(function(n) {
                state.selectedNumbers.add(n);
                var btn = elements.mainGrid.querySelector('[data-number="' + n + '"]');
                if (btn) btn.classList.add('selected');
            });

            (grid.etoiles || []).forEach(function(s) {
                state.selectedStars.add(s);
                var btn = elements.starGrid.querySelector('[data-star="' + s + '"]');
                if (btn) btn.classList.add('selected');
            });

            updateMainGridState();
            updateStarGridState();
            updateCountBadge();

            // Popup deja affiche — lancer l'analyse directement (sans re-popup)
            state.popupShownForCurrentGrid = true;
            await analyzeGrid(false);
        }
    } catch (error) {
        console.error('Erreur auto-generate EM:', error);
    } finally {
        elements.loadingOverlay.style.display = 'none';
    }
}

/**
 * Bind events
 */
function bindEvents() {
    elements.btnReset.addEventListener('click', resetSelection);
    elements.btnAuto.addEventListener('click', autoGenerate);
}
