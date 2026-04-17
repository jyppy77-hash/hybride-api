-- Migration 020: Add FK on fia_contrats + composite indexes on chat_log and contact_messages.
-- A11: FK fia_contrats.sponsor_id → fia_sponsors(id) ON DELETE RESTRICT
-- A16: Composite index on chat_log (module, created_at) for chatbot monitor queries
-- A17: Composite indexes on contact_messages for admin message queries

-- A11: Foreign key on fia_contrats.sponsor_id
ALTER TABLE fia_contrats
  ADD CONSTRAINT fk_contrats_sponsor
  FOREIGN KEY (sponsor_id) REFERENCES fia_sponsors(id)
  ON DELETE RESTRICT;

-- A16: Composite index for chatbot monitor (WHERE module = ? ORDER BY created_at DESC)
CREATE INDEX idx_chat_log_module_created ON chat_log (module, created_at DESC);

-- A17: Composite indexes for admin messages
CREATE INDEX idx_contact_messages_lu_created ON contact_messages (lu, created_at DESC);
CREATE INDEX idx_contact_messages_deleted_created ON contact_messages (deleted, created_at DESC);


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🔴
-- Data loss potentielle : non (FK + indexes uniquement — aucune donnée touchée)
-- PITR requis : non
-- ============================================================
-- -- ÉTAPE 1 : vérifier présence FK + indexes (diagnostic rapide, pas de data loss)
-- SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
--   WHERE TABLE_NAME = 'fia_contrats' AND CONSTRAINT_NAME = 'fk_contrats_sponsor';
-- SHOW INDEX FROM chat_log WHERE Key_name = 'idx_chat_log_module_created';
-- SHOW INDEX FROM contact_messages WHERE Key_name IN
--   ('idx_contact_messages_lu_created', 'idx_contact_messages_deleted_created');
--
-- -- ÉTAPE 2 : drop dans l'ordre FK FIRST puis INDEX (principe de sécurité MariaDB — ERROR 1553)
-- -- 2a. DROP FK — relâche la contrainte RESTRICT sur fia_contrats.sponsor_id
-- ALTER TABLE fia_contrats DROP FOREIGN KEY fk_contrats_sponsor;
-- -- 2b. DROP des 3 indexes composites
-- DROP INDEX idx_chat_log_module_created ON chat_log;
-- DROP INDEX idx_contact_messages_lu_created ON contact_messages;
-- DROP INDEX idx_contact_messages_deleted_created ON contact_messages;
-- -- Note : post-drop FK, DELETE sur fia_sponsors n'est plus bloqué → risque orphelins
-- -- fia_contrats.sponsor_id pointant vers ID inexistant. /admin/chatbot-monitor + /admin/messages
-- -- passent en full table scan (impact perf modéré, 90j retention pour chat_log).
