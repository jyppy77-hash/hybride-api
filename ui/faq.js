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
});
