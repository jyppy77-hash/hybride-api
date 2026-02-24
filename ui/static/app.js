// ================================================================
// APP.JS - Loto Analysis UI Logic
// ================================================================

// State management
let currentResult = null;
let selectedGridCount = 3; // Par defaut 3 grilles

// DOM Elements
const drawDateInput = document.getElementById('draw-date');
const btnAnalyze = document.getElementById('btn-analyze');
const btnStats = document.getElementById('btn-stats');
const btnUpdate = document.getElementById('btn-update');
const btnCopy = document.getElementById('btn-copy');
const resultsSection = document.getElementById('results-section');
const successState = document.getElementById('success-state');
const errorState = document.getElementById('error-state');
const updateStatus = document.getElementById('update-status');
const dateError = document.getElementById('date-error');

// Install Elements
const dbStatus = document.getElementById('db-status');
const btnInstall = document.getElementById('btn-install');
const btnReset = document.getElementById('btn-reset');
const installStatus = document.getElementById('install-status');

// Debug Logs Elements
const logsPanel = document.getElementById('logs-panel');
const logsBody = document.getElementById('logs-body');
const btnToggleLogs = document.getElementById('btn-toggle-logs');
const btnClearLogs = document.getElementById('btn-clear-logs');
const btnCloseLogs = document.getElementById('btn-close-logs');

// ================================================================
// API FETCH UTILITIES (Cloud SQL)
// ================================================================

/**
 * Fonction generique pour appeler les endpoints API tirages
 * Gestion complete des erreurs avec format JSON standardise
 *
 * @param {string} endpoint - URL de l'endpoint (ex: '/api/tirages/count')
 * @returns {Promise<Object>} - Les donnees de la reponse (data)
 * @throws {Error} - En cas d'erreur HTTP ou API
 *
 * @example
 * // Obtenir le nombre de tirages
 * const data = await fetchTirages('/api/tirages/count');
 * console.log(data.total); // 971
 *
 * @example
 * // Obtenir le dernier tirage
 * const tirage = await fetchTirages('/api/tirages/latest');
 * console.log(tirage.date_de_tirage); // "2025-01-20"
 *
 * @example
 * // Obtenir une liste de tirages
 * const data = await fetchTirages('/api/tirages/list?limit=5');
 * console.log(data.items.length); // 5
 */
async function fetchTirages(endpoint) {
    try {
        const response = await fetch(endpoint);

        // Erreur HTTP (404, 500, etc.)
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        // Erreur API (success: false)
        if (!data.success) {
            throw new Error(data.error || 'Erreur API inconnue');
        }

        // Retourner uniquement les donnees utiles
        return data.data;

    } catch (error) {
        console.error(`Erreur fetchTirages(${endpoint}):`, error.message);
        throw error;
    }
}

/**
 * Affiche le nombre total de tirages dans la console
 * Exemple d'utilisation de fetchTirages()
 */
async function afficherNombreTirages() {
    try {
        const data = await fetchTirages('/api/tirages/count');
        console.log(`Total tirages en base: ${data.total}`);
        return data.total;
    } catch (error) {
        console.error('Impossible de charger le nombre de tirages:', error.message);
        return null;
    }
}

/**
 * Affiche le dernier tirage dans la console
 * Exemple d'utilisation de fetchTirages()
 */
async function afficherDernierTirage() {
    try {
        const tirage = await fetchTirages('/api/tirages/latest');
        console.log('Dernier tirage:', tirage);
        return tirage;
    } catch (error) {
        console.error('Impossible de charger le dernier tirage:', error.message);
        return null;
    }
}

// ================================================================
// INITIALIZATION
// ================================================================

function init() {
    // Configure date picker with next draw day
    configureDatePicker();

    // Event listeners
    drawDateInput.addEventListener('change', validateDateInput);
    btnAnalyze.addEventListener('click', handleAnalyze);
    btnStats.addEventListener('click', handleStats);
    btnUpdate.addEventListener('click', handleUpdate);
    btnCopy.addEventListener('click', handleCopy);

    // Grid count selector
    initGridCountSelector();

    // Install event listeners
    btnInstall.addEventListener('click', handleInstall);
    btnReset.addEventListener('click', handleReset);

    // Debug logs event listeners (si éléments présents)
    if (btnToggleLogs) btnToggleLogs.addEventListener('click', toggleLogs);
    if (btnClearLogs) btnClearLogs.addEventListener('click', clearLogs);
    if (btnCloseLogs) btnCloseLogs.addEventListener('click', closeLogs);

    // Generate session ID
    getSessionId();

    // Check database status on load
    checkDatabaseStatus();

    // Update stats hero display
    updateStatsDisplay();

    // Refresh stats every 5 minutes
    setInterval(updateStatsDisplay, 5 * 60 * 1000);
}

// ================================================================
// STATS HERO DISPLAY
// ================================================================

/**
 * Formate une date au format "nov. 2019"
 * @param {string} dateStr - Date au format "YYYY-MM-DD"
 * @returns {string} - Date formatée "MMM YYYY"
 */
function formatMonthYear(dateStr) {
    if (!dateStr) return '';

    const date = new Date(dateStr);
    const months = ['jan.', 'fév.', 'mars', 'avr.', 'mai', 'juin',
                    'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];

    const month = months[date.getMonth()];
    const year = date.getFullYear();

    return `${month} ${year}`;
}

/**
 * Met à jour l'affichage des statistiques hero en temps réel
 */
function updateStatsDisplay() {
    fetch('/database-info')
        .then(res => res.json())
        .then(data => {
            if (data.exists) {
                // Nombre de tirages - mise à jour de TOUS les éléments
                const totalDraws = data.total_draws || 967; // Fallback sur 967

                // Element stat-tirages (bandeau trust)
                const tiragesElement = document.getElementById('stat-tirages');
                if (tiragesElement) {
                    tiragesElement.textContent = `${totalDraws.toLocaleString('fr-FR')} tirages analysés`;
                }

                // Element stat-tirages-inline (texte du générateur)
                const tiragesInlineElement = document.getElementById('stat-tirages-inline');
                if (tiragesInlineElement) {
                    tiragesInlineElement.textContent = totalDraws.toLocaleString('fr-FR');
                }

                // Mettre à jour TOUS les éléments avec la classe dynamic-tirages
                const dynamicElements = document.querySelectorAll('.dynamic-tirages');
                dynamicElements.forEach(el => {
                    el.textContent = totalDraws.toLocaleString('fr-FR');
                });

                // Stocker globalement pour réutilisation (popup, simulateur, etc.)
                window.TOTAL_TIRAGES = totalDraws;

                // Dernière date de mise à jour
                const dateElement = document.getElementById('last-update-date');
                if (dateElement && data.last_draw) {
                    const date = new Date(data.last_draw);
                    dateElement.textContent = date.toLocaleDateString('fr-FR', {
                        day: 'numeric',
                        month: 'long',
                        year: 'numeric'
                    });
                }

                // Calcul du "Il y a X heures/jours"
                const timeElement = document.getElementById('last-update-time');
                if (timeElement && data.last_draw) {
                    const lastUpdate = new Date(data.last_draw);
                    const now = new Date();
                    const diffMs = now - lastUpdate;
                    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
                    const diffDays = Math.floor(diffHours / 24);

                    if (diffHours < 1) {
                        timeElement.textContent = 'Mis à jour récemment';
                    } else if (diffHours < 24) {
                        timeElement.textContent = `Il y a ${diffHours} heure${diffHours > 1 ? 's' : ''}`;
                    } else if (diffDays === 1) {
                        timeElement.textContent = 'Il y a 1 jour';
                    } else {
                        timeElement.textContent = `Il y a ${diffDays} jours`;
                    }
                }

                // Période historique
                const periodElement = document.getElementById('stat-period');
                if (periodElement && data.first_draw && data.last_draw) {
                    const firstDate = new Date(data.first_draw);
                    const lastDate = new Date(data.last_draw);
                    const firstMonth = firstDate.toLocaleDateString('fr-FR', { month: 'short' });
                    const firstYear = firstDate.getFullYear();
                    const lastMonth = lastDate.toLocaleDateString('fr-FR', { month: 'short' });
                    const lastYear = lastDate.getFullYear();
                    periodElement.textContent = `${firstMonth} ${firstYear} à ${lastMonth} ${lastYear}`;
                }

                // Mise à jour du sous-titre "depuis 2019" → "de nov. 2019 à jan. 2026"
                const dataDepthElement = document.querySelector('.data-depth');
                if (dataDepthElement && data.first_draw && data.last_draw) {
                    const firstFormatted = formatMonthYear(data.first_draw);
                    const lastFormatted = formatMonthYear(data.last_draw);
                    dataDepthElement.textContent = `de ${firstFormatted} à ${lastFormatted}`;
                }

                addLog('Stats hero mises à jour', 'success');
            }
        })
        .catch(err => {
            console.error('Erreur mise à jour stats hero:', err);
            addLog('Erreur mise à jour stats hero', 'error');
        });
}

/**
 * Configure le date picker avec le prochain jour de tirage
 */
async function configureDatePicker() {
    // Definir la date par defaut : prochain jour de tirage
    const nextDrawDate = getNextDrawDate();
    drawDateInput.value = nextDrawDate;

    // Definir la date min (aujourd'hui)
    const today = new Date();
    drawDateInput.min = today.toISOString().split('T')[0];

    // Definir la date max (3 mois dans le futur)
    const maxDate = new Date();
    maxDate.setMonth(maxDate.getMonth() + 3);
    drawDateInput.max = maxDate.toISOString().split('T')[0];

    // Valider la date initiale
    validateDateInput();

    // Mettre à jour le message "jours avant tirage"
    updateDaysUntilDraw();

    addLog(`Calendrier configure - Prochain tirage: ${nextDrawDate}`, 'info');
}

/**
 * Met à jour le message "Prochain tirage dans X jours"
 * Calcul précis basé sur la date sélectionnée
 */
function updateDaysUntilDraw() {
    const dateValue = drawDateInput.value;
    if (!dateValue) return;

    // Reset des heures pour un calcul précis
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const drawDate = new Date(dateValue + 'T00:00:00');
    drawDate.setHours(0, 0, 0, 0);

    // Calcul des jours
    const diffTime = drawDate - today;
    const daysUntil = Math.round(diffTime / (1000 * 60 * 60 * 24));

    // Éléments DOM
    const daysElement = document.getElementById('days-until-draw');
    const urgencyText = document.querySelector('.urgency-text');

    if (!urgencyText) return;

    // Message adapté selon le nombre de jours
    if (daysUntil === 0) {
        // Tirage aujourd'hui
        if (daysElement) daysElement.textContent = 'ce soir';
        urgencyText.innerHTML = '⏱️ <span class="urgency-icon"></span>Prochain tirage <strong>ce soir</strong> — préparez vos grilles';
    } else if (daysUntil === 1) {
        // Tirage demain
        if (daysElement) daysElement.textContent = 'demain';
        urgencyText.innerHTML = '⏱️ <span class="urgency-icon"></span>Prochain tirage <strong>demain</strong> — préparez vos grilles';
    } else if (daysUntil < 0) {
        // Date passée (ne devrait pas arriver)
        if (daysElement) daysElement.textContent = 'passé';
        urgencyText.innerHTML = '⏱️ <span class="urgency-icon"></span>Sélectionnez une date de tirage à venir';
    } else {
        // Dans X jours
        if (daysElement) daysElement.textContent = daysUntil;
        urgencyText.innerHTML = `⏱️ <span class="urgency-icon"></span>Prochain tirage dans <strong>${daysUntil}</strong> jours — préparez vos grilles`;
    }
}

/**
 * Trouve le prochain jour de tirage (lundi, mercredi ou samedi)
 */
function getNextDrawDate() {
    const today = new Date();
    const dayOfWeek = today.getDay(); // 0=Dimanche, 1=Lundi, ..., 6=Samedi

    let daysToAdd = 0;

    // Logique pour trouver le prochain jour de tirage
    switch (dayOfWeek) {
        case 0: daysToAdd = 1; break; // Dimanche -> Lundi
        case 1: daysToAdd = 0; break; // Lundi -> Lundi (aujourd'hui)
        case 2: daysToAdd = 1; break; // Mardi -> Mercredi
        case 3: daysToAdd = 0; break; // Mercredi -> Mercredi (aujourd'hui)
        case 4: daysToAdd = 2; break; // Jeudi -> Samedi
        case 5: daysToAdd = 1; break; // Vendredi -> Samedi
        case 6: daysToAdd = 0; break; // Samedi -> Samedi (aujourd'hui)
    }

    // Si c'est un jour de tirage mais apres l'heure du tirage (20h30), passer au suivant
    const now = new Date();
    if (daysToAdd === 0 && now.getHours() >= 21) {
        // Passer au prochain jour de tirage
        switch (dayOfWeek) {
            case 1: daysToAdd = 2; break; // Lundi soir -> Mercredi
            case 3: daysToAdd = 3; break; // Mercredi soir -> Samedi
            case 6: daysToAdd = 2; break; // Samedi soir -> Lundi
        }
    }

    const nextDate = new Date(today);
    nextDate.setDate(nextDate.getDate() + daysToAdd);

    return nextDate.toISOString().split('T')[0];
}

/**
 * Trouve le prochain jour de tirage valide a partir d'une date donnee
 */
function findNextDrawDate(fromDate) {
    const date = new Date(fromDate);
    const dayOfWeek = date.getDay();

    // Si deja un jour valide (1, 3, 6), retourner tel quel
    if (dayOfWeek === 1 || dayOfWeek === 3 || dayOfWeek === 6) {
        return fromDate.toISOString ? fromDate.toISOString().split('T')[0] : fromDate;
    }

    let daysToAdd = 0;
    switch (dayOfWeek) {
        case 0: daysToAdd = 1; break; // Dimanche -> Lundi
        case 2: daysToAdd = 1; break; // Mardi -> Mercredi
        case 4: daysToAdd = 2; break; // Jeudi -> Samedi
        case 5: daysToAdd = 1; break; // Vendredi -> Samedi
    }

    date.setDate(date.getDate() + daysToAdd);
    return date.toISOString().split('T')[0];
}

/**
 * Initialise le selecteur de nombre de grilles
 */
function initGridCountSelector() {
    const selector = document.getElementById('grid-count-selector');
    if (!selector) return;

    const buttons = selector.querySelectorAll('.count-btn');

    buttons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();

            // Retirer la classe active de tous les boutons
            buttons.forEach(b => b.classList.remove('active'));

            // Ajouter la classe active au bouton clique
            btn.classList.add('active');

            // Mettre a jour le nombre de grilles selectionne
            selectedGridCount = parseInt(btn.dataset.count);

            addLog(`Nombre de grilles: ${selectedGridCount}`, 'info');
        });
    });
}

/**
 * Genere un UUID v4
 */
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

/**
 * Recupere ou cree l'ID de session
 */
function getSessionId() {
    let sessionId = sessionStorage.getItem('lotoia_session');
    if (!sessionId) {
        sessionId = generateUUID();
        sessionStorage.setItem('lotoia_session', sessionId);
    }
    return sessionId;
}


// ================================================================
// DATE VALIDATION - Autoriser uniquement les jours de tirage officiels
// ================================================================

/**
 * Vérifie si une date correspond à un jour de tirage officiel du Loto
 * Jours de tirage VALIDES : Lundi (1), Mercredi (3), Samedi (6)
 *
 * @param {Date} date - Date à vérifier
 * @returns {boolean} - true si jour de tirage valide, false sinon
 */
function isDrawDay(date) {
    const day = date.getDay(); // 0=Dimanche, 1=Lundi, ..., 6=Samedi
    return day === 1 || day === 3 || day === 6;
}

/**
 * Valide la date sélectionnée et affiche un message si jour invalide
 * Propose automatiquement le prochain jour de tirage valide
 */
function validateDateInput() {
    const dateValue = drawDateInput.value;

    if (!dateValue) {
        hideDateError();
        disableActionButtons(false);
        return;
    }

    const selectedDate = new Date(dateValue + 'T00:00:00'); // Force local timezone

    if (!isDrawDay(selectedDate)) {
        // Trouver le prochain jour de tirage valide
        const nextValidDate = findNextDrawDate(selectedDate);
        const nextDateFormatted = new Date(nextValidDate + 'T00:00:00').toLocaleDateString('fr-FR', {
            weekday: 'long',
            day: 'numeric',
            month: 'long'
        });

        showDateError(`Pas de tirage ce jour. Prochain tirage : ${nextDateFormatted}`);
        addLog(`Date invalide : ${dateValue} - Suggestion: ${nextValidDate}`, 'warning');

        // Proposer de corriger automatiquement apres 2 secondes
        setTimeout(() => {
            if (drawDateInput.value === dateValue) {
                drawDateInput.value = nextValidDate;
                hideDateError();
                disableActionButtons(false);
                updateDaysUntilDraw(); // Mettre à jour après correction
                addLog(`Date corrigee automatiquement: ${nextValidDate}`, 'info');
            }
        }, 1500);

        disableActionButtons(true);
    } else {
        hideDateError();
        addLog(`Date valide : ${dateValue} (jour de tirage)`, 'success');
        disableActionButtons(false);
        updateDaysUntilDraw(); // Mettre à jour le message "jours avant tirage"
    }
}

/**
 * Affiche le message d'erreur de date
 */
function showDateError(message) {
    dateError.textContent = message;
    dateError.style.display = 'block';
    drawDateInput.style.borderColor = '#d32f2f';
}

/**
 * Masque le message d'erreur de date
 */
function hideDateError() {
    dateError.style.display = 'none';
    drawDateInput.style.borderColor = '';
}

/**
 * Desactive ou reactive les boutons d'action selon la validite de la date
 */
function disableActionButtons(disable) {
    btnAnalyze.disabled = disable;

    // Ajout d'une classe visuelle pour indiquer l'etat desactive
    if (disable) {
        btnAnalyze.style.opacity = '0.5';
        btnAnalyze.style.cursor = 'not-allowed';
    } else {
        btnAnalyze.style.opacity = '1';
        btnAnalyze.style.cursor = 'pointer';
    }
}

// ================================================================
// API CALLS
// ================================================================

async function handleAnalyze() {
    const date = drawDateInput.value;
    if (!date) {
        showError('Veuillez sélectionner une date de tirage.');
        return;
    }

    // Validate draw day
    const selectedDate = new Date(date + 'T00:00:00');
    if (!isDrawDay(selectedDate)) {
        showError('Impossible d\'analyser cette date. Le Loto est uniquement tiré les lundis, mercredis et samedis.');
        addLog(`Analyse bloquée : ${date} (pas un jour de tirage)`, 'error');
        return;
    }

    setLoading(btnAnalyze, true);
    hideResults();

    addLog('Clic sur "Générer les grilles"', 'info');
    addLog(`Date sélectionnée : ${date}`, 'success');

    // Calculer la durée du popup selon le nombre de grilles
    const popupDuration = calculateTimerDuration(selectedGridCount);
    const plural = selectedGridCount > 1 ? 's' : '';

    addLog(`Affichage popup sponsor (${popupDuration}s) avant génération`, 'info');

    // Afficher le popup sponsor AVANT l'appel API
const popupResult = await showSponsorPopup({
    duration: popupDuration,
    gridCount: selectedGridCount,
    onComplete: () => {
        addLog('Popup sponsor terminé, lancement de la génération', 'success');
    }
});

if (popupResult && popupResult.cancelled === true) {
    addLog('Génération annulée par l’utilisateur', 'warning');
    setLoading(btnAnalyze, false);
    addLog('Requête terminée', 'info');
    return;
}

addLog(`Envoi requête GET /generate?n=${selectedGridCount}&mode=balanced`, 'request');
    try {
        // Appel a /generate avec le nombre de grilles selectionne
        const response = await fetch(`/generate?n=${selectedGridCount}&mode=balanced`);

        addLog(`Réponse reçue : ${response.status} ${response.statusText}`, 'response');

        if (!response.ok) {
            throw new Error(`Erreur HTTP ${response.status}`);
        }

        const data = await response.json();

        if (data.success && data.grids) {
            currentResult = data;
            // Affichage visuel des grilles avec cards partenaire
            displayGridsWithAds(data.grids, data.metadata, date);
            addLog(`${data.grids.length} grille(s) générée(s) et affichée(s)`, 'success');

            // Pitch HYBRIDE async (non-blocking)
            fetchAndDisplayPitchs(data.grids);

            // Analytics GA4 - Track generation de grilles
            if (window.LotoIAAnalytics && window.LotoIAAnalytics.product) {
                window.LotoIAAnalytics.product.generateGrid({
                    count: data.grids.length,
                    mode: data.metadata?.mode || 'balanced',
                    targetDate: date
                });
            }
        } else {
            const errorMsg = data.message || 'Erreur lors de la génération des grilles.';
            addLog(`Erreur API : ${errorMsg}`, 'error');
            showError(errorMsg);
        }
    } catch (error) {
        const errorMsg = `Impossible de générer les grilles. ${error.message}`;
        addLog(`Erreur : ${error.message}`, 'error');
        console.error('Erreur complète:', error);
        showError(errorMsg);
    } finally {
        setLoading(btnAnalyze, false);
        addLog('Requête terminée', 'info');
    }
}

async function handleStats() {
    setLoading(btnStats, true);
    hideResults();

    try {
        const response = await fetch('/stats');
        const data = await response.json();

        if (data.success) {
            currentResult = data;
            displayStatsResult(data);
        } else {
            showError(data.message || 'Erreur lors de la récupération des stats.');
        }
    } catch (error) {
        showError('Impossible de se connecter au serveur.');
    } finally {
        setLoading(btnStats, false);
    }
}

async function handleUpdate() {
    addLog('→ Clic sur "Mettre à jour les données officielles"', 'info');

    setLoading(btnUpdate, true);
    hideUpdateStatus();

    addLog('→ Envoi requête POST /update-data', 'request');

    try {
        const response = await fetch('/update-data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        addLog(`← Réponse reçue : ${response.status} ${response.statusText}`, 'response');

        const data = await response.json();

        if (data.status === 'success') {
            // Format date for display
            const updateDate = new Date(data.updated_at).toLocaleDateString('fr-FR');

            // Build human message
            let message = data.message;
            if (data.new_rows === 0) {
                message = `Base de données à jour (${data.total_rows} tirages). Aucun nouveau tirage disponible.`;
                addLog(`✓ Aucun nouveau tirage (total: ${data.total_rows})`, 'success');
            } else if (data.new_rows === 1) {
                message = `1 nouveau tirage ajouté. Total : ${data.total_rows} tirages.`;
                addLog(`✓ 1 nouveau tirage ajouté (total: ${data.total_rows})`, 'success');
            } else {
                message = `${data.new_rows} nouveaux tirages ajoutés. Total : ${data.total_rows} tirages.`;
                addLog(`✓ ${data.new_rows} nouveaux tirages ajoutés (total: ${data.total_rows})`, 'success');
            }

            showUpdateStatus(message, 'success');
        } else {
            // Error from backend
            const errorMsg = data.message || 'Impossible de mettre à jour les données pour le moment.';
            addLog(`✗ Erreur : ${errorMsg}`, 'error');
            showUpdateStatus(errorMsg, 'error');
        }
    } catch (error) {
        const errorMsg = 'Impossible de se connecter au serveur. Vérifiez votre connexion.';
        addLog(`✗ Erreur de connexion : ${error.message}`, 'error');
        showUpdateStatus(errorMsg, 'error');
    } finally {
        setLoading(btnUpdate, false);
        addLog('→ Requête terminée', 'info');
    }
}

async function checkDatabaseStatus() {
    addLog('→ Vérification du statut de la base de données', 'info');

    try {
        const response = await fetch('/database-info');
        const data = await response.json();

        addLog(`← Statut BDD reçu : exists=${data.exists}`, 'response');
        console.log('[DEBUG] /database-info response:', data);

        const statusIcon = dbStatus.querySelector('.status-icon');
        const mainStatus = document.getElementById('db-main-status');
        const period = document.getElementById('db-period');
        const algoNote = document.getElementById('db-algo-note');
        const fallbackStatusText = dbStatus.querySelector('.status-text');

        // Helpers (fallback compatible ancien HTML si besoin)
        const setMainText = (text) => {
            if (mainStatus) {
                mainStatus.textContent = text;
                return;
            }
            if (fallbackStatusText) {
                fallbackStatusText.textContent = text;
            }
        };

        const hideExtras = () => {
            if (period) period.style.display = 'none';
            if (algoNote) algoNote.style.display = 'none';
        };

        if (data.status === 'success' && data.exists) {
            // Database exists
            dbStatus.classList.remove('not-exists');
            dbStatus.classList.add('exists');

            // Vérifier si la base est prête (contient des données)
            if (data.is_ready === true) {
                // Base prête avec snapshot FDJ chargé
                statusIcon.textContent = '✅';
                setMainText(`Base prête — Snapshot FDJ chargé (${data.total_rows} tirages)`);

                // Afficher la période couverte si disponible
                hideExtras();
                if (data.date_min && data.date_max && period && algoNote) {
                    period.textContent = `Période couverte : du ${formatDate(data.date_min)} au ${formatDate(data.date_max)}`;
                    period.style.display = 'block';

                    algoNote.textContent = 'Les modèles statistiques sont calibrés spécifiquement pour cet historique de tirages.';
                    algoNote.style.display = 'block';
                }

                // Masquer les deux boutons (install ET reset)
                btnInstall.style.display = 'none';
                btnReset.style.display = 'none';

                // Désactiver le bouton Update avec tooltip
                btnUpdate.disabled = true;
                btnUpdate.style.opacity = '0.5';
                btnUpdate.style.cursor = 'not-allowed';
                btnUpdate.title = 'Update FDJ indisponible (source officielle absente)';

                addLog(`✓ Base de données prête (${data.total_rows} tirages, ${data.file_size_mb} MB)`, 'success');
            } else {
                // Base existe mais est vide
                statusIcon.textContent = '⚠️';
                setMainText('Base installée mais vide (0 tirage)');
                hideExtras();

                // Masquer install, afficher reset
                btnInstall.style.display = 'none';
                btnReset.style.display = 'inline-flex';

                // Réactiver le bouton Update
                btnUpdate.disabled = false;
                btnUpdate.style.opacity = '1';
                btnUpdate.style.cursor = 'pointer';
                btnUpdate.title = 'Mettre à jour les données';

                addLog('⚠️ Base de données vide', 'warning');
            }
        } else {
            // Database does not exist
            statusIcon.textContent = '⚠️';
            setMainText('Base de données non installée');
            hideExtras();

            dbStatus.classList.remove('exists');
            dbStatus.classList.add('not-exists');

            // Show install button, hide reset button
            btnInstall.style.display = 'inline-flex';
            btnReset.style.display = 'none';

            // Réactiver le bouton Update
            btnUpdate.disabled = false;
            btnUpdate.style.opacity = '1';
            btnUpdate.style.cursor = 'pointer';
            btnUpdate.title = 'Mettre à jour les données';

            addLog('⚠️ Base de données non trouvée', 'warning');
        }
    } catch (error) {
        addLog(`✗ Erreur vérification BDD : ${error.message}`, 'error');

        const statusIcon = dbStatus.querySelector('.status-icon');
        const mainStatus = document.getElementById('db-main-status');
        const period = document.getElementById('db-period');
        const algoNote = document.getElementById('db-algo-note');
        const fallbackStatusText = dbStatus.querySelector('.status-text');

        statusIcon.textContent = '✗';

        if (mainStatus) {
            mainStatus.textContent = 'Erreur lors de la vérification';
        } else if (fallbackStatusText) {
            fallbackStatusText.textContent = 'Erreur lors de la vérification';
        }

        if (period) period.style.display = 'none';
        if (algoNote) algoNote.style.display = 'none';

        dbStatus.classList.remove('exists', 'not-exists');
    }
}

async function handleInstall() {
    addLog('→ Clic sur "Installer la base de données"', 'info');

    setLoading(btnInstall, true);
    hideInstallStatus();

    addLog('→ Envoi requête POST /install-database', 'request');

    try {
        const response = await fetch('/install-database', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        addLog(`← Réponse reçue : ${response.status} ${response.statusText}`, 'response');

        const data = await response.json();

        if (data.status === 'success') {
            // Installation successful
            const message = data.message || 'Base de données installée avec succès.';
            addLog(`✓ Installation réussie : ${data.tables_created.join(', ')}`, 'success');
            showInstallStatus(message, 'success');

            // Refresh database status
            setTimeout(() => {
                checkDatabaseStatus();
            }, 500);
        } else if (data.status === 'exists') {
            // Database already exists
            const message = data.message || 'Base de données déjà installée.';
            addLog(`ℹ Base déjà installée`, 'info');
            showInstallStatus(message, 'info');

            // Refresh database status
            setTimeout(() => {
                checkDatabaseStatus();
            }, 500);
        } else {
            // Error from backend
            const errorMsg = data.message || 'Erreur lors de l\'installation de la base de données.';
            addLog(`✗ Erreur : ${errorMsg}`, 'error');
            showInstallStatus(errorMsg, 'error');
        }
    } catch (error) {
        const errorMsg = 'Impossible de se connecter au serveur. Vérifiez votre connexion.';
        addLog(`✗ Erreur de connexion : ${error.message}`, 'error');
        showInstallStatus(errorMsg, 'error');
    } finally {
        setLoading(btnInstall, false);
        addLog('→ Requête terminée', 'info');
    }
}

async function handleReset() {
    addLog('→ Clic sur "Réinitialiser la base"', 'warning');

    // Confirmation dialog
    const confirmed = confirm(
        '⚠️ ATTENTION ⚠️\n\n' +
        'Vous allez SUPPRIMER toutes les données actuelles et réinitialiser la base de données.\n\n' +
        'Cette action est IRRÉVERSIBLE.\n\n' +
        'Voulez-vous vraiment continuer ?'
    );

    if (!confirmed) {
        addLog('→ Réinitialisation annulée par l\'utilisateur', 'info');
        return;
    }

    addLog('⚠️ Confirmation reçue - Réinitialisation en cours', 'warning');

    setLoading(btnReset, true);
    hideInstallStatus();

    addLog('→ Envoi requête POST /install-database?force=true', 'request');

    try {
        const response = await fetch('/install-database?force=true', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        addLog(`← Réponse reçue : ${response.status} ${response.statusText}`, 'response');

        const data = await response.json();

        if (data.status === 'success') {
            // Reset successful
            const message = data.message || 'Base de données réinitialisée avec succès.';
            addLog(`✓ Réinitialisation réussie`, 'success');
            showInstallStatus(message, 'success');

            // Refresh database status
            setTimeout(() => {
                checkDatabaseStatus();
            }, 500);
        } else {
            // Error from backend
            const errorMsg = data.message || 'Erreur lors de la réinitialisation de la base de données.';
            addLog(`✗ Erreur : ${errorMsg}`, 'error');
            showInstallStatus(errorMsg, 'error');
        }
    } catch (error) {
        const errorMsg = 'Impossible de se connecter au serveur. Vérifiez votre connexion.';
        addLog(`✗ Erreur de connexion : ${error.message}`, 'error');
        showInstallStatus(errorMsg, 'error');
    } finally {
        setLoading(btnReset, false);
        addLog('→ Requête terminée', 'info');
    }
}

// ================================================================
// DISPLAY RESULTS
// ================================================================

function displayAnalysisResult(data) {
    const { analysis, target_date } = data;

    // Parse analysis text to extract numbers and info
    const lines = analysis.split('\n');

    // Extract grids (looking for "Numeros : XX - XX - XX - XX - XX")
    const gridMatches = analysis.match(/Numeros : ([\d\s-]+)/g);
    const grids = [];

    if (gridMatches) {
        gridMatches.forEach(match => {
            const numbers = match.replace('Numeros : ', '').split(' - ').map(n => parseInt(n.trim()));
            grids.push(numbers);
        });
    }

    // Extract chance numbers
    const chanceMatch = analysis.match(/Chance\s+:\s+(\d+)/);
    const chanceNumber = chanceMatch ? parseInt(chanceMatch[1]) : null;

    // Display first grid with chance
    if (grids.length > 0) {
        displayNumbers(grids[0], chanceNumber);
    }

    // Key info
    const keyInfo = [
        `Analyse pour le tirage du ${target_date}`,
        `${grids.length} grille(s) recommandée(s)`,
        'Basé sur les statistiques historiques'
    ];
    displayKeyInfo(keyInfo);

    // Détails supprimés pour simplifier l'UX

    // Show results
    document.getElementById('result-title').textContent = 'Analyse du tirage';
    showSuccess();
}

function displayGenerateResult(data) {
    const { grids, metadata } = data;

    if (grids && grids.length > 0) {
        const firstGrid = grids[0];
        displayNumbers(firstGrid.nums, firstGrid.chance);

        const keyInfo = [
            `${grids.length} grille(s) générée(s)`,
            `Mode : ${metadata.mode}`,
            `Fenêtre : ${metadata.fenetre_principale_annees} ans (${metadata.ponderation})`
        ];

        if (firstGrid.badges && firstGrid.badges.length > 0) {
            firstGrid.badges.forEach(badge => {
                // Nettoyage du vocabulaire
                const cleaned = badge
                    .replace(/Numéros chauds/gi, 'Fréquences élevées observées')
                    .replace(/Retard/gi, 'Écart observé');
                keyInfo.push(`• ${cleaned}`);
            });
        }

        // Add metadata info
        keyInfo.push(`Tirages analysés : ${metadata.nb_tirages_total}`);

        displayKeyInfo(keyInfo);
        displayExplanations(firstGrid);

        document.getElementById('result-title').textContent = 'Grilles générées';
        showSuccess();
    } else {
        showError('Aucune grille générée. Vérifiez que la base de données contient des tirages.');
    }
}

function formatDateFR(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    const options = { day: 'numeric', month: 'long', year: 'numeric' };
    return date.toLocaleDateString('fr-FR', options);
}

function formatPeriod(startDate, endDate) {
    if (!startDate || !endDate) return { years: 0, period: 'N/A' };

    const start = new Date(startDate);
    const end = new Date(endDate);
    const startMonth = start.toLocaleDateString('fr-FR', { month: 'short', year: 'numeric' });
    const endMonth = end.toLocaleDateString('fr-FR', { month: 'short', year: 'numeric' });

    // Calculer durée en années
    const years = Math.floor((end - start) / (365.25 * 24 * 60 * 60 * 1000));

    return {
        years: years,
        period: `De ${startMonth} à ${endMonth}`
    };
}

function displayStatsResult(data) {
    const { stats } = data;

    // Masquer la grille de numéros
    document.getElementById('numbers-grid').innerHTML = '';

    // Formater les données
    const lastUpdateFormatted = formatDateFR(stats.last_draw_date || stats.last_update);
    const periodInfo = formatPeriod(stats.first_draw_date, stats.last_draw_date);

    // Créer les cards visuelles
    const statsHTML = `
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon">🎲</div>
                <div class="stat-value">${stats.total_draws.toLocaleString('fr-FR')}</div>
                <div class="stat-label">Tirages analysés</div>
            </div>

            <div class="stat-card">
                <div class="stat-icon">📅</div>
                <div class="stat-value">${lastUpdateFormatted}</div>
                <div class="stat-label">Dernière mise à jour</div>
            </div>

            <div class="stat-card">
                <div class="stat-icon">📊</div>
                <div class="stat-value">${periodInfo.years} ans</div>
                <div class="stat-label">Historique</div>
                <div class="stat-sublabel">${periodInfo.period}</div>
            </div>
        </div>
    `;

    // Afficher dans key-info
    const keyInfoEl = document.getElementById('key-info');
    keyInfoEl.innerHTML = statsHTML;
    keyInfoEl.style.background = 'transparent';
    keyInfoEl.style.borderLeft = 'none';
    keyInfoEl.style.padding = '0';

    document.getElementById('result-title').textContent = 'Statistiques';
    showSuccess();
}

// ================================================================
// TRACKING FUNCTIONS
// ================================================================

/**
 * Tracking generation grille individuelle
 */
function trackGridGeneration(grid, gridNumber, targetDate) {
    if (!(window.LotoIAAnalytics && window.LotoIAAnalytics.utils && window.LotoIAAnalytics.utils.hasConsent())) return;
    fetch('/api/track-grid', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            grid_id: generateUUID(),
            grid_number: gridNumber || 0,
            grid_data: {
                nums: grid.nums || [],
                chance: grid.chance || 0,
                score: grid.score || 0
            },
            target_date: targetDate || 'unknown',
            timestamp: Math.floor(Date.now() / 1000),
            session_id: getSessionId() || 'anonymous'
        })
    }).catch(err => console.error('Tracking error:', err));
}

/**
 * Tracking impression pub
 */
function trackAdImpression(adId) {
    if (!(window.LotoIAAnalytics && window.LotoIAAnalytics.utils && window.LotoIAAnalytics.utils.hasConsent())) return;
    fetch('/api/track-ad-impression', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            ad_id: adId || 'unknown',
            timestamp: Math.floor(Date.now() / 1000),
            session_id: getSessionId() || 'anonymous'
        })
    }).catch(err => console.error('Ad tracking error:', err));
}

/**
 * Tracking clic pub (pour CPA)
 */
function trackAdClick(adId, partnerId) {
    if (!(window.LotoIAAnalytics && window.LotoIAAnalytics.utils && window.LotoIAAnalytics.utils.hasConsent())) return;
    fetch('/api/track-ad-click', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            ad_id: adId || 'unknown',
            partner_id: partnerId || 'unknown',
            timestamp: Math.floor(Date.now() / 1000),
            session_id: getSessionId() || 'anonymous'
        })
    }).then(() => {
        // Rediriger vers partenaire avec UTM
        // Pour l'instant, juste un placeholder
        console.log('Ad click tracked:', adId);
    }).catch(err => console.error('Click tracking error:', err));
}

/**
 * Cree une card partenaire elegante
 */
function createPartnerCard(index) {
    const adId = `ad_${Date.now()}_${index}`;
    const partnerId = 'partner_demo';

    const html = `
        <div class="partner-card" data-ad-id="${adId}" data-partner-id="${partnerId}">
            <div class="partner-content">
                <div class="partner-badge">Partenaire</div>
                <div class="partner-body">
                    <p class="partner-text">LotoIA.fr est propulsé par nos partenaires</p>
                    <a href="#" class="partner-cta" onclick="trackAdClick('${adId}', '${partnerId}'); return false;">
                        En savoir plus
                    </a>
                </div>
            </div>
        </div>
    `;

    // Track impression
    trackAdImpression(adId);

    return html;
}

/**
 * Affiche les grilles générées avec cards partenaire intercalées
 * @param {Array} grids - Tableau des grilles générées
 * @param {Object} metadata - Métadonnées de génération
 * @param {string} targetDate - Date cible du tirage (format YYYY-MM-DD)
 */
function displayGridsWithAds(grids, metadata, targetDate) {
    // Formater la date pour l'affichage
    const dateObj = new Date(targetDate + 'T00:00:00');
    const dateFormatted = dateObj.toLocaleDateString('fr-FR', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric'
    });

    // Header des résultats
    let html = `
        <div class="results-header">
            <h2>Grilles Recommandées Pour Le ${dateFormatted}</h2>
            <div class="results-meta">
                <span>Mode : ${translateMode(metadata.mode || 'balanced')}</span>
                <span>${grids.length} grille(s) générée(s)</span>
                <span>${new Date().toLocaleTimeString('fr-FR')}</span>
            </div>
        </div>
    `;

    // Grilles + pubs intercalées
    grids.forEach((grid, index) => {
        // Profil descriptif basé sur les badges (indicateurs réels)
        const badges = grid.badges || [];
        let convergenceLabel, convergenceClass;
        if (badges.some(b => b.toLowerCase().includes('chaud'))) {
            convergenceLabel = 'Profil chaud';
            convergenceClass = 'convergence-elevated';
        } else if (badges.some(b => b.toLowerCase().includes('retard') || b.toLowerCase().includes('cart'))) {
            convergenceLabel = 'Profil mixte';
            convergenceClass = 'convergence-moderate';
        } else {
            convergenceLabel = 'Profil équilibré';
            convergenceClass = 'convergence-elevated';
        }

        html += `
            <div class="grid-visual-card" style="animation-delay: ${index * 0.15}s">
                <div class="grid-visual-header">
                    <div class="grid-number">
                        <span class="grid-number-label">Grille</span>
                        <span class="grid-number-value">#${index + 1}</span>
                    </div>
                    <div class="grid-convergence-indicator ${convergenceClass}">
                        <span class="convergence-label">Profil</span>
                        <span class="convergence-value">${convergenceLabel}</span>
                    </div>
                </div>

                <div class="grid-visual-numbers">
                    ${[...grid.nums].sort((a, b) => a - b).map(n => `
                        <div class="visual-ball main">${String(n).padStart(2, '0')}</div>
                    `).join('')}
                    <div class="visual-ball separator">+</div>
                    <div class="visual-ball chance">${String(grid.chance).padStart(2, '0')}</div>
                </div>

                <div class="grid-visual-badges">
                    ${(grid.badges || []).map(badge => {
                        let icon = '🎯';
                        let badgeClass = 'badge-default';

                        if (badge.toLowerCase().includes('chaud')) {
                            icon = '🔥';
                            badgeClass = 'badge-hot';
                        } else if (badge.toLowerCase().includes('spectre') || badge.toLowerCase().includes('large')) {
                            icon = '📏';
                            badgeClass = 'badge-spectrum';
                        } else if (badge.toLowerCase().includes('quilibr') || badge.toLowerCase().includes('pair')) {
                            icon = '⚖️';
                            badgeClass = 'badge-balanced';
                        } else if (badge.toLowerCase().includes('hybride')) {
                            icon = '⚙️';
                            badgeClass = 'badge-hybrid';
                        } else if (badge.toLowerCase().includes('retard') || badge.toLowerCase().includes('cart')) {
                            icon = '⏰';
                            badgeClass = 'badge-gap';
                        }

                        return `<span class="visual-badge ${badgeClass}">${icon} ${badge}</span>`;
                    }).join('')}
                </div>

                <div class="grille-pitch grille-pitch-loading" data-pitch-index="${index}">
                    <span class="pitch-icon">\u{1F916}</span> HYBRIDE analyse ta grille\u2026
                </div>
            </div>
        `;

        // Tracking grille individuelle
        trackGridGeneration(grid, index + 1, targetDate);

        // Afficher card partenaire APRES chaque grille (sauf la derniere)
        if (index < grids.length - 1) {
            html += createPartnerCard(index);
        }
    });

    // Footer disclaimer
    html += `
        <div class="results-footer">
            <p><strong>Rappel important :</strong> Ces grilles sont générées à partir de statistiques historiques.
            Le Loto est un jeu de hasard et aucune méthode ne garantit de gains.</p>
            <p>Jouez responsable : <a href="https://www.joueurs-info-service.fr" target="_blank">Joueurs Info Service</a></p>
        </div>
    `;

    // Injecter dans le DOM
    const numbersGrid = document.getElementById('numbers-grid');
    const keyInfo = document.getElementById('key-info');
    const explanationsSection = document.getElementById('explanations-section');

    // Vider les anciens contenus
    numbersGrid.innerHTML = '';
    keyInfo.innerHTML = html;
    keyInfo.style.background = 'transparent';
    keyInfo.style.borderLeft = 'none';
    keyInfo.style.padding = '0';
    explanationsSection.style.display = 'none';

    // Titre et affichage
    document.getElementById('result-title').textContent = 'Analyse du tirage';
    showSuccess();
}

/**
 * Affiche les grilles générées sous forme de cards visuelles premium (version legacy)
 * @param {Array} grids - Tableau des grilles générées
 * @param {Object} metadata - Métadonnées de génération
 * @param {string} targetDate - Date cible du tirage (format YYYY-MM-DD)
 */
function displayGridsVisual(grids, metadata, targetDate) {
    // Formater la date pour l'affichage
    const dateObj = new Date(targetDate + 'T00:00:00');
    const dateFormatted = dateObj.toLocaleDateString('fr-FR', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric'
    });

    // Construire le HTML
    let html = `
        <div class="analysis-header">
            <h3>Grilles recommandées pour le ${dateFormatted}</h3>
            <div class="analysis-metadata">
                <span class="meta-item">
                    <span class="meta-icon">📊</span>
                    Mode : ${translateMode(metadata.mode || 'balanced')}
                </span>
                <span class="meta-item">
                    <span class="meta-icon">🎲</span>
                    ${metadata.nb_tirages_total || '?'} tirages analysés
                </span>
                <span class="meta-item">
                    <span class="meta-icon">📅</span>
                    Fenêtre : ${metadata.fenetre_principale_annees || '?'} ans
                </span>
            </div>
        </div>
        <div class="grids-visual-container">
    `;

    // Pour chaque grille
    grids.forEach((grid, index) => {
        // Profil descriptif basé sur les badges (indicateurs réels)
        const badges = grid.badges || [];
        let convergenceLabel, convergenceClass;
        if (badges.some(b => b.toLowerCase().includes('chaud'))) {
            convergenceLabel = 'Profil chaud';
            convergenceClass = 'convergence-elevated';
        } else if (badges.some(b => b.toLowerCase().includes('retard') || b.toLowerCase().includes('cart'))) {
            convergenceLabel = 'Profil mixte';
            convergenceClass = 'convergence-moderate';
        } else {
            convergenceLabel = 'Profil équilibré';
            convergenceClass = 'convergence-elevated';
        }

        html += `
            <div class="grid-visual-card" style="animation-delay: ${index * 0.15}s">
                <div class="grid-visual-header">
                    <div class="grid-number">
                        <span class="grid-number-label">Grille</span>
                        <span class="grid-number-value">#${index + 1}</span>
                    </div>
                    <div class="grid-convergence-indicator ${convergenceClass}">
                        <span class="convergence-label">Profil</span>
                        <span class="convergence-value">${convergenceLabel}</span>
                    </div>
                </div>

                <div class="grid-visual-numbers">
                    ${[...grid.nums].sort((a, b) => a - b).map(n => `
                        <div class="visual-ball main">${String(n).padStart(2, '0')}</div>
                    `).join('')}
                    <div class="visual-ball separator">+</div>
                    <div class="visual-ball chance">${String(grid.chance).padStart(2, '0')}</div>
                </div>

                <div class="grid-visual-badges">
                    ${(grid.badges || []).map(badge => {
                        let icon = '🎯';
                        let badgeClass = 'badge-default';

                        if (badge.toLowerCase().includes('chaud')) {
                            icon = '🔥';
                            badgeClass = 'badge-hot';
                        } else if (badge.toLowerCase().includes('spectre') || badge.toLowerCase().includes('large')) {
                            icon = '📏';
                            badgeClass = 'badge-spectrum';
                        } else if (badge.toLowerCase().includes('quilibr') || badge.toLowerCase().includes('pair')) {
                            icon = '⚖️';
                            badgeClass = 'badge-balanced';
                        } else if (badge.toLowerCase().includes('hybride')) {
                            icon = '⚙️';
                            badgeClass = 'badge-hybrid';
                        } else if (badge.toLowerCase().includes('retard') || badge.toLowerCase().includes('cart')) {
                            icon = '⏰';
                            badgeClass = 'badge-gap';
                        }

                        return `<span class="visual-badge ${badgeClass}">${icon} ${badge}</span>`;
                    }).join('')}
                </div>
            </div>
        `;
    });

    html += `
        </div>
        <div class="analysis-footer">
            <p>⚠️ Le Loto est un jeu de pur hasard. Ces grilles sont générées à titre indicatif uniquement et ne garantissent aucun gain.</p>
        </div>
    `;

    // Injecter dans le DOM
    const numbersGrid = document.getElementById('numbers-grid');
    const keyInfo = document.getElementById('key-info');
    const explanationsSection = document.getElementById('explanations-section');

    // Vider les anciens contenus
    numbersGrid.innerHTML = '';
    keyInfo.innerHTML = html;
    keyInfo.style.background = 'transparent';
    keyInfo.style.borderLeft = 'none';
    keyInfo.style.padding = '0';
    explanationsSection.style.display = 'none';

    // Titre et affichage
    document.getElementById('result-title').textContent = 'Analyse du tirage';
    showSuccess();
}

// ================================================================
// UI HELPERS
// ================================================================

function displayNumbers(numbers, chanceNumber = null) {
    const grid = document.getElementById('numbers-grid');
    grid.innerHTML = '';

    // Tri croissant visuel uniquement — données brutes côté moteur/API
    const sorted = [...numbers].sort((a, b) => a - b);
    sorted.forEach(num => {
        const ball = document.createElement('div');
        ball.className = 'number-ball';
        ball.textContent = num;
        grid.appendChild(ball);
    });

    if (chanceNumber !== null) {
        const chanceBall = document.createElement('div');
        chanceBall.className = 'number-ball chance';
        chanceBall.textContent = chanceNumber;
        chanceBall.title = 'Numéro Chance';
        grid.appendChild(chanceBall);
    }
}

function displayKeyInfo(items) {
    const keyInfoDiv = document.getElementById('key-info');
    const ul = document.createElement('ul');

    items.forEach(item => {
        const li = document.createElement('li');
        li.textContent = item;
        ul.appendChild(li);
    });

    keyInfoDiv.innerHTML = '';
    keyInfoDiv.appendChild(ul);
}

// Fonction displayDetails() supprimée - remplacée par displayExplanations()

function displayExplanations(grid) {
    const section = document.getElementById('explanations-section');

    if (!grid.explain) {
        section.style.display = 'none';
        return;
    }

    const { numbers, chance, summary } = grid.explain;

    let html = `
        <div style="margin-top: 32px; padding: 24px; background: #F8F9FA; border-radius: 8px;">
            <h3 style="font-size: 1.3rem; margin-bottom: 16px; color: var(--primary);">
                💡 Pourquoi ces numéros ?
            </h3>
            <p style="color: var(--text-muted); margin-bottom: 24px; font-style: italic;">
                ${summary}
            </p>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px;">
    `;

    // Explications pour chaque numéro principal (tri croissant visuel)
    for (let num of [...grid.nums].sort((a, b) => a - b)) {
        const data = numbers[num];
        html += `
            <div class="explain-card" style="background: white; padding: 16px; border-radius: 8px;">
                <div style="font-size: 1.8rem; font-weight: 700; color: var(--primary); margin-bottom: 8px;">
                    ${num}
                </div>
                <div style="font-size: 0.9rem; color: var(--text-dark); line-height: 1.6;">
                    <strong>Sorties observées :</strong> ${data.freq_observed}<br>
                    <strong>Dernière apparition :</strong> ${formatDate(data.last_date)}<br>
                    <strong>Écart actuel :</strong> ${data.gap_draws} tirages<br>
                    <strong>Profil :</strong> ${data.tags.join(', ')}
                </div>
            </div>
        `;
    }

    html += `</div>`;

    // Explication numéro chance
    const chanceData = chance;
    html += `
        <div style="background: #FFF9F0; padding: 20px; border-radius: 8px; border-left: 4px solid #FFD700; margin-bottom: 24px;">
            <h4 style="font-size: 1.1rem; margin-bottom: 12px; color: #E65100;">
                🎯 Numéro Chance : ${grid.chance}
            </h4>
            <div style="font-size: 0.9rem; color: var(--text-dark); line-height: 1.6;">
                <strong>Sorties observées :</strong> ${chanceData.freq_observed}<br>
                <strong>Dernière apparition :</strong> ${formatDate(chanceData.last_date)}<br>
                <strong>Écart actuel :</strong> ${chanceData.gap_draws} tirages<br>
                <strong>Profil :</strong> ${chanceData.tags.join(', ')}
            </div>
        </div>

        <div style="margin-top: 24px; padding: 16px; background: #E3F2FD; border-left: 4px solid #2196F3; border-radius: 8px;">
            <strong style="color: #0D47A1;">⚠️ Avertissement :</strong><br>
            <span style="font-size: 0.95rem; color: #0D47A1;">
                Ces informations sont basées exclusivement sur l'historique des tirages passés.
                Elles sont descriptives et n'ont aucun lien avec les chances de gain.
                Le Loto reste un jeu de pur hasard.
            </span>
        </div>
    </div>
    `;

    section.innerHTML = html;
    section.style.display = 'block';
}

// Fonction helper pour formater les dates
function formatDate(dateStr) {
    if (!dateStr || dateStr === "Inconnu") return "Inconnu";
    const [year, month, day] = dateStr.split('-');
    return `${day}/${month}/${year}`;
}

function showSuccess() {
    resultsSection.style.display = 'block';
    successState.style.display = 'block';
    errorState.style.display = 'none';
    resultsSection.classList.add('fade-in');

    // Auto-scroll vers les résultats après génération
    // Délai de 300ms pour laisser l'animation fade-in démarrer
    setTimeout(() => {
        resultsSection.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
    }, 300);
}

function showError(message) {
    resultsSection.style.display = 'block';
    successState.style.display = 'none';
    errorState.style.display = 'block';
    document.getElementById('error-message').textContent = message;
    resultsSection.classList.add('fade-in');
}

function hideResults() {
    resultsSection.style.display = 'none';
    successState.style.display = 'none';
    errorState.style.display = 'none';
}

function setLoading(button, isLoading) {
    // Support both .btn-text (standard buttons) and .cta-text (CTA buttons)
    const btnText = button.querySelector('.btn-text') || button.querySelector('.cta-text');
    const spinner = button.querySelector('.spinner');
    // For CTA buttons, also hide icon and arrow
    const ctaIcon = button.querySelector('.cta-icon');
    const ctaArrow = button.querySelector('.cta-arrow');

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

// toggleAccordion removed - replaced by <details> element in HTML

function handleCopy() {
    if (!currentResult) return;

    let textToCopy = '';

    // Build copy text based on result type
    if (currentResult.analysis) {
        textToCopy = currentResult.analysis;
    } else if (currentResult.grids) {
        textToCopy = currentResult.grids.map((grid, i) => {
            const nums = [...grid.nums].sort((a, b) => a - b)
                .map(n => String(n).padStart(2, '0')).join(' ');
            const chance = String(grid.chance).padStart(2, '0');
            return `Grille ${i + 1} : ${nums} + ${chance}`;
        }).join('\n');
    } else if (currentResult.stats) {
        textToCopy = JSON.stringify(currentResult.stats, null, 2);
    }

    navigator.clipboard.writeText(textToCopy).then(() => {
        // Analytics GA4 — Track copie de grille
        if (window.LotoIAAnalytics && window.LotoIAAnalytics.product) {
            window.LotoIAAnalytics.product.copyGrid({});
        }
        // Visual feedback
        const originalText = btnCopy.textContent;
        btnCopy.textContent = '✓';
        setTimeout(() => {
            btnCopy.textContent = originalText;
        }, 1500);
    }).catch(() => {
        alert('Erreur lors de la copie');
    });
}

function showUpdateStatus(message, type = 'info') {
    updateStatus.style.display = 'block';
    updateStatus.textContent = message;
    updateStatus.className = `update-status ${type}`;
    updateStatus.classList.add('fade-in');
}

function hideUpdateStatus() {
    updateStatus.style.display = 'none';
    updateStatus.className = 'update-status';
}

function showInstallStatus(message, type = 'info') {
    installStatus.style.display = 'block';
    installStatus.textContent = message;
    installStatus.className = `install-status ${type}`;
    installStatus.classList.add('fade-in');
}

function hideInstallStatus() {
    installStatus.style.display = 'none';
    installStatus.className = 'install-status';
}

function translateMode(mode) {
    const modes = {
        'safe': 'Sécurisé',
        'balanced': 'Équilibré',
        'risky': 'Audacieux'
    };
    return modes[mode] || mode;
}

// ================================================================
// DEBUG LOGS
// ================================================================

/**
 * Ajoute une entrée de log dans le panneau de debug
 *
 * @param {string} message - Message à logger
 * @param {string} type - Type de log : info, success, error, warning, request, response
 */
function addLog(message, type = 'info') {
    if (!logsBody) return;
    const now = new Date();
    const time = now.toLocaleTimeString('fr-FR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    logEntry.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-message">${message}</span>
    `;
    logsBody.appendChild(logEntry);
    logsBody.scrollTop = logsBody.scrollHeight;
}

function toggleLogs() {
    if (!logsPanel) return;
    if (logsPanel.style.display === 'none') {
        logsPanel.style.display = 'flex';
        addLog('Panneau de logs ouvert', 'info');
    } else {
        logsPanel.style.display = 'none';
    }
}

function closeLogs() {
    if (!logsPanel) return;
    logsPanel.style.display = 'none';
}

function clearLogs() {
    if (!logsBody) return;
    logsBody.innerHTML = `
        <div class="log-entry log-info">
            <span class="log-time">--:--:--</span>
            <span class="log-message">Logs effacés.</span>
        </div>
    `;
}

// ================================================================
// PITCH HYBRIDE — Gemini async
// ================================================================

/**
 * Appelle /api/pitch-grilles et affiche les pitchs sous chaque grille.
 * Non-bloquant : les grilles sont deja visibles, les pitchs arrivent apres.
 * @param {Array} grids - Tableau des grilles generees ({nums, chance})
 */
async function fetchAndDisplayPitchs(grids) {
    const payload = grids.map(g => ({
        numeros: g.nums,
        chance: g.chance
    }));

    try {
        const response = await fetch('/api/pitch-grilles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ grilles: payload })
        });
        const data = await response.json();

        if (data.success && data.data && data.data.pitchs) {
            data.data.pitchs.forEach((pitch, index) => {
                const el = document.querySelector(`.grille-pitch[data-pitch-index="${index}"]`);
                if (el && pitch) {
                    el.innerHTML = `<span class="pitch-icon">\u{1F916}</span> ${pitch}`;
                    el.classList.remove('grille-pitch-loading');
                }
            });
            addLog(`${data.data.pitchs.length} pitch(s) HYBRIDE affiche(s)`, 'success');
        } else {
            // Pas de pitchs — retirer les placeholders
            document.querySelectorAll('.grille-pitch-loading').forEach(el => el.remove());
        }
    } catch (e) {
        console.warn('[PITCH] Erreur:', e);
        document.querySelectorAll('.grille-pitch-loading').forEach(el => el.remove());
    }
}

// ================================================================
// START APP
// ================================================================

document.addEventListener('DOMContentLoaded', init);
