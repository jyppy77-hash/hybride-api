/* ══════════════════════════════════════════════════════════════
   Bandeau Notation — Toutes pages LotoIA
   Declencheur : 1m30 de SESSION cumulee (pas par page)
   Guard : ne s'affiche pas si deja vote (chatbot OU popup)
   Design : petit bandeau discret en bas, pas d'overlay bloquant
   V2 : textarea commentaire optionnel apres selection etoile
   ══════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    var LI = window.LotoIA_i18n || {};
    var SESSION_START_KEY = 'lotoia_session_start';
    var DELAY_MS = 90000; // 1m30

    // ── Guard : deja vote via n'importe quel canal ? ──
    function hasAlreadyRated() {
        return sessionStorage.getItem('lotoia_rated_popup_accueil')
            || sessionStorage.getItem('lotoia_rated_popup_em')
            || sessionStorage.getItem('lotoia_rated_chatbot_loto')
            || sessionStorage.getItem('lotoia_rated_chatbot_em')
                || sessionStorage.getItem('lotoia_dismissed_rating')
            || sessionStorage.getItem('lotoia_rating_banner_shown');
    }

    if (hasAlreadyRated()) return;

    // ── Timer session global (survit a la navigation entre pages) ──
    var sessionStart = sessionStorage.getItem(SESSION_START_KEY);
    if (!sessionStart) {
        sessionStart = String(Date.now());
        sessionStorage.setItem(SESSION_START_KEY, sessionStart);
    }

    var elapsed = Date.now() - parseInt(sessionStart, 10);
    var remaining = DELAY_MS - elapsed;

    if (remaining <= 0) {
        // Deja 1m30+ de session : afficher au prochain idle
        onReady(showBanner);
    } else {
        // Attendre le temps restant
        setTimeout(function () {
            if (!hasAlreadyRated()) showBanner();
        }, remaining);
    }

    function onReady(fn) {
        if (document.readyState !== 'loading') { fn(); }
        else { document.addEventListener('DOMContentLoaded', fn); }
    }

    var selectedRating = 0;

    function showBanner() {
        // Double-check (le vote a pu arriver entre-temps via chatbot)
        if (hasAlreadyRated()) return;
        if (document.getElementById('rating-banner')) return;

        // Marquer comme affiché — empêche le ré-affichage sur les pages suivantes
        sessionStorage.setItem('lotoia_rating_banner_shown', '1');

        var banner = document.createElement('div');
        banner.id = 'rating-banner';

        // Texte
        var text = document.createElement('span');
        text.className = 'rating-banner-text';
        text.textContent = LI.rating_prompt || 'Votre avis sur LotoIA ?';
        banner.appendChild(text);

        // Etoiles
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
                    if (selectedRating) return;
                    var all = document.querySelectorAll('#banner-rating-stars .banner-star');
                    for (var j = 0; j < all.length; j++) {
                        if (j < val) { all[j].classList.add('active'); }
                        else { all[j].classList.remove('active'); }
                    }
                });
                star.addEventListener('click', function () { selectRating(val); });
            })(i);
            starsDiv.appendChild(star);
        }

        starsDiv.addEventListener('mouseleave', function () {
            if (selectedRating) return;
            var all = document.querySelectorAll('#banner-rating-stars .banner-star');
            for (var j = 0; j < all.length; j++) { all[j].classList.remove('active'); }
        });

        banner.appendChild(starsDiv);

        // Feedback (cache par defaut)
        var feedback = document.createElement('span');
        feedback.className = 'rating-banner-feedback';
        feedback.id = 'banner-rating-feedback';
        banner.appendChild(feedback);

        // Bouton fermer
        var closeBtn = document.createElement('button');
        closeBtn.className = 'rating-banner-close';
        closeBtn.setAttribute('aria-label', LI.rating_close || 'Fermer');
        closeBtn.textContent = '\u2715';
        closeBtn.addEventListener('click', function () {
            var ratingModule = window.location.pathname.indexOf('/euromillions/') !== -1 ? 'euromillions' : 'loto';
            if (window.LotoIA_track) LotoIA_track('rating-dismissed', {module: ratingModule});
            if (window.LotoIAAnalytics) window.LotoIAAnalytics.track('rating_dismissed', { event_category: 'engagement', module: ratingModule });
            sessionStorage.setItem('lotoia_dismissed_rating', 'true');
            banner.classList.add('rating-banner-hide');
            setTimeout(function () { banner.remove(); }, 300);
        });
        banner.appendChild(closeBtn);

        document.body.appendChild(banner);

        var ratingModule = window.location.pathname.indexOf('/euromillions/') !== -1 ? 'euromillions' : 'loto';
        if (window.LotoIA_track) LotoIA_track('rating-popup-shown', {module: ratingModule});
        if (window.LotoIAAnalytics) window.LotoIAAnalytics.track('rating_popup_shown', { event_category: 'engagement', module: ratingModule });
    }

    function selectRating(rating) {
        // V141 A.4 UX Fix 1 \u2014 3 tiers : low (1-2) obligatoire 20 chars, mid (3) / high (4-5) optionnel
        selectedRating = rating;

        // Highlight selected stars
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

        var banner = document.getElementById('rating-banner');
        if (!banner) return;

        // V141 A.4 UX Fix 1 \u2014 recr\u00e9er la section pour adapter au tier
        var oldSection = document.getElementById('rating-comment-section');
        if (oldSection) oldSection.remove();

        buildCommentSection(rating);
    }

    function buildCommentSection(rating) {
        // V141 A.4 UX Fix 1 \u2014 popup 3 tiers (low 1-2 obligatoire / mid 3 / high 4-5 optionnel)
        var banner = document.getElementById('rating-banner');
        if (!banner) return;

        var tier = rating <= 2 ? 'low' : (rating === 3 ? 'mid' : 'high');
        var isMandatory = (tier === 'low');
        var MIN_CHARS = 20;

        var section = document.createElement('div');
        section.id = 'rating-comment-section';
        section.className = 'rating-comment-section rating-comment-tier-' + tier;

        // Prompt par tier
        var prompt = document.createElement('div');
        prompt.className = 'rating-comment-prompt';
        if (tier === 'low') {
            prompt.textContent = LI.rating_prompt_low || 'Qu\'est-ce qui n\'a pas march\u00e9 ?';
        } else if (tier === 'mid') {
            prompt.textContent = LI.rating_prompt_mid || 'Une suggestion pour qu\'on s\'am\u00e9liore ? (optionnel)';
        } else {
            prompt.textContent = LI.rating_prompt_high || 'Un mot pour nous faire plaisir ? (optionnel) \ud83e\udd29';
        }
        section.appendChild(prompt);

        var textarea = document.createElement('textarea');
        textarea.id = 'rating-comment-input';
        textarea.className = 'rating-comment-input';
        textarea.maxLength = 500;
        textarea.rows = 2;
        section.appendChild(textarea);

        // Erreur inline (LOW only)
        var errorMsg = null;
        if (isMandatory) {
            errorMsg = document.createElement('div');
            errorMsg.className = 'rating-comment-error';
            errorMsg.textContent = LI.rating_min_chars || 'Min. 20 caract\u00e8res s\'il te pla\u00eet \ud83d\ude0a';
            section.appendChild(errorMsg);
        }

        var footer = document.createElement('div');
        footer.className = 'rating-comment-footer';

        var counter = document.createElement('span');
        counter.className = 'rating-comment-counter';
        if (isMandatory) counter.classList.add('too-short');
        counter.textContent = (LI.rating_comment_counter || '{n} / 500').replace('{n}', '0');

        var submitted = false;
        var btnGroup = document.createElement('span');
        btnGroup.className = 'rating-comment-buttons';

        // Passer button (MID/HIGH only \u2014 envoie sans commentaire)
        if (!isMandatory) {
            var skipBtn = document.createElement('button');
            skipBtn.className = 'rating-comment-skip';
            skipBtn.textContent = LI.rating_skip || 'Passer';
            skipBtn.addEventListener('click', function () {
                if (submitted) return;
                submitted = true;
                skipBtn.disabled = true;
                submitBannerRating(rating, '');
            });
            btnGroup.appendChild(skipBtn);
        }

        var submitBtn = document.createElement('button');
        submitBtn.className = 'rating-comment-submit';
        submitBtn.textContent = LI.rating_submit || 'Envoyer';
        if (isMandatory) submitBtn.disabled = true;
        submitBtn.addEventListener('click', function () {
            if (submitted) return;
            var comment = textarea.value.trim();
            if (isMandatory && comment.length < MIN_CHARS) {
                if (errorMsg) errorMsg.classList.add('visible');
                textarea.classList.add('has-error');
                try { textarea.focus(); } catch (e) { /* ignore */ }
                return;
            }
            submitted = true;
            submitBtn.disabled = true;
            submitBannerRating(rating, comment.substring(0, 500));
        });
        btnGroup.appendChild(submitBtn);

        footer.appendChild(counter);
        footer.appendChild(btnGroup);
        section.appendChild(footer);

        // Textarea input \u2014 compteur \u00e9volutif
        textarea.addEventListener('input', function () {
            var n = textarea.value.length;
            counter.textContent = (LI.rating_comment_counter || '{n} / 500').replace('{n}', String(n));
            if (isMandatory) {
                counter.classList.remove('too-short', 'near-limit', 'valid');
                if (n < 20) {
                    counter.classList.add('too-short');
                    submitBtn.disabled = true;
                } else if (n < 30) {
                    counter.classList.add('near-limit');
                    submitBtn.disabled = false;
                    if (errorMsg) errorMsg.classList.remove('visible');
                    textarea.classList.remove('has-error');
                } else {
                    counter.classList.add('valid');
                    submitBtn.disabled = false;
                    if (errorMsg) errorMsg.classList.remove('visible');
                    textarea.classList.remove('has-error');
                }
            }
        });

        // Esc key \u2014 LOW = X close banner, MID/HIGH = Passer
        textarea.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' || e.keyCode === 27) {
                e.preventDefault();
                if (isMandatory) {
                    // LOW Esc = dismiss banner entier (X close behavior)
                    var closeBtn = banner.querySelector('.rating-banner-close');
                    if (closeBtn) closeBtn.click();
                } else if (!submitted) {
                    submitted = true;
                    submitBannerRating(rating, '');
                }
            }
        });

        // Insert section before the close button
        var closeBtn = banner.querySelector('.rating-banner-close');
        banner.insertBefore(section, closeBtn);
        try { textarea.focus(); } catch (e) { /* ignore */ }
    }

    function submitBannerRating(rating, comment) {
        var sessionId = sessionStorage.getItem('hybride_session_id')
            || ('sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9));
        sessionStorage.setItem('hybride_session_id', sessionId);

        var isEM = window.location.pathname.indexOf('/euromillions') !== -1
                  || document.body.classList.contains('em-page');
        var ratingSource = isEM ? 'popup_em' : 'popup_accueil';
        var ratingModule = isEM ? 'euromillions' : 'loto';
        var hasComment = !!(comment && comment.length > 0);

        if (window.LotoIA_track) LotoIA_track('rating-submitted', {rating: rating, module: ratingModule, has_comment: hasComment});
        if (window.LotoIAAnalytics) window.LotoIAAnalytics.track('rating_submitted', { event_category: 'rating', rating: rating, module: ratingModule, has_comment: hasComment });

        var payload = {
            source: ratingSource,
            rating: rating,
            session_id: sessionId,
            page: window.location.pathname
        };
        if (hasComment) {
            payload.comment = comment.substring(0, 500);
        }

        fetch('/api/rating', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.success) {
                sessionStorage.setItem('lotoia_rated_' + ratingSource, 'true');
                var feedback = document.getElementById('banner-rating-feedback');
                if (feedback) feedback.textContent = LI.rating_thanks || 'Merci !';
                // Hide comment section
                var commentSection = document.getElementById('rating-comment-section');
                if (commentSection) commentSection.style.display = 'none';
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
