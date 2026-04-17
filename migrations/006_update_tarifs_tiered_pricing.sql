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


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🔴
-- Data loss potentielle : oui (tarifs sponsor — impact facturation immédiat)
-- PITR requis : recommandé
-- ============================================================
-- -- 🔍 NOTE HISTORIQUE : à date V122 (17/04/2026), les 13 UPDATE ci-dessous
-- -- sont des no-op car les valeurs tiered = valeurs seed 005. Si 005 a été
-- -- modifié depuis, ces UPDATE deviennent autoritatifs et restaurent les
-- -- valeurs V122.
-- --
-- -- ⚠️ CHECK CRITIQUE : détecter modifs manuelles via admin UI post-006
-- SELECT code, tarif_mensuel, updated_at FROM sponsor_tarifs
--   WHERE code IN ('LOTO_FR_A','EM_FR_A','EM_FR_B','EM_ES_A','EM_ES_B',
--                  'EM_PT_A','EM_PT_B','EM_NL_A','EM_NL_B',
--                  'EM_EN_A','EM_EN_B','EM_DE_A','EM_DE_B')
--   ORDER BY updated_at DESC;
-- -- Si updated_at d'un code > date_migration_006, un UPDATE manuel a eu lieu.
-- -- Décider : (a) accepter l'écrasement (rollback complet) ou
-- --           (b) exporter valeurs actuelles, faire DOWN, puis re-UPDATE les codes concernés.
--
-- -- ÉTAPE 1 : restaurer tarifs aux valeurs V122 (= valeurs seed 005)
-- -- Loto FR (LOTO_FR_B exclu du UP 006 — ne pas toucher ici)
-- UPDATE sponsor_tarifs SET tarif_mensuel = 449.00 WHERE code = 'LOTO_FR_A';
-- -- EM Tier 2 (FR/NL/ES/PT) — Premium 449, Standard 199
-- UPDATE sponsor_tarifs SET tarif_mensuel = 449.00 WHERE code = 'EM_FR_A';
-- UPDATE sponsor_tarifs SET tarif_mensuel = 199.00 WHERE code = 'EM_FR_B';
-- UPDATE sponsor_tarifs SET tarif_mensuel = 449.00 WHERE code = 'EM_ES_A';
-- UPDATE sponsor_tarifs SET tarif_mensuel = 199.00 WHERE code = 'EM_ES_B';
-- UPDATE sponsor_tarifs SET tarif_mensuel = 449.00 WHERE code = 'EM_PT_A';
-- UPDATE sponsor_tarifs SET tarif_mensuel = 199.00 WHERE code = 'EM_PT_B';
-- UPDATE sponsor_tarifs SET tarif_mensuel = 449.00 WHERE code = 'EM_NL_A';
-- UPDATE sponsor_tarifs SET tarif_mensuel = 199.00 WHERE code = 'EM_NL_B';
-- -- EM Tier 1 (EN/DE) — Premium 549, Standard 249
-- UPDATE sponsor_tarifs SET tarif_mensuel = 549.00 WHERE code = 'EM_EN_A';
-- UPDATE sponsor_tarifs SET tarif_mensuel = 249.00 WHERE code = 'EM_EN_B';
-- UPDATE sponsor_tarifs SET tarif_mensuel = 549.00 WHERE code = 'EM_DE_A';
-- UPDATE sponsor_tarifs SET tarif_mensuel = 249.00 WHERE code = 'EM_DE_B';
-- -- Note : /admin/tarifs + services/admin_pdf.py::generate_facture_pdf réutilisent
-- -- ces tarifs. Impact immédiat sur le calcul des factures sponsor post-rollback.
