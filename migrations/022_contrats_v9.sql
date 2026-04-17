-- V9: Add mono-annonceur exclusif columns to fia_contrats
-- New fields: engagement_mois, pool_impressions, mode_depassement, plafond_mensuel
-- Add 'exclusif' to type_contrat ENUM

ALTER TABLE fia_contrats
    ADD COLUMN engagement_mois INT NOT NULL DEFAULT 3 AFTER montant_mensuel_ht,
    ADD COLUMN pool_impressions INT NOT NULL DEFAULT 10000 AFTER engagement_mois,
    ADD COLUMN mode_depassement ENUM('CPC','CPM','HYBRIDE') NOT NULL DEFAULT 'CPC' AFTER pool_impressions,
    ADD COLUMN plafond_mensuel DECIMAL(10,2) DEFAULT NULL COMMENT 'Hard cap depassement mensuel, NULL = pas de plafond' AFTER mode_depassement;

ALTER TABLE fia_contrats
    MODIFY COLUMN type_contrat ENUM('standard', 'premium', 'pack_regional', 'exclusif') NOT NULL DEFAULT 'exclusif';


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🔴
-- Data loss potentielle : oui (4 colonnes + type_contrat='exclusif' perdus)
-- PITR requis : recommandé
-- ============================================================
-- -- ⚠️ PRÉ-REQUIS CASCADE : si migration 018 est aussi rollbackée (DROP TABLE fia_contrats),
-- -- ce DOWN est implicitement fait (tout disparaît). Ce DOWN n'est nécessaire que pour
-- -- revenir au schéma pré-022 en gardant la table.
-- --
-- -- ⚠️ PRÉ-CHECK 1 : perte de données non-défaut dans les 4 nouvelles colonnes
-- SELECT COUNT(*) FROM fia_contrats
--   WHERE engagement_mois != 3 OR pool_impressions != 10000
--      OR mode_depassement != 'CPC' OR plafond_mensuel IS NOT NULL;
-- -- Si résultat > 0, exporter avant drop (voir migrations/ROLLBACK_PROCEDURE.md §Export).
-- --
-- -- ⚠️ PRÉ-CHECK 2 : MODIFY ENUM shrink échoue (ERROR 1265) si rows avec type='exclusif'
-- SELECT COUNT(*) FROM fia_contrats WHERE type_contrat='exclusif';
-- -- Si résultat > 0, exécuter ÉTAPE 1 ci-dessous pour réassigner ces rows.
--
-- -- ÉTAPE 1 : réassigner rows type_contrat='exclusif' (si pré-check 2 > 0)
-- UPDATE fia_contrats SET type_contrat='premium' WHERE type_contrat='exclusif';
-- -- Note : 'premium' est un choix par défaut — le dev peut préférer 'standard' selon contexte.
--
-- -- ÉTAPE 2 : MODIFY ENUM shrink (retire 'exclusif') + restaure DEFAULT d'origine 018
-- ALTER TABLE fia_contrats
--   MODIFY COLUMN type_contrat ENUM('standard', 'premium', 'pack_regional')
--   NOT NULL DEFAULT 'standard';
-- -- ⚠️ ATTENTION DEFAULT : 022 UP a mis DEFAULT='exclusif'. Le DOWN restaure
-- -- DEFAULT='standard' (valeur ORIGINALE de 018, pas 022).
--
-- -- ÉTAPE 3 : DROP des 4 colonnes en un seul ALTER
-- ALTER TABLE fia_contrats
--   DROP COLUMN engagement_mois,
--   DROP COLUMN pool_impressions,
--   DROP COLUMN mode_depassement,
--   DROP COLUMN plafond_mensuel;
-- -- Note : rend routes/admin_sponsors.py (V121 pool widget) partiellement KO — les champs
-- -- de contrat V9 disparaissent de l'UI admin. admin_helpers.py::get_contract_impressions_consumed
-- -- lèvera KeyError sur les colonnes absentes. Revert code applicatif requis en parallèle.
