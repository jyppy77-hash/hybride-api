/** FAQ EuroMillions — Accordion + DB Stats (English version) */
document.addEventListener('DOMContentLoaded', function() {
    // Accordion toggle
    document.querySelectorAll('.faq-item .faq-question').forEach(function(question) {
        question.addEventListener('click', function() {
            var item = this.closest('.faq-item');
            var wasActive = item.classList.contains('active');

            // Close all items in the same group
            item.closest('.faq-category').querySelectorAll('.faq-item').forEach(function(i) {
                i.classList.remove('active');
            });

            // Toggle the clicked item
            if (!wasActive) {
                item.classList.add('active');
            }
        });
    });

    // Load EuroMillions database stats
    fetch('/api/euromillions/database-info')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.exists) {
                document.querySelectorAll('.em-db-total').forEach(function(el) {
                    el.textContent = (data.total_draws || 0).toLocaleString('en-GB');
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
            console.error('Error loading EM database stats:', err);
        });
});
