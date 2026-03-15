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
