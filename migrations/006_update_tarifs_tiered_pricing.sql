-- Migration 006: Update tarifs to tiered pricing (mars 2026)
-- Tier 1 (EN/DE): Premium 549, Standard 249
-- Tier 2 (FR/NL/ES/PT): Premium 449, Standard 199
-- Loto FR: Premium 449, Standard 199
-- CPC: 0.30 (Loto) / 0.45 (EM) — CPM: 15 uniforme
-- 10 000 impressions incluses par forfait

-- Loto FR
UPDATE sponsor_tarifs SET tarif_mensuel = 449.00 WHERE code = 'LOTO_FR_A';
-- LOTO_FR_B stays at 199.00 (unchanged)

-- EM Tier 2 (FR/NL/ES/PT) — Premium 449, Standard 199
UPDATE sponsor_tarifs SET tarif_mensuel = 449.00 WHERE code = 'EM_FR_A';
UPDATE sponsor_tarifs SET tarif_mensuel = 199.00 WHERE code = 'EM_FR_B';
UPDATE sponsor_tarifs SET tarif_mensuel = 449.00 WHERE code = 'EM_ES_A';
UPDATE sponsor_tarifs SET tarif_mensuel = 199.00 WHERE code = 'EM_ES_B';
UPDATE sponsor_tarifs SET tarif_mensuel = 449.00 WHERE code = 'EM_PT_A';
UPDATE sponsor_tarifs SET tarif_mensuel = 199.00 WHERE code = 'EM_PT_B';
UPDATE sponsor_tarifs SET tarif_mensuel = 449.00 WHERE code = 'EM_NL_A';
UPDATE sponsor_tarifs SET tarif_mensuel = 199.00 WHERE code = 'EM_NL_B';

-- EM Tier 1 (EN/DE) — Premium 549, Standard 249
UPDATE sponsor_tarifs SET tarif_mensuel = 549.00 WHERE code = 'EM_EN_A';
UPDATE sponsor_tarifs SET tarif_mensuel = 249.00 WHERE code = 'EM_EN_B';
UPDATE sponsor_tarifs SET tarif_mensuel = 549.00 WHERE code = 'EM_DE_A';
UPDATE sponsor_tarifs SET tarif_mensuel = 249.00 WHERE code = 'EM_DE_B';
