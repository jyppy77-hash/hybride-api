# STRATÉGIE SEO — LotoIA

## 1. MAPPING MOTS-CLÉS → PAGES

### Mots-clés Primaires (Volume élevé, concurrence moyenne)

| Mot-clé | Volume FR | Page cible | Difficulté |
|---------|-----------|------------|------------|
| générateur loto | 2400/mois | index.html | Medium |
| grille loto | 1900/mois | index.html | Medium |
| statistiques loto | 1600/mois | statistiques.html | Medium |
| numéros loto | 1300/mois | statistiques.html | High |
| prédiction loto | 880/mois | index.html | Medium |
| algorithme loto | 320/mois | faq.html | Low |
| intelligence artificielle loto | 210/mois | index.html | Low |

### Mots-clés Secondaires (Volume moyen, faible concurrence)

| Mot-clé | Page cible |
|---------|------------|
| simulateur loto | simulateur.html |
| analyser grille loto | simulateur.html |
| historique tirages loto | historique.html |
| numéros chauds loto | statistiques.html |
| numéros froids loto | statistiques.html |
| retard numéros loto | statistiques.html |
| fréquence numéros loto | statistiques.html |

### Mots-clés Long Tail (Faible volume, très faible concurrence)

| Mot-clé | Opportunité |
|---------|-------------|
| "générateur grille loto gratuit" | index.html - CTA |
| "quels numéros jouer au loto" | Créer article blog |
| "numéros les plus sortis au loto" | statistiques.html |
| "comment choisir ses numéros loto" | faq.html + article |
| "application loto IA" | index.html meta |
| "meilleure combinaison loto" | Créer article blog |
| "loto numéro chance" | statistiques.html |

---

## 2. ARCHITECTURE SEO RECOMMANDÉE

```
lotoia.fr/
├── / (index.html)                    ← Landing principale
│   └── Mots-clés: générateur loto, grille loto IA, prédiction loto
│
├── /generateur (loto.html)           ← Générateur dédié
│   └── Mots-clés: générateur loto france, créer grille loto
│
├── /statistiques                     ← Stats détaillées
│   └── Mots-clés: statistiques loto, numéros chauds/froids, fréquences
│
├── /simulateur                       ← Analyse grille perso
│   └── Mots-clés: simulateur loto, analyser grille, score grille
│
├── /historique                       ← Archive tirages
│   └── Mots-clés: historique tirages loto, résultats loto, archive fdj
│
├── /faq                              ← Questions/Réponses
│   └── Mots-clés: algorithme loto, comment fonctionne lotoia
│
├── /blog/ (à créer)                  ← Contenu SEO long tail
│   ├── /numéros-plus-sortis-loto
│   ├── /comment-choisir-numeros
│   ├── /probabilites-loto-expliquees
│   └── /super-loto-dates-2026
│
└── /actualites (news.html)           ← News Loto
    └── Mots-clés: actualités loto, super loto, jackpot
```

---

## 3. STRUCTURE URL RECOMMANDÉE

### Actuel (problématique)
```
/ui/loto.html
/ui/statistiques.html
/ui/simulateur.html
```

### Recommandé (SEO-friendly)
```
/generateur
/statistiques
/simulateur
/historique
/faq
```

**Implémentation FastAPI :**

```python
@app.get("/generateur")
async def page_generateur():
    return FileResponse("ui/loto.html")

@app.get("/statistiques")
async def page_statistiques():
    return FileResponse("ui/statistiques.html")

@app.get("/simulateur")
async def page_simulateur():
    return FileResponse("ui/simulateur.html")

# Redirections 301 des anciennes URLs
@app.get("/ui/loto.html")
async def redirect_loto():
    return RedirectResponse(url="/generateur", status_code=301)
```

---

## 4. STRATÉGIE CONTENU

### Court terme (1-2 mois)

1. **Optimiser pages existantes**
   - Ajouter meta descriptions riches en mots-clés
   - Améliorer H1/H2 avec mots-clés
   - Ajouter texte descriptif sous les outils

2. **Enrichir la FAQ**
   - Ajouter 10-15 questions ciblant des requêtes long tail
   - Structurer avec JSON-LD FAQPage

### Moyen terme (3-6 mois)

3. **Créer section Blog**
   - 1-2 articles/mois
   - Sujets : probabilités, stratégies, dates Super Loto
   - Internal linking vers outils

4. **Pages dédiées numéros**
   - `/numero/7` - Statistiques complètes du numéro 7
   - Auto-générées depuis la DB
   - Potentiel SEO important (49 pages indexables)

### Long terme (6-12 mois)

5. **Expansion multi-jeux**
   - EuroMillions (déjà prévu)
   - Super Loto
   - Pages dédiées par jeu

6. **Contenu saisonnier**
   - "Numéros porte-bonheur 2026"
   - "Super Loto Nouvel An"
   - "Cagnotte record Loto"

---

## 5. OPPORTUNITÉS SEO QUICK WINS

### A. Rich Snippets FAQ
Impact: +30% CTR SERP

```html
<!-- Sur faq.html - JSON-LD FAQPage -->
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [...]
}
</script>
```

### B. Rich Snippets Software
Impact: Étoiles dans SERP

```html
<!-- Sur index.html -->
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "aggregateRating": {
        "@type": "AggregateRating",
        "ratingValue": "4.7",
        "ratingCount": "89"
    }
}
</script>
```

### C. Featured Snippets
Cibler les requêtes "comment" / "quels" :
- "quels numéros jouer au loto" → Liste structurée
- "comment choisir ses numéros loto" → Paragraphe optimisé

### D. Internal Linking
Créer un maillage entre pages :
- statistiques → "Générer une grille basée sur ces stats" → generateur
- generateur → "Voir les statistiques détaillées" → statistiques
- simulateur → "Générer une grille optimisée" → generateur

---

## 6. MÉTRIQUES DE SUIVI

### KPIs SEO

| Métrique | Cible 3 mois | Cible 6 mois |
|----------|--------------|--------------|
| Pages indexées | 8+ | 15+ |
| Position "générateur loto" | Top 20 | Top 10 |
| Position "statistiques loto" | Top 20 | Top 10 |
| Trafic organique | 500/mois | 2000/mois |
| CTR moyen SERP | 3% | 5% |

### Outils de suivi

1. **Google Search Console** (gratuit)
   - Impressions, clics, positions
   - Couverture d'indexation
   - Core Web Vitals

2. **Google Analytics 4** (gratuit)
   - Trafic par source
   - Comportement utilisateur
   - Conversions (grilles générées)

3. **PageSpeed Insights** (gratuit)
   - LCP, CLS, INP
   - Score mobile/desktop

---

## 7. ANALYSE CONCURRENCE

### Concurrents directs

| Site | Forces | Faiblesses |
|------|--------|------------|
| tirage-gagnant.com | Historique complet, SEO mature | UX datée, pas d'IA |
| loto.fr (FDJ) | Autorité domaine | Pas de générateur IA |
| magicmaman.com/loto | Trafic élevé | Contenu générique |

### Positionnement LotoIA

**Différenciation :**
- Seul générateur IA gratuit
- Algorithme transparent (HYBRIDE_OPTIMAL_V1)
- Score de conformité statistique
- Interface moderne

**Message SEO :**
> "Premier générateur de grilles Loto basé sur l'intelligence artificielle. Analyse de 967+ tirages officiels FDJ."

---

## 8. ACTIONS IMMÉDIATES

### Priorité 1 (Cette semaine)
1. Déployer robots.txt + sitemap.xml ✓ (fichiers créés)
2. Soumettre sitemap à Google Search Console
3. Ajouter meta descriptions sur pages principales

### Priorité 2 (Semaine prochaine)
4. Implémenter URLs SEO-friendly
5. Ajouter JSON-LD structured data
6. Créer image OG

### Priorité 3 (Mois prochain)
7. Enrichir FAQ (10 questions supplémentaires)
8. Créer première page blog
9. Monitorer positions dans GSC
