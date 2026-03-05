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
            qs('#f-period').value = '7d';
            qs('#f-event').value = 'all';
            qs('#f-lang').value = 'all';
            qs('#f-device').value = 'all';
            toggleCustomDates();
            loadImpressions();
        });
        loadImpressions();
    }

    function buildImpressionsURL() {
        var p = qs('#f-period').value;
        var url = '/admin/api/impressions?period=' + p;
        if (p === 'custom') {
            url += '&date_start=' + (qs('#f-date-start').value || '');
            url += '&date_end=' + (qs('#f-date-end').value || '');
        }
        var ev = qs('#f-event').value;
        if (ev !== 'all') url += '&event_type=' + ev;
        var lang = qs('#f-lang').value;
        if (lang !== 'all') url += '&lang=' + lang;
        var dev = qs('#f-device').value;
        if (dev !== 'all') url += '&device=' + dev;
        return url;
    }

    function loadImpressions() {
        fetchJSON(buildImpressionsURL()).then(function(data) {
            if (!data) return;
            renderImpKPI(data.kpi);
            renderImpChart(data.chart);
            renderImpTable(data.table, 0);
            enableSort('impressions-table', data.table, renderImpTable);
        });
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

        var types = { 'sponsor-popup-shown': { label: 'Impressions', color: '#3b82f6' }, 'sponsor-click': { label: 'Clics', color: '#10b981' }, 'sponsor-video-played': { label: 'Videos', color: '#f59e0b' } };
        var datasets = [];
        Object.keys(types).forEach(function(evType) {
            var vals = labels.map(function(d) {
                var row = chartData.find(function(r) { return r.day === d && r.event_type === evType; });
                return row ? row.cnt : 0;
            });
            datasets.push({ label: types[evType].label, data: vals, backgroundColor: types[evType].color, borderColor: types[evType].color, borderWidth: 1 });
        });

        if (chart) chart.destroy();
        chart = new Chart(ctx, {
            type: 'bar',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                scales: { y: { beginAtZero: true, ticks: { color: '#9ca3af' }, grid: { color: '#2a2d3a' } }, x: { ticks: { color: '#9ca3af' }, grid: { color: '#2a2d3a' } } },
                plugins: { legend: { labels: { color: '#e0e0e0' } } }
            }
        });
    }

    function renderImpTable(rows, page) {
        var tbody = qs('#impressions-tbody');
        var start = page * PAGE_SIZE;
        var slice = rows.slice(start, start + PAGE_SIZE);
        tbody.innerHTML = slice.map(function(r) {
            return '<tr><td>' + escHtml(r.day) + '</td><td>' + escHtml(r.event_type) + '</td><td>' + escHtml(r.page) + '</td><td>' + escHtml(r.lang) + '</td><td>' + escHtml(r.device) + '</td><td>' + escHtml(r.country) + '</td><td>' + r.cnt + '</td></tr>';
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

    return { initImpressions: initImpressions, initVotes: initVotes };
})();
