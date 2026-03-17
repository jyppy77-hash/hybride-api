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
