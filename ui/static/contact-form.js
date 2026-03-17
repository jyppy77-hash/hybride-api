/* ══════════════════════════════════════════════════════════════
   Formulaire de Contact — Modal réutilisable
   Ouvert depuis footer, chatbot, page à propos
   ══════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    var LI = window.LotoIA_i18n || {};

    // ── Public API ──
    window.LotoIAContact = {
        openModal: openModal
    };

    var modalEl = null;

    function openModal(pageSource) {
        if (modalEl) {
            modalEl.style.display = 'flex';
            return;
        }
        createModal(pageSource || window.location.pathname);
    }

    function closeModal() {
        if (modalEl) {
            modalEl.style.display = 'none';
        }
    }

    function createModal(pageSource) {
        // Overlay
        modalEl = document.createElement('div');
        modalEl.className = 'contact-modal-overlay';
        modalEl.addEventListener('click', function (e) {
            if (e.target === modalEl) closeModal();
        });

        // Modal
        var modal = document.createElement('div');
        modal.className = 'contact-modal';

        // Header
        var header = document.createElement('div');
        header.className = 'contact-modal-header';
        var title = document.createElement('h3');
        title.textContent = LI.contact_title || 'Nous contacter';
        var closeBtn = document.createElement('button');
        closeBtn.className = 'contact-modal-close';
        closeBtn.textContent = '\u2715';
        closeBtn.addEventListener('click', closeModal);
        header.appendChild(title);
        header.appendChild(closeBtn);
        modal.appendChild(header);

        // Form
        var form = document.createElement('form');
        form.className = 'contact-form';
        form.addEventListener('submit', function (e) { e.preventDefault(); });

        // Honeypot (hidden)
        var honey = document.createElement('input');
        honey.type = 'text';
        honey.name = '_honey';
        honey.id = 'contact-honey';
        honey.style.cssText = 'display:none !important';
        honey.tabIndex = -1;
        honey.autocomplete = 'off';
        form.appendChild(honey);

        // Nom
        form.appendChild(makeInput('text', 'contact-nom', LI.contact_nom || 'Votre nom (optionnel)', false));

        // Email
        form.appendChild(makeInput('email', 'contact-email', LI.contact_email || 'Votre email (optionnel)', false));

        // Sujet
        var sujetWrap = document.createElement('div');
        sujetWrap.className = 'contact-field';
        var sujet = document.createElement('select');
        sujet.id = 'contact-sujet';
        sujet.className = 'contact-select';
        var sujets = [
            { value: 'question', label: LI.contact_sujet_question || 'Question' },
            { value: 'suggestion', label: LI.contact_sujet_suggestion || 'Suggestion' },
            { value: 'bug', label: LI.contact_sujet_bug || 'Signaler un bug' },
            { value: 'autre', label: LI.contact_sujet_autre || 'Autre' }
        ];
        for (var i = 0; i < sujets.length; i++) {
            var opt = document.createElement('option');
            opt.value = sujets[i].value;
            opt.textContent = sujets[i].label;
            sujet.appendChild(opt);
        }
        sujetWrap.appendChild(sujet);
        form.appendChild(sujetWrap);

        // Message
        var msgWrap = document.createElement('div');
        msgWrap.className = 'contact-field';
        var textarea = document.createElement('textarea');
        textarea.id = 'contact-message';
        textarea.className = 'contact-textarea';
        textarea.placeholder = LI.contact_message || 'Votre message';
        textarea.maxLength = 2000;
        textarea.rows = 5;
        textarea.required = true;

        var msgFooter = document.createElement('div');
        msgFooter.className = 'contact-field-footer';
        var minLabel = document.createElement('span');
        minLabel.className = 'contact-min-label';
        minLabel.textContent = LI.contact_message_min || 'Minimum 10 caractères';
        var counter = document.createElement('span');
        counter.className = 'contact-counter';
        counter.textContent = (LI.contact_counter || '{n} / 2000').replace('{n}', '0');

        textarea.addEventListener('input', function () {
            var n = textarea.value.length;
            counter.textContent = (LI.contact_counter || '{n} / 2000').replace('{n}', String(n));
            submitBtn.disabled = n < 10;
            if (n >= 10) { minLabel.style.display = 'none'; }
            else { minLabel.style.display = ''; }
        });

        msgFooter.appendChild(minLabel);
        msgFooter.appendChild(counter);
        msgWrap.appendChild(textarea);
        msgWrap.appendChild(msgFooter);
        form.appendChild(msgWrap);

        // Submit button
        var submitBtn = document.createElement('button');
        submitBtn.type = 'button';
        submitBtn.className = 'contact-submit-btn';
        submitBtn.textContent = LI.contact_submit || 'Envoyer';
        submitBtn.disabled = true;

        // Feedback
        var feedback = document.createElement('div');
        feedback.className = 'contact-feedback';
        feedback.id = 'contact-feedback';

        submitBtn.addEventListener('click', function () {
            var msg = textarea.value.trim();
            if (msg.length < 10) return;

            submitBtn.disabled = true;
            submitBtn.textContent = '...';

            var payload = {
                nom: document.getElementById('contact-nom').value.trim() || null,
                email: document.getElementById('contact-email').value.trim() || null,
                sujet: sujet.value,
                message: msg,
                page_source: pageSource,
                lang: window.LotoIA_lang || 'fr',
                _honey: honey.value
            };

            fetch('/api/contact', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function (res) {
                if (res.ok) {
                    feedback.textContent = LI.contact_success || 'Message envoyé, merci !';
                    feedback.className = 'contact-feedback contact-feedback-ok';
                    form.reset();
                    counter.textContent = (LI.contact_counter || '{n} / 2000').replace('{n}', '0');
                    setTimeout(closeModal, 2500);
                } else {
                    feedback.textContent = LI.contact_error || 'Erreur, veuillez réessayer';
                    feedback.className = 'contact-feedback contact-feedback-err';
                }
            })
            .catch(function () {
                feedback.textContent = LI.contact_error || 'Erreur, veuillez réessayer';
                feedback.className = 'contact-feedback contact-feedback-err';
            })
            .finally(function () {
                submitBtn.textContent = LI.contact_submit || 'Envoyer';
                submitBtn.disabled = false;
            });
        });

        form.appendChild(submitBtn);
        form.appendChild(feedback);
        modal.appendChild(form);
        modalEl.appendChild(modal);
        document.body.appendChild(modalEl);

        // Escape key
        document.addEventListener('keydown', function (e) {
            if ((e.key === 'Escape' || e.keyCode === 27) && modalEl && modalEl.style.display !== 'none') {
                closeModal();
            }
        });
    }

    function makeInput(type, id, placeholder, required) {
        var wrap = document.createElement('div');
        wrap.className = 'contact-field';
        var input = document.createElement('input');
        input.type = type;
        input.id = id;
        input.className = 'contact-input';
        input.placeholder = placeholder;
        if (required) input.required = true;
        wrap.appendChild(input);
        return wrap;
    }

})();
