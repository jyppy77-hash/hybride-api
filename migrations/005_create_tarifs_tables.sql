-- Migration 005: Admin config (EI/SASU switch) + Sponsor tarifs (14 product codes)

-- Key-value admin config (billing mode, entity details)
CREATE TABLE IF NOT EXISTS admin_config (
    config_key VARCHAR(50) PRIMARY KEY,
    config_value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Default values: mode EI
INSERT IGNORE INTO admin_config (config_key, config_value) VALUES
('billing_mode', 'EI'),
('ei_raison_sociale', 'EmovisIA — Jean-Philippe Godard'),
('ei_siret', ''),
('sasu_raison_sociale', 'LotoIA SASU'),
('sasu_siret', '');

-- 14 product codes (tariff grid EU)
CREATE TABLE IF NOT EXISTS sponsor_tarifs (
    code VARCHAR(20) PRIMARY KEY,
    langue VARCHAR(5) NOT NULL,
    pays TEXT NOT NULL,
    tier ENUM('premium', 'standard') NOT NULL,
    tarif_mensuel DECIMAL(10,2) NOT NULL,
    engagement_min_mois INT NOT NULL DEFAULT 3,
    reduction_6m DECIMAL(5,2) DEFAULT 10.00,
    reduction_12m DECIMAL(5,2) DEFAULT 20.00,
    emplacements VARCHAR(50) NOT NULL,
    requires_sasu TINYINT(1) NOT NULL DEFAULT 0,
    active TINYINT(1) NOT NULL DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert 14 default product codes
-- Tiered pricing: Tier 1 (EN/DE) = 549/249, Tier 2 (FR/NL/ES/PT) = 449/199, Loto FR = 449/199
INSERT IGNORE INTO sponsor_tarifs (code, langue, pays, tier, tarif_mensuel, engagement_min_mois, emplacements, requires_sasu) VALUES
('LOTO_FR_A', 'fr', 'France',          'premium',  449.00, 6, 'E1-E5',      0),
('LOTO_FR_B', 'fr', 'France',          'standard', 199.00, 3, 'E1,E4,E5',   0),
('EM_FR_A',   'fr', 'FR,BE,LU,CH',     'premium',  449.00, 6, 'E1-E5',      0),
('EM_FR_B',   'fr', 'FR,BE,LU,CH',     'standard', 199.00, 3, 'E1,E4,E5',   0),
('EM_EN_A',   'en', 'UK,IE',           'premium',  549.00, 6, 'E1-E5',      1),
('EM_EN_B',   'en', 'UK,IE',           'standard', 249.00, 3, 'E1,E4,E5',   1),
('EM_ES_A',   'es', 'Espagne',         'premium',  449.00, 6, 'E1-E5',      1),
('EM_ES_B',   'es', 'Espagne',         'standard', 199.00, 3, 'E1,E4,E5',   1),
('EM_PT_A',   'pt', 'Portugal',        'premium',  449.00, 6, 'E1-E5',      1),
('EM_PT_B',   'pt', 'Portugal',        'standard', 199.00, 3, 'E1,E4,E5',   1),
('EM_DE_A',   'de', 'DE,AT,CH(DE)',    'premium',  549.00, 6, 'E1-E5',      1),
('EM_DE_B',   'de', 'DE,AT,CH(DE)',    'standard', 249.00, 3, 'E1,E4,E5',   1),
('EM_NL_A',   'nl', 'NL,BE(NL)',       'premium',  449.00, 6, 'E1-E5',      1),
('EM_NL_B',   'nl', 'NL,BE(NL)',       'standard', 199.00, 3, 'E1,E4,E5',   1);
