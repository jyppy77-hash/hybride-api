-- Migration 015: Create chat_log table for Chatbot Monitor (V44)
CREATE TABLE IF NOT EXISTS chat_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    module ENUM('loto', 'em') NOT NULL,
    lang VARCHAR(5) NOT NULL DEFAULT 'fr',
    question TEXT NOT NULL,
    response_preview VARCHAR(500),
    phase_detected VARCHAR(30),
    sql_generated TEXT,
    sql_status ENUM('OK', 'EMPTY', 'NO_SQL', 'REJECTED', 'ERROR', 'N/A') DEFAULT 'N/A',
    duration_ms INT,
    gemini_tokens_in INT DEFAULT 0,
    gemini_tokens_out INT DEFAULT 0,
    ip_hash VARCHAR(64),
    session_hash VARCHAR(64),
    grid_count INT DEFAULT 0,
    has_exclusions BOOLEAN DEFAULT FALSE,
    is_error BOOLEAN DEFAULT FALSE,
    error_detail VARCHAR(255),
    INDEX idx_chat_log_created (created_at),
    INDEX idx_chat_log_module (module),
    INDEX idx_chat_log_phase (phase_detected),
    INDEX idx_chat_log_status (sql_status),
    INDEX idx_chat_log_error (is_error)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟢
-- Data loss potentielle : oui (90j retention batched, audit chatbot + debug phase detection)
-- PITR requis : recommandé
-- ============================================================
-- -- ÉTAPE 1 : vérifier volume (90j retention via cleanup_chat_log)
-- SELECT COUNT(*) FROM chat_log;
-- -- Si résultat != 0, exporter avant drop (voir migrations/ROLLBACK_PROCEDURE.md §Export)
--
-- -- ÉTAPE 2 : drop
-- DROP TABLE IF EXISTS chat_log;
-- -- Note : rend /admin/chatbot-monitor inopérant
-- -- services/chat_logger.py::log_chat() fire-and-forget, catche l'exception (logger.warning)
-- -- → chatbot continue de fonctionner pour les users, seul le monitor admin est KO
