-- Migration 029 : chat_log.traffic_source (origine non identifiante de l'échange)
-- Date : 2026-11-23
-- Raison : Release 1.6.077 — sépare le trafic public, le trafic propriétaire (owner) et les smoke tests
--   dans chat_log, sans aucun identifiant : ip_hash / session_hash ne seront jamais remplis
--   (décision du 23/11/2026, promesse de confidentialité 1.6.072).
-- Numéro : 028 réservé au lot sécurité ip_ban (028_add_auto_suspicious_to_banned_ips.sql, non écrite).
-- VARCHAR(8) et non ENUM : une valeur hors ENUM ferait perdre la ligne en mode SQL strict.
-- Pas d'index. Pas d'UPDATE : les lignes existantes prennent le DEFAULT 'public'.
-- Le DEFAULT permet à la révision précédente (1.6.076) de continuer à écrire.
-- Exécution manuelle (Cloud SQL Studio), staging puis prod, AVANT le déploiement du code 1.6.077.

ALTER TABLE chat_log
  ADD COLUMN traffic_source VARCHAR(8) NOT NULL DEFAULT 'public';


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟢
-- Data loss potentielle : partielle (étiquette owner/test des échanges perdue ; aucun autre champ)
-- PITR requis : non
-- ============================================================
-- -- ⚠️ PRÉ-REQUIS : revenir d'abord à une révision antérieure à 1.6.077 (le code 1.6.077 écrit
-- -- et lit traffic_source : sans la colonne, ses INSERT chat_log échouent).
--
-- -- ÉTAPE 1 : vérifier la présence de la colonne
-- SHOW COLUMNS FROM chat_log LIKE 'traffic_source';
--
-- -- ÉTAPE 2 : drop
-- ALTER TABLE chat_log DROP COLUMN traffic_source;
-- -- Note : routes/admin_monitoring.py (KPI, export CSV) lit traffic_source en 1.6.077.
