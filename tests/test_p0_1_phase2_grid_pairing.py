"""1.6.056 P0-1 — Contrôle 2 Phase 2 : appariement date ↔ suite par ligne.

Cas de référence : chat_log 8011 (16/10/2026). Grille soumise 14-24-25-39-45,
Gemini cite la « meilleure correspondance » du 19/07/2025 issue du bloc
`[ANALYSE DE GRILLE]` → l'ancien croisement (1re suite × 1re date du texte entier)
comparait la grille utilisateur au tirage du 19/07/2025 → blocage à tort.
Audit RO 19/10 : 29/29 blocages Phase 2 sur 30 j = faux positifs.

Règles testées (`_pair_phase2_draw_citations`) :
- une date n'est appariée qu'à une suite de sa ligne (la plus proche) ;
- ligne titre « … date : » → 1re suite de la ligne suivante ;
- grille soumise écartée seulement si la date figure dans le bloc d'analyse
  (log-only `PHASE2_GRID_PAIR_SKIPPED`) ;
- phases 0/1/T/3/3-bis : croisement historique inchangé.

Aucun appel Vertex ni DB : `get_tirage_fn` est un AsyncMock à dictionnaire.
"""
import asyncio
import logging
import time
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.chat_pipeline_gemini import (
    _STRICT_BLOCK_FALLBACK_I18N,
    _find_draw_dates,
    _pair_phase2_draw_citations,
    _parse_draw_date_multilang,
    _recheck_phase0_draw_accuracy,
    stream_and_respond,
)
from services.chat_utils import _format_grille_context
from services.chat_utils_em import _format_grille_context_em


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

_DRAWS_LOTO = {
    date(2025, 7, 19): {"date": "2025-07-19", "boules": [18, 19, 24, 25, 45], "chance": 4},
    date(2026, 3, 28): {"date": "2026-03-28", "boules": [2, 9, 17, 30, 41], "chance": 1},
}
_DRAWS_EM = {
    date(2025, 10, 3): {"date": "2025-10-03", "boules": [6, 12, 18, 25, 41], "etoiles": [5, 9]},
}

_RESP_8011 = (
    "Ta grille 14 - 24 - 25 - 39 - 45 n'est jamais sortie. Sa meilleure correspondance date du "
    "19/07/2025 avec 3 numéros communs (24, 25, 45)."
)


def _tirage_fn(draws):
    async def _get(d):
        return draws.get(d)
    return AsyncMock(side_effect=_get)


def _analyse(nums):
    return {
        "somme": sum(nums), "somme_ok": True, "pairs": 2, "impairs": 3,
        "equilibre_pair_impair": True, "bas": 2, "hauts": 3, "equilibre_bas_haut": True,
        "dispersion": max(nums) - min(nums), "dispersion_ok": True, "consecutifs": 0,
        "numeros_chauds": [], "numeros_froids": [], "numeros_neutres": list(nums),
        "conformite_pct": 74, "badges": ["Équilibré"],
    }


def _ctx_8011():
    """Bloc réel `_format_grille_context` du cas 8011 (meilleure correspondance 19/07/2025)."""
    return _format_grille_context({
        "numeros": [14, 24, 25, 39, 45], "chance": None,
        "analyse": _analyse([14, 24, 25, 39, 45]),
        "historique": {
            "deja_sortie": False, "exact_dates": [],
            "meilleure_correspondance": {
                "nb_numeros_communs": 3, "date": "2025-07-19",
                "numeros_communs": [24, 25, 45], "chance_match": False,
            },
        },
    })


def _ctx_em():
    """Bloc réel `_format_grille_context_em` (cas 6760, meilleure correspondance 03/10/2025)."""
    return _format_grille_context_em({
        "numeros": [3, 12, 18, 25, 33], "etoiles": [3, 4],
        "analyse": _analyse([3, 12, 18, 25, 33]),
        "historique": {
            "deja_sortie": False, "exact_dates": [],
            "meilleure_correspondance": {
                "nb_numeros_communs": 3, "date": "2025-10-03",
                "numeros_communs": [12, 18, 25], "etoiles_match": False,
            },
        },
    })


async def _recheck(response, ctx, draws=_DRAWS_LOTO, game="loto", phase="2", fn=None):
    return await _recheck_phase0_draw_accuracy(
        response, phase, "fr", "[TEST P0-1]",
        get_tirage_fn=fn or _tirage_fn(draws), game=game,
        enrichment_context=ctx,
    )


async def _collect(gen):
    return [c async for c in gen]


def _strict_ctx(phase, enrichment, draws):
    return {
        "system_prompt": "sys",
        "contents": [{"role": "user", "parts": [{"text": "test"}]}],
        "mode": "chat",
        "insult_prefix": "",
        "history": [],
        "lang": "fr",
        "_http_client": MagicMock(),
        "gem_api_key": "",
        "_strict_hallucination_block": True,
        "_chat_meta": {
            "phase": phase, "lang": "fr", "t0": time.monotonic(),
            "enrichment_context": enrichment,
        },
        "_get_tirage_fn": _tirage_fn(draws),
        "_game": "loto",
    }


# ─────────────────────────────────────────────────────────────────────
# Classe 1 — _find_draw_dates + synchro avec _parse_draw_date_multilang
# ─────────────────────────────────────────────────────────────────────


class TestFindDrawDates:
    """1.6.056 P0-1 — extraction de toutes les dates avec position."""

    def test_find_draw_dates_multiple_sorted_by_position(self):
        found = _find_draw_dates("le 19/07/2025 puis 2026-03-28 et le 3 mai 2024")
        assert [d for _, _, d in found] == [date(2025, 7, 19), date(2026, 3, 28), date(2024, 5, 3)]

    def test_find_draw_dates_priority_no_overlap(self):
        """« first of May 2026 » pris par DMY_WORD, pas relu par MDY."""
        found = _find_draw_dates("first of May 2026")
        assert [d for _, _, d in found] == [date(2026, 5, 1)]

    def test_find_draw_dates_invalid_date_ignored(self):
        found = _find_draw_dates("le 31/02/2025 et le 19/07/2025")
        assert [d for _, _, d in found] == [date(2025, 7, 19)]

    @pytest.mark.parametrize("text", [
        "Tirage 2025-07-19 : 18-19-24-25-45",                 # ISO
        "Tirage du 19/07/2025 : 18-19-24-25-45",              # JJ/MM/AAAA
        "Tirage du 19 juillet 2025 : 18-19-24-25-45",         # J mois AAAA (FR)
        "Ziehung vom 12. Dezember 2025",                      # J mois AAAA (DE point ordinal)
        "Sorteo del 1 de mayo de 2026",                       # J de mes de AAAA (ES)
        "Tirage du 1er mai 2026",                             # ordinal numérique
        "Tirage du premier mai 2026",                         # ordinal en lettres
        "The first of May 2026 draw",                         # ordinal en lettres EN
        "Draw of May 3rd, 2026",                              # MDY
        "Draw of December 12, 2025",                          # MDY
    ])
    def test_date_patterns_in_sync_with_parse_draw_date_multilang(self, text):
        """Ajout 3 — `_DATE_PATTERNS_ORDERED` duplique les motifs de
        `_parse_draw_date_multilang` : la 1re date (unique ici) doit être identique.
        Échoue si l'un des deux évolue sans l'autre (ex. futur correctif JJ.MM.AAAA)."""
        found = _find_draw_dates(text)
        parsed = _parse_draw_date_multilang(text)
        assert parsed is not None
        assert found, f"_find_draw_dates ne reconnaît pas : {text!r}"
        assert found[0][2] == parsed

    @pytest.mark.parametrize("text", ["Tirage du 20.10.2026", "aucune date ici"])
    def test_unparsed_formats_in_sync(self, text):
        """Formats non reconnus (JJ.MM.AAAA, cas 8124) : ignorés des deux côtés."""
        assert _parse_draw_date_multilang(text) is None
        assert _find_draw_dates(text) == []


# ─────────────────────────────────────────────────────────────────────
# Classe 2 — Phase 2 Loto : appariement + grille soumise
# ─────────────────────────────────────────────────────────────────────


class TestPhase2PairingLoto:
    """1.6.056 P0-1 — scénarios (a) à (d) + cas limites."""

    @pytest.mark.asyncio
    async def test_8011_replay_not_blocked(self):
        """(a) Rejeu 8011 : grille + date de meilleure correspondance même ligne → None."""
        assert await _recheck(_RESP_8011, _ctx_8011()) is None

    @pytest.mark.asyncio
    async def test_8011_grid_disorder_separate_lines_not_blocked(self):
        """(a) Grille citée dans le désordre, date sur une autre ligne → None."""
        response = (
            "📊 Analyse de 45 - 14 - 24 - 39 - 25\n\n- Somme 147 ✓\n"
            "- Meilleure correspondance : le 19 juillet 2025 (24, 25, 45)"
        )
        assert await _recheck(response, _ctx_8011()) is None

    @pytest.mark.asyncio
    async def test_invented_draw_on_block_date_blocked(self):
        """(b) Tirage inventé à la date du bloc (suite ≠ grille) → bloqué."""
        response = "Ta grille 14 - 24 - 25 - 39 - 45.\nLe tirage du 19/07/2025 était 3 - 9 - 24 - 25 - 45."
        assert await _recheck(response, _ctx_8011()) is not None

    @pytest.mark.asyncio
    async def test_invented_draw_same_line_as_grid_blocked(self):
        """(b) Grille et tirage inventé sur la même ligne : la grille est écartée,
        la suite inventée reste vérifiée → bloqué."""
        response = "Ta grille 14 - 24 - 25 - 39 - 45 rappelle le tirage du 19/07/2025 : 3 - 9 - 24 - 25 - 45."
        assert await _recheck(response, _ctx_8011()) is not None

    @pytest.mark.asyncio
    async def test_invented_draw_title_line_then_list_blocked(self):
        """(b) Ligne titre « … date : » puis suite à la ligne suivante → bloqué."""
        response = "**Tirage du 19 juillet 2025 :**\n• 3 - 9 - 24 - 25 - 45"
        assert await _recheck(response, _ctx_8011()) is not None

    @pytest.mark.asyncio
    async def test_grid_claimed_drawn_on_date_outside_block_blocked(self):
        """(b) « Ta grille est sortie le X » avec X hors bloc → vérifié → bloqué."""
        response = "Bonne nouvelle : ta grille 14 - 24 - 25 - 39 - 45 est sortie le 28/03/2026 !"
        assert await _recheck(response, _ctx_8011()) is not None

    @pytest.mark.asyncio
    async def test_phase2_grid_claimed_on_block_date_passes_but_is_logged(self, caplog):
        """Ajout 2 — RISQUE ACCEPTÉ (arbitrage Jyppy 19/10/2026, lot 1.6.056 P0-1).

        « Ta grille <grille> est sortie le <date du bloc> » passe sans contrôle : le couple
        (grille, date de meilleure correspondance) est écarté par la règle 1 affinée.
        L'ancien code le bloquait, par accident. Trou accepté (71 % de faux positifs
        Phase 2 sinon) mais mesurable en prod via le log-only `PHASE2_GRID_PAIR_SKIPPED`.
        """
        response = "Ta grille 14 - 24 - 25 - 39 - 45 est sortie le 19/07/2025 !"
        fn = _tirage_fn(_DRAWS_LOTO)
        with caplog.at_level(logging.INFO, logger="services.chat_pipeline_gemini"):
            result = await _recheck(response, _ctx_8011(), fn=fn)
        assert result is None
        fn.assert_not_called()
        skipped = [r.getMessage() for r in caplog.records if "PHASE2_GRID_PAIR_SKIPPED" in r.getMessage()]
        assert len(skipped) == 1
        assert "date=2025-07-19" in skipped[0]
        assert "grid=[14, 24, 25, 39, 45]" in skipped[0]
        assert "est sortie le 19/07/2025" in skipped[0]

    def test_grid_pair_skipped_log_excerpt_single_line_capped(self, caplog):
        """Ajout 1 — extrait de la ligne : retours à la ligne retirés, 200 caractères max."""
        response = "Ta grille 14 - 24 - 25 - 39 - 45 le 19/07/2025 " + "x" * 400
        with caplog.at_level(logging.INFO, logger="services.chat_pipeline_gemini"):
            pairs = _pair_phase2_draw_citations(response, _ctx_8011(), "[TEST P0-1]")
        assert pairs == []
        msg = next(r.getMessage() for r in caplog.records if "PHASE2_GRID_PAIR_SKIPPED" in r.getMessage())
        excerpt = msg.split("line=", 1)[1]
        assert len(excerpt) == 200
        assert "\n" not in msg

    @pytest.mark.asyncio
    async def test_grid_and_real_draw_real_date_not_blocked(self):
        """(c) Grille + vrai tirage avec sa vraie date, même ligne → None."""
        response = (
            "Ta grille 14 - 24 - 25 - 39 - 45 partage 3 numéros avec le tirage du "
            "19/07/2025 : 18 - 19 - 24 - 25 - 45."
        )
        assert await _recheck(response, _ctx_8011()) is None

    @pytest.mark.asyncio
    async def test_grid_and_real_draw_title_format_not_blocked(self):
        """(c) Grille, puis titre daté et vrai tirage à la ligne suivante → None."""
        response = "Ta grille : 14 - 24 - 25 - 39 - 45\n\nTirage du 19/07/2025 :\n18 - 19 - 24 - 25 - 45"
        assert await _recheck(response, _ctx_8011()) is None

    @pytest.mark.asyncio
    async def test_date_absent_db_seq_not_grid_blocked(self, caplog):
        """(d) Date absente de la base + suite ≠ grille → bloqué, log DATE_NOT_IN_DB conservé."""
        response = "Ta grille 14 - 24 - 25 - 39 - 45.\nLe tirage du 21/07/2025 : 3 - 9 - 24 - 25 - 45."
        with caplog.at_level(logging.WARNING, logger="services.chat_pipeline_gemini"):
            result = await _recheck(response, _ctx_8011())
        assert result is not None
        assert "aucune donnée disponible pour le 2025-07-21" in result
        assert "PHASE0_DATE_NOT_IN_DB" in caplog.text

    @pytest.mark.asyncio
    async def test_two_dates_same_line_nearest_pairing(self):
        """Deux couples sur une ligne, appariés au plus proche : justes → None."""
        response = "Le 19/07/2025 (18 - 19 - 24 - 25 - 45) et le 28/03/2026 (2 - 9 - 17 - 30 - 41)."
        assert await _recheck(response, _ctx_8011()) is None

    @pytest.mark.asyncio
    async def test_two_dates_same_line_second_invented_blocked(self):
        """Deux couples, le 2e inventé → bloqué (l'ancien code ne voyait que le 1er)."""
        response = "Le 19/07/2025 (18 - 19 - 24 - 25 - 45) et le 28/03/2026 (2 - 9 - 17 - 30 - 44)."
        assert await _recheck(response, _ctx_8011()) is not None

    @pytest.mark.asyncio
    async def test_date_without_sequence_not_checked(self):
        """Date sans suite sur sa ligne (pas de format titre) → aucune lecture DB."""
        response = "Meilleure correspondance le 19/07/2025.\n\nUne idée : 3 - 12 - 27 - 33 - 41"
        fn = _tirage_fn(_DRAWS_LOTO)
        assert await _recheck(response, _ctx_8011(), fn=fn) is None
        fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_timeout_phase2_non_blocking(self):
        """Timeout DB (1s V127) en Phase 2 → None, jamais bloquant."""
        async def _slow(_d):
            await asyncio.sleep(5)
        response = "Le tirage du 19/07/2025 était 3 - 9 - 24 - 25 - 45."
        assert await _recheck(response, _ctx_8011(), fn=AsyncMock(side_effect=_slow)) is None

    @pytest.mark.asyncio
    async def test_legacy_context_without_header_still_checked(self):
        """En-tête non parsable → appariement sans exclusion de grille (côté sûr)."""
        response = "Le tirage du 28 mars 2026 : 1-10-12-29-49"
        ctx = "[ANALYSE DE GRILLE] grille soumise 1-10-12-29-49"
        assert await _recheck(response, ctx) is not None


# ─────────────────────────────────────────────────────────────────────
# Classe 2 bis — log-only PHASE2_DATE_UNPAIRED (mesure de couverture)
# ─────────────────────────────────────────────────────────────────────

_RESP_8237 = (
    "Oh, pas mal comme choix ! Ta grille (14, 24, 25, 39, 45) est super équilibrée avec un "
    "score de conformité de 99% ! ✨\n\nElle respecte bien les ratios pairs/impairs et "
    "bas/hauts. Le 24 est chaud, le 14 et le 39 sont froids, ça fait un bon mix !\n\n"
    "Elle n'est jamais sortie, mais a eu 3 numéros en commun le 19 juillet 2025. "
    "Tu veux que je détaille ?"
)


def _logged(caplog, key):
    return [r.getMessage() for r in caplog.records if key in r.getMessage()]


class TestPhase2DateUnpairedLog:
    """1.6.056 P0-1 — log-only `PHASE2_DATE_UNPAIRED` : dates de Phase 2 restées sans
    suite appariée (smoke 19/10, chat_log 8237 : grille ligne 0, date ligne 4)."""

    @pytest.mark.asyncio
    async def test_smoke_8237_paragraph_break_logged_unpaired(self, caplog):
        fn = _tirage_fn(_DRAWS_LOTO)
        with caplog.at_level(logging.INFO, logger="services.chat_pipeline_gemini"):
            result = await _recheck(_RESP_8237, _ctx_8011(), fn=fn)
        assert result is None
        fn.assert_not_called()
        unpaired = _logged(caplog, "PHASE2_DATE_UNPAIRED")
        assert len(unpaired) == 1
        assert "date=2025-07-19 in_block=True grid_in_response=True" in unpaired[0]
        assert "3 numéros en commun le 19 juillet 2025" in unpaired[0]
        assert _logged(caplog, "PHASE2_GRID_PAIR_SKIPPED") == []

    def test_date_without_any_sequence_in_response_not_logged(self, caplog):
        with caplog.at_level(logging.INFO, logger="services.chat_pipeline_gemini"):
            _pair_phase2_draw_citations("Meilleure correspondance le 19/07/2025.", _ctx_8011(), "[T]")
        assert _logged(caplog, "PHASE2_DATE_UNPAIRED") == []

    def test_date_paired_normally_not_logged(self, caplog):
        response = "Le 19/07/2025 (18 - 19 - 24 - 25 - 45)."
        with caplog.at_level(logging.INFO, logger="services.chat_pipeline_gemini"):
            pairs = _pair_phase2_draw_citations(response, _ctx_8011(), "[T]")
        assert len(pairs) == 1
        assert _logged(caplog, "PHASE2_DATE_UNPAIRED") == []

    def test_grid_and_block_date_same_line_only_skipped_logged(self, caplog):
        response = "Ta grille 14 - 24 - 25 - 39 - 45 est sortie le 19/07/2025 !"
        with caplog.at_level(logging.INFO, logger="services.chat_pipeline_gemini"):
            _pair_phase2_draw_citations(response, _ctx_8011(), "[T]")
        assert len(_logged(caplog, "PHASE2_GRID_PAIR_SKIPPED")) == 1
        assert _logged(caplog, "PHASE2_DATE_UNPAIRED") == []

    def test_same_unpaired_date_twice_logged_once(self, caplog):
        response = (
            "Ta grille 14 - 24 - 25 - 39 - 45.\n\nMeilleure correspondance le 19/07/2025.\n\n"
            "Oui, c'était le 19 juillet 2025 !"
        )
        with caplog.at_level(logging.INFO, logger="services.chat_pipeline_gemini"):
            _pair_phase2_draw_citations(response, _ctx_8011(), "[T]")
        assert len(_logged(caplog, "PHASE2_DATE_UNPAIRED")) == 1


# ─────────────────────────────────────────────────────────────────────
# Classe 3 — (e) Non-régression phases 0/1/T/3/3-bis
# ─────────────────────────────────────────────────────────────────────


class TestOtherPhasesUnchanged:
    """1.6.056 P0-1 — le croisement historique (1re suite × 1re date) reste en vigueur
    hors Phase 2 : la même entrée que 8011 y est toujours bloquée."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("phase", ["0", "1", "T", "3", "3-bis"])
    async def test_other_phases_keep_historical_cross_check(self, phase):
        result = await _recheck(_RESP_8011, _ctx_8011(), phase=phase)
        assert result is not None

    @pytest.mark.asyncio
    async def test_same_input_phase_2_not_blocked(self):
        assert await _recheck(_RESP_8011, _ctx_8011(), phase="2") is None


# ─────────────────────────────────────────────────────────────────────
# Classe 4 — (f) EuroMillions Phase 2 (boules 1-50 + étoiles)
# ─────────────────────────────────────────────────────────────────────


class TestPhase2PairingEuroMillions:
    """1.6.056 P0-1 — même logique EM, étoiles lues après la suite retenue."""

    @pytest.mark.asyncio
    async def test_em_grid_user_stars_block_date_not_blocked(self):
        """Cas 6760 : grille + étoiles utilisateur + date du bloc → None."""
        response = "Ta grille 3 - 12 - 18 - 25 - 33 étoiles 3 et 4 : meilleure correspondance le 03/10/2025."
        assert await _recheck(response, _ctx_em(), _DRAWS_EM, "em") is None

    @pytest.mark.asyncio
    async def test_em_real_full_draw_not_blocked(self):
        response = (
            "Ta grille 3 - 12 - 18 - 25 - 33 étoiles 3 et 4.\n"
            "Le 03/10/2025 : 6 - 12 - 18 - 25 - 41 étoiles 5 et 9."
        )
        assert await _recheck(response, _ctx_em(), _DRAWS_EM, "em") is None

    @pytest.mark.asyncio
    async def test_em_invented_stars_blocked(self):
        """Boules justes, étoiles inventées ; étoiles user plus loin sur la ligne ignorées."""
        response = (
            "Le 03/10/2025 : 6 - 12 - 18 - 25 - 41 étoiles 7 et 9, "
            "ta grille 3 - 12 - 18 - 25 - 33 étoiles 3 et 4."
        )
        assert await _recheck(response, _ctx_em(), _DRAWS_EM, "em") is not None

    @pytest.mark.asyncio
    async def test_em_invented_balls_up_to_50_blocked(self):
        response = "Le 03/10/2025 : 6 - 12 - 18 - 48 - 50 étoiles 5 et 9."
        assert await _recheck(response, _ctx_em(), _DRAWS_EM, "em") is not None


# ─────────────────────────────────────────────────────────────────────
# Classe 5 — Strict mode bout en bout (stream_and_respond)
# ─────────────────────────────────────────────────────────────────────


class TestStrictStreamPhase2:
    """1.6.056 P0-1 — buffer mode V131.G, Phase 2 réelle."""

    @pytest.mark.asyncio
    async def test_strict_stream_8011_delivered(self):
        async def _stream(*args, **kwargs):
            yield _RESP_8011

        events = await _collect(stream_and_respond(
            _strict_ctx("2", _ctx_8011(), _DRAWS_LOTO), "FALLBACK", "[TEST P0-1]", "loto", "fr",
            "14 24 25 39 45", "page", "chat", stream_fn=_stream,
        ))
        full = "".join(events)
        assert "19/07/2025" in full
        assert _STRICT_BLOCK_FALLBACK_I18N["fr"] not in full

    @pytest.mark.asyncio
    async def test_strict_stream_invented_draw_blocked(self):
        async def _stream(*args, **kwargs):
            yield "Ta grille 14 - 24 - 25 - 39 - 45.\nLe tirage du 19/07/2025 était 3 - 9 - 24 - 25 - 45."

        events = await _collect(stream_and_respond(
            _strict_ctx("2", _ctx_8011(), _DRAWS_LOTO), "FALLBACK", "[TEST P0-1]", "loto", "fr",
            "14 24 25 39 45", "page", "chat", stream_fn=_stream,
        ))
        full = "".join(events)
        assert _STRICT_BLOCK_FALLBACK_I18N["fr"] in full
        assert "3 - 9 - 24 - 25 - 45" not in full
