"""
V137.C — Tests `get_next_draw_date_db_aware` (BDD-aware next draw date helper).
================================================================================

Contexte : V137.B en prod a révélé un bug le 29/04/2026 : 55 grilles polluantes
générées entre 21h12 et 22h27 ciblaient le tirage du 29/04 alors que celui-ci
avait déjà eu lieu (20h50, inséré ~21h30 en BDD). Root cause : la fonction
sync `get_next_draw_date` (V110) calcule la prochaine date à partir du calendrier
hebdomadaire + heure cutoff hardcodée (Loto 21h, EM 22h), sans consulter la BDD.

Fix V137.C : nouveau helper async `get_next_draw_date_db_aware(game, conn, ref)`
qui utilise la **présence du résultat officiel en BDD** comme source de vérité.

Tests structurés en 3 classes :
- TestComputeNextDrawDateLoto (5 tests)
- TestComputeNextDrawDateEm (3 tests)
- TestComputeNextDrawDateRobustness (1 test fallback)

Pattern mocks : `MagicMock` + `AsyncMock` pour conn.cursor()/execute()/fetchone().
Pattern logger : `patch("config.games.logger")` direct (leçon V135 — caplog ne
propage pas avec handler JSON custom).

DST skip : DST n'affecte pas l'arithmétique `date + timedelta(days=i)` (objects
`date` sans tzinfo) — la fonction n'utilise pas `datetime.now()` pour itérer.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.games import ValidGame, get_next_draw_date_db_aware


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_mock_conn(fetchone_side_effect):
    """Build a MagicMock conn whose cursor.fetchone returns successive values.

    Args:
        fetchone_side_effect: list of return values for successive fetchone()
                              calls. Each item must be either None (= no row)
                              or a dict (= row exists).
    """
    cur = MagicMock()
    cur.execute = AsyncMock()
    cur.fetchone = AsyncMock(side_effect=fetchone_side_effect)
    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cur)
    return conn, cur


# ═══════════════════════════════════════════════════════════════════════════
# TestComputeNextDrawDateLoto (5 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeNextDrawDateLoto:
    """Loto FR weekdays = lundi (0), mercredi (2), samedi (5)."""

    @pytest.mark.asyncio
    async def test_before_draw_no_result_yet_returns_today(self):
        """Mercredi 29/04 19h, BDD vide pour 29/04 → returns 2026-04-29."""
        # 29/04/2026 = mercredi (weekday 2 ∈ Loto)
        ref = datetime.datetime(2026, 4, 29, 19, 0)
        # Premier candidat = 29/04, fetchone retourne None (pas encore tiré)
        conn, _ = _make_mock_conn(fetchone_side_effect=[None])

        result = await get_next_draw_date_db_aware(ValidGame.loto, conn, ref)

        assert result == datetime.date(2026, 4, 29)

    @pytest.mark.asyncio
    async def test_after_draw_result_inserted_returns_next(self):
        """Mercredi 29/04 22h, BDD a row 29/04 → returns 2026-05-02 (samedi).

        Pipeline insertion OK : on avance vers le tirage suivant. Cas nominal.
        """
        # 29/04/2026 = mercredi, 02/05/2026 = samedi
        ref = datetime.datetime(2026, 4, 29, 22, 0)
        # 1er candidat 29/04 → row trouvée, 2e candidat (jeudi 30/04) skipped
        # weekday non-tirage, 3e (vendredi 01/05) skipped, 4e (samedi 02/05)
        # → fetchone retourne None.
        # Note : la boucle skippe les non-tirage SANS appeler fetchone, donc
        # seul le 1er fetchone (29/04 → row) puis le 2nd (02/05 → None).
        conn, _ = _make_mock_conn(fetchone_side_effect=[{"found": 1}, None])

        result = await get_next_draw_date_db_aware(ValidGame.loto, conn, ref)

        assert result == datetime.date(2026, 5, 2)

    @pytest.mark.asyncio
    async def test_after_draw_pipeline_late_returns_today_NOT_next(self):
        """🎯 TEST CRITIQUE V137.C : Loto 29/04 22h, BDD VIDE pour 29/04 → 2026-04-29.

        Pipeline d'import retardé : le tirage a eu lieu à 20h50 mais la row
        n'est pas encore en BDD à 22h. Comportement attendu V137.C : on
        continue à cibler 29/04 (cohérent avec l'absence en BDD), pas 02/05.

        C'est exactement le bug initial qui a motivé V137.C. La version V110
        sync aurait retourné 02/05 (cutoff 21h dépassé) → 55 grilles polluantes.
        """
        # 29/04/2026 = mercredi 22h, BDD vide pour 29/04 (pipeline retardé)
        ref = datetime.datetime(2026, 4, 29, 22, 0)
        conn, _ = _make_mock_conn(fetchone_side_effect=[None])

        result = await get_next_draw_date_db_aware(ValidGame.loto, conn, ref)

        # CRITIQUE : reste sur 29/04 même à 22h, source de vérité = BDD
        assert result == datetime.date(2026, 4, 29)

    @pytest.mark.asyncio
    async def test_non_draw_day_returns_next_draw(self):
        """Vendredi 30/04 (pas un jour Loto), BDD vide → returns 02/05 (samedi)."""
        # 30/04/2026 = vendredi (weekday 4 ∉ Loto)
        ref = datetime.datetime(2026, 4, 30, 10, 0)
        # Boucle : 30/04 vendredi (skip), 01/05 vendredi → en fait 01/05 est
        # samedi non — recheck : 01/05/2026 = vendredi, 02/05/2026 = samedi
        # Donc i=0 vendredi skip, i=1 samedi → fetchone retourne None
        conn, _ = _make_mock_conn(fetchone_side_effect=[None])

        result = await get_next_draw_date_db_aware(ValidGame.loto, conn, ref)

        assert result == datetime.date(2026, 5, 2)

    @pytest.mark.asyncio
    async def test_log_auto_advance_emitted_when_skipping(self):
        """Skipped non-vide → log [NEXT_DRAW] auto-advance émis.
        Skipped vide → AUCUN log [NEXT_DRAW] auto-advance émis.
        """
        # ── Cas 1 : skipped non-vide (1 candidat skipped) ──
        ref1 = datetime.datetime(2026, 4, 29, 22, 0)  # mercredi
        conn1, _ = _make_mock_conn(fetchone_side_effect=[{"found": 1}, None])

        with patch("config.games.logger") as mock_logger:
            result = await get_next_draw_date_db_aware(ValidGame.loto, conn1, ref1)

            assert result == datetime.date(2026, 5, 2)
            # Vérifier qu'au moins un appel logger.info contient [NEXT_DRAW]
            info_calls = [
                c for c in mock_logger.info.call_args_list
                if c.args and "[NEXT_DRAW] auto-advance" in str(c.args[0])
            ]
            assert len(info_calls) == 1, (
                f"Expected 1 [NEXT_DRAW] auto-advance log, got {len(info_calls)}"
            )
            # Vérifier le contenu structuré
            call_args = info_calls[0].args
            assert call_args[1] == "loto"  # game.value
            assert "2026-04-29" in str(call_args[2])  # skipped contient 29/04
            assert call_args[3] == "2026-05-02"  # next candidate

        # ── Cas 2 : skipped vide (0 candidat skipped) ──
        ref2 = datetime.datetime(2026, 4, 29, 19, 0)  # mercredi avant tirage
        conn2, _ = _make_mock_conn(fetchone_side_effect=[None])

        with patch("config.games.logger") as mock_logger:
            result = await get_next_draw_date_db_aware(ValidGame.loto, conn2, ref2)

            assert result == datetime.date(2026, 4, 29)
            # AUCUN log [NEXT_DRAW] auto-advance ne doit être émis
            info_calls = [
                c for c in mock_logger.info.call_args_list
                if c.args and "[NEXT_DRAW] auto-advance" in str(c.args[0])
            ]
            assert len(info_calls) == 0, (
                f"Expected 0 [NEXT_DRAW] auto-advance log when skipped empty, "
                f"got {len(info_calls)}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# TestComputeNextDrawDateEm (3 tests symétrie V99 F09)
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeNextDrawDateEm:
    """EuroMillions weekdays = mardi (1), vendredi (4)."""

    @pytest.mark.asyncio
    async def test_em_before_draw_no_result_yet_returns_today(self):
        """Mardi 28/04 19h EM, BDD vide → returns 2026-04-28."""
        # 28/04/2026 = mardi (weekday 1 ∈ EM)
        ref = datetime.datetime(2026, 4, 28, 19, 0)
        conn, _ = _make_mock_conn(fetchone_side_effect=[None])

        result = await get_next_draw_date_db_aware(
            ValidGame.euromillions, conn, ref,
        )

        assert result == datetime.date(2026, 4, 28)

    @pytest.mark.asyncio
    async def test_em_after_draw_result_inserted_returns_next(self):
        """Mardi 28/04 22h EM, BDD a row 28/04 → returns 2026-05-01 (vendredi)."""
        # 28/04 = mardi, 01/05 = vendredi
        ref = datetime.datetime(2026, 4, 28, 22, 0)
        # 1er fetchone (28/04) → row, 2e fetchone (01/05) → None
        # (mer 29 jeu 30 skipped sans fetchone)
        conn, _ = _make_mock_conn(fetchone_side_effect=[{"found": 1}, None])

        result = await get_next_draw_date_db_aware(
            ValidGame.euromillions, conn, ref,
        )

        assert result == datetime.date(2026, 5, 1)

    @pytest.mark.asyncio
    async def test_em_friday_already_drawn_returns_tuesday_next_week(self):
        """Vendredi 01/05 22h EM, BDD a row 01/05 → returns 2026-05-05 (mardi)."""
        # 01/05/2026 = vendredi, 05/05/2026 = mardi suivant
        ref = datetime.datetime(2026, 5, 1, 22, 0)
        # 1er fetchone (01/05) → row, 2e fetchone (05/05) → None
        # (sam 02, dim 03, lun 04 skipped sans fetchone)
        conn, _ = _make_mock_conn(fetchone_side_effect=[{"found": 1}, None])

        result = await get_next_draw_date_db_aware(
            ValidGame.euromillions, conn, ref,
        )

        assert result == datetime.date(2026, 5, 5)


# ═══════════════════════════════════════════════════════════════════════════
# TestComputeNextDrawDateRobustness (1 test defensive)
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeNextDrawDateRobustness:
    """Defense in depth — V135 lesson : fallback sync sur edge case."""

    @pytest.mark.asyncio
    async def test_no_draw_day_in_8_days_falls_back_to_sync(self):
        """Cas pathologique (mock weekdays vides via patch GAME_CONFIGS) :
        aucun candidat libre dans 8 jours → log warning + fallback sync.

        Le fallback sync `get_next_draw_date` retourne `today` en dernier
        recours (cf. games.py:156). Pas de raise (philosophie defense in
        depth V135 confirmée).

        DST skip : DST n'affecte pas `date + timedelta(days=i)` (objects
        `date` sans tzinfo) — non testé séparément.
        """
        ref = datetime.datetime(2026, 4, 29, 19, 0)
        # Boucle de 8 itérations sans aucun fetchone (toutes skip)
        # car target_weekdays sera vide
        conn, cur = _make_mock_conn(fetchone_side_effect=[None] * 8)

        with patch("config.games.GAME_CONFIGS") as mock_configs:
            from config.games import RouteGameConfig
            # Config Loto avec draw_days vide → target_weekdays vide
            mock_configs.__getitem__.return_value = RouteGameConfig(
                slug="loto", table="tirages",
                stats_module="services.stats_service",
                engine_module="engine.hybride",
                engine_stats_module="engine.stats",
                chat_pipeline_module="services.chat_pipeline",
                num_range=(1, 49), secondary_range=(1, 10),
                secondary_name="chance", secondary_column="numero_chance",
                num_count=5, secondary_count=1,
                draw_days=[],  # ← weekdays vides
            )

            with patch("config.games.logger") as mock_logger:
                result = await get_next_draw_date_db_aware(
                    ValidGame.loto, conn, ref,
                )

                # Fallback sync `get_next_draw_date(loto, ref)` avec weekdays
                # vides retourne `today` (cf. games.py:156 fallback final)
                assert isinstance(result, datetime.date)
                # Vérifier que le warning [NEXT_DRAW] no candidate a été émis
                warning_calls = [
                    c for c in mock_logger.warning.call_args_list
                    if c.args and "[NEXT_DRAW] no candidate" in str(c.args[0])
                ]
                assert len(warning_calls) == 1, (
                    f"Expected 1 [NEXT_DRAW] no candidate warning, "
                    f"got {len(warning_calls)}"
                )
                # fetchone n'a JAMAIS été appelé (weekdays vides → tous skip)
                assert cur.fetchone.call_count == 0
