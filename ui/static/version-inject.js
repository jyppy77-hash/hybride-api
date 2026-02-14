/**
 * LotoIA — Injection dynamique de la version depuis /api/version
 * Met a jour tous les <span class="app-version"> du DOM.
 */
(function () {
    fetch('/api/version')
        .then(function (r) { return r.json(); })
        .then(function (d) {
            if (!d || !d.version) return;
            var spans = document.querySelectorAll('.app-version');
            for (var i = 0; i < spans.length; i++) {
                spans[i].textContent = 'v' + d.version;
            }
        })
        .catch(function () { /* fallback: garde la valeur statique */ });
})();
