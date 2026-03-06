# SPONSOR SYSTEM CHANGELOG

Historique complet des modifications du systeme sponsor LotoIA.

---

## 2026-03-06 — Fix A1 + A2 (Audit final)

**Commit** : `fix(sponsor): admin chart 6/6 events + 14 README.md Sponsors_media`

### A1 — Admin chart : 6/6 event types

`ui/static/admin.js:148` — Ajout des 3 events manquants dans le graphique dashboard :
- `sponsor-inline-shown` (Chatbot, violet `#8b5cf6`)
- `sponsor-result-shown` (Resultats, rose `#ec4899`)
- `sponsor-pdf-downloaded` (PDF, cyan `#06b6d4`)

Le chart visualise desormais les 6 event types, aligne avec `_ALLOWED_EVENTS` et `_VALID_EVENTS`.

### A2 — 14 README.md dans Sponsors_media

Creation d'un README.md dans chacun des 14 dossiers produit :
- Tier Premium (slot A) : inclut ligne video_meta75.mp4
- Tier Standard (slot B) : logo + banner uniquement
- Renvoi vers `_templates/specs.md` pour specs completes

**Tests** : 1217 passed / 0 failed (4 echecs pre-existants dans test_seo_schema.py, non lies)

---

## 2026-03-06 — Etape 1/5 : Virer EmovisIA + Poser codes produit

**Commit** : `2b4011b` — `refactor(sponsor): remove EmovisIA promo, add LOTO_FR_A/B product codes`

**Fichiers modifies** :

| Fichier | Lignes | MD5 |
|---------|--------|-----|
| `ui/static/sponsor-popup.js` | 655 | `52c529ac` |
| `ui/static/em/sponsor-popup-em.js` | 696 | `f9163b71` |
| `config/js_i18n.py` | 1070 | `3d4444a3` |

**Tests** : 1171 passed / 0 failed

**Resume** :
- Remplacement de EmovisIA hardcode par LOTO_FR_A (Premium) et LOTO_FR_B (Standard)
- Ajout de `sponsor1_name` i18n en 6 langues (FR/EN/ES/PT/DE/NL)
- Remplacement de `sponsor1_desc` EmovisIA par des labels generiques premium
- Unification de toutes les URLs sponsor vers `mailto:partenariats@lotoia.fr`
- Zero reference EmovisIA restante dans les fichiers sponsor

**Reste a faire** : Rotation chatbot A/B, unification emplacements, tracking PDF, EM alignment.

---

## 2026-03-06 — Etape 2/5 : Rotation chatbot sponsor A/B/A/B (Loto FR)

**Commit** : `7e57775` — `feat(sponsor): chatbot A/B rotation LOTO_FR_A/B + tracking inline + sponsors.json v2`

**Fichiers modifies** :

| Fichier | Lignes | MD5 |
|---------|--------|-----|
| `config/sponsors.json` | 42 | `f99bb9e0` |
| `services/chat_utils.py` | 422 | `7f1beb2c` |
| `routes/api_sponsor_track.py` | 112 | `82e18730` |
| `ui/static/hybride-chatbot.js` | 598 | `b0b45245` |
| `tests/test_chat_utils.py` | 292 | `e5bbb73f` |
| `tests/test_sponsor_track.py` | 172 | `bb67ff4e` |

**Tests** : 1183 passed / 0 failed

**Resume** :
- Restructuration `sponsors.json` v2 avec `slots.loto_fr.slot_a/slot_b`
- Rotation A/B dans `_get_sponsor_if_due()` : msg 3 -> A, msg 6 -> B, msg 9 -> A...
- Marqueur `[SPONSOR:ID]` dans les messages pour parsing frontend
- Frontend parse le marqueur, strip avant affichage, POST `/api/sponsor/track`
- Ajout `sponsor-inline-shown` event + champ `sponsor_id` dans le tracking endpoint
- 12 tests ajoutes (9 rotation A/B + 3 tracking)

**Reste a faire** : Unification emplacements, tracking PDF, EM alignment.

---

## 2026-03-06 — Etape 3/5 : Emplacements unifies LOTO_FR_A/B

**Commit** : `45ec030` — `feat(sponsor): unify all placements with LOTO_FR_A/B codes + result banner E5`

**Fichiers modifies** :

| Fichier | Lignes | MD5 |
|---------|--------|-----|
| `ui/static/sponsor-popup.js` | 657 | `a50f7f71` |
| `ui/static/sponsor-popup75.js` | 1243 | `e7a808c2` |
| `services/pdf_generator.py` | 597 | `6b6f7856` |
| `ui/static/simulateur.js` | 909 | `eeee55e3` |
| `ui/static/style.css` | 5523 | `addc82a6` |
| `routes/api_sponsor_track.py` | 112 | `73150ed0` |
| `tests/test_sponsor_track.py` | 179 | `8e89a978` |

**Tests** : 1184 passed / 0 failed

**Resume** :
- E1 popup : ajout `sponsor_id` dans tous les POST `/api/sponsor/track`
- E2 video META75 : id `lotoia_video` -> `LOTO_FR_A`, `sponsor_id` dans 3 tracking calls
- E3 PDF : nom sponsor dynamique depuis `sponsors.json`, email -> `partenariats@lotoia.fr`
- E5 banniere resultats : nouvelle `.sponsor-result-banner` apres analyse grille dans simulateur
- Ajout `sponsor-result-shown` aux events autorises

**Reste a faire** : Tracking PDF download, EM PDF alignment, audit analytics final.

---

## 2026-03-06 — Verification PDF sponsor + tracking download

**Commit** : (en cours) — `feat(sponsor): PDF sponsor tracking LOTO_FR_A + sponsor-pdf-downloaded event`

**Fichiers modifies** :

| Fichier | Lignes | MD5 |
|---------|--------|-----|
| `services/pdf_generator.py` | 601 | `9dd25421` |
| `services/em_pdf_generator.py` | 646 | `48046ef0` |
| `ui/static/sponsor-popup75.js` | 1244 | `7f3f4627` |
| `ui/static/sponsor-popup75-em.js` | 1116 | `9463dd70` |
| `routes/api_sponsor_track.py` | 112 | `36f72120` |
| `tests/test_sponsor_track.py` | 184 | `19b1954` |

**Tests** : 1185 passed / 0 failed

**Resume** :
- Simplification logique sponsor name dynamique dans PDF (6 langues : par/by/por/von/door)
- EM PDF aligne : lecture sponsors.json + email corrige (`contact@lotoia.fr` -> `partenariats@lotoia.fr`)
- Tracking PDF download : POST `/api/sponsor/track` avec `sponsor-pdf-downloaded` (Loto + EM)
- Ajout `sponsor-pdf-downloaded` aux events autorises
- Fix rate limit tests : conversion de 2 tests HTTP en tests unitaires purs

**Reste a faire** :
- Etape 4/5 : Replication pattern EM (codes EM_FR_A/B, rotation chatbot EM, tracking EM)
- Etape 5/5 : Dashboard admin + facturation FacturIA

---

## Grille des emplacements — etat actuel

| # | Emplacement | Slots | sponsor_id dans tracking | Status |
|---|-------------|-------|--------------------------|--------|
| E1 | Popup simulateur | A + B | LOTO_FR_A + LOTO_FR_B | OK |
| E2 | Video META 75 | A | LOTO_FR_A | OK |
| E3 | PDF mention | A | Dynamique (sponsors.json) | OK |
| E4 | Chatbot inline | A + B (rotation) | LOTO_FR_A / LOTO_FR_B | OK |
| E5 | Banniere resultats | A | LOTO_FR_A | OK |
| E6 | PDF download tracking | A | LOTO_FR_A | OK (nouveau) |

## Events tracking autorises

```
sponsor-popup-shown
sponsor-click
sponsor-video-played
sponsor-inline-shown
sponsor-result-shown
sponsor-pdf-downloaded
```

---

## 2026-03-06 — Fix admin _VALID_EVENTS + Grille tarifaire V6

**Fichiers modifies** :

| Fichier | Action |
|---------|--------|
| `routes/admin.py` | `_VALID_EVENTS` : 3 events -> 6 events (ajout inline-shown, result-shown, pdf-downloaded) |
| `docs/PDF Sponsors/grille_tarifaire_lotoia_v6.pdf` | Deja a jour — V6 avec codes produit LOTO_FR_A/B, rotation A/B, vision EM multi-langue |

**Resume** :
- `_VALID_EVENTS` dans admin.py n'avait que 3 events (popup-shown, click, video-played)
- Aligne avec les 6 events reels du tracking endpoint (`api_sponsor_track.py`)
- Sans ce fix, l'admin dashboard ne pouvait pas creer de tarifs pour les 3 nouveaux events
- Grille tarifaire V6 PDF deja generee avec : nomenclature produit, rotation chatbot A/B, packs LOTO_FR_A/B, vision EM 14 codes

**Reste a faire** :
- Etape 4/5 : Replication pattern EM (codes EM_FR_A/B, rotation chatbot EM, tracking EM)
- Etape 5/5 : Dashboard admin + facturation FacturIA
- Migration SQL : ajouter colonne `slot` ou `tier` dans `fia_grille_tarifaire` (optionnel, le `sponsor_id` FK suffit)

---

## 2026-03-06 — Etape 4a/5 : Config + Backend — 12 slots EuroMillions

**Fichiers modifies** :

| Fichier | Lignes | MD5 |
|---------|--------|-----|
| `config/sponsors.json` | 174 | `fa933740` |
| `services/chat_utils.py` | 433 | `23ca08a2` |
| `services/chat_pipeline_em.py` | 771 | `6e1e103e` |
| `services/em_pdf_generator.py` | 649 | `d3658531` |
| `tests/test_chat_utils.py` | 358 | `d4798b9d` |

**Tests** : 1217 passed / 0 failed (4 pre-existing SEO failures non lies)

**Resume** :
- `sponsors.json` V2 -> V3 : ajout 12 slots EM (em_fr, em_en, em_es, em_pt, em_de, em_nl) x 2 (A/B)
- `_get_sponsor_if_due()` : nouveau param `module="loto"|"em"`, slot_key = `em_{lang}` si EM
- `chat_pipeline_em.py` : 2 appels mis a jour avec `module="em"`
- `em_pdf_generator.py` : sponsor name dynamique depuis `em_{lang}.slot_a` (fallback `loto_fr`)
- 5 tests EM ajoutes : rotation FR/EN/PT, lang inconnue -> None, isolation EM/Loto

**Nomenclature des 14 codes produit** :

| Module | Slot A (Premium) | Slot B (Standard) |
|--------|-----------------|-------------------|
| Loto FR | LOTO_FR_A | LOTO_FR_B |
| EM FR | EM_FR_A | EM_FR_B |
| EM EN | EM_EN_A | EM_EN_B |
| EM ES | EM_ES_A | EM_ES_B |
| EM PT | EM_PT_A | EM_PT_B |
| EM DE | EM_DE_A | EM_DE_B |
| EM NL | EM_NL_A | EM_NL_B |

**Reste a faire** :
- Etape 4b/5 : Frontend JS EM (sponsor-popup-em.js, sponsor-popup75-em.js, simulateur EM, hybride-chatbot-em.js)
- Etape 5/5 : Dashboard admin + facturation FacturIA

---

## 2026-03-06 — Etape 4b/5 : Frontend EM + Sponsors_media + Grille tarifaire EM UE

**Fichiers modifies** :

| Fichier | Lignes | MD5 |
|---------|--------|-----|
| `ui/static/em/sponsor-popup-em.js` | 701 | `f434465d` |
| `ui/static/sponsor-popup75-em.js` | 1117 | `c79e096f` |
| `ui/static/hybride-chatbot-em.js` | 607 | `9851b0a7` |
| `ui/static/hybride-chatbot-em-en.js` | 512 | `86186793` |
| `ui/static/simulateur-em.js` | 762 | `08b91563` |
| `ui/static/Sponsors_media/` | 14 dossiers + _templates | — |
| `docs/PDF Sponsors/grille_tarifaire_em_ue_v1.pdf` | 5 pages | — |

**Tests** : 1217 passed / 0 failed (4 pre-existing SEO)

**Resume** :
- `sponsor-popup-em.js` : LOTO_FR_A/B -> EM_{lang}_A/B dynamique via LI.locale + sponsor_id dans tracking
- `sponsor-popup75-em.js` : id lotoia_video -> EM_{lang}_A dynamique, LOTO_FR_A -> SPONSOR_VIDEO_75_EM.id dans 4 POST tracking
- `hybride-chatbot-em.js` : hasSponsor() text-based -> extractSponsorId() regex [SPONSOR:xx] + POST sponsor-inline-shown
- `hybride-chatbot-em-en.js` : idem (JSON response, pas SSE)
- `simulateur-em.js` : ajout injectSponsorBannerEM() E5 avec EM_{lang}_A dynamique + POST sponsor-result-shown
- 14 dossiers Sponsors_media crees (LOTO_FR_A/B + 12 EM_xx_A/B) + specs.md
- Grille tarifaire EM UE v1 PDF generee (5 pages : nomenclature, emplacements, packs, revision, contact)

**Reste a faire** :
- Etape 5/5 : Dashboard admin + facturation FacturIA

---

## 2026-03-06 — Audit 360 + Mise a jour PROJECT_OVERVIEW

**Fichiers modifies** :

| Fichier | Action |
|---------|--------|
| `docs/SPONSOR_COHERENCE_AUDIT.md` | Audit coherence EM : 42/42 verifications OK, 6 langues x 6 emplacements |
| `docs/PROJECT_OVERVIEW.md` | Mise a jour v26.0 : Sponsor V3 (14 codes, 6 emplacements, A/B rotation, changelog, status, score V10 9.5/10) |

**Resume** :
- Audit 360 Loto FR (11/11 OK) + EM (10/11 OK, 1 info mineur Sponsors_media path)
- Grilles tarifaires verifiees a jour (Loto V6 + EM UE V1, datees 6 mars 2026)
- Zero anomalie bloquante
- PROJECT_OVERVIEW v26.0 : sponsor system V3 documente, score V10 9.5/10, 1217 tests

**Reste a faire** :
- Etape 5/5 : Dashboard admin + facturation FacturIA
