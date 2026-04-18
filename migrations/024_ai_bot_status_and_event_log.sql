-- Migration 024 : Anti-pollution — status column + event_log is_ai_bot flag (V123 Phase 2.5)
-- Date : 2026-04-18
-- Raison : V123 Phase 2.5 — Widgets admin Bot Intelligence + Extension A "Anti-pollution analytics"
--
--   1. ai_bot_access_log.status ENUM('allowed','blocked') — distingue hits Catégorie A autorisés
--      des Catégorie C bloqués (is_blocked_ai_bot match). Permet widget 4 "Bots bloqués 24h"
--      + KPI "bot_blocked_24h" dashboard principal.
--
--   2. event_log.is_ai_bot TINYINT(1) NOT NULL DEFAULT 0 — marque les rows insérées par des
--      AI bots Catégorie A. Les stats humaines (get_human_stats()) filtrent WHERE is_ai_bot=0
--      pour ne pas polluer les chiffres publics utilisés en communication sponsors.
--      Index composite (is_ai_bot, created_at DESC) pour requêtes stats filtrées rapides.
--
-- Rétro-compatibilité : DEFAULT 'allowed' + DEFAULT 0 → rows V122 Phase 2/4 restent cohérentes.

ALTER TABLE ai_bot_access_log
    ADD COLUMN status ENUM('allowed','blocked') NOT NULL DEFAULT 'allowed' AFTER canonical_name,
    ADD INDEX idx_status_ts (status, ts DESC);

ALTER TABLE event_log
    ADD COLUMN is_ai_bot TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'V123 anti-pollution: 1 si AI bot Cat A',
    ADD INDEX idx_human_created (is_ai_bot, created_at DESC);


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟡
-- Data loss potentielle : partielle (colonne status + is_ai_bot + leurs index perdus)
-- PITR requis : non (colonnes d'observabilité, perte acceptable)
-- ============================================================
-- -- ⚠️ PRÉ-CHECK 1 : volumétrie rows status='blocked' (perte si DROP)
-- SELECT COUNT(*) AS blocked_rows, MIN(ts) AS oldest, MAX(ts) AS newest
--   FROM ai_bot_access_log WHERE status='blocked';
-- -- Si > 0, exporter avant rollback (voir migrations/ROLLBACK_PROCEDURE.md §Export)
--
-- -- ⚠️ PRÉ-CHECK 2 : volumétrie event_log.is_ai_bot=1 (rows bots AI préservées pour analyse ?)
-- SELECT COUNT(*) AS bot_rows, MIN(created_at) AS oldest, MAX(created_at) AS newest
--   FROM event_log WHERE is_ai_bot=1;
-- -- Si > 0 et besoin historique, exporter avant rollback
--
-- -- ⚠️ PRÉ-CHECK 3 : index dépendants
-- SHOW INDEX FROM ai_bot_access_log WHERE Key_name='idx_status_ts';
-- SHOW INDEX FROM event_log WHERE Key_name='idx_human_created';
-- -- Doivent exister avant DROP INDEX (ERROR 1091 sinon)
--
-- -- ÉTAPE 1 : DROP INDEX ai_bot_access_log.idx_status_ts
-- ALTER TABLE ai_bot_access_log DROP INDEX idx_status_ts;
--
-- -- ÉTAPE 2 : DROP COLUMN ai_bot_access_log.status
-- ALTER TABLE ai_bot_access_log DROP COLUMN status;
-- -- Note : rend services/bot_feeds_monitor.py::get_blocked_bots_stats() KO.
-- -- L'endpoint /admin/api/ai-bots/blocked retournera {"blocked_bots": [], "total_blocked": 0}
-- -- (fail-safe try/except). flush_ai_bot_counters() doit aussi reverter pour arrêter
-- -- d'insérer le champ status. Revert code applicatif requis en parallèle.
--
-- -- ÉTAPE 3 : DROP INDEX event_log.idx_human_created
-- ALTER TABLE event_log DROP INDEX idx_human_created;
--
-- -- ÉTAPE 4 : DROP COLUMN event_log.is_ai_bot
-- ALTER TABLE event_log DROP COLUMN is_ai_bot;
-- -- Note : rend services/event_log_helpers.py::get_human_stats() dégradé (toutes rows comptées
-- -- comme humaines = pollution revient). routes/api_track.py::track_event() revertir la clause
-- -- is_ai_bot=%s pour rester compatible avec colonne absente.
