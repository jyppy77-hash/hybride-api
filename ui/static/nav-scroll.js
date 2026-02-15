/* Auto-scroll du menu nav vers le bouton actif (mobile < 599px)
   Fonctionne pour .loto-hero-actions (sous-pages) et .hero-actions (accueil) */
(function () {
    var container = document.querySelector('.loto-hero-actions') || document.querySelector('.hero-actions');
    if (!container) return;
    var active = container.querySelector('.loto-hero-btn-active');
    if (!active) return;
    var cl = container.offsetWidth;
    var al = active.offsetLeft;
    var aw = active.offsetWidth;
    container.scrollLeft = al - (cl / 2) + (aw / 2);
})();
