-- S11: Enforce UTC timestamps on tracking tables
-- CURRENT_TIMESTAMP depends on server timezone (@@global.time_zone).
-- UTC_TIMESTAMP is always UTC regardless of server config.

ALTER TABLE sponsor_impressions
    ALTER COLUMN created_at SET DEFAULT (UTC_TIMESTAMP());

ALTER TABLE event_log
    ALTER COLUMN created_at SET DEFAULT (UTC_TIMESTAMP());


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🔴
-- Data loss potentielle : partielle irréversible (timestamps historiques figés en UTC)
-- PITR requis : OBLIGATOIRE pour retour data complet
-- ============================================================
-- -- ⚠️ DOWN NON-TRIVIAL : ALTER SET DEFAULT ne modifie QUE les futurs INSERT.
-- -- Les rows déjà stockées avec UTC_TIMESTAMP() depuis l'UP restent en UTC.
-- -- Impossible de deviner la timezone d'origine serveur (@@global.time_zone)
-- -- au moment de chaque INSERT pré-UP. Seul PITR antérieur à 016 restaure la data complète.
-- --
-- -- ÉTAPE 1 : estimer volume impacté (rows insérées POST-migration 016)
-- -- Note : remplacer 'YYYY-MM-DD' par la date d'exécution en prod (Cloud SQL Operations log
-- -- ou équivalent MySQL SHOW LOGS). La date de création du fichier migration (27/03/2026
-- -- selon git log) peut différer de la date d'exécution réelle en prod.
-- SELECT COUNT(*) FROM sponsor_impressions WHERE created_at >= 'YYYY-MM-DD';
-- SELECT COUNT(*) FROM event_log WHERE created_at >= 'YYYY-MM-DD';
-- -- Ces rows resteront en UTC même après le DOWN. Décider si PITR nécessaire avant ALTER.
--
-- -- ÉTAPE 2 : restaurer DEFAULT CURRENT_TIMESTAMP (comportement pré-UP pour futurs INSERT)
-- ALTER TABLE sponsor_impressions ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
-- ALTER TABLE event_log ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
-- -- Note : CURRENT_TIMESTAMP dépend de @@global.time_zone serveur Cloud SQL (souvent UTC
-- -- par défaut). Le DOWN restaure le comportement par défaut mais n'améliore pas la
-- -- cohérence des rows historiques. admin_helpers.py::_PERIOD_SQL utilise CONVERT_TZ
-- -- côté app — fonctionnera quelle que soit la TZ des rows (compatibilité assurée).
