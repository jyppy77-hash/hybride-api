"""V141 A.4 Patch V131.G — Tests adversarial 3 fixes Option B + non-régression audit 11/05.

Cible : éliminer faux positifs structurels Phase 2/3/3-bis post-V141 A.3 Item 7 +
V131.G strict, pour réactiver `STRICT_HALLUCINATION_BLOCK=true` en prod sans
dégrader le taux UX (8.8% bloquées dimanche 10/05 → cible <1%).

Couvre 3 fixes Option B chirurgicaux :
- Fix 1 : skip Check 2 `_recheck_phase0_draw_accuracy` sur Phase 2/3/3-bis si
  aucun `_DATA_TAG_RE` dans `enrichment_context` (cas ID 2762 grille USER vs
  tirage DB de comparaison).
- Fix 2 : symétrie `_DATA_TAG_RE` ↔ `_FACTUAL_TAGS` (3 → 15 tags) — élimine
  bruit log orphan sequence/stat sur phases factuelles non-V99.
- Fix 3 : skip Check 2 si `[CONTEXTE TIRAGE À VENIR]` ou
  `[CONTEXTE PAS DE TIRAGE CE JOUR]` présent (anti `PHASE0_DATE_NOT_IN_DB`
  sur dates futures).

Refs :
- `docs/Archives/AUDIT_V131G_VS_V141A3_2026-05-11.md`
- IDs incidents 10/05 : 2738 (Phase T) / 2745 (Phase 0) / 2762 (Phase 2 FP)
"""
import logging

import pytest
from unittest.mock import AsyncMock

from services.chat_pipeline_gemini import (
    _DATA_TAG_RE,
    _FACTUAL_TAGS,
    _check_sql_number_hallucination,
    _recheck_phase0_draw_accuracy,
)


# ════════════════════════════════════════════════════════════════════
# Classe 1 — Fix 1 : skip Check 2 si `_DATA_TAG_RE` absent (Phase 2/3/3-bis)
# ════════════════════════════════════════════════════════════════════


class TestV141A4PatchV131G_Fix1SkipNoDataTag:
    """V141 A.4 Patch V131.G Fix 1 — skip Check 2 sur Phase 2/3/3-bis si
    `enrichment_context` ne contient aucun tag `_DATA_TAG_RE`.

    Élimine le faux positif structurel ID 2762 (11/05 19:40) où la grille USER
    `1-18-20-28-32` était capturée par `_DRAW_SEQUENCE_RE` et comparée à un
    tirage DB de comparaison cité par Gemini → mismatch garanti.
    """

    @pytest.mark.asyncio
    async def test_fix1_phase_2_no_data_tag_skips_silently(self):
        """Phase 2 sans tag factuel → early return None, get_tirage_fn jamais appelé."""
        response = "Le tirage du 28 mars 2026 : 1-18-20-28-32 chance 9"
        get_tirage_fn = AsyncMock()
        result = await _recheck_phase0_draw_accuracy(
            response, "2", "fr", "[TEST FIX1]",
            get_tirage_fn=get_tirage_fn, game="loto",
            enrichment_context="",
        )
        assert result is None
        get_tirage_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_fix1_phase_3_no_data_tag_skips_silently(self):
        """Phase 3 sans tag factuel → early return None."""
        response = "Tirage du 15 février 2026 : 7-14-21-28-35"
        get_tirage_fn = AsyncMock()
        result = await _recheck_phase0_draw_accuracy(
            response, "3", "fr", "[TEST FIX1]",
            get_tirage_fn=get_tirage_fn, game="loto",
            enrichment_context="texte conversationnel sans tag",
        )
        assert result is None
        get_tirage_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_fix1_phase_3_bis_no_data_tag_skips_silently(self):
        """Phase 3-bis sans tag factuel → early return None."""
        response = "Tirage du 1 avril 2026 : 5-15-25-35-45"
        get_tirage_fn = AsyncMock()
        result = await _recheck_phase0_draw_accuracy(
            response, "3-bis", "fr", "[TEST FIX1]",
            get_tirage_fn=get_tirage_fn, game="loto",
            enrichment_context="",
        )
        assert result is None
        get_tirage_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_fix1_phase_2_with_data_tag_check_actif(self):
        """Non-régression : Phase 2 AVEC tag factuel → Check 2 actif (mismatch détecté)."""
        response = "Le tirage du 28 mars 2026 : 1-10-12-29-49"
        mock_tirage = {"boules": [18, 20, 35, 38, 48], "chance": 5, "date": "2026-03-28"}
        get_tirage_fn = AsyncMock(return_value=mock_tirage)
        result = await _recheck_phase0_draw_accuracy(
            response, "2", "fr", "[TEST FIX1]",
            get_tirage_fn=get_tirage_fn, game="loto",
            enrichment_context="[ANALYSE DE GRILLE] grille soumise 1-10-12-29-49",
        )
        # Check 2 actif → mismatch boules → safe_replacement renvoyé
        assert result is not None
        get_tirage_fn.assert_called_once()


# ════════════════════════════════════════════════════════════════════
# Classe 2 — Fix 2 : symétrie `_FACTUAL_TAGS` ↔ `_DATA_TAG_RE` (3 → 15)
# ════════════════════════════════════════════════════════════════════


class TestV141A4PatchV131G_Fix2SymmetryFactualTags:
    """V141 A.4 Patch V131.G Fix 2 — `_DATA_TAG_RE` étendu aux 15 tags
    `_FACTUAL_TAGS` V141 A.1. Élimine l'asymétrie historique V99 vs V141 A.1
    qui produisait du bruit log orphan sequence / orphan stat-single sur les
    7 nouvelles phases factuelles (2/3/3-bis/P/EVAL/0-bis/G).
    """

    @pytest.mark.parametrize("factual_tag", list(_FACTUAL_TAGS))
    def test_fix2_every_factual_tag_matched_by_data_tag_re(self, factual_tag):
        """Invariant symétrie : chaque tag `_FACTUAL_TAGS` est reconnu par
        `_DATA_TAG_RE` (avec sa fermeture `]` virtuelle).

        Reproduit le pattern de contexte enrichi réel : `[TAG ...] body`.
        """
        ctx = f"{factual_tag} 12 - 14 - 22 - 31 - 44]\nQuelques données factuelles."
        match = _DATA_TAG_RE.search(ctx)
        assert match is not None, (
            f"Tag {factual_tag!r} non reconnu par _DATA_TAG_RE — asymétrie résiduelle"
        )

    def test_fix2_orphan_sequence_silent_on_analyse_de_grille(self, caplog):
        """Cas ID 2762 11/05 — `[ANALYSE DE GRILLE]` désormais factuel donc
        pas de bruit log `HALLUCINATION_ORPHAN_SEQUENCE` sur Phase 2."""
        ctx = "[ANALYSE DE GRILLE] grille USER 1-18-20-28-32 chance 9"
        response = "Voici votre comparaison : 1-18-20-28-32 contre 1-12-28-31-32."
        with caplog.at_level(logging.WARNING, logger="services.chat_pipeline_gemini"):
            _check_sql_number_hallucination(ctx, response, "2", "[TEST FIX2]")
        assert "HALLUCINATION_ORPHAN_SEQUENCE" not in caplog.text

    def test_fix2_orphan_stat_silent_on_classement(self, caplog):
        """Tag `[CLASSEMENT]` désormais reconnu → pas de bruit
        `HALLUCINATION_ORPHAN_STAT_SINGLE` sur Phase 3."""
        ctx = "[CLASSEMENT] top 5 numéros sortis 2024 — le 42 (95 fois)"
        response = "Le 42 est apparu 95 fois selon le classement."
        with caplog.at_level(logging.WARNING, logger="services.chat_pipeline_gemini"):
            _check_sql_number_hallucination(ctx, response, "3", "[TEST FIX2]")
        assert "HALLUCINATION_ORPHAN_STAT_SINGLE" not in caplog.text


# ════════════════════════════════════════════════════════════════════
# Classe 3 — Fix 3 : skip Check 2 si tirage à venir / pas de tirage ce jour
# ════════════════════════════════════════════════════════════════════


class TestV141A4PatchV131G_Fix3SkipFutureDrawContext:
    """V141 A.4 Patch V131.G Fix 3 — skip Check 2 si `[CONTEXTE TIRAGE À VENIR]`
    ou `[CONTEXTE PAS DE TIRAGE CE JOUR]` présent dans `enrichment_context`
    (tags Item 5 V141 A.3). Anti faux positif `PHASE0_DATE_NOT_IN_DB` quand
    Gemini hérite d'une date future dans sa réponse.
    """

    @pytest.mark.asyncio
    async def test_fix3_contexte_tirage_a_venir_skips(self):
        """`[CONTEXTE TIRAGE À VENIR]` présent → skip Check 2 (get_tirage_fn pas appelé)."""
        response = "Pour le tirage du 19 mai 2026 : 1-10-12-29-49"
        get_tirage_fn = AsyncMock()
        result = await _recheck_phase0_draw_accuracy(
            response, "T", "fr", "[TEST FIX3]",
            get_tirage_fn=get_tirage_fn, game="loto",
            enrichment_context=(
                "[CONTEXTE TIRAGE À VENIR]\n"
                "Le tirage du Loto du 19/05/2026 n'a pas encore eu lieu."
            ),
        )
        assert result is None
        get_tirage_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_fix3_contexte_pas_de_tirage_ce_jour_skips(self):
        """`[CONTEXTE PAS DE TIRAGE CE JOUR]` présent → skip Check 2."""
        response = "Pour le 14 mai 2026 : 1-10-12-29-49"
        get_tirage_fn = AsyncMock()
        result = await _recheck_phase0_draw_accuracy(
            response, "T", "fr", "[TEST FIX3]",
            get_tirage_fn=get_tirage_fn, game="loto",
            enrichment_context=(
                "[CONTEXTE PAS DE TIRAGE CE JOUR]\n"
                "Le 14/05/2026 n'est pas un jour de tirage du Loto."
            ),
        )
        assert result is None
        get_tirage_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_fix3_no_future_tag_check_actif(self):
        """Non-régression : contexte sans tag future → Check 2 normal."""
        response = "Le tirage du 28 mars 2026 : 1-10-12-29-49"
        mock_tirage = {"boules": [18, 20, 35, 38, 48], "chance": 5, "date": "2026-03-28"}
        get_tirage_fn = AsyncMock(return_value=mock_tirage)
        result = await _recheck_phase0_draw_accuracy(
            response, "T", "fr", "[TEST FIX3]",
            get_tirage_fn=get_tirage_fn, game="loto",
            enrichment_context="[RÉSULTAT TIRAGE 2026-03-28] 18-20-35-38-48 chance 5",
        )
        # Check 2 actif → mismatch → safe replacement
        assert result is not None
        get_tirage_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_fix3_cumul_avec_fix1_phase_2_skips(self):
        """Cumul Fix 1 + Fix 3 : `[CONTEXTE TIRAGE À VENIR]` ne matche pas
        `_DATA_TAG_RE`, donc Fix 1 skip d'abord en Phase 2 (avant que Fix 3
        n'ait l'occasion). Vérifie qu'on aboutit bien à un skip propre."""
        response = "Tirage du 19 mai 2026 : 1-10-12-29-49"
        get_tirage_fn = AsyncMock()
        result = await _recheck_phase0_draw_accuracy(
            response, "2", "fr", "[TEST FIX3 cumul]",
            get_tirage_fn=get_tirage_fn, game="loto",
            enrichment_context="[CONTEXTE TIRAGE À VENIR] Le tirage du 19/05.",
        )
        assert result is None
        get_tirage_fn.assert_not_called()


# ════════════════════════════════════════════════════════════════════
# Classe 4 — Non-régression audit 11/05 (3 incidents reproductibles)
# ════════════════════════════════════════════════════════════════════


class TestV141A4PatchV131G_NonRegressionAudit11_05:
    """V141 A.4 Patch V131.G — Non-régression sur les 3 incidents identifiés
    dans l'audit `docs/Archives/AUDIT_V131G_VS_V141A3_2026-05-11.md` §2.

    Objectif : confirmer que les 2 BLOCKs légitimes restent légitimes (ID 2738
    Phase T context-leak, ID 2745 Phase 0 date inventée) tandis que le faux
    positif structurel (ID 2762 Phase 2) disparaît.
    """

    @pytest.mark.asyncio
    async def test_id_2762_phase_2_grille_user_no_longer_blocked(self):
        """ID 2762 11/05 19:40 — Phase 2 grille USER `1-18-20-28-32` chance 9
        + tirage DB comparaison `1-12-28-31-32` cité. AVANT V141 A.4 : faux
        positif PHASE0_DRAW_MISMATCH (parser capturait grille USER vs DB).
        APRÈS : skip propre via Fix 1 ou Fix 3 (selon contexte injecté)."""
        response = (
            "Votre grille 1-18-20-28-32 partage 3 numéros avec le tirage du "
            "18 juin 2022 (1-12-28-31-32)."
        )
        # Cas Phase 2 sans tag factuel (contexte minimal) → Fix 1 skip
        get_tirage_fn = AsyncMock()
        result = await _recheck_phase0_draw_accuracy(
            response, "2", "fr", "[TEST ID 2762]",
            get_tirage_fn=get_tirage_fn, game="loto",
            enrichment_context="",
        )
        assert result is None, "ID 2762 doit être skip — faux positif éliminé"
        get_tirage_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_id_2738_phase_t_block_reste_legitime(self):
        """ID 2738 10/05 12:21 — Phase T context-leak `1-15-30-40-47` avec
        `15` du contexte + 4 numéros inventés. Check 1 (V99 F08
        HALLUCINATION_INVENTED) reste actif et bloque légitimement.
        V141 A.4 Patch V131.G ne touche PAS Check 1 → comportement inchangé."""
        ctx = "[RÉSULTAT TIRAGE 2026-05-10] 15-18-22-35-42 chance 7"
        response = "Le tirage du 11 mai 2026 a donné : 1 - 15 - 30 - 40 - 47"
        safe_replacement = _check_sql_number_hallucination(
            ctx, response, "T", "[TEST ID 2738]", lang="fr", history=None,
        )
        # Check 1 doit toujours détecter les numéros inventés (1, 30, 40, 47)
        # vs contexte (15-18-22-35-42) → safe replacement renvoyé
        assert safe_replacement is not None
