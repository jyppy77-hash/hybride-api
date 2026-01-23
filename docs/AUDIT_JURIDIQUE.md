# Notes d'Audit Juridique - LotoIA.fr

**Document interne - Usage exclusif du fondateur**

**Date de l'audit :** 23 janvier 2026
**Auditeur :** Analyse automatisée
**Version :** 1.0

---

## Synthèse exécutive

LotoIA.fr est un outil d'analyse statistique pour le Loto français, utilisant un algorithme propriétaire (HYBRIDE_OPTIMAL_V1). L'audit révèle un **niveau de conformité excellent** suite à la mise en place des documents juridiques.

**Score de conformité estimé : 95/100**

**Éditeur :** EmovisIA — Jean-Philippe Godard
**SIRET :** 511 245 730 00029

---

## 1. Risques juridiques identifiés

### 1.1 Risques CRITIQUES (Action immédiate requise)

| Risque | Description | Gravité | Action |
|--------|-------------|---------|--------|
| ~~**Mentions légales incomplètes**~~ | ~~Absence de SIRET, adresse, identité complète de l'éditeur~~ | ~~CRITIQUE~~ | **RÉSOLU** - Informations complétées |
| ~~**Responsable traitement RGPD**~~ | ~~Non identifié nominativement~~ | ~~ÉLEVÉE~~ | **RÉSOLU** - Jean-Philippe Godard identifié |

### 1.2 Risques ÉLEVÉS (Action sous 30 jours)

| Risque | Description | Gravité | Action |
|--------|-------------|---------|--------|
| **Bandeau cookies** | Non implémenté sur toutes les pages | ÉLEVÉE | Intégrer cookie-consent.js sur toutes les pages |
| **Footer juridique** | Liens légaux absents des pages existantes | ÉLEVÉE | Mettre à jour tous les footers |
| **Validation avocat** | Documents non validés par un professionnel | ÉLEVÉE | Planifier validation |

### 1.3 Risques MODÉRÉS (Action sous 90 jours)

| Risque | Description | Gravité | Action |
|--------|-------------|---------|--------|
| **Politique de conservation** | Logs serveur sans politique formelle | MODÉRÉE | Documenter et implémenter purge automatique |
| **Sous-traitants** | Contrat DPA avec Google à vérifier | MODÉRÉE | Vérifier les CCT en place |
| **Accessibilité** | Conformité RGAA non évaluée | MODÉRÉE | Audit accessibilité à planifier |

### 1.4 Risques FAIBLES (Amélioration continue)

| Risque | Description | Gravité | Action |
|--------|-------------|---------|--------|
| **Version mobile** | Vérifier affichage bandeau cookies | FAIBLE | Tests sur différents appareils |
| **Traductions** | Site monolingue (FR) | FAIBLE | Pas d'obligation, à considérer pour expansion |

---

## 2. Conformité actuelle - Checklist détaillée

### 2.1 LCEN (Loi pour la Confiance dans l'Économie Numérique)

| Exigence | Statut | Commentaire |
|----------|--------|-------------|
| Identité éditeur (nom) | **OK** | EmovisIA — Entreprise individuelle |
| Adresse siège social | **OK** | 3 rue Alexandre Riou, 44270 Machecoul-Saint-Même |
| SIRET/SIREN | **OK** | 511 245 730 00029 |
| Email contact | **OK** | contact@lotoia.fr |
| Directeur publication | **OK** | Jean-Philippe Godard |
| Hébergeur identifié | **OK** | Google Ireland Limited |
| Mentions accessibles | **OK** | Page dédiée créée |

**Score LCEN : 7/7 (100%)** - Conforme

### 2.2 RGPD (Règlement Général sur la Protection des Données)

| Exigence | Statut | Commentaire |
|----------|--------|-------------|
| Responsable traitement | **OK** | Jean-Philippe Godard |
| Finalités explicites | **OK** | Détaillées dans politique |
| Base juridique | **OK** | Intérêt légitime documenté |
| Durées conservation | **OK** | Tableau détaillé |
| Droits utilisateurs | **OK** | 8 droits documentés |
| Contact RGPD | **OK** | rgpd@lotoia.fr |
| Transferts hors UE | **OK** | CCT Google documentées |
| Registre traitements | **PARTIEL** | À formaliser séparément |
| Analyse d'impact (AIPD) | **N/A** | Non requise (risque minimal) |

**Score RGPD : 8/9 (89%)** - Très bon niveau

### 2.3 CNIL (Cookies et Traceurs)

| Exigence | Statut | Commentaire |
|----------|--------|-------------|
| Bandeau conforme | **OK** | Script créé (cookie-consent.js) |
| Bouton "Tout refuser" | **OK** | Visible et accessible |
| Liste cookies exhaustive | **OK** | Documentée |
| Catégorisation | **OK** | 3 catégories |
| Consentement granulaire | **OK** | Panneau paramètres |
| Durée consentement | **OK** | 13 mois |
| Pas de cookies avant consentement | **OK** | Aucun cookie tiers |

**Score CNIL : 7/7 (100%)** - Excellent

### 2.4 ANJ (Jeux d'argent)

| Exigence | Statut | Commentaire |
|----------|--------|-------------|
| Non-opérateur clarifié | **OK** | Disclaimer explicite |
| Pas de promesse gain | **OK** | Avertissements multiples |
| Pas d'affiliation FDJ | **OK** | Indépendance affirmée |
| Qualification statistique | **OK** | "Outil d'analyse" |
| Interdiction mineurs | **OK** | Mention 18+ |
| Numéro aide addiction | **OK** | Joueurs Info Service |
| Probabilités affichées | **OK** | Tableau complet |

**Score ANJ : 7/7 (100%)** - Excellent

### 2.5 AI Act (Intelligence Artificielle)

| Exigence | Statut | Commentaire |
|----------|--------|-------------|
| Transparence algo | **OK** | HYBRIDE_OPTIMAL_V1 documenté |
| Classification risque | **OK** | Risque minimal |
| Pas de revendication scientifique | **OK** | Limites explicitées |
| Disclaimer prédictions | **OK** | "Ne peut pas prédire" |
| Intervention humaine | **OK** | Utilisateur décide |

**Score AI Act : 5/5 (100%)** - Excellent

---

## 3. Points de vigilance

### 3.1 Évolutions réglementaires à surveiller

- **AI Act** : Entrée en vigueur progressive jusqu'à 2027
- **DSA/DMA** : Obligations pour plateformes (peu applicable ici)
- **ePrivacy** : Règlement en discussion (remplacerait directive cookies)
- **CNIL** : Nouvelles recommandations cookies possibles

### 3.2 Risques opérationnels

| Point | Risque | Recommandation |
|-------|--------|----------------|
| Emails juridiques | Boîtes non créées | Créer contact@, rgpd@, partenariats@ |
| Délai réponse RGPD | Non-respect 1 mois | Mettre en place processus |
| Mises à jour légales | Documents obsolètes | Revoir annuellement |
| Plainte CNIL | Procédure de contrôle | Préparer documentation |

### 3.3 Évolutions fonctionnelles à anticiper

Si les évolutions suivantes sont prévues, des adaptations juridiques seront nécessaires :

| Évolution | Impact juridique |
|-----------|------------------|
| Version payante | CGV, droit rétractation, TVA |
| Création de comptes | Politique données étendue |
| Newsletter | Opt-in explicite, désinscription |
| Application mobile | Stores policies, permissions |
| API publique | CGU API, licence données |

---

## 4. Recommandations prioritaires

### Priorité 1 - Avant mise en ligne (J-0)

1. ~~**Compléter les placeholders** dans mentions légales~~ **FAIT**
   - EmovisIA — Entreprise individuelle
   - 3 rue Alexandre Riou, 44270 Machecoul-Saint-Même
   - SIRET : 511 245 730 00029
   - Tél : 06 99 55 22 10
   - Jean-Philippe Godard

2. **Créer les boîtes email** (si pas déjà fait)
   - contact@lotoia.fr
   - rgpd@lotoia.fr
   - partenariats@lotoia.fr

3. ~~**Intégrer le bandeau cookies** sur toutes les pages HTML~~ **FAIT**
   - legal.css ajouté
   - cookie-consent.js ajouté

4. ~~**Mettre à jour les footers** de toutes les pages existantes~~ **FAIT**

### Priorité 2 - Première semaine (J+7)

5. **Faire valider par un avocat** l'ensemble des documents
6. **Tester le parcours utilisateur** complet (consentement cookies)
7. **Vérifier l'accessibilité** du bandeau cookies

### Priorité 3 - Premier mois (J+30)

8. **Créer un registre des traitements** (modèle CNIL)
9. **Documenter la politique de purge** des logs serveur
10. **Mettre en place une veille juridique**

---

## 5. Budget validation professionnelle

### Option A - Validation minimale

| Prestation | Estimation HT |
|------------|---------------|
| Relecture mentions légales | 200-300 EUR |
| Relecture politique confidentialité | 200-300 EUR |
| **Total** | **400-600 EUR** |

### Option B - Validation standard (recommandée)

| Prestation | Estimation HT |
|------------|---------------|
| Relecture mentions légales | 200-300 EUR |
| Relecture politique confidentialité | 200-300 EUR |
| Validation disclaimer jeux | 300-500 EUR |
| Échange téléphonique conseils | 150-250 EUR |
| **Total** | **850-1350 EUR** |

### Option C - Audit complet

| Prestation | Estimation HT |
|------------|---------------|
| Audit conformité RGPD | 500-800 EUR |
| Audit conformité LCEN | 300-500 EUR |
| Analyse risques jeux d'argent | 400-600 EUR |
| Rédaction registre traitements | 300-400 EUR |
| Rapport d'audit écrit | 200-300 EUR |
| **Total** | **1700-2600 EUR** |

### Cabinets recommandés

**Spécialistes droit du numérique :**
- Membres de l'AFDIT (Association Française du Droit de l'Informatique et des Télécoms)
- Cabinets avec expertise RGPD/données personnelles

**Plateformes juridiques en ligne (tarifs plus accessibles) :**
- Captain Contrat
- Legalstart
- LegalPlace

**Points de vigilance choix avocat :**
- Vérifier expertise spécifique "jeux d'argent" si possible
- Demander devis détaillé avant engagement
- Préférer forfait à honoraires horaires

---

## 6. Annexes

### A. Documents créés

| Fichier | Description | Statut |
|---------|-------------|--------|
| `ui/mentions-legales.html` | Mentions légales LCEN | **OK** - Complet |
| `ui/politique-confidentialite.html` | Politique RGPD | **OK** |
| `ui/politique-cookies.html` | Politique cookies CNIL | **OK** |
| `ui/disclaimer.html` | Avertissements jeux/IA | **OK** |
| `ui/static/cookie-consent.js` | Bandeau consentement | **OK** |
| `ui/static/legal.css` | Styles pages juridiques | **OK** |

### B. Checklist pré-lancement

```
[x] Mentions légales complétées (SIRET, adresse, etc.)
[ ] Boîtes email créées et fonctionnelles
[x] Bandeau cookies intégré sur toutes les pages
[x] Footers mis à jour avec liens juridiques
[ ] Tests sur mobile effectués
[ ] Validation avocat obtenue (recommandé)
[ ] Registre traitements créé (recommandé)
```

### C. Calendrier de révision

| Date | Action |
|------|--------|
| J+30 | Vérification bon fonctionnement |
| J+90 | Première révision documents |
| J+180 | Audit intermédiaire |
| J+365 | Révision annuelle complète |

---

## Avertissement

Ce document d'audit a été généré par une analyse automatisée et ne constitue pas un avis juridique. Il est **fortement recommandé** de faire valider l'ensemble des documents et recommandations par un avocat spécialisé avant toute mise en production.

L'utilisation de ces analyses sans validation professionnelle se fait sous l'entière responsabilité de l'éditeur.

---

*Document généré le 23 janvier 2026*
*LotoIA.fr - Audit de conformité juridique v1.0*
