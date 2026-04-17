-- Phase P2: Add product_code column to event_log for sponsor/product attribution
ALTER TABLE event_log
    ADD COLUMN product_code VARCHAR(20) DEFAULT NULL
    AFTER meta_json;

CREATE INDEX idx_event_product ON event_log (product_code, created_at);


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟡
-- Data loss potentielle : oui (attribution sponsor/product_code perdue — V117 audit)
-- PITR requis : recommandé
-- ============================================================
-- -- ÉTAPE 1 : vérifier volume de rows peuplées
-- SELECT COUNT(*) FROM event_log WHERE product_code IS NOT NULL;
-- -- Si résultat != 0, exporter avant drop (voir migrations/ROLLBACK_PROCEDURE.md §Export)
-- -- Impact : perd l'attribution produit (LOTO_FR_A, EM_EN_B, etc.) pour analytics + facturation.
--
-- -- ÉTAPE 2 : drop dans l'ordre INDEX → COLUMN (obligatoire, MariaDB refuse sinon)
-- DROP INDEX idx_event_product ON event_log;
-- ALTER TABLE event_log DROP COLUMN product_code;
-- -- Note : routes/api_track.py::track_event() continue à insérer sans product_code.
-- -- VALID_PRODUCT_CODES (config) devient sans effet côté DB — validation applicative inchangée.
