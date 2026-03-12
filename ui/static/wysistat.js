/**
 * Wysistat analytics — ACPM-labelled, CNIL-exempt.
 * Owner IP filtered via window.__OWNER__ (set by UmamiOwnerFilterMiddleware).
 * ws.jsa expects a global `isOwner` variable — bridge it from __OWNER__.
 */
(function () {
    window.isOwner = !!window.__OWNER__;
    if (window.__OWNER__) return;

    var _wsq = window._wsq = window._wsq || [];
    _wsq.push(['_setNom', 'lotoia']);
    _wsq.push(['_setToken', 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJhY2NvdW50TmFtZSI6ImxvdG9pYSIsIm5hbWUiOiJsb3RvaWEtcHJvZCJ9.IzXT4dwmGHqqHMx7ir8SKxbBPwb_JrkTBEV1DVh5NZ4']);
    _wsq.push(['_wysistat']);

    var ws = document.createElement('script');
    ws.type = 'text/javascript';
    ws.async = true;
    ws.src = 'https://www.wysistat.com/ws.jsa';
    var s = document.getElementsByTagName('script')[0] || document.getElementsByTagName('body')[0];
    s.parentNode.insertBefore(ws, s);
})();
