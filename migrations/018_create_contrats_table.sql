-- S06: Contrats table for FacturIA sponsor contracts
CREATE TABLE IF NOT EXISTS fia_contrats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sponsor_id INT NOT NULL,
    numero VARCHAR(30) NOT NULL UNIQUE,
    type_contrat ENUM('standard', 'premium', 'pack_regional') NOT NULL DEFAULT 'standard',
    product_codes TEXT DEFAULT NULL COMMENT 'JSON array of product codes covered',
    date_debut DATE NOT NULL,
    date_fin DATE NOT NULL,
    montant_mensuel_ht DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    statut ENUM('brouillon', 'envoye', 'signe', 'actif', 'expire', 'resilie') NOT NULL DEFAULT 'brouillon',
    conditions_particulieres TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT UTC_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT UTC_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_sponsor (sponsor_id),
    INDEX idx_statut (statut),
    INDEX idx_dates (date_debut, date_fin)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟢
-- Data loss potentielle : oui (contrats sponsors = données légales + comptables)
-- PITR requis : recommandé
-- ============================================================
-- -- ⚠️ PRÉ-REQUIS : si la migration 020 a été appliquée, la FK fk_contrats_sponsor
-- -- pointe vers fia_contrats. Rollback 020 AVANT 018, sinon DROP TABLE échoue :
-- -- ALTER TABLE fia_contrats DROP FOREIGN KEY fk_contrats_sponsor;
-- -- (+ rollback indexes 020 si pertinent — voir bloc DOWN 020)
-- --
-- -- ⚠️ PRÉ-REQUIS BIS : si la migration 022 a été appliquée, les colonnes
-- -- engagement_mois/pool_impressions/mode_depassement/plafond_mensuel et le
-- -- type_contrat='exclusif' disparaîtront aussi avec le DROP TABLE.
-- --
-- -- ÉTAPE 1 : vérifier volume + contrats actifs (priorité comptable)
-- SELECT COUNT(*) FROM fia_contrats;
-- SELECT COUNT(*) FROM fia_contrats WHERE statut='actif';
-- -- Si résultat contrats actifs > 0, exporter avant drop (voir migrations/ROLLBACK_PROCEDURE.md §Export)
--
-- -- ÉTAPE 2 : drop
-- DROP TABLE IF EXISTS fia_contrats;
-- -- Note : rend /admin/contrats inopérant + dashboard KPI contrats_proches_count à 0
