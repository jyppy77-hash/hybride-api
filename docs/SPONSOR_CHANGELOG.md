# SPONSOR SYSTEM CHANGELOG

Historique complet des modifications du systeme sponsor LotoIA.

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
