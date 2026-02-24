/* ══════════════════════════════════════════════════════════════
   HYBRIDE Chatbot Widget — EuroMillions (vanilla, IIFE, ES5+)
   Auto-init sur #hybride-chatbot-root.
   Aucune dependance. Aucune pollution globale.
   Endpoint : /api/euromillions/hybride-chat
   Storage  : hybride-history-em
   ══════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    /* ── Attendre le DOM ── */
    function onReady(fn) {
        if (document.readyState !== 'loading') { fn(); }
        else { document.addEventListener('DOMContentLoaded', fn); }
    }

    onReady(function () {

        /* ── Point d'ancrage + guard anti-double-init ── */
        var root = document.getElementById('hybride-chatbot-root');
        if (!root) return;
        if (root.getAttribute('data-hybride-init') === '1') return;
        root.setAttribute('data-hybride-init', '1');

        /* ══════════════════════════════════
           HTML du widget
           ══════════════════════════════════ */

        // Bulle flottante
        var bubble = document.createElement('button');
        bubble.className = 'hybride-bubble';
        bubble.setAttribute('aria-label', 'Ouvrir le chatbot HYBRIDE EuroMillions');
        bubble.innerHTML = '<span>\uD83E\uDD16</span>';

        // Fenetre
        var win = document.createElement('div');
        win.className = 'hybride-window';
        win.innerHTML =
            '<div class="hybride-header">' +
                '<span class="hybride-header-title">\uD83E\uDD16 HYBRIDE \u2014 EuroMillions</span>' +
                '<div class="hybride-header-actions">' +
                    '<button class="hybride-header-clear" aria-label="Nouvelle conversation" title="Nouvelle conversation">\uD83D\uDDD1\uFE0F</button>' +
                    '<button class="hybride-header-close" aria-label="Fermer">\u2715</button>' +
                '</div>' +
            '</div>' +
            '<div class="hybride-messages"></div>' +
            '<div class="hybride-input-area">' +
                '<input class="hybride-input" type="text" placeholder="Pose ta question EuroMillions..." autocomplete="off">' +
                '<button class="hybride-send" aria-label="Envoyer">\u27A4</button>' +
            '</div>';

        // Injecter dans le root
        root.appendChild(bubble);
        root.appendChild(win);

        /* ── References DOM internes ── */
        var closeBtn = win.querySelector('.hybride-header-close');
        var clearBtn = win.querySelector('.hybride-header-clear');
        var messagesArea = win.querySelector('.hybride-messages');
        var input = win.querySelector('.hybride-input');
        var sendBtn = win.querySelector('.hybride-send');

        var isOpen = false;

        /* ══════════════════════════════════
           Helpers
           ══════════════════════════════════ */

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
            el.id = 'hybride-typing-indicator-em';
            el.innerHTML =
                '<span class="hybride-typing-dot"></span>' +
                '<span class="hybride-typing-dot"></span>' +
                '<span class="hybride-typing-dot"></span>';
            messagesArea.appendChild(el);
            scrollToBottom();
        }

        function removeTyping() {
            var el = document.getElementById('hybride-typing-indicator-em');
            if (el && el.parentNode) el.parentNode.removeChild(el);
        }

        /* ══════════════════════════════════
           Toggle ouverture / fermeture
           ══════════════════════════════════ */

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
                trackEvent('hybride_em_chat_open', {
                    page: detectPage(),
                    has_history: chatHistory.length > 1
                });
            } else {
                win.classList.remove('visible');
                bubble.classList.remove('open');
                root.classList.remove('hybride-fullscreen');
                trackEvent('hybride_em_chat_session', {
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
            trackEvent('hybride_em_chat_session', {
                page: detectPage(),
                message_count: messageCount,
                session_duration_seconds: chatOpenTime ? Math.round((Date.now() - chatOpenTime) / 1000) : 0,
                sponsor_views: sponsorViews
            });
        }

        /* ══════════════════════════════════
           Detection de page EM + historique
           ══════════════════════════════════ */

        function detectPage() {
            var path = window.location.pathname;
            if (path.indexOf('/euromillions/generateur') !== -1) return 'euromillions';
            if (path.indexOf('/euromillions/simulateur') !== -1) return 'simulateur-em';
            if (path.indexOf('/euromillions/statistiques') !== -1) return 'statistiques-em';
            if (path.indexOf('/euromillions/historique') !== -1) return 'historique-em';
            if (path.indexOf('/euromillions/faq') !== -1) return 'faq-em';
            if (path.indexOf('/euromillions/news') !== -1) return 'news-em';
            return 'accueil-em';
        }

        var chatHistory = [];
        var WELCOME_TEXT = 'Bienvenue ! Je suis HYBRIDE, l\u2019assistant IA de LotoIA \u2014 module EuroMillions. Pose-moi tes questions sur l\u2019EuroMillions, les statistiques ou le moteur HYBRIDE \uD83C\uDF1F';
        var STORAGE_KEY = 'hybride-history-em';

        /* ── GA4 session tracking state ── */
        var chatOpenTime = 0;
        var sponsorViews = 0;
        var messageCount = 0;

        function saveHistory() {
            try {
                var toSave = chatHistory.length > 50 ? chatHistory.slice(-50) : chatHistory;
                sessionStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
            } catch (e) { /* quota exceeded — silent */ }
        }

        /* ── Analytics helper (safe, ne bloque jamais) ── */
        function trackEvent(name, params) {
            try {
                if (window.LotoIAAnalytics && window.LotoIAAnalytics.track) {
                    window.LotoIAAnalytics.track(name, params || {});
                }
            } catch (e) { /* analytics must never break chat */ }
        }

        /* ══════════════════════════════════
           Envoi message (API EuroMillions)
           ══════════════════════════════════ */

        function hasSponsor(text) {
            return text.indexOf('partenaires') !== -1 || text.indexOf('Espace partenaire') !== -1;
        }

        function send() {
            var text = input.value.trim();
            if (!text) return;

            addMessage(text, 'user');
            input.value = '';
            messageCount++;

            showTyping();
            trackEvent('hybride_em_chat_message', {
                page: detectPage(),
                message_length: text.length,
                message_count: messageCount
            });

            var controller = new AbortController();
            var timeoutId = setTimeout(function () { controller.abort(); }, 20000);

            fetch('/api/euromillions/hybride-chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    page: detectPage(),
                    history: chatHistory
                }),
                signal: controller.signal
            })
            .then(function (res) {
                clearTimeout(timeoutId);
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                removeTyping();
                var botText = data.response || '\uD83E\uDD16 R\u00e9ponse indisponible.';
                addMessage(botText, 'bot');
                chatHistory.push({ role: 'user', content: text });
                chatHistory.push({ role: 'assistant', content: botText });
                if (chatHistory.length > 20) chatHistory = [chatHistory[0]].concat(chatHistory.slice(-19));
                saveHistory();

                // Sponsor detection
                if (hasSponsor(botText)) {
                    sponsorViews++;
                    trackEvent('hybride_em_chat_sponsor_view', {
                        page: detectPage(),
                        sponsor_style: botText.indexOf('partenaires') !== -1 ? 'A' : 'B',
                        message_position: messageCount
                    });
                }

                // Rating widget : proposer apres 5 messages
                if (messageCount === 5) {
                    setTimeout(function () { showRatingWidget(); }, 1500);
                }
            })
            .catch(function () {
                clearTimeout(timeoutId);
                removeTyping();
                addMessage('\uD83E\uDD16 Connexion interrompue. R\u00e9essaie dans quelques secondes !', 'bot');
                trackEvent('hybride_em_chat_error', { page: detectPage() });
            });
        }

        /* ══════════════════════════════════
           Systeme de notation (rating widget)
           ══════════════════════════════════ */

        var RATING_SOURCE = 'chatbot_em';
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
            widget.id = 'hybride-rating-widget-em';

            var question = document.createElement('div');
            question.className = 'rating-question';
            question.textContent = 'Tu kiffes HYBRIDE EuroMillions ? Note ton exp\u00e9rience !';
            widget.appendChild(question);

            var starsDiv = document.createElement('div');
            starsDiv.className = 'rating-stars';
            starsDiv.id = 'hybride-rating-stars-em';

            for (var i = 1; i <= 5; i++) {
                var star = document.createElement('span');
                star.className = 'rating-star';
                star.setAttribute('data-value', String(i));
                star.textContent = '\u2605';
                (function (val) {
                    star.addEventListener('mouseover', function () { highlightStarsEm(val); });
                    star.addEventListener('mouseout', function () { resetStarsEm(); });
                    star.addEventListener('click', function () { submitChatRatingEm(val); });
                })(i);
                starsDiv.appendChild(star);
            }
            widget.appendChild(starsDiv);

            var labels = document.createElement('div');
            labels.className = 'rating-labels';
            var labelBof = document.createElement('span');
            labelBof.textContent = 'Bof';
            var labelTop = document.createElement('span');
            labelTop.textContent = 'Top !';
            labels.appendChild(labelBof);
            labels.appendChild(labelTop);
            widget.appendChild(labels);

            var feedback = document.createElement('div');
            feedback.className = 'rating-feedback';
            feedback.id = 'hybride-rating-feedback-em';
            feedback.style.display = 'none';
            widget.appendChild(feedback);

            messagesArea.appendChild(widget);
            scrollToBottom();
        }

        function highlightStarsEm(n) {
            var stars = document.querySelectorAll('#hybride-rating-stars-em .rating-star');
            for (var i = 0; i < stars.length; i++) {
                if (i < n) { stars[i].classList.add('active'); }
                else { stars[i].classList.remove('active'); }
            }
        }

        function resetStarsEm() {
            var selected = document.querySelector('#hybride-rating-stars-em .rating-star.selected');
            if (selected) return;
            var stars = document.querySelectorAll('#hybride-rating-stars-em .rating-star');
            for (var i = 0; i < stars.length; i++) { stars[i].classList.remove('active'); }
        }

        function submitChatRatingEm(rating) {
            var stars = document.querySelectorAll('#hybride-rating-stars-em .rating-star');
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
                    var feedback = document.getElementById('hybride-rating-feedback-em');
                    var messages = {
                        5: 'Merci ! Tu es un vrai !',
                        4: 'Merci ! Content que \u00e7a te plaise !',
                        3: 'Merci ! On va s\u2019am\u00e9liorer !',
                        2: 'Merci pour ton retour !',
                        1: 'Merci ! Dis-nous ce qu\u2019on peut am\u00e9liorer !'
                    };
                    if (feedback) {
                        feedback.textContent = messages[rating] || 'Merci !';
                        feedback.style.display = 'block';
                    }
                    setTimeout(function () {
                        var w = document.getElementById('hybride-rating-widget-em');
                        if (w) w.innerHTML = '<div class="rating-thanks">Merci pour ton avis !</div>';
                    }, 3000);
                }
            })
            .catch(function (err) { /* silent — rating is non-critical */ });

            trackEvent('hybride_em_chat_rating', {
                page: detectPage(),
                rating: rating,
                message_count: messageCount
            });
        }

        /* ══════════════════════════════════
           Restauration historique / accueil
           ══════════════════════════════════ */

        var savedHistory = sessionStorage.getItem(STORAGE_KEY);
        if (savedHistory) {
            try {
                chatHistory = JSON.parse(savedHistory);
                // Re-afficher toutes les bulles
                for (var i = 0; i < chatHistory.length; i++) {
                    var sender = chatHistory[i].role === 'user' ? 'user' : 'bot';
                    addMessage(chatHistory[i].content, sender);
                }
            } catch (e) {
                chatHistory = [];
                sessionStorage.removeItem(STORAGE_KEY);
            }
        }

        // Message de bienvenue uniquement si aucun historique
        if (chatHistory.length === 0) {
            addMessage(WELCOME_TEXT, 'bot');
            chatHistory.push({ role: 'assistant', content: WELCOME_TEXT });
            saveHistory();
        }

        /* ══════════════════════════════════
           Events
           ══════════════════════════════════ */

        function clearConversation() {
            trackEvent('hybride_em_chat_clear', {
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

        // Fermer avec Escape
        document.addEventListener('keydown', function (e) {
            if ((e.key === 'Escape' || e.keyCode === 27) && isOpen) {
                close();
            }
        });

        // Mobile : synchro visualViewport (clavier virtuel Android)
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

        // Guard meta viewport (fallback navigateurs anciens)
        var meta = document.querySelector('meta[name="viewport"]');
        if (meta) {
            var content = meta.getAttribute('content');
            if (content.indexOf('interactive-widget') === -1) {
                meta.setAttribute('content', content + ', interactive-widget=resizes-content');
            }
        }

    }); // fin onReady
})(); // fin IIFE
