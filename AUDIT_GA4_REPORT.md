# AUDIT GA4 — LotoIA Analytics Tracking

**Date :** 2026-03-01
**Version analytics.js :** v2.5.2
**GA4 ID :** `G-YYJ5LD1ZT3`

> **Phase 1 corrigee (2026-03-01)** : P1 analytics.js duplique supprime, P2 owner IP filtre dans GA4,
> P3 launcher.html + 404.html couverts, P4 4 events GA4 manquants ajoutes. Voir section 6.
>
> **Phase 2 corrigee (2026-03-01)** : P5 cookie consent i18n 6 langues, P7 dead code sponsor supprime.
**Umami ID :** `e6add519-5d39-42cd-b4bf-b795f4408dcc`
**Scope :** Diagnostic complet GA4 vs Umami — tracking gaps, edge cases, recommandations

---

## TABLE DES MATIERES

1. [Architecture actuelle](#1-architecture-actuelle)
2. [Problemes identifies](#2-problemes-identifies)
3. [Matrice de couverture evenements](#3-matrice-de-couverture-evenements)
4. [Couverture pages HTML](#4-couverture-pages-html)
5. [Impact AdBlock / Edge Tracking Prevention](#5-impact-adblock--edge-tracking-prevention)
6. [Plan d'action priorise](#6-plan-daction-priorise)

---

## 1. Architecture actuelle

### Dual Analytics Stack

```
Visiteur
  |
  +--> Umami (cloud.umami.is/script.js)
  |      - First-party-like (CNAME possible)
  |      - Cookieless natif
  |      - Filtre owner IP via window.__OWNER__ + umamiBeforeSend()
  |      - 13 custom events
  |
  +--> GA4 (googletagmanager.com/gtag/js)
         - Consent Mode v2 (CNIL/RGPD)
         - Baseline cookieless (denied) -> page_view anonyme
         - Enhanced (granted) -> analytics_storage apres consentement
         - 28+ custom events
         - Product Analytics Engine avec buffer (5 events / 2s flush)
         - PII sanitizer (23 patterns)
```

### Consent Mode v2 — Flux

```
Boot immediat:
  bootGtagImmediately() -> consent:default DENIED -> gtag.js inject

DOMContentLoaded:
  autoInit() -> baselineInit() -> 1 page_view cookieless (TOUS visiteurs)

Si consentement analytics:
  cookieConsentUpdated event -> enableEnhanced() -> consent:update GRANTED
                                                  -> event consent_granted
```

### Fichiers cles

| Fichier | Lignes | Role |
|---|---|---|
| `analytics.js` (racine) | 1 635 | Copie ancienne (NON utilisee par les pages) |
| `ui/static/analytics.js` | 1 713 | **Version active** incluee par les HTML |
| `ui/static/cookie-consent.js` | 418 | Gestionnaire consentement CNIL |
| `main.py:184-197` | — | CSP headers (GA4 + Umami autorises) |
| `main.py:399-465` | — | UmamiOwnerFilter middleware |

---

## 2. Problemes identifies

### P1 — CRITIQUE : Duplication analytics.js divergente

**Constat :** Deux fichiers `analytics.js` existent :
- `analytics.js` (racine) : 1 635 lignes
- `ui/static/analytics.js` : 1 713 lignes (78 lignes de plus)

Les contenus different. Le fichier racine est une version anterieure qui n'est plus synchronisee. Aucune page HTML ne reference `analytics.js` a la racine — elles pointent toutes vers `/static/analytics.js`.

**Risque :** Confusion lors de modifications futures. Un developpeur pourrait modifier le mauvais fichier.

**Recommandation :** Supprimer `analytics.js` a la racine ou le remplacer par un lien symbolique / commentaire de redirection.

---

### P2 — CRITIQUE : Owner IP non filtre dans GA4

**Constat :** Le middleware `UmamiOwnerFilterMiddleware` injecte `window.__OWNER__=true` pour l'IP du proprietaire. La fonction `umamiBeforeSend()` bloque alors les hits Umami.

**Mais GA4 ne verifie PAS ce flag.** Le code `analytics.js` n'a aucune reference a `window.__OWNER__`. Toutes les visites admin (dev, tests, debug) sont comptees dans GA4.

**Impact mesurable :** Toute session admin genere :
- 1 page_view baseline (cookieless)
- N page_view enhanced (si cookies acceptes)
- Des events custom (generate_grid, sponsor_impression, etc.)

**Recommandation :** Ajouter dans `bootGtagImmediately()` ou `baselineInit()` :
```javascript
if (window.__OWNER__) {
    state.gtagLoadFailed = true; // Bloque TOUT le pipeline GA4
    return;
}
```

---

### P3 — MAJEUR : 2 pages sans GA4 (mais avec Umami)

**Constat :** Sur 36 pages avec Umami, 2 n'incluent PAS `analytics.js` :

| Page | Umami | GA4 | Impact |
|---|---|---|---|
| `launcher.html` (racine) | OK | **ABSENT** | Point d'entree technique — traffic perdu |
| `ui/404.html` | OK | **ABSENT** | Pages 404 — pas de mesure du taux d'erreur |

**Recommandation :** Ajouter `<script src="/static/analytics.js"></script>` a ces 2 pages.

---

### P4 — MAJEUR : Edge Tracking Prevention bloque gtag.js

**Constat :** Microsoft Edge (Tracking Prevention: Balanced, defaut) bloque `googletagmanager.com` et `google-analytics.com`. C'est aussi le cas de :
- Brave Browser (bloque par defaut)
- Firefox avec Enhanced Tracking Protection (strict)
- uBlock Origin, AdBlock Plus, AdGuard

**Impact GA4 :** Le script `gtag.js` ne charge pas → `state.gtagLoadFailed = true` → zero events GA4 pour ces visiteurs. Le code gere gracieusement ce cas (pas d'erreur visible), mais le tracking est perdu silencieusement.

**Impact Umami :** `cloud.umami.is` est moins bloque car :
- Domaine moins connu des listes de filtres
- Pas dans les listes EasyPrivacy / EasyList standard
- Peut etre proxifie si necessaire

**Estimation perte GA4 :** 15-30% des visiteurs (selon audience desktop/mobile et navigateurs).

**Le code gere deja l'adblock :** `analytics.js` detecte l'echec via `script.onerror` et bascule en mode degrade. Le diagnostic GA4 montre le flag via `LotoIAAnalytics.getState().gtagLoadFailed`.

**Recommandation :** Accepter l'ecart Umami > GA4 comme normal. Documenter la difference attendue. Option avancee : proxy server-side pour gtag.js (complexite non negligeable).

---

### P5 — MODERE : Cookie consent non traduit (i18n)

**Constat :** `cookie-consent.js` affiche les labels en francais uniquement :
- "Strictement necessaires"
- "Mesure d'audience"
- "Publicite et partenaires"

Les visiteurs ES/PT/DE/NL voient une banniere de consentement en francais.

**Impact GA4 :** Taux de consentement potentiellement plus bas pour les visiteurs non-francophones (incomprehension → refus ou ignorance). Cela reduit le nombre de sessions "enhanced" GA4.

**Recommandation :** ~~Injecter les traductions via `window.LotoIA_i18n`~~ **CORRIGE Phase 2** — `cookie-consent.js` v2.0.0 avec `CONSENT_LABELS` dict 6 langues, detection auto via `window.LotoIA_lang || document.documentElement.lang`.

---

### P6 — MODERE : Event naming incoherent GA4 vs Umami

**Constat :** Les memes actions sont trackees sous des noms differents :

| Action | Umami | GA4 |
|---|---|---|
| Chatbot ouvert | `chatbot-open` | `hybride_chat_open` |
| Chatbot ferme | `chatbot-close` | `hybride_chat_close` |
| Message envoye | `chatbot-message` | `hybride_chat_message` |
| Rating soumis | `rating-submitted` | `hybride_chat_rating` |
| Sponsor clic | `sponsor-click` | `sponsor_click` |
| Popup sponsor | `sponsor-popup-shown` | `sponsor_impression` |
| PDF download | `meta75-pdf-download` | `meta_pdf_export` / `meta_pdf_export_em` |
| Grille simulee | `simulateur-grille-audited` | `simulate_grid` |
| Grille generee | `simulateur-grille-generated` | `generate_grid` + `lotoia_generate_grid` |

**Impact :** Pas fonctionnel, mais rend les comparaisons croisees GA4/Umami difficiles dans les dashboards.

**Recommandation :** Documenter la table de correspondance (ce rapport suffit). Pas de changement de noms necessaire.

---

### P7 — MINEUR : ~~Sponsor events dupliques dans GA4~~ CORRIGE Phase 2

**Constat initial :** Le code definissait 6 methodes sponsor/ad dans analytics.js, dont 4 n'etaient jamais appelees (dead code). Apres audit approfondi, chaque action utilisateur ne declenchait deja qu'**un seul** event GA4 — pas de duplication reelle.

**Correction Phase 2 :** Suppression du dead code :
- `ProductEngine.sponsorView()` (`lotoia_sponsor_view`) — supprime
- `ProductEngine.sponsorClick()` (`lotoia_sponsor_click`) — supprime
- `BusinessEvents.adImpression()` (`ad_impression`) — supprime
- `BusinessEvents.adClick()` (`ad_click`) — supprime

**Events canoniques conserves :**
- `BusinessEvents.sponsorImpression()` → `sponsor_impression` (1 par popup)
- `BusinessEvents.sponsorClick()` → `sponsor_click` (1 par clic)
- `LotoIAAnalytics.track('sponsor_video_played')` → (1 par video)
- `BusinessEvents.sponsorConversion()` → reserve pour futur

---

### P8 — MINEUR : Pas de tracking des pages legales multilang

**Constat :** Les 4 pages legales EM (CGU, Politique Confidentialite, Politique Cookies, Mentions Legales) servies via Jinja2 template `_base.html` incluent bien analytics.js. Cependant, aucun event custom ne distingue ces pages — seul le `page_view` automatique les capture.

**Impact :** Minimal. Les page_view suffisent pour les pages legales.

---

## 3. Matrice de couverture evenements

### Umami → GA4 (13 events Umami)

| # | Umami Event | GA4 Equivalent | Parite |
|---|---|---|---|
| 1 | `chatbot-open` | `hybride_chat_open` | OK |
| 2 | `chatbot-close` | `hybride_chat_close` | OK |
| 3 | `chatbot-message` | `hybride_chat_message` | OK |
| 4 | `rating-submitted` | `hybride_chat_rating` | OK |
| 5 | `rating-dismissed` | aucun | **GAP** |
| 6 | `rating-popup-shown` | aucun | **GAP** |
| 7 | `sponsor-click` | `sponsor_click` + `lotoia_sponsor_click` | OK (x2) |
| 8 | `sponsor-popup-shown` | `sponsor_impression` + `lotoia_sponsor_view` | OK (x2) |
| 9 | `sponsor-video-played` | aucun | **GAP** |
| 10 | `simulateur-grille-audited` | `simulate_grid` | OK |
| 11 | `simulateur-grille-generated` | `generate_grid` + `lotoia_generate_grid` | OK (x2) |
| 12 | `meta75-pdf-download` | `meta_pdf_export` / `meta_pdf_export_em` | OK |
| 13 | `meta75-launched` | aucun | **GAP** |

**4 events Umami sans equivalent GA4 :**
- `rating-dismissed` — Le dismiss du bandeau rating n'est pas tracke dans GA4
- `rating-popup-shown` — L'affichage du bandeau rating n'est pas tracke dans GA4
- `sponsor-video-played` — Le lancement de video sponsor n'est pas tracke dans GA4
- `meta75-launched` — Le demarrage de l'analyse META 75 n'est pas tracke dans GA4

### GA4-only events (pas d'equivalent Umami)

| GA4 Event | Type | Utilite |
|---|---|---|
| `scroll_depth` | UX | Engagement scroll (25/50/75/90/100%) |
| `page_view_lotoia` | UX | Custom page view enrichi |
| `session_start_lotoia` / `session_end_lotoia` | UX | Tracking sessions custom |
| `theme_change` | UX | Preference theme dark/light |
| `faq_open` | UX | Ouverture section FAQ |
| `search_history` | UX | Recherche historique |
| `copy_grid` | UX | Copie d'une grille |
| `refresh_engine` | UX | Rafraichissement moteur |
| `view_results` / `view_stats` | UX | Navigation pages |
| `user_error` | Error | Erreurs utilisateur |
| `api_call` | Tech | Appels API (endpoint, status, latency) |
| `hybride_chat_session` | Chat | Metriques session chatbot |
| `hybride_chat_sponsor_view` | Chat | Mention sponsor dans reponse chat |
| `hybride_chat_clear` | Chat | Clear conversation |
| `chat_error` | Error | Erreur chatbot |
| `engine_interaction` | Product | Interaction moteur generique |

**GA4 est nettement plus riche** (28+ events vs 13 Umami). Umami sert de "filet de securite" pour le trafic de base quand GA4 est bloque.

---

## 4. Couverture pages HTML

### Pages avec Umami ET GA4 (34 pages)

Toutes les pages principales Loto + EuroMillions (FR/EN) + pages templates Jinja2 (_base.html pour ES/PT/DE/NL) incluent les deux trackers.

### Pages avec Umami SANS GA4 (2 pages)

| Page | Description | Priorite |
|---|---|---|
| `launcher.html` (racine) | Lanceur technique | P3 — Faible trafic |
| `ui/404.html` | Page 404 | P2 — Mesure erreurs |

### Pages multilang EM (template Jinja2)

Les pages ES/PT/DE/NL sont servies dynamiquement via `ui/templates/em/_base.html` qui inclut **les deux trackers**. Couverture : OK pour les 6 langues.

---

## 5. Impact AdBlock / Edge Tracking Prevention

### Domaines bloques par tracker

| Liste de blocage | `googletagmanager.com` | `google-analytics.com` | `cloud.umami.is` |
|---|---|---|---|
| EasyPrivacy | BLOQUE | BLOQUE | non |
| uBlock Origin (defaut) | BLOQUE | BLOQUE | non |
| Edge Tracking Prevention (Balanced) | BLOQUE | BLOQUE | non |
| Brave Shields (defaut) | BLOQUE | BLOQUE | non |
| Firefox ETP (strict) | BLOQUE | BLOQUE | non |
| AdGuard | BLOQUE | BLOQUE | non |
| Safari ITP | cookies limites | cookies limites | non |

### Gestion adblock dans le code

Le code `analytics.js` gere correctement le blocage :

```
gtag.js bloque (onerror) → state.gtagLoadFailed = true
  → baselineInit() detecte le flag → "degraded mode"
  → Aucun event envoye → zero erreur JS
  → sendGA4Event() retourne silencieusement
  → ProductEngine.track() log un warning unique puis silence
```

**Conclusion :** La degradation gracieuse est excellente. Aucune erreur visible pour l'utilisateur. Mais le tracking est completement perdu pour ces visiteurs dans GA4 (pas dans Umami).

---

## 6. Plan d'action priorise

### Priorite 1 — CRITIQUE ~~(a faire immediatement)~~ CORRIGE

| # | Action | Fichier(s) | Statut |
|---|---|---|---|
| A1 | **Filtrer owner IP dans GA4** : `window.__OWNER__` check dans `bootGtagImmediately()` | `ui/static/analytics.js` | FAIT |
| A2 | **Supprimer analytics.js racine** (copie divergente inutilisee) | `analytics.js` | FAIT |

### Priorite 2 — MAJEUR ~~(semaine prochaine)~~ CORRIGE

| # | Action | Fichier(s) | Statut |
|---|---|---|---|
| A3 | **Ajouter analytics.js aux 2 pages manquantes** : `launcher.html` + `ui/404.html` | 2 fichiers HTML | FAIT |
| A4 | **Combler les 4 gaps events** : `rating_popup_shown`, `rating_dismissed`, `sponsor_video_played`, `meta75_launched` | `rating-popup.js`, `sponsor-popup75.js`, `sponsor-popup75-em.js` | FAIT |

### Priorite 3 — MODERE ~~(backlog)~~ CORRIGE

| # | Action | Fichier(s) | Statut |
|---|---|---|---|
| A5 | **Traduire cookie-consent.js** (6 langues) — `CONSENT_LABELS` dict + auto-detect lang | `cookie-consent.js` v2.0.0 | FAIT |
| A6 | **Nettoyer dead code sponsor** : supprime 4 methodes jamais appelees (ProductEngine + ad events) | `analytics.js` | FAIT |

### Priorite 4 — OPTIONNEL (nice-to-have)

| # | Action | Fichier(s) | Effort |
|---|---|---|---|
| A7 | **Proxy server-side gtag.js** pour contourner adblock (via Cloud Run reverse proxy) | `main.py`, `analytics.js` | 4h+ |
| A8 | **Documenter table de correspondance events** dans PROJECT_OVERVIEW.md | `docs/PROJECT_OVERVIEW.md` | 15 min |

---

## Resume executif

| Indicateur | Valeur |
|---|---|
| Pages avec GA4 | 36 / 36 (100%) — *fixe Phase 1* |
| Pages avec Umami | 36 / 36 (100%) |
| Events GA4 | 32+ types — *+4 Phase 1* |
| Events Umami | 13 types |
| Events Umami sans GA4 | 0 gaps — *fixe Phase 1* |
| Perte estimee GA4 (adblock) | 15-30% |
| Owner IP filtre GA4 | OUI — *fixe Phase 1* |
| Owner IP filtre Umami | OUI |
| Fichier analytics.js duplique | NON — *fixe Phase 1* |
| Cookie consent i18n | 6 langues — *fixe Phase 2* |
| Degradation gracieuse adblock | Excellente |
| Consent Mode v2 CNIL | Conforme |
| CSP headers | Corrects |

**Verdict global :** L'infrastructure GA4 est mature et bien architecturee (Consent Mode v2, degradation gracieuse, Product Analytics Engine). **Phases 1 + 2 corrigees** : 6/8 problemes resolus (P1-P5, P7). Restent : P6 (naming differences — cosmetic, documented) et P8 (legal pages — no action needed). Seules les actions optionnelles P4 (proxy server-side gtag) et P4-bis (documenter events dans PROJECT_OVERVIEW) restent en backlog.
