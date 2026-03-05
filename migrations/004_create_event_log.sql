-- Phase RT-1: Universal event tracking table
CREATE TABLE IF NOT EXISTS event_log (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_type  VARCHAR(80)  NOT NULL,
    page        VARCHAR(200) DEFAULT '',
    module      VARCHAR(80)  DEFAULT '',
    lang        VARCHAR(5)   DEFAULT '',
    device      VARCHAR(20)  DEFAULT '',
    country     VARCHAR(5)   DEFAULT '',
    session_hash VARCHAR(64) DEFAULT '',
    meta_json   JSON,
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_event_created (event_type, created_at),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
