# Procédure de rollback — Migrations SQL LotoIA

> **Créé** : V122 (17/04/2026) — Phase 1/4 Audit Infra CI/CD F02
> **Périmètre** : migrations Cloud SQL MariaDB `lotofrance` (prod) et `lotofrance_staging`
> **Public** : dev de garde à 3h du matin, ou Jyppy en intervention planifiée

---

## Quand utiliser le DOWN vs le PITR

| Situation | Outil recommandé | Raison |
|-----------|-------------------|--------|
| Migration 🟢 Simple — DROP TABLE vide ou indexes seuls | DOWN bloc du fichier migration | Rapide, réversible, pas de coût Cloud SQL |
| Migration 🟡 Moyenne — data loss partielle acceptée | DOWN après export préalable | Export + DOWN = rollback structuré |
| Migration 🔴 Complexe — data-altering irréversible (016 UTC) | **PITR OBLIGATOIRE** | DOWN ne restaure pas la data historique |
| Migration 🔴 avec pré-check bloquant (014 CHECK, 022 ENUM) | DOWN après politique choisie | Les pré-checks ERROR 3819 / 1265 imposent une action manuelle avant DOWN |
| Corruption de données détectée (bug applicatif) | PITR | DOWN migration ne corrige pas un bug applicatif |
| Besoin de revenir à un état T-X précis | PITR | DOWN agit sur structure, pas sur data historique |
| Cascade multiple (ex : 003 impliquant 017/018/019/020/022) | **PITR recommandé** | Rollback manuel en cascade = risque erreur humaine élevé |

**Règle simple** : si la complexité en en-tête DOWN indique `PITR requis : OBLIGATOIRE`, **ne pas essayer le DOWN seul** — lancer PITR directement.

---

## Procédure standard de rollback

### Étape 1 — Identifier le périmètre

1. Déterminer **quelle migration** doit être rollbackée (souvent la plus récente via `git log migrations/`).
2. Vérifier les **cascades amont** dans le bloc DOWN du fichier : section `⚠️ PRÉ-REQUIS CASCADE`.
3. Lister les **migrations postérieures dépendantes** qui doivent être rollbackées d'abord (ex : rollback 003 implique rollback 017 → 018 → 020 → 022 dans cet ordre).

### Étape 2 — Lire le bloc DOWN de CHAQUE migration concernée

Chaque migration dans `migrations/*.sql` se termine par un bloc commenté :

```sql
-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟢 / 🟡 / 🔴
-- Data loss potentielle : oui / non / partielle
-- PITR requis : non / recommandé / OBLIGATOIRE
-- ============================================================
```

Les 4 flags en en-tête donnent le diagnostic instantané.

### Étape 3 — Exécuter les pré-checks

**Toujours** lancer les `SELECT COUNT(*)` ou `SHOW INDEX` de l'ÉTAPE 1 du bloc DOWN **avant** toute commande destructive.

Résultat non attendu → arrêter, investiguer, ne pas continuer sans validation Jyppy.

### Étape 4 — Exporter les données sensibles

Voir **§Export avant rollback** ci-dessous pour les 3 options Cloud SQL-compatibles.

Migrations marquées `Data loss potentielle : oui` ou `partielle` → export **obligatoire** avant destruction.

### Étape 5 — Décommenter et exécuter le SQL du DOWN

Dans l'ordre numérique des ÉTAPES (2a, 2b, etc.) indiqué dans le bloc DOWN.

Chaque ligne SQL est préfixée par `-- -- ` dans le fichier → décommenter **une étape à la fois** pour ne pas tout exécuter d'un coup.

### Étape 6 — Vérifier côté application

Post-rollback, vérifier les helpers applicatifs listés en `Note :` du bloc DOWN (ex : `routes/admin_sponsors.py::create_facture`, `services/chat_logger.py::log_chat`).

Si le DOWN casse un endpoint (500), prévoir un **revert code applicatif en parallèle** ou un re-déploiement vers la version compatible.

### Étape 7 — Logger le rollback

Ajouter une ligne dans `migrations/ROLLBACK_LOG.md` (date, migration, raison, résultat, auteur).

---

## §Export avant rollback — 3 options Cloud SQL-compatibles

⚠️ **`SELECT INTO OUTFILE` est BLOQUÉ sur Cloud SQL** (managed MariaDB GCP) pour raisons de sécurité. Ne pas utiliser.

### Option A (recommandée) — gcloud sql export csv vers GCS

```bash
# Export d'une table entière
gcloud sql export csv lotostat-eu gs://lotoia-backups/migrations/sponsor_impressions_YYYYMMDD.csv \
    --database=lotofrance \
    --query="SELECT * FROM sponsor_impressions"

# Export d'un sous-ensemble (colonnes spécifiques)
gcloud sql export csv lotostat-eu gs://lotoia-backups/migrations/fia_config_YYYYMMDD.csv \
    --database=lotofrance \
    --query="SELECT id, forme_juridique, rcs, capital_social FROM fia_config_entreprise"
```

**Avantages** : serverless, aucun impact Cloud Run, stockage GCS durable.
**Pré-requis** : bucket `gs://lotoia-backups/` existant + service account Cloud SQL autorisé.

### Option B — mysqldump via Cloud SQL Proxy local

```bash
# Lancer Cloud SQL Proxy (depuis machine locale, ex : Windows bash)
./cloud-sql-proxy.exe gen-lang-client-0680927607:europe-west1:lotostat-eu &

# Puis mysqldump (depuis autre terminal)
mysqldump --single-transaction --column-statistics=0 \
    -h 127.0.0.1 -P 3306 -u <DB_USER> -p \
    lotofrance sponsor_impressions > backup_sponsor_impressions_YYYYMMDD.sql
```

**Avantages** : format SQL réinjectable directement, idéal pour re-seed complet.
**Pré-requis** : `cloud-sql-proxy.exe` installé localement (présent à la racine du projet).

### Option C (petits volumes < 10K rows) — mysql -e quick dump

```bash
./cloud-sql-proxy.exe gen-lang-client-0680927607:europe-west1:lotostat-eu &

mysql -h 127.0.0.1 -u <DB_USER> -p lotofrance \
    -e "SELECT * FROM fia_config_entreprise" > backup_fia_config_YYYYMMDD.tsv
```

**Avantages** : rapide, pas de config GCS.
**Limite** : format TSV, réinjection manuelle plus fastidieuse.

---

## Contacts urgence

| Rôle | Personne | Contact |
|------|----------|---------|
| Owner + lead dev | Jyppy (Jean-Philippe Godard) | jyppy77@gmail.com |
| Hébergeur prod | Google Cloud Support | via Console GCP → Support |
| Accès Cloud SQL | Compte GCP `gen-lang-client-0680927607` | IAM console |

**En cas de panne prod étendue (> 30 min)** : prioriser PITR via `gcloud sql backups restore` plutôt que rollback manuel cascade.

---

## PITR (Point-In-Time Recovery) — procédure

```bash
# Lister les backups disponibles
gcloud sql backups list --instance=lotostat-eu

# Restaurer à un timestamp précis (format RFC3339)
gcloud sql instances clone lotostat-eu lotostat-eu-restore-YYYYMMDD \
    --point-in-time='2026-04-17T02:00:00Z'
```

**Important** : PITR crée une **nouvelle instance** — il faut ensuite :
1. Vérifier les données sur l'instance clonée
2. Bascule applicative (modifier `CLOUD_SQL_CONNECTION_NAME` dans Cloud Run env vars)
3. Éventuellement décommissionner l'ancienne instance après validation

**Rétention PITR Cloud SQL** : 7 jours par défaut (configurable jusqu'à 35 jours). Vérifier la config actuelle via Console GCP avant de compter sur PITR.

---

## Checklist finale post-rollback

- [ ] Pré-checks exécutés et résultats documentés
- [ ] Export effectué et fichier vérifié (non vide, accessible)
- [ ] SQL DOWN exécuté dans l'ordre des étapes
- [ ] Endpoints applicatifs testés (helpers en `Note :` du DOWN)
- [ ] Entrée ajoutée dans `migrations/ROLLBACK_LOG.md`
- [ ] Jyppy notifié du rollback (raison + impact)
- [ ] Plan de re-migration ou de correction bug en préparation
