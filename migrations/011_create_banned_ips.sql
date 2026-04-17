-- Migration 011: IP ban table for admin activity monitor
-- Cloud Run: no filesystem persistence, all in MySQL

CREATE TABLE IF NOT EXISTS banned_ips (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ip VARCHAR(45) NOT NULL,
    session_hash VARCHAR(64) DEFAULT '',
    reason VARCHAR(255) DEFAULT '',
    source ENUM('manual', 'auto_spam', 'auto_flood') DEFAULT 'manual',
    banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL DEFAULT NULL,
    banned_by VARCHAR(50) DEFAULT 'admin',
    is_active TINYINT(1) DEFAULT 1,
    UNIQUE KEY idx_ip (ip),
    KEY idx_active_expires (is_active, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟢
-- Data loss potentielle : oui (bans actifs perdus = bots blacklistés reviendront immédiatement)
-- PITR requis : recommandé
-- ============================================================
-- -- ÉTAPE 1 : vérifier volume + bans ACTIFS (critique sécurité)
-- SELECT COUNT(*) FROM banned_ips;
-- SELECT COUNT(*) FROM banned_ips WHERE is_active=1 AND (expires_at IS NULL OR expires_at > NOW());
-- -- Si résultat bans actifs > 0, exporter avant drop (voir migrations/ROLLBACK_PROCEDURE.md §Export)
-- -- et prévoir re-ban immédiat post-rollback sinon auto_spam/auto_flood reviendra
--
-- -- ÉTAPE 2 : drop
-- DROP TABLE IF EXISTS banned_ips;
-- -- Note : middleware/ip_ban.py::_refresh_cache() catche l'exception (logger.warning)
-- -- _banned_set reste vide → IP ban désactivé jusqu'à re-création de la table
