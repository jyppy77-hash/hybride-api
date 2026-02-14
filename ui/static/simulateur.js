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
    popupShownForCurrentGrid: false,  // Flag pour éviter popup multiple sur même grille
    statsLoaded: false,
    totalTirages: 0
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
 * Connecte au Cloud SQL via /api/numbers-heat
 */
async function loadNumbersHeat() {
    try {
        const response = await fetch('/api/numbers-heat');
        const data = await response.json();

        if (data.success) {
            state.numbersHeat = data.numbers;
            state.totalTirages = data.total_tirages || 0;
            state.statsLoaded = true;

            // Mettre a jour l'affichage du nombre de tirages
            updateTiragesDisplay();

            console.log(`[Simulateur] Stats chargees: ${state.totalTirages} tirages`);
            console.log(`[Simulateur] Seuils - Chaud: ${data.seuils?.chaud}, Froid: ${data.seuils?.froid}`);
        } else {
            console.warn('[Simulateur] API numbers-heat: success=false');
            generateFallbackHeat();
        }
    } catch (error) {
        console.error('[Simulateur] Erreur chargement heat:', error);
        // Fallback: generer des categories neutres
        generateFallbackHeat();
    }

    // Initialize grid after loading heat data
    initMainGrid();
}

/**
 * Fallback si l'API n'est pas disponible
 * Tous les numeros sont classes comme neutres
 */
function generateFallbackHeat() {
    console.warn('[Simulateur] Mode fallback - tous numeros neutres');
    for (let i = 1; i <= 49; i++) {
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
    // Mettre a jour la variable globale pour le popup
    window.TOTAL_TIRAGES = state.totalTirages;

    // Chercher un element pour afficher le total
    const tiragesElement = document.getElementById('stats-tirages');
    if (tiragesElement) {
        tiragesElement.textContent = `Base sur ${state.totalTirages.toLocaleString('fr-FR')} tirages officiels`;
    }

    // Mettre a jour les elements avec classe dynamic-tirages
    document.querySelectorAll('.dynamic-tirages').forEach(el => {
        el.textContent = state.totalTirages.toLocaleString('fr-FR');
    });
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
        { time: step * 0, text: "> Initialisation HYBRIDE...", type: "info" },
        { time: step * 1, text: "✓ Connexion moteur OK (89ms)", type: "success" },
        { time: step * 2, text: "> Analyse de votre grille personnelle...", type: "info" },
        { time: step * 3, text: "✓ 5 numéros + 1 chance validés", type: "success" },
        { time: step * 4, text: "> POST /api/analyze-custom-grid", type: "request" },
        { time: step * 5, text: "⏳ Calcul fréquences historiques... 22%", type: "progress" },
        { time: step * 6, text: `⏳ Comparaison avec ${(window.TOTAL_TIRAGES || 967).toLocaleString('fr-FR')} tirages... 45%`, type: "progress" },
        { time: step * 7, text: "⏳ Détection patterns similaires... 63%", type: "progress" },
        { time: step * 8, text: "⏳ Calcul profil statistique... 81%", type: "progress" },
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

    // Indicateur de convergence (descriptif, non évaluatif)
    displayConvergenceLevel(data.score);

    // Comparaison
    document.getElementById('comparaison-text').textContent = data.comparaison;

    // Badges
    displayBadges(data.badges);

    // Details
    displayDetails(data.details);

    // Suggestions (avec systeme de severite a 3 paliers)
    displaySuggestions(data.suggestions, data.severity, data.alert_message);

    // Selected grid display
    displaySelectedGrid(data.nums, data.chance);

    // History check display (safe - only if data exists)
    displayHistoryCheck(data.history_check);

    // Pitch HYBRIDE async (non-blocking) — transmet score conformite + severite
    fetchAndDisplaySimulateurPitch(
        Array.from(state.selectedNumbers),
        state.selectedChance,
        data.details?.score_conformite,
        data.severity
    );

    // Analytics GA4 — Track simulation de grille
    if (window.LotoIAAnalytics && window.LotoIAAnalytics.product) {
        window.LotoIAAnalytics.product.simulateGrid({ score: data.score });
    }

    // Scroll automatique vers la grille sélectionnée (center pour UX mobile/desktop)
    setTimeout(() => {
        const target = document.getElementById('selected-numbers')
                    || document.querySelector('.selected-grid')
                    || document.querySelector('.numbers-grid');
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });
        }
    }, 150);
}

/**
 * Affiche le niveau de convergence descriptif (non évaluatif, sans score numérique)
 */
function displayConvergenceLevel(score) {
    const levelEl = document.getElementById('convergence-level');
    const container = document.querySelector('.convergence-display');

    let label, levelClass;
    if (score >= 80) {
        label = 'Forte convergence';
        levelClass = 'convergence-elevated';
    } else if (score >= 60) {
        label = 'Convergence modérée';
        levelClass = 'convergence-moderate';
    } else if (score >= 40) {
        label = 'Convergence intermédiaire';
        levelClass = 'convergence-intermediate';
    } else {
        label = 'Convergence partielle';
        levelClass = 'convergence-partial';
    }

    // Appliquer la classe de niveau
    container.className = 'convergence-display ' + levelClass;

    // Animation de fondu pour le texte
    levelEl.style.opacity = '0';
    levelEl.style.transform = 'translateY(8px)';
    setTimeout(() => {
        levelEl.textContent = label;
        levelEl.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        levelEl.style.opacity = '1';
        levelEl.style.transform = 'translateY(0)';
    }, 150);
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
/**
 * Display suggestions with severity system (3 tiers)
 * @param {Array} suggestions - List of suggestion strings
 * @param {number} severity - Severity level (1=light, 2=moderate, 3=critical)
 * @param {string|null} alertMessage - Global alert message for tier 3
 */
function displaySuggestions(suggestions, severity, alertMessage) {
    const list = document.getElementById('suggestions-list');
    list.innerHTML = '';

    // Nettoyer une alerte precedente
    const oldAlert = list.parentElement.querySelector('.severity-alert');
    if (oldAlert) oldAlert.remove();

    // Alerte globale pour palier 3 (critique)
    if (severity === 3 && alertMessage) {
        const alertDiv = document.createElement('div');
        alertDiv.className = 'severity-alert severity-alert-critical';
        alertDiv.innerHTML = '<span class="severity-alert-icon">\u{1F6A8}</span> <strong>' + alertMessage + '</strong>';
        list.parentElement.insertBefore(alertDiv, list);
    }

    suggestions.forEach((suggestion, index) => {
        const li = document.createElement('li');
        li.textContent = suggestion;
        li.style.animationDelay = `${index * 0.1}s`;

        // Icone et classe selon le palier de severite
        if (severity === 3) {
            li.classList.add('critical');
            li.setAttribute('data-icon', '\u{1F534}');
        } else if (severity === 2) {
            li.classList.add('negative');
            li.setAttribute('data-icon', '\u26A0\uFE0F');
        } else if (suggestion.includes('Excellent') || suggestion.includes('bien')) {
            li.classList.add('positive');
            li.setAttribute('data-icon', '\u2705');
        } else if (suggestion.includes('Attention') || suggestion.includes('Elargir') || suggestion.includes('Mixer') || suggestion.includes('Pensez') || suggestion.includes('Somme')) {
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
 * Display selected grid with bounce animation
 */
function displaySelectedGrid(nums, chance) {
    const container = document.getElementById('selected-numbers');
    container.innerHTML = '';

    // Tri croissant visuel uniquement — données brutes côté moteur/API
    const sorted = [...nums].sort((a, b) => a - b);
    sorted.forEach((n, index) => {
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
 * Formate une date ISO (YYYY-MM-DD) en format français lisible
 * Ex: "2025-11-02" → "2 novembre 2025"
 */
function formatDateFR(isoDate) {
    if (!isoDate) return '';
    try {
        const d = new Date(isoDate);
        if (isNaN(d.getTime())) return isoDate;
        return d.toLocaleDateString('fr-FR', {
            day: 'numeric',
            month: 'long',
            year: 'numeric'
        });
    } catch (e) {
        return isoDate;
    }
}

/**
 * Affiche la vérification historique de la combinaison
 * SAFE: Ne s'affiche que si les données existent et sont valides
 * Utilise l'élément HTML statique #history-check
 */
function displayHistoryCheck(historyCheck) {
    const historyDiv = document.getElementById('history-check');

    // Si pas d'élément ou pas de données, masquer et sortir
    if (!historyDiv) return;
    if (!historyCheck || typeof historyCheck !== 'object') {
        historyDiv.style.display = 'none';
        return;
    }

    let text = '';

    // CAS 1: Combinaison exacte sortie
    if (historyCheck.exact_match === true && Array.isArray(historyCheck.exact_dates) && historyCheck.exact_dates.length > 0) {
        const count = historyCheck.exact_dates.length;
        const datesFormatted = historyCheck.exact_dates.map(formatDateFR).join(', ');
        text = `📜 Cette combinaison est déjà sortie <strong>${count} fois</strong> (${datesFormatted})`;
    } else if (historyCheck.exact_match === false) {
        // CAS 2: Combinaison jamais sortie
        text = `🔎 Cette combinaison n'est jamais apparue dans l'historique.`;
    }

    // CAS 3: Meilleure correspondance
    const matchCount = parseInt(historyCheck.best_match_count, 10);
    if (matchCount > 0 && historyCheck.best_match_date) {
        const chanceText = historyCheck.best_match_chance ? ' + chance' : '';
        const dateFormatted = formatDateFR(historyCheck.best_match_date);
        text += `<br>🧠 Meilleure correspondance : <strong>${matchCount} numéro${matchCount > 1 ? 's' : ''} identique${matchCount > 1 ? 's' : ''}${chanceText}</strong> (${dateFormatted})`;

        // Affichage visuel des boules communes
        if (Array.isArray(historyCheck.best_match_numbers) && historyCheck.best_match_numbers.length > 0) {
            let balls = historyCheck.best_match_numbers
                .map(n => `<span style="display:inline-flex;width:26px;height:26px;border-radius:50%;background:linear-gradient(135deg,#4da3ff,#2563eb);color:white;font-size:12px;font-weight:600;align-items:center;justify-content:center;margin:2px;box-shadow:0 2px 4px rgba(37,99,235,0.3);">${n}</span>`)
                .join('');
            // Ajouter le numero chance si matche
            if (historyCheck.best_match_chance && historyCheck.best_match_chance_number) {
                balls += `<span style="display:inline-flex;align-items:center;margin:0 4px;color:var(--theme-text-muted,#888);font-weight:500;">+</span>`;
                balls += `<span style="display:inline-flex;width:26px;height:26px;border-radius:50%;background:linear-gradient(135deg,#f59e0b,#d97706);color:white;font-size:12px;font-weight:600;align-items:center;justify-content:center;margin:2px;box-shadow:0 2px 4px rgba(245,158,11,0.3);">${historyCheck.best_match_chance_number}</span>`;
            }
            text += `<div style="margin-top:8px;">${balls}</div>`;
        }
    }

    // Afficher seulement si du contenu a été généré
    if (text.trim()) {
        historyDiv.innerHTML = text;
        historyDiv.style.display = 'block';
    } else {
        historyDiv.style.display = 'none';
    }
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

    // Hide history check
    const historyDiv = document.getElementById('history-check');
    if (historyDiv) historyDiv.style.display = 'none';

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

// ================================================================
// PITCH HYBRIDE — Gemini async (simulateur)
// ================================================================

/**
 * Appelle /api/pitch-grilles pour 1 grille et affiche le pitch
 * apres la section history-check du simulateur.
 * @param {Array} nums - 5 numeros selectionnes
 * @param {number} chance - numero chance
 * @param {string|undefined} scoreConformite - score conformite (ex: "52%")
 * @param {number|undefined} severity - palier de severite (1, 2 ou 3)
 */
async function fetchAndDisplaySimulateurPitch(nums, chance, scoreConformite, severity) {
    // Conteneur cible : apres history-check
    const anchor = document.getElementById('history-check');
    if (!anchor) return;

    // Supprimer un pitch precedent
    const existing = anchor.parentElement.querySelector('.grille-pitch');
    if (existing) existing.remove();

    // Placeholder loading
    const pitchDiv = document.createElement('div');
    pitchDiv.className = 'grille-pitch grille-pitch-loading';
    pitchDiv.innerHTML = '<span class="pitch-icon">\u{1F916}</span> HYBRIDE analyse ta grille\u2026';
    anchor.insertAdjacentElement('afterend', pitchDiv);

    try {
        const response = await fetch('/api/pitch-grilles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ grilles: [{ numeros: nums, chance: chance, score_conformite: scoreConformite ? parseInt(scoreConformite) : null, severity: severity || null }] })
        });
        const data = await response.json();

        if (data.success && data.data && data.data.pitchs && data.data.pitchs[0]) {
            pitchDiv.innerHTML = '<span class="pitch-icon">\u{1F916}</span> ' + data.data.pitchs[0];
            pitchDiv.classList.remove('grille-pitch-loading');
        } else {
            pitchDiv.remove();
        }
    } catch (e) {
        console.warn('[PITCH SIMULATEUR] Erreur:', e);
        pitchDiv.remove();
    }
}

/**
 * Bind events
 */
function bindEvents() {
    elements.btnReset.addEventListener('click', resetSelection);
    elements.btnAuto.addEventListener('click', autoGenerate);
}
