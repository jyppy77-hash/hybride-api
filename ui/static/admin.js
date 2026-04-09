/**
 * LotoIA Admin — AJAX filters + Chart.js
 */
var LotoAdmin = (function() {
    'use strict';

    var chart = null;
    var PAGE_SIZE = 50;

    // ── Helpers ──

    function qs(sel) { return document.querySelector(sel); }
    function qsa(sel) { return document.querySelectorAll(sel); }

    function fetchJSON(url) {
        return fetch(url, { credentials: 'same-origin' })
            .then(function(r) {
                if (r.status === 302 || r.status === 401) { window.location = '/admin/login'; return null; }
                return r.json();
            });
    }

    function escHtml(s) {
        if (!s) return '';
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function stars(n) {
        var s = '';
        for (var i = 0; i < 5; i++) s += i < n ? '\u2605' : '\u2606';
        return s;
    }

    /** Format UTC datetime string to Europe/Paris local display. */
    function fmtDate(s) {
        if (!s) return '';
        try {
            var iso = s.replace(' ', 'T');
            if (iso.indexOf('Z') === -1 && iso.indexOf('+') === -1) iso += 'Z';
            var d = new Date(iso);
            if (isNaN(d.getTime())) return escHtml(s);
            return d.toLocaleString('fr-FR', { timeZone: 'Europe/Paris', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
        } catch (e) { return escHtml(s); }
    }

    /** Format UTC datetime string to Europe/Paris time only (HH:MM:SS). */
    function fmtTime(s) {
        if (!s) return '';
        try {
            var iso = s.replace(' ', 'T');
            if (iso.indexOf('Z') === -1 && iso.indexOf('+') === -1) iso += 'Z';
            var d = new Date(iso);
            if (isNaN(d.getTime())) return escHtml(s);
            return d.toLocaleTimeString('fr-FR', { timeZone: 'Europe/Paris', hour: '2-digit', minute: '2-digit', second: '2-digit' });
        } catch (e) { return escHtml(s); }
    }

    // ── Period helpers ──

    function toggleCustomDates() {
        var sel = qs('#f-period');
        var s = qs('#f-date-start');
        var e = qs('#f-date-end');
        if (!sel || !s || !e) return;
        var show = sel.value === 'custom';
        s.classList.toggle('hidden', !show);
        e.classList.toggle('hidden', !show);
    }

    // ── Table sorting ──

    function enableSort(tableId, data, renderFn) {
        var headers = qsa('#' + tableId + ' th[data-sort]');
        var sortCol = null, sortDir = 1;
        headers.forEach(function(th) {
            th.style.cursor = 'pointer';
            th.addEventListener('click', function() {
                var col = th.getAttribute('data-sort');
                if (sortCol === col) { sortDir *= -1; } else { sortCol = col; sortDir = 1; }
                data.sort(function(a, b) {
                    var va = a[col] || '', vb = b[col] || '';
                    if (typeof va === 'number') return (va - vb) * sortDir;
                    return String(va).localeCompare(String(vb)) * sortDir;
                });
                renderFn(data, 0);
            });
        });
    }

    // ── Pagination ──

    function renderPagination(total, currentPage, renderFn, data) {
        var pag = qs('#pagination');
        if (!pag) return;
        var pages = Math.ceil(total / PAGE_SIZE);
        if (pages <= 1) { pag.innerHTML = ''; return; }
        var html = '';
        for (var i = 0; i < pages; i++) {
            html += '<button class="pag-btn' + (i === currentPage ? ' active' : '') + '" data-page="' + i + '">' + (i + 1) + '</button>';
        }
        pag.innerHTML = html;
        pag.querySelectorAll('.pag-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                renderFn(data, parseInt(btn.getAttribute('data-page')));
            });
        });
    }

    // ══════════════════════════════════════
    // IMPRESSIONS PAGE
    // ══════════════════════════════════════

    function initImpressions() {
        toggleCustomDates();
        qs('#f-period').addEventListener('change', toggleCustomDates);
        qs('#btn-filter').addEventListener('click', loadImpressions);
        qs('#btn-reset').addEventListener('click', function() {
            qs('#f-period').value = '24h';
            qs('#f-event').value = 'all';
            qs('#f-sponsor').value = 'all';
            qs('#f-tarif').value = 'all';
            qs('#f-lang').value = 'all';
            qs('#f-device').value = 'all';
            toggleCustomDates();
            loadImpressions();
        });
        qs('#btn-export-csv').addEventListener('click', function() {
            window.location = '/admin/api/impressions/csv?' + buildImpressionsParams();
        });
        qs('#btn-export-pdf').addEventListener('click', function() {
            window.location = '/admin/api/sponsor-report/pdf?' + buildImpressionsParams();
        });
        loadImpressions();
    }

    function buildImpressionsParams() {
        var p = qs('#f-period').value;
        var params = 'period=' + p;
        if (p === 'custom') {
            params += '&date_start=' + (qs('#f-date-start').value || '');
            params += '&date_end=' + (qs('#f-date-end').value || '');
        }
        var ev = qs('#f-event').value;
        if (ev !== 'all') params += '&event_type=' + ev;
        var sp = qs('#f-sponsor');
        if (sp && sp.value !== 'all') params += '&sponsor_id=' + sp.value;
        var tarif = qs('#f-tarif');
        if (tarif && tarif.value !== 'all') params += '&tarif=' + tarif.value;
        var lang = qs('#f-lang').value;
        if (lang !== 'all') params += '&lang=' + lang;
        var dev = qs('#f-device').value;
        if (dev !== 'all') params += '&device=' + dev;
        return params;
    }

    function buildImpressionsURL() {
        return '/admin/api/impressions?' + buildImpressionsParams();
    }

    function loadImpressions() {
        fetchJSON(buildImpressionsURL()).then(function(data) {
            if (!data) return;
            renderImpKPI(data.kpi);
            renderSponsorBreakdown(data.by_sponsor || []);
            renderImpChart(data.chart);
            renderImpTable(data.table, 0);
            enableSort('impressions-table', data.table, renderImpTable);
        });
    }

    function renderSponsorBreakdown(bySponsor) {
        var tbody = qs('#sponsor-summary-body');
        if (!tbody) return;
        if (!bySponsor.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:1rem">Aucune donnee</td></tr>';
            return;
        }
        tbody.innerHTML = bySponsor.map(function(r) {
            return '<tr>'
                + '<td style="font-weight:700;color:var(--accent)">' + escHtml(r.sponsor_id || '\u2014') + '</td>'
                + '<td>' + (r.impressions || 0) + '</td>'
                + '<td>' + (r.clics || 0) + '</td>'
                + '<td>' + (r.videos || 0) + '</td>'
                + '<td>' + escHtml(r.ctr || '0.00%') + '</td>'
                + '<td>' + (r.sessions || 0) + '</td>'
                + '</tr>';
        }).join('');
    }

    function renderImpKPI(kpi) {
        qs('#kpi-impressions').textContent = kpi.impressions || 0;
        qs('#kpi-clicks').textContent = kpi.clicks || 0;
        qs('#kpi-videos').textContent = kpi.videos || 0;
        qs('#kpi-ctr').textContent = kpi.ctr || '0.00%';
        qs('#kpi-sessions').textContent = kpi.sessions || 0;
    }

    function renderImpChart(chartData) {
        var ctx = qs('#impressions-chart');
        if (!ctx) return;

        var labels = [];
        var seen = {};
        chartData.forEach(function(r) { if (!seen[r.day]) { labels.push(r.day); seen[r.day] = true; } });

        var types = { 'sponsor-popup-shown': { label: 'Impressions', color: '#3b82f6' }, 'sponsor-click': { label: 'Clics', color: '#10b981' }, 'sponsor-video-played': { label: 'Videos', color: '#f59e0b' }, 'sponsor-inline-shown': { label: 'Chatbot', color: '#8b5cf6' }, 'sponsor-result-shown': { label: 'Résultats', color: '#ec4899' }, 'sponsor-pdf-downloaded': { label: 'PDF', color: '#06b6d4' } };
        var datasets = [];
        Object.keys(types).forEach(function(evType) {
            var vals = labels.map(function(d) {
                var row = chartData.find(function(r) { return r.day === d && r.event_type === evType; });
                return row ? row.cnt : 0;
            });
            datasets.push({ label: types[evType].label, data: vals, backgroundColor: types[evType].color, borderColor: types[evType].color, borderWidth: 1 });
        });

        if (chart) chart.destroy();
        var cs = getComputedStyle(document.body);
        var tickColor = cs.getPropertyValue('--chart-tick').trim() || '#9ca3af';
        var gridColor = cs.getPropertyValue('--chart-grid').trim() || '#2a2d3a';
        var legendColor = cs.getPropertyValue('--chart-legend').trim() || '#e0e0e0';
        chart = new Chart(ctx, {
            type: 'bar',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                scales: { y: { beginAtZero: true, ticks: { color: tickColor }, grid: { color: gridColor } }, x: { ticks: { color: tickColor }, grid: { color: gridColor } } },
                plugins: { legend: { labels: { color: legendColor } } }
            }
        });
    }

    function renderImpTable(rows, page) {
        var tbody = qs('#impressions-tbody');
        var start = page * PAGE_SIZE;
        var slice = rows.slice(start, start + PAGE_SIZE);
        tbody.innerHTML = slice.map(function(r) {
            return '<tr><td>' + escHtml(r.day) + '</td><td style="font-weight:600;color:var(--accent)">' + escHtml(r.sponsor_id || '\u2014') + '</td><td>' + escHtml(r.event_type) + '</td><td>' + escHtml(r.page) + '</td><td>' + escHtml(r.lang) + '</td><td>' + escHtml(r.device) + '</td><td>' + escHtml(r.country) + '</td><td>' + r.cnt + '</td></tr>';
        }).join('');
        renderPagination(rows.length, page, renderImpTable, rows);
    }

    // ══════════════════════════════════════
    // VOTES PAGE
    // ══════════════════════════════════════

    function initVotes() {
        qs('#btn-filter').addEventListener('click', loadVotes);
        qs('#btn-reset').addEventListener('click', function() {
            qs('#f-period').value = 'all';
            qs('#f-source').value = 'all';
            qs('#f-rating').value = 'all';
            loadVotes();
        });
        loadVotes();
    }

    function buildVotesURL() {
        var url = '/admin/api/votes?period=' + qs('#f-period').value;
        var src = qs('#f-source').value;
        if (src !== 'all') url += '&source=' + src;
        var rat = qs('#f-rating').value;
        if (rat !== 'all') url += '&rating=' + rat;
        return url;
    }

    function loadVotes() {
        fetchJSON(buildVotesURL()).then(function(data) {
            if (!data) return;
            renderVotesKPI(data.summary);
            renderDistribution(data.distribution);
            renderVotesTable(data.table, 0);
            enableSort('votes-table', data.table, renderVotesTable);
        });
    }

    function renderVotesKPI(s) {
        qs('#kpi-avg').textContent = s.avg_rating || '0.0';
        qs('#kpi-total').textContent = s.total || 0;
        qs('#kpi-loto').textContent = s.chatbot_loto || 0;
        qs('#kpi-popup').textContent = s.popup_accueil || 0;
        qs('#kpi-em').textContent = s.chatbot_em || 0;
    }

    function renderDistribution(dist) {
        var el = qs('#distribution');
        if (!el) return;
        var maxVal = Math.max.apply(null, dist.map(function(d) { return d.count; })) || 1;
        el.innerHTML = dist.map(function(d) {
            var pct = d.total > 0 ? Math.round(d.count / d.total * 100) : 0;
            var barW = Math.round(d.count / maxVal * 100);
            return '<div class="dist-row"><span class="dist-label">' + d.stars + '\u2605</span><div class="dist-bar-bg"><div class="dist-bar" style="width:' + barW + '%"></div></div><span class="dist-count">' + d.count + ' (' + pct + '%)</span></div>';
        }).join('');
    }

    function renderVotesTable(rows, page) {
        var tbody = qs('#votes-tbody');
        var start = page * PAGE_SIZE;
        var slice = rows.slice(start, start + PAGE_SIZE);
        tbody.innerHTML = slice.map(function(r) {
            return '<tr><td>' + fmtDate(r.created_at) + '</td><td>' + escHtml(r.source) + '</td><td>' + stars(r.rating) + '</td><td>' + escHtml(r.comment || '') + '</td><td>' + escHtml(r.page) + '</td></tr>';
        }).join('');
        renderPagination(rows.length, page, renderVotesTable, rows);
    }

    // ══════════════════════════════════════
    // REALTIME PAGE
    // ══════════════════════════════════════

    var rtTimer = null;
    var rtPreviousIds = [];
    var rtActiveFilter = 'all';
    var rtActivePeriod = '24h';

    var RT_COLORS = {
        'sponsor': '#ff9800', 'rating': '#00c853', 'simulateur': '#4f8cff',
        'chatbot': '#e040fb', 'meta75': '#d4a843'
    };
    var RT_FLAGS = {
        'fr': '\uD83C\uDDEB\uD83C\uDDF7', 'en': '\uD83C\uDDEC\uD83C\uDDE7',
        'es': '\uD83C\uDDEA\uD83C\uDDF8', 'pt': '\uD83C\uDDF5\uD83C\uDDF9',
        'de': '\uD83C\uDDE9\uD83C\uDDEA', 'nl': '\uD83C\uDDF3\uD83C\uDDF1',
        'FR': '\uD83C\uDDEB\uD83C\uDDF7', 'BE': '\uD83C\uDDE7\uD83C\uDDEA',
        'CH': '\uD83C\uDDE8\uD83C\uDDED', 'LU': '\uD83C\uDDF1\uD83C\uDDFA',
        'AT': '\uD83C\uDDE6\uD83C\uDDF9', 'IE': '\uD83C\uDDEE\uD83C\uDDEA',
        'UK': '\uD83C\uDDEC\uD83C\uDDE7'
    };
    var PERIOD_LABELS = { 'today': "Aujourd'hui", 'week': '7 derniers jours', 'month': '30 derniers jours' };

    function rtEventCategory(evType) {
        if (evType.indexOf('sponsor') === 0) return 'sponsor';
        if (evType.indexOf('rating') === 0) return 'rating';
        if (evType.indexOf('simulateur') === 0) return 'simulateur';
        if (evType.indexOf('chatbot') === 0) return 'chatbot';
        if (evType.indexOf('meta75') === 0) return 'meta75';
        return 'other';
    }

    function rtDotColor(evType) {
        return RT_COLORS[rtEventCategory(evType)] || '#8b8b9e';
    }

    function rtBuildParams() {
        var evType = qs('#f-event-type').value;
        return 'event_type=' + encodeURIComponent(evType) + '&period=' + encodeURIComponent(rtActivePeriod);
    }

    function rtUpdateExportLinks() {
        var p = rtBuildParams();
        var csvEl = qs('#rt-export-csv');
        var pdfEl = qs('#rt-export-pdf');
        if (csvEl) csvEl.href = '/admin/export/realtime/csv?' + p;
        if (pdfEl) pdfEl.href = '/admin/export/realtime/pdf?' + p;
    }

    function initRealtime() {
        loadRealtime();
        qs('#rt-auto').addEventListener('change', function() {
            if (this.checked) { startAutoRefresh(); } else { stopAutoRefresh(); }
        });
        qs('#f-event-type').addEventListener('change', function() {
            rtActiveFilter = 'all';
            loadRealtime();
        });

        // Period toggle
        qsa('.rt-period-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                qsa('.rt-period-btn').forEach(function(b) { b.classList.remove('active'); });
                btn.classList.add('active');
                rtActivePeriod = btn.getAttribute('data-period');
                loadRealtime();
            });
        });

        // Init heatmap (60 empty blocks)
        var hm = qs('#rt-heatmap');
        if (hm) {
            for (var i = 0; i < 60; i++) {
                var b = document.createElement('div');
                b.className = 'rt-hm-block';
                hm.appendChild(b);
            }
        }

        startAutoRefresh();
    }

    function startAutoRefresh() {
        stopAutoRefresh();
        rtTimer = setInterval(loadRealtime, 5000);
    }

    function stopAutoRefresh() {
        if (rtTimer) { clearInterval(rtTimer); rtTimer = null; }
    }

    function loadRealtime() {
        var url = '/admin/api/realtime?' + rtBuildParams();
        rtUpdateExportLinks();
        // Pulse title on refresh
        var title = qs('#rt-title');
        if (title) { title.classList.remove('rt-title-pulse'); void title.offsetWidth; title.classList.add('rt-title-pulse'); }

        fetchJSON(url).then(function(data) {
            if (!data) return;
            animateKPI('kpi-visitors', data.kpi.unique_visitors || 0);
            animateKPI('kpi-total', data.kpi.total || 0);
            animateKPI('kpi-hour', data.kpi.hour || 0);
            animateKPI('kpi-types', data.kpi.types || 0);
            // Update period label
            var lbl = qs('#kpi-total-label');
            if (lbl) lbl.textContent = 'Events ' + (PERIOD_LABELS[rtActivePeriod] || '').toLowerCase();
            renderRtTypeCards(data.by_type || {});
            renderRtFeed(data.events);
            renderRtEventTypes(data.event_types);
            renderRtHeatmap(data.events);
        });
    }

    function animateKPI(id, target) {
        var el = qs('#' + id);
        if (!el) return;
        var current = parseInt(el.textContent) || 0;
        if (current === target) return;
        var diff = target - current;
        var steps = Math.min(Math.abs(diff), 15);
        var step = 0;
        var interval = setInterval(function() {
            step++;
            var val = Math.round(current + (diff * step / steps));
            el.textContent = val;
            if (step >= steps) { el.textContent = target; clearInterval(interval); }
        }, 30);
    }

    function renderRtTypeCards(byType) {
        var container = qs('#rt-type-cards');
        if (!container) return;
        var types = Object.keys(byType);
        if (!types.length) { container.innerHTML = ''; return; }
        container.innerHTML = types.map(function(t) {
            var cat = rtEventCategory(t);
            var color = RT_COLORS[cat] || '#8b8b9e';
            var activeClass = (rtActiveFilter === t) ? ' active' : '';
            return '<div class="rt-type-card' + activeClass + '" data-event-type="' + escHtml(t) + '">'
                + '<div><span class="rt-type-card-dot" style="background:' + color + ';box-shadow:0 0 6px ' + color + '"></span>'
                + '<span class="rt-type-card-name">' + escHtml(t) + '</span></div>'
                + '<div class="rt-type-card-count">' + byType[t] + '</div>'
                + '</div>';
        }).join('');

        // Click → filter by event_type
        qsa('.rt-type-card').forEach(function(card) {
            card.addEventListener('click', function() {
                var evType = card.getAttribute('data-event-type');
                if (rtActiveFilter === evType) {
                    rtActiveFilter = 'all';
                    qs('#f-event-type').value = 'all';
                } else {
                    rtActiveFilter = evType;
                    qs('#f-event-type').value = evType;
                }
                loadRealtime();
            });
        });
    }

    function renderRtFeed(events) {
        var feed = qs('#rt-feed');
        if (!feed) return;
        var newIds = events.map(function(e) { return e.event_type + e.created_at + e.page; });
        var isNew = rtPreviousIds.length > 0;

        feed.innerHTML = events.map(function(e, idx) {
            var cat = rtEventCategory(e.event_type);
            var color = rtDotColor(e.event_type);
            var deviceIcon = (e.device === 'mobile') ? '\uD83D\uDCF1' : ((e.device === 'tablet') ? '\uD83D\uDCF1' : '\uD83D\uDDA5\uFE0F');
            var flag = RT_FLAGS[e.lang] || RT_FLAGS[e.country] || '';
            var slideClass = (isNew && rtPreviousIds.indexOf(newIds[idx]) === -1) ? ' rt-card-new' : '';

            return '<div class="rt-event-card' + slideClass + '" data-category="' + cat + '">'
                + '<div class="rt-event-dot" style="background:' + color + ';box-shadow:0 0 8px ' + color + '"></div>'
                + '<div class="rt-event-body">'
                + '<div class="rt-event-top">'
                + '<span class="rt-badge rt-badge-' + escHtml(e.event_type).replace(/[^a-z0-9-]/g, '') + '">' + escHtml(e.event_type) + '</span>'
                + '<span class="rt-event-time">' + fmtTime(e.created_at) + '</span>'
                + '<span class="rt-event-device">' + deviceIcon + ' ' + escHtml(e.device || '') + '</span>'
                + '<span class="rt-event-flag">' + flag + '</span>'
                + '</div>'
                + '<div class="rt-event-bottom">'
                + '<span class="rt-event-page">' + escHtml(e.page || '') + '</span>'
                + (e.module ? '<span class="rt-event-module">' + escHtml(e.module) + '</span>' : '')
                + '<span class="rt-event-country">' + escHtml(e.country || '') + '</span>'
                + '</div>'
                + '</div>'
                + '</div>';
        }).join('');

        rtPreviousIds = newIds;
    }

    function renderRtEventTypes(types) {
        var sel = qs('#f-event-type');
        var current = sel.value;
        var html = '<option value="all">Tous les events</option>';
        types.forEach(function(t) {
            html += '<option value="' + escHtml(t) + '"' + (t === current ? ' selected' : '') + '>' + escHtml(t) + '</option>';
        });
        sel.innerHTML = html;
    }

    function renderRtHeatmap(events) {
        var blocks = qsa('.rt-hm-block');
        if (!blocks.length) return;
        // Parse event times, count per minute bucket (0=now, 59=60min ago)
        var counts = new Array(60);
        for (var i = 0; i < 60; i++) counts[i] = 0;
        var now = new Date();
        events.forEach(function(e) {
            if (!e.created_at) return;
            try {
                var iso = e.created_at.replace(' ', 'T');
                if (iso.indexOf('Z') === -1 && iso.indexOf('+') === -1) iso += 'Z';
                var evDate = new Date(iso);
                if (isNaN(evDate.getTime())) return;
                var diffMin = Math.floor((now - evDate) / 60000);
                if (diffMin >= 0 && diffMin < 60) counts[diffMin]++;
            } catch (ex) {}
        });
        // Render blocks (rightmost = now)
        for (var j = 0; j < 60; j++) {
            var c = counts[59 - j];
            var block = blocks[j];
            if (c === 0) { block.className = 'rt-hm-block rt-hm-0'; }
            else if (c <= 2) { block.className = 'rt-hm-block rt-hm-1'; }
            else { block.className = 'rt-hm-block rt-hm-2'; }
        }
    }

    // ══════════════════════════════════════
    // ENGAGEMENT PAGE
    // ══════════════════════════════════════

    var ENG_COLORS = {
        chatbot: '#a855f7',
        rating: '#22c55e',
        simulateur: '#3b82f6',
        sponsor: '#d4a843'
    };

    function initEngagement() {
        toggleCustomDates();
        qs('#f-period').addEventListener('change', toggleCustomDates);
        qs('#btn-filter').addEventListener('click', loadEngagement);
        qs('#btn-reset').addEventListener('click', function() {
            qs('#f-period').value = '24h';
            qs('#f-category').value = 'all';
            qs('#f-product-code').value = 'all';
            qs('#f-event').value = 'all';
            qs('#f-module').value = 'all';
            qs('#f-lang').value = 'all';
            qs('#f-device').value = 'all';
            toggleCustomDates();
            loadEngagement();
        });
        loadEngagement();
    }

    function buildEngagementURL() {
        var p = qs('#f-period').value;
        var url = '/admin/api/engagement?period=' + p;
        if (p === 'custom') {
            url += '&date_start=' + (qs('#f-date-start').value || '');
            url += '&date_end=' + (qs('#f-date-end').value || '');
        }
        var cat = qs('#f-category').value;
        if (cat !== 'all') url += '&category=' + cat;
        var pc = qs('#f-product-code').value;
        if (pc !== 'all') url += '&product_code=' + pc;
        var ev = qs('#f-event').value;
        if (ev !== 'all') url += '&event_type=' + ev;
        var mod = qs('#f-module');
        if (mod && mod.value !== 'all') url += '&module=' + mod.value;
        var lang = qs('#f-lang').value;
        if (lang !== 'all') url += '&lang=' + lang;
        var dev = qs('#f-device').value;
        if (dev !== 'all') url += '&device=' + dev;
        return url;
    }

    function loadEngagement() {
        fetchJSON(buildEngagementURL()).then(function(data) {
            if (!data) return;
            renderEngKPI(data.kpi);
            renderCategoryBreakdown(data.by_category || []);
            renderEngChart(data.chart);
            renderEngTable(data.table, 0);
            enableSort('engagement-table', data.table, renderEngTable);
            if (data.sponsor_map) updateProductCodeLabels(data.sponsor_map);
        });
    }

    function renderEngKPI(kpi) {
        qs('#kpi-total').textContent = kpi.total_events || 0;
        qs('#kpi-chatbot').textContent = kpi.chatbot_events || 0;
        qs('#kpi-rating').textContent = kpi.rating_events || 0;
        qs('#kpi-simulateur').textContent = kpi.simulateur_events || 0;
        qs('#kpi-sponsor').textContent = kpi.sponsor_events || 0;
        qs('#kpi-sessions').textContent = kpi.unique_sessions || 0;
    }

    function renderCategoryBreakdown(cats) {
        var tbody = qs('#category-tbody');
        if (!tbody) return;
        if (!cats.length) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:1rem">Aucune donnee</td></tr>';
            return;
        }
        var total = 0;
        cats.forEach(function(c) { total += c.events; });
        tbody.innerHTML = cats.map(function(c) {
            var pct = total > 0 ? ((c.events / total) * 100).toFixed(1) + '%' : '0.0%';
            var color = ENG_COLORS[c.category] || 'var(--text)';
            return '<tr>'
                + '<td style="font-weight:700;color:' + color + '">' + escHtml(c.category) + '</td>'
                + '<td>' + c.events + '</td>'
                + '<td>' + c.sessions + '</td>'
                + '<td>' + pct + '</td>'
                + '</tr>';
        }).join('');
    }

    function renderEngChart(chartData) {
        var ctx = qs('#engagement-chart');
        if (!ctx) return;

        var labels = chartData.map(function(r) { return r.day; });
        var cats = ['chatbot', 'rating', 'simulateur', 'sponsor'];
        var catLabels = { chatbot: 'Chatbot', rating: 'Rating', simulateur: 'Simulateur', sponsor: 'Sponsor' };
        var datasets = cats.map(function(cat) {
            return {
                label: catLabels[cat],
                data: chartData.map(function(r) { return r[cat] || 0; }),
                backgroundColor: ENG_COLORS[cat],
                borderColor: ENG_COLORS[cat],
                borderWidth: 1
            };
        });

        if (chart) chart.destroy();
        var cs = getComputedStyle(document.body);
        var tickColor = cs.getPropertyValue('--chart-tick').trim() || '#9ca3af';
        var gridColor = cs.getPropertyValue('--chart-grid').trim() || '#2a2d3a';
        var legendColor = cs.getPropertyValue('--chart-legend').trim() || '#e0e0e0';
        chart = new Chart(ctx, {
            type: 'bar',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                scales: {
                    y: { beginAtZero: true, stacked: true, ticks: { color: tickColor }, grid: { color: gridColor } },
                    x: { stacked: true, ticks: { color: tickColor }, grid: { color: gridColor } }
                },
                plugins: { legend: { labels: { color: legendColor } } }
            }
        });
    }

    function renderEngTable(rows, page) {
        var tbody = qs('#engagement-tbody');
        var start = page * PAGE_SIZE;
        var slice = rows.slice(start, start + PAGE_SIZE);
        tbody.innerHTML = slice.map(function(r) {
            return '<tr><td>' + escHtml(r.day) + '</td><td>' + escHtml(r.event_type) + '</td><td>' + escHtml(r.page) + '</td><td>' + escHtml(r.module) + '</td><td>' + escHtml(r.lang) + '</td><td>' + escHtml(r.device) + '</td><td>' + escHtml(r.country) + '</td><td>' + escHtml(r.product_code || '') + '</td><td>' + escHtml(r.sponsor_name || '') + '</td><td>' + r.cnt + '</td></tr>';
        }).join('');
        renderPagination(rows.length, page, renderEngTable, rows);
    }

    function updateProductCodeLabels(sponsorMap) {
        var select = qs('#f-product-code');
        if (!select) return;
        var options = select.querySelectorAll('option');
        for (var i = 0; i < options.length; i++) {
            var code = options[i].value;
            if (code === 'all') continue;
            var name = sponsorMap[code];
            // Only update slot options (with _A or _B suffix)
            if (name && code.match(/_[AB]$/)) {
                var tier = code.endsWith('_A') ? 'Premium' : 'Standard';
                options[i].textContent = code + ' — ' + name;
            } else if (code.match(/_[AB]$/) && !name) {
                options[i].textContent = code + ' (Vacant)';
            }
        }
    }

    // ══════════════════════════════════════
    // MESSAGES PAGE
    // ══════════════════════════════════════

    var messagesData = [];

    function initMessages() {
        qs('#btn-filter').addEventListener('click', loadMessages);
        qs('#btn-reset').addEventListener('click', function() {
            qs('#f-period').value = 'all';
            qs('#f-sujet').value = 'all';
            qs('#f-lu').value = 'all';
            loadMessages();
        });
        loadMessages();
    }

    function buildMessagesURL() {
        var url = '/admin/api/messages?period=' + qs('#f-period').value;
        var suj = qs('#f-sujet').value;
        if (suj !== 'all') url += '&sujet=' + suj;
        var lu = qs('#f-lu').value;
        if (lu !== 'all') url += '&lu=' + lu;
        return url;
    }

    function loadMessages() {
        fetchJSON(buildMessagesURL()).then(function(data) {
            if (!data) return;
            messagesData = data.table || [];
            renderMessagesKPI(data.summary);
            renderMessagesTable(messagesData, 0);
        });
    }

    function renderMessagesKPI(s) {
        qs('#kpi-total').textContent = s.total || 0;
        qs('#kpi-unread').textContent = s.unread || 0;
        qs('#kpi-today').textContent = s.today || 0;
    }

    function renderMessagesTable(rows, page) {
        var tbody = qs('#messages-tbody');
        var start = page * PAGE_SIZE;
        var slice = rows.slice(start, start + PAGE_SIZE);
        tbody.innerHTML = slice.map(function(r) {
            var bold = r.lu ? '' : 'font-weight:700;';
            var preview = r.message.length > 100 ? r.message.substring(0, 100) + '...' : r.message;
            var sujetBadge = '<span style="padding:2px 8px;border-radius:10px;font-size:0.75rem;background:' +
                ({bug:'#ef4444',suggestion:'#3b82f6',question:'#f59e0b',autre:'#6b7280'}[r.sujet] || '#6b7280') +
                ';color:#fff;">' + escHtml(r.sujet) + '</span>';
            var luIcon = r.lu ? '\u2705' : '\u2709\uFE0F';
            return '<tr style="' + bold + 'cursor:pointer;" data-msg-id="' + parseInt(r.id, 10) + '">' +
                '<td>' + fmtDate(r.created_at) + '</td>' +
                '<td>' + escHtml(r.nom) + '</td>' +
                '<td>' + escHtml(r.email) + '</td>' +
                '<td>' + sujetBadge + '</td>' +
                '<td>' + escHtml(preview) + '</td>' +
                '<td>' + escHtml(r.page_source) + '</td>' +
                '<td>' + escHtml(r.lang) + '</td>' +
                '<td>' + luIcon + '</td>' +
                '<td><button class="btn-secondary btn-msg-toggle" style="padding:2px 8px;font-size:0.75rem;" data-msg-id="' + parseInt(r.id, 10) + '" data-new-lu="' + (r.lu ? '0' : '1') + '">' + (r.lu ? 'Non-lu' : 'Lu') + '</button> <button class="btn-secondary btn-msg-delete" style="padding:2px 8px;font-size:0.75rem;background:#ef4444;border-color:#ef4444;color:#fff;" data-msg-id="' + parseInt(r.id, 10) + '" title="Supprimer">\uD83D\uDDD1\uFE0F</button></td>' +
                '</tr>';
        }).join('');
        // Event delegation — row click → show detail
        tbody.querySelectorAll('tr[data-msg-id]').forEach(function(tr) {
            tr.addEventListener('click', function(e) {
                if (e.target.classList.contains('btn-msg-toggle') || e.target.classList.contains('btn-msg-delete')) return;
                showMsgDetail(parseInt(tr.getAttribute('data-msg-id'), 10));
            });
        });
        // Event delegation — toggle read/unread button
        tbody.querySelectorAll('.btn-msg-toggle').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                toggleRead(parseInt(btn.getAttribute('data-msg-id'), 10), parseInt(btn.getAttribute('data-new-lu'), 10));
            });
        });
        // Event delegation — delete button
        tbody.querySelectorAll('.btn-msg-delete').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                deleteMessage(parseInt(btn.getAttribute('data-msg-id'), 10));
            });
        });
        renderPagination(rows.length, page, renderMessagesTable, rows);
    }

    function showMsgDetail(id) {
        var msg = null;
        for (var i = 0; i < messagesData.length; i++) {
            if (messagesData[i].id === id) { msg = messagesData[i]; break; }
        }
        if (!msg) return;
        var overlay = document.getElementById('msg-detail-overlay');
        document.getElementById('msg-detail-title').textContent = msg.sujet.toUpperCase() + (msg.nom ? ' — ' + msg.nom : '');
        document.getElementById('msg-detail-meta').innerHTML =
            fmtDate(msg.created_at) + ' &bull; ' + escHtml(msg.lang) + ' &bull; ' + escHtml(msg.page_source || 'N/A') +
            (msg.email ? ' &bull; <a href="mailto:' + escHtml(msg.email) + '" style="color:#3b82f6;">' + escHtml(msg.email) + '</a>' : '');
        document.getElementById('msg-detail-body').textContent = msg.message;
        var btn = document.getElementById('msg-detail-toggle');
        btn.textContent = msg.lu ? 'Marquer non-lu' : 'Marquer comme lu';
        btn.onclick = function() { toggleRead(id, msg.lu ? 0 : 1); overlay.style.display = 'none'; };
        overlay.style.display = 'flex';

        // Auto mark as read
        if (!msg.lu) toggleRead(id, 1);
    }

    function toggleRead(id, newLu) {
        var action = newLu ? 'read' : 'unread';
        fetch('/admin/api/messages/' + id + '/' + action, { method: 'POST', credentials: 'same-origin' })
            .then(function() { loadMessages(); });
    }

    function deleteMessage(id) {
        if (!confirm('Supprimer ce message ?')) return;
        fetch('/admin/api/messages/' + id, { method: 'DELETE', credentials: 'same-origin' })
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (d && d.status === 'ok') loadMessages();
            });
    }

    // ══════════════════════════════════════
    // CHATBOT MONITOR PAGE (V44)
    // ══════════════════════════════════════

    var cmTimer = null;
    var cmData = [];

    var CM_PHASE_COLORS = {
        'I': '#ef4444', 'C': '#10b981', 'R': '#f59e0b', 'G': '#3b82f6',
        'A': '#ef4444', 'GEO': '#06b6d4', '0': '#8b8b9e', '0-bis': '#8b8b9e',
        'T': '#6366f1', '2': '#a855f7', '3': '#d4a843', '3-bis': '#d4a843',
        'P+': '#ec4899', 'P': '#ec4899', 'OOR': '#ef4444', '1': '#4f8cff',
        'SQL': '#f59e0b', 'Gemini': '#10b981', 'unknown': '#8b8b9e'
    };

    var CM_STATUS_COLORS = {
        'OK': '#10b981', 'EMPTY': '#f59e0b', 'NO_SQL': '#8b8b9e',
        'REJECTED': '#ef4444', 'ERROR': '#ef4444', 'N/A': '#8b8b9e'
    };

    function initChatbotMonitor() {
        qs('#cm-btn-filter').addEventListener('click', loadChatbotLog);
        qs('#cm-btn-reset').addEventListener('click', function() {
            qs('#cm-period').value = '24h';
            qs('#cm-module').value = 'all';
            qs('#cm-phase').value = 'all';
            qs('#cm-status').value = 'all';
            qs('#cm-lang').value = 'all';
            qs('#cm-errors-only').checked = false;
            loadChatbotLog();
        });
        qs('#cm-auto').addEventListener('change', function() {
            if (this.checked) { cmStartAuto(); } else { cmStopAuto(); }
        });
        loadChatbotLog();
        cmStartAuto();
        cmUpdateExportLink();
    }

    function cmStartAuto() {
        cmStopAuto();
        cmTimer = setInterval(loadChatbotLog, 10000);
    }

    function cmStopAuto() {
        if (cmTimer) { clearInterval(cmTimer); cmTimer = null; }
    }

    function cmBuildParams() {
        var p = 'period=' + qs('#cm-period').value;
        p += '&module=' + qs('#cm-module').value;
        p += '&phase=' + qs('#cm-phase').value;
        p += '&status=' + qs('#cm-status').value;
        p += '&lang=' + qs('#cm-lang').value;
        if (qs('#cm-errors-only').checked) p += '&errors_only=true';
        return p;
    }

    function cmUpdateExportLink() {
        var el = qs('#cm-export-csv');
        if (el) el.href = '/admin/export/chatbot-log/csv?' + cmBuildParams();
    }

    function loadChatbotLog() {
        cmUpdateExportLink();
        fetchJSON('/admin/api/chatbot-log?' + cmBuildParams()).then(function(data) {
            if (!data) return;
            cmData = data.exchanges || [];
            renderCmKPI(data.kpi);
            renderCmTable(cmData, 0);
        });
    }

    function renderCmKPI(kpi) {
        qs('#cm-kpi-total').textContent = kpi.total || 0;
        qs('#cm-kpi-rejected').textContent = (kpi.rejected_pct || 0) + '%';
        qs('#cm-kpi-errors').textContent = (kpi.error_pct || 0) + '%';
        qs('#cm-kpi-duration').textContent = kpi.avg_duration || 0;
        qs('#cm-kpi-sessions').textContent = kpi.unique_sessions || 0;
        qs('#cm-kpi-sql').textContent = kpi.sql_count || 0;
    }

    function cmPhaseBadge(phase) {
        var color = CM_PHASE_COLORS[phase] || '#8b8b9e';
        return '<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:.72rem;font-weight:700;background:' + color + '22;color:' + color + ';">' + escHtml(phase) + '</span>';
    }

    function cmStatusBadge(status) {
        var color = CM_STATUS_COLORS[status] || '#8b8b9e';
        return '<span style="display:inline-block;padding:2px 6px;border-radius:10px;font-size:.7rem;font-weight:700;background:' + color + '22;color:' + color + ';">' + escHtml(status) + '</span>';
    }

    function cmRowClass(r) {
        if (r.is_error || r.sql_status === 'REJECTED' || r.sql_status === 'ERROR') return 'background:rgba(239,68,68,0.08);';
        if (r.sql_status === 'EMPTY' || r.sql_status === 'NO_SQL' || r.duration_ms > 3000) return 'background:rgba(245,158,11,0.08);';
        return '';
    }

    function renderCmTable(rows, page) {
        var tbody = qs('#cm-tbody');
        var start = page * PAGE_SIZE;
        var slice = rows.slice(start, start + PAGE_SIZE);
        if (!slice.length) {
            tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:1.5rem;">Aucun echange</td></tr>';
            renderPagination(0, 0, renderCmTable, rows);
            return;
        }
        tbody.innerHTML = slice.map(function(r) {
            var moduleBadge = r.module === 'loto'
                ? '<span style="padding:2px 6px;border-radius:10px;font-size:.7rem;font-weight:700;background:rgba(79,140,255,0.15);color:#4f8cff;">LOTO</span>'
                : '<span style="padding:2px 6px;border-radius:10px;font-size:.7rem;font-weight:700;background:rgba(212,168,67,0.15);color:#d4a843;">EM</span>';
            var question = r.question.length > 80 ? r.question.substring(0, 80) + '...' : r.question;
            var sqlPreview = r.sql_generated ? (r.sql_generated.length > 60 ? r.sql_generated.substring(0, 60) + '...' : r.sql_generated) : '';
            var sqlCell = r.phase === 'SQL' ? (escHtml(sqlPreview) + ' ' + cmStatusBadge(r.sql_status)) : '<span style="color:var(--text-muted);">-</span>';
            var responsePreview = r.response_preview ? (r.response_preview.length > 100 ? r.response_preview.substring(0, 100) + '...' : r.response_preview) : '';
            var durStyle = r.duration_ms > 3000 ? 'color:#ef4444;font-weight:700;' : '';
            var statusIcon = r.is_error ? '\u274C' : (r.sql_status === 'REJECTED' ? '\u26A0\uFE0F' : '\u2705');
            return '<tr style="cursor:pointer;' + cmRowClass(r) + '" data-cm-id="' + r.id + '">'
                + '<td>' + fmtDate(r.created_at) + '</td>'
                + '<td>' + moduleBadge + '</td>'
                + '<td>' + escHtml(r.lang) + '</td>'
                + '<td>' + cmPhaseBadge(r.phase) + '</td>'
                + '<td>' + escHtml(question) + '</td>'
                + '<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;">' + sqlCell + '</td>'
                + '<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;">' + escHtml(responsePreview) + '</td>'
                + '<td style="' + durStyle + '">' + r.duration_ms + 'ms</td>'
                + '<td>' + statusIcon + '</td>'
                + '</tr>';
        }).join('');
        // Row click → detail
        tbody.querySelectorAll('tr[data-cm-id]').forEach(function(tr) {
            tr.addEventListener('click', function() {
                showCmDetail(parseInt(tr.getAttribute('data-cm-id'), 10));
            });
        });
        renderPagination(rows.length, page, renderCmTable, rows);
    }

    function showCmDetail(id) {
        var r = null;
        for (var i = 0; i < cmData.length; i++) {
            if (cmData[i].id === id) { r = cmData[i]; break; }
        }
        if (!r) return;
        var overlay = document.getElementById('cm-detail-overlay');
        document.getElementById('cm-detail-title').textContent =
            r.module.toUpperCase() + ' | Phase ' + r.phase + ' | ' + r.lang.toUpperCase();
        var html = '<div style="margin-bottom:12px;">'
            + '<b style="color:var(--accent);">Date:</b> ' + fmtDate(r.created_at)
            + ' &bull; <b style="color:var(--accent);">Duree:</b> ' + r.duration_ms + 'ms'
            + ' &bull; <b style="color:var(--accent);">Session:</b> ' + escHtml(r.session_hash)
            + '</div>';
        html += '<div style="margin-bottom:12px;"><b style="color:var(--accent);">Question:</b><div style="white-space:pre-wrap;background:var(--bg-card-alt);padding:8px;border-radius:6px;margin-top:4px;">' + escHtml(r.question) + '</div></div>';
        if (r.sql_generated) {
            html += '<div style="margin-bottom:12px;"><b style="color:var(--accent);">SQL:</b> ' + cmStatusBadge(r.sql_status) + '<div style="white-space:pre-wrap;background:var(--bg-card-alt);padding:8px;border-radius:6px;margin-top:4px;font-family:monospace;font-size:.8rem;">' + escHtml(r.sql_generated) + '</div></div>';
        }
        if (r.response_preview) {
            html += '<div style="margin-bottom:12px;"><b style="color:var(--accent);">Reponse (preview):</b><div style="white-space:pre-wrap;background:var(--bg-card-alt);padding:8px;border-radius:6px;margin-top:4px;">' + escHtml(r.response_preview) + '</div></div>';
        }
        if (r.is_error && r.error_detail) {
            html += '<div style="margin-bottom:12px;padding:8px;background:rgba(239,68,68,0.1);border-radius:6px;border:1px solid rgba(239,68,68,0.2);"><b style="color:#ef4444;">Erreur:</b> ' + escHtml(r.error_detail) + '</div>';
        }
        var meta = [];
        if (r.tokens_in) meta.push('Gemini tokens in: ' + r.tokens_in);
        if (r.tokens_out) meta.push('Gemini tokens out: ' + r.tokens_out);
        if (r.grid_count) meta.push('Grilles: ' + r.grid_count);
        if (r.has_exclusions) meta.push('Exclusions: oui');
        if (meta.length) {
            html += '<div style="font-size:.8rem;color:var(--text-muted);">' + meta.join(' &bull; ') + '</div>';
        }
        document.getElementById('cm-detail-body').innerHTML = html;
        overlay.style.display = 'flex';
    }

    // ── Dashboard hard-refresh ──

    function initDashboard() {
        var btn = document.getElementById('btn-hard-refresh');
        if (!btn) return;
        btn.addEventListener('click', function() {
            var icon = btn.querySelector('.hard-refresh-icon');
            if (icon) icon.classList.add('spinning');
            setTimeout(function() {
                var url = location.href.split('?')[0];
                location.href = url + '?_r=' + Date.now();
            }, 500);
        });
    }

    // ── Calendar heatmap ── (migrated from inline calendar.html — F11 V91)

    function initCalendar() {
        var MONTHS_FR = ['Janvier','Fevrier','Mars','Avril','Mai','Juin',
                         'Juillet','Aout','Septembre','Octobre','Novembre','Decembre'];

        var now = new Date();
        var state = {
            year: now.getFullYear(),
            month: now.getMonth() + 1,
            data: null,
            metric: 'visitors'
        };

        var grid = document.getElementById('cal-grid');
        var labelEl = document.getElementById('cal-month-label');
        var tooltip = document.getElementById('cal-tooltip');
        var metricSelect = document.getElementById('cal-metric');

        if (!grid || !labelEl) return; // guard: not on calendar page

        // ── Fetch data ──
        function fetchData() {
            labelEl.textContent = MONTHS_FR[state.month - 1] + ' ' + state.year;
            fetchJSON('/admin/api/calendar-data?year=' + state.year + '&month=' + state.month)
                .then(function(d) {
                    if (!d) return;
                    state.data = d;
                    render();
                });
        }

        // ── Quantile levels ──
        function calcLevels(days, metric) {
            var vals = [];
            for (var k in days) {
                var v = days[k][metric];
                if (v > 0) vals.push(v);
            }
            if (vals.length === 0) return function() { return 0; };
            vals.sort(function(a, b) { return a - b; });
            var q1 = vals[Math.floor(vals.length * 0.25)] || vals[0];
            var q2 = vals[Math.floor(vals.length * 0.50)] || vals[0];
            var q3 = vals[Math.floor(vals.length * 0.75)] || vals[0];
            return function(v) {
                if (v <= 0) return 0;
                if (v <= q1) return 1;
                if (v <= q2) return 2;
                if (v <= q3) return 3;
                return 4;
            };
        }

        // ── Render calendar ──
        function render() {
            if (!state.data) return;

            var old = grid.querySelectorAll('.cal-day');
            for (var i = 0; i < old.length; i++) old[i].remove();

            var days = state.data.days;
            var metric = state.metric;
            var getLevel = calcLevels(days, metric);

            var firstDate = new Date(state.year, state.month - 1, 1);
            var startDow = (firstDate.getDay() + 6) % 7;

            var numDays = Object.keys(days).length;

            var todayNow = new Date();
            var isCurrentMonth = (state.year === todayNow.getFullYear() && state.month === todayNow.getMonth() + 1);
            var todayDay = todayNow.getDate();

            for (var e = 0; e < startDow; e++) {
                var empty = document.createElement('div');
                empty.className = 'cal-day empty';
                grid.appendChild(empty);
            }

            for (var d = 1; d <= numDays; d++) {
                var dayData = days[String(d)];
                var val = dayData ? dayData[metric] : 0;
                var level = getLevel(val);

                var cell = document.createElement('div');
                cell.className = 'cal-day cal-level-' + level;
                if (isCurrentMonth && d === todayDay) {
                    cell.className += ' cal-today';
                }

                var numSpan = document.createElement('span');
                numSpan.className = 'cal-day-num';
                numSpan.textContent = d;

                var valSpan = document.createElement('span');
                valSpan.className = 'cal-day-val';
                valSpan.textContent = val;

                cell.appendChild(numSpan);
                cell.appendChild(valSpan);

                cell._dayData = dayData;
                cell._dayNum = d;

                cell.addEventListener('mouseenter', showTooltip);
                cell.addEventListener('mouseleave', hideTooltip);

                grid.appendChild(cell);
            }

            var totalCells = startDow + numDays;
            var trailing = totalCells % 7;
            if (trailing > 0) {
                for (var t = 0; t < 7 - trailing; t++) {
                    var emptyEnd = document.createElement('div');
                    emptyEnd.className = 'cal-day empty';
                    grid.appendChild(emptyEnd);
                }
            }
        }

        // ── Tooltip ──
        function showTooltip(ev) {
            var cell = ev.currentTarget;
            var dd = cell._dayData;
            if (!dd) return;
            tooltip.innerHTML =
                '<strong>' + cell._dayNum + ' ' + MONTHS_FR[state.month - 1] + ' ' + state.year + '</strong><br>' +
                'Visiteurs: <b>' + dd.visitors + '</b><br>' +
                'Sessions: <b>' + dd.sessions + '</b><br>' +
                'Impressions: <b>' + dd.impressions + '</b><br>' +
                'Chatbot: <b>' + dd.chatbot + '</b>';
            tooltip.style.display = 'block';

            var rect = cell.getBoundingClientRect();
            tooltip.style.left = rect.left + 'px';
            tooltip.style.top = (rect.bottom + 6) + 'px';
        }

        function hideTooltip() {
            tooltip.style.display = 'none';
        }

        // ── Navigation ──
        document.getElementById('cal-prev').addEventListener('click', function() {
            state.month--;
            if (state.month < 1) { state.month = 12; state.year--; }
            fetchData();
        });

        document.getElementById('cal-next').addEventListener('click', function() {
            state.month++;
            if (state.month > 12) { state.month = 1; state.year++; }
            fetchData();
        });

        metricSelect.addEventListener('change', function() {
            state.metric = this.value;
            render();
        });

        // ── Init ──
        fetchData();
    }

    return {
        initImpressions: initImpressions,
        initVotes: initVotes,
        initRealtime: initRealtime,
        initEngagement: initEngagement,
        initMessages: initMessages,
        initChatbotMonitor: initChatbotMonitor,
        initDashboard: initDashboard,
        initCalendar: initCalendar
    };
})();
