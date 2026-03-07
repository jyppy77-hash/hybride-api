# RAPPORT AUDIT SEO — Impact Sponsor

**Date :** 2026-03-07
**Auditeur :** Claude Opus 4.6 (auto-audit)
**Score SEO pre-audit :** 88/100 (audit 360 du 06/03)

---

## Score impact : 2/10 (impact faible, corrige dans ce commit)

## Resume

- **Points verifies : 32**
- **Problemes critiques (bloquent le SEO) : 0** (apres fix)
- **Problemes corriges dans ce commit : 3**
- **Recommandations mineures : 2**
- **Clean : 27**

---

## Detail par section

### 1. CONTENU SPONSOR VISIBLE PAR GOOGLEBOT

| Point | Statut | Detail |
|-------|--------|--------|
| E1-E5 injectent du HTML avant interaction ? | OK | Popups crees dynamiquement par JS au clic, pas dans le DOM initial |
| `[SPONSOR:ID]` nettoye ? | OK | SSE streaming seulement. JS strip le marker (`botText.replace`) avant affichage |
| Taglines sponsors dans HTML source ? | OK | Seulement dans `sponsors.json` (config), jamais dans le HTML servi |
| Placeholder "Espace reserve" dans page source ? | OK | Texte dans config JSON + popups JS, pas dans le HTML statique |
| `rel="nofollow sponsored"` sur liens sponsors ? | **CORRIGE** | 4 fichiers JS avaient `rel="noopener noreferrer"` sans `nofollow sponsored` |

**Fix applique :**
- `sponsor-popup.js:119` — `rel="noopener noreferrer nofollow sponsored"`
- `sponsor-popup-em.js:191` — idem
- `simulateur.js:882` — idem (banniere resultat E5)
- `simulateur-em.js:377` — idem

### 2. BALISES META ET STRUCTURED DATA

| Point | Statut | Detail |
|-------|--------|--------|
| Meta title/description pollues ? | OK | Aucune reference sponsor dans title, description, og:*, twitter:card |
| JSON-LD intacts ? | OK | 12 templates EM verifies : Organization, WebSite, SoftwareApplication, Dataset, FAQPage, BreadcrumbList, Article, TechArticle — aucune injection sponsor |
| AggregateRating conditionnel ? | OK | `{% if em_rating_count >= 5 %}` dans `accueil.html` |

### 3. PERFORMANCE / CORE WEB VITALS

| Point | Statut | Detail |
|-------|--------|--------|
| `tracker.js` impact LCP/FID/CLS ? | OK | `defer`, `fetch` + `sendBeacon` fallback, fire-and-forget, dedup 2s |
| `sendBeacon` bloque le rendu ? | OK | Non-bloquant, `keepalive: true` |
| Assets sponsor en lazy loading ? | N/A | Pas d'images externes. Popups JS-only (overlay modal on demand) |
| Video `preload` ? | **CORRIGE** | `preload="auto"` change en `preload="none"` (evite telechargement 2-5MB au clic) |
| CSS sponsor bloquant ? | OK | `sponsor-popup-em.css` charge via `<link>` standard (pas d'inline critique) |
| Scripts sponsor sans `defer` ? | INFO | sponsor-popup*.js charges sync dans templates. Defer risque de casser les inline scripts suivants. Impact ~100ms parse. **Recommandation : a evaluer** |

**Fix applique :**
- `sponsor-popup75.js:138` — `preload="auto"` → `preload="none"`
- `sponsor-popup75-em.js:177` — idem

### 4. ROBOTS / CRAWL BUDGET

| Point | Statut | Detail |
|-------|--------|--------|
| `/api/sponsor/track` dans robots.txt Disallow ? | OK | Couvert par `Disallow: /api/` (ligne 40) |
| `/admin/*` bloque ? | OK | Pas de routes admin dans l'arbre public. Pas de lien vers /admin dans les templates |
| Admin `noindex` ? | OK | `admin/_base.html:6` : `<meta name="robots" content="noindex, nofollow">` |
| `Sponsors_media/` accessible ? | OK | Sous `/static/`, mais pas indexe (pas de liens internes, pas dans sitemap) |
| AI scrapers bloques ? | OK | robots.txt lignes 52-88 : ClaudeBot, CCBot, AhrefsBot, SemrushBot, etc. |

### 5. SITEMAP

| Point | Statut | Detail |
|-------|--------|--------|
| Pages admin exclues ? | OK | `sitemap.py` ne genere que pages publiques (Loto FR + EM 6 langs) |
| URLs `/api/sponsor/*` exclues ? | OK | Absentes du sitemap |
| Sitemap EM intact ? | OK | 6 langues, hreflang x-default, priorites correctes, content pages incluses |

### 6. HEADERS HTTP

| Point | Statut | Detail |
|-------|--------|--------|
| `Last-Modified` sur pages publiques ? | OK | `main.py:286-292` — set a today pour toutes les pages HTML |
| `Vary: Accept-Language` sur EM ? | OK | `main.py:294-296` — conditionnel sur prefixes EM |
| `/api/sponsor/track` `Cache-Control: no-store` ? | **CORRIGE** | Etait absent, ajoute dans la reponse 204 |
| CSP pour domains sponsor ? | OK | Assets sponsor en same-origin (`/static/Sponsors_media/`), pas de domaines externes |

**Fix applique :**
- `api_sponsor_track.py:112` — `Response(status_code=204, headers={"Cache-Control": "no-store"})`

### 7. CONTENU DUPLIQUE / THIN CONTENT

| Point | Statut | Detail |
|-------|--------|--------|
| Pages avec/sans sponsor = contenu different ? | OK | Le contenu sponsor est injecte par JS (popups, chatbot), pas dans le HTML initial. Googlebot voit le meme HTML |
| Placeholder = thin content ? | OK | Pas de placeholder dans le HTML rendu. Les taglines sont en JSON config, affichees uniquement dans les modals JS |
| Message "Espace reserve" duplique ? | OK | N'apparait jamais dans le HTML statique — uniquement dans les popups JS interactives |

### 8. LIENS SORTANTS

| Point | Statut | Detail |
|-------|--------|--------|
| Nombre de liens sortants sponsor/page | OK | 0 dans le HTML initial. 2 max dans les popups JS (si declenches) |
| `rel="sponsored nofollow"` ? | **CORRIGE** | Ajoute sur les 4 fichiers JS concernes |
| Ratio liens internes / sponsors | OK | >>10:1. Footer EM = 15+ liens internes, 0 sponsor. Popups = 2 max (conditionnel) |

---

## Resume des corrections appliquees

| # | Fichier | Correction | Impact SEO |
|---|---------|-----------|------------|
| S1 | `sponsor-popup.js` | `rel="nofollow sponsored"` ajoute | Google ne suit plus les liens sponsor |
| S2 | `sponsor-popup-em.js` | idem | idem |
| S3 | `simulateur.js` | idem (banniere E5) | idem |
| S4 | `simulateur-em.js` | idem (banniere E5 EM) | idem |
| S5 | `sponsor-popup75.js` | `preload="none"` (video) | LCP ameliore, pas de download 2-5MB |
| S6 | `sponsor-popup75-em.js` | idem | idem |
| S7 | `api_sponsor_track.py` | `Cache-Control: no-store` | Tracking non-cacheable |

## Recommandations restantes (non bloquantes)

1. **Scripts sponsor `defer`** — `sponsor-popup*.js` sont charges de maniere synchrone (~100KB total). Ajouter `defer` ameliorerait le FID de ~100ms, mais necessite de verifier que les inline scripts dependants ne cassent pas. **A evaluer manuellement.**

2. **`Sponsors_media/` dans robots.txt** — Les assets sponsor sont sous `/static/Sponsors_media/`. Bien que non indexes actuellement (pas de liens), un `Disallow: /static/Sponsors_media/` preventif dans robots.txt eviterait tout crawl accidentel.

---

## Conclusion

**Score SEO : STABLE a 88/100.** Le systeme sponsor n'impacte pas le referencement.

Le contenu sponsor est **100% client-side** (popups JS, chatbot SSE, bannires dynamiques) — Googlebot ne voit aucun contenu sponsor dans le HTML initial. Les 7 corrections appliquees sont preventives (Google Guidelines compliance) et n'etaient pas encore exploitees negativement.

**Aucun point bloquant pour le lancement du 15 mars.**
