-- Migration 027 : add `grid_id` UUID column for multi-grids tracking (V137)
-- Date : 2026-04-29
-- Raison : V137 calendrier admin /admin/calendar-perf — affichage multi-grilles.
--          Permet de regrouper les 5+1 numéros d'une même grille (canonique
--          generator ou top fréquences PDF META) sous un identifiant UUID
--          unique pour affichage individuel modal détail tirage.
--
-- Compat V136.A : les ~200 lignes existantes (V110 grilles canoniques + V136
-- PDF meta + V136.A grilles post-27/04) auront grid_id NULL après migration.
-- Affichées en mode "agrégat legacy" dans l'UI (1 grille fusionnée par
-- jour-cible × source avec flag is_legacy=true). Aucune perte de donnée.
--
-- Compat V110 brake : `services/selection_history.py::get_persistent_brake_map`
-- est adapté pour ne lire que la 1ère grille temporelle du jour (subquery JOIN
-- MIN(selected_at) INTERVAL 1 SECOND, symétrique au pattern V136.A).
-- Sémantique V110 strictement préservée : seule la grille canonique du 1er
-- visiteur du jour-cible contribue au persistent saturation brake.
--
-- Côté code :
-- - services/selection_history.py::record_canonical_selection génère 1 UUID v4
--   par appel et le propage aux 6 INSERTs de la grille (5 boules + 1 secondaire).
-- - services/selection_history.py::record_pdf_meta_top idem (1 UUID par fenêtre
--   PDF Global / 5A / 2A consultée).
-- - routes/admin_perf_calendar.py::calendar_perf_draw_detail GROUP BY grid_id
--   pour reconstruire chaque grille individuelle.

-- ÉTAPE 1 : ajout colonne grid_id (NULL pour les rows historiques V110/V136/V136.A)
ALTER TABLE hybride_selection_history
    ADD COLUMN grid_id CHAR(36) NULL AFTER source;

-- ÉTAPE 2 : index dédié pour optimiser les GROUP BY grid_id du calendrier admin
CREATE INDEX idx_grid_id ON hybride_selection_history (grid_id);

-- ÉTAPE 3 : extension UNIQUE KEY pour intégrer grid_id
-- Avant V137 : UNIQUE KEY (game, draw_date_target, number_value, number_type, source)
-- Après V137 : UNIQUE KEY (game, draw_date_target, number_value, number_type, source, grid_id)
-- Justification : 2 grilles distinctes peuvent avoir le même numéro (ex: 12) sur
-- le même draw_date_target — il faut grid_id dans la clé pour permettre les
-- doublons inter-grilles tout en gardant l'idempotence intra-grille (même grille
-- enregistrée 2 fois = INSERT IGNORE silencieux via UUID identique).
-- Rappel : MariaDB considère NULL comme distinct dans UNIQUE KEY, donc les rows
-- legacy grid_id=NULL ne créent pas de conflit.
ALTER TABLE hybride_selection_history
    DROP INDEX uk_game_draw_num_source,
    ADD UNIQUE KEY uk_game_draw_num_source_grid
        (game, draw_date_target, number_value, number_type, source, grid_id);


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟡
-- Data loss potentielle : partielle — les rows post-V137 avec grid_id NOT NULL
--   doivent être nettoyées avant restore UNIQUE KEY étroite (sinon doublons sur
--   la clé V136 (game, draw_date_target, num, type, source)).
-- PITR requis : non (data reconstructible : record_canonical via /generate,
--   record_pdf_meta via /meta-analyse-local consultations).
-- ============================================================
-- -- ÉTAPE 1 : check volume rows post-V137 (avec grid_id) à nettoyer avant DOWN
-- SELECT source, COUNT(DISTINCT grid_id) AS distinct_grids,
--        COUNT(*) AS total_rows
-- FROM hybride_selection_history
-- WHERE grid_id IS NOT NULL
-- GROUP BY source;
--
-- -- ⚠️ PRÉ-REQUIS : si plusieurs grilles distinctes existent sur le même
-- --   (game, draw_date_target, number_value, number_type, source),
-- --   le DROP UNIQUE KEY puis ADD UNIQUE KEY étroite échouera (ERROR 1062).
-- --   Stratégie : supprimer les grilles non-canoniques (toutes sauf MIN(selected_at)
-- --   par jour-cible) avant de restaurer la UNIQUE KEY V136.
-- -- DELETE h FROM hybride_selection_history h
-- -- LEFT JOIN (
-- --     SELECT game, draw_date_target, source, grid_id,
-- --            MIN(selected_at) OVER (PARTITION BY game, draw_date_target, source) AS first_ts,
-- --            MIN(selected_at) AS row_ts
-- --     FROM hybride_selection_history
-- --     WHERE grid_id IS NOT NULL
-- --     GROUP BY game, draw_date_target, source, grid_id
-- -- ) keep ON h.game = keep.game AND h.draw_date_target = keep.draw_date_target
-- --      AND h.source = keep.source AND h.grid_id = keep.grid_id
-- --      AND keep.row_ts = keep.first_ts
-- -- WHERE h.grid_id IS NOT NULL AND keep.grid_id IS NULL;
--
-- -- ÉTAPE 2 : restore UNIQUE KEY V136 + DROP INDEX grid_id
-- ALTER TABLE hybride_selection_history
--     DROP INDEX uk_game_draw_num_source_grid,
--     DROP INDEX idx_grid_id,
--     ADD UNIQUE KEY uk_game_draw_num_source
--         (game, draw_date_target, number_value, number_type, source);
--
-- -- ÉTAPE 3 : drop column grid_id
-- ALTER TABLE hybride_selection_history DROP COLUMN grid_id;
-- -- Note : après rollback, services/selection_history.py et
-- --        routes/admin_perf_calendar.py doivent être ré-alignés sur le schéma
-- --        V136 (retirer génération UUID + multi-grilles + V110 subquery JOIN).
