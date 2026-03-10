-- 007: metrics_history — stores periodic snapshots for 30-day graphs
CREATE TABLE IF NOT EXISTS metrics_history (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Cloud Run
    requests_per_second FLOAT DEFAULT 0,
    error_rate_5xx      FLOAT DEFAULT 0,
    latency_p50_ms      FLOAT DEFAULT 0,
    latency_p95_ms      FLOAT DEFAULT 0,
    latency_p99_ms      FLOAT DEFAULT 0,
    active_instances    INT   DEFAULT 0,
    cpu_utilization     FLOAT DEFAULT 0,
    memory_utilization  FLOAT DEFAULT 0,
    -- Gemini
    gemini_calls        INT   DEFAULT 0,
    gemini_errors       INT   DEFAULT 0,
    gemini_tokens_in    INT   DEFAULT 0,
    gemini_tokens_out   INT   DEFAULT 0,
    gemini_avg_ms       FLOAT DEFAULT 0,
    -- Costs
    cost_cloud_run_eur  FLOAT DEFAULT 0,
    cost_cloud_sql_eur  FLOAT DEFAULT 0,
    cost_gemini_eur     FLOAT DEFAULT 0,
    cost_total_eur      FLOAT DEFAULT 0,

    INDEX idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
