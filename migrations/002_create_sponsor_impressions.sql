-- Migration 002: Create sponsor_impressions table
-- Tracks sponsor popup events (shown, click, video-played) for billing analytics.
-- RGPD: no raw IP stored — only SHA-256 hashes.

CREATE TABLE IF NOT EXISTS sponsor_impressions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    sponsor_id VARCHAR(50) DEFAULT NULL,
    page VARCHAR(200) NOT NULL,
    lang VARCHAR(5) DEFAULT 'fr',
    country VARCHAR(5) DEFAULT NULL,
    device VARCHAR(20) DEFAULT NULL,
    session_hash VARCHAR(64) NOT NULL,
    user_agent_hash VARCHAR(64) DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_created (created_at),
    INDEX idx_event (event_type),
    INDEX idx_page (page),
    INDEX idx_lang (lang),
    INDEX idx_sponsor (sponsor_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
