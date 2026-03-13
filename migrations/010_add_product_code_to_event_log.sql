-- Phase P2: Add product_code column to event_log for sponsor/product attribution
ALTER TABLE event_log
    ADD COLUMN product_code VARCHAR(20) DEFAULT NULL
    AFTER meta_json;

CREATE INDEX idx_event_product ON event_log (product_code, created_at);
