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
            return '<tr><td>' + escHtml(r.created_at) + '</td><td>' + escHtml(r.source) + '</td><td>' + stars(r.rating) + '</td><td>' + escHtml(r.comment || '') + '</td><td>' + escHtml(r.page) + '</td></tr>';
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
                + '<span class="rt-event-time">' + escHtml(e.created_at) + '</span>'
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
        events.forEach(function(e) {
            if (!e.created_at) return;
            var parts = e.created_at.split(':');
            if (parts.length < 3) return;
            var now = new Date();
            var evDate = new Date();
            evDate.setHours(parseInt(parts[0]), parseInt(parts[1]), parseInt(parts[2]), 0);
            var diffMin = Math.floor((now - evDate) / 60000);
            if (diffMin >= 0 && diffMin < 60) counts[diffMin]++;
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

    return { initImpressions: initImpressions, initVotes: initVotes, initRealtime: initRealtime, initEngagement: initEngagement };
})();
