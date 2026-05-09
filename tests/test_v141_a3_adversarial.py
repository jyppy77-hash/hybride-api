"""V141 A.3 — Tests adversarial Phase T future + jour de tirage.

Couvre L5-F03 (NEW BUG #10 — CTA grille HYBRIDE Phase T future) :
- helpers `_is_draw_day` + `_is_target_in_future` (config/games.py)
- 4 dicts CTA i18n (chat_pipeline_shared.py)
- 6 langs symétrie (V99 F09 invariant)

Cas terrain #1 reproductible : "samedi 9 mai 2026" (= jour Loto, future si <21h).
"""
import logging
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

from config.games import ValidGame, _is_draw_day, _is_target_in_future
from services.chat_pipeline_gemini import (
    _check_sql_number_hallucination,
    _recheck_phase0_draw_accuracy,
)
from services.chat_pipeline_shared import (
    _DRAW_PENDING_CTA_EM,
    _DRAW_PENDING_CTA_LOTO,
    _NO_DRAW_THIS_DAY_EM,
    _NO_DRAW_THIS_DAY_LOTO,
    _PHASE_G_FALLTHROUGH_CONTEXT,
    _phase_g_get_safe_fallthrough_context,
)


# ════════════════════════════════════════════════════════════════════
# V141 A.3 — Helper `_is_draw_day`
# ════════════════════════════════════════════════════════════════════


class TestV141A3_IsDrawDay:
    """V141 A.3 — helper `_is_draw_day` (config/games.py)."""

    def test_loto_samedi_true(self):
        """Cas terrain #1 : samedi 9 mai 2026 = jour Loto (lundi/mercredi/samedi)."""
        assert _is_draw_day(ValidGame.loto, date(2026, 5, 9)) is True

    def test_loto_jeudi_false(self):
        """Jeudi 14 mai 2026 = PAS jour Loto."""
        assert _is_draw_day(ValidGame.loto, date(2026, 5, 14)) is False

    def test_em_mardi_true(self):
        """Mardi 12 mai 2026 = jour EuroMillions (mardi/vendredi)."""
        assert _is_draw_day(ValidGame.euromillions, date(2026, 5, 12)) is True

    def test_em_mercredi_false(self):
        """Mercredi 13 mai 2026 = PAS jour EuroMillions."""
        assert _is_draw_day(ValidGame.euromillions, date(2026, 5, 13)) is False


# ════════════════════════════════════════════════════════════════════
# V141 A.3 — Helper `_is_target_in_future` avec cutoff hour
# ════════════════════════════════════════════════════════════════════


class TestV141A3_IsTargetInFuture:
    """V141 A.3 — helper `_is_target_in_future` (gestion cutoff hour)."""

    def test_today_before_cutoff_loto_true(self):
        """Cas terrain #1 : samedi 9 mai 2026 18h00 → tirage Loto à venir (cutoff 21h)."""
        ref = datetime(2026, 5, 9, 18, 0)
        assert _is_target_in_future(ValidGame.loto, date(2026, 5, 9), ref) is True

    def test_today_after_cutoff_loto_false(self):
        """Samedi 9 mai 2026 22h00 → tirage Loto déjà passé (cutoff 21h)."""
        ref = datetime(2026, 5, 9, 22, 0)
        assert _is_target_in_future(ValidGame.loto, date(2026, 5, 9), ref) is False

    def test_tomorrow_true(self):
        """Date demain → toujours future quel que soit l'horaire courant."""
        ref = datetime(2026, 5, 9, 23, 30)
        assert _is_target_in_future(ValidGame.loto, date(2026, 5, 10), ref) is True

    def test_yesterday_false(self):
        """Date hier → jamais future."""
        ref = datetime(2026, 5, 9, 0, 0)
        assert _is_target_in_future(ValidGame.loto, date(2026, 5, 8), ref) is False


# ════════════════════════════════════════════════════════════════════
# V141 A.3 — Symétrie 6 langs (V99 F09 invariant) sur 4 dicts CTA
# ════════════════════════════════════════════════════════════════════


class TestV141A3_I18nSymmetry:
    """V141 A.3 — 6 langs symétrie pour 4 nouveaux dicts CTA Phase T."""

    @pytest.mark.parametrize("dict_obj,name", [
        (_DRAW_PENDING_CTA_LOTO, "_DRAW_PENDING_CTA_LOTO"),
        (_DRAW_PENDING_CTA_EM, "_DRAW_PENDING_CTA_EM"),
        (_NO_DRAW_THIS_DAY_LOTO, "_NO_DRAW_THIS_DAY_LOTO"),
        (_NO_DRAW_THIS_DAY_EM, "_NO_DRAW_THIS_DAY_EM"),
    ])
    def test_all_6_langs_present_with_placeholder(self, dict_obj, name):
        """V141 A.3 — chaque dict CTA expose 6 langs + placeholder `{date}`."""
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            assert lang in dict_obj, f"Lang {lang!r} manquante dans {name}"
            assert "{date}" in dict_obj[lang], (
                f"Placeholder {{date}} manquant dans {name}[{lang}]"
            )


# ════════════════════════════════════════════════════════════════════
# V141 A.3 — BUG #7 : Orphan stat-single detection (log-only)
# Détecte "1 num + N apparitions/times/etc." sans tag factuel
# ════════════════════════════════════════════════════════════════════


class TestV141A3_OrphanStatSingle:
    """V141 A.3 — BUG #7 : détection 1 num + N apparitions sans contexte factuel."""

    def test_orphan_stat_fr_logs_warning(self, caplog):
        """FR — 'Le 42 est sorti 95 fois' sans tag factuel → log warning."""
        with caplog.at_level(logging.WARNING, logger="services.chat_pipeline_gemini"):
            _check_sql_number_hallucination(
                "", "Le 42 est sorti 95 fois en historique.", "G", "[TEST]"
            )
        assert "HALLUCINATION_ORPHAN_STAT_SINGLE" in caplog.text

    def test_orphan_stat_en_logs_warning(self, caplog):
        """EN — 'Number 42 appeared 95 times' sans tag factuel → log warning."""
        with caplog.at_level(logging.WARNING, logger="services.chat_pipeline_gemini"):
            _check_sql_number_hallucination(
                "", "Number 42 appeared 95 times in past draws.", "G", "[TEST]"
            )
        assert "HALLUCINATION_ORPHAN_STAT_SINGLE" in caplog.text

    def test_orphan_stat_es_logs_warning(self, caplog):
        """ES — 'El 42 salió 95 veces' sans tag factuel → log warning."""
        with caplog.at_level(logging.WARNING, logger="services.chat_pipeline_gemini"):
            _check_sql_number_hallucination(
                "", "El 42 salió 95 veces en sorteos pasados.", "G", "[TEST]"
            )
        assert "HALLUCINATION_ORPHAN_STAT_SINGLE" in caplog.text

    def test_orphan_stat_with_factual_context_no_log(self, caplog):
        """Tag factuel présent → suppression du warning (intended behavior)."""
        ctx = "[RÉSULTAT TIRAGE 12/01/2026]\n42 - 12 - 33 - 45 - 7"
        with caplog.at_level(logging.WARNING, logger="services.chat_pipeline_gemini"):
            _check_sql_number_hallucination(
                ctx, "Le 42 est sorti 95 fois.", "T", "[TEST]"
            )
        assert "HALLUCINATION_ORPHAN_STAT_SINGLE" not in caplog.text

    def test_orphan_stat_num_over_50_no_log(self, caplog):
        """Numéro > 50 (hors range Loto/EM) → pas de log (anti faux positif)."""
        with caplog.at_level(logging.WARNING, logger="services.chat_pipeline_gemini"):
            _check_sql_number_hallucination(
                "", "Le 75 est sorti 95 fois selon nos sources.", "G", "[TEST]"
            )
        assert "HALLUCINATION_ORPHAN_STAT_SINGLE" not in caplog.text

    def test_orphan_stat_no_keyword_no_log(self, caplog):
        """Pas de keyword stat → pas de log (texte lambda)."""
        with caplog.at_level(logging.WARNING, logger="services.chat_pipeline_gemini"):
            _check_sql_number_hallucination(
                "", "Tu as 42 années pour 95 idées différentes.", "G", "[TEST]"
            )
        assert "HALLUCINATION_ORPHAN_STAT_SINGLE" not in caplog.text


# ════════════════════════════════════════════════════════════════════
# V141 A.3 — Extension _recheck_phase0_draw_accuracy à Phase 2/3/3-bis
# (cohérent V131.G qui avait étendu de "0" → ("0","1","T"))
# ════════════════════════════════════════════════════════════════════


class TestV141A3_RecheckPhasesExtended:
    """V141 A.3 — _recheck_phase0_draw_accuracy étendue Phase 2 + 3 + 3-bis."""

    @pytest.mark.asyncio
    async def test_phase_2_now_covered(self):
        """V141 A.3 — Phase 2 + mismatch → safe_replacement."""
        response = "Le tirage du 28 mars 2026 : 1-10-12-29-49"
        mock_tirage = {"boules": [18, 20, 35, 38, 48], "chance": 5, "date": "2026-03-28"}
        get_tirage_fn = AsyncMock(return_value=mock_tirage)
        result = await _recheck_phase0_draw_accuracy(
            response, "2", "fr", "[TEST]",
            get_tirage_fn=get_tirage_fn, game="loto",
        )
        assert result is not None
        assert "donn" in result.lower() or "data" in result.lower()

    @pytest.mark.asyncio
    async def test_phase_3_now_covered(self):
        """V141 A.3 — Phase 3 + mismatch → safe_replacement."""
        response = "Le tirage du 15 février 2026 : 7-14-21-28-35"
        mock_tirage = {"boules": [3, 8, 11, 22, 44], "chance": 5, "date": "2026-02-15"}
        get_tirage_fn = AsyncMock(return_value=mock_tirage)
        result = await _recheck_phase0_draw_accuracy(
            response, "3", "fr", "[TEST]",
            get_tirage_fn=get_tirage_fn, game="loto",
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_phase_3_bis_now_covered(self):
        """V141 A.3 — Phase 3-bis + mismatch → safe_replacement."""
        response = "Le tirage du 1 avril 2026 : 5-15-25-35-45"
        mock_tirage = {"boules": [2, 9, 17, 28, 44], "chance": 7, "date": "2026-04-01"}
        get_tirage_fn = AsyncMock(return_value=mock_tirage)
        result = await _recheck_phase0_draw_accuracy(
            response, "3-bis", "fr", "[TEST]",
            get_tirage_fn=get_tirage_fn, game="loto",
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_phase_2_valid_draw_no_replacement(self):
        """V141 A.3 — Phase 2 + draw matching DB → None (anti faux positif)."""
        response = "Le tirage du 28 mars 2026 : 18-20-35-38-48"
        mock_tirage = {"boules": [18, 20, 35, 38, 48], "chance": 5, "date": "2026-03-28"}
        get_tirage_fn = AsyncMock(return_value=mock_tirage)
        result = await _recheck_phase0_draw_accuracy(
            response, "2", "fr", "[TEST]",
            get_tirage_fn=get_tirage_fn, game="loto",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_phase_3_valid_draw_no_replacement(self):
        """V141 A.3 — Phase 3 + draw matching DB → None (anti faux positif)."""
        response = "Le tirage du 15 février 2026 : 3-8-11-22-44"
        mock_tirage = {"boules": [3, 8, 11, 22, 44], "chance": 5, "date": "2026-02-15"}
        get_tirage_fn = AsyncMock(return_value=mock_tirage)
        result = await _recheck_phase0_draw_accuracy(
            response, "3", "fr", "[TEST]",
            get_tirage_fn=get_tirage_fn, game="loto",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_phases_hors_scope_still_skipped(self):
        """V141 A.3 — Phases hors ('0','1','T','2','3','3-bis') restent skippées."""
        response = "Une grille HYBRIDE : 1-2-3-4-5"
        get_tirage_fn = AsyncMock()
        for phase in ("G", "SQL", "AFFIRMATION", "P", "OOR", "I", "EVAL", "0-bis"):
            result = await _recheck_phase0_draw_accuracy(
                response, phase, "fr", "[TEST]",
                get_tirage_fn=get_tirage_fn, game="loto",
            )
            assert result is None, f"Phase {phase} doit rester skippée"
        # get_tirage_fn ne doit JAMAIS avoir été appelé
        get_tirage_fn.assert_not_called()


# ════════════════════════════════════════════════════════════════════
# V141 A.3.1 — BUG #4 : Phase G fallthrough silent failure
# Cas terrain #3 reproductible : "Pru importe" 9/05 05:24 → leak Gemini
# ════════════════════════════════════════════════════════════════════


class TestV141A31_PhaseGFallthrough:
    """V141 A.3.1 BUG #4 : injection contexte safe + observabilité Phase G fail."""

    def test_phase_g_success_returns_none(self):
        """Phase G success (generation_context truthy) → helper retourne None."""
        ctx_filled = "[GRILLE GÉNÉRÉE PAR HYBRIDE]\n1-12-23-34-45 chance=7"
        assert _phase_g_get_safe_fallthrough_context(ctx_filled, "fr") is None

    def test_phase_g_no_grids_returns_safe_fr(self):
        """Phase G `_gen_result.grids = []` → contexte safe FR."""
        result = _phase_g_get_safe_fallthrough_context("", "fr")
        assert result is not None
        assert "[ERREUR GÉNÉRATION HYBRIDE]" in result
        assert "Ne PAS inventer" in result

    def test_phase_g_engine_timeout_returns_safe_en(self):
        """Phase G timeout (label engine_timeout) → contexte safe EN."""
        result = _phase_g_get_safe_fallthrough_context("", "en")
        assert result is not None
        assert "[HYBRIDE GENERATION ERROR]" in result
        assert "Do NOT invent" in result

    def test_phase_g_engine_error_returns_safe_es(self):
        """Phase G RuntimeError (label engine_error) → contexte safe ES."""
        result = _phase_g_get_safe_fallthrough_context("", "es")
        assert result is not None
        assert "[ERROR GENERACIÓN HYBRIDE]" in result

    def test_phase_g_unknown_lang_falls_back_fr(self):
        """Lang inconnue → fallback FR (cas terrain #3 reproductible)."""
        result = _phase_g_get_safe_fallthrough_context("", "zz")
        assert result is not None
        assert "[ERREUR GÉNÉRATION HYBRIDE]" in result

    def test_phase_g_fallthrough_dict_6_langs_symmetry(self):
        """V141 A.3.1 — `_PHASE_G_FALLTHROUGH_CONTEXT` expose les 6 langs."""
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            assert lang in _PHASE_G_FALLTHROUGH_CONTEXT
            # Anti-hallucination prompt invariant 6 langs
            assert any(
                marker in _PHASE_G_FALLTHROUGH_CONTEXT[lang]
                for marker in ("Ne PAS inventer", "Do NOT invent", "NO inventes",
                              "NÃO inventes", "Erfinde KEINE", "Verzin GEEN")
            )


# ════════════════════════════════════════════════════════════════════
# V141 A.3.2 — BUG #6 : Phase AFFIRMATION transitif anti-hallucination
# Cas terrain #2 reproductible : "Oui" 8/05 21:06 → leak brut classement
# ════════════════════════════════════════════════════════════════════


class TestV141A32_PhaseAffirmationTransitive:
    """V141 A.3.2 BUG #6 : extension V125 A2 filter à phase AFFIRMATION.

    Cas terrain : "Oui" après assistant cite [RÉSULTAT TIRAGE 12/01]
    → Phase AFFIRMATION (pas Phase 0) → V125 A2 transitif bypass
    → leak chiffres bruts. Fix : phase in ("0", "AFFIRMATION").
    """

    def _build_history_with_factual_tag(self):
        """Helper — historique réaliste avec tag factuel dans dernier assistant."""
        return [
            {"role": "user", "content": "Stats du numéro 1 ?"},
            {"role": "assistant", "content": (
                "[RÉSULTAT SQL]Le numéro 1 est sorti 112 fois.[/RÉSULTAT SQL]\n"
                "Veux-tu plus de détails ?"
            )},
        ]

    def test_phase_affirmation_invented_numbers_replaced(self):
        """Phase AFFIRMATION + history factuel + Gemini invente seq → safe replacement."""
        history = self._build_history_with_factual_tag()
        gemini_response = "Voici les numéros: 12-25-37-44-49 que je te propose."
        result = _check_sql_number_hallucination(
            "", gemini_response, "AFFIRMATION", "[TEST]",
            lang="fr", history=history,
        )
        # Attendu : V141 A.3.2 active V125 A2 transitif → invented détecté → safe
        assert result is not None
        assert "données exactes" in result.lower()

    def test_phase_affirmation_valid_response_returns_none(self):
        """Phase AFFIRMATION + history factuel + réponse valide → None (no false positive)."""
        history = self._build_history_with_factual_tag()
        gemini_response = "Oui bien sûr, le numéro 1 est sorti 112 fois historiquement."
        result = _check_sql_number_hallucination(
            "", gemini_response, "AFFIRMATION", "[TEST]",
            lang="fr", history=history,
        )
        assert result is None

    def test_phase_affirmation_no_factual_history_returns_none(self):
        """Phase AFFIRMATION sans history factuel → None (early return V125 A2)."""
        history = [
            {"role": "user", "content": "Salut"},
            {"role": "assistant", "content": "Bonjour, comment puis-je t'aider ?"},
        ]
        result = _check_sql_number_hallucination(
            "", "Voici 12-25-37-44-49.", "AFFIRMATION", "[TEST]",
            lang="fr", history=history,
        )
        assert result is None

    def test_phase_0_regression_still_works(self):
        """V141 A.3.2 — Phase 0 V125 A2 transitif reste fonctionnel (régression)."""
        history = self._build_history_with_factual_tag()
        gemini_response = "Voici les numéros: 12-25-37-44-49."
        result = _check_sql_number_hallucination(
            "", gemini_response, "0", "[TEST]",
            lang="fr", history=history,
        )
        # Régression V125 A2 : Phase 0 + factual history + invented → safe
        assert result is not None

    def test_other_conversational_phases_still_bypassed(self):
        """Phases conversationnelles hors AFFIRMATION/0 → bypass anti-hallu."""
        history = self._build_history_with_factual_tag()
        gemini_response = "Voici 12-25-37-44-49."
        for phase in ("G", "EVAL", "REFUS", "AFFIRMATION_SANS_CONTEXTE", "GAME_KEYWORD"):
            result = _check_sql_number_hallucination(
                "", gemini_response, phase, "[TEST]",
                lang="fr", history=history,
            )
            assert result is None, f"Phase {phase} doit rester bypassed"
