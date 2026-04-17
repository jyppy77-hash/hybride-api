-- Migration 014 : Relâcher la contrainte CHECK sur ratings.source
-- Date : 2026-03-17
-- Raison : V41 a ajouté popup_em, V42 a ajouté chatbot_em_en,
--          mais la contrainte CHECK ne les autorisait pas → INSERT échoue → 500
-- IMPORTANT : Jyppy exécutera cette migration manuellement AVANT le push

-- Supprimer l'ancienne contrainte CHECK trop restrictive
ALTER TABLE ratings DROP CHECK chk_source_enum;

-- Recréer avec toutes les sources valides
ALTER TABLE ratings ADD CONSTRAINT chk_source_enum
    CHECK (source IN ('chatbot_loto', 'chatbot_em', 'chatbot_em_en', 'popup_accueil', 'popup_em'));


-- ============================================================
-- DOWN (rollback manuel — à décommenter et exécuter en prod si besoin)
-- Complexité : 🔴
-- Data loss potentielle : oui (rows chatbot_em_en + popup_em selon politique choisie)
-- PITR requis : recommandé
-- ============================================================
-- -- ⚠️ PRÉ-REQUIS CASCADE : si migration 001 est aussi rollbackée, la CHECK 014 disparaît
-- -- automatiquement avec DROP TABLE ratings (voir 001 DOWN). Ce DOWN n'est nécessaire
-- -- QUE si on veut revenir à la CHECK restreinte en gardant la table.
-- --
-- -- ⚠️ PRÉ-CHECK BLOQUANT : l'ADD CHECK restreinte échoue (ERROR 3819) si des rows
-- -- avec les nouvelles valeurs existent.
-- SELECT source, COUNT(*) FROM ratings
--   WHERE source IN ('chatbot_em_en', 'popup_em') GROUP BY source;
-- -- Si résultat non vide, choisir UNE des 3 politiques ci-dessous AVANT l'ÉTAPE 2.
-- --
-- -- OPTION A — DELETE (perte des votes de ces modules) :
-- -- DELETE FROM ratings WHERE source IN ('chatbot_em_en', 'popup_em');
-- --
-- -- OPTION B — UPDATE source vers valeur ancienne (préserve les votes, écrase précision) :
-- -- UPDATE ratings SET source='chatbot_em' WHERE source IN ('chatbot_em_en', 'popup_em');
-- --
-- -- OPTION C — annuler le rollback : garder la nouvelle CHECK, ne rien faire ici.
--
-- -- ÉTAPE 1 : vérifier que le pré-check est résolu (0 rows non conformes)
-- SELECT COUNT(*) FROM ratings WHERE source IN ('chatbot_em_en', 'popup_em');
-- -- Résultat attendu : 0. Sinon, revenir aux options ci-dessus.
--
-- -- ÉTAPE 2 : drop la CHECK élargie, puis re-add la CHECK restreinte d'origine
-- ALTER TABLE ratings DROP CHECK chk_source_enum;
-- ALTER TABLE ratings ADD CONSTRAINT chk_source_enum
--   CHECK (source IN ('chatbot_loto', 'chatbot_em', 'popup_accueil'));
-- -- Note : routes/api_ratings.py::submit_rating rejettera les INSERT avec source
-- -- 'chatbot_em_en' ou 'popup_em' (MariaDB ERROR 3819). Popups rating EM EN/FR
-- -- casseront silencieusement (500 côté serveur). Restaurer 014 dès que possible.
