/* ==============================================================
   Rating Banner — All LotoIA EN pages
   Trigger: 1m30 cumulated SESSION (not per page)
   Guard: hidden if already rated (chatbot OR popup)
   Design: small discreet banner at bottom, no blocking overlay
   ============================================================== */

(function () {
    'use strict';

    var SESSION_START_KEY = 'lotoia_session_start';
    var DELAY_MS = 90000; // 1m30

    // -- Guard: already rated via any channel? --
    function hasAlreadyRated() {
        return sessionStorage.getItem('lotoia_rated_popup_accueil')
            || sessionStorage.getItem('lotoia_rated_chatbot_loto')
            || sessionStorage.getItem('lotoia_rated_chatbot_em');
    }

    if (hasAlreadyRated()) return;

    // -- Global session timer (survives navigation between pages) --
    var sessionStart = sessionStorage.getItem(SESSION_START_KEY);
    if (!sessionStart) {
        sessionStart = String(Date.now());
        sessionStorage.setItem(SESSION_START_KEY, sessionStart);
    }

    var elapsed = Date.now() - parseInt(sessionStart, 10);
    var remaining = DELAY_MS - elapsed;

    if (remaining <= 0) {
        onReady(showBanner);
    } else {
        setTimeout(function () {
            if (!hasAlreadyRated()) showBanner();
        }, remaining);
    }

    function onReady(fn) {
        if (document.readyState !== 'loading') { fn(); }
        else { document.addEventListener('DOMContentLoaded', fn); }
    }

    function showBanner() {
        if (hasAlreadyRated()) return;
        if (document.getElementById('rating-banner')) return;

        var banner = document.createElement('div');
        banner.id = 'rating-banner';

        // Text
        var text = document.createElement('span');
        text.className = 'rating-banner-text';
        text.textContent = 'Rate LotoIA?';
        banner.appendChild(text);

        // Stars
        var starsDiv = document.createElement('span');
        starsDiv.className = 'rating-banner-stars';
        starsDiv.id = 'banner-rating-stars';

        for (var i = 1; i <= 5; i++) {
            var star = document.createElement('span');
            star.className = 'banner-star';
            star.setAttribute('data-value', String(i));
            star.textContent = '\u2605';
            (function (val) {
                star.addEventListener('mouseover', function () {
                    var all = document.querySelectorAll('#banner-rating-stars .banner-star');
                    for (var j = 0; j < all.length; j++) {
                        if (j < val) { all[j].classList.add('active'); }
                        else { all[j].classList.remove('active'); }
                    }
                });
                star.addEventListener('click', function () { submitBannerRating(val); });
            })(i);
            starsDiv.appendChild(star);
        }

        starsDiv.addEventListener('mouseleave', function () {
            var selected = document.querySelector('#banner-rating-stars .banner-star.selected');
            if (selected) return;
            var all = document.querySelectorAll('#banner-rating-stars .banner-star');
            for (var j = 0; j < all.length; j++) { all[j].classList.remove('active'); }
        });

        banner.appendChild(starsDiv);

        // Feedback (hidden by default)
        var feedback = document.createElement('span');
        feedback.className = 'rating-banner-feedback';
        feedback.id = 'banner-rating-feedback';
        banner.appendChild(feedback);

        // Close button
        var closeBtn = document.createElement('button');
        closeBtn.className = 'rating-banner-close';
        closeBtn.setAttribute('aria-label', 'Close');
        closeBtn.textContent = '\u2715';
        closeBtn.addEventListener('click', function () {
            var ratingModule = window.location.pathname.indexOf('/euromillions/') !== -1 ? 'euromillions' : 'loto';
            if (typeof umami !== 'undefined') umami.track('rating-dismissed', { module: ratingModule });
            banner.classList.add('rating-banner-hide');
            setTimeout(function () { banner.remove(); }, 300);
        });
        banner.appendChild(closeBtn);

        document.body.appendChild(banner);

        // Umami tracking
        var ratingModule = window.location.pathname.indexOf('/euromillions/') !== -1 ? 'euromillions' : 'loto';
        if (typeof umami !== 'undefined') umami.track('rating-popup-shown', { module: ratingModule });
    }

    function submitBannerRating(rating) {
        // Highlight
        var all = document.querySelectorAll('#banner-rating-stars .banner-star');
        for (var j = 0; j < all.length; j++) {
            if (j < rating) {
                all[j].classList.add('selected');
                all[j].classList.add('active');
            } else {
                all[j].classList.remove('selected');
                all[j].classList.remove('active');
            }
        }

        var sessionId = sessionStorage.getItem('hybride_session_id')
            || ('sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9));
        sessionStorage.setItem('hybride_session_id', sessionId);

        var ratingModule = window.location.pathname.indexOf('/euromillions/') !== -1 ? 'euromillions' : 'loto';
        if (typeof umami !== 'undefined') umami.track('rating-submitted', { rating: rating, module: ratingModule });

        fetch('/api/rating', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source: 'popup_accueil',
                rating: rating,
                session_id: sessionId,
                page: window.location.pathname
            })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.success) {
                sessionStorage.setItem('lotoia_rated_popup_accueil', 'true');
                var feedback = document.getElementById('banner-rating-feedback');
                if (feedback) feedback.textContent = 'Thanks!';
                var banner = document.getElementById('rating-banner');
                setTimeout(function () {
                    if (banner) {
                        banner.classList.add('rating-banner-hide');
                        setTimeout(function () { banner.remove(); }, 300);
                    }
                }, 2000);
            }
        })
        .catch(function () { /* silent */ });
    }

})();
