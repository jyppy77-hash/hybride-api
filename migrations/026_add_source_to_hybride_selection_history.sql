-- Migration 026 : add `source` column + extend UNIQUE KEY (V136)
-- Date : 2026-04-29
-- Raison : V136 calendrier admin performance HYBRIDE vs FDJ (Release 1.6.023).
--          Ajoute une colonne `source` à `hybride_selection_history` pour
--          distinguer les selections du générateur (V110, /api/{game}/generate)
--          des top fréquences PDF META (Global / 5A / 2A) tracées par /admin/calendar-perf.
--          Étend la UNIQUE KEY pour permettre la coexistence
--          (game, draw_date_target, num, type, source). Nouvel index dédié calendrier.
--
-- Compat V110 : les ~14 lignes existantes (1 batch Loto + 1 batch EM générées
-- depuis 27/04 quand CONFIG_SATURATION_PERSISTENT_ENABLED=true) sont classées
-- 'generator' automatiquement par DEFAULT — aucun backfill nécessaire.
--
-- Côté code : `services/selection_history.py::get_persistent_brake_map`,
-- `cleanup_old_selections` et `is_first_generation_of_target_draw` filtrent
-- désormais explicitement `AND source='generator'` pour préserver le
-- comportement V110 (les rows pdf_meta_* ne contribuent pas au brake).

ALTER TABLE hybride_selection_history
    ADD COLUMN source ENUM('generator', 'pdf_meta_global', 'pdf_meta_5a', 'pdf_meta_2a')
        NOT NULL DEFAULT 'generator' AFTER number_type;

ALTER TABLE hybride_selection_history
    DROP INDEX uk_game_draw_num,
    ADD UNIQUE KEY uk_game_draw_num_source
        (game, draw_date_target, number_value, number_type, source);

CREATE INDEX idx_source_draw_date
    ON hybride_selection_history (source, draw_date_target);


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟡
-- Data loss potentielle : partielle (perte des rows pdf_meta_* ; les rows
--   'generator' restent intactes après DROP COLUMN car DEFAULT était 'generator')
-- PITR requis : non (data loss limitée et reconstructible : pdf_meta_* est
--   re-générable via consultation du PDF ; generator est reconstructible
--   via event_log et /api/{game}/generate)
-- ============================================================
-- -- ÉTAPE 1 : check volume avant rollback (combien de rows pdf_meta_* à perdre)
-- SELECT source, COUNT(*) AS rows FROM hybride_selection_history GROUP BY source;
--
-- -- ÉTAPE 2 : drop index + restore UNIQUE KEY originale (V110 état pré-V136)
-- ALTER TABLE hybride_selection_history
--     DROP INDEX idx_source_draw_date,
--     DROP INDEX uk_game_draw_num_source,
--     ADD UNIQUE KEY uk_game_draw_num
--         (game, draw_date_target, number_value, number_type);
--
-- -- ⚠️ PRÉ-REQUIS : les rows pdf_meta_* doivent être supprimées AVANT le DROP COLUMN
-- --   sinon elles deviendraient des doublons sous l'ancienne UNIQUE KEY
-- DELETE FROM hybride_selection_history WHERE source != 'generator';
--
-- -- ÉTAPE 3 : drop column source
-- ALTER TABLE hybride_selection_history DROP COLUMN source;
-- -- Note : après rollback, services/selection_history.py et
-- --        routes/api_analyse_unified.py (hook PDF META) doivent être ré-alignés
-- --        sur le schéma V110 (retirer AND source='generator' et record_pdf_meta_top).
