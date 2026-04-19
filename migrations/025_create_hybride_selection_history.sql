-- V110: Selection history for HYBRIDE persistent saturation brake (inter-draw rotation)
-- Tracks canonical grid selections per (game, draw_date_target, number) to enable
-- per-number inter-draw score brake. Breaks the uniformity of decay multipliers
-- documented as failure F01.1-01 in audit 360° sous-audit 01.1 rev.2.
--
-- See docs/AUDIT_360_DECAY_META_PIPELINE_V123.md — axis 4 — 19/04/2026.
CREATE TABLE IF NOT EXISTS hybride_selection_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game ENUM('loto', 'euromillions') NOT NULL,
    number_value SMALLINT UNSIGNED NOT NULL,
    number_type ENUM('ball', 'star', 'chance') NOT NULL,
    draw_date_target DATE NOT NULL,
    selected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_game_draw_num (game, draw_date_target, number_value, number_type),
    INDEX idx_game_date (game, draw_date_target)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟢
-- Data loss potentielle : totale mais non critique (état reconstructible depuis
--   event_log après ~3 tirages si besoin)
-- PITR requis : non
-- ============================================================
-- -- ÉTAPE 1 : vérifier volume (compact : ~7 rows/tirage × 20 tirages gardés = ~280 rows/jeu max)
-- SELECT game, COUNT(*) AS rows FROM hybride_selection_history GROUP BY game;
--
-- -- ÉTAPE 2 : drop
-- DROP TABLE IF EXISTS hybride_selection_history;
-- -- Note : après rollback, set EngineConfig.saturation_persistent_enabled = False
-- --        et re-déployer. Comportement = V123 pur.
