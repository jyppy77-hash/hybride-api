/* ==============================================================
   HYBRIDE Chatbot Widget — EuroMillions ES (vanilla, IIFE, ES5+)
   Auto-init on #hybride-chatbot-root.
   No dependency. No global pollution.
   Endpoint : /api/euromillions/hybride-chat (lang=es)
   Storage  : hybride-history-em-es
   ============================================================== */

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

        var LI = window.LotoIA_i18n || {};

        // Floating bubble
        var bubble = document.createElement('button');
        bubble.className = 'hybride-bubble';
        bubble.setAttribute('aria-label', LI.chatbot_bubble_label || 'Abrir el chatbot HYBRIDE EuroMillions');
        bubble.innerHTML = '<span>\uD83E\uDD16</span>';

        // Window
        var win = document.createElement('div');
        win.className = 'hybride-window';
        win.innerHTML =
            '<div class="hybride-header">' +
                '<span class="hybride-header-title">\uD83E\uDD16 HYBRIDE \u2014 EuroMillions</span>' +
                '<div class="hybride-header-actions">' +
                    '<button class="hybride-header-clear" aria-label="' + (LI.chatbot_clear_title || 'Nueva conversaci\u00f3n') + '" title="' + (LI.chatbot_clear_title || 'Nueva conversaci\u00f3n') + '">\uD83D\uDDD1\uFE0F</button>' +
                    '<button class="hybride-header-close" aria-label="Close">\u2715</button>' +
                '</div>' +
            '</div>' +
            '<div class="hybride-messages"></div>' +
            '<div class="hybride-input-area">' +
                '<input class="hybride-input" type="text" placeholder="' + (LI.chatbot_placeholder || 'Haz tu pregunta EuroMillions...') + '" autocomplete="off">' +
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
            el.id = 'hybride-typing-indicator-em-es';
            el.innerHTML =
                '<span class="hybride-typing-dot"></span>' +
                '<span class="hybride-typing-dot"></span>' +
                '<span class="hybride-typing-dot"></span>';
            messagesArea.appendChild(el);
            scrollToBottom();
        }

        function removeTyping() {
            var el = document.getElementById('hybride-typing-indicator-em-es');
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
                trackEvent('hybride_em_es_chat_open', {
                    page: detectPage(),
                    has_history: chatHistory.length > 1
                });
                if (window.LotoIA_track) LotoIA_track('chatbot-open', {module: 'euromillions-es'});
            } else {
                win.classList.remove('visible');
                bubble.classList.remove('open');
                root.classList.remove('hybride-fullscreen');
                if (window.LotoIA_track) LotoIA_track('chatbot-close', {module: 'euromillions-es'});
                trackEvent('hybride_em_es_chat_session', {
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
            if (window.LotoIA_track) LotoIA_track('chatbot-close', {module: 'euromillions-es'});
            trackEvent('hybride_em_es_chat_session', {
                page: detectPage(),
                message_count: messageCount,
                session_duration_seconds: chatOpenTime ? Math.round((Date.now() - chatOpenTime) / 1000) : 0,
                sponsor_views: sponsorViews
            });
        }

        /* ==================================
           Page detection (ES URLs)
           ================================== */

        function detectPage() {
            var path = window.location.pathname;
            if (path.indexOf('/es/euromillions/generador') !== -1) return 'generator-em-es';
            if (path.indexOf('/es/euromillions/simulador') !== -1) return 'simulator-em-es';
            if (path.indexOf('/es/euromillions/estadisticas') !== -1) return 'statistics-em-es';
            if (path.indexOf('/es/euromillions/historial') !== -1) return 'history-em-es';
            if (path.indexOf('/es/euromillions/faq') !== -1) return 'faq-em-es';
            if (path.indexOf('/es/euromillions/noticias') !== -1) return 'news-em-es';
            return 'home-em-es';
        }

        var chatHistory = [];
        var WELCOME_TEXT = LI.chatbot_welcome || '\u00a1Bienvenido! Soy HYBRIDE, el asistente IA de LotoIA \u2014 m\u00f3dulo EuroMillions.';
        var STORAGE_KEY = 'hybride-history-em-es';

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

        /* ==================================
           Send message (API EuroMillions, lang=es)
           ================================== */

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
            trackEvent('hybride_em_es_chat_message', {
                page: detectPage(),
                message_length: text.length,
                message_count: messageCount
            });
            if (window.LotoIA_track) LotoIA_track('chatbot-message', {module: 'euromillions-es'});

            var controller = new AbortController();
            var timeoutId = setTimeout(function () { controller.abort(); }, 20000);

            fetch('/api/euromillions/hybride-chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    page: detectPage(),
                    history: chatHistory,
                    lang: 'es'
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
                var botText = data.response || (LI.chatbot_error_empty || '\uD83E\uDD16 Respuesta no disponible.');
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
                    trackEvent('hybride_em_es_chat_sponsor_view', {
                        page: detectPage(),
                        sponsor_id: sponsorId,
                        message_position: messageCount
                    });
                    fetch('/api/sponsor/track', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            event_type: 'sponsor-inline-shown',
                            sponsor_id: sponsorId,
                            page: window.location.pathname,
                            lang: 'es',
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
                addMessage(LI.chatbot_error_connection || '\uD83E\uDD16 Conexi\u00f3n interrumpida. \u00a1Vuelve a intentarlo en unos segundos!', 'bot');
                showContactLink();
                trackEvent('hybride_em_es_chat_error', { page: detectPage() });
            });
        }

        function showContactLink() {
            if (messageCount < 3 && !document.querySelector('.hybride-contact-link')) return;
            var link = document.createElement('div');
            link.className = 'hybride-msg hybride-msg-bot hybride-contact-link';
            var a = document.createElement('a');
            a.href = '#';
            a.textContent = LI.contact_chatbot_link || '\u00bfAlg\u00fan problema? Cont\u00e1ctanos \u2192';
            a.style.cssText = 'color:#94a3b8;font-size:0.82rem;text-decoration:underline;cursor:pointer;';
            a.addEventListener('click', function(e) {
                e.preventDefault();
                if (window.LotoIAContact) LotoIAContact.openModal('chatbot');
            });
            link.appendChild(a);
            messagesArea.appendChild(link);
            scrollToBottom();
        }

        /* ==================================
           Rating widget
           ================================== */

        var RATING_SOURCE = 'chatbot_em_es';
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
            widget.id = 'hybride-rating-widget-em-es';

            var question = document.createElement('div');
            question.className = 'rating-question';
            question.textContent = LI.chatbot_rating_question || '\u00bfTe gusta HYBRIDE EuroMillions? \u00a1Punt\u00faa tu experiencia!';
            widget.appendChild(question);

            var starsDiv = document.createElement('div');
            starsDiv.className = 'rating-stars';
            starsDiv.id = 'hybride-rating-stars-em-es';

            for (var i = 1; i <= 5; i++) {
                var star = document.createElement('span');
                star.className = 'rating-star';
                star.setAttribute('data-value', String(i));
                star.textContent = '\u2605';
                (function (val) {
                    star.addEventListener('mouseover', function () { highlightStarsEmEs(val); });
                    star.addEventListener('mouseout', function () { resetStarsEmEs(); });
                    star.addEventListener('click', function () { submitChatRatingEmEs(val); });
                })(i);
                starsDiv.appendChild(star);
            }
            widget.appendChild(starsDiv);

            var labels = document.createElement('div');
            labels.className = 'rating-labels';
            var labelBof = document.createElement('span');
            labelBof.textContent = LI.chatbot_rating_low || 'Regular';
            var labelTop = document.createElement('span');
            labelTop.textContent = LI.chatbot_rating_high || '\u00a1Genial!';
            labels.appendChild(labelBof);
            labels.appendChild(labelTop);
            widget.appendChild(labels);

            var feedback = document.createElement('div');
            feedback.className = 'rating-feedback';
            feedback.id = 'hybride-rating-feedback-em-es';
            feedback.style.display = 'none';
            widget.appendChild(feedback);

            messagesArea.appendChild(widget);
            scrollToBottom();
        }

        function highlightStarsEmEs(n) {
            var stars = document.querySelectorAll('#hybride-rating-stars-em-es .rating-star');
            for (var i = 0; i < stars.length; i++) {
                if (i < n) { stars[i].classList.add('active'); }
                else { stars[i].classList.remove('active'); }
            }
        }

        function resetStarsEmEs() {
            var selected = document.querySelector('#hybride-rating-stars-em-es .rating-star.selected');
            if (selected) return;
            var stars = document.querySelectorAll('#hybride-rating-stars-em-es .rating-star');
            for (var i = 0; i < stars.length; i++) { stars[i].classList.remove('active'); }
        }

        function submitChatRatingEmEs(rating) {
            var stars = document.querySelectorAll('#hybride-rating-stars-em-es .rating-star');
            for (var i = 0; i < stars.length; i++) {
                if (i < rating) {
                    stars[i].classList.add('selected');
                    stars[i].classList.add('active');
                } else {
                    stars[i].classList.remove('selected');
                    stars[i].classList.remove('active');
                }
            }

            var sessionId = sessionStorage.getItem('hybride_session_id')
                || ('sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9));
            sessionStorage.setItem('hybride_session_id', sessionId);

            fetch('/api/rating', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source: RATING_SOURCE,
                    rating: rating,
                    session_id: sessionId,
                    page: window.location.pathname
                })
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    sessionStorage.setItem(RATING_STORAGE_KEY, 'true');
                    var feedback = document.getElementById('hybride-rating-feedback-em-es');
                    var messages = {
                        5: LI.chatbot_rating_5 || '\u00a1Gracias! \u00a1Eres genial!',
                        4: LI.chatbot_rating_4 || '\u00a1Gracias! \u00a1Nos alegra que te guste!',
                        3: LI.chatbot_rating_3 || '\u00a1Gracias! \u00a1Seguiremos mejorando!',
                        2: LI.chatbot_rating_2 || '\u00a1Gracias por tu opini\u00f3n!',
                        1: LI.chatbot_rating_1 || '\u00a1Gracias! \u00a1Cu\u00e9ntanos c\u00f3mo mejorar!'
                    };
                    if (feedback) {
                        feedback.textContent = messages[rating] || (LI.chatbot_rating_default || '\u00a1Gracias!');
                        feedback.style.display = 'block';
                    }
                    setTimeout(function () {
                        var w = document.getElementById('hybride-rating-widget-em-es');
                        if (w) w.innerHTML = '<div class="rating-thanks">' + (LI.chatbot_rating_done || '\u00a1Gracias por tu opini\u00f3n!') + '</div>';
                    }, 3000);
                }
            })
            .catch(function (err) { /* silent */ });

            trackEvent('hybride_em_es_chat_rating', {
                page: detectPage(),
                rating: rating,
                message_count: messageCount
            });
            if (window.LotoIA_track) LotoIA_track('rating-submitted', {rating: rating, module: 'euromillions-es'});
        }

        /* ==================================
           History restore / welcome
           ================================== */

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

        /* ==================================
           Events
           ================================== */

        function clearConversation() {
            trackEvent('hybride_em_es_chat_clear', {
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
