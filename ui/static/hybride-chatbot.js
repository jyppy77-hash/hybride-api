/* ══════════════════════════════════════════════════════════════
   HYBRIDE Chatbot Widget — JS autonome (vanilla, IIFE, ES5+)
   Auto-init sur #hybride-chatbot-root.
   Aucune dépendance. Aucune pollution globale.
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
        bubble.setAttribute('aria-label', 'Ouvrir le chatbot HYBRIDE');
        bubble.innerHTML = '<span>🤖</span>';

        // Fenetre
        var win = document.createElement('div');
        win.className = 'hybride-window';
        win.innerHTML =
            '<div class="hybride-header">' +
                '<span class="hybride-header-title">\uD83E\uDD16 HYBRIDE — Assistant IA</span>' +
                '<button class="hybride-header-close" aria-label="Fermer">\u2715</button>' +
            '</div>' +
            '<div class="hybride-messages"></div>' +
            '<div class="hybride-input-area">' +
                '<input class="hybride-input" type="text" placeholder="Posez votre question..." autocomplete="off">' +
                '<button class="hybride-send" aria-label="Envoyer">\u27A4</button>' +
            '</div>';

        // Injecter dans le root
        root.appendChild(bubble);
        root.appendChild(win);

        /* ── Références DOM internes ── */
        var closeBtn = win.querySelector('.hybride-header-close');
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
            el.id = 'hybride-typing-indicator';
            el.innerHTML =
                '<span class="hybride-typing-dot"></span>' +
                '<span class="hybride-typing-dot"></span>' +
                '<span class="hybride-typing-dot"></span>';
            messagesArea.appendChild(el);
            scrollToBottom();
        }

        function removeTyping() {
            var el = document.getElementById('hybride-typing-indicator');
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
                input.focus();
            } else {
                win.classList.remove('visible');
                bubble.classList.remove('open');
                root.classList.remove('hybride-fullscreen');
            }
        }

        function close() {
            if (!isOpen) return;
            isOpen = false;
            win.classList.remove('visible');
            bubble.classList.remove('open');
            root.classList.remove('hybride-fullscreen');
        }

        /* ══════════════════════════════════
           Detection de page + historique
           ══════════════════════════════════ */

        function detectPage() {
            var path = window.location.pathname;
            if (path.indexOf('/loto') !== -1) return 'loto';
            if (path.indexOf('/simulateur') !== -1) return 'simulateur';
            if (path.indexOf('/statistiques') !== -1) return 'statistiques';
            return 'accueil';
        }

        var chatHistory = [];

        /* ══════════════════════════════════
           Envoi message (API Gemini)
           ══════════════════════════════════ */

        function send() {
            var text = input.value.trim();
            if (!text) return;

            addMessage(text, 'user');
            input.value = '';

            chatHistory.push({ role: 'user', content: text });
            if (chatHistory.length > 10) chatHistory = chatHistory.slice(-10);

            showTyping();

            var controller = new AbortController();
            var timeoutId = setTimeout(function () { controller.abort(); }, 20000);

            fetch('/api/hybride-chat', {
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
                chatHistory.push({ role: 'assistant', content: botText });
                if (chatHistory.length > 10) chatHistory = chatHistory.slice(-10);
            })
            .catch(function () {
                clearTimeout(timeoutId);
                removeTyping();
                addMessage('\uD83E\uDD16 Connexion interrompue. R\u00e9essaie dans quelques secondes !', 'bot');
            });
        }

        /* ══════════════════════════════════
           Message d'accueil
           ══════════════════════════════════ */

        addMessage(
            'Bienvenue ! Je suis HYBRIDE, l\u2019assistant IA de LotoIA. ' +
            'Pose-moi tes questions sur le Loto, les statistiques ou le moteur HYBRIDE \uD83D\uDE80',
            'bot'
        );

        /* ══════════════════════════════════
           Events
           ══════════════════════════════════ */

        bubble.addEventListener('click', toggle);
        closeBtn.addEventListener('click', close);
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
            if (!vvp || !root) return;
            root.style.setProperty('--vvp-height', vvp.height + 'px');
            root.style.top = vvp.offsetTop + 'px';
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
