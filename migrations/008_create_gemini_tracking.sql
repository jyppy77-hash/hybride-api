-- Migration 008: Gemini tracking table (replaces Redis/in-memory counters)
-- Shared across all Cloud Run instances via Cloud SQL.

CREATE TABLE IF NOT EXISTS gemini_tracking (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  call_type VARCHAR(50) NOT NULL DEFAULT '',
  lang VARCHAR(10) NOT NULL DEFAULT 'fr',
  tokens_in INT NOT NULL DEFAULT 0,
  tokens_out INT NOT NULL DEFAULT 0,
  duration_ms INT NOT NULL DEFAULT 0,
  is_error TINYINT NOT NULL DEFAULT 0,
  INDEX idx_ts (ts),
  INDEX idx_type_lang (call_type, lang)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟢
-- Data loss potentielle : oui (compteurs Gemini = base calcul coût + audit usage)
-- PITR requis : recommandé
-- ============================================================
-- -- ÉTAPE 1 : vérifier volume (90j retention batched cleanup)
-- SELECT COUNT(*) FROM gemini_tracking;
-- -- Si résultat != 0, exporter avant drop (voir migrations/ROLLBACK_PROCEDURE.md §Export)
--
-- -- ÉTAPE 2 : drop
-- DROP TABLE IF EXISTS gemini_tracking;
-- -- Note : services/gcp_monitoring.py::_get_gemini_counters fallback à defaults {0,0,0,0,0}
