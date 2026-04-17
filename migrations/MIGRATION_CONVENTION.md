# Convention des migrations SQL — LotoIA

> **Créé** : V122 (17/04/2026) — Phase 1/4 Audit Infra CI/CD F02
> **Obligation** : toute migration dans `migrations/*.sql` doit respecter ce format
> **Enforcement** : test CI `tests/test_migrations_have_down.py` vérifie la présence du bloc DOWN

---

## 1. Format obligatoire d'une migration

Chaque fichier `migrations/NNN_nom_descriptif.sql` comporte **deux blocs** :

### Bloc UP — au début du fichier

```sql
-- Migration NNN : <titre court>
-- Date : <YYYY-MM-DD>
-- Raison : <contexte métier + version LotoIA concernée>

<SQL réversible ou idempotent>
<CREATE TABLE IF NOT EXISTS ... / ALTER TABLE ... / UPDATE ... / etc.>
```

### Bloc DOWN — à la fin du fichier, commenté

```sql


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟢 / 🟡 / 🔴
-- Data loss potentielle : oui / non / partielle / partielle irréversible
-- PITR requis : non / recommandé / OBLIGATOIRE
-- ============================================================
-- -- <PRÉ-REQUIS CASCADE éventuels, marqués ⚠️>
--
-- -- ÉTAPE 1 : <check préalable — SELECT COUNT(*), SHOW INDEX, etc.>
-- <SQL commenté avec -- -- devant>
--
-- -- ÉTAPE 2 : <action de rollback>
-- <SQL commenté avec -- -- devant>
-- -- Note : <impact applicatif avec helpers précis ex: routes/admin_xxx.py::function>
```

---

## 2. Les 4 flags obligatoires de l'en-tête DOWN

Chaque bloc DOWN commence par un en-tête standardisé avec 4 flags permettant un diagnostic instantané à 3h du matin :

| Flag | Valeurs possibles | Signification |
|------|-------------------|---------------|
| **Complexité** | 🟢 Simple / 🟡 Moyenne / 🔴 Complexe | Charge cognitive du rollback |
| **Data loss potentielle** | non / oui / partielle / partielle irréversible | Niveau de perte si DOWN exécuté sans export |
| **PITR requis** | non / recommandé / OBLIGATOIRE | Recourir à un Point-In-Time Recovery Cloud SQL |
| Ligne de séparation | `-- ============================================================` | Délimite l'en-tête |

### Grille de classification

**🟢 Simple** — DROP TABLE pur, DROP INDEX pur, sans FK ni cascade
- Ex : `004_create_event_log.sql`, `009_create_snapshot_lock.sql`
- Taille DOWN typique : 10-15 lignes

**🟡 Moyenne** — ALTER TABLE DROP COLUMN, DROP VIEW avant TABLE, data loss ciblée
- Ex : `010_add_product_code_to_event_log.sql`, `019_add_legal_fields.sql`
- Taille DOWN typique : 15-25 lignes

**🔴 Complexe** — FK cascade, ENUM shrink, CHECK fix, data-altering irréversible
- Ex : `003_create_facturia_tables.sql`, `016_utc_timestamps.sql`, `022_contrats_v9.sql`
- Taille DOWN typique : 25-40 lignes

---

## 3. Règle d'or v2 (formalisée V122)

### Énoncé

> Le bloc DOWN ne doit **pas** dépasser le bloc UP en taille.

### Exceptions admises

La règle peut être dépassée dans les 3 cas suivants :

1. **UP très court (≤ 10 lignes)** : le DOWN a besoin d'en-tête 4 flags + checks + note applicative, soit ~15 lignes minimum. L'infrastructure documentaire l'emporte sur la symétrie.
   - Ex : `017_unique_facture_numero.sql` (UP=6 / DOWN=13)
   - Ex : `010_add_product_code_to_event_log.sql` (UP=6 / DOWN=15)

2. **Dépendances inter-migrations (FK, cascades, colonnes)** : les pré-requis amont doivent être explicites pour éviter un échec ERROR 1217/1451/1553 à 3h du matin.
   - Ex : `018_create_contrats_table.sql` (UP=18 / DOWN=20, +7L pour 2 pré-requis)
   - Ex : `003_create_facturia_tables.sql` (UP=75 / DOWN=32, 5 pré-requis cascade)

3. **Pré-check bloquant ENUM / CHECK** : les codes erreur MariaDB (ERROR 3819, 1265) nécessitent une politique choisie par le dev AVANT le DOWN, documentée dans le bloc.
   - Ex : `014_fix_ratings_source_constraint.sql` (UP=12 / DOWN=28, 3 politiques)
   - Ex : `022_contrats_v9.sql` (UP=12 / DOWN=37, 3 étapes + checks)

### Règle interdite

Un bloc DOWN **vide ou placebo** (juste l'en-tête sans action SQL) **est interdit**. Si une migration n'a vraiment rien à rollbacker (cas no-op historique comme 006), documenter la situation mais fournir quand même le SQL symétrique explicite.

> **Exemple 006** : les 13 UPDATE tiered sont des no-op au moment V122 (valeurs identiques seed 005). Le DOWN contient quand même les 13 UPDATE explicites avec note historique pour résilience future.

---

## 4. Convention de numérotation

- Format : `NNN_description_courte.sql`, avec `NNN` sur 3 chiffres (zero-padded)
- Ordre chronologique strict — ne pas réutiliser un numéro existant
- Trou volontaire accepté (ex : 012 sauté entre 011 et 013) — documenter la raison en commentaire du fichier suivant
- Fichiers sans numéro (ex : `add_indexes.sql`) tolérés pour migrations manuelles hors CI/CD, mais **doivent aussi** contenir un bloc DOWN

---

## 5. Test d'enforcement (CI)

Le test `tests/test_migrations_have_down.py` vérifie que **chaque** fichier `migrations/*.sql` contient la chaîne `-- DOWN`. Le CI Cloud Build échoue si une migration est ajoutée sans bloc DOWN.

Ce test protège la convention pour toutes les futures migrations (V130, V200, ...).

---

## 6. Checklist avant commit d'une nouvelle migration

- [ ] Fichier nommé `migrations/NNN_description.sql` (numéro non réutilisé)
- [ ] Bloc UP testé localement via Cloud SQL Proxy
- [ ] Bloc DOWN rédigé avec les 4 flags dans l'en-tête
- [ ] Pré-checks SQL décommentables individuellement
- [ ] Notes applicatives avec helpers précis (`routes/xxx.py::function`)
- [ ] Pré-requis cascade documentés (⚠️ PRÉ-REQUIS si applicable)
- [ ] Export Cloud SQL référencé si data loss (vers `migrations/ROLLBACK_PROCEDURE.md §Export`)
- [ ] Règle d'or v2 respectée (ou exception justifiée en `§3`)
- [ ] Test `test_migrations_have_down.py` passe localement

---

## 7. Références

- **Procédure de rollback** : `migrations/ROLLBACK_PROCEDURE.md`
- **Journal des rollbacks** : `migrations/ROLLBACK_LOG.md`
- **Audit source** : `docs/AUDIT_360_INFRA_CICD.md` §F02
- **Sprint V122** : Phase 1/4 Audit Infra CI/CD (17/04/2026)
