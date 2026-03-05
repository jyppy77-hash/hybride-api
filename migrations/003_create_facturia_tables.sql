-- Migration 003: FacturIA tables
-- Sponsor billing system: enterprise config, sponsors, pricing grid, invoices.

-- Enterprise config (single row, id=1)
CREATE TABLE IF NOT EXISTS fia_config_entreprise (
    id INT PRIMARY KEY DEFAULT 1,
    raison_sociale VARCHAR(200) NOT NULL DEFAULT '',
    siret VARCHAR(20) DEFAULT '',
    adresse TEXT,
    code_postal VARCHAR(10) DEFAULT '',
    ville VARCHAR(100) DEFAULT '',
    pays VARCHAR(50) DEFAULT 'France',
    email VARCHAR(200) DEFAULT '',
    telephone VARCHAR(30) DEFAULT '',
    tva_intra VARCHAR(30) DEFAULT '',
    taux_tva DECIMAL(5,2) DEFAULT 20.00,
    iban VARCHAR(40) DEFAULT '',
    bic VARCHAR(15) DEFAULT '',
    logo_url VARCHAR(500) DEFAULT '',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default row
INSERT IGNORE INTO fia_config_entreprise (id) VALUES (1);

-- Sponsors
CREATE TABLE IF NOT EXISTS fia_sponsors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(200) NOT NULL,
    contact_nom VARCHAR(200) DEFAULT '',
    contact_email VARCHAR(200) DEFAULT '',
    contact_tel VARCHAR(30) DEFAULT '',
    adresse TEXT,
    siret VARCHAR(20) DEFAULT '',
    notes TEXT,
    actif TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_actif (actif)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pricing grid (per sponsor)
CREATE TABLE IF NOT EXISTS fia_grille_tarifaire (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sponsor_id INT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    prix_unitaire DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    description VARCHAR(200) DEFAULT '',
    FOREIGN KEY (sponsor_id) REFERENCES fia_sponsors(id) ON DELETE CASCADE,
    UNIQUE KEY uk_sponsor_event (sponsor_id, event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Invoices
CREATE TABLE IF NOT EXISTS fia_factures (
    id INT AUTO_INCREMENT PRIMARY KEY,
    numero VARCHAR(30) NOT NULL UNIQUE,
    sponsor_id INT NOT NULL,
    date_emission DATE NOT NULL,
    date_echeance DATE NOT NULL,
    periode_debut DATE NOT NULL,
    periode_fin DATE NOT NULL,
    montant_ht DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    montant_tva DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    montant_ttc DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    statut ENUM('brouillon','envoyee','payee') DEFAULT 'brouillon',
    lignes JSON,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (sponsor_id) REFERENCES fia_sponsors(id),
    INDEX idx_sponsor (sponsor_id),
    INDEX idx_statut (statut),
    INDEX idx_date (date_emission)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
