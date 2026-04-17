# Journal des rollbacks — Migrations SQL LotoIA

> **Créé** : V122 (17/04/2026) — Phase 1/4 Audit Infra CI/CD F02
> **Objectif** : tracer chaque rollback de migration en prod (DOWN ou PITR)
> **Procédure** : voir `migrations/ROLLBACK_PROCEDURE.md`

---

## Format d'entrée

Chaque rollback doit être documenté comme suit :

```markdown
## [YYYY-MM-DD HH:MM] Migration NNN_nom_de_fichier.sql

- **Auteur** : Jyppy / <nom>
- **Méthode** : DOWN bloc / PITR / DOWN + PITR
- **Raison** : (bug, hotfix, compliance, test)
- **Pré-checks exécutés** : (liste + résultats)
- **Export effectué** : (oui/non + chemin GCS ou fichier local)
- **Durée indispo service** : X min (ou 0 si rollback hors ligne)
- **Résultat** : succès / échec / partiel
- **Impact applicatif** : (endpoints touchés, workarounds appliqués)
- **Plan suivi** : (re-migration prévue, investigation bug, etc.)
- **Notes** : (observations, difficultés rencontrées)
```

---

## Historique

*Aucun rollback enregistré à ce jour.*

<!--
Exemple à recopier et remplir :

## [2026-05-12 14:30] Migration 022_contrats_v9.sql

- **Auteur** : Jyppy
- **Méthode** : DOWN bloc
- **Raison** : bug V9 détecté sur calcul pool_impressions — hotfix nécessaire
- **Pré-checks exécutés** :
    - SELECT COUNT(*) FROM fia_contrats WHERE engagement_mois != 3 OR ... : 7 rows non-défaut → exportées
    - SELECT COUNT(*) FROM fia_contrats WHERE type_contrat='exclusif' : 3 rows → UPDATE vers 'premium' exécuté
- **Export effectué** : oui, gs://lotoia-backups/migrations/fia_contrats_20260512.csv
- **Durée indispo service** : 0 (admin sponsors KO 5 min, pas d'impact public)
- **Résultat** : succès
- **Impact applicatif** : /admin/sponsors pool widget KO jusqu'à re-déploiement V122.fix
- **Plan suivi** : re-migration 022.fix prévue V123 avec calcul pool corrigé
- **Notes** : DEFAULT 'standard' bien restauré comme prévu par le DOWN
-->
