-- Migration 013 : Table contact_messages
-- Date : 2026-03-17
-- Chantier : Feedback utilisateur — Contact admin
-- IMPORTANT : Jyppy exécutera cette migration manuellement AVANT le push

CREATE TABLE IF NOT EXISTS contact_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(100) DEFAULT NULL,
    email VARCHAR(255) DEFAULT NULL,
    sujet VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    page_source VARCHAR(100) DEFAULT NULL,
    lang VARCHAR(5) DEFAULT 'fr',
    ip VARCHAR(45) DEFAULT NULL,
    session_hash VARCHAR(64) DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    lu TINYINT(1) DEFAULT 0,
    INDEX idx_created_at (created_at),
    INDEX idx_lu (lu),
    INDEX idx_sujet (sujet)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
