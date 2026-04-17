-- S15: Enforce unique invoice numbers to prevent duplicates under concurrency.
-- The numero column already exists in fia_factures (format FIA-YYYYMM-XXXX).

ALTER TABLE fia_factures
    ADD UNIQUE INDEX idx_unique_numero (numero);


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🟡
-- Data loss potentielle : non (drop d'un index UNIQUE uniquement)
-- PITR requis : non
-- ============================================================
-- -- ÉTAPE 1 : vérifier l'absence de doublons (invariant garanti par UP, à re-confirmer)
-- SELECT numero, COUNT(*) FROM fia_factures GROUP BY numero HAVING COUNT(*) > 1;
-- -- Résultat attendu : vide. Si non vide, l'UNIQUE actuel est incohérent (bug à investiguer).
--
-- -- ÉTAPE 2 : drop de l'index UNIQUE
-- ALTER TABLE fia_factures DROP INDEX idx_unique_numero;
-- -- Note : après drop, routes/admin_sponsors.py::create_facture perd sa garantie d'unicité.
-- -- Si des INSERT concurrents arrivent post-drop, des doublons peuvent apparaître
-- -- (bug V68 re-ouvert). Re-créer l'index UP dès que possible.
