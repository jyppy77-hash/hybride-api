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
