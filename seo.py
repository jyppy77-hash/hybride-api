"""
SEO Module pour LotoIA
======================

Génération dynamique du sitemap.xml et optimisations SEO.
Compatible FastAPI / Cloud Run.
"""

from datetime import datetime, timezone
from typing import Optional
from fastapi import Response
from fastapi.responses import PlainTextResponse

# ============================================================================
# CONFIGURATION SEO
# ============================================================================

SITE_URL = "https://lotoia.fr"

# Pages avec priorité SEO et fréquence de mise à jour
# URLs SEO-friendly (sans .html)
SEO_PAGES = [
    # (path, priority, changefreq, lastmod_dynamic)
    ("/", 1.0, "daily", True),
    ("/generateur", 0.9, "daily", True),
    ("/statistiques", 0.9, "daily", True),
    ("/simulateur", 0.8, "weekly", False),
    ("/historique", 0.7, "daily", True),
    ("/faq", 0.6, "monthly", False),
    ("/actualites", 0.5, "weekly", True),
]

# Pages à exclure du sitemap (légales, noindex)
EXCLUDED_PAGES = [
    "/ui/mentions-legales.html",
    "/ui/politique-confidentialite.html",
    "/ui/politique-cookies.html",
    "/ui/disclaimer.html",
]


# ============================================================================
# GÉNÉRATION SITEMAP XML
# ============================================================================

def generate_sitemap_xml(last_tirage_date: Optional[str] = None) -> str:
    """
    Génère le sitemap.xml dynamique.

    Args:
        last_tirage_date: Date du dernier tirage (YYYY-MM-DD) pour lastmod dynamique

    Returns:
        XML string du sitemap
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lastmod_dynamic = last_tirage_date or today

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '        xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9',
        '        http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">',
        '',
        f'  <!-- LotoIA Sitemap - Generated {today} -->',
        '',
    ]

    for path, priority, changefreq, is_dynamic in SEO_PAGES:
        url = f"{SITE_URL}{path}" if path != "/" else SITE_URL
        lastmod = lastmod_dynamic if is_dynamic else today

        xml_parts.extend([
            '  <url>',
            f'    <loc>{url}</loc>',
            f'    <lastmod>{lastmod}</lastmod>',
            f'    <changefreq>{changefreq}</changefreq>',
            f'    <priority>{priority}</priority>',
            '  </url>',
        ])

    xml_parts.append('</urlset>')

    return '\n'.join(xml_parts)


def generate_sitemap_response(last_tirage_date: Optional[str] = None) -> Response:
    """
    Retourne une Response FastAPI avec le sitemap XML.
    Headers optimisés pour cache CDN.
    """
    xml_content = generate_sitemap_xml(last_tirage_date)

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Cache-Control": "public, max-age=3600",  # 1h cache
            "X-Robots-Tag": "noindex",  # Le sitemap lui-même n'est pas indexé
        }
    )


# ============================================================================
# GÉNÉRATION ROBOTS.TXT DYNAMIQUE (optionnel)
# ============================================================================

def generate_robots_txt() -> str:
    """
    Génère robots.txt dynamiquement (alternative au fichier statique).
    """
    return f"""# LotoIA - robots.txt
# {SITE_URL}/robots.txt

User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /

User-agent: *
Allow: /

# Blocage API
Disallow: /api/
Disallow: /health
Disallow: /debug-env

# Blocage pages légales
Disallow: /ui/mentions-legales.html
Disallow: /ui/politique-confidentialite.html
Disallow: /ui/politique-cookies.html

# Blocage scrapers
User-agent: AhrefsBot
Disallow: /

User-agent: SemrushBot
Disallow: /

User-agent: GPTBot
Disallow: /

Sitemap: {SITE_URL}/sitemap.xml
"""


def generate_robots_response() -> PlainTextResponse:
    """
    Retourne une Response FastAPI avec robots.txt.
    """
    return PlainTextResponse(
        content=generate_robots_txt(),
        headers={
            "Cache-Control": "public, max-age=86400",  # 24h cache
        }
    )


# ============================================================================
# META TAGS HELPERS
# ============================================================================

# Configuration meta par page
# URLs SEO-friendly (canonicals mis à jour)
PAGE_META = {
    "index": {
        "title": "LotoIA - Générateur de Grilles Loto par Intelligence Artificielle",
        "description": "Générez des grilles de Loto optimisées par IA. Analyse statistique de 967+ tirages FDJ, algorithme HYBRIDE_OPTIMAL_V1. 100% gratuit.",
        "keywords": "loto ia, générateur grille loto, prédiction loto, algorithme loto, intelligence artificielle loto, statistiques loto",
        "canonical": "/",
    },
    "loto": {
        "title": "Générateur Loto France - Grilles IA Optimisées | LotoIA",
        "description": "Créez vos grilles Loto France avec notre moteur IA. Analyse des numéros chauds/froids, scores de conformité statistique. Gratuit et sans inscription.",
        "keywords": "générateur loto france, grille loto gratuit, numéros loto, analyse loto fdj",
        "canonical": "/generateur",
    },
    "generateur": {
        "title": "Générateur Loto France - Grilles IA Optimisées | LotoIA",
        "description": "Créez vos grilles Loto France avec notre moteur IA. Analyse des numéros chauds/froids, scores de conformité statistique. Gratuit et sans inscription.",
        "keywords": "générateur loto france, grille loto gratuit, numéros loto, analyse loto fdj",
        "canonical": "/generateur",
    },
    "statistiques": {
        "title": "Statistiques Loto - Fréquences et Retards des Numéros | LotoIA",
        "description": "Consultez les statistiques complètes du Loto : numéros les plus sortis, retards actuels, tendances. Données issues de 967+ tirages officiels FDJ.",
        "keywords": "statistiques loto, fréquence numéros loto, retard loto, numéros chauds froids",
        "canonical": "/statistiques",
    },
    "simulateur": {
        "title": "Simulateur de Grille Loto - Analysez votre Combinaison | LotoIA",
        "description": "Testez votre grille Loto et obtenez un score IA. Notre simulateur analyse votre combinaison selon les statistiques historiques.",
        "keywords": "simulateur loto, analyser grille loto, score grille, test combinaison loto",
        "canonical": "/simulateur",
    },
    "faq": {
        "title": "FAQ LotoIA - Questions sur l'Algorithme et le Générateur",
        "description": "Toutes les réponses sur LotoIA : fonctionnement du moteur HYBRIDE, interprétation des scores, badges, et jeu responsable.",
        "keywords": "faq lotoia, comment fonctionne lotoia, algorithme hybride, aide loto ia",
        "canonical": "/faq",
    },
    "historique": {
        "title": "Historique des Tirages Loto - Base de Données FDJ | LotoIA",
        "description": "Consultez l'historique complet des tirages Loto France depuis 2019. Recherche par date, numéros gagnants et numéro chance.",
        "keywords": "historique tirages loto, résultats loto, archive tirages fdj, anciens tirages",
        "canonical": "/historique",
    },
    "news": {
        "title": "Actualités Loto et Mises à Jour LotoIA",
        "description": "Dernières actualités du Loto France et mises à jour de l'algorithme LotoIA. Super Loto, jackpots exceptionnels, nouvelles fonctionnalités.",
        "keywords": "actualités loto, news fdj, super loto, jackpot loto",
        "canonical": "/actualites",
    },
    "actualites": {
        "title": "Actualités Loto et Mises à Jour LotoIA",
        "description": "Dernières actualités du Loto France et mises à jour de l'algorithme LotoIA. Super Loto, jackpots exceptionnels, nouvelles fonctionnalités.",
        "keywords": "actualités loto, news fdj, super loto, jackpot loto",
        "canonical": "/actualites",
    },
}


def get_meta_tags(page_key: str) -> dict:
    """
    Retourne les meta tags pour une page donnée.
    """
    return PAGE_META.get(page_key, PAGE_META["index"])


def generate_meta_html(page_key: str, og_image: str = "/ui/static/og-lotoia.png") -> str:
    """
    Génère le bloc HTML complet des meta tags SEO.
    À insérer dans le <head> de chaque page.
    """
    meta = get_meta_tags(page_key)
    canonical_url = f"{SITE_URL}{meta['canonical']}"

    return f'''
    <!-- SEO Meta Tags -->
    <meta name="description" content="{meta['description']}">
    <meta name="keywords" content="{meta['keywords']}">
    <meta name="author" content="LotoIA - EmovisIA">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="{canonical_url}">

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:title" content="{meta['title']}">
    <meta property="og:description" content="{meta['description']}">
    <meta property="og:image" content="{SITE_URL}{og_image}">
    <meta property="og:locale" content="fr_FR">
    <meta property="og:site_name" content="LotoIA">

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:url" content="{canonical_url}">
    <meta name="twitter:title" content="{meta['title']}">
    <meta name="twitter:description" content="{meta['description']}">
    <meta name="twitter:image" content="{SITE_URL}{og_image}">
'''


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
        "description": "Générateur de grilles Loto par intelligence artificielle",
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
    Schema.org SoftwareApplication pour le générateur.
    """
    return '''
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "LotoIA - Générateur de Grilles",
        "applicationCategory": "UtilitiesApplication",
        "operatingSystem": "Web",
        "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "EUR"
        },
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": "4.5",
            "ratingCount": "127"
        },
        "description": "Générateur de grilles Loto optimisées par algorithme IA HYBRIDE_OPTIMAL_V1"
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
        items: Liste de tuples (nom, url)
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
