"""
SEO Module pour LotoIA
======================

Helpers SEO : génération de structured data JSON-LD.
Le sitemap.xml et robots.txt sont servis comme fichiers statiques.
"""

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
        "description": "Plateforme d'analyse statistique du Loto par intelligence artificielle",
        "foundingDate": "2024",
        "founder": {
            "@type": "Organization",
            "name": "EmovisIA"
        },
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
            "name": "{q}",
            "acceptedAnswer": {{
                "@type": "Answer",
                "text": "{a}"
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
            "name": "{name}",
            "item": "{SITE_URL}{url}"
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
