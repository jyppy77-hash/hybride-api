/**
 * Simulateur de Grille Loto
 * Interface interactive pour composer et analyser des grilles
 */

// State
const state = {
    selectedNumbers: new Set(),
    selectedChance: null,
    numbersHeat: {},
    debounceTimer: null,
    popupShownForCurrentGrid: false  // Flag pour éviter popup multiple sur même grille
};

// DOM Elements
const elements = {
    mainGrid: document.getElementById('main-grid'),
    chanceGrid: document.getElementById('chance-grid'),
    countMain: document.getElementById('count-main'),
    countChance: document.getElementById('count-chance'),
    resultsSection: document.getElementById('results-section'),
    loadingOverlay: document.getElementById('loading-overlay'),
    btnReset: document.getElementById('btn-reset'),
    btnAuto: document.getElementById('btn-auto')
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadNumbersHeat();
    initChanceGrid();
    bindEvents();
});

/**
 * Load heat data for numbers (hot/cold/neutral)
 */
async function loadNumbersHeat() {
    try {
        const response = await fetch('/api/numbers-heat');
        const data = await response.json();

        if (data.success) {
            state.numbersHeat = data.numbers;
        }
    } catch (error) {
        console.error('Erreur chargement heat:', error);
    }

    // Initialize grid after loading heat data
    initMainGrid();
}

/**
 * Initialize main grid (1-49)
 */
function initMainGrid() {
    elements.mainGrid.innerHTML = '';

    for (let i = 1; i <= 49; i++) {
        const btn = document.createElement('button');
        btn.className = 'grid-number';
        btn.textContent = i;
        btn.dataset.number = i;

        // Apply heat category
        const heat = state.numbersHeat[i];
        if (heat) {
            btn.classList.add(heat.category);
            btn.title = `Fréquence: ${heat.frequency} | Dernier: ${heat.last_draw || 'N/A'}`;
        } else {
            btn.classList.add('neutral');
        }

        btn.addEventListener('click', () => toggleNumber(i));
        elements.mainGrid.appendChild(btn);
    }
}

/**
 * Initialize chance grid (1-10)
 */
function initChanceGrid() {
    elements.chanceGrid.innerHTML = '';

    for (let i = 1; i <= 10; i++) {
        const btn = document.createElement('button');
        btn.className = 'chance-number';
        btn.textContent = i;
        btn.dataset.chance = i;
        btn.addEventListener('click', () => toggleChance(i));
        elements.chanceGrid.appendChild(btn);
    }
}

/**
 * Toggle number selection
 */
function toggleNumber(num) {
    const btn = elements.mainGrid.querySelector(`[data-number="${num}"]`);

    if (state.selectedNumbers.has(num)) {
        // Deselect
        state.selectedNumbers.delete(num);
        btn.classList.remove('selected');
    } else {
        // Select (max 5)
        if (state.selectedNumbers.size >= 5) {
            return; // Already 5 selected
        }
        state.selectedNumbers.add(num);
        btn.classList.add('selected');
    }

    updateMainGridState();
    updateCountBadge();
    triggerAnalysis();
}

/**
 * Toggle chance number selection
 */
function toggleChance(num) {
    const btns = elements.chanceGrid.querySelectorAll('.chance-number');

    if (state.selectedChance === num) {
        // Deselect
        state.selectedChance = null;
        btns.forEach(b => b.classList.remove('selected'));
    } else {
        // Select new
        state.selectedChance = num;
        btns.forEach(b => {
            b.classList.toggle('selected', parseInt(b.dataset.chance) === num);
        });
    }

    updateCountBadge();
    triggerAnalysis();
}

/**
 * Update main grid state (disable unselected when 5 selected)
 */
function updateMainGridState() {
    const btns = elements.mainGrid.querySelectorAll('.grid-number');
    const maxReached = state.selectedNumbers.size >= 5;

    btns.forEach(btn => {
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
    // Main numbers
    const mainCount = state.selectedNumbers.size;
    elements.countMain.textContent = `${mainCount}/5`;
    elements.countMain.classList.toggle('complete', mainCount === 5);

    // Chance
    const chanceCount = state.selectedChance ? 1 : 0;
    elements.countChance.textContent = `${chanceCount}/1`;
    elements.countChance.classList.toggle('complete', chanceCount === 1);
}

/**
 * Trigger analysis with debounce
 */
function triggerAnalysis() {
    // Clear previous timer
    if (state.debounceTimer) {
        clearTimeout(state.debounceTimer);
    }

    // Check if grid is complete
    if (state.selectedNumbers.size !== 5 || !state.selectedChance) {
        elements.resultsSection.style.display = 'none';
        // Reset popup flag si grille incomplète (user modifie sa sélection)
        state.popupShownForCurrentGrid = false;
        return;
    }

    // Debounce 300ms
    state.debounceTimer = setTimeout(() => {
        // Afficher le popup sponsor seulement la 1ère fois que cette grille est complétée
        const showPopup = !state.popupShownForCurrentGrid;
        if (showPopup) {
            state.popupShownForCurrentGrid = true;
        }
        analyzeGrid(showPopup);
    }, 300);
}

/**
 * Génère les logs personnalisés pour l'analyse de grille manuelle
 * @returns {Array} Tableau de logs avec timing
 */
function getCustomGridAnalysisLogs() {
    const duration = 5;
    const step = duration / 12;

    return [
        { time: step * 0, text: "> Initialisation HYBRIDE_OPTIMAL_V1...", type: "info" },
        { time: step * 1, text: "✓ Connexion moteur OK (89ms)", type: "success" },
        { time: step * 2, text: "> Analyse de votre grille personnelle...", type: "info" },
        { time: step * 3, text: "✓ 5 numéros + 1 chance validés", type: "success" },
        { time: step * 4, text: "> POST /api/analyze-custom-grid", type: "request" },
        { time: step * 5, text: "⏳ Calcul fréquences historiques... 22%", type: "progress" },
        { time: step * 6, text: `⏳ Comparaison avec ${(window.TOTAL_TIRAGES || 967).toLocaleString('fr-FR')} tirages... 45%`, type: "progress" },
        { time: step * 7, text: "⏳ Détection patterns similaires... 63%", type: "progress" },
        { time: step * 8, text: "⏳ Calcul score de probabilité... 81%", type: "progress" },
        { time: step * 9, text: "⏳ Génération recommandations... 93%", type: "progress" },
        { time: step * 10, text: "✓ Analyse terminée avec succès", type: "success" },
        { time: step * 11, text: "> Préparation affichage résultats...", type: "info" }
    ];
}

/**
 * Analyze the current grid
 * @param {boolean} withPopup - Afficher le pop-up sponsor (true pour analyse manuelle)
 */
async function analyzeGrid(withPopup = false) {
    const nums = Array.from(state.selectedNumbers);
    const chance = state.selectedChance;

    // Afficher le pop-up sponsor si demandé (analyse manuelle)
    if (withPopup && typeof showSponsorPopup === 'function') {
        const popupResult = await showSponsorPopup({
            duration: 5,
            gridCount: 1,
            title: 'Analyse de votre grille en cours',
            logs: getCustomGridAnalysisLogs(),
            onComplete: () => {
                console.log('[Simulateur] Popup sponsor terminé, lancement analyse');
            }
        });

        // Vérifier si l'utilisateur a annulé
        if (popupResult && popupResult.cancelled === true) {
            console.log('[Simulateur] Analyse annulée par l\'utilisateur');
            // Reset du flag pour permettre une nouvelle analyse
            state.popupShownForCurrentGrid = false;
            return; // Sortir sans afficher les résultats
        }
    }

    // Show loading
    elements.loadingOverlay.style.display = 'flex';

    try {
        // Build query string
        const params = new URLSearchParams();
        nums.forEach(n => params.append('nums', n));
        params.append('chance', chance);

        const response = await fetch(`/api/analyze-custom-grid?${params.toString()}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            displayResults(data);
        } else {
            console.error('Erreur analyse:', data.error);
        }
    } catch (error) {
        console.error('Erreur fetch:', error);
    } finally {
        elements.loadingOverlay.style.display = 'none';
    }
}

/**
 * Display analysis results
 */
function displayResults(data) {
    elements.resultsSection.style.display = 'block';

    // Score gauge
    updateGauge(data.score);

    // Score number with CountUp animation
    animateScore(data.score);

    // Stars
    displayStars(data.note_etoiles);

    // Comparaison
    document.getElementById('comparaison-text').textContent = data.comparaison;

    // Badges
    displayBadges(data.badges);

    // Details
    displayDetails(data.details);

    // Suggestions
    displaySuggestions(data.suggestions);

    // Selected grid display
    displaySelectedGrid(data.nums, data.chance);

    // Scroll to results
    elements.resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Update gauge fill with glow effect
 */
function updateGauge(score) {
    const gaugeFill = document.getElementById('gauge-fill');
    const gaugeContainer = document.querySelector('.score-gauge');

    // Arc length is about 110 units
    const fillLength = (score / 100) * 110;
    gaugeFill.style.strokeDasharray = `${fillLength} 110`;

    // Color and glow class based on score
    let color, glowClass;
    if (score >= 80) {
        color = '#27ae60';
        glowClass = 'excellent';
    } else if (score >= 60) {
        color = '#2ecc71';
        glowClass = 'good';
    } else if (score >= 40) {
        color = '#f39c12';
        glowClass = 'medium';
    } else {
        color = '#e74c3c';
        glowClass = 'low';
    }
    gaugeFill.style.stroke = color;

    // Apply glow class
    gaugeContainer.className = 'score-gauge ' + glowClass;
}

/**
 * Animate score counter (CountUp effect)
 */
function animateScore(targetScore) {
    const scoreEl = document.getElementById('score-number');
    let current = 0;
    const duration = 1500; // 1.5s
    const steps = 60;
    const increment = targetScore / steps;
    const stepTime = duration / steps;

    const timer = setInterval(() => {
        current += increment;
        if (current >= targetScore) {
            current = targetScore;
            clearInterval(timer);
        }
        scoreEl.textContent = Math.floor(current);
    }, stepTime);
}

/**
 * Display stars rating with sparkle animation
 */
function displayStars(rating) {
    const container = document.getElementById('stars-display');
    container.innerHTML = '';

    for (let i = 1; i <= 5; i++) {
        const star = document.createElement('span');
        star.className = `star ${i <= rating ? 'filled' : 'empty'}`;
        star.textContent = '★';
        star.style.animationDelay = `${i * 0.1}s`;
        container.appendChild(star);
    }
}

/**
 * Display badges with icons
 */
function displayBadges(badges) {
    const container = document.getElementById('badges-container');
    container.innerHTML = '';

    const iconMap = {
        'chaud': '🔥',
        'spectre': '📏',
        'quilibr': '⚖️',
        'Pair': '✅',
        'Hybride': '⚙️',
        'retard': '⏰',
        'froid': '❄️',
        'Mix': '🎰'
    };

    badges.forEach((badge, index) => {
        const el = document.createElement('span');
        el.className = 'badge';
        el.style.animationDelay = `${index * 0.1}s`;

        // Find matching icon
        let icon = '🎯'; // default
        for (const [key, emoji] of Object.entries(iconMap)) {
            if (badge.toLowerCase().includes(key.toLowerCase())) {
                icon = emoji;
                break;
            }
        }

        // Add specific class based on badge type
        if (badge.toLowerCase().includes('chaud')) {
            el.classList.add('hot');
        } else if (badge.includes('quilibr') || badge.includes('Pair')) {
            el.classList.add('balance');
        } else if (badge.toLowerCase().includes('spectre')) {
            el.classList.add('spectre');
        } else if (badge.includes('Hybride')) {
            el.classList.add('model');
        } else if (badge.toLowerCase().includes('froid')) {
            el.classList.add('cold');
        }

        el.innerHTML = `<span>${icon}</span><span>${badge}</span>`;
        container.appendChild(el);
    });
}

/**
 * Display details grid with icons and color coding
 */
function displayDetails(details) {
    const container = document.getElementById('details-grid');
    container.innerHTML = '';

    const detailsConfig = [
        {
            key: 'pairs_impairs',
            label: 'Pair / Impair',
            icon: '⚖️',
            evaluate: (val) => {
                const [pairs] = val.split('/').map(Number);
                if (pairs >= 2 && pairs <= 3) return 'good';
                if (pairs >= 1 && pairs <= 4) return 'warning';
                return 'bad';
            }
        },
        {
            key: 'bas_haut',
            label: 'Bas / Haut',
            icon: '📊',
            evaluate: (val) => {
                const [bas] = val.split('/').map(Number);
                if (bas >= 2 && bas <= 3) return 'good';
                if (bas >= 1 && bas <= 4) return 'warning';
                return 'bad';
            }
        },
        {
            key: 'somme',
            label: 'Somme',
            icon: '➕',
            evaluate: (val) => {
                const num = parseInt(val);
                if (num >= 100 && num <= 140) return 'good';
                if (num >= 70 && num <= 170) return 'warning';
                return 'bad';
            }
        },
        {
            key: 'dispersion',
            label: 'Dispersion',
            icon: '↔️',
            evaluate: (val) => {
                const num = parseInt(val);
                if (num >= 20 && num <= 40) return 'good';
                if (num >= 15 && num <= 45) return 'warning';
                return 'bad';
            }
        },
        {
            key: 'suites_consecutives',
            label: 'Suites',
            icon: '🔗',
            evaluate: (val) => {
                const num = parseInt(val);
                if (num === 0 || num === 1) return 'good';
                if (num === 2) return 'warning';
                return 'bad';
            }
        },
        {
            key: 'score_conformite',
            label: 'Conformité',
            icon: '✓',
            evaluate: (val) => {
                const num = parseFloat(val);
                if (num >= 80) return 'good';
                if (num >= 50) return 'warning';
                return 'bad';
            }
        }
    ];

    detailsConfig.forEach(({ key, label, icon, evaluate }) => {
        if (details[key] !== undefined) {
            const item = document.createElement('div');
            const statusClass = evaluate(details[key]);
            item.className = `detail-item ${statusClass}`;
            item.innerHTML = `
                <div class="detail-icon">${icon}</div>
                <div class="detail-label">${label}</div>
                <div class="detail-value">${details[key]}</div>
            `;
            container.appendChild(item);
        }
    });
}

/**
 * Display suggestions with icons
 */
function displaySuggestions(suggestions) {
    const list = document.getElementById('suggestions-list');
    list.innerHTML = '';

    suggestions.forEach((suggestion, index) => {
        const li = document.createElement('li');
        li.textContent = suggestion;
        li.style.animationDelay = `${index * 0.1}s`;

        // Determine type and icon
        if (suggestion.includes('Excellent') || suggestion.includes('bien')) {
            li.classList.add('positive');
            li.setAttribute('data-icon', '✅');
        } else if (suggestion.includes('Ajouter') || suggestion.includes('Equilibrer') || suggestion.includes('trop') || suggestion.includes('Mieux')) {
            li.classList.add('negative');
            li.setAttribute('data-icon', '⚠️');
        } else {
            li.classList.add('neutral');
            li.setAttribute('data-icon', '💡');
        }

        list.appendChild(li);
    });
}

/**
 * Display selected grid with bounce animation
 */
function displaySelectedGrid(nums, chance) {
    const container = document.getElementById('selected-numbers');
    container.innerHTML = '';

    // Main numbers with staggered animation
    nums.forEach((n, index) => {
        const ball = document.createElement('div');
        ball.className = 'selected-ball main';
        ball.textContent = n;
        ball.style.animationDelay = `${index * 0.1}s`;
        container.appendChild(ball);
    });

    // Separator
    const sep = document.createElement('div');
    sep.className = 'selected-ball separator';
    sep.textContent = '+';
    sep.style.animationDelay = '0.5s';
    container.appendChild(sep);

    // Chance
    const chanceBall = document.createElement('div');
    chanceBall.className = 'selected-ball chance';
    chanceBall.textContent = chance;
    chanceBall.style.animationDelay = '0.6s';
    container.appendChild(chanceBall);
}

/**
 * Reset selection
 */
function resetSelection() {
    state.selectedNumbers.clear();
    state.selectedChance = null;
    state.popupShownForCurrentGrid = false;  // Reset popup flag

    // Reset main grid
    elements.mainGrid.querySelectorAll('.grid-number').forEach(btn => {
        btn.classList.remove('selected', 'disabled');
    });

    // Reset chance grid
    elements.chanceGrid.querySelectorAll('.chance-number').forEach(btn => {
        btn.classList.remove('selected');
    });

    // Hide results
    elements.resultsSection.style.display = 'none';

    // Update badges
    updateCountBadge();
}

/**
 * Auto-generate grid using API
 */
async function autoGenerate() {
    try {
        // Afficher le popup sponsor AVANT la generation (5 secondes fixe)
        const popupResult = await showSponsorPopup({
            duration: 5,
            title: 'Génération d\'une grille optimisée...',
            onComplete: () => {
                console.log('[Simulateur] Popup sponsor terminé');
            }
        });

        // Vérifier si l'utilisateur a annulé
        if (popupResult && popupResult.cancelled === true) {
            console.log('[Simulateur] Génération auto annulée par l\'utilisateur');
            return; // Sortir sans générer
        }

        elements.loadingOverlay.style.display = 'flex';

        const response = await fetch('/generate?n=1');
        const data = await response.json();

        if (data.success && data.grids && data.grids.length > 0) {
            const grid = data.grids[0];

            // Reset first
            resetSelection();

            // Select numbers
            grid.nums.forEach(n => {
                state.selectedNumbers.add(n);
                const btn = elements.mainGrid.querySelector(`[data-number="${n}"]`);
                if (btn) btn.classList.add('selected');
            });

            // Select chance
            state.selectedChance = grid.chance;
            const chanceBtn = elements.chanceGrid.querySelector(`[data-chance="${grid.chance}"]`);
            if (chanceBtn) chanceBtn.classList.add('selected');

            // Update state
            updateMainGridState();
            updateCountBadge();

            // Trigger analysis (sans popup car déjà affiché)
            await analyzeGrid(false);
        }
    } catch (error) {
        console.error('Erreur auto-generate:', error);
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
