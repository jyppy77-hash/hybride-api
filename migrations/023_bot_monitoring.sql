-- Migration 023 : Bot monitoring tables (AI bots whitelist V122)
-- Date : 2026-04-18
-- Raison : V122 Phase 2/4 — AI Bots Whitelist + Feed Refresh Monitoring.
--          Pivot "Sovereignty over code, transparency for audits" (JyppY, 17/04/2026).
--          Ajoute 2 tables : bot_feed_refresh_log (observabilité refresh 6h) +
--          ai_bot_access_log (compteur IA bots Catégorie A, batched 60s).

CREATE TABLE IF NOT EXISTS bot_feed_refresh_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source VARCHAR(50) NOT NULL COMMENT 'googlebot|bingbot|applebot|google_special|google_user_triggered|google_user_triggered2|gptbot|tor_exit|ipsum_l3',
    status ENUM('ok','error') NOT NULL,
    cidrs_count INT NOT NULL DEFAULT 0 COMMENT 'Nombre de CIDR chargés depuis la source',
    error_msg VARCHAR(500) NULL,
    INDEX idx_source_ts (source, ts DESC),
    INDEX idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='V122 — Log refresh 6h bot IP feeds (Q8)';

CREATE TABLE IF NOT EXISTS ai_bot_access_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    canonical_name VARCHAR(50) NOT NULL COMMENT 'Googlebot|ClaudeBot|GPTBot|PerplexityBot|... (canonique normalisé)',
    hit_count INT NOT NULL DEFAULT 0 COMMENT 'Batched from in-memory counter flush 60s',
    INDEX idx_canonical_ts (canonical_name, ts DESC),
    INDEX idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='V122 — Compteur AI bots Catégorie A';


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟢
-- Data loss potentielle : oui (historique refresh + compteurs IA bots perdus)
-- PITR requis : non (tables de logs, perte acceptable)
-- ============================================================
-- -- ⚠️ PRÉ-CHECK : volumétrie à préserver avant DROP
-- SELECT COUNT(*) AS rows_feed, MIN(ts) AS oldest, MAX(ts) AS newest
--   FROM bot_feed_refresh_log;
-- SELECT COUNT(*) AS rows_ai, MIN(ts) AS oldest, MAX(ts) AS newest
--   FROM ai_bot_access_log;
-- -- Si > 0, exporter via `gcloud sql export csv` vers GCS avant DROP
-- -- (voir migrations/ROLLBACK_PROCEDURE.md §Export)
--
-- -- ÉTAPE 1 : DROP table bot_feed_refresh_log
-- DROP TABLE IF EXISTS bot_feed_refresh_log;
-- -- Note : rend services/bot_feeds_monitor.py::log_refresh_result()+get_feeds_status() KO.
-- -- L'endpoint /admin/api/bot-feeds-status retournera {"feeds": [], "summary": {}} (fail-safe try/except dans le service).
--
-- -- ÉTAPE 2 : DROP table ai_bot_access_log
-- DROP TABLE IF EXISTS ai_bot_access_log;
-- -- Note : rend services/bot_feeds_monitor.py::get_ai_bots_stats() KO + flush_ai_bot_counters() no-op.
-- -- config/ai_bots.py continue de fonctionner en mémoire (compteurs session uniquement).
-- -- L'endpoint /admin/api/ai-bots/stats retournera {"bots": [], "total_hits": 0}.
