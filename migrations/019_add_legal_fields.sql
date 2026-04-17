-- Migration 019: Add legal fields to fia_config_entreprise
-- Required for French invoice compliance (Art. L441-9, R123-237 Code de Commerce).
-- forme_juridique: EI (default), SAS, SARL, SASU, etc.
-- rcs: RCS registration (empty for EI/auto-entrepreneur)
-- capital_social: share capital (empty for EI/auto-entrepreneur)

ALTER TABLE fia_config_entreprise
  ADD COLUMN IF NOT EXISTS forme_juridique VARCHAR(20) DEFAULT 'EI',
  ADD COLUMN IF NOT EXISTS rcs VARCHAR(50) DEFAULT '',
  ADD COLUMN IF NOT EXISTS capital_social VARCHAR(20) DEFAULT '';


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟡
-- Data loss potentielle : oui (compliance légale factures — Art. L441-9 Code de Commerce)
-- PITR requis : recommandé
-- ============================================================
-- -- ÉTAPE 1 : exporter les 3 champs légaux (OBLIGATOIRE — valeurs saisies manuellement admin UI)
-- SELECT id, forme_juridique, rcs, capital_social FROM fia_config_entreprise;
-- -- Exporter avant drop (voir migrations/ROLLBACK_PROCEDURE.md §Export) — compliance légale.
--
-- -- ÉTAPE 2 : drop des 3 colonnes en un seul ALTER
-- ALTER TABLE fia_config_entreprise
--   DROP COLUMN forme_juridique,
--   DROP COLUMN rcs,
--   DROP COLUMN capital_social;
-- -- Note : services/admin_pdf.py::generate_facture_pdf() utilise forme_juridique + rcs + capital_social
-- -- (V69 audit). Post-rollback : PDFs factures affichent "EI" par défaut et omettent RCS/capital.
-- -- Non bloquant techniquement, mais non-conforme Art. L441-9 si la société était SASU.
