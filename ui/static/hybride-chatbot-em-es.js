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

        function createBotBubble() {
            var msg = document.createElement('div');
            msg.className = 'hybride-msg hybride-msg-bot';
            var textSpan = document.createElement('span');
            var timeSpan = document.createElement('span');
            timeSpan.className = 'hybride-msg-time';
            timeSpan.textContent = getTime();
            msg.appendChild(textSpan);
            msg.appendChild(timeSpan);
            messagesArea.appendChild(msg);
            scrollToBottom();
            return msg;
        }

        function updateBubbleText(msgEl, text) {
            var span = msgEl.querySelector('span:first-child');
            span.textContent = text;
            scrollToBottom();
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
            var timeoutId = setTimeout(function () { controller.abort(); }, 30000);

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

                var reader = res.body.getReader();
                var decoder = new TextDecoder();
                var botText = '';
                var msgEl = null;
                var buffer = '';

                function processStream() {
                    return reader.read().then(function (result) {
                        if (result.done) {
                            finalize();
                            return;
                        }

                        buffer += decoder.decode(result.value, { stream: true });
                        var parts = buffer.split('\n\n');
                        buffer = parts.pop();

                        for (var i = 0; i < parts.length; i++) {
                            var lines = parts[i].split('\n');
                            for (var j = 0; j < lines.length; j++) {
                                var line = lines[j].trim();
                                if (line.indexOf('data: ') === 0) {
                                    try {
                                        var evt = JSON.parse(line.substring(6));
                                        if (evt.chunk) {
                                            botText += evt.chunk;
                                            if (!msgEl) {
                                                removeTyping();
                                                msgEl = createBotBubble();
                                            }
                                            updateBubbleText(msgEl, botText);
                                        }
                                        if (evt.is_done) {
                                            finalize();
                                            return;
                                        }
                                    } catch (e) { /* ignore parse errors */ }
                                }
                            }
                        }
                        return processStream();
                    });
                }

                function finalize() {
                    if (!botText) botText = (LI.chatbot_error_empty || '\uD83E\uDD16 Respuesta no disponible.');
                    if (!msgEl) {
                        removeTyping();
                        addMessage(botText, 'bot');
                    }
                    var sponsorId = extractSponsorId(botText);
                    if (sponsorId) {
                        botText = botText.replace(/\[SPONSOR:[^\]]+\]/, '');
                        if (msgEl) updateBubbleText(msgEl, botText);
                    }
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
                            keepalive: true,
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
                }

                return processStream();
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
            // V141 A.4 UX Fix 1 — 3 tiers : low (1-2) obligatorio 20 chars, mid (3) / high (4-5) opcional
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
            showRatingCommentSectionEmEs(rating);
        }

        function showRatingCommentSectionEmEs(rating) {
            var widget = document.getElementById('hybride-rating-widget-em-es');
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
                dismissBtn.setAttribute('aria-label', LI.rating_close || 'Cerrar');
                dismissBtn.textContent = '✕';
                dismissBtn.addEventListener('click', function () { dismissRatingCommentEmEs(); });
                section.appendChild(dismissBtn);
            }

            var prompt = document.createElement('div');
            prompt.className = 'hybride-rating-comment-prompt';
            if (tier === 'low') {
                prompt.textContent = LI.chatbot_rating_prompt_low || '¿Qué no funcionó?';
            } else if (tier === 'mid') {
                prompt.textContent = LI.chatbot_rating_prompt_mid || '¿Alguna sugerencia para mejorar? (opcional)';
            } else {
                prompt.textContent = LI.chatbot_rating_prompt_high || '¿Una palabra para alegrarnos? (opcional) 🤩';
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
                errorMsg.textContent = LI.chatbot_rating_min_chars || 'Mínimo 20 caracteres por favor 😊';
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
                skipBtn.textContent = LI.chatbot_rating_skip || 'Saltar';
                skipBtn.addEventListener('click', function () {
                    if (submitted) return;
                    submitted = true;
                    skipBtn.disabled = true;
                    _sendRatingPayloadEmEs(rating, '');
                });
                btnGroup.appendChild(skipBtn);
            }

            var submitBtn = document.createElement('button');
            submitBtn.className = 'hybride-rating-comment-submit';
            submitBtn.textContent = LI.chatbot_rating_send || 'Enviar';
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
                _sendRatingPayloadEmEs(rating, comment.substring(0, 500));
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
                        dismissRatingCommentEmEs();
                    } else if (!submitted) {
                        submitted = true;
                        _sendRatingPayloadEmEs(rating, '');
                    }
                }
            });

            widget.appendChild(section);
            try { textarea.focus(); } catch (e) { /* ignore */ }
            scrollToBottom();
        }

        function dismissRatingCommentEmEs() {
            var section = document.getElementById('hybride-rating-comment-section');
            if (section) section.remove();
            var stars = document.querySelectorAll('#hybride-rating-stars-em-es .rating-star');
            for (var i = 0; i < stars.length; i++) {
                stars[i].classList.remove('selected');
                stars[i].classList.remove('active');
            }
            if (window.LotoIA_track) LotoIA_track('rating-dismissed-popup', {module: 'euromillions-es'});
        }

        function _sendRatingPayloadEmEs(rating, comment) {
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
                message_count: messageCount,
                has_comment: hasComment
            });
            if (window.LotoIA_track) LotoIA_track('rating-submitted', {rating: rating, module: 'euromillions-es', has_comment: hasComment});
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
