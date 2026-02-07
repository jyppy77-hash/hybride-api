(function() {
    'use strict';

    const THEME_KEY = 'lotoia-theme';
    const NIGHT_START = 20;
    const NIGHT_END = 7;
    let initialized = false;

    function isNightTime() {
        const hour = new Date().getHours();
        return hour >= NIGHT_START || hour < NIGHT_END;
    }

    function getSavedTheme() {
        try {
            return localStorage.getItem(THEME_KEY);
        } catch (e) {
            return null;
        }
    }

    function saveTheme(theme) {
        try {
            localStorage.setItem(THEME_KEY, theme);
        } catch (e) {}
    }

    function clearSavedTheme() {
        try {
            localStorage.removeItem(THEME_KEY);
        } catch (e) {}
    }

    function applyTheme(theme) {
        if (!document.body) return false;
        document.body.classList.remove('theme-night', 'theme-day');
        document.body.classList.add('theme-' + theme);
        updateSwitchButton(theme);
        return true;
    }

    function updateSwitchButton(theme) {
        var switchBtn = document.getElementById('theme-switch');
        if (!switchBtn) return;
        switchBtn.setAttribute('data-current-theme', theme);
        switchBtn.setAttribute('title', 'Passer en mode ' + (theme === 'night' ? 'Jour' : 'Nuit'));
    }

    function getTargetTheme() {
        var saved = getSavedTheme();
        if (saved === 'night' || saved === 'day') return saved;
        return isNightTime() ? 'night' : 'day';
    }

    function initTheme() {
        if (initialized) return;
        var theme = getTargetTheme();
        if (applyTheme(theme)) {
            initialized = true;
        }
    }

    function toggleTheme() {
        if (!document.body) return null;
        var current = document.body.classList.contains('theme-night') ? 'night' : 'day';
        var next = current === 'night' ? 'day' : 'night';
        var btn = document.getElementById('theme-switch');
        if (btn) {
            btn.classList.add('switching');
            setTimeout(function() { btn.classList.remove('switching'); }, 500);
        }
        applyTheme(next);
        saveTheme(next);
        try { if (window.LotoIAAnalytics && window.LotoIAAnalytics.ux) { window.LotoIAAnalytics.ux.themeChange(next); } } catch(e) {}
        return next;
    }

    function resetToAutoTheme() {
        clearSavedTheme();
        var theme = isNightTime() ? 'night' : 'day';
        applyTheme(theme);
        return theme;
    }

    function bindSwitch() {
        var btn = document.getElementById('theme-switch');
        if (btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                toggleTheme();
            });
        }
    }

    window.LotoIATheme = {
        init: initTheme,
        toggle: toggleTheme,
        setTheme: function(theme) {
            if (theme === 'night' || theme === 'day') {
                applyTheme(theme);
                saveTheme(theme);
            }
        },
        resetToAuto: resetToAutoTheme,
        getCurrentTheme: function() {
            if (!document.body) return getTargetTheme();
            return document.body.classList.contains('theme-night') ? 'night' : 'day';
        },
        isNightTime: isNightTime
    };

    if (document.body) {
        initTheme();
    }

    // Injection annee courante dans tous les .dynamic-year
    function injectYear() {
        var y = new Date().getFullYear();
        var els = document.querySelectorAll('.dynamic-year');
        for (var i = 0; i < els.length; i++) {
            els[i].textContent = y;
        }
    }

    // Nombre de grilles META DONNÉE (variable globale)
    window.META_GRID_COUNT = 75;

    function injectGridCount() {
        var els = document.querySelectorAll('.meta-grid-count');
        for (var i = 0; i < els.length; i++) {
            els[i].textContent = window.META_GRID_COUNT;
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initTheme();
            bindSwitch();
            injectYear();
            injectGridCount();
        });
    } else {
        initTheme();
        bindSwitch();
        injectYear();
        injectGridCount();
    }
})();
