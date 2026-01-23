# SEO SNIPPETS — LotoIA

Snippets HTML prêts à copier-coller dans le `<head>` de chaque page.

---

## PAGE: index.html / Page d'accueil

```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <!-- Title optimisé SEO -->
    <title>LotoIA - Générateur de Grilles Loto par Intelligence Artificielle</title>

    <!-- Meta SEO -->
    <meta name="description" content="Générez des grilles de Loto optimisées par IA. Analyse statistique de 967+ tirages FDJ, algorithme HYBRIDE_OPTIMAL_V1. 100% gratuit.">
    <meta name="keywords" content="loto ia, générateur grille loto, prédiction loto, algorithme loto, intelligence artificielle loto, statistiques loto">
    <meta name="author" content="LotoIA - EmovisIA">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://lotoia.fr/">

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://lotoia.fr/">
    <meta property="og:title" content="LotoIA - Générateur de Grilles Loto par IA">
    <meta property="og:description" content="Générez des grilles de Loto optimisées par intelligence artificielle. Analyse de 967+ tirages officiels FDJ.">
    <meta property="og:image" content="https://lotoia.fr/ui/static/og-lotoia.png">
    <meta property="og:locale" content="fr_FR">
    <meta property="og:site_name" content="LotoIA">

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:url" content="https://lotoia.fr/">
    <meta name="twitter:title" content="LotoIA - Générateur de Grilles Loto par IA">
    <meta name="twitter:description" content="Générez des grilles de Loto optimisées par intelligence artificielle.">
    <meta name="twitter:image" content="https://lotoia.fr/ui/static/og-lotoia.png">

    <!-- Favicon -->
    <link rel="icon" type="image/png" sizes="32x32" href="/ui/static/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="/ui/static/favicon-16x16.png">
    <link rel="apple-touch-icon" sizes="180x180" href="/ui/static/apple-touch-icon.png">

    <!-- Preload ressources critiques -->
    <link rel="preload" href="/static/style.css" as="style">
    <link rel="preload" href="/static/app.js" as="script">
    <link rel="preconnect" href="https://fonts.googleapis.com">

    <!-- CSS -->
    <link rel="stylesheet" href="/static/style.css">
    <link rel="stylesheet" href="/static/sponsor-popup.css">

    <!-- Theme (anti-flash) -->
    <script src="/static/theme.js"></script>
</head>
```

**JSON-LD à ajouter avant `</body>` :**

```html
<!-- Structured Data -->
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": "LotoIA",
    "url": "https://lotoia.fr",
    "description": "Générateur de grilles Loto par intelligence artificielle",
    "applicationCategory": "UtilitiesApplication",
    "operatingSystem": "Web",
    "offers": {
        "@type": "Offer",
        "price": "0",
        "priceCurrency": "EUR"
    },
    "author": {
        "@type": "Organization",
        "name": "EmovisIA",
        "url": "https://lotoia.fr"
    }
}
</script>

<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": "LotoIA",
    "url": "https://lotoia.fr",
    "logo": "https://lotoia.fr/ui/static/logo-lotoia.png",
    "sameAs": [],
    "address": {
        "@type": "PostalAddress",
        "streetAddress": "3 rue Alexandre Riou",
        "addressLocality": "Machecoul-Saint-Même",
        "postalCode": "44270",
        "addressCountry": "FR"
    }
}
</script>
```

---

## PAGE: loto.html / Générateur Loto France

```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Générateur Loto France - Grilles IA Optimisées | LotoIA</title>

    <meta name="description" content="Créez vos grilles Loto France avec notre moteur IA. Analyse des numéros chauds/froids, scores de conformité statistique. Gratuit et sans inscription.">
    <meta name="keywords" content="générateur loto france, grille loto gratuit, numéros loto, analyse loto fdj, tirage loto">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://lotoia.fr/ui/loto.html">

    <!-- Open Graph -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://lotoia.fr/ui/loto.html">
    <meta property="og:title" content="Générateur Loto France - Grilles IA Optimisées">
    <meta property="og:description" content="Créez vos grilles Loto France avec notre moteur IA HYBRIDE_OPTIMAL_V1.">
    <meta property="og:image" content="https://lotoia.fr/ui/static/og-lotoia.png">
    <meta property="og:locale" content="fr_FR">
    <meta property="og:site_name" content="LotoIA">

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Générateur Loto France - Grilles IA">
    <meta name="twitter:description" content="Créez vos grilles Loto France optimisées par IA.">
    <meta name="twitter:image" content="https://lotoia.fr/ui/static/og-lotoia.png">

    <!-- ... reste du head ... -->
</head>
```

---

## PAGE: statistiques.html

```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Statistiques Loto - Fréquences et Retards des Numéros | LotoIA</title>

    <meta name="description" content="Consultez les statistiques complètes du Loto : numéros les plus sortis, retards actuels, tendances. Données issues de 967+ tirages officiels FDJ.">
    <meta name="keywords" content="statistiques loto, fréquence numéros loto, retard loto, numéros chauds froids, analyse tirages">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://lotoia.fr/ui/statistiques.html">

    <!-- Open Graph -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://lotoia.fr/ui/statistiques.html">
    <meta property="og:title" content="Statistiques Loto - Fréquences et Retards">
    <meta property="og:description" content="Statistiques complètes du Loto : numéros chauds, froids, retards. 967+ tirages analysés.">
    <meta property="og:image" content="https://lotoia.fr/ui/static/og-stats.png">
    <meta property="og:locale" content="fr_FR">

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Statistiques Loto - LotoIA">
    <meta name="twitter:description" content="Statistiques complètes du Loto France.">
    <meta name="twitter:image" content="https://lotoia.fr/ui/static/og-stats.png">

    <!-- ... reste du head ... -->
</head>
```

---

## PAGE: simulateur.html

```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Simulateur de Grille Loto - Analysez votre Combinaison | LotoIA</title>

    <meta name="description" content="Testez votre grille Loto et obtenez un score IA. Notre simulateur analyse votre combinaison selon les statistiques historiques de 967+ tirages.">
    <meta name="keywords" content="simulateur loto, analyser grille loto, score grille, test combinaison loto, vérifier numéros">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://lotoia.fr/ui/simulateur.html">

    <!-- Open Graph -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://lotoia.fr/ui/simulateur.html">
    <meta property="og:title" content="Simulateur de Grille Loto">
    <meta property="og:description" content="Testez votre grille Loto et obtenez un score d'analyse IA.">
    <meta property="og:image" content="https://lotoia.fr/ui/static/og-simulateur.png">
    <meta property="og:locale" content="fr_FR">

    <!-- ... reste du head ... -->
</head>
```

---

## PAGE: faq.html

```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>FAQ LotoIA - Questions sur l'Algorithme et le Générateur</title>

    <meta name="description" content="Toutes les réponses sur LotoIA : fonctionnement du moteur HYBRIDE_OPTIMAL_V1, interprétation des scores et badges, jeu responsable.">
    <meta name="keywords" content="faq lotoia, comment fonctionne lotoia, algorithme hybride, aide loto ia, questions loto">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://lotoia.fr/ui/faq.html">

    <!-- Open Graph -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://lotoia.fr/ui/faq.html">
    <meta property="og:title" content="FAQ LotoIA - Questions Fréquentes">
    <meta property="og:description" content="Toutes les réponses sur le fonctionnement de LotoIA.">
    <meta property="og:image" content="https://lotoia.fr/ui/static/og-lotoia.png">

    <!-- ... reste du head ... -->
</head>
```

**JSON-LD FAQPage à ajouter avant `</body>` :**

```html
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
        {
            "@type": "Question",
            "name": "Comment fonctionne l'algorithme HYBRIDE_OPTIMAL_V1 ?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "L'algorithme HYBRIDE_OPTIMAL_V1 analyse 967+ tirages officiels FDJ en combinant fréquences et retards des numéros. Il utilise une fenêtre principale de 5 ans (60% du poids) et une fenêtre récente de 2 ans (40%)."
            }
        },
        {
            "@type": "Question",
            "name": "LotoIA garantit-il de gagner au Loto ?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Non. LotoIA est un outil d'analyse statistique. Le Loto reste un jeu de hasard avec des probabilités fixes. Notre outil aide à choisir des numéros selon des critères statistiques, mais ne prédit pas les tirages."
            }
        },
        {
            "@type": "Question",
            "name": "Le service est-il gratuit ?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Oui, LotoIA est 100% gratuit et sans inscription. Générez autant de grilles que vous le souhaitez."
            }
        }
    ]
}
</script>
```

---

## PAGE: historique.html

```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Historique des Tirages Loto - Base de Données FDJ | LotoIA</title>

    <meta name="description" content="Consultez l'historique complet des tirages Loto France depuis 2019. Recherche par date, numéros gagnants et numéro chance. 967+ tirages disponibles.">
    <meta name="keywords" content="historique tirages loto, résultats loto, archive tirages fdj, anciens tirages, recherche tirage">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://lotoia.fr/ui/historique.html">

    <!-- Open Graph -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://lotoia.fr/ui/historique.html">
    <meta property="og:title" content="Historique des Tirages Loto France">
    <meta property="og:description" content="Base de données complète des tirages Loto depuis 2019.">
    <meta property="og:image" content="https://lotoia.fr/ui/static/og-lotoia.png">

    <!-- ... reste du head ... -->
</head>
```

---

## PERFORMANCE: Preload / Prefetch

À ajouter dans le `<head>` de toutes les pages :

```html
<!-- Preload CSS critique -->
<link rel="preload" href="/static/style.css" as="style">

<!-- Preload JS critique -->
<link rel="preload" href="/static/app.js" as="script">

<!-- Prefetch pages secondaires (navigation anticipée) -->
<link rel="prefetch" href="/ui/statistiques.html">
<link rel="prefetch" href="/ui/simulateur.html">

<!-- DNS Prefetch (si APIs externes) -->
<link rel="dns-prefetch" href="//fonts.googleapis.com">
```

---

## CACHE HEADERS (à configurer côté FastAPI/Cloud Run)

Ajouter ce middleware dans `main.py` :

```python
from fastapi import Request
from fastapi.responses import Response

@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)

    path = request.url.path

    # Cache long pour assets statiques
    if path.startswith("/static/") or path.startswith("/ui/static/"):
        if path.endswith((".css", ".js")):
            response.headers["Cache-Control"] = "public, max-age=604800"  # 7 jours
        elif path.endswith((".png", ".jpg", ".svg", ".ico")):
            response.headers["Cache-Control"] = "public, max-age=2592000"  # 30 jours

    # Cache court pour HTML
    elif path.endswith(".html") or path == "/":
        response.headers["Cache-Control"] = "public, max-age=3600"  # 1 heure

    return response
```

---

## COMPRESSION (Cloud Run)

Cloud Run gère automatiquement la compression gzip. Pour Brotli, ajouter :

```python
# requirements.txt
brotli==1.1.0

# main.py
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=500)
```

---

## IMAGES: Lazy Loading

Dans les templates HTML :

```html
<!-- Images sous le fold -->
<img src="/ui/static/promo.png"
     alt="Description"
     loading="lazy"
     decoding="async"
     width="400"
     height="300">

<!-- Image critique (au-dessus du fold) -->
<img src="/ui/static/hero.png"
     alt="Description"
     fetchpriority="high"
     width="800"
     height="400">
```
