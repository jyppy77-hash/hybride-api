/**
 * FAQ Accordeon interactif
 * Gere l'ouverture/fermeture des questions FAQ
 */

document.addEventListener('DOMContentLoaded', () => {
    const faqItems = document.querySelectorAll('.faq-item');

    faqItems.forEach(item => {
        const question = item.querySelector('.faq-question');

        if (question) {
            question.addEventListener('click', () => {
                // Toggle l'item clique
                item.classList.toggle('active');

                // Analytics GA4 — Track ouverture FAQ
                if (item.classList.contains('active')) {
                    try { if (window.LotoIAAnalytics && window.LotoIAAnalytics.ux) { window.LotoIAAnalytics.ux.faqOpen(question.textContent.trim()); } } catch(e) {}
                }

                // Optionnel : Fermer les autres items (accordeon exclusif)
                // Decommenter pour activer le mode exclusif
                /*
                faqItems.forEach(otherItem => {
                    if (otherItem !== item) {
                        otherItem.classList.remove('active');
                    }
                });
                */
            });
        }
    });

    // Scroll smooth vers FAQ si hash #faq dans URL
    if (window.location.hash === '#faq') {
        setTimeout(() => {
            const faqSection = document.getElementById('faq');
            if (faqSection) {
                faqSection.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        }, 100);
    }

    // Chargement dynamique des stats base de donnees
    fetch('/api/database-info')
        .then(r => r.json())
        .then(data => {
            if (!data.total_draws) return;

            const fmt = (iso, long) => {
                const d = new Date(iso + 'T00:00:00');
                if (isNaN(d)) return null;
                return long
                    ? d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })
                    : d.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
            };

            document.querySelectorAll('.db-total').forEach(el => {
                el.textContent = data.total_draws.toLocaleString('fr-FR');
            });
            document.querySelectorAll('.db-first-date').forEach((el, i) => {
                const txt = fmt(data.first_draw, i > 0);
                if (txt) el.textContent = txt;
            });
            document.querySelectorAll('.db-last-date').forEach((el, i) => {
                const txt = fmt(data.last_draw, i > 0);
                if (txt) el.textContent = txt;
            });
        })
        .catch(() => { /* fallback HTML statique conserve */ });
});
