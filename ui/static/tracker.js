/**
 * LotoIA Universal Event Tracker
 * Sends events to /api/track (internal event_log table).
 * Usage: LotoIA_track('event-name', { key: 'value' })
 */
(function() {
    'use strict';

    var ENDPOINT = '/api/track';
    var DEDUP_TTL = 1000; // ms — ignore duplicate event within 1s (V92 S13: was 2s)

    function getDevice() {
        var w = window.innerWidth || document.documentElement.clientWidth;
        if (w < 768) return 'mobile';
        if (w < 1024) return 'tablet';
        return 'desktop';
    }

    function getLang() {
        if (window.LotoIA_lang) return window.LotoIA_lang;
        var html = document.documentElement.lang;
        return html ? html.substring(0, 2) : 'fr';
    }

    function getPage() {
        return window.location.pathname;
    }

    function getProductCode(meta) {
        // Explicit product_code from caller — sponsor events pass the full
        // code with A/B suffix (e.g. LOTO_FR_A, EM_EN_B) so event_log
        // records match sponsor_impressions.sponsor_id exactly.
        if (meta && meta.product_code) return meta.product_code;
        // Auto-deduce from module + lang (no A/B suffix — general tracking
        // only needs the game/lang granularity, not the sponsor slot).
        var mod = (meta && meta.module) || '';
        var lang = getLang().toUpperCase();
        if (mod === 'loto') return 'LOTO_FR';
        if (mod.indexOf('euromillions') === 0) return 'EM_' + lang;
        return '';
    }

    function dedupKey(event, meta) {
        // V92 S13: key = event + page (not full meta) — allows same event from
        // different pages in rapid navigation, while still deduplicating
        // genuine double-fires on the same page.
        var page = (meta && meta.page) || window.location.pathname;
        return event + '|' + page;
    }

    var _lastEvents = {};

    window.LotoIA_track = function(event, meta) {
        if (!event) return;

        // Owner filter — skip if owner flag is set (defense-in-depth: script + body attr)
        if (window.__OWNER__ || (document.body && document.body.dataset.owner === '1')) return;

        // Dedup
        var key = dedupKey(event, meta);
        var now = Date.now();
        if (_lastEvents[key] && (now - _lastEvents[key]) < DEDUP_TTL) return;
        _lastEvents[key] = now;

        var payload = {
            event: event,
            page: getPage(),
            lang: getLang(),
            device: getDevice(),
            product_code: getProductCode(meta)
        };
        if (meta && typeof meta === 'object') {
            payload.module = meta.module || '';
            payload.meta = meta;
        }

        try {
            fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                keepalive: true
            }).catch(function() {});
        } catch (e) {
            // Fallback sendBeacon if fetch throws (e.g. page unload race)
            try {
                navigator.sendBeacon(ENDPOINT, new Blob([JSON.stringify(payload)], {type: 'application/json'}));
            } catch (e2) {}
        }
    };
})();
