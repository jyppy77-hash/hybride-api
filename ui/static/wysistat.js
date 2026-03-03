/**
 * Wysistat analytics — ACPM-labelled, CNIL-exempt.
 * Owner IP filtered via window.__OWNER__ (set by UmamiOwnerFilterMiddleware).
 */
(function () {
    if (window.__OWNER__) return;

    var _wsq = window._wsq = window._wsq || [];
    _wsq.push(['_setNom', 'lotoia']);
    _wsq.push(['_wysistat']);

    var ws = document.createElement('script');
    ws.type = 'text/javascript';
    ws.async = true;
    ws.src = 'https://www.wysistat.com/ws.jsa';
    var s = document.getElementsByTagName('script')[0] || document.getElementsByTagName('body')[0];
    s.parentNode.insertBefore(ws, s);
})();
