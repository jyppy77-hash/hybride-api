-- =============================================================================
-- Migration: add_indexes.sql
-- Description: Index critiques pour performances requêtes fréquentes
-- À EXÉCUTER MANUELLEMENT sur Cloud SQL (ne pas exécuter en CI/CD)
-- =============================================================================

-- Index sur date_de_tirage (ORDER BY, WHERE date >= ...)
CREATE INDEX IF NOT EXISTS idx_tirages_date
    ON tirages (date_de_tirage DESC);

-- Index sur les colonnes boule_1..5 (fréquences UNION ALL, filtres WHERE)
CREATE INDEX IF NOT EXISTS idx_tirages_boule_1
    ON tirages (boule_1);

CREATE INDEX IF NOT EXISTS idx_tirages_boule_2
    ON tirages (boule_2);

CREATE INDEX IF NOT EXISTS idx_tirages_boule_3
    ON tirages (boule_3);

CREATE INDEX IF NOT EXISTS idx_tirages_boule_4
    ON tirages (boule_4);

CREATE INDEX IF NOT EXISTS idx_tirages_boule_5
    ON tirages (boule_5);

-- Index sur numero_chance (stats chance, filtres)
CREATE INDEX IF NOT EXISTS idx_tirages_chance
    ON tirages (numero_chance);
