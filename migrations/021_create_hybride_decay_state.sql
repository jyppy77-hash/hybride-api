-- V79: Decay state for HYBRIDE engine anti-lock rotation
-- Tracks consecutive misses per number to enable score decay.
-- See audit 360° Engine HYBRIDE F04 — 01/04/2026.
CREATE TABLE IF NOT EXISTS hybride_decay_state (
    game ENUM('loto', 'euromillions') NOT NULL,
    number_type ENUM('ball', 'star', 'chance') NOT NULL,
    number_value SMALLINT UNSIGNED NOT NULL,
    consecutive_misses SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    last_played DATE DEFAULT NULL,
    last_drawn DATE DEFAULT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (game, number_type, number_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟢
-- Data loss potentielle : partielle (état reconstructible depuis tirages via recalcul)
-- PITR requis : non
-- ============================================================
-- -- ÉTAPE 1 : vérifier volume (state compact : ~49+10+10 rows = 69 max pour Loto+EM)
-- SELECT COUNT(*) FROM hybride_decay_state;
--
-- -- ÉTAPE 2 : drop
-- DROP TABLE IF EXISTS hybride_decay_state;
-- -- Note : au prochain démarrage moteur, services/decay_state.py::_update_decay_from_draws()
-- -- reconstruit consecutive_misses depuis l'historique tirages. Impact : 1 requête SELECT
-- -- supplémentaire sur le 1er appel HYBRIDE post-rollback (pas de downtime).
