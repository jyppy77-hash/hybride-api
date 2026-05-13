/* ══════════════════════════════════════════════════════════════
   HYBRIDE Chatbot Widget — EuroMillions EN (vanilla, IIFE, ES5+)
   Auto-init on #hybride-chatbot-root.
   No dependency. No global pollution.
   Endpoint : /api/euromillions/hybride-chat (lang=en)
   Storage  : hybride-history-em-en
   ══════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    function onReady(fn) {
        if (document.readyState !== 'loading') { fn(); }
        else { document.addEventListener('DOMContentLoaded', fn); }
    }

    onReady(function () {

        var root = document.getElementById('hybride-chatbot-root');
        if (!root) return;
        if (root.getAttribute('data-hybride-init') === '1') return;
        root.setAttribute('data-hybride-init', '1');

        // Floating bubble
        var bubble = document.createElement('button');
        bubble.className = 'hybride-bubble';
        bubble.setAttribute('aria-label', 'Open HYBRIDE EuroMillions chatbot');
        bubble.innerHTML = '<span>\uD83E\uDD16</span>';

        // Window
        var win = document.createElement('div');
        win.className = 'hybride-window';
        win.innerHTML =
            '<div class="hybride-header">' +
                '<span class="hybride-header-title">\uD83E\uDD16 HYBRIDE \u2014 EuroMillions</span>' +
                '<div class="hybride-header-actions">' +
                    '<button class="hybride-header-clear" aria-label="New conversation" title="New conversation">\uD83D\uDDD1\uFE0F</button>' +
                    '<button class="hybride-header-close" aria-label="Close">\u2715</button>' +
                '</div>' +
            '</div>' +
            '<div class="hybride-messages"></div>' +
            '<div class="hybride-input-area">' +
                '<input class="hybride-input" type="text" placeholder="Ask your EuroMillions question..." autocomplete="off">' +
                '<button class="hybride-send" aria-label="Send">\u27A4</button>' +
            '</div>';

        root.appendChild(bubble);
        root.appendChild(win);

        var closeBtn = win.querySelector('.hybride-header-close');
        var clearBtn = win.querySelector('.hybride-header-clear');
        var messagesArea = win.querySelector('.hybride-messages');
        var input = win.querySelector('.hybride-input');
        var sendBtn = win.querySelector('.hybride-send');

        var isOpen = false;

        function getTime() {
            var d = new Date();
            var h = d.getHours();
            var m = d.getMinutes();
            return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
        }

        function scrollToBottom() {
            messagesArea.scrollTop = messagesArea.scrollHeight;
        }

        function addMessage(text, sender) {
            var msg = document.createElement('div');
            msg.className = 'hybride-msg hybride-msg-' + sender;
            msg.innerHTML =
                '<span>' + escapeHtml(text) + '</span>' +
                '<span class="hybride-msg-time">' + getTime() + '</span>';
            messagesArea.appendChild(msg);
            scrollToBottom();
        }

        function escapeHtml(str) {
            var div = document.createElement('div');
            div.appendChild(document.createTextNode(str));
            return div.innerHTML;
        }

        function showTyping() {
            var el = document.createElement('div');
            el.className = 'hybride-typing';
            el.id = 'hybride-typing-indicator-em-en';
            el.innerHTML =
                '<span class="hybride-typing-dot"></span>' +
                '<span class="hybride-typing-dot"></span>' +
                '<span class="hybride-typing-dot"></span>';
            messagesArea.appendChild(el);
            scrollToBottom();
        }

        function removeTyping() {
            var el = document.getElementById('hybride-typing-indicator-em-en');
            if (el && el.parentNode) el.parentNode.removeChild(el);
        }

        function toggle() {
            isOpen = !isOpen;
            if (isOpen) {
                root.classList.add('hybride-fullscreen');
                win.classList.add('visible');
                bubble.classList.add('open');
                adjustViewport();
                input.focus();
                chatOpenTime = Date.now();
                sponsorViews = 0;
                trackEvent('hybride_em_en_chat_open', {
                    page: detectPage(),
                    has_history: chatHistory.length > 1
                });
                if (window.LotoIA_track) LotoIA_track('chatbot-open', {module: 'euromillions-en'});
            } else {
                win.classList.remove('visible');
                bubble.classList.remove('open');
                root.classList.remove('hybride-fullscreen');
                if (window.LotoIA_track) LotoIA_track('chatbot-close', {module: 'euromillions-en'});
                trackEvent('hybride_em_en_chat_session', {
                    page: detectPage(),
                    message_count: messageCount,
                    session_duration_seconds: chatOpenTime ? Math.round((Date.now() - chatOpenTime) / 1000) : 0,
                    sponsor_views: sponsorViews
                });
            }
        }

        function close() {
            if (!isOpen) return;
            isOpen = false;
            win.classList.remove('visible');
            bubble.classList.remove('open');
            root.classList.remove('hybride-fullscreen');
            if (window.LotoIA_track) LotoIA_track('chatbot-close', {module: 'euromillions-en'});
            trackEvent('hybride_em_en_chat_session', {
                page: detectPage(),
                message_count: messageCount,
                session_duration_seconds: chatOpenTime ? Math.round((Date.now() - chatOpenTime) / 1000) : 0,
                sponsor_views: sponsorViews
            });
        }

        /* ══════════════════════════════════
           Page detection (EN URLs)
           ══════════════════════════════════ */

        function detectPage() {
            var path = window.location.pathname;
            if (path.indexOf('/en/euromillions/generator') !== -1) return 'generator-em-en';
            if (path.indexOf('/en/euromillions/simulator') !== -1) return 'simulator-em-en';
            if (path.indexOf('/en/euromillions/statistics') !== -1) return 'statistics-em-en';
            if (path.indexOf('/en/euromillions/history') !== -1) return 'history-em-en';
            if (path.indexOf('/en/euromillions/faq') !== -1) return 'faq-em-en';
            if (path.indexOf('/en/euromillions/news') !== -1) return 'news-em-en';
            return 'home-em-en';
        }

        var chatHistory = [];
        var WELCOME_TEXT = 'Welcome! I\u2019m HYBRIDE, the LotoIA AI assistant \u2014 EuroMillions module. Ask me anything about EuroMillions, statistics or the HYBRIDE engine \uD83C\uDF1F';
        var STORAGE_KEY = 'hybride-history-em-en';

        var chatOpenTime = 0;
        var sponsorViews = 0;
        var messageCount = 0;

        function saveHistory() {
            try {
                var toSave = chatHistory.length > 50 ? chatHistory.slice(-50) : chatHistory;
                sessionStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
            } catch (e) { /* quota exceeded */ }
        }

        function trackEvent(name, params) {
            try {
                if (window.LotoIAAnalytics && window.LotoIAAnalytics.track) {
                    window.LotoIAAnalytics.track(name, params || {});
                }
            } catch (e) { /* analytics must never break chat */ }
        }

        /* ══════════════════════════════════
           Send message (API EuroMillions, lang=en)
           ══════════════════════════════════ */

        function extractSponsorId(text) {
            var m = text.match(/\[SPONSOR:([^\]]+)\]/);
            return m ? m[1] : null;
        }
        function hasSponsor(text) {
            return extractSponsorId(text) !== null;
        }

        function send() {
            var text = input.value.trim();
            if (!text) return;

            addMessage(text, 'user');
            input.value = '';
            messageCount++;

            showTyping();
            trackEvent('hybride_em_en_chat_message', {
                page: detectPage(),
                message_length: text.length,
                message_count: messageCount
            });
            if (window.LotoIA_track) LotoIA_track('chatbot-message', {module: 'euromillions-en'});

            var controller = new AbortController();
            var timeoutId = setTimeout(function () { controller.abort(); }, 20000);

            fetch('/api/euromillions/hybride-chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    page: detectPage(),
                    history: chatHistory,
                    lang: 'en'
                }),
                signal: controller.signal
            })
            .then(function (res) {
                clearTimeout(timeoutId);
                if (res.status === 429) {
                    return res.json().then(function (body) {
                        removeTyping();
                        addMessage('\uD83D\uDED1 ' + (body.message || 'Rate limit exceeded'), 'bot');
                    });
                }
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                removeTyping();
                var botText = data.response || '\uD83E\uDD16 Response unavailable.';
                var sponsorId = extractSponsorId(botText);
                if (sponsorId) {
                    botText = botText.replace(/\[SPONSOR:[^\]]+\]/, '');
                }
                addMessage(botText, 'bot');
                chatHistory.push({ role: 'user', content: text });
                chatHistory.push({ role: 'assistant', content: botText });
                if (chatHistory.length > 20) chatHistory = [chatHistory[0]].concat(chatHistory.slice(-19));
                saveHistory();

                if (sponsorId) {
                    sponsorViews++;
                    trackEvent('hybride_em_en_chat_sponsor_view', {
                        page: detectPage(),
                        sponsor_id: sponsorId,
                        message_position: messageCount
                    });
                    fetch('/api/sponsor/track', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        keepalive: true,
                        body: JSON.stringify({
                            event_type: 'sponsor-inline-shown',
                            sponsor_id: sponsorId,
                            page: window.location.pathname,
                            lang: 'en',
                            device: /Mobi/.test(navigator.userAgent) ? 'mobile' : 'desktop'
                        })
                    }).catch(function() {});
                    if (typeof LotoIA_track === 'function') LotoIA_track('sponsor-inline-shown', { sponsor_id: sponsorId, product_code: sponsorId });
                }

                if (messageCount === 5) {
                    setTimeout(function () { showRatingWidget(); }, 1500);
                }
                if (messageCount === 3) {
                    setTimeout(function () { showContactLink(); }, 2000);
                }
            })
            .catch(function () {
                clearTimeout(timeoutId);
                removeTyping();
                addMessage('\uD83E\uDD16 Connection interrupted. Try again in a few seconds!', 'bot');
                showContactLink();
                trackEvent('hybride_em_en_chat_error', { page: detectPage() });
            });
        }

        function showContactLink() {
            if (messageCount < 3 && !document.querySelector('.hybride-contact-link')) return;
            var link = document.createElement('div');
            link.className = 'hybride-msg hybride-msg-bot hybride-contact-link';
            var a = document.createElement('a');
            a.href = '#';
            a.textContent = (window.LotoIA_i18n || {}).contact_chatbot_link || 'Having trouble? Contact us \u2192';
            a.style.cssText = 'color:#94a3b8;font-size:0.82rem;text-decoration:underline;cursor:pointer;';
            a.addEventListener('click', function(e) {
                e.preventDefault();
                if (window.LotoIAContact) LotoIAContact.openModal('chatbot');
            });
            link.appendChild(a);
            messagesArea.appendChild(link);
            scrollToBottom();
        }

        /* ══════════════════════════════════
           Rating widget
           ══════════════════════════════════ */

        var RATING_SOURCE = 'chatbot_em_en';
        var RATING_STORAGE_KEY = 'lotoia_rated_' + RATING_SOURCE;
        var ratingShown = false;

        function showRatingWidget() {
            if (ratingShown) return;
            if (sessionStorage.getItem(RATING_STORAGE_KEY)) return;
            if (sessionStorage.getItem('lotoia_rated_chatbot_loto')) return;
            if (sessionStorage.getItem('lotoia_rated_popup_accueil')) return;
            ratingShown = true;

            var widget = document.createElement('div');
            widget.className = 'hybride-msg hybride-msg-bot hybride-rating-widget';
            widget.id = 'hybride-rating-widget-em-en';

            var question = document.createElement('div');
            question.className = 'rating-question';
            question.textContent = 'Enjoying HYBRIDE EuroMillions? Rate your experience!';
            widget.appendChild(question);

            var starsDiv = document.createElement('div');
            starsDiv.className = 'rating-stars';
            starsDiv.id = 'hybride-rating-stars-em-en';

            for (var i = 1; i <= 5; i++) {
                var star = document.createElement('span');
                star.className = 'rating-star';
                star.setAttribute('data-value', String(i));
                star.textContent = '\u2605';
                (function (val) {
                    star.addEventListener('mouseover', function () { highlightStarsEmEn(val); });
                    star.addEventListener('mouseout', function () { resetStarsEmEn(); });
                    star.addEventListener('click', function () { submitChatRatingEmEn(val); });
                })(i);
                starsDiv.appendChild(star);
            }
            widget.appendChild(starsDiv);

            var labels = document.createElement('div');
            labels.className = 'rating-labels';
            var labelBof = document.createElement('span');
            labelBof.textContent = 'Meh';
            var labelTop = document.createElement('span');
            labelTop.textContent = 'Great!';
            labels.appendChild(labelBof);
            labels.appendChild(labelTop);
            widget.appendChild(labels);

            var feedback = document.createElement('div');
            feedback.className = 'rating-feedback';
            feedback.id = 'hybride-rating-feedback-em-en';
            feedback.style.display = 'none';
            widget.appendChild(feedback);

            messagesArea.appendChild(widget);
            scrollToBottom();
        }

        function highlightStarsEmEn(n) {
            var stars = document.querySelectorAll('#hybride-rating-stars-em-en .rating-star');
            for (var i = 0; i < stars.length; i++) {
                if (i < n) { stars[i].classList.add('active'); }
                else { stars[i].classList.remove('active'); }
            }
        }

        function resetStarsEmEn() {
            var selected = document.querySelector('#hybride-rating-stars-em-en .rating-star.selected');
            if (selected) return;
            var stars = document.querySelectorAll('#hybride-rating-stars-em-en .rating-star');
            for (var i = 0; i < stars.length; i++) { stars[i].classList.remove('active'); }
        }

        function submitChatRatingEmEn(rating) {
            // V141 A.4 UX Fix 1 — 3 tiers : low (1-2) mandatory 20 chars, mid (3) / high (4-5) optional
            var stars = document.querySelectorAll('#hybride-rating-stars-em-en .rating-star');
            for (var i = 0; i < stars.length; i++) {
                if (i < rating) {
                    stars[i].classList.add('selected');
                    stars[i].classList.add('active');
                } else {
                    stars[i].classList.remove('selected');
                    stars[i].classList.remove('active');
                }
            }
            showRatingCommentSectionEmEn(rating);
        }

        function showRatingCommentSectionEmEn(rating) {
            var widget = document.getElementById('hybride-rating-widget-em-en');
            if (!widget) return;
            if (document.getElementById('hybride-rating-comment-section')) return;

            var tier = rating <= 2 ? 'low' : (rating === 3 ? 'mid' : 'high');
            var isMandatory = (tier === 'low');
            var MIN_CHARS = 20;

            var section = document.createElement('div');
            section.id = 'hybride-rating-comment-section';
            section.className = 'hybride-rating-comment-section hybride-rating-tier-' + tier;

            if (isMandatory) {
                var dismissBtn = document.createElement('button');
                dismissBtn.className = 'hybride-rating-comment-dismiss';
                dismissBtn.setAttribute('aria-label', 'Close');
                dismissBtn.textContent = '✕';
                dismissBtn.addEventListener('click', function () { dismissRatingCommentEmEn(); });
                section.appendChild(dismissBtn);
            }

            var prompt = document.createElement('div');
            prompt.className = 'hybride-rating-comment-prompt';
            if (tier === 'low') {
                prompt.textContent = 'What didn\'t work?';
            } else if (tier === 'mid') {
                prompt.textContent = 'Any suggestion to improve? (optional)';
            } else {
                prompt.textContent = 'A word to make us smile? (optional) 🤩';
            }
            section.appendChild(prompt);

            var textarea = document.createElement('textarea');
            textarea.id = 'hybride-rating-comment-input';
            textarea.className = 'hybride-rating-comment-input';
            textarea.maxLength = 500;
            textarea.rows = 3;
            section.appendChild(textarea);

            var errorMsg = null;
            if (isMandatory) {
                errorMsg = document.createElement('div');
                errorMsg.className = 'hybride-rating-comment-error';
                errorMsg.textContent = 'Min. 20 characters please 😊';
                section.appendChild(errorMsg);
            }

            var footer = document.createElement('div');
            footer.className = 'hybride-rating-comment-footer';

            var counter = document.createElement('span');
            counter.className = 'hybride-rating-comment-counter';
            if (isMandatory) counter.classList.add('too-short');
            counter.textContent = '0 / 500';

            var submitted = false;
            var btnGroup = document.createElement('span');
            btnGroup.className = 'hybride-rating-comment-buttons';

            if (!isMandatory) {
                var skipBtn = document.createElement('button');
                skipBtn.className = 'hybride-rating-comment-skip';
                skipBtn.textContent = 'Skip';
                skipBtn.addEventListener('click', function () {
                    if (submitted) return;
                    submitted = true;
                    skipBtn.disabled = true;
                    _sendRatingPayloadEmEn(rating, '');
                });
                btnGroup.appendChild(skipBtn);
            }

            var submitBtn = document.createElement('button');
            submitBtn.className = 'hybride-rating-comment-submit';
            submitBtn.textContent = 'Send';
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
                _sendRatingPayloadEmEn(rating, comment.substring(0, 500));
            });
            btnGroup.appendChild(submitBtn);

            footer.appendChild(counter);
            footer.appendChild(btnGroup);
            section.appendChild(footer);

            textarea.addEventListener('input', function () {
                var n = textarea.value.length;
                counter.textContent = n + ' / 500';
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

            textarea.addEventListener('keydown', function (e) {
                if (e.key === 'Escape' || e.keyCode === 27) {
                    e.preventDefault();
                    if (isMandatory) {
                        dismissRatingCommentEmEn();
                    } else if (!submitted) {
                        submitted = true;
                        _sendRatingPayloadEmEn(rating, '');
                    }
                }
            });

            widget.appendChild(section);
            try { textarea.focus(); } catch (e) { /* ignore */ }
            scrollToBottom();
        }

        function dismissRatingCommentEmEn() {
            var section = document.getElementById('hybride-rating-comment-section');
            if (section) section.remove();
            var stars = document.querySelectorAll('#hybride-rating-stars-em-en .rating-star');
            for (var i = 0; i < stars.length; i++) {
                stars[i].classList.remove('selected');
                stars[i].classList.remove('active');
            }
            if (window.LotoIA_track) LotoIA_track('rating-dismissed-popup', {module: 'euromillions-en'});
        }

        function _sendRatingPayloadEmEn(rating, comment) {
            var sessionId = sessionStorage.getItem('hybride_session_id')
                || ('sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9));
            sessionStorage.setItem('hybride_session_id', sessionId);

            var hasComment = !!(comment && comment.length > 0);
            var payload = {
                source: RATING_SOURCE,
                rating: rating,
                session_id: sessionId,
                page: window.location.pathname
            };
            if (hasComment) payload.comment = comment.substring(0, 500);

            fetch('/api/rating', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    sessionStorage.setItem(RATING_STORAGE_KEY, 'true');
                    var commentSection = document.getElementById('hybride-rating-comment-section');
                    if (commentSection) commentSection.style.display = 'none';
                    var feedback = document.getElementById('hybride-rating-feedback-em-en');
                    var messages = {
                        5: 'Thanks! You\'re a legend!',
                        4: 'Thanks! Glad you like it!',
                        3: 'Thanks! We\'ll keep improving!',
                        2: 'Thanks for your feedback!',
                        1: 'Thanks! Tell us what we can improve!'
                    };
                    if (feedback) {
                        feedback.textContent = messages[rating] || 'Thanks!';
                        feedback.style.display = 'block';
                    }
                    setTimeout(function () {
                        var w = document.getElementById('hybride-rating-widget-em-en');
                        if (w) w.innerHTML = '<div class="rating-thanks">Thanks for your feedback!</div>';
                    }, 3000);
                }
            })
            .catch(function (err) { /* silent */ });

            trackEvent('hybride_em_en_chat_rating', {
                page: detectPage(),
                rating: rating,
                message_count: messageCount,
                has_comment: hasComment
            });
            if (window.LotoIA_track) LotoIA_track('rating-submitted', {rating: rating, module: 'euromillions-en', has_comment: hasComment});
        }

        /* ══════════════════════════════════
           History restore / welcome
           ══════════════════════════════════ */

        var savedHistory = sessionStorage.getItem(STORAGE_KEY);
        if (savedHistory) {
            try {
                chatHistory = JSON.parse(savedHistory);
                for (var i = 0; i < chatHistory.length; i++) {
                    var sender = chatHistory[i].role === 'user' ? 'user' : 'bot';
                    addMessage(chatHistory[i].content, sender);
                }
            } catch (e) {
                chatHistory = [];
                sessionStorage.removeItem(STORAGE_KEY);
            }
        }

        if (chatHistory.length === 0) {
            addMessage(WELCOME_TEXT, 'bot');
            chatHistory.push({ role: 'assistant', content: WELCOME_TEXT });
            saveHistory();
        }

        /* ══════════════════════════════════
           Events
           ══════════════════════════════════ */

        function clearConversation() {
            trackEvent('hybride_em_en_chat_clear', {
                page: detectPage(),
                message_count: messageCount
            });
            chatHistory = [];
            messageCount = 0;
            sessionStorage.removeItem(STORAGE_KEY);
            messagesArea.innerHTML = '';
            addMessage(WELCOME_TEXT, 'bot');
            chatHistory.push({ role: 'assistant', content: WELCOME_TEXT });
            saveHistory();
        }

        bubble.addEventListener('click', toggle);
        closeBtn.addEventListener('click', close);
        clearBtn.addEventListener('click', clearConversation);
        sendBtn.addEventListener('click', send);

        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.keyCode === 13) {
                e.preventDefault();
                send();
            }
        });

        document.addEventListener('keydown', function (e) {
            if ((e.key === 'Escape' || e.keyCode === 27) && isOpen) {
                close();
            }
        });

        var vvp = window.visualViewport;

        function adjustViewport() {
            if (!root) return;
            if (vvp) {
                root.style.setProperty('--vvp-height', vvp.height + 'px');
                root.style.top = vvp.offsetTop + 'px';
            } else {
                root.style.setProperty('--vvp-height', window.innerHeight + 'px');
                root.style.top = '0px';
            }
            if (messagesArea) {
                setTimeout(function () {
                    messagesArea.scrollTop = messagesArea.scrollHeight;
                }, 50);
            }
        }

        if (vvp) {
            vvp.addEventListener('resize', adjustViewport);
            vvp.addEventListener('scroll', adjustViewport);
        }

        input.addEventListener('focus', function () {
            setTimeout(adjustViewport, 300);
        });

        var meta = document.querySelector('meta[name="viewport"]');
        if (meta) {
            var content = meta.getAttribute('content');
            if (content.indexOf('interactive-widget') === -1) {
                meta.setAttribute('content', content + ', interactive-widget=resizes-content');
            }
        }

    });
})();
