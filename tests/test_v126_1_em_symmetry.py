"""
V126.1 Hotfix — regroupement tests F1-bis + F2 + F3 + F4.

Scope :
- F1-bis : regex DE avec point (`12. Dezember 2025`) + non-régression sans point
- F2 : extension `_SQL_EVOCATIVE_KEYWORDS` 6 langs (keywords EM EN manquants,
       équivalents FR/ES/PT/DE/NL) — additif, V125/V126 L13 préservés
- F3 : `_EM_STARS_RE` + branche étoiles dans `_recheck_phase0_draw_accuracy`
- F4 : test phare bug 12/12/2025 EM EN (log 2118) + non-régression Loto FR
"""

from datetime import date
import logging
from unittest.mock import AsyncMock

import pytest

from services.base_chat_detect_intent import (
    _is_sql_continuation,
    _SQL_EVOCATIVE_KEYWORDS,
)
from services.chat_pipeline_gemini import (
    _parse_draw_date_multilang,
    _recheck_phase0_draw_accuracy,
    _EM_STARS_RE,
)


# ═════════════════════════════════════════════════════════════════════
# F1-bis — Patch regex DE `\.?` (12. Dezember) + non-régression
# ═════════════════════════════════════════════════════════════════════


class TestV126_1_F1bis_DE_DatePatch:
    """V126.1 F1-bis : `_DATE_RE_DMY` doit accepter le point allemand."""

    def test_parse_de_12_dezember_avec_point(self):
        """V126.1 F1-bis : `12. Dezember 2025` (point ordinal) → 2025-12-12."""
        assert _parse_draw_date_multilang(
            "Die Ziehung vom 12. Dezember 2025 war episch"
        ) == date(2025, 12, 12)

    def test_parse_de_12_dezember_sans_point_non_regression(self):
        """Non-régression V126 : `12 Dezember 2025` (sans point) reste OK."""
        assert _parse_draw_date_multilang(
            "12 Dezember 2025"
        ) == date(2025, 12, 12)


# ═════════════════════════════════════════════════════════════════════
# F2 — Extension keywords 6 langs (additif)
# ═════════════════════════════════════════════════════════════════════


class TestV126_1_F2_NewKeywords:
    """V126.1 F2 : nouveaux keywords Volet B 6 langs."""

    # --- EN (cas terrain 2118) ---

    def test_know_more_triggers_reroute_en(self):
        """Cas direct log 2118 : `"Want to know more about that draw?"`."""
        assert _is_sql_continuation(
            "Want to know more about that draw?", "en"
        ) is True

    def test_that_draw_triggers_reroute_en(self):
        assert _is_sql_continuation(
            "Tell me more about that draw.", "en"
        ) is True

    def test_this_combo_triggers_reroute_en(self):
        assert _is_sql_continuation(
            "Want me to analyse this combo?", "en"
        ) is True

    def test_this_draw_triggers_reroute_en(self):
        assert _is_sql_continuation(
            "This draw is interesting.", "en"
        ) is True

    # --- FR ---

    def test_en_savoir_plus_triggers_reroute_fr(self):
        assert _is_sql_continuation("tu veux en savoir plus ?", "fr") is True

    def test_ce_tirage_triggers_reroute_fr(self):
        assert _is_sql_continuation("je regarde ce tirage", "fr") is True

    def test_ces_numeros_triggers_reroute_fr(self):
        assert _is_sql_continuation("parle-moi de ces numéros", "fr") is True

    # --- ES ---

    def test_saber_mas_triggers_reroute_es(self):
        assert _is_sql_continuation("¿quieres saber más?", "es") is True

    def test_este_sorteo_triggers_reroute_es(self):
        assert _is_sql_continuation("dime más sobre este sorteo", "es") is True

    # --- PT ---

    def test_saber_mais_triggers_reroute_pt(self):
        assert _is_sql_continuation("queres saber mais?", "pt") is True

    def test_este_sorteio_triggers_reroute_pt(self):
        assert _is_sql_continuation("fala-me deste sorteio", "pt") is True

    # --- DE ---

    def test_mehr_wissen_triggers_reroute_de(self):
        assert _is_sql_continuation("möchtest du mehr wissen?", "de") is True

    def test_diese_ziehung_triggers_reroute_de(self):
        assert _is_sql_continuation("erzähl mir von dieser ziehung", "de") is True

    # --- NL ---

    def test_meer_weten_triggers_reroute_nl(self):
        assert _is_sql_continuation("wil je meer weten?", "nl") is True

    def test_deze_trekking_triggers_reroute_nl(self):
        assert _is_sql_continuation("vertel over deze trekking", "nl") is True


class TestV126_1_F2_NoRegression:
    """V126.1 F2 : keywords V125 + V126 L13 toujours présents (additif)."""

    def test_v125_history_still_works_en(self):
        assert _is_sql_continuation(
            "want to see the full history?", "en"
        ) is True

    def test_v125_historique_still_works_fr(self):
        assert _is_sql_continuation(
            "tu veux l'historique complet ?", "fr"
        ) is True

    def test_v126_l13_creuser_still_works_fr(self):
        assert _is_sql_continuation(
            "tu veux creuser un de ces numéros ?", "fr"
        ) is True

    def test_v126_l13_dig_deeper_still_works_en(self):
        assert _is_sql_continuation("want to dig deeper?", "en") is True

    def test_conversational_still_not_flagged_fr(self):
        """Anti-FP : message conversationnel sans keyword → False."""
        assert _is_sql_continuation(
            "tu veux parler d'autre chose ?", "fr"
        ) is False


# ═════════════════════════════════════════════════════════════════════
# F3 — Regex étoiles EM + branche étoiles dans _recheck
# ═════════════════════════════════════════════════════════════════════


class TestV126_1_F3_EmStarsRegex:
    """V126.1 F3 : `_EM_STARS_RE` extraction 2 étoiles 6 langs."""

    def test_extract_em_stars_en_colon_dash(self):
        """Format log 2118 : `stars: 3 - 8`."""
        m = _EM_STARS_RE.search("13 - 15 - 23 - 30 - 49 and the stars: 3 - 8")
        assert m and m.groups() == ("3", "8")

    def test_extract_em_stars_en_and(self):
        m = _EM_STARS_RE.search("stars 3 and 8")
        assert m and m.groups() == ("3", "8")

    def test_extract_em_stars_en_star_singular_comma(self):
        m = _EM_STARS_RE.search("star 3, star 8")
        assert m and m.groups() == ("3", "8")

    def test_extract_em_stars_fr(self):
        m = _EM_STARS_RE.search("étoiles 3 et 8")
        assert m and m.groups() == ("3", "8")

    def test_extract_em_stars_es(self):
        m = _EM_STARS_RE.search("estrellas 3 y 8")
        assert m and m.groups() == ("3", "8")

    def test_extract_em_stars_pt(self):
        m = _EM_STARS_RE.search("estrelas 3 e 8")
        assert m and m.groups() == ("3", "8")

    def test_extract_em_stars_de(self):
        m = _EM_STARS_RE.search("Sterne 3 und 8")
        assert m and m.groups() == ("3", "8")

    def test_extract_em_stars_nl(self):
        m = _EM_STARS_RE.search("sterren 3 en 8")
        assert m and m.groups() == ("3", "8")


class TestV126_1_F3_EmStarsBranch:
    """V126.1 F3 : mismatch étoiles EM → replacement (défense-en-profondeur)."""

    @pytest.mark.asyncio
    async def test_em_mismatch_stars_only(self, caplog):
        """5 boules correctes MAIS étoiles fausses → mismatch F3 détecté.

        Cas où V126 boules passe (5/5 OK) mais F3 sauve via étoiles.
        """
        caplog.set_level(logging.WARNING)
        response = (
            "Tirage du 12 December 2025 : 7 - 25 - 30 - 37 - 41 "
            "and the stars: 1 - 2"
        )
        real_em = {
            "date": date(2025, 12, 12),
            "boules": [7, 25, 30, 37, 41],
            "etoiles": [5, 11],
        }
        result = await _recheck_phase0_draw_accuracy(
            response, "0", "en", "[TEST F3]",
            get_tirage_fn=AsyncMock(return_value=real_em),
            game="em",
        )
        # F3 détecte étoiles fausses malgré boules correctes
        assert result is not None
        assert "5" in result or "11" in result  # vraies étoiles dans le safe
        assert any(
            "stars_mismatch=True" in r.message for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_em_match_stars_no_mismatch(self):
        """5 boules + 2 étoiles TOUTES correctes → None."""
        response = (
            "Tirage du 12 December 2025 : 7 - 25 - 30 - 37 - 41 stars 5 and 11"
        )
        real_em = {
            "date": date(2025, 12, 12),
            "boules": [7, 25, 30, 37, 41],
            "etoiles": [5, 11],
        }
        result = await _recheck_phase0_draw_accuracy(
            response, "0", "en", "[TEST F3]",
            get_tirage_fn=AsyncMock(return_value=real_em),
            game="em",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_loto_ignores_stars_branch(self):
        """game='loto' (default rétrocompat) → étoiles ignorées même si
        response contient 'stars'. Seules les boules comptent."""
        response = "28 mars 2026 : 17 - 28 - 30 - 38 - 45 (pas d'étoiles en loto)"
        real_loto = {
            "date": date(2026, 3, 28),
            "boules": [17, 28, 30, 38, 45],
            "chance": 6,
        }
        result = await _recheck_phase0_draw_accuracy(
            response, "0", "fr", "[TEST loto]",
            get_tirage_fn=AsyncMock(return_value=real_loto),
            game="loto",  # explicit
        )
        assert result is None


# ═════════════════════════════════════════════════════════════════════
# F4 — Test phare bug 12/12/2025 EM EN + non-régression Loto FR V126
# ═════════════════════════════════════════════════════════════════════


class TestV126_1_F4_BugsCritical:
    """V126.1 F4 : test bug terrain 12/12/2025 EM EN (log 2118)
    + non-régression V126 Loto FR bug 28/03/2026."""

    @pytest.mark.asyncio
    async def test_bug_12_12_2025_F01_phase0_reapply_EM_EN(self, caplog):
        """V126.1 test NON NÉGOCIABLE : bug log 2118 (20/04/2026 06:56:07).

        User : "yes" après "Want to know more about that draw?"
        Bot (halluc.) : "The draw on 12 December 2025: 13-15-23-30-49 and the stars: 3-8"
        Vrai (DB)     : 7-25-30-37-41 stars 5-11
        → mismatch 4/5 boules + 2/2 étoiles → replacement avec vrai tirage.
        """
        caplog.set_level(logging.WARNING)
        hallucinated = (
            "The draw on 12 December 2025: 13 - 15 - 23 - 30 - 49 "
            "and the stars: 3 - 8! 🎰 Want me to analyse this combo?"
        )
        real_em = {
            "date": date(2025, 12, 12),
            "boules": [7, 25, 30, 37, 41],
            "etoiles": [5, 11],
        }
        get_fn = AsyncMock(return_value=real_em)

        safe = await _recheck_phase0_draw_accuracy(
            response=hallucinated, phase="0", lang="en",
            log_prefix="[TEST BUG 2118]",
            get_tirage_fn=get_fn, game="em",
        )
        # Replacement obligatoire
        assert safe is not None, "V126.1 doit détecter le mismatch EM EN 2118"
        # Vrais chiffres dans safe
        assert "7" in safe or "07" in safe
        assert "25" in safe
        assert "37" in safe
        assert "41" in safe
        # Étoiles vraies
        assert "5" in safe or "11" in safe
        # Log warning émis avec mismatch marqué
        assert any("PHASE0_DRAW_MISMATCH" in r.message for r in caplog.records)
        # DB lookup avec bonne date
        get_fn.assert_awaited_once_with(date(2025, 12, 12))

    @pytest.mark.asyncio
    async def test_bug_28_03_2026_loto_fr_non_regression_V126(self, caplog):
        """Non-régression V126 : le test phare Loto FR doit encore passer
        après V126.1 (signature étendue avec param `game`)."""
        caplog.set_level(logging.WARNING)
        hallucinated = (
            "Oui ! Le tirage du 28 mars 2026 : 8 - 12 - 28 - 30 - 48 Chance : 4"
        )
        real_loto = {
            "date": date(2026, 3, 28),
            "boules": [17, 28, 30, 38, 45],
            "chance": 6,
        }
        safe = await _recheck_phase0_draw_accuracy(
            hallucinated, "0", "fr", "[TEST NR V126]",
            get_tirage_fn=AsyncMock(return_value=real_loto),
            game="loto",
        )
        assert safe is not None
        assert "17" in safe and "38" in safe and "45" in safe
        assert any("PHASE0_DRAW_MISMATCH" in r.message for r in caplog.records)
