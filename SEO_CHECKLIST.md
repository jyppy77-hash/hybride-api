# CHECKLIST SEO — LotoIA

## STATUT GLOBAL

| Catégorie | Score | Statut |
|-----------|-------|--------|
| Indexabilité | 3/10 | A corriger |
| Meta Tags | 2/10 | Critique |
| Performance | 6/10 | Moyen |
| Mobile | 8/10 | Bon |
| Structured Data | 0/10 | Absent |

---

## P0 — CRITIQUE (Impact SEO majeur)

### Indexabilité

- [ ] **Créer /robots.txt** → Fichier créé dans `ui/robots.txt`
  - Route dynamique ajoutée : `GET /robots.txt`

- [ ] **Créer /sitemap.xml** → Fichier créé dans `ui/sitemap.xml`
  - Route dynamique ajoutée : `GET /sitemap.xml`
  - Soumettre dans Google Search Console

- [ ] **Soumettre sitemap à Google Search Console**
  ```
  https://search.google.com/search-console
  → Sitemaps → Ajouter : https://lotoia.fr/sitemap.xml
  ```

### Meta Tags (Chaque page)

- [ ] **index.html** : Ajouter meta description + OG + Twitter + canonical
- [ ] **loto.html** : Ajouter meta description + OG + Twitter + canonical
- [ ] **statistiques.html** : Ajouter meta description + OG + Twitter + canonical
- [ ] **simulateur.html** : Ajouter meta description + OG + Twitter + canonical
- [ ] **faq.html** : Meta OK, ajouter OG + Twitter + canonical
- [ ] **historique.html** : Ajouter meta description + OG + Twitter + canonical
- [ ] **news.html** : Ajouter meta description + OG + Twitter + canonical

### Duplication de contenu

- [ ] **Résoudre index.html ≈ loto.html**
  - Option A : Supprimer loto.html, rediriger vers index.html
  - Option B : Différencier le contenu (index = landing, loto = générateur)
  - Option C : Canonical de loto.html vers index.html

### Structured Data

- [ ] **Ajouter JSON-LD Organization** sur index.html
- [ ] **Ajouter JSON-LD WebApplication** sur index.html
- [ ] **Ajouter JSON-LD FAQPage** sur faq.html

---

## P1 — IMPORTANT (Impact SEO significatif)

### Titles optimisés

| Page | Actuel | Recommandé |
|------|--------|------------|
| index.html | "LotoIA - Analyse Intelligente du Loto" | "LotoIA - Générateur de Grilles Loto par IA" |
| loto.html | "LotoIA - Analyse Intelligente du Loto" | "Générateur Loto France - Grilles IA \| LotoIA" |
| statistiques.html | "LotoIA - Statistiques" | "Statistiques Loto - Fréquences Numéros \| LotoIA" |
| simulateur.html | "LotoIA - Simulateur de Grille" | "Simulateur Grille Loto - Analysez vos Numéros \| LotoIA" |

### Performance

- [ ] **Ajouter preload CSS/JS** dans chaque `<head>`
  ```html
  <link rel="preload" href="/static/style.css" as="style">
  <link rel="preload" href="/static/app.js" as="script">
  ```

- [ ] **Extraire CSS inline de statistiques.html** vers fichier externe

- [ ] **Activer compression GZip**
  ```python
  # main.py
  from fastapi.middleware.gzip import GZipMiddleware
  app.add_middleware(GZipMiddleware, minimum_size=500)
  ```

- [ ] **Configurer cache headers**
  - CSS/JS : 7 jours
  - Images : 30 jours
  - HTML : 1 heure

### Images

- [ ] **Créer image OG** (1200x630px) : `ui/static/og-lotoia.png`
- [ ] **Créer favicon set** : 16x16, 32x32, apple-touch-icon
- [ ] **Ajouter lazy loading** sur images below the fold

---

## P2 — OPTIONNEL (Quick wins)

- [ ] **Ajouter manifest.json** pour PWA
- [ ] **Ajouter hreflang** si expansion internationale
- [ ] **Breadcrumbs JSON-LD** sur pages profondes
- [ ] **Minifier CSS/JS** en production
- [ ] **Convertir images en WebP**

---

## CORE WEB VITALS

### LCP (Largest Contentful Paint) — Cible < 2.5s

- [ ] Preload hero section CSS
- [ ] Optimiser taille image header (si présente)
- [ ] Éviter render-blocking JS
- [ ] Cloud Run : min-instances=1 pour éviter cold start

### CLS (Cumulative Layout Shift) — Cible < 0.1

- [ ] Définir width/height sur toutes les images
- [ ] Réserver espace pour éléments dynamiques (grilles générées)
- [ ] Font-display: swap sur fonts

### INP (Interaction to Next Paint) — Cible < 200ms

- [ ] Code JS actuel semble léger ✓
- [ ] Éviter long tasks JS
- [ ] Debounce inputs si nécessaire

---

## COMMANDES POST-DÉPLOIEMENT

```bash
# 1. Vérifier robots.txt
curl https://lotoia.fr/robots.txt

# 2. Vérifier sitemap.xml
curl https://lotoia.fr/sitemap.xml

# 3. Tester mobile-friendly
# https://search.google.com/test/mobile-friendly?url=https://lotoia.fr

# 4. PageSpeed Insights
# https://pagespeed.web.dev/analysis?url=https://lotoia.fr

# 5. Rich Results Test
# https://search.google.com/test/rich-results?url=https://lotoia.fr
```

---

## GOOGLE SEARCH CONSOLE — Actions

1. Vérifier la propriété `https://lotoia.fr`
2. Soumettre sitemap.xml
3. Demander indexation des pages principales
4. Vérifier couverture d'indexation après 48h
5. Monitorer Core Web Vitals

---

## TIMELINE RECOMMANDÉE

### Semaine 1 (Critique)
- [ ] Déployer robots.txt + sitemap.xml
- [ ] Ajouter meta tags sur toutes les pages
- [ ] Soumettre sitemap à GSC
- [ ] Résoudre duplication index/loto

### Semaine 2 (Important)
- [ ] Ajouter JSON-LD structured data
- [ ] Créer image OG + favicons
- [ ] Configurer cache headers
- [ ] Activer GZip

### Semaine 3+ (Optimisation)
- [ ] Monitorer Core Web Vitals
- [ ] A/B test titles
- [ ] Créer contenu long-tail (blog)
