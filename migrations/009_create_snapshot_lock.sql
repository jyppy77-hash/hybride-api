-- Migration 009: metrics_snapshot_lock — MySQL-based lock for snapshot cooldown
-- Replaces Redis lock so snapshots work even without Redis.

CREATE TABLE IF NOT EXISTS metrics_snapshot_lock (
  id INT PRIMARY KEY,
  locked_until DATETIME NOT NULL DEFAULT '2000-01-01 00:00:00'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Seed the single lock row
INSERT IGNORE INTO metrics_snapshot_lock (id, locked_until) VALUES (1, '2000-01-01');


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟢
-- Data loss potentielle : non (1 row de lock — régénérable via INSERT IGNORE au prochain init_monitoring)
-- PITR requis : non
-- ============================================================
-- -- ÉTAPE 1 : vérifier invariant (1 row attendu)
-- SELECT * FROM metrics_snapshot_lock;
--
-- -- ÉTAPE 2 : drop
-- DROP TABLE IF EXISTS metrics_snapshot_lock;
-- -- Note : sans cette table, _maybe_snapshot() catche l'exception (logger.debug) — pas de crash
