/**
 * FAQ EuroMillions — Accordion + Stats BDD
 */
var LI = window.LotoIA_i18n || {};

document.addEventListener('DOMContentLoaded', function() {
    // Accordion toggle
    document.querySelectorAll('.faq-item .faq-question').forEach(function(question) {
        question.addEventListener('click', function() {
            var item = this.closest('.faq-item');
            var wasActive = item.classList.contains('active');

            // Fermer tous les items du meme groupe
            var group = item.closest('.faq-category') || item.closest('.mini-faq-container');
            if (group) {
                group.querySelectorAll('.faq-item').forEach(function(i) {
                    i.classList.remove('active');
                });
            }

            // Toggle l'item clique
            if (!wasActive) {
                item.classList.add('active');
            }
        });
    });

    // Charger les stats BDD EuroMillions
    fetch('/api/euromillions/database-info')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.exists) {
                document.querySelectorAll('.em-db-total').forEach(function(el) {
                    el.textContent = (data.total_draws || 0).toLocaleString(LI.locale);
                });

                document.querySelectorAll('.em-db-first-date').forEach(function(el) {
                    el.textContent = data.first_draw || '';
                });

                document.querySelectorAll('.em-db-last-date').forEach(function(el) {
                    el.textContent = data.last_draw || '';
                });
            }
        })
        .catch(function(err) {
            console.error('Erreur chargement stats BDD EM:', err);
        });
});
