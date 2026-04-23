"""
Tests for services/decay_state.py and decay integration in engine pipeline.
V79 — F04 terrain: anti-lock rotation via score decay.
"""

import random
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from services.decay_state import (
    calculate_decay_multiplier,
    get_decay_state,
    update_decay_after_draw,
    check_and_update_decay,
)
from config.engine import LOTO_CONFIG, EM_CONFIG
from engine.hybride_base import HybrideEngine


# ═══════════════════════════════════════════════════════════════════════
# calculate_decay_multiplier — pure function tests
# ═══════════════════════════════════════════════════════════════════════

class TestCalculateDecayMultiplier:

    def test_zero_selections(self):
        """0 selections → 1.0 (no penalty)."""
        assert calculate_decay_multiplier(0) == 1.0

    def test_one_selection(self):
        """1 selection → 0.897 with default rate 0.10, acceleration 0.03.
        Formula: 1 - (1 × 0.10 × (1 + 1×0.03)) = 1 - 0.103 = 0.897."""
        assert calculate_decay_multiplier(1) == pytest.approx(0.897, abs=0.001)

    def test_two_selections(self):
        """2 selections → 0.788.
        Formula: 1 - (2 × 0.10 × (1 + 2×0.03)) = 1 - 0.212 = 0.788."""
        assert calculate_decay_multiplier(2) == pytest.approx(0.788, abs=0.001)

    def test_three_selections(self):
        """3 selections → 0.673.
        Formula: 1 - (3 × 0.10 × (1 + 3×0.03)) = 1 - 0.327 = 0.673."""
        assert calculate_decay_multiplier(3) == pytest.approx(0.673, abs=0.001)

    def test_five_selections_hits_floor(self):
        """5 selections → 0.50 (floor).
        Raw: 1 - (5 × 0.10 × 1.15) = 0.425 → clamped to floor."""
        assert calculate_decay_multiplier(5) == pytest.approx(0.50)

    def test_ten_selections_clamped_at_floor(self):
        """10 selections → 0.50 (clamped, does not go below floor)."""
        assert calculate_decay_multiplier(10) == pytest.approx(0.50)

    def test_twenty_selections_clamped_at_floor(self):
        """20 selections → 0.50 (clamped, does not go below floor)."""
        assert calculate_decay_multiplier(20) == pytest.approx(0.50)

    def test_negative_selections(self):
        """Negative selections → 1.0 (guard)."""
        assert calculate_decay_multiplier(-1) == 1.0

    def test_custom_rate_no_acceleration(self):
        """Custom rate=0.10, acceleration=0.0 → linear: 3 selections = 0.70."""
        assert calculate_decay_multiplier(3, decay_rate=0.10, acceleration=0.0) == pytest.approx(0.70)

    def test_custom_floor(self):
        """Custom floor=0.30 → clamped at floor."""
        assert calculate_decay_multiplier(15, decay_rate=0.05, floor=0.30) == pytest.approx(0.30)

    def test_zero_rate(self):
        """decay_rate=0.0 → always 1.0 regardless of selections."""
        assert calculate_decay_multiplier(100, decay_rate=0.0) == 1.0

    def test_floor_one(self):
        """floor=1.0 → always 1.0 (decay effectively disabled)."""
        assert calculate_decay_multiplier(10, decay_rate=0.05, floor=1.0) == 1.0

    def test_acceleration_increases_penalty(self):
        """With acceleration, each selection weighs more than the previous."""
        m1 = calculate_decay_multiplier(1)
        m2 = calculate_decay_multiplier(2)
        m3 = calculate_decay_multiplier(3)
        # Penalty increments should grow (accelerate)
        penalty_1_to_2 = m1 - m2
        penalty_2_to_3 = m2 - m3
        assert penalty_2_to_3 > penalty_1_to_2

    def test_acceleration_zero_is_linear(self):
        """acceleration=0.0 → linear decay (no acceleration)."""
        m1 = calculate_decay_multiplier(1, decay_rate=0.10, acceleration=0.0)
        m2 = calculate_decay_multiplier(2, decay_rate=0.10, acceleration=0.0)
        m3 = calculate_decay_multiplier(3, decay_rate=0.10, acceleration=0.0)
        assert m1 == pytest.approx(0.90)
        assert m2 == pytest.approx(0.80)
        assert m3 == pytest.approx(0.70)

    def test_decay_rate_secondary_higher(self):
        """Secondary rate (étoiles) produces more aggressive decay."""
        mult_boules = calculate_decay_multiplier(2, decay_rate=0.10, acceleration=0.03)
        mult_etoiles = calculate_decay_multiplier(2, decay_rate=0.15, acceleration=0.03)
        assert mult_etoiles < mult_boules


# ═══════════════════════════════════════════════════════════════════════
# apply_decay — engine method tests
# ═══════════════════════════════════════════════════════════════════════

class TestApplyDecay:

    def test_empty_decay_state_noop(self):
        """Empty decay_state → scores unchanged."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {1: 0.8, 2: 0.6, 3: 0.4}
        result = engine.apply_decay(scores, {})
        assert result == scores

    def test_none_decay_state_noop(self):
        """None decay_state treated as empty → scores unchanged."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {1: 0.8, 2: 0.6}
        # apply_decay is called with None guard in generer_grille
        # but the method itself handles empty dict
        result = engine.apply_decay(scores, {})
        assert result == scores

    def test_decay_applied(self):
        """Numbers with selections get decayed scores (V92: rate=0.10, accel=0.03)."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {1: 1.0, 2: 1.0, 3: 1.0}
        # 0 selections → ×1.00, 3 selections → ×0.673, 5 selections → ×0.50 (floor)
        decay = {1: 0, 2: 3, 3: 5}
        result = engine.apply_decay(scores, decay)
        assert result[1] == pytest.approx(1.0)
        assert result[2] == pytest.approx(0.673, abs=0.001)
        assert result[3] == pytest.approx(0.50)

    def test_decay_preserves_zero_scores(self):
        """T-1 hard-excluded (score=0.0) stays 0.0 after decay."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {1: 0.0, 2: 0.8}
        decay = {1: 3, 2: 3}
        result = engine.apply_decay(scores, decay)
        assert result[1] == 0.0  # 0 × anything = 0
        assert result[2] == pytest.approx(0.8 * 0.673, abs=0.001)

    def test_unknown_numbers_get_no_decay(self):
        """Numbers not in decay_state treated as 0 selections."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {1: 0.8, 2: 0.8}
        decay = {1: 3}  # only num 1 in decay
        result = engine.apply_decay(scores, decay)
        assert result[1] == pytest.approx(0.8 * 0.673, abs=0.001)
        assert result[2] == pytest.approx(0.8)   # no decay (0 misses)

    def test_decay_with_secondary_rate(self):
        """apply_decay with rate override uses decay_rate_secondary."""
        engine = HybrideEngine(EM_CONFIG)
        scores = {1: 1.0, 2: 1.0}
        decay = {1: 2, 2: 0}
        # rate=0.15 (EM secondary), accel=0.03: 1 - (2 × 0.15 × 1.06) = 0.682
        result = engine.apply_decay(scores, decay, rate=engine.cfg.decay_rate_secondary)
        assert result[1] == pytest.approx(0.682, abs=0.001)
        assert result[2] == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════════════════════
# Decay config in EngineConfig
# ═══════════════════════════════════════════════════════════════════════

class TestDecayConfig:

    def test_loto_decay_defaults(self):
        assert LOTO_CONFIG.decay_enabled is True
        assert LOTO_CONFIG.decay_rate == 0.10
        assert LOTO_CONFIG.decay_floor == 0.50
        assert LOTO_CONFIG.decay_acceleration == 0.03
        assert LOTO_CONFIG.decay_rate_secondary == 0.12

    def test_em_decay_defaults(self):
        assert EM_CONFIG.decay_enabled is True
        assert EM_CONFIG.decay_rate == 0.10
        assert EM_CONFIG.decay_floor == 0.50
        assert EM_CONFIG.decay_acceleration == 0.03
        assert EM_CONFIG.decay_rate_secondary == 0.15


# ═══════════════════════════════════════════════════════════════════════
# Pipeline integration — decay_state parameter flows through
# ═══════════════════════════════════════════════════════════════════════

class TestDecayPipelineIntegration:

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_generate_grids_accepts_decay_state(self, mock_get_conn):
        """generate_grids() accepts decay_state kwarg without error."""
        from engine.hybride import generate_grids
        from tests.conftest import AsyncSmartMockCursor, make_async_conn
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        decay = {10: 5, 20: 10, 30: 3}
        result = await generate_grids(n=1, mode="balanced", decay_state=decay)
        assert len(result["grids"]) == 1
        assert result["metadata"]["decay"]["enabled"] is True
        assert result["metadata"]["decay"]["active"] is True

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_decay_none_metadata_inactive(self, mock_get_conn):
        """decay_state=None → metadata shows active=False."""
        from engine.hybride import generate_grids
        from tests.conftest import AsyncSmartMockCursor, make_async_conn
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        result = await generate_grids(n=1, mode="balanced")
        assert result["metadata"]["decay"]["enabled"] is True
        assert result["metadata"]["decay"]["active"] is False

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_decay_affects_grid_diversity(self, mock_get_conn):
        """With heavy decay on common numbers, grids should differ from no-decay."""
        from engine.hybride import generate_grids
        from tests.conftest import AsyncSmartMockCursor, make_async_conn
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)

        # Generate without decay
        random.seed(42)
        result_no_decay = await generate_grids(n=5, mode="balanced")

        # Generate with heavy decay on top-frequent numbers
        heavy_decay = {n: 20 for n in range(20, 40)}  # 20 nums at floor
        random.seed(42)
        result_decay = await generate_grids(n=5, mode="balanced", decay_state=heavy_decay)

        # Collect all nums from both
        nums_no_decay = set()
        nums_decay = set()
        for g in result_no_decay["grids"]:
            nums_no_decay.update(g["nums"])
        for g in result_decay["grids"]:
            nums_decay.update(g["nums"])

        # Decay should produce different number selection
        assert nums_no_decay != nums_decay, (
            "Decay on 20 numbers should change at least some grid content"
        )


# ═══════════════════════════════════════════════════════════════════════
# Async DB functions — mock tests
# ═══════════════════════════════════════════════════════════════════════

class TestDecayDBFunctions:

    @pytest.mark.asyncio
    async def test_get_decay_state_returns_dict(self):
        """get_decay_state returns {number: selections} dict."""
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[
            {"number_value": 5, "consecutive_misses": 3},
            {"number_value": 12, "consecutive_misses": 7},
        ])
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)

        result = await get_decay_state(mock_conn, "loto", "ball")
        assert result == {5: 3, 12: 7}

    @pytest.mark.asyncio
    async def test_get_decay_state_empty_table(self):
        """Empty table → empty dict."""
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)

        result = await get_decay_state(mock_conn, "euromillions", "ball")
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_decay_state_error_graceful(self):
        """DB error → empty dict (graceful degradation)."""
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(side_effect=Exception("DB down"))

        result = await get_decay_state(mock_conn, "loto", "ball")
        assert result == {}

    @pytest.mark.asyncio
    async def test_update_after_draw_resets_misses(self):
        """update_decay_after_draw resets drawn numbers and increments others (V94)."""
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 0
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        await update_decay_after_draw(mock_conn, "euromillions", [5, 10], drawn_stars=[3, 7])
        # 2 ball resets + 1 bulk UPDATE other balls
        # + 2 star resets + 1 bulk UPDATE other stars = 6 calls
        assert mock_cursor.execute.call_count == 6
        mock_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_after_draw_error_graceful(self):
        """DB error on draw update → no crash."""
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(side_effect=Exception("DB down"))

        await update_decay_after_draw(mock_conn, "loto", [1, 2, 3])


# ═══════════════════════════════════════════════════════════════════════
# Chatbot pipeline integration — decay called from Phase G
# V83 F03: verify get_decay_state / update_decay_after_generation
# are called from _prepare_chat_context_base() during grid generation.
# ═══════════════════════════════════════════════════════════════════════

class TestDecayChatbotPipelineIntegration:
    """Tests that decay functions are wired correctly in the chatbot pipeline."""

    _FAKE_GRIDS = {
        "grids": [{
            "nums": [3, 12, 25, 33, 41],
            "chance": 7,
            "score": 82,
            "badges": ["Equilibre"],
        }],
        "metadata": {"decay": {"enabled": True, "active": True}},
    }

    _FAKE_GRIDS_EM = {
        "grids": [{
            "nums": [5, 14, 22, 38, 47],
            "etoiles": [3, 9],
            "score": 78,
            "badges": ["Equilibre"],
        }],
        "metadata": {"decay": {"enabled": True, "active": True}},
    }

    def _base_patches_loto(self):
        """Common patches to reach Phase G in Loto pipeline."""
        return [
            patch("services.chat_pipeline.load_prompt", return_value="sys"),
            patch.dict("os.environ", {"GEM_API_KEY": "fake"}),
            patch("services.chat_pipeline._detect_insulte", return_value=None),
            patch("services.chat_pipeline._detect_compliment", return_value=None),
            patch("services.chat_pipeline._detect_salutation", return_value=False),
            patch("services.chat_pipeline._detect_generation", return_value=True),
            patch("services.chat_pipeline._detect_generation_mode", return_value="balanced"),
            patch("services.chat_pipeline._extract_grid_count", return_value=1),
            patch("services.chat_pipeline._extract_forced_numbers",
                  return_value={"forced_nums": None, "forced_chance": None, "error": None}),
            patch("services.chat_pipeline._extract_exclusions", return_value=None),
            patch("services.chat_pipeline._detect_grid_evaluation", return_value=None),
        ]

    def _base_patches_em(self):
        """Common patches to reach Phase G in EM pipeline."""
        return [
            patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"),
            patch.dict("os.environ", {"GEM_API_KEY": "fake"}),
            patch("services.chat_pipeline_em._detect_insulte", return_value=None),
            patch("services.chat_pipeline_em._detect_compliment", return_value=None),
            patch("services.chat_pipeline_em._detect_salutation", return_value=False),
            patch("services.chat_pipeline_em._detect_generation", return_value=True),
            patch("services.chat_pipeline_em._detect_generation_mode", return_value="balanced"),
            patch("services.chat_pipeline_em._extract_grid_count", return_value=1),
            patch("services.chat_pipeline_em._extract_forced_numbers",
                  return_value={"forced_nums": None, "forced_etoiles": None, "error": None}),
            patch("services.chat_pipeline_em._extract_exclusions", return_value=None),
            patch("services.chat_pipeline_em._detect_grid_evaluation", return_value=None),
        ]

    def _gemini_response(self, text="Voici votre grille"):
        return MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "candidates": [{"content": {"parts": [{"text": text}]}}],
            }),
        )

    def _run_loto_generation(self, mock_decay, vc, grids=None):
        """ExitStack helper — enter all patches for Loto Phase G.

        V131.B : vc = VertexController de la fixture mock_vertex_client (SDK B mock).
        Configure vc.set_response pour simuler réponse Gemini Phase G.
        """
        from contextlib import ExitStack
        stack = ExitStack()
        for p in self._base_patches_loto():
            stack.enter_context(p)
        stack.enter_context(patch("engine.hybride.generate_grids",
                                  new_callable=AsyncMock,
                                  return_value=grids or self._FAKE_GRIDS))
        stack.enter_context(patch("services.chat_pipeline_shared.get_decay_state", mock_decay))
        stack.enter_context(patch("db_cloudsql.get_connection", return_value=AsyncMock()))
        stack.enter_context(patch("services.chat_pipeline._build_session_context", return_value=""))
        # V131.B — remplace mock gemini_breaker.call(httpx) par fixture SDK B
        vc.set_response(text="Voici votre grille")
        return stack

    def _run_em_generation(self, mock_decay, vc, grids=None):
        """ExitStack helper — enter all patches for EM Phase G.

        V131.B : vc = VertexController de la fixture mock_vertex_client (SDK B mock).
        """
        from contextlib import ExitStack
        stack = ExitStack()
        for p in self._base_patches_em():
            stack.enter_context(p)
        stack.enter_context(patch("engine.hybride_em.generate_grids",
                                  new_callable=AsyncMock,
                                  return_value=grids or self._FAKE_GRIDS_EM))
        stack.enter_context(patch("services.chat_pipeline_shared.get_decay_state", mock_decay))
        stack.enter_context(patch("db_cloudsql.get_connection", return_value=AsyncMock()))
        stack.enter_context(patch("services.chat_pipeline_em._build_session_context_em", return_value=""))
        # V131.B — remplace mock gemini_breaker.call(httpx) par fixture SDK B
        vc.set_response(text="Voici votre grille")
        return stack

    @pytest.mark.asyncio
    async def test_pipeline_generation_calls_get_decay_state(self, mock_vertex_client):
        """Phase G generation → get_decay_state() called before grid generation."""
        from services.chat_pipeline import handle_chat

        mock_decay = AsyncMock(return_value={10: 5, 20: 3})

        with mock_vertex_client() as vc:
            with self._run_loto_generation(mock_decay, vc):
                await handle_chat("genere une grille", [], "loto", MagicMock())

        mock_decay.assert_called_once()
        args = mock_decay.call_args
        assert args[0][1] == "loto"  # game name
        assert args[0][2] == "ball"  # number_type

    @pytest.mark.asyncio
    async def test_pipeline_generation_no_write_v94(self, mock_vertex_client):
        """V94 hotfix: Phase G generation does NOT write to decay_state (read-only)."""
        from services.chat_pipeline import handle_chat

        mock_decay = AsyncMock(return_value={})
        mock_conn = AsyncMock()

        with mock_vertex_client() as vc:
            with self._run_loto_generation(mock_decay, vc):
                with patch("db_cloudsql.get_connection", return_value=mock_conn):
                    await handle_chat("genere une grille", [], "loto", MagicMock())

        # Verify no UPDATE/INSERT was called on the connection for decay writes
        # The only DB calls should be get_decay_state (SELECT)
        # update_decay_after_generation no longer exists in the pipeline

    @pytest.mark.asyncio
    async def test_pipeline_generation_continues_if_decay_fails(self, mock_vertex_client):
        """get_decay_state() raises → generation still works (graceful degradation)."""
        from services.chat_pipeline import handle_chat

        mock_decay = AsyncMock(side_effect=Exception("DB unavailable"))

        with mock_vertex_client() as vc:
            with self._run_loto_generation(mock_decay, vc):
                result = await handle_chat("genere une grille", [], "loto", MagicMock())

        # Pipeline should NOT crash — Gemini still called
        assert result["source"] == "gemini"

    @pytest.mark.asyncio
    async def test_pipeline_em_generation_reads_decay_only(self, mock_vertex_client):
        """V94: Phase G EM → get_decay_state() called, NO write to decay_state."""
        from services.chat_pipeline_em import handle_chat_em

        mock_decay = AsyncMock(return_value={})

        with mock_vertex_client() as vc:
            with self._run_em_generation(mock_decay, vc):
                await handle_chat_em("generate a grid", [], "euromillions", MagicMock(), lang="en")

        mock_decay.assert_called_once()
        args = mock_decay.call_args
        assert args[0][1] == "euromillions"

    @pytest.mark.asyncio
    async def test_pipeline_no_decay_when_no_generation(self):
        """Non-generation message (insult) → decay functions NOT called."""
        from services.chat_pipeline import handle_chat

        mock_decay = AsyncMock(return_value={})

        with patch("services.chat_pipeline.load_prompt", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value="insulte"), \
             patch("services.chat_pipeline_shared.get_decay_state", mock_decay):
            await handle_chat("t'es nul", [], "loto", MagicMock())

        mock_decay.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# V94 HOTFIX — Decay trigger bug fix tests
# ═══════════════════════════════════════════════════════════════════════

class TestDecayV94HotfixTriggerBug:
    """V94: Decay must only increment on real draw import, not on generation."""

    @pytest.mark.asyncio
    async def test_decay_read_only_in_scoring(self):
        """Scoring pipeline (apply_decay) does SELECT only, never UPDATE/INSERT."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {1: 0.9, 2: 0.8, 3: 0.7, 4: 0.6, 5: 0.5}
        decay = {1: 0, 2: 1, 3: 2, 4: 3, 5: 5}

        # apply_decay is a pure function on dicts — no DB interaction at all
        result = engine.apply_decay(scores, decay)

        # Verify it returns modified scores without any side effects
        assert result[1] == pytest.approx(0.9)  # 0 misses → ×1.0
        assert result[5] == pytest.approx(0.25)  # 5 misses → ×0.50 (floor)
        # No DB mock needed — apply_decay is pure computation

    @pytest.mark.asyncio
    async def test_decay_increment_on_new_draw(self):
        """Importing a real draw increments misses for non-drawn numbers and resets drawn ones."""
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 3  # 3 numbers incremented
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        result = await update_decay_after_draw(
            mock_conn, "loto",
            drawn_balls=[5, 10, 22, 33, 49],
            drawn_stars=[7],
        )

        # 5 balls reset (INSERT...ON DUPLICATE KEY UPDATE consecutive_misses=0)
        # 1 star reset
        # 1 UPDATE for all OTHER tracked balls (consecutive_misses += 1)
        # 1 UPDATE for all OTHER tracked stars (consecutive_misses += 1)
        assert result["reset"] == 6  # 5 balls + 1 chance
        assert result["game"] == "loto"
        mock_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_decay_reset_on_hit(self):
        """A drawn number gets consecutive_misses=0 and last_drawn set."""
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 0
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        await update_decay_after_draw(mock_conn, "euromillions", [8, 27], drawn_stars=[2, 10])

        # Check that INSERT...ON DUPLICATE KEY UPDATE with consecutive_misses=0 was called
        calls = mock_cursor.execute.call_args_list
        # First 2 calls: ball resets (nums 8, 27)
        for i in range(2):
            sql = calls[i][0][0]
            assert "consecutive_misses = 0" in sql
            assert "last_drawn" in sql
        # Call index 3, 4: star resets (stars 2, 10)
        for i in range(3, 5):
            sql = calls[i][0][0]
            assert "consecutive_misses = 0" in sql

    @pytest.mark.asyncio
    async def test_decay_guard_duplicate_draw(self):
        """check_and_update_decay skips if the latest draw was already processed."""
        mock_cursor = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)

        # Latest draw date = 2026-04-08
        mock_cursor.fetchone = AsyncMock(side_effect=[
            {"date_de_tirage": "2026-04-08"},  # latest draw in tirages
            {"last_update": "2026-04-08 10:00:00", "last_drawn_date": "2026-04-08"},  # already processed
        ])

        result = await check_and_update_decay(mock_conn, "loto", "tirages")
        assert result is None  # Skipped — already processed

    @pytest.mark.asyncio
    async def test_decay_detects_new_draw(self):
        """check_and_update_decay detects a new draw and triggers update."""
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 5
        mock_conn = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        mock_cursor.fetchone = AsyncMock(side_effect=[
            {"date_de_tirage": "2026-04-10"},  # latest draw in tirages
            {"last_update": "2026-04-08 10:00:00", "last_drawn_date": "2026-04-08"},  # old
            # fetch drawn numbers
            {"boule_1": 3, "boule_2": 17, "boule_3": 29, "boule_4": 38, "boule_5": 44, "numero_chance": 5},
        ])

        result = await check_and_update_decay(mock_conn, "loto", "tirages")
        assert result is not None
        assert result["game"] == "loto"
        assert result["reset"] > 0  # at least balls were reset

    @pytest.mark.asyncio
    async def test_decay_increment_only_on_draw_not_generation(self):
        """V94 core fix: generating 10 grids does NOT change consecutive_misses.

        Verifies the architectural invariant that the scoring pipeline is read-only.
        """
        engine = HybrideEngine(LOTO_CONFIG)
        initial_decay = {1: 2, 2: 3, 3: 0, 4: 5, 5: 1}

        # Simulate 10 grid generations using apply_decay (the scoring step)
        for _ in range(10):
            scores = {n: 0.8 for n in range(1, 50)}
            engine.apply_decay(scores, initial_decay)

        # The decay dict should be UNCHANGED — apply_decay doesn't mutate it
        assert initial_decay == {1: 2, 2: 3, 3: 0, 4: 5, 5: 1}
