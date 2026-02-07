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
                win.classList.add('visible');
                bubble.classList.add('open');
                input.focus();
            } else {
                win.classList.remove('visible');
                bubble.classList.remove('open');
            }
        }

        function close() {
            if (!isOpen) return;
            isOpen = false;
            win.classList.remove('visible');
            bubble.classList.remove('open');
        }

        /* ══════════════════════════════════
           Reponses mock
           ══════════════════════════════════ */

        var GREETINGS = ['bonjour', 'hello', 'salut', 'coucou', 'hey', 'bonsoir'];

        var GREETING_REPLY =
            '\uD83D\uDC4B Bonjour ! Je suis HYBRIDE, l\u2019assistant IA de LotoIA. ' +
            'Je serai bient\u00f4t op\u00e9rationnel !';

        var DEFAULT_REPLY =
            '\uD83E\uDD16 HYBRIDE est en cours de configuration. ' +
            'Bient\u00f4t je pourrai analyser vos grilles et r\u00e9pondre ' +
            '\u00e0 vos questions sur le Loto !';

        function getMockReply(userText) {
            var lower = userText.toLowerCase().trim();
            for (var i = 0; i < GREETINGS.length; i++) {
                if (lower.indexOf(GREETINGS[i]) !== -1) {
                    return GREETING_REPLY;
                }
            }
            return DEFAULT_REPLY;
        }

        /* ══════════════════════════════════
           Envoi message
           ══════════════════════════════════ */

        function send() {
            var text = input.value.trim();
            if (!text) return;

            addMessage(text, 'user');
            input.value = '';

            var reply = getMockReply(text);

            showTyping();

            setTimeout(function () {
                removeTyping();
                addMessage(reply, 'bot');
            }, 800);
        }

        /* ══════════════════════════════════
           Message d'accueil
           ══════════════════════════════════ */

        addMessage(
            'Bienvenue ! Je suis HYBRIDE, l\u2019assistant IA de LotoIA. ' +
            'Je suis en cours de configuration \u2014 bient\u00f4t op\u00e9rationnel !',
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

    }); // fin onReady
})(); // fin IIFE
