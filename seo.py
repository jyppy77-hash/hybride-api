"""
SEO Module pour LotoIA — Source de vérité structured data.
==========================================================

Générateurs JSON-LD : Organization, SoftwareApplication, FAQPage, BreadcrumbList.

NOTE : Ces fonctions ne sont actuellement pas appelées par les routes/templates.
Les JSON-LD sont inline dans chaque template HTML pour performance et contrôle granulaire.
Ce module sert de **source de vérité** pour les données Organization, founder, et structured data.
Les fonctions peuvent être intégrées dans le pipeline de rendu dans une future refactorisation.
"""

import json

SITE_URL = "https://lotoia.fr"


# ============================================================================
# STRUCTURED DATA (JSON-LD)
# ============================================================================

def generate_jsonld_organization() -> str:
    """
    Schema.org Organization pour LotoIA.
    """
    return '''
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "LotoIA",
        "alternateName": "LotoIA.fr",
        "url": "https://lotoia.fr",
        "logo": "https://lotoia.fr/ui/static/logo-lotoia.png",
        "description": "Plateforme d'analyse statistique du Loto et de l'EuroMillions par intelligence artificielle",
        "foundingDate": "2025-01-01",
        "founder": {
            "@type": "Person",
            "name": "Jean-Philippe Godard",
            "alternateName": "JyppY",
            "jobTitle": "Fondateur & Lead Developer",
            "knowsAbout": ["Data Science", "Intelligence Artificielle", "Statistiques", "Probabilités"],
            "sameAs": ["https://www.linkedin.com/in/jpgodard/"]
        },
        "parentOrganization": {
            "@type": "Organization",
            "name": "EmovisIA",
            "url": "https://emovisia.fr"
        },
        "disambiguatingDescription": "Plateforme française d'analyse statistique du Loto et de l'EuroMillions par intelligence artificielle. Sans aucun lien avec les produits de literie ou les accessoires.",
        "sameAs": ["https://emovisia.fr"],
        "contactPoint": {
            "@type": "ContactPoint",
            "email": "contact@lotoia.fr",
            "contactType": "customer support",
            "availableLanguage": ["French", "English"]
        },
        "areaServed": "FR",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "3 rue Alexandre Riou",
            "addressLocality": "Machecoul-Saint-Même",
            "postalCode": "44270",
            "addressCountry": "FR"
        }
    }
    </script>
'''


def generate_jsonld_software_application() -> str:
    """
    Schema.org SoftwareApplication pour le moteur HYBRIDE.
    """
    return '''
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "LotoIA - Moteur HYBRIDE",
        "applicationCategory": "UtilitiesApplication",
        "operatingSystem": "Web",
        "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "EUR"
        },
        "description": "Moteur d'analyse statistique hybride pour l'exploration de grilles Loto"
    }
    </script>
'''


def generate_jsonld_faq(questions: list[tuple[str, str]]) -> str:
    """
    Schema.org FAQPage pour la page FAQ.

    Args:
        questions: Liste de tuples (question, réponse)
    """
    faq_items = []
    for q, a in questions:
        faq_items.append(f'''
        {{
            "@type": "Question",
            "name": {json.dumps(q)},
            "acceptedAnswer": {{
                "@type": "Answer",
                "text": {json.dumps(a)}
            }}
        }}''')

    items_json = ",".join(faq_items)

    return f'''
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [{items_json}
        ]
    }}
    </script>
'''


def generate_jsonld_breadcrumb(items: list[tuple[str, str]]) -> str:
    """
    Schema.org BreadcrumbList pour la navigation.

    Args:
        items: Liste de tuples (nom, url_path)
    """
    breadcrumb_items = []
    for i, (name, url) in enumerate(items, 1):
        breadcrumb_items.append(f'''
        {{
            "@type": "ListItem",
            "position": {i},
            "name": {json.dumps(name)},
            "item": {json.dumps(SITE_URL + url)}
        }}''')

    items_json = ",".join(breadcrumb_items)

    return f'''
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{items_json}
        ]
    }}
    </script>
'''
