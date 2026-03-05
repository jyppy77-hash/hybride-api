/**
 * LotoIA Universal Event Tracker
 * Sends events to /api/track (internal event_log table).
 * Usage: LotoIA_track('event-name', { key: 'value' })
 */
(function() {
    'use strict';

    var ENDPOINT = '/api/track';
    var DEDUP_TTL = 2000; // ms — ignore duplicate event within 2s

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

    function dedupKey(event, meta) {
        return event + '|' + JSON.stringify(meta || {});
    }

    var _lastEvents = {};

    window.LotoIA_track = function(event, meta) {
        if (!event) return;

        // Owner filter — skip if owner flag is set
        if (window.__OWNER__) return;

        // Dedup
        var key = dedupKey(event, meta);
        var now = Date.now();
        if (_lastEvents[key] && (now - _lastEvents[key]) < DEDUP_TTL) return;
        _lastEvents[key] = now;

        var payload = {
            event: event,
            page: getPage(),
            lang: getLang(),
            device: getDevice()
        };
        if (meta && typeof meta === 'object') {
            payload.module = meta.module || '';
            payload.meta = meta;
        }

        try {
            if (navigator.sendBeacon) {
                navigator.sendBeacon(ENDPOINT, new Blob([JSON.stringify(payload)], {type: 'application/json'}));
            } else {
                fetch(ENDPOINT, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                    keepalive: true
                }).catch(function() {});
            }
        } catch (e) {
            // Silent fail — tracking should never break the page
        }
    };
})();
