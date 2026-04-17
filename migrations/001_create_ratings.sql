-- ============================================================================
-- Migration 001 : Table ratings + vues agrégées
-- Base : MySQL 8.x (Google Cloud SQL)
-- Usage : système de notation utilisateur LotoIA
-- ============================================================================

-- Table principale des votes
CREATE TABLE IF NOT EXISTS ratings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source VARCHAR(20) NOT NULL COMMENT 'chatbot_loto | chatbot_em | popup_accueil',
    rating TINYINT NOT NULL,
    comment TEXT DEFAULT NULL COMMENT 'Commentaire optionnel (max 500 car côté API)',
    session_id VARCHAR(64) NOT NULL COMMENT 'Anti-spam : 1 vote par session+source',
    page VARCHAR(100) DEFAULT '/' COMMENT 'Page d''origine',
    user_agent TEXT DEFAULT NULL COMMENT 'Pour analytics',
    ip_hash VARCHAR(64) DEFAULT NULL COMMENT 'SHA-256 tronqué (RGPD-friendly)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Contraintes
    CONSTRAINT chk_rating_range CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT chk_source_enum CHECK (source IN ('chatbot_loto', 'chatbot_em', 'popup_accueil')),

    -- Anti-spam : 1 seul vote par session + source
    UNIQUE KEY uq_session_source (session_id, source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Index pour les requêtes d'agrégation
CREATE INDEX idx_ratings_source ON ratings(source);
CREATE INDEX idx_ratings_created ON ratings(created_at);


-- ============================================================================
-- Vue agrégée par source (chatbot_loto, chatbot_em, popup_accueil)
-- ============================================================================
CREATE OR REPLACE VIEW ratings_aggregate AS
SELECT
    source,
    COUNT(*) AS review_count,
    ROUND(AVG(rating), 1) AS avg_rating,
    SUM(rating = 5) AS five_stars,
    SUM(rating = 4) AS four_stars,
    SUM(rating = 3) AS three_stars,
    SUM(rating = 2) AS two_stars,
    SUM(rating = 1) AS one_star,
    MAX(created_at) AS last_rating
FROM ratings
GROUP BY source;


-- ============================================================================
-- Vue globale (tous modules confondus) pour le schema JSON-LD
-- ============================================================================
CREATE OR REPLACE VIEW ratings_global AS
SELECT
    COUNT(*) AS review_count,
    ROUND(AVG(rating), 1) AS avg_rating
FROM ratings;


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟡
-- Data loss potentielle : oui (notes utilisateurs + reviews JSON-LD SEO AggregateRating)
-- PITR requis : recommandé
-- ============================================================
-- -- ⚠️ PRÉ-REQUIS CASCADE : si la migration 014 (fix CHECK constraint) a été appliquée,
-- -- elle disparaîtra aussi avec le DROP TABLE (la CHECK vit sur la table). Pas d'action séparée.
-- --
-- -- ÉTAPE 1 : vérifier volume + breakdown par source (diagnostic rapide)
-- SELECT COUNT(*) FROM ratings;
-- SELECT source, COUNT(*) FROM ratings GROUP BY source;
-- -- Si résultat != 0, exporter avant drop (voir migrations/ROLLBACK_PROCEDURE.md §Export)
--
-- -- ÉTAPE 2 : drop dans l'ordre VIEWs → TABLE (MySQL strict refuse VIEW orphelines)
-- DROP VIEW IF EXISTS ratings_aggregate;
-- DROP VIEW IF EXISTS ratings_global;
-- DROP TABLE IF EXISTS ratings;
-- -- Note : rend /api/ratings/submit + /api/ratings/global inopérants, popup rating cassée,
-- -- KPI dashboard avg_rating/review_count à 0, JSON-LD AggregateRating retiré des pages SEO.
